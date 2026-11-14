"""Rastreringen av sjökortet: rätt ruta, rätt tecken, klippning och etiketter."""
from sim.chart import ChartView, Mark, Ray, Ring, Track
from sim.reports import Quality
from ui.chart_render import MARGIN, grid_step, ray_char, render_chart

W, H = 60, 21          # kortytan blir 55 × 20 rutor


def _view(*items, size=20.0):
    return ChartView("03:00:00", "kvadrat 7", size, (10.0, 10.0), list(items))


def _grid(view, scale=0.1, cx=10.0, cy=10.0):
    lines = render_chart(view, cx, cy, scale, W, H)
    assert len(lines) == H and all(len(t.plain) == W for t in lines)
    return [t.plain[MARGIN:] for t in lines[1:]]


def _find(rows, ch):
    return [(c, r) for r, row in enumerate(rows) for c, x in enumerate(row) if x == ch]


def test_mark_lands_in_the_right_cell():
    rows = _grid(_view(Mark(10.0, 10.0, "@", "own"), Mark(11.0, 10.0, "◆", "contact"),
                       Mark(10.0, 11.0, "Ö", "opening")))
    (c0, r0), = _find(rows, "@")
    (c1, r1), = _find(rows, "◆")
    (c2, r2), = _find(rows, "Ö")
    assert (c1 - c0, r1 - r0) == (10, 0)          # 1 nm = 10 kolumner
    assert (c2 - c0, r2 - r0) == (0, -5)          # 1 nm = 5 rader (rutorna är höga)


def test_rays_use_the_right_character_and_are_clipped():
    rows = _grid(_view(Ray(10.0, 10.0, 90.0, 100.0, "bearing", "S-1 090"),
                       Ray(10.0, 10.0, 0.0, 0.5, "own_vector"),
                       Ray(10.0, 10.0, 135.0, 0.5, "contact_vector")))
    assert len(_find(rows, "─")) >= 15               # klippt vid kanten, ingen krasch
    assert len(_find(rows, "│")) in (2, 3)          # 0,5 nm = 2,5 rader
    assert _find(rows, "╲")
    assert "S-1 090" in "".join(rows)                # etiketten flyttas in vid kanten
    assert [ray_char(b) for b in (0, 45, 90, 135, 180, 225, 270, 315)] == \
        ["│", "╱", "─", "╲", "│", "╱", "─", "╲"]


def test_labels_never_overwrite_marks():
    rows = _grid(_view(Mark(10.0, 10.0, "◆", "contact", "S-1 god, 12 kn", Quality.GOD),
                       Mark(10.3, 10.0, "Ö", "opening", "Ö1 god", Quality.GOD)))
    (c, r), = _find(rows, "◆")
    assert rows[r][c + 3] == "Ö"                     # S-1:s etikett skriver inte över Ö
    assert rows[r][c + 5:c + 7] == "Ö1"


def test_offscreen_contact_gets_an_arrow_at_the_edge_but_ice_does_not():
    rows = _grid(_view(Mark(10.0, 30.0, "◆", "contact", "S-2 osäker", Quality.OSAKER),
                       Mark(30.0, 10.0, "Ö", "opening", "Ö4 god", Quality.GOD)))
    assert _find(rows, "↑") and not _find(rows, "◆")
    assert "S-2 osäker" in "".join(rows)
    assert "Ö4" not in "".join(rows)


def test_rings_tracks_and_grid():
    rows = _grid(_view(Ring(10.0, 10.0, 0.5, "own"),
                       Track(((9.0, 9.0), (9.0, 9.6)), "track")))
    assert len(_find(rows, ".")) >= 16
    assert len(_find(rows, "·")) >= 3
    assert _find(rows, "┼")
    small = _grid(_view(Ring(10.0, 10.0, 0.1, "own")))     # ryms i märket: ritas inte
    assert not _find(small, ".")


def test_area_border_and_axis_labels():
    lines = render_chart(_view(size=20.0), 1.0, 1.0, 0.1, W, H)
    text = "\n".join(t.plain for t in lines)
    assert "└" in text and "│" in text and "─" in text
    assert "1" in lines[0].plain and "2" in lines[0].plain


def test_grid_step_follows_zoom():
    assert grid_step(0.01) == 0.1
    assert grid_step(0.1) == 1.0
    assert grid_step(0.4) == 5.0
