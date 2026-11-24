"""Plottets lösning som inte satt sig (2026-11-23): ett hopp från förra lösningen eller en lång
lucka i bäringarna nyss ger ett steg lägre kvalitet en stund (`Knowledge._settled`). Säker kräver
bäringar över minst `SURE_MIN_SPAN_S` utan ett mätt avstånd (2026-11-24)."""
from dataclasses import replace

import pytest

import sim.knowledge

from sim.knowledge import (GAP_HOLD_S, GAP_S, JUMP_DT_S, JUMP_HOLD_S, ContactTrack, Knowledge)
from sim.reports import Quality
from sim.tma import BearingObs, Solution


@pytest.fixture(autouse=True)
def _no_span_rule(request, monkeypatch):
    """Hopp och luckor prövas på korta serier: spannregeln har ett eget test."""
    if "span" not in request.node.name:
        monkeypatch.setattr(sim.knowledge, "SURE_MIN_SPAN_S", 0)


def _sol(t, x, y, q=Quality.SAKER, sigma=0.1):
    return Solution(t=t, t_ref=t, state=(x, y, 0.0, 0.0), x=x, y=y, course=0.0, speed=0.0,
                    range_nm=3.0, bearing=0.0, range_sigma=sigma, course_sigma=10.0, speed_sigma=1.0,
                    quality=q, n_obs=30, span_s=900, own_maneuvered=True, rms_residual=1.0)


def _obs(ts):
    return [BearingObs(t, 0.0, 0.5, 0.0, 0.0, 0.0, designation="S-1") for t in ts]


def test_a_jump_lowers_the_quality_for_a_while():
    k = Knowledge()
    tr = ContactTrack("S-1", 0)
    obs = _obs(range(0, 900, 20))
    assert k._settled(tr, _sol(900, 0.0, 3.0), obs, 900).quality == Quality.SAKER
    # 0,5 nm bort på 30 s, σ 0,1: hopp
    s = k._settled(tr, _sol(930, 0.5, 3.0), obs, 930)
    assert s.quality == Quality.GOD
    # samma läge sedan: fortfarande ett steg lägre inom JUMP_HOLD_S, sedan säker igen
    t = 930 + JUMP_DT_S
    assert k._settled(tr, _sol(t, 0.5, 3.0), obs, t).quality == Quality.GOD
    t = 930 + JUMP_HOLD_S + JUMP_DT_S
    assert k._settled(tr, _sol(t, 0.5, 3.0), obs, t).quality == Quality.SAKER


def test_a_small_move_inside_sigma_is_not_a_jump():
    k = Knowledge()
    tr = ContactTrack("S-1", 0)
    obs = _obs(range(0, 900, 20))
    k._settled(tr, _sol(900, 0.0, 3.0), obs, 900)
    assert k._settled(tr, _sol(930, 0.05, 3.0), obs, 930).quality == Quality.SAKER


def test_a_long_gap_in_the_bearings_lowers_the_quality_until_settled():
    k = Knowledge()
    tr = ContactTrack("S-1", 0)
    end = 600 + GAP_S + 60
    obs = _obs(list(range(0, 600, 20)) + list(range(end, end + 120, 20)))
    now = end + 120
    assert k._settled(tr, _sol(now, 0.0, 3.0), obs, now).quality == Quality.GOD
    later = end + GAP_HOLD_S + 20
    obs2 = obs + _obs(range(end + 120, later, 20))
    tr2 = ContactTrack("S-1", 0)
    assert k._settled(tr2, _sol(later, 0.0, 3.0), obs2, later).quality == Quality.SAKER


def test_poor_and_unsure_are_not_lowered():
    k = Knowledge()
    tr = ContactTrack("S-1", 0)
    obs = _obs(range(0, 900, 20))
    k._settled(tr, _sol(900, 0.0, 3.0, Quality.OSAKER), obs, 900)
    assert k._settled(tr, _sol(930, 2.0, 3.0, Quality.OSAKER), obs, 930).quality == Quality.OSAKER


def test_a_short_span_is_not_sure_without_a_measured_range():
    """Konvoj frö 1, 4, 5: säker på 0,7–1,2 nm efter 6–10 min bäringar, sant 2,8–3,7 nm."""
    from sim.knowledge import SURE_MIN_SPAN_S
    k = Knowledge()
    short = _obs(range(0, SURE_MIN_SPAN_S - 60, 20))
    t = short[-1].t
    assert k._settled(ContactTrack("S-1", 0), _sol(t, 0.0, 3.0), short, t).quality == Quality.GOD
    ranged = short[:-1] + [replace(short[-1], range_nm=3.0, range_sigma=0.3, source="periskop")]
    assert k._settled(ContactTrack("S-1", 0), _sol(t, 0.0, 3.0), ranged, t).quality == Quality.SAKER
    long = _obs(range(0, SURE_MIN_SPAN_S + 60, 20))
    t = long[-1].t
    assert k._settled(ContactTrack("S-1", 0), _sol(t, 0.0, 3.0), long, t).quality == Quality.SAKER
