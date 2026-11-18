"""Ljud: besättningen talar och larmen går.

Ljudet hör till gränssnittet och styrs enbart av levererade rapporter
(ReportDelivered) – samma sak som spelaren läser i loggen. Inget ljud
får avslöja något som besättningen inte har rapporterat.

Dessutom hörs det sonaren hör (SoundHeard): pingar, bojar, sprängningar,
sönderbrytning. Styrkan sätter volymen och den relativa bäringen
panorerar ljudet i stereo – babord till vänster. Egna ljud (aktiv ping,
avfyring, skenmål, nödblåsning) kommer från OwnSoundMade.

Uppspelningen sker i egna processer, så att spelet aldrig väntar på ljudet:
talet genom rösterna (`voices.py`, på macOS `say`) och ljuden med `afplay`. Ljuden
syntetiseras med numpy och sparas som wav i en cachekatalog, ett per
panoreringsläge.

    SoundBoard(bus, player)   prenumererar på rapporter och ljud och köar tal
    SoundBoard.update(t)      anropas varje bildruta: startar nästa replik
    MacPlayer / NullPlayer    uppspelning resp. tystnad
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from sim.events import EventBus, OwnSoundMade, ReportDelivered, SoundHeard
from sim.reports import Report
from sim.russian import segments

from . import voices
from .ambience import Ambience, AmbientOut, ambient_targets

RATE = 22050
VOICE = voices.SV_VOICE            # svensk röst
RU_VOICE = voices.RU_VOICE         # rysk röst: läser bara de ryska fraserna (sim/russian.py)

# Talhastighet (ord/min) per roll – alla talar med samma röst men i olika takt.
ROLE_RATE = {
    "sonar": 165,                  # lågmält och noggrant
    "navigator": 175,
    "plot": 180,
    "officer": 180,
    "starpom": 170,                # lugn, van
    "radio": 190,
    "torpedo": 195,
    "engineer": 200,
}
DEFAULT_RATE = 180

# Larmljud per rapporttyp. Övriga larmrapporter får "attention".
CUE_BY_TYPE = {
    # revun: vakthavande blåser stridslarm (boevaja trevoga)
    "off.battle_stations": "revun",
    # stridslarm: fienden har gått till anfall
    "sonar.ping.first": "general",
    "sonar.ping.fast": "general",
    "sonar.splash": "general",
    "sonar.nuclear": "general",
    "sonar.torpedo": "general",
    "sonar.doors": "attention",
    # haverilarm
    "eng.blow": "klaxon",
    "reactor.scram": "klaxon",
    "damage": "klaxon",
    "ice.collision": "klaxon",
    "surfaced": "klaxon",
    # brandlarm
    "fire": "fire",
    # snabbtelefonen i hytten och ordonnansen som knackar
    "xo.ring": "phone",
    "xo.orderly": "knock",
    "xo.danger": "attention",
    # radiomannen vrider in Moskva på kortvåg
    "radio.moscow": "shortwave",
    "radio.moscow.silent": "shortwave",
}

# Hydrofonljud: SoundHeard.kind -> (ljud, signalöverskott i dB som ger full volym).
TRANSIENT_SOUND = {
    "ping": ("ping", 60.0),
    "buoy_ping": ("buoy_ping", 40.0),
    "buoy": ("splash", 30.0),
    "splash": ("splash", 40.0),
    "explosion": ("explosion", 120.0),
    "breakup": ("breakup", 40.0),
    "uwt": ("uwt", 30.0),
    "ice": ("ice", 25.0),
    "launch": ("launch", 30.0),
}
NUCLEAR_SE = 160.0                 # som sonarrummet: starkare än så är en kärnladdning
OWN_SOUND = {"ping": "own_ping", "launch": "launch", "decoy": "decoy", "blow": "blow"}
MIN_VOLUME = 0.2                   # svagaste hörbara transient
PAN_STEPS = 9                      # stereolägen från vänster till höger
SAME_SOUND_S = 0.3                 # samma ljud tätare än så spelas en gång (tidskomprimering)

MAX_QUEUE = 4                      # fler väntande repliker än så: släpp de oviktiga
STALE_S = 12.0                     # oviktiga repliker som väntat längre släpps
MUFFLED_STALE_S = 4.0              # mumlet genom skottet är bara stämning: släpps fortare


# --------------------------------------------------------------------------- uppspelning
class Player(Protocol):
    def play(self, cue: str, pan: float = 0.0, volume: float = 1.0) -> float:
        """Spela ett ljud utan att vänta. pan -1 (vänster) … 1 (höger), volume 0 … 1.
        Returnerar längden i sekunder."""

    def speak(self, text: str, rate: int, voice: str | None = None) -> None:
        """Börja läsa upp text utan att vänta. voice None: spelarens svenska röst.
        En spelare med `effects = True` tar också effect ("phone", "muffled")."""

    def speaking(self) -> bool: ...

    def stop(self) -> None: ...


class NullPlayer:
    """Tystnad (--tyst, eller utan macOS-verktygen)."""

    def play(self, cue: str, pan: float = 0.0, volume: float = 1.0) -> float:
        return 0.0

    def speak(self, text: str, rate: int, voice: str | None = None) -> None:
        pass

    def speaking(self) -> bool:
        return False

    def stop(self) -> None:
        pass


class MacPlayer:
    """Spelar ljuden med afplay och talet genom rösterna (`voices.backend()`). Ljuden
    syntetiseras vid start; stereofilerna skrivs första gången ett panoreringsläge behövs."""

    MAX_SOUNDS = 6                 # samtidiga ljud

    def __init__(self, cache_dir: Path | None = None, voice: str = VOICE,
                 volume: float = 0.6):
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "k114-ljud"
        self.voice = voice
        self.volume = volume
        self.samples = {**synth_cues(), **synth_transients()}
        self._files: dict[tuple[str, int], Path] = {}
        self._speech: voices.Speaking | None = None
        self._sounds: list[subprocess.Popen] = []

    @staticmethod
    def available() -> bool:
        return voices.backend().available() and shutil.which("afplay") is not None

    def _file(self, cue: str, step: int) -> Path:
        key = (cue, step)
        if key not in self._files:
            path = self.cache_dir / f"{cue}-{step}.wav"
            write_wav(path, stereo(self.samples[cue], pan_of_step(step)))
            self._files[key] = path
        return self._files[key]

    def play(self, cue: str, pan: float = 0.0, volume: float = 1.0) -> float:
        if cue not in self.samples:
            return 0.0
        self._sounds = [p for p in self._sounds if p.poll() is None]
        if len(self._sounds) >= self.MAX_SOUNDS:
            return 0.0
        path = self._file(cue, pan_step(pan))
        self._sounds.append(subprocess.Popen(
            ["afplay", "-v", f"{self.volume * volume:.2f}", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        return len(self.samples[cue]) / RATE

    def speak(self, text: str, rate: int, voice: str | None = None) -> None:
        self._speech = voices.backend().start(text, voice or self.voice, rate)

    def speaking(self) -> bool:
        return self._speech is not None and self._speech.poll() is None

    def stop(self) -> None:
        for p in [self._speech, *self._sounds]:
            if p is not None and p.poll() is None:
                p.terminate()
        self._speech = None
        self._sounds = []


class MixPlayer:
    """Allt ljud genom mixern (sounddevice), inga egna processer. Ljuden panoreras i mixern och
    talet renderas av rösterna (`voices.backend().render`, i processen på macOS) i en egen
    tråd och spelas som ett enstaka ljud. Därför kan repliker filtreras: `effect` "phone"
    (stationer utanför centralen, starpom i telefonen) och "muffled" (centralen genom skottet
    till hytten)."""

    MAX_SOUNDS = 6                 # samtidiga ljud (repliken oräknad)
    effects = True                 # SoundBoard: kan spela repliker med effekt

    def __init__(self, mixer: Ambience, synth: voices.Voices | None = None, voice: str = VOICE,
                 volume: float = 0.6, speech_gain: float = 1.0):
        import queue
        self.mixer = mixer
        self.synth = synth or voices.backend()
        self.voice = voice
        # Mixerns huvudvolym gäller allt; ljud och tal hålls i samma styrka som med afplay/say.
        self.volume = volume / max(0.05, mixer.volume)
        self.speech_gain = speech_gain / max(0.05, mixer.volume)
        self.samples = {**synth_cues(), **synth_transients()}
        self._jobs: queue.Queue = queue.Queue()
        self._want = 0                 # repliken som ska höras (0: ingen)
        self._rendering = 0            # repliken som renderas just nu
        self._lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True, name="repliker").start()

    def play(self, cue: str, pan: float = 0.0, volume: float = 1.0) -> float:
        if cue not in self.samples:
            return 0.0
        if self.mixer.shots() >= self.MAX_SOUNDS:
            return 0.0
        self.mixer.oneshot(stereo(self.samples[cue], pan), self.volume * volume, tag="cue")
        return len(self.samples[cue]) / RATE

    def speak(self, text: str, rate: int, voice: str | None = None,
              effect: str | None = None) -> None:
        with self._lock:
            self._want += 1
            n = self._want
            self._rendering = n
        self._jobs.put((n, text, voice or self.voice, rate, effect))

    def speaking(self) -> bool:
        with self._lock:
            n, rendering = self._want, self._rendering
        return n != 0 and (rendering == n or self.mixer.playing(("tal", n)))

    def stop(self) -> None:
        with self._lock:
            self._want += 1            # repliker som renderas nu kastas
            self._rendering = 0
        self.mixer.stop_shots()

    def _work(self) -> None:
        while True:
            n, text, voice, rate, effect = self._jobs.get()
            with self._lock:
                stale = n != self._want
            x = None if stale else self.synth.render(text, voice, rate, RATE)
            with self._lock:
                if x is not None and n == self._want and len(x):
                    x = apply_effect(x, effect, seed=n)
                    gain = self.speech_gain * EFFECT_GAIN.get(effect, 1.0)
                    self.mixer.oneshot(x, gain, tag=("tal", n))
                if self._rendering == n:
                    self._rendering = 0


# --------------------------------------------------------------------------- styrning
@dataclass
class Line:
    parts: list[tuple[str | None, str]]   # (röst, text) i tur och ordning; None = svenska
    rate: int
    urgent: bool
    queued_at: float
    not_before: float = 0.0
    effect: str | None = None             # "phone", "muffled" (bara MixPlayer)

    @property
    def text(self) -> str:
        return " ".join(t for _, t in self.parts)


@dataclass
class SoundBoard:
    """Gör ljud av besättningens rapporter och det sonaren hör.

    heading: egen kurs (gyrot) för att räkna relativ bäring; utan den
    spelas alla ljud mitt i.
    """
    bus: EventBus
    player: Player
    speech: bool = True
    enabled: bool = True
    heading: Callable[[], float] | None = None
    ru_voice: str | None = None    # rysk röst, annars läser den svenska rösten translittereringen
    language: str = "ru"           # "ru": allt tal på ryska (kräver ru_voice), "sv": svenska
    ambience: Ambience | None = None
    out: AmbientOut | None = None
    queue: list[Line] = field(default_factory=list)
    _parts: list[tuple[str | None, str]] = field(default_factory=list)   # resten av repliken
    _rate: int = DEFAULT_RATE
    _effect: str | None = None          # repliken som läses: dess effekt
    _now: float = 0.0
    _cue_until: float = 0.0
    _last_played: dict[str, float] = field(default_factory=dict)
    _half_hour: int | None = None       # senaste halvtimmen klockan slagit (eller sett)
    _status = None                      # senaste StatusSnapshot (var kaptenen är)

    def __post_init__(self) -> None:
        self.bus.subscribe(ReportDelivered, self._on_report)
        self.bus.subscribe(SoundHeard, self._on_sound)
        self.bus.subscribe(OwnSoundMade, self._on_own_sound)

    # -- bakgrundsljud --------------------------------------------------------
    def ambient(self, status, tracks=()) -> None:
        """Uppdatera bakgrundsljudet ur statusraden och kontaktspåren (kunskap)."""
        self._status = status
        if status is not None and not status.over:
            self._ship_bell(status)
        if self.ambience is None:
            return
        if status is None or status.over:
            self.ambience.set_targets({})
        else:
            self.ambience.set_targets(ambient_targets(status, tracks))

    def _ship_bell(self, status) -> None:
        """Vid varje hel och halv timme slår klockan glasen, utom vid tyst gång och jakt."""
        half = status.clock // 1800
        if self._half_hour is None or half == self._half_hour:
            self._half_hour = half
            return
        self._half_hour = half
        if self.enabled and status.propulsion != "electric" and not status.hunted:
            self.player.play(f"bells{bells_for(status.clock)}", 0.0, 0.6)

    def announce(self, ru: str, sv: str) -> None:
        """Högtalarutrop till besättningen (vakthavande): ryska med den ryska rösten, annars svenska."""
        if not self.enabled or not self.speech:
            return
        parts = [(self.ru_voice, ru)] if self.speaks_russian else [(None, speech_text(sv))]
        self.queue.append(Line(parts, ROLE_RATE["officer"], urgent=True, queued_at=self._now,
                               not_before=self._now + 1.0))

    # -- hydrofonen ----------------------------------------------------------
    def _play_once(self, cue: str, pan: float = 0.0, volume: float = 1.0) -> None:
        if self._now - self._last_played.get(cue, -1e9) < SAME_SOUND_S:
            return
        self._last_played[cue] = self._now
        self.player.play(cue, pan, volume)

    def _on_sound(self, e: SoundHeard) -> None:
        if not self.enabled or e.kind not in TRANSIENT_SOUND:
            return
        cue, full_se = TRANSIENT_SOUND[e.kind]
        if e.kind == "explosion" and e.se > NUCLEAR_SE:
            cue = "nuclear"
        rel = e.bearing - self.heading() if self.heading else 0.0
        self._play_once(cue, pan_of_bearing(rel), volume_of(e.se, full_se))

    def _on_own_sound(self, e: OwnSoundMade) -> None:
        if self.enabled and e.kind in OWN_SOUND:
            self._play_once(OWN_SOUND[e.kind])

    # -- rapporter -----------------------------------------------------------
    def _on_report(self, e: ReportDelivered) -> None:
        if not self.enabled:
            return
        r = e.report
        effects = getattr(self.player, "effects", False)
        effect = speech_effect(r, self._status) if effects else None
        if self._status is not None and from_central(r, self._status) and not effects:
            return                  # i hytten hörs centralen inte (utan mixern: inte alls)
        cue = cue_for(r)
        delay = 0.0
        if cue:
            length = self.player.play(cue)
            # Talet börjar när larmet nästan har klingat av.
            delay = length * 0.7 if cue in ("general", "klaxon", "fire", "revun") else length * 0.5
            self._cue_until = max(self._cue_until, self._now + delay)
        if not self.speech or not spoken(r):
            return
        if self.speaks_russian and r.speech:
            parts: list[tuple[str | None, str]] = [(self.ru_voice, r.speech)]
        else:
            text = r.text
            if r.data.get("read_aloud"):
                text += " " + r.data["read_aloud"]
            parts = speech_parts(text, self.ru_voice)
        line = Line(parts, ROLE_RATE.get(r.role, DEFAULT_RATE),
                    urgent=(r.alarm or r.kind == "suggest") and effect != "muffled",
                    queued_at=self._now, not_before=self._now + delay, effect=effect)
        self.queue.append(line)
        self._trim()

    def _trim(self) -> None:
        """Håll kön kort: vid tidskomprimering hinner ingen säga allt."""
        self.queue = [ln for ln in self.queue
                      if ln.urgent or self._now - ln.queued_at <
                      (MUFFLED_STALE_S if ln.effect == "muffled" else STALE_S)]
        while len(self.queue) > MAX_QUEUE:
            routine = [ln for ln in self.queue if not ln.urgent]
            self.queue.remove(routine[0] if routine else self.queue[0])

    # -- varje bildruta ------------------------------------------------------
    def update(self, now: float) -> None:
        """now: monoton realtid i sekunder."""
        self._now = now
        if not self.enabled:
            return
        if self._parts:                              # repliken fortsätter med nästa röst
            if not self.player.speaking():
                voice, text = self._parts.pop(0)
                self._speak(text, self._rate, voice)
            return
        if not self.queue:
            return
        self._trim()
        if not self.queue or self.player.speaking() or \
                now < max(self.queue[0].not_before, self._cue_until):
            return
        line = self.queue.pop(0)
        (voice, text), *self._parts = line.parts
        self._rate = line.rate
        self._effect = line.effect
        self._speak(text, line.rate, voice)

    def _speak(self, text: str, rate: int, voice: str | None) -> None:
        if self._effect is not None:
            self.player.speak(text, rate, voice, effect=self._effect)
        else:
            self.player.speak(text, rate, voice)

    @property
    def speaks_russian(self) -> bool:
        return self.language == "ru" and self.ru_voice is not None

    def set_language(self, language: str) -> bool:
        """'ru' eller 'sv'. Returnerar om besättningen nu talar ryska."""
        self.language = language
        return self.speaks_russian

    @property
    def available(self) -> bool:
        """Finns något att spela med (inte --tyst eller saknade verktyg)?"""
        return not isinstance(self.player, NullPlayer)

    def toggle(self) -> bool:
        """Slå av eller på ljudet. Returnerar det nya läget."""
        self.enabled = not self.enabled
        if self.ambience is not None:
            self.ambience.enabled = self.enabled
        if not self.enabled:
            self.queue.clear()
            self._parts = []
            self.player.stop()
        return self.enabled

    def close(self) -> None:
        self.bus.unsubscribe(ReportDelivered, self._on_report)
        self.bus.unsubscribe(SoundHeard, self._on_sound)
        self.bus.unsubscribe(OwnSoundMade, self._on_own_sound)
        self.queue.clear()
        self._parts = []
        self.player.stop()
        if self.out is not None:
            self.out.close()


def pan_of_bearing(relative: float) -> float:
    """Relativ bäring -> stereoläge. Rakt för/akter i mitten, babord till vänster."""
    return float(np.sin(np.radians(relative)))


def pan_step(pan: float) -> int:
    return int(round((max(-1.0, min(1.0, pan)) + 1) / 2 * (PAN_STEPS - 1)))


def pan_of_step(step: int) -> float:
    return step / (PAN_STEPS - 1) * 2 - 1


def volume_of(se: float, full_se: float) -> float:
    return MIN_VOLUME + (1 - MIN_VOLUME) * max(0.0, min(1.0, se / full_se))


def stereo(mono: np.ndarray, pan: float) -> np.ndarray:
    """Panorering med konstant effekt: (n, 2)."""
    a = (pan + 1) * np.pi / 4
    return np.stack([mono * np.cos(a), mono * np.sin(a)], axis=1) * np.sqrt(2) / 2 * 1.4


# --------------------------------------------------------------------------- effekter på talet
# Stationer utanför centralen hörs genom högtalartelefonen ("Kashtan"); starpom ringer till
# hytten. I hytten hörs centralen dämpad genom skottet: man hör att någon talar, inte vad.
REMOTE_ROLES = ("sonar", "torpedo", "engineer", "radio")
EFFECT_GAIN = {"phone": 0.9, "muffled": 0.35}


def _filtered(x: np.ndarray, gain_of_f) -> np.ndarray:
    pad = int(RATE * 0.05)
    y = np.concatenate([x, np.zeros(pad)])         # plats för filtrets svans
    f = np.fft.rfftfreq(len(y), 1 / RATE)
    return np.fft.irfft(np.fft.rfft(y) * gain_of_f(f), len(y))


def phone_voice(x: np.ndarray, seed: int = 0) -> np.ndarray:
    """Högtalartelefon: smalt band 300–3000 Hz, lätt överstyrd, svagt sus."""
    def band(f):
        return np.clip((f - 200) / 150, 0, 1) * np.clip((3400 - f) / 500, 0, 1)
    y = _filtered(x, band)
    y = np.tanh(2.2 * _norm(y, 1.0)) / np.tanh(2.2)
    hiss = 0.015 * np.random.default_rng(seed).standard_normal(len(y))
    return _norm(y + hiss, 0.7)


def muffled_voice(x: np.ndarray) -> np.ndarray:
    """Genom skottet: bara det låga kommer igenom."""
    y = _filtered(x, lambda f: 1 / (1 + (f / 320) ** 4))
    return _norm(y, 0.6)


def apply_effect(x: np.ndarray, effect: str | None, seed: int = 0) -> np.ndarray:
    if effect == "phone":
        return phone_voice(x, seed)
    if effect == "muffled":
        return muffled_voice(x)
    return x


def speech_effect(r: Report, status) -> str | None:
    """Hur repliken låter där kaptenen är: i hytten centralen dämpad och starpom i telefonen,
    i centralen stationerna utanför i högtalartelefonen."""
    if status is None or r.alarm:
        return None
    cabin = getattr(status, "command", "captain") == "starpom" and \
        getattr(status, "captain_at", "central") == "cabin"
    if cabin:
        if r.role == "starpom":
            return "phone"
        return "muffled" if from_central(r, status) else None
    return "phone" if r.role in REMOTE_ROLES else None


def cue_for(r: Report) -> str | None:
    if r.type in CUE_BY_TYPE:
        return CUE_BY_TYPE[r.type]
    if r.alarm:
        return "attention"
    if r.kind == "suggest" and r.data.get("order"):
        return "suggest"
    return None


def from_central(r: Report, status) -> bool:
    """Kaptenen är i hytten och rapporten är centralens (inte starpom, telefonen eller ett larm):
    den står i loggboken men hörs inte."""
    if getattr(status, "command", "captain") != "starpom" or \
            getattr(status, "captain_at", "central") != "cabin":
        return False
    return r.role not in ("starpom", "") and not r.alarm


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


def speech_parts(text: str, ru_voice: str | None) -> list[tuple[str | None, str]]:
    """Repliken i delar per röst: de ryska fraserna med den ryska rösten (kyrilliskt),
    resten med den svenska. Utan rysk röst läser den svenska allt."""
    if ru_voice is None:
        return [(None, speech_text(text))]
    return [(ru_voice, t) if lang == "ru" else (None, speech_text(t))
            for lang, t in segments(text)] or [(None, speech_text(text))]


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


def synth_revun() -> np.ndarray:
    """Revun: elektromekanisk tjutsiren. Motorn varvar upp och tonen stiger,
    membranet surrar; två långa tjut."""
    blast_s, gap_s = 1.25, 0.2
    t = _t(blast_s)
    f = 150 + 95 * (1 - np.exp(-t / 0.3)) - 25 * np.maximum(0.0, t - blast_s + 0.2) / 0.2
    phase = 2 * np.pi * np.cumsum(f) / RATE
    saw = sum(np.sin(k * phase) / k for k in range(1, 9))          # rik, hes ton
    buzz = 1 + 0.25 * np.sin(2 * np.pi * 31 * t)                   # membranet surrar
    env = np.minimum(1.0, t / 0.12) * np.minimum(1.0, (blast_s - t) / 0.18)
    blast = saw * buzz * env
    out = np.zeros(int(RATE * (2 * blast_s + gap_s)))
    for k in range(2):
        a = int(RATE * k * (blast_s + gap_s))
        out[a:a + len(blast)] += blast
    return 0.75 * _speaker(_lowpass(out, 2600), 1.8)


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


def synth_phone() -> np.ndarray:
    """Snabbtelefonen «Каштан»: ett surrande anrop, två gånger."""
    t = _t(0.45)
    buzz = np.sign(np.sin(2 * np.pi * 420 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 25 * t))
    burst = _speaker(buzz * np.minimum(1.0, t / 0.01) * np.minimum(1.0, (0.45 - t) / 0.02), 1.0)
    gap = np.zeros(int(RATE * 0.25))
    return 0.35 * np.concatenate([burst, gap, burst])


def synth_knock() -> np.ndarray:
    """Ordonnansen knackar på hyttdörren: tre dova slag i stål."""
    t = _t(0.18)
    hit = (np.sin(2 * np.pi * 140 * t) + 0.5 * np.sin(2 * np.pi * 310 * t)) * np.exp(-t * 30)
    gap = np.zeros(int(RATE * 0.12))
    return 0.6 * _speaker(np.concatenate([hit, gap, hit, gap, hit]), 1.5)


def synth_ship_bell(strikes: int) -> np.ndarray:
    """Skeppsklockan slår glasen (склянки): slagen två och två, ett ensamt sist vid udda tal."""
    t = _t(1.6)
    partials = ((1.0, 1.0, 2.0), (2.0, 0.5, 3.0), (2.76, 0.35, 4.0), (5.4, 0.15, 6.0))
    strike = sum(a * np.sin(2 * np.pi * 1180 * k * t) * np.exp(-t * d) for k, a, d in partials)
    strike = strike * np.minimum(1.0, t / 0.002)
    starts, at = [], 0.0
    for i in range(strikes):
        starts.append(at)
        at += 0.32 if i % 2 == 0 else 0.95
    out = np.zeros(int(RATE * (starts[-1] + 1.6)) + 1)
    for a in starts:
        i = int(a * RATE)
        out[i:i + len(strike)] += strike[: len(out) - i]
    return 0.45 * out / max(1e-9, float(np.max(np.abs(out))))


def synth_shortwave() -> np.ndarray:
    """Kortvågsmottagaren: ratten vrids, visslingar och brus (samma som i menyns radio)."""
    from .menu_audio import synth_static, synth_tuning
    return 0.6 * np.concatenate([synth_tuning(), synth_static()[: RATE]])


def bells_for(clock: int) -> int:
    """Hur många glas klockan slår vid en halvtimme: 1–8 under varje fyratimmarsvakt."""
    return (clock // 1800) % 8 or 8


def synth_cues() -> dict[str, np.ndarray]:
    cues = {"general": synth_general(), "klaxon": synth_klaxon(), "fire": synth_fire(),
            "revun": synth_revun(),
            "attention": synth_attention(), "suggest": synth_suggest(),
            "phone": synth_phone(), "knock": synth_knock()}
    cues.update({f"bells{n}": synth_ship_bell(n) for n in range(1, 9)})
    cues["shortwave"] = synth_shortwave()
    return cues


def write_wav(path: Path, samples: np.ndarray) -> None:
    """Mono (n,) eller stereo (n, 2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1 if samples.ndim == 1 else samples.shape[1])
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


