"""Navigation: kurs, fart, djup, bestick (dödräkning med drift), fix och ekolod.

Under is lodar det uppåtriktade isekolodet isen var femte sekund
(IceSounded, med beräknad position). Navigatören läser iskartan i
kunskapen, varnar för kölar och tjock is, och kan på order ("vak") styra
ubåten tillbaka till en loggad öppning och stoppa under den."""
from __future__ import annotations

import re

from ... import acoustics
from ...chart import LAYER_CONTOUR, LAYER_ICE, LAYER_OWN, LAYER_TRACK, Mark, Note, Ray, Ring, Track
from ...crew import Role
from ...fmt import clock, fmt_course, kn, nm
from ...geo import angle_diff, bearing_to, norm360, velocity
from ...ice import SAIL_TOP_M
from ...icemap import Opening
from ...orders import NUM, CommandSpec, Order, Unknown, num
from ...ownship import ANTENNA_DEPTH, CRUSH_DEPTH, PERISCOPE_DEPTH, TEST_DEPTH
from ...profile import BottomSounding, ChartBottom, DepthTrace, IceSounding, Level
from ...sonar_view import KEEP_S as SONAR_KEEP_S
from ...sonar_view import OwnHeading, own_turns
from ...systems import DANGER, INFO, OK, WARN, Gauge
from ..base import Proposal, Station
from .bottom import BottomMixin
from .current import CurrentMixin, CurrentReport
from .common import (
    ATTACK_STEP_S,
    BRIDGE_FIX_EVERY_S,
    DEPTH_LOG_INTERVAL_S,
    DIVE_ORDER,
    DR_GROWTH_NM_PER_H,
    DR_LABEL_S,
    DR_TICK_S,
    DR_TRACK_INTERVAL_S,
    FIX_VAK_MAX_M,
    ICE_FIX_SIGMA_NM,
    IDLE_FIX_SIGMA_NM,
    OWN_VECTOR_S,
    PERISCOPE_FIX_SIGMA,
    PROFILE_KEEP_S,
    SEARCH_LEG_S,
    SHOAL_CHECK_S,
    SHOAL_MARGIN_M,
    TIDE_TABLE_ERR,
    AttackApproach,
    BottomFix,
    EchoSounder,
    FollowContact,
    FollowFairway,
    GoToOpening,
    GoToStation,
    GoToWait,
    IceReport,
    ReportPosition,
    SetCourse,
    SetDepth,
    SetSpeed,
    SettleOnBottom,
    StarFix,
    SteerTo,
    TakeFix,
)
from .exit_route import ExitMixin
from .fixes import FixMixin
from .ice import IceMixin
from .steering import SteeringMixin
from .tasks import Attack, Fairway, Follow, NavTask, Steering, Wait
from .tasks import Station as StationSteer


def _course(m: re.Match) -> Order:
    c = num(m[1])
    if not 0 <= c < 360:
        return Unknown("", "kursen måste vara 000–359")
    return SetCourse(int(round(c)) % 360)



