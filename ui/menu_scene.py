"""Huvudmenyns bild: К-114 vid kaj i Poljarnyj en natt i oktober.

Ritas i braille (`canvas.Braille`, 2 × 4 prickar per ruta): stjärnor, fjällen på andra sidan
fjorden, kajen med en kran och en lampa, ubåten med tornet en tredjedel från fören och
snö som driver med vinden. Bara stämning: inget här läser spelet.

    render_scene(cols, rows, t)   rader (rich Text) för tiden t sekunder
"""
from __future__ import annotations

import math

from rich.text import Text

from .canvas import Braille, Canvas
from .menutext import BG, DIM, INK, RED

STAR = "#8a8470"
HILL = "#4a4438"
SEA = "#2c4050"
HULL = "#5a534c"
HULL_TOP = "#8a8278"
PIER = "#5a5248"
SNOW = "#d8d0c0"
LAMP = "#e8c060"

MIN_COLS, MIN_ROWS = 30, 6


def _hash(i: int, salt: int = 0) -> float:
    """Fast slump i [0, 1) per föremål, utan random-modulen."""
    x = math.sin(i * 12.9898 + salt * 78.233) * 43758.5453
    return x - math.floor(x)


def _hull_top(u: float) -> float:
    """Skrovets höjd över vattnet längs båten, u = 0 aktern … 1 fören (0–1)."""
    if u <= 0 or u >= 1:
        return 0.0
    aft = min(1.0, u / 0.12) ** 0.6           # akterns kona
    bow = min(1.0, (1 - u) / 0.08) ** 0.5     # rundad bog
    return aft * bow


def render_scene(cols: int, rows: int, t: float) -> list[Text]:
    """Bilden som rader. För liten yta ⇒ inga rader."""
    if cols < MIN_COLS or rows < MIN_ROWS:
        return []
    b = Braille(cols, rows)
    w, h = b.w, b.h
    water = int(h * 0.74)

    # stjärnor som blinkar
    for i in range(cols // 2):
        x, y = _hash(i, 1) * w, _hash(i, 2) * h * 0.4
        if (int(t * 1.5 + _hash(i, 3) * 7) % 5) != 0:
            b.dot(x, y, STAR)

    # fjällen på andra sidan fjorden
    for x in range(w):
        ridge = h * (0.4 - 0.08 * math.sin(x / w * 5.1 + 0.7) - 0.05 * math.sin(x / w * 13.3)
                     - 0.03 * math.sin(x / w * 29.0 + 1.9))
        b.dot(x, ridge, HILL)

    # sjön: glitter som rör sig
    for k, y in enumerate(range(water + 2, h, 3)):
        for x in range(0, w, 2):
            if math.sin(x * 0.27 + t * 1.6 + k * 1.3) + 0.5 * math.sin(x * 0.09 - t * 0.7) > 0.9:
                b.dot(x, y, SEA)

    # kajen till vänster, med kran och lampa
    pier_x1 = int(w * 0.16)
    deck = water - 4
    b.line(0, deck, pier_x1, deck, PIER, 2)
    b.line(0, deck + 1, pier_x1, deck + 1, PIER, 2)
    for x in range(2, pier_x1, 6):
        b.line(x, deck, x, water + 2, PIER, 2)
    crane_x = int(w * 0.05)
    b.line(crane_x, deck, crane_x, deck - int(h * 0.42), PIER, 2)
    b.line(crane_x, deck - int(h * 0.42), crane_x + int(w * 0.12), deck - int(h * 0.36), PIER, 2)
    b.line(crane_x + int(w * 0.12), deck - int(h * 0.36), crane_x + int(w * 0.12), deck - 10,
           PIER, 2)
    lamp_x = pier_x1 - 3
    b.line(lamp_x, deck, lamp_x, deck - 9, PIER, 2)

    # ubåten: lång och låg, tornet en tredjedel från fören
    x0, x1 = int(w * 0.18), int(w * 0.92)
    length = x1 - x0
    freeboard = max(4.0, h * 0.13)
    for x in range(x0, x1 + 1):
        top = water - freeboard * _hull_top((x - x0) / length)
        for y in range(int(math.ceil(top)), water + 1):
            b.dot(x, y, HULL_TOP if y == int(math.ceil(top)) else HULL, 5)
    sail_c = x1 - length * 0.36
    sail_w = length * 0.12
    sail_h = max(8.0, h * 0.3)
    for x in range(int(sail_c - sail_w / 2), int(sail_c + sail_w / 2) + 1):
        u = (x - (sail_c - sail_w / 2)) / sail_w
        rise = min(1.0, (1 - u) / 0.35) * min(1.0, u / 0.15 + 0.6)   # rundad framkant
        top = water - freeboard - sail_h * rise
        for y in range(int(math.ceil(top)), int(water - freeboard) + 1):
            b.dot(x, y, HULL, 5)
    mast_top = water - freeboard - sail_h
    for dx, extra in ((-0.15, 4), (0.05, 6)):
        mx = sail_c + dx * sail_w
        b.line(mx, mast_top, mx, mast_top - extra, HULL, 5)

    # snö som driver med vinden
    for i in range(cols * rows // 8):
        vy = 4 + 4 * _hash(i, 5)
        x = (_hash(i, 6) * w - 3.0 * t + 2 * math.sin(t * 0.8 + i)) % w
        y = (_hash(i, 7) * h + vy * t) % h
        b.dot(x, y, SNOW, 9)

    canvas = Canvas(cols, rows, f"on {BG}")
    b.blit(canvas, 0, 0)
    # lampan på kajen och tornets röda lanterna, ett tecken var
    canvas.put(int((deck - 10) / 4), lamp_x // 2, "✦" if int(t * 3) % 7 else "·", f"bold {LAMP}")
    canvas.put(int(mast_top / 4), int(sail_c) // 2, "•" if int(t / 0.8) % 2 else "·", f"bold {RED}")
    star_row = int((water - freeboard - sail_h / 2) / 4)
    canvas.put(star_row, int(sail_c - sail_w * 0.1) // 2, "★", f"bold {RED}")
    caption = " К-114 · Poljarnyj · natt "
    canvas.text(rows - 1, cols - len(caption) - 1, caption, f"italic {DIM}")
    return canvas.lines()


def scene_text(cols: int, rows: int, t: float) -> Text:
    lines = render_scene(cols, rows, t)
    return Text("\n").join(lines) if lines else Text("", style=INK)
