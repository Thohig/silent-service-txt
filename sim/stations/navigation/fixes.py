"""Fixar: periskopfix, bäringar från bryggan, stjärnfix och fix mot botten."""
from __future__ import annotations

import numpy as np

from ...events import OwnActionLogged
from ...ownship import PERISCOPE_DEPTH
from .common import (
    BFIX_GAIN,
    BFIX_INTERVAL_S,
    BFIX_MIN_SPEED,
    BFIX_N,
    BFIX_RELIEF_M_PER_NM,
    COAST_FIX_NIGHT_S,
    COAST_FIX_S,
    FIX_TIME_S,
    LANDMARK_DAY_NM,
    LANDMARK_NIGHT_NM,
    MOON_FIX_LIGHT,
    MOON_FIX_SIGMA,
    PERISCOPE_SEXTANT_F,
    STAR_FIX_S,
    STAR_FIX_SIGMA,
    STAR_SUGGEST_SIGMA,
    STAR_SUN_HIGH,
    STAR_SUN_LOW,
)
from .tasks import BottomFix as BottomFixTask
from .tasks import PositionFix, periscope_refusal
from .tasks import StarFix as StarFixTask


class FixMixin:
    """Del av NavigationStation (station.py)."""

    # --- fix mot botten -----------------------------------------------------------
    def _start_bottom_fix(self) -> None:
        s = self.ship
        reason = None
        if self.game.knowledge.bathymetry is None:
            reason = "vi har inget sjökort med djup här"
        elif "bfix" in self.tasks:
            reason = "vi lodar redan för en fix"
        elif s.speed < BFIX_MIN_SPEED and s.ordered_speed < BFIX_MIN_SPEED:
            reason = "vi måste ha minst två knop för att lodningarna ska säga något"
        elif self.own.sys.on_bottom:
            reason = "vi ligger på botten"
        if reason:
            self.say("nav.bfix.refused", {"reason": reason})
            return
        self.tasks["bfix"] = BottomFixTask(next_t=self.now)
        self.say("nav.bfix.start", {"n": BFIX_N,
                                    "minutes": round(BFIX_N * BFIX_INTERVAL_S / 60)}, kind="ack")

    def _bfix_worthwhile(self) -> bool:
        """Kan en fix mot botten hjälpa här: kort med djup, brant botten, bestick sämre än kortet."""
        chart = self.game.knowledge.bathymetry
        if chart is None or "bfix" in self.tasks or self.own.sys.on_bottom:
            return False
        sys = self.own.sys
        if sys.fire or sys.smoke > 0.2 or sys.flooding > 0:
            return False                    # annat går före
        if self.uncertainty() < BFIX_GAIN * max(chart.accuracy_nm, 0.3):
            return False                    # kortet är inte bättre än besticket
        return chart.slope(self.est_x, self.est_y) > BFIX_RELIEF_M_PER_NM

    def _bridge_bearings(self) -> bool:
        """I ytläge med folk på bryggan och land i sikte: fix med pejlskivan, inget periskop."""
        return self.own.surfaced and self.own.sys.bridge == "manned" and \
            self._land_in_sight(self.game.world.env.daylight(self.now))

    def _start_fix(self, quiet: bool = False) -> None:
        own = self.own
        day = self.game.world.env.daylight(self.now)
        if self._bridge_bearings():
            self.tasks["fix"] = PositionFix(self.now + (COAST_FIX_S if day else COAST_FIX_NIGHT_S),
                                            coast=True, quiet=quiet, bridge=True)
            if not quiet:
                self.say("nav.fix.start", {"coast": True, "day": day, "bridge": True}, kind="ack")
            return
        reason = periscope_refusal(self, "vi måste upp på periskopdjup för en fix")
        if reason:
            self.say("nav.fix.refused", {"reason": reason})
            return
        coast = self._land_in_sight(day)
        t = (COAST_FIX_S if day else COAST_FIX_NIGHT_S) if coast else FIX_TIME_S
        own.sys.periscope_until = max(own.sys.periscope_until, self.now + t)
        self.tasks["fix"] = PositionFix(self.now + t, coast=coast, quiet=quiet)
        self.game.bus.publish(OwnActionLogged(self.now, "periscope"))   # ⊙ på kortet
        self.say("nav.fix.start", {"coast": coast, "day": day}, kind="ack")

    def _star_method(self, alm=None) -> tuple[str | None, float, str]:
        """Vad himlen tillåter just nu, ur almanackan: (metod, σ, varför inte)."""
        alm = alm or self.game.knowledge.almanac
        if alm is None:
            return None, 0.0, "ingen almanacka för området"
        lt = alm.light(self.now)
        if STAR_SUN_LOW <= lt.sun_elev <= STAR_SUN_HIGH:
            return "stjärnor", STAR_FIX_SIGMA, ""
        if lt.sun_elev < STAR_SUN_LOW and lt.moon_light >= MOON_FIX_LIGHT:
            return "månen", MOON_FIX_SIGMA, ""
        if lt.sun_elev > STAR_SUN_HIGH:
            return None, 0.0, "det är för ljust för stjärnorna, de syns först i skymningen"
        return None, 0.0, "det är för mörkt, ingen horisont att mäta mot"

    def _start_star_fix(self) -> None:
        own = self.own
        method, sigma, why = self._star_method()
        bridge = own.surfaced and own.sys.bridge == "manned"
        reason = why or None
        if reason is None and not bridge:
            reason = periscope_refusal(self, "vi måste upp på periskopdjup")
        if reason:
            self.say("nav.starfix.refused", {"reason": reason})
            return
        if not bridge:
            sigma *= PERISCOPE_SEXTANT_F
            own.sys.periscope_until = max(own.sys.periscope_until, self.now + STAR_FIX_S)
            self.game.bus.publish(OwnActionLogged(self.now, "periscope"))
        self.tasks["starfix"] = StarFixTask(self.now + STAR_FIX_S, sigma, method, bridge)
        self.say("nav.starfix.start", {"method": method, "bridge": bridge}, kind="ack")

    def _star_watch(self) -> None:
        """I skymning och gryning: föreslå stjärnfix när besticket är osäkert och vi kan."""
        if "starfix" in self.tasks or "fix" in self.tasks or self.now % 60:
            return
        method, _, _ = self._star_method()
        if method != "stjärnor":
            return
        own, s = self.own, self.ship
        sigma = self.uncertainty()
        able = (own.surfaced and own.sys.bridge == "manned") or \
            (s.depth <= PERISCOPE_DEPTH and s.speed <= 7)
        if sigma > STAR_SUGGEST_SIGMA and able:
            lt = self.game.knowledge.almanac.light(self.now)
            self.suggest("starfix", "nav.suggest.starfix",
                         {"sigma": sigma, "when": "gryning" if lt.morning else "skymning"},
                         order="stjärnfix", cooldown=4 * 3600)

    def _land_in_sight(self, day: bool) -> bool:
        """Visar kortet land inom synhåll? Då tas fixen med bäringar på landmärken."""
        chart = self.game.knowledge.bathymetry
        if chart is None or not chart.has_land:
            return False
        reach = LANDMARK_DAY_NM if day else LANDMARK_NIGHT_NM
        ang = np.radians(np.arange(0, 360, 15))
        for r in np.arange(0.5, reach + 0.01, 0.5):
            if (chart.depths(self.est_x + r * np.sin(ang), self.est_y + r * np.cos(ang)) <= 0).any():
                return True
        return False