class NavigationStation(CurrentMixin, BottomMixin, FixMixin, IceMixin, SteeringMixin, ExitMixin, Station):
    REACHES_WORLD = True        # ekolodet, isekolodet och dagsljuset för landmärken
    role = Role.NAVIGATOR
    COMMANDS = [
        CommandSpec(rf"(?:kurs|k|styr)\s+{NUM}", _course, "kurs 090"),
        CommandSpec(rf"(?:fart|f)\s+{NUM}(?:\s*(?:knop|kn))?", lambda m: SetSpeed(num(m[1])), "fart 5"),
        CommandSpec(r"stopp|stoppa|stopp i maskin", lambda m: SetSpeed(0.0), "stopp"),
        CommandSpec(rf"(?:djup|d)\s+{NUM}(?:\s*(?:m|meter))?",
                    lambda m: SetDepth(int(round(num(m[1])))), "djup 100"),
        CommandSpec(r"periskopdjup|pd", lambda m: SetDepth(int(PERISCOPE_DEPTH - 1)), "periskopdjup"),
        CommandSpec(r"antenndjup", lambda m: SetDepth(int(ANTENNA_DEPTH - 2)), "antenndjup"),
        CommandSpec(r"ytläge|ytlage|upp till ytan|till ytan", lambda m: SetDepth(0), "ytläge"),
        CommandSpec(r"fix|ta fix", lambda m: TakeFix(), "fix"),
        CommandSpec(r"stjärnfix|stjarnfix|ta stjärnfix|astrofix|sextant", lambda m: StarFix(),
                    "stjärnfix"),
        CommandSpec(r"position|var är vi\??|pos", lambda m: ReportPosition(), "position"),
        CommandSpec(r"ström|strom|strömmen|strommen", lambda m: CurrentReport(), "ström"),
        CommandSpec(r"ekolod|loda", lambda m: EchoSounder(), "ekolod"),
        CommandSpec(r"isekolod|isläge|islage", lambda m: IceReport(), "isekolod"),
        CommandSpec(r"vak|gå till vaken|ga till vaken|öppning|oppning|till öppningen",
                    lambda m: GoToOpening(), "vak"),
        CommandSpec(r"(?:gå till |ga till |kurs mot |mot )?(?:drivstationen|stationen|nord-?7)",
                    lambda m: GoToStation(), "drivstationen"),
        CommandSpec(r"anfall (?:mot )?(s-?\d+)|anfallsläge (s-?\d+)|anfallslage (s-?\d+)",
                    lambda m: AttackApproach(m.group(1) or m.group(2) or m.group(3)),
                    "anfall S-1"),
        CommandSpec(r"(?:gå till |ga till |till )?(?:väntläget|vantlaget|väntläge|vantlage)",
                    lambda m: GoToWait(), "väntläget"),
        CommandSpec(r"(?:följ |folj |gå |ga |styr |ut )?(?:i |genom )?(?:farleden|fjorden)|lotsa",
                    lambda m: FollowFairway(), "farleden"),
        CommandSpec(r"följ (s-?\d+)|folj (s-?\d+)",
                    lambda m: FollowContact(m.group(1) or m.group(2)), "följ S-1"),
        CommandSpec(r"(?:kurs|styr|gå|ga) mot (.+)", lambda m: SteerTo(m.group(1)), "kurs mot <plats>"),
        CommandSpec(r"bottenfix|fix mot botten|djupfix|lodfix", lambda m: BottomFix(), "bottenfix"),
        CommandSpec(r"(?:lägg oss på |lagg oss pa |lägg på |lagg pa |sätt oss på |satt oss pa |"
                    r"gå ned på |ga ned pa )?botten", lambda m: SettleOnBottom(), "botten"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self._pending: set[str] = set()
        s = self.ship
        self.est_x, self.est_y = s.x, s.y
        # besticket på kortet: ett spår per fix, och fixarna (x, y, tid)
        self.dr_track: list[list[tuple[float, float]]] = [[(s.x, s.y)]]
        self.dr_ticks: list[tuple[int, float, float]] = []   # besticket var 10:e min på klockan
        self.fixes: list[tuple[float, float, int]] = []
        self.rng = rng = game.rng_for("navigation")
        skill = self.member.effective_skill()
        self.gyro_err = rng.gauss(0, 0.3)
        self.log_bias = rng.gauss(0, 0.01 + 0.02 * (1 - skill))
        self.last_fix_t = 0
        self.fix_sigma = PERISCOPE_FIX_SIGMA
        self._tide_fix_t, self._tide_sigma = 0, 0.0
        self._current_init()
        self.course_set_t = 0
        self.tasks: dict[str, NavTask] = {}   # pågående fixar (tasks.py), per namn
        self._next_sound = 0
        self.vak: Opening | None = None
        self._vak_t = 0
        self._vak_stopping = False
        self._vak_here = False
        self._prev_usable = False
        self._told_out = False                # har sagt att vi lämnat området
        self.exit_via: str | None = None      # vägen ut går först runt land
        self.steer: Steering | None = None    # styruppdraget (tasks.py): följ, anfall, väntläget …
        self._attack_arrived_t = -10**9       # senaste skjutläge (inget nytt anfallsförslag strax)
        self._fw_done = False                 # farleden är gången
        self._water = None                    # sjökortets vattenrutnät för vägsökning
        self._exit_cache: tuple[int, tuple | None, str | None] | None = None
        self._touching = False
        self._settle_aim = 0.0
        # djupprofilen: djupmätaren (t, djup) och ekolodets bottenlodningar
        self.depth_log: list[tuple[int, float]] = [(0, s.depth)]
        self.course_log: list[tuple[int, float]] = [(0, round(s.course, 1))]   # sonarvyn: gyrot
        self.bottom_soundings: list[BottomSounding] = []
        cd = self.chart_depth_at(s.x, s.y)
        self.chart_depth_log: list[tuple[int, float]] = [] if cd is None else [(0, round(cd))]
        self._contour_items: list | None = None


    @property
    def ship(self):
        return self.own.state

    # --- bestick ---------------------------------------------------------------
    def position_estimate(self) -> tuple[float, float]:
        return self.est_x, self.est_y

    def uncertainty(self) -> float:
        return self.fix_sigma + DR_GROWTH_NM_PER_H * self.dr_growth_factor() * \
            (self.now - self.last_fix_t) / 3600.0 \
            + (self._tide_sigma if self._tide_fix_t == self.last_fix_t else 0.0)

    # --- systemtavlan ------------------------------------------------------------
    def system_items(self) -> list:
        s, sys = self.ship, self.own.sys
        items: list = []
        g = lambda label, text, state=OK, level=None: \
            items.append(Gauge("NAVIGATION", label, text, state, level))
        txt = f"{s.depth:.0f} m"
        if abs(s.ordered_depth - s.depth) >= 1:
            txt += f" ▸ {s.ordered_depth:.0f} m"
        g("Djup", txt, DANGER if s.depth > TEST_DEPTH else
          WARN if s.depth > TEST_DEPTH - 30 else OK, min(1.0, s.depth / CRUSH_DEPTH))
        txt = fmt_course(s.course)
        if abs(angle_diff(s.ordered_course, s.course)) >= 1:
            txt += f" ▸ {fmt_course(s.ordered_course)}"
        g("Kurs", txt, INFO)
        txt = f"{kn(s.speed)} kn"
        if abs(s.ordered_speed - s.speed) >= 0.1:
            txt += f" ▸ {kn(s.ordered_speed)} kn"
        cav = s.speed > acoustics.cavitation_speed(s.depth) + 0.2
        g("Fart", txt + (", kaviterar" if cav else ""), WARN if cav else INFO)
        sigma = self.uncertainty()
        g("Bestick", f"± {nm(sigma)} nm, fix {clock(self.game.start_clock + self.last_fix_t)[:5]}",
          WARN if sigma >= 1.0 else OK)
        if (cur := self.current_gauge_text()) is not None:
            g("Ström", cur, INFO)
        bh = self.bottom_here()
        if sys.on_bottom:
            g("Botten", f"vi ligger på botten, {s.depth:.0f} m", INFO)
        elif bh is not None:
            depth, kind, sounded = bh
            under = depth - s.depth
            txt = f"{depth:.0f} m " + ("lodat" if sounded else "enligt kortet")
            if kind:
                txt += f", {kind}"
            g("Botten", txt, WARN if under < 60 else OK)
        else:
            g("Botten", "okänd", INFO)
        if self.under_ice():
            g("Is", "is ovanför" + (", på väg mot öppning" if self.vak is not None else ""), INFO)
        if self.own.masts_up(self.now):
            now = self.now
            up = [name for name, t in (("periskop", sys.periscope_until), ("radar", sys.radar_until),
                                       ("antenn", sys.transmit_until)) if t > now]
            g("Master", ", ".join(up) + " uppe", WARN)
        elif s.depth <= PERISCOPE_DEPTH:
            g("Master", "periskopdjup, nere", INFO)
        return items

    # --- sjökortet -------------------------------------------------------------
    def chart_items(self) -> list:
        s, now = self.ship, self.now
        sigma = self.uncertainty()
        items: list = [Note(f"besticket osäkert {nm(sigma)} nm, "
                            f"senaste fix {clock(self.game.start_clock + self.last_fix_t)[:5]}")]
        for seg in self.dr_track:
            pts = list(seg)
            if seg is self.dr_track[-1]:
                pts.append((self.est_x, self.est_y))
            items.append(Track(tuple(pts), "track"))
        items.extend(self._contours())
        fw = self.game.knowledge.fairway
        if len(fw) >= 2:
            items.append(Track(tuple(fw), "fairway", LAYER_CONTOUR + 0.05, "╌"))
        for b in reversed(self.bottom_soundings):      # nyaste först: dess etikett vinner
            if b.x is not None:
                items.append(Mark(b.x, b.y, "∙", "sounding", f"{b.depth:.0f}".replace(",", " "),
                                  layer=LAYER_ICE))
        for x, y, _ in self.fixes:
            items.append(Mark(x, y, "+", "fix"))
        for t, x, y in self.dr_ticks:            # tidsstreck: klockslaget varje halvtimme
            c = self.game.start_clock + t
            label = clock(c)[:5] if c % DR_LABEL_S == 0 else ""
            items.append(Mark(x, y, "◦", "track", label, layer=LAYER_TRACK + 0.2))
        # isen: lodningarna där vi beräknade att vi var
        for o in self.icemap.soundings:
            # i samma ruta vinner tunnast: öppet vatten är det vi letar efter
            sym, style, up = (("≈", "ice_open", 0.2) if o.open else
                              ("=", "ice_thin", 0.1) if o.usable else ("#", "ice_thick", 0.0))
            items.append(Mark(o.x, o.y, sym, style, layer=LAYER_ICE + up))
        for o in self.icemap.candidates(now):
            q = o.quality(now)
            cx, cy = o.center
            items.append(Mark(cx, cy, "Ö", "opening", f"Ö{o.no} {q.label}", quality=q))
        for wp in self.game.knowledge.waypoints.values():
            ws = wp.sigma(now)
            items.append(Ring(wp.x, wp.y, ws, "waypoint"))
            items.append(Mark(wp.x, wp.y, "⊕", "waypoint", f"{wp.name} ±{nm(ws)} nm"))
        items.append(Ring(self.est_x, self.est_y, sigma, "own"))
        if s.speed > 0.2:
            items.append(Ray(self.est_x, self.est_y, s.course, s.speed * OWN_VECTOR_S / 3600,
                             "own_vector"))
        items.append(Mark(self.est_x, self.est_y, "@", "own", layer=LAYER_OWN))
        return items

    # --- djupprofilen ------------------------------------------------------------
    def profile_items(self) -> list:
        items: list = [
            Level(0.0, "yta", "surface", "≈"),
            Level(PERISCOPE_DEPTH, "periskopdjup", "periscope", "┄"),
            Level(TEST_DEPTH, "provdjup", "test", "╌"),
            Level(CRUSH_DEPTH, "krossdjup", "crush", "━"),
            DepthTrace(tuple(self.depth_log) + ((self.now, self.ship.depth),)),
        ]
        if self.chart_depth_log:
            items.append(ChartBottom(tuple(self.chart_depth_log)))
        items.extend(self.bottom_soundings)
        items.extend(IceSounding(o.t, o.thickness, o.draft, o.open, o.usable)
                     for o in self.icemap.soundings)
        return items

    # --- sonarvyn ----------------------------------------------------------------
    def sonar_items(self) -> list:
        """Vår kurs över tid (för relativ bäring) och våra girar, ur gyrot."""
        pts = tuple(self.course_log)
        if not pts or pts[-1][0] < self.now:          # kursen nu, om den inte just loggats
            pts += ((self.now, round(self.ship.course, 1)),)
        return [OwnHeading(pts), *own_turns(pts)]

    def _log_depth(self) -> None:
        if self.now % DEPTH_LOG_INTERVAL_S:
            return
        self.depth_log.append((self.now, round(self.ship.depth, 1)))
        self.course_log.append((self.now, round(self.ship.course, 1)))
        if self.course_log[0][0] < self.now - SONAR_KEEP_S:
            self.course_log = [p for p in self.course_log if p[0] >= self.now - SONAR_KEEP_S]
        cd = self.chart_depth_at(self.est_x, self.est_y)
        if cd is not None:
            self.chart_depth_log.append((self.now, round(cd)))
        cutoff = self.now - PROFILE_KEEP_S
        if self.depth_log[0][0] < cutoff:
            self.depth_log = [p for p in self.depth_log if p[0] >= cutoff]
            self.chart_depth_log = [p for p in self.chart_depth_log if p[0] >= cutoff]
            self.bottom_soundings = [b for b in self.bottom_soundings if b.t >= cutoff]

    def _dead_reckon(self) -> None:
        s = self.ship
        vx, vy = velocity(s.course + self.gyro_err, s.speed * (1 + self.log_bias))
        if self._tide_fix_t != self.last_fix_t:
            self._tide_fix_t, self._tide_sigma = self.last_fix_t, 0.0
        tide = self.game.knowledge.tide_table
        if tide is not None and not self.own.sys.on_bottom:
            depth = self.chart_depth_at(self.est_x, self.est_y)
            if depth is not None:
                sp = tide.speed(self.now, depth)
                tx, ty = velocity(tide.flood_set, sp)
                vx, vy = vx + tx, vy + ty
                self._tide_sigma += TIDE_TABLE_ERR * abs(sp) / 3600.0
        if not self.own.sys.on_bottom:
            cx, cy = self.current_velocity()            # strömmen navigatören räknat ut
            vx, vy = vx + cx, vy + cy
        self.est_x += vx
        self.est_y += vy

    def tide_now(self) -> float | None:
        """Tidvattnet här enligt tabellen, knop längs flodriktningen (negativt vid ebb)."""
        tide = self.game.knowledge.tide_table
        depth = self.chart_depth_at(self.est_x, self.est_y)
        if tide is None or depth is None:
            return None
        return tide.speed(self.now, depth)

    # --- order -------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        s = self.ship
        match order:
            case SetCourse(course=c):
                self.vak = None
                self.steer = None
                self.course_set_t = self.now
                s.order_course(c)
                self._ack("course", {"course": c}, s.course == s.ordered_course)
            case SetSpeed(speed=v):
                self.vak = None
                if isinstance(self.steer, Wait):
                    self.steer = None           # kaptenen tar över farten: vi håller inte läget
                if isinstance(self.steer, Follow):
                    self.steer.hold_speed = False   # kaptenen sätter farten själv
                if v > 0:
                    self._lift()
                limit = self.own.max_speed()
                if v > limit:
                    self.say("nav.limit", {"what": "speed", "limit": limit})
                    return
                s.order_speed(v)
                self._ack("speed", {"speed": v}, s.speed == s.ordered_speed)
            case SetDepth(depth=d):
                self._lift()
                if d > s.max_depth:
                    self.say("nav.limit", {"what": "depth", "limit": s.max_depth})
                    return
                if d > 0 and self._dive_forbidden_here():
                    self.say("nav.fjord_dive", alarm=True)
                s.order_depth(d)
                data = {"depth": d, "below_test": d > TEST_DEPTH}
                latest = self.icemap.latest(self.now)
                if latest is not None and not latest.usable and d < latest.draft + SAIL_TOP_M:
                    data["ice_ceiling"] = latest.draft + SAIL_TOP_M
                elif latest is not None and not latest.open and d <= ANTENNA_DEPTH:
                    data["ice_masts"] = True
                shoal = self.known_bottom()
                if shoal is not None and d > shoal[0] - SHOAL_MARGIN_M:
                    data["shoal"] = round(shoal[0], -1)
                self._ack("depth", data, s.depth == s.ordered_depth)
            case TakeFix():
                self._start_fix()
            case StarFix():
                self._start_star_fix()
            case CurrentReport():
                self._current_report()
            case ReportPosition():
                self.say("nav.position", {"x": self.est_x, "y": self.est_y,
                                          "sigma": self.uncertainty(),
                                          "last_fix": self.game.clock_str(self.last_fix_t)})
            case EchoSounder():
                self.say("nav.echo", {"under_keel": self._echo() - s.depth})
            case BottomFix():
                self._start_bottom_fix()
            case IceReport():
                self._ice_report()
            case GoToOpening():
                self._go_to_opening()
            case GoToStation():
                self._go_to_station()
            case SteerTo(name=name):
                self._steer_to(name)
            case GoToWait():
                self._start_wait()
            case FollowFairway():
                self._start_fairway()
            case FollowContact(designation=d):
                self._start_follow(d)
            case AttackApproach(designation=d):
                self._start_attack(d)
            case SettleOnBottom():
                self._settle()

    def _ack(self, what: str, data: dict, already: bool) -> None:
        self.say(f"nav.{what}.ack", {**data, "already": already}, kind="ack")
        if already:
            self._pending.discard(what)
        else:
            self._pending.add(what)

    def vetoes(self, order: str) -> bool:
        """Ingen i besättningen föreslår dykning där ordern förbjuder det."""
        return bool(DIVE_ORDER.search(order.lower())) and self._dive_forbidden_here()

    def _dive_forbidden_here(self) -> bool:
        """Ordern förbjuder dykning i fjorden, och kortet säger att vi är där."""
        sc = self.game.scenario
        chart = self.game.knowledge.bathymetry
        if sc is None or not getattr(sc, "no_dive_in_fjord", False) or chart is None:
            return False
        return any(hasattr(f, "in_fjord") and bool(f.in_fjord(self.est_x, self.est_y, 0.0))
                   for f in chart.features)

    # --- initiativ vid tystnad -----------------------------------------------------
    def _quiet_contact_picture(self) -> bool:
        """Ingen kontakt hålls och ingen har hörts på SEARCH_LEG_S sekunder."""
        tracks = self.game.knowledge.tracks.values()
        if any(t.threat for t in tracks):
            return False
        last = max((t.observations[-1].t for t in tracks if t.observations), default=-10**9)
        return self.now - last >= SEARCH_LEG_S

    def idle_proposals(self) -> list[Proposal]:
        s = self.ship
        out = []
        if s.depth > TEST_DEPTH + 5:
            out.append(Proposal(1, "idle_test_depth", "nav.suggest.test_depth", "djup 280",
                                {"depth": s.depth}, cooldown=300))
        size = self.area_nm
        if self.game.escape_nm is not None:
            if self.game.escape_ready() and (route := self.exit_route()) is not None:
                c, dist, clear = route
                out.append(Proposal(3, "idle_exit", "nav.suggest.exit", f"kurs {fmt_course(c)}",
                                    {"course": c, "dist": dist, "clear": clear,
                                     "area": self.game.area_name, "via": self.exit_via},
                                    cooldown=900))
        elif not (0.5 <= self.est_x <= size - 0.5 and 0.5 <= self.est_y <= size - 0.5):
            c = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            out.append(Proposal(3, "idle_area", "nav.suggest.area", f"kurs {fmt_course(c)}",
                                {"course": c, "area": self.game.area_name}, cooldown=900))
        if (p := self._settle_proposal()) is not None:
            out.append(p)
        held = self.game.knowledge.threat_held()
        sigma = self.uncertainty()
        if self.icemap.soundings:
            o = self.best_opening() if self.under_ice() else None
            if not held and sigma > ICE_FIX_SIGMA_NM and "fix" not in self.tasks and \
                    o is not None and self.vak is None and \
                    self.opening_data(o)["range"] <= FIX_VAK_MAX_M:
                out.append(Proposal(4, "idle_fix_vak", "nav.suggest.fix_vak", "vak",
                                    {"sigma": sigma, **self.opening_data(o)},
                                    quality=o.quality(self.now)))
        elif not held and sigma > IDLE_FIX_SIGMA_NM and "fix" not in self.tasks:
            if s.depth <= PERISCOPE_DEPTH and s.speed <= 7:
                out.append(Proposal(4, "idle_fix_now", "nav.suggest.fix_now", "fix",
                                    {"sigma": sigma}, cooldown=900))
            elif s.depth > PERISCOPE_DEPTH:
                out.append(Proposal(4, "idle_fix", "nav.suggest.fix", "periskopdjup",
                                    {"sigma": sigma}))
        if self.game.escape_nm is None and self._quiet_contact_picture() \
                and self.now - self.course_set_t >= SEARCH_LEG_S \
                and self.vak is None and self.goal is None and s.ordered_speed > 0:
            # gir 90° åt den sida som pekar mest mot kvadratens mitt
            size = self.area_nm
            to_mid = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            c = min((norm360(s.ordered_course + 90), norm360(s.ordered_course - 90)),
                    key=lambda k: abs(angle_diff(k, to_mid)))
            out.append(Proposal(6, "idle_search", "nav.suggest.search",
                                f"kurs {fmt_course(c)}", {"course": c}))
        return out

    # --- löpande -----------------------------------------------------------------
    # --- pågående uppdrag (tasks.py) --------------------------------------------------
    @property
    def goal(self) -> str | None:
        """Styruppdragets namn: follow, attack, wait, fairway, station eller circle."""
        return self.steer.goal if self.steer is not None else None

    @property
    def attack_eta_t(self) -> int | None:
        """Beräknad ankomst till skjutläget, medan vi anfaller."""
        return self.steer.eta_t if isinstance(self.steer, Attack) else None

    def _steer_step(self, kind: type[Steering]) -> bool:
        """Ett steg i styruppdraget om det är av slaget `kind` och det är dags.
        Sant om det var dags (då görs inte det som annars görs på samma takt)."""
        task = self.steer
        if not isinstance(task, kind) or self.now % task.STEP_S:
            return False
        task.step(self)
        return True

    @property
    def fix_done_t(self) -> int | None:
        """När fixen i periskopet eller från bryggan är klar, om en pågår."""
        t = self.tasks.get("fix")
        return t.done_t if t is not None else None

    def _run_task(self, name: str) -> None:
        """Ett steg i uppdraget, eller avbrott. Uppdraget tas bort innan det talar."""
        task = self.tasks.pop(name, None)
        if task is None:
            return
        if (why := task.abort(self)) is not None:
            if why[0]:
                self.say(why[0], why[1] or None)
            return
        if not task.step(self):
            self.tasks.setdefault(name, task)

    def _apply_fix(self, x: float, y: float, sigma: float) -> None:
        """Besticket flyttas till fixen: nytt spår på kortet, fixen noteras, ny σ. Restfelet
        är en mätning av strömmen (current.py)."""
        self._current_measure(x, y, sigma)
        self.dr_track[-1].append((self.est_x, self.est_y))
        self.dr_track.append([(x, y)])
        self.fixes.append((x, y, self.now))
        self.est_x, self.est_y = x, y
        self.last_fix_t = self.now
        self.fix_sigma = sigma

    def update(self) -> None:
        self._current_age()
        self._dead_reckon()
        if (self.game.start_clock + self.now) % DR_TICK_S == 0:
            self.dr_ticks.append((self.now, self.est_x, self.est_y))
        self._steer_step(Follow)
        if not self._steer_step(Attack) and self.now % ATTACK_STEP_S == 0:
            self._convoy_watch()
            self._harbor_watch()
        self._steer_step(Wait)
        if not self._steer_step(Fairway) and self.now % SHOAL_CHECK_S == 0:
            self._fairway_watch()
        self._log_depth()
        if self.now % DR_TRACK_INTERVAL_S == 0:
            self.dr_track[-1].append((self.est_x, self.est_y))
        self._sound_ice()
        self._run_task("bfix")
        self._settle_watch()
        self._shoal_watch()
        self._steer_to_opening()
        self._steer_step(StationSteer)
        self._ice_advice()
        s = self.ship
        changing = s.changing()
        for what in list(self._pending):
            if what not in changing:
                self._pending.discard(what)
                value = {"course": s.course, "speed": s.speed, "depth": s.depth}[what]
                self.say(f"nav.{what}.done", {what: value}, kind="done")

        fixing = "fix" in self.tasks
        self._run_task("fix")
        if not fixing and self.now - self.last_fix_t >= BRIDGE_FIX_EVERY_S and self.now % 10 == 0 \
                and self._bridge_bearings():
            self._start_fix(quiet=True)       # navigatören pejlar landmärken från bryggan

        self._run_task("starfix")
        self._star_watch()
        sigma = self.uncertainty()
        if s.depth <= PERISCOPE_DEPTH and sigma > 0.8 and "fix" not in self.tasks \
                and s.speed <= 7 and "depth" not in changing:
            self.suggest("fix_now", "nav.suggest.fix_now", {"sigma": sigma}, order="fix",
                         cooldown=900)
        elif sigma > 1.0 and s.depth > PERISCOPE_DEPTH and self.icemap.soundings:
            o = self.best_opening() if self.under_ice() else None
            if o is not None and self.vak is None and \
                    self.opening_data(o)["range"] <= FIX_VAK_MAX_M:
                self.suggest("fix_vak", "nav.suggest.fix_vak", {"sigma": sigma, **self.opening_data(o)},
                             order="vak", cooldown=1800, quality=o.quality(self.now))
            elif self.under_ice() and self._bfix_worthwhile():
                self.suggest("bfix", "nav.suggest.bfix", {"sigma": sigma}, order="bottenfix",
                             cooldown=1800)
        elif sigma > 1.0 and s.depth > PERISCOPE_DEPTH and \
                (self.under_ice() or self.game.knowledge.threat_held()) and self._bfix_worthwhile():
            self.suggest("bfix", "nav.suggest.bfix", {"sigma": sigma}, order="bottenfix",
                         cooldown=1800)
        elif sigma > 1.0 and s.depth > PERISCOPE_DEPTH:
            self.suggest("fix", "nav.suggest.fix", {"sigma": sigma}, order="periskopdjup",
                         cooldown=1800)
        size = self.area_nm
        if self.game.escape_nm is not None:
            self._escape_watch()
        elif not (0.5 <= self.est_x <= size - 0.5 and 0.5 <= self.est_y <= size - 0.5):
            c = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            self.suggest("area", "nav.suggest.area", {"course": c, "area": self.game.area_name},
                         order=f"kurs {fmt_course(c)}", cooldown=900)
        if s.depth > TEST_DEPTH + 5:
            self.suggest("test_depth", "nav.suggest.test_depth", {"depth": s.depth},
                         order="djup 280", cooldown=300)
