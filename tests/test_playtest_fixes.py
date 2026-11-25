"""Rättelser efter provspelet 2026-11-21: loggens bredd, telegrammens ordning, order med minustecken,
kurs mot banken, starpoms citat av kaptenens order."""
import random

import pytest

from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Report, ReportQueue
from sim.scenario import build_scenario
from sim.stations.starpom import _canon


def _game(key="kuba", seed=1):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed, warm_up=False)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, n=8):
    for _ in range(n):
        g.tick()


def test_report_log_wraps_at_its_own_width():
    from ui.widgets import ReportLog
    assert ReportLog().min_width <= 20       # RichLog bryter annars vid 78 tecken


def test_telegrams_are_delivered_in_number_order():
    q = ReportQueue()
    q.submit(Report(10, "Radio", "radio.message", {"telegram": 7}))
    q.submit(Report(8, "Radio", "radio.message", {"telegram": 8}))
    assert [r.data["telegram"] for r in q.due(20)] == [7, 8]


def test_negative_values_get_an_explanation():
    g, reports = _game()
    for order in ("kurs -10", "fart -3", "djup -5"):
        g.command(order)
    _run(g)
    texts = [r.text for r in reports if r.type == "order.unknown"]
    assert len(texts) == 3
    for word in ("000–359", "back 3", "ytläge"):
        assert any(word in t for t in texts), (word, texts)


def test_course_to_the_bank_uses_the_chart():
    for key in ("jagad", "kuba"):
        g, reports = _game(key, 5)
        g.command("kurs mot banken")
        _run(g)
        r = next(r for r in reports if r.type.startswith("nav.steer"))
        assert r.type in ("nav.steer.bank", "nav.steer.bank_here"), r.text
        if r.type == "nav.steer.bank":
            assert g.world.own.state.ordered_course == r.data["course"]
            assert 60 <= r.data["depth"] <= 250


def test_unknown_place_has_no_trailing_space():
    g, reports = _game("sundet", 3)
    g.command("kurs mot månen")
    _run(g)
    r = next(r for r in reports if r.type == "nav.steer.none")
    assert r.text == r.text.strip() and "Ankarplatsen" in r.text


def test_starpom_quotes_courses_with_three_digits():
    assert _canon("kurs 0") == "kurs 000"
    assert _canon("Kurs  45") == "kurs 045"
    assert _canon("fart 5") == "fart 5"


# --- steg 2: sjunkna kontakter, stabens telegram ---------------------------------------
from sim.dispatch import ReportedContact, ReportedConvoy, SentReport  # noqa: E402
from sim.events import EventBus, ReportTransmitted  # noqa: E402
from sim.headquarters import Headquarters  # noqa: E402
from sim.reports import Quality  # noqa: E402
from sim.sonar import TransientHeard  # noqa: E402
from sim.stations.sonar_room import SonarRoom  # noqa: E402


def _report(hq_bus, n=1):
    dd = ReportedContact("S-2", "jagare, ångturbiner, två axlar", 1.0, 2.0, 90.0, 15.0, Quality.GOD, 0)
    cv = ReportedConvoy(3.0, 4.0, 200.0, 12.0, Quality.OSAKER, 5, 2)
    hq_bus.publish(ReportTransmitted(10, SentReport(10, "full", (0.0, 0.0, 0.3), (dd,), cv,
                                                    ("hunted",), number=n)))


def test_staff_at_war_does_not_forbid_attacks_or_ask_to_follow():
    bus = EventBus()
    hq = Headquarters(at_war=True)
    hq.attach(bus)
    _report(bus)
    out = hq.outgoing() + hq.outgoing()
    assert not any("ANGRIP EJ" in t or "FÖLJ KONVOJEN" in t for t in out)
    assert out[0].endswith("MOTTAGEN.") and not hq.expects_report


def test_recall_leaves_only_the_receipts():
    bus = EventBus()
    hq = Headquarters()
    hq.attach(bus)
    _report(bus)
    hq.read_order({"tasks": ("ut",), "recalled": True})
    assert hq.outgoing() == ["FRÅN HUVUDSTABEN. ER RAPPORT NR 1 MOTTAGEN."]
    assert not hq.expects_report
    _report(bus, 2)
    assert hq.outgoing() == ["FRÅN HUVUDSTABEN. ER RAPPORT NR 2 MOTTAGEN."]


def test_a_sunk_contact_is_no_threat_and_its_pinger_is_forgotten():
    g, reports = _game("kuba", 1)
    g.knowledge.on_detection("S-2", 0)
    sonar = g.station(SonarRoom)
    sonar._on_sound(TransientHeard("ping", 40.0, 80.0, "S-2"))
    assert "S-2" in sonar._pings
    sonar._on_sound(TransientHeard("breakup", 40.0, 60.0, "S-2"))
    tr = g.knowledge.tracks["S-2"]
    assert tr.sunk and not tr.held and not tr.threat
    assert "S-2" not in sonar._pings


