"""Provskjutning i ytläge mot ett stillaliggande mål: torpedtyperna jämförda.

Egen ubåt i ytläge, stilla, ingen annan trafik. Jagaren ligger still (fart 0, men driver med
strömmen som allt annat) på 1–6 nm i en slumpad bäring. Radarn sveper varje minut i 10 minuter
och bryggan tittar; plottet bygger lösningen av det. Sedan skjuter kaptenen `eld tub 1 mot S-n`
(två gånger: jagaren är bara klassad som ytfartyg) eller `salva mot S-n` med tre 53-61.

Användning: ytskott.py [typer] [frön]
  typer kommaseparerade bland 53-61, SET-53, 53-62T och salva (tre 53-61); standard alla
  (standard 24). Varje frö och avstånd får ett eget spelfrö (`run_seed`); andelen träffar visas med
  90 % konfidensintervall. T.ex. ytskott.py 53-61,53-62T 8   (~2 min på 4 kärnor)

Körs från repots rot: uv run python kalibrering/ytskott.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import math
import random
import sys
from multiprocessing import Pool

from sim.events import ReportDelivered
from sim.game import Game
from sim.geo import distance
from sim.scenario import default_scenario
from sim.stations import TorpedoRoom

RANGES = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
WATCH_S = 600


def run_seed(seed: int, rng_nm: float) -> int:
    """Ett eget frö per avstånd: med samma frö på alla avstånd fick varje avstånd samma sensorslump
    och samma bäring, så 8 frön × 6 avstånd var i praktiken 8 försök."""
    return seed * 100 + int(rng_nm * 10)


def wilson(k: int, n: int, z: float = 1.645) -> tuple[float, float]:
    """90 % konfidensintervall för en andel (Wilson)."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def run(args):
    typ, rng_nm, seed = args
    seed = run_seed(seed, rng_nm)
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    rep = []
    g.bus.subscribe(ReportDelivered, lambda e: rep.append(e.report))
    w = g.world
    w.ais.clear()
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    dd = w.contacts[0]
    for v in w.contacts[1:]:
        v.sunk = True
    o = w.own.state
    o.depth = 0.0
    o.order_depth(0.0)
    o.speed = 0.0
    o.order_speed(0)
    b = math.radians(random.Random(seed).uniform(0, 360))
    dd.state.x, dd.state.y = o.x + rng_nm * math.sin(b), o.y + rng_nm * math.cos(b)

    def still():
        dd.state.speed = 0.0
        dd.state.order_speed(0)

    for i in range(WATCH_S):
        if i % 60 == 0:
            g.command("radar")
        g.tick()
        still()
    tracks = [t for t in g.knowledge.tracks.values() if t.solution is not None]
    if not tracks:
        return "ingen lösning", None, None
    tr = min(tracks, key=lambda t: t.solution.range_nm)
    sol = tr.solution
    ex, ey = g.own_position_estimate()
    # felet som avgör skottet: målet relativt oss enligt plottet mot sanningen
    rel_err = math.hypot((sol.x - ex) - (dd.state.x - o.x), (sol.y - ey) - (dd.state.y - o.y))
    tor = g.station(TorpedoRoom)
    for t in tor.tubes:
        t.load = None
    if typ == "salva":
        for t in tor.tubes[:3]:
            t.load = "53-61"
        order = f"salva mot {tr.designation}"
    else:
        tor.tubes[0].load = typ
        order = f"eld tub 1 mot {tr.designation}"
    g.command(order)
    g.command(order)
    for _ in range(900):
        g.tick()
        still()
        if dd.sunk:
            break
    fired = any(r.type == "torp.fired" for r in rep)
    return ("träff" if dd.sunk else "miss" if fired else "ej skjuten"), rel_err, sol.quality.label


def main():
    types = sys.argv[1].split(",") if len(sys.argv) > 1 else ["53-61", "salva", "SET-53", "53-62T"]
    seeds = range(1, 1 + (int(sys.argv[2]) if len(sys.argv) > 2 else 24))
    jobs = [(t, r, s) for t in types for r in RANGES for s in seeds]
    with Pool() as p:
        res = dict(zip(jobs, p.map(run, jobs)))
    for t in types:
        for r in RANGES:
            rows = [res[(t, r, s)] for s in seeds]
            hits = sum(x[0] == "träff" for x in rows)
            not_fired = sum(x[0] not in ("träff", "miss") for x in rows)
            errs = sorted(x[1] for x in rows if x[1] is not None)
            med = f"{errs[len(errs) // 2]:.3f}" if errs else "-"
            q = sorted({x[2] for x in rows if x[2]})
            lo, hi = wilson(hits, len(rows))
            print(f"{t:7} {r:.0f} nm: {hits}/{len(rows)} träff ({lo:.0%}–{hi:.0%}), ej skjuten {not_fired}, "
                  f"relativt lägesfel median {med} nm, lösning {', '.join(q)}")


if __name__ == "__main__":
    main()
