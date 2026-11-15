"""Centralen (центральный пост) som bild bredvid loggen.

Kaptenens blick förut genom centralen: mätare på väggarna (kurs, sidroder, djup, djuproder),
periskopet mitt i rummet, stegen upp i tornet, besättningen vid pulpeterna. Allt ur egna
instrument (`StatusSnapshot`) och vem som just rapporterat; aldrig något om fienden.

Ren funktion: `render_central(status, speaking, t)` ger en rad `Text` per rad.
"""
from __future__ import annotations

import math

from rich.text import Text

from sim.game import StatusSnapshot

W, H = 40, 13
CRUSH_M = 450.0
SPEAK_S = 3.0                   # så länge en plats lyser efter en rapport

# rad- och kolumnlägen
DIAL_ROW = 1                    # mätarnas översta rad (5 rader höga, 7 breda)
DIALS = {"kurs": 2, "roder": 9, "djup": 24, "djupror": 31}   # vänsterkant
LABEL_ROW = 6
LAMP_ROW = 7
CONSOLE_ROW = 8
HEAD_ROW, BODY_ROW = 9, 10
FLOOR_ROW, DECK_ROW = 11, 12
LADDER_COL = 17
PERI_COL = 20                   # periskoprörets vänstra halva (två kolumner)
PERI_EYE_UP = 6                 # okularets rad när periskopet är uppe
OFFICER_COL = 24                # vakthavandes huvud
SEATED = {"ror": 5, "djupror": 12, "engineer": 28, "navigator": 32, "plot": 36}   # huvudets kolumn
INTERCOM = {"sonar": 3, "radio": 5, "torpedo": 7}

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
    "radio": "bold #d0a8ff",
}
GREEN, RED, AMBER = "bold #5fd75f", "bold #ff5f5f", "bold #ffaf00"
SKY_DAY, SKY_NIGHT = "#a8c8e8", "#283850"

# nålens riktning i åtta steg (0 = upp, medurs): (rad, kolumn, tecken)
NEEDLE = [(-1, 0, "│"), (-1, 1, "╱"), (0, 1, "─"), (1, 1, "╲"),
          (1, 0, "│"), (1, -1, "╱"), (0, -1, "─"), (-1, -1, "╲")]


class _Canvas:
    def __init__(self, base: str) -> None:
        self.cells = [[(" ", base) for _ in range(W)] for _ in range(H)]

    def put(self, row: int, col: int, ch: str, style: str) -> None:
        if 0 <= row < H and 0 <= col < W:
            self.cells[row][col] = (ch, style)

    def text(self, row: int, col: int, s: str, style: str) -> None:
        for i, ch in enumerate(s):
            if ch != "\0":
                self.put(row, col + i, ch, style)

    def blank(self, row: int, col: int) -> bool:
        return self.cells[row][col][0] == " "

    def lines(self) -> list[Text]:
        out = []
        for row in self.cells:
            t = Text(no_wrap=True, overflow="crop")
            run, style = "", None
            for ch, st in row:
                if st != style and run:
                    t.append(run, style=style)
                    run = ""
                run += ch
                style = st
            if run:
                t.append(run, style=style)
            out.append(t)
        return out


def _signed_diff(a: float, b: float) -> float:
    """b − a i (−180, 180]."""
    return (b - a + 180.0) % 360.0 - 180.0


def rudder_angle(s: StatusSnapshot) -> float:
    """Sidrodrets läge, grader, styrbord positivt (ur girens riktning mot beordrad kurs)."""
    if "course" not in s.changing:
        return 0.0
    d = _signed_diff(s.course, s.ordered_course)
    return max(-35.0, min(35.0, d))


def plane_angle(s: StatusSnapshot) -> float:
    """Djuprodrens läge, grader, ned positivt."""
    if "depth" not in s.changing or s.on_bottom:
        return 0.0
    return max(-25.0, min(25.0, s.ordered_depth - s.depth))


