"""Skador, läckor och vattnet i avdelningarna (sanning). docs/system/besattning.md, Skadekontrollen.

Skadan sitter någonstans: laddningens läge längs skrovet avgör avdelningen (`frac_of`, `compartment_at`) och
vilka komponenter som tar stöten (de närmaste, `nearest_components`). En läcka (`Leak`) har en plats och en
sort; inflödet växer med djupet (roten ur trycket, `inflow_factor`), så att gå grundare minskar det. Avdelningens
folk tätar läckan (`LEAK_KINDS`: tid och vad som blir kvar; en spricka går inte att täta helt till sjöss).

Vattnet ligger i avdelningen där läckan är. Vid en läcka stänger besättningen länsskotten själv; en avdelning
tar som mest `CAP_T` ton (sedan står trycket emot). Över hälften fullt lämnar folket den (`EVAC_FRAC`): ingen
tätar läckan och inget lagas där. Vattnet ger framåt- eller bakåtlast (`fore_load`) till trimmen.

`OwnSystems.flooding` och `leak_rate` är summorna (ton ombord, ton/min just nu), räknade här varje sekund.
Sätter något annat dem direkt (äldre tester) läggs skillnaden i femte avdelningen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ownship import OwnShip

HULL_LEN_M = 107.0
# (nummer, namn, mitten räknat från fören 0–1, ton vatten avdelningen tar)
COMPARTMENTS = ((1, "torped", 0.06, 40.0), (2, "batteri", 0.17, 35.0), (3, "central", 0.28, 40.0),
                (4, "diesel", 0.38, 30.0), (5, "reaktor", 0.48, 40.0), (6, "turbin", 0.59, 40.0),
                (7, "el", 0.69, 30.0), (8, "bostad", 0.79, 30.0), (9, "akter", 0.92, 25.0))
CENTER = {n: c for n, _, c, _ in COMPARTMENTS}
CAP_T = {n: cap for n, _, _, cap in COMPARTMENTS}
COMPONENT_COMPARTMENT = {"tubes": 1, "sonar": 1, "periscope": 3, "radio": 3,
                         "propulsion": 6, "planes": 9}
FORE_LEVER_T = 0.5          # framåtlast per ton vatten längst fram (fören +, aktern −)


@dataclass(frozen=True)
class LeakKind:
    k: float                # ton/min vid ytan (gånger inflow_factor på djupet)
    seal_s: int             # så länge tätar avdelningens folk den (på ytan)
    residual: float         # det som blir kvar när de gjort vad de kan (0 = tät)


LEAK_KINDS = {
    "packbox": LeakKind(0.08, 120, 0.0),      # axel- eller rodertätning
    "rör": LeakKind(0.18, 200, 0.0),          # rörgenomföring, ventil
    "svetsfog": LeakKind(0.30, 360, 0.0),
    "spricka": LeakKind(0.50, 600, 0.3),      # skrovet: kilas och stöttas, men läcker kvar
}
SEAL_DEPTH_M = 400.0        # tätningen tar (1 + djup/SEAL_DEPTH_M) gånger längre: trycket
EVAC_FRAC = 0.5             # så full: folket lämnar avdelningen och stänger skottet efter sig
REMAN_FRAC = 0.2            # så lite vatten kvar: de går in igen
WET_FRAC = 0.5              # komponenterna i en så full avdelning står under vatten
WET_HEALTH = 0.25
WET_CAP = 0.6               # saltvatten: går inte att laga helt till sjöss
OPEN_BELOW_T = 1.0          # inga läckor och så lite vatten: skotten öppnas igen

# Fastnat djuproder: en skada som tar rodren under JAM_HEALTH medan de står ute låser dem. Båten går
# då ned (eller upp) med farten tills rodren kopplats om till handstyrning (JAM_MANUAL_S).
# Länspumparna: tar mindre ju djupare (mottrycket), behöver kraft (på batteriet drar de av det) och hörs.
BILGE_T_PER_MIN = 1.0       # vid ytan
BILGE_ZERO_M = 500.0        # kapaciteten faller linjärt mot noll här …
BILGE_MIN_F = 0.25          # … men inte under så stor andel
BILGE_LEVEL = 124.0         # dB när de går
BILGE_BATTERY_PER_H = 0.05  # på batteriet: så mycket laddning per timme
# Belastningen (steg 5): felen kommer av hur båten körs, aldrig ur det blå, och maskin varnar innan.
STRESS_HALF_S = 3600.0      # tryckvågornas belastning halveras på så lång tid
STRESS_SCRAM_F = 4.0        # snabbstopp: så många gånger fler per enhet belastning
STRESS_LEAK_F = 3.0         # ångläcka: likaså
BEARING_HOT_KN = 24.0       # så fort på turbinen: lagren blir varma
BEARING_WARN_S = 1200       # maskin varnar efter så lång tid
BEARING_DAMAGE_S = 1800     # lagren skär
BEARING_DAMAGE = 0.35
BEARING_CAP = 0.8
CAVITATION_WARN_S = 900     # sammanlagt så länge kaviterat: maskin säger att propellern far illa
CAVITATION_DAMAGE_S = 1800  # gröpt: framdrivningen kan inte lagas bättre än förut minus EROSION_CAP …
EROSION_CAP = 0.1
EROSION_DB = 1.0            # … och den hörs så mycket mer (högst EROSION_MAX_DB)
EROSION_MAX_DB = 3.0
DEEP_FRAC = 0.95            # nära provdjupet: djupare än så stor del av det (0,9 = 270 m tjatade, krig frö 2)
DEEP_WARN_S = 600           # maskin säger att packboxarna gråter
DEEP_LEAK_S = 1200          # en packbox släpper (akteraxeln)
REPAIR_QUIET_F = 0.5        # tyst reparation (tystnad i båten): så mycket av takten
REPAIR_BANG_S = 40          # hörbar reparation: ett slag (hammare, mejsel) så ofta
REPAIR_LEVEL = 130.0        # dB
BATTERY_SHORT_T = 3.0       # så mycket vatten i andra avdelningen: saltvatten i batteriet, kortslutning, brand
BATTERY_SHORT_KEEP = 0.7    # det som är kvar av laddningen (cellerna som brann)
JAM_HEALTH = 0.35
JAM_MPS_PER_KN = 0.05
JAM_MANUAL_S = 90


def bilge_capacity(depth: float) -> float:
    """Ton per minut länspumparna tar på djupet."""
    return BILGE_T_PER_MIN * max(BILGE_MIN_F, 1.0 - max(depth, 0.0) / BILGE_ZERO_M)


def repairable(own: OwnShip, component: str) -> bool:
    """Går komponenten att laga mer nu (skadad under det som går till sjöss, folk i avdelningen)?"""
    s = own.sys
    return s.health[component] < s.dmg.cap.get(component, 1.0) - 1e-9 and \
        COMPONENT_COMPARTMENT[component] not in s.dmg.evacuated


def pumping(own: OwnShip) -> bool:
    """Går länspumparna (påslagna, med kraft och något att ta)?"""
    s = own.sys
    return s.dmg.bilge_on and (own.power or s.battery > 0.02) and s.flooding > 0.05


def inflow_factor(depth: float) -> float:
    """Inflödet växer med roten ur trycket (1 bar vid ytan, +1 per 10 m)."""
    return math.sqrt(1.0 + max(depth, 0.0) / 10.0)


@dataclass
class Leak:
    compartment: int
    kind: str
    scale: float = 1.0
    progress: float = 0.0       # tätningsarbetet, 0–1
    held: bool = False          # en spricka: så tät som den blir till sjöss (sagt en gång)

    def rate(self, depth: float) -> float:
        """Ton per minut just nu."""
        lk = LEAK_KINDS[self.kind]
        return lk.k * self.scale * inflow_factor(depth) * (1.0 - min(self.progress, 1.0) * (1.0 - lk.residual))


@dataclass
class DamageState:
    water: dict[int, float] = field(default_factory=lambda: {n: 0.0 for n in CENTER})
    leaks: list[Leak] = field(default_factory=list)
    closed: bool = False                    # länsskotten stängda
    evacuated: set[int] = field(default_factory=set)
    cap: dict[str, float] = field(default_factory=dict)     # det en komponent kan lagas till till sjöss
    planes_jam: int = 0                     # +1 rodren fast i dykläge, −1 i stigläge
    jam_left: float = 0.0
    jam_order: float = 0.0                  # det beordrade djupet att gå tillbaka till efter omkopplingen
    _jam_set: float = -1.0
    bilge_on: bool = True                   # länspumparna (skadekontrollen styr dem)
    battery_shorted: bool = False           # saltvatten i batteriet har kortslutit (en gång)
    repair: str | None = None               # komponenten som lagas (skadekontrollen väljer; None: den första)
    repair_quiet: bool = False              # tyst: halva takten, inga slag
    # belastningen (wear_step): fel som kommer av hur båten körs, varslade av maskin först
    stress: float = 0.0                     # tryckvågor och skador nyss (halveras på en timme)
    bearing_heat_s: float = 0.0             # tid i full fart på turbinen (svalnar dubbelt så fort)
    cavitation_s: float = 0.0               # tid som propellern kaviterat (sedan förra gången den gröptes)
    eroded_db: float = 0.0                  # propellern gröpt av kavitationen: så mycket mer hörs den
    deep_s: float = 0.0                     # tid nära provdjupet (sedan förra packboxläckan)
    _warned: set = field(default_factory=set)
    touching: set = field(default_factory=set)          # fartyg vi ligger an mot (collision.py)
    last_collision_t: int = -10**9
    _bang_t: int = -10**9
    _flood_seen: float = 0.0
    _leak_seen: float = 0.0

    def leak_rate(self, depth: float) -> float:
        return sum(lk.rate(depth) for lk in self.leaks if self.water[lk.compartment] < CAP_T[lk.compartment])

    def flooded(self, n: int) -> bool:
        return self.water[n] > WET_FRAC * CAP_T[n]


def fore_load(dmg: DamageState) -> float:
    """Framåtlast (ton, + förut) av vattnet i avdelningarna."""
    return sum(w * (1.0 - 2.0 * CENTER[n]) * FORE_LEVER_T for n, w in dmg.water.items())


def compartment_at(frac: float) -> int:
    return min(CENTER, key=lambda n: abs(CENTER[n] - frac))


def frac_of(own: OwnShip, x: float, y: float) -> float:
    """Var längs skrovet en punkt ligger: 0 fören, 1 aktern (punkten projicerad på kölen)."""
    st = own.state
    c = math.radians(st.course)
    along = ((x - st.x) * math.sin(c) + (y - st.y) * math.cos(c)) * 1852.0
    return min(1.0, max(0.0, 0.5 - along / HULL_LEN_M))


def nearest_components(frac: float, n: int, rng, components) -> list[str]:
    """De n komponenter som sitter närmast punkten längs skrovet (lika nära: slumpen)."""
    ranked = sorted(components, key=lambda c: (abs(CENTER[COMPONENT_COMPARTMENT[c]] - frac), rng.random()))
    return ranked[:n]


def add_leak(own: OwnShip, compartment: int, kind: str, scale: float = 1.0) -> Leak:
    """En ny läcka; besättningen stänger länsskotten."""
    dmg = own.sys.dmg
    leak = Leak(compartment, kind, scale)
    dmg.leaks.append(leak)
    dmg.closed = True
    own.sys.leak_rate = dmg._leak_seen = dmg.leak_rate(own.state.depth)
    return leak


def limit(own: OwnShip, component: str, cap: float) -> None:
    """Komponenten kan inte lagas bättre än cap till sjöss."""
    dmg = own.sys.dmg
    dmg.cap[component] = min(dmg.cap.get(component, 1.0), cap)


def maybe_jam(own: OwnShip, rng) -> None:
    """Rodren skadades under JAM_HEALTH: står de ute fastnar de (åt det håll de stod)."""
    s, st, dmg = own.sys, own.state, own.sys.dmg
    if dmg.planes_jam or s.health["planes"] >= JAM_HEALTH or own.surfaced or s.on_bottom:
        return
    diff = st.ordered_depth - st.depth
    direction = 1 if diff > 2 else -1 if diff < -2 else (1 if rng.random() < 0.5 else -1)
    dmg.planes_jam, dmg.jam_left = direction, float(JAM_MANUAL_S)
    dmg.jam_order = dmg._jam_set = st.ordered_depth      # kaptenens djup: dit igen när rodren är omkopplade
    own.alert("dc.planes_jammed", down=direction > 0)


def _absorb_external(own: OwnShip) -> None:
    """Någon har satt flooding eller leak_rate direkt (äldre tester): lägg det i femte avdelningen."""
    s, dmg = own.sys, own.sys.dmg
    extra = s.flooding - dmg._flood_seen
    if abs(extra) > 1e-9:
        if extra > 0:
            dmg.water[5] += extra
        else:
            _remove(dmg, -extra)
    extra = s.leak_rate - dmg._leak_seen
    if extra > 1e-9:
        lk = LEAK_KINDS["rör"]
        add_leak(own, 5, "rör", extra / (lk.k * inflow_factor(own.state.depth)))


def _remove(dmg: DamageState, tons: float) -> float:
    """Ta bort så mycket vatten (fullast avdelning först); hur mycket som togs."""
    taken = 0.0
    for n in sorted(dmg.water, key=lambda n: -dmg.water[n]):
        if tons - taken <= 0:
            break
        d = min(dmg.water[n], tons - taken)
        dmg.water[n] -= d
        taken += d
    return taken


def step(own: OwnShip, dt: float, pump_t_per_min: float) -> None:
    """En sekund: läckorna fyller sina avdelningar, folket tätar, pumparna tar, folket går ut och in."""
    s, st, dmg = own.sys, own.state, own.sys.dmg
    _absorb_external(own)
    depth = st.depth
    for leak in list(dmg.leaks):
        n = leak.compartment
        dmg.water[n] = min(CAP_T[n], dmg.water[n] + leak.rate(depth) * dt / 60.0)
        if n in dmg.evacuated:
            continue                                # ingen därinne som tätar
        lk = LEAK_KINDS[leak.kind]
        leak.progress = min(1.0, leak.progress + dt / (lk.seal_s * (1.0 + depth / SEAL_DEPTH_M)))
        if leak.progress >= 1.0:
            if lk.residual <= 0:
                dmg.leaks.remove(leak)
                own.alert("leak_stopped", compartment=n, kind=leak.kind)
            elif not leak.held:
                leak.held = True
                own.alert("dc.leak_held", compartment=n, kind=leak.kind)
    if pump_t_per_min > 0:
        _remove(dmg, pump_t_per_min * dt / 60.0)
    for n in CENTER:
        if dmg.closed and n not in dmg.evacuated and dmg.water[n] > EVAC_FRAC * CAP_T[n]:
            dmg.evacuated.add(n)
            own.alert("dc.evacuated", compartment=n)
        elif n in dmg.evacuated and dmg.water[n] < REMAN_FRAC * CAP_T[n]:
            dmg.evacuated.discard(n)
            own.alert("dc.remanned", compartment=n)
        if dmg.flooded(n):
            for c, where in COMPONENT_COMPARTMENT.items():
                if where == n:
                    s.health[c] = min(s.health[c], WET_HEALTH)
                    limit(own, c, WET_CAP)
    total = sum(dmg.water.values())
    if dmg.closed and not dmg.leaks and total < OPEN_BELOW_T and not dmg.evacuated:
        dmg.closed = False
        own.alert("dc.bulkheads_open")
    s.flooding = dmg._flood_seen = total
    s.leak_rate = dmg._leak_seen = dmg.leak_rate(depth)


def jam_step(own: OwnShip, dt: float) -> None:
    """Fastnat djuproder: båten går ned (upp) med farten, djupstyrningen är borta."""
    s, st, dmg = own.sys, own.state, own.sys.dmg
    if not dmg.planes_jam:
        return
    if st.ordered_depth != dmg._jam_set:
        dmg.jam_order = st.ordered_depth             # kaptenen har beordrat ett nytt djup under tiden
    dmg.jam_left -= dt
    if dmg.jam_left <= 0 or own.surfaced or s.on_bottom or s.blowing:
        dmg.planes_jam = 0
        # tillbaka till det beordrade djupet (förut låg båten kvar där rodren drivit den, konvoj-mot frö 3:
        # på 3,6 m, och eskorten rammade); inte vid nödblåsning (då ska vi upp)
        if not s.blowing:
            st.ordered_depth = dmg.jam_order
        if dmg.jam_left <= 0:
            own.alert("dc.planes_manual")
        return
    v = -st.speed if st.astern else st.speed
    st.depth_rate = 0.0
    st.depth = max(0.0, st.depth + dmg.planes_jam * JAM_MPS_PER_KN * v * dt)
    st.ordered_depth = dmg._jam_set = st.depth


def shock(own: OwnShip, amount: float = 1.0) -> None:
    """En tryckvåg eller skada: belastningen ökar (snabbstopp och ångläcka blir vanligare en tid)."""
    own.sys.dmg.stress += amount


def stress_factor(dmg: DamageState, f: float) -> float:
    return 1.0 + f * dmg.stress


def _warn_once(own: OwnShip, key: str, type: str, **data) -> None:
    dmg = own.sys.dmg
    if key not in dmg._warned:
        dmg._warned.add(key)
        own.alert(type, **data)


def wear_step(own: OwnShip, dt: float, cavitating: bool) -> None:
    """Belastningen en sekund: lagren i full fart, propellern som kaviterar, packboxarna på djupet."""
    s, st, dmg = own.sys, own.state, own.sys.dmg
    dmg.stress *= 0.5 ** (dt / STRESS_HALF_S)
    # lagren
    if s.propulsion == "turbine" and own.power and st.speed >= BEARING_HOT_KN:
        dmg.bearing_heat_s += dt
    else:
        dmg.bearing_heat_s = max(0.0, dmg.bearing_heat_s - 2 * dt)
        if dmg.bearing_heat_s < BEARING_WARN_S / 2:
            dmg._warned.discard("bearings")
    if dmg.bearing_heat_s >= BEARING_WARN_S:
        _warn_once(own, "bearings", "wear.bearings_warm", minutes=round(dmg.bearing_heat_s / 60))
    if dmg.bearing_heat_s >= BEARING_DAMAGE_S:
        dmg.bearing_heat_s = 0.0
        s.health["propulsion"] = max(0.0, s.health["propulsion"] - BEARING_DAMAGE)
        limit(own, "propulsion", BEARING_CAP)
        own.alert("wear.bearings_ran")
    # propellern
    if cavitating:
        dmg.cavitation_s += dt
        if dmg.cavitation_s >= CAVITATION_WARN_S:
            _warn_once(own, "cavitation", "wear.cavitation", minutes=round(dmg.cavitation_s / 60))
        if dmg.cavitation_s >= CAVITATION_DAMAGE_S:
            dmg.cavitation_s = 0.0
            dmg._warned.discard("cavitation")
            limit(own, "propulsion", dmg.cap.get("propulsion", 1.0) - EROSION_CAP)
            s.health["propulsion"] = min(s.health["propulsion"], dmg.cap["propulsion"])
            dmg.eroded_db = min(EROSION_MAX_DB, dmg.eroded_db + EROSION_DB)
            own.alert("wear.eroded")
    # packboxarna nära provdjupet
    if st.depth > DEEP_FRAC * own.test_depth() and not own.surfaced:
        dmg.deep_s += dt
        if dmg.deep_s >= DEEP_WARN_S:
            _warn_once(own, "deep", "wear.deep", depth=round(st.depth))
        if dmg.deep_s >= DEEP_LEAK_S:
            dmg.deep_s = 0.0
            dmg._warned.discard("deep")
            add_leak(own, 9, "packbox")
            own.alert("wear.packing", compartment=9)
    else:
        dmg.deep_s = max(0.0, dmg.deep_s - dt)
        if dmg.deep_s < DEEP_WARN_S / 2:
            dmg._warned.discard("deep")
