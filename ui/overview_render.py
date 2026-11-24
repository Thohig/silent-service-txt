"""Översikten (обстановка) som text: allt kaptenen vet just nu på en skärm.

Vänster spalt: sjökortet kring vårt beräknade läge, vattenfallet och djupprofilen, ritade av
vyernas egna renderare i mindre storlek. Höger spalt: kontakttabellen och lägesraderna ur
`Game.overview()` (plottets lösningar med kvalitet, uppdraget, periskopet), bäringsrepeatern
(gyrot med plottets kontakter) och systemtavlans paneler, oroliga först. Under `TWO_COL_W`
kolumner bara höger spalt och sedan sjökortet. Ren funktion; räknar inget själv.
"""
from __future__ import annotations

from rich.text import Text

from sim.chart import ChartView
from sim.fmt import kn, nm
from sim.geo import fmt_course
from sim.overview import ContactRow, OverviewView
from sim.profile import ProfileView
from sim.reports import Quality
from sim.sonar_view import SonarView
from sim.systems import SystemsView

from . import instruments as ins
from .canvas import Canvas
from .central_render import PALETTES
from .chart_render import render_chart
from .placards import RU_STYLE, view_title
from .profile_render import TIME_ZOOM, auto_time_zoom, render_profile
from .sonar_render import render_sonar
from .styles import CONTACT_STYLE
from .systems_render import STATE_MARK, STATE_STYLE, render_compact_panels

TITLE = "ÖVERSIKT"
TWO_COL_W = 100                 # så bred: två spalter
LEFT_SHARE = 0.55               # vänstra spaltens andel
GAP = 2
RULE = "#2f4a36"
HEAD = "bold #c8d0b0"
CHART_ZOOM = (0.025, 0.05, 0.1, 0.2, 0.4)      # sjömil per kolumn (som sjökortets)
CHART_MIN_NM = 3.0              # kortet visar minst så här långt åt varje håll
SONAR_WINDOW_S = 600            # vattenfallet: tio minuter
REPEATER = (11, 22)             # bäringsrepeaterns storlek (rader, kolumner)
QUALITY_STYLE = {Quality.DALIG: "bold red", Quality.OSAKER: "yellow", Quality.GOD: "green",
                 Quality.SAKER: "bold bright_green"}

PANEL_RU = {"KONTAKTER": "ЦЕЛИ", "UPPDRAG": "ЗАДАЧА", "PERISKOP": "ПЕРИСКОП",
            "SJÖKORT": "КАРТА", "VATTENFALL": "ГАК", "DJUP": "ГЛУБИНА", "SYSTEM": "БЧ"}


def heading(name: str, w: int) -> Text:
    """Panelens rubrik: "─ KONTAKTER ЦЕЛИ ─────"."""
    t = Text(f"─ {name} ", style=HEAD, no_wrap=True, overflow="crop")
    ru = PANEL_RU.get(name)
    if ru and len(name) + len(ru) + 6 <= w:
        t.append(f"{ru} ", style=RU_STYLE)
    t.append("─" * max(0, w - len(t.plain)), style=RULE)
    return t


def _fit(t: Text, w: int) -> Text:
    """Exakt w tecken: kapad eller utfylld."""
    t = t.copy()
    t.no_wrap, t.overflow = True, "crop"
    if len(t.plain) > w:
        t.truncate(w)
    else:
        t.pad_right(w - len(t.plain))
    return t


def _short_class(c: str) -> str:
    """Klassningens första led: "jagare, ångturbiner …" ⇒ "jagare"."""
    return c.split(",")[0].strip()


def contact_line(r: ContactRow, w: int) -> Text:
    """En kontakt: beteckning, klassning, bäring, och plottets lösning med kvalitet."""
    style = CONTACT_STYLE.get(r.kind, CONTACT_STYLE["contact"])
    if not r.held:
        style = f"{style} dim"
    t = Text(no_wrap=True, overflow="crop")
    t.append(f"{r.designation:<5}", style=style)
    cw = max(6, min(14, w - 51))       # plats för lösningen, kvaliteten och "tappad"
    t.append(f"{_short_class(r.classification)[:cw]:<{cw}} ", style=style if r.held else "dim")
    t.append(fmt_course(r.bearing), style="bold" if r.held else "dim")
    if r.range_nm is not None:
        t.append(f"  {nm(r.range_nm):>5} nm  {fmt_course(r.course)} {kn(r.speed):>4} kn ")
    else:
        age = f"({r.bearing_age_s // 60} min)" if r.bearing_age_s >= 60 else ""
        t.append(f"  {age:<24}", style="dim")
    if r.quality is not None:
        t.append(r.quality.label, style=QUALITY_STYLE[r.quality])
    if not r.held:
        t.append(" tappad", style="dim")
    return _fit(t, w)


def contacts_panel(ov: OverviewView, w: int, max_rows: int) -> list[Text]:
    rows = [heading("KONTAKTER", w)]
    contacts = ov.contacts
    if not contacts:
        rows.append(_fit(Text(" inga kontakter", style="dim"), w))
        return rows
    room = max(1, max_rows - 1)
    shown = contacts if len(contacts) <= room else contacts[:room - 1]
    rows.extend(contact_line(r, w) for r in shown)
    if len(shown) < len(contacts):
        rows.append(_fit(Text(f" och {len(contacts) - len(shown)} till", style="dim"), w))
    return rows


