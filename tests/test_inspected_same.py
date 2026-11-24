"""Samma anmärkningar som förra inspektionen inom 15 min: maskin säger kort "inget nytt" (jagad frö 3,
2026-11-24: samma långa rad sex gånger på 20 min)."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.stations import engineering as E


def _run_inspection(g, eng, seen):
    eng._inspect_t = g.now
    for _ in range(5):
        g.tick()
    return [r.type for r in seen if r.type.startswith("eng.inspected")][-1]


def test_same_remarks_are_short_new_remarks_in_full():
    g = Game(build_scenario("jagad", random.Random(3)), seed=3, warm_up=False)
    eng = g.station(E.EngineeringStation)
    seen = []
    g.bus.subscribe(ReportDelivered, lambda e: seen.append(e.report))
    rows = [(5, "Reaktor", E.DANGER, "snabbstopp")]
    eng._compartments = lambda: rows
    assert _run_inspection(g, eng, seen) == "eng.inspected"
    assert _run_inspection(g, eng, seen) == "eng.inspected.same"
    rows.append((1, "Torped", E.WARN, "skador"))
    assert _run_inspection(g, eng, seen) == "eng.inspected"
    found, t = eng._inspected_last
    eng._inspected_last = (found, t - E.INSPECT_SAME_S - 1)     # förra inspektionen längre sedan
    assert _run_inspection(g, eng, seen) == "eng.inspected"
