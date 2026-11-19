"""Kärnvapenbeslutet (KV1–KV7): ordern som kunskap, bombernas klassning, krigsbedömningen,
rådet med tre nycklar och slutet."""
import random

from sim.events import NuclearOrderRead
from sim.game import Game
from sim.scenario import build_scenario


def _game(key, seed=1):
    return Game(build_scenario(key, random.Random(seed)), seed=seed, warm_up=False)


# --- KV1: ordern om kärnladdningen som kunskap ----------------------------------------
def test_the_order_is_read_at_start_per_scenario():
    want = {"kuba": ("order_only", False), "jagad": ("order_only", False),
            "konvoj": ("forbidden", True), "duell": ("forbidden", True),
            "ovning": ("forbidden", False), "arktis": ("order_only", False)}
    for key, (nuclear, war) in want.items():
        g = _game(key)
        g.tick()
        k = g.knowledge
        assert k.nuclear_order()[0] == nuclear, key
        assert k.at_war()[0] == war, key


def test_telegram_changes_the_order_and_the_latest_counts():
    from sim.stations.radio import RadioStation
    g = _game("jagad")
    seen = []
    g.bus.subscribe(NuclearOrderRead, seen.append)
    g.tick()
    g.station(RadioStation)._deliver(10)          # båda telegrammen tas emot
    assert g.knowledge.nuclear_order()[0] == "conditional"
    assert seen[-1].source.startswith("telegram")


# --- KV2: bombernas klassning ur datan -------------------------------------------------
from sim import acoustics  # noqa: E402
from sim.entities import Transient  # noqa: E402
from sim.events import ChargeHeard  # noqa: E402
from sim.reports import Quality  # noqa: E402


def _quiet_kuba(seed):
    g = _game("kuba", seed)
    w = g.world
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    for ai in w.ais:
        ai.can_force = False
    heard = []
    g.bus.subscribe(ChargeHeard, heard.append)
    g.tick()
    return g, heard


def _boom(g, dx, dy, practice, depth=50.0):
    st = g.world.own.state
    lvl = acoustics.EXPLOSION_PRACTICE if practice else acoustics.EXPLOSION_REAL
    g.world.emit(Transient("explosion", st.x + dx, st.y + dy, depth, lvl, "DD1", g.now,
                           practice=practice))
    for _ in range(3):
        g.tick()


def test_close_real_charge_is_known_real_for_sure():
    for seed in range(4):
        g, heard = _quiet_kuba(seed)
        _boom(g, 0.0, 0.3, practice=False)
        h = [c for c in heard if c.source == "sonar"]
        assert h and h[-1].real and h[-1].quality == Quality.SAKER


def test_signal_charges_and_distant_real_ones_sound_alike_without_a_range():
    for seed in range(4):
        g, heard = _quiet_kuba(seed)
        _boom(g, 0.0, 0.15, practice=True)
        near_signal = [c for c in heard if c.source == "sonar"][-1]
        _boom(g, 0.0, 3.0, practice=False)
        far_real = [c for c in heard if c.source == "sonar"][-1]
        assert not near_signal.real and not far_real.real
        assert near_signal.quality == far_real.quality == Quality.OSAKER


def test_no_charge_is_called_wrong_with_certainty_over_seeds():
    import random as _r
    wrong_sure = 0
    for seed in range(8):
        g, heard = _quiet_kuba(seed)
        rng = _r.Random(seed)
        for _ in range(6):
            practice = rng.random() < 0.5
            r = rng.uniform(0.05, 4.0)
            n0 = len(heard)
            _boom(g, 0.0, r, practice)
            for c in heard[n0:]:
                if c.source == "sonar" and c.quality == Quality.SAKER and c.real == practice:
                    wrong_sure += 1
    assert wrong_sure == 0


