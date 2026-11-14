"""Spelmotorn: en tunn samordnare.

Game äger världen (sanning), kunskapslagret, händelsebussen, rapportkön
och stationerna. All ombordlogik bor i stationerna (sim/stations/).

Gränssnittet anropar bara:
    game.command(text)   – kaptenens order
    game.tick()          – en sekund simtid
    game.status()        – ögonblicksbild för statusraden
och prenumererar på händelser via game.bus.

Ett tick:
    1. världen rör sig ett steg (sanning)
    2. varje station uppdateras, i ordning
    3. förfallna rapporter formuleras och levereras (larm -> 1x)
    4. Tick publiceras
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, TypeVar

from . import phrases
from .crew import CrewMember, Role
from .events import EventBus, OrderIssued, ReportDelivered, Tick, TimeScaleChanged
from .fmt import clock
from .knowledge import Knowledge
from .orders import HELP_COMMAND, TIME_COMMAND, CommandRegistry, Help, SetTimeScale, Unknown
from .reports import Quality, Report, ReportQueue
from .scenario import Scenario
from .stations import DEFAULT_STATIONS, NavigationStation, SonarRoom, Station
from .truthlog import TruthLog

S = TypeVar("S", bound=Station)


@dataclass(frozen=True)
class StatusSnapshot:
    clock: int                  # sekunder efter midnatt
    sim_time: int
    course: float
    ordered_course: float
    speed: float
    ordered_speed: float
    depth: float
    ordered_depth: float
    changing: frozenset[str]
    time_scale: int
    contacts_held: tuple[str, ...]


def build_registry(station_classes: list[type[Station]]) -> CommandRegistry:
    reg = CommandRegistry([TIME_COMMAND])
    for cls in station_classes:
        reg.register(*cls.COMMANDS)
    reg.register(HELP_COMMAND)
    return reg


class Game:
    def __init__(self, scenario: Scenario, seed: int | None = None,
                 truth_log: TruthLog | None = None,
                 stations: list[type[Station]] | None = None):
        self.rng = random.Random(seed)
        self.world = scenario.world
        self.crew: dict[Role, CrewMember] = scenario.crew
        self.start_clock = scenario.start_clock
        self.secret_order = scenario.secret_order
        self.truth_log = truth_log
        self.time_scale = 1

        self.bus = EventBus()
        self.queue = ReportQueue()
        self.knowledge = Knowledge()
        self.knowledge.attach(self.bus)          # före stationerna, se events.py

        station_classes = stations if stations is not None else DEFAULT_STATIONS
        self.stations: list[Station] = [cls(self) for cls in station_classes]
        for st in self.stations:
            st.attach(self.bus)
        self.registry = build_registry(station_classes)

    # ------------------------------------------------------------------ åtkomst
    @property
    def now(self) -> int:
        return self.world.time

    def station(self, cls: type[S]) -> S:
        for st in self.stations:
            if isinstance(st, cls):
                return st
        raise KeyError(cls.__name__)

    def own_position_estimate(self) -> tuple[float, float]:
        return self.station(NavigationStation).position_estimate()

    def clock_str(self, sim_t: int | None = None) -> str:
        return clock(self.start_clock + (self.now if sim_t is None else sim_t))

    # ------------------------------------------------------------------ rapporter
    def say(self, role: Role, type: str, data: dict[str, Any], *, kind: str = "info",
            quality: Quality | None = None, alarm: bool = False, extra_delay: int = 0) -> None:
        member = self.crew[role]
        self.queue.submit(Report(
            t_due=self.now + member.report_delay(self.rng) + extra_delay,
            speaker=member.callsign, type=type, data=data, role=role.value,
            quality=quality, alarm=alarm, kind=kind))

    def _deliver(self, r: Report) -> None:
        phrases.render(r, self.clock_str)
        self.bus.publish(ReportDelivered(self.now, r))

    def log(self, text: str) -> None:
        if self.truth_log:
            self.truth_log.note(self.now, text)

    def set_time_scale(self, scale: int, reason: str = "") -> None:
        if scale != self.time_scale:
            self.time_scale = scale
            self.bus.publish(TimeScaleChanged(self.now, scale, reason))

    # ------------------------------------------------------------------ order
    def command(self, text: str) -> None:
        order = self.registry.parse(text)
        self.log(f"ORDER {text!r} -> {order}")
        self.bus.publish(OrderIssued(self.now, text, order))
        match order:
            case SetTimeScale(scale=n):
                self.set_time_scale(n, "order")
            case Help():
                self._deliver(Report(self.now, "", "system.help",
                                     {"text": self.registry.help_text()}, kind="system"))
            case Unknown(reason=reason):
                self.say(Role.NAVIGATOR, "order.unknown", {"reason": reason})

    # ------------------------------------------------------------------ tick
    def tick(self) -> list[Report]:
        self.world.tick(1)
        if self.truth_log:
            self.truth_log.tick(self.world)

        for st in self.stations:
            st.update()

        delivered = self.queue.due(self.now)
        for r in delivered:
            self._deliver(r)
            if r.alarm and self.time_scale > 1:
                self.set_time_scale(1, "larm")
        self.bus.publish(Tick(self.now))
        return delivered

    # ------------------------------------------------------------------ status
    def status(self) -> StatusSnapshot:
        s = self.world.own.state
        try:
            held = tuple(self.station(SonarRoom).held_designations())
        except KeyError:
            held = ()
        return StatusSnapshot(
            clock=(self.start_clock + self.now) % 86400, sim_time=self.now,
            course=s.course, ordered_course=s.ordered_course,
            speed=s.speed, ordered_speed=s.ordered_speed,
            depth=s.depth, ordered_depth=s.ordered_depth,
            changing=frozenset(s.changing()), time_scale=self.time_scale,
            contacts_held=held,
        )
