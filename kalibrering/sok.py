"""Sök i skyttebotarnas JSON-loggar (logs/skytt/<läge>/*.jsonl, skrivna av skytt.py).

Varje rad är en rapport: t, klocka, typ, roll, slag, data, text, egen (x, y, djup, kurs, fart);
"KAPTEN" är botens order; sista raden är utfallet, skotten och larmen.

Användning (från repots rot):
    uv run python kalibrering/sok.py [läge] [--typ REGEX] [--text REGEX] [--roll R] [--scenario S]
                                     [--antal] [--visa N] [--larm]
--antal: antal träffar per scenario och typ. --visa N: de N första raderna (standard 20).
--larm: alla larm i loggarna (typ, spel, text).
T.ex.: sok.py skjut --typ "sonar.suggest.astern_lost" --antal
       sok.py lyssna --text "skjutläge" --scenario krig-kort --visa 10
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "logs" / "skytt"


def main() -> int:
    a = sys.argv[1:]
    def opt(name, default=None):
        return a[a.index(name) + 1] if name in a else default
    mode = a[0] if a and not a[0].startswith("--") else "skjut"
    typ, text, role = opt("--typ"), opt("--text"), opt("--roll")
    scen = opt("--scenario")
    files = sorted((ROOT / mode).glob("*.jsonl"))
    if scen:
        files = [f for f in files if f.stem.rsplit("-", 1)[0] == scen]
    if not files:
        print(f"inga loggar i {ROOT / mode}")
        return 1
    if "--larm" in a:
        c = Counter()
        for f in files:
            last = json.loads(f.read_text().splitlines()[-1])
            for l in last.get("larm", []):
                c[l["typ"]] += 1
                print(f"{f.stem:16} {l['klocka']} {l['typ']}: {l['text'][:150]}")
        print(dict(c))
        return 0
    rt, rx = (re.compile(typ) if typ else None), (re.compile(text) if text else None)
    hits, counts = [], Counter()
    for f in files:
        for line in f.read_text().splitlines():
            r = json.loads(line)
            if "utfall" in r:
                continue
            if rt and not rt.search(r.get("typ", "")) or rx and not rx.search(r.get("text") or "") \
                    or role and r.get("roll") != role:
                continue
            counts[(f.stem.rsplit("-", 1)[0], r.get("typ"))] += 1
            hits.append((f.stem, r))
    if "--antal" in a:
        for (s, t), n in sorted(counts.items()):
            print(f"{s:14} {t:40} {n}")
        print(f"totalt {len(hits)} i {len({h[0] for h in hits})} spel")
        return 0
    for stem, r in hits[:int(opt("--visa", 20))]:
        print(f"{stem:16} {r.get('klocka')} {r.get('typ')}: {(r.get('text') or '')[:150]}")
    print(f"({len(hits)} träffar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
