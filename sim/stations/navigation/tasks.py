"""Navigatörens pågående uppdrag: fix i periskopet eller med bäringar från bryggan,
stjärnfix och fix mot botten.

Varje uppdrag är ett `NavTask` med två frågor: `abort` (ska det avbrytas nu, och vad säger
navigatören då) och `step` (ett steg; sant när det är klart). NavigationStation håller dem
i `tasks` per namn och kör dem på deras platser i `update` med `_run_task`, som tar bort
uppdraget före steget, så att det som sägs under steget ser att det är över.

Nytt uppdrag: en klass här med `name`, starta det med `nav.tasks[name] = …`. Avbrotten
skrivs i uppdraget, inte i update, så att ett nytt sätt att börja (bryggan, periskopet)
inte glömmer hur det slutar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from ...geo import bearing_to, distance
from ...ice import masts_clear
from ...ownship import PERISCOPE_DEPTH
from ...reports import Quality
from ...seabed import match_soundings
from .common import (
    BFIX_FLAT,
    BFIX_INTERVAL_S,
    BFIX_N,
    BRIDGE_FIX_QUIET_NM,
    COAST_FIX_SIGMA,
    PERISCOPE_FIX_SIGMA,
)

if TYPE_CHECKING:
    from .station import NavigationStation

Abort = tuple[str, dict]            # (rapporttyp, data) när uppdraget avbryts


class NavTask:
    name: ClassVar[str] = ""

    def abort(self, nav: NavigationStation) -> Abort | None:
        """Skäl att avbryta nu, annars None."""
        return None

    def step(self, nav: NavigationStation) -> bool:
        """Ett steg. Sant när uppdraget är klart."""
        return False


@dataclass
class PositionFix(NavTask):
    """Fix i periskopet (bäringar och avstånd) eller med pejlskivan från bryggan."""
    name: ClassVar[str] = "fix"
    done_t: int
    coast: bool                     # landmärken: snabbare och bättre
    quiet: bool = False             # navigatörens egen pejling från bryggan

    def abort(self, nav: NavigationStation) -> Abort | None:
        return ("nav.fix.aborted", {}) if nav.ship.depth > PERISCOPE_DEPTH + 1 else None

    def step(self, nav: NavigationStation) -> bool:
        if nav.now < self.done_t:
            return False
        s, rng = nav.ship, nav.game.rng
        e = COAST_FIX_SIGMA if self.coast else 0.08
        new_x, new_y = s.x + rng.gauss(0, e), s.y + rng.gauss(0, e)
        err = distance(nav.est_x, nav.est_y, new_x, new_y)
        b = bearing_to(nav.est_x, nav.est_y, new_x, new_y)
        nav._apply_fix(new_x, new_y, COAST_FIX_SIGMA if self.coast else PERISCOPE_FIX_SIGMA)
        if not self.quiet or err >= BRIDGE_FIX_QUIET_NM:
            nav.say("nav.fix.done", {"error": err, "bearing": b})
        return True


@dataclass
class StarFix(NavTask):
    """Stjärnor (eller månen) mot horisonten med sextanten, på bryggan eller i periskopet."""
    name: ClassVar[str] = "starfix"
    done_t: int
    sigma: float
    method: str
    bridge: bool                    # sextanten på bryggan, annars periskopsextanten

    def abort(self, nav: NavigationStation) -> Abort | None:
        gone = nav.own.sys.bridge != "manned" if self.bridge \
            else nav.ship.depth > PERISCOPE_DEPTH + 1
        return ("nav.starfix.aborted", {"bridge": self.bridge}) if gone else None

    def step(self, nav: NavigationStation) -> bool:
        if nav.now < self.done_t:
            return False
        s, rng, sigma = nav.ship, nav.game.rng, self.sigma
        new_x, new_y = s.x + rng.gauss(0, sigma), s.y + rng.gauss(0, sigma)
        err = distance(nav.est_x, nav.est_y, new_x, new_y)
        b = bearing_to(nav.est_x, nav.est_y, new_x, new_y)
        nav._apply_fix(new_x, new_y, sigma)
        q = Quality.SAKER if sigma < 0.1 else Quality.GOD
        nav.say("nav.starfix.done", {"error": err, "bearing": b, "sigma": sigma}, quality=q)
        return True


@dataclass
class BottomFix(NavTask):
    """Fix mot botten: BFIX_N lodningar med BFIX_INTERVAL_S mellan, matchade mot sjökortet."""
    name: ClassVar[str] = "bfix"
    next_t: int
    series: list[tuple[float, float, float]] = field(default_factory=list)   # (x, y, djup)

    def abort(self, nav: NavigationStation) -> Abort | None:
        if nav.now >= self.next_t and nav.ship.speed < 1.0:
            return ("nav.bfix.aborted", {})
        return None

    def step(self, nav: NavigationStation) -> bool:
        if nav.now < self.next_t:
            return False
        self.series.append((nav.est_x, nav.est_y, nav._echo()))
        self.next_t = nav.now + BFIX_INTERVAL_S
        if len(self.series) < BFIX_N:
            return False
        self._match(nav, self.series)
        return True

    @staticmethod
    def _match(nav: NavigationStation, series: list[tuple[float, float, float]]) -> None:
        chart = nav.game.knowledge.bathymetry
        # lodningarna i besticket som det var då, flyttade till där vi tror att vi är nu
        cx, cy, _ = series[-1]
        pts = [(x - cx + nav.est_x, y - cy + nav.est_y) for x, y, _ in series]
        prior = nav.uncertainty()
        m = match_soundings(chart, pts, [d for *_, d in series], prior)
        sigma = math.hypot(m.sigma, chart.accuracy_nm)
        if not m.consistent:
            depths = [d for *_, d in series]
            here = [chart.depth_at(x, y) for x, y in pts]
            how = "grundare" if sum(depths) < sum(here) else "djupare"
            nav.say("nav.bfix.mismatch", {"how": how}, quality=Quality.DALIG)
            return
        if m.sigma > BFIX_FLAT * prior:
            nav.say("nav.bfix.flat", quality=Quality.DALIG)
            return
        if sigma >= prior * 0.95:
            nav.say("nav.bfix.chart", {"accuracy": chart.accuracy_nm}, quality=Quality.DALIG)
            return
        new_x, new_y = nav.est_x + m.dx, nav.est_y + m.dy
        err = math.hypot(m.dx, m.dy)
        b = bearing_to(nav.est_x, nav.est_y, new_x, new_y)
        nav._apply_fix(new_x, new_y, sigma)
        q = (Quality.SAKER if sigma < 0.15 else Quality.GOD if sigma < 0.3
             else Quality.OSAKER if sigma < 0.6 else Quality.DALIG)
        if m.line_of_position:
            nav.say("nav.bfix.line", {"error": err, "bearing_corr": b, "sigma": sigma,
                                      "bearing": m.minor_bearing,
                                      "minor": math.hypot(m.sigma_minor, chart.accuracy_nm)},
                    quality=q)
            return
        nav.say("nav.bfix.done", {"error": err, "bearing": b, "sigma": sigma}, quality=q)


def periscope_refusal(nav: NavigationStation, too_deep: str) -> str | None:
    """Varför periskopet inte kan användas för en fix just nu, annars None."""
    own, s = nav.own, nav.ship
    if s.depth > PERISCOPE_DEPTH:
        return too_deep
    if s.speed > 7:
        return "farten är för hög för periskopet"
    if own.sys.health["periscope"] < 0.3:
        return "periskopet är skadat"
    if not masts_clear(nav.game.world):
        return "det är is ovanför, periskopet kommer inte upp"
    return None
