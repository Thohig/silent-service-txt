"""Provspel: en kapten som svarar ja på förslagen efter 20 s, ger en rutinorder var 10:e min, bygger
vyerna var 5:e min, tittar i periskopet och skjuter på fientliga mål med god lösning inom 3 nm.
Skriver hela rapportflödet per scenario till logs/provspel/<scenario>-<frö>.log och letar efter
undantag, spam (samma rapporttyp 6+ gånger samma minut), sanningens id:n och oifyllda fält
("nan", "None", "inf" som hela ord: "innanför" larmar inte). Loggarna läses sedan för hand.

Användning (från repots rot): uv run python kalibrering/provspel.py krig,kuba,arktis [timmar] [frö]
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import sys, random, re, time, traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario

OUT = _Path(__file__).resolve().parents[1] / "logs" / "provspel"
ROUTINE = ["läget", "position", "torped", "maskin", "radio", "trim", "ström", "förslag", "S-1",
           "torpeder", "skjutlösning", "ekolod"]
TRUTH_ID = re.compile(r"\b(DD|T|SS|M|CV|P|AC|N)\d+\b")


def run(args):
    key, hours, seed = args
    log = open(f"{OUT}/{key}-{seed}.log", "w")
    issues = []
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    start = g.now
    due = []
    st = {"fired": None, "n": 0}
    per_min = Counter()

    def on(e):
        r = e.report
        st["n"] += 1
        txt = r.text or ""
        log.write(f"{g.clock_str()} [{r.kind}] {r.type}: {txt}\n")
        per_min[(g.now // 60, r.type)] += 1
        if per_min[(g.now // 60, r.type)] == 6 and not r.type.startswith(("sonar.bearing", "torp.countdown")):
            issues.append(f"{g.clock_str()} spam: {r.type} 6+ gånger samma minut")
        for bad in ("None", "nan", "{", "}", "inf", "Traceback"):
            if re.search(rf"\b{re.escape(bad)}\b" if bad.isalpha() else re.escape(bad), txt):
                issues.append(f"{g.clock_str()} '{bad}' i text: {r.type}: {txt[:160]}")
        m = TRUTH_ID.search(txt)
        if m and not re.search(r"\b[A-Z]-\d", txt[max(0, m.start()-2):m.end()]):
            issues.append(f"{g.clock_str()} möjligt sanningsid {m.group()}: {r.type}: {txt[:160]}")
        if r.kind == "suggest" and r.data.get("order"):
            due.append(g.now + 20)
    g.bus.subscribe(ReportDelivered, on)
    o = g.world.own.state
    t0 = time.time()
    try:
        for _ in range(hours * 3600):
            if g.over:
                break
            g.tick()
            t = g.now
            if due and t >= due[0]:
                due.pop(0)
                if g.active_suggestion():
                    g.command("ja")
            el = t - start
            if el % 600 == 300:
                g.command(ROUTINE[(el // 600) % len(ROUTINE)])
            if el % 300 == 0:
                g.chart(); g.profile(); g.sonar(); g.systems(); g.status()
            k = g.knowledge
            if st["fired"] is not None:
                if t - st["fired"] == 5:
                    g.command("djup 150, fart 10")
                if t - st["fired"] >= 900:
                    st["fired"] = None
                continue
            if el % 240 == 0 and o.depth <= 19:
                g.command("periskop")
            if el % 30 == 0:
                for tr in k.tracks.values():
                    sol = tr.solution
                    cls = tr.classification or ""
                    hostile = any(w in cls for w in ("jagare", "trupptransport", "tankfartyg", "ubåt")) \
                        and key.split("-")[0] not in ("kuba", "jagad", "clyde", "arktis", "sundet", "ovning")
                    if hostile and sol and sol.quality >= Quality.GOD and sol.range_nm <= 3.0 \
                            and t - sol.t < 60 and o.depth <= 100:
                        g.command(f"eld {tr.designation}")
                        g.command(f"eld {tr.designation}")
                        log.write(f"{g.clock_str()} *** KAPTEN: eld {tr.designation} ({cls}, {sol.range_nm:.1f} nm, {sol.quality})\n")
                        st["fired"] = t
                        break
    except Exception:
        issues.append(f"{g.clock_str()} UNDANTAG:\n{traceback.format_exc()}")
    out = (g.world.outcome or {}).get("outcome") or "pågår"
    log.write(f"\n=== {key} frö {seed}: {out}, {(g.now-start)//60} min speltid, {time.time()-t0:.0f} s\n")
    log.write("\n".join(issues) + "\n")
    log.close()
    return key, seed, out, (g.now - start) // 60, st["n"], issues


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    keys = sys.argv[1].split(",")
    hours = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
    with ProcessPoolExecutor(4) as ex:
        for key, s, out, mins, n, issues in ex.map(run, [(k, hours, seed) for k in keys]):
            print(f"\n## {key} frö {s}: {out}, {mins} min, {n} rapporter, {len(issues)} anmärkningar")
            for i in issues[:25]:
                print("  ", i)
