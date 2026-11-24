"""Centralen (центральный пост) som bild.

Kaptenens blick förut genom centralen: väggarna, periskopet mitt i rummet, stegen upp i tornet,
besättningen vid pulpeterna. Bara egna instrument (`StatusSnapshot`) och vem som just rapporterat,
aldrig kunskapen om andra fartyg (kontakterna står i översikten, `ui/overview_render.py`).

Ren funktion: `render_central(status, speaking, t, width, height)` ger en rad `Text` per rad.
Bilden ritas i den storlek den får (minst `W` × `H`). Två storlekar: stor (`BIG`, huvudvyn) har
väggarna instrument i braille (`ui/central_instruments.py`, `ui/instruments.py`): gyro, sidroder och
telegraf till vänster, djup, fart, klocka och djuproder till höger, visarna mjuka (`Needles`).
Liten (bredvid loggen) är bara rummet: rör på väggarna, besättningen och lamporna.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from rich.text import Text

from sim.game import StatusSnapshot

from .canvas import Canvas as _Canvas
from .central_instruments import (AMBER, GREEN, JULGRAN, JULGRAN_CELL, PLANE_HOLD_DEG, RED,  # noqa: F401
                                  Needles, draw_instruments, openings, plane_angle, rudder_angle,
                                  shown_now, signed_diff, telegraph_lamp)
from .placards import PLATE_STYLE, central_plate

W, H = 40, 13                   # minsta storlek (och den lilla bilden bredvid loggen)
SPEAK_S = 3.0                   # så länge en plats lyser efter en rapport
DIAL_ROW = 1                    # instrumentens översta rad
BIG = (100, 22)                 # minst så stor: braillesinstrumenten

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
SKY_DAY, SKY_NIGHT = "#a8c8e8", "#283850"


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

    def pipes(self) -> tuple[int, ...]:
        """Rörens rader på väggarna i lilla bilden."""
        return tuple(r for r in (2, 4) if r < self.lamps - 1)

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
    shown = shown or shown_now(s)
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

    # stor: instrumenten på väggarna; liten: bara rören
    if g.big:
        draw_instruments(c, g.slots(), s, shown, p, p["label"] if smoky else None)
    else:
        for a, b in (g.left, g.right):
            for k, r in enumerate(g.pipes()):
                c.text(r, a, "═" * (b - a + 1), p["ring"])
                for col in range(a + 3 + 2 * k, b - 1, 7):
                    c.put(r, col, "⊗", p["label"])

    # pulpeterna
    for a, b in (g.left, g.right):
        c.text(g.console, a, "▒" * (b - a + 1), p["console"])
    # snabbtelefonen (Kasjtan): lyser när sonar, radio eller torpedrummet talar
    for role, col in g.intercom().items():
        c.put(g.lamps, col, "●" if role in lit else "○", lit.get(role) or p["lamp_off"])
    # maskintelegrafen: beordrad fart i fyra steg
    if not g.big:                                   # stor: telegrafen är ett instrument
        steps, tele = telegraph_lamp(s)
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
        c.text(eye, g.peri - 2, eyepiece(signed_diff(s.course, s.periscope_train)), p["eye"])
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
