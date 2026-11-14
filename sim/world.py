"""Sanningen: världens exakta tillstånd. Spelaren ser aldrig detta direkt.

Ett tick:
  1. transienter/emissioner från förra steget blir hörbara nu
  2. alla fartyg rör sig (plus ström); isen driver och ubåten kan stöta i den
  3. egen ubåts system (reaktor, batteri, läckor, skrov)
  4. vapen (torpeder, sjunkbomber, skenmål)
  5. civil trafik (nya fartyg) och fiendens och handelsfartygens beteende
  6. kontroll av spelslut
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from . import acoustics
from .entities import Emission, Transient, Vessel
from .environment import Environment
from .geo import angle_diff, bearing_to, distance
from .ice import ice_contact, ice_sounds
from .seabed import bottom_contact
from .ownship import OwnShip
from .weapons import Torpedo, step_weapons

SINK_ENDING_DELAY = 45      # sekunder brytningsljud innan spelet slutar
HUNT_NEAR_NM = 1.0          # ett datum så nära oss räknas som att jägaren har oss
MASK_BEAM_DEG = 4.0         # ett neutralt fartygs brus döljer andra ljud inom så här många grader


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
    # det som skickar in nya enheter under spelet (civil trafik, flyg); var och en har step(world)
    spawners: list[Any] = field(default_factory=list)
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

    @property
    def neutral_ships(self) -> list[Vessel]:
        """Civila fartyg (inte isljud eller drivstationen)."""
        return [v for v in self.contacts if v.side == "neutral" and v.is_ship]

    # --- tick ---------------------------------------------------------------
    def tick(self, dt: int = 1) -> None:
        if self.outcome is not None:
            return
        self.transients, self._pending_t = self._pending_t, []
        self.emissions, self._pending_e = self._pending_e, []

        o = self.own.state
        prev = (o.x, o.y, o.depth)
        env = self.env
        ice = env.ice
        for v in [self.own, *self.contacts]:
            if v.sunk or isinstance(v, Torpedo):
                continue
            if v.airborne:
                v.state.step(dt)            # flyget bryr sig inte om strömmen
                continue
            if v.drifts_with_ice and ice is not None:
                ivx, ivy = ice.drift_velocity()
                v.state.x += ivx * dt
                v.state.y += ivy * dt
                continue
            if v is self.own and self.own.sys.on_bottom:
                continue                    # ligger stilla på botten
            if v.kind == "moored":
                continue                    # till ankars
            v.state.step(dt)
            if v is self.own and ice is not None and v.state.depth <= 1.0:
                # i ytläge i en vak eller råk: ubåten ligger fast i isen och driver med den
                ivx, ivy = ice.drift_velocity()
                v.state.x += ivx * dt
                v.state.y += ivy * dt
                continue
            cvx, cvy = env.current_at(v.state.x, v.state.y, self.time)
            v.state.x += cvx * dt
            v.state.y += cvy * dt
            if v.state.depth <= 0 and v is self.own:
                v.state.depth = 0.0
        if self.env.ice is not None:
            self.env.ice.advance(dt)
            ice_contact(self, prev, dt)
            ice_sounds(self)
        bottom_contact(self, prev)

        self.own.update(self, dt)
        step_weapons(self, dt)
        for sp in self.spawners:
            sp.step(self)
        for ai in self.ais:
            ai.step(self)
        self.time += dt
        self._check_outcome()

    def _check_outcome(self) -> None:
        if self.outcome is not None:
            return
        if any(v.sunk for v in self.neutral_ships):
            self.mission.setdefault("neutral_sunk_t", self.time)
            if self.time - self.mission["neutral_sunk_t"] >= SINK_ENDING_DELAY:
                self.end("neutral_sunk")
            return
        enemies = self.enemy_ships
        if enemies and all(v.sunk for v in enemies):
            self.mission.setdefault("all_sunk_t", self.time)
            if self.time - self.mission["all_sunk_t"] >= SINK_ENDING_DELAY:
                self.end("sank")
            return
        goal = self.mission.get("goal")
        if goal and self.own.surfaced:
            target = next((v for v in self.contacts if v.id == goal["id"]), None)
            if target is not None and self.true_range(target) <= goal["radius_nm"]:
                self.end(goal["outcome"])
                return
        esc = self.mission.get("escape")
        if esc and esc.get("requires_photo") is not None and \
                self.mission.get("best_photo", -1) < esc["requires_photo"]:
            esc = None                      # inte utan bilderna
        if esc and not self.own.surfaced and self._outside_area(esc["margin_nm"]) \
                and not any(self._hunting_us(ai) for ai in self.ais):
            self.end(esc["outcome"])
            return
        if self.own.surfaced:
            for ai in self.ais:
                if ai.vessel.sunk or not getattr(ai, "can_force", True):
                    continue
                if ai.aware() or self.true_range(ai.vessel) < 6.0:
                    self.end("forced")
                    return
        if self.patrol_end is not None and self.time >= self.patrol_end:
            self.end("patrol_end")

    # --- sanningshjälp (sensorer, vapen, sanningslogg) ----------------------
    def _hunting_us(self, ai: Any) -> bool:
        """En jägare som är medveten och vars datum ligger nära oss (inte ett skenmål)."""
        if ai.vessel.sunk or not getattr(ai, "aware", lambda: False)():
            return False
        d = getattr(ai, "datum", None)
        if d is None:
            return True
        px, py = d.predict(self.time)
        o = self.own.state
        return distance(o.x, o.y, px, py) <= max(HUNT_NEAR_NM, 3 * d.sigma)

    def _outside_area(self, margin: float) -> bool:
        o = self.own.state
        return not (-margin <= o.x <= self.size_nm + margin
                    and -margin <= o.y <= self.size_nm + margin)

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
        """SE vid egna hydrofoner, utan operatörens tröskel – ren fysik.
        Ett högljutt neutralt fartyg i nästan samma bäring dränker signalen."""
        o = self.own.state
        tl = self.tl_to_own(v.state.x, v.state.y, v.depth)
        noise = [self.background_at_own(), self.own.self_noise()]
        mask = self.masking_noise(o.x, o.y, o.depth, v.state.x, v.state.y, exclude=(v.id,))
        if mask is not None:
            noise.append(mask)
        return v.radiated_level(self.env) - tl - acoustics.power_sum(*noise)

    def masking_noise(self, lx: float, ly: float, ldepth: float, tx: float, ty: float,
                      exclude: tuple[str, ...] = (),
                      sides: tuple[str, ...] = ("neutral",)) -> float | None:
        """Brus från fartyg (normalt neutrala handelsfartyg) som ligger nästan i samma
        bäring som målet, sett från lyssnaren. None om inget fartyg skymmer."""
        b = bearing_to(lx, ly, tx, ty)
        levels = []
        for m in self.contacts:
            if m.side not in sides or not m.is_ship or m.sunk or m.id in exclude:
                continue
            if abs(angle_diff(bearing_to(lx, ly, m.state.x, m.state.y), b)) > MASK_BEAM_DEG:
                continue
            r = distance(lx, ly, m.state.x, m.state.y)
            levels.append(m.radiated_level(self.env)
                          - acoustics.transmission_loss(r, ldepth, m.depth, self.env))
        return acoustics.power_sum(*levels) if levels else None

    def background_at_own(self) -> float:
        o = self.own.state
        return self.env.noise_at(o.x, o.y)
