"""Sjökortets solfjäder: plottets bäringar till det markerade målet (plot S-1 / läge S-1)."""
import random

import pytest

from sim.chart import Ray
from sim.game import Game
from sim.scenario import build_scenario
from sim.stations.plot import FAN_LINES, PlotTeam


def _game_with_track(seed=1):
    g = Game(build_scenario("ovning-kort", random.Random(seed)), seed=seed)
    for _ in range(3600):
        g.tick()
        tr = next((t for t in g.knowledge.tracks.values()
                   if len([o for o in t.observations if o.t >= t.tma_from_t]) >= 4), None)
        if tr is not None:
            return g, tr
    pytest.skip("ingen kontakt med bäringar")


def _fan(g):
    return [i for i in g.station(PlotTeam).chart_items() if isinstance(i, Ray) and i.style == "fan"]


@pytest.mark.slow
def test_solfjadern_for_markerat_mal():
    g, tr = _game_with_track()
    assert _fan(g) == []                                 # inget markerat än
    g.command(f"plot {tr.designation}")
    g.tick()
    fan = _fan(g)
    leg = [o for o in tr.observations if o.t >= tr.tma_from_t]
    assert 2 <= len(fan) <= FAN_LINES
    # från där vi trodde att vi var, längs plottets bäringar (kunskap, inte sanning)
    starts = {(o.own_x, o.own_y, o.bearing) for o in leg}
    assert all((r.x, r.y, r.bearing) in starts for r in fan)
    assert fan[-1].label.startswith(tr.designation)
    assert (fan[-1].x, fan[-1].y) == (leg[-1].own_x, leg[-1].own_y)


@pytest.mark.slow
def test_solfjadern_syns_pa_kortet():
    from ui.chart_render import render_chart
    g, tr = _game_with_track()
    g.command(f"läge {tr.designation}")
    g.tick()
    g.invalidate_views()
    cx, cy = g.own_position_estimate()
    rows = render_chart(g.chart(), cx, cy, 0.1, 110, 45)
    text = "\n".join(r.plain for r in rows)
    assert f"{tr.designation}: " in text and "bäringar sedan" in text
