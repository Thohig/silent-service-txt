"""Stationer, förslag som kaptenen kan godkänna och spelslut."""
import pytest
import random

from sim.events import BearingObserved, ContactDetected, GameEnded, ReportDelivered
from sim.game import Game
from sim.geo import distance
from sim.reports import Quality
from sim.scenario import default_scenario
from sim.stations import NavigationStation, TorpedoRoom
from sim.tma import BearingObs
from sim.weapons import Torpedo


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()


def _types(reports):
    return [r.type for r in reports]


def _park_destroyer(g, x=10.0, y=8.0, speed=0.0):
    dd = g.world.contacts[0]
    dd.state.x, dd.state.y = x, y
    dd.state.speed = speed
    dd.state.order_speed(speed)
    g.world.ais.clear()               # passiv jagare i dessa tester
    return dd


def test_crew_suggestion_can_be_accepted_with_ja():
    g, reports = _game()
    g.command("djup 30")
    g.command("fart 20")
    _run(g, 200)
    sug = [r for r in reports if r.type == "eng.suggest.cavitation"]
    assert sug, "maskin borde föreslå lägre fart när vi kaviterar"
    assert "[ja: fart" in sug[0].text
    g.command("ja")
    _run(g, 10)
    assert g.world.own.state.ordered_speed < 20
    assert "order.executing" in _types(reports)


def test_ja_without_suggestion_and_nej():
    g, reports = _game()
    g.command("ja")
    g.command("nej")
    _run(g, 10)
    assert "order.no_suggestion" in _types(reports)
    assert "order.declined" in _types(reports)


def test_periscope_needs_periscope_depth_and_gives_range():
    g, reports = _game()
    dd = _park_destroyer(g, 10.0, 5.0)
    g.command("periskop")
    _run(g, 5)
    assert "off.refused" in _types(reports)
    g.world.own.state.depth = 15
    g.world.own.state.order_depth(15)
    g.world.own.state.order_speed(3)
    g.world.own.state.speed = 3
    g.command("periskop")
    _run(g, 25)
    seen = [r for r in reports if r.type == "off.periscope.contact"]
    assert seen
    tr = g.knowledge.track(seen[0].data["designation"])
    assert any(o.range_nm is not None for o in tr.observations)


@pytest.mark.slow
def test_radio_message_needs_antenna_depth():
    g, reports = _game()
    w0 = g.scenario.radio_windows[0]
    _run(g, w0 + 1300)                       # djupt hela fönstret
    assert "radio.missed" in _types(reports)
    assert "radio.prewarn" in _types(reports)
    missed = next(r for r in reports if r.type == "radio.missed")
    nxt = g.clock_str(g.scenario.radio_windows[1])[:5]
    assert missed.data["next"] == nxt and f"kl {nxt}" in missed.text   # sänds om vid nästa

    g, reports = _game()
    g.world.own.state.depth = 25
    g.world.own.state.order_depth(25)
    _run(g, w0 + 120)
    msgs = [r for r in reports if r.type == "radio.message"]
    assert msgs and "SIGNALSJUNKBOMBER" in msgs[0].data["text"]
    assert "Radiogram nummer 1" in msgs[0].text and "SIGNALSJUNKBOMBER" not in msgs[0].text


def test_sending_report_is_direction_found():
    g, reports = _game()
    ai = g.world.ais[0]
    g.world.own.state.depth = 15
    g.world.own.state.order_depth(15)
    g.command("sänd rapport")
    _run(g, 40)
    assert "radio.sent" in _types(reports)
    assert ai.datum is not None and ai.datum.sigma >= 1.0
    assert g.world.mission["reports_sent"] == 1


def test_torpedo_fire_needs_solution_and_nuclear_is_locked():
    g, reports = _game()
    dd = _park_destroyer(g, 10.0, 6.0, speed=0)
    g.world.own.state.order_speed(3)
    k = g.knowledge
    g.bus.publish(ContactDetected(0, "S-1", 0.0, "jagare", Quality.GOD))
    ex, ey = g.own_position_estimate()
    g.bus.publish(BearingObserved(0, BearingObs(0, 0.0, 0.5, ex, ey, 0, designation="S-1",
                                                range_nm=distance(ex, ey, dd.state.x, dd.state.y),
                                                range_sigma=0.02)))
    for t in range(1, 8):
        g.bus.publish(BearingObserved(0, BearingObs(t, 0.0, 0.5, ex, ey, 0, designation="S-1")))
    room = g.station(TorpedoRoom)
    room.tubes[6].load = "T-5"
    g.command("eld tub 7 mot S-1")
    g.command("eld tub 1 mot S-2")
    g.command("eld tub 1 mot S-1")
    _run(g, 10)
    texts = [r.text for r in reports]
    assert any("kärnladdningen kräver kärnvapenråd" in t for t in texts)
    assert any("ingen kontakt S-2" in t for t in texts)
    assert any(isinstance(v, Torpedo) for v in g.world.contacts)
    assert room.tubes[0].load is None


def test_reload_and_decoy():
    g, reports = _game()
    g.command("ladda tub 7 set-53")
    g.command("skenmål")
    _run(g, 310)
    assert g.station(TorpedoRoom).tubes[6].load == "SET-53"
    assert "torp.decoy" in _types(reports)


@pytest.mark.slow
def test_dead_reckoning_drifts_and_fix_corrects():
    drifts, afters = [], []
    for seed in range(1, 6):
        g, reports = _game(seed)
        nav = g.station(NavigationStation)
        _run(g, 3600)
        s = g.world.own.state
        drift = distance(nav.est_x, nav.est_y, s.x, s.y)
        assert drift > 0.2
        s.depth = 15
        s.order_depth(15)
        s.order_speed(3)
        s.speed = 3
        g.command("fix")
        _run(g, 130)
        drifts.append(drift)
        afters.append(distance(nav.est_x, nav.est_y, s.x, s.y))
        assert "nav.fix.done" in _types(reports)
    # fixen har eget brus (σ 0,08 nm per axel); i medel ska felet mer än halveras
    assert sum(afters) < sum(drifts) / 2


def test_active_sonar_gives_range_but_reveals_us():
    g, reports = _game()
    _park_destroyer(g, 10.0, 6.5, speed=5)
    from sim.enemy import DestroyerAI
    ai = DestroyerAI(g.world.contacts[0], random.Random(1))
    g.world.ais.append(ai)
    g.command("aktiv sonar")
    _run(g, 15)
    echo = [r for r in reports if r.type == "sonar.active.echo"]
    assert echo and echo[0].data["range"] > 0
    assert ai.datum is not None


def test_game_ends_when_patrol_is_over():
    g, _ = _game()
    ended = []
    g.bus.subscribe(GameEnded, lambda e: ended.append(e))
    g.world.patrol_end = 50
    g.world.ais.clear()
    _run(g, 60)
    assert ended and ended[0].outcome == "patrol_end"
    assert g.over


def test_torpedoes_cannot_be_fired_deeper_than_100_m():
    g, reports = _game()
    g.world.own.state.depth = 110
    g.command("eld tub 1 kurs 090")
    _run(g, 10)
    assert any(r.type == "torp.refused" and "högst 100 meter" in r.text for r in reports)
    assert not any(isinstance(w, Torpedo) for w in g.world.contacts)
    g.world.own.state.depth = 95
    g.command("eld tub 1 kurs 090")
    _run(g, 10)
    assert any(isinstance(w, Torpedo) for w in g.world.contacts)
