"""Sonarrummets takt: en jakt nära ska inte dränka loggen."""
import random

from sim.events import BearingObserved, ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.sonar import TransientHeard
from sim.stations.sonar_room import BEARING_MIN_GAP_S, SonarRoom
from sim.tma import BearingObs


def _game(seed=1):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, g.station(SonarRoom), reports


def _settle(g):
    for _ in range(5):
        g.tick()


def test_a_fast_moving_bearing_is_called_at_most_once_a_minute():
    g, sonar, reports = _game()
    g.knowledge.on_detection("S-9", 0)
    for t in range(1, 181):                         # jagaren cirklar nära: 2°/s
        g.world.time = t
        g.bus.publish(BearingObserved(t, BearingObs(t, (2.0 * t) % 360, 1.0, 0.0, 0.0, 0.0,
                                                    se=10.0, designation="S-9")))
        sonar._maybe_call_bearing("S-9")
    _settle(g)
    calls = [r for r in reports if r.type == "sonar.bearing"]
    assert 2 <= len(calls) <= 180 // BEARING_MIN_GAP_S + 1


def test_a_missed_ping_does_not_flip_the_ping_rate_back_and_forth():
    for seed in range(1, 4):
        g, sonar, reports = _game(seed)
        t = 100
        for gap in (9, 9, 9, 22, 9, 9, 23, 9, 9, 9):  # anfallstakt med två missade pingar
            t += gap
            g.world.time = t
            sonar._on_sound(TransientHeard("ping", 45.0, 20.0, "S-9", rl=150.0))
        _settle(g)
        types = [r.type for r in reports if r.data.get("designation") == "S-9"]
        assert types.count("sonar.ping.fast") == 1 and "sonar.ping.slow" not in types, seed


def test_the_ping_rate_falls_after_two_long_gaps():
    g, sonar, reports = _game()
    t = 100
    for gap in (9, 9, 9, 30, 30):
        t += gap
        g.world.time = t
        sonar._on_sound(TransientHeard("ping", 45.0, 20.0, "S-9", rl=150.0))
    _settle(g)
    types = [r.type for r in reports if r.data.get("designation") == "S-9"]
    assert types.count("sonar.ping.fast") == 1 and types.count("sonar.ping.slow") == 1
