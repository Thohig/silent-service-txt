"""Rastrering av djupprofilen och djupmätaren till tecken (rich, testbart utan Textual).

Sidovyn: vågrätt simtid (högerkanten är nu), lodrätt djup. Rad 0 är ytan
och varje rad `dpr` meter. Djupare än skalan, där botten brukar ligga, bryts
axeln och botten ritas i ett eget band med lodat djup. Under bilden en rad
med det sonar hört.
"""
from __future__ import annotations

import math

from rich.text import Text

from sim.fmt import clock, fmt_course, kn
from sim.profile import ProfileView

MARGIN = 7                  # djupetiketter till vänster: "  450 ┤"
RIGHT = 14                  # etiketter för djupen till höger
DEPTH_ZOOM = (40, 80, 150, 300, 500)          # största djup i bilden, meter
TIME_ZOOM = (10, 30, 60, 120)                 # sekunder per kolumn
DEFAULT_TIME_ZOOM = 1
BOTTOM_VALID_S = 600        # en ekolodslodning gäller så här länge framåt
TICK_MINUTES = (1, 2, 5, 10, 15, 30, 60)
DEPTH_TICKS = (5, 10, 20, 25, 50, 100)
ROW_METERS = (1, 2, 2.5, 5, 10, 12.5, 15, 20, 25, 30, 40, 50)     # jämna meter per rad

STYLE = {
    "own": "bold bright_white",
    "trace": "#6f9f6f",
    "ordered": "yellow",
    "surface": "#5f87af",
    "periscope": "#4f6f60",
    "layer": "#5fafaf",
    "test": "#b0a050",
    "crush": "#b05050",
    "bottom": "#8a7a5a",
    "bottom_old": "#5a5040",
    "ice_open": "bold #5fd7ff",
    "ice_thin": "#5f87af",
    "ice_thick": "#8fa39a",
    "heard_ping": "cyan",
    "heard_splash": "bold yellow",
    "heard_explosion": "bold red",
    "heard_practice": "yellow",
    "heard_buoy": "#c6a0ff",
    "heard_other": "cyan",
    "own_sound": "bold white",
    "axis": "#7f9a80",
    "dim": "#4f6358",
}
# vilket ljud som vinner när två hamnar i samma kolumn
EVENT_PRIO = {"explosion": 6, "breakup": 6, "splash": 5, "own_launch": 5, "own_blow": 5,
              "buoy_ping": 4, "own_ping": 4, "own_decoy": 4, "practice": 3, "buoy": 3,
              "uwt": 2, "ping": 1}

LEGEND = [
    ("▬▶", "own", "vi nu"), ("·", "trace", "vårt djup"), ("┆", "ordered", "beordrat"),
    ("─", "layer", "språngskikt"), ("▓", "bottom", "botten (ekolod)"), ("█", "ice_thick", "is"),
    ("≈", "ice_open", "öppet vatten"),
    None, ("◦", "heard_ping", "ping"), ("↓", "heard_splash", "plask"),
    ("✱", "heard_explosion", "detonation"),
    ("⊥", "heard_buoy", "boj"), ("~", "heard_other", "telefon"),
    ("!", "own_sound", "egen ping"), ("»", "own_sound", "avfyring"), ("o", "own_sound", "skenmål"),
]


def auto_depth_zoom(view: ProfileView, t0: int) -> int:
    """Minsta skala som rymmer vårt djup i bilden, beordrat djup och isens kölar."""
    deepest = max([view.depth, view.ordered_depth]
                  + [d for t, d in view.trace if t >= t0]
                  + [s.draft for s in view.ice if s.t >= t0])
    for i, z in enumerate(DEPTH_ZOOM):
        if deepest * 1.15 + 5 <= z:
            return i
    return len(DEPTH_ZOOM) - 1


def _depth_tick(dpr: float) -> int:
    for step in DEPTH_TICKS:
        if step / dpr >= 3:
            return step
    return DEPTH_TICKS[-1]


def _time_tick(spc: int) -> int:
    for m in TICK_MINUTES:
        if m * 60 / spc >= 12:
            return m
    return TICK_MINUTES[-1]


