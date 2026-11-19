"""Sundet vid Guantánamo: spaningen (sundet), in (sundet-in) och ut (sundet-ut)."""
from __future__ import annotations

import random
from typing import Any

from ..entities import Vessel
from ..environment import Environment, TidalStream
from ..goals import EscapeGoal, PhotoGoal
from ..ownship import OwnShip
from ..reports import Quality
from ..seabed import strait_seabed
from ..ship import ShipState
from ..traffic import Lane, TrafficDef, TrafficGenerator
from ..world import World
from .common import GUANTANAMO_PLACE, RadioMessage, Scenario, Warmup, _crew, _place

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
    RadioMessage("FRÅN HUVUDSTABEN. INGEN ÄNDRING.", {"nuclear": "order_only"}),
]

HARBOR_PATROL_SPEED = 6.0


def strait_scenario(rng: random.Random, short: bool = False, out: bool = False) -> Scenario:
    """Genom sundet: smyg in mot en flottbas, fotografera ankarplatsen, ta dig ut.

    short (`sundet-in`): 06:20, vi ligger vid väntläget och ett fartyg är på väg in;
    målet är bara fotot (se strait_in_scenario). out (`sundet-ut`): 07:00 innanför nätet,
    ett fartyg på väg ut; ute = vid skärmens inre kant (se strait_out_scenario)."""
    from ..harbor import HarborDefense, HydrophoneLine, Net, PatrolBoatAI, hydrophone_points
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
    env = Environment(clock_start=start_clock, sea_state=2, background_noise=66.5, current_set=270.0,  # 64 dB vid sjö 2
                      current_kn=0.2, seabed=seabed, tide=tide, **_place(GUANTANAMO_PLACE))
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

    margin = 0.5
    escape = EscapeGoal(margin, "recon_done", requires_photo=int(Quality.GOD))
    if not short:
        world.goals.append(escape)
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
        world.goals.append(PhotoGoal(int(Quality.GOD), "photo_taken"))   # ingen utväg
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
        escape.y_below = net_y - STRAIT_OUT_LINE_NM
        world.patrol_end = STRAIT_OUT_WARM_S + STRAIT_OUT_LIMIT_S
    windows = [(c - start_clock) for c in (6 * 3600 + 30 * 60, 8 * 3600) if c > start_clock + 3600]
    known = [("Ankarplatsen", ax + rng.gauss(0, 0.2), ay + rng.gauss(0, 0.2), 0.4, 0),
             ("Nätet", cx + rng.gauss(0, 0.05), net_y + rng.gauss(0, 0.15), 0.2, 0)]
    return Scenario(world, _crew(), STRAIT_ORDER, start_clock,
                    radio_windows=windows, radio_messages=list(STRAIT_RADIO),
                    known_positions=known, chart_seabed=chart,
                    tide_table=tide.table_copy(random.Random(rng.random())),
                    area_name="inloppet", escape_margin_nm=None if short else margin,
                    tasks=("ut",) if out else ("foto",) if short else ("foto", "ut"),
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
    sc.escape_y_below = sc.world.goal(EscapeGoal).y_below
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
