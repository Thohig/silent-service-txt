"""Utsikten (Tab, "utsikt", "brygga", "periskopbild"): bryggan och periskopbilden i en vy.

De två var egna vyer men syns aldrig samtidigt: bryggan bara med tornluckan öppen, periskopet bara
under ytan (eller i ytläge när det hålls uppe). Vyn väljer själv efter läget:
- bryggan bemannad (eller luckan på väg upp eller ned) och periskopet inte uppe: bryggans panorama
  (`ui/bridge.py`, `BridgePane`), och ↓ byter till kikarens okular (↑ tillbaka);
- annars periskopets okular (`ui/periscope.py`, `PeriscopePane`).
Blickens bäring delas mellan dem (`SubApp.look_bearing`). Vyns tangenter (`EMPTY_KEYS`) följer det som
visas. Spelet går vidare medan vyn visas.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Static

from .bridge import BridgePane
from .periscope import PeriscopePane
from .viewbase import ViewScreen

REDRAW_S = 0.5


class LookoutScreen(ViewScreen):
    CSS = """
    LookoutScreen { background: #0b0f0c; }
    #lookout-head { height: 2; background: #1c2a20; color: #c8d0b0; }
    #lookout-body { height: 1fr; }
    #lookout-ticker { height: 2; background: #0f1611; }
    """
    PREFIX = "lookout"
    REDRAW_S = REDRAW_S

    def __init__(self) -> None:
        super().__init__()
        self.bridge = BridgePane(self)
        self.periscope = PeriscopePane(self)
        self.okular = False              # på bryggan: kikarens okular i stället för panoramat
        self._shown: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="lookout-head")
        yield Static(id="lookout-body")
        yield Static(id="lookout-ticker")
        yield self.order_line()

    # --- vad som visas ---------------------------------------------------------------
    def mode(self) -> str:
        """"bridge" (panoramat), "glass" (kikarens okular på bryggan) eller "periscope"."""
        game = getattr(self.app, "game", None)
        if game is None:
            return "periscope"
        st = game.status()
        if st.bridge != "shut" and st.periscope is None:
            return "glass" if self.okular and st.bridge == "manned" else "bridge"
        return "periscope"

    @property
    def EMPTY_KEYS(self) -> dict[str, str]:          # noqa: N802 (läses som klassens tangenter)
        m = self.mode()
        keys = BridgePane.KEYS if m == "bridge" else \
            PeriscopePane.GLASS_KEYS if m == "glass" else PeriscopePane.KEYS
        return {"escape": "close", **keys}

    def draw(self) -> None:
        if getattr(self.app, "game", None) is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#lookout-body", Static)
            head = self.query_one("#lookout-head", Static)
        except NoMatches:
            return
        m = self.mode()
        if m == "bridge" and self._shown != "bridge":
            self.bridge.enter()                    # panoramat mot det okularet tittade på
        self._shown = m
        if m == "bridge":
            self.bridge.draw(body, head)
        else:
            self.periscope.draw(body, head)

    # --- tangenterna ------------------------------------------------------------------
    def action_okular(self, on: bool) -> None:
        self.okular = on
        self.draw()

    def action_b_turn(self, step: int) -> None:
        self.bridge.turn(step)
        self.draw()

    def action_b_ahead(self) -> None:
        self.bridge.ahead()
        self.draw()

    def action_b_glass(self, on: bool) -> None:
        self.bridge.glass(on)
        self.draw()

    def action_p_select(self, step: int) -> None:
        self.periscope.select(step)

    def action_p_raise(self) -> None:
        self.periscope.raise_()

    def action_p_lower(self) -> None:
        self.periscope.lower()

    def action_p_ahead(self) -> None:
        self.periscope.ahead()

    def action_p_power(self, power: str) -> None:
        self.periscope.power(power)
