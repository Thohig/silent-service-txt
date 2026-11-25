"""Ritar systemtavlan: genomskärning av ubåten överst, panelerna under."""
from __future__ import annotations

import math

from rich.text import Text

from sim.systems import (DANGER, INFO, OFF, OK, SEVERITY, WARN, Compartment, Flooding, Gauge,
                         SystemsView, TubeRack, TrimTanks)

from .canvas import Canvas, DotLayer
from .placards import PANEL_RU, RU_STYLE

STATE_STYLE = {OK: "#8fbf8f", INFO: "#c8d0b0", OFF: "#6f7f70", WARN: "bold yellow",
               DANGER: "bold red"}
STATE_MARK = {OK: "·", INFO: " ", OFF: "○", WARN: "▲", DANGER: "■"}
CELL_BG = {WARN: "on #3a3410", DANGER: "on #4a1010"}
HULL = "#5f8a66"
WATER = "bold #5fafff"
TITLE = "bold #c8d0b0"
ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
LABEL_W = 14
BAR_W = 10
TUBE_W = 17
GAP = 3


def _center(s: str, w: int) -> str:
    s = s[:w]
    left = (w - len(s)) // 2
    return " " * left + s + " " * (w - len(s) - left)


# --- genomskärningen ----------------------------------------------------------------
HULL_ROWS = 7               # torn, överkant, tre textrader, kölsvin, underkant
BOW_COLS, STERN_COLS = 3, 6
TANK_W_DOTS, TANK_H_DOTS = 10.0, 4.0
TANK = "#6f8f9f"
CLOSED = "bold #ffaf00"          # stängda länsskott


