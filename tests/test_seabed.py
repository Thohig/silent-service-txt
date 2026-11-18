"""Havsbotten: sanningen varierar, sjökortet är en egen, felaktig bild av den."""
import pytest
import math
import random

import numpy as np

from sim.chart import Mark, Track
from sim.game import Game
from sim.scenario import build_scenario
from sim.seabed import Seabed, Seamount, arctic_seabed, contours, kuba_seabed

GRID = np.meshgrid(np.linspace(0, 20, 81), np.linspace(0, 20, 81))


def _game(key="kuba", seed=3):
    return Game(build_scenario(key, random.Random(seed)), seed=seed)


def test_kuba_has_a_bank_but_we_start_over_deep_water():
    fractions = []
    for seed in range(12):
        sb = kuba_seabed(random.Random(seed), (10.0, 3.0))
        z = sb.depths(*GRID)
        fractions.append((z < 300).mean())
        assert z.min() > 80 and z.max() < 3500
        assert sb.depth_at(10.0, 3.0) > 1000
    assert 0.10 < np.median(fractions) < 0.25
    assert min(fractions) > 0.05


def test_arctic_has_a_ridge_well_below_the_ice():
    for seed in range(8):
        z = arctic_seabed(random.Random(seed)).depths(*GRID)
        assert 600 < z.min() < 1500
        assert z.max() > 2800


def test_chart_copy_is_shifted_and_smooth():
    sb = kuba_seabed(random.Random(1), (10.0, 3.0))
    chart = sb.chart_copy(random.Random(2), err_nm=0.5)
    assert chart is not sb and chart.rough == ()
    diff = np.abs(chart.depths(*GRID) - sb.depths(*GRID))
    assert diff.mean() > 20                       # kortet stämmer inte exakt
    assert np.median(diff / sb.depths(*GRID)) < 0.2   # men ungefär


def test_chart_copy_sometimes_misses_a_seamount():
    sb = Seabed(2000.0, features=(Seamount(10, 10, 300, 1.2),))
    missing = sum(not sb.chart_copy(random.Random(s), 0.5).features for s in range(200))
    assert 20 < missing < 80


def test_contours_follow_the_levels():
    sb = Seabed(1000.0, gradient=(100.0, 0.0))     # 1000 m i väster, 3000 m i öster
    segs = contours(sb, 0, 0, 20, 20, levels=(2000,))[2000]
    xs = [p[0] for seg in segs for p in seg]
    assert all(abs(x - 10) < 0.05 for x in xs)


def test_knowledge_has_the_old_chart_not_the_truth():
    g = _game()
    assert g.knowledge.bathymetry is not None
    assert g.knowledge.bathymetry is not g.world.env.seabed


@pytest.mark.slow
def test_echo_sounder_reads_the_true_bottom_where_we_are():
    g = _game()
    g.command("kurs 270")
    g.command("fart 8")
    depths = []
    for t in range(3600):
        if t % 300 == 5:
            g.command("ekolod")
        g.tick()
    depths = [b.depth for b in g.profile().bottom]
    assert len(depths) >= 10
    assert max(depths) - min(depths) > 200          # botten varierar längs vägen
    s = g.world.own.state
    assert abs(depths[-1] - g.world.env.bottom_at(s.x, s.y)) < 100


def test_chart_shows_contours_and_soundings():
    g = _game()
    g.command("ekolod")
    for _ in range(5):
        g.tick()
    view = g.chart()
    assert any(isinstance(i, Track) and i.style == "contour" for i in view.drawables)
    assert any(isinstance(i, Mark) and i.style == "sounding" for i in view.drawables)
    assert g.profile().chart_bottom


