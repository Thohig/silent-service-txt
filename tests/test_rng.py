"""Slumpen per station (Game.rng_for): samma frö ⇒ samma strömmar, och en ström påverkar
inte de andra (designprincip 6)."""
import random
from pathlib import Path

from sim.game import Game
from sim.scenario import build_scenario

SIM = Path(__file__).resolve().parents[1] / "sim"


def _game(seed=4):
    return Game(build_scenario("ovning", random.Random(seed)), seed=seed, warm_up=False)


def test_streams_are_fixed_by_seed_and_name_and_independent():
    a, b = _game(), _game()
    assert a.rng_for("bridge").random() == b.rng_for("bridge").random()
    assert a.rng_for("bridge") is a.rng_for("bridge")
    for _ in range(50):                          # mycket slump i en station ...
        a.rng_for("navigation").random()
    # ... flyttar inte en annan
    assert a.rng_for("sonar").random() == b.rng_for("sonar").random()
    assert _game(5).rng_for("bridge").random() != _game(4).rng_for("bridge").random()


def test_stations_draw_only_from_their_own_streams():
    for path in (SIM / "stations").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "game.rng." not in text and "game.rng)" not in text, path
        assert "random.Random(" not in text, path
