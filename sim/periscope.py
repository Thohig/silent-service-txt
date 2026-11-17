"""Periskopbilden: det utkiken såg vid senaste svepet (kunskap, inte sanning).

Vakthavande bygger en `PeriscopePicture` när svepet är klart och publicerar den
som `PeriscopeSighted`. `Knowledge.periscope` håller den senaste bilden, som
periskopvyn ritar. Inget här läser världen: hjälpfunktionerna räknar bara på
det utkiken mätte (avstånd, bedömd kurs) och på kända fartygstyper.

Synlig del: ögat sitter lågt i periskopet, så på långt håll döljs skrovet bakom
horisonten. Geografisk sikt i nm ≈ 2,08·√(höjd i m) för både öga och mål.
Vinkel på bogen (`aob`): bäringen från målet till oss mätt från målets bog,
positiv om vi ser dess styrbordssida. Dess osäkerhet följer av hur mycket av
fartyget som syns; på natten syns bara lanternorna.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .geo import angle_diff, norm360
from .reports import Quality

EYE_PERISCOPE_M = 1.5          # periskopets öga över vattnet på periskopdjup
EYE_BRIDGE_M = 8.0             # tornets brygga i ytläge
HORIZON_K = 2.08               # nm per √m (geografisk sikt med normal refraktion)

# fartygstyp -> (skrov, överbyggnad, mast) i meter över vattnet
HEIGHTS: dict[str, tuple[float, float, float]] = {
    "destroyer": (6.0, 14.0, 30.0),
    "merchant": (7.0, 16.0, 28.0),
    "moored": (7.0, 16.0, 28.0),
    "patrol": (2.5, 5.0, 9.0),
    "guardship": (5.0, 12.0, 25.0),
    "transport": (9.0, 22.0, 34.0),
    "tanker": (5.0, 13.0, 26.0),
}
DEFAULT_HEIGHTS = (6.0, 14.0, 25.0)

# synlig del -> vinkel på bogen, 1σ i grader
AOB_SIGMA = {"helt": 8.0, "överbyggnad": 15.0, "mastoppar": 30.0, "ljus": 25.0}
TWILIGHT_AOB_F = 1.6           # en siluett i skymning eller månljus: kursen svårare att bedöma
SECTOR_HALF_DEG = 16.0         # en kort titt (periskop 047) ser så här långt åt sidorna
CARRY_S = 600                  # föremål utanför en kort titt finns kvar i bilden så här länge
SIDELIGHT_ARC = 112.5          # lanternorna syns från rakt förut till 22,5° akter om tvärs


def horizon_nm(height_m: float) -> float:
    return HORIZON_K * math.sqrt(max(0.0, height_m))


def hidden_height_m(range_nm: float, eye_m: float) -> float:
    """Så mycket av ett mål på detta avstånd som ligger under horisonten."""
    beyond = range_nm - horizon_nm(eye_m)
    return 0.0 if beyond <= 0 else (beyond / HORIZON_K) ** 2


def visible_part(kind: str, range_nm: float, eye_m: float) -> str:
    """helt, överbyggnad eller mastoppar, ur avstånd och ögonhöjd."""
    hull, sup, _mast = HEIGHTS.get(kind, DEFAULT_HEIGHTS)
    hidden = hidden_height_m(range_nm, eye_m)
    if hidden < 0.5 * hull:
        return "helt"
    if hidden < sup:
        return "överbyggnad"
    return "mastoppar"


def aob_quality(sigma_deg: float) -> Quality:
    if sigma_deg <= 10:
        return Quality.GOD
    if sigma_deg <= 20:
        return Quality.OSAKER
    return Quality.DALIG


def angle_on_bow(bearing_to_target: float, target_course: float) -> float:
    """Vinkel på bogen: + styrbord, − babord (vi ser målets styrbords-/babordssida)."""
    return angle_diff(norm360(bearing_to_target + 180.0), target_course)


def lights(aob: float) -> tuple[str, ...]:
    """Lanternorna vi ser vid denna vinkel på bogen."""
    if abs(aob) <= SIDELIGHT_ARC:
        return ("topp", "grön" if aob > 0 else "röd")
    return ("akter",)


def range_quality(range_nm: float, sigma_nm: float) -> Quality:
    rel = sigma_nm / max(range_nm, 0.01)
    if rel <= 0.1:
        return Quality.SAKER
    if rel <= 0.25:
        return Quality.GOD
    if rel <= 0.5:
        return Quality.OSAKER
    return Quality.DALIG


@dataclass
class Judgement:
    """Utkikens bedömningsfel för ett föremål (i σ), fasta en stund så att bilden
    inte fladdrar. Varje fält skalas med sensorns egen σ."""
    t: int
    bearing: float
    range_rel: float
    range_abs: float
    course: float
    speed: float


class Judges:
    """Bedömningarna per föremål. En ny dras när den gamla är hold_s gammal, eller
    inte är yngre än `since` (när periskopet hissades: varje titt är en ny bedömning)."""

    def __init__(self, hold_s: int):
        self.hold_s = hold_s
        self._j: dict[str, Judgement] = {}

    def get(self, key: str, now: int, rng, since: int = -10**9) -> tuple[Judgement, bool]:
        """Bedömningen för key; sant om den är ny (dragen nu)."""
        j = self._j.get(key)
        if j is not None and now - j.t < self.hold_s and j.t > since:
            return j, False
        g = rng.gauss
        j = Judgement(now, g(0, 1), g(0, 1), g(0, 1), g(0, 1), g(0, 1))
        self._j[key] = j
        return j, True


@dataclass(frozen=True)
class SightedObject:
    """Ett föremål i periskopet, som utkiken bedömde det."""
    kind: str                       # siluett: destroyer, merchant, patrol, moored, aircraft, station, net
    label: str                      # ord i rapporten: "jagare", "handelsfartyg" …
    bearing: float                  # sann bäring (beräknad)
    range_nm: float
    range_quality: Quality
    designation: str | None = None  # plottets beteckning (S-1 …), om fartyg
    visible: str = "helt"           # helt, överbyggnad, mastoppar, ljus
    aob: float | None = None        # vinkel på bogen, + styrbord
    aob_quality: Quality = Quality.DALIG
    course: float | None = None
    speed: float | None = None
    lights: tuple[str, ...] = ()
    detail: str = ""                # t.ex. "lågt" för flyg, "grinden öppen" för nätet
    seen_t: int = -1                # när utkiken såg det (äldre än bilden: från ett tidigare svep)


@dataclass(frozen=True)
class IceBearing:
    """Isen i en riktning: avstånd till kanten (None = öppet så långt vi ser), vall."""
    bearing: float
    edge_nm: float | None
    ridged: bool = False


@dataclass(frozen=True)
class LandBearing:
    """Land i en riktning: avstånd till stranden, bedömt med ögat (bryggan)."""
    bearing: float
    range_nm: float


# händelser utkiken ser (SightedObject.kind) utöver fartyg, flyg och ljus
EVENT_KINDS = ("splash", "column", "hit", "wake")


@dataclass(frozen=True)
class PeriscopePicture:
    t: int
    day: bool
    visibility_nm: float
    own_course: float               # vår kurs när bilden togs (för remsans "rätt förut")
    eye: str                        # "periskop" eller "brygga"
    objects: tuple[SightedObject, ...] = ()
    sector: float | None = None     # kort titt mot denna bäring (± SECTOR_HALF_DEG), annars runt
    ice: tuple[IceBearing, ...] = ()
    land: tuple[LandBearing, ...] = ()

    def ships(self) -> list[SightedObject]:
        return [o for o in self.objects if o.designation is not None]


def in_sector(bearing: float, sector: float | None) -> bool:
    return sector is None or abs(angle_diff(bearing, sector)) <= SECTOR_HALF_DEG


def carried(prev: PeriscopePicture | None, now: int, looked,
            fresh: list[SightedObject]) -> list[SightedObject]:
    """Föremål från förra bilden där okularet inte har varit (looked(bäring) falskt)
    och som inte syns nu: de ritas som äldre (seen_t)."""
    if prev is None:
        return []
    seen = {o.designation for o in fresh if o.designation}
    return [o for o in prev.objects
            if not looked(o.bearing) and 0 <= o.seen_t and now - o.seen_t <= CARRY_S
            and (o.designation is None or o.designation not in seen)]
