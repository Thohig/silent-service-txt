"""Övningsmål (sanning): ett eget bevakningsfartyg som går raka ben i övningsområdet.

Fartyget är sovjetiskt och vänligt (`side="neutral"`: sänks det slutar spelet). Det
söker inte efter ubåten och kan inte tvinga upp den; det går ben på 2,5–4,5 nm mellan
slumpade punkter inom området, så att plottet får raka ben att räkna på och en gir då
och då. Bara sensorerna läser var det är.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from .entities import Vessel
from .geo import bearing_to, distance
from .ship import ShipState

if TYPE_CHECKING:
    from .world import World

ARRIVE_NM = 0.2             # framme vid benets slut: nytt ben
STEER_S = 15                # ny kurs mot benets slut så här ofta


class ExerciseShipAI:
    """Bevakningsfartyget: raka ben inom radius nm från center."""
    can_force = False
    datum = None
    roe = "övning"

    def __init__(self, vessel: Vessel, rng: random.Random, center: tuple[float, float],
                 radius: float, speed: tuple[float, float] = (9.0, 12.0),
                 leg_nm: tuple[float, float] = (2.5, 4.5)):
        self.vessel = vessel
        self.rng = rng
        self.center = center
        self.radius = radius
        self.speed = speed
        self.leg_nm = leg_nm
        self.state = "övning"
        self.target = self._next_point()
        vessel.state.order_speed(rng.uniform(*speed))

    def aware(self) -> bool:
        return False

    def _next_point(self) -> tuple[float, float]:
        s, rng = self.vessel.state, self.rng
        cx, cy = self.center
        best = (cx, cy)
        for _ in range(40):
            a = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(*self.leg_nm)
            x, y = s.x + d * math.sin(a), s.y + d * math.cos(a)
            if distance(x, y, cx, cy) <= self.radius:
                return (x, y)
        return best

    def step(self, world: World) -> None:
        v, s = self.vessel, self.vessel.state
        if v.sunk:
            return
        if distance(s.x, s.y, *self.target) < ARRIVE_NM:
            self.target = self._next_point()
            s.order_speed(self.rng.uniform(*self.speed))
        if world.time % STEER_S == 0:
            s.order_course(bearing_to(s.x, s.y, *self.target))


def make_exercise_ship(rng: random.Random, center: tuple[float, float], radius: float,
                       vid: str = "SKR1") -> tuple[Vessel, ExerciseShipAI]:
    a = rng.uniform(0, 2 * math.pi)
    r = radius * math.sqrt(rng.random())
    x, y = center[0] + r * math.sin(a), center[1] + r * math.cos(a)
    v = Vessel(vid, "guardship",
               ShipState(x=x, y=y, course=rng.uniform(0, 360), speed=10.0, turn_rate=2.0,
                         accel=0.1, max_speed=24),
               side="neutral", has_radar=False)   # radarn tyst under övningen
    return v, ExerciseShipAI(v, random.Random(rng.random()), center, radius)


UK_RANGE_NM = 5.0           # undervattenstelefonen når så här långt
REPORT_POS_SIGMA_NM = 0.1   # partnerns egen navigering


def partner_report(world: World, rng: random.Random, vid: str = "SKR1") -> dict | None:
    """Undervattenstelefonen (en sensor): partnern meddelar kurs, fart och läge enligt sin
    egen navigering. None om den är utom räckhåll, sänkt eller inte finns."""
    v = next((c for c in world.contacts if c.id == vid and not c.sunk), None)
    if v is None or world.true_range(v) > UK_RANGE_NM:
        return None
    s = v.state
    return {"course": round(s.course / 5) * 5 % 360, "speed": round(s.speed),
            "x": s.x + rng.gauss(0, REPORT_POS_SIGMA_NM), "y": s.y + rng.gauss(0, REPORT_POS_SIGMA_NM)}


def torpedo_report(world: World, vid: str = "SKR1") -> dict | None:
    """Undervattenstelefonen: partnerns utkik om senaste övningstorpeden.
    hit = passerade under skrovet; miss_m = närmaste passage i meter. None om ingen
    övningstorped avfyrats eller partnern är utom räckhåll."""
    from .weapons import Torpedo
    v = next((c for c in world.contacts if c.id == vid and not c.sunk), None)
    if v is None or world.true_range(v) > UK_RANGE_NM:
        return None
    runs = [c for c in world.contacts if isinstance(c, Torpedo) and c.spec.exercise]
    if not runs:
        return None
    t = runs[-1]
    d = t.passed.get(vid, 9.9)
    return {"hit": t.under.get(vid, 9.9) <= 1.0, "miss_m": round(d * 1852 / 10) * 10, "seen": d < 0.5}
