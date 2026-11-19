"""Övningen i Kolafjorden (ovning) och den korta varianten (ovning-kort)."""
from __future__ import annotations

import random
from typing import Any

from ..environment import Environment, TidalStream
from ..exercise import make_exercise_ship
from ..geo import bearing_to, offset_starboard
from ..goals import GroundingFails, NoDiveInFjord, TrainingGoal
from ..ownship import OwnShip
from ..seabed import kola_seabed
from ..ship import ShipState
from ..traffic import Lane, TrafficDef, TrafficGenerator
from ..world import World
from .common import KOLA_PLACE, Scenario, Warmup, _crew, _place

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
   LYSSNINGSÖVNING, ÖVNINGSTORPED,
   UPPSTIGNING.
   ANMÄL NÄR DET ÄR KLART.
4. BEVAKNINGSFARTYGET SKR-112 ÖVAR I
   OMRÅDET SOM MÅL FÖR LYSSNINGEN.
5. INGA SKARPA VAPEN. TUB 1 OCH 2
   LADDADE MED ÖVNINGSTORPEDER.

SLUT
"""

TRAINING_CLOCK = 10 * 3600
TRAINING_SIZE = 16.0
TRAINING_AREA = "Övningsområdet"
TRAINING_AREA_OUT_NM = 4.5          # övningsområdet så långt norr om mynningen
TRAINING_STEPS = ("dyk", "svep", "fix", "framme", "djup100", "provdjup", "smyg", "lyssna", "torped",
                  "pd", "upp")
TRAINING_ARMAMENT = {"tubes": {1: "övning", 2: "övning"}, "inventory": {"övning": 0}}
TRAINING_SHIP_R_NM = 3.0            # bevakningsfartyget håller sig inom så här långt från området
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
    env = Environment(clock_start=TRAINING_CLOCK, sea_state=2, background_noise=64.5, current_set=270.0,  # 62 dB vid sjö 2
                      current_kn=0.1, seabed=seabed, tide=tide, **_place(KOLA_PLACE, 3.0))
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
    ship, ship_ai = make_exercise_ship(random.Random(rng.random()), (area_x, area_y),
                                       TRAINING_SHIP_R_NM)
    world.contacts.append(ship)
    world.ais.append(ship_ai)
    world.goals += [TrainingGoal("training_done"), NoDiveInFjord("dived_in_fjord"),
                    GroundingFails("grounded")]
    # farleden enligt kortet: från första punkten framför oss ut genom mynningen
    fairway = [p for p in cfj.path if p[1] > TRAINING_START_Y + 0.3]
    known = [(TRAINING_AREA, area_x, area_y, 0.1, 0),
             ("Poljarnyj", ax - fj.half_w[0] - 0.4, TRAINING_START_Y, 0.05, 0)]
    return Scenario(world, _crew(), TRAINING_ORDER, TRAINING_CLOCK,
                    known_positions=known, chart_seabed=chart,
                    tide_table=tide.table_copy(random.Random(rng.random())),
                    area_name="Kolafjorden", fairway=fairway, fairway_to=TRAINING_AREA,
                    training=TRAINING_STEPS, training_area=TRAINING_AREA, no_dive_in_fjord=True,
                    armament=TRAINING_ARMAMENT, tasks=("övning",), nuclear_order="forbidden",
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
                        "neutral_sunk": "Ett sovjetiskt fartyg har sänkts under övningen. "
                                        "Befälhavaren kallas till staben.",
                        "quit": "Kaptenen har avbrutit övningen. K-114 går tillbaka till "
                                "Poljarnyj.",
                        "lost": "K-114 är förlorad i Barents hav med hela besättningen.",
                    })



TRAINING_SHORT_WARM_S = 4 * 60        # vakten: periskopsvep och fix i övningsområdet
TRAINING_SHORT_LIMIT_S = 60 * 60      # sedan så här länge för resten av programmet
TRAINING_SHORT_STEPS = ("djup100", "provdjup", "smyg", "lyssna", "torped", "pd", "upp")


def _training_watch_pilot(game: Any, t: int) -> None:
    """Vakten i övningsområdet: periskopsvep, sedan en fix på kustens landmärken."""
    if t == 5:
        game.command("periskop")
    elif t == 60:
        game.command("fix")


def training_short_scenario(rng: random.Random) -> Scenario:
    """Övningen, kort: K-114 ligger redan på periskopdjup i övningsområdet."""
    sc = training_scenario(rng)
    w = sc.world
    r2 = random.Random(rng.random())
    a = next(k for k in sc.known_positions if k[0] == TRAINING_AREA)
    o = w.own.state
    o.x, o.y = a[1] + r2.uniform(-0.4, 0.4), a[2] + r2.uniform(-0.4, 0.4)
    o.depth = o.ordered_depth = 17.0
    o.speed = o.ordered_speed = 4.0
    o.course = o.ordered_course = r2.uniform(0, 360)
    w.own.sys.bridge = "shut"
    sc.training = TRAINING_SHORT_STEPS
    sc.warmup = Warmup(TRAINING_SHORT_WARM_S, _training_watch_pilot)
    w.patrol_end = TRAINING_SHORT_WARM_S + TRAINING_SHORT_LIMIT_S
    sc.secret_order += ("\nVAKTJOURNALEN, 11.10: K-114 LIGGER PÅ PERISKOPDJUP\n"
                        "I ÖVNINGSOMRÅDET. DYKNING, PERISKOPSVEP OCH FIX\n"
                        "ÄR GENOMFÖRDA. KAPTENEN TAR BEFÄLET FÖR RESTEN\n"
                        "AV PROGRAMMET.\n")
    sc.outcome_text["patrol_end"] = ("Tiden är ute innan programmet var genomfört; staben i "
                                     "Severomorsk vill ha en förklaring.")
    return sc
