"""Ryska inslag: fasta fraser med svensk mening bredvid, rysk röst i talet."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.russian import WORDS, glossary, ru, segments
from sim.scenario import default_scenario
from sim.stations.engineering import _inspected


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_segments_split_russian_from_swedish():
    assert segments("Jest, kurs 090.") == [("ru", "Есть"), ("sv", "kurs 090.")]
    assert segments(f"{ru('Avarijnaja trevoga')}! Brand i turbinrummet!") == [
        ("ru", "Аварийная тревога!"), ("sv", "Brand i turbinrummet!")]
    assert segments("Kapten, plottet.") == [("sv", "Kapten, plottet.")]
    # ett svenskt ord som börjar likadant är inte ryska
    assert segments("Jesters") == [("sv", "Jesters")]


def test_every_word_has_meaning_in_help():
    g, reports = _game()
    g.command("hjälp")
    g.tick()
    text = next(r.text for r in reports if r.type == "system.help")
    for w in WORDS.values():
        assert w.meaning and f"{w.latin} = {w.meaning}" in text
    assert glossary().startswith("Ryska:")


def test_jest_accepts_a_suggestion():
    g, reports = _game()
    assert g.registry.parse("jest") == g.registry.parse("ja")


def test_compartment_inspection_lists_remarks():
    assert _inspected({"remarks": []}) == "Alla nio avdelningar inspekterade, inga anmärkningar."
    txt = _inspected({"remarks": [(5, "snabbstopp"), (6, "BRAND")], "leak": True})
    assert "Inga anmärkningar i första, andra, tredje, fjärde, sjunde, åttonde och nionde." in txt
    assert "Femte avdelningen: snabbstopp." in txt and "Sjätte avdelningen: brand." in txt
    assert txt.endswith("Vatteninträngning, länsning pågår.")
    all_smoke = _inspected({"remarks": [(n, "rök") for n in range(1, 10)]})
    assert "Alla avdelningar: rök." in all_smoke and "Inga anmärkningar" not in all_smoke


def test_damage_raises_alarm_and_compartments_report():
    g, reports = _game()
    g.world.own.sys.health["sonar"] = 0.6
    g.world.own.alert("damage", severity="lätta", components=["sonar"], leak=False)
    for _ in range(120):
        g.tick()
    dmg = next(r for r in reports if r.type == "damage")
    assert dmg.text.startswith("Avarijnaja trevoga! Lätta skador")
    insp = next(r for r in reports if r.type == "eng.inspected")
    assert insp.t_due >= dmg.t_due + 50
    assert "Första avdelningen: skador." in insp.text


def test_battle_stations_once_when_hunted():
    g, reports = _game()
    k = g.knowledge
    for t in (10, 40, 70):
        while g.now < t:
            g.tick()
        k.hunt_t = g.now
    for _ in range(30):
        g.tick()
    calls = [r for r in reports if r.type == "off.battle_stations"]
    assert len(calls) == 1 and calls[0].alarm
    assert calls[0].text.startswith("Boevaja trevoga! Stridslarm")
