"""Havsbotten och land: djupkurvor, kortets djup framåt, ekolodet, ligga på botten,
grundvarning och landvarning."""
from __future__ import annotations

import math

import numpy as np

from ... import acoustics
from ...chart import LAYER_CONTOUR, Mark, Track
from ...entities import Transient
from ...fmt import fmt_course
from ...geo import angle_diff, distance, norm360
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
    LAND_SAFE_NM,
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
    UNSTICK_AHEAD_KN,
    UNSTICK_CLEAR_S,
    UNSTICK_KN,
    UNSTICK_WINDOW_S,
    WATER_LOOK_NM,
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
        """Grundaste kortdjup framåt längs kursen (akterut när vi backar), med bestickets
        osäkerhet åt sidorna och framåt (vi kan vara längre fram än besticket säger; utan den gick
        ja-boten i Clyde på grund mot en brant strand 0,25 nm från besticket): (djup, avstånd nm).
        None om kortet saknar djup."""
        chart = self.game.knowledge.bathymetry
        if chart is None:
            return None
        s, sigma = self.ship, self.uncertainty()
        reach = max(SHOAL_LOOK_MIN_NM, s.speed * SHOAL_LOOK_MIN / 60) + sigma
        dist = np.arange(0.0, reach + 0.05, 0.1)
        side = np.array([-sigma, 0.0, sigma])
        b = math.radians(s.track if course is None else course)
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
        depth = chart.depth_at(self.est_x, self.est_y)
        if depth <= self.ship.depth + 5:
            return None         # kortet visar land eller grundare än vi går: kortet eller besticket har fel
        return depth, kind, False

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
        k = self.game.knowledge
        if sys.settle or sys.on_bottom or not k.threat_held() \
                or self.own.surfaced or self._dive_forbidden_here():
            return None
        if "inspelning" in k.order_tasks and not k.hunted(self.now):
            return None                 # vi ska höra målet, inte gömma oss för det
        if self.game.recalled() and not k.hunted(self.now):
            return None                 # hemkallade: vi ska ut, inte ligga still
        if not k.hunted(self.now) and self._radio_window_pending():
            return None                 # radion ska upp och ta emot: lägg oss inte på botten nu
        if k.charged_close(self.now):
            return None                 # de bombar redan där vi är: botten gömmer oss inte nu
        here = self.bottom_here()
        if here is None or here[1] is None or here[1] == "klippa" or here[0] > SETTLE_SUGGEST_MAX_M:
            return None
        return Proposal(2, "settle", "nav.suggest.settle", "botten",
                        {"depth": round(here[0], -1), "kind": here[1]},
                        quality=self._shoal_quality(), cooldown=1200)

    def _radio_window_pending(self) -> bool:
        """Väntar eller pågår ett sambandstillfälle som radion inte klarat av (eget instrument:
        radions schema)?"""
        from ..radio import RadioStation
        try:
            radio = self.game.station(RadioStation)
        except KeyError:
            return False
        return radio.window_pending() is not None

    def _unstick_watch(self) -> None:
        """Fast mot land eller stoppade tvärt mot en isvägg: föreslå att gå loss åt andra
        hållet, sakta (back om fören tog i, framåt om aktern gjorde det). Efter en grundstötning
        behövs det inte: båten lyfts upp från botten och kommer loss av sig själv."""
        s, sys = self.ship, self.own.sys
        if sys.settle or sys.on_bottom or self.now % 5:
            return
        stop = sys.hull_stop
        if s.astern and stop is not None and not stop[1] and stop[2] != "bottom" and \
                not sys.bottom_contact and \
                UNSTICK_CLEAR_S <= self.now - stop[0] <= 3 * UNSTICK_CLEAR_S:
            # backat loss: fören är fri, gå framåt bort från grundet (en gir i fart framåt)
            c = self._away_course()
            self.suggest("unstuck", "nav.suggest.unstuck", {"course": c, "speed": UNSTICK_AHEAD_KN},
                         order=f"kurs {fmt_course(c)}, fart {UNSTICK_AHEAD_KN:.0f}", cooldown=900)
            return
        if s.speed > 0.3:
            return
        pressed = sys.bottom_contact and s.ordered_speed > 0
        recent = stop is not None and stop[2] == "ice" and self.now - stop[0] <= UNSTICK_WINDOW_S \
            and s.ordered_speed == 0
        if not (pressed or recent):
            return
        stern = s.ordered_astern if pressed else stop[1]
        order = f"fart {UNSTICK_KN:.0f}" if stern else f"back {UNSTICK_KN:.0f}"
        self.suggest("unstick", "nav.suggest.unstick",
                     {"stern": stern, "speed": UNSTICK_KN, "ice": not pressed and self.under_ice()},
                     order=order, cooldown=300)

    def _away_course(self) -> float:
        """Kursen bort från grundet: den med djupast vatten framåt på kortet, annars motsatt."""
        s = self.ship
        options = [(c, self.chart_ahead(c)) for c in
                   (norm360(s.course + sgn * a) for a in LAND_TURNS for sgn in (1, -1))]
        options = [(c, a[0]) for c, a in options if a is not None]
        if not options:
            return norm360(s.course + 180)
        return max(options, key=lambda o: o[1])[0]

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
                     {"shoal": round(shoal, -1), "dist": dist, "depth": limit, "sounded": sounded,
                      **({"astern": True} if s.astern else {})},
                     order=f"djup {limit:.0f}", cooldown=300,
                     quality=Quality.SAKER if sounded else self._shoal_quality(),
                     alarm=minutes < 3)

    def water_dist(self, course: float) -> float:
        """Avstånd (nm) längs kursen tills kortet visar vatten nog för periskopdjup; inf om inte
        inom WATER_LOOK_NM. Används när kortet visar land där besticket står."""
        chart = self.game.knowledge.bathymetry
        if chart is None:
            return math.inf
        b = math.radians(course)
        dist = np.arange(0.0, WATER_LOOK_NM + 0.01, 0.02)
        z = chart.depths(self.est_x + dist * math.sin(b), self.est_y + dist * math.cos(b))
        ok = np.nonzero(z >= LAND_CLEAR_M)[0]
        return float(dist[ok[0]]) if len(ok) else math.inf

    def on_chart_land(self) -> bool:
        """Visar kortet land där besticket står? Vi flyter, så kortet (eller besticket) är fel."""
        chart = self.game.knowledge.bathymetry
        return chart is not None and chart.depth_at(self.est_x, self.est_y) <= 0

    def course_safe(self, course: float) -> bool:
        """Går kursen bort från kortets land? För andra stationers kursförslag (plottets ben)."""
        if self.game.knowledge.bathymetry is None:
            return True
        if self.on_chart_land():
            best = min(self.water_dist(c) for c in range(0, 360, 15))
            return self.water_dist(course) <= best + 0.1
        ahead = self.chart_ahead(course)
        return ahead is None or ahead[0] >= LAND_CLEAR_M or ahead[1] >= LAND_SAFE_NM

    def _land_watch(self) -> bool:
        """Land eller vatten för grunt även på periskopdjup framåt: föreslå en gir."""
        s = self.ship
        if s.speed < 0.5:
            return False
        if self.on_chart_land():
            # kortet ligger fel här (strandlinjen är förskjuten): närmaste vatten på kortet
            dists = [(self.water_dist(c), c) for c in range(0, 360, 15)]
            d, c = min(dists)
            if d == math.inf or abs(angle_diff(c, s.course)) < 20 and \
                    self.water_dist(s.course) <= d + 0.1:
                return True
            self.suggest("chart_land", "nav.suggest.chart_land", {"course": c, "dist": d},
                         order=f"kurs {fmt_course(c)}", cooldown=300,
                         quality=self._shoal_quality(), alarm=True)
            return True
        ahead = self.chart_ahead()
        if ahead is None or ahead[0] >= LAND_CLEAR_M:
            return False
        if s.astern:
            # vi backar mot land: en gir hjälper inte (rodret tar dåligt), stoppa
            minutes = ahead[1] * 60 / max(s.speed, 0.5)
            self.suggest("land_astern", "nav.suggest.land_astern",
                         {"shoal": ahead[0], "dist": ahead[1]}, order="stopp", cooldown=120,
                         quality=self._shoal_quality(), alarm=minutes < 4)
            return True
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
