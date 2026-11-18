"""Havsbotten: djup över operationsområdet (sanning) och det gamla sjökortets bild av den.

Botten är en analytisk funktion av (x, y) i sjömil: ett grunddjup med svag
lutning, några former och småskalig ojämnhet. Formerna:
  Bank      grund platå längs en sida, sluttar ned mot djupet (tanh-profil),
  Seamount  undervattensberg, gaussisk kägla upp mot en topp,
  Ridge     rygg längs en linje, toppdjupet varierar längs den,
  Canyon    ränna längs en linje, djupare än omgivningen.

Samma klass beskriver sjökortets bild (`chart_copy`): formerna flyttade och
utjämnade, utan ojämnhet, ibland utan ett berg. Sjökortet hör till
kunskapen (`Knowledge.bathymetry`) och har ingen referens till sanningen.

Bara ekolodet (navigation/bottom.py) och bottenkontakten (`bottom_contact`, anropas
av World efter förflyttningen) läser sanningens botten:
  - i låg fart (≤ TOUCH_MAX_KN) sätter sig kölen lätt i botten; trimmen tar
    oss upp igen, inga skador,
  - i högre fart går vi på grund: ubåten stannar, skrov och sonar/roder tar
    skada efter farten, över LEAK_KN blir det läckor.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

from typing import TYPE_CHECKING

import numpy as np

from .geo import NM_IN_M

if TYPE_CHECKING:
    from .world import World

CONTOUR_LEVELS = (200, 500, 1000, 2000, 3000)
CONTOUR_STEP_NM = 0.2
HULL_HALF_NM = 50.0 / NM_IN_M   # för- och akterskeppet från tornet
TOUCH_MAX_KN = 2.0              # så sakta: kölen sätter sig, inga skador
LEAK_KN = 5.0                   # fortare: läckor
CLEAR_M = 2.0                   # så här långt över botten räknas kontakten som släppt
BACKOFF_M = 15.0                # trimmen tar oss upp så här mycket efter kontakt
ROCK_SLOPE_M_PER_NM = 450.0     # brantare än så: klippa
SAND_DEPTH_M = 400.0            # grundare än så (och inte klippa): sand, annars lera
CLUTTER_M = 20.0                # så nära botten drunknar ekot i bottenekot
BOTTOM_CLUTTER_DB = 10.0        # i rörelse nära botten
RESTING_CLUTTER_DB = 25.0       # stilla på botten: inget dopplerskift, ekot är en del av botten
ROCK_HULL_DAMAGE = 0.03         # att sätta sig på klippbotten
SURFACE_DRAFT_M = 7.0           # djupgående i ytläge: kölen så här djupt


def _line_coords(x, y, px: float, py: float, bearing: float):
    """(längs, tvärs) linjen genom (px, py) med riktningen bearing, i nm."""
    b = math.radians(bearing)
    ux, uy = math.sin(b), math.cos(b)
    dx, dy = x - px, y - py
    return dx * ux + dy * uy, dx * uy - dy * ux


@dataclass(frozen=True)
class Bank:
    """Grund platå. bearing pekar från banken mot djupet; edge är kantens läge längs den."""
    bearing: float
    edge: float                 # nm från origo längs bearing
    width: float                # sluttningens bredd, nm
    depth: float                # bankens djup, m

    def apply(self, x, y, d):
        b = math.radians(self.bearing)
        s = x * math.sin(b) + y * math.cos(b) - self.edge
        f = 0.5 * (1 + np.tanh(2 * s / self.width))
        return np.where(d > self.depth, self.depth + (d - self.depth) * f, d)

    def moved(self, rng: random.Random, err_nm: float) -> Bank:
        return replace(self, edge=self.edge + rng.gauss(0, err_nm),
                       depth=self.depth + rng.gauss(0, 15))


@dataclass(frozen=True)
class Seamount:
    x: float
    y: float
    peak: float                 # toppens djup, m
    radius: float               # nm (gaussisk)

    def apply(self, x, y, d):
        r2 = ((x - self.x) ** 2 + (y - self.y) ** 2) / self.radius ** 2
        return np.where(d > self.peak, d - (d - self.peak) * np.exp(-r2), d)

    def moved(self, rng: random.Random, err_nm: float) -> Seamount:
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.5, 1.0) * err_nm * 1.6
        return replace(self, x=self.x + r * math.sin(a), y=self.y + r * math.cos(a),
                       peak=max(50.0, self.peak + rng.gauss(0, 40)),
                       radius=self.radius * rng.uniform(1.0, 1.3))


@dataclass(frozen=True)
class Ridge:
    x: float                    # en punkt på ryggen
    y: float
    bearing: float              # ryggens riktning
    crest: float                # medeldjup på krönet, m
    half_width: float           # nm (gaussisk)
    wave_amp: float = 0.0       # krönets variation längs ryggen, m
    wave_nm: float = 6.0
    wave_phase: float = 0.0

    def apply(self, x, y, d):
        along, across = _line_coords(x, y, self.x, self.y, self.bearing)
        crest = self.crest + self.wave_amp * np.sin(2 * math.pi * along / self.wave_nm
                                                    + self.wave_phase)
        w = np.exp(-(across / self.half_width) ** 2)
        return np.where(d > crest, d - (d - crest) * w, d)

    def moved(self, rng: random.Random, err_nm: float) -> Ridge:
        b = math.radians(self.bearing + 90)
        off = rng.gauss(0, err_nm)
        return replace(self, x=self.x + off * math.sin(b), y=self.y + off * math.cos(b),
                       crest=self.crest + rng.gauss(0, 60), wave_amp=self.wave_amp * 0.5)


@dataclass(frozen=True)
class Canyon:
    x: float
    y: float
    bearing: float
    deepen: float               # m djupare i mitten
    half_width: float           # nm

    def apply(self, x, y, d):
        _, across = _line_coords(x, y, self.x, self.y, self.bearing)
        return d + self.deepen * np.exp(-(across / self.half_width) ** 2) * np.clip(d / 600, 0, 1)

    def moved(self, rng: random.Random, err_nm: float) -> Canyon:
        b = math.radians(self.bearing + 90)
        off = rng.gauss(0, err_nm)
        return replace(self, x=self.x + off * math.sin(b), y=self.y + off * math.cos(b),
                       half_width=self.half_width * 1.5, deepen=self.deepen * 0.7)


@dataclass(frozen=True)
class Coast:
    """Kust: land norr om en vågig strandlinje, en farled genom landet och en bukt innanför.

    Djupet utanför stranden växer snabbt (kustbank som stupar mot djuphavet). Land får
    negativt djup; Seabed måste då ha min_depth under noll."""
    shore_y: float              # strandlinjens medelläge (nm norrut)
    wave_amp: float
    wave_nm: float
    wave_phase: float
    channel_x: float            # farledens mitt (nm österut), går rakt norrut
    channel_w: float            # bredd, nm
    channel_depth: float        # m
    bay_x: float
    bay_y: float
    bay_rx: float
    bay_ry: float
    bay_depth: float            # mitt i bukten, m
    shelf_m_per_nm: float = 60.0
    land_m: float = -10.0

    def shore(self, x):
        return self.shore_y + self.wave_amp * np.sin(2 * np.pi * x / self.wave_nm + self.wave_phase)

    def apply(self, x, y, d):
        s = self.shore(x) - y                       # nm till havs från stranden
        shelf = 8.0 + self.shelf_m_per_nm * s + 300.0 * s * s
        out = np.where(s > 0, np.minimum(d, shelf), self.land_m)
        chan = (np.abs(x - self.channel_x) < self.channel_w / 2) & \
            (y > self.shore(x) - 0.6) & (y < self.bay_y)
        out = np.where(chan, np.maximum(out, self.channel_depth), out)
        e = ((x - self.bay_x) / self.bay_rx) ** 2 + ((y - self.bay_y) / self.bay_ry) ** 2
        out = np.where(e < 1, np.maximum(out, self.bay_depth * (1 - 0.45 * e)), out)
        return out

    def moved(self, rng: random.Random, err_nm: float) -> Coast:
        """Kusten är bättre kartlagd än djuphavet: små fel i läge och djup."""
        f = 0.3 * err_nm
        return replace(self, shore_y=self.shore_y + rng.gauss(0, f),
                       channel_x=self.channel_x + rng.gauss(0, f),
                       channel_depth=self.channel_depth * rng.uniform(0.9, 1.1),
                       bay_depth=self.bay_depth * rng.uniform(0.9, 1.1))


def _polyline_coords(x, y, path: tuple[tuple[float, float], ...]):
    """(index, andel, avstånd) till närmaste segment av en linje; första och sista segmentet
    förlängs ut i det oändliga (fjorden fortsätter utanför kortet och ut i mynningen)."""
    best_d = best_i = best_t = None
    n = len(path) - 1
    for i in range(n):
        (ax, ay), (bx, by) = path[i], path[i + 1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = ((x - ax) * dx + (y - ay) * dy) / L2
        lo = -np.inf if i == 0 else 0.0
        hi = np.inf if i == n - 1 else 1.0
        t = np.clip(t, lo, hi)
        d = np.hypot(x - (ax + t * dx), y - (ay + t * dy))
        if best_d is None:
            best_d, best_i, best_t = d, np.zeros_like(d, dtype=int), t
        else:
            closer = d < best_d
            best_d = np.where(closer, d, best_d)
            best_i = np.where(closer, i, best_i)
            best_t = np.where(closer, t, best_t)
    return best_i, best_t, best_d


@dataclass(frozen=True)
class Fjord:
    """Fjordkust: hav norr om en vågig strandlinje, land söder om den utom längs en fjord.

    Fjorden följer `path` (söder → norr, sista punkten ute i mynningen) med halva bredden
    och mittdjupet i varje punkt; väggarna stupar brant. Holmar (x, y, radie) är land med
    brant strand. Land får negativt djup; Seabed måste då ha min_depth under noll."""
    shore_y: float              # strandlinjens medelläge mot havet (nm norrut)
    wave_amp: float
    wave_nm: float
    wave_phase: float
    path: tuple[tuple[float, float], ...]
    half_w: tuple[float, ...]   # nm, per punkt
    depth: tuple[float, ...]    # m mitt i fjorden, per punkt
    islands: tuple[tuple[float, float, float], ...] = ()
    shelf_m_per_nm: float = 120.0
    land_m: float = -10.0

    def shore(self, x):
        return self.shore_y + self.wave_amp * np.sin(2 * np.pi * x / self.wave_nm + self.wave_phase)

    def _along(self, x, y):
        """Halva bredden, mittdjupet och avståndet från mittlinjen på platsen."""
        i, t, d = _polyline_coords(x, y, self.path)
        hw, dp = np.asarray(self.half_w), np.asarray(self.depth)
        j = np.minimum(i + 1, len(self.path) - 1)
        tc = np.clip(t, 0.0, 1.0)
        return hw[i] + (hw[j] - hw[i]) * tc, dp[i] + (dp[j] - dp[i]) * tc, d

    def in_fjord(self, x, y, margin: float = 0.0):
        """Innanför mynningen (söder om strandlinjen + margin nm) och i fjorden."""
        hw, _, d = self._along(x, y)
        return (y < self.shore(x) + margin) & (d < hw + max(margin, 0.0))

    def apply(self, x, y, d):
        s = y - self.shore(x)                       # nm till havs från stranden
        shelf = 8.0 + self.shelf_m_per_nm * s + 300.0 * s * s
        out = np.where(s > 0, np.minimum(d, shelf), self.land_m)
        hw, dp, a = self._along(x, y)
        u = np.clip(a / hw, 0.0, 1.0)
        fj = np.where(a < hw, np.minimum(dp * (1 - u ** 4), d), self.land_m)
        out = np.maximum(out, fj)
        for ix, iy, r in self.islands:
            di = np.hypot(x - ix, y - iy) - r
            out = np.where(di < 0, self.land_m, np.minimum(out, 8.0 + 1000.0 * di))
        return out

    def moved(self, rng: random.Random, err_nm: float) -> Fjord:
        """Hemmavattnen är väl kartlagda: små fel i läge och djup."""
        f = 0.3 * err_nm
        path = tuple((px + rng.gauss(0, f), py + rng.gauss(0, f)) for px, py in self.path)
        isl = tuple((ix + rng.gauss(0, f), iy + rng.gauss(0, f), r) for ix, iy, r in self.islands)
        return replace(self, shore_y=self.shore_y + rng.gauss(0, f), path=path, islands=isl,
                       depth=tuple(dp * rng.uniform(0.9, 1.1) for dp in self.depth))


Feature = Bank | Seamount | Ridge | Canyon | Coast | Fjord


@dataclass(frozen=True)
class Seabed:
    base: float                                     # djup i origo, m
    gradient: tuple[float, float] = (0.0, 0.0)      # m per nm österut, norrut
    features: tuple[Feature, ...] = ()
    # ojämnhet: (kx, ky, fas, andel av djupet) – summan av några vågor
    rough: tuple[tuple[float, float, float, float], ...] = field(default_factory=tuple)
    accuracy_nm: float = 0.0                        # sjökort: angiven lägesnoggrannhet
    min_depth: float = 20.0                         # under noll: land (kust)
    contour_levels: tuple[int, ...] = CONTOUR_LEVELS

    def depths(self, x, y):
        """Djupet (m) för skalärer eller numpy-matriser i nm."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        d = self.base + self.gradient[0] * x + self.gradient[1] * y + 0 * x * y
        for f in self.features:
            if not isinstance(f, Canyon):
                d = f.apply(x, y, d)
        for f in self.features:
            if isinstance(f, Canyon):
                d = f.apply(x, y, d)
        if self.rough:
            n = sum(a * np.sin(kx * x + ky * y + ph) for kx, ky, ph, a in self.rough)
            d = d * (1 + n)
        return np.maximum(d, self.min_depth)

    def depth_at(self, x: float, y: float) -> float:
        return float(self.depths(x, y))

    def slope(self, x: float, y: float, h: float = 0.05) -> float:
        """Lutning i m per nm."""
        dx = (self.depth_at(x + h, y) - self.depth_at(x - h, y)) / (2 * h)
        dy = (self.depth_at(x, y + h) - self.depth_at(x, y - h)) / (2 * h)
        return math.hypot(dx, dy)

    def bottom_type(self, x: float, y: float) -> str:
        """lera, sand eller klippa: berg, ryggkrön och branta sluttningar är klippa."""
        for f in self.features:
            if isinstance(f, Seamount) and math.dist((x, y), (f.x, f.y)) < f.radius * 1.2:
                return "klippa"
            if isinstance(f, Ridge) and abs(_line_coords(x, y, f.x, f.y, f.bearing)[1]) \
                    < f.half_width * 0.8:
                return "klippa"
        if self.slope(x, y) > ROCK_SLOPE_M_PER_NM:
            return "klippa"
        return "sand" if self.depth_at(x, y) < SAND_DEPTH_M else "lera"

    def chart_copy(self, rng: random.Random, err_nm: float, miss_p: float = 0.25) -> Seabed:
        """Det gamla sjökortets bild: formerna flyttade, utjämnade, ibland ett berg som saknas."""
        feats = []
        for f in self.features:
            if isinstance(f, Seamount) and rng.random() < miss_p:
                continue
            feats.append(f.moved(rng, err_nm))
        return Seabed(self.base + rng.gauss(0, 40), self.gradient, tuple(feats),
                      accuracy_nm=err_nm, min_depth=self.min_depth,
                      contour_levels=self.contour_levels)

    @property
    def has_land(self) -> bool:
        return self.min_depth < 0


