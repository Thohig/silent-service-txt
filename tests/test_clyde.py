"""Firth of Clyde (N2–N6): geografin, fyrarna, molnen, Polarisbåten, inspelningen och målen."""
import random

import pytest

from sim.environment import CLOUD_STARS, Clouds, Environment
from sim.events import ReportDelivered
from sim.game import Game
from sim.goals import EscapeGoal, RecordGoal
from sim.scenario import build_scenario
from sim.seabed import CLYDE_LIGHTS, CLYDE_PLADDA, clyde_seabed, light_visible
from sim.stations.navigation import NavigationStation
from sim.stations.recording import RECORD_S


def _light(name):
    return next(l for l in CLYDE_LIGHTS if l.name == name)


def test_the_firth_has_its_islands_channels_and_holy_loch():
    sb = clyde_seabed(random.Random(1))
    assert sb.depth_at(*CLYDE_PLADDA) < 0                  # Pladda
    assert sb.depth_at(9.5, 12.5) < 0                      # Arran
    assert sb.depth_at(20.9, 20.3) < 0                     # Great Cumbrae
    assert sb.depth_at(19.0, 17.4) < 0                     # Little Cumbrae
    assert sb.depth_at(30.0, 20.0) < 0                     # Ayrshire
    assert 120 < sb.depth_at(20.0, 12.0) < 170             # Arrandjupet
    west, largs = sb.depth_at(18.6, 20.3), sb.depth_at(22.2, 20.3)
    assert west > 50 and 15 < largs < west                 # Largs-rännan grundare
    widths = [x / 10 for x in range(210, 240) if sb.depth_at(x / 10, 20.3) > 0]
    assert max(widths) - min(widths) < 1.0                 # och under en sjömil bred öster om ön
    assert 5 < sb.depth_at(20.4, 33.15) < 30               # Holy Loch: grund vik
    assert sb.depth_at(17.0, -5.0) > 80                    # södra änden ut till havs


def test_the_british_chart_is_close_to_the_truth():
    rng = random.Random(3)
    sb = clyde_seabed(rng)
    chart = sb.chart_copy(rng, err_nm=0.1, miss_p=0.0)
    for p in ((18.0, 10.0), (20.0, 25.8), (21.0, 30.0), (19.6, 19.0)):
        assert abs(chart.depth_at(*p) - sb.depth_at(*p)) < 0.25 * sb.depth_at(*p) + 5


def test_lights_have_range_and_land_hides_them():
    sb = clyde_seabed(random.Random(1))
    assert light_visible(sb, _light("Pladda"), 17.0, 1.0)
    assert not light_visible(sb, _light("Toward Point"), 17.0, 1.0)      # för långt
    # Little Cumbrae-fyren står på öns västra sida: från nordost skymmer ön den
    assert not light_visible(sb, _light("Little Cumbrae"), 19.6, 18.2)
    assert light_visible(sb, _light("Little Cumbrae"), 17.6, 17.0)


def test_clouds_dim_the_moon_and_have_breaks():
    c = Clouds(0.9, breaks=((100, 200),))
    assert c.at(50) == 0.9 and c.at(150) < CLOUD_STARS
    clear = Environment(lat=55.75, lon=-4.95, utc_offset_h=1.0, date=(1962, 10, 20),
                        clock_start=3 * 3600)
    cloudy = Environment(lat=55.75, lon=-4.95, utc_offset_h=1.0, date=(1962, 10, 20),
                         clock_start=3 * 3600, clouds=Clouds(0.9))
    assert clear.light(0).moon_light > 0.1
    assert cloudy.light(0).moon_light < 0.4 * clear.light(0).moon_light


def _night_game(key="clyde", seed=1):
    g = Game(build_scenario(key, random.Random(seed)), seed=seed)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports, g.station(NavigationStation)


def test_no_star_fix_under_the_clouds():
    g, _, nav = _night_game()
    g.world.env.clouds = Clouds(0.95)
    method, _, why = nav._star_method()
    assert method is None and "molnen" in why


