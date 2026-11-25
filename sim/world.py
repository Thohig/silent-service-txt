"""Sanningen: världens exakta tillstånd. Spelaren ser aldrig detta direkt.

Ett tick:
  1. transienter/emissioner från förra steget blir hörbara nu; vädret (`weather.py`) sätter sjögången
  2. alla fartyg rör sig (plus ström); isen driver och ubåten kan stöta i den
  3. egen ubåts system (reaktor, batteri, läckor, skrov)
  4. vapen (torpeder, sjunkbomber, skenmål)
  5. civil trafik (nya fartyg) och fiendens och handelsfartygens beteende
  6. lotsen: fartyg som är på väg upp på grunt vatten girar undan (`pilotage.py`)
  7. kontroll av spelslut
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, TypeVar

import numpy as np

from . import acoustics
from .entities import Emission, Transient, Vessel
from .environment import Environment
from .geo import angle_diff, bearing_to, distance
from .goals import Goal
from .ice import ice_contact, ice_sounds
from .collision import ship_contact
from .seabed import bottom_contact
from .ownship import OwnShip
from .pilotage import steer_clear
from .weapons import Torpedo, step_weapons

LAND_STEP_NM = 0.05         # land mellan två punkter: prov så här tätt längs linjen
LAND_BLOCK_DB = 60.0        # ljud genom ett berg: i praktiken inget
NO_DIVE_MARGIN_NM = 0.2     # förbudet gäller klart innanför mynningen
G = TypeVar("G", bound=Goal)

SURFACE_GRACE_S = 60        # i ytläge sedda av fienden: så länge innan uppdraget är förlorat
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
    mission: dict[str, Any] = field(default_factory=dict)   # det som hänt (sänkt, foto, rapport …)
    goals: list[Goal] = field(default_factory=list)         # scenariots mål (`goals.py`)
    outcome: dict[str, Any] | None = None
    patrol_end: int | None = None
    # det som skickar in nya enheter under spelet (civil trafik, flyg); var och en har step(world)
    spawners: list[Any] = field(default_factory=list)
    # ett spel utan slut när alla fiender är sänkta (krigspatrullen: staben sänder nya uppgifter)
    open_ended: bool = False
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
        prev = (o.x, o.y, o.depth, o.course)
        env = self.env
        if env.weather is not None:
            env.weather.step(env, self.time)    # sjögången (sim/weather.py)
        if env.showers is not None:
            env.showers.step(self.time)         # regn och dimma (sim/weather.py)
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
        ship_contact(self)

        self.own.update(self, dt)
        step_weapons(self, dt)
        for sp in self.spawners:
            sp.step(self)
        for ai in self.ais:
            ai.step(self)
        steer_clear(self)
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
        if enemies and not self.open_ended and all(v.sunk for v in enemies):
            self.mission.setdefault("all_sunk_t", self.time)
            if self.time - self.mission["all_sunk_t"] >= SINK_ENDING_DELAY:
                self.end("sank")
            return
        for goal in sorted(self.goals, key=lambda g: g.RANK):
            if goal.check(self):
                return
        if self.own.surfaced:
            seen = any(not ai.vessel.sunk and getattr(ai, "can_force", True) and
                       (ai.aware() or self.true_range(ai.vessel) < 6.0) for ai in self.ais)
            if seen:
                # ett ögonblick att dyka igen (utkiken ropar ut fartyget); ligger vi kvar är det slut
                t0 = self.mission.setdefault("seen_surfaced_t", self.time)
                if self.time - t0 >= SURFACE_GRACE_S:
                    self.end("forced")
                    return
            else:
                self.mission.pop("seen_surfaced_t", None)
        else:
            self.mission.pop("seen_surfaced_t", None)
        if self.patrol_end is not None and self.time >= self.patrol_end:
            self.end("patrol_end")

    def goal(self, cls: type[G]) -> G | None:
        """Scenariots första mål av en viss sort (t.ex. övningsledaren som bockar av)."""
        return next((g for g in self.goals if isinstance(g, cls)), None)

    # --- sanningshjälp (sensorer, vapen, sanningslogg) ----------------------
    def _hunting_us(self, ai: Any, max_sigma: float | None = None) -> bool:
        """En jägare som är medveten och vars datum ligger nära oss (inte ett skenmål).
        max_sigma: bara ett datum så skarpt räknas (annars räcker en grov pejling)."""
        if ai.vessel.sunk or not getattr(ai, "aware", lambda: False)():
            return False
        d = getattr(ai, "datum", None)
        if d is None:
            return True
        if max_sigma is not None and d.sigma > max_sigma:
            return False
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

    def _in_fjord(self) -> bool:
        sb = self.env.seabed
        o = self.own.state
        return sb is not None and any(
            hasattr(f, "in_fjord") and bool(f.in_fjord(o.x, o.y, -NO_DIVE_MARGIN_NM))
            for f in sb.features)

    def land_between(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        """Ligger land mellan punkterna? Sanning: ljud och syn går inte genom berg."""
        sb = self.env.seabed
        if sb is None or not sb.has_land:
            return False
        r = distance(x0, y0, x1, y1)
        n = int(r / LAND_STEP_NM)
        if n < 2:
            return False
        t = np.arange(1, n) / n
        return bool((sb.depths(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t) <= 0).any())

    def land_loss(self, x0: float, y0: float, x1: float, y1: float) -> float:
        """Extra förlust (dB) när land ligger mellan källan och lyssnaren."""
        return LAND_BLOCK_DB if self.land_between(x0, y0, x1, y1) else 0.0

    def in_sight(self, x: float, y: float) -> bool:
        """Kan vi se platsen från ubåten (inget land mellan)?"""
        o = self.own.state
        return not self.land_between(o.x, o.y, x, y)

    def tl_to_own(self, x: float, y: float, depth: float) -> float:
        o = self.own.state
        return acoustics.transmission_loss(distance(o.x, o.y, x, y), o.depth, depth, self.env) \
            + self.land_loss(o.x, o.y, x, y)

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
