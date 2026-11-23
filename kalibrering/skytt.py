"""Skyttebotarna med orakel: spelar scenarier och letar buggar (2026-11-23).

Lägen:
- ja:     ja-boten (svarar ja på varje förslag efter 20 s), som kontroll.py
- skjut:  ja-boten som också skjuter (`eld`/`salva` växelvis) på varje säker lösning som inte är ett
          handelsfartyg, och upprepar ordern en gång (går förbi torpedrummets frågor); går själv till
          skjutdjup och skjutfart
- lyssna: som skjut, men avstår när torpedrummet frågar om ett långt skott (anfallsförslaget tas av
          ja-boten) och skjuter också på god lösning de första 5 min i skjutläget

Varje spel följs av oraklet (`orakel.py`, larm mot sanningen). Rapportflödet skrivs som JSON-rader till
logs/skytt/<läge>/<scenario>-<frö>.jsonl (typ, roll, slag, data, text, egen ubåts sanna läge; botens
order som typ "KAPTEN"; sist utfallet, skotten och larmen), så att loggarna kan sökas som data.

Användning (från repots rot):
    PYTHONHASHSEED=0 uv run python kalibrering/skytt.py [läge] [scenarier|alla] [frön] [minuter]
Standard: skjut, alla, frön 0-7, 180 min. Frön som 0-7 eller 1,4,9. NPROC=n processer.
Sammanfattningen: larmen per typ (med det första exemplets sammanhang), skotten, utfallen.
"""
import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(ROOT))
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import json
import math
import os
import random
import sys
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import SCENARIOS, build_scenario
from sim.stations.sonar_room import SonarRoom
from sim.weapons import Torpedo
from orakel import Orakel

OUT = ROOT / "logs" / "skytt"
JA_EFTER_S = 20
SHOT_GAP_S = 240          # samma mål högst så ofta
IN_POSITION_S = 300       # lyssna: skjut på god lösning så länge efter "vi är i skjutläge"
RESULT_S = 1200           # så länge efter skottet räknas en sänkning som skottets


def _truth_of(g, designation):
    sensor = g.station(SonarRoom).sensor
    for v in g.world.contacts:
        if v.side != "own" and getattr(v, "is_ship", False) and sensor.designation_of(v.id) == designation:
            return v
    return None


