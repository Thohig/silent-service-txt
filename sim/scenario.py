"""Startläge, den hemliga ordern och radiomeddelanden från huvudstaben."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

from .crew import CrewMember, Role
from .enemy import DestroyerAI
from .entities import Vessel
from .environment import ArcticProfile, Environment
from .arctic import DriftStation, EnemySub, SubmarineAI
from .fmt import nm
from .ice import IceField, clearance
from .ownship import OwnShip
from .ship import ShipState
from .geo import bearing_to, distance
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
    # (namn, x, y, sigma nm, simtid) – en position huvudstaben meddelar
    waypoint: tuple[str, float, float, float, int] | None = None


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
    # positioner besättningen känner från start: (namn, x, y, sigma nm, simtid)
    known_positions: list[tuple[str, float, float, float, int]] = field(default_factory=list)
    area_name: str = "kvadrat 7"         # operationsområdet, som besättningen säger det
    outcome_text: dict[str, str] = field(default_factory=dict)   # ersätter Game.OUTCOME_TEXT


def _crew() -> dict[Role, CrewMember]:
    return {
        Role.SONAR: CrewMember("Volkov", Role.SONAR, 0.75, rank="Starsjina"),
        Role.NAVIGATOR: CrewMember("Orlov", Role.NAVIGATOR, 0.8, rank="Kaptenlöjtnant"),
        Role.PLOT: CrewMember("Sjtjerbakov", Role.PLOT, 0.7, rank="Löjtnant"),
        Role.ENGINEER: CrewMember("Kuznetsov", Role.ENGINEER, 0.8, rank="Kapten 3:e rang"),
        Role.TORPEDO: CrewMember("Ivanov", Role.TORPEDO, 0.75, rank="Kaptenlöjtnant"),
        Role.OFFICER: CrewMember("Petrov", Role.OFFICER, 0.8, rank="Kaptenlöjtnant"),
        Role.RADIO: CrewMember("Belov", Role.RADIO, 0.7, rank="Starsjina"),
    }


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

    crew = _crew()
    # sambandstillfällen kl 05:00, 06:30 och 08:00
    windows = [(c - start_clock) for c in (5 * 3600, 6 * 3600 + 1800, 8 * 3600)]
    return Scenario(world, crew, SECRET_ORDER, start_clock,
                    radio_windows=windows, radio_messages=list(RADIO_MESSAGES))


ARCTIC_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 24 OKTOBER 1962

1. DRIVSTATIONEN NORD-7 HAR INTE HÖRTS AV
   SEDAN 21 OKTOBER. SENAST KÄND CIRKA
   {dist} SJÖMIL {dir} OM ERT INGÅNGSLÄGE.
2. GÅ UNDER PACKISEN TILL NORD-7. GÅ UPP
   I ÖPPET VATTEN INTILL STATIONEN OCH
   UNDERSÖK.
3. LYSSNA VID VARJE SAMBANDSTILLFÄLLE.
4. FÖRBLI OUPPTÄCKT. AMERIKANSKA UBÅTAR
   KAN FINNAS UNDER ISEN.
5. VAPEN FÅR ENDAST ANVÄNDAS PÅ ORDER FRÅN
   MOSKVA.

SLUT
"""

STATION_NAME = "Nord-7"


