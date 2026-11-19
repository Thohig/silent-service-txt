"""Tystnad i båten och skrovknak under jakt (H1)."""
import random

from sim import acoustics
from sim.crew import Role
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import default_scenario
from sim.stations.officer import HUSH_LIFT_S, OfficerStation


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts, w.ais = [], []
    reports, creaks = [], []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    orig = w.emit

    def emit(tr):
        if tr.kind == "creak":
            creaks.append((g.now, tr.depth, tr.level))
        orig(tr)
    w.emit = emit
    return g, reports, creaks


def _run(g, n):
    for _ in range(n):
        g.tick()


def _deep(g, depth=100.0, speed=15.0):
    st = g.world.own.state
    st.depth = st.ordered_depth = depth
    st.speed = st.ordered_speed = speed


def test_fast_dive_creaks_every_25_m_and_slow_does_not():
    g, _, creaks = _game()
    _deep(g, 100, 15)
    g.command("djup 200")
    _run(g, 150)
    assert 3 <= len(creaks) <= 4
    assert all(lv == acoustics.CREAK_LEVEL for *_, lv in creaks)
    g, _, creaks = _game()
    _deep(g, 100, 3)
    g.command("fart 3")
    g.command("djup 200")
    _run(g, 300)
    assert creaks == []


def test_engineer_mentions_the_creak_only_when_hunted():
    g, reports, creaks = _game()
    _deep(g, 100, 15)
    g.command("djup 200")
    _run(g, 120)
    assert creaks and not any(r.type == "hull.groan" for r in reports)
    g, reports, creaks = _game()
    g.knowledge.hunted = lambda now: True
    _deep(g, 100, 15)
    g.command("djup 200")
    _run(g, 120)
    groans = [r for r in reports if r.type == "hull.groan"]
    assert len(groans) == 1 and "ned" in groans[0].text


def test_hunted_on_the_creep_motor_the_boat_goes_quiet_and_alarms_still_shout():
    g, reports, _ = _game()
    _deep(g, 100, 4)
    hunted = [True]
    g.knowledge.hunted = lambda now: hunted[0]
    g.command("smygmotor")
    _run(g, 15)
    assert any(r.type == "off.hush" for r in reports)
    assert g.station(OfficerStation).hushed
    g.command("kurs 120")
    g.say(Role.SONAR, "sonar.torpedo", {"bearing": 10.0}, alarm=True)
    _run(g, 15)
    ack = [r for r in reports if r.role and r.type not in ("off.hush",) and not r.alarm
           and r.kind != "system"]
    assert ack and all(r.data.get("hushed") for r in ack[-1:])
    assert all(not r.data.get("hushed") for r in reports if r.alarm)
    hunted[0] = False
    _run(g, HUSH_LIFT_S + 5)
    assert any(r.type == "off.hush.end" for r in reports)
    assert not g.station(OfficerStation).hushed


def test_hushed_reports_are_spoken_low():
    from types import SimpleNamespace
    from ui.audio import speech_effect
    from sim.reports import Report
    r = Report(0, "Sonar", "sonar.bearing", {"hushed": True}, role="sonar")
    st = SimpleNamespace(command="captain", captain_at="central")
    assert speech_effect(r, st) == "hushed"
    r.alarm = True
    assert speech_effect(r, st) is None
