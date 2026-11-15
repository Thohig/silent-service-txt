"""Bryggan: luckan, utrymning före dykning och utkikens bild i ytläge."""
import random
import re

import pytest

from sim.air import Aircraft
from sim.events import BearingObserved, ReportDelivered
from sim.game import Game
from sim.ownship import BRIDGE_CLEAR_S, BRIDGE_MAN_S
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.bridge import JUDGE_EVERY_S


def _game(seed=3, day=True, dd_at=(4.0, 8.5)):
    """Kuba utan trafik och flyg; jagaren på avstånd och utan att kunna tvinga upp oss."""
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    for ai in w.ais:
        ai.can_force = False
    st = w.own.state
    dd = next(v for v in w.contacts if v.kind == "destroyer")
    dd.state.x, dd.state.y = st.x + dd_at[0], st.y + dd_at[1]
    if day:
        w.env.sunrise, w.env.sunset = 0, 24 * 3600
    else:
        w.env.sunrise = w.env.sunset = 0
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _surface(g):
    """Rakt upp i ytläge och vänta tills bryggan är bemannad."""
    st = g.world.own.state
    st.depth = st.ordered_depth = 0.0
    g.world.own.sys.bridge = "shut"
    for _ in range(BRIDGE_MAN_S + 3):
        g.tick()


def _types(reports):
    return [r.type for r in reports]


def test_bridge_is_manned_after_surfacing():
    g, reports = _game()
    assert g.world.own.sys.bridge == "shut"          # börjar på djupet
    st = g.world.own.state
    st.depth = st.ordered_depth = 0.0
    g.tick()
    assert g.world.own.sys.bridge == "manning"
    assert g.knowledge.bridge is None
    for _ in range(BRIDGE_MAN_S + 3):
        g.tick()
    assert g.world.own.sys.bridge == "manned"
    for _ in range(10):
        g.tick()
    assert "bridge.manned" in _types(reports)
    assert g.knowledge.bridge is not None and g.knowledge.bridge.eye == "brygga"


def test_dive_waits_until_the_bridge_is_cleared():
    g, reports = _game()
    _surface(g)
    st = g.world.own.state
    g.command("djup 60")
    for _ in range(BRIDGE_CLEAR_S - 2):
        g.tick()
        assert st.depth <= 1.0, "inte ned med folk på bryggan"
    assert g.world.own.sys.bridge == "clearing"
    assert g.knowledge.bridge is None, "ingen bild medan bryggan utryms"
    for _ in range(30):
        g.tick()
    assert g.world.own.sys.bridge == "shut"
    assert st.depth > 5.0
    types = _types(reports)
    assert types.index("bridge.clearing") < types.index("bridge.shut")


def test_dive_order_before_the_hatch_opens_dives_at_once():
    g, _ = _game()
    st = g.world.own.state
    st.depth = st.ordered_depth = 0.0
    g.tick()
    assert g.world.own.sys.bridge == "manning"
    g.command("djup 40")
    for _ in range(10):
        g.tick()
    assert g.world.own.sys.bridge == "shut" and st.depth > 3.0


def test_a_game_that_starts_surfaced_has_the_bridge_manned():
    g, _ = _game()
    from sim.ownship import OwnShip
    from sim.ship import ShipState
    own = OwnShip(ShipState(0.0, 0.0, 0.0, 0.0, depth=0.0))
    assert own.sys.bridge == "manned"
    assert g.world.own.sys.bridge == "shut"


def test_picture_uses_plot_designations_and_the_bridge_eye():
    g, reports = _game()
    _surface(g)
    pic = g.knowledge.bridge
    assert pic is not None and pic.day and pic.sector is None
    ships = pic.ships()
    assert ships, "jagaren nio sjömil bort ska synas från bryggan"
    truth_ids = {v.id for v in g.world.contacts}
    for o in ships:
        assert re.fullmatch(r"S-\d+", o.designation)
        assert o.designation not in truth_ids
    for _ in range(20):
        g.tick()
    assert any(r.type == "bridge.contact" for r in reports)
    for r in reports:
        for tid in truth_ids:
            assert tid not in r.text


def test_picture_is_updated_every_other_second_while_manned():
    g, _ = _game()
    _surface(g)
    times = set()
    for _ in range(10):
        g.tick()
        times.add(g.knowledge.bridge.t)
    assert len(times) == 5