def _rough(rng: random.Random, n: int, amp: float) -> tuple:
    out = []
    for _ in range(n):
        k = rng.uniform(0.6, 3.0)                   # våglängd ~2–10 nm
        a = rng.uniform(0, 2 * math.pi)
        out.append((k * math.sin(a), k * math.cos(a), rng.uniform(0, 2 * math.pi),
                    amp * rng.uniform(0.4, 1.0) / math.sqrt(n)))
    return tuple(out)


def kuba_seabed(rng: random.Random, start: tuple[float, float], size: float = 20.0) -> Seabed:
    """Kvadrat 7: djuphav med en bank längs västra eller östra sidan, ett berg och en ränna."""
    deep = rng.uniform(2000, 2500)
    west = rng.random() < 0.5
    bank_depth = rng.uniform(120, 200)
    edge_in = rng.uniform(4.5, 5.5)                 # kantens avstånd från sidan, nm
    bank = Bank(bearing=90.0 if west else 270.0,
                edge=edge_in if west else -(size - edge_in),
                width=rng.uniform(2.0, 3.0), depth=bank_depth)
    bank_x = 0.0 if west else size
    for _ in range(100):
        mx, my = rng.uniform(3, size - 3), rng.uniform(4, size - 2)
        if math.dist((mx, my), start) > 4 and abs(mx - bank_x) > 9:
            break
    mount = Seamount(mx, my, peak=rng.uniform(250, 400), radius=rng.uniform(1.0, 1.6))
    canyon = Canyon(x=edge_in if west else size - edge_in, y=rng.uniform(6, size - 4),
                    bearing=(90.0 if west else 270.0) + rng.uniform(-35, 35),
                    deepen=rng.uniform(250, 450), half_width=rng.uniform(0.25, 0.4))
    return Seabed(base=deep - 150, gradient=(0.0, 15.0), features=(bank, mount, canyon),
                  rough=_rough(rng, 6, 0.06))


