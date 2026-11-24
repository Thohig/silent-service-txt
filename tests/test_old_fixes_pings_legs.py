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


def test_navigator_does_not_suggest_the_bottom_again_after_being_bombed_there():
    """Jagad frö 61: bombade på botten, lättade, och 9 min senare föreslog navigatören botten igen
    med samma jagare kvar ovanför (sänkta där)."""
    from sim.events import ChargeHeard
    from sim.reports import Quality
    from sim.stations.navigation import NavigationStation
    from sim.stations.navigation.common import SETTLE_AFTER_BOMBED_S
    g = Game(build_scenario("jagad", random.Random(1)), seed=1, warm_up=False)
    nav, k, sys = g.station(NavigationStation), g.knowledge, g.world.own.sys
    nav.bottom_here = lambda: (150.0, "sand")
    nav._dive_forbidden_here = lambda: False
    k.threat_held = lambda: True
    k.hunt_t = g.now
    assert nav._settle_proposal() is not None
    sys.on_bottom = True
    g.bus.publish(ChargeHeard(g.now, True, Quality.GOD, True, "sonar", 90.0))
    nav._settle_watch()
    sys.on_bottom = False                            # vi lättade
    k.charges.clear()                                # laddningarna är gamla nu
    k.hunt_t = g.now
    assert nav._settle_proposal() is None            # jagade: inte botten igen
    k.hunt_t = -10**9                                # jakten är över: botten går igen
    assert nav._settle_proposal() is not None
    nav._bombed_on_bottom_t -= SETTLE_AFTER_BOMBED_S # länge sedan: botten går igen under jakt
    k.hunt_t = g.now
    assert nav._settle_proposal() is not None


def _pinger_room():
    g = Game(build_scenario("kuba", random.Random(2)), seed=2, warm_up=False)
    g.world.ais.clear()
    return g, g.station(SonarRoom)


def test_two_pingers_in_almost_the_same_bearing_stay_apart_on_their_strength():
    """Jagad-kort frö 51: två jagare som sonar hållit isär drog ihop sig till 4°, och den svaga tog
    båda pingarna; den starka som sedan passerade över oss blev 'Någon söker' igen."""
    g, sonar = _pinger_room()
    t = 100
    for i in range(16):                                # först långt isär, sedan 4° isär
        t += 4
        g.world.time = t
        sep = max(4.0, 40.0 - 6.0 * (i // 2))
        b, rl = (20.0, 166.0) if i % 2 else (20.0 + sep, 173.0)
        sonar._on_sound(TransientHeard("ping", b, 80.0, None, rl))
    assert len(sonar._pings) == 2
    for p in sonar._pings.values():
        assert t - p["last"] <= 4                      # båda fick sina egna pingar till slutet
    assert sorted(round(p["rl"]) for p in sonar._pings.values()) == [166, 173]


def test_a_pingers_old_drift_is_not_carried_over_a_long_silence():
    """Jagad frö 51: en nära passages −1,7°/s framräknad över 91 s tystnad gav 55° fel och en ny pingare."""
    g, sonar = _pinger_room()
    t = 100
    for b in (60.0, 46.0, 32.0, 19.0):                 # nära passage: 1,7°/s
        t += 8
        g.world.time = t
        sonar._on_sound(TransientHeard("ping", b, 80.0, None, 158.0))
    g.world.time = t + 91
    sonar._on_sound(TransientHeard("ping", 28.0, 80.0, None, 158.0))
    assert len(sonar._pings) == 1
    (p,) = sonar._pings.values()
    assert p["bearing"] == 28.0 and "rate" not in p


def test_two_pingers_a_second_apart_are_two_pingers():
    """Krig-kort frö 17: två jagare 5° och 4 dB isär pingade med en sekunds mellanrum; de blev en pingare i
    snabb takt med 2°/s drift, och varannan ping blev en ny: "Någon söker" 15 gånger på 10 min."""
    from sim.events import ReportDelivered
    g, sonar = _pinger_room()
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    t = 100
    for _ in range(12):
        t += 20
        for dt, b, rl in ((0, 109.0, 132.0), (1, 104.0, 136.0)):
            g.world.time = t + dt
            sonar._on_sound(TransientHeard("ping", b, 80.0, None, rl))
        g.tick()
    assert len(sonar._pings) == 2
    assert sorted(round(p["rl"]) for p in sonar._pings.values()) == [132, 136]
    assert not any(p["fast"] for p in sonar._pings.values())


def test_a_double_ping_from_one_pinger_is_the_same_pinger():
    """Vid ett nytt datum pingar jagaren igen en sekund senare: samma nivå och bäring, samma pingare."""
    g, sonar = _pinger_room()
    for t, b in ((100, 50.0), (120, 51.0), (121, 49.5)):
        g.world.time = t
        sonar._on_sound(TransientHeard("ping", b, 80.0, None, 150.0))
    assert len(sonar._pings) == 1
