"""Vyregistret: helskärmsvyerna, orden som öppnar dem och Tab-ordningen.

En vy är en `ViewDef`: skärmklassen, orden på orderraden, namnet i handboken och när den
står i Tab-ordningen (`tab`, ett villkor på `ViewContext`). Registrets ordning är Tab-ordningen.
Appen (`ui/app.py`) slår upp ord och Tab här och behöver inte ändras för en ny vy med vanligt
beteende (ordet växlar vyn av och på). Vyer med eget beteende på ordet (loggboken, telegrammen)
anger `word_action`, namnet på en metod i appen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from textual.screen import Screen

from .boat import BoatScreen
from .central import CentralScreen
from .bridge import BridgeScreen
from .cabin import CabinScreen
from .chart import ChartScreen
from .logview import LogScreen
from .overview import OverviewScreen
from .periscope import PeriscopeScreen
from .sonar import SonarScreen


@dataclass(frozen=True)
class ViewContext:
    """Det Tab-ordningen beror på."""
    big: bool = False               # stort fönster: översikten är huvudvyn med loggremsan, loggen en egen vy
    command: str = "captain"        # starpom har befälet: hytten först
    bridge: str = "shut"            # tornluckan: bryggan bara när den inte är stängd


@dataclass(frozen=True)
class ViewDef:
    screen: type[Screen]
    words: frozenset[str]
    name: str | None = None                                 # ordet i handboken (None: inte där)
    tab: Callable[[ViewContext], bool] | None = lambda c: True   # None: aldrig i Tab-ordningen
    word_action: str | None = None                          # appens metod för ordet (annars växla)


def _words(*w: str) -> frozenset[str]:
    return frozenset(w)


# Tab-ordningen: (hytten) → (översikt, i litet fönster) → central → (loggboken) → sjökort → sonar → ubåten → (bryggan) → periskopbilden.
# Med folk på väg upp eller på bryggan kommer bryggan före periskopbilden (kikaren).
REGISTRY: tuple[ViewDef, ...] = (
    ViewDef(CabinScreen, _words("hytt", "hytten", "kajuta", "kajutan"),
            tab=lambda c: c.command == "starpom"),
    # i stort fönster är översikten huvudvyn: ordet stänger den vy som är öppen
    ViewDef(OverviewScreen, _words("översikt", "översikten", "oversikt", "oversikten", "lägesbild",
                                   "lagesbild", "lägesbilden"), "översikt",
            tab=lambda c: not c.big, word_action="_overview_word"),
    ViewDef(CentralScreen, _words("central", "centralen", "centralposten"), "central"),
    ViewDef(LogScreen, _words("logg", "loggen", "loggbok", "loggboken"), "logg",
            tab=lambda c: c.big, word_action="_log_word"),
    ViewDef(ChartScreen, _words("sjökort", "sjokort", "kort", "karta"), "sjökort"),
    ViewDef(SonarScreen, _words("sonar", "sonarvy", "vattenfall", "vattenfallet", "hydrofon",
                                "lurarna"), "sonar"),
    ViewDef(BoatScreen, _words("ubåt", "ubåten", "båten", "profil", "djupprofil", "sidovy",
                               "system", "systemtavla", "systemtavlan", "tavla", "tavlan"), "ubåt"),
    ViewDef(BridgeScreen, _words("brygga", "bryggan", "bryggvy", "utsikt"), "brygga",
            tab=lambda c: c.bridge != "shut"),
    ViewDef(PeriscopeScreen, _words("periskopbild", "periskopvy", "bild"), "periskopbild"),
    ViewDef(LogScreen, _words("telegram", "telegrammen", "telegrammet", "radiogram", "radiogrammen"),
            "telegram", tab=None, word_action="_telegrams"),
)

# alla helskärmsvyer (skärmar som ligger ovanpå spelets huvudskärm)
SCREENS: tuple[type[Screen], ...] = tuple(dict.fromkeys(v.screen for v in REGISTRY))


def view_for(word: str) -> ViewDef | None:
    """Vyn som ordet öppnar."""
    return next((v for v in REGISTRY if word in v.words), None)


def tab_order(ctx: ViewContext) -> tuple[type[Screen], ...]:
    """Vyerna i Tab-ordningen i det här läget."""
    return tuple(v.screen for v in REGISTRY if v.tab is not None and v.tab(ctx))


def all_words() -> frozenset[str]:
    """Alla ord som öppnar eller stänger en vy."""
    return frozenset().union(*(v.words for v in REGISTRY))


def manual_words() -> list[str]:
    """Vyernas ord i handboken, i registrets ordning."""
    return [v.name for v in REGISTRY if v.name]
