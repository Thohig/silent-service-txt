"""Djupprofilen: elementen byggs ur kunskapen, och rastreringen visar dem."""
import asyncio
import random

from sim.game import Game
from sim.ownship import CRUSH_DEPTH, PERISCOPE_DEPTH, TEST_DEPTH
from sim.profile import BottomSounding, HeardEvent, Level, ProfileView
from sim.scenario import build_scenario
from ui.profile_render import render_gauge, render_profile


def _game(key="kuba", seed=3):
    return Game(build_scenario(key, random.Random(seed)), seed=seed)


def _run(g, n):
    for _ in range(n):
        g.tick()


def _text(lines):
    return "\n".join(line.plain for line in lines)


def test_levels_trace_and_layer():
    g = _game()
    g.command("djup 120")
    _run(g, 600)
    v = g.profile()
    depths = {lv.label: lv.depth for lv in v.levels}
    assert depths["periskopdjup"] == PERISCOPE_DEPTH
    assert depths["provdjup"] == TEST_DEPTH and depths["krossdjup"] == CRUSH_DEPTH
    assert depths["språngskikt"] == g.world.env.layer_depth
    assert len(v.trace) >= 60                      # var tionde sekund
    assert v.trace[-1] == (g.now, g.world.own.state.depth)
    assert max(d for _, d in v.trace) > 100


def test_bottom_only_from_the_echo_sounder():
    g = _game()
    _run(g, 30)
    assert g.profile().bottom == []
    g.command("ekolod")
    _run(g, 5)
    [b] = g.profile().bottom
    s = g.world.own.state
    assert abs(b.depth - g.world.env.bottom_at(s.x, s.y)) < 60
    assert "ekolod ger bottendjupet" not in _text(render_profile(g.profile(), 100, 30))


def test_arctic_has_ice_and_no_layer():
    g = _game("arktis", seed=2)
    _run(g, 900)
    v = g.profile()
    assert v.ice and all(s.t <= g.now for s in v.ice)
    assert "språngskikt" not in {lv.label for lv in v.levels}
    out = _text(render_profile(v, 100, 30))
    assert "█" in out or "≈" in out


def test_heard_sounds_are_noted_from_the_bus():
    g = _game()
    g.command("aktiv sonar")
    _run(g, 3)
    kinds = {e.kind for e in g.profile().events}
    assert "own_ping" in kinds


def test_no_truth_ids_in_the_profile():
    g = _game()
    g.command("ekolod")
    _run(g, 2400)
    v = g.profile()
    text = _text(render_profile(v, 120, 40)) + _text(render_gauge(v))
    for tid in ("DD1", "T1", "D1", "SSN1", "NORD7"):
        assert tid not in text


def _view(depth=90.0, ordered=90.0, items=()):
    v = ProfileView("04:00:00", 3600, 4 * 3600, depth, ordered, 5.0, 0.0, list(items))
    v.items += [Level(0, "yta", "surface", "≈"), Level(60, "språngskikt", "layer"),
                Level(300, "provdjup", "test", "╌"), Level(450, "krossdjup", "crush", "━")]
    return v


def test_render_draws_us_on_our_depth_row_and_the_ordered_depth():
    lines = render_profile(_view(depth=100, ordered=200), 90, 30, max_depth=300)
    own = next(i for i, line in enumerate(lines) if "▬▬▶" in line.plain)
    target = next(i for i, line in enumerate(lines) if "↓ 200 m" in line.plain)
    layer = next(i for i, line in enumerate(lines) if "språngskikt" in line.plain)
    assert layer < own < target
    assert len(lines) == 30
    assert all(line.cell_len == 90 for line in lines)


def test_deep_bottom_goes_in_its_own_band_with_unknown_stretches():
    v = _view(items=[BottomSounding(3000, 2380.0)])
    out = _text(render_profile(v, 100, 30))
    assert "axeln bruten" in out and "2 300" in out and "▓" in out and "?" in out
    assert "ekolod 04:50" in out


def test_shallow_bottom_is_drawn_in_place():
    v = _view(depth=40, ordered=40, items=[BottomSounding(3500, 120.0)])
    out = _text(render_profile(v, 100, 30, max_depth=150))
    assert "axeln bruten" not in out
    assert "ekolod 120" in out


def test_events_row_shows_what_was_heard():
    v = _view(items=[HeardEvent(3500, "explosion", "✱", "heard_explosion"),
                     HeardEvent(3550, "ping", "◦", "heard_ping")])
    last = render_profile(v, 100, 30)[-1].plain
    assert "✱" in last and "◦" in last


def test_gauge_is_ordered_by_depth():
    v = _view(depth=95, ordered=120, items=[BottomSounding(3500, 2380.0)])
    rows = [line.plain for line in render_gauge(v)]
    order = [next(i for i, r in enumerate(rows) if key in r)
             for key in ("yta", "skikt", "↓120", "prov", "kross", "ekolod")]
    assert order == sorted(order)


def test_tab_cycles_the_views(tmp_path):
    from ui.app import SubApp
    from ui.chart import ChartScreen
    from ui.profile import ProfileScreen
    from ui.widgets import DepthGauge

    async def run():
        app = SubApp(seed=2, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("enter", "enter")
            for _ in range(600):
                app.game.tick()
            await pilot.pause(0.7)
            assert "DJUPMÄTARE" in str(app.query_one(DepthGauge).render())
            await pilot.press(*"kurs 0")          # orderraden behåller texten
            await pilot.press("tab", "tab")
            assert isinstance(app.screen, ProfileScreen)
            await pilot.pause(0.3)
            assert "▬▬▶" in str(app.screen.query_one("#profile-body").render())
            await pilot.press("minus")
            assert app.screen.depth_zoom is not None
            await pilot.press("a")
            assert app.screen.depth_zoom is None
            app.save_screenshot(str(tmp_path / "profil.svg"))
            await pilot.press("escape")
            assert app.query_one("#order").value == "kurs 0"
            await pilot.press("tab")                 # logg → sjökort → profil → logg
            assert isinstance(app.screen, ChartScreen)
            await pilot.press("tab")
            assert isinstance(app.screen, ProfileScreen)
            await pilot.press("tab")
            assert not isinstance(app.screen, (ChartScreen, ProfileScreen))
            await pilot.press("ctrl+u", *"profil", "enter")
            assert isinstance(app.screen, ProfileScreen)
            await pilot.press("tab")
            assert not isinstance(app.screen, ProfileScreen)

    asyncio.run(run())
