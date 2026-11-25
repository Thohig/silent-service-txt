"""Talnivån (ui/audio.py): hur mycket som läses upp på varje nivå, och vad, med ja-boten (2026-11-25).

Ett `SoundBoard` per nivå (allt, viktigt, larm, av) lyssnar på samma spel; repliken räknas när den köas för
uppläsning (tecken och antal, larm och förslag för sig). Loggboken påverkas inte av nivån. `--typer` listar
de rapporttyper som läses mest på nivån viktigt (där `ROUTINE_TYPES` i ui/audio.py finjusteras).

Användning (från repots rot):
    uv run python kalibrering/talniva.py kuba,konvoj-kort,jagad-kort [frön] [--typer]
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import collections
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from ui.audio import IMPORTANT, LEVELS, SoundBoard, speech_rank, spoken


class _Tyst:
    def play(self, *a, **k): return 0.0
    def speak(self, *a, **k): pass
    def speaking(self): return False
    def stop(self): pass


def run(args):
    key, seed = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    boards = {lv: SoundBoard(g.bus, _Tyst(), level=lv, ru_voice="Milena") for lv in LEVELS}
    out = {lv: [0, 0, 0] for lv in LEVELS}           # tecken, repliker, larm och förslag
    types: collections.Counter = collections.Counter()
    due: list[int] = []
    seen: list = []
    g.bus.subscribe(ReportDelivered, lambda e: (seen.append(e.report),
                                                e.report.kind == "suggest" and due.append(g.now + 20)))
    t0 = g.now
    for _ in range(2 * 3600):
        if g.over:
            break
        st = SimpleNamespace(time_scale=1, sim_time=g.now, command="captain", captain_at="central")
        for b in boards.values():
            b._status = st
        seen.clear()
        n0 = len(boards[IMPORTANT].queue)
        g.tick()
        new = len(boards[IMPORTANT].queue) - n0
        for r in [r for r in seen if spoken(r)][-new:] if new else []:
            types[(r.type, speech_rank(r))] += len(r.speech or r.text)
        for lv, b in boards.items():
            for ln in b.queue:
                out[lv][0] += sum(len(t) for _, t in ln.parts)
                out[lv][1] += 1
                out[lv][2] += ln.urgent
            b.queue.clear()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
    return (g.now - t0) / 60, out, types


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keys = args[0].split(",") if args else ["kuba", "konvoj-kort", "jagad-kort"]
    seeds = range(int(args[1]) if len(args) > 1 else 2)
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(run, [(k, s) for k in keys for s in seeds]))
    mins = sum(r[0] for r in res)
    print(f"{len(res)} spel, {mins:.0f} min")
    for lv in LEVELS:
        c = sum(r[1][lv][0] for r in res)
        n = sum(r[1][lv][1] for r in res)
        a = sum(r[1][lv][2] for r in res)
        print(f"  {lv:8} {c / mins:6.1f} tecken/min {n / mins * 60:5.0f} repliker/h  ({a} larm och förslag)")
    if "--typer" in sys.argv:
        tot: collections.Counter = collections.Counter()
        for r in res:
            tot.update(r[2])
        print("mest uppläst på nivån viktigt (typ, rang, tecken):")
        for (typ, rank), n in tot.most_common(20):
            print(f"  {typ:40} {rank}  {n}")
