"""Plottets konvojanalys: baskurs ur sicksackens ben, benlängd och gruppering."""
import pytest
import math
import random

from sim.convoy import ConvoyDef, make_convoy
from sim.events import ReportDelivered
from sim.game import Game
from sim.geo import angle_diff
from sim.reports import Quality
from sim.scenario import default_scenario
from sim.zigzag import LegFix, TrackPoint, base_course, groups, mean_leg


def _legs(base=200.0, speed=12.0, offsets=(30, -20, 10, -35, 25, -10), leg_s=480, noise=0.0,
          rng=None):
    x = y = 0.0
    t = 0
    out = []
    for off in offsets:
        c = math.radians(base + off)
        h = leg_s / 3600.0
        mx, my = x + speed * h / 2 * math.sin(c), y + speed * h / 2 * math.cos(c)
        if rng:
            mx += rng.gauss(0, noise)
            my += rng.gauss(0, noise)
        out.append(LegFix(t + leg_s // 2, mx, my, 0.1, base + off, speed))
        x, y, t = x + speed * h * math.sin(c), y + speed * h * math.cos(c), t + leg_s
    return out


def test_base_course_from_a_full_zigzag_cycle():
    b = base_course([_legs()])
    assert abs(angle_diff(b.course, 200.0)) < 5
    assert 9.5 < b.speed < 12.0                   # benfart längs baskursen
    assert b.legs == 6 and b.quality >= Quality.GOD


def test_two_legs_are_never_better_than_uncertain():
    b = base_course([_legs(offsets=(30, -30))])
    assert b.quality <= Quality.OSAKER


def test_quality_is_honest_over_noisy_legs():
    rng = random.Random(1)
    for _ in range(40):
        b = base_course([_legs(noise=0.4, rng=rng)])
        if b.quality >= Quality.GOD:
            assert abs(angle_diff(b.course, 200.0)) < 3 * b.sigma_deg + 5


def test_mean_leg_compares_turns_within_each_contact():
    a = [100, 580, 940, 1540]
    b = [220, 690, 1070, 1650]                    # samma girar, märkta senare
    assert 400 <= mean_leg([a, b]) <= 600


def test_groups_join_ships_with_same_motion_and_leave_escorts_out():
    pts = [TrackPoint("S-1", 0, 0, 200, 12, False), TrackPoint("S-2", 0.5, 0.3, 205, 11, False),
           TrackPoint("S-3", 9, 9, 200, 12, False), TrackPoint("S-4", 1, 2, 200, 14, True)]
    g = groups(pts)
    assert len(g) == 1 and {p.designation for p in g[0]} == {"S-1", "S-2"}


@pytest.mark.slow
def test_plot_finds_the_convoy_and_its_base_course_with_periscope_looks():
    errs = []
    for seed in (3, 5, 7):
        g = Game(default_scenario(random.Random(seed)), seed=seed)
        w = g.world
        w.contacts = [v for v in w.contacts if v.kind != "destroyer"]
        w.ais = [a for a in w.ais if getattr(getattr(a, "vessel", None), "kind", "") != "destroyer"]
        o = w.own.state
        o.depth = o.ordered_depth = 15.0
        o.speed = o.ordered_speed = 3.0
        w.env.sunrise, w.env.sunset = 0, 24 * 3600
        w.env.lat = None            # utan plats: ljuset följer sunrise/sunset
        make_convoy(w, ConvoyDef(start=(o.x + 7, o.y + 9), base_course=225.0), random.Random(seed))
        types = []
        g.bus.subscribe(ReportDelivered, lambda e: types.append(e.report.type))
        for t in range(100 * 60):
            g.tick()
            if t % 240 == 0:
                g.command("periskop")
        k = g.knowledge.convoy
        assert k is not None and len(k.members) >= 2
        assert "plot.convoy.found" in types and "plot.convoy.base" in types
        assert types.count("plot.maneuver") <= 4          # efter grupperingen sägs girarna som konvoj
        assert k.base is not None and k.base.quality >= Quality.GOD
        assert 8.0 < k.base.speed < 15.0
        assert 360 <= k.mean_leg_s <= 600
        errs.append(abs(angle_diff(k.base.course, 225.0)))
    assert max(errs) < 10


# --- anfall och torpedvarning (K3) -----------------------------------------------
import pytest  # noqa: E402

from sim.events import ConvoyAssessed  # noqa: E402
from sim.firecontrol import approach  # noqa: E402
from sim.stations import TorpedoRoom  # noqa: E402
from sim.stations.navigation import NavigationStation  # noqa: E402
from sim.zigzag import BaseCourse, ConvoyEstimate  # noqa: E402


def test_approach_puts_the_firing_point_beside_the_track_on_our_side():
    course, t_h, px, py, side = approach(3.0, 0.0, 0.0, 10.0, 0.0, -12.0, 5.0, 1.2)
    assert side == -1                     # vi ligger om babord om en sydgående konvoj
    assert px == pytest.approx(1.2)
    assert py == pytest.approx(10.0 - 12.0 * t_h)
    assert math.hypot(px - 3.0, py) == pytest.approx(5.0 * t_h, rel=1e-6)
    assert approach(0.0, 20.0, 0.0, 10.0, 0.0, -12.0, 5.0, 1.2) is None   # den har gått förbi


def _game_with_convoy_estimate(cx, cy, course=180.0, speed=12.0, mean_leg=480, last_turn=None):
    g = Game(default_scenario(random.Random(3)), seed=3)
    w = g.world
    w.contacts = [v for v in w.contacts if v.kind != "destroyer"]
    w.ais = [a for a in w.ais if getattr(getattr(a, "vessel", None), "kind", "") != "destroyer"]
    for d in ("S-1", "S-2"):
        g.knowledge.on_detection(d, 0)
    est = ConvoyEstimate(0, ("S-1", "S-2"), (), cx, cy, course, speed,
                         BaseCourse(course, speed, 6.0, Quality.GOD, 4), mean_leg, last_turn)
    g.bus.publish(ConvoyAssessed(0, est))
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_navigator_takes_us_to_a_firing_position_beside_the_convoy():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x - 1.0, o0.y + 14.0)
    g.command("fart 6")
    g.command("anfall S-1")
    nav = g.station(NavigationStation)
    assert nav.goal == "attack"
    for _ in range(60 * 60):
        g.tick()
        if nav.goal is None:
            break
    ex, ey = g.own_position_estimate()
    cx, cy, _vx, _vy = g.knowledge.convoy.advance(g.now)
    for _ in range(15):                                  # rapporterna levereras strax efter
        g.tick()
    types = [r.type for r in reports]
    assert "nav.attack" in types and "nav.attack.arrived" in types
    assert abs(ex - cx) <= 2.5                          # nära konvojens väg
    assert 0 <= cy - ey <= 12.0 * 8 / 60 + 0.1          # tvärs inom åtta minuter
    sug = [r for r in reports if r.type == "nav.suggest.attack_slow"]
    assert sug and "fart 3" in sug[0].text


def test_navigator_says_when_the_convoy_has_passed():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x + 0.5, o0.y - 2.0)
    g.command("anfall S-2")
    for _ in range(120):
        g.tick()
    assert "nav.attack.passed" in [r.type for r in reports]
    assert g.station(NavigationStation).goal is None


