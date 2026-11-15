"""Kvadrat 7 kort: passiv och ja-boten.
Användning: kuba_kort.py frön förstafrö passiv,ja

Körs från repots rot: uv run python kalibrering/kuba_kort.py …
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
        g = Game(build_scenario("kuba-kort", random.Random(seed)), seed=seed)
        t0 = g.now; hunted_at_ho = g.knowledge.hunted(g.now)
        while not g.over and g.now - t0 < 4000:
            if bot == "ja" and g.active_suggestion():
                g.command("ja")
            g.tick()
        o = g.world.outcome["outcome"] if g.world.outcome else "?"
        wins += o == "reported"
        outs.append(f"{o}@{(g.now - t0) // 60}{'H' if hunted_at_ho else ''}{'R' if g.world.mission.get('last_report_t') else ''}")
    print(bot, wins, "/", n, outs, flush=True)
