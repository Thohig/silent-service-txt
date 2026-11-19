"""Konvojen (konvoj), den korta varianten (konvoj-kort) och motanfallet (konvoj-mot)."""
from __future__ import annotations

import math
import random
from typing import Any

from ..air import AirPatrol
from ..convoy import ConvoyDef, make_convoy, make_escorts
from ..environment import Environment
from ..geo import bearing_to, distance
from ..goals import StrikeGoal
from ..ownship import OwnShip
from ..reports import Quality
from ..seabed import kuba_seabed
from ..ship import ShipState
from ..traffic import TrafficGenerator
from ..world import World
from .common import CONVOY_PLACE, RadioMessage, Scenario, Warmup, _compass, _crew, _place
from .kuba import KUBA_AIR, KUBA_TRAFFIC

CONVOY_ORDER = """\
STRÄNGT HEMLIGT — ENDAST FÖR BEFÄLHAVAREN
FRÅN: MARINENS HUVUDSTAB, MOSKVA
TILL: BEFÄLHAVARE, UBÅT K-114
DATUM: 28 OKTOBER 1962

1. KARANTÄNLINJEN HAR BRUTITS. AMERIKANSKA
   STYRKOR FÖRBEREDER LANDSTIGNING PÅ KUBA.
2. EN KONVOJ MED TRUPPTRANSPORTER OCH
   EN TANKER UNDER ESKORT ÄR RAPPORTERAD
   CIRKA {dist} SJÖMIL {dir} OM ER,
   KURS CIRKA {course}. DEN SICKSACKAR.
3. ANFALL KONVOJEN MED KONVENTIONELLA
   TORPEDER. SÄNK MINST ETT FARTYG.
   BRYT SEDAN KONTAKTEN.
4. KÄRNVAPEN FÅR INTE ANVÄNDAS.
   NEUTRAL SJÖFART FÅR INTE ANGRIPAS.

SLUT
"""

CONVOY_RADIO = [
    RadioMessage("FRÅN HUVUDSTABEN. KONVOJEN HAR SETTS AV SPANINGSFLYG. INGEN ÄNDRING I ORDERN."),
    RadioMessage("FRÅN HUVUDSTABEN. KÄRNVAPEN FÅR INTE ANVÄNDAS.", {"nuclear_authorized": False}),
]


def convoy_scenario(rng: random.Random, run_in_nm: tuple[float, float] = (16.0, 20.0),
                    side_nm: tuple[float, float] = (1.5, 5.0)) -> Scenario:
    """Konvojen: krig, en eskorterad konvoj sicksackar förbi; sänk ett fartyg och kom undan."""
    start_clock = 6 * 3600 + 30 * 60                   # 06:30, just efter gryningen
    size = 20.0
    env = Environment(clock_start=start_clock, sea_state=5, **_place(CONVOY_PLACE))   # hård vind
    ox, oy = size / 2, rng.uniform(5.0, 8.0)
    own = OwnShip(ShipState(x=ox, y=oy, course=0, speed=4, depth=60, max_depth=400))
    world = World(own=own, env=env, rng=random.Random(rng.random()), size_nm=size,
                  patrol_end=4 * 3600)
    # konvojen kommer från nordnordost; dess väg passerar oss på 1,5–5 nm
    base = rng.uniform(190.0, 230.0)
    ux, uy = math.sin(math.radians(base)), math.cos(math.radians(base))
    nx, ny = uy, -ux
    side = rng.choice((-1.0, 1.0)) * rng.uniform(*side_nm)
    run_in = rng.uniform(*run_in_nm)
    cx, cy = ox + side * nx - run_in * ux, oy + side * ny - run_in * uy
    convoy = make_convoy(world, ConvoyDef(start=(cx, cy), base_course=base),
                         random.Random(rng.random()))
    make_escorts(world, convoy, random.Random(rng.random()))
    world.mission["nuclear_authorized"] = False
    world.goals.append(StrikeGoal([v.id for v in convoy.vessels], "convoy_attacked",
                                  "convoy_missed", clear_s=600, miss_nm=8.0))
    traffic = TrafficGenerator(KUBA_TRAFFIC, random.Random(rng.random()))
    traffic.populate(world)
    world.spawners.append(traffic)
    world.spawners.append(AirPatrol(KUBA_AIR, random.Random(rng.random()), area=size))

    # huvudstabens rapport: läget med några sjömils fel, kursen avrundad
    rx, ry = cx + rng.gauss(0, 2.0), cy + rng.gauss(0, 2.0)
    order = CONVOY_ORDER.format(dist=round(distance(ox, oy, rx, ry)),
                                dir=_compass(bearing_to(ox, oy, rx, ry)),
                                course=f"{int(round(base / 10.0) * 10) % 360:03d}")
    windows = [(c - start_clock) for c in (7 * 3600 + 30 * 60, 9 * 3600)]
    sb_rng = random.Random(rng.random())
    env.seabed = kuba_seabed(sb_rng, (ox, oy), size)
    chart = env.seabed.chart_copy(sb_rng, err_nm=0.5)
    return Scenario(world, _crew(), order, start_clock,
                    radio_windows=windows, radio_messages=list(CONVOY_RADIO),
                    chart_seabed=chart, area_name="kvadrat 12", tasks=("anfall",),
                    outcome_text={
                        "convoy_attacked": "K-114 har sänkt fartyg ur konvojen och brutit kontakten. "
                                           "Bakom er brinner det på horisonten.",
                        "convoy_missed": "Konvojen har passerat. K-114 kom aldrig till skott. "
                                         "Trupperna når Kuba.",
                        "patrol_end": "Tiden är ute. Konvojen är borta och K-114 har inte "
                                      "fullgjort ordern.",
                        "sank": "Hela konvojen och dess eskort är sänkta. Kriget till sjöss har "
                                "börjat på allvar.",
                        "forced": "K-114 har tvingats till ytan av eskortjagarna. Besättningen "
                                  "tas till fånga.",
                        "neutral_sunk": "K-114 har sänkt ett neutralt fartyg. Huvudstaben kallar "
                                        "hem befälhavaren för att stå till svars.",
                        "lost": "K-114 är förlorad norr om Kuba med hela besättningen.",
                        "quit": "Kaptenen har avbrutit. K-114 lämnar kvadrat 12.",
                    })


