"""Tolkning av kaptenens skrivna order (svenska)."""
from __future__ import annotations

import re
from dataclasses import dataclass

TIME_SCALES = (1, 2, 5, 10)


@dataclass(frozen=True)
class SetCourse:
    course: int


@dataclass(frozen=True)
class SetSpeed:
    speed: float


@dataclass(frozen=True)
class SetDepth:
    depth: int


@dataclass(frozen=True)
class SetTimeScale:
    scale: int


@dataclass(frozen=True)
class QuerySolution:
    designation: str | None


@dataclass(frozen=True)
class ShowPlot:
    designation: str | None


@dataclass(frozen=True)
class Help:
    pass


@dataclass(frozen=True)
class Unknown:
    text: str
    reason: str = ""


Order = SetCourse | SetSpeed | SetDepth | SetTimeScale | QuerySolution | ShowPlot | Help | Unknown

_NUM = r"(\d+(?:[.,]\d+)?)"
_DESIG = r"(s\s*-?\s*\d+)"


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _desig(s: str | None) -> str | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    return f"S-{int(digits)}"


def parse(text: str, max_speed: float = 28, max_depth: float = 300) -> Order:
    t = " ".join(text.strip().lower().split())
    if not t:
        return Unknown(text, "tom order")

    if m := re.fullmatch(rf"(?:kurs|k|styr)\s+{_NUM}", t):
        c = _num(m[1])
        if not 0 <= c < 360:
            return Unknown(text, "kursen måste vara 000–359")
        return SetCourse(int(round(c)) % 360)

    if m := re.fullmatch(rf"(?:fart|f)\s+{_NUM}(?:\s*(?:knop|kn))?", t):
        v = _num(m[1])
        if v > max_speed:
            return Unknown(text, f"högsta fart är {max_speed:g} knop")
        return SetSpeed(v)
    if t in ("stopp", "stoppa", "stopp i maskin"):
        return SetSpeed(0)

    if m := re.fullmatch(rf"(?:djup|d)\s+{_NUM}(?:\s*(?:m|meter))?", t):
        d = _num(m[1])
        if d > max_depth:
            return Unknown(text, f"största djup är {max_depth:g} meter")
        return SetDepth(int(round(d)))

    if m := re.fullmatch(r"(?:tid|tidskomprimering)\s+(\d+)\s*x?", t):
        n = int(m[1])
        if n not in TIME_SCALES:
            return Unknown(text, "tid kan vara 1, 2, 5 eller 10")
        return SetTimeScale(n)

    if m := re.fullmatch(rf"(?:läge|lage|lösning|losning)(?:\s+{_DESIG})?", t):
        return QuerySolution(_desig(m[1]))

    if m := re.fullmatch(rf"(?:plot|plott|plotten)(?:\s+{_DESIG})?", t):
        return ShowPlot(_desig(m[1]))

    if t in ("hjälp", "hjalp", "?", "order"):
        return Help()

    return Unknown(text)


HELP_TEXT = (
    "Order: kurs 090 · fart 5 · stopp · djup 100 · tid 1|2|5|10 · "
    "läge S-1 · plot S-1 · hjälp"
)
