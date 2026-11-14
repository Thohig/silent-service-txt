import random

from sim.geo import bearing_to, distance
from sim.reports import Quality
from sim.ship import ShipState
from sim.tma import BearingObs, solve


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
