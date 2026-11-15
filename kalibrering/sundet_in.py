"""Sundet in: passiv, ja och grind (följ ett fartyg in, foto innanför).
Användning: sundet_in.py frön förstafrö passiv,ja,grind

Körs från repots rot: uv run python kalibrering/sundet_in.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys, math
from sim.game import Game
from sim.scenario import build_scenario
from sim.reports import Quality
from sim.stations.navigation import NavigationStation
from sim.geo import distance, angle_diff
n = int(sys.argv[1]); s0 = int(sys.argv[2]); bots = sys.argv[3].split(",")
for bot in bots:
    wins = 0; outs = []
    for seed in range(s0, s0 + n):
        g = Game(build_scenario("sundet-in", random.Random(seed)), seed=seed)
        nav = g.station(NavigationStation); k = g.knowledge
        net = next(w for nm_, w in k.waypoints.items() if nm_.lower() == "nätet")
        t0 = g.now; phase = "wait"; follow = None
        while not g.over and g.now - t0 < 2700:
            if bot == "ja" and g.active_suggestion():
                g.command("ja")
            if bot == "grind" and g.now % 5 == 0:
                ex, ey = nav.est_x, nav.est_y
                if phase == "wait":
                    for tr in k.tracks.values():
                        sol = tr.solution
                        if not tr.civil or not tr.held or sol is None or sol.quality < Quality.OSAKER:
                            continue
                        if abs(angle_diff(sol.course, bearing := math.degrees(math.atan2(net.x - ex, net.y - ey)))) > 40:
                            continue
                        if sol.y > ey and 0.2 <= sol.range_nm <= 0.45:
                            g.command(f"turbin, djup 40, följ {tr.designation}")
                            phase, follow = "follow", tr.designation
                            break
                elif phase == "follow" and ey > net.y + 0.6:
                    g.command("kurs mot ankarplatsen, fart 4, periskopdjup"); phase = "up"
                elif phase == "up" and g.world.own.state.depth <= 18:
                    g.command("foto"); phase = "photo"
                elif phase == "photo" and g.now % 60 == 0:
                    g.command("foto")
            g.tick()
        o = g.world.outcome["outcome"] if g.world.outcome else "?"
        wins += o == "photo_taken"
        outs.append(f"{o}@{(g.now - t0) // 60}:{phase}")
    print(bot, wins, "/", n, outs, flush=True)
