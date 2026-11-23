"""Döda sektorn akterut i alla scenarier (2026-11-23) och det som följde: sonars gir för tappade
kontakter akterut, skydden för lyssningsgiren, vakthavandes nej till periskopdjup under stark radar,
navigatörens blick framåt med bestickets osäkerhet."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import BAFFLE_DEG
from sim.reports import Quality
from sim.scenario import SCENARIOS, build_scenario
from sim.stations.navigation import NavigationStation
from sim.stations.navigation.tasks import Attack
from sim.stations.officer import OfficerStation
from sim.stations.sonar_room import SonarRoom
from sim.tma import BearingObs


def _game(key="kuba", seed=1):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed, warm_up=False)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()


def test_every_scenario_has_the_baffles():
    for key in SCENARIOS:
        g = Game(build_scenario(key, random.Random(1)), seed=1, warm_up=False)
        assert g.world.own.baffle_deg == BAFFLE_DEG, key


def _lost_astern(g, designation="S-9"):
    """En kontakt som sonar tappade för en minut sedan, sista bäringen rakt akterut."""
    st = g.world.own.state
    st.course = st.ordered_course = 0.0
    st.speed = st.ordered_speed = 5.0
    st.depth = st.ordered_depth = 60.0
    g.knowledge.on_detection(designation, g.now)
    tr = g.knowledge.tracks[designation]
    ex, ey = g.own_position_estimate()
    tr.observations.append(BearingObs(g.now, 180.0, 1.0, ex, ey, 0.0, designation=designation))
    tr.classification, tr.class_quality = "stort fartyg, ångturbiner, två axlar", Quality.GOD
    tr.held = False
    return tr


def test_sonar_suggests_a_turn_for_a_contact_lost_astern_once():
    g, reports = _game()
    _lost_astern(g)
    _run(g, 90)
    sug = [r for r in reports if r.type == "sonar.suggest.astern_lost"]
    assert len(sug) == 1
    assert sug[0].data["order"] in ("kurs 090", "kurs 270")
    _run(g, 15 * 60)                                       # samma tappade kontakt: inte igen
    assert len([r for r in reports if r.type == "sonar.suggest.astern_lost"]) == 1


def test_no_astern_turn_while_the_navigator_steers():
    g, reports = _game()
    _lost_astern(g)
    g.station(NavigationStation).steer = Attack("S-1")
    g.station(SonarRoom)._astern_lost_watch()
    _run(g, 20)
    assert not any(r.type == "sonar.suggest.astern_lost" for r in reports)


def test_the_officer_says_no_to_periscope_depth_under_a_very_strong_radar():
    g, _ = _game()
    off = g.station(OfficerStation)
    st = g.world.own.state
    st.depth = st.ordered_depth = 60.0
    assert not off.vetoes("periskopdjup")
    off._esm_last["R1"] = ("mycket stark", g.now)
    assert off.vetoes("periskopdjup") and off.vetoes("fix")
    assert not off.vetoes("djup 100")
    g.world.time += 400                                    # radarn är inte längre färsk
    assert not off.vetoes("periskopdjup")


def test_the_navigator_looks_further_ahead_the_less_sure_the_dead_reckoning():
    g, _ = _game("clyde")
    nav = g.station(NavigationStation)
    st = g.world.own.state
    st.speed = 5.0
    sure = nav.chart_ahead(st.course)
    nav.last_fix_t = g.now - 4 * 3600                     # gammalt bestick: större osäkerhet
    unsure = nav.chart_ahead(st.course)
    assert nav.uncertainty() > 0.5
    assert unsure[0] <= sure[0]                            # minst lika grunt, för den ser längre


def test_no_turn_to_find_a_hunter_we_lost_astern():
    g, reports = _game()
    tr = _lost_astern(g)
    tr.classification = "trolig ubåt"
    _run(g, 90)
    assert not any(r.type == "sonar.suggest.astern_lost" for r in reports)
