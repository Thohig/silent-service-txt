"""Havsmiljön: ljudprofil, botten, ström, dygnsljus.

Ljudprofilen avgör hur ljud dämpas mellan två djup. Den är utbytbar:
  Thermocline – tempererat hav med språngskikt (Kubakrisen).
  ArcticProfile – arktiskt hav under is: ljudhastigheten ökar med djupet
      ända från ytan, så ljudet böjs uppåt och studsar mot isens undersida.
      Ljudet hålls i en kanal (cylindrisk spridning efter övergångsavståndet)
      men tappar några dB vid varje isstuds. Djupt gående källor och
      mottagare får färre studsar per sjömil.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Protocol

from .geo import NM_IN_M, angle_diff, velocity
from .sky import julian_day, moon_phase, moon_position, sun_position

if TYPE_CHECKING:
    from .seabed import Seabed
    from .ice import IceField

ABSORPTION_DB_PER_NM = 0.5


def spherical_loss(range_nm: float) -> float:
    """Sfärisk spridning plus absorption."""
    r_m = max(range_nm * NM_IN_M, 1.0)
    return 20.0 * math.log10(r_m) + ABSORPTION_DB_PER_NM * range_nm


class SoundProfile(Protocol):
    @property
    def layer_depth(self) -> float | None: ...

    def transmission_loss(self, range_nm: float, depth_a: float, depth_b: float) -> float: ...


@dataclass(frozen=True)
class Thermocline:
    layer_depth: float = 60.0        # m – språngskiktets djup
    layer_loss: float = 7.0          # dB extra dämpning när skiktet ligger emellan

    def layer_between(self, depth_a: float, depth_b: float) -> bool:
        return (depth_a < self.layer_depth) != (depth_b < self.layer_depth)

    def transmission_loss(self, range_nm: float, depth_a: float, depth_b: float) -> float:
        tl = spherical_loss(range_nm)
        if self.layer_between(depth_a, depth_b):
            tl += self.layer_loss
        return tl


@dataclass(frozen=True)
class ArcticProfile:
    transition_nm: float = 1.0       # sfärisk spridning ut hit, sedan cylindrisk
    scatter_db_per_nm: float = 2.4   # isstudsar för en källa/mottagare nära isen
    scatter_depth_m: float = 150.0   # halverar studsförlusten vid detta medeldjup
    layer_depth: float | None = None # inget språngskikt

    def scatter_loss(self, range_nm: float, depth_a: float, depth_b: float) -> float:
        mean_depth = (max(depth_a, 0.0) + max(depth_b, 0.0)) / 2.0
        per_nm = self.scatter_db_per_nm / (1.0 + mean_depth / self.scatter_depth_m)
        return per_nm * range_nm

    def transmission_loss(self, range_nm: float, depth_a: float, depth_b: float) -> float:
        r0 = self.transition_nm
        if range_nm <= r0:
            tl = spherical_loss(range_nm)
        else:
            tl = spherical_loss(r0) + 10.0 * math.log10(range_nm / r0) \
                + ABSORPTION_DB_PER_NM * (range_nm - r0)
        return tl + self.scatter_loss(range_nm, depth_a, depth_b)


TIDE_PERIOD_S = 44712            # halvdygnstidvatten, 12 h 25 min


@dataclass(frozen=True)
class TidalStream:
    """Tidvattenström: sätter mot flood_set vid flod, motsatt vid ebb.

    Farten skalar med vattendjupet (smalt och grunt ⇒ starkare), noll på land.
    Samma klass är tidvattentabellen i kunskapen (`Knowledge.tide_table`)."""
    flood_set: float                 # dit floden sätter
    peak_kn: float                   # starkaste fart på referensdjupet
    phase_s: float                   # simtid när floden är som starkast
    period_s: float = TIDE_PERIOD_S
    ref_depth: float = 60.0
    max_factor: float = 1.5
    min_factor: float = 0.2

    def factor(self, depth: float) -> float:
        if depth <= 0:
            return 0.0
        return min(self.max_factor, max(self.min_factor, self.ref_depth / depth))

    def speed(self, t: float, depth: float) -> float:
        """Fart i knop längs flood_set (negativ vid ebb)."""
        return self.peak_kn * self.factor(depth) * \
            math.cos(2 * math.pi * (t - self.phase_s) / self.period_s)

    def velocity(self, t: float, depth: float) -> tuple[float, float]:
        return velocity(self.flood_set, self.speed(t, depth))

    def table_copy(self, rng) -> "TidalStream":
        """Tidvattentabellen: förutsägelsen, med fel i styrka och tid."""
        return replace(self, peak_kn=self.peak_kn * (1 + rng.gauss(0, 0.2)),
                       phase_s=self.phase_s + rng.gauss(0, 1200))


# --- ljuset: sol, skymning och måne -------------------------------------------------------
SUNRISE_ELEV = -0.833       # solens överkant vid horisonten
CIVIL_ELEV = -6.0           # borgerlig skymning: horisonten och siluetter syns
NAUTICAL_ELEV = -12.0       # nautisk skymning: ljus himmel bara åt solens håll
TWILIGHT_SIL_DEG = 75.0     # i nautisk skymning syns siluetter så här nära solens bäring
MOON_SIL_DEG = 35.0         # i månglittret syns siluetter så här nära månens bäring
MOON_SIL_LIGHT = 0.2        # månljus som krävs för siluetter i glittret
MOON_FULL_ELEV = 25.0       # månen ger fullt ljus från denna höjd
FALLBACK_TWILIGHT_DEG_H = 15.0   # utan plats: solen sjunker så här många grader per timme


@dataclass(frozen=True)
class Light:
    """Ljuset en viss stund: solens och månens läge och vad det betyder för sikten."""
    sun_elev: float
    sun_az: float
    moon_elev: float = -90.0
    moon_az: float = 0.0
    moon_frac: float = 0.0       # månens belysta andel
    waxing: bool = True
    day_vis: float = 10.0
    night_vis: float = 2.5

    @property
    def phase(self) -> str:
        """dag, skymning (borgerlig), nautisk (skymning) eller natt."""
        e = self.sun_elev
        return ("dag" if e > SUNRISE_ELEV else "skymning" if e > CIVIL_ELEV
                else "nautisk" if e > NAUTICAL_ELEV else "natt")

    @property
    def morning(self) -> bool:
        """Solen på östra himlen: gryning, inte skymning."""
        return self.sun_az < 180.0

    @property
    def moon_light(self) -> float:
        """Månljuset 0–1: fasen gånger hur högt den står."""
        if self.moon_elev <= 0:
            return 0.0
        return self.moon_frac * min(1.0, math.sin(math.radians(self.moon_elev))
                                    / math.sin(math.radians(MOON_FULL_ELEV)))

    @property
    def level(self) -> float:
        """Ljusnivån 0–1: dag 1, borgerlig skymning 1 → 0,5, nautisk 0,5 → 0,1, natt
        0,05 plus månen (högst 0,35)."""
        e = self.sun_elev
        if e > SUNRISE_ELEV:
            sun = 1.0
        elif e > CIVIL_ELEV:
            sun = 1.0 - 0.5 * (SUNRISE_ELEV - e) / (SUNRISE_ELEV - CIVIL_ELEV)
        elif e > NAUTICAL_ELEV:
            sun = 0.5 - 0.4 * (CIVIL_ELEV - e) / (CIVIL_ELEV - NAUTICAL_ELEV)
        else:
            sun = 0.0
        return max(sun, 0.05 + 0.3 * self.moon_light)

    @property
    def visibility_nm(self) -> float:
        e = self.sun_elev
        mid = (self.day_vis + self.night_vis) / 2 if self.day_vis > 5 else self.day_vis
        if e > SUNRISE_ELEV:
            sun = self.day_vis
        elif e > CIVIL_ELEV:
            sun = self.day_vis + (mid - self.day_vis) * (SUNRISE_ELEV - e) / (SUNRISE_ELEV - CIVIL_ELEV)
        elif e > NAUTICAL_ELEV:
            sun = mid + (self.night_vis - mid) * (CIVIL_ELEV - e) / (CIVIL_ELEV - NAUTICAL_ELEV)
        else:
            sun = self.night_vis
        return max(sun, self.night_vis * (1 + self.moon_light))

    @property
    def daylight(self) -> bool:
        """Tillräckligt ljust för det som kräver dagsljus (foto, plask, flyg): nivå ≥ 0,5."""
        return self.level >= 0.5

    def silhouette(self, bearing: float) -> bool:
        """Syns ett fartyg i denna bäring som siluett (inte bara lanternor)?
        Dag och borgerlig skymning: överallt. Nautisk: mot den ljusa himlen åt solen.
        Natt: i månglittret när månen lyser nog."""
        ph = self.phase
        if ph in ("dag", "skymning"):
            return True
        if ph == "nautisk" and abs(angle_diff(bearing, self.sun_az)) <= TWILIGHT_SIL_DEG:
            return True
        return self.moon_light >= MOON_SIL_LIGHT and abs(angle_diff(bearing, self.moon_az)) <= MOON_SIL_DEG


def light_at(lat: float, lon: float, jd: float, day_vis: float = 10.0,
             night_vis: float = 2.5) -> Light:
    """Ljuset på en plats vid en juliansk dag (UTC)."""
    elev, az = sun_position(lat, lon, jd)
    m_elev, m_az = moon_position(lat, lon, jd)
    frac, waxing = moon_phase(jd)
    return Light(elev, az, m_elev, m_az, frac, waxing, day_vis, night_vis)


@dataclass(frozen=True)
class Almanac:
    """Navigatörens almanacka: solens och månens läge för vår ungefärliga plats, datumet och
    klockan. Kunskap (tabeller ombord), inte sanning: samma astronomi, ingen tillgång till
    världen."""
    lat: float
    lon: float
    utc_offset_h: float
    date: tuple[int, int, int]
    clock_start: int

    @classmethod
    def of(cls, env: "Environment") -> "Almanac | None":
        if env.lat is None or env.date is None:
            return None
        return cls(env.lat, env.lon, env.utc_offset_h, env.date, env.clock_start)

    def light(self, sim_t: int) -> Light:
        y, m, d = self.date
        return light_at(self.lat, self.lon,
                        julian_day(y, m, d, self.clock_start + sim_t - self.utc_offset_h * 3600))


@dataclass
class Environment:
    profile: SoundProfile = field(default_factory=Thermocline)
    bottom_depth: float = 2400.0     # m
    background_noise: float = 60.0   # dB, havsbrus
    current_set: float = 45.0        # strömmens riktning (dit den sätter)
    current_kn: float = 0.4
    sunrise: int = 6 * 3600 + 10 * 60
    sunset: int = 17 * 3600 + 50 * 60
    day_visibility_nm: float = 10.0
    night_visibility_nm: float = 2.5
    clock_start: int = 0             # sekunder efter midnatt vid simtid 0
    # var och när: solens och månens läge räknas ur dessa. Utan plats följer ljuset
    # sunrise/sunset (och ingen måne). Klockan är lokal: UTC + utc_offset_h.
    lat: float | None = None
    lon: float = 0.0
    utc_offset_h: float = 0.0
    date: tuple[int, int, int] | None = None     # datumet vid simtid 0 (år, månad, dag)
    ice: IceField | None = None      # packis ovanför, se ice.py
    seabed: Seabed | None = None     # bottentopografi, se seabed.py
    tide: TidalStream | None = None  # tidvattenström (kustnära)

    def bottom_at(self, x: float, y: float) -> float:
        """Bottendjupet (m) på platsen. Sanning: bara ekolodet frågar."""
        return self.seabed.depth_at(x, y) if self.seabed is not None else self.bottom_depth

    @property
    def layer_depth(self) -> float | None:
        """Språngskiktets djup, eller None om profilen saknar skikt."""
        return self.profile.layer_depth

    def layer_between(self, depth_a: float, depth_b: float) -> bool:
        ld = self.layer_depth
        return ld is not None and (depth_a < ld) != (depth_b < ld)

    def transmission_loss(self, range_nm: float, depth_a: float, depth_b: float) -> float:
        return self.profile.transmission_loss(range_nm, depth_a, depth_b)

    def noise_at(self, x: float, y: float) -> float:
        """Bakgrundsbrus (dB) på platsen: isens brus om det finns is, annars havsbrus."""
        if self.ice is not None:
            return self.ice.noise_at(x, y)
        return self.background_noise

    def clock(self, sim_t: int) -> int:
        return (self.clock_start + sim_t) % 86400

    def is_day(self, sim_t: int) -> bool:
        """Solen över horisonten."""
        if self.lat is None or self.date is None:
            c = self.clock(sim_t)
            return self.sunrise <= c < self.sunset
        return self.light(sim_t).sun_elev > SUNRISE_ELEV

    def visibility_nm(self, sim_t: int) -> float:
        return self.light(sim_t).visibility_nm

    def daylight(self, sim_t: int) -> bool:
        """Ljust nog för det som kräver dagsljus (foto, plask, flyg, landmärken)."""
        return self.light(sim_t).daylight

    def jd(self, sim_t: int) -> float:
        """Juliansk dag (UTC) vid simtid sim_t."""
        y, m, d = self.date
        return julian_day(y, m, d, self.clock_start + sim_t - self.utc_offset_h * 3600)

    def light(self, sim_t: int) -> Light:
        """Ljuset vid simtid sim_t (sparas per sekund)."""
        cache = self.__dict__.setdefault("_light_cache", {})
        key = (sim_t, self.clock_start, self.lat, self.date, self.sunrise, self.sunset)
        hit = cache.get(key)
        if hit is not None:
            return hit
        vis = dict(day_vis=self.day_visibility_nm, night_vis=self.night_visibility_nm)
        if self.lat is None or self.date is None:
            elev, az = self._fallback_sun(sim_t)
            out = Light(elev, az, **vis)
        else:
            out = light_at(self.lat, self.lon, self.jd(sim_t), **vis)
        if len(cache) > 4:
            cache.clear()
        cache[key] = out
        return out

    def _fallback_sun(self, sim_t: int) -> tuple[float, float]:
        """Utan plats: solen över horisonten mellan sunrise och sunset (högst 45°), under den
        sjunker den FALLBACK_TWILIGHT_DEG_H per timme till −30°. Azimut öst–syd–väst."""
        c, sr, ss = self.clock(sim_t), self.sunrise, self.sunset
        if ss <= sr:                                       # polarnatt
            return -30.0, 180.0
        if sr <= c < ss:
            f = (c - sr) / (ss - sr)
            return max(0.0, 45.0 * math.sin(math.pi * f)), 90.0 + 180.0 * f
        since = (c - ss) % 86400
        until = (sr - c) % 86400
        h = min(since, until) / 3600
        return max(-30.0, -0.9 - FALLBACK_TWILIGHT_DEG_H * h), (270.0 if since < until else 90.0)

    def current_velocity(self) -> tuple[float, float]:
        """Den jämna havsströmmen i nm per sekund."""
        return velocity(self.current_set, self.current_kn)

    def current_at(self, x: float, y: float, t: float) -> tuple[float, float]:
        """Strömmen på platsen (nm per sekund): havsströmmen plus tidvattnet."""
        vx, vy = self.current_velocity()
        if self.tide is not None:
            tx, ty = self.tide.velocity(t, self.bottom_at(x, y))
            vx, vy = vx + tx, vy + ty
        return vx, vy
