"""Centralen (центральный пост) som bild.

Kaptenens blick förut genom centralen: mätare på väggarna (kurs, sidroder, djup, djuproder),
periskopet mitt i rummet, stegen upp i tornet, besättningen vid pulpeterna. Allt ur egna
instrument (`StatusSnapshot`) och vem som just rapporterat; om andra fartyg bara plottets
kontakter på gyrot (bäringsrepeatern, ur kunskapen), aldrig sanningen.

Ren funktion: `render_central(status, speaking, t, width, height)` ger en rad `Text` per rad.
Bilden ritas i den storlek den får (minst `W` × `H`): stor som huvudvy, liten bredvid loggen.
Stor (`BIG`) har väggarna instrument i braille (`ui/instruments.py`): gyro, sidroder och telegraf
till vänster, djup, fart, klocka och djuproder till höger. Visarna rör sig mjukt (`Needles`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from rich.text import Text

from sim.game import StatusSnapshot

from . import instruments as ins
from .canvas import Canvas as _Canvas
from .placards import PLATE_STYLE, central_plate

W, H = 40, 13                   # minsta storlek (och den lilla bilden bredvid loggen)
CRUSH_M = 450.0
SPEAK_S = 3.0                   # så länge en plats lyser efter en rapport
DIAL_ROW = 1                    # mätarnas översta rad
BIG = (100, 22)                 # minst så stor: braillesinstrumenten
NEEDLE_TAU_S = 0.5              # visarnas tröghet

PALETTES = {
    "normal": {
        "wall": "#3d5244", "ceiling": "#2e4034", "deck": "#33463a", "ring": "#7f9a80",
        "needle": "bold #e8eccf", "hub": "#c8d0b0", "label": "#56705c", "console": "#24342a",
        "crew": "#4f6655", "head": "#8a9c88", "tube": "#9aa89a", "eye": "bold #c8d0b0",
        "ladder": "#56705c", "lamp_off": "#2f4236", "smoke": "#6a6a62", "water": "bold #3f7fbf",
        "water2": "#2f5f8f",
    },
    "red": {
        "wall": "#5a2424", "ceiling": "#401a1a", "deck": "#4a1e1e", "ring": "#b05050",
        "needle": "bold #ffb0a0", "hub": "#e08070", "label": "#7a3a3a", "console": "#341414",
        "crew": "#6a2c2c", "head": "#a05050", "tube": "#b07070", "eye": "bold #e09080",
        "ladder": "#7a3a3a", "lamp_off": "#3a1818", "smoke": "#7a5a5a", "water": "bold #6f5fbf",
        "water2": "#4f3f8f",
    },
}
ROLE_LIGHT = {
    "sonar": "bold #5fd7ff", "navigator": "bold #87ff87", "plot": "bold #ff87ff",
    "engineer": "bold #ffaf5f", "torpedo": "bold #ff5f5f", "officer": "bold #a0c0ff",
    "radio": "bold #d0a8ff", "starpom": "bold #f0f0b0", "trim": "bold #8fd7c6",
    "zampolit": "bold #ffafaf",
}
GREEN, RED, AMBER = "bold #5fd75f", "bold #ff5f5f", "bold #ffaf00"
ASTERN_LAMP = ins.ASTERN_LAMP
SKY_DAY, SKY_NIGHT = "#a8c8e8", "#283850"
MARKER = "bold #f0c674"
# färg per kontaktslag (huvudraden och bäringsrepeatern, som sonarvyns spår)
CONTACT_STYLE = {"threat": "bold #ff7f5f", "contact": "bold #e8c860", "civil": "#a8b890",
                 "benign": "#5f7a68", "friendly": "bold #5fd7ff"}

# nålens riktning i åtta steg (0 = upp, medurs): (rad, kolumn, tecken)
NEEDLE = [(-1, 0, "│"), (-1, 1, "╱"), (0, 1, "─"), (1, 1, "╲"),
          (1, 0, "│"), (1, -1, "╱"), (0, -1, "─"), (-1, -1, "╲")]


@dataclass(frozen=True)
class Geometry:
    """Var allt står i en bild av given storlek."""
    w: int
    h: int

    @property
    def deck(self) -> int:
        return self.h - 1

    @property
    def floor(self) -> int:
        return self.h - 2

    @property
    def body(self) -> int:
        return self.h - 3

    @property
    def head(self) -> int:
        return self.h - 4

    @property
    def console(self) -> int:
        return self.h - 5

    @property
    def lamps(self) -> int:
        return self.h - 6

    @property
    def dial_h(self) -> int:
        """Mätarnas höjd (udda): så stora som höjden ger, men två ska få plats på varje vägg."""
        dh = max(5, (self.h - 6) // 2)
        if dh % 2 == 0:
            dh -= 1
        region = self.left[1] - self.left[0] + 1
        while dh > 5 and 2 * (2 * dh - 3) + 3 > region:
            dh -= 2
        return dh

    @property
    def dial_w(self) -> int:
        return 2 * self.dial_h - 3

    @property
    def label(self) -> int:
        return DIAL_ROW + self.dial_h

    @property
    def big(self) -> bool:
        return self.w >= BIG[0] and self.h >= BIG[1]

    def slots(self) -> dict[str, tuple[int, int, int, int]]:
        """De stora instrumentens rutor (top, left, rows, cols): den stora mätaren ytterst på
        varje vägg, de mindre staplade närmare mitten."""
        top, rows = DIAL_ROW, self.lamps - DIAL_ROW
        out = {}
        for (a, b), outer, inner in ((self.left, "gyro", ("sidror", "telegraf")),
                                     (self.right, "djup", ("fart", "djupror"))):
            width = b - a + 1
            big_w = min(int(width * 0.55), 2 * (rows - 1))
            rest = width - big_w - 1
            upper = rows // 2
            if outer == "gyro":
                out[outer] = (top, a, rows, big_w)
                x = a + big_w + 1
            else:
                out[outer] = (top, b - big_w + 1, rows, big_w)
                x = a
            if inner[0] == "fart":                 # fart och klocka sida vid sida
                half = rest // 2
                out["fart"] = (top, x, upper, half)
                out["klocka"] = (top, x + half, upper, rest - half)
            else:
                out[inner[0]] = (top, x, upper, rest)
            out[inner[1]] = (top + upper, x, rows - upper, rest)
        return out

    @property
    def mid(self) -> int:
        return self.w // 2

    @property
    def ladder(self) -> int:
        return self.mid - 3

    @property
    def peri(self) -> int:                      # periskoprörets vänstra halva
        return self.mid

    @property
    def peri_eye_up(self) -> int:               # okularets rad när periskopet är uppe
        return self.head - 3

    @property
    def officer(self) -> int:                   # vakthavandes huvud
        return self.mid + 4

    @property
    def left(self) -> tuple[int, int]:          # vänstra väggens område (från, till och med)
        return 2, self.mid - 5

    @property
    def right(self) -> tuple[int, int]:
        return self.mid + 4, self.w - 3

    def dials(self) -> dict[str, int]:
        """Mätarnas vänsterkant: två på varje vägg."""
        out = {}
        for (a, b), keys in ((self.left, ("kurs", "roder")), (self.right, ("djup", "djupror"))):
            gap = max(0, (b - a + 1 - 2 * self.dial_w) // 3)
            out[keys[0]] = a + gap
            out[keys[1]] = a + 2 * gap + self.dial_w
        return out

    def seated(self) -> dict[str, int]:
        """Huvudets kolumn för de sittande."""
        a, b = self.left
        lo = self.officer + 4
        hi = max(lo + 8, self.right[1] - 1 - (self.w - W) // 20)
        out = {"ror": round(a + (b - a) * 0.25), "djupror": round(a + (b - a) * 0.75)}
        for i, role in enumerate(("engineer", "navigator", "plot")):
            out[role] = round(lo + (hi - lo) * i / 2)
        return out

    def intercom(self) -> dict[str, int]:
        a = self.left[0]
        return {"sonar": a + 1, "radio": a + 3, "torpedo": a + 5}

    @property
    def telegraph(self) -> int:
        return self.left[0] + 8

    @property
    def julgran(self) -> int:
        """Julgranens vänsterkant: i lilla bilden lamporna i rad, i stora tre per rad med namn."""
        if self.big:
            return self.right[1] - 3 * JULGRAN_CELL + 2
        return self.right[1] - 2 * len(JULGRAN) + 2


def _signed_diff(a: float, b: float) -> float:
    """b − a i (−180, 180]."""
    return (b - a + 180.0) % 360.0 - 180.0


def rudder_angle(s: StatusSnapshot) -> float:
    """Sidrodrets läge, grader, styrbord positivt (ur girens riktning mot beordrad kurs)."""
    if "course" not in s.changing:
        return 0.0
    d = _signed_diff(s.course, s.ordered_course)
    return max(-35.0, min(35.0, d))


PLANE_HOLD_DEG = 15.0      # rodret när det bär så mycket vikt det orkar


def plane_angle(s: StatusSnapshot) -> float:
    """Djuprodrens läge, grader, ned positivt. Vid djupändring mot det beordrade djupet,
    annars så mycket som behövs för att bära vikten (en tung båt håller rodret uppåt)."""
    if s.on_bottom:
        return 0.0
    if "depth" not in s.changing:
        return max(-25.0, min(25.0, -s.plane_load * PLANE_HOLD_DEG))
    return max(-25.0, min(25.0, s.ordered_depth - s.depth))


def eyepiece(rel: float) -> str:
    """Okularet sett akterifrån, vridet mot periskopets bäring relativt fören (rel, grader):
    rakt förut handtagen åt sidorna, åt sidan en pil dit det ser, akterut linserna mot oss."""
    e = list("═▐██▌═")
    sector = round(((rel + 360.0) % 360.0) / 45.0) % 8
    match sector:
        case 1: e[5] = "◥"
        case 2: e[5] = "▶"
        case 3: e[5] = "◢"
        case 4: e[2:4] = "◉◉"
        case 5: e[0] = "◣"
        case 6: e[0] = "◀"
        case 7: e[0] = "◤"
    return "".join(e)


JULGRAN = ("Lucka", "Periskop", "Radar", "Antenn", "Ventil", "Blåsning")
JULGRAN_CELL = 11               # "● Periskop" och mellanrum


def openings(s: StatusSnapshot) -> list[tuple[str, str | None]]:
    """Julgranen (skrovets öppningar och ventiler): namn och lampans färg (rött öppet, gult
    blåser, grönt stängt). Bara egna instrument."""
    up = s.periscope is not None and s.periscope_optic == "periskop"
    state = (s.bridge != "shut", up, s.radar_up, s.transmitting, s.ventilating)
    out = [(name, RED if is_open else GREEN) for name, is_open in zip(JULGRAN, state)]
    out.append((JULGRAN[-1], AMBER if s.blowing else GREEN))
    return out


PERI_MODE = {"sweep": "svep", "look": "titt", "hold": "håller"}


def _ring_cell(angle: float, rx: int, ry: int) -> tuple[int, int]:
    """Var på mätarens ram en vinkel hamnar, relativt mitten."""
    a = math.radians(angle)
    dx, dy = math.sin(a), -math.cos(a)
    k = 1.0 / max(abs(dx) / rx, abs(dy) / ry)
    return round(k * dy), round(k * dx)


def _dial(c: _Canvas, g: Geometry, col: int, angle: float, p: dict,
          marker: float | None = None, top: str | None = None, style: str | None = None) -> None:
    ring = style or p["ring"]
    dw, dh = g.dial_w, g.dial_h
    r0 = DIAL_ROW
    c.text(r0, col, "╭" + "─" * (dw - 2) + "╮", ring)
    for r in range(1, dh - 1):
        c.text(r0 + r, col, "│" + " " * (dw - 2) + "│", ring)
    c.text(r0 + dh - 1, col, "╰" + "─" * (dw - 2) + "╯", ring)
    rx, ry = dw // 2, dh // 2
    cr, cc = r0 + ry, col + rx
    if top:
        c.put(r0, cc, top, ring)
    if marker is not None:
        dr, dc = _ring_cell(marker, rx, ry)
        c.put(cr + dr, cc + dc, "◆", MARKER)
    dr, dc, ch = NEEDLE[round(angle / 45.0) % 8]
    if dr == 0:                                   # vågrätt
        for k in range(1, rx):
            c.put(cr, cc + dc * k, ch, p["needle"])
    else:                                         # lodrätt eller snett (tecknen är dubbelt så höga)
        wide = 1 if dh == 5 else 2
        for k in range(1, ry):
            for j in range(wide if dc else 1):
                c.put(cr + dr * k, cc + dc * (wide * k - j), ch, p["needle"])
    c.put(cr, cc, "●", p["hub"])


class Needles:
    """Visarnas visade läge: följer instrumenten med tröghet, så att de svänger mjukt
    i stället för att hoppa en gång per sekund. En per bild (widget)."""

    def __init__(self, tau: float = NEEDLE_TAU_S) -> None:
        self.tau = tau
        self.values: dict[str, float] = {}
        self.t: float | None = None

    def update(self, s: StatusSnapshot, now: float) -> dict[str, float]:
        targets = {"course": s.course, "depth": s.depth, "speed": s.speed,
                   "rudder": rudder_angle(s), "planes": plane_angle(s)}
        dt = 0.0 if self.t is None else max(0.0, min(2.0, now - self.t))
        self.t = now
        k = 1.0 - math.exp(-dt / self.tau) if dt > 0 else 0.0
        for key, target in targets.items():
            if key not in self.values:
                self.values[key] = target
            elif key == "course":
                v = self.values[key]
                self.values[key] = (v + _signed_diff(v, target) * k) % 360.0
            else:
                self.values[key] += (target - self.values[key]) * k
        return dict(self.values)


def repeater(s: StatusSnapshot) -> list[tuple[str, float, str]]:
    """Bäringsrepeaterns märken: plottets hållna kontakter med bäring (numret i beteckningen,
    färgen efter slaget som i huvudraden), hot först."""
    out = []
    for d, kind, b in zip(s.contacts_held, s.contact_kinds, s.contact_bearings):
        if b is None:
            continue
        out.append((d.rsplit("-", 1)[-1], b, CONTACT_STYLE.get(kind, CONTACT_STYLE["contact"])))
    return out


def _big_instruments(c: _Canvas, g: Geometry, s: StatusSnapshot, shown: dict[str, float],
                     p: dict, ring: str | None) -> None:
    slots = g.slots()
    turning = "course" in s.changing
    diving = "depth" in s.changing
    dials = {
        "gyro": ins.gyro(shown["course"], s.ordered_course if turning else None, p,
                         repeater(s)),
        "djup": ins.depth_gauge(shown["depth"], s.ordered_depth if diving else None, p),
        "fart": ins.speed_gauge(shown["speed"], s.ordered_speed, s.depth, s.cavitating, p,
                                astern=s.astern, ordered_astern=s.ordered_astern),
        "klocka": ins.clock_face(s.clock, p),
        "sidror": ins.rudder_gauge(shown["rudder"], p),
        "djupror": ins.planes_gauge(shown["planes"], p, pitch=s.pitch),
        "telegraf": ins.telegraph(s.ordered_speed, s.speed, s.propulsion, s.reactor, p,
                                  astern=s.astern, ordered_astern=s.ordered_astern),
    }
    # avläsningarna visar instrumentens exakta värde, visarna det trögare
    dials["gyro"].readout[0] = (ins.fmt_course(s.course), "bold")
    dials["djup"].readout[0] = (f"{s.depth:.0f} m", dials["djup"].readout[0][1])
    for key, d in dials.items():
        top, left, rows, cols = slots[key]
        ins.draw_dial(c, top, left, rows, cols, d, p, ring)


def _small_dials(c: _Canvas, g: Geometry, s: StatusSnapshot, shown: dict[str, float],
                 p: dict, dial_style: str | None, blink: bool) -> None:
    """Den lilla bilden: fyra enkla mätare med åtta visarlägen."""
    dials = g.dials()
    _dial(c, g, dials["kurs"], shown["course"], p, top="N",
          marker=s.ordered_course if "course" in s.changing else None, style=dial_style)
    _dial(c, g, dials["roder"], shown["rudder"] * 2.5, p, style=dial_style)

    def depth_angle(d: float) -> float:
        return -150.0 + 300.0 * min(max(d, 0.0) / CRUSH_M, 1.0)

    deep = s.depth >= 300
    _dial(c, g, dials["djup"], depth_angle(shown["depth"]), p,
          marker=depth_angle(s.ordered_depth) if "depth" in s.changing else None,
          style=RED if deep and blink else dial_style)
    _dial(c, g, dials["djupror"], 90.0 + shown["planes"] * 2.0, p, style=dial_style)
    for key, label in (("kurs", "kurs"), ("roder", "roder"), ("djup", "djup"),
                       ("djupror", "djupr")):
        col = dials[key] + g.dial_w // 2 - len(label) // 2
        c.text(g.label, col, label, p["label"])


def _seated(c: _Canvas, g: Geometry, col: int, p: dict, lit: str | None, lean: int = 0) -> None:
    c.put(g.head, col + lean, "●", lit or p["head"])
    c.text(g.body, col - 1, "▟█▙", lit or p["crew"])


def render_central(s: StatusSnapshot, speaking: dict[str, float] | None = None,
                   t: float = 0.0, width: int = W, height: int = H,
                   shown: dict[str, float] | None = None) -> list[Text]:
    """speaking: roll → sekunder sedan rollens senaste rapport. t: väggklocka för blinkande.
    width/height: bildens storlek i tecken (minst W × H). shown: visarnas läge (`Needles`),
    annars instrumentens."""
    g = Geometry(max(W, width), max(H, height))
    shown = shown or {"course": s.course, "depth": s.depth, "speed": s.speed,
                      "rudder": rudder_angle(s), "planes": plane_angle(s)}
    red = s.night or s.hunted
    p = PALETTES["red" if red else "normal"]
    speaking = speaking or {}
    lit = {role: ROLE_LIGHT.get(role) for role, age in speaking.items() if age < SPEAK_S}
    blink = (t % 1.0) < 0.5
    smoky = s.smoke > 0.5
    c = _Canvas(g.w, g.h, p["wall"])

    # skrovet: tak, väggar och durk
    c.text(0, 0, "▗" + "▄" * (g.w - 2) + "▖", p["ceiling"])
    for r in range(1, g.deck):
        c.put(r, 0, "▐", p["wall"])
        c.put(r, g.w - 1, "▌", p["wall"])
    c.text(g.deck, 0, "▀" * g.w, p["deck"])

    # mässingsskylten i taket, mellan väggen och stegen
    plate = central_plate()
    if g.ladder - 4 >= len(plate):
        c.text(0, max(2, (g.ladder - 2 - len(plate)) // 2), plate, PLATE_STYLE)

    # tornluckan och stegen
    if s.bridge != "shut":
        sky = SKY_NIGHT if s.night else SKY_DAY
        c.text(0, g.ladder - 1, "███", sky)
        if not s.night:
            for r in (1, 2):
                c.put(r, g.ladder - 1, "░", sky)
                c.put(r, g.ladder + 1, "░", sky)
    for r in range(1, g.floor):
        c.put(r, g.ladder, "╫", p["ladder"])
    if s.bridge in ("manning", "clearing"):          # någon på stegen
        span = max(1, min(4, g.floor - 3))
        step = int(t * 2) % span
        r = span - step if s.bridge == "manning" else 1 + step
        c.put(r, g.ladder, "●", p["head"])
        c.put(r + 1, g.ladder, "█", p["crew"])

    # mätarna
    dial_style = p["label"] if smoky else None
    if g.big:
        _big_instruments(c, g, s, shown, p, dial_style)
    else:
        _small_dials(c, g, s, shown, p, dial_style, blink)

    # pulpeterna
    for a, b in (g.left, g.right):
        c.text(g.console, a, "▒" * (b - a + 1), p["console"])
    # snabbtelefonen (Kasjtan): lyser när sonar, radio eller torpedrummet talar
    for role, col in g.intercom().items():
        c.put(g.lamps, col, "●" if role in lit else "○", lit.get(role) or p["lamp_off"])
    # maskintelegrafen: beordrad fart i fyra steg
    steps = sum(s.ordered_speed >= v for v in (0.5, 6.0, 12.0, 20.0))
    tele = GREEN if s.propulsion == "turbine" else "bold #5fafff"
    if s.reactor != "online":
        tele = AMBER
    if s.ordered_astern:
        tele = ASTERN_LAMP                          # back i maskin
    if not g.big:                                   # stor: telegrafen är ett instrument
        for i, ch in enumerate("▂▄▆█"):
            c.put(g.lamps, g.telegraph + i, ch, tele if i < steps else p["lamp_off"])
    # julgranen: skrovets öppningar, grönt stängt, rött öppet
    if g.big:                                       # tavlan under högra pulpeten, med namn
        for i, (name, lamp) in enumerate(openings(s)):
            r, col = g.head + i // 3, g.julgran + JULGRAN_CELL * (i % 3)
            c.put(r, col, "●", lamp)
            c.text(r, col + 2, name, p["label"])
    else:
        for i, (_, lamp) in enumerate(openings(s)):
            c.put(g.lamps, g.julgran + 2 * i, "●", lamp)

    # periskopet
    up = s.periscope is not None and s.periscope_optic == "periskop"
    c.text(1, g.peri, "╤╤", p["tube"])
    if up:
        eye = max(g.peri_eye_up, g.floor - s.periscope_up_s)
        for r in range(2, g.floor):
            c.text(r, g.peri, "┃┃", p["tube"])
        c.text(eye, g.peri - 2, eyepiece(_signed_diff(s.course, s.periscope_train)), p["eye"])
        if g.big:                                   # gradringen under okularet, vid pulpeten
            label = (f"PERISKOP {ins.fmt_course(s.periscope_train)} · "
                     f"{PERI_MODE.get(s.periscope, s.periscope)} · {s.periscope_power}")
            c.text(g.floor, g.peri + 4, label, p["eye"])
    c.text(g.floor, g.peri - 1, "▁▁▁▁", p["tube"])

    # besättningen
    if not g.big:                                   # stor: inga figurer, bara rummet
        officer = lit.get("officer")
        c.put(g.console, g.officer, "●", officer or p["head"])
        c.text(g.head, g.officer - 1, "▟█▙", officer or p["crew"])
        c.text(g.body, g.officer - 1, "▐ ▌", officer or p["crew"])
    rud = shown["rudder"]
    lean = 1 if rud > 5 else -1 if rud < -5 else 0
    if not g.big:                                   # stor: instrumenten står ensamma vid pulpeterna
        seats = g.seated()
        _seated(c, g, seats["ror"], p, None, lean)
        _seated(c, g, seats["djupror"], p, None)
        for role in ("engineer", "navigator", "plot"):
            _seated(c, g, seats[role], p, lit.get(role))

    # larmlampor i taket: stridslarm rött, brand gult
    alarm = RED if s.hunted else AMBER if s.fire else None
    if alarm:
        for col in (1, g.w - 2):
            c.put(1, col, "◉" if blink else "○", alarm if blink else p["lamp_off"])

    # rök uppifrån, vatten nerifrån
    if s.smoke > 0.02 or s.fire:
        rows = max(1, math.ceil(min(s.smoke, 1.0) * (g.h - 4)))
        drift = int(t * 2)
        for r in range(1, 1 + rows):
            for col in range(1, g.w - 1):
                if not c.blank(r, col) and s.smoke < 0.7:
                    continue
                if (col + r + drift) % 3 != 0 or s.smoke > 0.4:
                    c.put(r, col, "▒" if s.smoke > 0.6 else "░", p["smoke"])
    if s.flooding > 0.5:
        level = 1 if s.flooding < 10 else 2 if s.flooding < 40 else 3
        phase = int(t * 2) % 2
        for i in range(level):
            r = g.floor - i
            for col in range(1, g.w - 1):
                top = i == level - 1
                ch = ("≈" if (col + phase) % 2 else "~") if top else "█"
                c.put(r, col, ch, p["water"] if top else p["water2"])
    if s.command == "starpom":                  # kaptenen är inte här
        sign = " СТАРПОМ – STARPOM HAR BEFÄLET " if g.w >= 40 else " СТАРПОМ "
        c.text(g.deck, max(1, (g.w - len(sign)) // 2), sign, PLATE_STYLE)
    return c.lines()
