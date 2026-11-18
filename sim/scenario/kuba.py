"""Kvadrat 7 (kuba) och sambandsfönstret (kuba-kort); Kuba-trafiken och flyget som andra scenarier lånar."""
from __future__ import annotations

import math
import random
from typing import Any

from ..air import AirDef, AirPatrol
from ..enemy import DestroyerAI
from ..entities import Vessel
from ..environment import Environment
from ..goals import ReportGoal
from ..ownship import OwnShip
from ..seabed import kuba_seabed
from ..ship import ShipState
from ..traffic import Lane, TrafficDef, TrafficGenerator
from ..world import World
from .common import KUBA_PLACE, RadioMessage, Scenario, Warmup, _crew, _place

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

RADIO_MESSAGES = [
    RadioMessage("FRÅN HUVUDSTABEN. AMERIKANSKA STYRKOR UPPRÄTTHÅLLER KARANTÄN. "
                 "FARTYG KAN ANVÄNDA SMÅ SIGNALSJUNKBOMBER FÖR ATT TVINGA UPP UBÅTAR. "
                 "FÖRBLI OUPPTÄCKT. SVARA EJ."),
    RadioMessage("FRÅN HUVUDSTABEN. RAPPORTERA OBSERVERADE FARTYGSRÖRELSER "
                 "VID FÖRSTA MÖJLIGA SAMBANDSTILLFÄLLE.", {"report_requested": True}),
    RadioMessage("FRÅN HUVUDSTABEN. INGEN ÄNDRING. VAPENANVÄNDNING EJ AUKTORISERAD.",
                 {"nuclear_authorized": False}),
]

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
    env = Environment(clock_start=start_clock, sea_state=3, **_place(KUBA_PLACE))
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
    sc.tasks = ("rapport",)
    w.goals.append(ReportGoal(w0, w0 + KUBA_SHORT_WINDOW_S, "reported", "report_missed",
                              contact_sigma_nm=KUBA_SHORT_CONTACT_SIGMA_NM))
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