COAST_CONTOUR_LEVELS = (0, 20, 50, 200, 1000)


def strait_seabed(rng: random.Random, size: float = 14.0) -> Seabed:
    """Inloppet: djuphav i söder, kustbank, land i norr med farled in till en grund bukt."""
    cx = size / 2 + rng.uniform(-1.0, 1.0)
    coast = Coast(shore_y=size * 0.64 + rng.uniform(-0.3, 0.3), wave_amp=rng.uniform(0.2, 0.4),
                  wave_nm=rng.uniform(4.0, 7.0), wave_phase=rng.uniform(0, 2 * math.pi),
                  channel_x=cx, channel_w=rng.uniform(0.6, 0.8),
                  channel_depth=rng.uniform(35, 45),
                  bay_x=cx + rng.uniform(-0.5, 0.5), bay_y=size * 0.87, bay_rx=rng.uniform(2.2, 2.8),
                  bay_ry=rng.uniform(1.1, 1.4), bay_depth=rng.uniform(24, 30))
    return Seabed(base=rng.uniform(1600, 2000), gradient=(0.0, 0.0), features=(coast,),
                  rough=_rough(rng, 4, 0.04), min_depth=-30.0,
                  contour_levels=COAST_CONTOUR_LEVELS)


FJORD_CONTOUR_LEVELS = (0, 20, 50, 100, 200)
ISLAND_CLEAR_NM = 0.5           # holmarnas insida minst så långt från fjordens mitt