# --- steg 3: förslagen under jakt ---------------------------------------------------------
from sim.stations.engineering import EngineeringStation  # noqa: E402


def test_sprint_accepts_a_deeper_ordered_depth():
    g, _ = _game("kuba", 2)
    eng = g.station(EngineeringStation)
    st, s = g.world.own.state, g.world.own.sys
    s.propulsion = "turbine"
    st.ordered_depth, st.ordered_speed = 280, 5
    order, data = eng._sprint()
    assert "djup" not in order and data["depth"] == 280      # förut "djup 220" tillbaka upp
    st.ordered_speed = data["speed"]
    assert eng._sprint() is None
    st.ordered_depth = 60
    assert eng._sprint()[0].startswith("djup 220")


def test_no_new_sprint_when_we_already_run_fast_on_the_turbine():
    """Krig-kort frö 31: sprint 13 knop på 220, sonar bytte till 280, maskin föreslog fart 16 och sa
    'smygandet hjälper inte nu' fast vi redan sprang (åtta gånger på 90 min)."""
    g, _ = _game("kuba", 2)
    eng = g.station(EngineeringStation)
    st, s = g.world.own.state, g.world.own.sys
    s.propulsion = "turbine"
    st.ordered_depth, st.ordered_speed = 280, 13
    assert eng._sprint() is None
    st.ordered_speed = 6
    assert eng._sprint() is not None


def test_attack_slow_says_what_going_up_costs_when_they_have_us():
    from sim.phrases import PHRASES
    d = {"slow": True, "fire_depth": 90, "max_depth": 100}
    assert "De har oss" not in PHRASES["nav.suggest.attack_slow"](d)
    assert "De har oss" in PHRASES["nav.suggest.attack_slow"]({**d, "hunted": True})


def test_evasive_depth_names_its_cause_and_stays_under_the_layer():
    g, reports = _game("kuba", 2)
    sonar = g.station(SonarRoom)
    st = g.world.own.state
    st.ordered_depth, st.ordered_speed = 200, 4
    d = sonar._evasive_target()
    assert d >= g.world.env.layer_depth + 60
    sonar._evasive_depth(cause="charges")
    _run(g, 10)
    r = next(r for r in reports if r.type == "sonar.suggest.depth_change")
    assert r.text.startswith("Kapten, sonar.") and "laddningarna" in r.text


def test_underwater_telephone_is_reported_ever_more_seldom():
    g, reports = _game("kuba", 2)
    sonar = g.station(SonarRoom)
    for _ in range(40 * 60):
        if g.now % 180 == 0:
            sonar._on_sound(TransientHeard("uwt", 40.0, 30.0, None))
        g.tick()
    said = [r for r in reports if r.type == "sonar.uwt"]
    assert 3 <= len(said) <= 6                 # var 3:e min i 40 min gav 14 förut
    assert not said[0].data["again"] and said[1].data["again"]


def test_a_near_pinger_sweeping_past_stays_one_pinger():
    g, reports = _game("kuba", 2)
    g.world.ais.clear()                         # bara vår pingare
    sonar = g.station(SonarRoom)
    b = 245.0
    for i in range(10):
        sonar._on_sound(TransientHeard("ping", b, 80.0, None, 150.0))
        b += 9.0
        for _ in range(10):
            g.tick()
    assert len([r for r in reports if r.type == "sonar.ping.first"]) == 1


# --- steg 4: order som bryter mot uppdraget -------------------------------------------------
def test_blowing_without_reason_is_asked_once():
    g, reports = _game("jagad", 3)
    g.command("nödblåsning")
    _run(g)
    assert any(r.type == "eng.blow_confirm" for r in reports) and not g.world.own.sys.blowing
    g.command("nödblåsning")
    _run(g)
    assert g.world.own.sys.blowing


def test_surfacing_near_a_plotted_enemy_is_asked_but_not_an_accepted_suggestion():
    g = Game(build_scenario("kuba-kort", random.Random(1)), seed=1)   # vakten har plottat jagaren
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.command("ytläge")
    _run(g)
    assert any(r.type == "nav.surface_confirm" for r in reports)
    assert g.world.own.state.ordered_depth > 0
    g.suggestion = ("ytläge", "test", g.now)     # besättningens förslag: kaptenen säger ja
    g.command("ja")
    _run(g)
    assert g.world.own.state.ordered_depth == 0


def test_surfacing_with_an_unranged_warship_before_a_ranged_one_does_not_crash():
    """krig-kort frö 71 (kaosboten): ett örlogsfartyg utan lösning först i plottet, sedan ett hot med
    lösning; ytläge jämförde avståndet med None."""
    from types import SimpleNamespace as NS
    from sim.reports import Quality
    from sim.stations.navigation import NavigationStation
    g = Game(build_scenario("kuba-kort", random.Random(1)), seed=1)
    nav = g.station(NavigationStation)
    unranged = NS(threat=True, solution=None, warship=True, designation="S-1", classification="jagare")
    ranged = NS(threat=True, warship=True, designation="S-2", classification="jagare",
                solution=NS(quality=Quality.GOD, range_nm=1.5))
    g.knowledge.tracks = {"S-1": unranged, "S-2": ranged}
    near = nav._threat_near()
    assert near["designation"] == "S-2" and near["range"] == 1.5


