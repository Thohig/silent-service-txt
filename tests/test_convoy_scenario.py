"""Scenariot Konvojen: uppställning, spelslut, salva och okända pingare."""
import pytest
import random

from sim.events import BearingObserved, ReportDelivered
from sim.game import Game
from sim.geo import angle_diff, bearing_to, distance
from sim.scenario import build_scenario
from sim.stations import TorpedoRoom
from sim.stations.sonar_room import SonarRoom
from sim.tma import BearingObs
from sim.weapons import Torpedo, _sink

SEEDS = range(1, 6)


def _game(seed=1):
    g = Game(build_scenario("konvoj", random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _convoy(g):
    return next(sp for sp in g.world.spawners if hasattr(sp, "escorts"))


def test_convoy_comes_from_the_north_and_passes_within_reach():
    for seed in SEEDS:
        g, _ = _game(seed)
        c = _convoy(g)
        o = g.world.own.state
        assert len(c.vessels) == 3 and len(c.escorts) == 2
        assert all(e.roe == "lethal" for e in c.escorts)
        assert 15.0 < distance(o.x, o.y, c.x, c.y) < 22.0
        # avståndet till konvojens väg (baskursen genom ledpunkten)
        b = bearing_to(c.x, c.y, o.x, o.y)
        import math
        across = distance(c.x, c.y, o.x, o.y) * abs(math.sin(math.radians(angle_diff(b, c.base_course))))
        assert 1.4 < across < 5.1
        assert "KONVOJ" in g.secret_order and "SICKSACKAR" in g.secret_order


def test_sinking_a_convoy_ship_and_getting_clear_wins():
    g, _ = _game(2)
    c = _convoy(g)
    for e in c.escorts:                       # eskorten långt borta och utan datum
        e.vessel.state.x += 40.0
        e.datum = None
    _sink(g.world, c.vessels[0])
    for _ in range(700):
        g.tick()
        if g.over:
            break
    assert g.world.outcome["outcome"] == "convoy_attacked"


@pytest.mark.slow
def test_passive_submarine_lets_the_convoy_pass():
    g, _ = _game(4)
    for _ in range(3 * 3600):
        g.tick()
        if g.over:
            break
    assert g.world.outcome is not None
    assert g.world.outcome["outcome"] in ("convoy_missed", "lost", "forced")


def test_salvo_fans_out_around_the_solution(perfect_torpedoes):
    g, reports = _game(3)
    w = g.world
    o = w.own.state
    o.depth = o.ordered_depth = 15.0
    o.speed = o.ordered_speed = 3.0
    # en kontakt två sjömil norrut som går öster i 10 knop, sedd i periskopet
    g.knowledge.on_detection("S-1", 0)
    x0, y0 = o.x, o.y + 2.0
    for t in range(0, 300, 10):
        x = x0 + 10.0 * t / 3600.0
        ex, ey = g.own_position_estimate()
        g.bus.publish(BearingObserved(t, BearingObs(
            t, bearing_to(ex, ey, x, y0), 0.5, ex, ey, o.course, designation="S-1",
            range_nm=distance(ex, ey, x, y0), range_sigma=0.1, source="periskop")))
    g.world.time = 300
    g.command("salva S-1")
    g.command("salva S-1")                    # inte säkert örlogsfartyg: torpedrummet frågar
    torps = [v for v in w.contacts if isinstance(v, Torpedo)]
    assert len(torps) == 3
    cs = sorted(t.state.course for t in torps)
    assert abs(angle_diff(cs[1], cs[0]) - angle_diff(cs[2], cs[1])) < 0.01
    assert 1.0 <= angle_diff(cs[1], cs[0]) <= 10.0
    for _ in range(5):
        g.tick()
    assert any(r.type == "torp.salvo" for r in reports)
    assert all(t.load is None for t in g.station(TorpedoRoom).tubes[:3])


def test_a_close_pinger_sweeping_fast_in_bearing_is_one_pinger():
    """Sundet frö 51: ett fartyg som passerar nära drar 0,8°/s; sonar sa 'Någon söker' och 'pingtakten
    har ökat' fem gånger på två minuter (grinden räknade inte med pingarens egen drift)."""
    from sim.sonar import TransientHeard
    for seed in SEEDS:
        g, reports = _game(seed)
        for ai in g.world.ais:
            if hasattr(ai, "next_ping"):
                ai.next_ping = 10**9
        sonar = g.station(SonarRoom)
        rng = random.Random(seed)
        for k in range(20):                               # var 8:e s, 0,8°/s, 130 → 2
            g.world.time = 100 + 8 * k
            sonar._on_sound(TransientHeard("ping", 130.0 - 6.4 * k + rng.gauss(0, 1.0), 2.0, None))
        for _ in range(5):
            g.tick()
        firsts = [r for r in reports if r.type == "sonar.ping.first" and r.data["bearing"] <= 140]
        assert len(firsts) == 1, (seed, [r.data["bearing"] for r in firsts])


def test_two_unknown_pingers_on_different_bearings_are_not_a_fast_pinger():
    g, reports = _game(1)
    for ai in g.world.ais:                        # scenariots egna eskorter tiger under provet
        if hasattr(ai, "next_ping"):
            ai.next_ping = 10**9
    sonar = g.station(SonarRoom)
    from sim.sonar import TransientHeard
    for k in range(6):
        g.world.time = 100 + 10 * k
        b = 20.0 if k % 2 == 0 else 40.0          # två jagare, 20 s var, 10 s isär
        sonar._on_sound(TransientHeard("ping", b, 30.0, None))
    for _ in range(5):
        g.tick()
    assert not any(r.type == "sonar.ping.fast" for r in reports)


def test_one_unknown_pinger_with_noisy_bearings_is_one_pinger():
    from sim.sonar import TransientHeard
    for seed in SEEDS:
        g, reports = _game(seed)
        sonar = g.station(SonarRoom)
        rng = random.Random(seed)
        for k in range(30):                               # en jagare, 20 s mellan pingarna, 10 min
            g.world.time = 100 + 20 * k
            b = 90.0 + 1.0 * k + rng.gauss(0, 2.5)        # drar 1°/ping, svag signal
            sonar._on_sound(TransientHeard("ping", b, 2.0, None))
        for _ in range(5):
            g.tick()
        firsts = [r for r in reports if r.type == "sonar.ping.first"
                  and 80 <= r.data["bearing"] <= 130]      # scenariots egna eskorter räknas inte
        assert len(firsts) == 1, seed


def test_a_two_torpedo_salvo_still_warns_about_the_zigzag():
    from types import SimpleNamespace
    from sim.stations.torpedo_room import FireSalvo
    g, _reports = _game(1)
    room = g.station(TorpedoRoom)
    sol = SimpleNamespace(range_sigma=0.1, speed_sigma=1.0, speed=10.0, course_sigma=5.0)
    room._solution_for = lambda d: (None, sol)
    room._aim = lambda s, load: (90.0, 300.0, 2.0)
    fired, warned = [], []
    room._fire = lambda o: fired.append(o) or True
    room._refusal = lambda o: None
    room._leg_warning = lambda d, run_s, kind: warned.append((d, run_s))
    room._salvo(FireSalvo("S-1", (1, 2)))
    assert len(fired) == 2 and all(o.offset != 0.0 for o in fired)
    assert warned == [("S-1", 300.0)]


def test_known_pinger_lost_as_contact_is_not_a_new_pinger():
    """Sonar tappar S-4 som kontakt men hör fortfarande pingarna i samma bäring: ingen ny 'Någon söker'."""
    from sim.sonar import TransientHeard
    g, reports = _game(1)
    for ai in g.world.ais:
        if hasattr(ai, "next_ping"):
            ai.next_ping = 10**9
    sonar = g.station(SonarRoom)
    for k in range(6):
        g.world.time = 100 + 20 * k
        sonar._on_sound(TransientHeard("ping", 112.0 + 0.5 * k, 30.0, "S-4"))
    g.world.time = 240
    sonar._on_sound(TransientHeard("ping", 114.0, 30.0, None))      # kontakten tappad
    g.world.time = 260
    sonar._on_sound(TransientHeard("ping", 200.0, 30.0, None))      # en annan bäring: ny pingare
    for _ in range(5):
        g.tick()
    firsts = [r for r in reports if r.type == "sonar.ping.first"]
    assert [round(r.data["bearing"]) for r in firsts] == [112, 200]