def test_nothing_beyond_visibility():
    g, _ = _game(dd_at=(0.0, 30.0))
    _surface(g)
    assert g.knowledge.bridge.ships() == []


def test_night_shows_lights_only():
    g, reports = _game(day=False, dd_at=(0.0, 2.0))
    _surface(g)
    for _ in range(20):
        g.tick()
    ships = g.knowledge.bridge.ships()
    assert ships and all(o.visible == "ljus" and o.lights for o in ships)
    contact = next(r for r in reports if r.type == "bridge.contact")
    assert "lanternor" in contact.text


def test_plot_gets_one_observation_per_ship_and_minute():
    g, _ = _game()
    obs = []
    g.bus.subscribe(BearingObserved, lambda e: obs.append(e.obs)
                    if e.obs.source == "brygga" else None)
    _surface(g)
    for _ in range(3 * JUDGE_EVERY_S):
        g.tick()
    per = {}
    for o in obs:
        per.setdefault(o.designation, []).append(o)
    assert per
    for lst in per.values():
        assert 3 <= len(lst) <= 4
        assert all(o.course_obs is not None and o.range_nm is not None for o in lst)


def test_lookout_classification_is_not_downgraded_by_sonar():
    g, _ = _game()
    _surface(g)
    for _ in range(600):
        g.tick()
    desig = g.knowledge.bridge.ships()[0].designation
    tr = g.knowledge.tracks[desig]
    assert tr.class_quality >= Quality.GOD and "jagare" in tr.classification


def test_aircraft_in_sight_suggests_diving():
    g, reports = _game()
    _surface(g)
    st = g.world.own.state
    g.world.contacts.append(Aircraft("P1", st.x + 3.0, st.y, 270.0))
    for _ in range(4):
        g.tick()
    assert any(o.kind == "aircraft" for o in g.knowledge.bridge.objects)
    for _ in range(20):
        g.tick()
    assert "bridge.aircraft" in _types(reports)
    sug = next(r for r in reports if r.type == "bridge.suggest.dive")
    assert sug.alarm and "ja: djup 60" in sug.text


def test_russian_speech_for_bridge_reports_is_cyrillic():
    g, reports = _game(day=False, dd_at=(0.0, 2.0))
    _surface(g)
    for _ in range(20):
        g.tick()
    g.command("djup 60")
    for _ in range(BRIDGE_CLEAR_S + 10):
        g.tick()
    bridge = [r for r in reports if r.type.startswith("bridge.")]
    assert len({r.type for r in bridge}) >= 4
    for r in bridge:
        assert r.speech and not re.search(r"[A-Za-zÅÄÖåäö]", r.speech), (r.type, r.speech)


