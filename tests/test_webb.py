"""Webbversionen (`web/`): bygget, drivrutinen för Pyodide och uppvärmningen i bitar.

Drivrutinen provas här i vanlig CPython med en låtsasterminal; i webbläsaren är `bridge`
xterm.js. Själva Pyodide provas för hand (`web/README.md`)."""
import asyncio
import random
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from sim.game import Game
from sim.scenario import build_scenario

WEB = Path(__file__).resolve().parent.parent / "web"
sys.path.insert(0, str(WEB))

import bygg  # noqa: E402
import web_audio  # noqa: E402
from pyodide_driver import PyodideDriver  # noqa: E402
from ui.ambience import BLOCK, RATE, Ambience  # noqa: E402


def test_bygget_har_spelet_och_startfilerna(tmp_path):
    out = bygg.build(tmp_path / "dist")
    names = set(zipfile.ZipFile(out / "k114.zip").namelist())
    assert {"start.py", "pyodide_driver.py", "web_audio.py", "sim/game.py", "ui/app.py"} <= names
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert (out / "index.html").exists() and (out / "k114.png").exists()
    html = (out / "index.html").read_text()
    for size in bygg.ICON_SIZES:   # varje ikon sidan länkar finns i bygget
        assert f'href="k114-{size}.png"' in html and (out / f"k114-{size}.png").exists()


class FakeTerm:
    def __init__(self):
        self.out: list[str] = []
        self.closed = False

    def write(self, s: str) -> None:
        self.out.append(s)

    def exit(self) -> None:
        self.closed = True

    def text(self) -> str:
        return "".join(self.out)


@pytest.mark.slow
def test_drivrutinen_ritar_menyn_och_tar_tangenter(tmp_path):
    from ui.app import MenuScreen, SubApp

    term = FakeTerm()

    async def run():
        PyodideDriver.bridge = term
        app = SubApp(log_dir=tmp_path)
        app.driver_class = PyodideDriver
        task = asyncio.create_task(app.run_async(size=(140, 42)))
        for _ in range(100):
            await asyncio.sleep(0.05)
            if isinstance(app.screen, MenuScreen) and "Övning" in term.text():
                break
        assert isinstance(app.screen, MenuScreen)
        driver = PyodideDriver.current
        assert driver is not None
        driver.resize(100, 30)
        await asyncio.sleep(0.2)
        assert app.size == (100, 30)
        driver.feed("\x11")                  # ctrl+q
        await asyncio.wait_for(task, 5)

    asyncio.run(run())
    assert "Övning" in term.text()
    assert term.closed and PyodideDriver.current is None


@pytest.mark.slow
def test_uppvarmningen_i_bitar_ger_samma_spel():
    def game():
        return Game(build_scenario("ovning-kort", random.Random(5)), seed=5, warm_up=False)

    a, b = game(), game()
    a.warm_up()
    steps = list(b.warm_up_steps(every=30))
    assert len(steps) > 1 and not b.warmup_pending
    assert a.now == b.now
    assert a.status() == b.status()


class FakeSink:
    """Sidans ljud: en klocka som står still tills testet flyttar den, och kön."""

    def __init__(self, rate: int = RATE):
        self.rate = rate
        self.now = 0.0
        self.chunks: list[np.ndarray] = []
        self.cleared = False

    def time(self) -> float:
        return self.now

    def push(self, x) -> None:
        self.chunks.append(x)

    def clear(self) -> None:
        self.cleared = True

    def frames(self) -> int:
        return sum(len(c) for c in self.chunks)


def _tone_mixer() -> Ambience:
    mixer = Ambience(samples={})
    mixer.oneshot(np.full(RATE, 0.5))           # en sekund ljud ovanpå tystnaden
    return mixer


def test_ljudet_fylls_pa_i_forvag_och_inte_mer():
    sink = FakeSink()
    out = web_audio.WebOut(_tone_mixer(), sink, timer=False)
    assert out.error is None
    out.pump()
    ahead = sink.frames() / RATE
    assert web_audio.AHEAD_S <= ahead < web_audio.AHEAD_S + BLOCK / RATE
    assert sink.chunks[0].dtype == np.float32 and sink.chunks[0].shape == (BLOCK, 2)
    assert out.pump() == 0                       # klockan står still: kön räcker
    sink.now = 0.1
    n = out.pump()
    assert 0 < n <= 0.1 * RATE + BLOCK          # bara det som spelats upp fylls på
    assert np.abs(np.concatenate(sink.chunks)).max() > 0.1


def test_ljudet_borjar_om_efter_ett_avbrott():
    sink = FakeSink()
    out = web_audio.WebOut(_tone_mixer(), sink, timer=False)
    out.pump()
    sink.chunks.clear()
    sink.now = 5.0                               # slingan stod still längre än kön räckte
    out.pump()
    assert sink.frames() / RATE < web_audio.AHEAD_S + BLOCK / RATE


