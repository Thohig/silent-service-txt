"""Under isen: isekolodet, öppningarna (vak) och drivstationen Nord-7."""
from __future__ import annotations

import math

from ...events import IceSounded, OpeningNotFound
from ...geo import NM_IN_M, angle_diff, bearing_to, distance, norm360
from ...icemap import (
    BREAKABLE_M,
    HULL_HALF_M,
    MIN_SURFACE_LEN_M,
    OPEN_M,
    IceMap,
    IceSoundingObs,
    Opening,
    describe_opening,
    round_m,
    thickness_words,
)
from ...ownship import ANTENNA_DEPTH, PERISCOPE_DEPTH
from .common import (
    DECEL_M_PER_S2,
    ICE_FIX_SIGMA_NM,
    JUST_PASSED_S,
    VAK_CENTRED_M,
    REPORT_OPENING_M,
    SAFE_ICE_DEPTH,
    SOUNDER_INTERVAL_S,
    STATION_ARRIVE_NM,
    STATION_NAME,
    STATION_NEAR_NM,
    STATION_OVERHEAD_SE,
    STATION_SEARCH_GROW_NM_PER_H,
    STATION_SEARCH_MAX_NM,
    STATION_SEARCH_R_NM,
    STATION_SEARCH_SPEED,
    VAK_FAST_SPEED,
    VAK_RUN_OUT_M,
    VAK_SLOW_M,
    VAK_SPEED,
    VAK_TIMEOUT_S,
)
from .tasks import Station as StationSteer

VAK_TRIES = 2                   # så många gånger lägger vi om mot mitten innan vi tar det vi har
NARROW_STATION_S = 600          # så länge efter "för smal vid stationen" föreslås inget nytt stopp där


