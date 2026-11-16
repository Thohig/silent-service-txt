"""Starpom har befälet: överlämnande, mandat, väckning och kaptenens väg till centralen."""
import pathlib
import random
import re

import pytest

from sim.crew import Role
from sim.events import OrderIssued, ReportDelivered
from sim.game import Game
from sim.phrases import RU_PHRASES
from sim.scenario import build_scenario, default_scenario
from sim.stations import FirstOfficer
from sim.stations.starpom import (ORDERLY_S, WALK_S, alarm_level, in_mandate,
                                  mandate_for)
from sim.stations.torpedo_room import FireTube, FireSalvo


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
                assert isinstance(e.order, mandate_for(g.knowledge.order_tasks)), (key, seed, e.text)
                assert not isinstance(e.order, (FireTube, FireSalvo)), (key, seed, e.text)
            for r in reports:
                if r.alarm and r.role != "starpom" and r.kind != "suggest" \
                        and alarm_level(r.type) == "danger":
                    later = [x for x in reports if x.t_due >= r.t_due and x.type in
                             ("xo.danger", "xo.handback")]
                    assert later, (key, seed, r.type)


def test_cabin_muffles_the_boat_and_hides_hydrophones():
    from types import SimpleNamespace
    from ui.ambience import ambient_targets
    from ui.audio import from_central
    from sim.reports import Report
    g, _ = _game()
    _run(g, 5)
    central = ambient_targets(g.status(), g.knowledge.tracks.values())
    g.command("starpom har befälet")
    _run(g, 2)
    s = g.status()
    cabin = ambient_targets(s, g.knowledge.tracks.values())
    assert not any(k.startswith("contact:") or k == "dread" for k in cabin)
    for k in cabin:
        assert cabin[k].gain < central[k].gain
    sonar = Report(0, "Sonar (Volkov)", "sonar.bearing", {}, role="sonar")
    xo = Report(0, "Starpom (Sokolov)", "xo.call", {}, role="starpom")
    alarm = Report(0, "Sonar (Volkov)", "sonar.splash", {}, role="sonar", alarm=True)
    assert from_central(sonar, s) and not from_central(xo, s) and not from_central(alarm, s)
    assert not from_central(sonar, SimpleNamespace(command="captain", captain_at="central"))


def test_cabin_render_shows_phone_and_walk():
    from dataclasses import replace
    from ui.cabin_render import render_cabin
    g, _ = _game()
    g.command("starpom har befälet")
    _run(g, 2)
    s = replace(g.status(), phone="ring", sleeping=True)
    rows = [r.plain for r in render_cabin(s, 0.0, 100, 24)]
    assert len(rows) == 24 and all(len(r) == 100 for r in rows)
    text = "\n".join(rows)
    assert "КАЮТА КОМАНДИРА" in text and "КАШТАН" in text and "RING" in text
    walk = replace(s, captain_at="walking", walk_s=20)
    text = "\n".join(r.plain for r in render_cabin(walk, 0.0, 60, 16))
    assert "På väg till centralen, 20 s" in text
    small = render_cabin(s, 0.0, 40, 14)
    assert len(small) == 14


@pytest.mark.slow
def test_ui_cabin_opens_on_handover_and_closes_in_central(tmp_path):
    import asyncio
    from ui.app import SubApp
    from ui.cabin import CabinScreen
    import os
    shots = pathlib.Path(os.environ.get("K114_SHOTS", tmp_path / "shots"))
    shots.mkdir(parents=True, exist_ok=True)

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="arktis")
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.press("enter", "enter")
            await pilot.press(*"starpom har befälet", "enter")
            await pilot.pause(0.3)
            assert isinstance(app.screen, CabinScreen)
            app.screen.draw()
            app.save_screenshot("hytt.svg", str(shots))
            await pilot.press(*"tid 60", "enter")
            assert app.game.time_scale == 60
            await pilot.press(*"jag har befälet", "enter")
            assert app.game.status().captain_at == "walking"
            for _ in range(45):
                app.game.tick()
            await pilot.pause(0.3)
            assert app.game.status().command == "captain"
            assert not isinstance(app.screen, CabinScreen)

    asyncio.run(run())
    assert (shots / "hytt.svg").exists()


