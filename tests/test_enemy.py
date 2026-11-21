import random

from sim import acoustics as ac
from sim.enemy import DestroyerAI
from sim.entities import Transient, Vessel
from sim.environment import Environment
from sim.ownship import OwnShip
from sim.ship import ShipState
from sim.weapons import TORPEDO_TYPES, launch_torpedo
from sim.world import World


def _setup(own_depth=40, dd_xy=(10, 12), dd_speed=10, seed=1):
    own = OwnShip(ShipState(x=10, y=10, course=0, speed=3, depth=own_depth, max_depth=400))
    dd = Vessel("DD1", "destroyer", ShipState(x=dd_xy[0], y=dd_xy[1], course=90, speed=dd_speed,
                                              turn_rate=2, accel=0.3, max_speed=32))
    w = World(own=own, contacts=[dd], env=Environment(current_kn=0), rng=random.Random(seed))
    ai = DestroyerAI(dd, random.Random(seed))
    w.ais.append(ai)
    return w, ai


def _pings(w, ai, n=10):
    hits = 0
    for _ in range(n):
        ai.datum = None
        ai._ping(w, ai._noise(w))
        hits += ai.datum is not None
    return hits


def test_active_sonar_finds_shallow_sub_but_layer_hides_deep_one():
    w, ai = _setup(own_depth=40, dd_xy=(10, 13.5))     # 3,5 nm, samma sida om skiktet
    assert _pings(w, ai) >= 8
    w, ai = _setup(own_depth=150, dd_xy=(10, 13.5))    # 3,5 nm, under skiktet
    assert _pings(w, ai) <= 2


def test_our_ping_gives_away_position():
    w, ai = _setup(own_depth=150, dd_xy=(10, 18))
    w.emit(Transient("ping", 10, 10, 150, ac.PING_LEVEL_OWN, w.own.id, 0))
    w.tick()
    assert ai.datum is not None
    w.tick()
    assert ai.state == "prosecute"


def test_signal_rules_drop_practice_charges_and_call_on_uwt():
    w, ai = _setup(own_depth=40, dd_xy=(10, 11.0), dd_speed=12)
    heard = []
    for _ in range(900):
        w.tick()
        heard += [t.kind for t in w.transients]
    assert ai.attacks >= 1
    assert "uwt" in heard and "explosion" in heard
    assert w.own.sys.hull == 1.0                        # signalsjunkbomber skadar inte
    assert ai.roe == "signal"


def test_torpedo_makes_destroyer_evade_and_go_lethal():
    w, ai = _setup(own_depth=40, dd_xy=(10, 12), dd_speed=15)
    launch_torpedo(w, TORPEDO_TYPES["53-61"], 0)
    for _ in range(60):
        w.tick()
    assert ai.roe == "lethal"
    assert ai.state == "evade" or ai.vessel.sunk
    assert ai.vessel.state.ordered_speed == 30 or ai.vessel.sunk


def test_surfacing_near_aware_destroyer_ends_game():
    w, ai = _setup(own_depth=40, dd_xy=(10, 13))
    w.own.state.depth = 0
    w.own.state.order_depth(0)
    for _ in range(5):
        w.tick()
    assert w.outcome is None                    # en stund att dyka igen (SURFACE_GRACE_S)
    for _ in range(60):
        w.tick()
    assert w.outcome and w.outcome["outcome"] == "forced"
