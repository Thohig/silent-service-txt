"""Havsmiljön: språngskikt, botten, ström, dygnsljus."""
from __future__ import annotations

from dataclasses import dataclass

from .geo import velocity


@dataclass
class Environment:
    layer_depth: float = 60.0        # m – språngskiktets djup
    layer_loss: float = 7.0          # dB extra dämpning när skiktet ligger emellan
    bottom_depth: float = 2400.0     # m
    background_noise: float = 60.0   # dB, havsbrus
    current_set: float = 45.0        # strömmens riktning (dit den sätter)
    current_kn: float = 0.4
    sunrise: int = 6 * 3600 + 10 * 60
    sunset: int = 17 * 3600 + 50 * 60
    clock_start: int = 0             # sekunder efter midnatt vid simtid 0

    def layer_between(self, depth_a: float, depth_b: float) -> bool:
        return (depth_a < self.layer_depth) != (depth_b < self.layer_depth)

    def clock(self, sim_t: int) -> int:
        return (self.clock_start + sim_t) % 86400

    def is_day(self, sim_t: int) -> bool:
        c = self.clock(sim_t)
        return self.sunrise <= c < self.sunset

    def visibility_nm(self, sim_t: int) -> float:
        return 10.0 if self.is_day(sim_t) else 2.5

    def current_velocity(self) -> tuple[float, float]:
        """Strömmen i nm per sekund."""
        return velocity(self.current_set, self.current_kn)
