"""Arktis: ja-boten, hur många frön når Nord-7.
Användning: arktis.py förstafrö frön

Körs från repots rot: uv run python kalibrering/arktis.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.game import Game
from sim.scenario import build_scenario
s0, n = int(sys.argv[1]), int(sys.argv[2]); outs = []
for seed in range(s0, s0 + n):
    g = Game(build_scenario("arktis", random.Random(seed)), seed=seed)
    while not g.over and g.now < 6 * 3600:
        if g.active_suggestion(): g.command("ja")
        g.tick()
    outs.append(g.world.outcome["outcome"] if g.world.outcome else "?")
print(sum(o == "station_reached" for o in outs), "/", n, outs, flush=True)
