"""Rättelser efter provspelet 2026-11-21: loggens bredd, telegrammens ordning, order med minustecken,
kurs mot banken, starpoms citat av kaptenens order."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Report, ReportQueue
from sim.scenario import build_scenario
from sim.stations.starpom import _canon


def _game(key="kuba", seed=1):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed, warm_up=False)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n=8):
    for _ in range(n):
        g.tick()


def test_report_log_wraps_at_its_own_width():
    from ui.widgets import ReportLog
    assert ReportLog().min_width <= 20       # RichLog bryter annars vid 78 tecken


def test_telegrams_are_delivered_in_number_order():
    q = ReportQueue()
    q.submit(Report(10, "Radio", "radio.message", {"telegram": 7}))
    q.submit(Report(8, "Radio", "radio.message", {"telegram": 8}))
    assert [r.data["telegram"] for r in q.due(20)] == [7, 8]


def test_negative_values_get_an_explanation():
    g, reports = _game()
    for order in ("kurs -10", "fart -3", "djup -5"):
        g.command(order)
    _run(g)
    texts = [r.text for r in reports if r.type == "order.unknown"]
    assert len(texts) == 3
    for word in ("000–359", "back 3", "ytläge"):
        assert any(word in t for t in texts), (word, texts)


def test_course_to_the_bank_uses_the_chart():
    for key in ("jagad", "kuba"):
        g, reports = _game(key, 5)
        g.command("kurs mot banken")
        _run(g)
        r = next(r for r in reports if r.type.startswith("nav.steer"))
        assert r.type in ("nav.steer.bank", "nav.steer.bank_here"), r.text
        if r.type == "nav.steer.bank":
            assert g.world.own.state.ordered_course == r.data["course"]
            assert 60 <= r.data["depth"] <= 250


def test_unknown_place_has_no_trailing_space():
    g, reports = _game("sundet", 3)
    g.command("kurs mot månen")
    _run(g)
    r = next(r for r in reports if r.type == "nav.steer.none")
    assert r.text == r.text.strip() and "Ankarplatsen" in r.text


def test_starpom_quotes_courses_with_three_digits():
    assert _canon("kurs 0") == "kurs 000"
    assert _canon("Kurs  45") == "kurs 045"
    assert _canon("fart 5") == "fart 5"
