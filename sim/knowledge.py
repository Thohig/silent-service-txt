"""Kunskap: det besättningen vet.

Byggs enbart av sensorhändelser på bussen, aldrig av World. Det gör att
gränsen mellan sanning och kunskap hålls av strukturen: kunskapslagret har
ingen referens till världen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .events import (AirRadarHeard, BearingObserved, ChargeHeard, InterceptHeard, BridgeSighted, ClassificationChanged, ContactDetected,
                     ConvoyAssessed, ContactLost, ContactSunk, EventBus, HuntSigns, IceSounded, OpeningNotFound,
                     PeriscopeBlocked, PeriscopeSighted, PhotoTaken, PositionReported, RecordingMade,
                     ListeningExercise, NuclearOrderRead, TasksOrdered, TelegramReceived, TorpedoExercise,
                     TorpedoInWater)
from .icemap import IceMap
from .periscope import PeriscopePicture
from .seabed import Seabed
from .environment import Almanac, TidalStream
from .reports import Quality
from . import tma
from .tma import HUNTER_MANEUVER_Q, BearingObs, Solution, solve
from .zigzag import ConvoyEstimate, LegFix


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
    legs: list[LegFix] = field(default_factory=list)   # avslutade ben (sicksack)
    turns: list[int] = field(default_factory=list)     # när plottet märkt att målet girat
    leg_sol: Solution | None = None                    # benets senaste användbara lösning
    sunk_t: int | None = None                          # när sonar hörde den sjunka

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
    def friendly(self) -> bool:
        """Klassad som eget bevakningsfartyg (övningsmålet ordern nämner): inget hot,
        men plottet räknar på det."""
        return "bevakningsfartyg" in self.classification

    @property
    def threat(self) -> bool:
        """En hållen kontakt som kan vara ett fiendefartyg."""
        return self.held and not self.benign and not self.friendly and self.sunk_t is None

    @property
    def sunk(self) -> bool:
        return self.sunk_t is not None

    @property
    def last_bearing(self) -> float | None:
        return self.observations[-1].bearing if self.observations else None


HUNTED_WINDOW_S = 300          # så länge efter senaste tecknet räknar vi med att de har oss
TORPEDO_ALARM_S = 60           # så länge efter senaste bäringen på en fientlig torped
WAYPOINT_DRIFT_KN = 0.3          # isdrift åt okänt håll: så växer osäkerheten
WAYPOINT_MOTION_KN = 2.0         # ett mål som rör sig: fel i meddelad kurs och fart, sicksack
HUNTER_PING_S = 300            # ett mål som pingat så nyss räknas som jagande


@dataclass
class Waypoint:
    """Ett mål vi känner läget på, t.ex. drivstationen (beräknade koordinater)."""
    name: str
    x: float
    y: float
    sigma0: float
    t: int
    source: str = "radio"
    motion: tuple[float, float] | None = None    # (kurs, fart) om målet rör sig

    def sigma(self, now: int) -> float:
        drift = WAYPOINT_DRIFT_KN if self.motion is None else WAYPOINT_MOTION_KN
        return self.sigma0 + drift * max(0, now - self.t) / 3600.0

    def at(self, now: int) -> tuple[float, float]:
        """Läget nu: det meddelade, framräknat med meddelad kurs och fart."""
        if self.motion is None:
            return self.x, self.y
        c, v = self.motion
        dt_h = max(0, now - self.t) / 3600.0
        return (self.x + v * dt_h * math.sin(math.radians(c)),
                self.y + v * dt_h * math.cos(math.radians(c)))


AIR_CLOSE = ("stark", "mycket stark")    # flygradarns styrka då masterna kan synas


@dataclass
class Knowledge:
    tracks: dict[str, ContactTrack] = field(default_factory=dict)
    ice: IceMap = field(default_factory=IceMap)
    waypoints: dict[str, Waypoint] = field(default_factory=dict)
    bathymetry: Seabed | None = None     # det gamla sjökortets djupkurvor (inte sanningen)
    tide_table: TidalStream | None = None   # tidvattentabellen (förutsägelse, inte sanningen)
    almanac: Almanac | None = None          # sol och måne för platsen och datumet (D4)
    lights: tuple = ()                      # fyrlistan (seabed.Lighthouse), Clyde
    # farleden enligt sjökortet (beräknade koordinater, i gångriktningen) och vart den leder
    fairway: tuple[tuple[float, float], ...] = ()
    fairway_to: str | None = None
    best_photo: Quality | None = None    # bästa spaningsfotot hittills
    recorded: set = field(default_factory=set)   # kontakter sonar har en färdig inspelning av
    hunt_t: int = -10**9                 # senast sonar hörde att fienden har oss
    torpedo_t: int = -10**9              # senaste bäringen på en fientlig torped
    doors_t: int = -10**9                # senast sonar hörde fienden öppna torpedrören
    periscope: PeriscopePicture | None = None   # utkikens senaste bild
    bridge: PeriscopePicture | None = None      # bryggans bild just nu (None: ingen på bryggan)
    listening: bool = False              # lyssningsövning pågår: plottet tar in vårt eget fartyg
    torpedo_exercise: bool = False       # torpedövning pågår: skjutlösning på vårt eget fartyg
    periscope_blocked: tuple[int, str] | None = None   # (tid, skäl) när periskopet inte kom upp
    air_radar: tuple[int, str | None] | None = None   # radarvarnarens senaste svep: (tid, flygradarns styrka)
    intercept: InterceptHeard | None = None   # senaste radiospaningen
    air_close_t: int | None = None       # senast radarvarnaren hörde flygradar nära (stark, mycket stark)
    convoy: ConvoyEstimate | None = None   # plottets bild av en konvoj
    telegrams: list[TelegramReceived] = field(default_factory=list)   # det radion tagit emot
    order_tasks: frozenset[str] = frozenset()   # vad ordern kräver (Scenario.tasks, TasksOrdered)
    order_tasks_t: int = 0                      # när ordern senast byttes (TasksOrdered)
    task_place: str | None = None               # positionen den senaste uppgiften gäller
    photo_t: int | None = None                  # senaste spaningsfotot
    # vad ordern och telegrammen säger om kärnladdningen och kriget: (tid, nuclear, war, källa)
    nuclear_orders: list[tuple[int, str | None, bool | None, str]] = field(default_factory=list)
    charges: list[ChargeHeard] = field(default_factory=list)   # sjunkbomberna som besättningen bedömt dem

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(ContactDetected, self._on_detected)
        bus.subscribe(BearingObserved, lambda e: self.on_bearing(e.obs))
        bus.subscribe(ClassificationChanged, self._on_classified)
        bus.subscribe(ContactLost, lambda e: self.on_lost(e.designation))
        bus.subscribe(ContactSunk, self._on_sunk)
        bus.subscribe(IceSounded, lambda e: self.ice.on_sounding(e.obs))
        bus.subscribe(OpeningNotFound, self._on_opening_not_found)
        bus.subscribe(PositionReported, self._on_position)
        bus.subscribe(TelegramReceived, self.telegrams.append)
        bus.subscribe(TasksOrdered, self._on_tasks)
        bus.subscribe(ChargeHeard, self.charges.append)
        bus.subscribe(NuclearOrderRead,
                      lambda e: self.nuclear_orders.append((e.t, e.nuclear, e.war, e.source)))
        bus.subscribe(HuntSigns, self._on_hunt)
        bus.subscribe(TorpedoInWater, self._on_torpedo)
        bus.subscribe(PhotoTaken, self._on_photo)
        bus.subscribe(RecordingMade, lambda e: self.recorded.add(e.designation))
        bus.subscribe(PeriscopeSighted, self._on_periscope)
        bus.subscribe(BridgeSighted, self._on_bridge)
        bus.subscribe(ConvoyAssessed, lambda e: setattr(self, "convoy", e.estimate))
        bus.subscribe(AirRadarHeard, self._on_air_radar)
        bus.subscribe(InterceptHeard, lambda e: setattr(self, "intercept", e))
        bus.subscribe(PeriscopeBlocked, lambda e: setattr(self, "periscope_blocked", (e.t, e.reason)))
        bus.subscribe(ListeningExercise, lambda e: setattr(self, "listening", e.active))
        bus.subscribe(TorpedoExercise, lambda e: setattr(self, "torpedo_exercise", e.active))

    # --- händelser ------------------------------------------------------------
    def _on_tasks(self, e: TasksOrdered) -> None:
        self.order_tasks, self.order_tasks_t = frozenset(e.tasks), e.t

    def _on_air_radar(self, e: AirRadarHeard) -> None:
        self.air_radar = (e.t, e.strength)
        if e.strength in AIR_CLOSE:
            self.air_close_t = e.t

    def nuclear_order(self) -> tuple[str, int, str]:
        """Den senaste ordern om kärnladdningen: (nuclear, tid, källa). Utan något läst gäller
        order_only (marinens grundregel: bara på order från Moskva)."""
        for t, nuclear, _war, source in reversed(self.nuclear_orders):
            if nuclear is not None:
                return nuclear, t, source
        return "order_only", 0, "ordern"

    def at_war(self) -> tuple[bool, int | None, str | None]:
        """Om ordern eller ett telegram sagt att det är krig: (krig, tid, källa)."""
        for t, _nuclear, war, source in reversed(self.nuclear_orders):
            if war is not None:
                return war, t, source
        return False, None, None

    def air_close_now(self) -> bool:
        """Hörde radarvarnaren flygradar nära i sitt senaste svep (det gäller bara på periskopdjup)?"""
        return self.air_radar is not None and self.air_radar[1] in AIR_CLOSE and \
            self.air_radar[0] == self.air_close_t
    def _on_periscope(self, e: PeriscopeSighted) -> None:
        self.periscope = e.picture

    def _on_bridge(self, e: BridgeSighted) -> None:
        """Utryms bryggan blir dess sista bild periskopbilden (om den är nyare): det
        senaste vi såg ovanför ytan."""
        last = self.bridge
        self.bridge = e.picture
        if e.picture is None and last is not None and \
                (self.periscope is None or last.t > self.periscope.t):
            self.periscope = last

    def _on_photo(self, e: PhotoTaken) -> None:
        self.photo_t = e.t
        if self.best_photo is None or e.quality > self.best_photo:
            self.best_photo = e.quality

    def _on_hunt(self, e: HuntSigns) -> None:
        self.hunt_t = e.t
        if e.reason == "doors":
            self.doors_t = e.t

    def _on_torpedo(self, e: TorpedoInWater) -> None:
        if e.kind != "lost":
            self.torpedo_t = e.t

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
        new = Waypoint(e.name, e.x, e.y, e.sigma, e.t_pos, e.source, e.motion)
        if e.task:
            self.task_place = e.name
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
        elif not tr.held:
            # återfunnen: lösningen är från när vi tappade den (kanske en timme sedan). Plottet
            # räknar om ur bäringarna vid nästa omräkning; till dess finns ingen lösning att visa.
            tr.solution = None
        tr.held = True
        return tr

    def _on_sunk(self, e: ContactSunk) -> None:
        if (tr := self.tracks.get(e.designation)) is not None and tr.sunk_t is None:
            tr.sunk_t = e.t
            tr.held = False

    def on_lost(self, designation: str) -> None:
        if tr := self.tracks.get(designation):
            tr.held = False

    def on_bearing(self, obs: BearingObs) -> ContactTrack | None:
        tr = self.tracks.get(obs.designation)
        if tr is not None:
            tr.observations.append(obs)
        return tr

    # --- frågor ---------------------------------------------------------------
    def torpedo_alarm(self, now: int, window: int = TORPEDO_ALARM_S) -> bool:
        """Hör sonar en fientlig torped (nyss)? Då är undanmanövern det enda som gäller."""
        return now - self.torpedo_t <= window

    def hunted(self, now: int, window: int = HUNTED_WINDOW_S) -> bool:
        """Har fienden troligen kontakt med oss (tecken hörda nyligen)?"""
        return now - self.hunt_t <= window

    def charged_close(self, now: int, window: int = 300) -> bool:
        """Skarpa sjunkbomber nära oss nyligen (sonar eller maskin): jagaren har ett bra läge på oss."""
        return any(c.real and c.near and now - c.t <= window for c in self.charges)

    def threat_held(self) -> bool:
        return any(t.threat for t in self.tracks.values())

    def zigzags(self, tr: ContactTrack) -> bool:
        """Plottet vet att målet sicksackar: konvojfartyg, eller två märkta girar."""
        c = self.convoy
        return (c is not None and tr.designation in c.members) or len(tr.turns) >= 2

    def hunting(self, tr: ContactTrack, t_now: int) -> bool:
        """Jagar målet oss? Ett mål som pingar medan vi är jagade (snabb pingtakt, plask) girar hela
        tiden; en jagare som pingar i lugn patrull går sina ben."""
        return self.hunted(t_now) and any(
            o.source == "ping" and o.t >= t_now - HUNTER_PING_S and o.t >= tr.tma_from_t
            for o in tr.observations)

    def track(self, designation: str) -> ContactTrack | None:
        return self.tracks.get(_normalize(designation))

    def resolve(self, designation: str, t_now: int,
                own_now: tuple[float, float]) -> Solution | None:
        tr = self.tracks.get(_normalize(designation))
        if tr is None:
            return None
        obs = [o for o in tr.observations if o.t >= tr.tma_from_t]
        q = HUNTER_MANEUVER_Q if self.hunting(tr, t_now) else \
            tma.ZIGZAG_MANEUVER_Q if self.zigzags(tr) else None
        tr.solution = solve(obs, t_now=t_now, own_now=own_now, maneuver_q=q)
        return tr.solution


def _normalize(designation: str) -> str:
    d = designation.strip().upper().replace(" ", "")
    if d.startswith("S") and not d.startswith("S-"):
        d = "S-" + d[1:]
    return d