def _compass(b: float) -> str:
    return ["NORR", "NORDOST", "ÖSTER", "SYDOST", "SÖDER", "SYDVÄST", "VÄSTER", "NORDVÄST"][
        int(((b % 360) + 22.5) // 45) % 8]


def arctic_scenario(rng: random.Random) -> Scenario:
    start_clock = 2 * 3600
    ice = IceField(random.Random(rng.random()), drift_set=200.0, drift_kn=0.25)
    env = Environment(profile=ArcticProfile(), clock_start=start_clock, ice=ice,
                      background_noise=52.0, current_set=150.0, current_kn=0.1,
                      sunrise=0, sunset=0,                     # polarnatt
                      night_visibility_nm=1.0)
    x, y = 10.0, 3.0
    # starta inte inne i en isköl
    while clearance(ice, x, y, 0.0, 120.0) < 10:
        x += 0.05
    own = OwnShip(ShipState(x=x, y=y, course=0, speed=5, depth=120, max_depth=400))

    # drivstationen: en isflak med en vak intill
    sx, sy = x + rng.uniform(-2.5, 2.5), y + rng.uniform(10.5, 12.5)
    station = DriftStation("NORD7", sx, sy)
    b = rng.uniform(0, 360)
    ice.carve_polynya(sx + 0.3 * math.sin(math.radians(b)), sy + 0.3 * math.cos(math.radians(b)),
                      rng.uniform(0.14, 0.2))

    # amerikansk atomubåt på väg mot samma område
    ub = rng.uniform(40, 140)
    ux, uy = sx + 9 * math.sin(math.radians(ub)), sy + 9 * math.cos(math.radians(ub))
    us = EnemySub("SSN1", ShipState(x=ux, y=uy, course=bearing_to(ux, uy, sx, sy), speed=8,
                                    depth=150, turn_rate=1.5, accel=0.05, max_speed=25,
                                    max_depth=300))
    world = World(own=own, contacts=[station, us], env=env, rng=random.Random(rng.random()),
                  patrol_end=6 * 3600)
    world.ais.append(SubmarineAI(us, random.Random(rng.random()), station))
    world.mission["nuclear_authorized"] = False
    # i ytläge inom en och en halv sjömil kan en landstigningsgrupp gå över isen
    world.mission["goal"] = {"id": station.id, "radius_nm": 1.5, "outcome": "station_reached"}

    # huvudstabens bild: stationens nödsignal kl 02:40, pejlad med ett par kabellängders fel
    t_sig = 40 * 60
    ivx, ivy = ice.drift_velocity()
    px, py = sx + ivx * t_sig + rng.gauss(0, 0.4), sy + ivy * t_sig + rng.gauss(0, 0.4)
    # ordern bygger på en äldre position: stationen har drivit sedan dess
    ox, oy = sx + rng.gauss(0, 1.2), sy + rng.gauss(0, 1.2)
    order_dist = round(distance(x, y, ox, oy))
    order = ARCTIC_ORDER.format(dist=order_dist, dir=_compass(bearing_to(x, y, ox, oy)))
    messages = [
        RadioMessage(f"FRÅN HUVUDSTABEN. NORD-7 SÄNDE KORT NÖDSIGNAL KL 02:40. POSITION CIRKA "
                     f"{nm(px)} SJÖMIL ÖST OCH {nm(py)} SJÖMIL NORR I NORD-3. "
                     "ISEN DRIVER. TA ER DIT OCH GÅ UPP.",
                     waypoint=(STATION_NAME, px, py, 0.6, t_sig)),
        RadioMessage("FRÅN HUVUDSTABEN. AMERIKANSK ATOMUBÅT TROLIGEN PÅ VÄG MOT NORD-7. "
                     "FÖRBLI OUPPTÄCKT. VAPENANVÄNDNING EJ AUKTORISERAD."),
        RadioMessage("FRÅN HUVUDSTABEN. INGEN ÄNDRING. RAPPORTERA NÄR NI NÅTT NORD-7.",
                     {"nuclear_authorized": False}),
    ]
    crew = _crew()
    windows = [(c - start_clock) for c in (3 * 3600, 4 * 3600 + 1800, 6 * 3600)]
    return Scenario(world, crew, order, start_clock,
                    radio_windows=windows, radio_messages=messages,
                    known_positions=[(STATION_NAME, ox, oy, 2.0, 0)],
                    area_name="område Nord-3",
                    outcome_text={
                        "station_reached": "K-114 har gått upp genom isen vid Nord-7. En "
                                           "landstigningsgrupp går ut över isen mot de mörka barackerna.",
                        "patrol_end": "Patrullen är slut utan att K-114 nått Nord-7. "
                                      "Ubåten lämnar område Nord-3 under isen.",
                        "quit": "Kaptenen har avbrutit patrullen. K-114 lämnar område Nord-3 i förtid.",
                        "lost": "K-114 är förlorad under isen med hela besättningen.",
                        "sank": "Den amerikanska ubåten är sänkt under isen. Vad som händer nu "
                                "avgörs inte längre i Nord-3.",
                    })


# --- scenarioregister ----------------------------------------------------------
@dataclass(frozen=True)
class ScenarioDef:
    key: str                                   # namnet för --scenario
    title: str
    summary: str
    build: Callable[[random.Random], Scenario]


SCENARIOS: dict[str, ScenarioDef] = {}


def register(sd: ScenarioDef) -> None:
    SCENARIOS[sd.key] = sd


def build_scenario(key: str, rng: random.Random) -> Scenario:
    if key not in SCENARIOS:
        raise KeyError(f"okänt scenario {key!r}, välj bland: {', '.join(SCENARIOS)}")
    return SCENARIOS[key].build(rng)


register(ScenarioDef(
    "kuba", "Kvadrat 7, oktober 1962",
    "Kubakrisen. Förbli oupptäckt för en amerikansk jagare i karantänlinjen.",
    default_scenario))
register(ScenarioDef(
    "arktis", "Under packisen, oktober 1962",
    "Polarnatt vid 85° nord. Drivstationen Nord-7 har tystnat. Ta er dit under isen, "
    "hitta öppet vatten och gå upp. En amerikansk ubåt är på väg mot samma plats.",
    arctic_scenario))