def test_machine_feels_real_charges_close_and_small_ones():
    g, heard = _quiet_kuba(1)
    g.world.own.apply_explosion(100, practice=False, rng=g.world.rng)
    for _ in range(20):
        g.tick()
    g.world.own.apply_explosion(50, practice=True, rng=g.world.rng)
    for _ in range(20):
        g.tick()
    felt = [c for c in heard if c.source == "maskin"]
    assert any(c.real and c.quality == Quality.SAKER and c.near for c in felt)
    assert any(not c.real for c in felt)
    assert g.knowledge.charges == heard


# --- KV3: krigsbedömningen -------------------------------------------------------------
from sim.war import assess, starpom_vote, zampolit_vote  # noqa: E402


def _k_with(order="order_only", charges=(), war=False, now=1000):
    from sim.knowledge import Knowledge
    k = Knowledge()
    k.nuclear_orders.append((0, order, war, "ordern"))
    for t, real, q, near in charges:
        k.charges.append(ChargeHeard(t, real, q, near, "sonar"))
    return k


def test_forbidden_is_never_lifted():
    k = _k_with("forbidden", [(990, True, Quality.SAKER, True)])
    a = assess(k, 1000)
    assert a.attacked and not zampolit_vote(a).yes and not starpom_vote(a).yes


def test_signal_charges_are_no_attack():
    k = _k_with(charges=[(990, False, Quality.GOD, True)])
    a = assess(k, 1000)
    assert not a.attacked and a.signal_only
    assert not zampolit_vote(a).yes and not starpom_vote(a).yes


def test_real_attack_but_uncertain_splits_the_officers_and_starpom_suggests_away():
    k = _k_with(charges=[(990, True, Quality.GOD, True)])
    a = assess(k, 1000)
    assert a.attacked and a.attacked_q == Quality.GOD
    z, s = zampolit_vote(a), starpom_vote(a)
    assert z.yes and not s.yes and s.suggest == "djup 150"


def test_sure_attack_starpom_wants_to_ask_staff_unless_cut_off():
    k = _k_with(charges=[(100, True, Quality.SAKER, True)])
    a = assess(k, 1000)                       # angreppet 15 min sedan: vi kan gå upp
    assert a.reach_staff and starpom_vote(a).why == "ask_staff"
    k = _k_with(charges=[(990, True, Quality.SAKER, True)])
    a = assess(k, 1000)                       # nyss: vi kan inte
    assert not a.reach_staff and starpom_vote(a).yes and zampolit_vote(a).yes


def test_conditional_order_counts_charges_after_the_telegram():
    from sim.knowledge import Knowledge
    k = Knowledge()
    k.nuclear_orders.append((0, "order_only", False, "ordern"))
    k.charges.append(ChargeHeard(500, True, Quality.SAKER, True, "maskin"))
    k.nuclear_orders.append((600, "conditional", None, "telegram 2"))
    a = assess(k, 700)
    assert a.order == "conditional" and not a.attacked
    k.charges.append(ChargeHeard(650, True, Quality.SAKER, True, "maskin"))
    a = assess(k, 700)
    assert a.attacked and zampolit_vote(a).yes and starpom_vote(a).yes


def test_old_charges_do_not_count():
    k = _k_with(charges=[(0, True, Quality.SAKER, True)], now=5000)
    assert not assess(k, 5000).attacked


# --- KV4: zampoliten och rådet ---------------------------------------------------------
from sim.events import ReportDelivered  # noqa: E402
from sim.stations.council import AGAIN_S, ARM_S, GATHER_S, NuclearCouncil  # noqa: E402
from sim.stations.torpedo_room import TorpedoRoom  # noqa: E402


def _council_game(key="kuba", seed=1):
    g = _game(key, seed)
    w = g.world
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    for ai in w.ais:
        ai.can_force = False
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.station(TorpedoRoom).tubes[0].load = "T-5"
    g.tick()
    return g, reports


def _hold(g, reports):
    n = len(reports)
    g.command("kärnvapenråd")
    for _ in range(GATHER_S + 20):
        g.tick()
    return [r for r in reports[n:] if r.type.startswith("council.")]


