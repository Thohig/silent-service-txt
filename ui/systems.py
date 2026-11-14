"""Systemtavlan i helskärm (Tab eller "system"). Spelet går vidare medan den visas."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Static

from sim.reports import Report

from .systems_render import header, legend, render_systems
from .widgets import ROLE_STYLE

REDRAW_S = 0.5
TICKER_LINES = 2


class SystemScreen(Screen):
    CSS = """
    SystemScreen { background: #0b0f0c; }
    #systems-head { height: 1; background: #1c2a20; color: #c8d0b0; }
    #systems-body { height: 1fr; padding: 1 1 0 1; }
    #systems-legend { height: 1; color: #7f9a80; }
    #systems-ticker { height: 2; background: #0f1611; }
    """
    BINDINGS = [Binding("escape", "close", "Tillbaka")]

    def __init__(self) -> None:
        super().__init__()
        self.ticker: list[Text] = []

    def compose(self) -> ComposeResult:
        yield Static(id="systems-head")
        yield Static(id="systems-body")
        yield Static(legend(), id="systems-legend")
        yield Static(id="systems-ticker")

    def on_mount(self) -> None:
        self.draw()
        self.set_interval(REDRAW_S, self.draw)

    def action_close(self) -> None:
        self.app.pop_screen()

    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#systems-body", Static)
            head = self.query_one("#systems-head", Static)
        except NoMatches:
            return
        w = body.size.width
        if w < 30:
            return
        view = game.systems()
        body.update(Text("\n").join(render_systems(view, w)))
        t = header(view)
        t.append("   Tab loggen · Esc tillbaka", style="dim")
        head.update(t)

    def add_report(self, clock: str, report: Report) -> None:
        line = Text(f" {clock[:5]} ", style="dim")
        line.append(f"{report.speaker}: " if report.speaker else "",
                    style=ROLE_STYLE.get(report.role, "bold"))
        line.append(report.text or "", style="bold red" if report.alarm else "")
        self.ticker = (self.ticker + [line])[-TICKER_LINES:]
        try:
            self.query_one("#systems-ticker", Static).update(Text("\n").join(self.ticker))
        except NoMatches:
            pass
