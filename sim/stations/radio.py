"""Radio: sambandstillfällen med huvudstaben och rapportsändning.

Staben sänder vid sambandstillfällena enligt schemat; det vi missar sänds om vid nästa.
Mottagning: på antenndjup med masten (en minut), eller på djupet på långvåg med flytkabeln
(högst VLF_DEPTH meter och VLF_SPEED knop, fem minuter; kabeln flyter inte under is).
Långvågen kommer in hel eller stympad (`_vlf_quality`: mörker, låg fart och grunt hjälper);
stympat visas med oläsbara grupper och radion lyssnar vidare på omsändningen.
Sändning (kortvåg) kräver periskopdjup och kan pejlas av fienden.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import phrases
from .. import russian as R
from ..crew import Role
from ..entities import Emission
from ..broadcasts import broadcasts_for, order_day
from ..dispatch import SentReport, compose, report_text
from ..headquarters import MAX_PER_WINDOW, Headquarters
from ..events import (Handover, InterceptHeard, NuclearOrderRead, OwnActionLogged, OwnTorpedoHeard, PhotoTaken, PositionReported,
                      ReportTransmitted, TelegramReceived)
from ..fmt import fmt_course, nm
from ..geo import angle_diff, distance
from ..icemap import thickness_words
from ..orders import DESIG, CommandSpec, Order, desig
from ..reports import Quality
from ..ownship import ANTENNA_DEPTH, PERISCOPE_DEPTH
from ..profile import Cable, Level
from ..systems import INFO, OK, WARN, Gauge
from .base import Proposal, Station
from .navigation import NavigationStation

RECEIVE_S = 60
RISK_LONG_S = 45             # så lång sändning: pejlas med god noggrannhet
RISK_MID_S = 25
RISK_NEAR_NM = 8.0           # en hotkontakt så nära i plottet: hör sändningen
RISK_MID_NM = 15.0
PREWARN_S = 600
RADIO_SAFE_NM = 5.0          # en hotkontakt närmare än så enligt plottet: vänta med att gå upp
REPORT_SUGGEST_S = 180       # förslaget att sända upprepas högst så här ofta
AIR_QUIET_S = 120            # så länge efter flygradar nära innan radion föreslår att gå upp igen
AIR_LEFT_S = 150             # minst så mycket kvar av fönstret: upp från djupet och trettio sekunder sändning
INTERCEPT_S = 60             # radiospaning: så länge radiomannen avlyssnar trafiken
INTERCEPT_AIR_NM = 150       # flygradion hörs så långt (VHF/UHF från höjd)
INTERCEPT_SHIP_NM = 60       # fartygens radiotelefoni
INTERCEPT_AGAIN_S = 1800     # radiomannen föreslår en ny avlyssning högst så här ofta
INTERCEPT_HUNT_S = 600       # jagarna har haft kontakt så nyss: deras trafik är livlig
LISTEN_S = 20                # så länge radiomannen letar upp Moskva på kortvåg
RADIO_VAK_MAX_M = 2500        # öppningar längre bort hinner vi inte till
VLF_DEPTH = 50.0             # flytkabeln: djupare än så räcker den inte till ytan
VLF_SPEED = 5.0              # fortare än så dras kabeln under
VLF_UP_DEPTH = 40            # radiomannen föreslår det här djupet för långvågen
VLF_SLOW_KN = 3              # och den här farten
VLF_RECEIVE_S = 300          # långvågen är långsam: så länge tar mottagningen
GARBLE_P = 0.45              # stympad: så stor del av grupperna går förlorade


@dataclass(frozen=True)
class SendReport(Order):
    kind: str = "full"              # full, short (läge och det som hänt), contact (en kontakt)
    target: str | None = None


@dataclass(frozen=True)
class RadioStatus(Order):
    pass


@dataclass(frozen=True)
class ListenBroadcast(Order):
    pass


@dataclass(frozen=True)
class Intercept(Order):
    """Radiospaning: avlyssna amerikansk trafik på antenndjup."""


KIND_SV = {"full": "rapporten", "short": "kort rapport", "contact": "rapport om kontakten"}
KIND_RU = {"full": "донесение", "short": "короткое донесение", "contact": "донесение о цели"}
RISK_RU = {"liten": "малый", "måttlig": "умеренный", "stor": "большой"}


def _groups(n: int) -> str:
    return f"{n} grupp" if n == 1 else f"{n} grupper"


def _contacts_sv(n: int) -> str:
    return "en kontakt" if n == 1 else f"{n} kontakter"


def _intercept_sv(d: dict) -> str:
    parts = []
    if d["air"]:
        parts.append("amerikansk flygradio, " + ("ett plan" if d["air"] == 1 else
                                                 f"{d['air']} plan") + " i luften i området")
    if d["ships"]:
        parts.append("radiotelefoni från " + ("ett örlogsfartyg" if d["ships"] == 1 else
                                              f"{d['ships']} örlogsfartyg"))
    if d["hunting"]:
        parts.append("jagarna rapporterar kontakt till varandra, de söker något")
    if not parts:
        return "Kapten, radio. Avlyssning: bara avlägsen rutintrafik, inget som rör oss."
    return "Kapten, radio. Avlyssning: " + "; ".join(parts) + "."


def _intercept_ru(d: dict) -> str:
    parts = []
    if d["air"]:
        parts.append(f"американская авиационная связь, самолётов в районе: {d['air']}")
    if d["ships"]:
        parts.append(f"радиотелефон военных кораблей: {d['ships']}")
    if d["hunting"]:
        parts.append("эсминцы докладывают друг другу о контакте, они кого-то ищут")
    if not parts:
        return f"{R.CAPTAIN}, радист. Радиоперехват: только дальний обычный трафик."
    return f"{R.CAPTAIN}, радист. Радиоперехват: " + "; ".join(parts) + "."


WHY_GARBLED = {"day": "dagsljus", "speed": f"farten över {VLF_SLOW_KN} knop",
               "depth": f"djupare än {VLF_UP_DEPTH} meter"}


def _why_garbled(why: list[str]) -> str:
    words = [WHY_GARBLED[w] for w in why]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " och " + words[-1]


def garble(text: str, rng) -> str:
    """Stympad mottagning: en del av grupperna oläsbara (samma längd, ░)."""
    words = text.split(" ")
    idx = [i for i, w in enumerate(words) if sum(ch.isalnum() for ch in w) >= 2]
    if not idx:
        return text
    lost = {i for i in idx if rng.random() < GARBLE_P} or {rng.choice(idx)}
    return " ".join("░" * len(w) if i in lost else w for i, w in enumerate(words))


PHRASES = {
    "radio.prewarn": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}. "
    f"Vi behöver antenndjup, {ANTENNA_DEPTH:.0f} meter eller grundare.",
    "radio.prewarn_vlf": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}. Vi kan ta emot "
    f"på långvåg med flytkabeln, högst {VLF_DEPTH:.0f} meter och högst {VLF_SPEED:.0f} knop; det tar "
    f"cirka {VLF_RECEIVE_S // 60} minuter." + (
        " I den här farten dras kabeln under, så föreslår antenndjup: masten tar emot på en minut."
        if d.get("mast") else f" Föreslår {d['what']}." if d.get("what") else ""),
    "radio.window_open": lambda d: "Sambandstillfället har börjat. Vi lyssnar.",
    "radio.cable.out": lambda d: f"Flytkabeln ute, vi tar emot på långvåg, cirka {d['minutes']} minuter.",
    "radio.cable.fast": lambda d: "Kapten, radio. Flytkabeln dras under i den här farten, vi tappar "
    f"långvågen. Föreslår fart {VLF_SLOW_KN}.",
    "radio.garbled": lambda d: "Kapten, radio. Långvågen kom in stympad, " + _why_garbled(d["why"])
    + ". Vi lyssnar vidare på omsändningen." + (f" Föreslår {d['what']}." if d.get("what") else ""),
    "radio.message": lambda d: f"Kapten, radio. Radiogram nummer {d['telegram']} från huvudstaben"
    + (", på långvåg." if d.get("via") == "vlf" else "."),
    "radio.nothing": lambda d: "Sambandstillfälle: inga nya meddelanden till oss.",
    "radio.missed": lambda d: "Kapten, vi missade sambandstillfället. " + (
        f"Staben sänder om radiogrammen vid nästa, kl {d['next']}." if d.get("next") else
        "Det finns inget fler inplanerat, så det staben sänt når oss inte."),
    "radio.refused": lambda d: f"Kapten, {d['reason']}.",
    "radio.sending": lambda d: f"Sänder {KIND_SV[d['kind']]} på kortvåg, {_groups(d['groups'])}, "
    f"cirka {d['seconds']} sekunder. Risken att de pejlar oss är {d['risk']}.",
    "radio.sent": lambda d: "Rapport sänd och kvitterad"
    + (f", {_contacts_sv(d['contacts'])} rapporterade." if d["contacts"] else "."),
    "radio.aborted": lambda d: "Sändningen avbröts, antennen kom under ytan.",
    "radio.prewarn_ice": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}. Det är is "
    "ovanför oss. " + (f"Navigatören har öppning {d['no']} i bäring {fmt_course(d['bearing'])}, cirka "
                       f"{d['range']} meter. Föreslår att vi går dit." if d.get("no")
                       else "Vi har ingen öppning loggad, vi behöver hitta öppet vatten."),
    "radio.opening_now": lambda d: f"Kapten, radio. Navigatören har {d['kind']} ovanför oss nu, och "
    f"sambandstillfället kl {d['clock']} är inte avklarat. Föreslår att vi stoppar här.",
    "radio.suggest.air_clear": lambda d: f"Kapten, radio. Flygradarn hördes nära för "
    f"{d['minutes']} minuter sedan, och sambandstillfället stänger kl {d['close']}. Föreslår "
    "periskopdjup: radarvarnaren säger om flyget gått, och då sänder vi.",
    "radio.intercept.start": lambda d: "Avlyssnar amerikansk trafik, en minut.",
    "radio.intercept.lost": lambda d: "Avlyssningen avbröts, antennen kom under ytan.",
    "radio.intercept": _intercept_sv,
    "radio.suggest.intercept": lambda d: "Kapten, radio. Vi har antennen uppe. Föreslår att vi "
    "avlyssnar den amerikanska trafiken en minut, så vet vi om flyget och jagarna är i närheten.",
    "radio.ice": lambda d: "Kapten, radio. Antennen och flytkabeln kommer inte upp genom isen, vi får "
    "ingen mottagning. "
    "Vi behöver öppet vatten ovanför.",
    "radio.suggest.report": lambda d: "Kapten, radio. Sambandstillfället är öppet och huvudstaben "
    "väntar på vår rapport. " + (
        (f"Hela rapporten tar cirka {d['seconds']} sekunder och risken att de pejlar oss är "
         f"{d['risk']}. Föreslår en kort rapport, cirka {d['short_s']} sekunder."
         if d.get("short") else
         f"Föreslår att vi sänder nu. Det tar cirka {d['seconds']} sekunder, och risken att de "
         f"pejlar oss är {d['risk']}.") if d["now"] else
        "Vi måste upp på periskopdjup för att sända. Föreslår periskopdjup."),
    "radio.wait": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}, men plottet har "
    f"{d['designation']} på {nm(d['range'])} sjömil. Där uppe ligger vi över skiktet och hörs. "
    "Föreslår att vi väntar på djupet tills den gått längre bort.",
    "radio.clear": lambda d: f"Kapten, radio. Plottet har nu {d['designation']} på {nm(d['range'])} "
    "sjömil" + (f", och sambandstillfället stänger kl {d['close']}" if d.get("close") else "")
    + f". Föreslår {d.get('what', 'antenndjup')}.",
    "radio.listen": lambda d: "Lyssnar på kortvåg efter Moskva.",
    "radio.listen.lost": lambda d: "Tappade Moskva, antennen kom under ytan.",
    "radio.moscow": lambda d: f"Kapten, radio. Radio Moskva hörs, remsa nummer {d['telegram']}.",
    "radio.moscow.silent": lambda d: "Kapten, radio. Moskva tiger, bara bärvågen.",
    "radio.status": lambda d: (f"Nästa sambandstillfälle kl {d['next']}. " if d.get("next")
                               else "Inga fler sambandstillfällen inplanerade. ")
    + f"{d['received']} meddelanden mottagna."
    + (f" Senaste: {d['last']}" if d.get("last") else ""),
}
phrases.register(PHRASES)

RU_PHRASES = {
    "radio.refused": lambda d: f"{R.CAPTAIN}, радист. Выполнить не могу.",
    "radio.intercept.start": lambda d: "Есть, слушаем американский трафик, одну минуту.",
    "radio.intercept.lost": lambda d: "Перехват прерван, антенна ушла под воду.",
    "radio.intercept": _intercept_ru,
    "radio.suggest.intercept": lambda d: f"{R.CAPTAIN}, радист. Антенна поднята. Предлагаю минуту "
    "послушать американский трафик, узнаем, нет ли рядом самолётов и эсминцев.",
    "radio.suggest.air_clear": lambda d: f"{R.CAPTAIN}, радист. Самолёт слышали рядом "
    f"{R.count(d['minutes'], R.MINUTE)} назад, сеанс связи кончается в {d['close']}. Предлагаю "
    "перископную глубину: станция предупреждения покажет, ушёл ли самолёт, и тогда передадим.",
    "radio.prewarn_ice": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}. Над нами лёд. "
    + (f"У штурмана полынья {d['no']}, пеленг {R.course(d['bearing'])}, около "
       f"{R.count(d['range'], R.METER)}. Предлагаю идти туда." if d.get("no")
       else "Полыней не отмечено, нужно искать чистую воду."),
    "radio.opening_now": lambda d: f"{R.CAPTAIN}, радист. Над нами {R.ice_kind(d['kind'])}, а сеанс связи в "
    f"{d['clock']} ещё не прошёл. Предлагаю остановиться здесь.",
    "radio.ice": lambda d: f"{R.CAPTAIN}, радист. Антенны подо льдом, приёма нет. "
    "Нужна чистая вода над нами.",
    "radio.status": lambda d: (f"Следующий сеанс связи в {d['next']}. " if d.get("next")
                               else "Сеансов связи больше не запланировано. ")
    + f"Принято радиограмм: {d['received']}.",
    "radio.prewarn": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}. Нужна глубина "
    f"под антенну, {R.count(ANTENNA_DEPTH, R.METER)} или меньше.",
    "radio.prewarn_vlf": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}. Примем на "
    "сверхдлинных волнах на плавающую антенну." + (
        " Предлагаю " + " и ".join(w for w, on in (("подвсплыть", d.get("up")), ("сбавить ход", d.get("slow")))
                                   if on) + "." if d.get("what") else ""),
    "radio.window_open": lambda d: "Сеанс связи начался. Слушаем.",
    "radio.cable.out": lambda d: "Плавающая антенна выпущена, принимаем на сверхдлинных волнах.",
    "radio.cable.fast": lambda d: f"{R.CAPTAIN}, радист. На этом ходу антенну притапливает. "
    "Предлагаю сбавить ход.",
    "radio.garbled": lambda d: f"{R.CAPTAIN}, радист. Приём на сверхдлинных волнах искажён, "
    "ждём повтора." + (" Предлагаю " + " и ".join(
        w for w, on in (("подвсплыть", "depth" in d["why"]), ("сбавить ход", "speed" in d["why"])) if on)
        + "." if d.get("what") else ""),
    "radio.message": lambda d: f"{R.CAPTAIN}, радист. Радиограмма из Главного штаба"
    + (" на сверхдлинных волнах." if d.get("via") == "vlf" else "."),
    "radio.nothing": lambda d: "Сеанс связи: новых радиограмм для нас нет.",
    "radio.missed": lambda d: f"{R.CAPTAIN}, мы пропустили сеанс связи. " + (
        f"Штаб повторит радиограммы в {d['next']}." if d.get("next") else
        "Сеансов больше нет, радиограммы до нас не дойдут."),
    "radio.listen": lambda d: "Есть, слушаем Москву на коротких волнах.",
    "radio.listen.lost": lambda d: "Москву потеряли, антенна ушла под воду.",
    "radio.moscow": lambda d: d["ru"],
    "radio.moscow.silent": lambda d: f"{R.CAPTAIN}, радист. Только несущая. Москва молчит.",
    "radio.sending": lambda d: f"Есть, передаём {KIND_RU[d['kind']]} на коротких волнах, "
    f"{R.count(d['groups'], ('группа', 'группы', 'групп'))}, около {R.count(d['seconds'], R.SECOND)}. "
    f"Риск пеленгации {RISK_RU[d['risk']]}.",
    "radio.sent": lambda d: "Донесение передано, квитанция получена.",
    "radio.aborted": lambda d: "Передача прервана, антенна ушла под воду.",
    "radio.wait": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}, но "
    f"{R.contact(d['designation'])} в {R.dec(d['range'], R.MILE)}. Предлагаю ждать на глубине.",
    "radio.clear": lambda d: f"{R.CAPTAIN}, радист. {R.contact(d['designation']).capitalize()} теперь в "
    f"{R.dec(d['range'], R.MILE)}. Предлагаю подвсплыть.",
    "radio.suggest.report": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи идёт, штаб ждёт донесения. "
    + ((f"Полное донесение около {R.count(d['seconds'], R.SECOND)}, риск пеленгации "
        f"{RISK_RU[d['risk']]}. Предлагаю короткое донесение, около "
        f"{R.count(d['short_s'], R.SECOND)}." if d.get("short") else
        f"Предлагаю передать сейчас, около {R.count(d['seconds'], R.SECOND)}. Риск пеленгации "
        f"{RISK_RU[d['risk']]}.") if d["now"] else
       "Для передачи нужна перископная глубина. Предлагаю всплыть под перископ."),
}
phrases.register_ru(RU_PHRASES)


class RadioStation(Station):
    REACHES_WORLD = True        # sändningar (pejlbara emissioner) och huvudstabens meddelanden
    role = Role.RADIO
    MAST_ORDERS = (SendReport,)
    COMMANDS = [
        CommandSpec(r"(?:sänd |sand )?kort rapport|rapportera kort",
                    lambda m: SendReport("short"), "sänd kort rapport"),
        CommandSpec(rf"(?:sänd|sand) rapport (?:om )?{DESIG}|rapportera {DESIG}",
                    lambda m: SendReport("contact", desig(m[1] or m[2]))),
        CommandSpec(r"sänd rapport|sand rapport|rapportera|sänd", lambda m: SendReport(), "sänd rapport"),
        CommandSpec(r"radio|meddelanden", lambda m: RadioStatus(), "radio"),
        CommandSpec(r"avlyssna|avlyssning|radiospaning|lyssna(?: på)? trafik(?:en)?",
                    lambda m: Intercept(), "avlyssna"),
        CommandSpec(r"lyssna(?: på)? (?:radio|moskva|radio moskva)|radio moskva|moskva",
                    lambda m: ListenBroadcast(), "radio moskva"),
    ]

    def __init__(self, game):
        super().__init__(game)
        sc = game.scenario
        self.windows: list[int] = list(sc.radio_windows) if sc else []
        self.window_len: int = sc.radio_window_len if sc else 1200
        self.messages = list(sc.radio_messages) if sc else []
        self.delivered: list[str] = []
        self._next_msg = 0
        self._orders_read = False
        self._listen = 0
        self._handled: set[int] = set()
        self._prewarned: set[int] = set()
        self._opened: set[int] = set()
        self._ice_warned: set[int] = set()
        self.tx_done_t: int | None = None
        self._tx: SentReport | None = None       # rapporten som sänds
        self._tx_start = 0
        self.sent: list[SentReport] = []          # det vi sänt till staben
        self._photo_t: int | None = None          # det som hänt sedan förra rapporten
        self._hit_t: int | None = None
        self._reported_t = -10**9
        self._waiting: set[int] = set()       # fönster där vi väntar på djupet på grund av ett hot
        # ordern kräver en rapport under sambandstillfället (kuba-kort)
        self.report_required = bool(sc and sc.report_required)
        self.hq = Headquarters(expects_report=self.report_required)   # vet bara vad vi sänt
        self._closed: set[int] = set()
        self.broadcasts = broadcasts_for(order_day(sc.secret_order) if sc else None)
        self._broadcast_n = 0
        self._listen_until: int | None = None   # radiomannen letar upp Moskva
        self.received = 0                       # mottagningsnummer ombord
        self._intercept_until: int | None = None    # radiospaning pågår
        self._intercept_start = 0
        self.cable = False                      # flytkabeln ute (långvåg)
        self._vlf = 0                           # sekunder långvåg i detta fönster
        self._cable_said: set[int] = set()
        self._cable_fast: set[int] = set()
        self._garbled: set[int] = set()


    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(Handover, self._on_handover)
        self.hq.attach(bus)
        bus.subscribe(PhotoTaken, lambda e: setattr(self, "_photo_t", e.t))
        bus.subscribe(OwnTorpedoHeard,
                      lambda e: setattr(self, "_hit_t", e.t) if e.kind == "detonated" else None)

    # --- rapporten ------------------------------------------------------------------
    def _events(self) -> tuple[str, ...]:
        """Det som hänt sedan förra rapporten (ur kunskapen)."""
        since = self.sent[-1].t if self.sent else -10**9
        out = []
        if self._photo_t is not None and self._photo_t > since:
            out.append("photo")
        if self._hit_t is not None and self._hit_t > since:
            out.append("hit")
        if self.game.knowledge.hunt_t > since:
            out.append("hunted")
        return tuple(out)

    def draft(self, kind: str = "full", target: str | None = None) -> SentReport:
        """Rapporten som den skulle se ut nu (för sändningen och för förslagen)."""
        nav = self._nav()
        x, y = self.game.own_position_estimate()
        sigma = nav.uncertainty() if nav is not None else 0.0
        return compose(self.game.knowledge, self.now, (x, y, sigma), kind, target,
                       self._events(), number=len(self.sent) + 1)

    def risk(self, seconds: float) -> tuple[str, Quality]:
        """Radiomannens bedömning av pejlrisken: sändningens längd och hotet i plottet."""
        near = self._far_threat()
        r_nm = near[1] if near else None
        q = Quality.GOD
        if near is not None:
            tr = next((t for t in self.game.knowledge.tracks.values()
                       if t.designation == near[0]), None)
            if tr is not None and tr.solution is not None:
                q = tr.solution.quality
        if seconds >= RISK_LONG_S or (r_nm is not None and r_nm <= RISK_NEAR_NM):
            return "stor", q
        if seconds >= RISK_MID_S or (r_nm is not None and r_nm <= RISK_MID_NM):
            return "måttlig", q
        return "liten", q

    def _on_handover(self, e: Handover) -> None:
        """Förvarningar under vakten hörde kaptenen inte: ge dem igen."""
        self._prewarned = {i for i in self._prewarned if self.windows[i] <= self.now}

    def on_order(self, order: Order) -> None:
        match order:
            case SendReport():
                st, sys = self.own.state, self.own.sys
                if st.depth > PERISCOPE_DEPTH:
                    self.say("radio.refused", {"reason": "vi måste upp på periskopdjup för att sända"})
                elif sys.health["radio"] < 0.3:
                    self.say("radio.refused", {"reason": "radion är skadad"})
                elif not self.masts_free:
                    self.say("radio.refused", {"reason": "det är is ovanför, antennen kommer inte upp"})
                elif self.tx_done_t is not None:
                    self.say("radio.refused", {"reason": "vi sänder redan"})
                else:
                    r = self.draft(order.kind, order.target)
                    if r.kind == "contact" and not r.contacts:
                        self.say("radio.refused", {"reason": f"plottet har ingen lösning på "
                                                             f"{order.target} att rapportera"})
                        return
                    secs = r.duration_s
                    sys.transmit_until = self.now + secs
                    self.tx_done_t = self.now + secs
                    self._tx, self._tx_start = r, self.now
                    risk, q = self.risk(secs)
                    self.say("radio.sending", {"kind": r.kind, "groups": r.groups, "seconds": secs,
                                               "contacts": len(r.contacts), "risk": risk},
                             kind="ack", quality=q)
            case ListenBroadcast():
                st, sys = self.own.state, self.own.sys
                if st.depth > ANTENNA_DEPTH:
                    self.say("radio.refused", {"reason": "vi måste upp på antenndjup för att höra "
                                                         "Moskva"})
                elif sys.health["radio"] < 0.3:
                    self.say("radio.refused", {"reason": "radion är skadad"})
                elif not self.masts_free:
                    self.say("radio.refused", {"reason": "det är is ovanför, antennen kommer inte upp"})
                elif self._listen_until is None:
                    self._listen_until = self.now + LISTEN_S
                    self.say("radio.listen", kind="ack")
            case Intercept():
                st, sys = self.own.state, self.own.sys
                if st.depth > ANTENNA_DEPTH:
                    self.say("radio.refused", {"reason": "vi måste upp på antenndjup för att "
                                                         "avlyssna"})
                elif sys.health["radio"] < 0.3:
                    self.say("radio.refused", {"reason": "radion är skadad"})
                elif not self.masts_free:
                    self.say("radio.refused", {"reason": "det är is ovanför, antennen kommer inte upp"})
                elif self._intercept_until is None:
                    self._intercept_until = self.now + INTERCEPT_S
                    self._intercept_start = self.now
                    self.say("radio.intercept.start", kind="ack")
            case RadioStatus():
                nxt = next((w for w in self.windows if w + self.window_len > self.now), None)
                self.say("radio.status", {
                    "next": self.game.clock_str(nxt) if nxt is not None else None,
                    "received": len(self.delivered),
                    "last": self.delivered[-1] if self.delivered else None})

    def _nav(self) -> NavigationStation | None:
        try:
            return self.game.station(NavigationStation)
        except KeyError:
            return None

    def _ice_route(self) -> tuple[bool, dict]:
        """Är det is ovanför (enligt navigatörens isekolod), och finns en öppning att gå till?"""
        nav = self._nav()
        if nav is None or not nav.under_ice():
            return False, {}
        o = nav.best_opening()
        d = nav.opening_data(o) if o is not None else {}
        if d and d["range"] > RADIO_VAK_MAX_M:
            d = {}                      # för långt bort för att hinna dit
        return True, d

    def system_items(self) -> list:
        items: list = []
        if self.tx_done_t is not None:
            items.append(Gauge("SAMBAND", "Sändning", f"pågår, {self.tx_done_t - self.now} s kvar",
                               WARN))
        i = self.window_pending()
        if i is not None and self.windows[i] <= self.now:
            if self._listen:
                what = "lyssnar på masten"
            elif self.cable:
                left = max(1, round((VLF_RECEIVE_S - self._vlf) / 60))
                what = f"långvåg, kabeln ute, {left} min kvar"
            elif self.report_required:
                what = f"antenndjup ≤ {ANTENNA_DEPTH:.0f} m"
            else:
                what = f"kabeln: ≤ {VLF_DEPTH:.0f} m och ≤ {VLF_SPEED:.0f} kn"
            items.append(Gauge("SAMBAND", "Samband", "öppet nu, " + what,
                               OK if self._listen or self.cable else WARN))
        else:
            nxt = next((w for w in self.windows if w + self.window_len > self.now), None)
            items.append(Gauge("SAMBAND", "Nästa samband",
                               self.game.clock_str(nxt)[:5] if nxt is not None else "inget planerat",
                               WARN if i is not None else INFO))
        items.append(Gauge("SAMBAND", "Mottaget", f"{len(self.delivered)} meddelanden", INFO))
        return items

    def profile_items(self) -> list:
        """Flytkabelns djup medan ett sambandstillfälle väntar, och kabeln när den är ute."""
        items: list = []
        if self.window_pending() is not None and not self.report_required:
            items.append(Level(VLF_DEPTH, "flytkabel", "cable", "┄"))
        if self.cable:
            items.append(Cable())
        return items

    def needs_mast(self) -> bool:
        """Behöver radion oss uppe: ett sambandstillfälle som inte är avklarat, eller en
        rapport som ordern kräver och som inte är sänd medan fönstret är öppet."""
        return self.up_depth() is not None

    def up_depth(self) -> float | None:
        """Hur grunt radion behöver oss: antenndjup för rapporten som ordern kräver, annars
        flytkabelns djup för ett sambandstillfälle som inte är avklarat; None om inget."""
        if self.report_required and (self.window_pending() is not None or any(
                w0 <= self.now < w0 + self.window_len and self._reported_t < w0 for w0 in self.windows)):
            return ANTENNA_DEPTH
        if self.window_pending() is not None:
            return VLF_DEPTH
        return None

    def _up_order(self) -> tuple[str | None, dict]:
        """Ordern som tar oss dit radion kan ta emot (beordrat djup och fart), och vad den
        innehåller: antenndjup när ordern kräver rapport, annars långvågen med flytkabeln."""
        st = self.own.state
        if self.report_required:
            return ("antenndjup" if st.ordered_depth > ANTENNA_DEPTH else None), {"up": True}
        if st.ordered_speed > VLF_SPEED:        # vi går fort (följer, anfaller): masten i stället
            return ("antenndjup" if st.ordered_depth > ANTENNA_DEPTH else None), {"up": True, "mast": True}
        up, slow = st.ordered_depth > VLF_DEPTH, st.ordered_speed > VLF_SPEED
        parts = ([f"djup {VLF_UP_DEPTH}"] if up else []) + ([f"fart {VLF_SLOW_KN}"] if slow else [])
        return (" och ".join(parts) or None), {"up": up, "slow": slow}

    def _next_window_clock(self) -> str | None:
        """Nästa sambandstillfälle som inte börjat än (då sänder staben om det vi missat)."""
        nxt = next((w for w in self.windows if w > self.now), None)
        return self.game.clock_str(nxt)[:5] if nxt is not None else None

    def window_pending(self) -> int | None:
        """Ett sambandstillfälle som snart börjar eller pågår och inte är avklarat."""
        for i, w0 in enumerate(self.windows):
            if i not in self._handled and w0 - PREWARN_S <= self.now < w0 + self.window_len:
                return i
        return None

    def idle_proposals(self) -> list[Proposal]:
        if self.own.state.depth <= ANTENNA_DEPTH:
            k = self.game.knowledge
            if self._intercept_until is None and self.masts_free and \
                    (k.intercept is None or self.now - k.intercept.t > INTERCEPT_AGAIN_S):
                return [Proposal(5, "idle_intercept", "radio.suggest.intercept", "avlyssna",
                                 cooldown=INTERCEPT_AGAIN_S)]
            return []
        for i, w0 in enumerate(self.windows):
            # påminnelse: förvarningen är redan given men vi är kvar på djupet
            if i in self._prewarned and i not in self._handled \
                    and self.now < w0 + self.window_len:
                d = {"clock": self.game.clock_str(w0)[:5]}
                ice, opening = self._ice_route()
                if ice:
                    if not opening:
                        return []
                    return [Proposal(3, f"idle_window{i}", "radio.prewarn_ice", "vak",
                                     {**d, **opening}, cooldown=900)]
                up, how = self._up_order()
                if up is None:
                    return []
                return [Proposal(3, f"idle_window{i}", self._prewarn_type(), up,
                                 {**d, **how, "what": up}, cooldown=900)]
        return []

    def _prewarn_type(self) -> str:
        return "radio.prewarn" if self.report_required else "radio.prewarn_vlf"

    def _broadcast(self) -> None:
        """Radiomannen har hittat Moskva (eller bara bärvågen)."""
        self._listen_until = None
        if not self.broadcasts:
            return
        b = self.broadcasts[self._broadcast_n % len(self.broadcasts)]
        self._broadcast_n += 1
        self.received += 1
        self.game.bus.publish(TelegramReceived(self.now, b.sv, "broadcast", self.received))
        strip = {"text": b.sv, "telegram": self.received, "telegram_kind": "broadcast"}
        if b.ru:
            self.say("radio.moscow", {**strip, "ru": b.ru, "read_aloud": b.sv}, kind="info")
        else:
            self.say("radio.moscow.silent", strip, kind="info")

    def update(self) -> None:
        if not self._orders_read:            # ordern läst vid start: vad den säger om kärnladdningen
            self._orders_read = True
            sc = self.game.scenario
            self.game.bus.publish(NuclearOrderRead(self.now, getattr(sc, "nuclear_order", "order_only"),
                                                   getattr(sc, "at_war", False), "ordern"))
        st = self.own.state
        if self._listen_until is not None:
            if st.depth > ANTENNA_DEPTH + 1 or not self.masts_free:
                self._listen_until = None
                self.say("radio.listen.lost")
            elif self.now >= self._listen_until:
                self._broadcast()
        if self._intercept_until is not None:
            if st.depth > ANTENNA_DEPTH + 1 or not self.masts_free:
                self._intercept_until = None
                self.say("radio.intercept.lost")
            elif self.now >= self._intercept_until:
                self._intercept_until = None
                self._intercept()
        i = self.window_pending()
        nav = self._nav()
        if i is not None and nav is not None and nav.opening_now() is not None \
                and not self.game.queue.has_kind("suggest") \
                and self.now - self.game.suggested_at.get("vak", -10**9) > 60:
            latest = nav.icemap.latest(self.now)
            self.suggest(f"open_now{i}", "radio.opening_now",
                         {"kind": thickness_words(latest.thickness),
                          "clock": self.game.clock_str(self.windows[i])[:5]},
                         order="vak", cooldown=300)
        if self.tx_done_t is not None:
            if st.depth > PERISCOPE_DEPTH + 1:
                self.tx_done_t = None
                self._emit_hf(self.now - self._tx_start)
                self.game.bus.publish(ReportTransmitted(self.now, self._tx, complete=False))
                self._tx = None
                self.say("radio.aborted")
            elif self.now >= self.tx_done_t:
                self.tx_done_t = None
                r, self._tx = self._tx, None
                self._emit_hf(self.now - self._tx_start)
                w = self.world
                w.mission["reports_sent"] = w.mission.get("reports_sent", 0) + 1
                w.mission["last_report_t"] = self.now
                w.mission.setdefault("reports", []).append(r)
                w.mission.setdefault("report_truth", []).append(self._truth_of(r))
                self._reported_t = self.now
                self.sent.append(r)
                self.say("radio.sent", {"contacts": len(r.contacts), "telegram": r.number,
                                        "telegram_kind": "outgoing", "text": report_text(r)})
                self.game.bus.publish(ReportTransmitted(self.now, r))
                self.game.bus.publish(OwnActionLogged(self.now, "report"))

        for i, w0 in enumerate(self.windows):
            if w0 <= self.now < w0 + self.window_len:
                self._report_advice(w0)
            if self.now >= w0 + self.window_len and i not in self._closed:
                self._closed.add(i)
                self.hq.window_closed(reported=self._reported_t >= w0)
            if i in self._handled:
                continue
            if self.now >= w0 - PREWARN_S and i not in self._prewarned:
                self._prewarned.add(i)
                d = {"clock": self.game.clock_str(w0)[:5]}
                ice, opening = self._ice_route()
                if ice and opening:
                    self.suggest(f"window{i}", "radio.prewarn_ice", {**d, **opening}, order="vak",
                                 cooldown=0)
                elif ice:
                    self.say("radio.prewarn_ice", d)
                elif (up := self._up_order())[0] is not None and \
                        (near := self._threat_near()) is not None:
                    self.say("radio.wait", {**d, "designation": near[0], "range": near[1]})
                    self._waiting.add(i)
                elif up[0] is not None:
                    self.suggest(f"window{i}", self._prewarn_type(), {**d, **up[1], "what": up[0]},
                                 order=up[0], cooldown=0)
                else:
                    self.say(self._prewarn_type(), d)
            if i in self._waiting and self._up_order()[0] is not None and self.now % 30 == 0:
                self._clear_advice(i, w0)
            if w0 <= self.now < w0 + self.window_len:
                if i not in self._opened:
                    self._opened.add(i)
                    self._listen = self._vlf = 0
                    self.say("radio.window_open")
                self._receive(i)
            elif self.now >= w0 + self.window_len:
                self._handled.add(i)
                self.cable = False
                if self._next_msg <= i and self._next_msg < len(self.messages):
                    self.say("radio.missed", {"next": self._next_window_clock()}, alarm=False)

    def _receive(self, i: int) -> None:
        """Sambandstillfället är öppet: masten på antenndjup, annars flytkabeln på långvåg."""
        st = self.own.state
        working = self.own.sys.health["radio"] >= 0.3
        if st.depth <= VLF_DEPTH and not self.masts_free:
            self.cable = False
            if i not in self._ice_warned:
                self._ice_warned.add(i)
                self.say("radio.ice")
        elif st.depth <= ANTENNA_DEPTH and working:
            self.cable = False
            self._listen += 1
            if self._listen >= RECEIVE_S:
                self._handled.add(i)
                self._deliver(upto=i)
        elif st.depth <= VLF_DEPTH and working:
            if not self.cable:
                self.cable = True
                if i not in self._cable_said:
                    self._cable_said.add(i)
                    self.say("radio.cable.out", {"minutes": VLF_RECEIVE_S // 60})
            if st.speed > VLF_SPEED + 0.1:
                if i not in self._cable_fast:
                    self._cable_fast.add(i)
                    self.suggest(f"cable_fast{i}", "radio.cable.fast", {}, order=f"fart {VLF_SLOW_KN}",
                                 cooldown=120)
                return
            self._vlf += 1
            if self._vlf >= VLF_RECEIVE_S:
                why = self._vlf_quality()
                pending = self._pending_texts(upto=i)
                if not why or not pending:
                    self._handled.add(i)
                    self.cable = False
                    self._deliver(upto=i, via="vlf")
                else:
                    self._vlf = 0               # stympat: lyssna på omsändningen
                    if i not in self._garbled:
                        self._garbled.add(i)
                        self._say_garbled(pending[0], why)
        else:
            self.cable = False

    def _vlf_quality(self) -> list[str]:
        """Varför långvågen kommer in stympad (tom: hel). Mörkret, låg fart (kabeln flyter
        i ytan) och litet djup (kabeln räcker) ger var sitt plus; två räcker."""
        st = self.own.state
        night = not self.world.env.is_day(self.now)
        ok = {"day": night, "speed": st.speed <= VLF_SLOW_KN + 0.1,
              "depth": st.depth <= VLF_UP_DEPTH + 0.5}
        if sum(ok.values()) >= 2:
            return []
        return [k for k, v in ok.items() if not v]

    def _pending_texts(self, upto: int) -> list[str]:
        """Det staben sänder vid detta tillfälle: scenariots radiogram och stabens svar."""
        out = [m.text for m in self.messages[self._next_msg:upto + 1]]
        return out + self.hq.queue[:MAX_PER_WINDOW]

    def _say_garbled(self, text: str, why: list[str]) -> None:
        st = self.own.state
        parts = ([f"djup {VLF_UP_DEPTH}"] if "depth" in why and st.ordered_depth > VLF_UP_DEPTH else []) \
            + ([f"fart {VLF_SLOW_KN}"] if "speed" in why and st.ordered_speed > VLF_SLOW_KN else [])
        what = " och ".join(parts) or None
        d = {"why": why, "what": what, "telegram": "?", "telegram_kind": "telegram",
             "text": garble(text, self.game.rng_for("radio"))}
        if what:
            self.suggest("garbled", "radio.garbled", d, order=what, cooldown=300)
        else:
            self.say("radio.garbled", d)

    def _intercept(self) -> None:
        """Radiospaning (sensor): amerikansk flygradio, fartygens radiotrafik och om jagarna
        rapporterar kontakt till varandra. Kvaliteten ur hur mycket som hördes."""
        from ..enemy import DestroyerAI
        w = self.world
        air = [v for v in w.contacts if v.kind == "aircraft" and not v.gone
               and w.true_range(v) <= INTERCEPT_AIR_NM]
        ships = [ai for ai in w.ais if isinstance(ai, DestroyerAI) and not ai.vessel.sunk
                 and w.true_range(ai.vessel) <= INTERCEPT_SHIP_NM]
        hunting = any(ai.datum is not None and w.time - ai.datum.t <= INTERCEPT_HUNT_S
                      for ai in ships)
        heard = len(air) + len(ships)
        q = Quality.GOD if heard >= 2 else Quality.OSAKER if heard == 1 else Quality.DALIG
        d = {"air": len(air), "ships": len(ships), "hunting": hunting}
        self.game.bus.publish(InterceptHeard(self.now, len(air), len(ships), hunting, q))
        self.say("radio.intercept", d, kind="contact", quality=q, alarm=hunting)

    def _truth_of(self, r: SentReport) -> dict:
        """Hur väl rapporten stämde (sanningen, bara för slutrapporten; staben vet det inte).
        Kontakternas läge räknas fram till nu med rapporterad kurs och fart."""
        from .sonar_room import SonarRoom
        w, own = self.world, self.own.state
        x, y, _ = r.position
        out = {"t": self.now, "own_err_nm": distance(x, y, own.x, own.y), "contacts": []}
        sensor = next((st.sensor for st in self.game.stations if isinstance(st, SonarRoom)), None)
        for c in r.contacts:
            v = next((v for v in w.contacts if sensor is not None
                      and sensor.designation_of(v.id) == c.designation), None)
            if v is None:
                continue
            dt_h = (self.now - c.t) / 3600.0
            px = c.x + c.speed * dt_h * math.sin(math.radians(c.course))
            py = c.y + c.speed * dt_h * math.cos(math.radians(c.course))
            out["contacts"].append({
                "designation": c.designation,
                "pos_err_nm": distance(px, py, v.state.x, v.state.y),
                "course_err": abs(angle_diff(c.course, v.state.course)),
                "speed_err": abs(c.speed - v.state.speed)})
        return out

    def _emit_hf(self, seconds: float) -> None:
        """Sändningen hörs i etern så länge den pågick: fiendens pejlnät (enemy.py)."""
        st = self.own.state
        self.world.emit_em(Emission("hf", st.x, st.y, self.own.id, self.now, duration=seconds))

    def _threat_near(self) -> tuple[str, float] | None:
        """Närmaste hotkontakt som plottet har inom RADIO_SAFE_NM (beteckning, sjömil)."""
        best = None
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            if not tr.threat or not tr.held or sol is None or sol.quality < Quality.OSAKER:
                continue
            if sol.range_nm < RADIO_SAFE_NM and (best is None or sol.range_nm < best[1]):
                best = (tr.designation, sol.range_nm)
        return best

    def _far_threat(self) -> tuple[str, float] | None:
        """Närmaste hotkontakt med en lösning, för att säga hur långt bort den är."""
        sols = [(tr.designation, tr.solution.range_nm) for tr in self.game.knowledge.tracks.values()
                if tr.threat and tr.held and tr.solution is not None
                and tr.solution.quality >= Quality.OSAKER]
        return min(sols, key=lambda p: p[1]) if sols else None

    def _clear_advice(self, i: int, w0: int) -> None:
        """Vi väntar på djupet: föreslå antenndjup när hotet gått längre bort."""
        if self._threat_near() is not None or self.game.knowledge.hunted(self.now):
            return
        self._waiting.discard(i)
        far = self._far_threat()
        d = {"designation": far[0] if far else "kontakten", "range": far[1] if far else RADIO_SAFE_NM,
             "close": self.game.clock_str(w0 + self.window_len)[:5]}
        up, _ = self._up_order()
        if up is None:
            return
        self.suggest(f"clear{i}", "radio.clear", {**d, "what": up}, order=up, cooldown=0)

    def _report_advice(self, w0: int) -> None:
        """Ordern kräver en rapport: föreslå periskopdjup och sedan sändningen, men inte
        medan fienden har oss (sändningen pejlas)."""
        if not self.report_required or self._reported_t >= w0 or self.tx_done_t is not None:
            return
        if self.game.knowledge.hunted(self.now) or self._threat_near() is not None:
            return
        st, k = self.own.state, self.game.knowledge
        air_recent = k.air_close_t is not None and self.now - k.air_close_t < AIR_QUIET_S
        if st.depth <= PERISCOPE_DEPTH + 0.5:
            if not k.air_close_now():           # flyget nära: vakthavande föreslår djup 60
                full, short = self.draft("full"), self.draft("short")
                risk, q = self.risk(full.duration_s)
                use_short = risk == "stor" and self.risk(short.duration_s)[0] != "stor"
                self.suggest("report_send", "radio.suggest.report",
                             {"now": True, "seconds": full.duration_s, "risk": risk,
                              "short": use_short, "short_s": short.duration_s},
                             order="sänd kort rapport" if use_short else "sänd rapport",
                             cooldown=REPORT_SUGGEST_S, quality=q)
        elif st.depth > ANTENNA_DEPTH + 0.5 and k.air_close_t is not None and k.air_close_t >= w0 \
                and not air_recent \
                and w0 + self.window_len - self.now >= AIR_LEFT_S:
            # flyget drev ned oss under fönstret: gå upp och se om det gått
            self.suggest(f"report_air{k.air_close_t}", "radio.suggest.air_clear",
                         {"minutes": round((self.now - k.air_close_t) / 60),
                          "close": self.game.clock_str(w0 + self.window_len)[:5]},
                         order="periskopdjup", cooldown=REPORT_SUGGEST_S)
        elif st.depth <= VLF_DEPTH + 0.5 and not air_recent and any(
                i in self._handled for i, w in enumerate(self.windows) if w == w0):
            self.suggest("report_depth", "radio.suggest.report", {"now": False},
                         order="periskopdjup", cooldown=REPORT_SUGGEST_S)

    def _deliver(self, upto: int, via: str = "mast") -> None:
        any_msg = False
        while self._next_msg <= upto and self._next_msg < len(self.messages):
            msg = self.messages[self._next_msg]
            self._next_msg += 1
            self._telegram(msg.text, via)
            if "nuclear" in msg.flags or "war" in msg.flags:
                self.game.bus.publish(NuclearOrderRead(self.now, msg.flags.get("nuclear"),
                                                       msg.flags.get("war"),
                                                       f"telegram {self.received}"))
            self.world.mission.update(msg.flags)
            if msg.flags.get("report_requested"):
                self.hq.request_report()
            if msg.waypoint is not None:
                name, x, y, sigma, t_pos = msg.waypoint
                self.game.bus.publish(PositionReported(self.now, name, x, y, sigma, t_pos))
            any_msg = True
        for text in self.hq.outgoing():          # stabens svar på det vi sänt (eller inte sänt)
            self._telegram(text, via)
            any_msg = True
        if not any_msg:
            self.say("radio.nothing")

    def _telegram(self, text: str, via: str = "mast") -> None:
        self.delivered.append(text)
        self.received += 1
        self.game.bus.publish(TelegramReceived(self.now, text, "telegram", self.received))
        self.say("radio.message", {"text": text, "telegram": self.received, "via": via,
                                   "telegram_kind": "telegram", "read_aloud": text},
                 kind="info", alarm=True)
