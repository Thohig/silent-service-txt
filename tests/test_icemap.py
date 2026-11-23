"""Isekolodet, iskartan och navigatörens arbete under isen."""
import math
import random

import pytest

from sim.events import IceSounded, OpeningNotFound, ReportDelivered
from sim.game import Game
from sim.ice import masts_clear
from sim.icemap import MIN_SURFACE_LEN_M, IceMap, IceSoundingObs
from sim.reports import Quality
from sim.scenario import build_scenario
from sim.stations import NavigationStation
from sim.stations.radio import RadioStation

M = 1 / 1852


def _feed(m: IceMap, thick: list[float], t0=0, dx_m=13.0):
    """Lodningar var femte sekund längs en rak linje norrut."""
    for i, t in enumerate(thick):
        m.on_sounding(IceSoundingObs(t0 + 5 * i, 0.0, i * dx_m * M, t, 0.89 * t))


# --- iskartan (ren kunskap) ---------------------------------------------------------
def test_opening_is_logged_from_a_run_of_thin_soundings():
    m = IceMap()
    _feed(m, [3.0] * 5 + [0.0] * 15 + [3.0] * 5)
    assert len(m.openings) == 1
    o = m.openings[0]
    assert o.open and not o.active
    assert o.length_m == pytest.approx(14 * 13 + 20, abs=1)
    assert m.under_ice(5 * 24)
    assert m.latest(5 * 24 + 31) is None              # gammal lodning räknas inte


def test_thin_ice_counts_but_thick_does_not():
    m = IceMap()
    _feed(m, [3.0] * 3 + [0.6] * 12 + [1.5] * 3 + [0.0] * 3 + [3.0])
    assert [round(o.thickest, 1) for o in m.openings] == [0.6, 0.0]
    assert not m.openings[0].open


def test_quality_falls_with_age_and_is_capped_for_narrow_openings():
    m = IceMap()
    _feed(m, [3.0] + [0.0] * 25 + [3.0])          # ~330 m
    o = m.openings[0]
    now = o.last.t
    qs = [o.quality(now + 60 * k) for k in (0, 5, 15, 40)]
    assert qs == sorted(qs, reverse=True)
    assert qs[0] >= Quality.GOD and qs[-1] == Quality.DALIG
    m2 = IceMap()
    _feed(m2, [3.0] + [0.0] * 4 + [3.0])          # ~70 m
    assert m2.openings[0].length_m < MIN_SURFACE_LEN_M
    assert m2.openings[0].quality(m2.openings[0].last.t) <= Quality.OSAKER


def test_best_prefers_quality_then_distance_and_skips_dropped():
    m = IceMap()
    _feed(m, [3.0] + [0.0] * 25 + [3.0] * 10, t0=0)
    _feed(m, [3.0] + [0.0] * 25 + [3.0], t0=2400)
    old, new = m.openings
    assert m.best(2600, 0, 0) is new
    new.dropped = True
    assert m.best(2600, 0, 0) is None              # den gamla är för osäker nu


def test_knowledge_ice_map_is_fed_by_bus_only():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    for i, t in enumerate([3.0, 0.0, 0.0, 0.0, 3.0]):
        g.bus.publish(IceSounded(i * 5, IceSoundingObs(i * 5, 0, i * 0.01, t, t)))
    assert len(g.knowledge.ice.openings) == 1
    g.bus.publish(OpeningNotFound(30, g.knowledge.ice.openings[0].no))
    assert g.knowledge.ice.openings[0].dropped


