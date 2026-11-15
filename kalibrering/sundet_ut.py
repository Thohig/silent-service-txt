"""Sundet ut: passiv, ja och ut (följ fartyget ut, sedan söderut).
Användning: sundet_ut.py frön förstafrö passiv,ja,ut [spåra]

Körs från repots rot: uv run python kalibrering/sundet_ut.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys, math
from sim.game import Game
from sim.scenario import build_scenario
from sim.reports import Quality
from sim.stations.navigation import NavigationStation
from sim.geo import angle_diff
n = int(sys.argv[1]); s0 = int(sys.argv[2]); bots = sys.argv[3].split(",")
for bot in bots:
    wins = 0; outs = []
    for seed in range(s0, s0 + n):
        g = Game(build_scenario("sundet-ut", random.Random(seed)), seed=seed)
        nav = g.station(NavigationStation); k = g.knowledge
        net = next(w for nm_, w in k.waypoints.items() if nm_.lower() == "nätet")
        t0 = g.now; phase = "wait"
        while not g.over and g.now - t0 < 2700:
            sug = g.active_suggestion()
            if bot == "ja" and sug:
                g.command("ja")
            if bot == "ut":
                if sug and sug[0].startswith("djup"):
                    g.command("ja")
                ex, ey = nav.est_x, nav.est_y
                if phase == "wait" and g.now == t0:
                    g.command("periskopdjup")
                if phase == "wait" and (g.now - t0) % 60 == 30 and g.world.own.state.depth <= 18:
                    g.command("periskop")
                if phase == "wait" and g.now % 5 == 0:
                    for tr in k.tracks.values():
                        sol = tr.solution
                        if not tr.civil or not tr.held or sol is None or sol.quality < Quality.OSAKER:
                            continue
                        if abs(angle_diff(sol.course, 180)) > 40:
                            continue
                        if sol.y < ey and 0.2 <= sol.range_nm <= 0.45:
                            g.command(f"turbin, djup 25, följ {tr.designation}")
                            phase = "follow"
                            break
                elif phase == "follow" and ey < net.y - 1.2:
                    g.command("kurs 180, fart 10"); phase = "run"
            if len(sys.argv) > 4 and (g.now - t0) % 120 == 0:
                w = g.world; st = w.own.state
                print("   ", (g.now-t0)//60, phase, f"y-line {st.y - w.mission['escape']['y_below']:+.2f} d{st.depth:.0f} v{st.speed:.0f} c{st.course:.0f} prop {w.own.sys.propulsion}",
                      [(a.vessel.id, a.state, round(w.true_range(a.vessel),2), a.datum and round(a.datum.sigma,2)) for a in w.ais if hasattr(a, "datum")], "hunting" if any(w._hunting_us(a) for a in w.ais) else "")
            g.tick()
        o = g.world.outcome["outcome"] if g.world.outcome else "?"
        wins += o == "recon_done"
        outs.append(f"{o}@{(g.now - t0) // 60}:{phase}")
    print(bot, wins, "/", n, outs, flush=True)
