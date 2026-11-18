"""Arktis: drivstationen, huvudstabens position, målet och den amerikanska ubåten."""
import random

import pytest

from sim.arctic import STATION_LIGHT_NM, DriftStation, EnemySub, SubmarineAI
from sim.environment import ArcticProfile, Environment
from sim.events import PositionReported, ReportDelivered
from sim.game import Game
from sim.ice import IceField
from sim.ownship import OwnShip
from sim.scenario import build_scenario
from sim.ship import ShipState
from sim.stations import NavigationStation
from sim.world import World


def _game(seed=1):
    g = Game(build_scenario("arktis", random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _station(g):
    return next(v for v in g.world.contacts if v.kind == "station")


def _run(g, n):
    for _ in range(n):
        g.tick()


@pytest.mark.slow
def test_station_drifts_with_ice_and_is_not_a_ship():
    g, _ = _game()
    st = _station(g)
    assert not st.is_ship and st not in g.world.enemy_ships
    x0, y0 = st.state.x, st.state.y
    _run(g, 3600)
    ivx, ivy = g.world.env.ice.drift_velocity()
    assert abs(st.state.x - (x0 + ivx * 3600)) < 1e-6
    assert abs(st.state.y - (y0 + ivy * 3600)) < 1e-6


def test_known_position_from_the_order_and_radio():
    g, _ = _game()
    wp = g.knowledge.waypoints["Nord-7"]
    assert wp.source == "order" and wp.sigma0 == 2.0
    g.bus.publish(PositionReported(100, "Nord-7", 5.0, 6.0, 0.6, 100, "radio"))
    assert g.knowledge.waypoints["Nord-7"].source == "radio"
    # en sämre position ersätter inte en bättre
    g.bus.publish(PositionReported(110, "Nord-7", 1.0, 1.0, 3.0, 110, "radio"))
    assert g.knowledge.waypoints["Nord-7"].x == 5.0
    assert g.knowledge.waypoints["Nord-7"].sigma(3700) > 0.6


def test_station_order_steers_toward_waypoint():
    g, reports = _game()
    nav = g.station(NavigationStation)
    g.command("drivstationen")
    _run(g, 10)
    assert nav.goal == "station"
    wp = g.knowledge.waypoints["Nord-7"]
    from sim.geo import angle_diff, bearing_to
    want = bearing_to(nav.est_x, nav.est_y, wp.x, wp.y)
    assert abs(angle_diff(g.world.own.state.ordered_course, want)) < 2
    assert any(r.type == "nav.station.wp" for r in reports)


def test_periscope_sees_station_lights_and_reports_position():
    g, reports = _game()
    st, own = _station(g), g.world.own.state
    own.x, own.y = st.state.x, st.state.y - (STATION_LIGHT_NM - 0.5)
    g.world.env.ice.carve_polynya(own.x, own.y, 0.2)
    own.depth = 17.0
    own.order_depth(17)
    own.speed = 0.0
    own.order_speed(0)
    g.command("periskop")
    _run(g, 30)
    assert any(r.type == "off.periscope.station" for r in reports)
    assert g.knowledge.waypoints["Nord-7"].source == "periskop"


def test_surfacing_near_station_reaches_the_goal():
    g, _ = _game()
    st, own = _station(g), g.world.own.state
    own.x, own.y = st.state.x + 0.8, st.state.y
    g.world.env.ice.carve_polynya(own.x, own.y, 0.25)
    own.depth = own.ordered_depth = 0.0
    own.speed = 0.0
    own.order_speed(0)
    _run(g, 3)
    assert g.over and g.world.outcome["outcome"] == "station_reached"


def test_surfacing_far_from_station_does_not():
    g, _ = _game()
    own = g.world.own.state
    g.world.env.ice.carve_polynya(own.x, own.y, 0.25)
    own.depth = own.ordered_depth = 0.0
    own.speed = 0.0
    own.order_speed(0)
    _run(g, 30)
    assert not g.over


# --- den amerikanska ubåten ------------------------------------------------------------
def _sub_world(range_nm, own_speed, seed=1):
    ice = IceField(random.Random(seed), drift_kn=0.0)
    ice.thickness[:] = 3.0
    ice.draft[:] = 3.0
    ice.next_source_t = 10**9
    env = Environment(profile=ArcticProfile(), ice=ice, current_kn=0.0)
    own = OwnShip(ShipState(x=10, y=10, course=0, speed=own_speed, depth=150, max_depth=400))
    station = DriftStation("ST", 10, 18)
    us = EnemySub("SSN1", ShipState(x=10 + range_nm, y=10, course=0, speed=4, depth=150,
                                    max_speed=25, accel=0.05, turn_rate=1.5))
    w = World(own=own, contacts=[station, us], env=env, rng=random.Random(seed))
    ai = SubmarineAI(us, random.Random(seed), station)
    ai.state = "patrol"
    w.ais.append(ai)
    return w, ai


def test_us_sub_hears_noisy_boat_and_trails_without_forcing():
    trailed = 0
    for seed in range(1, 6):
        w, ai = _sub_world(1.5, 10, seed)
        w.own.state.order_speed(10)
        for _ in range(300):
            w.tick()
        trailed += ai.state == "trail"
        assert not ai.aware() or ai.can_force is False
    assert trailed >= 4


def test_us_sub_does_not_hear_quiet_boat_far_away():
    heard = 0
    for seed in range(1, 6):
        w, ai = _sub_world(5.0, 2, seed)
        w.own.set_propulsion("electric")
        w.own.state.order_speed(2)
        for _ in range(600):
            w.tick()
        heard += ai.state == "trail"
    assert heard <= 1


def test_surfacing_next_to_us_sub_is_not_forced():
    w, ai = _sub_world(1.0, 0)
    w.env.ice.carve_polynya(10, 10, 0.3)
    w.own.state.depth = w.own.state.ordered_depth = 0.0
    for _ in range(60):
        w.tick()
    assert w.outcome is None


def test_station_spiral_does_not_pull_us_down_while_surfacing():
    from sim.game import Game
    from sim.scenario import build_scenario
    from sim.stations.navigation import NavigationStation
    g = Game(build_scenario("arktis", random.Random(1)), seed=1)
    nav = g.station(NavigationStation)
    from sim.stations.navigation.tasks import Station as StationSteer
    nav.steer = StationSteer()
    nav._station_overhead = lambda: (1.0, 1.0)          # generatorn rakt ovanför
    g.world.own.state.order_depth(0)
    nav._steer_to_station(nav.steer)
    assert nav.goal == "station" and g.world.own.state.ordered_depth == 0


@pytest.mark.slow
def test_arctic_short_hands_over_near_the_station_with_the_fire_ahead():
    from sim.game import Game
    from sim.scenario import ARCTIC_SHORT_LIMIT_S, ARCTIC_SHORT_WARM_S, SCENARIOS, build_scenario
    assert SCENARIOS["arktis-kort"].minutes
    for seed in range(3):
        g = Game(build_scenario("arktis-kort", random.Random(seed)), seed=seed)
        w = g.world
        st = next(v for v in w.contacts if v.id == "NORD7")
        assert g.now == ARCTIC_SHORT_WARM_S and not g.over
        assert 1.6 < w.true_range(st) < 3.0
        assert 5 * 60 <= w.mission["fire_at"] - g.now <= 12 * 60
        assert w.patrol_end == ARCTIC_SHORT_WARM_S + ARCTIC_SHORT_LIMIT_S
        assert "Nord-7" in g.knowledge.waypoints
