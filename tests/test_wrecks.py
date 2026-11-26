"""Vrak på botten (sim/seabed.py Wreck): kortet, ekolodets fix, gömstället och jagarens eko."""
import random

import pytest
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


@pytest.mark.slow
def test_the_wreck_is_not_suggested_through_the_shallows():
    """sundet-in frö 22 (ja-boten): "kurs mot vrak 1" gick genom grundet, och navigatören vände oss bort
    en halv minut senare (nav.suggest.land), två gånger. Vägen till vraket ska vara fri på kortet."""
    from sim.stations.navigation import NavigationStation
    g = Game(build_scenario("sundet-in", random.Random(22)), seed=22)
    nav = g.station(NavigationStation)
    start = g.now
    seen = []
    g.bus.subscribe(ReportDelivered, lambda e: seen.append((g.now, e.report.type)))
    for _ in range(36 * 60):
        g.tick()
        if g.over:
            break
        if g.active_suggestion() and (g.now - start) % 15 == 0:
            g.command("ja")
    wrecks = [t for t, ty in seen if ty == "nav.suggest.wreck"]
    lands = [t for t, ty in seen if ty == "nav.suggest.land"]
    assert not any(0 <= lt - wt <= 120 for wt in wrecks for lt in lands)


def test_shoal_in_the_depth_ack_says_ahead_when_it_is_ahead():
    """"Kortet visar botten på cirka 20 meter här" gällde grundet framåt (sundet-in frö 22)."""
    from sim import phrases
    ack = phrases.PHRASES["nav.depth.ack"]
    assert "20 meter här" in ack({"depth": 18, "below_test": False, "shoal": 20, "shoal_nm": 0.0})
    assert "0,8 sjömil framåt" in ack({"depth": 18, "below_test": False, "shoal": 20, "shoal_nm": 0.8})
