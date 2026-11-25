"""Fiskeflottan (sim/fishing.py): trålen fastnar, sliter loss, fiskaren larmar, lamporna på natten och
jagaren som skuggar spaningstrålaren."""
import random

from sim import fishing as F
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario


def _game(seed=1):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _trawler(g):
    return next(a for a in g.world.ais if isinstance(a, F.Trawler) and a.vessel.kind == "fishing")


def test_kuba_has_trawlers_on_the_bank_and_a_soviet_spy_trawler():
    g, _ = _game()
    kinds = [v.kind for v in g.world.contacts]
    assert kinds.count("fishing") == 3 and kinds.count("spytrawler") == 1
    assert g.world.ais[0].shadow is not None and g.world.ais[0].shadow.kind == "spytrawler"


def test_running_into_the_trawl_snags_us_and_the_fisherman_calls_it_in():
    g, reports = _game()
    t = _trawler(g)
    own = g.world.own
    tx, ty, td = t.trawl(g.world)
    own.state.x, own.state.y = tx, ty
    own.state.depth = own.state.ordered_depth = td + 5
    dd = g.world.ais[0]
    dd.datum = None
    g.tick()
    assert t.snagged_t is not None and own.sys.health["propulsion"] < 1.0
    assert dd.datum is not None and dd.datum.sigma == F.TRAWL_ALARM_SIGMA_NM
    for _ in range(5):
        g.tick()
    assert any(r.type == "trawl.caught" and r.alarm for r in reports)
    own.state.speed = own.state.ordered_speed = 5
    for _ in range(F.TRAWL_BREAK_S + 5):
        g.tick()
    assert t.snagged_t is None and any(r.type == "trawl.free" for r in reports)


def test_deep_under_the_trawl_nothing_happens():
    g, _ = _game()
    t = _trawler(g)
    own = g.world.own
    tx, ty, td = t.trawl(g.world)
    own.state.x, own.state.y = tx, ty
    own.state.depth = own.state.ordered_depth = td + 40
    g.tick()
    assert t.snagged_t is None


def test_fishing_lights_show_at_night_beyond_the_night_visibility():
    class V:
        kind = "fishing"
    assert F.lit_at_night(V(), 5.0, day=False, fog=None)
    assert not F.lit_at_night(V(), 5.0, day=True, fog=None)
    assert not F.lit_at_night(V(), 5.0, day=False, fog=0.4)
    assert not F.lit_at_night(V(), 8.0, day=False, fog=None)


def test_sonar_says_a_fishing_boat_is_trawling():
    from sim.reports import Quality
    from sim.sonar import ClassificationUpdate
    from sim.stations.sonar_room import SonarRoom
    g, reports = _game()
    sonar = g.station(SonarRoom)
    orig = sonar.sensor.update
    sent = []

    def update(world, xy):
        out = orig(world, xy)
        if not sent:
            sent.append(1)
            out = [*out, ClassificationUpdate("S-4", "fiskebåt, diesel, en axel", Quality.GOD)]
        return out
    sonar.sensor.update = update
    for _ in range(40):
        g.tick()
    assert any(r.type == "sonar.trawling" and "S-4 trålar" in r.text for r in reports)


def test_the_destroyer_shadows_the_spy_trawler_for_a_while():
    from sim.enemy import SHADOW_ON_S, SHADOW_PERIOD_S
    g, _ = _game()
    w = g.world
    dd = w.ais[0]
    spy = dd.shadow
    dd.datum = None
    dd.state = "patrol"
    w.time = SHADOW_PERIOD_S - SHADOW_ON_S + 10
    dd.step(w)
    from sim.geo import bearing_to
    s = dd.vessel.state
    assert abs((s.ordered_course - bearing_to(s.x, s.y, spy.state.x, spy.state.y) + 180) % 360 - 180) < 1
