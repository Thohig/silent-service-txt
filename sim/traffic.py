"""Civil trafik (sanning): handelsfartyg längs leder genom operationsområdet.

Scenariot beskriver trafiken med en `TrafficDef` (leder, hur ofta fartyg
kommer, fart). `TrafficGenerator` lägger ut några fartyg från start och
skickar sedan in nya med slumpade mellanrum (Poisson). Varje fartyg får en
`MerchantAI` i `world.ais`.

Handelsfartygen är neutrala (`side="neutral"`): de hörs som vilka fartyg som
helst, deras brus kan dölja ubåten för jagaren (se `World.masking_noise`),
och en målsökande torped kan låsa på dem. Sovjetiska fraktfartyg på väg mot
Kuba stoppar när en jagare kommer nära och vänder sedan hem.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .entities import Transient, Vessel
from .geo import bearing_to, distance
from .ship import ShipState

if TYPE_CHECKING:
    from .world import World

VIA_ARRIVE_NM = 0.08        # en brytpunkt (grind) passeras så här nära
ARRIVE_NM = 0.5             # framme vid ledens slut: gå vidare rakt fram
STOP_NM = 3.0               # sovjetiskt fraktfartyg stoppar när en jagare är så nära
STOP_S = (15 * 60, 35 * 60) # så länge det ligger stilla innan det vänder hem
FOGHORN_EVERY_S = 120       # en lång signal i dimma högst varannan minut
FOGHORN_LEVEL = 150.0       # dB i vattnet (luren låter genom skrovet och ytan)
MIN_START_RANGE_NM = 3.0    # lägg inte ut fartyg ovanpå ubåten från start


@dataclass(frozen=True)
class Lane:
    """En led: fartygen går från start mot end med lite spridning i sidled."""
    name: str
    start: tuple[float, float]
    end: tuple[float, float]
    per_hour: float
    speed: tuple[float, float] = (9.0, 14.0)
    soviet: float = 0.0          # andel sovjetiska fraktfartyg (stoppar vid karantänlinjen)
    moor: bool = False           # ankrar vid ledens slut (in i en hamn) i stället för att gå vidare
    via: tuple[tuple[float, float], ...] = ()   # brytpunkter före slutet, t.ex. en grind


@dataclass(frozen=True)
class TrafficDef:
    lanes: tuple[Lane, ...]
    initial: int = 2             # fartyg på väg genom området när scenariot börjar
    width_nm: float = 1.5        # ledens bredd (spridning i sidled, 1σ)


class MerchantAI:
    """Ett handelsfartyg: följer sin led; ett sovjetiskt stoppar för jagaren och vänder."""
    can_force = False            # kan inte tvinga upp ubåten
    datum = None
    roe = "-"

    def __init__(self, vessel: Vessel, rng: random.Random, target: tuple[float, float],
                 home: tuple[float, float], soviet: bool, speed: float, moor: bool = False,
                 via: tuple[tuple[float, float], ...] = ()):
        self.vessel = vessel
        self.rng = rng
        self.target = target
        self.home = home
        self.soviet = soviet
        self.speed = speed
        self.moor = moor
        self.via = list(via)
        self.state = "transit"
        self.resume_t = 0

    def aware(self) -> bool:
        return False

    @property
    def _horn_phase(self) -> int:
        """Var i varvet mistluren ljuder (ur id:t, ingen slump: fartygen tutar inte i takt)."""
        return sum(map(ord, self.vessel.id)) % FOGHORN_EVERY_S

    def step(self, world: World) -> None:
        v, s = self.vessel, self.vessel.state
        if v.sunk or self.state == "moored":
            return
        if world.env.fog_vis() is not None and (world.time + self._horn_phase) % FOGHORN_EVERY_S == 0:
            # i dimma: en lång signal med mistluren (sjövägsreglerna), hörs i vattnet
            world.emit(Transient("foghorn", s.x, s.y, 0.0, FOGHORN_LEVEL, v.id, world.time))
        if self.state == "stopped":
            if world.time >= self.resume_t:
                self.state = "homeward"
                self.target = self.home
                s.order_speed(self.speed)
            return
        if self.soviet and self.state == "transit" and any(
                distance(s.x, s.y, e.state.x, e.state.y) < STOP_NM
                for e in world.enemy_ships if e.kind == "destroyer" and not e.sunk):
            self.state = "stopped"
            self.resume_t = world.time + self.rng.randint(*STOP_S)
            s.order_speed(0)
            return
        if self.via:
            vx, vy = self.via[0]
            if distance(s.x, s.y, vx, vy) < VIA_ARRIVE_NM:
                self.via.pop(0)
            elif world.time % 15 == 0:
                s.order_course(bearing_to(s.x, s.y, vx, vy))
            return
        if self.target is not None:
            tx, ty = self.target
            if distance(s.x, s.y, tx, ty) < ARRIVE_NM:
                self.target = None          # rakt fram ut ur området
                if self.moor:
                    self.state = "moored"   # till ankars i hamnen
                    s.order_speed(0)
                    s.speed = 0.0
                    v.kind = "moored"
            elif world.time % 60 == 0:
                s.order_course(bearing_to(s.x, s.y, tx, ty))


class TrafficGenerator:
    def __init__(self, tdef: TrafficDef, rng: random.Random):
        self.tdef = tdef
        self.rng = rng
        self.count = 0
        self.next_t = [self._gap(lane) for lane in tdef.lanes]

    def _gap(self, lane: Lane) -> int:
        return int(self.rng.expovariate(lane.per_hour) * 3600) if lane.per_hour > 0 else 10**9

    def populate(self, world: World) -> None:
        """Fartyg som redan är på väg genom området när scenariot börjar."""
        o = world.own.state
        placed = tries = 0
        while placed < self.tdef.initial and tries < 50:
            tries += 1
            lane = self.rng.choice(self.tdef.lanes)
            f = self.rng.uniform(0.15, 0.85)
            v = self._spawn(world, lane, f)
            if distance(v.state.x, v.state.y, o.x, o.y) < MIN_START_RANGE_NM:
                world.contacts.remove(v)
                world.ais.pop()
                self.count -= 1
                continue
            placed += 1

    def step(self, world: World) -> None:
        for i, lane in enumerate(self.tdef.lanes):
            if world.time >= self.next_t[i]:
                self._spawn(world, lane, 0.0)
                self.next_t[i] = world.time + max(60, self._gap(lane))

    def _spawn(self, world: World, lane: Lane, f: float) -> Vessel:
        """Ett nytt fartyg andelen f in längs leden."""
        rng = self.rng
        (x0, y0), (x1, y1) = lane.start, lane.end
        L = distance(x0, y0, x1, y1)
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L          # normal i sidled
        off = rng.gauss(0, self.tdef.width_nm)
        x, y = x0 + (x1 - x0) * f + nx * off, y0 + (y1 - y0) * f + ny * off
        tx, ty = x1 + nx * off, y1 + ny * off
        speed = rng.uniform(*lane.speed)
        self.count += 1
        v = Vessel(f"H{self.count}", "merchant",
                   ShipState(x=x, y=y, course=bearing_to(x, y, tx, ty), speed=speed,
                             turn_rate=0.5, accel=0.03, max_speed=16),
                   side="neutral")
        soviet = rng.random() < lane.soviet
        world.contacts.append(v)
        world.ais.append(MerchantAI(v, random.Random(rng.random()), (tx, ty),
                                    (x0 + nx * off, y0 + ny * off), soviet, speed,
                                    moor=lane.moor,
                                    via=tuple(p for p in lane.via
                                              if (p[1] - y) * (y1 - y0) > 0)))
        return v

