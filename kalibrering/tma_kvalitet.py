"""Plottets lösningar mot sanningen per kvalitet (ja-boten). Mäter hur ofta god/säker är grovt
fel (avstånd > 50 % eller kurs > 90°) och hur ofta felet är större än 3σ.
Användning: tma_kvalitet.py [scenarier] [frön] [minuter]
  t.ex. tma_kvalitet.py ovning,kuba,konvoj-kort,sundet 8 120   (~2 min)
Miljövariabeln TMA_Q sätter tma.TARGET_MANEUVER_Q för provkörningar.

Körs från repots rot: uv run python kalibrering/tma_kvalitet.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import os, random, sys
from multiprocessing import Pool
import sim.tma
from sim.scenario import build_scenario
from sim.game import Game
from sim.stations.sonar_room import SonarRoom
from sim.geo import distance, angle_diff

if os.environ.get("TMA_Q"):
    sim.tma.TARGET_MANEUVER_Q = float(os.environ["TMA_Q"])


def run(args):
    key, seed, minutes = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    sensor = g.station(SonarRoom).sensor          # bara för att para ihop beteckning och sanning
    rows, bot_t = [], 0
    for _ in range(minutes * 60):
        g.tick()
        if g.suggestion and g.suggestion[2] > bot_t:
            bot_t = g.suggestion[2]
            g.command("ja")
        if g.over:
            break
        if g.now % 20:
            continue
        o = g.world.own.state
        id_of = {sensor.designation_of(v.id): v for v in g.world.contacts}
        for tr in g.knowledge.tracks.values():
            sol, v = tr.solution, id_of.get(tr.designation)
            if sol is None or v is None or not tr.held or sol.t != g.now:
                continue
            r = distance(o.x, o.y, v.state.x, v.state.y)
            rows.append((key, int(sol.quality), abs(sol.range_nm - r) / r,
                         abs(sol.range_nm - r) / max(sol.range_sigma, 1e-6),
                         abs(angle_diff(sol.course, v.state.course))))
    return rows


if __name__ == "__main__":
    keys = (sys.argv[1] if len(sys.argv) > 1 else "ovning,kuba,konvoj-kort,sundet").split(",")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    minutes = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    with Pool() as p:
        rows = [r for rs in p.map(run, [(k, s, minutes) for k in keys for s in range(1, n + 1)])
                for r in rs]
    names = {1: "osäker", 2: "god", 3: "säker"}
    for key in keys + [None]:
        print(f"== {key or 'alla'}")
        for q in (1, 2, 3):
            x = [r for r in rows if r[1] == q and (key is None or r[0] == key)]
            if not x:
                continue
            rel = sorted(r[2] for r in x)
            print(f"  {names[q]:7s} n={len(x):5d} avståndsfel median {rel[len(rel) // 2]:.2f}"
                  f" p90 {rel[int(.9 * len(rel))]:.2f} | grovt {sum(r[2] > .5 or r[4] > 90 for r in x) / len(x):5.1%}"
                  f" | > 3σ {sum(r[3] > 3 for r in x) / len(x):5.1%} | kurs > 90° {sum(r[4] > 90 for r in x) / len(x):5.1%}")
