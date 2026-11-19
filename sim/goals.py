"""Uppdragsmål (sanning): scenariot lägger dem i `World.goals`, världen prövar dem varje tick.

Varje mål har `check(world) -> bool`. Sant betyder att kontrollen ska sluta för det här
ticket: målet har avslutat spelet med `world.end(...)`, eller det väntar på något (t.ex.
brytningsljud) och inget annat mål ska få avsluta under tiden. Målen prövas i `RANK`-ordning,
så ett scenario behöver inte bry sig om i vilken ordning det lägger till dem.

Det som sker under spelet (sänkta fartyg, bilder, sända rapporter, grundstötning) skrivs
fortfarande i `World.mission` av de delar som ser det; målen läser därifrån.

Nytt mål: en ny klass här med `RANK` och `check`, ingen ändring i `World`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from .geo import distance

if TYPE_CHECKING:
    from .world import World

NO_DIVE_M = 3.0             # djupare än så räknas som dykt (förbud i fjorden)


@dataclass
class Goal:
    RANK: ClassVar[int] = 50

    def check(self, world: World) -> bool:
        raise NotImplementedError


@dataclass
class NuclearFired(Goal):
    """Kärnladdningen har detonerat: spelet slutar (utfallet `nuclear`) efter `delay_s`, före
    sänkt-målen (de väntar 45 s), så att det är detta och inget annat som blir utfallet. Alla
    scenarier har det (`Game` lägger till det)."""
    delay_s: int = 30
    RANK: ClassVar[int] = 0

    def check(self, world: World) -> bool:
        t = world.mission.get("nuclear_t")
        if t is None:
            return False
        if world.time - t >= self.delay_s:
            world.end("nuclear")
        return True


@dataclass
class StrikeGoal(Goal):
    """Anfall: sänkt minst ett mål och ingen jägare har oss `clear_s` efter senaste
    sänkningen; eller alla mål har passerat och ligger `miss_nm` bort utan att något sänkts."""
    targets: list[str]
    outcome: str
    miss_outcome: str
    clear_s: int = 600
    miss_nm: float = 8.0
    RANK: ClassVar[int] = 10

    def check(self, world: World) -> bool:
        targets = [v for v in world.contacts if v.id in self.targets]
        sunk = [v for v in targets if v.sunk]
        if sunk:
            if world.time - world.mission.get("last_sink_t", 0) >= self.clear_s and \
                    not any(world._hunting_us(ai) for ai in world.ais):
                world.end(self.outcome, sunk=len(sunk))
                return True
            return False
        o = world.own.state
        alive = [v for v in targets if not v.sunk]
        if alive and all(
                distance(o.x, o.y, v.state.x, v.state.y) > self.miss_nm
                and (o.x - v.state.x) * math.sin(math.radians(v.state.course))
                + (o.y - v.state.y) * math.cos(math.radians(v.state.course)) < 0
                for v in alive):
            world.end(self.miss_outcome)
            return True
        return False


@dataclass
class PhotoGoal(Goal):
    """Ett spaningsfoto minst så här bra (`mission["best_photo"]`)."""
    quality: int
    outcome: str
    RANK: ClassVar[int] = 20

    def check(self, world: World) -> bool:
        if world.mission.get("best_photo", -1) >= self.quality:
            world.end(self.outcome)
            return True
        return False


@dataclass
class ReportGoal(Goal):
    """Rapport sänd inom sambandsfönstret och, när det stängt, ingen jägare som har oss.
    `contact_sigma_nm`: bara ett datum så skarpt räknas (en pejling av sändningen gör det inte)."""
    t_from: int
    t_to: int
    outcome: str
    miss_outcome: str
    contact_sigma_nm: float | None = None
    RANK: ClassVar[int] = 30

    def check(self, world: World) -> bool:
        if world.time < self.t_to:
            return False
        sent = world.mission.get("last_report_t")
        if sent is None or not self.t_from <= sent <= self.t_to:
            world.end(self.miss_outcome)
            return True
        if not any(world._hunting_us(ai, max_sigma=self.contact_sigma_nm) for ai in world.ais):
            world.end(self.outcome)
            return True
        return False


@dataclass
class SurfaceNearGoal(Goal):
    """I ytläge inom `radius_nm` från ett föremål (t.ex. drivstationen)."""
    target_id: str
    radius_nm: float
    outcome: str
    RANK: ClassVar[int] = 40

    def check(self, world: World) -> bool:
        if not world.own.surfaced:
            return False
        target = next((v for v in world.contacts if v.id == self.target_id), None)
        if target is not None and world.true_range(target) <= self.radius_nm:
            world.end(self.outcome)
            return True
        return False


@dataclass
class GroundingFails(Goal):
    """Grundstötning (`mission["grounded_t"]`) avslutar uppdraget."""
    outcome: str
    RANK: ClassVar[int] = 50

    def check(self, world: World) -> bool:
        if "grounded_t" in world.mission:
            world.end(self.outcome)
            return True
        return False


@dataclass
class NoDiveInFjord(Goal):
    """Dykning innanför fjordens mynning avslutar uppdraget."""
    outcome: str
    RANK: ClassVar[int] = 60

    def check(self, world: World) -> bool:
        if world.own.state.depth > NO_DIVE_M and world._in_fjord():
            world.end(self.outcome)
            return True
        return False


@dataclass
class TrainingGoal(Goal):
    """Övningen klar: övningsledaren sätter `done_t` när sista steget är avbockat."""
    outcome: str
    done_t: int | None = None
    RANK: ClassVar[int] = 70

    def check(self, world: World) -> bool:
        if self.done_t is not None and world.time >= self.done_t:
            world.end(self.outcome)
            return True
        return False


@dataclass
class EscapeGoal(Goal):
    """Ut ur området (`margin_nm` utanför kvadraten, eller söder om `y_below`), i undervattensläge
    och ingen jägare har oss. `requires_photo`: inte utan ett foto minst så bra."""
    margin_nm: float
    outcome: str
    requires_photo: int | None = None
    y_below: float | None = None
    RANK: ClassVar[int] = 90

    def check(self, world: World) -> bool:
        if self.requires_photo is not None and \
                world.mission.get("best_photo", -1) < self.requires_photo:
            return False
        out = world.own.state.y < self.y_below if self.y_below is not None \
            else world._outside_area(self.margin_nm)
        if not world.own.surfaced and out and not any(world._hunting_us(ai) for ai in world.ais):
            world.end(self.outcome)
            return True
        return False


def report_summary(world: World, windows: list[int], window_len: int) -> dict:
    """Radions del i slutrapporten (sanning): sambandstillfällen med rapport och hur väl det vi
    rapporterade stämde (`mission["report_truth"]`, antecknat av radion när den sände)."""
    reports = world.mission.get("reports", [])
    times = [r.t for r in reports]
    passed = [w0 for w0 in windows if w0 <= world.time]
    with_report = sum(1 for w0 in passed if any(w0 <= t <= w0 + window_len for t in times))
    truth = world.mission.get("report_truth", [])
    own = [t["own_err_nm"] for t in truth]
    contacts = [c for t in truth for c in t["contacts"]]
    return {
        "windows": len(passed),
        "windows_reported": with_report,
        "reports": len(reports),
        "own_err_nm": max(own) if own else None,
        "contact_pos_err_nm": (sorted(c["pos_err_nm"] for c in contacts)[len(contacts) // 2]
                               if contacts else None),
        "contact_course_err": (sorted(c["course_err"] for c in contacts)[len(contacts) // 2]
                               if contacts else None),
        "contacts_reported": len({c["designation"] for c in contacts}),
    }


COUNCIL_TRUTH_S = 30 * 60      # sjunkbomberna så långt tillbaka jämförs med rådets bedömning
COUNCIL_NEAR_M = 600           # och så nära oss


def council_summary(world: World) -> list[dict]:
    """Kärnvapenrådet i slutrapporten (sanning): varje råd med vad zampoliten och starpom sa,
    det de trodde (skarpt angrepp eller inte) och vad sjunkbomberna nära oss verkligen var
    (`mission["councils"]`, antecknat av torpedrummet när rådet hölls)."""
    return list(world.mission.get("councils", []))
