"""Vakthavande officer: radar, radarvarnare (ESM) och kamera. Periskopet är en egen
station (periscope.py) som vakthavande också sköter.

Allt här kräver periskopdjup och exponerar ubåten: periskop och radar kan
upptäckas av jagarens radar och utkik, och radarsändning pejlas på långt håll.

Vakthavande håller också vakten när kaptenen är tyst: efter QUIET_S sekunder
utan inmatning och utan att någon annan föreslagit något samlar han
stationernas idle_proposals() och låter den station som har det viktigaste
förslaget säga det. Högst ett sådant förslag per QUIET_S, inget medan ett
annat förslag väntar, och ingen order som redan föreslagits inom REPEAT_S.

Ber kaptenen om förslag ("förslag", "förslag sonar", "annat förslag") svarar
vakthavande direkt ur samma kandidater, utan att vänta eller spärra upprepning.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import phrases
from ..crew import ROLE_LABEL, Role
from ..entities import Emission
from ..events import (AirRadarHeard, BearingObserved, Handover, ClassificationChanged,
                      ContactDetected, PhotoTaken)
from ..knowledge import AIR_CLOSE
from ..fmt import count, fmt_course, kn, nm
from ..geo import angle_diff, bearing_to, distance, norm360
from ..orders import AskSuggestion, CommandSpec, Order
from ..ownship import PERISCOPE_DEPTH
from ..periscope import SightedObject
from ..reports import Quality
from .. import russian as R
from ..russian import ru
from ..tma import BearingObs
from .base import Proposal, Station
from .sonar_room import SonarRoom

BIG_SHIP_WORDS = ("stort", "transport", "tank")   # sonarns klassning av stora fartyg (mål)


def is_big_ship(track) -> bool:
    """Ett stort fartyg som inte är civilt: en trolig transport eller tanker (ett mål)."""
    return not track.civil and any(w in track.classification for w in BIG_SHIP_WORDS)


RADAR_S = 10
RADAR_RANGE_NM = 12.0
ESM_REPEAT_S = 1800        # radarvarnaren ropar ut samma radar igen först efter så här lång tid,
ESM_MOVED_DEG = 15.0       # eller när styrkan ändrats eller den flyttat sig så här mycket i bäring
AIR_ESM_NM = 40.0          # flygradar hörs så här långt
AIR_STRENGTHS = ("svag", "medel", "stark", "mycket stark")
QUIET_S = 600              # tystnad från kaptenen innan besättningen tar initiativ
IDLE_RETRY_S = 60          # om ingen station hade något att föreslå
REPEAT_S = 1200            # samma order föreslås inte igen inom denna tid
LOOK_INTERVAL_S = 900      # på periskopdjup utan kontakt: titta så här ofta
CONVOY_LOOK_S = 240        # konvojen känd: en kort titt mot den så här ofta (utkiken ger kursen)
FIRE_LOOK_NM = 3.5         # ett stort fartyg så nära enligt plottet: snart skjutläge
FIRE_LOOK_S = 90           # ... då en titt före skottet om förra titten på det är så här gammal
CONVOY_STEP_S = 30
PHOTO_TASK_NM = 3.5         # så nära den meddelade ankarplatsen föreslår vakthavande en titt
PHOTO_LOOK_S = 180          # och en ny titt så här ofta
HUSH_SPEED_KN = 6          # tystnad i båten: jagade och högst så här fort (eller smygmotorn)
HUSH_LIFT_S = 60           # tystnaden hävs när det varit lugnt eller fort så här länge
ESCORT_CLOSE_NM = 3.0      # en jagare så nära: föreslå inte att gå upp
ESM_STRONG_S = 300         # mycket stark radar så nyligen: föreslå inte att gå upp
HUNTED_UP_DEPTH = 50       # jagade: ingen föreslår att gå så här grunt (master, flytkabeln, fix)
SMOKE_MUST_VENT = 0.7      # så tät rök: ventilationen går före jakten (maskins larmgräns)


@dataclass(frozen=True)
class RadarSweep(Order):
    pass


@dataclass(frozen=True)
class Situation(Order):
    """`läget`: vakthavande sammanfattar djup, kurs, fart, kontakter och besticket."""


@dataclass(frozen=True)
class Photograph(Order):
    pass


PHOTO_S = 40               # periskopet uppe medan kameran arbetar
# bildens kvalitet efter avstånd (nm) till närmaste fartyg vid ankarplatsen: dag, natt
PHOTO_RANGES = {True: ((1.2, Quality.SAKER), (2.2, Quality.GOD), (3.5, Quality.OSAKER)),
                False: ((0.6, Quality.GOD), (1.2, Quality.OSAKER))}
PHOTO_TARGET_KIND = "moored"


# vad utkiken ser i periskopet: (klassning till plottet, ord i rapporten)
SIGHTED = {"destroyer": ("jagare, amerikansk", "jagare"),
           "merchant": ("handelsfartyg", "handelsfartyg"),
           "patrol": ("patrullbåt, amerikansk", "patrullbåt"),
           "guardship": ("bevakningsfartyg, sovjetiskt", "bevakningsfartyg"),
           "moored": ("fartyg till ankars", "fartyg till ankars"),
           "transport": ("trupptransport, amerikansk", "trupptransport"),
           "tanker": ("tankfartyg, amerikanskt", "tankfartyg"),
           "ssbn": ("Polarisubåt i ytläge, amerikansk", "ubåt i ytläge"),
           "fishing": ("fiskebåt", "fiskebåt")}


def mast_refusal(station, what: str) -> str | None:
    """Varför masten inte kan komma upp nu (eget läge och egna instrument), annars None."""
    own = station.own
    st, sys = own.state, own.sys
    if st.depth > PERISCOPE_DEPTH:
        return f"vi måste upp på periskopdjup för {what}"
    if st.speed > 7 and not own.surfaced:      # i ytläge ger masten inget svall
        return "farten är för hög, periskopet vibrerar och ger svall"
    if sys.health["periscope"] < 0.3:
        return "periskopet och masterna är skadade"
    if not station.masts_free:
        return "det är is ovanför, masterna kommer inte upp"
    return None


def _view_object(type_: str, d: dict) -> SightedObject | None:
    """Hamnskyddets nät (spawnarnas periscope_view) som föremål i bilden."""
    if type_ == "off.periscope.net":
        return SightedObject("net", "bojrad", d["bearing"], d["range"], Quality.OSAKER,
                             detail="grinden öppen" if d["gate_open"] else "grinden stängd")
    return None


def _minutes_old(s: int) -> str:
    m = round(s / 60)
    return "en minut" if m <= 1 else f"{m} minuter"


def _names(ds: list[str]) -> str:
    return ds[0] if len(ds) == 1 else ", ".join(ds[:-1]) + " och " + ds[-1]


def _briefing(d: dict) -> str:
    """Lägesrapporten när kaptenen tar befälet efter vakten före (kort variant)."""
    return " ".join([f"Kapten, vakthavande. Ni har befälet. Vi har gått i {d['minutes']} minuter, "
                     f"nu djup {d['depth']:.0f} meter, kurs {fmt_course(d['course'])}, "
                     f"fart {kn(d['speed'])} knop."] + situation(d))


def situation(d: dict) -> list[str]:
    """Konvoj, kontakter och besticket ur briefing_data(), mening för mening."""
    out: list[str] = []
    c = d.get("convoy")
    if c:
        line = (f"Plottet har konvojen: {_names(c['members'])}"
                + (f", med eskort {_names(c['escorts'])}" if c["escorts"] else "")
                + f". Mitten i bäring {fmt_course(c['bearing'])}, cirka {nm(c['range'])} sjömil")
        if c["quality"] is not None:
            line += (f", baskurs {fmt_course(c['course'])}, fart {kn(round(c['speed']))} knop, "
                     f"bedömningen {Quality(c['quality']).label}.")
        else:
            line += (f", nuvarande ben kurs cirka {fmt_course(round(c['course'] / 5) * 5)}, "
                     f"fart cirka {kn(round(c['speed']))} knop. Baskursen har vi inte ännu.")
        out.append(line)
    for t in d["contacts"]:
        where = f"bäring {fmt_course(t['bearing'])}"
        if t.get("range") is not None:
            where += f", cirka {nm(t['range'])} sjömil ({Quality(t['quality']).label})"
        out.append(f"{t['designation']}, {t['label']}, {where}.")
    if d["civil"]:
        out.append(f"Dessutom {count(d['civil'], 'civilt fartyg', 'civila fartyg')} i plottet.")
    if not c and not d["contacts"]:
        out.append("Inga kontakter just nu.")
    if d.get("sigma") is not None:
        out.append(f"Bestickets osäkerhet {nm(d['sigma'])} sjömil.")
    return out


BATTLE_CALM_S = 1800        # så länge utan jakttecken innan nytt stridslarm
BATTLE_DELAY_S = 6          # vakthavande ropar efter sonars rapport

PHRASES = {
    "off.hush": lambda d: "Tystnad i båten. Inga verktyg, inga luckor, bara det nödvändiga. "
    "Rapporterna lågt.",
    "off.hush.end": lambda d: "Tystnaden hävd. Normal gång i båten.",
    "off.briefing": _briefing,
    "off.situation": lambda d: " ".join([
        f"Kapten, vakthavande. Djup {d['depth']:.0f} meter, kurs {fmt_course(d['course'])}, "
        f"fart {kn(d['speed'])} knop."] + situation(d)),
    "off.refused": lambda d: f"Kapten, {d['reason']}.",
    "off.battle_stations": lambda d: f"{ru('Boevaja trevoga')}! Stridslarm, alla man till "
    "stridsstationerna. Fienden har troligen kontakt med oss.",
    "off.periscope.net": lambda d: f"Periskop: rad av små bojar tvärs farleden, närmast i bäring "
    f"{fmt_course(d['bearing'])}, cirka {nm(d['range'])} sjömil. Ett nät! Grinden i bäring "
    f"{fmt_course(d['gate_bearing'])} är " + ("öppen." if d["gate_open"] else "stängd."),
    "off.photo.start": lambda d: "Periskop upp, kameran klar. Fotograferar.",
    "off.photo.aborted": lambda d: "Kapten, vi kom under periskopdjup. Inga bilder.",
    "off.photo.nothing": lambda d: "Kapten, bilderna visar inget. "
    + ("Ankarplatsen är för långt bort." if d.get("far") else "Inga fartyg i sikte.")
    + ("" if d["day"] else " Det är för mörkt."),
    "off.photo.done": lambda d: f"Bilder tagna, kapten. {count(d['count'], 'fartyg', 'fartyg').capitalize()} till ankars på cirka "
    f"{nm(d['range'])} sjömil. Bildkvaliteten är {d['quality']}"
    + ("." if d["day"] else ", i mörker.") + " Periskop ner.",
    "off.suggest.photo_up": lambda d: f"Kapten, vakthavande. Enligt besticket är vi cirka "
    f"{nm(d['range'])} sjömil från ankarplatsen. Föreslår periskopdjup för en titt och bilder"
    + ("." if d["day"] else ", men i mörkret måste vi nära."),
    "off.suggest.photo_look": lambda d: f"Kapten, vakthavande. Ankarplatsen bör ligga cirka "
    f"{nm(d['range'])} sjömil bort. Föreslår ett periskopsvep.",
    "off.suggest.photo": lambda d: f"Kapten, vakthavande. Ankarplatsen är cirka {nm(d['range'])} "
    f"sjömil bort, nära nog för {d['quality']} bild. Föreslår fotografering.",
    "off.radar.start": lambda d: "Radar sänder. Ett svep.",
    "off.radar.contact": lambda d: f"Radar: {d['designation']} i bäring {fmt_course(d['bearing'])}, "
    f"avstånd {nm(d['range'])} sjömil.",
    "off.radar.none": lambda d: "Radar: inga ekon inom tolv sjömil.",
    "off.esm.same": lambda d: "Radarvarnare: " + ("samma radar som förut." if d["n"] == 1 else
                                                  f"samma {d['n']} radarstationer som förut."),
    "off.esm": lambda d: f"Radarvarnare: radar i bäring {fmt_course(d['bearing'])}, "
    f"signal {d['strength']}." + (" De kan se våra master!" if d['strength'] == "mycket stark" else ""),
    "off.esm.air": lambda d: f"Radarvarnare: flygradar i bäring {fmt_course(d['bearing'])}, "
    f"signal {d['strength']}. Bäringen drar snabbt, det är ett flygplan."
    + (" Det är nära, kapten!" if d['strength'] == "mycket stark" else ""),
    "off.suggest.down": lambda d: f"Kapten, vakthavande. {d['reason']} Föreslår djup "
    f"{d['depth']:.0f}.",
    "off.suggest.none": lambda d: (
        f"Kapten, vakthavande. {d['station']} har inget att föreslå just nu." if d.get("station")
        else "Kapten, vakthavande. Inget annat att föreslå just nu." if d.get("other")
        else "Kapten, vakthavande. Inga förslag just nu" + (", läget är lugnt." if d.get("calm", True) else ".")),
    "off.suggest.look": lambda d: "Kapten, vakthavande. Vi är på periskopdjup och har inte "
    "tittat på en stund. Föreslår ett periskopsvep.",
    "off.suggest.convoy_up": lambda d: "Kapten, vakthavande. Sonar hör stora fartyg, men bara "
    "utkiken ser vart de styr. Föreslår periskopdjup för en titt.",
    "off.suggest.convoy_look": lambda d: f"Kapten, vakthavande. Föreslår en kort titt mot "
    f"{d['designation']}, så att plottet får kursen ur vinkeln på bogen.",
    "off.suggest.fire_look": lambda d: f"Kapten, vakthavande. {d['designation']} är "
    f"{nm(d['range'])} sjömil bort, snart skjutläge. "
    + (f"Senaste titten på det är {_minutes_old(d['age'])} gammal. " if d["age"] is not None
       else "Vi har inte sett det i periskopet. ")
    + "Föreslår en titt före skottet, så att lösningen är färsk."
    + (f" Obs, jagare {d['escort']} på {nm(d['escort_range'])} sjömil: masten kan synas."
       if d.get("escort") else ""),
}
phrases.register(PHRASES)


def _briefing_ru(d: dict) -> str:
    out = f"{R.CAPTAIN}, вахтенный офицер. Вахту сдал, командование ваше."
    c = d.get("convoy")
    if c:
        out += (f" Конвой: {R.count(len(c['members']), ('судно', 'судна', 'судов'))}"
                f" и {R.count(len(c['escorts']), ('эсминец', 'эсминца', 'эсминцев'))}, "
                f"пеленг {R.course(c['bearing'])}, дистанция {R.dec(c['range'], R.MILE)}.")
    elif d["contacts"]:
        out += f" На планшете {R.count(len(d['contacts']), ('цель', 'цели', 'целей'))}."
    else:
        out += " Контактов нет."
    return out


STRENGTH_RU = {"svag": "слабый", "medel": "средний", "stark": "сильный",
               "mycket stark": "очень сильный"}
LABEL_RU = {q.label: R.QUALITY_RU[int(q)] for q in Quality}
_OFF = f"{R.CAPTAIN}, вахтенный офицер."


def _down_reason_ru(d: dict) -> str:
    why = d.get("why")
    if why == "air":
        return "Авиационный радар близко, могут увидеть наши выдвижные. "
    if why == "esm":
        return "Сигнал радара очень сильный. "
    if why == "aircraft":
        return "Вижу самолёт. "
    if why == "close":
        return f"{R.contact(d.get('designation', '')).capitalize()} близко. "
    return ""


def _none_ru(d: dict) -> str:
    if d.get("station"):
        return f"{_OFF} Других предложений нет."
    if d.get("other"):
        return f"{_OFF} Больше предложений нет."
    return f"{_OFF} Предложений нет" + (", обстановка спокойная." if d.get("calm", True) else ".")


RU_PHRASES = {
    "off.hush": lambda d: "Тишина в отсеках! Доклады вполголоса.",
    "off.hush.end": lambda d: "Режим тишины отменён.",
    "off.refused": lambda d: f"{_OFF} Выполнить не могу.",
    "off.esm.same": lambda d: "Станция предупреждения: те же радары, что и раньше.",
    "off.esm": lambda d: f"Станция предупреждения: радар, пеленг {R.course(d['bearing'])}, "
    f"сигнал {STRENGTH_RU[d['strength']]}."
    + (" Они могут видеть наши выдвижные!" if d["strength"] == "mycket stark" else ""),
    "off.esm.air": lambda d: f"Станция предупреждения: авиационный радар, пеленг "
    f"{R.course(d['bearing'])}, сигнал {STRENGTH_RU[d['strength']]}. Пеленг быстро меняется, "
    "это самолёт." + (f" Он близко, {R.CAPTAIN.lower()}!" if d["strength"] == "mycket stark" else ""),
    "off.suggest.down": lambda d: f"{_OFF} {_down_reason_ru(d)}Предлагаю погрузиться на "
    f"{R.count(d['depth'], R.METER)}.",
    "off.radar.start": lambda d: "Есть, радар излучает. Один оборот.",
    "off.radar.contact": lambda d: f"Радар: {R.contact(d['designation'])}, пеленг "
    f"{R.course(d['bearing'])}, дистанция {R.dec(d['range'], R.MILE)}.",
    "off.radar.none": lambda d: "Радар: целей в пределах двенадцати миль нет.",
    "off.periscope.net": lambda d: f"Перископ: ряд малых буёв поперёк фарватера, ближайший пеленг "
    f"{R.course(d['bearing'])}, около {R.dec(d['range'], R.MILE)}. Это сеть! Ворота, пеленг "
    f"{R.course(d['gate_bearing'])}, " + ("открыты." if d["gate_open"] else "закрыты."),
    "off.photo.start": lambda d: "Есть, перископ поднят, фотоаппарат готов. Снимаем.",
    "off.photo.aborted": lambda d: f"{_OFF} Ушли с перископной глубины. Снимков нет.",
    "off.photo.nothing": lambda d: f"{_OFF} На снимках ничего нет. "
    + ("Якорная стоянка слишком далеко." if d.get("far") else "Судов не видно.")
    + ("" if d["day"] else " Слишком темно."),
    "off.photo.done": lambda d: f"Снимки сделаны, {R.CAPTAIN.lower()}. "
    f"{R.count(d['count'], ('судно', 'судна', 'судов'))} на якоре, около "
    f"{R.dec(d['range'], R.MILE)}. Качество снимков {LABEL_RU[d['quality']]}"
    + ("." if d["day"] else ", в темноте.") + " Перископ опустить.",
    "off.suggest.photo_up": lambda d: f"{_OFF} До якорной стоянки около {R.dec(d['range'], R.MILE)}. "
    "Предлагаю всплыть под перископ, осмотреться и фотографировать.",
    "off.suggest.photo_look": lambda d: f"{_OFF} Якорная стоянка примерно в "
    f"{R.dec(d['range'], R.MILE)}. Предлагаю осмотреться в перископ.",
    "off.suggest.photo": lambda d: f"{_OFF} До якорной стоянки около {R.dec(d['range'], R.MILE)}, "
    f"можно снять, качество будет {LABEL_RU[d['quality']]}. Предлагаю фотографировать.",
    "off.suggest.look": lambda d: f"{_OFF} Мы на перископной глубине и давно не смотрели. "
    "Предлагаю осмотреться в перископ.",
    "off.suggest.none": _none_ru,
    "off.briefing": _briefing_ru,
    "off.situation": lambda d: f"{R.CAPTAIN}, вахтенный офицер. Докладываю обстановку.",
    "off.battle_stations": lambda d: "Боевая тревога! Боевая тревога! Противник, видимо, "
    "обнаружил нас.",
    "off.suggest.convoy_up": lambda d: f"{R.CAPTAIN}, вахтенный офицер. Слышим большие суда. "
    "Предлагаю всплыть на перископную глубину и посмотреть.",
    "off.suggest.convoy_look": lambda d: f"{R.CAPTAIN}, вахтенный офицер. Предлагаю короткий "
    f"взгляд в перископ на {R.contact(d['designation'], True)}.",
    "off.suggest.fire_look": lambda d: f"{R.CAPTAIN}, вахтенный офицер. "
    f"{R.contact(d['designation']).capitalize()}, дистанция {R.dec(d['range'], R.MILE)}. "
    f"Предлагаю взгляд в перископ перед залпом."
    + (f" Внимание, эсминец {R.contact(d['escort'])} рядом." if d.get("escort") else ""),
}
phrases.register_ru(RU_PHRASES)


class OfficerStation(Station):
    REACHES_WORLD = True        # radarn, radarvarnaren och kameran (sensorer)
    role = Role.OFFICER
    MAST_ORDERS = (RadarSweep, Photograph)
    COMMANDS = [
        CommandSpec(r"radar|radarsvep", lambda m: RadarSweep(), "radar"),
        CommandSpec(r"läget|laget|hur är läget\??|hur ar laget\??|situationen", lambda m: Situation(),
                    "läget (vakthavande sammanfattar)"),
        CommandSpec(r"foto|fotografera|ta bilder|ta foto|kamera", lambda m: Photograph(), "foto"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.rng = game.rng_for("officer")
        self.radar_done_t: int | None = None
        self.photo_done_t: int | None = None
        self._esm_last: dict[str, tuple[str, int]] = {}      # radar: styrka, när hörd (flyg: när sagd)
        self._esm_said: dict[str, tuple[str, int, float]] = {}   # fartygsradar: styrka, när sagd, bäring
        self._next_esm = 0
        self._esm_fresh = True      # första svepet efter att vi kommit upp: sammanfatta de kända
        self._idle_t = -10**9       # senaste initiativ (eller försök) vid tystnad
        self._hunt_seen = -10**9    # senaste jakttecken vakthavande har tagit ställning till
        self.hushed = False         # tystnad i båten: jagade och vi smyger
        self._hush_off_t: int | None = None


    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(Handover, self._on_handover)
        self.game.queue.filters.append(self._hush_filter)

    def vetoes(self, order: str) -> bool:
        """Har fienden oss föreslår ingen att gå upp: periskop- och antenndjup, ytläge, fix,
        öppningen i isen och ventilation väntar tills jakten är över (nödblåsning och tät rök undantagna)."""
        if super().vetoes(order):
            return True
        if self._radar_sees_masts() and self._goes_to_periscope(order):
            return True     # mycket stark radar nyss: masterna syns (fixen tas mot botten i stället)
        if not self.game.knowledge.hunted(self.now) or self.own.sys.smoke >= SMOKE_MUST_VENT:
            return False
        from ..orders import split_orders
        from .engineering import Ventilate
        from .navigation.common import GoToOpening, SetDepth, TakeFix
        ordered = self.own.state.ordered_depth
        for part in split_orders(order):
            o = self.game.registry.parse(part)
            if isinstance(o, (TakeFix, GoToOpening, Ventilate)):
                return True
            if isinstance(o, SetDepth) and o.depth <= HUNTED_UP_DEPTH and o.depth < ordered:
                return True
        return False

    def _radar_sees_masts(self) -> bool:
        """En radar har varit mycket stark de senaste ESM_STRONG_S: masterna kan ses."""
        return any(strength == "mycket stark" and self.now - t <= ESM_STRONG_S
                   for strength, t in self._esm_last.values())

    def _goes_to_periscope(self, order: str) -> bool:
        """Tar ordern oss upp till periskopdjup (eller är det en fix i periskopet)?"""
        from ..orders import split_orders
        from .navigation.common import SetDepth, TakeFix
        ordered = self.own.state.ordered_depth
        for part in split_orders(order):
            o = self.game.registry.parse(part)
            if isinstance(o, TakeFix):
                return True
            if isinstance(o, SetDepth) and 1 <= o.depth <= PERISCOPE_DEPTH + 1 and o.depth < ordered:
                return True
        return False

    # --- tystnad i båten -----------------------------------------------------------
    def _quiet_wanted(self) -> bool:
        """Jagade och vi smyger (smygmotorn eller låg fart, under ytan): då viskar man."""
        own = self.own
        return self.game.knowledge.hunted(self.now) and not own.surfaced and \
            own.state.depth > 20 and (own.sys.propulsion == "electric" or own.state.speed <= HUSH_SPEED_KN)

    def _hush_watch(self) -> None:
        if self._quiet_wanted():
            self._hush_off_t = None
            if not self.hushed:
                self.say("off.hush", kind="info")     # sägs innan filtret slår till: lågt men tydligt
                self.hushed = True
        elif self.hushed:
            # hävs när läget hållit i sig en stund, så att en kort fartökning inte väcker båten
            if self._hush_off_t is None:
                self._hush_off_t = self.now
            elif self.now - self._hush_off_t >= HUSH_LIFT_S:
                self.hushed = False
                self._hush_off_t = None
                self.say("off.hush.end", kind="info")

    def _hush_filter(self, r):
        """Rapportfilter: i tystnaden talar besättningen lågt (larm ropas ändå)."""
        if self.hushed and not r.alarm and r.kind != "system" and r.role:
            r.data["hushed"] = True
        return r

    # --- överlämnandet efter vakten före kaptenen ---------------------------------
    def _on_handover(self, e: Handover) -> None:
        self.say("off.briefing", self.briefing_data(e.warm_s // 60))

    def situation_report(self) -> None:
        self.say("off.situation", self.briefing_data(0))

    def briefing_data(self, minutes: int) -> dict:
        """Läget ur kunskapen och egna instrument: konvoj, kontakter, besticket."""
        k, now, st = self.game.knowledge, self.game.now, self.own.state
        ox, oy = self.game.own_position_estimate()
        d: dict = {"minutes": minutes, "depth": st.depth, "course": st.course,
                   "speed": round(st.speed), "contacts": [], "civil": 0, "convoy": None}
        c = k.convoy
        if c is not None:
            x, y, vx, vy = c.advance(now)
            base = c.base if c.base is not None and c.base.quality >= Quality.OSAKER else None
            d["convoy"] = {
                "members": list(c.members), "escorts": list(c.escorts),
                "bearing": bearing_to(ox, oy, x, y), "range": distance(ox, oy, x, y),
                "course": base.course if base else c.leg_course,
                "speed": base.speed if base else c.leg_speed,
                "quality": int(base.quality) if base else None}
        for tr in sorted(k.tracks.values(), key=lambda t: t.first_t):
            if not tr.held or (c is not None and c.contains(tr.designation)):
                continue
            if tr.civil:
                d["civil"] += 1
                continue
            b = tr.last_bearing
            if b is None:
                continue
            sol = tr.solution
            good = sol is not None and sol.quality >= Quality.OSAKER
            d["contacts"].append({"designation": tr.designation, "label": tr.classification,
                                  "bearing": b, "range": sol.range_nm if good else None,
                                  "quality": int(sol.quality) if good else None})
        try:
            from .navigation import NavigationStation
            d["sigma"] = self.game.station(NavigationStation).uncertainty()
        except KeyError:
            pass
        return d

    def _periscope(self):
        from .periscope import PeriscopeWatch
        return self.game.station(PeriscopeWatch)

    def _sonar(self) -> SonarRoom:
        return self.game.station(SonarRoom)

    def _check_mast(self, what: str) -> str | None:
        return mast_refusal(self, what)

    def on_order(self, order: Order) -> None:
        sys = self.own.sys
        match order:
            case AskSuggestion(role=role, other=other):
                self._answer_request(Role(role) if role else None, other)
            case Situation():
                self.situation_report()
            case Photograph():
                if reason := self._check_mast("periskopet"):
                    self.say("off.refused", {"reason": reason})
                    return
                sys.periscope_until = max(sys.periscope_until, self.now + PHOTO_S)
                self.photo_done_t = self.now + PHOTO_S
                self.say("off.photo.start", kind="ack")
            case RadarSweep():
                if reason := self._check_mast("radarn"):
                    self.say("off.refused", {"reason": reason})
                    return
                o = self.own.state
                sys.radar_until = self.now + RADAR_S
                self.world.emit_em(Emission("radar", o.x, o.y, self.own.id, self.now))
                self.radar_done_t = self.now + RADAR_S
                self.say("off.radar.start", kind="ack")

    def _battle_watch(self) -> None:
        """Stridslarm när sonar hör att fienden har oss, om det var lugnt en halvtimme."""
        ht = self.game.knowledge.hunt_t
        if ht <= self._hunt_seen:
            return
        if ht - self._hunt_seen > BATTLE_CALM_S:
            self.say("off.battle_stations", kind="info", alarm=True, extra_delay=BATTLE_DELAY_S)
        self._hunt_seen = ht

    # --- initiativ när kaptenen är tyst ------------------------------------------
    def _idle_watch(self) -> None:
        g = self.game
        since = max(g.last_command_t, g.last_suggestion_t, self._idle_t)
        if self.now - since < QUIET_S:
            return
        if g.active_suggestion() is not None or g.queue.has_kind("suggest"):
            return
        for st, p in self._candidates():
            if self.now - g.suggested_at.get(p.order, -10**9) < REPEAT_S:
                continue
            if st.propose(p):
                self._idle_t = self.now
                g.log(f"INITIATIV efter tystnad: {p.key} -> {p.order!r}")
                return
        self._idle_t = self.now - QUIET_S + IDLE_RETRY_S

    def _candidates(self, role: Role | None = None) -> list[tuple[Station, Proposal]]:
        """Alla stationers förslag, viktigast först (lika prioritet: stationsordning)."""
        out = [(p.priority, i, st, p) for i, st in enumerate(self.game.stations)
               if role is None or st.role == role for p in st.idle_proposals()]
        return [(st, p) for _, _, st, p in sorted(out, key=lambda c: (c[0], c[1]))]

    def _answer_request(self, role: Role | None, other: bool) -> None:
        g = self.game
        active = g.active_suggestion()
        skip = active[0] if (other and active) else None
        for st, p in self._candidates(role):
            if p.order == skip:
                continue
            # kaptenen frågade: ingen väntan och ingen spärr mot upprepning
            if st.suggest(p.key, p.type, p.data, order=p.order, cooldown=0, quality=p.quality):
                g.log(f"FÖRSLAG på begäran: {p.key} -> {p.order!r}")
                return
        k = g.knowledge
        self.say("off.suggest.none",
                 {"station": ROLE_LABEL[role] if role else None, "other": other,
                  "calm": not k.hunted(self.now) and not k.threat_held() and not k.torpedo_alarm(self.now)})

    def _convoy_watch(self) -> None:
        """Konvojen känd: utkiken ger plottet kursen, så föreslå periskopdjup och korta tittar.
        Nära skjutläget en titt före skottet, också med en jagare nära (risken sägs)."""
        k = self.game.knowledge
        c = k.convoy
        big = [t for t in k.tracks.values() if t.held and is_big_ship(t)]
        if (c is None and not big) or k.hunted(self.now):
            return
        escort = self._escort_close()
        held_back = escort is not None or \
            any(strength == "mycket stark" and self.now - t <= ESM_STRONG_S
                for strength, t in self._esm_last.values())
        st = self.own.state
        if st.depth > PERISCOPE_DEPTH + 1:
            if not held_back:
                self.suggest("convoy_up", "off.suggest.convoy_up", order="periskopdjup",
                             cooldown=600)
            return
        if self._periscope().busy or st.speed > 7:
            return
        if self._fire_look(big, escort):
            return
        if not held_back and self.now - self._periscope().last_look_t >= CONVOY_LOOK_S:
            d = c.members[0] if c is not None and c.members else big[0].designation
            self.suggest("convoy_look", "off.suggest.convoy_look", {"designation": d},
                         order=f"periskop {d}", cooldown=CONVOY_LOOK_S)

    def _fire_look(self, big, escort: tuple[str, float] | None) -> bool:
        """Det närmaste stora fartyget inom FIRE_LOOK_NM enligt plottet (lösning ≥ osäker):
        föreslå en titt på det om förra titten är äldre än FIRE_LOOK_S. Sant om ett fartyg är
        så nära (då föreslås inga vanliga konvojtittar)."""
        near = [(r, tr) for tr in big
                if (r := self._predicted_range(tr, Quality.OSAKER)) is not None and r <= FIRE_LOOK_NM]
        if not near:
            return False
        r, tr = min(near, key=lambda n: n[0])
        looks = [o.t for o in tr.observations if o.course_obs is not None]
        age = self.now - looks[-1] if looks else None
        if age is None or age >= FIRE_LOOK_S:
            d = tr.designation
            data = {"designation": d, "range": r, "age": age}
            if escort is not None:
                data["escort"], data["escort_range"] = escort
            self.suggest(f"fire_look{d}", "off.suggest.fire_look", data,
                         order=f"periskop {d}", cooldown=FIRE_LOOK_S)
        return True

    def _predicted_range(self, tr, min_quality: Quality | None = None) -> float | None:
        """Avståndet till kontakten nu enligt plottets lösning, framräknad (kunskap)."""
        sol = tr.solution
        if sol is None or not tr.held or (min_quality is not None and sol.quality < min_quality):
            return None
        ex, ey = self.game.own_position_estimate()
        dt = (self.now - sol.t) / 3600.0
        x, y = sol.x + sol.state[2] * dt, sol.y + sol.state[3] * dt
        return math.hypot(x - ex, y - ey)

    def _escort_close(self) -> tuple[str, float] | None:
        """Närmaste klassade jagare inom ESCORT_CLOSE_NM enligt plottet: (beteckning, avstånd)."""
        close = [(r, tr.designation) for tr in self.game.knowledge.tracks.values()
                 if "jagare" in tr.classification
                 and (r := self._predicted_range(tr)) is not None and r < ESCORT_CLOSE_NM]
        if not close:
            return None
        r, d = min(close)
        return d, r

    def idle_proposals(self) -> list[Proposal]:
        st = self.own.state
        held = self.game.knowledge.threat_held()
        if st.depth <= PERISCOPE_DEPTH and not held and st.speed <= 7 and \
                not self.own.bridge_open and \
                not self.game.knowledge.ice.under_ice(self.now) and \
                self.now - self._periscope().last_look_t >= LOOK_INTERVAL_S and \
                self._periscope().mode is None:
            return [Proposal(5, "idle_look", "off.suggest.look", "periskop", cooldown=900)]
        return []

    def _observe(self, v, bearing_sigma: float, range_sigma: float, source: str,
                 label: str, velocity=None) -> dict:
        """En observation till plottet. velocity(): periskopets bedömning
        (kurs, σ, fart, σ), dras efter bäring och avstånd."""
        world, rng = self.world, self.rng
        sonar = self._sonar().sensor
        desig = sonar.designate(v.id)
        bearing = norm360(world.true_bearing(v) + rng.gauss(0, bearing_sigma))
        r = world.true_range(v)
        r_meas = max(0.05, r + rng.gauss(0, range_sigma))
        course = c_sig = speed = s_sig = None
        if velocity is not None:
            course, c_sig, speed, s_sig = velocity()
        tr = self.game.knowledge.tracks.get(desig)
        if tr is None:
            self.game.bus.publish(ContactDetected(self.now, desig, bearing, label, Quality.GOD))
        elif source == "periskop" and tr.class_quality < Quality.GOD:
            # det vi ser i periskopet slår sonarens gissning
            self.game.bus.publish(ClassificationChanged(self.now, desig, label, Quality.GOD))
        ex, ey = self.game.own_position_estimate()
        self.game.bus.publish(BearingObserved(self.now, BearingObs(
            self.now, bearing, bearing_sigma, ex, ey, self.own.state.course,
            designation=desig, range_nm=r_meas, range_sigma=range_sigma, source=source,
            course_obs=course, course_sigma=c_sig or 0.0, speed_obs=speed,
            speed_sigma=s_sig or 0.0)))
        d = {"designation": desig, "bearing": bearing, "range": r_meas}
        if velocity is not None:
            d.update(course=course, speed=speed)
        return d

    def _photo_targets(self):
        world = self.world
        return [v for v in world.contacts if v.kind == PHOTO_TARGET_KIND and not v.sunk]

    def _photo_quality(self, r: float) -> Quality | None:
        day = self.world.env.daylight(self.now)
        for limit, q in PHOTO_RANGES[day]:
            if r <= limit:
                return q
        return None

    def _photo_done(self) -> None:
        world = self.world
        if self.own.state.depth > PERISCOPE_DEPTH + 1:
            self.say("off.photo.aborted")
            return
        targets = self._photo_targets()
        if not targets:
            self.say("off.photo.nothing", {"day": world.env.daylight(self.now)})
            return
        r = min(world.true_range(v) for v in targets)
        q = self._photo_quality(r)
        if q is None:
            self.say("off.photo.nothing", {"day": world.env.daylight(self.now), "far": True})
            return
        n = sum(1 for v in targets if world.true_range(v) <= r + 1.0)
        world.mission["best_photo"] = max(world.mission.get("best_photo", -1), int(q))
        world.mission.setdefault("photos", []).append((self.now, int(q)))
        self.game.bus.publish(PhotoTaken(self.now, q, "ankarplatsen"))
        self.say("off.photo.done", {"range": r * self.rng.uniform(0.9, 1.1), "count": n,
                                    "quality": q.label, "day": world.env.daylight(self.now)},
                 quality=q)

    def _photo_task_watch(self) -> None:
        """Staben vill ha ett foto (`foto` i ordern): nära den meddelade ankarplatsen föreslår
        vakthavande periskopdjup och en titt (bilden föreslås efter svepet, `_suggest_photo`)."""
        k = self.game.knowledge
        if "foto" not in k.order_tasks or k.task_place is None or k.hunted(self.now) or \
                k.photo_t is not None and k.photo_t >= k.order_tasks_t and \
                k.best_photo is not None and k.best_photo >= Quality.OSAKER:
            return
        wp = k.waypoints.get(k.task_place)
        if wp is None:
            return
        ex, ey = self.game.own_position_estimate()
        wx, wy = wp.at(self.now)
        r = distance(ex, ey, wx, wy)
        if r > PHOTO_TASK_NM + wp.sigma(self.now):
            return
        st = self.own.state
        d = {"range": r, "day": self.world.env.daylight(self.now)}
        if st.ordered_depth > PERISCOPE_DEPTH:
            self.suggest("photo_up", "off.suggest.photo_up", d, order="periskopdjup", cooldown=600)
        elif st.depth <= PERISCOPE_DEPTH + 0.5 and self._periscope().mode is None and \
                self.now - self._periscope().last_look_t >= PHOTO_LOOK_S:
            self.suggest("photo_look", "off.suggest.photo_look", d, order="periskop", cooldown=300)

    def _suggest_photo(self) -> None:
        """Efter ett periskopsvep: ankarplatsen nära nog för en bättre bild än vi har."""
        world = self.world
        targets = self._photo_targets()
        if not targets:
            return
        r = min(world.true_range(v) for v in targets)
        q = self._photo_quality(r)
        best = self.game.knowledge.best_photo
        if q is None or (best is not None and q <= best):
            return
        self.suggest("photo", "off.suggest.photo", {"range": r, "quality": q.label},
                     order="foto", cooldown=300, quality=q)

    def _esm_air(self) -> None:
        """Flygradar: stark på långt håll, och bäringen drar snabbt."""
        world, rng = self.world, self.rng
        strongest = None
        for v in world.contacts:
            if v.kind != "aircraft" or v.gone:
                continue
            r = world.true_range(v)
            if r > AIR_ESM_NM:
                continue
            strength = ("mycket stark" if r < 4 else "stark" if r < 10
                        else "medel" if r < 20 else "svag")
            if strongest is None or AIR_STRENGTHS.index(strength) > AIR_STRENGTHS.index(strongest):
                strongest = strength
            prev = self._esm_last.get(v.id)
            close = strength in AIR_CLOSE
            if prev is None or prev[0] != strength or self.now - prev[1] > 600:
                self._esm_last[v.id] = (strength, self.now)
                b = norm360(world.true_bearing(v) + rng.gauss(0, 3))
                self.say("off.esm.air", {"bearing": b, "strength": strength}, kind="contact",
                         alarm=close)
            if close and (d := self.dive_depth(60)) is not None:   # också när vi kommer upp igen
                self.suggest("down_air", "off.suggest.down",
                             {"reason": "Flygradar, nära. De kan se våra master.", "why": "air", "depth": d},
                             order=f"djup {d}", cooldown=120, alarm=True)
        self.game.bus.publish(AirRadarHeard(self.now, strongest))

    def _surface_ships(self):
        return [v for v in self.world.contacts
                if v.side != "own" and v.is_ship and not v.sunk and v.depth < 10]

    def update(self) -> None:
        world, st, rng = self.world, self.own.state, self.rng
        self._idle_watch()
        self._battle_watch()
        self._hush_watch()
        if self.now % CONVOY_STEP_S == 0:
            self._convoy_watch()
            self._photo_task_watch()
        if self.photo_done_t is not None and self.now >= self.photo_done_t:
            self.photo_done_t = None
            self._photo_done()

        if self.radar_done_t is not None and self.now >= self.radar_done_t:
            self.radar_done_t = None
            hits = [v for v in self._surface_ships() if world.true_range(v) <= RADAR_RANGE_NM]
            if not hits:
                self.say("off.radar.none")
            for v in hits:
                r = world.true_range(v)
                d = self._observe(v, 1.0, 0.01 * r + 0.01, "radar", "ytfartyg (radar)")
                self.say("off.radar.contact", d, kind="contact", quality=Quality.SAKER)

        # radarvarnare: automatiskt på periskopdjup
        if st.depth > PERISCOPE_DEPTH + 1:
            self._esm_fresh = True              # nästa svep är det första efter att vi kommit upp
        if st.depth <= PERISCOPE_DEPTH + 1 and self.now >= self._next_esm:
            self._next_esm = self.now + 10
            self._esm_air()
            known = 0
            for v in self._surface_ships():
                if not v.has_radar:
                    continue
                r = world.true_range(v)
                if r > 30:
                    continue
                strength = ("mycket stark" if r < 4 else "stark" if r < 8
                            else "medel" if r < 15 else "svag")
                true_b = world.true_bearing(v)
                self._esm_last[v.id] = (strength, self.now)
                prev = self._esm_said.get(v.id)
                if prev is not None and prev[0] == strength and self.now - prev[1] <= ESM_REPEAT_S \
                        and abs(angle_diff(true_b, prev[2])) <= ESM_MOVED_DEG:
                    known += 1                  # samma radar som förut: ropas inte ut igen
                else:
                    self._esm_said[v.id] = (strength, self.now, true_b)
                    b = norm360(true_b + rng.gauss(0, 3))
                    self.say("off.esm", {"bearing": b, "strength": strength}, kind="contact",
                             alarm=strength == "mycket stark")
                if strength == "mycket stark" and (d := self.dive_depth(60)) is not None and \
                        self._suggested.get("down_air", -10**9) < self.now - 5:
                    # (inte samma sekund som flygradarns förslag om samma djup: ett räcker)
                    self.suggest("down_esm", "off.suggest.down",
                                 {"reason": "Radarn är mycket stark.", "why": "esm", "depth": d},
                                 order=f"djup {d}", cooldown=300, alarm=True)
            if self._esm_fresh and known:
                self.say("off.esm.same", {"n": known}, kind="contact")
            self._esm_fresh = False