# --- steg 2: grundstötning och varning ------------------------------------------------
def _toward_bank(seed=4, speed=10.0, depth=250.0, offset=3.0):
    """Ubåten i djupt vatten tre sjömil från bankens kant, på väg in över den."""
    from sim.events import ReportDelivered
    from sim.seabed import Bank
    from sim.stations import NavigationStation
    g = _game(seed=seed)
    bank = next(f for f in g.world.env.seabed.features if isinstance(f, Bank))
    west = bank.bearing == 90.0
    edge_x = bank.edge if west else -bank.edge
    s = g.world.own.state
    s.x, s.y = (edge_x + offset if west else edge_x - offset), 10.0
    s.course = s.ordered_course = 270.0 if west else 90.0
    s.speed = s.ordered_speed = speed
    s.depth = s.ordered_depth = depth
    g.world.env.current_kn = 0.0
    nav = g.station(NavigationStation)
    nav.est_x, nav.est_y = s.x, s.y
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


@pytest.mark.slow
def test_running_onto_the_bank_damages_the_hull():
    g, reports = _toward_bank()
    for _ in range(3600):
        g.tick()
        if g.world.own.sys.bottom_contact:
            break
    own = g.world.own
    assert own.sys.bottom_contact and own.sys.hull < 1.0
    assert own.state.speed == 0.0
    s = own.state
    assert s.depth < g.world.env.bottom_at(s.x, s.y)
    for _ in range(20):
        g.tick()
    assert any(r.type == "bottom.collision" and "på grund" in r.text for r in reports)


@pytest.mark.slow
def test_slow_touch_does_no_damage():
    g, reports = _toward_bank(speed=1.5, offset=0.0)
    for _ in range(6000):
        g.tick()
        if g.world.own.sys.bottom_contact:
            break
    assert g.world.own.sys.bottom_contact and g.world.own.sys.hull == 1.0
    for _ in range(20):
        g.tick()
    assert any(r.type == "bottom.touch" for r in reports)


@pytest.mark.slow
def test_navigator_warns_and_yes_keeps_us_off_the_bank():
    for seed in (1, 4, 7):
        g, reports = _toward_bank(seed=seed)
        from sim.events import ReportDelivered
        g.bus.subscribe(ReportDelivered, lambda e: e.report.kind == "suggest"
                        and e.report.type == "nav.suggest.shoal" and g.command("ja"))
        for _ in range(3600):
            g.tick()
        assert any(r.type == "nav.suggest.shoal" for r in reports)
        assert g.world.own.sys.hull == 1.0, seed
        assert not any(r.type.startswith("bottom.") for r in reports), seed


@pytest.mark.slow
def test_sonar_never_suggests_a_depth_below_the_known_bottom():
    from sim.stations import NavigationStation, SonarRoom
    g, _ = _toward_bank(depth=40.0, speed=8.0)
    s = g.world.own.state
    nav = g.station(NavigationStation)
    for _ in range(2700):                      # in över banken
        g.tick()
    lim = nav.depth_limit()
    assert lim is not None and lim < 200
    sonar = g.station(SonarRoom)
    d = sonar._below_layer(g.world.env.layer_depth)
    assert d is None or d <= lim
    assert s.depth < g.world.env.bottom_at(s.x, s.y)


# --- steg 3: ligga på botten ------------------------------------------------------------
def _on_bank(seed=4):
    """Ubåten över bankens flata del på 100 m, stilla vatten."""
    g, reports = _toward_bank(seed=seed, depth=100.0, speed=8.0)
    for _ in range(3400):
        g.tick()
    return g, reports


def _settle(g, ticks=900):
    g.command("botten")
    for _ in range(ticks):
        g.tick()


@pytest.mark.slow
def test_settle_on_soft_bottom_is_quiet_and_still():
    from sim.seabed import RESTING_CLUTTER_DB, bottom_clutter
    g, reports = _on_bank()
    own = g.world.own
    before = own.radiated_level(g.world.env)
    assert bottom_clutter(g.world, own) == 0.0
    _settle(g)
    s = own.state
    assert own.sys.on_bottom and own.sys.hull == 1.0
    assert abs(s.depth - g.world.env.bottom_at(s.x, s.y)) < 15
    assert own.radiated_level(g.world.env) < before - 6
    assert bottom_clutter(g.world, own) == RESTING_CLUTTER_DB
    assert g.status().on_bottom
    g.world.env.current_kn = 0.5                  # strömmen flyttar oss inte
    x, y = s.x, s.y
    for _ in range(300):
        g.tick()
    assert (s.x, s.y) == (x, y)
    assert any(r.type == "bottom.settled" and "Mjuk botten" in r.text for r in reports)
    assert not any(r.type == "bottom.collision" for r in reports)


