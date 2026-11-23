"""Styruppdragen: följ, anfall, väntläget, farleden och konvojvakten."""
from __future__ import annotations

import math

import numpy as np

from ...geo import bearing_to, distance, norm360, offset_starboard
from ...reports import Quality
from .common import (
    ATTACK_IN_POSITION_H,
    ATTACK_IN_POSITION_NM,
    ATTACK_LEAD_H,
    ATTACK_DEPTH_MARGIN_M, ATTACK_MAX_H,
    ATTACK_OFFSET_NM,
    ATTACK_PASSED_NM,
    ATTACK_REST_S,
    ATTACK_SUGGEST_S,
    BANK_LOOK_NM,
    BANK_MAX_M,
    BANK_MIN_M,
    FAIRWAY_RIGHT_NM,
    FAIRWAY_SUGGEST_S,
    FAIRWAY_TURN_NM,
    WAIT_ARRIVED_NM,
    WAIT_MIN_DEPTH_M,
    WAIT_NAME,
    WAIT_OUT_NM,
    WAIT_QUIET_KN,
    WAIT_QUIET_NM,
    WAIT_SIDE_NM,
    WAIT_SUGGEST_S,
    WAIT_TRANSIT_KN,
)
from .tasks import Attack, Fairway, Follow, Wait