def test_night_fix_on_two_lights_one_light_or_none():
    g, reports, nav = _night_game()
    o = g.world.own.state
    o.depth = o.ordered_depth = 17.0
    o.speed = o.ordered_speed = 3.0
    o.x, o.y = 17.0, 1.0                                    # Pladda och Holy Isle syns
    g.command("fix")
    assert nav.tasks["fix"].sigma == pytest.approx(0.1)
    nav.tasks.clear()
    o.x, o.y = 19.6, 18.2                                   # bakom Little Cumbrae
    seen = nav.visible_lights()
    g.command("fix")
    if not seen:
        assert "fix" not in nav.tasks
        for _ in range(8):
            g.tick()
        assert any(r.type == "nav.fix.refused" and "fyrar" in r.text for r in reports)
    else:
        assert nav.tasks["fix"].sigma >= 0.1


def test_short_variant_starts_with_a_poor_reckoning_beside_the_track():
    g = Game(build_scenario("clyde-in", random.Random(2)), seed=2)
    nav = g.station(NavigationStation)
    o = g.world.own.state
    assert nav.uncertainty() >= 1.0
    assert (nav.est_x, nav.est_y) != (o.x, o.y)
    ss = next(v for v in g.world.contacts if v.id == "SSBN")
    assert ss.state.y > o.y and ss.state.speed > 5      # på väg ned mot oss
    assert g.knowledge.order_tasks == frozenset({"inspelning"})


def test_polaris_waits_then_goes_down_the_firth():
    sc = build_scenario("clyde", random.Random(4))
    w = sc.world
    ai = next(a for a in w.ais if getattr(a, "vessel", None) and a.vessel.id == "SSBN")
    y0 = ai.vessel.state.y
    w.time = ai.depart_t - 5
    ai.step(w)
    assert ai.state == "waiting"
    w.time = ai.depart_t
    for _ in range(3):
        ai.step(w)
    assert ai.state == "transit" and ai.vessel.state.ordered_speed > 0
    assert ai.vessel.state.y <= y0 + 0.01


def test_record_goal_needs_the_tape_and_misses_when_it_has_gone():
    sc = build_scenario("clyde", random.Random(1))
    w = sc.world
    rec, esc = w.goal(RecordGoal), w.goal(EscapeGoal)
    assert rec.outcome is None and esc.requires_record == "SSBN"
    o = w.own.state
    o.y = -1.0                                              # söder om Pladda
    assert not esc.check(w)                                 # utan bandet räknas det inte
    w.mission["recorded"] = ["SSBN"]
    assert not rec.check(w)                                 # inspelningen avslutar inte spelet
    ss = next(v for v in w.contacts if v.id == "SSBN")
    w.mission["recorded"] = []
    ss.state.y = rec.miss_y - 0.1
    assert rec.check(w) and w.outcome["outcome"] == "record_missed"


def test_recording_mission_keeps_the_navigator_from_hiding_on_the_bottom():
    g, _, nav = _night_game("clyde-in", seed=3)
    g.knowledge.threat_held = lambda: True
    nav.bottom_here = lambda: (80.0, "sand")
    assert nav._settle_proposal() is None
    g.knowledge.hunted = lambda now: True
    assert nav._settle_proposal() is not None


@pytest.mark.slow
def test_recording_with_the_crews_tools_over_seeds():
    """Kort variant: över skiktet och mot kontakten (som sonar föreslår) ger oftast bandet;
    stilla vid sidan av farleden sällan."""
    from sim.stations.sonar_room import SonarRoom
    done = {"passiv": 0, "verktyg": 0}
    for bot in done:
        for seed in range(1, 5):
            g = Game(build_scenario("clyde-in", random.Random(seed)), seed=seed)
            acted = False
            for _ in range(3600):
                if g.over:
                    break
                g.tick()
                if bot == "verktyg" and not acted:
                    pol = [t for t in g.knowledge.tracks.values()
                           if "Polaris" in t.classification and t.held]
                    if pol:
                        acted = True
                        g.command(f"djup 40, följ {pol[0].designation}")
            son = g.station(SonarRoom)
            rec = max((son.recorded_s(d) for d in g.knowledge.tracks), default=0)
            if (g.world.outcome or {}).get("outcome") == "recorded":
                assert rec >= RECORD_S and g.knowledge.recorded
                done[bot] += 1
    assert done["verktyg"] >= 2 and done["passiv"] <= 2, done