@pytest.mark.slow
def test_depth_order_lifts_us_off_the_bottom():
    g, reports = _on_bank()
    _settle(g)
    g.command("djup 100")
    for _ in range(300):
        g.tick()
    own = g.world.own
    assert not own.sys.on_bottom and not own.sys.settle
    assert own.state.depth < 150
    assert any(r.type == "nav.settle.lift" for r in reports)


def test_settling_is_refused_over_deep_water():
    g = _game()
    _, reports = g, []
    from sim.events import ReportDelivered
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    _settle(g, ticks=20)
    assert not g.world.own.sys.settle
    assert any(r.type == "nav.settle.refused" and "provdjup" in r.text for r in reports)


def test_rock_bottom_scrapes_the_hull():
    g = _game()
    s = g.world.own.state
    rock = Seabed(1500.0, features=(Seamount(s.x, s.y, 150.0, 4.0),))
    g.world.env.seabed = rock
    g.knowledge.bathymetry = rock
    assert rock.bottom_type(s.x, s.y) == "klippa"
    g.command("fart 1")
    for _ in range(400):
        g.tick()
    _settle(g, ticks=900)
    assert g.world.own.sys.on_bottom
    assert g.world.own.sys.hull < 1.0


@pytest.mark.slow
def test_navigator_suggests_the_bottom_when_hunted_over_the_bank():
    from sim.events import ContactDetected
    g, reports = _on_bank()
    g.bus.publish(ContactDetected(g.now, "S-9", 90.0, "ytfartyg"))
    for _ in range(60):
        g.tick()
    sugg = [r for r in reports if r.type == "nav.suggest.settle"]
    assert sugg and sugg[-1].data["order"] == "botten"


def test_bottom_types():
    sb = kuba_seabed(random.Random(4), (10.0, 3.0))
    kinds = {sb.bottom_type(x, y) for x in range(0, 21, 2) for y in range(0, 21, 2)}
    assert {"lera", "sand", "klippa"} <= kinds


# --- steg 4: fix mot botten -------------------------------------------------------------
from sim.seabed import Bank, match_soundings  # noqa: E402


def _series(sb, x0, y0, course, n=9, step=0.05):
    b = math.radians(course)
    pts = [(x0 + i * step * math.sin(b), y0 + i * step * math.cos(b)) for i in range(n)]
    return pts, [sb.depth_at(x, y) for x, y in pts]


def test_crossing_a_seamount_on_a_perfect_chart_finds_the_offset():
    hits = 0
    for seed in range(10):
        rng = random.Random(seed)
        sb = Seabed(2000.0, features=(Seamount(10, 10, 300, 1.2),))
        pts, depths = _series(sb, 9.0, 9.4 + rng.uniform(0, 0.4), 70)
        ex, ey = rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6)
        m = match_soundings(sb, [(x + ex, y + ey) for x, y in pts], depths, 0.8)
        assert m.consistent
        if math.hypot(m.dx + ex, m.dy + ey) < 0.25:
            hits += 1
    assert hits >= 7


def test_a_straight_slope_gives_a_line_of_position_across_it():
    sb = Seabed(2000.0, features=(Bank(90.0, 5.0, 2.5, 150.0),))     # kant i nord–sydlig led
    pts, depths = _series(sb, 6.0, 10.0, 270)
    m = match_soundings(sb, [(x + 0.4, y - 0.4) for x, y in pts], depths, 0.8)
    assert m.line_of_position
    assert abs(((m.minor_bearing + 90) % 180) - 90) > 70          # bestämt i öst–västlig led
    assert abs(m.dx + 0.4) < 0.2                                  # rätt tvärs sluttningen


def test_flat_bottom_says_nothing():
    sb = Seabed(3000.0)
    pts, depths = _series(sb, 10.0, 10.0, 0)
    m = match_soundings(sb, pts, depths, 0.8)
    assert m.sigma > 0.8 * 0.8


