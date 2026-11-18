"""Lotsen: fienderna och trafiken går inte på land, men fria kurser lämnas i fred."""
import random

import pytest

from sim.entities import Vessel
from sim.environment import Environment
from sim.geo import bearing_to
from sim.ownship import OwnShip
from sim.pilotage import SURFACE_KEEL_M, clear_course, steer_clear
from sim.seabed import kola_seabed, kuba_seabed, strait_seabed
from sim.ship import ShipState
from sim.world import World


class _Toward:
    """En AI som envist styr mot en punkt (som en jagare mot ett datum på stranden)."""

    def __init__(self, v, x, y):
        self.v, self.x, self.y = v, x, y

    def step(self, world):
        s = self.v.state
        s.order_course(bearing_to(s.x, s.y, self.x, self.y))


def _world(sb, own_xy=(1.0, 1.0), size=14.0):
    own = OwnShip(ShipState(x=own_xy[0], y=own_xy[1], course=0, speed=0, depth=100, max_depth=400))
    return World(own=own, env=Environment(current_kn=0.0, seabed=sb), rng=random.Random(1),
                 size_nm=size)


def _ship(world, kind, x, y, course, speed):
    v = Vessel(kind, kind, ShipState(x=x, y=y, course=course, speed=speed, max_speed=30),
               side="enemy")
    world.contacts.append(v)
    return v


def _shallowest(world, v, minutes):
    sb = world.env.seabed
    least = 1e9
    for t in range(minutes * 60):
        world.tick()
        if t % 5 == 0:
            least = min(least, sb.depth_at(v.state.x, v.state.y))
    return least


@pytest.mark.slow
def test_hunter_chasing_a_datum_ashore_stays_afloat():
    """Patrullbåten jagar en punkt inne på land i sundet: den går längs stranden, aldrig upp."""
    for seed in range(4):
        sb = strait_seabed(random.Random(seed), 14.0)
        c = sb.features[0]
        w = _world(sb)
        land = (c.channel_x - 2.0, c.shore_y + 1.0)
        assert sb.depth_at(*land) <= 0
        v = _ship(w, "patrol", c.channel_x - 2.0, c.shore_y - 2.0, 0.0, 22.0)
        w.ais.append(_Toward(v, *land))
        assert _shallowest(w, v, 20) >= SURFACE_KEEL_M * 0.5


@pytest.mark.slow
def test_ship_running_straight_at_the_fjord_side_turns_away():
    """Utan någon AI alls: fartyget på rak kurs mot fjordens strand girar och går inte upp."""
    for seed in range(4):
        sb = kola_seabed(random.Random(seed), 16.0)
        fj = sb.features[0]
        (x0, y0) = fj.path[1]
        w = _world(sb, size=16.0)
        v = _ship(w, "merchant", x0, y0, 90.0, 12.0)              # tvärs över fjorden
        assert _shallowest(w, v, 20) >= SURFACE_KEEL_M * 0.5


def test_course_at_the_shore_is_replaced_by_a_free_one():
    sb = strait_seabed(random.Random(0), 14.0)
    c = sb.features[0]
    w = _world(sb)
    v = _ship(w, "destroyer", c.channel_x - 2.0, c.shore_y - 0.6, 0.0, 20.0)   # rakt mot land
    new = clear_course(w, v)
    assert new is not None and new != 0.0
    v.state.order_course(new)
    assert clear_course(w, v) is None                            # vägen dit är fri


def test_free_course_is_left_alone():
    sb = strait_seabed(random.Random(0), 14.0)
    c = sb.features[0]
    w = _world(sb)
    v = _ship(w, "merchant", c.channel_x, 1.0, 180.0, 12.0)      # ut mot djuphavet
    assert clear_course(w, v) is None
    steer_clear(w)
    assert v.state.ordered_course == 180.0


def test_nothing_happens_without_land():
    sb = kuba_seabed(random.Random(0), (10.0, 10.0), 20.0)
    assert not sb.has_land
    w = _world(sb, size=20.0)
    v = _ship(w, "destroyer", 10.0, 10.0, 45.0, 20.0)
    steer_clear(w)
    assert v.state.ordered_course == 45.0


def test_own_boat_and_moored_ships_are_not_steered():
    sb = strait_seabed(random.Random(0), 14.0)
    c = sb.features[0]
    w = _world(sb, own_xy=(c.channel_x - 2.0, c.shore_y - 0.3))
    w.own.state.order_course(0.0)
    w.own.state.order_speed(10.0)
    m = _ship(w, "moored", c.channel_x + 2.0, c.shore_y - 0.3, 0.0, 0.0)
    m.kind = "moored"
    steer_clear(w)
    assert w.own.state.ordered_course == 0.0 and m.state.ordered_course == 0.0
