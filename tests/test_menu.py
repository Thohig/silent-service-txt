"""Huvudmenyn: uppdragen grupperade med varianter, beskrivning och återgång."""
import asyncio

import pytest

from sim.scenario import SCENARIOS
from ui.menu import QUIT_ID, MenuScreen, brief, mission_groups, split_title, variant_label


def test_every_scenario_is_in_exactly_one_group_with_one_long_variant():
    groups = mission_groups()
    keys = [sd.key for g in groups for sd in g.variants]
    assert sorted(keys) == sorted(SCENARIOS)
    for g in groups:
        longs = [sd for sd in g.variants if sd.minutes is None]
        assert len(longs) <= 1, g.key               # ett uppdrag kan vara bara kort (svansen)
        assert g.variants[0] is g.main              # det långa först
        assert all(sd.key.split("-")[0] == g.key for sd in g.variants)
        assert g.heading and g.date


def test_missions_stand_in_sections_training_crisis_war():
    from ui.menu import SECTIONS, section_label
    groups = mission_groups()
    order = [k for k, _, _ in SECTIONS]
    idx = [order.index(g.section) for g in groups]
    assert idx == sorted(idx)                       # avdelningarna i följd
    assert all(sd.section == g.section for g in groups for sd in g.variants)
    war = {g.key for g in groups if g.section == "krig"}
    assert {"duell", "konvoj", "krig"} <= war and "kuba" not in war
    assert "KRIGET" in section_label("krig").plain
    assert "Kriget: vapen fria" in brief(SCENARIOS["duell"], None).plain


def test_training_comes_first_and_headings_come_from_titles():
    groups = mission_groups()
    assert groups[0].key == "ovning" and groups[0].heading == "Övning"
    kuba = next(g for g in groups if g.key == "kuba")
    assert (kuba.heading, kuba.date) == ("Kvadrat 7", "oktober 1962")
    assert split_title("Kvadrat 7 – sambandsfönstret, oktober 1962") == \
        ("Kvadrat 7", "sambandsfönstret", "oktober 1962")


def test_labels_and_brief():
    assert "hela uppdraget" in variant_label(SCENARIOS["kuba"]).plain
    assert "~25 min" in variant_label(SCENARIOS["kuba-kort"]).plain
    kuba = next(g for g in mission_groups() if g.key == "kuba")
    text = brief(SCENARIOS["kuba-kort"], kuba).plain
    assert "Kort variant · ~25 min" in text
    assert not text.split("\n\n")[1].startswith("Kort variant.")   # prefixet står bara en gång
    assert SCENARIOS["kuba"].summary in text                        # bakgrunden ur det långa
    assert "hela uppdraget" in text                                 # andra varianter


def test_menu_skips_headings_and_marks_the_last_mission(tmp_path):
    from ui.app import SubApp

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path)
        async with app.run_test(size=(110, 36)) as pilot:
            await pilot.pause()
            options = app.screen.query_one("#scenarios")
            assert options.highlighted_option.id == "ovning"
            await pilot.press("down", "down")       # över rubrikerna till nästa grupp
            assert options.highlighted_option.id == "kuba"
            assert "Kvadrat 7" in str(app.screen.query_one("#brief").render())
            app.switch_screen(MenuScreen(selected="konvoj-mot"))
            await pilot.pause()
            assert app.screen.query_one("#scenarios").highlighted_option.id == "konvoj-mot"
            await pilot.press("end")
            assert app.screen.query_one("#scenarios").highlighted_option.id == QUIT_ID
            await pilot.press("enter")              # Avsluta stänger programmet
            await pilot.pause()
        assert not app.is_running

    asyncio.run(run())


