"""Snabb pingtakt ger stridslarm bara när pingarna är starka (jagaren nära); svaga pingar i snabb
takt jagar något långt bort och rapporteras utan larm."""
import random

from sim.events import HuntSigns, ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.sonar import TransientHeard
from sim.stations.sonar_room import PING_LAYER_DB, PING_NEAR_RL, SonarRoom

SEEDS = (1, 2, 3)


def _game(seed):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    for ai in g.world.ais:                        # scenariots egna jagare tiger under provet
        if hasattr(ai, "next_ping"):
            ai.next_ping = 10**9
    reports, hunts = [], []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.bus.subscribe(HuntSigns, lambda e: hunts.append(e))
    g.world.own.state.depth = g.world.own.state.ordered_depth = 30.0   # över skiktet
    return g, g.station(SonarRoom), reports, hunts


def _pings(g, sonar, rls, start=100, gap=9, bearing=45.0):
    t = start
    for rl in rls:
        g.world.time = t
        sonar._on_sound(TransientHeard("ping", bearing, 20.0, None, rl=rl))
        t += gap
    for _ in range(5):
        g.tick()


def _of(reports, kind):
    return [r for r in reports if r.type == kind and r.data.get("bearing") is not None
            and abs(r.data["bearing"] - 45.0) < 10]


def test_fast_weak_pings_far_away_give_no_battle_alarm():
    for seed in SEEDS:
        g, sonar, reports, hunts = _game(seed)
        _pings(g, sonar, [PING_NEAR_RL - 20] * 8)          # ~30 nm: anfallstakt, svaga
        assert not hunts, seed
        assert not _of(reports, "sonar.ping.fast"), seed
        far = _of(reports, "sonar.ping.fast_far")
        assert len(far) == 1 and not far[0].alarm and "långt bort" in far[0].text, seed
        first = _of(reports, "sonar.ping.first")
        assert len(first) == 1 and not first[0].alarm and first[0].data.get("far"), seed
        assert not any(r.type == "off.battle_stations" for r in reports), seed
        assert not any(r.type == "sonar.suggest.depth_change" for r in reports), seed


def test_fast_strong_pings_still_sound_the_alarm():
    for seed in SEEDS:
        g, sonar, reports, hunts = _game(seed)
        _pings(g, sonar, [PING_NEAR_RL + 10] * 6)
        assert hunts, seed
        fast = _of(reports, "sonar.ping.fast")
        assert len(fast) == 1 and fast[0].alarm, seed
        assert not _of(reports, "sonar.ping.fast_far"), seed
        assert _of(reports, "sonar.ping.first")[0].alarm, seed


def test_a_far_hunter_closing_in_raises_the_alarm_once():
    g, sonar, reports, hunts = _game(1)
    rls = [PING_NEAR_RL - 15] * 5 + [PING_NEAR_RL + 5] * 5     # snabb takt hela tiden, kommer närmare
    _pings(g, sonar, rls)
    assert len(_of(reports, "sonar.ping.fast_far")) == 1
    assert len(_of(reports, "sonar.ping.fast")) == 1
    assert hunts and all(h.t >= 100 + 9 * 5 for h in hunts)


def test_below_the_layer_the_operator_allows_for_it():
    g, sonar, reports, hunts = _game(1)
    ld = sonar.layer_depth()
    assert ld is not None
    g.world.own.state.depth = ld + 40
    _pings(g, sonar, [PING_NEAR_RL - PING_LAYER_DB + 2] * 6)  # försvagad av skiktet men nära
    assert hunts and _of(reports, "sonar.ping.fast")


def test_far_judgement_has_quality_from_the_margin():
    g, sonar, reports, _ = _game(1)
    _pings(g, sonar, [PING_NEAR_RL - 3] * 4)                      # nära gränsen: osäker
    _pings(g, sonar, [PING_NEAR_RL - 25] * 4, start=2000, bearing=200.0)  # långt under: god
    firsts = sorted((r for r in reports if r.type == "sonar.ping.first"),
                    key=lambda r: r.data["bearing"])
    firsts = [r for r in firsts if round(r.data["bearing"]) in (45, 200)]
    assert [r.data["sure"] for r in firsts] == [False, True]
    assert "troligen långt bort" in firsts[0].text and "troligen" not in firsts[1].text


def test_a_far_pinger_switching_rate_is_reported_once():
    g, sonar, reports, hunts = _game(1)
    t = 100
    for _ in range(6):                        # snabb, långsam, snabb … i en kvart
        for gap in (9, 9, 9, 25, 25):
            t += gap
            g.world.time = t
            sonar._on_sound(TransientHeard("ping", 45.0, 20.0, None, rl=PING_NEAR_RL - 20))
    for _ in range(5):
        g.tick()
    assert len(_of(reports, "sonar.ping.fast_far")) == 1
    assert not _of(reports, "sonar.ping.slow") and not hunts