# --- korta varianter ------------------------------------------------------------
CONVOY_SHORT_WARM_S = 35 * 60          # vakten före kaptenen: 06:30–07:05
CONVOY_SHORT_LIMIT_S = 45 * 60         # sedan så här länge innan tiden är ute
CONVOY_SHORT_LOOK_S = 240              # vakten tittar i periskopet så här ofta


def _convoy_watch_pilot(game: Any, t: int) -> None:
    """Vakten före kaptenen: periskopdjup i 3 knop, ett svep var 4:e minut, inget anfall."""
    if t == 0:
        game.command("periskopdjup, fart 3")
    elif t % CONVOY_SHORT_LOOK_S == CONVOY_SHORT_LOOK_S // 2 \
            and game.world.own.state.depth <= 18:
        game.command("periskop")


def convoy_short_scenario(rng: random.Random) -> Scenario:
    """Konvojen, kort: vakten har följt konvojen i 35 minuter och plottet har den.
    Kaptenen tar över med konvojen 5–9 nm bort och eskorten ovetande."""
    sc = convoy_scenario(rng, run_in_nm=(13.0, 15.0))
    sc.warmup = Warmup(CONVOY_SHORT_WARM_S, _convoy_watch_pilot)
    sc.world.patrol_end = CONVOY_SHORT_WARM_S + CONVOY_SHORT_LIMIT_S
    sc.secret_order += ("\nVAKTJOURNALEN, 07.05: VAKTHAVANDE HAR GÅTT PÅ\n"
                        "PERISKOPDJUP SEDAN 06.30 OCH FÖLJT KONVOJEN.\n"
                        "KAPTENEN TAR BEFÄLET.\n")
    return sc


COUNTER_MAX_WARM_S = 15 * 60          # vakten lämnar över senast så här långt in
COUNTER_LIMIT_S = 30 * 60             # efter överlämnandet
COUNTER_LOOK_S = 60                   # periskoptitt så här ofta före salvan
COUNTER_RUN_IN_NM = (1.0, 2.0)        # konvojens ledpunkt så långt före tvärs vid start
COUNTER_SIDE_NM = (1.8, 2.4)          # vi ligger så långt vid sidan av baskursen
COUNTER_LEASH_NM = 6.0                # eskortens koppel från konvojen (annars 4)
COUNTER_WAKE_SIGMA_NM = 0.1          # eskortens datum ur torpedbanorna
COUNTER_FIRE_NM = 2.5                 # vakten skjuter på ett stort fartyg så här nära
COUNTER_MIN_SPAN_S = 60               # med minst så lång plottning sedan målets senaste gir
COUNTER_LOOK_FRESH_S = 60             # och en periskoptitt (kurs och fart) så här färsk
COUNTER_MAX_KN = 20.0                 # och en rimlig fart (snabbare: plottet har blandat ihop)
COUNTER_HANDOVER_S = 45               # kaptenen tar över så här långt före beräknad träff


