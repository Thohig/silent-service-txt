"""Kollision med andra fartyg (sanning). docs/system/besattning.md, Skadekontrollen (Kollision och ramning).

Varje sekund, efter rörelsen, prövas egen ubåt mot varje fartyg:

- på höjden: ett ytfartyg går från ytan ned till sitt djupgående (`DRAFT_M`); en ubåt från tornets topp
  (kölen − `SAIL_M`) till kölen. Egen ubåt: skrovet från kölen − `HULL_TOP_M` till kölen, tornet ovanför det
  (kring `SAIL_FRAC` längs skrovet). Kölen är djupet, i ytläge `SURFACE_KEEL_M`.
- i sidled: närmaste avstånd mellan skrovens axlar (sträckor längs kursen, `weapons.HULL_M`) mot de halva
  bredderna; när bara tornet når upp i fartygets djupgående, tornets korta sträcka mot fartygets axel.

En träff går genom skadekontrollen (`damage.py`): tornet uppifrån ger periskopet och radion och en liten läcka
i centralen; skrovet ger skador efter den relativa farten (`REL_*`), från en buckla till skrovbrott, där
kontaktpunkten avgör avdelningen. Smällen hörs (`Transient("collision")`) och fartyget vet exakt var vi är.
Samma fartyg igen först när de skilts åt (`APART_M`).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from . import damage
from .entities import Transient
from .weapons import HULL_DEFAULT_M, HULL_M

if TYPE_CHECKING:
    from .entities import Vessel
    from .world import World

NM = 1852.0
KN_MPS = 0.5144
OWN_HALF_LEN_M = damage.HULL_LEN_M / 2
OWN_HALF_BEAM_M = 4.0
HULL_TOP_M = 8.0            # skrovets överkant över kölen
SAIL_M = 13.0               # tornets topp över kölen (tornet bryter ytan med kölen på 13 m)
SAIL_FRAC = (0.22, 0.34)    # tornet längs skrovet (0 fören, 1 aktern)
SAIL_HALF_BEAM_M = 2.0
SURFACE_KEEL_M = 7.0        # i ytläge går kölen så djupt (seabed.SURFACE_DRAFT_M)
SUPERSTRUCTURE_M = -30.0    # ytfartygets överbyggnad: ovanför ytan, når allt
DRAFT_M = {"destroyer": 5.5, "merchant": 8.0, "transport": 9.0, "tanker": 11.0, "patrol": 2.5,
           "guardship": 4.0, "fishing": 4.0, "spytrawler": 4.5, "moored": 8.0}
DRAFT_DEFAULT_M = 6.0
SUBMARINES = ("submarine", "ssbn", "foxtrot")
APART_M = 60.0              # skilda åt: samma fartyg kan träffa igen
COLLISION_LEVEL = 165.0     # dB: stålet mot stål hörs långt
# skadorna efter den relativa farten (knop)
REL_LEAK_KN = 3.0           # under det en buckla, ingen läcka
REL_WELD_KN = 6.0           # svetsfog
REL_CRACK_KN = 12.0         # spricka (skalad med farten)
HULL_PER_KN = 0.02          # skrovet per knop (ramad i 30 kn: 0,6)
COMPONENT_PER_KN = 0.04
SCRAM_KN = 8.0              # så hård smäll: reaktorn snabbstoppar
SAIL_HIT = 0.3              # tornet: periskopet och radion …
SAIL_PER_KN = 0.05          # … plus så mycket per knop
SAIL_HULL_PER_KN = 0.004


def _keel(v) -> float:
    return max(v.state.depth, SURFACE_KEEL_M)


def _vertical(v: Vessel) -> tuple[float, float]:
    """Fartygets utsträckning på höjden (överst, underst), meter under ytan."""
    if v.kind in SUBMARINES:
        k = _keel(v)
        return k - SAIL_M, k
    return SUPERSTRUCTURE_M, DRAFT_M.get(v.kind, DRAFT_DEFAULT_M)


def _axis(x: float, y: float, course: float, half_m: float, a: float = -1.0, b: float = 1.0):
    """Skrovets axel som sträcka (meter, lokalt kring x, y i nm), från a till b av halva längden (+ fören)."""
    c = math.radians(course)
    fx, fy = math.sin(c), math.cos(c)
    return ((x * NM + fx * half_m * a, y * NM + fy * half_m * a),
            (x * NM + fx * half_m * b, y * NM + fy * half_m * b))


def _seg_dist(p1, p2, q1, q2) -> tuple[float, float]:
    """Närmaste avstånd mellan sträckorna p1–p2 och q1–q2, och var på p (0–1) det är."""
    def clamp(t):
        return max(0.0, min(1.0, t))
    d1 = (p2[0] - p1[0], p2[1] - p1[1])
    d2 = (q2[0] - q1[0], q2[1] - q1[1])
    r = (p1[0] - q1[0], p1[1] - q1[1])
    a, e = d1[0] ** 2 + d1[1] ** 2, d2[0] ** 2 + d2[1] ** 2
    f = d2[0] * r[0] + d2[1] * r[1]
    c = d1[0] * r[0] + d1[1] * r[1]
    b = d1[0] * d2[0] + d1[1] * d2[1]
    denom = a * e - b * b
    s = clamp((b * f - c * e) / denom) if denom > 1e-9 else 0.0
    t = (b * s + f) / e if e > 1e-9 else 0.0
    if t < 0:
        t, s = 0.0, clamp(-c / a) if a > 1e-9 else 0.0
    elif t > 1:
        t, s = 1.0, clamp((b - c) / a) if a > 1e-9 else 0.0
    px, py = p1[0] + d1[0] * s, p1[1] + d1[1] * s
    qx, qy = q1[0] + d2[0] * t, q1[1] + d2[1] * t
    return math.hypot(px - qx, py - qy), s


def _velocity(v) -> tuple[float, float]:
    st = v.state
    c = math.radians(st.course)
    sp = -st.speed if getattr(st, "astern", False) else st.speed
    return sp * math.sin(c), sp * math.cos(c)


def contact(own, v) -> tuple[str, float] | None:
    """Rör fartyget oss? ("hull"/"sail", var längs vårt skrov 0 fören – 1 aktern) eller None."""
    top, bottom = _vertical(v)
    keel = _keel(own)
    hull = keel - HULL_TOP_M < bottom and keel > top
    sail = keel - SAIL_M < bottom and keel - HULL_TOP_M > top
    if not hull and not sail:
        return None
    half_len, half_beam = HULL_M.get(v.kind, HULL_DEFAULT_M)
    if v.kind in SUBMARINES:
        half_beam = OWN_HALF_BEAM_M
    q1, q2 = _axis(v.state.x, v.state.y, v.state.course, half_len)
    o = own.state
    if hull:
        p1, p2 = _axis(o.x, o.y, o.course, OWN_HALF_LEN_M)
        d, s = _seg_dist(p1, p2, q1, q2)
        if d <= OWN_HALF_BEAM_M + half_beam:
            return "hull", 1.0 - s          # p1 är aktern (a = -1): s = 0 aktern
    if sail or hull:
        # tornet: från SAIL_FRAC i fören räknat (frac 0 = fören = +1 av halva längden)
        a, b = 1.0 - 2 * SAIL_FRAC[1], 1.0 - 2 * SAIL_FRAC[0]
        p1, p2 = _axis(o.x, o.y, o.course, OWN_HALF_LEN_M, a, b)
        d, s = _seg_dist(p1, p2, q1, q2)
        if d <= SAIL_HALF_BEAM_M + half_beam and keel - SAIL_M < bottom:
            return "sail", SAIL_FRAC[1] - s * (SAIL_FRAC[1] - SAIL_FRAC[0])
    return None


def ship_contact(world: World) -> None:
    """Egen ubåt mot alla fartyg, en gång per sekund efter rörelsen."""
    own = world.own
    if own.sunk:
        return
    touching = own.sys.dmg.touching
    o = own.state
    for v in world.contacts:
        if v.sunk or not v.is_ship or v.airborne or v is own:
            continue
        r = math.hypot(v.state.x - o.x, v.state.y - o.y) * NM
        if r > OWN_HALF_LEN_M + HULL_M.get(v.kind, HULL_DEFAULT_M)[0] + APART_M:
            touching.discard(v.id)
            continue
        hit = contact(own, v)
        if hit is None:
            continue                    # (samma fartyg igen först när skroven är långt isär, ovan)
        if v.id in touching:
            continue
        touching.add(v.id)
        _collide(world, v, *hit)


def _collide(world: World, v, where: str, frac: float) -> None:
    own, s, o = world.own, world.own.sys, world.own.state
    ovx, ovy = _velocity(own)
    vvx, vvy = _velocity(v)
    rel = math.hypot(ovx - vvx, ovy - vvy)
    n = damage.compartment_at(frac)
    rng = world.rng
    now = world.time
    surface = v.kind not in SUBMARINES
    if where == "sail":
        hit = ["periscope", "radio"]
        for c in hit:
            s.health[c] = max(0.0, s.health[c] - SAIL_HIT - SAIL_PER_KN * rel)
        s.hull -= SAIL_HULL_PER_KN * rel
        leak = rel >= REL_LEAK_KN
        if leak:
            damage.add_leak(own, 3, "rör")
        severity = "svåra" if rel >= REL_WELD_KN else "lätta"
    else:
        hit = damage.nearest_components(frac, 2 if rel >= REL_WELD_KN else 1, rng,
                                        tuple(damage.COMPONENT_COMPARTMENT))
        for c in hit:
            s.health[c] = max(0.0, s.health[c] - COMPONENT_PER_KN * rel)
        s.hull -= HULL_PER_KN * rel
        leak = rel >= REL_LEAK_KN
        if rel >= REL_CRACK_KN:
            damage.add_leak(own, n, "spricka", rel / REL_CRACK_KN)
            damage.limit(own, hit[0], 0.75)
        elif rel >= REL_WELD_KN:
            damage.add_leak(own, n, "svetsfog")
        elif leak:
            damage.add_leak(own, n, "rör")
        severity = "svåra" if rel >= REL_WELD_KN else "lätta"
        if rel >= SCRAM_KN:
            own.scram("kollisionen")
    damage.shock(own, 1.0 if rel >= REL_WELD_KN else 0.5)
    s.dmg.last_collision_t = now
    # båtarna studsar isär: farten går ned, en träff uppifrån trycker oss ned några meter
    o.speed *= 0.5
    if where == "sail" and surface:
        o.depth += 2.0
    world.emit(Transient("collision", o.x, o.y, o.depth, COLLISION_LEVEL, own.id, now))
    world.mission.setdefault("collisions", []).append((now, v.id, where, round(rel, 1)))
    # fartyget vet nu exakt var vi är
    for ai in world.ais:
        if getattr(ai, "vessel", None) is v and hasattr(ai, "_set_datum"):
            ai._set_datum(world, o.x, o.y, o.depth, 0.05, fix=True)
            ai.last_contact_t = now
            if hasattr(ai, "opening_until"):
                ai.opening_until = now + 90         # backar ur och vänder för ett anfall
    own.alert("collision", where=where, compartment=n, components=hit, leak=leak, severity=severity,
              rammed=rel >= REL_CRACK_KN, surface=surface, from_above=surface and where == "sail")
