"""Bryggans panorama, en del av utsikten (`ui/lookout.py`, Tab eller "utsikt"/"brygga").

Vyn ritar utkikens bild (`Knowledge.bridge`), som uppdateras varannan sekund
medan bryggan är bemannad i ytläge, aldrig världen. ← → vrider blicken
relativt fören, mellanslag tittar rakt förut igen, ↓ byter till okularet. Blicken delas med periskopet
(`SubApp.look_bearing`). Under ytan, eller medan
luckan öppnas eller bryggan utryms, säger vyn det.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from sim.geo import norm360

from .bridge_render import TURN_STEP_DEG, header, render_bridge


class BridgePane:
    """Bryggans panorama i utsikten (`ui/lookout.py`): blicken relativt fören och kikaren."""

    KEYS = {"left": "b_turn(-1)", "right": "b_turn(1)", "space": "b_ahead",
            "plus": "b_glass(True)", "equals_sign": "b_glass(True)", "minus": "b_glass(False)",
            "down": "okular(True)"}

    def __init__(self, screen) -> None:
        self.screen = screen
        self.view_rel = 0.0          # blicken relativt fören, grader
        self.binoculars = False      # kikaren (7°) i stället för ögat

    @property
    def app(self):
        return self.screen.app

    def enter(self) -> None:
        """Blicken där periskopet (eller okularet) senast tittade."""
        game = getattr(self.app, "game", None)
        look = getattr(self.app, "look_bearing", None)
        if game is not None and look is not None:
            self.view_rel = norm360(look - game.status().course)

    def _share_look(self) -> None:
        game = getattr(self.app, "game", None)
        if game is not None and hasattr(self.app, "look_bearing"):
            self.app.look_bearing = norm360(game.status().course + self.view_rel)

    def turn(self, step: int) -> None:
        self.view_rel = norm360(self.view_rel + step * TURN_STEP_DEG)
        self._share_look()

    def glass(self, on: bool) -> None:
        self.binoculars = on

    def ahead(self) -> None:
        self.view_rel = 0.0
        self._share_look()

    def draw(self, body: Static, head: Static) -> None:
        game = getattr(self.app, "game", None)
        if game is None:
            return
        w, h = body.size.width, body.size.height
        if w < 40 or h < 10:
            return
        pic = game.knowledge.bridge
        st = game.status()
        body.update(Text("\n").join(render_bridge(
            pic, w, h, self.view_rel, game.now, st.speed, st.bridge, st.depth, self.binoculars)))
        t = header(pic, game.clock_str(), self.view_rel, self.binoculars)
        t.append("\n")
        t.append(" ←/→ vrid blicken · mellanslag rakt förut · + kikaren · − ögat · ↓ okularet"
                 " · Tab översikten · Esc tillbaka", style="dim")
        head.update(t)
