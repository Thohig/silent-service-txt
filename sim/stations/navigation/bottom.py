"""Havsbotten och land: djupkurvor, kortets djup framåt, ekolodet, ligga på botten,
grundvarning och landvarning."""
from __future__ import annotations

import math

import numpy as np

from ... import acoustics
from ...chart import LAYER_CONTOUR, Mark, Track
from ...entities import Transient
from ...fmt import fmt_course
from ...geo import distance, norm360
from ...ownship import PERISCOPE_DEPTH, TEST_DEPTH
from ...profile import BottomSounding
from ...reports import Quality
from ...seabed import contours
from ..base import Proposal
from .common import (
    CONTOUR_LABEL_SPOTS,
    CONTOUR_MARGIN_NM,
    LAND_CLEAR_M,
    LAND_MARK_STEP_NM,
    LAND_TURNS,
    SETTLE_DESCEND_KN,
    SETTLE_EXTRA_M,
    SETTLE_SPEED,
    SETTLE_SUGGEST_MAX_M,
    SHOAL_CHECK_S,
    SHOAL_LOOK_MIN,
    SHOAL_LOOK_MIN_NM,
    SHOAL_MARGIN_M,
    SOUNDING_TRUST_S,
)


class BottomMixin:
    """Del av NavigationStation (station.py)."""

    def _contours(self) -> list:
        """Sjökortets djupkurvor, beräknade en gång ur det gamla kortet."""
        if self._contour_items is not None:
            return self._contour_items
        items: list = []
        chart = self.game.knowledge.bathymetry
        if chart is not None:
            size, m = self.area_nm, CONTOUR_MARGIN_NM
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
        self.steer = None
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
        if sys.settle or sys.on_bottom or not self.game.knowledge.threat_held() \
                or self.own.surfaced or self._dive_forbidden_here():
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
        if self.goal == "fairway" and (p := self._fairway_point()) is not None and \
                ahead[1] > distance(self.est_x, self.est_y, *p) + 0.1:
            return True                         # landet ligger bortom girpunkten i farleden
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

    def _echo(self) -> float:
        """Ekolodet: en sensor. Lodar botten rakt under oss (hörs) och loggar lodningen."""
        world, s = self.world, self.ship
        world.emit(Transient("echosounder", s.x, s.y, s.depth,
                             acoustics.ECHO_SOUNDER_LEVEL, world.own.id, self.now))
        bottom = world.env.bottom_at(s.x, s.y)
        under = round(bottom - s.depth + self.rng.gauss(0, 2 + bottom * 0.005), -1)
        self.bottom_soundings.append(BottomSounding(self.now, s.depth + under,
                                                    self.est_x, self.est_y))
        return s.depth + under
