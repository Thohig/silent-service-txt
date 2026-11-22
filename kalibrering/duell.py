"""Duellen under isen: passiv, ja-boten och en bot med besättningens verktyg, 8 frön.

Verktygsboten svarar ja som ja-boten och skjuter dessutom målsökande torpeder (tub 5, 6, sedan
1–4) mot en hållen hotkontakt med lösning ≥ osäker; är vi under 100 m går den först upp till 90.
Kolumnerna: frö, utfall, minuter efter överlämnandet, sekunder till första rapport (kontakt,
förslag eller larm), US-ubåtens skott, våra skott.

Användning (från repots rot): uv run python kalibrering/duell.py duell-kort,duell-torped passiv,ja,verktyg
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random
import sys
from concurrent.futures import ProcessPoolExecutor

from sim.events import ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario


def run(args):
    key, seed, bot = args
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    due=[]; first=[None]; start=g.now; fired=[0]
    def on(e):
        r=e.report
        if first[0] is None and (r.kind in ("suggest","contact") or r.alarm): first[0]=g.now-start
        if r.kind=="suggest": due.append(g.now+20)
    g.bus.subscribe(ReportDelivered, on)
    last_fire=-10**9
    while not g.over and g.now < start + 5*3600:
        g.tick()
        if bot!="passiv" and due and g.now>=due[0]:
            due.pop(0)
            if g.active_suggestion(): g.command("ja")
        if bot=="verktyg" and g.now-last_fire>=180 and g.now % 10 == 0:
            for tr in g.knowledge.tracks.values():
                sol=tr.solution
                if tr.held and tr.threat and sol is not None and sol.quality>=Quality.OSAKER:
                    if g.world.own.state.depth > 100:
                        if g.world.own.state.ordered_depth > 95:
                            g.command("djup 90")
                        break
                    tube = (5, 6, 1, 2, 3, 4)[min(fired[0], 5)]
                    g.command(f"eld tub {tube} mot {tr.designation}"); last_fire=g.now; fired[0]+=1
                    break
    o=g.world.outcome or {}
    return key, bot, seed, o.get("outcome"), (g.now-start)//60, first[0], g.world.mission.get("us_fired",0), fired[0]

if __name__=="__main__":
    keys=sys.argv[1].split(","); bots=sys.argv[2].split(",")
    with ProcessPoolExecutor() as ex:
        res=list(ex.map(run,[(k,s,b) for k in keys for b in bots for s in range(1,9)]))
    for k in keys:
        for b in bots:
            rows=[r for r in res if r[0]==k and r[1]==b]
            outs={}
            for r in rows: outs[r[3]]=outs.get(r[3],0)+1
            print(k,b,outs)
            print("   ",[(r[2],r[3],r[4],r[5],r[6],r[7]) for r in rows])
