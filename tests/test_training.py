"""Övningen (`ovning`): Kolafjorden, farleden, fixar från bryggan, land som skymmer."""
import math
import random

import pytest

from sim.environment import Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import OwnShip
from sim.scenario import build_scenario
from sim.seabed import ISLAND_CLEAR_NM, Seabed, kola_seabed
from sim.ship import ShipState
from sim.stations.navigation import NavigationStation
from sim.world import LAND_BLOCK_DB, World


def _game(seed=1):
    return Game(build_scenario("ovning", random.Random(seed)), seed=seed)


def test_fjord_is_water_with_land_on_both_sides_and_deep_sea_outside():
    for seed in range(8):
        sb = kola_seabed(random.Random(seed))
        f = sb.features[0]
        assert sb.has_land
        for (ax, ay), (bx, by) in zip(f.path, f.path[1:]):
            for t in (0.25, 0.5, 0.75):
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                if 0 <= y <= f.shore_y:
                    assert sb.depth_at(x, y) > 60, (seed, x, y)            # fjordens mitt
                    assert sb.depth_at(x - 2.0, y) <= 0                     # land väster
                    assert sb.depth_at(x + 2.5, y) <= 0                     # land öster
        mx = f.path[-1][0]
        assert sb.depth_at(mx, f.shore_y + 1.5) > 150                       # djupt utanför
        for ix, iy, r in f.islands:
            assert sb.depth_at(ix, iy) <= 0                                 # holmen är land
            hw, _, a = f._along(ix, iy)
            assert float(a) - r >= ISLAND_CLEAR_NM - 0.01                   # farleden fri


def test_in_fjord_only_inside_the_mouth():
    sb = kola_seabed(random.Random(3))
    f = sb.features[0]
    x, y = f.path[1]
    assert bool(f.in_fjord(x, y))
    assert not bool(f.in_fjord(f.path[-1][0], f.shore_y + 2.0))


def _world(sb, x, y, depth=0.0, speed=0.0, course=0.0):
    env = Environment(current_kn=0.0, seabed=sb)
    own = OwnShip(ShipState(x=x, y=y, course=course, speed=speed, depth=depth, max_depth=400))
    return World(own=own, env=env, rng=random.Random(1), size_nm=16.0)


def test_land_blocks_sound_and_sight():
    sb = kola_seabed(random.Random(1))
    f = sb.features[0]
    x, y = f.path[1]
    w = _world(sb, x, y)
    assert not w.land_between(x, y, x, y + 1.0)              # uppför fjorden
    assert w.land_between(x, y, x + 3.0, y)                  # genom berget
    assert w.in_sight(x, y + 1.0)
    assert not w.in_sight(x + 3.0, y)
    # samma avstånd, med och utan berg emellan
    assert w.land_between(x, y, x + 1.0, y)
    assert w.tl_to_own(x + 1.0, y, 5.0) - w.tl_to_own(x, y + 1.0, 5.0) > LAND_BLOCK_DB - 5


def test_no_land_no_blocking():
    sb = Seabed(base=2000.0)
    w = _world(sb, 5.0, 5.0)
    assert not w.land_between(0.0, 0.0, 10.0, 10.0)


def test_surfaced_sub_grounds_in_shallow_water():
    sb = Seabed(base=5.0, min_depth=1.0)
    w = _world(sb, 5.0, 5.0, depth=0.0, speed=4.0)
    for _ in range(10):
        w.tick()
    assert w.own.sys.bottom_contact


def test_start_on_the_surface_with_the_bridge_manned_and_a_fairway():
    for seed in range(4):
        g = _game(seed)
        own = g.world.own
        assert own.surfaced and own.sys.bridge == "manned"
        assert abs((own.state.course + 180) % 360 - 180) < 45          # ut mot havet (norrut)
        assert len(g.knowledge.fairway) >= 3
        assert g.knowledge.fairway_to in g.knowledge.waypoints
        f = g.world.env.seabed.features[0]
        assert bool(f.in_fjord(own.state.x, own.state.y))


def test_navigator_suggests_the_fairway_early():
    g = _game(2)
    seen = []
    g.bus.subscribe(ReportDelivered, lambda e: seen.append(e.report.data.get("order")))
    for _ in range(90):
        g.tick()
    assert "farleden" in seen


def test_fairway_order_steers_and_fixes_from_the_bridge():
    g = _game(1)
    nav = g.station(NavigationStation)
    g.command("farleden")
    for _ in range(400):
        g.tick()
    assert nav.goal == "fairway"
    assert nav.fixes                                       # pejlingar från bryggan
    assert nav.uncertainty() < 0.2
    o = g.world.own.state
    assert math.dist((nav.est_x, nav.est_y), (o.x, o.y)) < 0.25