# --- isekolodet ------------------------------------------------------------------------
def _arctic(seed):
    g = Game(build_scenario("arktis", random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_sounder_uses_estimated_position_not_truth():
    g, _ = _arctic(1)
    nav = g.station(NavigationStation)
    nav.est_x += 0.3                                # besticket har glidit
    seen = []
    g.bus.subscribe(IceSounded, lambda e: seen.append(e.obs))
    for _ in range(30):
        g.tick()
    assert len(seen) == 6
    assert seen[-1].x == pytest.approx(nav.est_x, abs=0.01)
    assert abs(seen[-1].x - g.world.own.state.x) > 0.25


def test_no_sounder_without_ice():
    g = Game(build_scenario("kuba", random.Random(1)), seed=1)
    for _ in range(60):
        g.tick()
    assert not g.knowledge.ice.soundings


def test_ice_report_command():
    g, reports = _arctic(2)
    for _ in range(20):
        g.tick()
    g.command("isekolod")
    for _ in range(10):
        g.tick()
    assert any(r.type == "nav.ice.report" and r.text.startswith("Isekolod:") for r in reports)


def test_depth_ack_warns_about_ice_overhead():
    g, reports = _arctic(3)
    ice = g.world.env.ice
    ice.thickness[:] = 3.0
    ice.draft[:] = 3.0
    for _ in range(10):
        g.tick()
    g.command("periskopdjup")
    for _ in range(10):
        g.tick()
    ack = next(r for r in reports if r.type == "nav.depth.ack")
    assert "is ovanför" in ack.text


# --- hela kedjan: hitta öppet vatten och ta emot order ---------------------------------
def _yes_bot(seed, seconds):
    g, reports = _arctic(seed)
    due: list[int] = []
    g.bus.subscribe(ReportDelivered,
                    lambda e: due.append(g.now + 20) if e.report.kind == "suggest" else None)
    surfaced_or_pd_in_open = 0
    for _ in range(seconds):
        g.tick()
        if due and g.now >= due[0]:
            due.pop(0)
            if g.active_suggestion():
                g.command("ja")
        s = g.world.own.state
        if s.depth <= 18 and masts_clear(g.world):
            surfaced_or_pd_in_open += 1
    return g, reports, surfaced_or_pd_in_open


@pytest.mark.slow
def test_crew_guides_boat_to_open_water_and_station_over_seeds():
    """Med en kapten som säger ja når besättningen öppet vatten och drivstationen
    i de flesta frön, utan att skada ubåten nämnvärt."""
    reached, station = [], []
    for seed in range(1, 9):
        g, reports, open_s = _yes_bot(seed, 6 * 3600)
        reached.append(open_s > 0)
        station.append((g.world.outcome or {}).get("outcome") == "station_reached")
        assert g.world.own.sys.hull > 0.9
    assert sum(reached) >= 7
    # 16 frön (2026-11-23): 11 av 16 når stationen, med och utan döda sektorn; på 8 frön 3–6 av
    # slumpen, så gränsen 5 föll på brus när nästan vad som helst ändrades
    assert sum(station) >= 3


@pytest.mark.slow
def test_vak_steers_back_and_stops_under_opening():
    """Efter en passerad öppning: 'vak' ska oftast leda till stopp under öppet
    vatten eller nyis (sanningen), inom tjugo minuter."""
    ok = 0
    trials = 0
    for seed in range(1, 11):
        g, reports = _arctic(seed)
        nav = g.station(NavigationStation)
        g.command("djup 60")
        # gå tills en bra öppning är passerad
        for _ in range(3 * 3600):
            g.tick()
            o = nav.best_opening()
            if o is not None and not o.active and o.quality(g.now) >= Quality.GOD:
                break
        else:
            continue
        trials += 1
        g.command("vak")
        for _ in range(1200):
            g.tick()
            if nav.vak is None and g.world.own.state.speed < 0.3:
                break
        s = g.world.own.state
        if g.world.env.ice.thickness_at(s.x, s.y) <= 1.0:
            ok += 1
    assert trials >= 7
    assert ok >= 0.7 * trials


def test_vak_at_the_station_ends_the_station_search_so_we_stay_under_the_opening():
    """Framme under en öppning vid Nord-7: sökspiralen får inte starta och köra oss ur den
    medan navigatören föreslår ytläge (arktis-kort, frö 4, 02:40)."""
    from sim.stations.navigation.tasks import Station as StationSteer
    g, reports = _arctic(1)
    nav = g.station(NavigationStation)
    _feed(nav.icemap, [3.0] * 5 + [0.0] * 20, t0=g.now - 120)
    o = nav.icemap.openings[-1] if nav.icemap.openings else None
    nav.icemap.on_sounding(IceSoundingObs(g.now, nav.est_x, nav.est_y, 0.0, 0.0))
    nav.steer = StationSteer(source="sonar")
    nav.vak, nav._vak_stopping = o or nav.icemap.current, True
    nav.near_station = lambda: True
    nav._station_overhead = lambda: (nav.est_x, nav.est_y)
    nav._hull_ice = (g.now, 0.0, 0.0)           # isekolodet för och akter: öppet vatten
    s = g.world.own.state
    s.speed = 0.0
    s.order_speed(0)
    nav._steer_to_opening()
    nav._steer_step(StationSteer)
    assert nav.steer is None
    assert s.ordered_speed == 0


def _round_opening(g, radius_nm):
    """Isen som en rund öppning kring tornet (sanningens is byts mot en enkel funktion)."""
    s = g.world.own.state
    s.speed = s.ordered_speed = 0.0
    x0, y0 = s.x, s.y
    ice = g.world.env.ice
    ice.thickness_at = lambda x, y: 0.0 if math.hypot(x - x0, y - y0) < radius_nm else 3.0


def test_sounder_fore_and_aft_tells_whether_the_hull_fits():
    """Isekolodet för och akter: tornet i en liten öppning räcker inte för ytläge."""
    g, _ = _arctic(1)
    nav = g.station(NavigationStation)
    _round_opening(g, 0.02)                     # 37 m: för- och akterskeppet (50 m) under isen
    for _ in range(12):
        g.tick()
    assert not nav.hull_clear()
    _round_opening(g, 0.1)                      # 185 m: hela skrovet under öppet vatten
    for _ in range(12):
        g.tick()
    assert nav.hull_clear()


def test_vak_goes_back_to_a_small_opening_we_just_passed():
    """'Stoppa här' kom medan vi låg under en liten öppning med öppet vatten; när ordern kom hade vi
    glidit förbi. Vak går tillbaka dit, fast best() inte tar så små (förut: 'ingen öppning loggad')."""
    g, reports = _arctic(1)
    nav = g.station(NavigationStation)
    t0 = g.now - 30
    x, y = nav.est_x, nav.est_y
    for i, th in enumerate([3.0, 0.0, 0.0, 3.0]):       # ~30 m öppet vatten
        nav.icemap.on_sounding(IceSoundingObs(t0 + 5 * i, x, y - (30 - i * 10) * M, th, 0.89 * th))
    small = nav.icemap.openings[-1]
    assert nav.icemap.best(g.now, x, y) is not small
    nav._go_to_opening()
    assert nav.vak is small


def test_vak_takes_the_opening_that_was_good_a_minute_ago():
    """Maskin föreslog en öppning; på de sekunder kaptenen tänkte blev den 'dålig'. Vak går ändå dit."""
    m = IceMap()
    _feed(m, [3.0] * 3 + [0.0] * 10 + [3.0] * 3)
    o = m.openings[0]
    t = next(t for t in range(o.last.t, o.last.t + 7200, 5) if o.quality(t) < Quality.OSAKER)
    assert m.best(t, 0.0, 0.0) is None
    assert m.best(t - 60, 0.0, 0.0) is o


def test_a_failed_surfacing_drops_the_opening():
    """Arktis frö 13: ytläge genom nyis, isen drev in över akterskeppet på vägen upp, och navigatören
    föreslog samma öppning igen. Nu stryks den."""
    g, reports = _arctic(1)
    nav = g.station(NavigationStation)
    _round_opening(g, 0.1)
    s = g.world.own.state
    s.depth = s.ordered_depth = 40.0
    for _ in range(12):
        g.tick()
    o = nav.icemap.current
    assert o is not None
    nav._surfacing_through = o.no
    _round_opening(g, 0.02)                     # isen har drivit in: skrovet ryms inte längre
    s.ordered_depth = 0.0
    for _ in range(12):
        g.tick()
    assert o.dropped and nav._surfacing_through is None


def test_no_exit_suggestion_while_going_to_an_opening():
    """Duell frö 51: 'kurs 180 ut ur området' kom medan vaken lade om för sambandstillfället."""
    g, reports = _arctic(1)
    nav = g.station(NavigationStation)
    g.escape_ready = lambda: True
    nav.outside_area = lambda: False
    nav.exit_route = lambda: (180.0, 5.0, False)
    for _ in range(200):                        # förbi EXIT_FIRST_SUGGEST_S
        g.tick()
    nav._exit_cache = None
    from sim.icemap import IceSoundingObs as _Obs
    o = _Obs(g.now, nav.est_x, nav.est_y + 0.05, 0.0, 0.0)
    from sim.icemap import Opening as _Opening
    nav.vak, nav._vak_t = _Opening(99, o, o), g.now
    nav._escape_watch()
    for _ in range(10):
        nav._vak_t = g.now
        g.tick()
    assert not any(r.type == "nav.suggest.exit" for r in reports)
    nav.vak = None
    nav._escape_watch()
    for _ in range(10):
        g.tick()
    assert any(r.type == "nav.suggest.exit" for r in reports)


def test_no_search_on_suggestion_while_going_to_an_opening():
    """Arktis frö 3: 'sök vidare, fart 5' levererades sekunden efter att kaptenen sagt vak och avbröt den."""
    from sim.stations.navigation.common import SAFE_ICE_DEPTH
    g, _ = _arctic(1)
    nav = g.station(NavigationStation)
    order = f"fart 5, djup {SAFE_ICE_DEPTH}"
    assert not nav.vetoes(order)
    nav.vak = object()
    assert nav.vetoes(order)


def test_with_smoke_aboard_a_narrow_opening_at_the_station_is_for_the_masts():
    """Arktis frö 2: vid stationen, tät rök, öppet vatten ovanför: 'för smal för ytläge, vi letar vidare'.
    Masterna räcker för att ventilera: periskopdjup först."""
    g, reports = _arctic(1)
    nav = g.station(NavigationStation)
    _round_opening(g, 0.02)                     # 37 m öppet vatten kring tornet
    for _ in range(12):
        g.tick()
    o = nav.icemap.current
    assert o is not None and o.length_m < 120
    nav.near_station = lambda: True
    g.world.own.sys.smoke = 0.5
    nav.vak, nav._vak_t, nav._vak_stopping, nav._vak_tries = o, g.now, True, 9
    g.world.own.state.speed = 0.0
    nav._steer_to_opening()
    for _ in range(10):
        g.tick()
    ups = [r for r in reports if r.type == "nav.suggest.up"]
    assert ups and ups[-1].data["order"] == "periskopdjup"
    assert not any(r.type == "nav.vak.narrow_station" for r in reports)
