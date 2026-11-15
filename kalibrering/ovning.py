"""Övningen: ja-boten, utfall, grundstötning, närmaste fartyg, bestickfel.
Användning: ovning.py [frö ...] (ett frö ⇒ hela loggen)

Körs från repots rot: uv run python kalibrering/ovning.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.scenario import build_scenario
from sim.game import Game
from sim.events import ReportDelivered
from sim.geo import distance

def run(seed, verbose=False, bot=True):
    sc = build_scenario("ovning", random.Random(seed))
    g = Game(sc, seed=seed)
    fj = g.world.env.seabed.features[0]
    log = []
    g.bus.subscribe(ReportDelivered, lambda e: log.append((g.now, e.report.text)))
    bot_t = 0
    mind = 99
    grounded = False
    for i in range(3 * 3600):
        g.tick()
        o = g.world.own
        for v in g.world.neutral_ships:
            mind = min(mind, distance(o.state.x, o.state.y, v.state.x, v.state.y))
        if o.sys.bottom_contact:
            grounded = True
        if bot and g.suggestion and g.suggestion[2] > bot_t:
            bot_t = g.suggestion[2]
            g.command("ja")
        if g.over:
            break
    if verbose:
        for t, txt in log:
            print(f"{t//60:3d}:{t%60:02d} {txt}")
    out = g.world.outcome
    nav = g.stations[0]
    print(f"seed {seed}: {out['outcome'] if out else '-'} t={g.now//60} min, grund={grounded}, "
          f"närmast fartyg {mind:.2f} nm, skrov {o.sys.hull:.2f}, "
          f"bestickfel {distance(nav.est_x, nav.est_y, o.state.x, o.state.y):.2f}, "
          f"rapporter {len(log)}")

if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or range(1, 9)
    for s in seeds:
        run(s, verbose=len(sys.argv) == 2)
