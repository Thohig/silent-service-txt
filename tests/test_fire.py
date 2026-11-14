"""Brand och rök: branden stoppar turbinen, röken kräver ventilation i öppen luft."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario


def _game(fire_at=10, seed=1):
    g = Game(build_scenario("arktis", random.Random(seed)), seed=seed)
    g.world.mission["fire_at"] = fire_at
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()


def _to_open_water(g, depth=17.0):
    own = g.world.own.state
    g.world.env.ice.carve_polynya(own.x, own.y, 0.4)
    own.depth = own.ordered_depth = depth
    own.speed = 0.0
    own.order_speed(0)


def test_fire_stops_turbine_and_fills_boat_with_smoke():
    g, reports = _game()
    _run(g, 30)
    sys = g.world.own.sys
    assert sys.fire and sys.propulsion == "electric"
    g.command("turbin")
    _run(g, 10)
    assert any("brinner" in r.text for r in reports)
    assert sys.propulsion == "electric"
    _run(g, 800)
    assert not sys.fire and sys.fire_done
    s_out = sys.smoke
    assert 0.3 < s_out < 0.8
    _run(g, 1800)
    assert sys.smoke > s_out                       # glödbränder: värre utan ventilation
    assert any(r.type == "fire" and r.alarm for r in reports)
    assert any(r.type == "fire.out" for r in reports)


def test_smoke_lowers_crew_performance():
    g, _ = _game()
    nav = g.crew[next(iter(g.crew))]
    before = nav.effective_skill()
    _run(g, 900)
    assert nav.effective_skill() < before


def test_ventilation_needs_open_air_and_clears_smoke():
    g, reports = _game()
    _run(g, 900)
    sys = g.world.own.sys
    g.command("ventilera")                         # på 120 m under isen
    _run(g, 10)
    assert not sys.ventilating
    assert any("periskopdjup" in r.text for r in reports if r.type == "eng.refused")
    _to_open_water(g)
    smoke = sys.smoke
    g.command("ventilera")
    _run(g, 600)
    assert sys.smoke < smoke - 0.15
    g.world.own.state.order_depth(60)              # ned igen: ventilationen avbryts
    _run(g, 120)
    assert not sys.ventilating
    assert any(r.type == "vent.stopped" for r in reports)


def test_too_much_smoke_kills_the_crew():
    g, _ = _game()
    _run(g, 30)
    g.world.own.sys.smoke = 0.995
    _run(g, 60)
    assert g.over
    assert g.world.outcome["outcome"] == "lost"
    assert "rök" in g.world.outcome["cause"]


def test_crew_proposes_way_to_fresh_air():
    g, reports = _game()
    _run(g, 900)
    _to_open_water(g)
    _run(g, 120)
    assert any(r.type == "eng.suggest.vent" and r.data.get("order") == "ventilera"
               for r in reports)


def test_no_fire_in_cuba_scenario():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    for _ in range(3600):
        g.tick()
    assert not g.world.own.sys.fire and g.world.own.sys.smoke == 0.0
