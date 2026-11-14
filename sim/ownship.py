"""Egen ubåt (Projekt 627A-liknande) med delsystem.

Allt här är sanning: fysik och teknik. Besättningen läser systemen via
instrument (stationerna) och rapporterar via alerts-kön, som
maskinstationen tömmer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import acoustics
from .entities import Vessel

if TYPE_CHECKING:
    from .world import World

TEST_DEPTH = 300.0
CRUSH_DEPTH = 450.0
PERISCOPE_DEPTH = 18.0
ANTENNA_DEPTH = 30.0
FIRE_SMOKE_PER_S = 0.0009     # rök medan det brinner
SMOLDER_PER_H = 0.2           # glödbränder efter släckning, tills vi ventilerar
VENT_PD_PER_MIN = 0.02        # ventilation genom masten på periskopdjup
VENT_SURFACE_PER_MIN = 0.05   # med luckorna öppna i ytläge
SMOKE_LEVELS = (0.3, 0.5, 0.7, 0.85)
TRIM_RESERVE_T = 25.0         # ton vatten trimsystemet kan kompensera
FLOOD_LOSS_T = 120.0          # ton vatten ombord = förlorad
SCRAM_RATE_PER_H = 0.01       # spontana snabbstopp
STEAM_LEAK_RATE_PER_H = 0.005
REACTOR_START_S = 1200
REPAIR_S = 1200               # tid att reparera en komponent helt
COMPONENTS = ("sonar", "planes", "propulsion", "tubes", "periscope", "radio")
COMPONENT_LABEL = {
    "sonar": "sonaren", "planes": "rodren", "propulsion": "framdrivningen",
    "tubes": "torpedtuberna", "periscope": "periskopet", "radio": "radion",
}


@dataclass
class OwnSystems:
    reactor: str = "online"          # online, scram, off, starting
    reactor_ready_t: int = 0
    steam_leak: bool = False
    steam_leak_fixed_t: int = 0
    propulsion: str = "turbine"      # turbine, electric
    battery: float = 1.0
    co2: float = 0.3                 # procent
    hull: float = 1.0
    flooding: float = 0.0            # ton vatten ombord
    leak_rate: float = 0.0           # ton/min
    health: dict[str, float] = field(default_factory=lambda: {c: 1.0 for c in COMPONENTS})
    blowing: bool = False
    ice_contact: bool = False        # ubåten ligger an mot isen ovanför
    bottom_contact: bool = False     # kölen tar i botten
    settle: bool = False             # order: lägg oss på botten
    on_bottom: bool = False          # ligger stilla på botten
    fire: bool = False               # brand ombord
    fire_out_t: int = 0
    fire_done: bool = False
    smoke: float = 0.0               # 0 = ren luft, 1 = besättningen kvävs
    ventilating: bool = False
    _smoke_warned: set = field(default_factory=set)
    ice_press: int = 0               # sekunder ubåten tryckt mot tunn is
    hp_air: float = 1.0
    periscope_until: int = -1
    radar_until: int = -1
    transmit_until: int = -1
    alerts: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    _battery_warned: set = field(default_factory=set)
    _last_creak: int = -10**9


class OwnShip(Vessel):
    def __init__(self, state, id: str = "OWN"):
        super().__init__(id=id, kind="submarine", state=state, side="own")
        self.sys = OwnSystems()

    # ------------------------------------------------------------------ hjälp
    def alert(self, type: str, **data: Any) -> None:
        self.sys.alerts.append((type, data))

    @property
    def power(self) -> bool:
        return self.sys.reactor == "online"

    def max_speed(self) -> float:
        s = self.sys
        if s.propulsion == "electric" or not self.power:
            if not self.power and s.battery <= 0:
                return 0.0
            return 5.0 * max(s.health["propulsion"], 0.3)
        v = 28.0 * max(s.health["propulsion"], 0.3)
        return min(v, 16.0) if s.steam_leak else v

    def masts_up(self, now: int) -> bool:
        s = self.sys
        return self.state.depth <= PERISCOPE_DEPTH and (
            s.periscope_until > now or s.radar_until > now or s.transmit_until > now)

    @property
    def surfaced(self) -> bool:
        return self.state.depth <= 1.0

    # ------------------------------------------------------------------ akustik
    def radiated_level(self, env) -> float:
        if self.sunk:
            return -999.0
        s, speed = self.sys, self.state.speed
        if s.on_bottom:
            # maskinen stoppad, kylpumparna på lågvarv (självcirkulation)
            parts = [100.0, 112.0 if s.reactor in ("online", "starting") else 0.0]
        else:
            parts = [128.0 if s.propulsion == "turbine" and self.power else 112.0]
            if s.reactor in ("online", "starting"):
                parts.append(120.0)           # reaktorns kylpumpar går alltid
        lvl = acoustics.power_sum(*parts) + 1.2 * speed
        if speed > acoustics.cavitation_speed(self.state.depth):
            lvl += 12.0
        if s.flooding > 0 or s.hull < 0.7:
            lvl += 2.0                        # skrammel från skador
        if s.blowing:
            lvl = acoustics.power_sum(lvl, acoustics.BLOW_LEVEL)
        return lvl

    def self_noise(self) -> float:
        s, speed = self.sys, self.state.speed
        parts = [acoustics.own_noise(speed), 58.0 if s.propulsion == "turbine" and self.power else 46.0]
        if s.reactor in ("online", "starting"):
            parts.append(50.0)
        return acoustics.power_sum(*parts)

    # ------------------------------------------------------------------ order
    def set_propulsion(self, mode: str) -> bool:
        if mode == "turbine" and (not self.power or self.sys.fire):
            return False
        self.sys.propulsion = mode
        return True

    def scram(self, cause: str) -> None:
        if self.sys.reactor not in ("online", "starting"):
            return
        self.sys.reactor = "scram"
        self.sys.propulsion = "electric"
        self.alert("reactor.scram", cause=cause)

    def shutdown_reactor(self) -> None:
        self.sys.reactor = "off"
        self.sys.propulsion = "electric"

    def start_reactor(self, now: int) -> bool:
        if self.sys.reactor in ("online", "starting"):
            return False
        self.sys.reactor = "starting"
        self.sys.reactor_ready_t = now + REACTOR_START_S
        return True

    def start_ventilation(self, open_air: bool) -> bool:
        if not open_air or self.state.depth > PERISCOPE_DEPTH:
            return False
        self.sys.ventilating = True
        return True

    def emergency_blow(self) -> bool:
        if self.sys.hp_air <= 0 or self.sys.blowing:
            return False
        self.sys.blowing = True
        self.sys.hp_air = 0.0
        return True

    # ------------------------------------------------------------------ skador
    def apply_explosion(self, dist_m: float, practice: bool, rng) -> None:
        s = self.sys
        if practice:
            if dist_m < 400:
                self.alert("shock", strength="lätt" if dist_m > 100 else "kraftig", practice=True)
            return
        if dist_m < 25:
            s.hull -= 0.35
            s.leak_rate += 2.0
            hit = rng.sample(COMPONENTS, 2)
            for c in hit:
                s.health[c] = max(0.0, s.health[c] - 0.7)
            self.alert("damage", severity="svåra", components=hit, leak=True)
            if rng.random() < 0.8:
                self.scram("tryckvåg")
        elif dist_m < 60:
            s.hull -= 0.08
            hit = [rng.choice(COMPONENTS)]
            s.health[hit[0]] = max(0.0, s.health[hit[0]] - 0.4)
            leak = rng.random() < 0.5
            if leak:
                s.leak_rate += 0.5
            self.alert("damage", severity="lätta", components=hit, leak=leak)
            if rng.random() < 0.3:
                self.scram("tryckvåg")
        elif dist_m < 150:
            self.alert("shock", strength="kraftig", practice=False)
            if rng.random() < 0.05:
                self.scram("tryckvåg")
        elif dist_m < 600:
            self.alert("shock", strength="lätt", practice=False)

    # ------------------------------------------------------------------ fysik
    def update(self, world: World, dt: int = 1) -> None:
        if self.sunk:
            return
        s, st, now, rng = self.sys, self.state, world.time, world.rng

        # reaktor
        if s.reactor == "starting" and now >= s.reactor_ready_t:
            s.reactor = "online"
            self.alert("reactor.online")
        if s.reactor == "online" and rng.random() < SCRAM_RATE_PER_H / 3600 * dt:
            self.scram("spontant")
        if s.reactor == "online" and not s.steam_leak and rng.random() < STEAM_LEAK_RATE_PER_H / 3600 * dt:
            s.steam_leak = True
            s.steam_leak_fixed_t = now + 1800
            self.alert("reactor.leak")
        if s.steam_leak and now >= s.steam_leak_fixed_t:
            s.steam_leak = False
            self.alert("reactor.leak_fixed")

        # batteri
        if self.power:
            s.battery = min(1.0, s.battery + 0.2 / 3600 * dt)
            s._battery_warned.clear()
        else:
            drain = (0.05 + 0.012 * st.speed ** 2) / 3600 * dt
            s.battery = max(0.0, s.battery - drain)
            for level in (0.3, 0.1, 0.0):
                if s.battery <= level and level not in s._battery_warned:
                    s._battery_warned.add(level)
                    self.alert("battery", level=level)

        # brand och rök
        fire_at = world.mission.get("fire_at")
        if fire_at is not None and now >= fire_at and not s.fire and not s.fire_done:
            s.fire = True
            s.fire_out_t = now + rng.randint(420, 780)
            s.propulsion = "electric"         # turbinrummet utrymt
            self.alert("fire", compartment="turbinrummet")
        if s.fire:
            s.smoke = min(1.0, s.smoke + FIRE_SMOKE_PER_S * dt)
            s.propulsion = "electric"
            if now >= s.fire_out_t:
                s.fire, s.fire_done = False, True
                self.alert("fire.out")
        elif s.fire_done and s.smoke > 0 and not s.ventilating:
            s.smoke = min(1.0, s.smoke + SMOLDER_PER_H / 3600 * dt)
        if s.ventilating:
            from .ice import masts_clear
            if st.depth > PERISCOPE_DEPTH + 1 or not masts_clear(world):
                s.ventilating = False
                self.alert("vent.stopped", smoke=s.smoke)
            else:
                rate = VENT_SURFACE_PER_MIN if self.surfaced else VENT_PD_PER_MIN
                s.smoke = max(0.0, s.smoke - rate / 60 * dt)
                if s.smoke == 0.0:
                    s.ventilating = False
                    self.alert("vent.done")
        for level in SMOKE_LEVELS:
            if s.smoke >= level and level not in s._smoke_warned:
                s._smoke_warned.add(level)
                self.alert("smoke", level=level)
            elif s.smoke < level - 0.1:
                s._smoke_warned.discard(level)

        # fart begränsas av framdrivningen
        st.max_speed = self.max_speed()
        if st.ordered_speed > st.max_speed:
            st.ordered_speed = st.max_speed

        # luft
        regen = self.power or s.battery > 0.02
        if regen:
            s.co2 = max(0.3, s.co2 - 0.5 / 3600 * dt)
        else:
            s.co2 += 0.6 / 3600 * dt
            if s.co2 > 1.5 and int(s.co2 * 10) != int((s.co2 - 0.6 / 3600 * dt) * 10):
                self.alert("air", co2=s.co2)

        # djupstyrning: rodren behöver fart, barlasten verkar långsamt
        st.depth_rate = min(2.0, max(0.2, (0.25 + 0.12 * st.speed) * max(s.health["planes"], 0.2)))
        if s.blowing:
            st.ordered_depth = 0.0
            st.depth = max(0.0, st.depth - 3.0 * dt)
            if st.depth <= 0.0:
                s.blowing = False
                self.alert("surfaced")

        # vatteninträngning
        pumps = 0.5 if regen else 0.0
        s.flooding = max(0.0, s.flooding + (s.leak_rate - pumps) * dt / 60.0)
        if s.leak_rate > 0:
            before = s.leak_rate
            s.leak_rate = max(0.0, s.leak_rate - s.leak_rate * 0.002 * dt - 0.0005 * dt)
            if before > 0 and s.leak_rate == 0:
                self.alert("leak_stopped")
        excess = s.flooding - TRIM_RESERVE_T
        if excess > 0 and not s.blowing:
            st.depth += excess * 0.03 * dt
            st.ordered_depth = max(st.ordered_depth, st.depth)

        # skrov
        if st.depth > TEST_DEPTH:
            s.hull -= (st.depth - TEST_DEPTH) / 100.0 * 0.0015 * dt
            if now - s._last_creak >= 60:
                s._last_creak = now
                self.alert("hull.creak", depth=st.depth)
            if s.hull < 0.6 and rng.random() < 0.01 * dt:
                s.leak_rate += 0.3
                self.alert("damage", severity="lätta", components=[], leak=True)

        # reparationer: en komponent i taget
        for c in COMPONENTS:
            if s.health[c] < 1.0:
                s.health[c] = min(1.0, s.health[c] + dt / REPAIR_S)
                if s.health[c] >= 1.0:
                    self.alert("repaired", component=c)
                break

        if st.depth >= CRUSH_DEPTH or s.hull <= 0 or s.flooding >= FLOOD_LOSS_T:
            self.sunk = True
            cause = ("krossad på djupet" if st.depth >= CRUSH_DEPTH
                     else "skrovet brast" if s.hull <= 0 else "vattenfylld")
            world.end("lost", cause=cause)
        elif s.smoke >= 1.0:
            world.end("lost", cause="besättningen kvävd av röken")
