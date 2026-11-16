"""Vyn Ubåten: genomskärningen överst, djupprofilen till vänster och panelerna till höger.

Slår ihop djupprofilen och systemtavlan. Smalt fönster: profilen över panelerna. Lågt
fönster: ingen genomskärning, avdelningarna blir lampor i rubriken. Ren funktion av
`ProfileView` och `SystemsView`, testbar utan Textual.
"""
from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text

from sim.fmt import fmt_course, kn
from sim.profile import ProfileView
from sim.systems import OK, Compartment, Flooding, SystemsView

from . import profile_render
from .placards import view_title
from .systems_render import (CELL_BG, ROMAN, STATE_MARK, STATE_STYLE, WATER, WORST_TEXT,
                             render_compact_panels, render_hull)

TITLE = "UBÅTEN"
SIDE_MIN_W = 110            # smalare: profilen över panelerna
HULL_MIN_H = 22             # lägre: avdelningarna som lampor i rubriken
PROFILE_SHARE = 0.6
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


def layout(width: int, height: int, hull_rows: int, panel_rows: int) -> Layout:
    """Var delarna hamnar. `hull_rows`: genomskärningens höjd; `panel_rows`: panelernas
    höjd fullt utfällda (det smala läget ger dem högst det, och högst halva höjden)."""
    hull = hull_rows > 0 and height >= HULL_MIN_H
    rest = height - (hull_rows + 1 if hull else 0)
    if width >= SIDE_MIN_W:
        pw = round(width * PROFILE_SHARE)
        return Layout(hull, True, pw, rest, width - pw - GAP, rest)
    ph = max(3, min(panel_rows, rest // 2, rest - PROFILE_MIN_H - 1))
    return Layout(hull, False, width, max(PROFILE_MIN_H, rest - ph - 1), width, ph)


def render_boat(pv: ProfileView, sv: SystemsView, width: int, height: int,
                sec_per_col: int = profile_render.TIME_ZOOM[profile_render.DEFAULT_TIME_ZOOM],
                max_depth: float | None = None) -> tuple[list[Text], Layout]:
    hull = render_hull(sv.compartments(), sv.first(Flooding), width)
    full_panels = len(render_compact_panels(sv, width, 10_000))
    lay = layout(width, height, len(hull), full_panels)
    rows: list[Text] = []
    if lay.hull:
        rows.extend(hull)
        rows.append(Text(""))
    profile = profile_render.render_profile(pv, lay.profile_w, lay.profile_h, sec_per_col,
                                            max_depth)
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
    t.append(f" · fart {kn(pv.speed)} kn · kurs {fmt_course(pv.course)}")
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


def legend() -> Text:
    """Profilens teckenförklaring och tavlans tillstånd på andra raden."""
    t = profile_render.legend()
    t.append("  ")
    for state, what in ((OK, "normalt"), ("varning", "varning"), ("fara", "fara")):
        t.append(STATE_MARK[state], style=STATE_STYLE[state])
        t.append(f" {what}  ", style="dim")
    return t

