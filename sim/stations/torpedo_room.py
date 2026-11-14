"""Torpedrum och eldledning: tuber, laddning, skjutlösningar, avfyring och skenmål.

Eldledningen räknar bara på kunskap: plottlagets lösning och navigatörens
bestick. Avfyring kräver alltid en uttrycklig order; torpedofficeren
meddelar när en skjutlösning finns men föreslår aldrig avfyring som en
order som kan godkännas med "ja".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import phrases
from ..crew import Role
from ..events import SoundHeard
from ..fmt import fmt_course, nm
from ..firecontrol import intercept
from ..orders import DESIG, NUM, CommandSpec, Order, Unknown, desig, num
from ..reports import Quality
from ..weapons import TORPEDO_TYPES, launch_decoy, launch_torpedo
from .base import Station

N_TUBES = 8
RELOAD_S = 300
MAX_LAUNCH_DEPTH = 120
MAX_LAUNCH_SPEED = 12

TYPE_ALIASES = {
    "53-61": "53-61", "53": "53-61", "rak": "53-61", "raka": "53-61",
    "set-53": "SET-53", "set53": "SET-53", "set": "SET-53", "målsökande": "SET-53",
    "malsokande": "SET-53",
    "t-5": "T-5", "t5": "T-5", "kärn": "T-5", "karn": "T-5", "kärnladdning": "T-5",
}


@dataclass(frozen=True)
class FireTube(Order):
    tube: int
    designation: str | None = None
    course: float | None = None


@dataclass(frozen=True)
class LoadTube(Order):
    tube: int
    type: str


@dataclass(frozen=True)
class TubeStatus(Order):
    pass


@dataclass(frozen=True)
class FiringSolution(Order):
    designation: str | None


@dataclass(frozen=True)
class LaunchDecoy(Order):
    pass


def _load(m: re.Match) -> Order:
    t = TYPE_ALIASES.get(m[2])
    if t is None:
        return Unknown("", "okänd torpedtyp, välj 53-61, SET-53 eller T-5")
    return LoadTube(int(m[1]), t)


@dataclass
class Tube:
    n: int
    load: str | None = None
    loading: str | None = None
    ready_t: int = 0


def _mmss(s: float) -> str:
    s = int(round(s))
    return f"{s // 60} min {s % 60:02d} s"


def _tubes(d: dict) -> str:
    parts = []
    for t in d["tubes"]:
        if t["loading"]:
            parts.append(f"{t['n']}: laddas {t['loading']}")
        else:
            parts.append(f"{t['n']}: {t['load'] or 'tom'}")
    inv = ", ".join(f"{k} {v}" for k, v in d["inventory"].items())
    return "Tuber – " + ", ".join(parts) + f". I förråd: {inv}. Skenmål: {d['decoys']}."


def _solution(d: dict) -> str:
    rows = []
    for r in d["rows"]:
        if r.get("blocked"):
            rows.append(f"{r['type']}: {r['blocked']}")
        elif r.get("course") is None:
            rows.append(f"{r['type']}: utom räckhåll")
        else:
            rows.append(f"{r['type']}: kurs {fmt_course(r['course'])}, gångtid {_mmss(r['run_s'])}")
    return (f"Skjutlösning {d['designation']} (lösning {Quality(d['quality']).label}): "
            + "; ".join(rows) + ".")


PHRASES = {
    "torp.refused": lambda d: f"Kapten, {d['reason']}.",
    "torp.fired": lambda d: f"Tub {d['tube']} avfyrad! {d['type']}, kurs {fmt_course(d['course'])}"
    + (f", beräknad gångtid {_mmss(d['run_s'])}" if d.get("run_s") else "")
    + (". Lösningen var dålig, risk för miss." if d.get("quality") == Quality.DALIG else "."),
    "torp.time": lambda d: f"Tid för torpeden från tub {d['tube']}"
    + (f" mot {d['designation']}" if d.get("designation") else "") + "!",
    "torp.loading": lambda d: f"Laddar tub {d['tube']} med {d['type']}. Fem minuter.",
    "torp.loaded": lambda d: f"Tub {d['tube']} laddad med {d['type']}.",
    "torp.status": _tubes,
    "torp.solution": _solution,
    "torp.decoy": lambda d: f"Skenmål ute. {d['left']} kvar.",
    "torp.ready": lambda d: f"Kapten, torped. Vi har skjutlösning på {d['designation']}: "
    f"tub {d['tube']} med {d['type']}, gångtid {_mmss(d['run_s'])}. Inväntar order.",
    "torp.suggest.decoy": lambda d: "Kapten, torped. Föreslår skenmål för att dra deras sonar.",
}
phrases.register(PHRASES)


class TorpedoRoom(Station):
    role = Role.TORPEDO
    COMMANDS = [
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+tub\s+(\d)\s+(?:mot\s+)?{DESIG}",
                    lambda m: FireTube(int(m[1]), designation=desig(m[2])), "eld tub 1 mot S-1"),
        CommandSpec(rf"(?:eld|avfyra|fyr|skjut)\s+tub\s+(\d)\s+kurs\s+{NUM}",
                    lambda m: FireTube(int(m[1]), course=num(m[2]) % 360), "eld tub 1 kurs 045"),
        CommandSpec(r"ladda\s+tub\s+(\d)\s+(?:med\s+)?(\S+)", _load, "ladda tub 7 SET-53"),
        CommandSpec(r"tuber|torpeder|torpedrum", lambda m: TubeStatus(), "tuber"),
        CommandSpec(rf"(?:skjutlösning|skjutlosning|eldlösning|eldlosning)(?:\s+{DESIG})?",
                    lambda m: FiringSolution(desig(m[1])), "skjutlösning S-1"),
        CommandSpec(r"skenmål|skenmal|motmedel", lambda m: LaunchDecoy(), "skenmål"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.tubes = [Tube(i + 1) for i in range(N_TUBES)]
        for t in self.tubes[:4]:
            t.load = "53-61"
        for t in self.tubes[4:6]:
            t.load = "SET-53"
        self.inventory = {"53-61": 6, "SET-53": 4, "T-5": 2}
        self.decoys = 6
        self.running: list[tuple[int, str | None, int]] = []
        self._ready_said: dict[str, Quality] = {}

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(SoundHeard, self._on_sound)

    @property
    def own(self):
        return self.game.world.own

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
        if TORPEDO_TYPES[type_key].nuclear and not self.game.world.mission.get("nuclear_authorized"):
            return "kärnladdningen kräver order från Moskva"
        return None

    # --- order -------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        match order:
            case FireTube():
                self._fire(order)
            case LoadTube(tube=n, type=typ):
                self._load(n, typ)
            case TubeStatus():
                self.say("torp.status", {
                    "tubes": [{"n": t.n, "load": t.load, "loading": t.loading} for t in self.tubes],
                    "inventory": dict(self.inventory), "decoys": self.decoys})
            case FiringSolution(designation=d):
                self._preview(d)
            case LaunchDecoy():
                if self.decoys <= 0:
                    self.say("torp.refused", {"reason": "skenmålen är slut"})
                    return
                self.decoys -= 1
                launch_decoy(self.game.world)
                self.say("torp.decoy", {"left": self.decoys}, kind="ack")

    def _tube(self, n: int) -> Tube | None:
        return self.tubes[n - 1] if 1 <= n <= N_TUBES else None

    def _fire(self, o: FireTube) -> None:
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
        elif b := self._blocked(tube.load):
            reason = b
        if reason:
            self.say("torp.refused", {"reason": reason})
            return
        spec = TORPEDO_TYPES[tube.load]
        quality = None
        run_s = None
        detonate_at = None
        if o.designation:
            tr, sol = self._solution_for(o.designation)
            if tr is None:
                self.say("torp.refused", {"reason": f"vi har ingen kontakt {o.designation}"})
                return
            if sol is None:
                self.say("torp.refused", {"reason": f"plottet har ingen lösning på {o.designation}"})
                return
            aim = self._aim(sol, tube.load)
            if aim is None:
                self.say("torp.refused", {"reason": f"{o.designation} är utom räckhåll för {spec.key}"})
                return
            course, run_s, dist = aim
            quality = sol.quality
            if spec.nuclear:
                detonate_at = dist
        else:
            course = o.course
        launch_torpedo(self.game.world, spec, course, detonate_at)
        self.game.world.mission["hostile_act"] = True
        tube.load = None
        if run_s:
            self.running.append((o.tube, o.designation, int(self.now + run_s)))
        self.say("torp.fired", {"tube": o.tube, "type": spec.key, "course": course,
                                "run_s": run_s, "quality": quality},
                 kind="ack", quality=quality, alarm=True)

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
            tube.loading = typ
            tube.ready_t = self.now + RELOAD_S
            self.say("torp.loading", {"tube": n, "type": typ}, kind="ack")

    def _preview(self, designation: str | None) -> None:
        if designation is None:
            held = [t for t in self.game.knowledge.tracks.values() if t.held]
            if len(held) != 1:
                self.say("torp.refused", {"reason": "ange vilken kontakt"})
                return
            designation = held[0].designation
        tr, sol = self._solution_for(designation)
        if tr is None or sol is None:
            self.say("torp.refused", {"reason": f"vi har ingen lösning på {designation}"})
            return
        rows = []
        for key in TORPEDO_TYPES:
            row = {"type": key}
            if b := self._blocked(key):
                row["blocked"] = b
            elif (aim := self._aim(sol, key)) is not None:
                row["course"], row["run_s"] = aim[0], aim[1]
            else:
                row["course"] = None
            rows.append(row)
        self.say("torp.solution", {"designation": tr.designation, "quality": sol.quality,
                                   "rows": rows}, quality=sol.quality)

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        for t in self.tubes:
            if t.loading and self.now >= t.ready_t:
                t.load, t.loading = t.loading, None
                self.say("torp.loaded", {"tube": t.n, "type": t.load})
        still = []
        for tube, d, t_hit in self.running:
            if self.now >= t_hit:
                self.say("torp.time", {"tube": tube, "designation": d}, kind="info")
            else:
                still.append((tube, d, t_hit))
        self.running = still

        if self.now % 30 == 0:
            self._readiness()

    def _readiness(self) -> None:
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            if not tr.held or sol is None or sol.quality < Quality.GOD:
                continue
            if self._ready_said.get(tr.designation, Quality.DALIG) >= sol.quality:
                continue
            for tube in self.tubes:
                if tube.load and not self._blocked(tube.load) and \
                        (aim := self._aim(sol, tube.load)) is not None:
                    self._ready_said[tr.designation] = sol.quality
                    self.suggest(f"ready{tr.designation}", "torp.ready",
                                 {"designation": tr.designation, "tube": tube.n,
                                  "type": tube.load, "run_s": aim[1]},
                                 quality=sol.quality, cooldown=0)
                    break

    def _on_sound(self, e: SoundHeard) -> None:
        if self.decoys > 0 and (e.kind == "splash" or e.detail == "fast"):
            self.suggest("decoy", "torp.suggest.decoy", order="skenmål", cooldown=600)
