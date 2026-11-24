"""I skjutläget men djupt efter en undanmanöver: navigatören föreslår skjutdjupet när jakten lugnat sig
och målet ännu inte är tvärs (krig-kort frö 12, 2026-11-24)."""
import random

from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.navigation import NavigationStation


def _nav(depth=220, pass_in_s=600):
    g = Game(build_scenario("konvoj-kort", random.Random(3)), seed=3, warm_up=False)
    nav = g.station(NavigationStation)
    g.world.own.state.depth = g.world.own.state.ordered_depth = depth
    nav._attack_pass_t = g.now + pass_in_s
    nav._attack_what = {"what": "konvojen", "designation": "S-1"}
    return g, nav


def test_suggests_fire_depth_when_the_hunt_is_over():
    g, nav = _nav()
    nav._fire_depth_watch()
    assert "attack_depth" in nav._suggested


def test_not_while_hunted_not_after_passage_and_not_when_shallow():
    g, nav = _nav()
    g.knowledge.hunted = lambda now, window=300: True
    nav._fire_depth_watch()
    assert "attack_depth" not in nav._suggested
    for g, nav in (_nav(pass_in_s=-1), _nav(depth=80)):
        nav._fire_depth_watch()
        assert "attack_depth" not in nav._suggested
