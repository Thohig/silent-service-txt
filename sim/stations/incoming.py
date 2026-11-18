"""Torped i vattnet: sonarrummet följer en fientlig torped och föreslår undanmanöver.

Del av SonarRoom (sonar_room.py). Sonar ropar genast (larm) med bäringen och föreslår att gå
undan: skenmål, kurs bort från torpeden, högsta fart (turbin om reaktorn går) och ett annat djup
(`SonarRoom._evasive_target`). Därefter var `CALL_EVERY_S` bäringen och hur den drar: står den
still kommer torpeden rakt mot oss. Tystnar den sägs det. Bara det sonar hör: bäringar och
styrka, aldrig torpedens läge eller mål.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import phrases
from .. import russian as R
from ..events import HuntSigns, TorpedoInWater
from ..fmt import fmt_course, kn
from ..geo import angle_diff, norm360
from ..reports import Quality
from ..russian import ru
from ..sonar import IncomingTorpedo

CALL_EVERY_S = 20              # bäringen ropas så här ofta
STEADY_DEG_PER_MIN = 3.0       # så lite drar bäringen: kommer mot oss
DRIFT_WINDOW_S = 30


@dataclass
class _Heard:
    no: int
    bearings: list[tuple[int, float, float]] = field(default_factory=list)   # (t, bäring, se)
    last_call: int = -10**9


def _drift(h: _Heard, now: int) -> float | None:
    """Bäringens drift (grader per minut, + medurs) över de senaste sekunderna."""
    recent = [b for b in h.bearings if now - b[0] <= DRIFT_WINDOW_S]
    if len(recent) < 3 or recent[-1][0] - recent[0][0] < 10:
        return None
    dt = (recent[-1][0] - recent[0][0]) / 60.0
    return angle_diff(recent[-1][1], recent[0][1]) / dt


def _drift_text(d: dict) -> str:
    if d.get("steady"):
        return "Bäringen står still, den kommer mot oss!"
    if d.get("drift") is None:
        return ""
    side = "medurs" if d["drift"] > 0 else "moturs"
    return f"Bäringen drar {abs(d['drift']):.0f} grader i minuten {side}."


PHRASES = {
    "sonar.torpedo": lambda d: f"{ru('Torpeda')}! Torped i vattnet, bäring {fmt_course(d['bearing'])}!"
    + (" Höga varv, målsökande." if d.get("close") else ""),
    "sonar.torpedo.bearing": lambda d: f"Torpeden bäring {fmt_course(d['bearing'])}. {_drift_text(d)}",
    "sonar.torpedo.lost": lambda d: "Torpeden hörs inte längre"
    + (f", sista bäring {fmt_course(d['bearing'])}." if d.get("bearing") is not None else "."),
    "sonar.doors": lambda d: f"Kapten, sonar! Mekaniskt ljud i bäring {fmt_course(d['bearing'])}, "
    "luckor och vatten som fylls. De öppnar torpedrören!",
    "sonar.suggest.spoil": lambda d: f"Kapten! Föreslår kurs {fmt_course(d['course'])} och djup "
    f"{d['depth']:.0f}, så stämmer inte deras lösning när de skjuter.",
    "sonar.suggest.evade": lambda d: f"Kapten! Föreslår skenmål, kurs {fmt_course(d['course'])} "
    f"bort från torpeden, fart {kn(d['speed'])}"
    + (f" och djup {d['depth']:.0f}" if d.get("depth") is not None else "") + "!",
}
phrases.register(PHRASES)


def _ru_drift(d: dict) -> str:
    if d.get("steady"):
        return "Пеленг не меняется, идёт на нас!"
    if d.get("drift") is None:
        return ""
    return f"Пеленг смещается {R.count(abs(d['drift']), R.DEGREE)} в минуту " + \
        ("вправо." if d["drift"] > 0 else "влево.")


RU_PHRASES = {
    "sonar.torpedo": lambda d: f"Торпеда! Торпеда в воде, пеленг {R.course(d['bearing'])}!",
    "sonar.torpedo.bearing": lambda d: f"Торпеда, пеленг {R.course(d['bearing'])}. {_ru_drift(d)}",
    "sonar.torpedo.lost": lambda d: "Торпеду больше не слышно.",
    "sonar.doors": lambda d: f"{R.CAPTAIN}, акустик! Механический шум, пеленг {R.course(d['bearing'])}. "
    "Открывают торпедные аппараты!",
    "sonar.suggest.spoil": lambda d: f"{R.CAPTAIN}! Предлагаю курс {R.course(d['course'])}, глубина "
    f"{R.count(d['depth'], R.METER)}, чтобы сбить им решение.",
    "sonar.suggest.evade": lambda d: f"{R.CAPTAIN}! Предлагаю имитатор, курс {R.course(d['course'])} "
    f"от торпеды, ход {R.count(d['speed'], R.KNOT)}"
    + (f", глубина {R.count(d['depth'], R.METER)}" if d.get("depth") is not None else "") + "!",
}
phrases.register_ru(RU_PHRASES)


class IncomingMixin:
    """Del av SonarRoom: fientliga torpeder."""

    def _incoming_init(self) -> None:
        self._heard_torpedoes: dict[int, _Heard] = {}

    def _on_incoming(self, ev: IncomingTorpedo) -> None:
        bus = self.game.bus
        h = self._heard_torpedoes.setdefault(ev.no, _Heard(ev.no))
        if ev.kind == "lost":
            self.say("sonar.torpedo.lost", {"bearing": ev.bearing}, kind="contact")
            bus.publish(TorpedoInWater(self.now, ev.no, "lost", ev.bearing))
            return
        h.bearings.append((self.now, ev.bearing, ev.se))
        bus.publish(TorpedoInWater(self.now, ev.no, ev.kind, ev.bearing))
        bus.publish(HuntSigns(self.now, "torpedo"))
        if ev.kind == "new":
            h.last_call = self.now
            self.say("sonar.torpedo", {"bearing": ev.bearing, "close": ev.se > 20},
                     kind="contact", alarm=True)
            self._suggest_evasion(ev.bearing)
            return
        if self.now - h.last_call >= CALL_EVERY_S:
            h.last_call = self.now
            drift = _drift(h, self.now)
            steady = drift is not None and abs(drift) < STEADY_DEG_PER_MIN
            self.say("sonar.torpedo.bearing", {"bearing": ev.bearing, "drift": drift,
                                               "steady": steady},
                     kind="contact", alarm=steady,
                     quality=Quality.GOD if ev.se > 6 else Quality.OSAKER)
            if steady:
                self._suggest_evasion(ev.bearing, again=True)

    def _on_doors(self, bearing: float) -> None:
        """De öppnar torpedrören: byt kurs och djup innan de skjuter."""
        self.say("sonar.doors", {"bearing": bearing}, kind="contact", alarm=True)
        self.game.bus.publish(HuntSigns(self.now, "doors"))
        own = self.own
        rel = angle_diff(bearing, own.state.course)
        course = round(norm360(bearing + (-90 if rel > 0 else 90))) % 360    # tvärs, bort
        depth = self._evasive_target()
        if depth is None:
            return
        self.suggest("spoil", "sonar.suggest.spoil", {"course": course, "depth": depth},
                     order=f"kurs {course:03d}, djup {depth:.0f}", cooldown=120, alarm=True)

    def _suggest_evasion(self, bearing: float, again: bool = False) -> None:
        """Skenmål, bort från torpeden, högsta fart och ett annat djup, i en order."""
        own = self.own
        course = round(norm360(bearing + 180)) % 360
        parts = ["skenmål"] if not again else []
        parts.append(f"kurs {course:03d}")
        turbine = own.power and not own.sys.fire
        if turbine and own.sys.propulsion != "turbine":
            parts.append("turbin")
        if turbine:
            speed = int(min(28.0 * max(own.sys.health["propulsion"], 0.3),
                            16.0 if own.sys.steam_leak else 99.0))
        else:
            speed = int(own.max_speed())
        parts.append(f"fart {speed}")
        depth = self._evasive_target()
        if depth is not None:
            parts.append(f"djup {depth:.0f}")
        self.suggest("evade_torpedo" + ("_again" if again else ""), "sonar.suggest.evade",
                     {"course": course, "speed": speed, "depth": depth},
                     order=", ".join(parts), cooldown=60, alarm=True)
