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
from .geo import bearing_to, norm360
from .reports import Quality
from .tma import BearingObs
from .entities import Vessel
from .world import World

OBS_INTERVAL = 5           # sekunder mellan loggade bäringar till plottet
LOSE_AFTER = 120           # sekunder utan hörbar signal innan kontakten förloras

# Klassificeringsstadier per typ: (ackumulerad lyssning, text)
_CLASS_STAGES = {
    "destroyer": ["okänd kontakt", "ytfartyg", "ytfartyg, tvåskruv, trolig jagare",
                  "jagare, ångturbiner, två axlar"],
    "merchant": ["okänd kontakt", "ytfartyg", "ytfartyg, enskruv, trolig handelsfartyg",
                 "handelsfartyg, diesel, en axel"],
    "submarine": ["okänd kontakt", "möjlig undervattenskontakt", "trolig ubåt",
                  "ubåt, atomdriven"],
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


@dataclass
class ClassificationUpdate:
    designation: str
    classification: str
    quality: Quality


SonarEvent = Detection | Lost | ClassificationUpdate | BearingObs | TransientHeard


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
class SonarStation:
    operator: CrewMember
    rng: random.Random
    _tracks: dict[str, _Tracking] = field(default_factory=dict)
    _next_number: int = 1

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
        for v in world.contacts:
            if v.side == "own":
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

    def _transients(self, world: World, own_xy) -> list[SonarEvent]:
        out: list[SonarEvent] = []
        noise = acoustics.power_sum(world.env.background_noise, world.own.self_noise())
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
            out.append(TransientHeard(tr.kind, norm360(true_b + self.rng.gauss(0, sig)), se,
                                      desig if track and track.held else None, tr.practice))
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
