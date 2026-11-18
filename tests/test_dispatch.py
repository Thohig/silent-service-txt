"""Rapporten till staben (R1) och pejlningen av sändningen (R2)."""
import random

import pytest

from sim.dispatch import GROUP_S, compose, report_text
from sim.entities import Emission
from sim.events import ReportDelivered, ReportTransmitted
from sim.game import Game
from sim.knowledge import ContactTrack, Knowledge
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.radio import RadioStation, SendReport
from sim.tma import Solution


def _sol(x, y, q=Quality.GOD, r=3.0):
    return Solution(t=0, t_ref=0, state=(x, y, 6.0, 0.0), x=x, y=y, course=90.0, speed=12.0,
                    range_nm=r, bearing=40.0, range_sigma=0.3, course_sigma=10.0,
                    speed_sigma=1.0, quality=q, n_obs=20, span_s=900, own_maneuvered=True,
                    rms_residual=1.0)


def _track(k, des, cls, q=Quality.GOD, x=3.0, y=4.0, r=3.0):
    tr = ContactTrack(des, first_t=0, classification=cls, class_quality=Quality.GOD)
    tr.solution = _sol(x, y, q, r)
    k.tracks[des] = tr


def test_report_has_contacts_from_the_plot_and_length_follows_content():
    k = Knowledge()
    _track(k, "S-1", "jagare, ångturbiner, två axlar")
    _track(k, "S-2", "handelsfartyg, diesel, en axel")
    _track(k, "S-3", "isljud, ingen maskin")                     # inget att rapportera
    _track(k, "S-4", "okänd kontakt", q=Quality.DALIG)           # för dålig lösning
    full = compose(k, 100, (5.0, 6.0, 0.3), "full")
    assert [c.designation for c in full.contacts] == ["S-1", "S-2"]   # hotet först
    short = compose(k, 100, (5.0, 6.0, 0.3), "short", events=("photo",))
    assert short.contacts == () and short.events == ("photo",)
    assert full.duration_s - short.duration_s == GROUP_S * (full.groups - short.groups)
    assert full.duration_s > short.duration_s
    one = compose(k, 100, (5.0, 6.0, 0.3), "contact", "S-2")
    assert [c.designation for c in one.contacts] == ["S-2"]
    text = report_text(full)
    assert "EGET LÄGE 5,0 Ö 6,0 N" in text and "S-1 JAGARE" in text and "KURS 090" in text


def _radio_game(seed=3):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    g.world.ais.clear()
    reports, sent = [], []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.bus.subscribe(ReportTransmitted, lambda e: sent.append(e))
    s = g.world.own.state
    s.depth = s.ordered_depth = 15.0
    return g, reports, sent


def test_short_report_is_sent_faster_and_lands_as_an_outgoing_strip():
    g, reports, sent = _radio_game()
    _track(g.knowledge, "S-7", "jagare, ångturbiner, två axlar")
    g.command("sänd kort rapport")
    for _ in range(5):
        g.tick()
    ack = next(r for r in reports if r.type == "radio.sending")
    assert ack.data["kind"] == "short" and ack.data["contacts"] == 0
    for _ in range(ack.data["seconds"] + 5):
        g.tick()
    done = next(r for r in reports if r.type == "radio.sent")
    assert done.data["telegram_kind"] == "outgoing" and "EGET LÄGE" in done.data["text"]
    assert sent and sent[-1].complete and sent[-1].report.kind == "short"
    assert g.world.mission["reports"][-1] is sent[-1].report


def test_full_report_is_longer_than_short_with_contacts():
    g, _, _ = _radio_game()
    x, y = g.own_position_estimate()
    _track(g.knowledge, "S-7", "jagare, ångturbiner, två axlar", x=x + 20.0, y=y, r=20.0)
    radio = g.station(RadioStation)
    assert radio.draft("full").duration_s > radio.draft("short").duration_s
    assert radio.risk(60)[0] == "stor" and radio.risk(10)[0] == "liten"
    _track(g.knowledge, "S-7", "jagare, ångturbiner, två axlar", x=x + 4.0, y=y, r=4.0)
    assert radio.risk(10)[0] == "stor"


def test_report_on_unknown_contact_is_refused():
    g, reports, sent = _radio_game()
    g.command("sänd rapport S-9")
    for _ in range(10):
        g.tick()
    assert any(r.type == "radio.refused" for r in reports) and not sent
    assert g.registry.parse("sänd rapport S-9") == SendReport("contact", "S-9")
    assert g.registry.parse("kort rapport") == SendReport("short")


def _df(seconds, seed):
    from sim.enemy import DestroyerAI
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    dd = next(a for a in g.world.ais if isinstance(a, DestroyerAI))
    o = g.world.own.state
    g.world.emissions = [Emission("hf", o.x, o.y, g.world.own.id, 0, duration=seconds)]
    dd.datum = None
    dd._emissions(g.world)
    return dd.datum


def test_short_transmission_is_seldom_fixed_and_long_one_is_sharp():
    short = [_df(8, s) for s in range(12)]
    assert all(d is None for d in short)
    long = [_df(60, s) for s in range(12)]
    assert all(d is not None for d in long)
    assert all(d.sigma < 2.0 for d in long)
    mid = [_df(30, s) for s in range(12)]
    assert all(d is not None and d.sigma == pytest.approx(2.0) for d in mid)
