"""Uppföljning av egna torpeder: sonar följer dem, torpedrummet rapporterar."""
import pytest
import random
import re

from sim.events import BearingObserved, ContactDetected, ReportDelivered
from sim.game import Game
from sim.geo import bearing_to, distance
from sim.reports import Quality
from sim.scenario import default_scenario
from sim.stations import TorpedoRoom
from sim.tma import BearingObs

SEEDS = range(1, 6)


@pytest.fixture(autouse=True)
def _perfect(perfect_torpedoes):
    """Torpedfelen provas för sig (test_torpedo_faults.py)."""


def _game(seed):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _setup(g, range_nm=2.0, dd_speed=0.0, dd_course=90.0):
    """Jagaren rakt norr om oss, passiv, klassad, och plottet har en exakt lösning.
    Ingen civil trafik."""
    g.world.ais.clear()
    g.world.contacts = [v for v in g.world.contacts if v.side != "neutral"]
    g.world.spawners.clear()
    own = g.world.own.state
    own.order_speed(3)
    dd = g.world.contacts[0]
    dd.state.x, dd.state.y = own.x, own.y + range_nm
    dd.state.course = dd_course
    dd.state.order_course(dd_course)
    dd.state.speed = dd_speed
    dd.state.order_speed(dd_speed)
    ex, ey = g.own_position_estimate()
    b = bearing_to(ex, ey, dd.state.x, dd.state.y)
    g.bus.publish(ContactDetected(g.now, "S-1", b, "jagare", Quality.GOD))
    g.bus.publish(BearingObserved(g.now, BearingObs(
        g.now, b, 0.5, ex, ey, own.course, designation="S-1",
        range_nm=distance(ex, ey, dd.state.x, dd.state.y), range_sigma=0.02)))
    for k in range(1, 8):
        g.bus.publish(BearingObserved(g.now, BearingObs(g.now + k, b, 0.5, ex, ey, own.course,
                                                        designation="S-1")))
    return dd


def _run_until(g, reports, types, limit):
    for _ in range(limit):
        g.tick()
        if any(r.type in types for r in reports):
            return
    raise AssertionError(f"inget av {types} inom {limit} s")


def _types(reports):
    return [r.type for r in reports]


def test_hit_is_followed_and_reported_per_tube():
    for seed in SEEDS:
        g, reports = _game(seed)
        dd = _setup(g)
        g.command("eld tub 2 mot S-1")
        for _ in range(30):
            g.tick()
        g.command("torpeder")
        _run_until(g, reports, {"torp.run.hit"}, 400)
        g.tick()
        g.command("torpeder")
        for _ in range(15):
            g.tick()
        t = _types(reports)
        assert dd.sunk, f"seed {seed}"
        assert "torp.run.running" in t
        hit = next(r for r in reports if r.type == "torp.run.hit")
        assert hit.text.startswith("Tub 2: detonation i bäring")
        status = [r.text for r in reports if r.type == "torp.in_water"]
        assert "tub 2 (53-61 mot S-1)" in status[0] and "beräknad träff om" in status[0]
        assert status[-1] == "Inga torpeder i vattnet."
        # sonarens allmänna detonationsrapport ersätts av torpedrummets
        assert "sonar.explosion" not in t
        assert not g.station(TorpedoRoom).in_water


@pytest.mark.slow
def test_miss_is_reported():
    for seed in SEEDS:
        g, reports = _game(seed)
        dd = _setup(g)
        g.command("eld tub 1 kurs 180")          # rakt bort från jagaren
        _run_until(g, reports, {"torp.run.silent", "torp.run.timeout"}, 900)
        assert not dd.sunk
        assert "torp.run.hit" not in _types(reports)
        miss = next(r for r in reports if r.type in ("torp.run.silent", "torp.run.timeout"))
        assert miss.text.startswith("Tub 1:") and "miss" in miss.text.lower()
        assert not g.station(TorpedoRoom).in_water


@pytest.mark.slow
def test_homing_torpedo_turn_is_heard():
    turned = 0
    for seed in SEEDS:
        g, reports = _game(seed)
        dd = _setup(g, range_nm=1.5, dd_speed=10)
        g.command("eld tub 5 kurs 030")          # 30° fel, målsökaren måste svänga
        _run_until(g, reports, {"torp.run.hit", "torp.run.silent", "torp.run.timeout"}, 900)
        if "torp.run.turned" in _types(reports):
            turned += 1
            r = next(r for r in reports if r.type == "torp.run.turned")
            assert r.text.startswith("Tub 5: torpeden svänger")
    assert turned >= 4


