"""Kaptenens hytt (каюта командира) som bild.

Kojen, skrivbordet med sjökortsrullen och nattlampan, repeatrarna för kurs och djup
och skeppsklockan på skottet (braille, `ui/instruments.py`), och snabbtelefonen «Каштан»
med sin lampa: släckt, lyser (något att veta) eller blinkar rött (det ringer). Inga
kontakter syns härifrån; vill kaptenen veta mer får han ringa centralen.

Medan kaptenen är på väg till centralen visas gången och lejdaren, och han själv på väg.

Ren funktion: `render_cabin(status, t, width, height)` ger en rad `Text` per rad, ur
`StatusSnapshot` (egna instrument), aldrig något om fienden.
"""
from __future__ import annotations

from rich.text import Text

from sim.game import StatusSnapshot
from sim.fmt import kn

from . import instruments as ins
from .canvas import Canvas
from .central_render import PALETTES
from .placards import PLATE_STYLE

MIN_W, MIN_H = 40, 14
WALK_TOTAL_S = 40
CABIN_RU = "КАЮТА КОМАНДИРА"

BG = "on #15110c"
WALL = "#4a3e2e on #15110c"
WOOD = "#8a6a40 on #15110c"
WOOD_DARK = "#5e4a2e on #15110c"
BLANKET = "#5a6a8a on #15110c"
PILLOW = "#c8c0a8 on #15110c"
SLEEPER = "#a09070 on #15110c"
LAMP = "bold #f0c060 on #15110c"
GLOW = "#6a5a30 on #15110c"
PAPER = "#d8c89a on #15110c"
DIM = "#6a5c48 on #15110c"
PHONE = "#7a7a6a on #15110c"
LAMP_OFF = "#3a3020 on #15110c"
LAMP_ON = "bold #ffaf00 on #15110c"
LAMP_RING = "bold #ff5f5f on #15110c"
FIGURE = "bold #e8dcc0 on #15110c"

PAL = dict(PALETTES["normal"], ring="#8a7a5a", needle="bold #f0e6c8", label="#6a5c48",
           hub="#c8b890")


