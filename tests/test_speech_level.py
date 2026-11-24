"""Talnivån (ui/audio.py): vad som läses upp. Larm och förslag alltid (utom "tal av"),
rutinen bara med "tal allt", kvittensen kort, inga upprepningar och tystare vid tidskomprimering."""
import random
from types import SimpleNamespace

import pytest

from sim.events import EventBus, ReportDelivered
from sim.game import Game
from sim.reports import Quality, Report
from sim.scenario import build_scenario
from ui.audio import (ALARMS, ALL, IMPORTANT, LEVELS, REPEAT_S, SILENT, SHORT_ACK_RU, SoundBoard,
                      speech_rank, spoken)


class Player:
    def __init__(self):
        self.said = []

    def play(self, cue, pan=0.0, volume=1.0):
        return 0.0

    def speak(self, text, rate, voice=None, **kw):
        self.said.append(text)

    def speaking(self):
        return False

    def stop(self):
        pass


def _board(level=IMPORTANT, scale=1, t=0, ru_voice=None):
    bus = EventBus()
    b = SoundBoard(bus, Player(), level=level, ru_voice=ru_voice)
    b._status = SimpleNamespace(time_scale=scale, sim_time=t, command="captain", captain_at="central")
    return bus, b


def _r(type="x", kind="info", role="sonar", alarm=False, quality=None, **data):
    return Report(0, "Sonar", type, data=data, role=role, kind=kind, alarm=alarm, quality=quality,
                  text="Kapten, något.", speech="Командир.")


def _queued(level, r, **kw) -> bool:
    bus, b = _board(level, **kw)
    bus.publish(ReportDelivered(0, r))
    return bool(b.queue)


def test_rank_alarms_and_suggestions_first_routine_last():
    assert speech_rank(_r(alarm=True)) == speech_rank(_r(kind="suggest")) == 2
    assert speech_rank(_r("sonar.new_contact", "contact")) == 1
    assert speech_rank(_r("sonar.bearing", "contact")) == 0
    assert speech_rank(_r("sonar.bearing", "contact", alarm=True)) == 2
    assert speech_rank(_r("nav.depth.done", "done", role="navigator")) == 0
    assert speech_rank(_r("bridge.shut", "done", role="officer")) == 1


@pytest.mark.parametrize("level", LEVELS)
def test_what_each_level_reads(level):
    routine, important = _r("sonar.bearing", "contact"), _r("sonar.new_contact", "contact")
    alarm, suggest = _r("fire", alarm=True), _r("x.suggest", "suggest", order="fart 5")
    want = {ALL: (True, True, True), IMPORTANT: (False, True, True), ALARMS: (False, False, True),
            SILENT: (False, False, False)}[level]
    assert _queued(level, routine) == want[0]
    assert _queued(level, important) == want[1]
    assert _queued(level, alarm) == want[2] and _queued(level, suggest) == want[2]


def test_nothing_with_alarm_or_suggestion_is_ever_dropped_below_silent():
    for level in (ALL, IMPORTANT, ALARMS):
        for scale in (1, 2, 8, 64):
            bus, b = _board(level, scale=scale)
            for i in range(3):          # samma larm tre gånger: alla läses upp
                bus.publish(ReportDelivered(0, _r("sonar.ping.close", "contact", alarm=True,
                                                  designation="S-1")))
            assert len(b.queue) == 3, (level, scale)


def test_short_ack_except_with_all():
    ack = _r("nav.course.ack", "ack", role="navigator")
    for level, ru in ((IMPORTANT, "Milena"), (ALL, "Milena"), (IMPORTANT, None)):
        bus, b = _board(level, ru_voice=ru)
        b.language = "ru"
        bus.publish(ReportDelivered(0, ack))
        text = " ".join(t for _, t in b.queue[0].parts)
        if level == ALL:
            assert text == "Командир."
        elif ru:
            assert text == SHORT_ACK_RU
        else:
            assert text.startswith("Jest") and "Kapten" not in text


