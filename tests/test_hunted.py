"""Jagade: jagare i grupp, upptrappning till skarpa sjunkbomber och målet att lämna kvadraten."""
import random
from dataclasses import replace

from sim.enemy import SHARED_SIGMA_NM, DestroyerAI
from sim.entities import Vessel
from sim.environment import Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.ownship import OwnShip
from sim.scenario import build_scenario
from sim.ship import ShipState
from sim.stations.navigation import NavigationStation
from sim.world import World


def _world(own_xy=(10, 10), own_depth=40, dds=((10, 11.0),), seed=1):
    own = OwnShip(ShipState(x=own_xy[0], y=own_xy[1], course=0, speed=3, depth=own_depth,
                            max_depth=400))
    vs = [Vessel(f"DD{i + 1}", "destroyer", ShipState(x=x, y=y, course=90, speed=12,
                                                      turn_rate=2, accel=0.3, max_speed=32))
          for i, (x, y) in enumerate(dds)]
    w = World(own=own, contacts=vs, env=Environment(current_kn=0), rng=random.Random(seed))
    ais = [DestroyerAI(v, random.Random(seed + i), escalate_after=2) for i, v in enumerate(vs)]
    for a in ais:
        a.partners = [b for b in ais if b is not a]
    w.ais += ais
    return w, ais


def test_fix_is_shared_with_partner_at_lower_precision():
    w, (a, b) = _world(dds=((10, 12.0), (10, 30.0)))
    a._set_datum(w, 10.0, 10.0, 50.0, 0.08, fix=True)
    assert b.datum is not None
    assert abs(b.datum.sigma - (0.08 + SHARED_SIGMA_NM)) < 1e-9
    # en egen färsk och bättre bild skrivs inte över
    b._set_datum(w, 10.1, 10.0, 50.0, 0.08, fix=True)
    a._set_datum(w, 10.0, 10.0, 50.0, 0.08, fix=True)
    assert b.datum.sigma == 0.08 and b.datum.x == 10.1


def test_destroyer_escalates_to_live_charges_after_practice_attacks():
    w, (ai,) = _world(own_depth=40, dds=((10, 11.0),))
    for _ in range(1500):
        w.tick()
        if ai.attacks >= 2:
            break
    assert ai.attacks >= 2
    assert ai.roe == "lethal"


def test_escape_needs_outside_margin_and_no_aware_hunter():
    w, (ai,) = _world(own_xy=(-0.8, 10), own_depth=150, dds=((15, 15),))
    w.mission["escape"] = {"margin_nm": 0.5, "outcome": "escaped"}
    ai.start_hunt(-0.8, 10, 150, 0.5)
    w._check_outcome()
    assert w.outcome is None                    # jagaren söker oss fortfarande
    ai.state, ai.datum = "patrol", None
    w._check_outcome()
    assert w.outcome["outcome"] == "escaped"


def test_escape_not_counted_inside_margin():
    w, (ai,) = _world(own_xy=(-0.3, 10), own_depth=150, dds=((15, 15),))
    w.mission["escape"] = {"margin_nm": 0.5, "outcome": "escaped"}
    w._check_outcome()
    assert w.outcome is None


def test_hunted_scenario_starts_in_contact_with_two_destroyers():
    for seed in range(4):
        sc = build_scenario("jagad", random.Random(seed))
        w = sc.world
        hunters = [a for a in w.ais if isinstance(a, DestroyerAI)]
        assert len(hunters) == 2
        assert hunters[0].aware() and hunters[0].datum.sigma < 0.3
        assert 2.0 < w.true_range(hunters[0].vessel) < 3.2
        assert w.own.state.depth < 60              # ovanför skiktet: därför hittade de oss
        assert w.env.seabed.depth_at(w.own.state.x, w.own.state.y) > 400   # djupt, men banken nära
        assert sc.escape_margin_nm is not None


def test_crew_hears_the_hunt_in_the_first_minute():
    """Över flera frön: sonar rapporterar aktiv sonar och en kontakt inom en minut."""
    for seed in range(4):
        g = Game(build_scenario("jagad", random.Random(seed)), seed=seed)
        types = []
        g.bus.subscribe(ReportDelivered, lambda ev: types.append(ev.report.type))
        for _ in range(60):
            g.tick()
        assert any("ping" in t or "active" in t for t in types), types
        assert g.knowledge.threat_held()


def test_navigator_points_the_way_out_away_from_threats():
    g = Game(build_scenario("jagad", random.Random(0)), seed=0)
    nav = g.station(NavigationStation)
    for _ in range(40):
        g.tick()
    nav.est_x, nav.est_y = 8.0, 9.0
    g.knowledge.bathymetry = None                           # bara hoten, inte banken
    for tr in g.knowledge.tracks.values():                  # inga hot västerut
        tr.observations[-1] = replace(tr.observations[-1], bearing=90.0)
    c, dist, clear = nav.exit_route()
    assert c == 270 and clear and abs(dist - (8.0 + 1.0 + nav.uncertainty())) < 1e-6
    # ett hot rakt västerut: då hellre en något längre väg söderut
    for tr in g.knowledge.tracks.values():
        tr.observations[-1] = replace(tr.observations[-1], bearing=270.0)
    c, _, _ = nav.exit_route()
    assert c == 180


def test_navigator_does_not_turn_us_back_into_the_area():
    g = Game(build_scenario("jagad", random.Random(0)), seed=0)
    nav = g.station(NavigationStation)
    nav.est_x, nav.est_y = -0.2, 10.0
    assert all(p.key != "idle_area" for p in nav.idle_proposals())


