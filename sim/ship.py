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

    def order_speed(self, speed: float) -> None:
        self.ordered_speed = min(max(speed, 0.0), self.max_speed)

    def order_depth(self, depth: float) -> None:
        self.ordered_depth = min(max(depth, 0.0), self.max_depth)

    # --- dynamik -----------------------------------------------------------
    def step(self, dt: float = 1.0) -> None:
        d = angle_diff(self.ordered_course, self.course)
        max_turn = self.turn_rate * dt
        if abs(d) <= max_turn:
            self.course = self.ordered_course
        else:
            self.course = norm360(self.course + math.copysign(max_turn, d))

        self.speed = _approach(self.speed, self.ordered_speed, self.accel * dt)
        self.depth = _approach(self.depth, self.ordered_depth, self.depth_rate * dt)

        vx, vy = velocity(self.course, self.speed)
        self.x += vx * dt
        self.y += vy * dt

    def changing(self) -> set[str]:
        """Vilka storheter som fortfarande är på väg mot beordrat värde."""
        out: set[str] = set()
        if self.course != self.ordered_course:
            out.add("course")
        if self.speed != self.ordered_speed:
            out.add("speed")
        if self.depth != self.ordered_depth:
            out.add("depth")
        return out


def _approach(value: float, target: float, max_step: float) -> float:
    if abs(target - value) <= max_step:
        return target
    return value + math.copysign(max_step, target - value)
