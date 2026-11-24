"""Civil trafik: handelsfartyg längs leder, maskering, klassning och regler för eld."""
import dataclasses
import pytest
import random
import statistics

from sim import acoustics
from sim.enemy import DestroyerAI
from sim.events import BearingObserved, ContactDetected, ReportDelivered
from sim.game import Game
from sim.geo import bearing_to, distance
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.ship import ShipState
from sim.stations import TorpedoRoom
from sim.tma import BearingObs
from sim.traffic import MerchantAI
from sim.weapons import _sink

SEEDS = range(1, 7)


def _game(seed=3, key="kuba"):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()
        if g.over:
            return


def _merchants(g):
    return [v for v in g.world.contacts if v.kind == "merchant"]


def test_kuba_has_traffic_and_arctic_does_not():
    for seed in SEEDS:
        g, _ = _game(seed)
        ms = _merchants(g)
        assert len(ms) == 3
        o = g.world.own.state
        assert all(distance(o.x, o.y, m.state.x, m.state.y) >= 3.0 for m in ms)
        assert all(m.side == "neutral" and m not in g.world.enemy_ships for m in ms)
    assert not _merchants(_game(2, "arktis")[0])


@pytest.mark.slow
def test_new_ships_arrive_over_the_patrol():
    counts = []
    for seed in SEEDS:
        g, _ = _game(seed)
        g.world.ais = [a for a in g.world.ais if not isinstance(a, DestroyerAI)]
        _run(g, 3 * 3600)
        counts.append(len(_merchants(g)))
    # 1,8 fartyg i timmen över tre leder
    assert 5 <= statistics.mean(counts) <= 12


def test_soviet_freighter_stops_for_the_destroyer_and_turns_home():
    g, _ = _game()
    dd = g.world.contacts[0]
    ai = next(a for a in g.world.ais if isinstance(a, MerchantAI))
    ai.soviet = True
    m = ai.vessel
    dd.state.x, dd.state.y = m.state.x + 2.0, m.state.y
    g.world.ais = [a for a in g.world.ais if not isinstance(a, DestroyerAI)]
    dd.state.order_speed(0)
    dd.state.speed = 0
    _run(g, 5)
    assert ai.state == "stopped" and m.state.ordered_speed == 0
    _run(g, 36 * 60)
    assert ai.state == "homeward" and m.state.speed > 5
    hx, hy = ai.home
    assert abs(((m.state.course - bearing_to(m.state.x, m.state.y, hx, hy)) + 180) % 360 - 180) < 30


def _place(v, x, y, course=0.0, speed=0.0):
    v.state.x, v.state.y, v.state.course, v.state.speed = x, y, course, speed
    v.state.order_course(course)
    v.state.order_speed(speed)


def test_merchant_on_the_same_bearing_masks_our_sonar():
    g, _ = _game()
    w = g.world
    o = w.own.state
    o.depth = o.ordered_depth = 40                     # över skiktet, som handelsfartyget
    dd = w.contacts[0]
    m = _merchants(g)[0]
    for other in _merchants(g)[1:]:
        _place(other, -40, -40)
    _place(dd, o.x, o.y + 6.0, speed=15)
    _place(m, o.x + 3.0, o.y - 3.0, speed=10)        # åt annat håll: ingen maskering
    clear = w.raw_signal_excess(dd)
    _place(m, o.x + 0.05, o.y + 4.0, speed=10)       # i samma bäring som jagaren
    masked = w.raw_signal_excess(dd)
    assert clear - masked > 6


