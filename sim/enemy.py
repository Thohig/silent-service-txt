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

Varje jagarkapten har ett temperament (`Temperament`): metodisk (som förut), envis
(söker längre och saktare, lyssnar bättre) eller ivrig (stänger och söker fort, hör sämre,
anfaller på sämre datum och ger upp tidigare). Det dras ur en egen ström, så att jagarens
övriga slump inte flyttas. Ubåten får veta det bara genom vad besättningen hör (plottet).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import acoustics
from .entities import Transient, Vessel
from .environment import MOON_SIL_DEG, MOON_SIL_LIGHT, radar_clutter_f, sea_ping_loss_db
from .geo import angle_diff, bearing_to, distance, norm360
from .seabed import bottom_clutter, shallow_reverb
from .weapons import Decoy, Torpedo, drop_charges
from .weather import RAIN_RADAR_F

if TYPE_CHECKING:
    from .world import World

DT_PASSIVE = 6.0
DT_ACTIVE = 10.0
PING_INTERVAL = {"patrol": 30, "prosecute": 15, "attack": 8, "evade": 30}
DATUM_TIMEOUT = 900
SHADOW_PERIOD_S = 90 * 60   # i patrull: skugga spaningstrålaren så länge av varje sådan period
SHADOW_ON_S = 30 * 60
SHADOW_NM = 1.0
# Pejlnätet mot vår kortvåg (radio.py): under DF_MIN_S hinner de inte, över DF_SURE_S alltid;
# felet krymper med längden (1,5 nm för 30 s, som förut).
DF_MIN_S = 10.0
DF_SURE_S = 25.0
DF_SIGMA_30S_NM = 1.5
DF_SIGMA_MIN_NM = 0.7
DF_SIGMA_MAX_NM = 3.0
ATTACK_COOLDOWN = 240


def df_probability(duration: float) -> float:
    """Sannolikheten att pejlnätet får ett fix på en kortvågssändning så här lång (s)."""
    return min(1.0, max(0.0, (duration - DF_MIN_S) / (DF_SURE_S - DF_MIN_S)))


def df_sigma(duration: float) -> float:
    """Pejlfixets fel (nm, 1σ) för en sändning så här lång (s)."""
    return min(DF_SIGMA_MAX_NM, max(DF_SIGMA_MIN_NM, DF_SIGMA_30S_NM * math.sqrt(30.0 / duration)))
UWT_INTERVAL = 180
WAKE_NM = 0.3               # ubåt så nära ett handelsfartyg gömmer sig i dess kölvatten
WAKE_DEPTH_M = 100
WAKE_CLUTTER_DB = 12.0
DEAD_ZONE_DEG = 20.0        # skrovsonaren ser inte brantare nedåt: djup ubåt tappas nära
DEAF_S = 60                 # efter en detonation nära jagaren hör sonaren ingenting
DEAF_NM = 1.5
SHARED_SIGMA_NM = 0.4       # ett fix från en annan jagare, med navigationsfel och fördröjning


MOON_GLITTER_F = 1.5        # plymen i månglittret: så mycket lättare att se


@dataclass(frozen=True)
class Temperament:
    """Jagarkaptenens sätt att jaga, som avvikelser från fartygets egna värden."""
    name: str
    close_add: float = 0.0      # kn till SPEED_CLOSE
    search_add: float = 0.0     # kn till SPEED_SEARCH
    ping_mult: float = 1.0      # pingintervallen gånger detta
    timeout_mult: float = 1.0   # DATUM_TIMEOUT gånger detta: så länge han söker på ett gammalt datum
    turn_s: int = 120           # sökgirarna kring datumet
    attack_sigma: float = 0.3   # datumet så här säkert (nm): han går in och fäller


TEMPERAMENTS = {
    "metodisk": Temperament("metodisk"),
    "envis": Temperament("envis", search_add=-2.0, timeout_mult=2.0, turn_s=90),
    "ivrig": Temperament("ivrig", close_add=5.0, search_add=4.0, ping_mult=0.8,
                         timeout_mult=0.67, attack_sigma=0.5),
}