def lines_panels(ov: OverviewView, w: int) -> list[Text]:
    """Lägesraderna (UPPDRAG, PERISKOP …) panel för panel, som systemtavlan."""
    rows: list[Text] = []
    panel = None
    for ln in ov.lines:
        if ln.panel != panel:
            panel = ln.panel
            rows.append(heading(panel, w))
        t = Text(no_wrap=True, overflow="crop")
        t.append(f"{STATE_MARK.get(ln.state, ' ')} ", style=STATE_STYLE.get(ln.state))
        t.append(f"{ln.label:<12}", style="dim")
        t.append(ln.text, style=STATE_STYLE.get(ln.state))
        rows.append(_fit(t, w))
    return rows


def repeater(ov: OverviewView, course: float, rows: int, cols: int) -> list[Text]:
    """Gyrot med bäringsrepeatern: plottets hållna kontakter (numret i slagets färg), hot överst."""
    p = PALETTES["normal"]
    c = Canvas(cols, rows, p["wall"])
    tags = [(r.designation.rsplit("-", 1)[-1], r.bearing,
             CONTACT_STYLE.get(r.kind, CONTACT_STYLE["contact"])) for r in ov.contacts if r.held]
    ins.draw_dial(c, 0, 0, rows, cols, ins.gyro(course, None, p, tags), p, None)
    return c.lines()


def chart_scale(ov: OverviewView, cols: int) -> float:
    """Minsta skala där kortet rymmer plottets lösningar på de hållna kontakterna (och minst
    `CHART_MIN_NM`)."""
    reach = max([CHART_MIN_NM] + [r.range_nm for r in ov.contacts if r.held and r.range_nm])
    for s in CHART_ZOOM:
        if s * cols / 2 >= reach * 1.15:
            return s
    return CHART_ZOOM[-1]


def _side_by_side(left: list[Text], right: list[Text], lw: int, rw: int, h: int) -> list[Text]:
    out = []
    for i in range(h):
        a = left[i] if i < len(left) else Text("")
        b = right[i] if i < len(right) else Text("")
        line = _fit(a, lw)
        line.append(" " * GAP)
        line.append_text(_fit(b, rw))
        out.append(line)
    return out


def _right_column(ov: OverviewView, sv: SystemsView, course: float, w: int, h: int) -> list[Text]:
    rows = contacts_panel(ov, w, max(3, min(len(ov.contacts) + 1, h // 3)))
    situation = lines_panels(ov, w)
    rep_rows, rep_cols = REPEATER
    if w >= rep_cols + 30 and h - len(rows) >= rep_rows + 6:
        side = situation + [Text("")] * max(0, rep_rows - len(situation))
        rows.extend(_side_by_side(repeater(ov, course, rep_rows, rep_cols), side,
                                  rep_cols, w - rep_cols - GAP, max(rep_rows, len(situation))))
    else:
        rows.extend(situation)
    room = h - len(rows)
    if room >= 3:
        rows.extend(render_compact_panels(sv, w, room))
    return [_fit(r, w) for r in rows[:h]]


def _left_column(ov: OverviewView, chart: ChartView, sonar: SonarView, profile: ProfileView,
                 w: int, h: int) -> list[Text]:
    ch = max(6, round(h * 0.48))
    sh = max(6, round(h * 0.30))
    ph = max(4, h - ch - sh - 3)
    rows = [heading("SJÖKORT", w)]
    rows += render_chart(chart, *chart.own, chart_scale(ov, w), w, ch)
    rows.append(heading("VATTENFALL", w))
    rows += render_sonar(sonar, w, sh, SONAR_WINDOW_S)
    rows.append(heading("DJUP", w))
    rows += render_profile(profile, w, ph, TIME_ZOOM[auto_time_zoom(profile, w)])
    return [_fit(r, w) for r in rows[:h]]


def render_overview(ov: OverviewView, chart: ChartView, sonar: SonarView, profile: ProfileView,
                    systems: SystemsView, width: int, height: int) -> list[Text]:
    """Översikten som `height` rader, `width` tecken breda."""
    course = profile.course
    if width < TWO_COL_W:
        right = _right_column(ov, systems, course, width, height)
        left = []
        room = height - len(right)
        if room >= 8:
            left = [heading("SJÖKORT", width)] + \
                render_chart(chart, *chart.own, chart_scale(ov, width), width, room - 1)
        rows = right[:max(0, height - len(left))] + left
        rows += [Text("")] * (height - len(rows))
        return [_fit(r, width) for r in rows]
    lw = int((width - GAP) * LEFT_SHARE)
    rw = width - GAP - lw
    return _side_by_side(_left_column(ov, chart, sonar, profile, lw, height),
                         _right_column(ov, systems, course, rw, height), lw, rw, height)


def header(ov: OverviewView) -> Text:
    t = view_title(TITLE, f"  {ov.clock[:5]}")
    held = sum(r.held for r in ov.contacts)
    t.append(f" · {held} kontakter hålls" if held != 1 else " · 1 kontakt hålls", style="dim")
    return t
