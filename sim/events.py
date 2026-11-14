"""Händelsebuss mellan simulering, besättning och gränssnitt.

Prenumeranter registrerar sig på en händelsetyp (eller basklassen Event för
allt). Gränssnittet, framtida talsyntes (macOS "say") och berättelselagret
kopplar in sig här utan att simuleringen känner till dem.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from .reports import Report


@dataclass(frozen=True)
class Event:
    t: int


@dataclass(frozen=True)
class Tick(Event):
    pass


@dataclass(frozen=True)
class ReportDelivered(Event):
    report: Report


@dataclass(frozen=True)
class TimeScaleChanged(Event):
    scale: int
    reason: str = ""


@dataclass(frozen=True)
class OrderIssued(Event):
    text: str
    order: Any


@dataclass(frozen=True)
class ContactDetected(Event):
    designation: str


@dataclass(frozen=True)
class ContactLost(Event):
    designation: str


E = TypeVar("E", bound=Event)
Handler = Callable[[Any], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        for cls in type(event).__mro__:
            for h in list(self._handlers.get(cls, ())):
                h(event)
