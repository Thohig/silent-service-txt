"""Navigatören föreslår ingen bottenfix som skulle nekas: på väg ned mot botten eller under två knop
(kuba frö 16, 2026-11-24: "bottenfix" föreslagen i 1 kn på väg ned, och ja gav "minst två knop")."""
import random

from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.navigation import NavigationStation


def _nav(monkeypatch):
    g = Game(build_scenario("kuba", random.Random(16)), seed=16, warm_up=False)
    nav = g.station(NavigationStation)
    assert g.knowledge.bathymetry is not None
    monkeypatch.setattr(type(g.knowledge.bathymetry), "slope", lambda self, x, y: 10**6)   # brant botten
    nav.uncertainty = lambda: 5.0                           # besticket sämre än kortet
    st = g.world.own.state
    st.speed = st.ordered_speed = 6
    return g, nav, st


def test_bfix_worthwhile_at_speed(monkeypatch):
    g, nav, st = _nav(monkeypatch)
    assert nav._bfix_worthwhile()


def test_no_bfix_while_slow_or_settling(monkeypatch):
    g, nav, st = _nav(monkeypatch)
    st.speed = st.ordered_speed = 1
    assert not nav._bfix_worthwhile()
    g, nav, st = _nav(monkeypatch)
    g.world.own.sys.settle = True
    assert not nav._bfix_worthwhile()
