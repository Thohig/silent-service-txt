"""Rösterna (ui/voices.py): allt om talsyntesen på ett ställe."""
import re
import wave
from pathlib import Path

import numpy as np
import pytest

from ui import voices
from ui.voices import MacSay

UI = Path(__file__).resolve().parent.parent / "ui"


def test_say_bara_i_voices():
    """Talsyntesen nås bara genom rösterna, så att en annan plattform bara behöver en backend."""
    for path in UI.glob("*.py"):
        if path.name == "voices.py":
            continue
        assert not re.search(r"""["']say["']""", path.read_text()), path.name


def test_rost_per_sprak(monkeypatch):
    monkeypatch.setattr(voices, "_say_voices", lambda: frozenset({"Alva"}))
    monkeypatch.setattr(MacSay, "available", lambda self: True)
    say = MacSay()
    assert say.voice("sv") == "Alva"
    assert say.voice("ru") is None          # Milena saknas: besättningen talar svenska
    assert say.voice("de") is None


def test_utan_say_finns_inga_roster(monkeypatch):
    monkeypatch.setattr(MacSay, "available", lambda self: False)
    assert MacSay().voice("sv") is None
    assert MacSay().render("Jest", "Milena", 150, 22050) is None


def test_read_wav_blandar_ner_och_raknar_om(tmp_path):
    path = tmp_path / "s.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes((np.ones((4410, 2)) * 16384).astype("<i2").tobytes())
    x = voices.read_wav(path, 22050)
    assert len(x) == 2205
    assert np.allclose(x, 0.5)


@pytest.mark.slow
def test_render_ger_ljud():
    say = MacSay()
    voice = say.voice("sv")
    if voice is None:
        pytest.skip("rösten saknas")
    x = say.render("Kapten, sonar.", voice, 180, 22050)
    assert x is not None and len(x) > 22050 * 0.3


def _aiff(path, x, rate=22050, aifc=True):
    """Skriv mono 16 bitar som macOS talsyntes (AIFC 'twos'), eller vanlig AIFF."""
    import struct
    pcm = (np.asarray(x) * 32767).astype(">i2").tobytes()
    exp, mant = 16383 + 63, int(rate)
    while mant < (1 << 63):
        mant <<= 1
        exp -= 1
    comm = struct.pack(">hIh", 1, len(x), 16) + struct.pack(">HQ", exp, mant)
    if aifc:
        comm += b"twos" + b"\x00"
    ssnd = struct.pack(">II", 0, 0) + pcm
    chunks = b"COMM" + struct.pack(">I", len(comm)) + comm + (b"\x00" if len(comm) & 1 else b"")
    chunks += b"SSND" + struct.pack(">I", len(ssnd)) + ssnd
    path.write_bytes(b"FORM" + struct.pack(">I", 4 + len(chunks)) + (b"AIFC" if aifc else b"AIFF")
                     + chunks)


@pytest.mark.parametrize("aifc", [True, False])
def test_read_aiff(tmp_path, aifc):
    x = np.sin(np.arange(2205) / 10) * 0.5
    _aiff(tmp_path / "t.aiff", x, aifc=aifc)
    y, rate = voices.read_aiff(tmp_path / "t.aiff")
    assert rate == 22050
    assert np.allclose(y, x, atol=1e-4)


@pytest.mark.slow
def test_macsynth_renderar_snabbt_med_laddad_rost():
    if not voices.MacSynth.supported():
        pytest.skip("pyobjc saknas")
    import time
    syn = voices.MacSynth()
    voice = syn.voice("sv")
    if voice is None:
        pytest.skip("rösten saknas")
    assert syn.render("Kapten.", voice, 180, 22050) is not None       # laddar rösten
    t0 = time.perf_counter()
    x = syn.render("Torped i vattnet!", voice, 180, 22050)
    assert x is not None and len(x) > 22050 * 0.5
    assert time.perf_counter() - t0 < 0.4


class FakeWebSpeech:
    """Sidans talsyntes: språken den har, och replikerna den fått."""

    def __init__(self, langs=("sv", "ru")):
        self.langs = set(langs)
        self.spoken: list[tuple[str, str, float]] = []
        self.cancelled = 0

    def has(self, lang):
        return lang in self.langs

    def speak(self, text, lang, rate):
        self.spoken.append((text, lang, rate))
        return type("Handle", (), {"done": False})()

    def cancel(self):
        self.cancelled += 1


def test_webbens_roster_per_sprak(monkeypatch):
    monkeypatch.setattr(voices.WebSpeech, "bridge", FakeWebSpeech(langs=("sv",)))
    web = voices.WebSpeech()
    assert web.available()
    assert web.voice("sv") == voices.SV_VOICE
    assert web.voice("ru") is None           # ingen rysk röst i webbläsaren: svenska
    assert web.render("Jest", voices.SV_VOICE, 180, 22050) is None
    monkeypatch.setattr(voices.WebSpeech, "bridge", None)
    assert not web.available() and web.voice("sv") is None
    assert web.start("Jest", voices.SV_VOICE, 180) is None


def test_webben_laser_upp_och_avbryter(monkeypatch):
    bridge = FakeWebSpeech()
    monkeypatch.setattr(voices.WebSpeech, "bridge", bridge)
    web = voices.WebSpeech()
    s = web.start("Есть", voices.RU_VOICE, 270)
    assert bridge.spoken == [("Есть", "ru", 1.5)]
    assert s.poll() is None
    s.terminate()
    assert bridge.cancelled == 1
    s.handle.done = True
    assert s.poll() == 0
    s.terminate()                            # redan slut: avbryter inte nästa replik
    assert bridge.cancelled == 1
    assert web.start("x", "Okänd", 180) is None


def test_backend_i_webblasaren(monkeypatch):
    monkeypatch.setattr(voices.sys, "platform", "emscripten")
    voices.backend.cache_clear()
    try:
        assert isinstance(voices.backend(), voices.WebSpeech)
    finally:
        voices.backend.cache_clear()
