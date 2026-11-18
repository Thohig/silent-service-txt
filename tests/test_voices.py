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
