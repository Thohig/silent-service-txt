"""Enkel bredbandsakustik för passiv och aktiv sonar.

Passiv:  SE = SL - TL - (NL_bakgrund ⊕ NL_egen) - DT
Aktiv:   SE = SL_ping - 2·TL + TS - NL - DT
där ⊕ är effektsumma av brusnivåer i dB. Utbredningsförlusten (TL)
kommer från miljöns ljudprofil, se environment.py.
"""
from __future__ import annotations

import math

from .environment import ABSORPTION_DB_PER_NM, spherical_loss  # noqa: F401

BACKGROUND_NOISE_DB = 60.0

# Källnivå för främmande fartyg: bas + lutning * fart
_SOURCE = {
    "destroyer": (137.0, 1.25),
    "merchant": (140.0, 1.0),
    "submarine": (110.0, 1.5),
    "patrol": (125.0, 1.5),
    "guardship": (132.0, 1.25),      # sovjetiskt bevakningsfartyg (övningsmål)
    "moored": (100.0, 0.0),          # till ankars: bara hjälpmaskiner
    "transport": (145.0, 1.0),       # stor trupptransport, ångturbiner
    "tanker": (143.0, 1.0),          # tungt lastat tankfartyg
    "ssbn": (130.0, 2.0),            # Polarisubåt i ytläge: vågsvallet och skruven nära ytan
    "fishing": (128.0, 1.5),         # fiskebåt, diesel
    "spytrawler": (133.0, 1.5),      # sovjetisk spaningstrålare: diesel och generatorerna till radion
}

# Målstyrka (ekostyrka) för aktiv sonar
TARGET_STRENGTH = {"destroyer": 25.0, "merchant": 28.0, "submarine": 15.0, "decoy": 15.0,
                   "ssbn": 20.0, "fishing": 15.0, "spytrawler": 17.0, "foxtrot": 16.0,
                   "patrol": 18.0, "guardship": 22.0, "moored": 28.0, "transport": 31.0, "tanker": 32.0}

# Transienter (momentana ljud)
PING_LEVEL_SHIP = 230.0
PING_LEVEL_OWN = 225.0
SPLASH_LEVEL = 140.0
EXPLOSION_REAL = 230.0
EXPLOSION_PRACTICE = 195.0
EXPLOSION_TORPEDO = 235.0
EXPLOSION_NUCLEAR = 270.0
LAUNCH_LEVEL = 150.0
UWT_LEVEL = 180.0
BREAKUP_LEVEL = 165.0
DUD_LEVEL = 150.0             # egen torped slår i ett skrov utan att detonera
ECHO_SOUNDER_LEVEL = 175.0
BLOW_LEVEL = 165.0
BUOY_SPLASH_LEVEL = 135.0     # en sonoboj slår i vattnet
BUOY_PING_LEVEL = 205.0       # aktiv sonoboj
RELOAD_LEVEL = 145.0          # omladdning: torpeden går in i tuben, bakluckan stängs
CREAK_LEVEL = 132.0           # skrovet knakar vid snabb djupändring (kompressionen)
CLATTER_LEVEL = 135.0         # lösa föremål far i durken när båten lutar brant
RELOAD_QUIET_DB = 12.0        # försiktig omladdning (smygmotor, jagade)


# Ett fartyg som ligger still eller glider har bara hjälpmaskinerna igång (generatorer, pumpar):
# under IDLE_KN faller nivån linjärt till IDLE_DB under det framdrivningen ger vid den farten.
IDLE_KN = 3.0
IDLE_DB = 12.0


def source_level(kind: str, speed: float) -> float:
    base, slope = _SOURCE.get(kind, (130.0, 1.0))
    v = max(speed, 0.0)
    level = base + slope * v
    if slope > 0 and v < IDLE_KN:
        level -= IDLE_DB * (1.0 - v / IDLE_KN)
    return level


def own_noise(speed: float) -> float:
    """Flödesbrus vid hydrofonerna som funktion av egen fart."""
    return 50.0 + 2.5 * max(speed, 0.0)


def hull_sonar_self_noise(speed: float) -> float:
    """Egenbrus för ett ytfartygs skrovsonar."""
    return 55.0 + 1.5 * max(speed, 0.0)


ASTERN_TRANSIENT_MIN_KN = 2.0   # omkastning i lägre fart hörs inte särskilt
ASTERN_CAVITATION = 0.5     # propellern går bakåt: kaviterar vid halva farten


def astern_level(speed: float) -> float:
    """Källnivå (dB) när maskinen slår om mot farten: propellern river upp vattnet,
    starkare ju fortare vi gick. 12 kn ≈ en torpedutskjutning, 20 kn mer än nödblåsning."""
    return 120.0 + 2.5 * speed


def cavitation_speed(depth: float, astern: bool = False) -> float:
    """Fart (knop) över vilken propellern kaviterar. Ökar med djupet. Akterut går
    propellern med fel sida mot vattnet och kaviterar vid halva farten."""
    v = 6.0 + max(depth, 0.0) / 25.0
    return v * ASTERN_CAVITATION if astern else v


def transmission_loss(range_nm: float, depth_a: float | None = None,
                      depth_b: float | None = None, env=None) -> float:
    """Utbredningsförlust. Med miljö och djup avgör miljöns ljudprofil,
    annars ren sfärisk spridning."""
    if env is not None and depth_a is not None and depth_b is not None:
        return env.transmission_loss(range_nm, depth_a, depth_b)
    return spherical_loss(range_nm)


def power_sum(*levels_db: float) -> float:
    """Effektsumma av brusnivåer i dB."""
    return 10.0 * math.log10(sum(10.0 ** (l / 10.0) for l in levels_db))


def total_noise(background: float, own_speed: float) -> float:
    return power_sum(background, own_noise(own_speed))


def signal_excess(sl: float, tl: float, noise: float, dt: float = 0.0) -> float:
    return sl - tl - noise - dt


def active_excess(ping_level: float, tl_one_way: float, ts: float,
                  noise: float, dt: float = 0.0) -> float:
    return ping_level - 2.0 * tl_one_way + ts - noise - dt
