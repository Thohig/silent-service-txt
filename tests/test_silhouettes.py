"""Siluetterna i braille (SB1–SB3): profiler i meter, verklig skala med minsta storlek,
vinkeln på bogen, horisonten och vågorna, bogvågen, röken och vattenpelaren."""
import math

from sim.periscope import HEIGHTS, PeriscopePicture, SightedObject
from sim.reports import Quality
from ui.silhouettes import (MIN_MAST_DOTS, PROFILES, column_dots, dots_per_m, silhouette)


def _span(sil):
    xs = [dx for dx, _ in sil.dots]
    return min(xs), max(xs)


def test_profiles_match_the_heights_the_lookout_uses():
    for kind, p in PROFILES.items():
        hull, sup, mast = HEIGHTS[kind]
        assert max(pt.z1 for pt in p.parts if pt.kind == "mast") == mast, kind
        blocks = [pt.z1 for pt in p.parts if pt.kind == "block"]
        assert max(blocks) == sup, kind
        assert all(pt.z0 >= hull - 0.01 or pt.kind != "block" for pt in p.parts) or kind


def test_true_scale_close_and_minimum_size_far():
    near = silhouette("destroyer", 90, 0.5, 20.0, 1.5)
    far = silhouette("destroyer", 90, 6.0, 20.0, 1.5)
    s_true = dots_per_m(20.0, 0.5)
    assert near.scale == s_true and near.scale * 30 > MIN_MAST_DOTS
    assert far.scale == MIN_MAST_DOTS / 30.0
    assert near.width > far.width


def test_bow_points_right_on_the_starboard_side_and_left_on_the_port_side():
    stb = silhouette("destroyer", 90, 1.0, 20.0, 1.5, speed=20)
    port = silhouette("destroyer", -90, 1.0, 20.0, 1.5, speed=20)
    bow_s = [dx for (dx, _), w in stb.dots.items() if w == "bow"]
    bow_p = [dx for (dx, _), w in port.dots.items() if w == "bow"]
    assert bow_s and min(bow_s) > 0 and bow_p and max(bow_p) < 0


def test_bow_on_is_narrow_but_keeps_its_masts():
    side = silhouette("merchant", 90, 2.0, 20.0, 1.5)
    bow_on = silhouette("merchant", 3, 2.0, 20.0, 1.5)
    assert bow_on.width < side.width / 3
    assert any(w == "mast" for w in bow_on.dots.values())


def test_horizon_and_waves_cut_the_hull_first():
    near = silhouette("destroyer", 90, 2.0, 20.0, 1.5)
    far = silhouette("destroyer", 90, 9.0, 20.0, 1.5)
    rough = silhouette("destroyer", 90, 2.0, 20.0, 1.5, wave_m=3.0)
    assert not any(w == "hull" for w in far.dots.values())      # skrovet under horisonten
    assert any(w == "mast" for w in far.dots.values())
    low = lambda sil: sum(1 for (_, dz), w in sil.dots.items() if w == "hull")
    assert low(rough) < low(near)


def test_rough_sea_waterline_moves_with_time():
    a = silhouette("merchant", 90, 2.0, 20.0, 1.5, wave_m=2.0, t=0)
    b = silhouette("merchant", 90, 2.0, 20.0, 1.5, wave_m=2.0, t=3)
    assert a.dots != b.dots


def test_bow_wave_grows_with_speed_and_smoke_only_from_steamers():
    slow = silhouette("merchant", 90, 1.0, 20.0, 1.5, speed=4)
    fast = silhouette("merchant", 90, 1.0, 20.0, 1.5, speed=16)
    bow = lambda sil: sum(1 for w in sil.dots.values() if w == "bow")
    assert bow(fast) > bow(slow)
    assert any(w == "smoke" for w in fast.dots.values())
    assert not any(w == "smoke" for w in silhouette("destroyer", 90, 1.0, 20.0, 1.5).dots.values())
    assert not any(w == "smoke" for w in silhouette("merchant", 90, 1.0, 20.0, 1.5,
                                                    day=False).dots.values())


def test_unknown_kind_has_no_silhouette():
    assert silhouette("aircraft", 90, 1.0, 20.0, 1.5) is None


def test_water_column_rises_then_falls_and_practice_is_smaller():
    h = lambda d: max(dz for _, dz in d)
    rise = [h(column_dots(1.5, 20.0, a)) for a in range(0, 3)]
    fall = [h(column_dots(1.5, 20.0, a)) for a in range(3, 10)]
    assert rise == sorted(rise) and fall == sorted(fall, reverse=True)
    assert h(column_dots(1.5, 20.0, 2, practice=True)) < h(column_dots(1.5, 20.0, 2))


def test_eyepiece_draws_braille_ship_and_keeps_the_reticle():
    from ui.periscope_render import render_eyepiece
    o = SightedObject("destroyer", "jagare", 0.0, 1.5, Quality.GOD, designation="S-1",
                      visible="helt", aob=60.0, aob_quality=Quality.GOD, course=0.0, speed=12)
    pic = PeriscopePicture(100, True, 10.0, 0.0, "periskop", (o,), power="hög")
    rows = [r.plain for r in render_eyepiece(pic, 76, 20, o, False, aim=0.0, power="hög")]
    empty = [r.plain for r in render_eyepiece(PeriscopePicture(100, True, 10.0, 0.0, "periskop", (),
                                                                power="hög"),
                                              76, 20, None, False, aim=0.0, power="hög")]
    braille = lambda rs: sum(1 for r in rs for ch in r if "\u2801" <= ch <= "\u28ff")
    assert braille(rows) > braille(empty) + 15
    assert "┊" in "".join(rows) and "╪" in "".join(rows)
    assert "_|_" not in "".join(rows)
