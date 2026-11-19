"""Vädret (V5): sjögången ändras under uppdraget, och besättningen märker det med sina
instrument (utkiken, periskopet, sonarens havsbrus)."""
import random

from sim.environment import Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.weather import STEP_EVERY_S, Weather


def _run(w: Weather, sea: int, hours: float, seed: int) -> list[int]:
    env = Environment(sea_state=sea)
    w.rng = random.Random(seed)
    out = []
    for t in range(int(hours * 3600)):
        w.step(env, t)
        out.append(env.sea_state)
    return out


def test_sea_changes_one_step_at_a_time_and_seldom_within_bounds():
    for seed in range(8):
        seq = _run(Weather(2, 5), 3, 8, seed)
        changes = [i for i in range(1, len(seq)) if seq[i] != seq[i - 1]]
        assert all(abs(seq[i] - seq[i - 1]) == 1 for i in changes)
        assert all(2 <= s <= 5 for s in seq)
        gaps = [b - a for a, b in zip(changes, changes[1:])]
        assert all(g >= STEP_EVERY_S[0] for g in gaps)


def test_sea_follows_the_forecast_over_seeds():
    ends = [_run(Weather(2, 6, trend=((0, 3), (3600, 5))), 3, 6, seed)[-1] for seed in range(12)]
    assert sum(e >= 4 for e in ends) >= 9


def test_no_rng_means_fixed_sea():
    env = Environment(sea_state=4)
    w = Weather(2, 6, trend=((0, 6),))
    for t in range(20000):
        w.step(env, t)
    assert env.sea_state == 4


def test_game_gives_the_weather_its_own_stream_and_same_seed_same_weather():
    def seas(seed):
        g = Game(build_scenario("konvoj", random.Random(seed)), seed=seed)
        assert g.world.env.weather is not None and g.world.env.weather.rng is not None
        out = []
        for t in range(3 * 3600):
            g.world.env.weather.step(g.world.env, t)
            out.append(g.world.env.sea_state)
        return out
    assert seas(1) == seas(1)
    assert any(len(set(seas(s))) > 1 for s in range(4))


def test_orders_carry_the_forecast():
    for key in ("kuba", "konvoj"):
        sc = build_scenario(key, random.Random(0))
        assert "VÄDER:" in sc.secret_order and sc.world.env.weather is not None


def _game():
    g = Game(build_scenario("kuba", random.Random(2)), seed=2)
    w = g.world
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    for ai in w.ais:
        ai.can_force = False
    w.env.weather = None
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_sonar_hears_the_sea_rise_and_says_so():
    g, reports = _game()
    for _ in range(70):
        g.tick()
    g.world.env.sea_state = 5
    for _ in range(130):
        g.tick()
    r = next(r for r in reports if r.type == "sonar.ambient")
    assert r.data["db"] > 0 and "ökat" in r.text and r.speech


def test_periscope_sees_the_sea_has_changed_since_the_last_look():
    g, reports = _game()
    st = g.world.own.state
    st.depth = st.ordered_depth = 17.0
    st.speed = st.ordered_speed = 6.0
    g.world.env.sea_state = 4
    g.command("periskop")
    for _ in range(40):
        g.tick()
    r = next(r for r in reports if r.type == "off.periscope.sea")
    assert r.data["up"] and r.data["sea"] == 4 and "ökat" in r.text


def test_bridge_calls_out_the_sea_getting_up():
    g, reports = _game()
    st = g.world.own.state
    st.depth = st.ordered_depth = 0.0
    for _ in range(30):
        g.tick()
    g.world.env.sea_state = 5
    for _ in range(20):
        g.tick()
    r = next(r for r in reports if r.type == "bridge.sea")
    assert r.data["up"] and "ökar" in r.text
