"""Förslag om sådant kaptenen redan har beordrat ges inte och hålls inte kvar."""
import pytest
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


def test_compound_suggestion_is_redundant_only_when_every_part_is_decided():
    """Undanmanövern "kurs, fart, djup" släpps när allt redan är beordrat (den kom förr igen)."""
    g, _ = _game()
    g.command("kurs 189, fart 20, djup 200")
    _run(g, 5)
    assert g.suggestion_redundant("kurs 189, fart 20, djup 200", g.now)
    assert not g.suggestion_redundant("kurs 189, fart 20, djup 220", g.now)   # nytt djup
    assert not g.suggestion_redundant("skenmål, kurs 189", g.now)            # skenmålet är nytt


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


@pytest.mark.slow
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


# --- larmförslag står mot vanliga förslag (Game.held, ALARM_HOLD_S) ------------------------
from sim.game import ALARM_HOLD_S, HELD_MAX_S  # noqa: E402
from sim.reports import Report  # noqa: E402


def _put(g, type, order, data=None, *, alarm=False, role="officer", at=None):
    t = g.now + 1 if at is None else at
    g.queue.submit(Report(t, "Vakthavande", type, dict(data or {}, order=order, made_t=t - 1),
                          role=role, kind="suggest", alarm=alarm))


_DOWN = {"reason": "Flygradar, nära. De kan se våra master.", "why": "air", "depth": 60}
_REPORT = {"now": True, "seconds": 22, "risk": "liten", "short_s": 22}


def test_alarm_suggestion_stands_against_routine():
    g, reports = _game()
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _put(g, "radio.suggest.report", "sänd rapport", _REPORT, role="radio", at=g.now + 5)
    _run(g, 10)
    assert g.active_suggestion()[0] == "djup 60"
    assert [r.type for r in _suggestions(reports)] == ["off.suggest.down"]   # rutinen tiger
    assert g.held is not None


def test_routine_comes_after_the_alarm_is_answered():
    g, reports = _game()
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _put(g, "eng.suggest.cavitation", "fart 7", {"speed": 7}, role="engineer", at=g.now + 5)
    _run(g, 10)
    g.command("ja")
    _run(g, 2)
    assert g.active_suggestion()[0] == "fart 7"
    assert [r.type for r in _suggestions(reports)] == ["off.suggest.down", "eng.suggest.cavitation"]


def test_routine_comes_when_the_alarm_has_stood_long_enough():
    g, reports = _game()
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _put(g, "eng.suggest.cavitation", "fart 7", {"speed": 7}, role="engineer", at=g.now + 5)
    _run(g, ALARM_HOLD_S - 2)
    assert g.active_suggestion()[0] == "djup 60"
    _run(g, 4)
    assert g.active_suggestion()[0] == "fart 7"


def test_newer_alarm_replaces_alarm():
    g, reports = _game()
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _put(g, "eng.suggest.blow", "nödblåsning", {"flooding": 12}, alarm=True, role="engineer",
         at=g.now + 5)
    _run(g, 10)
    assert g.active_suggestion()[0] == "nödblåsning" and g.held is None


def test_alarm_replaces_routine_and_routine_replaces_routine():
    g, reports = _game()
    _put(g, "radio.suggest.report", "sänd rapport", _REPORT, role="radio")
    _put(g, "eng.suggest.cavitation", "fart 7", {"speed": 7}, role="engineer", at=g.now + 3)
    _run(g, 5)
    assert g.active_suggestion()[0] == "fart 7"
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _run(g, 2)
    assert g.active_suggestion()[0] == "djup 60"


def test_newest_held_routine_wins():
    g, reports = _game()
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _put(g, "radio.suggest.report", "sänd rapport", _REPORT, role="radio", at=g.now + 3)
    _put(g, "eng.suggest.cavitation", "fart 7", {"speed": 7}, role="engineer", at=g.now + 6)
    _run(g, 8)
    g.command("nej")
    _run(g, 2)
    assert g.active_suggestion()[0] == "fart 7"
    assert "radio.suggest.report" not in [r.type for r in _suggestions(reports)]


def test_held_routine_is_dropped_when_stale_or_decided():
    g, reports = _game()
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _put(g, "eng.suggest.cavitation", "fart 7", {"speed": 7}, role="engineer", at=g.now + 3)
    _run(g, 5)
    g.command("fart 5")                 # kaptenen har själv beslutat om farten
    _run(g, ALARM_HOLD_S + 2)
    assert "eng.suggest.cavitation" not in [r.type for r in _suggestions(reports)]

    g, reports = _game()
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _put(g, "eng.suggest.cavitation", "fart 7", {"speed": 7}, role="engineer", at=g.now + 3)
    _run(g, 5)
    g.suggestion = (g.suggestion[0], g.suggestion[1], g.now + HELD_MAX_S)   # larmet står länge
    _run(g, HELD_MAX_S + 5)
    g.suggestion = None
    _run(g, 2)
    assert "eng.suggest.cavitation" not in [r.type for r in _suggestions(reports)]


def test_mast_order_is_not_suggested_when_ordered_deep():
    """Ett "sänd rapport" som väntat bakom ett larm om att dyka släpps när vi går ned."""
    g, reports = _game()
    g.command("periskopdjup")
    _run(g, 3)
    _put(g, "off.suggest.down", "djup 60", _DOWN, alarm=True)
    _put(g, "radio.suggest.report", "sänd rapport", _REPORT, role="radio", at=g.now + 3)
    _run(g, 5)
    g.command("ja")                     # djup 60
    _run(g, 3)
    assert "radio.suggest.report" not in [r.type for r in _suggestions(reports)]
    from sim.stations import OfficerStation
    from sim.stations.radio import RadioStation
    assert g.station(RadioStation).vetoes("sänd rapport")
    assert g.station(OfficerStation).vetoes("radar") and g.station(OfficerStation).vetoes("foto")
    assert not g.station(RadioStation).vetoes("periskopdjup")
    g.command("periskopdjup")
    assert not g.station(RadioStation).vetoes("sänd rapport")
