"""Telegrammen i helskärm ("telegram"): det radion tagit emot, som remsor från fjärrskrivaren.

Läser bara kunskapen (`Knowledge.telegrams`, händelsen `TelegramReceived`): staben sänder vid
sambandstillfällena, och Radio Moskva hörs när kaptenen beordrar `lyssna radio`.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Static

from .menutext import DIM, HIGHLIGHT_FG, INK, RED, RED_DARK
from .placards import view_title
from .viewbase import ViewScreen

PAPER = "#1a120d"


def render_telegrams(telegrams, clock_of, width: int) -> Text:
    """Remsorna, äldst överst. clock_of(t) ger klockan "hh:mm"."""
    out = Text()
    if not telegrams:
        out.append("\n  Inget mottaget än. Staben sänder vid sambandstillfällena (antenndjup); "
                   "Radio Moskva hörs med lyssna radio.", style=f"italic {DIM}")
        return out
    w = max(30, width - 4)
    for tg in telegrams:
        broadcast = tg.kind == "broadcast"
        if broadcast:
            left = f" РАДИО МОСКВА · {clock_of(tg.t)}"
            right = f"rundradio, nr {tg.number} "
            head_style = f"bold {INK} on {RED_DARK}"
        else:
            left = f" РАДИОГРАММА № {tg.number} · {clock_of(tg.t)}"
            right = "telegram från staben "
            head_style = f"bold {HIGHLIGHT_FG} on {RED}"
        out.append("\n ")
        out.append(left + " " * max(2, w - len(left) - len(right)) + right, style=head_style)
        out.append("\n")
        body = Text(tg.text, style=f"italic {INK}" if broadcast else f"bold {INK}")
        for line in body.wrap(_console(), w - 2):
            out.append("  ")
            out.append_text(line)
            out.append("\n")
    return out


def _console():
    from rich.console import Console
    return Console(width=400)


class TelegramScreen(ViewScreen):
    CSS = f"""
    TelegramScreen {{ background: {PAPER}; }}
    #telegrams-head {{ height: 1; background: #1c2a20; color: #c8d0b0; }}
    #telegrams-scroll {{ height: 1fr; background: {PAPER}; scrollbar-size-vertical: 1; }}
    #telegrams-body {{ padding: 0 1; background: {PAPER}; }}
    #telegrams-ticker {{ height: 2; background: #0f1611; }}
    """
    PREFIX = "telegrams"
    REDRAW_S = 0.5

    def __init__(self) -> None:
        super().__init__()
        self._shown: tuple[int, int] | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="telegrams-head")
        with VerticalScroll(id="telegrams-scroll"):
            yield Static(id="telegrams-body")
        yield Static(id="telegrams-ticker")
        yield self.order_line()

    def draw(self) -> None:
        game = getattr(self.app, "game", None)
        if game is None or not self.is_mounted:
            return
        try:
            body = self.query_one("#telegrams-body", Static)
            head = self.query_one("#telegrams-head", Static)
            scroll = self.query_one("#telegrams-scroll", VerticalScroll)
        except NoMatches:
            return
        tgs = game.knowledge.telegrams
        t = view_title("TELEGRAM", " ")
        t.append(f" {len(tgs)} mottagna", style="bold")
        t.append("   lyssna radio: Moskva på antenndjup · Esc tillbaka", style="dim")
        head.update(t)
        key = (len(tgs), body.size.width)
        if key != self._shown:
            self._shown = key
            body.update(render_telegrams(tgs, lambda s: game.clock_str(s)[:5],
                                         body.size.width or 80))
            scroll.scroll_end(animate=False)
