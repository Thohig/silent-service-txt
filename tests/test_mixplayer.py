"""Allt ljud genom mixern (MixPlayer): repliker, effekter och hytten (T2)."""
import time
from types import SimpleNamespace

import numpy as np

from sim.events import EventBus, ReportDelivered
from sim.reports import Report
from ui.ambience import RATE, Ambience
from ui.audio import (MixPlayer, SoundBoard, apply_effect, muffled_voice, phone_voice,
                      speech_effect)


class FakeSynth:
    """Låtsasröst: en ton på 150 Hz med övertoner, en halv sekund per replik."""

    def __init__(self):
        self.calls = []

    def render(self, text, voice, rate, sample_rate):
        self.calls.append((text, voice, rate))
        t = np.arange(int(sample_rate * 0.5)) / sample_rate
        return 0.5 * sum(np.sin(2 * np.pi * 150 * k * t) / k for k in range(1, 30))


def _wait(cond, timeout=2.0):
    t0 = time.monotonic()
    while not cond() and time.monotonic() - t0 < timeout:
        time.sleep(0.005)
    return cond()


def _player():
    mixer = Ambience(samples={})
    return mixer, MixPlayer(mixer, FakeSynth())


def _pull(mixer, seconds):
    return np.concatenate([mixer.render(1024) for _ in range(int(seconds * RATE / 1024) + 1)])


def test_repliken_renderas_och_spelas_i_mixern():
    mixer, p = _player()
    p.speak("Kapten, sonar.", 165, "Alva")
    assert p.speaking()                              # redan medan den renderas
    assert _wait(lambda: mixer.busy)
    out = _pull(mixer, 0.6)
    assert np.abs(out).max() > 0.1
    assert _wait(lambda: not p.speaking())
    assert p.synth.calls == [("Kapten, sonar.", "Alva", 165)]


def test_stopp_tystar_och_kastar_det_som_renderas():
    mixer, p = _player()
    p.speak("Ett", 180)
    p.stop()
    time.sleep(0.1)
    assert not p.speaking() and not mixer.busy


def test_ljuden_gar_genom_mixern():
    mixer, p = _player()
    assert p.play("attention") > 0
    assert mixer.busy
    assert p.play("finns-inte") == 0.0


def _energy(x, lo, hi):
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    s = np.abs(np.fft.rfft(x)) ** 2
    return s[(f >= lo) & (f < hi)].sum() / s.sum()


def test_telefonen_tar_bort_basen_och_skottet_diskanten():
    x = FakeSynth().render("", "", 180, RATE)
    assert _energy(phone_voice(x), 0, 200) < 0.1 * _energy(x, 0, 200)
    assert _energy(muffled_voice(x), 800, 11025) < 0.05 * _energy(x, 800, 11025)
    assert apply_effect(x, None) is x


def _status(where="central"):
    return SimpleNamespace(command="starpom" if where == "cabin" else "captain",
                           captain_at=where)


def _report(role, alarm=False):
    return Report(t_due=0, speaker="", type="x", role=role, text="Kapten.", alarm=alarm)


def test_effekten_efter_var_kaptenen_ar():
    central, cabin = _status("central"), _status("cabin")
    assert speech_effect(_report("sonar"), central) == "phone"
    assert speech_effect(_report("navigator"), central) is None
    assert speech_effect(_report("sonar"), cabin) == "muffled"
    assert speech_effect(_report("navigator"), cabin) == "muffled"
    assert speech_effect(_report("starpom"), cabin) == "phone"
    assert speech_effect(_report("sonar", alarm=True), cabin) is None


def test_hytten_hor_centralen_dampad_med_mixern():
    bus = EventBus()
    mixer, p = _player()
    board = SoundBoard(bus, p)
    board._status = _status("cabin")
    bus.publish(ReportDelivered(0, _report("navigator")))
    assert len(board.queue) == 1
    assert board.queue[0].effect == "muffled" and not board.queue[0].urgent
    board.update(1.0)
    assert _wait(lambda: p.synth.calls)
