"""Det alla scenarier delar: Scenario, uppvärmningen, radiomeddelanden, platserna,
besättningen och registret."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

from ..crew import CrewMember, Role
from ..environment import TidalStream
from ..reports import Quality
from ..seabed import Seabed
from ..world import World


@dataclass
class RadioMessage:
    text: str
    flags: dict = field(default_factory=dict)
    # (namn, x, y, sigma nm, simtid) – en position huvudstaben meddelar
    waypoint: tuple[str, float, float, float, int] | None = None


@dataclass(frozen=True)
class Warmup:
    """Vakten före kaptenen. Game kör så många sekunder med en fast plan (pilot) innan
    spelaren tar befälet: plottet, sonaren och besticket byggs av sensorerna som vanligt,
    så att en kort variant kan börja mitt i läget utan att kunskapen skrivs in för hand.
    pilot(game, t) ger order med game.command(...) som vakthavande gjort före oss.
    Returnerar piloten True lämnar vakten över före `seconds` (som då är ett tak)."""
    seconds: int
    pilot: Callable[[Any, int], None]


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
    chart_seabed: Seabed | None = None   # det gamla sjökortets bild av botten (kunskap)
    tide_table: TidalStream | None = None   # tidvattentabellen besättningen räknar med
    # målet är att lämna området: så här långt utanför kanten räknas som ute (nm)
    escape_margin_nm: float | None = None
    escape_requires_photo: Quality | None = None   # utvägen räknas först med ett så bra foto
    escape_y_below: float | None = None  # ute = söder om denna linje (i stället för kvadratens kant)
    warmup: Warmup | None = None         # kort variant: vakten före kaptenen (se Warmup)
    report_required: bool = False        # ordern kräver en rapport vid sambandstillfället
    # farleden ut enligt sjökortet (beräknade koordinater, i gångriktningen) och vart den leder
    fairway: list[tuple[float, float]] = field(default_factory=list)
    fairway_to: str | None = None
    # övningsprogram (stegen i sim/stations/training.py) och var det görs
    training: tuple[str, ...] = ()
    training_area: str | None = None
    no_dive_in_fjord: bool = False      # ordern förbjuder dykning innanför mynningen
    # torpedrummets laddning: {"tubes": {tub: typ}, "inventory": {typ: antal}}, annars standard
    armament: dict | None = None
    # vad ordern kräver, så som besättningen förstår den (Knowledge.order_tasks):
    # patrull, rapport, anfall, foto, ut, station, övning. Aldrig ur World.goals.
    tasks: tuple[str, ...] = ("patrull",)
    # vad ordern säger om kärnladdningen (NuclearOrderRead.nuclear) och om det är krig
    nuclear_order: str = "order_only"
    at_war: bool = False



# platserna för solen och månen (sim/sky.py): (latitud, longitud); klockan är lokal medeltid
# utom i Kolafjorden (Moskvatid, UTC+3)
KUBA_PLACE = (24.5, -68.0)          # kvadrat 7, nordost om Kuba
GUANTANAMO_PLACE = (19.9, -75.15)
CONVOY_PLACE = (23.0, -72.0)        # kvadrat 12
ARCTIC_PLACE = (85.0, 10.0)
KOLA_PLACE = (69.2, 33.45)          # Poljarnyj


def _place(place: tuple[float, float], utc_offset_h: float | None = None) -> dict:
    lat, lon = place
    return {"lat": lat, "lon": lon,
            "utc_offset_h": lon / 15.0 if utc_offset_h is None else utc_offset_h}


def _compass(b: float) -> str:
    return ["NORR", "NORDOST", "ÖSTER", "SYDOST", "SÖDER", "SYDVÄST", "VÄSTER", "NORDVÄST"][
        int(((b % 360) + 22.5) // 45) % 8]


def _crew() -> dict[Role, CrewMember]:
    return {
        Role.SONAR: CrewMember("Volkov", Role.SONAR, 0.75, rank="Starsjina"),
        Role.NAVIGATOR: CrewMember("Orlov", Role.NAVIGATOR, 0.8, rank="Kaptenlöjtnant"),
        Role.PLOT: CrewMember("Sjtjerbakov", Role.PLOT, 0.7, rank="Löjtnant"),
        Role.ENGINEER: CrewMember("Kuznetsov", Role.ENGINEER, 0.8, rank="Kapten 3:e rang"),
        Role.TORPEDO: CrewMember("Ivanov", Role.TORPEDO, 0.75, rank="Kaptenlöjtnant"),
        Role.OFFICER: CrewMember("Petrov", Role.OFFICER, 0.8, rank="Kaptenlöjtnant"),
        Role.RADIO: CrewMember("Belov", Role.RADIO, 0.7, rank="Starsjina"),
        Role.XO: CrewMember("Sokolov", Role.XO, 0.85, rank="Kapten 3:e rang"),
        Role.TRIM: CrewMember("Zajtsev", Role.TRIM, 0.75, rank="Mitjman"),
    }


@dataclass(frozen=True)
class ScenarioDef:
    key: str                                   # namnet för --scenario
    title: str
    summary: str
    build: Callable[[random.Random], Scenario]
    minutes: int | None = None                 # kort variant: ungefärlig speltid


SCENARIOS: dict[str, ScenarioDef] = {}


def register(sd: ScenarioDef) -> None:
    SCENARIOS[sd.key] = sd


def build_scenario(key: str, rng: random.Random) -> Scenario:
    if key not in SCENARIOS:
        raise KeyError(f"okänt scenario {key!r}, välj bland: {', '.join(SCENARIOS)}")
    return SCENARIOS[key].build(rng)
