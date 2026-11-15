"""Bäringsbaserad målrörelseanalys (TMA) med viktad minsta kvadrat.

Tillstånd: målets position och hastighet vid referenstiden t_ref,
    s = [x, y, vx, vy]   (nm, nm, knop, knop)
Modell: målet går rak kurs med konstant fart.

Lösningen hittas med Levenberg–Marquardt från flera startavstånd längs
senaste bäringen. Osäkerheten tas ur kovariansen (JᵀWJ)⁻¹. Kvaliteten
härleds ur den relativa avståndsosäkerheten och slumpas aldrig. Om
den egna båten inte har manövrerat är avståndet i princip omöjligt att
bestämma ur bäringar. Matrisen blir då nästan singulär, osäkerheten
stor och kvaliteten dålig, utan att någon specialregel behövs.

Plottlaget använder två svaga antaganden (apriorifördelningar) som håller
numeriken stabil när problemet är obestämt:
- målets fart kring 0 med σ = 30 kn,
- avståndet log-normalfördelat kring ett typiskt upptäcktsavstånd
  (faktor e i spridning). Det motverkar den kända dragningen mot orimligt
  korta avstånd vid brusiga bäringar, men är för svagt för att ensamt ge
  bättre kvalitet än "dålig".

Målet kan ha manövrerat utan att plottlaget märkt det än. Därför räknar
lösningen med processbrus (vit acceleration, TARGET_MANEUVER_Q): en bäring
som är τ timmar gammal har en extra osäkerhet i målets läge på
√(q·τ³/3) nm och i dess kurs/fart på √(q·τ) kn. Gamla bäringar väger alltså
mindre, och en lösning som räknas fram utan nya bäringar blir osäkrare med
tiden. Utan nya bäringar kan målet dessutom ha girat (UNSEEN_TURN_*), och
ett mål som pingar (jagar) får större processbrus (HUNTER_MANEUVER_Q).
Kursens osäkerhet sätter ett tak för kvaliteten (COURSE_SIGMA_LIMITS).
Utan detta kallades lösningar säkra fast målet hade girat eller kursen var
okänd (granskning 2026-11-15: grova fel bland god/säker 11 % ⇒ 7 %).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .geo import angle_diff, norm360
from .reports import Quality

VELOCITY_PRIOR_KN = 30.0
RANGE_PRIOR_NM = 6.0
RANGE_PRIOR_LOG_SIGMA = 1.0
MAX_SPAN_S = 1800                 # använd bäringar från de senaste 30 min
MAX_OBS = 400
MIN_OBS = 6
MIN_SPAN_S = 60
MANEUVER_CHI2 = 4.0     # över detta passar rak-kurs-modellen inte datan
# Brytpunktstest: hur mycket bättre två raka ben (före/efter de senaste minuterna)
# förklarar bäringarna än ett. Utan manöver ~chi² med 4 frihetsgrader (median 2,
# 99 % under 10 i provspel); en gir ger tiotals till hundratals.
MANEUVER_SPLIT = 15.0
SPLIT_AGES_S = (300, 600)       # pröva brytpunkt så här långt tillbaka
SPLIT_MIN_BEFORE = 12           # bäringar före brytpunkten
SPLIT_MIN_BEFORE_SPAN_S = 300
SPLIT_MIN_AFTER = 8
MAX_TARGET_KN = 35.0            # snabbare än något fartyg: rak-kurs-modellen stämmer inte
# Processbrus för målets manöver, kn²/h: hastighetens varians växer med q per timme.
# 1 ⇒ σ ≈ 0,4 kn efter 10 min, läget σ ≈ 0,04 nm efter 10 min och 0,2 nm efter 30.
# Bäringsbaserad TMA är känslig för detta: med 3 gav två ben ofta bara osäker, med 40
# aldrig god. Girar som syns tar brytpunktstestet, girar utan nya bäringar UNSEEN_TURN_*.
TARGET_MANEUVER_Q = 1.0
# Gir som ingen hört medan lösningen räknas fram utan nya bäringar: sannolikheten
# τ/(τ + benlängd) att målet girat, och då kanske så här mycket (1σ).
UNSEEN_TURN_LEG_H = 10 / 60
UNSEEN_TURN_DEG = 90.0
# Processbrus för ett mål som jagar (pingar): girar hela tiden.
HUNTER_MANEUVER_Q = 400.0
# Kursens σ (grader) som tak för kvaliteten: ≥ 15 högst god, ≥ 30 högst osäker,
# ≥ 60 dålig. Gäller mål som går minst COURSE_MATTERS_KN.
COURSE_SIGMA_LIMITS = (15.0, 30.0, 60.0)
COURSE_MATTERS_KN = 3.0
_START_RANGES_NM = (1.0, 2.0, 3.5, 5.0, 7.0, 10.0, 14.0)


@dataclass(frozen=True)
class BearingObs:
    t: int
    bearing: float          # uppmätt bäring, grader rätt
    sigma: float            # förväntat bäringsbrus, grader (1σ)
    own_x: float            # egen position enligt navigatören
    own_y: float
    own_course: float
    se: float = 0.0
    designation: str = ""
    range_nm: float | None = None    # avståndsmätning (periskop, radar, aktiv sonar)
    range_sigma: float = 0.0
    source: str = "sonar"            # sonar, ping, periskop, radar, aktiv
    # periskopets bedömning av målets kurs (vinkel på bogen) och fart, om den finns
    course_obs: float | None = None
    course_sigma: float = 0.0
    speed_obs: float | None = None
    speed_sigma: float = 0.0


@dataclass(frozen=True)
class Solution:
    t: int                  # tid lösningen avser
    t_ref: int
    state: tuple[float, float, float, float]   # x, y, vx, vy vid t_ref
    x: float
    y: float
    course: float
    speed: float
    range_nm: float
    bearing: float
    range_sigma: float
    course_sigma: float
    speed_sigma: float
    quality: Quality
    n_obs: int
    span_s: int
    own_maneuvered: bool
    rms_residual: float     # grader
    fit: float = 1.0        # normaliserad chi²: ~1 = modellen passar, >>1 = målet har manövrerat

    @property
    def rel_range_error(self) -> float:
        return self.range_sigma / max(self.range_nm, 1e-6)


def predicted_bearing(state: Sequence[float], t_ref: int, t: int,
                      own_x: float, own_y: float) -> float:
    x, y, vx, vy = state
    tau = (t - t_ref) / 3600.0
    return norm360(math.degrees(math.atan2(x + vx * tau - own_x, y + vy * tau - own_y)))


def quality_from(rel_range_error: float, n_obs: int, span_s: int,
                 course_sigma: float = 0.0, speed: float = 0.0) -> Quality:
    """Kvaliteten ur avståndets relativa osäkerhet, med kursens osäkerhet som tak
    när målet går (en lösning med okänd kurs duger inte att skjuta på)."""
    if n_obs < MIN_OBS or span_s < MIN_SPAN_S:
        return Quality.DALIG
    if rel_range_error < 0.10:
        q = Quality.SAKER
    elif rel_range_error < 0.25:
        q = Quality.GOD
    elif rel_range_error < 0.50:
        q = Quality.OSAKER
    else:
        return Quality.DALIG
    if speed >= COURSE_MATTERS_KN:
        for limit, cap in zip(COURSE_SIGMA_LIMITS, (Quality.GOD, Quality.OSAKER, Quality.DALIG)):
            if course_sigma >= limit:
                q = min(q, cap)
    return q


def own_maneuvered(obs: Sequence[BearingObs], threshold_deg: float = 20.0) -> bool:
    if not obs:
        return False
    c0 = obs[0].own_course
    return any(abs(angle_diff(o.own_course, c0)) > threshold_deg for o in obs)


class _Problem:
    """Minsta-kvadratproblemet. Med q > 0 och ett tillstånd att räkna avstånden ur
    får varje mätning sitt manöverbrus efter sin ålder (se modulens beskrivning)."""

    def __init__(self, obs: Sequence[BearingObs], t_ref: int, q: float = 0.0,
                 state: np.ndarray | None = None):
        self.n_b = len(obs)
        self.tau = np.array([(o.t - t_ref) / 3600.0 for o in obs])
        self.ox = np.array([o.own_x for o in obs])
        self.oy = np.array([o.own_y for o in obs])
        self.meas = np.radians([o.bearing for o in obs])
        age = np.maximum(-self.tau, 0.0)
        pos_var = q * age ** 3 / 3.0          # nm², målets läge vid mätningen
        vel_var = q * age                     # kn²
        if q > 0 and state is not None:
            x, y, vx, vy = state
            r2 = np.maximum((x + vx * self.tau - self.ox) ** 2
                            + (y + vy * self.tau - self.oy) ** 2, 0.01)
            sp2 = max(vx * vx + vy * vy, 1.0)
        else:
            r2, sp2 = np.full(self.n_b, np.inf), np.inf
        sig_b = np.radians([max(o.sigma, 0.05) for o in obs])
        w_b = 1.0 / (sig_b ** 2 + pos_var / r2)
        ranged = [i for i, o in enumerate(obs) if o.range_nm is not None]
        self.r_idx = np.array(ranged, dtype=int)
        self.r_meas = np.array([obs[i].range_nm for i in ranged])
        w_r = np.array([1.0 / (max(obs[i].range_sigma, 0.01) ** 2 + pos_var[i])
                        for i in ranged])
        vel = [i for i, o in enumerate(obs) if o.course_obs is not None]
        self.c_meas = np.radians([obs[i].course_obs for i in vel])
        w_c = np.array([1.0 / (math.radians(max(obs[i].course_sigma, 1.0)) ** 2
                               + vel_var[i] / sp2) for i in vel])
        spd = [i for i, o in enumerate(obs) if o.speed_obs is not None]
        self.s_meas = np.array([obs[i].speed_obs for i in spd], dtype=float)
        w_s = np.array([1.0 / (max(obs[i].speed_sigma, 0.5) ** 2 + vel_var[i]) for i in spd])
        self.w = np.concatenate([w_b, w_r, w_c, w_s])
        self.prior_w = 1.0 / VELOCITY_PRIOR_KN ** 2
        last = obs[-1]
        self.ref_x, self.ref_y = last.own_x, last.own_y
        self.range_w = 1.0 / RANGE_PRIOR_LOG_SIGMA ** 2
        self.log_r0 = math.log(RANGE_PRIOR_NM)

    def _range_prior(self, s: np.ndarray):
        """Residual och gradient för log-avståndsantagandet vid t_ref."""
        dx, dy = s[0] - self.ref_x, s[1] - self.ref_y
        r2 = max(dx * dx + dy * dy, 1e-6)
        e = self.log_r0 - 0.5 * math.log(r2)
        grad = np.array([dx / r2, dy / r2, 0.0, 0.0])   # d log r / ds
        return e, grad

    def residuals_and_jacobian(self, s: np.ndarray):
        x, y, vx, vy = s
        dx = x + vx * self.tau - self.ox
        dy = y + vy * self.tau - self.oy
        r2 = np.maximum(dx * dx + dy * dy, 1e-4)
        pred = np.arctan2(dx, dy)
        e = (self.meas - pred + np.pi) % (2 * np.pi) - np.pi
        db_dx = dy / r2
        db_dy = -dx / r2
        J = np.column_stack([db_dx, db_dy, db_dx * self.tau, db_dy * self.tau])
        if len(self.r_idx):
            i = self.r_idx
            r = np.sqrt(r2[i])
            er = self.r_meas - r
            ux, uy = dx[i] / r, dy[i] / r
            Jr = np.column_stack([ux, uy, ux * self.tau[i], uy * self.tau[i]])
            e = np.concatenate([e, er])
            J = np.vstack([J, Jr])
        # kurs och fart ur periskopet: rak kurs, så samma hastighet hela tiden
        sp2 = max(vx * vx + vy * vy, 1.0)
        sp = math.sqrt(sp2)
        if len(self.c_meas):
            ec = (self.c_meas - math.atan2(vx, vy) + np.pi) % (2 * np.pi) - np.pi
            Jc = np.tile([0.0, 0.0, vy / sp2, -vx / sp2], (len(ec), 1))
            e = np.concatenate([e, ec])
            J = np.vstack([J, Jc])
        if len(self.s_meas):
            es = self.s_meas - math.hypot(vx, vy)
            Js = np.tile([0.0, 0.0, vx / sp, vy / sp], (len(es), 1))
            e = np.concatenate([e, es])
            J = np.vstack([J, Js])
        return e, J

    def cost(self, s: np.ndarray) -> float:
        e, _ = self.residuals_and_jacobian(s)
        er, _ = self._range_prior(s)
        return float(np.sum(self.w * e * e) + self.prior_w * (s[2] ** 2 + s[3] ** 2)
                     + self.range_w * er * er)

    def normal_equations(self, s: np.ndarray):
        e, J = self.residuals_and_jacobian(s)
        JW = J.T * self.w
        H = JW @ J
        g = JW @ e
        H[2, 2] += self.prior_w
        H[3, 3] += self.prior_w
        g[2] -= self.prior_w * s[2]
        g[3] -= self.prior_w * s[3]
        er, gr = self._range_prior(s)
        H += self.range_w * np.outer(gr, gr)
        g += self.range_w * er * gr
        return H, g


def _levenberg_marquardt(p: _Problem, s0: np.ndarray, iters: int = 60):
    s = s0.copy()
    c = p.cost(s)
    lam = 1e-3
    for _ in range(iters):
        H, g = p.normal_equations(s)
        A = H + lam * np.diag(np.maximum(np.diag(H), 1e-9))
        try:
            delta = np.linalg.solve(A, g)
        except np.linalg.LinAlgError:
            lam *= 10
            continue
        s_new = s + delta
        c_new = p.cost(s_new)
        if c_new < c:
            improvement = c - c_new
            s, c = s_new, c_new
            lam = max(lam / 3, 1e-9)
            if improvement < 1e-9 * max(c, 1.0) and np.linalg.norm(delta) < 1e-7:
                break
        else:
            lam *= 4
            if lam > 1e10:
                break
    return s, c


def solve(observations: Sequence[BearingObs], t_now: int | None = None,
          own_now: tuple[float, float] | None = None,
          maneuver_q: float | None = None) -> Solution | None:
    """Lös målrörelsen. own_now är egen position vid t_now (för avstånd/bäring).
    maneuver_q: processbrus för målets manöver (None = TARGET_MANEUVER_Q, 0 = målet
    antas gå helt rakt)."""
    if maneuver_q is None:
        maneuver_q = TARGET_MANEUVER_Q
    obs = list(observations)[-MAX_OBS:]
    if obs:
        obs = [o for o in obs if o.t >= obs[-1].t - MAX_SPAN_S]
    if len(obs) < 3:
        return None
    last = obs[-1]
    t_ref = last.t
    t_now = t_ref if t_now is None else t_now
    own_now = (last.own_x, last.own_y) if own_now is None else own_now

    p = _Problem(obs, t_ref)
    b = math.radians(last.bearing)
    best: tuple[np.ndarray, float] | None = None
    for r0 in _START_RANGES_NM:
        s0 = np.array([last.own_x + r0 * math.sin(b), last.own_y + r0 * math.cos(b), 0.0, 0.0])
        s, c = _levenberg_marquardt(p, s0)
        if best is None or c < best[1]:
            best = (s, c)
    assert best is not None
    s, _ = best
    p_fit = p
    if maneuver_q > 0:
        # vikterna beror på avstånden: räkna om dem ur lösningen och lös igen
        for _ in range(2):
            p = _Problem(obs, t_ref, maneuver_q, s)
            s, _ = _levenberg_marquardt(p, s)

    H, _ = p.normal_equations(s)
    try:
        P = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        P = np.linalg.pinv(H)

    x, y, vx, vy = (float(v) for v in s)
    tau_n = (t_now - t_ref) / 3600.0
    tx, ty = x + vx * tau_n, y + vy * tau_n
    dx, dy = tx - own_now[0], ty - own_now[1]
    rng = math.hypot(dx, dy)
    ux, uy = (dx / rng, dy / rng) if rng > 1e-9 else (0.0, 0.0)
    g_r = np.array([ux, uy, ux * tau_n, uy * tau_n])
    # Målet kan ha manövrerat sedan senaste mätningen: dels jämnt (processbruset),
    # dels en gir som ingen hört, sannolikheten turn_p efter benlängden.
    speed = math.hypot(vx, vy)
    age_n = max(tau_n, 0.0)
    turn_p = age_n / (age_n + UNSEEN_TURN_LEG_H)
    range_sigma = math.sqrt(max(float(g_r @ P @ g_r), 0.0) + maneuver_q * age_n ** 3 / 3.0
                            + turn_p * (speed * age_n) ** 2)

    course = norm360(math.degrees(math.atan2(vx, vy)))
    if speed > 1e-6:
        g_s = np.array([0, 0, vx / speed, vy / speed])
        g_c = np.array([0, 0, vy / speed ** 2, -vx / speed ** 2])
        speed_sigma = math.sqrt(max(float(g_s @ P @ g_s), 0.0) + maneuver_q * age_n)
        course_sigma = math.degrees(math.sqrt(max(float(g_c @ P @ g_c), 0.0)
                                              + maneuver_q * age_n / speed ** 2))
    else:
        speed_sigma = math.sqrt(max(P[2, 2], 0.0))
        course_sigma = 180.0
    course_sigma = min(math.hypot(course_sigma, UNSEEN_TURN_DEG * math.sqrt(turn_p)), 180.0)

    # anpassningen mäts utan manöverbruset: den ska visa när målet girat
    e, _ = p_fit.residuals_and_jacobian(s)
    eb = e[: p_fit.n_b]
    rms = math.degrees(math.sqrt(float(np.mean(eb * eb))))
    fit = float(np.mean(p_fit.w * e * e))
    span = obs[-1].t - obs[0].t
    rel = range_sigma / max(rng, 1e-6)

    return Solution(
        t=t_now, t_ref=t_ref, state=(x, y, vx, vy), x=tx, y=ty,
        course=course, speed=speed, range_nm=rng,
        bearing=norm360(math.degrees(math.atan2(dx, dy))),
        range_sigma=range_sigma, course_sigma=course_sigma, speed_sigma=speed_sigma,
        quality=Quality.DALIG if fit > MANEUVER_CHI2 or speed > MAX_TARGET_KN
        else quality_from(rel, len(obs), span, course_sigma, speed),
        n_obs=len(obs), span_s=span, own_maneuvered=own_maneuvered(obs),
        rms_residual=rms, fit=fit,
    )


def _bearing_cost(obs: Sequence[BearingObs], sol: Solution) -> float:
    """Viktad kvadratsumma av residualerna (utan antagandena)."""
    p = _Problem(obs, sol.t_ref)
    e, _ = p.residuals_and_jacobian(np.array(sol.state))
    return float(np.sum(p.w * e * e))


def maneuver_statistic(observations: Sequence[BearingObs],
                       full: Solution | None = None) -> float:
    """Brytpunktstest för målmanöver.

    En mjuk gir som rak-kurs-modellen kan följa syns inte i den sammanlagda
    anpassningen (fit), men två raka ben förklarar då bäringarna mycket
    bättre än ett. Returnerar största förbättringen över de prövade
    brytpunkterna; 0 om datan inte räcker. full: färdig lösning på samma
    bäringar räknad med maneuver_q=0, om den redan finns. Testet jämför
    raka ben, så alla lösningar här räknas utan manöverbrus.
    """
    obs = list(observations)[-MAX_OBS:]
    if not obs:
        return 0.0
    obs = [o for o in obs if o.t >= obs[-1].t - MAX_SPAN_S]
    if full is None:
        full = solve(obs, maneuver_q=0.0)
    if full is None:
        return 0.0
    c_full = _bearing_cost(obs, full)
    best = 0.0
    for age in SPLIT_AGES_S:
        cut = obs[-1].t - age
        before = [o for o in obs if o.t < cut]
        after = [o for o in obs if o.t >= cut]
        if len(before) < SPLIT_MIN_BEFORE or len(after) < SPLIT_MIN_AFTER \
                or before[-1].t - before[0].t < SPLIT_MIN_BEFORE_SPAN_S:
            continue
        sa, sb = solve(before, maneuver_q=0.0), solve(after, maneuver_q=0.0)
        if sa is None or sb is None:
            continue
        best = max(best, c_full - _bearing_cost(before, sa) - _bearing_cost(after, sb))
    return best
