"""Plottlaget: målrörelseanalys, svar på läge/plot och självmant kursförslag."""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass

import math

from ..chart import LAYER_MARK, LAYER_TRACK, Mark, Ray, Ring
from ..events import ConvoyAssessed, SoundHeard
from ..crew import Role
from ..fmt import fmt_course
from ..geo import angle_diff, norm360
from ..knowledge import ContactTrack
from ..orders import DESIG, CommandSpec, Order, desig
from ..reports import Quality
from ..tma import (MANEUVER_CHI2, MANEUVER_SPLIT, MAX_TARGET_KN, BearingObs, Solution,
                   maneuver_statistic, own_maneuvered, predicted_bearing, solve)
from ..zigzag import (ConvoyEstimate, LegFix, TrackPoint, base_course, escorts_near, groups,
                      mean_leg, merge_turns)
from .base import Proposal, Station

PLOT_INTERVAL = 30              # sekunder mellan omräkningar
LOOK_TURN_MIN_DEG = 20.0        # periskopets kurs så här långt från lösningens: målet har girat
LOOK_TURN_SIGMAS = 3.0
SUGGEST_COOLDOWN = 420
SUGGEST_MIN_LEG_S = 300         # rak kurs så här länge innan nytt förslag
TABLE_ROWS = 15
BEARING_LINE_NM = 12.0          # bäringslinjer på kortet
VECTOR_S = 360                  # fartvektor på kortet: sex minuters gång
FADE_S = 300                    # äldre bäringar ritas bleka
MANEUVER_REPEAT_S = 300         # säg "har ändrat kurs" högst så här ofta per kontakt
FORGET_S = 1800                 # tappade kontakter: bäringen tas bort efter så här länge
CONVOY_TURN_REPEAT_S = 180      # "konvojen girar" högst så här ofta
CONVOY_POINT_AGE_S = 300        # en lösning så gammal räknas inte i grupperingen
CONVOY_MAX_KN = 25.0            # snabbare lösning på ett konvojfartyg är fel
CONVOY_COURSE_SIGMA = 30.0      # sämre bestämd kurs än så räknas inte i grupperingen
CONVOY_SPEED_SIGMA = 6.0

# Blyertsmärken: det sonar hört, skrivet på kortet med klockslag där och när det hördes
PENCIL_KEEP_S = 1800            # suddas ut efter så här länge
PENCIL_FRESH_S = 60             # nytt märke: skarpt
PENCIL_FADE_S = 600             # äldre än så: blekt
PENCIL_CLOCKS = 5               # klockslag bara på de nyaste
PENCIL_STROKE_NM = 0.6          # streck längs bäringen när avståndet är okänt
PENCIL_SECTOR_DEG = 15          # okänd källa: samma märke inom sektorn
PENCIL_SYMBOL = {"ping": "P", "buoy_ping": "BP", "splash": "✕", "buoy": "B",
                 "explosion": "✱", "breakup": "↓"}
PENCIL_GAP_S = {"ping": 300, "buoy_ping": 300, "splash": 60, "buoy": 300,
                "explosion": 30, "breakup": 60}   # samma märke och källa högst så ofta
LAYER_PENCIL = LAYER_TRACK + 0.5                 # strecken under bäringar och lösningar
LAYER_PENCIL_MARK = LAYER_MARK - 0.5             # märken på en lösning: under kontaktens märke


@dataclass(frozen=True)
class PencilMark:
    """Ett blyertsmärke: ett hört ljud där plottet trodde det kom ifrån (kunskap).

    on_bearing: avståndet okänt, (x, y) är vårt beräknade läge och märket ett streck
    längs bäringen. Annars ligger (x, y) på kontaktens lösning när ljudet hördes.
    """
    t: int
    kind: str
    symbol: str
    x: float
    y: float
    bearing: float
    on_bearing: bool
    key: str


@dataclass(frozen=True)
class QuerySolution(Order):
    designation: str | None


@dataclass(frozen=True)
class ShowPlot(Order):
    designation: str | None


def solution_data(sol: Solution) -> dict:
    d = dataclasses.asdict(sol)
    d["quality"] = sol.quality
    return d


