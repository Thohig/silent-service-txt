"""Startläge, den hemliga ordern och radiomeddelanden från huvudstaben."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable

from .crew import CrewMember, Role
from .enemy import DestroyerAI
from .entities import Vessel
from .environment import ArcticProfile, Environment, TidalStream
from .arctic import DriftStation, EnemySub, SubmarineAI
from .convoy import ConvoyDef, make_convoy, make_escorts
from .fmt import nm
from .ice import IceField, clearance
from .seabed import Seabed, arctic_seabed, kola_seabed, kuba_seabed, strait_seabed
from .ownship import OwnShip
from .reports import Quality
from .ship import ShipState
from .geo import bearing_to, distance, offset_starboard
from .air import AirDef, AirPatrol
from .traffic import Lane, TrafficDef, TrafficGenerator
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


# Civil trafik kring kvadrat 7 (x österut, y norrut, kvadraten 0–20 nm).
KUBA_TRAFFIC = TrafficDef(lanes=(
    Lane("västgående", start=(24.0, 15.0), end=(-4.0, 11.0), per_hour=0.7),
    Lane("östgående", start=(-4.0, 6.0), end=(24.0, 9.0), per_hour=0.7),
    Lane("mot Kuba", start=(8.0, 24.0), end=(12.0, -4.0), per_hour=0.4, speed=(9.0, 12.0),
         soviet=1.0),
), initial=3)


# Ubåtsjaktflyg från Key West (västnordväst om kvadraten).
KUBA_AIR = AirDef()


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
    traffic = TrafficGenerator(KUBA_TRAFFIC, random.Random(rng.random()))
    traffic.populate(world)
    world.spawners.append(traffic)
    world.spawners.append(AirPatrol(KUBA_AIR, random.Random(rng.random()), area=world.size_nm))

    crew = _crew()
    # sambandstillfällen kl 05:00, 06:30 och 08:00
    windows = [(c - start_clock) for c in (5 * 3600, 6 * 3600 + 1800, 8 * 3600)]
    # botten sist, så att den inte flyttar övriga slumpdragningar
    sb_rng = random.Random(rng.random())
    env.seabed = kuba_seabed(sb_rng, (own.state.x, own.state.y), world.size_nm)
    chart = env.seabed.chart_copy(sb_rng, err_nm=0.5)
    return Scenario(world, crew, SECRET_ORDER, start_clock,
                    radio_windows=windows, radio_messages=list(RADIO_MESSAGES),
                    chart_seabed=chart)


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


def arctic_scenario(rng: random.Random, short: bool = False) -> Scenario:
    """Under packisen till Nord-7. short (`arktis-kort`): stationen ligger nära, vakten har
    gått mot den i 20 min, ubåten är närmare och branden kommer snart (arctic_short_scenario)."""
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
    if short:
        sx, sy = x + rng.uniform(-1.0, 1.0), y + rng.uniform(*ARCTIC_SHORT_STATION_NM)
    else:
        sx, sy = x + rng.uniform(-2.5, 2.5), y + rng.uniform(10.5, 12.5)
    station = DriftStation("NORD7", sx, sy)
    b = rng.uniform(0, 360)
    ice.carve_polynya(sx + 0.3 * math.sin(math.radians(b)), sy + 0.3 * math.cos(math.radians(b)),
                      rng.uniform(0.14, 0.2))

    # amerikansk atomubåt på väg mot samma område
    ub = rng.uniform(40, 140)
    ur = ARCTIC_SHORT_SUB_NM if short else 9
    ux, uy = sx + ur * math.sin(math.radians(ub)), sy + ur * math.cos(math.radians(ub))
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
    # brand i turbinrummet någon gång under första timmarna
    world.mission["fire_at"] = rng.randint(40 * 60, 110 * 60)
    crew = _crew()
    windows = [(c - start_clock) for c in (3 * 3600, 4 * 3600 + 1800, 6 * 3600)]
    known = [(STATION_NAME, ox, oy, 2.0, 0)]
    if short:
        r2 = random.Random(rng.random())
        world.mission["fire_at"] = ARCTIC_SHORT_WARM_S + r2.randint(*ARCTIC_SHORT_FIRE_MIN) * 60
        world.patrol_end = ARCTIC_SHORT_WARM_S + ARCTIC_SHORT_LIMIT_S
        windows = []
        # nödsignalen har redan kommit: vakten har stationens pejlade läge
        t0 = 0
        known = [(STATION_NAME, sx + r2.gauss(0, 0.4), sy + r2.gauss(0, 0.4), 0.6, t0)]
        messages = []
    sb_rng = random.Random(rng.random())
    env.seabed = arctic_seabed(sb_rng, world.size_nm)
    chart = env.seabed.chart_copy(sb_rng, err_nm=0.8)
    return Scenario(world, crew, order, start_clock, chart_seabed=chart,
                    radio_windows=windows, radio_messages=messages,
                    known_positions=known,
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


ARCTIC_SHORT_STATION_NM = (3.6, 4.2)    # stationen norrut vid start (2,0–2,6 nm vid överlämnandet)
ARCTIC_SHORT_SUB_NM = 5.5               # amerikanska ubåten så långt från stationen vid start
ARCTIC_SHORT_WARM_S = 20 * 60
ARCTIC_SHORT_LIMIT_S = 35 * 60
ARCTIC_SHORT_FIRE_MIN = (5, 12)         # branden så många minuter efter överlämnandet


def _arctic_watch_pilot(game: Any, t: int) -> None:
    """Vakten: mot Nord-7 i 5 knop på 60 m; isekolodet lodar och iskartan byggs bakom oss."""
    if t == 0:
        game.command("kurs mot Nord-7, djup 60")


def arctic_short_scenario(rng: random.Random) -> Scenario:
    sc = arctic_scenario(rng, short=True)
    sc.warmup = Warmup(ARCTIC_SHORT_WARM_S, _arctic_watch_pilot)
    sc.secret_order += ("\nVAKTJOURNALEN, 02.20: NORD-7 SÄNDE NÖDSIGNAL,\n"
                        "PEJLAD. VAKTHAVANDE HAR GÅTT MOT STATIONEN I\n"
                        "TJUGO MINUTER UNDER ISEN. KAPTENEN TAR BEFÄLET.\n")
    sc.outcome_text["patrol_end"] = ("Tiden är ute. K-114 har inte kommit upp vid Nord-7, och "
                                     "den amerikanska ubåten är redan där.")
    return sc


HUNTED_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 26 OKTOBER 1962

1. LÄMNA KVADRAT 7 OUPPTÄCKT OCH FORTSÄTT
   TILL RESERVOMRÅDET.
2. GÅ INTE TILL YTAN UNDER AMERIKANSK
   BEVAKNING.
3. KARANTÄNFARTYGEN ÄR BUNDNA TILL SINA
   SEKTORER OCH FÖLJER SÄLLAN EFTER MER ÄN
   EN SJÖMIL UTANFÖR KVADRATEN.
4. VAPEN FÅR ENDAST ANVÄNDAS PÅ ORDER FRÅN
   MOSKVA ELLER OM NI ANGRIPS MED SKARPA
   VAPEN.

SLUT
"""

