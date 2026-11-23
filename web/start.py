"""Start i webbläsaren (Pyodide). Sidan (`index.html`) packar upp spelet, sätter
`sys.path` och anropar `main` med terminalens storlek; tangenter går till `feed`.
Sidans ljud (`bridge.audio`, en AudioWorklet) blir `web_audio.WebOut.sink` och dess talsyntes
(`bridge.speech`) `ui.voices.WebSpeech.bridge`."""
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


class JsAudio:
    """Sidans ljudbrygga som `WebOut` vill ha den: numpy in, Float32Array ut."""

    def __init__(self, audio):
        self.js = audio
        self.rate = int(audio.rate)

    def time(self) -> float:
        return float(self.js.time())

    def push(self, x) -> None:
        import js
        flat = x.reshape(-1)                        # sammanflätat: v, h, v, h …
        buf = js.Float32Array.new(len(flat))
        buf.assign(flat)
        self.js.push(buf)

    def clear(self) -> None:
        self.js.clear()


async def main(bridge, cols: int, rows: int, seed: int | None = None,
               scenario: str | None = None) -> None:
    from ui.app import SubApp

    from web_audio import WebOut

    PyodideDriver.bridge = bridge
    audio = getattr(bridge, "audio", None)
    WebOut.sink = JsAudio(audio) if audio is not None else None
    import ui.ambience
    ui.ambience.OUTPUT = WebOut
    from ui.voices import WebSpeech
    WebSpeech.bridge = getattr(bridge, "speech", None)
    app = SubApp(seed=seed, scenario=scenario or None, sound=True, log_dir=LOG_DIR)
    await app.run_async(size=(cols, rows))


def feed(data: str) -> None:
    if PyodideDriver.current is not None:
        PyodideDriver.current.feed(data)


def resize(cols: int, rows: int) -> None:
    if PyodideDriver.current is not None:
        PyodideDriver.current.resize(cols, rows)