def kola_seabed(rng: random.Random, size: float = 16.0) -> Seabed:
    """Kolafjorden från Poljarnyj ut till Barents hav (stiliserad): fjorden går från
    södra kanten norrut med en böj åt öster, ett par holmar, mynningen ungefär 7 nm norrut
    och sedan kustbanken som stupar mot 350–420 m (provdjup 300 m går)."""
    x0 = size * 0.4 + rng.uniform(-0.5, 0.5)
    mouth_y = 8.0 + rng.uniform(-0.4, 0.4)
    bend = rng.uniform(0.8, 1.6)                    # så långt åt öster vid mynningen
    path = ((x0, -2.0), (x0 + rng.uniform(-0.2, 0.2), 2.5),
            (x0 + bend * 0.5, 5.0 + rng.uniform(-0.3, 0.3)),
            (x0 + bend, mouth_y), (x0 + bend + rng.uniform(-0.3, 0.3), mouth_y + 1.5))
    half_w = (0.55, rng.uniform(0.6, 0.75), rng.uniform(0.65, 0.85), rng.uniform(0.8, 1.0), 1.4)
    depth = (rng.uniform(110, 150), rng.uniform(130, 180), rng.uniform(160, 220),
             rng.uniform(180, 240), 240.0)
    islands = []
    for k in (1, 2):                                # en holme vid var sida av mittenbenen
        (ax, ay), (bx, by) = path[k], path[k + 1]
        f = rng.uniform(0.3, 0.7)
        cx, cy = ax + (bx - ax) * f, ay + (by - ay) * f
        L = math.hypot(bx - ax, by - ay)
        nx, ny = (by - ay) / L, -(bx - ax) / L      # åt höger längs leden
        side = rng.choice((-1.0, 1.0))
        w = half_w[k] + (half_w[k + 1] - half_w[k]) * f
        r = rng.uniform(0.12, 0.2)
        # nära stranden: farleden (0,15–0,2 nm åt sidorna) går fritt innanför holmen
        off = side * max(w * 0.95, ISLAND_CLEAR_NM + r)
        islands.append((cx + nx * off, cy + ny * off, r))
    fjord = Fjord(shore_y=mouth_y - 0.3, wave_amp=rng.uniform(0.2, 0.4),
                  wave_nm=rng.uniform(4.0, 7.0), wave_phase=rng.uniform(0, 2 * math.pi),
                  path=path, half_w=half_w, depth=depth, islands=tuple(islands))
    return Seabed(base=rng.uniform(330, 370), gradient=(0.0, 4.0), features=(fjord,),
                  rough=_rough(rng, 4, 0.04), min_depth=-30.0,
                  contour_levels=FJORD_CONTOUR_LEVELS)


