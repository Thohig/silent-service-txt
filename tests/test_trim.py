"""Trim och flytkraft (sanning, sim/trim.py): vikten, rodrens förmåga och pumparna."""
import random
from types import SimpleNamespace

import pytest

from sim import trim
from sim.environment import Environment
from sim.ice import IceField
from sim.ownship import OwnShip
from sim.ship import ShipState
from sim.world import World


def _world(depth=40.0, speed=1.0, **env):
    own = OwnShip(ShipState(x=10, y=10, course=0, speed=speed, depth=depth, max_depth=400))
    return World(own=own, env=Environment(**env), rng=random.Random(1))


def _run(w, n):
    for _ in range(n):
        w.tick()


def test_vikten_av_djupet_skiktet_och_isen():
    env = Environment()                                 # skikt på 60 m
    assert trim.environment_weight(100, env) < trim.environment_weight(40, env)   # skiktet bär
    assert trim.environment_weight(300, env) > trim.environment_weight(100, env)  # skrovet trycks
    ice = SimpleNamespace(layer_depth=None, ice=object())
    assert trim.environment_weight(10, ice) - trim.environment_weight(60, ice) > 0.3  # smältvatten


def test_trimmad_vid_start():
    w = _world(depth=80)
    _run(w, 1)
    assert w.own.sys.trim.weight_t == pytest.approx(0, abs=1e-6)


def test_rodren_bar_mer_ju_fortare():
    assert trim.plane_capacity(0) == 0
    assert trim.plane_capacity(2) < trim.plane_capacity(3) < trim.plane_capacity(6)
    assert trim.plane_capacity(20) == trim.PLANE_MAX_T
    assert trim.plane_capacity(6, planes_health=0.5) == pytest.approx(trim.PLANE_MAX_T / 2)


def test_genom_skiktet_blir_baten_latt_och_stiger_i_smygfart():
    """Djupändringen i låg fart görs med barlasten, men att hålla djupet under skiktet
    otrimmad går inte: det kallare vattnet bär båten uppåt."""
    w = _world(depth=40, speed=0.8)
    w.own.state.order_depth(100)
    _run(w, 600)
    t = w.own.sys.trim
    assert t.weight_t < -1.5                            # lätt under skiktet
    assert t.free_t < 0                                 # rodren bär det inte
    _run(w, 900)
    assert w.own.state.depth < 95                       # och den stiger


def test_i_fart_bar_rodren_det():
    w = _world(depth=40, speed=6)
    w.own.state.order_depth(100)
    _run(w, 400)
    assert w.own.state.depth == pytest.approx(100)
    assert w.own.sys.trim.free_t == 0 and w.own.sys.trim.plane_load < 0


def test_torpeden_gor_foren_latt():
    t = trim.TrimState()
    for _ in range(4):
        t.torpedo_fired()
    t.weigh(0, Environment(), 0.0)
    net = 4 * trim.TORPEDO_T * (1 - trim.REPLACE_SHARE)
    assert t.weight_t == pytest.approx(-net)
    assert t.pitch == pytest.approx(-trim.PITCH_DEG_PER_T * net)       # fören upp


def test_pumparna_tar_tid_och_hors():
    w = _world(depth=100, speed=3)
    w.own.sys.propulsion = "electric"                   # bredvid turbinen hörs de knappt
    _run(w, 2)
    quiet = w.own.radiated_level(w.env)
    t = w.own.sys.trim
    start = t.ballast_t
    t.pump(ballast_to=start - 3)
    assert w.own.radiated_level(w.env) > quiet + 1.0
    _run(w, 60)
    assert t.ballast_t == pytest.approx(start - trim.PUMP_T_PER_MIN, abs=0.05)
    _run(w, 150)
    assert not t.pumping and w.own.radiated_level(w.env) == pytest.approx(quiet, abs=0.3)


def test_tankarna_har_granser():
    t = trim.TrimState()
    t.pump(ballast_to=-100, fore_to=50)
    assert t.pump_to_t == trim.BALLAST_MIN_T and t.fore_to_t == trim.FORE_MAX_T


def test_lackvatten_ar_vikt():
    w = _world(depth=100, speed=2)
    _run(w, 1)
    w.own.sys.flooding = 10.0
    w.own.sys.dmg.bilge_on = False                      # länspumparna står (de tar 0,8 t/min här)
    _run(w, 120)
    assert w.own.sys.trim.weight_t > 9
    assert w.own.state.depth > 105                      # 2 knop bär inte 10 ton


def test_vid_order_om_ytlage_bar_huvudbarlasten():
    w = _world(depth=30, speed=0, ice=None)
    w.own.sys.flooding = 6.0
    w.own.state.order_depth(0)
    _run(w, 300)
    assert w.own.state.depth == 0
