"""Kaptenens hytt (каюта командира) som bild.

Från `ROOM_MIN_W` × `ROOM_MIN_H` ses hytten från kudden i perspektiv: taket med rörstråk,
det bortre skottet med skrivbordet, repeatrarna och kassaskåpet, dörren längst bort på
styrbords skott med ljuset från gången under, filten över benen och handen nederst, och
«Каштан» inom räckhåll till vänster. I mindre fönster den enkla bilden:

Kojen, skrivbordet med sjökortsrullen och nattlampan, repeatrarna för kurs och djup
och skeppsklockan på skottet (braille, `ui/instruments.py`), och snabbtelefonen «Каштан»
med sin lampa: släckt, lyser (något att veta) eller blinkar rött (det ringer). Inga
kontakter syns härifrån; vill kaptenen veta mer får han ringa centralen.

Medan kaptenen är på väg till centralen visas gången och lejdaren, och han själv på väg.

Ren funktion: `render_cabin(status, t, width, height)` ger en rad `Text` per rad, ur
`StatusSnapshot` (egna instrument), aldrig något om fienden.
"""
from __future__ import annotations

import math
import re
import textwrap

from rich.text import Text

from sim.game import StatusSnapshot
from sim.fmt import kn, kn_dir

from . import instruments as ins
from .canvas import Braille, Canvas
from .central_render import PALETTES
from .placards import PLATE_STYLE

MIN_W, MIN_H = 40, 14
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


def footer(s: StatusSnapshot) -> Text:
    t = Text()
    if s.command == "starpom":
        t.append(" СТАРПОМ ", style=PLATE_STYLE)
        t.append(" Starpom har befälet", style="bold #e0e0a0")
        t.append(f"   kurs {s.ordered_course:03.0f} · fart {kn_dir(s.ordered_speed, s.ordered_astern)} kn · "
                 f"djup {s.ordered_depth:.0f} m", style="#a09070")
        if s.sleeping:
            t.append("   · ni sover", style="dim")
    else:
        t.append(" Ni har befälet.", style="bold")
    return t


def call_line(s: StatusSnapshot, now: float) -> Text:
    """Raden ovanför rapporterna: telefonen ringer, eller förslaget som väntar på ert beslut."""
    t = Text()
    if s.command != "starpom":
        return t
    if s.phone == "ring":
        bright = int(now * 2) % 2 == 0
        t.append(" ☎ RINGER ", style="bold #15110c on #e0b030" if bright else "bold #e0b030 on #3a2a10")
        t.append("  Snabbtelefonen från centralen – Enter svarar", style="bold #e0c070")
    elif s.decision:
        t.append(" ERT BESLUT ", style=PLATE_STYLE)
        t.append(f"  {s.decision}. ", style="bold #e0e0a0")
        t.append("ja", style="bold #a0e0a0")
        t.append(" verkställer · ", style="#a09070")
        t.append("nej", style="bold #e0a0a0")
        t.append(" avslår", style="#a09070")
    elif s.phone == "lamp":
        t.append("  Lampan på snabbtelefonen lyser – lägesrapport ringer centralen", style="#c0a060")
    return t


# --- rummet sett från kudden ----------------------------------------------------------
ROOM_MIN_W, ROOM_MIN_H = 64, 18
EDGE = "#6a5a42 on #15110c"
SEAM = "#3a3226 on #15110c"
PIPE = "#7a6e5a on #15110c"
DOOR = "#4a3a24 on #15110c"
DOOR_EDGE = "#8a6a40 on #15110c"
STRIP = "#c0903a on #15110c"
FLOOR = "#2e261c on #15110c"
BLANKET_SH = ("#2e3648 on #15110c", "#46526e on #15110c", "#6a7a9c on #15110c")
HAND = "#b89a78 on #15110c"
HAND_DARK = "#7a6450 on #15110c"


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _on_line(p0: tuple[float, float], p1: tuple[float, float], x: float) -> float:
    """y på linjen p0–p1 vid x (prickar)."""
    (x0, y0), (x1, y1) = p0, p1
    if x1 == x0:
        return y0
    return _lerp(y0, y1, (x - x0) / (x1 - x0))


class _Room:
    """Rummets geometri: det bortre skottet och linjerna mot fyra hörn nära ögat."""

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.fl, self.fr = round(w * 0.17), round(w * 0.74)   # bortre skottet, kolumner
        self.ft, self.fb = max(3, round(h * 0.17)), round(h * 0.60)
        W, H = 2 * w - 1, 4 * h - 1
        self.near = {"tl": (0.0, 4.0), "tr": (float(W), 4.0), "bl": (0.0, float(H)),
                     "br": (float(W), float(H))}
        self.far = {"tl": (2.0 * self.fl, 4.0 * self.ft), "tr": (2.0 * self.fr + 1, 4.0 * self.ft),
                    "bl": (2.0 * self.fl, 4.0 * self.fb + 3), "br": (2.0 * self.fr + 1, 4.0 * self.fb + 3)}
        self.vp = (_lerp(self.far["tl"][0], self.far["tr"][0], 0.45),
                   _lerp(self.far["tl"][1], self.far["bl"][1], 0.5))

    def edge(self, corner: str) -> tuple[tuple[float, float], tuple[float, float]]:
        return self.near[corner], self.far[corner]

    def toward_vp(self, x: float, y: float, y_stop: float) -> tuple[float, float]:
        """Punkten där linjen från (x, y) mot flyktpunkten når höjden y_stop."""
        vx, vy = self.vp
        f = (y_stop - y) / (vy - y) if vy != y else 0.0
        return _lerp(x, vx, f), y_stop


