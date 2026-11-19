"""Jagarkaptener med temperament (J1) och plottets bild av jagarens sätt (J2)."""
import random
from collections import Counter

import pytest

from sim.enemy import DATUM_TIMEOUT, TEMPERAMENTS, DestroyerAI, draw_temperament
from sim.environment import Environment
from sim.entities import Vessel
from sim.ownship import OwnShip
from sim.ship import ShipState
from sim.world import World


def _setup(temper, dd_xy=(10, 20), seed=1):
    own = OwnShip(ShipState(x=10, y=10, course=0, speed=3, depth=150, max_depth=400))
    dd = Vessel("DD1", "destroyer", ShipState(x=dd_xy[0], y=dd_xy[1], course=90, speed=10,
                                              turn_rate=2, accel=0.3, max_speed=32))
    w = World(own=own, contacts=[dd], env=Environment(current_kn=0), rng=random.Random(seed))
    ai = DestroyerAI(dd, random.Random(seed), temperament=TEMPERAMENTS[temper])
    w.ais.append(ai)
    return w, ai


def test_temperament_is_drawn_without_moving_the_ships_own_stream():
    names = Counter()
    for seed in range(300):
        rng = random.Random(seed)
        before = rng.getstate()
        names[draw_temperament(rng).name] += 1
        assert rng.getstate() == before
    assert set(names) == set(TEMPERAMENTS)
    assert all(70 <= n <= 130 for n in names.values()), names
    # samma frö ger samma kapten
    assert draw_temperament(random.Random(5)) == draw_temperament(random.Random(5))


def test_eager_captain_closes_faster_than_a_methodical_one():
    speeds = {}
    for t in ("metodisk", "ivrig"):
        w, ai = _setup(t)
        ai.start_hunt(10, 10, 150, 1.0, t=0)
        ai._decide(w)
        speeds[t] = ai.vessel.state.ordered_speed
    assert speeds["ivrig"] == speeds["metodisk"] + 5


def test_stubborn_captain_keeps_an_old_datum():
    for t, keeps in (("metodisk", False), ("envis", True), ("ivrig", False)):
        w, ai = _setup(t)
        ai.start_hunt(10, 10, 150, 1.0, t=0)
        w.time = DATUM_TIMEOUT + 100
        ai._decide(w)
        assert (ai.datum is not None) == keeps, t


def test_patrol_boats_are_all_alike():
    from sim.harbor import PatrolBoatAI
    dd = Vessel("PB1", "patrol", ShipState(x=0, y=0, course=0, speed=5))
    for seed in range(20):
        assert PatrolBoatAI(dd, random.Random(seed)).temper.name == "metodisk"


def _plot_game():
    from sim.game import Game
    from sim.scenario import default_scenario
    from sim.stations.plot import PlotTeam
    g = Game(default_scenario(random.Random(4)), seed=4)
    return g, g.station(PlotTeam)


def _hunter_track(g, ping_every=8, n=12):
    from sim.knowledge import ContactTrack
    from sim.reports import Quality
    from sim.tma import BearingObs
    tr = ContactTrack("S-7", 0, classification="jagare", class_quality=Quality.GOD)
    tr.observations = [BearingObs(g.now - i * ping_every, 45.0, 1.0, 0, 0, 0, designation="S-7",
                                  source="ping") for i in range(n)]
    g.knowledge.tracks["S-7"] = tr
    return tr


@pytest.mark.slow
def test_plot_tells_the_hunters_ping_rate_and_that_he_keeps_on():
    from sim.events import ReportDelivered
    from sim.stations.plot import HUNTER_AFTER_S, HUNTER_LONG_S
    g, plot = _plot_game()
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.knowledge.hunted = lambda now: True
    for _ in range(HUNTER_AFTER_S + 40):
        _hunter_track(g)
        g.tick()
    said = [r for r in reports if r.type == "plot.hunter"]
    assert len(said) == 1 and "tätt, var 8:e sekund" in said[0].text and "ger inte upp" not in said[0].text
    for _ in range(HUNTER_LONG_S - HUNTER_AFTER_S):
        _hunter_track(g)
        g.tick()
    said = [r for r in reports if r.type == "plot.hunter"]
    assert len(said) == 2 and "ger inte upp" in said[-1].text


def test_nothing_to_say_without_pings_or_a_solution():
    g, plot = _plot_game()
    tr = _hunter_track(g, n=2)
    assert plot.hunter_data(tr, 700) is None
