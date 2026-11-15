"""Konvojboten: ja på förslag, salva mot klassad transport/tanker ≤ 3 nm med lösning ≥ osäker.
Användning: konvoj_salva.py konvoj|konvoj-kort frön

Körs från repots rot: uv run python kalibrering/konvoj_salva.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.game import Game
from sim.scenario import build_scenario
from sim.reports import Quality
from sim.stations.officer import is_big_ship
key = sys.argv[1]; n = int(sys.argv[2])
res = []
for seed in range(n):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    t0 = g.now; first_sink = None
    while not g.over and g.now - t0 < 4 * 3600:
        if g.active_suggestion(): g.command("ja")
        if g.now % 10 == 0 and g.world.own.state.depth <= 60:
            for tr in list(g.knowledge.tracks.values()):
                if not tr.held or not is_big_ship(tr) or tr.class_quality < Quality.GOD: continue
                sol = g.knowledge.resolve(tr.designation, g.now, g.own_position_estimate())
                if sol and sol.quality >= Quality.OSAKER and sol.range_nm <= 3.0:
                    g.command(f"salva {tr.designation}"); g.command(f"salva {tr.designation}")
                    break
        g.tick()
        if first_sink is None and any(v.sunk for v in g.world.contacts if v.id.startswith("K")):
            first_sink = (g.now - t0) // 60
    sunk = [v.id for v in g.world.contacts if v.sunk]
    res.append((seed, g.world.outcome and g.world.outcome["outcome"], sunk, first_sink))
    print(res[-1], flush=True)
print(key, "sänkt minst ett:", sum(1 for r in res if any(s.startswith("K") for s in r[2])), "av", n)
