"""Fartygsdynamik: kurs, fart och djup ändras gradvis mot beordrade värden."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .geo import angle_diff, norm360, velocity


@dataclass
class ShipState:
    x: float
    y: float
    course: float
    speed: float
    depth: float = 0.0
    ordered_course: float | None = None
    ordered_speed: float | None = None
    ordered_depth: float | None = None
    turn_rate: float = 1.0      # grader per sekund
    accel: float = 0.05         # knop per sekund
    depth_rate: float = 1.0     # meter per sekund
    max_speed: float = 28.0
    max_depth: float = 300.0
    # back i maskin (bara egen ubåt beordrar det): farten är alltid farten genom vattnet (≥ 0),
    # astern säger att båten går akterut. Maskinen slår om via stopp.
    astern: bool = False
    ordered_astern: bool = False
    brake_accel: float | None = None    # inbromsning när maskinen går mot farten (None = accel)
    astern_turn: float = 1.0            # girförmåga akterut, andel av turn_rate

    def __post_init__(self) -> None:
        self.course = norm360(self.course)
        if self.ordered_course is None:
            self.ordered_course = self.course
        if self.ordered_speed is None:
            self.ordered_speed = self.speed
        if self.ordered_depth is None:
            self.ordered_depth = self.depth

    # --- order -------------------------------------------------------------
    def order_course(self, course: float) -> None:
        self.ordered_course = norm360(course)

    def order_speed(self, speed: float, astern: bool = False) -> None:
        self.ordered_speed = min(max(speed, 0.0), self.max_speed)
        self.ordered_astern = astern and self.ordered_speed > 0

    def halt(self) -> None:
        """Stannar tvärt (grundstötning, is, nät): ingen fart och ingen order om fart."""
        self.speed = self.ordered_speed = 0.0
        self.astern = self.ordered_astern = False

    @property
    def track(self) -> float:
        """Riktningen båten rör sig genom vattnet: kursen, eller rakt akterut vid back."""
        return norm360(self.course + 180.0) if self.astern else self.course

    @property
    def prop_astern(self) -> bool:
        """Propellern går akterut (back, eller maskinen slår om mot fart framåt)."""
        return self.ordered_astern if self.reversing else self.astern

    @property
    def reversing(self) -> bool:
        """Maskinen går mot farten (slår om): båten bromsar mot stopp."""
        return self.speed > 0 and self.astern != self.ordered_astern

    def order_depth(self, depth: float) -> None:
        self.ordered_depth = min(max(depth, 0.0), self.max_depth)

    # --- dynamik -----------------------------------------------------------
    def step(self, dt: float = 1.0) -> None:
        d = angle_diff(self.ordered_course, self.course)
        max_turn = self.turn_rate * (self.astern_turn if self.astern else 1.0) * dt
        if abs(d) <= max_turn:
            self.course = self.ordered_course
        else:
            self.course = norm360(self.course + math.copysign(max_turn, d))

        if self.reversing:
            # maskinen mot farten: bromsa till stopp, sedan åt andra hållet
            brake = self.accel if self.brake_accel is None else self.brake_accel
            self.speed = _approach(self.speed, 0.0, brake * dt)
        else:
            if self.speed == 0:
                self.astern = self.ordered_astern
            self.speed = _approach(self.speed, self.ordered_speed, self.accel * dt)
        if self.speed == 0:
            self.astern = self.ordered_astern
        self.depth = _approach(self.depth, self.ordered_depth, self.depth_rate * dt)

        vx, vy = velocity(self.track, self.speed)
        self.x += vx * dt
        self.y += vy * dt

    def changing(self) -> set[str]:
        """Vilka storheter som fortfarande är på väg mot beordrat värde."""
        out: set[str] = set()
        if self.course != self.ordered_course:
            out.add("course")
        if self.speed != self.ordered_speed or self.astern != self.ordered_astern:
            out.add("speed")
        if self.depth != self.ordered_depth:
            out.add("depth")
        return out


def _approach(value: float, target: float, max_step: float) -> float:
    if abs(target - value) <= max_step:
        return target
    return value + math.copysign(max_step, target - value)
