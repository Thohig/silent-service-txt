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


def test_salt_water_in_the_battery_shorts_it_and_starts_a_fire_there():
    w = _world(depth=60, speed=4)
    own = w.own
    own.sys.dmg.water[2] = D.BATTERY_SHORT_T + 1
    own.sys.battery = 1.0
    _run(w, 2)
    assert own.sys.fire and own.sys.fire_room == 2
    assert own.sys.battery <= D.BATTERY_SHORT_KEEP + 0.01
    assert own.sys.propulsion == "turbine" and not own.turbine_fire     # turbinen går
    _, data = next(a for a in own.sys.alerts if a[0] == "fire")
    assert data["room"] == 2


def test_battery_fire_is_reported_in_the_battery_room():
    from sim.stations.engineering import PHRASES
    txt = PHRASES["fire"]({"compartment": "batterirummet", "room": 2})
    assert "batteriet" in txt and "Turbinen" not in txt
    assert "batterirummet" in PHRASES["fire.out"]({"room": 2})


def test_bilge_pumps_take_less_the_deeper_and_are_heard():
    assert D.bilge_capacity(0) == pytest.approx(D.BILGE_T_PER_MIN)
    assert D.bilge_capacity(250) == pytest.approx(D.BILGE_T_PER_MIN * 0.5)
    assert D.bilge_capacity(480) == pytest.approx(D.BILGE_T_PER_MIN * D.BILGE_MIN_F)
    w = _world(depth=100, speed=3)
    quiet = w.own.radiated_level(w.env)
    w.own.sys.dmg.water[5] = 2.0
    _run(w, 1)
    assert D.pumping(w.own) and w.own.radiated_level(w.env) > quiet + 1


def test_hush_stops_the_bilge_pumps_and_the_crew_asks_to_pump():
    from sim.stations.officer import OfficerStation
    g, reports = _game()
    own = g.world.own
    off = g.station(OfficerStation)
    off._hush_watch = lambda: None                  # tystnad i båten hela provet
    off.hushed = True
    own.add_leak(5, "svetsfog", 1.5)
    for _ in range(300):
        g.tick()
    assert not own.sys.dmg.bilge_on and own.sys.flooding > D.BILGE_T_PER_MIN
    assert any(r.type == "dc.bilge.hushed" for r in reports)
    sug = [r for r in reports if r.type == "dc.suggest.bilge"]
    assert sug and sug[0].data["order"] == "länsa"
    g.command("ja")
    for _ in range(5):
        g.tick()
    assert own.sys.dmg.bilge_on


def test_bilge_stop_holds_the_pumps_until_the_water_is_dangerous():
    g, reports = _game()
    own = g.world.own
    g.command("läns stopp")
    own.sys.dmg.water[6] = 5.0
    for _ in range(5):
        g.tick()
    assert not own.sys.dmg.bilge_on and any(r.type == "dc.bilge.off" for r in reports)
    own.sys.dmg.water[6] = 16.0
    for _ in range(5):
        g.tick()
    assert own.sys.dmg.bilge_on and any(r.type == "dc.bilge.danger" for r in reports)
    g.command("länsa")
    for _ in range(3):
        g.tick()
    assert any(r.type == "dc.bilge.on" for r in reports)


def _damaged_game(*components, health=0.4):
    g, reports = _game()
    for c in components:
        g.world.own.sys.health[c] = health
    return g, reports


def _tick(g, n):
    for _ in range(n):
        g.tick()


def test_the_crew_repairs_in_its_order_and_says_so():
    g, reports = _damaged_game("radio", "planes", "sonar")
    _tick(g, 30)
    r = next(r for r in reports if r.type == "dc.repair.start")
    assert r.data["component"] == "planes" and "rodren" in r.text and "sedan" in r.text.lower()
    assert g.world.own.sys.dmg.repair == "planes"


def test_the_captain_sets_what_is_repaired_first():
    g, reports = _damaged_game("radio", "planes")
    g.command("reparera radion")
    _tick(g, 3)
    assert g.world.own.sys.dmg.repair == "radio"
    assert any(r.type == "dc.repair.ack" and "radion" in r.text for r in reports)
    g.command("reparera")
    _tick(g, 3)
    assert any(r.type == "dc.repair.ack" and "radion, sedan rodren" in r.text for r in reports)


def test_repair_is_heard_unless_the_boat_is_hushed_then_slower():
    from sim.stations.officer import OfficerStation
    g, reports = _damaged_game("sonar")
    heard = []
    orig = g.world.emit
    g.world.emit = lambda tr: (heard.append(tr.kind), orig(tr))[-1]
    h0 = g.world.own.sys.health["sonar"]
    _tick(g, 100)
    loud = g.world.own.sys.health["sonar"] - h0
    assert "repair" in heard
    g2, _ = _damaged_game("sonar")
    off = g2.station(OfficerStation)
    off._hush_watch = lambda: None
    off.hushed = True
    _tick(g2, 1)                                     # skadekontrollen hör tystnaden från nästa sekund
    heard.clear()
    g2.world.emit = lambda tr: (heard.append(tr.kind), orig(tr))[-1]
    _tick(g2, 99)
    quiet = g2.world.own.sys.health["sonar"] - h0
    assert "repair" not in heard
    assert quiet == pytest.approx(loud * D.REPAIR_QUIET_F, rel=0.05)


