"""Kalibreringskontroll: kör passiva boten och ja-boten över alla scenarier och jämför med
baslinjen (`kalibrering/baslinje.json`).

Det är siffrorna under Kalibrering i CLAUDE.md som oftast glider: hur ofta passiv kapten och
ja-boten når varje utfall, och på hur lång tid. Kontrollen säger vad som flyttat sig sedan
baslinjen sparades. De särskilda botarna (salva, grind, sprint …) körs fortfarande för hand.

Användning (från repots rot; ~30 min på 4 kärnor för alla scenarier och 8 frön):
    uv run python kalibrering/kontroll.py                 # jämför med baslinjen
    uv run python kalibrering/kontroll.py --spara         # skriv en ny baslinje
    uv run python kalibrering/kontroll.py --bara kuba,konvoj-kort --frön 4

Frön 0 … n−1, n = 8 eller FLER_FRÖN för scenarier där slumpen avgör (`--frön n` för alla). Ett
utfall räknas som flyttat när andelen skiljer med minst FLYTT_N av 8, tiden när medianen
ändrats mer än FLYTT_TID (andel). Baslinjen sparar också utfallet per frö (frön 0 … n−1): när något
flyttat listas fröna som bytt utfall, med kommandot för `skillnad.py` (första skillnaden mot
baslinjens commit). Avslutar med 1 om något flyttat.
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
MAX_H = 15                 # längsta speltid (krig 14 h, clyde 10 h, sundet 7 h)
JA_EFTER_S = 20            # ja-boten svarar så här länge efter förslaget
FLYTT_N = 2               # av 8 frön (räknas som andel vid andra antal)
FLYTT_TID = 0.25
# scenarier där ja-botens utfall avgörs av vilken väg den råkar ta: fler frön, så att en verklig
# effekt skiljs från brus (Clyde: 3 eller 4 av 16 klara beroende på nästan vilken ändring som helst)
FLER_FRÖN = {"clyde": 16, "clyde-in": 16, "konvoj": 16, "konvoj-kort": 16, "krig-kort": 16}


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


def _commit() -> str:
    """HEAD:s korta hash; med ändringar som inte är committade står det efter ("+ändrad")."""
    import subprocess
    root = _Path(__file__).resolve().parents[1]
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                         text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "sim"], cwd=root, capture_output=True,
                           text=True).stdout.strip()
    return sha + ("+ändrad" if dirty else "")


def summarize(rows) -> dict:
    """{scenario: {bot: {"utfall": {utfall: antal}, "minuter": {utfall: median},
    "frön": {frö: utfall}}}}"""
    res: dict = {}
    for key, bot, seed, out, minutes in rows:
        r = res.setdefault(key, {}).setdefault(bot, {"utfall": {}, "_t": {}, "frön": {}})
        r["utfall"][out] = r["utfall"].get(out, 0) + 1
        r["_t"].setdefault(out, []).append(minutes)
        r["frön"][str(seed)] = out
    for bots in res.values():
        for r in bots.values():
            r["minuter"] = {o: round(statistics.median(ts)) for o, ts in sorted(r.pop("_t").items())}
            r["utfall"] = dict(sorted(r["utfall"].items()))
            r["frön"] = dict(sorted(r["frön"].items(), key=lambda kv: int(kv[0])))
    return res


def compare(old: dict, new: dict) -> list[str]:
    moved = []
    for key, bots in new.items():
        for bot, r in bots.items():
            o = old.get(key, {}).get(bot)
            if o is None:
                moved.append(f"{key} {bot}: ny (ingen baslinje)")
                continue
            na, nb = sum(o["utfall"].values()) or 1, sum(r["utfall"].values()) or 1
            for out in sorted(set(o["utfall"]) | set(r["utfall"])):
                a, b = o["utfall"].get(out, 0), r["utfall"].get(out, 0)
                if abs(a / na - b / nb) * 8 >= FLYTT_N:
                    moved.append(f"{key} {bot}: {out} {a} av {na} ⇒ {b} av {nb}" if na != nb
                                 else f"{key} {bot}: {out} {a} ⇒ {b}")
                ta, tb = o["minuter"].get(out), r["minuter"].get(out)
                if ta and tb and abs(tb - ta) > FLYTT_TID * ta:
                    moved.append(f"{key} {bot}: {out} median {ta} ⇒ {tb} min")
            # vilka frön som bytt utfall (baslinjer sparade före 2026-11-23 har inga frön)
            old_seeds = o.get("frön") or {}
            changed = [(s_, old_seeds[s_], out) for s_, out in r.get("frön", {}).items()
                       if s_ in old_seeds and old_seeds[s_] != out]
            if changed and any(m.startswith(f"{key} {bot}:") for m in moved):
                moved.append(f"  frön som bytt: " + ", ".join(f"{s_} {a} ⇒ {b}" for s_, a, b in changed))
                moved.append(f"  första skillnaden: uv run python kalibrering/skillnad.py {key} "
                             f"{changed[0][0]} --bot {bot} --mot <commit för baslinjen>")
    return moved


def main() -> int:
    argv = sys.argv[1:]
    keys = list(SCENARIOS)
    if "--bara" in argv:
        keys = argv[argv.index("--bara") + 1].split(",")
    n = int(argv[argv.index("--frön") + 1]) if "--frön" in argv else None
    t0 = time.time()
    jobs = [(k, bot, s) for k in keys for bot in ("passiv", "ja")
            for s in range(n if n is not None else FLER_FRÖN.get(k, 8))]
    jobs.sort(key=lambda j: -FLER_FRÖN.get(j[0], 0))      # de långa först, så att kärnorna fylls
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(run, jobs, chunksize=1))
    new = summarize(rows)
    for key, bots in new.items():
        for bot, r in bots.items():
            print(f"{key:12s} {bot:6s} {r['utfall']}  median min {r['minuter']}")
    print(f"{time.time() - t0:.0f} s")
    if "--spara" in argv:
        old = json.loads(BASLINJE.read_text()) if BASLINJE.exists() else {}
        if old:                              # vad som flyttat mot den gamla, innan den skrivs över
            moved = [m.replace("<commit för baslinjen>", old.get("_commit", "<commit för baslinjen>"))
                     for m in compare(old, new)]
            print("\n".join(["flyttat mot förra baslinjen:", *moved]) if moved else "som förra baslinjen")
        old.update(new)
        old["_commit"] = _commit()          # vilken kod baslinjen kommer från (skillnad.py --mot)
        BASLINJE.write_text(json.dumps(old, indent=1, ensure_ascii=False) + "\n")
        print("sparad:", BASLINJE)
        return 0
    if not BASLINJE.exists():
        print("ingen baslinje: kör med --spara först")
        return 1
    base = json.loads(BASLINJE.read_text())
    moved = [m.replace("<commit för baslinjen>", base.get("_commit", "<commit för baslinjen>"))
             for m in compare(base, new)]
    print("\n".join(["flyttat:", *moved]) if moved else "som baslinjen")
    return 1 if moved else 0


if __name__ == "__main__":
    raise SystemExit(main())
