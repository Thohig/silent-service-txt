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


def _repeat(g, key, order, alarm=False, until=4000):
    """Försök ge samma förslag varje sekund; returnera när det faktiskt gavs."""
    eng = g.station(EngineeringStation)
    times = []
    for _ in range(until):
        if eng.suggest(key, "eng.suggest.restart", order=order, cooldown=300, alarm=alarm):
            times.append(g.now)
        g.tick()
    return times


def test_unanswered_suggestion_backs_off():
    g, _ = _game()
    for st in g.stations:
        st.idle_proposals = lambda: []
    times = _repeat(g, "r", "starta reaktorn")
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps[0] >= 840 and gaps[1] >= 1680
    assert all(b >= a for a, b in zip(gaps, gaps[1:]))


def test_answered_suggestion_keeps_normal_cooldown():
    g, _ = _game()
    eng = g.station(EngineeringStation)
    assert eng.suggest("r", "eng.suggest.restart", order="starta reaktorn", cooldown=300)
    for _ in range(3):
        _run(g, 100)
        g.command("nej")                 # kaptenen svarar
        _run(g, 201)
        assert eng.suggest("r", "eng.suggest.restart", order="starta reaktorn", cooldown=300)


def test_alarm_suggestion_does_not_back_off():
    g, _ = _game()
    times = _repeat(g, "b", "nödblåsning", alarm=True, until=1300)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps and all(gap == 300 for gap in gaps)
