"""Passiv sonar: sonaroperatören är bryggan mellan sanning och kunskap.

Operatören "lyssnar" på världen (sanning) men lämnar bara ifrån sig brusiga
bäringar, upptäckter, klassificeringar och förluster. Aldrig avstånd.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .crew import CrewMember
from .geo import norm360
from .reports import Quality
from .tma import BearingObs
from .world import Vessel, World

OBS_INTERVAL = 5           # sekunder mellan loggade bäringar till plottet
LOSE_AFTER = 60            # sekunder utan hörbar signal innan kontakten förloras

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
class ClassificationUpdate:
    designation: str
    classification: str
    quality: Quality


SonarEvent = Detection | Lost | ClassificationUpdate | BearingObs


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

    def signal_excess(self, world: World, v: Vessel, t: _Tracking) -> float:
        """SE inkl. operatörens tröskel och långsam fluktuation."""
        return world.raw_signal_excess(v) - self.operator.detection_threshold() + t.fluct

    def bearing_sigma(self, se: float) -> float:
        return self.operator.bearing_sigma() * (1.0 + 1.5 / (1.0 + max(se, 0.0)))

    def update(self, world: World, own_xy: tuple[float, float]) -> list[SonarEvent]:
        events: list[SonarEvent] = []
        for v in world.contacts:
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
                    if t.designation is None:
                        t.designation = f"S-{self._next_number}"
                        self._next_number += 1
                    t.listening = 0.0
                    t.class_stage = 0
                    events.append(Detection(
                        designation=t.designation,
                        bearing=self._noisy_bearing(world, v, se),
                        classification=_CLASS_STAGES.get(v.kind, ["okänd kontakt"])[0],
                        quality=Quality.DALIG,
                    ))
                continue

            # kontakt hålls
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
                    events.append(BearingObs(
                        t=world.time,
                        bearing=self._noisy_bearing(world, v, se),
                        sigma=self.bearing_sigma(se),
                        own_x=own_xy[0],
                        own_y=own_xy[1],
                        own_course=world.own.state.course,
                        se=se,
                        designation=t.designation,
                    ))
        return events

    def _noisy_bearing(self, world: World, v: Vessel, se: float) -> float:
        return norm360(world.true_bearing(v) + self.rng.gauss(0.0, self.bearing_sigma(se)))

    def held_designations(self) -> list[str]:
        return [t.designation for t in self._tracks.values() if t.held and t.designation]
