"""Passiv sonar: sonaroperatören är bryggan mellan sanning och kunskap.

Operatören "lyssnar" på världen (sanning) men lämnar bara ifrån sig brusiga
bäringar, upptäckter, klassificeringar, förluster och hörda transienter
(pingar, plask, detonationer, undervattenstelefon). Aldrig avstånd.

Sensorn håller också reda på beteckningar (S-1, S-2 …), så att periskop,
radar och aktiv sonar kan knyta sina observationer till samma kontakt.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .crew import CrewMember
from . import acoustics
from .geo import angle_diff, bearing_to, norm360
from .reports import Quality
from .tma import BearingObs
from .entities import Vessel
from .world import World

OBS_INTERVAL = 5           # sekunder mellan loggade bäringar till plottet
LOSE_AFTER = 120           # sekunder utan hörbar signal innan kontakten förloras
OWN_LOSE_AFTER = 60        # egen torped: sekunder tyst innan operatören tappar den
OWN_TURN_DEG = 20.0        # så mycket måste en egen torped svänga för att det ska höras
OWN_END_WAIT = 2           # sekunder att vänta på detonation när en torped tystnar

# Klassificeringsstadier per typ: (ackumulerad lyssning, text)
_CLASS_STAGES = {
    "destroyer": ["okänd kontakt", "ytfartyg", "ytfartyg, tvåskruv, trolig jagare",
                  "jagare, ångturbiner, två axlar"],
    "merchant": ["okänd kontakt", "ytfartyg", "ytfartyg, enskruv, trolig handelsfartyg",
                 "handelsfartyg, diesel, en axel"],
    "guardship": ["okänd kontakt", "ytfartyg", "ytfartyg, tvåskruv, trolig bevakningsfartyg",
                  "bevakningsfartyg, ångturbiner, två axlar"],
    "patrol": ["okänd kontakt", "ytfartyg", "ytfartyg, tvåskruv, snabbgående, trolig patrullbåt",
               "patrullbåt, diesel, två axlar"],
    "transport": ["okänd kontakt", "ytfartyg", "ytfartyg, stort, två axlar, långsamt varvtal",
                  "stort fartyg, ångturbiner, två axlar, trolig trupptransport"],
    "tanker": ["okänd kontakt", "ytfartyg", "ytfartyg, stort, enskruv, tungt lastat",
               "tankfartyg, ångturbin, en axel"],
    "moored": ["okänd kontakt", "svagt maskinbuller, stillaliggande",
               "hjälpmaskiner, troligen fartyg till ankars", "fartyg till ankars, hjälpmaskiner"],
    "submarine": ["okänd kontakt", "möjlig undervattenskontakt", "trolig ubåt",
                  "ubåt, atomdriven"],
    "station": ["okänd kontakt", "maskinbuller, stillaliggande", "dieselgenerator, trolig drivstation",
                "dieselgenerator, drivstation på isen"],
    "ice": ["okänd kontakt", "bredbandigt brus, ingen tydlig maskin", "trolig isskruvning",
            "isljud, ingen maskin"],
}
_CLASS_THRESHOLDS = [0.0, 40.0, 250.0, 900.0]


@dataclass
class Detection:
    designation: str
    bearing: float
    classification: str
    quality: Quality


@dataclass
class Lost:
    designation: str


@dataclass
class TransientHeard:
    kind: str                 # ping, splash, explosion, uwt, breakup, launch, echosounder
    bearing: float
    se: float
    designation: str | None   # om källan är en känd kontakt
    practice: bool = False
    own_weapon: bool = False  # ljudet kom från en egen torped


@dataclass
class OwnTorpedo:
    """Operatören följer en egen torped.

    no är ordningsnumret i avfyrningsordning (1, 2, …). Torpedrummet räknar
    sina avfyringar på samma sätt och knyter numret till en tub.
    kind: running (bäring), turned (har svängt), lost (hörs inte längre),
    detonated (detonation från torpeden), silent (tystnade utan detonation).
    """
    no: int
    kind: str
    bearing: float | None
    se: float = 0.0


@dataclass
class ClassificationUpdate:
    designation: str
    classification: str
    quality: Quality


SonarEvent = Detection | Lost | ClassificationUpdate | BearingObs | TransientHeard | OwnTorpedo


@dataclass
class _Tracking:
    """Operatörens inre minne per ljudkälla (dolt för resten av spelet)."""
    audible_for: int = 0
    silent_for: int = 0
    designation: str | None = None
    held: bool = False
    listening: float = 0.0
    class_stage: int = 0
    fluct: float = 0.0
    last_obs_t: int = -10**9


@dataclass
class _OwnTrack:
    """Operatörens minne av en egen torped."""
    no: int
    launch_course: float
    held: bool = True
    silent_for: int = 0
    last_obs_t: int = -10**9
    last_bearing: float | None = None
    turned: bool = False
    done_t: int | None = None
    ended: bool = False


@dataclass
class SonarStation:
    operator: CrewMember
    rng: random.Random
    _tracks: dict[str, _Tracking] = field(default_factory=dict)
    _next_number: int = 1
    _own: dict[str, _OwnTrack] = field(default_factory=dict)
    _own_count: int = 0
    background: float = 0.0       # senast hörda bakgrundsbrus, dB
    under_ice: bool = False       # bruset kommer från isen

    def threshold(self, world: World) -> float:
        """Operatörens tröskel, sämre om sonaren är skadad."""
        return self.operator.detection_threshold() + (1.0 - world.own.sys.health["sonar"]) * 15.0

    def signal_excess(self, world: World, v: Vessel, t: _Tracking) -> float:
        """SE inkl. operatörens tröskel och långsam fluktuation."""
        return world.raw_signal_excess(v) - self.threshold(world) + t.fluct

    def bearing_sigma(self, se: float) -> float:
        return self.operator.bearing_sigma() * (1.0 + 1.5 / (1.0 + max(se, 0.0)))

    def designate(self, vessel_id: str) -> str:
        """Ge (eller hämta) beteckning för en ljudkälla."""
        t = self._tracks.setdefault(vessel_id, _Tracking())
        if t.designation is None:
            t.designation = f"S-{self._next_number}"
            self._next_number += 1
        return t.designation

    def designation_of(self, vessel_id: str) -> str | None:
        t = self._tracks.get(vessel_id)
        return t.designation if t else None

    def update(self, world: World, own_xy: tuple[float, float]) -> list[SonarEvent]:
        events: list[SonarEvent] = []
        # Bakgrundsbruset operatören hör i lurarna (havet eller isen).
        self.background = world.background_at_own()
        self.under_ice = world.env.ice is not None
        for v in world.contacts:
            if v.side == "own":
                if v.kind == "torpedo":
                    events += self._own_torpedo(world, v)
                continue
            t = self._tracks.setdefault(v.id, _Tracking())
            t.fluct = 0.95 * t.fluct + self.rng.gauss(0.0, 0.5)
            se = self.signal_excess(world, v, t)
            audible = se > 0.0

            if audible:
                t.audible_for += 1
                t.silent_for = 0
            else:
                t.silent_for += 1
                t.audible_for = 0

            if not t.held:
                if t.audible_for >= self.operator.detection_time():
                    t.held = True
                    first = t.designation is None
                    self.designate(v.id)
                    if first:
                        t.listening = 0.0
                        t.class_stage = 0
                    events.append(Detection(
                        designation=t.designation,
                        bearing=self._noisy_bearing(world, v, se),
                        classification=_CLASS_STAGES.get(v.kind, ["okänd kontakt"])[t.class_stage],
                        quality=Quality(t.class_stage),
                    ))
                continue

            if t.silent_for >= LOSE_AFTER:
                t.held = False
                events.append(Lost(t.designation))
                continue

            if audible:
                t.listening += se * self.operator.effective_skill()
                stages = _CLASS_STAGES.get(v.kind, ["okänd kontakt"])
                new_stage = max(i for i, th in enumerate(_CLASS_THRESHOLDS[: len(stages)])
                                if t.listening >= th)
                if new_stage > t.class_stage:
                    t.class_stage = new_stage
                    events.append(ClassificationUpdate(
                        t.designation, stages[new_stage], Quality(new_stage)))

                if world.time - t.last_obs_t >= OBS_INTERVAL:
                    t.last_obs_t = world.time
                    events.append(self._obs(world, v, se, own_xy, t.designation))

        events += self._transients(world, own_xy)
        return events

    def _obs(self, world: World, v: Vessel, se: float, own_xy, designation: str,
             sigma: float | None = None, source: str = "sonar") -> BearingObs:
        sig = self.bearing_sigma(se) if sigma is None else sigma
        return BearingObs(
            t=world.time,
            bearing=norm360(world.true_bearing(v) + self.rng.gauss(0.0, sig)),
            sigma=sig, own_x=own_xy[0], own_y=own_xy[1],
            own_course=world.own.state.course, se=se, designation=designation, source=source)

    def _own_torpedo(self, world: World, v: Vessel) -> list[SonarEvent]:
        """Följ en egen torped: bäring, sväng, tappad och tystnad."""
        tr = self._own.get(v.id)
        if tr is None:
            self._own_count += 1
            tr = self._own[v.id] = _OwnTrack(self._own_count, v.state.course)
        if tr.ended:
            return []
        if getattr(v, "done", False):
            # Torpeden har slutat gå. En detonation hörs nästa tick (_transients);
            # hörs ingen tystnade den utan att detonera.
            if tr.done_t is None:
                tr.done_t = world.time
            elif world.time - tr.done_t >= OWN_END_WAIT:
                tr.ended = True
                if tr.held:
                    return [OwnTorpedo(tr.no, "silent", tr.last_bearing)]
            return []
        out: list[SonarEvent] = []
        se = world.raw_signal_excess(v) - self.threshold(world)
        if se > 0:
            tr.silent_for = 0
            tr.held = True
            if world.time - tr.last_obs_t >= OBS_INTERVAL:
                tr.last_obs_t = world.time
                tr.last_bearing = self._noisy_bearing(world, v, se)
                out.append(OwnTorpedo(tr.no, "running", tr.last_bearing, se))
            if not tr.turned and abs(angle_diff(v.state.course, tr.launch_course)) > OWN_TURN_DEG:
                tr.turned = True
                tr.last_bearing = self._noisy_bearing(world, v, se)
                out.append(OwnTorpedo(tr.no, "turned", tr.last_bearing, se))
        else:
            tr.silent_for += 1
            if tr.held and tr.silent_for >= OWN_LOSE_AFTER:
                tr.held = False
                out.append(OwnTorpedo(tr.no, "lost", tr.last_bearing))
        return out

    def _transients(self, world: World, own_xy) -> list[SonarEvent]:
        out: list[SonarEvent] = []
        noise = acoustics.power_sum(world.background_at_own(), world.own.self_noise())
        dt = self.threshold(world)
        o = world.own.state
        for tr in world.transients:
            if tr.source_id == world.own.id:
                continue
            se = tr.level - world.tl_to_own(tr.x, tr.y, tr.depth) - noise - dt
            if se <= 0:
                continue
            true_b = bearing_to(o.x, o.y, tr.x, tr.y)
            sig = self.bearing_sigma(se)
            desig = self.designation_of(tr.source_id)
            track = self._tracks.get(tr.source_id)
            heard_b = norm360(true_b + self.rng.gauss(0, sig))
            own_t = self._own.get(tr.source_id)
            if own_t is not None and tr.kind == "explosion" and not own_t.ended:
                own_t.ended = True
                out.append(OwnTorpedo(own_t.no, "detonated", heard_b, se))
            out.append(TransientHeard(tr.kind, heard_b, se,
                                      desig if track and track.held else None, tr.practice,
                                      own_weapon=own_t is not None))
            # en ping ger en skarp bäring på en känd kontakt
            if tr.kind == "ping" and track is not None and track.held and desig:
                src = next((v for v in world.contacts if v.id == tr.source_id), None)
                if src is not None:
                    out.append(self._obs(world, src, se, own_xy, desig,
                                         sigma=self.operator.bearing_sigma() * 0.5, source="ping"))
        return out

    def _noisy_bearing(self, world: World, v: Vessel, se: float) -> float:
        return norm360(world.true_bearing(v) + self.rng.gauss(0.0, self.bearing_sigma(se)))

    def held_designations(self) -> list[str]:
        return [t.designation for t in self._tracks.values() if t.held and t.designation]
