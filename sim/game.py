"""Spelmotorn: en tunn samordnare.

Game äger världen (sanning), kunskapslagret, händelsebussen, rapportkön
och stationerna. All ombordlogik bor i stationerna (sim/stations/).

Gränssnittet anropar bara:
    game.command(text)   – kaptenens order
    game.tick()          – en sekund simtid
    game.status()        – ögonblicksbild för statusraden
och prenumererar på händelser via game.bus.

Ett tick:
    1. världen rör sig ett steg (sanning)
    2. varje station uppdateras, i ordning
    3. förfallna rapporter formuleras och levereras (larm -> 1x)
    4. Tick publiceras; om världen har nått ett slut publiceras GameEnded
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from . import phrases, russian
from .chart import ChartView
from .profile import ProfileView
from .sonar_view import SonarView
from .systems import SystemsView
from .crew import CrewMember, Role
from .events import (EventBus, GameEnded, Handover, OrderIssued, PositionReported,
                     ReportDelivered, Tick, TimeScaleChanged)
from .broadcasts import order_day
from .environment import Almanac
from .fmt import clock
from .knowledge import Knowledge
from .logbook import Logbook
from .orders import (HELP_COMMAND, QUIT_COMMAND, SUGGESTION_COMMANDS, TIME_COMMAND,
                     AcceptSuggestion, Quit,
                     AskSuggestion, CommandRegistry, DeclineSuggestion, Help, Order,
                     split_orders,
                     SetTimeScale, Unknown)
from .ownship import PERISCOPE_DEPTH
from .reports import Quality, Report, ReportQueue
from .scenario import Scenario
from .stations import DEFAULT_STATIONS, NavigationStation, Station
from .goals import NuclearFired, council_summary, report_summary
from .theatre import task_summary
from .truthlog import TruthLog

S = TypeVar("S", bound=Station)
V = TypeVar("V")
SUGGESTION_TTL = 300
ALARM_HOLD_S = 30           # ett larmförslag står så länge mot vanliga förslag
HELD_MAX_S = 60             # ett förslag som väntat bakom ett larm släpps när det är så här gammalt
SAME_SUGGESTION_S = 30      # en annan station föreslår samma order så här snart efter: släpps (senare
                            # kommer den fram, med sitt skäl: grundvarningen efter sonarns djupförslag)
QUIT_CONFIRMED = "avbryt uppdraget bekräftat"   # ordern som ja verkställer efter frågan


@dataclass(frozen=True)
class StatusSnapshot:
    clock: int                  # sekunder efter midnatt
    sim_time: int
    course: float
    ordered_course: float
    speed: float
    ordered_speed: float
    depth: float
    ordered_depth: float
    changing: frozenset[str]
    time_scale: int
    contacts_held: tuple[str, ...] = ()     # hot först, sedan okända, handel, is och eget
    reactor: str = "online"
    propulsion: str = "turbine"
    battery: float = 1.0
    hull: float = 1.0
    flooding: float = 0.0
    periscope_depth: bool = False
    masts_up: bool = False
    radar_up: bool = False          # radarmasten uppe (julgranen)
    transmitting: bool = False      # antennen uppe och sänder
    blowing: bool = False           # nödblåsning pågår
    cavitating: bool = False
    suggestion: str | None = None
    over: bool = False
    sea_noise: float = 0.0          # bakgrundsbrus sonaren hör, dB
    under_ice: bool = False
    fire: bool = False
    smoke: float = 0.0
    ventilating: bool = False
    on_bottom: bool = False
    bridge: str = "shut"            # tornluckan: shut, manning, manned, clearing
    periscope: str | None = None    # periskopet: sweep, look, hold; None = nere
    periscope_train: float = 0.0    # okularets bäring (periskopets gradring)
    periscope_up_s: int = 0         # så länge masten varit uppe
    periscope_power: str = "låg"    # förstoringen i okularet (låg, hög), från periskopet
    periscope_optic: str = "periskop"   # periskop, eller kikare från bryggan
    night: bool = False             # mörkt ute (centralen går på rött ljus)
    hunted: bool = False            # sonar hör att fienden har oss
    contact_kinds: tuple[str, ...] = ()   # slaget per hållen kontakt (sonar_view.KINDS)
    contact_bearings: tuple[float | None, ...] = ()   # plottets senaste bäring per hållen kontakt
    command: str = "captain"        # vem som har befälet: captain eller starpom
    captain_at: str = "central"     # var kaptenen är: central eller cabin (hytten)
    phone: str | None = None        # snabbtelefonen i hytten: lamp eller ring
    sleeping: bool = False          # kaptenen sover (snabbspolat tills han väcks)
    order_day: int | None = None    # orderns dag i oktober 1962 (almanackan i hytten)
    decision: str | None = None     # förslaget starpom bett kaptenen besluta om (hytten)
    door: str | None = None         # hyttdörren: steps (någon utanför), ajar (ordonnansen), open (kaptenen går)
    pitch: float = 0.0              # lutningen (дифферент), grader, + förlig
    plane_load: float = 0.0         # andel av djuprodrens förmåga som bär vikten (+ tung)
    astern: bool = False            # båten går akterut (speed är farten genom vattnet)
    ordered_astern: bool = False    # back i maskin beordrad


def build_registry(station_classes: list[type[Station]]) -> CommandRegistry:
    reg = CommandRegistry([TIME_COMMAND, *SUGGESTION_COMMANDS])
    for cls in station_classes:
        reg.register(*cls.COMMANDS)
    reg.register(QUIT_COMMAND, HELP_COMMAND)
    return reg


OUTCOME_TEXT = {
    "lost": "K-114 är förlorad med hela besättningen.",
    "forced": "K-114 har tvingats till ytan under amerikansk bevakning. Uppdraget har misslyckats, "
              "men besättningen lever.",
    "sank": "Den amerikanska jagaren är sänkt. Vad som händer nu avgörs inte längre i Kvadrat 7.",
    "patrol_end": "Patrullen är slut. K-114 lämnar Kvadrat 7.",
    "station_reached": "K-114 har nått målet.",
    "neutral_sunk": "K-114 har sänkt ett civilt fartyg. Patrullen avbryts; befälhavaren kallas "
                    "hem för att stå till svars.",
    "quit": "Kaptenen har avbrutit patrullen. K-114 lämnar Kvadrat 7 i förtid.",
    "nuclear": "K-114 har avfyrat en kärnladdning. Eldklotet syntes på många sjömils håll. Vad som "
               "händer nu avgörs inte längre till sjöss: det som skulle förhindras har börjat.",
}


def outcome_text(scenario: Scenario | None, outcome: str) -> str:
    if scenario is not None and outcome in scenario.outcome_text:
        return scenario.outcome_text[outcome]
    return OUTCOME_TEXT.get(outcome, outcome)


class Game:
    def __init__(self, scenario: Scenario, seed: int | None = None,
                 truth_log: TruthLog | None = None,
                 stations: list[type[Station]] | None = None, warm_up: bool = True):
        self.rng = random.Random(seed)
        # en egen slumpström per station och användning (rng_for), så att en ny dragning i en
        # station inte flyttar allt annat; samma frö ⇒ samma strömmar
        self._rng_base = seed if seed is not None else self.rng.getrandbits(64)
        self._rngs: dict[str, random.Random] = {}
        self.scenario = scenario
        self.world = scenario.world
        if self.world.goal(NuclearFired) is None:   # i alla scenarier: kärnladdningen avslutar
            self.world.goals.append(NuclearFired())
        env = self.world.env
        if env.weather is not None:          # vädret: egen slumpström (sim/weather.py)
            env.weather.rng = self.rng_for("weather")
        if env.date is None:                 # datumet ur orderns DATUM-rad (solen och månen)
            day = order_day(scenario.secret_order or "")
            env.date = (1962, 10, day) if day else None
        self.crew: dict[Role, CrewMember] = scenario.crew
        self.start_clock = scenario.start_clock
        self.secret_order = scenario.secret_order
        self.truth_log = truth_log
        self.time_scale = 1
        # vyerna (sjökort, profil, sonar, systemtavla) byggs en gång per läge: läget ändras
        # av tick, order och tidsskalan (_version) och av händelser på bussen
        self._version = 0
        self._views: dict[str, tuple[tuple[int, int], Any]] = {}
        self.over = False
        self.suggestion: tuple[str, str, int] | None = None   # (order, text, t)
        self.suggestion_by = ""                                 # vem som gav förslaget
        self.suggestion_alarm = False            # det väntande förslaget är ett larm
        # ett vanligt förslag som kom medan ett larmförslag stod (ALARM_HOLD_S); det nyaste
        # vinner och levereras när larmet är besvarat eller tiden gått (_release_held)
        self.held: Report | None = None
        # senaste order av varje typ: typ -> (order, tid). Används för att inte
        # föreslå eller hålla kvar förslag om sådant kaptenen redan beslutat.
        self._ordered: dict[type[Order], tuple[Order, int]] = {}
        self.last_command_t = 0                  # senaste inmatning från kaptenen
        self.last_suggestion_t = 0               # senaste levererade förslag
        self.suggested_at: dict[str, int] = {}   # order -> senast föreslagen

        self.bus = EventBus()
        self.queue = ReportQueue()
        self.knowledge = Knowledge(bathymetry=scenario.chart_seabed,
                                   tide_table=scenario.tide_table,
                                   fairway=tuple(scenario.fairway),
                                   fairway_to=scenario.fairway_to,
                                   order_tasks=frozenset(scenario.tasks),
                                   almanac=Almanac.of(self.world.env),
                                   lights=tuple(scenario.light_list))
        self.knowledge.attach(self.bus)          # före stationerna, se events.py

        station_classes = stations if stations is not None else DEFAULT_STATIONS
        self.stations: list[Station] = [cls(self) for cls in station_classes]
        for st in self.stations:
            st.attach(self.bus)
        self.registry = build_registry(station_classes)
        for name, x, y, sigma, t, *rest in scenario.known_positions:   # (…[, (kurs, fart), uppgift])
            self.bus.publish(PositionReported(0, name, x, y, sigma, t, "order",
                                              motion=rest[0] if rest else None,
                                              task=len(rest) > 1 and bool(rest[1])))
        # loggboken börjar när kaptenen tar befälet, efter en ev. uppvärmning
        self.logbook = Logbook(self.clock_str)
        self.warmup_pending = scenario.warmup is not None
        if not self.warmup_pending:
            self.logbook.attach(self.bus)
        elif warm_up:
            self.warm_up()

    def warm_up(self) -> None:
        """Kör vakten före kaptenen (Scenario.warmup) och lämna över befälet.

        Gränssnittet kan skapa Game med warm_up=False och köra detta i en tråd medan
        ordern skrivs ut; det ska prenumerera på rapporterna först efteråt, så att
        vaktens rapporter inte syns. Lägesrapporten (Handover) levereras efter."""
        if not self.warmup_pending:
            return
        self.warmup_pending = False
        w = self.scenario.warmup
        for t in range(w.seconds):
            if w.pilot(self, t):            # vakten lämnar över tidigare
                break
            self.tick()
            if self.over:
                break
        self.suggestion = None
        self.held = None
        self.last_command_t = self.last_suggestion_t = self.now
        self.logbook.start_t = self.now
        self.logbook.attach(self.bus)
        if not self.over:
            self.bus.publish(Handover(self.now, w.seconds))

    # ------------------------------------------------------------------ åtkomst
    @property
    def now(self) -> int:
        return self.world.time

    def station(self, cls: type[S]) -> S:
        for st in self.stations:
            if isinstance(st, cls):
                return st
        raise KeyError(cls.__name__)

    def own_position_estimate(self) -> tuple[float, float]:
        try:
            return self.station(NavigationStation).position_estimate()
        except KeyError:
            s = self.world.own.state
            return s.x, s.y

    @property
    def area_name(self) -> str:
        return self.scenario.area_name if self.scenario else "kvadrat 7"

    @property
    def escape_nm(self) -> float | None:
        """Om målet är att lämna området: marginalen utanför kanten (nm). Med `escape_task`
        först när ordern (kunskapen) har den uppgiften, t.ex. när staben kallat hem oss."""
        sc = self.scenario
        if sc is None:
            return None
        if sc.escape_task is not None and sc.escape_task not in self.knowledge.order_tasks:
            return None
        return sc.escape_margin_nm

    def recalled(self) -> bool:
        """Har staben kallat hem oss (`Scenario.escape_task` i ordern)? Då är vägen ut det enda
        som gäller: plottlaget föreslår inga nya ben för bättre lösningar."""
        sc = self.scenario
        return sc is not None and sc.escape_task is not None and \
            sc.escape_task in self.knowledge.order_tasks

    def escape_ready(self) -> bool:
        """Har vi det vi kom för (t.ex. fotot), så att vägen ut är det som återstår?"""
        need = self.scenario.escape_requires_photo if self.scenario else None
        best = self.knowledge.best_photo
        if self.scenario is not None and self.scenario.escape_requires_record and \
                not self.knowledge.recorded:
            return False
        return need is None or (best is not None and best >= need)

    def clock_str(self, sim_t: int | None = None) -> str:
        return clock(self.start_clock + (self.now if sim_t is None else sim_t))

    def rng_for(self, name: str) -> random.Random:
        """Slumpströmmen för `name` (t.ex. "navigation", "delay:sonar"): densamma varje gång,
        oberoende av de andra strömmarna och av PYTHONHASHSEED (strängfrö går via sha512)."""
        if name not in self._rngs:
            self._rngs[name] = random.Random(f"{self._rng_base}:{name}")
        return self._rngs[name]

    # ------------------------------------------------------------------ rapporter
    def say(self, role: Role, type: str, data: dict[str, Any], *, kind: str = "info",
            quality: Quality | None = None, alarm: bool = False, extra_delay: int = 0) -> None:
        member = self.crew[role]
        self.queue.submit(Report(
            t_due=self.now + member.report_delay(self.rng_for(f"delay:{role.value}")) + extra_delay,
            speaker=member.callsign, type=type, data=data, role=role.value,
            quality=quality, alarm=alarm, kind=kind))

    def suggestion_redundant(self, order_text: str, made_t: int) -> bool:
        """Har kaptenen redan beslutat i frågan?

        Sant om en order av samma typ har getts sedan förslaget gjordes
        (förslaget är inaktuellt), eller om förslaget är exakt den bestående
        order som redan gäller (t.ex. "fart 6" när fart 6 är beordrad).
        """
        o = self.registry.parse(order_text)
        last = self._ordered.get(type(o))
        if last is None:
            return False
        last_order, t = last
        return t >= made_t or (o.STANDING and last_order == o)

    def _deliver(self, r: Report) -> None:
        if r.kind == "suggest" and r.data.get("order") and self._suggestion_stale(r):
            return
        phrases.render(r, self.clock_str)
        if r.kind == "suggest" and r.data.get("order"):
            self.suggestion = (r.data["order"], r.text, self.now)
            self.suggestion_by = r.speaker
            self.suggestion_alarm = r.alarm
            self.last_suggestion_t = self.now
            self.suggested_at[r.data["order"]] = self.now
        self.bus.publish(ReportDelivered(self.now, r))
        if r.kind == "suggest" and r.data.get("order") and self.suggestion is not None \
                and self.suggestion[0] == r.data["order"]:
            for st in self.stations:
                if st.on_suggestion(r):         # starpom med befälet har beslutat
                    if self.suggestion is not None and self.suggestion[0] == r.data["order"]:
                        self.suggestion = None
                    break

    def _suggestion_stale(self, r: Report) -> bool:
        """Ska förslaget inte levereras? Kaptenen har redan beslutat, någon station säger nu nej
        (läget har ändrats sedan förslaget gjordes), eller en annan station har just föreslagit
        samma sak och det står obesvarat."""
        order = r.data["order"]
        if self.suggestion_redundant(order, r.data.get("made_t", r.t_due)):
            return True
        if any(st.vetoes(order) for st in self.stations):
            return True
        sug = self.active_suggestion()
        return sug is not None and sug[0] == order and r.speaker != self.suggestion_by and \
            self.now - sug[2] < SAME_SUGGESTION_S

    def _confirm_quit(self) -> None:
        """Vakthavande frågar innan uppdraget avbryts; ja verkställer."""
        officer = self.crew[Role.OFFICER]
        self._deliver(Report(self.now, officer.callsign, "off.confirm_quit",
                             {"order": QUIT_CONFIRMED}, role=Role.OFFICER.value, kind="suggest"))

    def _system(self, type: str, data: dict[str, Any]) -> None:
        self._deliver(Report(self.now, "", type, data, kind="system"))

    def log(self, text: str) -> None:
        if self.truth_log:
            self.truth_log.note(self.now, text)

    def set_time_scale(self, scale: int, reason: str = "") -> None:
        if scale != self.time_scale:
            self._version += 1
            self.time_scale = scale
            self.bus.publish(TimeScaleChanged(self.now, scale, reason))

    def _alarm_holds(self) -> bool:
        """Ett larmförslag väntar på svar och får inte ersättas av ett vanligt förslag."""
        return self.suggestion is not None and self.suggestion_alarm and \
            self.now - self.suggestion[2] < ALARM_HOLD_S

    def _hold(self, r: Report) -> bool:
        """Ett vanligt förslag medan ett larmförslag står: vänta (det nyaste vinner)."""
        if r.kind != "suggest" or not r.data.get("order") or r.alarm or not self._alarm_holds():
            return False
        self.held = r
        return True

    def _release_held(self) -> Report | None:
        """Det väntande förslaget, när larmet är besvarat eller har stått ALARM_HOLD_S. Släpps om
        det blivit för gammalt eller någon station nu säger nej; redan beslutat släpper _deliver."""
        r = self.held
        if r is None or self._alarm_holds():
            return None
        self.held = None
        order = r.data["order"]
        if self.now - r.data.get("made_t", r.t_due) > HELD_MAX_S or \
                any(st.vetoes(order) for st in self.stations):
            return None
        self._deliver(r)
        return r

    def active_suggestion(self) -> tuple[str, str, int] | None:
        if self.suggestion and self.now - self.suggestion[2] <= SUGGESTION_TTL:
            return self.suggestion
        return None

    # ------------------------------------------------------------------ order
    def command(self, text: str, by: str = "captain") -> None:
        """Kaptenens inmatning. Flera order kan ges på en rad, åtskilda med
        komma, semikolon eller "och"; de verkställs i tur och ordning.
        by="starpom": ordern ges av den som har befälet i kaptenens ställe."""
        parts = split_orders(text)
        if len(parts) <= 1:
            self._command_one(text, by=by)
            return
        for part in parts:
            self._command_one(part, many=True, by=by)

    def _command_one(self, text: str, many: bool = False, by: str = "captain") -> None:
        self._version += 1
        if self.over:
            return
        self.last_command_t = self.now
        order = self.registry.parse(text)
        if by == "captain" and any(st.intercept(order) for st in self.stations):
            self.log(f"ORDER {text!r} -> {order} (stoppad)")
            return
        if many and isinstance(order, Unknown):
            # säg vilken del av raden som inte gick att förstå
            order = Unknown(text, f"förstod inte \"{text}\"" + (f", {order.reason}"
                                                                   if order.reason else ""))
        self.log(f"ORDER {text!r} -> {order}" + ("" if by == "captain" else f" ({by})"))
        match order:
            case AcceptSuggestion():
                sug = self.active_suggestion()
                if sug is None:
                    self.say(Role.NAVIGATOR, "order.no_suggestion", {})
                    return
                self.suggestion = None
                self._system("order.executing", {"what": sug[0]})
                self.command(sug[0])
                return
            case DeclineSuggestion():
                self.suggestion = None
                self.say(Role.NAVIGATOR, "order.declined", {})
                return
            case AskSuggestion(role=None, other=False) if self.active_suggestion():
                self._system("order.suggestion_repeat", {"text": self.active_suggestion()[1]})
                return
        if not isinstance(order, (Unknown, Help, SetTimeScale, AskSuggestion, Quit)):
            self._ordered[type(order)] = (order, self.now)
            if self.suggestion and \
                    type(self.registry.parse(self.suggestion[0])) is type(order):
                self.suggestion = None          # kaptenen har själv beslutat i frågan
        self.bus.publish(OrderIssued(self.now, text, order, by))
        match order:
            case SetTimeScale(scale=n):
                self.set_time_scale(n, "order")
            case Help():
                self._system("system.help", {"text": self.registry.help_text() + " " + russian.glossary()})
            case Quit(confirmed=False):
                self._confirm_quit()
            case Quit():
                self.world.end("quit")
                self._end()
            case Unknown(reason=reason):
                self.say(Role.NAVIGATOR, "order.unknown", {"reason": reason})

    # ------------------------------------------------------------------ tick
    def tick(self) -> list[Report]:
        if self.over:
            return []
        self._version += 1
        self.world.tick(1)
        if self.truth_log:
            self.truth_log.tick(self.world)

        for st in self.stations:
            st.update()

        released = self._release_held()
        delivered = [released] if released else []
        for r in self.queue.due(self.now):
            if self._hold(r):                   # i tur och ordning: ett larm i samma tick räknas
                continue
            self._deliver(r)
            delivered.append(r)
            if r.alarm and self.time_scale > 1 and \
                    not any(st.keeps_time_scale(r) for st in self.stations):
                self.set_time_scale(1, "larm")
        self.bus.publish(Tick(self.now))

        if self.world.outcome is not None:
            self._end()
        return delivered

    def _end(self) -> None:
        self.over = True
        o = self.world.outcome
        m = self.world.mission
        summary = {
            "outcome": o["outcome"],
            "text": outcome_text(self.scenario, o["outcome"]),
            "cause": o.get("cause"),
            "clock": self.clock_str(),
            "detected": m.get("enemy_contacts", 0),
            "charges": m.get("charges_exploded", 0),
            "reports_sent": m.get("reports_sent", 0),
            "torpedoes": m.get("torpedoes_fired", 0),
            "nuclear": bool(m.get("nuclear_used")),
            "hull": self.world.own.sys.hull,
            "session": self.logbook.report(self.now, self.knowledge),
            "radio": report_summary(self.world, list(self.scenario.radio_windows),
                                    self.scenario.radio_window_len),
            "council": council_summary(self.world),
            "war": task_summary(self.world),
        }
        self.log(f"SLUT {summary}")
        self.bus.publish(GameEnded(self.now, o["outcome"], summary))

    # ------------------------------------------------------------------ vyerna
    def _view(self, name: str, build: Callable[[], V]) -> V:
        """Samma vy tills läget ändrats (tick, order, tidsskala). Vyn är bara till läsning."""
        key = (self._version, self.bus.published)
        hit = self._views.get(name)
        if hit is None or hit[0] != key:
            hit = self._views[name] = (key, build())
        return hit[1]

    def invalidate_views(self) -> None:
        """Bygg vyerna på nytt nästa gång (efter att någon ändrat läget utan tick eller order)."""
        self._version += 1

    def chart(self) -> ChartView:
        return self._view("chart", self._build_chart)

    def profile(self) -> ProfileView:
        return self._view("profile", self._build_profile)

    def sonar(self) -> SonarView:
        return self._view("sonar", self._build_sonar)

    def systems(self) -> SystemsView:
        return self._view("systems", self._build_systems)

    # ------------------------------------------------------------------ sjökort
    def _build_chart(self) -> ChartView:
        """Sjökortet: stationernas element ur kunskapen, i beräknade koordinater."""
        view = ChartView(self.clock_str(), self.area_name, self.world.size_nm,
                         self.own_position_estimate())
        for st in self.stations:
            view.items.extend(st.chart_items())
        return view

    # ------------------------------------------------------------------ djupprofil
    def _build_profile(self) -> ProfileView:
        """Djupprofilen: stationernas element ur kunskapen, längs tidsaxeln."""
        s = self.world.own.state
        view = ProfileView(self.clock_str(), self.now, self.start_clock, s.depth,
                           s.ordered_depth, s.speed, s.course, astern=s.astern)
        for st in self.stations:
            view.items.extend(st.profile_items())
        return view

    # ------------------------------------------------------------------ sonarvyn
    def _build_sonar(self) -> SonarView:
        """Sonarvyns vattenfall: stationernas element ur kunskapen, bäring mot tid."""
        view = SonarView(self.clock_str(), self.now, self.start_clock,
                         self.world.own.state.course)
        for st in self.stations:
            view.items.extend(st.sonar_items())
        return view

    # ------------------------------------------------------------------ systemtavla
    def _build_systems(self) -> SystemsView:
        """Systemtavlan: stationernas element ur egna instrument."""
        view = SystemsView(self.clock_str())
        for st in self.stations:
            view.items.extend(st.system_items())
        return view

    # ------------------------------------------------------------------ status
    def status(self) -> StatusSnapshot:
        """Ögonblicksbilden: egen ubåt här, resten ur stationernas `status_fields()`."""
        own = self.world.own
        s, sy = own.state, own.sys
        from .acoustics import cavitation_speed
        sug = self.active_suggestion()
        return StatusSnapshot(
            clock=(self.start_clock + self.now) % 86400, sim_time=self.now,
            course=s.course, ordered_course=s.ordered_course,
            speed=s.speed, ordered_speed=s.ordered_speed,
            astern=s.astern, ordered_astern=s.ordered_astern,
            depth=s.depth, ordered_depth=s.ordered_depth,
            changing=frozenset(s.changing()), time_scale=self.time_scale,
            reactor=sy.reactor, propulsion=sy.propulsion, battery=sy.battery,
            hull=sy.hull, flooding=sy.flooding,
            periscope_depth=s.depth <= PERISCOPE_DEPTH, masts_up=own.masts_up(self.now),
            radar_up=sy.radar_until > self.now, transmitting=sy.transmit_until > self.now,
            blowing=sy.blowing,
            cavitating=s.speed > cavitation_speed(s.depth, s.prop_astern),
            suggestion=sug[0] if sug else None, over=self.over,
            fire=sy.fire, smoke=sy.smoke, ventilating=sy.ventilating, on_bottom=sy.on_bottom,
            bridge=sy.bridge,
            night=not self.world.env.is_day(self.now), hunted=self.knowledge.hunted(self.now),
            **{k: v for st in self.stations for k, v in st.status_fields().items()},
        )

