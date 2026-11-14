"""Startläge och den hemliga ordern från marinens huvudstab."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .crew import CrewMember, Role
from .ship import ShipState
from .world import Vessel, World

SECRET_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 24 OKTOBER 1962

1. INTA STÄLLNING I OPERATIONSOMRÅDE KVADRAT 7.
2. FÖRBLI OUPPTÄCKT. UNDVIK KONTAKT MED
   AMERIKANSKA ÖRLOGSFARTYG.
3. RAPPORTERA FARTYGSRÖRELSER VID NÄSTA
   SAMBANDSTILLFÄLLE.
4. VAPEN FÅR ENDAST ANVÄNDAS PÅ ORDER FRÅN MOSKVA.

SLUT
"""


@dataclass
class Scenario:
    world: World
    crew: dict[Role, CrewMember]
    secret_order: str
    start_clock: int        # sekunder efter midnatt


def default_scenario(rng: random.Random) -> Scenario:
    own = Vessel("OWN", "submarine",
                 ShipState(x=10.0, y=3.0, course=0, speed=5, depth=100))
    dd = Vessel("DD1", "destroyer",
                ShipState(x=1.0 + rng.uniform(-0.5, 0.5),
                          y=12.0 + rng.uniform(-1.5, 1.5),
                          course=100 + rng.uniform(-10, 10),
                          speed=15 + rng.uniform(-2, 2)))
    world = World(own=own, contacts=[dd])
    crew = {
        Role.SONAR: CrewMember("Volkov", Role.SONAR, 0.75, rank="Starsjina"),
        Role.NAVIGATOR: CrewMember("Orlov", Role.NAVIGATOR, 0.8, rank="Kaptenlöjtnant"),
        Role.PLOT: CrewMember("Sjtjerbakov", Role.PLOT, 0.7, rank="Löjtnant"),
    }
    return Scenario(world, crew, SECRET_ORDER, start_clock=4 * 3600 + 30 * 60)
