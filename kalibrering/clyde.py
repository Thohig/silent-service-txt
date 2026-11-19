"""Clyde: passiv, ja och verktyg (över skiktet och följ Polarisbåten när sonar klassat den).
Användning: clyde.py clyde-in|clyde frön passiv,ja,verktyg

Skriver per frö: utfall, minuter, första förslag eller kontakt efter överlämnandet (s), sekunder på
bandet, besticksfel vid slutet (nm). Körs från repots rot: uv run python kalibrering/clyde.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random
import sys
from concurrent.futures import ProcessPoolExecutor

from sim.events import ReportDelivered
from sim.game import Game
from sim.geo import distance
from sim.scenario import build_scenario

JA_EFTER_S = 20


def run(args):
    key, bot, seed = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    t0, due, first = g.now, [], [None]

    def on(e):
        r = e.report
        if first[0] is None and (r.kind == "suggest" or r.type == "sonar.new_contact"):
            first[0] = g.now - t0
        if bot != "passiv" and r.kind == "suggest":
            due.append(g.now + JA_EFTER_S)
    g.bus.subscribe(ReportDelivered, on)
    k = g.knowledge
    acted = False
    for _ in range(12 * 3600):
        if g.over:
            break
        g.tick()
        if bot == "verktyg" and not acted:
            pol = [t for t in k.tracks.values() if "Polaris" in t.classification and t.held]
            if pol:
                acted = True
                g.command(f"djup 40, följ {pol[0].designation}")
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
    from sim.stations.navigation import NavigationStation
    from sim.stations.sonar_room import SonarRoom
    son, nav = g.station(SonarRoom), g.station(NavigationStation)
    rec = max((son.recorded_s(d) for d in k.tracks), default=0)
    o = g.world.own.state
    err = distance(o.x, o.y, nav.est_x, nav.est_y)
    out = (g.world.outcome or {}).get("outcome") or "pågår"
    return bot, seed, out, (g.now - t0) // 60, first[0], rec, round(err, 2)


if __name__ == "__main__":
    key, n, bots = sys.argv[1], int(sys.argv[2]), sys.argv[3].split(",")
    jobs = [(key, b, s) for b in bots for s in range(1, n + 1)]
    with ProcessPoolExecutor() as ex:
        for r in ex.map(run, jobs):
            print(*r)
