"""Arktis (sanning): drivstationen Nord-7 och en amerikansk atomubåt under isen.

Drivstationen står på isen och driver med den. Dess dieselgenerator hörs
genom isen på några sjömil; dess ljus syns i periskopet på längre håll än
mörkret annars tillåter.

Den amerikanska ubåten är på väg mot samma område. Den lyssnar bättre än vi
(lägre egenbrus, bättre sonar) men går inte till anfall: insatsreglerna
1962 är att följa och dokumentera. Hör den oss skuggar den oss på ett par
sjömils avstånd. Hör den en torped väjer den.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import acoustics
from .entities import Vessel
from .geo import bearing_to, distance, norm360
from .ship import ShipState
from .weapons import Torpedo

if TYPE_CHECKING:
    from .world import World

STATION_LEVEL = 142.0           # dieselgeneratorn genom isen
STATION_LIGHT_NM = 2.5          # stationens ljus syns i periskopet så här långt
US_SUB_BASE = 125.0             # amerikansk atomubåt 1962: bas + 1,5·fart
US_SUB_DT = 0.0                 # bättre sonar än vår
US_DETECT_S = 30                # så länge den måste höra oss innan den vet
US_FORGET_S = 900
TRAIL_NM = 2.0


class DriftStation(Vessel):
    """Nord-7: baracker och master på en isflak. Driver med isen."""
    drifts_with_ice = True

    def __init__(self, id: str, x: float, y: float):
        super().__init__(id=id, kind="station", state=ShipState(x=x, y=y, course=0, speed=0,
                                                                depth=2.0), side="neutral")

    def radiated_level(self, env) -> float:
        return STATION_LEVEL


class EnemySub(Vessel):
    def __init__(self, id: str, state: ShipState):
        super().__init__(id=id, kind="submarine", state=state, side="enemy")

    def radiated_level(self, env) -> float:
        if self.sunk:
            return -999.0
        return US_SUB_BASE + 1.5 * max(self.state.speed, 0.0)


@dataclass
class SubDatum:
    x: float
    y: float
    depth: float
    sigma: float
    t: int


class SubmarineAI:
    """Amerikansk atomubåt: transit -> patrull vid stationen; skuggar oss om den hör oss."""
    can_force = False                    # kan inte tvinga oss till ytan

    def __init__(self, vessel: EnemySub, rng: random.Random, station: DriftStation):
        self.vessel = vessel
        self.rng = rng
        self.station = station
        self.state = "transit"
        self.roe = "observe"
        self.datum: SubDatum | None = None
        self._heard_for = 0
        self.evade_until = -1
        self.next_listen = 0
        self.next_turn = 0

    def aware(self) -> bool:
        return self.state == "trail"

    def _noise(self, world: World) -> float:
        s = self.vessel.state
        return acoustics.power_sum(world.env.noise_at(s.x, s.y), 48.0 + 1.0 * s.speed)

    def _tl(self, world: World, x: float, y: float, depth: float) -> float:
        s = self.vessel.state
        return acoustics.transmission_loss(distance(s.x, s.y, x, y), s.depth, depth, world.env) \
            + world.land_loss(s.x, s.y, x, y)

    # --- sensorer -------------------------------------------------------------------
    def _listen(self, world: World) -> None:
        own, now = world.own, world.time
        if own.sunk:
            return
        noise = self._noise(world)
        se = own.radiated_level(world.env) - self._tl(world, own.state.x, own.state.y,
                                                      own.depth) - noise - US_SUB_DT
        heard = se + self.rng.gauss(0, 2) > 0
        # transienter från oss: aktiv sonar, torpedutskjutning, nödblåsning
        for tr in world.transients:
            if tr.source_id != own.id:
                continue
            if tr.level - self._tl(world, tr.x, tr.y, tr.depth) - noise > 0:
                heard = True
                if tr.kind == "launch":
                    self.roe = "evade"
        self._heard_for = self._heard_for + 1 if heard else 0
        if heard and (self._heard_for >= US_DETECT_S or self.datum is not None):
            r = distance(self.vessel.state.x, self.vessel.state.y, own.state.x, own.state.y)
            err = 0.2 * r + 0.1
            self.datum = SubDatum(own.state.x + self.rng.gauss(0, err),
                                  own.state.y + self.rng.gauss(0, err), own.depth, err, now)
            if self.state != "trail":
                world.mission["us_sub_contact"] = world.mission.get("us_sub_contact", 0) + 1
            self.state = "trail"

    def _threats(self, world: World) -> None:
        s = self.vessel.state
        noise = self._noise(world)
        for t in world.contacts:
            if not isinstance(t, Torpedo) or t.done:
                continue
            se = t.radiated_level(world.env) - self._tl(world, t.state.x, t.state.y, t.depth) - noise
            if se > 0:
                self.evade_until = world.time + 240
                s.order_course(bearing_to(t.state.x, t.state.y, s.x, s.y))
                s.order_speed(25)

    # --- beslut -----------------------------------------------------------------------
    def step(self, world: World) -> None:
        if self.vessel.sunk:
            return
        now, s = world.time, self.vessel.state
        if now >= self.next_listen:
            self.next_listen = now + 5
            self._listen(world)
        self._threats(world)
        if now < self.evade_until:
            return
        if self.datum is not None and now - self.datum.t > US_FORGET_S:
            self.datum = None
            self.state = "patrol"
        st = self.station.state
        if self.state == "trail" and self.datum is not None:
            d = self.datum
            r = distance(s.x, s.y, d.x, d.y)
            b = bearing_to(s.x, s.y, d.x, d.y)
            if r > TRAIL_NM + 0.5:
                s.order_course(b)
                s.order_speed(10)
            elif r < TRAIL_NM - 0.5:
                s.order_course(norm360(b + 180))
                s.order_speed(4)
            else:
                s.order_course(norm360(b + 60))      # håll avståndet, gå på sidan
                s.order_speed(5)
            return
        r = distance(s.x, s.y, st.x, st.y)
        if self.state == "transit" and r < 1.5:
            self.state = "patrol"
        if self.state == "transit":
            s.order_course(bearing_to(s.x, s.y, st.x, st.y))
            s.order_speed(8)
            return
        # patrull runt stationen, långsamt och tyst
        s.order_speed(4)
        if r > 2.0:
            s.order_course(bearing_to(s.x, s.y, st.x, st.y))
        elif now >= self.next_turn:
            self.next_turn = now + 600
            s.order_course(norm360(bearing_to(st.x, st.y, s.x, s.y) + 90))
