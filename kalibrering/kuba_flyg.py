"""Kvadrat 7 med ubåtsjaktflyg: ja-boten, flygets och jagarens kontakter per frö.
Användning: kuba_flyg.py [frö ...]

Körs från repots rot: uv run python kalibrering/kuba_flyg.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys, collections, time
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
seeds = [int(s) for s in sys.argv[1:]] or range(1, 9)
outs = collections.Counter(); t0 = time.time()
for seed in seeds:
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    c = collections.Counter(); log = []
    def on(e, g=g, c=c, log=log):
        r = e.report; c[r.type] += 1
        if r.type.startswith(("off.esm.air", "off.periscope.aircraft", "sonar.buoy", "off.suggest.down", "sonar.suggest.quiet")):
            log.append(f"{g.clock_str()[:5]} {r.text}")
        if r.kind == "suggest" and r.data.get("order"): g.command("ja")
    g.bus.subscribe(ReportDelivered, on)
    while not g.over: g.tick()
    m = g.world.mission
    outs[g.world.outcome["outcome"]] += 1
    hows = collections.Counter(h for _, h in m.get("air_log", []))
    print(f"seed {seed}: {g.world.outcome['outcome']} jagarkontakt={m.get('enemy_contacts',0)} flygkontakt={m.get('air_contacts',0)} {dict(hows)} esm={c['off.esm.air']} bojar={c['sonar.buoy']} bojping={c['sonar.buoy_ping']} periskopflyg={c['off.periscope.aircraft']}")
    if len(seeds) == 1:
        print("\n".join(log[:30]))
print(dict(outs), f"{time.time()-t0:.0f}s")
