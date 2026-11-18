"""Sonarvyn: vattenfallets element byggs ur kunskapen (aldrig sanningen)."""
import random

import pytest

from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.sonar_view import (BearingTrace, ContactLine, HeardMark, LostMark, OwnMark, OwnTurn,
                            SolutionTrace,
                            SonarView, TargetTurn, bearing_drift, drift_words, own_turns)


def _game(key="jagad-kort", seed=2):
    return Game(build_scenario(key, random.Random(seed)), seed=seed)


def test_bearing_drift_across_north():
    pts = [(t, (350 + t / 30) % 360) for t in range(0, 181, 5)]    # 2°/min medurs över 000
    assert bearing_drift(pts, 180) == pytest.approx(2.0, abs=0.01)
    back = [(t, (10 - t / 60) % 360) for t in range(0, 181, 5)]
    assert bearing_drift(back, 180) == pytest.approx(-1.0, abs=0.01)
    assert bearing_drift(pts[:3], 180) is None                        # för få
    assert bearing_drift(pts, 1000) is None                           # för gamla


def test_drift_words():
    assert drift_words(None) == "drift okänd"
    assert drift_words(0.1) == "bäringen står"
    assert drift_words(2.04) == "drar höger 2,0°/min"
    assert drift_words(-12.6) == "drar vänster 13°/min"


def test_own_turns_from_course_log():
    log = [(t, 90.0) for t in range(0, 100, 10)]
    log += [(100 + 10 * i, 90.0 + 10 * i) for i in range(1, 7)]       # gir till 150
    log += [(170 + 10 * i, 150.0) for i in range(1, 6)]
    log += [(230, 152.0), (240, 152.0)]                               # liten rättelse
    log += [(250, 140.0), (260, 128.0), (270, 128.0)]                 # gir babord 24°
    turns = own_turns(log)
    assert [(round(t.course_from), round(t.course_to)) for t in turns] == [(90, 150), (152, 128)]
    assert own_turns([(0, 355.0), (10, 5.0), (20, 15.0), (30, 15.0)])[0].course_to == 15.0


def test_heading_at():
    v = SonarView("12:00:00", 100, 0, 200.0)
    from sim.sonar_view import OwnHeading
    v.items.append(OwnHeading(((0, 10.0), (50, 20.0))))
    assert v.heading_at(-5) == 200.0 and v.heading_at(70) == 20.0
    assert v.heading_at(0) == 10.0 and v.heading_at(25) == pytest.approx(15.0)
    w = SonarView("12:00:00", 100, 0, 200.0)       # genom norr den korta vägen
    w.items.append(OwnHeading(((0, 350.0), (10, 10.0), (10, 10.0))))
    assert w.heading == [(0, 350.0), (10, 10.0)]
    assert w.heading_at(5) == pytest.approx(0.0) or w.heading_at(5) == pytest.approx(360.0)


def test_own_turns_ignore_a_repeated_point_mid_turn():
    """Kursen nu läggs efter loggen; samma tidpunkt två gånger får inte avsluta giren."""
    log = [(0, 90.0), (10, 90.0), (20, 100.0), (30, 112.0), (30, 112.0), (40, 124.0),
           (50, 135.0), (60, 135.0)]
    turns = own_turns(log)
    assert [(t.t, t.course_from, t.course_to) for t in turns] == [(60, 90.0, 135.0)]


@pytest.mark.slow
def test_waterfall_from_knowledge_only():
    g = _game()
    g.command("kurs 90")
    for _ in range(900):
        g.tick()
    v = g.sonar()
    k = g.knowledge
    traces = {t.designation: t for t in v.traces}
    assert traces and set(traces) <= set(k.tracks)
    for d, tr in traces.items():
        obs = [o for o in k.tracks[d].observations if o.source in ("sonar", "ping", "aktiv")]
        assert tr.points[-1] == (obs[-1].t, obs[-1].bearing, obs[-1].se)
        assert tr.kind == "threat"           # jagare, klassade
    lines = v.lines
    assert {c.designation for c in lines} == set(traces)
    assert all(c.solution_quality in Quality for c in lines)
    assert any(c.drift is not None for c in lines)
    assert v.of(HeardMark) and all(0 <= m.bearing < 360 for m in v.of(HeardMark))
    assert v.of(SolutionTrace)
    turns = v.of(TargetTurn)
    for d in {t.designation for t in turns}:     # ett märke per kontakt och fem minuter
        ts = sorted(t.t for t in turns if t.designation == d)
        assert all(b - a >= 300 for a, b in zip(ts, ts[1:]))
    assert v.of(OwnTurn)                          # vi girade
    truth_ids = {e.id for e in g.world.contacts}
    text = repr(v.items)
    assert not any(f"'{i}'" in text for i in truth_ids)


