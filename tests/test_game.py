import pytest
import random

from sim.events import ReportDelivered, TimeScaleChanged
from sim.game import Game
from sim.scenario import default_scenario


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_course_order_is_acknowledged_then_reported_done():
    g, reports = _game()
    g.command("kurs 090")
    for _ in range(150):
        g.tick()
    kinds = [(r.kind, r.text) for r in reports if r.kind in ("ack", "done")]
    assert kinds[0] == ("ack", "Jest, kurs 090.")
    assert kinds[1] == ("done", "Kapten, kurs 090 påkommen.")
    assert g.status().course == 90


def test_new_contact_drops_time_compression_to_1x():
    g, reports = _game()
    changes = []
    g.bus.subscribe(TimeScaleChanged, lambda e: changes.append((e.scale, e.reason)))
    g.command("tid 10")
    for _ in range(3600):
        g.tick()
        if any(r.kind == "contact" and r.alarm for r in reports):
            break
    assert any(r.alarm for r in reports), "jagaren borde höras inom en timme"
    assert g.time_scale == 1
    assert changes[-1] == (1, "larm")


@pytest.mark.slow
def test_reports_never_reveal_truth_ids():
    g, reports = _game()
    for _ in range(3000):
        g.tick()
    assert reports
    assert not any("DD1" in r.text for r in reports)
