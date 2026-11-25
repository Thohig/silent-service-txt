"""Helikoptern med doppingsonar (sim/helo.py): flyger, doppar, pingar från en fast punkt, ger jagaren läget,
fäller en Mk 44 med skarpa regler, och sonar känner igen den."""
import random

from sim import helo as H
from sim.enemy import DestroyerAI
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario


def _game(seed=1):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    w = g.world
    w.spawners = [sp for sp in w.spawners if not isinstance(sp, H.HeloPatrol)]
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _helo_near(g, r_nm=0.5):
    w = g.world
    o = w.own.state
    h = H.Helicopter("HS9", o.x + r_nm, o.y, 270)
    ai = H.HelicopterAI(h, random.Random(1), w.size_nm, 10**9, (30.0, 10.0))
    ai.point = (h.state.x, h.state.y)
    w.contacts.append(h)
    w.ais.append(ai)
    return h, ai


def test_the_helicopter_dips_pings_from_a_fixed_point_and_gives_the_destroyer_a_fix():
    g, reports = _game()
    h, ai = _helo_near(g)
    dd = next(a for a in g.world.ais if isinstance(a, DestroyerAI))
    dd.datum = None
    pings = []
    orig = g.world.emit
    g.world.emit = lambda tr: (pings.append((g.now, tr.x, tr.y)) if tr.kind == "dip_ping" else None, orig(tr))[-1]
    for _ in range(H.DIP_LOWER_S + H.DIP_S):
        g.tick()
    assert len(pings) >= H.DIP_S // H.DIP_PING_S - 1
    assert len({(round(x, 4), round(y, 4)) for _, x, y in pings}) == 1          # en fast punkt
    assert ai.datum is not None and dd.datum is not None and dd.datum.sigma < 0.1
    assert any(r.type == "sonar.dip" and "helikopter" in r.text for r in reports)


def test_with_lethal_rules_it_drops_a_homing_torpedo_once():
    g, _ = _game()
    h, ai = _helo_near(g)
    for a in g.world.ais:
        if isinstance(a, DestroyerAI):
            a.roe = "lethal"
    for _ in range(H.DIP_LOWER_S + H.DIP_S):
        g.tick()
        if g.over:
            break
    assert ai.dropped and g.world.mission.get("enemy_torpedoes", 0) == 1


def test_the_patrol_waits_for_a_destroyer_datum():
    g, _ = _game()
    w = g.world
    patrol = H.HeloPatrol(H.HeloDef(first_s=(0, 0)), random.Random(1), w.size_nm)
    for a in w.ais:
        if isinstance(a, DestroyerAI):
            a.datum = None
    patrol.step(w)
    assert patrol.current is None
    dd = next(a for a in w.ais if isinstance(a, DestroyerAI))
    o = w.own.state
    dd._set_datum(w, o.x, o.y, 100, 0.5)
    w.time = patrol.next_t
    patrol.step(w)
    assert patrol.current is not None and getattr(patrol.current.vessel, "helo", False)


def test_no_radar_warning_from_a_helicopter():
    g, reports = _game()
    _helo_near(g, 2.0)
    st = g.world.own.state
    st.depth = st.ordered_depth = 15.0
    for _ in range(30):
        g.tick()
    assert not any(r.type == "off.esm.air" for r in reports)


def test_outside_war_the_patrol_sends_helicopters_without_torpedoes():
    assert not H.HeloDef().torpedo
    sc = build_scenario("krig", random.Random(1))
    assert any(isinstance(sp, H.HeloPatrol) and sp.hdef.torpedo for sp in sc.world.spawners)
