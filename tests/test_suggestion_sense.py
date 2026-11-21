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


def test_a_suggestion_never_comes_before_the_report_it_follows():
    from sim.reports import Report, ReportQueue
    q = ReportQueue()
    q.submit(Report(11, "Maskin", "eng.suggest.creep", {"order": "smygmotor"}, kind="suggest"))
    q.submit(Report(12, "Sonar", "sonar.new_contact", {}, kind="contact"))
    assert [r.type for r in q.due(20)] == ["sonar.new_contact", "eng.suggest.creep"]
    q.submit(Report(30, "Vakthavande", "off.esm", {}, kind="contact"))
    q.submit(Report(29, "Vakthavande", "off.suggest.down", {"order": "djup 60"}, kind="suggest"))
    assert [r.type for r in q.due(40)] == ["off.esm", "off.suggest.down"]
    # långt isär: förslaget väntar inte
    q.submit(Report(50, "Maskin", "eng.suggest.creep", {"order": "smygmotor"}, kind="suggest"))
    q.submit(Report(70, "Sonar", "sonar.new_contact", {}, kind="contact"))
    assert [r.type for r in q.due(60)] == ["eng.suggest.creep"]


def test_no_new_firing_solution_while_our_torpedoes_run_at_the_target():
    from sim.stations.torpedo_room.common import Running
    g, _ = _game()
    room = g.station(TorpedoRoom)
    room.in_water.append(Running(1, 1, "53-61", "S-1", 90.0, g.now, g.now + 120, g.now + 600))
    said = []
    room.suggest = lambda key, type, *a, **k: said.append(type) or True
    from types import SimpleNamespace
    from sim.reports import Quality
    tr = SimpleNamespace(designation="S-1", threat=True, friendly=False, held=True,
                         solution=SimpleNamespace(quality=Quality.SAKER))
    g.knowledge.tracks = {"S-1": tr}
    room._readiness()
    assert said == []


def test_firing_solution_without_contact_picks_the_best_threat():
    from types import SimpleNamespace
    from sim.reports import Quality
    g, _ = _game()
    room = g.station(TorpedoRoom)
    mk = lambda d, q, r: SimpleNamespace(designation=d, held=True, threat=True,  # noqa: E731
                                         solution=SimpleNamespace(quality=q, range_nm=r))
    g.knowledge.tracks = {"S-1": mk("S-1", Quality.OSAKER, 1.0), "S-2": mk("S-2", Quality.GOD, 4.0),
                          "S-3": mk("S-3", Quality.GOD, 2.0)}
    assert room._best_target() == "S-3"
    g.knowledge.tracks = {}
    assert room._best_target() is None


def test_an_anchored_ship_is_reported_lying_still():
    from sim.phrases import render
    from sim.reports import Report
    r = Report(0, "Vakthavande", "off.periscope.contact",
               {"designation": "S-9", "label": "fartyg till ankars", "bearing": 231.0, "range": 7.8,
                "course": None, "speed": 0, "lights": []})
    render(r, lambda t=None: "06:00:00")
    assert "Ligger still" in r.text and "Vinkel på bogen" not in r.text
    r = Report(0, "Bryggan", "bridge.contact",
               {"designation": "S-9", "label": "fartyg till ankars", "bearing": 231.0, "range": 2.0,
                "visible": "helt", "course": None, "speed": 0, "lights": ["topp"]})
    render(r, lambda t=None: "06:00:00")
    assert "ankarljus" in r.text and "Ligger still" in r.text