def test_manual_lists_every_command_and_only_real_view_words():
    from sim.stations import DEFAULT_STATIONS
    from ui import app as ui_app
    from ui.manual import SOUND_WORDS, VIEW_WORDS, order_sections

    listed = {h for _, helps in order_sections() for h in helps}
    for cls in DEFAULT_STATIONS:
        assert {s.help for s in cls.COMMANDS if s.help} <= listed
    assert "avbryt uppdraget" in listed and "ja" in listed
    from ui.views import all_words
    assert set(VIEW_WORDS) <= all_words()
    assert set(SOUND_WORDS) <= ui_app.SOUND_WORDS | set(ui_app.SPEECH_WORDS)


@pytest.mark.slow
def test_settings_change_sound_speech_and_seed_for_the_next_mission(tmp_path):
    from ui.app import GameScreen, SubApp
    from ui.manual import ManualScreen
    from ui.menu import MANUAL_ID, SETTINGS_ID
    from ui.settings import SettingsScreen

    async def run():
        app = SubApp(log_dir=tmp_path, sound=True)
        async with app.run_test(size=(110, 36)) as pilot:
            await pilot.pause()
            options = app.screen.query_one("#scenarios")
            options.highlighted = options.get_option_index(SETTINGS_ID)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)
            await pilot.press("enter")                       # ljud av
            await pilot.press("down", "enter")               # tal svenska
            await pilot.press("down", "enter", *"12x", "enter")
            assert app.fixed_seed is None                    # bara siffror
            await pilot.press(*"4711", "enter")
            assert (app.sound_wanted, app.language, app.fixed_seed) == (False, "sv", 4711)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen)
            assert "4711" in str(app.screen.query_one("#brief").render())
            options = app.screen.query_one("#scenarios")
            options.highlighted = options.get_option_index(MANUAL_ID)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ManualScreen)
            await pilot.press("escape")
            await pilot.pause()
            options = app.screen.query_one("#scenarios")
            options.highlighted = options.get_option_index("kuba")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, GameScreen)
            assert app.seed == 4711 and app.last_seed == 4711

    asyncio.run(run())


def test_stamps_grow_more_secret_towards_28_october():
    from ui.menutext import (STAMP_SECRET, STAMP_SPECIAL, STAMP_TOP_SECRET, STAMP_TRAINING,
                             mission_day, stamp_for)
    assert mission_day("Jagade, natten till 27 oktober 1962") == 27
    assert mission_day("Kvadrat 7, oktober 1962") is None
    assert stamp_for("ovning-kort", SCENARIOS["ovning-kort"].title) is STAMP_TRAINING
    assert stamp_for("kuba", SCENARIOS["kuba"].title) is STAMP_SECRET
    assert stamp_for("sundet", SCENARIOS["sundet"].title) is STAMP_TOP_SECRET
    assert stamp_for("konvoj-mot", SCENARIOS["konvoj-mot"].title) is STAMP_SPECIAL
    text = brief(SCENARIOS["jagad"], None).plain
    assert text.startswith(" СОВ. СЕКРЕТНО") and "strängt hemligt" in text


def test_header_fits_the_width_and_translates_the_russian():
    from ui.menutext import header
    for width in (80, 120, 200):
        lines = header(width).plain.split("\n")
        assert len(lines[0]) == width and len(lines[1]) == width
    plain = header(120).plain
    assert "СОВЕРШЕННО СЕКРЕТНО" in plain and "Strängt hemligt" in plain
    assert "СЕВЕРНЫЙ ФЛОТ" in plain and "Norra flottan" in plain


def test_ticker_types_the_calendar_in_order_and_starts_over():
    from ui.menutext import DISPATCHES, TICKER_CYCLE_S, TICKER_CPS, ticker_at
    s = ticker_at(0.0)
    assert (s.index, s.chars, s.typing, s.blank) == (0, 0, True, False)
    s = ticker_at(10 / TICKER_CPS)
    assert s.chars == 10 and s.typing
    seen, levels, t = [], [], 0.0
    while t < TICKER_CYCLE_S:
        s = ticker_at(t)
        if not seen or seen[-1] != s.index:
            seen.append(s.index)
            levels.append(s.level)
        t += 0.25
    assert seen == list(range(len(DISPATCHES)))
    assert levels == sorted(levels) and levels[0] == 0 and levels[-1] == 3   # bara uppåt
    assert ticker_at(TICKER_CYCLE_S + 0.01).index == 0                          # börjar om
    days = [int(d.stamp[:2]) for d in DISPATCHES]
    assert days == sorted(days) and days[-1] == 28


