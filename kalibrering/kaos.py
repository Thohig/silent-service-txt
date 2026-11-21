"""Kaosbot: en kapten som ger slumpade, udda och felaktiga order (kurs 999, fart -3, djup 1000,
ladda tub 2 banan, kurs mot månen, flera order på en rad …) var 10–150:e s och svarar ja, nej eller
jest på förslagen efter 2–40 s. Bygger vyerna varje minut. Letar efter undantag, oifyllda fält,
punkt som decimaltecken, kurser utan tre siffror, NaN i egen ubåts tillstånd, sanningens id:n och
samma rapporttyp 6+ gånger samma minut. Hela rapportflödet till logs/kaos/<scenario>-<frö>.log.

Användning (från repots rot):
    uv run python kalibrering/kaos.py kuba,arktis 1,2,3 [minuter]     # NPROC=n processer (4)
Provkörd 2026-11-21: 20 scenarier × 3 frön à 150 min, inga undantag (se kalibrering/README.md).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # repots rot
import sys, random, re, traceback, math, os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario

OUT = _Path(__file__).resolve().parents[1] / "logs" / "kaos"
ORDERS = [
    "kurs 090", "kurs 360", "kurs 0", "kurs 999", "kurs -10", "kurs 45,5", "fart 0", "fart 30", "fart 5,5",
    "fart -3", "fart 99", "stopp", "back 3", "full back", "halv back", "djup 0", "djup 18", "djup 100",
    "djup 299", "djup 320", "djup 460", "djup 1000", "djup -5", "periskopdjup", "antenndjup", "ytläge",
    "nödblåsning", "smygmotor", "turbin", "stäng reaktorn", "starta reaktorn", "ventilera", "maskin",
    "läget", "position", "fix", "stjärnfix", "bottenfix", "ström", "ekolod", "isekolod", "vak",
    "drivstationen", "botten", "trimma", "trim stopp", "trim", "ligg still", "periskop", "periskop 047",
    "periskop S-1", "periskop upp", "periskop ned", "förstoring hög", "radar", "foto", "aktiv sonar",
    "sänd rapport", "sänd kort rapport", "avlyssna", "radio moskva", "radio", "torped", "torpeder",
    "eld S-1", "eld S-1", "salva S-2", "eld tub 1 kurs 045", "eld tub 9 kurs 045", "ladda tub 1 SET-53",
    "ladda tub 3 53-62T", "ladda tub 7 T-5", "ladda tub 2 banan", "kapa tråden", "skenmål",
    "kärnvapenråd", "S-1", "S-2", "S-9", "S-0", "följ S-1", "anfall S-1", "anfall S-7", "kurs mot nätet",
    "kurs mot ankarplatsen", "kurs mot månen", "väntläget", "farleden", "starpom har befälet",
    "jag har befälet", "lägesrapport", "svara", "sov", "väck mig 04:30", "väck mig 25:99", "tid 10",
    "tid 60", "tid 1", "tid 5", "förslag", "annat förslag", "förslag sonar", "förslag radio", "ja", "nej",
    "jest", "hjälp", "", "   ", ",,,", "och och", "kurs 090 och fart 5; djup 100", "fart 5,5, kurs 120",
    "KURS 180", "Djup  60", "ö", "sänd", "titta 400", "vrid periskopet 270", "låg förstoring",
    "avbryt uppdraget", "nej", "kurs 270, djup 40, periskop, foto, sänd rapport",
]
TRUTH_ID = re.compile(r"\b(DD|T|SS|M|CV|P|AC|N)\d+\b")
DOT_DEC = re.compile(r"\b\d+\.\d+\s*(nm|kn|m\b|knop|sjömil|meter|grader|°)")
SHORT_COURSE = re.compile(r"\bkurs (\d{1,2})\b")


def run(args):
    key, seed, minutes = args
    rng = random.Random(f"{key}:{seed}")
    log = open(f"{OUT}/{key}-{seed}.log", "w")
    issues = []
    try:
        g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    except Exception:
        return key, seed, "start", 0, [traceback.format_exc()]
    start = g.now
    per_min = Counter()

    def on(e):
        r = e.report
        txt = r.text or ""
        log.write(f"{g.clock_str()} [{r.kind}] {r.type}: {txt}\n")
        per_min[(g.now // 60, r.type)] += 1
        if per_min[(g.now // 60, r.type)] == 6 and not r.type.startswith(("sonar.bearing", "torp.countdown", "order.", "system.")):
            issues.append(f"{g.clock_str()} spam: {r.type}")
        for bad in ("None", " nan", "{", "}", "inf ", "Traceback", "[]", "()"):
            if bad in txt:
                issues.append(f"{g.clock_str()} '{bad}' i {r.type}: {txt[:200]}")
        m = TRUTH_ID.search(txt)
        if m and not re.search(r"\b[A-Z]-\d", txt[max(0, m.start()-2):m.end()]):
            issues.append(f"{g.clock_str()} sanningsid? {m.group()} i {r.type}: {txt[:200]}")
        if DOT_DEC.search(txt) and r.type not in ("system.help",):
            issues.append(f"{g.clock_str()} punktdecimal i {r.type}: {txt[:200]}")
        mm = SHORT_COURSE.search(txt)
        if mm and r.type not in ("system.help", "order.unknown"):
            issues.append(f"{g.clock_str()} kurs utan tre siffror i {r.type}: {txt[:200]}")
    g.bus.subscribe(ReportDelivered, on)
    o = g.world.own.state
    next_order = start + rng.randint(5, 60)
    sugg_reply = None
    try:
        for _ in range(minutes * 60):
            if g.over:
                break
            g.tick()
            t = g.now
            sug = g.active_suggestion()
            if sug and sugg_reply is None:
                sugg_reply = t + rng.randint(2, 40)
            if sugg_reply and t >= sugg_reply:
                sugg_reply = None
                if g.active_suggestion():
                    o_ = rng.choice(["ja", "ja", "ja", "nej", "jest"])
                    log.write(f"{g.clock_str()} *** KAPTEN: {o_}\n")
                    g.command(o_)
            if t >= next_order:
                cmd = rng.choice(ORDERS)
                if cmd in ("avbryt uppdraget",) and rng.random() < 0.7:
                    cmd = "läget"
                log.write(f"{g.clock_str()} *** KAPTEN: {cmd}\n")
                g.command(cmd)
                next_order = t + rng.randint(10, 150)
            if (t - start) % 60 == 0:
                g.chart(); g.profile(); g.sonar(); g.systems(); g.status()
            for name in ("depth", "speed", "course"):
                v = getattr(o, name, 0.0)
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    issues.append(f"{g.clock_str()} {name} = {v}")
                    raise RuntimeError("nan")
    except Exception:
        issues.append(f"{g.clock_str()} UNDANTAG:\n{traceback.format_exc()}")
    out = (g.world.outcome or {}).get("outcome") or "pågår"
    log.write(f"\n=== {key} {seed}: {out} {(g.now-start)//60} min\n" + "\n".join(issues) + "\n")
    log.close()
    return key, seed, out, (g.now - start) // 60, issues


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    keys = sys.argv[1].split(",")
    seeds = [int(s) for s in sys.argv[2].split(",")]
    minutes = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    with ProcessPoolExecutor(int(os.environ.get("NPROC", 4))) as ex:
        for key, s, out, mins, issues in ex.map(run, [(k, s, minutes) for k in keys for s in seeds]):
            uniq = list(dict.fromkeys(i.split(" ", 1)[1][:150] if " " in i else i for i in issues))
            print(f"\n## {key} {s}: {out}, {mins} min, {len(issues)} anm ({len(uniq)} unika)", flush=True)
            for i in uniq[:15]:
                print("  ", i)