class _CounterattackWatch:
    """Vakten före kaptenen i Motanfallet: periskopdjup, korta tittar (svep tills plottet har
    ett stort fartyg), och salvan mot det
    första stora fartyget inom COUNTER_FIRE_NM med en lösning minst osäker. Kaptenen tar
    befälet när torpedrummets gångtid säger att torpederna är framme om ~45 s.
    Allt går via order och besättningens kunskap; ingen torped läggs in i världen."""

    def __init__(self) -> None:
        self.handover_t: int | None = None

    def __call__(self, game: Any, t: int) -> bool:
        from ..stations.officer import is_big_ship
        from ..stations.torpedo_room import TorpedoRoom
        if self.handover_t is not None:
            if t >= self.handover_t:
                game.world.patrol_end = game.now + COUNTER_LIMIT_S
                self._wakes_seen(game.world)
                return True
            return False
        if t == 0:
            game.command("periskopdjup, fart 3")
            return False
        if t >= COUNTER_MAX_WARM_S - 1:
            game.world.patrol_end = game.now + COUNTER_LIMIT_S
            return True
        own = game.world.own.state
        torp = game.station(TorpedoRoom)
        if t % COUNTER_LOOK_S == 0 and own.depth <= 18:
            # en kort titt mot närmaste stora fartyg (mäts i hög förstoring), annars ett svep
            big = [(sol.range_nm, tr.designation) for tr in game.knowledge.tracks.values()
                   if tr.held and is_big_ship(tr)
                   and (sol := torp._solution_for(tr.designation)[1]) is not None]
            game.command(f"periskop {min(big)[1]}" if big else "periskop")
        best = None
        for tr in game.knowledge.tracks.values():
            if not tr.held or not is_big_ship(tr):
                continue
            _, sol = torp._solution_for(tr.designation)
            looked = any(o.course_obs is not None and o.t >= tr.tma_from_t
                         and t - o.t <= COUNTER_LOOK_FRESH_S for o in tr.observations)
            if sol is None or sol.quality < Quality.GOD or sol.span_s < COUNTER_MIN_SPAN_S \
                    or not looked or sol.speed > COUNTER_MAX_KN or sol.range_nm > COUNTER_FIRE_NM:
                continue
            aim = torp._aim(sol, "53-61")
            if aim is None:
                continue
            if best is None or aim[1] < best[1]:
                best = (tr.designation, aim[1])
        if best is None:
            return False
        game.command(f"salva {best[0]}")
        game.command(f"salva {best[0]}")       # torpedrummet frågar en gång om målet
        if game.world.mission.get("hostile_act"):
            self.handover_t = t + max(0, int(best[1]) - COUNTER_HANDOVER_S)
        return False


    @staticmethod
    def _wakes_seen(world: Any) -> None:
        """Startläget (sanning): utkiken på närmaste eskort har sett torpedbanorna i
        dagsljuset och följer dem tillbaka mot avfyringsplatsen."""
        from ..convoy import EscortAI
        escorts = [a for a in world.ais if isinstance(a, EscortAI) and not a.vessel.sunk]
        if not escorts or any(world._hunting_us(a) for a in escorts):
            return
        ai = min(escorts, key=lambda a: world.true_range(a.vessel))
        o = world.own.state
        ai.start_hunt(o.x + ai.rng.gauss(0, COUNTER_WAKE_SIGMA_NM),
                      o.y + ai.rng.gauss(0, COUNTER_WAKE_SIGMA_NM), 30.0,
                      COUNTER_WAKE_SIGMA_NM, t=world.time, contact=True)


def convoy_counter_scenario(rng: random.Random) -> Scenario:
    """Motanfallet: vakten har skjutit en salva mot konvojen; torpederna är framme om
    en knapp minut och eskorten vänder mot oss."""
    sc = convoy_scenario(rng, run_in_nm=COUNTER_RUN_IN_NM, side_nm=COUNTER_SIDE_NM)
    sc.warmup = Warmup(COUNTER_MAX_WARM_S, _CounterattackWatch())
    from ..convoy import EscortAI
    for ai in sc.world.ais:
        if isinstance(ai, EscortAI):        # anfallen konvoj: eskorten följer längre efter
            ai.leash_nm = COUNTER_LEASH_NM
    sc.world.patrol_end = COUNTER_MAX_WARM_S + COUNTER_LIMIT_S
    sc.secret_order += ("\nVAKTJOURNALEN: VAKTHAVANDE HAR FÖLJT KONVOJEN PÅ\n"
                        "PERISKOPDJUP OCH SKJUTIT EN SALVA. TORPEDERNA\n"
                        "ÄR PÅ VÄG. KAPTENEN TAR BEFÄLET.\n")
    sc.outcome_text["convoy_missed"] = ("Salvan missade och konvojen har passerat. Trupperna "
                                        "når Kuba.")
    sc.outcome_text["patrol_end"] = ("Tiden är ute. Eskorten har fortfarande K-114 och "
                                     "konvojen är borta.")
    return sc
