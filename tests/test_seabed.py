"""Havsbotten: sanningen varierar, sjökortet är en egen, felaktig bild av den."""
import random

import numpy as np

from sim.chart import Mark, Track
from sim.game import Game
from sim.scenario import build_scenario
from sim.seabed import Seabed, Seamount, arctic_seabed, contours, kuba_seabed

GRID = np.meshgrid(np.linspace(0, 20, 81), np.linspace(0, 20, 81))


def _game(key="kuba", seed=3):
    return Game(build_scenario(key, random.Random(seed)), seed=seed)


def test_kuba_has_a_bank_but_we_start_over_deep_water():
    fractions = []
    for seed in range(12):
        sb = kuba_seabed(random.Random(seed), (10.0, 3.0))
        z = sb.depths(*GRID)
        fractions.append((z < 300).mean())
        assert z.min() > 80 and z.max() < 3500
        assert sb.depth_at(10.0, 3.0) > 1000
    assert 0.10 < np.median(fractions) < 0.25
    assert min(fractions) > 0.05


def test_arctic_has_a_ridge_well_below_the_ice():
    for seed in range(8):
        z = arctic_seabed(random.Random(seed)).depths(*GRID)
        assert 600 < z.min() < 1500
        assert z.max() > 2800


def test_chart_copy_is_shifted_and_smooth():
    sb = kuba_seabed(random.Random(1), (10.0, 3.0))
    chart = sb.chart_copy(random.Random(2), err_nm=0.5)
    assert chart is not sb and chart.rough == ()
    diff = np.abs(chart.depths(*GRID) - sb.depths(*GRID))
    assert diff.mean() > 20                       # kortet stämmer inte exakt
    assert np.median(diff / sb.depths(*GRID)) < 0.2   # men ungefär


def test_chart_copy_sometimes_misses_a_seamount():
    sb = Seabed(2000.0, features=(Seamount(10, 10, 300, 1.2),))
    missing = sum(not sb.chart_copy(random.Random(s), 0.5).features for s in range(200))
    assert 20 < missing < 80


def test_contours_follow_the_levels():
    sb = Seabed(1000.0, gradient=(100.0, 0.0))     # 1000 m i väster, 3000 m i öster
    segs = contours(sb, 0, 0, 20, 20, levels=(2000,))[2000]
    xs = [p[0] for seg in segs for p in seg]
    assert all(abs(x - 10) < 0.05 for x in xs)


def test_knowledge_has_the_old_chart_not_the_truth():
    g = _game()
    assert g.knowledge.bathymetry is not None
    assert g.knowledge.bathymetry is not g.world.env.seabed


def test_echo_sounder_reads_the_true_bottom_where_we_are():
    g = _game()
    g.command("kurs 270")
    g.command("fart 8")
    depths = []
    for t in range(3600):
        if t % 300 == 5:
            g.command("ekolod")
        g.tick()
    depths = [b.depth for b in g.profile().bottom]
    assert len(depths) >= 10
    assert max(depths) - min(depths) > 200          # botten varierar längs vägen
    s = g.world.own.state
    assert abs(depths[-1] - g.world.env.bottom_at(s.x, s.y)) < 100


def test_chart_shows_contours_and_soundings():
    g = _game()
    g.command("ekolod")
    for _ in range(5):
        g.tick()
    view = g.chart()
    assert any(isinstance(i, Track) and i.style == "contour" for i in view.drawables)
    assert any(isinstance(i, Mark) and i.style == "sounding" for i in view.drawables)
    assert g.profile().chart_bottom
