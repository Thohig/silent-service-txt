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
