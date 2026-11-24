"""Orakel: larm mot sanningen för botarna (skytt.py och andra). Följer ett spel och flaggar det som
troligen är en bugg, med tid och de senaste rapporterna. Varje larm är ett fel vi hittat för hand
förut (2026-11-23), nu automatiskt:

- grund_utan_varning: grundstötning utan navigatörens varning (land, grund, kortets land) de sista
  10 min (Clyde: kortet framåt utan bestickets osäkerhet framåt).
- skjutläge_för_djupt: "vi är i skjutläge" djupare än torpedernas skjutdjup utan förslag om att gå upp
  (inte när de har oss: då är djupet kaptenens val).
- tjatar: samma förslag (samma order) levererat 4+ gånger på 20 min (pingpongen periskopdjup/djup 50).
- låg_fart_kvar: en tillfällig låg fart (lyssningsgiren, ≤ 4 kn) som ingen tagit tillbaka efter
  30 min, utan jakt, styruppdrag eller smygmotor (lyssningsgiren som glömdes).
- säker_men_fel: plottet säger säker och avståndet är > 50 % fel eller kursen > 90° fel (mål > 3 kn).
- neutral_utan_varning: ett neutralt fartyg sjunker utan torpedrummets varning (neutral, bekräftelse)
  de senaste 15 min.
- text: oifyllda fält, punkt som decimaltecken, kurs utan tre siffror, sanningens id:n.
- undantag: ett undantag i spelet (fångas av boten).

Användning: o = Orakel(game); varje tick o.tick(); o.larm är listan (typ, klocka, text, sammanhang).
"""
from __future__ import annotations

import math
import re
from collections import deque

from sim.events import ReportDelivered
from sim.geo import angle_diff, distance
from sim.reports import Quality

NAV_WARN = ("nav.suggest.land", "nav.suggest.shoal", "nav.suggest.chart_land", "nav.suggest.land_astern",
            "nav.shoal", "nav.echo")
WARN_S = 600
NAG_N, NAG_S = 4, 1200
# förslag som ska upprepas: korta periskoptittar mot konvojen, upp för en titt
NAG_OK = ("off.suggest.convoy_look", "off.suggest.convoy_up", "torp.ready")
SLOW_KN, SLOW_S = 4, 1800
# förslag om låg fart som ska tas tillbaka (sonars "Vi hör dåligt" är menat att stå kvar)
TEMP_SLOW = ("sonar.suggest.clear_baffles", "sonar.suggest.record_close")
NEUTRAL_WARN_S = 900
FIRE_DEPTH_M = 100
TRUTH_ID = re.compile(r"\b(DD|T|SS|M|CV|P|AC|N)\d+\b")
DOT_DEC = re.compile(r"\b\d+\.\d+\s*(nm|kn|m\b|knop|sjömil|meter|grader|°)")
SHORT_COURSE = re.compile(r"\bkurs (\d{1,2})\b")
TEXT_SKIP = ("system.help", "order.unknown")


