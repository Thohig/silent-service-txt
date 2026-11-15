"""Övningen: ja-bot som också skjuter övningstorpeden när lösningen är god.
Användning: ovning_torped.py ovning|ovning-kort [frö ...]

Körs från repots rot: uv run python kalibrering/ovning_torped.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.scenario import build_scenario
from sim.game import Game
from sim.events import ReportDelivered

def run(key, seed, fire=True, verbose=False, minutes=150):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    log = []
    pending = []
    def on(e):
        r = e.report
        log.append((g.now, r.type, r.text))
        if fire and r.type == "train.torpedo.brief" and r.data.get("good") and r.data.get("tubes"):
            pending.append(f"eld tub {r.data['tubes'][0]} mot {r.data['designation']}")
    g.bus.subscribe(ReportDelivered, on)
    bot_t, t0 = 0, g.now
    first = None
    for _ in range(minutes * 60):
        g.tick()
        while pending:
            c = pending.pop(); g.command(c); g.command(c)   # bekräftelse vid behov
        if g.suggestion and g.suggestion[2] > bot_t:
            bot_t = g.suggestion[2]; g.command("ja")
            first = first if first is not None else g.now - t0
        if g.over: break
    if verbose:
        for t, ty, x in log:
            if ty.startswith(("train", "torp")):
                print(f"{t//60:3d}:{t%60:02d} {x}")
    res = [x for t, ty, x in log if ty == "train.torpedo.result"]
    out = g.world.outcome["outcome"] if g.world.outcome else "-"
    print(f"{key} seed {seed}: {out} {(g.now - t0)//60} min, första förslag {first}s | "
          f"{res[0][60:] if res else '-'}")

if __name__ == "__main__":
    key = sys.argv[1]
    seeds = [int(a) for a in sys.argv[2:]] or range(1, 9)
    for s in seeds:
        run(key, s, verbose=len(sys.argv) == 3)
