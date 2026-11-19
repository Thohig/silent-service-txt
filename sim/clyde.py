"""Firth of Clyde (sanning): Polarisbåten som går ut ur Holy Loch, fiskebåtarna och färjan.

Polarisbåten (`TransitAI`) ligger vid depåfartyget i Holy Loch tills `depart_t`, går sedan ut
i ytläge längs farleden (västra rännan förbi Cumbraeöarna, ned mellan Arran och Ayrshire) och
förbi Pladda ut ur kortet. Den letar inte efter oss och kan inte tvinga upp oss.

Fiskebåtarna (`FishingAI`) trålar sakta fram och tillbaka i sina områden: brus som skymmer och
kölar att akta sig för, inget mer. Färjan Wemyss Bay–Rothesay går bara på kvällen
(`ClydeTraffic`). Lotsen (`pilotage.py`) håller alla från land.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from .entities import Vessel
from .geo import bearing_to, distance
from .traffic import TrafficGenerator

if TYPE_CHECKING:
    from .world import World

WAYPOINT_NM = 0.25           # så nära en brytpunkt: nästa
LOCH_SPEED_KN = 5.0          # i Holy Loch och förbi Dunoon
TRANSIT_SPEED_KN = 10.0      # sedan ned genom firthen
LOCH_LEGS = 2                # så många brytpunkter går den i låg fart
FISH_SPEED_KN = (3.0, 4.5)
FISH_LEG_NM = (1.0, 2.5)

# Polarisbåtens väg från Holy Loch till havet (nm, kortets koordinater)
POLARIS_ROUTE = ((21.3, 32.4), (22.2, 30.6), (20.7, 27.2), (19.4, 23.0), (18.8, 19.4),
                 (18.0, 15.0), (17.4, 8.0), (16.6, 0.0), (16.0, -6.0))


class TransitAI:
    """Ett fartyg som väntar och sedan går en fast väg (Polarisbåten)."""
    can_force = False
    datum = None
    roe = "-"

    def __init__(self, vessel: Vessel, route: tuple[tuple[float, float], ...], depart_t: int,
                 speed: float = TRANSIT_SPEED_KN, slow_legs: int = LOCH_LEGS,
                 slow_speed: float = LOCH_SPEED_KN):
        self.vessel = vessel
        self.route = list(route)
        self.depart_t = depart_t
        self.speed = speed
        self.slow_legs = slow_legs
        self.slow_speed = slow_speed
        self.state = "waiting"
        self.passed = 0

    def aware(self) -> bool:
        return False

    def step(self, world: World) -> None:
        v, s = self.vessel, self.vessel.state
        if v.sunk:
            return
        if self.state == "waiting":
            if world.time < self.depart_t:
                return
            self.state = "transit"
        if self.route:
            wx, wy = self.route[0]
            if distance(s.x, s.y, wx, wy) < WAYPOINT_NM:
                self.route.pop(0)
                self.passed += 1
                if not self.route:
                    self.state = "gone"
                    return
                wx, wy = self.route[0]
            s.order_course(bearing_to(s.x, s.y, wx, wy))
        s.order_speed(self.slow_speed if self.passed < self.slow_legs else self.speed)


class FishingAI:
    """En fiskebåt som trålar fram och tillbaka i sitt område (x0, y0, x1, y1)."""
    can_force = False
    datum = None
    roe = "-"

    def __init__(self, vessel: Vessel, rng: random.Random, box: tuple[float, float, float, float],
                 depth_ok):
        self.vessel = vessel
        self.rng = rng
        self.box = box
        self.depth_ok = depth_ok             # (x, y) -> bool: vatten nog att tråla
        self.target: tuple[float, float] | None = None
        self.speed = rng.uniform(*FISH_SPEED_KN)

    def aware(self) -> bool:
        return False

    def _next(self) -> tuple[float, float]:
        s = self.vessel.state
        x0, y0, x1, y1 = self.box
        for _ in range(20):
            d = self.rng.uniform(*FISH_LEG_NM)
            b = self.rng.uniform(0, 360)
            x = min(max(s.x + d * math.sin(math.radians(b)), x0), x1)
            y = min(max(s.y + d * math.cos(math.radians(b)), y0), y1)
            if self.depth_ok(x, y):
                return x, y
        return (x0 + x1) / 2, (y0 + y1) / 2

    def step(self, world: World) -> None:
        s = self.vessel.state
        if self.vessel.sunk:
            return
        if self.target is None or distance(s.x, s.y, *self.target) < WAYPOINT_NM:
            self.target = self._next()
        s.order_course(bearing_to(s.x, s.y, *self.target))
        s.order_speed(self.speed)


class ClydeTraffic(TrafficGenerator):
    """Trafiken i firthen: leder som slutar gå vid en viss tid (färjan på kvällen)."""

    def __init__(self, tdef, rng: random.Random, until: dict[int, int]):
        super().__init__(tdef, rng)
        self.until = until                  # led -> simtid då den slutar gå

    def step(self, world: World) -> None:
        for k, t in self.until.items():
            if world.time >= t:
                self.next_t[k] = 10**9
        super().step(world)
