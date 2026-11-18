"""Ryska inslag: fasta fraser med svensk mening bredvid, rysk röst i talet."""
import pytest
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


# --- ryskt tal ------------------------------------------------------------------
from sim import russian as R  # noqa: E402
from sim.phrases import RU_PHRASES  # noqa: E402


def test_russian_numbers_read_like_at_sea():
    assert R.course(90) == "ноль девять ноль"
    assert R.course(360) == "ноль ноль ноль"
    assert [R.count(n, R.MILE) for n in (1, 3, 5, 11, 21, 22)] == [
        "1 миля", "3 мили", "5 миль", "11 миль", "21 миля", "22 мили"]
    assert R.dec(3.24, R.MILE) == "3 и две десятых мили"
    assert R.dec(0.5, R.MILE) == "пять десятых мили"
    assert R.dec(2.0, R.MILE) == "2 мили"
    assert R.dec(1.1, R.MILE) == "1 и одна десятая мили"
    assert R.mmss(273) == "4 минуты 33 секунды"
    assert R.contact("S-12") == "цель 12" and R.contact("S-2", genitive=True) == "цели 2"


def test_every_classification_has_russian():
    from sim.sonar import _CLASS_STAGES
    for stages in _CLASS_STAGES.values():
        for c in stages:
            assert c in R.CLASS_RU, c


def test_report_without_russian_phrase_says_who_reports():
    assert R.fallback("navigator", "ack") == "Есть."
    assert R.fallback("sonar", "info") == "Товарищ командир, акустик."
    assert R.fallback("plot", "suggest").endswith("Есть предложение.")


def test_every_phrase_has_russian_or_is_never_spoken():
    """Varje fras som kan läsas upp har en rysk fras; de som aldrig läses upp står i NO_SPEECH."""
    from sim.phrases import NO_SPEECH, PHRASES
    import sim.game  # noqa: F401  (registrerar alla stationers fraser)
    missing = sorted(k for k in PHRASES if k not in RU_PHRASES and k not in NO_SPEECH)
    assert not missing, missing
    assert not NO_SPEECH & set(RU_PHRASES), "fras i NO_SPEECH har ändå rysk fras"


@pytest.mark.slow
def test_russian_speech_is_pure_cyrillic_over_a_patrol():
    """Över en patrull med ja-bot: allt tal har rysk fras, och inget latinskt läcker in."""
    import re
    from sim.scenario import build_scenario
    for key, seed in (("kuba", 2), ("jagad", 3), ("arktis-kort", 4), ("sundet-in", 1)):
        g = Game(build_scenario(key, random.Random(seed)), seed=seed)
        reports = []
        g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
        for _ in range(3600):
            g.tick()
            if any(r.kind == "suggest" and r.data.get("order") for r in reports[-3:]):
                g.command("ja")
            if g.now % 300 == 0:        # statusfrågorna läses också upp
                g.command("status; position; ekolod; tuber; radio")
        spoken = [r for r in reports if r.role and r.kind != "system" and r.table is None]
        assert len(spoken) > 20
        assert all(r.type in RU_PHRASES for r in spoken), \
            (key, sorted({r.type for r in spoken} - set(RU_PHRASES)))
        for r in spoken:
            assert r.speech and not re.search(r"[A-Za-zÅÄÖåäö]", r.speech), (r.type, r.speech)


def test_half_knots_are_spoken_not_rounded_away():
    from sim.phrases import RU_PHRASES
    assert "пять десятых узла" in RU_PHRASES["nav.speed.ack"]({"speed": 0.5})
    assert "5 и пять десятых узла" in RU_PHRASES["nav.speed.done"]({"speed": 5.5})
    assert "Есть, ход 6 узлов." == RU_PHRASES["nav.speed.ack"]({"speed": 6})
