"""Rapporter från besättningen och kön som levererar dem med fördröjning.

En rapport bär strukturerad data (type + data), inte färdig text:
    station.say("sonar.bearing", {"designation": "S-1", "bearing": 47.2, ...})

Flödet:
    Report -> ReportQueue.submit()
           -> rapportfilter (kan ändra data, fördröja eller stoppa:
              krok för trötthet, lojalitet, sabotage)
           -> kö -> vid t_due: phrases.render() formulerar texten
           -> ReportDelivered på händelsebussen.

Eftersom filtren arbetar på data kan en sabotör ändra en bäring och texten
blir ändå korrekt formulerad.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Protocol


class Quality(IntEnum):
    DALIG = 0
    OSAKER = 1
    GOD = 2
    SAKER = 3

    @property
    def label(self) -> str:
        return {0: "dålig", 1: "osäker", 2: "god", 3: "säker"}[self.value]


@dataclass
class Report:
    t_due: int
    speaker: str                       # visningsnamn, t.ex. "Sonar (Volkov)"
    type: str                          # meddelandetyp, t.ex. "sonar.bearing"
    data: dict[str, Any] = field(default_factory=dict)
    role: str = ""                     # besättningsroll som avsändare
    quality: Quality | None = None
    alarm: bool = False                # sätter tidskomprimering till 1x
    kind: str = "info"                 # ack, done, contact, solution, plot, suggest, info, system
    # fylls i av phrases.render() vid leverans:
    text: str = ""
    table: list[list[str]] | None = None
    table_header: list[str] | None = None


class ReportFilter(Protocol):
    """Krok: kan ändra, fördröja eller stoppa en rapport (returnera None)."""

    def __call__(self, report: Report) -> Report | None: ...


@dataclass
class ReportQueue:
    filters: list[ReportFilter | Callable[[Report], Report | None]] = field(default_factory=list)
    _heap: list[tuple[int, int, Report]] = field(default_factory=list)
    _seq: itertools.count = field(default_factory=itertools.count)

    def submit(self, report: Report) -> None:
        r: Report | None = report
        for f in self.filters:
            r = f(r)
            if r is None:
                return
        heapq.heappush(self._heap, (r.t_due, next(self._seq), r))

    def due(self, now: int) -> list[Report]:
        out: list[Report] = []
        while self._heap and self._heap[0][0] <= now:
            out.append(heapq.heappop(self._heap)[2])
        return out

    def __len__(self) -> int:
        return len(self._heap)

    def has_kind(self, kind: str) -> bool:
        """Finns en rapport av detta slag i kön (ännu inte levererad)?"""
        return any(r.kind == kind for _, _, r in self._heap)
