import pytest

from sim import acoustics as ac


def test_power_sum():
    assert ac.power_sum(60, 60) == pytest.approx(63.01, abs=0.01)
    assert ac.power_sum(60, 80) == pytest.approx(80.04, abs=0.01)


def test_loss_grows_with_range():
    assert ac.transmission_loss(2) < ac.transmission_loss(5) < ac.transmission_loss(10)


def test_own_speed_deafens_sonar():
    sl = ac.source_level("destroyer", 15)
    tl = ac.transmission_loss(5)
    slow = ac.signal_excess(sl, tl, ac.total_noise(60, 4))
    fast = ac.signal_excess(sl, tl, ac.total_noise(60, 18))
    assert slow > 0 > fast


def test_slow_speed_limited_by_background():
    # under ~4 knop dominerar havsbruset: långsammare hjälper knappt
    assert ac.total_noise(60, 0) - ac.total_noise(60, 2) < 1.5
