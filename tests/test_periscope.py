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


# --- vyn -------------------------------------------------------------------------------
from sim.periscope import PeriscopePicture, SightedObject  # noqa: E402
from ui.periscope_render import (compress, mirror, ordered_objects, render_periscope,  # noqa: E402
                                 silhouette)


def _ship(desig="S-1", bearing=10.0, rng=1.5, aob=60.0, visible="helt", kind="destroyer",
          lights=()):
    return SightedObject(kind, "jagare", bearing, rng, Quality.GOD, designation=desig,
                         visible=visible, aob=aob, aob_quality=Quality.GOD, course=0.0,
                         speed=12, lights=lights)


def _pic(*objs, day=True):
    return PeriscopePicture(100, day, 8.0, 0.0, "periskop", tuple(objs))


def test_silhouette_turns_with_the_bow_and_is_cut_by_the_horizon():
    stb = silhouette(_ship(aob=90), large=True)
    bb = silhouette(_ship(aob=-90), large=True)
    assert stb[-1].rstrip().endswith("/") and bb[-1].lstrip().startswith("\\")
    assert mirror(mirror(["h ab/("])) == ["h ab/("]
    far = silhouette(_ship(aob=90, visible="mastoppar"), large=True)
    sup = silhouette(_ship(aob=90, visible="överbyggnad"), large=True)
    assert len(far) < len(sup) < len(stb)
    assert all("\\" not in ln for ln in far)
    # rakt förut: smal siluett, men masterna finns kvar
    bow_on = silhouette(_ship(aob=3), large=True)
    assert max(map(len, bow_on)) < max(map(len, stb)) / 2
    assert "|" in "".join(bow_on)
    assert compress(["h abc"], 1.0) == ["h abc"]


def test_render_shows_strip_eyepiece_and_data_without_truth():
    pic = _pic(_ship("S-1", 10.0), _ship("S-2", 200.0, rng=6.0, visible="överbyggnad"))
    rows = [r.plain for r in render_periscope(pic, 100, 30, 0, 0)]
    text = "\n".join(rows)
    assert "S-1" in rows[0] and "S-2" in rows[0]
    assert "förut" in rows[2]
    assert "┊" in text and "░" in text
    assert "vinkel på bogen styrbord 60° (god)" in rows[-1]
    assert "DD1" not in text
    objs = ordered_objects(pic)
    assert [o.designation for o in objs] == ["S-2", "S-1"]   # 200° ligger till vänster om fören


def test_night_eyepiece_shows_only_lights():
    pic = _pic(_ship(aob=40, visible="ljus", lights=("topp", "grön")), day=False)
    rows = [r.plain for r in render_periscope(pic, 100, 30, 0, 0)]
    eye = "\n".join(rows[4:-1])
    assert "●" in eye and "*" in eye and "\\" not in eye
    assert "lanternor: topp, grön" in rows[-1]


def test_no_picture_message():
    rows = render_periscope(None, 100, 30, None, 0)
    assert "periskop" in rows[0].plain


@pytest.mark.slow
def test_tab_reaches_the_periscope_view(tmp_path):
    import asyncio

    from ui.app import SubApp
    from ui.periscope import PeriscopeScreen

    async def run():
        app = SubApp(seed=3, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("enter", "enter")
            g = app.game
            st = g.world.own.state
            st.depth = st.ordered_depth = 15.0
            st.speed = st.ordered_speed = 3.0
            dd = next(v for v in g.world.contacts if v.kind == "destroyer")
            dd.state.x, dd.state.y = st.x + 0.5, st.y + 1.5
            g.command("periskop")
            for _ in range(20):
                g.tick()
            await pilot.press("tab", "tab", "tab", "tab")
            assert isinstance(app.screen, PeriscopeScreen)
            await pilot.pause(0.6)
            body = str(app.screen.query_one("#periscope-body").render())
            assert "S-" in body and "┊" in body
            await pilot.press("right")
            assert app.screen.selected_key is not None
            app.save_screenshot(str(tmp_path / "periskop.svg"))
            await pilot.press("tab")
            assert not isinstance(app.screen, PeriscopeScreen)

    asyncio.run(run())


# --- kort titt, is och sektor (P3) -----------------------------------------------
from sim.scenario import arctic_scenario  # noqa: E402
from sim.stations.officer import OfficerStation, SHORT_LOOK_S  # noqa: E402


def test_short_look_parses_bearing_and_contact():
    g = _game_at_periscope_depth(day=True)
    g.command("periskop 180")
    off = g.station(OfficerStation)
    assert off.look_sector == 180
    assert off.look_done_t == g.now + SHORT_LOOK_S
    g2 = _game_at_periscope_depth(day=True)
    g2.command("periskop S-7")
    assert g2.station(OfficerStation).look_done_t is None     # ingen sådan kontakt


def test_short_look_sees_only_its_sector_and_keeps_the_rest_as_older():
    g = _game_at_periscope_depth(day=True)
    _look(g)                                       # helt svep: jagaren rakt norrut
    dd0 = next(o for o in g.knowledge.periscope.ships() if o.kind == "destroyer")
    for _ in range(60):
        g.tick()
    g.command("periskop 180")
    for _ in range(SHORT_LOOK_S + 2):
        g.tick()
    pic = g.knowledge.periscope
    assert pic.sector == 180
    dd = next(o for o in pic.ships() if o.designation == dd0.designation)
    assert dd.seen_t == dd0.seen_t < pic.t         # från förra svepet, inte sett nu
    rows = [r.plain for r in render_periscope(pic, 100, 30, 0, 0, lambda t: "05:00:00")]
    assert "{" in rows[0] and "}" in rows[0]
    # en kort titt mot jagaren ser den på nytt
    g.command(f"periskop {dd0.designation}")
    for _ in range(SHORT_LOOK_S + 2):
        g.tick()
    pic = g.knowledge.periscope
    dd = next(o for o in pic.ships() if o.designation == dd0.designation)
    assert dd.seen_t == pic.t
    rows = [r.plain for r in render_periscope(pic, 100, 30, None, 0)]
    assert rows


def _arctic(seed=4):
    g = Game(arctic_scenario(random.Random(seed)), seed=seed)
    st = g.world.own.state
    st.depth = st.ordered_depth = 15.0
    st.speed = st.ordered_speed = 1.0
    return g


def test_ice_overhead_blocks_the_periscope_and_is_noted():
    g = _arctic()
    ice, st = g.world.env.ice, g.world.own.state
    if ice.is_open(st.x, st.y):
        ice.thickness[ice._cell(st.x, st.y)] = 3.0
    g.command("periskop")
    assert g.knowledge.periscope_blocked is not None
    assert g.knowledge.periscope is None


def test_periscope_sees_the_ice_around_an_opening():
    g = _arctic()
    ice, st = g.world.env.ice, g.world.own.state
    ice.carve_polynya(st.x, st.y, 0.15)
    _look(g)
    pic = g.knowledge.periscope
    assert pic is not None and len(pic.ice) == 16
    edges = [i.edge_nm for i in pic.ice if i.edge_nm is not None]
    assert len(edges) >= 12 and all(0.08 < e < 0.3 for e in edges)
    rows = [r.plain for r in render_periscope(pic, 100, 30, None, 0)]
    eye = "\n".join(rows[4:-1])
    assert "▂" in eye and "^" in rows[1]
