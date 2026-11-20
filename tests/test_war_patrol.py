"""Krigspatrullen (krig, krig-kort): krigsskådeplatsens uppgifter, telegrammen, hemkallelsen och
följderna (sim/theatre.py)."""
import random

import pytest

from sim.entities import Emission
from sim.events import ReportDelivered
from sim.game import Game
from sim.goals import EscapeGoal
from sim.knowledge import Waypoint
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.radio import RadioStation
from sim.theatre import TASK_ORDER, task_summary


def _game(key="krig", seed=1):
    return Game(build_scenario(key, random.Random(seed)), seed=seed, warm_up=False)


def _receive(g):
    """Radion tar emot vid ett sambandstillfälle (det staben har i kö)."""
    g.station(RadioStation)._deliver(upto=-1)


def _resolve_current(g, result="missad"):
    th = g.scenario.theatre
    th._resolve(g.world, th.current, result)


def test_order_carries_the_first_task_and_the_navigator_suggests_course():
    reports = []
    sc = build_scenario("krig", random.Random(2))
    g = Game(sc, seed=2, warm_up=False)
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    assert "FÖRSTA UPPGIFT" in sc.secret_order and "KONVOJ" in sc.secret_order
    assert g.knowledge.order_tasks == frozenset({"anfall"})
    assert "konvoj 1" in g.knowledge.waypoints
    assert g.knowledge.waypoints["konvoj 1"].motion is not None
    for _ in range(30):
        g.tick()
    sug = [r for r in reports if r.type == "nav.suggest.task"]
    assert sug and sug[0].data["order"] == "kurs mot konvoj 1"
    assert g.escape_nm is None                  # utvägen gäller först efter hemkallelsen


def test_moving_waypoint_is_dead_reckoned():
    wp = Waypoint("konvoj 1", 0.0, 0.0, 2.0, 0, motion=(90.0, 12.0))
    x, y = wp.at(1800)
    assert x == pytest.approx(6.0) and y == pytest.approx(0.0, abs=1e-9)
    assert wp.sigma(3600) == pytest.approx(4.0)           # 2 kn osäkerhet per timme
    still = Waypoint("ankarplatsen", 1.0, 2.0, 0.5, 0)
    assert still.at(3600) == (1.0, 2.0)


def test_next_task_is_laid_out_before_the_window_and_changes_the_order():
    g = _game()
    th = g.scenario.theatre
    _resolve_current(g)
    w = next(w for w in th.windows if w > g.now + 60)
    while g.now < w:
        g.tick()
    task = th.current
    assert task is not None and task.n == 2 and task.kind == th.tdef.kinds[0]
    assert task.told_t is None and th.pending(g.world)
    _receive(g)
    assert task.told_t == g.now
    assert g.knowledge.order_tasks == frozenset(TASK_ORDER[task.kind])
    assert g.knowledge.task_place == task.name and task.name in g.knowledge.waypoints
    assert not th.pending(g.world)               # sänt: kön är tom
    assert any(f"UPPGIFT {task.n}" in t.text for t in g.knowledge.telegrams)


def test_telegram_text_never_names_truth_ids():
    g = _game(seed=3)
    for kind in ("anfall", "spaning", "foto"):
        task = g.scenario.theatre.start(g.world, kind)
        msg = g.scenario.theatre._message(g.world, task)
        assert msg is not None
        for v in task.vessels:
            assert v.id not in msg.text
        assert msg.flags["tasks"] == TASK_ORDER[kind]


def test_recall_after_max_tasks_sets_the_way_out():
    g = _game()
    th = g.scenario.theatre
    for i in range(th.tdef.max_tasks):
        if th.current is None:
            th.start(g.world, th.tdef.kinds[i % len(th.tdef.kinds)])
        _resolve_current(g)
    g.world.time += 10 - g.world.time % 10       # nästa prövning
    th.step(g.world)
    assert th.recall_queued and th.queue[-1] == "recall"
    _receive(g)
    assert g.world.mission.get("recalled") is True
    assert g.knowledge.order_tasks == frozenset({"ut"})
    assert g.escape_nm == pytest.approx(2.0) and g.recalled()
    goal = g.world.goal(EscapeGoal)
    o = g.world.own.state
    o.x = -5.0                                   # ute ur kvadraten i undervattensläge
    assert goal.check(g.world)
    assert g.world.outcome["outcome"] == "patrol_done"


