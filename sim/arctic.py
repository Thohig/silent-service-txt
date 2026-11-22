"""Arktis (sanning): drivstationen Nord-7 och en amerikansk atomubåt under isen.

Drivstationen står på isen och driver med den. Dess dieselgenerator hörs
genom isen på några sjömil; dess ljus syns i periskopet på längre håll än
mörkret annars tillåter.

Den amerikanska ubåten är på väg mot samma område. Den lyssnar bättre än vi
(lägre egenbrus, bättre sonar) men går inte till anfall: insatsreglerna
1962 är att följa och dokumentera. Hör den oss skuggar den oss på ett par
sjömils avstånd. Hör den en torped väjer den.

I krig (`roe = "attack"`, Duellen) går den närmare (`ATTACK_NM`), räknar vår kurs och fart ur
sina senaste pejlingar, öppnar torpedluckorna (`DOORS_LEVEL`, hörs på några sjömil) och skjuter
en Mk 37 med förhållning `DOORS_S` senare, om pejlingen är färsk och säker nog (`FIRE_SIGMA_NM`)
och vi är inom `FIRE_NM`. Sedan väntar den `FIRE_EVERY_S` och har `torpedoes` kvar.
`opening_shot_t` (torpeden i vattnet, `duell-torped`): den har redan sin lösning och öppnar luckorna
då, vad den än hör.

Skuggning (`state = "shadow"`, Svansen): den ligger `SHADOW_NM` akter om oss i vår döda sektor och styr
mot där den senast medlat oss (förföljare hamnar akter om målet), med vår fart ur skruvens varvtal, som den
märker med eftersläpning (`SHADOW_REACT_S`: saktar vi in hinner den komma närmare). Girar
vi går den rakt en stund innan den följer, och då kommer den ut ur sektorn. Den går till anfall (`trail`)
vid `shadow_until`, när den hör oss pinga, skjuta eller släppa skenmål, när den hör en torped, eller när
vi kommer närmare än `SHADOW_ALERT_NM`.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import acoustics
from .entities import Vessel
from .geo import bearing_to, distance, norm360
from .ship import ShipState
from .entities import Transient
from .weapons import MK37, Torpedo, launch_enemy_torpedo, lead_course

if TYPE_CHECKING:
    from .world import World

STATION_LEVEL = 142.0           # dieselgeneratorn genom isen
STATION_LIGHT_NM = 2.5          # stationens ljus syns i periskopet så här långt
US_SUB_BASE = 125.0             # amerikansk atomubåt 1962: bas + 1,5·fart
US_SUB_DT = 0.0                 # bättre sonar än vår
US_DETECT_S = 30                # så länge den måste höra oss innan den vet
US_FORGET_S = 900
TRAIL_NM = 2.0
ATTACK_NM = 2.5                 # krig: så nära går den för att skjuta
FIRE_NM = 4.0                   # skjuter inte på längre håll
FIRE_SIGMA_NM = 0.5             # pejlingen måste vara så säker
FIRE_DATUM_AGE_S = 60
FIRE_EVERY_S = 480               # omladdning och ny lösning
DOORS_S = 30                    # luckorna öppnas så här länge före skottet
DOORS_LEVEL = 150.0             # luckor och vattenfyllning: transient som hörs på några sjömil
US_TORPEDOES = 3                # laddade och redo i duellen
US_FORGET_ATTACK_S = 1800       # i krig söker den längre innan den ger upp
AWARE_S = 300                   # i krig: så färsk måste pejlingen vara för att den ska ha oss
SEARCH_AFTER_S = 120            # ingen ny pejling så länge: sök där vi hördes sist
SEARCH_KN = 6                   # tyst nog att höra
ATTACK_KN = 8                   # på skjutavstånd, på sidan om oss
SEARCH_RADIUS_NM = 0.8
US_MAX_SHADOW_KN = 18             # Skate: högsta fart
SHADOW_NM = 1.7                 # skuggning: så långt akter om oss
SHADOW_BAND_NM = 0.3            # fart efter avståndet utanför bandet
SHADOW_REACT_S = 90.0           # så länge innan den märkt att vi ändrat fart (tidskonstant)
SHADOW_ALERT_NM = 1.0           # närmare än så: vi har den, anfall
SHADOW_ALERT_SOUNDS = ("ping", "launch", "decoy")   # det från oss som säger att vi har den


class DriftStation(Vessel):
    """Nord-7: baracker och master på en isflak. Driver med isen."""
    drifts_with_ice = True

    def __init__(self, id: str, x: float, y: float):
        super().__init__(id=id, kind="station", state=ShipState(x=x, y=y, course=0, speed=0,
                                                                depth=2.0), side="neutral")

    def radiated_level(self, env) -> float:
        return STATION_LEVEL


class EnemySub(Vessel):
    def __init__(self, id: str, state: ShipState, base: float = US_SUB_BASE):
        super().__init__(id=id, kind="submarine", state=state, side="enemy")
        self.base = base

    def radiated_level(self, env) -> float:
        if self.sunk:
            return -999.0
        return self.base + 1.5 * max(self.state.speed, 0.0)


@dataclass
class SubDatum:
    x: float
    y: float
    depth: float
    sigma: float
    t: int

    def predict(self, now: int) -> tuple[float, float]:
        """Där vi tros vara nu (pejlingen räknar inte med vår fart)."""
        return self.x, self.y


class SubmarineAI:
    """Amerikansk atomubåt: transit -> patrull vid stationen; skuggar oss om den hör oss."""
    can_force = False                    # kan inte tvinga oss till ytan

    def __init__(self, vessel: EnemySub, rng: random.Random, station: DriftStation):
        self.vessel = vessel
        self.rng = rng
        self.station = station
        self.state = "transit"
        self.roe = "observe"
        self.datum: SubDatum | None = None
        self._heard_for = 0
        self.evade_until = -1
        self.next_listen = 0
        self.next_turn = 0
        self._now = 0
        self.torpedoes = US_TORPEDOES
        self.next_fire = 0
        self.doors_t: int | None = None          # skottet går då (luckorna är öppna)
        self.datums: list[SubDatum] = []         # senaste pejlingarna (kurs och fart ur dem)
        self.opening_shot_t: int | None = None   # skjuter på lösningen den har, då (duell-torped)
        self.shadow_until: int | None = None     # skuggning: anfaller då (Svansen)
        self._our_speed: float | None = None     # skuggning: vår fart som den uppfattat den

    def aware(self) -> bool:
        """Har den oss: skuggar, och (i krig) med en pejling som inte är äldre än `AWARE_S`.
        Söker den bara där vi var har den oss inte."""
        if self.state not in ("trail", "shadow"):
            return False
        if self.roe != "attack" or self.datum is None:
            return True
        return self._now - self.datum.t <= AWARE_S

    def _noise(self, world: World) -> float:
        s = self.vessel.state
        return acoustics.power_sum(world.env.noise_at(s.x, s.y), 48.0 + 1.0 * s.speed)

    def _tl(self, world: World, x: float, y: float, depth: float) -> float:
        s = self.vessel.state
        return acoustics.transmission_loss(distance(s.x, s.y, x, y), s.depth, depth, world.env) \
            + world.land_loss(s.x, s.y, x, y)

    # --- sensorer -------------------------------------------------------------------
    def _listen(self, world: World) -> None:
        own, now = world.own, world.time
        if own.sunk:
            return
        noise = self._noise(world)
        se = own.radiated_level(world.env) - self._tl(world, own.state.x, own.state.y,
                                                      own.depth) - noise - US_SUB_DT
        heard = se + self.rng.gauss(0, 2) > 0
        # transienter från oss: aktiv sonar, torpedutskjutning, nödblåsning
        for tr in world.transients:
            if tr.source_id != own.id:
                continue
            if tr.level - self._tl(world, tr.x, tr.y, tr.depth) - noise > 0:
                heard = True
                if tr.kind == "launch" and self.roe != "attack":
                    self.roe = "evade"
                if self.state == "shadow" and tr.kind in SHADOW_ALERT_SOUNDS:
                    self.state = "trail"             # vi har den: anfall
        self._heard_for = self._heard_for + 1 if heard else 0
        if heard and (self._heard_for >= US_DETECT_S or self.datum is not None):
            r = distance(self.vessel.state.x, self.vessel.state.y, own.state.x, own.state.y)
            err = 0.2 * r + 0.1
            self.datum = SubDatum(own.state.x + self.rng.gauss(0, err),
                                  own.state.y + self.rng.gauss(0, err),
                                  own.depth + self.rng.gauss(0, 15), err, now)
            self.datums = [d for d in self.datums if now - d.t <= 180] + [self.datum]
            if self.state not in ("trail", "shadow"):
                world.mission["us_sub_contact"] = world.mission.get("us_sub_contact", 0) + 1
                self.state = "trail"

    def _threats(self, world: World) -> None:
        s = self.vessel.state
        noise = self._noise(world)
        for t in world.contacts:
            if not isinstance(t, Torpedo) or t.done or t.side != "own":
                continue
            se = t.radiated_level(world.env) - self._tl(world, t.state.x, t.state.y, t.depth) - noise
            if se > 0:
                if self.state == "shadow":
                    self.state = "trail"
                self.evade_until = world.time + 240
                s.order_course(bearing_to(t.state.x, t.state.y, s.x, s.y))
                s.order_speed(25)

    # --- beslut -----------------------------------------------------------------------
    def step(self, world: World) -> None:
        if self.vessel.sunk:
            return
        now, s = world.time, self.vessel.state
        self._now = now
        if now >= self.next_listen:
            self.next_listen = now + 5
            self._listen(world)
        self._threats(world)
        if now < self.evade_until:
            return
        forget = US_FORGET_ATTACK_S if self.roe == "attack" else US_FORGET_S
        if self.datum is not None and now - self.datum.t > forget:
            self.datum = None
            self.state = "patrol"
        st = self.station.state
        if self.state == "shadow" and self.datum is not None:
            self._shadow(world, now)
            if self.state == "shadow":
                return
        if self.state == "trail" and self.datum is not None:
            d = self.datum
            r = distance(s.x, s.y, d.x, d.y)
            b = bearing_to(s.x, s.y, d.x, d.y)
            if self.roe == "attack":
                self._attack(world, d, r, b)
                return
            if r > TRAIL_NM + 0.5:
                s.order_course(b)
                s.order_speed(10)
            elif r < TRAIL_NM - 0.5:
                s.order_course(norm360(b + 180))
                s.order_speed(4)
            else:
                s.order_course(norm360(b + 60))      # håll avståndet, gå på sidan
                s.order_speed(5)
            return
        r = distance(s.x, s.y, st.x, st.y)
        if self.state == "transit" and r < 1.5:
            self.state = "patrol"
        if self.state == "transit":
            s.order_course(bearing_to(s.x, s.y, st.x, st.y))
            s.order_speed(8)
            return
        # patrull runt stationen, långsamt och tyst
        s.order_speed(4)
        if r > 2.0:
            s.order_course(bearing_to(s.x, s.y, st.x, st.y))
        elif now >= self.next_turn:
            self.next_turn = now + 600
            s.order_course(norm360(bearing_to(st.x, st.y, s.x, s.y) + 90))

    # --- krig ---------------------------------------------------------------------------
    def _target_motion(self) -> tuple[float, float]:
        """Vår kurs och fart ur de senaste pejlingarna (grovt)."""
        ds = self.datums
        if len(ds) < 2 or ds[-1].t - ds[0].t < 60:
            return 0.0, 0.0
        a, b = ds[0], ds[-1]
        dt_h = (b.t - a.t) / 3600.0
        sp = distance(a.x, a.y, b.x, b.y) / dt_h
        return bearing_to(a.x, a.y, b.x, b.y), min(sp, 30.0)

    def _fire_datum(self, now: int) -> SubDatum | None:
        """Pejlingarna senaste minuten medlade: eldledningens läge på oss (σ/√n)."""
        recent = [d for d in self.datums if now - d.t <= FIRE_DATUM_AGE_S]
        if not recent:
            return None
        n = len(recent)
        return SubDatum(sum(d.x for d in recent) / n, sum(d.y for d in recent) / n,
                        sum(d.depth for d in recent) / n,
                        sum(d.sigma for d in recent) / n / math.sqrt(n), recent[-1].t)

    def _attack(self, world: World, d: SubDatum, r: float, b: float) -> None:
        s, now = self.vessel.state, world.time
        if self.opening_shot_t is not None and now >= self.opening_shot_t and self.doors_t is None \
                and self.torpedoes > 0:
            self.opening_shot_t = None          # lösningen är gjord: luckorna upp nu
            self.doors_t = now + DOORS_S
            world.emit(Transient("doors", s.x, s.y, s.depth, DOORS_LEVEL, self.vessel.id, now))
        if now - d.t > SEARCH_AFTER_S and self.doors_t is None:
            self._search(d, r, b, now)
            return
        d = self._fire_datum(now) or d
        r, b = distance(s.x, s.y, d.x, d.y), bearing_to(s.x, s.y, d.x, d.y)
        if self.doors_t is not None and now >= self.doors_t:
            self.doors_t = None
            if self.torpedoes > 0:
                course, speed = self._target_motion()
                aim = lead_course(s.x, s.y, d.x, d.y, course, speed, MK37.speed) if speed > 1 else b
                launch_enemy_torpedo(world, self.vessel, MK37, aim, max(20.0, d.depth))
                self.torpedoes -= 1
                self.next_fire = now + FIRE_EVERY_S
                world.mission["us_fired"] = world.mission.get("us_fired", 0) + 1
        ready = self.torpedoes > 0 and now >= self.next_fire and self.doors_t is None
        if ready and r <= FIRE_NM and d.sigma <= FIRE_SIGMA_NM and now - d.t <= FIRE_DATUM_AGE_S:
            self.doors_t = now + DOORS_S
            world.emit(Transient("doors", s.x, s.y, s.depth, DOORS_LEVEL, self.vessel.id, now))
        # håll skjutavståndet, på sidan om vår kurs
        if r > ATTACK_NM + 0.5:
            s.order_course(b)
            s.order_speed(12)
        elif r < ATTACK_NM - 1.0:
            s.order_course(norm360(b + 180))
            s.order_speed(6)
        else:
            s.order_course(norm360(b + 70))
            s.order_speed(ATTACK_KN)

    def _shadow(self, world: World, now: int) -> None:
        """Skugga: mot där vi medlat hördes senast, farten efter avståndet (se modulens text)."""
        s = self.vessel.state
        if self.shadow_until is not None and now >= self.shadow_until:
            self.state = "trail"
            return
        d = self._fire_datum(now) or self.datum
        r, b = distance(s.x, s.y, d.x, d.y), bearing_to(s.x, s.y, d.x, d.y)
        if r < SHADOW_ALERT_NM:
            self.state = "trail"
            return
        true = max(0.0, world.own.state.speed)           # skruvens varvtal, med eftersläpning
        if self._our_speed is None:
            self._our_speed = true
        self._our_speed += (true - self._our_speed) / SHADOW_REACT_S
        ours = self._our_speed
        if r > SHADOW_NM + SHADOW_BAND_NM:
            speed = ours + 3
        elif r < SHADOW_NM - SHADOW_BAND_NM:
            speed = ours - 2
        else:
            speed = ours
        s.order_course(b)
        s.order_speed(int(min(US_MAX_SHADOW_KN, max(3.0, speed))))

    def _search(self, d: SubDatum, r: float, b: float, now: int) -> None:
        """Tappat oss: dit vi hördes sist, tyst och lyssnande, sedan i en växande cirkel."""
        s = self.vessel.state
        s.order_speed(SEARCH_KN)
        if r > SEARCH_RADIUS_NM:
            s.order_course(b)
        elif now >= self.next_turn:
            self.next_turn = now + 240
            s.order_course(norm360(b + 100))

