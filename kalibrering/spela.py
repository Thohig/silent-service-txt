"""Spela ett scenario med en bot och skriv rapportflödet som JSON-rader (en per rapport, sist utfallet).

Används av `skillnad.py` för att köra samma frö med olika versioner av koden: första argumentet är
roten vars `sim/` ska importeras (arbetskopian eller en utpackad äldre version).

Användning: spela.py rot scenario frö [ja|passiv] [minuter]
Raderna: {"t", "klocka", "typ", "roll", "text", "x", "y"} (egen ubåts sanna läge vid rapporten),
sist {"utfall": ..., "t": ...}. Ja-boten svarar ja 20 s efter varje förslag, som kontroll.py.
"""
import json
import random
import sys

JA_EFTER_S = 20


def play(root: str, key: str, seed: int, bot: str = "ja", minutes: int = 15 * 60, out=sys.stdout):
    sys.path.insert(0, root)
    from sim.events import ReportDelivered
    from sim.game import Game
    from sim.scenario import build_scenario

    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    due: list[int] = []

    def on(e):
        r = e.report
        o = g.world.own.state
        print(json.dumps({"t": g.now, "klocka": g.clock_str(), "typ": r.type, "roll": r.role,
                          "text": r.text, "x": round(o.x, 4), "y": round(o.y, 4)},
                         ensure_ascii=False), file=out)
        if bot == "ja" and r.kind == "suggest":
            due.append(g.now + JA_EFTER_S)

    g.bus.subscribe(ReportDelivered, on)
    for _ in range(minutes * 60):
        if g.over:
            break
        g.tick()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                print(json.dumps({"t": g.now, "klocka": g.clock_str(), "typ": "KAPTEN",
                                  "roll": "", "text": "ja " + g.active_suggestion()[0]},
                                 ensure_ascii=False), file=out)
                g.command("ja")
    print(json.dumps({"utfall": (g.world.outcome or {}).get("outcome") or "pågår", "t": g.now},
                     ensure_ascii=False), file=out)


if __name__ == "__main__":
    a = sys.argv[1:]
    play(a[0], a[1], int(a[2]), a[3] if len(a) > 3 else "ja", int(a[4]) if len(a) > 4 else 15 * 60)
