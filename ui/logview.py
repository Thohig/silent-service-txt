"""Hela loggboken i helskärm (Tab eller "logg" när centralen är huvudvyn, "telegram" alltid).

Loggen i huvudvyn är då bara en remsa; här visas allt den skrivit, och nya rader
speglas hit medan vyn är öppen. Mellanslag (tom orderrad) växlar till bara telegrammen:
ordern, stabens radiogram och Radio Moskva (`TelegramStrip`). Spelet går vidare under tiden.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .menutext import DIM
from .placards import view_title
from .strips import TelegramStrip
from .viewbase import ViewScreen
from .widgets import ReportLog

NO_TELEGRAMS = ("Inget mottaget än. Staben sänder vid sambandstillfällena (antenndjup); "
                "Radio Moskva hörs med lyssna radio.")


class FilteredLog(ReportLog):
    """Loggvyns kopia: med `only_telegrams` skrivs bara remsorna."""

    only_telegrams = False

    def emit(self, content) -> None:
        if self.only_telegrams and not isinstance(content, TelegramStrip):
            return
        super().emit(content)


class LogScreen(ViewScreen):
    CSS = """
    LogScreen { background: #0b0f0c; }
    #logview-head { height: 1; background: #1c2a20; color: #c8d0b0; }
    #logview-log { height: 1fr; padding: 0 1; background: #0b0f0c; scrollbar-size-vertical: 1; }
    """
    PREFIX = "logview"
    EMPTY_KEYS = {"escape": "close", "space": "toggle_telegrams"}

    def __init__(self, telegrams: bool = False) -> None:
        super().__init__()
        self.only_telegrams = telegrams
        self._strips = 0

    def compose(self) -> ComposeResult:
        yield Static(id="logview-head")
        yield FilteredLog(id="logview-log", wrap=True, markup=False, max_lines=2000)
        yield self.order_line()

    def on_mount(self) -> None:          # ViewScreen.on_mount körs också (Textual går genom MRO)
        self.call_after_refresh(self._fill)  # när storleken är känd: remsorna bryts efter bredden
        try:
            self.app.gs().query_one("#log", ReportLog).mirror = self.query_one("#logview-log",
                                                                                FilteredLog)
        except NoMatches:
            pass

    def on_unmount(self) -> None:
        try:
            self.app.gs().query_one("#log", ReportLog).mirror = None
        except NoMatches:
            pass

    def _fill(self) -> None:
        """Skriv om vyn ur huvudloggen, med eller utan filtret."""
        try:
            main = self.app.gs().query_one("#log", ReportLog)
            log = self.query_one("#logview-log", FilteredLog)
        except NoMatches:
            return
        log.clear()
        log.entries = []
        log.only_telegrams = self.only_telegrams
        for entry in main.entries:
            log.emit(entry)
        self._strips = sum(isinstance(e, TelegramStrip) for e in main.entries)
        if self.only_telegrams and not self._strips:
            log.write(Text(NO_TELEGRAMS, style=f"italic {DIM}"))
        self.draw()

    def draw(self) -> None:
        """Rubriken; och tomt filter som fått sin första remsa skrivs om."""
        try:
            main = self.app.gs().query_one("#log", ReportLog)
            head = self.query_one("#logview-head", Static)
        except NoMatches:
            return
        n = sum(isinstance(e, TelegramStrip) for e in main.entries)
        if self.only_telegrams and n and not self._strips:
            self._fill()
            return
        self._strips = n
        t = view_title("LOGGBOKEN")
        if self.only_telegrams:
            t.append(f"  bara telegram ({n})", style="bold")
            t.append("   mellanslag hela loggen", style="dim")
        else:
            t.append("   mellanslag bara telegram", style="dim")
        t.append("   Tab vidare · Esc tillbaka", style="dim")
        head.update(t)

    def set_telegrams(self, on: bool) -> None:
        self.only_telegrams = on
        self._fill()

    def action_toggle_telegrams(self) -> None:
        self.set_telegrams(not self.only_telegrams)

    # loggen speglas från huvudvyn, så rapporterna behöver ingen egen rad här
    def add_report(self, clock, report) -> None:
        pass

    def add_captain(self, clock, text) -> None:
        pass
