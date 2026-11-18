"""Telegramremsor från fjärrskrivaren: rubrik på rött fält och texten under.

Skrivs i loggboken under radiomannens rad (`TelegramStrip`, rich-renderbar efter bredden).
"""
from __future__ import annotations

from rich.text import Text

from .menutext import HIGHLIGHT_FG, INK, RED, RED_DARK

MAX_W = 96                  # remsan är smalare än en bred logg, som papper


def strip_lines(number: int | str, kind: str, clock: str, text: str, width: int,
                note: str = "") -> list[Text]:
    """En remsa: rubrik på rött fält och texten under, `width` tecken bred. `kind`: telegram
    (staben), broadcast (Radio Moskva), outgoing (vår rapport till staben) eller order (den
    hemliga ordern; `note` = stämpeln)."""
    w = max(30, min(width - 2, MAX_W))
    broadcast = kind == "broadcast"
    if kind == "order":
        left = f" ШИФРОГРАММА · Вх. № {number} · {clock}"
        right = f"ordern{', ' + note if note else ''} "
        head_style = f"bold {INK} on {RED_DARK}"
    elif kind == "outgoing":
        left = f" ДОНЕСЕНИЕ · Исх. № {number} · {clock}"
        right = "rapport till staben "
        head_style = f"bold {INK} on {RED_DARK}"
    elif broadcast:
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
    body = Text(text.strip("\n"), style=f"italic {INK}" if broadcast else f"bold {INK}")
    for line in body.wrap(_console(), w - 2):
        t = Text("   ")
        t.append_text(line)
        rows.append(t)
    return rows


class TelegramStrip:
    """En remsa i loggboken. Ritas om efter loggens bredd (rich-renderbar)."""

    def __init__(self, number: int | str, kind: str, clock: str, text: str,
                 note: str = "") -> None:
        self.number, self.kind, self.clock, self.text, self.note = number, kind, clock, text, note

    def __rich_console__(self, console, options):
        yield Text("\n").join(strip_lines(self.number, self.kind, self.clock, self.text,
                                          options.max_width, self.note))


def _console():
    from rich.console import Console
    return Console(width=400)
