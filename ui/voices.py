"""Rösterna: vem som talar vilket språk och hur en replik blir ljud.

Allt som rör talsyntesen bor här, så att en annan plattform bara behöver en ny
backend. Gränssnittet (`Voices`) har två sätt att tala:

    start(text, voice, rate)          läs upp direkt utan att vänta (besättningen i spelet)
    render(text, voice, rate, sr)     läs till ljud (mono flyttal) för mixern (Radio Moskva)

`backend()` väljer backend för plattformen: `MacSynth` (macOS talsyntes i processen, rösterna
laddade, 20–60 ms per replik) om pyobjc finns, annars `MacSay` (`say`, `say -o` ~0,55 s). I
webbläsaren (Pyodide) `WebSpeech`: sidans talsyntes, som bara kan läsa upp direkt (ingen `render`).
Röstnamnen per språk står i backendens `VOICES`; `voice("ru")` ger namnet om rösten finns.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
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


class MacSynth(MacSay):
    """macOS talsyntes i processen (NSSpeechSynthesizer): rösterna laddas en gång och hålls
    kvar, så att en replik renderas på 20–60 ms i stället för `say -o`:s halva sekund.

    All syntes sker i en egen tråd som äger syntesmotorerna (en per röst) och kör sin
    händelseslinga medan den skriver; `render` går att anropa från vilken tråd som helst.
    Uppläsning direkt (`start`) går som förut genom `say`."""

    TIMEOUT_S = 30.0

    def __init__(self) -> None:
        import queue
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._dir = Path(tempfile.mkdtemp(prefix="k114-tal-"))
        self._n = 0

    @staticmethod
    def supported() -> bool:
        try:
            import AppKit  # noqa: F401 – finns pyobjc?
        except ImportError:
            return False
        return True

    def render(self, text: str, voice: str, rate: int, sample_rate: int) -> np.ndarray | None:
        if not self.has_voice(voice):
            return None
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, daemon=True, name="talsyntes")
            self._thread.start()
        done = threading.Event()
        job = {"text": text, "voice": voice, "rate": rate, "out": None, "done": done}
        self._jobs.put(job)
        if not done.wait(self.TIMEOUT_S):
            return None
        x = job["out"]
        return None if x is None else _resample(x, job["rate_hz"], sample_rate)

    def warm_up(self, *voices_: str) -> None:
        """Ladda rösterna i förväg (första repliken blir annars 0,1–0,4 s långsammare)."""
        for v in voices_:
            if self.has_voice(v):
                threading.Thread(target=self.render, args=(".", v, 180, 22050),
                                 daemon=True).start()

    def _work(self) -> None:
        from AppKit import NSSpeechSynthesizer
        from Foundation import NSURL, NSDate, NSRunLoop
        ids: dict[str, str] = {}
        for v in NSSpeechSynthesizer.availableVoices():
            name = str(NSSpeechSynthesizer.attributesForVoice_(v)["VoiceName"]).split(" (")[0]
            # Finns flera kvaliteter: premium före förbättrad före kompakt.
            rank = 2 if ".premium." in v else 1 if ".enhanced." in v else 0
            if name not in ids or rank > ids[name][1]:
                ids[name] = (v, rank)
        synths: dict[str, object] = {}
        loop = NSRunLoop.currentRunLoop()
        while True:
            job = self._jobs.get()
            try:
                syn = synths.get(job["voice"])
                if syn is None:
                    syn = NSSpeechSynthesizer.alloc().initWithVoice_(ids[job["voice"]][0])
                    synths[job["voice"]] = syn
                syn.setRate_(float(job["rate"]))
                self._n += 1
                path = self._dir / f"{self._n % 8}.aiff"
                if not syn.startSpeakingString_toURL_(job["text"], NSURL.fileURLWithPath_(str(path))):
                    raise OSError("syntesen startade inte")
                t0 = time.monotonic()
                while syn.isSpeaking() and time.monotonic() - t0 < self.TIMEOUT_S:
                    loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.005))
                job["out"], job["rate_hz"] = read_aiff(path)
            except Exception:                          # noqa: BLE001 – en replik får aldrig fälla talet
                job["out"] = None
            finally:
                job["done"].set()


# --------------------------------------------------------------------------- webbläsaren
class _Utterance:
    """En replik i webbläsarens talsyntes (`Speaking`)."""

    def __init__(self, handle, bridge):
        self.handle = handle
        self.bridge = bridge

    def poll(self) -> int | None:
        return 0 if self.handle.done else None

    def terminate(self) -> None:
        if not self.handle.done:
            self.bridge.cancel()


class WebSpeech:
    """Webbläsarens talsyntes (`speechSynthesis`) genom sidans brygga (`web/index.html`,
    `speech`): `has(språk)`, `speak(text, språk, takt)` ger ett handtag med `done`, `cancel()`.
    Röstnamnen är spelets (Alva, Milena); sidan väljer den rösten om webbläsaren har den,
    annars en annan på samma språk. Uppläsningen går inte genom mixern, så `render` ger None."""

    VOICES = MacSay.VOICES
    BASE_WPM = 180                 # `say`-takt som motsvarar webbläsarens takt 1

    bridge = None                  # sätts av web/start.py

    def available(self) -> bool:
        return self.bridge is not None

    def _language(self, voice: str) -> str | None:
        return next((lang for lang, name in self.VOICES.items() if name == voice), None)

    def has_voice(self, voice: str) -> bool:
        lang = self._language(voice)
        return self.available() and lang is not None and bool(self.bridge.has(lang))

    def voice(self, language: str) -> str | None:
        name = self.VOICES.get(language)
        return name if name is not None and self.has_voice(name) else None

    def start(self, text: str, voice: str, rate: int) -> Speaking | None:
        lang = self._language(voice)
        if not self.available() or lang is None:
            return None
        try:
            return _Utterance(self.bridge.speak(text, lang, rate / self.BASE_WPM), self.bridge)
        except Exception:                              # noqa: BLE001 – en replik får aldrig fälla talet
            return None

    def render(self, text: str, voice: str, rate: int, sample_rate: int) -> np.ndarray | None:
        return None


# --------------------------------------------------------------------------- val
@lru_cache(maxsize=1)
def backend() -> Voices:
    """Backend för den här plattformen: i webbläsaren dess talsyntes, på macOS talsyntesen i
    processen om den finns, annars `say`."""
    if sys.platform == "emscripten":
        return WebSpeech()
    return MacSynth() if MacSynth.supported() else MacSay()


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
    return _resample(x, rate, sample_rate)


def read_aiff(path: Path) -> tuple[np.ndarray, int]:
    """AIFF/AIFC med 16 bitar okomprimerat (som macOS talsyntes skriver): (mono, takt)."""
    data = Path(path).read_bytes()
    if data[:4] != b"FORM" or data[8:12] not in (b"AIFF", b"AIFC"):
        raise ValueError("inte AIFF")
    pos, ch, bits, rate, pcm = 12, 1, 16, 22050, b""
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"COMM":
            ch, _frames, bits = struct.unpack(">hIh", body[:8])
            exp, mant = struct.unpack(">HQ", body[8:18])
            rate = int(round(mant * 2.0 ** ((exp & 0x7FFF) - 16383 - 63)))
            if len(body) >= 22 and body[18:22] not in (b"NONE", b"twos"):
                raise ValueError("komprimerad AIFF")
        elif cid == b"SSND":
            offset = struct.unpack(">I", body[:4])[0]
            pcm = body[8 + offset:]
        pos += 8 + size + (size & 1)
    if bits != 16:
        raise ValueError("bara 16 bitar")
    x = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype=">i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x[:len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, rate


def _resample(x: np.ndarray, rate: int, sample_rate: int) -> np.ndarray:
    """Linjär omräkning av takten."""
    if rate == sample_rate or not len(x):
        return x
    return np.interp(np.arange(int(len(x) * sample_rate / rate)) * rate / sample_rate,
                     np.arange(len(x)), x)
