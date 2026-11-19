"""Hök-boten: ja-boten som laddar en kärnladdning och håller kärnvapenrådet så snart sjunkbomber
hörs eller känns nära, och skjuter mot närmaste hotkontakt med lösning om nycklarna vrids.
Mäter hur ofta zampoliten och starpom säger ja, hur ofta kärnladdningen skjuts och hur ofta rådet
trodde på ett skarpt angrepp som inte fanns (eller tvärtom).

Användning: rad.py kuba,kuba-kort,jagad,jagad-kort [frön]

Körs från repots rot: uv run python kalibrering/rad.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from sim.events import ChargeHeard, ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations.council import NuclearCouncil

JA_EFTER_S = 20
RAD_SPARR_S = 120          # boten kallar rådet högst så ofta
MAX_H = 8


def run(args):
    key, seed = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    due: list[int] = []
    want = {"council": False}
    last_council = [-10**9]
    fire_asked = [0]

    def on_report(e):
        if e.report.kind == "suggest":
            due.append(g.now + JA_EFTER_S)

    def on_charge(e: ChargeHeard):
        if e.near:
            want["council"] = True

    g.bus.subscribe(ReportDelivered, on_report)
    g.bus.subscribe(ChargeHeard, on_charge)
    g.command("ladda tub 7 T-5")
    council = g.station(NuclearCouncil)
    for _ in range(MAX_H * 3600):
        if g.over:
            break
        g.tick()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
        if want["council"] and g.now - last_council[0] >= RAD_SPARR_S and council.due is None:
            want["council"] = False
            last_council[0] = g.now
            g.command("kärnvapenråd")
        if council.armed() and fire_asked[0] < 2:
            st = g.world.own.state
            if st.ordered_depth > 90 or st.depth > 100 or st.speed > 12:
                if st.ordered_depth > 90:
                    g.command("djup 90, fart 6")        # upp till skjutdjup (≤ 100 m, ≤ 12 kn)
                continue
            k = g.knowledge
            targets = [t for t in k.tracks.values() if t.threat and t.solution is not None
                       and t.solution.quality >= Quality.OSAKER]
            if targets:
                t = min(targets, key=lambda t: t.solution.range_nm)
                g.command(f"eld tub 7 mot {t.designation}")   # första: frågan; andra: skottet
                fire_asked[0] += 1
            else:                                   # ingen lösning: mot närmaste hotets bäring
                held = [t for t in k.tracks.values() if t.threat and t.last_bearing is not None]
                if held:
                    b = round(held[-1].last_bearing) % 360
                    g.command(f"eld tub 7 kurs {b:03d}")
                    fire_asked[0] += 1
    m = g.world.mission
    councils = m.get("councils", [])
    return {
        "key": key, "seed": seed, "outcome": (g.world.outcome or {}).get("outcome"),
        "min": g.now // 60, "councils": len(councils),
        "z_yes": sum(c["zampolit"] for c in councils),
        "s_yes": sum(c["starpom"] for c in councils),
        "keys": sum(c["zampolit"] and c["starpom"] for c in councils),
        "fired": bool(m.get("nuclear_fired_t")),
        "wrong_attack": sum(c["believed_attacked"] and not c["real_near"] for c in councils),
        "missed_attack": sum(not c["believed_attacked"] and c["real_near"] > 0 for c in councils),
    }


if __name__ == "__main__":
    keys = sys.argv[1].split(",")
    seeds = range(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    t0 = time.time()
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(run, [(k, s) for k in keys for s in seeds]))
    for k in keys:
        rows = [r for r in res if r["key"] == k]
        tot = lambda f: sum(r[f] for r in rows)
        outs: dict = {}
        for r in rows:
            outs[r["outcome"]] = outs.get(r["outcome"], 0) + 1
        print(f"{k:12} utfall {outs}")
        print(f"{'':12} råd {tot('councils')}, zampolit ja {tot('z_yes')}, starpom ja {tot('s_yes')}, "
              f"nycklar {tot('keys')}, skjutit i {sum(r['fired'] for r in rows)} av {len(rows)}, "
              f"trodde skarpt utan skarpa {tot('wrong_attack')}, missade skarpa {tot('missed_attack')}")
    print(f"{time.time() - t0:.0f} s")
