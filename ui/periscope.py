"""Periskopbilden i helskärm (Tab eller "periskopbild"). Spelet går vidare medan den visas.

Vyn visar utkikens senaste svep (`Knowledge.periscope`), inte världen. Den
uppdateras bara när periskopet varit uppe; en gammal bild ritas nedtonad.
← → byter föremål i okularet.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Static

from sim.reports import Report

from .periscope_render import (default_index, header, object_key, ordered_objects,
                               render_periscope)
from .widgets import ROLE_STYLE

REDRAW_S = 0.5
TICKER_LINES = 2


class PeriscopeScreen(Screen):
    CSS = """
    PeriscopeScreen { background: #0b0f0c; }
    #periscope-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #periscope-body { height: 1fr; }
    #periscope-ticker { height: 2; background: #0f1611; }
    """
    BINDINGS = [
        Binding("escape", "close", "Tillbaka"),
        Binding("left", "select(-1)", "Föregående"),
        Binding("right", "select(1)", "Nästa"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.selected_key: str | None = None
        self._pic_t: int | None = None
        self.ticker: list[Text] = []

    def compose(self) -> ComposeResult:
        yield Static(id="periscope-head")
        yield Static(id="periscope-body")
        yield Static(id="periscope-ticker")

    def on_mount(self) -> None:
        self.draw()
        self.set_interval(REDRAW_S, self.draw)

    def action_close(self) -> None:
        self.app.pop_screen()

    def action_select(self, step: int) -> None:
        pic = self._picture()
        if pic is None or not pic.objects:
            return
        objs = ordered_objects(pic)
        i = (self._index(pic) + step) % len(objs)
        self.selected_key = object_key(objs[i])
        self.draw()

    def _picture(self):
        game = getattr(self.app, "game", None)
        return None if game is None else game.knowledge.periscope

    def _index(self, pic) -> int:
        """Behåll valet mellan svepen om föremålet finns kvar, annars det närmaste fartyget."""
        objs = ordered_objects(pic)
        if self._pic_t != pic.t:
            self._pic_t = pic.t
            if self.selected_key not in {object_key(o) for o in objs}:
                self.selected_key = None
        for i, o in enumerate(objs):
            if object_key(o) == self.selected_key:
                return i
        i = default_index(pic)
        if objs:
            self.selected_key = object_key(objs[i])
        return i

    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#periscope-body", Static)
            head = self.query_one("#periscope-head", Static)
        except NoMatches:
            return
        w, h = body.size.width, body.size.height
        if w < 30 or h < 8:
            return
        pic = game.knowledge.periscope
        age = 0 if pic is None else game.now - pic.t
        index = None if pic is None else self._index(pic)
        body.update(Text("\n").join(render_periscope(pic, w, h, index, age)))
        t = header(pic, game.clock_str(pic.t) if pic else "", age)
        t.append("\n")
        t.append(" ←/→ byt föremål · periskop tar en ny bild på periskopdjup · "
                 "Tab logg · Esc tillbaka", style="dim")
        head.update(t)

    def add_report(self, clock: str, report: Report) -> None:
        line = Text(f" {clock[:5]} ", style="dim")
        line.append(f"{report.speaker}: " if report.speaker else "",
                    style=ROLE_STYLE.get(report.role, "bold"))
        line.append(report.text or "", style="bold red" if report.alarm else "")
        self.ticker = (self.ticker + [line])[-TICKER_LINES:]
        try:
            self.query_one("#periscope-ticker", Static).update(Text("\n").join(self.ticker))
        except NoMatches:
            pass
