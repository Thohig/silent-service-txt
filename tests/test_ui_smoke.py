"""Röktest: scenarioväljaren, introt går att hoppa över och en order kvitteras."""
import asyncio

from sim.events import ReportDelivered
from ui.app import SubApp


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
    assert "Kurs 090, aye." in reports
    assert list(tmp_path.glob("truth-*.log"))


def test_game_begins_with_scenario_picker(tmp_path):
    async def run():
        app = SubApp(seed=1, log_dir=tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert app.game is None
            assert app.query_one("#picker").display
            await pilot.press("enter")        # välj första scenariot
            assert app.game is not None
            assert not app.query_one("#picker").display
            await pilot.press("enter")        # hoppa över fjärrskrivaren
            await pilot.press("enter")        # ta befälet
            assert app.running

    asyncio.run(run())
    assert list(tmp_path.glob("truth-*.log"))


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
            await pilot.press("tab")
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
            await pilot.press("c")
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
