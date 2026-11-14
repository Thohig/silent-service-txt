"""Sanningen: världens exakta tillstånd. Spelaren ser aldrig detta direkt."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import acoustics
from .geo import bearing_to, distance
from .ship import ShipState


@dataclass
class Vessel:
    id: str          # sanningens id, t.ex. "DD1" – visas aldrig för spelaren
    kind: str        # "submarine", "destroyer", ...
    state: ShipState


@dataclass
class World:
    own: Vessel
    contacts: list[Vessel] = field(default_factory=list)
    time: int = 0
    background_noise: float = acoustics.BACKGROUND_NOISE_DB
    size_nm: float = 20.0

    def tick(self, dt: int = 1) -> None:
        self.own.state.step(dt)
        for v in self.contacts:
            v.state.step(dt)
        self.time += dt

    # --- sanningshjälp (används av sensorer och sanningsloggen) -----------
    def true_range(self, v: Vessel) -> float:
        o = self.own.state
        return distance(o.x, o.y, v.state.x, v.state.y)

    def true_bearing(self, v: Vessel) -> float:
        o = self.own.state
        return bearing_to(o.x, o.y, v.state.x, v.state.y)

    def raw_signal_excess(self, v: Vessel) -> float:
        """SE utan detektionströskel – ren fysik."""
        sl = acoustics.source_level(v.kind, v.state.speed)
        tl = acoustics.transmission_loss(self.true_range(v))
        nl = acoustics.total_noise(self.background_noise, self.own.state.speed)
        return acoustics.signal_excess(sl, tl, nl)
