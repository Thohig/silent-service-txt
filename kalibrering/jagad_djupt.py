"""Djupt och fort i Jagade: turbin 12 kn, 200 m, kurs enligt navigatörens väg ut.
Användning: jagad_djupt.py [frön] [starttid] [--varje-minut (vilket tredje argument som helst)]

Körs från repots rot: uv run python kalibrering/jagad_djupt.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.navigation import NavigationStation
n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
wins, outs = 0, []
for seed in range(n):
    g = Game(build_scenario("jagad", random.Random(seed)), seed=seed)
    nav = g.station(NavigationStation)
    while not g.over and g.now < 7200:
        if g.now == (int(sys.argv[2]) if len(sys.argv) > 2 else 0) or (len(sys.argv) > 3 and g.now % 60 == 0):
            r = nav.exit_route()
            if r:
                g.command(f"turbin, djup 200, fart 12, kurs {int(r[0]):03d}")
        sug = g.active_suggestion()
        if sug and sug[0].startswith('djup'):
            g.command('ja')
        g.tick()
    o = g.world.outcome["outcome"] if g.world.outcome else "?"
    wins += o == "escaped"
    outs.append(f"{o}@{g.now // 60}")
print("fast", wins, "/", n, outs, flush=True)
