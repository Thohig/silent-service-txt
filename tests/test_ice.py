"""Packisen: generering, drift och ubåtens kontakt med isen."""
import random

import numpy as np
import pytest

from sim.environment import ArcticProfile, Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.ice import (BREAK_S, CELL_NM, IceField, ceiling, clearance, masts_clear)
from sim.ownship import OwnShip
from sim.scenario import build_scenario
from sim.ship import ShipState
from sim.world import World


def _flat(thickness: float, draft: float | None = None) -> IceField:
    f = IceField(random.Random(0), size_nm=4.0, leads=0, ridges=0, polynyas=0, drift_kn=0.0)
    f.thickness[:] = thickness
    f.draft[:] = 0.89 * thickness if draft is None else draft
    return f


def _world(ice: IceField, depth=60.0, speed=0.0, course=0.0) -> World:
    own = OwnShip(ShipState(x=2.0, y=2.0, course=course, speed=speed, depth=depth, max_depth=400))
    env = Environment(profile=ArcticProfile(), ice=ice, current_kn=0.0)
    return World(own=own, env=env, rng=random.Random(1))


def _run(w, n):
    for _ in range(n):
        w.tick()


def _alerts(w):
    return [a[0] for a in w.own.sys.alerts]


# --- generering ------------------------------------------------------------------
def test_generation_is_deterministic_per_seed():
    a, b = IceField(random.Random(7)), IceField(random.Random(7))
    assert np.array_equal(a.thickness, b.thickness) and np.array_equal(a.draft, b.draft)
    c = IceField(random.Random(8))
    assert not np.array_equal(a.thickness, c.thickness)


@pytest.mark.parametrize("seed", range(5))
def test_generated_ice_has_openings_and_keels(seed):
    f = IceField(random.Random(seed))
    assert 0.02 < f.open_fraction() < 0.10
    assert 0.04 < float(np.mean(f.thickness < 1.0)) < 0.15     # öppet eller nyis
    assert float(np.mean(f.draft > 15)) > 0.001                 # iskölar finns
    assert float(f.draft.max()) < 50
    assert 2.0 < float(np.median(f.thickness)) < 4.5            # mest flerårsis


def test_ice_drifts_and_wraps_around():
    f = IceField(random.Random(3), drift_set=90.0, drift_kn=0.25)
    before = f.thickness_at(5.025, 5.025)                    # mitt i en ruta
    for _ in range(3600):
        f.advance(1)
    assert f.ox == pytest.approx(0.25, abs=1e-6)
    assert f.thickness_at(5.275, 5.025) == before
    assert f.thickness_at(5.0 + f.size_nm, 5.0 + f.size_nm) == f.thickness_at(5.0, 5.0)


# --- kontakt med isen --------------------------------------------------------------
def test_thick_ice_stops_ascent_and_boat_backs_down():
    w = _world(_flat(3.0), depth=60)
    w.own.state.order_depth(0)
    _run(w, 400)
    st = w.own.state
    assert "ice.bump" in _alerts(w)
    assert st.depth > 15
    assert clearance(w.env.ice, st.x, st.y, st.course, st.depth) >= 0
    assert w.own.sys.hull == 1.0


def test_emergency_blow_under_thick_ice_ends_against_the_ice_and_we_can_dive_again():
    """Nödblåsning under tjock is: förut blåste den så länge båten inte nått ytan, och det beordrade
    djupet hölls på 0, så båten låg fast mot isen (arktis, kaosboten)."""
    w = _world(_flat(3.0), depth=40)
    assert w.own.emergency_blow()
    _run(w, 60)
    bumps = [a for a in w.own.sys.alerts if a[0] == "ice.bump"]
    assert bumps and bumps[0][1]["blow"]
    assert not w.own.sys.blowing
    w.own.state.order_depth(60)
    _run(w, 200)
    assert w.own.state.depth == pytest.approx(60, abs=0.5)


def test_thin_ice_can_be_broken_through_at_low_speed():
    w = _world(_flat(0.5), depth=40)
    w.own.state.order_depth(0)
    _run(w, 200 + BREAK_S)
    assert "ice.pressing" in _alerts(w)
    assert "ice.broke_through" in _alerts(w)
    assert w.own.state.depth == 0
    assert masts_clear(w)


def test_thin_ice_too_fast_bumps_instead():
    w = _world(_flat(0.5), depth=40, speed=5)
    w.own.state.order_depth(0)
    _run(w, 120)
    bumps = [a for a in w.own.sys.alerts if a[0] == "ice.bump"]
    assert bumps and bumps[0][1]["too_fast"]
    assert "ice.broke_through" not in _alerts(w)


def test_running_into_a_keel_stops_and_damages_the_boat():
    f = _flat(3.0)
    row = int(2.3 / CELL_NM)
    f.draft[row:row + 2, :] = 40.0                 # isköl tvärs kursen, 0,3 nm norrut
    w = _world(f, depth=35, speed=8)
    w.own.state.order_speed(8)
    _run(w, 300)
    st = w.own.state
    assert "ice.collision" in _alerts(w)
    assert w.own.sys.hull < 1.0
    assert st.y < row * CELL_NM                    # kom aldrig förbi kölen
    assert st.ordered_speed == 0


def test_deep_boat_passes_under_keels():
    f = _flat(3.0)
    row = int(2.3 / CELL_NM)
    f.draft[row:row + 2, :] = 40.0
    w = _world(f, depth=80, speed=8)
    w.own.state.order_speed(8)
    _run(w, 300)
    assert w.own.state.y > (row + 2) * CELL_NM
    assert not any(a.startswith("ice.") for a in _alerts(w))


def test_ceiling_matches_hull_geometry():
    f = _flat(3.0, draft=3.0)
    assert ceiling(f, 2.0, 2.0, 0.0) == pytest.approx(16.0)       # torn 13 m + 3 m is
    assert clearance(f, 2.0, 2.0, 0.0, 16.0) == pytest.approx(0.0)


# --- besättningen och masterna -------------------------------------------------------
def _arctic_game(seed=1):
    g = Game(build_scenario("arktis", random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_periscope_and_fix_refused_under_ice():
    g, reports = _arctic_game()
    ice = g.world.env.ice
    ice.thickness[:] = 3.0
    ice.draft[:] = 3.0
    g.world.own.state.depth = 17.0
    g.world.own.state.order_depth(17)
    g.world.own.state.order_speed(3)
    g.command("periskop")
    g.command("fix")
    for _ in range(20):
        g.tick()
    texts = [r.text for r in reports]
    assert any("is ovanför" in t and "masterna" in t for t in texts)
    assert any("is ovanför" in t and "periskopet" in t for t in texts)


def test_arctic_scenario_is_dark_and_layerless():
    g, _ = _arctic_game()
    env = g.world.env
    assert env.layer_depth is None
    assert not any(env.is_day(t) for t in range(0, 6 * 3600, 600))
    s = g.world.own.state
    assert clearance(env.ice, s.x, s.y, s.course, s.depth) >= 10
