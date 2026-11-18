"""Kalibreringskontroll: kör passiva boten och ja-boten över alla scenarier och jämför med
baslinjen (`kalibrering/baslinje.json`).

Det är siffrorna under Kalibrering i CLAUDE.md som oftast glider: hur ofta passiv kapten och
ja-boten når varje utfall, och på hur lång tid. Kontrollen säger vad som flyttat sig sedan
baslinjen sparades. De särskilda botarna (salva, grind, sprint …) körs fortfarande för hand.

Användning (från repots rot; ~25 min på 4 kärnor för alla scenarier och 8 frön):
    uv run python kalibrering/kontroll.py                 # jämför med baslinjen
    uv run python kalibrering/kontroll.py --spara         # skriv en ny baslinje
    uv run python kalibrering/kontroll.py --bara kuba,konvoj-kort --frön 4

Ett utfall räknas som flyttat när antalet skiljer med minst FLYTT_N (av 8), tiden när medianen
ändrats mer än FLYTT_TID (andel). Avslutar med 1 om något flyttat.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import json
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import SCENARIOS, build_scenario

BASLINJE = _Path(__file__).with_name("baslinje.json")
MAX_H = 8                  # längsta speltid (sundet 7 h)
JA_EFTER_S = 20            # ja-boten svarar så här länge efter förslaget
FLYTT_N = 2
FLYTT_TID = 0.25


def run(args) -> tuple[str, str, int, str, int]:
    key, bot, seed = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    due: list[int] = []
    if bot == "ja":
        g.bus.subscribe(ReportDelivered,
                        lambda e: due.append(g.now + JA_EFTER_S) if e.report.kind == "suggest"
                        else None)
    for _ in range(MAX_H * 3600):
        if g.over:
            break
        g.tick()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
    out = (g.world.outcome or {}).get("outcome") or "pågår"
    return key, bot, seed, out, g.now // 60


def summarize(rows) -> dict:
    """{scenario: {bot: {"utfall": {utfall: antal}, "minuter": {utfall: median}}}}"""
    res: dict = {}
    for key, bot, _seed, out, minutes in rows:
        r = res.setdefault(key, {}).setdefault(bot, {"utfall": {}, "_t": {}})
        r["utfall"][out] = r["utfall"].get(out, 0) + 1
        r["_t"].setdefault(out, []).append(minutes)
    for bots in res.values():
        for r in bots.values():
            r["minuter"] = {o: round(statistics.median(ts)) for o, ts in sorted(r.pop("_t").items())}
            r["utfall"] = dict(sorted(r["utfall"].items()))
    return res


def compare(old: dict, new: dict) -> list[str]:
    moved = []
    for key, bots in new.items():
        for bot, r in bots.items():
            o = old.get(key, {}).get(bot)
            if o is None:
                moved.append(f"{key} {bot}: ny (ingen baslinje)")
                continue
            for out in sorted(set(o["utfall"]) | set(r["utfall"])):
                a, b = o["utfall"].get(out, 0), r["utfall"].get(out, 0)
                if abs(a - b) >= FLYTT_N:
                    moved.append(f"{key} {bot}: {out} {a} ⇒ {b}")
                ta, tb = o["minuter"].get(out), r["minuter"].get(out)
                if ta and tb and abs(tb - ta) > FLYTT_TID * ta:
                    moved.append(f"{key} {bot}: {out} median {ta} ⇒ {tb} min")
    return moved


def main() -> int:
    argv = sys.argv[1:]
    keys = list(SCENARIOS)
    if "--bara" in argv:
        keys = argv[argv.index("--bara") + 1].split(",")
    seeds = range(int(argv[argv.index("--frön") + 1]) if "--frön" in argv else 8)
    t0 = time.time()
    jobs = [(k, bot, s) for k in keys for bot in ("passiv", "ja") for s in seeds]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(run, jobs, chunksize=1))
    new = summarize(rows)
    for key, bots in new.items():
        for bot, r in bots.items():
            print(f"{key:12s} {bot:6s} {r['utfall']}  median min {r['minuter']}")
    print(f"{time.time() - t0:.0f} s")
    if "--spara" in argv:
        old = json.loads(BASLINJE.read_text()) if BASLINJE.exists() else {}
        old.update(new)
        BASLINJE.write_text(json.dumps(old, indent=1, ensure_ascii=False) + "\n")
        print("sparad:", BASLINJE)
        return 0
    if not BASLINJE.exists():
        print("ingen baslinje: kör med --spara först")
        return 1
    moved = compare(json.loads(BASLINJE.read_text()), new)
    print("\n".join(["flyttat:", *moved]) if moved else "som baslinjen")
    return 1 if moved else 0


if __name__ == "__main__":
    raise SystemExit(main())