def run(args):
    mode, key, seed, minutes = args
    (OUT / mode).mkdir(parents=True, exist_ok=True)
    log = open(OUT / mode / f"{key}-{seed}.jsonl", "w")
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    orakel = Orakel(g)
    seen: list[str] = []
    due: list[int] = []
    state = {"arrived_t": -10**9, "n": 0, "limit_t": -10**9}

    def write(rec):
        print(json.dumps(rec, ensure_ascii=False, default=str), file=log)

    def on(e):
        r = e.report
        o = g.world.own.state
        seen.append(r.type)
        write({"t": g.now, "klocka": g.clock_str(), "typ": r.type, "roll": r.role, "slag": r.kind,
               "data": r.data, "text": r.text,
               "egen": [round(o.x, 4), round(o.y, 4), round(o.depth), round(o.course), round(o.speed, 1)]})
        if r.kind == "suggest":
            due.append(g.now + JA_EFTER_S)
        if r.type == "nav.attack.arrived":
            state["arrived_t"] = g.now

    def captain(cmd, note=""):
        write({"t": g.now, "klocka": g.clock_str(), "typ": "KAPTEN", "text": cmd + note})
        g.command(cmd)

    g.bus.subscribe(ReportDelivered, on)
    shots, last_shot = [], {}
    o = g.world.own.state
    try:
        for _ in range(minutes * 60):
            if g.over:
                break
            g.tick()
            orakel.tick()
            if due and g.now >= due[0]:
                due.pop(0)
                if g.active_suggestion():
                    captain("ja", f" ({g.active_suggestion()[0]})")
            for s in shots:                                   # skottens utfall
                if "res" not in s and s["_v"] is not None:
                    if s["_v"].sunk:
                        s["res"] = "träff"
                    elif g.now - s["t"] > RESULT_S:
                        sunk = [x for x in g.world.contacts if x.sunk and x.id not in s["_sunk0"]
                                and getattr(x, "is_ship", False)]
                        s["res"] = "sänkt annat" if sunk else "miss"
            if mode == "ja" or g.now % 10:
                continue
            in_pos = mode == "lyssna" and g.now - state["arrived_t"] < IN_POSITION_S
            for tr in list(g.knowledge.tracks.values()):
                sol = tr.solution
                if sol is None or not tr.held or tr.sunk or tr.civil or tr.friendly:
                    continue
                if not (sol.quality == Quality.SAKER or (in_pos and sol.quality >= Quality.GOD)):
                    continue
                if g.now - last_shot.get(tr.designation, -10**9) < SHOT_GAP_S:
                    continue
                if o.depth > 95 or o.speed > 12:
                    if g.now - state["limit_t"] > 60:
                        state["limit_t"] = g.now
                        parts = (["djup 60"] if o.depth > 95 else []) + (["fart 8"] if o.speed > 12 else [])
                        captain(", ".join(parts), f" (för skott på {tr.designation})")
                    continue
                last_shot[tr.designation] = g.now
                order = f"salva {tr.designation}" if state["n"] % 2 else f"eld {tr.designation}"
                state["n"] += 1
                v = _truth_of(g, tr.designation)
                before = {id(c) for c in g.world.contacts}
                rec = {"t": g.now, "klocka": g.clock_str(), "mål": tr.designation, "order": order,
                       "klass": tr.classification, "kvalitet": sol.quality.label,
                       "avstånd_lösning": round(sol.range_nm, 2)}
                if v is not None:
                    rec.update(slag=v.kind, sida=v.side,
                               avstånd_sant=round(math.hypot(v.state.x - o.x, v.state.y - o.y), 2))
                for _ in range(2):
                    n0 = len(seen)
                    captain(order, f" ({tr.classification}, {sol.range_nm:.1f} nm, {sol.quality.label})")
                    if mode == "lyssna":
                        for _ in range(8):
                            g.tick()
                            orakel.tick()
                        if "torp.long_shot" in seen[n0:]:
                            rec["res"] = "avstod (långt)"
                            break
                    if any(isinstance(c, Torpedo) and c.side == "own" and id(c) not in before
                           for c in g.world.contacts):
                        break
                fired = [c for c in g.world.contacts
                         if isinstance(c, Torpedo) and c.side == "own" and id(c) not in before]
                if not fired and "res" not in rec:
                    rec["res"] = "ej skjuten"
                rec["_v"] = v if fired else None
                rec["_sunk0"] = {x.id for x in g.world.contacts if x.sunk}
                shots.append(rec)
                break
    except Exception:
        orakel.larm.append(("undantag", g.clock_str(), traceback.format_exc().splitlines()[-1],
                            traceback.format_exc().splitlines()[-12:]))
    for s in shots:
        s.setdefault("res", "pågår")
        s.pop("_v", None)
        s.pop("_sunk0", None)
    out = (g.world.outcome or {}).get("outcome") or "pågår"
    larm = [{"typ": k, "klocka": c, "text": t, "sammanhang": ctx} for k, c, t, ctx in orakel.larm]
    write({"utfall": out, "minuter": g.now // 60, "skott": shots, "larm": larm})
    log.close()
    return {"key": key, "seed": seed, "out": out, "mins": g.now // 60, "shots": shots, "larm": larm}


def summary(mode, rows) -> None:
    by_kind = defaultdict(list)
    for r in rows:
        for a in r["larm"]:
            by_kind[a["typ"]].append((r["key"], r["seed"], a))
    print(f"\n=== {mode}: {len(rows)} spel")
    if not by_kind:
        print("inga larm")
    for kind, items in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        games = sorted({(k, s) for k, s, _ in items})
        print(f"\n## larm {kind}: {len(items)} i {len(games)} spel: "
              + ", ".join(f"{k} {s}" for k, s in games[:12]) + (" …" if len(games) > 12 else ""))
        texts = Counter(a["text"] for _, _, a in items)
        for t, n in texts.most_common(4):
            print(f"   {n}× {t[:200]}")
        k, s, a = items[0]
        print(f"   sammanhang ({k} {s} {a['klocka']}):")
        for line in a["sammanhang"][-6:]:
            print(f"     {line[:190]}")
    shots = [s for r in rows for s in r["shots"]]
    fired = [s for s in shots if s["res"] not in ("ej skjuten", "avstod (långt)")]
    if shots:
        print(f"\n## skott: {len(shots)} försök, {len(fired)} avfyrade, avstod "
              f"{sum(s['res'] == 'avstod (långt)' for s in shots)}: {dict(Counter(s['res'] for s in fired))}")
    outs = defaultdict(Counter)
    for r in rows:
        outs[r["key"]][r["out"]] += 1
    print("\n## utfall")
    for k, c in outs.items():
        print(f"   {k:13} {dict(c)}")


def seeds_of(arg: str) -> list[int]:
    if "-" in arg:
        a, b = arg.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in arg.split(",")]


def main() -> int:
    a = sys.argv[1:]
    mode = a[0] if a else "skjut"
    keys = list(SCENARIOS) if len(a) < 2 or a[1] == "alla" else a[1].split(",")
    seeds = seeds_of(a[2]) if len(a) > 2 else list(range(8))
    minutes = int(a[3]) if len(a) > 3 else 180
    t0 = time.time()
    with ProcessPoolExecutor(int(os.environ.get("NPROC", os.cpu_count() or 4))) as ex:
        rows = list(ex.map(run, [(mode, k, s, minutes) for k in keys for s in seeds], chunksize=1))
    summary(mode, rows)
    print(f"\n{time.time() - t0:.0f} s; loggarna i {OUT / mode}/", file=sys.stderr)
    return 1 if any(r["larm"] for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
