"""Konvojen: formation, sicksack kring baskursen, nödgir och hur besättningen uppfattar den."""
import math
import random

import pytest

from sim.convoy import NODGIR_DEG, NODGIR_S, ZIGZAG_PLANS, ConvoyDef, make_convoy
from sim.events import ClassificationChanged, ContactDetected
from sim.game import Game
from sim.geo import angle_diff, bearing_to, distance, velocity
from sim.ownship import OwnShip
from sim.scenario import default_scenario
from sim.ship import ShipState
from sim.weapons import _sink
from sim.world import World

SEEDS = range(1, 7)


def _world(seed=1, base=160.0, plan=None):
    w = World(own=OwnShip(ShipState(x=0.0, y=-30.0, course=0, speed=0, depth=150)),
              rng=random.Random(seed), size_nm=60.0)
    c = make_convoy(w, ConvoyDef(start=(10.0, 20.0), base_course=base, plan=plan),
                    random.Random(seed))
    return w, c


def _run(w, n):
    for _ in range(n):
        w.tick()


def test_zigzag_plans_average_to_the_base_course():
    for plan in ZIGZAG_PLANS:
        side = sum(math.sin(math.radians(off)) * s for off, s in plan)
        along = sum(math.cos(math.radians(off)) * s for off, s in plan)
        assert abs(math.degrees(math.atan2(side, along))) < 3.0


def test_convoy_zigzags_around_the_base_course_and_keeps_formation():
    for seed in SEEDS:
        w, c = _world(seed)
        x0, y0 = c.x, c.y
        courses = set()
        worst = 0.0
        for t in range(3 * 3600):
            w.tick()
            courses.add(round(c.course))
            if t > 600:
                for v, slot in zip(c.vessels, c.cdef.ships):
                    px, py = c.station(slot)
                    worst = max(worst, distance(v.state.x, v.state.y, px, py))
        made_good = bearing_to(x0, y0, c.x, c.y)
        assert abs(angle_diff(made_good, 160.0)) < 6.0, seed
        assert len(courses) >= 4, seed                     # flera ben
        assert worst < 0.35, (seed, worst)                 # ingen tappar sin plats
        sog = distance(x0, y0, c.x, c.y) / 3.0
        assert 10.0 < sog < 12.0                           # sicksacken kostar fart


def test_sinking_a_ship_makes_the_convoy_turn_away_and_speed_up():
    w, c = _world(2, base=180.0, plan=0)
    _run(w, 120)
    before = c.course
    # fartyget om styrbord (västra kolumnen sett mot söder) sänks
    victim = next(v for v, s in zip(c.vessels, c.cdef.ships) if s.column == -1)
    side = angle_diff(bearing_to(c.x, c.y, victim.state.x, victim.state.y), c.course)
    _sink(w, victim)
    _run(w, 2)
    assert c.nodgir_count == 1
    turn = angle_diff(c.course, before)
    assert abs(turn) == pytest.approx(NODGIR_DEG, abs=0.5)
    assert turn * side < 0                                 # bort från hotet
    assert c.speed > c.cdef.speed
    _run(w, NODGIR_S + 30)
    assert c.speed == c.cdef.speed
    assert c.base_course == 180.0
    # samma sänkta fartyg ger ingen ny gir
    assert c.nodgir_count == 1


def test_crew_hears_and_classifies_the_convoy():
    g = Game(default_scenario(random.Random(3)), seed=3)
    o = g.world.own.state
    o.depth = o.ordered_depth = 150.0
    o.speed = o.ordered_speed = 4.0
    make_convoy(g.world, ConvoyDef(start=(o.x + 4.0, o.y + 5.0), base_course=200.0),
                random.Random(3))
    classes = []
    g.bus.subscribe(ContactDetected, lambda e: classes.append(e.classification))
    g.bus.subscribe(ClassificationChanged, lambda e: classes.append(e.classification))
    for _ in range(40 * 60):
        g.tick()
    text = " | ".join(classes)
    assert "trupptransport" in text or "tankfartyg" in text, text
    assert "K1" not in text


