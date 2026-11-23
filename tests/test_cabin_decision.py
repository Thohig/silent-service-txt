"""Hytten: telefonen och beslutet syns mitt i bilden, och starpom säger varför stationen föreslår."""
import random

from sim.events import ReportDelivered
from sim.game import Game, StatusSnapshot
from sim.scenario import build_scenario
from sim.stations.starpom import FirstOfficer, suggestion_why
from ui.cabin_render import render_cabin

BASE = dict(clock=4 * 3600, sim_time=0, course=90.0, ordered_course=90.0, speed=3.0,
            ordered_speed=3.0, depth=17.0, ordered_depth=17.0, changing=frozenset(), time_scale=1,
            command="starpom", captain_at="cabin")
WHY = ("Sambandstillfället är öppet och huvudstaben väntar på vår rapport. Föreslår att vi sänder nu. "
       "Det tar cirka 22 sekunder, och risken att de pejlar oss är liten.")


def _text(s, w, h):
    return "\n".join(line.plain for line in render_cabin(s, 0.0, w, h))


def test_the_decision_card_shows_who_what_why_and_how_to_answer_in_all_sizes():
    s = StatusSnapshot(**BASE, decision="Radio föreslår sänd rapport", decision_why=WHY)
    for w, h in ((60, 14), (80, 20), (120, 30), (200, 50)):
        txt = _text(s, w, h)
        assert "ERT BESLUT" in txt, (w, h)
        assert "Radio föreslår: sänd rapport" in txt, (w, h)
        assert " ja " in txt and " nej " in txt, (w, h)
    assert "huvudstaben" in _text(s, 120, 30)


def test_a_ringing_phone_is_shown_mid_picture_with_enter():
    s = StatusSnapshot(**BASE, phone="ring")
    txt = _text(s, 120, 30)
    assert "SNABBTELEFONEN RINGER" in txt and "Enter" in txt


def test_no_card_when_the_captain_has_command():
    s = StatusSnapshot(**{**BASE, "command": "captain"}, decision="Radio föreslår sänd rapport")
    assert "ERT BESLUT" not in _text(s, 120, 30)


def test_starpom_quotes_the_station_without_the_address():
    q = suggestion_why({"type": "sonar.suggest.depth_change", "data": {"depth": 140}})
    assert q == "Föreslår djupändring till 140 meter, så att de tappar ekot!"


def test_starpom_tells_the_reasons_on_the_phone():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    reps = []
    g.bus.subscribe(ReportDelivered, lambda e: reps.append(e.report))
    g.command("starpom har befälet")
    for _ in range(5):
        g.tick()
    xo = g.station(FirstOfficer)
    xo._wake("question", {"kind": "suggestion", "who": "Sonar", "proposed": "djup 140",
                          "why": {"type": "sonar.suggest.depth_change", "data": {"depth": 140}}})
    g.command("svara")
    for _ in range(5):
        g.tick()
    call = [r for r in reps if r.type == "xo.call"]
    assert call and "Han säger: »" in call[-1].text and "140" in call[-1].text
