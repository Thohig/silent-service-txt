"""Rapporten vid sambandstillfället (kuba-kort): målet, radions råd och sonarens hänsyn."""
import random

import pytest

from sim.enemy import DestroyerAI
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import (KUBA_SHORT_WARM_S, KUBA_SHORT_WINDOW_IN_S, KUBA_SHORT_WINDOW_S,
                          SCENARIOS, build_scenario, default_scenario)
from sim.goals import ReportGoal
from sim.stations.radio import RadioStation
from sim.stations.sonar_room import SonarRoom


def _game(window_at=60, report=True, seed=3):
    sc = default_scenario(random.Random(seed))
    sc.radio_windows = [window_at]
    sc.radio_window_len = 300
    sc.report_required = report
    sc.world.goals.append(ReportGoal(window_at, window_at + 300, "reported", "report_missed",
                                     contact_sigma_nm=0.5))
    g = Game(sc, seed=seed)
    types = []
    g.bus.subscribe(ReportDelivered, lambda e: types.append((e.report.type, e.report.data)))
    return g, types


def _far(g):
    dd = next(a for a in g.world.ais if isinstance(a, DestroyerAI))
    dd.vessel.state.x, dd.vessel.state.y = 19.5, 19.5           # långt bort, tyst
    return dd


def test_no_report_in_the_window_fails():
    g, _ = _game()
    _far(g)
    g.world.time = 359
    g.tick()
    assert g.world.outcome["outcome"] == "report_missed"


def test_report_sent_and_no_contact_succeeds_but_a_fix_blocks_it():
    g, _ = _game()
    dd = _far(g)
    g.world.mission["last_report_t"] = 120
    o = g.world.own.state
    dd.start_hunt(o.x, o.y, 100, 0.1, t=0)                       # ett skarpt datum på oss
    g.world.time = 360
    g.world._check_outcome()
    assert g.world.outcome is None
    dd.datum.sigma = 1.5                                         # bara pejlingen av sändningen
    g.world._check_outcome()
    assert g.world.outcome["outcome"] == "reported"


def test_radio_suggests_sending_in_the_window_at_periscope_depth():
    g, types = _game(window_at=10)
    _far(g)
    g.command("periskopdjup, fart 3")
    for _ in range(200):
        g.tick()
        if g.active_suggestion() and g.active_suggestion()[0] == "sänd rapport":
            break
    assert any(t == "radio.suggest.report" and d.get("order") == "sänd rapport" for t, d in types)
    g.command("ja")
    for _ in range(40):
        g.tick()
    assert g.world.mission.get("last_report_t") is not None


def test_radio_waits_when_the_plot_has_a_threat_close():
    g, types = _game(window_at=700)
    radio = g.station(RadioStation)
    radio._threat_near = lambda: ("S-1", 3.2)
    g.world.time = 700 - 600
    for _ in range(15):
        g.tick()
    assert any(t == "radio.wait" for t, _ in types)
    assert not any(t == "radio.prewarn" for t, _ in types)
    radio._threat_near = lambda: None
    for _ in range(45):
        g.tick()
    assert any(t == "radio.clear" and d.get("order") == "periskopdjup" for t, d in types)


def test_sonar_does_not_send_us_under_the_layer_while_up_for_the_radio():
    g, _ = _game(window_at=60)
    g.command("antenndjup")
    sonar = g.station(SonarRoom)
    g.world.time = 70
    assert sonar._up_for_radio()
    assert all(p.key != "idle_layer" for p in sonar.idle_proposals())


@pytest.mark.slow
def test_kuba_short_hands_over_with_the_destroyer_plotted_and_the_window_ahead():
    assert SCENARIOS["kuba-kort"].minutes
    plotted = 0
    for seed in range(4):
        g = Game(build_scenario("kuba-kort", random.Random(seed)), seed=seed, warm_up=False)
        g.warm_up()
        assert g.now == KUBA_SHORT_WARM_S and not g.over
        radio = g.station(RadioStation)
        assert radio.windows == [KUBA_SHORT_WARM_S + KUBA_SHORT_WINDOW_IN_S]
        assert g.world.patrol_end > KUBA_SHORT_WARM_S + KUBA_SHORT_WINDOW_IN_S + KUBA_SHORT_WINDOW_S
        plotted += any(t.threat and t.solution is not None for t in g.knowledge.tracks.values())
        types = []
        g.bus.subscribe(ReportDelivered, lambda e: types.append(e.report.type))
        for _ in range(20):
            g.tick()
        assert "radio.prewarn" in types or "radio.wait" in types
    assert plotted >= 3


def test_radio_does_not_suggest_sending_while_the_air_radar_is_close():
    from sim.events import AirRadarHeard
    from sim.stations import OfficerStation
    g, types = _game(window_at=10)
    _far(g)
    off = g.station(OfficerStation)
    heard = ["stark"]                                            # radarvarnaren hör flyget nära
    off._esm_air = lambda: g.bus.publish(AirRadarHeard(g.now, heard[0]))
    g.command("periskopdjup, fart 3")
    for _ in range(200):
        g.tick()
    assert not any(d.get("order") == "sänd rapport" for _, d in types)
    heard[0] = "medel"
    for _ in range(40):
        g.tick()
    assert any(d.get("order") == "sänd rapport" for _, d in types)


def test_radio_suggests_going_up_again_when_the_aircraft_has_been_quiet():
    from sim.events import AirRadarHeard
    from sim.stations.radio import AIR_QUIET_S
    g, types = _game(window_at=10)
    _far(g)
    g.command("djup 60, fart 3")
    for _ in range(20):
        g.tick()
    g.bus.publish(AirRadarHeard(g.now, "mycket stark"))          # flyget drev ned oss
    t0 = g.now
    while g.now < t0 + AIR_QUIET_S - 2:
        g.tick()
    assert not any(t == "radio.suggest.air_clear" for t, _ in types)
    for _ in range(30):                                          # förslaget når kaptenen
        g.tick()
    assert any(t == "radio.suggest.air_clear" and d.get("order") == "periskopdjup" for t, d in types)


def test_air_clear_needs_time_left_in_the_window():
    from sim.events import AirRadarHeard
    from sim.stations.radio import AIR_LEFT_S
    g, types = _game(window_at=10)                               # fönstret stänger 310
    _far(g)
    g.command("djup 60, fart 3")
    for _ in range(30):
        g.tick()
    g.world.time = 310 - AIR_LEFT_S
    g.bus.publish(AirRadarHeard(g.now - 200, "stark"))
    for _ in range(60):
        g.tick()
    assert not any(t == "radio.suggest.air_clear" for t, _ in types)