# -- hydrofonljud -------------------------------------------------------------
# Brus ur en fast seedad generator: samma ljud varje gång, ingen spelslump.
def _noise(seconds: float, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(int(RATE * seconds))


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Enpoligt lågpassfilter."""
    a = np.exp(-2 * np.pi * cutoff / RATE)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def _norm(x: np.ndarray, peak: float) -> np.ndarray:
    return peak * x / max(1e-9, float(np.max(np.abs(x))))


def _fade(x: np.ndarray, fade_in: float = 0.005, fade_out: float = 0.05) -> np.ndarray:
    n = len(x)
    t = np.arange(n) / RATE
    return x * np.minimum(1.0, t / fade_in) * np.minimum(1.0, (n / RATE - t) / fade_out)


def _reverb(dry: np.ndarray, seconds: float, decay: float, cutoff: float, seed: int,
            mix: float = 0.35) -> np.ndarray:
    """Havets efterklang: avklingande, filtrerat brus format efter ljudet."""
    tail = _lowpass(_noise(seconds, seed), cutoff) * np.exp(-_t(seconds) * decay)
    wet = np.convolve(dry, tail)[: len(dry) + len(tail)]
    out = np.zeros(len(wet))
    out[: len(dry)] += dry
    return out + mix * _norm(wet, float(np.max(np.abs(dry))))


def synth_ping() -> np.ndarray:
    """Jagarens sonar: en lång, ren ton som ekar ut."""
    t = _t(0.55)
    tone = np.sin(2 * np.pi * 3500 * t) * np.minimum(1.0, t / 0.01) * np.minimum(1.0, (0.55 - t) / 0.08)
    out = _reverb(tone, 1.8, 2.2, 3800, seed=1)
    return _fade(_norm(out, 0.7), fade_out=0.3)


def synth_own_ping() -> np.ndarray:
    """Vår egen ping: kortare, lägre, med en smäll i skrovet."""
    t = _t(0.35)
    tone = np.sin(2 * np.pi * 2600 * t) * np.minimum(1.0, t / 0.005) * np.exp(-t * 3)
    thump = np.sin(2 * np.pi * 90 * t) * np.exp(-t * 25)
    out = _reverb(tone + 0.6 * thump, 1.2, 3.0, 3000, seed=2)
    return _fade(_norm(out, 0.8), fade_out=0.2)


def synth_buoy_ping() -> np.ndarray:
    """Aktiv boj: tunt och metalliskt."""
    t = _t(0.16)
    tone = (np.sin(2 * np.pi * 8200 * t) + 0.4 * np.sin(2 * np.pi * 11300 * t)) * np.exp(-t * 12)
    out = _reverb(tone, 0.9, 4.0, 7000, seed=3, mix=0.25)
    return _fade(_norm(out, 0.6), fade_out=0.15)


def synth_splash() -> np.ndarray:
    """Något slår i vattnet ovanför: plask och bubbel."""
    n = _noise(0.9, 4)
    t = _t(0.9)
    body = _lowpass(n, 1800) * np.exp(-t * 6)
    bubbles = sum(np.sin(2 * np.pi * f * t) * np.exp(-((t - d) * 30) ** 2)
                  for f, d in ((420, 0.15), (610, 0.22), (350, 0.31), (520, 0.4)))
    return _fade(_norm(body + 0.3 * bubbles, 0.7))


def _boom(seconds: float, seed: int, decay: float, cutoff: float) -> np.ndarray:
    t = _t(seconds)
    rumble = _lowpass(_lowpass(_noise(seconds, seed), cutoff), cutoff)
    rumble = _norm(rumble, 1.0) * np.exp(-t * decay)
    thud = np.sin(2 * np.pi * (55 - 20 * np.minimum(t, 1.0)) * t) * np.exp(-t * decay * 1.5)
    attack = _lowpass(_noise(seconds, seed + 1), 2500) * np.exp(-t * 40)
    return rumble + 0.8 * thud + 0.5 * _norm(attack, 1.0)


def synth_explosion() -> np.ndarray:
    """Sjunkbomb eller torped: dov smäll som mullrar ut."""
    return _fade(_speaker(_boom(2.8, 5, 1.6, 300), 1.8) * 0.9, fade_out=0.4)


def synth_nuclear() -> np.ndarray:
    """Kärnladdning: ett tryck som aldrig tar slut."""
    return _fade(_speaker(_boom(5.5, 7, 0.7, 180), 2.5) * 1.0, fade_out=1.0)


def synth_breakup() -> np.ndarray:
    """Ett skrov som går sönder: knak, gnissel och dova smällar."""
    secs = 4.0
    t = _t(secs)
    rng = np.random.default_rng(9)
    out = np.zeros(len(t))
    for _ in range(14):                          # gnisslande plåt
        start, dur = rng.uniform(0, 3.2), rng.uniform(0.2, 0.7)
        f0, f1 = rng.uniform(80, 220), rng.uniform(40, 160)
        seg = _t(dur)
        f = f0 + (f1 - f0) * seg / dur
        groan = np.sign(np.sin(2 * np.pi * np.cumsum(f) / RATE)) * np.sin(np.pi * seg / dur)
        a = int(start * RATE)
        out[a:a + len(seg)] += groan[: len(out) - a] * rng.uniform(0.3, 0.8)
    for _ in range(5):                           # skott inne i skrovet
        a = int(rng.uniform(0, 3.5) * RATE)
        bang = _boom(0.4, int(rng.integers(100, 200)), 10, 400)
        out[a:a + len(bang)] += bang[: len(out) - a] * 0.8
    return _fade(_norm(_lowpass(out, 1200), 0.7), fade_out=0.6)


def synth_uwt() -> np.ndarray:
    """Undervattenstelefon: morse på en darrig bärare."""
    pattern = "-.-.  --.-"                       # bara ett mönster, inget meddelande
    dot = 0.08
    parts = []
    for c in pattern:
        n = {".": 1, "-": 3, " ": 0}[c]
        if n:
            t = _t(dot * n)
            f = 1500 + 30 * np.sin(2 * np.pi * 6 * t)
            parts.append(np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.minimum(1.0, t / 0.005))
        parts.append(np.zeros(int(RATE * dot * (1 if n else 2))))
    tone = np.concatenate(parts)
    out = tone + 0.15 * _lowpass(_noise(len(tone) / RATE, 10), 3000)
    return _fade(_norm(out, 0.5))


def synth_ice() -> np.ndarray:
    """Isen knakar."""
    t = _t(0.7)
    rng = np.random.default_rng(11)
    out = np.zeros(len(t))
    for _ in range(9):
        a = int(rng.uniform(0, 0.55) * RATE)
        click = _noise(0.03, int(rng.integers(20, 90))) * np.exp(-_t(0.03) * 120)
        out[a:a + len(click)] += click * rng.uniform(0.3, 1.0)
    return _fade(_norm(_reverb(_lowpass(out, 2500), 0.5, 6, 2000, seed=12), 0.6))


def _air(seconds: float, seed: int, cutoff: float) -> np.ndarray:
    t = _t(seconds)
    return _lowpass(_noise(seconds, seed), cutoff) * np.minimum(1.0, t / 0.03)


def synth_launch() -> np.ndarray:
    """Avfyring: tryckluftsstöt, ett väsande och torpeden som drar iväg."""
    secs = 2.0
    t = _t(secs)
    thump = np.sin(2 * np.pi * 45 * t) * np.exp(-t * 8)
    whoosh = _air(secs, 13, 1500) * np.exp(-t * 2.2)
    motor = np.sin(2 * np.pi * (180 + 60 * t) * t) * np.minimum(1.0, t / 0.6) * np.exp(-t * 1.5)
    return _fade(_norm(1.2 * thump + _norm(whoosh, 1.0) + 0.25 * motor, 0.8), fade_out=0.4)


def synth_decoy() -> np.ndarray:
    """Skenmål: en liten stöt och bubbel."""
    t = _t(1.0)
    thump = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 14)
    fizz = _air(1.0, 14, 4000) * np.exp(-t * 3)
    return _fade(_norm(thump + 0.5 * _norm(fizz, 1.0), 0.6), fade_out=0.3)


def synth_blow() -> np.ndarray:
    """Nödblåsning: högtrycksluft vräker in i tankarna."""
    secs = 3.5
    t = _t(secs)
    roar = _air(secs, 15, 900) * np.minimum(1.0, (secs - t) / 1.2)
    hiss = _air(secs, 16, 5000) * 0.4 * np.exp(-t * 0.5)
    return _fade(_norm(_norm(roar, 1.0) + hiss, 0.8), fade_out=0.6)


def synth_transients() -> dict[str, np.ndarray]:
    return {"ping": synth_ping(), "own_ping": synth_own_ping(),
            "buoy_ping": synth_buoy_ping(), "splash": synth_splash(),
            "explosion": synth_explosion(), "nuclear": synth_nuclear(),
            "breakup": synth_breakup(), "uwt": synth_uwt(), "ice": synth_ice(),
            "launch": synth_launch(), "decoy": synth_decoy(), "blow": synth_blow()}


def make_soundboard(bus: EventBus, enabled: bool,
                    heading: Callable[[], float] | None = None) -> tuple[SoundBoard, str | None]:
    """Koppla ljud till spelet. Returnerar (ljudbord, meddelande till kaptenen eller None)."""
    if not enabled:
        return SoundBoard(bus, NullPlayer(), enabled=False), None
    if not MacPlayer.available():
        return SoundBoard(bus, NullPlayer(), enabled=False), \
            "Ljud saknas: kräver macOS (say och afplay)."
    ambience = Ambience()
    out = AmbientOut(ambience)
    notes = []
    if out.error:
        notes.append("Bakgrundsljudet kunde inte startas.")
    speech = voices.backend().voice("sv") is not None
    ru_voice = voices.backend().voice("ru") if speech else None
    if not speech:
        notes.append(f"Rösten {VOICE} saknas, besättningen hörs inte. Lägg till den under "
                     "Systeminställningar › Hjälpmedel › Talat innehåll › Systemröst.")
    synth = voices.backend()
    if out.stream is not None and isinstance(synth, voices.MacSynth):
        # Allt genom mixern; rösterna laddas nu så att första repliken inte dröjer.
        synth.warm_up(*(v for v in (VOICE, ru_voice) if v and speech))
        player: Player = MixPlayer(ambience, synth)
    else:
        player = MacPlayer()
    board = SoundBoard(bus, player, speech=speech, heading=heading, ru_voice=ru_voice,
                       ambience=ambience, out=out)
    return board, " ".join(notes) or None
