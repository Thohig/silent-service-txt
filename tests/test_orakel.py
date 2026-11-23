"""Oraklet (kalibrering/orakel.py) larmar för de fel det ska hitta."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kalibrering"))

from orakel import Orakel  # noqa: E402
from sim.game import Game  # noqa: E402
from sim.reports import Quality, Report  # noqa: E402
from sim.scenario import build_scenario  # noqa: E402


def _game(key="kuba"):
    g = Game(build_scenario(key, random.Random(1)), seed=1, warm_up=False)
    return g, Orakel(g)


def _deliver(g, type_, data=None, kind="info", quality=None, role="navigator"):
    g._deliver(Report(g.now, "Test", type_, dict(data or {}), role=role, kind=kind, quality=quality))


def test_grounding_without_warning_is_flagged_and_with_warning_not():
    g, o = _game()
    g.world.mission["grounded_t"] = g.now
    o.tick()
    assert [a[0] for a in o.larm] == ["grund_utan_varning"]
    g2, o2 = _game()
    _deliver(g2, "nav.suggest.land", {"shoal": 10, "dist": 0.5, "course": 90, "order": "kurs 090"},
             kind="suggest")
    g2.world.mission["grounded_t"] = g2.now
    o2.tick()
    assert not any(a[0] == "grund_utan_varning" for a in o2.larm)


def test_the_same_suggestion_again_and_again_is_flagged():
    g, o = _game()
    for i in range(4):
        g.world.time += 120
        _deliver(g, "nav.suggest.fix", {"sigma": 1.2, "order": "periskopdjup"}, kind="suggest")
    assert any(a[0] == "tjatar" for a in o.larm)


def test_a_wrong_sure_solution_is_flagged():
    from sim.stations.sonar_room import SonarRoom
    from sim.tma import Solution
    g, o = _game()
    v = next(c for c in g.world.contacts if c.side == "enemy")
    sensor = g.station(SonarRoom).sensor
    d = "S-1"
    sensor.designation_of = lambda vid, d=d, v=v: d if vid == v.id else None
    g.knowledge.on_detection(d, g.now)
    tr = g.knowledge.tracks[d]
    own = g.world.own.state
    x, y = own.x + 10.0, own.y + 10.0                    # långt från sanningen
    tr.solution = Solution(t=g.now, t_ref=g.now, state=(x, y, 0.0, 0.0), x=x, y=y, course=0.0,
                           speed=0.0, range_nm=14.1, bearing=45.0, range_sigma=0.1, course_sigma=5.0,
                           speed_sigma=0.5, quality=Quality.SAKER, n_obs=40, span_s=1200,
                           own_maneuvered=True, rms_residual=0.5)
    from sim.stations.plot import solution_data
    _deliver(g, "plot.improved", {"designation": d, "solution": solution_data(tr.solution)},
             kind="solution", quality=Quality.SAKER, role="plot")
    assert any(a[0] == "säker_men_fel" for a in o.larm)


def test_text_checks():
    g, o = _game()
    _deliver(g, "system.text", {"text": "Avstånd 2.5 nm, kurs 45 och None"})
    kinds = [a[2] for a in o.larm if a[0] == "text"]
    assert any("None" in k for k in kinds) and any("punktdecimal" in k for k in kinds)
