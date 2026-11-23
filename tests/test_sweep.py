"""Svepet: många kontakter i ett svep blir en rad och en tabell (periskop, brygga, aktiv sonar)."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.phrases import render
from sim.reports import Quality, Report
from sim.scenario import build_scenario
from sim.stations import SonarRoom
from sim.stations.sweep import BATCH_MIN, QUIET_S, SweepCalls


def _game():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _call(i, label="handelsfartyg"):
    return {"designation": f"S-{i}", "label": label, "bearing": 10.0 * i, "range": 1.0 + i,
            "course": 90.0, "speed": 10, "lights": [], "power": "låg"}


def test_few_calls_are_said_one_by_one():
    g, reports = _game()
    calls = SweepCalls(g.station(SonarRoom), "periscope")
    for i in range(1, BATCH_MIN):
        calls.add("off.periscope.contact", _call(i), kind="contact", quality=Quality.GOD)
    calls.flush()                                    # svepet pågår: inget sägs ännu
    for _ in range(QUIET_S + 8):
        g.tick()
        calls.flush()
    said = [r for r in reports if r.type.startswith("off.periscope")]
    assert [r.type for r in said] == ["off.periscope.contact"] * (BATCH_MIN - 1)


def test_many_calls_become_one_line_and_a_table():
    g, reports = _game()
    calls = SweepCalls(g.station(SonarRoom), "periscope")
    calls.add("off.periscope.contact", _call(3, "jagare"), kind="contact", quality=Quality.GOD)
    for i in (1, 2, 4, 5, 6):
        calls.add("off.periscope.contact", _call(i), kind="contact", quality=Quality.GOD)
    calls.add("off.periscope.again", {"designation": "S-7", "bearing": 70.0, "range": 0.6},
              kind="contact", quality=Quality.GOD)
    calls.flush(force=True)
    for _ in range(8):
        g.tick()
    said = [r for r in reports if r.type.startswith("off.periscope")]
    assert [r.type for r in said] == ["off.periscope.sweep"]
    r = said[0]
    assert r.text.startswith("Periskop: sju fartyg i sikte. Närmast S-7, bäring 070, cirka 0,6 sjömil.")
    assert "Örlogsfartyg: S-3." in r.text
    assert len(r.table) == 7 and r.table[0][0] == "S-7" and r.table[0][4] == "som förut"
    assert r.table[1] == ["S-1", "handelsfartyg", "010", "2,0 nm", "090, 10 kn"]
    assert r.speech and not any(c.isascii() and c.isalpha() for c in r.speech)


def test_a_table_line_is_read_aloud_only_when_it_says_so():
    from ui.audio import spoken
    r = render(Report(0, "Vakthavande", "off.periscope.sweep",
                      {"who": "periscope", "n": 5, "nearest": _call(1), "warships": [],
                       "table": [["S-1", "", "010", "2,0 nm", ""]], "table_header": ["a"] * 5,
                       "spoken": True}, role="officer", kind="contact"), lambda t: "")
    assert r.table and spoken(r)
    r.data["spoken"] = False
    assert not spoken(r)


def test_active_sonar_many_echoes_one_report():
    g, reports = _game()
    sonar = g.station(SonarRoom)
    calls = SweepCalls(sonar, "active")
    for i in range(1, 6):
        calls.add("sonar.active.echo", {"designation": f"S-{i}", "bearing": 30.0 * i, "range": 2.0 * i},
                  kind="contact", quality=Quality.SAKER)
    calls.flush(force=True)
    for _ in range(8):
        g.tick()
    said = [r for r in reports if r.type.startswith("sonar.active")]
    assert [r.type for r in said] == ["sonar.active.sweep"]
    assert said[0].text.startswith("Aktiv sonar: fem ekon. Närmast S-1, bäring 030, cirka 2,0 sjömil.")


def test_counts_are_words_with_the_right_form():
    """'Dessutom 1 civila fartyg', 'med 1 jagare som eskort' (provspel 2026-11-23)."""
    from sim.fmt import count
    from sim.phrases import PHRASES
    assert count(1, "civilt fartyg", "civila fartyg") == "ett civilt fartyg"
    assert count(3, "civilt fartyg", "civila fartyg") == "tre civila fartyg"
    assert count(1, "jagare", "jagare", neuter=False) == "en jagare"
    assert count(14, "torped", "torpeder", neuter=False) == "14 torpeder"
    text = PHRASES["plot.convoy.found"]({"members": ["S-1", "S-2"], "escorts": 1, "course": 90, "speed": 8})
    assert "med en jagare som eskort" in text


def test_a_hopeless_range_is_not_given_as_numbers():
    from sim.phrases import solution_sentence
    sol = {"quality": int(Quality.DALIG), "range_nm": 24.6, "range_sigma": 32.0, "bearing": 111,
           "course": 90, "speed": 5, "course_sigma": 90, "speed_sigma": 10}
    assert "avståndet kan vi inte säga ännu" in solution_sentence(sol)
    sol.update(range_nm=4.0, range_sigma=1.5)
    assert "någonstans mellan" in solution_sentence(sol)


def test_one_minute_is_singular():
    """'1 minuter av 10 inspelade' (Clyde-in, provspel 2026-11-23)."""
    from sim.phrases import PHRASES
    assert "en minut av 10 inspelade" in PHRASES["sonar.record.weak"]({"designation": "S-1", "minutes": 1,
                                                                       "need": 10})
    assert "3 minuter av 10" in PHRASES["sonar.record.weak"]({"designation": "S-1", "minutes": 3, "need": 10})


def test_many_contacts_heard_again_on_one_line():
    """Krig-kort: sex 'hörs igen' samma minut (under skiktet, ur döda sektorn)."""
    from sim.sonar import Detection
    g, reports = _game()
    sonar = g.station(SonarRoom)
    for i in (1, 2, 3):
        g.knowledge.on_detection(f"S-{i}", g.now)
    sonar._regained_t = g.now
    sonar._regained_batch = [("S-1", 10.0), ("S-2", 20.0), ("S-3", 30.0)]
    for _ in range(12):
        g.tick()
    said = [r for r in reports if r.type.startswith("sonar.regained")]
    assert [r.type for r in said] == ["sonar.regained.many"]
    assert said[0].text == "Kapten, sonar. S-1 (010), S-2 (020) och S-3 (030) hörs igen."


def test_radar_many_echoes_one_report():
    g, reports = _game()
    calls = SweepCalls(g.station(SonarRoom), "radar")
    for i in range(1, 5):
        calls.add("off.radar.contact", {"designation": f"S-{i}", "bearing": 30.0 * i, "range": 2.0 * i},
                  kind="contact", quality=Quality.SAKER)
    calls.flush(force=True)
    for _ in range(8):
        g.tick()
    said = [r for r in reports if r.type.startswith("off.radar")]
    assert [r.type for r in said] == ["off.radar.sweep"] and said[0].text.startswith("Radar: fyra ekon. Närmast S-1")
