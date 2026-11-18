"""Under isen: Nord-7 (arktis) och den korta varianten (arktis-kort)."""
from __future__ import annotations

import math
import random
from typing import Any

from ..arctic import DriftStation, EnemySub, SubmarineAI
from ..environment import ArcticProfile, Environment
from ..fmt import nm
from ..geo import bearing_to, distance
from ..goals import SurfaceNearGoal
from ..ice import IceField, clearance
from ..ownship import OwnShip
from ..seabed import arctic_seabed
from ..ship import ShipState
from ..world import World
from .common import ARCTIC_PLACE, RadioMessage, Scenario, Warmup, _compass, _crew, _place


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


def arctic_scenario(rng: random.Random, short: bool = False) -> Scenario:
    """Under packisen till Nord-7. short (`arktis-kort`): stationen ligger nära, vakten har
    gått mot den i 20 min, ubåten är närmare och branden kommer snart (arctic_short_scenario)."""
    start_clock = 2 * 3600
    ice = IceField(random.Random(rng.random()), drift_set=200.0, drift_kn=0.25)
    env = Environment(profile=ArcticProfile(), clock_start=start_clock, ice=ice, sea_state=1,
                      background_noise=52.0, current_set=150.0, current_kn=0.1,
                      night_visibility_nm=1.0, **_place(ARCTIC_PLACE))   # polarnatt
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
    world.goals.append(SurfaceNearGoal(station.id, 1.5, "station_reached"))

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
                    area_name="område Nord-3", tasks=("station",),
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
