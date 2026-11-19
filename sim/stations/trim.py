"""Trimmaren (трюмный) vid trimposten i centralen: hur tung båten är, och att trimma den.

Bedömningen bygger på egna instrument: vad som pumpats och skjutits (känt exakt), läckan
(ungefär), djupet (skrovet trycks ihop, känt ungefär; skiktet och smältvattnet okänt) och
var tionde sekund djuprodret och djupets drift (`MEASURE_S`), som mäter vikten med ett fel
som växer med farten (rodren tar mer last ju fortare vi går). Kvaliteten följer osäkerheten
(`SIGMA_QUALITY`).

Trimmaren pumpar själv i vanlig gång. Vid tyst gång (smygmotorn) ber han först,
eftersom pumparna hörs, utom när båten är så ur trim att rodren inte bär (då pumpar han och
säger varför). `trim stopp` håller pumparna stilla tills nästa `trimma`, utom i fara.
`ligg still`: fart 0, djupet hålls bara med trimmen; trimmaren trimmar tätare.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import phrases
from .. import russian as R
from .. import trim as T
from ..crew import Role
from ..fmt import nm
from ..orders import CommandSpec, Order
from ..ownship import BROACH_DEPTH_M, heave_depth_f, heave_speed_f
from ..reports import Quality
from ..russian import ru
from ..systems import INFO, OFF, OK, WARN, Gauge, TrimTanks
from .base import Proposal, Station

MEASURE_S = 10                 # rodret och driften läses så här ofta
TRIM_AT_T = 1.0                # obalans som trimmas bort
FORE_AT_T = 1.5                # framåt- eller bakåtlast som trimmas bort
HOVER_AT_T = 0.3               # när vi ligger still
HOVER_MAX_SIGMA_T = 0.6        # så säker måste bedömningen vara för att ligga still
DEPTH_VAR_T2_PER_M = 0.02      # okänt per meter djupändring (skiktet, smältvattnet)
AGE_VAR_T2_PER_S = 0.0005      # okänt med tiden (vattnets täthet, förbrukning): σ +0,5 t på 10 min
MEASURE_BASE_T = 0.2           # rodret och driften: fel i ton …
MEASURE_PER_T = 0.03           # … plus så mycket per ton rodren bär (större last, sämre mått)
FLOOD_SIGMA = 0.1              # läckvattnet: pejlat ungefär
FORE_SIGMA_T = 0.2             # lutningsmätaren
SIGMA_QUALITY = (0.4, 0.8, 1.6)    # σ (ton) under: säker, god, osäker; annars dålig
REPORT_PUMP_T = 2.0            # så stora trimningar säger han till om
NOTHING_T = 0.1                # `trimma` med mindre obalans: inget att pumpa
# Sjön suger (V3): djupmätaren slår i takt med sjön. Trimmaren ser utslaget och vet hur grunt
# kölen kan gå innan tornet bryter ytan (BROACH_DEPTH_M); när marginalen är under en meter
# föreslår han mer fart (rodren tar) eller djupare.
HEAVE_SHOW_M = 0.5             # så stort utslag visas på tavlan
HEAVE_SENSE_M = 0.05           # mindre utslag än så syns inte på djupmätaren
HEAVE_MARGIN_M = 1.0           # marginal till ytan som räcker
HEAVE_MAX_KN = 7               # fortare går inte med masten uppe
HEAVE_SAFE_DEPTH = 25
HEAVE_EVERY_S = 600


@dataclass(frozen=True)
class TrimNow(Order):
    pass


@dataclass(frozen=True)
class TrimHold(Order):
    STANDING = True


@dataclass(frozen=True)
class TrimReport(Order):
    pass


@dataclass(frozen=True)
class Hover(Order):
    STANDING = True


def quality_of(sigma: float) -> Quality:
    a, b, c = SIGMA_QUALITY
    return Quality.SAKER if sigma < a else Quality.GOD if sigma < b else \
        Quality.OSAKER if sigma < c else Quality.DALIG


def _heavy(w: float) -> str:
    return "tung" if w > 0 else "lätt"


def _tons(w: float) -> str:
    return f"{nm(abs(w))} ton"


def _pump_text(d: dict) -> str:
    parts = []
    if abs(d["ballast"]) >= 0.1:
        parts.append(f"pumpar {'ut' if d['ballast'] < 0 else 'in'} {_tons(d['ballast'])}")
    if abs(d["fore"]) >= 0.1:
        parts.append(f"flyttar {_tons(d['fore'])} {'förut' if d['fore'] > 0 else 'akterut'}")
    return " och ".join(parts) or "pumpar"


def _state(d: dict) -> str:
    w, q = d["weight"], Quality(d["quality"]).label
    txt = "Båten är i trim" if abs(w) < 0.3 else f"Båten är {_heavy(w)}, cirka {_tons(w)}"
    txt += f" (bedömningen {q})"
    p = d["pitch"]
    if abs(p) >= 0.5:
        txt += f", {nm(abs(p))} grader {'förlig' if p > 0 else 'akterlig'}"
    return txt


PHRASES = {
    "trim.report": lambda d: f"Trim: {_state(d)}. "
    + ("Pumparna går." if d["pumping"] else "Pumparna står.")
    + (" Kaptenen har stoppat trimningen." if d.get("hold") else ""),
    "trim.ack": lambda d: f"{ru('Jest')}, trimmar. {_pump_text(d).capitalize()}.",
    "trim.nothing": lambda d: f"Båten är i trim, kapten (bedömningen {Quality(d['quality']).label}). "
    "Inget att pumpa.",
    "trim.auto": lambda d: f"Kapten, trim. {_state(d)}. {_pump_text(d).capitalize()}.",
    "trim.danger": lambda d: f"Kapten, trim! Båten är {_heavy(d['weight'])}, cirka {_tons(d['weight'])}, "
    "rodren bär det inte i den här farten. " + _pump_text(d).capitalize() + ", pumparna hörs.",
    "trim.suggest": lambda d: f"Kapten, trim. {_state(d)}. Ber att få trimma, pumparna hörs.",
    "trim.hold": lambda d: f"{ru('Jest')}, pumparna stilla. Jag pumpar bara om båten blir farlig.",
    "trim.hover": lambda d: f"{ru('Jest')}, ligger still på {d['depth']:.0f} meter. "
    "Trimmar efter behov, pumparna går ibland.",
    "trim.hover.refused": lambda d: f"Kapten, trim. {_state(d)}. Vi kan inte ligga still förrän "
    "båten är trimmad. Ber att få trimma först.",
    "trim.hover.end": lambda d: "Ligger inte längre still, rodren håller djupet.",
    "trim.done": lambda d: "Båten är trimmad, pumparna stoppade.",
    "trim.heave": lambda d: f"Kapten, trim. Sjön suger oss mot ytan, på periskopdjup slår djupet "
    f"{nm(d['amp'])} meter. "
    "Tornet kan bryta ytan. "
    + (f"Föreslår fart {d['speed']}, då tar rodren." if d.get("speed") else
       f"Föreslår djup {d['depth']}, där suger det mindre."),
}
phrases.register(PHRASES)


def _ru_state(d: dict) -> str:
    w = d["weight"]
    if abs(w) < 0.3:
        txt = "Лодка удифферентована"
    else:
        txt = f"Лодка {'тяжёлая' if w > 0 else 'лёгкая'}, около {R.dec(abs(w), R.TON)}"
    txt += f", оценка {R.QUALITY_RU[d['quality']]}"
    if abs(d["pitch"]) >= 0.5:
        txt += f", дифферент {R.dec(abs(d['pitch']), R.DEGREE)} " + \
            ("на нос" if d["pitch"] > 0 else "на корму")
    return txt


def _ru_pump(d: dict) -> str:
    parts = []
    if abs(d["ballast"]) >= 0.1:
        parts.append(("откачиваем " if d["ballast"] < 0 else "принимаем ")
                     + R.dec(abs(d["ballast"]), R.TON))
    if abs(d["fore"]) >= 0.1:
        parts.append("перекачиваем " + R.dec(abs(d["fore"]), R.TON)
                     + (" в нос" if d["fore"] > 0 else " в корму"))
    return " и ".join(parts) or "откачиваем"


RU_PHRASES = {
    "trim.report": lambda d: f"{_ru_state(d)}. " + ("Насосы работают." if d["pumping"]
                                                   else "Насосы остановлены."),
    "trim.ack": lambda d: f"Есть, удифферентовываем: {_ru_pump(d)}.",
    "trim.nothing": lambda d: f"{R.CAPTAIN}, лодка удифферентована. Откачивать нечего.",
    "trim.auto": lambda d: f"{R.CAPTAIN}, трюмный. {_ru_state(d)}. {_ru_pump(d).capitalize()}.",
    "trim.danger": lambda d: f"{R.CAPTAIN}, трюмный! Лодка {'тяжёлая' if d['weight'] > 0 else 'лёгкая'}, "
    f"около {R.dec(abs(d['weight']), R.TON)}, рули не держат на этом ходу. "
    f"{_ru_pump(d).capitalize()}, насосы слышно.",
    "trim.suggest": lambda d: f"{R.CAPTAIN}, трюмный. {_ru_state(d)}. Прошу разрешения "
    "удифферентоваться, насосы слышно.",
    "trim.hold": lambda d: "Есть, насосы стоят. Откачиваем только при опасности.",
    "trim.hover": lambda d: f"Есть, стоим без хода на {R.count(d['depth'], R.METER)}. "
    "Удифферентовываемся по необходимости.",
    "trim.hover.refused": lambda d: f"{R.CAPTAIN}, трюмный. {_ru_state(d)}. Без хода стоять "
    "нельзя, пока лодка не удифферентована. Прошу удифферентоваться.",
    "trim.hover.end": lambda d: "Больше не стоим без хода, глубину держат рули.",
    "trim.done": lambda d: "Лодка удифферентована, насосы остановлены.",
    "trim.heave": lambda d: f"{R.CAPTAIN}, трюмный. Волна подсасывает лодку, глубина гуляет на "
    f"{R.dec(d['amp'], R.METER)}. Рубка может показаться. "
    + ("Предлагаю увеличить ход." if d.get("speed") else "Предлагаю уйти на глубину."),
}
phrases.register_ru(RU_PHRASES)


class TrimStation(Station):
    role = Role.TRIM
    COMMANDS = [
        CommandSpec(r"trimma|trimma båten|trimma baten", lambda m: TrimNow(), "trimma"),
        CommandSpec(r"trim stopp|stoppa trimmen|stoppa pumparna|inga pumpar",
                    lambda m: TrimHold(), "trim stopp"),
        CommandSpec(r"trim|trimrapport|trimläge|trimlage", lambda m: TrimReport(), "trim"),
        CommandSpec(r"ligg still|ligg stilla|hovra", lambda m: Hover(), "ligg still"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.rng = game.rng_for("trim")
        self.est = 0.0                  # bedömd överskottsvikt (ton, + tung)
        self.var = 0.1                  # trimmad vid start: nästan säker
        self.fore_est = 0.0
        self.hold = False               # kaptenen: inga pumpar (utom i fara)
        self._seen: tuple | None = None
        self._next = 0
        self._announced = False         # säg till när en trimning han sagt till om är klar
        self._was_pumping = False

    # --- bedömningen ----------------------------------------------------------------
    @property
    def sigma(self) -> float:
        return math.sqrt(max(self.var, 0.0))

    @property
    def quality(self) -> Quality:
        return quality_of(self.sigma)

    def _track(self) -> None:
        """Det trimmaren vet ändras: pumpat, skjutet, läckan, djupet."""
        own, t = self.own, self.own.sys.trim
        snap = (t.payload_t, t.ballast_t, own.sys.flooding, own.state.depth)
        if self._seen is not None:
            dp, db, dfl, dd = (a - b for a, b in zip(snap, self._seen))
            self.est += dp + db + dfl + T.COMPRESS_T_PER_100M * dd / 100.0
            self.var += (FLOOD_SIGMA * dfl) ** 2 + DEPTH_VAR_T2_PER_M * abs(dd) + AGE_VAR_T2_PER_S
        self._seen = snap

    def _measure(self) -> None:
        """Rodret och djupets drift: vikten med ett fel som växer med farten."""
        own, s, t = self.own, self.own.sys, self.own.sys.trim
        self.fore_est = t.fore_t + self.rng.gauss(0, FORE_SIGMA_T)
        if self._resting():
            return
        cap = T.plane_capacity(own.state.speed, s.health["planes"])
        sm = (MEASURE_BASE_T + MEASURE_PER_T * cap) * (1.6 - self.member.effective_skill())
        z = t.weight_t + self.rng.gauss(0, sm)
        k = self.var / (self.var + sm * sm)
        self.est += k * (z - self.est)
        self.var *= 1 - k

    def _resting(self) -> bool:
        own, s = self.own, self.own.sys
        surfacing = T.ballast_carries(own.state.depth, own.state.ordered_depth, own.state.speed,
                                      s.trim.changing)
        return own.surfaced or s.blowing or s.on_bottom or surfacing

    def _data(self) -> dict:
        t = self.own.sys.trim
        return {"weight": round(self.est, 1), "quality": int(self.quality),
                "pitch": round(t.pitch, 1), "pumping": t.pumping, "hold": self.hold,
                "depth": round(self.own.state.depth)}

    # --- att trimma -----------------------------------------------------------------
    def _plan(self) -> dict:
        return {"ballast": round(-self.est, 1), "fore": round(-self.fore_est, 1)}

    def _pump(self) -> dict:
        t = self.own.sys.trim
        plan = self._plan()
        ballast = plan["ballast"] if abs(self.est) >= 0.1 else 0.0
        fore = plan["fore"] if abs(self.fore_est) >= FORE_AT_T / 2 else 0.0
        t.pump(ballast_to=t.ballast_t + ballast if ballast else None,
               fore_to=t.fore_ballast_t + fore if fore else None)
        return {**self._data(), "ballast": ballast, "fore": fore}

    def _silent(self) -> bool:
        """Tyst gång: på smygmotorn hörs pumparna (bredvid turbinen inte)."""
        return self.own.sys.propulsion == "electric"

    def _danger(self) -> bool:
        cap = T.plane_capacity(self.own.state.speed, self.own.sys.health["planes"])
        return abs(self.est) > cap + T.CONTROL_LOST_T and self.sigma < abs(self.est)

    def _needs_trim(self) -> bool:
        at = HOVER_AT_T if self.own.sys.trim.hover else TRIM_AT_T
        heavy = abs(self.est) > at + self.sigma / 2 and self.sigma < abs(self.est)
        return heavy or abs(self.fore_est) > FORE_AT_T

    def _decide(self) -> None:
        t = self.own.sys.trim
        if self._resting() or t.pumping or not self._needs_trim():
            return
        danger = self._danger()
        if self.hold and not danger:
            return
        if danger:
            self.say("trim.danger", self._pump())
            self._announced = True
        elif t.hover or not self._silent():
            d = self._pump()
            if abs(d["ballast"]) >= REPORT_PUMP_T:
                self.say("trim.auto", d)
                self._announced = True
        elif not self._other_pending():
            self.suggest("trim", "trim.suggest", {**self._data(), **self._plan()},
                         order="trimma", cooldown=600, quality=self.quality)

    def _other_pending(self) -> bool:
        """Väntar ett annat förslag på kaptenens svar? Då väntar trimningen (den är sällan
        bråttom, och ett nytt förslag skulle ta platsen för det som väntar)."""
        active = self.game.active_suggestion()
        return (active is not None and active[0] != "trimma") or self.game.queue.has_kind("suggest")

    # --- order ----------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        t = self.own.sys.trim
        match order:
            case TrimNow():
                self.hold = False
                if self._resting() or not (abs(self.est) >= NOTHING_T or abs(self.fore_est) >= FORE_AT_T / 2):
                    self.say("trim.nothing", self._data(), kind="ack")
                else:
                    self.say("trim.ack", self._pump(), kind="ack")
                    self._announced = True
            case TrimHold():
                self.hold = True
                t.stop_pumps()
                self.say("trim.hold", kind="ack")
            case TrimReport():
                self.say("trim.report", self._data(), quality=self.quality)
            case Hover():
                if self.sigma > HOVER_MAX_SIGMA_T or abs(self.est) > 1.0:
                    self.suggest("hover_trim", "trim.hover.refused", self._data(),
                                 order="trimma", cooldown=60, quality=self.quality)
                    return
                t.hover = True
                self.hold = False
                self.own.state.order_speed(0)
                self.say("trim.hover", self._data(), kind="ack")
            case _ if t.hover and _moves(order):
                t.hover = False
                self.say("trim.hover.end", kind="info")

    # --- varje sekund ---------------------------------------------------------------
    def update(self) -> None:
        t = self.own.sys.trim
        was_pumping, self._was_pumping = self._was_pumping, t.pumping
        self._track()
        if self.now >= self._next:
            self._next = self.now + MEASURE_S
            self._measure()
            self._decide()
        if was_pumping and not t.pumping and self._announced:
            self._announced = False
            self.say("trim.done")
        self._heave_advice()

    def _heave_advice(self) -> None:
        """Djupmätaren slår (sjön suger): föreslå fart eller djup innan tornet bryter ytan.
        På väg upp räknar trimmaren om utslaget till det beordrade djupet (suget avtar med
        djupet på känt sätt), så att förslaget kommer innan vi är där."""
        own = self.own
        st, amp = own.state, own.heave_amp_m
        if amp <= HEAVE_SENSE_M or own.surfaced or st.ordered_depth > HEAVE_SAFE_DEPTH:
            return
        target = min(st.depth, st.ordered_depth)
        amp_t = amp * heave_depth_f(target) / heave_depth_f(st.depth)
        if target - amp_t - BROACH_DEPTH_M >= HEAVE_MARGIN_M:
            return
        now_f = heave_speed_f(st.speed)
        speed = next((v for v in range(max(int(st.speed) + 1, 3), HEAVE_MAX_KN + 1)
                      if target - amp_t * heave_speed_f(v) / now_f - BROACH_DEPTH_M >= HEAVE_MARGIN_M),
                     None)
        data = {"amp": amp_t, "speed": speed, "depth": HEAVE_SAFE_DEPTH}
        self.suggest("heave", "trim.heave", data,
                     order=f"fart {speed}" if speed else f"djup {HEAVE_SAFE_DEPTH}",
                     cooldown=HEAVE_EVERY_S, quality=Quality.GOD, alarm=True)

    def idle_proposals(self) -> list[Proposal]:
        t = self.own.sys.trim
        if self._resting() or t.pumping or self.hold or not self._needs_trim() or not self._silent():
            return []
        return [Proposal(3, "idle_trim", "trim.suggest", "trimma",
                         {**self._data(), **self._plan()}, cooldown=600, quality=self.quality)]

    # --- systemtavlan ---------------------------------------------------------------
    def system_items(self) -> list:
        own, t = self.own, self.own.sys.trim
        cap = T.plane_capacity(own.state.speed, own.sys.health["planes"])
        q = self.quality.label
        items: list = []
        g = lambda label, text, state=OK, level=None: \
            items.append(Gauge("TRIM", label, text, state, level))
        w = self.est
        if abs(w) < 0.3:
            txt = f"i trim ±{nm(self.sigma)} t ({q})"
        else:
            txt = f"{_heavy(w)} {nm(abs(w))} ±{nm(self.sigma)} t ({q})"
        g("Vikt", txt, WARN if abs(w) > cap + T.CONTROL_LOST_T and not self._resting() else
          INFO if abs(w) >= TRIM_AT_T else OK)
        p = t.pitch
        g("Lutning", "rak" if abs(p) < 0.5 else
          f"{nm(abs(p))}° {'förlig' if p > 0 else 'akterlig'}",
          WARN if abs(p) >= 5 else INFO if abs(p) >= 1 else OK)
        span = T.BALLAST_MAX_T - T.BALLAST_MIN_T
        g("Utjämningstank", f"{t.ballast_t - T.BALLAST_MIN_T:.0f} av {span:.0f} t",
          WARN if t.ballast_t <= T.BALLAST_MIN_T + 2 else OK,
          (t.ballast_t - T.BALLAST_MIN_T) / span)
        if t.pumping:
            g("Pumpar", "går, hörs" if self._silent() else "går", WARN if self._silent() else INFO)
        elif self.hold:
            g("Pumpar", "stoppade (kaptenen)", OFF)
        else:
            g("Pumpar", "stilla")
        if t.hover:
            g("Ligg still", f"på {own.state.depth:.0f} m", INFO)
        amp = own.heave_amp_m
        if amp >= HEAVE_SHOW_M:
            close = own.state.depth - amp - BROACH_DEPTH_M < HEAVE_MARGIN_M
            g("Sjön suger", f"djupet slår {nm(amp)} m" + (", tornet nära ytan" if close else ""),
              WARN if close else INFO)
        shift = t.fore_ballast_t / (2 * T.FORE_MAX_T)
        items.append(TrimTanks(fore=0.5 + shift, compensating=(t.ballast_t - T.BALLAST_MIN_T) / span,
                               aft=0.5 - shift, pitch=t.pitch))
        return items

    def status_fields(self) -> dict:
        """Lutningsmätaren och rodrets last (egna instrument) till centralens mätare."""
        t = self.own.sys.trim
        return {"pitch": t.pitch, "plane_load": t.plane_load}


def _moves(order: Order) -> bool:
    """Order som sätter fart på båten (då ligger vi inte längre still)."""
    from .navigation import SetSpeed
    return isinstance(order, SetSpeed) and order.speed > 0
