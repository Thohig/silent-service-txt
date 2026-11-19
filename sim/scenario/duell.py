"""Duellen under isen (duell) och den korta varianten (duell-kort).

Krig, 28 oktober 1962. En amerikansk atomubåt skyddar isön T-3 (en amerikansk drivstation på
en isö) i Nord-3 och har order att sänka sovjetiska ubåtar (`SubmarineAI.roe = "attack"`): hör
den oss går den närmare, öppnar torpedrören och skjuter Mk 37. Sänk den (utfallet `sank`) eller
lämna området utan att den har oss (`escaped`).

Kort variant (`duell-kort`): ubåten har redan pejlat oss och är ett par sjömil bort; vakten har
gått på smygmotor i några minuter. Vi är närmare kanten, så att det går att komma undan.
"""
from __future__ import annotations

import math
import random
from typing import Any

from ..arctic import DriftStation, EnemySub, SubDatum, SubmarineAI
from ..environment import ArcticProfile, Environment
from ..geo import bearing_to, distance
from ..goals import EscapeGoal
from ..ice import IceField, clearance
from ..ownship import OwnShip
from ..seabed import arctic_seabed
from ..ship import ShipState
from ..world import World
from .common import ARCTIC_PLACE, RadioMessage, Scenario, Warmup, _compass, _crew, _place

DUEL_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 28 OKTOBER 1962

1. KRIGSTILLSTÅND RÅDER MED FÖRENTA STATERNA.
2. EN AMERIKANSK ATOMUBÅT SKYDDAR ISÖN T-3
   I NORD-3, CIRKA {dist} SJÖMIL {dir} OM ER.
   DEN HAR ORDER ATT SÄNKA SOVJETISKA UBÅTAR.
3. SÄNK DEN. KAN NI INTE, LÄMNA NORD-3
   UTAN ATT DEN HAR ER.
4. KONVENTIONELLA VAPEN TILLÅTNA. T-5 FÅR
   INTE ANVÄNDAS.

