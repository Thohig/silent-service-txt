"""Röktest: scenarioväljaren, introt går att hoppa över och en order kvitteras."""
import pytest
import asyncio

from sim.events import ReportDelivered
from ui.app import SubApp
from ui.menu import MenuScreen


@pytest.mark.slow
def test_app_starts_and_acknowledges_order(tmp_path):
    reports = []

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        app.game.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report.text))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("enter")        # hoppa över fjärrskrivaren
            await pilot.press("enter")        # ta befälet
            assert app.running
            await pilot.press(*"kurs 090", "enter")
            for _ in range(15):
                app.game.tick()

    asyncio.run(run())
    assert "Jest, kurs 090." in reports
    assert list(tmp_path.glob("truth-*.log"))


def test_game_begins_with_scenario_picker(tmp_path):
    async def run():
        app = SubApp(seed=1, log_dir=tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert app.game is None
            assert isinstance(app.screen, MenuScreen)
            await pilot.press("enter")        # välj första scenariot
            assert app.game is not None
            assert not isinstance(app.screen, MenuScreen)
            await pilot.press("enter")        # hoppa över fjärrskrivaren
            await pilot.press("enter")        # ta befälet
            assert app.running

    asyncio.run(run())
    assert list(tmp_path.glob("truth-*.log"))


@pytest.mark.slow
def test_tab_shows_the_chart_while_the_game_runs(tmp_path):
    from ui.chart import ChartScreen

    async def run():
        app = SubApp(seed=2, log_dir=tmp_path, scenario="arktis")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("tab")         # inget kort innan befälet är taget
            assert not isinstance(app.screen, ChartScreen)
            await pilot.press("enter", "enter")
            for _ in range(900):
                app.game.tick()
            await pilot.press("tab", "tab")  # översikten först
            assert isinstance(app.screen, ChartScreen)
            await pilot.pause(0.3)
            t0 = app.game.now
            await pilot.pause(1.5)
            assert app.game.now > t0          # realtid går vidare
            body = str(app.screen.query_one("#chart-body").render())
            assert "@" in body
            zoom = app.screen.zoom
            await pilot.press("plus")
            assert app.screen.zoom == zoom - 1
            await pilot.press("left")
            assert not app.screen.follow
            await pilot.press("space")
            assert app.screen.follow
            app.save_screenshot(str(tmp_path / "sjokort.svg"))
            await pilot.press("escape")
            assert not isinstance(app.screen, ChartScreen)
            await pilot.press(*"sjökort", "enter")
            assert isinstance(app.screen, ChartScreen)
            await pilot.press("escape")
            assert not isinstance(app.screen, ChartScreen)
            await pilot.press(*"kurs 090", "enter")   # ordern går fram igen
            assert app.game.world.own.state.ordered_course == 90

    asyncio.run(run())


@pytest.mark.slow
def test_orders_can_be_given_in_every_view(tmp_path):
    from ui.bridge import BridgeScreen
    from ui.chart import ChartScreen
    from ui.periscope import PeriscopeScreen
    from ui.boat import BoatScreen
    from ui.sonar import SonarScreen
    from ui.viewbase import OrderLine

    async def run():
        app = SubApp(seed=2, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("enter", "enter")
            # under ytan: ingen brygga i Tab-ordningen
            from ui.overview import OverviewScreen
            for i, cls in enumerate((OverviewScreen, ChartScreen, SonarScreen, BoatScreen, PeriscopeScreen)):
                await pilot.press("tab")
                assert isinstance(app.screen, cls)
                course = 100 + 10 * i
                await pilot.press(*f"kurs {course}", "enter")
                assert isinstance(app.screen, cls)            # vi stannar i vyn
                assert app.game.world.own.state.ordered_course == course
                assert "kurs" in str(app.screen.query_one(f"#{app.screen.PREFIX}-ticker").render())
            # tillbaka till sjökortet: tangenterna styr vyn bara när raden är tom
            await pilot.press("tab", "tab", "tab")
            assert isinstance(app.screen, ChartScreen)
            line = app.screen.query_one(OrderLine)
            await pilot.press("left")
            assert not app.screen.follow and line.value == ""
            await pilot.press(*"anfall", "left", "space")
            assert line.value == "anfal l" and not app.screen.follow
            await pilot.press("escape")                    # tömmer raden, stannar i vyn
            assert line.value == "" and isinstance(app.screen, ChartScreen)
            await pilot.press(*"logg", "enter")            # logg går tillbaka
            assert not isinstance(app.screen, ChartScreen)

    asyncio.run(run())


@pytest.mark.slow
def test_a_pending_suggestion_shows_in_the_view_order_line(tmp_path):
    from ui.boat import BoatScreen
    from ui.viewbase import OrderLine

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("enter", "enter")
            for _ in range(3 * 3600):
                app.game.tick()
                if app.game.status().suggestion:
                    break
            sug = app.game.status().suggestion
            assert sug
            await pilot.press(*"system", "enter")
            assert isinstance(app.screen, BoatScreen)
            await pilot.pause(0.7)
            assert sug in app.screen.query_one(OrderLine).placeholder
            await pilot.press(*"ja", "enter")
            assert app.game.status().suggestion != sug

    asyncio.run(run())


@pytest.mark.slow
def test_ending_returns_to_menu_and_next_mission_starts_clean(tmp_path):
    from ui.app import GameScreen
    from ui.chart import ChartScreen

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("enter")        # hoppa över fjärrskrivaren
            await pilot.press("enter")        # ta befälet
            first = app.game
            await pilot.press(*"avbryt uppdraget", "enter")
            assert not first.over             # vakthavande frågar först
            await pilot.press(*"ja", "enter")
            assert first.over
            await pilot.press("tab", "tab")   # vyerna går att titta på efter slutet
            assert isinstance(app.screen, ChartScreen)
            await pilot.press("enter")        # Enter i vyn: tillbaka till huvudmenyn
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen)
            assert app.game is None and not app.running
            assert app.screen.selected == "kuba"
            await pilot.press("enter")        # samma scenario igen, markerat
            await pilot.pause()
            assert isinstance(app.screen, GameScreen)
            assert app.game is not None and app.game is not first and not app.game.over
            await pilot.press("enter")
            await pilot.press("enter")
            assert app.running
            await pilot.press(*"kurs 090", "enter")
            for _ in range(15):
                app.game.tick()
            assert app.game.world.own.state.ordered_course == 90

    asyncio.run(run())
    assert len(list(tmp_path.glob("truth-*.log"))) == 2   # en sanningslogg per uppdrag


def test_the_log_never_takes_focus_and_ctrl_p_is_not_a_palette():
    """Ett klick i loggen fick orderraden att tappa fokus (ordern försvann); ctrl+p öppnade
    Textuals kommandopalett mitt i spelet och trasslade till skärmstacken."""
    from ui.widgets import ReportLog
    assert not ReportLog.can_focus
    assert not SubApp.ENABLE_COMMAND_PALETTE


@pytest.mark.slow
def test_log_view_keeps_mirroring_after_the_end_and_cabin_enter_goes_to_menu(tmp_path):
    from ui.bridge import BridgeScreen
    from ui.widgets import ReportLog

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.press("enter", "enter")
            await pilot.pause()
            app.push_screen(BridgeScreen())
            await pilot.pause(0.2)
            assert len(app.screen._timers) == 3            # inte dubbla (draw, förslag, …)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("tab", "tab")                # stort fönster: översikten, loggvyn
            await pilot.pause()
            main = app.gs().query_one("#log", ReportLog)
            await pilot.press(*"avbryt uppdraget", "enter")
            await pilot.press(*"ja", "enter")
            await pilot.pause(0.5)
            assert app.game.over and main.mirror is not None
            await pilot.press(*"hytt", "enter")
            await pilot.pause(0.7)
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert isinstance(app.screen, MenuScreen) and app.game is None
            assert [type(s).__name__ for s in app.screen_stack][-1] == "MenuScreen"

    asyncio.run(run())