def test_the_same_thing_about_the_same_contact_once_per_repeat_s():
    bus, b = _board()
    r = _r("sonar.classified", "contact", designation="S-1", quality=Quality.OSAKER)
    bus.publish(ReportDelivered(0, r))
    bus.publish(ReportDelivered(0, r))
    assert len(b.queue) == 1
    bus.publish(ReportDelivered(0, _r("sonar.classified", "contact", designation="S-2")))
    assert len(b.queue) == 2                                    # en annan kontakt
    bus.publish(ReportDelivered(0, _r("sonar.classified", "contact", designation="S-1",
                                      quality=Quality.GOD)))
    assert len(b.queue) == 3                                    # bättre kvalitet: sägs
    b._status.sim_time = REPEAT_S + 1
    bus.publish(ReportDelivered(0, r))
    assert len(b.queue) == 4                                    # efter REPEAT_S igen
    bus_all, b_all = _board(ALL)
    for _ in range(2):
        bus_all.publish(ReportDelivered(0, r))
    assert len(b_all.queue) == 2                                # "tal allt": allt


def test_time_compression_quiets_routine_then_all_but_alarms():
    routine, important = _r("sonar.bearing", "contact"), _r("sonar.new_contact", "contact")
    assert _queued(ALL, routine, scale=1) and not _queued(ALL, routine, scale=2)
    assert _queued(ALL, important, scale=4) and not _queued(ALL, important, scale=8)
    assert _queued(ALL, _r("fire", alarm=True), scale=64)


def test_silent_level_clears_the_queue_and_skips_announcements():
    bus, b = _board(ALL)
    bus.publish(ReportDelivered(0, _r("sonar.new_contact", "contact")))
    b.set_level(SILENT)
    assert not b.queue
    b.announce("Боевая тревога!", "Stridslarm!")
    assert not b.queue
    with pytest.raises(ValueError):
        b.set_level("mycket")


@pytest.mark.slow
def test_important_level_reads_about_half_as_much_in_play():
    """En spelad timme med ja-boten: "tal viktigt" läser upp mindre än hälften så mycket text som
    "tal allt", och varje larm och förslag som "tal allt" läser."""
    def run(level):
        g = Game(build_scenario("konvoj-kort", random.Random(1)), seed=1)
        bus, b = g.bus, SoundBoard(g.bus, Player(), level=level, ru_voice="Milena")
        n = {"chars": 0, "alarms": 0}
        due = []

        def on(e):
            r = e.report
            if r.kind == "suggest":
                due.append(g.now + 20)
            b._status = SimpleNamespace(time_scale=1, sim_time=g.now, command="captain",
                                        captain_at="central")
        bus.subscribe(ReportDelivered, on)
        for _ in range(3600):
            if g.over:
                break
            g.tick()
            for line in b.queue:
                n["chars"] += sum(len(t) for _, t in line.parts)
                n["alarms"] += line.urgent
            b.queue.clear()
            if due and g.now >= due[0]:
                due.pop(0)
                if g.active_suggestion():
                    g.command("ja")
        return n
    full, important = run(ALL), run(IMPORTANT)
    assert important["chars"] < 0.6 * full["chars"]
    assert important["alarms"] == full["alarms"]


@pytest.mark.slow
def test_the_log_keeps_everything_whatever_the_speech_level(tmp_path):
    """Talnivån styr bara uppläsningen: loggboken får varje rapport, också rutinen."""
    import asyncio

    from ui.app import SubApp
    from ui.widgets import ReportLog

    async def run():
        app = SubApp(seed=1, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.press("enter", "enter")
            await pilot.press(*"tal larm", "enter")
            seen: list[str] = []
            app.game.bus.subscribe(ReportDelivered, lambda e: seen.append(e.report.text))
            await pilot.press(*"kurs 090", "enter")
            for _ in range(120):
                app.game.tick()
            await pilot.pause(0.3)
            entries = " ".join(str(e) for e in app.gs().query_one("#log", ReportLog).entries)
            assert seen and all(t.split(",")[0] in entries for t in seen)
            assert app.speech_level == ALARMS

    asyncio.run(run())
