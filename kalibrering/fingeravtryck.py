"""Fingeravtryck: kör alla scenarier med ja-boten och hashar allt som syns.

Till omstruktureringar som inte ska ändra spelet: samma kod ⇒ samma fingeravtryck för samma frö.
Hashar varje levererad rapport (roll, typ, data, text), egen ubåts sanna läge varje minut,
`Game.status()` och vyerna (sjökort, profil, sonar, systemtavla) var 5:e minut, och utfallet.

Användning (från repots rot):
    uv run python kalibrering/fingeravtryck.py [minuter] [frön] [--spara fil] [--jämför fil]

Standard 30 min och 2 frön (antalet: frön 0 … n−1), alla scenarier. Flaggorna kan stå var som helst. `--spara` skriver fingeravtrycken som JSON,
`--jämför` visar vilka scenarier/frön som skiljer sig från en sparad fil (avslutar med 1 då).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import dataclasses
import hashlib
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import SCENARIOS, build_scenario


def _views(g: Game) -> str:
    st = dataclasses.replace(g.status(), changing=tuple(sorted(g.status().changing)))
    return repr((st, g.chart(), g.profile(), g.sonar(), g.systems()))


def run(args) -> tuple[str, int, str, str]:
    key, seed, minutes = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    h = hashlib.sha256()
    due: list[int] = []

    def on(e):
        r = e.report
        h.update(repr((g.now, r.role, r.type, sorted(r.data.items(), key=lambda kv: kv[0]),
                       r.text)).encode())
        if r.kind == "suggest":
            due.append(g.now + 20)
    g.bus.subscribe(ReportDelivered, on)
    h.update(_views(g).encode())
    for _ in range(minutes * 60):
        if g.over:
            break
        g.tick()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
        if g.now % 60 == 0:
            s = g.world.own.state
            h.update(repr((s.x, s.y, s.depth, s.course, s.speed)).encode())
        if g.now % 300 == 0:
            h.update(_views(g).encode())
    out = (g.world.outcome or {}).get("outcome") or "-"
    h.update(repr((g.now, out)).encode())
    return key, seed, out, h.hexdigest()[:16]


def main() -> int:
    argv = sys.argv[1:]
    save = argv[argv.index("--spara") + 1] if "--spara" in argv else None
    comp = argv[argv.index("--jämför") + 1] if "--jämför" in argv else None
    # filnamnen efter --spara/--jämför är inga minuter eller frön
    skip = {i + 1 for i, a in enumerate(argv) if a in ("--spara", "--jämför")}
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and i not in skip]
    minutes = int(args[0]) if args else 30
    seeds = range(int(args[1]) if len(args) > 1 else 2)
    t0 = time.time()
    jobs = [(k, s, minutes) for k in SCENARIOS for s in seeds]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(run, jobs))
    prints = {f"{k}/{s}": f"{o} {d}" for k, s, o, d in res}
    for name, v in prints.items():
        print(f"{name:20s} {v}")
    print(f"{time.time() - t0:.0f} s")
    if save:
        _Path(save).write_text(json.dumps(prints, indent=1, ensure_ascii=False))
    if comp:
        old = json.loads(_Path(comp).read_text())
        diff = [n for n in prints if old.get(n) != prints[n]]
        print("skiljer:" if diff else "samma som", comp, *diff)
        return 1 if diff else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
