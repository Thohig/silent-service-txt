"""Sjökortet: elementen byggs ur kunskapen, i navigatörens beräknade koordinater."""
import pytest
import random
import re

from sim.chart import Mark, Note, Ray, Ring, Track
from sim.events import BearingObserved, ContactDetected, ReportDelivered
from sim.game import Game
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations import NavigationStation
from sim.tma import BearingObs

TRUTH_IDS = ("DD1", "SSN1", "NORD7", "T1", "D1")


def _game(key="kuba", seed=3):
    return Game(build_scenario(key, random.Random(seed)), seed=seed)


def _yes_bot(g):
    g.bus.subscribe(ReportDelivered,
                    lambda e: e.report.kind == "suggest" and e.report.data.get("order")
                    and g.command("ja"))


def _labels(view):
    out = [n.text for n in view.notes]
    out += [i.label for i in view.drawables if isinstance(i, (Mark, Ray))]
    return out


def test_own_mark_is_the_estimate_not_the_truth():
    g = _game()
    nav = g.station(NavigationStation)
    nav.est_x += 0.7                               # besticket har glidit
    g.tick()
    view = g.chart()
    own = [i for i in view.drawables if isinstance(i, Mark) and i.style == "own"]
    assert len(own) == 1
    assert (own[0].x, own[0].y) == (nav.est_x, nav.est_y)
    assert abs(own[0].x - g.world.own.state.x) > 0.5
    assert view.own == (nav.est_x, nav.est_y)
    assert any("besticket" in n.text for n in view.notes)
    ring = next(i for i in view.drawables if isinstance(i, Ring) and i.style == "own")
    assert ring.radius == nav.uncertainty()


def test_dead_reckoning_track_and_fix_split_the_track():
    g = _game()
    nav = g.station(NavigationStation)
    for _ in range(600):
        g.tick()
    assert len(nav.dr_track[0]) >= 10
    s = g.world.own.state
    s.depth = s.ordered_depth = 15
    s.speed = s.ordered_speed = 3
    nav.est_x += 1.0
    g.command("fix")
    for _ in range(200):
        g.tick()
    assert len(nav.fixes) == 1
    view = g.chart()
    tracks = [i for i in view.drawables if isinstance(i, Track) and i.style == "track"]
    assert len(tracks) == 2
    fx, fy, _ = nav.fixes[0]
    assert tracks[1].points[0] == (fx, fy)
    assert any(isinstance(i, Mark) and i.style == "fix" for i in view.drawables)


def test_bearing_without_solution_is_drawn_from_where_we_thought_we_were():
    g = _game()
    g.bus.publish(ContactDetected(0, "S-4", 120.0, "okänd kontakt"))
    g.bus.publish(BearingObserved(0, BearingObs(0, 121.0, 1.0, 3.0, 4.0, 0,
                                                designation="S-4")))
    rays = [i for i in g.chart().drawables if isinstance(i, Ray) and i.style == "bearing"]
    assert len(rays) == 1
    r = rays[0]
    assert (r.x, r.y, r.bearing) == (3.0, 4.0, 121.0)
    assert r.label.startswith("S-4 121")
    assert r.quality == Quality.DALIG


def test_ice_soundings_openings_and_station_appear_in_the_arctic():
    g = _game("arktis", seed=2)
    for _ in range(1800):
        g.tick()
    view = g.chart()
    styles = {i.style for i in view.drawables}
    assert "ice_thick" in styles
    assert any(isinstance(i, Mark) and i.style == "waypoint" and "Nord-7" in i.label
               for i in view.drawables)
    ice = [i for i in view.drawables if isinstance(i, Mark) and i.style.startswith("ice")]
    assert len(ice) == len(g.knowledge.ice.soundings)


@pytest.mark.slow
def test_chart_never_reveals_truth_ids():
    for key, seed in (("kuba", 1), ("kuba", 4), ("arktis", 2), ("arktis", 5)):
        g = _game(key, seed)
        _yes_bot(g)
        for t in range(3600):
            g.tick()
            if t % 300 == 0:
                for label in _labels(g.chart()):
                    assert not any(tid in label for tid in TRUTH_IDS), (key, seed, label)
            if g.over:
                break


