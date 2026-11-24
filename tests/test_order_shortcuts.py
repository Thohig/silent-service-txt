"""Förenklad ordergivning: j/n, ja på en stations fråga, relativa girar och "Menade ni …?"."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario


def _game(key="kuba", seed=1):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    for _ in range(5):
        g.tick()
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()


def test_babord_and_styrbord_turn_from_the_ordered_course():
    g, _ = _game()
    s = g.world.own.state
    g.command("kurs 350")
    g.command("styrbord 30")
    assert s.ordered_course == 20
    g.command("bb 45")
    assert s.ordered_course == 335
    g.command("gira babord 200")                # mer än ett halvt varv: inte förstått
    assert s.ordered_course == 335


def test_a_misspelt_order_is_offered_as_a_suggestion_and_j_does_it():
    g, reports = _game()
    g.command("periskopdjp")
    _run(g, 15)
    ask = [r for r in reports if r.type == "order.did_you_mean"]
    assert ask and "periskopdjup" in ask[0].text
    g.command("j")
    assert g.world.own.state.ordered_depth <= 18


def test_n_declines_and_weapons_are_never_guessed():
    g, reports = _game()
    g.command("smyg motor")
    _run(g, 15)
    assert g.active_suggestion() is not None
    g.command("n")
    assert g.active_suggestion() is None
    for typo in ("edl s1", "salav s1", "avsluta spleet"):
        assert g.registry.guess(typo) is None


def test_j_answers_a_stations_question_about_the_captains_own_order():
    """Maskin frågar före nödblåsning utan vatten ombord: j verkställer, som att upprepa ordern."""
    g, reports = _game()
    g.world.own.state.depth = g.world.own.state.ordered_depth = 100
    g.command("nödblåsning")
    _run(g, 15)
    ask = [r for r in reports if r.type == "eng.blow_confirm"]
    assert ask and "Svara ja" in ask[0].text
    assert not g.world.own.sys.blowing
    assert g.status().suggestion == "nödblåsning"   # orderraden visar vad ja gör
    g.command("j")
    assert g.world.own.sys.blowing


def test_a_question_answered_no_is_dropped():
    g, reports = _game()
    g.world.own.state.depth = g.world.own.state.ordered_depth = 100
    g.command("nödblåsning")
    _run(g, 15)
    g.command("n")
    g.command("j")
    assert not g.world.own.sys.blowing
