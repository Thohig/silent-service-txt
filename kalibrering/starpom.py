"""Starpom har befälet: kaptenen lämnar över direkt och sover; väckt svarar han, och i
centralen är han ja-bot tills det varit lugnt i 10 min, då lämnar han över igen.
Jämförs med ja-boten utan starpom.
Användning: starpom.py kuba,konvoj 8

Mäter: utfall, väckningar (ring, fara, ordonnans), andel av tiden med starpom i befäl,
starpoms beslut och order utanför mandatet (ska vara 0).

Körs från repots rot: uv run python kalibrering/starpom.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random
import sys
from collections import Counter
from multiprocessing import Pool

from sim.events import OrderIssued, ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.starpom import MANDATE

LIMIT_S = 6 * 3600
CALM_S = 600


def run(args):
    key, seed, starpom = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    types = Counter()
    bad = []
    xo_orders = 0

    def on_report(e):
        types[e.report.type] += 1

    def on_order(e):
        nonlocal xo_orders
        if e.by == "starpom":
            xo_orders += 1
            if not isinstance(e.order, MANDATE):
                bad.append(e.text)

    g.bus.subscribe(ReportDelivered, on_report)
    g.bus.subscribe(OrderIssued, on_order)
    xo_s = 0
    central_since = 0
    if starpom:
        g.command("starpom har befälet")
        g.command("sov")
    while not g.over and g.now < LIMIT_S:
        st = g.status()
        if st.command == "starpom":
            xo_s += 1
            if st.phone == "ring" and g.now % 15 == 0:
                g.command("svara")
            central_since = g.now
        elif starpom and st.captain_at == "central":
            if g.active_suggestion():
                g.command("ja")
            calm = not g.knowledge.hunted(g.now)
            if not calm:
                central_since = g.now
            elif g.now - central_since >= CALM_S:
                g.command("starpom har befälet")
                g.command("sov")
        elif g.active_suggestion():
            g.command("ja")
        g.tick()
    out = g.world.outcome["outcome"] if g.world.outcome else "tid"
    return (key, seed, starpom, out, g.now, xo_s, types["xo.ring"], types["xo.danger"],
            types["xo.orderly"], xo_orders, bad)


def main():
    keys = sys.argv[1].split(",")
    n = int(sys.argv[2])
    jobs = [(k, s, xo) for k in keys for xo in (True, False) for s in range(n)]
    with Pool() as pool:
        res = pool.map(run, jobs)
    for key in keys:
        for xo in (True, False):
            rows = [r for r in res if r[0] == key and r[2] == xo]
            outs = Counter(r[3] for r in rows)
            print(f"{key} {'starpom' if xo else 'ja-bot '}: {dict(outs)}")
            if xo:
                for r in rows:
                    print(f"   frö {r[1]}: {r[3]:16s} {r[4] / 3600:4.1f} h, starpom {r[5] / max(1, r[4]):4.0%}"
                          f", ring {r[6]}, fara {r[7]}, ordonnans {r[8]}, beslut {r[9]}"
                          + (f", UTANFÖR MANDATET {r[10]}" if r[10] else ""))


if __name__ == "__main__":
    main()