def render_hull(comps: list[Compartment], flooding: Flooding | None, width: int,
                tanks: TrimTanks | None = None) -> list[Text]:
    """Genomskärningen: skrovet, tornet, skotten och vattnet i braille, avdelningarnas
    nummer, namn och läge som text (färg efter läget). Fören till vänster. Med trimtankarna
    står de som små rutor med sin vattennivå (för i I, utjämningstanken i III, akter i IX).
    Lutningen visas på panelen och libellen i centralen, inte här: ett lutande skrov med rak
    text blev svårläst."""
    if not comps:
        return []
    n = len(comps)
    cw = min(12, (width - BOW_COLS - STERN_COLS - 2 - (n - 1)) // n)
    if cw < 4:
        return []                           # för smalt för en genomskärning
    inner = n * cw + (n - 1)
    total = BOW_COLS + inner + STERN_COLS
    left = max(0, (width - total) // 2)
    ic0 = left + BOW_COLS                   # första kolumnen inne i skrovet
    ic1 = ic0 + inner - 1
    w = min(width, left + total + 1)
    c = Canvas(w, HULL_ROWS, "")
    dots = DotLayer(w, HULL_ROWS)
    y_top, y_bot = 6.0, 4.0 * (HULL_ROWS - 1) + 1
    cy, ry = (y_top + y_bot) / 2, (y_bot - y_top) / 2
    style_of = lambda cp: f"{STATE_STYLE[cp.state]} {CELL_BG.get(cp.state, '')}".strip()

    # avdelningarna: bakgrund vid varning/fara, nummer, namn och läge
    seps = []
    for i, cp in enumerate(comps):
        x = ic0 + i * (cw + 1)
        st = style_of(cp)
        for r in range(2, HULL_ROWS - 1):
            c.text(r, x, " " * cw, st)
        num = ROMAN[cp.no - 1] if cp.no <= len(ROMAN) else str(cp.no)
        for r, txt in ((2, num), (3, cp.name), (4, cp.note)):
            c.text(r, x, _center(txt, cw), st)
        if i:
            seps.append(x - 1)

    # vattnet: i varje avdelning efter hur full den är (skadekontrollen), annars i hela kölsvinet
    water_label = None
    per_room = any(cp.water > 0.01 for cp in comps)
    if flooding is not None and flooding.tons > 0.5:
        frac = min(1.0, flooding.tons / flooding.limit)
        spans = [(2 * (ic0 + i * (cw + 1)), 2 * (ic0 + i * (cw + 1) + cw), cp.water) for i, cp in enumerate(comps)] \
            if per_room else [(2 * ic0, 2 * (ic1 + 1), frac)]
        for x0, x1, f in spans:
            if f <= 0.01:
                continue
            level = y_bot - 1 - max(1.5, min(1.0, f) * (y_bot - y_top - 2))
            for yy in range(int(math.ceil(level)), int(y_bot)):
                for xx in range(x0, x1):
                    if yy <= level + 1 or (xx + yy) % 2 == 0:
                        dots.dot(xx, yy, WATER, prio=1)
        fill = "≈" if frac >= 0.2 else "~" if frac >= 0.05 else "·"
        label = f" {fill} {flooding.tons:.0f} ton vatten" + (", läcker" if flooding.leaking else "") \
            + (", skotten stängda " if flooding.closed else " ") + f"{fill} "
        if len(label) < inner:
            water_label = (ic0 + (inner - len(label)) // 2, label)

    # skrovet: rundad för, rak överkant och underkant, avsmalnande akter med propeller och roder
    x_bow = 2.0 * ic0
    x_aft = 2.0 * (ic1 + 1)
    tip = x_aft + 2.0 * (STERN_COLS - 2)

    def line(x0, y0, x1, y1):
        dots.line(x0, y0, x1, y1, HULL, prio=2)

    line(x_bow, y_top, x_aft, y_top)
    line(x_bow, y_bot, x_aft, y_bot)
    rx = 2.0 * BOW_COLS - 1
    for k in range(0, 61):
        a = math.pi / 2 + math.pi * k / 60
        dots.dot(x_bow + rx * math.cos(a), cy - ry * math.sin(a), HULL, prio=2)
    line(x_aft, y_top, tip, cy - 1.5)
    line(x_aft, y_bot, tip, cy + 1.5)
    line(tip + 1, cy - ry * 0.8, tip + 1, cy + ry * 0.8)                      # rodret
    c.put(int(cy // 4), int(tip // 2) + 1, "╪", HULL)                          # propellern
    # skotten mellan avdelningarna (stängda: gula)
    closed = flooding is not None and flooding.closed
    for sc in seps:
        dots.line(2 * sc + 1, y_top + 1, 2 * sc + 1, y_bot - 1, CLOSED if closed else HULL, prio=2)
    # tornet över centralen (III)
    sail_at = next((i for i, cp in enumerate(comps) if cp.no == 3), n // 3)
    sx0 = 2.0 * (ic0 + sail_at * (cw + 1)) + cw * 0.4
    sx1 = sx0 + cw * 1.2
    line(sx0, y_top, sx0 + 2, 1)
    line(sx0 + 2, 1, sx1 - 1, 1)
    line(sx1 - 1, 1, sx1, y_top)
    line((sx0 + sx1) / 2 + 1, 1, (sx0 + sx1) / 2 + 1, -3)                      # periskopet

    # trimtankarna i botten: för (I), utjämningstanken (III), akter (IX)
    if tanks is not None:
        where = {1: tanks.fore, 3: tanks.compensating, 9: tanks.aft}
        for i, cp in enumerate(comps):
            if cp.no not in where:
                continue
            tw = min(2.0 * cw - 4, TANK_W_DOTS)
            tx0 = 2.0 * (ic0 + i * (cw + 1)) + (2.0 * cw - tw) / 2
            tx1 = tx0 + tw
            ty0, ty1 = y_bot - 1 - TANK_H_DOTS, y_bot - 1
            for a, b in (((tx0, ty0), (tx1, ty0)), ((tx1, ty0), (tx1, ty1)),
                         ((tx1, ty1), (tx0, ty1)), ((tx0, ty1), (tx0, ty0))):
                dots.line(*a, *b, TANK, prio=3)
            fill = max(0.0, min(1.0, where[cp.no]))
            for yy in range(int(ty1) - 1, int(ty1 - 1 - round(fill * (TANK_H_DOTS - 1))), -1):
                dots.line(tx0 + 1, yy, tx1 - 1, yy, WATER, prio=3)

    rows = []
    for r in range(HULL_ROWS):
        for col in range(w):
            ch, st = c.cells[r][col]
            d = dots.cell(r, col)
            if d is not None and ch == " ":
                bg = st[st.index(" on "):] if " on " in st else (st if st.startswith("on ") else "")
                c.cells[r][col] = (d[0], f"{d[1]}{(' ' + bg.strip()) if bg else ''}")
        if water_label and r == HULL_ROWS - 2:          # etiketten ovanpå vattnet
            c.text(r, water_label[0], water_label[1], WATER)
        line = Text(no_wrap=True, overflow="crop")
        for ch, st in c.cells[r]:
            line.append(ch, style=st or None)
        line.rstrip()
        rows.append(line)
    return rows


# --- panelerna ------------------------------------------------------------------------
def _bar(level: float, style: str) -> Text:
    k = max(0, min(BAR_W, round(level * BAR_W)))
    t = Text("█" * k, style=style)
    t.append("░" * (BAR_W - k), style="#2f4a36")
    return t


def _gauge(g: Gauge, w: int) -> Text:
    style = STATE_STYLE.get(g.state, "")
    t = Text(no_wrap=True, overflow="ellipsis")
    t.append(STATE_MARK.get(g.state, " ") + " ", style=style)
    t.append(f"{g.label:<{LABEL_W}}", style="#7f9a80")
    room = w - 2 - LABEL_W
    if g.level is not None and room >= BAR_W + 8:
        t.append(_bar(g.level, style))
        t.append(" ")
        room -= BAR_W + 1
    t.append(g.text[:room] if len(g.text) > room else g.text, style=style)
    return t


def _tubes(rack: TubeRack, w: int) -> list[Text]:
    cells = []
    for n, load, loading, left in rack.tubes:
        c = Text(f"{n} ", style="#7f9a80")
        if load:
            c.append(f"{load:<{TUBE_W - 2}}", style="bold #c8d0b0")
        elif loading:
            c.append(f"{loading} {left // 60}:{left % 60:02d}".ljust(TUBE_W - 2), style="yellow")
        else:
            c.append(f"{'tom':<{TUBE_W - 2}}", style="#6f7f70")
        cells.append(c)
    per = max(1, (w - 2) // TUBE_W)
    out = []
    for i in range(0, len(cells), per):
        t = Text("  ", no_wrap=True, overflow="crop")
        for c in cells[i:i + per]:
            t.append(c)
        out.append(t)
    return out


def _panel(view: SystemsView, name: str, w: int, alarms_only: bool = False) -> list[Text]:
    head = Text(f"─ {name} ", style=TITLE, no_wrap=True)
    ru = PANEL_RU.get(name)
    if ru and len(name) + len(ru) + 6 <= w:
        head.append(f"{ru} ", style=RU_STYLE)
    head.append("─" * max(0, w - len(head.plain)), style="#2f4a36")
    rows = [head]
    gauges = view.gauges(name)
    if alarms_only:                 # trångt: bara det som varnar, allvarligast först
        gauges = sorted((g for g in gauges if SEVERITY[g.state] >= SEVERITY[WARN]),
                        key=lambda g: -SEVERITY[g.state])
    elif name == "VAPEN" and (rack := view.first(TubeRack)) is not None:
        rows.extend(_tubes(rack, w))
    rows.extend(_gauge(g, w) for g in gauges)
    return rows


def render_panels(view: SystemsView, width: int) -> list[Text]:
    ncol = 3 if width >= 120 else 2 if width >= 72 else 1
    pw = (width - GAP * (ncol - 1)) // ncol
    cols: list[list[Text]] = [[] for _ in range(ncol)]
    for name in view.panels():
        rows = _panel(view, name, pw)
        col = min(cols, key=len)            # kortaste kolumnen först
        if col:
            col.append(Text(""))
        col.extend(rows)
    height = max(len(c) for c in cols)
    out = []
    for i in range(height):
        t = Text(no_wrap=True, overflow="crop")
        for j, col in enumerate(cols):
            cell = col[i] if i < len(col) else Text("")
            cell = cell.copy()
            cell.truncate(pw, overflow="ellipsis", pad=True)
            t.append(cell)
            if j < ncol - 1:
                t.append(" " * GAP)
        out.append(t)
    return out


# --- kompakt: en kolumn i allvarsordning (vyn Ubåten) ---------------------------------
CALM_TEXT = "allt i ordning"
# lugna paneler fälls i den här ordningen (okända först, torpedrören sist)
FOLD_ORDER = ("SKADOR", "TRIM", "SAMBAND", "SONAR", "MASKIN", "NAVIGATION", "VAPEN")


def panel_state(view: SystemsView, name: str) -> str:
    return max((g.state for g in view.gauges(name)), key=SEVERITY.get, default=OK)


def _calm_rows(names: list[str], w: int) -> list[Text]:
    """Lugna paneler på en gemensam rad (radbryts vid behov): "· allt i ordning: MASKIN · SONAR"."""
    if not names:
        return []
    rows: list[Text] = []
    t = Text(no_wrap=True, overflow="ellipsis")
    t.append(STATE_MARK[OK] + " " + CALM_TEXT + ":", style=STATE_STYLE[OK])
    first = True
    for n in names:
        piece = (" " if first else " · ") + n
        if not first and len(t.plain) + len(piece) > w:
            rows.append(t)
            t = Text("  ", no_wrap=True, overflow="ellipsis")
            piece = n
        t.append(piece, style=TITLE)
        first = False
    rows.append(t)
    return rows


def render_compact_panels(view: SystemsView, width: int, height: int) -> list[Text]:
    """Panelerna i en kolumn, högst `height` rader: fara och varning först och fullt;
    får allt inte plats fälls lugna paneler (ok/info) efter `FOLD_ORDER` till en gemensam
    rad sist, och sedan visar de oroliga bara sina larm (varning och fara)."""
    names = sorted(view.panels(), key=lambda n: -SEVERITY[panel_state(view, n)])  # stabil
    full = {n: _panel(view, n, width) for n in names}
    calm = [n for n in names if SEVERITY[panel_state(view, n)] == 0]
    folded: list[str] = []

    def total() -> int:
        open_rows = sum(len(full[n]) for n in names if n not in folded)
        return open_rows + len(_calm_rows([n for n in names if n in folded], width))

    rank = {n: i for i, n in enumerate(FOLD_ORDER)}
    for n in sorted(calm, key=lambda n: rank.get(n, -1)):
        if total() <= height:
            break
        folded.append(n)
    for n in reversed(names):       # fortfarande för högt: oroliga paneler bara med larmen
        if total() <= height:
            break
        if n not in folded:
            full[n] = _panel(view, n, width, alarms_only=True)
    rows: list[Text] = []
    for n in names:
        if n not in folded:
            rows.extend(full[n])
    rows.extend(_calm_rows([n for n in names if n in folded], width))
    if len(rows) > height:
        rows = rows[:max(0, height - 1)] + [Text(" …", style="dim")]
    out = []
    for r in rows:
        r = r.copy()
        r.truncate(width, overflow="ellipsis", pad=True)
        out.append(r)
    return out


def render_systems(view: SystemsView, width: int) -> list[Text]:
    rows = render_hull(view.compartments(), view.first(Flooding), width, view.first(TrimTanks))
    if rows:
        rows.append(Text(""))
    rows.extend(render_panels(view, width))
    return rows


WORST_TEXT = {OK: ("allt normalt", STATE_STYLE[OK]), INFO: ("allt normalt", STATE_STYLE[OK]),
              OFF: ("system avställda", STATE_STYLE[OFF]), WARN: ("VARNING", "bold yellow"),
              DANGER: ("FARA", "bold white on #8a1010")}
