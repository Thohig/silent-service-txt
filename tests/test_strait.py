"""Genom sundet: foto av ankarplatsen, kurs mot kända platser, utvägen kräver bilderna."""
import pytest
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.harbor import HarborDefense
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.navigation import NavigationStation


def _game(seed=0):
    return Game(build_scenario("sundet", random.Random(seed)), seed=seed)


def _said(g):
    out = []
    g.bus.subscribe(ReportDelivered, lambda e: out.append(e.report))
    return out


def _moored(g):
    return [v for v in g.world.contacts if v.kind == "moored"]


def _put_near_anchorage(g, r, day=True):
    """Ubåten på periskopdjup i farleden, ankarplatsen r sjömil rakt norrut."""
    w = g.world
    coast = w.env.seabed.features[0]
    o = w.own.state
    o.x, o.y = coast.channel_x, float(coast.shore(coast.channel_x)) + 0.2
    o.depth = o.ordered_depth = 15
    o.speed = o.ordered_speed = 0
    w.env.clock_start = (12 if day else 2) * 3600
    for i, v in enumerate(_moored(g)):
        v.state.x, v.state.y = o.x, o.y + r + 0.5 * i


def test_scenario_builds_with_harbor_defence_and_anchorage():
    for seed in range(4):
        g = _game(seed)
        w = g.world
        assert any(isinstance(sp, HarborDefense) for sp in w.spawners)
        assert len(_moored(g)) >= 3
        assert all(w.env.seabed.depth_at(v.state.x, v.state.y) > 10 for v in _moored(g))
        assert w.env.seabed.depth_at(w.own.state.x, w.own.state.y) > 1000
        assert {"Ankarplatsen", "Nätet"} <= set(g.knowledge.waypoints)
        assert not w.env.is_day(0)                      # start i mörker


def test_photo_quality_follows_range_and_light():
    for r, day, want in ((1.0, True, Quality.SAKER), (2.0, True, Quality.GOD),
                         (3.0, True, Quality.OSAKER), (1.0, False, Quality.OSAKER)):
        g = _game()
        _put_near_anchorage(g, r, day)
        said = _said(g)
        g.command("foto")
        for _ in range(45):
            g.tick()
        done = [x for x in said if x.type == "off.photo.done"]
        assert done, [x.type for x in said]
        assert done[0].quality == want
        assert g.knowledge.best_photo == want


def test_photo_too_far_gives_nothing():
    g = _game()
    _put_near_anchorage(g, 5.0)
    said = _said(g)
    g.command("foto")
    for _ in range(45):
        g.tick()
    assert any(x.type == "off.photo.nothing" for x in said)
    assert g.knowledge.best_photo is None


def test_steer_to_known_place():
    g = _game()
    said = _said(g)
    g.command("kurs mot ankarplatsen")
    for _ in range(10):
        g.tick()
    nav = g.station(NavigationStation)
    wp = g.knowledge.waypoints["Ankarplatsen"]
    from sim.geo import bearing_to
    want = round(bearing_to(nav.est_x, nav.est_y, wp.x, wp.y)) % 360
    assert abs(g.world.own.state.ordered_course - want) < 1
    assert any(x.type == "nav.steer" for x in said)
    g.command("kurs mot nätet")
    g.tick()
    g.command("kurs mot havanna")
    for _ in range(5):
        g.tick()
    assert any(x.type == "nav.steer.none" for x in said)


def test_leaving_without_good_photos_does_not_end_the_game():
    g = _game()
    w = g.world
    for v in w.ais:
        if hasattr(v, "datum"):
            v.datum, v.state = None, "patrol"
    w.own.state.y = -1.0
    w._check_outcome()
    assert w.outcome is None
    w.mission["best_photo"] = int(Quality.OSAKER)
    w._check_outcome()
    assert w.outcome is None
    w.mission["best_photo"] = int(Quality.GOD)
    w._check_outcome()
    assert w.outcome["outcome"] == "recon_done"


def test_navigator_suggests_the_way_out_only_after_the_photos():
    g = _game()
    nav = g.station(NavigationStation)
    assert all(p.key != "idle_exit" for p in nav.idle_proposals())
    g.knowledge.best_photo = Quality.GOD
    exits = [p for p in nav.idle_proposals() if p.key == "idle_exit"]
    assert exits and exits[0].order == "kurs 180"


