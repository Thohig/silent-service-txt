"""Övningen (`ovning`): Kolafjorden, farleden, fixar från bryggan, land som skymmer."""
import math
import random

import pytest

from sim.environment import Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import OwnShip
from sim.scenario import build_scenario
from sim.seabed import ISLAND_CLEAR_NM, Seabed, kola_seabed
from sim.ship import ShipState
from sim.stations.navigation import NavigationStation
from sim.world import LAND_BLOCK_DB, World


def _game(seed=1):
    return Game(build_scenario("ovning", random.Random(seed)), seed=seed)


def test_fjord_is_water_with_land_on_both_sides_and_deep_sea_outside():
    for seed in range(8):
        sb = kola_seabed(random.Random(seed))
        f = sb.features[0]
        assert sb.has_land
        for (ax, ay), (bx, by) in zip(f.path, f.path[1:]):
            for t in (0.25, 0.5, 0.75):
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                if 0 <= y <= f.shore_y:
                    assert sb.depth_at(x, y) > 60, (seed, x, y)            # fjordens mitt
                    assert sb.depth_at(x - 2.0, y) <= 0                     # land väster
                    assert sb.depth_at(x + 2.5, y) <= 0                     # land öster
        mx = f.path[-1][0]
        assert sb.depth_at(mx, f.shore_y + 1.5) > 150                       # djupt utanför
        for ix, iy, r in f.islands:
            assert sb.depth_at(ix, iy) <= 0                                 # holmen är land
            hw, _, a = f._along(ix, iy)
            assert float(a) - r >= ISLAND_CLEAR_NM - 0.01                   # farleden fri


def test_in_fjord_only_inside_the_mouth():
    sb = kola_seabed(random.Random(3))
    f = sb.features[0]
    x, y = f.path[1]
    assert bool(f.in_fjord(x, y))
    assert not bool(f.in_fjord(f.path[-1][0], f.shore_y + 2.0))


def _world(sb, x, y, depth=0.0, speed=0.0, course=0.0):
    env = Environment(current_kn=0.0, seabed=sb)
    own = OwnShip(ShipState(x=x, y=y, course=course, speed=speed, depth=depth, max_depth=400))
    return World(own=own, env=env, rng=random.Random(1), size_nm=16.0)


def test_land_blocks_sound_and_sight():
    sb = kola_seabed(random.Random(1))
    f = sb.features[0]
    x, y = f.path[1]
    w = _world(sb, x, y)
    assert not w.land_between(x, y, x, y + 1.0)              # uppför fjorden
    assert w.land_between(x, y, x + 3.0, y)                  # genom berget
    assert w.in_sight(x, y + 1.0)
    assert not w.in_sight(x + 3.0, y)
    # samma avstånd, med och utan berg emellan
    assert w.land_between(x, y, x + 1.0, y)
    assert w.tl_to_own(x + 1.0, y, 5.0) - w.tl_to_own(x, y + 1.0, 5.0) > LAND_BLOCK_DB - 5


def test_no_land_no_blocking():
    sb = Seabed(base=2000.0)
    w = _world(sb, 5.0, 5.0)
    assert not w.land_between(0.0, 0.0, 10.0, 10.0)


def test_surfaced_sub_grounds_in_shallow_water():
    sb = Seabed(base=5.0, min_depth=1.0)
    w = _world(sb, 5.0, 5.0, depth=0.0, speed=4.0)
    for _ in range(10):
        w.tick()
    assert w.own.sys.bottom_contact


def test_start_on_the_surface_with_the_bridge_manned_and_a_fairway():
    for seed in range(4):
        g = _game(seed)
        own = g.world.own
        assert own.surfaced and own.sys.bridge == "manned"
        assert abs((own.state.course + 180) % 360 - 180) < 45          # ut mot havet (norrut)
        assert len(g.knowledge.fairway) >= 3
        assert g.knowledge.fairway_to in g.knowledge.waypoints
        f = g.world.env.seabed.features[0]
        assert bool(f.in_fjord(own.state.x, own.state.y))


def test_navigator_suggests_the_fairway_early():
    g = _game(2)
    seen = []
    g.bus.subscribe(ReportDelivered, lambda e: seen.append(e.report.data.get("order")))
    for _ in range(90):
        g.tick()
    assert "farleden" in seen


def test_fairway_order_steers_and_fixes_from_the_bridge():
    g = _game(1)
    nav = g.station(NavigationStation)
    g.command("farleden")
    for _ in range(400):
        g.tick()
    assert nav.goal == "fairway"
    assert nav.fixes                                       # pejlingar från bryggan
    assert nav.uncertainty() < 0.2
    o = g.world.own.state
    assert math.dist((nav.est_x, nav.est_y), (o.x, o.y)) < 0.25


def test_diving_in_the_fjord_is_warned_and_ends_the_exercise():
    g = _game(1)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    g.command("djup 40")
    for _ in range(120):
        g.tick()
        if g.over:
            break
    assert "nav.fjord_dive" in said
    assert g.world.outcome["outcome"] == "dived_in_fjord"


def test_training_officer_is_silent_without_a_programme():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    for _ in range(600):
        g.tick()
    assert not any(t.startswith("train.") for t in said)


def _yes_bot(seed, minutes):
    g = _game(seed)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    bot_t, closest = 0, 99.0
    for _ in range(minutes * 60):
        g.tick()
        o = g.world.own.state
        if g.world.own.surfaced:
            for v in g.world.neutral_ships:
                closest = min(closest, math.dist((o.x, o.y), (v.state.x, v.state.y)))
        if g.suggestion and g.suggestion[2] > bot_t:
            bot_t = g.suggestion[2]
            g.command("ja")
        if g.over:
            break
    return g, said, closest


@pytest.mark.slow
def test_yes_bot_gets_out_and_completes_the_programme():
    for seed in range(1, 5):
        g, said, closest = _yes_bot(seed, 110)
        assert g.world.outcome["outcome"] == "training_done", seed
        assert said.count("train.step.done") == 9, seed
        assert "train.done" in said, seed
        assert closest > 0.2, seed                    # inga fartyg nära i ytläge
        assert g.now < 100 * 60, seed


@pytest.mark.slow
def test_passive_captain_runs_aground_in_the_first_bend():
    g = _game(1)
    for _ in range(40 * 60):
        g.tick()
        if g.over:
            break
    assert g.world.outcome["outcome"] == "grounded"
