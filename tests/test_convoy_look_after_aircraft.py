"""Vakthavande föreslår ingen titt på konvojen de första 15 min efter att en flygradar varit nära
(krig-kort frö 18, 2026-11-24: upp, flyget, ned och upp igen fyra gånger på 19 min)."""
import random

from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.officer import AIR_HOLD_S, OfficerStation


def _officer():
    g = Game(build_scenario("konvoj-kort", random.Random(3)), seed=3, warm_up=False)
    off = g.station(OfficerStation)
    g.knowledge.convoy = object()           # konvojen känd (bara att den finns räknas här)
    off._escort_close = lambda: None
    g.world.own.state.depth = g.world.own.state.ordered_depth = 60
    return g, off


def test_no_convoy_look_right_after_a_close_aircraft():
    g, off = _officer()
    off._air_close_t = g.now
    off._convoy_watch()
    assert "convoy_up" not in off._suggested


def test_convoy_look_when_the_aircraft_was_long_ago():
    g, off = _officer()
    off._air_close_t = g.now - AIR_HOLD_S - 1
    off._convoy_watch()
    assert "convoy_up" in off._suggested


def test_no_convoy_look_in_fog_the_periscope_just_saw():
    """Konvoj-kort frö 11: periskopet såg sikten 0,7 sjömil, konvojen var 4 sjömil bort, och vakthavande
    föreslog ändå titt och periskopdjup."""
    from sim.stations.officer import FOG_MEMORY_S
    from sim.stations.periscope import PeriscopeWatch
    g, off = _officer()
    off._air_close_t = -10**9
    peri = g.station(PeriscopeWatch)
    peri.seen_visibility = (g.now, 0.7)
    off._convoy_watch()
    assert "convoy_up" not in off._suggested
    peri.seen_visibility = (g.now - FOG_MEMORY_S - 1, 0.7)   # för gammalt: vädret kan ha ändrats
    off._convoy_watch()
    assert "convoy_up" in off._suggested
