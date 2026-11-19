"""Navigatörens pågående uppdrag: fix i periskopet eller med bäringar från bryggan,
stjärnfix och fix mot botten, och styruppdragen (följ, anfall, väntläget, farleden,
drivstationen).

Varje uppdrag är ett `NavTask` med två frågor: `abort` (ska det avbrytas nu, och vad säger
navigatören då) och `step` (ett steg; sant när det är klart). NavigationStation håller dem
i `tasks` per namn och kör dem på deras platser i `update` med `_run_task`, som tar bort
uppdraget före steget, så att det som sägs under steget ser att det är över.

Nytt uppdrag: en klass här med `name`, starta det med `nav.tasks[name] = …`. Avbrotten
skrivs i uppdraget, inte i update, så att ett nytt sätt att börja (bryggan, periskopet)
inte glömmer hur det slutar.

Styruppdragen (`Steering`) är ett i taget: `nav.steer`, och `nav.goal` är dess namn. Varje
uppdrag bär sitt eget tillstånd (kontakten, beräknad ankomst, farledens nästa punkt, sökcirkeln)
och sitt steg (`step`, metoderna i steering.py och ice.py). Kaptenens `kurs` avbryter vilket det
än är (station.py, on_order); ett steg som slutar sätter `nav.steer = None` där det säger varför.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from ...geo import bearing_to, distance
from ...ownship import PERISCOPE_DEPTH
from ...reports import Quality
from ...seabed import match_soundings
from .common import (
    ATTACK_STEP_S,
    BFIX_FLAT,
    BFIX_INTERVAL_S,
    BFIX_N,
    BRIDGE_FIX_QUIET_NM,
    COAST_FIX_SIGMA,
    FAIRWAY_STEP_S,
    FOLLOW_STEP_S,
    PERISCOPE_FIX_SIGMA,
    WAIT_STEP_S,
)

if TYPE_CHECKING:
    from .station import NavigationStation

Abort = tuple[str, dict]            # (rapporttyp, data) när uppdraget avbryts; tom typ: tyst


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
    bridge: bool = False            # pejlskivan på bryggan, inte periskopet
    sigma: float | None = None      # fyrarna på natten: fixens osäkerhet (annars efter coast)

    def abort(self, nav: NavigationStation) -> Abort | None:
        gone = nav.own.sys.bridge != "manned" if self.bridge \
            else nav.ship.depth > PERISCOPE_DEPTH + 1
        if not gone:
            return None
        # navigatörens egen pejling, som aldrig sagts: avbryts lika tyst
        return ("", {}) if self.quiet else ("nav.fix.aborted", {"bridge": self.bridge})

    def step(self, nav: NavigationStation) -> bool:
        if nav.now < self.done_t:
            return False
        s, rng = nav.ship, nav.rng
        e = self.sigma if self.sigma is not None else COAST_FIX_SIGMA if self.coast else 0.08
        new_x, new_y = s.x + rng.gauss(0, e), s.y + rng.gauss(0, e)
        err = distance(nav.est_x, nav.est_y, new_x, new_y)
        b = bearing_to(nav.est_x, nav.est_y, new_x, new_y)
        nav._apply_fix(new_x, new_y, self.sigma if self.sigma is not None else
                       COAST_FIX_SIGMA if self.coast else PERISCOPE_FIX_SIGMA)
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
        s, rng, sigma = nav.ship, nav.rng, self.sigma
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
    if not nav.masts_free:
        return "det är is ovanför, periskopet kommer inte upp"
    return None


# --- styruppdragen ------------------------------------------------------------------
class Steering:
    """Ett styruppdrag: navigatören styr (och ibland håller farten) tills det är klart."""
    goal: ClassVar[str] = ""
    STEP_S: ClassVar[int] = 1           # steg så här ofta (simtid delbar med STEP_S)

    def step(self, nav: NavigationStation) -> None:
        raise NotImplementedError


@dataclass
class Follow(Steering):
    """`följ S-x`: styr på kontaktens bäring, håll plottets fart tills kaptenen sätter farten."""
    goal: ClassVar[str] = "follow"
    STEP_S: ClassVar[int] = FOLLOW_STEP_S
    designation: str
    hold_speed: bool = True

    def step(self, nav: NavigationStation) -> None:
        nav._follow_step(self)


@dataclass
class Attack(Steering):
    """`anfall S-x`: till skjutläget vid sidan av målets väg (firecontrol.approach)."""
    goal: ClassVar[str] = "attack"
    STEP_S: ClassVar[int] = ATTACK_STEP_S
    designation: str
    eta_t: int | None = None            # beräknad ankomst till skjutläget (simtid)
    behind: int = 0                     # så många steg i rad bakom målet

    def step(self, nav: NavigationStation) -> None:
        nav._attack_step(self)


@dataclass
class Wait(Steering):
    """`väntläget`: dit utanför grinden och håll läget mot tidvattnet."""
    goal: ClassVar[str] = "wait"
    STEP_S: ClassVar[int] = WAIT_STEP_S
    arrived: bool = False

    def step(self, nav: NavigationStation) -> None:
        nav._wait_step(self)


@dataclass
class Fairway(Steering):
    """`farleden`: längs sjökortets farled, till styrbord om mitten."""
    goal: ClassVar[str] = "fairway"
    STEP_S: ClassVar[int] = FAIRWAY_STEP_S
    index: int = 0                      # nästa punkt

    def step(self, nav: NavigationStation) -> None:
        nav._fairway_step(self)


@dataclass
class Station(Steering):
    """`drivstationen`: mot Nord-7 på sonar eller huvudstabens läge; nära: sökspiral runt den."""
    STEP_S: ClassVar[int] = 1
    source: str = ""                    # "sonar" eller "wp"
    circle: tuple[float, float] | None = None    # sökspiralens mitt (beräknad), när vi söker
    circle_t: int = 0

    @property
    def goal(self) -> str:              # type: ignore[override]
        return "circle" if self.circle is not None else "station"

    def step(self, nav: NavigationStation) -> None:
        nav._steer_to_station(self)

