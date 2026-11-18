"""Huvudstaben (R3): vet bara vad vi sänt, svarar vid nästa sambandstillfälle."""
import random

from sim.dispatch import ReportedContact, ReportedConvoy, SentReport
from sim.events import EventBus, ReportDelivered, ReportTransmitted
from sim.game import Game
from sim.headquarters import SILENCE, Headquarters
from sim.reports import Quality
from sim.scenario import default_scenario
from sim.stations.radio import RadioStation


def _hq(expects=False):
    bus = EventBus()
    hq = Headquarters(expects_report=expects)
    hq.attach(bus)
    return hq, bus


def test_report_is_acknowledged_and_its_content_gives_follow_up_orders():
    hq, bus = _hq()
    dd = ReportedContact("S-2", "jagare, ångturbiner, två axlar", 1.0, 2.0, 90.0, 15.0,
                         Quality.GOD, 0)
    cv = ReportedConvoy(3.0, 4.0, 200.0, 12.0, Quality.OSAKER, 5, 2)
    bus.publish(ReportTransmitted(10, SentReport(10, "full", (0.0, 0.0, 0.3), (dd,), cv,
                                                 ("hunted",), number=1)))
    out = hq.outgoing()
    assert out[0] == "FRÅN HUVUDSTABEN. ER RAPPORT NR 1 MOTTAGEN."
    assert any("FÖLJ KONVOJEN" in t for t in out) and any("S-2 UPPFATTAD" in t for t in out)
    assert any("BRYT KONTAKTEN" in t for t in hq.outgoing())   # resten nästa gång
    assert hq.expects_report                                    # konvojen: nästa rapport väntas
    assert len(hq.received) == 1


def test_aborted_report_never_reaches_the_staff():
    hq, bus = _hq()
    bus.publish(ReportTransmitted(10, SentReport(10, "short", (0.0, 0.0, 0.3)), complete=False))
    assert hq.outgoing() == [] and hq.received == []


def test_silence_escalates_only_when_a_report_is_expected():
    hq, _ = _hq(expects=False)
    hq.window_closed(reported=False)
    assert hq.outgoing() == []
    hq.request_report()
    hq.window_closed(reported=False)
    hq.window_closed(reported=False)
    hq.window_closed(reported=False)
    assert hq.outgoing() == [SILENCE[0], SILENCE[1], SILENCE[1]]


def test_staff_reply_arrives_with_the_next_window():
    sc = default_scenario(random.Random(3))
    sc.radio_windows = [30, 600]
    sc.radio_window_len = 200
    sc.radio_messages = []
    g = Game(sc, seed=3)
    g.world.ais.clear()
    texts = []
    g.bus.subscribe(ReportDelivered, lambda e: texts.append(e.report.data.get("text", ""))
                    if e.report.type == "radio.message" else None)
    s = g.world.own.state
    s.depth = s.ordered_depth = 15.0
    while g.now < 120:
        g.tick()
    g.command("sänd kort rapport")
    while g.now < 750:
        g.tick()
        s.depth = s.ordered_depth = 15.0
    assert "FRÅN HUVUDSTABEN. ER RAPPORT NR 1 MOTTAGEN." in texts
    assert g.station(RadioStation).hq.received
