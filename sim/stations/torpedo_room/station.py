"""Torpedrummet: stationen, order, laddning, torpederna i vattnet och kortet."""
from __future__ import annotations

import math

from ...chart import LAYER_RAY, Mark, Ray, Track
from ...crew import Role
from ...events import CouncilHeld, HuntSigns, OwnSoundMade, OwnTorpedoHeard
from ...orders import DESIG, NUM, AskContact, CommandSpec, Order, desig, num
from ...reports import Quality
from ...sonar_view import TorpedoTrace
from ...systems import INFO, OK, WARN, Gauge, TubeRack
from ...entities import Transient
from ... import acoustics
from ...weapons import TORPEDO_TYPES, launch_decoy
from ..base import Proposal, Station
from .common import (
    DECOY_SUGGEST_S, EARLY_FRACTION, EARLY_MIN_S, END_GRACE_S, CutWire, FireAt, FireSalvo, FireTube, FiringSolution, LaunchDecoy, LoadTube, N_TUBES,
    RELOAD_CLANK_S, RELOAD_COOLDOWN_S, RELOAD_QUIET_S, RELOAD_S, RELOAD_SUGGEST_S,
    RELOAD_URGENT_COOLDOWN_S, RUN_REPORT_AFTER, Running, TRACK_FADE_S,
    TRACK_KEEP_S, TorpedoReport, TorpedoStatus, Tube, TubeStatus, load_order,
)
from .firing import FiringMixin
from .wire import WireMixin, dr_position, path


