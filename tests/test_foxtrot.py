"""Den sovjetiska ubåten (sim/foxtrot.py): smyger, snorklar och hörs då, staben meddelar läget, och plottet
räknar den som vänlig när sonar känt igen den."""
import random

from sim import foxtrot as F
from sim.environment import Environment
from sim.knowledge import ContactTrack
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.sonar import _CLASS_STAGES as CLASSES


def test_it_creeps_quietly_and_is_loud_when_snorting():
    b = F.Foxtrot("B36", 0, 0, 0)
    env = Environment()
    quiet = b.radiated_level(env)
    b.snorting = True
    b.state.depth = F.SNORT_DEPTH_M
    b.state.speed = F.SNORT_KN
    assert b.radiated_level(env) > quiet + 30


def test_the_ai_goes_up_to_snort_and_down_again():
    sc = build_scenario("kuba", random.Random(1))
    w = sc.world
    ai = next(a for a in w.ais if isinstance(a, F.FoxtrotAI))
    seen = set()
    for t in range(0, 5 * 3600, 30):
        w.time = t
        ai.step(w)
        seen.add(ai.vessel.snorting)
    assert seen == {True, False}


def test_hq_tells_roughly_where_b36_is_and_kuba_kort_has_none():
    sc = build_scenario("kuba", random.Random(2))
    wp = sc.radio_messages[0].waypoint
    assert wp[0] == "B-36" and "B-36" in sc.radio_messages[0].text
    assert not any(v.kind == "foxtrot" for v in build_scenario("kuba-kort", random.Random(2)).world.contacts)


def test_sonar_knows_its_own_class_at_best_and_then_it_is_friendly():
    best = CLASSES["foxtrot"][-1]
    tr = ContactTrack("S-5", 0, classification=best, class_quality=Quality.SAKER)
    assert tr.friendly and not tr.threat
    unsure = ContactTrack("S-5", 0, classification=CLASSES["foxtrot"][2], class_quality=Quality.GOD)
    assert unsure.threat                          # trolig ubåt med diesel: kan vara amerikansk
