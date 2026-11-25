"""Ubåtsjakthelikopter med doppingsonar (sanning): HSS-1 Seabat från ett hangarfartyg, som i karantänen 1962.

Helikoptern flyger till en punkt (jagarens färska datum, annars en sökpunkt), hovrar och firar ned sonaren
(`DIP_LOWER_S`). Sonaren pingar från en fast punkt på `DIP_DEPTH_M` (ofta under språngskiktet, som jagarens
skrovsonar inte når) i `DIP_S`; ett eko ger både bäring och avstånd, så läget blir skarpt och går till jagarna
över radio. Sedan hissas sonaren och helikoptern flyger till nästa doppunkt: nära läget om den hittat oss,
annars vidare i sökmönstret. Med skarpa insatsregler (jagarna har gått över till `lethal`) fäller den en
målsökande Mk 44 på ett skarpt läge, en per flygning, men bara i krig (`HeloDef.torpedo`).

Ubåten märker den genom sonaren: korta, ljusa pingar från en fast punkt nära oss som sedan flyttar sig
(`Transient("dip_ping")`, `SonarRoom`), och genom periskopet (en helikopter som hovrar lågt). Den har ingen
radar som radarvarnaren hör.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from . import acoustics
from .air import Aircraft
from .enemy import Datum, DestroyerAI
from .entities import Transient
from .geo import bearing_to, distance
from .seabed import bottom_clutter
from .weapons import MK37, launch_enemy_torpedo

if TYPE_CHECKING:
    from .world import World

FLY_KN = 85.0
DIP_DEPTH_M = 45.0
DIP_LOWER_S = 60                # sonaren firas ned (och hissas) så länge
DIP_S = 180                     # så länge den lyssnar och pingar på varje punkt
DIP_PING_S = 15
DIP_PING_LEVEL = 212.0          # dB (AQS-4): svagare än jagarens, men nära och under skiktet
DIP_DT = 10.0
ALT_HOVER_M = 15.0
ALT_FLY_M = 150.0
SEARCH_STEP_NM = 3.0            # inget eko: nästa doppunkt så långt bort
FOUND_STEP_NM = 1.0             # eko: nästa doppunkt mot det förutsagda läget
CUE_FRESH_S = 600
MK44 = replace(MK37, key="Mk44", name="Mk 44 (målsökande, från helikopter)", speed=30, range_nm=3.0,
               source_level=140, active_nm=0.5)
DROP_SIGMA_NM = 0.15            # så skarpt läge innan den fäller torpeden


class Helicopter(Aircraft):
    helo = True

    def __init__(self, id: str, x: float, y: float, course: float):
        super().__init__(id, x, y, course)
        self.state.speed = self.state.ordered_speed = FLY_KN
        self.state.max_speed = 110
        self.altitude = ALT_FLY_M


class HelicopterAI:
    can_force = False

    def __init__(self, helo: Helicopter, rng: random.Random, area: float, leave_t: int,
                 home: tuple[float, float]):
        self.vessel = helo
        self.rng = rng
        self.area = area
        self.leave_t = leave_t
        self.home = home
        self.state = "fly"              # fly, lower, dip, raise, leave
        self.roe = "-"
        self.datum: Datum | None = None
        self.point: tuple[float, float] | None = None
        self.state_t = 0
        self.next_ping = 0
        self.dropped = False
        self._heard = False
        self.torpedo = True             # HeloPatrol sätter det ur HeloDef (bara krig)

    def aware(self) -> bool:
        return self.datum is not None

    def _cue(self, world: World) -> Datum | None:
        return next((ai.datum for ai in world.ais if isinstance(ai, DestroyerAI)
                     and ai.datum is not None and world.time - ai.datum.t < CUE_FRESH_S), None)

    def _lethal(self, world: World) -> bool:
        return any(isinstance(ai, DestroyerAI) and ai.roe == "lethal" for ai in world.ais)

    def _next_point(self, world: World) -> tuple[float, float]:
        p = self.vessel.state
        d = self.datum if self.datum is not None and world.time - self.datum.t < CUE_FRESH_S else self._cue(world)
        if d is not None:
            x, y = d.predict(world.time + DIP_LOWER_S + 120)
            if self._heard:              # ett eko: nästa punkt nära det förutsagda läget
                b = bearing_to(p.x, p.y, x, y)
                r = min(distance(p.x, p.y, x, y), FOUND_STEP_NM)
                return p.x + r * math.sin(math.radians(b)), p.y + r * math.cos(math.radians(b))
            return x + self.rng.gauss(0, d.sigma), y + self.rng.gauss(0, d.sigma)
        b = self.rng.uniform(0, 360)
        x = min(max(p.x + SEARCH_STEP_NM * math.sin(math.radians(b)), 1.0), self.area - 1.0)
        y = min(max(p.y + SEARCH_STEP_NM * math.cos(math.radians(b)), 1.0), self.area - 1.0)
        return x, y

    def _ping(self, world: World) -> None:
        p, own = self.vessel.state, world.own
        world.emit(Transient("dip_ping", p.x, p.y, DIP_DEPTH_M, DIP_PING_LEVEL, self.vessel.id, world.time))
        if own.sunk:
            return
        r = distance(p.x, p.y, own.state.x, own.state.y)
        tl = acoustics.transmission_loss(r, DIP_DEPTH_M, own.state.depth, world.env)
        noise = world.env.noise_at(own.state.x, own.state.y)
        se = acoustics.active_excess(DIP_PING_LEVEL, tl, own.target_strength, noise, DIP_DT) \
            - bottom_clutter(world, own)
        if se + self.rng.gauss(0, 3) <= 0:
            return
        # bäring och avstånd: ett skarpt läge
        sigma = max(0.05, 0.05 * r)
        x, y = own.state.x + self.rng.gauss(0, sigma), own.state.y + self.rng.gauss(0, sigma)
        self.datum = Datum(x, y, own.state.depth, sigma, world.time)
        self._heard = True
        world.mission.setdefault("helo_log", []).append((world.time, round(r, 2)))
        for ai in world.ais:                     # jagarna får läget över radio
            if isinstance(ai, DestroyerAI) and not ai.vessel.sunk:
                ai._set_datum(world, x, y, own.state.depth, sigma, fix=True)
                ai.last_contact_t = world.time
        if self.torpedo and self._lethal(world) and not self.dropped and sigma <= DROP_SIGMA_NM:
            self.dropped = True
            course = bearing_to(p.x, p.y, x, y)
            launch_enemy_torpedo(world, self.vessel, MK44, course, max(20.0, own.state.depth))

    def step(self, world: World) -> None:
        helo, p, now = self.vessel, self.vessel.state, world.time
        if self.state == "leave":
            helo.altitude = ALT_FLY_M
            p.order_speed(FLY_KN)
            p.order_course(bearing_to(p.x, p.y, *self.home))
            if distance(p.x, p.y, *self.home) < 1.0:
                helo.gone = True
            return
        if now >= self.leave_t and self.state in ("fly", "dip"):
            self.state, self.state_t = ("raise", now) if self.state == "dip" else ("leave", now)
            return
        if self.state == "fly":
            if self.point is None:
                self.point = self._next_point(world)
                self._heard = False
            helo.altitude = ALT_FLY_M
            p.order_speed(FLY_KN)
            p.order_course(bearing_to(p.x, p.y, *self.point))
            if distance(p.x, p.y, *self.point) < 0.1:
                self.state, self.state_t = "lower", now
            return
        p.order_speed(0.0)
        p.speed = 0.0                            # hovrar
        helo.altitude = ALT_HOVER_M
        if self.state == "lower" and now - self.state_t >= DIP_LOWER_S:
            self.state, self.state_t, self.next_ping = "dip", now, now
        elif self.state == "dip":
            if now >= self.next_ping:
                self.next_ping = now + DIP_PING_S
                self._ping(world)
            if now - self.state_t >= DIP_S:
                self.state, self.state_t = "raise", now
        elif self.state == "raise" and now - self.state_t >= DIP_LOWER_S:
            self.point = None
            self.state = "leave" if now >= self.leave_t else "fly"


@dataclass(frozen=True)
class HeloDef:
    """När helikoptrarna kommer och hur länge de stannar (sekunder simtid), och varifrån (hangarfartyget)."""
    first_s: tuple[int, int] = (30 * 60, 70 * 60)
    on_station_s: tuple[int, int] = (50 * 60, 80 * 60)
    gap_s: tuple[int, int] = (40 * 60, 70 * 60)
    entry: tuple[float, float] = (30.0, 10.0)
    only_cued: bool = True          # bara när jagaren har ett färskt datum (annars söker de inte här)
    torpedo: bool = False           # fäller en Mk 44 med skarpa regler: bara i krig (i jagad, där jagarna fäller
                                    # skarpt men det inte är krig, sänkte den oss: frö 102)


class HeloPatrol:
    """Skickar ut en helikopter i taget (egen slumpström)."""

    def __init__(self, hdef: HeloDef, rng: random.Random, area: float = 20.0):
        self.hdef = hdef
        self.rng = rng
        self.area = area
        self.next_t = -1
        self.count = 0
        self.current: HelicopterAI | None = None

    def step(self, world: World) -> None:
        if self.next_t < 0:
            self.next_t = self.rng.randint(*self.hdef.first_s)
        ai = self.current
        if ai is not None and ai.vessel.gone:
            world.contacts.remove(ai.vessel)
            world.ais.remove(ai)
            self.current = None
            self.next_t = world.time + self.rng.randint(*self.hdef.gap_s)
        if self.current is None and world.time >= self.next_t:
            cued = any(isinstance(a, DestroyerAI) and a.datum is not None and
                       world.time - a.datum.t < CUE_FRESH_S for a in world.ais)
            if self.hdef.only_cued and not cued:
                self.next_t = world.time + 300        # titta igen om fem minuter
                return
            self.count += 1
            ex, ey = self.hdef.entry
            helo = Helicopter(f"HS{self.count}", ex, ey, bearing_to(ex, ey, self.area / 2, self.area / 2))
            leave = world.time + self.rng.randint(*self.hdef.on_station_s)
            ai = HelicopterAI(helo, random.Random(self.rng.random()), self.area, leave, (ex, ey))
            ai.torpedo = self.hdef.torpedo
            world.contacts.append(helo)
            world.ais.append(ai)
            self.current = ai
