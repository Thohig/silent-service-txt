"""Startläge, den hemliga ordern och radiomeddelanden från huvudstaben."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

from .crew import CrewMember, Role
from .enemy import DestroyerAI
from .entities import Vessel
from .environment import ArcticProfile, Environment, TidalStream
from .arctic import DriftStation, EnemySub, SubmarineAI
from .fmt import nm
from .ice import IceField, clearance
from .seabed import Seabed, arctic_seabed, kuba_seabed, strait_seabed
from .ownship import OwnShip
from .reports import Quality
from .ship import ShipState
from .geo import bearing_to, distance
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
    # brand i turbinrummet någon gång under första timmarna
    world.mission["fire_at"] = rng.randint(40 * 60, 110 * 60)
    crew = _crew()
    windows = [(c - start_clock) for c in (3 * 3600, 4 * 3600 + 1800, 6 * 3600)]
    sb_rng = random.Random(rng.random())
    env.seabed = arctic_seabed(sb_rng, world.size_nm)
    chart = env.seabed.chart_copy(sb_rng, err_nm=0.8)
    return Scenario(world, crew, order, start_clock, chart_seabed=chart,
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


def hunted_scenario(rng: random.Random) -> Scenario:
    """Jagade: spelet börjar när jagaren just fått kontakt och en till är på väg."""
    start_clock = 40 * 60                               # 00:40, mörkt
    env = Environment(clock_start=start_clock)
    size = 20.0
    # botten först: ubåten börjar på djupt vatten några sjömil från bankens kant
    sb_rng = random.Random(rng.random())
    y = rng.uniform(4.5, 6.5)
    seabed = kuba_seabed(sb_rng, (size / 2, y), size)
    chart = seabed.chart_copy(sb_rng, err_nm=0.5)
    env.seabed = seabed
    edge, west = _bank_edge_x(seabed, y, size)
    x = edge + (1.3 if west else -1.3)
    own = OwnShip(ShipState(x=x, y=y, course=rng.uniform(150, 210), speed=6, depth=45,
                            max_depth=400))

    def destroyer(vid: str, bearing: float, r: float, speed: float) -> Vessel:
        dx, dy = x + r * math.sin(math.radians(bearing)), y + r * math.cos(math.radians(bearing))
        return Vessel(vid, "destroyer",
                      ShipState(x=dx, y=dy, course=bearing_to(dx, dy, x, y), speed=speed,
                                turn_rate=2.0, accel=0.3, max_speed=32),
                      side="enemy", has_radar=True)

    # jagaren som har oss: 2–3 nm norrut, på väg in
    dd1 = destroyer("DD1", rng.uniform(320, 400) % 360, rng.uniform(2.2, 3.0), 15)
    # den andra kommer från söder och spärrar den vägen ut
    dd2 = destroyer("DD2", rng.uniform(150, 210), rng.uniform(7.0, 8.5), 25)
    world = World(own=own, contacts=[dd1, dd2], env=env, rng=random.Random(rng.random()),
                  size_nm=size, patrol_end=3 * 3600)
    ai1 = DestroyerAI(dd1, random.Random(rng.random()), area=size, escalate_after=3,
                      leash_nm=1.0)
    ai2 = DestroyerAI(dd2, random.Random(rng.random()), area=size, escalate_after=3,
                      leash_nm=1.0)
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

    windows = [(c - start_clock) for c in (1 * 3600 + 30 * 60, 3 * 3600)]
    return Scenario(world, _crew(), HUNTED_ORDER, start_clock,
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

HARBOR_PATROL_SPEED = 8.0


def strait_scenario(rng: random.Random) -> Scenario:
    """Genom sundet: smyg in mot en flottbas, fotografera ankarplatsen, ta dig ut."""
    from .harbor import HarborDefense, HydrophoneLine, Net, PatrolBoatAI, hydrophone_points
    start_clock = 4 * 3600 + 20 * 60                   # 04:20, gryningen kl 06:10
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
                  patrol_end=5 * 3600)

    # skyddet: nät i farledens mynning, hydrofoner en sjömil ut, patrullbåt däremellan
    net_y = shore_c + 0.5
    half = coast.channel_w / 2 + 0.05
    net = Net(y=net_y, x0=cx - half, x1=cx + half, gate_x=cx)
    phones = HydrophoneLine(hydrophone_points(cx - 3.0, cx + 3.0, shore_c - 1.0, 0.6),
                            random.Random(rng.random()))
    xs = [cx - 3.0 + 0.1 * i for i in range(61)]
    top = min(float(coast.shore(x)) for x in xs) - 0.4
    box = (cx - 3.0, top - 2.2, cx + 3.0, top)
    pb = Vessel("PB1", "patrol",
                ShipState(x=rng.uniform(box[0], box[2]), y=rng.uniform(box[1], box[3]),
                          course=rng.uniform(0, 360), speed=HARBOR_PATROL_SPEED, turn_rate=4.0,
                          accel=0.5, max_speed=24),
                side="enemy", has_radar=True)
    world.contacts.append(pb)
    boat = PatrolBoatAI(pb, random.Random(rng.random()), area=size,
                        patrol_speed=HARBOR_PATROL_SPEED, box=box, leash_nm=0.8)
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
    lanes = (Lane("in", start=(cx, -2.0), end=(cx, coast.bay_y - 0.2), per_hour=0.5,
                  speed=(8.0, 11.0), moor=True),
             Lane("ut", start=(cx, coast.bay_y - 0.4), end=(cx, -3.0), per_hour=0.4,
                  speed=(8.0, 11.0)))
    traffic = TrafficGenerator(TrafficDef(lanes=lanes, initial=1, width_nm=0.03),
                               random.Random(rng.random()))
    traffic.populate(world)
    world.spawners.append(traffic)

    world.mission["nuclear_authorized"] = False
    margin = 0.5
    world.mission["escape"] = {"margin_nm": margin, "outcome": "recon_done",
                               "requires_photo": int(Quality.GOD)}
    windows = [(c - start_clock) for c in (6 * 3600 + 30 * 60, 8 * 3600)]
    known = [("Ankarplatsen", ax + rng.gauss(0, 0.2), ay + rng.gauss(0, 0.2), 0.4, 0),
             ("Nätet", cx + rng.gauss(0, 0.05), net_y + rng.gauss(0, 0.15), 0.2, 0)]
    return Scenario(world, _crew(), STRAIT_ORDER, start_clock,
                    radio_windows=windows, radio_messages=list(STRAIT_RADIO),
                    known_positions=known, chart_seabed=chart,
                    tide_table=tide.table_copy(random.Random(rng.random())),
                    area_name="inloppet", escape_margin_nm=margin,
                    escape_requires_photo=Quality.GOD,
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
register(ScenarioDef(
    "jagad", "Jagade, natten till 27 oktober 1962",
    "En amerikansk jagare har just fått kontakt och en till är på väg. Bryt kontakten "
    "och ta er ut ur kvadrat 7 innan sjunkbomberna blir skarpa.",
    hunted_scenario))
register(ScenarioDef(
    "sundet", "Guantánamo, 25 oktober 1962",
    "Smyg in mot den amerikanska flottbasen genom ett grunt inlopp med nät, hydrofoner och "
    "patrullbåt. Fotografera ankarplatsen i dagsljus och ta er ut igen.",
    strait_scenario))
