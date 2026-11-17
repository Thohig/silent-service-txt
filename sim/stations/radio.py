"""Radio: sambandstillfällen med huvudstaben och rapportsändning.

Mottagning (längstvåg) kräver antenndjup. Sändning (kortvåg) kräver
periskopdjup och kan pejlas av fienden.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import phrases
from .. import russian as R
from ..crew import Role
from ..entities import Emission
from ..broadcasts import broadcasts_for, order_day
from ..events import OwnActionLogged, Handover, PositionReported, TelegramReceived
from ..fmt import fmt_course, nm
from ..icemap import thickness_words
from ..ice import masts_clear
from ..orders import CommandSpec, Order
from ..reports import Quality
from ..ownship import ANTENNA_DEPTH, PERISCOPE_DEPTH
from ..systems import INFO, OK, WARN, Gauge
from .base import Proposal, Station
from .navigation import NavigationStation

RECEIVE_S = 60
TRANSMIT_S = 30
PREWARN_S = 600
RADIO_SAFE_NM = 5.0          # en hotkontakt närmare än så enligt plottet: vänta med att gå upp
REPORT_SUGGEST_S = 180       # förslaget att sända upprepas högst så här ofta
LISTEN_S = 20                # så länge radiomannen letar upp Moskva på kortvåg
RADIO_VAK_MAX_M = 2500        # öppningar längre bort hinner vi inte till


@dataclass(frozen=True)
class SendReport(Order):
    pass


@dataclass(frozen=True)
class RadioStatus(Order):
    pass


@dataclass(frozen=True)
class ListenBroadcast(Order):
    pass


PHRASES = {
    "radio.prewarn": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}. "
    f"Vi behöver antenndjup, {ANTENNA_DEPTH:.0f} meter eller grundare.",
    "radio.window_open": lambda d: "Sambandstillfället har börjat. Vi lyssnar.",
    "radio.message": lambda d: f"Kapten, radio. Radiogram nummer {d['telegram']} från huvudstaben.",
    "radio.nothing": lambda d: "Sambandstillfälle: inga nya meddelanden till oss.",
    "radio.missed": lambda d: "Kapten, vi missade sambandstillfället. Meddelanden kan ha gått förlorade "
    "till nästa.",
    "radio.refused": lambda d: f"Kapten, {d['reason']}.",
    "radio.sending": lambda d: "Sänder rapport på kortvåg. Trettio sekunder.",
    "radio.sent": lambda d: f"Rapport sänd och kvitterad. {d['contacts']} kontakter rapporterade.",
    "radio.aborted": lambda d: "Sändningen avbröts, antennen kom under ytan.",
    "radio.prewarn_ice": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}. Det är is "
    "ovanför oss. " + (f"Navigatören har öppning {d['no']} i bäring {fmt_course(d['bearing'])}, cirka "
                       f"{d['range']} meter. Föreslår att vi går dit." if d.get("no")
                       else "Vi har ingen öppning loggad, vi behöver hitta öppet vatten."),
    "radio.opening_now": lambda d: f"Kapten, radio. Navigatören har {d['kind']} ovanför oss nu, och "
    f"sambandstillfället kl {d['clock']} är inte avklarat. Föreslår att vi stoppar här.",
    "radio.ice": lambda d: "Kapten, radio. Antennen är under isen, vi får ingen mottagning. "
    "Vi behöver öppet vatten ovanför.",
    "radio.suggest.report": lambda d: "Kapten, radio. Sambandstillfället är öppet och huvudstaben "
    "väntar på vår rapport. " + ("Föreslår att vi sänder nu. Det tar trettio sekunder, och sändningen "
                                "kan pejlas." if d["now"] else
                                "Vi måste upp på periskopdjup för att sända. Föreslår periskopdjup."),
    "radio.wait": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}, men plottet har "
    f"{d['designation']} på {nm(d['range'])} sjömil. På antenndjup ligger vi över skiktet och hörs. "
    "Föreslår att vi väntar på djupet tills den gått längre bort.",
    "radio.clear": lambda d: f"Kapten, radio. Plottet har nu {d['designation']} på {nm(d['range'])} "
    "sjömil" + (f", och sambandstillfället stänger kl {d['close']}" if d.get("close") else "")
    + ". Föreslår antenndjup.",
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
    "radio.prewarn": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}. Нужна глубина "
    f"под антенну, {R.count(ANTENNA_DEPTH, R.METER)} или меньше.",
    "radio.window_open": lambda d: "Сеанс связи начался. Слушаем.",
    "radio.message": lambda d: f"{R.CAPTAIN}, радист. Радиограмма из Главного штаба.",
    "radio.nothing": lambda d: "Сеанс связи: новых радиограмм для нас нет.",
    "radio.missed": lambda d: f"{R.CAPTAIN}, мы пропустили сеанс связи. Радиограммы могли "
    "пропасть до следующего.",
    "radio.listen": lambda d: "Есть, слушаем Москву на коротких волнах.",
    "radio.listen.lost": lambda d: "Москву потеряли, антенна ушла под воду.",
    "radio.moscow": lambda d: d["ru"],
    "radio.moscow.silent": lambda d: f"{R.CAPTAIN}, радист. Только несущая. Москва молчит.",
    "radio.sending": lambda d: "Есть, передаём донесение на коротких волнах. Тридцать секунд.",
    "radio.sent": lambda d: "Донесение передано, квитанция получена.",
    "radio.aborted": lambda d: "Передача прервана, антенна ушла под воду.",
    "radio.wait": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}, но "
    f"{R.contact(d['designation'])} в {R.dec(d['range'], R.MILE)}. Предлагаю ждать на глубине.",
    "radio.clear": lambda d: f"{R.CAPTAIN}, радист. {R.contact(d['designation']).capitalize()} теперь в "
    f"{R.dec(d['range'], R.MILE)}. Предлагаю всплыть под антенну.",
    "radio.suggest.report": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи идёт, штаб ждёт донесения. "
    + ("Предлагаю передать сейчас. Тридцать секунд, нас могут запеленговать." if d["now"] else
       "Для передачи нужна перископная глубина. Предлагаю всплыть под перископ."),
}
phrases.register_ru(RU_PHRASES)


class RadioStation(Station):
    role = Role.RADIO
    COMMANDS = [
        CommandSpec(r"sänd rapport|sand rapport|rapportera|sänd", lambda m: SendReport(), "sänd rapport"),
        CommandSpec(r"radio|meddelanden", lambda m: RadioStatus(), "radio"),
        CommandSpec(r"lyssna(?: på)? (?:radio|moskva|radio moskva)|radio moskva|moskva",
                    lambda m: ListenBroadcast(), "lyssna radio"),
    ]

    def __init__(self, game):
        super().__init__(game)
        sc = game.scenario
        self.windows: list[int] = list(sc.radio_windows) if sc else []
        self.window_len: int = sc.radio_window_len if sc else 1200
        self.messages = list(sc.radio_messages) if sc else []
        self.delivered: list[str] = []
        self._next_msg = 0
        self._listen = 0
        self._handled: set[int] = set()
        self._prewarned: set[int] = set()
        self._opened: set[int] = set()
        self._ice_warned: set[int] = set()
        self.tx_done_t: int | None = None
        self._reported_t = -10**9
        self._waiting: set[int] = set()       # fönster där vi väntar på djupet på grund av ett hot
        # ordern kräver en rapport under sambandstillfället (kuba-kort)
        self.report_required = bool(sc and sc.report_required)
        self.broadcasts = broadcasts_for(order_day(sc.secret_order) if sc else None)
        self._broadcast_n = 0
        self._listen_until: int | None = None   # radiomannen letar upp Moskva
        self.received = 0                       # mottagningsnummer ombord

    @property
    def own(self):
        return self.game.world.own

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(Handover, self._on_handover)

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
                elif not masts_clear(self.game.world):
                    self.say("radio.refused", {"reason": "det är is ovanför, antennen kommer inte upp"})
                elif self.tx_done_t is not None:
                    self.say("radio.refused", {"reason": "vi sänder redan"})
                else:
                    sys.transmit_until = self.now + TRANSMIT_S
                    self.tx_done_t = self.now + TRANSMIT_S
                    self.game.world.emit_em(Emission("hf", st.x, st.y, self.own.id, self.now))
                    self.say("radio.sending", kind="ack")
            case ListenBroadcast():
                st, sys = self.own.state, self.own.sys
                if st.depth > ANTENNA_DEPTH:
                    self.say("radio.refused", {"reason": "vi måste upp på antenndjup för att höra "
                                                         "Moskva"})
                elif sys.health["radio"] < 0.3:
                    self.say("radio.refused", {"reason": "radion är skadad"})
                elif not masts_clear(self.game.world):
                    self.say("radio.refused", {"reason": "det är is ovanför, antennen kommer inte upp"})
                elif self._listen_until is None:
                    self._listen_until = self.now + LISTEN_S
                    self.say("radio.listen", kind="ack")
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
            got = self._listen >= RECEIVE_S
            items.append(Gauge("SAMBAND", "Samband", "öppet nu, " + (
                "mottaget" if got else "lyssnar" if self._listen else f"antenndjup ≤ {ANTENNA_DEPTH:.0f} m"),
                OK if self._listen else WARN))
        else:
            nxt = next((w for w in self.windows if w + self.window_len > self.now), None)
            items.append(Gauge("SAMBAND", "Nästa samband",
                               self.game.clock_str(nxt)[:5] if nxt is not None else "inget planerat",
                               WARN if i is not None else INFO))
        items.append(Gauge("SAMBAND", "Mottaget", f"{len(self.delivered)} meddelanden", INFO))
        return items

    def needs_mast(self) -> bool:
        """Behöver radion oss uppe: ett sambandstillfälle som inte är avklarat, eller en
        rapport som ordern kräver och som inte är sänd medan fönstret är öppet."""
        if self.window_pending() is not None:
            return True
        return self.report_required and any(
            w0 <= self.now < w0 + self.window_len and self._reported_t < w0 for w0 in self.windows)

    def window_pending(self) -> int | None:
        """Ett sambandstillfälle som snart börjar eller pågår och inte är avklarat."""
        for i, w0 in enumerate(self.windows):
            if i not in self._handled and w0 - PREWARN_S <= self.now < w0 + self.window_len:
                return i
        return None

    def idle_proposals(self) -> list[Proposal]:
        if self.own.state.depth <= ANTENNA_DEPTH:
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
                return [Proposal(3, f"idle_window{i}", "radio.prewarn", "antenndjup",
                                 d, cooldown=900)]
        return []

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
        st = self.own.state
        if self._listen_until is not None:
            if st.depth > ANTENNA_DEPTH + 1 or not masts_clear(self.game.world):
                self._listen_until = None
                self.say("radio.listen.lost")
            elif self.now >= self._listen_until:
                self._broadcast()
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
                self.say("radio.aborted")
            elif self.now >= self.tx_done_t:
                self.tx_done_t = None
                w = self.game.world
                w.mission["reports_sent"] = w.mission.get("reports_sent", 0) + 1
                w.mission["last_report_t"] = self.now
                self._reported_t = self.now
                self.say("radio.sent", {"contacts": len(self.game.knowledge.tracks)})
                self.game.bus.publish(OwnActionLogged(self.now, "report"))

        for i, w0 in enumerate(self.windows):
            if w0 <= self.now < w0 + self.window_len:
                self._report_advice(w0)
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
                elif st.depth > ANTENNA_DEPTH and (near := self._threat_near()) is not None:
                    self.say("radio.wait", {**d, "designation": near[0], "range": near[1]})
                    self._waiting.add(i)
                elif st.depth > ANTENNA_DEPTH:
                    self.suggest(f"window{i}", "radio.prewarn", d, order="antenndjup", cooldown=0)
                else:
                    self.say("radio.prewarn", d)
            if i in self._waiting and st.depth > ANTENNA_DEPTH and self.now % 30 == 0:
                self._clear_advice(i, w0)
            if w0 <= self.now < w0 + self.window_len:
                if i not in self._opened:
                    self._opened.add(i)
                    self._listen = 0
                    self.say("radio.window_open")
                if st.depth <= ANTENNA_DEPTH and not masts_clear(self.game.world):
                    if i not in self._ice_warned:
                        self._ice_warned.add(i)
                        self.say("radio.ice")
                elif st.depth <= ANTENNA_DEPTH and self.own.sys.health["radio"] >= 0.3:
                    self._listen += 1
                    if self._listen >= RECEIVE_S:
                        self._handled.add(i)
                        self._deliver(upto=i)
            elif self.now >= w0 + self.window_len:
                self._handled.add(i)
                if self._next_msg <= i and self._next_msg < len(self.messages):
                    self.say("radio.missed", alarm=False)

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
        self.suggest(f"clear{i}", "radio.clear", d, order="antenndjup", cooldown=0)

    def _report_advice(self, w0: int) -> None:
        """Ordern kräver en rapport: föreslå periskopdjup och sedan sändningen, men inte
        medan fienden har oss (sändningen pejlas)."""
        if not self.report_required or self._reported_t >= w0 or self.tx_done_t is not None:
            return
        if self.game.knowledge.hunted(self.now) or self._threat_near() is not None:
            return
        st = self.own.state
        if st.depth <= PERISCOPE_DEPTH + 0.5:
            self.suggest("report_send", "radio.suggest.report", {"now": True},
                         order="sänd rapport", cooldown=REPORT_SUGGEST_S)
        elif st.depth <= ANTENNA_DEPTH + 0.5 and any(
                i in self._handled for i, w in enumerate(self.windows) if w == w0):
            self.suggest("report_depth", "radio.suggest.report", {"now": False},
                         order="periskopdjup", cooldown=REPORT_SUGGEST_S)

    def _deliver(self, upto: int) -> None:
        any_msg = False
        while self._next_msg <= upto and self._next_msg < len(self.messages):
            msg = self.messages[self._next_msg]
            self._next_msg += 1
            self.delivered.append(msg.text)
            self.received += 1
            self.game.bus.publish(TelegramReceived(self.now, msg.text, "telegram", self.received))
            self.game.world.mission.update(msg.flags)
            if msg.waypoint is not None:
                name, x, y, sigma, t_pos = msg.waypoint
                self.game.bus.publish(PositionReported(self.now, name, x, y, sigma, t_pos))
            self.say("radio.message", {"text": msg.text, "telegram": self.received,
                                       "telegram_kind": "telegram", "read_aloud": msg.text},
                     kind="info", alarm=True)
            any_msg = True
        if not any_msg:
            self.say("radio.nothing")
