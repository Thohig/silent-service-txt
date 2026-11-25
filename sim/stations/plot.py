"""Plottlaget: målrörelseanalys, svar på läge/plot och självmant kursförslag."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import math

from ..chart import LAYER_MARK, LAYER_TRACK, Mark, Ray, Ring
from ..events import (ContactDetected, ContactLost, ConvoyAssessed, EventSighted, OwnActionLogged, OwnSoundMade,
                      ReportDelivered, SoundHeard)
from ..crew import Role
from ..fmt import count, fmt_course, minutes
from ..geo import angle_diff, norm360
from ..knowledge import ContactTrack
from ..orders import DESIG, AskContact, CommandSpec, Order, desig
from ..overview import ContactRow
from ..reports import Quality
from ..sonar_view import (KEEP_S as SONAR_KEEP_S, SONAR_SOURCES, SolutionTrace, TargetTurn,
                          bearing_drift, track_kind)
from ..tma import (MANEUVER_CHI2, MANEUVER_SPLIT, MAX_TARGET_KN, BearingObs, Solution,
                   maneuver_statistic, own_maneuvered, predicted_bearing, solve)
from ..zigzag import (ConvoyEstimate, LegFix, TrackPoint, base_course, escorts_near, groups,
                      mean_leg, merge_turns)
from .base import Proposal, Station

SOLUTION_STEP_S = 20          # sonarvyn: lösningens förutsagda bäring så här tätt
TURN_SHOW_GAP_S = 300         # sonarvyn: högst ett girmärke per kontakt på så här lång tid
TURN_NEAR_OBS_S = 120         # sonarvyn: giren märks bara om sonar hade en bäring så nära i tid
PLOT_INTERVAL = 30              # sekunder mellan omräkningar
LOOK_TURN_MIN_DEG = 20.0        # periskopets kurs så här långt från lösningens: målet har girat
LOOK_TURN_SIGMAS = 3.0
SUGGEST_COOLDOWN = 420
LEG_GAP_S = 300                 # ett benförslag (för vilken kontakt som helst) högst så här ofta
SUGGEST_MIN_LEG_S = 300         # rak kurs så här länge innan nytt förslag
TABLE_ROWS = 15
BEARING_LINE_NM = 12.0          # bäringslinjer på kortet
VECTOR_S = 360                  # fartvektor på kortet: sex minuters gång
FADE_S = 300                    # äldre bäringar ritas bleka
MANEUVER_REPEAT_S = 300         # säg "har ändrat kurs" högst så här ofta per kontakt
IMPROVED_AGAIN_S = 600          # samma kvalitet sägs inte igen inom så här lång tid (den svänger)
HUNTED_MANEUVER_REPEAT_S = 1800  # ... och så här sällan medan vi är jagade (jagaren girar hela
                                 # tiden; plot.hunter säger hur han jagar)
HUNTER_AFTER_S = 600            # jagade så länge: plottet säger vad det vet om jagarens sätt
HUNTER_LONG_S = 1500            # ... och igen när jakten hållit på så här länge
HUNTER_PING_WINDOW_S = 300      # pingtakten ur bäringarna från hans pingar så här långt bakåt
HUNTER_FAST_KN = 20             # så fort: han hör oss dåligt
HUNTER_SLOW_KN = 12             # så sakta: han lyssnar
HUNTER_PING_TIGHT_S = 10
HUNTER_PING_SPARSE_S = 20
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
PENCIL_LOST_GAP_S = 600         # samma kontakt tappad: högst ett märke så ofta
PENCIL_NAMED = ("first", "lost")   # beteckningen står alltid bredvid
PENCIL_SECTOR_DEG = 15          # okänd källa: samma märke inom sektorn
PENCIL_SYMBOL = {"ping": "P", "buoy_ping": "BP", "splash": "✕", "buoy": "B",
                 "explosion": "✱", "breakup": "↓"}
PENCIL_GAP_S = {"ping": 300, "buoy_ping": 300, "splash": 60, "buoy": 300,
                "explosion": 30, "breakup": 60}   # samma märke och källa högst så ofta
# egna handlingar som kan ha röjt oss: symbol, ord och minsta mellanrum
OWN_PENCIL = {"ping": ("!", "aktiv ping", 300), "decoy": ("≋", "skenmål", 60),
              "blow": ("▲", "nödblåsning", 300), "report": ("R", "rapport", 60),
              "periscope": ("⊙", "periskop", 300), "astern": ("◂", "omkastning", 300),
              "reload": ("¤", "omladdning", 300), "clatter": ("≡", "slammer", 300),
              "repair": ("h", "reparation", 300)}
LAYER_PENCIL = LAYER_TRACK + 0.5                 # strecken under bäringar och lösningar
LAYER_PENCIL_MARK = LAYER_MARK - 0.5             # märken på en lösning: under kontaktens märke
LAYER_FAN = LAYER_TRACK + 0.75                   # solfjädern: över blyertsen, under lösningen
FAN_LINES = 10                  # så många av benets bäringar ritas för det markerade målet
FAN_LINE_NM = 12.0


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
    word: str = ""                  # förklaring bredvid de nyaste, t.ex. "skenmål"


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
        CommandSpec(rf"{DESIG}\s*\??", lambda m: AskContact(desig(m[1])),
                    "S-1 (lösningen, solfjädern på kortet och skjutlösningen)"),
        CommandSpec(rf"(?:läge|lage|lösning|losning)(?:\s+{DESIG})?",
                    lambda m: QuerySolution(desig(m[1]))),
        CommandSpec(rf"(?:plot|plott|plotten)(?:\s+{DESIG})?",
                    lambda m: ShowPlot(desig(m[1]))),
    ]

    def __init__(self, game):
        super().__init__(game)
        self._last_suggest: dict[str, int] = {}
        self._last_leg_t = -10**9      # senaste benförslaget, för vilken kontakt som helst (LEG_GAP_S)
        self._maneuver_said: dict[str, int] = {}
        # senast sagda förbättring per kontakt: (kvalitet, tma_from_t, tid)
        self._improved_said: dict[str, tuple[Quality, int, int]] = {}
        self._hunt_since: int | None = None
        self._hunter_said: dict[str, int] = {}     # beteckning -> vad som sagts (1, 2) denna jakt
        self._look_checked: dict[str, int] = {}     # senaste periskoptitt prövad mot lösningen
        self._convoy_turn_said = -10**9
        self._convoy_quality: Quality | None = None
        self.pencil: list[PencilMark] = []
        self._pencil_last: dict[str, int] = {}
        self._first_heard: set[str] = set()
        self.marked: str | None = None      # kontakten kaptenen senast frågade om (sjökortets solfjäder)

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(SoundHeard, self._on_sound)
        bus.subscribe(OwnSoundMade, lambda e: self._on_own(e.t, e.kind))
        bus.subscribe(OwnActionLogged, lambda e: self._on_own(e.t, e.kind))
        bus.subscribe(ContactDetected, self._on_detected)
        bus.subscribe(ContactLost, self._on_lost)
        bus.subscribe(ReportDelivered, self._on_delivered)
        bus.subscribe(EventSighted, self._on_event_sighted)

    def _on_detected(self, e: ContactDetected) -> None:
        """Första gången en kontakt hörs: dess beteckning vid bäringen."""
        if e.designation in self._first_heard:
            return
        self._first_heard.add(e.designation)
        x, y = self.game.own_position_estimate()
        self.pencil.append(PencilMark(e.t, "first", "»", x, y, e.bearing, True,
                                      f"first:{e.designation}", e.designation))

    def _on_lost(self, e: ContactLost) -> None:
        """Tappad kontakt: på lösningen om plottet har en, annars vid senaste bäringen."""
        tr = self.game.knowledge.track(e.designation)
        if tr is None or tr.benign or not tr.observations:
            return
        key = f"lost:{tr.designation}"
        if e.t - self._pencil_last.get(key, -10**9) < PENCIL_LOST_GAP_S:
            return
        self._pencil_last[key] = e.t
        sol = tr.solution
        if sol is not None and sol.quality >= Quality.OSAKER:
            dt = (e.t - sol.t) / 3600.0
            x, y = sol.x + sol.state[2] * dt, sol.y + sol.state[3] * dt
            mark = PencilMark(e.t, "lost", "∅", x, y, 0.0, False, key, tr.designation)
        else:
            o = tr.observations[-1]
            mark = PencilMark(e.t, "lost", "∅", o.own_x, o.own_y, o.bearing, True, key,
                              tr.designation)
        self.pencil.append(mark)

    def _on_own(self, t: int, kind: str) -> None:
        """Egna handlingar som kan ha röjt oss, där vi trodde att vi var."""
        if kind not in OWN_PENCIL:
            return
        symbol, word, gap = OWN_PENCIL[kind]
        key = f"own:{kind}"
        if t - self._pencil_last.get(key, -10**9) < gap:
            return
        self._pencil_last[key] = t
        x, y = self.game.own_position_estimate()
        self.pencil.append(PencilMark(t, kind, symbol, x, y, 0.0, False, key, word))

    def _on_event_sighted(self, e: EventSighted) -> None:
        """Plask eller vattenpelare som utkiken såg: märket där det syntes (bäring och bedömt
        avstånd från där vi trodde att vi var), bättre än sonarens bäring."""
        symbol = "○" if e.practice else PENCIL_SYMBOL["splash" if e.kind == "splash" else "explosion"]
        kind = "splash" if e.kind == "splash" else "explosion"
        key = f"seen:{symbol}:{round(e.bearing / PENCIL_SECTOR_DEG) % (360 // PENCIL_SECTOR_DEG)}"
        if e.t - self._pencil_last.get(key, -10**9) < PENCIL_GAP_S[kind]:
            return
        self._pencil_last[key] = e.t
        ox, oy = self.game.own_position_estimate()
        b = math.radians(e.bearing)
        dx, dy = e.range_nm * math.sin(b), e.range_nm * math.cos(b)
        self.pencil.append(PencilMark(e.t, kind, symbol, ox + dx, oy + dy, 0.0, False, key))

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
        """Nyaste först, så att deras etiketter vinner där de krockar."""
        self.pencil = [m for m in self.pencil if self.now - m.t < PENCIL_KEEP_S]
        items: list = []
        n = len(self.pencil)
        for i in range(n - 1, -1, -1):
            m = self.pencil[i]
            age = self.now - m.t
            style = "pencil_new" if age < PENCIL_FRESH_S else "pencil"
            newest = i >= n - PENCIL_CLOCKS
            clock = self.game.clock_str(m.t)[:5] if newest else ""
            word = m.word if newest or m.kind in PENCIL_NAMED else ""
            faded = age >= PENCIL_FADE_S
            if m.on_bearing:            # strecket, sedan symbolen och klockslaget vid änden
                label = " ".join(p for p in (m.symbol, word, clock) if p)
                items.append(Ray(m.x, m.y, m.bearing, PENCIL_STROKE_NM, style, label,
                                 faded=faded, layer=LAYER_PENCIL))
            else:                       # symbolen på lösningen (en ruta), klockslaget bredvid
                extra = word or ("snabb" if m.symbol == "PP" and newest else m.symbol[1:])
                label = " ".join(p for p in (extra, clock) if p)
                items.append(Mark(m.x, m.y, m.symbol[0], style, label,
                                  faded=faded, layer=LAYER_PENCIL_MARK))
        return items

    # --- order ------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        match order:
            case QuerySolution(designation=d) | AskContact(designation=d):
                self._answer_solution(d)
            case ShowPlot(designation=d):
                self._answer_plot(d)

    def _pick_track(self, designation: str | None) -> ContactTrack | None:
        tr = self._find_track(designation)
        if tr is not None:
            self.marked = tr.designation
        return tr

    def _find_track(self, designation: str | None) -> ContactTrack | None:
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

    # --- sonarvyn ----------------------------------------------------------------
    def sonar_items(self) -> list:
        """Lösningens förutsagda bäringar för det nuvarande benet (från där vi trodde att vi
        var när bäringen togs) och girarna plottet märkt, vid den bäring sonar hade då."""
        items: list = []
        cutoff = self.now - SONAR_KEEP_S
        own_now = self.game.own_position_estimate()
        for tr in self.game.knowledge.tracks.values():
            obs = [o for o in tr.observations if o.t >= cutoff and o.source in SONAR_SOURCES]
            shown = -10**9
            for t in tr.turns:
                if t - shown < TURN_SHOW_GAP_S:
                    continue            # en jagare som söker girar hela tiden: ett märke räcker
                near = min(obs, key=lambda o: abs(o.t - t), default=None)
                if near is not None and t >= cutoff and abs(near.t - t) <= TURN_NEAR_OBS_S:
                    items.append(TargetTurn(t, tr.designation, near.bearing))
                    shown = t
            sol = tr.solution
            if sol is None:
                continue
            leg = [o for o in obs if o.t >= tr.tma_from_t]
            pts: list[tuple[int, float]] = []
            last = -10**9
            for o in leg:
                if o.t - last >= SOLUTION_STEP_S:
                    pts.append((o.t, predicted_bearing(sol.state, sol.t_ref, o.t, o.own_x, o.own_y)))
                    last = o.t
            if tr.held:
                pts.append((self.now, predicted_bearing(sol.state, sol.t_ref, self.now, *own_now)))
            if len(pts) >= 2:
                items.append(SolutionTrace(tr.designation, tuple(pts), sol.quality,
                                           track_kind(tr)))
        return items

    # --- sjökortet -------------------------------------------------------------
    def chart_items(self) -> list:
        """Lösningar som läge, fartvektor och avståndsosäkerhet; annars senaste bäringen.
        Därtill blyertsmärkena för det sonar hört."""
        items: list = self._pencil_items() + self._fan_items()
        for tr in self.game.knowledge.tracks.values():
            if tr.benign and "drivstation" not in tr.classification and not tr.civil:
                continue
            sol = tr.solution
            style = "merchant" if tr.civil else "contact"
            if tr.sunk:
                if self.now - tr.sunk_t <= FORGET_S and (p := self._sunk_at(tr)) is not None:
                    items.append(Mark(*p, "×", style, f"{tr.designation} sjönk "
                                      f"{self.game.clock_str(tr.sunk_t)[:5]}", faded=True))
                continue
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

    # --- översikten ---------------------------------------------------------------
    def overview_items(self) -> list:
        """Kontakttabellen: varje kontakt plottet har en bäring på (tappade i FORGET_S), med
        lösningen framräknad till nu där sjökortet visar den (≥ osäker), som på kortet."""
        rows: list = []
        own_x, own_y = self.game.own_position_estimate()
        for tr in self.game.knowledge.tracks.values():
            if tr.sunk or not tr.observations:
                continue
            o = tr.observations[-1]
            age = self.now - o.t
            if not tr.held and age > FORGET_S:
                continue
            drift = bearing_drift([(b.t, b.bearing) for b in tr.observations if b.source == "sonar"],
                                  self.now) if tr.held else None
            row = ContactRow(tr.designation, track_kind(tr), tr.classification, tr.class_quality,
                             tr.held, o.bearing, age, drift=drift)
            sol = tr.solution
            if sol is not None and sol.quality >= Quality.OSAKER and \
                    (tr.threat or tr.civil or tr.friendly):
                dt = (self.now - sol.t) / 3600.0
                x, y = sol.x + sol.state[2] * dt, sol.y + sol.state[3] * dt
                dx, dy = x - own_x, y - own_y
                row = dataclasses.replace(
                    row, bearing=norm360(math.degrees(math.atan2(dx, dy))), bearing_age_s=0,
                    range_nm=math.hypot(dx, dy), course=sol.course, speed=sol.speed,
                    quality=sol.quality)
            elif sol is not None:
                row = dataclasses.replace(row, quality=sol.quality)
            rows.append(row)
        return rows

    def _sunk_at(self, tr) -> tuple[float, float] | None:
        """Var plottet tror att kontakten sjönk: lösningen framräknad till dess, annars ingenstans."""
        sol = tr.solution or tr.leg_sol
        if sol is None:
            return None
        dt = (tr.sunk_t - sol.t) / 3600.0
        return sol.x + sol.state[2] * dt, sol.y + sol.state[3] * dt

    def _fan_items(self) -> list:
        """Solfjädern för det markerade målet: plottlagets bäringar på nuvarande ben, dragna från
        där vi trodde att vi var när de togs. Nästan parallella linjer ⇒ avståndet är osäkert;
        efter en gir korsar de varandra där målet är."""
        tr = self.game.knowledge.track(self.marked) if self.marked else None
        if tr is None or (not tr.held and tr.observations and
                          self.now - tr.observations[-1].t > FORGET_S):
            return []
        obs = [o for o in tr.observations if o.t >= tr.tma_from_t]
        if len(obs) < 2:
            return []
        step = max(1, math.ceil(len(obs) / FAN_LINES))
        picked = obs[::-1][::step][::-1]                # det nyaste alltid med
        sol = tr.solution
        out = []
        for i, o in enumerate(picked):
            length = FAN_LINE_NM
            if sol is not None and sol.quality >= Quality.OSAKER:
                dt = (o.t - sol.t) / 3600.0
                tx, ty = sol.x + sol.state[2] * dt, sol.y + sol.state[3] * dt
                length = min(FAN_LINE_NM, max(0.5, 1.4 * math.hypot(tx - o.own_x, ty - o.own_y)))
            newest = i == len(picked) - 1
            label = (f"{tr.designation}: {len(obs)} bäringar sedan {self._hhmm(obs[0].t)}"
                     if newest else "")
            out.append(Ray(o.own_x, o.own_y, o.bearing, length, "fan", label,
                           faded=not newest and self.now - o.t > FADE_S, layer=LAYER_FAN))
        return out

    def _hhmm(self, t: int) -> str:
        return self.game.clock_str(t)[:5]

    # --- löpande arbete -------------------------------------------------------
    # --- jagarens sätt (J2): bara det plottet och sonar har ------------------------------
    def _hunter_watch(self) -> None:
        k, now = self.game.knowledge, self.now
        if not k.hunted(now):
            self._hunt_since = None
            self._hunter_said = {}
            return
        if self._hunt_since is None:
            self._hunt_since = now
        dur = now - self._hunt_since
        if dur < HUNTER_AFTER_S:
            return
        stage = 2 if dur >= HUNTER_LONG_S else 1
        for tr in sorted(k.tracks.values(), key=lambda t: t.first_t):
            if not (tr.held and tr.threat and tr.warship and "jagare" in tr.classification) or \
                    self._hunter_said.get(tr.designation, 0) >= stage:
                continue
            if (found := self.hunter_data(tr, dur)) is None:
                continue
            d, q = found
            self._hunter_said[tr.designation] = stage
            self.say("plot.hunter", d, kind="solution", quality=q)

    def hunter_data(self, tr: ContactTrack, dur: int) -> tuple[dict, Quality] | None:
        """Fart ur lösningen (minst osäker), pingtakten ur bäringarna från hans pingar och hur
        länge jakten pågått. Ingen fart och ingen takt: inget att säga."""
        d: dict = {"designation": tr.designation, "minutes": dur // 60,
                   "long": dur >= HUNTER_LONG_S}
        q = Quality.SAKER
        sol = tr.solution
        if sol is not None and sol.quality >= Quality.OSAKER and self.now - sol.t <= 180:
            d["speed"] = round(sol.speed)
            q = min(q, sol.quality)
        pings = sorted(o.t for o in tr.observations
                       if o.source == "ping" and o.t >= self.now - HUNTER_PING_WINDOW_S)
        gaps = sorted(b - a for a, b in zip(pings, pings[1:]) if b > a)
        if len(gaps) >= 3:
            d["ping_s"] = gaps[len(gaps) // 2]
            q = min(q, Quality.GOD)
        if "speed" not in d and "ping_s" not in d:
            return None
        return d, q

    def update(self) -> None:
        if self.now % PLOT_INTERVAL == 0:
            self._hunter_watch()
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
                elif self.now - self._maneuver_said.get(tr.designation, -10**9) >= (
                        HUNTED_MANEUVER_REPEAT_S if self.game.knowledge.hunted(self.now)
                        else MANEUVER_REPEAT_S):
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
            said = self._improved_said.get(tr.designation)
            if said is not None and (said[1] != tr.tma_from_t or self.now - said[2] >= IMPROVED_AGAIN_S):
                said = None             # lösningen har börjat om, eller det var länge sedan
            if sol.quality >= Quality.GOD and (prev_q is None or sol.quality > prev_q) \
                    and (said is None or sol.quality > said[0]):
                self._improved_said[tr.designation] = (sol.quality, tr.tma_from_t, self.now)
                self.say("plot.improved",
                         {"designation": tr.designation, "solution": solution_data(sol)},
                         kind="solution", quality=sol.quality)
            elif (sol.quality < Quality.GOD and sol.n_obs >= 12 and sol.span_s >= 120
                  and (tr.threat or self.game.knowledge.listening)
                  and not self._maneuvered_recently(tr) and not self._convoy_sibling(tr)
                  and not self.game.knowledge.hunted(self.now) and not self.game.recalled()
                  and not self._navigator_steers()
                  and self.now - self._last_suggest.get(tr.designation, -10**9) >= SUGGEST_COOLDOWN
                  and self.now - self._last_leg_t >= LEG_GAP_S):
                self._last_suggest[tr.designation] = self.now
                course = self._suggest_course(sol, tr)
                if course is None:
                    continue
                self._last_leg_t = self.now     # ett nytt ben ger avstånd på alla bäringar
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

    def _on_delivered(self, e: ReportDelivered) -> None:
        """Ett benförslag har getts (också på vakthavandes initiativ): nästa först efter LEG_GAP_S."""
        if e.report.type == "plot.suggest":
            self._last_leg_t = e.t

    def idle_proposals(self) -> list[Proposal]:
        out = []
        if self.game.knowledge.hunted(self.now) or self.game.recalled() or \
                self.now - self._last_leg_t < LEG_GAP_S:
            return out          # jagade eller hemkallade: kursen behövs för att komma ut, inte för TMA
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            if not (tr.threat or tr.held and tr.friendly and self.game.knowledge.listening) \
                    or sol is None or sol.quality >= Quality.GOD:
                continue
            if self._maneuvered_recently(tr) or self._navigator_steers():
                continue
            course = self._suggest_course(sol, tr)
            if course is None:
                continue
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
                or "course" in self.own.state.changing())

    def _navigator_steers(self) -> bool:
        """Styr navigatören (anfall, följa, farleden, vaken)? Då föreslår plottet inget nytt ben: det
        avbröt anfallet, och navigatören föreslog det igen (krig-kort frö 51, tre gånger)."""
        from .navigation import NavigationStation
        try:
            nav = self.game.station(NavigationStation)
        except KeyError:
            return False
        return nav.steer is not None or nav.vak is not None

    def _suggest_course(self, sol: Solution, tr: ContactTrack) -> float | None:
        """Nästa ben. Navigatören säger om kortet har land åt det hållet; då giren åt andra
        hållet, och går ingen av dem föreslår plottet inget."""
        own_course = self.own.state.course
        window = [o for o in tr.observations if o.t >= self.now - 1800]
        turn = None
        if sol.own_maneuvered and window:
            # sicksack: spegla förra giren så att nästa ben korsar tillbaka
            t = angle_diff(own_course, window[0].own_course)
            if abs(t) >= 20:
                turn = -2 * t
        if turn is None:
            # första giren: vänd bort från kontakten för att inte stänga avståndet
            turn = -60 if angle_diff(sol.bearing, own_course) > 0 else 60
        from .navigation import NavigationStation
        nav = next((st for st in self.game.stations if isinstance(st, NavigationStation)), None)
        for c in (norm360(own_course + turn), norm360(own_course - turn)):
            if nav is None or nav.course_safe(c):
                return c
        return None


def _base_data(c: ConvoyEstimate) -> dict | None:
    b = c.base
    if b is None:
        return None
    return {"course": b.course, "speed": b.speed, "quality": b.quality, "legs": b.legs}


def _leg_text(s: int | None) -> str:
    return f" Sicksack, ben på ungefär {minutes(round(s / 60))}." if s else ""


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


def _hunter(d: dict) -> str:
    out = [f"Kapten, plottet. Om jagaren {d['designation']}:"]
    v = d.get("speed")
    if v is not None:
        if v >= HUNTER_FAST_KN:
            out.append(f"han går fort, cirka {v} knop. I den farten hör han oss dåligt.")
        elif v <= HUNTER_SLOW_KN:
            out.append(f"han går sakta, cirka {v} knop, och lyssnar. Håll tyst.")
        else:
            out.append(f"han går cirka {v} knop.")
    p = d.get("ping_s")
    if p is not None:
        word = "tätt" if p <= HUNTER_PING_TIGHT_S else "glest" if p >= HUNTER_PING_SPARSE_S else "jämnt"
        out.append(f"Han pingar {word}, var {p}:e sekund.")
    if d.get("long"):
        out.append(f"Han har jagat oss i {minutes(d['minutes'])} och ger inte upp.")
    return " ".join(out)


def _ru_hunter(d: dict) -> str:
    from .. import russian as R
    out = [f"Товарищ командир, планшет. {R.contact(d['designation']).capitalize()}:"]
    if d.get("speed") is not None:
        out.append(f"ход около {R.count(d['speed'], R.KNOT)}.")
    if d.get("ping_s") is not None:
        out.append(f"Посылки через {R.count(d['ping_s'], R.SECOND)}.")
    if d.get("long"):
        out.append(f"Преследует нас {R.count(d['minutes'], R.MINUTE)}, не отстаёт.")
    return " ".join(out)


PHRASES = {
    "plot.hunter": _hunter,
    "plot.convoy.found": lambda d: (
        f"Kapten, plottet! {', '.join(d['members'])} går tillsammans, samma kurs och fart. "
        f"Det är en konvoj" + (f" med {count(d['escorts'], 'jagare', 'jagare', neuter=False)} som eskort" if d["escorts"] else "")
        + f". Just nu kurs {fmt_course(d['course'])}, {d['speed']:.0f} knop."),
    "plot.convoy.turn": lambda d: "Kapten, plottet. Konvojen girar, nytt ben. "
    + _base_text(d["base"]) + _leg_text(d.get("mean_leg_s")),
    "plot.convoy.base": lambda d: "Kapten, plottet. " + _base_text(d["base"])
    + _leg_text(d.get("mean_leg_s")),
}
RU_PHRASES = {
    "plot.hunter": _ru_hunter,
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
