"""Vyn Ubåten: genomskärning, djupprofil och paneler i ett, efter fönstrets storlek."""
import random

from sim.game import Game
from sim.scenario import build_scenario
from ui.boat_render import HULL_MIN_H, SIDE_MIN_W, header, layout, legend, render_boat


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
    assert narrow.panels_h <= (40 - 7) // 3 and narrow.profile_h + narrow.panels_h + 1 <= 33
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


def test_header_has_lamps_only_without_the_hull():
    g = _game()
    pv, sv = g.profile(), g.systems()
    _, tall = render_boat(pv, sv, 148, 36)
    _, low = render_boat(pv, sv, 148, 15)
    assert "UBÅTEN" in header(pv, sv, tall).plain and "avd" not in header(pv, sv, tall).plain
    assert "avd I II III" in header(pv, sv, low).plain
    assert "fara" in legend().plain and "språngskikt" in legend().plain
