"""Rösterna: vem som talar vilket språk och hur en replik blir ljud.

Allt som rör talsyntesen bor här, så att en annan plattform bara behöver en ny
backend. Gränssnittet (`Voices`) har två sätt att tala:

    start(text, voice, rate)          läs upp direkt utan att vänta (besättningen i spelet)
    render(text, voice, rate, sr)     läs till ljud (mono flyttal) för mixern (Radio Moskva)

`backend()` väljer backend för plattformen; än så länge bara `MacSay` (macOS `say`).
Röstnamnen per språk står i backendens `VOICES`; `voice("ru")` ger namnet om rösten finns.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np


class Speaking(Protocol):
    """En replik som läses upp: frågas om den pågår och kan avbrytas."""

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...


class Voices(Protocol):
    VOICES: dict[str, str]                 # språk ("sv", "ru") -> röstnamn

    def available(self) -> bool: ...

    def has_voice(self, voice: str) -> bool: ...

    def voice(self, language: str) -> str | None: ...

    def start(self, text: str, voice: str, rate: int) -> Speaking | None: ...

    def render(self, text: str, voice: str, rate: int, sample_rate: int) -> np.ndarray | None: ...


# --------------------------------------------------------------------------- macOS
@lru_cache(maxsize=1)
def _say_voices() -> frozenset[str]:
    """Rösterna `say` har installerade (en gång per körning)."""
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    return frozenset(line.split()[0] for line in out.splitlines() if line.split())


class MacSay:
    """macOS `say`: Alva läser svenska, Milena ryska."""

    VOICES = {"sv": "Alva", "ru": "Milena"}

    def available(self) -> bool:
        return shutil.which("say") is not None

    def has_voice(self, voice: str) -> bool:
        return self.available() and voice in _say_voices()

    def voice(self, language: str) -> str | None:
        name = self.VOICES.get(language)
        return name if name is not None and self.has_voice(name) else None

    def start(self, text: str, voice: str, rate: int) -> Speaking | None:
        try:
            return subprocess.Popen(["say", "-v", voice, "-r", str(rate), text],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return None

    def render(self, text: str, voice: str, rate: int, sample_rate: int) -> np.ndarray | None:
        if not self.has_voice(voice):
            return None
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tal.wav"
            try:
                subprocess.run(["say", "-v", voice, "-r", str(rate), "--file-format=WAVE",
                                f"--data-format=LEI16@{sample_rate}", "-o", str(path), text],
                               capture_output=True, timeout=30, check=True)
                return read_wav(path, sample_rate)
            except (OSError, subprocess.SubprocessError, ValueError, wave.Error):
                return None


# --------------------------------------------------------------------------- val
@lru_cache(maxsize=1)
def backend() -> Voices:
    """Backend för den här plattformen."""
    return MacSay()


SV_VOICE = MacSay.VOICES["sv"]
RU_VOICE = MacSay.VOICES["ru"]


# --------------------------------------------------------------------------- ljudfiler
def read_wav(path: Path, sample_rate: int) -> np.ndarray:
    """Mono flyttal i sample_rate. Annan takt räknas om linjärt."""
    with wave.open(str(path), "rb") as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("bara 16 bitar")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if rate != sample_rate and len(x):
        x = np.interp(np.arange(int(len(x) * sample_rate / rate)) * rate / sample_rate,
                      np.arange(len(x)), x)
    return x
