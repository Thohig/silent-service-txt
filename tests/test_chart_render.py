"""Rastreringen av sjökortet: rätt ruta, rätt tecken, klippning och etiketter."""
from sim.chart import LAYER_ICE, ChartView, Mark, Ray, Ring, Track
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


def _dots(rows):
    """Rutorna med brailleprickar."""
    return [(c, r) for r, row in enumerate(rows) for c, x in enumerate(row)
            if 0x2800 < ord(x) <= 0x28FF]


def test_mark_lands_in_the_right_cell():
    rows = _grid(_view(Mark(10.0, 10.0, "@", "own"), Mark(11.0, 10.0, "◆", "contact"),
                       Mark(10.0, 11.0, "Ö", "opening")))
    (c0, r0), = _find(rows, "@")
    (c1, r1), = _find(rows, "◆")
    (c2, r2), = _find(rows, "Ö")
    assert (c1 - c0, r1 - r0) == (10, 0)          # 1 nm = 10 kolumner
    assert (c2 - c0, r2 - r0) == (0, -5)          # 1 nm = 5 rader (rutorna är höga)


def test_rays_are_dotted_lines_and_clipped():
    rows = _grid(_view(Ray(10.0, 10.0, 90.0, 100.0, "bearing", "S-1 090")))
    (c0, r0), = [(c, r) for c, r in _dots(rows)][:1]
    east = [(c, r) for c, r in _dots(rows) if r == r0]
    assert len(east) >= 15                           # klippt vid kanten, ingen krasch
    assert "S-1 090" in "".join(rows)                # etiketten flyttas in vid kanten
    north = _grid(_view(Ray(10.0, 10.0, 0.0, 0.5, "own_vector")))
    cols = {c for c, _ in _dots(north)}
    assert len(cols) == 1 and len(_dots(north)) in (2, 3)   # 0,5 nm = 2,5 rader, lodrät
    se = _grid(_view(Ray(10.0, 10.0, 135.0, 0.5, "contact_vector")))
    pts = _dots(se)
    assert pts and max(c for c, _ in pts) > min(c for c, _ in pts) and \
        max(r for _, r in pts) > min(r for _, r in pts)     # snett nedåt höger
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
    ring = _grid(_view(Ring(10.0, 10.0, 0.5, "own")))
    assert len(_dots(ring)) >= 16                          # streckad ring i prickar
    rows = _grid(_view(Track(((9.0, 9.0), (9.0, 9.6)), "track")))
    assert len(_dots(rows)) >= 3
    assert _find(rows, "┼")
    small = _grid(_view(Ring(10.0, 10.0, 0.1, "own")))     # ryms i märket: ritas inte
    assert not _dots(small)
    fairway = _grid(_view(Track(((8.0, 10.0), (12.0, 10.0)), "fairway", char="╌")))
    solid = _grid(_view(Track(((8.0, 10.0), (12.0, 10.0)), "track")))
    assert 0 < len(_dots(fairway)) < len(_dots(solid))     # farleden streckad


def test_area_border_and_axis_labels():
    lines = render_chart(_view(size=20.0), 1.0, 1.0, 0.1, W, H)
    text = "\n".join(t.plain for t in lines)
    assert "└" in text and "│" in text and "─" in text
    assert "1" in lines[0].plain and "2" in lines[0].plain


def test_grid_step_follows_zoom():
    assert grid_step(0.01) == 0.1
    assert grid_step(0.1) == 1.0
    assert grid_step(0.4) == 5.0


def test_oblique_lines_are_thin():
    rows = _grid(_view(Ray(10.0, 10.0, 300.0, 100.0, "bearing")))
    per_col = {}
    for c, r in _dots(rows):
        per_col[c] = per_col.get(c, 0) + 1
    assert per_col and max(per_col.values()) <= 2    # grund linje: högst två rutor per kolumn
    rows = _grid(_view(Ray(10.0, 10.0, 20.0, 100.0, "bearing")))
    per_row = {}
    for c, r in _dots(rows):
        per_row[r] = per_row.get(r, 0) + 1
    assert per_row and max(per_row.values()) <= 2    # brant linje: högst två rutor per rad


def test_marks_and_labels_sit_on_top_of_lines():
    rows = _grid(_view(Ray(9.0, 10.0, 90.0, 3.0, "bearing"),
                       Mark(10.0, 10.0, "◆", "contact", "S-1", Quality.GOD)))
    (c, r), = _find(rows, "◆")
    assert rows[r][c + 2:c + 5] == "S-1"             # linjen under, märke och etikett syns


def test_label_is_separated_from_its_mark():
    rows = _grid(_view(Mark(10.05, 10.0, "#", "ice_thick", layer=LAYER_ICE),
                       Mark(10.15, 10.0, "#", "ice_thick", layer=LAYER_ICE),
                       Mark(10.0, 10.0, "Ö", "opening", "Ö1 god", Quality.GOD)))
    (c, r), = [p for p in _find(rows, "Ö") if rows[p[1]][p[0] + 1] != "1"]
    assert rows[r][c + 1] == " " and rows[r][c + 2:c + 4] == "Ö1"


def test_label_of_a_higher_layer_wins_where_labels_collide():
    """Kontaktens etikett får platsen före ett blyertsmärke, oavsett ordning; inom ett lager
    vinner den som kom först (stationen lägger det nyaste först). Den som förlorar flyttas
    en rad i stället för att försvinna."""
    def row_of(rows, s):
        return next(r for r, row in enumerate(rows) if s in row)

    pencil = Ray(10.0, 10.0, 90.0, 0.6, "pencil", "P 03:01", layer=0.5)
    contact = Mark(10.7, 10.0, "◆", "contact", "S-1 god")
    alone = row_of(_grid(_view(pencil)), "P 03:01")
    for order in ((pencil, contact), (contact, pencil)):
        rows = _grid(_view(*order))
        (_c, r), = _find(rows, "◆")
        assert row_of(rows, "S-1 god") == r
        assert row_of(rows, "P 03:01") != alone          # flyttad, inte borta
    newer = Ray(10.0, 10.0, 90.0, 0.6, "pencil", "✕ 03:05", layer=0.5)
    rows = _grid(_view(newer, pencil))
    assert row_of(rows, "✕ 03:05") == alone and row_of(rows, "P 03:01") != alone