def test_diving_in_the_fjord_is_warned_and_ends_the_exercise():
    g = _game(1)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    g.command("djup 40")
    for _ in range(120):
        g.tick()
        if g.over:
            break
    assert "nav.fjord_dive" in said
    assert g.world.outcome["outcome"] == "dived_in_fjord"


def test_training_officer_is_silent_without_a_programme():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    for _ in range(600):
        g.tick()
    assert not any(t.startswith("train.") for t in said)


def _yes_bot(seed, minutes):
    g = _game(seed)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.type))
    bot_t, closest = 0, 99.0
    for _ in range(minutes * 60):
        g.tick()
        o = g.world.own.state
        if g.world.own.surfaced:
            for v in g.world.neutral_ships:
                closest = min(closest, math.dist((o.x, o.y), (v.state.x, v.state.y)))
        if g.suggestion and g.suggestion[2] > bot_t:
            bot_t = g.suggestion[2]
            g.command("ja")
        if g.over:
            break
    return g, said, closest


@pytest.mark.slow
def test_yes_bot_gets_out_and_completes_the_programme():
    for seed in range(1, 5):
        g, said, closest = _yes_bot(seed, 150)
        assert g.world.outcome["outcome"] == "training_done", seed
        assert said.count("train.step.done") == 11, seed
        assert "train.partner" in said, seed
        assert "train.done" in said, seed
        assert closest > 0.2, seed                    # inga fartyg nära i ytläge
        assert g.now < 135 * 60, seed


@pytest.mark.slow
def test_passive_captain_runs_aground_in_the_first_bend():
    g = _game(1)
    for _ in range(40 * 60):
        g.tick()
        if g.over:
            break
    assert g.world.outcome["outcome"] == "grounded"


def test_exercise_ship_is_friendly_and_stays_in_the_area():
    from sim.exercise import ExerciseShipAI
    g = _game(3)
    ship = next(v for v in g.world.contacts if v.kind == "guardship")
    ai = next(a for a in g.world.ais if isinstance(a, ExerciseShipAI))
    assert ship.side == "neutral" and not ai.aware() and not ai.can_force
    for _ in range(40 * 60):
        g.world.tick()
        assert math.dist((ship.state.x, ship.state.y), ai.center) < ai.radius + 1.0


def test_guardship_track_is_friendly_not_a_threat():
    from sim.knowledge import ContactTrack
    tr = ContactTrack("S-2", 0, classification="ytfartyg, tvåskruv, trolig bevakningsfartyg")
    assert tr.friendly and not tr.threat
    assert ContactTrack("S-3", 0, classification="ytfartyg").threat


def test_nobody_suggests_diving_in_the_fjord():
    g = _game(1)
    assert any(st.vetoes("djup 100") for st in g.stations)
    assert any(st.vetoes("turbin, djup 40") for st in g.stations)
    assert not any(st.vetoes("kurs 090") for st in g.stations)
    assert not any(st.vetoes("djup 0") for st in g.stations)


def test_partner_report_only_within_telephone_range():
    from sim.exercise import UK_RANGE_NM, partner_report
    g = _game(2)
    ship = next(v for v in g.world.contacts if v.kind == "guardship")
    o = g.world.own.state
    rep = partner_report(g.world, random.Random(1))
    assert (rep is None) == (math.dist((o.x, o.y), (ship.state.x, ship.state.y)) > UK_RANGE_NM)
    o.x, o.y = ship.state.x + 1.0, ship.state.y
    rep = partner_report(g.world, random.Random(1))
    assert rep is not None and rep["course"] % 5 == 0


def _target_world(dx=0.0):
    """Ubåten och ett stillaliggande bevakningsfartyg 1 nm norrut (dx åt sidan)."""
    from sim.entities import Vessel
    sb = Seabed(base=2000.0)
    w = _world(sb, 5.0, 5.0, depth=40.0)
    ship = Vessel("SKR1", "guardship", ShipState(x=5.0 + dx, y=6.0, course=90.0, speed=0.0),
                  side="neutral")
    w.contacts.append(ship)
    return w, ship


def test_exercise_torpedo_runs_under_the_target_without_sinking_it():
    from sim.exercise import torpedo_report
    from sim.weapons import TORPEDO_TYPES, launch_torpedo
    w, ship = _target_world()
    t = launch_torpedo(w, TORPEDO_TYPES["övning"], 0.0)
    for _ in range(200):
        w.tick()
    assert not ship.sunk
    assert not any(tr.kind == "explosion" for tr in w.transients)
    assert t.passed["SKR1"] < 0.03
    rep = torpedo_report(w)
    assert rep["hit"] and "hostile_act" not in w.mission


