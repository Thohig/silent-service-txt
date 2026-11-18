"""Rastrering av djupprofilen och djupmätaren till tecken (rich, testbart utan Textual).

Sidovyn: vågrätt simtid (högerkanten är nu), lodrätt djup. Rad 0 är ytan
och varje rad `dpr` meter. Djupare än skalan, där botten brukar ligga, bryts
axeln och botten ritas i ett eget band med lodat djup. Under bilden en rad
med det sonar hört.

Vårt djup, sjökortets botten och de tunna djupnivåerna (språngskikt, periskopdjup,
provdjup) ritas i braille (`DotLayer`, 2 × 4 prickar per ruta) vid sitt exakta djup;
is, lodad botten, ubåten och beordrat djup är hela tecken och går före prickarna.
"""
from __future__ import annotations

import math

from rich.text import Text

from sim.fmt import clock
from sim.profile import ProfileView

from .canvas import DotLayer


MARGIN = 7                  # djupetiketter till vänster: "  450 ┤"
RIGHT = 14                  # etiketter för djupen till höger
DEPTH_ZOOM = (40, 80, 150, 300, 500)          # största djup i bilden, meter
TIME_ZOOM = (10, 30, 60, 120)                 # sekunder per kolumn
DEFAULT_TIME_ZOOM = 1
BOTTOM_VALID_S = 600        # en ekolodslodning gäller så här länge framåt
BAND_ROWS = 3               # bottenbandet under den brutna axeln
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
    "chart_bottom": "#6f7fa0",
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
    ("▬▶", "own", "vi nu"), ("⠤⠤", "trace", "vårt djup"), ("┆", "ordered", "beordrat"),
    ("⠄⠠", "layer", "språngskikt"), ("▓", "bottom", "ekolod"), ("⠒⠒", "chart_bottom", "sjökortets djup"),
    ("█", "ice_thick", "is"),
    ("≈", "ice_open", "öppet vatten"),
    None, ("Sonar hörde:", "dim", ""), ("◦", "heard_ping", "ping"), ("↓", "heard_splash", "plask"),
    ("✱", "heard_explosion", "detonation"),
    ("⊥", "heard_buoy", "boj"), ("~", "heard_other", "telefon"),
    ("!", "own_sound", "egen ping"), ("»", "own_sound", "avfyring"), ("o", "own_sound", "skenmål"),
    ("✱", "near", "nära"),
]


def known_bottom(view: ProfileView, t0: int) -> list[float]:
    """Bottendjup besättningen känner i bilden: sjökortet längs besticket och lodningarna."""
    return ([d for t, d in view.chart_bottom if t >= t0]
            + [b.depth for b in view.bottom if b.t + BOTTOM_VALID_S >= t0])


def auto_time_zoom(view: ProfileView, width: int) -> int:
    """Minsta tidsskala vars fönster rymmer hela historiken, så att spåret fyller profilen
    redan i början av ett spel (största skalan när historiken är längre än så)."""
    trace = view.trace
    history = view.now - trace[0][0] if trace else 0
    for i, spc in enumerate(TIME_ZOOM):
        if max(10, width) * spc >= history:
            return i
    return len(TIME_ZOOM) - 1


def auto_depth_zoom(view: ProfileView, t0: int) -> int:
    """Minsta skala som rymmer vårt djup, beordrat djup, isens kölar och grund botten."""
    shallow = [d for d in known_bottom(view, t0) if d * 1.15 + 5 <= DEPTH_ZOOM[-1]]
    deepest = max([view.depth, view.ordered_depth]
                  + [d for t, d in view.trace if t >= t0]
                  + [s.draft for s in view.ice if s.t >= t0]
                  + ([min(shallow)] if shallow else []))
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
        self.dots = DotLayer(cols, rows)

    def put(self, c: int, r: int, ch: str, style: str) -> None:
        if 0 <= c < self.cols and 0 <= r < self.rows:
            self.ch[r][c], self.st[r][c] = ch, style

    def get(self, c: int, r: int) -> str:
        return self.ch[r][c] if 0 <= c < self.cols and 0 <= r < self.rows else ""

    def text(self, c: int, r: int, s: str, style: str) -> None:
        for i, ch in enumerate(s):
            self.put(c + i, r, ch, style)

    def line(self, r: int) -> Text:
        """Raden: tecknen, och prickarna där rutan är tom."""
        t = Text(no_wrap=True, overflow="crop")
        for c, (ch, st) in enumerate(zip(self.ch[r], self.st[r])):
            if ch == " ":
                d = self.dots.cell(r, c)
                if d is not None:
                    ch, st = d[0], d[1]
            t.append(ch, style=st)
        return t


