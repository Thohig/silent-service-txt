"""Rastrering av sonarvyns vattenfall (rich, inte Textual – går att testa direkt).

Bäring vågrätt (hela varvet, `center` i mitten), tid lodrätt med det nyaste överst. Varje
kontakts bäringar ritas med brailleprickar (`DotLayer`, 2 × 4 per ruta); ett starkt ljud
tänder fler prickar än ett svagt. Till vänster en smal marginal för våra egna girar och
ljud, till höger klockslagen. Allt kommer ur `SonarView`, alltså ur kunskapen.
"""
from __future__ import annotations

from rich.text import Text

from sim.fmt import fmt_course
from sim.geo import angle_diff, norm360
from sim.sonar_view import (BearingTrace, ContactLine, drift_words, HeardMark, LostMark, OwnMark, OwnTurn, SolutionTrace,
                            SonarView, TargetTurn, TorpedoTrace)

from .canvas import Canvas, DotLayer
from .widgets import QUALITY_STYLE

LEFT = 2                         # marginal för egna girar och egna ljud
RIGHT = 6                        # klockslagen
HEAD_ROWS = 2                    # bäringsskalan och linjalen
MIN_BODY_ROWS = 4
LINES_SHARE = 4                  # kontaktraderna tar högst var fjärde rad
TIME_STEPS_S = (60, 120, 300, 600, 900, 1800, 3600)
TIME_LABEL_MIN_ROWS = 4          # klockslag högst så här tätt
BEARING_STEPS = (10, 15, 30, 45, 90)
BEARING_LABEL_MIN_COLS = 7
JOIN_GAP_S = 30                  # bäringar närmare i tid än så binds ihop med en linje …
JOIN_MAX_DEG = 12.0              # … om bäringen inte hoppat mer (annars blir det vågräta streck)
STRONG_SE = 20.0                 # dB: tre prickar breda
MEDIUM_SE = 6.0                  # dB: två

STYLE = {
    "threat": "bold #ff7f5f",
    "contact": "bold #e8c860",
    "civil": "#a8b890",
    "benign": "#5f7a68",
    "friendly": "bold #5fd7ff",
    "torpedo": "bold #ff3f5f",          # fientlig torped: starkare än hoten
    "own_torpedo": "#d0c8ff",           # vår egen
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
    "target_turn": "bold #f0ead2",
    "own_turn": "bold #c8d0b0",
    "own_turn_line": "#33463a",
}
SOLUTION_PRIO = 1.0
NEUTRAL_SOLUTION_PRIO = 0.5
SOLUTION_DASH = 2
QUIET_MARKS = {"ping", "buoy_ping"}
BACKGROUND = {"┊", "╌"}                 # rutnätet och girlinjen: bakom prickarna     # täta: ritas bara där inget annat står
TRACE_PRIO = 2.0
TORPEDO_PRIO = 3.0              # en fientlig torped vinner över allt där spåren korsar
NEUTRAL_PRIO = 1.5              # neutrala spår under hotens (men över lösningarna)


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


NEUTRAL_KINDS = ("civil", "benign")     # handelsfartyg, isljud, drivstationen: tonas ned


def kind_style(kind: str, held: bool = True) -> str:
    st = STYLE.get(kind, STYLE["contact"])
    return st if held and kind not in NEUTRAL_KINDS else f"{st} dim"


