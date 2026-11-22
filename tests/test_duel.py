"""D3: Duellen under isen (duell, duell-kort, duell-torped)."""
import random

import pytest

from sim.arctic import SubmarineAI
from sim.events import ReportDelivered
from sim.game import Game
from sim.goals import EscapeGoal
from sim.scenario import SCENARIOS, build_scenario


def test_duellen_ar_registrerad_och_i_krig():
    assert "duell" in SCENARIOS and "duell-kort" in SCENARIOS
    sc = build_scenario("duell", random.Random(1))
    ai = next(a for a in sc.world.ais if isinstance(a, SubmarineAI))
    assert ai.roe == "attack"
    assert sc.world.goal(EscapeGoal) is not None
    assert "KRIGSTILLSTÅND" in sc.secret_order
    assert sc.nuclear_order == "forbidden" and sc.at_war


@pytest.mark.slow
def test_kort_variant_ger_kontakt_inom_tre_minuter():
    """Riktmärket för korta varianter: första kontakt, förslag eller larm inom 3 min."""
    for seed in range(1, 9):
        g = Game(build_scenario("duell-kort", random.Random(seed)), seed=seed)
        start, first = g.now, []
        g.bus.subscribe(ReportDelivered, lambda e: first.append(g.now) if (
            e.report.kind in ("suggest", "contact") or e.report.alarm) else None)
        for _ in range(180):
            g.tick()
        assert first and first[0] - start <= 180, seed


@pytest.mark.slow
def test_sanker_vi_ubaten_ar_det_seger():
    g = Game(build_scenario("duell-kort", random.Random(1)), seed=1)
    us = next(a for a in g.world.ais if isinstance(a, SubmarineAI)).vessel
    us.sunk = True
    for _ in range(200):
        g.tick()
        if g.over:
            break
    assert g.world.outcome["outcome"] == "sank"


@pytest.mark.slow
def test_torpeden_i_vattnet_luckor_och_torped_strax_efter_overlamnandet():
    """duell-torped: sonar hör luckorna inom en halv minut och torpeden inom en minut, efter
    överlämnandet (aldrig under vakten), i alla frön."""
    for seed in range(1, 5):
        g = Game(build_scenario("duell-torped", random.Random(seed)), seed=seed, warm_up=False)
        g.warm_up()
        start, said = g.now, {}
        g.bus.subscribe(ReportDelivered, lambda e: said.setdefault(e.report.type, g.now - start))
        for _ in range(90):
            g.tick()
        assert said.get("sonar.doors", 99) <= 30, (seed, said)
        assert said.get("sonar.torpedo", 99) <= 60, (seed, said)
        assert g.world.mission.get("us_fired") == 1
