"""Huvudfönstret. Simuleringen tickar i realtid oberoende av inmatningen."""
from __future__ import annotations

import random
import time
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from sim.events import GameEnded, ReportDelivered, TimeScaleChanged
from sim.game import Game
from sim.fmt import fmt_course, kn
from sim.scenario import SCENARIOS, build_scenario
from sim.truthlog import TruthLog

from .chart import ChartScreen
from .teletype import Teletype
from .widgets import ReportLog, StatusBar

MAX_TICKS_PER_FRAME = 20
CHART_WORDS = {"sjökort", "sjokort", "kort", "karta"}
CHART_KEY = "§"


class OrderInput(Input):
    """Orderraden. Släpper sjökortstangenten vidare till appens bindning
    (Textual tar annars bort bindningar för tecken som fältet kan skriva)."""

    def check_consume_key(self, key: str, character: str | None) -> bool:
        return character != CHART_KEY and super().check_consume_key(key, character)
FRAME_S = 0.05


class SubApp(App):
    TITLE = "K-114"
    CSS = """
    Screen { background: #0b0f0c; }
    #status { height: 2; background: #1c2a20; color: #c8d0b0; }
    #intro  { height: 1fr; padding: 2 6; }
    #picker { height: 1fr; padding: 2 6; }
    #picker-title { color: #c8d0b0; text-style: bold; margin-bottom: 1; }
    #scenarios { background: #0b0f0c; border: none; color: #c8d0b0; }
    #log    { height: 1fr; padding: 0 1; background: #0b0f0c; scrollbar-size-vertical: 1; }
    #order  { border: tall #2f4a36; background: #0f1611; }
    #order:focus { border: tall #5f8a66; }
    """
    BINDINGS = [Binding("ctrl+q", "quit", "Avsluta", priority=True),
                Binding("section_sign", "chart", "Sjökort", priority=True)]

    def __init__(self, seed: int | None = None, log_dir: Path | str = "logs",
                 scenario: str | None = None):
        """scenario: nyckel i SCENARIOS. Utan scenario börjar spelet med en väljare."""
        super().__init__()
        self.seed = seed if seed is not None else random.randrange(1_000_000)
        self.log_dir = Path(log_dir)
        self.game: Game | None = None
        self.truth_log: TruthLog | None = None
        self.running = False
        self._acc = 0.0
        self._last = 0.0
        if scenario is not None:
            self._create_game(scenario)

    def _create_game(self, key: str) -> None:
        scenario = build_scenario(key, random.Random(self.seed))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.truth_log = TruthLog(self.log_dir / f"truth-{stamp}.log")
        self.truth_log.write(f"# seed={self.seed} scenario={key}")
        self.game = Game(scenario, seed=self.seed, truth_log=self.truth_log)

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status")
        with Vertical(id="picker"):
            yield Static("K-114 — välj scenario", id="picker-title")
            yield OptionList(*[Option(_scenario_label(sd), id=sd.key)
                               for sd in SCENARIOS.values()], id="scenarios")
        yield Teletype("", id="intro")
        yield ReportLog(id="log", wrap=True, markup=False, max_lines=2000)
        yield OrderInput(placeholder="Order …   (skriv hjälp för en lista)", id="order")

    def on_mount(self) -> None:
        self.query_one("#log").display = False
        if self.game is None:
            self.query_one("#intro").display = False
            self.query_one("#order").display = False
            self.query_one("#scenarios", OptionList).focus()
        else:
            self._begin()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if self.game is not None or event.option.id is None:
            return
        self._create_game(event.option.id)
        self._begin()

    def _begin(self) -> None:
        """Scenariot är valt: visa den hemliga ordern på fjärrskrivaren."""
        game = self.game
        self.query_one("#picker").display = False
        self.query_one("#intro").display = True
        self.query_one("#order").display = True
        self.query_one(StatusBar).show(game.status())
        game.bus.subscribe(ReportDelivered, self._on_report)
        game.bus.subscribe(TimeScaleChanged, self._on_time_scale)
        game.bus.subscribe(GameEnded, self._on_game_ended)
        self.query_one("#order", Input).focus()
        tt = self.query_one(Teletype)
        tt.full_text = game.secret_order
        tt.start()

    def on_teletype_finished(self, _: Teletype.Finished) -> None:
        self.query_one(Teletype).set_footer("Tryck Enter för att ta befälet.")

    # ------------------------------------------------------------------ order
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if self.game is None:
            return
        if not self.running:
            tt = self.query_one(Teletype)
            if not tt.done:
                tt.finish()
            else:
                self._start()
            return
        if not text:
            return
        if text.lower() in CHART_WORDS:
            self.action_chart()
            return
        self.query_one(ReportLog).add_captain(self.game.clock_str(), text)
        self.game.command(text)

    def _start(self) -> None:
        self.query_one(Teletype).display = False
        log = self.query_one(ReportLog)
        log.display = True
        st = self.game.world.own.state
        log.add_system(self.game.clock_str(),
                       f"Du har befälet. Ubåten går kurs {fmt_course(st.course)}, "
                       f"fart {kn(st.speed)} knop, djup {st.depth:.0f} meter.")
        log.add_system(self.game.clock_str(), "Skriv hjälp för en lista över order. Besättningens förslag godkänns med ja, avslås med nej.")
        log.add_system(self.game.clock_str(), f"{CHART_KEY} visar navigatörens sjökort.")
        self.running = True
        self._last = time.monotonic()
        self.set_interval(FRAME_S, self._pump)

    # ------------------------------------------------------------------ sjökort
    def action_chart(self) -> None:
        """§: visa eller stäng sjökortet. Spelet går vidare under tiden."""
        if not self.running or self.game is None:
            return
        if isinstance(self.screen, ChartScreen):
            self.pop_screen()
        else:
            self.push_screen(ChartScreen())

    # ------------------------------------------------------------------ realtid
    def _pump(self) -> None:
        if not self.is_running or self.game is None or self.game.over:
            return
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
        try:
            self.query_one(StatusBar).show(self.game.status())
        except NoMatches:
            pass

    # ------------------------------------------------------------------ händelser
    def _on_report(self, e: ReportDelivered) -> None:
        self.query_one(ReportLog).add_report(self.game.clock_str(), e.report)
        if isinstance(self.screen, ChartScreen):
            self.screen.add_report(self.game.clock_str(), e.report)

    def _on_time_scale(self, e: TimeScaleChanged) -> None:
        log = self.query_one(ReportLog)
        if e.reason == "larm":
            log.add_system(self.game.clock_str(), "Tidskomprimering avbruten – 1×.", "bold red")
        else:
            log.add_system(self.game.clock_str(), f"Tidskomprimering {e.scale}×.")
        self.query_one(StatusBar).show(self.game.status())

    def _on_game_ended(self, e: GameEnded) -> None:
        if isinstance(self.screen, ChartScreen):
            self.pop_screen()               # slutrapporten visas i loggen
        self.query_one(ReportLog).add_ending(e.summary)
        inp = self.query_one("#order", Input)
        inp.placeholder = "Spelet är slut – ctrl+q avslutar"
        inp.disabled = True
        self.query_one(StatusBar).show(self.game.status())

    def on_unmount(self) -> None:
        if self.truth_log:
            self.truth_log.close()


def _scenario_label(sd) -> Text:
    t = Text(sd.title, style="bold")
    t.append(f"  ({sd.key})\n", style="dim")
    t.append(sd.summary, style="italic")
    return t
