"""Trådstyrningen: eldledningen styr försökstorpeden 53-62T längs tråden mot plottets lösning.

Kaptenen räknar inget: torpedrummet räknar om kursen var `GUIDE_STEP_S` ur plottets lösning och
torpedens beräknade läge (avfyrningspunkten och styrordern, aldrig sanningens läge), och släpper
målsökaren när torpeden enligt räkningen är `SEEKER_ON_NM` från målet. Tråden är vårt instrument:
torpedrummet märker genast när den går av, men vet bara varför om det var vår egen fart, gir
eller trådlängden. Kaptenens enda nya order är `kapa tråden`.
"""
from __future__ import annotations

import math

from ...firecontrol import intercept
from ...geo import angle_diff
from ...reports import Quality
from ...weapons import TORPEDO_TYPES, WIRE_MAX_SPEED, WIRE_MAX_TURN, cut_wire, guide_torpedo
from .common import GUIDE_MIN_DEG, GUIDE_STEP_S, SEEKER_ON_NM, WIRE_WARN_TURN, CutWire, Running

GUIDE_SAY_DEG = 10.0        # en styrorder så här stor sägs (de små går tyst)


def dr_position(r: Running, t: int) -> tuple[float, float]:
    """Torpedens beräknade läge vid tiden t: avfyrningspunkten och styrordern (rak gång per ben)."""
    return path(r, t)[-1]


def path(r: Running, t: int) -> list[tuple[float, float]]:
    """Den beräknade banan fram till t: en punkt per styrorder och läget vid t."""
    speed = TORPEDO_TYPES[r.type].speed
    legs = r.legs or [(r.launch_t, r.course)]
    x, y = r.launch_x, r.launch_y
    pts = [(x, y)]
    for i, (t0, course) in enumerate(legs):
        t1 = legs[i + 1][0] if i + 1 < len(legs) else t
        t1 = min(t1, t)
        if t1 <= t0:
            break
        run = speed * (t1 - t0) / 3600
        b = math.radians(course)
        x, y = x + run * math.sin(b), y + run * math.cos(b)
        pts.append((x, y))
    return pts


class WireMixin:
    """Trådstyrningen, som TorpedoRoom ärver."""

    def _wire_launched(self, r: Running, torp) -> None:
        """En trådstyrd torped har gått: styr den, eller (utan mål) släpp målsökaren direkt."""
        r.legs = [(self.now, r.course)]
        if r.designation is None:
            cut_wire(torp)              # skjuten på kurs: den söker själv som en SET-53
            r.seeker_on = True
            return
        r.wired = True
        self._wire_truth[r.no] = torp

    def _cut_wire(self, o: CutWire) -> None:
        runs = [r for r in self.in_water if r.wired and (o.tube is None or r.tube == o.tube)]
        if not runs:
            self.say("torp.refused", {"reason": "ingen trådstyrd torped i vattnet" if o.tube is None
                                      else f"torpeden från tub {o.tube} går inte på tråd"})
            return
        for r in runs:
            cut_wire(self._wire_truth.pop(r.no))
            self._wire_ended(r)
        self.say("torp.wire.cut", {"tubes": [r.tube for r in runs]}, kind="ack")

    def _wire_ended(self, r: Running) -> None:
        r.wired, r.seeker_on, r.wire_end_t = False, True, self.now

    def _guide(self) -> None:
        for r in [r for r in self.in_water if r.wired]:
            torp = self._wire_truth.get(r.no)
            if torp is None:
                continue
            if not torp.wire_ok:
                self._wire_broke(r)
                continue
            self._strain(r)
            if (self.now - r.launch_t) % GUIDE_STEP_S == 0 and self.now > r.launch_t:
                self._steer(r, torp)
        if any(r.wired for r in self.in_water) and self.game.knowledge.torpedo_alarm(self.now):
            self.suggest("cutwire", "torp.suggest.cut_wire", order="kapa tråden", cooldown=180)

    def _launch_course(self, r: Running) -> float:
        return self._wire_truth[r.no].wire_course

    def _wire_broke(self, r: Running) -> None:
        """Tråden är av. Varför vet vi bara om det var vi: farten, giren eller längden."""
        torp = self._wire_truth.pop(r.no)
        spec = TORPEDO_TYPES[r.type]
        st = self.own.state
        if spec.speed * (self.now - r.launch_t) / 3600 >= spec.wire_nm - 0.05:
            why = "längd"
        elif st.speed > WIRE_MAX_SPEED:
            why = "fart"
        elif abs(angle_diff(st.course, torp.wire_course)) > WIRE_MAX_TURN:
            why = "gir"
        else:
            why = ""
        self._wire_ended(r)
        self.say("torp.wire.broken", {"tube": r.tube, "why": why, "course": r.course},
                 alarm=why != "längd")

    def _strain(self, r: Running) -> None:
        """Varna en gång när vår fart eller gir håller på att slita av tråden."""
        st = self.own.state
        turn = abs(angle_diff(st.course, self._launch_course(r)))
        why = "fart" if st.speed > WIRE_MAX_SPEED else "gir" if turn > WIRE_WARN_TURN else ""
        if why and why != r.strain_said:
            self.say("torp.wire.strain", {"tube": r.tube, "why": why,
                                          "limit": WIRE_MAX_SPEED if why == "fart" else WIRE_MAX_TURN},
                     alarm=True)
        r.strain_said = why

    def _steer(self, r: Running, torp) -> None:
        """Ny kurs mot plottets lösning från torpedens beräknade läge; nära målet: målsökaren."""
        tr, sol = self._solution_for(r.designation)
        if sol is None:
            if not r.no_solution_said:
                r.no_solution_said = True
                self.say("torp.wire.no_solution", {"tube": r.tube, "designation": r.designation},
                         quality=Quality.OSAKER)
            return
        r.no_solution_said = False
        tx, ty = dr_position(r, self.now)
        rel_x, rel_y = sol.x - tx, sol.y - ty
        spec = TORPEDO_TYPES[r.type]
        if math.hypot(rel_x, rel_y) <= SEEKER_ON_NM:
            cut_wire(self._wire_truth.pop(r.no))     # tråden kapas när målsökaren tar över
            self._wire_ended(r)
            self.say("torp.wire.seeker", {"tube": r.tube, "designation": r.designation},
                     quality=sol.quality)
            return
        res = intercept(rel_x, rel_y, sol.state[2], sol.state[3], spec.speed)
        if res is None:
            course, run_h = math.degrees(math.atan2(rel_x, rel_y)) % 360, None
        else:
            course, run_h = res
        if run_h is not None:
            r.t_hit = int(self.now + run_h * 3600)
            r.timed = r.timed and self.now >= r.t_hit
        change = angle_diff(course, r.course)
        if abs(change) < GUIDE_MIN_DEG or not guide_torpedo(torp, course):
            return
        r.legs.append((self.now, course))
        r.course = course
        if abs(change) >= GUIDE_SAY_DEG:
            self.say("torp.wire.guide", {"tube": r.tube, "course": course,
                                         "designation": r.designation}, quality=sol.quality)
