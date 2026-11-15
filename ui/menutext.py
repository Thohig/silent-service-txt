"""Huvudmenyns texter: sidhuvudet som en hemlig handling och stämplarna på uppdragen.

Ryskan står alltid med den svenska betydelsen bredvid. Inget här läser spelet; det är
bara stämning kring kalendern i oktober 1962.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rich.text import Text

# --- färger: en stämplad mapp, ockra papper och flaggrött ---------------------------
BG = "#120b09"
INK = "#d8c8a0"            # ockra text
DIM = "#8a7a5c"
RED = "#b8281c"
RED_DARK = "#5a1410"
HIGHLIGHT_BG = "#4a1a12"
HIGHLIGHT_FG = "#f4e6c4"
RULE = "#6a2a20"

STAR = "★"


def header(width: int = 100) -> Text:
    """Två rader: sekretessen och flottan på ett rött fält, sedan båten."""
    left = " СОВЕРШЕННО СЕКРЕТНО · ЭКЗ. № 2"
    right = f"{STAR} ВМФ СССР · СЕВЕРНЫЙ ФЛОТ "
    gap = max(2, width - len(left) - len(right))
    t = Text()
    t.append(left + " " * gap + right, style=f"bold {INK} on {RED_DARK}")
    t.append("\n")
    sv_left = " Strängt hemligt, exemplar nr 2"
    note = "Sovjetunionens örlogsflotta, Norra flottan "
    t.append(sv_left + " " * max(2, width - len(sv_left) - len(note)) + note,
             style=f"{DIM} on {RED_DARK}")
    t.append("\n\n")
    t.append(" К-114", style=f"bold {HIGHLIGHT_FG}")
    t.append("   Projekt 627A · 4:e eskadern · Poljarnyj", style=DIM)
    return t


# --- stämplar ---------------------------------------------------------------------
@dataclass(frozen=True)
class Stamp:
    ru: str
    sv: str
    style: str


STAMP_TRAINING = Stamp("ДЛЯ СЛУЖЕБНОГО ПОЛЬЗОВАНИЯ", "för tjänstebruk", f"{DIM}")
STAMP_SECRET = Stamp("СЕКРЕТНО", "hemligt", f"bold {RED}")
STAMP_TOP_SECRET = Stamp("СОВЕРШЕННО СЕКРЕТНО", "strängt hemligt", f"bold #e03a26")
STAMP_SPECIAL = Stamp("СОВ. СЕКРЕТНО · ОСОБОЙ ВАЖНОСТИ", "strängt hemligt, av särskild vikt",
                      f"bold {HIGHLIGHT_FG} on {RED}")


def mission_day(title: str) -> int | None:
    """Dagen i oktober ur titeln ("Jagade, natten till 27 oktober 1962" ⇒ 27)."""
    m = re.search(r"(\d+) oktober", title)
    return int(m.group(1)) if m else None


def stamp_for(key: str, title: str) -> Stamp:
    """Ju närmare den 28 oktober, desto hemligare. Övningen är bara för tjänstebruk."""
    if key.split("-")[0] == "ovning":
        return STAMP_TRAINING
    day = mission_day(title)
    if day is None or day < 22:
        return STAMP_SECRET
    if day < 27:
        return STAMP_TOP_SECRET
    return STAMP_SPECIAL


def stamp_text(stamp: Stamp) -> Text:
    t = Text()
    t.append(f" {stamp.ru} ", style=stamp.style)
    t.append(f"\n{stamp.sv}", style=f"italic {DIM}")
    return t
