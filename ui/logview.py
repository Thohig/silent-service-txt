"""Hela loggboken i helskärm (Tab eller "logg") när centralen är huvudvyn.

Loggen i huvudvyn är då bara en remsa; här visas allt den skrivit, och nya rader
speglas hit medan vyn är öppen. Spelet går vidare under tiden.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .placards import view_title
from .viewbase import ViewScreen
from .widgets import ReportLog


class LogScreen(ViewScreen):
    CSS = """
    LogScreen { background: #0b0f0c; }
    #logview-head { height: 1; background: #1c2a20; color: #c8d0b0; }
    #logview-log { height: 1fr; padding: 0 1; background: #0b0f0c; scrollbar-size-vertical: 1; }
    """
    PREFIX = "logview"

    def compose(self) -> ComposeResult:
        head = view_title("LOGGBOKEN")
        head.append("   Tab sjökort · Esc centralen", style="dim")
        yield Static(head, id="logview-head")
        yield ReportLog(id="logview-log", wrap=True, markup=False, max_lines=2000)
        yield self.order_line()

    def on_mount(self) -> None:          # ViewScreen.on_mount körs också (Textual går genom MRO)
        try:
            main = self.app.gs().query_one("#log", ReportLog)
            log = self.query_one("#logview-log", ReportLog)
        except NoMatches:
            return
        for entry in main.entries:
            log.emit(entry)
        main.mirror = log

    def on_unmount(self) -> None:
        try:
            self.app.gs().query_one("#log", ReportLog).mirror = None
        except NoMatches:
            pass

    # loggen speglas från huvudvyn, så rapporterna behöver ingen egen rad här
    def add_report(self, clock, report) -> None:
        pass

    def add_captain(self, clock, text) -> None:
        pass
