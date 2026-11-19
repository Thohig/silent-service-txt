"""Sjögångens verkan (V1–V4): havsbruset, jagarens ping, flygets radar, sikten och vågorna."""
import random

from sim.environment import (Environment, radar_clutter_f, sea_noise_db, sea_ping_loss_db)
from sim.ice import IceField


def test_sea_noise_is_referenced_to_beaufort_three_and_grows_with_the_wind():
    assert sea_noise_db(3) == 0
    assert sea_noise_db(5) == 5.0 and sea_noise_db(1) == -5.0
    env = Environment(background_noise=60.0, sea_state=3)
    assert env.noise_at(0, 0) == 60.0
    env.sea_state = 6
    assert env.noise_at(0, 0) == 67.5


def test_ice_noise_does_not_follow_the_sea():
    env = Environment(sea_state=6)
    env.ice = IceField.__new__(IceField)
    env.ice.noise_at = lambda x, y: 55.0
    assert env.noise_at(0, 0) == 55.0


def test_destroyer_ping_suffers_only_in_rough_sea():
    assert [sea_ping_loss_db(b) for b in range(8)] == [0, 0, 0, 0, 0, 3.0, 6.0, 9.0]


def test_radar_clutter_hides_masts_from_force_four():
    assert radar_clutter_f(3) == 1.0 and radar_clutter_f(1) == 1.0
    assert radar_clutter_f(4) <= 0.5 and radar_clutter_f(6) <= 0.25
    assert radar_clutter_f(6, surfaced=True) > radar_clutter_f(6)


def test_aircraft_radar_sees_the_periscope_less_far_in_rough_sea():
    """Över frön: flyget på 4 nm hittar masten i lugn sjö, aldrig i grov."""
    from sim.air import RADAR_MAST_NM, Aircraft, AircraftAI
    from sim.game import Game
    from sim.scenario import build_scenario
    hits = {}
    for sea in (2, 6):
        n = 0
        for seed in range(4):
            g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
            w = g.world
            w.env.sea_state = sea
            st = w.own.state
            st.depth = st.ordered_depth = 15.0
            w.own.sys.periscope_until = 10**9
            p = Aircraft("P9", st.x, st.y + 0.7 * RADAR_MAST_NM, 90.0)
            ac = AircraftAI(p, random.Random(seed), w.size_nm, 10**6, (-10.0, 18.0))
            got = []
            ac._detect = lambda *a, **k: got.append(a)
            for _ in range(200):
                ac._radar(w)
            n += bool(got)
        hits[sea] = n
    assert hits[2] == 4 and hits[6] == 0


def test_visibility_shrinks_in_a_gale():
    env = Environment(sea_state=3)
    v3 = env.visibility_nm(12 * 3600)
    env.sea_state = 6
    assert env.visibility_nm(12 * 3600) == v3 * 0.6


def test_waves_hide_small_ships_and_the_hull_sooner():
    from sim.periscope import detectable, visible_part, wave_height_m
    assert detectable("patrol", 7.0, 1.5, 1.5, wave_height_m(2))
    assert not detectable("patrol", 7.0, 1.5, 1.5, wave_height_m(5))
    assert visible_part("destroyer", 3.0, 1.5) == "helt"
    assert visible_part("destroyer", 3.0, 1.5, wave_height_m(6)) != "helt"


def test_rough_sea_widens_the_periscope_estimates_honestly():
    """Över frön: avståndets fel växer i grov sjö, och kvaliteten säger det (σ större)."""
    from sim.periscope import sea_sigma_f
    assert sea_sigma_f(3) == 1.0 and sea_sigma_f(6) > 1.25
    from sim.events import PeriscopeSighted
    from sim.game import Game
    from sim.scenario import default_scenario
    errs = {}
    for sea in (2, 6):
        e = []
        for seed in range(12):
            g = Game(default_scenario(random.Random(seed)), seed=seed)
            w = g.world
            w.env.sea_state = sea
            w.env.lat = None
            w.env.sunrise, w.env.sunset = 0, 24 * 3600
            st = w.own.state
            st.depth = st.ordered_depth = 15.0
            st.speed = st.ordered_speed = 3.0
            dd = next(v for v in w.contacts if v.kind == "destroyer")
            dd.state.x, dd.state.y = st.x, st.y + 2.0
            pics = []
            g.bus.subscribe(PeriscopeSighted, pics.append)
            g.command("periskop")
            for _ in range(20):
                g.tick()
            ships = [o for p in pics for o in p.picture.ships() if o.kind == "destroyer"]
            if ships:
                e.append(abs(ships[-1].range_nm - w.true_range(dd)) / w.true_range(dd))
        errs[sea] = sum(e) / len(e)
    assert errs[6] > errs[2]


