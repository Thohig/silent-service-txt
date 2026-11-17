"""Solen, månen och ljuset: skymning, gryning, siluetter mot den ljusa himlen och månljus."""
import random

import pytest

from sim.environment import Environment, Light
from sim.game import Game
from sim.scenario import build_scenario
from sim.sky import julian_day, moon_phase, sun_position


def _env(clock_h: float, place=(24.5, -68.0), date=(1962, 10, 24)) -> Environment:
    lat, lon = place
    return Environment(clock_start=round(clock_h * 3600), lat=lat, lon=lon, utc_offset_h=lon / 15,
                       date=date)


def test_moon_phases_in_october_1962():
    """Fullmåne 13 oktober, nymåne 28 oktober: krisens nätter var mörka."""
    frac = {d: moon_phase(julian_day(1962, 10, d, 12 * 3600))[0] for d in (8, 13, 24, 28)}
    assert frac[13] > 0.98 and frac[28] < 0.02
    assert 0.6 < frac[8] < 0.8 and 0.1 < frac[24] < 0.25
    assert moon_phase(julian_day(1962, 10, 8))[1] and not moon_phase(julian_day(1962, 10, 24))[1]


def test_sun_rises_in_the_east_and_sets_in_the_west_near_the_old_times():
    rise = next(h / 60 for h in range(5 * 60, 7 * 60) if _env(h / 60).is_day(0))
    assert 5.8 < rise < 6.4                                  # förut 06:10 i kvadrat 7
    assert 80 < _env(rise).light(0).sun_az < 120             # i öster
    set_ = next(h / 60 for h in range(17 * 60, 19 * 60) if not _env(h / 60).is_day(0))
    assert 17.2 < set_ < 18.0 and 240 < _env(set_).light(0).sun_az < 280
    elev, _ = sun_position(85.0, 10.0, julian_day(1962, 10, 24, 11 * 3600))
    assert elev < -5                                         # polarnatt vid middag


def test_twilight_phases_and_visibility_fall_off_after_sunset():
    phases = [_env(17.0 + m / 60).light(0) for m in range(0, 180, 5)]
    names = [lt.phase for lt in phases]
    first = {n: names.index(n) for n in ("skymning", "nautisk", "natt")}
    assert first["skymning"] < first["nautisk"] < first["natt"]
    vis = [lt.visibility_nm for lt in phases]
    assert all(a >= b - 1e-9 for a, b in zip(vis, vis[1:]))  # sikten minskar
    assert vis[0] > 8 and min(vis) < 3.5
    assert not phases[0].morning and _env(5.5).light(0).morning      # skymning / gryning


def test_silhouettes_only_against_the_bright_sky_in_nautical_twilight():
    lt = next(_env(18.0 + m / 60).light(0) for m in range(0, 120) if
              _env(18.0 + m / 60).light(0).phase == "nautisk")
    toward = lt.sun_az
    assert lt.silhouette(toward) and lt.silhouette(toward + 40)
    assert not lt.silhouette(toward + 180) and not lt.silhouette(toward + 100)
    assert Light(10.0, 180.0).silhouette(0.0)                # dag: överallt
    assert not Light(-30.0, 180.0).silhouette(0.0)           # natt utan måne: bara lanternor


def test_moonlight_gives_silhouettes_in_the_glitter_and_longer_sight():
    full = Light(-30.0, 0.0, moon_elev=40.0, moon_az=120.0, moon_frac=1.0)
    none = Light(-30.0, 0.0)
    assert full.visibility_nm > none.visibility_nm * 1.8
    assert full.silhouette(130.0) and not full.silhouette(250.0)
    assert full.level > none.level
    low = Light(-30.0, 0.0, moon_elev=40.0, moon_az=120.0, moon_frac=0.1)
    assert not low.silhouette(120.0)                         # en tunn skära räcker inte


def test_fallback_without_a_place_keeps_the_old_day_and_night():
    env = Environment(clock_start=0)
    assert not env.is_day(6 * 3600) and env.is_day(6 * 3600 + 600)
    assert env.is_day(17 * 3600 + 49 * 60) and not env.is_day(17 * 3600 + 51 * 60)
    assert env.light(18 * 3600).phase in ("skymning", "nautisk")
    assert env.light(20 * 3600).phase == "natt"


@pytest.mark.parametrize("key,day", [("kuba", 24), ("jagad", 26), ("sundet", 25), ("konvoj", 28),
                                     ("ovning", 8), ("arktis", 24)])
