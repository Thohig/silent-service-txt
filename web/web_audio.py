"""Ljudet i webbläsaren: mixern (`ui.ambience.Ambience`) till Web Audio.

I terminalen hämtar sounddevice ljudet ur mixern i en egen tråd (`AmbientOut`). Pyodide har
inga trådar, och Web Audios ljudtråd kan inte anropa Python. Därför fyller `WebOut` på i
förväg från händelseslingan: var `TICK_S` renderas så mycket att sidan har `AHEAD_S` ljud
i kö, och sidans AudioWorklet (`index.html`) spelar kön. Fördröjningen är alltså ~`AHEAD_S`.
Hinner slingan inte med (ett tungt tick) blir det en kort tystnad, och kön börjar om, då
`AHEAD_STEP_S` längre (högst `MAX_AHEAD_S`): Safari kör Pyodide långsammare och tömde kön av och till.

`sink` är sidans ljudbrygga (`start.JsAudio`): `rate`, `time()` (ljudklockan i sekunder; står
still tills sidan fått en tangent, då webbläsaren tillåter ljud) och `push(ljud)` (stereo
float32, (n, 2)). Utan brygga är det tyst (`error`), som `AmbientOut` utan ljudkort.
Har bryggan `channel()` öppnar varje `WebOut` sin egen kanal: menyns och spelets ljud går
samtidigt medan ordern skrivs ut, och i en delad kö varvades deras block i stället för att blandas.
"""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np

from ui.ambience import BLOCK, RATE, Ambience

TICK_S = 0.05      # hur ofta kön fylls på
AHEAD_S = 0.25     # så mycket ljud ska ligga i kö från början
AHEAD_STEP_S = 0.1  # så mycket längre kö efter varje gång den tagit slut
MAX_AHEAD_S = 1.0   # längre kö än så gör knappljud och ping för sena


class WebOut:
    """Samma gränssnitt som `AmbientOut` (`stream`, `error`, `close`), för webbläsaren."""

    sink: Any = None     # sätts av start.py

    def __init__(self, ambience: Ambience, sink: Any = None, timer: bool = True):
        self.ambience = ambience
        self.stream = sink if sink is not None else WebOut.sink
        self.error: str | None = None
        self._until: float | None = None   # ljudklockan där kön slutar
        self.ahead = AHEAD_S                # så långt fram kön fylls
        self.underruns = 0                  # gånger kön tagit slut
        self._handle: asyncio.TimerHandle | None = None
        if self.stream is None:
            self.error = "Webbläsaren har inget ljud."
            return
        if int(self.stream.rate) != RATE:
            self.error = f"Ljudet går i {self.stream.rate} Hz, inte {RATE}."
            self.stream = None
            return
        if hasattr(self.stream, "channel"):
            self.stream = self.stream.channel()     # egen kanal: blandas med de andra
        if timer:
            self._schedule()

    def pump(self) -> int:
        """Fyll på kön till `AHEAD_S` fram. Returnerar antal renderade ljudrutor."""
        if self.stream is None:
            return 0
        now = float(self.stream.time())
        if self._until is not None and self._until < now:
            self.underruns += 1                     # kön tog slut: tystnad sedan _until
            self.ahead = min(MAX_AHEAD_S, self.ahead + AHEAD_STEP_S)
        if self._until is None or self._until < now:
            self._until = now                       # början, eller kön tog slut
        frames = 0
        while self._until - now < self.ahead:
            x = self.ambience.render(BLOCK).astype(np.float32)
            self.stream.push(x)
            self._until += BLOCK / RATE
            frames += BLOCK
        return frames

    def _schedule(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return                                  # utan slinga: pump() anropas för hand
        self._handle = loop.call_later(TICK_S, self._tick)

    def _tick(self) -> None:
        try:
            self.pump()
        except Exception as exc:                    # noqa: BLE001 – ljudet får aldrig stoppa spelet
            self.error = str(exc)
            self.close()
            return
        if self.stream is not None:
            self._schedule()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        if self.stream is not None:
            getattr(self.stream, "close", self.stream.clear)()
            self.stream = None
