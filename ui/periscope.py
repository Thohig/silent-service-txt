"""Periskopbilden i helskärm (Tab eller "periskopbild"). Spelet går vidare medan den visas.

Vyn visar utkikens bild (`Knowledge.periscope`), inte världen. Medan masten är uppe
kommer en ny bild varannan sekund och okularet står där periskopet är vänt
(`StatusSnapshot.periscope_train`): ← → vrider det (`vrid periskop …`, tar över ett svep),
mellanslag vänder det förut, ↓ fäller det. När masten är nere visas den senaste bilden
(nedtonad när den är gammal), ← → byter föremål i okularet och ↑ hissar periskopet.
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
TURN_STEP_DEG = 5


class PeriscopeScreen(ViewScreen):
    CSS = """
    PeriscopeScreen { background: #0b0f0c; }
    #periscope-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #periscope-body { height: 1fr; }
    #periscope-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "periscope"
    REDRAW_S = REDRAW_S
    EMPTY_KEYS = {"escape": "close", "left": "select(-1)", "right": "select(1)",
                  "up": "raise", "down": "lower", "space": "ahead"}

    def __init__(self) -> None:
        super().__init__()
        self.selected_key: str | None = None
        self._pic_t: int | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="periscope-head")
        yield Static(id="periscope-body")
        yield Static(id="periscope-ticker")
        yield self.order_line()

    def _game(self):
        return getattr(self.app, "game", None)

    def _hand(self, text: str) -> None:
        """Kaptenens hand på periskopet: en order utan rad i loggen."""
        game = self._game()
        if game is not None:
            game.command(text)
            self.draw()

    def action_raise(self) -> None:
        game = self._game()
        if game is not None and game.status().periscope != "hold":
            self._hand("periskop upp")

    def action_lower(self) -> None:
        game = self._game()
        if game is not None and game.status().periscope is not None:
            self._hand("periskop ned")

    def action_ahead(self) -> None:
        game = self._game()
        if game is not None and game.status().periscope is not None:
            self._hand(f"vrid periskop {round(game.status().course) % 360:03d}")

    def action_select(self, step: int) -> None:
        game = self._game()
        if game is not None and (st := game.status()).periscope is not None:
            b = (round(st.periscope_train / TURN_STEP_DEG) + step) * TURN_STEP_DEG % 360
            self._hand(f"vrid periskop {b:03d}")
            return
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
        st = game.status()
        aim = st.periscope_train if st.periscope is not None else None
        age = 0 if pic is None else game.now - pic.t
        index = None if pic is None or aim is not None else self._index(pic)
        body.update(Text("\n").join(render_periscope(pic, w, h, index, age, game.clock_str, aim)))
        note = None
        blocked = game.knowledge.periscope_blocked
        if blocked is not None and (pic is None or blocked[0] > pic.t):
            note = f"Is ovanför kl {game.clock_str(blocked[0])[:5]}, masten kom inte upp."
        up = None if aim is None else (st.periscope, st.periscope_up_s, aim)
        t = header(pic, game.clock_str(pic.t) if pic else "", age, note, up)
        t.append("\n")
        if aim is not None:
            t.append(" ←/→ vrid · mellanslag förut · ↓ periskop ned · Tab logg · Esc tillbaka",
                     style="dim")
        else:
            t.append(" ←/→ byt föremål · ↑ periskop upp · periskop ger ett svep, periskop 047 "
                     "eller S-3 en kort titt · Tab logg · Esc tillbaka", style="dim")
        head.update(t)

