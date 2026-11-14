"""Ljud: besättningen talar och larmen går.

Ljudet hör till gränssnittet och styrs enbart av levererade rapporter
(ReportDelivered) – samma sak som spelaren läser i loggen. Inget ljud
får avslöja något som besättningen inte har rapporterat.

Uppspelningen sker med macOS egna verktyg (`say` för tal, `afplay` för
larmljud) i egna processer, så att spelet aldrig väntar på ljudet. Larmljuden
syntetiseras med numpy vid start och sparas som wav i en cachekatalog.

    SoundBoard(bus, player)   prenumererar på rapporterna och köar ljud
    SoundBoard.update(t)      anropas varje bildruta: startar nästa replik
    MacPlayer / NullPlayer    uppspelning resp. tystnad
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from sim.events import EventBus, ReportDelivered
from sim.reports import Report

RATE = 22050
VOICE = "Alva"                     # svensk röst i macOS

# Talhastighet (ord/min) per roll – alla talar med samma röst men i olika takt.
ROLE_RATE = {
    "sonar": 165,                  # lågmält och noggrant
    "navigator": 175,
    "plot": 180,
    "officer": 180,
    "radio": 190,
    "torpedo": 195,
    "engineer": 200,
}
DEFAULT_RATE = 180

# Larmljud per rapporttyp. Övriga larmrapporter får "attention".
CUE_BY_TYPE = {
    # stridslarm: fienden har gått till anfall
    "sonar.ping.first": "general",
    "sonar.ping.fast": "general",
    "sonar.splash": "general",
    "sonar.nuclear": "general",
    # haverilarm
    "eng.blow": "klaxon",
    "reactor.scram": "klaxon",
    "damage": "klaxon",
    "ice.collision": "klaxon",
    "surfaced": "klaxon",
    # brandlarm
    "fire": "fire",
}

MAX_QUEUE = 4                      # fler väntande repliker än så: släpp de oviktiga
STALE_S = 12.0                     # oviktiga repliker som väntat längre släpps


# --------------------------------------------------------------------------- uppspelning
class Player(Protocol):
    def play(self, cue: str) -> float:
        """Spela ett larmljud utan att vänta. Returnerar längden i sekunder."""

    def speak(self, text: str, rate: int) -> None:
        """Börja läsa upp text utan att vänta."""

    def speaking(self) -> bool: ...

    def stop(self) -> None: ...


class NullPlayer:
    """Tystnad (--tyst, eller utan macOS-verktygen)."""

    def play(self, cue: str) -> float:
        return 0.0

    def speak(self, text: str, rate: int) -> None:
        pass

    def speaking(self) -> bool:
        return False

    def stop(self) -> None:
        pass


class MacPlayer:
    """Spelar med afplay och say. Larmljuden syntetiseras till wav vid start."""

    def __init__(self, cache_dir: Path | None = None, voice: str = VOICE,
                 volume: float = 0.6):
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "k114-ljud"
        self.voice = voice
        self.volume = volume
        self.cues: dict[str, tuple[Path, float]] = {}
        for name, samples in synth_cues().items():
            path = self.cache_dir / f"{name}.wav"
            write_wav(path, samples)
            self.cues[name] = (path, len(samples) / RATE)
        self._speech: subprocess.Popen | None = None
        self._sounds: list[subprocess.Popen] = []

    @staticmethod
    def available() -> bool:
        return shutil.which("say") is not None and shutil.which("afplay") is not None

    @staticmethod
    def has_voice(voice: str = VOICE) -> bool:
        try:
            out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                                 timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return any(line.split()[:1] == [voice] for line in out.splitlines())

    def play(self, cue: str) -> float:
        if cue not in self.cues:
            return 0.0
        path, length = self.cues[cue]
        self._sounds = [p for p in self._sounds if p.poll() is None]
        self._sounds.append(subprocess.Popen(
            ["afplay", "-v", f"{self.volume:.2f}", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        return length

    def speak(self, text: str, rate: int) -> None:
        self._speech = subprocess.Popen(
            ["say", "-v", self.voice, "-r", str(rate), text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def speaking(self) -> bool:
        return self._speech is not None and self._speech.poll() is None

    def stop(self) -> None:
        for p in [self._speech, *self._sounds]:
            if p is not None and p.poll() is None:
                p.terminate()
        self._speech = None
        self._sounds = []


# --------------------------------------------------------------------------- styrning
@dataclass
class Line:
    text: str
    rate: int
    urgent: bool
    queued_at: float
    not_before: float = 0.0


@dataclass
class SoundBoard:
    """Gör ljud av besättningens rapporter."""
    bus: EventBus
    player: Player
    speech: bool = True
    enabled: bool = True
    queue: list[Line] = field(default_factory=list)
    _now: float = 0.0
    _cue_until: float = 0.0

    def __post_init__(self) -> None:
        self.bus.subscribe(ReportDelivered, self._on_report)

    # -- rapporter -----------------------------------------------------------
    def _on_report(self, e: ReportDelivered) -> None:
        if not self.enabled:
            return
        r = e.report
        cue = cue_for(r)
        delay = 0.0
        if cue:
            length = self.player.play(cue)
            # Talet börjar när larmet nästan har klingat av.
            delay = length * 0.7 if cue in ("general", "klaxon", "fire") else length * 0.5
            self._cue_until = max(self._cue_until, self._now + delay)
        if not self.speech or not spoken(r):
            return
        line = Line(speech_text(r.text), ROLE_RATE.get(r.role, DEFAULT_RATE),
                    urgent=r.alarm or r.kind == "suggest", queued_at=self._now,
                    not_before=self._now + delay)
        self.queue.append(line)
        self._trim()

    def _trim(self) -> None:
        """Håll kön kort: vid tidskomprimering hinner ingen säga allt."""
        self.queue = [ln for ln in self.queue
                      if ln.urgent or self._now - ln.queued_at < STALE_S]
        while len(self.queue) > MAX_QUEUE:
            routine = [ln for ln in self.queue if not ln.urgent]
            self.queue.remove(routine[0] if routine else self.queue[0])

    # -- varje bildruta ------------------------------------------------------
    def update(self, now: float) -> None:
        """now: monoton realtid i sekunder."""
        self._now = now
        if not self.enabled or not self.queue:
            return
        self._trim()
        if not self.queue or self.player.speaking() or \
                now < max(self.queue[0].not_before, self._cue_until):
            return
        line = self.queue.pop(0)
        self.player.speak(line.text, line.rate)

    @property
    def available(self) -> bool:
        """Finns något att spela med (inte --tyst eller saknade verktyg)?"""
        return not isinstance(self.player, NullPlayer)

    def toggle(self) -> bool:
        """Slå av eller på ljudet. Returnerar det nya läget."""
        self.enabled = not self.enabled
        if not self.enabled:
            self.queue.clear()
            self.player.stop()
        return self.enabled

    def close(self) -> None:
        self.queue.clear()
        self.player.stop()


def cue_for(r: Report) -> str | None:
    if r.type in CUE_BY_TYPE:
        return CUE_BY_TYPE[r.type]
    if r.alarm:
        return "attention"
    if r.kind == "suggest" and r.data.get("order"):
        return "suggest"
    return None


def spoken(r: Report) -> bool:
    """Bara besättningens egna repliker läses upp – inte tabeller och systemrader."""
    return bool(r.role) and r.kind != "system" and r.table is None and bool(r.text.strip())


_DIGIT = {"0": "noll", "1": "ett", "2": "två", "3": "tre", "4": "fyra",
          "5": "fem", "6": "sex", "7": "sju", "8": "åtta", "9": "nio"}
_COURSE = re.compile(r"\b(kurs|bäring|bäringen|kursen|bäringarna|riktning)( \w+)?? (\d{3})\b",
                     re.IGNORECASE)


def speech_text(text: str) -> str:
    """Gör texten lätt att läsa upp: kurser siffra för siffra, som till sjöss."""
    def course(m: re.Match) -> str:
        digits = " ".join(_DIGIT[c] for c in m[3])
        return f"{m[1]}{m[2] or ''} {digits}"
    t = _COURSE.sub(course, text)
    t = re.sub(r"\baye\b", "aj", t, flags=re.IGNORECASE)
    t = t.replace("–", ",").replace("…", ".")
    return t


# --------------------------------------------------------------------------- syntes
def _t(seconds: float) -> np.ndarray:
    return np.arange(int(RATE * seconds)) / RATE


def _speaker(x: np.ndarray, drive: float = 2.0) -> np.ndarray:
    """Gammal högtalare: lätt överstyrning och normalisering."""
    y = np.tanh(drive * x)
    return y / max(1e-9, float(np.max(np.abs(y))))


def _bell_strike(seconds: float, base: float) -> np.ndarray:
    t = _t(seconds)
    partials = [(1.0, 1.0), (2.76, 0.6), (5.40, 0.35), (8.93, 0.2)]
    s = sum(a * np.sin(2 * np.pi * base * k * t) * np.exp(-t * (6 + 4 * k))
            for k, a in partials)
    return s


def synth_general() -> np.ndarray:
    """Stridslarm: ringklocka, tre ringningar."""
    out = np.zeros(int(RATE * 3.2))
    strike = _bell_strike(0.25, 820)
    for ring_start in (0.0, 1.1, 2.2):
        for i in range(int(0.8 / 0.045)):
            a = int(RATE * (ring_start + i * 0.045))
            seg = strike[: len(out) - a]
            out[a:a + len(seg)] += seg
    return 0.8 * _speaker(out, 1.2)


def synth_klaxon() -> np.ndarray:
    """Haverilarm: tre hesa tutor."""
    out = np.zeros(int(RATE * 2.4))
    t = _t(0.55)
    f = 330 + 50 * np.minimum(t / 0.12, 1.0)               # stiger in i tonen
    phase = 2 * np.pi * np.cumsum(f) / RATE
    blast = np.sign(np.sin(phase)) * 0.6 + np.sin(2 * phase) * 0.4
    env = np.minimum(1.0, t / 0.02) * np.minimum(1.0, (t[-1] - t) / 0.05)
    blast *= env
    for k in range(3):
        a = int(RATE * k * 0.8)
        out[a:a + len(blast)] += blast
    return 0.7 * _speaker(out, 1.5)


def synth_fire() -> np.ndarray:
    """Brandlarm: två toner som växlar snabbt."""
    t = _t(2.8)
    f = np.where((t * 4).astype(int) % 2 == 0, 960.0, 720.0)
    phase = 2 * np.pi * np.cumsum(f) / RATE
    s = np.sign(np.sin(phase)) * 0.5 + np.sin(phase) * 0.5
    env = np.minimum(1.0, t / 0.02) * np.minimum(1.0, (t[-1] - t) / 0.1)
    return 0.6 * _speaker(s * env, 1.5)


def synth_attention() -> np.ndarray:
    """Uppmärksamhet: tvåtonssignal i högtalaren."""
    parts = []
    for f in (660.0, 880.0):
        t = _t(0.22)
        tone = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)
        parts.append(tone * np.minimum(1.0, t / 0.01) * np.exp(-t * 6))
    return 0.5 * _speaker(np.concatenate(parts), 1.2)


def synth_suggest() -> np.ndarray:
    """Förslag: en kort, dämpad ton."""
    t = _t(0.3)
    tone = np.sin(2 * np.pi * 520 * t) * np.minimum(1.0, t / 0.01) * np.exp(-t * 10)
    return 0.3 * _speaker(tone, 1.0)


def synth_cues() -> dict[str, np.ndarray]:
    return {"general": synth_general(), "klaxon": synth_klaxon(), "fire": synth_fire(),
            "attention": synth_attention(), "suggest": synth_suggest()}


def write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def make_soundboard(bus: EventBus, enabled: bool) -> tuple[SoundBoard, str | None]:
    """Koppla ljud till spelet. Returnerar (ljudbord, meddelande till kaptenen eller None)."""
    if not enabled:
        return SoundBoard(bus, NullPlayer(), enabled=False), None
    if not MacPlayer.available():
        return SoundBoard(bus, NullPlayer(), enabled=False), \
            "Ljud saknas: kräver macOS (say och afplay)."
    if not MacPlayer.has_voice():
        return SoundBoard(bus, MacPlayer(), speech=False), \
            (f"Rösten {VOICE} saknas, besättningen hörs inte. Lägg till den under "
             "Systeminställningar › Hjälpmedel › Talat innehåll › Systemröst.")
    return SoundBoard(bus, MacPlayer()), None