def test_exit_route_avoids_land():
    g = _game()
    nav = g.station(NavigationStation)
    coast = g.knowledge.bathymetry.features[0]
    g.knowledge.best_photo = Quality.GOD
    nav.est_x, nav.est_y = coast.channel_x, coast.bay_y - 1.0   # i farleden: rakt söderut
    c, _, _ = nav.exit_route()
    assert c == 180 and nav.exit_via is None
    nav.est_x, nav.est_y = coast.bay_x + 1.5, coast.bay_y       # i bukten: runt land
    route = nav.exit_route()
    assert route is not None and nav.exit_via is not None
    c, dist, _ = route
    assert 3.0 < dist < 25                       # genom farleden och ut till närmaste kant


def test_harbor_ship_moors_in_the_bay():
    g = _game(1)
    w = g.world
    for _ in range(3 * 3600):
        w.tick()
        if any(v.kind == "moored" and v.id.startswith("H") for v in w.contacts):
            break
    assert any(v.kind == "moored" and v.id.startswith("H") for v in w.contacts)


def _inbound(g):
    return [v for v in g.world.contacts if v.kind == "merchant" and abs(v.state.course) < 30]


@pytest.mark.slow
def test_patrol_boat_escorts_an_inbound_ship_to_the_gate():
    from sim.geo import distance
    from sim.harbor import PatrolBoatAI
    g = _game(0)
    w = g.world
    boat = next(a for a in w.ais if isinstance(a, PatrolBoatAI))
    best = (0, 0, None)                                  # (framför, nära, fartygets y vid slut)
    ahead = near = 0
    ship = None
    for _ in range(5 * 3600):
        w.tick()
        if boat.state == "escort":
            ship = next(v for v in w.contacts if v.id == boat.escorting)
            bs, ts = boat.vessel.state, ship.state
            ahead += bs.y > ts.y
            near += distance(bs.x, bs.y, ts.x, ts.y) < 0.8
        elif ship is not None:
            if ahead > best[0]:
                best = (ahead, near, ship.state.y)
            ahead = near = 0
            ship = None
    assert best[0] > 300 and best[1] > 300               # en bra stund framför fartyget
    assert best[2] > net_y(g) - 0.4                      # eskorten slutar vid grinden


def net_y(g):
    return next(sp for sp in g.world.spawners if isinstance(sp, HarborDefense)).net.y


def test_moored_ships_do_not_drift():
    g = _game(0)
    w = g.world
    m = _moored(g)[0]
    x0, y0 = m.state.x, m.state.y
    for _ in range(1800):
        w.tick()
    assert (m.state.x, m.state.y) == (x0, y0)


@pytest.mark.slow
def test_harbor_ships_pass_through_the_gate():
    g = _game(1)
    w = g.world
    net = next(sp for sp in w.spawners if isinstance(sp, HarborDefense)).net
    prev, crossings = {}, []
    for _ in range(4 * 3600):
        w.tick()
        for v in w.contacts:
            if v.id.startswith("H"):
                py = prev.get(v.id)
                if py is not None and (py - net.y) * (v.state.y - net.y) < 0:
                    crossings.append(v.state.x - net.gate_x)
                prev[v.id] = v.state.y
    assert crossings and all(abs(dx) < 0.05 for dx in crossings)


def test_follow_order_steers_on_the_contacts_bearing():
    from sim.entities import Vessel
    from sim.ship import ShipState
    g = _game(0)
    o = g.world.own.state
    g.world.contacts.append(Vessel("H99", "merchant", ShipState(x=o.x + 0.8, y=o.y + 1.2, course=10,
                                                               speed=6), side="neutral"))
    said = _said(g)
    g.command("följ S-9")
    for _ in range(5):
        g.tick()
    assert any(x.type == "nav.follow.none" for x in said)
    held = []
    for _ in range(600):
        g.tick()
        held = [d for d, t in g.knowledge.tracks.items() if t.held and t.last_bearing is not None]
        if held:
            break
    assert held
    g.command(f"följ {held[0]}")
    for _ in range(20):
        g.tick()
    nav = g.station(NavigationStation)
    assert nav.goal == "follow"
    tr = g.knowledge.tracks[held[0]]
    assert abs(g.world.own.state.ordered_course - round(tr.last_bearing) % 360) <= 15
    assert any(x.type == "nav.follow" for x in said)
    g.command("kurs 090")
    g.tick()
    assert nav.goal is None