def test_bearing_of_a_long_lost_contact_is_dropped():
    from sim.events import ContactLost
    g = _game()
    g.bus.publish(ContactDetected(0, "S-4", 120.0, "okänd kontakt"))
    g.bus.publish(BearingObserved(0, BearingObs(0, 121.0, 1.0, 3.0, 4.0, 0, designation="S-4")))
    g.bus.publish(ContactLost(0, "S-4"))
    for _ in range(600):
        g.tick()
    bearing = [i for i in g.chart().drawables if isinstance(i, Ray) and i.style == "bearing"]
    assert bearing and bearing[0].faded
    for _ in range(1300):
        g.tick()
    assert not [i for i in g.chart().drawables if isinstance(i, Ray) and i.style == "bearing"]


# --- blyertsmärken ---------------------------------------------------------------
from sim.chart import LAYER_TRACK  # noqa: E402
from sim.events import SoundHeard  # noqa: E402
from sim.knowledge import ContactTrack  # noqa: E402
from sim.stations import PlotTeam  # noqa: E402
from sim.stations.plot import PENCIL_CLOCKS, PENCIL_FADE_S, PENCIL_GAP_S, PENCIL_KEEP_S  # noqa: E402
from sim.tma import Solution  # noqa: E402


def _pencil(view, contacts=False):
    """Blyertsmärkena, äldst först. Utan contacts: inte först hörd/tappad (sonar hör
    fartygen i övningen av sig själv)."""
    out = [i for i in view.drawables
           if isinstance(i, (Mark, Ray)) and i.style.startswith("pencil")]
    if not contacts:
        out = [i for i in out if (i.symbol if isinstance(i, Mark) else i.label[:1]) not in "»∅"]
    return out[::-1]


def _hear(g, kind, bearing, designation=None, detail="", practice=False):
    g.bus.publish(SoundHeard(g.now, kind, bearing, designation, practice, detail, se=20.0))


def test_pencil_mark_on_bearing_from_estimate_fresh_then_faded_then_gone():
    g = _game("ovning")             # inga ljud av sig självt
    nav = g.station(NavigationStation)
    nav.est_x += 0.7                               # besticket har glidit: märket följer det
    _hear(g, "splash", 47.0)
    (m,) = _pencil(g.chart())
    assert isinstance(m, Ray)
    assert (m.x, m.y) == (nav.est_x, nav.est_y)
    assert m.bearing == 47.0 and m.style == "pencil_new" and not m.faded
    assert m.label == "✕ " + g.clock_str()[:5]
    assert m.layer < LAYER_TRACK + 1
    for _ in range(61):
        g.tick()
    (m,) = _pencil(g.chart())
    assert m.style == "pencil" and not m.faded
    for _ in range(PENCIL_FADE_S):
        g.tick()
    assert _pencil(g.chart())[0].faded
    g.station(PlotTeam).pencil[0] = dataclasses_replace(g.station(PlotTeam).pencil[0],
                                                        t=g.now - PENCIL_KEEP_S)
    g.invalidate_views()
    assert _pencil(g.chart()) == []


def dataclasses_replace(obj, **kw):
    import dataclasses
    return dataclasses.replace(obj, **kw)


def test_pencil_one_mark_per_source_and_while_fast_ping_marked():
    g = _game("ovning")             # inga ljud av sig självt
    _hear(g, "ping", 100.0)
    g.tick()
    _hear(g, "ping", 103.0)                        # samma pingare strax efter
    _hear(g, "ping", 250.0)                        # en annan bäring
    assert [m.label.split()[0] for m in _pencil(g.chart())] == ["P", "P"]
    _hear(g, "ping", 101.0, detail="fast")         # snabb takt: eget märke
    assert [m.label.split()[0] for m in _pencil(g.chart())] == ["P", "P", "PP"]
    for _ in range(PENCIL_GAP_S["ping"]):
        g.tick()
    _hear(g, "ping", 99.0)
    assert len(_pencil(g.chart())) == 4
    _hear(g, "ice", 10.0)                          # isljud och telefon skrivs inte upp
    _hear(g, "uwt", 10.0)
    assert len(_pencil(g.chart())) == 4
    _hear(g, "explosion", 10.0, practice=True)
    assert g.station(PlotTeam).pencil[-1].symbol == "○"


