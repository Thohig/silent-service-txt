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