HUNTED_RADIO = [
    RadioMessage("FRÅN HUVUDSTABEN. AMERIKANSKA JAGARE HAR FÄLLT SJUNKBOMBER MOT VÅRA "
                 "UBÅTAR I FLERA KVADRATER. LÄMNA KVADRAT 7. FÖRBLI OUPPTÄCKT."),
    RadioMessage("FRÅN HUVUDSTABEN. INGEN ÄNDRING. KÄRNVAPEN EJ AUKTORISERADE.",
                 {"nuclear_authorized": False}),
]

# Flyget kommer tidigare: jagarna har kallat på det.
HUNTED_AIR = AirDef(first_s=(25 * 60, 45 * 60))


def _bank_edge_x(seabed: Seabed, y: float, size: float) -> tuple[float, bool]:
    """Bankens kant (300-metersdjupet) längs y, och om banken ligger åt väster."""
    west = seabed.depth_at(0.5, y) < seabed.depth_at(size - 0.5, y)
    xs = [i * 0.1 for i in range(int(size * 10) + 1)]
    if not west:
        xs.reverse()
    for x in xs:
        if seabed.depth_at(x, y) > 300:
            return x, west
    return size / 2, west


def hunted_scenario(rng: random.Random, short: bool = False) -> Scenario:
    """Jagade: spelet börjar när jagaren just fått kontakt och en till är på väg.

    short: kort variant (`jagad-kort`): kvadraten 8 nm, DD1 1,5 nm bort i anfallsgång med
    skarpa bomber från start, DD2 spärrar den korta vägen ut över djupt vatten."""
    start_clock = 40 * 60                               # 00:40, mörkt
    env = Environment(clock_start=start_clock)
    size = HUNTED_SHORT_SIZE if short else 20.0
    # botten först: ubåten börjar på djupt vatten några sjömil från bankens kant
    sb_rng = random.Random(rng.random())
    y = size / 2 + rng.uniform(-0.5, 0.5) if short else rng.uniform(4.5, 6.5)
    seabed = kuba_seabed(sb_rng, (size / 2, y), size)
    chart = seabed.chart_copy(sb_rng, err_nm=0.5)
    env.seabed = seabed
    edge, west = _bank_edge_x(seabed, y, size)
    if short:       # nära djupvattensidan: kortaste vägen ut går förbi DD2
        d = rng.uniform(*HUNTED_SHORT_EDGE_NM)
        x = size - d if west else d
    else:
        x = edge + (1.3 if west else -1.3)
    own = OwnShip(ShipState(x=x, y=y, course=rng.uniform(150, 210), speed=6, depth=45,
                            max_depth=400))

    def destroyer(vid: str, bearing: float, r: float, speed: float) -> Vessel:
        dx, dy = x + r * math.sin(math.radians(bearing)), y + r * math.cos(math.radians(bearing))
        return Vessel(vid, "destroyer",
                      ShipState(x=dx, y=dy, course=bearing_to(dx, dy, x, y), speed=speed,
                                turn_rate=2.0, accel=0.3, max_speed=32),
                      side="enemy", has_radar=True)

    if short:
        # DD1 har oss på 1,5 nm och går in för anfall; DD2 spärrar djupvattensidan
        dd1 = destroyer("DD1", rng.uniform(320, 400) % 360, rng.uniform(*HUNTED_SHORT_DD1_NM),
                        DestroyerAI.SPEED_ATTACK)
        deep_side = 90.0 if west else 270.0
        dd2 = destroyer("DD2", deep_side + rng.uniform(-30, 30), rng.uniform(*HUNTED_SHORT_DD2_NM),
                        20)
    else:
        # jagaren som har oss: 2–3 nm norrut, på väg in
        dd1 = destroyer("DD1", rng.uniform(320, 400) % 360, rng.uniform(2.2, 3.0), 15)
        # den andra kommer från söder och spärrar den vägen ut
        dd2 = destroyer("DD2", rng.uniform(150, 210), rng.uniform(7.0, 8.5), 25)
    world = World(own=own, contacts=[dd1, dd2], env=env, rng=random.Random(rng.random()),
                  size_nm=size, patrol_end=HUNTED_SHORT_LIMIT_S if short else 3 * 3600)
    ai1 = DestroyerAI(dd1, random.Random(rng.random()), area=size, escalate_after=3,
                      leash_nm=1.0)
    ai2 = DestroyerAI(dd2, random.Random(rng.random()), area=size, escalate_after=3,
                      leash_nm=1.0)
    if short:
        ai1.roe = ai2.roe = "lethal"
    ai1.partners, ai2.partners = [ai2], [ai1]
    ai1.start_hunt(x + rng.gauss(0, 0.05), y + rng.gauss(0, 0.05), 50.0, 0.08, contact=True)
    ai2.start_hunt(x + rng.gauss(0, 0.3), y + rng.gauss(0, 0.3), 50.0, 0.5)
    world.ais += [ai1, ai2]
    world.mission["nuclear_authorized"] = False
    margin = 1.0
    world.mission["escape"] = {"margin_nm": margin, "outcome": "escaped"}
    traffic = TrafficGenerator(KUBA_TRAFFIC, random.Random(rng.random()))
    traffic.populate(world)
    world.spawners.append(traffic)
    world.spawners.append(AirPatrol(HUNTED_AIR, random.Random(rng.random()), area=size))

    windows = [] if short else [(c - start_clock) for c in (1 * 3600 + 30 * 60, 3 * 3600)]
    order = HUNTED_ORDER
    if short:
        order += ("\nVAKTJOURNALEN, 00.40: JAGAREN HAR FÄLLT SKARPA\n"
                  "SJUNKBOMBER I NÄRHETEN. DEN GÅR IN IGEN.\n"
                  "KAPTENEN TAR BEFÄLET.\n")
    sc = Scenario(world, _crew(), order, start_clock,
                  radio_windows=windows, radio_messages=list(HUNTED_RADIO),
                  chart_seabed=chart, escape_margin_nm=margin,
                  outcome_text={
                      "escaped": "K-114 har brutit kontakten och lämnat kvadrat 7. Bakom er "
                                 "pingar jagarna på tomt vatten.",
                      "patrol_end": "Gryningen kommer och K-114 är fortfarande kvar i kvadrat 7. "
                                    "Uppdraget har misslyckats.",
                      "forced": "K-114 har gått till ytan mellan de amerikanska jagarna. "
                                "Strålkastarna sveper över tornet. Besättningen lever, "
                                "men uppdraget har misslyckats.",
                      "sank": "Båda jagarna är sänkta. Kriget har börjat i kvadrat 7.",
                      "quit": "Kaptenen har avbrutit. K-114 lämnar kvadrat 7 i förtid.",
                  })
    if short:
        sc.outcome_text["patrol_end"] = ("Jagarna har fortfarande K-114 inne i kvadrat 7. "
                                         "Fler fartyg är på väg. Uppdraget har misslyckats.")
        sc.outcome_text["lost"] = ("Sjunkbomberna har krossat skrovet. K-114 är förlorad "
                                   "med hela besättningen.")
    return sc


