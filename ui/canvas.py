"""Ritytor för bilderna: tecken med stil per ruta, och brailleprickar för fina linjer.

`Canvas` är ett rutnät av (tecken, stil). `Braille` ritar med prickar, 2 × 4 per ruta, så
att visare och skalor kan stå i alla vinklar; prickarna är ungefär kvadratiska. Varje ruta
får stilen med högst prioritet bland sina prickar (visaren går före skalan), och
`Braille.blit` lägger de rutor som har prickar på en `Canvas`.

Vinklar är kompassvinklar i grader: 0 upp, medurs.
"""
from __future__ import annotations

import math

from rich.text import Text

BRAILLE_BASE = 0x2800
# prickens bit efter (x, y) inom rutan
DOT_BITS = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (1, 0): 0x08,
            (1, 1): 0x10, (1, 2): 0x20, (0, 3): 0x40, (1, 3): 0x80}


class Canvas:
    def __init__(self, w: int, h: int, base: str) -> None:
        self.w, self.h = w, h
        self.cells = [[(" ", base) for _ in range(w)] for _ in range(h)]

    def put(self, row: int, col: int, ch: str, style: str) -> None:
        if 0 <= row < self.h and 0 <= col < self.w:
            self.cells[row][col] = (ch, style)

    def text(self, row: int, col: int, s: str, style: str) -> None:
        for i, ch in enumerate(s):
            self.put(row, col + i, ch, style)

    def centered(self, row: int, col: int, s: str, style: str) -> None:
        """Text centrerad kring en kolumn."""
        self.text(row, col - len(s) // 2, s, style)

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


def polar(cx: float, cy: float, r: float, angle: float) -> tuple[float, float]:
    """Punkt på avståndet r i kompassvinkeln angle från (cx, cy), i prickar."""
    a = math.radians(angle)
    return cx + r * math.sin(a), cy - r * math.cos(a)


class Braille:
    """Prickritning på cols × rows rutor (2 × 4 prickar per ruta)."""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.w, self.h = 2 * cols, 4 * rows
        self.bits = [[0] * cols for _ in range(rows)]
        self.styles: list[list[tuple[int, str] | None]] = [[None] * cols for _ in range(rows)]

    def dot(self, x: float, y: float, style: str, prio: int = 0) -> None:
        xi, yi = int(round(x)), int(round(y))
        if not (0 <= xi < self.w and 0 <= yi < self.h):
            return
        col, row = xi // 2, yi // 4
        self.bits[row][col] |= DOT_BITS[(xi % 2, yi % 4)]
        cur = self.styles[row][col]
        if cur is None or prio >= cur[0]:
            self.styles[row][col] = (prio, style)

    def line(self, x0: float, y0: float, x1: float, y1: float, style: str,
             prio: int = 0) -> None:
        n = max(1, int(math.ceil(max(abs(x1 - x0), abs(y1 - y0)))))
        for i in range(n + 1):
            f = i / n
            self.dot(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, style, prio)

    def ray(self, cx: float, cy: float, angle: float, r0: float, r1: float, style: str,
            prio: int = 0) -> None:
        """Linje längs en radie, från r0 till r1."""
        x0, y0 = polar(cx, cy, r0, angle)
        x1, y1 = polar(cx, cy, r1, angle)
        self.line(x0, y0, x1, y1, style, prio)

    def arc(self, cx: float, cy: float, r: float, a0: float, a1: float, style: str,
            prio: int = 0) -> None:
        """Båge medurs från a0 till a1 (grader)."""
        span = a1 - a0
        n = max(8, int(abs(span) / 360.0 * 2 * math.pi * r * 1.5))
        for i in range(n + 1):
            x, y = polar(cx, cy, r, a0 + span * i / n)
            self.dot(x, y, style, prio)

    def blit(self, canvas: Canvas, row0: int, col0: int) -> None:
        """Lägg rutorna som har prickar på ritytan."""
        for r in range(self.rows):
            for c in range(self.cols):
                b = self.bits[r][c]
                if b:
                    st = self.styles[r][c]
                    canvas.put(row0 + r, col0 + c, chr(BRAILLE_BASE + b), st[1] if st else "")


class DotLayer:
    """Glest prickskikt i braille ovanpå ett teckenrutnät (sjökortet, profilen …).

    Ritar i prickkoordinater: x = 2·kolumn, y = 4·rad, så att en prick är ungefär kvadratisk.
    Varje ruta samlar sina prickar och får stilen från pricken med högst prioritet. Rutnätet
    som äger skiktet avgör per ruta om tecknet eller prickarna syns (`cell`)."""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.cells: dict[tuple[int, int], list] = {}      # (rad, kol) -> [bitar, stil, prio]

    def dot(self, x: float, y: float, style: str, prio: float = 0.0) -> tuple[int, int] | None:
        xi, yi = math.floor(x + 1e-6), math.floor(y + 1e-6)     # 53,9999… är 54
        col, row = xi // 2, yi // 4
        if not (0 <= col < self.cols and 0 <= row < self.rows):
            return None
        cell = self.cells.get((row, col))
        bit = DOT_BITS[(xi % 2, yi % 4)]
        if cell is None:
            self.cells[(row, col)] = [bit, style, prio]
        else:
            cell[0] |= bit
            if prio >= cell[2]:
                cell[1], cell[2] = style, prio
        return row, col

    def line(self, x0: float, y0: float, x1: float, y1: float, style: str,
             prio: float = 0.0, dash: int = 0, skip: float = 0.0) -> tuple[int, int] | None:
        """Linje prick för prick; `dash` > 0 ger streck och luckor om så många prickar,
        `skip` hoppar över de första prickarna (en linje som börjar i ett märke).
        Ger den sista rutan som fick en prick."""
        n = max(1, int(math.ceil(max(abs(x1 - x0), abs(y1 - y0)))))
        last = None
        for i in range(n + 1):
            if i < skip or (dash and (i // dash) % 2 == 1):
                continue
            f = i / n
            hit = self.dot(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, style, prio)
            if hit is not None:
                last = hit
        return last

    def polyline(self, pts, style: str, prio: float = 0.0, dash: int = 0) -> None:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            self.line(x0, y0, x1, y1, style, prio, dash)

    def circle(self, cx: float, cy: float, r: float, style: str, prio: float = 0.0,
               dash: int = 0) -> None:
        n = max(12, int(2 * math.pi * r * 1.2))
        for i in range(n):
            if dash and (i // dash) % 2 == 1:
                continue
            a = 2 * math.pi * i / n
            self.dot(cx + r * math.sin(a), cy - r * math.cos(a), style, prio)

    def cell(self, row: int, col: int) -> tuple[str, str, float] | None:
        c = self.cells.get((row, col))
        if c is None:
            return None
        return chr(BRAILLE_BASE + c[0]), c[1], c[2]
