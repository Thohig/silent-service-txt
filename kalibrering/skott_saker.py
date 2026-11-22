"""Provskjutning på säkra lösningar: ja-boten spelar scenariot; varje gång plottet har en säker
lösning på ett fartyg (högst var 5:e min per kontakt) spelas fröet om till den sekunden och
kaptenen skjuter (`eld tub 1 mot S-n`, två gånger om torpedrummet frågar, eller `salva mot S-n`).
Spärren för djup och fart är av i omspelningen (`legal` i raden säger om läget var tillåtet).
Mäter lösningens fel mot sanningen, siktfelet mot den ideala kursen och utfallet.

Användning: skott_saker.py scenarier frön minuter typer [max skott per spel] [ut.jsonl]
  typer bland 53-61, SET-53 och salva (tre 53-61). Frön som 1-16 eller 1,4,7.
  T.ex. skott_saker.py kuba,konvoj-kort,sundet-in,krig-kort 1-8 150 53-61,salva 8   (~10 min, 10 kärnor)
Sammanfattningen skrivs ut; raderna (en per skott, JSON) till filen om den anges.

Körs från repots rot: PYTHONHASHSEED=0 uv run python kalibrering/skott_saker.py …
(fast hashfrö: omspelningen måste ge exakt samma spel; `det_ok` i raden visar att den gjorde det)
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import json, math, random, sys, time
from multiprocessing import Pool

from sim.events import ReportDelivered
from sim.game import Game
from sim.geo import distance, angle_diff, bearing_to
from sim.scenario import build_scenario
from sim.stations import TorpedoRoom
from sim.stations.sonar_room import SonarRoom
from sim.reports import Quality
import sim.stations.torpedo_room.firing as firing
from sim.weapons import Torpedo, hull_pass, TORPEDO_TYPES
from sim.firecontrol import intercept
from sim.geo import velocity

CHECK_S = 10
LIMITS = (firing.MAX_LAUNCH_DEPTH, firing.MAX_LAUNCH_SPEED)
GAP_S = 300


def new_game(key, seed):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    due = []
    reps = []

    def on(e):
        reps.append((g.now, e.report))
        if e.report.kind == "suggest":
            due.append(g.now + 20)
    g.bus.subscribe(ReportDelivered, on)
    return g, due, reps


def bot_step(g, due):
    g.tick()
    if due and g.now >= due[0]:
        due.pop(0)
        if g.active_suggestion():
            g.command("ja")


def truth_map(g):
    sensor = g.station(SonarRoom).sensor
    out = {}
    for v in g.world.contacts:
        if v.side == "own" or not v.is_ship or v.sunk:
            continue
        d = sensor.designation_of(v.id)
        if d:
            out[d] = v
    return out


def candidates(args):
    key, seed, minutes, max_shots = args
    g, due, _ = new_game(key, seed)
    last = {}
    out = []
    while g.now < minutes * 60 and not g.over:
        bot_step(g, due)
        if g.now % CHECK_S:
            continue
        tm = truth_map(g)
        for tr in g.knowledge.tracks.values():
            sol = tr.solution
            if sol is None or not tr.held or sol.quality != Quality.SAKER:
                continue
            v = tm.get(tr.designation)
            if v is None:
                continue
            if g.now - last.get(tr.designation, -10**9) < GAP_S:
                continue
            last[tr.designation] = g.now
            out.append((key, seed, g.now, tr.designation, sol.x, sol.y))
    # sprid skotten över spelet
    if len(out) > max_shots:
        rnd = random.Random(seed)
        out = sorted(rnd.sample(out, max_shots), key=lambda c: c[2])
    return out


def shoot(args):
    (key, seed, t_fire, desig, sx, sy), typ = args
    g, due, reps = new_game(key, seed)
    while g.now < t_fire:
        bot_step(g, due)
        if g.over:
            return {"err": "över före skottet"}
    tr = g.knowledge.track(desig)
    det_ok = tr is not None and tr.solution is not None and \
        abs(tr.solution.x - sx) < 1e-9 and abs(tr.solution.y - sy) < 1e-9
    tm = truth_map(g)
    v = tm.get(desig)
    if v is None:
        return {"err": "inget mål"}
    o = g.world.own.state
    tor = g.station(TorpedoRoom)
    # fältet före skottet
    legal = o.depth <= LIMITS[0] and o.speed <= LIMITS[1]
    firing.MAX_LAUNCH_DEPTH, firing.MAX_LAUNCH_SPEED = 10**6, 10**6
    for t in tor.tubes:
        t.load, t.loading = None, None
    if typ == "salva":
        for t in tor.tubes[:3]:
            t.load = "53-61"
    else:
        tor.tubes[0].load = typ
    n_rep0 = len(reps)
    old = tr.solution
    sol = g.knowledge.resolve(desig, g.now, g.own_position_estimate())
    if sol is None:
        obs_all = len(tr.observations); obs_new = sum(o.t >= tr.tma_from_t for o in tr.observations)
        return {"err": "resolve None", "key": key, "seed": seed, "t": t_fire, "desig": desig,
                "old_t": old.t if old else None, "old_q": old.quality.label if old else None,
                "tma_from_t": tr.tma_from_t, "obs_all": obs_all, "obs_new": obs_new, "now": g.now}
    ex, ey = g.own_position_estimate()
    rx_s, ry_s = sol.x - ex, sol.y - ey
    rx_t, ry_t = v.state.x - o.x, v.state.y - o.y
    r_true = math.hypot(rx_t, ry_t)
    spec = TORPEDO_TYPES["53-61" if typ == "salva" else typ]
    # ideal kurs med sanningen
    tvx, tvy = velocity(v.state.course, v.state.speed)
    ideal = intercept(rx_t, ry_t, tvx * 3600, tvy * 3600, spec.speed)
    aim = tor._aim(sol, "53-61" if typ == "salva" else typ)
    row = dict(key=key, seed=seed, t=t_fire, desig=desig, typ=typ, kind=v.kind, side=v.side,
               det_ok=det_ok, legal=legal, depth=o.depth, own_speed=o.speed,
               q=sol.quality.label, r_true=r_true, r_sol=math.hypot(rx_s, ry_s),
               r_sig=sol.range_sigma, rel_err=math.hypot(rx_s - rx_t, ry_s - ry_t),
               brg_err=angle_diff(math.degrees(math.atan2(rx_s, ry_s)), math.degrees(math.atan2(rx_t, ry_t))),
               crs_true=v.state.course, crs_sol=sol.course, crs_err=angle_diff(sol.course, v.state.course),
               crs_sig=sol.course_sigma, spd_true=v.state.speed, spd_sol=sol.speed, spd_sig=sol.speed_sigma,
               nav_err=math.hypot(ex - o.x, ey - o.y),
               aim=aim[0] if aim else None, run_s=aim[1] if aim else None,
               ideal=ideal[0] if ideal else None, target_depth=v.depth)
    if aim and ideal:
        row["aim_err"] = angle_diff(aim[0], ideal[0])
    before = {id(c) for c in g.world.contacts}
    order = f"salva mot {desig}" if typ == "salva" else f"eld tub 1 mot {desig}"
    new = lambda: [c for c in g.world.contacts if isinstance(c, Torpedo) and c.side == "own" and id(c) not in before]
    for _ in range(3):
        g.command(order)
        if new():
            break
    torps = new()
    if not torps:
        row["res"] = "ej skjuten"
        for _ in range(10):
            g.tick()
        row["reports"] = [(r.type, str(r.data)[:160]) for _, r in reps[n_rep0:]]
        return row
    tps = torps
    tp = torps[-1]
    row["fired_course"] = tp.state.course
    min_d, min_pass = 9.9, 99.0
    c0 = v.state.course; s0 = v.state.speed
    maneuver = 0.0
    sunk_before = set(x.id for x in g.world.contacts if x.sunk)
    t0 = g.now
    along = None
    while g.now < t0 + 1200 and not g.over:
        p0 = (tp.state.x, tp.state.y)
        bot_step(g, due)
        if not tp.done:
            pass
        d = distance(tp.state.x, tp.state.y, v.state.x, v.state.y)
        if d < min_d and not v.sunk:
            min_d = d
            # var passerade torpeden: längs målets kurs (+ för om)
            c = math.radians(v.state.course)
            dx, dy = tp.state.x - v.state.x, tp.state.y - v.state.y
            along = (dx * math.sin(c) + dy * math.cos(c)) * 1852
            across = (dx * math.cos(c) - dy * math.sin(c)) * 1852
        if not v.sunk:
            maneuver = max(maneuver, abs(angle_diff(v.state.course, c0)))
        if all(x.done for x in tps) and g.now > t0 + 5:
            # låt rapporterna komma
            for _ in range(90):
                bot_step(g, due)
            break
    sunk = [x for x in g.world.contacts if x.sunk and x.id not in sunk_before and x.is_ship
            and not isinstance(x, Torpedo) and x.side != "own"]
    if v.sunk:
        res = "träff"
    elif sunk:
        res = "annat sänkt"
    elif any(x.dud for x in tps) and g.world.mission.get("duds"):
        res = "klick?"
    elif tp.premature_nm is not None and tp.run_nm >= tp.premature_nm - 0.01:
        res = "förtidig"
    else:
        res = "miss"
    row.update(res=res, min_d_m=min_d * 1852, along_m=along, maneuver=maneuver,
               spd_change=abs(v.state.speed - s0), dud=tp.dud, premature=tp.premature_nm,
               run_end=g.now - t0, other=[x.kind for x in sunk],
               reports=[(g_t - t0, r.type, str(r.data)[:200]) for g_t, r in reps[n_rep0:]
                        if r.type.startswith("torp") or "hit" in r.type or "sink" in r.type
                        or r.type.startswith("sonar.torp") or "explo" in r.type])
    return row


def summary(rows) -> None:
    import collections
    import statistics as st
    bad = [r for r in rows if "err" in r]
    rows = [r for r in rows if "err" not in r and r["res"] != "ej skjuten"]
    if bad:
        print(f"utan skott: {collections.Counter(r['err'] for r in bad)}")
    for typ in sorted({r["typ"] for r in rows}):
        v = [r for r in rows if r["typ"] == typ]
        print(f"== {typ}: {len(v)} skjutna, träff {sum(r['res'] == 'träff' for r in v) / len(v):.0%}, "
              f"{dict(collections.Counter(r['res'] for r in v))}")
        for k in sorted({r["key"] for r in v}):
            x = [r for r in v if r["key"] == k]
            s = [r for r in x if r["maneuver"] <= 15]
            print(f"  {k:12} n={len(x):3} träff {sum(r['res'] == 'träff' for r in x) / len(x):4.0%}"
                  f"  målet girade {1 - len(s) / len(x):4.0%}"
                  f"  träff på rakt mål {sum(r['res'] == 'träff' for r in s) / max(1, len(s)):4.0%}")
    v = [r for r in rows if r["typ"] != "salva"]
    if v:
        z = [r["rel_err"] / r["r_sig"] for r in v]
        zc = [abs(r["crs_err"]) / max(r["crs_sig"], 1e-3) for r in v if r["spd_true"] > 3]
        print(f"lösningarna: läge > 3σ {sum(x > 3 for x in z) / len(z):.0%}, "
              f"kurs > 3σ {sum(x > 3 for x in zc) / max(1, len(zc)):.0%} (mål > 3 kn), "
              f"siktfel median {st.median(abs(r.get('aim_err') or 0) for r in v):.2f}°")


def main():
    keys = sys.argv[1].split(",")
    a = sys.argv[2]
    seeds = list(range(int(a.split("-")[0]), int(a.split("-")[1]) + 1)) if "-" in a         else [int(x) for x in a.split(",")]
    minutes = int(sys.argv[3])
    types = sys.argv[4].split(",")
    max_shots = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    out = open(sys.argv[6], "w") if len(sys.argv) > 6 else None
    t = time.time()
    rows = []
    with Pool() as p:
        cands = [c for cs in p.imap_unordered(candidates, [(k, s, minutes, max_shots) for k in keys for s in seeds])
                 for c in cs]
        print(f"{len(cands)} säkra lägen på {time.time() - t:.0f} s", file=sys.stderr)
        for row in p.imap_unordered(shoot, [(c, ty) for c in cands for ty in types]):
            rows.append(row)
            if out:
                print(json.dumps(row, ensure_ascii=False, default=str), file=out, flush=True)
    summary(rows)
    print(f"{time.time() - t:.0f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
