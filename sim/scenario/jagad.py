"""Jagade på bankens kant (jagad) och den korta varianten (jagad-kort)."""
from __future__ import annotations

import math
import random

from ..weather import Showers
from ..air import AirDef, AirPatrol
from ..enemy import DestroyerAI
from ..entities import Vessel
from ..environment import Environment
from ..geo import bearing_to
from ..goals import EscapeGoal
from ..ownship import OwnShip
from ..seabed import Seabed, kuba_seabed
from ..ship import ShipState
from ..traffic import TrafficGenerator
from ..world import World
from .common import KUBA_PLACE, RadioMessage, Scenario, _crew, _place
from .kuba import KUBA_TRAFFIC

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
    RadioMessage("FRÅN HUVUDSTABEN. KÄRNVAPEN FÅR ANVÄNDAS ENDAST OM NI ANGRIPS MED SKARPA "
                 "SJUNKBOMBER. SIGNALSJUNKBOMBER ÄR INGET ANGREPP.",
                 {"nuclear": "conditional"}),
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
    env = Environment(showers=Showers(rain_per_h=0.2), clock_start=start_clock, sea_state=3, **_place(KUBA_PLACE))
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
    margin = 1.0
    world.goals.append(EscapeGoal(margin, "escaped"))
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
                  chart_seabed=chart, escape_margin_nm=margin, tasks=("ut",),
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
