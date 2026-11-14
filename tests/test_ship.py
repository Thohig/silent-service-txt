import pytest

from sim.geo import angle_diff, bearing_to, norm360
from sim.ship import ShipState


def test_angle_helpers():
    assert angle_diff(10, 350) == pytest.approx(20)
    assert angle_diff(350, 10) == pytest.approx(-20)
    assert norm360(-90) == pytest.approx(270)
    assert bearing_to(0, 0, 1, 0) == pytest.approx(90)
    assert bearing_to(0, 0, 0, -1) == pytest.approx(180)


def test_moves_north_at_six_knots():
    s = ShipState(x=0, y=0, course=0, speed=6)
    for _ in range(3600):
        s.step(1)
    assert s.y == pytest.approx(6.0, abs=1e-6)
    assert s.x == pytest.approx(0.0, abs=1e-6)


def test_turns_shortest_way_and_gradually():
    s = ShipState(x=0, y=0, course=350, speed=5, turn_rate=1.0)
    s.order_course(10)
    s.step(1)
    assert s.course == pytest.approx(351)
    assert "course" in s.changing()
    for _ in range(19):
        s.step(1)
    assert s.course == pytest.approx(10)
    assert "course" not in s.changing()


def test_speed_and_depth_ramp():
    s = ShipState(x=0, y=0, course=0, speed=0, depth=50, accel=0.1, depth_rate=1.0)
    s.order_speed(5)
    s.order_depth(100)
    for _ in range(10):
        s.step(1)
    assert s.speed == pytest.approx(1.0)
    assert s.depth == pytest.approx(60)
    for _ in range(100):
        s.step(1)
    assert s.speed == pytest.approx(5)
    assert s.depth == pytest.approx(100)
    assert s.changing() == set()


def test_orders_are_clamped():
    s = ShipState(x=0, y=0, course=0, speed=0, max_speed=28, max_depth=300)
    s.order_speed(99)
    s.order_depth(-5)
    assert s.ordered_speed == 28
    assert s.ordered_depth == 0
