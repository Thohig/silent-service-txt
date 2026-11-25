"""Gemensamt för helskärmsvyerna: orderrad, de senaste rapporterna och Esc.

Kaptenen kan ge order i alla vyer. Bokstäver och siffror går alltid till
orderraden. När raden är tom styr vyns tangenter (EMPTY_KEYS: pilar, +/−,
mellanslag, Esc) vyn; när den har text redigerar de texten och Esc tömmer den.
Enter verkställer ordern och vi stannar kvar i vyn.
"""
from __future__ import annotations

from rich.text import Text
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Input, Static

from sim.reports import Report

from .widgets import ROLE_STYLE

TICKER_LINES = 2
PLACEHOLDER_S = 0.5
PLACEHOLDER = "Order …   (Esc tillbaka)"


class OrderLine(Input):
    """Orderraden i en vy: vyns tangenter gäller bara när raden är tom."""

    async def _on_key(self, event) -> None:
        if event.key == "escape" and not self.value:
            from .logdrawer import close_drawer
            if close_drawer(self.screen):     # loggboken nere: Esc fäller upp den först
                event.stop()
                event.prevent_default()
                return
        keys = getattr(self.screen, "EMPTY_KEYS", {})
        if not self.value and event.key in keys:
            event.stop()
            event.prevent_default()
            await self.screen.run_action(keys[event.key])
            return
        if event.key == "escape" and self.value:
            event.stop()
            event.prevent_default()
            self.value = ""
            return
        await super()._on_key(event)


class ViewScreen(Screen):
    """Basklass för vyerna. Underklassen sätter PREFIX (id-prefix) och ritar själv."""

    DEFAULT_CSS = """
    ViewScreen #view-order { border: tall #2f4a36; background: #0f1611; height: 3; }
    ViewScreen #view-order:focus { border: tall #5f8a66; }
    """
    PREFIX = "view"
    REDRAW_S = 0.5
    EMPTY_KEYS: dict[str, str] = {"escape": "close"}

    def __init__(self) -> None:
        super().__init__()
        self.ticker: list[Text] = []

    def order_line(self) -> OrderLine:
        return OrderLine(placeholder=PLACEHOLDER, id="view-order")

    def on_mount(self) -> None:
        self.draw()
        self.set_interval(self.REDRAW_S, self.draw)
        self.set_interval(PLACEHOLDER_S, self._show_suggestion)
        try:
            self.query_one(OrderLine).focus()
        except NoMatches:
            pass

    def draw(self) -> None:          # ritas av underklassen
        pass

    def on_resize(self, event) -> None:
        """Loggboken (lagret) följer skärmens höjd. (Körs också när underklassen har en egen.)"""
        from .logdrawer import drawer_on
        if (d := drawer_on(self)) is not None:
            d.place()

    def action_close(self) -> None:
        self.app.pop_screen()

    def _show_suggestion(self) -> None:
        """Ett väntande förslag syns i orderraden, så att ja/nej går att svara här."""
        game = getattr(self.app, "game", None)
        if game is None:
            return
        try:
            line = self.query_one(OrderLine)
        except NoMatches:
            return
        if game.over:
            line.placeholder = "Uppdraget är slut – Enter: huvudmenyn   (Esc tillbaka)"
            return
        from .logdrawer import drawer_on
        esc = "(Esc loggen upp)" if drawer_on(self) is not None else "(Esc tillbaka)"
        sug = game.status().suggestion
        line.placeholder = f"Förslag: ja = {sug} · nej avslår   {esc}" if sug \
            else PLACEHOLDER.replace("(Esc tillbaka)", esc)

    # --- de senaste rapporterna ---------------------------------------------------
    def _push_ticker(self, line: Text) -> None:
        self.ticker = (self.ticker + [line])[-TICKER_LINES:]
        try:
            self.query_one(f"#{self.PREFIX}-ticker", Static).update(Text("\n").join(self.ticker))
        except NoMatches:
            pass

    def add_report(self, clock: str, report: Report) -> None:
        line = Text(f" {clock[:5]} ", style="dim")
        line.append(f"{report.speaker}: " if report.speaker else "",
                    style=ROLE_STYLE.get(report.role, "bold"))
        line.append(report.text or "", style="bold red" if report.alarm else "")
        self._push_ticker(line)

    def add_captain(self, clock: str, text: str) -> None:
        line = Text(f" {clock[:5]} ", style="dim")
        line.append("Kapten: ", style="bold")
        line.append(text, style="italic")
        self._push_ticker(line)
