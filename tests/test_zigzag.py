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


def _plotted(g, desig, dx, dy, classification, quality=Quality.GOD):
    """En kontakt med en plottad lösning dx, dy nm från vårt beräknade läge."""
    from sim.knowledge import ContactTrack
    from sim.tma import Solution
    ex, ey = g.own_position_estimate()
    tr = g.knowledge.tracks.get(desig) or ContactTrack(desig, g.now)
    g.knowledge.tracks[desig] = tr
    tr.classification, tr.class_quality = classification, Quality.GOD
    tr.solution = Solution(t=g.now, t_ref=g.now, state=(ex + dx, ey + dy, 0.0, 0.0), x=ex + dx,
                           y=ey + dy, course=180.0, speed=0.0, range_nm=math.hypot(dx, dy),
                           bearing=0.0, range_sigma=0.2, course_sigma=10.0, speed_sigma=1.0,
                           quality=quality, n_obs=20, span_s=900, own_maneuvered=True,
                           rms_residual=1.0)
    return tr


def _at_periscope_depth(g):
    g.command("periskopdjup")
    g.world.own.state.depth = 16
    g.command("fart 3")
    g.world.own.state.speed = 3.0


def test_officer_suggests_a_look_before_the_shot_when_a_big_ship_is_close():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x - 1.0, o0.y + 14.0)
    _at_periscope_depth(g)
    _plotted(g, "S-7", 0.0, 2.5, "stort fartyg, trolig transport")
    _ticks(g, 70)
    sug = [r for r in reports if r.type == "off.suggest.fire_look"]
    assert sug and "[ja: periskop S-7]" in sug[0].text and "2,5 sjömil" in sug[0].text
    assert "jagare" not in sug[0].text
    assert not any(r.type == "off.suggest.convoy_look" for r in reports)


def test_look_before_the_shot_names_a_close_escort_instead_of_staying_quiet():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x - 1.0, o0.y + 14.0)
    _at_periscope_depth(g)
    _plotted(g, "S-7", 0.0, 2.5, "stort fartyg, trolig transport")
    _plotted(g, "S-9", 1.5, 0.0, "jagare")
    _ticks(g, 70)
    sug = [r for r in reports if r.type == "off.suggest.fire_look"]
    assert sug and "jagare S-9 på 1,5 sjömil" in sug[0].text


def test_no_look_before_the_shot_on_a_far_target_or_a_poor_solution():
    o0 = default_scenario(random.Random(3)).world.own.state
    g, reports = _game_with_convoy_estimate(o0.x - 1.0, o0.y + 14.0)
    _at_periscope_depth(g)
    _plotted(g, "S-7", 0.0, 6.0, "stort fartyg, trolig transport")
    _plotted(g, "S-8", 0.0, 2.0, "stort fartyg, trolig transport", quality=Quality.DALIG)
    _ticks(g, 70)
    assert not any(r.type == "off.suggest.fire_look" for r in reports)


def _room_with_track(seed=1):
    from sim.events import ContactDetected
    from sim.stations import TorpedoRoom
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.bus.publish(ContactDetected(g.now, "S-1", 10.0, "jagare", Quality.GOD))
    return g, g.station(TorpedoRoom), g.knowledge.track("S-1"), reports


def _warnings(g, reports):
    for _ in range(5):
        g.tick()
    return [r for r in reports if r.type == "torp.leg_warning"]


def test_a_ship_with_two_marked_turns_gets_the_leg_warning_too():
    g, room, tr, reports = _room_with_track()
    tr.turns = [g.now - 900, g.now - 400]               # ben ~8 min, senaste giren för 400 s sedan
    room._leg_warning("S-1", 300.0, "53-61")            # 100 s kvar av benet, gångtid 5 min
    w = _warnings(g, reports)
    assert len(w) == 1 and "sicksackar" in w[0].text and "Den kan ha girat" in w[0].text
    assert "målsökande torped har större chans" in w[0].text
    room._leg_warning("S-1", 60.0, "53-61")             # hinner fram
    assert len(_warnings(g, reports)) == 1


def test_a_hunting_destroyer_turns_all_the_time():
    from sim.tma import BearingObs
    g, room, tr, reports = _room_with_track()
    g.knowledge.hunt_t = g.now
    tr.observations.append(BearingObs(g.now, 10.0, 0.5, 0.0, 0.0, 0.0, designation="S-1",
                                      source="ping"))
    room._leg_warning("S-1", 90.0, "53-61")             # kort gångtid: ingen varning
    room._leg_warning("S-1", 300.0, "SET-53")
    w = _warnings(g, reports)
    assert len(w) == 1 and "jagar och girar hela tiden" in w[0].text
    assert "söker själv" in w[0].text
