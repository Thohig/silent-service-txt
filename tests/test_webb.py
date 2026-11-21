"""Webbversionen (`web/`): bygget, drivrutinen för Pyodide och uppvärmningen i bitar.

Drivrutinen provas här i vanlig CPython med en låtsasterminal; i webbläsaren är `bridge`
xterm.js. Själva Pyodide provas för hand (`web/README.md`)."""
import asyncio
import random
import sys
import zipfile
from pathlib import Path

import pytest

from sim.game import Game
from sim.scenario import build_scenario

WEB = Path(__file__).resolve().parent.parent / "web"
sys.path.insert(0, str(WEB))

import bygg  # noqa: E402
from pyodide_driver import PyodideDriver  # noqa: E402


def test_bygget_har_spelet_och_startfilerna(tmp_path):
    out = bygg.build(tmp_path / "dist")
    names = set(zipfile.ZipFile(out / "k114.zip").namelist())
    assert {"start.py", "pyodide_driver.py", "sim/game.py", "ui/app.py"} <= names
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert (out / "index.html").exists() and (out / "k114.png").exists()


class FakeTerm:
    def __init__(self):
        self.out: list[str] = []
        self.closed = False

    def write(self, s: str) -> None:
        self.out.append(s)

    def exit(self) -> None:
        self.closed = True

    def text(self) -> str:
        return "".join(self.out)


@pytest.mark.slow
def test_drivrutinen_ritar_menyn_och_tar_tangenter(tmp_path):
    from ui.app import MenuScreen, SubApp

    term = FakeTerm()

    async def run():
        PyodideDriver.bridge = term
        app = SubApp(log_dir=tmp_path)
        app.driver_class = PyodideDriver
        task = asyncio.create_task(app.run_async(size=(140, 42)))
        for _ in range(100):
            await asyncio.sleep(0.05)
            if isinstance(app.screen, MenuScreen) and "Övning" in term.text():
                break
        assert isinstance(app.screen, MenuScreen)
        driver = PyodideDriver.current
        assert driver is not None
        driver.resize(100, 30)
        await asyncio.sleep(0.2)
        assert app.size == (100, 30)
        driver.feed("\x11")                  # ctrl+q
        await asyncio.wait_for(task, 5)

    asyncio.run(run())
    assert "Övning" in term.text()
    assert term.closed and PyodideDriver.current is None


@pytest.mark.slow
def test_uppvarmningen_i_bitar_ger_samma_spel():
    def game():
        return Game(build_scenario("ovning-kort", random.Random(5)), seed=5, warm_up=False)

    a, b = game(), game()
    a.warm_up()
    steps = list(b.warm_up_steps(every=30))
    assert len(steps) > 1 and not b.warmup_pending
    assert a.now == b.now
    assert a.status() == b.status()
