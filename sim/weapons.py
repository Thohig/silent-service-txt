"""Vapen i sanningslagret: sjunkbomber, torpeder och skenmål.

Torpeder är fartyg i världen (kind="torpedo") som rör sig själva.
Träff avgörs geometriskt: närmaste passage under ett tidssteg mot målet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import acoustics
from .entities import Transient, Vessel
from .geo import NM_IN_M, angle_diff, bearing_to, distance
from .ship import ShipState

if TYPE_CHECKING:
    from .world import World

SINK_RATE = 3.5              # m/s för sjunkbomber
ARM_DISTANCE_NM = 0.25       # torpeden armeras efter denna sträcka
HIT_RADIUS_NM = 0.03         # ~55 m: halva jagarens längd


@dataclass(frozen=True)
class TorpedoSpec:
    key: str
    name: str
    speed: float              # knop
    range_nm: float
    homing: bool = False
    nuclear: bool = False
    source_level: float = 150.0
    run_depth: float = 5.0
    kill_radius_nm: float = HIT_RADIUS_NM
    seeker_cone: float = 35.0
    seeker_noise: float = 70.0


TORPEDO_TYPES: dict[str, TorpedoSpec] = {
    "53-61": TorpedoSpec("53-61", "53-61 (rak)", speed=45, range_nm=8.0, source_level=155),
    "SET-53": TorpedoSpec("SET-53", "SET-53 (målsökande)", speed=23, range_nm=4.0,
                          homing=True, source_level=130),
    "T-5": TorpedoSpec("T-5", "T-5 (kärnladdning)", speed=40, range_nm=5.5, nuclear=True,
                       source_level=150, kill_radius_nm=1.0),
}


@dataclass
class DepthCharge:
    x: float
    y: float
    target_depth: float
    practice: bool
    source_id: str
    depth: float = 0.0


class Torpedo(Vessel):
    def __init__(self, id: str, spec: TorpedoSpec, x: float, y: float, course: float,
                 launch_t: int, detonate_at_nm: float | None = None):
        state = ShipState(x=x, y=y, course=course, speed=spec.speed, depth=spec.run_depth,
                          turn_rate=3.0, max_speed=spec.speed)
        super().__init__(id=id, kind="torpedo", state=state, side="own")
        self.spec = spec
        self.launch_t = launch_t
        self.launch_xy = (x, y)
        self.run_nm = 0.0
        self.locked: str | None = None
        self.detonate_at_nm = detonate_at_nm
        self.done = False

    def radiated_level(self, env) -> float:
        return -999.0 if self.done else self.spec.source_level


class Decoy(Vessel):
    def __init__(self, id: str, x: float, y: float, depth: float, expire_t: int):
        state = ShipState(x=x, y=y, course=0, speed=0.3, depth=depth)
        super().__init__(id=id, kind="decoy", state=state, side="own")
        self.expire_t = expire_t

    def radiated_level(self, env) -> float:
        return -999.0 if self.sunk else 135.0


# ---------------------------------------------------------------------- sjunkbomber
def drop_charges(world: World, source: Vessel, aim_x: float, aim_y: float, aim_depth: float,
                 n: int, practice: bool, spread_nm: float = 0.04, depth_spread: float = 25.0) -> None:
    rng = world.rng
    for i in range(n):
        world.charges.append(DepthCharge(
            x=aim_x + rng.gauss(0, spread_nm), y=aim_y + rng.gauss(0, spread_nm),
            target_depth=max(15.0, aim_depth + rng.gauss(0, depth_spread)),
            practice=practice, source_id=source.id))
    world.emit(Transient("splash", source.state.x, source.state.y, 0.0,
                         acoustics.SPLASH_LEVEL, source.id, world.time, practice))


def _step_charges(world: World, dt: int) -> None:
    remaining = []
    own = world.own
    for c in world.charges:
        c.depth += SINK_RATE * dt
        if c.depth < c.target_depth:
            remaining.append(c)
            continue
        level = acoustics.EXPLOSION_PRACTICE if c.practice else acoustics.EXPLOSION_REAL
        world.emit(Transient("explosion", c.x, c.y, c.depth, level, c.source_id,
                             world.time, c.practice))
        world.mission["charges_exploded"] = world.mission.get("charges_exploded", 0) + 1
        horiz_m = distance(c.x, c.y, own.state.x, own.state.y) * NM_IN_M
        dist_m = math.hypot(horiz_m, c.depth - own.state.depth)
        own.apply_explosion(dist_m, c.practice, world.rng)
    world.charges = remaining


# ---------------------------------------------------------------------- torpeder
def launch_torpedo(world: World, spec: TorpedoSpec, course: float,
                   detonate_at_nm: float | None = None) -> Torpedo:
    o = world.own.state
    world.mission["torpedoes_fired"] = world.mission.get("torpedoes_fired", 0) + 1
    tid = f"T{world.mission['torpedoes_fired']}"
    t = Torpedo(tid, spec, o.x, o.y, course, world.time, detonate_at_nm)
    world.contacts.append(t)
    world.emit(Transient("launch", o.x, o.y, o.depth, acoustics.LAUNCH_LEVEL, world.own.id, world.time))
    return t


def launch_decoy(world: World) -> Decoy:
    o = world.own.state
    n = world.mission.get("decoys", 0) + 1
    world.mission["decoys"] = n
    d = Decoy(f"D{n}", o.x, o.y, o.depth, world.time + 600)
    world.contacts.append(d)
    return d


def _seek(world: World, t: Torpedo) -> None:
    """Passiv målsökare: låser på det starkaste fartyget inom konen."""
    best, best_se = None, 0.0
    ts = t.state
    for v in world.contacts:
        if v.side == "own" or v.sunk or not v.is_ship:
            continue
        rel = angle_diff(bearing_to(ts.x, ts.y, v.state.x, v.state.y), ts.course)
        if abs(rel) > t.spec.seeker_cone and t.locked != v.id:
            continue
        r = distance(ts.x, ts.y, v.state.x, v.state.y)
        se = v.radiated_level(world.env) - acoustics.transmission_loss(r, ts.depth, v.depth, world.env) \
            - t.spec.seeker_noise
        if se > best_se:
            best, best_se = v, se
    if best is not None:
        t.locked = best.id
        ts.order_course(bearing_to(ts.x, ts.y, best.state.x, best.state.y))


def _closest_approach(p0, p1, q) -> float:
    (x0, y0), (x1, y1), (qx, qy) = p0, p1, q
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((qx - x0) * dx + (qy - y0) * dy) / L2))
    return math.hypot(x0 + u * dx - qx, y0 + u * dy - qy)


def _detonate(world: World, t: Torpedo, target: Vessel | None) -> None:
    t.done = True
    t.sunk = True
    ts = t.state
    if t.spec.nuclear:
        world.emit(Transient("explosion", ts.x, ts.y, ts.depth, acoustics.EXPLOSION_NUCLEAR,
                             t.id, world.time))
        world.mission["nuclear_used"] = True
        for v in world.contacts:
            if v.side != "own" and v.is_ship and not v.sunk and \
                    distance(ts.x, ts.y, v.state.x, v.state.y) <= t.spec.kill_radius_nm:
                _sink(world, v)
        r_own = distance(ts.x, ts.y, world.own.state.x, world.own.state.y)
        if r_own < 0.6:
            world.own.apply_explosion(10.0, False, world.rng)
            world.own.sys.hull = 0.0
        elif r_own < 2.0:
            world.own.apply_explosion(20.0, False, world.rng)
        else:
            world.own.apply_explosion(400.0, False, world.rng)
        return
    world.emit(Transient("explosion", ts.x, ts.y, ts.depth, acoustics.EXPLOSION_TORPEDO,
                         t.id, world.time))
    if target is not None:
        _sink(world, target)


def _sink(world: World, v: Vessel) -> None:
    v.sunk = True
    v.state.order_speed(0)
    v.state.speed = 0.0
    world.emit(Transient("breakup", v.state.x, v.state.y, 20.0, acoustics.BREAKUP_LEVEL,
                         v.id, world.time))
    world.mission.setdefault("sunk", []).append(v.id)


def _step_torpedo(world: World, t: Torpedo, dt: int) -> None:
    ts = t.state
    if t.spec.homing and t.run_nm >= ARM_DISTANCE_NM:
        _seek(world, t)
    p0 = (ts.x, ts.y)
    ts.step(dt)
    cvx, cvy = world.env.current_at(ts.x, ts.y, world.time)
    ts.x += cvx * dt
    ts.y += cvy * dt
    t.run_nm += ts.speed * dt / 3600.0
    p1 = (ts.x, ts.y)

    if t.spec.nuclear:
        limit = t.detonate_at_nm if t.detonate_at_nm is not None else t.spec.range_nm
        if t.run_nm >= min(limit, t.spec.range_nm):
            _detonate(world, t, None)
        return

    if t.run_nm >= ARM_DISTANCE_NM:
        for v in world.contacts:
            if v.side == "own" or v.sunk or not v.is_ship:
                continue
            if _closest_approach(p0, p1, (v.state.x, v.state.y)) <= t.spec.kill_radius_nm:
                _detonate(world, t, v)
                return
    if t.run_nm >= t.spec.range_nm:
        t.done = True
        t.sunk = True


def step_weapons(world: World, dt: int) -> None:
    for v in list(world.contacts):
        if isinstance(v, Torpedo) and not v.done:
            _step_torpedo(world, v, dt)
        elif isinstance(v, Decoy) and not v.sunk and world.time >= v.expire_t:
            v.sunk = True
    _step_charges(world, dt)
