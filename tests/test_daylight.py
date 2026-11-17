"""D4: vakthavande om ljuset (utrop, vänta på mörkret) och navigatörens stjärnfix."""
import random

import pytest

from sim.environment import Almanac
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.navigation import (MOON_FIX_SIGMA, PERISCOPE_SEXTANT_F, STAR_FIX_S,
                                     STAR_FIX_SIGMA, NavigationStation)


def _game(clock_h: float, date=(1962, 10, 24), seed=2):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    env = g.world.env
    env.clock_start, env.date = round(clock_h * 3600), date
    g.knowledge.almanac = Almanac.of(env)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, s):
    for _ in range(s):
        g.tick()


def _periscope_depth(g):
    st = g.world.own.state
    st.depth = st.ordered_depth = 15.0
    st.speed = st.ordered_speed = 3.0


@pytest.mark.slow
def test_officer_calls_sunset_and_darkness_in_order():
    """Kvadrat 7, 24 okt: solen går ned omkring 17:30 lokal tid."""
    g, reports = _game(16.75)
    _run(g, 2 * 3600)
    kinds = [r.type for r in reports if r.type.startswith("light.")]
    assert kinds[:3] == ["light.sunset_soon", "light.sunset", "light.dark"]
    dark = next(r for r in reports if r.type == "light.dark")
    assert "Månen" in dark.text or "måne" in dark.text.lower()


def test_wait_for_dark_is_suggested_on_the_surface_with_a_threat():
    g, reports = _game(17.0)
    st = g.world.own.state
    st.depth = st.ordered_depth = 0.0
    g.knowledge.threat_held = lambda: True
    _run(g, 40)
    sug = [r for r in reports if r.type == "light.suggest.wait_dark"]
    assert sug and sug[0].data["order"] == "djup 40" and 0 < sug[0].data["minutes"] <= 45
    calm, calm_reports = _game(17.0)                 # inget hot: inget förslag
    calm.world.own.state.depth = calm.world.own.state.ordered_depth = 0.0
    _run(calm, 40)
    assert not any(r.type == "light.suggest.wait_dark" for r in calm_reports)


def test_star_fix_in_twilight_through_the_periscope():
    g, reports = _game(17.85)                         # nautisk skymning
    lt = g.knowledge.almanac.light(g.now)
    assert -11 <= lt.sun_elev <= -3
    _periscope_depth(g)
    nav = g.station(NavigationStation)
    nav.last_fix_t, nav.fix_sigma = -4 * 3600, 0.5   # osäkert bestick
    g.command("stjärnfix")
    _run(g, STAR_FIX_S + 5)
    done = [r for r in reports if r.type == "nav.starfix.done"]
    assert done and abs(done[0].data["sigma"] - STAR_FIX_SIGMA * PERISCOPE_SEXTANT_F) < 1e-9
    assert nav.fix_sigma < 0.1 and nav.uncertainty() < 0.15


def test_star_fix_refused_in_daylight_and_dark_nights_but_works_by_bright_moonlight():
    for clock, date, ok in ((12.0, (1962, 10, 24), False),    # dag
                            (0.5, (1962, 10, 26), False),     # natt utan måne
                            (23.5, (1962, 10, 13), True)):    # fullmåne högt
        g, reports = _game(clock, date)
        _periscope_depth(g)
        g.command("stjärnfix")
        _run(g, STAR_FIX_S + 5)
        done = [r for r in reports if r.type == "nav.starfix.done"]
        refused = [r for r in reports if r.type == "nav.starfix.refused"]
        assert bool(done) == ok and bool(refused) != ok, (clock, date)
        if ok:
            assert abs(done[0].data["sigma"] - MOON_FIX_SIGMA * PERISCOPE_SEXTANT_F) < 1e-9


def test_navigator_suggests_a_star_fix_in_twilight_when_the_position_is_uncertain():
    g, reports = _game(17.75)
    _periscope_depth(g)
    nav = g.station(NavigationStation)
    nav.last_fix_t, nav.fix_sigma = -4 * 3600, 0.5
    _run(g, 120)
    sug = [r for r in reports if r.type == "nav.suggest.starfix"]
    assert sug and sug[0].data["order"] == "stjärnfix" and "skymning" in sug[0].text.lower()


def test_star_fix_aborted_when_we_go_deep():
    g, reports = _game(17.85)
    _periscope_depth(g)
    g.command("stjärnfix")
    _run(g, 30)
    g.world.own.state.depth = 60.0
    _run(g, 5)
    assert any(r.type == "nav.starfix.aborted" for r in reports)
