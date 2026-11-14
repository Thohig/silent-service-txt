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

    @property
    def rel_range_error(self) -> float:
        return self.range_sigma / max(self.range_nm, 1e-6)


def predicted_bearing(state: Sequence[float], t_ref: int, t: int,
                      own_x: float, own_y: float) -> float:
    x, y, vx, vy = state
    tau = (t - t_ref) / 3600.0
    return norm360(math.degrees(math.atan2(x + vx * tau - own_x, y + vy * tau - own_y)))


def quality_from(rel_range_error: float, n_obs: int, span_s: int) -> Quality:
    if n_obs < MIN_OBS or span_s < MIN_SPAN_S:
        return Quality.DALIG
    if rel_range_error < 0.10:
        return Quality.SAKER
    if rel_range_error < 0.25:
        return Quality.GOD
    if rel_range_error < 0.50:
        return Quality.OSAKER
    return Quality.DALIG


def own_maneuvered(obs: Sequence[BearingObs], threshold_deg: float = 20.0) -> bool:
    if not obs:
        return False
    c0 = obs[0].own_course
    return any(abs(angle_diff(o.own_course, c0)) > threshold_deg for o in obs)


class _Problem:
    def __init__(self, obs: Sequence[BearingObs], t_ref: int):
        self.tau = np.array([(o.t - t_ref) / 3600.0 for o in obs])
        self.ox = np.array([o.own_x for o in obs])
        self.oy = np.array([o.own_y for o in obs])
        self.meas = np.radians([o.bearing for o in obs])
        self.w = 1.0 / np.radians([max(o.sigma, 0.05) for o in obs]) ** 2
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
          own_now: tuple[float, float] | None = None) -> Solution | None:
    """Lös målrörelsen. own_now är egen position vid t_now (för avstånd/bäring)."""
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
    range_sigma = math.sqrt(max(float(g_r @ P @ g_r), 0.0))

    speed = math.hypot(vx, vy)
    course = norm360(math.degrees(math.atan2(vx, vy)))
    if speed > 1e-6:
        g_s = np.array([0, 0, vx / speed, vy / speed])
        g_c = np.array([0, 0, vy / speed ** 2, -vx / speed ** 2])
        speed_sigma = math.sqrt(max(float(g_s @ P @ g_s), 0.0))
        course_sigma = math.degrees(math.sqrt(max(float(g_c @ P @ g_c), 0.0)))
    else:
        speed_sigma = math.sqrt(max(P[2, 2], 0.0))
        course_sigma = 180.0
    course_sigma = min(course_sigma, 180.0)

    e, _ = p.residuals_and_jacobian(s)
    rms = math.degrees(math.sqrt(float(np.mean(e * e))))
    span = obs[-1].t - obs[0].t
    rel = range_sigma / max(rng, 1e-6)

    return Solution(
        t=t_now, t_ref=t_ref, state=(x, y, vx, vy), x=tx, y=ty,
        course=course, speed=speed, range_nm=rng,
        bearing=norm360(math.degrees(math.atan2(dx, dy))),
        range_sigma=range_sigma, course_sigma=course_sigma, speed_sigma=speed_sigma,
        quality=quality_from(rel, len(obs), span),
        n_obs=len(obs), span_s=span, own_maneuvered=own_maneuvered(obs),
        rms_residual=rms,
    )
