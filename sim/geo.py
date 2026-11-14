"""Geometri och vinkelaritmetik.

Konventioner:
- Position i sjömil (nm), x österut, y norrut.
- Kurs och bäring i grader rätt, 0 = norr, medurs.
- Fart i knop. Tid i sekunder.
"""
from __future__ import annotations

import math

NM_IN_M = 1852.0
SECONDS_PER_HOUR = 3600.0


def norm360(angle: float) -> float:
    """Normalisera vinkel till [0, 360)."""
    a = angle % 360.0
    return 0.0 if a == 360.0 else a


def angle_diff(a: float, b: float) -> float:
    """Kortaste signerade vinkel a - b i grader, i intervallet (-180, 180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def bearing_to(x0: float, y0: float, x1: float, y1: float) -> float:
    """Bäring (grader rätt) från punkt 0 till punkt 1."""
    return norm360(math.degrees(math.atan2(x1 - x0, y1 - y0)))


def distance(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.hypot(x1 - x0, y1 - y0)


def velocity(course: float, speed_kn: float) -> tuple[float, float]:
    """Hastighetsvektor i nm per sekund."""
    c = math.radians(course)
    v = speed_kn / SECONDS_PER_HOUR
    return v * math.sin(c), v * math.cos(c)


def fmt_course(angle: float) -> str:
    """Tresiffrig kurs/bäring, t.ex. 045."""
    return f"{round(norm360(angle)) % 360:03d}"


def circular_mean(angles: list[float]) -> float:
    """Medelvärde av vinklar i grader (hanterar 359/001)."""
    sx = sum(math.sin(math.radians(a)) for a in angles)
    cy = sum(math.cos(math.radians(a)) for a in angles)
    return norm360(math.degrees(math.atan2(sx, cy)))
