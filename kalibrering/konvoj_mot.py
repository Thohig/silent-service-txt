"""Konvojen motanfall: läge vid överlämnandet och utfall för passiv, ja och djupt-bort.
Användning: konvoj_mot.py frön [passiv,ja,bort]

Körs från repots rot: uv run python kalibrering/konvoj_mot.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.game import Game
from sim.scenario import build_scenario
from sim.convoy import EscortAI
from sim.geo import distance
n = int(sys.argv[1]); bots = sys.argv[2].split(",") if len(sys.argv) > 2 else ["passiv", "ja", "bort"]
handover = {}
for bot in bots:
    wins = 0
    for seed in range(n):
        g = Game(build_scenario("konvoj-mot", random.Random(seed)), seed=seed)
        w = g.world; t0 = g.now
        if bot == bots[0]:
            esc = [round(w.true_range(a.vessel), 1) for a in w.ais if isinstance(a, EscortAI)]
            print("  ", seed, f"över {t0//60} min", "skjutit" if w.mission.get("hostile_act") else "INTE SKJUTIT",
                  "jagad" if any(w._hunting_us(a) for a in w.ais) else "ej jagad", "eskort", esc,
                  "skrov", round(w.own.sys.hull, 2), "slut" if g.over else "")
        sink = None
        while not g.over and g.now - t0 < 3600:
            if bot == "ja" and g.active_suggestion():
                g.command("ja")
            if bot == "bort" and g.now == t0:
                th = [t.last_bearing for t in g.knowledge.tracks.values() if t.threat and t.last_bearing is not None and t.warship]
                b = (th[-1] + 180) % 360 if th else 90
                g.command(f"turbin, djup 200, fart 12, kurs {int(b):03d}")
            g.tick()
            if sink is None and any(v.sunk for v in w.contacts if v.id.startswith("K")):
                sink = g.now - t0
        out = w.outcome["outcome"] if w.outcome else "?"
        wins += out == "convoy_attacked"
        print(bot, seed, out, (g.now - t0) // 60, "min", "sänkt efter", sink, "s", "skrov", round(w.own.sys.hull, 2))
    print(bot, "lyckades", wins, "av", n, flush=True)
