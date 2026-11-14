"""Eldledning: ren matematik på kunskap (plottlagets lösning), aldrig sanning."""
from __future__ import annotations

import math

from .geo import norm360


def intercept(rel_x: float, rel_y: float, tvx: float, tvy: float,
              torpedo_speed: float) -> tuple[float, float] | None:
    """Kurs och gångtid (timmar) för att möta ett mål.

    rel_x, rel_y: målets position relativt egen båt (nm)
    tvx, tvy:     målets hastighet (knop)
    Löser |p + v·t| = s·t för minsta positiva t.
    """
    a = tvx * tvx + tvy * tvy - torpedo_speed ** 2
    b = 2.0 * (rel_x * tvx + rel_y * tvy)
    c = rel_x * rel_x + rel_y * rel_y
    if abs(a) < 1e-9:
        if abs(b) < 1e-12:
            return None
        ts = [-c / b]
    else:
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        sq = math.sqrt(disc)
        ts = [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]
    ts = [t for t in ts if t > 0]
    if not ts:
        return None
    t = min(ts)
    ax, ay = rel_x + tvx * t, rel_y + tvy * t
    return norm360(math.degrees(math.atan2(ax, ay))), t


def approach(own_x: float, own_y: float, cx: float, cy: float, vx: float, vy: float,
             own_speed: float, offset_nm: float, lead_h: float = 0.0
             ) -> tuple[float, float, float, float, float] | None:
    """Kurs till ett skjutläge vid sidan av ett måls väg.

    Målet (eller konvojens mitt) är i (cx, cy) och går (vx, vy) knop. Skjutläget
    ligger offset_nm från målets väg på vår sida, där målet är tvärs lead_h
    timmar efter att vi kommit fram. Svar: (kurs, gångtid h, x, y, sida) där
    sida är +1 om skjutläget ligger om styrbord om målets väg, −1 om babord.
    """
    v = math.hypot(vx, vy)
    if v < 0.1 or own_speed <= 0:
        return None
    ux, uy = vx / v, vy / v
    nx, ny = uy, -ux                                 # styrbord om målets kurs
    side = 1.0 if (own_x - cx) * nx + (own_y - cy) * ny >= 0 else -1.0
    px = cx + vx * lead_h + side * offset_nm * nx
    py = cy + vy * lead_h + side * offset_nm * ny
    res = intercept(px - own_x, py - own_y, vx, vy, own_speed)
    if res is None:
        return None
    course, t_h = res
    return course, t_h, px + vx * t_h, py + vy * t_h, side
