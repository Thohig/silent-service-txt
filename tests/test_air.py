"""Ubåtsjaktflyg: radar, sonobojar, MAD, samarbete med jagaren och besättningens reaktioner."""
import random

from sim.air import (ALT_MAD_M, AirDef, Aircraft, AircraftAI, AirPatrol, Sonobuoy)
from sim.enemy import DestroyerAI
from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import PERISCOPE_DEPTH
from sim.scenario import build_scenario

SEEDS = range(1, 9)


def _game(seed=3):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    w.ais = [a for a in w.ais if isinstance(a, DestroyerAI)]
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _plane(g, dx=0.0, dy=0.0, leave_s=3600, seed=1):
    w, o = g.world, g.world.own.state
    p = Aircraft("P9", o.x + dx, o.y + dy, 90.0)
    ai = AircraftAI(p, random.Random(seed), w.size_nm, w.time + leave_s, (-10.0, 18.0))
    w.contacts.append(p)
    w.ais.append(ai)
    return p, ai


def _destroyer_far(g):
    dd = g.world.contacts[0]
    dd.state.x, dd.state.y = -30, -30
    return next(a for a in g.world.ais if isinstance(a, DestroyerAI))


def test_aircraft_and_buoys_are_silent_and_not_ships():
    g, _ = _game()
    p, _ = _plane(g, 1.0)
    b = Sonobuoy("B1", 0, 0, False, 10**6)
    assert not p.is_ship and not b.is_ship
    assert p not in g.world.enemy_ships
    assert p.radiated_level(g.world.env) < -900 and b.radiated_level(g.world.env) < -900


def test_radar_sees_a_surfaced_sub_but_not_a_deep_one():
    found_surface = found_deep = 0
    for seed in SEEDS:
        for surfaced, depth in ((True, 0.0), (False, 120.0)):
            g, _ = _game(seed)
            _destroyer_far(g)
            o = g.world.own.state
            o.depth = o.ordered_depth = depth
            p, ai = _plane(g, 8.0, seed=seed)
            for _ in range(60):
                ai._radar(g.world)
            if surfaced:
                found_surface += ai.found
            else:
                found_deep += ai.found
    assert found_surface == len(SEEDS) and found_deep == 0


def test_mad_finds_us_overhead_unless_we_are_deep():
    for depth, expect in ((100.0, True), (250.0, False)):
        g, _ = _game()
        _destroyer_far(g)
        o = g.world.own.state
        o.depth = depth
        p, ai = _plane(g)
        p.altitude = ALT_MAD_M
        ai._mad(g.world)
        assert ai.found == expect


def test_passive_buoy_hears_turbine_but_not_a_quiet_sub():
    heard = {"loud": 0, "quiet": 0}
    for seed in SEEDS:
        for mode in ("loud", "quiet"):
            g, _ = _game(seed)
            _destroyer_far(g)
            own = g.world.own
            o = own.state
            o.depth = o.ordered_depth = 40
            if mode == "loud":
                o.speed = o.ordered_speed = 14
            else:
                own.sys.propulsion = "electric"
                o.speed = o.ordered_speed = 3
            p, ai = _plane(g, 3.0, seed=seed)
            ai.buoys.append(Sonobuoy("B1", o.x + 0.8, o.y, False, 10**6))
            for _ in range(20):
                ai._listen(g.world)
            heard[mode] += ai.found
    assert heard["loud"] >= 6 and heard["quiet"] <= 2


def test_aircraft_takes_the_destroyers_datum_and_cues_it_back():
    g, _ = _game()
    w, o = g.world, g.world.own.state
    o.depth = o.ordered_depth = 80
    dd_ai = _destroyer_far(g)
    dd_ai.vessel.state.order_speed(0)
    dd_ai._set_datum(w, o.x + 0.3, o.y, 80.0, 0.6)
    p, ai = _plane(g, -6.0)
    for _ in range(600):
        g.tick()
        if ai.found:
            break
    assert ai.state == "prosecute"
    assert any(isinstance(v, Sonobuoy) for v in w.contacts)
    assert ai.found                                   # MAD eller boj har hittat oss
    d = dd_ai.datum
    assert abs(d.x - o.x) < 1.0 and abs(d.y - o.y) < 1.0


def test_crew_hears_flight_radar_and_suggests_going_down():
    g, reports = _game()
    _destroyer_far(g)
    o = g.world.own.state
    o.depth = o.ordered_depth = PERISCOPE_DEPTH - 2
    o.speed = o.ordered_speed = 4
    _plane(g, 6.0)
    for _ in range(40):
        g.tick()
    types = [r.type for r in reports]
    assert "off.esm.air" in types
    esm = next(r for r in reports if r.type == "off.esm.air")
    assert "flygradar" in esm.text and "P9" not in esm.text
    assert any(r.kind == "suggest" and r.data.get("order") == "djup 60" for r in reports)


def test_crew_hears_buoys_splash_and_active_pings():
    g, reports = _game()
    _destroyer_far(g)
    o = g.world.own.state
    o.depth = o.ordered_depth = 40
    p, ai = _plane(g, 3.0)
    ai._drop(g.world, o.x + 0.6, o.y, active=False)
    ai._drop(g.world, o.x - 0.5, o.y, active=True)
    for _ in range(90):
        g.tick()
    types = [r.type for r in reports]
    assert "sonar.buoy" in types and "sonar.buoy_ping" in types


def test_patrol_sends_planes_on_a_schedule_and_cleans_up():
    g, _ = _game()
    w = g.world
    patrol = AirPatrol(AirDef(first_s=(600, 600), on_station_s=(1200, 1200), gap_s=(900, 900)),
                       random.Random(1), area=w.size_nm)
    w.spawners.append(patrol)
    seen = set()
    for _ in range(3 * 3600):
        g.tick()
        seen |= {v.id for v in w.contacts if v.kind == "aircraft"}
    assert len(seen) >= 3
    assert sum(v.kind == "aircraft" for v in w.contacts) <= 1
    assert all(not v.sunk for v in w.contacts if v.kind == "sonobuoy")
