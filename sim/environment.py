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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from .geo import NM_IN_M, velocity

if TYPE_CHECKING:
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
    ice: IceField | None = None      # packis ovanför, se ice.py

    @property
    def layer_depth(self) -> float | None:
        """Språngskiktets djup, eller None om profilen saknar skikt."""
        return self.profile.layer_depth

    def layer_between(self, depth_a: float, depth_b: float) -> bool:
        ld = self.layer_depth
        return ld is not None and (depth_a < ld) != (depth_b < ld)

    def transmission_loss(self, range_nm: float, depth_a: float, depth_b: float) -> float:
        return self.profile.transmission_loss(range_nm, depth_a, depth_b)

    def clock(self, sim_t: int) -> int:
        return (self.clock_start + sim_t) % 86400

    def is_day(self, sim_t: int) -> bool:
        c = self.clock(sim_t)
        return self.sunrise <= c < self.sunset

    def visibility_nm(self, sim_t: int) -> float:
        return self.day_visibility_nm if self.is_day(sim_t) else self.night_visibility_nm

    def current_velocity(self) -> tuple[float, float]:
        """Strömmen i nm per sekund."""
        return velocity(self.current_set, self.current_kn)
