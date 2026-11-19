"""Fartygens siluetter i braille, i meter och skalade efter vinkelstorleken (SB1–SB3).

Varje fartygstyp är en profil i meter: skrovet (med språng och förstävens lutning),
överbyggnader, skorstenar och master. Höjderna stämmer med `sim.periscope.HEIGHTS`
(skrov, överbyggnad, masttopp), så att det utkiken säger syns ("bara mastopparna") är
det som ritas. Siluetten projiceras efter vinkeln på bogen (längden × |sin|, bredden ×
|cos|; fören åt höger när vi ser styrbordssidan) och skärs där horisonten och vågtopparna
döljer den.

Skalan är den verkliga: prickar per grad i bilden gånger fartygets vinkelstorlek. Är den
för liten för att se något (nästan alltid i låg förstoring, på långt håll även i hög) ritas
siluetten med minst `MIN_MAST_DOTS` (låg, bryggan) eller `MIN_MAST_DOTS_HIGH` (hög, kikaren)
prickars masthöjd, i samma proportioner; nära är den verklig och växer med förstoringen. Prickarna är ungefär kvadratiska
(2 × 4 per ruta), så samma skala gäller båda ledderna.

Allt här ritar det utkiken bedömt (bildens avstånd, vinkel på bogen, fart): inget läser sanningen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from sim.periscope import HEIGHTS, hidden_height_m

MIN_MAST_DOTS = 8           # minsta masthöjd i prickar i låg förstoring och från bryggan
MIN_MAST_DOTS_HIGH = 20     # i hög förstoring och kikaren: detaljerna syns
WATERLINE_DOT = 2           # vattenlinjen ligger så många prickar ned i horisontens rad
BOW_WAVE_M_PER_KN = 0.15    # bogvågens höjd per knop
SMOKE_DOTS = 7              # rökplymens längd i prickar


@dataclass(frozen=True)
class Part:
    kind: str           # block (överbyggnad), funnel (skorsten), mast
    u0: float           # längs fartyget: 0 aktern, 1 fören
    u1: float
    z0: float           # höjd över vattnet, m
    z1: float
    w: float = 0.6      # bredd som andel av fartygets bredd (syns när det går mot eller från oss)


@dataclass(frozen=True)
class Profile:
    length_m: float
    beam_m: float
    sheer: float = 0.2              # fördäcket så mycket högre (andel av fribordet) än akterdäcket
    parts: tuple[Part, ...] = ()

    def hull_m(self, kind: str) -> float:
        return HEIGHTS[kind][0]


def _mast(u: float, z0: float, z1: float) -> Part:
    return Part("mast", u, u, z0, z1, 0.0)


# fartygstyp -> profil; höjderna efter HEIGHTS (skrov, överbyggnad, mast)
PROFILES: dict[str, Profile] = {
    # jagare (Fletcher/Gearing-liknande): bryggan förut, två skorstenar, gittermast
    "destroyer": Profile(115.0, 12.0, 0.3, (
        Part("block", 0.58, 0.74, 6.0, 14.0, 0.7),        # bryggan
        Part("block", 0.18, 0.32, 6.0, 9.0, 0.5),         # akterkanonen
        Part("block", 0.80, 0.86, 6.0, 8.5, 0.4),         # förkanonen
        Part("funnel", 0.46, 0.53, 6.0, 13.0, 0.4),
        Part("funnel", 0.36, 0.43, 6.0, 12.0, 0.4),
        _mast(0.62, 14.0, 30.0),
    )),
    # handelsfartyg: midskeppsbrygga, skorsten akter om den, två lastbommar
    "merchant": Profile(140.0, 18.0, 0.15, (
        Part("block", 0.42, 0.58, 7.0, 16.0, 0.8),
        Part("funnel", 0.32, 0.38, 7.0, 15.0, 0.4),
        _mast(0.75, 7.0, 28.0),
        _mast(0.20, 7.0, 24.0),
    )),
    # patrullbåt: liten, styrhytt mitt, en mast
    "patrol": Profile(35.0, 6.0, 0.4, (
        Part("block", 0.45, 0.65, 2.5, 5.0, 0.6),
        _mast(0.55, 5.0, 9.0),
    )),
    # trupptransport: hög överbyggnad med däck på däck, en skorsten, master för och akter
    "transport": Profile(160.0, 21.0, 0.15, (
        Part("block", 0.25, 0.80, 9.0, 16.0, 0.9),
        Part("block", 0.38, 0.66, 16.0, 22.0, 0.8),
        Part("funnel", 0.48, 0.56, 22.0, 30.0, 0.4),
        _mast(0.88, 9.0, 34.0),
        _mast(0.12, 9.0, 30.0),
    )),
    # tankfartyg: lågt skrov, bryggan midskepps, maskin och skorsten akter
    "tanker": Profile(170.0, 22.0, 0.1, (
        Part("block", 0.55, 0.63, 5.0, 13.0, 0.8),
        Part("block", 0.03, 0.18, 5.0, 12.0, 0.9),
        Part("funnel", 0.06, 0.12, 12.0, 18.0, 0.4),
        _mast(0.60, 13.0, 26.0),
        _mast(0.85, 5.0, 20.0),
    )),
    # vaktfartyget i sundet: en mindre jagare (fregatt)
    "guardship": Profile(95.0, 11.0, 0.3, (
        Part("block", 0.58, 0.74, 5.0, 12.0, 0.7),
        Part("funnel", 0.42, 0.50, 5.0, 11.0, 0.4),
        Part("block", 0.80, 0.86, 5.0, 7.5, 0.4),
        _mast(0.63, 12.0, 25.0),
    )),
}
PROFILES["moored"] = PROFILES["merchant"]
SMOKY = {"merchant", "moored", "transport", "tanker"}     # ångare: rök ur skorstenen


@dataclass
class Silhouette:
    """Prickarna relativt fartygets mitt i vattenlinjen: (dx, dz), dz uppåt. `part` säger vad
    pricken är (hull, block, funnel, mast, bow, smoke), så att ritningen kan ge stil."""
    dots: dict[tuple[int, int], str]
    scale: float                    # prickar per meter
    width: int                      # bredd i prickar

    def top(self) -> int:
        return max((dz for _, dz in self.dots), default=0)


def dots_per_m(dpd: float, range_nm: float) -> float:
    """Verklig skala: prickar per grad gånger graderna en meter tar på detta avstånd."""
    return dpd * math.degrees(1.0 / max(range_nm * 1852.0, 1.0))


def _hull_top(p: Profile, hull: float, u: float) -> float:
    """Däckets höjd längs fartyget: språnget stiger mot fören."""
    return hull * (1.0 - p.sheer + p.sheer * u * u)


def _hull_bottom(hull: float, u: float) -> float:
    """Vattenlinjen: aktern hänger över och förstäven lutar framåt (ändarna lyfts)."""
    if u < 0.04:
        return hull * 0.5 * (0.04 - u) / 0.04
    if u > 0.93:
        return hull * 0.8 * (u - 0.93) / 0.07
    return 0.0


def silhouette(kind: str, aob: float | None, range_nm: float, dpd: float, eye_m: float,
               wave_m: float = 0.0, speed: float | None = None, t: int = 0,
               day: bool = True, min_mast_dots: int = MIN_MAST_DOTS) -> Silhouette | None:
    """Siluetten för ett fartyg sett så här. None för okända typer.

    aob: vinkel på bogen (+ styrbord: fören åt höger); dpd: prickar per grad i bilden;
    eye_m: ögats höjd (periskop 1,5, brygga 8); wave_m: vågtoppar som skymmer nederkanten
    (och går i bilden med tiden t); speed ger bogvågen."""
    p = PROFILES.get(kind)
    if p is None or kind not in HEIGHTS:
        return None
    hull, _sup, mast = HEIGHTS[kind]
    s = max(dots_per_m(dpd, range_nm), min_mast_dots / mast)
    a = math.radians(aob if aob is not None else 90.0)
    sa, ca = abs(math.sin(a)), abs(math.cos(a))
    sign = 1.0 if (aob is None or aob >= 0) else -1.0
    hidden = hidden_height_m(range_nm, eye_m)
    dots: dict[tuple[int, int], str] = {}

    def x_of(u: float) -> float:
        return (u - 0.5) * p.length_m * sa * sign

    def cut(dx: int) -> float:
        """Nederkanten där vågtopparna står just nu (de rör sig längs horisonten)."""
        if wave_m <= 0:
            return hidden
        crest = 0.5 * (1 + math.sin(0.9 * dx + 0.7 * t)) * (0.5 + 0.5 * math.sin(0.37 * dx - 0.4 * t))
        return hidden + wave_m * (0.4 + 0.6 * crest)

    def fill(x0: float, x1: float, z0: float, z1: float, what: str, thin: bool = False) -> None:
        xa, xb = sorted((x0 * s, x1 * s))
        cols = range(round(xa), round(xb) + 1) if not thin else [round((xa + xb) / 2)]
        for dx in cols:
            lo = max(z0, cut(dx))
            if lo >= z1:
                continue
            for dz in range(math.floor(lo * s + 0.5), math.floor(z1 * s - 0.5) + 1):
                if dz >= 0 and dz / s >= lo - 1e-9:
                    dots.setdefault((dx, dz), what)

    # skrovet: skivor längs fartyget, var och en med sin bredd mot oss
    n = max(8, int(p.length_m * sa * s) * 2)
    half_b = p.beam_m / 2 * ca
    for i in range(n + 1):
        u = i / n
        x = x_of(u)
        fill(x - half_b, x + half_b, _hull_bottom(hull, u), _hull_top(p, hull, u), "hull")
    for part in p.parts:
        if part.kind == "mast":
            x = x_of(part.u0)
            fill(x, x, part.z0, part.z1, "mast", thin=True)
            yard = part.z0 + 0.8 * (part.z1 - part.z0)      # rån tvärs masten
            yw = max(p.beam_m * 0.3, 1.5 / s)
            fill(x - yw * ca / 2 - 0.5 / s, x + yw * ca / 2 + 0.5 / s, yard, yard + 0.6 / s, "mast")
            continue
        xa, xb = x_of(part.u0), x_of(part.u1)
        w = part.w * p.beam_m / 2 * ca
        fill(min(xa, xb) - w, max(xa, xb) + w, part.z0, part.z1, part.kind)
    width = (max(dx for dx, _ in dots) - min(dx for dx, _ in dots) + 1) if dots else 0
    if not dots:
        return Silhouette(dots, s, 0)

    # bogvågen: skum vid fören, högre ju fortare (det utkiken bedömer farten efter)
    if speed and speed >= 4 and sa > 0.25 and day:
        h = BOW_WAVE_M_PER_KN * speed
        bx = x_of(0.97) * s
        rows = max(1, round(h * s + speed / 8))         # syns även i minsta storleken
        for k in range(rows):
            for j in range(max(1, rows - k)):
                dx = round(bx + sign * j)
                if (dx, k) not in dots or dots[(dx, k)] == "hull":
                    if k >= cut(dx) * s - 1:
                        dots[(dx, k)] = "bow"
    # röken ur skorstenen driver akterut och uppåt (dagsljus)
    if kind in SMOKY and day:
        for part in p.parts:
            if part.kind != "funnel":
                continue
            fx = (x_of(part.u0) + x_of(part.u1)) / 2 * s
            fz = part.z1 * s
            for k in range(1, SMOKE_DOTS + 1):
                if (k * 7 + t) % 5 == 0:
                    continue                                 # röken är trasig
                dx = round(fx - sign * sa * k * 1.5)
                dz = round(fz + k * 0.6)
                dots.setdefault((dx, dz), "smoke")
    return Silhouette(dots, s, width)


# --- vattenpelaren (SB3) ---------------------------------------------------------------
COLUMN_M = 25.0             # en sjunkbombs vattenpelare (övningsladdning hälften)
COLUMN_RISE_S = 2           # stiger så länge
COLUMN_S = 10               # och har sjunkit ihop efter så här länge (EVENT_S)
COLUMN_MIN_DOTS = 8


def column_dots(range_nm: float, dpd: float, age: int, practice: bool = False,
                min_dots: int = COLUMN_MIN_DOTS) -> dict[tuple[int, int], str]:
    """Vattenpelaren som prickar (dx, dz uppåt från vattenlinjen): stiger på COLUMN_RISE_S
    sekunder, sprutar ut upptill och sjunker ihop till ett skumfält."""
    s = max(dots_per_m(dpd, range_nm), min_dots / COLUMN_M)
    full = COLUMN_M * (0.5 if practice else 1.0) * s
    if age < COLUMN_RISE_S:
        f = (age + 1) / (COLUMN_RISE_S + 1)
    else:
        f = max(0.15, 1.0 - (age - COLUMN_RISE_S) / (COLUMN_S - COLUMN_RISE_S))
    h = max(1, round(full * f))
    out: dict[tuple[int, int], str] = {}
    for dz in range(h + 1):
        top = dz / h
        half = 0.6 + top * top * full * 0.25          # sprutet vidgar sig upptill
        for dx in range(-round(half), round(half) + 1):
            core = abs(dx) <= 0.6
            if core or (dx * 7 + dz * 3 + age) % 3:
                out[(dx, dz)] = "foam"
    spread = round(1 + (full * 0.3) * min(1.0, age / COLUMN_S))   # skummet breder ut sig
    for dx in range(-spread, spread + 1):
        if (dx + age) % 2 == 0:
            out[(dx, 0)] = "foam"
    return out