def _room_lines(c: Canvas, g: _Room) -> None:
    """Hörnlinjerna, takets rör och skottens plåtfogar i braille."""
    b = Braille(g.w, g.h)
    for corner in ("tl", "tr", "bl", "br"):
        (x0, y0), (x1, y1) = g.edge(corner)
        b.line(x0, y0, x1, y1, EDGE, prio=2)
    # rörstråk i taket mot flyktpunkten, två och två
    y_far = g.far["tl"][1]
    for f, gap in ((0.30, 3.0), (0.60, 2.0), (0.86, 4.0)):
        for dx in (0.0, gap):
            x = _lerp(0, g.near["tr"][0], f) + dx
            x1, y1 = g.toward_vp(x, 4.0, y_far)
            b.line(x, 4.0, x1, y1, PIPE, prio=1)
    # plåtfogar på sidoskotten
    for side in ("l", "r"):
        top, bot = g.edge("t" + side), g.edge("b" + side)
        x_near, x_far = top[0][0], top[1][0]
        for f in ((0.55,) if side == "l" else (0.45,)):
            x = _lerp(x_near, x_far, f)
            b.line(x, _on_line(*top, x), x, _on_line(*bot, x), SEAM)
    # durkplåtarnas fogar mellan kojen och styrbords skott
    y_floor = g.far["br"][1]
    for f in (0.86, 0.94):
        x = _lerp(0, g.near["br"][0], f)
        x1, y1 = g.toward_vp(x, g.near["br"][1], y_floor)
        b.line(x, g.near["br"][1], x1, y1, FLOOR)
    b.blit(c, 0, 0)


# personliga saker på skottet: (rader, stilar per rad); ritas bara där de får plats
FRAME = "#a08850 on #15110c"
PHOTO = "#9a9480 on #15110c"
PHOTO_DARK = "#5a5648 on #15110c"
SEA = "#4a5a6a on #15110c"
RIBBON = "#b03a2e on #15110c"
MEDAL = "bold #e0b040 on #15110c"
CAL = "#d8d0b8 on #15110c"
CAL_RED = "bold #c04030 on #15110c"
TEA = "#c0903a on #15110c"
CAP = "#2a3040 on #15110c"
CAP_BAND = "#1a1a1a on #15110c"

MONTH_RU = "ОКТЯБРЯ"
WEEKDAY_RU = ["ПОНЕДЕЛЬНИК", "ВТОРНИК", "СРЕДА", "ЧЕТВЕРГ", "ПЯТНИЦА", "СУББОТА",
              "ВОСКРЕСЕНЬЕ"]


def _calendar(day: int, rows: int = 6) -> list[tuple[str, str]]:
    """Rivkalendern (отрывной календарь): dagens blad, söndagar i rött. Kortare om
    höjden inte räcker: först utan året, sedan utan veckodagen."""
    import datetime
    if not 1 <= day <= 31:
        return []
    wd = datetime.date(1962, 10, day).weekday()
    red = CAL_RED if wd == 6 else CAL
    name = WEEKDAY_RU[wd]
    w = max(9, len(name) + 2)
    body = [("│" + "1962".center(w) + "│", CAL),
            ("│" + f"{day}".center(w) + "│", red),
            ("│" + MONTH_RU.center(w) + "│", CAL),
            ("│" + name.center(w) + "│", red)]
    if rows < 6:
        body = body[1:]
    if rows < 5:
        body = body[:2]
    return [("┌" + "─" * w + "┐", FRAME)] + body + [("└" + "▔" * w + "┘", FRAME)]


def _boat_photo() -> list[tuple[str, str]]:
    """Fotot av hans första ubåt, en Projekt 613 vid kaj i Poljarnyj."""
    return [("┌──────────┐", FRAME),
            ("│    ▗▅▖   │", PHOTO),
            ("│▁▂▄▅▅██▅▅▄│", PHOTO),
            ("│≈≈≈≈≈≈≈≈≈≈│", SEA),
            ("└─ Пр.613 ─┘", FRAME)]


def _diploma() -> list[tuple[str, str]]:
    """Examensbeviset från sjökrigsskolan Frunze i Leningrad."""
    return [("╔════════╗", FRAME),
            ("║ ДИПЛОМ ║", PAPER),
            ("║  ВВМУ  ║", PAPER),
            ("║ ≈≈≈≈ ✪ ║", PAPER),
            ("╚════════╝", FRAME)]


