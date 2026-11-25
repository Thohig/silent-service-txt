"""Kollision med fartyg och ramning (sim/collision.py, DestroyerAI._ram, sonars stående bäring)."""
import random

import pytest

from sim import collision as C
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario

NM = 1852.0


def _setup(kind="destroyer", speed=12.0, depth=17.0, offset_m=23.0, own_speed=0.0, ai=False):
    """Fartyget 1 nm söder om oss på kurs 000; vi ligger på kurs 090 (tornet 17–30 m öster om mitten)."""
    g = Game(build_scenario("kuba", random.Random(2)), seed=2)
    w = g.world
    w.spawners.clear()
    v = next(x for x in w.contacts if x.kind == kind)
    w.contacts = [v]
    w.ais = [a for a in w.ais if getattr(a, "vessel", None) is v]
    if not ai:
        for a in w.ais:
            a.step = lambda world: None
    o = w.own.state
    o.depth = o.ordered_depth = depth
    o.speed = o.ordered_speed = own_speed
    o.course = o.ordered_course = 90
    v.state.x, v.state.y = o.x + offset_m / NM, o.y - 1.0
    v.state.course = v.state.ordered_course = 0
    v.state.speed = v.state.ordered_speed = speed
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, v, reports


def _run(g, n):
    for _ in range(n):
        if g.over:
            break
        g.tick()


def test_a_ship_over_the_sail_hits_it_from_above():
    g, v, reports = _setup()
    _run(g, 400)
    hits = g.world.mission.get("collisions")
    assert hits and len(hits) == 1 and hits[0][2] == "sail"
    s = g.world.own.sys
    assert s.health["periscope"] < 0.5 and s.health["radio"] < 0.5
    r = next(r for r in reports if r.type == "collision")
    assert r.alarm and "tornet" in r.text and "DD" not in r.text


def test_a_ship_over_the_middle_misses_the_sail_and_deep_misses_all():
    g, v, _ = _setup(offset_m=0.0)                       # tornet sitter förut: kölen går över mittskeppet
    _run(g, 400)
    assert not g.world.mission.get("collisions")
    g, v, _ = _setup(depth=40.0)                         # under kölen
    _run(g, 400)
    assert not g.world.mission.get("collisions")


def test_sonar_hears_a_steady_bearing_and_rising_screws_and_says_go_down():
    g, v, reports = _setup()
    _run(g, 260)
    sug = [r for r in reports if r.type == "sonar.collision_course"]
    assert sug and sug[0].alarm and sug[0].data["order"] == "djup 40"
    g.command("ja")
    _run(g, 200)
    assert not g.world.mission.get("collisions")         # under hans köl


def test_a_passing_ship_brings_no_collision_warning():
    g, v, reports = _setup(offset_m=400.0)
    _run(g, 400)
    assert not [r for r in reports if r.type == "sonar.collision_course"]


def test_rammed_on_the_surface_at_speed_breaks_the_hull():
    g, v, reports = _setup(speed=25.0, depth=4.0, offset_m=0.0)     # i ytläge vore spelet slut (sedda)
    _run(g, 200)
    hit = g.world.mission["collisions"][0]
    assert hit[2] == "hull" and hit[3] >= C.REL_CRACK_KN
    s = g.world.own.sys
    assert s.hull <= 0.55 and any(lk.kind == "spricka" for lk in s.dmg.leaks)
    assert any(r.type == "collision" and "rammade" in r.text for r in reports)


def test_the_destroyer_rams_a_submarine_it_sees_shallow():
    g, v, reports = _setup(depth=4.0, offset_m=300.0, speed=10.0, ai=True)
    ai = g.world.ais[0]
    ai.roe = "lethal"
    st = g.world.own.state
    ai._set_datum(g.world, st.x, st.y, st.depth, 0.05, fix=True)
    ai.last_contact_t = g.now
    ai.state = "attack"
    rammed = False
    for _ in range(400):
        ai.last_contact_t = g.now                        # han ser tornet hela tiden
        ai._set_datum(g.world, st.x, st.y, st.depth, 0.05, fix=True)
        g.tick()
        rammed = rammed or ai.ramming(g.now)
        if g.world.mission.get("collisions") or g.over:
            break
    assert rammed and v.state.speed > 25                 # full fart rakt på (sedan backar han ur)
    assert g.world.mission.get("collisions")


def test_the_destroyer_does_not_ram_in_peacetime_or_a_deep_submarine():
    g, v, _ = _setup(depth=4.0, offset_m=300.0, speed=10.0, ai=True)
    ai = g.world.ais[0]
    st = g.world.own.state
    ai._set_datum(g.world, st.x, st.y, st.depth, 0.05, fix=True)
    ai.last_contact_t = g.now
    assert ai.roe == "signal" and not ai._ram(g.world)
    ai.roe = "lethal"
    ai._set_datum(g.world, st.x, st.y, 100.0, 0.05, fix=True)
    assert not ai._ram(g.world)


def test_two_submarines_at_the_same_depth_collide():
    from sim.entities import Vessel
    from sim.ship import ShipState
    g, v, _ = _setup()
    o = g.world.own.state
    sub = Vessel("SS9", "submarine", ShipState(x=o.x - 0.2, y=o.y, course=90, speed=8, depth=100,
                                               max_depth=300))
    sub.state.ordered_speed, sub.state.ordered_course, sub.state.ordered_depth = 8, 90, 100
    o.depth = o.ordered_depth = 100
    o.course = o.ordered_course = 90
    g.world.contacts = [sub]
    g.world.ais = []
    _run(g, 120)
    hit = g.world.mission["collisions"][0]
    assert hit[2] == "hull"