class SteeringMixin:
    """Del av NavigationStation (station.py)."""

    def _start_follow(self, designation: str) -> None:
        tr = self.game.knowledge.track(designation)
        if tr is None or not tr.held or tr.last_bearing is None:
            self.say("nav.follow.none", {"designation": designation.upper()})
            return
        self.vak = None
        self.steer = task = Follow(tr.designation)
        self._follow_step(task, announce=True)

    def _follow_step(self, task: Follow, announce: bool = False) -> None:
        """Gå i kontaktens kölvatten: styr på bäringen, håll plottets fart."""
        tr = self.game.knowledge.tracks.get(task.designation)
        s = self.ship
        if tr is None or not tr.held:
            self.steer = None
            self.say("nav.follow.lost", {"designation": task.designation}, alarm=True)
            return
        c = round(tr.last_bearing) % 360
        s.order_course(c)
        sol = tr.solution
        speed = None
        if task.hold_speed and sol is not None and sol.quality >= Quality.OSAKER \
                and self.now - sol.t < 600:
            speed = max(2, min(round(sol.speed), int(self.own.max_speed())))
            s.order_speed(speed)
        if announce:
            self.say("nav.follow", {"designation": task.designation, "course": c, "speed": speed},
                     kind="ack")

    # --- anfall: till skjutläge vid sidan av målets väg -----------------------------
    def _start_attack(self, designation: str) -> None:
        self.vak = None
        d = (designation or "").upper().replace(" ", "")
        if not d.startswith("S-"):
            d = "S-" + d.lstrip("S")
        self.steer = task = Attack(d)
        self._attack_step(task, announce=True)

    def _attack_target(self, designation: str):
        """Målets mitt nu och fart (knop) enligt plottet: konvojens baskurs om vi har den."""
        k = self.game.knowledge
        tr = k.track(designation)
        if tr is None:
            return None
        c = k.convoy
        if c is not None and tr.designation in c.members:
            x, y, vx, vy = c.advance(self.now)
            basis = "base" if c.base is not None and c.base.quality >= Quality.OSAKER else "leg"
            q = c.base.quality if basis == "base" else Quality.DALIG
            return x, y, vx, vy, "konvojen", basis, q
        sol = tr.solution
        if sol is None or sol.quality < Quality.OSAKER or self.now - sol.t > 600 or not tr.held:
            return None
        dt = (self.now - sol.t) / 3600.0
        vx, vy = sol.state[2], sol.state[3]
        return sol.x + vx * dt, sol.y + vy * dt, vx, vy, tr.designation, "solution", sol.quality

    def _attack_step(self, task: Attack, announce: bool = False) -> None:
        from ...firecontrol import approach
        tgt = self._attack_target(task.designation)
        if tgt is None:
            self.steer = None
            self.say("nav.attack.none" if announce else "nav.attack.lost",
                     {"designation": task.designation}, alarm=not announce)
            return
        x, y, vx, vy, what, basis, q = tgt
        s = self.ship
        ex, ey = self.game.own_position_estimate()
        speed = max(3.0, s.ordered_speed if s.ordered_speed is not None else s.speed)
        res = approach(ex, ey, x, y, vx, vy, speed, ATTACK_OFFSET_NM, ATTACK_LEAD_H)
        data = {"designation": task.designation, "what": what, "basis": basis, "quality": q,
                "offset": ATTACK_OFFSET_NM, "speed": speed,
                "target_course": norm360(math.degrees(math.atan2(vx, vy))),
                "target_speed": math.hypot(vx, vy)}
        v = math.hypot(vx, vy)
        if v > 0.5:
            # var vi ligger i förhållande till målets väg: framför (+) eller bakom, och åt sidan
            along = ((ex - x) * vx + (ey - y) * vy) / v
            across = abs((ex - x) * vy - (ey - y) * vx) / v
            # bakom målet: säkert bara med baskursen eller nära; två gånger i rad
            behind = along < -ATTACK_PASSED_NM and (basis != "leg" or math.hypot(ex - x, ey - y) < 3.0)
            task.behind = task.behind + 1 if behind else 0
            if task.behind >= 2:
                self.steer = None
                self.say("nav.attack.passed", data, quality=q, alarm=not announce)
                return
            if 0 <= along / v <= ATTACK_IN_POSITION_H and across <= ATTACK_IN_POSITION_NM:
                self.steer = None
                data.update(passage_min=along / v * 60, dist=across,
                            side=1 if (ex - x) * vy - (ey - y) * vx > 0 else -1)
                self.say("nav.attack.arrived", data, quality=q, alarm=True)
                self._attack_arrived_t = self.now
                # tyst medan de kommer, och upp till skjutdjup om vi ligger för djupt för avfyring
                from ..torpedo_room.common import MAX_LAUNCH_DEPTH
                parts = []
                if s.speed > 3.5:
                    parts.append("fart 3")
                if s.ordered_depth > MAX_LAUNCH_DEPTH:
                    data["fire_depth"] = MAX_LAUNCH_DEPTH - ATTACK_DEPTH_MARGIN_M
                    data["max_depth"] = MAX_LAUNCH_DEPTH
                    parts.append(f"djup {data['fire_depth']}")
                    # de har oss (krig-kort: sjunkbomber en minut före): kaptenen ska veta vad det kostar
                    data["hunted"] = self.game.knowledge.hunted(self.now)
                if parts:
                    data["slow"] = s.speed > 3.5
                    self.suggest("attack_slow", "nav.suggest.attack_slow", data,
                                 order=", ".join(parts), cooldown=120)
                return
        if res is None or res[1] > ATTACK_MAX_H:
            need = None
            for v in range(int(speed) + 1, 26):
                r2 = approach(ex, ey, x, y, vx, vy, float(v), ATTACK_OFFSET_NM, ATTACK_LEAD_H)
                if r2 is not None and r2[1] <= ATTACK_MAX_H:
                    need, res = v, r2
                    break
            if need is None:
                self.steer = None
                self.say("nav.attack.cannot", data, quality=q)
                return
            s.order_course(round(res[0]) % 360)
            task.eta_t = self.now + round(res[1] * 3600)
            if announce:
                limit = self.own.max_speed()
                data.update(course=res[0], minutes=res[1] * 60, need=need, side=res[4],
                            turbine=need > limit)
                self.say("nav.attack.speed", data, kind="ack", quality=q)
                if need <= limit:
                    self.suggest("attack_speed", "nav.suggest.attack_speed", data,
                                 order=f"fart {need}", cooldown=120)
            return
        course, t_h, _px, _py, side = res
        s.order_course(round(course) % 360)
        task.eta_t = self.now + round(t_h * 3600)
        if announce:
            data.update(course=course, minutes=t_h * 60, side=side)
            self.say("nav.attack", data, kind="ack", quality=q)

    # --- väntläget utanför grinden -------------------------------------------------
    def _wait_point(self) -> tuple[float, float, float] | None:
        """Väntläget utanför nätet: ut längs farleden (dit kortet visar djupast vatten), åt vår sida."""
        k = self.game.knowledge
        net = next((w for n, w in k.waypoints.items() if n.lower() == "nätet"), None)
        chart = k.bathymetry
        if net is None or chart is None:
            return None
        dirs = [math.radians(a) for a in range(0, 360, 10)]
        depth, b = max((float(chart.depth_at(net.x + WAIT_OUT_NM * math.sin(b),
                                             net.y + WAIT_OUT_NM * math.cos(b))), b) for b in dirs)
        if depth < WAIT_MIN_DEPTH_M:
            return None
        ux, uy = math.sin(b), math.cos(b)                       # ut mot havet längs farleden
        nx, ny = uy, -ux
        side = 1.0 if (self.est_x - net.x) * nx + (self.est_y - net.y) * ny >= 0 else -1.0
        for sd in (side, -side):
            x = net.x + ux * WAIT_OUT_NM + sd * nx * WAIT_SIDE_NM
            y = net.y + uy * WAIT_OUT_NM + sd * ny * WAIT_SIDE_NM
            if float(chart.depth_at(x, y)) >= WAIT_MIN_DEPTH_M:
                return x, y, net.sigma(self.now)
        return None

    def _publish_wait_point(self) -> tuple[float, float] | None:
        wp = self._wait_point()
        if wp is None:
            return None
        x, y, sigma = wp
        from ...events import PositionReported
        self.game.bus.publish(PositionReported(self.now, WAIT_NAME, x, y, sigma, self.now,
                                               "navigatören"))
        return x, y

    def _harbor_watch(self) -> None:
        """Före bilderna, utanför nätet: föreslå väntläget (resten upptäcker kaptenen själv)."""
        k = self.game.knowledge
        if k.best_photo is not None or self.steer is not None or k.hunted(self.now):
            return
        net = next((w for n, w in k.waypoints.items() if n.lower() == "nätet"), None)
        if net is None or distance(self.est_x, self.est_y, net.x, net.y) < WAIT_OUT_NM - 0.3:
            return
        p = self._publish_wait_point()
        if p is None or distance(self.est_x, self.est_y, *p) < 0.3:
            return
        self.suggest("harbor_wait", "nav.suggest.wait",
                     {"out": WAIT_OUT_NM, "range": distance(self.est_x, self.est_y, *p)},
                     order="smygmotor, väntläget", cooldown=WAIT_SUGGEST_S)

    def _start_wait(self) -> None:
        p = self._publish_wait_point()
        if p is None:
            self.say("nav.wait.none")
            return
        self.vak = None
        self.steer = task = Wait()
        c = round(bearing_to(self.est_x, self.est_y, *p)) % 360
        self.ship.order_course(c)
        self._wait_step(task)
        self.say("nav.wait", {"course": c, "range": distance(self.est_x, self.est_y, *p)},
                 kind="ack")

    def _wait_step(self, task: Wait) -> None:
        """Styr mot väntläget och håll det mot tidvattnet: 3 kn dit, 1–2 kn när vi är framme."""
        wp = self.game.knowledge.waypoints.get(WAIT_NAME)
        if wp is None:
            self.steer = None
            return
        s = self.ship
        d = distance(self.est_x, self.est_y, wp.x, wp.y)
        s.order_course(round(bearing_to(self.est_x, self.est_y, wp.x, wp.y)) % 360)
        if d <= WAIT_ARRIVED_NM and not task.arrived:
            task.arrived = True
            self.say("nav.wait.arrived", {"sigma": self.uncertainty()}, alarm=True)
        if task.arrived:
            s.order_speed(1.0 if d <= WAIT_ARRIVED_NM else 2.0)
        else:
            # fortare långt ute; tyst genom patrullbåtens skärm (1,5–2,5 nm ut) och sista biten
            net = next((w for n, w in self.game.knowledge.waypoints.items()
                        if n.lower() == "nätet"), None)
            far = net is not None and distance(self.est_x, self.est_y, net.x, net.y) > WAIT_QUIET_NM
            s.order_speed(min(WAIT_TRANSIT_KN, self.own.max_speed()) if far else WAIT_QUIET_KN)

    # --- farleden ------------------------------------------------------------------
    def _fairway_points(self) -> list[tuple[float, float]]:
        """Farleden enligt kortet, förskjuten till styrbord: där vi styr."""
        fw = self.game.knowledge.fairway
        if len(fw) < 2:
            return list(fw)
        return offset_starboard(fw, FAIRWAY_RIGHT_NM)

    def _fairway_point(self) -> tuple[float, float] | None:
        """Nästa punkt på farleden medan vi går den, annars None."""
        task = self.steer
        if not isinstance(task, Fairway):
            return None
        pts = self._fairway_points()
        return pts[task.index] if task.index < len(pts) else None

    def _fairway_passed(self, pts: list[tuple[float, float]], i: int) -> bool:
        """Är vi framme vid, eller förbi, punkt i (längs benet som leder dit)?"""
        px, py = pts[i]
        if distance(self.est_x, self.est_y, px, py) < FAIRWAY_TURN_NM:
            return True
        ax, ay = pts[i - 1] if i > 0 else (self.est_x, self.est_y)
        if i == 0:
            return False
        dx, dy = px - ax, py - ay
        return (self.est_x - px) * dx + (self.est_y - py) * dy > 0

    def _fairway_index(self) -> int:
        pts = self._fairway_points()
        # närmaste ben framför oss: hoppa över punkter vi redan passerat
        i = 0
        if pts:
            i = min(range(len(pts)), key=lambda k: distance(self.est_x, self.est_y, *pts[k]))
            if i + 1 < len(pts) and self._fairway_passed(pts, i):
                i += 1
            elif i > 0 and not self._fairway_passed(pts, i - 1):
                i -= 1
        return i

    def _fairway_left(self) -> bool:
        """Finns det farled kvar framför oss?"""
        pts = self._fairway_points()
        if len(pts) < 2 or self._fw_done:
            return False
        i = self._fairway_index()
        return not (i == len(pts) - 1 and self._fairway_passed(pts, i))

    def _start_fairway(self) -> None:
        if not self._fairway_left():
            self.say("nav.fairway.none", {"done": self._fw_done})
            return
        self.vak = None
        self.steer = task = Fairway(self._fairway_index())
        self.course_set_t = self.now
        pts = self._fairway_points()
        c = round(bearing_to(self.est_x, self.est_y, *pts[task.index])) % 360
        self.ship.order_course(c)
        self.say("nav.fairway", {"course": c, "legs": len(pts) - task.index,
                                 "dist": self._fairway_dist(pts, task.index)}, kind="ack")

    def _fairway_dist(self, pts: list[tuple[float, float]], i: int) -> float:
        d, x, y = 0.0, self.est_x, self.est_y
        for p in pts[i:]:
            d += distance(x, y, *p)
            x, y = p
        return d

    def _fairway_step(self, task: Fairway) -> None:
        """Styr längs farleden; gir mot nästa ben strax före brytpunkten."""
        pts = self._fairway_points()
        if task.index >= len(pts):
            self.steer = None
            return
        if self._fairway_passed(pts, task.index):
            task.index += 1
            if task.index >= len(pts):
                self.steer = None
                self._fw_done = True
                k = self.game.knowledge
                depth = self.chart_depth_at(self.est_x, self.est_y)
                self.say("nav.fairway.done", {"to": k.fairway_to, "surfaced": self.own.surfaced,
                                              "depth": round(depth, -1) if depth else None})
                if k.fairway_to and k.fairway_to in k.waypoints:
                    wp = k.waypoints[k.fairway_to]
                    c = bearing_to(self.est_x, self.est_y, wp.x, wp.y)
                    self.suggest("fairway_to", "nav.suggest.fairway_to",
                                 {"name": wp.name, "course": c,
                                  "range": distance(self.est_x, self.est_y, wp.x, wp.y)},
                                 order=f"kurs mot {wp.name.lower()}", cooldown=600)
                return
            c = round(bearing_to(self.est_x, self.est_y, *pts[task.index])) % 360
            self.ship.order_course(c)
            self.say("nav.fairway.leg", {"course": c, "legs": len(pts) - task.index})
            return
        self.ship.order_course(round(bearing_to(self.est_x, self.est_y, *pts[task.index])) % 360)

    def _fairway_watch(self) -> None:
        """I fjorden utan lots: föreslå att följa farleden ut."""
        if self.steer is not None or not self.game.knowledge.fairway or \
                self.now - self.course_set_t < 120 and self.course_set_t > 0:
            return
        if not self._fairway_left():
            return
        k = self.game.knowledge
        if k.fairway_to in k.waypoints and \
                self._fairway_index() >= len(self._fairway_points()) - 1:
            return      # bara sista benet kvar och farleden leder till ett känt mål: gå dit direkt
                        # (förut gick förslagen fram och tillbaka med övningens "kurs mot området")
        self.suggest("fairway", "nav.suggest.fairway",
                     {"to": self.game.knowledge.fairway_to, "surfaced": self.own.surfaced},
                     order="farleden", cooldown=FAIRWAY_SUGGEST_S)

    def _convoy_watch(self) -> None:
        """Plottet har en konvoj och vi ligger framför den: föreslå anfall (aldrig avfyring)."""
        from ..officer import is_big_ship
        k = self.game.knowledge
        if k.hunted(self.now) or self.now - self._attack_arrived_t < ATTACK_REST_S:
            return
        c = k.convoy
        if c is not None:
            tracks = [t for m in c.members if (t := k.track(m)) is not None]
        else:                                   # ett ensamt stort fartyg med en färsk lösning
            tracks = [t for t in k.tracks.values() if t.held and is_big_ship(t)
                      and t.solution is not None and t.solution.quality >= Quality.OSAKER
                      and self.now - t.solution.t <= 600]
        if not tracks:
            return
        # helst ett klassat mål: trupptransport eller tankfartyg
        best = next((t for t in tracks if "transport" in t.classification
                     or "tank" in t.classification), tracks[0])
        tgt = self._attack_target(best.designation)
        if tgt is None:
            return
        x, y, vx, vy, what, _basis, q = tgt
        v = math.hypot(vx, vy)
        ex, ey = self.game.own_position_estimate()
        if v < 0.5 or ((ex - x) * vx + (ey - y) * vy) / v < 0:
            return                              # målet har redan passerat
        self.suggest("convoy_attack", "nav.suggest.attack",
                     {"designation": best.designation, "convoy": what == "konvojen",
                      "course": norm360(math.degrees(math.atan2(vx, vy))),
                      "classification": best.classification if best.classification
                      != "okänd kontakt" else ""},
                     order=f"anfall {best.designation}", cooldown=ATTACK_SUGGEST_S, quality=q)

    def _steer_to(self, name: str) -> None:
        wps = self.game.knowledge.waypoints
        key = name.strip().lower()
        wp = next((w for n, w in wps.items() if n.lower() == key), None) or \
            next((w for n, w in wps.items() if n.lower().startswith(key[:5])), None)
        if wp is None and key.startswith(("bank", "grund")) and self._chart_has_bank():
            self._steer_to_bank()
            return
        if wp is None:
            known = sorted(wps) + (["banken"] if self._chart_has_bank() else [])
            self.say("nav.steer.none", {"name": name, "known": known})
            return
        wx, wy = wp.at(self.now)                # ett rörligt mål: framräknat med meddelad kurs
        c = round(bearing_to(self.est_x, self.est_y, wx, wy)) % 360
        self.vak = None
        self.steer = None
        self.course_set_t = self.now
        self.ship.order_course(c)
        self.say("nav.steer", {"name": wp.name, "course": c,
                               "range": distance(self.est_x, self.est_y, wx, wy),
                               "sigma": wp.sigma(self.now) + self.uncertainty()}, kind="ack")

    def _chart_has_bank(self) -> bool:
        from ...seabed import Bank
        chart = self.game.knowledge.bathymetry
        return chart is not None and any(isinstance(f, Bank) for f in chart.features)

    def _steer_to_bank(self) -> None:
        """Kurs mot närmaste vatten där kortet visar botten grundare än provdjupet (att lägga sig på)."""
        chart = self.game.knowledge.bathymetry
        here = float(chart.depth_at(self.est_x, self.est_y))
        if BANK_MIN_M <= here <= BANK_MAX_M:
            self.say("nav.steer.bank_here", {"depth": round(here, -1)}, kind="ack")
            return
        dist = np.arange(0.1, BANK_LOOK_NM + 0.01, 0.1)
        best = None
        for c in range(0, 360, 5):
            b = math.radians(c)
            z = chart.depths(self.est_x + dist * math.sin(b), self.est_y + dist * math.cos(b))
            ok = np.nonzero((z >= BANK_MIN_M) & (z <= BANK_MAX_M))[0]
            if len(ok) and (best is None or dist[ok[0]] < best[0]):
                best = (float(dist[ok[0]]), c, float(z[ok[0]]))
        if best is None:
            self.say("nav.steer.none", {"name": "banken", "known": sorted(self.game.knowledge.waypoints)})
            return
        d, c, z = best
        self.vak = None
        self.steer = None
        self.course_set_t = self.now
        self.ship.order_course(c)
        self.say("nav.steer.bank", {"course": c, "range": d, "depth": round(z, -1),
                                    "sigma": self.uncertainty()}, kind="ack")