def test_no_contacts_no_traces():
    g = _game("ovning", seed=1)
    for _ in range(30):
        g.tick()
    v = g.sonar()
    assert v.traces == [] and v.lines == []
    assert v.heading and v.heading[-1] == (g.now, round(g.world.own.state.course, 1))


# --- rastreringen -------------------------------------------------------------------
from sim.sonar_view import OwnHeading  # noqa: E402
from ui.sonar_render import LEFT, render_sonar  # noqa: E402


def _view(now=1800, course=90.0, items=()):
    v = SonarView("12:30:00", now, 12 * 3600, course)
    v.items.extend(items)
    return v


def _plain(lines):
    return [line.plain for line in lines]


def test_render_axes_and_bow():
    rows = _plain(render_sonar(_view(), 100, 30))
    assert len(rows) == 30 and all(len(r) == 100 for r in rows)
    assert "000" in rows[0] and "090" in rows[0] and "270" in rows[0]
    assert "F" in rows[1]                                     # fören på 090
    assert rows[2].rstrip().endswith("◂ nu")
    assert any("12:" in r for r in rows[3:])                  # klockslag i marginalen


def test_trace_drawn_at_its_bearing_newest_on_top():
    pts = tuple((t, 45.0, 10.0) for t in range(0, 1801, 5))
    v = _view(items=[BearingTrace("S-3", pts, "threat")])
    rows = _plain(render_sonar(v, 100, 30, window_s=1800, center=0.0))
    cols = 100 - LEFT - 6
    col = LEFT + int((45 + 180) / 360 * 2 * cols) // 2
    body = rows[2:]
    assert all("⠀" < r[col] <= "⣿" for r in body[1:])   # brailleprickar hela vägen
    assert "S-3" in body[0]
    # relativ bäring: fören (090) i mitten ⇒ 045 sann = 315 relativt
    rel = _plain(render_sonar(v, 100, 30, window_s=1800, center=0.0, relative=True))
    col_rel = LEFT + int((-45 + 180) / 360 * 2 * cols) // 2
    assert "⠀" < rel[10][col_rel] <= "⣿"
    assert "för" in rel[0] and "akter" in rel[0]


def test_old_points_outside_window_are_not_drawn():
    pts = tuple((t, 200.0, 10.0) for t in range(0, 300, 5))      # bara för 25–30 min sedan
    v = _view(items=[BearingTrace("S-1", pts, "contact")])
    rows = _plain(render_sonar(v, 100, 30, window_s=600))
    assert not any(any("⠀" < ch <= "⣿" for ch in r) for r in rows)


def test_heard_marks_lost_and_own_sounds():
    pts = tuple((t, 100.0, 3.0) for t in range(600, 1500, 5))
    items = [BearingTrace("S-2", pts, "threat", held=False),
             HeardMark(1700, "explosion", 300.0, "✱", "heard_explosion"),
             HeardMark(1500, "splash", 300.0, "↓", "heard_splash"),
             HeardMark(1200, "ping", 100.0, "◦", "heard_ping", "S-2"),   # på spåret: syns inte
             HeardMark(1000, "ping", 200.0, "◦", "heard_ping"),
             LostMark(1500, "S-2", 100.0),
             OwnMark(1790, "ping", "!")]
    rows = _plain(render_sonar(_view(items=items), 100, 30, window_s=1800, center=180.0))
    text = "\n".join(rows)
    assert "✱" in text and "↓" in text and "∅" in text
    assert text.count("◦") == 1
    assert rows[2][0] == "!"
    lost_row = next(r for r in rows if "∅" in r)
    assert "S-2" in lost_row


def test_solution_only_when_asked_and_turns_marked():
    items = [SolutionTrace("S-1", tuple((t, 300.0) for t in range(0, 1801, 20)), Quality.GOD),
             TargetTurn(900, "S-1", 300.0),
             OwnTurn(1200, 90.0, 150.0), OwnTurn(600, 150.0, 120.0)]
    off = _plain(render_sonar(_view(items=items), 100, 30, center=180.0))
    on = _plain(render_sonar(_view(items=items), 100, 30, center=180.0, show_solution=True))
    braille = lambda rows: sum(1 for r in rows for ch in r if "⠀" < ch <= "⣿")  # noqa: E731
    assert braille(off) == 0 and braille(on) > 20
    assert any("‹gir" in r for r in off)
    margin = [r[1] for r in off]
    assert "↻" in margin and "↺" in margin
    assert any(r.count("╌") > 20 for r in off)


