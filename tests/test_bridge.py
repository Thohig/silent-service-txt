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
        w.env.lat = None            # utan plats: ljuset följer sunrise/sunset
    else:
        w.env.sunrise = w.env.sunset = 0
        w.env.lat = None            # utan plats: ljuset följer sunrise/sunset
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
    """Avståndet i kikaren: σ ≈ 12 % + 0,03 nm; kvaliteten följer felet (god, inte säker)."""
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


def _braille(s: str) -> int:
    return sum(0x2800 < ord(ch) <= 0x28FF for ch in s)


def test_scene_shows_ships_in_view_with_labels_and_the_bow_ahead():
    pic = _bpic(_obj("S-1", 20.0), _obj("S-4", 200.0))
    ahead = _plain(render_scene(pic, 110, 24, 0.0, 0))
    assert "S-1 1,8" in ahead and "S-4" not in ahead
    assert "▒" in ahead and "╤" in ahead, "fördäcket och räcket syns förut"
    astern = _plain(render_scene(pic, 110, 24, 180.0, 0, own_speed=8.0))
    still = _plain(render_scene(pic, 110, 24, 180.0, 0, own_speed=0.0))
    assert "S-4" in astern and "S-1" not in astern
    assert astern.count("▒") < ahead.count("▒") // 2, "akterut inget fördäck"
    assert _braille(astern) > _braille(still) + 30, "akterut syns kölvattnet (prickar)"


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
    from ui.periscope import PeriscopeScreen

    async def run():
        app = SubApp(seed=3, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("enter", "enter")
            g = app.game
            for ai in g.world.ais:
                ai.can_force = False
            g.world.env.sunrise, g.world.env.sunset = 0, 24 * 3600
            g.world.env.lat = None            # utan plats: ljuset följer sunrise/sunset
            _surface(g)
            await pilot.press("tab", "tab", "tab", "tab")   # sjökort, sonar, ubåten; i ytläge före periskopet
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
            assert isinstance(app.screen, PeriscopeScreen)
            await pilot.press("tab")
            assert not isinstance(app.screen, (BridgeScreen, PeriscopeScreen))

    asyncio.run(run())


# --- land, händelser och torpedspår (B3) -------------------------------------------
from sim import acoustics  # noqa: E402
from sim.entities import Transient  # noqa: E402
from sim.periscope import LandBearing  # noqa: E402
from sim.weapons import TORPEDO_TYPES, launch_torpedo  # noqa: E402


def _emit_and_look(g, tr, ticks=3):
    g.world.emit(tr)
    for _ in range(ticks):
        g.tick()
    return g.knowledge.bridge


def test_depth_charge_gives_a_water_column_and_a_call_out():
    g, reports = _game()
    _surface(g)
    st = g.world.own.state
    pic = _emit_and_look(g, Transient("explosion", st.x + 0.5, st.y + 1.0, 50.0,
                                      acoustics.EXPLOSION_REAL, "DD1", g.now))
    cols = [o for o in pic.objects if o.kind == "column"]
    assert len(cols) == 1 and cols[0].designation is None and cols[0].detail == ""
    assert abs(cols[0].range_nm - 1.12) < 0.6
    for _ in range(15):
        g.tick()
    assert "bridge.column" in _types(reports)
    assert not any(o.kind == "column" for o in g.knowledge.bridge.objects), "pelaren är borta"


def test_practice_charge_is_marked_and_a_splash_is_seen_by_day_only():
    g, _ = _game()
    _surface(g)
    st = g.world.own.state
    pic = _emit_and_look(g, Transient("explosion", st.x, st.y + 1.0, 50.0,
                                      acoustics.EXPLOSION_PRACTICE, "DD1", g.now, practice=True))
    assert next(o for o in pic.objects if o.kind == "column").detail == "övning"
    pic = _emit_and_look(g, Transient("splash", st.x, st.y + 1.0, 0.0, acoustics.SPLASH_LEVEL,
                                      "DD1", g.now))
    assert any(o.kind == "splash" for o in pic.objects)
    g, _ = _game(day=False)
    _surface(g)
    st = g.world.own.state
    pic = _emit_and_look(g, Transient("splash", st.x, st.y + 1.0, 0.0, acoustics.SPLASH_LEVEL,
                                      "DD1", g.now))
    assert not any(o.kind == "splash" for o in pic.objects)


def test_torpedo_wake_is_seen_close_by_day_but_not_for_the_electric_torpedo():
    g, _ = _game()
    _surface(g)
    launch_torpedo(g.world, TORPEDO_TYPES["53-61"], 90.0)
    for _ in range(40):                 # 45 kn: 0,5 nm på 40 s
        g.tick()
    wakes = [o for o in g.knowledge.bridge.objects if o.kind == "wake"]
    assert len(wakes) == 1 and 60 < wakes[0].bearing < 120
    g, _ = _game()
    _surface(g)
    launch_torpedo(g.world, TORPEDO_TYPES["SET-53"], 90.0)
    for _ in range(40):
        g.tick()
    assert not any(o.kind == "wake" for o in g.knowledge.bridge.objects)


def test_torpedo_hit_is_fire_and_smoke():
    g, reports = _game()
    _surface(g)
    t = launch_torpedo(g.world, TORPEDO_TYPES["53-61"], 0.0)
    st = g.world.own.state
    pic = _emit_and_look(g, Transient("explosion", st.x, st.y + 2.0, 5.0,
                                      acoustics.EXPLOSION_TORPEDO, t.id, g.now))
    assert any(o.kind == "hit" for o in pic.objects)
    for _ in range(10):
        g.tick()
    assert "bridge.hit" in _types(reports)


def test_land_is_seen_from_the_bridge_in_the_strait():
    g = Game(build_scenario("sundet", random.Random(3)), seed=3)
    for ai in g.world.ais:
        ai.can_force = False
    g.world.env.sunrise, g.world.env.sunset = 0, 24 * 3600
    g.world.env.lat = None            # utan plats: ljuset följer sunrise/sunset
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    _surface(g)
    for _ in range(10):
        g.tick()
    land = g.knowledge.bridge.land
    assert land, "kusten ligger inom sikt i sundet"
    assert all(lb.range_nm > 0 for lb in land)
    assert "bridge.land" in _types(reports)
    # i Kuba finns inget land
    g2, _ = _game()
    _surface(g2)
    assert g2.knowledge.bridge.land == ()


def test_scene_draws_land_and_events():
    land = tuple(LandBearing(float(b), 3.0) for b in range(330, 360, 3))
    objs = (SightedObject("column", "vattenpelare", 20.0, 1.5, Quality.GOD, seen_t=100),
            SightedObject("hit", "explosion", 10.0, 2.0, Quality.GOD, seen_t=100),
            SightedObject("wake", "torpedspår", 5.0, 0.3, Quality.GOD, aob=60.0, seen_t=100))
    pic = PeriscopePicture(100, True, 10.0, 0.0, "brygga", objs, land=land)
    txt = _plain(render_bridge(pic, 110, 30, 0.0, 100))
    bare = _plain(render_bridge(PeriscopePicture(100, True, 10.0, 0.0, "brygga", objs), 110, 30,
                                0.0, 100))
    assert _braille(txt) > _braille(bare) + 60, "landet är en silhuett i prickar"
    assert "▲▲▲" in txt and "===" in txt
    no_col = tuple(o for o in objs if o.kind != "column")
    without = _plain(render_bridge(PeriscopePicture(100, True, 10.0, 0.0, "brygga", no_col, land=land),
                                   110, 30, 0.0, 100))
    assert _braille(txt) > _braille(without) + 3, "vattenpelaren i prickar"
    later = _plain(render_scene(pic, 110, 24, 0.0, 130))
    assert "░" in later or "▒" in later, "röken stiger efter en stund"
    night = PeriscopePicture(100, False, 2.5, 0.0, "brygga", objs, land=land)
    ntxt = _plain(render_scene(night, 110, 24, 0.0, 100))
    assert "▲▲▲" in ntxt and "|||" not in ntxt and "░" not in ntxt


# --- kikaren: periskopets order med bryggan bemannad (L3) ----------------------------
from sim.events import BridgeSighted, PeriscopeSighted  # noqa: E402
from sim.stations.periscope import LOOK_S, PeriscopeWatch  # noqa: E402


def test_periscope_on_a_manned_bridge_is_the_binoculars_with_the_bridges_picture():
    g, reports = _game(dd_at=(0.5, 3.0))
    _surface(g)
    frames, obs, bridge_pics = [], [], []
    g.bus.subscribe(PeriscopeSighted, frames.append)
    g.bus.subscribe(BridgeSighted, lambda e: bridge_pics.append(e.picture))
    g.bus.subscribe(BearingObserved, lambda e: obs.append(e.obs.source))
    g.world.own.state.speed = g.world.own.state.ordered_speed = 10.0   # ingen fartgräns
    g.command("periskop")
    ps = g.station(PeriscopeWatch)
    assert ps.mode == "sweep" and ps.optic == "kikare"
    for _ in range(LOOK_S):
        g.tick()
        assert not g.world.own.masts_up(g.now)        # ingen mast: utkiken tittar
    done = [e for e in frames if not e.live]
    assert len(done) == 1 and done[0].picture.eye == "brygga"
    seen = done[0].picture.ships()
    judged = {(o.designation, o.course, o.speed, o.range_nm)
              for p in bridge_pics if p is not None for o in p.ships()}
    assert seen
    for o in seen:                                    # bryggans bedömning, inte en egen
        assert (o.designation, o.course, o.speed, o.range_nm) in judged
    assert "periskop" not in obs
    types = _types(reports)
    assert "off.binoculars.up" in types and "off.refused" not in types
    assert "off.periscope.contact" not in types       # utkiken har redan ropat ut


def test_binoculars_come_down_when_the_bridge_is_cleared():
    g, reports = _game()
    _surface(g)
    g.command("periskop upp")
    ps = g.station(PeriscopeWatch)
    assert ps.mode == "hold" and ps.optic == "kikare"
    g.command("djup 40")
    for _ in range(5):
        g.tick()
    assert ps.mode is None
    for _ in range(30):
        g.tick()
    assert "off.binoculars.down" in _types(reports)


def test_periscope_has_no_speed_limit_on_the_surface_with_the_hatch_shut():
    g, reports = _game()
    st = g.world.own.state
    st.depth = st.ordered_depth = 0.0
    st.speed = st.ordered_speed = 10.0
    g.world.own.sys.bridge = "shut"
    g.command("periskop")
    ps = g.station(PeriscopeWatch)
    assert ps.mode == "sweep" and ps.optic == "periskop"
    g2, _ = _game()
    st = g2.world.own.state
    st.depth = st.ordered_depth = 15.0
    st.speed = st.ordered_speed = 10.0
    g2.command("periskop")
    assert g2.station(PeriscopeWatch).mode is None    # under ytan: för fort


@pytest.mark.slow
def test_periscope_view_shows_the_bridge_and_shares_the_look(tmp_path):
    import asyncio

    from ui.app import SubApp
    from ui.bridge import BridgeScreen
    from ui.periscope import PeriscopeScreen

    async def run():
        app = SubApp(seed=3, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("enter", "enter")
            g = app.game
            g.world.env.sunrise, g.world.env.sunset = 0, 24 * 3600
            g.world.env.lat = None            # utan plats: ljuset följer sunrise/sunset
            st = g.world.own.state
            dd = next(v for v in g.world.contacts if v.kind == "destroyer")
            dd.state.x, dd.state.y = st.x + 2.0, st.y + 0.3        # tvärs styrbord
            for ai in g.world.ais:
                ai.can_force = False
            _surface(g)
            app.action_bridge()
            await pilot.pause(0.1)
            assert isinstance(app.screen, BridgeScreen)
            for _ in range(6):                                     # blicken 90° styrbord
                await pilot.press("right")
            app.action_periscope()
            await pilot.pause(0.6)
            assert isinstance(app.screen, PeriscopeScreen)
            head = str(app.screen.query_one("#periscope-head").render())
            assert "KIKARE" in head
            body = str(app.screen.query_one("#periscope-body").render())
            line = body.splitlines()[-1]
            assert "jagare" in line                                # det bryggan tittade på
            app.save_screenshot(str(tmp_path / "kikare.svg"))
            await pilot.press("space")                             # inget periskop: ingen effekt
            app.action_bridge()
            await pilot.pause(0.2)
            assert isinstance(app.screen, BridgeScreen)
            assert 60 <= app.screen.view_rel <= 120

    asyncio.run(run())


def test_the_last_bridge_picture_becomes_the_periscope_picture_on_diving():
    g, reports = _game(dd_at=(0.5, 3.0))
    _surface(g)
    assert g.knowledge.periscope is None
    last = g.knowledge.bridge
    g.command("djup 40")
    for _ in range(BRIDGE_CLEAR_S + 5):
        g.tick()
    assert g.knowledge.bridge is None
    pic = g.knowledge.periscope
    assert pic is not None and pic.eye == "brygga" and pic.t >= last.t
    assert pic.ships()


def test_eyepiece_has_a_soft_rim_waves_and_the_binoculars_land():
    from ui.periscope_render import render_eyepiece
    land = tuple(LandBearing(float(b), 2.0) for b in range(330, 391, 3))
    bare = PeriscopePicture(100, True, 10.0, 0.0, "kikare", ())
    with_land = PeriscopePicture(100, True, 10.0, 0.0, "kikare", (), land=land)
    plain = _plain(render_eyepiece(bare, 90, 20, None, False, aim=0.0))
    shore = _plain(render_eyepiece(with_land, 90, 20, None, False, aim=0.0))
    assert _braille(plain) > 40                           # kanten och vågorna i prickar
    assert _braille(shore) > _braille(plain) + 100        # landet som silhuett
    assert "┼" in shore                                   # siktet syns över landet


def test_sea_state_shows_in_the_picture_and_the_report():
    from dataclasses import replace

    from sim.periscope import PeriscopePicture
    from sim.stations.bridge import sea_words
    from ui.bridge_render import render_scene, swell_rows
    from ui.periscope_render import STYLE

    calm = PeriscopePicture(100, True, 10.0, 0.0, "brygga", sea_state=1)
    rough = replace(calm, sea_state=6)

    def dots(pic):
        rows = render_scene(pic, 100, 24, 0.0, 100)
        return sum(1 for r in rows[11:] for ch in r.plain if "⠀" < ch <= "⣿")

    assert dots(rough) > 2 * dots(calm)
    foam = lambda pic: any(STYLE["foam"] in str(sp.style)  # noqa: E731
                           for r in render_scene(pic, 100, 24, 0.0, 100) for sp in r.spans)
    assert foam(rough) and not foam(calm)
    assert swell_rows(3, 2) == 0 and {swell_rows(6, t) for t in range(9)} == {-1, 0, 1}
    assert sea_words(0) == "Spegelblankt" and sea_words(4) == "Måttlig sjö, vind 4"
    assert sea_words(6) == "Grov sjö, vind 6"


def test_bridge_reports_sea_when_manned():
    from sim.phrases import render
    from sim.reports import Report
    rep = render(Report(0, "Vakthavande", "bridge.manned", {"sea": 3}), str)
    assert rep.text.endswith("Måttlig sjö, vind 3.") and "Волнение 3 балла" in rep.speech


def test_lookout_judges_ships_through_the_binoculars():
    """Utkiken bedömer fartyg i kikaren: avståndets σ 12 % + 0,03 nm, inte ögats 15 % + 0,05."""
    from sim.stations.bridge import BINOC_RANGE_ABS, BINOC_RANGE_REL
    g, _ = _game()
    obs = []
    g.bus.subscribe(BearingObserved, lambda e: obs.append(e.obs)
                    if e.obs.source == "brygga" else None)
    _surface(g)
    for _ in range(5):
        g.tick()
    assert obs
    for o in obs:
        assert o.range_sigma == pytest.approx(BINOC_RANGE_REL * o.range_nm + BINOC_RANGE_ABS,
                                              rel=0.3)


def test_nothing_below_the_horizon_from_the_bridge():
    g, _ = _game(dd_at=(0.0, 18.0))
    g.world.env.day_visibility_nm = 25.0
    _surface(g)
    assert not any(o.kind == "destroyer" for o in g.knowledge.bridge.ships())


def test_bridge_view_binoculars_narrow_the_view():
    from ui.bridge_render import render_bridge
    g, _ = _game(dd_at=(0.0, 6.0))
    _surface(g)
    pic = g.knowledge.bridge
    eye = "\n".join(r.plain for r in render_bridge(pic, 100, 26, 0.0, g.now))
    glass = "\n".join(r.plain for r in render_bridge(pic, 100, 26, 0.0, g.now, binoculars=True))
    assert "░" in glass and glass != eye                    # okularets rör runt bilden
