import random

import pytest

from sim.entities import Vessel
from sim.environment import Environment
from sim.firecontrol import intercept
from sim.geo import velocity
from sim.ownship import OwnShip
from sim.ship import ShipState
from sim.weapons import TORPEDO_TYPES, drop_charges, launch_torpedo
from sim.world import World


@pytest.fixture(autouse=True)
def _perfect(perfect_torpedoes):
    """Torpedfelen provas för sig (test_torpedo_faults.py)."""


def _world(target_course=90, target_speed=15, tx=6, ty=14):
    own = OwnShip(ShipState(x=10, y=10, course=0, speed=3, depth=60))
    dd = Vessel("DD1", "destroyer", ShipState(x=tx, y=ty, course=target_course,
                                              speed=target_speed))
    env = Environment(current_kn=0.0)
    return World(own=own, contacts=[dd], env=env, rng=random.Random(2)), dd


def _fire(w, dd, key, course_offset=0.0):
    spec = TORPEDO_TYPES[key]
    vx, vy = velocity(dd.state.course, dd.state.speed)
    sol = intercept(dd.state.x - w.own.state.x, dd.state.y - w.own.state.y,
                    vx * 3600, vy * 3600, spec.speed)
    assert sol is not None
    return launch_torpedo(w, spec, sol[0] + course_offset), sol


def _run(w, n):
    for _ in range(n):
        w.tick()


def test_intercept_head_on():
    course, t = intercept(0, 4, 0, 0, 40)
    assert round(course) == 0 and abs(t - 0.1) < 1e-9


def test_straight_torpedo_with_true_solution_hits():
    w, dd = _world()
    _fire(w, dd, "53-61")
    _run(w, 900)
    assert dd.sunk
    assert w.mission["sunk"] == ["DD1"]


def test_straight_torpedo_with_bad_solution_misses():
    w, dd = _world()
    _fire(w, dd, "53-61", course_offset=8)
    _run(w, 900)
    assert not dd.sunk


def test_homing_torpedo_corrects_a_bad_solution():
    for off in (-10, 10):
        w, dd = _world(target_speed=10, tx=8, ty=12.5)
        t, _ = _fire(w, dd, "SET-53", course_offset=off)
        _run(w, 900)
        assert t.locked == "DD1" and dd.sunk
        w2, dd2 = _world(target_speed=10, tx=8, ty=12.5)
        _fire(w2, dd2, "53-61", course_offset=off)
        _run(w2, 900)
        assert not dd2.sunk          # den raka torpeden missar med samma fel


def test_nuclear_torpedo_kills_wide_and_hurts_own_boat_if_close():
    w, dd = _world(target_speed=10, tx=9, ty=11.6)
    t, sol = _fire(w, dd, "T-5", course_offset=25)       # dåligt sikte spelar ingen roll
    t.detonate_at_nm = sol[1] * 40
    _run(w, 300)
    assert dd.sunk
    assert w.own.sys.hull < 1.0


def test_depth_charges_explode_at_set_depth():
    w, dd = _world()
    drop_charges(w, dd, w.own.state.x, w.own.state.y, w.own.state.depth, n=3, practice=False,
                 spread_nm=0.0, depth_spread=0.0)
    _run(w, 30)
    assert w.mission["charges_exploded"] == 3
    assert w.own.sys.hull < 1.0
