"""Förenklade order: beteckningen ensam, eld S-1, fix som väljer metod, torped, läget.
De gamla formerna finns kvar som tysta synonymer."""
import random

import pytest

from sim.events import ReportDelivered
from sim.game import Game, build_registry
from sim.orders import AskContact
from sim.scenario import default_scenario
from sim.stations import DEFAULT_STATIONS, NavigationStation, TorpedoRoom
from sim.stations.officer import Situation
from sim.stations.torpedo_room import FireAt, TorpedoReport

reg = build_registry(DEFAULT_STATIONS)


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()


def test_new_forms_parse():
    assert reg.parse("S-1") == AskContact("S-1")
    assert reg.parse("s1?") == AskContact("S-1")
    assert reg.parse("eld S-2") == FireAt("S-2")
    assert reg.parse("skjut mot s-2") == FireAt("S-2")
    assert reg.parse("torped") == TorpedoReport()
    assert reg.parse("läget") == Situation()


@pytest.mark.parametrize("text", ["läge S-1", "plot S-1", "skjutlösning S-1", "stjärnfix", "bottenfix",
                                  "periskop upp", "periskop ned", "förstoring hög", "sakta back",
                                  "full back", "tuber", "torpeder", "eld tub 1 mot S-1",
                                  "eld tub 1-3 mot S-1", "sänd rapport S-3", "förslag sonar",
                                  "lyssna radio", "radio moskva"])
def test_old_forms_still_work(text):
    from sim.orders import Unknown
    assert not isinstance(reg.parse(text), Unknown), text


def test_fire_at_picks_homing_first_and_never_the_nuclear_tube(monkeypatch):
    g, _ = _game()
    tr = g.station(TorpedoRoom)
    monkeypatch.setattr(TorpedoRoom, "_solution_for", lambda self, d: (None, None))
    monkeypatch.setattr(TorpedoRoom, "_blocked", lambda self, key: None)
    for t in tr.tubes:
        t.load, t.loading = None, None
    tr.tubes[0].load, tr.tubes[1].load, tr.tubes[2].load = "53-61", "T-5", "SET-53"
    assert tr._pick_tube("S-1") == 3
    tr.tubes[2].load = None
    assert tr._pick_tube("S-1") == 1
    tr.tubes[0].load = None
    assert tr._pick_tube("S-1") is None                    # bara T-5 kvar: kräver tubens nummer


def test_fix_deep_takes_the_bottom_when_it_can(monkeypatch):
    for possible, want in ((True, "nav.bfix"), (False, "nav.fix.refused")):
        g, reports = _game()
        monkeypatch.setattr(NavigationStation, "_bfix_possible", lambda self, p=possible: p)
        st = g.world.own.state
        st.depth = 120
        st.order_depth(120)
        st.speed = 5
        st.order_speed(5)
        g.command("fix")
        _run(g, 5)
        assert any(r.type.startswith(want) for r in reports), (possible, [r.type for r in reports])


def test_situation_and_phone_call_without_starpom():
    g, reports = _game()
    g.command("läget")
    _run(g, 5)
    g.command("lägesrapport")                              # kaptenen har befälet: vakthavande svarar
    _run(g, 5)
    sit = [r for r in reports if r.type == "off.situation"]
    assert len(sit) == 2 and "Kapten, vakthavande. Djup" in sit[0].text


def test_torped_reports_tubes():
    g, reports = _game()
    g.command("torped")
    _run(g, 5)
    assert any(r.type == "torp.status" for r in reports)
