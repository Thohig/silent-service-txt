"""Periskopbilden: synlig del, vinkel på bogen, lanternor och kunskapens senaste bild."""
import random

import pytest

from sim.game import Game
from sim.periscope import (EYE_BRIDGE_M, EYE_PERISCOPE_M, angle_on_bow, aob_quality,
                           hidden_height_m, horizon_nm, lights, range_quality, visible_part)
from sim.reports import Quality
from sim.scenario import default_scenario


# --- geometri -------------------------------------------------------------------
def test_horizon_and_hidden_height():
    assert horizon_nm(EYE_PERISCOPE_M) == pytest.approx(2.55, abs=0.01)
    assert hidden_height_m(2.0, EYE_PERISCOPE_M) == 0.0
    assert hidden_height_m(8.0, EYE_PERISCOPE_M) == pytest.approx(6.9, abs=0.1)


def test_visible_part_shrinks_with_range_and_grows_with_eye_height():
    assert visible_part("destroyer", 2.0, EYE_PERISCOPE_M) == "helt"
    assert visible_part("destroyer", 8.0, EYE_PERISCOPE_M) == "överbyggnad"
    assert visible_part("destroyer", 14.0, EYE_PERISCOPE_M) == "mastoppar"
    assert visible_part("destroyer", 8.0, EYE_BRIDGE_M) == "helt"
    # en låg patrullbåt försvinner tidigare än en jagare
    assert visible_part("patrol", 8.0, EYE_PERISCOPE_M) == "mastoppar"


def test_angle_on_bow_and_lights():
    # målet rakt norrut går mot väster: vi ser dess babordssida (röd lanterna)
    aob = angle_on_bow(0.0, 270.0)
    assert aob == pytest.approx(-90.0)
    assert lights(aob) == ("topp", "röd")
    # går mot öster: styrbord, grön
    assert angle_on_bow(0.0, 90.0) == pytest.approx(90.0)
    assert lights(90.0) == ("topp", "grön")
    # går rakt bort från oss: akterlanternan
    assert abs(angle_on_bow(0.0, 0.0)) == pytest.approx(180.0)
    assert lights(180.0) == ("akter",)


def test_qualities_follow_uncertainty():
    assert aob_quality(8) == Quality.GOD
    assert aob_quality(15) == Quality.OSAKER
    assert aob_quality(30) == Quality.DALIG
    assert range_quality(4.0, 0.35) == Quality.SAKER
    assert range_quality(1.0, 0.11) == Quality.GOD


# --- i spelet ----------------------------------------------------------------------
def _game_at_periscope_depth(seed=3, day=False, dd_range=2.0):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    w = g.world
    st = w.own.state
    st.depth = st.ordered_depth = 15.0
    st.speed = st.ordered_speed = 3.0
    dd = next(v for v in w.contacts if v.kind == "destroyer")
    dd.state.x, dd.state.y = st.x, st.y + dd_range
    dd.state.course = dd.state.ordered_course = 270.0
    if day:
        w.env.sunrise = 0
        w.env.sunset = 24 * 3600
    return g


def _look(g, seconds=20):
    g.command("periskop")
    for _ in range(seconds):
        g.tick()


def test_picture_after_sweep_uses_plot_designations_not_truth():
    g = _game_at_periscope_depth(day=True)
    assert g.knowledge.periscope is None
    _look(g)
    pic = g.knowledge.periscope
    assert pic is not None and pic.eye == "periskop" and pic.day
    ships = pic.ships()
    assert ships, "jagaren två sjömil bort ska synas"
    truth_ids = {v.id for v in g.world.contacts}
    for o in ships:
        assert o.designation.startswith("S-") and o.designation not in truth_ids
        assert o.designation in g.knowledge.tracks
    dd = next(o for o in ships if o.kind == "destroyer")
    assert dd.label == "jagare" and dd.visible == "helt"
    assert dd.aob is not None and dd.aob < 0          # babordssidan mot oss
    assert dd.aob_quality == Quality.GOD
    assert dd.lights == ()


def test_night_picture_shows_only_lights():
    g = _game_at_periscope_depth(day=False)
    assert not g.world.env.is_day(g.now)
    _look(g)
    dd = next(o for o in g.knowledge.periscope.ships() if o.kind == "destroyer")
    assert dd.visible == "ljus"
    assert dd.aob_quality == Quality.DALIG
    assert "topp" in dd.lights or "akter" in dd.lights


def test_no_picture_when_deep_or_when_diving_during_sweep():
    g = _game_at_periscope_depth()
    g.world.own.state.depth = g.world.own.state.ordered_depth = 100.0
    _look(g)
    assert g.knowledge.periscope is None
    g = _game_at_periscope_depth()
    g.command("periskop")
    g.world.own.state.depth = g.world.own.state.ordered_depth = 60.0
    for _ in range(20):
        g.tick()
    assert g.knowledge.periscope is None


def test_far_targets_give_worse_angle_on_bow_over_seeds():
    """Långt bort syns bara överbyggnaden: kursbedömningen sprider mer."""
    near, far = [], []
    for seed in range(8):
        for rng_nm, out in ((2.0, near), (7.5, far)):
            g = _game_at_periscope_depth(seed=seed, day=True, dd_range=rng_nm)
            g.world.env.day_visibility_nm = 12.0
            _look(g)
            dd = next(o for o in g.knowledge.periscope.ships() if o.kind == "destroyer")
            out.append((dd.visible, abs(dd.aob + 90.0)))
    assert all(v == "helt" for v, _ in near)
    assert all(v == "överbyggnad" for v, _ in far)
    assert sum(e for _, e in far) > sum(e for _, e in near)