def test_surfaced_in_sight_of_the_enemy_gives_a_moment_to_dive():
    from sim.world import SURFACE_GRACE_S
    g, _ = _game("kuba-kort", 1)
    w = g.world
    w.own.state.depth = 0
    w.own.state.order_depth(0)
    ai = w.ais[0]
    ai.vessel.state.x, ai.vessel.state.y = w.own.state.x + 2, w.own.state.y
    for _ in range(SURFACE_GRACE_S - 5):
        w.tick()
    assert w.outcome is None
    for _ in range(10):
        w.tick()
    assert w.outcome["outcome"] == "forced"


# --- steg 5: radarvarnaren, skott på för kort håll ------------------------------------------
def test_firing_inside_the_arming_distance_is_asked_once():
    from sim.stations.torpedo_room import TorpedoRoom
    g = Game(build_scenario("kuba-kort", random.Random(1)), seed=1)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    torp = g.station(TorpedoRoom)
    tr = g.knowledge.tracks["S-1"]
    tr.classification, tr.class_quality = "jagare, ångturbiner, två axlar", Quality.SAKER
    torp._aim = lambda sol, load: (90.0, 30.0, 0.2)      # träffpunkten 0,2 nm bort
    torp._solution_for = lambda d: (tr, tr.solution or object())
    g.world.own.state.ordered_speed = g.world.own.state.speed = 3
    g.command("eld tub 1 mot S-1")
    _run(g)
    assert any(r.type == "torp.too_close" for r in reports) and not torp.in_water
    g.command("eld tub 1 mot S-1")
    _run(g)
    assert torp.in_water


@pytest.mark.slow
def test_radar_warner_does_not_repeat_known_radars():
    from sim.stations.officer import ESM_REPEAT_S
    g, reports = _game("clyde", 29)
    st = g.world.own.state
    st.depth = st.ordered_depth = 17
    for _ in range(ESM_REPEAT_S - 60):
        g.tick()
    first = [r for r in reports if r.type == "off.esm"]
    assert first and len(first) <= 4            # var 10:e min förut: 3 radarstationer × 3
    st.depth = st.ordered_depth = 40
    _run(g, 30)
    st.depth = st.ordered_depth = 17
    _run(g, 30)
    assert any(r.type == "off.esm.same" for r in reports)


def test_no_settling_under_attack_and_lift_off_when_bombed_on_the_bottom():
    from sim.events import ChargeHeard
    from sim.stations.navigation import NavigationStation
    g, reports = _game("jagad", 5)
    k = g.knowledge
    g.bus.publish(ChargeHeard(g.now, True, Quality.GOD, True, "sonar", 90.0))
    assert k.charged_close(g.now)
    assert g.station(NavigationStation)._settle_proposal() is None
    s = g.world.own.sys
    s.on_bottom = True
    g.world.own.state.speed = g.world.own.state.ordered_speed = 0
    order, data = g.station(EngineeringStation)._sprint(lift=True)
    assert "fart" in order and "turbin" in order
    # reaktorn snabbstoppad av tryckvågen: lätta ändå, på elmotorn (krig frö 4 låg kvar och sänktes)
    s.reactor = "scram"
    s.propulsion = "electric"
    assert not g.world.own.power
    order, data = g.station(EngineeringStation)._sprint(lift=True)
    assert "turbin" not in order and data["electric"] and 2 <= data["speed"] <= g.world.own.max_speed()
    s.on_bottom = False
    assert g.station(EngineeringStation)._sprint() is None      # utan botten: ingen sprint på batteriet


def test_cavitation_advice_uses_the_depth_we_are_going_to():
    g, _ = _game("kuba", 2)
    eng = g.station(EngineeringStation)
    st = g.world.own.state
    st.depth, st.ordered_depth = 200.0, 90.0
    st.speed = st.ordered_speed = 16.0
    order, data = eng._cavitation_advice()
    assert data["speed"] == 9 and order == "fart 9"


def test_creep_is_not_suggested_once_they_have_us():
    g, _ = _game("kuba", 2)
    eng = g.station(EngineeringStation)
    assert not eng.vetoes("smygmotor")
    g.knowledge.hunt_t = g.now
    assert eng.vetoes("smygmotor")
    assert not eng.vetoes("skenmål, kurs 090, smygmotor, fart 4, djup 130")


def test_attack_lost_says_why():
    from sim.phrases import PHRASES
    f = PHRASES["nav.attack.lost"]
    assert "tappat S-2" in f({"designation": "S-2", "why": "lost"})
    assert "för osäker" in f({"designation": "S-2", "why": "poor"})
    assert "för gammal" in f({"designation": "S-2", "why": "old"})
