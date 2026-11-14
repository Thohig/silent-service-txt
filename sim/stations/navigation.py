"""Navigation: kurs, fart, djup, bestick (dödräkning med drift), fix och ekolod.

Under is lodar det uppåtriktade isekolodet isen var femte sekund
(IceSounded, med beräknad position). Navigatören läser iskartan i
kunskapen, varnar för kölar och tjock is, och kan på order ("vak") styra
ubåten tillbaka till en loggad öppning och stoppa under den.
"""
from __future__ import annotations

import math
from collections import deque
import re

import numpy as np
from dataclasses import dataclass

from .. import acoustics, phrases
from ..chart import LAYER_CONTOUR, LAYER_ICE, LAYER_OWN, Mark, Note, Ray, Ring, Track
from ..profile import BottomSounding, ChartBottom, DepthTrace, IceSounding, Level
from ..reports import Quality
from ..seabed import contours, match_soundings
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
from ..systems import DANGER, INFO, OK, WARN, Gauge
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
SHOAL_MARGIN_M = 30         # håll så här långt över botten enligt kortet
SHOAL_LOOK_MIN = 6          # navigatören tittar så många minuters gång framåt
SHOAL_LOOK_MIN_NM = 1.0     # men minst så långt
SHOAL_CHECK_S = 20
SOUNDING_TRUST_S = 600      # en lodning räknas så här länge
BFIX_N = 9                  # fix mot botten: så många lodningar
BFIX_INTERVAL_S = 20        # med så här långt mellan
BFIX_MIN_SPEED = 2.0        # vi måste röra oss över botten
BFIX_FLAT = 0.8             # matchningen smalnar inte av mer än så: botten för flat
BFIX_GAIN = 2.0             # föreslå bara om besticket är så här mycket sämre än kortet
BFIX_RELIEF_M_PER_NM = 150  # föreslå bottenfix bara där kortet visar så här brant botten
PERISCOPE_FIX_SIGMA = 0.1
LAND_MARK_STEP_NM = 0.25   # land på sjökortet: en prick per ruta
LAND_CLEAR_M = 21          # grundare än så framåt: inte ens periskopdjup går, gir i stället
LAND_TURNS = (30, 60, 90, 120, 150, 180)
PATH_STEP_NM = 0.1         # vägsökningens rutnät
EXIT_RECALC_S = 20         # vägen ut räknas om så här ofta
TIDE_TABLE_ERR = 0.3        # tidvattentabellen kan ha så här stort fel (andel av farten)
EXIT_FIRST_SUGGEST_S = 150  # ut ur området: låt sonar och djup komma först
EXIT_THREAT_SECTOR = 40     # en väg ut inom så många grader från en hotkontakt är inte fri
EXIT_THREAT_PENALTY_NM = 4.0
SETTLE_SPEED = 1.0          # fart när vi går ned mot botten
SETTLE_DESCEND_KN = 1.5     # gå ned först när farten är nere i detta
SETTLE_EXTRA_M = 60         # sikta så här långt under kortets botten
SETTLE_SUGGEST_MAX_M = 280  # föreslå att lägga oss på botten bara grundare än så
BOTTOM_WORDS = {"lera": "lerbotten", "sand": "sandbotten", "klippa": "klippbotten"}
CONTOUR_MARGIN_NM = 4.0     # djupkurvor så här långt utanför kvadraten
CONTOUR_LABEL_SPOTS = ((5, 5), (15, 5), (5, 15), (15, 15), (10, 10))   # andelar av kvadraten ×20


@dataclass(frozen=True)
class SteerTo(Order):
    name: str


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


@dataclass(frozen=True)
class SettleOnBottom(Order):
    pass


