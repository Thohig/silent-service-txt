"""Konvojboten: ja på förslag, salva mot klassad transport/tanker ≤ 3 nm med lösning ≥ osäker.
Användning: konvoj_salva.py konvoj|konvoj-kort frön [titt]

Med `titt` skjuter boten först när plottets lösning bygger på en periskoptitt på målet som är
högst 60 s gammal (den svarar ja på vakthavandes titt före skottet och väntar på den). Är ett
stort mål ≤ 3,5 nm enligt plottet och vi inte jagade går den själv upp på periskopdjup för titten
(vakthavande föreslår inte det med en jagare nära eller stark radar).
Vid varje skott skrivs lösningens avståndsfel mot sanningen (för jämförelse mellan lägena).

Körs från repots rot: uv run python kalibrering/konvoj_salva.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.game import Game
from sim.scenario import build_scenario
from sim.reports import Quality
from sim.stations.officer import is_big_ship
from sim.stations.sonar_room import SonarRoom

LOOK_FRESH_S = 60
key = sys.argv[1]; n = int(sys.argv[2])
wait_look = len(sys.argv) > 3 and sys.argv[3] == "titt"


def fresh_look(tr, sol, now) -> bool:
    looks = [o.t for o in tr.observations if o.course_obs is not None]
    return bool(looks) and now - looks[-1] <= LOOK_FRESH_S and sol.t >= looks[-1]


def close_target(g) -> bool:
    for tr in g.knowledge.tracks.values():
        sol = tr.solution
        if tr.held and is_big_ship(tr) and sol is not None and sol.quality >= Quality.OSAKER:
            r = g.knowledge.resolve(tr.designation, g.now, g.own_position_estimate())
            if r is not None and r.range_nm <= 3.5:
                return True
    return False


def range_error(g, desig, sol) -> float | None:
    sensor = g.station(SonarRoom).sensor
    for v in g.world.contacts:
        if sensor.designation_of(v.id) == desig:
            return abs(sol.range_nm - g.world.true_range(v))
    return None


res = []
for seed in range(n):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    t0 = g.now; first_sink = None; shots = []
    while not g.over and g.now - t0 < 4 * 3600:
        if g.active_suggestion(): g.command("ja")
        if wait_look and g.now % 60 == 0 and g.world.own.state.depth > 18 \
                and not g.knowledge.hunted(g.now) and close_target(g):
            g.command("periskopdjup")
        if g.now % 10 == 0 and g.world.own.state.depth <= 60:
            for tr in list(g.knowledge.tracks.values()):
                if not tr.held or not is_big_ship(tr) or tr.class_quality < Quality.GOD: continue
                sol = g.knowledge.resolve(tr.designation, g.now, g.own_position_estimate())
                if sol and sol.quality >= Quality.OSAKER and sol.range_nm <= 3.0 \
                        and (not wait_look or fresh_look(tr, tr.solution or sol, g.now)):
                    err = range_error(g, tr.designation, sol)
                    shots.append((sol.quality.label, None if err is None else round(err, 2)))
                    g.command(f"salva {tr.designation}"); g.command(f"salva {tr.designation}")
                    break
        g.tick()
        if first_sink is None and any(v.sunk for v in g.world.contacts if v.id.startswith("K")):
            first_sink = (g.now - t0) // 60
    sunk = [v.id for v in g.world.contacts if v.sunk]
    neutral = sum(1 for v in g.world.contacts if v.sunk and v.side == "neutral")
    res.append((seed, g.world.outcome and g.world.outcome["outcome"], sunk, first_sink, shots[:3],
                neutral))
    print(res[-1], flush=True)
print(key, "titt" if wait_look else "salva", "sänkt minst ett:",
      sum(1 for r in res if any(s.startswith("K") for s in r[2])), "av", n,
      "· neutrala sänkta:", sum(r[5] for r in res))
