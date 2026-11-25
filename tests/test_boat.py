"""Vyn Ubåten: genomskärning, djupprofil och paneler i ett, efter fönstrets storlek."""
import random

from sim.game import Game
from sim.scenario import build_scenario
from ui.boat_render import HULL_MIN_H, SIDE_MIN_W, header, lamps, layout, legend, render_boat


def _game(seed=3):
    g = Game(build_scenario("kuba", random.Random(seed)), seed=seed)
    for _ in range(120):
        g.tick()
    return g


def test_layout_side_by_side_when_wide_and_stacked_when_narrow():
    wide = layout(150, 40, 6, 30)
    assert wide.side and wide.hull and wide.profile_w + wide.panels_w + 2 == 150
    assert wide.profile_h == wide.panels_h == 40 - 7
    narrow = layout(90, 40, 6, 30)
    assert not narrow.side and narrow.profile_w == narrow.panels_w == 90
    assert narrow.panels_h <= (40 - 7) // 2 and narrow.profile_h + narrow.panels_h + 1 <= 33
    low = layout(150, HULL_MIN_H - 1, 6, 30)
    assert not low.hull and low.profile_h == HULL_MIN_H - 1


def test_render_fits_and_shows_all_three_parts():
    g = _game()
    for w, h in ((148, 36), (SIDE_MIN_W - 2, 30), (88, 15)):
        rows, lay = render_boat(g.profile(), g.systems(), w, h)
        txt = "\n".join(r.plain for r in rows)
        assert len(rows) <= h
        assert all(len(r.plain) <= w for r in rows)
        assert "▬▶" in txt                                       # vi i profilen
        assert "MASKIN" in txt                                   # panelerna
        assert ("III" in txt) == lay.hull                        # genomskärningen bara när högt


def test_lamps_only_without_the_hull():
    g = _game()
    pv, sv = g.profile(), g.systems()
    _, tall = render_boat(pv, sv, 148, 36)
    _, low = render_boat(pv, sv, 148, 15)
    assert "UBÅTEN" in header(pv, sv).plain
    assert lamps(sv, tall).plain == ""
    assert "avd I II III" in lamps(sv, low).plain
    assert "fara" in legend().plain and "språngskikt" in legend().plain


def test_time_scale_follows_the_history():
    g = _game()                                              # två minuter spelat
    _, short = render_boat(g.profile(), g.systems(), 148, 36)
    for _ in range(3600):
        g.tick()
    _, long = render_boat(g.profile(), g.systems(), 148, 36)
    assert short.sec_per_col < long.sec_per_col
    _, fixed = render_boat(g.profile(), g.systems(), 148, 36, sec_per_col=30)
    assert fixed.sec_per_col == 30


def test_panels_in_two_columns_only_when_they_do_not_fit_and_it_is_wide():
    assert layout(150, 40, 6, 30).panel_cols == 1            # ryms
    two = layout(200, 30, 6, 40)
    assert two.panel_cols == 2 and two.profile_w < layout(200, 30, 6, 20).profile_w
    assert layout(150, 30, 6, 40).panel_cols == 1            # för smalt för två spalter
    g = _game()
    rows, lay = render_boat(g.profile(), g.systems(), 210, 24)
    txt = "\n".join(r.plain for r in rows)
    assert lay.panel_cols == 2
    right = [r.plain[lay.profile_w + 2 + (lay.panels_w - 2) // 2 + 2:] for r in rows[-lay.panels_h:]]
    first = next(r for r in right if r.strip())
    assert first.startswith("─")                             # högra spalten börjar med en panel
    assert "MASKIN" in txt and all(len(r.plain) <= 210 for r in rows)


def test_legend_breaks_between_items_and_fits_the_width():
    """80 kolumner: "····" hamnade sist på en rad och "sjökortets djup" på nästa, och raden med
    "Sonar hörde" och tavlans tillstånd syntes inte alls (höjden var 2)."""
    for width in (78, 100, 140):
        lines = legend(width).plain.split("\n")
        assert all(len(line) <= width for line in lines)
        assert any("⠒⠒ sjökortets djup" in line for line in lines)
        assert any("fara" in line for line in lines) and any("Sonar hörde" in line for line in lines)