# --- väntläget utanför grinden (första steget i grindtricket) -----------------------
def _harbor(g):
    return next(sp for sp in g.world.spawners if isinstance(sp, HarborDefense))


def test_navigator_suggests_a_wait_point_seaward_of_the_gate():
    for seed in range(1, 6):
        g = _game(seed)
        said = _said(g)
        for _ in range(40):
            g.tick()
        sug = [r for r in said if r.type == "nav.suggest.wait"]
        assert sug and "[ja: smygmotor, väntläget]" in sug[0].text, seed
        wp = g.knowledge.waypoints["Väntläget"]
        net, anchor = g.knowledge.waypoints["Nätet"], g.knowledge.waypoints["Ankarplatsen"]
        assert float(g.knowledge.bathymetry.depth_at(wp.x, wp.y)) >= 40, seed
        assert 1.2 <= ((wp.x - net.x) ** 2 + (wp.y - net.y) ** 2) ** 0.5 <= 1.6, seed
        assert wp.y < net.y < anchor.y + 0.5, seed          # ute på havssidan om nätet
        assert abs(wp.x - _harbor(g).net.gate_x) <= 0.6, seed   # nära farleden, vid sidan av


def test_wait_order_takes_us_there_and_holds_station():
    g = _game(2)
    said = _said(g)
    for _ in range(40):
        g.tick()
    nav = g.station(NavigationStation)
    wp = g.knowledge.waypoints["Väntläget"]
    o = g.world.own.state
    o.x, o.y = wp.x - 0.3, wp.y - 0.3                      # nära, med besticket i fas
    nav.est_x, nav.est_y = o.x, o.y
    g.command("väntläget")
    assert nav.goal == "wait"
    for _ in range(15 * 60):
        g.tick()
        if any(r.type == "nav.wait.arrived" for r in said):
            break
    assert any(r.type == "nav.wait.arrived" for r in said)
    for _ in range(30):
        g.tick()
    assert o.ordered_speed <= 2.0 and nav.goal == "wait"
    g.command("fart 8")                                    # kaptenen tar över
    assert nav.goal is None


def test_photo_goal_ends_the_game_when_good():
    from sim.scenario import build_scenario
    g = Game(build_scenario("sundet-in", random.Random(1)), seed=1, warm_up=False)
    w = g.world
    assert "escape" not in w.mission and w.mission["photo"]["outcome"] == "photo_taken"
    w.mission["best_photo"] = int(Quality.OSAKER)
    w._check_outcome()
    assert w.outcome is None
    w.mission["best_photo"] = int(Quality.GOD)
    w._check_outcome()
    assert w.outcome["outcome"] == "photo_taken"


@pytest.mark.slow
def test_strait_in_hands_over_at_the_wait_point_with_a_ship_coming_in():
    from sim.harbor import HarborDefense
    from sim.scenario import SCENARIOS, STRAIT_IN_LIMIT_S, STRAIT_IN_WARM_S, build_scenario
    assert SCENARIOS["sundet-in"].minutes
    for seed in range(3):
        g = Game(build_scenario("sundet-in", random.Random(seed)), seed=seed)
        w = g.world
        net = next(sp for sp in w.spawners if isinstance(sp, HarborDefense)).net
        o = w.own.state
        assert g.now == STRAIT_IN_WARM_S and not g.over
        assert w.env.is_day(g.now)
        assert 1.0 < net.y - o.y < 1.8 and abs(o.x - net.gate_x) < 0.6
        inbound = [v for v in w.contacts if v.kind == "merchant" and 0.0 < o.y - v.state.y < 1.0
                   and abs(v.state.x - net.gate_x) < 0.3]
        assert inbound, "ett fartyg på väg in strax utanför oss"
        assert any(t.civil and t.solution is not None for t in g.knowledge.tracks.values())
        assert w.patrol_end == STRAIT_IN_WARM_S + STRAIT_IN_LIMIT_S
