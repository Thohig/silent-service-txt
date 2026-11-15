"""Övningen: lyssningsövningens längd och partnerns svar per frö (ja-boten).
Användning: ovning_lyssna.py [frö ...]

Körs från repots rot: uv run python kalibrering/ovning_lyssna.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.scenario import build_scenario
from sim.game import Game
from sim.events import ReportDelivered
from sim.geo import distance

def run(seed, verbose=False):
    g = Game(build_scenario("ovning", random.Random(seed)), seed=seed)
    log = []
    g.bus.subscribe(ReportDelivered, lambda e: log.append((g.now, e.report.type, e.report.text)))
    bot_t = 0
    truth = None
    tro = __import__("sim.stations.training", fromlist=["x"])
    for _ in range(150 * 60):
        g.tick()
        to = g.station(tro.TrainingOfficer)
        if truth is None and to.done and to.done[-1][0] == "lyssna":
            skr = next(v for v in g.world.contacts if v.id == "SKR1")
            o = g.world.own.state
            truth = f"sant: {distance(o.x,o.y,skr.state.x,skr.state.y):.2f} nm, kurs {skr.state.course:.0f}, fart {skr.state.speed:.1f}"
        if g.suggestion and g.suggestion[2] > bot_t:
            bot_t = g.suggestion[2]; g.command("ja")
        if g.over: break
    ls = [(t, x) for t, ty, x in log if ty == "train.suggest.lyssna"]
    ld = [(t, x) for t, ty, x in log if ty == "train.step.done" and "Lyssning" in x]
    pr = [x for t, ty, x in log if ty == "train.partner"]
    skr = next(v for v in g.world.contacts if v.id == "SKR1")
    if verbose:
        t0 = ls[0][0] if ls else 0
        for t, ty, x in log:
            if t >= t0 - 5 and not ty.startswith("sonar.bearing"):
                print(f"{t//60:3d}:{t%60:02d} {x}")
    dur = (ld[0][0] - ls[0][0]) // 60 if ls and ld else None
    print(f"seed {seed}: {g.world.outcome['outcome'] if g.world.outcome else '-'} {g.now//60} min | "
          f"lyssning {dur} min | {pr[0][95:] if pr else '-'}")

if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or range(1, 9)
    for s in seeds:
        run(s, verbose=len(sys.argv) == 2)