def test_hiding_under_a_merchant_hides_us_from_the_destroyer():
    """Jagarens sonar: aktivt eko och passiv lyssning, med och utan ett
    handelsfartyg ovanför oss. Statistiskt över många pingar."""
    def detections(with_merchant: bool) -> int:
        g, _ = _game(4)
        w = g.world
        o = w.own.state
        o.depth = o.ordered_depth = 50                 # över skiktet: jagaren hör bra
        dd = w.contacts[0]
        ai = next(a for a in w.ais if isinstance(a, DestroyerAI))
        w.ais = [ai]
        ms = _merchants(g)
        for other in ms[1:]:
            _place(other, -40, -40)
        _place(ms[0], *((o.x + 0.1, o.y) if with_merchant else (-40, -40)), speed=10)
        _place(dd, o.x, o.y + 2.5, course=180, speed=12)
        hits = 0
        for _ in range(200):
            dd.state.x, dd.state.y = o.x, o.y + 2.5
            before = ai.last_contact_t
            ai._ping(w, ai._noise(w))
            hits += ai.last_contact_t != before
            w.time += 1
        return hits
    assert detections(False) > 150
    assert detections(True) < 60


def test_merchant_classified_as_civil_is_not_a_threat():
    g, _ = _game()
    k = g.knowledge
    g.bus.publish(ContactDetected(0, "S-7", 10.0, "ytfartyg, enskruv, troligt handelsfartyg",
                                  Quality.GOD))
    tr = k.track("S-7")
    assert tr.civil and tr.benign and not tr.threat and not tr.warship


def _known(g, desig, classification, quality, target):
    ex, ey = g.own_position_estimate()
    b = bearing_to(ex, ey, target.state.x, target.state.y)
    g.bus.publish(ContactDetected(g.now, desig, b, classification, quality))
    r = distance(ex, ey, target.state.x, target.state.y)
    g.bus.publish(BearingObserved(g.now, BearingObs(g.now, b, 0.5, ex, ey, 0, designation=desig,
                                                    range_nm=r, range_sigma=0.02)))
    for k in range(1, 8):
        g.bus.publish(BearingObserved(g.now, BearingObs(g.now + k, b, 0.5, ex, ey, 0,
                                                        designation=desig)))


def test_torpedo_room_asks_before_firing_at_an_unidentified_or_civil_contact():
    g, reports = _game()
    w = g.world
    w.ais.clear()
    o = w.own.state
    o.order_speed(3)
    m = _merchants(g)[0]
    _place(m, o.x, o.y + 2.0)
    _known(g, "S-8", "handelsfartyg", Quality.GOD, m)
    room = g.station(TorpedoRoom)
    loaded = room.tubes[0].load
    g.command("eld tub 1 mot S-8")
    _run(g, 5)
    assert room.tubes[0].load == loaded
    ask = [r for r in reports if r.type == "torp.confirm"]
    assert ask and "handelsfartyg" in ask[0].text and "Svara ja" in ask[0].text
    g.command("eld tub 1 mot S-8")                   # kaptenen står fast
    _run(g, 5)
    assert room.tubes[0].load is None


def test_sinking_a_merchant_ends_the_patrol():
    g, _ = _game()
    _sink(g.world, _merchants(g)[0])
    _run(g, 120)
    assert g.over and g.world.outcome["outcome"] == "neutral_sunk"


def test_merchant_is_loud_enough_to_hear_at_distance():
    """Ett handelsfartyg i 12 kn hörs ungefär som jagaren i patrullfart."""
    assert abs(acoustics.source_level("merchant", 12) - acoustics.source_level("destroyer", 15)) < 6


def _target_and_merchant_behind(g):
    """Jagaren 2 nm rakt fram (mål) och ett känt handelsfartyg 4 nm bortom den i banan."""
    w = g.world
    o = w.own.state
    o.depth = o.ordered_depth = 20
    o.speed = 3.0
    dd, m = w.contacts[0], _merchants(g)[0]
    ex, ey = g.own_position_estimate()
    _place(dd, ex, ey + 2.0)
    _place(m, ex + 0.1, ey + 4.0)
    _known(g, "S-7", "jagare", Quality.GOD, dd)
    _known(g, "S-8", "handelsfartyg", Quality.GOD, m)
    for tr in g.knowledge.tracks.values():
        g.knowledge.resolve(tr.designation, g.now, (ex, ey))
    return g.station(TorpedoRoom)