# Jagade, kort: mindre kvadrat, skarpt från start
HUNTED_SHORT_SIZE = 7.0
HUNTED_SHORT_EDGE_NM = (2.0, 2.5)      # från djupvattensidans kant
HUNTED_SHORT_DD1_NM = (1.4, 1.7)
HUNTED_SHORT_DD2_NM = (3.0, 3.8)       # från oss, på djupvattensidan
HUNTED_SHORT_LIMIT_S = 30 * 60


def hunted_short_scenario(rng: random.Random) -> Scenario:
    return hunted_scenario(rng, short=True)


STRAIT_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 25 OKTOBER 1962

1. GÅ IN MOT INLOPPET TILL GUANTÁNAMOBUKTEN.
   FOTOGRAFERA FARTYGEN VID ANKARPLATSEN
   GENOM PERISKOPET. BILDERNA MÅSTE VARA
   GODA. DAGSLJUS KRÄVS.
2. INLOPPET SKYDDAS AV NÄT MED GRIND, AV
   HYDROFONER PÅ BOTTEN OCH AV PATRULLBÅTAR.
   GRINDEN ÖPPNAS FÖR FARTYG.
3. LÄMNA OMRÅDET SÖDERUT OUPPTÄCKT MED
   BILDERNA.
4. VAPEN FÅR ENDAST ANVÄNDAS PÅ ORDER FRÅN
   MOSKVA.

