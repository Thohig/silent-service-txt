"""Sjökortet: elementen byggs ur kunskapen, i navigatörens beräknade koordinater."""
import random

from sim.chart import Mark, Note, Ray, Ring, Track
from sim.events import BearingObserved, ContactDetected, ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations import NavigationStation
from sim.tma import BearingObs

TRUTH_IDS = ("DD1", "SSN1", "NORD7", "T1", "D1")


def _game(key="kuba", seed=3):
    return Game(build_scenario(key, random.Random(seed)), seed=seed)


def _yes_bot(g):
    g.bus.subscribe(ReportDelivered,
                    lambda e: e.report.kind == "suggest" and e.report.data.get("order")
                    and g.command("ja"))


def _labels(view):
    out = [n.text for n in view.notes]
    out += [i.label for i in view.drawables if isinstance(i, (Mark, Ray))]
    return out


def test_own_mark_is_the_estimate_not_the_truth():
    g = _game()
    nav = g.station(NavigationStation)
    nav.est_x += 0.7                               # besticket har glidit
    g.tick()
    view = g.chart()
    own = [i for i in view.drawables if isinstance(i, Mark) and i.style == "own"]
    assert len(own) == 1
    assert (own[0].x, own[0].y) == (nav.est_x, nav.est_y)
    assert abs(own[0].x - g.world.own.state.x) > 0.5
    assert view.own == (nav.est_x, nav.est_y)
    assert any("besticket" in n.text for n in view.notes)
    ring = next(i for i in view.drawables if isinstance(i, Ring) and i.style == "own")
    assert ring.radius == nav.uncertainty()


def test_dead_reckoning_track_and_fix_split_the_track():
    g = _game()
    nav = g.station(NavigationStation)
    for _ in range(600):
        g.tick()
    assert len(nav.dr_track[0]) >= 10
    s = g.world.own.state
    s.depth = s.ordered_depth = 15
    s.speed = s.ordered_speed = 3
    nav.est_x += 1.0
    g.command("fix")
    for _ in range(200):
        g.tick()
    assert len(nav.fixes) == 1
    view = g.chart()
    tracks = [i for i in view.drawables if isinstance(i, Track)]
    assert len(tracks) == 2
    fx, fy, _ = nav.fixes[0]
    assert tracks[1].points[0] == (fx, fy)
    assert any(isinstance(i, Mark) and i.style == "fix" for i in view.drawables)


def test_bearing_without_solution_is_drawn_from_where_we_thought_we_were():
    g = _game()
    g.bus.publish(ContactDetected(0, "S-4", 120.0, "okänd kontakt"))
    g.bus.publish(BearingObserved(0, BearingObs(0, 121.0, 1.0, 3.0, 4.0, 0,
                                                designation="S-4")))
    rays = [i for i in g.chart().drawables if isinstance(i, Ray) and i.style == "bearing"]
    assert len(rays) == 1
    r = rays[0]
    assert (r.x, r.y, r.bearing) == (3.0, 4.0, 121.0)
    assert r.label.startswith("S-4 121")
    assert r.quality == Quality.DALIG


def test_ice_soundings_openings_and_station_appear_in_the_arctic():
    g = _game("arktis", seed=2)
    for _ in range(1800):
        g.tick()
    view = g.chart()
    styles = {i.style for i in view.drawables}
    assert "ice_thick" in styles
    assert any(isinstance(i, Mark) and i.style == "waypoint" and "Nord-7" in i.label
               for i in view.drawables)
    ice = [i for i in view.drawables if isinstance(i, Mark) and i.style.startswith("ice")]
    assert len(ice) == len(g.knowledge.ice.soundings)


def test_chart_never_reveals_truth_ids():
    for key, seed in (("kuba", 1), ("kuba", 4), ("arktis", 2), ("arktis", 5)):
        g = _game(key, seed)
        _yes_bot(g)
        for t in range(3600):
            g.tick()
            if t % 300 == 0:
                for label in _labels(g.chart()):
                    assert not any(tid in label for tid in TRUTH_IDS), (key, seed, label)
            if g.over:
                break
