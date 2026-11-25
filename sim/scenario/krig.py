"""Krigspatrullen (krig) och den korta varianten (krig-kort).

Kriget har börjat. K-114 patrullerar kvadrat 14 norr om Kuba utan fast plan: staben sänder en
uppgift i taget vid sambandstillfällena (krigsskådeplatsen, `sim/theatre.py`) och kallar hem oss
när patrullen är slut. Den första uppgiften, en konvoj, står i ordern.
"""
from __future__ import annotations

import random
import textwrap
from dataclasses import replace

from ..air import AirDef, AirPatrol
from ..environment import Environment
from ..goals import EscapeGoal
from ..ownship import OwnShip
from ..seabed import kuba_seabed
from ..ship import ShipState
from ..theatre import Theatre, TheatreDef
from ..traffic import Lane, TrafficDef, TrafficGenerator
from ..weather import Showers, Weather
from ..world import World
from .common import Scenario, Warmup, _crew, _place
from .konvoj import _convoy_watch_pilot

WAR_PLACE = (22.5, -70.5)           # kvadrat 14, nordost om Kuba
WAR_AREA = "kvadrat 14"
WAR_SIZE = 30.0
WAR_START = 6 * 3600 + 30 * 60      # 06:30, strax efter gryningen
WAR_WINDOW_FIRST_S = 60 * 60        # första sambandstillfället 07.30
WAR_WINDOW_EVERY_S = 90 * 60        # sedan var 90:e minut
WAR_WINDOWS = 10                    # till 21.00
WAR_RECALL_S = 10 * 3600            # senast 16.30 kallar staben hem oss
WAR_LIMIT_S = 14 * 3600             # tiden är ute 20.30 (har vi inte gått hem)
WAR_ESCAPE_NM = 2.0

# den korta varianten: vakten har följt den första konvojen; efter den kallar staben hem oss.
# Kvadraten är mindre och vi ligger nära nordkanten (konvojen kommer norrifrån och går förbi)
WAR_SHORT_WARM_S = 35 * 60
WAR_SHORT_FAR_NM = (11.0, 13.0)            # konvojen går 10–12 kn: 5–9 nm vid överlämnandet
WAR_SHORT_SIZE = 20.0
WAR_SHORT_EDGE_NM = (3.0, 4.0)                          # så långt innanför nordkanten
WAR_SHORT_WINDOW_EVERY_S = 30 * 60
WAR_SHORT_WINDOW_FIRST_S = WAR_SHORT_WARM_S + WAR_SHORT_WINDOW_EVERY_S   # 07.35
WAR_SHORT_RECALL_S = WAR_SHORT_WARM_S + 59 * 60         # senast då (sänds 08.05), även mitt i anfallet
WAR_SHORT_LIMIT_S = WAR_SHORT_WARM_S + 140 * 60
WAR_SHORT_PASSED_NM = 6.0                               # konvojen förbi och så långt bort: missad

# handelssjöfarten går igenom kvadraten öster–väster även i krig
WAR_TRAFFIC = TrafficDef(lanes=(
    Lane("västgående", start=(34.0, 22.0), end=(-4.0, 16.0), per_hour=0.6),
    Lane("östgående", start=(-4.0, 8.0), end=(34.0, 12.0), per_hour=0.6),
), initial=2)
WAR_AIR = AirDef(entry=(-12.0, 26.0))       # ubåtsjaktflyg från Florida

WAR_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 28 OKTOBER 1962

1. KRIG. AMERIKANSKA STYRKOR GÅR MOT
   KUBA FÖR LANDSTIGNING.
2. K-114 PATRULLERAR {area} TILLS
   VIDARE. NYA UPPGIFTER SÄNDS VID
   SAMBANDSTILLFÄLLENA, FÖRSTA KL {first},
   SEDAN VAR {every}:E MINUT.
3. FÖRSTA UPPGIFT:
{task}
4. KÄRNVAPEN FÅR INTE ANVÄNDAS.
   NEUTRAL SJÖFART FÅR INTE ANGRIPAS.
5. NÄR STABEN KALLAR HEM ER: LÄMNA
   KVADRATEN I UNDERVATTENSLÄGE.

VÄDER: OSTLIG VIND 4, 3–5.

