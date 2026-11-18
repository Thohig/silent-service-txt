"""Iskartan: vad besättningen vet om isen ovanför (kunskap, aldrig sanning).

Byggs enbart av IceSounded-händelser från det uppåtriktade isekolodet.
Positionerna är navigatörens beräknade (besticket), inte sanna.

En öppning är en sammanhängande följd av lodningar med öppet vatten
eller tunn is (≤ BREAKABLE_M) som går att bryta igenom. Bedömningens
kvalitet räknas ur hur väl vi vet var öppningen ligger nu jämfört med hur
stor den är: osäkerheten växer med åldern, eftersom isen driver åt ett
okänt håll och besticket glider.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .geo import NM_IN_M, bearing_to, distance
from .reports import Quality

OPEN_M = 0.05               # lodad tjocklek under detta = öppet vatten
BREAKABLE_M = 1.0           # tunn is som ubåten kan bryta igenom
BASE_SIGMA_M = 20.0         # ekolodets fotavtryck och besticksbrus
GROWTH_M_PER_MIN = 8.0      # isdrift (~0,25 kn åt okänt håll) och besticksglidning
MIN_SURFACE_LEN_M = 120.0   # kortare än så: trångt, ubåten är 107 m lång
HULL_HALF_M = 50.0          # för- och akterskeppet från tornet (egen ubåt, inte isen)
FORGET_S = 3600             # äldre öppningar har drivit iväg
RECENT_S = 30               # lodning som räknas som "just nu"
LONG_OPENING_M = 250        # längre öppningar: sikta en bit innanför utgången
TARGET_INSIDE_M = 100


@dataclass(frozen=True)
class IceSoundingObs:
    t: int
    x: float                # beräknad position, nm
    y: float
    thickness: float        # lodad istjocklek, m
    draft: float            # lodat isdjup (undersidan), m

    @property
    def usable(self) -> bool:
        return self.thickness <= BREAKABLE_M

    @property
    def open(self) -> bool:
        return self.thickness < OPEN_M


@dataclass
class Opening:
    no: int
    first: IceSoundingObs
    last: IceSoundingObs
    thickest: float = 0.0
    active: bool = True             # vi ligger under den just nu
    dropped: bool = False           # sökt men inte hittad: drivit iväg
    track: list[IceSoundingObs] = field(default_factory=list)

    @property
    def open(self) -> bool:
        return self.thickest < OPEN_M

    @property
    def center(self) -> tuple[float, float]:
        """Målpunkten: mitt i en kort öppning; i en lång en bit innanför den
        punkt där vi senast hade öppet vatten (där vet vi säkrast att det är öppet)."""
        if self.length_m <= LONG_OPENING_M or not self.track:
            return (self.first.x + self.last.x) / 2, (self.first.y + self.last.y) / 2
        back = TARGET_INSIDE_M / NM_IN_M
        for o in reversed(self.track):
            if distance(o.x, o.y, self.last.x, self.last.y) >= back:
                return o.x, o.y
        return self.first.x, self.first.y

    @property
    def length_m(self) -> float:
        return distance(self.first.x, self.first.y, self.last.x, self.last.y) * NM_IN_M \
            + BASE_SIGMA_M

    def sigma_m(self, now: int) -> float:
        age_min = max(0.0, (now - self.last.t) / 60.0)
        return BASE_SIGMA_M + GROWTH_M_PER_MIN * age_min

    def quality(self, now: int) -> Quality:
        r = self.sigma_m(now) / max(self.length_m / 2, 1.0)
        q = (Quality.SAKER if r < 0.25 else Quality.GOD if r < 0.5
             else Quality.OSAKER if r < 1.0 else Quality.DALIG)
        if self.length_m < MIN_SURFACE_LEN_M:
            q = min(q, Quality.OSAKER)
        return q


@dataclass
class IceMap:
    soundings: list[IceSoundingObs] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)
    _current: Opening | None = None
    _next_no: int = 1

    def on_sounding(self, s: IceSoundingObs) -> Opening | None:
        """Lägg till en lodning. Returnerar öppningen som just stängdes, om någon."""
        self.soundings.append(s)
        cutoff = s.t - FORGET_S
        if self.soundings and self.soundings[0].t < cutoff:
            self.soundings = [o for o in self.soundings if o.t >= cutoff]
            self.openings = [o for o in self.openings if o.last.t >= cutoff or o.active]
        cur = self._current
        if s.usable:
            if cur is None:
                cur = Opening(self._next_no, s, s, s.thickness, track=[s])
                self._next_no += 1
                self.openings.append(cur)
                self._current = cur
            else:
                cur.last = s
                cur.track.append(s)
                cur.thickest = max(cur.thickest, s.thickness)
            return None
        if cur is not None:
            cur.active = False
            self._current = None
            return cur
        return None

    # --- frågor ------------------------------------------------------------------
    def latest(self, now: int) -> IceSoundingObs | None:
        if self.soundings and now - self.soundings[-1].t <= RECENT_S:
            return self.soundings[-1]
        return None

    def under_ice(self, now: int) -> bool:
        """Har vi is ovanför just nu (enligt senaste lodningen)?"""
        s = self.latest(now)
        return s is not None and not s.usable

    def deepest_keel(self, now: int, window_s: int = 600) -> float:
        """Djupaste isköl lodad under de senaste window_s sekunderna."""
        return max((o.draft for o in self.soundings if now - o.t <= window_s), default=0.0)

    @property
    def current(self) -> Opening | None:
        return self._current

    def candidates(self, now: int) -> list[Opening]:
        return [o for o in self.openings if not o.dropped and now - o.last.t <= FORGET_S]

    def best(self, now: int, x: float, y: float) -> Opening | None:
        """Bästa öppningen att gå till: högst kvalitet, sedan närmast."""
        def key(o: Opening):
            cx, cy = o.center
            return (-int(o.quality(now)), distance(x, y, cx, cy))
        cands = [o for o in self.candidates(now) if o.quality(now) >= Quality.OSAKER]
        return min(cands, key=key, default=None)

    @staticmethod
    def course_and_range_m(x: float, y: float, o: Opening) -> tuple[float, float]:
        cx, cy = o.center
        return bearing_to(x, y, cx, cy), distance(x, y, cx, cy) * NM_IN_M


def round_m(v: float) -> int:
    """Avrunda meter som en navigatör säger dem."""
    step = 10 if v < 200 else 50 if v < 2000 else 100
    return int(step * round(v / step))


def thickness_words(t: float) -> str:
    if t < OPEN_M:
        return "öppet vatten"
    return f"nyis, cirka {f'{t:.1f}'.replace('.', ',')} meter"


def describe_opening(o: Opening, now: int, x: float, y: float) -> dict:
    """Data för fraser: bäring, avstånd, längd, slag. Allt ur kunskapen."""
    course, rng = IceMap.course_and_range_m(x, y, o)
    return {"no": o.no, "bearing": course, "range": round_m(rng),
            "length": round_m(o.length_m), "kind": thickness_words(o.thickest),
            "open": o.open, "age_min": math.floor((now - o.last.t) / 60)}
