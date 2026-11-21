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


# --- steg 2: sjunkna kontakter, stabens telegram ---------------------------------------
from sim.dispatch import ReportedContact, ReportedConvoy, SentReport  # noqa: E402
from sim.events import EventBus, ReportTransmitted  # noqa: E402
from sim.headquarters import Headquarters  # noqa: E402
from sim.reports import Quality  # noqa: E402
from sim.sonar import TransientHeard  # noqa: E402
from sim.stations.sonar_room import SonarRoom  # noqa: E402


def _report(hq_bus, n=1):
    dd = ReportedContact("S-2", "jagare, ångturbiner, två axlar", 1.0, 2.0, 90.0, 15.0, Quality.GOD, 0)
    cv = ReportedConvoy(3.0, 4.0, 200.0, 12.0, Quality.OSAKER, 5, 2)
    hq_bus.publish(ReportTransmitted(10, SentReport(10, "full", (0.0, 0.0, 0.3), (dd,), cv,
                                                    ("hunted",), number=n)))


def test_staff_at_war_does_not_forbid_attacks_or_ask_to_follow():
    bus = EventBus()
    hq = Headquarters(at_war=True)
    hq.attach(bus)
    _report(bus)
    out = hq.outgoing() + hq.outgoing()
    assert not any("ANGRIP EJ" in t or "FÖLJ KONVOJEN" in t for t in out)
    assert out[0].endswith("MOTTAGEN.") and not hq.expects_report


def test_recall_leaves_only_the_receipts():
    bus = EventBus()
    hq = Headquarters()
    hq.attach(bus)
    _report(bus)
    hq.read_order({"tasks": ("ut",), "recalled": True})
    assert hq.outgoing() == ["FRÅN HUVUDSTABEN. ER RAPPORT NR 1 MOTTAGEN."]
    assert not hq.expects_report
    _report(bus, 2)
    assert hq.outgoing() == ["FRÅN HUVUDSTABEN. ER RAPPORT NR 2 MOTTAGEN."]


def test_a_sunk_contact_is_no_threat_and_its_pinger_is_forgotten():
    g, reports = _game("kuba", 1)
    g.knowledge.on_detection("S-2", 0)
    sonar = g.station(SonarRoom)
    sonar._on_sound(TransientHeard("ping", 40.0, 80.0, "S-2"))
    assert "S-2" in sonar._pings
    sonar._on_sound(TransientHeard("breakup", 40.0, 60.0, "S-2"))
    tr = g.knowledge.tracks["S-2"]
    assert tr.sunk and not tr.held and not tr.threat
    assert "S-2" not in sonar._pings
