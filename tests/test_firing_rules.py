"""Skyttebotens fynd (2026-11-23): vapen i fredstid, salvan med en tub och för nära,
omladdningen efter skottet."""
import random
from types import SimpleNamespace

import pytest

from sim.events import ReportDelivered
from sim.game import Game
from sim.goals import PeaceBroken
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.torpedo_room import TorpedoRoom
from sim.stations.torpedo_room.common import RELOAD_SUGGEST_S


def _game(key, seed=1):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    st = g.world.own.state
    st.depth = st.ordered_depth = 40.0
    st.speed = st.ordered_speed = 3.0
    g.tick()                                   # radion har läst ordern (krig eller inte)
    return g, reports


def _run(g, n=6):
    for _ in range(n):
        g.tick()


def _mock_target(g, rng=2.0):
    """S-1 som säkert klassad jagare med en lösning, träffpunkten `rng` nm bort."""
    torp = g.station(TorpedoRoom)
    if "S-1" not in g.knowledge.tracks:
        g.knowledge.on_detection("S-1", g.now)
    tr = g.knowledge.tracks["S-1"]
    tr.classification, tr.class_quality = "jagare, ångturbiner, två axlar", Quality.SAKER
    sol = SimpleNamespace(range_sigma=0.05, speed_sigma=0.5, speed=10.0, course_sigma=5.0,
                          course=90.0, quality=Quality.SAKER, x=0.0, y=0.0, t=g.now,
                          state=(0.0, 0.0, 0.0, 0.0), range_nm=rng)
    torp._aim = lambda s, load: (90.0, rng / 45 * 3600, rng)
    torp._solution_for = lambda d: (tr, sol)
    torp._neutrals_clear = lambda *a: True
    return torp


# --- fredstid ---------------------------------------------------------------------------
@pytest.mark.weapons_hold
def test_torpedo_room_asks_once_before_a_live_shot_in_peacetime():
    g, reports = _game("kuba")
    torp = g.station(TorpedoRoom)
    g.command("eld tub 1 kurs 090")
    _run(g)
    assert any(r.type == "torp.weapons_hold" for r in reports) and not torp.in_water
    g.command("eld tub 1 kurs 090")
    _run(g)
    assert len(torp.in_water) == 1


@pytest.mark.weapons_hold
def test_salvo_in_peacetime_is_asked_once_too():
    g, reports = _game("kuba")
    torp = _mock_target(g)
    g.command("salva S-1")
    _run(g)
    assert any(r.type == "torp.weapons_hold" for r in reports) and not torp.in_water
    g.command("salva S-1")
    _run(g)
    assert len(torp.in_water) == 3


@pytest.mark.weapons_hold
def test_no_question_at_war():
    g, reports = _game("konvoj")
    torp = g.station(TorpedoRoom)
    g.command("eld tub 1 kurs 090")
    _run(g)
    assert not any(r.type == "torp.weapons_hold" for r in reports)
    assert len(torp.in_water) == 1


def test_peacetime_scenarios_end_on_the_first_enemy_sunk():
    g, _ = _game("sundet")
    assert g.world.goal(PeaceBroken) is not None
    enemies = g.world.enemy_ships
    assert len(enemies) >= 2
    enemies[0].sunk = True
    for _ in range(60):
        g.tick()
        if g.over:
            break
    assert g.world.outcome["outcome"] == "peace_broken"


def test_war_scenarios_have_no_peace_goal():
    for key in ("konvoj", "krig", "duell", "svansen-kort"):
        g = Game(build_scenario(key, random.Random(1)), seed=1)
        assert g.world.goal(PeaceBroken) is None, key


# --- salvan -----------------------------------------------------------------------------
def test_a_salvo_with_one_straight_tube_is_a_single_shot():
    g, reports = _game("konvoj")
    torp = _mock_target(g)
    for t in torp.tubes:
        if t.n != 3:
            t.load = None
    g.command("salva S-1")
    _run(g)
    assert len(torp.in_water) == 1
    assert any(r.type == "torp.salvo_single" for r in reports)
    assert not any(r.type == "torp.salvo" for r in reports)


def test_a_salvo_inside_the_arming_distance_is_asked_once():
    g, reports = _game("konvoj")
    torp = _mock_target(g, rng=0.2)
    g.command("salva S-1")
    _run(g)
    assert any(r.type == "torp.too_close" for r in reports) and not torp.in_water
    g.command("salva S-1")
    _run(g)
    assert len(torp.in_water) == 3


# --- omladdningen -----------------------------------------------------------------------
def test_torpedo_room_suggests_reloading_a_tube_after_the_shot():
    g, reports = _game("konvoj")
    torp = g.station(TorpedoRoom)
    g.command("eld tub 1 kurs 090")
    _run(g, RELOAD_SUGGEST_S + 40)
    sug = [r for r in reports if r.type == "torp.suggest.reload"]
    assert sug and sug[0].data["tube"] == 1
    assert torp.tubes[0].load is None


def test_no_loaded_tube_gives_a_reload_suggestion_at_once():
    g, reports = _game("konvoj")
    torp = _mock_target(g)
    for t in torp.tubes:
        t.load = None
    g.command("eld S-1")
    _run(g, 10)
    assert any(r.type == "torp.refused" for r in reports)
    assert any(r.type == "torp.suggest.reload" for r in reports)


