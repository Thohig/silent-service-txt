"""Översikten (sim/overview.py, ui/overview_render.py): kontakttabellen ur plottet, uppdraget,
periskopet och bilden i den storlek den får. Bara kunskap: inga sanningens id:n."""
import asyncio
import random
import re
from dataclasses import replace

import pytest

from sim.game import Game
from sim.overview import ContactRow, Line, OverviewView
from sim.reports import Quality
from sim.scenario import build_scenario
from ui.overview_render import contact_line, render_overview

TRUTH_ID = re.compile(r"\b(DD|T|SS|M|F)\d+\b")


def _game(key="konvoj-kort", seed=2, ticks=300):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    for _ in range(ticks):
        g.tick()
    return g


def _render(g, w, h):
    return render_overview(g.overview(), g.chart(), g.sonar(), g.profile(), g.systems(), w, h)


@pytest.mark.slow
def test_contacts_are_the_plot_s_with_solutions_only_where_the_chart_shows_them():
    g = _game()
    ov = g.overview()
    rows = ov.contacts
    assert rows, "konvojen ska höras efter uppvärmningen"
    held = set(g.status().contacts_held)
    assert {r.designation for r in rows if r.held} == held
    for r in rows:
        tr = g.knowledge.track(r.designation)
        assert tr is not None and not tr.sunk
        if r.range_nm is not None:
            assert r.quality is not None and r.quality >= Quality.OSAKER
            assert tr.solution is not None and r.quality == tr.solution.quality
    kinds = [r.kind for r in rows if r.held]
    assert kinds == sorted(kinds, key=("threat", "contact", "civil", "benign", "friendly").index)


@pytest.mark.slow
def test_overview_never_shows_truth_ids_and_fits_the_size():
    g = _game()
    for w, h in ((160, 44), (120, 36), (100, 30), (80, 24), (60, 20)):
        rows = _render(g, w, h)
        assert len(rows) == h
        assert all(len(r.plain) == w for r in rows), (w, h)
        text = "\n".join(r.plain for r in rows)
        assert not TRUTH_ID.search(text)
        assert "KONTAKTER" in text and "UPPDRAG" in text


@pytest.mark.slow
def test_reading_the_overview_does_not_change_the_game():
    """Översikten läser kunskapen och räknar inte om lösningar: samma frö ger samma rapporter."""
    from sim.events import ReportDelivered

    def run(look: bool) -> list[str]:
        g = Game(build_scenario("konvoj-kort", random.Random(3)), seed=3)
        out: list[str] = []
        g.bus.subscribe(ReportDelivered, lambda e: out.append(e.report.text))
        for _ in range(300):
            g.tick()
            if look:
                g.overview()
        return out
    assert run(True) == run(False)


def test_mission_lines_from_the_order_and_the_clock():
    g = _game("kuba", ticks=5)
    lines = {ln.label: ln for ln in g.overview().lines}
    assert lines["Ordern"].text == "patrullera"
    assert "kvar" in lines["Tiden ut"].text
    assert "Läget" not in lines


def test_periscope_line_only_while_up():
    g = _game("kuba", ticks=5)
    assert not [ln for ln in g.overview().lines if ln.panel == "PERISKOP"]
    peri = next(st for st in g.stations if type(st).__name__ == "PeriscopeWatch")
    peri.mode, peri.train = "look", 47.0
    g.invalidate_views()
    line = next(ln for ln in g.overview().lines if ln.panel == "PERISKOP")
    assert line.text.startswith("047 · titt")


def test_contact_line_shows_quality_and_lost():
    r = ContactRow("S-3", "threat", "jagare, ångturbiner", Quality.SAKER, True, 99.6, 0,
                   1.26, 212.0, 9.3, Quality.GOD)
    t = contact_line(r, 60)
    assert len(t.plain) == 60
    assert t.plain.startswith("S-3  jagare") and "100" in t.plain and "1,3 nm" in t.plain
    assert "god" in t.plain and "tappad" not in t.plain
    lost = contact_line(replace(r, held=False, range_nm=None, course=None, speed=None,
                                quality=Quality.DALIG, bearing_age_s=300), 60)
    assert "(5 min)" in lost.plain and "tappad" in lost.plain


def test_empty_overview_says_so():
    from ui.overview_render import contacts_panel
    rows = contacts_panel(OverviewView("00:00:00", [Line("UPPDRAG", "Ordern", "patrullera")]), 50, 5)
    assert "inga kontakter" in rows[1].plain


@pytest.mark.slow
def test_overview_screen_opens_with_its_word(tmp_path):
    from ui.app import SubApp
    from ui.overview import OverviewScreen

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.press("enter", "enter")
            for _ in range(5):
                app.game.tick()
            await pilot.press(*"sjökort", "enter")
            await pilot.press(*"översikt", "enter")       # stort fönster: tillbaka till huvudvyn
            await pilot.pause(0.6)
            assert app.screen is app.gs()
            from ui.widgets import OverviewPanel
            body = str(app.gs().query_one(OverviewPanel).render())
            assert "KONTAKTER" in body and "SJÖKORT" in body
            await pilot.resize_terminal(90, 28)              # litet fönster: en egen vy
            await pilot.pause(0.2)
            await pilot.press(*"översikt", "enter")
            await pilot.pause(0.6)
            assert isinstance(app.screen, OverviewScreen)
            assert "KONTAKTER" in str(app.screen.query_one("#overview-body").render())
            await pilot.press("escape")
            assert not isinstance(app.screen, OverviewScreen)

    asyncio.run(run())


def test_two_columns_on_the_main_screen_at_100_columns():
    """Huvudskärmen i ett 100 kolumner brett fönster ger panelen 98: sjökortet ska ändå synas."""
    from ui.overview_render import TWO_COL_W
    assert TWO_COL_W <= 98


def test_quality_and_lost_always_fit_in_a_narrow_table():
    for w in (40, 44, 52, 60, 80):
        for held in (True, False):
            r = ContactRow("S-12", "civil", "handelsfartyg, diesel, en axel", Quality.SAKER, held, 237.0, 0,
                           12.34, 172.0, 11.7, Quality.OSAKER)
            t = contact_line(r, w).plain
            lost = "∅" if w < 60 else "tappad"
            assert len(t) == w and "osäker" in t and (lost in t) == (not held), (w, t)
            assert "12,3" in t and "172" in t


def test_next_radio_window_under_the_mission():
    g = _game("kuba", ticks=5)
    line = next((ln for ln in g.overview().lines if ln.label == "Samband"), None)
    assert line is not None and line.panel == "UPPDRAG"
    assert line.text.startswith("nästa ") and "min" in line.text
