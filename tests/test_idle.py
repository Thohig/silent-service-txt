"""Besättningen tar initiativ när kaptenen är tyst en längre stund."""
import pytest
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import default_scenario
from sim.stations import EngineeringStation, OfficerStation, TorpedoRoom
from sim.stations.base import Proposal, Station
from sim.stations.officer import QUIET_S

SEEDS = range(1, 6)


def _game(seed=3, stations=None):
    g = Game(default_scenario(random.Random(seed)), seed=seed, stations=stations)
    g.world.ais.clear()
    g.world.contacts = [v for v in g.world.contacts if v.side != "neutral"]   # tomt hav
    g.world.spawners.clear()
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n):
    for _ in range(n):
        g.tick()


def _idle(g, reports):
    """Förslag som kom från tystnadsvakten (nycklar idle_*)."""
    return [r for r in reports if r.kind == "suggest" and r.data.get("idle")]


def _mark_idle(g):
    """Märk initiativförslag i rapportdatan så att testerna kan skilja ut dem."""
    for st in g.stations:
        orig = st.propose

        def propose(p, _orig=orig):
            return _orig(Proposal(p.priority, p.key, p.type, p.order,
                                  {**p.data, "idle": True}, p.quality, p.cooldown))
        st.propose = propose


def test_no_initiative_before_quiet_period():
    for seed in SEEDS:
        g, reports = _game(seed)
        _mark_idle(g)
        g.command("kurs 090")
        _run(g, QUIET_S - 5)
        assert not _idle(g, reports)


@pytest.mark.slow
def test_initiative_comes_after_quiet_and_is_paced():
    for seed in SEEDS:
        g, reports = _game(seed)
        _mark_idle(g)
        _run(g, 3 * QUIET_S + 60)
        idle = _idle(g, reports)
        assert idle, f"seed {seed}: inget initiativ"
        assert len(idle) <= 3
        times = [r.t_due for r in idle]
        assert all(b - a >= QUIET_S - 30 for a, b in zip(times, times[1:]))


def test_any_input_resets_the_quiet_clock():
    g, reports = _game()
    _mark_idle(g)
    for _ in range(4):
        _run(g, QUIET_S - 60)
        g.command("nej")
    assert not _idle(g, reports)


class _Probe(Station):
    """Teststation med fasta förslag i olika prioritet."""
    role = EngineeringStation.role

    def idle_proposals(self):
        return [Proposal(5, "low", "eng.suggest.creep", "smygmotor"),
                Proposal(1, "high", "eng.suggest.restart", "starta reaktorn")]


def test_most_important_proposal_wins():
    from sim.stations import DEFAULT_STATIONS
    g, reports = _game(stations=[*DEFAULT_STATIONS, _Probe])
    for st in g.stations:
        if not isinstance(st, _Probe):
            st.idle_proposals = lambda: []
    _run(g, QUIET_S + 30)
    sug = [r for r in reports if r.kind == "suggest"]
    assert [r.data["order"] for r in sug] == ["starta reaktorn"]


def test_no_initiative_while_a_suggestion_waits():
    g, reports = _game()
    _mark_idle(g)
    _run(g, QUIET_S - 20)
    g.station(EngineeringStation).suggest("x", "eng.suggest.restart", order="starta reaktorn")
    _run(g, 60)
    assert g.active_suggestion() is not None
    assert not _idle(g, reports)


@pytest.mark.slow
def test_reload_proposed_but_never_fire_or_nuclear():
    g, reports = _game()
    room = g.station(TorpedoRoom)
    _run(g, 6 * 3600)
    orders = [r.data["order"] for r in reports if r.kind == "suggest" and r.data.get("order")]
    assert any(o.startswith("ladda tub") for o in orders)
    assert not any(o.startswith(("eld", "avfyra", "skjut")) for o in orders)
    assert not any("t-5" in o.lower() for o in orders)
    assert room.inventory["T-5"] == 2


def test_officer_proposes_periscope_look_when_shallow_and_quiet():
    g, reports = _game()
    s = g.world.own.state
    g.command("periskopdjup")
    g.command("fart 4")
    for st in g.stations:
        if not isinstance(st, OfficerStation):
            st.idle_proposals = lambda: []
    _run(g, QUIET_S + 300)
    assert s.depth <= 18
    assert "off.suggest.look" in [r.type for r in reports]


# --- förslag på begäran ------------------------------------------------------------
def test_ask_gives_best_proposal_immediately():
    g, reports = _game()
    g.command("djup 30")
    g.command("fart 20")              # kaviterar på 30 m
    _run(g, 200)
    reports.clear()
    g.suggestion = None
    g.command("förslag")
    _run(g, 20)
    sug = [r for r in reports if r.kind == "suggest"]
    assert sug and sug[0].type == "eng.suggest.cavitation"


def test_ask_repeats_waiting_suggestion():
    g, reports = _game()
    g.station(EngineeringStation).suggest("x", "eng.suggest.restart", order="starta reaktorn")
    _run(g, 20)
    g.command("förslag")
    assert reports[-1].type == "order.suggestion_repeat"


def test_ask_specific_station_and_nothing_to_say():
    g, reports = _game()
    g.command("förslag torped")
    g.command("förslag radio")
    _run(g, 20)
    types = [r.type for r in reports]
    assert "torp.suggest.reload" in types                 # tub 7 och 8 är tomma
    none = [r.text for r in reports if r.type == "off.suggest.none"]
    assert any("Radio har inget att föreslå" in t for t in none)


def test_ask_other_skips_waiting_suggestion():
    g, reports = _game()
    g.command("förslag torped")
    _run(g, 20)
    first = g.active_suggestion()[0]
    g.command("annat förslag")
    _run(g, 20)
    later = [r for r in reports if r.kind == "suggest"][1:]
    assert all(r.data["order"] != first for r in later)
    if not later:                     # inget annat att föreslå: vakthavande säger det
        assert any(r.type == "off.suggest.none" and "Inget annat" in r.text for r in reports)


def test_ask_unknown_station():
    g, reports = _game()
    g.command("förslag kocken")
    _run(g, 20)
    assert any(r.type == "order.unknown" and "vilken station" in r.text for r in reports)


@pytest.mark.slow
def test_ask_never_offers_fire():
    for seed in SEEDS:
        g, reports = _game(seed)
        for i in range(0, 3 * 3600, 300):
            g.command("annat förslag" if i % 600 else "förslag")
            _run(g, 300)
        orders = [r.data.get("order", "") for r in reports if r.kind == "suggest"]
        assert not any(o.startswith(("eld", "avfyra", "skjut")) for o in orders)
