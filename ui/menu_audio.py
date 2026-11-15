"""Huvudmenyns ljud: musik, hamnen i Poljarnyj och fjärrskrivaren.

Allt syntetiseras med numpy och spelas genom samma mixer som båtens bakgrundsljud
(`ambience.Ambience` via sounddevice), så det fungerar utan ljudfiler. Musiken är
skriven för spelet: en långsam kör i d-moll över ett hjärtslag i basen, en klocka
och, andra varvet, ett horn. Slingorna är cirkulära (efterklangen viks runt) så att
de går runt utan skarv.

    synth_menu()     {"music", "harbor", "teleprinter"}: slingor
    synth_oneshots() {"telegraph"}: enstaka ljud
    MenuMixer        Ambience med enstaka ljud ovanpå slingorna
    MenuSound        menyns ljud: start, fjärrskrivaren, avfärd, stäng
"""
from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np

from .ambience import RATE, Ambience, AmbientOut

MUSIC_BEAT_S = 1.0          # 60 slag i minuten
MUSIC_BARS = 16             # 4/4, alltså 64 s
CHORD_BARS = 2
HARBOR_S = 40.0
TELEPRINTER_S = 4.0

GAIN = {"music": 0.55, "harbor": 0.4, "teleprinter": 0.14}


def midi(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


# --------------------------------------------------------------------------- byggstenar
def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _spectral(x: np.ndarray, gain_of_f) -> np.ndarray:
    """Filtrera cirkulärt i frekvensplanet: gain_of_f(f) -> förstärkning."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    return np.fft.irfft(spec * gain_of_f(f), len(x))


def _band(lo: float, hi: float, tilt: float = 0.0):
    def g(f):
        f = np.maximum(f, 1.0)
        edge = np.clip((f - lo * 0.7) / (lo * 0.3), 0, 1) * np.clip((hi * 1.3 - f) / (hi * 0.3), 0, 1)
        return edge * (f / lo) ** (tilt / 6.02)
    return g


def _noise(n: int, seed: int, lo: float, hi: float, tilt: float = 0.0) -> np.ndarray:
    return _norm(_spectral(_rng(seed).standard_normal(n), _band(lo, hi, tilt)))


def _norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    return peak * x / max(1e-9, float(np.max(np.abs(x))))


def _reverb(x: np.ndarray, seconds: float, cutoff: float, mix: float, seed: int) -> np.ndarray:
    """Efterklang som viks runt slingan: avklingande brus, faltat i frekvensplanet."""
    n = len(x)
    m = int(RATE * seconds)
    tail = _rng(seed).standard_normal(m) * np.exp(-np.arange(m) / (m / 5))
    ir = np.zeros(n)
    ir[:m] = tail
    f = np.fft.rfftfreq(n, 1 / RATE)
    wet = np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(ir) / (1 + (f / cutoff) ** 2), n)
    return x + mix * _norm(wet, float(np.max(np.abs(x))))


def _place(out: np.ndarray, snd: np.ndarray, at: float) -> None:
    """Lägg ett ljud i slingan med start at sekunder; det som går över kanten viks runt."""
    n = len(out)
    a = int(at * RATE) % n
    pos = 0
    while pos < len(snd):
        k = min(len(snd) - pos, n - a)
        out[a:a + k] += snd[pos:pos + k]
        pos += k
        a = 0


def _env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.arange(n) / RATE
    dur = n / RATE
    return np.minimum(1.0, t / attack) * np.clip((dur - t) / release, 0.0, 1.0)


def _wavetable(f0: float, amp_of_harmonic, size: int = 2048) -> np.ndarray:
    """En period av en klang med övertoner k·f0 under 5 kHz, styrka amp_of_harmonic(k, f)."""
    ph = 2 * np.pi * np.arange(size) / size
    table = np.zeros(size)
    for k in range(1, int(5000 / f0) + 1):
        table += amp_of_harmonic(k, k * f0) * np.sin(k * ph)
    return _norm(table)


def _play_table(table: np.ndarray, f0: float, n: int, vibrato: float, vib_hz: float,
                phase0: float, detune_cents: float = 0.0) -> np.ndarray:
    t = np.arange(n) / RATE
    vib = 1 + vibrato * np.sin(2 * np.pi * vib_hz * t + phase0) * np.minimum(1.0, t / 0.8)
    f = f0 * 2 ** (detune_cents / 1200) * vib
    pos = (np.cumsum(f) / RATE * len(table) + phase0 * len(table)) % len(table)
    i0 = pos.astype(int)
    frac = pos - i0
    return table[i0] * (1 - frac) + table[(i0 + 1) % len(table)] * frac


# --------------------------------------------------------------------------- musiken
def _formant(k: int, f: float) -> float:
    """Kör på "o": formanter vid 450, 800 och 2 800 Hz."""
    peaks = (450, 120, 1.0), (800, 150, 0.6), (2800, 300, 0.12)
    return sum(a * np.exp(-0.5 * ((f - c) / bw) ** 2) for c, bw, a in peaks) / k ** 0.4 + 0.02 / k


def _brass(k: int, f: float) -> float:
    """Horn: mjukt, med avtagande övertoner över 1 500 Hz."""
    return k ** -0.8 / (1 + (f / 1500) ** 2)


# fyra stämmor (bas, tenor, alt, sopran) per ackord, MIDI, varje ackord två takter
CHORDS = [
    (38, 57, 62, 65),        # d-moll
    (46, 53, 62, 65),        # B-dur
    (43, 55, 58, 62),        # g-moll
    (45, 57, 61, 64),        # A-dur
    (38, 57, 62, 65),        # d-moll
    (39, 55, 58, 63),        # Ess-dur: det mörka
    (43, 55, 58, 64),        # g-moll med sext
    (45, 57, 61, 64),        # A-dur, tillbaka till d
]
ROOTS = [26, 34, 31, 33, 26, 27, 31, 33]          # basens hjärtslag, en oktav under

# hornet andra varvet: (MIDI, slag) per ackord 5–8, None = paus
MELODY = [
    [(69, 3), (67, 1), (65, 2), (64, 2)],
    [(67, 2), (70, 4), (67, 2)],
    [(74, 3), (72, 1), (70, 2), (67, 2)],
    [(69, 6), (None, 2)],
]


@lru_cache(maxsize=1)
def synth_music() -> np.ndarray:
    beat = MUSIC_BEAT_S
    chord_s = 4 * CHORD_BARS * beat
    n = int(RATE * len(CHORDS) * chord_s)
    out = np.zeros(n)
    rng = _rng(71)
    tables: dict[int, np.ndarray] = {}
    # kören
    for c, voices in enumerate(CHORDS):
        seg = int(RATE * (chord_s + 1.6))
        for v, m in enumerate(voices):
            if m not in tables:
                tables[m] = _wavetable(midi(m), _formant)
            gain = (0.9, 0.7, 0.6, 0.55)[v]
            for cents in (-7.0, 6.0):
                s = _play_table(tables[m], midi(m), seg, 0.004, 5.0 + v * 0.3,
                                rng.uniform(0, 1), cents)
                _place(out, s * _env(seg, 1.4, 1.8) * gain * 0.5, c * chord_s)
    # hjärtslaget: slag 1 och 3, dovt som en trumma och en kontrabas
    for c, root in enumerate(ROOTS):
        for b in range(0, 4 * CHORD_BARS, 2):
            m = int(RATE * 1.4)
            t = np.arange(m) / RATE
            f = midi(root + 12)
            hit = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 3.0)
            thump = _noise(m, 80 + b, 40, 160) * np.exp(-t * 18)
            soft = np.minimum(1.0, t / 0.004)    # filten på klubban: inget klick
            _place(out, (hit * 0.9 + thump * 0.5) * soft * (1.0 if b == 0 else 0.6),
                   c * chord_s + b * beat)
    # pukvirvel som växer mot slutet och slår över i början
    m = int(RATE * 6.0)
    t = np.arange(m) / RATE
    roll = (_noise(m, 81, 50, 260) + 0.7 * np.sin(2 * np.pi * midi(38) * t)) * (t / 6.0) ** 2 \
        * np.clip((6.0 - t) / 0.15, 0, 1)         # slår över i första slaget utan klick
    _place(out, roll * 0.8, len(CHORDS) * chord_s - 6.0)
    # klockan, var fjärde takt i början av varje varv
    for at in (0.0, 4 * chord_s):
        _place(out, _bell(midi(50), 7.0) * 0.6, at)
    # hornet andra varvet
    horn = _wavetable(midi(67), _brass)
    for c, phrase in enumerate(MELODY):
        at = (4 + c) * chord_s
        for m_, beats in phrase:
            dur = beats * beat
            if m_ is not None:
                seg = int(RATE * (dur + 0.4))
                s = _play_table(horn, midi(m_), seg, 0.006, 5.5, 0.0)
                _place(out, s * _env(seg, 0.18, 0.5) * 0.55, at)
            at += dur
    out = _reverb(out, 3.0, 2500.0, 0.45, 72)
    return _norm(out, 0.9).astype(np.float64)


def _bell(f0: float, seconds: float) -> np.ndarray:
    """Kyrkklocka: delvis inharmoniska deltoner, mollters, lång avklingning."""
    t = np.arange(int(RATE * seconds)) / RATE
    partials = ((0.5, 0.6, 0.6), (1.0, 1.0, 1.0), (1.19, 0.5, 1.4), (1.5, 0.4, 1.8),
                (2.0, 0.35, 2.2), (2.52, 0.2, 3.0), (3.01, 0.12, 4.0))
    return _norm(sum(a * np.sin(2 * np.pi * f0 * r * t) * np.exp(-t * d / 1.5)
                     for r, a, d in partials) * np.minimum(1.0, t / 0.004))


# --------------------------------------------------------------------------- hamnen
def _creak(rng: np.random.Generator) -> np.ndarray:
    """Förtöjningar som knarrar."""
    dur = rng.uniform(0.5, 1.4)
    t = np.arange(int(RATE * dur)) / RATE
    f = rng.uniform(70, 160) * (1 + 0.3 * t / dur)
    stick = 1 + 0.8 * (np.sin(2 * np.pi * rng.uniform(12, 30) * t) > 0.5)
    s = np.sign(np.sin(2 * np.pi * np.cumsum(f) / RATE)) * stick * np.sin(np.pi * t / dur)
    return _spectral(s, _band(60, 900, -3))


@lru_cache(maxsize=1)
def synth_harbor() -> np.ndarray:
    n = int(RATE * HARBOR_S)
    t = np.arange(n) / RATE
    rng = _rng(91)
    # vind i byar: långsamma sinusar med helt antal perioder per slinga
    gust = sum(np.sin(2 * np.pi * k / HARBOR_S * t + rng.uniform(0, 6)) / k for k in (1, 2, 3, 5))
    gust = 0.55 + 0.45 * gust / np.max(np.abs(gust))
    wind = _noise(n, 92, 180, 1600, -2) * gust
    whistle = _noise(n, 93, 700, 1100) * np.clip(gust - 0.6, 0, 1) * 0.6
    # vågor mot kajen
    waves = np.zeros(n)
    at = 0.0
    while at < HARBOR_S:
        m = int(RATE * rng.uniform(1.2, 2.2))
        tt = np.arange(m) / RATE
        lap = _noise(m, int(at * 10) + 200, 90, 900, -3) * np.minimum(1, tt / 0.25) \
            * np.exp(-tt * 2.2)
        _place(waves, lap * rng.uniform(0.5, 1.0), at)
        at += rng.uniform(2.3, 4.0)
    # mistluren långt borta i fjorden
    m = int(RATE * 4.0)
    tt = np.arange(m) / RATE
    horn = sum(np.sin(2 * np.pi * 98 * k * tt) / k ** 1.3 for k in range(1, 12))
    horn = _spectral(horn * _env(m, 0.35, 0.9), _band(60, 700, -2))
    foghorn = np.zeros(n)
    _place(foghorn, _norm(horn), 21.0)
    foghorn = _reverb(foghorn, 4.0, 600.0, 1.2, 94)
    # knarr och en avlägsen bojklocka
    creaks = np.zeros(n)
    for _ in range(5):
        _place(creaks, _creak(rng) * rng.uniform(0.3, 0.8), rng.uniform(0, HARBOR_S))
    buoy = np.zeros(n)
    for at in (7.5, 9.1, 31.0):
        _place(buoy, _bell(midi(76), 3.0) * 0.5, at)
    buoy = _spectral(buoy, _band(300, 1800))
    mix = (0.55 * wind + 0.2 * whistle + 0.7 * _norm(waves) + 0.35 * _norm(foghorn)
           + 0.3 * _norm(creaks) + 0.12 * _norm(buoy))
    return _norm(_reverb(mix, 1.5, 3000.0, 0.15, 95), 0.9)


# --------------------------------------------------------------------------- fjärrskrivaren
@lru_cache(maxsize=1)
def synth_teleprinter() -> np.ndarray:
    """Typhjulet slår, motorn surrar."""
    n = int(RATE * TELEPRINTER_S)
    out = np.zeros(n)
    rng = _rng(101)
    at = 0.0
    while at < TELEPRINTER_S:
        m = int(RATE * 0.03)
        tt = np.arange(m) / RATE
        click = rng.standard_normal(m) * np.exp(-tt * 400) \
            + 0.6 * np.sin(2 * np.pi * rng.uniform(180, 260) * tt) * np.exp(-tt * 120)
        _place(out, click * rng.uniform(0.6, 1.0), at)
        at += 1 / 24 * rng.uniform(0.7, 1.3)
    out = _spectral(out, _band(150, 6000, -1))
    t = np.arange(n) / RATE
    motor = 0.08 * (np.sin(2 * np.pi * 50 * t) + 0.5 * np.sin(2 * np.pi * 100 * t))
    return _norm(_norm(out) + motor, 0.9)


def synth_telegraph() -> np.ndarray:
    """Maskintelegrafen: handtaget slår i läget och klockan ringer två gånger."""
    out = np.zeros(int(RATE * 2.2))
    m = int(RATE * 0.05)
    clack = _rng(111).standard_normal(m) * np.exp(-np.arange(m) / RATE * 120)
    _place(out, clack * 0.8, 0.0)
    for at in (0.12, 0.42):
        _place(out, _bell(1250.0, 1.6) * 0.7, at)
    return _norm(_spectral(out, _band(200, 7000)), 0.9)


def synth_menu() -> dict[str, np.ndarray]:
    return {"music": synth_music(), "harbor": synth_harbor(),
            "teleprinter": synth_teleprinter()}


def synth_oneshots() -> dict[str, np.ndarray]:
    return {"telegraph": synth_telegraph()}


# --------------------------------------------------------------------------- mixern
class MenuMixer(Ambience):
    """Slingorna och enstaka ljud ovanpå (klockan, radion)."""

    def __init__(self, samples: dict[str, np.ndarray] | None = None, volume: float = 0.8):
        super().__init__(samples=samples or {}, volume=volume)
        self._shots: list[list] = []                 # [ljud, läge, styrka]

    def oneshot(self, samples: np.ndarray, gain: float = 1.0) -> None:
        with self._lock:
            self._shots.append([samples, 0, gain])

    @property
    def busy(self) -> bool:
        """Spelas ett enstaka ljud just nu?"""
        return bool(self._shots)

    def extra(self, out: np.ndarray) -> None:
        with self._lock:
            shots = list(self._shots)
        n = len(out)
        done = []
        for shot in shots:
            snd, pos, gain = shot
            part = snd[pos:pos + n]
            if part.ndim == 1:
                part = np.repeat(part[:, None], 2, axis=1)
            out[:len(part)] += part * gain * (self._master if self.enabled else 0.0)
            shot[1] = pos + n
            if shot[1] >= len(snd):
                done.append(shot)
        if done:
            with self._lock:
                self._shots = [s for s in self._shots if s not in done]


class MenuSound:
    """Menyns ljud. Syntesen tar några sekunder och görs i en tråd; till dess är det tyst.

    out_factory: ljudströmmen (AmbientOut), utbytbar i tester.
    """

    def __init__(self, out_factory=AmbientOut, threaded: bool = True):
        self.mixer = MenuMixer()
        self.out = out_factory(self.mixer)
        self.typing = False
        self.departing = False
        self.oneshots: dict[str, np.ndarray] = {}
        self.ready = threading.Event()
        if threaded:
            threading.Thread(target=self._load, daemon=True).start()
        else:
            self._load()

    @property
    def error(self) -> str | None:
        return getattr(self.out, "error", None)

    def _load(self) -> None:
        samples = synth_menu()
        self.oneshots = synth_oneshots()
        self.mixer.samples = samples
        self.ready.set()
        self._targets()

    def _targets(self) -> None:
        from .ambience import Target
        targets = {}
        if not self.departing:
            targets["music"] = Target("music", GAIN["music"])
            targets["harbor"] = Target("harbor", GAIN["harbor"])
        if self.typing:
            targets["teleprinter"] = Target("teleprinter", GAIN["teleprinter"])
        self.mixer.set_targets(targets)

    def set_typing(self, typing: bool) -> None:
        if typing != self.typing:
            self.typing = typing
            self._targets()

    def play(self, name: str, gain: float = 1.0) -> None:
        if name in self.oneshots:
            self.mixer.oneshot(self.oneshots[name], gain)

    def depart(self) -> None:
        """Ett uppdrag är valt: telegrafen ringer, musiken och hamnen tonar bort."""
        self.departing = True
        self.play("telegraph", 0.8)
        self._targets()

    def close(self) -> None:
        self.mixer.set_targets({})
        if self.out is not None:
            self.out.close()
            self.out = None