def test_patrol_boats_listen_in_peace_and_ping_when_they_search():
    from sim.harbor import PatrolBoatAI
    sc = build_scenario("clyde", random.Random(2))
    w = sc.world
    pings = []
    orig = w.emit
    w.emit = lambda tr: (pings.append(tr.source_id) if tr.kind == "ping" else None, orig(tr))
    for _ in range(300):
        w.tick()
    assert pings == []
    boat = next(a for a in w.ais if isinstance(a, PatrolBoatAI))
    boat.start_hunt(boat.vessel.state.x + 1, boat.vessel.state.y, 50, 0.5, t=w.time)
    for _ in range(60):
        w.tick()
    assert boat.vessel.id in pings


@pytest.mark.slow
def test_sonar_does_not_steer_us_onto_the_chart_land_for_the_tape():
    """clyde-in frö 102 (kaosboten): sonar föreslog kurs mot Polarisbåten in mot land, navigatören
    föreslog genast en gir bort, och så fram och tillbaka var annan minut."""
    g = Game(build_scenario("clyde-in", random.Random(102)), seed=102)
    nav = g.station(NavigationStation)
    bad = []

    def on(e):
        r = e.report
        if r.type == "sonar.suggest.record_close" and not nav.course_safe(r.data["bearing"]):
            bad.append((g.clock_str(), r.data["bearing"]))
    g.bus.subscribe(ReportDelivered, on)
    for _ in range(15 * 60):
        g.tick()
        if g.active_suggestion() and g.now % 20 == 0:
            g.command("ja")
    assert not bad


def test_the_tape_intercepts_a_moving_target_instead_of_chasing_its_bearing():
    """clyde-in (ja-boten): "kurs mot den, fart 5" var femte minut efter en Polarisbåt i 10 knop, som drog
    ifrån. Nu: kurs med förhåll; kommer den mot oss men korsar för fort, mot dess väg; går den ifrån oss
    fortare än vi tyst kan gå, inget förslag (sonar säger det en gång)."""
    from sim.stations import SonarRoom
    g = Game(build_scenario("clyde-in", random.Random(1)), seed=1, warm_up=False)
    son = g.station(SonarRoom)
    st = g.world.own.state
    st.depth = st.ordered_depth = 40.0
    # långsamt mål tvärs, på väg österut: förhåll åt öster, lägsta fart
    course, speed, meet = son._intercept(0.0, 90.0, 3.0)
    assert 0 < course < 90 and speed == 5 and not meet
    # på väg bort i 10 knop: går inte
    assert son._intercept(0.0, 0.0, 10.0) is None
    # mot oss men tvärs för fort: mot dess väg, åt det håll den går
    course, speed, meet = son._intercept(0.0, 150.0, 14.0)
    assert meet and course == 60 and speed >= 5


def test_the_plot_does_not_suggest_a_leg_off_the_tape_target():
    from sim.knowledge import ContactTrack
    from sim.stations.plot import PlotTeam
    g = Game(build_scenario("clyde-in", random.Random(1)), seed=1, warm_up=False)
    plot = g.station(PlotTeam)
    tr = ContactTrack("S-9", 0, classification="Polarisubåt i ytläge")
    assert "inspelning" in g.knowledge.order_tasks
    assert plot._recording_target(tr)
    g.knowledge.recorded.add("S-9")
    assert not plot._recording_target(tr)
