"""Kust och tidvatten: land, farled, bukt, tidvattenström och navigatörens tabell."""
import random

from sim.environment import Environment, TidalStream
from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import OwnShip
from sim.scenario import Scenario, _crew
from sim.seabed import strait_seabed
from sim.ship import ShipState
from sim.stations.navigation import NavigationStation
from sim.world import World


def _sb(seed=1):
    return strait_seabed(random.Random(seed), 14.0)


def test_strait_has_land_channel_bay_and_deep_sea():
    for seed in range(5):
        sb = _sb(seed)
        c = sb.features[0]
        assert sb.has_land
        assert sb.depth_at(c.channel_x, 2.0) > 1000                       # djuphav i söder
        assert sb.depth_at(c.channel_x - 2.0, c.shore_y + 1.0) <= 0       # land vid sidan
        for y in (c.shore_y, c.shore_y + 0.8, c.bay_y - 1.2):
            assert sb.depth_at(c.channel_x, y) >= 30                     # farleden
        assert 15 < sb.depth_at(c.bay_x, c.bay_y) < 35                    # bukten


def test_chart_copy_keeps_land():
    sb = _sb()
    chart = sb.chart_copy(random.Random(2), err_nm=0.3)
    c = chart.features[0]
    assert chart.has_land and chart.depth_at(c.channel_x - 2.0, c.shore_y + 1.0) <= 0


def test_tide_reverses_and_is_strongest_in_the_narrows():
    tide = TidalStream(flood_set=0.0, peak_kn=1.2, phase_s=0)
    assert tide.speed(0, 40) > 1.5                      # flod i farleden
    assert tide.speed(tide.period_s / 2, 40) < -1.5     # ebb
    assert abs(tide.speed(0, 2000)) < 0.5               # svagt ute på djupet
    assert tide.speed(0, -10) == 0.0                    # inte på land


def _world(sb, x, y, depth=30.0, speed=0.0, course=0.0, tide=None):
    env = Environment(current_kn=0.0, seabed=sb, tide=tide)
    own = OwnShip(ShipState(x=x, y=y, course=course, speed=speed, depth=depth, max_depth=400))
    return World(own=own, env=env, rng=random.Random(1), size_nm=14.0)


def test_tide_carries_a_stopped_sub_up_the_channel():
    sb = _sb()
    c = sb.features[0]
    tide = TidalStream(flood_set=0.0, peak_kn=1.2, phase_s=0)
    w = _world(sb, c.channel_x, c.shore_y + 0.3, depth=25.0, tide=tide)
    y0 = w.own.state.y
    for _ in range(600):
        w.tick()
    assert w.own.state.y - y0 > 0.2                    # > 1,2 kn i tio minuter


def test_running_onto_land_on_the_surface_is_a_grounding():
    sb = _sb()
    c = sb.features[0]
    x = c.channel_x - 1.5
    w = _world(sb, x, float(c.shore(x)) - 0.15, depth=0.0, speed=8.0, course=0.0)
    for _ in range(200):
        w.tick()
    assert w.own.sys.hull < 1.0
    assert sb.depth_at(w.own.state.x, w.own.state.y) > 0      # står kvar i vattnet


def _game(sb, x, y, depth=30.0, speed=5.0, course=0.0, tide=None, table=None):
    w = _world(sb, x, y, depth=depth, speed=speed, course=course, tide=tide)
    sc = Scenario(w, _crew(), "ORDER", 0, chart_seabed=sb, tide_table=table)
    return Game(sc, seed=1)


def test_navigator_dead_reckons_with_the_tide_table():
    sb = _sb()
    c = sb.features[0]
    tide = TidalStream(flood_set=0.0, peak_kn=1.2, phase_s=0)
    errs = {}
    for name, table in (("med", tide), ("utan", None)):
        g = _game(sb, c.channel_x, c.shore_y - 0.5, depth=30.0, speed=0.0, tide=tide,
                  table=table)
        for _ in range(900):
            g.tick()
        nav = g.station(NavigationStation)
        o = g.world.own.state
        errs[name] = abs(nav.est_y - o.y)
    assert errs["med"] < 0.05 < errs["utan"]


def test_tide_table_widens_the_uncertainty():
    sb = _sb()
    c = sb.features[0]
    tide = TidalStream(flood_set=0.0, peak_kn=1.2, phase_s=0)
    sig = {}
    for name, table in (("med", tide), ("utan", None)):
        g = _game(sb, c.channel_x, c.shore_y - 0.5, speed=0.0, tide=tide, table=table)
        for _ in range(600):
            g.tick()
        sig[name] = g.station(NavigationStation).uncertainty()
    assert sig["med"] > sig["utan"]


def test_navigator_warns_of_land_ahead_and_suggests_a_turn():
    sb = _sb()
    c = sb.features[0]
    x = c.channel_x - 2.0
    g = _game(sb, x, float(c.shore(x)) - 0.8, depth=30.0, speed=6.0, course=0.0)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append((e.report.type, e.report.text)))
    for _ in range(90):
        g.tick()
    land = [t for k, t in said if k == "nav.suggest.land"]
    assert land, said
    assert "Föreslår kurs" in land[0]
    order = g.suggestion[0] if g.suggestion else ""
    assert order.startswith("kurs")
    c2 = float(order.split()[1])
    assert not (c2 < 30 or c2 > 330)                    # inte rakt mot land


def test_chart_draws_land_and_coastline():
    sb = _sb()
    c = sb.features[0]
    g = _game(sb, c.channel_x, 3.0)
    items = g.chart().items if hasattr(g.chart(), "items") else g.chart()
    styles = {getattr(i, "style", None) for i in items}
    assert {"land", "coast"} <= styles


def test_fix_near_land_uses_landmarks_and_is_quick():
    sb = _sb()
    c = sb.features[0]
    g = _game(sb, c.channel_x, float(c.shore(c.channel_x)) - 2.0, depth=15.0, speed=3.0)
    g.world.env.clock_start = 12 * 3600
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    g.command("fix")
    for _ in range(40):
        g.tick()
    assert "nav.fix.done" in said
    assert g.station(NavigationStation).uncertainty() < 0.07
    # långt ute till havs: den vanliga fixen på två minuter
    g = _game(sb, c.channel_x, 0.5, depth=15.0, speed=3.0)
    g.world.env.clock_start = 12 * 3600
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    g.command("fix")
    for _ in range(40):
        g.tick()
    assert "nav.fix.done" not in said
