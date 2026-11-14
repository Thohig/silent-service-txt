"""Hamnskydd: hydrofonkedjan, nätet med grind och patrullbåten."""
import random

from sim.entities import Vessel
from sim.environment import Environment
from sim.harbor import HarborDefense, HydrophoneLine, Net, PatrolBoatAI, hydrophone_points
from sim.ownship import OwnShip
from sim.ship import ShipState
from sim.world import World


def _world(x=7.0, y=5.0, depth=30.0, speed=0.0, course=0.0, prop="electric", seed=1):
    env = Environment(current_kn=0.0, background_noise=64.0)
    own = OwnShip(ShipState(x=x, y=y, course=course, speed=speed, depth=depth, max_depth=400))
    own.sys.propulsion = prop
    return World(own=own, env=env, rng=random.Random(seed), size_nm=14.0)


def _boat(w, x=7.0, y=3.0, box=(4.0, 2.0, 10.0, 6.0), seed=1):
    v = Vessel("PB1", "patrol", ShipState(x=x, y=y, course=90, speed=8, turn_rate=4, accel=0.5,
                                         max_speed=24), side="enemy", has_radar=True)
    w.contacts.append(v)
    ai = PatrolBoatAI(v, random.Random(seed), area=14.0, box=box)
    w.ais.append(ai)
    return ai


def _hits(prop, speed, r, n=60, mask=False):
    hits = 0
    for seed in range(n):
        w = _world(x=7.0, y=5.0 - r, speed=speed, prop=prop, seed=seed)
        if mask:
            w.contacts.append(Vessel("H1", "merchant", ShipState(x=7.0, y=5.0 - r - 0.3, course=0,
                                                                speed=10), side="neutral"))
        got = []
        line = HydrophoneLine([(7.0, 5.0)], random.Random(seed))
        line.listen(w, lambda *a: got.append(a))
        hits += bool(got)
    return hits


def test_hydrophones_hear_turbine_far_but_creep_only_close():
    assert _hits("turbine", 5, 0.4) >= 50
    assert _hits("electric", 3, 0.4) <= 3
    assert _hits("electric", 3, 0.08) >= 30


def test_a_merchant_in_the_same_bearing_masks_us():
    assert _hits("turbine", 5, 0.5, mask=True) < _hits("turbine", 5, 0.5) - 20


def test_hydrophone_alarm_gives_the_patrol_boat_a_datum():
    w = _world(x=7.0, y=4.6, speed=5, prop="turbine")
    hd = HarborDefense(hydrophones=HydrophoneLine([(7.0, 5.0)], random.Random(1)))
    boat = _boat(w)
    hd.boats.append(boat)
    w.spawners.append(hd)
    for _ in range(30):
        w.tick()
    assert boat.datum is not None and boat.aware()
    assert abs(boat.datum.x - 7.0) < 1.5 and abs(boat.datum.y - 4.6) < 1.5


def _net_world(gate_ship=False, x=7.0):
    w = _world(x=x, y=8.9, speed=3, course=0)
    net = Net(y=9.0, x0=6.6, x1=7.4, gate_x=7.0)
    hd = HarborDefense(net=net)
    w.spawners.append(hd)
    boat = _boat(w)
    hd.boats.append(boat)
    if gate_ship:
        w.contacts.append(Vessel("H1", "merchant", ShipState(x=7.0, y=9.3, course=180, speed=0),
                                 side="neutral"))
    return w, net, boat


def test_closed_net_stops_us_damages_the_propeller_and_raises_the_alarm():
    w, net, boat = _net_world()
    texts = []
    for _ in range(200):
        w.tick()
        texts += [a[0] for a in w.own.sys.alerts]
        w.own.sys.alerts.clear()
    o = w.own.state
    assert o.y < 9.0 and o.speed == 0
    assert "net.caught" in texts
    assert w.own.sys.health["propulsion"] < 1.0
    assert boat.datum is not None and boat.datum.sigma <= 0.15


def test_open_gate_lets_us_through():
    w, net, boat = _net_world(gate_ship=True)
    for _ in range(200):
        w.tick()
    assert w.own.state.y > 9.0
    assert not net.caught and boat.datum is None


def test_open_gate_does_not_help_beside_it():
    w, net, boat = _net_world(gate_ship=True, x=6.8)
    for _ in range(200):
        w.tick()
    assert w.own.state.y < 9.0 and net.caught


def test_patrol_boat_stays_in_its_box():
    w = _world(x=1.0, y=12.0, depth=30)
    boat = _boat(w)
    out = 0
    for _ in range(3600):
        w.tick()
        s = boat.vessel.state
        out += not (3.5 <= s.x <= 10.5 and 1.5 <= s.y <= 6.5)
    assert out < 200


def test_periscope_sees_net_buoys_by_day_only_close_at_night():
    w, net, _ = _net_world()
    hd = w.spawners[0]
    w.env.clock_start = 12 * 3600
    w.own.state.y = 7.5
    assert hd.periscope_view(w, random.Random(1))
    w.env.clock_start = 0
    assert not hd.periscope_view(w, random.Random(1))
    w.own.state.y = 8.7
    assert hd.periscope_view(w, random.Random(1))


def test_hydrophone_points_span_the_line():
    pts = hydrophone_points(4.0, 10.0, 5.0, 0.6)
    assert pts[0] == (4.0, 5.0) and pts[-1] == (10.0, 5.0)
    assert len(pts) == 11