def draw_temperament(rng: random.Random) -> Temperament:
    """Ett temperament ur fartygets ström utan att dra ur den (egen ström ur dess tillstånd)."""
    own = random.Random(repr(rng.getstate()[1][:8]))
    return TEMPERAMENTS[own.choice(sorted(TEMPERAMENTS))]


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
    # fartygets förmåga; PatrolBoatAI (harbor.py) är mindre och svagare
    PING_LEVEL = acoustics.PING_LEVEL_SHIP
    SPEED_CLOSE = 22        # mot ett avlägset datum
    SPEED_SEARCH = 12       # söker kring datum
    SPEED_OPEN = 18         # efter fällningen
    SPEED_ATTACK = 15
    SPEED_EVADE = 30
    CHARGES = (3, 9)        # signal, skarpa
    PING_INTERVAL = PING_INTERVAL
    PATROL_MARGIN = 1.0     # så långt utanför patrullområdet innan den vänder
    MAST_NM = 4.0           # utkik och radar ser periskop och master så här långt
    MAST_P = 0.03           # sannolikhet per sekund att de upptäcks inom det

    DRAW_TEMPERAMENT = True     # hamnens patrullbåtar är alla lika (sundets kalibrering)
    # Ramning: med skarpa insatsregler och en färsk, skarp fix på en ubåt grunt nog att träffa (tornet på
    # periskopdjup, eller i ytläge) går jagaren rakt på den i full fart med förhåll i stället för att fälla.
    RAM_DEPTH_M = 25.0
    RAM_RANGE_NM = 2.5
    RAM_SIGMA_NM = 0.2
    RAM_FRESH_S = 20

    def __init__(self, vessel: Vessel, rng: random.Random, area: float = 20.0,
                 patrol_speed: float = 15.0, escalate_after: int | None = None,
                 leash_nm: float | None = None,
                 box: tuple[float, float, float, float] | None = None,
                 temperament: Temperament | None = None):
        self.vessel = vessel
        self.rng = rng
        self.temper = temperament or (draw_temperament(rng) if self.DRAW_TEMPERAMENT
                                      else TEMPERAMENTS["metodisk"])
        self.quiet_patrol = False   # lyssnar bara i patrull (fred, Clyde): pingar först när den söker
        self.area = area
        # patrullområdet (x0, y0, x1, y1); kvadraten om inget annat sägs
        self.box = box if box is not None else (0.0, 0.0, area, area)
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
        self.shadow: Vessel | None = None        # spaningstrålaren den skuggar en stund i taget (fishing.py)

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
        return acoustics.transmission_loss(distance(s.x, s.y, x, y), 5.0, depth, world.env) \
            + world.land_loss(s.x, s.y, x, y)

    # ------------------------------------------------------------------ datum
    def _set_datum(self, world: World, x: float, y: float, depth: float, sigma: float,
                   fix: bool = False) -> None:
        now = world.time
        if self._outside_leash(x, y):
            return                  # utanför vår sektor: följ inte efter
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
        if self.vessel.sunk or self._outside_leash(d.x, d.y):
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
            if tr.kind in ("ping", "launch", "echosounder", "astern", "reload", "creak", "clatter", "repair",
                           "collision"):
                self._datum_from_bearing(world, tr.x, tr.y, 0.25 if tr.kind == "ping" else 0.3,
                                         depth_guess=max(20.0, tr.depth + self.rng.gauss(0, 40)))

    def glitter_factor(self, world: World) -> float:
        """Utkiken ser plymen efter periskopet lättare i månglittret: på natten, när månen
        lyser nog och vi ligger åt månens håll sett från fartyget. Annars 1 (radarn)."""
        lt = world.env.light(world.time)
        if lt.daylight or lt.moon_light < MOON_SIL_LIGHT:
            return 1.0
        s, o = self.vessel.state, world.own.state
        b = bearing_to(s.x, s.y, o.x, o.y)
        return MOON_GLITTER_F if abs(angle_diff(b, lt.moon_az)) <= MOON_SIL_DEG else 1.0

    def _masts(self, world: World) -> None:
        own = world.own
        if own.sunk:
            return
        r = distance(self.vessel.state.x, self.vessel.state.y, own.state.x, own.state.y)
        sea = world.env.sea_state
        if own.surfaced or own.broached(world.time):     # i ytläge, eller tornet bröt ytan
            det_r = (6.0 + 4.0 * world.env.light(world.time).level) * radar_clutter_f(sea, True)
            p = 0.2                                     # dag 10, natt 6 nm i lugn sjö
        elif own.masts_up(world.time):
            det_r, p = self.MAST_NM * radar_clutter_f(sea), self.MAST_P * self.glitter_factor(world)
            if world.env.raining():
                det_r *= RAIN_RADAR_F           # regnklotter på radarn
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
                # pejlnätet: en kort sändning hinner de inte pejla, en lång pejlas skarpare
                if self.rng.random() >= df_probability(em.duration):
                    continue
                sigma = df_sigma(em.duration)
                self._set_datum(world, em.x + self.rng.gauss(0, sigma),
                                em.y + self.rng.gauss(0, sigma), 15.0, sigma + 0.5)

    def _threats(self, world: World, noise: float) -> None:
        s = self.vessel.state
        for t in world.contacts:
            if not isinstance(t, Torpedo) or t.done or t.side != "own":
                continue
            se = t.radiated_level(world.env) - self._tl(world, t.state.x, t.state.y,
                                                        t.depth) - noise - DT_PASSIVE
            if se <= 0:
                continue
            self.roe = "lethal"
            self.evade_until = world.time + 180
            s.order_course(bearing_to(t.state.x, t.state.y, s.x, s.y))
            s.order_speed(self.SPEED_EVADE)
            if t.id not in self.seen_torpedoes:
                self.seen_torpedoes.add(t.id)
                lx, ly = t.launch_xy
                self._set_datum(world, lx + self.rng.gauss(0, 0.7), ly + self.rng.gauss(0, 0.7),
                                100.0, 1.0)

    def _ping(self, world: World, noise: float) -> None:
        s = self.vessel.state
        now = world.time
        world.emit(Transient("ping", s.x, s.y, 5.0, self.PING_LEVEL, self.vessel.id, now))
        self.next_ping = now + round(self.PING_INTERVAL[self.state] * self.temper.ping_mult) \
            + self.rng.randint(0, 3)
        echoes = []
        for tgt in [world.own, *[d for d in world.contacts if isinstance(d, Decoy)]]:
            if tgt.sunk or self._in_dead_zone(tgt):
                continue
            tl = self._tl(world, tgt.state.x, tgt.state.y, tgt.depth)
            se = acoustics.active_excess(self.PING_LEVEL, tl, tgt.target_strength,
                                         self._noise_toward(world, noise, tgt), DT_ACTIVE) \
                - self._wake_clutter(world, tgt) - bottom_clutter(world, tgt) \
                - shallow_reverb(world, tgt.state.x, tgt.state.y) \
                - sea_ping_loss_db(world.env.sea_state) \
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

    def _outside_leash(self, px: float, py: float) -> bool:
        if self.leash_nm is None:
            return False
        m = self.leash_nm
        x0, y0, x1, y1 = self.box
        return not (x0 - m <= px <= x1 + m and y0 - m <= py <= y1 + m)

    def _beyond_leash(self, now: int) -> bool:
        if self.datum is None:
            return False
        return self._outside_leash(*self.datum.predict(now))

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
        if world.time >= self.next_ping and not (self.quiet_patrol and self.state == "patrol"):
            self._ping(world, noise)
        self._decide(world)

    def ramming(self, now: int) -> bool:
        return now - getattr(self, "ram_t", -10**9) <= 1

    def _ram(self, world: World) -> bool:
        """Rakt på ubåten i full fart, med förhåll (datumets fart), när den ligger grunt och vi ser den."""
        now, s, d = world.time, self.vessel.state, self.datum
        if self.roe != "lethal" or d is None or now - self.last_contact_t > self.RAM_FRESH_S or \
                d.sigma > self.RAM_SIGMA_NM or d.depth > self.RAM_DEPTH_M:
            return False
        px, py = d.predict(now)
        r = distance(s.x, s.y, px, py)
        if r > self.RAM_RANGE_NM:
            return False
        lead_s = r / max(self.SPEED_EVADE, 1.0) * 3600.0
        ax, ay = d.predict(now + int(lead_s))
        s.order_speed(self.SPEED_EVADE)
        s.order_course(bearing_to(s.x, s.y, ax, ay))
        self.ram_t = now
        return True

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
        if self.datum is not None and now - self.datum.t > DATUM_TIMEOUT * self.temper.timeout_mult:
            self.datum = None
            self.state = "patrol"

        fresh = now - self.last_contact_t <= 40
        if self.state == "patrol" and self.datum is not None:
            self.state = "prosecute"

        if self.state == "prosecute":
            if fresh and self.datum.sigma < self.temper.attack_sigma:
                self.state = "attack"
            else:
                px, py = self.datum.predict(now)
                d = distance(s.x, s.y, px, py)
                if d > 1.0:
                    s.order_speed(self.SPEED_CLOSE + self.temper.close_add)
                    s.order_course(bearing_to(s.x, s.y, px, py))
                else:
                    s.order_speed(self.SPEED_SEARCH + self.temper.search_add)
                    if now >= self.next_search_turn:
                        self.next_search_turn = now + self.temper.turn_s
                        s.order_course(norm360(s.course + 90))
                return

        if self.state == "attack":
            if now < self.opening_until:
                s.order_speed(self.SPEED_OPEN)
                return
            if self._ram(world):
                return
            if now - self.last_contact_t > 90:
                self.state = "prosecute"
                return
            px, py = self.datum.predict(now)
            s.order_speed(self.SPEED_ATTACK)
            s.order_course(bearing_to(s.x, s.y, px, py))
            if self.roe == "signal" and now >= self.next_uwt:
                self.next_uwt = now + UWT_INTERVAL
                world.emit(Transient("uwt", s.x, s.y, 5.0, acoustics.UWT_LEVEL, self.vessel.id, now))
            if distance(s.x, s.y, px, py) < 0.12 and now >= self.attack_ready_t:
                practice = self.roe == "signal"
                drop_charges(world, self.vessel, px, py, self.datum.depth,
                             n=self.CHARGES[0] if practice else self.CHARGES[1],
                             practice=practice)
                self.attacks += 1
                if practice and self.escalate_after is not None \
                        and self.attacks >= self.escalate_after:
                    self.roe = "lethal"
                self.attack_ready_t = now + ATTACK_COOLDOWN
                self.opening_until = now + 90
            return

        # patrull (en stund i taget: skugga den sovjetiska spaningstrålaren, fishing.py)
        sh = self.shadow
        if sh is not None and not sh.sunk and now % SHADOW_PERIOD_S >= SHADOW_PERIOD_S - SHADOW_ON_S:
            r = distance(s.x, s.y, sh.state.x, sh.state.y)
            if r > SHADOW_NM:
                s.order_speed(self.patrol_speed)
                s.order_course(bearing_to(s.x, s.y, sh.state.x, sh.state.y))
            else:
                s.order_speed(max(3.0, sh.state.speed))
                s.order_course(sh.state.course)
            return
        s.order_speed(self.patrol_speed)
        m = self.PATROL_MARGIN
        x0, y0, x1, y1 = self.box
        if not (x0 - m <= s.x <= x1 + m and y0 - m <= s.y <= y1 + m):
            if "course" not in s.changing():
                c = bearing_to(s.x, s.y, (x0 + x1) / 2, (y0 + y1) / 2)
                s.order_course(norm360(c + self.rng.uniform(-40, 40)))
