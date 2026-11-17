"""Solen och månen: läge på himlen och månens fas, ur plats, datum och klocka.

Enkla formler (noggrannhet omkring en grad), tillräckligt för skymning, gryning och
månljus. Ren astronomi utan slump; samma för sanningen och för navigatörens almanacka.

Vinklar i grader. Azimut är bäring från norr, medurs. Höjd över horisonten utan
refraktion (solens överkant syns vid −0,833°).
"""
from __future__ import annotations

import math

J2000 = 2451545.0
SYNODIC_DAYS = 29.530588853


def julian_day(year: int, month: int, day: int, seconds_utc: float = 0.0) -> float:
    """Juliansk dag för ett datum (gregorianskt) och sekunder efter midnatt UTC."""
    if month <= 2:
        year, month = year - 1, month + 12
    a = year // 100
    b = 2 - a + a // 4
    jd0 = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + b - 1524.5
    return jd0 + seconds_utc / 86400.0


def _obliquity(n: float) -> float:
    return math.radians(23.439 - 0.0000004 * n)


def _sun_ecliptic(n: float) -> float:
    """Solens ekliptiska longitud (radianer)."""
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    return math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))


def _moon_ecliptic(n: float) -> tuple[float, float]:
    """Månens ekliptiska longitud och latitud (radianer)."""
    L = 218.316 + 13.176396 * n
    M = math.radians(134.963 + 13.064993 * n)
    F = math.radians(93.272 + 13.229350 * n)
    return math.radians((L + 6.289 * math.sin(M)) % 360), math.radians(5.128 * math.sin(F))


def _equatorial(lam: float, beta: float, eps: float) -> tuple[float, float]:
    """Ekliptiska koordinater till rektascension och deklination (radianer)."""
    ra = math.atan2(math.sin(lam) * math.cos(eps) - math.tan(beta) * math.sin(eps), math.cos(lam))
    dec = math.asin(math.sin(beta) * math.cos(eps) + math.cos(beta) * math.sin(eps) * math.sin(lam))
    return ra, dec


def _horizontal(ra: float, dec: float, lat: float, lon: float, n: float) -> tuple[float, float]:
    """Höjd och azimut (grader) för en punkt på himlen."""
    gmst = (280.46061837 + 360.98564736629 * n) % 360
    ha = math.radians(gmst + lon) - ra
    phi = math.radians(lat)
    alt = math.asin(math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha), math.tan(dec) * math.cos(phi) - math.sin(phi) * math.cos(ha))
    return math.degrees(alt), math.degrees(az) % 360


def sun_position(lat: float, lon: float, jd: float) -> tuple[float, float]:
    """Solens (höjd, azimut) i grader."""
    n = jd - J2000
    ra, dec = _equatorial(_sun_ecliptic(n), 0.0, _obliquity(n))
    return _horizontal(ra, dec, lat, lon, n)


def moon_position(lat: float, lon: float, jd: float) -> tuple[float, float]:
    """Månens (höjd, azimut) i grader (utan parallax, omkring en grad fel)."""
    n = jd - J2000
    lam, beta = _moon_ecliptic(n)
    ra, dec = _equatorial(lam, beta, _obliquity(n))
    return _horizontal(ra, dec, lat, lon, n)


def moon_phase(jd: float) -> tuple[float, bool]:
    """Månens belysta andel (0 ny – 1 full) och om den tilltar."""
    n = jd - J2000
    lam, beta = _moon_ecliptic(n)
    d = (lam - _sun_ecliptic(n)) % (2 * math.pi)
    elong = math.acos(max(-1.0, min(1.0, math.cos(beta) * math.cos(d))))
    return (1 - math.cos(elong)) / 2, d < math.pi
