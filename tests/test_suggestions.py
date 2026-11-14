"""Förslag om sådant kaptenen redan har beordrat ges inte och hålls inte kvar."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import default_scenario
from sim.stations import EngineeringStation, NavigationStation, SonarRoom


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    g.world.ais.clear()
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()


def _suggestions(reports):
    return [r for r in reports if r.kind == "suggest"]


def test_own_order_clears_pending_suggestion_of_same_kind():
    g, reports = _game()
    g.station(EngineeringStation).suggest("t", "eng.suggest.cavitation", {"speed": 7},
                                          order="fart 7")
    _run(g, 15)
    assert g.active_suggestion() is not None
    g.command("fart 6")
    assert g.active_suggestion() is None
    assert g.status().suggestion is None


def test_other_kind_of_order_keeps_suggestion():
    g, reports = _game()
    g.station(EngineeringStation).suggest("t", "eng.suggest.cavitation", {"speed": 7},
                                          order="fart 7")
    _run(g, 15)
    g.command("kurs 090")
    assert g.active_suggestion()[0] == "fart 7"


def test_queued_suggestion_is_dropped_after_own_order():
    g, reports = _game()
    g.station(EngineeringStation).suggest("t", "eng.suggest.cavitation", {"speed": 7},
                                          order="fart 7")
    g.command("fart 6")                  # innan förslaget hunnit levereras
    _run(g, 30)
    assert not _suggestions(reports)
    assert g.active_suggestion() is None


def test_no_suggestion_of_standing_order_already_given():
    g, reports = _game()
    g.command("djup 120")
    _run(g, 5)
    sonar = g.station(SonarRoom)
    assert not sonar.suggest("layer", "sonar.suggest.layer", {"layer": 60, "depth": 120},
                             order="djup 120")
    # en annan djupändring kan fortfarande föreslås senare
    assert sonar.suggest("evade", "sonar.suggest.depth_change", {"depth": 200},
                         order="djup 200")
    _run(g, 30)
    assert [r.data["order"] for r in _suggestions(reports)] == ["djup 200"]


def test_one_shot_order_can_be_suggested_again_later():
    g, reports = _game()
    g.command("fix")
    _run(g, 5)
    nav = g.station(NavigationStation)
    assert nav.suggest("fix_now", "nav.suggest.fix_now", {"sigma": 1.0}, order="fix")


def test_cavitation_suggestion_not_repeated_once_ordered():
    """Kaptenen skriver själv in föreslagen fart: inget nytt förslag om samma fart."""
    g, reports = _game()
    g.command("djup 30")
    g.command("fart 20")
    _run(g, 200)
    sug = [r for r in _suggestions(reports) if r.type == "eng.suggest.cavitation"]
    assert sug
    ordered = sug[0].data["order"]
    g.command(ordered)
    assert g.active_suggestion() is None
    n = len(sug)
    eng = g.station(EngineeringStation)
    eng._suggested.clear()               # ingen cooldown som döljer resultatet
    _run(g, 120)
    later = [r for r in _suggestions(reports) if r.type == "eng.suggest.cavitation"][n:]
    assert all(r.data["order"] != ordered for r in later)
