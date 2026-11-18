"""R5: stabens villkorade tillstånd för T-5 (bara om vi angrips med skarpa sjunkbomber)."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.knowledge import ContactTrack
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.torpedo_room import FireTube, TorpedoRoom
from sim.tma import Solution


def _game():
    g = Game(build_scenario("jagad", random.Random(2)), seed=2)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    room = g.station(TorpedoRoom)
    room.tubes[0].load, room.tubes[0].loading = "T-5", None
    s = g.world.own.state
    s.depth = s.ordered_depth = 60.0
    s.speed = s.ordered_speed = 4.0
    x, y = g.own_position_estimate()
    tr = ContactTrack("S-9", first_t=0, classification="jagare, ångturbiner, två axlar",
                      class_quality=Quality.SAKER)
    tr.solution = Solution(t=g.now, t_ref=g.now, state=(x, y + 2.0, 0.0, 0.0), x=x, y=y + 2.0,
                           course=90.0, speed=10.0, range_nm=2.0, bearing=0.0, range_sigma=0.1,
                           course_sigma=5.0, speed_sigma=1.0, quality=Quality.SAKER, n_obs=30,
                           span_s=900, own_maneuvered=True, rms_residual=1.0)
    g.knowledge.tracks["S-9"] = tr
    room._solution_for = lambda d: (tr, tr.solution) if d == "S-9" else (None, None)
    return g, room, reports


def _conditional(g, base=0):
    m = g.world.mission
    m["nuclear_authorized"] = False
    m["nuclear_condition"] = "real_charges"
    m["nuclear_condition_base"] = base


def test_without_any_permission_t5_is_refused():
    g, room, _ = _game()
    g.world.mission.pop("nuclear_condition", None)
    assert "order från Moskva" in room._blocked("T-5")


def test_conditional_permission_needs_real_charges_after_the_telegram():
    g, room, _ = _game()
    _conditional(g, base=3)
    g.world.mission["real_charges"] = 3                 # skarpa bomber före telegrammet räknas inte
    assert "skarpa sjunkbomber" in room._blocked("T-5")
    g.world.mission["charges_exploded"] = 20            # signalbomber räknas inte heller
    assert room._blocked("T-5")
    g.world.mission["real_charges"] = 4
    assert room._blocked("T-5") is None


def test_met_condition_asks_once_and_fires_on_the_repeated_order():
    g, room, reports = _game()
    _conditional(g)
    g.world.mission["real_charges"] = 1
    assert not room._fire(FireTube(1, "S-9"))
    for _ in range(10):
        g.tick()
    assert any(r.type == "torp.nuclear_confirm" and r.alarm for r in reports)
    assert room._fire(FireTube(1, "S-9"))
    assert room.tubes[0].load is None


def test_nuclear_torpedo_is_never_fired_in_a_salvo_on_conditional_permission():
    g, room, reports = _game()
    _conditional(g)
    g.world.mission["real_charges"] = 1
    assert not room._fire(FireTube(1, "S-9", in_salvo=True))
    for _ in range(10):
        g.tick()
    assert any(r.type == "torp.refused" and "salva" in r.text for r in reports)


def test_jagad_telegram_sets_the_condition_from_now():
    from sim.scenario.jagad import HUNTED_RADIO
    flags = HUNTED_RADIO[1].flags
    assert flags["nuclear_condition"] == "real_charges" and flags["nuclear_authorized"] is False
