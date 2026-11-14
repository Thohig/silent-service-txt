"""Sanningen: världens exakta tillstånd. Spelaren ser aldrig detta direkt.

Ett tick:
  1. transienter/emissioner från förra steget blir hörbara nu
  2. alla fartyg rör sig (plus ström)
  3. egen ubåts system (reaktor, batteri, läckor, skrov)
  4. vapen (torpeder, sjunkbomber, skenmål)
  5. fiendens beteende
  6. kontroll av spelslut
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from . import acoustics
from .entities import Emission, Transient, Vessel
from .environment import Environment
from .geo import bearing_to, distance
from .ownship import OwnShip
from .weapons import Torpedo, step_weapons

SINK_ENDING_DELAY = 45      # sekunder brytningsljud innan spelet slutar


@dataclass
class World:
    own: OwnShip
    contacts: list[Vessel] = field(default_factory=list)
    env: Environment = field(default_factory=Environment)
    time: int = 0
    size_nm: float = 20.0
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    ais: list[Any] = field(default_factory=list)
    charges: list[Any] = field(default_factory=list)
    transients: list[Transient] = field(default_factory=list)
    emissions: list[Emission] = field(default_factory=list)
    mission: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] | None = None
    patrol_end: int | None = None
    _pending_t: list[Transient] = field(default_factory=list)
    _pending_e: list[Emission] = field(default_factory=list)

    # --- utsändningar -----------------------------------------------------
    def emit(self, tr: Transient) -> None:
        self._pending_t.append(tr)

    def emit_em(self, em: Emission) -> None:
        self._pending_e.append(em)

    def end(self, outcome: str, **data: Any) -> None:
        if self.outcome is None:
            self.outcome = {"outcome": outcome, "t": self.time, **data}

    @property
    def enemy_ships(self) -> list[Vessel]:
        return [v for v in self.contacts if v.side == "enemy" and v.is_ship]

    # --- tick ---------------------------------------------------------------
    def tick(self, dt: int = 1) -> None:
        if self.outcome is not None:
            return
        self.transients, self._pending_t = self._pending_t, []
        self.emissions, self._pending_e = self._pending_e, []

        cvx, cvy = self.env.current_velocity()
        for v in [self.own, *self.contacts]:
            if v.sunk or isinstance(v, Torpedo):
                continue
            v.state.step(dt)
            v.state.x += cvx * dt
            v.state.y += cvy * dt
            if v.state.depth <= 0 and v is self.own:
                v.state.depth = 0.0

        self.own.update(self, dt)
        step_weapons(self, dt)
        for ai in self.ais:
            ai.step(self)
        self.time += dt
        self._check_outcome()

    def _check_outcome(self) -> None:
        if self.outcome is not None:
            return
        enemies = self.enemy_ships
        if enemies and all(v.sunk for v in enemies):
            self.mission.setdefault("all_sunk_t", self.time)
            if self.time - self.mission["all_sunk_t"] >= SINK_ENDING_DELAY:
                self.end("sank")
            return
        if self.own.surfaced:
            for ai in self.ais:
                if ai.vessel.sunk:
                    continue
                if ai.aware() or self.true_range(ai.vessel) < 6.0:
                    self.end("forced")
                    return
        if self.patrol_end is not None and self.time >= self.patrol_end:
            self.end("patrol_end")

    # --- sanningshjälp (sensorer, vapen, sanningslogg) ----------------------
    def true_range(self, v: Vessel) -> float:
        o = self.own.state
        return distance(o.x, o.y, v.state.x, v.state.y)

    def true_bearing(self, v: Vessel) -> float:
        o = self.own.state
        return bearing_to(o.x, o.y, v.state.x, v.state.y)

    def tl_to_own(self, x: float, y: float, depth: float) -> float:
        o = self.own.state
        return acoustics.transmission_loss(distance(o.x, o.y, x, y), o.depth, depth, self.env)

    def raw_signal_excess(self, v: Vessel) -> float:
        """SE vid egna hydrofoner, utan operatörens tröskel – ren fysik."""
        tl = self.tl_to_own(v.state.x, v.state.y, v.depth)
        return v.radiated_level(self.env) - tl - acoustics.power_sum(
            self.env.background_noise, self.own.self_noise())
