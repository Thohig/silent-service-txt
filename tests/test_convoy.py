"""Konvojen: formation, sicksack kring baskursen, nödgir och hur besättningen uppfattar den."""
import math
import random

import pytest

from sim.convoy import NODGIR_DEG, NODGIR_S, ZIGZAG_PLANS, ConvoyDef, make_convoy
from sim.events import ClassificationChanged, ContactDetected
from sim.game import Game
from sim.geo import angle_diff, bearing_to, distance
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