# --- varningen för lång gångtid och skjutlösningen efter skottet ---------------------------
def test_a_long_run_warns_even_without_a_known_turn_rhythm():
    from sim.stations.torpedo_room.common import LONG_RUN_S
    g, reports = _game("konvoj")
    torp = g.station(TorpedoRoom)
    g.knowledge.on_detection("S-9", g.now)
    torp._leg_warning("S-9", LONG_RUN_S + 60, "53-61")
    torp._leg_warning("S-9", LONG_RUN_S - 60, "53-61")
    _run(g, 5)
    warn = [r for r in reports if r.type == "torp.leg_warning"]
    assert len(warn) == 1 and warn[0].data["kind"] == "long" and "S-9" in warn[0].text


def test_a_queued_firing_solution_is_dropped_when_we_fire_at_the_target():
    from sim.reports import Report
    g, reports = _game("konvoj")
    torp = _mock_target(g)
    g.queue.submit(Report(g.now + 3, "Torped (Ivanov)", "torp.ready",
                          {"designation": "S-1", "tube": 1, "type": "53-61", "run_s": 120},
                          role="torpedo", kind="suggest"))
    g.command("eld tub 1 mot S-1")
    _run(g, 10)
    assert torp.in_water
    assert not any(r.type == "torp.ready" for r in reports)


# --- sonar: flera tappade på en rad ------------------------------------------------------
def test_contacts_lost_together_are_reported_on_one_line():
    from sim.stations.sonar_room import LOST_BATCH_S, SonarRoom
    g, reports = _game("konvoj")
    sonar = g.station(SonarRoom)
    sonar._lost_batch = [("S-3", 60.0), ("S-5", 72.0), ("S-6", None)]
    sonar._lost_t = g.now
    _run(g, LOST_BATCH_S + 20)
    many = [r for r in reports if r.type == "sonar.lost.many"]
    assert len(many) == 1 and many[0].text == "Kapten, sonar. Har tappat S-3 (060), S-5 (072) och S-6."
    assert not any(r.type == "sonar.lost" for r in reports)


# --- långt skott: fråga och föreslå anfall --------------------------------------------------
def _far_target(g, rng=5.0):
    """S-1, jagare 5 nm norrut på väg öster i 10 knop, med en riktig lösning i plottet."""
    from sim.tma import Solution
    torp = _mock_target(g, rng)
    tr = g.knowledge.tracks["S-1"]
    ex, ey = g.own_position_estimate()
    x, y = ex, ey + rng
    tr.solution = Solution(t=g.now, t_ref=g.now, state=(x, y, 10.0, 0.0), x=x, y=y, course=90.0,
                           speed=10.0, range_nm=rng, bearing=0.0, range_sigma=0.1, course_sigma=5.0,
                           speed_sigma=0.5, quality=Quality.SAKER, n_obs=40, span_s=1200,
                           own_maneuvered=True, rms_residual=0.5)
    from sim.tma import BearingObs
    tr.observations = [BearingObs(g.now, 0.0, 0.5, ex, ey, 0.0, designation="S-1")]
    torp._solution_for = lambda d: (tr, tr.solution)
    return torp


def test_a_long_straight_shot_is_asked_once_and_an_attack_is_suggested():
    g, reports = _game("konvoj")
    torp = _far_target(g)
    g.command("eld tub 1 mot S-1")
    _run(g, 30)
    assert not torp.in_water
    ask = [r for r in reports if r.type == "torp.long_shot"]
    assert ask and "Upprepa ordern" in ask[0].text
    sug = [r for r in reports if r.type == "torp.suggest.close"]
    assert sug and sug[0].data["order"] == "anfall S-1"
    g.command("eld tub 1 mot S-1")              # kaptenen står fast: skott
    _run(g, 6)
    assert len(torp.in_water) == 1
    assert not any(r.type == "torp.leg_warning" for r in reports)   # redan sagt


def test_yes_to_the_suggestion_starts_the_attack():
    from sim.stations.navigation import NavigationStation
    from sim.stations.navigation.tasks import Attack
    g, reports = _game("konvoj")
    _far_target(g)
    g.command("eld tub 1 mot S-1")
    _run(g, 30)
    sug = [r for r in reports if r.type == "torp.suggest.close"]
    assert sug
    g.command(sug[0].data["order"])          # samma som ja medan förslaget står
    _run(g, 5)
    assert isinstance(g.station(NavigationStation).steer, Attack)


def test_no_attack_suggested_while_they_have_us():
    g, reports = _game("konvoj")
    _far_target(g)
    g.knowledge.hunt_t = g.now
    g.command("eld tub 1 mot S-1")
    _run(g, 30)
    assert any(r.type == "torp.long_shot" for r in reports)
    assert not any(r.type == "torp.suggest.close" for r in reports)


def test_a_short_shot_is_not_asked():
    g, reports = _game("konvoj")
    torp = _far_target(g, rng=2.0)
    g.command("eld tub 1 mot S-1")
    _run(g, 6)
    assert len(torp.in_water) == 1
    assert not any(r.type == "torp.long_shot" for r in reports)


def test_no_attack_suggested_when_we_already_attack_the_target():
    g, reports = _game("konvoj")
    _far_target(g)
    g.command("anfall S-1")
    _run(g, 5)
    g.command("eld tub 1 mot S-1")
    _run(g, 30)
    assert any(r.type == "torp.long_shot" for r in reports)
    assert not any(r.type == "torp.suggest.close" for r in reports)
