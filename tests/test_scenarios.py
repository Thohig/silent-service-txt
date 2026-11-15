"""Scenarioregistret: varje scenario går att bygga och spela en stund."""
import random

import pytest

from sim.game import Game
from sim.scenario import SCENARIOS, build_scenario
from sim.truthlog import TruthLog


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_every_scenario_builds_and_runs(key, tmp_path, request):
    sc = build_scenario(key, random.Random(1))
    log = TruthLog(tmp_path / "truth.log")     # gränssnittet loggar alltid sanningen
    # korta varianter kör vakten i flera minuter före överlämnandet: bara med --slow
    g = Game(sc, seed=1, truth_log=log, warm_up=bool(request.config.getoption("--slow")))
    for _ in range(300):
        g.tick()
    log.close()
    assert not g.over
    assert sc.secret_order.strip()
    text = (tmp_path / "truth.log").read_text(encoding="utf-8")
    assert "OWN x=" in text
    if any(ai.vessel.side != "neutral" for ai in g.world.ais):   # övningen har inga fiender
        assert "AI " in text


def test_unknown_scenario_is_rejected():
    with pytest.raises(KeyError):
        build_scenario("finns-inte", random.Random(1))


def test_scenario_order_is_stable():
    assert next(iter(SCENARIOS)) == "kuba"