@dataclass(frozen=True)
class BottomFix(Order):
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
       " Det är is ovanför, kapten, masterna kommer inte upp här." if d.get("ice_masts") else "")
    + (f" Kortet visar botten på cirka {d['shoal']:.0f} meter här, kapten." if d.get("shoal") else ""),
    "nav.settle.ack": lambda d: "Lägger oss på botten, aye. "
    + (f"Ekolodet gav {d['depth']:.0f} meter" if d.get("sounded") else
       f"Kortet visar cirka {d['depth']:.0f} meter")
    + (f", {BOTTOM_WORDS[d['kind']]} enligt kortet" if d.get("kind") else "")
    + ". Sakta i en knop och går ned.",
    "nav.settle.refused": lambda d: f"Kapten, {d['reason']}.",
    "nav.settle.already": lambda d: "Vi ligger redan på botten, kapten.",
    "nav.settle.lift": lambda d: "Vi lättar från botten.",
    "nav.settle.not_reached": lambda d: f"Kapten, vi är på {d['depth']:.0f} meter och har inte "
    "nått botten. Kortet stämmer inte här. Föreslår ekolod.",
    "nav.suggest.settle": lambda d: "Kapten, navigatören. Vi är över grunt vatten, kortet visar "
    f"{BOTTOM_WORDS[d['kind']]} på cirka {d['depth']:.0f} meter. Ligger vi stilla på botten "
    "drunknar vårt eko i bottenekot. Föreslår att vi lägger oss på botten.",
    "nav.bfix.start": lambda d: f"Fix mot botten, aye. Lodar {d['n']} gånger under "
    f"{d['minutes']} minuter. Håll kurs och fart, ekolodet hörs.",
    "nav.bfix.refused": lambda d: f"Kapten, {d['reason']}.",
    "nav.bfix.aborted": lambda d: "Fixen mot botten avbröts, vi har nästan stannat.",
    "nav.bfix.done": lambda d: f"Fix mot botten klar. Lodningarna passar kortet bäst "
    f"{nm(d['error'])} sjömil åt {fmt_course(d['bearing'])}. Bestick korrigerat, osäkerhet "
    f"{nm(d['sigma'])} sjömil.",
    "nav.bfix.line": lambda d: f"Fix mot botten ger en lägeslinje: läget är bestämt i led "
    f"{fmt_course(d['bearing'])}–{fmt_course((d['bearing'] + 180) % 360)} på {nm(d['minor'])} sjömil, "
    f"men inte längs djupkurvorna. Bestick korrigerat {nm(d['error'])} sjömil åt "
    f"{fmt_course(d['bearing_corr'])}, osäkerhet {nm(d['sigma'])} sjömil. En fix där botten "
    "varierar åt flera håll, vid ett berg eller en ränna, ger läget i båda led.",
    "nav.bfix.mismatch": lambda d: "Fix mot botten: lodningarna stämmer inte med kortet här, "
    f"botten är {d['how']} än kortet visar. Kortet saknar något. Besticket oförändrat.",
    "nav.bfix.flat": lambda d: "Fix mot botten: botten är för flat här, lodningarna säger "
    "inget om var vi är. Besticket oförändrat.",
    "nav.bfix.chart": lambda d: f"Fix mot botten: lodningarna passar kortet, men kortet är inte "
    f"bättre än {nm(d['accuracy'])} sjömil. Besticket är lika bra. Oförändrat.",
    "nav.suggest.bfix": lambda d: f"Kapten, navigatören. Bestickets osäkerhet är {nm(d['sigma'])} "
    "sjömil och vi kan inte ta fix i periskopet. Kortet visar brant botten här. Föreslår fix "
    "mot botten, nio lodningar.",
    "nav.suggest.shoal": lambda d: "Kapten, navigatören. "
    + (f"Ekolodet visade {d['shoal']:.0f} meter till botten här" if d.get("sounded") else
       f"Sjökortet visar {d['shoal']:.0f} meter "
       + ("här" if d["dist"] < 0.15 else f"inom {nm(d['dist'])} sjömil framåt"))
    + f". Föreslår djup {d['depth']:.0f}.",
    "nav.steer": lambda d: f"Kurs {fmt_course(d['course'])} mot {d['name']}, "
    f"{nm(d['range'])} sjömil, ± {nm(d['sigma'])}.",
    "nav.steer.none": lambda d: f"Kapten, vi har ingen position för {d['name']}. "
    + (f"Vi känner till: {', '.join(d['known'])}." if d["known"] else ""),
    "nav.suggest.land": lambda d: "Kapten, navigatören! "
    + ("Land" if d["shoal"] <= 0 else f"Bara {d['shoal']:.0f} meter vatten")
    + (" här enligt kortet" if d["dist"] < 0.15 else f" inom {nm(d['dist'])} sjömil framåt")
    + f". Föreslår kurs {fmt_course(d['course'])}.",
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
    "nav.suggest.exit": lambda d: f"Kapten, navigatören. Närmaste väg ut ur {d['area']} "
    + (f"går runt land, {nm(d['dist'])} sjömil. Första biten kurs {fmt_course(d['course'])}"
       if d.get("via") else
       f"är kurs {fmt_course(d['course'])}, {nm(d['dist'])} sjömil")
    + (", bort från kontakterna." if d.get('clear') else ".")
    + f" Föreslår kurs {fmt_course(d['course'])}.",
    "nav.exit.out": lambda d: f"Kapten, enligt besticket är vi ute ur {d['area']}.",
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
        self.fixes: list[tuple[float, float, int]] = []
        rng = game.rng
        skill = self.member.effective_skill()
        self.gyro_err = rng.gauss(0, 0.3)
        self.log_bias = rng.gauss(0, 0.01 + 0.02 * (1 - skill))
        self.last_fix_t = 0
        self.fix_sigma = PERISCOPE_FIX_SIGMA
        self._tide_fix_t, self._tide_sigma = 0, 0.0   # tidvattnets bidrag sedan senaste fix
        self._bfix: list[tuple[float, float, float]] | None = None   # (x, y beräknat, djup)
        self._bfix_next = 0
        self.course_set_t = 0
        self.fix_done_t: int | None = None
        self._next_sound = 0
        self.vak: Opening | None = None
        self._vak_t = 0
        self._vak_stopping = False
        self._vak_here = False
        self._prev_usable = False
        self._told_out = False                # har sagt att vi lämnat området
        self.exit_via: str | None = None      # vägen ut går först runt land
        self._water = None                    # sjökortets vattenrutnät för vägsökning
        self._exit_cache: tuple[int, tuple | None, str | None] | None = None
        self.goal: str | None = None         # "station" mot drivstationen, "circle" söker runt den
        self._circle_c: tuple[float, float] | None = None
        self._circle_t = 0
        self._touching = False
        self._settle_aim = 0.0
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
        return self.fix_sigma + DR_GROWTH_NM_PER_H * (self.now - self.last_fix_t) / 3600.0 \
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
            g("Master", "uppe", WARN)
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
            if chart.has_land:
                step = LAND_MARK_STEP_NM
                xs = np.arange(-m, size + m + step / 2, step)
                gx, gy = np.meshgrid(xs, xs)
                for x, y in zip(gx[chart.depths(gx, gy) <= 0], gy[chart.depths(gx, gy) <= 0]):
                    items.append(Mark(float(x), float(y), "░", "land", layer=LAYER_CONTOUR - 0.2))
            for level, segs in contours(chart, -m, -m, size + m, size + m,
                                        levels=chart.contour_levels).items():
                style = "coast" if level == 0 else "contour"
                items.extend(Track(seg, style, LAYER_CONTOUR, None) for seg in segs)
                if level == 0 or not segs:
                    continue
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

    # --- grunt vatten -------------------------------------------------------------
    def chart_ahead(self, course: float | None = None) -> tuple[float, float] | None:
        """Grundaste kortdjup framåt längs kursen, med bestickets osäkerhet åt sidorna:
        (djup, avstånd nm). None om kortet saknar djup."""
        chart = self.game.knowledge.bathymetry
        if chart is None:
            return None
        s, sigma = self.ship, self.uncertainty()
        reach = max(SHOAL_LOOK_MIN_NM, s.speed * SHOAL_LOOK_MIN / 60)
        dist = np.arange(0.0, reach + 0.05, 0.1)
        side = np.array([-sigma, 0.0, sigma])
        b = math.radians(s.course if course is None else course)
        ux, uy = math.sin(b), math.cos(b)
        dd, ss = np.meshgrid(dist, side)
        xs = self.est_x + dd * ux + ss * uy
        ys = self.est_y + dd * uy - ss * ux
        z = chart.depths(xs, ys)
        i = np.unravel_index(np.argmin(z), z.shape)
        return float(z[i]), float(dd[i])

    def known_bottom(self) -> tuple[float, float, bool] | None:
        """Grundaste botten vi känner till här och framåt: (djup, avstånd nm, lodat).
        Kortet framåt, och senaste lodning om den är färsk och grundare."""
        ahead = self.chart_ahead()
        recent = [b for b in self.bottom_soundings if self.now - b.t <= SOUNDING_TRUST_S]
        best = (ahead[0], ahead[1], False) if ahead else None
        if recent and (best is None or recent[-1].depth < best[0]):
            best = (recent[-1].depth, 0.0, True)
        return best

    def depth_limit(self) -> float | None:
        """Djupaste djup navigatören går med på här, eller None om botten är okänd."""
        kb = self.known_bottom()
        if kb is None:
            return None
        return max(PERISCOPE_DEPTH, math.floor((kb[0] - SHOAL_MARGIN_M) / 10) * 10)

    # --- ligga på botten -----------------------------------------------------------
    def bottom_here(self) -> tuple[float, str | None, bool] | None:
        """Botten där vi tror att vi är: (djup, bottentyp enligt kortet, lodat)."""
        chart = self.game.knowledge.bathymetry
        kind = chart.bottom_type(self.est_x, self.est_y) if chart is not None else None
        recent = [b for b in self.bottom_soundings if self.now - b.t <= SOUNDING_TRUST_S]
        if recent:
            return recent[-1].depth, kind, True
        if chart is None:
            return None
        return chart.depth_at(self.est_x, self.est_y), kind, False

    def _settle(self) -> None:
        s, sys = self.ship, self.own.sys
        if sys.on_bottom:
            self.say("nav.settle.already", kind="ack")
            return
        here = self.bottom_here()
        if here is None:
            self.say("nav.settle.refused", {"reason": "vi vet inte djupet här. Ekolodet först"})
            return
        depth, kind, sounded = here
        if depth > TEST_DEPTH:
            self.say("nav.settle.refused",
                     {"reason": f"botten ligger på cirka {round(depth, -1):.0f} meter, under provdjup"})
            return
        self.vak = None
        self.goal = None
        sys.settle = True
        self._settle_aim = min(s.max_depth, depth + SETTLE_EXTRA_M)
        s.order_speed(min(s.ordered_speed, SETTLE_SPEED) if s.ordered_speed > 0 else SETTLE_SPEED)
        # först sakta in, sedan ned: botten ska nås i krypfart
        s.order_depth(self._settle_aim if s.speed <= SETTLE_DESCEND_KN else s.depth)
        self._pending.discard("depth")
        self._pending.discard("speed")
        self.say("nav.settle.ack", {"depth": round(depth, -1), "kind": kind, "sounded": sounded},
                 kind="ack")

    def _lift(self) -> None:
        sys = self.own.sys
        if sys.on_bottom:
            self.say("nav.settle.lift", kind="ack")
        sys.settle = sys.on_bottom = False

    def _settle_watch(self) -> None:
        s, sys = self.ship, self.own.sys
        if sys.blowing and (sys.settle or sys.on_bottom):
            sys.settle = sys.on_bottom = False
            return
        if sys.settle and not sys.on_bottom and s.speed <= SETTLE_DESCEND_KN \
                and s.ordered_depth < self._settle_aim:
            s.order_depth(self._settle_aim)
        if sys.settle and not sys.on_bottom and s.depth >= self._settle_aim - 0.5:
            sys.settle = False
            self.say("nav.settle.not_reached", {"depth": s.depth}, alarm=True)

    def _settle_proposal(self) -> Proposal | None:
        """Förslag att lägga oss på botten: hot hållet, grunt och mjukt enligt kortet."""
        sys = self.own.sys
        if sys.settle or sys.on_bottom or not self.game.knowledge.threat_held():
            return None
        here = self.bottom_here()
        if here is None or here[1] is None or here[1] == "klippa" or here[0] > SETTLE_SUGGEST_MAX_M:
            return None
        return Proposal(2, "settle", "nav.suggest.settle", "botten",
                        {"depth": round(here[0], -1), "kind": here[1]},
                        quality=self._shoal_quality(), cooldown=1200)

    def _shoal_quality(self) -> Quality:
        sigma = self.uncertainty()
        return Quality.GOD if sigma < 0.25 else Quality.OSAKER if sigma < 0.6 else Quality.DALIG

    def _shoal_watch(self) -> None:
        if self.now % SHOAL_CHECK_S:
            return
        if self.own.sys.settle or self.own.sys.on_bottom:
            return
        if (p := self._settle_proposal()) is not None:
            self.propose(p)
        if self._land_watch():
            return
        kb = self.known_bottom()
        if kb is None:
            return
        shoal, dist, sounded = kb
        s = self.ship
        limit = self.depth_limit()
        if s.ordered_depth <= limit:
            return                          # på väg upp, eller redan grunt nog
        minutes = dist * 60 / max(s.speed, 0.5)
        self.suggest("shoal", "nav.suggest.shoal",
                     {"shoal": round(shoal, -1), "dist": dist, "depth": limit, "sounded": sounded},
                     order=f"djup {limit:.0f}", cooldown=300,
                     quality=Quality.SAKER if sounded else self._shoal_quality(),
                     alarm=minutes < 3)

    def _land_watch(self) -> bool:
        """Land eller vatten för grunt även på periskopdjup framåt: föreslå en gir."""
        s = self.ship
        if s.speed < 0.5:
            return False
        ahead = self.chart_ahead()
        if ahead is None or ahead[0] >= LAND_CLEAR_M:
            return False
        options = [(c, self.chart_ahead(c)) for c in
                   (norm360(s.course + sgn * a) for a in LAND_TURNS for sgn in (1, -1))]
        options = [(c, a[0]) for c, a in options if a is not None]
        if not options:
            return True
        best = max(options, key=lambda o: o[1])
        if best[1] < ahead[0] + 10:
            return True                     # ingen kurs är bättre: säg inget nytt
        minutes = ahead[1] * 60 / max(s.speed, 0.5)
        self.suggest("land", "nav.suggest.land",
                     {"shoal": ahead[0], "dist": ahead[1], "course": best[0]},
                     order=f"kurs {fmt_course(best[0])}", cooldown=120,
                     quality=self._shoal_quality(), alarm=minutes < 4)
        return True

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
                self.goal = None
                self.course_set_t = self.now
                s.order_course(c)
                self._ack("course", {"course": c}, s.course == s.ordered_course)
            case SetSpeed(speed=v):
                self.vak = None
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
            case SettleOnBottom():
                self._settle()

    def _echo(self) -> float:
        """Ekolodet: en sensor. Lodar botten rakt under oss (hörs) och loggar lodningen."""
        world, s = self.game.world, self.ship
        world.emit(Transient("echosounder", s.x, s.y, s.depth,
                             acoustics.ECHO_SOUNDER_LEVEL, world.own.id, self.now))
        bottom = world.env.bottom_at(s.x, s.y)
        under = round(bottom - s.depth + self.game.rng.gauss(0, 2 + bottom * 0.005), -1)
        self.bottom_soundings.append(BottomSounding(self.now, s.depth + under,
                                                    self.est_x, self.est_y))
        return s.depth + under

    # --- fix mot botten -----------------------------------------------------------
    def _start_bottom_fix(self) -> None:
        s = self.ship
        reason = None
        if self.game.knowledge.bathymetry is None:
            reason = "vi har inget sjökort med djup här"
        elif self._bfix is not None:
            reason = "vi lodar redan för en fix"
        elif s.speed < BFIX_MIN_SPEED and s.ordered_speed < BFIX_MIN_SPEED:
            reason = "vi måste ha minst två knop för att lodningarna ska säga något"
        elif self.own.sys.on_bottom:
            reason = "vi ligger på botten"
        if reason:
            self.say("nav.bfix.refused", {"reason": reason})
            return
        self._bfix = []
        self._bfix_next = self.now
        self.say("nav.bfix.start", {"n": BFIX_N,
                                    "minutes": round(BFIX_N * BFIX_INTERVAL_S / 60)}, kind="ack")

    def _bottom_fix_step(self) -> None:
        if self._bfix is None or self.now < self._bfix_next:
            return
        if self.ship.speed < 1.0:
            self._bfix = None
            self.say("nav.bfix.aborted")
            return
        self._bfix.append((self.est_x, self.est_y, self._echo()))
        self._bfix_next = self.now + BFIX_INTERVAL_S
        if len(self._bfix) < BFIX_N:
            return
        series, self._bfix = self._bfix, None
        chart = self.game.knowledge.bathymetry
        # lodningarna i besticket som det var då, flyttade till där vi tror att vi är nu
        cx, cy, _ = series[-1]
        pts = [(x - cx + self.est_x, y - cy + self.est_y) for x, y, _ in series]
        prior = self.uncertainty()
        m = match_soundings(chart, pts, [d for *_, d in series], prior)
        sigma = math.hypot(m.sigma, chart.accuracy_nm)
        if not m.consistent:
            depths = [d for *_, d in series]
            here = [chart.depth_at(x, y) for x, y in pts]
            how = "grundare" if sum(depths) < sum(here) else "djupare"
            self.say("nav.bfix.mismatch", {"how": how}, quality=Quality.DALIG)
            return
        if m.sigma > BFIX_FLAT * prior:
            self.say("nav.bfix.flat", quality=Quality.DALIG)
            return
        if sigma >= prior * 0.95:
            self.say("nav.bfix.chart", {"accuracy": chart.accuracy_nm}, quality=Quality.DALIG)
            return
        new_x, new_y = self.est_x + m.dx, self.est_y + m.dy
        err = math.hypot(m.dx, m.dy)
        b = bearing_to(self.est_x, self.est_y, new_x, new_y)
        self.dr_track[-1].append((self.est_x, self.est_y))
        self.dr_track.append([(new_x, new_y)])
        self.fixes.append((new_x, new_y, self.now))
        self.est_x, self.est_y = new_x, new_y
        self.last_fix_t = self.now
        self.fix_sigma = sigma
        q = (Quality.SAKER if sigma < 0.15 else Quality.GOD if sigma < 0.3
             else Quality.OSAKER if sigma < 0.6 else Quality.DALIG)
        if m.line_of_position:
            self.say("nav.bfix.line", {"error": err, "bearing_corr": b, "sigma": sigma,
                                       "bearing": m.minor_bearing,
                                       "minor": math.hypot(m.sigma_minor, chart.accuracy_nm)},
                     quality=q)
            return
        self.say("nav.bfix.done", {"error": err, "bearing": b, "sigma": sigma}, quality=q)

    def _bfix_worthwhile(self) -> bool:
        """Kan en fix mot botten hjälpa här: kort med djup, brant botten, bestick sämre än kortet."""
        chart = self.game.knowledge.bathymetry
        if chart is None or self._bfix is not None or self.own.sys.on_bottom:
            return False
        sys = self.own.sys
        if sys.fire or sys.smoke > 0.2 or sys.flooding > 0:
            return False                    # annat går före
        if self.uncertainty() < BFIX_GAIN * max(chart.accuracy_nm, 0.3):
            return False                    # kortet är inte bättre än besticket
        return chart.slope(self.est_x, self.est_y) > BFIX_RELIEF_M_PER_NM

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
        if self.game.escape_nm is None and self._quiet_contact_picture() \
                and self.now - self.course_set_t >= SEARCH_LEG_S \
                and self.vak is None and self.goal is None and s.ordered_speed > 0:
            # gir 90° åt den sida som pekar mest mot kvadratens mitt
            size = self.game.world.size_nm
            to_mid = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            c = min((norm360(s.ordered_course + 90), norm360(s.ordered_course - 90)),
                    key=lambda k: abs(angle_diff(k, to_mid)))
            out.append(Proposal(6, "idle_search", "nav.suggest.search",
                                f"kurs {fmt_course(c)}", {"course": c}))
        return out

    def _steer_to(self, name: str) -> None:
        wps = self.game.knowledge.waypoints
        key = name.strip().lower()
        wp = next((w for n, w in wps.items() if n.lower() == key), None) or \
            next((w for n, w in wps.items() if n.lower().startswith(key[:5])), None)
        if wp is None:
            self.say("nav.steer.none", {"name": name, "known": sorted(wps)})
            return
        c = round(bearing_to(self.est_x, self.est_y, wp.x, wp.y)) % 360
        self.vak = None
        self.goal = None
        self.course_set_t = self.now
        self.ship.order_course(c)
        self.say("nav.steer", {"name": wp.name, "course": c,
                               "range": distance(self.est_x, self.est_y, wp.x, wp.y),
                               "sigma": wp.sigma(self.now) + self.uncertainty()}, kind="ack")

    # --- ut ur området -------------------------------------------------------------
    def outside_area(self) -> bool:
        m, size = self.game.escape_nm or 0.0, self.game.world.size_nm
        return not (-m <= self.est_x <= size + m and -m <= self.est_y <= size + m)

    def _clear_path(self, x: float, y: float, course: float, dist: float) -> bool:
        chart = self.game.knowledge.bathymetry
        if chart is None or not chart.has_land:
            return True
        b = math.radians(course)
        steps = np.arange(0.1, dist + 0.05, 0.1)
        return not (chart.depths(x + steps * math.sin(b), y + steps * math.cos(b))
                    < LAND_CLEAR_M).any()

    def _edge_routes(self, x: float, y: float) -> list[tuple[float, float]]:
        """Raka vägar ut till marginalen utanför varje kant som inte går över land."""
        m, size = self.game.escape_nm or 0.0, self.game.world.size_nm
        sigma = self.uncertainty()
        routes = [(90.0, size + m - x), (270.0, x + m), (0.0, size + m - y), (180.0, y + m)]
        return [(c, d + sigma) for c, d in routes if self._clear_path(x, y, c, d + sigma)]

    def _water_grid(self):
        """Sjökortets vatten (djupt nog för periskopdjup) på ett rutnät, en gång."""
        if self._water is None:
            chart = self.game.knowledge.bathymetry
            size, m = self.game.world.size_nm, (self.game.escape_nm or 0.0) + PATH_STEP_NM * 2
            xs = np.arange(-m, size + m + PATH_STEP_NM / 2, PATH_STEP_NM)
            gx, gy = np.meshgrid(xs, xs)            # [rad=y, kolumn=x]
            self._water = (xs, chart.depths(gx, gy) >= LAND_CLEAR_M)
        return self._water

    def _path_out(self, x: float, y: float) -> tuple[float, float] | None:
        """Väg genom vattnet ut ur området (bredden först på kortets rutnät).
        (kurs mot den längsta raka biten av vägen, total längd) eller None."""
        chart = self.game.knowledge.bathymetry
        if chart is None or not chart.has_land:
            return None
        xs, ok = self._water_grid()
        n = len(xs)
        m, size = self.game.escape_nm or 0.0, self.game.world.size_nm
        i0 = int(round((y - xs[0]) / PATH_STEP_NM))
        j0 = int(round((x - xs[0]) / PATH_STEP_NM))
        if not (0 <= i0 < n and 0 <= j0 < n):
            return None
        prev = {(i0, j0): None}
        queue = deque([(i0, j0)])
        goal = None
        while queue:
            i, j = queue.popleft()
            px, py = xs[j], xs[i]
            if not (-m <= px <= size + m and -m <= py <= size + m):
                goal = (i, j)
                break
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                a, b = i + di, j + dj
                if 0 <= a < n and 0 <= b < n and ok[a, b] and (a, b) not in prev:
                    prev[(a, b)] = (i, j)
                    queue.append((a, b))
        if goal is None:
            return None
        path = []
        cur = goal
        while cur is not None:
            path.append((float(xs[cur[1]]), float(xs[cur[0]])))
            cur = prev[cur]
        path.reverse()
        total = sum(distance(*path[k], *path[k + 1]) for k in range(len(path) - 1))
        # styr mot den längsta punkten längs vägen som syns rakt fram
        aim = path[min(1, len(path) - 1)]
        for px, py in path[1:]:
            d = distance(x, y, px, py)
            if d > 0.05 and self._clear_path(x, y, bearing_to(x, y, px, py), d):
                aim = (px, py)
        return bearing_to(x, y, *aim), total

    def exit_route(self) -> tuple[float, float, bool] | None:
        """Kortaste vägen ut ur området enligt besticket, helst inte mot en hotkontakt och
        aldrig över land. (kurs, sjömil, fri från kontakter). Finns ingen rak väg går den
        via en känd plats; `exit_via` säger vilken."""
        self.exit_via = None
        if self.outside_area():
            return None
        x, y = self.est_x, self.est_y
        threats = [t.last_bearing for t in self.game.knowledge.tracks.values()
                   if t.threat and t.last_bearing is not None]
        best = None
        for c, d in self._edge_routes(x, y):
            clear = all(abs(angle_diff(c, b)) > EXIT_THREAT_SECTOR for b in threats)
            cost = d + (0.0 if clear else EXIT_THREAT_PENALTY_NM)
            if best is None or cost < best[0]:
                best = (cost, c, d, clear and bool(threats))
        if best is None and (leg := self._path_out(x, y)) is not None:
            c, total = leg
            best = (total, c, total, False)
            self.exit_via = "runt land"
        if best is None:
            return None
        _, c, d, clear = best
        return c, d, clear

    def _escape_watch(self) -> None:
        if not self.game.escape_ready():
            return
        if self.outside_area():
            if not self._told_out:
                self._told_out = True
                self.say("nav.exit.out", {"area": self.game.area_name})
            return
        self._told_out = False
        if self.now < EXIT_FIRST_SUGGEST_S or not self.game.escape_ready():
            return
        if self._exit_cache is None or self.now - self._exit_cache[0] >= EXIT_RECALC_S:
            self._exit_cache = (self.now, self.exit_route(), self.exit_via)
        _, route, self.exit_via = self._exit_cache
        if route is None:
            return
        c, dist, clear = route
        if abs(angle_diff(c, self.ship.ordered_course)) <= 20:
            return
        self.suggest("exit", "nav.suggest.exit",
                     {"course": c, "dist": dist, "clear": clear, "area": self.game.area_name,
                      "via": self.exit_via},
                     order=f"kurs {fmt_course(c)}", cooldown=600 if self.exit_via else 1200)

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        self._dead_reckon()
        self._log_depth()
        if self.now % DR_TRACK_INTERVAL_S == 0:
            self.dr_track[-1].append((self.est_x, self.est_y))
        self._sound_ice()
        self._bottom_fix_step()
        self._settle_watch()
        self._shoal_watch()
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
                self.fix_sigma = PERISCOPE_FIX_SIGMA
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
        size = self.game.world.size_nm
        if self.game.escape_nm is not None:
            self._escape_watch()
        elif not (0.5 <= self.est_x <= size - 0.5 and 0.5 <= self.est_y <= size - 0.5):
            c = bearing_to(self.est_x, self.est_y, size / 2, size / 2)
            self.suggest("area", "nav.suggest.area", {"course": c, "area": self.game.area_name},
                         order=f"kurs {fmt_course(c)}", cooldown=900)
        if s.depth > TEST_DEPTH + 5:
            self.suggest("test_depth", "nav.suggest.test_depth", {"depth": s.depth},
                         order="djup 280", cooldown=300)