def test_a_flooded_compartment_cannot_be_repaired_and_a_severe_hit_leaves_a_mark():
    g, reports = _damaged_game("planes")
    own = g.world.own
    own.sys.dmg.evacuated.add(9)
    own.sys.dmg.closed = True
    own.sys.dmg.water[9] = 20.0
    own.sys.dmg.bilge_on = False
    g.command("läns stopp")
    _tick(g, 5)
    assert own.sys.dmg.repair is None
    g.command("reparera roder")
    _tick(g, 3)
    assert any(r.type == "dc.repair.cannot" and "under vatten" in r.text for r in reports)
    own.sys.dmg.evacuated.clear()
    own.sys.dmg.water[9] = 0.0
    own.sys.dmg.cap["planes"] = 1.0
    D.limit(own, "planes", 0.75)
    own.sys.health["planes"] = 0.7
    _tick(g, 120)
    assert own.sys.health["planes"] == pytest.approx(0.75)
    assert any(r.type == "repaired" and "så gott det går" in r.text for r in reports)


def test_the_crew_asks_for_the_planes_first_when_we_sink():
    g, reports = _damaged_game("radio", "planes")
    g.command("reparera radion")
    g.world.own.sys.dmg.planes_jam, g.world.own.sys.dmg.jam_left = 1, 60
    _tick(g, 5)
    sug = [r for r in reports if r.type == "dc.suggest.repair_planes"]
    assert sug and sug[0].data["order"] == "reparera roder"


def test_repair_order_parses():
    from sim.stations.damage_control import Repair
    g, _ = _game()
    assert g.registry.parse("reparera rodren") == Repair("planes")
    assert g.registry.parse("laga sonaren först") == Repair("sonar")
    assert g.registry.parse("reparera") == Repair(None)


def test_shocks_make_a_scram_more_likely_for_a_while():
    w = _world()
    assert D.stress_factor(w.own.sys.dmg, D.STRESS_SCRAM_F) == 1.0
    w.own.apply_explosion(100, False, random.Random(5), src=(10, 10))
    assert w.own.sys.dmg.stress == pytest.approx(0.5)
    w.own.apply_explosion(40, False, random.Random(5), src=(10, 10))
    assert D.stress_factor(w.own.sys.dmg, D.STRESS_SCRAM_F) > 6
    _run(w, 3600)
    assert w.own.sys.dmg.stress == pytest.approx(0.75, rel=0.05)


def test_long_full_speed_warms_the_bearings_then_they_run():
    w = _world(depth=150, speed=26)
    own = w.own
    own.state.ordered_speed = 26
    _run(w, D.BEARING_WARN_S + 5)
    assert "wear.bearings_warm" in _alerts(w) and own.sys.health["propulsion"] == 1.0
    _run(w, D.BEARING_DAMAGE_S - D.BEARING_WARN_S)
    assert "wear.bearings_ran" in _alerts(w)
    assert own.sys.dmg.cap["propulsion"] <= D.BEARING_CAP        # (i 26 kn kaviterar den också)


def test_the_bearings_cool_when_we_slow_down():
    w = _world(depth=150, speed=26)
    w.own.state.ordered_speed = 26
    _run(w, D.BEARING_WARN_S - 60)
    w.own.state.ordered_speed = 15
    _run(w, 900)
    assert w.own.sys.dmg.bearing_heat_s == 0.0 and "wear.bearings_warm" not in _alerts(w)


def test_cavitating_long_pits_the_propeller():
    w = _world(depth=20, speed=12)
    w.own.state.ordered_speed = 12
    quiet = w.own.radiated_level(w.env)
    _run(w, D.CAVITATION_DAMAGE_S + 2)
    alerts = _alerts(w)
    assert "wear.cavitation" in alerts and "wear.eroded" in alerts
    assert w.own.sys.dmg.cap["propulsion"] == pytest.approx(1 - D.EROSION_CAP)
    assert w.own.radiated_level(w.env) == pytest.approx(quiet + D.EROSION_DB, abs=0.3)


def test_running_near_test_depth_makes_the_packing_leak():
    w = _world(depth=292, speed=4)
    w.own.state.ordered_depth = 292
    _run(w, D.DEEP_LEAK_S + 2)
    alerts = _alerts(w)
    assert alerts.index("wear.deep") < alerts.index("wear.packing")
    assert any(lk.compartment == 9 and lk.kind == "packbox" for lk in w.own.sys.dmg.leaks) or \
        "leak_stopped" in alerts


def test_the_crew_suggests_slowing_for_the_bearings():
    g, reports = _game()
    st = g.world.own.state
    st.speed = st.ordered_speed = 26
    g.world.own.sys.dmg.bearing_heat_s = D.BEARING_WARN_S
    for _ in range(5):
        g.tick()
    sug = [r for r in reports if r.type == "dc.suggest.bearings"]
    assert sug and sug[0].data["order"] == "fart 20"
    assert any(r.type == "wear.bearings_warm" for r in reports)


def test_below_a_lowered_test_depth_the_hull_does_not_wear_away_by_itself():
    """Jagad frö 63: en träff sänkte provdjupet till 180 m under oss på 237; skrovet nöttes mot det sänkta
    provdjupet, provdjupet sjönk med och skrovet brast. Nu nöts det bara under det konstruerade (300 m),
    och krossdjupet sjunker i samma proportion som provdjupet."""
    w = _world(depth=237, speed=1)
    w.own.state.ordered_depth = 237
    w.own.sys.hull = 0.3
    assert w.own.test_depth() < 237 < w.own.crush_depth()
    _run(w, 600)
    assert w.own.sys.hull == pytest.approx(0.3) and w.outcome is None
    assert w.own.crush_depth() == pytest.approx(450 * 0.65)
