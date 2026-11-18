"""D2: amerikanska ubåten skjuter i krig (roe attack): luckorna hörs, sedan torpeden."""
import random

import pytest

from sim.arctic import ATTACK_NM, DOORS_S, SubmarineAI
from sim.events import ReportDelivered
from sim.game import Game
from sim.geo import velocity
from sim.scenario import build_scenario

SEEDS = range(1, 9)


def _duel(seed=1, range_nm=2.5, roe="attack"):
    g = Game(build_scenario("arktis", random.Random(seed)), seed=seed)
    w = g.world
    ai = next(a for a in w.ais if isinstance(a, SubmarineAI))
    ai.roe = roe
    o = w.own.state
    dx, dy = velocity(90, range_nm * 3600)
    us = ai.vessel.state
    us.x, us.y, us.depth = o.x + dx, o.y + dy, o.depth
    us.ordered_depth = o.depth
    w.own.sys.propulsion = "turbine"
    o.speed = o.ordered_speed = 8                  # hörs: den hittar oss
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, ai, reports


def _run(g, n):
    for _ in range(n):
        if g.over:
            break
        g.tick()


def test_i_krig_oppnar_den_luckorna_och_skjuter():
    g, ai, reports = _duel()
    _run(g, 900)
    assert g.world.mission.get("us_fired", 0) >= 1
    assert any(r.type == "sonar.doors" for r in reports)
    assert any(r.type == "sonar.torpedo" for r in reports)
    doors = next(r for r in reports if r.type == "sonar.doors")
    torp = next(r for r in reports if r.type == "sonar.torpedo")
    assert torp.t_due - doors.t_due >= DOORS_S - 10                # varningen kommer först


def test_i_fred_skjuter_den_inte():
    g, ai, reports = _duel(roe="observe")
    _run(g, 900)
    assert g.world.mission.get("us_fired", 0) == 0
    assert ai.state == "trail"


@pytest.mark.slow
def test_den_skjuter_i_de_flesta_froen_och_traffar_ibland_en_passiv_bat():
    fired = hit = 0
    for seed in SEEDS:
        g, ai, _ = _duel(seed)
        _run(g, 1800)
        fired += g.world.mission.get("us_fired", 0) >= 1
        hit += g.world.mission.get("hit_by_torpedo") is not None
    assert fired >= 6
    assert hit >= 3