def _family() -> list[tuple[str, str]]:
    """Hustrun och dottern."""
    return [("┌─────┐", FRAME),
            ("│ ●  •│", PHOTO),
            ("│▟█▙▗▙│", PHOTO_DARK),
            ("└─────┘", FRAME)]


def _medals() -> list[tuple[str, str]]:
    """Röda stjärnans orden och medaljen «За боевые заслуги» på en filtlapp."""
    return [("▐▀▌ ▐▀▌", RIBBON), (" ★   ✠ ", MEDAL)]


def _hang(c: Canvas, row: int, col: int, item: list[tuple[str, str]]) -> None:
    for i, (line, style) in enumerate(item):
        c.text(row + i, col, line, style)
    if item and item[0][1] == RIBBON:        # banden i rött, medaljerna i guld
        c.text(row + 1, col, item[1][0], MEDAL)


def _wall_items(c: Canvas, left: int, right: int, top: int, bottom: int,
                s: StatusSnapshot) -> int:
    """Hänger sakerna från vänster i prioritetsordning, lite olika höjd, tills platsen tar slut.
    Ger den nedersta raden som används (top − 1 om inget hängdes)."""
    lowest = top - 1
    items = []
    if s.order_day:
        day = s.order_day + s.clock // 86400
        items.append((_calendar(day, bottom - top + 1), 0))
    items += [(_boat_photo(), 1), (_diploma(), 0), (_family(), 2)]
    col = left
    for item, drop in items:
        if not item:
            continue
        iw, ih = max(len(line) for line, _ in item), len(item)
        if col + iw > right:
            break
        row = top + min(drop, max(0, bottom - top + 1 - ih))
        if row + ih - 1 > bottom:
            continue
        _hang(c, row, col, item)
        lowest = max(lowest, row + ih - 1)
        if item[0][0].startswith("╔"):          # medaljerna under diplomet
            m = _medals()
            if row + ih + len(m) - 1 <= bottom:
                for i, (line, style) in enumerate(m):
                    c.text(row + ih + i, col + 1, line, style)
                lowest = max(lowest, row + ih + len(m) - 1)
        col += iw + 2
    return lowest


CHART_MIN_W, CHART_MIN_H = 16, 6       # mindre än så: inget kort på väggen (ram inräknad)
CHART_SEA = "#4a5a6a on #15110c"
CHART_LAND = "#7a6a4a on #15110c"
CHART_INK = "#b8a888 on #15110c"
CHART_RED = "bold #c04030 on #15110c"
CHART_ITEMS = {                         # kunskapens kortelement -> tecken och färg på väggkortet
    "own": ("@", CHART_RED), "contact": ("◆", CHART_RED), "merchant": ("◇", PHOTO),
    "waypoint": ("⊕", CHART_INK), "station": ("⊕", CHART_INK),
}


def _wall_chart(c: Canvas, chart, top: int, left: int, bottom: int, right: int) -> None:
    """Navigatörens kort över området, nålat på skottet: land, kust, besticket, vi och
    kontakterna som tecken, utan text (kunskapen, `Game.chart()`). Norr uppåt."""
    if chart is None:
        return
    cols = min(right - left - 1, 2 * (bottom - top - 1))       # en ruta är dubbelt så hög
    rows = cols // 2
    if cols < CHART_MIN_W or rows + 2 < CHART_MIN_H:
        return
    left += (right - left - 1 - cols) // 2
    title = " КАРТА "
    c.text(top, left, "┌" + title + "─" * (cols - len(title)) + "┐", FRAME)
    for r in range(rows):
        c.text(top + 1 + r, left, "│" + " " * cols + "│", FRAME)
        for k in range(1, cols + 1, 6):
            c.put(top + 1 + r, left + k, "˙" if r % 3 == 1 else " ", CHART_SEA)
    c.text(top + 1 + rows, left, "└" + "─" * cols + "┘", FRAME)
    size = max(chart.size_nm, 1e-6)

    def cell(x: float, y: float):
        col, row = int(x / size * cols), int((1 - y / size) * rows)
        if 0 <= col < cols and 0 <= row < rows:
            return top + 1 + row, left + 1 + col
        return None

    for it in chart.drawables:
        style = getattr(it, "style", None)
        if hasattr(it, "points") and style in ("coast", "track"):
            for x, y in it.points:
                if (p := cell(x, y)) is not None:
                    c.put(*p, "·", CHART_INK if style == "track" else CHART_LAND)
        elif hasattr(it, "symbol") and style == "land":
            if (p := cell(it.x, it.y)) is not None:
                c.put(*p, "░", CHART_LAND)
    for it in chart.drawables:          # märkena ovanpå, vi sist
        style = getattr(it, "style", None)
        if hasattr(it, "symbol") and style in CHART_ITEMS and style != "own":
            if (p := cell(it.x, it.y)) is not None:
                c.put(*p, *CHART_ITEMS[style])
    if (p := cell(*chart.own)) is not None:
        c.put(*p, *CHART_ITEMS["own"])