def test_pencil_mark_sits_on_the_solution_when_plot_has_one():
    g = _game("ovning")             # inga ljud av sig självt
    k = g.knowledge
    tr = ContactTrack("S-4", first_t=0)
    sol = Solution(t=g.now - 600, t_ref=g.now - 600, state=(3.0, 4.0, 6.0, 0.0), x=3.0, y=4.0,
                   course=90.0, speed=6.0, range_nm=3.0, bearing=40.0, range_sigma=0.3,
                   course_sigma=10.0, speed_sigma=1.0, quality=Quality.GOD, n_obs=20,
                   span_s=900, own_maneuvered=True, rms_residual=1.0)
    tr.solution = sol
    k.tracks[tr.designation] = tr
    _hear(g, "ping", 41.0, designation="S-4")
    m = next(i for i in _pencil(g.chart()) if isinstance(i, Mark))
    assert m.x == pytest.approx(3.0 + 6.0 * 600 / 3600) and m.y == pytest.approx(4.0)
    assert m.symbol == "P"
    tr.solution = dataclasses_replace(sol, quality=Quality.DALIG)
    _hear(g, "splash", 41.0, designation="S-4")     # dålig lösning: bara bäringen
    assert [m.on_bearing for m in g.station(PlotTeam).pencil] == [False, True]


def test_pencil_clock_only_on_the_newest():
    g = _game("ovning")             # inga ljud av sig självt
    for i in range(PENCIL_CLOCKS + 3):
        _hear(g, "splash", 20.0 * i)
    labels = sorted((m.bearing, m.label) for m in _pencil(g.chart()))
    assert [len(s.split()) for _, s in labels] == [1] * 3 + [2] * PENCIL_CLOCKS


@pytest.mark.slow
def test_pencil_marks_in_a_hunt_come_from_what_sonar_heard():
    g = _game("jagad-kort", seed=2)
    _yes_bot(g)
    for _ in range(900):
        g.tick()
        if g.over:
            break
    marks = g.station(PlotTeam).pencil
    assert any(m.kind == "ping" for m in marks)
    labels = [m.label for m in _pencil(g.chart())]
    assert labels and not any(tid in s for s in labels for tid in TRUTH_IDS)


# --- egna handlingar, torpedbanan och tidsstrecken (B2) --------------------------
from sim.events import ContactLost, OwnActionLogged, OwnSoundMade  # noqa: E402
from sim.stations import TorpedoRoom  # noqa: E402
from sim.stations.navigation import DR_TICK_S  # noqa: E402


def test_own_actions_are_pencilled_where_we_thought_we_were():
    g = _game("ovning")
    nav = g.station(NavigationStation)
    nav.est_y -= 0.4
    g.bus.publish(OwnSoundMade(g.now, "decoy"))
    g.bus.publish(OwnActionLogged(g.now, "report"))
    g.bus.publish(OwnActionLogged(g.now, "report"))     # samma minut: ett märke
    g.bus.publish(OwnSoundMade(g.now, "launch"))         # torpedrummet ritar avfyringen
    marks = [m for m in _pencil(g.chart()) if isinstance(m, Mark)]
    assert sorted(m.symbol for m in marks) == ["R", "≋"]
    assert all((m.x, m.y) == (nav.est_x, nav.est_y) for m in marks)
    assert {m.label.rsplit(" ", 1)[0] for m in marks} == {"rapport", "skenmål"}


def test_raising_the_periscope_is_pencilled_but_not_the_binoculars():
    g = _game("ovning")
    plot = g.station(PlotTeam)
    s = g.world.own.state
    assert g.world.own.sys.bridge != "shut"                # ytläge, bryggan bemannad: kikaren
    g.command("periskop")
    for _ in range(20):
        g.tick()
    assert not any(m.kind == "periscope" for m in plot.pencil)


def test_periscope_hoist_marked_once_per_five_minutes():
    g = _game()
    plot = g.station(PlotTeam)
    s = g.world.own.state
    s.depth = s.ordered_depth = 15
    s.speed = s.ordered_speed = 3
    g.command("periskop")
    for _ in range(30):
        g.tick()
    g.command("periskop")
    for _ in range(30):
        g.tick()
    assert [m.symbol for m in plot.pencil if m.kind == "periscope"] == ["⊙"]


