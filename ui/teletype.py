"""Utskrift tecken för tecken, som en fjärrskrivare."""
from __future__ import annotations

from rich.text import Text
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Static


class Teletype(Static):
    class Finished(Message):
        pass

    def __init__(self, text: str = "", cps: float = 45.0, **kw):
        super().__init__("", **kw)
        self.full_text = text
        self.cps = cps
        self.pos = 0
        self.done = False
        self._timer: Timer | None = None
        self.footer = ""
        self.header: Text | None = None      # står kvar ovanför texten (telegrammets huvud)
        self.signature: Text | None = None   # visas under texten när den är utskriven
        self.style = "bold #c8d0b0"

    def start(self) -> None:
        self._timer = self.set_interval(1.0 / self.cps, self._advance)

    def _advance(self) -> None:
        if self.pos < len(self.full_text):
            # hoppa över blanktecken direkt, så rytmen känns som en fjärrskrivare
            self.pos += 1
            while self.pos < len(self.full_text) and self.full_text[self.pos] == " ":
                self.pos += 1
            self._redraw()
        else:
            self.finish()

    def finish(self) -> None:
        if self.done:
            return
        self.pos = len(self.full_text)
        self.done = True
        if self._timer:
            self._timer.stop()
        self._redraw()
        self.post_message(self.Finished())

    def set_footer(self, text: str) -> None:
        self.footer = text
        self._redraw()

    def _redraw(self) -> None:
        t = Text()
        if self.header is not None:
            t.append_text(self.header)
            t.append("\n\n")
        t.append(self.full_text[: self.pos], style=self.style)
        if not self.done:
            t.append("█", style=f"{self.style.split()[-1]} blink")
        elif self.signature is not None:
            t.append("\n")
            t.append_text(self.signature)
        if self.footer:
            t.append("\n\n" + self.footer, style="dim italic")
        self.update(t)
