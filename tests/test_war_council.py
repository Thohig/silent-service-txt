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
