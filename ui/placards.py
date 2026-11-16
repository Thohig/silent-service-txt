"""Skyltar på ryska, med den svenska betydelsen bredvid eller före.

Vyernas rubriker och systemtavlans paneler får båtens egna beteckningar: stridsavdelningarna
(БЧ, боевая часть) och tjänsterna som de hette ombord på en sovjetisk ubåt.
"""
from __future__ import annotations

from rich.text import Text

RU_STYLE = "#b8a878"            # mässingsskylt: ockra mot den gröna panelen
PLATE_STYLE = "bold #1a160c on #a08850"

# vyns svenska rubrik ⇒ rysk skylt
VIEW_RU = {
    "LOGGBOKEN": "ВАХТЕННЫЙ ЖУРНАЛ",
    "NAVIGATÖRENS SJÖKORT": "ШТУРМАНСКАЯ КАРТА",
    "UBÅTEN": "ПОДВОДНАЯ ЛОДКА",
    "DJUPMÄTARE": "ГЛУБИНОМЕР",
    "BRYGGAN": "МОСТИК",
    "KAPTENENS HYTT": "КАЮТА КОМАНДИРА",
}

# systemtavlans paneler ⇒ stridsavdelning eller tjänst
PANEL_RU = {
    "MASKIN": "БЧ-5 · ЭНЕРГЕТИКА",
    "SKADOR": "БЧ-5 · ЖИВУЧЕСТЬ",
    "NAVIGATION": "БЧ-1 · ШТУРМАНСКАЯ",
    "VAPEN": "БЧ-3 · ТОРПЕДЫ",
    "SONAR": "РТС · ГИДРОАКУСТИКА",
    "SAMBAND": "БЧ-4 · СВЯЗЬ",
}

CENTRAL_RU = "ЦЕНТРАЛЬНЫЙ ПОСТ"


def view_title(sv: str, trailing: str = "") -> Text:
    """" LOGGBOKEN · ВАХТЕННЫЙ ЖУРНАЛ" med den ryska delen som skylt."""
    t = Text(f" {sv}", style="bold")
    if sv in VIEW_RU:
        t.append(" · ", style="dim")
        t.append(VIEW_RU[sv], style=RU_STYLE)
    t.append(trailing, style="bold")
    return t


def central_plate() -> str:
    """Mässingsskylten över centralen."""
    return f" {CENTRAL_RU} · centralen "
