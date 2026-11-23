import pytest
import dataclasses
import random

from sim.geo import bearing_to, distance
from sim.reports import Quality
from sim.ship import ShipState
from sim.tma import (HUNTER_MANEUVER_Q, MANEUVER_CHI2, MANEUVER_SPLIT, MAX_TARGET_KN, BearingObs,
                     maneuver_statistic, quality_from, solve)


def _run(own, tgt, seconds, rng, obs, sigma=1.0, every=10, t0=0):
    for t in range(t0, t0 + seconds):
        if t % every == 0:
            b = bearing_to(own.x, own.y, tgt.x, tgt.y) + rng.gauss(0, sigma)
            obs.append(BearingObs(t, b % 360, sigma, own.x, own.y, own.course))
        own.step(1)
        tgt.step(1)
    return t0 + seconds


def _scenario():
    own = ShipState(x=10, y=2, course=0, speed=6)
    tgt = ShipState(x=3, y=12, course=100, speed=15)
    return own, tgt


def test_too_few_bearings_gives_no_solution_or_poor():
    own, tgt = _scenario()
    obs = []
    _run(own, tgt, 30, random.Random(1), obs)
    sol = solve(obs)
    assert sol is None or sol.quality == Quality.DALIG


def test_solution_improves_after_own_course_change():
    """Över många slumpfrön: kursbytet ger alltid mindre osäkerhet och
    nästan alltid bättre kvalitet och en lösning nära sanningen."""
    better_quality = 0
    errors = []
    n = 12
    for seed in range(n):
        rng = random.Random(seed)
        own = ShipState(x=10, y=2, course=0, speed=6)
        tgt = ShipState(x=6, y=7, course=100, speed=15)
        obs: list[BearingObs] = []

        t = _run(own, tgt, 600, rng, obs, sigma=0.7)            # ben 1: rak kurs
        leg1 = solve(obs, t_now=t, own_now=(own.x, own.y))

        own.order_course(90)                                     # kursbyte
        t = _run(own, tgt, 600, rng, obs, sigma=0.7, t0=t)       # ben 2
        leg2 = solve(obs, t_now=t, own_now=(own.x, own.y))
        true_r = distance(own.x, own.y, tgt.x, tgt.y)

        assert not leg1.own_maneuvered and leg2.own_maneuvered
        assert leg1.quality == Quality.DALIG
        assert leg2.rel_range_error < leg1.rel_range_error / 2
        better_quality += leg2.quality > leg1.quality
        errors.append(abs(leg2.range_nm - true_r) / true_r)

    errors.sort()
    assert better_quality >= n - 1
    assert errors[n // 2] < 0.25          # medianfel i avstånd under 25 %


def test_noise_free_two_leg_solution_is_exact():
    own, tgt = _scenario()
    obs: list[BearingObs] = []
    t = _run(own, tgt, 400, random.Random(0), obs, sigma=0.0001)
    own.order_course(300)
    t = _run(own, tgt, 400, random.Random(0), obs, sigma=0.0001, t0=t)
    sol = solve(obs, t_now=t, own_now=(own.x, own.y))
    assert abs(sol.x - tgt.x) < 0.05 and abs(sol.y - tgt.y) < 0.05
    assert abs(sol.course - 100) < 1 and abs(sol.speed - 15) < 0.3


def test_range_measurements_fix_solution_without_maneuver():
    """En periskop-/radarmätning ger avstånd även på rak kurs."""
    rng = random.Random(5)
    own = ShipState(x=10, y=2, course=0, speed=6)
    tgt = ShipState(x=6, y=7, course=100, speed=15)
    obs: list[BearingObs] = []
    t = _run(own, tgt, 600, rng, obs, sigma=0.7)
    bearings_only = solve(obs, t_now=t, own_now=(own.x, own.y))
    r = distance(own.x, own.y, tgt.x, tgt.y)
    b = bearing_to(own.x, own.y, tgt.x, tgt.y)
    obs.append(BearingObs(t, b, 0.5, own.x, own.y, own.course, range_nm=r * 1.05,
                          range_sigma=0.08 * r, source="periskop"))
    with_range = solve(obs, t_now=t, own_now=(own.x, own.y))
    assert bearings_only.quality == Quality.DALIG
    assert with_range.rel_range_error < bearings_only.rel_range_error / 3
    assert abs(with_range.range_nm - r) / r < 0.15


def test_target_maneuver_is_detected_by_poor_fit():
    rng = random.Random(9)
    own = ShipState(x=10, y=2, course=0, speed=6)
    tgt = ShipState(x=6, y=7, course=100, speed=15, turn_rate=3, accel=0.5, max_speed=30)
    obs: list[BearingObs] = []
    t = _run(own, tgt, 400, rng, obs, sigma=0.7)
    own.order_course(90)
    t = _run(own, tgt, 400, rng, obs, sigma=0.7, t0=t)
    before = solve(obs, t_now=t, own_now=(own.x, own.y))
    tgt.order_course(280)                       # jagaren vänder och ökar
    tgt.order_speed(28)
    t = _run(own, tgt, 300, rng, obs, sigma=0.7, t0=t)
    after = solve(obs, t_now=t, own_now=(own.x, own.y))
    assert before.fit < 2.0
    assert after.fit > 4.0 and after.quality == Quality.DALIG


# --- målmanöver: brytpunktstestet ---------------------------------------------------
def _two_legs(seed, turn_to=None, turn_rate=1.0):
    """Egen ubåt sicksackar; målet går rakt eller girar mjukt efter 20 min."""
    rng = random.Random(seed)
    own = ShipState(x=10, y=2, course=0, speed=5)
    tgt = ShipState(x=6, y=8, course=100, speed=15, turn_rate=turn_rate, max_speed=30)
    obs: list[BearingObs] = []
    t = _run(own, tgt, 600, rng, obs, sigma=1.0, every=5)
    own.order_course(60)
    t = _run(own, tgt, 600, rng, obs, sigma=1.0, every=5, t0=t)
    if turn_to is not None:
        tgt.order_course(turn_to)
    t = _run(own, tgt, 420, rng, obs, sigma=1.0, every=5, t0=t)
    return obs, t, own, tgt


@pytest.mark.slow
def test_gentle_target_turn_is_found_by_the_split_test():
    """En gir på 35° som den sammanlagda anpassningen inte ser (fit ~1)."""
    found = 0
    for seed in range(8):
        obs, t, own, tgt = _two_legs(seed, turn_to=135)
        sol = solve(obs, t_now=t, own_now=(own.x, own.y))
        assert sol.fit < MANEUVER_CHI2
        if maneuver_statistic(obs, sol) > MANEUVER_SPLIT:
            found += 1
    assert found >= 7


@pytest.mark.slow
def test_straight_target_rarely_trips_the_split_test():
    stats = []
    for seed in range(20):
        obs, t, own, tgt = _two_legs(100 + seed)
        stats.append(maneuver_statistic(obs))
    assert sum(s > MANEUVER_SPLIT for s in stats) <= 1
    assert sorted(stats)[len(stats) // 2] < 5


def test_impossible_speed_is_poor_quality():
    obs, t, own, tgt = _two_legs(3)
    sol = solve(obs, t_now=t, own_now=(own.x, own.y))
    assert sol.quality >= Quality.GOD
    fast = [BearingObs(o.t // 3, o.bearing, o.sigma, o.own_x, o.own_y, o.own_course)
            for o in obs]                       # samma bäringar på en tredjedel av tiden
    q = solve(fast)
    assert q.speed > MAX_TARGET_KN and q.quality == Quality.DALIG


def _looks(own, tgt, seconds, rng, obs, look_every=120, r_frac=0.08, c_sigma=8.0):
    """Sonarbäringar var 5:e s och periskoptittar med avstånd, kurs och fart."""
    for t in range(seconds):
        if t % 5 == 0:
            b = bearing_to(own.x, own.y, tgt.x, tgt.y) + rng.gauss(0, 1.0)
            obs.append(BearingObs(t, b % 360, 1.0, own.x, own.y, own.course))
        if t % look_every == look_every // 2:
            r = distance(own.x, own.y, tgt.x, tgt.y)
            rs = r_frac * r + 0.03
            obs.append(BearingObs(t, bearing_to(own.x, own.y, tgt.x, tgt.y) % 360, 0.5,
                                  own.x, own.y, own.course, range_nm=r + rng.gauss(0, rs),
                                  range_sigma=rs, source="periskop",
                                  course_obs=(tgt.course + rng.gauss(0, c_sigma)) % 360,
                                  course_sigma=c_sigma,
                                  speed_obs=tgt.speed + rng.gauss(0, 2.0), speed_sigma=2.3))
        own.step(1)
        tgt.step(1)


def test_periscope_course_and_speed_pin_down_the_target_over_seeds():
    """Periskopets kurs och fart (vinkel på bogen) gör lösningen rätt, inte bara säker:
    med några tittar på 3 nm är kursfelet litet och farten nära sanningen."""
    course_err, speed_err, without = [], [], []
    for seed in range(8):
        rng = random.Random(seed)
        own = ShipState(x=0, y=0, course=0, speed=3)
        tgt = ShipState(x=-1.5, y=3.0, course=120, speed=12)
        obs = []
        _looks(own, tgt, 420, rng, obs)
        sol = solve(obs)
        course_err.append(abs((sol.course - 120 + 180) % 360 - 180))
        speed_err.append(abs(sol.speed - 12))
        bare = [BearingObs(**{**o.__dict__, "course_obs": None, "speed_obs": None}) for o in obs]
        without.append(abs(solve(bare).speed - 12))
    assert sorted(course_err)[6] < 12
    assert sorted(speed_err)[6] < 2.5
    assert sum(speed_err) < sum(without)


def test_plot_sees_a_turn_in_the_periscope():
    """En titt som visar annan kurs än lösningen: plottet börjar om från titten."""
    from sim.game import Game
    from sim.scenario import default_scenario
    from sim.stations.plot import PlotTeam
    from sim.knowledge import ContactTrack
    g = Game(default_scenario(random.Random(1)), seed=1)
    plot = g.station(PlotTeam)
    rng = random.Random(4)
    own = ShipState(x=0, y=0, course=0, speed=3)
    tgt = ShipState(x=-1.5, y=3.0, course=120, speed=12)
    obs = []
    _looks(own, tgt, 400, rng, obs)
    tr = ContactTrack("S-9", 0, observations=list(obs))
    assert plot._look_turn(tr) is None              # titten stämmer med lösningen
    tgt.course = tgt.ordered_course = 60
    more = []
    _looks(own, tgt, 130, rng, more)
    tr.observations += [BearingObs(**{**o.__dict__, "t": o.t + 400}) for o in more]
    look = plot._look_turn(tr)
    assert look is not None and look.t > 400


# --- ärlig kvalitet: girar som plottet inte sett --------------------------------------
def test_course_uncertainty_caps_quality():
    """Ett säkert avstånd duger inte om kursen är okänd och målet går."""
    assert quality_from(0.05, 100, 600) == Quality.SAKER
    assert quality_from(0.05, 100, 600, course_sigma=20, speed=10) == Quality.GOD
    assert quality_from(0.05, 100, 600, course_sigma=40, speed=10) == Quality.OSAKER
    assert quality_from(0.05, 100, 600, course_sigma=70, speed=10) == Quality.DALIG
    # ett mål som nästan ligger still: kursen spelar ingen roll
    assert quality_from(0.05, 100, 600, course_sigma=70, speed=1) == Quality.SAKER
    # ... men inte om farten är så osäker att det lika gärna kan gå (provspelet: en trupptransport
    # i 6 kn skattad till 2 kn kallades god med okänd kurs, och den raka torpeden missade)
    assert quality_from(0.05, 100, 600, course_sigma=70, speed=1, speed_sigma=2) == Quality.DALIG


def test_solution_without_new_bearings_grows_uncertain():
    """Utan nya bäringar kan målet ha girat: lösningen blir osäkrare för varje minut."""
    for seed in range(6):
        obs, t, own, tgt = _two_legs(seed)
        now = solve(obs, t_now=t, own_now=(own.x, own.y))
        later = solve(obs, t_now=t + 600, own_now=(own.x, own.y))
        assert now.quality >= Quality.GOD
        assert later.quality <= Quality.OSAKER
        assert later.range_sigma > 2 * now.range_sigma
        assert later.course_sigma > 30


def test_unseen_turn_is_inside_the_stated_uncertainty():
    """Målet girar 90° strax efter sista bäringen. Tio minuter senare ligger det sanna
    läget inom tre σ av lösningen i nästan alla frön (förut: lösningen kallades god
    med σ ~0,3 nm och felet var 2–3 nm)."""
    inside = 0
    n = 12
    for seed in range(n):
        obs, t, own, tgt = _two_legs(seed)
        tgt.order_course(10)
        for _ in range(600):
            tgt.step(1)
        sol = solve(obs, t_now=t + 600, own_now=(own.x, own.y))
        err = distance(sol.x, sol.y, tgt.x, tgt.y)
        inside += err < 3 * sol.range_sigma or sol.quality == Quality.DALIG
    assert inside >= n - 1


def test_hunting_target_gets_more_maneuver_noise():
    """Ett mål som pingar jagar oss och girar hela tiden: större osäkerhet."""
    obs, t, own, tgt = _two_legs(4)
    calm = solve(obs, t_now=t, own_now=(own.x, own.y))
    hunter = solve(obs, t_now=t, own_now=(own.x, own.y), maneuver_q=HUNTER_MANEUVER_Q)
    assert hunter.range_sigma > 2 * calm.range_sigma
    assert hunter.quality < calm.quality


def test_knowledge_treats_pinging_contact_as_hunter_when_we_are_hunted():
    from sim.knowledge import ContactTrack, Knowledge
    obs, t, own, tgt = _two_legs(4)
    k_calm, k_hunt = Knowledge(), Knowledge()
    for k in (k_calm, k_hunt):
        k.tracks["S-1"] = ContactTrack("S-1", 0)
    for o in obs:
        k_calm.on_bearing(dataclasses.replace(o, designation="S-1"))
        k_hunt.on_bearing(dataclasses.replace(o, designation="S-1",
                                              source="ping" if o.t > t - 120 else "sonar"))
    calm = k_calm.resolve("S-1", t, (own.x, own.y))
    # pingar i lugn patrull: inget extra brus
    assert k_hunt.resolve("S-1", t, (own.x, own.y)).range_sigma < 1.5 * calm.range_sigma
    k_hunt.hunt_t = t - 60                      # sonar har hört jakttecken
    hunt = k_hunt.resolve("S-1", t, (own.x, own.y))
    assert hunt.range_sigma > 2 * calm.range_sigma


def test_straight_target_error_matches_stated_uncertainty():
    """Rakt mål, två ben: felet ligger inom tre σ i nästan alla frön."""
    inside, n = 0, 20
    for seed in range(n):
        obs, t, own, tgt = _two_legs(200 + seed)
        sol = solve(obs, t_now=t, own_now=(own.x, own.y))
        inside += distance(sol.x, sol.y, tgt.x, tgt.y) < 3 * sol.range_sigma
    assert inside >= n - 1


def test_knowledge_gives_a_zigzagging_contact_more_maneuver_noise():
    from sim.knowledge import ContactTrack, Knowledge
    obs, t, own, tgt = _two_legs(4)
    k = Knowledge()
    k.tracks["S-1"] = tr = ContactTrack("S-1", 0)
    for o in obs:
        k.on_bearing(dataclasses.replace(o, designation="S-1"))
    straight = k.resolve("S-1", t, (own.x, own.y))
    tr.turns = [t - 1500, t - 900]                  # plottet har sett två girar
    assert k.zigzags(tr)
    assert k.resolve("S-1", t, (own.x, own.y)).range_sigma > 1.5 * straight.range_sigma


def test_range_sigma_never_collapses_below_the_boats_length():
    """En lösning som kollapsar mot oss får inte påstå att avståndet är känt på meter."""
    from sim.tma import RANGE_SIGMA_FLOOR_NM
    obs, t, own, tgt = _two_legs(4)
    sol = solve(obs, t_now=t, own_now=(own.x, own.y))
    assert sol.range_sigma >= RANGE_SIGMA_FLOOR_NM
    own2 = ShipState(x=0, y=0, course=0, speed=5)
    near = ShipState(x=0.05, y=0.04, course=200, speed=10)
    obs2 = []
    rng = random.Random(1)
    t2 = _run(own2, near, 120, rng, obs2, every=5)
    s2 = solve(obs2, t_now=t2, own_now=(own2.x, own2.y))
    if s2 is not None and s2.range_nm < 0.1:
        assert s2.range_sigma >= RANGE_SIGMA_FLOOR_NM and s2.quality <= Quality.OSAKER


def test_a_zigzagger_may_have_turned_unseen_unless_we_just_looked():
    """Ett mål som girar ofta kan ha girat de senaste minuterna utan att bäringarna visat det än:
    kursen kan inte vara säker. En färsk periskoptitt visar kursen och tar bort det tvivlet."""
    from sim.tma import ZIGZAG_MANEUVER_Q
    rng = random.Random(3)
    own = ShipState(x=0, y=0, course=0, speed=3)
    tgt = ShipState(x=-1.5, y=3.0, course=120, speed=12)
    obs = []
    _looks(own, tgt, 600, rng, obs, look_every=120)
    t_end = obs[-1].t
    straight = solve(obs, maneuver_q=1.0)
    stale = [o for o in obs if not (o.course_obs is not None and o.t > t_end - 400)]
    zig_stale = solve(stale, maneuver_q=ZIGZAG_MANEUVER_Q)
    assert zig_stale.course_sigma >= 15.0 and zig_stale.quality <= Quality.GOD
    fresh = stale + [dataclasses.replace(obs[-1], t=t_end + 1, source="periskop", course_obs=120.0,
                                         course_sigma=8.0)]
    zig_fresh = solve(fresh, maneuver_q=ZIGZAG_MANEUVER_Q)
    assert zig_fresh.course_sigma < zig_stale.course_sigma - 5.0
    assert straight.course_sigma < zig_stale.course_sigma


def test_a_submerged_submarine_is_expected_to_turn():
    """Ubåten i duellen manövrerar när den söker eller anfaller oss: plottet räknar med giren (q som
    för sicksack); Polarisbåten i ytläge och ytfartyg gör det inte."""
    from sim.knowledge import submerged_submarine
    for c in ("möjlig undervattenskontakt", "trolig ubåt", "ubåt, atomdriven"):
        assert submerged_submarine(c), c
    for c in ("ubåt i ytläge, en axel, trolig Polarisbåt", "Polarisubåt i ytläge, atomdriven, en axel",
              "ytfartyg", "okänd kontakt", "jagare, ångturbiner, två axlar", None):
        assert not submerged_submarine(c), c
