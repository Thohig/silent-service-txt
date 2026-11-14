import random
import statistics

from sim.crew import CrewMember, Role
from sim.geo import angle_diff
from sim.ship import ShipState
from sim.sonar import Detection, SonarStation
from sim.tma import BearingObs
from sim.entities import Vessel
from sim.ownship import OwnShip
from sim.world import World


def _world(dd_x, dd_y, own_speed=4):
    own = OwnShip(ShipState(x=10, y=10, course=0, speed=own_speed, depth=40))
    dd = Vessel("DD1", "destroyer", ShipState(x=dd_x, y=dd_y, course=90, speed=15))
    return World(own=own, contacts=[dd])


def _run(world, station, seconds):
    events = []
    for _ in range(seconds):
        world.tick()
        events += station.update(world, (world.own.state.x, world.own.state.y))
    return events


def _station(skill, seed=1):
    return SonarStation(CrewMember("Volkov", Role.SONAR, skill), random.Random(seed))


def test_close_destroyer_detected_without_range():
    w = _world(8, 12)
    ev = _run(w, _station(0.8), 120)
    dets = [e for e in ev if isinstance(e, Detection)]
    assert len(dets) == 1
    assert dets[0].designation == "S-1"
    assert not hasattr(dets[0], "range_nm")
    assert any(isinstance(e, BearingObs) for e in ev)


def test_distant_destroyer_not_detected():
    w = _world(0, 30)
    ev = _run(w, _station(0.9), 300)
    assert not any(isinstance(e, Detection) for e in ev)


def test_running_fast_makes_sonar_deaf():
    w = _world(5, 13, own_speed=20)
    ev = _run(w, _station(0.9), 120)
    assert not any(isinstance(e, Detection) for e in ev)


def _bearing_errors(skill):
    w = _world(8, 12)
    st = _station(skill, seed=7)
    errs = []
    for _ in range(1500):
        w.tick()
        for e in st.update(w, (w.own.state.x, w.own.state.y)):
            if isinstance(e, BearingObs):
                errs.append(angle_diff(e.bearing, w.true_bearing(w.contacts[0])))
    return errs


def test_skill_reduces_bearing_noise():
    good = _bearing_errors(0.9)
    poor = _bearing_errors(0.3)
    assert len(good) > 30 and len(poor) > 30
    assert statistics.pstdev(good) < statistics.pstdev(poor)
