"""Sändningen: rapporten, pejlrisken, kortvågens utstrålning och råden om när vi går upp."""
from __future__ import annotations

import math

from ...entities import Emission
from ...dispatch import SentReport, compose
from ...geo import angle_diff, distance
from ...reports import Quality
from ...ownship import ANTENNA_DEPTH, PERISCOPE_DEPTH
from .common import (
    AIR_LEFT_S, AIR_QUIET_S, RADIO_SAFE_NM, REPORT_SUGGEST_S, RISK_LONG_S, RISK_MID_NM,
    RISK_MID_S, RISK_NEAR_NM, VLF_DEPTH,
)


class SendingMixin:
    """Sändningen och dess risk, som RadioStation ärver. Risken bedöms ur plottet (kunskap)."""

    # --- rapporten ------------------------------------------------------------------
    def _events(self) -> tuple[str, ...]:
        """Det som hänt sedan förra rapporten (ur kunskapen)."""
        since = self.sent[-1].t if self.sent else -10**9
        out = []
        if self._photo_t is not None and self._photo_t > since:
            out.append("photo")
        if self._hit_t is not None and self._hit_t > since:
            out.append("hit")
        if self.game.knowledge.hunt_t > since:
            out.append("hunted")
        return tuple(out)

    def draft(self, kind: str = "full", target: str | None = None) -> SentReport:
        """Rapporten som den skulle se ut nu (för sändningen och för förslagen)."""
        nav = self._nav()
        x, y = self.game.own_position_estimate()
        sigma = nav.uncertainty() if nav is not None else 0.0
        return compose(self.game.knowledge, self.now, (x, y, sigma), kind, target,
                       self._events(), number=len(self.sent) + 1)

    def risk(self, seconds: float) -> tuple[str, Quality]:
        """Radiomannens bedömning av pejlrisken: sändningens längd och hotet i plottet."""
        near = self._far_threat()
        r_nm = near[1] if near else None
        q = Quality.GOD
        if near is not None:
            tr = next((t for t in self.game.knowledge.tracks.values()
                       if t.designation == near[0]), None)
            if tr is not None and tr.solution is not None:
                q = tr.solution.quality
        if seconds >= RISK_LONG_S or (r_nm is not None and r_nm <= RISK_NEAR_NM):
            return "stor", q
        if seconds >= RISK_MID_S or (r_nm is not None and r_nm <= RISK_MID_NM):
            return "måttlig", q
        return "liten", q

    def _truth_of(self, r: SentReport) -> dict:
        """Hur väl rapporten stämde (sanningen, bara för slutrapporten; staben vet det inte).
        Kontakternas läge räknas fram till nu med rapporterad kurs och fart."""
        from ..sonar_room import SonarRoom
        w, own = self.world, self.own.state
        x, y, _ = r.position
        out = {"t": self.now, "own_err_nm": distance(x, y, own.x, own.y), "contacts": []}
        sensor = next((st.sensor for st in self.game.stations if isinstance(st, SonarRoom)), None)
        for c in r.contacts:
            v = next((v for v in w.contacts if sensor is not None
                      and sensor.designation_of(v.id) == c.designation), None)
            if v is None:
                continue
            dt_h = (self.now - c.t) / 3600.0
            px = c.x + c.speed * dt_h * math.sin(math.radians(c.course))
            py = c.y + c.speed * dt_h * math.cos(math.radians(c.course))
            out["contacts"].append({
                "designation": c.designation,
                "id": v.id,                     # sanningens id (krigsskådeplatsen, aldrig till spelaren)
                "pos_err_nm": distance(px, py, v.state.x, v.state.y),
                "course_err": abs(angle_diff(c.course, v.state.course)),
                "speed_err": abs(c.speed - v.state.speed)})
        return out

    def _emit_hf(self, seconds: float) -> None:
        """Sändningen hörs i etern så länge den pågick: fiendens pejlnät (enemy.py)."""
        st = self.own.state
        self.world.emit_em(Emission("hf", st.x, st.y, self.own.id, self.now, duration=seconds))

    def _threat_near(self) -> tuple[str, float] | None:
        """Närmaste hotkontakt som plottet har inom RADIO_SAFE_NM (beteckning, sjömil)."""
        best = None
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            if not tr.threat or not tr.held or sol is None or sol.quality < Quality.OSAKER:
                continue
            if sol.range_nm < RADIO_SAFE_NM and (best is None or sol.range_nm < best[1]):
                best = (tr.designation, sol.range_nm)
        return best

    def _far_threat(self) -> tuple[str, float] | None:
        """Närmaste hotkontakt med en lösning, för att säga hur långt bort den är."""
        sols = [(tr.designation, tr.solution.range_nm) for tr in self.game.knowledge.tracks.values()
                if tr.threat and tr.held and tr.solution is not None
                and tr.solution.quality >= Quality.OSAKER]
        return min(sols, key=lambda p: p[1]) if sols else None

    def _clear_advice(self, i: int, w0: int) -> None:
        """Vi väntar på djupet: föreslå antenndjup när hotet gått längre bort."""
        if self._threat_near() is not None or self.game.knowledge.hunted(self.now):
            return
        self._waiting.discard(i)
        far = self._far_threat()
        d = {"designation": far[0] if far else "kontakten", "range": far[1] if far else RADIO_SAFE_NM,
             "close": self.game.clock_str(w0 + self.window_len)[:5]}
        up, _ = self._up_order()
        if up is None:
            return
        self.suggest(f"clear{i}", "radio.clear", {**d, "what": up}, order=up, cooldown=0)

    def _task_report_advice(self) -> None:
        """Staben har gett en spaningsuppgift (`rapport` i ordern, krigspatrullen): när plottet har
        en lösning på ett fartyg som kommit efter uppgiften, föreslå att sända rapporten (inte
        medan fienden har oss), först periskopdjup om vi är djupt."""
        k = self.game.knowledge
        if self.report_required or "rapport" not in k.order_tasks or self.tx_done_t is not None \
                or self._reported_t >= k.order_tasks_t:
            return
        if k.hunted(self.now) or self._threat_near() is not None or k.air_close_now():
            return
        best = None
        for tr in k.tracks.values():
            sol = tr.solution
            if not tr.held or tr.benign or tr.friendly or sol is None or \
                    sol.quality < Quality.OSAKER or tr.first_t < k.order_tasks_t:
                continue
            if best is None or sol.quality > best[1]:
                best = (tr.designation, sol.quality)
        if best is None:
            return
        st = self.own.state
        if st.depth <= PERISCOPE_DEPTH + 0.5:
            full = self.draft("full")
            risk, q = self.risk(full.duration_s)
            self.suggest("task_report", "radio.suggest.task_report",
                         {"now": True, "designation": best[0], "seconds": full.duration_s,
                          "risk": risk}, order="sänd rapport", cooldown=REPORT_SUGGEST_S, quality=q)
        else:
            self.suggest("task_report_up", "radio.suggest.task_report",
                         {"now": False, "designation": best[0]}, order="periskopdjup",
                         cooldown=REPORT_SUGGEST_S, quality=best[1])

    def _report_advice(self, w0: int) -> None:
        """Ordern kräver en rapport: föreslå periskopdjup och sedan sändningen, men inte
        medan fienden har oss (sändningen pejlas)."""
        if not self.report_required or self._reported_t >= w0 or self.tx_done_t is not None:
            return
        if self.game.knowledge.hunted(self.now) or self._threat_near() is not None:
            return
        st, k = self.own.state, self.game.knowledge
        air_recent = k.air_close_t is not None and self.now - k.air_close_t < AIR_QUIET_S
        if st.depth <= PERISCOPE_DEPTH + 0.5:
            if not k.air_close_now():           # flyget nära: vakthavande föreslår djup 60
                full, short = self.draft("full"), self.draft("short")
                risk, q = self.risk(full.duration_s)
                use_short = risk == "stor" and self.risk(short.duration_s)[0] != "stor"
                self.suggest("report_send", "radio.suggest.report",
                             {"now": True, "seconds": full.duration_s, "risk": risk,
                              "short": use_short, "short_s": short.duration_s},
                             order="sänd kort rapport" if use_short else "sänd rapport",
                             cooldown=REPORT_SUGGEST_S, quality=q)
        elif st.depth > ANTENNA_DEPTH + 0.5 and k.air_close_t is not None and k.air_close_t >= w0 \
                and not air_recent \
                and w0 + self.window_len - self.now >= AIR_LEFT_S:
            # flyget drev ned oss under fönstret: gå upp och se om det gått
            self.suggest(f"report_air{k.air_close_t}", "radio.suggest.air_clear",
                         {"minutes": round((self.now - k.air_close_t) / 60),
                          "close": self.game.clock_str(w0 + self.window_len)[:5]},
                         order="periskopdjup", cooldown=REPORT_SUGGEST_S)
        elif st.depth <= VLF_DEPTH + 0.5 and not air_recent and any(
                i in self._handled for i, w in enumerate(self.windows) if w == w0):
            self.suggest("report_depth", "radio.suggest.report", {"now": False},
                         order="periskopdjup", cooldown=REPORT_SUGGEST_S)
