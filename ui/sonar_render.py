"""Rastrering av sonarvyns vattenfall (rich, inte Textual – går att testa direkt).

Bäring vågrätt (hela varvet, `center` i mitten), tid lodrätt med det nyaste överst. Varje
kontakts bäringar ritas med brailleprickar (`DotLayer`, 2 × 4 per ruta); ett starkt ljud
tänder fler prickar än ett svagt. Till vänster en smal marginal för våra egna girar och
ljud, till höger klockslagen. Allt kommer ur `SonarView`, alltså ur kunskapen.
"""
from __future__ import annotations

from rich.text import Text

from sim.geo import angle_diff, norm360
from sim.sonar_view import BearingTrace, HeardMark, LostMark, OwnMark, SonarView

from .canvas import Canvas, DotLayer

LEFT = 2                         # marginal för egna girar och egna ljud
RIGHT = 6                        # klockslagen
HEAD_ROWS = 2                    # bäringsskalan och linjalen
MIN_BODY_ROWS = 4
TIME_STEPS_S = (60, 120, 300, 600, 900, 1800, 3600)
TIME_LABEL_MIN_ROWS = 4          # klockslag högst så här tätt
BEARING_STEPS = (10, 15, 30, 45, 90)
BEARING_LABEL_MIN_COLS = 7
JOIN_GAP_S = 30                  # bäringar närmare i tid än så binds ihop med en linje …
JOIN_MAX_DEG = 12.0              # … om bäringen inte hoppat mer (annars blir det vågräta streck)
STRONG_SE = 12.0                 # dB: tre prickar breda
MEDIUM_SE = 4.0                  # dB: två

STYLE = {
    "threat": "bold #ff7f5f",
    "contact": "bold #e8c860",
    "civil": "#a8b890",
    "benign": "#5f7a68",
    "friendly": "bold #5fd7ff",
    "axis": "#7f9a80",
    "ruler": "#2f4a36",
    "grid": "#18241b",
    "bow": "bold bright_white",
    "label": "#c8d0b0",
    "time": "#7f9a80",
    "base": "#0b0f0c",
    # det sonar hört (som djupprofilen) och våra egna ljud
    "heard_ping": "cyan",
    "heard_splash": "bold yellow",
    "heard_explosion": "bold red",
    "heard_practice": "yellow",
    "heard_buoy": "#c6a0ff",
    "heard_other": "cyan",
    "own_sound": "bold white",
    "lost": "#b8b4a4",
}
QUIET_MARKS = {"ping", "buoy_ping"}     # täta: ritas bara där inget annat står
TRACE_PRIO = 2.0


class Waterfall:
    """Geometrin: bäring och tid till prickar och rutor."""

    def __init__(self, view: SonarView, cols: int, rows: int, window_s: int, center: float,
                 relative: bool) -> None:
        self.view, self.cols, self.rows = view, cols, rows
        self.window_s, self.center, self.relative = window_s, center, relative
        self.w, self.h = 2 * cols, 4 * rows

    def bearing(self, t: int, b: float) -> float:
        """Bäringen som den ritas: sann, eller relativt fören vid tiden t."""
        return norm360(b - self.view.heading_at(t)) if self.relative else b

    def x(self, b: float) -> float:
        """Prickkolumn för en (ritad) bäring; `center` i mitten, varvet runt."""
        off = angle_diff(b, self.center)
        return min(self.w - 1e-3, (off + 180.0) / 360.0 * self.w)

    def y(self, t: int) -> float | None:
        """Prickrad för en tid, eller None om den ligger utanför fönstret."""
        age = self.view.now - t
        if age < 0 or age >= self.window_s:
            return None
        return age / self.window_s * self.h

    def col(self, b: float) -> int:
        return int(self.x(b)) // 2

    def row(self, t: int) -> int | None:
        y = self.y(t)
        return None if y is None else int(y) // 4


def kind_style(kind: str, held: bool = True) -> str:
    st = STYLE.get(kind, STYLE["contact"])
    return st if held else f"{st} dim"


def render_sonar(view: SonarView, width: int, height: int, window_s: int = 1800,
                 center: float = 0.0, relative: bool = False,
                 show_solution: bool = False) -> list[Text]:
    """Vattenfallet i `width` × `height` tecken."""
    cols = max(8, width - LEFT - RIGHT)
    rows = max(MIN_BODY_ROWS, height - HEAD_ROWS)
    wf = Waterfall(view, cols, rows, window_s, center, relative)
    canvas = Canvas(LEFT + cols + RIGHT, HEAD_ROWS + rows, STYLE["base"])
    dots = DotLayer(cols, rows)
    over: dict[tuple[int, int], tuple[str, str]] = {}       # hela tecken ovanpå prickarna

    _bearing_axis(canvas, wf)
    _grid(over, wf)
    for tr in view.traces:
        _trace(dots, over, wf, tr)
    _heard(dots, over, wf, view)
    _time_axis(canvas, wf)
    _own_marks(canvas, wf, view)

    for r in range(rows):
        for c in range(cols):
            if (r, c) in over and over[(r, c)][0] != "┊":
                ch, st = over[(r, c)]
            elif (cell := dots.cell(r, c)) is not None:
                ch, st = cell[0], cell[1]
            elif (r, c) in over:
                ch, st = over[(r, c)]
            else:
                continue
            canvas.put(HEAD_ROWS + r, LEFT + c, ch, st)
    return canvas.lines()


# --- axlar ------------------------------------------------------------------------
def bearing_step(cols: int) -> int:
    for step in BEARING_STEPS:
        if cols * step / 360.0 >= BEARING_LABEL_MIN_COLS:
            return step
    return BEARING_STEPS[-1]


