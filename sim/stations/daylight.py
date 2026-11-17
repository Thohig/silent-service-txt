"""Vakthavande håller koll på ljuset: när solen går ned och upp, när det blir mörkt och när
månen går upp, ur almanackan (`Knowledge.almanac`), aldrig ur världen.

Utropen: solnedgång om en halvtimme, solen nere, mörkt (med månen), gryningen börjar,
soluppgång om en halvtimme, solen uppe, månen går upp (om den lyser nog). Ligger vi i
ytläge i dagsljus med ett hot i plottet och solen går ned inom 45 minuter föreslår han att
vi går ned och väntar på mörkret: i dagsljus ser en jagare oss på tio sjömil, i mörker på sex.
"""
from __future__ import annotations

from .. import phrases
from .. import russian as R
from ..crew import Role
from ..environment import NAUTICAL_ELEV, SUNRISE_ELEV, Light
from ..fmt import fmt_course
from .base import Station

CHECK_S = 30                 # så ofta vakthavande ser på klockan och himlen
SOON_S = 30 * 60             # förvarning före solnedgång och soluppgång
WAIT_DARK_S = 45 * 60        # så nära solnedgången föreslås att vänta på mörkret
WAIT_DARK_DEPTH = 40
MOONRISE_FRAC = 0.3          # månen ropas ut när den lyser så här mycket


def _moon_text(lt: Light) -> str:
    if lt.moon_elev <= 0:
        return "Månen är nere."
    if lt.moon_frac < 0.05:
        return "Nymåne, inget månljus."
    return (f"Månen, {lt.moon_frac * 100:.0f} procent, står i {fmt_course(lt.moon_az)}"
            + (", det lyser på sjön åt det hållet." if lt.moon_light >= 0.2 else "."))


def _moon_ru(lt: Light) -> str:
    if lt.moon_elev <= 0 or lt.moon_frac < 0.05:
        return "Луны нет."
    return f"Луна по пеленгу {R.course(lt.moon_az)}."


PHRASES = {
    "light.sunset_soon": lambda d: f"Kapten, vakthavande. Solnedgång om {d['minutes']} minuter.",
    "light.sunrise_soon": lambda d: f"Kapten, vakthavande. Soluppgång om {d['minutes']} minuter.",
    "light.sunset": lambda d: "Solen har gått ned. En halvtimme till syns fartyg som siluetter, "
    f"längst mot den ljusa himlen i {fmt_course(d['sun'])}.",
    "light.dark": lambda d: f"Det är mörkt. Bara lanternor syns nu. {d['moon']}",
    "light.dawn": lambda d: f"Gryningen börjar i {fmt_course(d['sun'])}. Fartyg åt det hållet "
    "syns snart som siluetter mot den ljusa himlen.",
    "light.sunrise": lambda d: "Solen är uppe.",
    "light.moonrise": lambda d: f"Månen går upp i {fmt_course(d['bearing'])}, "
    f"{d['frac']:.0f} procent. Det ljusnar på sjön åt det hållet.",
    "light.suggest.wait_dark": lambda d: f"Kapten, vakthavande. Solnedgång om {d['minutes']} "
    "minuter och vi har ett hot i plottet. I dagsljus ser de oss i ytläge på tio sjömil, i mörker "
    f"på sex. Föreslår att vi går ned till {d['depth']} meter och väntar på mörkret.",
}
phrases.register(PHRASES)

RU_PHRASES = {
    "light.sunset_soon": lambda d: f"{R.CAPTAIN}, вахтенный. Заход солнца через "
    f"{R.count(d['minutes'], R.MINUTE)}.",
    "light.sunrise_soon": lambda d: f"{R.CAPTAIN}, вахтенный. Восход солнца через "
    f"{R.count(d['minutes'], R.MINUTE)}.",
    "light.sunset": lambda d: "Солнце зашло. Сумерки.",
    "light.dark": lambda d: f"Стемнело. {d.get('moon_ru', '')}".strip(),
    "light.dawn": lambda d: f"Светает, пеленг {R.course(d['sun'])}.",
    "light.sunrise": lambda d: "Солнце взошло.",
    "light.moonrise": lambda d: f"Взошла луна, пеленг {R.course(d['bearing'])}.",
    "light.suggest.wait_dark": lambda d: f"{R.CAPTAIN}, вахтенный. Скоро стемнеет. "
    "Предлагаю погрузиться и дождаться темноты.",
}
phrases.register_ru(RU_PHRASES)


class LightWatch(Station):
    """Vakthavande om dagsljuset (roll vakthavande, som bryggan och periskopet)."""
    role = Role.OFFICER

    def __init__(self, game):
        super().__init__(game)
        self._prev: Light | None = None
        self._warned: set[tuple[str, int]] = set()     # (vad, dygn) som redan sagts

    def update(self) -> None:
        alm = self.game.knowledge.almanac
        if alm is None or self.now % CHECK_S:
            return
        lt = alm.light(self.now)
        prev, self._prev = self._prev, lt
        day = (alm.clock_start + self.now) // 86400
        if prev is not None:
            self._crossings(prev, lt, day)
        self._soon(alm, lt, day)

    def _once(self, what: str, day: int) -> bool:
        if (what, day) in self._warned:
            return False
        self._warned.add((what, day))
        return True

    def _crossings(self, prev: Light, lt: Light, day: int) -> None:
        if prev.sun_elev > SUNRISE_ELEV >= lt.sun_elev and self._once("sunset", day):
            self.say("light.sunset", {"sun": lt.sun_az})
        elif prev.sun_elev > NAUTICAL_ELEV >= lt.sun_elev and self._once("dark", day):
            self.say("light.dark", {"moon": _moon_text(lt), "moon_ru": _moon_ru(lt)})
        elif prev.sun_elev <= NAUTICAL_ELEV < lt.sun_elev and self._once("dawn", day):
            self.say("light.dawn", {"sun": lt.sun_az})
        elif prev.sun_elev <= SUNRISE_ELEV < lt.sun_elev and self._once("sunrise", day):
            self.say("light.sunrise")
        if prev.moon_elev <= 0 < lt.moon_elev and lt.moon_frac >= MOONRISE_FRAC \
                and lt.phase in ("nautisk", "natt") and self._once("moonrise", day):
            self.say("light.moonrise", {"bearing": lt.moon_az, "frac": lt.moon_frac * 100})

    def _minutes_until(self, alm, up: bool, limit_s: int) -> int | None:
        """Minuter tills solens överkant passerar horisonten (uppåt eller nedåt), inom limit_s."""
        for m in range(1, limit_s // 60 + 1):
            e = alm.light(self.now + 60 * m).sun_elev
            if (e > SUNRISE_ELEV) == up:
                return m
        return None

    def _soon(self, alm, lt: Light, day: int) -> None:
        if lt.sun_elev > SUNRISE_ELEV:
            m = self._minutes_until(alm, False, max(SOON_S, WAIT_DARK_S))
            if m is None:
                return
            if m <= SOON_S // 60 and self._once("sunset_soon", day):
                self.say("light.sunset_soon", {"minutes": m})
            own = self.game.world.own
            if own.surfaced and self.game.knowledge.threat_held():
                self.suggest("wait_dark", "light.suggest.wait_dark",
                             {"minutes": m, "depth": WAIT_DARK_DEPTH},
                             order=f"djup {WAIT_DARK_DEPTH}", cooldown=3600)
        else:
            m = self._minutes_until(alm, True, SOON_S)
            if m is not None and self._once("sunrise_soon", day):
                self.say("light.sunrise_soon", {"minutes": m})
