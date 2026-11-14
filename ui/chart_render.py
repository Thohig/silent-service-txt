"""Rastrering av sjökortet till tecken (rich, inte Textual – går att testa direkt).

En kolumn är `scale` sjömil bred och en rad `2·scale` hög, eftersom en
teckenruta är ungefär dubbelt så hög som bred. Då blir cirklar runda och
bäringar ritas i rätt vinkel.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from rich.text import Text

from sim.chart import LAYER_MARK, ChartView, Mark, Ray, Ring, Track
from sim.reports import Quality

from .widgets import QUALITY_STYLE

MARGIN = 5                      # kolumner till vänster för nordkoordinaterna
GRID_STEPS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
GRID_MIN_COLS = 8
LABEL_PRIO = LAYER_MARK - 0.5
BACK_PRIO = -1.0

STYLE = {
    "own": "bold bright_white",
    "own_vector": "white",
    "track": "#6f9f6f",
    "fix": "bold green",
    "ice_open": "bold #5fd7ff",
    "ice_thin": "#5f87af",
    "ice_thick": "#4f6358",
    "opening": "bold #5fd7ff",
    "waypoint": "bold #c6a0ff",
    "contact": "bold cyan",
    "contact_vector": "cyan",
    "bearing": "cyan",
    "merchant": "#c8b070",
    "merchant_vector": "#a08c58",
    "torpedo": "bold red",
    "grid": "#2f4a36",
    "border": "#5f8a66",
    "axis": "#7f9a80",
}
ARROWS = {(0, -1): "↑", (0, 1): "↓", (-1, 0): "←", (1, 0): "→",
          (-1, -1): "↖", (1, -1): "↗", (-1, 1): "↙", (1, 1): "↘", (0, 0): "·"}
EDGE_STYLES = {"contact", "waypoint", "merchant"}     # visas med pil vid kanten när de ligger utanför
QUALITY_KEYED = {"opening", "contact", "contact_vector"}


def item_style(style: str, quality: Quality | None = None, faded: bool = False) -> str:
    st = QUALITY_STYLE[quality] if quality is not None and style in QUALITY_KEYED \
        else STYLE.get(style, "white")
    return f"{st} dim" if faded else st


def grid_step(scale: float) -> float:
    for step in GRID_STEPS:
        if step / scale >= GRID_MIN_COLS:
            return step
    return GRID_STEPS[-1]


def fmt_grid(v: float) -> str:
    if abs(v - round(v)) < 1e-6:
        return f"{round(v)}"
    return f"{v:.2f}".rstrip("0").replace(".", ",")


def ray_char(bearing: float) -> str:
    b = bearing % 180
    if b < 22.5 or b >= 157.5:
        return "│"
    if b < 67.5:
        return "╱"
    if b < 112.5:
        return "─"
    return "╲"


@dataclass
class Canvas:
    """Kortytan (utan marginaler) med prioritet per ruta."""
    cols: int
    rows: int
    cx: float
    cy: float
    scale: float

    def __post_init__(self):
        self.ch = [[" "] * self.cols for _ in range(self.rows)]
        self.st = [[""] * self.cols for _ in range(self.rows)]
        self.prio = [[-2.0] * self.cols for _ in range(self.rows)]
        self.grid_xs: list[float] = []
        self.grid_ys: list[float] = []

    def cell(self, x: float, y: float) -> tuple[int, int]:
        c = math.floor((x - self.cx) / self.scale + self.cols / 2)
        r = math.floor((self.cy - y) / (2 * self.scale) + self.rows / 2)
        return c, r

    def x_of(self, c: int) -> float:
        return self.cx + (c - self.cols / 2) * self.scale

    def y_of(self, r: int) -> float:
        return self.cy - (r - self.rows / 2) * 2 * self.scale

    def inside(self, c: int, r: int) -> bool:
        return 0 <= c < self.cols and 0 <= r < self.rows

    def put(self, c: int, r: int, ch: str, style: str, prio: float) -> bool:
        if not self.inside(c, r) or prio < self.prio[r][c]:
            return False
        self.ch[r][c], self.st[r][c], self.prio[r][c] = ch, style, prio
        return True

    def text(self, c: int, r: int, s: str, style: str, prio: float) -> None:
        """Skriv en etikett utan att skriva över märken; flytta åt vänster vid kanten."""
        if c + len(s) > self.cols:
            c = max(0, c - len(s) - 3)
        for i, ch in enumerate(s):
            self.put(c + i, r, ch, style, prio)
        if c > 0 and self.prio[r][c - 1] < LAYER_MARK:
            self.put(c - 1, r, " ", "", prio)       # luft mellan märke och etikett

    # --- primitiver -------------------------------------------------------------
    def line(self, x0, y0, x1, y1, ch: str | None, style: str, prio: float,
             skip_start: bool = False) -> tuple[int, int] | None:
        """Linje genom kortet, en ruta per steg längs huvudaxeln (tunn linje).
        Returnerar sista synliga rutan."""
        fc0 = (x0 - self.cx) / self.scale + self.cols / 2
        fr0 = (self.cy - y0) / (2 * self.scale) + self.rows / 2
        fc1 = (x1 - self.cx) / self.scale + self.cols / 2
        fr1 = (self.cy - y1) / (2 * self.scale) + self.rows / 2
        n = max(1, math.ceil(max(abs(fc1 - fc0), abs(fr1 - fr0))))
        start = self.cell(x0, y0)
        diag = "╲" if (fc1 - fc0) * (fr1 - fr0) > 0 else "╱"
        cells = []
        for i in range(n + 1):
            f = i / n
            cells.append((math.floor(fc0 + (fc1 - fc0) * f), math.floor(fr0 + (fr1 - fr0) * f)))
        last = None
        for i, (c, r) in enumerate(cells):
            if skip_start and (c, r) == start:
                continue
            if ch is None:
                # tecknet efter hur linjen går här: i sidled, i höjdled eller snett
                pc, pr = cells[i - 1] if i else cells[min(1, len(cells) - 1)]
                dc, dr = c != pc, r != pr
                g = diag if dc and dr else "│" if dr else "─"
            else:
                g = ch
            if self.inside(c, r):
                self.put(c, r, g, style, prio)
                last = (c, r)
        return last

    def ring(self, x, y, radius, style, prio) -> None:
        if radius / self.scale < 1.5:
            return                      # ryms i själva märket
        n = max(16, int(2 * math.pi * radius / self.scale * 1.5))
        for i in range(n):
            a = 2 * math.pi * i / n
            c, r = self.cell(x + radius * math.sin(a), y + radius * math.cos(a))
            self.put(c, r, ".", style, prio)

    def edge(self, x: float, y: float) -> tuple[int, int, str]:
        """Rutan vid kanten i riktning mot en punkt utanför kortet, och en pil."""
        c, r = self.cell(x, y)
        cc, rr = min(max(c, 0), self.cols - 1), min(max(r, 0), self.rows - 1)
        sx = (c > cc) - (c < cc)
        sy = (r > rr) - (r < rr)
        return cc, rr, ARROWS[(sx, sy)]


def render_chart(view: ChartView, cx: float, cy: float, scale: float,
                 width: int, height: int) -> list[Text]:
    """Kortet som `height` rader text, `width` tecken breda."""
    cv = Canvas(max(1, width - MARGIN), max(1, height - 1), cx, cy, scale)
    _background(cv, view.size_nm)
    labels: list[tuple[float, float, str, str, int]] = []   # x, y, text, stil, förskjutning
    for it in view.drawables:
        match it:
            case Track(points=pts, style=s):
                st = item_style(s)
                for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                    cv.line(x0, y0, x1, y1, "·", st, it.layer)
                if len(pts) == 1:
                    c, r = cv.cell(*pts[0])
                    cv.put(c, r, "·", st, it.layer)
            case Ring():
                cv.ring(it.x, it.y, it.radius, item_style(it.style, it.quality, faded=True),
                        it.layer)
            case Ray():
                b = math.radians(it.bearing)
                x1, y1 = it.x + it.length * math.sin(b), it.y + it.length * math.cos(b)
                st = item_style(it.style, it.quality, it.faded)
                last = cv.line(it.x, it.y, x1, y1, None, st, it.layer, skip_start=True)
                if it.label and last is not None:
                    labels.append((cv.x_of(last[0]) + scale / 2, cv.y_of(last[1]) - scale,
                                   it.label, st, 1))
            case Mark():
                st = item_style(it.style, it.quality, it.faded)
                c, r = cv.cell(it.x, it.y)
                if cv.inside(c, r):
                    cv.put(c, r, it.symbol, st, it.layer)
                    if it.label:
                        labels.append((it.x, it.y, it.label, st, 2))
                elif it.label and it.style in EDGE_STYLES:
                    # utanför kortet: en pil vid kanten åt rätt håll
                    ec, er, arrow = cv.edge(it.x, it.y)
                    cv.put(ec, er, arrow, st, it.layer)
                    labels.append((cv.x_of(ec) + scale / 2, cv.y_of(er) - scale,
                                   it.label, st, 2))
    for x, y, s, st, off in labels:
        c, r = cv.cell(x, y)
        if cv.inside(c, r):
            cv.text(c + off, r, s, st, LABEL_PRIO)
    return _with_axes(cv)


def _background(cv: Canvas, size: float) -> None:
    """Rutnät och kvadratens gräns."""
    step = grid_step(cv.scale)
    grid, border = STYLE["grid"], STYLE["border"]
    x_lo, x_hi = cv.x_of(0), cv.x_of(cv.cols)
    y_lo, y_hi = cv.y_of(cv.rows), cv.y_of(0)
    gx = math.ceil(max(0.0, x_lo) / step) * step
    xs = []
    while gx <= min(size, x_hi):
        xs.append(gx)
        gx += step
    gy = math.ceil(max(0.0, y_lo) / step) * step
    ys = []
    while gy <= min(size, y_hi):
        ys.append(gy)
        gy += step
    for x in xs:
        for y in ys:
            c, r = cv.cell(x, y)
            cv.put(c, r, "┼", grid, BACK_PRIO)
    cv.line(0, 0, size, 0, "─", border, BACK_PRIO)
    cv.line(0, size, size, size, "─", border, BACK_PRIO)
    cv.line(0, 0, 0, size, "│", border, BACK_PRIO)
    cv.line(size, 0, size, size, "│", border, BACK_PRIO)
    for (x, y), ch in (((0, 0), "└"), ((size, 0), "┘"), ((0, size), "┌"), ((size, size), "┐")):
        c, r = cv.cell(x, y)
        cv.put(c, r, ch, border, BACK_PRIO)
    cv.grid_xs, cv.grid_ys = xs, ys


def _with_axes(cv: Canvas) -> list[Text]:
    axis = STYLE["axis"]
    top = [" "] * cv.cols
    for x in cv.grid_xs:
        c, _ = cv.cell(x, cv.cy)
        s = fmt_grid(x)
        if 0 <= c and c + len(s) <= cv.cols and all(ch == " " for ch in top[c:c + len(s) + 1]):
            top[c:c + len(s)] = s
    row_label = {}
    for y in cv.grid_ys:
        _, r = cv.cell(cv.cx, y)
        row_label[r] = fmt_grid(y)
    out = [Text(" " * MARGIN + "".join(top), style=axis)]
    for r in range(cv.rows):
        t = Text(f"{row_label.get(r, ''):>{MARGIN - 1}} ", style=axis)
        run, run_st = "", None
        for ch, st in zip(cv.ch[r], cv.st[r]):
            if st != run_st and run:
                t.append(run, style=run_st or None)
                run = ""
            run_st = st
            run += ch
        if run:
            t.append(run, style=run_st or None)
        out.append(t)
    return out
