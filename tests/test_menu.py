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
        assert len(longs) == 1, g.key
        assert g.variants[0] is longs[0]            # det långa först
        assert all(sd.key.split("-")[0] == g.key for sd in g.variants)
        assert g.heading and g.date


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
            await pilot.press("down", "down")       # över rubriken till nästa grupp
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
    all_views = (ui_app.CHART_WORDS | ui_app.PROFILE_WORDS | ui_app.SYSTEM_WORDS
                 | ui_app.PERISCOPE_WORDS | ui_app.BRIDGE_WORDS | ui_app.LOG_WORDS
                 | ui_app.CENTRAL_WORDS)
    assert set(VIEW_WORDS) <= all_views
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