def _bearing_label(b: int, relative: bool) -> str:
    if not relative:
        return f"{b % 360:03d}"
    b %= 360
    return {0: "för", 90: "sb", 180: "akter", 270: "bb"}.get(b, f"{b:03d}")


def _bearing_axis(canvas: Canvas, wf: Waterfall) -> None:
    step = bearing_step(wf.cols)
    canvas.text(1, LEFT, "─" * wf.cols, STYLE["ruler"])
    for b in range(0, 360, step):
        c = LEFT + wf.col(b)
        canvas.put(1, c, "┼", STYLE["ruler"])
        canvas.centered(0, c, _bearing_label(b, wf.relative), STYLE["axis"])
    if wf.relative:                 # norr, sett från fören nu
        canvas.put(1, LEFT + wf.col(norm360(-wf.view.course)), "N", STYLE["bow"])
    else:                           # fören
        canvas.put(1, LEFT + wf.col(wf.view.course), "F", STYLE["bow"])


def _grid(over: dict, wf: Waterfall) -> None:
    """Svaga lodräta linjer vid skalans bäringar, bakom spåren."""
    step = bearing_step(wf.cols)
    for b in range(0, 360, step):
        c = wf.col(b)
        for r in range(wf.rows):
            over[(r, c)] = ("┊", STYLE["grid"])


def time_step(window_s: int, rows: int) -> int:
    for step in TIME_STEPS_S:
        if step / window_s * rows >= TIME_LABEL_MIN_ROWS:
            return step
    return TIME_STEPS_S[-1]


def _time_axis(canvas: Canvas, wf: Waterfall) -> None:
    """Klockslag i högermarginalen vid jämna minuter, "nu" överst."""
    col = LEFT + wf.cols
    canvas.text(HEAD_ROWS, col, "◂ nu", STYLE["time"])
    step = time_step(wf.window_s, wf.rows)
    now_clock = wf.view.start_clock + wf.view.now
    first = now_clock - now_clock % step
    for k in range(0, wf.window_s // step + 2):
        clock = first - k * step
        r = wf.row(clock - wf.view.start_clock)
        if r is None or r < 1:
            continue
        hh, mm = (clock // 3600) % 24, (clock // 60) % 60
        canvas.text(HEAD_ROWS + r, col, f"─{hh:02d}:{mm:02d}", STYLE["time"])


# --- spåren -----------------------------------------------------------------------
def _trace(dots: DotLayer, over: dict, wf: Waterfall, tr: BearingTrace) -> None:
    style = kind_style(tr.kind, tr.held)
    prev: tuple[int, float, float] | None = None
    newest: tuple[float, float] | None = None
    for t, b, se in tr.points:
        y = wf.y(t)
        if y is None:
            prev = None
            continue
        x = wf.x(wf.bearing(t, b))
        dots.dot(x, y, style, TRACE_PRIO)
        if se >= MEDIUM_SE:
            dots.dot(x + 1, y, style, TRACE_PRIO)
        if se >= STRONG_SE:
            dots.dot(x - 1, y, style, TRACE_PRIO)
        if prev is not None and t - prev[0] <= JOIN_GAP_S and \
                abs(x - prev[1]) <= JOIN_MAX_DEG / 360.0 * wf.w:
            dots.line(prev[1], prev[2], x, y, style, TRACE_PRIO)
        prev = (t, x, y)
        if newest is None or y < newest[1]:
            newest = (x, y)
    if newest is not None:
        _label(over, wf, newest, tr.designation, style)


def _label(over: dict, wf: Waterfall, at: tuple[float, float], text: str, style: str) -> None:
    """Beteckningen bredvid spårets nyaste punkt, där det finns plats."""
    r, c = int(at[1]) // 4, int(at[0]) // 2
    start = c + 2 if c + 2 + len(text) <= wf.cols else c - 1 - len(text)
    if start < 0:
        return
    for i, ch in enumerate(text):
        cur = over.get((r, start + i))
        if cur is not None and cur[0] != "┊":
            return
    for i, ch in enumerate(text):
        over[(r, start + i)] = (ch, style)


# --- det sonar hört -----------------------------------------------------------------
def _free(dots: DotLayer, over: dict, r: int, c: int) -> bool:
    cur = over.get((r, c))
    return dots.cell(r, c) is None and (cur is None or cur[0] == "┊")


def _heard(dots: DotLayer, over: dict, wf: Waterfall, view: SonarView) -> None:
    """Transienter som tecken vid sin bäring och tid; tappade kontakter som ∅ med
    beteckningen. Pingar är täta och står bara där inget annat står."""
    for m in sorted(view.of(HeardMark), key=lambda m: m.t):
        r = wf.row(m.t)
        if r is None:
            continue
        c = wf.col(wf.bearing(m.t, m.bearing))
        if m.kind in QUIET_MARKS and not _free(dots, over, r, c):
            continue
        over[(r, c)] = (m.symbol[0], STYLE.get(m.style, "white"))
    for lost in view.of(LostMark):
        r = wf.row(lost.t)
        if r is None:
            continue
        x = wf.x(wf.bearing(lost.t, lost.bearing))
        over[(r, int(x) // 2)] = ("∅", STYLE["lost"])
        _label(over, wf, (x, 4 * r), lost.designation, STYLE["lost"])


def _own_marks(canvas: Canvas, wf: Waterfall, view: SonarView) -> None:
    """Våra egna ljud (aktiv ping, avfyring, skenmål, nödblåsning) i vänstermarginalen."""
    for m in view.of(OwnMark):
        r = wf.row(m.t)
        if r is not None:
            canvas.put(HEAD_ROWS + r, 0, m.symbol[0], STYLE["own_sound"])
