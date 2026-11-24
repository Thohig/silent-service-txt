"""Sonarrummet: passiv lyssning, transienter, aktiv sonar och förslag.

Sensorn (sim/sonar.py) är bryggan mellan sanning och kunskap. Stationen
publicerar sensorns utdata som händelser på bussen. Kunskapslagret,
plottlaget och torpedrummet lyssnar utan att känna till sonaren.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import acoustics, phrases
from ..crew import Role
from ..entities import Transient
from ..events import (BearingObserved, ChargeHeard, ClassificationChanged, ContactDetected, ContactSunk, HuntSigns,
                      ContactLost, OwnSoundMade, OwnTorpedoHeard, SoundHeard)
from ..fmt import fmt_course, nm
from .. import russian as R
from ..russian import ru
from ..geo import angle_diff, circular_mean, norm360
from ..orders import CommandSpec, Order
from ..profile import HeardEvent, Level
from ..reports import Quality
from ..sonar_view import (held_by_kind, KEEP_S as WATERFALL_KEEP_S, SONAR_SOURCES, BearingTrace, ContactLine,
                          HeardMark, LostMark, OwnMark, bearing_drift, track_kind)
from ..systems import INFO, OK, WARN, Gauge
from ..sonar import (ClassificationUpdate, Detection, IncomingTorpedo, Lost, OwnTorpedo,
                     SonarStation, TransientHeard)
from ..tma import BearingObs
from .base import Proposal, Station
from .baffles import BafflesMixin
from .incoming import IncomingMixin
from .recording import RecordingMixin
from .sweep import SweepCalls

BEARING_REPORT_DELTA = 5.0
LOST_BATCH_S = 20          # tappade (och åter hörda) kontakter samlas på en rad tills ingen ny kommit på så länge,
LOST_BATCH_MAX_S = 60      # ... högst så länge; en som hörs igen innan raden sagts nämns inte (krig-kort frö 61:
                           # konvojen vid hörgränsen gav fyra rader "har tappat" på 50 s, 5 s förut)
BEARING_REPORT_MAX_AGE = 300
BEARING_MIN_GAP_S = 60       # samma kontakts bäring ropas inte oftare (jakt nära: annars var 5:e s)
SMOOTH_OBS = 6
FAST_PING_S = 13
SLOW_PING_S = 20            # så här långt mellan pingarna två gånger i rad: takten har minskat
PING_SAME_DEG = 8.0         # okända pingar inom så här många grader räknas som samma pingare
PING_DRIFT_DEG_PER_S = 0.4  # ... plus så här mycket per sekund sedan förra pingen (pingaren rör sig)
PING_SAME_MAX_DEG = 20.0
PING_DRIFT_NEAR_DEG_PER_S = 1.5     # starka pingar (≥ PING_NEAR_RL): pingaren är nära och svänger fort
PING_SAME_MAX_NEAR_DEG = 60.0
UWT_FIRST_S = 120           # undervattenstelefonen: första gången, sedan dubbelt så länge emellan
UWT_MAX_S = 1800
UWT_RESET_S = 1800          # tyst så här länge: nästa är en ny omgång
CLOSE_FIRST_S = 300         # "pingarna är mycket starka": samma glesning per pingare
CLOSE_MAX_S = 1800
CLOSE_RESET_S = 2400
PING_KNOWN_S = 900          # en känd pingare som tappats som kontakt känns igen på bäringen så länge
PING_SMOOTH = 0.5           # ny ping väger så här mycket i pingarens bäring
PING_RATE_GAIN = 0.5        # ny drift väger så här mycket i pingarens skattade drift
PING_RATE_MAX = 2.0         # pingarens bäringsdrift (°/s, ur pingarna) som grinden räknar med, högst
PING_RATE_HORIZON_S = 30    # driften räknas fram högst så här långt; ett längre uppehåll börjar om bäringen
                            # (en gammal drift över 6 min gav 38° fel, en nära passages −1,7°/s över 91 s 55°)
PING_LEVEL_DEG_PER_DB = 3.0 # två pingare i grinden: nivån skiljer dem (en dB väger som tre grader)
PING_LEVEL_SMOOTH = 0.5     # ny ping väger så här mycket i pingarens nivå
# Så starka pingar (mottagen nivå, dB) kommer från en jagare nära nog att jaga oss: en jagarping
# på 230 dB når hit på ~8 nm (~5,5 nm genom skiktet). Svagare pingar i snabb takt jagar något
# långt bort: sonar säger det, men inget stridslarm (HuntSigns) och inget förslag om att undvika.
PING_NEAR_RL = 142.0
PING_LAYER_DB = 7.0         # operatörens tumregel för vad skiktet tar av en ping
PING_FAR_REPORT_S = 900     # en avlägsen jakt från samma pingare rapporteras inte oftare
ICE_REPORT_S = 1800          # knakande is rapporteras inte oftare
PROFILE_KEEP_S = 3 * 3600    # djupprofilen minns hörda ljud så här länge
# Djupprofilens symboler för hörda ljud (och våra egna): (symbol, stil)
HEARD_SYMBOL = {
    "ping": ("◦", "heard_ping"), "splash": ("↓", "heard_splash"),
    "explosion": ("✱", "heard_explosion"), "practice": ("*", "heard_practice"),
    "buoy": ("⊥", "heard_buoy"), "buoy_ping": ("◎", "heard_buoy"),
    "uwt": ("~", "heard_other"), "breakup": ("×", "heard_explosion"),
}
OWN_SYMBOL = {"ping": ("!", "own_sound"), "launch": ("»", "own_sound"),
              "decoy": ("o", "own_sound"), "blow": ("↑", "own_sound"),
              "astern": ("◂", "own_sound"), "reload": ("¤", "own_sound")}


CONTACTS_NAMED = 2          # systemtavlan: så här många kontakter nämns vid namn
LINE_AFTER_LOST_S = 300     # en tappad kontakt står kvar i sonarvyns lista så här länge


def contacts_text(held: list[str], threats: int) -> str:
    """Systemtavlans rad: antalet och hur många som är hot; beteckningarna bara när de är
    få (panelen är smal, listan står i huvudraden och sonarvyn)."""
    if not held:
        return "inga"
    hot = f"{threats} hot" if threats else ""
    if len(held) <= CONTACTS_NAMED:
        return ", ".join(held) + (f" ({hot})" if hot else "")
    return f"{len(held)}" + (f" ({hot})" if hot else "")


def _recent(marks: list, now: int) -> list:
    """Vattenfallets märken från den senaste timmen."""
    if marks and marks[0].t < now - WATERFALL_KEEP_S:
        return [m for m in marks if m.t >= now - WATERFALL_KEEP_S]
    return marks


@dataclass(frozen=True)
class ActivePing(Order):
    pass


def _src(d: dict) -> str:
    return f" från {d['designation']}" if d.get("designation") else ""


def _far(d: dict) -> str:
    return "långt bort" if d.get("sure") else "troligen långt bort"


def _only_pings(d: dict) -> str:
    """Kontakten är tappad på passiv sonar men pingarna känns igen: säg det, så att det inte låter
    som att vi har den igen."""
    return f" Maskinerna på {d['designation']} hör vi inte, bara pingarna." if d.get("lost") else ""


# Sjunkbombernas klassning (KV2): sonaren hör bara den mottagna nivån. En signalladdning ger
# 195 dB vid källan, en skarp 230: en signalladdning nära låter som en skarp flera sjömil bort.
# Starkare än en signalladdning kan låta (närmast CHARGE_MIN_M) är skarpt, säkert. Annars avgör
# avståndet till den som fällde den (plottets lösning), med kvalitet ur avståndets osäkerhet;
# utan avstånd: "troligen signalladdningar, eller skarpa långt bort", osäker.
CHARGE_SIGNAL_DB = acoustics.EXPLOSION_PRACTICE
CHARGE_REAL_DB = acoustics.EXPLOSION_REAL
CHARGE_MIN_M = 50.0
CHARGE_MARGIN_DB = 4.0
CHARGE_TL_SIGMA_Q = (4.0, 9.0, 17.0)     # osäkerheten i dB under detta: säker, god, osäker
NEAR_SE = 110                            # så starkt: nära

AMBIENT_EVERY_S = 60        # havsbruset läses av så här ofta
AMBIENT_REPORT_DB = 2.0     # så stor ändring säger sonaren till om

def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " och " + items[-1]


PHRASES = {
    "sonar.ambient": lambda d: f"Kapten, sonar. Havsbruset har {'ökat' if d['db'] > 0 else 'minskat'} "
    f"cirka {abs(d['db']):.0f} dB. " + ("Vi hör sämre, kontakterna hörs kortare." if d["db"] > 0
                                        else "Vi hör längre nu."),
    "sonar.new_contact": lambda d: f"{ru('Tovarisjtj komandir')}, sonar! Ny kontakt i bäring {fmt_course(d['bearing'])}. "
    f"Betecknas {d['designation']}. {d['classification'][:1].upper()}{d['classification'][1:]}.",
    "sonar.classified": lambda d: f"{d['designation']} klassas som {d['classification']}.",
    "sonar.bearing": lambda d: f"{d['designation']}, bäring {fmt_course(d['bearing'])}, "
    f"{d['strength']} signal" + {1: ", bäringen drar höger", -1: ", bäringen drar vänster"}
    .get(d.get("drift", 0), "") + ".",
    "sonar.lost": lambda d: f"Kapten, sonar. Har tappat {d['designation']}"
    + (f", sista bäring {fmt_course(d['last_bearing'])}" if d.get("last_bearing") is not None else "")
    + ".",
    "sonar.lost.many": lambda d: "Kapten, sonar. Har tappat "
    + _and([c["designation"] + (f" ({fmt_course(c['last_bearing'])})" if c.get("last_bearing")
                                is not None else "") for c in d["contacts"]]) + ".",
    "sonar.regained": lambda d: f"{d['designation']} hörs igen, bäring {fmt_course(d['bearing'])}.",
    "sonar.regained.many": lambda d: "Kapten, sonar. "
    + _and([f"{c['designation']} ({fmt_course(c['bearing'])})" for c in d["contacts"]]) + " hörs igen.",
    "sonar.ping.first": lambda d: f"Kapten, sonar! Aktiv sonar i bäring {fmt_course(d['bearing'])}"
    f"{_src(d)}. Någon söker." + (f" Svaga pingar, {_far(d)}." if d.get("far") else ""),
    "sonar.ping.fast": lambda d: f"{ru('Tovarisjtj komandir')}, sonar! Pingtakten{_src(d)} har ökat kraftigt. "
    "De har troligen kontakt med oss!" + _only_pings(d),
    "sonar.ping.fast_far": lambda d: f"Kapten, sonar. Pingtakten{_src(d)} har ökat, men pingarna är svaga. "
    f"De jagar något {_far(d)}, inte oss." + _only_pings(d),
    "sonar.ping.slow": lambda d: f"Pingtakten{_src(d)} har minskat igen." + _only_pings(d),
    "sonar.ping.close": lambda d: f"Pingarna{_src(d)} är mycket starka nu, kapten. "
    "Jag hör dem genom skrovet." + _only_pings(d),
    "sonar.splash": lambda d: f"Kapten, sonar! Plask i vattnet, bäring {fmt_course(d['bearing'])}"
    + (", nära!" if d.get("near") else ".") + " Sjunkbomber!",
    "sonar.explosion": lambda d: (
        (f"Små detonationer i bäring {fmt_course(d['bearing'])}. Troligen signalsjunkbomber"
         + (", eller skarpa långt bort." if d.get("quality", 3) <= Quality.OSAKER else "."))
        if d.get("practice") else
        f"Detonation i bäring {fmt_course(d['bearing'])}" + (", mycket nära!" if d.get("near") else "!")
        + (" Skarpa laddningar." if d.get("quality", 0) >= Quality.GOD else "")),
    "sonar.nuclear": lambda d: f"Kapten! Enorm detonation i bäring {fmt_course(d['bearing'])}. "
    "Hela hydrofonen är mättad.",
    "sonar.uwt": lambda d: f"Undervattenstelefon i bäring {fmt_course(d['bearing'])}. "
    + ("De sänder fortfarande, samma uppmaning." if d.get("again") else
       "Morse, upprepat. Jag tror de uppmanar oss att gå till ytan."),
    "sonar.breakup": lambda d: f"Brytningsljud i bäring {fmt_course(d['bearing'])}{_src(d)}. "
    "Skott som ger vika. Ett fartyg sjunker, kapten.",
    "sonar.buoy": lambda d: f"Kapten, sonar. Små plask i bäring {fmt_course(d['bearing'])}, "
    "inget motorljud. Troligen sonobojar från ett flygplan. De lyssnar efter oss.",
    "sonar.buoy_ping": lambda d: f"Kapten, sonar! Korta ljusa pingar i bäring "
    f"{fmt_course(d['bearing'])}, från en fast punkt. Aktiv sonoboj.",
    "sonar.suggest.quiet": lambda d: "Kapten, sonar. Föreslår smygmotor, så hör bojarna oss sämre.",
    "sonar.ice": lambda d: f"Knakande isljud i bäring {fmt_course(d['bearing'])}"
    + (", starkt. Isen skruvar sig nära." if d.get("near") else ". Isen skruvar sig."),
    "sonar.active.none": lambda d: "Aktiv sonar: inga ekon.",
    "sonar.active.echo": lambda d: f"Aktiv sonar: eko {d['designation']} i bäring "
    f"{fmt_course(d['bearing'])}, avstånd {nm(d['range'])} sjömil.",
    "sonar.active.refused": lambda d: f"Kapten, {d['reason']}.",
    "sonar.suggest.layer": lambda d: f"Kapten, sonar. Vi ligger ovanför språngskiktet på "
    f"{d['layer']:.0f} meter. Föreslår djup {d['depth']:.0f}, under skiktet hörs vi sämre.",
    "sonar.suggest.depth_change": lambda d: f"Kapten, sonar. Föreslår djupändring till "
    f"{d['depth']:.0f} meter, " + ("så att laddningarna är inställda på fel djup!"
                                    if d.get("cause") == "charges" else "så att de tappar ekot!"),
    "sonar.suggest.slow": lambda d: f"Kapten, sonar. Vi hör dåligt i {d['speed']:.0f} knop. "
    "Föreslår fart 4.",
}
phrases.register(PHRASES)


STRENGTH_RU = {"svag": "слабый", "tydlig": "чёткий", "stark": "сильный"}


def _ru_src(d: dict) -> str:
    return f" от {R.contact(d['designation'], True)}" if d.get("designation") else ""


def _ru_far(d: dict) -> str:
    return "далеко" if d.get("sure") else "видимо, далеко"


def _ru_only_pings(d: dict) -> str:
    return " Шумов винтов не слышно, только посылки." if d.get("lost") else ""


def _ru_cap(s: str) -> str:
    return s[:1].upper() + s[1:]


RU_PHRASES = {
    "sonar.ambient": lambda d: f"{R.CAPTAIN}, акустик. Шумы моря "
    + ("усилились, слышимость хуже." if d["db"] > 0 else "ослабли, слышимость лучше."),
    "sonar.active.refused": lambda d: f"{R.CAPTAIN}, акустик. Выполнить не могу.",
    "sonar.new_contact": lambda d: f"{R.CAPTAIN}, акустик! Новый контакт, пеленг "
    f"{R.course(d['bearing'])}, {R.contact(d['designation'])}. "
    f"{_ru_cap(R.classification(d['classification']))}.",
    "sonar.classified": lambda d: f"{_ru_cap(R.contact(d['designation']))}: "
    f"{R.classification(d['classification'])}.",
    "sonar.bearing": lambda d: f"{_ru_cap(R.contact(d['designation']))}, пеленг "
    f"{R.course(d['bearing'])}, сигнал {STRENGTH_RU.get(d['strength'], '')}"
    + {1: ", пеленг смещается вправо", -1: ", пеленг смещается влево"}.get(d.get("drift", 0), "")
    + ".",
    "sonar.lost": lambda d: f"{R.CAPTAIN}, акустик. {_ru_cap(R.contact(d['designation']))} потеряна"
    + (f", последний пеленг {R.course(d['last_bearing'])}" if d.get("last_bearing") is not None
       else "") + ".",
    "sonar.lost.many": lambda d: f"{R.CAPTAIN}, акустик. Потеряны: "
    + ", ".join(R.contact(c["designation"]) for c in d["contacts"]) + ".",
    "sonar.regained": lambda d: f"{_ru_cap(R.contact(d['designation']))} снова слышна, пеленг "
    f"{R.course(d['bearing'])}.",
    "sonar.regained.many": lambda d: f"{R.CAPTAIN}, акустик. Снова слышны: "
    + ", ".join(R.contact(c["designation"]) for c in d["contacts"]) + ".",
    "sonar.ping.first": lambda d: f"{R.CAPTAIN}, акустик! Работа гидролокатора, пеленг "
    f"{R.course(d['bearing'])}{_ru_src(d)}. "
    + (f"Посылки слабые, {_ru_far(d)}." if d.get("far") else "Нас ищут."),
    "sonar.ping.fast": lambda d: f"{R.CAPTAIN}, акустик! Темп посылок{_ru_src(d)} резко возрос. "
    "Видимо, они нас обнаружили!" + _ru_only_pings(d),
    "sonar.ping.fast_far": lambda d: f"{R.CAPTAIN}, акустик. Темп посылок{_ru_src(d)} возрос, "
    f"но посылки слабые. Ищут кого-то {_ru_far(d)}, не нас." + _ru_only_pings(d),
    "sonar.ping.slow": lambda d: f"Темп посылок{_ru_src(d)} снова снизился." + _ru_only_pings(d),
    "sonar.ping.close": lambda d: f"Посылки{_ru_src(d)} очень сильные, товарищ командир. "
    "Слышно через корпус." + _ru_only_pings(d),
    "sonar.splash": lambda d: f"{R.CAPTAIN}, акустик! Всплески, пеленг {R.course(d['bearing'])}"
    + (", близко!" if d.get("near") else ".") + " Глубинные бомбы!",
    "sonar.explosion": lambda d: (
        f"Слабые взрывы, пеленг {R.course(d['bearing'])}. Видимо, сигнальные заряды."
        + (" Или боевые, далеко." if d.get("quality", 3) <= Quality.OSAKER else "")
        if d.get("practice") else
        f"Взрыв, пеленг {R.course(d['bearing'])}" + (", очень близко!" if d.get("near") else "!")),
    "sonar.nuclear": lambda d: f"{R.CAPTAIN}! Мощнейший взрыв, пеленг {R.course(d['bearing'])}. "
    "Гидрофоны забиты.",
    "sonar.uwt": lambda d: f"Звукоподводная связь, пеленг {R.course(d['bearing'])}. "
    + ("Всё ещё передают то же." if d.get("again") else "Морзе, повторяют. Думаю, требуют всплыть."),
    "sonar.breakup": lambda d: f"Шумы разрушения корпуса, пеленг {R.course(d['bearing'])}"
    f"{_ru_src(d)}. Переборки не выдерживают. Судно тонет, товарищ командир.",
    "sonar.buoy": lambda d: f"{R.CAPTAIN}, акустик. Слабые всплески, пеленг "
    f"{R.course(d['bearing'])}, шума винтов нет. Видимо, самолёт ставит буи. Нас слушают.",
    "sonar.buoy_ping": lambda d: f"{R.CAPTAIN}, акустик! Короткие высокие посылки, пеленг "
    f"{R.course(d['bearing'])}, из неподвижной точки. Активный буй.",
    "sonar.suggest.quiet": lambda d: f"{R.CAPTAIN}, акустик. Предлагаю перейти на электромотор, "
    "тогда буи нас хуже услышат.",
    "sonar.ice": lambda d: f"Треск льда, пеленг {R.course(d['bearing'])}"
    + (", сильный. Лёд торосится рядом." if d.get("near") else ". Лёд торосится."),
    "sonar.active.none": lambda d: "Активный поиск: эха нет.",
    "sonar.active.echo": lambda d: f"Активный поиск: эхо от {R.contact(d['designation'], True)}, "
    f"пеленг {R.course(d['bearing'])}, дистанция {R.dec(d['range'], R.MILE)}.",
    "sonar.suggest.layer": lambda d: f"{R.CAPTAIN}, акустик. Мы над слоем скачка, он на глубине "
    f"{R.count(d['layer'], R.METER)}. Предлагаю глубину {R.count(d['depth'], R.METER)}, "
    "под слоем нас хуже слышно.",
    "sonar.suggest.depth_change": lambda d: f"Предлагаю сменить глубину на "
    f"{R.count(d['depth'], R.METER)}, " + ("чтобы бомбы были установлены на неверную глубину!"
                                          if d.get("cause") == "charges" else "чтобы они потеряли эхо!"),
    "sonar.suggest.slow": lambda d: f"{R.CAPTAIN}, акустик. На ходу {R.count(d['speed'], R.KNOT)} "
    "слышим плохо. Предлагаю ход четыре узла.",
}
phrases.register_ru(RU_PHRASES)


class SonarRoom(IncomingMixin, RecordingMixin, BafflesMixin, Station):
    REACHES_WORLD = True        # hydrofonerna och aktiv sonar (sensor)
    role = Role.SONAR
    COMMANDS = [
        CommandSpec(r"aktiv sonar|pinga|ping|aktiv", lambda m: ActivePing(), "aktiv sonar"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.sensor = SonarStation(self.member, game.rng_for("sonar"))
        self._incoming_init()
        self._recording_init()
        self._baffles_init()
        self._last_called: dict[str, tuple[float, int]] = {}
        self._pings: dict[str, dict] = {}
        self._unknown_pingers = 0
        self._last_sound: dict[str, int] = {}
        self._uwt_gap: tuple[int, int] = (UWT_FIRST_S, -1)    # (väntan till nästa, senast sagd)
        self.heard: list[HeardEvent] = []          # för djupprofilen
        self.marks: list[HeardMark] = []           # för vattenfallet (med bäring)
        self.lost: list[LostMark] = []
        self.own_marks: list[OwnMark] = []
        self._ambient: float | None = None         # havsbruset sonaren senast sagt (dB)
        self._lost_batch: list[tuple[str, float | None]] = []   # tappade, ännu inte sagda
        self._regained_batch: list[tuple[str, float]] = []      # hörda igen, ännu inte sagda (som de tappade)
        self._regained_t = self._regained_last = 0
        self._lost_t = self._lost_last = 0

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(SoundHeard, self._note_heard)
        bus.subscribe(OwnSoundMade, self._note_own)
        bus.subscribe(ContactLost, self._note_lost)

    # --- djupprofilen ------------------------------------------------------------
    def _note(self, e: HeardEvent) -> None:
        self.heard.append(e)
        cutoff = self.now - PROFILE_KEEP_S
        if self.heard[0].t < cutoff:
            self.heard = [h for h in self.heard if h.t >= cutoff]

    def _note_heard(self, e: SoundHeard) -> None:
        kind = "practice" if e.kind == "explosion" and e.practice else e.kind
        if kind not in HEARD_SYMBOL:
            return
        sym, style = HEARD_SYMBOL[kind]
        near = e.se > (110 if kind == "explosion" else 45 if kind == "splash" else 75)
        self._note(HeardEvent(e.t, kind, sym, style, near))
        self.marks.append(HeardMark(e.t, kind, e.bearing, sym, style, e.designation))
        self.marks = _recent(self.marks, self.now)

    def _note_own(self, e: OwnSoundMade) -> None:
        if e.kind in OWN_SYMBOL:
            sym, style = OWN_SYMBOL[e.kind]
            self._note(HeardEvent(e.t, "own_" + e.kind, sym, style))
            self.own_marks.append(OwnMark(e.t, e.kind, sym))
            self.own_marks = _recent(self.own_marks, self.now)

    def _note_lost(self, e: ContactLost) -> None:
        tr = self.game.knowledge.track(e.designation)
        if tr is None or tr.last_bearing is None:
            return
        self.lost.append(LostMark(e.t, e.designation, tr.last_bearing))
        self.lost = _recent(self.lost, self.now)

    def profile_items(self) -> list:
        items: list = list(self.heard)
        layer = self.world.env.layer_depth
        if layer is not None:
            items.append(Level(layer, "språngskikt", "layer", "─"))
        return items

    # --- sonarvyn -----------------------------------------------------------------
    def sonar_items(self) -> list:
        """Vattenfallet: varje kontakts bäringar som vi tagit dem, det vi hört och tappat,
        och en rad per kontakt med klassning och bäringsdrift (operatörens egen räkning)."""
        cutoff = self.now - WATERFALL_KEEP_S
        items: list = [*self.marks, *self.lost, *self.own_marks, *self.torpedo_traces()]
        for tr in self.game.knowledge.tracks.values():
            obs = [o for o in tr.observations if o.t >= cutoff and o.source in SONAR_SOURCES]
            if not obs:
                continue
            kind = track_kind(tr)
            items.append(BearingTrace(tr.designation,
                                      tuple((o.t, o.bearing, o.se) for o in obs), kind, tr.held))
            if not tr.held and self.now - obs[-1].t > LINE_AFTER_LOST_S:
                continue
            sol = tr.solution
            drift = bearing_drift([(o.t, o.bearing) for o in obs if o.source == "sonar"],
                                  self.now) if tr.held else None
            items.append(ContactLine(tr.designation, tr.classification, tr.class_quality,
                                     obs[-1].bearing, drift,
                                     sol.quality if sol is not None else None, kind, tr.held))
        return items

    # --- systemtavlan ------------------------------------------------------------
    def system_items(self) -> list:
        held = self.held_designations()
        k = self.game.knowledge
        threats = [d for d in held if (tr := k.track(d)) is not None and tr.threat]
        noise, ice = self.background()
        items = [Gauge("SONAR", "Kontakter", contacts_text(held, len(threats)),
                       WARN if threats else INFO if held else OK),
                 Gauge("SONAR", "Bakgrund", f"{noise:.0f} dB" + (", isbrus" if ice else ""), INFO)]
        if self.own.sys.health["sonar"] < 0.5:
            items.append(Gauge("SONAR", "Aktiv sonar", "ur bruk, skadad", WARN))
        return items

    def held_designations(self) -> list[str]:
        return self.sensor.held_designations()

    def status_fields(self) -> dict:
        """Kontakterna sonar håller (hot först, ur kunskapens klassning) och bruset i lurarna."""
        held, kinds = held_by_kind(self.held_designations(), self.game.knowledge.track)
        bearings = []
        for d in held:
            tr = self.game.knowledge.track(d)
            bearings.append(tr.last_bearing if tr is not None else None)
        return {"contacts_held": held, "contact_kinds": kinds, "contact_bearings": tuple(bearings),
                "sea_noise": self.sensor.background, "under_ice": self.sensor.under_ice}

    def background(self) -> tuple[float, bool]:
        """Bakgrundsbruset i lurarna: (dB, kommer från isen)."""
        return self.sensor.background, self.sensor.under_ice


    # --- order -------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        if isinstance(order, ActivePing):
            self._active_ping()

    def _active_ping(self) -> None:
        world, own = self.world, self.own
        if own.sys.health["sonar"] < 0.3:
            self.say("sonar.active.refused", {"reason": "sonaren är skadad"})
            return
        o = own.state
        world.emit(Transient("ping", o.x, o.y, o.depth, acoustics.PING_LEVEL_OWN, own.id, self.now))
        self.game.bus.publish(OwnSoundMade(self.now, "ping"))
        world.mission["own_pings"] = world.mission.get("own_pings", 0) + 1
        noise = acoustics.power_sum(world.background_at_own(), own.self_noise())
        own_xy = self.game.own_position_estimate()
        rng = self.sensor.rng
        echoes = []
        for v in world.contacts:
            if v.side == "own" or v.sunk or not v.is_ship:
                continue
            tl = world.tl_to_own(v.state.x, v.state.y, v.depth)
            se = acoustics.active_excess(acoustics.PING_LEVEL_OWN, tl, v.target_strength,
                                         noise, self.sensor.threshold(world)) + rng.gauss(0, 2)
            if se <= 0:
                continue
            r = world.true_range(v)
            desig = self.sensor.designate(v.id)
            if self.game.knowledge.tracks.get(desig) is None:
                self.game.bus.publish(ContactDetected(self.now, desig, world.true_bearing(v),
                                                      "eko, okänd typ", Quality.DALIG))
            r_meas = max(0.05, r + rng.gauss(0, 0.02 * r + 0.02))
            obs = BearingObs(self.now, norm360(world.true_bearing(v) + rng.gauss(0, 1.0)), 1.0,
                             own_xy[0], own_xy[1], o.course, se=se, designation=desig,
                             range_nm=r_meas, range_sigma=0.02 * r + 0.02, source="aktiv")
            self.game.bus.publish(BearingObserved(self.now, obs))
            echoes.append({"designation": desig, "bearing": obs.bearing, "range": r_meas})
        if not echoes:
            self.say("sonar.active.none")
        calls = SweepCalls(self, "active")       # många ekon: en rad och en tabell
        for e in echoes:
            calls.add("sonar.active.echo", e, kind="contact", quality=Quality.SAKER)
        calls.flush(force=True)

    # --- löpande -----------------------------------------------------------------
    def _ambient_watch(self) -> None:
        """Havsbruset i hydrofonerna (vädret): sonaren säger till när det ändrats märkbart.
        Inte under isen (där är det isens brus, som ändras med platsen)."""
        if self.world.env.ice is not None:
            return
        n = self.world.background_at_own()
        if self._ambient is None:
            self._ambient = n
        elif abs(n - self._ambient) >= AMBIENT_REPORT_DB:
            self.say("sonar.ambient", {"db": n - self._ambient})
            self._ambient = n

    def _mark_recorded(self, designation: str) -> None:
        """Inspelningen klar (recording.py): sanningens bokföring för uppdragsmålet, vilket
        fartyg bandet har. Rapporterna nämner bara beteckningen."""
        for v in self.world.contacts:
            if self.sensor.designation_of(v.id) == designation:
                self.world.mission.setdefault("recorded", []).append(v.id)
                return

    def update(self) -> None:
        bus = self.game.bus
        if self.now % AMBIENT_EVERY_S == 0:
            self._ambient_watch()
        self._recording_watch()
        self._baffles_watch()
        own_xy = self.game.own_position_estimate()
        for ev in self.sensor.update(self.world, own_xy):
            match ev:
                case Detection():
                    known = self.game.knowledge.tracks.get(ev.designation)
                    bus.publish(ContactDetected(self.now, ev.designation, ev.bearing,
                                                ev.classification, ev.quality))
                    self._last_called[ev.designation] = (ev.bearing, self.now)
                    if any(d == ev.designation for d, _ in self._lost_batch):
                        # tappad och hörd igen innan det sagts: ingenting att säga
                        self._lost_batch = [x for x in self._lost_batch if x[0] != ev.designation]
                        continue
                    if known is not None:
                        if not self._regained_batch:
                            self._regained_t = self.now
                        self._regained_batch.append((ev.designation, ev.bearing))
                        self._regained_last = self.now
                        continue
                    self.say("sonar.new_contact",
                             {"designation": ev.designation, "bearing": ev.bearing,
                              "classification": ev.classification},
                             kind="contact", quality=ev.quality, alarm=True)
                    self._suggest_layer()
                case ClassificationUpdate():
                    tr = self.game.knowledge.tracks.get(ev.designation)
                    if tr is not None and tr.class_quality > ev.quality:
                        continue        # utkiken (periskop, brygga) har redan sett bättre
                    bus.publish(ClassificationChanged(self.now, ev.designation,
                                                      ev.classification, ev.quality))
                    self.say("sonar.classified",
                             {"designation": ev.designation, "classification": ev.classification},
                             kind="contact", quality=ev.quality)
                case Lost():
                    bus.publish(ContactLost(self.now, ev.designation))
                    tr = self.game.knowledge.tracks.get(ev.designation)
                    if tr is not None and tr.sunk:
                        continue        # den sjönk: brytningsljudet är redan rapporterat
                    if any(d == ev.designation for d, _ in self._regained_batch):
                        # hörd igen och tappad innan det sagts: ingenting att säga
                        self._regained_batch = [x for x in self._regained_batch if x[0] != ev.designation]
                        continue
                    if not self._lost_batch:
                        self._lost_t = self.now
                    self._lost_batch.append((ev.designation, tr.last_bearing if tr else None))
                    self._lost_last = self.now
                    if self.own.state.speed > 6 and not self.game.knowledge.hunted(self.now) \
                            and not self.own.bridge_open:   # i ytläge ser bryggan
                        self.suggest("slow", "sonar.suggest.slow",
                                     {"speed": self.own.state.speed}, order="fart 4", cooldown=600)
                case BearingObs():
                    bus.publish(BearingObserved(self.now, ev))
                    if ev.source == "sonar":
                        self._maybe_call_bearing(ev.designation)
                case TransientHeard():
                    self._on_sound(ev)
                case IncomingTorpedo():
                    self._on_incoming(ev)
                case OwnTorpedo():
                    # Torpedrummet rapporterar egna torpeder med tubnummer.
                    q = Quality.GOD if ev.se >= 6 else Quality.OSAKER
                    bus.publish(OwnTorpedoHeard(self.now, ev.no, ev.kind, ev.bearing, q, ev.se))
        if self._lost_batch and (self.now - self._lost_last >= LOST_BATCH_S
                                 or self.now - self._lost_t >= LOST_BATCH_MAX_S):
            self._say_lost()
        if self._regained_batch and (self.now - self._regained_last >= LOST_BATCH_S
                                     or self.now - self._regained_t >= LOST_BATCH_MAX_S):
            self._say_regained()

    def _say_lost(self) -> None:
        """De tappade kontakterna: en rad för en, en samlad rad för flera (t.ex. under skiktet)."""
        batch, self._lost_batch = self._lost_batch, []
        if len(batch) == 1:
            d, b = batch[0]
            self.say("sonar.lost", {"designation": d, "last_bearing": b}, kind="contact")
        else:
            self.say("sonar.lost.many", {"contacts": [{"designation": d, "last_bearing": b}
                                                      for d, b in batch]}, kind="contact")

    def _say_regained(self) -> None:
        """Kontakterna som hörs igen: en rad för en, en samlad rad för flera (vi kom under skiktet
        eller ur döda sektorn: krig-kort gav sex rader samma minut)."""
        batch, self._regained_batch = self._regained_batch, []
        if len(batch) == 1:
            d, b = batch[0]
            self.say("sonar.regained", {"designation": d, "bearing": b}, kind="contact")
        else:
            self.say("sonar.regained.many", {"contacts": [{"designation": d, "bearing": b} for d, b in batch]},
                     kind="contact")

    def idle_proposals(self) -> list[Proposal]:
        st, env = self.own.state, self.world.env
        held = self.game.knowledge.threat_held()
        out = []
        d = self._below_layer(env.layer_depth) if env.layer_depth is not None else None
        if held and d is not None and st.ordered_depth < env.layer_depth \
                and not self._up_for_radio() and not self.own.surfaced and not self.own.bridge_open:
            out.append(Proposal(2, "idle_layer", "sonar.suggest.layer",
                                f"djup {d:.0f}", {"layer": env.layer_depth, "depth": d}))
        # inte under jakt: då vill maskin springa (Kuba frö 31: fart 4, och 25 s senare fart 16)
        if not held and st.ordered_speed > 6 and not self.own.bridge_open and \
                not self.game.knowledge.hunted(self.now):
            out.append(Proposal(4, "idle_slow", "sonar.suggest.slow", "fart 4",
                                {"speed": st.ordered_speed}))
        return out

    def _depth_limit(self) -> float | None:
        """Navigatörens gräns mot botten (sjökortet och ekolodet), om den finns."""
        from .navigation import NavigationStation
        try:
            return self.game.station(NavigationStation).depth_limit()
        except KeyError:
            return None

    def _below_layer(self, layer: float) -> float | None:
        """Djup under skiktet som botten tillåter, eller None om det inte finns plats."""
        if self.own.sys.settle or self.own.sys.on_bottom:
            return None                     # vi ligger på (eller går ned mot) botten
        d = layer + 60
        lim = self._depth_limit()
        if lim is not None:
            d = min(d, lim)
        return d if d >= layer + 20 else None

    def _up_for_radio(self) -> bool:
        """Ligger vi uppe för ett sambandstillfälle som inte är avklarat? Då föreslår sonar
        inte skiktet, så länge fienden inte har oss."""
        from .radio import RadioStation
        try:
            radio = self.game.station(RadioStation)
        except KeyError:
            return False
        return radio.needs_mast() and not self.game.knowledge.hunted(self.now)

    def layer_depth(self) -> float | None:
        """Språngskiktet som sonar mäter det (badytermografen)."""
        return self.world.env.layer_depth

    def _suggest_layer(self) -> None:
        env, st = self.world.env, self.own.state
        if "inspelning" in self.game.knowledge.order_tasks:
            return                  # vi ska lyssna, inte gömma oss: under skiktet hörs målet sämre
        if self.own.surfaced or self.own.bridge_open:
            return                  # i ytläge med folk på bryggan: att dyka är vakthavandes och bryggans sak
        if env.layer_depth is not None and st.ordered_depth < env.layer_depth \
                and not self._up_for_radio():
            d = self._below_layer(env.layer_depth)
            if d is None:
                return
            self.suggest("layer", "sonar.suggest.layer", {"layer": env.layer_depth, "depth": d},
                         order=f"djup {d:.0f}", cooldown=1800)

    def _dedupe(self, key: str, window: int) -> bool:
        if self.now - self._last_sound.get(key, -10**9) < window:
            return False
        self._last_sound[key] = self.now
        return True

    def classify_charge(self, ev: TransientHeard) -> tuple[bool, Quality]:
        """Skarp eller signalladdning ur den mottagna nivån och vad plottet vet om avståndet
        till den som fällde den. (skarp, kvalitet)."""
        signal_max = CHARGE_SIGNAL_DB - 20 * math.log10(CHARGE_MIN_M) + CHARGE_MARGIN_DB
        if ev.rl >= signal_max:
            return True, Quality.SAKER
        tr = self.game.knowledge.track(ev.designation) if ev.designation else None
        sol = tr.solution if tr is not None else None
        if sol is not None and sol.quality >= Quality.OSAKER:
            r_m = max(sol.range_nm * 1852.0, CHARGE_MIN_M)
            s_m = sol.range_sigma * 1852.0
            tl = 20 * math.log10(r_m)
            real = abs(ev.rl - (CHARGE_REAL_DB - tl)) < abs(ev.rl - (CHARGE_SIGNAL_DB - tl))
            spread = 20 * math.log10((r_m + s_m) / max(r_m - s_m, CHARGE_MIN_M))
            a, b, c = CHARGE_TL_SIGMA_Q
            q = Quality.SAKER if spread < a else Quality.GOD if spread < b else \
                Quality.OSAKER if spread < c else Quality.DALIG
            return real, q
        return False, Quality.OSAKER

    def _on_sound(self, ev: TransientHeard) -> None:
        bus = self.game.bus
        d = {"bearing": ev.bearing, "designation": ev.designation}
        detail = ""
        if ev.kind == "ping":
            # okända pingare hålls isär på bäringen: två jagare i skärm är inte en snabb pingare
            # bäringen brusar ett par grader per ping och pingaren rör sig: närmaste inom grinden
            # en ping utan beteckning kan också vara en känd pingare som sonar just tappat som
            # kontakt: den behåller sin nyckel (annars "Någon söker" igen mitt i jakten)
            unknown, best = None, None
            for k, q in self._pings.items():
                if not k.startswith("okänd") and (
                        ev.designation or q["last"] is None or self.now - q["last"] > PING_KNOWN_S):
                    continue
                since = self.now - q["last"] if q["last"] is not None else 0
                # där pingaren borde vara nu efter sin egen bäringsdrift (ett nära fartyg som passerar
                # drar 0,8°/s: sundet frö 51 gav fem "Någon söker" och fem stridslarm på två minuter)
                expected = norm360(q.get("bearing", ev.bearing)
                                   + q.get("rate", 0.0) * min(since, PING_RATE_HORIZON_S))
                off = abs(angle_diff(expected, ev.bearing))
                if ev.rl >= PING_NEAR_RL:
                    # en nära pingare kan svänga fort i bäring (245 → 326 på 90 s förbi oss)
                    gate = min(PING_SAME_MAX_NEAR_DEG, PING_SAME_DEG + PING_DRIFT_NEAR_DEG_PER_S * since)
                else:
                    gate = min(PING_SAME_MAX_DEG, PING_SAME_DEG + PING_DRIFT_DEG_PER_S * since)
                # två jagare nära samma bäring: operatören skiljer dem på styrkan (jagad-kort frö 51
                # slog ihop dem, och den som passerade över oss blev "Någon söker" igen)
                cost = off + PING_LEVEL_DEG_PER_DB * abs(ev.rl - q.get("rl", ev.rl))
                if off <= gate and (best is None or cost < best):
                    unknown, best = k, cost
            if unknown is None and not ev.designation:
                self._unknown_pingers += 1
            key = ev.designation or unknown or f"okänd{self._unknown_pingers}"
            if not key.startswith("okänd"):
                d["designation"] = key           # den kända pingaren, också när kontakten tappats
                tr = self.game.knowledge.tracks.get(key)
                if tr is not None and not tr.held:
                    d["lost"] = True             # vi hör bara pingarna, inte maskinerna
            if key not in self._pings and unknown and ev.designation and unknown.startswith("okänd"):
                self._pings[key] = self._pings.pop(unknown)      # samma pingare, nu identifierad
            p = self._pings.setdefault(key, {"last": None, "fast": False, "close_t": -10**9,
                                             "slow_n": 0, "hunting": False})
            p["rl"] = ev.rl if "rl" not in p else p["rl"] + PING_LEVEL_SMOOTH * (ev.rl - p["rl"])
            # utjämnad bäring: en enstaka brusig ping drar inte iväg grinden
            if "bearing" not in p or p["last"] is None or self.now - p["last"] > PING_RATE_HORIZON_S:
                p["bearing"] = ev.bearing
                p.pop("rate", None)
            else:
                dt = max(1, self.now - p["last"]) if p["last"] is not None else 1
                expected = norm360(p["bearing"] + p.get("rate", 0.0) * dt)
                new = norm360(expected + PING_SMOOTH * angle_diff(ev.bearing, expected))
                rate = angle_diff(new, p["bearing"]) / dt      # driften ur den utjämnade bäringen
                rate = rate if "rate" not in p else (1 - PING_RATE_GAIN) * p["rate"] + PING_RATE_GAIN * rate
                p["rate"] = max(-PING_RATE_MAX, min(PING_RATE_MAX, rate))
                p["bearing"] = new
            near, sure = self._ping_near(ev.rl)
            if p["last"] is None or self.now - p["last"] > 900:
                if near:
                    self.say("sonar.ping.first", d, kind="contact", alarm=True)
                else:               # svaga pingar: någon söker långt bort, inget larm
                    self.say("sonar.ping.first", {**d, "far": True, "sure": sure}, kind="contact",
                             quality=Quality.GOD if sure else Quality.OSAKER)
                self._suggest_layer()
            else:
                interval = self.now - p["last"]
                # en missad ping ger ett långt mellanrum: minskad takt först efter två i rad
                p["slow_n"] = p["slow_n"] + 1 if interval >= SLOW_PING_S else 0
                if interval <= FAST_PING_S and not p["fast"]:
                    p["fast"] = True
                    detail = "fast"
                    # den jagar något, men långt bort: inte oss (en gång per jakt, högst var 15:e min)
                    if not near and self.now - p.get("far_t", -10**9) > PING_FAR_REPORT_S:
                        p["far_t"] = self.now
                        self.say("sonar.ping.fast_far", {**d, "sure": sure}, kind="contact",
                                 quality=Quality.GOD if sure else Quality.OSAKER)
                elif p["slow_n"] >= 2 and p["fast"]:
                    if p["hunting"]:    # en avlägsen jakt som ebbar ut är inget att ropa om
                        self.say("sonar.ping.slow", d, kind="contact")
                    p["fast"] = p["hunting"] = False
                if p["fast"] and near and not p["hunting"]:
                    # snabb takt och starka pingar: de har troligen kontakt med oss
                    p["hunting"] = True
                    self.say("sonar.ping.fast", d, kind="contact", alarm=True)
                    self._evasive_depth(cause="ping")
            if p["hunting"]:
                bus.publish(HuntSigns(self.now, "ping"))
            if ev.se > 75 and self.now - p["close_t"] > p.get("close_gap", CLOSE_FIRST_S):
                # glesare för varje gång under samma jakt (2,5 h med samma rad var 5:e min förut)
                p["close_gap"] = CLOSE_FIRST_S if self.now - p["close_t"] > CLOSE_RESET_S \
                    else min(p.get("close_gap", CLOSE_FIRST_S) * 2, CLOSE_MAX_S)
                p["close_t"] = self.now
                self.say("sonar.ping.close", d, kind="contact")
            p["last"] = self.now
        elif ev.kind == "splash":
            if self._dedupe("splash", 20):
                self.say("sonar.splash", {**d, "near": ev.se > 45}, kind="contact", alarm=True)
                bus.publish(HuntSigns(self.now, "splash"))
                self._evasive_depth(cooldown=60, cause="charges")
        elif ev.kind == "explosion":
            if ev.se > 160:
                if self._dedupe("nuclear", 60):
                    self.say("sonar.nuclear", d, kind="contact", alarm=True)
            elif ev.own_weapon:
                pass                    # torpedrummet rapporterar sina egna träffar
            else:
                real, q = self.classify_charge(ev)
                practice = not real
                near = ev.se > NEAR_SE
                bus.publish(ChargeHeard(self.now, real, q, near, "sonar", ev.bearing))
                if self._dedupe("explosion", 10):
                    self.say("sonar.explosion", {**d, "practice": practice, "near": near,
                                                 "quality": q.value}, kind="contact",
                             alarm=not practice, quality=q)
        elif ev.kind == "buoy":
            if self._dedupe("buoy", 300):
                self.say("sonar.buoy", d, kind="contact", alarm=True)
                if self.own.sys.propulsion == "turbine":
                    self.suggest("quiet", "sonar.suggest.quiet", order="smygmotor", cooldown=900)
        elif ev.kind == "buoy_ping":
            if self._dedupe("buoy_ping", 600):
                self.say("sonar.buoy_ping", d, kind="contact", alarm=True)
                self._evasive_depth(cause="ping")
        elif ev.kind == "ice":
            if self._dedupe("ice", ICE_REPORT_S):
                self.say("sonar.ice", {**d, "near": ev.se > 25}, kind="contact",
                         quality=Quality.GOD if ev.se > 10 else Quality.OSAKER)
        elif ev.kind == "doors":
            if self._dedupe("doors", 60):
                self._on_doors(ev.bearing)
        elif ev.kind == "uwt":
            gap, last = self._uwt_gap
            if self.now - last > UWT_RESET_S:
                gap = UWT_FIRST_S                   # en ny omgång: säg det som första gången
            if self.now - last >= gap or last < 0:
                again = 0 <= last and self.now - last <= UWT_RESET_S
                self._uwt_gap = (min(gap * 2, UWT_MAX_S) if again else UWT_FIRST_S, self.now)
                self.say("sonar.uwt", {**d, "again": again}, kind="contact")
            else:
                self._uwt_gap = (gap, last)
        elif ev.kind == "breakup":
            if self._dedupe(f"breakup{ev.designation}", 60):
                # brytningsljudet följer på detonationen; rapportera det efter den
                self.say("sonar.breakup", d, kind="contact", alarm=True, extra_delay=6)
            if ev.designation:
                # den sjunker: dess pingar finns inte mer (andras pingar i samma bäring är inte dess)
                self._pings.pop(ev.designation, None)
                bus.publish(ContactSunk(self.now, ev.designation))
        practice = ev.kind == "explosion" and not ev.own_weapon and ev.se <= 160 and \
            not self.classify_charge(ev)[0]
        bus.publish(SoundHeard(self.now, ev.kind, ev.bearing, ev.designation, practice, detail,
                               se=ev.se))

    def _ping_near(self, rl: float) -> tuple[bool, bool]:
        """Är pingaren nära nog att jaga oss? Operatören bedömer på styrkan (mottagen nivå), med
        tumregeln att skiktet tar PING_LAYER_DB när vi ligger under det. Ger (nära, säker): säker
        när styrkan är minst ett skikt från gränsen, så att ett felbedömt skikt inte ändrar svaret."""
        ld = self.layer_depth()
        level = rl + (PING_LAYER_DB if ld is not None and self.own.state.depth > ld else 0.0)
        return level >= PING_NEAR_RL, abs(level - PING_NEAR_RL) >= PING_LAYER_DB

    def _evasive_depth(self, cooldown: int = 300, cause: str = "ping") -> None:
        d = self._evasive_target()
        if d is None:
            return
        self.suggest("evade_depth", "sonar.suggest.depth_change", {"depth": d, "cause": cause},
                     order=f"djup {d:.0f}", cooldown=cooldown, alarm=True)

    def _evasive_target(self) -> float | None:
        """Ett nytt djup att byta till för att gömma sig (skiktet, eller långt från nuvarande)."""
        st = self.own.state
        if self.own.sys.settle or self.own.sys.on_bottom:
            return None
        env = self.world.env
        if env.layer_depth is not None and st.ordered_depth < env.layer_depth:
            d = env.layer_depth + 60
        elif st.ordered_depth < 200:
            d = min(st.ordered_depth + 80, 280)
        elif st.ordered_speed > acoustics.cavitation_speed(st.ordered_depth - 80):
            d = min(st.ordered_depth + 60, 280)     # grundare skulle vi kavitera i den här farten
        else:
            d = st.ordered_depth - 80
            if env.layer_depth is not None:
                # uppåt bara till under skiktet: över det hör jagaren oss igen
                d = max(d, env.layer_depth + 60)
                if abs(d - st.ordered_depth) < 20:
                    d = min(st.ordered_depth + 60, 280)
        lim = self._depth_limit()
        if lim is not None and d > lim:
            d = lim
            if abs(d - st.ordered_depth) < 20:
                return None                 # botten ger inget utrymme att byta djup
        return d

    def _maybe_call_bearing(self, designation: str) -> None:
        tr = self.game.knowledge.tracks.get(designation)
        if tr is None or not tr.observations:
            return
        recent = [o for o in tr.observations if o.source == "sonar"][-SMOOTH_OBS:]
        if not recent:
            return
        bearing = circular_mean([o.bearing for o in recent])
        prev, prev_t = self._last_called.get(designation, (None, -10**9))
        delta = angle_diff(bearing, prev) if prev is not None else 0.0
        if abs(delta) < BEARING_REPORT_DELTA and self.now - prev_t < BEARING_REPORT_MAX_AGE:
            return
        if self.now - prev_t < BEARING_MIN_GAP_S:
            return
        self._last_called[designation] = (bearing, self.now)
        se = sum(o.se for o in recent) / len(recent)
        self.say("sonar.bearing",
                 {"designation": designation, "bearing": bearing,
                  "strength": "svag" if se < 2 else "tydlig" if se < 6 else "stark",
                  "drift": 0 if abs(delta) < 2 else (1 if delta > 0 else -1)},
                 kind="contact")