def test_scenarios_get_the_date_of_the_order_and_a_place(key, day):
    g = Game(build_scenario(key, random.Random(1)), seed=1)
    env = g.world.env
    assert env.date == (1962, 10, day) and env.lat is not None
    lt = env.light(g.now)
    assert lt.phase == {"kuba": "natt", "jagad": "natt", "sundet": "natt", "konvoj": "dag",
                        "ovning": "dag", "arktis": "natt"}[key]


def test_destroyer_sees_our_periscope_plume_easier_in_the_moon_glitter():
    """D2: fullmåne natten mot 14 oktober. Ligger vi åt månens håll sett från jagaren
    syns plymen lättare; åt andra hållet, eller på dagen, gäller bara radarn."""
    from sim.enemy import MOON_GLITTER_F
    g = Game(build_scenario("kuba", random.Random(2)), seed=2)
    w = g.world
    w.env.date = (1962, 10, 13)
    w.env.clock_start = 0                         # midnatt, lokal medeltid: månen högt i söder
    lt = w.env.light(w.time)
    assert lt.phase == "natt" and lt.moon_light > 0.5 and 120 < lt.moon_az < 240
    dd = next(v for v in w.contacts if v.kind == "destroyer")
    ai = next(a for a in w.ais if getattr(a, "vessel", None) is dd)
    o = w.own.state
    dd.state.x, dd.state.y = o.x, o.y + 2.0           # jagaren norr om oss: vi åt månens håll
    assert ai.glitter_factor(w) == MOON_GLITTER_F
    dd.state.x, dd.state.y = o.x, o.y - 2.0           # söder om oss: vi mot den mörka sidan
    assert ai.glitter_factor(w) == 1.0
    w.env.clock_start = 12 * 3600                     # dag
    dd.state.x, dd.state.y = o.x, o.y + 2.0
    assert ai.glitter_factor(w) == 1.0


def _braille(s: str) -> int:
    return sum(0x2800 < ord(ch) <= 0x28FF for ch in s)


def _pic(phase, sun=(-4.0, 260.0), moon=(-10.0, 0.0, 0.0, True), morning=False, day=False):
    from sim.periscope import PeriscopePicture
    return PeriscopePicture(100, day, 6.0, 0.0, "brygga", (), phase=phase, morning=morning,
                            sun=sun, moon=moon)


def test_phase_text_in_the_header():
    from ui.periscope_render import phase_text
    assert phase_text(_pic("dag", sun=(20.0, 180.0), day=True)) == "dag"
    assert phase_text(_pic("skymning")) == "skymning"
    assert phase_text(_pic("skymning", morning=True)) == "gryning"
    assert phase_text(_pic("nautisk")) == "nautisk skymning"
    assert phase_text(_pic("natt", moon=(30.0, 150.0, 0.19, False))) == "natt, måne 19 % avtagande"
    assert phase_text(_pic("natt", moon=(-5.0, 150.0, 0.5, True))) == "natt, månen nere"
    assert phase_text(_pic("natt", moon=(30.0, 150.0, 1.0, True))) == "natt, fullmåne"


def test_twilight_glow_toward_the_sun_and_the_moon_with_its_phase():
    """D3: skymningens sken åt solens håll, inte åt andra hållet; månen ritas med rätt sida
    belyst och glittret under den."""
    from ui.bridge_render import render_scene
    from ui.periscope_render import _Grid, draw_sky
    dusk = _pic("skymning", sun=(-3.0, 260.0))
    toward = "\n".join(t.plain for t in render_scene(dusk, 110, 22, 260.0, 0)[:9])
    away = "\n".join(t.plain for t in render_scene(dusk, 110, 22, 80.0, 0)[:9])
    assert _braille(toward) > _braille(away) + 10 and _braille(away) < 3
    for waxing in (True, False):
        g = _Grid(40, 12)
        draw_sky(g, _pic("natt", moon=(4.0, 0.0, 0.5, waxing)), 8, 0.0, 40 / 120, 19.5)
        lit = [(c, r) for (r, c), cell in g.dots.cells.items() if "e8e8d8" in cell[1]]
        assert lit
        mean_c = sum(c for c, _ in lit) / len(lit)
        assert (mean_c > 19.5) == waxing                  # tilltagande: ljust till höger
        below = [r for (r, c), cell in g.dots.cells.items() if r > 8]
        assert below                                      # glittret på vattnet
