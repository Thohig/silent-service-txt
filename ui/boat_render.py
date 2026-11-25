"""Vyn Ubåten: genomskärningen överst, djupprofilen till vänster och panelerna till höger.

Slår ihop djupprofilen och systemtavlan. Smalt fönster: profilen över panelerna. Lågt
fönster: ingen genomskärning, avdelningarna blir lampor i rubriken. Ren funktion av
`ProfileView` och `SystemsView`, testbar utan Textual.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from rich.text import Text

from sim.fmt import fmt_course, kn, kn_dir
from sim.profile import ProfileView
from sim.systems import OK, Compartment, Flooding, SystemsView, TrimTanks

from . import profile_render
from .placards import view_title
from .systems_render import (CELL_BG, ROMAN, STATE_MARK, STATE_STYLE, WATER, WORST_TEXT,
                             render_compact_panels, render_hull)

TITLE = "UBÅTEN"
SIDE_MIN_W = 110            # smalare: profilen över panelerna
HULL_MIN_H = 22             # lägre: avdelningarna som lampor i rubriken
PROFILE_SHARE = 0.6
PROFILE_SHARE_TWO = 0.45    # panelerna i två spalter: profilen får mindre
PANEL_COL_MIN_W = 48        # en panelspalt smalare än så klipper raderna
GAP = 2
PROFILE_MIN_H = 8


@dataclass(frozen=True)
class Layout:
    hull: bool
    side: bool
    profile_w: int
    profile_h: int
    panels_w: int
    panels_h: int
    sec_per_col: int = 0        # profilens tidsskala (sätts av render_boat)
    panel_cols: int = 1         # panelerna i två spalter när de inte ryms och det är brett


def layout(width: int, height: int, hull_rows: int, panel_rows: int) -> Layout:
    """Var delarna hamnar. `hull_rows`: genomskärningens höjd; `panel_rows`: panelernas
    höjd fullt utfällda (det smala läget ger dem högst det, och högst halva höjden)."""
    hull = hull_rows > 0 and height >= HULL_MIN_H
    rest = height - (hull_rows + 1 if hull else 0)
    if width >= SIDE_MIN_W:
        pw2 = round(width * PROFILE_SHARE_TWO)
        if panel_rows > rest and (width - pw2 - 2 * GAP) // 2 >= PANEL_COL_MIN_W:
            return Layout(hull, True, pw2, rest, width - pw2 - GAP, rest, panel_cols=2)
        pw = round(width * PROFILE_SHARE)
        return Layout(hull, True, pw, rest, width - pw - GAP, rest)
    ph = max(3, min(panel_rows, rest // 2, rest - PROFILE_MIN_H - 1))
    return Layout(hull, False, width, max(PROFILE_MIN_H, rest - ph - 1), width, ph)


def _two_columns(sv: SystemsView, width: int, height: int) -> list[Text]:
    """Panelerna i två spalter, delade vid en panelrubrik så att ingen panel delas."""
    cw = (width - GAP) // 2
    rows = render_compact_panels(sv, cw, 2 * height)
    heads = [i for i, r in enumerate(rows) if r.plain.startswith("─") and 0 < i <= height]
    fits = [i for i in heads if len(rows) - i <= height]
    if fits:                        # båda spalterna ryms: dela närmast mitten
        split = min(fits, key=lambda i: abs(i - len(rows) / 2))
    else:                           # högra spalten klipps: vänstra så full som möjligt
        split = max(heads, default=min(height, len(rows)))
    left, right = rows[:split], rows[split:]
    if len(right) > height:
        right = right[:height - 1] + [Text(" …", style="dim")]
    out = []
    for i in range(max(len(left), len(right))):
        t = Text(no_wrap=True, overflow="crop")
        t.append(left[i] if i < len(left) else Text(" " * cw))
        t.append(" " * GAP)
        if i < len(right):
            t.append(right[i])
        out.append(t)
    return out


def render_boat(pv: ProfileView, sv: SystemsView, width: int, height: int,
                sec_per_col: int | None = None,
                max_depth: float | None = None) -> tuple[list[Text], Layout]:
    """sec_per_col None: tidsskalan väljs så att historiken fyller profilen
    (`profile_render.auto_time_zoom`); den valda står i `Layout.sec_per_col`."""
    hull = render_hull(sv.compartments(), sv.first(Flooding), width, sv.first(TrimTanks))
    full_panels = len(render_compact_panels(sv, width, 10_000))
    lay = layout(width, height, len(hull), full_panels)
    rows: list[Text] = []
    if lay.hull:
        rows.extend(hull)
        rows.append(Text(""))
    if sec_per_col is None:
        sec_per_col = profile_render.TIME_ZOOM[profile_render.auto_time_zoom(pv, lay.profile_w)]
    lay = dataclasses.replace(lay, sec_per_col=sec_per_col)
    profile = profile_render.render_profile(pv, lay.profile_w, lay.profile_h, sec_per_col,
                                            max_depth)
    if lay.panel_cols == 2:
        panels = _two_columns(sv, lay.panels_w, lay.panels_h)
    else:
        panels = render_compact_panels(sv, lay.panels_w, lay.panels_h)
    if lay.side:
        for i in range(max(len(profile), len(panels))):
            left = profile[i].copy() if i < len(profile) else Text("")
            left.truncate(lay.profile_w, pad=True)
            t = Text(no_wrap=True, overflow="crop")
            t.append(left)
            t.append(" " * GAP)
            if i < len(panels):
                t.append(panels[i])
            rows.append(t)
    else:
        rows.extend(profile)
        rows.append(Text(""))
        rows.extend(panels)
    return rows[:height], lay


def _lamps(comps: list[Compartment]) -> Text:
    """Avdelningarna som lampor: romersk siffra i tillståndets färg."""
    t = Text()
    for c in comps:
        style = f"{STATE_STYLE[c.state]} {CELL_BG.get(c.state, '')}".strip()
        t.append(" ")
        t.append(ROMAN[c.no - 1] if c.no <= len(ROMAN) else str(c.no), style=style)
    return t


def header(pv: ProfileView, sv: SystemsView) -> Text:
    t = view_title(TITLE, " ")
    t.append(f" djup {pv.depth:.0f} m", style="bold")
    if abs(pv.ordered_depth - pv.depth) >= 1:
        t.append(f" ▸{pv.ordered_depth:.0f} m", style="yellow")
    t.append(f" · fart {kn_dir(pv.speed, pv.astern)} kn · kurs {fmt_course(pv.course)}")
    for n in pv.notes:
        t.append(f" · {n.text}")
    t.append(" · ")
    word, style = WORST_TEXT[sv.worst()]
    t.append(f" {word} ", style=style)
    return t


def lamps(sv: SystemsView, lay: Layout | None) -> Text:
    """Avdelningarna som lampor när genomskärningen inte får plats (annars tomt)."""
    t = Text()
    if lay is None or lay.hull or not sv.compartments():
        return t
    t.append(" avd", style="dim")
    t.append(_lamps(sv.compartments()))
    if (fl := sv.first(Flooding)) is not None and fl.tons > 0.5:
        t.append(f"  ≈ {fl.tons:.0f} ton", style=WATER)
    t.append(" ·")
    return t


def legend(width: int | None = None) -> Text:
    """Profilens teckenförklaring och tavlans tillstånd på andra raden, brutna efter bredden."""
    items = profile_render.legend_items()
    for state, what in ((OK, "normalt"), ("varning", "varning"), ("fara", "fara")):
        t = Text(STATE_MARK[state], style=STATE_STYLE[state])
        t.append(f" {what}", style="dim")
        items.append(t)
    return profile_render.pack_legend(items, width)

