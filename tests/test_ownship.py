import random

import pytest

from sim import acoustics as ac
from sim.environment import Environment, Thermocline
from sim.ownship import TEST_DEPTH, OwnShip
from sim.ship import ShipState
from sim.world import World


def _world(**kw):
    own = OwnShip(ShipState(x=10, y=10, course=0, speed=kw.pop("speed", 5),
                            depth=kw.pop("depth", 100), max_depth=400))
    return World(own=own, env=Environment(), rng=random.Random(1))


def _run(w, n):
    for _ in range(n):
        w.tick()


def test_layer_adds_loss_only_across_it():
    env = Environment(profile=Thermocline(layer_depth=60, layer_loss=7))
    same = ac.transmission_loss(5, 5, 40, env)
    across = ac.transmission_loss(5, 5, 100, env)
    assert across - same == pytest.approx(7)


def test_cavitation_speed_grows_with_depth():
    assert ac.cavitation_speed(0) < ac.cavitation_speed(100) < ac.cavitation_speed(300)


def test_quiet_modes_and_cavitation():
    w = _world(speed=5)
    env, own = w.env, w.own
    turbine = own.radiated_level(env)
    own.set_propulsion("electric")
    electric = own.radiated_level(env)
    own.shutdown_reactor()
    silent = own.radiated_level(env)
    assert turbine > electric > silent
    own.sys.reactor = "online"
    own.set_propulsion("turbine")
    own.state.speed = 9.9
    below = own.radiated_level(env)
    own.state.speed = 10.1                     # cav-fart på 100 m är 10 kn
    assert own.radiated_level(env) - below > 10


def test_scram_limits_speed_and_drains_battery():
    w = _world(speed=12)
    w.own.state.order_speed(12)
    w.own.scram("test")
    _run(w, 600)
    assert w.own.sys.propulsion == "electric"
    assert w.own.state.speed <= 5.0
    assert w.own.sys.battery < 1.0
    assert w.own.start_reactor(w.time)
    _run(w, 1201)
    assert w.own.sys.reactor == "online"
    assert ("reactor.online", {}) in w.own.sys.alerts


def test_emergency_blow_surfaces():
    w = _world(depth=150, speed=3)
    assert w.own.emergency_blow()
    _run(w, 60)
    assert w.own.state.depth == 0
    assert not w.own.emergency_blow()          # högtrycksluften är slut


def test_below_test_depth_stresses_hull():
    w = _world(depth=TEST_DEPTH + 60)
    w.own.state.order_depth(TEST_DEPTH + 60)
    _run(w, 120)
    assert w.own.sys.hull < 1.0
    assert any(a[0] == "hull.creak" for a in w.own.sys.alerts)


def test_close_real_charge_damages_practice_does_not():
    w = _world()
    w.own.apply_explosion(15, practice=True, rng=w.rng)
    assert w.own.sys.hull == 1.0 and w.own.sys.leak_rate == 0
    w.own.apply_explosion(15, practice=False, rng=w.rng)
    assert w.own.sys.hull < 1.0 and w.own.sys.leak_rate > 0


def test_heavy_flooding_drags_boat_down():
    w = _world(depth=100, speed=3)
    w.own.sys.flooding = 60
    _run(w, 30)
    assert w.own.state.depth > 110