SLUT
"""

STRAIT_RADIO = [
    RadioMessage("FRÅN HUVUDSTABEN. FLERA AMERIKANSKA FARTYG HAR ANLÄNT TILL GUANTÁNAMO. "
                 "BILDERNA ÄR AV STÖRSTA VIKT. FÖRBLI OUPPTÄCKT."),
    RadioMessage("FRÅN HUVUDSTABEN. INGEN ÄNDRING.", {"nuclear_authorized": False}),
]

HARBOR_PATROL_SPEED = 6.0


def strait_scenario(rng: random.Random, short: bool = False, out: bool = False) -> Scenario:
    """Genom sundet: smyg in mot en flottbas, fotografera ankarplatsen, ta dig ut.

    short (`sundet-in`): 06:20, vi ligger vid väntläget och ett fartyg är på väg in;
    målet är bara fotot (se strait_in_scenario). out (`sundet-ut`): 07:00 innanför nätet,
    ett fartyg på väg ut; ute = vid skärmens inre kant (se strait_out_scenario)."""
    from .harbor import HarborDefense, HydrophoneLine, Net, PatrolBoatAI, hydrophone_points
    # 04:20, gryningen kl 06:10; kort variant efter gryningen
    start_clock = STRAIT_OUT_CLOCK if out else STRAIT_IN_CLOCK if short else 4 * 3600 + 20 * 60
    assert not (short and out)
    size = 14.0
    sb_rng = random.Random(rng.random())
    seabed = strait_seabed(sb_rng, size)
    chart = seabed.chart_copy(sb_rng, err_nm=0.3)
    coast = seabed.features[0]
    cx = coast.channel_x
    shore_c = float(coast.shore(cx))
    tide = TidalStream(flood_set=0.0, peak_kn=rng.uniform(0.9, 1.3),
                       phase_s=rng.uniform(0, 44712))
    env = Environment(clock_start=start_clock, background_noise=64.0, current_set=270.0,
                      current_kn=0.2, seabed=seabed, tide=tide)
    own = OwnShip(ShipState(x=cx + rng.uniform(-3.0, 3.0), y=1.5, course=0, speed=5, depth=100,
                            max_depth=400))
    world = World(own=own, env=env, rng=random.Random(rng.random()), size_nm=size,
                  patrol_end=7 * 3600)

    # skyddet: nät i farledens mynning, hydrofoner en halv sjömil ut, patrullbåtens skärm längre ut
    net_y = shore_c + 0.5
    half = coast.channel_w / 2 + 0.05
    net = Net(y=net_y, x0=cx - half, x1=cx + half, gate_x=cx)
    phones = HydrophoneLine(hydrophone_points(cx - 2.5, cx + 2.5, shore_c - 0.6, 0.5),
                            random.Random(rng.random()))
    xs = [cx - 2.0 + 0.1 * i for i in range(41)]
    top = min(float(coast.shore(x)) for x in xs) - 1.5   # skärm ute på djupt vatten
    box = (cx - 2.0, top - 1.0, cx + 2.0, top)
    pb = Vessel("PB1", "patrol",
                ShipState(x=rng.uniform(box[0], box[2]), y=rng.uniform(box[1], box[3]),
                          course=rng.uniform(0, 360), speed=HARBOR_PATROL_SPEED, turn_rate=4.0,
                          accel=0.5, max_speed=24),
                side="enemy", has_radar=True)
    world.contacts.append(pb)
    boat = PatrolBoatAI(pb, random.Random(rng.random()), area=size,
                        patrol_speed=HARBOR_PATROL_SPEED, box=box, leash_nm=0.8,
                        gate=(cx, net_y))
    world.ais.append(boat)
    harbor = HarborDefense(hydrophones=phones, net=net, boats=[boat])
    world.spawners.append(harbor)

    # fartygen vid ankarplatsen
    ax, ay = coast.bay_x + rng.uniform(-0.6, 0.6), coast.bay_y + rng.uniform(-0.2, 0.3)
    n_ships = rng.randint(3, 5)
    placed = 0
    for _ in range(60):
        if placed >= n_ships:
            break
        mx, my = ax + rng.uniform(-1.0, 1.0), ay + rng.uniform(-0.5, 0.5)
        if seabed.depth_at(mx, my) < 12:
            continue
        placed += 1
        world.contacts.append(Vessel(f"M{placed}", "moored",
                                     ShipState(x=mx, y=my, course=rng.uniform(0, 360), speed=0),
                                     side="enemy", has_radar=False))

    # hamntrafik genom grinden
    gate_in = ((cx, net_y - 0.8), (cx, net_y - 0.15), (cx, net_y + 0.3))
    lanes = (Lane("in", start=(cx, -2.0), end=(cx, coast.bay_y - 0.2), per_hour=0.6,
                  speed=(6.0, 7.5), moor=True, via=gate_in),    # lotsfart in mot hamnen
             Lane("ut", start=(cx, coast.bay_y - 0.4), end=(cx, -3.0), per_hour=0.6,
                  speed=(6.0, 8.0), via=tuple(reversed(gate_in))))
    traffic = TrafficGenerator(TrafficDef(lanes=lanes, initial=1, width_nm=0.03),
                               random.Random(rng.random()))
    traffic.populate(world)
    traffic.next_t[0] = rng.randint(45 * 60, 75 * 60)   # ett fartyg in genom grinden efter gryningen
    world.spawners.append(traffic)

    world.mission["nuclear_authorized"] = False
    margin = 0.5
    world.mission["escape"] = {"margin_nm": margin, "outcome": "recon_done",
                               "requires_photo": int(Quality.GOD)}
    if short:
        r2 = random.Random(rng.random())
        # vid väntläget: ut längs farleden och lite åt sidan, på smygmotor
        side = r2.choice((-1.0, 1.0))
        own.state.x, own.state.y = cx + side * 0.35, net_y - 1.4 - r2.uniform(0.1, 0.3)
        own.state.depth = own.state.ordered_depth = 30.0
        own.state.speed = own.state.ordered_speed = 2.0
        # fartyget in: framme vid grinden ungefär 1,5 nm efter vakten
        y0, y1 = lanes[0].start[1], lanes[0].end[1]
        gy = net_y - r2.uniform(*STRAIT_IN_SHIP_NM)
        traffic._spawn(world, lanes[0], (gy - y0) / (y1 - y0))
        traffic.next_t[0] = 10**9                         # inga fler in under spelet
        del world.mission["escape"]
        world.mission["photo"] = {"quality": int(Quality.GOD), "outcome": "photo_taken"}
        world.patrol_end = STRAIT_IN_WARM_S + STRAIT_IN_LIMIT_S
    if out:
        r2 = random.Random(rng.random())
        # innanför nätet, nära nog ankarplatsen för en god bild, på periskopdjup
        # vid sidan av farleden: fartyget ut går förbi, inte rakt över oss
        own.state.x = cx + r2.choice((-1.0, 1.0)) * STRAIT_OUT_SIDE_NM
        own.state.y = net_y + r2.uniform(*STRAIT_OUT_INSIDE_NM)
        own.state.depth = own.state.ordered_depth = 16.0
        own.state.speed = own.state.ordered_speed = 2.0
        own.state.course = own.state.ordered_course = 180.0
        # fartyget ut: passerar oss några minuter efter överlämnandet
        y0, y1 = lanes[1].start[1], lanes[1].end[1]
        gy = min(own.state.y + r2.uniform(*STRAIT_OUT_SHIP_BEHIND_NM), y0 - 0.05)
        traffic._spawn(world, lanes[1], (gy - y0) / (y1 - y0))
        traffic.next_t = [10**9, 10**9]
        # ute: förbi nätet och hydrofonerna, och ingen har oss
        world.mission["escape"] = {"margin_nm": margin, "outcome": "recon_done",
                                   "requires_photo": int(Quality.GOD),
                                   "y_below": net_y - STRAIT_OUT_LINE_NM}
        world.patrol_end = STRAIT_OUT_WARM_S + STRAIT_OUT_LIMIT_S
    windows = [(c - start_clock) for c in (6 * 3600 + 30 * 60, 8 * 3600) if c > start_clock + 3600]
    known = [("Ankarplatsen", ax + rng.gauss(0, 0.2), ay + rng.gauss(0, 0.2), 0.4, 0),
             ("Nätet", cx + rng.gauss(0, 0.05), net_y + rng.gauss(0, 0.15), 0.2, 0)]
    return Scenario(world, _crew(), STRAIT_ORDER, start_clock,
                    radio_windows=windows, radio_messages=list(STRAIT_RADIO),
                    known_positions=known, chart_seabed=chart,
                    tide_table=tide.table_copy(random.Random(rng.random())),
                    area_name="inloppet", escape_margin_nm=None if short else margin,
                    escape_requires_photo=None if short else Quality.GOD,
                    outcome_text={
                        "recon_done": "K-114 har lämnat inloppet med bilderna av ankarplatsen. "
                                      "Filmen framkallas ombord; i Moskva väntar man på dem.",
                        "patrol_end": "Tiden är ute. K-114 lämnar Guantánamo utan de bilder "
                                      "huvudstaben ville ha.",
                        "forced": "K-114 har gått till ytan utanför den amerikanska flottbasen. "
                                  "Besättningen lever, men uppdraget har misslyckats.",
                        "sank": "Fartygen i Guantánamobukten är sänkta. Kriget har börjat.",
                        "quit": "Kaptenen har avbrutit. K-114 lämnar inloppet i förtid.",
                        "lost": "K-114 är förlorad utanför Guantánamo med hela besättningen.",
                    })


STRAIT_IN_CLOCK = 6 * 3600 + 20 * 60      # efter gryningen: fotot kräver dagsljus
STRAIT_IN_WARM_S = 10 * 60
STRAIT_IN_LIMIT_S = 35 * 60
STRAIT_IN_SHIP_NM = (3.0, 3.2)             # fartyget in så långt från nätet vid start


def _strait_watch_pilot(game: Any, t: int) -> None:
    """Vakten: smygmotor och väntläget, så att sonar och plott får fartyget som kommer in."""
    if t == 0:
        game.command("smygmotor, väntläget")


def strait_in_scenario(rng: random.Random) -> Scenario:
    """Genom sundet, kort: väntläget, ett fartyg på väg in mot grinden, fotot är målet."""
    sc = strait_scenario(rng, short=True)
    sc.warmup = Warmup(STRAIT_IN_WARM_S, _strait_watch_pilot)
    sc.secret_order = STRAIT_ORDER.replace(
        "3. LÄMNA OMRÅDET SÖDERUT OUPPTÄCKT MED\n   BILDERNA.",
        "3. BILDERNA ÄR ALLT. VÄGEN UT ÄR EN\n   SENARE FRÅGA.") + (
        "\nVAKTJOURNALEN, 06.30: VI LIGGER I VÄNTLÄGET\n"
        "UTANFÖR NÄTET. ETT FARTYG ÄR PÅ VÄG IN MOT\n"
        "GRINDEN. KAPTENEN TAR BEFÄLET.\n")
    sc.outcome_text.update({
        "photo_taken": "Bilderna av ankarplatsen är tagna. K-114 ligger innanför nätet i "
                       "Guantánamobukten med filmen ombord.",
        "patrol_end": "Fartyget har passerat och grinden är stängd. K-114 har inte kommit nära "
                      "nog för bilderna.",
    })
    return sc


STRAIT_OUT_CLOCK = 7 * 3600                # dagsljus för bilden under vakten
STRAIT_OUT_WARM_S = 4 * 60
STRAIT_OUT_LIMIT_S = 30 * 60
STRAIT_OUT_INSIDE_NM = (1.0, 1.2)          # vi startar så långt innanför nätet
STRAIT_OUT_LINE_NM = 1.0                  # ute: så långt söder om nätet (hydrofonerna 0,5–0,6)
STRAIT_OUT_SIDE_NM = 0.2                  # vid sidan av farledens mitt
STRAIT_OUT_SHIP_BEHIND_NM = (0.9, 1.2)     # fartyget ut startar så långt bakom oss


def _strait_out_pilot(game: Any, t: int) -> None:
    """Vakten: bilden av ankarplatsen, sedan ned på 20 m (bukten är grund) och vänta."""
    if t == 5:
        game.command("foto")
    elif t == 60:
        game.command("djup 20, smygmotor, fart 1")


def strait_out_scenario(rng: random.Random) -> Scenario:
    """Genom sundet, ut: filmen är tagen innanför nätet; ta er ut bakom ett fartyg."""
    sc = strait_scenario(rng, out=True)
    sc.warmup = Warmup(STRAIT_OUT_WARM_S, _strait_out_pilot)
    sc.escape_y_below = sc.world.mission["escape"]["y_below"]
    sc.secret_order += ("\nVAKTJOURNALEN, 07.04: BILDERNA AV ANKARPLATSEN\n"
                        "ÄR TAGNA. VI LIGGER INNANFÖR NÄTET. ETT FARTYG\n"
                        "ÄR PÅ VÄG UT MOT GRINDEN. KAPTENEN TAR BEFÄLET.\n")
    sc.outcome_text.update({
        "recon_done": "K-114 har tagit sig ut förbi nätet och hydrofonerna med bilderna av "
                      "ankarplatsen. "
                      "Filmen framkallas ombord; i Moskva väntar man på dem.",
        "patrol_end": "Tiden är ute. K-114 är kvar i inloppet med filmen, och fler fartyg "
                      "letar efter henne.",
    })
    return sc


CONVOY_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 28 OKTOBER 1962

1. KARANTÄNLINJEN HAR BRUTITS. AMERIKANSKA
   STYRKOR FÖRBEREDER LANDSTIGNING PÅ KUBA.
2. EN KONVOJ MED TRUPPTRANSPORTER OCH
   EN TANKER UNDER ESKORT ÄR RAPPORTERAD
   CIRKA {dist} SJÖMIL {dir} OM ER,
   KURS CIRKA {course}. DEN SICKSACKAR.
3. ANFALL KONVOJEN MED KONVENTIONELLA
   TORPEDER. SÄNK MINST ETT FARTYG.
   BRYT SEDAN KONTAKTEN.
4. KÄRNVAPEN FÅR INTE ANVÄNDAS.
   NEUTRAL SJÖFART FÅR INTE ANGRIPAS.

SLUT
"""

