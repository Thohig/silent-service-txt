"""Centralen som bild: storlek, periskopet, ljuset, rapporterande platser, rök och vatten."""
import asyncio
from dataclasses import replace

import pytest

from sim.game import StatusSnapshot
from ui.central_render import (DIAL_ROW, DIALS, FLOOR_ROW, H, PERI_COL, PERI_EYE_UP, W,
                               plane_angle, render_central, rudder_angle)

BASE = StatusSnapshot(clock=0, sim_time=0, course=90, ordered_course=90, speed=6,
                      ordered_speed=6, depth=100, ordered_depth=100, changing=frozenset(),
                      time_scale=1, contacts_held=())


def plain(s: StatusSnapshot, **kw) -> list[str]:
    return [t.plain for t in render_central(s, **kw)]


def styles_at(s: StatusSnapshot, row: int, col: int, **kw) -> str:
    line = render_central(s, **kw)[row]
    return " ".join(str(span.style) for span in line.spans if span.start <= col < span.end)


def test_fixed_size():
    for s in (BASE, replace(BASE, smoke=0.9, flooding=60, hunted=True, bridge="manned")):
        rows = plain(s, t=0.3)
        assert len(rows) == H
        assert all(len(r) == W for r in rows)


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


def test_compass_needle_follows_course():
    col = DIALS["kurs"] + 3
    north = plain(replace(BASE, course=0))
    assert north[DIAL_ROW + 1][col] == "│"
    east = plain(replace(BASE, course=90))
    assert east[DIAL_ROW + 2][col + 1] == "─"


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


def test_periscope_column_stays_clear_of_dials():
    rows = plain(replace(BASE, periscope="hold", periscope_up_s=20))
    assert rows[DIAL_ROW + 2][PERI_COL:PERI_COL + 2] == "┃┃"


@pytest.mark.slow
def test_central_shown_beside_the_log_and_hidden_when_narrow(tmp_path):
    from ui.app import SubApp
    from ui.widgets import CentralView

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("enter", "enter")
            for _ in range(5):
                app.game.tick()
            await pilot.pause(0.7)
            central = app.gs().query_one(CentralView)
            assert central.display
            assert "╭─────╮" in str(central.render())
            await pilot.resize_terminal(90, 30)
            await pilot.pause(0.1)
            assert not central.display

    asyncio.run(run())
