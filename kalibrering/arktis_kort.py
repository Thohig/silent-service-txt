"""Arktis kort: passiv och ja-boten.
Användning: arktis_kort.py frön förstafrö passiv,ja

Körs från repots rot: uv run python kalibrering/arktis_kort.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.game import Game
from sim.scenario import build_scenario
n = int(sys.argv[1]); s0 = int(sys.argv[2]); bots = sys.argv[3].split(",")
for bot in bots:
    wins = 0; outs = []
    for seed in range(s0, s0 + n):
        g = Game(build_scenario("arktis-kort", random.Random(seed)), seed=seed)
        t0 = g.now; fire_seen = None
        while not g.over and g.now - t0 < 2400:
            if bot == "ja" and g.active_suggestion():
                g.command("ja")
            if fire_seen is None and g.world.own.sys.fire:
                fire_seen = (g.now - t0) // 60
            g.tick()
        o = g.world.outcome["outcome"] if g.world.outcome else "?"
        wins += o == "station_reached"
        outs.append(f"{o}@{(g.now - t0) // 60}f{fire_seen}")
    print(bot, wins, "/", n, outs, flush=True)
