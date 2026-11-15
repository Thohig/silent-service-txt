"""Kvadrat 7: ja-boten över 12 frön, hur ofta jagaren och flyget hittar oss.
Användning: kuba_jakt.py etikett

Körs från repots rot: uv run python kalibrering/kuba_jakt.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys, collections
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
tag = sys.argv[1]; tot = collections.Counter()
for seed in range(1, 13):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    g.bus.subscribe(ReportDelivered, lambda e, g=g: e.report.kind == "suggest" and e.report.data.get("order") and g.command("ja"))
    while not g.over: g.tick()
    m = g.world.mission
    tot["upptäckt"] += m.get("enemy_contacts", 0) > 0
    tot["sjunkbomber"] += m.get("charges_exploded", 0)
    tot["anfallen"] += m.get("charges_exploded", 0) > 0
    tot["skrov<1"] += g.world.own.sys.hull < 1
    tot[g.world.outcome["outcome"]] += 1
    tot["flyget hittade"] += m.get("air_contacts", 0) > 0
print(tag, dict(tot))
