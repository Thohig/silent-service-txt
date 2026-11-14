"""Rapporter från besättningen och kön som levererar dem med fördröjning.

Rapportflödet är: besättningsmedlem skapar Report -> ReportQueue.submit()
-> rapportfilter (krok för trötthet, lojalitet, sabotage m.m.) -> kö ->
levereras när simtiden når t_due.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Protocol


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
    text: str
    role: str = ""                     # besättningsroll som avsändare
    quality: Quality | None = None
    alarm: bool = False                # sätter tidskomprimering till 1x
    table: list[list[str]] | None = None
    table_header: list[str] | None = None
    kind: str = "info"                 # ack, done, contact, solution, plot, suggest, info


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
