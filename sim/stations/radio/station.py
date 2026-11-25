"""Radion: stationen, order, tavlan, förslagen, uppdateringen och radiospaningen."""
from __future__ import annotations


from ...crew import Role
from ...broadcasts import broadcasts_for, order_day
from ...dispatch import SentReport, report_text
from ...headquarters import Headquarters
from ...events import (ContactSunk, Handover, InterceptHeard, NuclearOrderRead, OwnActionLogged, PhotoTaken, ReportTransmitted)
from ...icemap import thickness_words
from ...fmt import duration
from ...orders import DESIG, CommandSpec, Order, desig
from ...overview import Line
from ...reports import Quality
from ...ownship import ANTENNA_DEPTH, PERISCOPE_DEPTH
from ...profile import Cable, Level
from ...systems import INFO, OK, WARN, Gauge
from ..base import Proposal, Station
from ..navigation import NavigationStation
from .common import (
    INTERCEPT_AGAIN_S, INTERCEPT_AIR_NM, INTERCEPT_HUNT_S, INTERCEPT_S, INTERCEPT_SHIP_NM,
    CLOSING_WARN_S, Intercept, LISTEN_S, ListenBroadcast, PREWARN_S, RADIO_VAK_MAX_M, RadioStatus, SendReport,
    VLF_DEPTH, VLF_RECEIVE_S, VLF_SLOW_KN, VLF_SPEED, VLF_UP_DEPTH,
)
from .reception import ReceptionMixin
from .sending import SendingMixin


class RadioStation(ReceptionMixin, SendingMixin, Station):
    REACHES_WORLD = True        # sändningar (pejlbara emissioner), stabens meddelanden och krigsskådeplatsen
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
        # krigsskådeplatsen (theatre.py, sanning): uppgifter som staben sänder under spelet
        self.theatre = getattr(sc, "theatre", None)
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
        self.hq = Headquarters(expects_report=self.report_required,
                               at_war=bool(getattr(sc, "at_war", False)))   # vet bara vad vi sänt
        self._closed: set[int] = set()
        self._closing_said: set[int] = set()
        self._lost_wait: dict[int, str] = {}   # fönster där vi väntar på djupet efter en tappad jagare   # fönstren där radion sagt att det stänger utan rapport
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
        # sänkt är det sonar hör sjunka (brytningsljudet), inte varje detonation: en torped som gått av
        # i förtid eller på grund är ingen träff
        bus.subscribe(ContactSunk, lambda e: setattr(self, "_hit_t", e.t))

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
                self.say("radio.status", self._status_data())

    def _status_data(self) -> dict:
        """Radions läge: ett sambandstillfälle som pågår och inte är avklarat, annars nästa som inte
        börjat än, och telegrammen."""
        clock = lambda t: self.game.clock_str(t)[:5]   # noqa: E731
        d: dict = {"received": len(self.delivered),
                   "last": self.delivered[-1] if self.delivered else None}
        for i, w0 in enumerate(self.windows):
            if i not in self._handled and w0 <= self.now < w0 + self.window_len:
                d["open"], d["until"] = clock(w0), clock(w0 + self.window_len)
                break
        nxt = next((w for w in self.windows if w > self.now), None)
        if nxt is not None:
            d["next"] = clock(nxt)
        return d

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

    def overview_items(self) -> list:
        """Sambandet under UPPDRAG i översikten: öppet nu (och till när), annars nästa tillfälle."""
        i = self.window_pending()
        if i is not None and self.windows[i] <= self.now:
            end = self.windows[i] + self.window_len
            return [Line("UPPDRAG", "Samband", f"öppet nu, till {self.game.clock_str(end)[:5]}", "varning")]
        nxt = next((w for w in self.windows if w > self.now), None)
        if nxt is None:
            return []
        mins = (nxt - self.now) // 60
        return [Line("UPPDRAG", "Samband", f"nästa {self.game.clock_str(nxt)[:5]}, om {duration(mins)}",
                     "info")]

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
        innehåller: periskopdjup när ordern kräver rapport (sändningen kräver det; antenndjup räckte bara
        för att ta emot, och kaptenen fick "vi måste upp på periskopdjup för att sända" mitt i fönstret,
        kuba-kort frö 7), annars långvågen med flytkabeln."""
        st = self.own.state
        if self.report_required:
            return ("periskopdjup" if st.ordered_depth > PERISCOPE_DEPTH else None), {"up": True, "send": True}
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
                if up is None or i in self._waiting or self._threat_near() is not None or \
                        self._threat_lost() is not None or self.game.knowledge.hunted(self.now):
                    return []           # vi väntar på djupet för ett hot (radio.wait): ingen påminnelse
                return [Proposal(3, f"idle_window{i}", self._prewarn_type(), up,
                                 {**d, **how, "what": up}, cooldown=900)]
        return []

    def _prewarn_type(self) -> str:
        return "radio.prewarn" if self.report_required else "radio.prewarn_vlf"

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

        if self.now % 30 == 0:
            self._task_report_advice()
        for i, w0 in enumerate(self.windows):
            if w0 <= self.now < w0 + self.window_len:
                self._report_advice(w0)
                self._closing_warning(i, w0)
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
                    tr = self.game.knowledge.tracks.get(near[0])
                    poor = tr is not None and tr.solution is not None and tr.solution.quality < Quality.OSAKER
                    self.say("radio.wait", {**d, "designation": near[0], "range": near[1], "poor": poor})
                    self._waiting.add(i)
                elif up[0] is not None and (lost := self._threat_lost()) is not None:
                    self.say("radio.wait_lost", {**d, "designation": lost[0], "minutes": lost[1]})
                    self._waiting.add(i)
                    self._lost_wait[i] = lost[0]
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
                if self._next_msg <= i and self._next_msg < len(self.messages) or \
                        self.theatre is not None and self.theatre.pending(self.world):
                    self.say("radio.missed", {"next": self._next_window_clock()}, alarm=False)

    def _closing_warning(self, i: int, w0: int) -> None:
        """Ordern kräver en rapport och fönstret stänger snart utan den: säg det, och varför vi inte
        sänt (kuba-kort: radion teg medan jagaren hade oss, och spelet tog slut på en missad rapport
        utan att kaptenen hört ett ord om det)."""
        left = w0 + self.window_len - self.now
        if not self.report_required or i in self._closing_said or left > min(CLOSING_WARN_S, self.window_len // 2) \
                or self._reported_t >= w0 or self.tx_done_t is not None:
            return
        self._closing_said.add(i)
        k, st = self.game.knowledge, self.own.state
        near = self._threat_near()
        if k.hunted(self.now):
            why = {"why": "hunted"}
        elif near is not None:
            why = {"why": "threat", "designation": near[0], "range": near[1]}
        elif k.air_close_now():
            why = {"why": "air"}
        elif st.depth > PERISCOPE_DEPTH + 0.5:
            why = {"why": "depth"}
        else:
            why = {"why": "ready"}
        self.say("radio.closing", {"clock": self.game.clock_str(w0 + self.window_len)[:5],
                                   "minutes": max(1, round(left / 60)), **why})

    def _intercept(self) -> None:
        """Radiospaning (sensor): amerikansk flygradio, fartygens radiotrafik och om jagarna
        rapporterar kontakt till varandra. Kvaliteten ur hur mycket som hördes."""
        from ...enemy import DestroyerAI
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