def arctic_seabed(rng: random.Random, size: float = 20.0) -> Seabed:
    """Nord-3: djuphavsslätt med en rygg som korsar området."""
    ridge = Ridge(x=rng.uniform(6, size - 6), y=rng.uniform(6, size - 6),
                  bearing=rng.uniform(20, 160), crest=rng.uniform(900, 1200),
                  half_width=rng.uniform(1.2, 2.0), wave_amp=rng.uniform(100, 200),
                  wave_nm=rng.uniform(5, 9), wave_phase=rng.uniform(0, 2 * math.pi))
    return Seabed(base=rng.uniform(3300, 3800), gradient=(rng.uniform(-10, 10), 0.0),
                  features=(ridge,), rough=_rough(rng, 6, 0.03))


SHORE_STEP_DEG = 3          # stranden: en riktning var 3:e grad
SHORE_STEP_NM = 0.1


def shore_ranges(seabed: Seabed | None, x: float, y: float,
                 reach: float) -> list[tuple[float, float]]:
    """Avståndet till närmaste land i varje riktning ut till reach (sanning; bryggan och
    periskopet ser det med ögat). Landet är högre än horisonten, så ögonhöjden spelar ingen roll."""
    if seabed is None or not seabed.has_land:
        return []
    bearings = np.arange(0, 360, SHORE_STEP_DEG, dtype=float)
    dists = np.arange(SHORE_STEP_NM, reach + SHORE_STEP_NM / 2, SHORE_STEP_NM)
    if dists.size == 0:
        return []
    rad = np.radians(bearings)[:, None]
    xs = x + dists[None, :] * np.sin(rad)
    ys = y + dists[None, :] * np.cos(rad)
    land = seabed.depths(xs, ys) <= 0
    out = []
    for i, b in enumerate(bearings):
        hits = np.nonzero(land[i])[0]
        if hits.size:
            out.append((float(b), float(dists[hits[0]])))
    return out


