"""Ritar systemtavlan: genomskärning av ubåten överst, panelerna under."""
from __future__ import annotations

from rich.text import Text

from sim.systems import (DANGER, INFO, OFF, OK, SEVERITY, WARN, Compartment, Flooding, Gauge,
                         SystemsView, TubeRack)

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
def render_hull(comps: list[Compartment], flooding: Flooding | None, width: int) -> list[Text]:
    if not comps:
        return []
    n = len(comps)
    cw = min(12, (width - 7 - (n - 1)) // n)
    if cw < 4:
        return []                           # för smalt för en genomskärning
    inner = n * cw + (n - 1)
    pad = " " * max(0, (width - inner - 6) // 2)

    def line(left: str, cells: list[tuple[str, str]], sep: str, right: str) -> Text:
        t = Text(pad + " ", style=HULL, no_wrap=True, overflow="crop")
        t.append(left, style=HULL)
        for i, (s, style) in enumerate(cells):
            if i:
                t.append(sep, style=HULL)
            t.append(s, style=style)
        t.append(right, style=HULL)
        return t

    # tornet över centralen (III)
    sail_at = next((i for i, c in enumerate(comps) if c.no == 3), n // 3)
    x0 = 3 + sail_at * (cw + 1)
    sail = Text(pad + " " * x0, no_wrap=True, overflow="crop")
    sail.append(_center("▁▄▆▆▄▁", cw), style=HULL)
    rows = [sail,
            line(" ╭", [("─" * cw, HULL)] * n, "┬", "╮")]
    style_of = lambda c: f"{STATE_STYLE[c.state]} {CELL_BG.get(c.state, '')}".strip()
    rows.append(line("╱ ", [(_center(ROMAN[c.no - 1] if c.no <= len(ROMAN) else str(c.no), cw),
                             style_of(c)) for c in comps], "│", "╲"))
    rows.append(line("│ ", [(_center(c.name, cw), style_of(c)) for c in comps], "│", " ═╪═"))
    rows.append(line("╲ ", [(_center(c.note, cw), style_of(c)) for c in comps], "│", "╱"))
    if flooding is not None and flooding.tons > 0.5:
        # vattnet ligger i kölsvinet längs hela skrovet; tätare ju mer det är
        frac = min(1.0, flooding.tons / flooding.limit)
        fill = "≈" if frac >= 0.2 else "~" if frac >= 0.05 else "·"
        label = f" {flooding.tons:.0f} ton vatten" + (", läcker " if flooding.leaking else " ")
        water = label.center(inner, fill) if len(label) < inner else fill * inner
        rows.append(line(" │", [(water, WATER)], "", "│"))
    rows.append(line(" ╰", [("─" * cw, HULL)] * n, "┴", "╯"))
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
FOLD_ORDER = ("SKADOR", "SAMBAND", "SONAR", "MASKIN", "NAVIGATION", "VAPEN")


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
    rows = render_hull(view.compartments(), view.first(Flooding), width)
    if rows:
        rows.append(Text(""))
    rows.extend(render_panels(view, width))
    return rows


WORST_TEXT = {OK: ("allt normalt", STATE_STYLE[OK]), INFO: ("allt normalt", STATE_STYLE[OK]),
              OFF: ("system avställda", STATE_STYLE[OFF]), WARN: ("VARNING", "bold yellow"),
              DANGER: ("FARA", "bold white on #8a1010")}