def _plate(c: Canvas, w: int) -> None:
    s = f" {CABIN_RU} · kaptenens hytt "
    if len(s) > w - 2:
        s = f" {CABIN_RU} "
    c.text(0, max(0, (w - len(s)) // 2), s, PLATE_STYLE)


def _phone(c: Canvas, row: int, col: int, s: StatusSnapshot, t: float) -> None:
    """Snabbtelefonen «Каштан» på skottet vid kojen."""
    c.text(row, col, "┌──КАШТАН──┐", PHONE)
    c.text(row + 1, col, "│ ", PHONE)
    if s.phone == "ring":
        on = int(t * 4) % 2 == 0
        c.text(row + 1, col + 2, "●" if on else "○", LAMP_RING if on else LAMP_OFF)
        c.text(row + 1, col + 3, " ☎ RING ", LAMP_RING if on else PHONE)
    else:
        c.text(row + 1, col + 2, "●", LAMP_ON if s.phone == "lamp" else LAMP_OFF)
        c.text(row + 1, col + 3, " ▤ ▤ ▤  ", PHONE)
    c.put(row + 1, col + 11, "│", PHONE)
    c.text(row + 2, col, "└──────────┘", PHONE)


def _shelf(c: Canvas, row: int, col: int, width: int) -> None:
    """Bokhyllan med reglementen och kassaskåpet med de hemliga orderna."""
    books = "▐▌▐█▌▐▌█▐▌▐▌▐█"
    c.text(row, col, books[: max(4, width - 9)], WOOD)
    c.text(row + 1, col, "▔" * max(4, width - 9), WOOD_DARK)
    c.text(row - 1, col + width - 7, "┌СЕЙФ┐", PHONE)
    c.text(row, col + width - 7, "│ ◎ │", PHONE)
    c.text(row + 1, col + width - 7, "└───┘", PHONE)


def _bunk(c: Canvas, top: int, left: int, width: int, s: StatusSnapshot, t: float) -> None:
    """Kojen: ram, kudde och filt; kaptenen under filten när han sover."""
    width = max(12, width)
    c.text(top, left, "╔" + "═" * (width - 2) + "╗", WOOD)
    c.text(top + 3, left, "╚" + "═" * (width - 2) + "╝", WOOD)
    for r in (top + 1, top + 2):
        c.put(r, left, "║", WOOD)
        c.put(r, left + width - 1, "║", WOOD)
    in_bunk = s.command == "starpom" and s.captain_at == "cabin"
    c.text(top + 1, left + 1, "▓▓▓", PILLOW)
    if in_bunk:
        c.text(top + 1, left + 4, "◖", SLEEPER)
        c.text(top + 1, left + 5, "▒" * (width - 6), BLANKET)
        c.text(top + 2, left + 1, "▒" * (width - 2), BLANKET)
        if s.sleeping:                       # z z Z stiger från kudden
            phase = int(t * 1.5) % 3
            for i in range(3):
                if i <= phase:
                    c.put(top - 1 - i, left + 3 + 2 * i, "zzZ"[i], DIM)
    else:
        c.text(top + 2, left + width - 8, "▒▒▒▒▒▒", BLANKET)      # filten vikt


def _desk(c: Canvas, top: int, left: int, width: int) -> None:
    """Skrivbordet: nattlampan, sjökortsrullen och loggboken."""
    width = max(14, width)
    c.text(top, left + 1, "◠", LAMP)
    c.text(top + 1, left, "▔█▔", LAMP)
    for i in range(3, min(width, 10)):
        c.put(top + 1, left + i, "·", GLOW)
    c.text(top + 1, left + 4, "═══════◯", PAPER)
    c.text(top + 2, left, "▀" * width, WOOD)
    c.text(top + 3, left + 1, "▌", WOOD_DARK)
    c.text(top + 3, left + width - 2, "▐", WOOD_DARK)


def _walk(c: Canvas, w: int, h: int, s: StatusSnapshot, t: float) -> None:
    """Gången från hytten och lejdaren upp till centralen; kaptenen på väg."""
    mid = h // 2
    left, right = 3, w - 4
    c.text(mid - 2, left, "─" * (right - left), WALL)
    c.text(mid + 2, left, "─" * (right - left), WALL)
    c.text(mid - 1, left - 1, "▐", WOOD)
    c.text(mid, left - 1, "▐", WOOD)
    c.text(mid + 1, left - 1, "▐", WOOD)
    c.text(mid + 3, left - 2, "hytten", DIM)
    for x in range(left + 6, right - 6, 9):    # skott med dörrar
        c.put(mid - 1, x, "╥", WALL)
        c.put(mid + 1, x, "╨", WALL)
    lad = right - 3
    for r in range(1, mid + 2):                 # lejdaren upp till centralen
        c.text(r, lad, "╫", WOOD)
    c.text(1, lad - 6, "centralen", DIM)
    frac = 1.0 - min(1.0, s.walk_s / WALK_TOTAL_S)
    path = (lad - left - 2) + mid
    pos = int(frac * path)
    if pos <= lad - left - 2:
        col, row = left + 1 + pos, mid
    else:
        col, row = lad, mid - (pos - (lad - left - 2))
    stride = int(t * 4) % 2
    c.put(row - 1 if row > 1 else row, col, "●", FIGURE)
    c.put(row, col, "╫" if col == lad else ("╱" if stride else "╲"), FIGURE)
    c.text(h - 2, 2, f"På väg till centralen, {s.walk_s} s.", FIGURE)


def footer(s: StatusSnapshot) -> Text:
    t = Text()
    if s.command == "starpom":
        t.append(" СТАРПОМ ", style=PLATE_STYLE)
        t.append(" Starpom har befälet", style="bold #e0e0a0")
        t.append(f"   kurs {s.ordered_course:03.0f} · fart {kn(s.ordered_speed)} kn · "
                 f"djup {s.ordered_depth:.0f} m", style="#a09070")
        if s.sleeping:
            t.append("   · ni sover", style="dim")
    else:
        t.append(" Ni har befälet.", style="bold")
    return t


def render_cabin(s: StatusSnapshot, t: float, width: int, height: int) -> list[Text]:
    w, h = max(MIN_W, width), max(MIN_H, height)
    c = Canvas(w, h, BG)
    _plate(c, w)
    if s.captain_at == "walking":
        _walk(c, w, h, s, t)
        return c.lines()[:height]
    # skottets plåtfogar
    for r in range(2, h - 1, 4):
        c.text(r, 0, "·" + " " * (w - 2) + "·", WALL)
    # repeatrar och skeppsklocka på skottet till höger
    rr = max(4, min((h - 6) // 2 + 1, (w // 2) // 6))
    cols = 2 * rr
    n = 3 if w >= 3 * cols + 16 else 2
    x0 = w - n * (cols + 1) - 1
    dials = [ins.gyro(s.course, None, PAL), ins.depth_gauge(s.depth, None, PAL),
             ins.clock_face(s.clock, PAL)][:n]
    dials[0].title, dials[1].title = "KURS", "DJUP"
    for i, d in enumerate(dials):
        ins.draw_dial(c, 2, x0 + i * (cols + 1), rr, cols, d, PAL)
    # telefonen och kojen till vänster, skrivbordet under repeatrarna
    _phone(c, 2, 2, s, t)
    bunk_w = min(32, max(14, w // 2 - 4), x0 - 3) if x0 > 20 else max(14, w // 2 - 2)
    if x0 - 18 >= 24:
        _shelf(c, 4, 18, min(30, x0 - 20))
    _bunk(c, h - 6, 2, bunk_w, s, t)
    desk_left = max(bunk_w + 5, x0)
    if desk_left + 14 < w:
        _desk(c, h - 5, desk_left, w - desk_left - 2)
    return c.lines()[:height]
