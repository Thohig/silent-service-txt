"""Periskopet ser plask, vattenpelare och träffar (P1–P2): bara i okularet, bara över
horisonten och vågtopparna, och plottet skriver ett blyertsmärke där det syntes."""
import random

from sim import acoustics
from sim.entities import Transient
from sim.events import EventSighted, PeriscopeSighted, ReportDelivered
from sim.game import Game
from sim.periscope import event_visible, horizon_nm
from sim.scenario import default_scenario
from sim.stations.periscope import PeriscopeWatch
from sim.stations.plot import PlotTeam


def _game(day=True, seed=3, sea=3):
    g = Game(default_scenario(random.Random(seed)), seed=seed)
    w = g.world
    w.spawners.clear()
    w.contacts = [v for v in w.contacts if v.side != "neutral"]
    for ai in w.ais:
        ai.can_force = False
    st = w.own.state
    st.depth = st.ordered_depth = 15.0
    st.speed = st.ordered_speed = 3.0
    dd = next(v for v in w.contacts if v.kind == "destroyer")
    dd.state.x, dd.state.y = st.x + 30, st.y + 30
    w.env.lat = None
    w.env.sunrise, w.env.sunset = (0, 24 * 3600) if day else (0, 0)
    w.env.sea_state = sea
    reports, seen, frames = [], [], []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report.type))
    g.bus.subscribe(EventSighted, seen.append)
    g.bus.subscribe(PeriscopeSighted, frames.append)
    return g, reports, seen, frames


def _hold(g, bearing):
    g.command("periskop upp")
    g.command(f"vrid periskop {bearing:03d}")
    for _ in range(3):
        g.tick()


def _emit(g, kind, dx, dy, practice=False, ticks=3):
    st = g.world.own.state
    level = acoustics.SPLASH_LEVEL if kind == "splash" else acoustics.EXPLOSION_REAL
    g.world.emit(Transient(kind, st.x + dx, st.y + dy, 0.0 if kind == "splash" else 50.0,
                           level, "DD1", g.now, practice=practice))
    for _ in range(ticks):
        g.tick()


def test_heights_decide_how_far_events_are_seen_from_the_periscope():
    eye = 1.5
    assert event_visible("splash", 5.0, eye) and not event_visible("splash", 8.0, eye)
    assert event_visible("column", 11.0, eye) and not event_visible("column", 14.0, eye)
    # vågtopparna döljer ett plask tidigare
    assert event_visible("splash", 6.0, eye, 0.6) and not event_visible("splash", 6.0, eye, 3.0)
    assert horizon_nm(eye) < 3


def test_column_in_the_eyepiece_is_seen_called_out_and_pencilled():
    g, reports, seen, frames = _game()
    _hold(g, 0)
    _emit(g, "explosion", 0.0, 1.5)
    cols = [o for o in frames[-1].picture.objects if o.kind == "column"]
    assert len(cols) == 1 and cols[0].designation is None
    assert abs(cols[0].range_nm - 1.5) < 0.6
    assert seen and seen[0].source == "periskop"
    plot = g.station(PlotTeam)
    assert any(m.kind == "explosion" and m.key.startswith("seen:") for m in plot.pencil)
    for _ in range(15):
        g.tick()
    assert not any(o.kind == "column" for o in frames[-1].picture.objects), "pelaren är borta"
    assert "off.periscope.column" in reports


def test_event_outside_the_eyepiece_is_not_seen():
    g, reports, seen, frames = _game()
    _hold(g, 180)
    _emit(g, "explosion", 0.0, 1.5, ticks=20)
    assert not seen and "off.periscope.column" not in reports


def test_high_power_sees_a_narrow_sector():
    g, _, seen, _ = _game()
    _hold(g, 0)
    g.command("förstoring hög")
    g.tick()
    _emit(g, "explosion", 1.0, 1.0)          # 45°: utanför ±4°
    assert not seen
    _emit(g, "explosion", 0.0, 2.0)
    assert seen


def test_splash_far_away_is_below_the_horizon_and_night_shows_no_splash():
    g, _, seen, _ = _game()
    _hold(g, 0)
    _emit(g, "splash", 0.0, 9.0)
    assert not seen
    _emit(g, "splash", 0.0, 2.0)
    assert seen and seen[-1].kind == "splash"
    g, _, seen, _ = _game(day=False)
    _hold(g, 0)
    _emit(g, "splash", 0.0, 1.0)
    assert not seen
    _emit(g, "explosion", 0.0, 1.0)
    assert seen and seen[-1].kind == "column"


def test_rough_sea_hides_a_splash_that_calm_sea_shows():
    seen_at = {}
    for sea in (2, 6):
        g, _, seen, _ = _game(sea=sea)
        _hold(g, 0)
        _emit(g, "splash", 0.0, 6.0)
        seen_at[sea] = bool(seen)
    assert seen_at == {2: True, 6: False}


def test_practice_column_is_called_as_practice_and_no_alarm():
    g, reports, seen, frames = _game()
    got = []
    g.bus.subscribe(ReportDelivered, lambda e: got.append(e.report))
    _hold(g, 0)
    _emit(g, "explosion", 0.0, 1.5, practice=True, ticks=20)
    r = next(r for r in got if r.type == "off.periscope.column")
    assert "övning" in r.text and not r.alarm
    assert r.speech and not any("a" <= c.lower() <= "z" for c in r.speech)


def test_periscope_down_sees_nothing():
    g, _, seen, _ = _game()
    _emit(g, "explosion", 0.0, 1.5)
    assert not seen
    assert g.station(PeriscopeWatch).mode is None


def test_eyepiece_draws_the_column():
    from ui.periscope_render import render_eyepiece
    g, _, _, frames = _game()
    _hold(g, 0)
    _emit(g, "explosion", 0.0, 1.5, ticks=2)
    pic = frames[-1].picture
    rows = "\n".join(r.plain for r in render_eyepiece(pic, 60, 18, None, False, aim=0.0))
    assert "|||" in rows or r"\|/" in rows
