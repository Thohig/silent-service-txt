"""Bakgrundsljud: båten som lever runt kaptenen.

Reaktorpumparna brummar alltid när reaktorn är i drift, turbinen tar i med
farten, smygmotorn är nästan tyst. Skrovet knakar när djupet ändras och
stönar nära provdjupet. Under isen hörs isen; vid brand hörs elden och
fläktarna. Kontakter som sonaren håller hörs svagt i sina bäringar, och
deras ljud blir tydligare ju bättre de är klassade.

Allt styrs av det besättningen vet: statusraden (StatusSnapshot) och
kunskapens kontaktspår. Inget läses ur världen.

    ambient_targets(status, tracks)   vad som ska höras, och hur starkt
    Ambience                          mixern: slingor med mjuka volymändringar
    AmbientOut                        ljudström till högtalarna (sounddevice)

Slingorna syntetiseras i frekvensplanet och är därför sömlösa.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

import numpy as np

RATE = 22050
BLOCK = 1024
LOOP_S = 6.0
MAX_CONTACTS = 3                   # så många kontakter hörs samtidigt
CONTACT_FULL_SE = 30.0             # signalöverskott som ger full kontaktvolym
SMOOTH_S = 0.8                     # volym- och panoreringsändringar glider så länge


@dataclass(frozen=True)
class Target:
    sample: str
    gain: float
    pan: float = 0.0               # -1 vänster … 1 höger
    rate: float = 1.0              # uppspelningstakt (tonhöjd)


# --------------------------------------------------------------------------- vad som hörs
def contact_sample(classification: str) -> str | None:
    """Vilket ljud en kontakt har, efter hur den är klassad. None: hörs inte som maskin."""
    c = classification
    if any(w in c for w in ("isskruvning", "isljud", "bredbandigt")):
        return None
    if "dieselgenerator" in c or "maskinbuller" in c:
        return "generator"
    if "jagare" in c or "tvåskruv" in c:
        return "screws_warship"
    if any(w in c for w in ("handelsfartyg", "enskruv", "stort", "tankfartyg", "trupptransport")):
        return "screws_merchant"
    if "ubåt" in c or "undervattens" in c:
        return "screws_sub"
    return "screws_unknown"


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def ambient_targets(st, tracks: Iterable = ()) -> dict[str, Target]:
    """Bakgrundsljudet för ett ögonblick. st: StatusSnapshot. tracks: ContactTrack."""
    out: dict[str, Target] = {}
    speed, depth = st.speed, st.depth

    # --- steg 3: egen båt ---------------------------------------------------
    reactor = {"online": 0.16, "starting": 0.07}.get(st.reactor, 0.0)
    if reactor:
        out["reactor"] = Target("reactor", reactor)
    if st.propulsion == "turbine" and st.reactor == "online":
        out["turbine"] = Target("turbine", 0.06 + 0.26 * _clip(speed / 25),
                                rate=0.75 + speed / 40)
    elif speed > 0.3:
        out["electric"] = Target("electric", 0.03 + 0.06 * _clip(speed / 6),
                                 rate=0.85 + speed / 25)
    flow = 0.3 * _clip(speed / 25) ** 1.5
    if flow > 0.005:
        out["flow"] = Target("flow", flow)
    if st.cavitating:
        out["cavitation"] = Target("cavitation", 0.15 + 0.2 * _clip((speed - 6) / 10))
    deep = _clip((depth - 200) / 100)
    damage = 1.0 - st.hull
    creak = (0.2 if "depth" in st.changing else 0.0) + 0.35 * deep * (1 if "depth" in st.changing else 0.4) \
        + 0.4 * damage
    if creak > 0.01 and depth > 20:
        out["creak"] = Target("creak", _clip(creak, 0, 0.6))
    groan = _clip((depth - 270) / 60) * 0.5 + (0.2 if damage > 0.3 and depth > 100 else 0.0)
    if groan > 0.01:
        out["groan"] = Target("groan", groan)
    if st.flooding > 0:
        out["flooding"] = Target("flooding", 0.25 + 0.3 * _clip(st.flooding * 4))
    if depth < 2.0:
        out["waves"] = Target("waves", 0.25)

    # --- steg 4: is, brand, ventilation --------------------------------------
    if st.under_ice and depth >= 2.0:
        out["ice"] = Target("ice", 0.04 + 0.3 * _clip((st.sea_noise - 48) / 24))
    if st.fire:
        out["fire"] = Target("fire", 0.3)
    if st.fire or st.smoke > 0.3:
        out["fans"] = Target("fans", 0.12 + 0.1 * _clip(st.smoke))
    if st.ventilating:
        out["vent"] = Target("vent", 0.25)

    # --- centralen: luften, besättningen och det som hotar -------------------
    quiet = st.propulsion == "electric" or st.hunted       # tyst gång: ingen pratar
    if st.reactor == "online":
        out["aircon"] = Target("aircon", 0.035 if quiet else 0.07)
    if not quiet and not st.over:
        out["crew"] = Target("crew", 0.05)
    menace = 0.0
    if st.hunted:
        menace = 0.11
    elif any(tr.held and tr.warship and tr.observations and tr.observations[-1].se > 10
             for tr in tracks):
        menace = 0.05
    if menace:
        out["dread"] = Target("dread", menace)

    # --- kontakter sonaren håller -------------------------------------------
    heard = []
    for tr in tracks:
        if not tr.held or not tr.observations:
            continue
        sample = contact_sample(tr.classification)
        obs = tr.observations[-1]
        if sample is None or obs.se <= 0:
            continue
        heard.append((obs.se, tr.designation, sample, obs.bearing))
    heard.sort(reverse=True)
    for se, desig, sample, bearing in heard[:MAX_CONTACTS]:
        rel = np.radians(bearing - st.course)
        out[f"contact:{desig}"] = Target(sample, 0.03 + 0.17 * _clip(se / CONTACT_FULL_SE),
                                         pan=float(np.sin(rel)))
    if in_cabin(st):
        return muffled(out)
    return out


CABIN_GAIN = 0.55          # genom skottet till hytten
CABIN_KEEP = ("reactor", "turbine", "electric", "flow", "creak", "groan", "aircon", "crew",
              "flooding", "fire", "fans", "vent", "ice", "cavitation", "waves")


def in_cabin(st) -> bool:
    """Kaptenen är i hytten (starpom har befälet)."""
    return getattr(st, "command", "captain") == "starpom" and \
        getattr(st, "captain_at", "central") == "cabin"


def muffled(targets: dict[str, Target]) -> dict[str, Target]:
    """Hytten: båten hörs dämpad genom skottet, mumlet från centralen svagt; inga
    hydrofonljud och inget hotfullt sväv (sonarens hörlurar når inte hit)."""
    out = {}
    for k, t in targets.items():
        if k not in CABIN_KEEP:
            continue
        gain = t.gain * (0.3 if k == "crew" else CABIN_GAIN)
        out[k] = Target(t.sample, gain, pan=t.pan, rate=t.rate)
    return out


# --------------------------------------------------------------------------- mixern
@dataclass
class _Layer:
    sample: str
    pos: float = 0.0
    gain: float = 0.0
    pan: float = 0.0
    rate: float = 1.0


class Ambience:
    """Mixar slingor till stereo. set_targets() från spelet, render() från ljudtråden."""

    def __init__(self, samples: dict[str, np.ndarray] | None = None, volume: float = 0.8):
        self.samples = samples if samples is not None else synth_ambience()
        self.volume = volume
        self.enabled = True
        self._targets: dict[str, Target] = {}
        self._layers: dict[str, _Layer] = {}
        self._master = 1.0
        self._fading = 0                   # löpnummer för lager som tonar ut efter ett byte
        self._lock = threading.Lock()

    def set_targets(self, targets: dict[str, Target]) -> None:
        with self._lock:
            self._targets = dict(targets)

    def render(self, n: int) -> np.ndarray:
        with self._lock:
            targets = self._targets
        k = min(1.0, n / (RATE * SMOOTH_S))           # andel av vägen mot målet per block
        out = np.zeros((n, 2))
        master_to = self.volume if self.enabled else 0.0
        m0, self._master = self._master, self._master + (master_to - self._master) * k * 2
        for key, t in targets.items():
            if t.sample not in self.samples:
                continue
            old = self._layers.get(key)
            if old is not None and old.sample != t.sample:
                # Ljudet byts (kontakten klassad om): det gamla tonar ut, det nya tonar in.
                self._fading += 1
                self._layers[f"{key}~{self._fading}"] = self._layers.pop(key)
                old = None
            if old is None:
                self._layers[key] = _Layer(t.sample, pan=t.pan, rate=t.rate)
        for key in list(self._layers):
            lay = self._layers[key]
            t = targets.get(key)
            g_to = t.gain if t else 0.0
            if t:
                lay.pan += (t.pan - lay.pan) * k
                lay.rate += (t.rate - lay.rate) * k
            g0, lay.gain = lay.gain, lay.gain + (g_to - lay.gain) * k
            if t is None and lay.gain < 1e-3:
                del self._layers[key]
                continue
            src = self.samples[lay.sample]
            idx = lay.pos + lay.rate * np.arange(n)
            i0 = np.floor(idx).astype(int)
            frac = idx - i0
            i0 %= len(src)
            mono = src[i0] * (1 - frac) + src[(i0 + 1) % len(src)] * frac
            lay.pos = float((lay.pos + lay.rate * n) % len(src))
            env = np.linspace(g0, lay.gain, n, endpoint=False)
            a = (lay.pan + 1) * np.pi / 4
            out[:, 0] += mono * env * np.cos(a) * np.sqrt(2)
            out[:, 1] += mono * env * np.sin(a) * np.sqrt(2)
        out *= np.linspace(m0, self._master, n, endpoint=False)[:, None]
        self.extra(out)
        return np.tanh(out)                            # mjuk begränsning, aldrig klipp

    def extra(self, out: np.ndarray) -> None:
        """Krok för underklasser: lägg till ljud utöver slingorna (stereo, på plats)."""

    @property
    def layers(self) -> dict[str, _Layer]:
        return self._layers


class AmbientOut:
    """Ljudström via sounddevice. Saknas ljudkort eller PortAudio blir det tyst."""

    def __init__(self, ambience: Ambience):
        self.ambience = ambience
        self.stream = None
        self.error: str | None = None
        try:
            import sounddevice as sd
            self.stream = sd.OutputStream(samplerate=RATE, channels=2, blocksize=BLOCK,
                                          dtype="float32", callback=self._callback)
            self.stream.start()
        except Exception as exc:                       # noqa: BLE001 – inget ljud är inget fel
            self.stream = None
            self.error = str(exc)

    def _callback(self, outdata, frames, _time, _status) -> None:
        try:
            outdata[:] = self.ambience.render(frames).astype(np.float32)
        except Exception:                              # noqa: BLE001 – ljudtråden får aldrig dö
            outdata.fill(0)

    def close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:                          # noqa: BLE001
                pass
            self.stream = None


# --------------------------------------------------------------------------- syntes
# Allt är periodiskt över LOOP_S: brus formas i frekvensplanet (cirkulärt) och
# toner och moduleringar har ett helt antal perioder per slinga.
_N = int(RATE * LOOP_S)
_F = np.fft.rfftfreq(_N, 1 / RATE)
_T = np.arange(_N) / RATE


def _q(f: float) -> float:
    """Avrunda frekvensen så att den går jämnt upp i slingan."""
    return round(f * LOOP_S) / LOOP_S


def _tone(f: float) -> np.ndarray:
    return np.sin(2 * np.pi * _q(f) * _T)


def _shaped(seed: int, lo: float, hi: float, tilt: float = 0.0) -> np.ndarray:
    """Bandbegränsat brus (lo–hi Hz), tilt dB/oktav. Sömlöst."""
    spec = np.fft.rfft(np.random.default_rng(seed).standard_normal(_N))
    f = np.maximum(_F, 1.0)
    mag = ((f >= lo) & (f <= hi)).astype(float) * (f / max(lo, 1.0)) ** (tilt / 6.02)
    # mjuka kanter
    mag *= np.clip((f - lo * 0.7) / (lo * 0.3 + 1e-9), 0, 1) if lo > 0 else 1.0
    x = np.fft.irfft(spec * mag, _N)
    return x / max(1e-9, float(np.max(np.abs(x))))


def _lfo(f: float, depth: float, phase: float = 0.0) -> np.ndarray:
    return 1.0 - depth * 0.5 * (1 + np.sin(2 * np.pi * _q(f) * _T + phase))


def _norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    return peak * x / max(1e-9, float(np.max(np.abs(x))))


def _events(seed: int, count: int, make) -> np.ndarray:
    """Utspridda händelser i slingan (med omslag), make(rng) -> kort ljud."""
    rng = np.random.default_rng(seed)
    out = np.zeros(_N)
    for _ in range(count):
        snd = make(rng)
        a = int(rng.uniform(0, _N))
        idx = (a + np.arange(len(snd))) % _N
        np.add.at(out, idx, snd)
    return out


def synth_reactor() -> np.ndarray:
    """Reaktorpumparna: 50 Hz-brum, pumpvin och dovt brus."""
    hum = sum(a * _tone(50 * k) for k, a in ((1, 1.0), (2, 0.5), (3, 0.25), (6, 0.1)))
    whine = _tone(410) * 0.08 * _lfo(0.5, 0.4)
    rumble = _shaped(21, 20, 250, -3) * 0.6
    return _norm(hum * 0.5 + whine + rumble)


def synth_turbine() -> np.ndarray:
    """Turbin och axel: bredbandigt muller med bladfrekvens."""
    rumble = _shaped(22, 25, 900, -4)
    blade = (_tone(29) + 0.5 * _tone(58) + 0.3 * _tone(87)) * 0.35
    gear = _tone(310) * 0.06
    return _norm((rumble + blade + gear) * _lfo(29 / 7, 0.25))


def synth_electric() -> np.ndarray:
    """Smygmotorn: ett svagt elektriskt vin."""
    return _norm(_tone(180) * 0.4 + _tone(360) * 0.2 + _shaped(23, 100, 500, -3) * 0.3)


def synth_flow() -> np.ndarray:
    """Vatten som strömmar förbi skrovet."""
    return _norm(_shaped(24, 80, 2500, -2) * _lfo(0.17, 0.3) * _lfo(0.5, 0.15, 1.0))


def synth_cavitation() -> np.ndarray:
    """Kavitation: sprakande bubblor kring propellern."""
    crackle = _shaped(25, 1500, 8000, 0) * (np.random.default_rng(26).random(_N) < 0.25)
    beat = _lfo(29 / 7, 0.7)
    return _norm(crackle * beat + _shaped(27, 300, 3000, -2) * 0.4 * beat)


def _creak_sound(rng) -> np.ndarray:
    dur = rng.uniform(0.25, 0.9)
    t = np.arange(int(RATE * dur)) / RATE
    f0, f1 = rng.uniform(90, 260), rng.uniform(60, 200)
    f = f0 + (f1 - f0) * t / dur
    stick = 1.0 + 0.8 * (np.sin(2 * np.pi * rng.uniform(15, 40) * t) > 0.6)   # stick-slip
    s = np.sign(np.sin(2 * np.pi * np.cumsum(f) / RATE)) * stick * np.sin(np.pi * t / dur)
    return s * rng.uniform(0.3, 1.0)


def synth_creak() -> np.ndarray:
    """Skrovet knakar när trycket ändras."""
    x = _events(31, 6, _creak_sound)
    spec = np.fft.rfft(x)
    spec[_F > 1400] *= 0.1                           # stål, inte plåtburk
    return _norm(np.fft.irfft(spec, _N))


def synth_groan() -> np.ndarray:
    """Djupt stönande nära provdjupet."""
    g = _shaped(32, 25, 140, -6) * _lfo(0.33, 0.8) * _lfo(1 / 6, 0.5, 2.0)
    return _norm(g + 0.4 * _norm(_events(33, 3, _creak_sound)) * 0.5)


def synth_flooding() -> np.ndarray:
    """Inträngande vatten."""
    return _norm(_shaped(34, 200, 6000, -1) * _lfo(3.0, 0.2) + _shaped(35, 40, 300, -3) * 0.5)


def synth_waves() -> np.ndarray:
    """Ytläge: vågor som slår mot skrovet."""
    swell = _lfo(1 / 3, 0.9) * _lfo(1 / 2, 0.4, 1.3)
    return _norm(_shaped(36, 100, 2000, -3) * swell)


def _ice_pop(rng) -> np.ndarray:
    n = int(RATE * rng.uniform(0.01, 0.06))
    return rng.standard_normal(n) * np.exp(-np.arange(n) / (n / 4)) * rng.uniform(0.2, 1.0)


def synth_ice() -> np.ndarray:
    """Isen ovanför: knäppningar, knastrande och ett lågt stön."""
    pops = _events(41, 70, _ice_pop)
    spec = np.fft.rfft(pops)
    spec[_F > 4000] *= 0.2
    pops = np.fft.irfft(spec, _N)
    moan = _shaped(42, 40, 300, -4) * _lfo(1 / 3, 0.9)
    return _norm(_norm(pops) + 0.35 * moan)


def synth_fire() -> np.ndarray:
    """Eld bakom ett skott: dovt sprakande."""
    crack = _events(43, 120, _ice_pop)
    spec = np.fft.rfft(crack)
    spec[_F > 2500] *= 0.1                           # hörs genom skottet
    roar = _shaped(44, 30, 400, -4) * _lfo(0.5, 0.4)
    return _norm(_norm(np.fft.irfft(spec, _N)) + 0.6 * roar)


def synth_fans() -> np.ndarray:
    """Nödfläktar."""
    return _norm(_tone(97) * 0.3 + _tone(194) * 0.15 + _shaped(45, 200, 3000, -2))


def synth_vent() -> np.ndarray:
    """Ventilation genom masten: luft som dras in."""
    return _norm(_shaped(46, 150, 4000, -1) * _lfo(0.25, 0.2) + _tone(120) * 0.1)


def _screws(seed: int, blade_hz: float, beat_hz: float, lo: float, hi: float,
            depth: float, tone_hz: float) -> np.ndarray:
    churn = _shaped(seed, lo, hi, -2) * _lfo(beat_hz, depth)
    return _norm(churn + 0.25 * _tone(tone_hz) * _lfo(blade_hz, 0.5))


def synth_screws_merchant() -> np.ndarray:
    """Handelsfartyg: en stor, långsam skruv och en diesel."""
    return _screws(51, 7.5, 1.5, 40, 1200, 0.7, 75)


def synth_screws_warship() -> np.ndarray:
    """Jagare: två snabba skruvar, ångturbiner."""
    return _screws(52, 20, 3.5, 80, 3000, 0.6, 140) * 0.9 + 0.1 * _norm(_shaped(53, 1000, 4000, 0)
                                                                         * _lfo(3.5, 0.8, 1.0))


def synth_screws_sub() -> np.ndarray:
    """Ubåt: tyst, ett lågt pumpbrum."""
    return _norm(_tone(60) * 0.5 + _tone(120) * 0.3 + _shaped(54, 30, 400, -4) * 0.4 * _lfo(2.0, 0.3))


def synth_screws_unknown() -> np.ndarray:
    """Okänd kontakt: ett otydligt dunkande brus."""
    return _norm(_shaped(55, 60, 1500, -3) * _lfo(2.5, 0.35))


def synth_generator() -> np.ndarray:
    """Dieselgenerator på isen."""
    knock = _tone(25) * 0.4 + _tone(50) * 0.4 + _tone(100) * 0.2
    return _norm(knock * _lfo(12.5, 0.6) + _shaped(56, 100, 1500, -2) * 0.3)


def _syllable(rng) -> np.ndarray:
    """En stavelse långt bort i båten: formantfärgat brus med tonfall."""
    n = int(RATE * rng.uniform(0.08, 0.22))
    t = np.arange(n) / RATE
    f0 = rng.uniform(95, 140)
    voice = np.sign(np.sin(2 * np.pi * f0 * t)) * 0.5 + rng.standard_normal(n) * 0.2
    return voice * np.sin(np.pi * t / t[-1]) * rng.uniform(0.3, 1.0)


def _phrase_events(seed: int, phrases: int) -> np.ndarray:
    """Korta repliker: några stavelser tätt, sedan tystnad."""
    rng = np.random.default_rng(seed)
    out = np.zeros(_N)
    for _ in range(phrases):
        at = rng.uniform(0, LOOP_S)
        for _k in range(rng.integers(3, 8)):
            snd = _syllable(rng)
            idx = (int(at * RATE) + np.arange(len(snd))) % _N
            out[idx] += snd
            at += len(snd) / RATE + rng.uniform(0.02, 0.09)
    return out


def synth_crew() -> np.ndarray:
    """Besättningen i grannavdelningarna: dämpat mummel bakom skotten."""
    talk = _phrase_events(61, 5) + 0.6 * _phrase_events(62, 4)
    spec = np.fft.rfft(talk)
    f = _F
    spec *= np.exp(-0.5 * ((f - 500) / 260) ** 2) + 0.5 * np.exp(-0.5 * ((f - 1200) / 300) ** 2)
    murmur = np.fft.irfft(spec, _N)
    clank = _events(63, 2, lambda r: np.sin(2 * np.pi * r.uniform(600, 900)
                                            * np.arange(int(RATE * 0.4)) / RATE)
                    * np.exp(-np.arange(int(RATE * 0.4)) / RATE * 12) * 0.3)
    return _norm(_norm(murmur) + clank)


def synth_aircon() -> np.ndarray:
    """Luftkonditioneringen och fläktarna som alltid går: jämnt sus med brum."""
    return _norm(_shaped(64, 120, 2500, -3) * _lfo(0.5, 0.08) + _tone(100) * 0.08
                 + _tone(200) * 0.04)


def synth_dread() -> np.ndarray:
    """Något som hotar: ett lågt sväv (två toner som slår mot varandra) som andas."""
    drone = _tone(41.0) + _tone(41.5) + 0.4 * _tone(61.5)
    breath = _lfo(1 / 6, 0.6)
    rumble = _shaped(65, 25, 120, -6) * 0.5
    return _norm((drone * 0.6 + rumble) * breath)


def synth_ambience() -> dict[str, np.ndarray]:
    return {
        "reactor": synth_reactor(), "turbine": synth_turbine(), "electric": synth_electric(),
        "flow": synth_flow(), "cavitation": synth_cavitation(), "creak": synth_creak(),
        "groan": synth_groan(), "flooding": synth_flooding(), "waves": synth_waves(),
        "ice": synth_ice(), "fire": synth_fire(), "fans": synth_fans(), "vent": synth_vent(),
        "screws_merchant": synth_screws_merchant(), "screws_warship": synth_screws_warship(),
        "screws_sub": synth_screws_sub(), "screws_unknown": synth_screws_unknown(),
        "generator": synth_generator(),
        "crew": synth_crew(), "aircon": synth_aircon(), "dread": synth_dread(),
    }
