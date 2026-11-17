"""Sonarvyn: vattenfallets element byggs ur kunskapen (aldrig sanningen)."""
import random

import pytest

from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.sonar_view import (BearingTrace, ContactLine, HeardMark, OwnTurn, SolutionTrace,
                            SonarView, TargetTurn, bearing_drift, drift_words, own_turns)


def _game(key="jagad-kort", seed=2):
    return Game(build_scenario(key, random.Random(seed)), seed=seed)


def test_bearing_drift_across_north():
    pts = [(t, (350 + t / 30) % 360) for t in range(0, 181, 5)]    # 2°/min medurs över 000
    assert bearing_drift(pts, 180) == pytest.approx(2.0, abs=0.01)
    back = [(t, (10 - t / 60) % 360) for t in range(0, 181, 5)]
    assert bearing_drift(back, 180) == pytest.approx(-1.0, abs=0.01)
    assert bearing_drift(pts[:3], 180) is None                        # för få
    assert bearing_drift(pts, 1000) is None                           # för gamla


def test_drift_words():
    assert drift_words(None) == "drift okänd"
    assert drift_words(0.1) == "bäringen står"
    assert drift_words(2.04) == "drar höger 2,0°/min"
    assert drift_words(-12.6) == "drar vänster 13°/min"


def test_own_turns_from_course_log():
    log = [(t, 90.0) for t in range(0, 100, 10)]
    log += [(100 + 10 * i, 90.0 + 10 * i) for i in range(1, 7)]       # gir till 150
    log += [(170 + 10 * i, 150.0) for i in range(1, 6)]
    log += [(230, 152.0), (240, 152.0)]                               # liten rättelse
    log += [(250, 140.0), (260, 128.0), (270, 128.0)]                 # gir babord 24°
    turns = own_turns(log)
    assert [(round(t.course_from), round(t.course_to)) for t in turns] == [(90, 150), (152, 128)]
    assert own_turns([(0, 355.0), (10, 5.0), (20, 15.0), (30, 15.0)])[0].course_to == 15.0


def test_heading_at():
    v = SonarView("12:00:00", 100, 0, 200.0)
    from sim.sonar_view import OwnHeading
    v.items.append(OwnHeading(((0, 10.0), (50, 20.0))))
    assert v.heading_at(-5) == 200.0 and v.heading_at(10) == 10.0 and v.heading_at(70) == 20.0


@pytest.mark.slow
def test_waterfall_from_knowledge_only():
    g = _game()
    g.command("kurs 90")
    for _ in range(900):
        g.tick()
    v = g.sonar()
    k = g.knowledge
    traces = {t.designation: t for t in v.traces}
    assert traces and set(traces) <= set(k.tracks)
    for d, tr in traces.items():
        obs = [o for o in k.tracks[d].observations if o.source in ("sonar", "ping", "aktiv")]
        assert tr.points[-1] == (obs[-1].t, obs[-1].bearing, obs[-1].se)
        assert tr.kind == "threat"           # jagare, klassade
    lines = v.lines
    assert {c.designation for c in lines} == set(traces)
    assert all(c.solution_quality in Quality for c in lines)
    assert any(c.drift is not None for c in lines)
    assert v.of(HeardMark) and all(0 <= m.bearing < 360 for m in v.of(HeardMark))
    assert v.of(SolutionTrace)
    turns = v.of(TargetTurn)
    for d in {t.designation for t in turns}:     # ett märke per kontakt och fem minuter
        ts = sorted(t.t for t in turns if t.designation == d)
        assert all(b - a >= 300 for a, b in zip(ts, ts[1:]))
    assert v.of(OwnTurn)                          # vi girade
    truth_ids = {e.id for e in g.world.contacts}
    text = repr(v.items)
    assert not any(f"'{i}'" in text for i in truth_ids)


def test_no_contacts_no_traces():
    g = _game("ovning", seed=1)
    for _ in range(30):
        g.tick()
    v = g.sonar()
    assert v.traces == [] and v.lines == []
    assert v.heading and v.heading[-1] == (g.now, round(g.world.own.state.course, 1))
