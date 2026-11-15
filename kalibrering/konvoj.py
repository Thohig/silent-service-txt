"""Konvojen: passiv, ja-boten och anfallsbot (periskop, anfall, salva, djupt bort).
Användning: konvoj.py passiv,ja,attack

Körs från repots rot: uv run python kalibrering/konvoj.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random, sys
from sim.game import Game
from sim.events import ReportDelivered
from sim.scenario import build_scenario
from sim.reports import Quality
from sim.stations.navigation import NavigationStation

def run(seed, bot, verbose=False, max_h=4):
    g = Game(build_scenario("konvoj", random.Random(seed)), seed=seed)
    st = {"phase": "approach", "fired": 0, "t_fire": None, "last": None}
    log = []
    def on(e):
        r = e.report
        log.append((g.now, r.type, r.text))
        if verbose and not r.type.startswith(("sonar.bearing",)):
            print(g.clock_str(), r.type, r.text)
        if bot == "ja" and r.data.get("order"):
            g.command("ja")
        if bot == "attack":
            o_ = r.data.get("order") or ""
            fast = o_.startswith("fart ") and int(o_.split()[1]) > 8
            if o_ and not fast and (st["phase"] != "approach" or r.type.startswith(("nav.suggest.attack", "nav.suggest.shoal", "nav.suggest.land", "off.suggest.down"))):
                g.command("ja")
            if r.type == "nav.attack.arrived":
                st["phase"] = "wait"
            if r.type in ("nav.attack.passed", "nav.attack.cannot", "nav.attack.lost"):
                st["attack_ordered"] = False
    g.bus.subscribe(ReportDelivered, on)
    o = g.world.own.state
    if bot == "attack":
        g.command("periskopdjup"); g.command("fart 4")
    nav = g.station(NavigationStation)
    for t in range(int(max_h * 3600)):
        g.tick()
        if g.over: break
        if bot != "attack": continue
        k = g.knowledge
        if st["phase"] in ("approach", "wait") and t % 240 == 0 and o.depth <= 19:
            g.command("periskop")
        if st["phase"] in ("approach", "wait") and t % 300 == 150 and o.depth > 19 \
                and not k.hunted(g.now):
            g.command("periskopdjup")
        if st["phase"] == "approach" and k.convoy and not st.get("attack_ordered") and t % 60 == 0:
            g.command(f"anfall {k.convoy.members[0]}"); st["attack_ordered"] = True
        if st["phase"] in ("approach", "wait") and t % 30 == 0 and k.convoy:
            # skjut när en konvojmedlem har god lösning inom 3 nm
            best = None
            for m in k.convoy.members:
                tr = k.tracks.get(m)
                sol = tr.solution if tr else None
                big = tr and ("trupptransport" in tr.classification or "tankfartyg" in tr.classification)
                if big and sol and sol.quality >= Quality.GOD and sol.range_nm <= 3.0 and g.now - sol.t < 60:
                    best = m if best is None else best
            if best:
                g.command(f"salva {best}"); g.command(f"salva {best}")
                st["fired"] += 1
                st["phase"] = "escape"; st["t_fire"] = g.now
        if st["phase"] == "escape" and g.now == st["t_fire"] + 5:
            away = (k.convoy.base.course + 180) % 360 if k.convoy and k.convoy.base else (o.course + 180) % 360
            g.command("turbin"); g.command("djup 200"); g.command(f"kurs {round(away):03d}"); g.command("fart 12")
    out = g.world.outcome or {"outcome": "pågår"}
    m = g.world.mission
    return out["outcome"], len(m.get("sunk", [])), m.get("enemy_contacts", 0), m.get("charges_exploded", 0), round(g.world.own.sys.hull, 2), g.now // 60

if __name__ == "__main__":
    bots = sys.argv[1].split(",")
    seeds = range(1, 9)
    for b in bots:
        res = [run(s, b) for s in seeds]
        print(b, res)