def fmt_m(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


class _Grid:
    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.ch = [[" "] * cols for _ in range(rows)]
        self.st = [[""] * cols for _ in range(rows)]

    def put(self, c: int, r: int, ch: str, style: str) -> None:
        if 0 <= c < self.cols and 0 <= r < self.rows:
            self.ch[r][c], self.st[r][c] = ch, style

    def get(self, c: int, r: int) -> str:
        return self.ch[r][c] if 0 <= c < self.cols and 0 <= r < self.rows else ""

    def text(self, c: int, r: int, s: str, style: str) -> None:
        for i, ch in enumerate(s):
            self.put(c + i, r, ch, style)

    def line(self, r: int) -> Text:
        t = Text(no_wrap=True, overflow="crop")
        for ch, st in zip(self.ch[r], self.st[r]):
            t.append(ch, style=st)
        return t


def render_profile(view: ProfileView, width: int, height: int,
                   sec_per_col: int = TIME_ZOOM[DEFAULT_TIME_ZOOM],
                   max_depth: float | None = None) -> list[Text]:
    """Sidovyn som `height` rader text, `width` tecken breda."""
    cols = max(10, width - MARGIN - RIGHT)
    now = view.now
    t0 = now - (cols - 1) * sec_per_col

    def col_of(t: float) -> int:
        return cols - 1 - math.floor((now - t) / sec_per_col + 0.5)

    if max_depth is None:
        max_depth = DEPTH_ZOOM[auto_depth_zoom(view, t0)]
    bottoms = [b for b in view.bottom if b.t + BOTTOM_VALID_S >= t0]
    bottom_in_view = any(b.depth <= max_depth for b in bottoms)
    band = 0 if bottom_in_view else 2              # bruten axel + bottenraden
    plot_rows = max(4, height - 1 - 1 - band)      # tidsaxel överst, ljud underst
    need = max_depth / (plot_rows - 1)
    dpr = next((m for m in ROW_METERS if m >= need), need)
    max_depth = dpr * (plot_rows - 1)

    def row_of(d: float) -> int:
        return min(plot_rows - 1, max(0, round(d / dpr)))

    g = _Grid(cols, plot_rows)
    left = [Text(" " * (MARGIN - 1) + "│", style=STYLE["axis"]) for _ in range(plot_rows)]
    right = [Text("") for _ in range(plot_rows)]

    # djupaxeln
    step = _depth_tick(dpr)
    for d in range(0, int(max_depth) + 1, step):
        r = row_of(d)
        left[r] = Text(f"{d:>{MARGIN - 2}} ┤", style=STYLE["axis"])

    # fasta djup: yta, periskopdjup, skikt, provdjup, krossdjup
    warn_style = {}
    if view.depth >= 300 * 0.9:
        warn_style["test"] = "bold yellow"
    if view.depth >= 300:
        warn_style["crush"] = "bold red"
    for lv in view.levels:
        if lv.depth > max_depth:
            continue
        r = row_of(lv.depth)
        st = warn_style.get(lv.style, STYLE.get(lv.style, "white"))
        for c in range(cols):
            g.put(c, r, lv.char if lv.char != "─" or c % 2 == 0 else " ", st)
        right[r] = Text(f" {lv.label}", style=st)
        left[r] = Text(f"{lv.depth:>{MARGIN - 2}.0f} ┼", style=st)

    # botten i bilden (grunt vatten)
    if bottom_in_view:
        for i, b in enumerate(bottoms):
            end = bottoms[i + 1].t if i + 1 < len(bottoms) else b.t + BOTTOM_VALID_S
            for c in range(max(0, col_of(b.t)), min(cols, col_of(min(end, now)) + 1)):
                for r in range(row_of(b.depth), plot_rows):
                    g.put(c, r, "▓", STYLE["bottom"])
        right[row_of(bottoms[-1].depth)] = Text(f" botten {fmt_m(bottoms[-1].depth)}",
                                                style=STYLE["bottom"])

    # isen ovanför, kolumn för kolumn: öppet vinner, annars djupaste kölen
    cells: dict[int, list] = {}
    for s in view.ice:
        c = col_of(s.t)
        if 0 <= c < cols:
            cells.setdefault(c, []).append(s)
    for c, ss in cells.items():
        if any(s.open for s in ss):
            g.put(c, 0, "≈", STYLE["ice_open"])
            continue
        if all(s.usable for s in ss):
            g.put(c, 0, "▀", STYLE["ice_thin"])
            continue
        draft = max(s.draft for s in ss)
        g.put(c, 0, "█", STYLE["ice_thick"])
        for r in range(1, plot_rows):
            d = r * dpr
            if draft >= d:
                g.put(c, r, "█", STYLE["ice_thick"])
            elif draft > d - dpr / 2:
                g.put(c, r, "▀", STYLE["ice_thick"])
            else:
                break
    if cells:
        right[0] = Text(" is", style=STYLE["ice_thick"])

    # vårt djup: medel per kolumn, prickat och sammanbundet
    by_col: dict[int, list[float]] = {}
    for t, d in view.trace:
        c = col_of(t)
        if 0 <= c < cols:
            by_col.setdefault(c, []).append(d)
    prev = None
    for c in sorted(by_col):
        r = row_of(sum(by_col[c]) / len(by_col[c]))
        lo, hi = (r, r) if prev is None or c - prev[0] > 1 else sorted((prev[1], r))
        for rr in range(lo, hi + 1):
            if g.get(c, rr) not in ("█", "▀", "▓"):
                g.put(c, rr, "·", STYLE["trace"])
        prev = (c, r)

    # beordrat djup och ubåten nu
    r_now = row_of(view.depth)
    if abs(view.ordered_depth - view.depth) >= 1:
        r_ord = row_of(view.ordered_depth)
        arrow = "↓" if view.ordered_depth > view.depth else "↑"
        sgn = 1 if r_ord > r_now else -1
        for rr in range(r_now + sgn, r_ord, sgn):
            g.put(cols - 1, rr, "┆", STYLE["ordered"])
        g.put(cols - 1, r_ord, arrow, STYLE["ordered"])
        right[r_ord] = Text(f" {arrow} {view.ordered_depth:.0f} m", style=STYLE["ordered"])
    g.text(cols - 3, r_now, "▬▬▶", STYLE["own"])
    right[r_now] = Text(f" ◀ {view.depth:.0f} m", style=STYLE["own"])

    lines = [_time_axis(view, cols, sec_per_col)]
    for r in range(plot_rows):
        lines.append(Text.assemble(left[r], g.line(r), _pad(right[r])))

    if band:
        lines.extend(_bottom_band(view, bottoms, cols, col_of, max_depth))
    lines.append(_events_row(view, cols, col_of))
    return lines[:height]


def _pad(t: Text) -> Text:
    t = t.copy()
    t.truncate(RIGHT, overflow="crop", pad=True)
    return t


def _time_axis(view: ProfileView, cols: int, spc: int) -> Text:
    g = _Grid(cols, 1)
    m = _time_tick(spc)
    k = 1
    while True:
        c = cols - 1 - round(k * m * 60 / spc)
        label = f"−{k * m} min"
        if c - len(label) // 2 < 0:
            break
        g.text(c - len(label) // 2, 0, label, STYLE["axis"])
        k += 1
    g.text(cols - 2, 0, "nu", STYLE["own"])
    return Text.assemble(Text(" " * MARGIN), g.line(0), _pad(Text(" " + view.clock[:5])))


def _bottom_band(view: ProfileView, bottoms, cols: int, col_of, max_depth: float) -> list[Text]:
    brk = Text(" " * (MARGIN - 1) + "┊", style=STYLE["axis"])
    brk.append(("≈ " * cols)[:cols], style=STYLE["dim"])
    brk.append(_pad(Text(" axeln bruten", style=STYLE["dim"])))

    g = _Grid(cols, 1)
    now = view.now
    for i, b in enumerate(bottoms):
        end = bottoms[i + 1].t if i + 1 < len(bottoms) else b.t + BOTTOM_VALID_S
        fresh = now - b.t < BOTTOM_VALID_S
        for c in range(max(0, col_of(b.t)), min(cols, col_of(min(end, now)) + 1)):
            g.put(c, 0, "▓", STYLE["bottom" if fresh else "bottom_old"])
    # okända sträckor får ett frågetecken i mitten
    run_start = None
    for c in range(cols + 1):
        empty = c < cols and g.get(c, 0) == " "
        if empty and run_start is None:
            run_start = c
        elif not empty and run_start is not None:
            if c - run_start >= 3:
                g.put((run_start + c) // 2, 0, "?", STYLE["dim"])
            run_start = None
    if bottoms:
        b = bottoms[-1]
        label = f"{fmt_m(b.depth):>{MARGIN - 2}} ┤"
        tail = Text(f" botten {clock(view.start_clock + b.t)[:5]}", style=STYLE["bottom"])
    else:
        label = f"{'?':>{MARGIN - 2}} ┤"
        tail = Text(" botten okänd", style=STYLE["dim"])
        g.text(max(0, cols // 2 - 14), 0, " ekolod ger bottendjupet ", STYLE["dim"])
    return [brk, Text.assemble(Text(label, style=STYLE["axis"]), g.line(0), _pad(tail))]


def _events_row(view: ProfileView, cols: int, col_of) -> Text:
    g = _Grid(cols, 1)
    prio = [-1] * cols
    for e in view.events:
        c = col_of(e.t)
        p = EVENT_PRIO.get(e.kind, 0)
        if 0 <= c < cols and p >= prio[c]:
            prio[c] = p
            g.put(c, 0, e.symbol, STYLE.get(e.style, "white") + (" reverse" if e.near else ""))
    return Text.assemble(Text(" " * (MARGIN - 1) + "╵", style=STYLE["axis"]), g.line(0),
                         _pad(Text(" hört", style=STYLE["dim"])))


def legend() -> Text:
    t = Text(" ", no_wrap=True, overflow="crop")
    for item in LEGEND:
        if item is None:
            t.append("\n ")
            continue
        sym, style, what = item
        t.append(sym, style=STYLE[style])
        t.append(f" {what}  ", style="dim")
    return t


def header(view: ProfileView) -> Text:
    t = Text(" DJUPPROFIL ", style="bold")
    t.append(f" djup {view.depth:.0f} m", style="bold")
    if abs(view.ordered_depth - view.depth) >= 1:
        t.append(f" ▸{view.ordered_depth:.0f} m", style="yellow")
    t.append(f" · fart {kn(view.speed)} kn · kurs {fmt_course(view.course)}")
    for n in view.notes:
        t.append(f" · {n.text}")
    return t


# --- djupmätaren bredvid loggen ----------------------------------------------------------
GAUGE_WIDTH = 22


def render_gauge(view: ProfileView) -> list[Text]:
    """Liten djupmätare: fasta djup, vårt djup och beordrat, isen och botten, i djupordning."""
    rows: list[tuple[float, int, Text]] = []          # (djup, ordning, rad)

    def row(depth: float, order: int, label: str, mark: str, what: str, style: str,
            mark_style: str | None = None) -> None:
        t = Text(no_wrap=True, overflow="crop")
        t.append(f"{label:>6} ", style=style)
        t.append(mark, style=mark_style or style)
        t.append(f" {what}", style=style)
        rows.append((depth, order, t))

    for lv in view.levels:
        if lv.style == "surface":
            continue
        st = STYLE.get(lv.style, "white")
        if lv.style == "test" and view.depth >= lv.depth * 0.9:
            st = "bold yellow"
        if lv.style == "crush" and view.depth >= 300:
            st = "bold red"
        short = {"periskopdjup": "periskop", "språngskikt": "skikt", "provdjup": "prov",
                 "krossdjup": "kross"}.get(lv.label, lv.label)
        row(lv.depth, 1, f"{lv.depth:.0f}", lv.char * 2, short, st)

    ice = [s for s in view.ice if view.now - s.t <= 30]
    if ice:
        s = ice[-1]
        if s.open:
            row(0, 0, "yta", "≈≈", "öppet vatten", STYLE["ice_open"])
        else:
            row(0, 0, "yta", "██" if not s.usable else "▀▀",
                f"is {s.thickness:.1f} m".replace(".", ","), STYLE["ice_thick"])
            row(s.draft, 0, f"{s.draft:.0f}", "▀▀", "isens undersida", STYLE["ice_thick"])
    else:
        row(0, 0, "yta", "≈≈", "", STYLE["surface"])

    own = Text(no_wrap=True, overflow="crop")
    own.append(f"▶{view.depth:>5.0f} ", style=STYLE["own"])
    own.append("◆◆", style=STYLE["own"])
    if abs(view.ordered_depth - view.depth) >= 1:
        arrow = "↓" if view.ordered_depth > view.depth else "↑"
        own.append(f" {arrow}{view.ordered_depth:.0f}", style=STYLE["ordered"])
    else:
        own.append(" vi", style=STYLE["own"])
    rows.append((view.depth, 2, own))

    b = view.latest_bottom()
    if b is not None:
        fresh = view.now - b.t < BOTTOM_VALID_S
        row(b.depth, 3, f"~{fmt_m(b.depth)}", "▓▓", f"botten {clock(view.start_clock + b.t)[:5]}",
            STYLE["bottom" if fresh else "bottom_old"])
    else:
        row(10**6, 3, "?", "▓▓", "botten okänd", STYLE["dim"])

    rows.sort(key=lambda x: (x[0], x[1]))
    head = Text(" DJUPMÄTARE", style="bold")
    return [head] + [r[2] for r in rows]
