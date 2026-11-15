"""Ljud: besättningens repliker och larm styrs bara av levererade rapporter."""
import asyncio
import random

import numpy as np

from sim.events import EventBus, OwnSoundMade, ReportDelivered, SoundHeard
from sim.game import Game
from sim.reports import Report
from sim.scenario import build_scenario
from ui.app import SubApp
from ui.audio import (MAX_QUEUE, MIN_VOLUME, STALE_S, SoundBoard, cue_for, pan_of_bearing,
                      RATE, speech_parts, speech_text, stereo, synth_cues, synth_transients,
                      write_wav)


class RecordingPlayer:
    def __init__(self, cue_len: float = 1.0):
        self.cues: list[str] = []
        self.played: list[tuple[str, float, float]] = []
        self.voices: list[str | None] = []
        self.said: list[tuple[str, int]] = []
        self.busy_until = 0.0
        self.now = 0.0
        self.cue_len = cue_len
        self.stopped = 0

    def play(self, cue, pan=0.0, volume=1.0):
        self.cues.append(cue)
        self.played.append((cue, pan, volume))
        return self.cue_len

    def speak(self, text, rate, voice=None):
        self.said.append((text, rate))
        self.voices.append(voice)
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
        limit = 8.0 if name.startswith("bells") else 4.0      # åtta glas tar sin tid
        assert 0.1 < len(s) / 22050 < limit, name
        assert np.max(np.abs(s)) <= 1.0 and np.isfinite(s).all(), name
        write_wav(tmp_path / f"{name}.wav", s)
    assert len(list(tmp_path.glob("*.wav"))) == 6 + 8


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
            await pilot.press("ctrl+t")                     # inget händer utan ljud
            assert not app.sound.enabled

    asyncio.run(run())


# --- steg 2: hydrofonen -------------------------------------------------------
def test_heard_ping_is_panned_by_relative_bearing_and_scaled_by_strength():
    bus = EventBus()
    p = RecordingPlayer()
    board = SoundBoard(bus, p, heading=lambda: 90.0)
    bus.publish(SoundHeard(0, "ping", 0.0, se=5.0))       # rakt babord, svag
    board.update(1.0)
    bus.publish(SoundHeard(1, "ping", 180.0, se=200.0))   # rakt styrbord, stark
    (c1, pan1, v1), (c2, pan2, v2) = p.played
    assert c1 == c2 == "ping"
    assert pan1 < -0.99 and pan2 > 0.99
    assert MIN_VOLUME <= v1 < 0.4 and v2 == 1.0


def test_nuclear_explosion_and_own_sounds():
    bus, p, board = _board()
    bus.publish(SoundHeard(0, "explosion", 10.0, se=40.0))
    board.update(1.0)
    bus.publish(SoundHeard(1, "explosion", 10.0, se=190.0))
    bus.publish(OwnSoundMade(1, "launch"))
    bus.publish(OwnSoundMade(1, "ping"))
    bus.publish(SoundHeard(1, "echosounder", 10.0, se=40.0))   # inget ljud för det
    assert p.cues == ["explosion", "nuclear", "launch", "own_ping"]


def test_same_sound_in_quick_succession_plays_once():
    bus, p, board = _board()
    for _ in range(5):                                    # tidskomprimering
        bus.publish(SoundHeard(0, "ping", 0.0, se=30.0))
    board.update(1.0)
    bus.publish(SoundHeard(1, "ping", 0.0, se=30.0))
    assert p.cues == ["ping", "ping"]


def test_silenced_board_ignores_sounds():
    bus, p, board = _board()
    board.toggle()
    bus.publish(SoundHeard(0, "ping", 0.0, se=30.0))
    bus.publish(OwnSoundMade(0, "blow"))
    assert p.cues == []


def test_pan_follows_port_and_starboard():
    assert pan_of_bearing(-90) == -1.0 and pan_of_bearing(90) == 1.0
    assert abs(pan_of_bearing(0)) < 1e-9 and abs(pan_of_bearing(180)) < 1e-9
    left = stereo(np.ones(4), -1.0)
    assert left[0, 0] > 0.9 and abs(left[0, 1]) < 1e-9


def test_transients_synthesize_to_valid_stereo_wav(tmp_path):
    for name, s in synth_transients().items():
        assert 0.1 < len(s) / 22050 < 6.0, name
        assert np.isfinite(s).all() and 0.3 < np.max(np.abs(s)) <= 1.0, name
        write_wav(tmp_path / f"{name}.wav", stereo(s, 0.5))


def test_sonar_publishes_heard_strength_in_a_real_game():
    """SoundHeard bär signalöverskottet från sensorn; ljudet behöver inget ur världen."""
    g = Game(build_scenario("kuba", random.Random(4)), seed=4)
    p = RecordingPlayer(cue_len=0.0)
    SoundBoard(g.bus, p, heading=lambda: g.status().course)
    heard = []
    g.bus.subscribe(SoundHeard, heard.append)
    g.command("aktiv sonar")
    for _ in range(3 * 3600):
        g.tick()
        if any(e.kind == "ping" for e in heard) or g.over:
            break
    assert "own_ping" in p.cues
    pings = [e for e in heard if e.kind == "ping"]
    assert pings and all(e.se > 0 for e in pings)
    assert "ping" in p.cues


