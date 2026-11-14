"""Kunskap: det besättningen vet.

Byggs enbart av sensorhändelser på bussen, aldrig av World. Det gör att
gränsen mellan sanning och kunskap hålls av strukturen: kunskapslagret har
ingen referens till världen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .events import (BearingObserved, ClassificationChanged, ContactDetected,
                     ContactLost, EventBus)
from .reports import Quality
from .tma import BearingObs, Solution, solve


@dataclass
class ContactTrack:
    designation: str
    first_t: int
    classification: str = "okänd kontakt"
    class_quality: Quality = Quality.DALIG
    observations: list[BearingObs] = field(default_factory=list)
    solution: Solution | None = None
    held: bool = True

    @property
    def last_bearing(self) -> float | None:
        return self.observations[-1].bearing if self.observations else None


@dataclass
class Knowledge:
    tracks: dict[str, ContactTrack] = field(default_factory=dict)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(ContactDetected, self._on_detected)
        bus.subscribe(BearingObserved, lambda e: self.on_bearing(e.obs))
        bus.subscribe(ClassificationChanged, self._on_classified)
        bus.subscribe(ContactLost, lambda e: self.on_lost(e.designation))

    # --- händelser ------------------------------------------------------------
    def _on_detected(self, e: ContactDetected) -> None:
        tr = self.on_detection(e.designation, e.t)
        tr.classification, tr.class_quality = e.classification, e.quality

    def _on_classified(self, e: ClassificationChanged) -> None:
        if tr := self.tracks.get(e.designation):
            tr.classification, tr.class_quality = e.classification, e.quality

    def on_detection(self, designation: str, t: int) -> ContactTrack:
        tr = self.tracks.get(designation)
        if tr is None:
            tr = ContactTrack(designation, first_t=t)
            self.tracks[designation] = tr
        tr.held = True
        return tr

    def on_lost(self, designation: str) -> None:
        if tr := self.tracks.get(designation):
            tr.held = False

    def on_bearing(self, obs: BearingObs) -> ContactTrack | None:
        tr = self.tracks.get(obs.designation)
        if tr is not None:
            tr.observations.append(obs)
        return tr

    # --- frågor ---------------------------------------------------------------
    def track(self, designation: str) -> ContactTrack | None:
        return self.tracks.get(_normalize(designation))

    def resolve(self, designation: str, t_now: int,
                own_now: tuple[float, float]) -> Solution | None:
        tr = self.tracks.get(_normalize(designation))
        if tr is None:
            return None
        tr.solution = solve(tr.observations, t_now=t_now, own_now=own_now)
        return tr.solution


def _normalize(designation: str) -> str:
    d = designation.strip().upper().replace(" ", "")
    if d.startswith("S") and not d.startswith("S-"):
        d = "S-" + d[1:]
    return d
