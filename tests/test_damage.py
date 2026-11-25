"""Skadekontrollen (sim/damage.py, sim/stations/damage_control.py): var skadan sitter, läckorna mot djupet,
tätningen, vattnet i avdelningarna, utrymningen, lutningen, provdjupet och det fastnade djuprodret."""
import random

import pytest

from sim import damage as D
from sim.environment import Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import TEST_DEPTH, OwnShip
from sim.scenario import build_scenario
from sim.ship import ShipState
from sim.world import World

NM = 1852.0


def _world(depth=100.0, speed=5.0, course=0.0):
    own = OwnShip(ShipState(x=10, y=10, course=course, speed=speed, depth=depth, max_depth=400))
    own.state.ordered_speed = speed
    return World(own=own, env=Environment(), rng=random.Random(1))


def _run(w, n):
    for _ in range(n):
        w.tick()


def _alerts(w):
    return [t for t, _ in w.own.sys.alerts]


def _game(seed=1):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts, w.ais = [], []
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_the_charge_damages_the_end_it_went_off_at():
    """Kurs 000: norr är fören. En laddning akter om oss tar rodren och läcker i nionde, en förut sonar
    och tuberna och läcker i första."""
    for dy, compartment, near in ((-60 / NM, 9, {"planes"}), (60 / NM, 1, {"sonar", "tubes"})):
        w = _world()
        w.rng = random.Random(3)
        w.own.apply_explosion(20, False, w.rng, src=(10, 10 + dy))
        _, data = next(a for a in w.own.sys.alerts if a[0] == "damage")
        assert data["compartment"] == compartment
        assert set(data["components"]) <= near | {"propulsion", "periscope", "radio"}
        assert set(data["components"]) & near
        assert w.own.sys.dmg.leaks and w.own.sys.dmg.leaks[0].compartment == compartment
        assert w.own.sys.dmg.closed                       # skotten stängda


def test_a_leak_gives_more_the_deeper_we_are():
    leak = D.Leak(5, "rör")
    assert leak.rate(150) > 2 * leak.rate(10)
    assert leak.rate(150) == pytest.approx(D.LEAK_KINDS["rör"].k * 4.0)


def test_the_crew_seals_a_leak_and_says_where():
    w = _world(depth=100, speed=0)
    w.own.add_leak(6, "rör")
    _run(w, 30)
    assert w.own.sys.flooding > 0 and w.own.sys.leak_rate > 0
    _run(w, 400)
    assert not w.own.sys.dmg.leaks and w.own.sys.leak_rate == 0
    _, data = next(a for a in w.own.sys.alerts if a[0] == "leak_stopped")
    assert data["compartment"] == 6


def test_a_crack_is_held_but_keeps_leaking():
    w = _world(depth=40, speed=0)
    w.own.add_leak(4, "spricka")
    _run(w, 1200)
    assert not w.own.sys.dmg.evacuated
    assert "dc.leak_held" in _alerts(w)
    leak = w.own.sys.dmg.leaks[0]
    assert leak.held and leak.rate(40) == pytest.approx(D.LEAK_KINDS["spricka"].k * D.LEAK_KINDS["spricka"].residual
                                                        * D.inflow_factor(40))


def test_a_compartment_half_full_is_left_and_its_gear_drowns():
    w = _world(depth=150, speed=0)
    own = w.own
    own.sys.dmg.bilge_on = False
    own.add_leak(9, "spricka", 6.0)              # stor: avdelningen fylls innan de hinner
    _run(w, 600)
    assert 9 in own.sys.dmg.evacuated and "dc.evacuated" in _alerts(w)
    assert own.sys.dmg.water[9] <= D.CAP_T[9] + 1e-6
    assert own.sys.health["planes"] <= D.WET_HEALTH
    assert own.sys.dmg.cap["planes"] <= D.WET_CAP
    progress = own.sys.dmg.leaks[0].progress
    _run(w, 60)
    assert own.sys.dmg.leaks[0].progress == progress     # ingen därinne som tätar


def test_water_aft_trims_the_boat_down_by_the_stern():
    w = _world(depth=100, speed=0)
    w.own.sys.dmg.water[9] = 10.0
    w.own.sys.dmg.bilge_on = False
    _run(w, 2)
    assert w.own.sys.trim.fore_t < -3
    assert w.own.pitch < -1.5


def test_a_damaged_hull_lowers_the_test_depth():
    w = _world()
    assert w.own.test_depth() == TEST_DEPTH
    w.own.sys.hull = 0.65
    assert 240 < w.own.test_depth() < 260


def test_the_crew_reports_the_lower_test_depth_and_suggests_no_deeper():
    g, reports = _game()
    g.world.own.sys.hull = 0.65
    for _ in range(5):
        g.tick()
    r = next(r for r in reports if r.type == "dc.test_depth")
    assert r.data["depth"] == 240 and "240" in r.text
    from sim.stations.engineering import EngineeringStation
    assert g.station(EngineeringStation).dive_depth(300) <= 230


def test_jammed_planes_take_us_down_and_the_crew_says_back():
    g, reports = _game()
    own = g.world.own
    st = own.state
    st.speed = st.ordered_speed = 10
    own.sys.health["planes"] = 0.3
    own.sys.dmg.planes_jam, own.sys.dmg.jam_left = 1, D.JAM_MANUAL_S
    start = st.depth
    for _ in range(30):
        g.tick()
    assert st.depth > start + 8
    sug = [r for r in reports if r.type == "dc.suggest.jam"]
    assert sug and sug[0].alarm and sug[0].data["order"] == "back 5"
    for _ in range(D.JAM_MANUAL_S):
        g.tick()
    assert own.sys.dmg.planes_jam == 0
    assert any(r.type == "dc.planes_manual" for r in reports)


def test_planes_hit_while_diving_jam_in_the_dive():
    w = _world(depth=100, speed=8)
    w.own.state.ordered_depth = 200
    w.own.sys.health["planes"] = 0.3
    D.maybe_jam(w.own, random.Random(1))
    assert w.own.sys.dmg.planes_jam == 1 and "dc.planes_jammed" in _alerts(w)


def test_bulkheads_open_again_when_the_leaks_are_sealed_and_the_boat_is_dry():
    w = _world(depth=60, speed=0)
    w.own.add_leak(3, "packbox")
    assert w.own.sys.dmg.closed
    _run(w, 900)
    assert not w.own.sys.dmg.closed and "dc.bulkheads_open" in _alerts(w)


def test_a_damaged_shaft_is_heard():
    w = _world()
    quiet = w.own.radiated_level(w.env)
    w.own.sys.health["propulsion"] = 0.5
    assert w.own.radiated_level(w.env) >= quiet + 2.9


def test_leak_beyond_the_pumps_brings_a_suggestion_to_go_shallower():
    g, reports = _game()
    own = g.world.own
    own.state.depth = own.state.ordered_depth = 200
    own.add_leak(9, "spricka", 2.0)
    own.sys.dmg.leaks[0].progress, own.sys.dmg.leaks[0].held = 1.0, True
    for _ in range(5):
        g.tick()
    r = next(r for r in reports if r.type == "dc.suggest.leak_up")
    target = int(r.data["order"].split()[1])
    assert 40 <= target < 200
    at = D.Leak(9, "spricka", 2.0, progress=1.0).rate(target)
    assert (at <= 0.5 + 1e-6) == r.data["enough"]
    assert target == 40 or r.data["enough"]
