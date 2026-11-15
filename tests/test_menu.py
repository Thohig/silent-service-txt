"""Huvudmenyn: uppdragen grupperade med varianter, beskrivning och återgång."""
import asyncio

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
