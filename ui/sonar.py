"""Sonarvyn i helskärm (Tab eller "sonar"): vattenfallet, bäring mot tid. Spelet går vidare
medan den visas. Vyn visar vad sonarrummet hört och vad plottet säger om det; den räknar
inget själv."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .placards import view_title
from .sonar_render import render_sonar
from .viewbase import ViewScreen

WINDOWS_S = (600, 1800, 3600)          # tidsfönster: 10, 30, 60 min
DEFAULT_WINDOW = 1
PAN_DEG = 30
REDRAW_S = 0.5


class SonarScreen(ViewScreen):
    CSS = """
    SonarScreen { background: #0b0f0c; }
    #sonar-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #sonar-body { height: 1fr; }
    #sonar-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "sonar"
    REDRAW_S = REDRAW_S
    EMPTY_KEYS = {"escape": "close", "plus": "window(-1)", "equals_sign": "window(-1)",
                  "minus": "window(1)", "left": "pan(-1)", "right": "pan(1)",
                  "space": "center", "down": "relative", "up": "solution"}

    def __init__(self) -> None:
        super().__init__()
        self.window = DEFAULT_WINDOW
        self.turn = 0.0                  # vridning från norr (sann) eller fören (relativ)
        self.relative = False
        self.show_solution = False

    def compose(self) -> ComposeResult:
        yield Static(id="sonar-head")
        yield Static(id="sonar-body")
        yield Static(id="sonar-ticker")
        yield self.order_line()

    @property
    def window_s(self) -> int:
        return WINDOWS_S[self.window]

    # --- tangenter ----------------------------------------------------------------
    def action_window(self, step: int) -> None:
        self.window = min(max(self.window + step, 0), len(WINDOWS_S) - 1)
        self.draw()

    def action_pan(self, step: int) -> None:
        self.turn = (self.turn + step * PAN_DEG) % 360
        self.draw()

    def action_center(self) -> None:
        self.turn = 0.0
        self.draw()

    def action_relative(self) -> None:
        self.relative = not self.relative
        self.turn = 0.0
        self.draw()

    def action_solution(self) -> None:
        self.show_solution = not self.show_solution
        self.draw()

    # --- ritning --------------------------------------------------------------------
    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#sonar-body", Static)
            head = self.query_one("#sonar-head", Static)
        except NoMatches:
            return
        w, h = body.size.width, body.size.height
        if w < 20 or h < 6:
            return
        view = game.sonar()
        lines = render_sonar(view, w, h, self.window_s, self.turn, self.relative,
                             self.show_solution)
        body.update(Text("\n").join(lines))

        t = view_title("SONARRUMMET", " ")
        t.append(f" vattenfallet · {view.clock[:5]} · "
                 + ("relativ bäring" if self.relative else "sann bäring")
                 + f" · {self.window_s // 60} min"
                 + (" · plottets lösning" if self.show_solution else ""))
        t.append("\n")
        t.append(" ←/→ vrid · +/− tid · ↓ sann/relativ · ↑ lösningen · mellanslag "
                 + ("fören" if self.relative else "norr") + " i mitten · Tab vidare · Esc tillbaka",
                 style="dim")
        head.update(t)
