"""Under isen: maskin och navigatören föreslår inget annat medan ett förslag står obesvarat
(arktis-kort frö 3, 2026-11-24)."""
import random

from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.engineering import EngineeringStation
from sim.stations.navigation import NavigationStation


def _game():
    g = Game(build_scenario("arktis", random.Random(3)), seed=3, warm_up=False)
    return g, g.station(EngineeringStation), g.station(NavigationStation)


def _keys(station):
    return set(station._suggested)


def test_engineering_does_not_send_us_to_another_opening_while_going_up_is_proposed():
    g, eng, nav = _game()
    g.world.own.sys.smoke = 0.5
    g.world.own.state.depth = g.world.own.state.ordered_depth = 60
    nav.under_ice = lambda: True
    from sim.reports import Quality
    nav.best_opening = lambda: type("O", (), {"quality": lambda self, t: Quality.GOD})()
    nav.opening_data = lambda o: {"no": 4, "bearing": 180.0, "range": 110, "kind": "öppet vatten"}
    g.suggestion = ("ytläge", "Föreslår ytläge.", g.now)
    eng._smoke_advice()
    assert "vent_vak" not in _keys(eng)
    g.suggestion = None
    eng._smoke_advice()
    assert "vent_vak" in _keys(eng)


def test_navigator_does_not_say_search_on_while_an_opening_is_proposed():
    g, eng, nav = _game()
    s = g.world.own.state
    s.depth = s.ordered_depth = 60
    s.speed = s.ordered_speed = 0
    nav.under_ice = lambda: True
    nav.best_opening = lambda: None
    nav.vak = None
    nav._suggested["station_go"] = g.now               # bara viloförslaget prövas här
    g.suggestion = ("vak", "Öppning 6 ligger i bäring 257, cirka 80 meter.", g.now)
    nav._ice_advice()
    assert "resume" not in _keys(nav)
    g.suggestion = None
    nav._ice_advice()
    assert "resume" in _keys(nav)
