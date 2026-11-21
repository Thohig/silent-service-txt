"""Förslag som inte ska ges: uppåt under jakt, fix på väg ned, för djupt på grunt vatten,
skenmål mot någon annans jakt, samma förslag från två stationer. Och radions statusrad.
(Fynd från ett provspel på 3 timmar i alla långa scenarier, 2026-11-21.)"""
import random

from sim.crew import Role
from sim.events import HuntSigns, ReportDelivered, SoundHeard
from sim.game import Game
from sim.scenario import default_scenario
from sim.stations import NavigationStation, OfficerStation, RadioStation, TorpedoRoom


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, s):
    for _ in range(s):
        g.tick()


def _vetoed(g, order: str) -> bool:
    return any(st.vetoes(order) for st in g.stations)


def test_nobody_suggests_going_up_while_they_have_us():
    g, _ = _game()
    _run(g, 2)
    for order in ("periskopdjup", "antenndjup", "ytläge", "fix", "vak", "ventilera", "djup 40",
                  "fart 5, djup 40"):
        assert not _vetoed(g, order), order
    g.knowledge.hunt_t = g.now                      # sonar: de har oss
    for order in ("periskopdjup", "antenndjup", "ytläge", "fix", "vak", "ventilera", "djup 40",
                  "fart 5, djup 40"):
        assert _vetoed(g, order), order
    for order in ("djup 220", "djup 220, turbin, fart 13", "nödblåsning", "kurs 090", "skenmål"):
        assert not _vetoed(g, order), order
    g.world.own.sys.smoke = 0.8                     # för tät rök: ventilationen går före
    assert not _vetoed(g, "ventilera")


def test_going_up_is_suggested_again_after_the_hunt():
    g, reports = _game()
    _run(g, 2)
    g.knowledge.hunt_t = g.now
    nav = g.station(NavigationStation)
    assert not nav.suggest("t_fix", "nav.suggest.fix", {"sigma": 1.2}, order="periskopdjup")
    g.knowledge.hunt_t = g.now - 400                # tecknen är äldre än fönstret
    assert nav.suggest("t_fix", "nav.suggest.fix", {"sigma": 1.2}, order="periskopdjup")


def test_a_suggestion_waiting_in_the_queue_is_dropped_when_the_hunt_starts():
    g, reports = _game()
    _run(g, 2)
    g.say(Role.RADIO, "order.declined", {"order": "antenndjup", "made_t": g.now}, kind="suggest",
          extra_delay=5)
    g.knowledge.hunt_t = g.now
    _run(g, 10)
    assert not any(r.kind == "suggest" and r.data.get("order") == "antenndjup" for r in reports)


def test_no_periscope_fix_when_the_captain_just_ordered_us_down():
    g, _ = _game()
    st = g.world.own.state
    st.depth = st.ordered_depth = 17
    assert not _vetoed(g, "fix")
    st.ordered_depth = 60
    assert _vetoed(g, "fix")


def test_dive_suggestions_respect_the_navigators_depth_limit():
    g, _ = _game()
    off, nav = g.station(OfficerStation), g.station(NavigationStation)
    nav.depth_limit = lambda: None
    assert off.dive_depth(60) == 60
    nav.depth_limit = lambda: 40
    assert off.dive_depth(60) == 40 and off.dive_depth(30) == 30
    nav.depth_limit = lambda: 17                    # inget under periskopdjup: inget förslag
    assert off.dive_depth(60) is None


def test_decoy_only_when_the_hunt_is_for_us():
    g, reports = _game()
    _run(g, 2)
    g.bus.publish(SoundHeard(g.now, "ping", 10.0, "S-1", detail="fast", se=10.0))
    _run(g, 10)
    assert not any(r.type == "torp.suggest.decoy" for r in reports)
    g.bus.publish(HuntSigns(g.now, "ping"))
    _run(g, 10)
    assert any(r.type == "torp.suggest.decoy" for r in reports)
    assert g.station(TorpedoRoom).decoys > 0


def test_the_same_order_from_two_stations_is_suggested_once():
    g, reports = _game()
    _run(g, 2)
    g.say(Role.NAVIGATOR, "order.declined", {"order": "fart 5, djup 60", "made_t": g.now},
          kind="suggest")
    _run(g, 3)
    g.say(Role.ENGINEER, "order.declined", {"order": "fart 5, djup 60", "made_t": g.now},
          kind="suggest")
    _run(g, 5)
    assert len([r for r in reports if r.data.get("order") == "fart 5, djup 60"]) == 1


def test_radio_status_during_an_open_window_and_after_it():
    g, reports = _game()
    _run(g, 2)
    radio = g.station(RadioStation)
    radio.windows = [g.now - 60, g.now + 3600]
    radio.window_len = 1200
    g.command("radio")
    _run(g, 5)
    text = [r for r in reports if r.type == "radio.status"][-1].text
    assert "pågår" in text and "Inga meddelanden mottagna" in text
    radio._handled.add(0)                           # radiogrammet mottaget: nästa tillfälle
    radio.delivered.append("FRÅN HUVUDSTABEN.")
    g.command("radio")
    _run(g, 5)
    text = [r for r in reports if r.type == "radio.status"][-1].text
    nxt = g.clock_str(radio.windows[1])[:5]
    assert f"Nästa sambandstillfälle kl {nxt}." in text and "1 meddelande mottaget" in text