DOTTED_LEVELS = {"─": 1, "┄": 2, "╌": 3}      # tunna nivåer i prickar: streckens längd


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
    chart_cols = _per_column(view.chart_bottom, col_of, cols)
    known = known_bottom(view, t0)
    band = 1 + BAND_ROWS                            # bruten axel + bottenbandet
    plot_rows = max(4, height - 1 - 1 - band)      # tidsaxel överst, ljud underst
    need = max_depth / (plot_rows - 1)
    dpr = next((m for m in ROW_METERS if m >= need), need)
    max_depth = dpr * (plot_rows - 1)
    if known and min(known) <= max_depth:          # grunt: botten ritas i bilden
        band = 0
        plot_rows = max(4, height - 1 - 1)
        need = max_depth / (plot_rows - 1)
        dpr = next((m for m in ROW_METERS if m >= need), need)
        max_depth = dpr * (plot_rows - 1)

    def row_of(d: float) -> int:
        return min(plot_rows - 1, max(0, round(d / dpr)))

    def dot_x(t: float) -> float:
        return 2 * (cols - 1 - (now - t) / sec_per_col) + 1

    def dot_y(d: float) -> float:
        return min(4 * plot_rows - 1, max(0.0, 4 * d / dpr + 1.5))

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
        if lv.char in DOTTED_LEVELS:                  # tunn linje vid det exakta djupet
            y = dot_y(lv.depth)
            g.dots.line(0, y, 2 * cols - 1, y, st, dash=DOTTED_LEVELS[lv.char])
        else:
            for c in range(cols):
                g.put(c, r, lv.char, st)
        right[r] = Text(f" {lv.label}", style=st)
        left[r] = Text(f"{lv.depth:>{MARGIN - 2}.0f} ┼", style=st)

    # botten i bilden (grunt vatten): sjökortets djup och lodningarna
    if not band:
        pts = [(2 * c + 1, dot_y(d)) for c, d in sorted(chart_cols.items()) if d <= max_depth]
        g.dots.polyline(pts, STYLE["chart_bottom"], prio=1)
        if chart_cols:
            c_last = max(chart_cols)
            d = chart_cols[c_last]
            if d <= max_depth:
                right[row_of(d)] = Text(f" kortet {fmt_m(d)}", style=STYLE["chart_bottom"])
        for c, (d, fresh) in _sounded_columns(view, bottoms, col_of, cols).items():
            st = STYLE["bottom" if fresh else "bottom_old"]
            if d > max_depth:
                continue                              # djupare än bilden: bara en ▾ nedan
            for r in range(row_of(d), plot_rows):
                g.put(c, r, "▓", st)
        for b in bottoms:
            if b.depth > max_depth:
                g.put(col_of(b.t), plot_rows - 1, "▾", STYLE["bottom_old"])
        if bottoms and bottoms[-1].depth <= max_depth:
            right[row_of(bottoms[-1].depth)] = Text(f" ekolod {fmt_m(bottoms[-1].depth)}",
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

    # vårt djup: en sammanhängande linje i prickar genom navigatörens djuplogg
    pts = [(dot_x(t), dot_y(d)) for t, d in view.trace if t >= t0 - sec_per_col]
    if len(pts) == 1:
        g.dots.dot(*pts[0], STYLE["trace"], prio=2)
    g.dots.polyline(pts, STYLE["trace"], prio=2)

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
        lines.extend(_bottom_band(view, bottoms, chart_cols, cols, col_of))
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


def _per_column(points, col_of, cols: int) -> dict[int, float]:
    """Medelvärde per kolumn av (t, värde)."""
    acc: dict[int, list[float]] = {}
    for t, d in points:
        c = col_of(t)
        if 0 <= c < cols:
            acc.setdefault(c, []).append(d)
    return {c: sum(v) / len(v) for c, v in acc.items()}


def _sounded_columns(view: ProfileView, bottoms, col_of, cols: int) -> dict[int, tuple[float, bool]]:
    """Kolumner där en lodning gäller: (djup, färsk). En lodning gäller till nästa
    eller BOTTOM_VALID_S framåt."""
    out: dict[int, tuple[float, bool]] = {}
    now = view.now
    for i, b in enumerate(bottoms):
        end = bottoms[i + 1].t if i + 1 < len(bottoms) else b.t + BOTTOM_VALID_S
        fresh = now - b.t < BOTTOM_VALID_S
        for c in range(max(0, col_of(b.t)), min(cols, col_of(min(end, now)) + 1)):
            out[c] = (b.depth, fresh)
    return out


def _bottom_band(view: ProfileView, bottoms, chart_cols: dict[int, float], cols: int,
                 col_of) -> list[Text]:
    """Botten under den brutna axeln: BAND_ROWS rader med egen skala."""
    brk = Text(" " * (MARGIN - 1) + "┊", style=STYLE["axis"])
    brk.append(("≈ " * cols)[:cols], style=STYLE["dim"])
    brk.append(_pad(Text(" axeln bruten", style=STYLE["dim"])))

    sounded = _sounded_columns(view, bottoms, col_of, cols)
    values = list(chart_cols.values()) + [d for d, _ in sounded.values()]
    g = _Grid(cols, BAND_ROWS)
    left = [Text(" " * (MARGIN - 1) + "│", style=STYLE["axis"]) for _ in range(BAND_ROWS)]
    right = [Text("") for _ in range(BAND_ROWS)]
    if not values:
        g.text(max(0, cols // 2 - 14), BAND_ROWS // 2, " ekolod ger bottendjupet ", STYLE["dim"])
        right[BAND_ROWS // 2] = Text(" botten okänd", style=STYLE["dim"])
        left[BAND_ROWS // 2] = Text(f"{'?':>{MARGIN - 2}} ┤", style=STYLE["axis"])
        return [brk] + [Text.assemble(left[r], g.line(r), _pad(right[r]))
                        for r in range(BAND_ROWS)]

    lo = math.floor(min(values) / 100) * 100
    hi = max(lo + 100 * (BAND_ROWS - 1), math.ceil(max(values) / 100) * 100)
    step = (hi - lo) / (BAND_ROWS - 1)

    def row_of(d: float) -> int:
        return min(BAND_ROWS - 1, max(0, round((d - lo) / step)))

    for r in range(BAND_ROWS):
        left[r] = Text(f"{fmt_m(lo + r * step):>{MARGIN - 2}} ┤", style=STYLE["axis"])
    pts = [(2 * c + 1, min(4 * BAND_ROWS - 1, max(0.0, 4 * (d - lo) / step + 1.5)))
           for c, d in sorted(chart_cols.items())]
    g.dots.polyline(pts, STYLE["chart_bottom"], prio=1)
    for c, (d, fresh) in sounded.items():
        for r in range(row_of(d), BAND_ROWS):
            g.put(c, r, "▓", STYLE["bottom" if fresh else "bottom_old"])
    # okända sträckor (varken kort eller lodning) får ett frågetecken i mitten
    run_start = None
    for c in range(cols + 1):
        empty = c < cols and all(g.get(c, r) == " " and g.dots.cell(r, c) is None
                                 for r in range(BAND_ROWS))
        if empty and run_start is None:
            run_start = c
        elif not empty and run_start is not None:
            if c - run_start >= 3:
                g.put((run_start + c) // 2, BAND_ROWS // 2, "?", STYLE["dim"])
            run_start = None
    if chart_cols:
        d = chart_cols[max(chart_cols)]
        right[row_of(d)] = Text(f" kortet {fmt_m(d)}", style=STYLE["chart_bottom"])
    if bottoms:
        b = bottoms[-1]
        r = row_of(b.depth)
        if chart_cols and r == row_of(chart_cols[max(chart_cols)]):
            r = min(BAND_ROWS - 1, r + 1) if r < BAND_ROWS - 1 else r - 1
        right[r] = Text(f" ekolod {clock(view.start_clock + b.t)[:5]}", style=STYLE["bottom"])
    return [brk] + [Text.assemble(left[r], g.line(r), _pad(right[r])) for r in range(BAND_ROWS)]


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
                         _pad(Text(" sonar hörde", style=STYLE["dim"])))


def legend() -> Text:
    t = Text(" ", no_wrap=True, overflow="crop")
    for item in LEGEND:
        if item is None:
            t.append("\n ")
            continue
        sym, style, what = item
        if style == "near":                       # omvänt tecken: ljudet var nära
            t.append(sym, style=STYLE["heard_explosion"] + " reverse")
        else:
            t.append(sym, style=STYLE[style])
        t.append(f" {what}  " if what else " ", style="dim")
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

    chart = view.chart_bottom
    if chart:
        d = chart[-1][1]
        row(d, 3, f"~{fmt_m(d)}", "~~", "kortet", STYLE["chart_bottom"])
    b = view.latest_bottom()
    if b is not None:
        fresh = view.now - b.t < BOTTOM_VALID_S
        row(b.depth, 4, f"{fmt_m(b.depth)}", "▓▓", f"ekolod {clock(view.start_clock + b.t)[:5]}",
            STYLE["bottom" if fresh else "bottom_old"])
    else:
        row(10**6, 4, "?", "▓▓", "ekolod ej lodat", STYLE["dim"])

    rows.sort(key=lambda x: (x[0], x[1]))
    head = Text(" DJUPMÄTARE", style="bold")
    return [head] + [r[2] for r in rows]
