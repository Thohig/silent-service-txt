"""Sonar säger när bara pingarna hörs från en tappad kontakt; plottet ger ett benförslag i taget."""
import random

import pytest

from sim.events import ContactLost, ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.sonar import TransientHeard
from sim.stations.plot import LEG_GAP_S
from sim.stations.sonar_room import SonarRoom


def _sonar_reports(lost: bool):
    g = Game(build_scenario("kuba", random.Random(1)), seed=1, warm_up=False)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.knowledge.on_detection("S-2", 0)
    if lost:
        g.bus.publish(ContactLost(0, "S-2"))
    sonar = g.station(SonarRoom)
    sonar._on_sound(TransientHeard("ping", 40.0, 80.0, "S-2"))
    for _ in range(10):
        g.tick()
    return [r for r in reports if r.type == "sonar.ping.close"]


def test_pings_from_a_lost_contact_say_only_the_pings_are_heard():
    r = _sonar_reports(lost=True)
    assert r and r[0].data["lost"] and "bara pingarna" in r[0].text
    r = _sonar_reports(lost=False)
    assert r and not r[0].data.get("lost") and "bara pingarna" not in r[0].text


@pytest.mark.slow
def test_plot_gives_one_leg_suggestion_at_a_time():
    for seed in (1, 2, 3):
        g = Game(build_scenario("konvoj", random.Random(seed)), seed=seed)
        times = []
        g.bus.subscribe(ReportDelivered, lambda e: times.append(e.report.data.get("made_t", g.now))
                        if e.report.type == "plot.suggest" else None)
        for _ in range(100 * 60):
            g.tick()
        made = sorted(set(times))
        assert all(b - a >= LEG_GAP_S for a, b in zip(made, made[1:])), (seed, made)


def test_navigator_does_not_suggest_the_bottom_while_a_radio_window_waits():
    from sim.stations.navigation import NavigationStation
    from sim.stations.radio import RadioStation
    g = Game(build_scenario("kuba", random.Random(1)), seed=1, warm_up=False)
    nav, radio = g.station(NavigationStation), g.station(RadioStation)
    nav.bottom_here = lambda: (150.0, "sand")
    nav._dive_forbidden_here = lambda: False
    g.knowledge.threat_held = lambda: True
    radio.windows = []
    assert nav._settle_proposal() is not None
    radio.windows = [g.now + 120]                    # förvarningen gäller: radion ska upp
    assert nav._settle_proposal() is None
    g.knowledge.hunt_t = g.now                       # jagade: botten går före sambandet
    assert nav._settle_proposal() is not None