def _clinometer(c: Canvas, row: int, col: int, sway: float) -> None:
    """Krängningsmätaren (кренометр): en pendel som visar krängningen, ur samma svängning
    som mössan (`sway_of`), ungefär 6° per kolumns utslag."""
    deg = round(6 * sway)
    pos = 4 + max(-4, min(4, round(sway * 1.5)))
    scale = list("╵ ╵ ┃ ╵ ╵")
    c.text(row, col, "╭─ КРЕН ─╮", FRAME)
    c.text(row + 1, col, "│" + "".join(scale) + "│", DIM)
    c.put(row + 1, col + 1 + pos, "▼", LAMP)
    c.text(row + 2, col, "╰" + f" {abs(deg):2d}° ".center(9, "─") + "╯", FRAME)


def _far_wall(c: Canvas, g: _Room, s: StatusSnapshot, sway: float = 0.0, chart=None) -> dict:
    """Det bortre skottet: ram, skrivbordet, repeatrarna, kassaskåpet och hans saker.
    Ger platserna för det som lever (`desk_lamp`, `tea`, `cap`). Mössan svänger med `sway`."""
    spots: dict = {}
    fl, fr, ft, fb = g.fl, g.fr, g.ft, g.fb
    c.text(ft, fl, "┌" + "─" * (fr - fl - 1) + "┐", EDGE)
    c.text(fb, fl, "└" + "─" * (fr - fl - 1) + "┘", EDGE)
    for r in range(ft + 1, fb):
        c.put(r, fl, "│", EDGE)
        c.put(r, fr, "│", EDGE)
    inner = fr - fl - 1
    # skrivbordsskivan längs skottet
    desk = fb - 2
    c.text(desk, fl + 1, "▀" * inner, WOOD)
    c.put(fb - 1, fl + 2, "▌", WOOD_DARK)
    c.put(fb - 1, fr - 2, "▐", WOOD_DARK)
    # repeatrarna för kurs och djup högt upp till höger
    rows = max(4, min(7, desk - ft - 3))
    cols = max(2 * rows, 13)
    x0 = fr - 2 * (cols + 1)
    dials = [ins.gyro(s.course, None, PAL), ins.depth_gauge(s.depth, None, PAL)]
    dials[0].title, dials[1].title = "KURS", "DJUP"
    for i, d in enumerate(dials):
        ins.draw_dial(c, ft + 1, x0 + i * (cols + 1), rows, cols, d, PAL)
    # kassaskåpet vid skivan till höger, mössan på kroken bredvid
    safe = fr - 8
    if desk - 2 > ft + rows and inner > 30:
        c.text(desk - 2, safe, "┌СЕЙФ┐", PHONE)
        c.text(desk - 1, safe, "│ ◎  │", PHONE)
        cap = safe - 7
        if cap > x0 and desk - 3 > ft + rows:
            c.put(desk - 3, cap + 2, "┬", PHONE)       # kroken sitter fast, mössan svänger
            dx = max(-1, min(1, round(sway)))
            c.text(desk - 2, cap + dx, "▄█", CAP)
            c.put(desk - 2, cap + 2 + dx, "★", MEDAL)
            c.text(desk - 2, cap + 3 + dx, "█▄", CAP)
            c.text(desk - 1, cap + dx, "▀▀▀▀▀", CAP_BAND)
            spots["cap"] = (desk - 2, cap + 2)
    # saker på skrivbordet: nattlampan, loggboken, teglaset, schackpartiet, klockan
    on_desk = [(fl + 3, "◠", LAMP), (fl + 6, "▤▤", PAPER), (fl + 10, "▯", TEA),
               (fl + 11, ")", TEA), (fl + 14, "♜♞♟", PAPER)]
    clock = f"◷ {(s.clock // 3600) % 24:02d}:{(s.clock // 60) % 60:02d}"
    for col, text, style in on_desk:
        if col + len(text) < x0 - 2:
            c.text(desk - 1, col, text, style)
            if text == "◠":
                spots["desk_lamp"] = (desk - 1, col)
            elif text == "▯":
                spots["tea"] = (desk - 1, col)
    clock_col = min(x0 - 2 - len(clock), safe - 9 - len(clock)) if inner > 30 else -1
    if clock_col > fl + 18:
        c.text(desk - 1, clock_col, clock, PAPER)
    # de personliga sakerna mellan skottets kant och repeatrarna, kortet under dem
    lowest = _wall_items(c, fl + 2, x0 - 2, ft + 1, desk - 2, s)
    _wall_chart(c, chart, lowest + 2, fl + 2, desk - 2, x0 - 2)
    # krängningsmätaren under repeatrarna, om den ryms ovanför mössan
    clino = ft + 1 + rows + 1
    if clino + 2 < desk - 3 and x0 + 10 < fr:
        _clinometer(c, clino, x0 + (2 * (cols + 1) - 11) // 2, sway)
    return spots


CORRIDOR = "#f0d8a0 on #15110c"
CORRIDOR_DIM = "#a08860 on #15110c"
SHADOW = "#15110c on #15110c"
FIGURE_DARK = "#2a2218 on #15110c"


def _door_spans(g: _Room) -> list[tuple[int, int, int]]:
    """Dörrens kolumner med övre och nedre rad; den första vid gångjärnen (längst bort)."""
    top, bot = g.edge("tr"), g.edge("br")
    x_far = g.far["tr"][0] + 3
    x_near = _lerp(x_far, g.near["tr"][0], 0.28)
    c0, c1 = int(x_far // 2), int(x_near // 2)
    if c1 - c0 < 3:
        return []
    spans = []
    for col in range(c0, c1 + 1):
        x = 2 * col + 1
        yc, yf = _on_line(*top, x), _on_line(*bot, x)
        r0 = int((yc + 0.12 * (yf - yc)) // 4)
        r1 = min(g.h - 1, int((yf - 0.02 * (yf - yc)) // 4))
        spans.append((col, r0, r1))
    return spans


def _figure(c: Canvas, col: int, r0: int, r1: int) -> None:
    """En mörk gestalt i dörröppningen: huvud, axlar och kropp."""
    h = r1 - r0
    head = r0 + max(1, h // 6)
    c.put(head, col, "●", FIGURE_DARK)
    for r in range(head + 1, r1):
        c.put(r, col, "█", FIGURE_DARK)


def _door(c: Canvas, g: _Room, state: str | None = None, t: float = 0.0) -> list:
    """Dörren längst bort på styrbords skott, med ljus från gången under.

    `steps`: någon står utanför, fötternas skuggor i ljusstrimman. `ajar`: dörren på glänt
    vid regeln, ordonnansen i springan."""
    spans = _door_spans(g)
    if not spans:
        return spans
    n = len(spans)
    gap = max(2, n // 3) if state == "ajar" else 0
    leaf = spans[: n - gap]
    opening = spans[n - gap:]
    for col, r0, r1 in leaf:
        for r in range(r0, r1 + 1):
            c.put(r, col, "░", DOOR)
        c.put(r0, col, "▁", DOOR_EDGE)
        c.put(r1, col, "▔", STRIP)                     # ljuset från gången
    for col, r0, r1 in opening:                         # gången bortom: ljus, en lampa, durken
        for r in range(r0, r1 + 1):
            c.put(r, col, "▓" if r < r1 - (r1 - r0) // 4 else "▒", CORRIDOR)
        c.put(r0, col, "▁", DOOR_EDGE)
    if state == "ajar" and opening:
        col, r0, r1 = opening[len(opening) // 2]
        _figure(c, col, r0, r1)
    if leaf:
        first, last = leaf[0], leaf[-1]
        for col, r0, r1 in (first, last):
            for r in range(r0 + 1, r1):
                c.put(r, col, "▏" if col == first[0] else "▕", DOOR_EDGE)
        inner = leaf[1:-1]
        if inner:
            col, r0, r1 = inner[len(inner) // 2]
            vent = r0 + max(1, (r1 - r0) // 5)
            for cc, a, z in inner:
                if a < vent < z:
                    c.put(vent, cc, "≡", DOOR_EDGE)
        if state is None or state == "steps":
            col, r0, r1 = spans[-2]
            c.put((r0 + r1) // 2, col, "╼", PHONE)
    if state == "steps":                                 # två fötter skuggar strimman, han väger
        shift = int(t * 1.5) % 2
        for k in (n // 3, n // 3 + 2):
            col, r0, r1 = spans[min(n - 1, k + shift)]
            c.put(r1, col, "▔", SHADOW)
    return spans


def _spill(c: Canvas, g: _Room, spans: list, state: str | None) -> None:
    """Ljuset från gången faller in på durken genom öppningen."""
    if state != "ajar" or not spans:
        return
    n = len(spans)
    lit = spans[n - max(2, n // 3):]
    (ca, _, ra), (cb, _, rb) = lit[0], lit[-1]
    start = max(ra, rb) + 1
    for r in range(start, g.h):
        f = (r - start + 1) / max(1, g.h - start)
        left = round(_lerp(ca, ca - 4, f))
        right = round(_lerp(cb, min(g.w - 1, cb + 6), f))
        for col in range(left, right + 1):
            if 0 <= col < g.w and (c.blank(r, col) or 0x2800 <= ord(c.cells[r][col][0]) <= 0x28FF):
                c.put(r, col, "░" if f > 0.5 else "▒", CORRIDOR_DIM)


def _blanket(c: Canvas, g: _Room, t: float, breath: float = 0.0) -> None:
    """Kojen och filten över benen, sett från kudden: fotänden borta, knäna och handen."""
    top = g.fb + 1
    foot_l, foot_r = g.fl + 1, round(_lerp(g.fl, g.fr, 0.62))
    rail_bottom = round(g.w * 0.80)
    rows = g.h - top
    if rows < 3:
        return
    left_floor = g.edge("bl")
    # fotänden
    c.text(top, foot_l, "▄" * (foot_r - foot_l + 1), WOOD)
    for i, r in enumerate(range(top + 1, g.h)):
        f = (i + 1) / rows
        right = round(_lerp(foot_r, rail_bottom, f))
        left = max(0, int(_lerp(foot_l, 0, min(1.0, f * 1.6))))
        mid = (left + right) / 2
        width = max(1, right - left)
        for col in range(left, right):
            u = (col - mid) / width                     # −0,5 … 0,5 över kojen
            feet = max(0.0, 1 - (f / 0.25) ** 2) * max(0.0, 1 - (abs(abs(u) - 0.16) / 0.12) ** 2)
            knees = max(0.0, 1 - ((f - 0.55) / 0.22) ** 2) * max(0.0, 1 - (abs(abs(u) - 0.17) / 0.17) ** 2)
            fold = 0.25 * (1 - min(1.0, abs(u) / 0.5))
            v = 0.15 + fold + 0.7 * max(feet, knees)
            shade = 2 if v > 0.62 else (1 if v > 0.32 else 0)
            c.put(r, col, "▓▒░"[2 - shade] if shade else "░", BLANKET_SH[shade])
        c.put(r, right, "▐" if f < 0.5 else "█", WOOD)  # kojens kant
        if right + 1 < g.w:
            c.put(r, right + 1, "▌", WOOD_DARK)
    # handen på filten nära ögat
    hr = g.h - 2 - (1 if breath > 0.6 else 0)        # bröstet häver sig, handen följer med
    hc = round(_lerp(foot_r, rail_bottom, 0.85)) - 9
    if hc > 4:
        c.text(hr, hc, "▗▄▄▖", HAND)
        c.text(hr + 1, hc - 1, "▐████▌", HAND)
        c.put(hr + 1, hc + 5, "▘", HAND_DARK)
        if hr + 2 < g.h:
            c.text(hr + 2, hc - 1, "▀▀▀▀▀▀", BLANKET_SH[2])


# --- liv och ljus ----------------------------------------------------------------------
LID = "#050403 on #050403"
LID_EDGE = "#2a2018 on #050403"
DUST = "#8a7a60 on #15110c"
HAZE = "#4a463e on #15110c"
SPLASH = "#c0903a on #15110c"
BREATH_S = 5.0                     # ett andetag, sekunder (sovande)
_HEX = re.compile(r"#([0-9a-fA-F]{6})")


def _hash(*xs: int) -> float:
    """Fast brus 0–1 ur heltal (ingen slump: samma bild varje gång)."""
    h = 2166136261
    for x in xs:
        h = ((h ^ (x & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return (h % 10007) / 10007.0


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def sway_of(s: StatusSnapshot, t: float) -> float:
    """Hur långt det som hänger svänger ut (kolumner, + åt höger).

    Jagade: sjunkbomberna skakar båten. Nära ytan rullar sjön (havsbruset). I en gir
    kränger båten och det som hänger står snett mot rummet."""
    shake = 1.6 * math.sin(t * 2.3) * (0.6 + 0.4 * math.sin(t * 0.7)) if s.hunted else 0.0
    roll = 1.4 * _clip((s.sea_noise - 48) / 24) * _clip(1 - s.depth / 30) * math.sin(t * 2 * math.pi / 8)
    turn = ((s.ordered_course - s.course + 540) % 360) - 180
    heel = 1.2 * _clip(abs(turn) / 30) * (1 if turn > 0 else -1) if abs(turn) > 2 else 0.0
    return shake + roll + heel


def lids_of(s: StatusSnapshot, t: float) -> float:
    """Hur slutna ögonen är (0 öppna, 1 slutna). Sover han är de nästan slutna och glider
    med andningen; ringer telefonen slår han upp dem (han måste se telefonen)."""
    if not s.sleeping or s.phone == "ring" or getattr(s, "door", None):
        return 0.0
    return 0.86 + 0.06 * math.sin(t * 2 * math.pi / BREATH_S)


def _light_at(g: _Room, s: StatusSnapshot, t: float, spots: dict):
    """Ljusets styrka och färgton per ruta: (r, c) -> (gånger, ton, tonens andel)."""
    lamps = []
    if s.night or s.sleeping:
        base = 0.28 if s.sleeping else 0.42             # taklampan släckt
        if "desk_lamp" in spots and not s.sleeping:     # nattlampan lyser på skrivbordet
            lamps.append((spots["desk_lamp"], 9.0, 1.0, (240, 192, 96), 0.25))
    else:
        base = 0.92
    phone = (3, 3)
    if s.phone == "ring":
        on = int(t * 4) % 2 == 0
        if on:
            lamps.append((phone, 24.0, 0.9, (255, 60, 50), 0.9))
    elif s.phone == "lamp":
        lamps.append((phone, 6.0, 0.5, (255, 175, 0), 0.35))
    if "door" in spots:                                 # gångens ljus genom dörren
        lamps.append((spots["door"], 18.0, 0.4, (255, 228, 170), 0.3))
    dim = 1.0 - 0.55 * _clip(s.smoke)

    def light(r: int, c: int) -> tuple[float, tuple[int, int, int] | None, float]:
        k, tone, amount = base, None, 0.0
        for (lr, lc), radius, gain, color, tint in lamps:
            d = math.hypot((r - lr) * 2.0, c - lc) / radius
            if d < 1.0:
                f = 1 - d
                k += gain * f
                if f * tint > amount:
                    tone, amount = color, f * tint
        far = g.ft <= r <= g.fb and g.fl <= c <= g.fr
        k *= dim * (1 - 0.25 * _clip(s.smoke) if far else 1.0)
        return min(1.15, k), tone, amount
    return light


def _restyle(style: str, k: float, tone, amount: float) -> str:
    m = _HEX.search(style)
    if not m:
        return style
    v = int(m.group(1), 16)
    rgb = [(v >> 16) & 255, (v >> 8) & 255, v & 255]
    if tone is not None and amount > 0:
        rgb = [x + (tc - x) * amount for x, tc in zip(rgb, tone)]
    rgb = [max(0, min(255, round(x * k))) for x in rgb]
    return style[:m.start()] + "#%02x%02x%02x" % tuple(rgb) + style[m.end():]


def _shade(c: Canvas, light) -> None:
    """Färga om varje rutas tecken efter ljuset (bakgrunden lämnas)."""
    cache: dict = {}
    for r in range(c.h):
        row = c.cells[r]
        for col in range(c.w):
            ch, st = row[col]
            if ch == " ":
                continue
            k, tone, amount = light(r, col)
            key = (st, round(k, 2), tone, round(amount, 2))
            if key not in cache:
                cache[key] = _restyle(st, *key[1:])
            row[col] = (ch, cache[key])


def _dust_and_haze(c: Canvas, g: _Room, s: StatusSnapshot, t: float) -> None:
    """Damm som faller från rören när sjunkbomberna slår, dis när det luktar rök."""
    if s.hunted:
        for i in range(10):
            col = int(_hash(i, 7) * (c.w - 2)) + 1
            fall = (t * (2.0 + 2.0 * _hash(i, 3)) + 30 * _hash(i, 11)) % (g.fb + 4)
            r = 1 + int(fall)
            if 1 <= r < g.fb and c.blank(r, col):
                c.put(r, col, "·" if _hash(i, r) > 0.3 else "˙", DUST)
    if s.smoke > 0.05:
        step = int(t * 0.8)                              # diset driver långsamt
        for r in range(1, c.h):
            for col in range(c.w):
                n = _hash(r, col + step, 5)
                if n < 0.25 * _clip(s.smoke) and c.blank(r, col):
                    c.put(r, col, "░" if n < 0.1 * s.smoke else "·", HAZE)


def _lids(c: Canvas, closed: float) -> None:
    """Ögonlocken: mörkret uppifrån och nedifrån, böjt som ett ögonlock."""
    if closed <= 0.02:
        return
    half = c.h / 2
    for col in range(c.w):
        u = (col - c.w / 2) / (c.w / 2)                  # −1 … 1
        bow = 1 - 0.35 * u * u                            # lockets kant högst på mitten
        top = closed * half * (1.15 - 0.15 * bow * 2 + 0.3 * u * u)
        bot = c.h - closed * half * (0.9 + 0.3 * u * u)
        for r in range(c.h):
            if r < top - 0.5 or r > bot + 0.5:
                c.put(r, col, "█", LID)
            elif r < top:
                c.put(r, col, "▀", LID_EDGE)
            elif r > bot:
                c.put(r, col, "▄", LID_EDGE)


def _room(c: Canvas, s: StatusSnapshot, t: float, chart=None) -> None:
    g = _Room(c.w, c.h)
    sway = sway_of(s, t)
    _room_lines(c, g)
    door = getattr(s, "door", None)
    spans = _door(c, g, door, t)
    spots = _far_wall(c, g, s, sway, chart)
    if spans and door == "ajar":
        col, r0, r1 = spans[-1]
        spots["door"] = ((r0 + r1) // 2, col)
    # taklampan mitt i rummet hänger i sin sladd och svänger
    lr = max(2, (1 + g.ft) // 2)
    lc = int(g.vp[0] // 2)
    dx = max(-2, min(2, round(sway * 1.3)))
    c.put(lr - 1, lc + (dx // 2), "│" if dx == 0 else ("╲" if dx > 0 else "╱"), PIPE)
    c.put(lr, lc + dx, "◓", LAMP if not (s.night or s.sleeping) else LAMP_OFF)
    # teglaset skvätter när det skakar
    if "tea" in spots and abs(sway) > 1.0 and int(t * 3) % 2 == 0:
        r, col = spots["tea"]
        c.put(r - 1, col, "'", SPLASH)
    breath = 0.5 + 0.5 * math.sin(t * 2 * math.pi / (BREATH_S if s.sleeping else 4.0))
    _blanket(c, g, t, breath)
    _phone(c, 2, 1, s, t)                               # på skottet vid kojen, inom räckhåll
    _spill(c, g, spans, door)
    _dust_and_haze(c, g, s, t)
    _shade(c, _light_at(g, s, t, spots))
    _lids(c, lids_of(s, t))


def _flat(c: Canvas, s: StatusSnapshot, t: float) -> None:
    """Liten hytt för små fönster: kojen, telefonen, repeatrarna och skrivbordet."""
    w, h = c.w, c.h
    for r in range(2, h - 1, 4):
        c.text(r, 0, "·" + " " * (w - 2) + "·", WALL)
    rr = max(4, min((h - 6) // 2 + 1, (w // 2) // 6))
    cols = 2 * rr
    n = 3 if w >= 3 * cols + 16 else 2
    x0 = w - n * (cols + 1) - 1
    dials = [ins.gyro(s.course, None, PAL), ins.depth_gauge(s.depth, None, PAL),
             ins.clock_face(s.clock, PAL)][:n]
    dials[0].title, dials[1].title = "KURS", "DJUP"
    for i, d in enumerate(dials):
        ins.draw_dial(c, 2, x0 + i * (cols + 1), rr, cols, d, PAL)
    _phone(c, 2, 2, s, t)
    bunk_w = min(32, max(14, w // 2 - 4), x0 - 3) if x0 > 20 else max(14, w // 2 - 2)
    if x0 - 18 >= 24:
        _shelf(c, 4, 18, min(30, x0 - 20))
    _bunk(c, h - 6, 2, bunk_w, s, t)
    desk_left = max(bunk_w + 5, x0)
    if desk_left + 14 < w:
        _desk(c, h - 5, desk_left, w - desk_left - 2)


CARD_BG = "#2a2218"
CARD_EDGE = f"#c0a060 on {CARD_BG}"
CARD_TEXT = f"#e0d8b0 on {CARD_BG}"
CARD_HEAD = f"bold #15110c on #e0b030"
CARD_WHO = f"bold #f0e6c8 on {CARD_BG}"
CARD_QUOTE = f"italic #c8bc98 on {CARD_BG}"
CARD_DIM = f"#a09070 on {CARD_BG}"
CARD_YES = f"bold #15110c on #a0e0a0"
CARD_NO = f"bold #15110c on #e0a0a0"


def _card(c: Canvas, head: str, body: list[tuple[str, str]], foot: list[tuple[str, str]],
          width: int = 76, low: bool = False) -> None:
    """En lapp över rummet, mitt i bilden (eller nederst, `low`): rubrik, rader och en rad med
    knappar (text, stil)."""
    w = min(c.w - 4, width)
    inner = w - 4
    rows = [("", CARD_TEXT)]
    for text, style in body:
        for line in (textwrap.wrap(text, inner) or [""]):
            rows.append((line, style))
    rows.append(("", CARD_TEXT))
    h = len(rows) + 3
    top = max(1, c.h - h - 1 if low else (c.h - h) // 2)
    left = (c.w - w) // 2
    c.text(top, left, "┌" + "─" * (w - 2) + "┐", CARD_EDGE)
    c.text(top, left + 2, f" {head} ", CARD_HEAD)
    for i, (line, style) in enumerate(rows[: max(1, c.h - top - 3)]):
        r = top + 1 + i
        c.text(r, left, "│" + " " * (w - 2) + "│", CARD_EDGE)
        c.text(r, left + 2, line, style)
    r = top + 1 + len(rows)
    c.text(r, left, "│" + " " * (w - 2) + "│", CARD_EDGE)
    col = left + 2
    for text, style in foot:
        c.text(r, col, text, style)
        col += len(text)
    c.text(r + 1, left, "└" + "─" * (w - 2) + "┘", CARD_EDGE)


def _decision_card(c: Canvas, s: StatusSnapshot, t: float) -> None:
    """Det kaptenen ska göra, mitt i bilden: svara i telefonen, eller ja/nej till förslaget."""
    if s.command != "starpom":
        return
    if s.phone == "ring":
        bright = int(t * 2) % 2 == 0
        _card(c, "☎ SNABBTELEFONEN RINGER", [("Starpom ringer från centralen.", CARD_TEXT)],
              [(" Enter ", CARD_YES if bright else CARD_HEAD), (" svarar", CARD_DIM)],
              width=40, low=True)
    elif s.decision:
        who, _, what = s.decision.partition(" föreslår ")
        body = [(f"{who} föreslår: {what}", CARD_WHO)]
        if s.decision_why:
            body.append((f"»{s.decision_why}«", CARD_QUOTE))
        body.append(("Starpom väntar på ert beslut.", CARD_DIM))
        _card(c, "ERT BESLUT", body,
              [("Skriv ", CARD_DIM), (" ja ", CARD_YES), (" verkställer · ", CARD_DIM),
               (" nej ", CARD_NO), (" avslår, sedan Enter", CARD_DIM)])


def render_cabin(s: StatusSnapshot, t: float, width: int, height: int,
                 chart=None) -> list[Text]:
    """chart: navigatörens kort (`Game.chart()`, kunskap) för kortet på väggen; utan det inget kort."""
    w, h = max(MIN_W, width), max(MIN_H, height)
    c = Canvas(w, h, BG)
    if w >= ROOM_MIN_W and h >= ROOM_MIN_H:
        _room(c, s, t, chart)
    else:
        _flat(c, s, t)
    _plate(c, w)
    _decision_card(c, s, t)
    return c.lines()[:height]
