"""Långvågen (L1–L4): hur ja-boten tar emot vid sambandstillfällena.
Användning: langvag.py kuba,jagad,konvoj [frön]

Räknar per scenario radiogram mottagna med masten och på långvåg, stympade mottagningar och
missade sambandstillfällen, och utfallen.

Körs från repots rot: uv run python kalibrering/langvag.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario


def run(args):
    key, seed = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    due: list[int] = []
    n = Counter()

    def on(e):
        r = e.report
        if r.kind == "suggest":
            due.append(g.now + 20)
        if r.type == "radio.message":
            n[r.data.get("via", "mast")] += 1
        elif r.type in ("radio.garbled", "radio.missed"):
            n[r.type.split(".")[1]] += 1
    g.bus.subscribe(ReportDelivered, on)
    for _ in range(8 * 3600):
        if g.over:
            break
        g.tick()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
    return key, seed, (g.world.outcome or {}).get("outcome"), n


if __name__ == "__main__":
    keys = sys.argv[1].split(",")
    seeds = range(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    t0 = time.time()
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(run, [(k, s) for k in keys for s in seeds]))
    for key in keys:
        total, outs = Counter(), Counter()
        for k, seed, out, n in rows:
            if k == key:
                total.update(n)
                outs[out] += 1
                print(f"  {key:12} frö {seed}: {out:16} mast {n['mast']}, långvåg {n['vlf']}, "
                      f"stympat {n['garbled']}, missat {n['missed']}")
        print(f"{key:12} mast {total['mast']}, långvåg {total['vlf']}, stympat {total['garbled']}, "
              f"missat {total['missed']}; {dict(outs)}")
    print(f"{time.time() - t0:.0f} s")