def test_starpom_declines_course_suggestion_that_breaks_the_attack():
    from sim.stations.navigation import NavigationStation
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    nav = g.station(NavigationStation)
    nav.goal, nav.attack = "attack", "S-2"       # navigatören styr mot skjutläget
    course = g.world.own.state.ordered_course
    g.say(Role.PLOT, "order.declined", {"order": "kurs 123", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    assert g.world.own.state.ordered_course == course
    dec = [r for r in reports if r.type == "xo.decline"]
    assert dec and "skjutläget" in dec[-1].text and "S-2" in dec[-1].text
    assert g.active_suggestion() is None and _xo(g).decisions[-1][1] == "nej till kurs 123"
    # navigatörens egna kursförslag och larm går igenom
    g.say(Role.PLOT, "order.declined", {"order": "kurs 124", "made_t": g.now}, kind="suggest",
          alarm=True)
    _run(g, 12)
    assert g.world.own.state.ordered_course == 124


def test_starpom_keeps_the_mast_for_a_required_report():
    from sim.stations.radio import RadioStation
    g, reports = _game(key="kuba-kort")
    g.command("starpom har befälet")
    _run(g, 20)                                 # radions förvarning: starpom tar antenndjup
    radio = g.station(RadioStation)
    radio.needs_mast = lambda: True
    g.say(Role.SONAR, "order.declined", {"order": "djup 90", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    assert g.world.own.state.ordered_depth != 90
    assert any(r.type == "xo.decline" and "rapporten" in r.text for r in reports)
    radio.needs_mast = lambda: False
    g.say(Role.SONAR, "order.declined", {"order": "djup 91", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    assert g.world.own.state.ordered_depth == 91


def test_attack_order_widens_the_mandate_but_never_to_firing():
    g, _ = _game()                              # kvadrat 7: patrull
    assert not in_mandate(g, "anfall S-1")
    g, _ = _game(key="konvoj")
    assert in_mandate(g, "anfall S-1")
    for order in ("salva S-1", "eld tub 1 mot S-1", "sänd rapport", "ytläge"):
        assert not in_mandate(g, order), order


def test_captain_is_called_to_central_before_firing_position():
    from sim.stations.navigation import NavigationStation
    g, reports = _game(key="konvoj")
    g.command("starpom har befälet")
    g.command("sov")
    _run(g, 3)
    nav = g.station(NavigationStation)
    nav.goal, nav.attack = "attack", "S-2"
    nav.attack_eta_t = g.now + 600                # långt kvar: han får sova
    _run(g, 10)
    assert g.status().captain_at == "cabin"
    nav.attack_eta_t = g.now + 150                # strax: högtalaren, han hinner fram
    _run(g, 10)
    assert g.status().captain_at == "walking"
    assert any(r.type == "xo.danger" and "skjutläge" in r.text for r in reports)


def test_report_window_rings_the_captain():
    g, reports = _game(key="kuba-kort")
    g.command("starpom har befälet")
    g.command("sov")
    _run(g, 30)                                  # radions förvarning kommer direkt
    assert any(r.type == "xo.accept" and "antenndjup" in r.text for r in reports)
    assert g.status().phone == "ring" or any(r.type == "xo.orderly" for r in reports)
    g.command("svara")
    _run(g, 8)
    assert any(r.type in ("xo.call", "xo.orderly") and "Sambandstillfälle" in r.text
               for r in reports)


def test_big_ship_in_range_calls_captain_under_attack_orders_only():
    from sim.knowledge import ContactTrack
    from sim.reports import Quality
    from types import SimpleNamespace
    for key, called in (("konvoj", True), (None, False)):
        g, reports = _game(key=key)
        g.command("starpom har befälet")
        g.command("sov")
        _run(g, 3)
        tr = ContactTrack("S-9", g.now, classification="trupptransport",
                          class_quality=Quality.GOD)
        tr.solution = SimpleNamespace(quality=Quality.GOD, t=g.now, range_nm=3.0)
        g.knowledge.tracks["S-9"] = tr
        _run(g, 8)
        assert (g.status().captain_at == "walking") == called, key
        assert any(r.type == "xo.danger" and "S-9" in r.text for r in reports) == called
