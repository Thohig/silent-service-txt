"""Centralens instrument: rodrens lägen, visarnas tröghet, julgranen och de stora mätarna.

Bara egna instrument (`StatusSnapshot`), aldrig kunskapen om andra fartyg: kontakterna står i
översikten (`ui/overview_render.py`). Scenen (rummet, figurerna, periskopet) bor i
`ui/central_render.py`, som ritar mätarna här i de rutor `Geometry.slots` ger.
"""
from __future__ import annotations

import math

from sim.game import StatusSnapshot

from . import instruments as ins
from .canvas import Canvas

NEEDLE_TAU_S = 0.5              # visarnas tröghet
PLANE_HOLD_DEG = 15.0           # rodret när det bär så mycket vikt det orkar
GREEN, RED, AMBER = "bold #5fd75f", "bold #ff5f5f", "bold #ffaf00"

JULGRAN = ("Lucka", "Periskop", "Radar", "Antenn", "Ventil", "Blåsning")
JULGRAN_CELL = 11               # "● Periskop" och mellanrum


def signed_diff(a: float, b: float) -> float:
    """b − a i (−180, 180]."""
    return (b - a + 180.0) % 360.0 - 180.0


def rudder_angle(s: StatusSnapshot) -> float:
    """Sidrodrets läge, grader, styrbord positivt (ur girens riktning mot beordrad kurs)."""
    if "course" not in s.changing:
        return 0.0
    d = signed_diff(s.course, s.ordered_course)
    return max(-35.0, min(35.0, d))


def plane_angle(s: StatusSnapshot) -> float:
    """Djuprodrens läge, grader, ned positivt. Vid djupändring mot det beordrade djupet,
    annars så mycket som behövs för att bära vikten (en tung båt håller rodret uppåt)."""
    if s.on_bottom:
        return 0.0
    if "depth" not in s.changing:
        return max(-25.0, min(25.0, -s.plane_load * PLANE_HOLD_DEG))
    return max(-25.0, min(25.0, s.ordered_depth - s.depth))


def openings(s: StatusSnapshot) -> list[tuple[str, str | None]]:
    """Julgranen (skrovets öppningar och ventiler): namn och lampans färg (rött öppet, gult
    blåser, grönt stängt). Bara egna instrument."""
    up = s.periscope is not None and s.periscope_optic == "periskop"
    state = (s.bridge != "shut", up, s.radar_up, s.transmitting, s.ventilating)
    out = [(name, RED if is_open else GREEN) for name, is_open in zip(JULGRAN, state)]
    out.append((JULGRAN[-1], AMBER if s.blowing else GREEN))
    return out


def shown_now(s: StatusSnapshot) -> dict[str, float]:
    """Visarnas läge utan tröghet: instrumentens."""
    return {"course": s.course, "depth": s.depth, "speed": s.speed,
            "rudder": rudder_angle(s), "planes": plane_angle(s)}


class Needles:
    """Visarnas visade läge: följer instrumenten med tröghet, så att de svänger mjukt
    i stället för att hoppa en gång per sekund. En per bild (widget)."""

    def __init__(self, tau: float = NEEDLE_TAU_S) -> None:
        self.tau = tau
        self.values: dict[str, float] = {}
        self.t: float | None = None

    def update(self, s: StatusSnapshot, now: float) -> dict[str, float]:
        targets = shown_now(s)
        dt = 0.0 if self.t is None else max(0.0, min(2.0, now - self.t))
        self.t = now
        k = 1.0 - math.exp(-dt / self.tau) if dt > 0 else 0.0
        for key, target in targets.items():
            if key not in self.values:
                self.values[key] = target
            elif key == "course":
                v = self.values[key]
                self.values[key] = (v + signed_diff(v, target) * k) % 360.0
            else:
                self.values[key] += (target - self.values[key]) * k
        return dict(self.values)


