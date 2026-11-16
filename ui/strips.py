"""Telegramremsor från fjärrskrivaren: rubrik på rött fält och texten under.

Skrivs i loggboken under radiomannens rad (`TelegramStrip`, rich-renderbar efter bredden).
"""
from __future__ import annotations

from rich.text import Text

from .menutext import HIGHLIGHT_FG, INK, RED, RED_DARK


def strip_lines(number: int, kind: str, clock: str, text: str, width: int) -> list[Text]:
    """En remsa: rubrik på rött fält och texten under, `width` tecken bred."""
    w = max(30, width - 2)
    broadcast = kind == "broadcast"
    if broadcast:
        left = f" РАДИО МОСКВА · {clock}"
        right = f"rundradio, nr {number} "
        head_style = f"bold {INK} on {RED_DARK}"
    else:
        left = f" РАДИОГРАММА № {number} · {clock}"
        right = "telegram från staben "
        head_style = f"bold {HIGHLIGHT_FG} on {RED}"
    if len(left) + len(right) + 2 > w:
        right = ""
    rows = [Text(" " + left + " " * max(2, w - len(left) - len(right)) + right,
                 style=head_style, no_wrap=True, overflow="crop")]
    rows[0].stylize("default", 0, 1)
    body = Text(text, style=f"italic {INK}" if broadcast else f"bold {INK}")
    for line in body.wrap(_console(), w - 2):
        t = Text("   ")
        t.append_text(line)
        rows.append(t)
    return rows


class TelegramStrip:
    """En remsa i loggboken. Ritas om efter loggens bredd (rich-renderbar)."""

    def __init__(self, number: int, kind: str, clock: str, text: str) -> None:
        self.number, self.kind, self.clock, self.text = number, kind, clock, text

    def __rich_console__(self, console, options):
        yield Text("\n").join(strip_lines(self.number, self.kind, self.clock, self.text,
                                          options.max_width))


def _console():
    from rich.console import Console
    return Console(width=400)
