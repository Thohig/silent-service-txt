"""Egen ubåt (Projekt 627A-liknande) med delsystem.

Allt här är sanning: fysik och teknik. Besättningen läser systemen via
instrument (stationerna) och rapporterar via alerts-kön, som
maskinstationen tömmer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import acoustics, damage, trim
from .damage import DamageState
from .entities import Transient, Vessel
from .periscope import wave_height_m, wave_period_s
from .trim import TrimState

if TYPE_CHECKING:
    from .world import World

BAFFLE_DEG = 30.0     # sonarns döda sektor akterut, halva bredden (skrovet och skruven)

TEST_DEPTH = 300.0
GROAN_MIN_DEPTH = 80.0     # skrovknak vid snabb djupändring: bara så här djupt
GROAN_RATE_MPS = 1.0       # ... och fortare än så (≈ 6 kn och uppåt med rodren)
GROAN_STEP_M = 25.0        # ett knak per så många meter
# Stampvinkeln (docs/system/besattning.md, Lutningen): båten lutar när rodren byter djup.
BALLAST_MPS = 0.25         # den del av djupändringen barlasten gör (ingen lutning)
PITCH_DYN_MAX_DEG = 30.0   # största lutning av djupbytet
PITCH_SLEW_DEG_S = 3.0     # så fort båten ändrar lutning
BLOW_PITCH_DEG = -20.0     # nödblåsning: fören upp
STEEP_RATE_F = 1.4         # brant dykning (navigatören väljer den när det brådskar): fortare djupbyte
STEEP_MAX_MPS = 2.8        # ... upp till så här
CLATTER_DEG = 15.0         # brantare än så: lösa föremål far i durken och det hörs i vattnet
CLATTER_REARM_DEG = 5.0    # ... igen först när båten varit nästan rak
CRUSH_DEPTH = 450.0
PERISCOPE_DEPTH = 18.0
ANTENNA_DEPTH = 30.0
FIRE_SMOKE_PER_S = 0.0009     # rök medan det brinner
SMOLDER_PER_H = 0.2           # glödbränder efter släckning, tills vi ventilerar
VENT_PD_PER_MIN = 0.02        # ventilation genom masten på periskopdjup
VENT_SURFACE_PER_MIN = 0.05   # med luckorna öppna i ytläge
SMOKE_LEVELS = (0.3, 0.5, 0.7, 0.85)
TRIM_RESERVE_T = -trim.BALLAST_MIN_T   # ton vatten utjämningstanken kan kompensera
FLOOD_LOSS_T = 120.0          # ton vatten ombord = förlorad
SCRAM_RATE_PER_H = 0.01       # spontana snabbstopp
STEAM_LEAK_RATE_PER_H = 0.005
REACTOR_START_S = 1200
ASTERN_TURBINE_KN = 8.0       # högsta backfart på turbinen
ASTERN_ELECTRIC_KN = 3.0      # och på smygmotorn
BRAKE_KN_PER_S = 0.15         # inbromsning när maskinen går mot farten (stopp: 0,05)
ASTERN_TURN = 1 / 3           # rodret tar dåligt när båten går akterut
ASTERN_PLANES = 0.3           # djuprodrens bärförmåga akterut, andel
REPAIR_S = 1200               # tid att reparera en komponent helt
SEVERE_CAP = 0.75             # svår skada: det närmaste går inte att laga bättre än så till sjöss
PROP_RATTLE_HEALTH = 0.7      # framdrivningen så skadad: axeln slår och båten hörs mer
PROP_RATTLE_DB = 3.0
BRIDGE_MAN_S = 20             # luckan öppen och utkikarna uppe så här länge efter att vi kommit upp
BRIDGE_CLEAR_S = 20           # bryggan utryms och luckan stängs innan vi kan dyka
# Sjön suger (V3): nära ytan drar vågornas tryck båten uppåt i takt med sjön. Utslaget växer
# med våghöjden, minskar med farten (rodren tar) och med djupet. Når tornets topp ytan
# (kölen grundare än BROACH_DEPTH_M) bryter tornet ytan och syns en stund.
HEAVE_FROM_B = 4              # från denna Beaufort
HEAVE_K = 2.4                 # utslag (m) per meter våghöjd i låg fart på periskopdjup
HEAVE_SPEED_FROM_KN = 2.0     # över denna fart tar rodren …
HEAVE_SPEED_PER_KN = 0.12     # … så här mycket per knop
HEAVE_SPEED_MIN_F = 0.3
HEAVE_DECAY_M = 10.0          # under periskopdjup avtar suget med e-faldning per så många meter
BROACH_DEPTH_M = 13.0         # kölen så grunt: tornets topp i ytan
BROACH_S = 15                 # tornet syns så länge efter att det brutit ytan
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
    bottom_touch_t: int = 0          # senaste rapporten om kontakten
    # senaste tvärstopp (t, akterut, vad): "ice" (isvägg), "bottom" (grundstötning), "pressed" (står fast)
    hull_stop: tuple[int, bool, str] | None = None
    settle: bool = False             # order: lägg oss på botten
    on_bottom: bool = False          # ligger stilla på botten
    fire: bool = False               # brand ombord
    fire_room: int = 6               # var det brinner: 6 turbinrummet, 2 batterirummet (kortslutning)
    fire_out_t: int = 0
    fire_done: bool = False
    smoke: float = 0.0               # 0 = ren luft, 1 = besättningen kvävs
    ventilating: bool = False
    _smoke_warned: set = field(default_factory=set)
    ice_press: int = 0               # sekunder ubåten tryckt mot tunn is
    hp_air: float = 1.0
    # tornluckan och bryggan: shut, manning (luckan öppnas), manned, clearing (utryms)
    bridge: str = "shut"
    bridge_t: int = 0                # när pågående öppning eller utrymning är klar
    periscope_until: int = -1
    broach_until: int = -1           # tornet bröt ytan och syns till dess
    radar_until: int = -1
    transmit_until: int = -1
    trim: TrimState = field(default_factory=TrimState)
    dmg: DamageState = field(default_factory=DamageState)   # läckorna, vattnet i avdelningarna (damage.py)
    alerts: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    _battery_warned: set = field(default_factory=set)
    _last_creak: int = -10**9
    _groan_ref: float | None = None  # djupet vid förra knaket (kompressionen) under snabb djupändring
    steep: bool = False              # brant dykning: navigatören väljer den när det brådskar
    pitch_dyn: float = 0.0           # lutningen av djupbytet, grader (+ förlig, fören ned)
    _clatter_armed: bool = True      # lösa föremål kan slamra igen (båten har varit rak)


def heave_speed_f(speed: float) -> float:
    """Hur mycket av sjöns sug som når båten i denna fart (rodren tar emot)."""
    return min(1.0, max(HEAVE_SPEED_MIN_F,
                        1.0 - (abs(speed) - HEAVE_SPEED_FROM_KN) * HEAVE_SPEED_PER_KN))


def heave_depth_f(depth: float) -> float:
    """Hur mycket av sjöns sug som når ned till detta djup."""
    return 1.0 if depth <= PERISCOPE_DEPTH else math.exp(-(depth - PERISCOPE_DEPTH) / HEAVE_DECAY_M)


class OwnShip(Vessel):
    def __init__(self, state, id: str = "OWN"):
        super().__init__(id=id, kind="submarine", state=state, side="own")
        self.sys = OwnSystems()
        state.brake_accel = BRAKE_KN_PER_S
        state.astern_turn = ASTERN_TURN
        self._reversing = False          # maskinen slog mot farten förra sekunden
        self._prev_depth: float | None = None   # djupet förra sekunden (skrovknaket)
        self.heave_amp_m = 0.0           # sjöns sug: utslaget just nu (djupmätaren visar det)
        self.heave_m = 0.0               # och hur högt sjön drar oss denna sekund
        # sonarns döda sektor akterut, halva bredden i grader (0 = ingen; se sim/sonar.py `baffle_loss`)
        self.baffle_deg = BAFFLE_DEG
        if state.depth <= 1.0:
            self.sys.bridge = "manned"       # börjar i ytläge med folk på bryggan

    # ------------------------------------------------------------------ hjälp
    @property
    def pitch(self) -> float:
        """Lutningen (дифферент) som lutningsmätaren visar: trimmen och djupbytet, + förlig."""
        return max(-35.0, min(35.0, self.sys.trim.pitch + self.sys.pitch_dyn))

    def _pitch_step(self, world, st, s, now: int, dt: float) -> None:
        """Lutningen av djupbytet: vinkeln mellan farten framåt och den del av djupändringen rodren
        gör (barlasten lutar inte båten); vid nödblåsning fören brant upp. Över CLATTER_DEG far lösa
        föremål i durken: maskin säger det och det hörs i vattnet (en gång per brant läge)."""
        vz = (st.depth - self._prev_depth) / dt if self._prev_depth is not None and dt > 0 else 0.0
        if s.blowing:
            target = BLOW_PITCH_DEG
        elif st.speed < 2.0 or self.surfaced or s.on_bottom:
            target = 0.0
        else:
            planes_vz = math.copysign(max(0.0, abs(vz) - BALLAST_MPS), vz)
            target = math.degrees(math.atan2(planes_vz, st.speed * 0.5144))
            target = max(-PITCH_DYN_MAX_DEG, min(PITCH_DYN_MAX_DEG, target))
        step = PITCH_SLEW_DEG_S * dt
        s.pitch_dyn += max(-step, min(step, target - s.pitch_dyn))
        p = abs(self.pitch)
        if p > CLATTER_DEG and s._clatter_armed:
            s._clatter_armed = False
            world.emit(Transient("clatter", st.x, st.y, st.depth, acoustics.CLATTER_LEVEL, self.id, now))
            self.alert("hull.clatter", pitch=round(self.pitch),
                       steep=s.steep and st.ordered_depth > st.depth, trim=round(s.trim.pitch, 1))
        elif p < CLATTER_REARM_DEG:
            s._clatter_armed = True

    def _groan_step(self, world, st, s, now: int, dt: float) -> None:
        """Skrovet knakar var GROAN_STEP_M under en djupändring fortare än GROAN_RATE_MPS
        nedanför GROAN_MIN_DEPTH (stålet trycks ihop eller släpper). Långsamt knakar det inte."""
        rate = abs(st.depth - self._prev_depth) / dt if self._prev_depth is not None and dt > 0 else 0.0
        self._prev_depth = st.depth
        if st.depth < GROAN_MIN_DEPTH or rate < GROAN_RATE_MPS:
            s._groan_ref = st.depth
            return
        if s._groan_ref is None:
            s._groan_ref = st.depth
        if abs(st.depth - s._groan_ref) >= GROAN_STEP_M:
            down = st.depth > s._groan_ref
            s._groan_ref = st.depth
            world.emit(Transient("creak", st.x, st.y, st.depth, acoustics.CREAK_LEVEL, self.id, now))
            self.alert("hull.groan", depth=st.depth, down=down)

    def alert(self, type: str, **data: Any) -> None:
        self.sys.alerts.append((type, data))

    @property
    def turbine_fire(self) -> bool:
        """Det brinner i turbinrummet: turbinen kan inte köras."""
        return self.sys.fire and self.sys.fire_room == 6

    @property
    def power(self) -> bool:
        return self.sys.reactor == "online"

    def max_speed(self) -> float:
        s = self.sys
        if s.propulsion == "electric" or not self.power:
            if not self.power and s.battery <= 0:
                return 0.0
            return 5.0 * max(s.health["propulsion"], 0.3)
        return self.turbine_max_speed()

    def turbine_max_speed(self) -> float:
        """Högsta fart på turbinen med de skador vi har (också när vi går på elmotorn nu)."""
        s = self.sys
        v = 28.0 * max(s.health["propulsion"], 0.3)
        return min(v, 16.0) if s.steam_leak else v

    def max_astern_speed(self) -> float:
        """Högsta fart akterut: propellern ger mindre bakåt, en tredjedel ungefär."""
        ahead = self.max_speed()
        if ahead <= 0:
            return 0.0
        s = self.sys
        if s.propulsion == "electric" or not self.power:
            return ASTERN_ELECTRIC_KN * max(s.health["propulsion"], 0.3)
        return min(ahead, ASTERN_TURBINE_KN * max(s.health["propulsion"], 0.3))

    def masts_up(self, now: int) -> bool:
        s = self.sys
        return self.state.depth <= PERISCOPE_DEPTH and (
            s.periscope_until > now or s.radar_until > now or s.transmit_until > now)

    @property
    def surfaced(self) -> bool:
        return self.state.depth <= 1.0

    def broached(self, now: int) -> bool:
        """Tornet bröt nyss ytan (sjön drog upp oss): syns som en ubåt i ytläge."""
        return self.sys.broach_until > now and not self.surfaced

    # ------------------------------------------------------------------ sjön suger
    def heave_amplitude(self, sea_state: int) -> float:
        """Hur mycket sjön drar båten mot ytan (m), ur sjögången, farten och djupet."""
        st, s = self.state, self.sys
        if sea_state < HEAVE_FROM_B or self.surfaced or self.bridge_open or s.on_bottom:
            return 0.0
        speed_f = heave_speed_f(st.speed)
        return HEAVE_K * wave_height_m(sea_state) * speed_f * heave_depth_f(st.depth)

    def _heave_step(self, world: World) -> None:
        now, sea = world.time, world.env.sea_state
        self.heave_amp_m = amp = self.heave_amplitude(sea)
        self.heave_m = amp * max(0.0, math.sin(2 * math.pi * now / wave_period_s(sea)))
        if amp > 0 and self.state.depth - self.heave_m < BROACH_DEPTH_M:
            if self.sys.broach_until <= now:
                self.alert("broach")
            self.sys.broach_until = now + BROACH_S

    @property
    def bridge_open(self) -> bool:
        """Luckan är öppen (bryggan bemannad eller under utrymning): vi kan inte dyka."""
        return self.sys.bridge in ("manned", "clearing")

    def _bridge_step(self, now: int) -> None:
        """Luckan öppnas när vi ligger i ytläge och ingen order att dyka finns;
        en order att dyka utrymmer först bryggan."""
        s, want_down = self.sys, self.state.ordered_depth > 1.0
        if s.bridge == "shut":
            if self.surfaced and not want_down and not s.blowing:
                s.bridge, s.bridge_t = "manning", now + BRIDGE_MAN_S
        elif s.bridge == "manning":
            if want_down or not self.surfaced:
                s.bridge = "shut"            # luckan hann inte öppnas
            elif now >= s.bridge_t:
                s.bridge = "manned"
        elif s.bridge == "manned":
            if want_down:
                s.bridge, s.bridge_t = "clearing", now + BRIDGE_CLEAR_S
        elif s.bridge == "clearing" and now >= s.bridge_t:
            s.bridge = "shut"

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
        if speed > acoustics.cavitation_speed(self.state.depth, self.state.prop_astern):
            lvl += 12.0
        if s.flooding > 0 or s.hull < 0.7:
            lvl += 2.0                        # skrammel från skador
        if s.health["propulsion"] < PROP_RATTLE_HEALTH:
            lvl += PROP_RATTLE_DB             # axeln eller propellern skadad: den slår
        lvl += s.dmg.eroded_db                # propellern gröpt av kavitationen
        if s.blowing:
            lvl = acoustics.power_sum(lvl, acoustics.BLOW_LEVEL)
        if s.trim.pumping and (self.power or s.battery > 0.02):
            lvl = acoustics.power_sum(lvl, trim.PUMP_LEVEL)
        if damage.pumping(self):
            lvl = acoustics.power_sum(lvl, damage.BILGE_LEVEL)
        return lvl

    def self_noise(self) -> float:
        s, speed = self.sys, self.state.speed
        parts = [acoustics.own_noise(speed), 58.0 if s.propulsion == "turbine" and self.power else 46.0]
        if s.reactor in ("online", "starting"):
            parts.append(50.0)
        return acoustics.power_sum(*parts)

    # ------------------------------------------------------------------ order
    def set_propulsion(self, mode: str) -> bool:
        if mode == "turbine" and (not self.power or self.turbine_fire):
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
    def apply_explosion(self, dist_m: float, practice: bool, rng,
                        src: tuple[float, float] | None = None) -> None:
        """En detonation dist_m bort. src: var den small (x, y), som avgör var skadan sitter (fören,
        mitten, aktern; damage.py); utan läge mitt i båten."""
        s = self.sys
        if practice:
            if dist_m < 400:
                self.alert("shock", strength="lätt" if dist_m > 100 else "kraftig", practice=True)
            return
        frac = damage.frac_of(self, *src) if src is not None else 0.5
        where = damage.compartment_at(frac)
        if dist_m < 150:
            damage.shock(self, 1.0 if dist_m < 60 else 0.5)
        if dist_m < 25:
            s.hull -= 0.35
            hit = damage.nearest_components(frac, 2, rng, COMPONENTS)
            for i, c in enumerate(hit):
                s.health[c] = max(0.0, s.health[c] - 0.7)
                if i == 0:
                    damage.limit(self, c, SEVERE_CAP)   # det närmaste går inte att laga helt till sjöss
            damage.add_leak(self, where, "spricka" if rng.random() < 0.5 else "svetsfog")
            self.alert("damage", severity="svåra", components=hit, leak=True, cause="charge",
                       compartment=where)
            if "planes" in hit:
                damage.maybe_jam(self, rng)
            if rng.random() < 0.8:
                self.scram("tryckvåg")
        elif dist_m < 60:
            s.hull -= 0.08
            hit = damage.nearest_components(frac, 1, rng, COMPONENTS)
            s.health[hit[0]] = max(0.0, s.health[hit[0]] - 0.4)
            leak = rng.random() < 0.5
            if leak:
                damage.add_leak(self, where, "rör" if rng.random() < 0.5 else "packbox")
            self.alert("damage", severity="lätta", components=hit, leak=leak, cause="charge",
                       compartment=where)
            if "planes" in hit:
                damage.maybe_jam(self, rng)
            if rng.random() < 0.3:
                self.scram("tryckvåg")
        elif dist_m < 150:
            self.alert("shock", strength="kraftig", practice=False)
            if rng.random() < 0.05:
                self.scram("tryckvåg")
        elif dist_m < 600:
            self.alert("shock", strength="lätt", practice=False)

    def add_leak(self, compartment: int, kind: str, scale: float = 1.0) -> None:
        """En läcka i avdelningen (grundstötning, is; damage.py)."""
        damage.add_leak(self, compartment, kind, scale)

    def test_depth(self) -> float:
        """Provdjupet med skrovets skador: ett skadat skrov tål mindre (300 m helt, 250 vid 67 %)."""
        return TEST_DEPTH * min(1.0, 0.5 + 0.5 * self.sys.hull)

    # ------------------------------------------------------------------ trim
    def _trim_step(self, world: World, dt: int, power: bool) -> None:
        """Vikten mot djuprodrens förmåga: det rodren inte bär driver båten (se trim.py)."""
        s, st, t = self.sys, self.state, self.sys.trim
        if not t.started:
            t.start(st.depth, world.env)
        t.step_pumps(dt, power)
        t.follow_order(st.depth, st.ordered_depth)
        t.weigh(st.depth, world.env, s.flooding, damage.fore_load(s.dmg))
        cap = trim.plane_capacity(st.speed, s.health["planes"]) * (ASTERN_PLANES if st.astern else 1.0)
        w = t.weight_t
        t.plane_load = max(-1.0, min(1.0, w / cap)) if cap > 0 else (0.0 if w == 0 else
                                                                     (1.0 if w > 0 else -1.0))
        surfacing = trim.ballast_carries(st.depth, st.ordered_depth, st.speed, t.changing)
        if self.surfaced or s.blowing or s.on_bottom or self.bridge_open or surfacing:
            # flytkraften i ytläge, botten bär; på väg upp blåses huvudbarlasten
            t.free_t = 0.0
            return
        t.free_t = w - cap if w > cap else w + cap if w < -cap else 0.0
        if t.free_t == 0.0:
            return
        drift = max(-trim.DRIFT_MAX_M_PER_S, min(trim.DRIFT_MAX_M_PER_S,
                                                 t.free_t * trim.DRIFT_M_PER_S_PER_T))
        control = max(0.0, 1.0 - abs(t.free_t) / trim.CONTROL_LOST_T)
        hold = st.depth_rate * control         # vad djupstyrningen orkar per sekund
        if abs(drift) <= hold:
            st.depth_rate = hold - abs(drift)  # håller djupet; resten räcker till att byta
            return
        st.depth_rate = 0.0
        st.depth = max(0.0, st.depth + (drift - math.copysign(hold, drift)) * dt)
        if control == 0.0 and drift > 0:
            st.ordered_depth = max(st.ordered_depth, st.depth)

    # ------------------------------------------------------------------ fysik
    def update(self, world: World, dt: int = 1) -> None:
        if self.sunk:
            return
        s, st, now, rng = self.sys, self.state, world.time, world.rng

        # reaktor
        if s.reactor == "starting" and now >= s.reactor_ready_t:
            s.reactor = "online"
            self.alert("reactor.online")
        # snabbstopp och ångläcka: vanligare en tid efter tryckvågor och skador (damage.stress)
        if s.reactor == "online" and rng.random() < SCRAM_RATE_PER_H / 3600 * dt * \
                damage.stress_factor(s.dmg, damage.STRESS_SCRAM_F):
            self.scram("tryckvågorna" if s.dmg.stress >= 0.5 else "spontant")
        if s.reactor == "online" and not s.steam_leak and rng.random() < STEAM_LEAK_RATE_PER_H / 3600 * dt * \
                damage.stress_factor(s.dmg, damage.STRESS_LEAK_F):
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
            s.fire, s.fire_room = True, 6
            s.fire_out_t = now + rng.randint(420, 780)
            s.propulsion = "electric"         # turbinrummet utrymt
            self.alert("fire", compartment="turbinrummet", room=6)
        if not s.fire and not s.dmg.battery_shorted and s.dmg.water[2] > damage.BATTERY_SHORT_T:
            # saltvatten i batteriet: kortslutning och brand i andra avdelningen
            s.dmg.battery_shorted = True
            s.fire, s.fire_room = True, 2
            s.fire_out_t = now + rng.randint(420, 780)
            s.battery *= damage.BATTERY_SHORT_KEEP
            self.alert("fire", compartment="batterirummet", room=2)
        if s.fire:
            s.smoke = min(1.0, s.smoke + FIRE_SMOKE_PER_S * dt)
            if s.fire_room == 6:
                s.propulsion = "electric"
            if now >= s.fire_out_t:
                s.fire, s.fire_done = False, True
                self.alert("fire.out", room=s.fire_room)
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
        limit = self.max_astern_speed() if st.ordered_astern else st.max_speed
        if st.ordered_speed > limit:
            st.ordered_speed = limit
            if limit <= 0:
                st.ordered_astern = False
        if st.reversing and not self._reversing and st.speed >= acoustics.ASTERN_TRANSIENT_MIN_KN:
            # omkastningen: propellern slår mot farten och river upp vattnet
            world.emit(Transient("astern", st.x, st.y, st.depth, acoustics.astern_level(st.speed),
                                 self.id, now))
        self._reversing = st.reversing

        # luft
        regen = self.power or s.battery > 0.02
        if regen:
            s.co2 = max(0.3, s.co2 - 0.5 / 3600 * dt)
        else:
            s.co2 += 0.6 / 3600 * dt
            if s.co2 > 1.5 and int(s.co2 * 10) != int((s.co2 - 0.6 / 3600 * dt) * 10):
                self.alert("air", co2=s.co2)

        # djupstyrning: rodren behöver fart, barlasten verkar långsamt
        planes = max(s.health["planes"], 0.2) * (ASTERN_PLANES if st.astern else 1.0)
        st.depth_rate = min(2.0, max(0.2, (0.25 + 0.12 * st.speed) * planes))
        if s.steep and st.ordered_depth > st.depth:   # brant vinkel ned, undan: fortare, men lutar mer
            st.depth_rate = min(STEEP_MAX_MPS, st.depth_rate * STEEP_RATE_F)
        self._bridge_step(now)
        if self.bridge_open:
            st.depth_rate = 0.0               # inte ned med luckan öppen (vi ligger redan uppe)
        if s.blowing:
            st.ordered_depth = 0.0
            st.depth = max(0.0, st.depth - 3.0 * dt)
            if st.depth <= 0.0:
                s.blowing = False
                self.alert("surfaced")

        # vatteninträngning: läckorna, tätningen och länspumparna (damage.py)
        bilge = damage.pumping(self)
        damage.step(self, dt, damage.bilge_capacity(st.depth) if bilge else 0.0)
        if bilge and not self.power:
            s.battery = max(0.0, s.battery - damage.BILGE_BATTERY_PER_H / 3600 * dt)
        self._trim_step(world, dt, regen)
        damage.jam_step(self, dt)
        damage.wear_step(self, dt, not self.surfaced and
                         st.speed > acoustics.cavitation_speed(st.depth, st.prop_astern))
        self._heave_step(world)

        # lutningen av djupbytet, sedan skrovet: snabb djupändring på djupet knakar (kompressionen)
        self._pitch_step(world, st, s, now, dt)
        self._groan_step(world, st, s, now, dt)
        test = self.test_depth()
        if st.depth > test:
            s.hull -= (st.depth - test) / 100.0 * 0.0015 * dt
            if now - s._last_creak >= 60:
                s._last_creak = now
                self.alert("hull.creak", depth=st.depth)
            if s.hull < 0.6 and rng.random() < 0.01 * dt:
                where = 9 if rng.random() < 0.5 else rng.choice(tuple(damage.CENTER))
                damage.add_leak(self, where, "packbox")
                self.alert("damage", severity="lätta", components=[], leak=True, compartment=where)

        # reparationer: en komponent i taget (den skadekontrollen valt), inte bättre än det som går
        # till sjöss och inte i en avdelning folket lämnat; hörbar med slag, tyst i halva takten
        c = s.dmg.repair if s.dmg.repair in COMPONENTS else next(
            (c for c in COMPONENTS if damage.repairable(self, c)), None)
        if c is not None and damage.repairable(self, c):
            cap = s.dmg.cap.get(c, 1.0)
            quiet = s.dmg.repair_quiet
            s.health[c] = min(cap, s.health[c] + dt / REPAIR_S * (damage.REPAIR_QUIET_F if quiet else 1.0))
            if not quiet and now - s.dmg._bang_t >= damage.REPAIR_BANG_S:
                s.dmg._bang_t = now
                world.emit(Transient("repair", st.x, st.y, st.depth, damage.REPAIR_LEVEL, self.id, now))
            if s.health[c] >= cap:
                s.dmg.repair = None
                self.alert("repaired", component=c, **({"partly": True} if cap < 1.0 else {}))

        if st.depth >= CRUSH_DEPTH or s.hull <= 0 or s.flooding >= FLOOD_LOSS_T:
            self.sunk = True
            cause = ("krossad på djupet" if st.depth >= CRUSH_DEPTH
                     else "skrovet brast" if s.hull <= 0 else "vattenfylld")
            world.end("lost", cause=cause)
        elif s.smoke >= 1.0:
            world.end("lost", cause="besättningen kvävd av röken")