class PlotTeam(Station):
    role = Role.PLOT
    COMMANDS = [
        CommandSpec(rf"(?:läge|lage|lösning|losning)(?:\s+{DESIG})?",
                    lambda m: QuerySolution(desig(m[1])), "läge S-1"),
        CommandSpec(rf"(?:plot|plott|plotten)(?:\s+{DESIG})?",
                    lambda m: ShowPlot(desig(m[1])), "plot S-1"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self._last_suggest: dict[str, int] = {}
        self._maneuver_said: dict[str, int] = {}
        self._look_checked: dict[str, int] = {}     # senaste periskoptitt prövad mot lösningen
        self._convoy_turn_said = -10**9
        self._convoy_quality: Quality | None = None
        self.pencil: list[PencilMark] = []
        self._pencil_last: dict[str, int] = {}

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(SoundHeard, self._on_sound)

    # --- blyertsmärken -----------------------------------------------------------
    def _on_sound(self, e: SoundHeard) -> None:
        symbol = PENCIL_SYMBOL.get(e.kind)
        if symbol is None:
            return
        if e.kind == "ping" and e.detail == "fast":
            symbol = "PP"
        elif e.practice and e.kind in ("splash", "explosion"):
            symbol = "○"
        source = e.designation or f"{round(e.bearing / PENCIL_SECTOR_DEG) % (360 // PENCIL_SECTOR_DEG)}"
        key = f"{symbol}:{source}"
        if e.t - self._pencil_last.get(key, -10**9) < PENCIL_GAP_S[e.kind]:
            return
        self._pencil_last[key] = e.t
        x, y = self.game.own_position_estimate()
        on_bearing = True
        tr = self.game.knowledge.track(e.designation) if e.designation else None
        sol = tr.solution if tr is not None else None
        if sol is not None and sol.quality >= Quality.OSAKER:
            dt = (e.t - sol.t) / 3600.0
            x, y, on_bearing = sol.x + sol.state[2] * dt, sol.y + sol.state[3] * dt, False
        self.pencil.append(PencilMark(e.t, e.kind, symbol, x, y, e.bearing, on_bearing, key))

    def _pencil_items(self) -> list:
        self.pencil = [m for m in self.pencil if self.now - m.t < PENCIL_KEEP_S]
        items: list = []
        n = len(self.pencil)
        for i, m in enumerate(self.pencil):
            age = self.now - m.t
            style = "pencil_new" if age < PENCIL_FRESH_S else "pencil"
            clock = self.game.clock_str(m.t)[:5] if i >= n - PENCIL_CLOCKS else ""
            faded = age >= PENCIL_FADE_S
            if m.on_bearing:            # strecket, sedan symbolen och klockslaget vid änden
                label = f"{m.symbol} {clock}".strip()
                items.append(Ray(m.x, m.y, m.bearing, PENCIL_STROKE_NM, style, label,
                                 faded=faded, layer=LAYER_PENCIL))
            else:                       # symbolen på lösningen (en ruta), klockslaget bredvid
                extra = "snabb" if m.symbol == "PP" else m.symbol[1:]
                items.append(Mark(m.x, m.y, m.symbol[0], style, f"{extra} {clock}".strip(),
                                  faded=faded, layer=LAYER_PENCIL_MARK))
        return items

    # --- order ------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        match order:
            case QuerySolution(designation=d):
                self._answer_solution(d)
            case ShowPlot(designation=d):
                self._answer_plot(d)

    def _pick_track(self, designation: str | None) -> ContactTrack | None:
        k = self.game.knowledge
        if designation:
            tr = k.track(designation)
            if tr is None:
                self.say("plot.unknown_contact", {"designation": designation}, kind="solution")
            return tr
        held = [t for t in k.tracks.values() if t.held] or list(k.tracks.values())
        if not held:
            self.say("plot.no_contacts", kind="solution")
            return None
        if len(held) > 1:
            self.say("plot.which", {"options": [t.designation for t in held]}, kind="solution")
            return None
        return held[0]

    def _resolve(self, tr: ContactTrack) -> Solution | None:
        return self.game.knowledge.resolve(tr.designation, self.now,
                                           self.game.own_position_estimate())

    def _answer_solution(self, designation: str | None) -> None:
        tr = self._pick_track(designation)
        if tr is None:
            return
        sol = self._resolve(tr)
        if sol is None:
            self.say("plot.few_bearings", {"designation": tr.designation},
                     kind="solution", quality=Quality.DALIG)
            return
        need = None
        if sol.quality == Quality.DALIG:
            need = "time" if own_maneuvered(tr.observations) else "turn"
        self.say("plot.solution",
                 {"designation": tr.designation, "solution": solution_data(sol), "need": need},
                 kind="solution", quality=sol.quality)

    def _answer_plot(self, designation: str | None) -> None:
        tr = self._pick_track(designation)
        if tr is None:
            return
        if not tr.observations:
            self.say("plot.no_bearings", {"designation": tr.designation}, kind="plot")
            return
        sol = self._resolve(tr)
        rows = []
        for o in tr.observations[-TABLE_ROWS:]:
            pred = (predicted_bearing(sol.state, sol.t_ref, o.t, o.own_x, o.own_y)
                    if sol is not None else None)
            rows.append({"t": o.t, "bearing": o.bearing, "own_course": o.own_course,
                         "predicted": pred})
        self.say("plot.table",
                 {"designation": tr.designation, "n": len(tr.observations), "rows": rows,
                  "solution": solution_data(sol) if sol else None},
                 kind="plot", quality=sol.quality if sol else Quality.DALIG)

    # --- sjökortet -------------------------------------------------------------
    def chart_items(self) -> list:
        """Lösningar som läge, fartvektor och avståndsosäkerhet; annars senaste bäringen.
        Därtill blyertsmärkena för det sonar hört."""
        items: list = self._pencil_items()
        for tr in self.game.knowledge.tracks.values():
            if tr.benign and "drivstation" not in tr.classification and not tr.civil:
                continue
            sol = tr.solution
            style = "merchant" if tr.civil else "contact"
            if sol is not None and sol.quality >= Quality.OSAKER and \
                    (tr.threat or tr.civil or tr.friendly):
                dt = (self.now - sol.t) / 3600.0
                vx, vy = sol.state[2], sol.state[3]
                x, y = sol.x + vx * dt, sol.y + vy * dt
                faded = not tr.held
                what = "handelsfartyg" if tr.civil else sol.quality.label
                items.append(Ring(x, y, sol.range_sigma, style, quality=sol.quality))
                items.append(Ray(x, y, sol.course, sol.speed * VECTOR_S / 3600, f"{style}_vector",
                                 quality=sol.quality, faded=faded))
                items.append(Mark(x, y, "◇" if tr.civil else "◆", style,
                                  f"{tr.designation} {what}, {sol.speed:.0f} kn",
                                  quality=sol.quality, faded=faded))
            elif tr.observations:
                o = tr.observations[-1]
                age = self.now - o.t
                if not tr.held and age > FORGET_S:
                    continue
                label = f"{tr.designation} {fmt_course(o.bearing)}"
                if age >= 60:
                    label += f" ({age // 60} min)"
                if tr.civil:
                    label += " handelsfartyg"
                items.append(Ray(o.own_x, o.own_y, o.bearing, BEARING_LINE_NM,
                                 "merchant_vector" if tr.civil else "bearing", label,
                                 quality=sol.quality if sol else Quality.DALIG,
                                 faded=not tr.held or age > FADE_S))
        return items

    # --- löpande arbete -------------------------------------------------------
    def update(self) -> None:
        if self.now % PLOT_INTERVAL:
            return
        for tr in self.game.knowledge.tracks.values():
            civil = tr.civil and tr.held
            if not (tr.threat or civil or tr.held and tr.friendly) or len(tr.observations) < 3:
                continue
            prev_q = tr.solution.quality if tr.solution else None
            sol = self._resolve(tr)
            if sol is None or civil:
                continue                # handelsfartyg plottas tyst, för kortet
            look = self._look_turn(tr)
            if look is not None or \
                    sol.n_obs >= 12 and (sol.fit > MANEUVER_CHI2 or self._target_turned(tr, sol)):
                self._end_leg(tr)
                # en periskoptitt efter giren ger läge, kurs och fart: börja om från den
                tr.tma_from_t = look.t if look is not None else self.now - 120
                convoy = self.game.knowledge.convoy
                if convoy is not None and convoy.contains(tr.designation) \
                        and tr.designation in convoy.members:
                    self._convoy_turned(convoy)
                # ett mål som girar hela tiden (jagaren söker) startas om tyst däremellan
                elif self.now - self._maneuver_said.get(tr.designation, -10**9) >= MANEUVER_REPEAT_S:
                    self._maneuver_said[tr.designation] = self.now
                    self.say("plot.maneuver", {"designation": tr.designation},
                             kind="solution", quality=Quality.DALIG, alarm=True)
                sol = self._resolve(tr)
                if sol is None:
                    continue
            if sol.quality >= Quality.OSAKER:
                tr.leg_sol = sol
            self.game.log(f"TMA {tr.designation} r={sol.range_nm:.2f}±{sol.range_sigma:.2f} "
                          f"k={sol.course:.0f} v={sol.speed:.1f} q={sol.quality.label} n={sol.n_obs}")
            if sol.quality >= Quality.GOD and (prev_q is None or sol.quality > prev_q):
                self.say("plot.improved",
                         {"designation": tr.designation, "solution": solution_data(sol)},
                         kind="solution", quality=sol.quality)
            elif (sol.quality < Quality.GOD and sol.n_obs >= 12 and sol.span_s >= 120
                  and (tr.threat or self.game.knowledge.listening)
                  and not self._maneuvered_recently(tr) and not self._convoy_sibling(tr)
                  and not self.game.knowledge.hunted(self.now)
                  and self.now - self._last_suggest.get(tr.designation, -10**9) >= SUGGEST_COOLDOWN):
                self._last_suggest[tr.designation] = self.now
                course = self._suggest_course(sol, tr)
                self.suggest(f"turn{tr.designation}", "plot.suggest",
                             {"designation": tr.designation, "quality": sol.quality,
                              "course": course, "first": not sol.own_maneuvered},
                             order=f"kurs {round(course) % 360:03d}", cooldown=0,
                             quality=sol.quality)

        self._assess_convoy()

    # --- konvoj och sicksack ------------------------------------------------------
    def _end_leg(self, tr: ContactTrack) -> None:
        """Målet har girat: spara benets sista användbara lösning och girens tid."""
        ls = tr.leg_sol
        if ls is not None and ls.t >= tr.tma_from_t:
            tr.legs.append(LegFix(ls.t, ls.x, ls.y, ls.range_sigma, ls.course, ls.speed))
        tr.leg_sol = None
        tr.turns.append(self.now - 120)

    def _convoy_sibling(self, tr: ContactTrack) -> bool:
        """Ett konvojfartyg som inte är det första: kursförslag bara för det första."""
        c = self.game.knowledge.convoy
        return c is not None and tr.designation in c.members[1:]

    def _convoy_turned(self, convoy: ConvoyEstimate) -> None:
        if self.now - self._convoy_turn_said < CONVOY_TURN_REPEAT_S:
            return
        self._convoy_turn_said = self.now
        self.say("plot.convoy.turn", {"base": _base_data(convoy),
                                      "mean_leg_s": convoy.mean_leg_s},
                 kind="solution", quality=convoy.base.quality if convoy.base else Quality.DALIG)

    def _points(self) -> list[TrackPoint]:
        """Kontakternas läge och rörelse: TMA-lösningen, annars utkikens senaste bedömning."""
        k = self.game.knowledge
        seen = {}
        pic = k.periscope
        if pic is not None and self.now - pic.t <= CONVOY_POINT_AGE_S:
            seen = {o.designation: o for o in pic.objects if o.designation and o.seen_t == pic.t
                    and o.course is not None and o.aob_quality >= Quality.OSAKER}
        ex, ey = self.game.own_position_estimate()
        pts = []
        for tr in k.tracks.values():
            if not tr.held or tr.civil or "handelsfartyg" in tr.classification:
                continue
            escort = "jagare" in tr.classification
            sol = tr.solution
            if sol is not None and sol.quality >= Quality.OSAKER \
                    and self.now - sol.t <= CONVOY_POINT_AGE_S and sol.speed <= CONVOY_MAX_KN \
                    and sol.course_sigma <= CONVOY_COURSE_SIGMA \
                    and sol.speed_sigma <= CONVOY_SPEED_SIGMA:
                dt = (self.now - sol.t) / 3600.0
                pts.append(TrackPoint(tr.designation, sol.x + sol.state[2] * dt,
                                      sol.y + sol.state[3] * dt, sol.course, sol.speed, escort))
            elif (o := seen.get(tr.designation)) is not None:
                # periskopet: bäring och avstånd från vårt läge, kurs ur vinkeln på bogen
                b = math.radians(o.bearing)
                dt = (self.now - pic.t) / 3600.0
                vx = o.speed * math.sin(math.radians(o.course))
                vy = o.speed * math.cos(math.radians(o.course))
                pts.append(TrackPoint(tr.designation, ex + o.range_nm * math.sin(b) + vx * dt,
                                      ey + o.range_nm * math.cos(b) + vy * dt, o.course,
                                      o.speed, escort))
        return pts

    def _assess_convoy(self) -> None:
        k = self.game.knowledge
        prev = k.convoy
        pts = self._points()
        found = groups(pts)
        group = None
        if prev is not None:
            group = next((g for g in found if any(p.designation in prev.members for p in g)), None)
        elif found:
            group = max(found, key=len)
        if group is None and prev is None:
            return
        members = list(prev.members) if prev is not None else []
        for p in group or []:
            if p.designation not in members:
                members.append(p.designation)
        members = [m for m in members if (tr := k.tracks.get(m)) is not None
                   and "jagare" not in tr.classification and "handelsfartyg" not in tr.classification
                   and (tr.held or self.now - (tr.observations[-1].t if tr.observations else 0)
                        < FORGET_S)]
        if len(members) < 2:
            if prev is not None:            # konvojen är borta ur plottet: glöm den
                self.game.log(f"plott: konvojen {', '.join(prev.members)} är inte längre en grupp")
                self._convoy_quality = None
                self.game.bus.publish(ConvoyAssessed(self.now, None))
            return
        if group:
            x = sum(p.x for p in group) / len(group)
            y = sum(p.y for p in group) / len(group)
            sx = sum(math.sin(math.radians(p.course)) for p in group)
            sy = sum(math.cos(math.radians(p.course)) for p in group)
            leg_course = norm360(math.degrees(math.atan2(sx, sy)))
            leg_speed = sorted(p.speed for p in group)[len(group) // 2]
            escorts = escorts_near(group, pts)
        else:
            x, y, _vx, _vy = prev.advance(self.now)
            leg_course, leg_speed, escorts = prev.leg_course, prev.leg_speed, list(prev.escorts)
        tracks = [k.tracks[m] for m in members]
        base = base_course([t.legs for t in tracks if len(t.legs) >= 2])
        turns = merge_turns(t for tr in tracks for t in tr.turns)
        est = ConvoyEstimate(self.now, tuple(members), tuple(escorts), x, y, leg_course,
                             leg_speed, base, mean_leg(tr.turns for tr in tracks),
                             turns[-1] if turns else None)
        self.game.bus.publish(ConvoyAssessed(self.now, est))
        if prev is None:
            self.say("plot.convoy.found", {"members": list(members), "escorts": len(escorts),
                                           "course": leg_course, "speed": leg_speed},
                     kind="solution", quality=Quality.OSAKER, alarm=True)
        if base is not None and base.quality >= Quality.OSAKER and \
                (self._convoy_quality is None or base.quality > self._convoy_quality):
            self._convoy_quality = base.quality
            self.say("plot.convoy.base", {"base": _base_data(est), "mean_leg_s": est.mean_leg_s},
                     kind="solution", quality=base.quality)

    def idle_proposals(self) -> list[Proposal]:
        out = []
        if self.game.knowledge.hunted(self.now):
            return out          # jagade: kursen behövs för att komma undan, inte för TMA
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            if not (tr.threat or tr.held and tr.friendly and self.game.knowledge.listening) \
                    or sol is None or sol.quality >= Quality.GOD:
                continue
            if self._maneuvered_recently(tr):
                continue
            course = self._suggest_course(sol, tr)
            out.append(Proposal(3, f"idle_turn{tr.designation}", "plot.suggest",
                                f"kurs {round(course) % 360:03d}",
                                {"designation": tr.designation, "quality": sol.quality,
                                 "course": course, "first": not sol.own_maneuvered},
                                quality=sol.quality, cooldown=SUGGEST_COOLDOWN))
        return out

    def _target_turned(self, tr: ContactTrack, sol: Solution) -> bool:
        """Har målet girat? Brytpunktstestet på bäringarna sedan senaste omstart.
        En dålig lösning ritas inte som läge, så den prövas inte, utom när den är
        dålig för att farten är orimlig: det är ofta just en gir."""
        if sol.quality < Quality.OSAKER and sol.speed <= MAX_TARGET_KN:
            return False
        obs = [o for o in tr.observations if o.t >= tr.tma_from_t]
        return maneuver_statistic(obs) > MANEUVER_SPLIT

    def _look_turn(self, tr: ContactTrack) -> BearingObs | None:
        """Visar en ny periskoptitt en annan kurs än lösningen före titten? Då har målet
        girat sedan förra titten. Returnerar titten, annars None."""
        obs = [o for o in tr.observations if o.t >= tr.tma_from_t]
        looks = [o for o in obs if o.course_obs is not None
                 and o.t > self._look_checked.get(tr.designation, -10**9)]
        if not looks:
            return None
        look = looks[-1]
        self._look_checked[tr.designation] = look.t
        before = [o for o in obs if o.t < look.t]
        if len(before) < 12:
            return None
        sol = solve(before, t_now=look.t, own_now=(look.own_x, look.own_y))
        if sol is None or sol.quality < Quality.OSAKER:
            return None
        tol = max(LOOK_TURN_MIN_DEG,
                  LOOK_TURN_SIGMAS * math.hypot(look.course_sigma, min(sol.course_sigma, 60.0)))
        return look if abs(angle_diff(look.course_obs, sol.course)) > tol else None

    def _maneuvered_recently(self, tr: ContactTrack) -> bool:
        recent = [o for o in tr.observations if o.t >= self.now - SUGGEST_MIN_LEG_S]
        return (own_maneuvered(recent, threshold_deg=15.0)
                or "course" in self.game.world.own.state.changing())

    def _suggest_course(self, sol: Solution, tr: ContactTrack) -> float:
        own_course = self.game.world.own.state.course
        window = [o for o in tr.observations if o.t >= self.now - 1800]
        if sol.own_maneuvered and window:
            # sicksack: spegla förra giren så att nästa ben korsar tillbaka
            turn = angle_diff(own_course, window[0].own_course)
            if abs(turn) >= 20:
                return norm360(own_course - 2 * turn)
        rel = angle_diff(sol.bearing, own_course)
        # första giren: vänd bort från kontakten för att inte stänga avståndet
        return norm360(own_course - 60 if rel > 0 else own_course + 60)


def _base_data(c: ConvoyEstimate) -> dict | None:
    b = c.base
    if b is None:
        return None
    return {"course": b.course, "speed": b.speed, "quality": b.quality, "legs": b.legs}


def _leg_text(s: int | None) -> str:
    return f" Sicksack, ben på ungefär {round(s / 60)} minuter." if s else ""


def _base_text(b: dict | None) -> str:
    if b is None:
        return "Baskursen kan vi inte säga ännu, vi behöver se fler ben."
    q = Quality(b["quality"])
    if q == Quality.DALIG:
        return f"Baskursen är osäker, kanske {fmt_course(round(b['course'] / 10) * 10)}."
    return (f"Baskurs {fmt_course(b['course'])}, fart över grund {b['speed']:.0f} knop, "
            f"kvalitet {q.label} efter {b['legs']} ben.")


def _ru_base(b: dict | None) -> str:
    from .. import russian as R
    if b is None:
        return "генеральный курс пока определить не можем."
    q = Quality(b["quality"])
    if q == Quality.DALIG:
        return f"генеральный курс неясен, возможно {R.course(round(b['course'] / 10) * 10)}."
    return (f"генеральный курс {R.course(b['course'])}, скорость {R.count(b['speed'], R.KNOT)}, "
            f"решение {R.QUALITY_RU[q]}.")


def _ru_leg(s: int | None) -> str:
    from .. import russian as R
    return f" Противолодочный зигзаг, галс около {R.count(round(s / 60), R.MINUTE)}." if s else ""


PHRASES = {
    "plot.convoy.found": lambda d: (
        f"Kapten, plottet! {', '.join(d['members'])} går tillsammans, samma kurs och fart. "
        f"Det är en konvoj" + (f" med {d['escorts']} jagare som eskort" if d["escorts"] else "")
        + f". Just nu kurs {fmt_course(d['course'])}, {d['speed']:.0f} knop."),
    "plot.convoy.turn": lambda d: "Kapten, plottet. Konvojen girar, nytt ben. "
    + _base_text(d["base"]) + _leg_text(d.get("mean_leg_s")),
    "plot.convoy.base": lambda d: "Kapten, plottet. " + _base_text(d["base"])
    + _leg_text(d.get("mean_leg_s")),
}
RU_PHRASES = {
    "plot.convoy.found": lambda d: "Товарищ командир, планшет! Цели идут вместе, одним курсом. "
    "Это конвой" + (" с охранением" if d["escorts"] else "") + ".",
    "plot.convoy.turn": lambda d: "Товарищ командир, планшет. Конвой повернул, новый галс. "
    + _ru_base(d["base"]).capitalize() + _ru_leg(d.get("mean_leg_s")),
    "plot.convoy.base": lambda d: "Товарищ командир, планшет. " + _ru_base(d["base"]).capitalize()
    + _ru_leg(d.get("mean_leg_s")),
}
from .. import phrases as _phrases  # noqa: E402

_phrases.register(PHRASES)
_phrases.register_ru(RU_PHRASES)
