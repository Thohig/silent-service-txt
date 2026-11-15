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