CONVOY_RADIO = [
    RadioMessage("FRÅN HUVUDSTABEN. KONVOJEN HAR SETTS AV SPANINGSFLYG. INGEN ÄNDRING I ORDERN."),
    RadioMessage("FRÅN HUVUDSTABEN. KÄRNVAPEN FÅR INTE ANVÄNDAS.", {"nuclear_authorized": False}),
]


def convoy_scenario(rng: random.Random, run_in_nm: tuple[float, float] = (16.0, 20.0),
                    side_nm: tuple[float, float] = (1.5, 5.0)) -> Scenario:
    """Konvojen: krig, en eskorterad konvoj sicksackar förbi; sänk ett fartyg och kom undan."""
    start_clock = 6 * 3600 + 30 * 60                   # 06:30, just efter gryningen
    size = 20.0
    env = Environment(clock_start=start_clock)
    ox, oy = size / 2, rng.uniform(5.0, 8.0)
    own = OwnShip(ShipState(x=ox, y=oy, course=0, speed=4, depth=60, max_depth=400))
    world = World(own=own, env=env, rng=random.Random(rng.random()), size_nm=size,
                  patrol_end=4 * 3600)
    # konvojen kommer från nordnordost; dess väg passerar oss på 1,5–5 nm
    base = rng.uniform(190.0, 230.0)
    ux, uy = math.sin(math.radians(base)), math.cos(math.radians(base))
    nx, ny = uy, -ux
    side = rng.choice((-1.0, 1.0)) * rng.uniform(*side_nm)
    run_in = rng.uniform(*run_in_nm)
    cx, cy = ox + side * nx - run_in * ux, oy + side * ny - run_in * uy
    convoy = make_convoy(world, ConvoyDef(start=(cx, cy), base_course=base),
                         random.Random(rng.random()))
    make_escorts(world, convoy, random.Random(rng.random()))
    world.mission["nuclear_authorized"] = False
    world.mission["strike"] = {"targets": [v.id for v in convoy.vessels], "clear_s": 600,
                               "outcome": "convoy_attacked", "miss_nm": 8.0,
                               "miss_outcome": "convoy_missed"}
    traffic = TrafficGenerator(KUBA_TRAFFIC, random.Random(rng.random()))
    traffic.populate(world)
    world.spawners.append(traffic)
    world.spawners.append(AirPatrol(KUBA_AIR, random.Random(rng.random()), area=size))

    # huvudstabens rapport: läget med några sjömils fel, kursen avrundad
    rx, ry = cx + rng.gauss(0, 2.0), cy + rng.gauss(0, 2.0)
    order = CONVOY_ORDER.format(dist=round(distance(ox, oy, rx, ry)),
                                dir=_compass(bearing_to(ox, oy, rx, ry)),
                                course=f"{int(round(base / 10.0) * 10) % 360:03d}")
    windows = [(c - start_clock) for c in (7 * 3600 + 30 * 60, 9 * 3600)]
    sb_rng = random.Random(rng.random())
    env.seabed = kuba_seabed(sb_rng, (ox, oy), size)
    chart = env.seabed.chart_copy(sb_rng, err_nm=0.5)
    return Scenario(world, _crew(), order, start_clock,
                    radio_windows=windows, radio_messages=list(CONVOY_RADIO),
                    chart_seabed=chart, area_name="kvadrat 12",
                    outcome_text={
                        "convoy_attacked": "K-114 har sänkt fartyg ur konvojen och brutit kontakten. "
                                           "Bakom er brinner det på horisonten.",
                        "convoy_missed": "Konvojen har passerat. K-114 kom aldrig till skott. "
                                         "Trupperna når Kuba.",
                        "patrol_end": "Tiden är ute. Konvojen är borta och K-114 har inte "
                                      "fullgjort ordern.",
                        "sank": "Hela konvojen och dess eskort är sänkta. Kriget till sjöss har "
                                "börjat på allvar.",
                        "forced": "K-114 har tvingats till ytan av eskortjagarna. Besättningen "
                                  "tas till fånga.",
                        "neutral_sunk": "K-114 har sänkt ett neutralt fartyg. Huvudstaben kallar "
                                        "hem befälhavaren för att stå till svars.",
                        "lost": "K-114 är förlorad norr om Kuba med hela besättningen.",
                        "quit": "Kaptenen har avbrutit. K-114 lämnar kvadrat 12.",
                    })


# --- korta varianter ------------------------------------------------------------
CONVOY_SHORT_WARM_S = 35 * 60          # vakten före kaptenen: 06:30–07:05
CONVOY_SHORT_LIMIT_S = 45 * 60         # sedan så här länge innan tiden är ute
CONVOY_SHORT_LOOK_S = 240              # vakten tittar i periskopet så här ofta


def _convoy_watch_pilot(game: Any, t: int) -> None:
    """Vakten före kaptenen: periskopdjup i 3 knop, ett svep var 4:e minut, inget anfall."""
    if t == 0:
        game.command("periskopdjup, fart 3")
    elif t % CONVOY_SHORT_LOOK_S == CONVOY_SHORT_LOOK_S // 2 \
            and game.world.own.state.depth <= 18:
        game.command("periskop")


def convoy_short_scenario(rng: random.Random) -> Scenario:
    """Konvojen, kort: vakten har följt konvojen i 35 minuter och plottet har den.
    Kaptenen tar över med konvojen 5–9 nm bort och eskorten ovetande."""
    sc = convoy_scenario(rng, run_in_nm=(13.0, 15.0))
    sc.warmup = Warmup(CONVOY_SHORT_WARM_S, _convoy_watch_pilot)
    sc.world.patrol_end = CONVOY_SHORT_WARM_S + CONVOY_SHORT_LIMIT_S
    sc.secret_order += ("\nVAKTJOURNALEN, 07.05: VAKTHAVANDE HAR GÅTT PÅ\n"
                        "PERISKOPDJUP SEDAN 06.30 OCH FÖLJT KONVOJEN.\n"
                        "KAPTENEN TAR BEFÄLET.\n")
    return sc


