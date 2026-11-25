"""Centralen som bild: storlek, periskopet, ljuset, rapporterande platser, rök och vatten.
Bara egna instrument: inga kontakter (de står i översikten)."""
import asyncio
from dataclasses import replace

import pytest

from sim.game import StatusSnapshot
from ui.central_render import (DIAL_ROW, AMBER, GREEN, RED, JULGRAN, eyepiece, openings,
                               H, W, Geometry, plane_angle, render_central, rudder_angle)
from ui.styles import CONTACT_STYLE

G = Geometry(W, H)
FLOOR_ROW, PERI_COL, PERI_EYE_UP = G.floor, G.peri, G.peri_eye_up

BASE = StatusSnapshot(clock=0, sim_time=0, course=90, ordered_course=90, speed=6,
                      ordered_speed=6, depth=100, ordered_depth=100, changing=frozenset(),
                      time_scale=1, contacts_held=())


def plain(s: StatusSnapshot, **kw) -> list[str]:
    return [t.plain for t in render_central(s, **kw)]


def styles_at(s: StatusSnapshot, row: int, col: int, **kw) -> str:
    line = render_central(s, **kw)[row]
    return " ".join(str(span.style) for span in line.spans if span.start <= col < span.end)


def test_size_follows_the_space_given():
    busy = replace(BASE, smoke=0.9, flooding=60, hunted=True, bridge="manning",
                   periscope="hold", periscope_up_s=3)
    for s in (BASE, busy):
        for w, h in ((W, H), (90, 20), (130, 26), (200, 50), (10, 5)):
            rows = plain(s, t=0.3, width=w, height=h)
            assert len(rows) == max(H, h)
            assert all(len(r) == max(W, w) for r in rows)


def test_walls_ladder_and_periscope_in_order():
    for g in (Geometry(W, H), Geometry(150, 32)):
        assert g.left[1] < g.ladder < g.peri < g.right[0]


def test_periscope_rises_with_the_mast():
    down = plain(BASE)
    assert "▐██▌" not in "".join(down)
    up = replace(BASE, depth=15, ordered_depth=15, periscope="hold", periscope_up_s=20)
    rows = plain(up)
    assert "▐██▌" in rows[PERI_EYE_UP]
    rising = plain(replace(up, periscope_up_s=1))
    assert "▐██▌" in rising[FLOOR_ROW - 1]
    # kikaren från bryggan hissar inget periskop
    assert "▐██▌" not in "".join(plain(replace(up, periscope_optic="kikare")))


def test_small_room_has_pipes_and_no_dials():
    rows = plain(BASE)
    a, b = G.left
    assert set(rows[2][a:b + 1]) <= {"═", "⊗"}
    assert plain(replace(BASE, course=0)) == plain(replace(BASE, course=200, depth=250))


def test_fullscreen_in_80_by_24_shows_the_readouts_as_text():
    """Centralen i helskärm i ett 80 × 24-fönster (bilden 80 × 19) var tom: braillemätarna kräver 100 × 22."""
    s = replace(BASE, course=47, depth=163, ordered_depth=163, speed=4, ordered_speed=4)
    text = "\n".join(plain(s, width=80, height=19))
    for want in ("GYRO", "047", "DJUP", "163 m", "FART", "4,0", "TELEGRAF", "LÄNS", "KLOCKA"):
        assert want in text, want
    assert "⊗" not in text                                  # rören (ventilerna) bara i den lilla bilden


def test_rudder_and_planes_follow_the_orders():
    turning = replace(BASE, ordered_course=120, changing=frozenset({"course"}))
    assert rudder_angle(turning) > 0
    assert rudder_angle(replace(turning, ordered_course=60)) < 0
    assert rudder_angle(BASE) == 0
    diving = replace(BASE, ordered_depth=200, changing=frozenset({"depth"}))
    assert plane_angle(diving) > 0
    assert plane_angle(replace(diving, ordered_depth=40)) < 0


def test_red_light_at_night_and_when_hunted():
    normal = styles_at(BASE, 0, 5)
    assert styles_at(replace(BASE, night=True), 0, 5) != normal
    assert styles_at(replace(BASE, hunted=True), 0, 5) != normal


def test_speaker_lights_up():
    quiet = styles_at(BASE, 7, 3)
    assert styles_at(BASE, 7, 3, speaking={"sonar": 0.5}) != quiet
    assert styles_at(BASE, 7, 3, speaking={"sonar": 10.0}) == quiet


def test_open_hatch_shows_the_sky():
    assert "███" in plain(replace(BASE, depth=0, bridge="manned"))[0]
    assert "███" not in plain(BASE)[0]


def test_smoke_and_water():
    smoky = "".join(plain(replace(BASE, smoke=0.5, fire=True)))
    assert "░" in smoky or "▒" in smoky
    wet = plain(replace(BASE, flooding=50))
    assert "≈" in wet[FLOOR_ROW - 2]
    assert "≈" not in "".join(plain(replace(BASE, flooding=0.1)))


