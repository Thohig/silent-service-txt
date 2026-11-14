"""Huvudfönstret. Simuleringen tickar i realtid oberoende av inmatningen."""
from __future__ import annotations

import random
import time
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input

from sim.events import ReportDelivered, TimeScaleChanged
from sim.game import Game
from sim.scenario import default_scenario
from sim.truthlog import TruthLog

from .teletype import Teletype
from .widgets import ReportLog, StatusBar

MAX_TICKS_PER_FRAME = 20
FRAME_S = 0.05


class SubApp(App):
    TITLE = "K-114"
    CSS = """
    Screen { background: #0b0f0c; }
    #status { height: 1; background: #1c2a20; color: #c8d0b0; }
    #intro  { height: 1fr; padding: 2 6; }
    #log    { height: 1fr; padding: 0 1; background: #0b0f0c; scrollbar-size-vertical: 1; }
    #order  { border: tall #2f4a36; background: #0f1611; }
    #order:focus { border: tall #5f8a66; }
    """
    BINDINGS = [Binding("ctrl+q", "quit", "Avsluta", priority=True)]

    def __init__(self, seed: int | None = None, log_dir: Path | str = "logs"):
        super().__init__()
        seed = seed if seed is not None else random.randrange(1_000_000)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.truth_log = TruthLog(Path(log_dir) / f"truth-{stamp}.log")
        self.truth_log.write(f"# seed={seed}")
        self.game = Game(default_scenario(random.Random(seed)), seed=seed,
                         truth_log=self.truth_log)
        self.running = False
        self._acc = 0.0
        self._last = 0.0

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status")
        yield Teletype(self.game.secret_order, id="intro")
        yield ReportLog(id="log", wrap=True, markup=False, max_lines=2000)
        yield Input(placeholder="Order …   (skriv hjälp för en lista)", id="order")

    def on_mount(self) -> None:
        self.query_one("#log").display = False
        self.query_one(StatusBar).show(self.game.status())
        self.game.bus.subscribe(ReportDelivered, self._on_report)
        self.game.bus.subscribe(TimeScaleChanged, self._on_time_scale)
        self.query_one("#order", Input).focus()
        self.query_one(Teletype).start()

    def on_teletype_finished(self, _: Teletype.Finished) -> None:
        self.query_one(Teletype).set_footer("Tryck Enter för att ta befälet.")

    # ------------------------------------------------------------------ order
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not self.running:
            tt = self.query_one(Teletype)
            if not tt.done:
                tt.finish()
            else:
                self._start()
            return
        if not text:
            return
        self.query_one(ReportLog).add_captain(self.game.clock_str(), text)
        self.game.command(text)

    def _start(self) -> None:
        self.query_one(Teletype).display = False
        log = self.query_one(ReportLog)
        log.display = True
        log.add_system(self.game.clock_str(),
                       "Du har befälet. Ubåten går kurs 000, fart 5 knop, djup 100 meter.")
        log.add_system(self.game.clock_str(), "Skriv hjälp för en lista över order.")
        self.running = True
        self._last = time.monotonic()
        self.set_interval(FRAME_S, self._pump)

    # ------------------------------------------------------------------ realtid
    def _pump(self) -> None:
        now = time.monotonic()
        self._acc += (now - self._last) * self.game.time_scale
        self._last = now
        n = 0
        while self._acc >= 1.0 and n < MAX_TICKS_PER_FRAME:
            scale_before = self.game.time_scale
            self.game.tick()
            self._acc -= 1.0
            n += 1
            if self.game.time_scale < scale_before:
                self._acc = 0.0      # larm: släpp resterande komprimerad tid
                break
        self._acc = min(self._acc, 2.0)
        self.query_one(StatusBar).show(self.game.status())

    # ------------------------------------------------------------------ händelser
    def _on_report(self, e: ReportDelivered) -> None:
        self.query_one(ReportLog).add_report(self.game.clock_str(), e.report)

    def _on_time_scale(self, e: TimeScaleChanged) -> None:
        log = self.query_one(ReportLog)
        if e.reason == "larm":
            log.add_system(self.game.clock_str(), "Tidskomprimering avbruten – 1×.", "bold red")
        else:
            log.add_system(self.game.clock_str(), f"Tidskomprimering {e.scale}×.")
        self.query_one(StatusBar).show(self.game.status())

    def on_unmount(self) -> None:
        self.truth_log.close()
