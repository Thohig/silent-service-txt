"""Kunskap: det besättningen vet.

Byggs enbart av sensorhändelser på bussen, aldrig av World. Det gör att
gränsen mellan sanning och kunskap hålls av strukturen: kunskapslagret har
ingen referens till världen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .events import (BearingObserved, ClassificationChanged, ContactDetected,
                     ContactLost, EventBus, HuntSigns, IceSounded, OpeningNotFound,
                     PositionReported)
from .icemap import IceMap
from .seabed import Seabed
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
    tma_from_t: int = -10**9       # plottlaget använder bara bäringar efter denna tid

    @property
    def civil(self) -> bool:
        """Klassad (minst god) som handelsfartyg."""
        return self.class_quality >= Quality.GOD and "handelsfartyg" in self.classification

    @property
    def warship(self) -> bool:
        """Klassad (minst god) som örlogsfartyg: jagare eller ubåt."""
        c = self.classification
        return self.class_quality >= Quality.GOD and ("jagare" in c or "ubåt" in c)

    @property
    def benign(self) -> bool:
        """Säkert klassad som isljud, drivstationen eller handelsfartyg: inget hot."""
        c = self.classification
        return self.class_quality >= Quality.GOD and \
            ("isljud" in c or "isskruvning" in c or "drivstation" in c or self.civil)

    @property
    def threat(self) -> bool:
        """En hållen kontakt som kan vara ett fartyg."""
        return self.held and not self.benign

    @property
    def last_bearing(self) -> float | None:
        return self.observations[-1].bearing if self.observations else None


HUNTED_WINDOW_S = 300          # så länge efter senaste tecknet räknar vi med att de har oss
WAYPOINT_DRIFT_KN = 0.3          # isdrift åt okänt håll: så växer osäkerheten


@dataclass
class Waypoint:
    """Ett mål vi känner läget på, t.ex. drivstationen (beräknade koordinater)."""
    name: str
    x: float
    y: float
    sigma0: float
    t: int
    source: str = "radio"

    def sigma(self, now: int) -> float:
        return self.sigma0 + WAYPOINT_DRIFT_KN * max(0, now - self.t) / 3600.0


@dataclass
class Knowledge:
    tracks: dict[str, ContactTrack] = field(default_factory=dict)
    ice: IceMap = field(default_factory=IceMap)
    waypoints: dict[str, Waypoint] = field(default_factory=dict)
    bathymetry: Seabed | None = None     # det gamla sjökortets djupkurvor (inte sanningen)
    hunt_t: int = -10**9                 # senast sonar hörde att fienden har oss

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(ContactDetected, self._on_detected)
        bus.subscribe(BearingObserved, lambda e: self.on_bearing(e.obs))
        bus.subscribe(ClassificationChanged, self._on_classified)
        bus.subscribe(ContactLost, lambda e: self.on_lost(e.designation))
        bus.subscribe(IceSounded, lambda e: self.ice.on_sounding(e.obs))
        bus.subscribe(OpeningNotFound, self._on_opening_not_found)
        bus.subscribe(PositionReported, self._on_position)
        bus.subscribe(HuntSigns, self._on_hunt)

    # --- händelser ------------------------------------------------------------
    def _on_hunt(self, e: HuntSigns) -> None:
        self.hunt_t = e.t

    def _on_detected(self, e: ContactDetected) -> None:
        known = e.designation in self.tracks
        tr = self.on_detection(e.designation, e.t)
        if not known or e.quality > tr.class_quality:
            tr.classification, tr.class_quality = e.classification, e.quality

    def _on_classified(self, e: ClassificationChanged) -> None:
        if tr := self.tracks.get(e.designation):
            tr.classification, tr.class_quality = e.classification, e.quality

    def _on_position(self, e: PositionReported) -> None:
        old = self.waypoints.get(e.name)
        new = Waypoint(e.name, e.x, e.y, e.sigma, e.t_pos, e.source)
        if old is None or new.sigma(e.t) <= old.sigma(e.t):
            self.waypoints[e.name] = new

    def station_track(self) -> ContactTrack | None:
        """Den kontakt sonaren klassat som drivstationen, om någon."""
        cands = [t for t in self.tracks.values() if "drivstation" in t.classification]
        return max(cands, key=lambda t: t.observations[-1].t if t.observations else -1,
                   default=None)

    def _on_opening_not_found(self, e: OpeningNotFound) -> None:
        for o in self.ice.openings:
            if o.no == e.no:
                o.dropped = True

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
    def hunted(self, now: int, window: int = HUNTED_WINDOW_S) -> bool:
        """Har fienden troligen kontakt med oss (tecken hörda nyligen)?"""
        return now - self.hunt_t <= window

    def threat_held(self) -> bool:
        return any(t.threat for t in self.tracks.values())

    def track(self, designation: str) -> ContactTrack | None:
        return self.tracks.get(_normalize(designation))

    def resolve(self, designation: str, t_now: int,
                own_now: tuple[float, float]) -> Solution | None:
        tr = self.tracks.get(_normalize(designation))
        if tr is None:
            return None
        obs = [o for o in tr.observations if o.t >= tr.tma_from_t]
        tr.solution = solve(obs, t_now=t_now, own_now=own_now)
        return tr.solution


def _normalize(designation: str) -> str:
    d = designation.strip().upper().replace(" ", "")
    if d.startswith("S") and not d.startswith("S-"):
        d = "S-" + d[1:]
    return d