@pytest.mark.slow
def test_range_by_eye_is_rough_but_honest_over_seeds():
    """Avståndet med ögat: σ ≈ 15 % + 0,05 nm; kvaliteten följer felet."""
    rel = []
    for seed in range(8):
        g, _ = _game(seed=seed, dd_at=(1.5, 5.0))
        _surface(g)
        for _ in range(4):
            for _ in range(JUDGE_EVERY_S):
                g.tick()
            dd = next(v for v in g.world.contacts if v.kind == "destroyer")
            o = g.knowledge.bridge.ships()
            o = next(x for x in o if x.label == "jagare")
            r = g.world.true_range(dd)
            rel.append(abs(o.range_nm - r) / r)
            assert o.range_quality in (Quality.GOD, Quality.OSAKER)
    rel.sort()
    median = rel[len(rel) // 2]
    assert 0.03 < median < 0.2, median


# --- vyn (B2) ------------------------------------------------------------------------
from sim.periscope import PeriscopePicture, SightedObject  # noqa: E402
from ui.bridge_render import (FOV_DEG, focus_object, render_bridge,  # noqa: E402
                              render_scene, view_text)


def _obj(desig="S-1", bearing=20.0, rng=1.8, kind="destroyer", visible="helt", aob=70.0,
         lights=()):
    return SightedObject(kind, "jagare", bearing, rng, Quality.GOD, designation=desig,
                         visible=visible, aob=aob, course=250.0, speed=12, lights=lights)


def _bpic(*objs, day=True, course=0.0):
    return PeriscopePicture(100, day, 10.0 if day else 2.5, course, "brygga", tuple(objs))


def _plain(rows):
    return "\n".join(r.plain for r in rows)


def test_view_text():
    assert view_text(0) == "rakt förut"
    assert view_text(180) == "rakt akterut"
    assert view_text(45) == "styrbord 45°"
    assert view_text(300) == "babord 60°"


def test_focus_is_the_object_nearest_the_middle_of_the_view():
    a, b = _obj("S-1", 20.0), _obj("S-2", 95.0)
    pic = _bpic(a, b)
    assert focus_object(pic, 0.0) is None
    assert focus_object(pic, 15.0) is a
    assert focus_object(pic, 90.0) is b
    # blicken är relativ fören: vi går 080, S-2 i bäring 095 är 15° styrbord
    assert focus_object(_bpic(a, b, course=80.0), 15.0) is b


def test_scene_shows_ships_in_view_with_labels_and_the_bow_ahead():
    pic = _bpic(_obj("S-1", 20.0), _obj("S-4", 200.0))
    ahead = _plain(render_scene(pic, 110, 24, 0.0, 0))
    assert "S-1 1,8" in ahead and "S-4" not in ahead
    assert "▒" in ahead and "╤" in ahead, "fördäcket och räcket syns förut"
    astern = _plain(render_scene(pic, 110, 24, 180.0, 0, own_speed=8.0))
    assert "S-4" in astern and "S-1" not in astern
    assert "▒" not in astern and "≈" in astern, "akterut syns kölvattnet, inte fördäcket"


def test_far_ships_are_a_mark_and_night_ships_only_lights():
    far = _plain(render_scene(_bpic(_obj("S-1", 0.0, rng=9.0)), 110, 24, 0.0, 0))
    assert "▲" in far and "S-1 9,0" in far and "_|_" not in far
    night = _plain(render_scene(_bpic(_obj("S-1", 0.0, rng=2.0, visible="ljus",
                                           lights=("topp", "grön")), day=False),
                                110, 24, 0.0, 0))
    assert "●" in night and "_|_" not in night


def test_waves_move_with_time():
    pic = _bpic()
    assert _plain(render_scene(pic, 110, 24, 0.0, 0)) != _plain(render_scene(pic, 110, 24, 0.0, 4))


def test_full_view_has_scale_strip_and_data_line_without_truth():
    pic = _bpic(_obj("S-1", 20.0))
    rows = render_bridge(pic, 110, 30, 20.0, 0)
    txt = _plain(rows)
    assert "‹020›" in txt and "förut" in txt
    assert rows[-1].plain.startswith(" S-1 jagare · bäring 020")
    assert "DD" not in txt


def test_no_picture_says_why():
    assert "Under ytan" in _plain(render_bridge(None, 110, 30, 0.0, 0, depth=60.0))
    assert "öppnas" in _plain(render_bridge(None, 110, 30, 0.0, 0, status_bridge="manning"))
    assert "utryms" in _plain(render_bridge(None, 110, 30, 0.0, 0, status_bridge="clearing"))


def test_fov_is_wide():
    assert FOV_DEG >= 90


@pytest.mark.slow
def test_tab_reaches_the_bridge_view_and_arrows_turn_it(tmp_path):
    import asyncio

    from ui.app import SubApp
    from ui.bridge import BridgeScreen

    async def run():
        app = SubApp(seed=3, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("enter", "enter")
            g = app.game
            for ai in g.world.ais:
                ai.can_force = False
            g.world.env.sunrise, g.world.env.sunset = 0, 24 * 3600
            _surface(g)
            await pilot.press("tab", "tab", "tab", "tab", "tab")
            assert isinstance(app.screen, BridgeScreen)
            await pilot.pause(0.6)
            body = str(app.screen.query_one("#bridge-body").render())
            assert "╤" in body and "förut" in body
            await pilot.press("right", "right")
            assert app.screen.view_rel == pytest.approx(30.0)
            await pilot.press("space")
            assert app.screen.view_rel == 0.0
            app.save_screenshot(str(tmp_path / "brygga.svg"))
            await pilot.press("tab")
            assert not isinstance(app.screen, BridgeScreen)

    asyncio.run(run())
