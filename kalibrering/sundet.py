"""Genom sundet: bot med besättningens verktyg (eller --ja, --orakel som läser sanningen).
Användning: sundet.py [frön] [--ja | --orakel] [--verbose] [--trace]

Körs från repots rot: uv run python kalibrering/sundet.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import random
import sys
from collections import Counter

from sim.events import ReportDelivered  # noqa: E402
from sim.game import Game  # noqa: E402
from sim.geo import distance  # noqa: E402
from sim.harbor import HarborDefense  # noqa: E402
from sim.scenario import build_scenario  # noqa: E402
from sim.stations.navigation import NavigationStation  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
seeds = range(int(args[0])) if args else range(8)
if "--från" in " ".join(sys.argv): seeds = range(5, 8)
verbose = "--verbose" in sys.argv
yes_bot = "--ja" in sys.argv
oracle = "--orakel" in sys.argv     # läser sanningen: patrullbåtens avstånd och grinden
TR0, TR1 = [int(a.split("=")[1].split(",")[i]) for a in sys.argv if a.startswith("--tr=") for i in (0, 1)] or (0, -1)


def run(seed):
    g = Game(build_scenario("sundet", random.Random(seed)), seed=seed)
    w = g.world
    nav = g.station(NavigationStation)
    hd = next(sp for sp in w.spawners if isinstance(sp, HarborDefense))
    st = {"gate": None, "phase": "in", "look_t": -999, "through": False, "events": []}

    def on(ev):
        r = ev.report
        if verbose:
            print(f"{g.clock_str(ev.t)} {r.speaker}: {r.text}")
        if r.type == "sonar.bearing":
            st.setdefault("strength", {})[r.data["designation"]] = (ev.t, r.data["strength"])
        if r.type == "off.periscope.net":
            st["gate"] = (ev.t, r.data["gate_open"], r.data["gate_bearing"], r.data["range"])
        if r.type in ("net.caught", "off.photo.done", "sonar.splash", "sonar.ping.fast"):
            st["events"].append((ev.t // 60, r.type))
    g.bus.subscribe(ReportDelivered, on)

    def cmd(c):
        if verbose:
            print(f"   >>> {c}")
        g.command(c)

    while not g.over and g.now < 5 * 3600 + 10:
        if yes_bot:
            if g.suggestion is not None:
                g.command("ja")
            g.tick()
            continue
        o = w.own.state
        wp = g.knowledge.waypoints["Nätet"]
        dnet = distance(nav.est_x, nav.est_y, wp.x, wp.y)
        day = w.env.is_day(g.now)
        photo = g.knowledge.best_photo
        if g.now == 2:
            cmd("smygmotor, fart 3, djup 120, kurs mot nätet")
        hunted = g.knowledge.hunted(g.now)
        if hunted and st["phase"] in ("in", "wait", "gate"):
            st["phase"] = "evade"
            st["evade_t"] = g.now
            cmd("djup 150, turbin, fart 12, kurs 180")
        if st["phase"] == "evade":
            if hunted:
                st["evade_t"] = g.now
            elif g.now - st["evade_t"] > 600:
                st["phase"] = "in"
                cmd("smygmotor, fart 3, djup 120, kurs mot nätet")
        elif st["phase"] == "in":
            if not st.get("fixed") and nav.est_y >= 3.0 and nav.uncertainty() > 0.25:
                st["fixed"] = True              # fix långt ute, innan patrullbåten
                cmd("periskopdjup")
            if st.get("fixed") is True and o.depth <= 18:
                st["fixed"] = "tar"
                cmd("fix")
            if st.get("fixed") == "tar" and nav.uncertainty() < 0.2:
                st["fixed"] = "klar"
                cmd("djup 120, kurs mot nätet")
            # andra fixen nära kusten (landmärken, kort), om patrullbåten inte är nära
            past_screen = o.y > hd.boats[0].box[3] + 0.2 if oracle else dnet < 2.4
            if st.get("fixed") == "klar" and past_screen and nav.uncertainty() > 0.15 \
                    and not st.get("holding"):
                st["fixed"] = True
                cmd("periskopdjup")
            # patrullbåten nära enligt plottet: vänta tyst tills den gått förbi
            strong = {d for d, (t, sgl) in st.get("strength", {}).items()
                      if g.now - t < 90 and sgl == "stark"}
            near = [d for d, t in g.knowledge.tracks.items() if t.threat and d in strong
                    and "handels" not in t.classification and "ankar" not in t.classification]
            if oracle:
                # vänta söder om skärmen tills båten är långt bort, korsa sedan i 5 kn
                y0 = hd.boats[0].box[1]
                far_enough = all(w.true_range(b.vessel) > 2.2 for b in hd.boats)
                if o.y < y0 - 0.4 and not far_enough:
                    near = hd.boats
                else:
                    near = []                   # i skärmen: fortsätt
            if near and not st.get("holding") and st.get("fixed") != "tar":
                st["holding"] = True
                if oracle:
                    cmd("fart 1, djup 120")
                else:
                    cmd("fart 1")
            elif not near and st.get("holding"):
                st["holding"] = False
                cmd(("fart 5" if oracle else "fart 3") + ", kurs mot nätet")
            if g.now % 300 == 150 and dnet > 0.4:
                cmd("kurs mot nätet")
                if o.ordered_depth <= 18 and nav.uncertainty() < 0.3 and dnet > 1.5:
                    cmd("djup 120")
            if dnet <= 0.4:
                st["phase"] = "wait"
                cmd("fart 1")
        elif st["phase"] == "wait":
            if day and o.ordered_depth > 17:
                cmd("periskopdjup")
            if day and o.depth <= 18 and g.now - st["look_t"] >= 150:
                st["look_t"] = g.now
                cmd("periskop")
            gate = st["gate"]
            if oracle and day and hd.net.gate_open(g.now) and o.depth <= 18 and \
                    all(w.true_range(b.vessel) > 1.0 for b in hd.boats):
                from sim.geo import bearing_to
                gb = bearing_to(o.x, o.y, hd.net.gate_x, hd.net.y)
                gate = (g.now, True, gb, 0)
            if gate and g.now - gate[0] < 20 and gate[1]:
                cmd(f"kurs {round(gate[2]) % 360:03d}, fart 3")
                st["phase"] = "gate"
                st["gate_t"] = g.now
        elif st["phase"] == "gate":
            if o.y > hd.net.y + 0.05 or g.now - st["gate_t"] > 900:
                st["phase"] = "photo" if o.y > hd.net.y else "wait"
                st["through"] = o.y > hd.net.y
                if st["through"]:
                    cmd("kurs mot ankarplatsen, fart 2")
        elif st["phase"] == "photo":
            if photo is not None and photo >= 2:
                st["phase"] = "out"
                cmd("fart 3")
            elif g.now - st["look_t"] >= 240 and o.depth <= 18:
                st["look_t"] = g.now
                cmd("periskop")
        if g.suggestion is not None:
            order, text, _ = g.suggestion
            nav_s = "navigatören" in text
            ok = order == "foto" or order == "skenmål" or (
                nav_s and (order.startswith("djup") or
                           (order.startswith("kurs") and st["phase"] in ("in", "out"))))
            if nav_s and not hunted and order in ("fix", "periskopdjup") and st["phase"] in ("in", "out"):
                ok = True                   # fix när ingen jagar oss
            if st["phase"] in ("wait", "gate", "photo") and order.startswith("djup"):
                ok = False                  # stanna på periskopdjup vid nätet
            if st["phase"] == "evade" and order.startswith(("djup", "turbin")) and not nav_s:
                ok = True                   # maskinens djupt och fort
            if st["phase"] == "in" and order == "fix" and g.world.own.state.depth <= 18:
                ok = not hunted
            g.command("ja" if ok else "nej")
        g.tick()
        if "--trace" in sys.argv and (g.now % 300 == 0 or (TR0 <= g.now <= TR1 and g.now % 30 == 0)):
            o = w.own.state
            b = hd.boats[0]
            print(f"{g.clock_str()} {st['phase']:5} own ({o.x:.2f},{o.y:.2f}) d{o.depth:.0f} v{o.speed:.1f} "
                  f"est ({nav.est_x:.2f},{nav.est_y:.2f}) σ{nav.uncertainty():.2f} net y{hd.net.y:.2f} "
                  f"bot{w.env.seabed.depth_at(o.x, o.y):.0f} | PB {b.state} r{w.true_range(b.vessel):.1f} "
                  f"larm {hd.alarms} grind {"öppen" if hd.net.gate_open(g.now) else "stängd"} hold {st.get("holding")} PBlc {g.now - b.last_contact_t} PBd {round(b.datum.sigma,2) if b.datum else None}")
    o = w.outcome or {"outcome": "pågår", "t": g.now}
    return (o["outcome"], o["t"] // 60, g.knowledge.best_photo, hd.alarms, st["through"],
            st["events"][:6], round(w.own.sys.hull, 2))


res = Counter()
for s in seeds:
    out = run(s)
    res[out[0]] += 1
    print(f"frö {s}: {out[0]} efter {out[1]} min, foto {out[2] and out[2].label}, larm {out[3]}, "
          f"genom grinden {out[4]}, skrov {out[6]}, {out[5]}")
print(dict(res))
