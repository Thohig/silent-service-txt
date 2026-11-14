"""Kunskap: det besättningen vet. Byggs enbart av observationer, aldrig av World."""
from __future__ import annotations

from dataclasses import dataclass, field

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
    # bokföring för muntliga rapporter
    last_reported_bearing: float | None = None
    last_bearing_report_t: int = -10**9
    last_suggest_t: int = -10**9

    @property
    def last_bearing(self) -> float | None:
        return self.observations[-1].bearing if self.observations else None


@dataclass
class Knowledge:
    tracks: dict[str, ContactTrack] = field(default_factory=dict)

    def track(self, designation: str) -> ContactTrack | None:
        return self.tracks.get(_normalize(designation))

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