def test_torpedo_reports_never_reveal_truth_ids():
    g, reports = _game(2)
    _setup(g)
    g.command("eld tub 1 mot S-1")
    g.command("eld tub 3 kurs 200")
    for i in range(700):
        g.tick()
        if i % 60 == 0:
            g.command("torpeder")
    for r in reports:
        assert not re.search(r"\b(T|DD|D)\d+\b", r.text), r.text


def test_tubes_and_torpedoes_are_separate_orders():
    g, reports = _game(1)
    g.command("tuber")
    g.command("torpeder")
    for _ in range(15):
        g.tick()
    t = _types(reports)
    assert "torp.status" in t and "torp.in_water" in t


def test_salvo_is_all_or_nothing():
    """En tub i intervallet som inte får skjuta (T-5 utan order) stoppar salvan innan någon går."""
    g, reports = _game(1)
    _setup(g)
    room = g.station(TorpedoRoom)
    room.tubes[1].load = "T-5"
    loaded = [t.load for t in room.tubes]
    g.command("eld tub 1-3 mot S-1")
    for _ in range(5):
        g.tick()
    assert [t.load for t in room.tubes] == loaded and not room.in_water
    refused = [r for r in reports if r.type == "torp.refused"]
    assert refused and "kärnladdningen" in refused[0].text


def test_reverse_tube_range_means_the_same_tubes():
    from sim.stations.torpedo_room import FireSalvo
    g, _ = _game(1)
    assert g.registry.parse("eld tub 3-1 mot S-1") == FireSalvo("S-1", (1, 2, 3))


def test_the_solution_says_where_the_straight_torpedo_comes_in():
    from types import SimpleNamespace
    from sim.stations.torpedo_room.phrases import PHRASES
    g, _ = _game(1)
    room = g.station(TorpedoRoom)
    sol = lambda course, sigma=5.0, speed=10.0: SimpleNamespace(course=course, course_sigma=sigma,
                                                                 speed=speed)
    # torpeden går norrut: målet på kurs 180 möter den rakt förifrån, på kurs 090 från sidan
    bow = room._aspect(sol(180.0), 0.0)
    assert bow["deg"] < 1 and bow["narrow"]
    beam = room._aspect(sol(90.0), 0.0)
    assert abs(beam["deg"] - 90) < 1 and not beam["narrow"] and beam["side"] == "styrbord"
    stern = room._aspect(sol(10.0), 0.0)
    assert stern["deg"] > 165 and stern["narrow"] and stern["side"] == "styrbord"
    assert room._aspect(sol(90.0, sigma=40.0), 0.0) is None      # kursen okänd
    assert room._aspect(sol(90.0, speed=0.5), 0.0) is None       # ligger still
    d = {"designation": "S-1", "quality": Quality.SAKER, "aspect": stern,
         "rows": [{"type": "53-61", "course": 0.0, "run_s": 200.0}]}
    text = PHRASES["torp.solution"](d)
    assert "10° från aktern, styrbord" in text and "salva hjälper inte" in text


def test_a_homing_torpedo_warns_about_another_ship_near_the_target():
    from sim.tma import Solution
    from sim.weapons import Torpedo
    g, reports = _game(1)
    dd = _setup(g, range_nm=2.0)
    ex, ey = g.own_position_estimate()
    g.bus.publish(ContactDetected(g.now, "S-2", 0.0, "patrullbåt", Quality.GOD))
    tr2 = g.knowledge.track("S-2")
    tr2.observations.append(BearingObs(g.now, 5.0, 0.5, ex, ey, 0.0, designation="S-2"))
    x2, y2 = dd.state.x + 0.3, dd.state.y          # 0,3 nm öster om målet, still
    tr2.solution = Solution(t=g.now, t_ref=g.now, state=(x2, y2, 0.0, 0.0), x=x2, y=y2, course=0.0,
                            speed=0.0, range_nm=2.0, bearing=5.0, range_sigma=0.1, course_sigma=180.0,
                            speed_sigma=0.5, quality=Quality.GOD, n_obs=20, span_s=900,
                            own_maneuvered=True, rms_residual=1.0)
    room = g.station(TorpedoRoom)
    for t in room.tubes:
        t.load = None
    room.tubes[0].load = "SET-53"
    torps = lambda: [v for v in g.world.contacts if isinstance(v, Torpedo)]
    g.command("eld tub 1 mot S-1")
    assert not torps()
    for _ in range(20):
        g.tick()
        if any(r.type == "torp.neutral" for r in reports):
            break
    warn = [r for r in reports if r.type == "torp.neutral"]
    assert warn and "S-2" in warn[0].text and "kan ta fel fartyg" in warn[0].text
    g.command("eld tub 1 mot S-1")
    assert len(torps()) == 1
