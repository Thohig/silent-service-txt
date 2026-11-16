"""Vyn Hytten ("hytt"): kaptenens hytt medan starpom har befälet.

Visas av sig själv när kaptenen lämnar över och stängs när han är framme i centralen.
Härifrån syns inga kontakter: rapportraden visar bara starpom och telefonen. Enter på
en tom orderrad svarar i telefonen när den ringer.
"""
from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from sim.reports import Report

from .cabin_render import footer, render_cabin
from .placards import view_title
from .viewbase import ViewScreen

REDRAW_S = 0.25
SEEN_ROLES = {"starpom", ""}    # rapporter som når hytten: starpom, telefonen, ordonnansen


class CabinScreen(ViewScreen):
    CSS = """
    CabinScreen { background: #15110c; }
    #cabin-head { height: 1; background: #2a2218; color: #d8c89a; }
    #cabin-body { height: 1fr; }
    #cabin-foot { height: 1; background: #1e1810; }
    #cabin-ticker { height: 2; background: #1a140e; }
    """
    PREFIX = "cabin"
    REDRAW_S = REDRAW_S
    EMPTY_KEYS = {"escape": "close", "enter": "answer"}

    def compose(self) -> ComposeResult:
        yield Static(id="cabin-head")
        yield Static(id="cabin-body")
        yield Static(id="cabin-foot")
        yield Static(id="cabin-ticker")
        yield self.order_line()

    def action_answer(self) -> None:
        game = getattr(self.app, "game", None)
        if game is not None and game.status().phone == "ring":
            self.app.captain_says("svara")

    def add_report(self, clock: str, report: Report) -> None:
        if report.role in SEEN_ROLES:
            super().add_report(clock, report)

    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#cabin-body", Static)
            head = self.query_one("#cabin-head", Static)
            foot = self.query_one("#cabin-foot", Static)
        except NoMatches:
            return
        w, h = body.content_size.width, body.content_size.height
        if w < 20 or h < 6:
            return
        s = game.status()
        body.update(Text("\n").join(render_cabin(s, time.monotonic(), w, h)))
        head.update(view_title("KAPTENENS HYTT", "   lägesrapport · svara · sov · "
                                                 "jag har befälet · Esc centralen"))
        foot.update(footer(s))