class IceMixin:
    """Del av NavigationStation (station.py)."""

    @property
    def icemap(self) -> IceMap:
        return self.game.knowledge.ice

    def under_ice(self) -> bool:
        return self.icemap.under_ice(self.now)

    def best_opening(self) -> Opening | None:
        return self.icemap.best(self.now, self.est_x, self.est_y)

    def opening_now(self) -> Opening | None:
        """Ligger vi under en öppning just nu, i fart, utan att redan vara på väg dit?"""
        if self.vak is not None or self.ship.speed < 0.5:
            return None
        latest = self.icemap.latest(self.now)
        if latest is None or not latest.usable:
            return None
        cur = self.icemap.current
        # öppet vatten räcker för masterna; nyis måste vara lång nog att bryta igenom
        if cur is None or not (cur.open or cur.length_m >= MIN_SURFACE_LEN_M):
            return None
        return cur

    def opening_data(self, o: Opening) -> dict:
        return describe_opening(o, self.now, self.est_x, self.est_y)

    # --- isen -----------------------------------------------------------------------
    def _sound_ice(self) -> None:
        """Isekolodet: en sensor, läser isen rakt ovanför och publicerar lodningen."""
        ice = self.world.env.ice
        if ice is None or self.now < self._next_sound:
            return
        self._next_sound = self.now + SOUNDER_INTERVAL_S
        s, rng = self.ship, self.rng
        skill = self.member.effective_skill()
        t_true = ice.thickness_at(s.x, s.y)
        if t_true < OPEN_M:
            t, d = 0.0, 0.0
        else:
            t = max(0.1, t_true + rng.gauss(0, 0.1 + 0.15 * (1 - skill)))
            d = max(0.8 * t, ice.draft_at(s.x, s.y) + rng.gauss(0, 0.5))
        # isekolodet för och akter: ryms hela skrovet under en öppning (inte i isens karta)
        ends = []
        for sgn in (1, -1):
            hx = s.x + sgn * math.sin(math.radians(s.course)) * HULL_HALF_M / NM_IN_M
            hy = s.y + sgn * math.cos(math.radians(s.course)) * HULL_HALF_M / NM_IN_M
            te = ice.thickness_at(hx, hy)
            ends.append(0.0 if te < OPEN_M else max(0.1, te + rng.gauss(0, 0.1 + 0.15 * (1 - skill))))
        self._hull_ice = (self.now, ends[0], ends[1])
        before = self.icemap.current
        obs = IceSoundingObs(self.now, self.est_x, self.est_y, round(t, 2), round(d, 1))
        self.game.bus.publish(IceSounded(self.now, obs))
        closed = before if (before is not None and self.icemap.current is None) else None
        if closed is not None and closed.length_m >= REPORT_OPENING_M and self.vak is None:
            self.say("nav.ice.passed", self.opening_data(closed), quality=closed.quality(self.now))
        # isen driver in över oss på grunt vatten, eller medan vi stiger mot en öppning; på väg mot
        # ytläge räcker det att för- eller akterskeppet fått tjock is över sig
        rising = s.ordered_depth <= ANTENNA_DEPTH and s.ordered_depth < s.depth - 1
        hull_blocked = s.ordered_depth == 0 and max(ends) > BREAKABLE_M
        if (self._prev_usable and not obs.usable and (s.depth <= ANTENNA_DEPTH + 2 or rising)) \
                or (hull_blocked and rising and obs.usable):
            # ytläget genom öppningen gick inte: den räknas som för smal, ingen föreslår den igen
            # (arktis frö 13: samma nyis tre gånger medan röken tätnade)
            if self._surfacing_through is not None and s.ordered_depth == 0:
                self.game.bus.publish(OpeningNotFound(self.now, self._surfacing_through))
                self._surfacing_through = None
            self.suggest("ice_closing", "nav.suggest.ice_closing", {"depth": SAFE_ICE_DEPTH},
                         order=f"djup {SAFE_ICE_DEPTH}", cooldown=120, alarm=True)
        self._prev_usable = obs.usable

    def hull_clear(self) -> bool:
        """Visar isekolodet för och akter is vi kan bryta (eller öppet vatten), nyss?"""
        h = self._hull_ice
        return h is not None and self.now - h[0] <= 2 * SOUNDER_INTERVAL_S and \
            max(h[1], h[2]) <= BREAKABLE_M

    def _ice_report(self) -> None:
        latest = self.icemap.latest(self.now)
        if latest is None:
            self.say("nav.ice.report", {"sounded": False})
            return
        o = self.best_opening()
        self.say("nav.ice.report", {
            "sounded": True, "thickness": latest.thickness, "draft": latest.draft,
            "keel": self.icemap.deepest_keel(self.now) if self.under_ice() else 0.0,
            "opening": self.opening_data(o) if o else None},
            quality=o.quality(self.now) if o else None)

    def _go_to_opening(self) -> None:
        s = self.ship
        self._vak_tries = 0
        cur = self.icemap.current
        if cur is not None and self.icemap.latest(self.now) is not None:
            self.vak, self._vak_t, self._vak_stopping = cur, self.now, True
            self._vak_here = True
            s.order_speed(0)
            self.say("nav.vak.here", {"kind": thickness_words(cur.thickest)}, kind="ack")
            return
        # en öppning vi just passerade (förslaget "stoppa här" kom medan vi låg under den, ordern när
        # vi glidit förbi): tillbaka dit, också en liten med öppet vatten som best() inte tar
        # och en som dög när förslaget gavs men hunnit bli osäkrare innan ordern kom (maskins förslag
        # om öppning 19, och 20 s senare "ingen öppning loggad")
        o = self.just_passed_opening() or self.best_opening() or \
            self.icemap.best(self.now - JUST_PASSED_S, self.est_x, self.est_y)
        if o is None:
            self.say("nav.vak.none")
            return
        self._steer_for(o)

    def just_passed_opening(self) -> Opening | None:
        """Den öppning vi lämnade senast, om det var nyss (`JUST_PASSED_S`) och masterna går upp där."""
        recent = [o for o in self.icemap.candidates(self.now)
                  if not o.active and self.now - o.last.t <= JUST_PASSED_S
                  and (o.open or o.length_m >= MIN_SURFACE_LEN_M)]
        return max(recent, key=lambda o: o.last.t, default=None)

    def _steer_for(self, o: Opening, quiet: bool = False, centering: bool = False) -> None:
        s = self.ship
        self.vak, self._vak_t, self._vak_stopping, self._vak_here = o, self.now, False, False
        # lägga om mot mitten: stanna där, inte så fort öppningen är ovanför (då stod vi kvar i kanten
        # och sa "lägger oss mitt i den" två gånger på en sekund, arktis frö 51)
        self._vak_centering = centering
        d = self.opening_data(o)
        s.order_course(d["bearing"])
        fast = VAK_FAST_SPEED if d["range"] > VAK_SLOW_M else VAK_SPEED
        speed = min(fast, self.own.max_speed())
        s.order_speed(speed)
        depth = None
        if s.ordered_depth > SAFE_ICE_DEPTH:
            depth = SAFE_ICE_DEPTH
            s.order_depth(depth)
        if not quiet:
            self.say("nav.vak.ack", {**d, "speed": speed, "depth": depth}, kind="ack",
                     quality=o.quality(self.now))

    def _steer_to_opening(self) -> None:
        o, s = self.vak, self.ship
        if o is None:
            return
        if self.now - self._vak_t > VAK_TIMEOUT_S:
            self.vak = None
            s.order_speed(VAK_SPEED)
            self.say("nav.vak.timeout")
            return
        if not self._vak_stopping:
            course, rng_m = IceMap.course_and_range_m(self.est_x, self.est_y, o)
            off = abs(angle_diff(course, s.course))
            v = s.speed * 1852 / 3600
            stop_m = v * v / (2 * DECEL_M_PER_S2) + 10
            if off > 90 and rng_m < VAK_RUN_OUT_M:
                return                  # vaken ligger bakom: gå rakt ut, vänd sedan
            if rng_m <= VAK_SLOW_M and s.ordered_speed > VAK_SPEED:
                s.order_speed(VAK_SPEED)
            over = self.icemap.current is not None and rng_m < 150 and off < 90 and \
                not getattr(self, "_vak_centering", False)
            if (rng_m <= stop_m and off < 45) or over:
                s.order_speed(0)
                self._vak_stopping = True
            else:
                s.order_course(course)
            return
        if s.speed > 0.2:
            return
        # stilla: vad säger isekolodet?
        self.vak, self._vak_stopping = None, False
        latest = self.icemap.latest(self.now)
        near = self.near_station()
        # ytläge (vid stationen, eller genom nyis) kräver hela skrovet under öppningen; tornet kan
        # stå i kanten eller på tvären. Isekolodet för och akter säger det (periskopdjup räcker med
        # tornet)
        cramped = latest is not None and latest.usable and o.length_m >= MIN_SURFACE_LEN_M \
            and (near or not latest.open) and not self.hull_clear()
        # står vi redan mitt i (enligt kartan) hjälper ingen omläggning: säg att råken inte räcker
        centred = IceMap.course_and_range_m(self.est_x, self.est_y, o)[1] <= VAK_CENTRED_M
        if cramped and self._vak_tries < VAK_TRIES and not centred:
            self._vak_tries += 1
            if self._vak_tries == 1:
                self.say("nav.vak.reposition", {"no": o.no})
            self._steer_for(o, quiet=True, centering=True)
            return
        if latest is not None and latest.open:
            if near and (o.length_m < MIN_SURFACE_LEN_M or cramped):
                if o.no not in self._narrow_at_station:
                    # masterna kommer upp, men skrovet ryms inte: leta vidare runt stationen
                    self._narrow_at_station.add(o.no)
                    self._narrow_station_t = self.now
                    self.suggest("vak_narrow_station", "nav.vak.narrow_station",
                                 {"length": round_m(o.length_m), "name": STATION_NAME,
                                  "depth": SAFE_ICE_DEPTH},
                                 order=f"fart 4, djup {SAFE_ICE_DEPTH}", cooldown=0)
                    return
                # redan sagt att den är för smal: vi stoppade här för masterna (fix, radio)
                near = False
            if near and isinstance(self.steer, StationSteer):
                # framme: annars startar sökspiralen nästa sekund och kör oss ur öppningen
                self.steer = None
            self.suggest("vak_up", "nav.suggest.up",
                         {"kind": "öppet vatten", "open": True, "station": near},
                         order="ytläge" if near else "periskopdjup", cooldown=0)
            return
        if latest is not None and latest.usable:
            if o.length_m >= MIN_SURFACE_LEN_M and not cramped:
                self._surfacing_through = o.no
                self.suggest("vak_up", "nav.suggest.up",
                             {"kind": thickness_words(latest.thickness), "open": False},
                             order="ytläge", cooldown=0)
            else:
                # bara tornet ryms: för- och akterskeppet skulle stöta i tjock is (råken är för
                # smal, eller lång nog men vi står snett i den)
                self.game.bus.publish(OpeningNotFound(self.now, o.no))
                self.suggest("vak_narrow", "nav.vak.too_narrow",
                             {"length": round_m(o.length_m), "depth": SAFE_ICE_DEPTH,
                              "cramped": o.length_m >= MIN_SURFACE_LEN_M},
                             order=f"fart 5, djup {SAFE_ICE_DEPTH}", cooldown=0)
            return
        if self._vak_here:
            # vi stoppade när vi var under öppningen men gled förbi: backa tillbaka
            self.say("nav.vak.overshot")
            self._steer_for(o)
            return
        self.game.bus.publish(OpeningNotFound(self.now, o.no))
        self.say("nav.vak.missed")
        nxt = self.best_opening()
        if nxt is not None:
            self.suggest("vak_next", "nav.vak.next", self.opening_data(nxt), order="vak",
                         cooldown=0, quality=nxt.quality(self.now))
        else:
            self.suggest("vak_search", "nav.vak.search", {"depth": SAFE_ICE_DEPTH},
                         order=f"fart 5, djup {SAFE_ICE_DEPTH}", cooldown=0)

    # --- drivstationen ---------------------------------------------------------------
    def station_aim(self) -> tuple[str, float, float | None, dict] | None:
        """Vart vi ska styra mot stationen: ("sonar", kurs, None, data) eller
        ("wp", kurs, avstånd nm, data). Ur kunskapen, aldrig sanningen."""
        k = self.game.knowledge
        tr = k.station_track()
        if tr is not None and tr.held and tr.last_bearing is not None:
            return "sonar", tr.last_bearing, None, {"designation": tr.designation}
        wp = k.waypoints.get(STATION_NAME)
        if wp is None:
            return None
        c = bearing_to(self.est_x, self.est_y, wp.x, wp.y)
        r = distance(self.est_x, self.est_y, wp.x, wp.y)
        return "wp", c, r, {"sigma": wp.sigma(self.now)}

    def near_station(self) -> bool:
        if self.goal == "circle":
            return True
        k = self.game.knowledge
        tr = k.station_track()
        if tr is not None and tr.held and tr.observations and tr.observations[-1].se > 6:
            return True
        aim = self.station_aim()
        return aim is not None and aim[0] == "wp" and aim[2] < STATION_NEAR_NM \
            and aim[3]["sigma"] < 1.0

    def _radio_waiting(self) -> bool:
        """Väntar radion på ett sambandstillfälle som snart börjar eller pågår?"""
        from ..radio import RadioStation
        try:
            return self.game.station(RadioStation).window_pending() is not None
        except KeyError:
            return False

    def surface_ok(self) -> bool:
        """Ryms hela skrovet i öppningen vi ligger i, enligt isekolodet?"""
        latest = self.icemap.latest(self.now)
        cur = self.icemap.current
        return latest is not None and latest.usable and cur is not None \
            and cur.length_m >= MIN_SURFACE_LEN_M

    def _go_to_station(self) -> None:
        aim = self.station_aim()
        if aim is None:
            self.say("nav.station.none")
            return
        self.vak = None
        self.steer = StationSteer(source=aim[0])
        src, course, rng, d = aim
        self.ship.order_course(course)
        if src == "sonar":
            self.say("nav.station.sonar", {"name": STATION_NAME, "course": course, **d}, kind="ack")
        else:
            self.say("nav.station.wp", {"name": STATION_NAME, "course": course, "range": rng, **d},
                     kind="ack")

    def _station_overhead(self) -> tuple[float, float] | None:
        """Hörs generatorn så starkt att vi är nära? Då: skattad stationsposition."""
        tr = self.game.knowledge.station_track()
        if tr is None or not tr.held or not tr.observations:
            return None
        recent = [o for o in tr.observations[-3:] if self.now - o.t <= 30]
        if not recent or min(o.se for o in recent) < STATION_OVERHEAD_SE:
            return None
        b = math.radians(recent[-1].bearing)
        d = STATION_SEARCH_R_NM * 0.6
        return self.est_x + d * math.sin(b), self.est_y + d * math.cos(b)

    def _steer_circle(self, task: StationSteer) -> None:
        cx, cy = task.circle
        s = self.ship
        r = distance(cx, cy, self.est_x, self.est_y)
        out = bearing_to(cx, cy, self.est_x, self.est_y)
        # medurs runt mitten i en växande spiral; styr in eller ut mot banan
        want = min(STATION_SEARCH_MAX_NM, STATION_SEARCH_R_NM
                   + STATION_SEARCH_GROW_NM_PER_H * (self.now - task.circle_t) / 3600)
        corr = max(-45.0, min(45.0, (r - want) / want * 60.0))
        s.order_course(norm360(out + 90 + corr))

    def _steer_to_station(self, task: StationSteer) -> None:
        if self.vak is not None:
            return
        if self.ship.ordered_depth <= PERISCOPE_DEPTH:
            return          # på väg upp (ytläge, periskopdjup): ingen spiral som drar ned oss
        if task.circle is not None:
            self._steer_circle(task)
            return
        c = self._station_overhead()
        if c is not None:
            task.circle, task.circle_t = c, self.now
            s = self.ship
            s.order_speed(min(STATION_SEARCH_SPEED, self.own.max_speed()))
            if s.ordered_depth < SAFE_ICE_DEPTH:
                s.order_depth(SAFE_ICE_DEPTH)
            self.say("nav.station.circle", {"name": STATION_NAME,
                                             "radius": round_m(STATION_SEARCH_R_NM * 1852)})
            self._steer_circle(task)
            return
        aim = self.station_aim()
        if aim is None:
            self.steer = None
            return
        src, course, rng, d = aim
        if src != task.source and src == "sonar":
            task.source = src
            self.say("nav.station.sonar", {"name": STATION_NAME, "course": course, **d})
        self.ship.order_course(course)
        if src == "wp" and rng < STATION_ARRIVE_NM:
            self.steer = None
            self.suggest("station_arrived", "nav.station.arrived",
                         {"name": STATION_NAME, "sigma": d["sigma"]},
                         order="fart 3, smygmotor", cooldown=0)

    def _ice_advice(self) -> None:
        # stöten känns i hela båten: i fart under isen ska vi ned
        touching = self.own.sys.ice_contact
        if touching and not self._touching and self.ship.speed > 1.0:
            self.suggest("bumped", "nav.suggest.bumped", {"depth": SAFE_ICE_DEPTH},
                         order=f"djup {SAFE_ICE_DEPTH}", cooldown=60, alarm=True)
        self._touching = touching
        cur = self.opening_now()
        if cur is not None and self.near_station() and \
                getattr(cur, "no", None) not in self._narrow_at_station and \
                self.now - self._narrow_station_t > NARROW_STATION_S:
            # (inte strax efter "för smal": öppningen vi passerar har kanske inget nummer än)
            latest = self.icemap.latest(self.now)
            self.suggest("station_stop", "nav.suggest.station_stop",
                         {"kind": thickness_words(latest.thickness), "name": STATION_NAME},
                         order="vak", cooldown=300)
        sigma = self.uncertainty()
        if sigma > ICE_FIX_SIGMA_NM and self.opening_now() is not None and "fix" not in self.tasks:
            latest = self.icemap.latest(self.now)
            self.suggest("stop_here", "nav.suggest.stop_here",
                         {"kind": thickness_words(latest.thickness), "sigma": sigma},
                         order="vak", cooldown=600)
        wp = self.game.knowledge.waypoints.get(STATION_NAME)
        if wp is not None and self.steer is None and self.vak is None and \
                self.ship.depth > PERISCOPE_DEPTH + 1:
            aim = self.station_aim()
            if aim is not None and aim[0] == "wp" and aim[2] > 2 * STATION_ARRIVE_NM:
                self.suggest("station_go", "nav.suggest.station_go",
                             {"name": STATION_NAME, "course": aim[1], "range": aim[2]},
                             order="drivstationen", cooldown=900)
        s = self.ship
        if self.goal == "station" and s.speed < 0.3 and s.ordered_speed == 0 and self.vak is None \
                and not self.under_ice() and self.icemap.soundings and "fix" not in self.tasks \
                and self.uncertainty() < ICE_FIX_SIGMA_NM and not self._radio_waiting() \
                and self.own.sys.smoke < 0.15 and not self.own.sys.ventilating \
                and not self.near_station() and not self.game.queue.has_kind("suggest"):
            self.suggest("station_continue", "nav.suggest.station_continue",
                         {"name": STATION_NAME, "depth": SAFE_ICE_DEPTH},
                         order=f"fart 5, djup {SAFE_ICE_DEPTH}", cooldown=600)
        if not self.under_ice():
            return
        if s.speed < 0.3 and s.ordered_speed == 0 and self.vak is None \
                and "depth" not in s.changing() and not self.game.queue.has_kind("suggest"):
            # stilla under isen: gå till en känd öppning eller fortsätt söka
            o = self.best_opening()
            d = self.opening_data(o) if o is not None else None
            if d is not None and d["range"] > 150:
                self.suggest("resume_vak", "nav.vak.next", d, order="vak", cooldown=900,
                             quality=o.quality(self.now))
            else:
                self.suggest("resume", "nav.suggest.resume", {"depth": SAFE_ICE_DEPTH},
                             order=f"fart 5, djup {SAFE_ICE_DEPTH}", cooldown=900)
        if s.ordered_depth < SAFE_ICE_DEPTH and s.speed > VAK_SPEED + 0.5 and self.vak is None:
            self.suggest("keel", "nav.suggest.keel", {"speed": s.speed, "depth": SAFE_ICE_DEPTH},
                         order=f"djup {SAFE_ICE_DEPTH}", cooldown=900)