def test_utan_ljud_i_sidan_ar_det_tyst():
    out = web_audio.WebOut(_tone_mixer(), None, timer=False)
    assert out.stream is None and out.error and out.pump() == 0
    out = web_audio.WebOut(_tone_mixer(), FakeSink(rate=48000), timer=False)
    assert out.stream is None and "48000" in out.error
    sink = FakeSink()
    out = web_audio.WebOut(_tone_mixer(), sink, timer=False)
    out.close()
    assert sink.cleared and out.stream is None and out.pump() == 0


class FakeAudio(FakeSink):
    """Sidans ljud med kanaler (`index.html`, `channel`): en kö per utgång, samma klocka."""

    def __init__(self):
        super().__init__()
        self.channels: list[FakeSink] = []

    def channel(self) -> FakeSink:
        ch = FakeSink()
        ch.time = self.time
        ch.closed = False
        ch.close = lambda: setattr(ch, "closed", True)
        self.channels.append(ch)
        return ch


def test_menyns_och_spelets_ljud_far_var_sin_kanal():
    # Medan ordern skrivs ut går menyns och spelets ljud samtidigt. I en delad kö varvades
    # deras block (hackigt och dubbelt så fort), och menyns clear tömde spelets kö.
    audio = FakeAudio()
    menu = web_audio.WebOut(_tone_mixer(), audio, timer=False)
    game = web_audio.WebOut(_tone_mixer(), audio, timer=False)
    menu.pump()
    game.pump()
    a, b = audio.channels
    assert not audio.chunks
    for ch in (a, b):
        assert web_audio.AHEAD_S <= ch.frames() / RATE < web_audio.AHEAD_S + BLOCK / RATE
    menu.close()
    assert a.closed and not b.closed and not b.cleared
    audio.now = 0.1
    assert game.pump() > 0 and menu.pump() == 0


def test_ljudet_fylls_pa_av_handelseslingan():
    sink = FakeSink()

    async def run():
        out = web_audio.WebOut(_tone_mixer(), sink)
        await asyncio.sleep(web_audio.TICK_S * 3)
        out.close()

    asyncio.run(run())
    assert sink.frames() > 0 and sink.cleared


class FakeSynth:
    """Webbläsarens talsyntes som `voices.WebSpeech` ser ut utåt."""

    def __init__(self, langs=("sv", "ru")):
        self.langs = set(langs)
        self.spoken: list[tuple[str, str, int]] = []
        self.live = None

    def voice(self, language):
        return {"sv": "Alva", "ru": "Milena"}.get(language) if language in self.langs else None

    def start(self, text, voice, rate):
        self.spoken.append((text, voice, rate))

        class Utt:
            done = False

            def poll(self):
                return 0 if self.done else None

            def terminate(self):
                self.done = True

        self.live = Utt()
        return self.live


def _web(monkeypatch, sink, synth):
    from ui import ambience, audio, voices
    monkeypatch.setattr(audio, "WEB", True)
    monkeypatch.setattr(ambience, "OUTPUT", lambda mixer: web_audio.WebOut(mixer, sink, timer=False))
    monkeypatch.setattr(voices, "backend", lambda: synth)


def test_ljudbordet_i_webblasaren(monkeypatch):
    from sim.events import EventBus
    from ui import audio
    sink, synth = FakeSink(), FakeSynth()
    _web(monkeypatch, sink, synth)
    board, note = audio.make_soundboard(EventBus(), True)
    assert note is None and board.available and board.speaks_russian
    assert isinstance(board.player, audio.WebPlayer)
    assert board.player.play("ping", 0.5) > 0          # larm och hydrofonljud i mixern
    board.out.pump()
    assert np.abs(np.concatenate(sink.chunks)).max() > 0.01
    board.player.speak("Jest", 180, "Milena")
    assert synth.spoken == [("Jest", "Milena", 180)] and board.player.speaking()
    board.toggle()                                       # ljudet av: repliken tystnar
    assert synth.live.done and not board.player.speaking()
    board.close()
    assert sink.cleared


def test_webblasaren_utan_ljud_eller_svensk_rost(monkeypatch):
    from sim.events import EventBus
    from ui import audio
    _web(monkeypatch, None, FakeSynth())
    board, note = audio.make_soundboard(EventBus(), True)
    assert not board.available and note == audio.NO_WEB_SOUND
    _web(monkeypatch, FakeSink(), FakeSynth(langs=("ru",)))
    board, note = audio.make_soundboard(EventBus(), True)
    assert board.available and not board.speech and "svensk röst" in note
    assert audio.sound_available()


@pytest.mark.slow
def test_menyljudet_utan_trad(monkeypatch):
    from ui.menu_audio import MenuSound
    sink = FakeSink()
    menu = MenuSound(out_factory=lambda m: web_audio.WebOut(m, sink, timer=False),
                     threaded=False, voice=lambda _t: None)
    assert menu.ready.is_set() and "music" in menu.mixer.samples
    menu.radio("Говорит Москва")                         # utan röst: bara inställningen
    assert not menu.on_air
    menu.out.pump()
    assert np.abs(np.concatenate(sink.chunks)).max() > 0.01
    menu.close()
    assert sink.cleared