def test_destroyers_do_not_mistake_each_others_pings_for_the_sub():
    w, (a, b) = _world(own_depth=200, dds=((10, 14.0), (10, 15.0)))
    for _ in range(300):
        w.tick()
    assert a.datum is None and b.datum is None


def test_deep_sub_is_lost_in_the_dead_zone_under_the_destroyer():
    from sim.enemy import DEAD_ZONE_DEG
    import math
    # 200 m djup: döda zonen ~0,3 nm
    w, (ai,) = _world(own_depth=200, dds=((10, 10.15),))
    assert 0.15 * 1852 < 200 / math.tan(math.radians(DEAD_ZONE_DEG))
    for _ in range(10):
        ai.datum = None
        ai._ping(w, ai._noise(w))
        assert ai.datum is None
    # grunt går det inte att gömma sig rakt under
    w, (ai,) = _world(own_depth=40, dds=((10, 10.15),))
    ai._ping(w, ai._noise(w))
    assert ai.datum is not None


def test_sonar_is_deaf_after_nearby_explosion():
    from sim.entities import Transient
    from sim.enemy import DEAF_S
    w, (ai,) = _world(own_depth=40, dds=((10, 11.0),))
    w.emit(Transient("explosion", 10, 10.5, 50, 220, "DD1", 0))
    w.tick()
    w.tick()
    assert ai.deaf_until >= w.time
    pings = 0
    for _ in range(DEAF_S - 5):
        w.tick()
        pings += any(t.kind == "ping" and t.source_id == "DD1" for t in w.transients)
    assert pings == 0


def test_escape_counts_when_hunter_chases_a_decoy_far_away():
    w, (ai,) = _world(own_xy=(-2.0, 10), own_depth=150, dds=((15, 15),))
    w.mission["escape"] = {"margin_nm": 1.0, "outcome": "escaped"}
    ai.start_hunt(1.5, 10, 150, 0.08)          # datum på ett skenmål 3,5 nm bort
    w._check_outcome()
    assert w.outcome["outcome"] == "escaped"


def test_hunted_short_starts_with_live_charges_close_in():
    from sim.scenario import HUNTED_SHORT_LIMIT_S, HUNTED_SHORT_SIZE, SCENARIOS
    assert SCENARIOS["jagad-kort"].minutes
    for seed in range(4):
        sc = build_scenario("jagad-kort", random.Random(seed))
        w = sc.world
        dd1, dd2 = [a for a in w.ais if isinstance(a, DestroyerAI)]
        assert dd1.aware() and dd1.roe == "lethal" and dd2.roe == "lethal"
        assert 1.3 < w.true_range(dd1.vessel) < 1.8
        assert w.size_nm == HUNTED_SHORT_SIZE and w.patrol_end == HUNTED_SHORT_LIMIT_S
        o = w.own.state
        assert min(o.x, w.size_nm - o.x) < 2.6         # nära en kant, men DD2 är där
        assert w.true_range(dd2.vessel) < 4.0


def test_hunted_short_time_limit_ends_the_game():
    from sim.scenario import HUNTED_SHORT_LIMIT_S
    g = Game(build_scenario("jagad-kort", random.Random(2)), seed=2)
    g.world.time = HUNTED_SHORT_LIMIT_S
    g.tick()
    assert g.over and g.world.outcome["outcome"] == "patrol_end"
    assert "Uppdraget har misslyckats" in g.scenario.outcome_text["patrol_end"]


def test_crew_hears_the_short_hunt_in_the_first_minute():
    for seed in range(3):
        g = Game(build_scenario("jagad-kort", random.Random(seed)), seed=seed)
        for _ in range(60):
            g.tick()
        assert g.knowledge.hunted(g.now) and g.knowledge.threat_held()


def test_plot_does_not_ask_for_tma_legs_while_hunted():
    from sim.stations.plot import PlotTeam
    g = Game(build_scenario("jagad", random.Random(0)), seed=0)
    for _ in range(60):
        g.tick()
    assert g.knowledge.hunted(g.now)
    assert g.station(PlotTeam).idle_proposals() == []


def test_sprint_proposal_always_orders_the_turbine():
    """Förslaget levereras sent; har kaptenen hunnit beordra smygmotor ska ja ändå ge turbin."""
    from sim.stations.engineering import EngineeringStation
    g = Game(build_scenario("jagad", random.Random(0)), seed=0)
    eng = g.station(EngineeringStation)
    order, data = eng._sprint()
    assert "turbin" in order and f"fart {data['speed']}" in order


def test_way_out_avoids_running_over_the_bank():
    """Jagade vill springa djupt: vägen ut över banken (grundare än 300 m på kortet)
    räknas längre, så navigatören väljer djupt vatten även om det är något längre."""
    from sim.stations.navigation import EXIT_DEEP_M
    for seed in range(4):
        g = Game(build_scenario("jagad", random.Random(seed)), seed=seed)
        nav = g.station(NavigationStation)
        for tr in g.knowledge.tracks.values():
            tr.held = False                                 # inga hot: bara botten
        c, _, _ = nav.exit_route()
        chart = g.knowledge.bathymetry
        bank_west = chart.depth_at(0.5, nav.est_y) < chart.depth_at(19.5, nav.est_y)
        assert c != (270.0 if bank_west else 90.0)
        assert nav._shallow_nm(nav.est_x, nav.est_y, c, 3.0) < 1.0
        assert EXIT_DEEP_M >= 250