def render_sonar(view: SonarView, width: int, height: int, window_s: int = 1800,
                 center: float = 0.0, relative: bool = False,
                 show_solution: bool = False) -> list[Text]:
    """Vattenfallet i `width` × `height` tecken, med en rad per kontakt under."""
    contact_lines = view.lines
    foot_room = max(0, height - HEAD_ROWS - MIN_BODY_ROWS)    # vattenfallet går före
    n_lines = min(len(contact_lines), max(1, height // LINES_SHARE), foot_room)
    if n_lines and len(contact_lines) > n_lines:
        n_lines -= 1                 # sista raden säger hur många fler
    more = len(contact_lines) - n_lines if foot_room else 0
    foot = n_lines + (1 if more else 0)
    cols = max(8, width - LEFT - RIGHT)
    rows = max(MIN_BODY_ROWS, height - HEAD_ROWS - foot)
    wf = Waterfall(view, cols, rows, window_s, center, relative)
    canvas = Canvas(LEFT + cols + RIGHT, HEAD_ROWS + rows, STYLE["base"])
    dots = DotLayer(cols, rows)
    over: dict[tuple[int, int], tuple[str, str]] = {}       # hela tecken ovanpå prickarna

    _bearing_axis(canvas, wf)
    _grid(over, wf)
    if show_solution:
        for sol in view.of(SolutionTrace):
            _solution(dots, wf, sol)
    # hoten först: deras etiketter får platsen, och deras prickar vinner där spåren korsar
    torpedoes = view.of(TorpedoTrace)
    for tp in torpedoes:
        if tp.hostile:
            _torpedo(dots, over, wf, tp)
    for tr in sorted(view.traces, key=lambda tr: tr.kind in NEUTRAL_KINDS):
        _trace(dots, over, wf, tr)
    for tp in torpedoes:
        if not tp.hostile:
            _torpedo(dots, over, wf, tp)
    _heard(dots, over, wf, view)
    _target_turns(dots, over, wf, view)
    _own_turns(dots, over, wf, view)
    _time_axis(canvas, wf)
    _own_marks(canvas, wf, view)

    for r in range(rows):
        for c in range(cols):
            if (r, c) in over and over[(r, c)][0] not in BACKGROUND:
                ch, st = over[(r, c)]
            elif (cell := dots.cell(r, c)) is not None:
                ch, st = cell[0], cell[1]
            elif (r, c) in over:
                ch, st = over[(r, c)]
            else:
                continue
            canvas.put(HEAD_ROWS + r, LEFT + c, ch, st)
    out = canvas.lines()
    out.extend(contact_line(c, width) for c in contact_lines[:n_lines])
    if more:
        out.append(Text(f" … och {more} till", style="dim", no_wrap=True, overflow="crop"))
    return out


def contact_line(c: ContactLine, width: int) -> Text:
    """Sonarrummets och plottets ord om en kontakt: klassning, bäring, drift, lösning."""
    t = Text(" ", no_wrap=True, overflow="crop")
    t.append(f"{c.designation:<5}", style=kind_style(c.kind, c.held))
    t.append(f" bäring {fmt_course(c.bearing)}", style="" if c.held else "dim")
    drift = drift_words(c.drift) if c.held else "tappad"
    t.append(f"  {drift:<22}", style="" if c.held else "dim")
    t.append(" lösning ")
    if c.solution_quality is None:
        t.append(f"{'ingen':<7}", style="dim")
    else:
        t.append(f"{c.solution_quality.label:<7}", style=QUALITY_STYLE[c.solution_quality])
    t.append(f"  {c.classification}", style="" if c.held else "dim")
    t.append(f" ({c.class_quality.label})", style=QUALITY_STYLE[c.class_quality])
    if c.kind in NEUTRAL_KINDS:
        t.stylize("dim")                # neutral: hela raden nedtonad, hoten står ut
    t.truncate(width)
    return t


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
    prio = NEUTRAL_PRIO if tr.kind in NEUTRAL_KINDS else TRACE_PRIO
    newest = _dots(dots, wf, tr.points, style, prio)
    if newest is not None and tr.held:          # en tappad kontakt får sin etikett vid ∅
        _label(over, wf, newest, tr.designation, style)


def _torpedo(dots: DotLayer, over: dict, wf: Waterfall, tp: TorpedoTrace) -> None:
    """En torped som sonar hör: fientliga i torpedfärg över allt annat, våra egna dämpade.
    Etiketten står vid den nyaste bäringen, dämpad som spåret när sonar inte hör den längre."""
    style = STYLE["torpedo" if tp.hostile else "own_torpedo"]
    if not tp.held:
        style += " dim"
    newest = _dots(dots, wf, tp.points, style, TORPEDO_PRIO if tp.hostile else TRACE_PRIO)
    if newest is not None:
        _label(over, wf, newest, tp.label, style)


def _dots(dots: DotLayer, wf: Waterfall, points, style: str, prio: float) -> tuple[float, float] | None:
    """Bäringarna som prickar (bredare ju starkare), bundna med linjer där de ligger tätt;
    ger den nyaste punkten (för etiketten)."""
    prev: tuple[int, float, float] | None = None
    newest: tuple[float, float] | None = None
    for t, b, se in points:
        y = wf.y(t)
        if y is None:
            prev = None
            continue
        x = wf.x(wf.bearing(t, b))
        dots.dot(x, y, style, prio)
        if se >= MEDIUM_SE:
            dots.dot(x + 1, y, style, prio)
        if se >= STRONG_SE:
            dots.dot(x - 1, y, style, prio)
        if prev is not None and t - prev[0] <= JOIN_GAP_S and \
                abs(x - prev[1]) <= JOIN_MAX_DEG / 360.0 * wf.w:
            dots.line(prev[1], prev[2], x, y, style, prio)
        prev = (t, x, y)
        if newest is None or y < newest[1]:
            newest = (x, y)
    return newest


def _label(over: dict, wf: Waterfall, at: tuple[float, float], text: str, style: str) -> None:
    """Beteckningen bredvid spårets nyaste punkt, där det finns plats."""
    r, c = int(at[1]) // 4, int(at[0]) // 2
    start = c + 2 if c + 2 + len(text) <= wf.cols else c - 1 - len(text)
    if start < 0:
        return
    for col in range(start - 1, start + len(text) + 1):     # en ledig ruta före och efter: "S-3S-5"
        cur = over.get((r, col))
        if cur is not None and cur[0] not in BACKGROUND:
            return
    for i, ch in enumerate(text):
        over[(r, start + i)] = (ch, style)


# --- det sonar hört -----------------------------------------------------------------
def _free(dots: DotLayer, over: dict, r: int, c: int) -> bool:
    cur = over.get((r, c))
    return dots.cell(r, c) is None and (cur is None or cur[0] in BACKGROUND)


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
    """Våra egna ljud (aktiv ping, avfyring, skenmål, nödblåsning) och girar i
    vänstermarginalen."""
    for turn in view.of(OwnTurn):
        r = wf.row(turn.t)
        if r is not None:
            canvas.put(HEAD_ROWS + r, 1, own_turn_label(turn), STYLE["own_turn"])
    for m in view.of(OwnMark):
        r = wf.row(m.t)
        if r is not None:
            canvas.put(HEAD_ROWS + r, 0, m.symbol[0], STYLE["own_sound"])


# --- plottet och våra girar -----------------------------------------------------------
def _solution(dots: DotLayer, wf: Waterfall, sol: SolutionTrace) -> None:
    """Plottets lösning: de bäringar den förutsäger, streckat i kvalitetens färg. Där
    spåret och lösningen glider isär stämmer lösningen inte längre."""
    neutral = sol.kind in NEUTRAL_KINDS
    style = QUALITY_STYLE[sol.quality] + (" dim" if neutral else "")
    prio = NEUTRAL_SOLUTION_PRIO if neutral else SOLUTION_PRIO
    pts = []
    for t, b in sol.points:
        y = wf.y(t)
        if y is not None:
            pts.append((wf.x(wf.bearing(t, b)), y))
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(x1 - x0) <= JOIN_MAX_DEG / 360.0 * wf.w:
            dots.line(x0, y0, x1, y1, style, prio, dash=SOLUTION_DASH)


def _target_turns(dots: DotLayer, over: dict, wf: Waterfall, view: SonarView) -> None:
    """Där plottet märkte att målet girat: ⟩ eller ⟨ bredvid spåret, mot den sida där
    det finns plats, och "gir"."""
    for turn in view.of(TargetTurn):
        r = wf.row(turn.t)
        if r is None:
            continue
        x = wf.x(wf.bearing(turn.t, turn.bearing))
        _label(over, wf, (x, 4 * r), "‹gir", STYLE["target_turn"])


def _own_turns(dots: DotLayer, over: dict, wf: Waterfall, view: SonarView) -> None:
    """Våra girar: pil i vänstermarginalen (läggs på ritytan i `_own_turn_arrows`) och en
    svag streckad linje tvärs över där inget annat står; där knäcker bäringskurvorna."""
    for turn in view.of(OwnTurn):
        r = wf.row(turn.t)
        if r is None:
            continue
        for c in range(wf.cols):
            if _free(dots, over, r, c) and c % 2 == 0:
                over[(r, c)] = ("╌", STYLE["own_turn_line"])


def own_turn_label(turn: OwnTurn) -> str:
    """↻ styrbord, ↺ babord."""
    return "↻" if angle_diff(turn.course_to, turn.course_from) > 0 else "↺"
