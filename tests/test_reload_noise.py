"""Omladdningen hörs: torpeden som går in i tuben och bakluckan som stängs slamrar i vattnet."""
import random

from sim import acoustics
from sim.enemy import DestroyerAI
from sim.events import OwnSoundMade, ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario, default_scenario
from sim.stations.torpedo_room import RELOAD_CLANK_S, RELOAD_QUIET_S, RELOAD_S, TorpedoRoom


def _game(key=None, seed=2):
    sc = build_scenario(key, random.Random(seed)) if key else default_scenario(random.Random(seed))
    g = Game(sc, seed=seed)
    reports, sounds, clanks = [], [], []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.bus.subscribe(OwnSoundMade, lambda e: sounds.append(e.kind))
    orig = g.world.emit

    def emit(tr):
        if tr.kind == "reload":
            clanks.append((g.now, tr.level))
        orig(tr)
    g.world.emit = emit
    return g, reports, sounds, clanks


def _empty_tube(g) -> int:
    room = g.station(TorpedoRoom)
    t = room.tubes[0]
    if t.load:
        room.inventory[t.load] = room.inventory.get(t.load, 0) + 1
        t.load = None
    return t.n


def test_reload_clanks_twice_and_is_heard_by_our_own_crew():
    g, reports, sounds, clanks = _game()
    n = _empty_tube(g)
    g.command(f"ladda tub {n} 53-61")
    for _ in range(RELOAD_S + 20):
        g.tick()
    assert len(clanks) == 2 and all(lv == acoustics.RELOAD_LEVEL for _, lv in clanks)
    assert clanks[0][0] - clanks[1][0] < 0
    assert sounds.count("reload") == 2
    assert any(r.type == "torp.loaded" for r in reports)


def test_on_the_creep_motor_the_crew_loads_quietly_and_slower():
    g, reports, sounds, clanks = _game()
    n = _empty_tube(g)
    g.command("smygmotor")
    for _ in range(3):
        g.tick()
    g.command(f"ladda tub {n} 53-61")
    for _ in range(RELOAD_S + 5):
        g.tick()
    assert not any(r.type == "torp.loaded" for r in reports)
    for _ in range(RELOAD_QUIET_S - RELOAD_S):
        g.tick()
    assert any(r.type == "torp.loaded" for r in reports)
    assert any(r.type == "torp.loading" and "försiktigt" in r.text for r in reports)
    assert all(lv == acoustics.RELOAD_LEVEL - acoustics.RELOAD_QUIET_DB for _, lv in clanks)


def test_destroyer_close_above_the_layer_gets_a_datum_from_the_clank():
    """Fast tröskel: en jagare som söker sakta nära oss över skiktet hör slamret."""
    g, *_ = _game("jagad", seed=1)
    w = g.world
    ai = next(a for a in w.ais if isinstance(a, DestroyerAI))
    s, o = ai.vessel.state, w.own.state
    s.speed = 5
    noise = ai._noise(w)
    tl_near = acoustics.transmission_loss(0.5, 5.0, 30, w.env)
    tl_far_deep = acoustics.transmission_loss(2.0, 5.0, 150, w.env)
    from sim.enemy import DT_PASSIVE
    assert acoustics.RELOAD_LEVEL - tl_near - noise - DT_PASSIVE > 0
    assert acoustics.RELOAD_LEVEL - tl_far_deep - noise - DT_PASSIVE < 0
    tl_1nm = acoustics.transmission_loss(1.0, 5.0, 30, w.env)
    assert acoustics.RELOAD_LEVEL - tl_1nm - noise - DT_PASSIVE > 0
    assert acoustics.RELOAD_LEVEL - acoustics.RELOAD_QUIET_DB - tl_1nm - noise - DT_PASSIVE < 0


def test_no_idle_reload_proposal_while_hunted():
    g, *_ = _game()
    _empty_tube(g)
    room = g.station(TorpedoRoom)
    assert room.idle_proposals()
    g.knowledge.hunted = lambda now: True
    assert room.idle_proposals() == []