def test_escape_goal_waits_for_the_recall():
    g = _game()
    g.world.own.state.x = -5.0
    assert not g.world.goal(EscapeGoal).check(g.world)
    assert g.world.outcome is None


def test_recall_cancels_the_task_in_progress():
    g = _game()
    th = g.scenario.theatre
    g.world.mission["torpedoes_fired"] = th.tdef.torpedoes - 2      # nästan slut
    g.world.time = 10
    th.step(g.world)
    assert th.recall_queued
    _receive(g)
    assert th.tasks[0].result == "inställd"
    assert task_summary(g.world)["tasks"][0]["result"] == "inställd"


def test_all_enemies_sunk_does_not_end_the_war_patrol():
    g = _game()
    for v in g.world.enemy_ships:
        v.sunk = True
    for _ in range(60):
        g.tick()
    assert not g.over


def test_reconnaissance_counts_a_report_on_the_force_or_its_escort():
    g = _game()
    th = g.scenario.theatre
    _resolve_current(g)
    task = th.start(g.world, "spaning")
    task.told_t = g.now
    escort = next(v for v in task.vessels if v.kind == "destroyer")
    g.world.mission.setdefault("report_truth", []).append(
        {"t": g.now, "own_err_nm": 0.1, "contacts": [{"designation": "S-9", "id": escort.id}]})
    th._judge(g.world, task)
    assert task.result == "rapporterad"


def test_photo_task_needs_a_picture_after_the_telegram():
    g = _game()
    th = g.scenario.theatre
    _resolve_current(g)
    task = th.start(g.world, "foto")
    assert all(v.kind == "moored" for v in task.targets)
    guard = task.ais[0]
    assert guard.quiet_patrol and guard.roe == "lethal"
    task.told_t = g.now + 10
    g.world.mission["photos"] = [(g.now, int(Quality.SAKER))]       # före uppgiften: räknas inte
    th._judge(g.world, task)
    assert task.result is None
    g.world.mission["photos"].append((g.now + 20, int(Quality.OSAKER)))
    th._judge(g.world, task)
    assert task.result == "fotograferad"


def test_officer_suggests_a_look_near_the_anchorage():
    reports = []
    g = _game()
    th = g.scenario.theatre
    _resolve_current(g)
    task = th.start(g.world, "foto")
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    _receive(g)
    ax, ay = task.targets[0].state.x, task.targets[0].state.y
    o = g.world.own.state
    o.x, o.y, o.depth, o.ordered_depth = ax - 2.5, ay, 80.0, 80.0
    from sim.stations.navigation import NavigationStation
    nav = g.station(NavigationStation)
    nav.est_x, nav.est_y = o.x, o.y
    for _ in range(90):
        g.tick()
    assert any(r.type == "off.suggest.photo_up" and r.data["order"] == "periskopdjup"
               for r in reports)


def test_radio_suggests_the_report_when_the_plot_has_the_force():
    reports = []
    g = _game()
    th = g.scenario.theatre
    _resolve_current(g)
    th.start(g.world, "spaning")
    _receive(g)
    assert "rapport" in g.knowledge.order_tasks
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    from sim.tma import Solution
    tr = g.knowledge.on_detection("S-50", g.now + 1)
    tr.solution = Solution(t=g.now + 1, t_ref=g.now + 1, state=(1.0, 1.0, 0.0, -14.0), x=1.0,
                           y=1.0, course=200.0, speed=14.0, range_nm=6.0, bearing=10.0,
                           range_sigma=0.6, course_sigma=10.0, speed_sigma=1.0,
                           quality=Quality.GOD, n_obs=20, span_s=600, own_maneuvered=True,
                           rms_residual=0.5)
    o = g.world.own.state
    o.depth = o.ordered_depth = 15.0
    for _ in range(120):
        g.tick()
    sug = [r for r in reports if r.type == "radio.suggest.task_report"]
    assert sug and sug[0].data["order"] == "sänd rapport"


