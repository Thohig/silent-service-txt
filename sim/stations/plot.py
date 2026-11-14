"""Plottlaget: målrörelseanalys, svar på läge/plot och självmant kursförslag."""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass

from ..crew import Role
from ..geo import angle_diff, norm360
from ..knowledge import ContactTrack
from ..orders import DESIG, CommandSpec, Order, desig
from ..reports import Quality
from ..tma import MANEUVER_CHI2, Solution, own_maneuvered, predicted_bearing
from .base import Station

PLOT_INTERVAL = 30              # sekunder mellan omräkningar
SUGGEST_COOLDOWN = 420
SUGGEST_MIN_LEG_S = 300         # rak kurs så här länge innan nytt förslag
TABLE_ROWS = 15


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

    # --- löpande arbete -------------------------------------------------------
    def update(self) -> None:
        if self.now % PLOT_INTERVAL:
            return
        for tr in self.game.knowledge.tracks.values():
            if not tr.held or len(tr.observations) < 3:
                continue
            prev_q = tr.solution.quality if tr.solution else None
            sol = self._resolve(tr)
            if sol is None:
                continue
            if sol.fit > MANEUVER_CHI2 and sol.n_obs >= 12:
                tr.tma_from_t = self.now - 120
                self.say("plot.maneuver", {"designation": tr.designation},
                         kind="solution", quality=Quality.DALIG, alarm=True)
                sol = self._resolve(tr)
                if sol is None:
                    continue
            self.game.log(f"TMA {tr.designation} r={sol.range_nm:.2f}±{sol.range_sigma:.2f} "
                          f"k={sol.course:.0f} v={sol.speed:.1f} q={sol.quality.label} n={sol.n_obs}")
            if sol.quality >= Quality.GOD and (prev_q is None or sol.quality > prev_q):
                self.say("plot.improved",
                         {"designation": tr.designation, "solution": solution_data(sol)},
                         kind="solution", quality=sol.quality)
            elif (sol.quality < Quality.GOD and sol.n_obs >= 12 and sol.span_s >= 120
                  and not self._maneuvered_recently(tr)
                  and self.now - self._last_suggest.get(tr.designation, -10**9) >= SUGGEST_COOLDOWN):
                self._last_suggest[tr.designation] = self.now
                course = self._suggest_course(sol, tr)
                self.suggest(f"turn{tr.designation}", "plot.suggest",
                             {"designation": tr.designation, "quality": sol.quality,
                              "course": course, "first": not sol.own_maneuvered},
                             order=f"kurs {round(course) % 360:03d}", cooldown=0,
                             quality=sol.quality)

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
