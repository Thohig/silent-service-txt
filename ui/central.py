"""Centralen (центральный пост) i helskärm (Tab eller "central"): rummet och instrumenten på hela
skärmen, bara egna instrument (ui/central_render.py). Visarna ritas tio gånger i sekunden och följer
instrumenten med tröghet. Spelet går vidare medan den visas."""
from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .central_instruments import Needles
from .central_render import render_central
from .viewbase import ViewScreen

CENTRAL_EVERY_S = 0.1               # visarna: tio gånger i sekunden


class CentralScreen(ViewScreen):
    CSS = """
    CentralScreen { background: #0b0f0c; }
    #central-body { height: 1fr; }
    #central-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "central"
    REDRAW_S = CENTRAL_EVERY_S

    def __init__(self) -> None:
        super().__init__()
        self.needles = Needles()

    def compose(self) -> ComposeResult:
        yield Static(id="central-body")
        yield Static(id="central-ticker")
        yield self.order_line()

    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#central-body", Static)
        except NoMatches:
            return
        w, h = body.content_size.width, body.content_size.height
        if w < 10 or h < 5:
            return
        now = time.monotonic()
        status = game.status()
        spoke = getattr(self.app, "_spoke", {})
        speaking = {role: now - t for role, t in spoke.items()}
        shown = self.needles.update(status, now)
        body.update(Text("\n").join(render_central(status, speaking, now, w, h, shown)))