def test_russian_phrase_is_spoken_by_russian_voice_only():
    bus, p = EventBus(), RecordingPlayer(cue_len=0.0)
    board = SoundBoard(bus, p, ru_voice="Milena")
    _deliver(bus, text="Jest, kurs 090.", role="navigator")
    t = 0.0
    while len(p.said) < 2 and t < 20:
        p.now = t
        board.update(t)
        t += 0.5
    assert p.said[0][0] == "Есть" and p.voices[0] == "Milena"
    assert p.said[1][0] == "kurs noll nio noll." and p.voices[1] is None


def test_without_russian_voice_swedish_voice_reads_everything():
    assert speech_parts("Jest, kurs 090.", None) == [(None, "Jest, kurs noll nio noll.")]
    assert speech_parts("Kapten, plottet.", "Milena") == [(None, "Kapten, plottet.")]


def test_battle_stations_sounds_the_revun():
    bus, p = EventBus(), RecordingPlayer(cue_len=0.0)
    SoundBoard(bus, p)
    _deliver(bus, text="Boevaja trevoga! Stridslarm.", type="off.battle_stations",
            role="officer", alarm=True)
    assert p.cues == ["revun"]
    revun = synth_cues()["revun"]
    assert 2.0 < len(revun) / RATE < 3.5 and np.max(np.abs(revun)) <= 1.0


def test_russian_mode_speaks_the_russian_report():
    bus, p = EventBus(), RecordingPlayer(cue_len=0.0)
    board = SoundBoard(bus, p, ru_voice="Milena")
    _deliver(bus, text="Jest, kurs 090.", speech="Есть, курс ноль девять ноль.", role="navigator")
    board.update(0.0)
    assert p.said[-1][0] == "Есть, курс ноль девять ноль." and p.voices[-1] == "Milena"
    assert not board.set_language("sv")
    p.busy_until = 0.0
    _deliver(bus, text="Kapten, plottet.", speech="Товарищ командир, планшет.", role="plot")
    board.update(1.0)
    assert p.said[-1][0] == "Kapten, plottet." and p.voices[-1] is None


def test_russian_mode_without_milena_falls_back_to_swedish():
    bus, p = EventBus(), RecordingPlayer(cue_len=0.0)
    board = SoundBoard(bus, p)
    assert not board.speaks_russian
    _deliver(bus, text="Kapten, plottet.", speech="Товарищ командир, планшет.", role="plot")
    board.update(0.0)
    assert p.said[-1][0] == "Kapten, plottet."


def test_ship_bell_strikes_the_glasses_on_the_half_hour_but_not_when_quiet():
    from dataclasses import replace

    from sim.game import StatusSnapshot
    from ui.audio import bells_for, synth_ship_bell

    assert [bells_for(h * 1800) for h in range(9)] == [8, 1, 2, 3, 4, 5, 6, 7, 8]
    assert len(synth_ship_bell(4)) > len(synth_ship_bell(1))
    _bus, p, board = _board()
    st = StatusSnapshot(clock=3590, sim_time=0, course=0.0, ordered_course=0.0, speed=5.0,
                        ordered_speed=5.0, depth=100.0, ordered_depth=100.0,
                        changing=frozenset(), time_scale=1, contacts_held=())
    board.ambient(st)                                   # första gången: bara noterat
    board.ambient(replace(st, clock=3605))              # 01:00 ⇒ två glas
    assert [c for c, *_ in p.played] == ["bells2"]
    board.ambient(replace(st, clock=5405, propulsion="electric"))   # tyst gång: ingen klocka
    board.ambient(replace(st, clock=7205, hunted=True))
    assert len(p.played) == 1


def test_announcement_speaks_russian_with_russian_voice_otherwise_swedish():
    from ui.telegram import crew_announcement
    for key, title in (("ovning", "Övning, oktober 1962"), ("kuba", "Kvadrat 7, oktober 1962"),
                       ("konvoj", "Konvojen, 28 oktober 1962")):
        ru, sv = crew_announcement(key, title)
        assert not any("a" <= ch.lower() <= "z" for ch in ru) and sv
    assert "Боевая тревога" in crew_announcement("konvoj", "Konvojen, 28 oktober 1962")[0]
    _bus, p, board = _board()
    board.ru_voice = "Milena"
    board.announce("Внимание экипажу.", "Till besättningen.")
    _run(board, p, 0.0, 3.0)
    assert p.voices == ["Milena"] and "Внимание" in p.said[0][0]
    _bus, p, board = _board()
    board.announce("Внимание экипажу.", "Till besättningen.")
    _run(board, p, 0.0, 3.0)
    assert p.voices == [None] and "besättningen" in p.said[0][0]
