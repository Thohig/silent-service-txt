"""Försökstorpeden 53-62T: eldledningen styr den på tråd mot plottets lösning, släpper målsökaren
nära målet; tråden går av av vår fart, gir eller längd, och kaptenen kan kapa den."""
import re

import pytest

from sim import russian
from sim.events import BearingObserved, TorpedoInWater
from sim.geo import bearing_to, distance
from sim.stations import TorpedoRoom
from sim.tma import BearingObs
from sim.weapons import TORPEDO_TYPES, Torpedo

from test_torpedo_tracking import _game, _setup


def _feed(g, dd):
    """Plottet får en färsk bäring med avstånd (som om sonar och periskop följde målet)."""
    ex, ey = g.own_position_estimate()
    b = bearing_to(ex, ey, dd.state.x, dd.state.y)
    g.bus.publish(BearingObserved(g.now, BearingObs(
        g.now, b, 0.5, ex, ey, g.world.own.state.course, designation="S-1",
        range_nm=distance(ex, ey, dd.state.x, dd.state.y), range_sigma=0.02)))


def _wired(g):
    return next(v for v in g.world.contacts if isinstance(v, Torpedo))


def _fire_wire(g, tube=1):
    g.station(TorpedoRoom).tubes[tube - 1].load = "53-62T"
    g.command(f"eld tub {tube} mot S-1")
    g.command(f"eld tub {tube} mot S-1")        # jagaren med dålig klass: upprepa


def _run_against_turning_target(seed, typ):
    g, reports = _game(seed)
    dd = _setup(g, range_nm=3.0, dd_speed=12, dd_course=90)
    g.station(TorpedoRoom).tubes[0].load = typ
    g.command("eld tub 1 mot S-1")
    g.command("eld tub 1 mot S-1")
    for i in range(700):
        g.tick()
        if i == 60:
            dd.state.order_course(200)             # målet girar efter skottet
        if i % 10 == 0 and not dd.sunk:
            _feed(g, dd)
        if dd.sunk:
            break
    return g, reports, dd


@pytest.mark.slow
def test_guided_torpedo_follows_a_turning_target_where_a_straight_one_misses():
    wire = straight = 0
    for seed in range(1, 6):
        g, reports, dd = _run_against_turning_target(seed, "53-62T")
        wire += dd.sunk
        types = [r.type for r in reports]
        assert "torp.wire.guide" in types and "torp.wire.seeker" in types
        # en gir på vår styrorder är inte målsökaren
        assert "torp.run.turned" not in types[:types.index("torp.wire.seeker")]
        straight += _run_against_turning_target(seed, "53-61")[2].sunk
    assert wire >= 4 and straight <= 1


def test_seeker_is_off_while_the_wire_holds():
    g, _ = _game(1)
    _setup(g, range_nm=3.0)
    _fire_wire(g)
    t = _wired(g)
    assert t.wire_ok and not t.seeker_on
    for _ in range(60):
        g.tick()
    assert t.run_nm > 0.25 and t.locked is None     # armerad men söker inte


def test_speed_breaks_the_wire_after_a_warning():
    g, reports = _game(1)
    _setup(g, range_nm=4.0)
    _fire_wire(g)
    g.world.own.state.order_speed(25)
    for _ in range(400):
        g.tick()
    t = _wired(g)
    assert not t.wire_ok and t.seeker_on
    types = [r.type for r in reports]
    assert types.index("torp.wire.strain") < types.index("torp.wire.broken")
    broken = next(r for r in reports if r.type == "torp.wire.broken")
    assert "farten" in broken.text
    assert not g.station(TorpedoRoom).in_water[0].wired


def test_turn_breaks_the_wire():
    g, reports = _game(2)
    _setup(g, range_nm=4.0)
    _fire_wire(g)
    own = g.world.own.state
    own.order_course((own.course + 150) % 360)
    for _ in range(150):
        g.tick()
    assert not _wired(g).wire_ok
    assert any(r.type == "torp.wire.broken" and "giren" in r.text for r in reports)


def test_cut_wire_order():
    g, reports = _game(1)
    _setup(g, range_nm=4.0)
    g.command("kapa tråden")
    for _ in range(10):
        g.tick()
    assert any(r.type == "torp.refused" and "ingen trådstyrd" in r.text for r in reports)
    _fire_wire(g)
    for _ in range(30):
        g.tick()
    g.command("kapa tråden")
    for _ in range(10):
        g.tick()
    t = _wired(g)
    assert not t.wire_ok and t.seeker_on
    assert any(r.type == "torp.wire.cut" for r in reports)
    g.command("torpeder")
    for _ in range(10):
        g.tick()
    assert "tråden av, målsökaren söker" in \
        next(r for r in reversed(reports) if r.type == "torp.in_water").text


def test_fired_on_a_course_it_seeks_at_once():
    g, _ = _game(1)
    _setup(g)
    g.station(TorpedoRoom).tubes[0].load = "53-62T"
    g.command("eld tub 1 kurs 090")
    t = _wired(g)
    assert not t.wire_ok and t.seeker_on
    assert not g.station(TorpedoRoom).in_water[0].wired


def test_incoming_torpedo_brings_a_cut_wire_suggestion():
    g, reports = _game(1)
    _setup(g, range_nm=4.0)
    _fire_wire(g)
    g.tick()
    g.bus.publish(TorpedoInWater(g.now, 1, "new", 200.0))
    for _ in range(40):
        g.tick()
    s = [r for r in reports if r.type == "torp.suggest.cut_wire"]
    assert s and s[0].data["order"] == "kapa tråden"


def test_loading_and_speech():
    g, reports = _game(1)
    g.station(TorpedoRoom).tubes[0].load = None
    g.command("ladda tub 1 tråd")
    assert g.station(TorpedoRoom).tubes[0].loading == "53-62T"
    assert not re.search(r"[A-Za-z]", russian.weapon("53-62T"))
    assert TORPEDO_TYPES["53-62T"].wire_nm < TORPEDO_TYPES["53-62T"].range_nm
