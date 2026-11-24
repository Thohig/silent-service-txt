"""Stampvinkeln (sim/ownship.py, Lutningen i docs/system/besattning.md): båten lutar när rodren byter
djup, navigatören väljer brant vinkel när det brådskar, lösa föremål slamrar över 15° och torpedrummet
skjuter inte med mer än 7° lutning."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import BLOW_PITCH_DEG, CLATTER_DEG
from sim.scenario import build_scenario
from sim.stations.navigation import NavigationStation
from sim.stations.torpedo_room import TorpedoRoom
from sim.stations.torpedo_room.common import MAX_LAUNCH_PITCH


def _game(steep: bool | None = None, speed: float = 12.0):
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    st = g.world.own.state
    st.speed = st.ordered_speed = speed
    if steep is not None:
        g.station(NavigationStation)._steep = lambda: steep
    g.tick()
    return g, reports


def _dive(g, depth: int, n: int = 240) -> tuple[float, int]:
    """Största lutningen under djupbytet och sekunderna till djupet."""
    g.command(f"djup {depth}")
    most, reached = 0.0, None
    for i in range(n):
        g.tick()
        most = max(most, abs(g.world.own.pitch))
        if reached is None and g.world.own.state.depth == depth:
            reached = i
    return most, reached


def test_a_normal_depth_change_tilts_the_boat_and_it_levels_out():
    g, reports = _game(steep=False)
    most, reached = _dive(g, 250)
    assert 8.0 < most < CLATTER_DEG
    assert abs(g.world.own.sys.pitch_dyn) < 0.5           # framme: rak igen
    assert not any(r.type == "hull.clatter" for r in reports)
    assert g.status().pitch == g.world.own.pitch            # lutningsmätaren i centralen


def test_steep_angle_is_faster_and_loose_gear_clatters_once():
    g, _ = _game(steep=False)
    _, normal = _dive(g, 250)
    g2, reports = _game(steep=True)
    most, steep = _dive(g2, 250)
    assert most > CLATTER_DEG and steep < normal
    clatter = [r for r in reports if r.type == "hull.clatter"]
    assert len(clatter) == 1 and "far i durken" in clatter[0].text
    ack = next(r for r in reports if r.type == "nav.depth.ack")
    assert "Brant vinkel" in ack.text


def test_no_tilt_at_low_speed_where_the_ballast_does_it():
    g, _ = _game(speed=1.0)
    most, _ = _dive(g, 150, n=120)
    assert most < 1.0


def test_emergency_blow_puts_the_bow_up():
    g, _ = _game()
    g.world.own.sys.blowing = True
    for _ in range(10):
        g.tick()
    assert g.world.own.sys.pitch_dyn <= BLOW_PITCH_DEG + 1


def test_torpedo_room_refuses_with_too_much_pitch():
    g, reports = _game(speed=3.0)
    st = g.world.own.state
    st.depth = st.ordered_depth = 40.0
    g.world.own.sys.pitch_dyn = MAX_LAUNCH_PITCH + 3
    reason = g.station(TorpedoRoom)._refusal(type("O", (), {"tube": 1, "designation": None})())
    assert reason is not None and "lutar" in reason
    g.world.own.sys.pitch_dyn = 0.0
    assert g.station(TorpedoRoom)._refusal(type("O", (), {"tube": 1, "designation": None})()) is None


def test_steep_angle_only_going_down():
    """Upp mot periskopdjupet med fienden nära går navigatören inte brant: det skulle slamra."""
    g, reports = _game(steep=True)
    st = g.world.own.state
    st.depth = st.ordered_depth = 120.0
    for _ in range(20):
        g.tick()
    most, _ = _dive(g, 30)
    assert most < CLATTER_DEG
    assert not any(r.type == "hull.clatter" for r in reports)
    assert "Brant vinkel" not in next(r for r in reports if r.type == "nav.depth.ack").text