COUNTER_MAX_WARM_S = 15 * 60          # vakten lämnar över senast så här långt in
COUNTER_LIMIT_S = 30 * 60             # efter överlämnandet
COUNTER_LOOK_S = 60                   # periskoptitt så här ofta före salvan
COUNTER_RUN_IN_NM = (1.0, 2.0)        # konvojens ledpunkt så långt före tvärs vid start
COUNTER_SIDE_NM = (1.8, 2.4)          # vi ligger så långt vid sidan av baskursen
COUNTER_LEASH_NM = 6.0                # eskortens koppel från konvojen (annars 4)
COUNTER_WAKE_SIGMA_NM = 0.1          # eskortens datum ur torpedbanorna
COUNTER_FIRE_NM = 2.5                 # vakten skjuter på ett stort fartyg så här nära
COUNTER_MIN_SPAN_S = 60               # med minst så lång plottning sedan målets senaste gir
COUNTER_LOOK_FRESH_S = 60             # och en periskoptitt (kurs och fart) så här färsk
COUNTER_MAX_KN = 20.0                 # och en rimlig fart (snabbare: plottet har blandat ihop)
COUNTER_HANDOVER_S = 45               # kaptenen tar över så här långt före beräknad träff


class _CounterattackWatch:
    """Vakten före kaptenen i Motanfallet: periskopdjup, korta svep, och salvan mot det
    första stora fartyget inom COUNTER_FIRE_NM med en lösning minst osäker. Kaptenen tar
    befälet när torpedrummets gångtid säger att torpederna är framme om ~45 s.
    Allt går via order och besättningens kunskap; ingen torped läggs in i världen."""

    def __init__(self) -> None:
        self.handover_t: int | None = None

    def __call__(self, game: Any, t: int) -> bool:
        from .stations.officer import is_big_ship
        from .stations.torpedo_room import TorpedoRoom
        if self.handover_t is not None:
            if t >= self.handover_t:
                game.world.patrol_end = game.now + COUNTER_LIMIT_S
                self._wakes_seen(game.world)
                return True
            return False
        if t == 0:
            game.command("periskopdjup, fart 3")
            return False
        if t >= COUNTER_MAX_WARM_S - 1:
            game.world.patrol_end = game.now + COUNTER_LIMIT_S
            return True
        own = game.world.own.state
        if t % COUNTER_LOOK_S == 0 and own.depth <= 18:
            game.command("periskop")
        torp = game.station(TorpedoRoom)
        best = None
        for tr in game.knowledge.tracks.values():
            if not tr.held or not is_big_ship(tr):
                continue
            _, sol = torp._solution_for(tr.designation)
            looked = any(o.course_obs is not None and o.t >= tr.tma_from_t
                         and t - o.t <= COUNTER_LOOK_FRESH_S for o in tr.observations)
            if sol is None or sol.quality < Quality.GOD or sol.span_s < COUNTER_MIN_SPAN_S \
                    or not looked or sol.speed > COUNTER_MAX_KN or sol.range_nm > COUNTER_FIRE_NM:
                continue
            aim = torp._aim(sol, "53-61")
            if aim is None:
                continue
            if best is None or aim[1] < best[1]:
                best = (tr.designation, aim[1])
        if best is None:
            return False
        game.command(f"salva {best[0]}")
        game.command(f"salva {best[0]}")       # torpedrummet frågar en gång om målet
        if game.world.mission.get("hostile_act"):
            self.handover_t = t + max(0, int(best[1]) - COUNTER_HANDOVER_S)
        return False


    @staticmethod
    def _wakes_seen(world: Any) -> None:
        """Startläget (sanning): utkiken på närmaste eskort har sett torpedbanorna i
        dagsljuset och följer dem tillbaka mot avfyringsplatsen."""
        from .convoy import EscortAI
        escorts = [a for a in world.ais if isinstance(a, EscortAI) and not a.vessel.sunk]
        if not escorts or any(world._hunting_us(a) for a in escorts):
            return
        ai = min(escorts, key=lambda a: world.true_range(a.vessel))
        o = world.own.state
        ai.start_hunt(o.x + ai.rng.gauss(0, COUNTER_WAKE_SIGMA_NM),
                      o.y + ai.rng.gauss(0, COUNTER_WAKE_SIGMA_NM), 30.0,
                      COUNTER_WAKE_SIGMA_NM, t=world.time, contact=True)


def convoy_counter_scenario(rng: random.Random) -> Scenario:
    """Motanfallet: vakten har skjutit en salva mot konvojen; torpederna är framme om
    en knapp minut och eskorten vänder mot oss."""
    sc = convoy_scenario(rng, run_in_nm=COUNTER_RUN_IN_NM, side_nm=COUNTER_SIDE_NM)
    sc.warmup = Warmup(COUNTER_MAX_WARM_S, _CounterattackWatch())
    from .convoy import EscortAI
    for ai in sc.world.ais:
        if isinstance(ai, EscortAI):        # anfallen konvoj: eskorten följer längre efter
            ai.leash_nm = COUNTER_LEASH_NM
    sc.world.patrol_end = COUNTER_MAX_WARM_S + COUNTER_LIMIT_S
    sc.secret_order += ("\nVAKTJOURNALEN: VAKTHAVANDE HAR FÖLJT KONVOJEN PÅ\n"
                        "PERISKOPDJUP OCH SKJUTIT EN SALVA. TORPEDERNA\n"
                        "ÄR PÅ VÄG. KAPTENEN TAR BEFÄLET.\n")
    sc.outcome_text["convoy_missed"] = ("Salvan missade och konvojen har passerat. Trupperna "
                                        "når Kuba.")
    sc.outcome_text["patrol_end"] = ("Tiden är ute. Eskorten har fortfarande K-114 och "
                                     "konvojen är borta.")
    return sc


KUBA_SHORT_WARM_S = 15 * 60            # vakten före kaptenen: 04:30–04:45
KUBA_SHORT_WINDOW_IN_S = 5 * 60        # sambandstillfället öppnar så här långt efter överlämnandet
KUBA_SHORT_WINDOW_S = 15 * 60
KUBA_SHORT_AFTER_S = 10 * 60           # efter fönstret: så länge att bryta kontakten
KUBA_SHORT_DD_NM = (3.0, 4.0)
KUBA_SHORT_CONTACT_SIGMA_NM = 0.5      # jagaren "har oss" bara med ett så skarpt datum
KUBA_SHORT_TURN_S = 7 * 60             # vakten girar för plottets skull


def _kuba_watch_pilot(game: Any, t: int) -> None:
    """Vakten: smygmotor på 100 m och en gir efter sju minuter, så att plottet får avstånd."""
    if t == 0:
        game.command("smygmotor, fart 3")
    elif t == KUBA_SHORT_TURN_S:
        game.command(f"kurs {int(game.world.own.state.course + 70) % 360:03d}")


