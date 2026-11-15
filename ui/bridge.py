"""Utsikten från bryggan i helskärm (Tab eller "brygga"). Spelet går vidare medan den visas.

Vyn ritar utkikens bild (`Knowledge.bridge`), som uppdateras varannan sekund
medan bryggan är bemannad i ytläge, aldrig världen. ← → vrider blicken
relativt fören, mellanslag tittar rakt förut igen. Under ytan, eller medan
luckan öppnas eller bryggan utryms, säger vyn det.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from sim.geo import norm360

from .bridge_render import TURN_STEP_DEG, header, render_bridge
from .viewbase import ViewScreen

REDRAW_S = 0.5


class BridgeScreen(ViewScreen):
    CSS = """
    BridgeScreen { background: #0b0f0c; }
    #bridge-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #bridge-body { height: 1fr; }
    #bridge-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "bridge"
    REDRAW_S = REDRAW_S
    EMPTY_KEYS = {"escape": "close", "left": "turn(-1)", "right": "turn(1)", "space": "ahead"}

    def __init__(self) -> None:
        super().__init__()
        self.view_rel = 0.0          # blicken relativt fören, grader

    def compose(self) -> ComposeResult:
        yield Static(id="bridge-head")
        yield Static(id="bridge-body")
        yield Static(id="bridge-ticker")
        yield self.order_line()

    def action_turn(self, step: int) -> None:
        self.view_rel = norm360(self.view_rel + step * TURN_STEP_DEG)
        self.draw()

    def action_ahead(self) -> None:
        self.view_rel = 0.0
        self.draw()

    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#bridge-body", Static)
            head = self.query_one("#bridge-head", Static)
        except NoMatches:
            return
        w, h = body.size.width, body.size.height
        if w < 40 or h < 10:
            return
        pic = game.knowledge.bridge
        st = game.status()
        body.update(Text("\n").join(render_bridge(
            pic, w, h, self.view_rel, game.now, st.speed, st.bridge, st.depth)))
        t = header(pic, game.clock_str(), self.view_rel)
        t.append("\n")
        t.append(" ←/→ vrid blicken · mellanslag rakt förut · Tab logg · Esc tillbaka", style="dim")
        head.update(t)