def test_direction_finding_sends_a_hunter_group_and_the_aircraft():
    g = _game()
    th = g.scenario.theatre
    w = g.world
    o = w.own.state
    before = len(w.contacts)
    w.emissions = [Emission("hf", o.x, o.y, w.own.id, w.time, duration=40.0)]   # säkert fix
    th._hunt_consequences(w)
    assert w.mission["war_df"] == 1
    assert len(th.hunters) == 1 and len(w.contacts) == before + 2
    hunters = th.hunters[0].ais
    assert all(ai.roe == "lethal" and ai.leash_nm is not None for ai in hunters)
    assert th.air_cue is not None
    # samma sändning räknas en gång, och en ny grupp kommer inte inom timmen
    th._hunt_consequences(w)
    w.emissions = [Emission("hf", o.x + 1, o.y, w.own.id, w.time + 5, duration=40.0)]
    th._hunt_consequences(w)
    assert w.mission["war_df"] == 2 and len(th.hunters) == 1


def test_short_transmission_is_never_fixed():
    g = _game()
    w = g.world
    o = w.own.state
    for i in range(20):
        w.emissions = [Emission("hf", o.x, o.y, w.own.id, i, duration=8.0)]
        g.scenario.theatre._hunt_consequences(w)
    assert "war_df" not in w.mission


def test_resolved_tasks_far_away_are_removed_from_the_world():
    g = _game()
    th = g.scenario.theatre
    task = th.current
    _resolve_current(g)
    o = g.world.own.state
    for v in task.vessels:
        v.state.x, v.state.y = o.x + 40.0, o.y
    th._cleanup(g.world)
    assert task.removed
    assert not any(v in g.world.contacts for v in task.vessels)
    assert not any(ai in g.world.ais for ai in task.ais)


def test_plot_proposes_no_legs_once_recalled():
    g = _game()
    g.knowledge.order_tasks = frozenset({"ut"})
    assert g.recalled()
    from sim.stations.plot import PlotTeam
    assert g.station(PlotTeam).idle_proposals() == []


def test_summary_rows_list_the_tasks_and_tonnage():
    from ui.widgets import war_rows
    g = _game()
    th = g.scenario.theatre
    th.tasks[0].targets[0].sunk = True
    g.world.time = 10
    th._sinkings(g.world)
    _resolve_current(g, "sänkt")
    rows = dict(war_rows(task_summary(g.world)))
    assert rows["Uppgift 1, konvoj (kl 06.30)"] == "sänkt"
    assert rows["Sänkta fiendefartyg"].startswith("1, cirka 12 000")


@pytest.mark.slow
def test_short_variant_hands_over_with_the_convoy_plotted():
    for seed in range(1, 5):
        g = Game(build_scenario("krig-kort", random.Random(seed)), seed=seed)
        assert not g.over
        assert g.knowledge.convoy is not None or any(
            t.held and t.solution is not None for t in g.knowledge.tracks.values())
        assert g.knowledge.order_tasks == frozenset({"anfall"})


@pytest.mark.slow
def test_war_patrol_runs_to_an_end_without_errors():
    """En passiv kapten: uppgifterna läggs ut, avgörs och tiden går ut (inga fel på vägen)."""
    g = Game(build_scenario("krig", random.Random(5)), seed=5)
    for _ in range(15 * 3600):
        if g.over:
            break
        g.tick()
    assert g.over
    tasks = g.world.mission["war_tasks"]
    assert len(tasks) >= 2 and all(t["result"] for t in tasks)
