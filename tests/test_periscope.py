"""Periskopbilden: synlig del, vinkel på bogen, lanternor och kunskapens senaste bild."""
import random

import pytest

from sim.game import Game
from sim.geo import angle_diff
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
        w.env.lat = None            # utan plats: ljuset följer sunrise/sunset
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
    """Långt bort syns bara överbyggnaden: kursbedömningen sprider mer. Jagaren hålls på
    kurs 270 under svepet, så att felet är utkikens och inte en gir."""
    near, far = [], []
    for seed in range(12):
        for rng_nm, out in ((2.0, near), (7.5, far)):
            g = _game_at_periscope_depth(seed=seed, day=True, dd_range=rng_nm)
            g.world.env.day_visibility_nm = 12.0
            v = next(v for v in g.world.contacts if v.kind == "destroyer")
            g.command("periskop")
            for _ in range(20):
                v.state.course = v.state.ordered_course = 270.0
                g.tick()
            dd = next(o for o in g.knowledge.periscope.ships() if o.kind == "destroyer")
            out.append((dd.visible, abs(angle_diff(dd.course, 270.0))))
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
            await pilot.press("tab", "tab", "tab", "tab")   # sjökort, sonar, ubåten, periskop
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
from sim.stations.periscope import PeriscopeWatch, SHORT_LOOK_S  # noqa: E402


def test_short_look_parses_bearing_and_contact():
    g = _game_at_periscope_depth(day=True)
    g.command("periskop 180")
    ps = g.station(PeriscopeWatch)
    assert ps.mode == "look" and ps.train == 180
    assert ps.t_end == g.now + SHORT_LOOK_S
    g2 = _game_at_periscope_depth(day=True)
    g2.command("periskop S-7")
    assert g2.station(PeriscopeWatch).mode is None     # ingen sådan kontakt


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


# --- periskopet i realtid (L1) ------------------------------------------------------
from sim.events import BearingObserved, PeriscopeSighted  # noqa: E402
from sim.stations.periscope import LOOK_S  # noqa: E402


def _frames(g):
    out = []
    g.bus.subscribe(PeriscopeSighted, out.append)
    return out


def _periscope_obs(g):
    out = []
    g.bus.subscribe(BearingObserved,
                    lambda e: out.append(e.obs) if e.obs.source == "periskop" else None)
    return out


def test_sweep_gives_live_frames_then_a_full_picture():
    g = _game_at_periscope_depth(day=True)
    frames = _frames(g)
    g.command("periskop")
    trains = []
    for _ in range(LOOK_S):
        g.tick()
        trains.append(g.station(PeriscopeWatch).train)
    live = [e for e in frames if e.live]
    done = [e for e in frames if not e.live]
    assert len(live) >= LOOK_S // 2 - 1 and len(done) == 1
    assert done[0].picture.sector is None                 # helt svep
    assert all(e.picture.sector is not None for e in live)   # okularet under svepet
    assert g.station(PeriscopeWatch).mode is None
    assert not g.world.own.masts_up(g.now + 1)
    # okularet har gått runt
    steps = [(b - a) % 360 for a, b in zip(trains, trains[1:])]
    assert sum(steps) > 300 and all(0 < s <= 30 for s in steps)


def test_short_look_sees_only_its_sector_live():
    g = _game_at_periscope_depth(day=True)          # jagaren rakt norrut
    frames = _frames(g)
    g.command("periskop 180")
    for _ in range(SHORT_LOOK_S):
        g.tick()
    assert frames and all(not e.picture.ships() for e in frames)
    assert frames[-1].picture.sector == 180 and not frames[-1].live


def test_one_judgement_and_one_plot_observation_per_look():
    """Under ett svep står bedömningen still (bilden fladdrar inte), och plottet får
    en observation per fartyg och titt, med samma värden som bilden."""
    g = _game_at_periscope_depth(day=True)
    frames, obs = _frames(g), _periscope_obs(g)
    g.command("periskop")
    for _ in range(LOOK_S):
        g.tick()
    dd = [o for e in frames for o in e.picture.ships() if o.kind == "destroyer"]
    assert len({(round(o.course, 3), o.speed) for o in dd}) == 1
    mine = [o for o in obs if o.designation == dd[0].designation]
    assert len(mine) == 1
    assert mine[0].course_obs == pytest.approx(dd[-1].course)
    # en ny titt är en ny bedömning
    g.command("periskop")
    for _ in range(LOOK_S):
        g.tick()
    mine = [o for o in obs if o.designation == dd[0].designation]
    assert len(mine) == 2 and mine[1].course_obs != mine[0].course_obs


def test_hold_keeps_the_mast_up_and_turns_where_ordered():
    g = _game_at_periscope_depth(day=True)
    frames, obs = _frames(g), _periscope_obs(g)
    g.command("periskop upp")
    ps = g.station(PeriscopeWatch)
    g.command("vrid periskop 180")
    for _ in range(30):
        g.tick()
        assert g.world.own.masts_up(g.now)
    assert ps.mode == "hold" and ps.train == 180
    assert not any(e.picture.ships() for e in frames)      # jagaren är rakt norrut
    g.command("vrid periskop 000")
    for _ in range(4):
        g.tick()
    assert frames[-1].live and frames[-1].picture.ships()
    dd = next(o for o in frames[-1].picture.ships() if o.kind == "destroyer").designation
    assert sum(o.designation == dd for o in obs) == 1
    # i hålläge kommer en ny bedömning efter en minut
    for _ in range(62):
        g.tick()
    assert sum(o.designation == dd for o in obs) == 2
    g.command("periskop ned")
    assert ps.mode is None and not frames[-1].live
    g.tick()
    assert not g.world.own.masts_up(g.now)