# --- djupkurvor ---------------------------------------------------------------------
Segment = tuple[tuple[float, float], tuple[float, float]]


def contours(seabed: Seabed, x0: float, y0: float, x1: float, y1: float,
             levels=CONTOUR_LEVELS, step: float = CONTOUR_STEP_NM) -> dict[int, list[Segment]]:
    """Djupkurvor (marching squares) som linjestycken per nivå."""
    xs = np.arange(x0, x1 + step / 2, step)
    ys = np.arange(y0, y1 + step / 2, step)
    gx, gy = np.meshgrid(xs, ys)
    z = seabed.depths(gx, gy)
    out: dict[int, list[Segment]] = {}
    for lv in levels:
        segs: list[Segment] = []
        above = z > lv
        for j in range(len(ys) - 1):
            for i in range(len(xs) - 1):
                corners = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
                flags = [above[cj, ci] for ci, cj in corners]
                if all(flags) or not any(flags):
                    continue
                pts = []
                for k in range(4):
                    (ai, aj), (bi, bj) = corners[k], corners[(k + 1) % 4]
                    if flags[k] != flags[(k + 1) % 4]:
                        za, zb = z[aj, ai], z[bj, bi]
                        f = (lv - za) / (zb - za)
                        pts.append((float(xs[ai] + (xs[bi] - xs[ai]) * f),
                                    float(ys[aj] + (ys[bj] - ys[aj]) * f)))
                for k in range(0, len(pts) - 1, 2):
                    segs.append((pts[k], pts[k + 1]))
        if segs:
            out[lv] = segs
    return out


