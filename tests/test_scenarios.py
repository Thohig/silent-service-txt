"""Scenarioregistret: varje scenario går att bygga och spela en stund."""
import random

import pytest

from sim.game import Game
from sim.scenario import SCENARIOS, build_scenario
from sim.truthlog import TruthLog


# korta varianter med uppvärmning kör vakten i flera minuter före testet
WARMUP_KEYS = ("konvoj-kort", "konvoj-mot")


@pytest.mark.parametrize("key", [pytest.param(k, marks=pytest.mark.slow) if k in WARMUP_KEYS else k
                                 for k in SCENARIOS])
def test_every_scenario_builds_and_runs(key, tmp_path):
    sc = build_scenario(key, random.Random(1))
    log = TruthLog(tmp_path / "truth.log")     # gränssnittet loggar alltid sanningen
    g = Game(sc, seed=1, truth_log=log)
    for _ in range(300):
        g.tick()
    log.close()
    assert not g.over
    assert sc.secret_order.strip()
    assert "AI " in (tmp_path / "truth.log").read_text(encoding="utf-8")


def test_unknown_scenario_is_rejected():
    with pytest.raises(KeyError):
        build_scenario("finns-inte", random.Random(1))


def test_scenario_order_is_stable():
    assert next(iter(SCENARIOS)) == "kuba"
