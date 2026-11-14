"""Djupprofilen i helskärm (° eller "profil"). Spelet går vidare medan den visas."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Static

from sim.reports import Report

from .profile_render import (DEPTH_ZOOM, DEFAULT_TIME_ZOOM, TIME_ZOOM, auto_depth_zoom,
                             header, legend, render_profile)
from .widgets import ROLE_STYLE

REDRAW_S = 0.25
TICKER_LINES = 2


class ProfileScreen(Screen):
    CSS = """
    ProfileScreen { background: #0b0f0c; }
    #profile-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #profile-body { height: 1fr; }
    #profile-legend { height: 2; color: #7f9a80; }
    #profile-ticker { height: 2; background: #0f1611; }
    """
    BINDINGS = [
        Binding("escape", "close", "Tillbaka"),
        Binding("plus,equals_sign", "depth(-1)", "Zooma in"),
        Binding("minus", "depth(1)", "Zooma ut"),
        Binding("left", "time(1)", "Längre tid"),
        Binding("right", "time(-1)", "Kortare tid"),
        Binding("a", "auto", "Automatisk skala"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.depth_zoom: int | None = None          # None: automatisk efter vårt djup
        self.time_zoom = DEFAULT_TIME_ZOOM
        self.ticker: list[Text] = []

    def compose(self) -> ComposeResult:
        yield Static(id="profile-head")
        yield Static(id="profile-body")
        yield Static(legend(), id="profile-legend")
        yield Static(id="profile-ticker")

    def on_mount(self) -> None:
        self.draw()
        self.set_interval(REDRAW_S, self.draw)

    # --- tangenter ----------------------------------------------------------------
    def action_close(self) -> None:
        self.app.pop_screen()

    def action_depth(self, step: int) -> None:
        cur = self.depth_zoom if self.depth_zoom is not None else self._auto()
        self.depth_zoom = min(max(cur + step, 0), len(DEPTH_ZOOM) - 1)
        self.draw()

    def action_time(self, step: int) -> None:
        self.time_zoom = min(max(self.time_zoom + step, 0), len(TIME_ZOOM) - 1)
        self.draw()

    def action_auto(self) -> None:
        self.depth_zoom = None
        self.draw()

    def _auto(self) -> int:
        game = self.app.game
        body = self.query_one("#profile-body", Static)
        view = game.profile()
        span = max(10, body.size.width) * TIME_ZOOM[self.time_zoom]
        return auto_depth_zoom(view, view.now - span)

    # --- ritning --------------------------------------------------------------------
    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#profile-body", Static)
            head = self.query_one("#profile-head", Static)
        except NoMatches:
            return
        w, h = body.size.width, body.size.height
        if w < 30 or h < 8:
            return
        view = game.profile()
        spc = TIME_ZOOM[self.time_zoom]
        max_depth = DEPTH_ZOOM[self.depth_zoom] if self.depth_zoom is not None else None
        body.update(Text("\n").join(render_profile(view, w, h, spc, max_depth)))
        t = header(view)
        t.append("\n")
        t.append(f" 1 tecken = {spc} s · djup "
                 + ("automatiskt" if self.depth_zoom is None
                    else f"till {DEPTH_ZOOM[self.depth_zoom]} m"), style="dim")
        t.append("   +/− djup · ←/→ tid · a automatiskt · § sjökortet · Tab/Esc tillbaka",
                 style="dim")
        head.update(t)

    def add_report(self, clock: str, report: Report) -> None:
        line = Text(f" {clock[:5]} ", style="dim")
        line.append(f"{report.speaker}: " if report.speaker else "",
                    style=ROLE_STYLE.get(report.role, "bold"))
        line.append(report.text or "", style="bold red" if report.alarm else "")
        self.ticker = (self.ticker + [line])[-TICKER_LINES:]
        try:
            self.query_one("#profile-ticker", Static).update(Text("\n").join(self.ticker))
        except NoMatches:
            pass
