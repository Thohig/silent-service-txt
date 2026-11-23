"""Fiendens torpeder (D1): målsökning mot oss och skenmålen, träffen, sonarens larm och förslaget."""
import random

import pytest

from sim.entities import Vessel
from sim.events import ReportDelivered, TorpedoInWater
from sim.game import Game
from sim.geo import velocity
from sim.scenario import build_scenario
from sim.ship import ShipState
from sim.weapons import MK37, Decoy, launch_decoy, launch_enemy_torpedo, lead_course

SEEDS = range(1, 9)


def _game(seed=1, depth=120.0, speed=0.0, propulsion="turbine"):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts, w.ais = [], []
    st = w.own.state
    st.depth = st.ordered_depth = depth
    st.speed = st.ordered_speed = speed
    w.own.sys.propulsion = propulsion
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _shoot(g, range_nm=2.0, bearing=90.0, depth=None):
    """En fiende i bäring `bearing` från oss skjuter rakt mot oss."""
    o = g.world.own.state
    dx, dy = velocity(bearing, range_nm * 3600)
    shooter = Vessel("US1", "submarine", ShipState(x=o.x + dx, y=o.y + dy, course=0, speed=0,
                                                   depth=o.depth), side="enemy")
    course = lead_course(shooter.state.x, shooter.state.y, o.x, o.y, o.course, o.speed, MK37.speed)
    return launch_enemy_torpedo(g.world, shooter, MK37, course, o.depth if depth is None else depth)


def _run(g, n):
    for _ in range(n):
        if g.over:
            break
        g.tick()


def test_stillaliggande_bat_traffas():
    g, _ = _game()
    _shoot(g)
    _run(g, 600)
    assert g.world.mission.get("hit_by_torpedo") is not None
    assert g.world.outcome and g.world.outcome["outcome"] == "lost"


def test_full_fart_bort_klarar_sig():
    """627A går 28 knop på turbinen, Mk 37 bara 26: rakt bort från 2 nm hinner den inte ikapp."""
    g, _ = _game(depth=150, speed=28)
    g.world.own.state.course = g.world.own.state.ordered_course = 270.0     # bort från bäring 090
    _shoot(g)
    _run(g, 900)
    assert g.world.mission.get("hit_by_torpedo") is None


def test_skenmalet_drar_torpeden_fran_en_tyst_bat():
    """Skenmålet låter mer än en båt på smygmotorn: torpeden går på det (sedan söker den om)."""
    g, _ = _game(depth=120, speed=3, propulsion="electric")
    t = _shoot(g, range_nm=1.5)
    _run(g, 30)
    launch_decoy(g.world)
    g.command("kurs 180")
    locked_decoy = False
    for _ in range(600):
        g.tick()
        if g.over:
            break
        tgt = next((v for v in g.world.contacts if v.id == t.locked), None)
        locked_decoy |= isinstance(tgt, Decoy)
    assert locked_decoy


def test_torpeden_maste_ha_ratt_djup():
    g, _ = _game(depth=250)
    t = _shoot(g, range_nm=0.6, depth=40)
    t.spec = type(t.spec)(**{**t.spec.__dict__, "homing": False})     # rak, utan att söka djup
    _run(g, 200)
    assert g.world.mission.get("hit_by_torpedo") is None


def test_sonar_larmar_och_foreslar_undanmanover():
    g, reports = _game(depth=100, speed=4)
    heard = []
    g.bus.subscribe(TorpedoInWater, heard.append)
    _shoot(g, range_nm=2.5)
    _run(g, 40)
    alarm = next(r for r in reports if r.type == "sonar.torpedo")
    assert alarm.alarm and "Torped i vattnet" in alarm.text
    sug = next(r for r in reports if r.type == "sonar.suggest.evade")
    order = sug.data["order"]
    course = int(order.split("kurs ")[1][:3])
    assert order.startswith("skenmål") and abs(course - 270) <= 5 and "fart 28" in order
    assert heard and heard[0].kind == "new"
    assert "E1" not in alarm.text                                    # aldrig sanningens id


