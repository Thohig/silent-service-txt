"""N1: navigatören räknar strömmen ur besticket och fixarna (sim/stations/navigation/current.py)."""
import math
import random

import pytest

from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.navigation import NavigationStation

SEEDS = range(1, 9)


def _game(seed, use_current=True):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts, w.ais = [], []
    w.env.current_set, w.env.current_kn = 45.0, 0.4
    st = w.own.state
    st.depth = st.ordered_depth = 17
    st.speed = st.ordered_speed = 4
    nav = g.station(NavigationStation)
    if not use_current:
        nav.current_used = lambda: (0.0, 0.0)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, nav, reports


def _patrol(g, hours=3.0, fix_every=1500):
    for i in range(int(hours * 3600)):
        g.tick()
        if i % fix_every == fix_every - 1:
            g.command("fix")


def _truth_error(g, nav):
    s = g.world.own.state
    return math.hypot(nav.est_x - s.x, nav.est_y - s.y)


@pytest.mark.slow
def test_strommen_mats_upp_arligt_over_froen():
    inside, errs = 0, []
    for seed in SEEDS:
        g, nav, reports = _game(seed)
        _patrol(g)
        tx, ty = 0.4 * math.sin(math.radians(45)), 0.4 * math.cos(math.radians(45))
        err = math.hypot(nav.cur_vx - tx, nav.cur_vy - ty)
        errs.append(err)
        inside += err <= 3 * nav.current_sigma * math.sqrt(2) + 0.02
        assert nav.current_quality() >= Quality.OSAKER
        assert any(r.type == "nav.current" for r in reports)
    assert inside >= 7
    assert sorted(errs)[len(errs) // 2] < 0.15                    # median inom 0,15 kn


@pytest.mark.slow
def test_besticket_blir_battre_med_strommen():
    """En timme efter sista fixen: besticket med strömmen ligger närmare sanningen."""
    with_c, without = [], []
    for seed in SEEDS:
        for use, out in ((True, with_c), (False, without)):
            g, nav, _ = _game(seed, use_current=use)
            _patrol(g)
            for _ in range(3600):
                g.tick()
            out.append(_truth_error(g, nav))
    assert sum(with_c) < 0.75 * sum(without)                       # uppmätt ~0,66


def test_strom_order_utan_matning():
    g, nav, reports = _game(1)
    g.command("ström")
    for _ in range(20):
        g.tick()
    r = next(r for r in reports if r.type == "nav.current.report")
    assert "två fixar" in r.text


def test_inget_pa_botten():
    g, nav, _ = _game(1)
    nav._cur_since_fix_ok = True
    g.world.own.sys.on_bottom = True
    g.tick()
    assert not nav._cur_since_fix_ok