def test_eyepiece_turns_with_the_periscope_bearing():
    assert eyepiece(0) == "═▐██▌═"                       # rakt förut: handtagen åt sidorna
    assert eyepiece(90).endswith("▶") and eyepiece(-90).startswith("◀")
    assert "◉◉" in eyepiece(180) and "◉◉" in eyepiece(-170)
    assert eyepiece(40)[-1] == "◥" and eyepiece(-130)[0] == "◣"
    up = replace(BASE, depth=15, ordered_depth=15, periscope="hold", periscope_up_s=20)
    assert "═▐██▌▶" in plain(replace(up, periscope_train=180))[PERI_EYE_UP]   # kurs 090: styrbord tvärs


def test_the_periscope_shows_only_the_eyepiece():
    up = replace(BASE, depth=15, ordered_depth=15, periscope="look", periscope_up_s=20,
                 periscope_train=47, periscope_power="hög")
    for kw in ({}, {"width": 130, "height": 36}):
        assert "PERISKOP" not in "".join(plain(up, **kw))   # bäringen står i översikten


def test_julgran_shows_every_opening():
    assert [lamp for _, lamp in openings(BASE)] == [GREEN] * len(JULGRAN)
    busy = replace(BASE, depth=0, bridge="manned", radar_up=True, transmitting=True,
                   ventilating=True, blowing=True, periscope="hold")
    lamps = dict(openings(busy))
    assert lamps["Lucka"] == lamps["Radar"] == lamps["Antenn"] == lamps["Ventil"] == RED
    assert lamps["Periskop"] == RED and lamps["Blåsning"] == AMBER
    assert dict(openings(replace(busy, periscope_optic="kikare")))["Periskop"] == GREEN


def test_big_julgran_has_names_and_small_has_lamps():
    g = Geometry(130, 36)
    rows = plain(replace(BASE, radar_up=True), width=130, height=36)
    assert all(any(name in rows[r] for r in (g.head, g.body)) for name in JULGRAN)
    col = rows[g.head].index("Radar") - 2
    assert styles_at(replace(BASE, radar_up=True), g.head, col, width=130, height=36) == RED
    small = plain(BASE)
    assert small[G.lamps].count("●") == len(JULGRAN)
    assert styles_at(replace(BASE, radar_up=True), G.lamps, G.julgran + 4) == RED


def test_no_contacts_in_the_central():
    """Centralen läser bara egna instrument: plottets kontakter syns inte där."""
    s = replace(BASE, contacts_held=("S-3", "S-1"), contact_kinds=("threat", "civil"),
                contact_bearings=(45.0, 300.0))
    for kw in ({}, {"width": 130, "height": 36}):
        assert plain(s, **kw) == plain(BASE, **kw)
        rows = render_central(s, **kw)
        assert not any(sp.style == CONTACT_STYLE["threat"] for r in rows for sp in r.spans)


def test_periscope_column_stays_clear_of_dials():
    rows = plain(replace(BASE, periscope="hold", periscope_up_s=20))
    assert rows[DIAL_ROW + 2][PERI_COL:PERI_COL + 2] == "┃┃"


@pytest.mark.slow
def test_layout_follows_the_window(tmp_path):
    """Stort fönster: översikten är huvudvyn med loggremsan, centralen en helskärmsvy och loggvyn
    visar allt. Litet: loggen stor, översikten en vy i Tab-ordningen."""
    from ui.app import SubApp
    from ui.central import CentralScreen
    from ui.logview import LogScreen
    from ui.overview import OverviewScreen
    from ui.widgets import OverviewPanel, ReportLog

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.press("enter", "enter")
            for _ in range(5):
                app.game.tick()
            await pilot.pause(0.7)
            gs = app.gs()
            panel = gs.query_one(OverviewPanel)
            assert gs.big and panel.display
            assert gs.query_one("#log", ReportLog).size.height < 10
            assert "KONTAKTER" in str(panel.render())

            await pilot.press(*"kurs 090", "enter")
            await pilot.press("tab")                     # första vyn: centralen i helskärm
            assert isinstance(app.screen, CentralScreen)
            await pilot.pause(0.3)
            body = app.screen.query_one("#central-body")
            lines = str(body.render()).split("\n")
            assert body.size.width >= 138 and len(lines) >= 38
            assert any(0x2800 < ord(ch) <= 0x28FF for ch in "".join(lines))   # instrumenten
            assert "LUTNING" in "".join(lines)
            await pilot.press("tab")                     # sedan hela loggboken
            assert isinstance(app.screen, LogScreen)
            full = app.screen.query_one("#logview-log", ReportLog)
            for _ in range(10):
                app.game.tick()
            await pilot.pause(0.2)
            assert len(full.entries) == len(gs.query_one("#log", ReportLog).entries)
            await pilot.press(*"översikt", "enter")      # tillbaka till huvudvyn
            assert app.screen is gs
            await pilot.press(*"central", "enter")
            assert isinstance(app.screen, CentralScreen)
            await pilot.press("escape")
            assert app.screen is gs

            await pilot.resize_terminal(90, 28)
            await pilot.pause(0.3)
            assert not gs.big and not panel.display
            await pilot.press("tab")                     # litet: översikten är en vy
            assert isinstance(app.screen, OverviewScreen)
            await pilot.press("tab")
            assert isinstance(app.screen, CentralScreen)
            await pilot.press("escape")

    asyncio.run(run())
