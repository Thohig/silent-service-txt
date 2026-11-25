"""Regn och dimma (sim/weather.py Showers): sikten, havsbruset, radarn, sonars smatter, mistlurarna och bryggan."""
import random

from sim.environment import Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.weather import Showers


def test_showers_come_and_go_from_their_own_stream():
    sh = Showers(rain_per_h=1.0, fog_per_h=1.0, rng=random.Random(3))
    kinds = set()
    for t in range(0, 12 * 3600, 10):
        sh.step(t)
        kinds.add(sh.kind)
    assert kinds == {None, "rain", "fog"}
    assert Showers(rain_per_h=1.0).kind is None            # utan ström: inget väder


def test_fog_lowers_the_visibility_and_rain_raises_the_sea_noise():
    env = Environment(sea_state=3)
    clear_vis, clear_noise = env.visibility_nm(43200), env.noise_at(0, 0)
    env.showers = Showers(kind="fog", level=0.4)
    assert env.visibility_nm(43200) == 0.4 and env.noise_at(0, 0) == clear_noise
    env.showers = Showers(kind="rain", level=6.0)
    assert env.visibility_nm(43200) == clear_vis and env.noise_at(0, 0) == clear_noise + 6.0
    assert env.raining()


def _game():
    g = Game(build_scenario("kuba", random.Random(2)), seed=2)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_sonar_hears_the_rain_start_and_stop():
    from sim.stations.sonar_room import AMBIENT_EVERY_S
    g, reports = _game()
    g.world.env.showers = Showers(kind=None)
    for _ in range(AMBIENT_EVERY_S + 2):
        g.tick()
    g.world.env.showers = Showers(kind="rain", level=6.0, until=10**9)
    for _ in range(AMBIENT_EVERY_S + 5):
        g.tick()
    r = next(r for r in reports if r.type == "sonar.rain")
    assert r.data["on"] and "Regn på ytan" in r.text and "6 dB" in r.text


def test_merchants_sound_their_foghorns_in_fog_and_sonar_hears_them():
    g = Game(build_scenario("konvoj", random.Random(2)), seed=2)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    g.world.env.showers = Showers(kind="fog", level=0.3, until=10**9)
    o = g.world.own.state
    m = next(v for v in g.world.contacts if v.id.startswith("H"))
    m.state.x, m.state.y = o.x + 1.0, o.y                 # en mistlur hörs bara nära i vattnet
    horns = []
    orig = g.world.emit
    g.world.emit = lambda tr: (horns.append(tr) if tr.kind == "foghorn" else None, orig(tr))[-1]
    for _ in range(300):
        g.tick()
    assert horns
    assert any(r.type == "sonar.foghorn" and "Mistlur" in r.text for r in reports)


def test_the_bridge_sees_the_fog_and_the_periscope_says_it():
    g, reports = _game()
    w = g.world
    w.env.showers = Showers(kind="fog", level=0.5, until=10**9)
    st = w.own.state
    st.depth = st.ordered_depth = 15.0
    g.command("periskop")
    for _ in range(10):
        g.tick()
    assert any(r.type == "off.periscope.up" and "Dimma" in r.text for r in reports)
