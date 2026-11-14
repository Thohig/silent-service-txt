"""Enkel bredbandsakustik för passiv sonar.

Signalöverskott:
    SE = SL - TL - (NL_bakgrund ⊕ NL_egen) - DT
där ⊕ är effektsumma av två brusnivåer i dB och DT är operatörens
detektionströskel.
"""
from __future__ import annotations

import math

from .geo import NM_IN_M

BACKGROUND_NOISE_DB = 60.0      # havsbrus, måttlig sjö
ABSORPTION_DB_PER_NM = 0.5      # förenklad absorption, lågfrekvent bredband

# Källnivå: bas + lutning * fart (dB re 1 µPa @ 1 m, förenklat)
_SOURCE = {
    "destroyer": (135.0, 1.25),
    "merchant": (140.0, 1.0),
    "submarine": (100.0, 1.5),
}


def source_level(kind: str, speed: float) -> float:
    base, slope = _SOURCE.get(kind, (130.0, 1.0))
    return base + slope * max(speed, 0.0)


def own_noise(speed: float) -> float:
    """Egenbrus vid sonarns hydrofoner som funktion av egen fart."""
    return 50.0 + 2.5 * max(speed, 0.0)


def transmission_loss(range_nm: float) -> float:
    r_m = max(range_nm * NM_IN_M, 1.0)
    return 20.0 * math.log10(r_m) + ABSORPTION_DB_PER_NM * range_nm


def power_sum(*levels_db: float) -> float:
    """Effektsumma av brusnivåer i dB."""
    return 10.0 * math.log10(sum(10.0 ** (l / 10.0) for l in levels_db))


def total_noise(background: float, own_speed: float) -> float:
    return power_sum(background, own_noise(own_speed))


def signal_excess(sl: float, tl: float, noise: float, dt: float = 0.0) -> float:
    return sl - tl - noise - dt
