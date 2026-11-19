"""Det utkiken på bryggan och i periskopet ser av händelser: plask, vattenpelare och
träffar bland transienterna (sanning, alltså bara för sensorstationerna).

En transient finns i `World.transients` det tick den skapades (hörbar nästa), så den
som tittar varje sekund ser den medan den sker; sedan håller stationen den i bilden
`EVENT_S` sekunder. Synligheten är geometri, ingen slump: dagsljus för plask, blixten på
natten för explosioner, och höjden över horisonten och vågtopparna (`event_visible`).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..geo import bearing_to, distance
from ..periscope import FLASH_NM, event_visible, wave_height_m


@dataclass(frozen=True)
class SeenEvent:
    kind: str           # splash, column, hit
    x: float
    y: float
    bearing: float      # sann bäring
    range_nm: float     # sant avstånd
    practice: bool
    nuclear: bool


def visible_events(world, eye_m: float, looked=None) -> list[SeenEvent]:
    """Händelserna detta tick som syns från ögat (höjd över vattnet eye_m). looked(bäring)
    begränsar till ett synfält (periskopets okular)."""
    now = world.time
    light = world.env.light(now)
    day, vis = light.daylight, light.visibility_nm
    wave = wave_height_m(world.env.sea_state)
    torpedoes = {v.id: v for v in world.contacts if v.kind == "torpedo"}
    own = world.own.state
    out = []
    for tr in world.transients:
        if tr.kind not in ("splash", "explosion"):
            continue
        r = distance(own.x, own.y, tr.x, tr.y)
        if tr.kind == "splash":
            if not day or r > vis:
                continue
            kind, nuclear = "splash", False
        else:
            if r > (vis if day else max(vis, FLASH_NM)):
                continue
            t = torpedoes.get(tr.source_id)
            kind = "hit" if t is not None else "column"
            nuclear = kind == "hit" and t.spec.nuclear
        if not event_visible(kind, r, eye_m, wave if kind == "splash" or day else 0.0):
            continue
        b = bearing_to(own.x, own.y, tr.x, tr.y)
        if looked is not None and not looked(b):
            continue
        out.append(SeenEvent(kind, tr.x, tr.y, b, r, tr.practice, nuclear))
    return out
