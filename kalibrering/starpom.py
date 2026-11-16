"""Starpom har befälet: kaptenen lämnar över direkt och sover; väckt svarar han. Ber starpom
om ett beslut utanför mandatet går han till centralen; ropas han dit kommer han. I
centralen är han ja-bot tills det varit lugnt i 10 min, då lämnar han över igen.
Jämförs med ja-boten utan starpom.
Användning: starpom.py kuba,konvoj 8 [salva]

Med `salva` skjuter kaptenen i centralen dessutom en salva mot klassad transport/tanker
≤ 3 nm med lösning ≥ osäker (som konvoj_salva.py), men aldrig från hytten: starpom måste gå
mot skjutläget och ropa honom i tid.

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
from sim.reports import Quality
from sim.stations.officer import is_big_ship
from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.starpom import mandate_for

LIMIT_S = 6 * 3600
CALM_S = 600


def salvo(g) -> None:
    """Kaptenen i centralen: salva mot ett klassat stort fartyg inom 3 nm."""
    if g.now % 10 or g.world.own.state.depth > 60:
        return
    for tr in list(g.knowledge.tracks.values()):
        if not tr.held or not is_big_ship(tr) or tr.class_quality < Quality.GOD:
            continue
        sol = g.knowledge.resolve(tr.designation, g.now, g.own_position_estimate())
        if sol and sol.quality >= Quality.OSAKER and sol.range_nm <= 3.0:
            g.command(f"salva {tr.designation}")
            g.command(f"salva {tr.designation}")
            return


def run(args):
    key, seed, starpom, fire = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    types = Counter()
    bad = []
    xo_orders = 0
    wants_central = []

    def on_report(e):
        types[e.report.type] += 1
        # ett beslut som är kaptenens (förslag utanför mandatet): han går till centralen
        if e.report.type in ("xo.call", "xo.orderly") and "beslutet är ert" in e.report.text:
            wants_central.append(e.t)

    def on_order(e):
        nonlocal xo_orders
        if e.by == "starpom":
            xo_orders += 1
            if not isinstance(e.order, mandate_for(g.knowledge.order_tasks)):
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
            if wants_central and st.captain_at == "cabin":
                wants_central.clear()
                g.command("jag har befälet")
            central_since = g.now
        elif starpom and st.captain_at == "central":
            if g.active_suggestion():
                g.command("ja")
            if fire:
                salvo(g)
            calm = not g.knowledge.hunted(g.now)
            if not calm:
                central_since = g.now
            elif g.now - central_since >= CALM_S:
                g.command("starpom har befälet")
                g.command("sov")
        elif not starpom:
            if g.active_suggestion():
                g.command("ja")
            if fire:
                salvo(g)
        g.tick()
    out = g.world.outcome["outcome"] if g.world.outcome else "tid"
    return (key, seed, starpom, out, g.now, xo_s, types["xo.ring"], types["xo.danger"],
            types["xo.orderly"], xo_orders, bad, types["xo.decline"])


def main():
    keys = sys.argv[1].split(",")
    n = int(sys.argv[2])
    fire = len(sys.argv) > 3 and sys.argv[3] == "salva"
    jobs = [(k, s, xo, fire) for k in keys for xo in (True, False) for s in range(n)]
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
                          f", ring {r[6]}, fara {r[7]}, ordonnans {r[8]}, beslut {r[9]}, nej {r[11]}"
                          + (f", UTANFÖR MANDATET {r[10]}" if r[10] else ""))


if __name__ == "__main__":
    main()
