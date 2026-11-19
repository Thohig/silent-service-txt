"""KV5: torpedrummet skjuter kärnladdningen bara med kärnvapenrådets tre nycklar, en gång,
aldrig i salva, och frågar först en gång."""
import random

from sim.events import ChargeHeard, ReportDelivered
from sim.game import Game
from sim.knowledge import ContactTrack
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.council import GATHER_S, NuclearCouncil
from sim.stations.torpedo_room import FireTube, TorpedoRoom
from sim.tma import Solution


def _game(key="jagad"):
    g = Game(build_scenario(key, random.Random(2)), seed=2)
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


def _keys(g):
    for i in range(3):
        g.knowledge.charges.append(ChargeHeard(g.now - i, True, Quality.SAKER, True, "maskin"))
    g.command("kärnvapenråd")
    for _ in range(GATHER_S + 5):
        g.tick()
    assert g.station(NuclearCouncil).armed()


def test_without_keys_t5_is_refused():
    g, room, _ = _game()
    assert "kärnvapenråd" in room._blocked("T-5")
    assert room._blocked("53-61") is None
    assert not room._fire(FireTube(1, "S-9"))


def test_with_keys_asks_once_and_fires_on_the_repeated_order_then_keys_return():
    g, room, reports = _game()
    _keys(g)
    assert room._blocked("T-5") is None
    assert not room._fire(FireTube(1, "S-9"))
    for _ in range(10):
        g.tick()
    assert any(r.type == "torp.nuclear_confirm" and r.alarm for r in reports)
    assert room._fire(FireTube(1, "S-9"))
    assert room.tubes[0].load is None
    assert not g.station(NuclearCouncil).armed()
    assert g.world.mission.get("nuclear_fired_t") is not None


def test_nuclear_torpedo_is_never_fired_in_a_salvo():
    g, room, reports = _game()
    _keys(g)
    assert not room._fire(FireTube(1, "S-9", in_salvo=True))
    for _ in range(10):
        g.tick()
    assert any(r.type == "torp.refused" and "salva" in r.text for r in reports)


def test_jagad_telegram_carries_the_condition_as_knowledge():
    from sim.scenario.jagad import HUNTED_RADIO
    assert HUNTED_RADIO[1].flags["nuclear"] == "conditional"
