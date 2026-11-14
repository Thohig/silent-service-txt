"""Fiendens beteende: en amerikansk jagare i karantäntjänst, 1962.

Jagaren är en del av sanningen. Den har egna sensorer och bygger en
"datum": sin bild av var ubåten finns, med en osäkerhet.

Sensorer:
- aktiv skrovsonar (pingar; språngskiktet skyddar ubåten)
- passiv lyssning (svag i egen fart, men hör transienter som pingar,
  torpedutskjutningar och nödblåsning)
- radar/utkik mot periskop, master och ubåt i ytläge
- radarvarnare och pejling mot ubåtens radar och kortvågsradio

Tillstånd: patrol -> prosecute (söker kring datum) -> attack (håller
kontakt, fäller sjunkbomber) och evade (undanmanöver mot torped).

Insatsregler (roe): "signal" fäller signalsjunkbomber och uppmanar via
undervattenstelefon ubåten att gå till ytan. Om ubåten agerar fientligt
(torped) blir reglerna "lethal": skarpa sjunkbomber. Med `escalate_after`
går jagaren över till skarpa efter så många övningsanfall utan att ubåten
gått upp.

Skrovsonaren ser inte brantare än DEAD_ZONE_DEG nedåt: en djup ubåt tappas
i slutet av anfallet, som då går på förutsagt läge. Efter detonationer nära
jagaren är sonaren döv en stund. Med `leash_nm` släpper jagaren jakten när
datumet ligger så långt utanför dess område.

Jagare i samma grupp (`partners`) delar sina fix över radio: en partner
utan bättre bild får datumet med större osäkerhet.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import acoustics
from .entities import Transient, Vessel
from .geo import bearing_to, distance, norm360
from .seabed import bottom_clutter
from .weapons import Decoy, Torpedo, drop_charges

if TYPE_CHECKING:
    from .world import World

DT_PASSIVE = 6.0
DT_ACTIVE = 10.0
PING_INTERVAL = {"patrol": 30, "prosecute": 15, "attack": 8, "evade": 30}
DATUM_TIMEOUT = 900
ATTACK_COOLDOWN = 240
UWT_INTERVAL = 180
WAKE_NM = 0.3               # ubåt så nära ett handelsfartyg gömmer sig i dess kölvatten
WAKE_DEPTH_M = 100
WAKE_CLUTTER_DB = 12.0
DEAD_ZONE_DEG = 20.0        # skrovsonaren ser inte brantare nedåt: djup ubåt tappas nära
DEAF_S = 60                 # efter en detonation nära jagaren hör sonaren ingenting
DEAF_NM = 1.5
SHARED_SIGMA_NM = 0.4       # ett fix från en annan jagare, med navigationsfel och fördröjning


@dataclass
class Datum:
    x: float
    y: float
    depth: float
    sigma: float
    t: int
    vx: float = 0.0     # knop
    vy: float = 0.0

    def predict(self, now: int) -> tuple[float, float]:
        dt_h = (now - self.t) / 3600.0
        return self.x + self.vx * dt_h, self.y + self.vy * dt_h


class DestroyerAI:
    def __init__(self, vessel: Vessel, rng: random.Random, area: float = 20.0,
                 patrol_speed: float = 15.0, escalate_after: int | None = None,
                 leash_nm: float | None = None):
        self.vessel = vessel
        self.rng = rng
        self.area = area
        self.patrol_speed = patrol_speed
        self.state = "patrol"
        self.roe = "signal"
        self.datum: Datum | None = None
        self.fixes: list[tuple[int, float, float]] = []
        self.next_ping = rng.randint(0, 30)
        self.last_contact_t = -10**9
        self.evade_until = -1
        self.attack_ready_t = 0
        self.opening_until = -1
        self.next_uwt = 0
        self.next_search_turn = 0
        self.next_passive = 0
        self.seen_torpedoes: set[str] = set()
        self.attacks = 0
        self.escalate_after = escalate_after
        self.leash_nm = leash_nm
        self.deaf_until = -1
        self.partners: list[DestroyerAI] = []

    def start_hunt(self, x: float, y: float, depth: float, sigma: float, t: int = 0,
                   contact: bool = False) -> None:
        """Börja spelet mitt i jakten: datum på ubåten, ev. med färsk kontakt."""
        self.datum = Datum(x, y, depth, sigma, t)
        self.state = "prosecute"
        if contact:
            self.last_contact_t = t
            self.fixes = [(t, x, y)]
            self.next_ping = t + 1

    # ------------------------------------------------------------------ status
    def aware(self) -> bool:
        return self.state in ("prosecute", "attack")

    def _noise(self, world: World) -> float:
        s = self.vessel.state
        return acoustics.power_sum(world.env.noise_at(s.x, s.y),
                                   acoustics.hull_sonar_self_noise(self.vessel.state.speed))

    def _noise_toward(self, world: World, noise: float, tgt: Vessel) -> float:
        """Brus i den riktning sonaren lyssnar: ett handelsfartyg i samma bäring dränker målet."""
        s = self.vessel.state
        mask = world.masking_noise(s.x, s.y, 5.0, tgt.state.x, tgt.state.y)
        return noise if mask is None else acoustics.power_sum(noise, mask)

    @staticmethod
    def _wake_clutter(world: World, tgt: Vessel) -> float:
        """Ekot från en ubåt under ett handelsfartygs kölvatten drunknar bland skrovekon
        och luftbubblor (dB avdrag)."""
        if tgt.depth > WAKE_DEPTH_M:
            return 0.0
        for m in world.neutral_ships:
            if not m.sunk and distance(m.state.x, m.state.y, tgt.state.x, tgt.state.y) < WAKE_NM:
                return WAKE_CLUTTER_DB
        return 0.0

    def _tl(self, world: World, x: float, y: float, depth: float) -> float:
        s = self.vessel.state
        return acoustics.transmission_loss(distance(s.x, s.y, x, y), 5.0, depth, world.env)

    # ------------------------------------------------------------------ datum
    def _set_datum(self, world: World, x: float, y: float, depth: float, sigma: float,
                   fix: bool = False) -> None:
        now = world.time
        if self.datum is not None and not fix and sigma > self.datum.sigma \
                and now - self.datum.t < 120:
            return          # behåll bättre färsk information
        vx = vy = 0.0
        if fix:
            self.fixes = [f for f in self.fixes if now - f[0] <= 180] + [(now, x, y)]
            if len(self.fixes) >= 2 and self.fixes[-1][0] - self.fixes[0][0] >= 30:
                t0, x0, y0 = self.fixes[0]
                dt_h = (now - t0) / 3600.0
                vx, vy = (x - x0) / dt_h, (y - y0) / dt_h
                sp = math.hypot(vx, vy)
                if sp > 30:
                    vx, vy = vx * 30 / sp, vy * 30 / sp
        self.datum = Datum(x, y, depth, sigma, now, vx, vy)
        if fix:
            for p in self.partners:
                p._shared_datum(now, self.datum)

    def _shared_datum(self, now: int, d: Datum) -> None:
        """En annan jagare i gruppen meddelar sitt fix över radio."""
        if self.vessel.sunk:
            return
        sigma = d.sigma + SHARED_SIGMA_NM
        mine = self.datum
        if mine is not None and now - mine.t < 120 and mine.sigma <= sigma:
            return
        self.datum = Datum(d.x, d.y, d.depth, sigma, now, d.vx, d.vy)

    def _datum_from_bearing(self, world: World, x: float, y: float, rel_err: float,
                            depth_guess: float = 100.0) -> None:
        s = self.vessel.state
        r = distance(s.x, s.y, x, y)
        b = math.radians(bearing_to(s.x, s.y, x, y) + self.rng.gauss(0, 2))
        r_est = max(0.2, r * math.exp(self.rng.gauss(0, rel_err)))
        self._set_datum(world, s.x + r_est * math.sin(b), s.y + r_est * math.cos(b),
                        depth_guess, rel_err * r + 0.3)

    # ------------------------------------------------------------------ sensorer
    def _passive(self, world: World, noise: float) -> None:
        own = world.own
        if world.time >= self.next_passive:
            self.next_passive = world.time + 10
            for tgt in [own, *[d for d in world.contacts if isinstance(d, Decoy)]]:
                if tgt.sunk:
                    continue
                se = tgt.radiated_level(world.env) - self._tl(world, tgt.state.x, tgt.state.y,
                                                              tgt.depth) - self._noise_toward(
                    world, noise, tgt) - DT_PASSIVE
                if se + self.rng.gauss(0, 2) > 0:
                    self._datum_from_bearing(world, tgt.state.x, tgt.state.y, 0.4,
                                             depth_guess=self.rng.gauss(100, 40))
        friendly = {v.id for v in world.contacts if v.side == self.vessel.side}
        for tr in world.transients:
            if tr.source_id in friendly or tr.kind in ("splash", "uwt", "breakup"):
                continue
            hostile = tr.kind == "launch" or (tr.kind == "explosion" and tr.source_id.startswith("T"))
            if tr.kind == "explosion" and not hostile:
                continue
            se = tr.level - self._tl(world, tr.x, tr.y, tr.depth) - noise - DT_PASSIVE
            if se <= 0:
                continue
            if hostile:
                self.roe = "lethal"
            if tr.kind in ("ping", "launch", "echosounder"):
                self._datum_from_bearing(world, tr.x, tr.y, 0.25 if tr.kind == "ping" else 0.3,
                                         depth_guess=max(20.0, tr.depth + self.rng.gauss(0, 40)))

    def _masts(self, world: World) -> None:
        own = world.own
        if own.sunk:
            return
        r = distance(self.vessel.state.x, self.vessel.state.y, own.state.x, own.state.y)
        if own.surfaced:
            det_r, p = (10.0 if world.env.is_day(world.time) else 6.0), 0.2
        elif own.masts_up(world.time):
            det_r, p = 4.0, 0.03
        else:
            return
        if r < det_r and self.rng.random() < p:
            self._set_datum(world, own.state.x + self.rng.gauss(0, 0.05),
                            own.state.y + self.rng.gauss(0, 0.05), own.state.depth, 0.1, fix=True)
            self.last_contact_t = world.time

    def _emissions(self, world: World) -> None:
        s = self.vessel.state
        for em in world.emissions:
            if em.source_id != world.own.id:
                continue
            r = distance(s.x, s.y, em.x, em.y)
            if em.kind == "radar" and r < 25:
                self._datum_from_bearing(world, em.x, em.y, 0.3, depth_guess=15.0)
            elif em.kind == "hf" and r < 200:
                self._set_datum(world, em.x + self.rng.gauss(0, 1.5),
                                em.y + self.rng.gauss(0, 1.5), 15.0, 2.0)

    def _threats(self, world: World, noise: float) -> None:
        s = self.vessel.state
        for t in world.contacts:
            if not isinstance(t, Torpedo) or t.done:
                continue
            se = t.radiated_level(world.env) - self._tl(world, t.state.x, t.state.y,
                                                        t.depth) - noise - DT_PASSIVE
            if se <= 0:
                continue
            self.roe = "lethal"
            self.evade_until = world.time + 180
            s.order_course(bearing_to(t.state.x, t.state.y, s.x, s.y))
            s.order_speed(30)
            if t.id not in self.seen_torpedoes:
                self.seen_torpedoes.add(t.id)
                lx, ly = t.launch_xy
                self._set_datum(world, lx + self.rng.gauss(0, 0.7), ly + self.rng.gauss(0, 0.7),
                                100.0, 1.0)

    def _ping(self, world: World, noise: float) -> None:
        s = self.vessel.state
        now = world.time
        world.emit(Transient("ping", s.x, s.y, 5.0, acoustics.PING_LEVEL_SHIP, self.vessel.id, now))
        self.next_ping = now + PING_INTERVAL[self.state] + self.rng.randint(0, 3)
        echoes = []
        for tgt in [world.own, *[d for d in world.contacts if isinstance(d, Decoy)]]:
            if tgt.sunk or self._in_dead_zone(tgt):
                continue
            tl = self._tl(world, tgt.state.x, tgt.state.y, tgt.depth)
            se = acoustics.active_excess(acoustics.PING_LEVEL_SHIP, tl, tgt.target_strength,
                                         self._noise_toward(world, noise, tgt), DT_ACTIVE) \
                - self._wake_clutter(world, tgt) - bottom_clutter(world, tgt) \
                + self.rng.gauss(0, 3)
            if se > 0:
                echoes.append((tgt, se))
        if not echoes:
            return
        if self.datum is not None and len(echoes) > 1:
            px, py = self.datum.predict(now)
            tgt = min(echoes, key=lambda e: distance(px, py, e[0].state.x, e[0].state.y))[0]
        else:
            tgt = max(echoes, key=lambda e: e[1])[0]
        if now - self.last_contact_t > 120:
            world.mission["enemy_contacts"] = world.mission.get("enemy_contacts", 0) + 1
        self.last_contact_t = now
        self._set_datum(world, tgt.state.x + self.rng.gauss(0, 0.03),
                        tgt.state.y + self.rng.gauss(0, 0.03),
                        max(15.0, tgt.depth + self.rng.gauss(0, 35)), 0.08, fix=True)

    def _in_dead_zone(self, tgt: Vessel) -> bool:
        s = self.vessel.state
        r_m = distance(s.x, s.y, tgt.state.x, tgt.state.y) * 1852.0
        return r_m < tgt.depth / math.tan(math.radians(DEAD_ZONE_DEG))

    def _beyond_leash(self, now: int) -> bool:
        if self.leash_nm is None or self.datum is None:
            return False
        px, py = self.datum.predict(now)
        m = self.leash_nm
        return not (-m <= px <= self.area + m and -m <= py <= self.area + m)

    # ------------------------------------------------------------------ beslut
    def step(self, world: World) -> None:
        if self.vessel.sunk:
            return
        noise = self._noise(world)
        s = self.vessel.state
        for tr in world.transients:
            if tr.kind == "explosion" and distance(s.x, s.y, tr.x, tr.y) < DEAF_NM:
                self.deaf_until = world.time + DEAF_S
        if world.time < self.deaf_until:
            self._masts(world)
            self._emissions(world)
            self._decide(world)
            return
        self._passive(world, noise)
        self._masts(world)
        self._emissions(world)
        self._threats(world, noise)
        if world.time >= self.next_ping:
            self._ping(world, noise)
        self._decide(world)

    def _decide(self, world: World) -> None:
        now, s = world.time, self.vessel.state
        if now < self.evade_until:
            self.state = "evade"
            return
        if self.state == "evade":
            self.state = "prosecute" if self.datum else "patrol"
        if self._beyond_leash(now):
            self.datum = None               # utanför vår sektor: släpp jakten
            self.state = "patrol"
        if self.datum is not None and now - self.datum.t > DATUM_TIMEOUT:
            self.datum = None
            self.state = "patrol"

        fresh = now - self.last_contact_t <= 40
        if self.state == "patrol" and self.datum is not None:
            self.state = "prosecute"

        if self.state == "prosecute":
            if fresh and self.datum.sigma < 0.3:
                self.state = "attack"
            else:
                px, py = self.datum.predict(now)
                d = distance(s.x, s.y, px, py)
                if d > 1.0:
                    s.order_speed(22)
                    s.order_course(bearing_to(s.x, s.y, px, py))
                else:
                    s.order_speed(12)
                    if now >= self.next_search_turn:
                        self.next_search_turn = now + 120
                        s.order_course(norm360(s.course + 90))
                return

        if self.state == "attack":
            if now < self.opening_until:
                s.order_speed(18)
                return
            if now - self.last_contact_t > 90:
                self.state = "prosecute"
                return
            px, py = self.datum.predict(now)
            s.order_speed(15)
            s.order_course(bearing_to(s.x, s.y, px, py))
            if self.roe == "signal" and now >= self.next_uwt:
                self.next_uwt = now + UWT_INTERVAL
                world.emit(Transient("uwt", s.x, s.y, 5.0, acoustics.UWT_LEVEL, self.vessel.id, now))
            if distance(s.x, s.y, px, py) < 0.12 and now >= self.attack_ready_t:
                practice = self.roe == "signal"
                drop_charges(world, self.vessel, px, py, self.datum.depth,
                             n=3 if practice else 9, practice=practice)
                self.attacks += 1
                if practice and self.escalate_after is not None \
                        and self.attacks >= self.escalate_after:
                    self.roe = "lethal"
                self.attack_ready_t = now + ATTACK_COOLDOWN
                self.opening_until = now + 90
            return

        # patrull
        s.order_speed(self.patrol_speed)
        m = 1.0
        if not (-m <= s.x <= self.area + m and -m <= s.y <= self.area + m):
            if "course" not in s.changing():
                c = bearing_to(s.x, s.y, self.area / 2, self.area / 2)
                s.order_course(norm360(c + self.rng.uniform(-40, 40)))
