"""Textual i webbläsaren: en drivrutin för Pyodide som ritar i xterm.js.

Textuals egna drivrutiner läser tangenter ur stdin i en tråd; i Pyodide finns varken
stdin eller trådar. Här skriver drivrutinen escapesekvenserna till terminalen i sidan
(`bridge.write`) och sidan matar tangenter och storlek tillbaka med `feed`/`resize`,
på samma händelseslinga som appen (WebLoop), så allt går utan trådar.
"""
from __future__ import annotations

import asyncio
from typing import Any

from textual import events, messages
from textual._xterm_parser import XTermParser
from textual.driver import Driver
from textual.geometry import Size

TICK_S = 0.05      # hur ofta parsern prövar en ensam Esc (timeout)


class PyodideDriver(Driver):
    """Drivrutin för en terminal i sidan. `bridge` sätts av `start.py` före appen startar:
    ett JS-objekt med `write(text)` och `exit()`."""

    bridge: Any = None
    current: "PyodideDriver | None" = None

    def __init__(self, app, *, debug: bool = False, mouse: bool = True,
                 size: tuple[int, int] | None = None):
        super().__init__(app, debug=debug, mouse=mouse, size=size)
        self._parser = XTermParser(debug=False)
        self._ticker: asyncio.Handle | None = None
        self._open = False

    @property
    def is_web(self) -> bool:
        return False        # inte textual-serve: inga leveranser av filer genom protokollet

    # ------------------------------------------------------------------ ut
    def write(self, data: str) -> None:
        if self._open:
            self.bridge.write(data)

    def flush(self) -> None:
        pass

    # ------------------------------------------------------------------ in
    def send_message(self, message: messages.Message) -> None:
        # Samma tråd och slinga som appen: lägg meddelandet direkt i kön.
        self._app.post_message(message)

    def feed(self, data: str) -> None:
        """Tangenter och mus från terminalen (xterm.js `onData`)."""
        if not self._open:
            return
        for event in self._parser.feed(data):
            self.process_message(event)

    def resize(self, width: int, height: int) -> None:
        self._size = (width, height)
        size = Size(width, height)
        self._app.post_message(events.Resize(size, size))

    def _tick(self) -> None:
        for event in self._parser.tick():
            self.process_message(event)
        if self._open:
            self._ticker = asyncio.get_running_loop().call_later(TICK_S, self._tick)

    # ------------------------------------------------------------------ läge
    def start_application_mode(self) -> None:
        PyodideDriver.current = self
        self._open = True
        write = self.write
        write("\x1b[?1049h")        # alternativ skärm
        if self._mouse:
            write("\x1b[?1000h\x1b[?1003h\x1b[?1015h\x1b[?1006h")
        write("\x1b[?25l")          # dölj markören
        write("\x1b[?2004h")        # inklistring inom klamrar
        size = Size(*(self._size or (80, 24)))
        self._app.post_message(events.Resize(size, size))
        self._ticker = asyncio.get_running_loop().call_later(TICK_S, self._tick)
        self._app.call_later(self._app.post_message, events.AppFocus())

    def disable_input(self) -> None:
        pass

    def stop_application_mode(self) -> None:
        if self._mouse:
            self.write("\x1b[?1000l\x1b[?1003l\x1b[?1015l\x1b[?1006l")
        self.write("\x1b[?2004l\x1b[?25h\x1b[?1049l")
        self._open = False
        if self._ticker is not None:
            self._ticker.cancel()
        if PyodideDriver.current is self:
            PyodideDriver.current = None
        self.bridge.exit()
