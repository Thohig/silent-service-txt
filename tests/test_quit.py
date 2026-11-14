"""Kommandot avsluta och den korta rapporten över spelsessionen."""
import random
import re

from sim.events import GameEnded
from sim.game import Game
from sim.scenario import default_scenario
from tests.test_torpedo_tracking import _setup


def _game(seed=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    ended = []
    g.bus.subscribe(GameEnded, lambda e: ended.append(e))
    return g, ended


def _rows(summary):
    return dict(summary["session"]["rows"])


def test_avsluta_ends_game_with_report():
    g, ended = _game()
    g.command("kurs 090, fart 8")
    for _ in range(1800):
        g.tick()
    g.command("avsluta")
    assert g.over and len(ended) == 1
    s = ended[0].summary
    assert s["outcome"] == "quit" and "avbrutit patrullen" in s["text"]
    rows = _rows(s)
    assert rows["Tid i befäl"].startswith("04:30–05:00 (0 h 30 min)")
    assert rows["Order"].startswith("2 givna")
    # spelet går inte vidare efter avslut
    t = g.now
    g.tick()
    g.command("kurs 180")
    assert g.now == t and g.world.own.state.ordered_course == 90


def test_report_counts_torpedoes_hits_and_contacts():
    g, ended = _game(2)
    _setup(g)
    g.command("eld tub 1 mot S-1")
    for _ in range(400):
        g.tick()
    g.command("avsluta patrullen")
    s = ended[0].summary
    rows = _rows(s)
    assert rows["Torpeder"] == "1 avfyrade, 1 träff, 0 missar"
    assert rows["Kontakter"].startswith("S-1")
    events = [t for _, t in s["session"]["events"]]
    assert any(t.startswith("Tub 1 avfyrad") for t in events)
    assert any("Det var vår torped" in t for t in events)


def test_report_never_reveals_truth_and_is_short():
    for seed in range(1, 4):
        g, ended = _game(seed)
        bot_t = 0
        for i in range(3 * 3600):
            g.tick()
            if g.suggestion and g.suggestion[2] > bot_t:
                bot_t = g.suggestion[2]
                g.command("ja")
            if g.over:
                break
        if not g.over:
            g.command("avsluta")
        session = ended[0].summary["session"]
        assert len(session["events"]) <= 8
        texts = [v for _, v in session["rows"]] + [t for _, t in session["events"]]
        for t in texts:
            assert not re.search(r"\b(T|DD|D)\d+\b", t), t


def test_session_report_also_on_normal_ending():
    g, ended = _game()
    g.world.end("patrol_end")
    g.tick()
    assert ended and "session" in ended[0].summary