def test_hold_comes_down_when_we_go_deep_or_fast():
    g = _game_at_periscope_depth()
    reports = []
    g.bus.subscribe(__import__("sim.events", fromlist=["ReportDelivered"]).ReportDelivered,
                    lambda e: reports.append(e.report.type))
    g.command("periskop upp")
    g.tick()
    g.world.own.state.speed = 9.0
    g.tick()
    ps = g.station(PeriscopeWatch)
    assert ps.mode is None
    g.world.own.state.speed = 3.0
    g.command("periskop upp")
    g.tick()
    g.world.own.state.depth = 40.0
    g.tick()
    assert ps.mode is None
    for _ in range(30):
        g.tick()
    assert reports.count("off.periscope.lowered") == 2


def test_turning_takes_over_a_sweep_and_is_refused_when_down():
    g = _game_at_periscope_depth(day=True)
    reports = []
    g.bus.subscribe(__import__("sim.events", fromlist=["ReportDelivered"]).ReportDelivered,
                    lambda e: reports.append(e.report.type))
    g.command("vrid periskop 090")
    ps = g.station(PeriscopeWatch)
    assert ps.mode is None
    g.command("periskop")
    g.tick()
    g.command("vrid periskop 090")
    assert ps.mode == "hold" and ps.train == 90
    for _ in range(30):
        g.tick()
    assert "off.periscope.is_down" in reports


# --- den levande vyn (L2) --------------------------------------------------------------
from ui.periscope_render import header, in_eyepiece  # noqa: E402


def test_eyepiece_follows_the_aim_not_the_selection():
    pic = _pic(_ship("S-1", 10.0), _ship("S-2", 200.0, rng=6.0, visible="överbyggnad"))
    assert in_eyepiece(pic, 15.0).designation == "S-1"
    assert in_eyepiece(pic, 100.0) is None
    rows = [r.plain for r in render_periscope(pic, 100, 30, 0, 0, aim=195.0)]
    assert "S-2 jagare" in rows[-1]
    rows = [r.plain for r in render_periscope(pic, 100, 30, 0, 0, aim=100.0)]
    assert "Inget i okularet" in rows[-1]
    eye = "\n".join(rows[4:-1])
    assert "\\" not in eye and "/" not in eye           # inga siluetter mot 100°


def test_header_shows_the_mast_up():
    t = header(_pic(), "05:00:00", 0, None, ("hold", 75, 47.0)).plain
    assert "UPPE 1:15" in t and "hålls uppe" in t and "okular 047" in t


def test_turning_the_periscope_is_not_counted_as_an_order():
    g = _game_at_periscope_depth()
    before = g.logbook.orders
    g.command("periskop upp")
    g.command("vrid periskop 090")
    g.command("vrid periskop 095")
    assert g.logbook.orders == before + 1
    st = g.status()
    assert st.periscope == "hold" and st.periscope_train == 95


@pytest.mark.slow
def test_live_periscope_view_turns_with_the_arrows(tmp_path):
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
            dd.state.x, dd.state.y = st.x, st.y + 1.5          # rakt norrut
            app.action_periscope()
            await pilot.pause(0.1)
            assert isinstance(app.screen, PeriscopeScreen)
            await pilot.press("up")
            assert g.status().periscope == "hold"
            g.command("vrid periskop 000")
            for _ in range(4):
                g.tick()
            await pilot.pause(0.6)
            head = str(app.screen.query_one("#periscope-head").render())
            assert "UPPE" in head and "okular 000" in head
            body = str(app.screen.query_one("#periscope-body").render())
            assert "Inget i okularet" not in body
            app.save_screenshot(str(tmp_path / "periskop-uppe.svg"))
            await pilot.press("right", "right")
            assert g.status().periscope_train == 10
            await pilot.press("down")
            assert g.status().periscope is None

    asyncio.run(run())


# --- L4: korta utrop, mastvarning --------------------------------------------------
from sim.events import ReportDelivered  # noqa: E402


def _report_types(g):
    out = []
    g.bus.subscribe(ReportDelivered, lambda e: out.append(e.report.type))
    return out


def test_a_second_look_soon_after_gives_a_short_report():
    g = _game_at_periscope_depth(day=True)
    types = _report_types(g)
    v = next(v for v in g.world.contacts if v.kind == "destroyer")
    for _ in range(2):
        g.command("periskop")
        for _ in range(LOOK_S + 30):
            v.state.course = v.state.ordered_course = 270.0
            g.tick()
    assert types.count("off.periscope.contact") >= 1
    assert "off.periscope.again" in types
    # den korta rapporten är inte det första om jagaren
    assert types.index("off.periscope.contact") < types.index("off.periscope.again")


def test_crew_suggests_lowering_a_mast_held_up_with_a_threat_in_the_plot():
    g = _game_at_periscope_depth(day=True)
    types = _report_types(g)
    g.command("periskop upp")
    g.command("vrid periskop 000")          # jagaren rakt norrut: nu ett hot i plottet
    for _ in range(90):
        g.tick()
    assert any(t.threat for t in g.knowledge.tracks.values())
    assert "off.suggest.mast_down" in types
    assert g.active_suggestion()[0] == "periskop ned"
    g.command("ja")
    assert g.station(PeriscopeWatch).mode is None


def test_lookout_ranges_in_strip_and_eyepiece():
    from ui.periscope_render import render_periscope
    pic = _pic(_ship("S-1", 10.0), _ship("S-2", 200.0, rng=6.0, visible="överbyggnad"))
    rows = [r.plain for r in render_periscope(pic, 100, 30, 0, 0)]
    assert "S-1 1,5" in rows[0] and "S-2 6,0" in rows[0]
    eye = "\n".join(rows[3:-1])
    assert "6,0 nm" in eye                     # det valda föremålets avstånd i okularet
