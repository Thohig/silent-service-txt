"""Ubåtsjaktflyg (sanning): ett amerikanskt patrullflygplan över kvadraten.

Flygplanet hörs inte under vattnet. Det söker med radar (mot periskop,
master och ubåt i ytläge), fäller sonobojar och flyger lågt med magnetisk
spaning (MAD) över det läge det tror att ubåten har. Det skjuter inte, men
ger jagaren ett nytt utgångsläge för sökningen (datum).

Ubåten märker flyget genom radarvarnaren och periskopet, och hör bojarnas
plask och den aktiva bojens pingar (transienterna "buoy" och "buoy_ping").

Precis som jagarens sensorer läser flygets spaning sanningen.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import acoustics
from .enemy import Datum, DestroyerAI
from .entities import Emission, Transient, Vessel
from .geo import NM_IN_M, bearing_to, distance, norm360
from .seabed import bottom_clutter
from .ship import ShipState

if TYPE_CHECKING:
    from .world import World

SEARCH_KN = 180.0
MAD_KN = 150.0
ALT_SEARCH_M = 300.0
ALT_MAD_M = 60.0
RADAR_SWEEP_S = 10
RADAR_MAST_NM = 6.0          # periskop och antenn syns på radarn så här långt
P_RADAR_MAST = 0.06          # per svep
RADAR_SURFACED_NM = 25.0
P_RADAR_SURFACED = 0.5
MAD_RANGE_M = 250.0          # snedavstånd: under ~190 m djup går flyget rakt över oss utan utslag
BUOY_LIFE_S = 2 * 3600
BUOY_DEPTH_M = 20.0
BUOY_DT = 8.0
BUOY_LISTEN_S = 10
BUOY_RING_NM = 1.0
N_PASSIVE_BUOYS = 4
ACTIVE_BUOYS = 2
ACTIVE_PING_S = 20
ACTIVE_LIFE_S = 1800
ACTIVE_DT = 10.0
DATUM_TIMEOUT_S = 1200
MAD_LEG_NM = 1.0             # klöverblad: så här långt förbi datum innan flyget vänder
CUE_FRESH_S = 600            # jagarens datum så här färskt: flyget går dit
LEAVE_NM = 15.0              # utanför kvadraten så här långt: flyget är borta


class Aircraft(Vessel):
    airborne = True

    def __init__(self, id: str, x: float, y: float, course: float):
        super().__init__(id=id, kind="aircraft",
                         state=ShipState(x=x, y=y, course=course, speed=SEARCH_KN, turn_rate=3.0,
                                         accel=2.0, max_speed=220),
                         side="enemy")
        self.altitude = ALT_SEARCH_M
        self.gone = False

    def radiated_level(self, env) -> float:
        return -999.0


class Sonobuoy(Vessel):
    def __init__(self, id: str, x: float, y: float, active: bool, expire_t: int):
        super().__init__(id=id, kind="sonobuoy",
                         state=ShipState(x=x, y=y, course=0, speed=0, depth=BUOY_DEPTH_M),
                         side="enemy")
        self.active = active
        self.expire_t = expire_t
        self.next_ping = 0

    def radiated_level(self, env) -> float:
        return -999.0


@dataclass(frozen=True)
class AirDef:
    """När flyget kommer och hur länge det stannar (sekunder simtid)."""
    first_s: tuple[int, int] = (40 * 60, 80 * 60)
    on_station_s: tuple[int, int] = (60 * 60, 90 * 60)
    gap_s: tuple[int, int] = (45 * 60, 75 * 60)
    entry: tuple[float, float] = (-10.0, 18.0)       # varifrån det kommer (Key West)


class AircraftAI:
    can_force = False

    def __init__(self, plane: Aircraft, rng: random.Random, area: float, leave_t: int,
                 home: tuple[float, float]):
        self.vessel = plane
        self.rng = rng
        self.area = area
        self.leave_t = leave_t
        self.home = home
        self.state = "search"
        self.roe = "-"
        self.datum: Datum | None = None
        self.buoys: list[Sonobuoy] = []
        self.passive_left = 2 * N_PASSIVE_BUOYS
        self.active_left = ACTIVE_BUOYS
        self.next_sweep = 0
        self.next_listen = 0
        self.waypoint: tuple[float, float] | None = None
        self.mad_out = False
        self._leg = 0.0
        self.want_active: tuple[float, float] | None = None
        self.cue_wait = 0
        self.found = False          # har flyget självt hittat ubåten
        self._n_buoy = 0

    def aware(self) -> bool:
        return self.datum is not None

    # ------------------------------------------------------------------ sensorer
    def _detect(self, world: World, x: float, y: float, depth: float, sigma: float,
                how: str) -> None:
        now = world.time
        if self.datum is None or sigma <= self.datum.sigma or now - self.datum.t > 120:
            self.datum = Datum(x, y, depth, sigma, now)
            if not self.found:
                self.found = True
                world.mission["air_contacts"] = world.mission.get("air_contacts", 0) + 1
            world.mission.setdefault("air_log", []).append((now, how))
        if how == "passiv boj":
            self.want_active = (x, y)
        # jagaren får läget över radio
        for ai in world.ais:
            if isinstance(ai, DestroyerAI) and not ai.vessel.sunk:
                ai._set_datum(world, x, y, depth, sigma, fix=sigma < 0.1)

    def _radar(self, world: World) -> None:
        p = self.vessel.state
        world.emit_em(Emission("radar", p.x, p.y, self.vessel.id, world.time))
        own = world.own
        r = distance(p.x, p.y, own.state.x, own.state.y)
        if own.surfaced:
            det_r, prob = RADAR_SURFACED_NM, P_RADAR_SURFACED
        elif own.masts_up(world.time):
            det_r, prob = RADAR_MAST_NM, P_RADAR_MAST
        else:
            return
        if r < det_r and self.rng.random() < prob:
            self._detect(world, own.state.x + self.rng.gauss(0, 0.1),
                         own.state.y + self.rng.gauss(0, 0.1), own.state.depth, 0.15, "radar")

    def _listen(self, world: World) -> None:
        own = world.own
        noise = world.env.noise_at(own.state.x, own.state.y)
        best = None
        for b in self.buoys:
            if b.sunk:
                continue
            r = distance(b.state.x, b.state.y, own.state.x, own.state.y)
            tl = acoustics.transmission_loss(r, BUOY_DEPTH_M, own.state.depth, world.env)
            if b.active:
                if world.time >= b.next_ping:
                    b.next_ping = world.time + ACTIVE_PING_S
                    world.emit(Transient("buoy_ping", b.state.x, b.state.y, BUOY_DEPTH_M,
                                         acoustics.BUOY_PING_LEVEL, b.id, world.time))
                    se = acoustics.active_excess(acoustics.BUOY_PING_LEVEL, tl,
                                                 own.target_strength, noise, ACTIVE_DT) \
                        - bottom_clutter(world, own)
                    if se + self.rng.gauss(0, 3) > 0:
                        # avstånd men ingen bäring: ett läge på cirkeln, nära förra datum
                        ref = self.datum or Datum(b.state.x, b.state.y, 100, 1.0, world.time)
                        a = math.atan2(ref.x - b.state.x, ref.y - b.state.y)
                        a = 0.6 * a + 0.4 * math.atan2(own.state.x - b.state.x,
                                                       own.state.y - b.state.y)
                        self._detect(world, b.state.x + r * math.sin(a), b.state.y + r * math.cos(a),
                                     own.state.depth, max(0.2, 0.5 * r), "aktiv boj")
                continue
            se = own.radiated_level(world.env) - tl - noise - BUOY_DT + self.rng.gauss(0, 2)
            if se > 0 and (best is None or se > best[1]):
                best = (b, se)
        if best is not None:
            b = best[0]
            self._detect(world, b.state.x, b.state.y, 100.0, 0.8, "passiv boj")

    def _mad(self, world: World) -> None:
        p, own = self.vessel.state, world.own.state
        horiz = distance(p.x, p.y, own.x, own.y) * NM_IN_M
        if math.hypot(horiz, self.vessel.altitude + own.depth) < MAD_RANGE_M:
            self._detect(world, own.x + self.rng.gauss(0, 0.02), own.y + self.rng.gauss(0, 0.02),
                         own.depth, 0.05, "MAD")

    # ------------------------------------------------------------------ bojar
    def _drop(self, world: World, x: float, y: float, active: bool) -> None:
        self._n_buoy += 1
        life = ACTIVE_LIFE_S if active else BUOY_LIFE_S
        b = Sonobuoy(f"{self.vessel.id}B{self._n_buoy}", x, y, active, world.time + life)
        b.next_ping = world.time + 30
        world.contacts.append(b)
        self.buoys.append(b)
        world.emit(Transient("buoy", x, y, 1.0, acoustics.BUOY_SPLASH_LEVEL, b.id, world.time))

    def _drop_pattern(self, world: World) -> None:
        if self.passive_left < N_PASSIVE_BUOYS or self.datum is None:
            return
        d = self.datum
        a0 = self.rng.uniform(0, 360)
        for i in range(N_PASSIVE_BUOYS):
            a = math.radians(a0 + 360 * i / N_PASSIVE_BUOYS)
            self._drop(world, d.x + BUOY_RING_NM * math.sin(a), d.y + BUOY_RING_NM * math.cos(a),
                       active=False)
        self.passive_left -= N_PASSIVE_BUOYS

    # ------------------------------------------------------------------ beslut
    def step(self, world: World) -> None:
        plane, p, now = self.vessel, self.vessel.state, world.time
        for b in self.buoys:
            if not b.sunk and now >= b.expire_t:
                b.sunk = True
        if self.state == "leave":
            p.order_course(bearing_to(p.x, p.y, *self.home))
            m = LEAVE_NM
            if distance(p.x, p.y, *self.home) < 1.0 or \
                    not (-m <= p.x <= self.area + m and -m <= p.y <= self.area + m):
                plane.gone = True
            return
        if now >= self.leave_t:
            self.state = "leave"
            plane.altitude = ALT_SEARCH_M
            p.order_speed(SEARCH_KN)
            return
        if now >= self.next_sweep:
            self.next_sweep = now + RADAR_SWEEP_S
            self._radar(world)
        if now >= self.next_listen:
            self.next_listen = now + BUOY_LISTEN_S
            self._listen(world)
        if plane.altitude <= ALT_MAD_M:
            self._mad(world)

        if self.datum is not None and now - self.datum.t > DATUM_TIMEOUT_S:
            self.datum = None
        if self.datum is None:
            self._search(world)
        else:
            self._prosecute(world)

    def _search(self, world: World) -> None:
        p = self.vessel.state
        cue = next((ai.datum for ai in world.ais if isinstance(ai, DestroyerAI)
                    and ai.datum is not None and world.time - ai.datum.t < CUE_FRESH_S), None)
        if cue is not None and world.time >= self.cue_wait:
            # jagaren har ett färskt läge: gå dit och lägg ut bojar
            cx, cy = cue.predict(world.time)
            self.datum = Datum(cx, cy, cue.depth, max(cue.sigma, 0.5), world.time)
            self.cue_wait = world.time + DATUM_TIMEOUT_S + CUE_FRESH_S
            self._prosecute(world)
            return
        self.state = "search"
        self.vessel.altitude = ALT_SEARCH_M
        p.order_speed(SEARCH_KN)
        if self.waypoint is None or distance(p.x, p.y, *self.waypoint) < 0.5:
            # sök där jagaren tror att ubåten är, annars någonstans i kvadraten
            cue = next((ai.datum for ai in world.ais
                        if isinstance(ai, DestroyerAI) and ai.datum is not None), None)
            if cue is not None:
                cx, cy = cue.predict(world.time)
                r = 1.5 + 2 * cue.sigma
                self.waypoint = (cx + self.rng.uniform(-r, r), cy + self.rng.uniform(-r, r))
            else:
                self.waypoint = (self.rng.uniform(1, self.area - 1),
                                 self.rng.uniform(1, self.area - 1))
        p.order_course(bearing_to(p.x, p.y, *self.waypoint))

    def _prosecute(self, world: World) -> None:
        p, d = self.vessel.state, self.datum
        if self.state != "prosecute":
            self.state = "prosecute"
            self.mad_out = False
            if d.sigma > 0.3:
                self._drop_pattern(world)          # grovt läge: en ring passiva bojar
        if self.want_active is not None:
            # en passiv boj har hört något: en aktiv boj där, om vi har någon kvar
            if self.active_left > 0 and not any(b.active and not b.sunk for b in self.buoys):
                self.active_left -= 1
                self._drop(world, *self.want_active, active=True)
            self.want_active = None
        # MAD: klöverblad lågt över datum
        self.vessel.altitude = ALT_MAD_M
        p.order_speed(MAD_KN)
        r = distance(p.x, p.y, d.x, d.y)
        if not self.mad_out and r < 0.1:
            self.mad_out = True
            self._leg = norm360(p.course + self.rng.choice((-1, 1)) * self.rng.uniform(60, 120))
        if self.mad_out:
            if r > MAD_LEG_NM:
                self.mad_out = False
            else:
                p.order_course(self._leg)
                return
        p.order_course(bearing_to(p.x, p.y, d.x, d.y))


@dataclass
class AirPatrol:
    """Skickar ut ett flygplan i taget enligt AirDef."""
    adef: AirDef
    rng: random.Random
    area: float = 20.0
    next_t: int = -1
    count: int = 0
    current: AircraftAI | None = None
    buoys: list[Sonobuoy] = field(default_factory=list)

    def step(self, world: World) -> None:
        if self.next_t < 0:
            self.next_t = self.rng.randint(*self.adef.first_s)
        self._purge(world)
        if self.current is None and world.time >= self.next_t:
            self._launch(world)

    def _launch(self, world: World) -> None:
        self.count += 1
        ex, ey = self.adef.entry
        c = bearing_to(ex, ey, self.area / 2, self.area / 2)
        plane = Aircraft(f"P{self.count}", ex, ey, c)
        leave = world.time + self.rng.randint(*self.adef.on_station_s)
        ai = AircraftAI(plane, random.Random(self.rng.random()), self.area, leave, (ex, ey))
        world.contacts.append(plane)
        world.ais.append(ai)
        self.current = ai

    def _purge(self, world: World) -> None:
        ai = self.current
        if ai is not None and ai.vessel.gone:
            self.buoys += ai.buoys
            world.contacts.remove(ai.vessel)
            world.ais.remove(ai)
            self.current = None
            self.next_t = world.time + self.rng.randint(*self.adef.gap_s)
        dead = [b for b in self.buoys if b.sunk or world.time >= b.expire_t]
        for b in dead:
            if b in world.contacts:
                world.contacts.remove(b)
            self.buoys.remove(b)
        if ai is not None:
            for b in [b for b in ai.buoys if b.sunk and b in world.contacts]:
                world.contacts.remove(b)
