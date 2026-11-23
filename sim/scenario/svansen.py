"""Svansen (svansen-kort): en amerikansk ubåt ligger i vår döda sektor akterut.

Krig, 28 oktober 1962, Norska havet om natten. Vi går på turbinen i 10 knop under språngskiktet mot
patrullområdet. En amerikansk Skate-ubåt skuggar oss `SHADOW_START_NM` akterut i döda sektorn
(`OwnShip.baffle_deg`, bara här; modellen i sim/sonar.py) och har order att sänka oss när den har sin
lösning (`SubmarineAI.shadow_until`). Vakten har gått rakt i åtta minuter: sonar vill strax lyssna
akterut (sim/stations/baffles.py). Sänk den (`sank`) eller skaka av den (`ShakeGoal`, `shaken`).
"""
from __future__ import annotations

import math
import random
from typing import Any

from ..arctic import DriftStation, EnemySub, SubDatum, SubmarineAI
from ..environment import Environment
from ..goals import ShakeGoal
from ..ownship import OwnShip
from ..seabed import arctic_seabed
from ..ship import ShipState
from ..world import World
from .common import Scenario, Warmup, _crew, _place

TAIL_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 28 OKTOBER 1962

1. KRIGSTILLSTÅND RÅDER MED FÖRENTA STATERNA.
2. FORTSÄTT TILL PATRULLOMRÅDET, KURS {course}.
3. AMERIKANSKA ATOMUBÅTAR ÄR RAPPORTERADE
   I NORSKA HAVET. DE SKUGGAR VÅRA UBÅTAR
   AKTERIFRÅN OCH SKJUTER NÄR DE HAR LÖSNING.
4. KONVENTIONELLA VAPEN TILLÅTNA. T-5 FÅR
   INTE ANVÄNDAS.

SLUT

VAKTJOURNALEN, 02.51: SVAGT METALLISKT LJUD
AKTERUT, GICK INTE ATT FÖLJA. TURBIN, 10 KNOP,
100 METER. KAPTENEN TAR BEFÄLET.
"""

NORWEGIAN_SEA_PLACE = (67.5, 2.0)
TAIL_SIZE_NM = 30.0
TAIL_WARM_S = 8 * 60                  # vakten går rakt: sonar vill lyssna akterut strax efter
TAIL_LIMIT_S = 25 * 60
TAIL_SPEED_KN = 10
TAIL_DEPTH_M = 100.0
SHADOW_START_NM = (1.6, 1.9)
TAIL_ATTACK_MIN = (12, 16)            # minuter efter överlämnandet: den har sin lösning
SHAKE_QUIET_S = 600
US_BASE_DB = 131.0                    # Skate-klassen, i marschfart (bullrigare än i duellens smygläge)
US_MAX_KN = 18


def _tail_watch_pilot(game: Any, t: int) -> None:
    """Vakten: rakt mot patrullområdet på turbinen, under skiktet."""
    if t == 0:
        st = game.world.own.state
        game.command(f"kurs {round(st.course) % 360:03d}, fart {TAIL_SPEED_KN}, "
                     f"djup {TAIL_DEPTH_M:.0f}")


def tail_short_scenario(rng: random.Random) -> Scenario:
    start_clock = 2 * 3600 + 43 * 60                  # 02:43, vakten lämnar över 02:51
    env = Environment(clock_start=start_clock, sea_state=3, night_visibility_nm=1.5,
                      background_noise=60.0, current_set=30.0, current_kn=0.3,
                      **_place(NORWEGIAN_SEA_PLACE))
    size = TAIL_SIZE_NM
    course = rng.uniform(200.0, 250.0)
    x, y = size / 2 + rng.uniform(-2, 2), size / 2 + rng.uniform(-2, 2)
    own = OwnShip(ShipState(x=x, y=y, course=course, speed=TAIL_SPEED_KN, depth=TAIL_DEPTH_M,
                            max_depth=400))

    # ubåten rakt akterut, samma kurs och fart
    r = rng.uniform(*SHADOW_START_NM)
    b = math.radians(course + 180.0 + rng.uniform(-6, 6))
    ux, uy = x + r * math.sin(b), y + r * math.cos(b)
    us = EnemySub("SSN1", ShipState(x=ux, y=uy, course=course, speed=TAIL_SPEED_KN,
                                    depth=TAIL_DEPTH_M + rng.uniform(-10, 20), turn_rate=1.5,
                                    accel=0.05, max_speed=US_MAX_KN, max_depth=300),
                  base=US_BASE_DB)
    world = World(own=own, contacts=[us], env=env, rng=random.Random(rng.random()),
                  size_nm=size, patrol_end=TAIL_WARM_S + TAIL_LIMIT_S)
    # dit den går om den tappar oss (ingen station i vattnet: bara en punkt att patrullera kring)
    ai = SubmarineAI(us, random.Random(rng.random()), DriftStation("PAT", x, y))
    ai.roe = "attack"
    ai.state = "shadow"
    ai.datum = SubDatum(x, y, TAIL_DEPTH_M, 0.3, 0)
    ai.datums = [ai.datum]
    ai.shadow_until = TAIL_WARM_S + 60 * rng.randint(*TAIL_ATTACK_MIN)
    ai.next_fire = 0
    world.ais.append(ai)
    world.goals.append(ShakeGoal("shaken", SHAKE_QUIET_S, since_t=TAIL_WARM_S))

    sb_rng = random.Random(rng.random())
    env.seabed = arctic_seabed(sb_rng, size)
    chart = env.seabed.chart_copy(sb_rng, err_nm=0.8)
    order = TAIL_ORDER.format(course=f"{round(course) % 360:03d}")
    sc = Scenario(world, _crew(), order, start_clock, chart_seabed=chart,
                  area_name="Norska havet", tasks=("patrull",), nuclear_order="forbidden",
                  at_war=True,
                  outcome_text={
                      "sank": "Brytljuden från den amerikanska ubåten tystnar akter om er. "
                              "K-114 fortsätter mot patrullområdet utan svans.",
                      "shaken": "Den amerikanska ubåten har tappat K-114. Ni fortsätter mot "
                                "patrullområdet utan svans.",
                      "patrol_end": "Tiden är ute. Den amerikanska ubåten har fortfarande "
                                    "kontakt med K-114.",
                      "quit": "Kaptenen har avbrutit uppdraget.",
                      "lost": "K-114 är sänkt i Norska havet med hela besättningen.",
                  })
    sc.warmup = Warmup(TAIL_WARM_S, _tail_watch_pilot)
    return sc