# --- bottenkontakt (sanning) --------------------------------------------------------
def keel_points(x: float, y: float, course: float) -> list[tuple[str, float, float]]:
    dx = math.sin(math.radians(course)) * HULL_HALF_NM
    dy = math.cos(math.radians(course)) * HULL_HALF_NM
    return [("midskepps", x, y), ("förskeppet", x + dx, y + dy), ("akterskeppet", x - dx, y - dy)]


def keel_clearance(seabed: Seabed, x: float, y: float, course: float, depth: float) -> float:
    """Minsta frigång (m) mellan kölen och botten. < 0 = kontakt."""
    return min(seabed.depth_at(px, py) - depth for _, px, py in keel_points(x, y, course))


SHALLOW_REVERB_M = 100.0        # grundare: efterklang från botten och ytan stör aktiv sonar
SHALLOW_REVERB_DB = 15.0        # vid noll meter; linjärt mot SHALLOW_REVERB_M


def shallow_reverb(world: World, x: float, y: float) -> float:
    """Avdrag (dB) för aktiv sonar mot ett mål på grunt vatten: efterklangen dränker ekot."""
    seabed = world.env.seabed
    if seabed is None:
        return 0.0
    d = seabed.depth_at(x, y)
    if d >= SHALLOW_REVERB_M:
        return 0.0
    return SHALLOW_REVERB_DB * (SHALLOW_REVERB_M - max(d, 0.0)) / SHALLOW_REVERB_M


def bottom_clutter(world: World, vessel) -> float:
    """Ekot från en ubåt som ligger på eller strax över botten drunknar i bottenekot (dB)."""
    seabed = world.env.seabed
    if seabed is None or vessel is not world.own:
        return 0.0
    st = vessel.state
    if vessel.sys.on_bottom:
        return RESTING_CLUTTER_DB
    if seabed.depth_at(st.x, st.y) - st.depth < CLUTTER_M:
        return BOTTOM_CLUTTER_DB
    return 0.0


def bottom_contact(world: World, prev: tuple[float, float, float]) -> None:
    seabed = world.env.seabed
    own = world.own
    if seabed is None or own.sunk:
        return
    st, sys = own.state, own.sys
    if sys.on_bottom:
        return
    gap = keel_clearance(seabed, st.x, st.y, st.course, max(st.depth, SURFACE_DRAFT_M))
    if gap >= 0:
        if gap > CLEAR_M:
            sys.bottom_contact = False
        return
    px, py, pdepth = prev
    where = min(keel_points(st.x, st.y, st.course),
                key=lambda p: seabed.depth_at(p[1], p[2]))[0]
    speed = st.speed
    # tillbaka till förra läget, men aldrig under botten
    st.x, st.y = px, py
    floor = min(seabed.depth_at(p[1], p[2]) for p in keel_points(px, py, st.course))
    st.depth = max(0.0, min(pdepth, floor - 0.5))
    st.ordered_depth = min(st.ordered_depth, max(0.0, round(floor - BACKOFF_M)))
    if sys.settle and speed <= TOUCH_MAX_KN:
        # avsiktligt: vi lägger oss på botten och ligger kvar
        st.depth = st.ordered_depth = floor
        st.speed = st.ordered_speed = 0.0
        sys.on_bottom = sys.bottom_contact = True
        kind = seabed.bottom_type(st.x, st.y)
        if kind == "klippa":
            sys.hull -= ROCK_HULL_DAMAGE
        own.alert("bottom.settled", depth=round(floor), kind=kind)
        return
    if sys.bottom_contact:
        return
    sys.bottom_contact = True
    if speed <= TOUCH_MAX_KN:
        own.alert("bottom.touch", where=where, back_to=round(st.ordered_depth))
        return
    st.speed = st.ordered_speed = 0.0
    world.mission.setdefault("grounded_t", world.time)
    sys.hull -= 0.015 * speed
    hit = ["sonar"] if where == "förskeppet" else ["planes"] if where == "akterskeppet" \
        else [world.rng.choice(["sonar", "planes"])]
    if speed > 8:
        hit.append(world.rng.choice(["propulsion", "tubes"]))
    for c in hit:
        sys.health[c] = max(0.0, sys.health[c] - 0.05 * speed)
    leak = speed > LEAK_KN
    if leak:
        sys.leak_rate += 0.08 * speed
    own.alert("bottom.collision", severity="svåra" if speed > 8 else "lätta", where=where,
              components=hit, leak=leak, back_to=round(st.ordered_depth))