def _ring_cell(angle: float) -> tuple[int, int]:
    """Var på mätarens ram (7 × 5) en vinkel hamnar, relativt mitten."""
    a = math.radians(angle)
    dx, dy = math.sin(a), -math.cos(a)
    k = 1.0 / max(abs(dx) / 3.0, abs(dy) / 2.0)
    return round(k * dy), round(k * dx)


def _dial(c: _Canvas, col: int, angle: float, p: dict, marker: float | None = None,
          top: str | None = None, style: str | None = None) -> None:
    ring = style or p["ring"]
    r0 = DIAL_ROW
    c.text(r0, col, "╭─────╮", ring)
    for r in range(1, 4):
        c.text(r0 + r, col, "│     │", ring)
    c.text(r0 + 4, col, "╰─────╯", ring)
    cr, cc = r0 + 2, col + 3
    if top:
        c.put(r0, cc, top, ring)
    if marker is not None:
        dr, dc = _ring_cell(marker)
        c.put(cr + dr, cc + dc, "◆", "bold #f0c674")
    dr, dc, ch = NEEDLE[round(angle / 45.0) % 8]
    c.put(cr + dr, cc + dc, ch, p["needle"])
    if dr == 0:                                   # vågrätt: nålen räcker två steg
        c.put(cr, cc + 2 * dc, ch, p["needle"])
    c.put(cr, cc, "●", p["hub"])


def _seated(c: _Canvas, col: int, p: dict, lit: str | None, lean: int = 0) -> None:
    c.put(HEAD_ROW, col + lean, "●", lit or p["head"])
    c.text(BODY_ROW, col - 1, "▟█▙", lit or p["crew"])