def test_contact_lines_under_the_waterfall():
    lines = [ContactLine("S-1", "jagare", Quality.GOD, 47.0, 2.04, Quality.OSAKER, "threat"),
             ContactLine("S-2", "handelsfartyg", Quality.SAKER, 300.0, None, None, "civil",
                         held=False)]
    rows = _plain(render_sonar(_view(items=lines), 100, 30))
    assert len(rows) == 30
    assert rows[-2].startswith(" S-1") and "bäring 047" in rows[-2]
    assert "drar höger 2,0°/min" in rows[-2] and "lösning osäker" in rows[-2]
    assert "tappad" in rows[-1] and "lösning ingen" in rows[-1]
    many = [ContactLine(f"S-{i}", "okänd", Quality.DALIG, 10.0 * i, 0.0, None) for i in range(12)]
    rows = _plain(render_sonar(_view(items=many), 100, 24))
    assert len(rows) == 24 and rows[-1].strip() == "… och 7 till"


@pytest.mark.slow
def test_sonar_screen_keys_and_words(tmp_path):
    import asyncio

    from ui.app import SubApp
    from ui.chart import ChartScreen
    from ui.sonar import SonarScreen

    async def run():
        app = SubApp(seed=2, log_dir=tmp_path, scenario="jagad-kort")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("enter", "enter")
            await pilot.pause(0.3)
            for _ in range(300):
                app.game.tick()
            await pilot.press(*"sonar", "enter")
            assert isinstance(app.screen, SonarScreen)
            await pilot.pause(0.7)
            body = str(app.screen.query_one("#sonar-body").render())
            assert "◂ nu" in body and "S-1" in body
            head = str(app.screen.query_one("#sonar-head").render())
            assert "SONARRUMMET" in head and "ГИДРОАКУСТИЧЕСКАЯ РУБКА" in head
            await pilot.press("down")
            assert app.screen.relative
            await pilot.press("up", "minus", "right")
            assert app.screen.show_solution and app.screen.window_s == 3600 and app.screen.turn == 30
            await pilot.press("space")
            assert app.screen.turn == 0
            app.save_screenshot(str(tmp_path / "sonar.svg"))
            await pilot.press(*"kurs 200", "enter")              # order i vyn
            assert isinstance(app.screen, SonarScreen)
            assert app.game.world.own.state.ordered_course == 200
            await pilot.press("escape")
            assert not isinstance(app.screen, SonarScreen)
            await pilot.press("tab", "tab")       # stort fönster: loggboken → sjökort → sonar
            assert isinstance(app.screen, ChartScreen)
            await pilot.press("tab")
            assert isinstance(app.screen, SonarScreen)

    asyncio.run(run())


def test_status_bar_contacts_threats_first_in_colour():
    import dataclasses

    from ui.widgets import CONTACT_STYLE, contacts_text
    g = _game("kuba", seed=3)
    s = g.status()
    s = dataclasses.replace(s, contacts_held=("S-2", "S-4", "S-10"),
                            contact_kinds=("threat", "contact", "civil"))
    t = contacts_text(s, 80)
    assert t.plain == " S-2 S-4 S-10"
    assert [sp.style for sp in t.spans] == [CONTACT_STYLE["threat"], CONTACT_STYLE["contact"],
                                            CONTACT_STYLE["civil"]]
    hunted = contacts_text(dataclasses.replace(s, hunted=True), 80)
    assert "blink" in str(hunted.spans[0].style) and "blink" not in str(hunted.spans[1].style)
    assert contacts_text(s, 9).plain == " S-2 +2"


def test_game_orders_held_contacts_by_kind():
    from sim.game import _desig_no
    assert sorted(["S-10", "S-2", "S-1"], key=_desig_no) == ["S-1", "S-2", "S-10"]
    g = _game("jagad-kort", seed=2)
    for _ in range(60):
        g.tick()
    s = g.status()
    assert len(s.contact_kinds) == len(s.contacts_held)
    assert set(s.contact_kinds) <= {"threat", "contact", "civil", "benign", "friendly"}
