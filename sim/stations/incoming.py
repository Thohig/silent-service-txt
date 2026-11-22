"""Torped i vattnet: sonarrummet följer en fientlig torped och föreslår undanmanöver.

Del av SonarRoom (sonar_room.py). Sonar ropar genast (larm) med bäringen och föreslår att gå
undan. Hörs torpeden svagt (långt bort): skenmål, kurs bort, högsta fart (turbin om reaktorn går)
och ett annat djup (`SonarRoom._evasive_target`). Hörs den starkt (`CLOSE_SE`, nära): för nära
för att springa ifrån, och fart låter mer än skenmålet; då skenmål, smygmotor, tvärs och nytt djup. Därefter var `CALL_EVERY_S` bäringen och hur den drar: står den
still kommer torpeden rakt mot oss. Tystnar den sägs det. Bara det sonar hör: bäringar och
styrka, aldrig torpedens läge eller mål.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import phrases
from .. import russian as R
from ..events import HuntSigns, TorpedoInWater
from ..fmt import fmt_course, kn
from ..geo import angle_diff, norm360
from ..reports import Quality
from ..russian import ru
from ..ownship import TEST_DEPTH
from ..sonar import IncomingTorpedo
from ..sonar_view import KEEP_S as WATERFALL_KEEP_S, TorpedoTrace

CALL_EVERY_S = 20              # bäringen ropas så här ofta
DEPTH_JUMP_M = 80              # så långt från vårt djup: ut ur torpedens höjdband
CLOSE_SE = 8.0                 # så starkt hörs en torped som är nära (~2,5–3 nm under isen):
                               # för nära att springa ifrån, skenmål och tyst tvärs i stället
STEADY_DEG_PER_MIN = 3.0       # så lite drar bäringen: kommer mot oss
DRIFT_WINDOW_S = 30
# Nedräkningen: nivån stiger med 20·log(1/r) när torpeden närmar sig, så tiden till den är framme
# är ETA_K / (nivåns ökning i dB/s), oberoende av farten (sfärisk spridning).
ETA_K = 20.0 / 2.302585        # ≈ 8,7 dB
ETA_WINDOW_S = 40              # nivåerna så här långt bakåt
ETA_MIN_POINTS = 5
LEVEL_READ_SIGMA = 0.7         # operatörens avläsning av nivån (dB)
ETA_QUALITY = ((0.10, Quality.SAKER), (0.25, Quality.GOD), (0.50, Quality.OSAKER))
ETA_MODEL_REL = 0.20           # modellfelet: torpeden går inte rakt mot oss, spridningen är inte sfärisk
ETA_FAR_S = 120                # längre bort än så: torpeden söker och girar, högst osäker
ETA_MAX_S = 240                # längre än så sägs ingen tid
COUNTDOWN_UNDER_S = 90         # så nära: ropa var COUNTDOWN_EVERY_S i stället för var CALL_EVERY_S
COUNTDOWN_EVERY_S = 10


@dataclass
class _Heard:
    no: int
    bearings: list[tuple[int, float, float]] = field(default_factory=list)   # (t, bäring, se)
    levels: list[tuple[int, float]] = field(default_factory=list)            # (t, avläst nivå)
    last_call: int = -10**9
    eta: tuple[int, Quality] | None = None     # senast sagda tid kvar (s) och kvaliteten
    lost: bool = False                          # hörs inte längre


def _drift(h: _Heard, now: int) -> float | None:
    """Bäringens drift (grader per minut, + medurs) över de senaste sekunderna."""
    recent = [b for b in h.bearings if now - b[0] <= DRIFT_WINDOW_S]
    if len(recent) < 3 or recent[-1][0] - recent[0][0] < 10:
        return None
    dt = (recent[-1][0] - recent[0][0]) / 60.0
    return angle_diff(recent[-1][1], recent[0][1]) / dt


def eta_estimate(levels: list[tuple[int, float]], now: int) -> tuple[float, Quality] | None:
    """Tid tills torpeden är framme ur hur fort nivån stiger (minsta kvadrat över fönstret),
    med kvalitet ur lutningens osäkerhet. None om den inte stiger tydligt."""
    pts = [(t, lv) for t, lv in levels if now - t <= ETA_WINDOW_S]
    if len(pts) < ETA_MIN_POINTS or pts[-1][0] - pts[0][0] < 15:
        return None
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    ml = sum(lv for _, lv in pts) / n
    stt = sum((t - mt) ** 2 for t, _ in pts)
    slope = sum((t - mt) * (lv - ml) for t, lv in pts) / stt
    if slope <= 0:
        return None
    res = sum((lv - ml - slope * (t - mt)) ** 2 for t, lv in pts) / max(1, n - 2)
    sigma = (res / stt) ** 0.5
    rel = math.hypot(sigma / slope, ETA_MODEL_REL)
    q = next((q for lim, q in ETA_QUALITY if rel < lim), None)
    eta = ETA_K / slope - (now - mt)
    if q is None or eta > ETA_MAX_S:
        return None
    if eta > ETA_FAR_S:
        q = min(q, Quality.OSAKER)
    return max(0.0, eta), q


def _eta_text(d: dict) -> str:
    if d.get("eta") is None:
        return ""
    s = d["eta"]
    if s < 60:
        return f" Framme om cirka {s} sekunder."
    m, r = divmod(s, 60)
    return f" Framme om cirka {m} minut{'er' if m > 1 else ''}" + (f" {r}." if r else ".")


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
    "sonar.torpedo.bearing": lambda d: f"Torpeden bäring {fmt_course(d['bearing'])}. {_drift_text(d)}"
    + _eta_text(d),
    "sonar.torpedo.lost": lambda d: "Torpeden hörs inte längre"
    + (f", sista bäring {fmt_course(d['bearing'])}." if d.get("bearing") is not None else "."),
    "sonar.doors": lambda d: f"Kapten, sonar! Mekaniskt ljud i bäring {fmt_course(d['bearing'])}, "
    "luckor och vatten som fylls. De öppnar torpedrören!",
    "sonar.suggest.spoil": lambda d: f"Kapten! Föreslår kurs {fmt_course(d['course'])} och djup "
    f"{d['depth']:.0f}, så stämmer inte deras lösning när de skjuter.",
    "sonar.suggest.evade_quiet": lambda d: f"Kapten! Den är nära. Föreslår skenmål, smygmotor och "
    f"kurs {fmt_course(d['course'])} tvärs"
    + (f", djup {d['depth']:.0f}" if d.get("depth") is not None else "") + ". Låt den ta skenmålet!",
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
    "sonar.torpedo.bearing": lambda d: f"Торпеда, пеленг {R.course(d['bearing'])}. {_ru_drift(d)}"
    + (f" Подход через {R.mmss(d['eta'])}." if d.get("eta") is not None else ""),
    "sonar.torpedo.lost": lambda d: "Торпеду больше не слышно.",
    "sonar.doors": lambda d: f"{R.CAPTAIN}, акустик! Механический шум, пеленг {R.course(d['bearing'])}. "
    "Открывают торпедные аппараты!",
    "sonar.suggest.spoil": lambda d: f"{R.CAPTAIN}! Предлагаю курс {R.course(d['course'])}, глубина "
    f"{R.count(d['depth'], R.METER)}, чтобы сбить им решение.",
    "sonar.suggest.evade_quiet": lambda d: f"{R.CAPTAIN}! Она близко. Предлагаю имитатор, "
    f"электромотор, курс {R.course(d['course'])} на траверз"
    + (f", глубина {R.count(d['depth'], R.METER)}" if d.get("depth") is not None else "") + ".",
    "sonar.suggest.evade": lambda d: f"{R.CAPTAIN}! Предлагаю имитатор, курс {R.course(d['course'])} "
    f"от торпеды, ход {R.count(d['speed'], R.KNOT)}"
    + (f", глубина {R.count(d['depth'], R.METER)}" if d.get("depth") is not None else "") + "!",
}
phrases.register_ru(RU_PHRASES)


class IncomingMixin:
    """Del av SonarRoom: fientliga torpeder."""

    def _incoming_init(self) -> None:
        self._heard_torpedoes: dict[int, _Heard] = {}
        self._dodge_depth: float | None = None    # djupet vi går till, så länge torpeden går

    def torpedo_traces(self) -> list:
        """Vattenfallet: de fientliga torpedernas bäringar (`torped 1` …), den senaste timmen."""
        cutoff = self.now - WATERFALL_KEEP_S
        out = []
        for h in self._heard_torpedoes.values():
            pts = tuple(b for b in h.bearings if b[0] >= cutoff)
            if pts:
                out.append(TorpedoTrace(f"torped {h.no}", pts, hostile=True, held=not h.lost))
        return out

    def _on_incoming(self, ev: IncomingTorpedo) -> None:
        bus = self.game.bus
        h = self._heard_torpedoes.setdefault(ev.no, _Heard(ev.no))
        if ev.kind == "lost":
            h.lost = True
            self.say("sonar.torpedo.lost", {"bearing": ev.bearing}, kind="contact")
            bus.publish(TorpedoInWater(self.now, ev.no, "lost", ev.bearing))
            return
        h.bearings.append((self.now, ev.bearing, ev.se))
        h.lost = False
        if ev.level is not None:
            h.levels.append((self.now, ev.level + self.game.rng_for("incoming").gauss(0, LEVEL_READ_SIGMA)))
        bus.publish(TorpedoInWater(self.now, ev.no, ev.kind, ev.bearing))
        bus.publish(HuntSigns(self.now, "torpedo"))
        if ev.kind != "new" and not self._loudest(ev):
            return                          # en närmare torped styr undanmanövern
        if ev.kind == "new":
            h.last_call = self.now
            # torpeden söker där vi var när den sköts: ett djup långt därifrån (varje ny torped)
            self._dodge_depth = self._torpedo_depth()
            self.say("sonar.torpedo", {"bearing": ev.bearing, "close": ev.se > 20},
                     kind="contact", alarm=True)
            self._suggest_evasion(ev.bearing, close=ev.se > CLOSE_SE)
            return
        every = COUNTDOWN_EVERY_S if h.eta is not None and \
            h.eta[0] - (self.now - h.last_call) < COUNTDOWN_UNDER_S else CALL_EVERY_S
        if self.now - h.last_call >= every:
            h.last_call = self.now
            drift = _drift(h, self.now)
            steady = drift is not None and abs(drift) < STEADY_DEG_PER_MIN
            d = {"bearing": ev.bearing, "drift": drift, "steady": steady}
            quality = Quality.GOD if ev.se > 6 else Quality.OSAKER
            est = eta_estimate(h.levels, self.now) if steady else None
            h.eta = None
            if est is not None:
                eta, q = est
                step = 5 if eta < 60 else 10
                d["eta"] = int(round(eta / step) * step)
                h.eta = (d["eta"], q)
                quality = min(quality, q)
            self.say("sonar.torpedo.bearing", d, kind="contact", alarm=steady, quality=quality)
            if steady and not self._evasion_pending():
                self._suggest_evasion(ev.bearing, again=True, close=ev.se > CLOSE_SE)

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

    def _suggest_evasion(self, bearing: float, again: bool = False, close: bool = False) -> None:
        """Skenmål, bort från torpeden, högsta fart och ett annat djup, i en order. Nära: skenmål,
        smygmotor, tvärs och nytt djup (springa hinner vi inte, och farten låter mer än skenmålet)."""
        own = self.own
        if close:
            rel = angle_diff(bearing, own.state.course)
            course = round(norm360(bearing + (-90 if rel > 0 else 90))) % 360
            parts = ([] if again else ["skenmål"]) + [f"kurs {course:03d}"]
            if own.sys.propulsion != "electric":
                parts.append("smygmotor")
            parts.append("fart 4")
            depth = self._dodge_depth
            if depth is not None:
                parts.append(f"djup {depth:.0f}")
            self.suggest("evade_torpedo" + ("_again" if again else ""), "sonar.suggest.evade_quiet",
                         {"course": course, "depth": depth}, order=", ".join(parts),
                         cooldown=60, alarm=True)
            return
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
        depth = self._dodge_depth
        if depth is not None:
            parts.append(f"djup {depth:.0f}")
        self.suggest("evade_torpedo" + ("_again" if again else ""), "sonar.suggest.evade",
                     {"course": course, "speed": speed, "depth": depth},
                     order=", ".join(parts), cooldown=60, alarm=True)

    def _loudest(self, ev: IncomingTorpedo) -> bool:
        """Hörs ingen annan torped starkare just nu? Den närmaste styr förslagen."""
        for k, x in self._heard_torpedoes.items():
            if k != ev.no and x.bearings and self.now - x.bearings[-1][0] <= 10 \
                    and x.bearings[-1][2] > ev.se:
                return False
        return True

    def _evasion_pending(self) -> bool:
        """Väntar ett förslag om undanmanöver fortfarande på svar? Då ersätts det inte."""
        active = self.game.active_suggestion()
        return active is not None and active[0].startswith(("skenmål", "kurs"))

    def _torpedo_depth(self) -> float | None:
        """Ett djup långt från där vi är nu (torpeden söker på vårt djup när den sköts):
        nedåt om det finns plats under provdjupet och botten, annars uppåt."""
        st = self.own.state
        if self.own.sys.settle or self.own.sys.on_bottom:
            return None
        lim = min(TEST_DEPTH - 20, self._depth_limit() or TEST_DEPTH)
        if st.depth + DEPTH_JUMP_M <= lim:
            return round(st.depth + DEPTH_JUMP_M)
        up = st.depth - DEPTH_JUMP_M
        floor = self._ceiling_limit()
        return round(up) if up >= floor else None

    def _ceiling_limit(self) -> float:
        """Grundast vi vill gå: under isens kölar, annars under periskopdjup."""
        from .navigation import NavigationStation
        from .navigation.common import SAFE_ICE_DEPTH
        try:
            under_ice = self.game.station(NavigationStation).under_ice()   # isekolodet
        except KeyError:
            under_ice = False
        return SAFE_ICE_DEPTH if under_ice else 40.0