@pytest.mark.slow
def test_ja_till_undanmanovern_raddar_de_flesta():
    survived = lost_passive = 0
    for seed in SEEDS:
        for yes in (True, False):
            g, reports = _game(seed=seed, depth=100, speed=4, propulsion="electric")
            _shoot(g, range_nm=2.5, bearing=random.Random(seed).uniform(0, 360))
            for _ in range(900):
                if g.over:
                    break
                g.tick()
                if yes and g.active_suggestion() and "skenmål" in g.active_suggestion()[0]:
                    g.command("ja")
            hit = g.world.mission.get("hit_by_torpedo") is not None
            if yes:
                survived += not hit
            else:
                lost_passive += hit
    assert survived >= 6
    assert lost_passive >= 6


# --- torpeden i döda sektorn (2026-11-23) -------------------------------------------
from sim.sonar import IncomingTorpedo  # noqa: E402
from sim.stations import SonarRoom  # noqa: E402
from sim.stations.incoming import TORPEDO_RUN_S  # noqa: E402


def _heard_then_lost(g, bearing, lost_bearing, n=10):
    sonar = g.station(SonarRoom)
    for k in range(n):
        g.tick()
        sonar._on_incoming(IncomingTorpedo(1, "new" if k == 0 else "bearing", bearing, 12.0, 120.0))
    first = g.now - n + 1
    g.tick()
    sonar._on_incoming(IncomingTorpedo(1, "lost", lost_bearing))
    _run(g, 30)                     # rapporterna levereras ur kön
    return first


def _fleeing(g, course=270.0, speed=28.0, depth=50.0):
    st = g.world.own.state
    st.course = st.ordered_course = course
    st.speed = st.ordered_speed = speed
    st.depth = st.ordered_depth = depth


def test_tappad_akterut_gar_troligen_kvar():
    """Vi springer ifrån torpeden: den tystnar rakt akterut, i döda sektorn. Sonar säger att den
    troligen går kvar, och torpedlarmet gäller dess gångtid ut (förut sänkte maskin farten efter 5 min)."""
    g, reports = _game(depth=50, speed=28)
    _fleeing(g)
    first = _heard_then_lost(g, 90.0, 92.0)
    lost = [r for r in reports if r.type == "sonar.torpedo.lost"]
    assert lost and lost[-1].data.get("astern") and lost[-1].alarm
    assert "döda sektorn" in lost[-1].text and 10 <= lost[-1].data["minutes"] <= 12
    k = g.knowledge
    assert k.torpedo_alarm(g.now + 600)
    assert not k.torpedo_alarm(first + TORPEDO_RUN_S + 1)


def test_tappad_akterut_inga_forslag_om_fart_eller_gir():
    """Medan torpeden troligen går akterut föreslår maskin inte lägre fart för kavitationen, och sonar
    föreslår ingen gir för att lyssna akterut."""
    g, reports = _game(depth=50, speed=28)
    _fleeing(g)
    first = _heard_then_lost(g, 90.0, 90.0)
    _run(g, 9 * 60)
    types = {r.type for r in reports if r.data.get("made_t", first + 1) > first}
    assert "eng.suggest.cavitation" not in types
    assert "sonar.suggest.clear_baffles" not in types


def test_tappad_tvars_ar_borta():
    """Tystnar torpeden där vi hör (tvärs), är den borta: larmet släpper som förut."""
    g, reports = _game(depth=50, speed=28)
    _fleeing(g)
    _heard_then_lost(g, 0.0, 0.0)
    lost = [r for r in reports if r.type == "sonar.torpedo.lost"]
    assert lost and not lost[-1].data.get("astern")
    assert not g.knowledge.torpedo_alarm(g.now + 61)


def test_hord_och_tappad_igen_tvars_slapper_akterlarmet():
    g, _ = _game(depth=50, speed=28)
    _fleeing(g)
    _heard_then_lost(g, 90.0, 90.0)
    assert g.knowledge.torpedo_alarm(g.now + 300)
    sonar = g.station(SonarRoom)
    g.tick()
    sonar._on_incoming(IncomingTorpedo(1, "bearing", 10.0, 12.0, 120.0))
    g.tick()
    sonar._on_incoming(IncomingTorpedo(1, "lost", 10.0))
    assert not g.knowledge.torpedo_alarm(g.now + 61)