# --- V3: periskopdjupet i grov sjö -------------------------------------------------------
def _pd_game(sea, speed, depth=17.0, seed=3):
    from sim.events import ReportDelivered
    from sim.game import Game
    from sim.scenario import default_scenario
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    for ai in w.ais:
        ai.can_force = False
    w.env.sea_state = sea
    st = w.own.state
    st.depth = st.ordered_depth = depth
    st.speed = st.ordered_speed = speed
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_heave_grows_with_sea_and_shrinks_with_speed_and_depth():
    from sim.ownship import OwnShip
    from sim.ship import ShipState
    own = OwnShip(ShipState(x=0, y=0, course=0, speed=2, depth=17))
    assert own.heave_amplitude(3) == 0.0
    a5 = own.heave_amplitude(5)
    assert a5 > 4.0 > own.heave_amplitude(4)
    own.state.speed = 7
    assert own.heave_amplitude(5) < a5 / 2
    own.state.speed, own.state.depth = 2, 40
    assert own.heave_amplitude(5) < a5 / 5


def test_slow_at_periscope_depth_in_a_gale_breaks_the_surface_and_is_reported():
    g, reports = _pd_game(5, 2.0)
    broke = False
    for _ in range(120):
        g.tick()
        broke |= g.world.own.broached(g.now)
    assert broke
    types = [r.type for r in reports]
    assert "broach" in types and "trim.heave" in types
    r = next(r for r in reports if r.type == "broach")
    assert r.alarm and r.speech


def test_enough_speed_keeps_the_tower_under():
    g, _ = _pd_game(5, 6.0)
    for _ in range(120):
        g.tick()
        assert not g.world.own.broached(g.now)


def test_calm_sea_never_heaves():
    g, _ = _pd_game(3, 0.0, depth=15.0)
    for _ in range(60):
        g.tick()
        assert g.world.own.heave_amp_m == 0.0


def test_trim_suggests_speed_and_the_suggestion_helps():
    g, reports = _pd_game(5, 2.0)
    for _ in range(30):
        g.tick()
    r = next(r for r in reports if r.type == "trim.heave")
    assert r.data["speed"] and 3 <= r.data["speed"] <= 7
    g.command(f"fart {r.data['speed']}")
    for _ in range(90):
        g.tick()
    t0 = g.now
    for _ in range(60):
        g.tick()
    assert g.world.own.sys.broach_until <= t0


def test_broached_tower_is_seen_by_aircraft_radar_like_a_surfaced_boat():
    from sim.air import RADAR_MAST_NM, Aircraft, AircraftAI
    g, _ = _pd_game(5, 2.0)
    w = g.world
    st = w.own.state
    w.own.sys.broach_until = w.time + 100
    p = Aircraft("P9", st.x, st.y + 2 * RADAR_MAST_NM, 90.0)
    ac = AircraftAI(p, random.Random(1), w.size_nm, 10**6, (-10.0, 18.0))
    got = []
    ac._detect = lambda *a, **k: got.append(a)
    for _ in range(50):
        ac._radar(w)
    assert got


def test_periscope_is_washed_over_part_of_the_time_in_a_gale():
    from sim.stations.periscope import PeriscopeWatch
    for sea, washed_any in ((3, False), (6, True)):
        g, reports = _pd_game(sea, 6.0)
        ps = g.station(PeriscopeWatch)
        g.command("periskop upp")
        n = 0
        for _ in range(60):
            g.tick()
            n += ps._washed()
        assert (n > 0) == washed_any
        assert ("off.periscope.washed" in [r.type for r in reports]) == washed_any
        if washed_any:
            assert n < 40
