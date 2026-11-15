"""Systemtavlan i helskärm (Tab eller "system"). Spelet går vidare medan den visas."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .systems_render import header, legend, render_systems
from .viewbase import ViewScreen

REDRAW_S = 0.5


class SystemScreen(ViewScreen):
    CSS = """
    SystemScreen { background: #0b0f0c; }
    #systems-head { height: 1; background: #1c2a20; color: #c8d0b0; }
    #systems-body { height: 1fr; padding: 1 1 0 1; }
    #systems-legend { height: 1; color: #7f9a80; }
    #systems-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "systems"
    REDRAW_S = REDRAW_S

    def compose(self) -> ComposeResult:
        yield Static(id="systems-head")
        yield Static(id="systems-body")
        yield Static(legend(), id="systems-legend")
        yield Static(id="systems-ticker")
        yield self.order_line()

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
        t.append("   Tab periskop · Esc tillbaka", style="dim")
        head.update(t)

