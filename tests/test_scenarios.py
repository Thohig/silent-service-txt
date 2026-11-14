"""Scenarioregistret: varje scenario går att bygga och spela en stund."""
import random

import pytest

from sim.game import Game
from sim.scenario import SCENARIOS, build_scenario


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_every_scenario_builds_and_runs(key):
    sc = build_scenario(key, random.Random(1))
    g = Game(sc, seed=1)
    for _ in range(300):
        g.tick()
    assert not g.over
    assert sc.secret_order.strip()


def test_unknown_scenario_is_rejected():
    with pytest.raises(KeyError):
        build_scenario("finns-inte", random.Random(1))


def test_scenario_order_is_stable():
    assert next(iter(SCENARIOS)) == "kuba"