class TorpedoRoom(FiringMixin, WireMixin, Station):
    REACHES_WORLD = True        # torpeder och skenmål i vattnet, uppdragets flaggor
    role = Role.TORPEDO
    COMMANDS = [
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+(?:mot\s+)?{DESIG}",
                    lambda m: FireAt(desig(m[1])), "eld S-1 (torpedrummet väljer tub)"),
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+tub\s+(\d)\s+(?:mot\s+)?{DESIG}",
                    lambda m: FireTube(int(m[1]), designation=desig(m[2]))),
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+tub\s+(\d)\s+kurs\s+{NUM}",
                    lambda m: FireTube(int(m[1]), course=num(m[2]) % 360), "eld tub 1 kurs 045"),
        CommandSpec(r"ladda\s+tub\s+(\d)\s+(?:med\s+)?(\S+)", load_order, "ladda tub 7 SET-53"),
        CommandSpec(r"torped|torpedrummet", lambda m: TorpedoReport(), "torped (tuberna och torpederna i vattnet)"),
        CommandSpec(r"tuber|torpedrum", lambda m: TubeStatus()),
        CommandSpec(r"torpeder|torpedläge|torpedlage|torpeder i vattnet",
                    lambda m: TorpedoStatus()),
        CommandSpec(rf"(?:skjutlösning|skjutlosning|eldlösning|eldlosning)(?:\s+{DESIG})?",
                    lambda m: FiringSolution(desig(m[1]))),
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+tub\s+(\d)\s*-\s*(\d)\s+(?:mot\s+)?{DESIG}",
                    lambda m: FireSalvo(desig(m[3]), tuple(range(min(int(m[1]), int(m[2])),
                                                                 max(int(m[1]), int(m[2])) + 1)))),
        CommandSpec(rf"salva\s+(?:mot\s+)?{DESIG}", lambda m: FireSalvo(desig(m[1])), "salva S-1"),
        CommandSpec(r"skenmål|skenmal|motmedel", lambda m: LaunchDecoy(), "skenmål"),
        CommandSpec(r"kapa\s+tr[åa]d(?:en|arna)?(?:\s+(?:på\s+|pa\s+)?tub\s+(\d))?",
                    lambda m: CutWire(int(m[1]) if m[1] else None),
                    "kapa tråden (trådstyrd torped: målsökaren tar över)"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.tubes = [Tube(i + 1) for i in range(N_TUBES)]
        self._confirmed: dict[str, int] = {}     # kontakt -> när vi frågade om den
        self._nuclear_confirm_t = -10**9          # när vi frågade om kärnladdningen
        self._neutral_warned: dict[str, int] = {}   # mål (eller "kurs") -> när vi varnade
        self._emptied: dict[int, int] = {}       # tub -> när den sköts tom (omladdningsförslaget)
        for t in self.tubes[:4]:
            t.load = "53-61"
        for t in self.tubes[4:6]:
            t.load = "SET-53"
        self.inventory = {"53-61": 6, "SET-53": 4, "53-62T": 2, "T-5": 2}
        arm = getattr(game.scenario, "armament", None)
        if arm:                                   # t.ex. övningen: bara övningstorpeder
            for t in self.tubes:
                t.load = arm["tubes"].get(t.n)
            self.inventory = dict(arm["inventory"])
        self.decoys = 6
        self.in_water: list[Running] = []
        self.finished: list[Running] = []         # ritas kvar på kortet en stund
        self._launches = 0
        self._ready_said: dict[str, Quality] = {}
        self._wire_truth: dict = {}               # trådstyrd torped i vattnet: nr -> torpeden (tråden)

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(HuntSigns, self._on_hunt)
        bus.subscribe(OwnTorpedoHeard, self._on_own_torpedo)
        bus.subscribe(CouncilHeld, self._note_council)

    def _note_council(self, e: CouncilHeld) -> None:
        """Sanningen bakom rådets bedömning, till slutrapporten (`goals.council_summary`)."""
        from ...goals import COUNCIL_NEAR_M, COUNCIL_TRUTH_S
        log = [c for c in self.world.mission.get("charge_log", [])
               if e.t - c[0] <= COUNCIL_TRUTH_S and c[2] <= COUNCIL_NEAR_M]
        self.world.mission.setdefault("councils", []).append({
            "t": e.t, "clock": self.game.clock_str(e.t)[:5], "zampolit": e.zampolit, "starpom": e.starpom, "order": e.order,
            "believed_attacked": e.attacked, "quality": e.attacked_q.label,
            "real_near": sum(1 for c in log if not c[1]),
            "signal_near": sum(1 for c in log if c[1])})


    # --- order -------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        match order:
            case FireTube():
                self._fire(order)
            case FireSalvo():
                self._salvo(order)
            case LoadTube(tube=n, type=typ):
                self._load(n, typ)
            case TubeStatus():
                self.say("torp.status", {
                    "tubes": [{"n": t.n, "load": t.load, "loading": t.loading} for t in self.tubes],
                    "inventory": dict(self.inventory), "decoys": self.decoys})
            case TorpedoStatus():
                self._report_in_water()
            case FiringSolution(designation=d):
                self._preview(d)
            case FireAt(designation=d):
                self._fire_at(d)
            case TorpedoReport():
                self.on_order(TubeStatus())
                if self.in_water:
                    self._report_in_water()
            case AskContact(designation=d):
                self._contact_asked(d)
            case CutWire():
                self._cut_wire(order)
            case LaunchDecoy():
                if self.decoys <= 0:
                    self.say("torp.refused", {"reason": "skenmålen är slut"})
                    return
                self.decoys -= 1
                launch_decoy(self.world)
                self.game.bus.publish(OwnSoundMade(self.now, "decoy"))
                self.say("torp.decoy", {"left": self.decoys}, kind="ack")

    def _load(self, n: int, typ: str) -> None:
        tube = self._tube(n)
        if tube is None:
            self.say("torp.refused", {"reason": f"det finns ingen tub {n}"})
        elif tube.load or tube.loading:
            self.say("torp.refused", {"reason": f"tub {n} är inte tom"})
        elif self.inventory.get(typ, 0) <= 0:
            self.say("torp.refused", {"reason": f"vi har inga {typ} kvar"})
        else:
            self.inventory[typ] -= 1
            self._emptied.pop(n, None)
            tube.loading = typ
            tube.quiet = self._load_quietly()
            tube.clanked = 0
            tube.ready_t = self.now + (RELOAD_QUIET_S if tube.quiet else RELOAD_S)
            self.say("torp.loading", {"tube": n, "type": typ, "quiet": tube.quiet}, kind="ack")

    def _load_quietly(self) -> bool:
        """Minören laddar försiktigt när vi smyger eller är jagade (ingen order)."""
        return self.own.sys.propulsion == "electric" or self.game.knowledge.hunted(self.now)

    def _clank(self, tube: Tube) -> None:
        """Torpeden går in i tuben, bakluckan stängs: metall mot metall som hörs i vattnet."""
        tube.clanked += 1
        o = self.own.state
        level = acoustics.RELOAD_LEVEL - (acoustics.RELOAD_QUIET_DB if tube.quiet else 0.0)
        self.world.emit(Transient("reload", o.x, o.y, o.depth, level, self.own.id, self.now))
        self.game.bus.publish(OwnSoundMade(self.now, "reload"))

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        for t in self.tubes:
            if t.loading:
                total = RELOAD_QUIET_S if t.quiet else RELOAD_S
                if t.clanked == 0 and self.now >= t.ready_t - total + RELOAD_CLANK_S:
                    self._clank(t)
                elif t.clanked == 1 and self.now >= t.ready_t:
                    self._clank(t)
            if t.loading and self.now >= t.ready_t:
                t.load, t.loading = t.loading, None
                self.say("torp.loaded", {"tube": t.n, "type": t.load})
        self._guide()
        for r in list(self.in_water):
            if r.t_hit is not None and not r.timed and self.now >= r.t_hit:
                r.timed = True
                tr = self.game.knowledge.tracks.get(r.designation) if r.designation else None
                self.say("torp.time.sunk" if tr is not None and tr.sunk else "torp.time",
                         {"tube": r.tube, "designation": r.designation}, kind="info")
            if self.now >= r.t_end + END_GRACE_S:
                self._finish(r, "timeout")
                if TORPEDO_TYPES[r.type].exercise:
                    self.say("torp.run.exercise_end", {"tube": r.tube})
                else:
                    self.say("torp.run.timeout", {"tube": r.tube}, quality=Quality.OSAKER)

        if self.now % 30 == 0:
            self._readiness()
            self._suggest_reload()

    def _readiness(self) -> None:
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            # eget fartyg bara under torpedövningen (övningsledaren säger när)
            own_target = tr.friendly and tr.held and self.game.knowledge.torpedo_exercise
            if not (tr.threat or own_target) or sol is None \
                    or sol.quality < Quality.GOD:
                continue
            if any(r.designation == tr.designation for r in self.in_water):
                continue            # våra torpeder är på väg dit: inget nytt skott förrän de är framme
            if self._ready_said.get(tr.designation, Quality.DALIG) >= sol.quality:
                continue
            for tube in self.tubes:
                # mot vårt eget fartyg bara med övningstorped
                if tr.friendly and not (tube.load and TORPEDO_TYPES[tube.load].exercise):
                    continue
                if tube.load and not self._blocked(tube.load) and \
                        (aim := self._aim(sol, tube.load)) is not None:
                    self._ready_said[tr.designation] = sol.quality
                    self.suggest(f"ready{tr.designation}", "torp.ready",
                                 {"designation": tr.designation, "tube": tube.n,
                                  "type": tube.load, "run_s": aim[1]},
                                 quality=sol.quality, cooldown=0)
                    break

    # --- omladdning ------------------------------------------------------------------
    def _reload_offer(self, tubes=None, straight: bool = False) -> tuple[int, str] | None:
        """Första tomma tuben och vad minören laddar: konventionella vapen, det vi har mest av (en
        rak för salvan); kärnladdningen laddas bara på uttrycklig order."""
        stock = [k for k in (("53-61",) if straight else ("SET-53", "53-61"))
                 if self.inventory.get(k, 0) > 0]
        if not stock:
            return None
        for t in self.tubes:
            if t.load is None and t.loading is None and (tubes is None or t.n in tubes):
                return t.n, max(stock, key=lambda k: self.inventory[k])
        return None

    def _suggest_reload(self, urgent: bool = False, straight: bool = False) -> None:
        """Föreslå omladdning av en tub vi skjutit tom, en minut efter skottet och inte medan de
        har oss (slammer). `urgent`: kaptenen ville skjuta men ingen tub kunde; då genast, också
        under jakt (minören laddar då försiktigt)."""
        if urgent:
            offer = self._reload_offer(straight=straight)
        else:
            if self.game.knowledge.hunted(self.now):
                return
            ready = [n for n, t in self._emptied.items() if self.now - t >= RELOAD_SUGGEST_S]
            offer = self._reload_offer(ready) if ready else None
        if offer is None:
            return
        n, typ = offer
        self.suggest("reload_now" if urgent else f"reload{n}", "torp.suggest.reload",
                     {"tube": n, "type": typ}, order=f"ladda tub {n} {typ}",
                     cooldown=RELOAD_URGENT_COOLDOWN_S if urgent else RELOAD_COOLDOWN_S)

    # --- initiativ vid tystnad -------------------------------------------------------
    def idle_proposals(self) -> list[Proposal]:
        if self.game.knowledge.hunted(self.now):   # slammer under jakt: inte självmant
            return []
        offer = self._reload_offer()
        if offer is None:
            return []
        n, typ = offer
        return [Proposal(5, f"idle_reload{n}", "torp.suggest.reload",
                         f"ladda tub {n} {typ}", {"tube": n, "type": typ})]

    # --- sjökortet -------------------------------------------------------------------
    def system_items(self) -> list:
        rack = TubeRack(tuple((t.n, t.load, t.loading,
                               max(0, t.ready_t - self.now) if t.loading else 0)
                              for t in self.tubes))
        stock = ", ".join(f"{k} {n}" for k, n in self.inventory.items())
        items: list = [rack,
                       Gauge("VAPEN", "Reserv", stock or "slut",
                             WARN if not any(self.inventory.values()) else OK),
                       Gauge("VAPEN", "Skenmål", f"{self.decoys} kvar",
                             WARN if self.decoys == 0 else OK)]
        if self.in_water:
            items.append(Gauge("VAPEN", "I vattnet", ", ".join(
                f"tub {r.tube}" + (f" mot {r.designation}" if r.designation else "")
                + (" (tråd)" if r.wired else "") for r in self.in_water), INFO))
        return items

    def _early_s(self, r: Running) -> int | None:
        """Hur långt före beräknad träfftid torpeden detonerade, om det är tydligt för tidigt
        (mer än EARLY_MIN_S och en fjärdedel av gångtiden); annars None."""
        if r.t_hit is None or TORPEDO_TYPES[r.type].nuclear:
            return None
        early = r.t_hit - self.now
        return early if early > max(EARLY_MIN_S, EARLY_FRACTION * (r.t_hit - r.launch_t)) else None

    def _finish(self, r: Running, how: str) -> None:
        self.in_water.remove(r)
        self._wire_truth.pop(r.no, None)
        r.wired = False
        r.end_t, r.end = self.now, how
        self.finished.append(r)

    def sonar_items(self) -> list:
        """Vattenfallet: våra torpeders bäringar som sonar hört dem, med tubens nummer."""
        return [TorpedoTrace(f"tub {r.tube}", tuple(r.heard), hostile=False,
                             held=r in self.in_water and not r.lost)
                for r in self.finished + self.in_water if r.heard]

    def chart_items(self) -> list:
        """Egna torpeder som eldledningen räknar dem: från avfyrningspunkten längs den
        inställda kursen så långt de hunnit, med minutstreck. Har en målsökande torped
        girat ritas också den hörda bäringen."""
        self.finished = [r for r in self.finished if self.now - r.end_t < TRACK_KEEP_S]
        items: list = []
        x, y = self.game.own_position_estimate()
        for r in self.finished + self.in_water:
            done = r.end_t is not None
            faded = done and self.now - r.end_t >= TRACK_FADE_S or r.lost
            speed = TORPEDO_TYPES[r.type].speed
            t = min(self.now if not done else r.end_t, r.t_end)
            run = speed * max(0, t - r.launch_t) / 3600
            pts = path(r, t)            # trådstyrd: en bit per styrorder
            hx, hy = pts[-1]
            if len(pts) < 2:
                pts.append(pts[0])
            for a, b2 in zip(pts, pts[1:]):
                items.append(Track((a, b2), "torpedo_path", LAYER_RAY, None))
            for m in range(1, int((t - r.launch_t) // 60) + 1):
                mx, my = dr_position(r, r.launch_t + 60 * m)
                items.append(Mark(mx, my, "+", "torpedo", faded=True, layer=LAYER_RAY + 0.1))
            head = "✱" if r.end in ("hit", "early") else "?" if done or r.lost else "•"
            items.append(Mark(hx, hy, head, "torpedo", f"tub {r.tube}", faded=faded))
            if r.turned and r.bearing is not None and not done:
                items.append(Ray(x, y, r.bearing, max(run, 0.1), "torpedo", "hörd",
                                 faded=r.lost))
        return items

    # --- torpeder i vattnet ---------------------------------------------------------
    def _report_in_water(self) -> None:
        rows = []
        for r in self.in_water:
            rows.append({
                "tube": r.tube, "type": r.type, "designation": r.designation,
                "course": r.course, "elapsed": self.now - r.launch_t,
                "to_hit": None if r.t_hit is None else r.t_hit - self.now,
                "to_end": max(0, r.t_end - self.now),
                "bearing": r.bearing, "lost": r.lost, "turned": r.turned,
                "wired": r.wired, "seeker_on": r.seeker_on,
                "guided": r.legs is not None and r.designation is not None})
        self.say("torp.in_water", {"running": rows})

    def _on_own_torpedo(self, e: OwnTorpedoHeard) -> None:
        r = next((x for x in self.in_water if x.no == e.no), None)
        if r is None:
            return
        d = {"tube": r.tube, "bearing": e.bearing if e.bearing is not None else r.bearing}
        if e.kind in ("running", "turned") and e.bearing is not None:
            r.heard.append((self.now, e.bearing, e.se))       # till vattenfallet
        match e.kind:
            case "running":
                r.bearing, r.heard_t, r.lost = e.bearing, self.now, False
                if not r.confirmed and self.now - r.launch_t >= RUN_REPORT_AFTER:
                    r.confirmed = True
                    self.say("torp.run.running", d, quality=e.quality)
            case "turned":
                r.bearing, r.heard_t, r.turned = e.bearing, self.now, True
                # en trådstyrd torped girar på vår styrorder: det är inte målsökaren
                if TORPEDO_TYPES[r.type].homing and (r.legs is None or r.seeker_on):
                    self.say("torp.run.turned", d, quality=e.quality, alarm=True)
            case "lost":
                r.lost = True
                self.say("torp.run.lost", d)
            case "detonated" if (early := self._early_s(r)) is not None:
                # långt före beräknad tid: inte vid målet (förtidsdetonation, grund, annat fartyg)
                self._finish(r, "early")
                self.say("torp.run.early", {**d, "early_s": early, "designation": r.designation},
                         kind="contact", quality=Quality.GOD, alarm=True)
            case "detonated":
                self._finish(r, "hit")
                self.say("torp.run.hit", {**d, "nuclear": TORPEDO_TYPES[r.type].nuclear},
                         kind="contact", quality=Quality.SAKER, alarm=True)
            case "dud":
                self._finish(r, "dud")
                self.say("torp.run.dud", d, kind="contact", quality=e.quality, alarm=True)
            case "silent":
                self._finish(r, "silent")
                self.say("torp.run.silent", d, quality=Quality.GOD)

    def _on_hunt(self, e: HuntSigns) -> None:
        """Sonar säger att de har oss (täta starka pingar, sjunkbomber): skenmål. Täta svaga pingar
        långt bort (sonar.ping.fast_far) är någon annans jakt och ger inget förslag."""
        if self.decoys > 0 and e.reason in ("ping", "splash"):
            # glest: sex skenmål räcker annars en timme i en lång jakt
            self.suggest("decoy", "torp.suggest.decoy", {"left": self.decoys}, order="skenmål",
                         cooldown=DECOY_SUGGEST_S)
