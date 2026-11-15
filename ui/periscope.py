"""Periskopbilden i helskärm (Tab eller "periskopbild"). Spelet går vidare medan den visas.

Vyn visar utkikens senaste svep (`Knowledge.periscope`), inte världen. Den
uppdateras bara när periskopet varit uppe; en gammal bild ritas nedtonad.
← → byter föremål i okularet.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .periscope_render import (default_index, header, object_key, ordered_objects,
                               render_periscope)
from .viewbase import ViewScreen

REDRAW_S = 0.5


class PeriscopeScreen(ViewScreen):
    CSS = """
    PeriscopeScreen { background: #0b0f0c; }
    #periscope-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #periscope-body { height: 1fr; }
    #periscope-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "periscope"
    REDRAW_S = REDRAW_S
    EMPTY_KEYS = {"escape": "close", "left": "select(-1)", "right": "select(1)"}

    def __init__(self) -> None:
        super().__init__()
        self.selected_key: str | None = None
        self._pic_t: int | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="periscope-head")
        yield Static(id="periscope-body")
        yield Static(id="periscope-ticker")
        yield self.order_line()

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
            fresh = {object_key(o) for o in objs if not (0 <= o.seen_t < pic.t)}
            if self.selected_key not in fresh:
                self.selected_key = None        # nytt svep: välj bland det vi just såg
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
        body.update(Text("\n").join(render_periscope(pic, w, h, index, age, game.clock_str)))
        note = None
        blocked = game.knowledge.periscope_blocked
        if blocked is not None and (pic is None or blocked[0] > pic.t):
            note = f"Is ovanför kl {game.clock_str(blocked[0])[:5]}, masten kom inte upp."
        t = header(pic, game.clock_str(pic.t) if pic else "", age, note)
        t.append("\n")
        t.append(" ←/→ byt föremål · periskop ger ett svep, periskop 047 eller S-3 en kort titt · "
                 "Tab logg · Esc tillbaka", style="dim")
        head.update(t)

