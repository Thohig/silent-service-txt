"""Krigspatrullen: passiv bot, ja-boten och en bot med besättningens verktyg (verktyg).

Verktygsboten svarar ja på besättningens förslag och gör det kaptenen gör själv: periskoptittar,
`anfall` på konvojen, salva på ett stort fartyg med god lösning inom 3 sjömil, sedan djupt och fort
bort en kvart. Spaning och foto sköter besättningens förslag (kurs mot, sänd rapport, foto).
Den svarar ja på alla förslag, även att gå djupt och fort bort när fienden har oss.

Användning (från repots rot): uv run python kalibrering/krig.py krig passiv,ja,verktyg [frön]
Skriver utfall, uppgifternas resultat, sänkta fartyg, första förslaget och speltiden per frö.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario

MAX_H = 15
JA_EFTER_S = 20
FLEE: tuple[str, ...] = ()           # förslag verktygsboten avböjer (inga: den följer besättningen)
VERBOSE = int(__import__("os").environ.get("KRIG_VERBOSE", "0"))   # skriv de sista N rapporterna          # verktygsboten flyr bara när den själv skjutit


def run(args):
    key, bot, seed = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    start = g.now
    due: list[int] = []
    first = {"t": None}
    st = {"phase": "search", "t_fire": None}

    tail: list[str] = []

    def on(e):
        r = e.report
        if VERBOSE and not r.type.startswith("sonar.bearing"):
            tail.append(f"{g.clock_str()} {r.type} {r.text[:150]}")
        if r.kind == "suggest" and first["t"] is None:
            first["t"] = g.now - start
        if bot in ("ja", "verktyg") and r.kind == "suggest" and r.data.get("order"):
            if bot == "verktyg" and r.type in FLEE and st["phase"] != "escape":
                return
            due.append(g.now + JA_EFTER_S)
    g.bus.subscribe(ReportDelivered, on)
    o = g.world.own.state
    for _ in range(MAX_H * 3600):
        if g.over:
            break
        g.tick()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
        if bot != "verktyg":
            continue
        k, t = g.knowledge, g.now
        if st["phase"] == "escape":
            if t - st["t_fire"] == 5:
                g.command("turbin, djup 200, fart 12")
                g.command(f"kurs {round((o.course + 180) % 360):03d}")
            elif t - st["t_fire"] >= 15 * 60 and not k.hunted(t):
                g.command("smygmotor, fart 4, djup 60")
                st["phase"] = "search"
            continue
        if t % 240 == 0 and o.depth <= 19:
            g.command("periskop")
        if t % 300 == 150 and o.depth > 19 and not k.hunted(t):
            g.command("periskopdjup")
        if "anfall" in k.order_tasks and k.convoy and t % 120 == 0 and \
                g.station_goal() != "attack":
            g.command(f"anfall {k.convoy.members[0]}")
        if t % 30 == 0 and ("anfall" in k.order_tasks or "rapport" in k.order_tasks
                            and k.order_tasks_t < st.get("reported", -1)):
            for tr in k.tracks.values():
                sol = tr.solution
                big = "trupptransport" in tr.classification or "tankfartyg" in tr.classification
                if big and tr.held and sol and sol.quality >= Quality.GOD and sol.range_nm <= 3.0 \
                        and t - sol.t < 60:
                    g.command(f"salva {tr.designation}")
                    g.command(f"salva {tr.designation}")
                    st["phase"], st["t_fire"] = "escape", t
                    break
    out = (g.world.outcome or {}).get("outcome") or "pågår"
    if VERBOSE:
        print("\n".join(tail[-VERBOSE:]))
    m = g.world.mission
    results = tuple(f"{x['kind'][0]}:{x['result']}" for x in m.get("war_tasks", []))
    return (seed, bot, out, results, len(m.get("war_sunk", [])), m.get("war_df", 0),
            first["t"], (g.now - start) // 60)


def _goal(game):
    from sim.stations.navigation import NavigationStation
    return game.station(NavigationStation).goal


Game.station_goal = _goal


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "krig"
    bots = (sys.argv[2] if len(sys.argv) > 2 else "passiv,ja,verktyg").split(",")
    seeds = range(1, 1 + (int(sys.argv[3]) if len(sys.argv) > 3 else 8))
    jobs = [(key, b, s) for b in bots for s in seeds]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(run, jobs))
    for b in bots:
        mine = [r for r in rows if r[1] == b]
        print(f"\n{key} {b}: " + ", ".join(f"{k} {v}" for k, v in Counter(r[2] for r in mine).items()))
        res = Counter(x for r in mine for x in r[3])
        print("  uppgifter:", dict(sorted(res.items())))
        print("  sänkta:", sum(r[4] for r in mine), " pejlade:", sum(r[5] for r in mine))
        for r in mine:
            print("  ", r[0], r[2], r[3], "sänkta", r[4], "pejl", r[5], "första förslag",
                  "–" if r[6] is None else f"{r[6] / 60:.1f} min", "speltid", r[7], "min")
