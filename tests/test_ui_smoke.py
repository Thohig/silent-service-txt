"""Röktest: appen startar, introt går att hoppa över och en order kvitteras."""
import asyncio

from sim.events import ReportDelivered
from ui.app import SubApp


def test_app_starts_and_acknowledges_order(tmp_path):
    reports = []

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path)
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
