"""Starpom har befälet: överlämnande, mandat, väckning och kaptenens väg till centralen."""
import random
import re

import pytest

from sim.crew import Role
from sim.events import OrderIssued, ReportDelivered
from sim.game import Game
from sim.phrases import RU_PHRASES
from sim.scenario import build_scenario, default_scenario
from sim.stations import FirstOfficer
from sim.stations.starpom import MANDATE, ORDERLY_S, WALK_S, alarm_level, in_mandate


def _game(seed=3, key=None):
    sc = build_scenario(key, random.Random(seed)) if key else default_scenario(random.Random(seed))
    g = Game(sc, seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, s):
    for _ in range(s):
        g.tick()


def _xo(g) -> FirstOfficer:
    return g.station(FirstOfficer)


def test_handover_and_back_with_walk_to_central():
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    st = g.status()
    assert st.command == "starpom" and st.captain_at == "cabin"
    assert any(r.type == "xo.took" for r in reports)
    g.command("jag har befälet")
    assert g.status().captain_at == "walking"
    g.command("djup 150")                       # på väg: inga order
    _run(g, 6)
    assert g.world.own.state.ordered_depth != 150
    assert any(r.type == "xo.walking" for r in reports)
    _run(g, WALK_S - 4)
    st = g.status()
    assert st.command == "captain" and st.captain_at == "central"
    _run(g, 3)
    assert any(r.type == "xo.handback" for r in reports)


def test_fast_time_only_while_starpom_has_command():
    g, reports = _game()
    g.command("tid 60")
    _run(g, 6)
    assert g.time_scale == 1 and any(r.type == "xo.time_refused" for r in reports)
    g.command("starpom har befälet")
    g.command("sov")
    assert g.time_scale == 60 and g.status().sleeping


def test_mandate_never_weapons_radio_or_surface():
    g, _ = _game()
    for order in ("eld tub 1 mot S-1", "salva S-1", "sänd rapport", "ytläge", "anfall S-1",
                  "avbryt uppdraget bekräftat", "aktiv sonar", "radar", "nödblåsning"):
        assert not in_mandate(g, order), order
    for order in ("djup 100", "turbin, djup 220, fart 13", "smygmotor", "periskop", "skenmål",
                  "kurs 090", "fix"):
        assert in_mandate(g, order), order


def test_starpom_accepts_suggestion_inside_mandate_under_his_name():
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    issued = []
    g.bus.subscribe(OrderIssued, lambda e: issued.append(e))
    g.say(Role.NAVIGATOR, "order.declined", {"order": "djup 120", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    assert g.world.own.state.ordered_depth == 120
    assert any(e.by == "starpom" and e.text == "djup 120" for e in issued)
    assert any(r.type == "xo.accept" for r in reports)
    assert g.active_suggestion() is None
    assert g.logbook.orders == 1                  # överlämnandet; starpoms order räknas inte


def test_suggestion_outside_mandate_rings_the_captain():
    g, reports = _game()
    g.command("starpom har befälet")
    g.command("sov")
    _run(g, 3)
    g.say(Role.RADIO, "order.declined", {"order": "sänd rapport", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    st = g.status()
    assert st.phone == "ring" and g.time_scale == 1 and not st.sleeping
    assert g.active_suggestion() is not None       # kaptenen beslutar, per telefon
    g.command("svara")
    _run(g, 8)
    call = [r for r in reports if r.type == "xo.call"]
    assert call and "sänd rapport" in call[-1].text
    assert g.status().phone is None


def test_unanswered_call_brings_the_orderly():
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    g.say(Role.RADIO, "order.declined", {"order": "sänd rapport", "made_t": g.now}, kind="suggest")
    _run(g, 12 + ORDERLY_S)
    assert any(r.type == "xo.orderly" for r in reports)
    assert g.status().phone is None


def test_danger_calls_captain_to_central():
    g, reports = _game()
    g.command("starpom har befälet")
    g.command("sov")
    _run(g, 3)
    g.say(Role.SONAR, "sonar.splash", {"bearing": 10, "near": True}, alarm=True, kind="contact")
    _run(g, 12)
    assert any(r.type == "xo.danger" for r in reports)
    assert g.status().captain_at == "walking" and g.time_scale == 1
    _run(g, WALK_S)
    assert g.status().command == "captain"


def test_alarm_levels():
    assert alarm_level("sonar.splash") == "danger"
    assert alarm_level("torp.incoming") == "danger"
    assert alarm_level("sonar.ping.first") == "question"
    assert alarm_level("sonar.new_contact") == "info"
    assert alarm_level("radio.message") is None


def test_wake_at_clock():
    g, reports = _game()
    g.command("starpom har befälet")
    target = (g.start_clock + 600) % 86400
    g.command(f"väck mig {target // 3600:02d}:{target % 3600 // 60:02d}")
    _run(g, 620)
    assert _xo(g).wake_at is None
    assert any(r.type in ("xo.ring", "xo.danger") for r in reports)


def test_report_lists_decisions():
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    g.say(Role.NAVIGATOR, "order.declined", {"order": "djup 130", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    g.command("lägesrapport")
    _run(g, 10)
    rep = [r for r in reports if r.type == "xo.report"]
    assert rep and "djup 130" in rep[-1].text


def test_russian_speech_for_starpom():
    g, reports = _game()
    g.command("starpom har befälet")
    g.command("lägesrapport")
    g.command("sov")
    _run(g, 10)
    xo = [r for r in reports if r.role == "starpom" and r.kind != "system"]
    assert xo
    for r in xo:
        assert r.type in RU_PHRASES
        assert r.speech and not re.search(r"[A-Za-zÅÄÖåäö]", r.speech), (r.type, r.speech)


@pytest.mark.slow
def test_starpom_keeps_the_watch_over_several_seeds():
    """Kuba och konvojen, kaptenen lämnar över direkt och tar tillbaka när han väcks:
    starpom ger aldrig order utanför mandatet, och fara kallar alltid kaptenen."""
    for key in ("kuba", "konvoj"):
        for seed in range(4):
            g, reports = _game(seed, key)
            by_xo = []
            g.bus.subscribe(OrderIssued, lambda e: by_xo.append(e) if e.by == "starpom" else None)
            g.command("starpom har befälet")
            g.command("sov")
            for _ in range(2 * 3600):
                g.tick()
                if g.over:
                    break
                st = g.status()
                if st.phone == "ring" and g.now % 20 == 0:
                    g.command("svara")
                if st.command == "captain":
                    g.command("starpom har befälet")
                    g.command("sov")
            for e in by_xo:
                assert isinstance(e.order, MANDATE), (key, seed, e.text)
            for r in reports:
                if r.alarm and r.role != "starpom" and r.kind != "suggest" \
                        and alarm_level(r.type) == "danger":
                    later = [x for x in reports if x.t_due >= r.t_due and x.type in
                             ("xo.danger", "xo.handback")]
                    assert later, (key, seed, r.type)
