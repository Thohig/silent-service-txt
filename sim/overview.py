"""Översikten: det kaptenen vet just nu, samlat på en skärm (ui/overview_render.py).

Översikten ritar sjökortet, vattenfallet, djupprofilen och systemtavlan som de redan finns
(`Game.chart()` …) och lägger till det som bara finns här: kontakttabellen och lägesraderna.
Varje station bidrar via `Station.overview_items()` ur sin kunskap och sina egna instrument,
aldrig ur världen; Game samlar dem i en `OverviewView`. Allt är besättningens bedömning:
plottets lösning framräknad till nu, med sin kvalitet. Gränssnittet räknar inget själv.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .reports import Quality
from .sonar_view import KINDS, designation_order


@dataclass(frozen=True)
class ContactRow:
    """En rad i kontakttabellen: sonarrummets klassning och plottets lösning."""
    designation: str
    kind: str                           # sonar_view.KINDS: threat, contact, civil, benign, friendly
    classification: str
    class_quality: Quality
    held: bool
    bearing: float                      # plottets senaste bäring
    bearing_age_s: int                  # så länge sedan den togs
    range_nm: float | None = None       # lösningen framräknad till nu (None: ingen lösning)
    course: float | None = None
    speed: float | None = None
    quality: Quality | None = None
    drift: float | None = None          # bäringsdriften, grader per minut, + medurs (bara hållna)


@dataclass(frozen=True)
class Line:
    """En rad i en lägespanel (UPPDRAG, PERISKOP …): etikett och text, tillstånd som systemtavlan."""
    panel: str
    label: str
    text: str
    state: str = "ok"


# Lägespanelernas ordning (okända sist).
PANELS = ("UPPDRAG", "PERISKOP")

OverviewItem = ContactRow | Line


@dataclass
class OverviewView:
    clock: str
    items: list[OverviewItem] = field(default_factory=list)

    @property
    def contacts(self) -> list[ContactRow]:
        """Hållna först, hot först inom dem, sedan beteckningen."""
        order = {k: i for i, k in enumerate(KINDS)}
        rows = [it for it in self.items if isinstance(it, ContactRow)]
        return sorted(rows, key=lambda r: (not r.held, order.get(r.kind, len(order)),
                                           designation_order(r.designation)))

    @property
    def lines(self) -> list[Line]:
        rank = {p: i for i, p in enumerate(PANELS)}
        rows = [it for it in self.items if isinstance(it, Line)]
        return sorted(rows, key=lambda ln: rank.get(ln.panel, len(rank)))
