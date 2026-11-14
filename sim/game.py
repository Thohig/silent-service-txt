"""Spelmotorn: knyter ihop sanning, sensorer, kunskap, besättning och rapporter.

Gränssnittet anropar bara:
    game.command(text)   – kaptenens order
    game.tick()          – en sekund simtid
    game.status()        – ögonblicksbild för statusraden
och prenumererar på händelser via game.bus.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import orders as O
from .crew import CrewMember, Role
from .events import (ContactDetected, ContactLost, EventBus, OrderIssued,
                     ReportDelivered, Tick, TimeScaleChanged)
from .geo import angle_diff, circular_mean, fmt_course, norm360
from .knowledge import ContactTrack, Knowledge
from .reports import Quality, Report, ReportQueue
from .scenario import Scenario
from .sonar import ClassificationUpdate, Detection, Lost, SonarStation
from .tma import BearingObs, Solution, own_maneuvered, predicted_bearing
from .truthlog import TruthLog

PLOT_INTERVAL = 30              # sekunder mellan plottlagets omräkningar
BEARING_REPORT_DELTA = 5.0      # grader innan sonar ropar ny bäring
BEARING_REPORT_MAX_AGE = 300    # annars bäringsrapport var 5:e minut
SUGGEST_COOLDOWN = 420
SUGGEST_MIN_LEG_S = 300         # rak kurs så här länge innan nytt förslag
SMOOTH_OBS = 6                  # bäringar som sonaroperatören medelvärdesbildar


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
    contacts_held: tuple[str, ...]


def nm(v: float) -> str:
    """Svensk decimal med en decimal."""
    return f"{v:.1f}".replace(".", ",")


def kn(v: float) -> str:
    return f"{v:.0f}" if abs(v - round(v)) < 0.05 else nm(v)


class Game:
    def __init__(self, scenario: Scenario, seed: int | None = None,
                 truth_log: TruthLog | None = None):
        self.rng = random.Random(seed)
        self.world = scenario.world
        self.crew: dict[Role, CrewMember] = scenario.crew
        self.start_clock = scenario.start_clock
        self.secret_order = scenario.secret_order
        self.bus = EventBus()
        self.queue = ReportQueue()
        self.knowledge = Knowledge()
        self.sonar = SonarStation(self.crew[Role.SONAR], random.Random(self.rng.random()))
        self.time_scale = 1
        self.truth_log = truth_log
        self._pending_done: dict[str, float] = {}

    # ------------------------------------------------------------------ hjälp
    @property
    def now(self) -> int:
        return self.world.time

    def own_position_estimate(self) -> tuple[float, float]:
        """Navigatörens bestick. Version 1: perfekt navigering."""
        s = self.world.own.state
        return s.x, s.y

    def _say(self, role: Role, text: str, *, kind: str = "info",
             quality: Quality | None = None, alarm: bool = False,
             extra_delay: int = 0, table=None, table_header=None) -> None:
        member = self.crew[role]
        self.queue.submit(Report(
            t_due=self.now + member.report_delay(self.rng) + extra_delay,
            speaker=member.callsign, text=text, role=role.value, quality=quality,
            alarm=alarm, kind=kind, table=table, table_header=table_header))

    def _system(self, text: str) -> None:
        r = Report(t_due=self.now, speaker="", text=text, kind="system")
        self.bus.publish(ReportDelivered(self.now, r))

    def set_time_scale(self, scale: int, reason: str = "") -> None:
        if scale != self.time_scale:
            self.time_scale = scale
            self.bus.publish(TimeScaleChanged(self.now, scale, reason))

    def _log(self, text: str) -> None:
        if self.truth_log:
            self.truth_log.note(self.now, text)

    # ------------------------------------------------------------------ order
    def command(self, text: str) -> None:
        own = self.world.own.state
        order = O.parse(text, max_speed=own.max_speed, max_depth=own.max_depth)
        self.bus.publish(OrderIssued(self.now, text, order))
        self._log(f"ORDER {text!r} -> {order}")

        match order:
            case O.SetCourse(course=c):
                own.order_course(c)
                already = own.course == own.ordered_course
                self._say(Role.NAVIGATOR,
                          f"Kurs {fmt_course(c)}, aye." + (" Vi ligger på den." if already else ""),
                          kind="ack")
                self._track_done("course", c, already)
            case O.SetSpeed(speed=v):
                own.order_speed(v)
                already = own.speed == own.ordered_speed
                txt = "Stopp i maskin, aye." if v == 0 else f"Fart {kn(v)} knop, aye."
                self._say(Role.NAVIGATOR, txt, kind="ack")
                self._track_done("speed", v, already)
            case O.SetDepth(depth=d):
                own.order_depth(d)
                already = own.depth == own.ordered_depth
                self._say(Role.NAVIGATOR, f"Djup {d} meter, aye.", kind="ack")
                self._track_done("depth", d, already)
            case O.SetTimeScale(scale=n):
                self.set_time_scale(n, "order")
            case O.QuerySolution(designation=d):
                self._answer_solution(d)
            case O.ShowPlot(designation=d):
                self._answer_plot(d)
            case O.Help():
                self._system(O.HELP_TEXT)
            case O.Unknown(reason=reason):
                msg = "Kapten?" if not reason else f"Kapten, {reason}."
                self._say(Role.NAVIGATOR, msg, kind="info")

    def _track_done(self, field: str, value: float, already: bool) -> None:
        if already:
            self._pending_done.pop(field, None)
        else:
            self._pending_done[field] = value

    # ------------------------------------------------------------------ tick
    def tick(self) -> list[Report]:
        self.world.tick(1)
        if self.truth_log:
            self.truth_log.tick(self.world)

        for ev in self.sonar.update(self.world, self.own_position_estimate()):
            self._on_sonar(ev)

        if self.now % PLOT_INTERVAL == 0:
            self._plot_team_update()

        self._check_order_completion()

        delivered = self.queue.due(self.now)
        for r in delivered:
            self.bus.publish(ReportDelivered(self.now, r))
            if r.alarm and self.time_scale > 1:
                self.set_time_scale(1, "larm")
        self.bus.publish(Tick(self.now))
        return delivered

    def _check_order_completion(self) -> None:
        s = self.world.own.state
        if "course" in self._pending_done and s.course == s.ordered_course:
            self._pending_done.pop("course")
            self._say(Role.NAVIGATOR, f"Kapten, kurs {fmt_course(s.course)} påkommen.", kind="done")
        if "speed" in self._pending_done and s.speed == s.ordered_speed:
            self._pending_done.pop("speed")
            self._say(Role.NAVIGATOR, f"Fart {kn(s.speed)} knop uppnådd.", kind="done")
        if "depth" in self._pending_done and s.depth == s.ordered_depth:
            self._pending_done.pop("depth")
            self._say(Role.NAVIGATOR, f"Djup {s.depth:.0f} meter, kapten.", kind="done")

    # ------------------------------------------------------------------ sonar
    def _on_sonar(self, ev) -> None:
        match ev:
            case Detection():
                tr = self.knowledge.on_detection(ev.designation, self.now)
                tr.classification, tr.class_quality = ev.classification, ev.quality
                tr.last_reported_bearing = ev.bearing
                tr.last_bearing_report_t = self.now
                self._log(f"DETECTION {ev}")
                self.bus.publish(ContactDetected(self.now, ev.designation))
                self._say(Role.SONAR,
                          f"Kapten, sonar! Ny kontakt i bäring {fmt_course(ev.bearing)}. "
                          f"Betecknas {ev.designation}. {ev.classification.capitalize()}.",
                          kind="contact", quality=ev.quality, alarm=True)
            case ClassificationUpdate():
                if tr := self.knowledge.tracks.get(ev.designation):
                    tr.classification, tr.class_quality = ev.classification, ev.quality
                self._say(Role.SONAR,
                          f"{ev.designation} klassas som {ev.classification}.",
                          kind="contact", quality=ev.quality)
            case Lost():
                self.knowledge.on_lost(ev.designation)
                tr = self.knowledge.tracks.get(ev.designation)
                last = f", sista bäring {fmt_course(tr.last_bearing)}" if tr and tr.last_bearing is not None else ""
                self.bus.publish(ContactLost(self.now, ev.designation))
                self._say(Role.SONAR, f"Kapten, sonar. Har tappat {ev.designation}{last}.",
                          kind="contact")
            case BearingObs():
                tr = self.knowledge.on_bearing(ev)
                if tr is not None:
                    self._maybe_report_bearing(tr, ev)

    def _maybe_report_bearing(self, tr: ContactTrack, obs: BearingObs) -> None:
        """Operatören medelvärdesbildar de senaste bäringarna innan han ropar."""
        recent = tr.observations[-SMOOTH_OBS:]
        bearing = circular_mean([o.bearing for o in recent])
        prev = tr.last_reported_bearing
        delta = angle_diff(bearing, prev) if prev is not None else 0.0
        if abs(delta) < BEARING_REPORT_DELTA and self.now - tr.last_bearing_report_t < BEARING_REPORT_MAX_AGE:
            return
        tr.last_reported_bearing = bearing
        tr.last_bearing_report_t = self.now
        se = sum(o.se for o in recent) / len(recent)
        strength = "svag" if se < 2 else "tydlig" if se < 6 else "stark"
        drift = ""
        if abs(delta) >= 2:
            drift = ", bäringen drar höger" if delta > 0 else ", bäringen drar vänster"
        self._say(Role.SONAR,
                  f"{tr.designation}, bäring {fmt_course(bearing)}, {strength} signal{drift}.",
                  kind="contact")

    # ------------------------------------------------------------------ plott
    def _plot_team_update(self) -> None:
        own = self.own_position_estimate()
        for tr in self.knowledge.tracks.values():
            if not tr.held or len(tr.observations) < 3:
                continue
            prev_q = tr.solution.quality if tr.solution else None
            sol = self.knowledge.resolve(tr.designation, self.now, own)
            if sol is None:
                continue
            self._log(f"TMA {tr.designation} r={sol.range_nm:.2f}±{sol.range_sigma:.2f} "
                      f"k={sol.course:.0f} v={sol.speed:.1f} q={sol.quality.label} n={sol.n_obs}")

            if sol.quality >= Quality.GOD and (prev_q is None or sol.quality > prev_q):
                self._say(Role.PLOT,
                          f"Kapten, plottet. Lösningen på {tr.designation} är nu "
                          f"{sol.quality.label}. {self._solution_sentence(sol)}",
                          kind="solution", quality=sol.quality)
            elif (sol.quality < Quality.GOD and sol.n_obs >= 12 and sol.span_s >= 120
                  and not self._maneuvered_recently(tr)
                  and self.now - tr.last_suggest_t >= SUGGEST_COOLDOWN):
                tr.last_suggest_t = self.now
                new_course = fmt_course(self._suggest_course(sol, tr))
                if not sol.own_maneuvered:
                    text = (f"Kapten, plottet. Lösningen på {tr.designation} är "
                            f"{sol.quality.label}, på rak kurs får vi inget avstånd. "
                            f"Föreslår kursändring till {new_course}.")
                else:
                    text = (f"Kapten, plottet. Lösningen på {tr.designation} är fortfarande "
                            f"{sol.quality.label}. Ett nytt ben skulle hjälpa. "
                            f"Föreslår kurs {new_course}.")
                self._say(Role.PLOT, text, kind="suggest", quality=sol.quality)

    def _maneuvered_recently(self, tr: ContactTrack) -> bool:
        recent = [o for o in tr.observations if o.t >= self.now - SUGGEST_MIN_LEG_S]
        return own_maneuvered(recent, threshold_deg=15.0) or "course" in self.world.own.state.changing()

    def _suggest_course(self, sol: Solution, tr: ContactTrack) -> float:
        own_course = self.world.own.state.course
        window = [o for o in tr.observations if o.t >= self.now - 1800]
        if sol.own_maneuvered and window:
            # sicksack: spegla förra giren så att nästa ben korsar tillbaka
            turn = angle_diff(own_course, window[0].own_course)
            if abs(turn) >= 20:
                return norm360(own_course - 2 * turn)
        rel = angle_diff(sol.bearing, own_course)
        # första giren: vänd bort från kontakten för att inte stänga avståndet
        return norm360(own_course - 60 if rel > 0 else own_course + 60)

    @staticmethod
    def _solution_sentence(sol: Solution) -> str:
        """Lösningen i ord. Plottlaget säger inte mer än datan bär."""
        if sol.quality >= Quality.GOD:
            rng_txt = f"avstånd {nm(sol.range_nm)} sjömil"
        else:
            lo = max(0.2, sol.range_nm - 1.5 * sol.range_sigma)
            hi = sol.range_nm + 1.5 * sol.range_sigma
            rng_txt = (f"avstånd cirka {nm(sol.range_nm)} sjömil, "
                       f"någonstans mellan {nm(lo)} och {nm(hi)}")
        if sol.course_sigma > 40 or sol.speed_sigma > 8:
            motion = "kurs och fart kan vi inte säga ännu"
        elif sol.quality >= Quality.GOD:
            motion = f"kurs {fmt_course(sol.course)}, fart {kn(round(sol.speed))} knop"
        else:
            motion = (f"kurs cirka {fmt_course(round(sol.course / 5) * 5)}, "
                      f"fart cirka {kn(round(sol.speed))} knop")
        return f"Bäring {fmt_course(sol.bearing)}, {rng_txt}, {motion}."

    def _pick_track(self, designation: str | None) -> ContactTrack | None | str:
        if designation:
            return self.knowledge.track(designation) or f"Ingen kontakt betecknad {designation}, kapten."
        held = [t for t in self.knowledge.tracks.values() if t.held] or list(self.knowledge.tracks.values())
        if not held:
            return "Vi har inga kontakter, kapten."
        if len(held) > 1:
            return "Vilken kontakt, kapten? " + ", ".join(t.designation for t in held) + "."
        return held[0]

    def _answer_solution(self, designation: str | None) -> None:
        tr = self._pick_track(designation)
        if isinstance(tr, str) or tr is None:
            self._say(Role.PLOT, tr or "Kapten?", kind="solution")
            return
        sol = self.knowledge.resolve(tr.designation, self.now, self.own_position_estimate())
        if sol is None:
            self._say(Role.PLOT, f"För få bäringar på {tr.designation} ännu, kapten.",
                      kind="solution", quality=Quality.DALIG)
            return
        basis = f"({sol.n_obs} bäringar under {sol.span_s // 60} min.)"
        if sol.quality == Quality.DALIG:
            need = ("Vi behöver mer tid på det här benet." if own_maneuvered(tr.observations)
                    else "Vi behöver ett kursbyte för att få avstånd.")
            text = (f"{tr.designation}: lösningen är dålig. Bästa gissning: "
                    f"{self._solution_sentence(sol).lower()} {need} {basis}")
        else:
            text = f"{tr.designation}: {self._solution_sentence(sol)} Kvalitet {sol.quality.label}. {basis}"
        self._say(Role.PLOT, text, kind="solution", quality=sol.quality)

    def _answer_plot(self, designation: str | None) -> None:
        tr = self._pick_track(designation)
        if isinstance(tr, str) or tr is None:
            self._say(Role.PLOT, tr or "Kapten?", kind="plot")
            return
        if not tr.observations:
            self._say(Role.PLOT, f"Inga bäringar loggade på {tr.designation}.", kind="plot")
            return
        sol = self.knowledge.resolve(tr.designation, self.now, self.own_position_estimate())
        rows = []
        for o in tr.observations[-15:]:
            row = [self.clock_str(o.t), fmt_course(o.bearing), fmt_course(o.own_course)]
            if sol is not None:
                pb = predicted_bearing(sol.state, sol.t_ref, o.t, o.own_x, o.own_y)
                row += [fmt_course(pb), f"{angle_diff(o.bearing, pb):+.1f}°".replace(".", ",")]
            else:
                row += ["–", "–"]
            rows.append(row)
        if sol is None:
            summary = f"{tr.designation}: {len(tr.observations)} bäringar, ingen lösning ännu."
            q = Quality.DALIG
        else:
            summary = (f"{tr.designation}: {len(tr.observations)} bäringar. "
                       f"Uppskattning: {self._solution_sentence(sol).lower()} "
                       f"Kvalitet {sol.quality.label}, avvikelse {nm(sol.rms_residual)}° rms.")
            q = sol.quality
        self._say(Role.PLOT, summary, kind="plot", quality=q, table=rows,
                  table_header=["Tid", "Bäring", "Egen kurs", "Lösning", "Avvikelse"])

    # ------------------------------------------------------------------ status
    def clock_str(self, sim_t: int | None = None) -> str:
        c = (self.start_clock + (self.now if sim_t is None else sim_t)) % 86400
        return f"{c // 3600:02d}:{c % 3600 // 60:02d}:{c % 60:02d}"

    def status(self) -> StatusSnapshot:
        s = self.world.own.state
        return StatusSnapshot(
            clock=(self.start_clock + self.now) % 86400, sim_time=self.now,
            course=s.course, ordered_course=s.ordered_course,
            speed=s.speed, ordered_speed=s.ordered_speed,
            depth=s.depth, ordered_depth=s.ordered_depth,
            changing=frozenset(s.changing()), time_scale=self.time_scale,
            contacts_held=tuple(self.sonar.held_designations()),
        )
