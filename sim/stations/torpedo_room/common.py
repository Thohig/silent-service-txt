"""Torpedrummets konstanter, order, tuber och torpeder i vattnet."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ...orders import Order, Unknown


N_TUBES = 8
CONFIRM_S = 60          # en upprepad eldorder inom så här lång tid verkställs
NEUTRAL_LANE_NM = 0.5   # ett känt handelsfartyg så nära en torpedbana (enligt plottet): varna
NEUTRAL_CONE_DEG = 10.0  # ... eller, utan lösning, med bäringen så nära banan
NEUTRAL_STEP_S = 10      # banan prövas så här tätt
SALVO_MAX = 3
SALVO_GAP_NM = 0.08     # torpederna i en salva går minst så här långt isär vid målet (~150 m)
SALVO_GAP_MAX_NM = 0.25 # ... och högst så här (lägesfelet vid målet bestämmer)
SALVO_STEP_DEG = (1.0, 10.0)
RELOAD_S = 300
RELOAD_QUIET_S = 480    # jagade eller på smygmotorn: minören laddar försiktigt
RELOAD_CLANK_S = 30     # torpeden körs in i tuben så här länge efter ordern; sedan stängs bakluckan
MAX_LAUNCH_DEPTH = 100         # 627A: tuberna sköt från ungefär 100 m
MAX_LAUNCH_SPEED = 12
RUN_REPORT_AFTER = 10       # s efter avfyring innan sonar bekräftar normal gång
TRACK_KEEP_S = 1800              # avslutade banor ligger kvar på kortet så länge
TRACK_FADE_S = 600
DECOY_SUGGEST_S = 1200      # skenmål föreslås högst så här ofta under en jakt
END_GRACE_S = 30            # marginal efter räckvidden innan vi säger trolig miss
GUIDE_STEP_S = 20           # trådstyrning: eldledningen räknar om kursen så här ofta
GUIDE_MIN_DEG = 2.0         # ... och skickar en styrorder när den skiljer så här mycket
SEEKER_ON_NM = 0.6          # målsökaren släpps när torpeden (beräknat) är så här nära målet
WIRE_WARN_TURN = 60.0       # grader från kursen vid skottet: varna för tråden (av vid 90)

TYPE_ALIASES = {
    "53-61": "53-61", "53": "53-61", "rak": "53-61", "raka": "53-61",
    "set-53": "SET-53", "set53": "SET-53", "set": "SET-53", "målsökande": "SET-53",
    "malsokande": "SET-53",
    "övning": "övning", "ovning": "övning", "övningstorped": "övning", "ovningstorped": "övning",
    "53-62t": "53-62T", "53-62": "53-62T", "tråd": "53-62T", "trad": "53-62T",
    "trådstyrd": "53-62T", "tradstyrd": "53-62T",
    "t-5": "T-5", "t5": "T-5", "kärn": "T-5", "karn": "T-5", "kärnladdning": "T-5",
}


@dataclass(frozen=True)
class FireTube(Order):
    tube: int
    designation: str | None = None
    course: float | None = None
    offset: float = 0.0           # salva: vinkel från skjutlösningens kurs
    in_salvo: bool = False        # salvan varnar för sicksacken en gång för alla torpeder


@dataclass(frozen=True)
class FireAt(Order):
    """Eld mot en kontakt: torpedrummet väljer tub (aldrig kärnladdningen)."""
    designation: str


@dataclass(frozen=True)
class TorpedoReport(Order):
    """Tuberna och, om några går, torpederna i vattnet."""


@dataclass(frozen=True)
class FireSalvo(Order):
    """Salva raka torpeder i solfjäder mot en kontakt; torpedrummet lägger spridningen."""
    designation: str
    tubes: tuple[int, ...] | None = None    # None: de laddade raka tuberna, högst SALVO_MAX


@dataclass(frozen=True)
class CutWire(Order):
    """Kapa tråden till de trådstyrda torpederna (eller den från en tub): målsökaren tar över."""
    tube: int | None = None


@dataclass(frozen=True)
class LoadTube(Order):
    tube: int
    type: str


@dataclass(frozen=True)
class TubeStatus(Order):
    pass


@dataclass(frozen=True)
class TorpedoStatus(Order):
    pass


@dataclass(frozen=True)
class FiringSolution(Order):
    designation: str | None


@dataclass(frozen=True)
class LaunchDecoy(Order):
    pass


def load_order(m: re.Match) -> Order:
    t = TYPE_ALIASES.get(m[2])
    if t is None:
        return Unknown("", "okänd torpedtyp, välj 53-61, SET-53, 53-62T eller T-5")
    return LoadTube(int(m[1]), t)


@dataclass
class Tube:
    n: int
    load: str | None = None
    loading: str | None = None
    ready_t: int = 0
    quiet: bool = False           # försiktig omladdning: svagare slammer, längre tid
    clanked: int = 0              # så många slammer som hörts av den här omladdningen


@dataclass
class Running:
    """En torped i vattnet, så som torpedrummet känner till den."""
    no: int                       # avfyrningsordning, samma som sonarens
    tube: int
    type: str
    designation: str | None
    course: float
    launch_t: int
    t_hit: int | None             # beräknad träfftid (bara mot kontakt)
    t_end: int                    # när räckvidden är slut
    bearing: float | None = None
    heard_t: int | None = None
    lost: bool = False
    turned: bool = False
    confirmed: bool = False
    timed: bool = False
    launch_x: float = 0.0         # vårt beräknade läge vid avfyringen: banan börjar där
    launch_y: float = 0.0
    end_t: int | None = None      # när torpedrummet räknade den som slut
    end: str = ""                 # hit, silent, timeout
    # trådstyrd: eldledningens styrorder (tid, kurs) från skottet; banan räknas ur dem
    legs: list[tuple[int, float]] | None = None
    wired: bool = False           # tråden håller (så vitt torpedrummet vet)
    seeker_on: bool = False       # målsökaren släppt
    wire_end_t: int | None = None
    strain_said: str = ""         # varningen för tråden som redan sagts ("fart", "gir")
    no_solution_said: bool = False
