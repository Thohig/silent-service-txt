"""Ett obesvarat förslag dras tillbaka när en station nu säger nej till det (jagad frö 61, 2026-11-24:
maskin föreslog turbin, reaktorn snabbstoppade, och ja gav 'turbinen kan inte köras')."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario


def _game():
    g = Game(build_scenario("jagad", random.Random(61)), seed=61, warm_up=False)
    seen = []
    g.bus.subscribe(ReportDelivered, lambda e: seen.append(e.report))
    return g, seen


def test_turbine_suggestion_is_withdrawn_after_a_scram():
    g, seen = _game()
    g.suggestion = ("djup 110, turbin, fart 9", "Föreslår att vi lättar.", g.now)
    g.tick()
    assert g.active_suggestion() is not None          # reaktorn i drift: förslaget står
    g.world.own.sys.reactor = "scram"
    g.tick()
    assert g.active_suggestion() is None
    assert any(r.type == "order.suggestion_dropped" and "turbin" in r.text for r in seen)
    g.command("ja")
    assert not any(r.type == "eng.refused" for r in seen)


def test_suggestion_without_turbine_stands_after_a_scram():
    g, seen = _game()
    g.world.own.sys.reactor = "scram"
    g.suggestion = ("fart 3", "Föreslår fart 3.", g.now)
    g.tick()
    assert g.active_suggestion() is not None
    assert not any(r.type == "order.suggestion_dropped" for r in seen)
