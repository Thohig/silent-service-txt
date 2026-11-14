"""Startläge, den hemliga ordern och radiomeddelanden från huvudstaben."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .crew import CrewMember, Role
from .enemy import DestroyerAI
from .entities import Vessel
from .environment import Environment
from .ownship import OwnShip
from .ship import ShipState
from .world import World

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
class RadioMessage:
    text: str
    flags: dict = field(default_factory=dict)


RADIO_MESSAGES = [
    RadioMessage("FRÅN HUVUDSTABEN. AMERIKANSKA STYRKOR UPPRÄTTHÅLLER KARANTÄN. "
                 "FARTYG KAN ANVÄNDA SMÅ SIGNALSJUNKBOMBER FÖR ATT TVINGA UPP UBÅTAR. "
                 "FÖRBLI OUPPTÄCKT. SVARA EJ."),
    RadioMessage("FRÅN HUVUDSTABEN. RAPPORTERA OBSERVERADE FARTYGSRÖRELSER "
                 "VID FÖRSTA MÖJLIGA SAMBANDSTILLFÄLLE."),
    RadioMessage("FRÅN HUVUDSTABEN. INGEN ÄNDRING. VAPENANVÄNDNING EJ AUKTORISERAD.",
                 {"nuclear_authorized": False}),
]


@dataclass
class Scenario:
    world: World
    crew: dict[Role, CrewMember]
    secret_order: str
    start_clock: int                    # sekunder efter midnatt
    radio_windows: list[int] = field(default_factory=list)   # simtid när fönster öppnar
    radio_window_len: int = 20 * 60
    radio_messages: list[RadioMessage] = field(default_factory=list)


def default_scenario(rng: random.Random) -> Scenario:
    start_clock = 4 * 3600 + 30 * 60
    env = Environment(clock_start=start_clock)
    own = OwnShip(ShipState(x=10.0, y=3.0, course=0, speed=5, depth=100, max_depth=400))
    dd = Vessel("DD1", "destroyer",
                ShipState(x=1.0 + rng.uniform(-0.5, 0.5), y=12.0 + rng.uniform(-1.5, 1.5),
                          course=100 + rng.uniform(-10, 10), speed=15 + rng.uniform(-2, 2),
                          turn_rate=2.0, accel=0.3, max_speed=32),
                side="enemy", has_radar=True)
    world = World(own=own, contacts=[dd], env=env, rng=random.Random(rng.random()),
                  patrol_end=int(3.5 * 3600))
    world.ais.append(DestroyerAI(dd, random.Random(rng.random()), area=world.size_nm))
    world.mission["nuclear_authorized"] = False

    crew = {
        Role.SONAR: CrewMember("Volkov", Role.SONAR, 0.75, rank="Starsjina"),
        Role.NAVIGATOR: CrewMember("Orlov", Role.NAVIGATOR, 0.8, rank="Kaptenlöjtnant"),
        Role.PLOT: CrewMember("Sjtjerbakov", Role.PLOT, 0.7, rank="Löjtnant"),
        Role.ENGINEER: CrewMember("Kuznetsov", Role.ENGINEER, 0.8, rank="Kapten 3:e rang"),
        Role.TORPEDO: CrewMember("Ivanov", Role.TORPEDO, 0.75, rank="Kaptenlöjtnant"),
        Role.OFFICER: CrewMember("Petrov", Role.OFFICER, 0.8, rank="Kaptenlöjtnant"),
        Role.RADIO: CrewMember("Belov", Role.RADIO, 0.7, rank="Starsjina"),
    }
    # sambandstillfällen kl 05:00, 06:30 och 08:00
    windows = [(c - start_clock) for c in (5 * 3600, 6 * 3600 + 1800, 8 * 3600)]
    return Scenario(world, crew, SECRET_ORDER, start_clock,
                    radio_windows=windows, radio_messages=list(RADIO_MESSAGES))