def kuba_short_scenario(rng: random.Random) -> Scenario:
    """Kvadrat 7, kort: jagaren patrullerar 3–4 nm bort, vakten har plottat den i en kvart.
    Sambandstillfället öppnar fem minuter efter överlämnandet; rapporten ska sändas och
    ingen får ha oss när fönstret stänger."""
    sc = default_scenario(rng)
    w = sc.world
    r2 = random.Random(rng.random())
    o = w.own.state
    dd = next(v for v in w.contacts if v.id == "DD1")
    b, r = r2.uniform(0, 360), r2.uniform(*KUBA_SHORT_DD_NM)
    dd.state.x = o.x + r * math.sin(math.radians(b))
    dd.state.y = o.y + r * math.cos(math.radians(b))
    dd.state.course = dd.state.ordered_course = (b + 90 + r2.uniform(-40, 40)) % 360
    w0 = KUBA_SHORT_WARM_S + KUBA_SHORT_WINDOW_IN_S
    air = AirDef(first_s=(KUBA_SHORT_WARM_S + 5 * 60, KUBA_SHORT_WARM_S + 10 * 60))
    w.spawners = [sp for sp in w.spawners if not isinstance(sp, AirPatrol)]
    w.spawners.append(AirPatrol(air, random.Random(r2.random()), area=w.size_nm))
    sc.radio_windows = [w0]
    sc.radio_window_len = KUBA_SHORT_WINDOW_S
    sc.report_required = True
    w.mission["report"] = {"from": w0, "to": w0 + KUBA_SHORT_WINDOW_S, "outcome": "reported",
                           "miss_outcome": "report_missed",
                           "contact_sigma_nm": KUBA_SHORT_CONTACT_SIGMA_NM}
    w.patrol_end = w0 + KUBA_SHORT_WINDOW_S + KUBA_SHORT_AFTER_S
    sc.warmup = Warmup(KUBA_SHORT_WARM_S, _kuba_watch_pilot)
    open_at = sc.start_clock + w0
    close_at = open_at + KUBA_SHORT_WINDOW_S
    hm = lambda c: f"{c // 3600:02d}.{c % 3600 // 60:02d}"
    sc.secret_order += (f"\nVAKTJOURNALEN, {hm(sc.start_clock + KUBA_SHORT_WARM_S)}: EN JAGARE\n"
                        "PATRULLERAR NÄRA. VAKTHAVANDE HAR GÅTT PÅ\n"
                        "SMYGMOTOR OCH PLOTTAT DEN. KAPTENEN TAR BEFÄLET.\n"
                        f"RAPPORTEN SKA SÄNDAS VID SAMBANDSTILLFÄLLET\n"
                        f"{hm(open_at)}–{hm(close_at)}.\n")
    sc.outcome_text.update({
        "reported": "Rapporten är sänd och kvitterad, och jagaren söker på fel ställe. "
                    "Huvudstaben vet nu var de amerikanska fartygen går.",
        "report_missed": "Sambandstillfället stängde utan rapport från K-114. Huvudstaben "
                         "vet inte var de amerikanska fartygen går.",
        "patrol_end": "Rapporten gick fram, men jagaren har fortfarande K-114. Kvadrat 7 "
                      "är förlorad som spaningsområde.",
    })
    return sc


# --- scenarioregister ----------------------------------------------------------
TRAINING_ORDER = """\
ORDER — ENDAST FÖR BEFÄLHAVAREN
FRÅN: STABEN, NORRA FLOTTAN, SEVEROMORSK
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 8 OKTOBER 1962

1. LÄMNA POLJARNYJ KL 10.00 OCH GÅ UT
   GENOM KOLAFJORDEN I YTLÄGE. HÅLL
   STYRBORDS SIDA AV FARLEDEN. RÄKNA
   MED TRAFIK I FJORDEN.
2. DYKNING ÄR TILLÅTEN FÖRST UTANFÖR
   MYNNINGEN.
3. GÅ TILL ÖVNINGSOMRÅDET NORR OM
   MYNNINGEN. GENOMFÖR PROGRAMMET:
   DYKNING, PERISKOPSVEP, FIX, DJUP 100,
   PROVDJUP 300 METER, SMYGMOTOR,
   UPPSTIGNING. ANMÄL NÄR DET ÄR KLART.
4. INGA SKARPA VAPEN.

SLUT
"""

TRAINING_CLOCK = 10 * 3600
TRAINING_SIZE = 16.0
TRAINING_AREA = "Övningsområdet"
TRAINING_AREA_OUT_NM = 4.5          # övningsområdet så långt norr om mynningen
TRAINING_STEPS = ("dyk", "svep", "fix", "framme", "djup100", "provdjup", "smyg", "pd", "upp")
TRAINING_AREA_SIDE_NM = (1.5, 2.5)  # övningsområdet så långt vid sidan av leden
TRAINING_KEEP_RIGHT_NM = 0.15       # fartygen håller så här långt till styrbord om farledens mitt
TRAINING_KN = 10.0                  # fart ut genom fjorden
TRAINING_START_Y = 1.2              # vi lägger ut från Poljarnyj här (nm norr om kortets kant)


