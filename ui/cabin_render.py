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

from rich.text import Text

from sim.game import StatusSnapshot
from sim.fmt import kn

from . import instruments as ins
from .canvas import Braille, Canvas
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
                s: StatusSnapshot) -> None:
    """Hänger sakerna från vänster i prioritetsordning, lite olika höjd, tills platsen tar slut."""
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
        if item[0][0].startswith("╔"):          # medaljerna under diplomet
            m = _medals()
            if row + ih + len(m) - 1 <= bottom:
                for i, (line, style) in enumerate(m):
                    c.text(row + ih + i, col + 1, line, style)
        col += iw + 2


def _far_wall(c: Canvas, g: _Room, s: StatusSnapshot) -> None:
    """Det bortre skottet: ram, skrivbordet, repeatrarna, kassaskåpet och hans saker."""
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
            c.put(desk - 3, cap + 2, "┬", PHONE)
            c.text(desk - 2, cap, "▄█", CAP)
            c.put(desk - 2, cap + 2, "★", MEDAL)
            c.text(desk - 2, cap + 3, "█▄", CAP)
            c.text(desk - 1, cap, "▀▀▀▀▀", CAP_BAND)
    # saker på skrivbordet: nattlampan, loggboken, teglaset, schackpartiet, klockan
    on_desk = [(fl + 3, "◠", LAMP), (fl + 6, "▤▤", PAPER), (fl + 10, "▯", TEA),
               (fl + 11, ")", TEA), (fl + 14, "♜♞♟", PAPER)]
    clock = f"◷ {(s.clock // 3600) % 24:02d}:{(s.clock // 60) % 60:02d}"
    for col, text, style in on_desk:
        if col + len(text) < x0 - 2:
            c.text(desk - 1, col, text, style)
    clock_col = min(x0 - 2 - len(clock), safe - 9 - len(clock)) if inner > 30 else -1
    if clock_col > fl + 18:
        c.text(desk - 1, clock_col, clock, PAPER)
    # de personliga sakerna mellan skottets kant och repeatrarna
    _wall_items(c, fl + 2, x0 - 2, ft + 1, desk - 2, s)


def _door(c: Canvas, g: _Room) -> None:
    """Dörren längst bort på styrbords skott, med ljus från gången under."""
    top, bot = g.edge("tr"), g.edge("br")
    x_far = g.far["tr"][0] + 3
    x_near = _lerp(x_far, g.near["tr"][0], 0.28)
    c0, c1 = int(x_far // 2), int(x_near // 2)
    if c1 - c0 < 3:
        return
    spans = []
    for col in range(c0, c1 + 1):
        x = 2 * col + 1
        yc, yf = _on_line(*top, x), _on_line(*bot, x)
        r0 = int((yc + 0.12 * (yf - yc)) // 4)
        r1 = min(g.h - 1, int((yf - 0.02 * (yf - yc)) // 4))
        spans.append((col, r0, r1))
    for col, r0, r1 in spans:
        for r in range(r0, r1 + 1):
            c.put(r, col, "░", DOOR)
        c.put(r0, col, "▁", DOOR_EDGE)
        c.put(r1, col, "▔", STRIP)                     # ljuset från gången
    for col, r0, r1 in (spans[0], spans[-1]):
        for r in range(r0 + 1, r1):
            c.put(r, col, "▏" if col == spans[0][0] else "▕", DOOR_EDGE)
    # ventilationsgaller och regeln vid närmaste kanten
    col, r0, r1 = spans[len(spans) // 2]
    vent = r0 + max(1, (r1 - r0) // 5)
    for cc, a, z in spans[1:-1]:
        if a < vent < z:
            c.put(vent, cc, "≡", DOOR_EDGE)
    col, r0, r1 = spans[-2]
    c.put((r0 + r1) // 2, col, "╼", PHONE)


def _blanket(c: Canvas, g: _Room, t: float) -> None:
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
    hr = g.h - 2
    hc = round(_lerp(foot_r, rail_bottom, 0.85)) - 9
    if hc > 4:
        c.text(hr, hc, "▗▄▄▖", HAND)
        c.text(hr + 1, hc - 1, "▐████▌", HAND)
        c.put(hr + 1, hc + 5, "▘", HAND_DARK)


def _room(c: Canvas, s: StatusSnapshot, t: float) -> None:
    g = _Room(c.w, c.h)
    _room_lines(c, g)
    _door(c, g)
    _far_wall(c, g, s)
    # taklampan mitt i rummet
    lr = max(1, (1 + g.ft) // 2)
    lc = int(g.vp[0] // 2)
    c.put(lr - 1, lc, "│", PIPE)
    c.put(lr, lc, "◓", LAMP)
    _blanket(c, g, t)
    _phone(c, 2, 1, s, t)                               # på skottet vid kojen, inom räckhåll


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


def render_cabin(s: StatusSnapshot, t: float, width: int, height: int) -> list[Text]:
    w, h = max(MIN_W, width), max(MIN_H, height)
    c = Canvas(w, h, BG)
    if s.captain_at == "walking":
        _plate(c, w)
        _walk(c, w, h, s, t)
        return c.lines()[:height]
    if w >= ROOM_MIN_W and h >= ROOM_MIN_H:
        _room(c, s, t)
    else:
        _flat(c, s, t)
    _plate(c, w)
    return c.lines()[:height]
