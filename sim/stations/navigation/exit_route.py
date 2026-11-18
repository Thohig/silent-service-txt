"""Vägen ut ur området: kanten, hot, grunt vatten och vägsökning på kortets rutnät."""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from ...fmt import fmt_course
from ...geo import angle_diff, bearing_to, distance
from .common import (
    EXIT_DEEP_M,
    EXIT_FIRST_SUGGEST_S,
    EXIT_RECALC_S,
    EXIT_SAMPLE_NM,
    EXIT_SHALLOW_FACTOR,
    EXIT_THREAT_PENALTY_NM,
    EXIT_THREAT_SECTOR,
    LAND_CLEAR_M,
    PATH_STEP_NM,
)


class ExitMixin:
    """Del av NavigationStation (station.py)."""

    # --- ut ur området -------------------------------------------------------------
    def _escape_line(self) -> float | None:
        sc = self.game.scenario
        return sc.escape_y_below if sc is not None else None

    def outside_area(self) -> bool:
        if (line := self._escape_line()) is not None:
            return self.est_y < line
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
        if (line := self._escape_line()) is not None:
            routes = [(180.0, y - line)]           # ordern: ut söderut förbi linjen
        return [(c, d + sigma) for c, d in routes if self._clear_path(x, y, c, d + sigma)]

    def _shallow_nm(self, x: float, y: float, course: float, dist: float) -> float:
        """Hur mycket av en rak väg som går över vatten grundare än EXIT_DEEP_M enligt kortet."""
        chart = self.game.knowledge.bathymetry
        if chart is None or dist <= 0:
            return 0.0
        n = max(1, int(dist / EXIT_SAMPLE_NM))
        ts = (np.arange(n) + 0.5) * dist / n
        sx, sy = math.sin(math.radians(course)), math.cos(math.radians(course))
        depths = chart.depths(x + ts * sx, y + ts * sy)
        return float(np.count_nonzero(depths < EXIT_DEEP_M)) * dist / n

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
            cost = d + (0.0 if clear else EXIT_THREAT_PENALTY_NM) \
                + EXIT_SHALLOW_FACTOR * self._shallow_nm(x, y, c, d)
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
