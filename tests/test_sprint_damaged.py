"""Maskins sprint föreslår inte fortare än turbinen orkar med skadorna (krig-kort frö 20, 2026-11-24:
"turbin och fart 11", och sedan "högsta fart just nu är 9,8 knop")."""
import random

from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.engineering import EngineeringStation


def _eng():
    g = Game(build_scenario("jagad", random.Random(3)), seed=3, warm_up=False)
    return g, g.station(EngineeringStation)


def test_sprint_speed_is_capped_by_damage():
    g, eng = _eng()
    g.world.own.sys.health["propulsion"] = 0.35        # turbinen högst 9,8 kn
    order, data = eng._sprint()
    assert data["speed"] <= g.world.own.turbine_max_speed()
    assert f"fart {data['speed']}" in order


def test_sprint_speed_undamaged_is_the_cavitation_limit():
    g, eng = _eng()
    order, data = eng._sprint()
    assert data["speed"] > 10
