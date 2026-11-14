"""Isens ljud: bakgrundsbrus, knakande transienter och falska kontakter."""
import random

import numpy as np

from sim.environment import Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.ice import NOISE_SOLID_DB, IceField, IceSource
from sim.knowledge import ContactTrack
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations import SonarRoom


def test_noise_is_quiet_under_solid_ice_and_loud_where_it_moves():
    f = IceField(random.Random(4))
    assert f.noise_db.min() >= NOISE_SOLID_DB - 1e-9
    assert f.noise_db.max() > 65
    active = f.activity > 0.6
    calm = (f.activity == 0) & (f.thickness > 2.0)
    assert f.noise_db[active].mean() > f.noise_db[calm].mean() + 8


def test_environment_noise_falls_back_without_ice():
    assert Environment().noise_at(3, 4) == 60.0
    f = IceField(random.Random(1))
    env = Environment(ice=f)
    assert env.noise_at(3, 4) == f.noise_at(3, 4)


def test_ice_source_is_not_a_ship():
    src = IceSource("IS1", 0, 0, 140.0, 100, 200.0, 0.25)
    assert not src.is_ship
    assert src.radiated_level(None) == 140.0
    src.sunk = True
    assert src.radiated_level(None) < 0


def test_benign_needs_good_quality():
    tr = ContactTrack("S-1", 0, classification="trolig isskruvning", class_quality=Quality.GOD)
    assert tr.benign and not tr.threat
    tr2 = ContactTrack("S-2", 0, classification="bredbandigt brus, ingen tydlig maskin",
                       class_quality=Quality.OSAKER)
    assert not tr2.benign and tr2.threat


def _run(seed, seconds=2 * 3600):
    g = Game(build_scenario("arktis", random.Random(seed)), seed=seed)
    g.world.mission.pop("fire_at", None)              # bara isen i dessa tester
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.command("djup 100")
    for _ in range(seconds):
        g.tick()
    return g, reports


def test_sources_come_and_go():
    g, _ = _run(1, 3 * 3600)
    ice = g.world.env.ice
    assert ice._source_no >= 4
    assert len(ice.sources) <= 4                       # gamla tas bort
    assert all(s in g.world.contacts for s in ice.sources)


def test_ice_contacts_are_classified_as_ice_over_seeds():
    """Sonaren tar ofta isljud för kontakter, men lyssnar sig fram till att det är is."""
    detected = classified = 0
    for seed in range(1, 9):
        g, reports = _run(seed)
        texts = [r.text for r in reports]
        assert not any("IS1" in t or "ICE" in t for t in texts)     # sanningens id:n läcker inte
        assert any(r.type == "sonar.ice" for r in reports)
        # sanningen avgör vilka beteckningar som var isljud (bara testet tittar)
        sensor = g.station(SonarRoom).sensor
        ice_desigs = {t.designation for vid, t in sensor._tracks.items()
                      if vid.startswith("IS") and t.designation}
        ice_tracks = [g.knowledge.tracks[d] for d in ice_desigs if d in g.knowledge.tracks]
        if ice_tracks:
            detected += 1
            if any(t.benign for t in ice_tracks):
                classified += 1
    assert detected >= 3                               # ibland, inte alltid
    # svaga källor tystnar ibland innan sonaren hunnit avgöra vad de var
    assert classified >= max(2, detected // 2)
