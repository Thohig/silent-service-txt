"""Torpedrum och eldledning: tuber, laddning, skjutlösningar, avfyring och skenmål.

Eldledningen räknar bara på kunskap: plottlagets lösning och navigatörens
bestick. Avfyring kräver alltid en uttrycklig order; torpedofficeren
meddelar när en skjutlösning finns men föreslår aldrig avfyring som en
order som kan godkännas med "ja".

Torpeder i vattnet följs via sonaren (OwnTorpedoHeard): normal gång,
sväng (målsökning), tappad, detonation och tystnad utan detonation. Hörs
ingenting innan räckvidden är slut rapporteras en trolig miss. Sonaren
numrerar egna torpeder i avfyrningsordning; torpedrummet gör detsamma
och knyter numret till tuben. Alla torpeder avfyras därför här.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .. import phrases
from ..chart import LAYER_RAY, Mark, Ray, Track
from ..crew import Role
from ..events import OwnSoundMade, OwnTorpedoHeard, SoundHeard
from ..fmt import fmt_course, nm
from ..geo import angle_diff
from .. import russian as R
from ..russian import ru
from ..firecontrol import intercept
from ..orders import DESIG, NUM, CommandSpec, Order, Unknown, desig, num
from ..reports import Quality
from ..systems import INFO, OK, WARN, Gauge, TubeRack
from ..weapons import TORPEDO_TYPES, launch_decoy, launch_torpedo
from .base import Proposal, Station

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
MAX_LAUNCH_DEPTH = 100         # 627A: tuberna sköt från ungefär 100 m
MAX_LAUNCH_SPEED = 12
RUN_REPORT_AFTER = 10       # s efter avfyring innan sonar bekräftar normal gång
TRACK_KEEP_S = 1800              # avslutade banor ligger kvar på kortet så länge
TRACK_FADE_S = 600
END_GRACE_S = 30            # marginal efter räckvidden innan vi säger trolig miss

TYPE_ALIASES = {
    "53-61": "53-61", "53": "53-61", "rak": "53-61", "raka": "53-61",
    "set-53": "SET-53", "set53": "SET-53", "set": "SET-53", "målsökande": "SET-53",
    "malsokande": "SET-53",
    "övning": "övning", "ovning": "övning", "övningstorped": "övning", "ovningstorped": "övning",
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
class FireSalvo(Order):
    """Salva raka torpeder i solfjäder mot en kontakt; torpedrummet lägger spridningen."""
    designation: str
    tubes: tuple[int, ...] | None = None    # None: de laddade raka tuberna, högst SALVO_MAX


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


def _load(m: re.Match) -> Order:
    t = TYPE_ALIASES.get(m[2])
    if t is None:
        return Unknown("", "okänd torpedtyp, välj 53-61, SET-53 eller T-5")
    return LoadTube(int(m[1]), t)


@dataclass
class Tube:
    n: int
    load: str | None = None
    loading: str | None = None
    ready_t: int = 0


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


def _mmss(s: float) -> str:
    s = int(round(s))
    return f"{s // 60} min {s % 60:02d} s"


def _tubes(d: dict) -> str:
    parts = []
    for t in d["tubes"]:
        if t["loading"]:
            parts.append(f"{t['n']}: laddas {t['loading']}")
        else:
            parts.append(f"{t['n']}: {t['load'] or 'tom'}")
    inv = ", ".join(f"{k} {v}" for k, v in d["inventory"].items())
    return "Tuber – " + ", ".join(parts) + f". I förråd: {inv}. Skenmål: {d['decoys']}."


def _in_water(d: dict) -> str:
    if not d["running"]:
        return "Inga torpeder i vattnet."
    rows = []
    for r in d["running"]:
        aim = f" mot {r['designation']}" if r["designation"] else f", kurs {fmt_course(r['course'])}"
        s = f"tub {r['tube']} ({r['type']}{aim}): gått {_mmss(r['elapsed'])}"
        if r.get("to_hit") is not None:
            s += (f", beräknad träff om {_mmss(r['to_hit'])}" if r["to_hit"] > 0
                  else ", beräknad träfftid passerad")
        s += f", räckvidden slut om {_mmss(r['to_end'])}"
        if r["bearing"] is None:
            s += ", sonar hör den inte"
        elif r["lost"]:
            s += f", sonar har tappat den (sista bäring {fmt_course(r['bearing'])})"
        else:
            s += f", hörs i bäring {fmt_course(r['bearing'])}"
        if r["turned"]:
            s += ", har svängt, troligen målsökt"
        rows.append(s)
    return "Torpeder i vattnet – " + "; ".join(rows) + "."


def _solution(d: dict) -> str:
    rows = []
    for r in d["rows"]:
        if r.get("blocked"):
            rows.append(f"{r['type']}: {r['blocked']}")
        elif r.get("course") is None:
            rows.append(f"{r['type']}: utom räckhåll")
        else:
            rows.append(f"{r['type']}: kurs {fmt_course(r['course'])}, gångtid {_mmss(r['run_s'])}")
    return (f"Skjutlösning {d['designation']} (lösning {Quality(d['quality']).label}): "
            + "; ".join(rows) + ".")


PHRASES = {
    "torp.refused": lambda d: f"Kapten, {d['reason']}.",
    "torp.confirm": lambda d: (
        f"Kapten, {d['designation']} är klassad som {d['classification']}. "
        if d["civil"] else
        f"Kapten, {d['designation']} är inte säkert klassad som örlogsfartyg, "
        f"bara {d['classification']}. ") + "Upprepa ordern om vi ska skjuta.",
    "torp.neutral": lambda d: "Kapten, torpedrummet. Varning: "
    + ", ".join(f"{n['designation']} ({n['classification']}, bäring {fmt_course(n['bearing'])}"
                + (f", {nm(n['range'])} sjömil" if n.get("range") is not None else ", avståndet okänt")
                + ")" for n in d["ships"])
    + " ligger nära torpedernas bana. En rak torped som missar går vidare och kan träffa."
    + ("" if d.get("preview") else " Upprepa ordern om vi ska skjuta."),
    "torp.fired": lambda d: f"{ru('Torpeda vysjla')}! Tub {d['tube']} avfyrad, {d['type']}, kurs {fmt_course(d['course'])}"
    + (f", beräknad gångtid {_mmss(d['run_s'])}" if d.get("run_s") else "")
    + (". Lösningen var dålig, risk för miss." if d.get("quality") == Quality.DALIG else "."),
    "torp.salvo": lambda d: f"Salva mot {d['designation']}: {d['n']} torpeder i solfjäder, "
    f"{nm(d['step'])} grader isär.",
    "torp.leg_warning": lambda d: f"Kapten, torpedrummet. Varning: {d['designation']} sicksackar. "
    f"Benet har gått {round(d['elapsed_s'] / 60)} minuter av ungefär {round(d['leg_s'] / 60)}, och en "
    f"{d['type']} är framme om {_mmss(d['run_s'])}. Konvojen kan ha girat innan dess."
    + (" Den målsökande torpeden söker själv efter giren." if d.get("homing") else ""),
    "torp.time": lambda d: f"Tid för torpeden från tub {d['tube']}"
    + (f" mot {d['designation']}" if d.get("designation") else "") + "!",
    "torp.loading": lambda d: f"Laddar tub {d['tube']} med {d['type']}. Fem minuter.",
    "torp.loaded": lambda d: f"Tub {d['tube']} laddad med {d['type']}.",
    "torp.status": _tubes,
    "torp.solution": _solution,
    "torp.decoy": lambda d: f"Skenmål ute. {d['left']} kvar.",
    "torp.ready": lambda d: f"Kapten, torped. Vi har skjutlösning på {d['designation']}: "
    f"tub {d['tube']} med {d['type']}, gångtid {_mmss(d['run_s'])}. Inväntar order.",
    "torp.suggest.reload": lambda d: f"Kapten, torped. Tub {d['tube']} är tom. "
    f"Föreslår att vi laddar {d['type']}.",
    "torp.suggest.decoy": lambda d: "Kapten, torped. Föreslår skenmål för att dra deras sonar.",
    "torp.in_water": _in_water,
    "torp.run.running": lambda d: f"Tub {d['tube']}: sonar hör torpeden i bäring "
    f"{fmt_course(d['bearing'])}, normal gång.",
    "torp.run.turned": lambda d: f"Tub {d['tube']}: torpeden svänger, nu i bäring "
    f"{fmt_course(d['bearing'])}. Målsökaren har troligen fått något.",
    "torp.run.lost": lambda d: f"Tub {d['tube']}: sonar har tappat torpeden"
    + (f", sista bäring {fmt_course(d['bearing'])}" if d.get("bearing") is not None else "") + ".",
    "torp.run.hit": lambda d: (
        f"Tub {d['tube']}: kärnladdningen har detonerat i bäring {fmt_course(d['bearing'])}."
        if d.get("nuclear") else
        f"Tub {d['tube']}: detonation i bäring {fmt_course(d['bearing'])}. Det var vår torped!"),
    "torp.run.silent": lambda d: f"Tub {d['tube']}: torpeden har tystnat"
    + (f" i bäring {fmt_course(d['bearing'])}" if d.get("bearing") is not None else "")
    + " utan detonation. Miss, kapten.",
    "torp.run.exercise_end": lambda d: f"Tub {d['tube']}: övningstorpeden har gått färdigt "
    "och flyter upp för bärgning.",
    "torp.run.timeout": lambda d: f"Tub {d['tube']}: torpedens räckvidd är slut och vi har inte "
    "hört någon detonation. Trolig miss.",
}
phrases.register(PHRASES)


def _ru_tube(d: dict) -> str:
    return f"Аппарат {d['tube']}"


RU_PHRASES = {
    "torp.fired": lambda d: f"Торпеда вышла! {_ru_tube(d)}, {R.weapon(d['type'])}, курс "
    f"{R.course(d['course'])}"
    + (f", расчётное время хода {R.mmss(d['run_s'])}" if d.get("run_s") else "")
    + (". Решение было плохое, возможен промах." if d.get("quality") == Quality.DALIG else "."),
    "torp.salvo": lambda d: f"Залп по {R.contact(d['designation'], True)}: "
    f"{R.count(d['n'], ('торпеда', 'торпеды', 'торпед'))} веером.",
    "torp.neutral": lambda d: f"{R.CAPTAIN}, торпедный отсек. Внимание: "
    + ("торговое судно" if len(d["ships"]) == 1 else "торговые суда")
    + " рядом с курсом торпед."
    + ("" if d.get("preview") else " Повторите приказ, если стреляем."),
    "torp.leg_warning": lambda d: f"{R.CAPTAIN}, торпедный отсек. Внимание: цель идёт "
    f"зигзагом, конвой может повернуть раньше, чем дойдёт торпеда.",
    "torp.time": lambda d: f"Время торпеды из аппарата {d['tube']}"
    + (f" по {R.contact(d['designation'], True)}" if d.get("designation") else "") + "!",
    "torp.loading": lambda d: f"Есть, заряжаем аппарат {d['tube']}, {R.weapon(d['type'])}. "
    "Пять минут.",
    "torp.loaded": lambda d: f"{_ru_tube(d)} заряжен, {R.weapon(d['type'])}.",
    "torp.decoy": lambda d: f"Есть, имитатор выпущен. Осталось {d['left']}.",
    "torp.ready": lambda d: f"{R.CAPTAIN}, минёр. Есть решение по {R.contact(d['designation'], True)}: "
    f"аппарат {d['tube']}, {R.weapon(d['type'])}, время хода {R.mmss(d['run_s'])}. Ждём команды.",
    "torp.suggest.reload": lambda d: f"{R.CAPTAIN}, минёр. Аппарат {d['tube']} пуст. "
    f"Предлагаю зарядить {R.weapon(d['type'])}.",
    "torp.suggest.decoy": lambda d: f"{R.CAPTAIN}, минёр. Предлагаю выпустить имитатор, "
    "чтобы отвлечь их гидролокатор.",
    "torp.run.running": lambda d: f"{_ru_tube(d)}: акустик слышит торпеду, пеленг "
    f"{R.course(d['bearing'])}, идёт нормально.",
    "torp.run.turned": lambda d: f"{_ru_tube(d)}: торпеда поворачивает, пеленг "
    f"{R.course(d['bearing'])}. Головка самонаведения, видимо, что-то захватила.",
    "torp.run.lost": lambda d: f"{_ru_tube(d)}: торпеда потеряна"
    + (f", последний пеленг {R.course(d['bearing'])}" if d.get("bearing") is not None else "") + ".",
    "torp.run.hit": lambda d: (
        f"{_ru_tube(d)}: ядерный заряд взорвался, пеленг {R.course(d['bearing'])}."
        if d.get("nuclear") else
        f"{_ru_tube(d)}: взрыв, пеленг {R.course(d['bearing'])}. Это наша торпеда!"),
    "torp.run.silent": lambda d: f"{_ru_tube(d)}: торпеда затихла"
    + (f", пеленг {R.course(d['bearing'])}" if d.get("bearing") is not None else "")
    + ", взрыва не было. Промах, товарищ командир.",
    "torp.run.exercise_end": lambda d: f"{_ru_tube(d)}: практическая торпеда прошла дистанцию "
    "и всплыла.",
    "torp.run.timeout": lambda d: f"{_ru_tube(d)}: запас хода торпеды кончился, взрыва не "
    "слышали. Вероятно, промах.",
}
phrases.register_ru(RU_PHRASES)


class TorpedoRoom(Station):
    REACHES_WORLD = True        # torpeder och skenmål i vattnet, uppdragets flaggor
    role = Role.TORPEDO
    COMMANDS = [
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+tub\s+(\d)\s+(?:mot\s+)?{DESIG}",
                    lambda m: FireTube(int(m[1]), designation=desig(m[2])), "eld tub 1 mot S-1"),
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+tub\s+(\d)\s+kurs\s+{NUM}",
                    lambda m: FireTube(int(m[1]), course=num(m[2]) % 360), "eld tub 1 kurs 045"),
        CommandSpec(r"ladda\s+tub\s+(\d)\s+(?:med\s+)?(\S+)", _load, "ladda tub 7 SET-53"),
        CommandSpec(r"tuber|torpedrum", lambda m: TubeStatus(), "tuber"),
        CommandSpec(r"torpeder|torpedläge|torpedlage|torpeder i vattnet",
                    lambda m: TorpedoStatus(), "torpeder"),
        CommandSpec(rf"(?:skjutlösning|skjutlosning|eldlösning|eldlosning)(?:\s+{DESIG})?",
                    lambda m: FiringSolution(desig(m[1])), "skjutlösning S-1"),
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+tub\s+(\d)\s*-\s*(\d)\s+(?:mot\s+)?{DESIG}",
                    lambda m: FireSalvo(desig(m[3]), tuple(range(min(int(m[1]), int(m[2])),
                                                                 max(int(m[1]), int(m[2])) + 1))),
                    "eld tub 1-3 mot S-1"),
        CommandSpec(rf"salva\s+(?:mot\s+)?{DESIG}", lambda m: FireSalvo(desig(m[1])), "salva S-1"),
        CommandSpec(r"skenmål|skenmal|motmedel", lambda m: LaunchDecoy(), "skenmål"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.tubes = [Tube(i + 1) for i in range(N_TUBES)]
        self._confirmed: dict[str, int] = {}     # kontakt -> när vi frågade om den
        self._neutral_warned: dict[str, int] = {}   # mål (eller "kurs") -> när vi varnade
        for t in self.tubes[:4]:
            t.load = "53-61"
        for t in self.tubes[4:6]:
            t.load = "SET-53"
        self.inventory = {"53-61": 6, "SET-53": 4, "T-5": 2}
        arm = getattr(game.scenario, "armament", None)
        if arm:                                   # t.ex. övningen: bara övningstorpeder
            for t in self.tubes:
                t.load = arm["tubes"].get(t.n)
            self.inventory = dict(arm["inventory"])
        self.decoys = 6
        self.in_water: list[Running] = []
        self.finished: list[Running] = []         # ritas kvar på kortet en stund
        self._launches = 0
        self._ready_said: dict[str, Quality] = {}

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(SoundHeard, self._on_sound)
        bus.subscribe(OwnTorpedoHeard, self._on_own_torpedo)


    # --- eldledning --------------------------------------------------------------
    def _solution_for(self, designation: str | None):
        k = self.game.knowledge
        tr = k.track(designation) if designation else None
        if tr is None:
            return None, None
        sol = k.resolve(tr.designation, self.now, self.game.own_position_estimate())
        return tr, sol

    def _aim(self, sol, type_key: str):
        spec = TORPEDO_TYPES[type_key]
        ex, ey = self.game.own_position_estimate()
        vx, vy = sol.state[2], sol.state[3]
        res = intercept(sol.x - ex, sol.y - ey, vx, vy, spec.speed)
        if res is None:
            return None
        course, t_h = res
        if spec.speed * t_h > spec.range_nm:
            return None
        return course, t_h * 3600, spec.speed * t_h

    def _blocked(self, type_key: str) -> str | None:
        if TORPEDO_TYPES[type_key].nuclear and not self.world.mission.get("nuclear_authorized"):
            return "kärnladdningen kräver order från Moskva"
        return None

    # --- order -------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        match order:
            case FireTube():
                self._fire(order)
            case FireSalvo():
                self._salvo(order)
            case LoadTube(tube=n, type=typ):
                self._load(n, typ)
            case TubeStatus():
                self.say("torp.status", {
                    "tubes": [{"n": t.n, "load": t.load, "loading": t.loading} for t in self.tubes],
                    "inventory": dict(self.inventory), "decoys": self.decoys})
            case TorpedoStatus():
                self._report_in_water()
            case FiringSolution(designation=d):
                self._preview(d)
            case LaunchDecoy():
                if self.decoys <= 0:
                    self.say("torp.refused", {"reason": "skenmålen är slut"})
                    return
                self.decoys -= 1
                launch_decoy(self.world)
                self.game.bus.publish(OwnSoundMade(self.now, "decoy"))
                self.say("torp.decoy", {"left": self.decoys}, kind="ack")

    def _tube(self, n: int) -> Tube | None:
        return self.tubes[n - 1] if 1 <= n <= N_TUBES else None

    def _salvo(self, o: FireSalvo) -> None:
        """Raka torpeder i solfjäder: mittersta på lösningen, de andra vid sidan."""
        tubes = list(o.tubes) if o.tubes else [
            t.n for t in self.tubes if t.load and not TORPEDO_TYPES[t.load].homing
            and not TORPEDO_TYPES[t.load].nuclear][:SALVO_MAX]
        tubes = [n for n in tubes if (t := self._tube(n)) is not None and t.load]
        if not tubes:
            self.say("torp.refused", {"reason": "inga laddade raka tuber för en salva"})
            return
        tr, sol = self._solution_for(o.designation)
        first_type = self._tube(tubes[0]).load
        aim = self._aim(sol, first_type) if sol is not None else None
        dist = aim[2] if aim else 2.0
        # lägesfelet vid målet: avståndets σ plus fartens och kursens σ under gångtiden
        gap = SALVO_GAP_NM
        if aim and sol is not None:
            run_h = aim[1] / 3600.0
            err = math.sqrt(sol.range_sigma ** 2 + (run_h * sol.speed_sigma) ** 2
                            + (run_h * sol.speed * math.radians(min(sol.course_sigma, 60))) ** 2)
            gap = min(max(err, SALVO_GAP_NM), SALVO_GAP_MAX_NM)
        step = math.degrees(math.atan2(gap, max(dist, 0.1)))
        step = min(max(step, SALVO_STEP_DEG[0]), SALVO_STEP_DEG[1])
        # hela salvan eller ingen: en tub som inte kan skjuta stoppar den innan någon gått
        for tube in tubes:
            if why := self._refusal(FireTube(tube, designation=o.designation)):
                self.say("torp.refused", {"reason": why})
                return
        n = len(tubes)
        if aim and not self._neutrals_clear(
                o.designation, [(aim[0] + (i - (n - 1) / 2) * step) % 360 for i in range(n)],
                first_type):
            return
        for i, tube in enumerate(tubes):
            off = (i - (n - 1) / 2) * step
            if not self._fire(FireTube(tube, designation=o.designation, offset=off,
                                       in_salvo=True)):
                return
        self.say("torp.salvo", {"designation": o.designation, "n": n, "step": step})
        if aim:
            self._leg_warning(o.designation, aim[1], first_type)

    def _refusal(self, o: FireTube) -> str | None:
        """Varför tuben inte kan skjuta nu (tuben, djup och fart, tillstånd, målet), annars None."""
        tube = self._tube(o.tube)
        st, sys = self.own.state, self.own.sys
        reason = None
        if tube is None:
            reason = f"det finns ingen tub {o.tube}"
        elif tube.loading:
            reason = f"tub {o.tube} laddas fortfarande"
        elif tube.load is None:
            reason = f"tub {o.tube} är tom"
        elif sys.health["tubes"] < 0.5 and o.tube <= 4:
            reason = f"tub {o.tube} är skadad"
        elif st.depth > MAX_LAUNCH_DEPTH:
            reason = f"vi är för djupt för avfyring, högst {MAX_LAUNCH_DEPTH} meter"
        elif st.speed > MAX_LAUNCH_SPEED:
            reason = f"farten är för hög för avfyring, högst {MAX_LAUNCH_SPEED} knop"
        elif b := self._blocked(tube.load):
            reason = b
        elif o.designation:
            tr, sol = self._solution_for(o.designation)
            if tr is None:
                reason = f"vi har ingen kontakt {o.designation}"
            elif sol is None:
                reason = f"plottet har ingen lösning på {o.designation}"
            elif self._aim(sol, tube.load) is None:
                reason = f"{o.designation} är utom räckhåll för {TORPEDO_TYPES[tube.load].key}"
        return reason

    def _fire(self, o: FireTube) -> bool:
        if reason := self._refusal(o):
            self.say("torp.refused", {"reason": reason})
            return False
        tube = self._tube(o.tube)
        spec = TORPEDO_TYPES[tube.load]
        quality = None
        run_s = None
        detonate_at = None
        if o.designation:
            tr, sol = self._solution_for(o.designation)
            course, run_s, dist = self._aim(sol, tube.load)
            course = (course + o.offset) % 360
            if not o.in_salvo and not self._neutrals_clear(tr.designation, [course], tube.load):
                return False
            if not tr.warship and not (spec.exercise and tr.friendly) and \
                    self._confirmed.get(tr.designation, -10**9) < self.now - CONFIRM_S:
                # torpedrummet frågar en gång; samma order inom en minut verkställs
                self._confirmed[tr.designation] = self.now
                self.say("torp.confirm", {"designation": tr.designation,
                                          "classification": tr.classification,
                                          "civil": tr.civil}, quality=tr.class_quality)
                return False
            quality = sol.quality
            if spec.nuclear:
                detonate_at = dist
        else:
            course = o.course
            if not self._neutrals_clear(None, [course], tube.load):
                return False
        launch_torpedo(self.world, spec, course, detonate_at)
        self.game.bus.publish(OwnSoundMade(self.now, "launch"))
        if not spec.exercise:
            self.world.mission["hostile_act"] = True
        tube.load = None
        self._launches += 1
        run_nm = min(detonate_at, spec.range_nm) if detonate_at else spec.range_nm
        lx, ly = self.game.own_position_estimate()
        self.in_water.append(Running(
            no=self._launches, tube=o.tube, type=spec.key, designation=o.designation,
            course=course, launch_t=self.now,
            t_hit=int(self.now + run_s) if run_s else None,
            t_end=int(self.now + run_nm / spec.speed * 3600), launch_x=lx, launch_y=ly))
        self.say("torp.fired", {"tube": o.tube, "type": spec.key, "course": course,
                                "run_s": run_s, "quality": quality},
                 kind="ack", quality=quality, alarm=True)
        if o.designation and run_s and not o.in_salvo:
            self._leg_warning(o.designation, run_s, spec.key)
        return True

    def _neutrals_in_lane(self, target: str | None, courses: list[float],
                          type_key: str) -> list[dict]:
        """Kända handelsfartyg nära någon av torpedernas banor, hela vägen ut (kunskap)."""
        spec = TORPEDO_TYPES[type_key]
        if spec.homing or spec.exercise:
            return []
        k = self.game.knowledge
        ex, ey = self.game.own_position_estimate()
        run_s = spec.range_nm / spec.speed * 3600
        out = []
        for tr in k.tracks.values():
            if not tr.held or not tr.civil or tr.designation == target or not tr.observations:
                continue
            sol = tr.solution
            if sol is not None and sol.quality >= Quality.OSAKER:
                dt0 = (self.now - sol.t) / 3600.0
                sx, sy = sol.x + sol.state[2] * dt0 - ex, sol.y + sol.state[3] * dt0 - ey
                near = False
                for c in courses:
                    b = math.radians(c)
                    for t in range(0, int(run_s) + 1, NEUTRAL_STEP_S):
                        h = t / 3600.0
                        dx = sx + sol.state[2] * h - spec.speed * h * math.sin(b)
                        dy = sy + sol.state[3] * h - spec.speed * h * math.cos(b)
                        if math.hypot(dx, dy) <= NEUTRAL_LANE_NM:
                            near = True
                            break
                    if near:
                        break
                if near:
                    out.append({"designation": tr.designation, "classification": tr.classification,
                                "bearing": math.degrees(math.atan2(sx, sy)) % 360,
                                "range": math.hypot(sx, sy)})
            else:
                b = tr.last_bearing
                lo, hi = min(courses), max(courses)
                if any(abs(angle_diff(b, c)) <= NEUTRAL_CONE_DEG for c in courses) or \
                        (hi - lo < 180 and lo <= b <= hi):
                    out.append({"designation": tr.designation, "classification": tr.classification,
                                "bearing": b, "range": None})
        return out

    def _neutrals_clear(self, target: str | None, courses: list[float], type_key: str) -> bool:
        """Varna en gång för kända handelsfartyg i banan; samma order inom en minut skjuter.
        Varningen räknas också som bekräftelse av målet (ingen andra fråga)."""
        ships = self._neutrals_in_lane(target, courses, type_key)
        key = target or "kurs"
        if not ships or self._neutral_warned.get(key, -10**9) >= self.now - CONFIRM_S:
            return True
        self._neutral_warned[key] = self.now
        if target:
            self._confirmed[target] = self.now
        self.say("torp.neutral", {"ships": ships}, quality=Quality.GOD)
        return False

    def _leg_warning(self, designation: str, run_s: float, type_key: str) -> None:
        """Ett sicksackande mål kan gira innan torpeden är framme: säg det."""
        c = self.game.knowledge.convoy
        tr = self.game.knowledge.track(designation)
        if c is None or tr is None or tr.designation not in c.members \
                or c.mean_leg_s is None or c.last_turn_t is None:
            return
        elapsed = self.now - c.last_turn_t
        left = c.mean_leg_s - elapsed
        if run_s <= left:
            return
        self.say("torp.leg_warning", {"designation": tr.designation, "elapsed_s": elapsed,
                                      "leg_s": c.mean_leg_s, "run_s": run_s, "type": type_key,
                                      "homing": TORPEDO_TYPES[type_key].homing},
                 quality=Quality.OSAKER)

    def _load(self, n: int, typ: str) -> None:
        tube = self._tube(n)
        if tube is None:
            self.say("torp.refused", {"reason": f"det finns ingen tub {n}"})
        elif tube.load or tube.loading:
            self.say("torp.refused", {"reason": f"tub {n} är inte tom"})
        elif self.inventory.get(typ, 0) <= 0:
            self.say("torp.refused", {"reason": f"vi har inga {typ} kvar"})
        else:
            self.inventory[typ] -= 1
            tube.loading = typ
            tube.ready_t = self.now + RELOAD_S
            self.say("torp.loading", {"tube": n, "type": typ}, kind="ack")

    def _preview(self, designation: str | None) -> None:
        if designation is None:
            held = [t for t in self.game.knowledge.tracks.values() if t.held]
            if len(held) != 1:
                self.say("torp.refused", {"reason": "ange vilken kontakt"})
                return
            designation = held[0].designation
        tr, sol = self._solution_for(designation)
        if tr is None or sol is None:
            self.say("torp.refused", {"reason": f"vi har ingen lösning på {designation}"})
            return
        rows = []
        for key in TORPEDO_TYPES:
            row = {"type": key}
            if b := self._blocked(key):
                row["blocked"] = b
            elif (aim := self._aim(sol, key)) is not None:
                row["course"], row["run_s"] = aim[0], aim[1]
            else:
                row["course"] = None
            rows.append(row)
        self.say("torp.solution", {"designation": tr.designation, "quality": sol.quality,
                                   "rows": rows}, quality=sol.quality)
        straight = [r for r in rows if r.get("course") is not None
                    and not TORPEDO_TYPES[r["type"]].homing]
        if straight:
            self._leg_warning(tr.designation, min(r["run_s"] for r in straight),
                              straight[0]["type"])
            if ships := self._neutrals_in_lane(tr.designation, [straight[0]["course"]],
                                               straight[0]["type"]):
                self.say("torp.neutral", {"ships": ships, "preview": True}, quality=Quality.GOD)

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        for t in self.tubes:
            if t.loading and self.now >= t.ready_t:
                t.load, t.loading = t.loading, None
                self.say("torp.loaded", {"tube": t.n, "type": t.load})
        for r in list(self.in_water):
            if r.t_hit is not None and not r.timed and self.now >= r.t_hit:
                r.timed = True
                self.say("torp.time", {"tube": r.tube, "designation": r.designation}, kind="info")
            if self.now >= r.t_end + END_GRACE_S:
                self._finish(r, "timeout")
                if TORPEDO_TYPES[r.type].exercise:
                    self.say("torp.run.exercise_end", {"tube": r.tube})
                else:
                    self.say("torp.run.timeout", {"tube": r.tube}, quality=Quality.OSAKER)

        if self.now % 30 == 0:
            self._readiness()

    def _readiness(self) -> None:
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            # eget fartyg bara under torpedövningen (övningsledaren säger när)
            own_target = tr.friendly and tr.held and self.game.knowledge.torpedo_exercise
            if not (tr.threat or own_target) or sol is None \
                    or sol.quality < Quality.GOD:
                continue
            if self._ready_said.get(tr.designation, Quality.DALIG) >= sol.quality:
                continue
            for tube in self.tubes:
                # mot vårt eget fartyg bara med övningstorped
                if tr.friendly and not (tube.load and TORPEDO_TYPES[tube.load].exercise):
                    continue
                if tube.load and not self._blocked(tube.load) and \
                        (aim := self._aim(sol, tube.load)) is not None:
                    self._ready_said[tr.designation] = sol.quality
                    self.suggest(f"ready{tr.designation}", "torp.ready",
                                 {"designation": tr.designation, "tube": tube.n,
                                  "type": tube.load, "run_s": aim[1]},
                                 quality=sol.quality, cooldown=0)
                    break

    # --- initiativ vid tystnad -------------------------------------------------------
    def idle_proposals(self) -> list[Proposal]:
        # konventionella vapen; kärnladdningen laddas bara på uttrycklig order
        stock = [k for k in ("SET-53", "53-61") if self.inventory.get(k, 0) > 0]
        if not stock:
            return []
        for t in self.tubes:
            if t.load is None and t.loading is None:
                typ = max(stock, key=lambda k: self.inventory[k])
                return [Proposal(5, f"idle_reload{t.n}", "torp.suggest.reload",
                                 f"ladda tub {t.n} {typ}", {"tube": t.n, "type": typ})]
        return []

    # --- sjökortet -------------------------------------------------------------------
    def system_items(self) -> list:
        rack = TubeRack(tuple((t.n, t.load, t.loading,
                               max(0, t.ready_t - self.now) if t.loading else 0)
                              for t in self.tubes))
        stock = ", ".join(f"{k} {n}" for k, n in self.inventory.items())
        items: list = [rack,
                       Gauge("VAPEN", "Reserv", stock or "slut",
                             WARN if not any(self.inventory.values()) else OK),
                       Gauge("VAPEN", "Skenmål", f"{self.decoys} kvar",
                             WARN if self.decoys == 0 else OK)]
        if self.in_water:
            items.append(Gauge("VAPEN", "I vattnet", ", ".join(
                f"tub {r.tube}" + (f" mot {r.designation}" if r.designation else "")
                for r in self.in_water), INFO))
        return items

    def _finish(self, r: Running, how: str) -> None:
        self.in_water.remove(r)
        r.end_t, r.end = self.now, how
        self.finished.append(r)

    def chart_items(self) -> list:
        """Egna torpeder som eldledningen räknar dem: från avfyrningspunkten längs den
        inställda kursen så långt de hunnit, med minutstreck. Har en målsökande torped
        girat ritas också den hörda bäringen."""
        self.finished = [r for r in self.finished if self.now - r.end_t < TRACK_KEEP_S]
        items: list = []
        x, y = self.game.own_position_estimate()
        for r in self.finished + self.in_water:
            done = r.end_t is not None
            faded = done and self.now - r.end_t >= TRACK_FADE_S or r.lost
            speed = TORPEDO_TYPES[r.type].speed
            t = min(self.now if not done else r.end_t, r.t_end)
            run = speed * max(0, t - r.launch_t) / 3600
            b = math.radians(r.course)
            hx, hy = r.launch_x + run * math.sin(b), r.launch_y + run * math.cos(b)
            items.append(Track(((r.launch_x, r.launch_y), (hx, hy)), "torpedo_path", LAYER_RAY, None))
            for m in range(1, int((t - r.launch_t) // 60) + 1):
                d = speed * m / 60
                items.append(Mark(r.launch_x + d * math.sin(b), r.launch_y + d * math.cos(b),
                                  "+", "torpedo", faded=True, layer=LAYER_RAY + 0.1))
            head = "✱" if r.end == "hit" else "?" if done or r.lost else "•"
            items.append(Mark(hx, hy, head, "torpedo", f"tub {r.tube}", faded=faded))
            if r.turned and r.bearing is not None and not done:
                items.append(Ray(x, y, r.bearing, max(run, 0.1), "torpedo", "hörd",
                                 faded=r.lost))
        return items

    # --- torpeder i vattnet ---------------------------------------------------------
    def _report_in_water(self) -> None:
        rows = []
        for r in self.in_water:
            rows.append({
                "tube": r.tube, "type": r.type, "designation": r.designation,
                "course": r.course, "elapsed": self.now - r.launch_t,
                "to_hit": None if r.t_hit is None else r.t_hit - self.now,
                "to_end": max(0, r.t_end - self.now),
                "bearing": r.bearing, "lost": r.lost, "turned": r.turned})
        self.say("torp.in_water", {"running": rows})

    def _on_own_torpedo(self, e: OwnTorpedoHeard) -> None:
        r = next((x for x in self.in_water if x.no == e.no), None)
        if r is None:
            return
        d = {"tube": r.tube, "bearing": e.bearing if e.bearing is not None else r.bearing}
        match e.kind:
            case "running":
                r.bearing, r.heard_t, r.lost = e.bearing, self.now, False
                if not r.confirmed and self.now - r.launch_t >= RUN_REPORT_AFTER:
                    r.confirmed = True
                    self.say("torp.run.running", d, quality=e.quality)
            case "turned":
                r.bearing, r.heard_t, r.turned = e.bearing, self.now, True
                if TORPEDO_TYPES[r.type].homing:
                    self.say("torp.run.turned", d, quality=e.quality, alarm=True)
            case "lost":
                r.lost = True
                self.say("torp.run.lost", d)
            case "detonated":
                self._finish(r, "hit")
                self.say("torp.run.hit", {**d, "nuclear": TORPEDO_TYPES[r.type].nuclear},
                         kind="contact", quality=Quality.SAKER, alarm=True)
            case "silent":
                self._finish(r, "silent")
                self.say("torp.run.silent", d, quality=Quality.GOD)

    def _on_sound(self, e: SoundHeard) -> None:
        if self.decoys > 0 and (e.kind == "splash" or e.detail == "fast"):
            self.suggest("decoy", "torp.suggest.decoy", order="skenmål", cooldown=600)
