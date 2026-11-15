"""Konvoj (sanning): stora fartyg i formation som sicksackar kring en baskurs.

`Convoy` är en spawner (`World.spawners`) som flyttar konvojens ledpunkt: en
tänkt punkt i formationens mitt som går konvojfart på det aktuella benets kurs.
Benen följer en fast sicksackplan (vinkel från baskursen, längd) som upprepas,
så att konvojen i genomsnitt går baskursen. Varje fartyg har en `ConvoyShipAI`
som håller sin plats i formationen: platsen ligger fast i baskursens riktning
och fartyget styr och varierar farten mot den.

Nödgir: när ett konvojfartyg sänks, en torped kommer nära eller en detonation
hörs nära, girar konvojen bort från hotet (NODGIR_DEG), ökar farten och går den
nya kursen en stund innan den återtar baskursen och sicksackplanen.

Konvojens fartyg är fientliga (`side="enemy"`) men kan inte tvinga upp ubåten.

Eskortjagarna (`EscortAI`, en `DestroyerAI`) håller en skärmplats framför
konvojen och pingar tätt. De är kopplade till konvojen: ett datum längre än
`leash_nm` från ledpunkten släpps. Bara en eskort i taget jagar (`Convoy.hunter`);
den andra stannar på sin plats om inte hotet ligger nära konvojen (GUARD_NM), eller tar
över jakten om den själv har färsk kontakt och ligger mycket närmare (HANDOFF_*).
Konvojens eget brus skymmer ubåten för eskortens sonar i samma bäring.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import acoustics
from .enemy import DATUM_TIMEOUT, PING_INTERVAL, DestroyerAI
from .entities import Vessel
from .geo import angle_diff, bearing_to, distance, norm360, velocity
from .ship import ShipState
from .weapons import Torpedo

if TYPE_CHECKING:
    from .world import World

# sicksackplaner: (vinkel från baskursen, benets längd i sekunder). Medelavdriften är noll.
ZIGZAG_PLANS: tuple[tuple[tuple[float, int], ...], ...] = (
    ((30, 480), (-20, 360), (10, 600), (-35, 420), (25, 300), (-10, 540)),
    ((-25, 540), (35, 420), (-15, 300), (20, 600), (-40, 360), (25, 480)),
    ((20, 600), (-30, 480), (40, 300), (-20, 420), (0, 360), (-10, 480)),
)
NODGIR_DEG = 50.0            # så mycket girar konvojen bort från ett hot
NODGIR_S = 900               # så länge den går den nya kursen innan sicksacken tas upp igen
NODGIR_EXTRA_KN = 3.0
THREAT_TORPEDO_NM = 1.5      # en torped så nära konvojen syns eller hörs
THREAT_BLAST_NM = 4.0        # en detonation så nära
STATION_GAIN_DEG_PER_NM = 60.0
STATION_MAX_DEG = 35.0
SPEED_GAIN_KN_PER_NM = 8.0
SPEED_MAX_EXTRA_KN = 3.0
ARRIVE_COURSE_S = 15         # fartygen räknar om kurs och fart så här ofta
GUARD_NM = 1.5               # ett hot så nära konvojen tar även den bevakande eskorten
ESCORT_LEASH_NM = 4.0        # eskorten släpper ett datum så långt från konvojen
ATTACK_RUN_IN_NM = 1.0       # eskorten går in i SPEED_CLOSE tills den är så nära datumet
HANDOFF_FRESH_S = 40         # en eskort med så färsk egen kontakt ...
HANDOFF_RATIO = 0.8          # ... och så mycket närmare datumet tar över jakten
SCREEN = ((-1.5, 2.5), (1.5, 2.5), (0.0, -2.0))   # (styrbord, framåt) nm i konvojens kurs


@dataclass(frozen=True)
class ConvoyShip:
    kind: str                # transport, tanker, merchant
    column: int              # −1 vänster, 0 mitten, +1 höger
    row: int                 # 0 täten, 1 nästa …


@dataclass(frozen=True)
class ConvoyDef:
    start: tuple[float, float]          # ledpunktens läge från start (nm)
    base_course: float
    speed: float = 12.0
    ships: tuple[ConvoyShip, ...] = (
        ConvoyShip("transport", -1, 0), ConvoyShip("tanker", 1, 0), ConvoyShip("transport", 0, 1),
    )
    column_nm: float = 0.5
    row_nm: float = 0.6
    plan: int | None = None             # index i ZIGZAG_PLANS, None: slumpas


@dataclass
class Convoy:
    """Konvojens ledpunkt och sicksack. Steg före fartygens AI (spawners går före ais)."""
    cdef: ConvoyDef
    rng: random.Random
    x: float = 0.0
    y: float = 0.0
    base_course: float = 0.0
    course: float = 0.0
    speed: float = 0.0
    plan: tuple[tuple[float, int], ...] = ()
    leg: int = 0
    leg_end_t: int = 0
    nodgir_until: int = -1
    nodgir_course: float = 0.0
    nodgir_count: int = 0
    vessels: list[Vessel] = field(default_factory=list)
    escorts: list["EscortAI"] = field(default_factory=list)
    hunter: "EscortAI | None" = None
    _seen_threats: set = field(default_factory=set)

    def __post_init__(self) -> None:
        self.x, self.y = self.cdef.start
        self.base_course = self.course = self.cdef.base_course
        self.speed = self.cdef.speed
        k = self.cdef.plan if self.cdef.plan is not None else self.rng.randrange(len(ZIGZAG_PLANS))
        self.plan = ZIGZAG_PLANS[k]
        # börja någonstans i planen, en bit in i benet
        self.leg = self.rng.randrange(len(self.plan))
        off, length = self.plan[self.leg]
        self.course = norm360(self.base_course + off)
        self.leg_end_t = self.rng.randint(60, length)

    # --- formation ------------------------------------------------------------
    def station(self, s: ConvoyShip) -> tuple[float, float]:
        """Fartygets plats i formationen nu: fast i baskursens riktning kring ledpunkten."""
        along = -s.row * self.cdef.row_nm
        side = s.column * self.cdef.column_nm
        ax, ay = velocity(self.base_course, 3600.0)          # 1 nm framåt
        sx, sy = velocity(self.base_course + 90.0, 3600.0)   # 1 nm åt styrbord
        return self.x + along * ax + side * sx, self.y + along * ay + side * sy

    def alive(self) -> list[Vessel]:
        return [v for v in self.vessels if not v.sunk]

    # --- hot ---------------------------------------------------------------------
    def _threat(self, world: World) -> tuple[float, float] | None:
        """Det första nya hotet: sänkt konvojfartyg, torped nära, detonation nära."""
        for v in self.vessels:
            key = ("sunk", v.id)
            if v.sunk and key not in self._seen_threats:
                self._seen_threats.add(key)
                return v.state.x, v.state.y
        for v in world.contacts:
            if isinstance(v, Torpedo) and not v.sunk and v.side == "own":
                key = ("torpedo", v.id)
                if key not in self._seen_threats and \
                        distance(v.state.x, v.state.y, self.x, self.y) < THREAT_TORPEDO_NM:
                    self._seen_threats.add(key)
                    return v.state.x, v.state.y
        for tr in world.transients:
            if tr.kind == "explosion" and \
                    distance(tr.x, tr.y, self.x, self.y) < THREAT_BLAST_NM:
                key = ("blast", tr.x, tr.y, tr.t)
                if key not in self._seen_threats:
                    self._seen_threats.add(key)
                    return tr.x, tr.y
        return None

    def _nodgir(self, world: World, tx: float, ty: float) -> None:
        threat_b = bearing_to(self.x, self.y, tx, ty)
        side = angle_diff(threat_b, self.course)            # + hotet om styrbord
        turn = -NODGIR_DEG if side >= 0 else NODGIR_DEG
        self.nodgir_course = norm360(self.course + turn)
        self.nodgir_until = world.time + NODGIR_S
        self.nodgir_count += 1
        # formationen ligger fast i den nya kursens riktning så länge nödgiren varar
        self.base_course = self.nodgir_course

    # --- steg ------------------------------------------------------------------------
    def step(self, world: World) -> None:
        dt = 1                              # fast tidssteg
        if not self.alive():
            return
        if (threat := self._threat(world)) is not None:
            self._nodgir(world, *threat)
        if world.time < self.nodgir_until:
            self.course = self.nodgir_course
            self.speed = self.cdef.speed + NODGIR_EXTRA_KN
        else:
            if self.nodgir_until >= 0:
                # nödgiren är över: tillbaka till baskursen och planen
                self.nodgir_until = -1
                self.base_course = self.cdef.base_course
                self.leg_end_t = world.time
            if world.time >= self.leg_end_t:
                self.leg = (self.leg + 1) % len(self.plan)
                off, length = self.plan[self.leg]
                self.leg_end_t = world.time + length
                self.course = norm360(self.base_course + off)
            self.speed = self.cdef.speed
        vx, vy = velocity(self.course, self.speed)
        self.x += vx * dt
        self.y += vy * dt


class ConvoyShipAI:
    """Ett konvojfartyg: håller sin plats i formationen."""
    can_force = False
    datum = None
    roe = "-"
    state = "formation"

    def __init__(self, vessel: Vessel, convoy: Convoy, slot: ConvoyShip):
        self.vessel = vessel
        self.convoy = convoy
        self.slot = slot

    def aware(self) -> bool:
        return False

    def step(self, world: World) -> None:
        v, s, c = self.vessel, self.vessel.state, self.convoy
        if v.sunk or world.time % ARRIVE_COURSE_S:
            return
        px, py = c.station(self.slot)
        d = distance(s.x, s.y, px, py)
        if d < 1e-6:
            s.order_course(c.course)
            s.order_speed(c.speed)
            return
        b = bearing_to(s.x, s.y, px, py)
        rel = angle_diff(b, c.course)
        along = d * math.cos(math.radians(rel))          # + platsen ligger framför
        across = d * math.sin(math.radians(rel))         # + platsen ligger om styrbord
        corr = max(-STATION_MAX_DEG, min(STATION_MAX_DEG, STATION_GAIN_DEG_PER_NM * across))
        s.order_course(norm360(c.course + corr))
        extra = max(-SPEED_MAX_EXTRA_KN, min(SPEED_MAX_EXTRA_KN, SPEED_GAIN_KN_PER_NM * along))
        s.order_speed(max(2.0, c.speed + extra))


class EscortAI(DestroyerAI):
    """Eskortjagare: skärm framför konvojen, jagar bara nära den, en i taget."""
    PING_INTERVAL = {**PING_INTERVAL, "escort": 20}

    def __init__(self, vessel: Vessel, rng: random.Random, convoy: Convoy,
                 screen: tuple[float, float], leash_nm: float = ESCORT_LEASH_NM,
                 roe: str = "lethal"):
        super().__init__(vessel, rng, leash_nm=leash_nm)
        self.convoy = convoy
        self.screen = screen
        self.roe = roe
        self.state = "escort"

    def screen_point(self) -> tuple[float, float]:
        c = self.convoy
        side, ahead = self.screen
        # fast i baskursens riktning, som formationen: sicksacken flyttar inte skärmen
        ax, ay = velocity(c.base_course, 3600.0)
        sx, sy = velocity(c.base_course + 90.0, 3600.0)
        return c.x + ahead * ax + side * sx, c.y + ahead * ay + side * sy

    # koppel till konvojen i stället för till en ruta
    def _outside_leash(self, px: float, py: float) -> bool:
        return distance(px, py, self.convoy.x, self.convoy.y) > self.leash_nm

    def _noise_toward(self, world: World, noise: float, tgt: Vessel) -> float:
        s = self.vessel.state
        mask = world.masking_noise(s.x, s.y, 5.0, tgt.state.x, tgt.state.y,
                                   exclude=(self.vessel.id,), sides=("neutral", "enemy"))
        return noise if mask is None else acoustics.power_sum(noise, mask)

    def _keep_station(self) -> None:
        self.state = "escort"
        c, s = self.convoy, self.vessel.state
        tx, ty = self.screen_point()
        d = distance(s.x, s.y, tx, ty)
        s.order_course(bearing_to(s.x, s.y, tx, ty) if d > 0.1 else c.course)
        s.order_speed(min(self.SPEED_CLOSE, c.speed + min(10.0, d * 12.0)))

    def _decide(self, world: World) -> None:
        now, c = world.time, self.convoy
        h = c.hunter
        if h is not None and (h.vessel.sunk or not h.aware()):
            c.hunter = None
        if now < self.evade_until:
            super()._decide(world)
            return
        if self.datum is not None and (now - self.datum.t > DATUM_TIMEOUT
                                       or self._beyond_leash(now)):
            self.datum = None
        if self.datum is None:
            self._keep_station()
            return
        px, py = self.datum.predict(now)
        near = distance(px, py, c.x, c.y) <= GUARD_NM
        if c.hunter is None or c.hunter is self or self._closer_than(c.hunter, px, py, now):
            c.hunter = self
        elif not near:
            self._keep_station()          # den andra jagar; vi stannar hos konvojen
            return
        if self.state == "escort":
            self.state = "prosecute"
        super()._decide(world)
        if self.state == "patrol":        # basklassen släppte datumet
            self._keep_station()
        elif self.state == "attack" and now >= self.opening_until and self.datum is not None:
            # kopplad till konvojen: har bråttom in, anfallsfart först den sista sjömilen
            s = self.vessel.state
            if distance(s.x, s.y, *self.datum.predict(now)) > ATTACK_RUN_IN_NM:
                s.order_speed(self.SPEED_CLOSE)


    def _closer_than(self, other: "EscortAI", px: float, py: float, now: int) -> bool:
        """Har vi färsk egen kontakt och ligger närmare datumet än den som jagar nu?
        Då tar vi över jakten och den andra går tillbaka till sin plats."""
        if now - self.last_contact_t > HANDOFF_FRESH_S:
            return False
        s, o = self.vessel.state, other.vessel.state
        return distance(s.x, s.y, px, py) < HANDOFF_RATIO * distance(o.x, o.y, px, py)


def make_escorts(world: World, convoy: Convoy, rng: random.Random, n: int = 2,
                 roe: str = "lethal", prefix: str = "E") -> list[EscortAI]:
    """Eskortjagare på sina skärmplatser."""
    out = []
    for i in range(n):
        v = Vessel(f"{prefix}{i + 1}", "destroyer",
                   ShipState(x=0.0, y=0.0, course=convoy.course, speed=convoy.speed,
                             turn_rate=2.0, accel=0.3, max_speed=32),
                   side="enemy", has_radar=True)
        ai = EscortAI(v, random.Random(rng.random()), convoy, SCREEN[i % len(SCREEN)], roe=roe)
        v.state.x, v.state.y = ai.screen_point()
        world.contacts.append(v)
        world.ais.append(ai)
        convoy.escorts.append(ai)
        out.append(ai)
    for ai in out:
        ai.partners = [p for p in out if p is not ai]
    return out


def make_convoy(world: World, cdef: ConvoyDef, rng: random.Random,
                prefix: str = "K") -> Convoy:
    """Lägg ut konvojen på sina platser och registrera den och fartygens AI i världen."""
    convoy = Convoy(cdef, random.Random(rng.random()))
    for i, slot in enumerate(cdef.ships, start=1):
        x, y = convoy.station(slot)
        v = Vessel(f"{prefix}{i}", slot.kind,
                   ShipState(x=x, y=y, course=convoy.course, speed=cdef.speed,
                             turn_rate=0.6, accel=0.03,
                             max_speed=cdef.speed + SPEED_MAX_EXTRA_KN + 1.0),
                   side="enemy")
        convoy.vessels.append(v)
        world.contacts.append(v)
        world.ais.append(ConvoyShipAI(v, convoy, slot))
    world.spawners.append(convoy)
    return convoy