def test_a_feature_missing_from_the_chart_is_detected():
    truth = Seabed(2000.0, features=(Seamount(10, 10, 300, 1.2),))
    chart = Seabed(2000.0)
    pts, depths = _series(truth, 9.0, 9.8, 70)
    assert not match_soundings(chart, pts, depths, 1.0).consistent


def test_bottom_fix_order_sounds_nine_times_and_reports():
    g, reports = _toward_bank(speed=6.0, depth=100.0, offset=1.5)
    from sim.stations import NavigationStation
    nav = g.station(NavigationStation)
    nav.est_x += 0.6
    nav.last_fix_t = -7200
    n0 = len(nav.bottom_soundings)
    pings = []
    for _ in range(5):
        g.tick()
    g.command("bottenfix")
    for _ in range(200):
        g.tick()
        pings += [t for t in g.world.transients if t.kind == "echosounder"]
    assert len(nav.bottom_soundings) - n0 == 9
    assert len(pings) == 9
    done = [r for r in reports if r.type.startswith("nav.bfix.")]
    assert done and done[-1].type in ("nav.bfix.done", "nav.bfix.line", "nav.bfix.flat",
                                      "nav.bfix.chart", "nav.bfix.mismatch")
    assert done[-1].quality is not None


def test_bottom_fix_is_refused_when_slow():
    g, reports = _toward_bank(speed=0.0)
    g.command("bottenfix")
    for _ in range(5):
        g.tick()
    assert any(r.type == "nav.bfix.refused" for r in reports)


def test_bottom_fix_honest_over_seeds():
    """Över banken: fixen påstår aldrig mer än den levererar i genomsnitt."""
    from sim.stations import NavigationStation
    claimed, actual = [], []
    for seed in range(6):
        g, reports = _toward_bank(seed=seed, speed=6.0, depth=100.0, offset=1.5)
        nav = g.station(NavigationStation)
        a = random.Random(seed).uniform(0, 2 * math.pi)
        nav.est_x += 0.8 * math.sin(a)
        nav.est_y += 0.8 * math.cos(a)
        nav.last_fix_t = -7200
        g.command("bottenfix")
        for _ in range(200):
            g.tick()
        s = g.world.own.state
        claimed.append(nav.uncertainty())
        actual.append(math.dist((nav.est_x, nav.est_y), (s.x, s.y)))
    rms = math.sqrt(sum(e * e for e in actual) / len(actual))
    assert rms < 1.5 * sum(claimed) / len(claimed)


@pytest.mark.slow
def test_turning_into_a_steep_shore_does_not_lift_us_to_the_surface():
    """sundet-ut, frö 1: ja-boten girar med fören mot den branta stranden på 20 m. Förut
    flyttades båten tillbaka med den nya kursen, fören stod kvar i land och djupet blev 0
    på en sekund (ytläge utan rapport, uppdraget slut som 'forced')."""
    g = _game("sundet-ut", 1)
    depths = []
    for _ in range(20 * 60):
        g.tick()
        s = g.active_suggestion()
        if s and g.now - s[2] == 15:
            g.command("ja")
        depths.append(g.world.own.state.depth)
        if g.over:
            break
    assert (g.world.outcome or {}).get("outcome") != "forced"
    assert all(b - a < 3.0 for a, b in zip(depths[1:], depths)), "ett hopp uppåt på en sekund"


def test_navigator_does_not_take_charted_land_for_the_bottom():
    """sundet-ut, frö 1: kortet visar land (-10 m) där besticket säger att vi går på 20 m. Det är
    kortet eller besticket som har fel, inte en botten att lägga sig på."""
    from sim.stations import NavigationStation
    g = _game("sundet-ut", 1)
    nav = g.station(NavigationStation)
    nav.bottom_soundings.clear()
    assert nav.chart_depth_at(nav.est_x, nav.est_y) < 0 < g.world.own.state.depth
    assert nav.bottom_here() is None
    assert nav._settle_proposal() is None
