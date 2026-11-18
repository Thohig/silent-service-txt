"""Lotsen: andra fartyg går inte på land (sanning).

Fienderna och trafiken styr mot mål utan att se på sjökortet: en patrullbåt jagar ett datum som
bruset lagt på stranden, ett handelsfartyg går mot nästa brytpunkt i en fjordkrök. Efter deras
beslut varje tick prövar lotsen vägen fartyget skulle ta med den beordrade kursen (giren åt det
kortaste hållet med fartygets girhastighet, sedan rakt fram) en stund framåt. Leder den upp på
grunt vatten väljs den närmaste kurs (i steg om 10°) vars väg är fri; finns ingen går fartyget den
väg som håller djupast vatten. Bara för scenarier med land (`Seabed.has_land`); egen ubåt styrs
av besättningen och känner botten själv (`bottom_contact`). Ingen slump: samma frö, samma spel.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .geo import angle_diff, norm360

if TYPE_CHECKING:
    from .entities import Vessel
    from .world import World

LOOK_S = 180.0              # så långt fram (i tid) lotsen ser: en halv gir med 1°/s
LOOK_MIN_NM = 0.25          # långsamma fartyg ser minst så långt
STEPS = 18                  # prov längs vägen
SURFACE_KEEL_M = 10.0       # ytfartyg: minsta vattendjup (djupgående med marginal)
SUBMERGED_CLEAR_M = 15.0    # ubåt i undervattensläge: så mycket vatten under kölen
SURFACE_DEPTH_M = 2.0       # grundare än så räknas som ytläge
STEP_DEG = 10.0
OFFSETS = np.array(sorted((float(d) for d in np.arange(-170.0, 190.0, STEP_DEG)),
                          key=lambda d: (abs(d), d)))


def _needs(v: Vessel) -> float:
    d = v.state.depth
    return SURFACE_KEEL_M if d < SURFACE_DEPTH_M else d + SUBMERGED_CLEAR_M


def _min_depths(world: World, v: Vessel, targets: np.ndarray) -> np.ndarray:
    """Grundaste djupet längs vägen mot varje beordrad kurs (gir åt kortaste hållet, sedan rakt)."""
    s = v.state
    kn = max(s.speed, s.ordered_speed or 0.0)
    nm_s = kn / 3600.0
    horizon = max(LOOK_S, LOOK_MIN_NM / nm_s)
    dt = horizon / STEPS
    delta = (targets - s.course + 180.0) % 360.0 - 180.0
    delta = np.where(delta == -180.0, 180.0, delta)
    t = (np.arange(STEPS) + 0.5)[None, :] * dt                  # mitt i varje steg
    turned = np.sign(delta)[:, None] * np.minimum(s.turn_rate * t, np.abs(delta)[:, None])
    h = np.radians(s.course + turned)
    xs = s.x + np.cumsum(nm_s * dt * np.sin(h), axis=1)
    ys = s.y + np.cumsum(nm_s * dt * np.cos(h), axis=1)
    return world.env.seabed.depths(xs, ys).min(axis=1)


def clear_course(world: World, v: Vessel) -> float | None:
    """Kursen fartyget ska gå i stället för den beordrade, eller None om den beordrade är fri."""
    s = v.state
    need = _needs(v)
    ordered = s.ordered_course
    if _min_depths(world, v, np.array([ordered]))[0] >= need:
        return None
    cands = (ordered + OFFSETS) % 360.0
    depths = _min_depths(world, v, cands)
    free = np.flatnonzero(depths >= need)
    if free.size == 0:
        return norm360(float(cands[int(np.argmax(depths))]))
    # närmast den beordrade; lika långt åt båda hållen ⇒ minst gir från nuvarande kurs
    best = min(free, key=lambda i: (abs(OFFSETS[i]), abs(angle_diff(cands[i], s.course))))
    return norm360(float(cands[best]))


def steer_clear(world: World) -> None:
    """Vänd undan de fartyg (inte egen ubåt) som är på väg upp på grunt vatten."""
    sb = world.env.seabed
    if sb is None or not sb.has_land:
        return
    for v in world.contacts:
        if (v.sunk or not v.is_ship or v.airborne or v.drifts_with_ice or v.kind == "moored"
                or v.side == "own"):
            continue
        if max(v.state.speed, v.state.ordered_speed or 0.0) <= 0.0:
            continue
        c = clear_course(world, v)
        if c is not None:
            v.state.order_course(c)
