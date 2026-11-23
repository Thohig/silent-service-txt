"""Starpom (старпом), förste officer: håller befälet när kaptenen vilar.

Kaptenen lämnar över (`starpom har befälet`) och går till sin hytt. Starpom håller då
de stående orderna (kurs, fart, djup och pågående uppdrag som farleden, följ eller anfall
fortsätter som förut) och beslutar om besättningens förslag inom ett fast mandat
(MANDATE): djup, kurs, fart, smygmotor, periskop, fix, ventilera, skenmål … Ordern
kan lägga till (ORDER_MANDATE): i ett anfallsuppdrag går han mot skjutläget. Aldrig
avfyring, salva, radiosändning, ytläge eller att avbryta uppdraget; då väcker han
kaptenen. Han väger förslagen mot ordern (`_objection`) och säger nej till det som
skulle bryta anfallet, följandet eller rapporten. Inga slumpade beslut, och han läser bara kunskapen och egna
instrument.

Väckning på tre nivåer:
- information: lampan på snabbtelefonen i hytten lyser (civil kontakt …).
- fråga: telefonen ringer (ny hotkontakt, konvoj, telegram, förslag utanför mandatet,
  tidsgränsen nära, väckningstid). Tiden går till 1×. Svarar kaptenen inte inom
  ORDERLY_S kommer en ordonnans och knackar.
- fara: larm eller jakttecken. Högtalaren ropar kaptenen till centralen, tiden går
  till 1× och kaptenen tar befälet direkt och får lägesrapport.

Kaptenen kan också ringa (`lägesrapport`), ge order per telefon (starpom behåller
befälet), sova (`sov`: 60× tills han väcks) och gå till centralen (`jag har befälet`),
där han har befälet direkt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .. import phrases
from .. import russian as R
from ..broadcasts import order_day
from ..crew import Role
from ..events import OrderIssued, ReportDelivered
from ..fmt import clock, fmt_course, kn, nm
from ..ownship import ANTENNA_DEPTH
from ..orders import (REST_SCALE, AcceptSuggestion, CommandSpec, DeclineSuggestion, Order,
                      SetTimeScale, Unknown, split_orders)
from ..reports import Quality
from ..russian import ru
from .base import Station
from .engineering import EngineReport, SetPropulsion, Ventilate
from .navigation import (AttackApproach, BottomFix, EchoSounder, FollowFairway, GoToOpening, GoToStation,
                         GoToWait, IceReport, NavigationStation, ReportPosition, SetCourse,
                         SetDepth, SetSpeed, SettleOnBottom, SteerTo, TakeFix)
from .officer import is_big_ship, situation
from .periscope import PeriscopeDown, PeriscopeHold, PeriscopeLook, PeriscopeTrain
from .plot import QuerySolution, ShowPlot
from .trim import Hover, TrimHold, TrimNow, TrimReport
from .navigation.current import CurrentReport
from .radio import RadioStation, RadioStatus
from .torpedo_room import FiringSolution, LaunchDecoy, LoadTube, TorpedoStatus, TubeStatus

ORDERLY_S = 20          # obesvarat samtal: ordonnansen knackar
STEPS_S = 4             # så länge före knackningen hörs (syns) han utanför dörren
AJAR_S = 12             # så länge står dörren på glänt medan han talar
WATCH_S = 5             # så ofta starpom ser över läget
SUMMON_S = 120          # så långt före skjutläget ropas kaptenen till centralen
SUMMON_RANGE_NM = 3.5   # anfallsorder: ett stort fartyg så nära enligt plottet ⇒ kaptenen hit
TIME_WARN_S = 900       # tidsgränsen så här nära: väck kaptenen
REPEAT_S = 600          # samma fråga ringer inte igen förrän efter så här länge
PHONE_ORDER_S = 600     # en telefonorder så här färsk ändrar starpom inte på förslag: han ringer
SLEEP_SCALE = 60

# Det starpom får besluta om utan kaptenen. Allt annat väcker kaptenen.
MANDATE: tuple[type[Order], ...] = (
    SetCourse, SetSpeed, SetDepth, SetPropulsion, Ventilate,
    PeriscopeLook, PeriscopeHold, PeriscopeDown, PeriscopeTrain,
    TakeFix, ReportPosition, EchoSounder, IceReport, BottomFix, SettleOnBottom,
    FollowFairway, SteerTo, GoToWait, GoToStation, GoToOpening,
    QuerySolution, ShowPlot, EngineReport, TubeStatus, TorpedoStatus, FiringSolution,
    RadioStatus, LaunchDecoy, LoadTube, TrimNow, TrimHold, TrimReport, Hover, CurrentReport,
)

# Det ordern lägger till: i ett anfallsuppdrag får starpom gå mot skjutläget (`anfall S-x`).
# Avfyringen är alltid kaptenens; i skjutläget ropas han till centralen.
ORDER_MANDATE: dict[str, tuple[type[Order], ...]] = {"anfall": (AttackApproach,)}


def mandate_for(tasks) -> tuple[type[Order], ...]:
    """Starpoms mandat med det ordern (Knowledge.order_tasks) lägger till."""
    return MANDATE + tuple(c for t in sorted(tasks) for c in ORDER_MANDATE.get(t, ()))


@dataclass(frozen=True)
class HandOver(Order):
    """Kaptenen lämnar befälet till starpom och går till hytten."""


@dataclass(frozen=True)
class TakeBack(Order):
    """Kaptenen tar tillbaka befälet (går till centralen om han är i hytten)."""


@dataclass(frozen=True)
class CallCentral(Order):
    """Kaptenen ringer centralen: lägesrapport."""


@dataclass(frozen=True)
class AnswerPhone(Order):
    pass


@dataclass(frozen=True)
class Sleep(Order):
    pass


@dataclass(frozen=True)
class WakeAt(Order):
    clock_s: int        # sekunder efter midnatt


def _wake_at(m: re.Match) -> Order:
    h, mi = int(m[1]), int(m[2] or 0)
    if not (0 <= h < 24 and 0 <= mi < 60):
        return Unknown("", "klockslaget som tt:mm, t.ex. väck mig 04:30")
    return WakeAt(h * 3600 + mi * 60)


# Larmrapporter som inte är fara. None: starpoms egen bevakning tar det (kontakter,
# konvoj, telegram). Allt annat larm (torped, sjunkbomb, snabb pingtakt, skada,
# läcka, brand, stridslarm …) är fara: kaptenen till centralen.
ALARM_LEVELS = {
    "sonar.new_contact": "info", "sonar.regained": "info", "plot.maneuver": "info",
    "radio.message": None, "plot.convoy.found": None,
    "sonar.ping.first": "question", "nav.wait.arrived": "question",
    "nav.attack.arrived": "danger", "nav.attack.passed": "question",
    "nav.follow.lost": "question", "nav.settle.not_reached": "question",
    "off.esm": "question", "off.esm.air": "question",
}
# order som tar över styrningen (avbryter navigatörens anfall eller följande)
STEERING: tuple[type[Order], ...] = (SetCourse, SteerTo, GoToWait, GoToStation, GoToOpening,
                                     FollowFairway)

DANGER_PREFIXES = ("bridge.column", "bridge.hit")

# vad en order bestämmer över: ett förslag om samma sak går emot en färsk telefonorder
SLOTS: tuple[tuple[str, tuple[type[Order], ...]], ...] = (
    ("depth", (SetDepth, SettleOnBottom, Hover)),
    ("course", STEERING),
    ("speed", (SetSpeed,)),
    ("propulsion", (SetPropulsion,)),
)


def order_slots(order: Order) -> set[str]:
    return {name for name, kinds in SLOTS if isinstance(order, kinds)}


def alarm_level(type_: str) -> str | None:
    if type_ in ALARM_LEVELS:
        return ALARM_LEVELS[type_]
    if type_.startswith(DANGER_PREFIXES):
        return "danger"
    if type_.startswith(("off.periscope", "bridge.", "nav.")):
        return "question"               # något i sikte, navigatörens varningar
    return "danger"


def in_mandate(game, order_text: str) -> bool:
    """Får starpom själv verkställa ordern (alla delar på raden)?"""
    parts = split_orders(order_text)
    if not parts:
        return False
    allowed = mandate_for(game.knowledge.order_tasks)
    for part in parts:
        o = game.registry.parse(part)
        if not isinstance(o, allowed):
            return False
        if isinstance(o, SetDepth) and o.depth < 1:     # ytläge är kaptenens beslut
            return False
    return True


# --------------------------------------------------------------------------- fraser
def reason_text(d: dict) -> str:
    """Varför starpom väcker kaptenen, i en mening."""
    k = d["kind"]
    if k == "contact":
        s = f"Ny kontakt {d['designation']}, {d['label']}, bäring {fmt_course(d['bearing'])}"
        if d.get("range") is not None:
            s += f", cirka {nm(d['range'])} sjömil ({Quality(d['quality']).label})"
        return s + "."
    if k == "civil":
        return f"{d['designation']}, {d['label']}, i plottet."
    if k == "hunted":
        return "Sonar hör att fienden troligen har kontakt med oss."
    if k == "alarm":
        return f"Larm: {d['text']}"
    if k == "convoy":
        return "Plottet har en konvoj."
    if k == "big":
        return f"Sonar hör ett stort fartyg, {d['designation']}."
    if k == "telegram":
        return f"Telegram från staben, mottagning nummer {d['number']}."
    if k == "time":
        return f"Det är {d['minutes']} minuter kvar enligt ordern."
    if k == "wake_at":
        return f"Klockan är {d['clock']}, ni bad att bli väckt."
    if k == "attack":
        return (f"Vi är i skjutläge mot {d['designation']} om cirka {d['minutes']} minuter. "
                f"Avfyringen är ert beslut.")
    if k == "target":
        return (f"{d['designation']}, {d['label']}, cirka {nm(d['range'])} sjömil. "
                f"Inom skjutavstånd snart; avfyringen är ert beslut.")
    if k == "window":
        return f"Sambandstillfälle klockan {d['clock']}. Ordern kräver rapporten."
    if k == "suggestion":
        return f"{d['who']} föreslår {d['proposed']}.{_quoted(d)} Det beslutet är ert."
    if k == "phone_order":
        return (f"{d['who']} föreslår {d['proposed']}.{_quoted(d)} Ni beordrade {d['ordered']} "
                f"klockan {d['clock']}. Det beslutet är ert.")
    return ""


_ADDRESS = re.compile(r"^(?:Kapten|Tovarisjtj komandir)[,!]\s*[^.!]*[.!]\s*")


def suggestion_why(why: dict | None) -> str:
    """Stationens förslag som det lät (`why`: förslagets typ och data), utan tilltalet
    ("Kapten, radio.") och ja-ordern: det starpom läser upp i telefonen och hytten visar."""
    if not why:
        return ""
    phrase = phrases.PHRASES.get(why["type"])
    return _ADDRESS.sub("", phrase(why["data"])).strip() if phrase else ""


def _quoted(d: dict) -> str:
    q = suggestion_why(d.get("why"))
    return f" Han säger: »{q}«" if q else ""


def _why_not(d: dict) -> str:
    """Varför starpom säger nej till ett förslag: det går emot ordern."""
    w = d["why"]
    if w == "attack":
        return f"Vi håller kursen mot skjutläget för {d['designation']}, enligt ordern."
    if w == "follow":
        return f"Vi följer {d['designation']}; navigatören styr."
    if w == "report":
        return "Radion behöver masten vid sambandstillfället; ordern kräver rapporten."
    return ""


def _why_of(report) -> dict:
    """Förslagets typ och data (inte färdig text): frasen återges när starpom säger det."""
    return {"type": report.type, "data": {k: v for k, v in report.data.items() if k != "order"}}


def _canon(order: str) -> str:
    """Kaptenens order som besättningen säger den: kurser med tre siffror (\"kurs 0\" ⇒ kurs 000)."""
    return re.sub(r"\b(kurs|k|styr)\s+(\d{1,3})\b", lambda m: f"kurs {int(m[2]) % 360:03d}",
                  " ".join(order.strip().lower().split()))


def _reasons(d: dict) -> str:
    return " ".join(reason_text(r) for r in d.get("reasons", ()))


def _standing(d: dict) -> str:
    return (f"djup {d['depth']:.0f} meter, kurs {fmt_course(d['course'])}, "
            f"fart {kn(d['speed'])} knop")


def _decisions(d: dict) -> str:
    ds = d.get("decisions") or []
    if not ds:
        return "Inga beslut sedan förra samtalet."
    return "Sedan förra samtalet: " + "; ".join(f"{c} {o}" for c, o in ds) + "."


def _report(d: dict) -> str:
    out = [f"Kapten, starpom. Vi går {_standing(d)}."] + situation(d)
    out.append(_decisions(d))
    if d.get("reasons"):
        out.append(_reasons(d))
    out.append("Jag fortsätter enligt order.")
    return " ".join(out)


def _handback(d: dict) -> str:
    out = [f"Kapten, starpom. {ru('Komandovanie sdal')}, ni har befälet. Vi går {_standing(d)}."]
    if d.get("reasons"):
        out.append(_reasons(d))
    out += situation(d)
    out.append(_decisions(d))
    return " ".join(out)


PHRASES = {
    "xo.took": lambda d: f"{ru('Komandovanie prinjal')}. Jag har befälet, kapten. Vi håller "
    f"{_standing(d)}. Jag väcker er om något händer.",
    "xo.already": lambda d: "Kapten, jag har redan befälet.",
    "xo.captain_has": lambda d: "Kapten, ni har befälet.",
    "xo.not_in_command": lambda d: "Kapten, ni har befälet själv. Lämna över till mig först.",
    "xo.time_refused": lambda d: "Kapten, så fort går vakten bara när jag har befälet och ni vilar.",
    "xo.accept": lambda d: f"{d['who']} föreslår {d['proposed']}. Verkställ.",
    "xo.decline": lambda d: f"{d['who']} föreslår {d['proposed']}. Nej. {_why_not(d)}",
    "xo.report": _report,
    "xo.handback": _handback,
    "xo.ring": lambda d: "Snabbtelefonen ringer från centralen (svara).",
    "xo.call": lambda d: "Kapten, starpom. " + _reasons(d),
    "xo.orderly": lambda d: "Det knackar. Ordonnansen: Kamrat kapten, starpom ber er "
    "ringa centralen. " + _reasons(d),
    "xo.danger": lambda d: f"I högtalaren: {ru('Komandir, v tsentralnyj')}! Kaptenen till "
    f"centralen! " + _reasons(d),
    "xo.phone.silent": lambda d: "Kapten, starpom. Ingen har ringt, läget är oförändrat.",
    "xo.sleep": lambda d: "Uppfattat, kapten. Sov gott, jag väcker er.",
    "xo.wake_at": lambda d: f"Uppfattat, kapten. Jag väcker er klockan {d['clock']}.",
}
phrases.register(PHRASES)

XO = f"{R.CAPTAIN}, старпом."
RU_PHRASES = {
    "xo.took": lambda d: "Командование принял. Если что, разбужу.",
    "xo.already": lambda d: f"{XO} Командование уже у меня.",
    "xo.captain_has": lambda d: f"{XO} Командование у вас.",
    "xo.not_in_command": lambda d: f"{XO} Командование у вас.",
    "xo.time_refused": lambda d: f"{XO} Так быстро только когда вахту несу я.",
    "xo.accept": lambda d: "Добро. Исполнять.",
    "xo.decline": lambda d: "Нет. Отставить.",
    "xo.report": lambda d: f"{XO} Докладываю обстановку.",
    "xo.handback": lambda d: f"{XO} Командование сдал.",
    "xo.ring": lambda d: "",
    "xo.call": lambda d: f"{XO} Прошу вашего решения.",
    "xo.orderly": lambda d: "Товарищ командир, старпом просит позвонить в центральный.",
    "xo.danger": lambda d: "Командир, в центральный! Командир, в центральный!",
    "xo.phone.silent": lambda d: f"{XO} Всё спокойно.",
    "xo.sleep": lambda d: "Есть. Отдыхайте, разбужу.",
    "xo.wake_at": lambda d: "Есть, разбужу.",
}
phrases.register_ru(RU_PHRASES)


class FirstOfficer(Station):
    role = Role.XO
    COMMANDS = [
        CommandSpec(r"(?:starpom (?:har|tar|övertar|overtar) befälet|starpom (?:har|tar) befalet|"
                    r"(?:överlämna|overlamna|lämna över|lamna over|ge) befälet(?: till starpom)?|"
                    r"(?:överlämna|overlamna|lämna över|lamna over|ge) befalet(?: till starpom)?)",
                    lambda m: HandOver(), "starpom har befälet"),
        CommandSpec(r"(?:jag (?:har|tar) (?:befälet|befalet)|(?:kaptenen )?till centralen|"
                    r"gå till centralen|ga till centralen)",
                    lambda m: TakeBack(), "jag har befälet"),
        CommandSpec(r"(?:ring (?:centralen|starpom)|lägesrapport|lagesrapport)",
                    lambda m: CallCentral(), "lägesrapport"),
        CommandSpec(r"(?:svara|svara telefonen|lyft luren)", lambda m: AnswerPhone(), "svara"),
        CommandSpec(r"(?:sov|sova|vila|gå och lägg dig|ga och lagg dig)", lambda m: Sleep(), "sov"),
        CommandSpec(r"väck mig (?:vid |klockan |kl\.? )?(\d{1,2})(?:[:.](\d{2}))?",
                    _wake_at, "väck mig 04:30"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.in_command = False
        self.captain_at = "central"         # central eller cabin
        self.sleeping = False
        self.ring_t: int | None = None      # telefonen ringer sedan
        self.orderly_t: int | None = None   # ordonnansen knackade
        self.pending: list[dict] = []       # det kaptenen ska få veta (orsaker)
        self.asking: dict | None = None     # förslaget starpom senast bad kaptenen besluta om
        self.lamp = False
        self.decisions: list[tuple[str, str]] = []   # (klocka, order) sedan förra samtalet
        self.wake_at: int | None = None     # simtid
        self._seen: set[str] = set()
        self._convoy_seen = False
        self._telegrams_seen = 0
        self._hunt_seen = False
        self._time_warned = False
        self._asked: dict[str, int] = {}    # fråga -> senast ringd
        # kaptenens order per telefon medan starpom har befälet: sak -> (tid, ordertext)
        self.phone_orders: dict[str, tuple[int, str]] = {}
        sc = getattr(game, "scenario", None)
        self.order_day = order_day(sc.secret_order) if sc and sc.secret_order else None

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(ReportDelivered, self._on_report)
        bus.subscribe(OrderIssued, self._on_issued)

    def _on_issued(self, e: OrderIssued) -> None:
        """Kaptenens order per telefon: starpom ändrar dem inte själv på ett förslag."""
        if self.in_command and e.by == "captain":
            for slot in order_slots(e.order):
                self.phone_orders[slot] = (e.t, _canon(e.text))

    # --- läget ------------------------------------------------------------------
    def status_fields(self) -> dict:
        return {"command": "starpom" if self.in_command else "captain",
                "captain_at": self.captain_at,
                "phone": "ring" if self.ring_t is not None else "lamp" if self.lamp else None,
                "sleeping": self.sleeping, "order_day": self.order_day, "door": self._door(),
                "decision": self._decision(),
                "decision_why": suggestion_why(self.asking.get("why")) if self._decision() else None}

    def _decision(self) -> str | None:
        """Förslaget som väntar på kaptenens ja eller nej sedan han svarat i telefonen."""
        if not self.in_command or self.asking is None or self.ring_t is not None:
            return None
        sug = self.game.active_suggestion()
        if sug is None or sug[0] != self.asking["proposed"]:
            return None
        return f"{self.asking['who']} föreslår {self.asking['proposed']}"

    def _door(self) -> str | None:
        """Hyttdörren: ordonnansen står utanför och knackar."""
        if self.captain_at != "cabin":
            return None
        if self.ring_t is not None and self.now - self.ring_t >= ORDERLY_S - STEPS_S:
            return "steps"
        if self.orderly_t is not None and self.now - self.orderly_t < AJAR_S:
            return "ajar"
        return None

    def _situation(self) -> dict:
        from .officer import OfficerStation
        try:
            d = self.game.station(OfficerStation).briefing_data(0)
        except KeyError:
            st = self.own.state
            d = {"depth": st.depth, "course": st.course, "speed": round(st.speed),
                 "contacts": [], "civil": 0, "convoy": None}
        st = self.own.state
        d.update(depth=st.ordered_depth, course=st.ordered_course,
                 speed=round(st.ordered_speed, 1))
        return d

    def _mark_seen(self) -> None:
        """Det kaptenen redan vet när han lämnar över."""
        k = self.game.knowledge
        self._seen = {t.designation for t in k.tracks.values()}
        self._convoy_seen = k.convoy is not None
        self._telegrams_seen = len(k.telegrams)
        self._hunt_seen = k.hunted(self.now)
        self._time_warned = False

    # --- order -------------------------------------------------------------------
    def intercept(self, order: Order) -> bool:
        if isinstance(order, SetTimeScale):
            if order.scale > REST_SCALE and not self.in_command:
                self.say("xo.time_refused")
                return True
            self.sleeping = self.sleeping and order.scale > REST_SCALE
        if isinstance(order, (AcceptSuggestion, DeclineSuggestion)) and self.in_command and \
                self.ring_t is not None:
            self._answer()                  # ja eller nej: kaptenen lyfter luren först
        return False

    def on_order(self, order: Order) -> None:
        match order:
            case HandOver():
                if self.in_command:
                    self.say("xo.already")
                    return
                self.in_command = True
                self.captain_at = "cabin"
                self.phone_orders = {}
                self.decisions = []
                self.pending = []
                self.asking = None
                self.lamp = False
                if self.wake_at is not None and self.wake_at <= self.now:
                    self.wake_at = None         # en väckningstid som redan passerat gäller inte
                self._mark_seen()
                self.say("xo.took", self._situation(), kind="ack", extra_delay=-1)
            case TakeBack():
                if not self.in_command:
                    self.say("xo.captain_has")
                else:
                    self._arrive()
            case CallCentral():
                if not self.in_command:         # kaptenen är i centralen: vakthavande svarar
                    from .officer import OfficerStation
                    try:
                        self.game.station(OfficerStation).situation_report()
                    except KeyError:
                        self.say("xo.not_in_command")
                    return
                d = self._situation()
                d["decisions"] = list(self.decisions)
                d["reasons"] = list(self.pending)
                self._note_asking()
                self._clear_calls()
                self.say("xo.report", d)
            case AnswerPhone():
                if not self.in_command:
                    self.say("xo.not_in_command")
                elif self.pending:
                    self._answer()
                else:
                    self.say("xo.phone.silent")
            case Sleep():
                if not self.in_command:
                    self.say("xo.not_in_command")
                    return
                self.sleeping = True
                self.say("xo.sleep", kind="ack")
                self.game.set_time_scale(SLEEP_SCALE, "sömn")
            case WakeAt(clock_s=c):
                start = self.game.start_clock
                t = c - start % 86400
                while t <= self.now:
                    t += 86400
                self.wake_at = t
                self.say("xo.wake_at", {"clock": clock(c)[:5]}, kind="ack")

    def keeps_time_scale(self, report) -> bool:
        """Med befälet: larm som bara tänder lampan (eller som han själv bevakar) väcker inte
        kaptenen och sänker inte tiden. Frågor och fara sänker han själv (_wake)."""
        return self.in_command and self.captain_at == "cabin" and \
            alarm_level(report.type) in ("info", None)

    def _answer(self) -> None:
        """Kaptenen svarar: starpom säger varför han ringde."""
        d = {"reasons": list(self.pending)}
        self._note_asking()
        self._clear_calls()
        self.say("xo.call", d, extra_delay=-1)

    def _note_asking(self) -> None:
        """Det senaste förslaget i samtalet är det kaptenens ja eller nej gäller."""
        for r in reversed(self.pending):
            if r["kind"] in ("suggestion", "phone_order"):
                self.asking = {"who": r["who"], "proposed": r["proposed"], "why": r.get("why")}
                return

    def _clear_calls(self) -> None:
        self.pending = []
        self.ring_t = None
        self.lamp = False

    # --- förslagen ---------------------------------------------------------------
    def _objection(self, report, order: str) -> dict | None:
        """Går förslaget emot det som för ordern framåt? Fasta regler, ingen slump.
        Larm och jakttecken går alltid före: då verkställs förslaget."""
        if report.alarm or self.game.knowledge.hunted(self.now):
            return None
        parts = [self.game.registry.parse(p) for p in split_orders(order)]
        nav = self._nav()
        # navigatören styr mot skjutläget eller efter en kontakt: kursförslag från andra
        # stationer (t.ex. plottets TMA-gir) skulle avbryta det
        if nav is not None and nav.goal in ("attack", "follow") and \
                report.role != Role.NAVIGATOR.value and any(isinstance(o, STEERING) for o in parts):
            return {"why": nav.goal, "designation": nav.steer.designation}
        # ordern kräver en rapport och radion behöver masten: inte djupare än antenndjup
        radio = self._radio()
        if "rapport" in self.game.knowledge.order_tasks and radio is not None and \
                radio.needs_mast() and report.role != Role.NAVIGATOR.value and any(
                    isinstance(o, SettleOnBottom) or
                    isinstance(o, SetDepth) and o.depth > (radio.up_depth() or ANTENNA_DEPTH)
                    for o in parts):
            return {"why": "report"}
        return None

    def _against_phone_order(self, report, order: str) -> dict | None:
        """Går förslaget emot en order kaptenen gett per telefon de senaste tio minuterna?
        Larm och jakttecken går före, som i _objection."""
        if report.alarm or self.game.knowledge.hunted(self.now):
            return None
        for part in split_orders(order):
            for slot in order_slots(self.game.registry.parse(part)):
                if slot in self.phone_orders:
                    t, text = self.phone_orders[slot]
                    if self.now - t <= PHONE_ORDER_S and text != _canon(part):
                        return {"ordered": text, "clock": self.game.clock_str(t)[:5]}
        return None

    def _nav(self) -> NavigationStation | None:
        try:
            return self.game.station(NavigationStation)
        except KeyError:
            return None

    def _radio(self) -> RadioStation | None:
        try:
            return self.game.station(RadioStation)
        except KeyError:
            return None

    def on_suggestion(self, report) -> bool:
        if not self.in_command:
            return False
        order = report.data["order"]
        if in_mandate(self.game, order) and (why := self._objection(report, order)) is not None:
            self.decisions.append((self.game.clock_str()[:5], f"nej till {order}"))
            self.say("xo.decline", {"who": report.speaker.split(" (")[0], "proposed": order, **why},
                     kind="ack", extra_delay=-1)
            self.game.log(f"STARPOM avslår: {order!r} ({why})")
            return True
        if in_mandate(self.game, order) and (ph := self._against_phone_order(report, order)):
            self._wake("question", {"kind": "phone_order", "who": report.speaker.split(" (")[0],
                                    "proposed": order, "why": _why_of(report), **ph})
            return False
        if in_mandate(self.game, order):
            self.decisions.append((self.game.clock_str()[:5], order))
            self.say("xo.accept", {"who": report.speaker.split(" (")[0], "proposed": order},
                     kind="ack", extra_delay=-1)
            self.game.log(f"STARPOM beslutar: {order!r}")
            self.game.command(order, by="starpom")
            if report.type.startswith("radio.prewarn") and \
                    "rapport" in self.game.knowledge.order_tasks:
                self._wake("question", {"kind": "window", "clock": report.data.get("clock", "")})
            return True
        self._wake("danger" if report.alarm else "question",
                   {"kind": "suggestion", "who": report.speaker.split(" (")[0],
                    "proposed": order, "why": _why_of(report)})
        return False

    # --- väckning ------------------------------------------------------------------
    def _on_report(self, e: ReportDelivered) -> None:
        r = e.report
        if not self.in_command or not r.alarm or r.role == self.role.value or r.kind == "suggest":
            return
        level = alarm_level(r.type)
        if level is None:
            return
        if level != "danger" and any(p.get("type") == r.type for p in self.pending):
            return                          # samma slags larm väntar redan på kaptenen
        self._wake(level, {"kind": "alarm", "type": r.type, "text": r.text})

    def _wake(self, level: str, reason: dict[str, Any]) -> None:
        """level: info (lampan), question (telefonen ringer) eller danger (högtalaren)."""
        if not self.in_command:
            return
        if level == "question":
            key = f"{reason['kind']}:{reason.get('type') or reason.get('proposed') or ''}"
            if reason["kind"] in ("suggestion", "alarm", "phone_order"):
                if self.now - self._asked.get(key, -10**9) < REPEAT_S:
                    return
                self._asked[key] = self.now
        self.pending.append(reason)
        self.game.log(f"STARPOM väcker ({level}): {reason}")
        if level == "info":
            self.lamp = True
            return
        self.sleeping = False
        self.game.set_time_scale(1, "starpom")
        if level == "danger":
            d = {"reasons": [reason]}
            self.pending.remove(reason)     # sagt i högtalaren; upprepas inte
            self.say("xo.danger", d, alarm=True, extra_delay=-1)
            self._arrive(first=reason)
            return
        if self.ring_t is None:
            self.ring_t = self.now
            self.say("xo.ring", kind="system", extra_delay=-1)

    def _watch(self) -> None:
        k, now = self.game.knowledge, self.now
        hunted = k.hunted(now)
        if hunted and not self._hunt_seen:
            self._wake("danger", {"kind": "hunted"})
        self._hunt_seen = hunted
        for tr in sorted(k.tracks.values(), key=lambda t: t.first_t):
            if tr.designation in self._seen or not tr.held:
                continue
            if tr.benign or tr.friendly:
                self._seen.add(tr.designation)
                self._wake("info", {"kind": "civil", "designation": tr.designation,
                                    "label": tr.classification})
                continue
            if is_big_ship(tr):
                self._seen.add(tr.designation)
                self._wake("question", {"kind": "big", "designation": tr.designation})
                continue
            sol = tr.solution
            if sol is None or sol.quality < Quality.OSAKER or tr.last_bearing is None:
                continue                    # vänta tills plottet vet något
            self._seen.add(tr.designation)
            self._wake("question", {"kind": "contact", "designation": tr.designation,
                                    "label": tr.classification, "bearing": tr.last_bearing,
                                    "range": sol.range_nm, "quality": int(sol.quality)})
        if k.convoy is not None and not self._convoy_seen:
            self._convoy_seen = True
            self._wake("question", {"kind": "convoy"})
        if len(k.telegrams) > self._telegrams_seen:
            new = [t for t in k.telegrams[self._telegrams_seen:] if t.kind == "telegram"]
            self._telegrams_seen = len(k.telegrams)
            for t in new:
                self._wake("question", {"kind": "telegram", "number": t.number})
        nav = self._nav()
        if nav is not None and nav.goal == "attack" and nav.attack_eta_t is not None and \
                nav.attack_eta_t - now <= SUMMON_S and \
                self._asked.get(f"attack:{nav.steer.designation}", -10**9) < now - REPEAT_S:
            self._asked[f"attack:{nav.steer.designation}"] = now
            self._wake("danger", {"kind": "attack", "designation": nav.steer.designation,
                                  "minutes": max(1, round((nav.attack_eta_t - now) / 60))})
        if "anfall" in k.order_tasks and not hunted:
            self._target_watch()
        end = self.patrol_end       # tidsgränsen står i ordern
        if end is not None and not self._time_warned and end - now <= TIME_WARN_S:
            self._time_warned = True
            self._wake("question", {"kind": "time", "minutes": max(1, (end - now) // 60)})
        if self.wake_at is not None and now >= self.wake_at:
            self.wake_at = None
            self._wake("question", {"kind": "wake_at", "clock": self.game.clock_str()[:5]})

    def _target_watch(self) -> None:
        """Anfallsorder: ett klassat stort fartyg med färsk lösning närmare än SUMMON_RANGE_NM
        ⇒ kaptenen till centralen (avfyringen är hans)."""
        now = self.now
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            if not tr.held or not is_big_ship(tr) or tr.class_quality < Quality.GOD or \
                    sol is None or sol.quality < Quality.OSAKER or now - sol.t > 180 or \
                    sol.range_nm > SUMMON_RANGE_NM:
                continue
            key = f"target:{tr.designation}"
            if now - self._asked.get(key, -10**9) < REPEAT_S:
                continue
            self._asked[key] = now
            self._wake("danger", {"kind": "target", "designation": tr.designation,
                                  "label": tr.classification, "range": sol.range_nm})
            return

    def update(self) -> None:
        if not self.in_command:
            return
        if self.ring_t is not None and self.captain_at == "cabin" and \
                self.now - self.ring_t >= ORDERLY_S:
            d = {"reasons": list(self.pending)}
            self._clear_calls()
            self.orderly_t = self.now
            self.say("xo.orderly", d, kind="system", extra_delay=-1)
        if self.now % WATCH_S == 0:
            self._watch()

    def _arrive(self, first: dict | None = None) -> None:
        """Kaptenen är i centralen: befälet tillbaka och lägesrapport. first: larmet som kallade
        kaptenen i högtalaren, först bland skälen."""
        d = self._situation()
        d["decisions"] = list(self.decisions)
        d["reasons"] = ([first] if first else []) + list(self.pending)
        self.in_command = False
        self.captain_at = "central"
        self.sleeping = False
        self._clear_calls()
        self.decisions = []
        self.game.set_time_scale(1, "kaptenen")
        self.say("xo.handback", d, extra_delay=-1)