def test_exercise_torpedo_miss_is_reported_with_distance():
    from sim.exercise import torpedo_report
    from sim.weapons import TORPEDO_TYPES, launch_torpedo
    w, ship = _target_world(dx=0.1)
    launch_torpedo(w, TORPEDO_TYPES["övning"], 0.0)
    for _ in range(200):
        w.tick()
    rep = torpedo_report(w)
    assert not rep["hit"] and 150 <= rep["miss_m"] <= 220 and rep["seen"]


def test_training_loads_only_exercise_torpedoes_and_never_offers_to_fire():
    from sim.stations.torpedo_room import TorpedoRoom
    g = _game(1)
    tr = g.station(TorpedoRoom)
    assert [t.load for t in tr.tubes[:2]] == ["övning", "övning"]
    assert all(t.load is None for t in tr.tubes[2:])
    assert tr.idle_proposals() == []                       # inget att ladda om med
    from sim.stations.training import STEPS
    assert STEPS["torped"].order is None                    # vapen: aldrig en ja-order


def test_firing_solution_on_the_guardship_only_during_the_torpedo_exercise():
    """Torpedrummet säger skjutlösning på vårt eget fartyg bara när övningsledaren
    har börjat torpedövningen, inte så fort plottet har en god lösning."""
    from sim.events import TorpedoExercise
    from sim.knowledge import ContactTrack
    from sim.reports import Quality
    from sim.stations.torpedo_room import TorpedoRoom
    from sim.tma import Solution
    g = _game(1)
    room = g.station(TorpedoRoom)
    ex, ey = g.own_position_estimate()
    sol = Solution(t=g.now, t_ref=g.now, state=(ex, ey + 1.5, 0.0, 0.0), x=ex, y=ey + 1.5,
                   course=0.0, speed=0.0, range_nm=1.5, bearing=0.0, range_sigma=0.1,
                   course_sigma=10.0, speed_sigma=1.0, quality=Quality.GOD, n_obs=30,
                   span_s=600, own_maneuvered=True, rms_residual=0.5)
    g.knowledge.tracks["S-9"] = ContactTrack(
        "S-9", 0, classification="ytfartyg, tvåskruv, trolig bevakningsfartyg",
        class_quality=Quality.GOD, solution=sol)
    said = []
    room.suggest = lambda key, typ, data, **kw: said.append(typ)
    room._readiness()
    assert said == []                                       # lyssningen, dykningen …
    g.bus.publish(TorpedoExercise(g.now, True))
    room._readiness()
    assert said == ["torp.ready"]


@pytest.mark.slow
def test_short_variant_hands_over_at_periscope_depth_in_the_area():
    g = Game(build_scenario("ovning-kort", random.Random(1)), seed=1)
    nav = g.station(NavigationStation)
    a = g.knowledge.waypoints["Övningsområdet"]
    assert g.world.own.state.depth <= 18 and not g.world.own.surfaced
    assert math.dist((nav.est_x, nav.est_y), (a.x, a.y)) < 1.5
    assert g.knowledge.periscope is not None                # vakten har svept
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report.data.get("order")))
    for _ in range(180):
        g.tick()
    assert "djup 100" in said                               # första förslaget inom 3 min


@pytest.mark.slow
def test_short_variant_with_a_captain_who_fires():
    fired = 0
    for seed in range(1, 5):
        g = Game(build_scenario("ovning-kort", random.Random(seed)), seed=seed)
        pending, said = [], []

        def on(e, pending=pending, said=said):
            r = e.report
            said.append(r.type)
            if r.type == "train.torpedo.brief" and r.data.get("good") and r.data.get("tubes"):
                pending.append(f"eld tub {r.data['tubes'][0]} mot {r.data['designation']}")
        g.bus.subscribe(ReportDelivered, on)
        bot_t = 0
        for _ in range(60 * 60):
            g.tick()
            while pending:
                c = pending.pop()
                g.command(c)
            if g.suggestion and g.suggestion[2] > bot_t:
                bot_t = g.suggestion[2]
                g.command("ja")
            if g.over:
                break
        assert g.world.outcome["outcome"] == "training_done", seed
        fired += "train.torpedo.result" in said
    assert fired >= 3              # utan god lösning skjuter kaptenen inte, och steget hoppas över


def test_bridge_bearing_fix_aborted_when_the_bridge_is_cleared():
    """Pejlskivan på bryggan: utryms bryggan blir det ingen fix (som stjärnfixen)."""
    g = _game(1)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report))
    nav = g.station(NavigationStation)
    g.command("fix")
    g.tick()
    assert nav.tasks["fix"].bridge
    g.world.own.sys.bridge = "clearing"
    for _ in range(60):
        g.tick()
    aborted = [r for r in said if r.type == "nav.fix.aborted"]
    assert aborted and "bryggan" in aborted[0].text
    assert not any(r.type == "nav.fix.done" for r in said)
