"""Översikten (Tab eller "översikt"): sjökortet, vattenfallet, djupprofilen, kontakttabellen,
uppdraget och systemtavlan på en skärm (ui/overview_render.py). Spelet går vidare medan den visas."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .overview_render import header, render_overview
from .viewbase import ViewScreen

REDRAW_S = 0.5


class OverviewScreen(ViewScreen):
    CSS = """
    OverviewScreen { background: #0b0f0c; }
    #overview-head { height: 1; background: #1c2a20; color: #c8d0b0; }
    #overview-body { height: 1fr; padding: 0 1; }
    #overview-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "overview"
    REDRAW_S = REDRAW_S

    def compose(self) -> ComposeResult:
        yield Static(id="overview-head")
        yield Static(id="overview-body")
        yield Static(id="overview-ticker")
        yield self.order_line()

    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#overview-body", Static)
            head = self.query_one("#overview-head", Static)
        except NoMatches:
            return
        w, h = body.content_size.width, body.content_size.height
        if w < 40 or h < 10:
            return
        ov = game.overview()
        rows = render_overview(ov, game.chart(), game.sonar(), game.profile(), game.systems(), w, h)
        body.update(Text("\n").join(rows))
        t = header(ov)
        t.append("   Tab vidare · Esc tillbaka", style="dim")
        head.update(t)
