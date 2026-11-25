"""Vrak på botten (sim/seabed.py Wreck): kortet, ekolodets fix, gömstället och jagarens eko."""
import random
from dataclasses import replace

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.seabed import WRECK_CLUTTER_DB, Wreck, bottom_clutter


def _game(key="jagad", seed=1):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_wrecks_lie_on_the_bank_and_most_are_on_the_chart():
    n = charted = 0
    for seed in range(1, 9):
        g, _ = _game(seed=seed)
        n += len(g.world.env.seabed.wrecks)
        charted += len(g.knowledge.bathymetry.wrecks)
        for w in g.world.env.seabed.wrecks:
            assert 30 < g.world.env.seabed.depth_at(w.x, w.y) <= 400
    assert n >= 12 and 0.5 * n <= charted < n
    assert any(name.startswith("vrak") for name in g.knowledge.waypoints)


def test_echo_sounder_over_a_charted_wreck_gives_a_fix():
    g, reports = _game()
    w = g.world.env.seabed.wrecks[0]
    chart = g.knowledge.bathymetry
    g.knowledge.bathymetry = replace(chart, wrecks=(replace(w, x=w.x + 0.05, y=w.y),))
    from sim.stations.navigation import NavigationStation
    nav = g.station(NavigationStation)
    o = g.world.own.state
    o.x, o.y = w.x, w.y
    nav.est_x, nav.est_y = w.x + 0.4, w.y - 0.2               # besticket fel
    g.command("ekolod")
    for _ in range(10):
        g.tick()
    r = next(r for r in reports if r.type == "nav.wreck")
    assert r.data["charted"] and "fix" in r.text
    assert abs(nav.est_x - (w.x + 0.05)) < 0.05 and abs(nav.est_y - w.y) < 0.05   # (sedan bestick några sekunder)


def test_an_uncharted_wreck_is_only_an_object():
    g, reports = _game()
    w = g.world.env.seabed.wrecks[0]
    g.knowledge.bathymetry = replace(g.knowledge.bathymetry, wrecks=())
    o = g.world.own.state
    o.x, o.y = w.x, w.y
    g.command("ekolod")
    for _ in range(10):
        g.tick()
    r = next(r for r in reports if r.type == "nav.wreck")
    assert not r.data["charted"] and "inte på kortet" in r.text


def test_lying_by_a_wreck_hides_the_echo():
    g, _ = _game()
    w = g.world.env.seabed.wrecks[0]
    own = g.world.own
    own.state.x, own.state.y = w.x + 0.3, w.y
    own.sys.on_bottom = True
    away = bottom_clutter(g.world, own)
    own.state.x = w.x + 0.02
    assert bottom_clutter(g.world, own) == away + WRECK_CLUTTER_DB


def test_the_navigator_suggests_hiding_by_a_wreck_when_hunted():
    g, reports = _game()
    from sim.stations.navigation import NavigationStation
    nav = g.station(NavigationStation)
    chart = g.knowledge.bathymetry
    w = Wreck(nav.est_x + 1.0, nav.est_y, 10.0, "tankfartyg, sänkt 1942")
    g.knowledge.bathymetry = replace(chart, wrecks=(w,))
    from sim.knowledge import Waypoint
    g.knowledge.waypoints = {"vraket": Waypoint("vraket", w.x, w.y, 0.1, 0, source="kortet")}
    g.knowledge.threat_held = lambda: True
    g.knowledge.hunted = lambda now: True
    g.knowledge.charged_close = lambda now, *a: False
    depth = chart.depth_at(w.x, w.y)
    p = nav._wreck_proposal()
    if depth <= min(200, nav.hull_depth()) and chart.bottom_type(w.x, w.y) != "klippa":
        assert p is not None and p.order == "kurs mot vraket"
        nav.est_x = w.x - 0.05
        assert nav._wreck_proposal().order == "botten"
    else:
        assert p is None
