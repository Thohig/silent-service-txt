"""Konvoj och sicksack ur plottets lösningar (kunskap, ren matematik).

Ett sicksackande mål går raka ben. Plottlaget sparar varje bens sista
användbara lösning (`LegFix`: läge vid en tidpunkt, med avståndsosäkerhet).
Baskursen är riktningen genom benens lägen över tid: en viktad rak linje
x(t), y(t). Ett läge mitt i ett ben ligger åt sidan om baslinjen, så varje
läge får också en sicksackosäkerhet (ZIGZAG_POS_NM). Kvaliteten följer av
baskursens osäkerhet och av hur många ben vi har sett: två ben räcker inte
för att skilja ett ben från medelkursen, så kvaliteten begränsas av antalet.

Gruppering: kontakter med ungefär samma kurs och fart nära varandra är en
grupp. Minst två som inte är klassade som jagare är en konvoj; jagare nära
konvojen räknas som eskort.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .geo import angle_diff, distance, norm360
from .reports import Quality

ZIGZAG_POS_NM = 0.8          # ett benläge kan ligga så här långt från baslinjen (12 kn, 8 min, ±30°)
GROUP_NM = 3.0               # fartyg i samma grupp ligger så här nära varandra
GROUP_COURSE_DEG = 30.0
GROUP_SPEED_KN = 4.0
ESCORT_NM = 5.0              # en jagare så nära konvojen räknas som eskort
MIN_TURN_GAP_S = 180         # girar tätare än så räknas som samma gir
MAX_LEG_SIGMA_NM = 1.0       # ett ben med sämre läge än så används inte
MAX_LEG_KN = 35.0            # orimlig fart: benets lösning var fel
# kvalitetstak efter antal ben
MAX_QUALITY_BY_LEGS = {2: Quality.OSAKER, 3: Quality.GOD}


@dataclass(frozen=True)
class LegFix:
    """Ett bens sista användbara lösning: läge (x, y) vid t."""
    t: int
    x: float
    y: float
    sigma: float            # lägesosäkerhet (nm), avståndets σ
    course: float
    speed: float


@dataclass(frozen=True)
class BaseCourse:
    course: float
    speed: float
    sigma_deg: float
    quality: Quality
    legs: int


@dataclass(frozen=True)
class ConvoyEstimate:
    """Plottets bild av en konvoj (beräknade koordinater)."""
    t: int
    members: tuple[str, ...]
    escorts: tuple[str, ...]
    x: float                 # gruppens mitt vid t
    y: float
    leg_course: float        # det ben de går nu
    leg_speed: float
    base: BaseCourse | None
    mean_leg_s: int | None   # sicksackens ungefärliga benlängd
    last_turn_t: int | None  # senaste gir vi märkt

    def contains(self, designation: str) -> bool:
        return designation in self.members or designation in self.escorts

    def advance(self, now: int) -> tuple[float, float, float, float]:
        """Mitten nu och hastigheten (knop) längs baskursen, annars benet."""
        course, speed = ((self.base.course, self.base.speed) if self.base is not None
                         and self.base.quality >= Quality.OSAKER
                         else (self.leg_course, self.leg_speed))
        vx = speed * math.sin(math.radians(course))
        vy = speed * math.cos(math.radians(course))
        dt = (now - self.t) / 3600.0
        return self.x + vx * dt, self.y + vy * dt, vx, vy


def _fit_velocity(legs: Sequence[LegFix]) -> tuple[float, float, float] | None:
    """Viktad rak linje genom benens lägen: (vx, vy, σ_v) i knop."""
    if len(legs) < 2:
        return None
    w = [1.0 / (lg.sigma ** 2 + ZIGZAG_POS_NM ** 2) for lg in legs]
    sw = sum(w)
    tm = sum(wi * lg.t for wi, lg in zip(w, legs)) / sw
    xm = sum(wi * lg.x for wi, lg in zip(w, legs)) / sw
    ym = sum(wi * lg.y for wi, lg in zip(w, legs)) / sw
    stt = sum(wi * (lg.t - tm) ** 2 for wi, lg in zip(w, legs))
    if stt <= 0:
        return None
    vx = sum(wi * (lg.t - tm) * (lg.x - xm) for wi, lg in zip(w, legs)) / stt * 3600.0
    vy = sum(wi * (lg.t - tm) * (lg.y - ym) for wi, lg in zip(w, legs)) / stt * 3600.0
    sv = math.sqrt(1.0 / stt) * 3600.0
    return vx, vy, sv


def base_course(legs_by_track: Iterable[Sequence[LegFix]]) -> BaseCourse | None:
    """Baskursen ur en eller flera kontakters ben (samma konvoj, var sin formationsplats)."""
    fits, n_legs, all_legs = [], 0, []
    for legs in legs_by_track:
        legs = sorted((lg for lg in legs if lg.sigma <= MAX_LEG_SIGMA_NM
                       and lg.speed <= MAX_LEG_KN), key=lambda lg: lg.t)
        all_legs += legs
        if (f := _fit_velocity(legs)) is not None:
            fits.append(f)
            n_legs = max(n_legs, len(legs))
    if not fits:
        return None
    w = [1.0 / max(sv, 1e-3) ** 2 for _, _, sv in fits]
    vx = sum(wi * f[0] for wi, f in zip(w, fits)) / sum(w)
    vy = sum(wi * f[1] for wi, f in zip(w, fits)) / sum(w)
    sv = math.sqrt(1.0 / sum(w))
    drift = math.hypot(vx, vy)
    if drift < 0.5:
        return None
    sigma = min(180.0, math.degrees(math.atan2(sv, drift)))
    course = norm360(math.degrees(math.atan2(vx, vy)))
    # farten framåt: benens fart längs baskursen (lägena ger riktningen, benen farten)
    along = sorted(max(0.0, lg.speed * math.cos(math.radians(angle_diff(lg.course, course))))
                   for lg in all_legs)
    speed = along[len(along) // 2] if along else drift
    q = (Quality.SAKER if sigma <= 5 else Quality.GOD if sigma <= 10
         else Quality.OSAKER if sigma <= 20 else Quality.DALIG)
    q = min(q, MAX_QUALITY_BY_LEGS.get(n_legs, Quality.SAKER))
    return BaseCourse(course, speed, sigma, q, n_legs)


def mean_leg(turns_by_track: Iterable[Sequence[int]]) -> int | None:
    """Ungefärlig benlängd: medianen av tiden mellan girar, kontakt för kontakt.

    Plottet märker samma gir olika sent på olika fartyg, så girarna jämförs
    bara inom en och samma kontakt."""
    gaps = []
    for turns in turns_by_track:
        ts = sorted(turns)
        gaps += [b - a for a, b in zip(ts, ts[1:]) if b - a >= MIN_TURN_GAP_S]
    if not gaps:
        return None
    gaps.sort()
    return int(gaps[len(gaps) // 2])


def merge_turns(turns: Iterable[int]) -> list[int]:
    """Konvojens girar ur alla medlemmars: girar inom MIN_TURN_GAP_S är samma gir."""
    out: list[int] = []
    for t in sorted(turns):
        if out and t - out[-1] < MIN_TURN_GAP_S:
            continue
        out.append(t)
    return out


@dataclass(frozen=True)
class TrackPoint:
    """En kontakts läge och rörelse nu enligt plottet."""
    designation: str
    x: float
    y: float
    course: float
    speed: float
    escort: bool             # klassad som jagare


def groups(points: Sequence[TrackPoint]) -> list[list[TrackPoint]]:
    """Kontakter som går ihop: nära varandra med ungefär samma kurs och fart."""
    parent = list(range(len(points)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(points):
        for j in range(i + 1, len(points)):
            b = points[j]
            if a.escort or b.escort:
                continue
            if distance(a.x, a.y, b.x, b.y) <= GROUP_NM and \
                    abs(angle_diff(a.course, b.course)) <= GROUP_COURSE_DEG and \
                    abs(a.speed - b.speed) <= GROUP_SPEED_KN:
                parent[find(i)] = find(j)
    out: dict[int, list[TrackPoint]] = {}
    for i, p in enumerate(points):
        if not p.escort:
            out.setdefault(find(i), []).append(p)
    return [g for g in out.values() if len(g) >= 2]


def escorts_near(group: Sequence[TrackPoint], points: Sequence[TrackPoint]) -> list[str]:
    cx = sum(p.x for p in group) / len(group)
    cy = sum(p.y for p in group) / len(group)
    return [p.designation for p in points
            if p.escort and distance(p.x, p.y, cx, cy) <= ESCORT_NM]