def _types(rs):
    return [r.type for r in rs]


def test_no_order_and_no_attack_both_refuse_and_starpom_suggests_another_way():
    g, reports = _council_game()
    rs = _hold(g, reports)
    assert {"council.zampolit", "council.starpom", "council.refused"} <= set(_types(rs))
    z = next(r for r in rs if r.type == "council.zampolit")
    s = next(r for r in rs if r.type == "council.starpom")
    assert not z.data["yes"] and not s.data["yes"]
    assert z.speaker == "Zampolit (Gromov)" and s.role == "starpom"
    assert not g.station(NuclearCouncil).armed()
    for _ in range(30):
        g.tick()
    sug = [r for r in reports if r.kind == "suggest" and r.type == "council.suggest"]
    assert sug and "skjut" not in sug[-1].data["order"] and "salva" not in sug[-1].data["order"]


def test_sure_attack_cut_off_turns_all_keys_for_a_while():
    g, reports = _council_game()
    k = g.knowledge
    for i in range(3):
        k.charges.append(ChargeHeard(g.now - i, True, Quality.SAKER, True, "maskin"))
    rs = _hold(g, reports)
    assert "council.keys" in _types(rs)
    c = g.station(NuclearCouncil)
    assert c.armed()
    for _ in range(ARM_S + 5):
        g.tick()
    assert not c.armed()
    assert "council.expired" in [r.type for r in reports]


def test_council_is_not_held_again_unchanged_but_is_when_things_change():
    g, reports = _council_game()
    _hold(g, reports)
    rs = _hold(g, reports)
    assert _types(rs) == ["council.again"]
    g.knowledge.charges.append(ChargeHeard(g.now, False, Quality.GOD, True, "sonar"))
    rs = _hold(g, reports)
    assert "council.zampolit" in _types(rs)
    for _ in range(AGAIN_S):
        g.tick()
    rs = _hold(g, reports)
    assert "council.zampolit" in _types(rs)


def test_forbidden_order_in_the_convoy():
    g, reports = _council_game("konvoj")
    for i in range(3):
        g.knowledge.charges.append(ChargeHeard(g.now - i, True, Quality.SAKER, True, "maskin"))
    rs = _hold(g, reports)
    assert "council.refused" in _types(rs)
    assert all(not r.data["yes"] for r in rs if r.type in ("council.zampolit", "council.starpom"))


def test_council_speech_is_cyrillic():
    g, reports = _council_game()
    for r in _hold(g, reports):
        assert r.speech and not any("a" <= ch.lower() <= "z" for ch in r.speech), r.type


# --- KV6: slutet och slutrapporten -----------------------------------------------------
def test_council_is_noted_with_the_truth_for_the_final_report():
    from sim.goals import council_summary
    g, reports = _council_game()
    st = g.world.own.state
    g.world.mission.setdefault("charge_log", []).extend([(g.now, True, 150), (g.now, False, 5000)])
    _hold(g, reports)
    c = council_summary(g.world)
    assert len(c) == 1 and c[0]["signal_near"] == 1 and c[0]["real_near"] == 0
    assert c[0]["zampolit"] is False and c[0]["clock"]
    from ui.widgets import council_rows
    rows = council_rows(c)
    assert "1 av 3 nycklar" in rows[0][1] and "1 signalladdningar" in rows[0][1]


def test_nuclear_detonation_ends_the_game_as_nuclear():
    from sim.events import GameEnded
    g, reports = _council_game()
    ended = []
    g.bus.subscribe(GameEnded, ended.append)
    g.world.mission["nuclear_used"] = True
    g.world.mission["nuclear_t"] = g.now
    for _ in range(40):
        g.tick()
        if g.over:
            break
    assert ended and ended[0].outcome == "nuclear"
    assert ended[0].summary["nuclear"] and "kärnladdning" in ended[0].summary["text"]
