"""Korta varianter: vakten före kaptenen (Scenario.warmup) och överlämnandet."""
import random

from sim.events import Handover, OrderIssued, ReportDelivered
from sim.game import Game
from sim.scenario import SCENARIOS, Warmup, build_scenario, default_scenario


def _game(seconds=120, pilot=None, **kw):
    calls = []

    def rec(game, t):
        calls.append(t)
        if pilot:
            return pilot(game, t)

    sc = default_scenario(random.Random(3))
    sc.warmup = Warmup(seconds, rec)
    return Game(sc, seed=3, **kw), calls


def test_warmup_runs_before_the_captain_takes_command():
    g, calls = _game(120)
    assert calls == list(range(120))
    assert g.now == 120
    assert not g.warmup_pending
    assert g.active_suggestion() is None
    assert g.logbook.start_t == 120
    assert g.last_command_t == 120          # vakthavande tar inte initiativ direkt


def test_warmup_can_be_deferred_and_then_briefs_the_captain():
    g, calls = _game(120, warm_up=False)
    assert g.now == 0 and g.warmup_pending and not calls
    handovers, reports = [], []
    g.bus.subscribe(Handover, handovers.append)
    g.warm_up()
    g.warm_up()                              # en gång räcker
    assert calls == list(range(120)) and len(handovers) == 1
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    for _ in range(30):
        g.tick()
    brief = [r for r in reports if r.type == "off.briefing"]
    assert len(brief) == 1
    assert "Ni har befälet" in brief[0].text and "2 minuter" in brief[0].text
    assert brief[0].speech and "командование" in brief[0].speech


def test_pilot_orders_are_the_watch_not_the_captain():
    g, _ = _game(60, pilot=lambda game, t: t == 0 and game.command("fart 3"))
    assert g.world.own.state.ordered_speed == 3
    assert g.logbook.orders == 0             # kaptenens loggbok börjar efter vakten
    seen = []
    g.bus.subscribe(OrderIssued, seen.append)
    g.command("fart 5")
    assert g.logbook.orders == 1


def test_scenarios_without_warmup_start_at_zero():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    assert g.now == 0 and not g.warmup_pending


def test_short_variants_are_marked_with_play_time():
    assert SCENARIOS["konvoj-kort"].minutes
    assert SCENARIOS["konvoj"].minutes is None


def test_convoy_short_hands_over_with_the_convoy_plotted_and_unseen():
    """Över flera frön: plottet har konvojen, den är några sjömil bort och ingen eskort
    har oss när kaptenen tar befälet."""
    ok = 0
    seeds = range(4)
    for seed in seeds:
        g = Game(build_scenario("konvoj-kort", random.Random(seed)), seed=seed)
        w = g.world
        convoy = g.knowledge.convoy
        nearest = min(w.true_range(v) for v in w.contacts if v.id.startswith("K"))
        hunted = any(w._hunting_us(ai) for ai in w.ais)
        assert not g.over
        if convoy is not None and len(convoy.members) >= 2 and 4.0 < nearest < 10.0 \
                and not hunted:
            ok += 1
    assert ok >= len(seeds) - 1


def test_pilot_can_hand_over_early():
    g, calls = _game(300, pilot=lambda game, t: t >= 40)
    assert g.now == 40 and calls == list(range(41))
    assert g.logbook.start_t == 40


def test_convoy_counter_hands_over_with_the_salvo_running_and_an_escort_turning():
    """Över flera frön: vakten har skjutit, torpederna går, en eskort har oss och
    skrovet är helt när kaptenen tar befälet; tidsgränsen räknas från överlämnandet."""
    from sim.convoy import EscortAI
    from sim.scenario import COUNTER_LIMIT_S
    from sim.weapons import Torpedo
    for seed in range(3):
        g = Game(build_scenario("konvoj-mot", random.Random(seed)), seed=seed)
        w = g.world
        assert not g.over and w.mission.get("hostile_act")
        assert any(isinstance(v, Torpedo) and not v.done for v in w.contacts)
        assert any(w._hunting_us(a) for a in w.ais if isinstance(a, EscortAI))
        assert w.own.sys.hull == 1.0
        assert w.patrol_end == g.now + COUNTER_LIMIT_S
        assert g.now < 6 * 60


def test_convoy_counter_salvo_hits_within_minutes_over_seeds():
    hits = 0
    for seed in range(8):
        g = Game(build_scenario("konvoj-mot", random.Random(seed)), seed=seed)
        t0 = g.now
        while g.now - t0 < 180 and not g.over:
            g.tick()
        hits += any(v.sunk for v in g.world.contacts if v.id.startswith("K"))
    assert hits >= 5
