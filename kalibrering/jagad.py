"""Jagade (eller annat scenario med --scen=nyckel): ja-bot, passiv eller taktisk.
Användning: jagad.py [frön] [--passiv | --taktisk | --sprint] [--scen=kuba] [--verbose]

Körs från repots rot: uv run python kalibrering/jagad.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random
import sys
from collections import Counter

from sim.events import ReportDelivered  # noqa: E402
from sim.game import Game  # noqa: E402
from sim.scenario import build_scenario  # noqa: E402

SCEN = next((a.split("=")[1] for a in sys.argv if a.startswith("--scen=")), "jagad")
args = [a for a in sys.argv[1:] if not a.startswith("--")]
seeds = range(int(args[0])) if args else range(8)
verbose = "--verbose" in sys.argv
passive = "--passiv" in sys.argv     # svarar aldrig ja
sprint = "--sprint" in sys.argv
tactical = "--taktisk" in sys.argv or sprint   # djupt, smygmotor, följer navigatörens väg ut


def run(seed):
    sc = build_scenario(SCEN, random.Random(seed))
    g = Game(sc, seed=seed)
    log = []

    def on(ev):
        r = ev.report
        line = f"{g.clock_str(ev.t)} {r.speaker}: {r.text}"
        log.append(line)
        if verbose:
            print(line)
    g.bus.subscribe(ReportDelivered, on)
    first_contact = None
    lethal_t = None
    while not g.over and g.now < 5 * 3600 + 10:
        if tactical:
            if g.now == 2:
                from sim.stations.navigation import NavigationStation
                c, _, _ = g.station(NavigationStation).exit_route()
                g.command(f"djup 200, kurs {c:03.0f}, " + ("turbin, fart 12" if sprint else "smygmotor"))
            if g.suggestion is not None:
                order, text, _ = g.suggestion
                nav = "navigatören" in text
                if sprint:      # bara navigatörens djupvarningar och vägen ut, plus skenmål
                    ok = order == "skenmål" or (nav and order.startswith(("djup", "kurs")))
                else:
                    ok = order.startswith(("djup", "skenmål", "botten", "smygmotor")) or nav
                g.command("ja" if ok else "nej")
        elif not passive and g.suggestion is not None:
            g.command("ja")
        g.tick()
        if first_contact is None and any(t.threat for t in g.knowledge.tracks.values()):
            first_contact = g.now
        if lethal_t is None and any(getattr(a, "roe", "") == "lethal" for a in g.world.ais):
            lethal_t = g.now
    w = g.world
    o = w.outcome or {"outcome": "pågår", "t": g.now}
    return o["outcome"], o["t"], first_contact, lethal_t, w.own.sys.hull, \
        w.mission.get("harbor_alarms", w.mission.get("enemy_contacts", 0)), sum(a.attacks for a in w.ais if hasattr(a, "attacks"))


res = Counter()
for s in seeds:
    out, t, fc, lt, hull, cont, att = run(s)
    res[out] += 1
    print(f"frö {s}: {out} efter {t // 60} min, första kontakt {fc}s, skarpt {lt and lt // 60} min, "
          f"skrov {hull:.2f}, jagarkontakter {cont}, anfall {att}")
print(dict(res))
