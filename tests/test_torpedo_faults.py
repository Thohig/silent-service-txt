"""Egna torpeder: gyrofel, blindgångare och förtidsdetonationer."""
import random
import statistics

import pytest

from sim import weapons
from sim.entities import Vessel
from sim.environment import Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.geo import angle_diff
from sim.ownship import OwnShip
from sim.scenario import default_scenario
from sim.ship import ShipState
from sim.stations import TorpedoRoom
from sim.weapons import TORPEDO_TYPES, launch_torpedo
from sim.world import World


def _world(seed, tx=10.0, ty=11.0):
    own = OwnShip(ShipState(x=10, y=10, course=0, speed=0, depth=15))
    dd = Vessel("DD1", "destroyer", ShipState(x=tx, y=ty, course=90, speed=0))
    return World(own=own, contacts=[dd], env=Environment(current_kn=0.0), rng=random.Random(seed)), dd


def test_gyro_spreads_the_course_over_many_shots():
    errs = []
    for seed in range(400):
        w, _ = _world(seed)
        t = launch_torpedo(w, TORPEDO_TYPES["53-61"], 0.0)
        errs.append(angle_diff(t.state.course, 0.0))
    assert abs(statistics.mean(errs)) < 0.06
    assert 0.33 <= statistics.stdev(errs) <= 0.47


def test_duds_and_prematures_are_rare_and_only_with_a_warhead():
    n = 4000
    duds = prem = 0
    for seed in range(n):
        w, _ = _world(seed)
        t = launch_torpedo(w, TORPEDO_TYPES["53-61"], 0.0)
        duds += t.dud
        if t.premature_nm is not None:
            prem += 1
            assert weapons.ARM_DISTANCE_NM <= t.premature_nm <= t.spec.range_nm
    assert 0.04 <= duds / n <= 0.06
    assert 0.012 <= prem / n <= 0.028
    for key in ("övning", "T-5"):
        for seed in range(200):
            w, _ = _world(seed)
            t = launch_torpedo(w, TORPEDO_TYPES[key], 0.0)
            assert not t.dud and t.premature_nm is None


def _run(w, n):
    for _ in range(n):
        w.tick()


def test_a_dud_hits_the_hull_without_sinking_it():
    w, dd = _world(1)
    t = launch_torpedo(w, TORPEDO_TYPES["53-61"], 0.0)
    t.state.course = t.state.ordered_course = 0.0
    t.dud, t.premature_nm = True, None
    _run(w, 200)
    assert t.done and not dd.sunk
    assert w.mission["duds"] == 1 and "sunk" not in w.mission


def test_a_premature_detonates_short_of_the_target():
    w, dd = _world(1)
    t = launch_torpedo(w, TORPEDO_TYPES["53-61"], 0.0)
    t.state.course = t.state.ordered_course = 0.0
    t.dud, t.premature_nm = False, 0.5
    _run(w, 200)
    assert t.done and not dd.sunk
    assert 0.5 <= t.run_nm < 0.6


@pytest.mark.slow
def test_sonar_hears_the_dud_and_the_torpedo_room_says_so():
    g = Game(default_scenario(random.Random(4)), seed=4)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    w = g.world
    w.ais.clear()
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    dd = w.contacts[0]
    for v in w.contacts[1:]:
        v.sunk = True
    o = w.own.state
    dd.state.x, dd.state.y, dd.state.speed = o.x, o.y + 1.0, 0.0
    dd.state.order_speed(0)
    tor = g.station(TorpedoRoom)
    tor.tubes[0].load = "53-61"
    g.command("eld tub 1 kurs 000")
    t = next(v for v in w.contacts if isinstance(v, weapons.Torpedo))
    t.dud, t.premature_nm = True, None
    for _ in range(300):
        g.tick()
        dd.state.speed = 0.0
    assert t.done and not dd.sunk
    types = [r.type for r in reports]
    assert "torp.run.dud" in types and "torp.run.hit" not in types
    r = next(r for r in reports if r.type == "torp.run.dud")
    assert r.text.startswith("Tub 1:") and "Blindgångare" in r.text


def _passes(offset_m, aspect):
    """En torped som passerar fartygets mitt på offset_m meter, från sidan (aspect 'beam') eller
    rakt förifrån ('bow')."""
    w, dd = _world(1)
    dd.state.course = 90.0 if aspect == "beam" else 180.0     # torpeden går norrut
    off = offset_m / weapons.NM_IN_M
    p0, p1 = (dd.state.x + off, dd.state.y - 0.01), (dd.state.x + off, dd.state.y + 0.01)
    return weapons.hull_pass(p0, p1, dd)


def test_the_hull_is_long_and_narrow():
    # jagaren (halva längden 57 m, halva bredden 6 m, pistolen 10 m)
    assert _passes(60, "beam") <= 1.0          # från sidan: träff 60 m från mitten
    assert _passes(70, "beam") > 1.0
    assert _passes(12, "bow") <= 1.0           # förifrån: bara mitt på
    assert _passes(20, "bow") > 1.0
