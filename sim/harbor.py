"""Hamnskydd vid ett inlopp (sanning): hydrofonkedja, ubåtsnät med grind och patrullbåt.

- `HydrophoneLine`: fasta hydrofoner på botten tvärs inflygningen. Var tionde sekund
  lyssnar var och en efter ubåten (passivt, landstationens operatörer) och efter
  transienter. Hör de oss får patrullbåtarna ett datum kring den hydrofon som hörde,
  med en osäkerhet som växer med avståndet. Handelsfartyg i samma bäring maskerar.
- `Net`: ett nät från ytan till botten tvärs farleden, med en grind i mitten som
  öppnas när ett fartyg ska igenom och stängs några minuter efter. Korsar vi nätlinjen
  utanför en öppen grind fastnar vi: ubåten stoppas, propellern skadas och nätets
  larmbojar ger patrullbåten ett fix.
- `PatrolBoatAI`: en liten ubåtsjaktbåt; samma beteende som jagaren men svagare sonar,
  lägre fart och färre sjunkbomber. Håller en skärm i sitt patrullområde (`box`), men när
  ett fartyg är på väg in lämnar den skärmen och eskorterar det, en bit framför, fram till
  grinden. Då öppnas luckor i skärmen, och den som följer tätt efter fartyget göms i dess
  brus och kölvatten.

`HarborDefense` samlar delarna och stegas som en spawner (efter förflyttningen).
Periskopet ser nätets bojar (`periscope_view`), med grindens läge.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import acoustics
from .enemy import DestroyerAI
from .entities import Transient
from .geo import bearing_to, distance, norm360

if TYPE_CHECKING:
    from .world import World

HYDROPHONE_DT = 10.0
HYDROPHONE_DEPTH = 40.0
HYDROPHONE_INTERVAL = 10
HYDROPHONE_SIGMA_BASE = 0.25     # datumets osäkerhet: bas + andel av avståndet
HYDROPHONE_SIGMA_PER_NM = 0.6
SHIP_NOISE_NM = 5.0              # fartyg närmare än så höjer hydrofonens brus
ESCORT_NM = 6.0                  # ett fartyg så nära grinden på väg in eskorteras
ESCORT_AHEAD_NM = 0.4            # patrullbåten går så här långt framför
ESCORT_DONE_NM = 0.25            # fartyget så nära grinden: eskorten klar
COASTAL_NOISE_DB = 64.0          # bränning och knäppande räkor nära kusten

GATE_HALF_NM = 0.1               # grindens halva bredd (~185 m)
GATE_OPEN_NM = 1.0               # ett fartyg så nära: grinden öppnas
GATE_CLOSE_S = 240               # och stängs så här länge efter att det passerat
NET_SOUND_LEVEL = 150.0
NET_PROP_DAMAGE = 0.15
NET_CLEAR_NM = 0.02
NET_SPOT_DAY_NM = 2.0            # bojarna syns så långt i periskopet
NET_SPOT_NIGHT_NM = 0.5


@dataclass
class HydrophoneLine:
    points: list[tuple[float, float]]
    rng: random.Random
    next_t: int = 0

    def listen(self, world: World, alarm) -> None:
        if world.time < self.next_t:
            return
        self.next_t = world.time + HYDROPHONE_INTERVAL
        own = world.own
        if own.sunk:
            return
        o = own.state
        lvl = own.radiated_level(world.env)
        noise = max(world.env.background_noise, COASTAL_NOISE_DB)
        for hx, hy in self.points:
            r = max(0.02, distance(hx, hy, o.x, o.y))
            n = self._noise(world, hx, hy, noise)
            se = lvl - world.env.transmission_loss(r, HYDROPHONE_DEPTH, o.depth) - n - HYDROPHONE_DT
            if se + self.rng.gauss(0, 2) > 0:
                alarm(world, o.x, o.y, o.depth, HYDROPHONE_SIGMA_BASE + HYDROPHONE_SIGMA_PER_NM * r,
                      "hydrofon")
                return
        for tr in world.transients:
            if tr.source_id != own.id:
                continue
            for hx, hy in self.points:
                r = max(0.02, distance(hx, hy, tr.x, tr.y))
                se = tr.level - world.env.transmission_loss(r, HYDROPHONE_DEPTH, tr.depth) \
                    - self._noise(world, hx, hy, noise) - HYDROPHONE_DT
                if se > 0:
                    alarm(world, tr.x, tr.y, tr.depth,
                          HYDROPHONE_SIGMA_BASE + 0.3 * HYDROPHONE_SIGMA_PER_NM * r, "hydrofon")
                    return


    @staticmethod
    def _noise(world: World, hx: float, hy: float, base: float) -> float:
        """Rundstrålande hydrofon: alla fartyg i närheten höjer brusgolvet, åt alla håll."""
        levels = [base]
        for v in world.contacts:
            if not v.is_ship or v.sunk or v is world.own:
                continue
            r = distance(hx, hy, v.state.x, v.state.y)
            if r < SHIP_NOISE_NM:
                levels.append(v.radiated_level(world.env)
                              - world.env.transmission_loss(max(r, 0.02), HYDROPHONE_DEPTH, 5.0))
        return acoustics.power_sum(*levels)


@dataclass
class Net:
    """Nät tvärs farleden längs y = y, från x0 till x1, grind kring gate_x."""
    y: float
    x0: float
    x1: float
    gate_x: float
    open_until: int = -1
    caught: bool = False
    _prev: tuple[float, float] | None = None

    def gate_open(self, now: int) -> bool:
        return now < self.open_until

    def step(self, world: World, alarm) -> None:
        now = world.time
        for v in world.contacts:
            if v.is_ship and not v.sunk and v.side != "own" and \
                    distance(v.state.x, v.state.y, self.gate_x, self.y) < GATE_OPEN_NM:
                self.open_until = now + GATE_CLOSE_S
        own = world.own
        o = own.state
        prev, self._prev = self._prev, (o.x, o.y)
        if prev is None or own.sunk:
            return
        px, py = prev
        if (py - self.y) * (o.y - self.y) > 0 or py == o.y == self.y:
            if abs(o.y - self.y) > NET_CLEAR_NM:
                self.caught = False             # loss från nätet
            return
        # var korsade vi linjen?
        f = (self.y - py) / (o.y - py) if o.y != py else 0.0
        cx = px + f * (o.x - px)
        if not (self.x0 <= cx <= self.x1):
            return
        if abs(cx - self.gate_x) <= GATE_HALF_NM and self.gate_open(now):
            return
        # fast i nätet: tillbaka på samma sida, stopp
        side = 1 if py > self.y else -1
        o.x, o.y = cx, self.y + side * 0.005
        self._prev = (o.x, o.y)
        o.speed = o.ordered_speed = 0.0
        if not self.caught:
            self.caught = True
            s = own.sys
            s.health["propulsion"] = max(0.0, s.health["propulsion"] - NET_PROP_DAMAGE)
            own.alert("net.caught", gate_open=self.gate_open(now))
            world.emit(Transient("net", o.x, o.y, o.depth, NET_SOUND_LEVEL, own.id, now))
            alarm(world, o.x, o.y, o.depth, 0.1, "nät")


class PatrolBoatAI(DestroyerAI):
    """Liten ubåtsjaktbåt vid inloppet."""
    PING_LEVEL = 196.0       # liten båt, gammal sonar: ~0,6 nm under skiktet
    SPEED_CLOSE = 18
    SPEED_SEARCH = 9
    SPEED_OPEN = 14
    SPEED_ATTACK = 11
    SPEED_EVADE = 22
    CHARGES = (2, 6)
    PATROL_MARGIN = 0.1
    PING_INTERVAL = {"patrol": 45, "prosecute": 15, "attack": 8, "evade": 30, "escort": 45}

    def __init__(self, *args, gate: tuple[float, float] | None = None, **kw):
        super().__init__(*args, **kw)
        self.gate = gate                      # grinden: dit eskorterar den fartyg
        self.escorting: str | None = None

    def _escort_target(self, world: World):
        gx, gy = self.gate
        if self.escorting is not None:
            v = next((c for c in world.contacts if c.id == self.escorting), None)
            if v is not None and not v.sunk and v.state.y < gy - ESCORT_DONE_NM:
                return v
            self.escorting = None
        best = None
        for v in world.contacts:
            if v.kind != "merchant" or v.sunk or v.side != "neutral":
                continue
            st = v.state
            r = distance(st.x, st.y, gx, gy)
            if st.y >= gy - ESCORT_DONE_NM or r > ESCORT_NM:
                continue
            if abs((bearing_to(st.x, st.y, gx, gy) - st.course + 180) % 360 - 180) > 40:
                continue                      # inte på väg in
            if best is None or r < best[0]:
                best = (r, v)
        if best is None:
            return None
        self.escorting = best[1].id
        return best[1]

    def _decide(self, world: World) -> None:
        if self.gate is not None and self.datum is None and world.time >= self.evade_until:
            ship = self._escort_target(world)
            if ship is not None:
                self.state = "escort"
                st, s = ship.state, self.vessel.state
                b = math.radians(st.course)
                tx = st.x + ESCORT_AHEAD_NM * math.sin(b)
                ty = st.y + ESCORT_AHEAD_NM * math.cos(b)
                d = distance(s.x, s.y, tx, ty)
                s.order_course(bearing_to(s.x, s.y, tx, ty) if d > 0.05 else st.course)
                s.order_speed(min(self.SPEED_CLOSE, st.speed + min(8.0, d * 12)))
                return
        if self.state == "escort":
            self.state = "patrol"
        super()._decide(world)
    MAST_NM = 2.0
    MAST_P = 0.01


@dataclass
class HarborDefense:
    hydrophones: HydrophoneLine | None = None
    net: Net | None = None
    boats: list[PatrolBoatAI] = field(default_factory=list)
    alarms: int = 0
    last_alarm: tuple[int, str] | None = None

    def alarm(self, world: World, x: float, y: float, depth: float, sigma: float,
              source: str) -> None:
        self.alarms += 1
        self.last_alarm = (world.time, source)
        world.mission["harbor_alarms"] = self.alarms
        for b in self.boats:
            if b.vessel.sunk:
                continue
            b._set_datum(world, x + b.rng.gauss(0, sigma * 0.7), y + b.rng.gauss(0, sigma * 0.7),
                         max(15.0, depth), sigma, fix=sigma <= 0.15)

    def step(self, world: World) -> None:
        if self.net is not None:
            self.net.step(world, self.alarm)
        if self.hydrophones is not None:
            self.hydrophones.listen(world, self.alarm)

    # --- periskopet -------------------------------------------------------------------
    def periscope_view(self, world: World, rng: random.Random) -> list[tuple[str, dict]]:
        """Det vakthavande ser av hamnskyddet: nätets bojrad och grinden."""
        net = self.net
        if net is None:
            return []
        o = world.own.state
        day = world.env.is_day(world.time)
        reach = NET_SPOT_DAY_NM if day else NET_SPOT_NIGHT_NM
        # närmaste punkt på bojraden
        nx = min(max(o.x, net.x0), net.x1)
        r = distance(o.x, o.y, nx, net.y)
        if r > reach:
            return []
        gb = bearing_to(o.x, o.y, net.gate_x, net.y)
        return [("off.periscope.net", {
            "bearing": norm360(bearing_to(o.x, o.y, nx, net.y) + rng.gauss(0, 2)),
            "range": max(0.05, r * rng.uniform(0.85, 1.15)),
            "gate_bearing": norm360(gb + rng.gauss(0, 2)),
            "gate_open": net.gate_open(world.time),
        })]

    def chart_hint(self) -> tuple[float, float, float, float] | None:
        n = self.net
        return None if n is None else (n.x0, n.y, n.x1, n.gate_x)


def hydrophone_points(x0: float, x1: float, y: float, spacing: float) -> list[tuple[float, float]]:
    n = max(2, int(math.floor((x1 - x0) / spacing)) + 1)
    return [(x0 + i * (x1 - x0) / (n - 1), y) for i in range(n)]