# --- fix mot botten (kunskap: kortet mot egna lodningar) ------------------------------
MATCH_STEP_NM = 0.05
MATCH_MIN_RANGE_NM = 0.5
MATCH_MAX_RANGE_NM = 3.0
MATCH_FIT_MAX = 4.0             # chi² per lodning på bästa läget: sämre = kortet stämmer inte


@dataclass(frozen=True)
class BottomMatch:
    dx: float                   # bästa förskjutning av besticket, nm
    dy: float
    sigma: float                # matchningens osäkerhet (utan kortets fel), nm, rms av axlarna
    prior_sigma: float          # bestickets osäkerhet före fixen
    sigma_minor: float = 0.0    # bäst bestämda riktningen
    sigma_major: float = 0.0    # sämst bestämda riktningen
    minor_bearing: float = 0.0  # kurs (0–180) längs vilken läget är bäst bestämt
    fit: float = 0.0            # chi² per lodning på bästa läget (utan besticket)

    @property
    def consistent(self) -> bool:
        """Passar lodningarna kortet någonstans i närheten?"""
        return self.fit <= MATCH_FIT_MAX

    @property
    def line_of_position(self) -> bool:
        """Bara en led bestämd: läget tvärs djupkurvorna men inte längs dem."""
        return self.sigma_minor < 0.5 * self.sigma_major


def sounding_error(depth):
    """Förväntad skillnad (m) mellan en lodning och kortets djup: lod, ojämnhet, kortfel."""
    return 0.08 * np.asarray(depth) + 20.0


def match_soundings(chart: Seabed, points: list[tuple[float, float]], depths: list[float],
                    prior_sigma: float) -> BottomMatch:
    """Var på kortet passar lodningarna bäst? points är besticket vid varje lodning.

    Fördelning över förskjutningar (dx, dy) av hela serien: likelihood ur
    skillnaden mot kortets djup gånger bestickets osäkerhet som förhandsantagande.
    Platt botten ger en bred fördelning (sigma nära prior_sigma).
    """
    r = min(MATCH_MAX_RANGE_NM, max(MATCH_MIN_RANGE_NM, 3 * prior_sigma))
    off = np.arange(-r, r + MATCH_STEP_NM / 2, MATCH_STEP_NM)
    ox, oy = np.meshgrid(off, off)
    px = np.array([p[0] for p in points])[:, None, None]
    py = np.array([p[1] for p in points])[:, None, None]
    d = np.array(depths)[:, None, None]
    z = chart.depths(px + ox, py + oy)
    chi2 = (((z - d) / sounding_error(d)) ** 2).sum(axis=0)
    fit = float(chi2.min()) / len(depths)
    cost = chi2 + (ox ** 2 + oy ** 2) / max(prior_sigma, 0.05) ** 2
    w = np.exp(-(cost - cost.min()) / 2)
    w /= w.sum()
    mx, my = float((w * ox).sum()), float((w * oy).sum())
    cxx = float((w * (ox - mx) ** 2).sum())
    cyy = float((w * (oy - my) ** 2).sum())
    cxy = float((w * (ox - mx) * (oy - my)).sum())
    vals, vecs = np.linalg.eigh(np.array([[cxx, cxy], [cxy, cyy]]))
    minor = max(MATCH_STEP_NM, math.sqrt(max(vals[0], 0.0)))
    major = max(MATCH_STEP_NM, math.sqrt(max(vals[1], 0.0)))
    vx, vy = vecs[:, 0]
    bearing = math.degrees(math.atan2(vx, vy)) % 180
    rms = math.sqrt((minor ** 2 + major ** 2) / 2)
    return BottomMatch(mx, my, rms, prior_sigma, minor, major, bearing, fit)
