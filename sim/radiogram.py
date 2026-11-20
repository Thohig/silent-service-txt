"""Ett radiogram från huvudstaben: texten, flaggorna och en position den meddelar.

Scenarierna lägger dem i `Scenario.radio_messages` (ett per sambandstillfälle); krigsskådeplatsen
(`theatre.py`) skriver dem under spelet. Radion levererar dem (`stations/radio/reception.py`).

Flaggorna radion förstår: `nuclear`/`war` (kärnvapenordern), `report_requested` (staben väntar en
rapport), `tasks` (ordern byts: det besättningen ska göra nu, `Knowledge.order_tasks`). Alla flaggor
skrivs också i `World.mission` (sanningens mål läser dem, t.ex. `recalled`).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RadioMessage:
    text: str
    flags: dict = field(default_factory=dict)
    # (namn, x, y, sigma nm, simtid) – en position huvudstaben meddelar
    waypoint: tuple[str, float, float, float, int] | None = None
    # (kurs, fart i knop) för en position som rör sig (en konvoj), annars None
    motion: tuple[float, float] | None = None
