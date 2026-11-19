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
