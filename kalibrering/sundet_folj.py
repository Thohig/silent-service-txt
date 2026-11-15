"""Grindtricket i Sundet: följ ett fartyg in, foto, följ ett ut.
Utan --följ läser boten sanningen; med --följ används navigatörens `följ S-x`.
Användning: sundet_folj.py [frön] [--följ] [--trace] [--verbose]

Körs från repots rot: uv run python kalibrering/sundet_folj.py …
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import math
import random
import sys
from collections import Counter

from sim.events import ReportDelivered  # noqa: E402
from sim.game import Game  # noqa: E402
from sim.geo import bearing_to, distance  # noqa: E402
from sim.harbor import HarborDefense  # noqa: E402
from sim.scenario import build_scenario  # noqa: E402
from sim.stations.navigation import NavigationStation  # noqa: E402
from sim.stations.sonar_room import SonarRoom  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
seeds = range(int(args[0])) if args else range(8)
trace = "--trace" in sys.argv
verbose = "--verbose" in sys.argv
ASTERN = 0.3
crew = "--följ" in sys.argv          # följer med navigatörens `följ S-x` i stället för sanningen


def run(seed):
    g = Game(build_scenario("sundet", random.Random(seed)), seed=seed)
    w = g.world
    nav = g.station(NavigationStation)
    hd = next(sp for sp in w.spawners if isinstance(sp, HarborDefense))
    net = hd.net
    st = {"phase": "approach", "ship": None, "events": [], "look_t": -999}

    def on(ev):
        r = ev.report
        if verbose:
            print(f"{g.clock_str(ev.t)} {r.speaker}: {r.text}")
        if r.type in ("net.caught", "off.photo.done", "sonar.splash", "sonar.ping.fast"):
            st["events"].append((ev.t // 60, r.type))
    g.bus.subscribe(ReportDelivered, on)

    def cmd(c):
        if verbose:
            print(f"   >>> {c}")
        g.command(c)

    def follow(ship, depth):
        s = ship.state
        b = math.radians(s.course)
        tx, ty = s.x - ASTERN * math.sin(b), s.y - ASTERN * math.cos(b)
        o = w.own.state
        d = distance(o.x, o.y, tx, ty)
        ahead = (tx - o.x) * math.sin(b) + (ty - o.y) * math.cos(b)   # >0: vi ligger efter
        c = bearing_to(o.x, o.y, tx, ty) if d > 0.05 else s.course
        v = max(2.0, min(14.0, s.speed + 6 * ahead))
        cmd(f"kurs {round(c) % 360:03d}, fart {round(v)}, djup {depth}")

    while not g.over and g.now < 7 * 3600 + 10:
        o = w.own.state
        ph = st["phase"]
        if g.now == 2:
            cmd("smygmotor, fart 3, djup 120, kurs mot nätet")
        if ph == "approach":
            if not st.get("fixed") and nav.est_y >= 3.0:
                st["fixed"] = 1
                cmd("periskopdjup")
            if st.get("fixed") == 1 and o.depth <= 18:
                st["fixed"] = 2
                cmd("fix")
            if st.get("fixed") == 2 and nav.uncertainty() < 0.2:
                st["fixed"] = 3
                cmd("djup 120, fart 1")             # vänta på ett fartyg in
            if st.get("fixed") == 3 and g.now % 60 == 0:
                hx, hy = net.gate_x, net.y - 4.5           # väntpunkt rakt söder om grinden
                d = distance(o.x, o.y, hx, hy)
                if d > 0.25:
                    cmd(f"kurs {round(bearing_to(o.x, o.y, hx, hy)) % 360:03d}, fart 3")
                else:
                    cmd("fart 1")
            inbound = [v for v in w.contacts if v.kind == "merchant" and not v.sunk
                       and abs(((v.state.course + 180) % 360) - 180) < 30 and v.state.y < o.y + 0.5]
            if "--dbg" in sys.argv and g.now % 120 == 0 and 5400 < g.now < 9000:
                print(g.clock_str(), st.get("fixed"), round(o.x, 2), round(o.y, 2),
                      [(v.id, round(v.state.y, 2), round(distance(v.state.x, v.state.y, o.x, o.y), 2))
                       for v in w.contacts if v.kind == "merchant"])
            for v in inbound:
                if crew:
                    if "--dbg2" in sys.argv and distance(v.state.x, v.state.y, o.x, o.y) < 0.6 and g.now % 20 == 0:
                        d_ = g.station(SonarRoom).sensor.designate(v.id)
                        print(g.clock_str(), v.id, st.get("fixed"), round(v.state.y - o.y, 2), round(v.state.x - o.x, 2), d_, g.knowledge.track(d_) is not None, sorted(g.knowledge.tracks))
                    if st.get("fixed") == 3 and 0.2 < v.state.y - o.y < 0.45 and \
                            abs(v.state.x - o.x) < 0.4:
                        desig = g.station(SonarRoom).sensor.designate(v.id)
                        if g.knowledge.track(desig) is not None:
                            st["phase"], st["ship"] = "follow_in", v
                            cmd(f"turbin, fart {round(v.state.speed)}, djup 40, följ {desig}")
                            break
                elif distance(v.state.x, v.state.y, o.x, o.y) < 1.5 and st.get("fixed") == 3:
                    st["phase"], st["ship"] = "follow_in", v
                    cmd("turbin")
                    break
        elif ph == "follow_in":
            ship = st["ship"]
            if g.now % 15 == 0 and not crew:
                bottom = w.env.seabed.depth_at(o.x, o.y)
                follow(ship, int(max(17, min(60, bottom - 15))))
            if o.y > net.y + 0.1:
                st["phase"] = "photo"
                st["in_t"] = g.now
                cmd("smygmotor, fart 2, periskopdjup, kurs mot ankarplatsen")
            if st["phase"] == "follow_in" and (ship.kind == "moored" or w.true_range(ship) > 1.5):
                st["phase"] = "approach"    # tappat det
                cmd("smygmotor, fart 2, djup 60")
        elif ph == "photo":
            if g.knowledge.best_photo is not None and g.knowledge.best_photo >= 2:
                st["phase"] = "wait_out"
                cmd("fart 1, kurs 180")
            elif g.now - st["look_t"] >= 120 and o.depth <= 18:
                st["look_t"] = g.now
                cmd("foto")
        elif ph == "wait_out":
            if g.now % 60 == 0:
                hx, hy = net.gate_x, net.y + 0.6
                if distance(o.x, o.y, hx, hy) > 0.15:
                    cmd(f"kurs {round(bearing_to(o.x, o.y, hx, hy)) % 360:03d}, fart 2")
                else:
                    cmd("fart 1")
            outbound = [v for v in w.contacts if v.kind == "merchant" and not v.sunk
                        and abs(((v.state.course - 180 + 180) % 360) - 180) < 40
                        and v.state.y > net.y and distance(v.state.x, v.state.y, o.x, o.y) < 0.6]
            if crew:
                ob = [v for v in outbound if 0.2 < o.y - v.state.y < 0.45]
                if ob:
                    desig = g.station(SonarRoom).sensor.designate(ob[0].id)
                    if g.knowledge.track(desig) is not None:
                        st["phase"], st["ship"] = "follow_out", ob[0]
                        cmd(f"turbin, fart {round(ob[0].state.speed)}, djup 30, följ {desig}")
            elif outbound and outbound[0].state.y < o.y + 0.1:
                st["phase"], st["ship"] = "follow_out", outbound[0]
                cmd("turbin")
        elif ph == "follow_out":
            ship = st["ship"]
            if g.now % 15 == 0 and not crew:
                bottom = w.env.seabed.depth_at(o.x, o.y)
                follow(ship, int(max(17, min(80, bottom - 15))))
            if o.y < net.y - 1.5:
                st["phase"] = "out"
                cmd("smygmotor, fart 5, djup 120, kurs 180")
        if g.suggestion is not None:
            order, text, _ = g.suggestion
            ok = order == "foto" or (st["phase"] == "out" and order.startswith("djup")) or (
                crew and "navigatören" in text and order.startswith("djup"))
            g.command("ja" if ok else "nej")
        g.tick()
        if trace and g.now % 300 == 0:
            b = hd.boats[0]
            print(f"{g.clock_str()} {st['phase']:10} own ({o.x:.2f},{o.y:.2f}) d{o.depth:.0f} v{o.speed:.1f} "
                  f"| PB {b.state} r{w.true_range(b.vessel):.1f} larm {hd.alarms} "
                  f"skepp {st['ship'] and st['ship'].id} r{st['ship'] and round(w.true_range(st['ship']), 2)}")
    o = w.outcome or {"outcome": "pågår", "t": g.now}
    return o["outcome"], o["t"] // 60, g.knowledge.best_photo, hd.alarms, st["phase"], st["events"][:5]


res = Counter()
for s in seeds:
    out = run(s)
    res[out[0]] += 1
    print(f"frö {s}: {out[0]} efter {out[1]} min, foto {out[2] and out[2].label}, larm {out[3]}, "
          f"fas {out[4]}, {out[5]}")
print(dict(res))
