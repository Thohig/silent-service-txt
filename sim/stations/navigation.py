"""Navigation: kurs, fart, djup, bestick (dödräkning med drift), fix och ekolod.

Under is lodar det uppåtriktade isekolodet isen var femte sekund
(IceSounded, med beräknad position). Navigatören läser iskartan i
kunskapen, varnar för kölar och tjock is, och kan på order ("vak") styra
ubåten tillbaka till en loggad öppning och stoppa under den.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .. import acoustics, phrases
from ..chart import LAYER_CONTOUR, LAYER_ICE, LAYER_OWN, Mark, Note, Ray, Ring, Track
from ..profile import BottomSounding, ChartBottom, DepthTrace, IceSounding, Level
from ..seabed import contours
from ..crew import Role
from ..entities import Transient
from ..events import IceSounded, OpeningNotFound
from ..fmt import clock, fmt_course, kn, nm
from ..geo import angle_diff, bearing_to, distance, norm360, velocity
from ..ice import SAIL_TOP_M, masts_clear
from ..icemap import (MIN_SURFACE_LEN_M, OPEN_M, IceMap, IceSoundingObs, Opening,
                      describe_opening, round_m, thickness_words)
from ..orders import NUM, CommandSpec, Order, Unknown, num
from ..ownship import ANTENNA_DEPTH, CRUSH_DEPTH, PERISCOPE_DEPTH, TEST_DEPTH
from .base import Proposal, Station

FIX_TIME_S = 120
IDLE_FIX_SIGMA_NM = 0.5     # vid tystnad: föreslå fix redan vid denna osäkerhet
SEARCH_LEG_S = 1800         # utan kontakt: nytt sökben efter så här lång rak kurs
DR_GROWTH_NM_PER_H = 0.5
SOUNDER_INTERVAL_S = 5      # isekolodet lodar så här ofta
SAFE_ICE_DEPTH = 60         # under isen: djupare än de djupaste kölarna (≤ 45 m)
VAK_SPEED = 3.0             # fart mot en öppning
VAK_TIMEOUT_S = 1800
VAK_RUN_OUT_M = 250         # vaken bakom och närmare: gå ut så här långt innan vi vänder
DECEL_M_PER_S2 = 0.05 * 1852 / 3600
ICE_FIX_SIGMA_NM = 1.0      # under isen: stoppa för fix först vid denna osäkerhet
FIX_VAK_MAX_M = 1500        # gå inte längre än så för en fix
VAK_FAST_SPEED = 5.0        # långt till öppningen: gå fortare, sakta in sista biten
VAK_SLOW_M = 500
REPORT_OPENING_M = 60       # kortare öppningar nämns inte när vi passerar dem
STATION_NAME = "Nord-7"
STATION_ARRIVE_NM = 0.3     # framme vid huvudstabens position (plus dess osäkerhet)
STATION_NEAR_NM = 1.2       # så nära: ett stopp i öppet vatten är värt det
STATION_OVERHEAD_SE = 15.0  # generatorn så stark: vi är inom några kabellängder
STATION_SEARCH_R_NM = 0.3   # sökspiral runt stationen efter öppet vatten: startradie
STATION_SEARCH_GROW_NM_PER_H = 0.3
STATION_SEARCH_MAX_NM = 1.2
STATION_SEARCH_SPEED = 4.0
DR_TRACK_INTERVAL_S = 60    # navigatören prickar in besticket på kortet så här ofta
OWN_VECTOR_S = 360          # egen fartvektor på kortet: sex minuters gång
DEPTH_LOG_INTERVAL_S = 10   # djupprofilen: djupmätaren noteras så här ofta
PROFILE_KEEP_S = 3 * 3600   # så långt bakåt minns profilen
CONTOUR_MARGIN_NM = 4.0     # djupkurvor så här långt utanför kvadraten
CONTOUR_LABEL_SPOTS = ((5, 5), (15, 5), (5, 15), (15, 15), (10, 10))   # andelar av kvadraten ×20


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


@dataclass(frozen=True)
class IceReport(Order):
    pass


@dataclass(frozen=True)
class GoToOpening(Order):
    pass


@dataclass(frozen=True)
class GoToStation(Order):
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
    + (" Det är under provdjup, kapten." if d.get("below_test") else "")
    + (f" Det är is ovanför, kapten, vi kommer inte högre än cirka {d['ice_ceiling']:.0f} meter."
       if d.get("ice_ceiling") else
       " Det är is ovanför, kapten, masterna kommer inte upp här." if d.get("ice_masts") else ""),
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
    "nav.ice.report": lambda d: _ice_report(d),
    "nav.ice.passed": lambda d: f"Isekolod: vi passerade {d['kind']}, cirka {d['length']} meter. "
    f"Loggat som öppning {d['no']}.",
    "nav.suggest.keel": lambda d: f"Kapten, navigatören. Vi går grunt under isen i {kn(d['speed'])} "
    f"knop. Kölarna kan nå 40–45 meter. Föreslår djup {d['depth']}.",
    "nav.suggest.ice_closing": lambda d: "Kapten! Isekolodet visar tjock is ovanför, isen driver "
    f"in över oss. Föreslår djup {d['depth']}.",
    "nav.suggest.fix_vak": lambda d: f"Kapten, navigatören. Bestickets osäkerhet är {nm(d['sigma'])} "
    f"sjömil och det är is ovanför. " + _opening_words(d) + " Föreslår att vi går dit för en fix.",
    "nav.vak.none": lambda d: "Kapten, vi har ingen öppning i isen loggad som vi kan hitta igen. "
    "Vi får leta: isekolodet säger till när vi passerar en.",
    "nav.vak.ack": lambda d: f"Går till öppning {d['no']}, bäring {fmt_course(d['bearing'])}, cirka "
    f"{d['range']} meter. Fart {kn(d['speed'])} knop" + (f", djup {d['depth']}" if d.get("depth") else "")
    + ".",
    "nav.vak.here": lambda d: f"Vi ligger under öppningen nu, {d['kind']}. Stoppar.",
    "nav.suggest.up": lambda d: f"Kapten, vi står stilla under öppningen, {d['kind']} ovanför. "
    + ("Vi är vid Nord-7. Föreslår ytläge." if d.get("station") else
       "Föreslår periskopdjup." if d["open"] else "Föreslår ytläge, vi bryter igenom nyisen."),
    "nav.vak.missed": lambda d: "Kapten, isekolodet visar tjock is här. Öppningen har drivit "
    "iväg eller så missade vi den.",
    "nav.vak.next": lambda d: "Kapten, navigatören. " + _opening_words(d) + " Föreslår att vi går dit.",
    "nav.vak.too_narrow": lambda d: f"Kapten, vi står under nyisen, men råken är bara cirka "
    f"{d['length']} meter. För smal för att bryta igenom med hela skrovet. Föreslår att vi söker "
    f"vidare, fart 5 på {d['depth']} meter.",
    "nav.suggest.resume": lambda d: "Kapten, navigatören. Vi ligger stilla under tjock is. Föreslår "
    f"att vi söker vidare efter öppet vatten, fart 5 på {d['depth']} meter.",
    "nav.station.wp": lambda d: f"Kurs {fmt_course(d['course'])} mot {d['name']}, cirka "
    f"{nm(d['range'])} sjömil enligt huvudstabens position, osäkerhet {nm(d['sigma'])} sjömil.",
    "nav.station.sonar": lambda d: f"Styr på sonarbäringen mot {d['name']} ({d['designation']}), "
    f"kurs {fmt_course(d['course'])}.",
    "nav.station.none": lambda d: "Kapten, vi har ingen position på drivstationen ännu. Huvudstaben "
    "kan ge oss en vid sambandstillfället.",
    "nav.station.arrived": lambda d: f"Kapten, vi är vid huvudstabens position för {d['name']}. "
    f"Den kan ha drivit, osäkerheten är {nm(d['sigma'])} sjömil. Föreslår fart 3 och smygmotor, "
    "så att sonaren kan lyssna efter generatorn.",
    "nav.suggest.station_stop": lambda d: f"Kapten, navigatören. {d['kind'].capitalize()} ovanför oss "
    f"och vi bör vara nära {d['name']}. Föreslår att vi stoppar här.",
    "nav.suggest.station_go": lambda d: f"Kapten, navigatören. Vi har en position på {d['name']}, "
    f"kurs {fmt_course(d['course'])}, cirka {nm(d['range'])} sjömil. Föreslår att vi går dit.",
    "nav.suggest.station_continue": lambda d: f"Kapten, navigatören. Besticket är rättat. Föreslår "
    f"att vi fortsätter mot {d['name']}, fart 5 på {d['depth']} meter.",
    "nav.station.circle": lambda d: f"Kapten, generatorn på {d['name']} hörs mycket starkt, vi är "
    f"nästan under stationen. Går i en vidgande spiral runt den, från cirka {d['radius']} meter, "
    "och letar öppet vatten med isekolodet.",
    "nav.suggest.bumped": lambda d: "Kapten, vi skrapar mot isen i fart! Föreslår djup "
    f"{d['depth']} genast.",
    "nav.vak.narrow_station": lambda d: f"Kapten, öppet vatten ovanför, men råken är bara cirka "
    f"{d['length']} meter, för smal för ytläge. Föreslår att vi letar vidare runt {d['name']}, "
    f"fart 4 på {d['depth']} meter.",
    "nav.vak.overshot": lambda d: "Vi gled förbi öppningen när vi stoppade. Vänder tillbaka.",
    "nav.vak.search": lambda d: "Kapten, navigatören. Ingen annan öppning loggad. Föreslår att vi "
    f"fortsätter söka, fart 5 på {d['depth']} meter.",
    "nav.suggest.stop_here": lambda d: f"Kapten, navigatören. {d['kind'].capitalize()} ovanför oss nu. "
    f"Bestickets osäkerhet är {nm(d['sigma'])} sjömil. Föreslår att vi stoppar här för en fix.",
    "nav.vak.timeout": lambda d: "Kapten, vi hittar inte tillbaka till öppningen. Avbryter.",
}


def _opening_words(d: dict) -> str:
    return (f"Öppning {d['no']} ligger i bäring {fmt_course(d['bearing'])}, cirka {d['range']} "
            f"meter, {d['length']} meter lång, {d['kind']}.")


def _ice_report(d: dict) -> str:
    if not d.get("sounded"):
        return "Isekolod: ingen is ovanför."
    if d["thickness"] < OPEN_M:
        txt = "Isekolod: öppet vatten ovanför."
    else:
        txt = (f"Isekolod: {thickness_words(d['thickness']) if d['thickness'] <= 1.0 else 'tjock is, cirka ' + nm(d['thickness']) + ' meter'}"
               f" ovanför, undersidan på cirka {nm(d['draft'])} meter.")
    if d.get("keel"):
        txt += f" Djupaste köl senaste tio minuterna cirka {d['keel']:.0f} meter."
    if d.get("opening"):
        txt += " " + _opening_words(d["opening"])
    else:
        txt += " Ingen användbar öppning loggad."
    return txt
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
        CommandSpec(r"isekolod|isläge|islage", lambda m: IceReport(), "isekolod"),
        CommandSpec(r"vak|gå till vaken|ga till vaken|öppning|oppning|till öppningen",
                    lambda m: GoToOpening(), "vak"),
        CommandSpec(r"(?:gå till |ga till |kurs mot |mot )?(?:drivstationen|stationen|nord-?7)",
                    lambda m: GoToStation(), "drivstationen"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self._pending: set[str] = set()
        s = self.ship
        self.est_x, self.est_y = s.x, s.y
        # besticket på kortet: ett spår per fix, och fixarna (x, y, tid)
        self.dr_track: list[list[tuple[float, float]]] = [[(s.x, s.y)]]
        self.fixes: list[tuple[float, float, int]] = []
        rng = game.rng
        skill = self.member.effective_skill()
        self.gyro_err = rng.gauss(0, 0.3)
        self.log_bias = rng.gauss(0, 0.01 + 0.02 * (1 - skill))
        self.last_fix_t = 0
        self.course_set_t = 0
        self.fix_done_t: int | None = None
        self._next_sound = 0
        self.vak: Opening | None = None
        self._vak_t = 0
        self._vak_stopping = False
        self._vak_here = False
        self._prev_usable = False
        self.goal: str | None = None         # "station" mot drivstationen, "circle" söker runt den
        self._circle_c: tuple[float, float] | None = None
        self._circle_t = 0
        self._touching = False
        self._goal_src = ""
        # djupprofilen: djupmätaren (t, djup) och ekolodets bottenlodningar
        self.depth_log: list[tuple[int, float]] = [(0, s.depth)]
        self.bottom_soundings: list[BottomSounding] = []
        cd = self.chart_depth_at(s.x, s.y)
        self.chart_depth_log: list[tuple[int, float]] = [] if cd is None else [(0, round(cd))]
        self._contour_items: list | None = None

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
        for b in reversed(self.bottom_soundings):      # nyaste först: dess etikett vinner
            if b.x is not None:
                items.append(Mark(b.x, b.y, "∙", "sounding", f"{b.depth:.0f}".replace(",", " "),
                                  layer=LAYER_ICE))
        for x, y, _ in self.fixes:
            items.append(Mark(x, y, "+", "fix"))
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

    def _contours(self) -> list:
        """Sjökortets djupkurvor, beräknade en gång ur det gamla kortet."""
        if self._contour_items is not None:
            return self._contour_items
        items: list = []
        chart = self.game.knowledge.bathymetry
        if chart is not None:
            size, m = self.game.world.size_nm, CONTOUR_MARGIN_NM
            for level, segs in contours(chart, -m, -m, size + m, size + m).items():
                items.extend(Track(seg, "contour", LAYER_CONTOUR, None) for seg in segs)
                labelled: set[tuple[int, int]] = set()
                for fx, fy in CONTOUR_LABEL_SPOTS:
                    px, py = fx * size / 20, fy * size / 20
                    (ax, ay), _ = min(segs, key=lambda sg: (sg[0][0] - px) ** 2 + (sg[0][1] - py) ** 2)
                    key = (round(ax / 3), round(ay / 3))
                    if (ax - px) ** 2 + (ay - py) ** 2 < 9 and key not in labelled:
                        labelled.add(key)
                        items.append(Mark(ax, ay, "╴", "contour_label", f"{level}",
                                          layer=LAYER_CONTOUR + 0.1))
        self._contour_items = items
        return items

    def chart_depth_at(self, x: float, y: float) -> float | None:
        """Sjökortets djup på en (beräknad) plats, om kortet har djupkurvor."""
        chart = self.game.knowledge.bathymetry
        return None if chart is None else chart.depth_at(x, y)

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

    def _log_depth(self) -> None:
        if self.now % DEPTH_LOG_INTERVAL_S:
            return
        self.depth_log.append((self.now, round(self.ship.depth, 1)))
        cd = self.chart_depth_at(self.est_x, self.est_y)
        if cd is not None:
            self.chart_depth_log.append((self.now, round(cd)))
        cutoff = self.now - PROFILE_KEEP_S
        if self.depth_log[0][0] < cutoff:
            self.depth_log = [p for p in self.depth_log if p[0] >= cutoff]
            self.chart_depth_log = [p for p in self.chart_depth_log if p[0] >= cutoff]
            self.bottom_soundings = [b for b in self.bottom_soundings if b.t >= cutoff]

    @property
    def icemap(self) -> IceMap:
        return self.game.knowledge.ice

    def under_ice(self) -> bool:
        return self.icemap.under_ice(self.now)

    def best_opening(self) -> Opening | None:
        return self.icemap.best(self.now, self.est_x, self.est_y)

    def opening_now(self) -> Opening | None:
        """Ligger vi under en öppning just nu, i fart, utan att redan vara på väg dit?"""
        if self.vak is not None or self.ship.speed < 0.5:
            return None
        latest = self.icemap.latest(self.now)
        if latest is None or not latest.usable:
            return None
        cur = self.icemap.current
        # öppet vatten räcker för masterna; nyis måste vara lång nog att bryta igenom
        if cur is None or not (cur.open or cur.length_m >= MIN_SURFACE_LEN_M):
            return None
        return cur

    def opening_data(self, o: Opening) -> dict:
        return describe_opening(o, self.now, self.est_x, self.est_y)

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
                self.vak = None
                self.goal = None
                self.course_set_t = self.now
                s.order_course(c)
                self._ack("course", {"course": c}, s.course == s.ordered_course)
            case SetSpeed(speed=v):
                self.vak = None
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
                data = {"depth": d, "below_test": d > TEST_DEPTH}
                latest = self.icemap.latest(self.now)
                if latest is not None and not latest.usable and d < latest.draft + SAIL_TOP_M:
                    data["ice_ceiling"] = latest.draft + SAIL_TOP_M
                elif latest is not None and not latest.open and d <= ANTENNA_DEPTH:
                    data["ice_masts"] = True
                self._ack("depth", data, s.depth == s.ordered_depth)
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
                bottom = world.env.bottom_at(s.x, s.y)
                depth = round(bottom - s.depth + self.game.rng.gauss(0, 2 + bottom * 0.005), -1)
                self.bottom_soundings.append(BottomSounding(self.now, s.depth + depth,
                                                            self.est_x, self.est_y))
                self.say("nav.echo", {"under_keel": depth})
            case IceReport():
                self._ice_report()
            case GoToOpening():
                self._go_to_opening()
            case GoToStation():
                self._go_to_station()

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
        elif not masts_clear(self.game.world):
            reason = "det är is ovanför, periskopet kommer inte upp"
        if reason:
            self.say("nav.fix.refused", {"reason": reason})
            return
        own.sys.periscope_until = max(own.sys.periscope_until, self.now + FIX_TIME_S)
        self.fix_done_t = self.now + FIX_TIME_S
        self.say("nav.fix.start", kind="ack")

    # --- isen -----------------------------------------------------------------------
    def _sound_ice(self) -> None:
        """Isekolodet: en sensor, läser isen rakt ovanför och publicerar lodningen."""
        ice = self.game.world.env.ice
        if ice is None or self.now < self._next_sound:
            return
        self._next_sound = self.now + SOUNDER_INTERVAL_S
        s, rng = self.ship, self.game.rng
        skill = self.member.effective_skill()
        t_true = ice.thickness_at(s.x, s.y)
        if t_true < OPEN_M:
            t, d = 0.0, 0.0
        else:
            t = max(0.1, t_true + rng.gauss(0, 0.1 + 0.15 * (1 - skill)))
            d = max(0.8 * t, ice.draft_at(s.x, s.y) + rng.gauss(0, 0.5))
        before = self.icemap.current
        obs = IceSoundingObs(self.now, self.est_x, self.est_y, round(t, 2), round(d, 1))
        self.game.bus.publish(IceSounded(self.now, obs))
        closed = before if (before is not None and self.icemap.current is None) else None
        if closed is not None and closed.length_m >= REPORT_OPENING_M and self.vak is None:
            self.say("nav.ice.passed", self.opening_data(closed), quality=closed.quality(self.now))
        # isen driver in över oss på grunt vatten
        if self._prev_usable and not obs.usable and s.depth <= ANTENNA_DEPTH + 2:
            self.suggest("ice_closing", "nav.suggest.ice_closing", {"depth": SAFE_ICE_DEPTH},
                         order=f"djup {SAFE_ICE_DEPTH}", cooldown=120, alarm=True)
        self._prev_usable = obs.usable

    def _ice_report(self) -> None:
        latest = self.icemap.latest(self.now)
        if latest is None:
            self.say("nav.ice.report", {"sounded": False})
            return
        o = self.best_opening()
        self.say("nav.ice.report", {
            "sounded": True, "thickness": latest.thickness, "draft": latest.draft,
            "keel": self.icemap.deepest_keel(self.now) if self.under_ice() else 0.0,
            "opening": self.opening_data(o) if o else None},
            quality=o.quality(self.now) if o else None)

    def _go_to_opening(self) -> None:
        s = self.ship
        cur = self.icemap.current
        if cur is not None and self.icemap.latest(self.now) is not None:
            self.vak, self._vak_t, self._vak_stopping = cur, self.now, True
            self._vak_here = True
            s.order_speed(0)
            self.say("nav.vak.here", {"kind": thickness_words(cur.thickest)}, kind="ack")
            return
        o = self.best_opening()
        if o is None:
            self.say("nav.vak.none")
            return
        self._steer_for(o)

    def _steer_for(self, o: Opening) -> None:
        s = self.ship
        self.vak, self._vak_t, self._vak_stopping, self._vak_here = o, self.now, False, False
        d = self.opening_data(o)
        s.order_course(d["bearing"])
        fast = VAK_FAST_SPEED if d["range"] > VAK_SLOW_M else VAK_SPEED
        speed = min(fast, self.own.max_speed())
        s.order_speed(speed)
        depth = None
        if s.ordered_depth > SAFE_ICE_DEPTH:
            depth = SAFE_ICE_DEPTH
            s.order_depth(depth)
        self.say("nav.vak.ack", {**d, "speed": speed, "depth": depth}, kind="ack",
                 quality=o.quality(self.now))

    def _steer_to_opening(self) -> None:
        o, s = self.vak, self.ship
        if o is None:
            return
        if self.now - self._vak_t > VAK_TIMEOUT_S:
            self.vak = None
            s.order_speed(VAK_SPEED)
            self.say("nav.vak.timeout")
            return
        if not self._vak_stopping:
            course, rng_m = IceMap.course_and_range_m(self.est_x, self.est_y, o)
            off = abs(angle_diff(course, s.course))
            v = s.speed * 1852 / 3600
            stop_m = v * v / (2 * DECEL_M_PER_S2) + 10
            if off > 90 and rng_m < VAK_RUN_OUT_M:
                return                  # vaken ligger bakom: gå rakt ut, vänd sedan
            if rng_m <= VAK_SLOW_M and s.ordered_speed > VAK_SPEED:
                s.order_speed(VAK_SPEED)
            over = self.icemap.current is not None and rng_m < 150 and off < 90
            if (rng_m <= stop_m and off < 45) or over:
                s.order_speed(0)
                self._vak_stopping = True
            else:
                s.order_course(course)
            return
        if s.speed > 0.2:
            return
        # stilla: vad säger isekolodet?
        self.vak, self._vak_stopping = None, False
        latest = self.icemap.latest(self.now)
        if latest is not None and latest.open:
            near = self.near_station()
            if near and o.length_m < MIN_SURFACE_LEN_M:
                # masterna kommer upp, men skrovet ryms inte: leta vidare runt stationen
                self.suggest("vak_narrow_station", "nav.vak.narrow_station",
                             {"length": round_m(o.length_m), "name": STATION_NAME,
                              "depth": SAFE_ICE_DEPTH},
                             order=f"fart 4, djup {SAFE_ICE_DEPTH}", cooldown=0)
                return
            self.suggest("vak_up", "nav.suggest.up",
                         {"kind": "öppet vatten", "open": True, "station": near},
                         order="ytläge" if near else "periskopdjup", cooldown=0)
            return
        if latest is not None and latest.usable:
            if o.length_m >= MIN_SURFACE_LEN_M:
                self.suggest("vak_up", "nav.suggest.up",
                             {"kind": thickness_words(latest.thickness), "open": False},
                             order="ytläge", cooldown=0)
            else:
                # bara tornet ryms: för- och akterskeppet skulle stöta i tjock is
                self.game.bus.publish(OpeningNotFound(self.now, o.no))
                self.suggest("vak_narrow", "nav.vak.too_narrow",
                             {"length": round_m(o.length_m), "depth": SAFE_ICE_DEPTH},
                             order=f"fart 5, djup {SAFE_ICE_DEPTH}", cooldown=0)
            return
        if self._vak_here:
            # vi stoppade när vi var under öppningen men gled förbi: backa tillbaka
            self.say("nav.vak.overshot")
            self._steer_for(o)
            return
        self.game.bus.publish(OpeningNotFound(self.now, o.no))
        self.say("nav.vak.missed")
        nxt = self.best_opening()
        if nxt is not None:
            self.suggest("vak_next", "nav.vak.next", self.opening_data(nxt), order="vak",
                         cooldown=0, quality=nxt.quality(self.now))
        else:
            self.suggest("vak_search", "nav.vak.search", {"depth": SAFE_ICE_DEPTH},
                         order=f"fart 5, djup {SAFE_ICE_DEPTH}", cooldown=0)

    # --- drivstationen ---------------------------------------------------------------
    def station_aim(self) -> tuple[str, float, float | None, dict] | None:
        """Vart vi ska styra mot stationen: ("sonar", kurs, None, data) eller
        ("wp", kurs, avstånd nm, data). Ur kunskapen, aldrig sanningen."""
        k = self.game.knowledge
        tr = k.station_track()
        if tr is not None and tr.held and tr.last_bearing is not None:
            return "sonar", tr.last_bearing, None, {"designation": tr.designation}
        wp = k.waypoints.get(STATION_NAME)
        if wp is None:
            return None
        c = bearing_to(self.est_x, self.est_y, wp.x, wp.y)
        r = distance(self.est_x, self.est_y, wp.x, wp.y)
        return "wp", c, r, {"sigma": wp.sigma(self.now)}

    def near_station(self) -> bool:
        if self.goal == "circle":
            return True
        k = self.game.knowledge
        tr = k.station_track()
        if tr is not None and tr.held and tr.observations and tr.observations[-1].se > 6:
            return True
        aim = self.station_aim()
        return aim is not None and aim[0] == "wp" and aim[2] < STATION_NEAR_NM \
            and aim[3]["sigma"] < 1.0

    def _radio_waiting(self) -> bool:
        """Väntar radion på ett sambandstillfälle som snart börjar eller pågår?"""
        from .radio import RadioStation
        try:
            return self.game.station(RadioStation).window_pending() is not None
        except KeyError:
            return False

    def surface_ok(self) -> bool:
        """Ryms hela skrovet i öppningen vi ligger i, enligt isekolodet?"""
        latest = self.icemap.latest(self.now)
        cur = self.icemap.current
        return latest is not None and latest.usable and cur is not None \
            and cur.length_m >= MIN_SURFACE_LEN_M

    def _go_to_station(self) -> None:
        aim = self.station_aim()
        if aim is None:
            self.say("nav.station.none")
            return
        self.vak = None
        self.goal, self._goal_src = "station", aim[0]
        src, course, rng, d = aim
        self.ship.order_course(course)
        if src == "sonar":
            self.say("nav.station.sonar", {"name": STATION_NAME, "course": course, **d}, kind="ack")
        else:
            self.say("nav.station.wp", {"name": STATION_NAME, "course": course, "range": rng, **d},
                     kind="ack")

    def _station_overhead(self) -> tuple[float, float] | None:
        """Hörs generatorn så starkt att vi är nära? Då: skattad stationsposition."""
        tr = self.game.knowledge.station_track()
        if tr is None or not tr.held or not tr.observations:
            return None
        recent = [o for o in tr.observations[-3:] if self.now - o.t <= 30]
        if not recent or min(o.se for o in recent) < STATION_OVERHEAD_SE:
            return None
        b = math.radians(recent[-1].bearing)
        d = STATION_SEARCH_R_NM * 0.6
        return self.est_x + d * math.sin(b), self.est_y + d * math.cos(b)

    def _steer_circle(self) -> None:
        cx, cy = self._circle_c
        s = self.ship
        r = distance(cx, cy, self.est_x, self.est_y)
        out = bearing_to(cx, cy, self.est_x, self.est_y)
        # medurs runt mitten i en växande spiral; styr in eller ut mot banan
        want = min(STATION_SEARCH_MAX_NM, STATION_SEARCH_R_NM
                   + STATION_SEARCH_GROW_NM_PER_H * (self.now - self._circle_t) / 3600)
        corr = max(-45.0, min(45.0, (r - want) / want * 60.0))
        s.order_course(norm360(out + 90 + corr))

    def _steer_to_station(self) -> None:
        if self.goal not in ("station", "circle") or self.vak is not None:
            return
        if self.goal == "circle":
            self._steer_circle()
            return
        c = self._station_overhead()
        if c is not None:
            self.goal, self._circle_c, self._circle_t = "circle", c, self.now
            s = self.ship
            s.order_speed(min(STATION_SEARCH_SPEED, self.own.max_speed()))
            if s.ordered_depth < SAFE_ICE_DEPTH:
                s.order_depth(SAFE_ICE_DEPTH)
            self.say("nav.station.circle", {"name": STATION_NAME,
                                             "radius": round_m(STATION_SEARCH_R_NM * 1852)})
            self._steer_circle()
            return
        aim = self.station_aim()
        if aim is None:
            self.goal = None
            return
        src, course, rng, d = aim
        if src != self._goal_src and src == "sonar":
            self._goal_src = src
            self.say("nav.station.sonar", {"name": STATION_NAME, "course": course, **d})
        self.ship.order_course(course)
        if src == "wp" and rng < STATION_ARRIVE_NM:
            self.goal = None
            self.suggest("station_arrived", "nav.station.arrived",
                         {"name": STATION_NAME, "sigma": d["sigma"]},
                         order="fart 3, smygmotor", cooldown=0)

    def _ice_advice(self) -> None:
        # stöten känns i hela båten: i fart under isen ska vi ned
        touching = self.own.sys.ice_contact
        if touching and not self._touching and self.ship.speed > 1.0:
            self.suggest("bumped", "nav.suggest.bumped", {"depth": SAFE_ICE_DEPTH},
                         order=f"djup {SAFE_ICE_DEPTH}", cooldown=60, alarm=True)
        self._touching = touching
        if self.opening_now() is not None and self.near_station():
            latest = self.icemap.latest(self.now)
            self.suggest("station_stop", "nav.suggest.station_stop",
                         {"kind": thickness_words(latest.thickness), "name": STATION_NAME},
                         order="vak", cooldown=300)
        sigma = self.uncertainty()
        if sigma > ICE_FIX_SIGMA_NM and self.opening_now() is not None and self.fix_done_t is None:
            latest = self.icemap.latest(self.now)
            self.suggest("stop_here", "nav.suggest.stop_here",
                         {"kind": thickness_words(latest.thickness), "sigma": sigma},
                         order="vak", cooldown=600)
        wp = self.game.knowledge.waypoints.get(STATION_NAME)
        if wp is not None and self.goal is None and self.vak is None and \
                self.ship.depth > PERISCOPE_DEPTH + 1:
            aim = self.station_aim()
            if aim is not None and aim[0] == "wp" and aim[2] > 2 * STATION_ARRIVE_NM:
                self.suggest("station_go", "nav.suggest.station_go",
                             {"name": STATION_NAME, "course": aim[1], "range": aim[2]},
                             order="drivstationen", cooldown=900)
        s = self.ship
        if self.goal == "station" and s.speed < 0.3 and s.ordered_speed == 0 and self.vak is None \
                and not self.under_ice() and self.icemap.soundings and self.fix_done_t is None \
                and self.uncertainty() < ICE_FIX_SIGMA_NM and not self._radio_waiting() \
                and self.own.sys.smoke < 0.15 and not self.own.sys.ventilating \
                and not self.near_station() and not self.game.queue.has_kind("suggest"):
            self.suggest("station_continue", "nav.suggest.station_continue",
                         {"name": STATION_NAME, "depth": SAFE_ICE_DEPTH},
                         order=f"fart 5, djup {SAFE_ICE_DEPTH}", cooldown=600)
        if not self.under_ice():
            return
        if s.speed < 0.3 and s.ordered_speed == 0 and self.vak is None \
                and "depth" not in s.changing() and not self.game.queue.has_kind("suggest"):
            # stilla under isen: gå till en känd öppning eller fortsätt söka
            o = self.best_opening()
            d = self.opening_data(o) if o is not None else None
            if d is not None and d["range"] > 150:
                self.suggest("resume_vak", "nav.vak.next", d, order="vak", cooldown=900,
                             quality=o.quality(self.now))
            else:
                self.suggest("resume", "nav.suggest.resume", {"depth": SAFE_ICE_DEPTH},
                             order=f"fart 5, djup {SAFE_ICE_DEPTH}", cooldown=900)
        if s.ordered_depth < SAFE_ICE_DEPTH and s.speed > VAK_SPEED + 0.5 and self.vak is None:
            self.suggest("keel", "nav.suggest.keel", {"speed": s.speed, "depth": SAFE_ICE_DEPTH},
                         order=f"djup {SAFE_ICE_DEPTH}", cooldown=900)

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
        size = self.game.world.size_nm
        if not (0.5 <= self.est_x <= size - 0.5 and 0.5 <= self.est_y <= size - 0.5):
            c = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            out.append(Proposal(3, "idle_area", "nav.suggest.area", f"kurs {fmt_course(c)}",
                                {"course": c, "area": self.game.area_name}, cooldown=900))
        held = self.game.knowledge.threat_held()
        sigma = self.uncertainty()
        if self.icemap.soundings:
            o = self.best_opening() if self.under_ice() else None
            if not held and sigma > ICE_FIX_SIGMA_NM and self.fix_done_t is None and \
                    o is not None and self.vak is None and \
                    self.opening_data(o)["range"] <= FIX_VAK_MAX_M:
                out.append(Proposal(4, "idle_fix_vak", "nav.suggest.fix_vak", "vak",
                                    {"sigma": sigma, **self.opening_data(o)},
                                    quality=o.quality(self.now)))
        elif not held and sigma > IDLE_FIX_SIGMA_NM and self.fix_done_t is None:
            if s.depth <= PERISCOPE_DEPTH and s.speed <= 7:
                out.append(Proposal(4, "idle_fix_now", "nav.suggest.fix_now", "fix",
                                    {"sigma": sigma}, cooldown=900))
            elif s.depth > PERISCOPE_DEPTH:
                out.append(Proposal(4, "idle_fix", "nav.suggest.fix", "periskopdjup",
                                    {"sigma": sigma}))
        if self._quiet_contact_picture() and self.now - self.course_set_t >= SEARCH_LEG_S \
                and self.vak is None and self.goal is None and s.ordered_speed > 0:
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
        self._log_depth()
        if self.now % DR_TRACK_INTERVAL_S == 0:
            self.dr_track[-1].append((self.est_x, self.est_y))
        self._sound_ice()
        self._steer_to_opening()
        self._steer_to_station()
        self._ice_advice()
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
                self.dr_track[-1].append((self.est_x, self.est_y))
                self.dr_track.append([(new_x, new_y)])
                self.fixes.append((new_x, new_y, self.now))
                self.est_x, self.est_y = new_x, new_y
                self.last_fix_t = self.now
                self.say("nav.fix.done", {"error": err, "bearing": b})

        sigma = self.uncertainty()
        if s.depth <= PERISCOPE_DEPTH and sigma > 0.8 and self.fix_done_t is None \
                and s.speed <= 7 and "depth" not in changing:
            self.suggest("fix_now", "nav.suggest.fix_now", {"sigma": sigma}, order="fix",
                         cooldown=900)
        elif sigma > 1.0 and s.depth > PERISCOPE_DEPTH and self.icemap.soundings:
            o = self.best_opening() if self.under_ice() else None
            if o is not None and self.vak is None and \
                    self.opening_data(o)["range"] <= FIX_VAK_MAX_M:
                self.suggest("fix_vak", "nav.suggest.fix_vak", {"sigma": sigma, **self.opening_data(o)},
                             order="vak", cooldown=1800, quality=o.quality(self.now))
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
