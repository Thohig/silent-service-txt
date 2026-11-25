"""En sovjetisk ubåt i området (sanning): en Foxtrot (Projekt 641), som B-36 vid Kuba i oktober 1962.

Den smyger på batteriet på djupet (`DEPTH_M`, `CREEP_KN`) i sitt område och går var `SNORT_EVERY_S` upp och
snorklar med dieslarna en stund (`SNORT_S`, `SNORT_DEPTH_M`): då hörs den långt. Staben meddelar ungefär var
den är (scenariot lägger det i ett radiogram), och sonar klassar den först som en ubåt med diesel, som lika
gärna kan vara amerikansk; säkert klassad känner sonarmannen igen sin egen klass (sovjetisk, Projekt 641), och
då är den vänlig för plottet. Sänker vi den är det ett neutralt fartyg (det avslutar patrullen).
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

DEPTH_M = 100.0
SNORT_DEPTH_M = 10.0
CREEP_KN = 3.0
SNORT_KN = 6.0
SNORT_EVERY_S = (80 * 60, 120 * 60)
SNORT_S = (30 * 60, 50 * 60)
LEG_NM = (2.0, 4.0)
BATTERY_DB = 106.0              # på batteriet: tyst
SNORT_DB = 140.0                # dieslarna och snorkeln: hörs långt
DB_PER_KN = 1.2


class Foxtrot(Vessel):
    """Projekt 641: tre axlar, diesel-elektrisk."""

    def __init__(self, id: str, x: float, y: float, course: float):
        super().__init__(id=id, kind="foxtrot",
                         state=ShipState(x=x, y=y, course=course, speed=CREEP_KN, depth=DEPTH_M,
                                         turn_rate=2.0, accel=0.1, max_speed=16, max_depth=280),
                         side="neutral")
        self.state.ordered_speed, self.state.ordered_depth = CREEP_KN, DEPTH_M
        self.snorting = False

    def radiated_level(self, env) -> float:
        if self.sunk:
            return -999.0
        base = SNORT_DB if self.snorting and self.state.depth <= SNORT_DEPTH_M + 3 else BATTERY_DB
        return base + DB_PER_KN * self.state.speed


class FoxtrotAI:
    can_force = False
    roe = "-"
    datum = None

    def __init__(self, boat: Foxtrot, rng: random.Random, box: tuple[float, float, float, float], now: int = 0):
        self.vessel = boat
        self.rng = rng
        self.box = box
        self.target: tuple[float, float] | None = None
        self.next_snort = now + rng.randint(*SNORT_EVERY_S) // 2
        self.snort_until = -1

    def aware(self) -> bool:
        return False

    def _leg(self) -> tuple[float, float]:
        s = self.vessel.state
        x0, y0, x1, y1 = self.box
        b = self.rng.uniform(0, 360)
        d = self.rng.uniform(*LEG_NM)
        return (min(max(s.x + d * math.sin(math.radians(b)), x0), x1),
                min(max(s.y + d * math.cos(math.radians(b)), y0), y1))

    def step(self, world: World) -> None:
        v, s, now = self.vessel, self.vessel.state, world.time
        if v.sunk:
            return
        if not v.snorting and now >= self.next_snort:
            v.snorting = True
            self.snort_until = now + self.rng.randint(*SNORT_S)
        elif v.snorting and now >= self.snort_until:
            v.snorting = False
            self.next_snort = now + self.rng.randint(*SNORT_EVERY_S)
        s.order_depth(SNORT_DEPTH_M if v.snorting else DEPTH_M)
        s.order_speed(SNORT_KN if v.snorting else CREEP_KN)
        if self.target is None or distance(s.x, s.y, *self.target) < 0.2:
            self.target = self._leg()
        s.order_course(bearing_to(s.x, s.y, *self.target))


def add_foxtrot(world: World, seed: str, box: tuple[float, float, float, float]) -> Foxtrot:
    """Lägg ut ubåten i rutan (egen slump: flyttar inte scenariots övriga dragningar)."""
    rng = random.Random(seed)
    x0, y0, x1, y1 = box
    boat = Foxtrot("B36", rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(0, 360))
    world.contacts.append(boat)
    world.ais.append(FoxtrotAI(boat, random.Random(rng.random()), box))
    return boat
