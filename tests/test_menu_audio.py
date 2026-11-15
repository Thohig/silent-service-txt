"""Huvudmenyns ljud: slingorna går runt utan skarv, mixern och ljudets livscykel i appen."""
import asyncio

import numpy as np
import pytest

from ui import menu_audio
from ui.menu_audio import GAIN, MenuMixer, MenuSound, RATE


class FakeOut:
    def __init__(self, mixer):
        self.mixer = mixer
        self.closed = False
        self.error = None

    def close(self):
        self.closed = True


@pytest.fixture
def tiny_samples(monkeypatch):
    """Snabba slingor i stället för den riktiga syntesen."""
    loops = {"music": np.full(100, 0.1), "harbor": np.full(100, 0.1),
             "teleprinter": np.full(100, 0.1), "static": np.full(100, 0.1)}
    monkeypatch.setattr(menu_audio, "synth_menu", lambda: loops)
    monkeypatch.setattr(menu_audio, "synth_oneshots", lambda: {"telegraph": np.full(300, 0.2),
                                                             "tuning": np.full(300, 0.2)})


def _seam_ok(x: np.ndarray) -> bool:
    """Steget från slingans slut till början är inte större än ljudets egna steg."""
    steps = np.abs(np.diff(x))
    return abs(x[0] - x[-1]) <= 1.5 * float(np.percentile(steps, 99))


@pytest.mark.slow
def test_loops_are_finite_quiet_enough_and_seamless():
    loops = menu_audio.synth_menu()
    assert set(loops) == {"music", "harbor", "teleprinter", "static"}
    assert len(loops["music"]) == RATE * 64 and len(loops["harbor"]) == RATE * 40
    for name, x in loops.items():
        assert np.isfinite(x).all() and np.max(np.abs(x)) <= 1.0, name
        assert np.sqrt(np.mean(x ** 2)) > 0.03, name             # något hörs
    assert _seam_ok(loops["music"]) and _seam_ok(loops["harbor"])
    # musiken växer andra varvet när hornet kommer in
    halves = np.split(loops["music"], 2)
    assert np.sqrt(np.mean(halves[1] ** 2)) > np.sqrt(np.mean(halves[0] ** 2))
    shot = menu_audio.synth_telegraph()
    assert 1.0 < len(shot) / RATE < 3.0 and np.max(np.abs(shot)) <= 1.0


def test_mixer_plays_a_oneshot_over_the_loops_and_then_drops_it():
    mixer = MenuMixer(samples={"music": np.zeros(1000)})
    mixer.oneshot(np.full(150, 0.5), gain=1.0)
    assert mixer.busy
    first = mixer.render(100)
    assert first.shape == (100, 2) and first[50, 0] > 0.1
    mixer.render(100)
    assert not mixer.busy
    assert np.allclose(mixer.render(100), 0.0)


def test_menu_sound_targets_follow_typing_and_departure(tiny_samples):
    snd = MenuSound(out_factory=FakeOut, threaded=False)
    targets = snd.mixer._targets
    assert set(targets) == {"music", "harbor"} and targets["music"].gain == GAIN["music"]
    snd.set_typing(True)
    assert "teleprinter" in snd.mixer._targets
    snd.depart()
    assert set(snd.mixer._targets) == {"teleprinter"}                # musiken tonar bort
    assert snd.mixer.busy                                            # telegrafen ringer
    snd.set_typing(False)
    assert snd.mixer._targets == {}
    out = snd.out
    snd.close()
    assert out.closed and snd.out is None


@pytest.mark.slow
def test_app_starts_menu_music_toggles_it_and_stops_it_when_command_is_taken(
        tmp_path, tiny_samples, monkeypatch):
    from ui import app as ui_app
    from ui.app import GameScreen, SubApp

    monkeypatch.setattr(ui_app, "MenuSound", lambda: MenuSound(out_factory=FakeOut))

    async def run():
        app = SubApp(seed=3, log_dir=tmp_path, sound=True)
        async with app.run_test(size=(110, 36)) as pilot:
            await pilot.pause()
            assert app.menu_sound is not None
            await pilot.press("ctrl+t")
            assert app.menu_sound is None and not app.sound_wanted
            await pilot.press("ctrl+t")
            assert app.menu_sound is not None and app.sound_wanted
            snd = app.menu_sound
            options = app.screen.query_one("#scenarios")
            options.highlighted = options.get_option_index("kuba")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, GameScreen)
            assert snd.departing and snd.typing                       # ordern skrivs ut
            await pilot.press("enter")                                # hela ordern
            await pilot.pause()
            assert not snd.typing
            await pilot.press("enter")                                # ta befälet
            await pilot.pause()
            assert app.menu_sound is None and snd.out is None

    asyncio.run(run())


def test_radio_voice_is_narrow_band_and_bounded():
    t = np.arange(RATE) / RATE
    x = np.sin(2 * np.pi * 120 * t) + np.sin(2 * np.pi * 1000 * t) + np.sin(2 * np.pi * 6000 * t)
    y = menu_audio.radio_voice(x)
    assert np.max(np.abs(y)) <= 0.8 + 1e-9 and len(y) > len(x)
    spec = np.abs(np.fft.rfft(y))
    f = np.fft.rfftfreq(len(y), 1 / RATE)

    def power(c):
        return spec[(f > c - 20) & (f < c + 20)].sum()
    assert power(1000) > 5 * power(120) and power(1000) > 5 * power(6000)


def test_read_wav_resamples_to_the_mixer_rate(tmp_path):
    import wave
    path = tmp_path / "x.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(11025)
        w.writeframes((np.full(11025, 0.5) * 32767).astype("<i2").tobytes())
    x = menu_audio.read_wav(path)
    assert abs(len(x) - RATE) <= 1 and abs(x.mean() - 0.5) < 0.01


def test_broadcast_tunes_in_speaks_and_goes_quiet(tiny_samples):
    spoken = []

    def voice(text):
        spoken.append(text)
        return np.full(RATE // 2, 0.3)

    snd = MenuSound(out_factory=FakeOut, threaded=False, voice=voice)
    snd.radio("Говорит Москва.")
    assert spoken == ["Говорит Москва."]
    assert snd.mixer.busy and len(snd.mixer._shots) == 2                # ratten och rösten
    assert not snd.on_air and "static" not in snd.mixer._targets        # klart: bruset borta
    assert snd.mixer._targets["music"].gain == GAIN["music"]
    # utan rysk röst: bara brus
    quiet = MenuSound(out_factory=FakeOut, threaded=False, voice=lambda _t: None)
    quiet.radio("Говорит Москва.")
    assert len(quiet.mixer._shots) == 1
    # inte efter avfärden
    quiet.depart()
    quiet.radio("Говорит Москва.")
    assert quiet.radio_count == 1


def test_music_ducks_and_static_plays_while_on_air(tiny_samples):
    snd = MenuSound(out_factory=FakeOut, threaded=False, voice=lambda _t: None)
    snd.on_air = True
    snd._targets()
    assert "static" in snd.mixer._targets
    assert snd.mixer._targets["music"].gain < GAIN["music"]
