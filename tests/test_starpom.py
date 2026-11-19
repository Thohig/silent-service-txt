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
from sim.stations.starpom import (ORDERLY_S, alarm_level, in_mandate,
                                  mandate_for)
from sim.stations.navigation.tasks import Attack
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


def test_handover_and_back_to_central_at_once():
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    st = g.status()
    assert st.command == "starpom" and st.captain_at == "cabin"
    assert any(r.type == "xo.took" for r in reports)
    g.command("jag har befälet")                # i centralen direkt, ordern går igenom
    st = g.status()
    assert st.command == "captain" and st.captain_at == "central"
    g.command("djup 150")
    assert g.world.own.state.ordered_depth == 150
    _run(g, 6)
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


def test_cabin_shows_the_decision_after_the_call_and_yes_while_ringing_answers_first():
    from ui.cabin_render import call_line
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    g.say(Role.RADIO, "order.declined", {"order": "sänd rapport", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    st = g.status()
    assert st.phone == "ring" and st.decision is None
    assert "Enter svarar" in call_line(st, 0.0).plain
    g.command("svara")
    _run(g, 3)
    st = g.status()
    assert st.decision == "Radio föreslår sänd rapport"
    line = call_line(st, 0.0).plain
    assert "ERT BESLUT" in line and "sänd rapport" in line and "ja" in line and "nej" in line
    g.command("nej")
    _run(g, 2)
    assert g.status().decision is None
    # ja eller nej medan det ringer: kaptenen lyfter luren först och hör varför
    g.say(Role.RADIO, "order.declined", {"order": "sänd rapport kort", "made_t": g.now},
          kind="suggest")
    _run(g, 12)
    assert g.status().phone == "ring"
    n = len([r for r in reports if r.type == "xo.call"])
    g.command("nej")
    _run(g, 3)
    assert g.status().phone is None and g.status().door is None
    assert len([r for r in reports if r.type == "xo.call"]) == n + 1
    _run(g, ORDERLY_S + 5)
    assert not any(r.type == "xo.orderly" for r in reports)


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
    st = g.status()
    assert st.captain_at == "central" and st.command == "captain" and g.time_scale == 1
    assert any(r.type == "xo.handback" for r in reports)


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


def test_cabin_render_shows_phone():
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
    small = render_cabin(s, 0.0, 40, 14)
    assert len(small) == 14
    # stort fönster: rummet från kudden med dörren och ljuset från gången, filten och handen
    for w, h in ((120, 30), (90, 22), (64, 18)):
        rows = [r.plain for r in render_cabin(s, 0.0, w, h)]
        assert len(rows) == h and all(len(r) == w for r in rows)
        room = "\n".join(rows)
        assert "КАШТАН" in room and "▔" in room and "╼" in room and "▓" in room
        assert "KURS" in room and "DJUP" in room


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
            assert app.game.status().captain_at == "central"
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
    nav.steer = Attack("S-2")                     # navigatören styr mot skjutläget
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
    nav.steer = Attack("S-2", eta_t=g.now + 600)  # långt kvar: han får sova
    _run(g, 10)
    assert g.status().captain_at == "cabin"
    nav.steer.eta_t = g.now + 110                 # strax: högtalaren, han kommer
    _run(g, 10)
    assert g.status().captain_at == "central"
    assert any(r.type == "xo.danger" and "skjutläge" in r.text for r in reports)


def test_report_window_rings_the_captain():
    # frö där plottet inte har jagaren inom 5 nm (annars väntar radion: radio.wait)
    g, reports = _game(2, key="kuba-kort")
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
        assert (g.status().captain_at == "central") == called, key
        assert any(r.type == "xo.danger" and "S-9" in r.text for r in reports) == called


def test_cabin_calendar_follows_the_order_date():
    """Almanackan i hytten visar orderns dag; dagarna går vid midnatt; söndagen i rött."""
    from dataclasses import replace
    from ui.cabin_render import _calendar, render_cabin
    g, _ = _game()
    s = g.status()
    assert s.order_day == 24                       # Kvadrat 7: 24 oktober 1962, en onsdag
    room = "\n".join(r.plain for r in render_cabin(s, 0.0, 120, 30))
    assert "ОКТЯБРЯ" in room and "СРЕДА" in room and " 24 " in room
    assert "Пр.613" in room and "◷" in room
    later = replace(s, clock=s.clock + 86400)
    assert "ЧЕТВЕРГ" in "\n".join(r.plain for r in render_cabin(later, 0.0, 120, 30))
    sunday = _calendar(28)
    assert "ВОСКРЕСЕНЬЕ" in sunday[4][0] and "c04030" in sunday[4][1]
    assert len(_calendar(24, 5)) == 5 and len(_calendar(24, 4)) == 4
    big = "\n".join(r.plain for r in render_cabin(s, 0.0, 160, 40))
    assert "ДИПЛОМ" in big and "★" in big
    none = "\n".join(r.plain for r in render_cabin(replace(s, order_day=None), 0.0, 120, 30))
    assert "ОКТЯБРЯ" not in none


def _fg(text, col):
    """Förgrundsfärgen (r, g, b) i kolumnen col av en renderad rad."""
    import re
    pos = 0
    for span in text.spans:
        if span.start <= col < span.end:
            m = re.search(r"#([0-9a-f]{6})", str(span.style))
            v = int(m.group(1), 16)
            return (v >> 16) & 255, (v >> 8) & 255, v & 255
    return None


def test_cabin_light_and_life():
    """H3: telefonen lyser rött på skottet när den ringer, natten släcker taklampan,
    ögonlocken sluts när han sover, det som hänger svänger när vi är jagade, rök ger dis."""
    from dataclasses import replace
    from ui.cabin_render import lids_of, render_cabin, sway_of
    g, _ = _game()
    s = replace(g.status(), order_day=24, phone=None, sleeping=False, hunted=False, night=False,
                smoke=0.0, ordered_course=g.status().course)
    calm = render_cabin(s, 0.0, 100, 26)
    ring = render_cabin(replace(s, phone="ring"), 0.0, 100, 26)     # t = 0: lampan tänd
    r0, g0, _b = _fg(calm[3], 13)                                  # skottet strax intill telefonen
    r1, g1, _b = _fg(ring[3], 13)
    assert r1 - g1 > r0 - g0 + 30                                  # rödare
    night = render_cabin(replace(s, night=True), 0.0, 100, 26)
    assert sum(_fg(night[5], 50)) < sum(_fg(calm[5], 50))          # mörkare mitt på skottet
    assert lids_of(s, 0.0) == 0.0
    asleep = replace(s, sleeping=True)
    assert all(lids_of(asleep, t) > 0.75 for t in range(0, 10))
    assert lids_of(replace(asleep, phone="ring"), 0.0) == 0.0      # telefonen väcker
    rows = [r.plain for r in render_cabin(asleep, 1.0, 100, 26)]
    assert rows[3].count("█") > 90 and rows[-2].count("█") > 90     # bara en springa mitt i
    assert sway_of(s, 0.7) == 0.0
    assert max(abs(sway_of(replace(s, hunted=True), t / 10)) for t in range(60)) > 1.0
    turning = replace(s, ordered_course=(s.course + 40) % 360)
    assert sway_of(turning, 0.0) > 1.0 and sway_of(replace(s, ordered_course=(s.course - 40) % 360), 0.0) < -1.0
    hazy = "\n".join(r.plain for r in render_cabin(replace(s, smoke=0.8), 0.0, 100, 26))
    clear = "\n".join(r.plain for r in calm)
    assert hazy.count("·") > clear.count("·") + 40
    for state in (dict(sleeping=True), dict(hunted=True), dict(smoke=1.0), dict(night=True)):
        out = render_cabin(replace(s, **state), 2.0, 100, 26)
        assert len(out) == 26 and all(len(r.plain) == 100 for r in out)


def test_cabin_door_orderly():
    """H4: ordonnansen syns under dörren innan han knackar och står i dörren på glänt medan han
    talar."""
    from dataclasses import replace
    from sim.stations.starpom import AJAR_S, STEPS_S
    from ui.cabin_render import lids_of, render_cabin
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    g.say(Role.RADIO, "order.declined", {"order": "sänd rapport", "made_t": g.now}, kind="suggest")
    doors = []
    for _ in range(12 + ORDERLY_S + AJAR_S + 5):
        g.tick()
        doors.append(g.status().door)
    first_steps, first_ajar = doors.index("steps"), doors.index("ajar")
    assert first_steps < first_ajar and first_ajar - first_steps >= STEPS_S - 1
    assert doors.count("ajar") == AJAR_S and doors[-1] is None
    assert any(r.type == "xo.orderly" for r in reports)
    s = g.status()
    ajar = "\n".join(r.plain for r in render_cabin(replace(s, door="ajar"), 0.0, 100, 26))
    assert "●" in ajar and "▓" in ajar                    # ordonnansen i ljuset från gången
    closed = "\n".join(r.plain for r in render_cabin(replace(s, door=None), 0.0, 100, 26))
    assert "╼" in closed and "▓▓" not in closed.split("\n")[8]
    assert lids_of(replace(s, sleeping=True, door="steps"), 0.0) == 0.0


def test_info_alarm_does_not_break_the_captains_sleep():
    """Ny kontakt tänder bara lampan: tiden står kvar på sömnens takt."""
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 60)                                   # jagarens första ping: telefonen
    g.command("svara")
    g.command("sov")
    _run(g, 5)
    scale = g.time_scale
    assert scale > 1
    g.say(Role.SONAR, "sonar.new_contact", {"bearing": 120.0, "designation": "S-7",
                                            "classification": "okänd kontakt"}, alarm=True)
    _run(g, 10)
    assert any(r.type == "sonar.new_contact" for r in reports)
    assert g.time_scale == scale and g.status().sleeping and g.status().phone != "ring"


def test_a_passed_wake_time_is_dropped_at_handover():
    g, reports = _game()
    g.command("väck mig " + g.clock_str(g.now + 60)[:5])
    _run(g, 600)
    g.command("starpom har befälet")
    _run(g, 30)
    assert g.status().phone != "ring"
    assert not any(r.type in ("xo.ring", "xo.call") for r in reports)


def test_phone_stops_ringing_when_the_captain_takes_back_and_a_second_take_back_is_answered():
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    fo = g.station(FirstOfficer)
    fo.ring_t = g.now                                   # telefonen ringer
    g.command("jag har befälet")
    _run(g, 3)
    assert g.status().phone != "ring"
    g.command("jag har befälet")
    _run(g, 10)
    assert any(r.type == "xo.captain_has" for r in reports)


def test_cabin_wall_has_the_chart_and_the_clinometer_in_a_big_window():
    """Stort fönster: kortet ur kunskapen på väggen under sakerna, krängningsmätaren under
    repeatrarna; kortet bara när det ryms och när vyn ges."""
    from dataclasses import replace
    from ui.cabin_render import _clinometer, render_cabin
    from ui.canvas import Canvas
    g, _ = _game()
    s = g.status()
    big = "\n".join(r.plain for r in render_cabin(s, 0.0, 200, 55, g.chart()))
    assert "КАРТА" in big and "@" in big and "КРЕН" in big
    assert "КАРТА" not in "\n".join(r.plain for r in render_cabin(s, 0.0, 200, 55))
    small = "\n".join(r.plain for r in render_cabin(s, 0.0, 120, 30, g.chart()))
    assert "КАРТА" not in small                      # för lite plats under sakerna
    c = Canvas(12, 3, "")
    _clinometer(c, 0, 0, 2.0)                       # krängt åt styrbord: nålen till höger
    mid = "".join(ch for ch, _ in c.cells[1])
    assert mid.index("▼") > 5 and "12°" in "".join(ch for ch, _ in c.cells[2])
    assert render_cabin(replace(s, captain_at="cabin"), 0.0, 200, 55, g.chart())


def test_starpom_rings_when_a_suggestion_goes_against_a_phone_order():
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    g.command("djup 50")                          # per telefon
    _run(g, 60)
    g.say(Role.SONAR, "order.declined", {"order": "djup 150", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    assert g.world.own.state.ordered_depth == 50
    st = g.status()
    assert st.phone == "ring" and g.active_suggestion() is not None
    g.command("svara")
    _run(g, 8)
    call = [r for r in reports if r.type == "xo.call"][-1]
    assert "djup 150" in call.text and "Ni beordrade djup 50" in call.text
    # ett förslag om något annat beslutar han själv
    g.say(Role.NAVIGATOR, "order.declined", {"order": "kurs 200", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    assert g.world.own.state.ordered_course == 200


def test_phone_order_binds_ten_minutes_and_never_alarms():
    from sim.stations.starpom import PHONE_ORDER_S
    g, reports = _game()
    g.command("starpom har befälet")
    _run(g, 3)
    g.command("djup 50")
    _run(g, 30)
    g.say(Role.SONAR, "order.declined", {"order": "djup 160", "made_t": g.now}, kind="suggest",
          alarm=True)
    _run(g, 12)
    assert g.world.own.state.ordered_depth == 160      # larmet går före
    g.command("djup 60")
    _run(g, PHONE_ORDER_S + 5)
    g.say(Role.SONAR, "order.declined", {"order": "djup 140", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    assert g.world.own.state.ordered_depth == 140      # telefonordern är gammal


def test_orders_before_the_handover_are_not_phone_orders():
    g, reports = _game()
    g.command("djup 50")
    g.command("starpom har befälet")
    _run(g, 3)
    g.say(Role.SONAR, "order.declined", {"order": "djup 150", "made_t": g.now}, kind="suggest")
    _run(g, 12)
    assert g.world.own.state.ordered_depth == 150