def telegraph_lamp(s: StatusSnapshot) -> tuple[int, str]:
    """Maskintelegrafen i lilla bilden: beordrad fart i fyra steg och lampans färg."""
    steps = sum(s.ordered_speed >= v for v in (0.5, 6.0, 12.0, 20.0))
    tele = GREEN if s.propulsion == "turbine" else "bold #5fafff"
    if s.reactor != "online":
        tele = AMBER
    if s.ordered_astern:
        tele = ins.ASTERN_LAMP                      # back i maskin
    return steps, tele


def build_dials(s: StatusSnapshot, shown: dict[str, float], p: dict) -> dict[str, ins.Dial]:
    """Instrumenten (visare, skalor och avläsning) ur egen ubåts läge."""
    turning = "course" in s.changing
    diving = "depth" in s.changing
    dials = {
        "gyro": ins.gyro(shown["course"], s.ordered_course if turning else None, p),
        "djup": ins.depth_gauge(shown["depth"], s.ordered_depth if diving else None, p),
        "fart": ins.speed_gauge(shown["speed"], s.ordered_speed, s.depth, s.cavitating, p,
                                astern=s.astern, ordered_astern=s.ordered_astern),
        "klocka": ins.clock_face(s.clock, p),
        "sidror": ins.rudder_gauge(shown["rudder"], p),
        "djupror": ins.planes_gauge(shown["planes"], p, pitch=s.pitch),
        "telegraf": ins.telegraph(s.ordered_speed, s.speed, s.propulsion, s.reactor, p,
                                  astern=s.astern, ordered_astern=s.ordered_astern),
        "lutning": ins.pitch_gauge(s.pitch, p),
        "trim": ins.trim_gauge(s.plane_load, p),
        "batteri": ins.battery_gauge(s.battery, s.reactor, p),
        "lans": ins.bilge_gauge(s.flooding, p),
    }
    # avläsningarna visar instrumentens exakta värde, visarna det trögare
    dials["gyro"].readout[0] = (ins.fmt_course(s.course), "bold")
    dials["djup"].readout[0] = (f"{s.depth:.0f} m", dials["djup"].readout[0][1])
    return dials


def draw_instruments(c: Canvas, slots: dict[str, tuple[int, int, int, int]], s: StatusSnapshot,
                     shown: dict[str, float], p: dict, ring: str | None) -> None:
    """De stora instrumenten i braille, var och en i sin ruta (top, left, rows, cols)."""
    dials = build_dials(s, shown, p)
    for key, d in dials.items():
        if key in slots:                            # de mindre bara på en hög vägg
            top, left, rows, cols = slots[key]
            ins.draw_dial(c, top, left, rows, cols, d, p, ring)


READOUT_WALLS = (("gyro", "sidror", "telegraf", "lutning", "trim"),
                 ("djup", "fart", "djupror", "batteri", "lans", "klocka"))


def draw_readouts(c: Canvas, walls: tuple[tuple[int, int], tuple[int, int]], top: int, bottom: int,
                  s: StatusSnapshot, shown: dict[str, float], p: dict) -> None:
    """Mellanstor bild (helskärm i ett 80 × 24-fönster, för liten för braillemätarna): instrumentens
    namn och avläsning som rader på väggarna, vänster gyro, roder och telegraf, höger djup och fart.
    Raderna glesas ut när väggen är hög; får inte alla plats tas de sista bort."""
    dials = build_dials(s, shown, p)
    rows = bottom - top + 1
    step = max(1, rows // max(len(k) for k in READOUT_WALLS))     # samma radavstånd på båda väggarna
    for (a, b), keys in zip(walls, READOUT_WALLS):
        n = min(len(keys), rows)
        name_w = max(len(dials[k].title) for k in keys[:n]) + 1 if n else 0
        for i, key in enumerate(keys[:n]):
            d, r, col = dials[key], top + i * step, a
            if r > bottom:
                break
            c.text(r, col, d.title.ljust(name_w)[: b - col + 1], p["label"])
            col += name_w
            for text, style in d.readout:
                text = text[: max(0, b - col + 1)]
                c.text(r, col, text, style or "bold")
                col += len(text)
