"""Vapen i sanningslagret: sjunkbomber, torpeder och skenmål.

Torpeder är fartyg i världen (kind="torpedo") som rör sig själva.
Träff avgörs geometriskt: närmaste passage under ett tidssteg mot målet.

Fiendens torpeder (side="enemy", `launch_enemy_torpedo`, amerikanska Mk 37) söker mot oss och
våra skenmål: passivt mot det som låter mest i konen, aktivt nära (`active_nm`) och bara i ett
band i höjd (`ACTIVE_DEPTH_M`), där skrovet ekar och skenmålets bubbelmoln ekar mer. En låsning hålls tills något annat hörs klart bättre
(`RELOCK_DB`); ett skenmål som torpeden passerat bortser den från. En träff på oss är förlusten.

Egna torpeder träffar bara inom `DEPTH_HIT_M` i djup: en rak torped på 5 m går över en ubåt på
djupet, målsökarna styr också i djup mot det de låst på. Alla torpeder går på grund mot land och
grund (`_ground`): en armerad stridsspets detonerar där.
Trådstyrda torpeder (`wire_nm` > 0, försökstorpeden 53-62T): torpedrummet styr dem med
`guide_torpedo` medan tråden håller och släpper målsökaren (`release_seeker`) nära målet; förut
söker de inte. Tråden går av (`_step_wire`) när den är utspelad, när vi går fortare än
`WIRE_MAX_SPEED` en stund eller girar mer än `WIRE_MAX_TURN` från kursen vid skottet, och ibland av
sig själv. Då går torpeden vidare på sin kurs med målsökaren till.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import acoustics
from .entities import Transient, Vessel
from .geo import NM_IN_M, angle_diff, bearing_to, distance, norm360
from .geo import velocity as _vel
from .ship import ShipState

if TYPE_CHECKING:
    from .world import World

SINK_RATE = 3.5              # m/s för sjunkbomber
ARM_DISTANCE_NM = 0.25       # torpeden armeras efter denna sträcka
HIT_RADIUS_NM = 0.03         # ~55 m: fiendens målsökande torped mot oss
# Skrovet som träffyta för våra torpeder: en ellips med halva längden och halva bredden (meter), plus
# FUZE_M för pistolen och torpedens egen bredd. Rakt för- eller akterifrån är en jagare ~30 m bred att
# träffa, från sidan ~130 m.
HULL_M = {
    "destroyer": (57.0, 6.0), "merchant": (70.0, 9.0), "transport": (85.0, 11.0),
    "tanker": (92.0, 12.0), "patrol": (30.0, 4.0), "guardship": (45.0, 5.0),
    "submarine": (50.0, 5.0), "ssbn": (65.0, 5.0), "fishing": (20.0, 4.0), "spytrawler": (25.0, 5.0), "foxtrot": (45.0, 4.0),
    "moored": (70.0, 9.0),
}
HULL_DEFAULT_M = (60.0, 8.0)
FUZE_M = 10.0


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
    kill_radius_nm: float = 0.0  # kärnladdningen: sänker allt inom så här långt (andra: skrovets ellips)
    seeker_cone: float = 35.0
    seeker_noise: float = 70.0
    exercise: bool = False    # övningstorped: ingen stridsspets, går under målet
    active_nm: float = 0.0    # aktiv målsökare: hittar ett skrov så här nära (ekot)
    wire_nm: float = 0.0      # trådstyrd: så lång tråd (sjömil); målsökaren släpps av torpedrummet


TORPEDO_TYPES: dict[str, TorpedoSpec] = {
    "53-61": TorpedoSpec("53-61", "53-61 (rak)", speed=45, range_nm=8.0, source_level=155),
    "SET-53": TorpedoSpec("SET-53", "SET-53 (målsökande)", speed=23, range_nm=4.0,
                          homing=True, source_level=130),
    "övning": TorpedoSpec("övning", "53-61 övningstorped (utan stridsspets)", speed=45,
                          range_nm=8.0, source_level=155, run_depth=12.0, exercise=True),
    "T-5": TorpedoSpec("T-5", "T-5 (kärnladdning)", speed=40, range_nm=5.5, nuclear=True,
                       source_level=150, kill_radius_nm=1.0),
    # Försökstorpeden: elektrisk, trådstyrd, passiv målsökare som släpps nära målet. Trådstyrda
    # torpeder kom i sovjetisk tjänst först i slutet av 60-talet; här är den ett försöksexemplar.
    "53-62T": TorpedoSpec("53-62T", "53-62T (trådstyrd, försök)", speed=35, range_nm=7.0,
                          homing=True, source_level=140, wire_nm=5.5),
}
# Amerikanska ubåtens torped (Mk 37, 1960): elektrisk, långsam, passiv och aktiv målsökning.
MK37 = TorpedoSpec("Mk37", "Mk 37 (målsökande)", speed=26, range_nm=5.0, homing=True,
                   source_level=145, seeker_cone=40.0, seeker_noise=72.0, active_nm=0.4)
ACTIVE_ECHO_SE = 15.0        # ett skrov inom aktiva räckvidden: så tydligt eko
DECOY_ECHO_SE = 18.0         # skenmålets gasbubblor ekar mer än skrovet
ACTIVE_DEPTH_M = 50.0        # den aktiva målsökaren ser bara så långt upp och ned
RELOCK_DB = 6.0              # något annat måste höras så mycket bättre för att byta mål
DEPTH_HIT_M = 20.0           # träff bara om djupet stämmer så här nära (alla torpeder)
GROUND_MARGIN_M = 1.0        # botten så här mycket grundare än torpedens djup: den går på grund
TORPEDO_HIT_HULL = 0.7       # en Mk 37 i skrovet: tillsammans med tryckvågen är det slutet
WIRE_MAX_SPEED = 12.0        # knop: fortare och tråden slits av mot skrovet ...
WIRE_OVERSPEED_S = 15        # ... efter så här lång tid
WIRE_MAX_TURN = 90.0         # grader från skjutkursen: tråden hamnar i propellern
WIRE_FAIL_PER_S = 1 / 6000   # tråden går av av sig själv (skarvar, isolering): ~1 % per minut
# Egna torpeder är inte perfekta. Gyrot lägger torpeden på kursen med ett litet fel (en rak torped går
# ~40 m vid sidan på 3 nm), och stridsspetsen klickar ibland eller går av för tidigt (magnetpistolen).
GYRO_SIGMA_DEG = 0.4
DUD_P = 0.05                 # träffar skrovet utan att detonera
PREMATURE_P = 0.02           # detonerar på vägen, efter armeringen



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
                 launch_t: int, detonate_at_nm: float | None = None, side: str = "own",
                 depth: float | None = None):
        state = ShipState(x=x, y=y, course=course, speed=spec.speed,
                          depth=spec.run_depth if depth is None else depth,
                          turn_rate=3.0, max_speed=spec.speed, depth_rate=2.0, max_depth=450)
        super().__init__(id=id, kind="torpedo", state=state, side=side)
        self.spec = spec
        self.launch_t = launch_t
        self.launch_xy = (x, y)
        self.run_nm = 0.0
        self.locked: str | None = None
        self.detonate_at_nm = detonate_at_nm
        self.done = False
        self.passed: dict[str, float] = {}   # övningstorped: närmaste passage per fartyg (nm)
        self.under: dict[str, float] = {}    # ... och genom skrovets ellips (≤ 1: under kölen)
        self.locked_se = 0.0
        self.ignored: set[str] = set()       # skenmål som torpeden gått förbi
        self.wire_ok = spec.wire_nm > 0      # trådstyrd: tråden håller
        self.seeker_on = spec.wire_nm <= 0   # trådstyrd: målsökaren släpps av torpedrummet
        self.overspeed_s = 0
        self.wire_course = course            # vår kurs vid avfyringen: giren räknas därifrån
        self.dud = False                     # stridsspetsen klickar vid träff
        self.premature_nm: float | None = None   # går av för tidigt efter så här lång gång

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
        if not c.practice:      # skarpa: det stabens villkorade tillstånd för T-5 talar om
            world.mission["real_charges"] = world.mission.get("real_charges", 0) + 1
        horiz_m = distance(c.x, c.y, own.state.x, own.state.y) * NM_IN_M
        dist_m = math.hypot(horiz_m, c.depth - own.state.depth)
        world.mission.setdefault("charge_log", []).append((world.time, c.practice, round(dist_m)))
        own.apply_explosion(dist_m, c.practice, world.rng, src=(c.x, c.y))
    world.charges = remaining


# ---------------------------------------------------------------------- torpeder
def launch_torpedo(world: World, spec: TorpedoSpec, course: float,
                   detonate_at_nm: float | None = None) -> Torpedo:
    o = world.own.state
    world.mission["torpedoes_fired"] = world.mission.get("torpedoes_fired", 0) + 1
    world.own.sys.trim.torpedo_fired()           # fören lättare: trimmarens sak
    tid = f"T{world.mission['torpedoes_fired']}"
    rng = world.rng
    course = norm360(course + rng.gauss(0.0, GYRO_SIGMA_DEG))
    t = Torpedo(tid, spec, o.x, o.y, course, world.time, detonate_at_nm)
    t.wire_course = o.course
    if not spec.nuclear and not spec.exercise:
        t.dud = rng.random() < DUD_P
        if rng.random() < PREMATURE_P:
            t.premature_nm = rng.uniform(ARM_DISTANCE_NM, spec.range_nm)
    world.contacts.append(t)
    world.emit(Transient("launch", o.x, o.y, o.depth, acoustics.LAUNCH_LEVEL, world.own.id, world.time))
    return t


def guide_torpedo(t: Torpedo, course: float) -> bool:
    """Styrorder längs tråden. Går bara fram medan tråden håller."""
    if not t.wire_ok or t.done:
        return False
    t.state.order_course(course)
    return True


def release_seeker(t: Torpedo) -> None:
    """Målsökaren till (torpedrummet släpper den, eller tråden kapas)."""
    t.seeker_on = True


def cut_wire(t: Torpedo) -> None:
    t.wire_ok = False
    t.seeker_on = True


def _step_wire(world: World, t: Torpedo, dt: int) -> None:
    """Tråden mellan oss och torpeden: utspelad, sliten av farten, i propellern, eller av sig själv."""
    own = world.own.state
    if world.own.sunk or t.run_nm >= t.spec.wire_nm:
        cut_wire(t)
        return
    t.overspeed_s = t.overspeed_s + dt if own.speed > WIRE_MAX_SPEED else 0
    if t.overspeed_s >= WIRE_OVERSPEED_S or abs(angle_diff(own.course, t.wire_course)) > WIRE_MAX_TURN \
            or world.rng.random() < WIRE_FAIL_PER_S * dt:
        cut_wire(t)


def launch_decoy(world: World) -> Decoy:
    o = world.own.state
    n = world.mission.get("decoys", 0) + 1
    world.mission["decoys"] = n
    world.own.sys.trim.decoy_launched()
    d = Decoy(f"D{n}", o.x, o.y, o.depth, world.time + 600)
    world.contacts.append(d)
    return d


def lead_course(sx: float, sy: float, tx: float, ty: float, t_course: float, t_speed: float,
                speed: float) -> float:
    """Kursen som möter ett mål på rak kurs (förhållning). Går det inte: rakt mot målet."""
    vx, vy = _vel(t_course, t_speed)              # sjömil per sekund
    dx, dy = tx - sx, ty - sy
    s = speed / 3600.0
    a = vx * vx + vy * vy - s * s
    b = 2 * (dx * vx + dy * vy)
    c = dx * dx + dy * dy
    disc = b * b - 4 * a * c
    if abs(a) < 1e-12 or disc < 0:
        return bearing_to(sx, sy, tx, ty)
    roots = [r for r in ((-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a)) if r > 0]
    if not roots:
        return bearing_to(sx, sy, tx, ty)
    t = min(roots)
    return bearing_to(sx, sy, tx + vx * t, ty + vy * t)


def launch_enemy_torpedo(world: World, shooter: Vessel, spec: TorpedoSpec, course: float,
                         depth: float) -> Torpedo:
    """Fienden skjuter mot oss: torpeden går ut i kursen på djupet och söker själv."""
    s = shooter.state
    n = world.mission.get("enemy_torpedoes", 0) + 1
    world.mission["enemy_torpedoes"] = n
    t = Torpedo(f"E{n}", spec, s.x, s.y, course, world.time, side="enemy", depth=depth)
    world.contacts.append(t)
    world.emit(Transient("launch", s.x, s.y, s.depth, acoustics.LAUNCH_LEVEL, shooter.id, world.time))
    return t


def _enemy_targets(world: World, t: Torpedo) -> list[Vessel]:
    """Det en fiendetorped kan söka mot: vi och våra skenmål (inte de den gått förbi)."""
    out: list[Vessel] = [] if world.own.sunk else [world.own]
    out += [v for v in world.contacts if isinstance(v, Decoy) and not v.sunk
            and v.id not in t.ignored]
    return out


def _seek_enemy(world: World, t: Torpedo) -> None:
    ts = t.state
    best, best_se = None, 0.0
    for v in _enemy_targets(world, t):
        rel = angle_diff(bearing_to(ts.x, ts.y, v.state.x, v.state.y), ts.course)
        if abs(rel) > t.spec.seeker_cone and t.locked != v.id:
            continue
        r = distance(ts.x, ts.y, v.state.x, v.state.y)
        se = v.radiated_level(world.env) - acoustics.transmission_loss(r, ts.depth, v.depth, world.env) \
            - t.spec.seeker_noise
        if r <= t.spec.active_nm and abs(v.depth - ts.depth) <= ACTIVE_DEPTH_M:
            # ekot: skrovet, eller skenmålets bubbelmoln (som ekar mer)
            se = max(se, DECOY_ECHO_SE if isinstance(v, Decoy) else ACTIVE_ECHO_SE)
        if v.id == t.locked:
            se += RELOCK_DB                         # låsningen hålls
        if se > best_se:
            best, best_se = v, se
    if best is None:
        t.locked = None
        return
    t.locked, t.locked_se = best.id, best_se
    ts.order_course(bearing_to(ts.x, ts.y, best.state.x, best.state.y))
    ts.order_depth(best.depth)
    if isinstance(best, Decoy) and distance(ts.x, ts.y, best.state.x, best.state.y) < 0.03:
        t.ignored.add(best.id)                      # förbi skenmålet: sök vidare
        t.locked = None


def _seek(world: World, t: Torpedo) -> None:
    """Passiv målsökare: låser på det starkaste fartyget inom konen."""
    if t.side == "enemy":
        _seek_enemy(world, t)
        return
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
        ts.order_depth(max(best.depth, t.spec.run_depth))   # efter en ubåt nedåt, aldrig över ytläget


def hull_pass(p0, p1, v: Vessel) -> float:
    """Torpedens närmaste passage genom skrovets ellips, i ellipsens mått: ≤ 1 är träff. Banan p0 → p1
    räknas om till fartygets egna axlar (längs och tvärs), skalade med halva längden och bredden."""
    half_len, half_beam = HULL_M.get(v.kind, HULL_DEFAULT_M)
    a = (half_len + FUZE_M) / NM_IN_M
    b = (half_beam + FUZE_M) / NM_IN_M
    c = math.radians(v.state.course)
    fx, fy = math.sin(c), math.cos(c)               # för
    sx, sy = math.cos(c), -math.sin(c)              # styrbord

    def local(p):
        dx, dy = p[0] - v.state.x, p[1] - v.state.y
        return (dx * fx + dy * fy) / a, (dx * sx + dy * sy) / b

    return _closest_approach(local(p0), local(p1), (0.0, 0.0))


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
        world.mission.setdefault("nuclear_t", world.time)
        for v in world.contacts:
            if v.side != "own" and v.is_ship and not v.sunk and \
                    distance(ts.x, ts.y, v.state.x, v.state.y) <= t.spec.kill_radius_nm:
                _sink(world, v)
        r_own = distance(ts.x, ts.y, world.own.state.x, world.own.state.y)
        if r_own < 0.6:
            world.own.apply_explosion(10.0, False, world.rng, src=(ts.x, ts.y))
            world.own.sys.hull = 0.0
        elif r_own < 2.0:
            world.own.apply_explosion(20.0, False, world.rng, src=(ts.x, ts.y))
        else:
            world.own.apply_explosion(400.0, False, world.rng)
        return
    world.emit(Transient("explosion", ts.x, ts.y, ts.depth, acoustics.EXPLOSION_TORPEDO,
                         t.id, world.time))
    if target is not None:
        _sink(world, target)


def _dud(world: World, t: Torpedo, target: Vessel) -> None:
    """Torpeden slår i skrovet utan att detonera: en metallisk smäll, och målet går vidare."""
    t.done = True
    t.sunk = True
    ts = t.state
    world.emit(Transient("dud", ts.x, ts.y, ts.depth, acoustics.DUD_LEVEL, t.id, world.time))
    world.mission["duds"] = world.mission.get("duds", 0) + 1


def _sink(world: World, v: Vessel) -> None:
    v.sunk = True
    v.state.order_speed(0)
    v.state.speed = 0.0
    world.emit(Transient("breakup", v.state.x, v.state.y, 20.0, acoustics.BREAKUP_LEVEL,
                         v.id, world.time))
    world.mission.setdefault("sunk", []).append(v.id)
    world.mission["last_sink_t"] = world.time


def _ground(world: World, t: Torpedo) -> None:
    """Torpeden går upp på land eller ett grund: en armerad stridsspets detonerar där (ingen i
    närheten), annars (oarmerad, blindgångare, övningstorped) stannar den bara."""
    if t.run_nm >= ARM_DISTANCE_NM and not t.spec.exercise and not t.dud:
        _detonate(world, t, None)
    else:
        t.done = t.sunk = True


def _step_torpedo(world: World, t: Torpedo, dt: int) -> None:
    ts = t.state
    if t.wire_ok:
        _step_wire(world, t, dt)
    if t.spec.homing and t.seeker_on and t.run_nm >= ARM_DISTANCE_NM:
        _seek(world, t)
    p0 = (ts.x, ts.y)
    ts.step(dt)
    cvx, cvy = world.env.current_at(ts.x, ts.y, world.time)
    ts.x += cvx * dt
    ts.y += cvy * dt
    t.run_nm += ts.speed * dt / 3600.0
    p1 = (ts.x, ts.y)
    if world.env.bottom_at(ts.x, ts.y) < ts.depth - GROUND_MARGIN_M:
        _ground(world, t)
        return

    if t.spec.nuclear:
        limit = t.detonate_at_nm if t.detonate_at_nm is not None else t.spec.range_nm
        if t.run_nm >= min(limit, t.spec.range_nm):
            _detonate(world, t, None)
        return

    if t.spec.exercise:
        # ingen stridsspets: torpeden går under målet; vi noterar närmaste passage
        for v in world.contacts:
            if v.side == "own" or v.sunk or not v.is_ship:
                continue
            d = _closest_approach(p0, p1, (v.state.x, v.state.y))
            if d < t.passed.get(v.id, 9.9):
                t.passed[v.id] = d
            t.under[v.id] = min(t.under.get(v.id, 9.9), hull_pass(p0, p1, v))
    elif t.side == "enemy":
        own = world.own
        if t.run_nm >= ARM_DISTANCE_NM and not own.sunk and \
                abs(own.depth - ts.depth) <= DEPTH_HIT_M and \
                _closest_approach(p0, p1, (own.state.x, own.state.y)) <= HIT_RADIUS_NM:
            t.done = t.sunk = True
            world.emit(Transient("explosion", ts.x, ts.y, ts.depth, acoustics.EXPLOSION_TORPEDO,
                                 t.id, world.time))
            world.mission["hit_by_torpedo"] = world.time
            own.apply_explosion(5.0, False, world.rng, src=(ts.x, ts.y))
            own.sys.hull -= TORPEDO_HIT_HULL          # en träff är förlusten
            return
    elif t.premature_nm is not None and t.run_nm >= t.premature_nm:
        _detonate(world, t, None)                   # för tidigt: ingen i närheten
        return
    elif t.run_nm >= ARM_DISTANCE_NM:
        for v in world.contacts:
            if v.side == "own" or v.sunk or not v.is_ship:
                continue
            # en ubåt på djupet går den raka torpeden (5 m) över
            if abs(v.depth - ts.depth) > DEPTH_HIT_M:
                continue
            if hull_pass(p0, p1, v) <= 1.0:
                if t.dud:
                    _dud(world, t, v)
                else:
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