SLUT
"""

ISLAND_NAME = "T-3"
DUEL_SIZE_NM = 20.0
DUEL_LIMIT_S = 4 * 3600
DUEL_SHORT_SIZE_NM = 10.0
DUEL_SHORT_WARM_S = 3 * 60
DUEL_SHORT_LIMIT_S = 40 * 60
DUEL_SHORT_SUB_NM = (3.0, 4.0)        # ubåten så långt bort när vakten tar över
ESCAPE_MARGIN_NM = 1.0
US_MAX_KN = 18                        # Skate-klassen 1962: inte fortare än vår SET-53 (23 kn)
US_BASE_DB = 129.0                    # Skate-klassen: bullrigare än senare amerikanska ubåtar


class IceIsland(DriftStation):
    """T-3: en amerikansk forskningsstation på en isö. Generatorn hörs genom isen."""


def duel_scenario(rng: random.Random, short: bool = False) -> Scenario:
    start_clock = 3 * 3600
    ice = IceField(random.Random(rng.random()), drift_set=200.0, drift_kn=0.2)
    env = Environment(profile=ArcticProfile(), clock_start=start_clock, ice=ice, sea_state=1,
                      background_noise=52.0, current_set=150.0, current_kn=0.1,
                      night_visibility_nm=1.0, **_place(ARCTIC_PLACE))
    size = DUEL_SHORT_SIZE_NM if short else DUEL_SIZE_NM
    if short:
        x, y = size / 2 + rng.uniform(-1.0, 1.0), rng.uniform(1.5, 2.2)   # nära södra kanten
    else:
        x, y = size / 2 + rng.uniform(-1.5, 1.5), size / 2 + rng.uniform(-1.5, 1.5)
    while clearance(ice, x, y, 0.0, 150.0) < 10:
        x += 0.05
    own = OwnShip(ShipState(x=x, y=y, course=0, speed=5, depth=150, max_depth=400))

    # isön och ubåten som skyddar den
    ib = rng.uniform(-50, 50)
    ir = rng.uniform(5.5, 7.0) if short else rng.uniform(4.0, 6.0)
    ix, iy = x + ir * math.sin(math.radians(ib)), y + ir * math.cos(math.radians(ib))
    island = IceIsland("T3", ix, iy)
    if short:
        ur = rng.uniform(*DUEL_SHORT_SUB_NM)
        ub = rng.uniform(-40, 40)
        ux, uy = x + ur * math.sin(math.radians(ub)), y + ur * math.cos(math.radians(ub))
    else:
        ua = rng.uniform(0, 360)
        ux, uy = ix + 1.5 * math.sin(math.radians(ua)), iy + 1.5 * math.cos(math.radians(ua))
    us = EnemySub("SSN1", ShipState(x=ux, y=uy, course=bearing_to(ux, uy, x, y),
                                    speed=10 if short else 6,
                                    depth=150, turn_rate=1.5, accel=0.05, max_speed=US_MAX_KN,
                                    max_depth=300), base=US_BASE_DB)
    world = World(own=own, contacts=[island, us], env=env, rng=random.Random(rng.random()),
                  size_nm=size, patrol_end=DUEL_LIMIT_S)
    ai = SubmarineAI(us, random.Random(rng.random()), island)
    ai.roe = "attack"
    ai.state = "patrol"
    if short:
        # den har redan pejlat oss: skuggar och går närmare
        ai.state = "trail"
        # pejlingen är färsk när kaptenen tar över: den går fort mot oss under hela vakten
        ai.datum = SubDatum(x + rng.gauss(0, 0.3), y + rng.gauss(0, 0.3), 150.0, 0.4,
                            DUEL_SHORT_WARM_S - 60)
        ai.datums = [ai.datum]
        ai.next_fire = DUEL_SHORT_WARM_S + 120           # skjuter inte under vaktens minuter
    world.ais.append(ai)
    world.mission["nuclear_authorized"] = False
    world.goals.append(EscapeGoal(ESCAPE_MARGIN_NM, "escaped"))

    order = DUEL_ORDER.format(dist=round(distance(x, y, ix, iy)),
                              dir=_compass(bearing_to(x, y, ix, iy)))
    messages = [
        RadioMessage("FRÅN HUVUDSTABEN. KRIGSTILLSTÅND KVARSTÅR. AMERIKANSK UBÅT VID T-3 HAR "
                     "SÄNKT B-75 I NORD-2. SÄNK DEN.",
                     {"nuclear_authorized": False, "nuclear": "forbidden", "war": True}),
    ]
    windows = [] if short else [(c - start_clock) for c in (4 * 3600, 6 * 3600)]
    known = [(ISLAND_NAME, ix + rng.gauss(0, 0.5), iy + rng.gauss(0, 0.5), 1.0, 0)]
    if short:
        world.patrol_end = DUEL_SHORT_WARM_S + DUEL_SHORT_LIMIT_S
        messages = []
    sb_rng = random.Random(rng.random())
    env.seabed = arctic_seabed(sb_rng, size)
    chart = env.seabed.chart_copy(sb_rng, err_nm=0.8)
    return Scenario(world, _crew(), order, start_clock, chart_seabed=chart,
                    radio_windows=windows, radio_messages=messages, known_positions=known,
                    area_name="område Nord-3", escape_margin_nm=ESCAPE_MARGIN_NM,
                    tasks=("ut",), nuclear_order="forbidden", at_war=True,
                    outcome_text={
                        "sank": "Brytljuden från den amerikanska ubåten tystnar under isen. "
                                "K-114 har vunnit duellen i Nord-3.",
                        "escaped": "K-114 har brutit kontakten och lämnat Nord-3. Den "
                                   "amerikanska ubåten lyssnar fortfarande vid T-3.",
                        "patrol_end": "Tiden är ute. K-114 är kvar i Nord-3 och den amerikanska "
                                      "ubåten lever.",
                        "quit": "Kaptenen har avbrutit uppdraget. K-114 lämnar Nord-3.",
                        "lost": "K-114 är sänkt under isen i Nord-3 med hela besättningen.",
                    })


def _duel_watch_pilot(game: Any, t: int) -> None:
    """Vakten: smygmotor, långsamt och djupt medan sonar lyssnar."""
    if t == 0:
        game.command("smygmotor, fart 4, djup 150")


def duel_short_scenario(rng: random.Random) -> Scenario:
    sc = duel_scenario(rng, short=True)
    sc.warmup = Warmup(DUEL_SHORT_WARM_S, _duel_watch_pilot)
    sc.secret_order += ("\nVAKTJOURNALEN, 03.03: AMERIKANSKA UBÅTEN HÖRS\n"
                        "NÄRA. DEN HAR TROLIGEN PEJLAT OSS. SMYGMOTOR,\n"
                        "150 METER. KAPTENEN TAR BEFÄLET.\n")
    sc.outcome_text["patrol_end"] = ("Tiden är ute. Den amerikanska ubåten har fortfarande "
                                     "kontakt med K-114 i Nord-3.")
    return sc
