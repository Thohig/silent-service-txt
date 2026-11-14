"""Orderregister: varje station registrerar sina egna order.

En order tolkas i två steg:
1. Registret hittar den CommandSpec vars mönster matchar texten och bygger
   ett Order-objekt (ren syntax, ingen kunskap om ubåtens tillstånd).
2. Ordern publiceras på händelsebussen och den station som äger den
   hanterar den, inklusive att säga ifrån om ordern inte går att utföra.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

TIME_SCALES = (1, 2, 5, 10)

NUM = r"(\d+(?:[.,]\d+)?)"
DESIG = r"(s\s*-?\s*\d+)"


@dataclass(frozen=True)
class Order:
    """Basklass för alla order."""


@dataclass(frozen=True)
class Unknown(Order):
    text: str
    reason: str = ""


@dataclass(frozen=True)
class Help(Order):
    pass


@dataclass(frozen=True)
class SetTimeScale(Order):
    scale: int


def num(s: str) -> float:
    return float(s.replace(",", "."))


def desig(s: str | None) -> str | None:
    if not s:
        return None
    return f"S-{int(re.sub(r'[^0-9]', '', s))}"


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


@dataclass(frozen=True)
class CommandSpec:
    pattern: str
    build: Callable[[re.Match], Order]
    help: str = ""
    regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "regex", re.compile(self.pattern))


class CommandRegistry:
    def __init__(self, specs: Iterable[CommandSpec] = ()):
        self._specs: list[CommandSpec] = []
        self.register(*specs)

    def register(self, *specs: CommandSpec) -> None:
        self._specs.extend(specs)

    def parse(self, text: str) -> Order:
        t = normalize(text)
        if not t:
            return Unknown(text, "tom order")
        for spec in self._specs:
            if m := spec.regex.fullmatch(t):
                order = spec.build(m)
                if isinstance(order, Unknown) and not order.text:
                    order = Unknown(text, order.reason)
                return order
        return Unknown(text)

    def help_text(self) -> str:
        return "Order: " + " · ".join(s.help for s in self._specs if s.help)


def _time_scale(m: re.Match) -> Order:
    n = int(m[1])
    if n not in TIME_SCALES:
        return Unknown("", "tid kan vara 1, 2, 5 eller 10")
    return SetTimeScale(n)


TIME_COMMAND = CommandSpec(r"(?:tid|tidskomprimering)\s+(\d+)\s*x?", _time_scale, "tid 1|2|5|10")
HELP_COMMAND = CommandSpec(r"hjälp|hjalp|\?|order", lambda m: Help(), "hjälp")