SLUT
"""


def _clock(start: int, t: int) -> str:
    c = (start + t) % 86400
    return f"{c // 3600:02d}.{c % 3600 // 60:02d}"


def war_scenario(rng: random.Random, tdef: TheatreDef | None = None,
                 first_far: tuple[float, float] = (16.0, 22.0),
                 windows: list[int] | None = None, limit_s: int = WAR_LIMIT_S,
                 size: float = WAR_SIZE, short: bool = False) -> Scenario:
    """Krigspatrullen: en konvoj i ordern, sedan uppgifter från staben tills den kallar hem oss.
    short: vi ligger nära nordkanten (den korta varianten, en kortare väg ut)."""
    tdef = tdef or TheatreDef(recall_after_s=WAR_RECALL_S)
    env = Environment(showers=Showers(rain_per_h=0.2, fog_per_h=0.08), clock_start=WAR_START, sea_state=4, **_place(WAR_PLACE),
                      weather=Weather(3, 5, trend=((0, 4),)))
    if short:
        ox, oy = size / 2 + rng.uniform(-3.0, 3.0), size - rng.uniform(*WAR_SHORT_EDGE_NM)
    else:
        ox, oy = size / 2 + rng.uniform(-3.0, 3.0), size / 2 + rng.uniform(-3.0, 3.0)
    # den korta: längs nordkanten, så att vakten inte går ut ur kvadraten av sig själv
    course = rng.choice((90, 270)) if short else rng.choice((0, 90, 180, 270))
    own = OwnShip(ShipState(x=ox, y=oy, course=course, speed=5, depth=80,
                            max_depth=400))
    world = World(own=own, env=env, rng=random.Random(rng.random()), size_nm=size,
                  patrol_end=limit_s, open_ended=True)
    windows = windows if windows is not None else \
        [WAR_WINDOW_FIRST_S + i * WAR_WINDOW_EVERY_S for i in range(WAR_WINDOWS)]
    air = AirPatrol(WAR_AIR, random.Random(rng.random()), area=size)
    theatre = Theatre(tdef, random.Random(rng.random()), size, WAR_AREA, WAR_START, windows, air)
    _start_first(theatre, world, first_far, north=short)
    msg = theatre.deliver(world)[0]                 # den första uppgiften står i ordern
    world.spawners.insert(0, theatre)               # före konvojerna (de läggs till efter)
    traffic = TrafficGenerator(WAR_TRAFFIC, random.Random(rng.random()))
    traffic.populate(world)
    world.spawners.append(traffic)
    world.spawners.append(air)
    world.goals.append(EscapeGoal(WAR_ESCAPE_NM, "patrol_done", requires_flag="recalled"))
    sb_rng = random.Random(rng.random())
    env.seabed = kuba_seabed(sb_rng, (ox, oy), size)
    chart = env.seabed.chart_copy(sb_rng, err_nm=0.5)

    task = msg.text.split(". ", 2)[2]               # utan "FRÅN HUVUDSTABEN. UPPGIFT 1."
    order = WAR_ORDER.format(
        area=WAR_AREA.upper(), first=_clock(WAR_START, windows[0]),
        every=(windows[1] - windows[0]) // 60 if len(windows) > 1 else 90,
        task=textwrap.fill(task, 36, initial_indent="   ", subsequent_indent="   "))
    known = [(*msg.waypoint, msg.motion, True)] if msg.waypoint else []
    return Scenario(world, _crew(), order, WAR_START, radio_windows=windows,
                    known_positions=known, chart_seabed=chart, area_name=WAR_AREA,
                    tasks=tuple(msg.flags["tasks"]), nuclear_order="forbidden", at_war=True,
                    escape_margin_nm=WAR_ESCAPE_NM, escape_task="ut", theatre=theatre,
                    outcome_text={
                        "patrol_done": "Staben har kallat hem K-114 och ni har lämnat kvadrat 14 "
                                       "i undervattensläge. Krigspatrullen är slut.",
                        "patrol_end": "Tiden är ute och K-114 har inte lämnat kvadrat 14. Staben "
                                      "stryker båten ur sina planer.",
                        "forced": "K-114 har tvingats till ytan av jagarna. Besättningen tas "
                                  "till fånga.",
                        "neutral_sunk": "K-114 har sänkt ett neutralt fartyg. Huvudstaben kallar "
                                        "hem befälhavaren för att stå till svars.",
                        "lost": "K-114 är förlorad norr om Kuba med hela besättningen.",
                        "quit": "Kaptenen har avbrutit. K-114 lämnar kvadrat 14.",
                    })


def _start_first(theatre: Theatre, world: World, far: tuple[float, float],
                 north: bool = False) -> None:
    """Den första uppgiften, konvojen i ordern, så här långt bort (den korta: närmare och
    norrifrån, mot Kuba i syd–sydväst)."""
    rules = theatre.tdef
    theatre.tdef = replace(rules, far_nm=far, **({"course": (180.0, 230.0)} if north else {}))
    theatre.start(world, "anfall")
    theatre.tdef = rules


def war_short_scenario(rng: random.Random) -> Scenario:
    """Krigspatrullen, kort: vakten har följt den första konvojen i 35 minuter. När den är avgjord
    kallar staben hem oss vid nästa sambandstillfälle (var 30:e minut); vägen ut är kort."""
    tdef = TheatreDef(max_tasks=1, recall_after_s=WAR_SHORT_RECALL_S,
                      passed_nm=WAR_SHORT_PASSED_NM)
    windows = [WAR_SHORT_WINDOW_FIRST_S + i * WAR_SHORT_WINDOW_EVERY_S for i in range(5)]
    sc = war_scenario(rng, tdef, first_far=WAR_SHORT_FAR_NM, windows=windows,
                      limit_s=WAR_SHORT_LIMIT_S, size=WAR_SHORT_SIZE, short=True)
    sc.warmup = Warmup(WAR_SHORT_WARM_S, _convoy_watch_pilot)
    sc.secret_order += ("\nVAKTJOURNALEN, 07.05: VAKTHAVANDE HAR GÅTT PÅ\n"
                        "PERISKOPDJUP SEDAN 06.30 OCH FÖLJT KONVOJEN.\n"
                        "KAPTENEN TAR BEFÄLET.\n")
    return sc
