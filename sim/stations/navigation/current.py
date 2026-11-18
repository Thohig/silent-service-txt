"""Strömmen (N1): navigatören räknar den ur skillnaden mellan besticket och fixarna.

Vid varje fix är restfelet i besticket sedan förra fixen, delat med tiden, en mätning av den
ström besticket inte räknat med (`_current_measure`). Felet har två fixars osäkerhet och loggens
och gyrots fel längs den gångna vägen; mätningar över kortare tid än `CURRENT_MIN_S` är för
brusiga och används inte, och inte heller tid på botten (strömmen flyttar oss inte då).
Mätningarna vägs ihop (Kalman per axel, strömmen får ändra sig `CURRENT_DRIFT_KN2_PER_H`).

Kvaliteten följer osäkerheten (`current_quality`). Från osäker räknar besticket med strömmen;
från god växer bestickets osäkerhet långsammare (`CURRENT_GROWTH_FACTOR`). Navigatören säger
till när han först har en ström och när den ändrat sig, och på `ström`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ... import phrases
from ... import russian as R
from ...fmt import fmt_course, nm
from ...geo import norm360
from ...orders import Order
from ...reports import Quality

CURRENT_MIN_S = 1200               # kortare tid mellan fixarna: för brusigt
CURRENT_DRIFT_KN2_PER_H = 0.01     # strömmen ändrar sig (tidvatten, virvlar)
CURRENT_PRIOR_KN = 0.5             # före första mätningen: σ per axel
LOG_ERR = 0.02                     # loggens och gyrots fel, andel av den gångna vägen
CURRENT_GROWTH_FACTOR = 0.5        # bestickets osäkerhet växer så mycket långsammare med god ström
CURRENT_SAY_KN = 0.15              # säger till när strömmen ändrat sig så mycket …
CURRENT_SAY_DEG = 30               # … eller så många grader
QUALITY_SIGMA = ((0.05, Quality.SAKER), (0.1, Quality.GOD), (0.25, Quality.OSAKER))


@dataclass(frozen=True)
class CurrentReport(Order):
    pass


def _set_and_drift(vx: float, vy: float) -> tuple[float, float]:
    """(riktning dit strömmen sätter, knop)."""
    return norm360(math.degrees(math.atan2(vx, vy))), math.hypot(vx, vy)


def _current_text(d: dict) -> str:
    if d.get("none"):
        return "Ingen ström uppmätt än, kapten. Det behövs två fixar med en stund emellan."
    q = Quality(d["quality"]).label
    if d["kn"] < 0.05:
        return f"Ingen märkbar ström, kapten ({q})."
    return f"Strömmen sätter {fmt_course(d['set'])}, {nm(d['kn'])} knop ({q}). Besticket räknar med den." \
        if d["quality"] >= Quality.OSAKER else \
        f"Strömmen sätter kanske {fmt_course(d['set'])}, {nm(d['kn'])} knop, men det är för osäkert " \
        "för besticket."


PHRASES = {
    "nav.current": lambda d: f"Kapten, navigatören. {_current_text(d)}",
    "nav.current.report": _current_text,
}
phrases.register(PHRASES)


def _ru_current(d: dict) -> str:
    if d.get("none"):
        return "Течение ещё не определено. Нужны два места с промежутком."
    if d["kn"] < 0.05:
        return "Заметного течения нет."
    return (f"Течение {R.course(d['set'])}, {R.dec(d['kn'], R.KNOT)}, "
            f"оценка {R.QUALITY_RU[d['quality']]}.")


RU_PHRASES = {
    "nav.current": lambda d: f"{R.CAPTAIN}, штурман. {_ru_current(d)}",
    "nav.current.report": _ru_current,
}
phrases.register_ru(RU_PHRASES)


class CurrentMixin:
    """Del av NavigationStation (station.py)."""

    def _current_init(self) -> None:
        self.cur_vx = self.cur_vy = 0.0           # uppskattad ström (knop, öst/nord)
        self.cur_var = CURRENT_PRIOR_KN ** 2      # per axel
        self.cur_n = 0                             # mätningar hittills
        self._cur_said: tuple[float, float] | None = None
        self._cur_since_fix_ok = True              # ingen tid på botten sedan förra fixen

    # --- bedömningen ------------------------------------------------------------------
    @property
    def current_sigma(self) -> float:
        return math.sqrt(self.cur_var)

    def current_quality(self) -> Quality | None:
        if self.cur_n == 0:
            return None
        for limit, q in QUALITY_SIGMA:
            if self.current_sigma < limit:
                return q
        return Quality.DALIG

    def current_used(self) -> tuple[float, float]:
        """Strömmen besticket räknar med (knop per axel): bara från osäker."""
        q = self.current_quality()
        return (self.cur_vx, self.cur_vy) if q is not None and q >= Quality.OSAKER else (0.0, 0.0)

    def dr_growth_factor(self) -> float:
        q = self.current_quality()
        return CURRENT_GROWTH_FACTOR if q is not None and q >= Quality.GOD else 1.0

    def _current_age(self) -> None:
        """Varje sekund: strömmen kan ha ändrat sig; tid på botten gör mätningen ogiltig."""
        self.cur_var += CURRENT_DRIFT_KN2_PER_H / 3600.0
        if self.own.sys.on_bottom:
            self._cur_since_fix_ok = False

    def _current_measure(self, x: float, y: float, sigma: float) -> None:
        """En fix: restfelet i besticket sedan förra fixen är strömmen besticket missat."""
        dt_h = (self.now - self.last_fix_t) / 3600.0
        ok, self._cur_since_fix_ok = self._cur_since_fix_ok, True
        if not ok or dt_h * 3600 < CURRENT_MIN_S:
            return
        run = math.hypot(self.est_x - self.fixes[-1][0], self.est_y - self.fixes[-1][1]) \
            if self.fixes else 0.0
        err = math.sqrt(self.fix_sigma ** 2 + sigma ** 2 + (LOG_ERR * run) ** 2) / dt_h
        used_x, used_y = self.current_used()
        zx = used_x + (x - self.est_x) / dt_h
        zy = used_y + (y - self.est_y) / dt_h
        r = err * err
        k = self.cur_var / (self.cur_var + r)
        self.cur_vx += k * (zx - self.cur_vx)
        self.cur_vy += k * (zy - self.cur_vy)
        self.cur_var *= 1 - k
        self.cur_n += 1
        self._current_tell()

    def _current_data(self) -> dict:
        if self.cur_n == 0:
            return {"none": True}
        st, kn = _set_and_drift(self.cur_vx, self.cur_vy)
        return {"set": round(st), "kn": round(kn, 1), "quality": int(self.current_quality())}

    def _current_tell(self) -> None:
        """Säg till första gången strömmen är minst osäker, och när den ändrat sig."""
        q = self.current_quality()
        if q is None or q < Quality.OSAKER:
            return
        st, kn = _set_and_drift(self.cur_vx, self.cur_vy)
        if self._cur_said is not None:
            s0, k0 = self._cur_said
            turned = abs((st - s0 + 180) % 360 - 180) >= CURRENT_SAY_DEG and max(kn, k0) >= 0.1
            if abs(kn - k0) < CURRENT_SAY_KN and not turned:
                return
        self._cur_said = (st, kn)
        self.say("nav.current", self._current_data(), quality=q)

    def _current_report(self) -> None:
        self.say("nav.current.report", self._current_data(), quality=self.current_quality())

    def current_gauge_text(self) -> str | None:
        if self.cur_n == 0:
            return None
        st, kn = _set_and_drift(self.cur_vx, self.cur_vy)
        q = self.current_quality().label
        return f"{fmt_course(st)} {nm(kn)} kn ({q})" if kn >= 0.05 else f"ingen ({q})"

    def current_velocity(self) -> tuple[float, float]:
        """Det besticket lägger till per sekund (sjömil)."""
        vx, vy = self.current_used()
        return vx / 3600.0, vy / 3600.0

