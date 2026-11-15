"""Ja-boten (svarar ja 20 s efter varje förslag) över frön och scenarier.
Användning: ja_bot.py ovning,konvoj-kort [frön]

Körs från repots rot: uv run python kalibrering/ja_bot.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys, time
from concurrent.futures import ProcessPoolExecutor
from sim.game import Game
from sim.events import ReportDelivered
from sim.scenario import build_scenario

def run(args):
    key, seed = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    due = []
    looks = [0]
    def on(e):
        if e.report.kind == "suggest":
            due.append(g.now + 20)
        if e.report.type.startswith("off.periscope"):
            looks[0] += 1
    g.bus.subscribe(ReportDelivered, on)
    for _ in range(4 * 3600):
        if g.over:
            break
        g.tick()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
    return key, seed, (g.world.outcome or {}).get("outcome"), g.now // 60, looks[0]

if __name__ == "__main__":
    keys = sys.argv[1].split(",")
    seeds = range(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    t0 = time.time()
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(run, [(k, s) for k in keys for s in seeds]))
    for k in keys:
        rows = [r for r in res if r[0] == k]
        outs = {}
        for r in rows:
            outs[r[2]] = outs.get(r[2], 0) + 1
        print(k, outs)
        print("   ", [(r[1], r[2], r[3], r[4]) for r in rows])
    print(f"{time.time()-t0:.0f} s")
