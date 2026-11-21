"""Start i webbläsaren (Pyodide). Sidan (`index.html`) packar upp spelet, sätter
`sys.path` och anropar `main` med terminalens storlek; tangenter går till `feed`."""
from __future__ import annotations

import asyncio.tasks
import os

os.environ.setdefault("COLORTERM", "truecolor")
os.environ.setdefault("TERM", "xterm-256color")
os.environ["TEXTUAL_DRIVER"] = "pyodide_driver:PyodideDriver"   # före Textual importeras

# Pyodide 0.29:s WebLoop.create_task(name=...) anropar asyncio.tasks._set_task_name, som
# Python 3.13 tagit bort; Textual namnger sina uppgifter.
if not hasattr(asyncio.tasks, "_set_task_name"):
    def _set_task_name(task, name):
        if name is not None:
            task.set_name(name)
    asyncio.tasks._set_task_name = _set_task_name

from pyodide_driver import PyodideDriver  # noqa: E402

LOG_DIR = "/home/pyodide/logs"      # sanningsloggen i minnet (försvinner när sidan laddas om)


async def main(bridge, cols: int, rows: int, seed: int | None = None,
               scenario: str | None = None) -> None:
    from ui.app import SubApp

    PyodideDriver.bridge = bridge
    app = SubApp(seed=seed, scenario=scenario or None, sound=False, log_dir=LOG_DIR)
    await app.run_async(size=(cols, rows))


def feed(data: str) -> None:
    if PyodideDriver.current is not None:
        PyodideDriver.current.feed(data)


def resize(cols: int, rows: int) -> None:
    if PyodideDriver.current is not None:
        PyodideDriver.current.resize(cols, rows)