def test_ticker_line_fits_and_readiness_follows_the_dispatch():
    from ui.menutext import DISPATCHES, READINESS, TickerState, header, ticker_text
    for i, d in enumerate(DISPATCHES):
        full = TickerState(i, len(d.text), False, False)
        assert len(ticker_text(full, 80).plain) <= 80
        assert d.stamp in ticker_text(full, 80).plain
    assert ticker_text(TickerState(0, 0, False, True), 80).plain.strip() == "ТЕЛЕТАЙП"
    assert "ПОЛНАЯ" in header(120, 3).plain and "stridsberedskap: full" in header(120, 3).plain
    for width in (80, 100, 120):
        for lvl in range(len(READINESS)):
            line = header(width, lvl).plain.split("\n")[3]
            assert len(line) == width and READINESS[lvl].ru in line


def test_menu_screen_shows_the_ticker_and_readiness(tmp_path):
    from ui.app import SubApp
    from ui.menutext import DISPATCHES, dispatch_duration

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path)
        async with app.run_test(size=(110, 36)) as pilot:
            await pilot.pause()
            menu = app.screen
            last = len(DISPATCHES) - 1
            t = sum(dispatch_duration(i) for i in range(last)) + 2.0
            menu.animate(t)
            assert menu.ticker.index == last
            assert "ПОЛНАЯ" in str(menu.query_one("#menu-title").render())
            assert "СЕВФЛОТ 28.10" in str(menu.query_one("#ticker").render())

    asyncio.run(run())


def test_radio_moscow_comes_on_schedule_and_grows_more_ominous():
    from ui.menutext import (BULLETINS, RADIO_EVERY_S, RADIO_FIRST_S, RADIO_TUNE_S, radio_at,
                             radio_show_s, radio_text)
    assert radio_at(RADIO_FIRST_S - 1) is None
    first = radio_at(RADIO_FIRST_S + 0.5)
    assert first.number == 0 and first.bulletin is BULLETINS[0]
    assert "brus" in radio_text(first, 100).plain                     # ratten först
    speaking = radio_at(RADIO_FIRST_S + RADIO_TUNE_S + 1)
    assert BULLETINS[0].sv[:30] in radio_text(speaking, 120).plain
    assert radio_at(RADIO_FIRST_S + radio_show_s(BULLETINS[0]) + 1) is None
    late = radio_at(RADIO_FIRST_S + 40 * RADIO_EVERY_S + 1)
    assert late.bulletin is BULLETINS[-1]                              # det sista upprepas
    for b in BULLETINS:
        assert radio_show_s(b) < RADIO_EVERY_S
        assert not any("a" <= c.lower() <= "z" for c in b.ru)          # rösten läser bara kyrilliska
        assert len(radio_text(radio_at(RADIO_FIRST_S + RADIO_TUNE_S + 1), 80).plain) <= 80


def test_scene_draws_the_boat_at_the_quay_and_the_snow_moves():
    from ui.menu_scene import MIN_COLS, render_scene
    a = render_scene(80, 10, 0.5)   # lampan fladdrar ibland
    assert len(a) == 10 and all(len(line.plain) == 80 for line in a)
    text = "\n".join(line.plain for line in a)
    assert "★" in text and "✦" in text and "К-114" in text
    assert "⣿" in text                                             # skrovet är fyllt
    assert [l.plain for l in render_scene(80, 10, 0.5)] == [l.plain for l in a]   # ingen slump
    assert [l.plain for l in render_scene(80, 10, 1.5)] != [l.plain for l in a]   # snön faller
    assert render_scene(MIN_COLS - 1, 10, 0.0) == []
