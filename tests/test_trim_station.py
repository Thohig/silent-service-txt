"""Trimmaren (sim/stations/trim.py): bedömningen, när han pumpar och när han frågar."""
import random

import pytest

from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.trim import TrimStation

SEEDS = range(1, 9)


def _game(seed=3, depth=40.0, speed=6.0, propulsion="turbine"):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts, w.ais = [], []
    st = w.own.state
    st.depth = st.ordered_depth = depth
    st.speed = st.ordered_speed = speed
    w.own.sys.propulsion = propulsion
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()


def _trim(g):
    return g.station(TrimStation)


def test_i_turbinfart_trimmar_han_sjalv():
    g, reports = _game(speed=8)
    _run(g, 30)
    g.command("djup 150")
    _run(g, 900)
    t = g.world.own.sys.trim
    assert abs(t.weight_t) < 1.0
    assert not [r for r in reports if r.type == "trim.suggest"]


def test_pa_smygmotorn_fragar_han_forst():
    g, reports = _game(speed=3, propulsion="electric")
    _run(g, 30)
    g.command("djup 150")
    _run(g, 900)
    asks = [r for r in reports if r.type == "trim.suggest"]
    assert asks
    assert abs(g.world.own.sys.trim.weight_t) > 1.0           # han har inte pumpat
    g.command("trimma")
    _run(g, 400)
    assert abs(g.world.own.sys.trim.weight_t) < 1.0


def test_trim_stopp_haller_pumparna_stilla():
    g, reports = _game(speed=8)
    _run(g, 30)
    g.command("trim stopp")
    g.command("djup 150")
    _run(g, 900)
    assert abs(g.world.own.sys.trim.weight_t) > 1.0
    assert not g.world.own.sys.trim.pumping


def test_trimrapport_har_kvalitet():
    g, reports = _game()
    _run(g, 30)
    g.command("trim")
    _run(g, 20)
    r = next(r for r in reports if r.type == "trim.report")
    assert r.quality is not None and "bedömningen" in r.text


def test_ligg_still():
    g, reports = _game(depth=80, speed=3, propulsion="electric")
    _run(g, 120)
    g.command("ligg still")
    _run(g, 5)
    assert g.world.own.sys.trim.hover
    _run(g, 900)
    st = g.world.own.state
    assert st.speed == 0 and abs(st.depth - 80) < 3
    g.command("fart 4")
    _run(g, 5)
    assert not g.world.own.sys.trim.hover


def test_ligg_still_kraver_trim():
    g, reports = _game(speed=8)
    _run(g, 30)
    g.command("trim stopp")
    g.command("djup 150")
    _run(g, 900)
    g.command("ligg still")
    _run(g, 30)
    assert not g.world.own.sys.trim.hover
    assert any(r.type == "trim.hover.refused" for r in reports)


@pytest.mark.slow
def test_bedomningen_ar_arlig_over_froen():
    """Felet mellan bedömning och sanning ryms i 3σ i de flesta mätningar."""
    inside = total = 0
    for seed in SEEDS:
        g, _ = _game(seed=seed, speed=4, propulsion="electric")
        g.command("trim stopp")
        for depth in (120, 200, 90, 250):
            g.command(f"djup {depth}")
            for _ in range(6):
                _run(g, 100)
                ts, t = _trim(g), g.world.own.sys.trim
                total += 1
                inside += abs(ts.est - t.weight_t) <= 3 * ts.sigma + 0.05
    assert inside / total > 0.9


def test_torpeden_kanns_genast():
    g, _ = _game()
    _run(g, 30)
    before = _trim(g).est
    g.world.own.sys.trim.torpedo_fired()
    _run(g, 2)
    assert _trim(g).est == pytest.approx(before - 0.6, abs=0.15)
    assert _trim(g).quality >= Quality.GOD


# --- TR3: ubåtsvyn och centralen ------------------------------------------------------
def test_tankarna_i_genomskarningen():
    from sim.systems import Compartment, Flooding, TrimTanks
    from ui.systems_render import render_hull
    comps = [Compartment(n, "x") for n in range(1, 10)]

    def dots(tanks):
        text = "\n".join(r.plain for r in render_hull(comps, Flooding(0, 120, False), 120, tanks))
        return sum(bin(ord(ch) - 0x2800).count("1") for ch in text if 0x2800 <= ord(ch) <= 0x28FF)

    plain = dots(None)
    empty, full = dots(TrimTanks(0, 0, 0, 0)), dots(TrimTanks(1, 1, 1, 0))
    assert plain < empty < full


def test_systemtavlan_har_trim_och_tankarna():
    from sim.systems import TrimTanks
    g, _ = _game()
    _run(g, 30)
    v = g.systems()
    assert "TRIM" in v.panels()
    labels = [x.label for x in v.gauges("TRIM")]
    assert labels[:3] == ["Vikt", "Lutning", "Utjämningstank"]
    assert v.first(TrimTanks) is not None


def test_djuprodret_bar_vikten_och_libellen_visar_lutningen():
    from dataclasses import replace
    from ui import instruments as ins
    from ui.central_render import PLANE_HOLD_DEG, plane_angle
    g, _ = _game()
    _run(g, 5)
    s = replace(g.status(), plane_load=0.5, pitch=0.0)
    assert plane_angle(s) == pytest.approx(-0.5 * PLANE_HOLD_DEG)       # tung: rodret upp
    level = ins.libell(0.0, span=ins.PITCH_SPAN_DEG)
    bow_down = ins.libell(4.0, span=ins.PITCH_SPAN_DEG)
    assert level != bow_down and level.index("○") == 4