def test_torpedo_room_warns_when_the_leg_may_end_before_the_torpedo_arrives():
    g, reports = _game_with_convoy_estimate(0.0, 0.0, mean_leg=480, last_turn=-400)
    room = g.station(TorpedoRoom)
    room._leg_warning("S-1", 300.0, "53-61")             # 80 s kvar av benet, gångtid 5 min
    room._leg_warning("S-2", 30.0, "53-61")              # hinner fram
    for _ in range(5):
        g.tick()
    warn = [r for r in reports if r.type == "torp.leg_warning"]
    assert len(warn) == 1 and "S-1" in warn[0].text and "girat" in warn[0].text


def test_plot_forgets_the_convoy_when_its_ships_are_lost():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, _reports = _game_with_convoy_estimate(o0.x - 1.0, o0.y + 14.0)
    for d in ("S-1", "S-2"):
        g.knowledge.track(d).held = False
    for _ in range(1900):                       # längre än FORGET_S utan observationer
        g.tick()
    assert g.knowledge.convoy is None
    g.command("anfall S-1")                     # navigatören anfaller inte en gammal bild
    assert g.station(NavigationStation).goal is None


# --- besättningen föreslår vägen till skjutläge -------------------------------------
def _ticks(g, n):
    for _ in range(n):
        g.tick()


def test_navigator_suggests_an_attack_when_the_convoy_is_ahead():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x - 1.0, o0.y + 14.0)
    _ticks(g, 70)
    sug = [r for r in reports if r.type == "nav.suggest.attack"]
    assert sug and "[ja: anfall S-1]" in sug[0].text and "konvojen" in sug[0].text


def test_navigator_does_not_suggest_an_attack_on_a_convoy_that_has_passed():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x + 0.5, o0.y - 4.0)
    _ticks(g, 70)
    assert not any(r.type == "nav.suggest.attack" for r in reports)


def test_officer_suggests_periscope_depth_and_then_short_looks_at_the_convoy():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x - 1.0, o0.y + 14.0)
    g.command("djup 80")
    g.world.own.state.depth = 80
    _ticks(g, 70)
    assert any(r.type == "off.suggest.convoy_up" and "[ja: periskopdjup]" in r.text
               for r in reports)
    g.command("periskopdjup")
    g.world.own.state.depth = 16
    _ticks(g, 70)
    assert any(r.type == "off.suggest.convoy_look" and "[ja: periskop S-1]" in r.text
               for r in reports)


def test_officer_does_not_suggest_going_up_while_hunted():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x - 1.0, o0.y + 14.0)
    g.command("djup 80")
    g.world.own.state.depth = 80
    for t in range(0, 70, 10):
        g.knowledge.hunt_t = g.now
        _ticks(g, 10)
    assert not any(r.type == "off.suggest.convoy_up" for r in reports)
