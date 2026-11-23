"""«Клайд» – in i Firth of Clyde (`clyde`) och den korta varianten (`clyde-in`).

20 oktober 1962, natt. In i undervattensläge förbi Pladda upp mot Cumbraeöarna, spela in en
amerikansk Polarisubåt som går ut från Holy Loch, och kom ut söder om Pladda oupptäckta före
gryningen. Navigeringen är motståndet: tidvattnet i sunden, fyrar som bara syns ibland, moln som
stänger stjärnorna, patrullbåtar och en hydrofonlinje i västra rännan, fiskebåtar och handelsfartyg.

Ingen minering: 1962 var det fred i Clyde. Largs-rännan öster om Great Cumbrae är obevakad men
under en sjömil bred och 30–45 m djup: smitvägen.
"""
from __future__ import annotations

import random
from dataclasses import replace
from typing import Any

from ..clyde import POLARIS_ROUTE, ClydeTraffic, FishingAI, TransitAI
from ..entities import Vessel
from ..geo import bearing_to, distance
from ..environment import Clouds, Environment, TidalStream
from ..goals import EscapeGoal, GroundingFails, RecordGoal
from ..ownship import OwnShip
from ..seabed import CLYDE_HOLY_LOCH, CLYDE_LIGHTS, CLYDE_SIZE_NM, clyde_seabed
from ..ship import ShipState
from ..traffic import Lane, TrafficDef
from ..world import World
from .common import RadioMessage, Scenario, Warmup, _crew, _place

CLYDE_PLACE = (55.75, -4.95)          # mitt i firthen; brittisk sommartid (UTC+1) till 28 okt 1962
CLYDE_START_CLOCK = 21 * 3600 + 30 * 60
CLYDE_DAWN_CLOCK = 7 * 3600 + 30 * 60  # borgerlig gryning: då ska vi vara ute
CLYDE_DEPART_CLOCK = 24 * 3600 + 30 * 60   # Polarisbåten lämnar Holy Loch ungefär 00:30
CLYDE_DEPART_SPREAD_S = 30 * 60
CLYDE_ESCAPE_Y = 2.0                  # ute: söder om Pladda
CLYDE_MISS_Y = -3.0                   # Polarisbåten så långt söderut: den är borta

CLYDE_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 20 OKTOBER 1962

1. GÅ IN I FIRTH OF CLYDE I UNDERVATTENSLÄGE
   FÖRBI PLADDA MOT CUMBRAEÖARNA.
2. EN AMERIKANSK UBÅT AV TYP POLARIS VÄNTAS
   LÄMNA HOLY LOCH I NATT. SPELA IN DESS LJUD
   MED SONAREN: TIO MINUTER GOTT LJUD.
3. LÄMNA FIRTHEN SÖDER OM PLADDA OUPPTÄCKT
   FÖRE GRYNINGEN. FYRARNA PLADDA, HOLY ISLE,
   LITTLE CUMBRAE OCH TOWARD POINT LYSER.
4. BRITTISKA OCH AMERIKANSKA PATRULLBÅTAR
   OCH EN HYDROFONLINJE VID CUMBRAE. VAPEN
   FÅR ENDAST ANVÄNDAS I SJÄLVFÖRSVAR.