def test_periscope_names_convoy_ships():
    g = Game(default_scenario(random.Random(3)), seed=3)
    o = g.world.own.state
    o.depth = o.ordered_depth = 15.0
    o.speed = o.ordered_speed = 3.0
    g.world.env.sunrise, g.world.env.sunset = 0, 24 * 3600
    c = make_convoy(g.world, ConvoyDef(start=(o.x, o.y + 2.0), base_course=90.0),
                    random.Random(3))
    g.command("periskop")
    for _ in range(20):
        g.tick()
    labels = {ob.label for ob in g.knowledge.periscope.ships()}
    assert {"trupptransport", "tankfartyg"} <= labels
    assert all(not ob.designation.startswith("K") for ob in g.knowledge.periscope.ships())
    assert c.vessels


# --- eskort (K2) -----------------------------------------------------------------
from sim.convoy import GUARD_NM, ESCORT_LEASH_NM, make_escorts  # noqa: E402


def _escorted(seed=1, base=160.0):
    w, c = _world(seed, base=base)
    escorts = make_escorts(w, c, random.Random(seed))
    return w, c, escorts


def test_escorts_keep_their_screen_ahead_of_the_zigzagging_convoy():
    for seed in SEEDS:
        w, c, escorts = _escorted(seed)
        off = []
        for t in range(3600):
            w.tick()
            if t > 300 and t % 30 == 0:
                for e in escorts:
                    px, py = e.screen_point()
                    off.append(distance(e.vessel.state.x, e.vessel.state.y, px, py))
        assert all(e.state == "escort" and e.roe == "lethal" for e in escorts)
        assert sorted(off)[int(0.9 * len(off))] < 0.6, seed   # 9 av 10 nära platsen
        for e in escorts:                                      # framför konvojen
            b = bearing_to(c.x, c.y, e.vessel.state.x, e.vessel.state.y)
            assert abs(angle_diff(b, c.course)) < 70


def test_escort_ignores_a_datum_beyond_its_leash():
    w, c, (e1, e2) = _escorted()
    bx, by = c.x + ESCORT_LEASH_NM + 1.0, c.y
    e1._set_datum(w, bx, by, 100.0, 0.2, fix=True)
    assert e1.datum is None and e2.datum is None


def _datum_off_convoy(w, c, nm):
    """En punkt nm sjömil om styrbord om konvojen."""
    vx, vy = velocity(c.course + 90.0, 3600.0)
    return c.x + nm * vx, c.y + nm * vy


def test_only_one_escort_hunts_unless_the_threat_is_close():
    w, c, (e1, e2) = _escorted(2)
    _run(w, 120)
    x, y = _datum_off_convoy(w, c, 3.0)
    e1._set_datum(w, x, y, 100.0, 0.5, fix=True)          # delas med e2 över radio
    assert e2.datum is not None
    _run(w, 30)
    assert c.hunter is e1 and e1.aware()
    assert e2.state == "escort" and not e2.aware()
    # nära konvojen: även den andra tar hotet
    x, y = _datum_off_convoy(w, c, GUARD_NM * 0.6)
    e2._set_datum(w, x, y, 100.0, 0.5, fix=True)
    _run(w, 5)
    assert e2.aware()


def test_hunter_returns_to_the_screen_when_the_convoy_has_moved_on():
    w, c, (e1, e2) = _escorted(3)
    _run(w, 60)
    x, y = _datum_off_convoy(w, c, 2.5)
    e1._set_datum(w, x, y, 100.0, 0.5, fix=True)
    _run(w, 20)
    assert c.hunter is e1
    _run(w, 25 * 60)                                      # konvojen har gått 5 nm
    assert e1.state == "escort" and c.hunter is None


def test_convoy_noise_hides_the_submarine_behind_it():
    w, c, (e1, _e2) = _escorted(4)
    s = e1.vessel.state
    noise = e1._noise(w)
    tgt = w.own
    k = c.vessels[0].state
    # ubåten rakt bakom ett konvojfartyg sett från eskorten
    b = bearing_to(s.x, s.y, k.x, k.y)
    vx, vy = velocity(b, 3600.0)
    tgt.state.x, tgt.state.y = k.x + vx * 0.5, k.y + vy * 0.5
    masked = e1._noise_toward(w, noise, tgt)
    tgt.state.x, tgt.state.y = s.x - vx * 2.0, s.y - vy * 2.0     # åt andra hållet
    clear = e1._noise_toward(w, noise, tgt)
    assert masked > clear + 5
