"""Svansen (svansen-kort): döda sektorn akterut, sonars gir för att lyssna, den skuggande ubåten."""
import math
import random

import pytest

from sim.arctic import SubmarineAI
from sim.events import ReportDelivered
from sim.game import Game
from sim.geo import angle_diff, bearing_to
from sim.goals import ShakeGoal
from sim.scenario import SCENARIOS, TAIL_WARM_S, build_scenario
from sim.sonar import BAFFLE_EDGE_DEG, BAFFLE_HULL_DB, baffle_loss


def _game(seed=1, warm=True):
    g = Game(build_scenario("svansen-kort", random.Random(seed)), seed=seed, warm_up=False)
    if warm:
        g.warm_up()
    return g


def _ai(g) -> SubmarineAI:
    return next(a for a in g.world.ais if isinstance(a, SubmarineAI))


def _put_astern(g, off_deg, r=1.5):
    o = g.world.own.state
    b = math.radians(o.course + 180 + off_deg)
    return o.x + r * math.sin(b), o.y + r * math.cos(b)


def test_registrerad_i_kriget_med_mal_och_dod_sektor():
    sd = SCENARIOS["svansen-kort"]
    assert sd.section == "krig" and sd.minutes
    g = _game(warm=False)
    assert g.world.own.baffle_deg > 0
    assert g.world.goal(ShakeGoal) is not None
    assert _ai(g).state == "shadow" and _ai(g).roe == "attack"
    # de andra scenarierna har ingen död sektor (idén att införa den överallt står i IDEER)
    other = Game(build_scenario("duell-kort", random.Random(1)), seed=1, warm_up=False)
    assert other.world.own.baffle_deg == 0
    assert baffle_loss(other.world, *_put_astern(other, 0)) == 0


def test_dod_sektor_akterut_tonar_vid_kanten_och_vaxer_med_farten():
    g = _game(warm=False)
    w, o = g.world, g.world.own.state
    half = w.own.baffle_deg
    o.speed = 4
    assert baffle_loss(w, *_put_astern(g, 0)) == pytest.approx(BAFFLE_HULL_DB)
    assert baffle_loss(w, *_put_astern(g, -half + 1)) == pytest.approx(BAFFLE_HULL_DB)
    edge = baffle_loss(w, *_put_astern(g, half + BAFFLE_EDGE_DEG / 2))
    assert 0 < edge < BAFFLE_HULL_DB
    assert baffle_loss(w, *_put_astern(g, half + BAFFLE_EDGE_DEG + 1)) == 0
    assert baffle_loss(w, *_put_astern(g, 180)) == 0              # förut
    o.speed = 10
    assert baffle_loss(w, *_put_astern(g, 0)) > BAFFLE_HULL_DB + 5


@pytest.mark.slow
def test_svansen_ligger_i_doda_sektorn_och_hors_inte_under_vakten():
    for seed in range(1, 6):
        g = _game(seed)
        assert not g.knowledge.tracks, seed                      # inga kontakter vid överlämnandet
        o, s = g.world.own.state, _ai(g).vessel.state
        off = abs(angle_diff(bearing_to(o.x, o.y, s.x, s.y), o.course + 180))
        assert off < g.world.own.baffle_deg, (seed, off)
        assert 1.2 < g.world.true_range(_ai(g).vessel) < 2.3, seed
        assert _ai(g).state == "shadow"


@pytest.mark.slow
def test_sonar_foreslar_giren_och_giren_hittar_svansen():
    """Förslaget kommer inom 3 min efter överlämnandet (riktmärket), och säger kaptenen ja hörs
    ubåten inom 3 min i de flesta frön."""
    found = 0
    for seed in range(1, 7):
        g = _game(seed)
        start, said = g.now, []
        g.bus.subscribe(ReportDelivered, lambda e: said.append((g.now - start, e.report)))
        accepted = None
        for _ in range(8 * 60):
            g.tick()
            if accepted is None and any(r.type == "sonar.suggest.clear_baffles" for _, r in said):
                accepted = g.now - start
                g.command("ja")
            if accepted is not None and g.knowledge.tracks:
                break
        assert accepted is not None and accepted <= 180, seed
        if g.knowledge.tracks and g.now - start - accepted <= 180:
            found += 1
    assert found >= 4, found


def test_ping_eller_naerhet_vacker_svansen():
    g = _game(warm=False)
    ai, o = _ai(g), g.world.own.state
    g.command("aktiv sonar")
    for _ in range(10):
        g.tick()
    assert ai.state == "trail"                                  # vi har den: anfall
    g2 = _game(warm=False)
    ai2 = _ai(g2)
    s = ai2.vessel.state
    s.x, s.y = _put_astern(g2, 0, r=0.5)
    ai2.datum = type(ai2.datum)(g2.world.own.state.x, g2.world.own.state.y, 100.0, 0.1, 0)
    ai2.datums = [ai2.datum]
    for _ in range(6):
        g2.tick()
    assert ai2.state == "trail"


def test_skakad_av_nar_ingen_haft_oss_pa_tio_minuter():
    g = _game(warm=False)
    goal = g.world.goal(ShakeGoal)
    ai = _ai(g)
    ai.state, ai.datum = "patrol", None                         # den har tappat oss
    ai.vessel.state.x += 15
    goal.since_t = 0
    for _ in range(goal.quiet_s + 5):
        g.tick()
        if g.over:
            break
    assert g.world.outcome["outcome"] == "shaken"