def render_central(s: StatusSnapshot, speaking: dict[str, float] | None = None,
                   t: float = 0.0) -> list[Text]:
    """speaking: roll → sekunder sedan rollens senaste rapport. t: väggklocka för blinkande."""
    red = s.night or s.hunted
    p = PALETTES["red" if red else "normal"]
    speaking = speaking or {}
    lit = {role: ROLE_LIGHT.get(role) for role, age in speaking.items() if age < SPEAK_S}
    blink = (t % 1.0) < 0.5
    smoky = s.smoke > 0.5
    c = _Canvas(p["wall"])

    # skrovet: tak, väggar och durk
    c.text(0, 0, "▗" + "▄" * (W - 2) + "▖", p["ceiling"])
    for r in range(1, DECK_ROW):
        c.put(r, 0, "▐", p["wall"])
        c.put(r, W - 1, "▌", p["wall"])
    c.text(DECK_ROW, 0, "▀" * W, p["deck"])

    # tornluckan och stegen
    if s.bridge != "shut":
        sky = SKY_NIGHT if s.night else SKY_DAY
        c.text(0, LADDER_COL - 1, "███", sky)
        if not s.night:
            for r in (1, 2):
                c.put(r, LADDER_COL - 1, "░", sky)
                c.put(r, LADDER_COL + 1, "░", sky)
    for r in range(1, FLOOR_ROW):
        c.put(r, LADDER_COL, "╫", p["ladder"])
    if s.bridge in ("manning", "clearing"):          # någon på stegen
        step = int(t * 2) % 4
        r = 4 - step if s.bridge == "manning" else 1 + step
        c.put(r, LADDER_COL, "●", p["head"])
        c.put(r + 1, LADDER_COL, "█", p["crew"])

    # mätarna
    dial_style = p["label"] if smoky else None
    _dial(c, DIALS["kurs"], s.course, p, top="N",
          marker=s.ordered_course if "course" in s.changing else None, style=dial_style)
    _dial(c, DIALS["roder"], rudder_angle(s) * 2.5, p, style=dial_style)
    depth_angle = lambda d: -150.0 + 300.0 * min(max(d, 0.0) / CRUSH_M, 1.0)
    deep = s.depth >= 300
    _dial(c, DIALS["djup"], depth_angle(s.depth), p,
          marker=depth_angle(s.ordered_depth) if "depth" in s.changing else None,
          style=RED if deep and blink else dial_style)
    _dial(c, DIALS["djupror"], 90.0 + plane_angle(s) * 2.0, p, style=dial_style)
    for key, label in (("kurs", "kurs"), ("roder", "roder"), ("djup", "djup"),
                       ("djupror", "djupr")):
        col = DIALS[key] + 3 - len(label) // 2
        c.text(LABEL_ROW, col, label, p["label"])

    # pulpeterna
    c.text(CONSOLE_ROW, 2, "▒" * 14, p["console"])
    c.text(CONSOLE_ROW, 24, "▒" * 14, p["console"])
    # snabbtelefonen (Kasjtan): lyser när sonar, radio eller torpedrummet talar
    for role, col in INTERCOM.items():
        c.put(LAMP_ROW, col, "●" if role in lit else "○", lit.get(role) or p["lamp_off"])
    # maskintelegrafen: beordrad fart i fyra steg
    steps = sum(s.ordered_speed >= v for v in (0.5, 6.0, 12.0, 20.0))
    tele = GREEN if s.propulsion == "turbine" else "bold #5fafff"
    if s.reactor != "online":
        tele = AMBER
    for i, ch in enumerate("▂▄▆█"):
        c.put(LAMP_ROW, 10 + i, ch, tele if i < steps else p["lamp_off"])
    # julgranen: skrovets öppningar, grönt stängt, rött öppet
    openings = (s.bridge != "shut", s.periscope is not None and s.periscope_optic == "periskop",
                s.masts_up)
    for i, is_open in enumerate(openings):
        c.put(LAMP_ROW, 31 + 2 * i, "●", RED if is_open else GREEN)

    # periskopet
    up = s.periscope is not None and s.periscope_optic == "periskop"
    c.text(1, PERI_COL, "╤╤", p["tube"])
    if up:
        eye = max(PERI_EYE_UP, FLOOR_ROW - s.periscope_up_s)
        for r in range(2, FLOOR_ROW):
            c.text(r, PERI_COL, "┃┃", p["tube"])
        c.text(eye, PERI_COL - 2, "═▐██▌═", p["eye"])
    c.text(FLOOR_ROW, PERI_COL - 1, "▁▁▁▁", p["tube"])

    # besättningen
    officer = lit.get("officer")
    c.put(CONSOLE_ROW, OFFICER_COL, "●", officer or p["head"])
    c.text(HEAD_ROW, OFFICER_COL - 1, "▟█▙", officer or p["crew"])
    c.text(BODY_ROW, OFFICER_COL - 1, "▐ ▌", officer or p["crew"])
    lean = 1 if rudder_angle(s) > 5 else -1 if rudder_angle(s) < -5 else 0
    _seated(c, SEATED["ror"], p, None, lean)
    _seated(c, SEATED["djupror"], p, None)
    for role in ("engineer", "navigator", "plot"):
        _seated(c, SEATED[role], p, lit.get(role))

    # larmlampor i taket: stridslarm rött, brand gult
    alarm = RED if s.hunted else AMBER if s.fire else None
    if alarm:
        for col in (1, W - 2):
            c.put(1, col, "◉" if blink else "○", alarm if blink else p["lamp_off"])

    # rök uppifrån, vatten nerifrån
    if s.smoke > 0.02 or s.fire:
        rows = max(1, math.ceil(min(s.smoke, 1.0) * 9))
        drift = int(t * 2)
        for r in range(1, 1 + rows):
            for col in range(1, W - 1):
                if not c.blank(r, col) and s.smoke < 0.7:
                    continue
                if (col + r + drift) % 3 != 0 or s.smoke > 0.4:
                    c.put(r, col, "▒" if s.smoke > 0.6 else "░", p["smoke"])
    if s.flooding > 0.5:
        level = 1 if s.flooding < 10 else 2 if s.flooding < 40 else 3
        phase = int(t * 2) % 2
        for i in range(level):
            r = FLOOR_ROW - i
            for col in range(1, W - 1):
                top = i == level - 1
                ch = ("≈" if (col + phase) % 2 else "~") if top else "█"
                c.put(r, col, ch, p["water"] if top else p["water2"])
    return c.lines()
