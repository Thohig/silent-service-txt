"""Navigation: kurs, fart, djup, bestick (dödräkning med drift), fix och ekolod."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .. import acoustics, phrases
from ..crew import Role
from ..entities import Transient
from ..fmt import clock, fmt_course, kn, nm
from ..geo import angle_diff, bearing_to, distance, norm360, velocity
from ..orders import NUM, CommandSpec, Order, Unknown, num
from ..ownship import ANTENNA_DEPTH, PERISCOPE_DEPTH, TEST_DEPTH
from .base import Proposal, Station

FIX_TIME_S = 120
IDLE_FIX_SIGMA_NM = 0.5     # vid tystnad: föreslå fix redan vid denna osäkerhet
SEARCH_LEG_S = 1800         # utan kontakt: nytt sökben efter så här lång rak kurs
DR_GROWTH_NM_PER_H = 0.5


@dataclass(frozen=True)
class SetCourse(Order):
    course: int
    STANDING = True


@dataclass(frozen=True)
class SetSpeed(Order):
    speed: float
    STANDING = True


@dataclass(frozen=True)
class SetDepth(Order):
    depth: int
    STANDING = True


@dataclass(frozen=True)
class TakeFix(Order):
    pass


@dataclass(frozen=True)
class ReportPosition(Order):
    pass


@dataclass(frozen=True)
class EchoSounder(Order):
    pass


def _course(m: re.Match) -> Order:
    c = num(m[1])
    if not 0 <= c < 360:
        return Unknown("", "kursen måste vara 000–359")
    return SetCourse(int(round(c)) % 360)


PHRASES = {
    "nav.course.ack": lambda d: f"Kurs {fmt_course(d['course'])}, aye."
    + (" Vi ligger på den." if d.get("already") else ""),
    "nav.speed.ack": lambda d: "Stopp i maskin, aye." if d["speed"] == 0
    else f"Fart {kn(d['speed'])} knop, aye.",
    "nav.depth.ack": lambda d: ("Upp till ytan, aye." if d["depth"] == 0 else
                                f"Djup {d['depth']:.0f} meter, aye.")
    + (" Det är under provdjup, kapten." if d.get("below_test") else ""),
    "nav.course.done": lambda d: f"Kapten, kurs {fmt_course(d['course'])} påkommen.",
    "nav.speed.done": lambda d: f"Fart {kn(d['speed'])} knop uppnådd.",
    "nav.depth.done": lambda d: "Vi är i ytläge, kapten." if d["depth"] < 1
    else f"Djup {d['depth']:.0f} meter, kapten.",
    "nav.limit": lambda d: f"Kapten, högsta fart just nu är {kn(d['limit'])} knop."
    if d["what"] == "speed" else f"Kapten, största djup är {d['limit']:.0f} meter.",
    "nav.fix.start": lambda d: "Tar fix i periskopet, cirka två minuter.",
    "nav.fix.refused": lambda d: f"Kapten, {d['reason']}.",
    "nav.fix.aborted": lambda d: "Fixen avbröts, vi lämnade periskopdjup.",
    "nav.fix.done": lambda d: f"Fix tagen. Bestick korrigerat {nm(d['error'])} sjömil "
    f"åt {fmt_course(d['bearing'])}.",
    "nav.position": lambda d: f"Beräknad position {nm(d['x'])} sjömil öst och "
    f"{nm(d['y'])} norr i kvadraten, osäkerhet {nm(d['sigma'])} sjömil. "
    f"Senaste fix {d['last_fix']}.",
    "nav.echo": lambda d: f"Ekolod: {d['under_keel']:,.0f} meter under kölen.".replace(",", " "),
    "nav.suggest.fix": lambda d: f"Kapten, navigatören. Bestickets osäkerhet är "
    f"{nm(d['sigma'])} sjömil. Föreslår fix på periskopdjup.",
    "nav.suggest.fix_now": lambda d: f"Kapten, vi är på periskopdjup. Bestickets osäkerhet är "
    f"{nm(d['sigma'])} sjömil. Föreslår att vi tar en fix nu.",
    "nav.suggest.search": lambda d: "Kapten, navigatören. Inga kontakter på länge. "
    f"Föreslår nytt sökben, kurs {fmt_course(d['course'])}.",
    "nav.suggest.area": lambda d: f"Kapten, vi är på väg ut ur {d.get('area', 'kvadrat 7')}. "
    f"Föreslår kurs {fmt_course(d['course'])}.",
    "nav.suggest.test_depth": lambda d: f"Kapten, vi är på {d['depth']:.0f} meter, under "
    f"provdjup. Föreslår djup 280.",
}
phrases.register(PHRASES)


class NavigationStation(Station):
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
        CommandSpec(r"position|var är vi\??|pos", lambda m: ReportPosition(), "position"),
        CommandSpec(r"ekolod|loda", lambda m: EchoSounder(), "ekolod"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self._pending: set[str] = set()
        s = self.ship
        self.est_x, self.est_y = s.x, s.y
        rng = game.rng
        skill = self.member.effective_skill()
        self.gyro_err = rng.gauss(0, 0.3)
        self.log_bias = rng.gauss(0, 0.01 + 0.02 * (1 - skill))
        self.last_fix_t = 0
        self.course_set_t = 0
        self.fix_done_t: int | None = None

    @property
    def own(self):
        return self.game.world.own

    @property
    def ship(self):
        return self.game.world.own.state

    # --- bestick ---------------------------------------------------------------
    def position_estimate(self) -> tuple[float, float]:
        return self.est_x, self.est_y

    def uncertainty(self) -> float:
        return 0.1 + DR_GROWTH_NM_PER_H * (self.now - self.last_fix_t) / 3600.0

    def _dead_reckon(self) -> None:
        s = self.ship
        vx, vy = velocity(s.course + self.gyro_err, s.speed * (1 + self.log_bias))
        self.est_x += vx
        self.est_y += vy

    # --- order -------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        s = self.ship
        match order:
            case SetCourse(course=c):
                self.course_set_t = self.now
                s.order_course(c)
                self._ack("course", {"course": c}, s.course == s.ordered_course)
            case SetSpeed(speed=v):
                limit = self.own.max_speed()
                if v > limit:
                    self.say("nav.limit", {"what": "speed", "limit": limit})
                    return
                s.order_speed(v)
                self._ack("speed", {"speed": v}, s.speed == s.ordered_speed)
            case SetDepth(depth=d):
                if d > s.max_depth:
                    self.say("nav.limit", {"what": "depth", "limit": s.max_depth})
                    return
                s.order_depth(d)
                self._ack("depth", {"depth": d, "below_test": d > TEST_DEPTH},
                          s.depth == s.ordered_depth)
            case TakeFix():
                self._start_fix()
            case ReportPosition():
                self.say("nav.position", {"x": self.est_x, "y": self.est_y,
                                          "sigma": self.uncertainty(),
                                          "last_fix": self.game.clock_str(self.last_fix_t)})
            case EchoSounder():
                world = self.game.world
                world.emit(Transient("echosounder", s.x, s.y, s.depth,
                                     acoustics.ECHO_SOUNDER_LEVEL, world.own.id, self.now))
                depth = world.env.bottom_depth - s.depth + self.game.rng.gauss(0, 15)
                self.say("nav.echo", {"under_keel": round(depth, -1)})

    def _ack(self, what: str, data: dict, already: bool) -> None:
        self.say(f"nav.{what}.ack", {**data, "already": already}, kind="ack")
        if already:
            self._pending.discard(what)
        else:
            self._pending.add(what)

    def _start_fix(self) -> None:
        own, s = self.own, self.ship
        reason = None
        if s.depth > PERISCOPE_DEPTH:
            reason = "vi måste upp på periskopdjup för en fix"
        elif s.speed > 7:
            reason = "farten är för hög för periskopet"
        elif own.sys.health["periscope"] < 0.3:
            reason = "periskopet är skadat"
        if reason:
            self.say("nav.fix.refused", {"reason": reason})
            return
        own.sys.periscope_until = max(own.sys.periscope_until, self.now + FIX_TIME_S)
        self.fix_done_t = self.now + FIX_TIME_S
        self.say("nav.fix.start", kind="ack")

    # --- initiativ vid tystnad -----------------------------------------------------
    def _quiet_contact_picture(self) -> bool:
        """Ingen kontakt hålls och ingen har hörts på SEARCH_LEG_S sekunder."""
        tracks = self.game.knowledge.tracks.values()
        if any(t.held for t in tracks):
            return False
        last = max((t.observations[-1].t for t in tracks if t.observations), default=-10**9)
        return self.now - last >= SEARCH_LEG_S

    def idle_proposals(self) -> list[Proposal]:
        s = self.ship
        out = []
        if s.depth > TEST_DEPTH + 5:
            out.append(Proposal(1, "idle_test_depth", "nav.suggest.test_depth", "djup 280",
                                {"depth": s.depth}, cooldown=300))
        size = self.game.world.size_nm
        if not (0.5 <= self.est_x <= size - 0.5 and 0.5 <= self.est_y <= size - 0.5):
            c = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            out.append(Proposal(3, "idle_area", "nav.suggest.area", f"kurs {fmt_course(c)}",
                                {"course": c, "area": self.game.area_name}, cooldown=900))
        held = any(t.held for t in self.game.knowledge.tracks.values())
        sigma = self.uncertainty()
        if not held and sigma > IDLE_FIX_SIGMA_NM and self.fix_done_t is None:
            if s.depth <= PERISCOPE_DEPTH and s.speed <= 7:
                out.append(Proposal(4, "idle_fix_now", "nav.suggest.fix_now", "fix",
                                    {"sigma": sigma}, cooldown=900))
            elif s.depth > PERISCOPE_DEPTH:
                out.append(Proposal(4, "idle_fix", "nav.suggest.fix", "periskopdjup",
                                    {"sigma": sigma}))
        if self._quiet_contact_picture() and self.now - self.course_set_t >= SEARCH_LEG_S:
            # gir 90° åt den sida som pekar mest mot kvadratens mitt
            size = self.game.world.size_nm
            to_mid = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            c = min((norm360(s.ordered_course + 90), norm360(s.ordered_course - 90)),
                    key=lambda k: abs(angle_diff(k, to_mid)))
            out.append(Proposal(6, "idle_search", "nav.suggest.search",
                                f"kurs {fmt_course(c)}", {"course": c}))
        return out

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        self._dead_reckon()
        s = self.ship
        changing = s.changing()
        for what in list(self._pending):
            if what not in changing:
                self._pending.discard(what)
                value = {"course": s.course, "speed": s.speed, "depth": s.depth}[what]
                self.say(f"nav.{what}.done", {what: value}, kind="done")

        if self.fix_done_t is not None:
            if s.depth > PERISCOPE_DEPTH + 1:
                self.fix_done_t = None
                self.say("nav.fix.aborted")
            elif self.now >= self.fix_done_t:
                self.fix_done_t = None
                rng = self.game.rng
                new_x, new_y = s.x + rng.gauss(0, 0.08), s.y + rng.gauss(0, 0.08)
                err = distance(self.est_x, self.est_y, new_x, new_y)
                b = bearing_to(self.est_x, self.est_y, new_x, new_y)
                self.est_x, self.est_y = new_x, new_y
                self.last_fix_t = self.now
                self.say("nav.fix.done", {"error": err, "bearing": b})

        sigma = self.uncertainty()
        if s.depth <= PERISCOPE_DEPTH and sigma > 0.8 and self.fix_done_t is None \
                and s.speed <= 7 and "depth" not in changing:
            self.suggest("fix_now", "nav.suggest.fix_now", {"sigma": sigma}, order="fix",
                         cooldown=900)
        elif sigma > 1.0 and s.depth > PERISCOPE_DEPTH:
            self.suggest("fix", "nav.suggest.fix", {"sigma": sigma}, order="periskopdjup",
                         cooldown=1800)
        size = self.game.world.size_nm
        if not (0.5 <= self.est_x <= size - 0.5 and 0.5 <= self.est_y <= size - 0.5):
            c = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            self.suggest("area", "nav.suggest.area", {"course": c, "area": self.game.area_name},
                         order=f"kurs {fmt_course(c)}", cooldown=900)
        if s.depth > TEST_DEPTH + 5:
            self.suggest("test_depth", "nav.suggest.test_depth", {"depth": s.depth},
                         order="djup 280", cooldown=300)