def training_scenario(rng: random.Random) -> Scenario:
    """Övning: ut från Poljarnyj genom Kolafjorden i ytläge, dyk utanför mynningen."""
    size = TRAINING_SIZE
    sb_rng = random.Random(rng.random())
    seabed = kola_seabed(sb_rng, size)
    chart = seabed.chart_copy(sb_rng, err_nm=0.2)
    fj, cfj = seabed.features[0], chart.features[0]
    path = list(fj.path)
    mouth_y = fj.shore_y
    tide = TidalStream(flood_set=190.0, peak_kn=rng.uniform(0.8, 1.2),
                       phase_s=rng.uniform(0, 44712))
    env = Environment(clock_start=TRAINING_CLOCK, background_noise=62.0, current_set=270.0,
                      current_kn=0.1, seabed=seabed, tide=tide,
                      sunrise=8 * 3600, sunset=16 * 3600 + 40 * 60)
    # ut från kajen: på farledens styrbordssida, kurs längs första benet, i ytläge
    (ax, ay), (bx, by) = path[0], path[1]
    f = (TRAINING_START_Y - ay) / (by - ay)
    sx, sy = offset_starboard([(ax + (bx - ax) * f, TRAINING_START_Y), (bx, by)],
                        TRAINING_KEEP_RIGHT_NM)[0]
    own = OwnShip(ShipState(x=sx, y=sy, course=bearing_to(sx, sy, bx, by), speed=TRAINING_KN,
                            depth=0.0, max_depth=400))
    world = World(own=own, env=env, rng=random.Random(rng.random()), size_nm=size,
                  patrol_end=3 * 3600)

    # trafiken i fjorden: ut håller österut, in västerut (styrbord om gångriktningen)
    out_pts = offset_starboard(path, TRAINING_KEEP_RIGHT_NM + 0.05)
    in_pts = offset_starboard(list(reversed(path)), TRAINING_KEEP_RIGHT_NM + 0.05)
    lanes = (Lane("ut", start=out_pts[0], end=(out_pts[-1][0], size + 3.0), per_hour=0.5,
                  speed=(7.0, 10.0), via=tuple(out_pts[1:])),
             Lane("in", start=(in_pts[0][0], size + 2.0), end=in_pts[-1], per_hour=0.5,
                  speed=(7.0, 10.0), via=tuple(in_pts[:-1])))
    traffic = TrafficGenerator(TrafficDef(lanes=lanes, initial=0, width_nm=0.03),
                               random.Random(rng.random()))
    # ett fartyg på väg in möter oss i fjorden
    y0, y1 = lanes[1].start[1], lanes[1].end[1]
    meet_y = mouth_y + rng.uniform(1.5, 3.0)
    traffic._spawn(world, lanes[1], (meet_y - y0) / (y1 - y0))
    traffic.next_t[1] = rng.randint(20 * 60, 50 * 60)
    world.spawners.append(traffic)

    area_x = path[-1][0] + rng.choice((-1.0, 1.0)) * rng.uniform(*TRAINING_AREA_SIDE_NM)
    area_y = mouth_y + TRAINING_AREA_OUT_NM
    world.mission["nuclear_authorized"] = False
    world.mission["training"] = {"outcome": "training_done"}
    world.mission["no_dive_fjord"] = "dived_in_fjord"
    world.mission["fail_grounding"] = "grounded"
    # farleden enligt kortet: från första punkten framför oss ut genom mynningen
    fairway = [p for p in cfj.path if p[1] > TRAINING_START_Y + 0.3]
    known = [(TRAINING_AREA, area_x, area_y, 0.1, 0),
             ("Poljarnyj", ax - fj.half_w[0] - 0.4, TRAINING_START_Y, 0.05, 0)]
    return Scenario(world, _crew(), TRAINING_ORDER, TRAINING_CLOCK,
                    known_positions=known, chart_seabed=chart,
                    tide_table=tide.table_copy(random.Random(rng.random())),
                    area_name="Kolafjorden", fairway=fairway, fairway_to=TRAINING_AREA,
                    training=TRAINING_STEPS, training_area=TRAINING_AREA, no_dive_in_fjord=True,
                    outcome_text={
                        "training_done": "Övningsprogrammet är genomfört. K-114 ligger i "
                                         "ytläge i övningsområdet och anmäler till staben i "
                                         "Severomorsk. Båten och besättningen är klara för "
                                         "patrull.",
                        "patrol_end": "Tiden är ute innan programmet var genomfört; "
                                      "staben i Severomorsk vill ha en förklaring.",
                        "dived_in_fjord": "K-114 har dykt inne i Kolafjorden, mot ordern. "
                                          "Övningen avbryts och befälhavaren kallas till staben.",
                        "grounded": "K-114 har gått på grund. Övningen avbryts; båten går "
                                    "tillbaka till Poljarnyj för dockning.",
                        "neutral_sunk": "Ett sovjetiskt fartyg har sänkts i Kolafjorden. "
                                        "Befälhavaren kallas till staben.",
                        "quit": "Kaptenen har avbrutit övningen. K-114 går tillbaka till "
                                "Poljarnyj.",
                        "lost": "K-114 är förlorad i Barents hav med hela besättningen.",
                    })



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


register(ScenarioDef(
    "kuba", "Kvadrat 7, oktober 1962",
    "Kubakrisen. Förbli oupptäckt för en amerikansk jagare i karantänlinjen.",
    default_scenario))
register(ScenarioDef(
    "kuba-kort", "Kvadrat 7 – sambandsfönstret, oktober 1962",
    "Kort variant. En amerikansk jagare patrullerar några sjömil bort. Sambandstillfället "
    "öppnar om fem minuter: sänd rapporten och se till att ingen har er när det stänger.",
    kuba_short_scenario, minutes=25))
register(ScenarioDef(
    "arktis", "Under packisen, oktober 1962",
    "Polarnatt vid 85° nord. Drivstationen Nord-7 har tystnat. Ta er dit under isen, "
    "hitta öppet vatten och gå upp. En amerikansk ubåt är på väg mot samma plats.",
    arctic_scenario))
register(ScenarioDef(
    "arktis-kort", "Under packisen – sista milen, oktober 1962",
    "Kort variant. Vakten har gått mot Nord-7 under isen i tjugo minuter. Stationen ligger "
    "några sjömil fram, en amerikansk ubåt är på väg dit och isen ovanför är tjock.",
    arctic_short_scenario, minutes=25))
register(ScenarioDef(
    "jagad", "Jagade, natten till 27 oktober 1962",
    "En amerikansk jagare har just fått kontakt och en till är på väg. Bryt kontakten "
    "och ta er ut ur kvadrat 7 innan sjunkbomberna blir skarpa.",
    hunted_scenario))
register(ScenarioDef(
    "jagad-kort", "Jagade – skarpt, natten till 27 oktober 1962",
    "Kort variant. Jagaren fäller redan skarpa sjunkbomber och går in igen på en och en halv "
    "sjömil. Kvadraten är liten, men den andra jagaren spärrar den kortaste vägen ut.",
    hunted_short_scenario, minutes=25))
register(ScenarioDef(
    "sundet", "Guantánamo, 25 oktober 1962",
    "Smyg in mot den amerikanska flottbasen genom ett grunt inlopp med nät, hydrofoner och "
    "patrullbåt. Fotografera ankarplatsen i dagsljus och ta er ut igen.",
    strait_scenario))
register(ScenarioDef(
    "sundet-in", "Guantánamo – grinden, 25 oktober 1962",
    "Kort variant. Ni ligger i väntläget utanför nätet och ett fartyg är på väg in mot "
    "grinden. Ta er in bakom det och fotografera ankarplatsen.",
    strait_in_scenario, minutes=25))
register(ScenarioDef(
    "sundet-ut", "Guantánamo – ut med filmen, 25 oktober 1962",
    "Kort variant. Bilderna av ankarplatsen är tagna och ni ligger innanför nätet. Ett "
    "fartyg är på väg ut mot grinden. Ta er ut förbi patrullbåten med filmen.",
    strait_out_scenario, minutes=20))
register(ScenarioDef(
    "konvoj", "Konvojen, 28 oktober 1962",
    "Kriget har börjat. En eskorterad konvoj med trupper till Kuba sicksackar genom "
    "kvadrat 12. Kom i skjutläge, sänk minst ett fartyg och bryt kontakten.",
    convoy_scenario))
register(ScenarioDef(
    "konvoj-kort", "Konvojen – skjutläge, 28 oktober 1962",
    "Kort variant. Vakten har följt konvojen i en halvtimme och plottet har den. Ni tar "
    "befälet med målen några sjömil bort: kom i skjutläge, sänk och bryt kontakten.",
    convoy_short_scenario, minutes=30))
register(ScenarioDef(
    "konvoj-mot", "Konvojen – motanfallet, 28 oktober 1962",
    "Kort variant. Vakten har skjutit en salva mot konvojen och torpederna är framme om "
    "en knapp minut. Eskorten vänder redan mot er: bryt kontakten.",
    convoy_counter_scenario, minutes=20))
register(ScenarioDef(
    "ovning", "Övning – ut från Poljarnyj, oktober 1962",
    "Övning för att lära känna båten. Gå ut genom Kolafjorden i ytläge, möt trafiken, "
    "dyk utanför mynningen och gå igenom övningsprogrammet: periskop, fix, provdjup, "
    "smygmotor.",
    training_scenario))
