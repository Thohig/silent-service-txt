"""Långvågen: flytkabeln tar emot på djupet (L2)."""
import random

from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import build_scenario, default_scenario
from sim.stations.radio import (RECEIVE_S, VLF_RECEIVE_S, VLF_SLOW_KN, VLF_UP_DEPTH,
                                RadioStation)


def _game(seed=3, key=None):
    sc = build_scenario(key, random.Random(seed)) if key else default_scenario(random.Random(seed))
    g = Game(sc, seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _at(g, depth, speed):
    st = g.world.own.state
    st.depth = depth
    st.order_depth(depth)
    st.speed = speed
    st.order_speed(speed)


def _window_in(g, s=30):
    radio = g.station(RadioStation)
    radio.windows = [g.now + s]
    return radio


def _run(g, n):
    for _ in range(n):
        g.tick()


def test_cable_receives_at_depth_slowly():
    g, reports = _game()
    _at(g, 40, 3)
    radio = _window_in(g)
    _run(g, 30 + RECEIVE_S + 5)
    assert any(r.type == "radio.cable.out" for r in reports)
    assert radio.cable
    assert not any(r.type == "radio.message" for r in reports)     # långvågen är långsam
    _run(g, VLF_RECEIVE_S)
    msgs = [r for r in reports if r.type == "radio.message"]
    assert msgs and msgs[0].data["via"] == "vlf" and "på långvåg" in msgs[0].text
    assert not radio.cable                                          # kabeln in när det är mottaget


def test_cable_is_dragged_under_at_speed():
    g, reports = _game()
    _at(g, 40, 8)
    _window_in(g)
    _run(g, 30 + VLF_RECEIVE_S + 10)
    assert not any(r.type == "radio.message" for r in reports)
    fast = [r for r in reports if r.type == "radio.cable.fast"]
    assert fast and fast[0].data["order"] == f"fart {VLF_SLOW_KN}"


def test_too_deep_for_the_cable_gets_a_suggestion_to_come_up():
    g, reports = _game()
    _at(g, 100, 8)
    _window_in(g, 700)
    _run(g, 120)
    pre = [r for r in reports if r.type == "radio.prewarn_vlf"]
    assert pre and pre[0].data["order"] == f"djup {VLF_UP_DEPTH} och fart {VLF_SLOW_KN}"
    assert g.station(RadioStation).up_depth() == 50


def test_report_order_still_wants_the_mast():
    g, reports = _game(2, key="kuba-kort")
    radio = g.station(RadioStation)
    _at(g, 100, 3)
    radio.windows = [g.now + 30]
    radio._prewarned.clear()
    _run(g, 5)
    assert radio.up_depth() == 30
    assert radio._up_order()[0] == "antenndjup"


def test_no_cable_under_the_ice(monkeypatch):
    g, reports = _game()
    monkeypatch.setattr(RadioStation, "masts_free", property(lambda self: False))
    _at(g, 40, 3)
    radio = _window_in(g)
    _run(g, 30 + VLF_RECEIVE_S + 10)
    assert any(r.type == "radio.ice" for r in reports)
    assert not radio.cable and not any(r.type == "radio.message" for r in reports)
