"""Ljudprofiler: språngskikt och arktisk profil under is."""
import math

import pytest

from sim import acoustics as ac
from sim.environment import ArcticProfile, Environment, Thermocline, spherical_loss


def test_default_environment_is_unchanged_thermocline():
    env = Environment()
    assert env.layer_depth == 60.0
    for r in (0.5, 2.0, 5.0, 10.0):
        expected = 20 * math.log10(r * 1852) + 0.5 * r
        assert ac.transmission_loss(r, 30, 40, env) == pytest.approx(expected, abs=0.05)
        assert ac.transmission_loss(r, 30, 100, env) == pytest.approx(expected + 7, abs=0.05)


def test_arctic_has_no_layer():
    env = Environment(profile=ArcticProfile())
    assert env.layer_depth is None
    assert not env.layer_between(20, 200)


def test_arctic_ducts_at_middle_range_but_scatters_far():
    arc = ArcticProfile()
    # utan isstudsar vore kanalen bättre än sfärisk spridning
    for r in (3.0, 6.0, 12.0):
        duct_only = arc.transmission_loss(r, 100, 100) - arc.scatter_loss(r, 100, 100)
        assert duct_only < spherical_loss(r)
    # men studsarna växer linjärt och gör långa avstånd dyra för grunda gångare
    assert arc.transmission_loss(12, 20, 20) > spherical_loss(12)


def test_arctic_deep_runners_hear_and_are_heard_further():
    arc = ArcticProfile()
    shallow = arc.transmission_loss(5, 30, 30)
    deep = arc.transmission_loss(5, 250, 250)
    assert deep < shallow - 3
    # symmetriskt: samma förlust åt båda håll
    assert arc.transmission_loss(5, 30, 250) == pytest.approx(arc.transmission_loss(5, 250, 30))


def test_profiles_are_continuous_with_range():
    arc = ArcticProfile()
    a = arc.transmission_loss(arc.transition_nm - 1e-6, 100, 100)
    b = arc.transmission_loss(arc.transition_nm + 1e-6, 100, 100)
    assert a == pytest.approx(b, abs=0.01)
    assert Thermocline().transmission_loss(5, 10, 10) == pytest.approx(spherical_loss(5))
