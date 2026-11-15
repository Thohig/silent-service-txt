"""Ryska skyltar i vyerna: alltid med svenskan kvar, och bara där de får plats."""
import random

from sim.game import Game
from sim.scenario import build_scenario
from sim.systems import PANELS
from ui.central_render import Geometry, render_central
from ui.placards import CENTRAL_RU, PANEL_RU, VIEW_RU, view_title
from ui.systems_render import render_panels


def test_every_known_panel_and_view_has_a_russian_plate():
    assert set(PANELS) <= set(PANEL_RU)
    t = view_title("LOGGBOKEN").plain
    assert t.startswith(" LOGGBOKEN") and VIEW_RU["LOGGBOKEN"] in t
    assert view_title("OKÄND").plain == " OKÄND"            # ny vy: bara svenskan


def test_panels_keep_swedish_names_and_drop_russian_when_narrow():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    wide = "\n".join(t.plain for t in render_panels(g.systems(), 130))
    assert "MASKIN" in wide and PANEL_RU["MASKIN"] in wide
    narrow = "\n".join(t.plain for t in render_panels(g.systems(), 26))
    assert "MASKIN" in narrow and PANEL_RU["MASKIN"] not in narrow


def test_central_plate_only_where_there_is_room():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    big = render_central(g.status(), width=118, height=24)
    assert CENTRAL_RU in big[0].plain and len(big[0].plain) == 118
    small = render_central(g.status(), width=40, height=13)
    assert CENTRAL_RU not in small[0].plain
