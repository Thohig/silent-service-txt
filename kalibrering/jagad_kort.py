"""Jagade kort: passiv, ja-boten och djupt-och-fort (fast).
Användning: jagad_kort.py [nyckel=jagad-kort] [frön=8] [passiv,ja,fast]

Körs från repots rot: uv run python kalibrering/jagad_kort.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.game import Game
from sim.scenario import build_scenario
from sim.events import ReportDelivered
from sim.stations.navigation import NavigationStation

KEY = sys.argv[1] if len(sys.argv) > 1 else "jagad-kort"
SEEDS = range(int(sys.argv[2]) if len(sys.argv) > 2 else 8)


def run(seed, bot):
    g = Game(build_scenario(KEY, random.Random(seed)), seed=seed)
    first = None
    sugs = []
    def on(ev):
        nonlocal first
        if first is None and ev.report.type.startswith("sonar"):
            first = g.now
        if ev.report.kind == "suggest":
            sugs.append((g.now, ev.report.type))
    g.bus.subscribe(ReportDelivered, on)
    nav = g.station(NavigationStation)
    t0 = g.now
    while not g.over and g.now - t0 < (int(__import__("os").environ.get("CAP", 12000))):
        if bot == "ja" and g.active_suggestion():
            g.command("ja")
        if bot == "fast" and (g.now - t0) % 60 == 0:
            r = nav.exit_route()
            if r:
                g.command(f"turbin, djup 200, fart 12, kurs {int(r[0]):03d}")
        g.tick()
    w = g.world
    out = w.outcome["outcome"] if w.outcome else "?"
    return out, (g.now - t0) // 60, first, w.mission.get("enemy_contacts", 0), round(w.own.sys.hull, 2), sugs[:3]


for bot in (sys.argv[3].split(",") if len(sys.argv) > 3 else ("passiv", "ja", "fast")):
    res = [run(s, bot) for s in SEEDS]
    wins = sum(r[0] == "escaped" for r in res)
    print(f"{bot}: {wins}/{len(res)}")
    for s, r in zip(SEEDS, res):
        print("  ", s, r)