SLUT
"""

CLYDE_RADIO = [
    RadioMessage("FRÅN HUVUDSTABEN. POLARISBÅTEN HAR BUNKRAT VID DEPÅFARTYGET. AVGÅNG "
                 "TROLIG EFTER MIDNATT. INSPELNINGEN ÄR AV STÖRSTA VIKT."),
    RadioMessage("FRÅN HUVUDSTABEN. INGEN ÄNDRING. FÖRBLI OUPPTÄCKT.",
                 {"nuclear": "order_only"}),
]

OUTCOMES = {
    "clyde_done": "K-114 har lämnat Firth of Clyde med inspelningen av Polarisbåten. Bandet "
                  "går till Moskva med första tillfälle.",
    "recorded": "Inspelningen av Polarisbåten är klar. Nu återstår vägen ut förbi Pladda.",
    "record_missed": "Polarisbåten har passerat Pladda och gått ut till havs. K-114 fick ingen "
                     "användbar inspelning.",
    "grounded": "K-114 har gått på grund i Firth of Clyde. Hon måste upp, och upptäckten är "
                "ett faktum.",
    "patrol_end": "Det ljusnar över Arran. K-114 är fortfarande inne i firthen.",
    "forced": "K-114 har gått till ytan i Firth of Clyde. Besättningen lever, men uppdraget har "
              "misslyckats och Sovjetunionen har en diplomatisk kris till.",
    "sank": "Ett fartyg i Firth of Clyde är sänkt. Det är krig.",
    "peace_broken": "Ett fartyg i Firth of Clyde är sänkt. Det är krig.",
    "quit": "Kaptenen har avbrutit. K-114 lämnar firthen i förtid.",
    "lost": "K-114 är förlorad i Firth of Clyde med hela besättningen.",
}


def _sim_t(clock_s: int, start_clock: int) -> int:
    return (clock_s - start_clock) % 86400


def clyde_scenario(rng: random.Random, short: bool = False) -> Scenario:
    """Firth of Clyde: in, spela in Polarisbåten, ut före gryningen. short: `clyde-in`."""
    from ..harbor import HarborDefense, HydrophoneLine, PatrolBoatAI, hydrophone_points
    start_clock = CLYDE_IN_CLOCK if short else CLYDE_START_CLOCK
    sb_rng = random.Random(rng.random())
    seabed = clyde_seabed(sb_rng)
    chart = seabed.chart_copy(sb_rng, err_nm=0.1, miss_p=0.0)
    depart_clock = CLYDE_DEPART_CLOCK + rng.randint(-CLYDE_DEPART_SPREAD_S, CLYDE_DEPART_SPREAD_S)
    # tidvattnet: floden sätter uppför firthen (den korta varianten flyttar stiltjen, _short)
    tide = TidalStream(flood_set=355.0, peak_kn=rng.uniform(1.0, 1.4),
                       phase_s=rng.uniform(0, 44712.0))
    clouds_rng = random.Random(rng.random())
    breaks = []
    t = clouds_rng.randint(20 * 60, 90 * 60)
    while t < 12 * 3600:
        dur = clouds_rng.randint(10 * 60, 25 * 60)
        breaks.append((t, t + dur))
        t += dur + clouds_rng.randint(80 * 60, 180 * 60)
    clouds = Clouds(cover=clouds_rng.uniform(0.75, 0.95), breaks=tuple(breaks))
    env = Environment(clock_start=start_clock, sea_state=3, background_noise=64.0,
                      current_kn=0.0, seabed=seabed, tide=tide, clouds=clouds,
                      lights=CLYDE_LIGHTS, **_place(CLYDE_PLACE, utc_offset_h=1.0))
    own = OwnShip(ShipState(x=16.8 + rng.uniform(-0.4, 0.4), y=2.6 + rng.uniform(-0.3, 0.3),
                            course=10.0, speed=6, depth=60, max_depth=400))
    patrol_end = _sim_t(CLYDE_DAWN_CLOCK, start_clock)
    world = World(own=own, env=env, rng=random.Random(rng.random()), size_nm=CLYDE_SIZE_NM,
                  patrol_end=patrol_end)

    # Polarisbåten vid depåfartyget i Holy Loch
    hx, hy = CLYDE_HOLY_LOCH
    depart_t = _sim_t(depart_clock, start_clock)
    ssbn = Vessel("SSBN", "ssbn", ShipState(x=hx + 0.1, y=hy - 0.05, course=110.0, speed=0,
                                            turn_rate=1.5, accel=0.05, max_speed=16),
                  side="enemy", has_radar=True)
    world.contacts.append(ssbn)
    polaris = TransitAI(ssbn, POLARIS_ROUTE, depart_t)
    world.ais.append(polaris)
    world.contacts.append(Vessel("M1", "moored", ShipState(x=hx - 0.15, y=hy + 0.05, course=290.0,
                                                           speed=0), side="enemy", has_radar=False))

    # bevakningen: hydrofonlinjen tvärs västra rännan norr om Little Cumbrae, en patrullbåt där
    # och en utanför Toward och Dunoon. Largs-rännan är obevakad.
    phones = HydrophoneLine(hydrophone_points(17.3, 19.6, 19.3, 0.5), random.Random(rng.random()))
    boats = []
    for i, box in enumerate(((17.6, 18.0, 19.6, 22.5), (19.6, 26.0, 22.2, 30.0)), start=1):
        pb = Vessel(f"PB{i}", "patrol",
                    ShipState(x=rng.uniform(box[0], box[2]), y=rng.uniform(box[1], box[3]),
                              course=rng.uniform(0, 360), speed=6.0, turn_rate=4.0, accel=0.5,
                              max_speed=24),
                    side="enemy", has_radar=True)
        world.contacts.append(pb)
        boat = PatrolBoatAI(pb, random.Random(rng.random()), area=CLYDE_SIZE_NM, patrol_speed=6.0,
                            box=box, leash_nm=2.0)
        boat.quiet_patrol = True            # fred: lyssnar, pingar först när den söker
        world.ais.append(boat)
        boats.append(boat)
    world.spawners.append(HarborDefense(hydrophones=phones, net=None, boats=boats))

    # fiskebåtar mellan Arran och Ayrshire
    for i in range(3):
        box = (18.0, 4.0, 27.0, 14.0)
        for _ in range(30):
            fx, fy = rng.uniform(box[0], box[2]), rng.uniform(box[1], box[3])
            if seabed.depth_at(fx, fy) > 30:
                break
        fb = Vessel(f"F{i + 1}", "fishing", ShipState(x=fx, y=fy, course=rng.uniform(0, 360),
                                                      speed=3.5, turn_rate=3.0, accel=0.2,
                                                      max_speed=9),
                    side="neutral")
        world.contacts.append(fb)
        world.ais.append(FishingAI(fb, random.Random(rng.random()), box,
                                   lambda x, y: seabed.depth_at(x, y) > 30))

    # handelsfartyg upp till Greenock och ned, färjan Wemyss Bay–Rothesay på kvällen
    up_via = ((17.6, 8.0), (18.6, 16.0), (19.1, 21.5), (20.0, 25.5), (22.0, 30.5))
    lanes = (Lane("upp", start=(17.5, -4.0), end=(23.4, 33.8), per_hour=0.35, speed=(9.0, 12.0),
                  moor=True, via=up_via),
             Lane("ned", start=(23.4, 33.8), end=(17.0, -6.0), per_hour=0.35, speed=(9.0, 12.0),
                  via=tuple(reversed(up_via))),
             Lane("färjan", start=(21.9, 27.1), end=(18.0, 24.8), per_hour=1.0, speed=(10.0, 12.0),
                  moor=True))
    ferry_until = _sim_t(21 * 3600 + 45 * 60, start_clock)
    traffic = ClydeTraffic(TrafficDef(lanes=lanes, initial=1, width_nm=0.1),
                           random.Random(rng.random()),
                           until={2: ferry_until if ferry_until < 12 * 3600 else 0})
    traffic.populate(world)
    world.spawners.append(traffic)

    record = RecordGoal("SSBN", None if not short else "recorded", "record_missed", CLYDE_MISS_Y)
    world.goals.append(record)
    world.goals.append(GroundingFails("grounded"))
    if not short:
        world.goals.append(EscapeGoal(0.5, "clyde_done", y_below=CLYDE_ESCAPE_Y,
                                      requires_record="SSBN"))

    known = [("Holy Loch", hx + rng.gauss(0, 0.05), hy + rng.gauss(0, 0.05), 0.1, 0)]
    sc = Scenario(world, _crew(), CLYDE_ORDER, start_clock,
                  radio_windows=[w for w in (_sim_t(23 * 3600, start_clock),
                                             _sim_t(3 * 3600, start_clock)) if w > 1800],
                  radio_messages=list(CLYDE_RADIO), known_positions=known, chart_seabed=chart,
                  tide_table=tide.table_copy(random.Random(rng.random())),
                  area_name="Firth of Clyde", light_list=CLYDE_LIGHTS,
                  escape_margin_nm=None if short else 0.5,
                  escape_y_below=None if short else CLYDE_ESCAPE_Y,
                  escape_requires_record=not short,
                  tasks=("inspelning",) if short else ("inspelning", "ut"),
                  outcome_text=OUTCOMES)
    if short:
        _short(sc, rng, polaris, tide)
    return sc


# --- kort variant: söder om Little Cumbrae, Polarisbåten på väg ------------------------------
CLYDE_IN_CLOCK = 1 * 3600 + 20 * 60
CLYDE_IN_WARM_S = 8 * 60
CLYDE_IN_LIMIT_S = 40 * 60
CLYDE_IN_SIGMA_NM = 1.0               # besticket vid överlämnandet: sedan Pladda utan fix
CLYDE_IN_SHIP_NM = (3.0, 4.0)         # Polarisbåten så långt norr om oss vid överlämnandet
CLYDE_IN_SIDE_NM = (1.9, 2.6)         # vi så långt vid sidan av dess väg


def _route_x(route, y: float) -> float:
    """Farledens x där den korsar y (vägen går söderut)."""
    for (ax, ay), (bx, by) in zip(route, route[1:]):
        if by <= y <= ay:
            return ax + (bx - ax) * (y - ay) / (by - ay)
    return route[-1][0]


def _short(sc: Scenario, rng: random.Random, polaris: TransitAI, tide: TidalStream) -> None:
    w = sc.world
    r2 = random.Random(rng.random())
    o = w.own.state
    route = list(POLARIS_ROUTE)
    # vid sidan av farleden: Polarisbåten går förbi för långt bort för bandet om vi blir kvar
    y0 = 13.6 + r2.uniform(-0.4, 0.4)
    tx = _route_x(route, y0)
    o.x, o.y = tx + r2.choice((-1.0, 1.0)) * r2.uniform(*CLYDE_IN_SIDE_NM), y0
    o.depth = o.ordered_depth = 50.0
    o.speed = o.ordered_speed = 3.0
    o.course = o.ordered_course = 0.0
    # Polarisbåten redan på väg: längs farleden så långt norr om oss när vakten lämnar över
    ahead = r2.uniform(*CLYDE_IN_SHIP_NM)
    v = polaris.vessel
    # gå bakåt längs vägen från farledens punkt tvärs om oss
    pts = [(tx, y0)] + [p for p in route if p[1] > y0][::-1]
    left = ahead + polaris.speed * CLYDE_IN_WARM_S / 3600
    px, py = pts[0]
    for qx, qy in pts[1:]:
        d = distance(px, py, qx, qy)
        if d >= left:
            f = left / d
            px, py = px + (qx - px) * f, py + (qy - py) * f
            break
        left -= d
        px, py = qx, qy
    v.state.x, v.state.y = px, py
    v.state.speed = polaris.speed
    polaris.route = [p for p in route if p[1] < py - 0.1]
    polaris.depart_t = 0
    polaris.passed = polaris.slow_legs
    v.state.course = v.state.ordered_course = bearing_to(px, py, *polaris.route[0])
    # tidvattnet vänder strax: stiltje ungefär vid överlämnandet
    tide = replace(tide, phase_s=CLYDE_IN_WARM_S + r2.uniform(5, 15) * 60 - tide.period_s / 4)
    w.env.tide = tide
    sc.tide_table = tide.table_copy(random.Random(rng.random()))
    w.patrol_end = CLYDE_IN_WARM_S + CLYDE_IN_LIMIT_S
    sc.start_fix_sigma = CLYDE_IN_SIGMA_NM
    sc.radio_windows = []
    sc.radio_messages = []
    sc.warmup = Warmup(CLYDE_IN_WARM_S, _clyde_watch_pilot)
    sc.secret_order = CLYDE_ORDER + (
        "\nVAKTJOURNALEN, 01.28: SÖDER OM LITTLE CUMBRAE\n"
        "PÅ 50 METER, ÖVER SKIKTET, SMYGMOTOR. INGEN FIX\nSEDAN PLADDA.\n"
        "SONAR HAR ETT YTFARTYG I NORR, EN AXEL.\n")


def _clyde_watch_pilot(game: Any, t: int) -> None:
    """Vakten: smygmotor, sakta norrut mot farleden, så att sonar och plott får Polarisbåten."""
    if t == 0:
        game.command("smygmotor, fart 3, kurs 000")


def clyde_in_scenario(rng: random.Random) -> Scenario:
    return clyde_scenario(rng, short=True)
