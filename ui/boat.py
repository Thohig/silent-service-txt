"""Vyn Ubåten (Tab, "ubåt", "profil" eller "system"): genomskärningen, djupprofilen och
systemtavlans paneler. Spelet går vidare medan den visas."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .boat_render import header, lamps, legend, render_boat
from .profile_render import DEPTH_ZOOM, TIME_ZOOM, auto_depth_zoom, auto_time_zoom
from .viewbase import ViewScreen

REDRAW_S = 0.25


class BoatScreen(ViewScreen):
    CSS = """
    BoatScreen { background: #0b0f0c; }
    #boat-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #boat-body { height: 1fr; padding: 0 1; }
    #boat-legend { height: auto; max-height: 5; color: #7f9a80; }
    #boat-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "boat"
    REDRAW_S = REDRAW_S
    EMPTY_KEYS = {"escape": "close", "plus": "depth(-1)", "equals_sign": "depth(-1)",
                  "minus": "depth(1)", "left": "time(1)", "right": "time(-1)", "space": "auto"}

    def __init__(self) -> None:
        super().__init__()
        self.depth_zoom: int | None = None          # None: automatisk efter vårt djup
        self.time_zoom: int | None = None           # None: automatisk efter historiken
        self.profile_w = 80                         # profilens bredd vid senaste ritningen

    def compose(self) -> ComposeResult:
        yield Static(id="boat-head")
        yield Static(id="boat-body")
        yield Static(legend(), id="boat-legend")
        yield Static(id="boat-ticker")
        yield self.order_line()

    # --- tangenter ----------------------------------------------------------------
    def action_depth(self, step: int) -> None:
        cur = self.depth_zoom if self.depth_zoom is not None else self._auto()
        self.depth_zoom = min(max(cur + step, 0), len(DEPTH_ZOOM) - 1)
        self.draw()

    def action_time(self, step: int) -> None:
        cur = self.time_zoom if self.time_zoom is not None else \
            auto_time_zoom(self.app.game.profile(), self.profile_w)
        self.time_zoom = min(max(cur + step, 0), len(TIME_ZOOM) - 1)
        self.draw()

    def action_auto(self) -> None:
        self.depth_zoom = None
        self.time_zoom = None
        self.draw()

    def _auto(self) -> int:
        view = self.app.game.profile()
        tz = self.time_zoom if self.time_zoom is not None else auto_time_zoom(view, self.profile_w)
        span = max(10, self.profile_w) * TIME_ZOOM[tz]
        return auto_depth_zoom(view, view.now - span)

    # --- ritning --------------------------------------------------------------------
    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#boat-body", Static)
            head = self.query_one("#boat-head", Static)
        except NoMatches:
            return
        w, h = body.content_size.width, body.content_size.height
        if w < 30 or h < 8:
            return
        pv, sv = game.profile(), game.systems()
        spc = TIME_ZOOM[self.time_zoom] if self.time_zoom is not None else None
        max_depth = DEPTH_ZOOM[self.depth_zoom] if self.depth_zoom is not None else None
        rows, lay = render_boat(pv, sv, w, h, spc, max_depth)
        spc = lay.sec_per_col
        self.profile_w = lay.profile_w
        body.update(Text("\n").join(rows))
        try:
            leg = self.query_one("#boat-legend", Static)
            leg.update(legend(leg.size.width or self.size.width))
        except NoMatches:
            pass
        t = header(pv, sv)
        t.append("\n")
        t.append(lamps(sv, lay))
        t.append(f" 1 tecken = {spc} s" + (" (automatiskt)" if self.time_zoom is None else "")
                 + " · djup "
                 + ("automatiskt" if self.depth_zoom is None
                    else f"till {DEPTH_ZOOM[self.depth_zoom]} m"), style="dim")
        t.append("   +/− djup · ←/→ tid · mellanslag automatiskt · Tab vidare · Esc tillbaka",
                 style="dim")
        head.update(t)
