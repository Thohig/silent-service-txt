"""Ljud: besättningens repliker och larm styrs bara av levererade rapporter."""
import asyncio
import random

import numpy as np

from sim.events import EventBus, ReportDelivered
from sim.game import Game
from sim.reports import Report
from sim.scenario import build_scenario
from ui.app import SubApp
from ui.audio import (MAX_QUEUE, STALE_S, SoundBoard, cue_for, speech_text, synth_cues,
                      write_wav)


class RecordingPlayer:
    def __init__(self, cue_len: float = 1.0):
        self.cues: list[str] = []
        self.said: list[tuple[str, int]] = []
        self.busy_until = 0.0
        self.now = 0.0
        self.cue_len = cue_len
        self.stopped = 0

    def play(self, cue):
        self.cues.append(cue)
        return self.cue_len

    def speak(self, text, rate):
        self.said.append((text, rate))
        self.busy_until = self.now + 2.0

    def speaking(self):
        return self.now < self.busy_until

    def stop(self):
        self.stopped += 1
        self.busy_until = 0.0


def _board(**kw):
    bus = EventBus()
    p = RecordingPlayer(**kw)
    return bus, p, SoundBoard(bus, p)


def _deliver(bus, **kw):
    r = Report(t_due=0, speaker="Sonar (Volkov)", type=kw.pop("type", "x"),
               role=kw.pop("role", "sonar"), **kw)
    bus.publish(ReportDelivered(0, r))


def _run(board, p, start, seconds, step=0.05):
    t = start
    while t < start + seconds:
        p.now = t
        board.update(t)
        t += step
    return t


def test_cues_follow_report_type_and_alarm():
    r = lambda **kw: Report(0, "", kw.pop("type", "x"), **kw)
    assert cue_for(r(type="sonar.ping.first", alarm=True)) == "general"
    assert cue_for(r(type="eng.blow", alarm=True)) == "klaxon"
    assert cue_for(r(type="fire", alarm=True)) == "fire"
    assert cue_for(r(type="sonar.new_contact", alarm=True)) == "attention"
    assert cue_for(r(type="eng.suggest.x", kind="suggest", data={"order": "fart 5"})) == "suggest"
    assert cue_for(r(type="nav.position")) is None


def test_speech_waits_for_alarm_and_previous_line():
    bus, p, board = _board(cue_len=2.0)
    board.update(0.0)
    _deliver(bus, type="sonar.ping.first", text="Kapten, sonar! Aktiv sonar.", alarm=True,
             kind="contact")
    _deliver(bus, type="nav.position", role="navigator", text="Vi står här.")
    assert p.cues == ["general"]
    _run(board, p, 0.0, 1.0)
    assert p.said == []                              # larmet ringer fortfarande
    _run(board, p, 1.0, 1.0)
    assert [s for s, _ in p.said] == ["Kapten, sonar! Aktiv sonar."]
    _run(board, p, 2.0, 2.5)
    assert [s for s, _ in p.said][-1] == "Vi står här."
    assert p.said[0][1] != p.said[1][1]               # olika roller, olika takt


def test_only_crew_lines_are_spoken():
    bus, p, board = _board()
    _deliver(bus, role="", kind="system", text="Hjälp …")
    _deliver(bus, text="Tabell", table=[["a"]])
    _run(board, p, 0.0, 1.0)
    assert p.said == []


def test_queue_drops_routine_lines_but_keeps_alarms():
    bus, p, board = _board(cue_len=0.0)
    board.update(0.0)
    p.busy_until = 1000.0                             # någon pratar länge
    _deliver(bus, type="sonar.new_contact", text="Ny kontakt!", alarm=True, kind="contact")
    for i in range(10):
        _deliver(bus, text=f"rutin {i}")
    assert len(board.queue) <= MAX_QUEUE
    assert any(ln.text == "Ny kontakt!" for ln in board.queue)
    board.update(STALE_S + 1)
    assert [ln.text for ln in board.queue] == ["Ny kontakt!"]


def test_toggle_silences_and_stops():
    bus, p, board = _board()
    assert board.toggle() is False
    assert p.stopped == 1
    _deliver(bus, type="fire", text="BRAND!", alarm=True)
    _run(board, p, 0.0, 5.0)
    assert p.cues == [] and p.said == []
    assert board.toggle() is True


def test_courses_are_read_digit_by_digit():
    assert speech_text("Kurs 090, aye.") == "Kurs noll nio noll, aj."
    assert speech_text("Aktiv sonar i bäring 047.") == "Aktiv sonar i bäring noll fyra sju."
    assert speech_text("Djup 300 meter.") == "Djup 300 meter."


def test_cues_synthesize_to_valid_wav(tmp_path):
    for name, s in synth_cues().items():
        assert 0.1 < len(s) / 22050 < 4.0, name
        assert np.max(np.abs(s)) <= 1.0 and np.isfinite(s).all(), name
        write_wav(tmp_path / f"{name}.wav", s)
    assert len(list(tmp_path.glob("*.wav"))) == 5


def test_headless_game_speaks_crew_reports():
    bus_game = Game(build_scenario("kuba", random.Random(2)), seed=2)
    p = RecordingPlayer(cue_len=0.0)
    board = SoundBoard(bus_game.bus, p)
    bus_game.command("kurs 090")
    t = 0.0
    for _ in range(30):
        bus_game.tick()
        t = _run(board, p, t, 2.5)
    assert any("noll nio noll" in s for s, _ in p.said)


def test_app_is_silent_by_default(tmp_path):
    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("enter")
            await pilot.press("enter")
            assert app.sound is not None and not app.sound.enabled
            await pilot.press("f8")                     # inget händer utan ljud
            assert not app.sound.enabled

    asyncio.run(run())
