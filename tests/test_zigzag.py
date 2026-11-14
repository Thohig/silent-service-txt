"""Plottets konvojanalys: baskurs ur sicksackens ben, benlängd och gruppering."""
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
        assert types.count("plot.maneuver") <= 2          # konvojens girar sägs som konvoj
        assert k.base is not None and k.base.quality >= Quality.GOD
        assert 8.0 < k.base.speed < 15.0
        assert 360 <= k.mean_leg_s <= 600
        errs.append(abs(angle_diff(k.base.course, 225.0)))
    assert max(errs) < 10
