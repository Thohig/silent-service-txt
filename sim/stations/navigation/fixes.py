"""Fixar: periskopfix, bäringar från bryggan, stjärnfix och fix mot botten."""
from __future__ import annotations

import numpy as np

from ...environment import CLOUD_STARS
from ...events import OwnActionLogged
from ...ownship import PERISCOPE_DEPTH
from ...seabed import light_visible
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
    LIGHTS_FIX_SIGMA,
    ONE_LIGHT_FIX_SIGMA,
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

    # --- `fix`: navigatören väljer -------------------------------------------------
    def _start_any_fix(self) -> None:
        """`fix`: bryggan eller periskopet (landmärken om land syns) när vi är uppe eller kan
        komma upp; djupt nere fix mot botten om kortet har djup och botten är brant nog,
        annars säger han att vi måste upp."""
        s = self.ship
        deep = s.depth > PERISCOPE_DEPTH + 1 and not self.own.surfaced
        if deep and self._bfix_possible():
            self._start_bottom_fix()
        else:
            self._start_fix()

    def _bfix_possible(self) -> bool:
        """Kan en fix mot botten säga något här (kort med djup, brant botten, inte på botten)?"""
        chart = self.game.knowledge.bathymetry
        return chart is not None and not self.own.sys.on_bottom and \
            chart.slope(self.est_x, self.est_y) > BFIX_RELIEF_M_PER_NM

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
        if chart is None or "bfix" in self.tasks or self.own.sys.on_bottom or self.own.sys.settle:
            return False
        st = self.own.state
        if st.speed < BFIX_MIN_SPEED and st.ordered_speed < BFIX_MIN_SPEED:
            return False                    # nekas ändå (kuba frö 16: föreslagen på väg ned mot botten)
        sys = self.own.sys
        if sys.fire or sys.smoke > 0.2 or sys.flooding > 0:
            return False                    # annat går före
        if self.uncertainty() < BFIX_GAIN * max(chart.accuracy_nm, 0.3):
            return False                    # kortet är inte bättre än besticket
        return chart.slope(self.est_x, self.est_y) > BFIX_RELIEF_M_PER_NM

    def _bridge_bearings(self) -> bool:
        """I ytläge med folk på bryggan och land i sikte: fix med pejlskivan, inget periskop."""
        return self.own.surfaced and self.own.sys.bridge == "manned" and \
            self._land_in_sight(self.world.env.daylight(self.now))

    def _start_fix(self, quiet: bool = False) -> None:
        own = self.own
        day = self.world.env.daylight(self.now)
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
        if self.game.knowledge.lights and not day:
            self._start_light_fix()
            return
        coast = self._land_in_sight(day)
        t = (COAST_FIX_S if day else COAST_FIX_NIGHT_S) if coast else FIX_TIME_S
        own.sys.periscope_until = max(own.sys.periscope_until, self.now + t)
        self.tasks["fix"] = PositionFix(self.now + t, coast=coast, quiet=quiet)
        self.game.bus.publish(OwnActionLogged(self.now, "periscope"))   # ⊙ på kortet
        self.say("nav.fix.start", {"coast": coast, "day": day}, kind="ack")

    def visible_lights(self) -> list:
        """Fyrarna i fyrlistan som syns i periskopet just nu (lysvidd, land emellan). Sensor:
        utkiken ser dem eller inte; vilken fyr det är säger karaktären (fyrlistan)."""
        env = self.world.env
        o = self.own.state
        lit = {l.name for l in env.lights}
        return [l for l in self.game.knowledge.lights if l.name in lit and
                light_visible(env.seabed, l, o.x, o.y)]

    def lights_expected(self) -> bool | None:
        """Natt och fyrlista: borde någon fyr synas från besticket enligt kortet? None när det
        inte gäller (dag, ingen fyrlista)."""
        k = self.game.knowledge
        if not k.lights or k.bathymetry is None or self.world.env.daylight(self.now):
            return None
        return any(light_visible(k.bathymetry, l, self.est_x, self.est_y) for l in k.lights)

    def _start_light_fix(self) -> None:
        """Natt med fyrlista: korsbäring på två fyrar, en fyr ger bäring och avstånd sämre, ingen
        fyr i sikte ingen fix (stjärnor och måne är stjärnfixens sak)."""
        own = self.own
        seen = self.visible_lights()
        if not seen:
            self.say("nav.fix.refused", {"reason": "inga fyrar syns härifrån, land skymmer eller "
                                                   "de är för långt bort", "why": "no_lights"})
            return
        sigma = LIGHTS_FIX_SIGMA if len(seen) >= 2 else ONE_LIGHT_FIX_SIGMA
        own.sys.periscope_until = max(own.sys.periscope_until, self.now + COAST_FIX_NIGHT_S)
        self.tasks["fix"] = PositionFix(self.now + COAST_FIX_NIGHT_S, coast=True, sigma=sigma)
        self.game.bus.publish(OwnActionLogged(self.now, "periscope"))
        self.say("nav.fix.start", {"coast": True, "day": False,
                                   "lights": [l.name for l in seen[:3]]}, kind="ack")

    def _star_method(self, alm=None) -> tuple[str | None, float, str]:
        """Vad himlen tillåter just nu, ur almanackan: (metod, σ, varför inte). Moln (sett
        uppåt i periskopet) stänger stjärnor och måne."""
        alm = alm or self.game.knowledge.almanac
        if alm is None:
            return None, 0.0, "ingen almanacka för området"
        if self.world.env.cloud_at(self.now) >= CLOUD_STARS:
            return None, 0.0, "molnen täcker himlen"
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
