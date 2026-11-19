"""Back i maskin: maskinen slår om via stopp, båten går akterut med svagare roder."""
import math
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import ASTERN_ELECTRIC_KN, ASTERN_TURBINE_KN
from sim.scenario import default_scenario
from sim.ship import ShipState


def _state(**kw):
    return ShipState(x=0.0, y=0.0, course=0.0, speed=kw.pop("speed", 0.0), **kw)


def test_reversing_brakes_through_zero_then_goes_astern():
    s = _state(speed=12.0, brake_accel=0.15)
    s.order_speed(6.0, astern=True)
    assert s.reversing
    t = 0
    while s.speed > 0 and not s.astern:
        s.step(1)
        t += 1
    assert 75 <= t <= 85                    # 12 kn / 0,15 kn/s
    for _ in range(200):
        s.step(1)
    assert s.astern and s.speed == 6.0 and not s.reversing
    assert "speed" not in s.changing()


def test_astern_moves_backwards_along_course():
    s = _state(speed=0.0)
    s.order_speed(4.0, astern=True)
    for _ in range(600):
        s.step(1)
    assert s.course == 0.0
    assert s.y < -0.4 and abs(s.x) < 1e-9   # rakt söderut med fören mot norr


def test_turning_is_slower_astern():
    a = _state(speed=0.0, astern_turn=1 / 3)
    a.order_speed(3.0, astern=True)
    for _ in range(100):
        a.step(1)
    a.order_course(90.0)
    a.step(10)
    assert math.isclose(a.course, 10 / 3, abs_tol=1e-6)


def test_halt_clears_astern():
    s = _state(speed=3.0)
    s.order_speed(3.0, astern=True)
    s.halt()
    assert s.speed == 0 and not s.astern and not s.ordered_astern


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    said: list[str] = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.text))
    return g, said


def _run(g, n):
    for _ in range(n):
        g.tick()


def test_orders_and_limits():
    g, said = _game()
    s = g.world.own.state
    g.command("djup 100")
    g.command("full back")
    _run(g, 300)
    assert s.astern and s.speed == ASTERN_TURBINE_KN
    assert any("full back" in t for t in said)
    g.command("back 20")
    _run(g, 10)
    assert any("största backfart" in t for t in said)
    g.command("smygmotor")
    _run(g, 5)
    assert s.ordered_speed <= ASTERN_ELECTRIC_KN and s.ordered_astern
    g.command("fart 4")
    _run(g, 200)
    assert not s.astern and s.speed == 4.0
    assert any("står stilla" in t and "framåt" in t for t in said)


def test_back_parses():
    g, _ = _game()
    from sim.stations.navigation.common import SetSpeed
    p = g.registry.parse
    assert p("back 3") == SetSpeed(3.0, astern=True)
    assert p("back") == SetSpeed(0.0, astern=True, level="sakta")
    assert p("halv back") == SetSpeed(0.0, astern=True, level="halv")
    assert p("full back") == SetSpeed(0.0, astern=True, level="full")


def test_reversal_is_a_transient_louder_at_speed():
    from sim import acoustics
    g, said = _game()
    s = g.world.own.state
    g.command("djup 100")
    g.command("fart 14")
    _run(g, 400)
    heard = []
    g.command("full back")
    for _ in range(5):
        g.tick()
        heard += [tr for tr in g.world.transients if tr.kind == "astern"]
    assert len(heard) == 1
    assert abs(heard[0].level - acoustics.astern_level(14.0)) < 1.0   # efter första sekundens broms
    assert any("Omkastningen hörs långt" in t for t in said)
    assert g.world.own.state.prop_astern


def test_quiet_reversal_from_low_speed():
    g, said = _game()
    g.command("djup 100")
    g.command("fart 1")
    _run(g, 100)
    g.command("back 1")
    seen = []
    for _ in range(5):
        g.tick()
        seen += [tr for tr in g.world.transients if tr.kind == "astern"]
    assert not seen


def test_propeller_cavitates_sooner_astern():
    from sim import acoustics
    assert acoustics.cavitation_speed(100, True) == acoustics.cavitation_speed(100) / 2
    g, _ = _game()
    own = g.world.own
    own.state.depth = own.state.ordered_depth = 25
    own.state.speed, own.state.astern = 5.0, True
    own.state.ordered_speed, own.state.ordered_astern = 5.0, True
    quiet = own.radiated_level(g.world.env)
    own.state.astern = own.state.ordered_astern = False
    assert quiet - own.radiated_level(g.world.env) == 12.0      # 5 kn akterut kaviterar på 25 m
