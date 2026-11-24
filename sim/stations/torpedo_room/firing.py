"""Eldledningen: skjutlösning, avfyring, salva och varningarna före skottet."""
from __future__ import annotations

import math

from ...events import OwnSoundMade
from ...geo import angle_diff
from ...firecontrol import intercept
from ...reports import Quality
from ...war import assess
from ...weapons import ARM_DISTANCE_NM, TORPEDO_TYPES, launch_torpedo
from .common import (
    ASPECT_MAX_SIGMA, ASPECT_MIN_KN, CONFIRM_S, HUNTING_RUN_S, LONG_RUN_S, LOST_CONE_DEG, LOST_LANE_S,
    NARROW_DEG, FireSalvo, FireTube,
    MAX_LAUNCH_DEPTH, MAX_LAUNCH_PITCH, MAX_LAUNCH_SPEED, NEUTRAL_CONE_DEG, NEUTRAL_LANE_NM, NEUTRAL_STEP_S, N_TUBES,
    RIVAL_NM, Running, SALVO_GAP_MAX_NM, SALVO_GAP_NM, SEEKER_LANE_NM,
    SALVO_MAX, SALVO_STEP_DEG, TOO_CLOSE_MARGIN_NM, Tube,
)


class FiringMixin:
    """Eldledningen, som TorpedoRoom ärver. Räknar bara på kunskap (plottets lösning, bestick)."""

    # --- eldledning --------------------------------------------------------------
    def _solution_for(self, designation: str | None):
        k = self.game.knowledge
        tr = k.track(designation) if designation else None
        if tr is None:
            return None, None
        sol = k.resolve(tr.designation, self.now, self.game.own_position_estimate())
        return tr, sol

    def _aim(self, sol, type_key: str):
        spec = TORPEDO_TYPES[type_key]
        ex, ey = self.game.own_position_estimate()
        vx, vy = sol.state[2], sol.state[3]
        res = intercept(sol.x - ex, sol.y - ey, vx, vy, spec.speed)
        if res is None:
            return None
        course, t_h = res
        if spec.speed * t_h > spec.range_nm:
            return None
        return course, t_h * 3600, spec.speed * t_h

    def _blocked(self, type_key: str) -> str | None:
        """Kärnladdningen skjuts bara med kärnvapenrådets tre nycklar (`council.py`)."""
        if TORPEDO_TYPES[type_key].nuclear and not self._keys():
            return "kärnladdningen kräver kärnvapenråd, nycklarna är inte vridna"
        return None

    def _aboard(self) -> list[str]:
        """Torpedtyperna vi har ombord (i tuberna eller i stället), i `TORPEDO_TYPES` ordning:
        skjutlösningen räknar bara på dem (övningstorpeden finns bara i övningen)."""
        have = {t.load for t in self.tubes if t.load} | {k for k, n in self.inventory.items() if n > 0}
        return [k for k in TORPEDO_TYPES if k in have]

    def _keys(self) -> bool:
        from ..council import NuclearCouncil
        c = self.game.station(NuclearCouncil)
        return c is not None and c.armed()

    def _tube(self, n: int) -> Tube | None:
        return self.tubes[n - 1] if 1 <= n <= N_TUBES else None

    def _salvo(self, o: FireSalvo) -> None:
        """Raka torpeder i solfjäder: mittersta på lösningen, de andra vid sidan."""
        tubes = list(o.tubes) if o.tubes else [
            t.n for t in self.tubes if t.load and not TORPEDO_TYPES[t.load].homing
            and not TORPEDO_TYPES[t.load].nuclear][:SALVO_MAX]
        tubes = [n for n in tubes if (t := self._tube(n)) is not None and t.load]
        if not tubes:
            self.say("torp.refused", {"reason": "inga laddade raka tuber för en salva"})
            self._suggest_reload(urgent=True, straight=True)
            return
        if len(tubes) == 1:
            # en tub är ingen solfjäder: ett vanligt skott, med alla dess frågor
            if self._fire(FireTube(tubes[0], designation=o.designation)):
                self.say("torp.salvo_single", {"designation": o.designation, "tube": tubes[0]})
            return
        tr, sol = self._solution_for(o.designation)
        first_type = self._tube(tubes[0]).load
        aim = self._aim(sol, first_type) if sol is not None else None
        dist = aim[2] if aim else 2.0
        # lägesfelet vid målet: avståndets σ plus fartens och kursens σ under gångtiden
        gap = SALVO_GAP_NM
        if aim and sol is not None:
            run_h = aim[1] / 3600.0
            err = math.sqrt(sol.range_sigma ** 2 + (run_h * sol.speed_sigma) ** 2
                            + (run_h * sol.speed * math.radians(min(sol.course_sigma, 60))) ** 2)
            gap = min(max(err, SALVO_GAP_NM), SALVO_GAP_MAX_NM)
        step = math.degrees(math.atan2(gap, max(dist, 0.1)))
        step = min(max(step, SALVO_STEP_DEG[0]), SALVO_STEP_DEG[1])
        # hela salvan eller ingen: en tub som inte kan skjuta stoppar den innan någon gått
        for tube in tubes:
            if why := self._refusal(FireTube(tube, designation=o.designation)):
                self.say("torp.refused", {"reason": why})
                return
        if self._weapons_hold(first_type):
            return
        if aim and tr is not None and self._long_shot(tr, aim[1], first_type):
            return
        if aim and self._too_close(o.designation, aim[2], first_type):
            return
        n = len(tubes)
        if aim and not self._neutrals_clear(
                o.designation, [(aim[0] + (i - (n - 1) / 2) * step) % 360 for i in range(n)],
                first_type):
            return
        for i, tube in enumerate(tubes):
            off = (i - (n - 1) / 2) * step
            if not self._fire(FireTube(tube, designation=o.designation, offset=off,
                                       in_salvo=True)):
                return
        self.say("torp.salvo", {"designation": o.designation, "n": n, "step": step})
        if aim:
            self._leg_warning(o.designation, aim[1], first_type)

    def _refusal(self, o: FireTube) -> str | None:
        """Varför tuben inte kan skjuta nu (tuben, djup och fart, tillstånd, målet), annars None."""
        tube = self._tube(o.tube)
        st, sys = self.own.state, self.own.sys
        reason = None
        if tube is None:
            reason = f"det finns ingen tub {o.tube}"
        elif tube.loading:
            reason = f"tub {o.tube} laddas fortfarande"
        elif tube.load is None:
            reason = f"tub {o.tube} är tom"
        elif sys.health["tubes"] < 0.5 and o.tube <= 4:
            reason = f"tub {o.tube} är skadad"
        elif st.depth > MAX_LAUNCH_DEPTH:
            reason = f"vi är för djupt för avfyring, högst {MAX_LAUNCH_DEPTH} meter"
        elif st.speed > MAX_LAUNCH_SPEED:
            reason = f"farten är för hög för avfyring, högst {MAX_LAUNCH_SPEED} knop"
        elif abs(self.own.pitch) > MAX_LAUNCH_PITCH:
            reason = (f"båten lutar {abs(self.own.pitch):.0f} grader, högst {MAX_LAUNCH_PITCH} vid avfyring; "
                      "vänta tills djupet är nått")
        elif b := self._blocked(tube.load):
            reason = b
        elif o.designation:
            tr, sol = self._solution_for(o.designation)
            if tr is None:
                reason = f"vi har ingen kontakt {o.designation}"
            elif sol is None:
                reason = f"plottet har ingen lösning på {o.designation}"
            elif self._aim(sol, tube.load) is None:
                reason = f"{o.designation} är utom räckhåll för {TORPEDO_TYPES[tube.load].key}"
        return reason

    def _pick_tube(self, designation: str) -> int | None:
        """Tuben torpedrummet väljer mot kontakten: målsökande före raka före övning, den
        första laddade som når; aldrig kärnladdningen (den kräver tubens nummer)."""
        tr, sol = self._solution_for(designation)
        order = {"53-62T": 0, "SET-53": 1, "53-61": 2, "övning": 3}
        best = None
        for t in self.tubes:
            if t.load is None or t.loading or t.load not in order or self._blocked(t.load):
                continue
            if self.own.sys.health["tubes"] < 0.5 and t.n <= 4:
                continue
            if sol is not None and self._aim(sol, t.load) is None:
                continue
            if best is None or order[t.load] < order[best.load]:
                best = t
        return best.n if best else None

    def _fire_at(self, designation: str) -> None:
        n = self._pick_tube(designation)
        if n is None:
            loaded = [t for t in self.tubes if t.load and not t.loading and t.load != "T-5"]
            self.say("torp.refused", {"reason": "ingen laddad tub når " + designation if loaded
                                      else "ingen tub är laddad"})
            self._suggest_reload(urgent=True)
            return
        self._fire(FireTube(n, designation=designation))

    def _contact_asked(self, designation: str) -> None:
        """Kaptenen frågade om kontakten: skjutlösningen om vi har laddat och plottet har en
        lösning (inte för civila)."""
        if not any(t.load and not t.loading for t in self.tubes):
            return
        tr, sol = self._solution_for(designation)
        if tr is None or sol is None or tr.civil or sol.quality < Quality.OSAKER:
            return
        self._preview(designation)

    def _fire(self, o: FireTube) -> bool:
        if reason := self._refusal(o):
            self.say("torp.refused", {"reason": reason})
            return False
        tube = self._tube(o.tube)
        spec = TORPEDO_TYPES[tube.load]
        if not o.in_salvo and self._weapons_hold(tube.load):
            return False
        quality = None
        run_s = None
        detonate_at = None
        if o.designation:
            tr, sol = self._solution_for(o.designation)
            course, run_s, dist = self._aim(sol, tube.load)
            course = (course + o.offset) % 360
            if not o.in_salvo and self._long_shot(tr, run_s, tube.load):
                return False
            if not o.in_salvo and not self._neutrals_clear(tr.designation, [course], tube.load):
                return False
            if not o.in_salvo and self._too_close(tr.designation, dist, tube.load):
                return False
            if not tr.warship and not (spec.exercise and tr.friendly) and \
                    self._confirmed.get(tr.designation, -10**9) < self.now - CONFIRM_S:
                # torpedrummet frågar en gång; samma order inom en minut verkställs
                self._confirmed[tr.designation] = self.now
                self.game.asked()               # ja upprepar ordern
                self.say("torp.confirm", {"designation": tr.designation,
                                          "classification": tr.classification,
                                          "civil": tr.civil}, quality=tr.class_quality)
                return False
            quality = sol.quality
            if spec.nuclear:
                detonate_at = dist
                if o.in_salvo:
                    self.say("torp.refused", {"reason": "kärnladdningen skjuts inte i salva"})
                    return False
                if self._nuclear_confirm_t < self.now - CONFIRM_S:
                    # nycklarna är vridna: torpedrummet frågar en gång, upprepad order skjuter
                    self._nuclear_confirm_t = self.now
                    self.say("torp.nuclear_confirm", {"tube": o.tube, "designation": o.designation},
                             alarm=True)
                    return False
        else:
            course = o.course
            if not self._neutrals_clear(None, [course], tube.load):
                return False
        torp = launch_torpedo(self.world, spec, course, detonate_at)
        if spec.nuclear:
            from ..council import NuclearCouncil
            if (c := self.game.station(NuclearCouncil)) is not None:
                c.fired()
            self.world.mission["nuclear_fired_t"] = self.now
        self.game.bus.publish(OwnSoundMade(self.now, "launch"))
        if not spec.exercise:
            self.world.mission["hostile_act"] = True
        tube.load = None
        self._emptied[tube.n] = self.now
        self._launches += 1
        run_nm = min(detonate_at, spec.range_nm) if detonate_at else spec.range_nm
        lx, ly = self.game.own_position_estimate()
        run = Running(
            no=self._launches, tube=o.tube, type=spec.key, designation=o.designation,
            course=course, launch_t=self.now,
            t_hit=int(self.now + run_s) if run_s else None,
            t_end=int(self.now + run_nm / spec.speed * 3600), launch_x=lx, launch_y=ly)
        self.in_water.append(run)
        if o.designation:       # ett köat "skjutlösning på S-x" från före skottet gäller inte längre
            self.game.queue.drop(lambda r: r.type == "torp.ready"
                                 and r.data.get("designation") == o.designation)
        if spec.wire_nm:
            self._wire_launched(run, torp)
        self.say("torp.fired", {"tube": o.tube, "type": spec.key, "course": course,
                                "run_s": run_s, "quality": quality, "wired": run.wired},
                 kind="ack", quality=quality, alarm=True)
        if o.designation and run_s and not o.in_salvo:
            self._leg_warning(o.designation, run_s, spec.key)
        return True

    def _too_close(self, designation: str, dist: float | None, type_key: str) -> bool:
        """Träffpunkten innanför armeringssträckan: torpeden exploderar inte. Fråga en gång per mål
        (enkelskott och salva); upprepad order inom en minut skjuter."""
        if TORPEDO_TYPES[type_key].nuclear or dist is None or \
                dist >= ARM_DISTANCE_NM + TOO_CLOSE_MARGIN_NM:
            return False
        warned = self.__dict__.setdefault("_close_warned", {})
        if warned.get(designation, -10**9) >= self.now - CONFIRM_S:
            return False
        warned[designation] = self.now
        self.game.asked()               # ja upprepar ordern
        self.say("torp.too_close", {"designation": designation, "range": dist}, alarm=True)
        return True

    def _long_shot(self, tr, run_s: float | None, type_key: str) -> bool:
        """Rak torped med lång gångtid (över LONG_RUN_S): målet hinner gira eller ändra fart. Torpedrummet frågar
        en gång per mål och föreslår `anfall S-x` (navigatören tar oss till skjutläge), utom när de
        har oss eller skjutläget inte nås; upprepad order inom en minut skjuter."""
        spec = TORPEDO_TYPES[type_key]
        if spec.exercise or spec.nuclear or spec.homing or run_s is None or run_s <= LONG_RUN_S \
                or tr.friendly:
            return False                # målsökarna söker själva efter en gir (leg_warning räcker)
        asked = self.__dict__.setdefault("_long_asked", {})
        if asked.get(tr.designation, -10**9) >= self.now - CONFIRM_S:
            return False
        asked[tr.designation] = self.now
        rhythm = self._turn_rhythm(tr)
        self.game.asked()               # ja upprepar ordern
        self.say("torp.long_shot", {"designation": tr.designation, "run_s": run_s, "type": type_key,
                                    "kind": rhythm[0] if rhythm else None},
                 quality=Quality.OSAKER, alarm=True)
        if self._can_close(tr):
            self.suggest(f"close{tr.designation}", "torp.suggest.close",
                         {"designation": tr.designation}, order=f"anfall {tr.designation}",
                         cooldown=CONFIRM_S)
        return True

    def _can_close(self, tr) -> bool:
        """Kan navigatören ta oss till skjutläge mot målet (inte medan de har oss)?"""
        from ...firecontrol import approach
        from ..navigation.common import ATTACK_LEAD_H, ATTACK_MAX_H, ATTACK_OFFSET_NM
        from ..navigation import NavigationStation
        from ..navigation.tasks import Attack
        k = self.game.knowledge
        if k.hunted(self.now) or k.hunting(tr, self.now):
            return False
        try:
            steer = self.game.station(NavigationStation).steer
        except KeyError:
            steer = None
        if isinstance(steer, Attack):
            members = k.convoy.members if k.convoy is not None else ()
            if steer.designation == tr.designation or \
                    (steer.designation in members and tr.designation in members):
                return False            # navigatören anfaller redan målet (eller dess konvoj)
        sol = tr.solution
        if sol is None or sol.quality < Quality.OSAKER:
            return False
        ex, ey = self.game.own_position_estimate()
        dt = (self.now - sol.t) / 3600.0
        vx, vy = sol.state[2], sol.state[3]
        speed = max(3.0, float(self.own.max_speed()))
        res = approach(ex, ey, sol.x + vx * dt, sol.y + vy * dt, vx, vy, speed,
                       ATTACK_OFFSET_NM, ATTACK_LEAD_H)
        return res is not None and res[1] <= ATTACK_MAX_H

    def _weapons_hold(self, type_key: str) -> bool:
        """Fredstid: ordern tillåter inte vapen nu (den säger inte krig och vi angrips inte med
        skarpa vapen, `war.assess`). Torpedrummet frågar en gång (`confirm_once`); upprepad order
        inom en minut skjuter. Övningstorpeden frågas inte, kärnladdningen har kärnvapenrådet."""
        spec = TORPEDO_TYPES[type_key]
        if spec.exercise or spec.nuclear:
            return False
        k = self.game.knowledge
        if k.at_war()[0] or assess(k, self.now).attacked:
            return False
        return self.confirm_once("weapons_hold", "torp.weapons_hold")

    def _neutrals_in_lane(self, target: str | None, courses: list[float],
                          type_key: str) -> list[dict]:
        """Kända handelsfartyg nära någon av torpedernas banor, hela vägen ut (kunskap). En målsökande
        torped tar det den hör bäst: för den gäller i stället andra fartyg nära målet (`_seeker_rivals`)."""
        spec = TORPEDO_TYPES[type_key]
        if spec.exercise or spec.nuclear:
            return []
        if spec.homing:
            # nära målet, och handelsfartyg längs hela banan: missar den målet söker den vidare
            near = self._seeker_rivals(target, courses[0], type_key) if target else []
            seen = {r["designation"] for r in near}
            return near + [r for r in self._lane_ships(target, courses, spec, SEEKER_LANE_NM)
                           if r["designation"] not in seen]
        return self._lane_ships(target, courses, spec, NEUTRAL_LANE_NM)

    def _lane_ships(self, target: str | None, courses: list[float], spec,
                    lane_nm: float) -> list[dict]:
        """Kända handelsfartyg som enligt plottet kommer inom `lane_nm` från någon av banorna under
        hela räckvidden (utan lösning: bäringen nära en bana)."""
        k = self.game.knowledge
        ex, ey = self.game.own_position_estimate()
        run_s = spec.range_nm / spec.speed * 3600
        out = []
        for tr in k.tracks.values():
            if not self._neutral(tr) or tr.designation == target or not tr.observations or tr.sunk_t is not None:
                continue
            if not tr.held:
                # tappad nyss: fartyget är kvar, bara tyst för sonar (clyde-in frö 29: fiskebåten tappad 10 min
                # före skottet, 35° från banan, och den målsökande torpeden tog den). Bara bäringen, brett.
                lost_s = self.now - tr.observations[-1].t
                b = tr.last_bearing
                if lost_s <= LOST_LANE_S and any(abs(angle_diff(b, c)) <= LOST_CONE_DEG for c in courses):
                    out.append({"designation": tr.designation, "classification": tr.classification,
                                "bearing": b, "range": None, "lost_min": max(1, round(lost_s / 60))})
                continue
            sol = tr.solution
            if sol is not None and sol.quality >= Quality.OSAKER:
                dt0 = (self.now - sol.t) / 3600.0
                sx, sy = sol.x + sol.state[2] * dt0 - ex, sol.y + sol.state[3] * dt0 - ey
                near = False
                for c in courses:
                    b = math.radians(c)
                    for t in range(0, int(run_s) + 1, NEUTRAL_STEP_S):
                        h = t / 3600.0
                        dx = sx + sol.state[2] * h - spec.speed * h * math.sin(b)
                        dy = sy + sol.state[3] * h - spec.speed * h * math.cos(b)
                        if math.hypot(dx, dy) <= lane_nm:
                            near = True
                            break
                    if near:
                        break
                if near:
                    out.append({"designation": tr.designation, "classification": tr.classification,
                                "bearing": math.degrees(math.atan2(sx, sy)) % 360,
                                "range": math.hypot(sx, sy)})
            else:
                b = tr.last_bearing
                lo, hi = min(courses), max(courses)
                if any(abs(angle_diff(b, c)) <= NEUTRAL_CONE_DEG for c in courses) or \
                        (hi - lo < 180 and lo <= b <= hi):
                    out.append({"designation": tr.designation, "classification": tr.classification,
                                "bearing": b, "range": None})
        return out

    @staticmethod
    def _neutral(tr) -> bool:
        """Klassad (minst god) som handelsfartyg eller fiskebåt: ett neutralt fartyg vi varnar för (clyde-in frö
        29: fiskebåtarna räknades inte, och den målsökande torpeden tog en)."""
        return tr.civil or tr.class_quality >= Quality.GOD and "fiskebåt" in tr.classification

    def _seeker_rivals(self, target: str, course: float, type_key: str) -> list[dict]:
        """Andra kända fartyg som enligt plottet ligger nära målet när den målsökande torpeden är
        framme (inom RIVAL_NM), eller utan lösning i bäring nära torpedens kurs: målsökaren kan ta dem."""
        k = self.game.knowledge
        tr_t, sol_t = self._solution_for(target)
        aim = self._aim(sol_t, type_key) if sol_t is not None else None
        if aim is None:
            return []
        ex, ey = self.game.own_position_estimate()
        h = aim[1] / 3600.0
        tx, ty = sol_t.x + sol_t.state[2] * h, sol_t.y + sol_t.state[3] * h
        out = []
        for tr in k.tracks.values():
            if not tr.held or tr.designation == tr_t.designation or not tr.observations \
                    or tr.sunk_t is not None or tr.friendly and not tr.civil:
                continue
            sol = tr.solution
            if sol is not None and sol.quality >= Quality.OSAKER:
                dt0 = (self.now - sol.t) / 3600.0
                sx, sy = sol.x + sol.state[2] * (dt0 + h), sol.y + sol.state[3] * (dt0 + h)
                d = math.hypot(sx - tx, sy - ty)
                if d <= RIVAL_NM:
                    nx, ny = sol.x + sol.state[2] * dt0 - ex, sol.y + sol.state[3] * dt0 - ey
                    out.append({"designation": tr.designation, "classification": tr.classification,
                                "bearing": math.degrees(math.atan2(nx, ny)) % 360,
                                "range": math.hypot(nx, ny), "from_target": d})
            elif abs(angle_diff(tr.last_bearing, course)) <= NEUTRAL_CONE_DEG:
                out.append({"designation": tr.designation, "classification": tr.classification,
                            "bearing": tr.last_bearing, "range": None, "from_target": None})
        return out

    def _neutrals_clear(self, target: str | None, courses: list[float], type_key: str) -> bool:
        """Varna en gång för kända handelsfartyg i banan; samma order inom en minut skjuter.
        Varningen räknas också som bekräftelse av målet (ingen andra fråga)."""
        ships = self._neutrals_in_lane(target, courses, type_key)
        key = target or "kurs"
        if not ships or self._neutral_warned.get(key, -10**9) >= self.now - CONFIRM_S:
            return True
        self._neutral_warned[key] = self.now
        d = {"ships": ships, "homing": TORPEDO_TYPES[type_key].homing, "target": target}
        if target:
            # varningen räknas som frågan om målet också: säg då vad målet självt är
            self._confirmed[target] = self.now
            tr = self.game.knowledge.track(target)
            if tr is not None and not tr.warship and not tr.friendly:
                d.update(target_class=tr.classification, target_civil=tr.civil)
        self.game.asked()               # ja upprepar ordern
        self.say("torp.neutral", d, quality=Quality.GOD)
        return False

    def _turn_rhythm(self, tr) -> tuple[str, int | None, int | None] | None:
        """Hur målet girar, enligt plottet: konvojens sicksack (benlängd, senaste gir), ett mål som
        jagar oss (girar hela tiden), eller ett mål med två märkta girar (benet ur dem). Annars None."""
        k = self.game.knowledge
        c = k.convoy
        if c is not None and tr.designation in c.members and c.mean_leg_s is not None \
                and c.last_turn_t is not None:
            return "convoy", c.mean_leg_s, c.last_turn_t
        if k.hunting(tr, self.now):
            return "hunting", None, None
        gaps = sorted(b - a for a, b in zip(tr.turns, tr.turns[1:]) if b > a)
        if gaps:
            return "zigzag", gaps[len(gaps) // 2], tr.turns[-1]
        return None

    def _leg_warning(self, designation: str, run_s: float, type_key: str) -> None:
        """Ett mål som girar kan gira innan torpeden är framme: säg det."""
        tr = self.game.knowledge.track(designation)
        if tr is None or self.__dict__.get("_long_asked", {}).get(tr.designation, -10**9) \
                >= self.now - CONFIRM_S:
            return          # vi har just frågat om det långa skottet: kaptenen vet
        rhythm = self._turn_rhythm(tr)
        if rhythm is None:
            # ingen känd rytm: en lång gångtid räcker för en gir eller fartändring
            if run_s > LONG_RUN_S and not tr.friendly:
                self.say("torp.leg_warning", {"designation": tr.designation, "run_s": run_s,
                                              "type": type_key, "kind": "long",
                                              "homing": TORPEDO_TYPES[type_key].homing},
                         quality=Quality.OSAKER)
            return
        kind, leg_s, last_t = rhythm
        d = {"designation": tr.designation, "run_s": run_s, "type": type_key, "kind": kind,
             "homing": TORPEDO_TYPES[type_key].homing}
        if kind == "hunting":
            if run_s <= HUNTING_RUN_S:
                return
        else:
            elapsed = self.now - last_t
            if run_s <= leg_s - elapsed:
                return
            d.update(elapsed_s=elapsed, leg_s=leg_s)
        self.say("torp.leg_warning", d, quality=Quality.OSAKER)

    def _aspect(self, sol, torpedo_course: float) -> dict | None:
        """Varifrån den raka torpeden kommer in mot målet: grader från stäven (0 rakt förifrån, 180
        rakt akterifrån) och sidan. Bara när plottet vet kursen (målet går, kursens σ under taket)."""
        if sol.speed < ASPECT_MIN_KN or sol.course_sigma >= ASPECT_MAX_SIGMA:
            return None
        rel = angle_diff((torpedo_course + 180.0) % 360, sol.course)
        deg = abs(rel)
        return {"deg": deg, "side": "styrbord" if rel > 0 else "babord",
                "narrow": deg < NARROW_DEG or deg > 180 - NARROW_DEG}

    def _best_target(self) -> str | None:
        """Utan angiven kontakt: den enda hållna, annars hotkontakten med bäst lösning (närmast
        vid lika)."""
        tracks = self.game.knowledge.tracks.values()
        held = [t for t in tracks if t.held]
        if len(held) == 1:
            return held[0].designation
        cands = [t for t in held if t.threat and t.solution is not None]
        if not cands:
            return None
        best = max(cands, key=lambda t: (t.solution.quality, -t.solution.range_nm))
        return best.designation

    def _preview(self, designation: str | None) -> None:
        if designation is None:
            designation = self._best_target()
            if designation is None:
                self.say("torp.refused", {"reason": "vi har ingen kontakt med skjutlösning"})
                return
        tr, sol = self._solution_for(designation)
        if tr is None or sol is None:
            self.say("torp.refused", {"reason": f"vi har ingen lösning på {designation}"})
            return
        rows = []
        for key in self._aboard():
            row = {"type": key}
            if b := self._blocked(key):
                row["blocked"] = b
            elif (aim := self._aim(sol, key)) is not None:
                row["course"], row["run_s"] = aim[0], aim[1]
            else:
                row["course"] = None
            rows.append(row)
        straight = [r for r in rows if r.get("course") is not None
                    and not TORPEDO_TYPES[r["type"]].homing]
        aspect = self._aspect(sol, straight[0]["course"]) if straight else None
        self.say("torp.solution", {"designation": tr.designation, "quality": sol.quality,
                                   "rows": rows, "aspect": aspect}, quality=sol.quality)
        if straight:
            self._leg_warning(tr.designation, min(r["run_s"] for r in straight),
                              straight[0]["type"])
            if ships := self._neutrals_in_lane(tr.designation, [straight[0]["course"]],
                                               straight[0]["type"]):
                self.say("torp.neutral", {"ships": ships, "preview": True}, quality=Quality.GOD)
        loaded = {t.load for t in self.tubes if t.load and not t.loading}
        homing = [r for r in rows if r.get("course") is not None and r["type"] in loaded
                  and TORPEDO_TYPES[r["type"]].homing]
        if homing and (ships := self._seeker_rivals(tr.designation, homing[0]["course"],
                                                    homing[0]["type"])):
            self.say("torp.neutral", {"ships": ships, "preview": True, "homing": True,
                                      "target": tr.designation}, quality=Quality.GOD)
