"""Torped i vattnet: sonar räknar ned tiden tills torpeden är framme, ur hur fort nivån stiger."""
import math
import random

import pytest

from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.incoming import ETA_MAX_S, eta_estimate

from test_enemy_torpedo import _run, _shoot


def _approach(r0_m=3000.0, v=13.0, sl=145.0, t_end=60, noise=0.0, seed=1):
    rng = random.Random(seed)
    return [(t, sl - 20 * math.log10(r0_m - v * t) + rng.gauss(0, noise)) for t in range(0, t_end + 1, 5)]


def test_eta_from_a_straight_approach_is_right_and_sure_without_noise():
    lv = _approach()
    eta, q = eta_estimate(lv, 60)
    true = (3000 - 13 * 60) / 13
    assert eta == pytest.approx(true, rel=0.05)
    assert q >= Quality.OSAKER


def test_noisy_levels_lower_the_quality():
    _, q_clean = eta_estimate(_approach(), 60)
    noisy = eta_estimate(_approach(noise=1.5, seed=4), 60)
    assert noisy is None or noisy[1] <= q_clean


def test_no_eta_when_the_level_falls_or_it_is_far():
    falling = [(t, 100 - 0.1 * t) for t in range(0, 41, 5)]
    assert eta_estimate(falling, 40) is None
    far = _approach(r0_m=12000, v=13, t_end=40)
    assert eta_estimate(far, 40) is None or eta_estimate(far, 40)[0] <= ETA_MAX_S


@pytest.mark.slow
def test_countdown_against_the_truth_over_seeds():
    """God nedräkning ligger oftast inom 30 % (eller 10 s) av den verkliga tiden."""
    good = bad = 0
    for seed in range(1, 9):
        g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
        w = g.world
        w.spawners.clear()
        w.contacts, w.ais = [], []
        st = w.own.state
        st.depth = st.ordered_depth = 120
        st.speed = st.ordered_speed = 0
        reps = []
        g.bus.subscribe(ReportDelivered, lambda e: reps.append((g.now, e.report)))
        _shoot(g, 2.5, bearing=random.Random(seed).uniform(0, 360))
        _run(g, 900)
        hit = w.mission.get("hit_by_torpedo")
        assert hit is not None
        etas = [(t, r) for t, r in reps if r.type == "sonar.torpedo.bearing" and r.data.get("eta") is not None]
        assert etas, seed
        assert any("Framme om" in r.text for _, r in etas)
        for t, r in etas:
            if r.quality >= Quality.GOD:
                err = abs(r.data["eta"] - (hit - t))
                if err <= max(0.3 * (hit - t), 10):
                    good += 1
                else:
                    bad += 1
    assert good + bad >= 8
    assert bad <= 0.25 * (good + bad)