def test_own_torpedo_drawn_along_the_set_course_from_the_launch_point():
    g = _game()
    s = g.world.own.state
    s.speed = s.ordered_speed = 3
    nav = g.station(NavigationStation)
    lx, ly = nav.est_x, nav.est_y
    g.command("eld tub 1 kurs 090")
    g.tick()
    for _ in range(150):
        g.tick()
    room = g.station(TorpedoRoom)
    (r,) = room.in_water
    assert (r.launch_x, r.launch_y) == (lx, ly)
    view = g.chart()
    path = next(i for i in view.drawables if isinstance(i, Track) and i.style == "torpedo_path")
    (x0, y0), (x1, y1) = path.points
    assert (x0, y0) == (lx, ly) and y1 == pytest.approx(ly) and x1 > lx + 1.0
    head = next(i for i in view.drawables if isinstance(i, Mark) and i.label == "tub 1")
    assert head.symbol == "•" and (head.x, head.y) == (x1, y1)
    ticks = [i for i in view.drawables if isinstance(i, Mark) and i.style == "torpedo"
             and i.symbol == "+"]
    assert len(ticks) == 2                                # två hela minuter
    room._finish(r, "silent")
    g.invalidate_views()
    head = next(i for i in g.chart().drawables if isinstance(i, Mark) and i.label == "tub 1")
    assert head.symbol == "?"


def test_dead_reckoning_gets_a_tick_every_ten_minutes_on_the_clock():
    g = _game()
    nav = g.station(NavigationStation)
    for _ in range(2 * DR_TICK_S):
        g.tick()
    assert len(nav.dr_ticks) == 2 and not g.over
    assert all((g.start_clock + t) % DR_TICK_S == 0 for t, _, _ in nav.dr_ticks)
    ticks = [i for i in g.chart().drawables if isinstance(i, Mark) and i.symbol == "◦"]
    assert len(ticks) == 2
    assert all(m.label == "" or re.fullmatch(r"\d\d:[03]0", m.label) for m in ticks)


def test_contact_first_heard_and_lost_pencilled_with_designation():
    g = _game("ovning")
    plot = g.station(PlotTeam)
    nav = g.station(NavigationStation)
    g.bus.publish(ContactDetected(g.now, "S-9", 120.0, "okänd kontakt", Quality.DALIG))
    g.bus.publish(ContactDetected(g.now, "S-9", 121.0, "ytfartyg", Quality.OSAKER))
    first = [m for m in plot.pencil if m.kind == "first"]
    assert len(first) == 1 and first[0].bearing == 120.0
    assert (first[0].x, first[0].y) == (nav.est_x, nav.est_y)
    g.bus.publish(BearingObserved(g.now, BearingObs(g.now, 125.0, 1.0, 5.0, 2.0, 0.0,
                                                    designation="S-9")))
    g.bus.publish(ContactLost(g.now, "S-9"))
    (lost,) = [m for m in plot.pencil if m.kind == "lost"]
    assert lost.on_bearing and lost.bearing == 125.0 and (lost.x, lost.y) == (5.0, 2.0)
    for _ in range(PENCIL_CLOCKS + 1):                  # inte längre bland de nyaste
        g.bus.publish(SoundHeard(g.now, "splash", 10.0 + 40 * _, None, False, "", se=20.0))
    labels = [m.label for m in _pencil(g.chart(), contacts=True)
              if m.label.startswith(("»", "∅"))]
    assert sorted(labels) == ["» S-9", "∅ S-9"]


def test_navigators_periscope_fix_is_pencilled_too():
    g = _game()
    plot = g.station(PlotTeam)
    s = g.world.own.state
    s.depth = s.ordered_depth = 15
    s.speed = s.ordered_speed = 3
    g.command("fix")
    for _ in range(5):
        g.tick()
    assert [m.symbol for m in plot.pencil if m.kind == "periscope"] == ["⊙"]


def test_views_are_built_once_per_state():
    """Samma läge ⇒ samma vy; tick, order och händelser bygger om den."""
    g = _game()
    v = g.chart()
    assert g.chart() is v and g.sonar() is g.sonar()
    g.tick()
    v2 = g.chart()
    assert v2 is not v
    g.command("kurs 090")
    assert g.chart() is not v2
    v3 = g.chart()
    g.bus.publish(OwnActionLogged(g.now, "report"))
    assert g.chart() is not v3
