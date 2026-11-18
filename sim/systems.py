"""Systemtavlan: ubåtens system och deras tillstånd, så som besättningen ser dem.

Motsvarigheten till sjökortet för ubåtens inre. Varje station bidrar med
egna element via `Station.system_items()`; Game samlar dem i en
`SystemsView` och gränssnittet ritar (ui/systems_render.py). Stationerna
läser egna instrument (ownship.sys), aldrig fienden eller världen utanför.
Nytt system ombord ritar sig självt genom att ge egna element.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Tillstånd, i stigande allvar. Gränssnittet färgar efter dem.
OK, INFO, OFF, WARN, DANGER = "ok", "info", "av", "varning", "fara"
SEVERITY = {OK: 0, INFO: 0, OFF: 1, WARN: 2, DANGER: 3}

# Panelernas ordning på tavlan.
PANELS = ("MASKIN", "TRIM", "SKADOR", "NAVIGATION", "VAPEN", "SONAR", "SAMBAND")


@dataclass(frozen=True)
class Gauge:
    """En rad på en panel: etikett, text och ev. stapel (0–1)."""
    panel: str
    label: str
    text: str
    state: str = OK
    level: float | None = None


@dataclass(frozen=True)
class Compartment:
    """En avdelning i genomskärningen. Romerska siffror från fören."""
    no: int
    name: str
    state: str = OK
    note: str = ""


@dataclass(frozen=True)
class TubeRack:
    """Torpedtuberna: (nummer, laddad typ, typ som laddas, sekunder kvar)."""
    tubes: tuple[tuple[int, str | None, str | None, int], ...]


@dataclass(frozen=True)
class Flooding:
    """Vatten i kölsvinet (ton) mot vad ubåten tål."""
    tons: float
    limit: float
    leaking: bool


@dataclass
class SystemsView:
    clock: str
    items: list = field(default_factory=list)

    def gauges(self, panel: str) -> list[Gauge]:
        return [g for g in self.items if isinstance(g, Gauge) and g.panel == panel]

    def panels(self) -> list[str]:
        """Paneler med innehåll: de kända i fast ordning, sedan nya i den ordning de kom."""
        seen = [g.panel for g in self.items if isinstance(g, Gauge)]
        known = [p for p in PANELS if p in seen]
        extra = list(dict.fromkeys(p for p in seen if p not in PANELS))
        return known + extra

    def compartments(self) -> list[Compartment]:
        return sorted((c for c in self.items if isinstance(c, Compartment)), key=lambda c: c.no)

    def first(self, cls):
        return next((i for i in self.items if isinstance(i, cls)), None)

    def worst(self) -> str:
        states = [i.state for i in self.items if isinstance(i, (Gauge, Compartment))]
        return max(states, key=SEVERITY.get, default=OK)


def health_word(h: float) -> str:
    return ("hel" if h >= 1.0 else "lätt skadad" if h >= 0.75 else "skadad" if h >= 0.4
            else "svårt skadad" if h > 0.0 else "ur funktion")


def health_state(h: float) -> str:
    return OK if h >= 1.0 else WARN if h >= 0.4 else DANGER