def test_torpedo_room_warns_about_a_merchant_in_the_torpedo_lane():
    g, reports = _game()
    room = _target_and_merchant_behind(g)
    loaded = room.tubes[0].load
    g.command("eld tub 1 mot S-7")
    _run(g, 5)
    assert room.tubes[0].load == loaded                 # inget skott ännu
    warn = [r for r in reports if r.type == "torp.neutral"]
    assert warn and "S-8" in warn[0].text and "Svara ja" in warn[0].text
    g.command("eld tub 1 mot S-7")                     # kaptenen står fast: skott, ingen ny fråga
    _run(g, 5)
    assert room.tubes[0].load is None
    assert sum(r.type == "torp.neutral" for r in reports) == 1


def test_the_firing_solution_mentions_a_merchant_in_the_lane():
    g, reports = _game()
    _target_and_merchant_behind(g)
    g.command("skjutlösning S-7")
    _run(g, 5)
    warn = [r for r in reports if r.type == "torp.neutral"]
    assert warn and "S-8" in warn[0].text and "Svara ja" not in warn[0].text


def test_no_warning_when_the_merchant_is_well_off_the_lane():
    g, reports = _game()
    room = _target_and_merchant_behind(g)
    m = _merchants(g)[0]
    ex, ey = g.own_position_estimate()
    _place(m, ex + 4.0, ey - 1.0)
    g.knowledge.tracks.pop("S-8")
    _known(g, "S-8", "handelsfartyg", Quality.GOD, m)
    g.knowledge.resolve("S-8", g.now, (ex, ey))
    g.command("eld tub 1 mot S-7")
    _run(g, 5)
    assert room.tubes[0].load is None
    assert not any(r.type == "torp.neutral" for r in reports)


def test_a_homing_torpedo_warns_about_a_merchant_far_beyond_the_target():
    """Målsökaren söker vidare om den missar: ett handelsfartyg 2 nm bortom målet i banan."""
    g, reports = _game()
    room = _target_and_merchant_behind(g)
    for t in room.tubes:
        t.load = None
    room.tubes[0].load = "SET-53"
    g.command("eld tub 1 mot S-7")
    _run(g, 5)
    assert room.tubes[0].load == "SET-53"
    warn = [r for r in reports if r.type == "torp.neutral"]
    assert warn and "S-8" in warn[0].text and "längs den målsökande torpedens bana" in warn[0].text


def test_the_lane_warning_also_says_what_the_target_itself_is():
    """Varningen räknas som frågan om målet: ett mål som inte är säkert örlogsfartyg nämns."""
    g, reports = _game()
    _target_and_merchant_behind(g)
    tr = g.knowledge.track("S-7")
    tr.classification, tr.class_quality = "stort fartyg", Quality.OSAKER
    g.command("eld tub 1 mot S-7")
    _run(g, 5)
    warn = [r for r in reports if r.type == "torp.neutral"]
    assert warn and "S-7 själv är inte säkert klassad som örlogsfartyg" in warn[0].text


def test_torpedo_room_warns_about_a_merchant_sonar_lost_a_few_minutes_ago():
    """Ett handelsfartyg sonar tappat nyss är kvar, bara tyst (clyde-in frö 29: fiskebåten tappad 10 min före
    skottet, 35° från banan, och den målsökande torpeden tog den)."""
    g, reports = _game()
    room = _target_and_merchant_behind(g)
    tr = g.knowledge.track("S-8")
    tr.held = False
    tr.observations = [dataclasses.replace(ob, t=ob.t - 600) for ob in tr.observations]   # tappad för 10 min sedan
    loaded = room.tubes[0].load
    g.command("eld tub 1 mot S-7")
    _run(g, 5)
    assert room.tubes[0].load == loaded
    warn = [r for r in reports if r.type == "torp.neutral"]
    assert warn and "S-8" in warn[0].text and "tappad för" in warn[0].text
    tr.observations = [dataclasses.replace(ob, t=ob.t - 900) for ob in tr.observations]   # för länge sedan
    tr.held = False
    room._neutral_warned.clear()
    reports.clear()
    g.command("eld tub 1 mot S-7")
    _run(g, 5)
    assert not any(r.type == "torp.neutral" for r in reports)