class Orakel:
    def __init__(self, game, context: int = 8):
        self.g = game
        self.larm: list[tuple[str, str, str, list[str]]] = []
        self.recent: deque = deque(maxlen=context)
        self.last_nav_warn = -10**9
        self.suggested: dict[str, list[int]] = {}
        self.slow_since: int | None = None
        self.slow_suggested_t = -10**9
        self.neutral_warn_t = -10**9
        self.sunk_seen: set[str] = set()
        self.grounded = False
        self.arrived_t: int | None = None
        self.fire_depth_suggested = False
        self._said: set[tuple[str, str]] = set()
        game.bus.subscribe(ReportDelivered, self._on)

    # --- hjälp ---------------------------------------------------------------------
    def flag(self, kind: str, text: str, once_key: str | None = None) -> None:
        key = (kind, once_key or text)
        if key in self._said:
            return
        self._said.add(key)
        self.larm.append((kind, self.g.clock_str(), text, list(self.recent)))

    def _truth(self, designation: str):
        from sim.stations.sonar_room import SonarRoom
        sensor = self.g.station(SonarRoom).sensor
        for v in self.g.world.contacts:
            if sensor.designation_of(v.id) == designation:
                return v
        return None

    # --- rapporterna ---------------------------------------------------------------
    def _on(self, e) -> None:
        r, g = e.report, self.g
        txt = r.text or ""
        self.recent.append(f"{g.clock_str()} {r.type}: {txt[:140]}")
        if r.type in NAV_WARN:
            self.last_nav_warn = g.now
        if r.type.startswith(("torp.neutral", "torp.confirm")):
            self.neutral_warn_t = g.now
        if r.kind == "suggest" and r.data.get("order") and r.type not in NAG_OK:
            m = re.search(r"\bfart (\d+)", r.data["order"])
            if m and int(m.group(1)) <= SLOW_KN and r.type in TEMP_SLOW:
                self.slow_suggested_t = g.now
            ts = [t for t in self.suggested.get(r.data["order"], []) if g.now - t <= NAG_S] + [g.now]
            self.suggested[r.data["order"]] = ts
            if len(ts) >= NAG_N:
                self.flag("tjatar", f"{r.type} '{r.data['order']}' {len(ts)} gånger på "
                          f"{(ts[-1] - ts[0]) // 60} min", once_key=r.data["order"])
        if r.type == "nav.attack.arrived":
            self.arrived_t = g.now
            self.fire_depth_suggested = False
        if self.arrived_t is not None and r.kind == "suggest" and \
                re.search(r"\bdjup (\d+)", r.data.get("order", "")) and \
                int(re.search(r"\bdjup (\d+)", r.data["order"]).group(1)) <= FIRE_DEPTH_M:
            self.fire_depth_suggested = True       # navigatören föreslår skjutdjup
        if r.type == "plot.improved" and r.quality == Quality.SAKER and r.data.get("designation"):
            self._check_solution(r.data["designation"])
        if r.type not in TEXT_SKIP:
            for bad in ("None", " nan", "{", "}", "inf ", "Traceback", "[]", "()"):
                if bad in txt:
                    self.flag("text", f"'{bad}' i {r.type}: {txt[:160]}", once_key=r.type + bad)
            m = TRUTH_ID.search(txt)
            if m and not re.search(r"\b[A-Z]-\d", txt[max(0, m.start() - 2):m.end()]):
                self.flag("text", f"sanningsid {m.group()} i {r.type}: {txt[:160]}", once_key=r.type)
            if DOT_DEC.search(txt):
                self.flag("text", f"punktdecimal i {r.type}: {txt[:160]}", once_key=r.type + ".")
            if SHORT_COURSE.search(txt):
                self.flag("text", f"kurs utan tre siffror i {r.type}: {txt[:160]}", once_key=r.type + "k")

    def _check_solution(self, designation: str) -> None:
        g = self.g
        tr = g.knowledge.track(designation)
        v = self._truth(designation)
        if tr is None or tr.solution is None or v is None:
            return
        sol, o = tr.solution, g.world.own.state
        r = distance(o.x, o.y, v.state.x, v.state.y)
        rel = abs(sol.range_nm - r) / max(r, 0.05)
        crs = abs(angle_diff(sol.course, v.state.course)) if v.state.speed > 3 else 0.0
        if rel > 0.5 or crs > 90:
            self.flag("säker_men_fel", f"{designation} ({v.kind}): plottet {sol.range_nm:.1f} nm kurs "
                      f"{sol.course:.0f}, sant {r:.1f} nm kurs {v.state.course:.0f}",
                      once_key=f"{designation}{g.now // 600}")

    # --- varje tick ----------------------------------------------------------------
    def tick(self) -> None:
        g = self.g
        w, o = g.world, g.world.own.state
        if not self.grounded and "grounded_t" in w.mission:
            self.grounded = True
            if g.now - self.last_nav_warn > WARN_S:
                self.flag("grund_utan_varning", f"på grund i {o.speed:.1f} kn på {o.depth:.0f} m, "
                          f"senaste varning {(g.now - self.last_nav_warn) // 60} min sedan")
        if self.arrived_t is not None and g.now - self.arrived_t == 10:
            self.arrived_t = None
            # jagade: djupt är kaptenens val (sprinten samma sekund, krig-kort 12); navigatören
            # föreslår skjutdjupet när jakten lugnat sig (_fire_depth_watch)
            if o.ordered_depth > FIRE_DEPTH_M and not self.fire_depth_suggested and \
                    not g.knowledge.hunted(g.now):
                self.flag("skjutläge_för_djupt", f"i skjutläget på {o.ordered_depth:.0f} m beordrat djup")
        for v in w.contacts:
            if v.sunk and v.side == "neutral" and getattr(v, "is_ship", False) and v.id not in self.sunk_seen:
                self.sunk_seen.add(v.id)
                if g.now - self.neutral_warn_t > NEUTRAL_WARN_S:
                    self.flag("neutral_utan_varning", f"neutralt {v.kind} sänkt utan varning")
        if g.now % 60:
            return
        from sim.stations.navigation import NavigationStation
        nav = g.station(NavigationStation)
        busy = g.knowledge.hunted(g.now) or nav.steer is not None or nav.vak is not None or \
            g.world.own.sys.propulsion == "electric" or o.depth < 1
        if 0 < o.ordered_speed <= SLOW_KN and not busy and \
                (self.slow_since is not None or g.now - self.slow_suggested_t <= 180):
            # bara en låg fart som besättningen föreslog (i Kuba går vi 3 kn från start)
            self.slow_since = self.slow_since if self.slow_since is not None else g.now
            if g.now - self.slow_since >= SLOW_S:
                self.flag("låg_fart_kvar", f"fart {o.ordered_speed:.0f} beordrad i "
                          f"{(g.now - self.slow_since) // 60} min utan jakt eller uppdrag",
                          once_key=str(self.slow_since))
        else:
            self.slow_since = None
