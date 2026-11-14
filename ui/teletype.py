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
        t = Text(self.full_text[: self.pos], style="bold #c8d0b0")
        if not self.done:
            t.append("█", style="#c8d0b0 blink")
        if self.footer:
            t.append("\n\n" + self.footer, style="dim italic")
        self.update(t)
