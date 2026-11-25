"""Fiskeflottan (sanning): trålare på bankerna och en sovjetisk spaningstrålare. docs/system/hav.md, Fisket.

Varje fiskebåt (`clyde.FishingAI`) drar en trål: vajern går från aktern snett ned till trålen
`TRAWL_ASTERN_NM` akterut på `TRAWL_DEPTH_M` (en bottentrål på grunt vatten går nära botten). Går vi in i vajern
eller trålen fastnar vi (`Trawler.step`): propellern far illa, fiskebåten bromsas och fiskaren ropar på radion,
så att jagarna i närheten får ett ungefärligt läge (`TRAWL_ALARM_NM`, `TRAWL_ALARM_SIGMA_NM`). Fart framåt i en
stund sliter vajern (`TRAWL_BREAK_S`).

På natten lyser fiskebåtarna (`LIGHTS_NM`: periskopet och bryggan ser dem långt bortom nattsikten, inte i dimma).
Spaningstrålaren (`spytrawler`, sovjetisk, neutral för torpedrummet) skuggas en stund i taget av de amerikanska
jagarna (`DestroyerAI.shadow`).
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from .clyde import FishingAI
from .entities import Transient, Vessel
from .geo import distance
from .ship import ShipState

if TYPE_CHECKING:
    from .world import World

TRAWL_ASTERN_NM = 0.25          # trålen går så långt akterom båten …
TRAWL_DEPTH_M = 60.0            # … på så här djupt (bottentrål: botten − 5 m om det är grundare)
TRAWL_MOUTH_M = 12.0            # trålöppningens höjd
TRAWL_HALF_WIDTH_M = 30.0       # vajrarna och trålen i sidled
TRAWL_DAMAGE = 0.15             # framdrivningen (propellern fångad)
TRAWL_SOUND_LEVEL = 145.0       # vajern som sliter i skrovet och vinschen som rusar
TRAWL_ALARM_NM = 12.0           # fiskaren ropar på radion: jagare inom så långt får ett läge
TRAWL_ALARM_SIGMA_NM = 0.5
TRAWL_BREAK_S = 30              # så länge med fart framåt (≥ TRAWL_BREAK_KN) innan vajern slits
TRAWL_BREAK_KN = 3.0
LIGHTS_NM = 6.0                 # fiskelamporna syns så långt på natten
SHADOW_NM = 1.0                 # jagaren håller sig så nära spaningstrålaren den skuggar


class Trawler(FishingAI):
    """En fiskebåt som trålar (FishingAI) med sin trål akterut."""

    def __init__(self, vessel: Vessel, rng: random.Random, box, depth_ok):
        super().__init__(vessel, rng, box, depth_ok)
        self.snagged_t: int | None = None
        self._pull_s = 0

    def trawl(self, world: World) -> tuple[float, float, float]:
        """Trålens läge (x, y) och djup."""
        s = self.vessel.state
        c = math.radians(s.course)
        x, y = s.x - TRAWL_ASTERN_NM * math.sin(c), s.y - TRAWL_ASTERN_NM * math.cos(c)
        depth = TRAWL_DEPTH_M
        if world.env.seabed is not None:
            depth = min(depth, world.env.seabed.depth_at(x, y) - 5.0)
        return x, y, max(depth, 5.0)

    def _fouls(self, world: World) -> bool:
        """Går vår ubåt genom vajern eller trålen? (vajern rak från aktern ned till trålen)"""
        own, s = world.own, self.vessel.state
        o = own.state
        tx, ty, td = self.trawl(world)
        dx, dy = tx - s.x, ty - s.y
        L2 = dx * dx + dy * dy
        f = max(0.0, min(1.0, ((o.x - s.x) * dx + (o.y - s.y) * dy) / L2)) if L2 > 0 else 0.0
        px, py = s.x + f * dx, s.y + f * dy
        if distance(o.x, o.y, px, py) * 1852.0 > TRAWL_HALF_WIDTH_M + 50.0:   # vår halva längd
            return False
        wire_depth = f * td                         # vajern sjunker längs vägen ned till trålen
        keel = max(o.depth, 7.0)
        top = keel - 13.0                           # tornets topp
        if f >= 0.95:
            return top < td + TRAWL_MOUTH_M and keel > td
        return top < wire_depth < keel

    def step(self, world: World) -> None:
        if self.vessel.sunk:
            return
        own = world.own
        s = self.vessel.state
        if self.snagged_t is not None:
            # fast: fiskebåten bromsas, vi drar den; fart framåt sliter till slut vajern
            s.order_speed(0.0)
            if own.state.speed >= TRAWL_BREAK_KN and not own.state.astern:
                self._pull_s += 1
            if self._pull_s >= TRAWL_BREAK_S or own.sunk:
                self.snagged_t = None
                self._pull_s = 0
                own.alert("trawl.free")
            return
        super().step(world)
        if not own.sunk and not own.surfaced and self._fouls(world):
            self.snagged_t = world.time
            sys = own.sys
            sys.health["propulsion"] = max(0.0, sys.health["propulsion"] - TRAWL_DAMAGE)
            o = own.state
            o.speed = min(o.speed, 2.0)
            world.emit(Transient("trawl", o.x, o.y, o.depth, TRAWL_SOUND_LEVEL, own.id, world.time))
            own.alert("trawl.caught")
            for ai in world.ais:                    # fiskaren ropar på radion
                v = getattr(ai, "vessel", None)
                if v is None or v.side != "enemy" or not hasattr(ai, "_set_datum") or \
                        distance(v.state.x, v.state.y, s.x, s.y) > TRAWL_ALARM_NM:
                    continue
                ai._set_datum(world, o.x + ai.rng.gauss(0, TRAWL_ALARM_SIGMA_NM),
                              o.y + ai.rng.gauss(0, TRAWL_ALARM_SIGMA_NM), o.depth, TRAWL_ALARM_SIGMA_NM)


def add_fleet(world: World, seed: float, n: int, box: tuple[float, float, float, float], depth_ok,
              spy: bool = False) -> list[Vessel]:
    """Lägg ut n trålare i rutan (och en sovjetisk spaningstrålare). Egen slump ur seed: flottan flyttar inte
    resten av scenariots dragningar."""
    rng = random.Random(seed)
    out = []
    for i in range(n + (1 if spy else 0)):
        for _ in range(30):
            fx, fy = rng.uniform(box[0], box[2]), rng.uniform(box[1], box[3])
            if depth_ok(fx, fy):
                break
        is_spy = spy and i == n
        v = Vessel(f"AGI{i}" if is_spy else f"FV{i + 1}", "spytrawler" if is_spy else "fishing",
                   ShipState(x=fx, y=fy, course=rng.uniform(0, 360), speed=3.5, turn_rate=3.0, accel=0.2,
                             max_speed=10),
                   side="neutral")
        world.contacts.append(v)
        world.ais.append(Trawler(v, random.Random(rng.random()), box, depth_ok))
        out.append(v)
    return out


def lit_at_night(v: Vessel, r: float, day: bool, fog: float | None) -> bool:
    """Syns fartyget på sina lampor (fiskelampor på natten, inte i dimma)?"""
    return v.kind in ("fishing", "spytrawler") and not day and fog is None and r <= LIGHTS_NM
