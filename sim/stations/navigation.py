"""Navigation: kurs, fart och djup. Kvitterar order och rapporterar när de är verkställda."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..crew import Role
from ..orders import NUM, CommandSpec, Order, Unknown, num
from .base import Station


@dataclass(frozen=True)
class SetCourse(Order):
    course: int


@dataclass(frozen=True)
class SetSpeed(Order):
    speed: float


@dataclass(frozen=True)
class SetDepth(Order):
    depth: int


def _course(m: re.Match) -> Order:
    c = num(m[1])
    if not 0 <= c < 360:
        return Unknown("", "kursen måste vara 000–359")
    return SetCourse(int(round(c)) % 360)


class NavigationStation(Station):
    role = Role.NAVIGATOR
    COMMANDS = [
        CommandSpec(rf"(?:kurs|k|styr)\s+{NUM}", _course, "kurs 090"),
        CommandSpec(rf"(?:fart|f)\s+{NUM}(?:\s*(?:knop|kn))?", lambda m: SetSpeed(num(m[1])), "fart 5"),
        CommandSpec(r"stopp|stoppa|stopp i maskin", lambda m: SetSpeed(0.0), "stopp"),
        CommandSpec(rf"(?:djup|d)\s+{NUM}(?:\s*(?:m|meter))?",
                    lambda m: SetDepth(int(round(num(m[1])))), "djup 100"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self._pending: set[str] = set()

    @property
    def ship(self):
        return self.game.world.own.state

    def position_estimate(self) -> tuple[float, float]:
        """Navigatörens bestick. Version 1: perfekt navigering."""
        return self.ship.x, self.ship.y

    def on_order(self, order: Order) -> None:
        s = self.ship
        match order:
            case SetCourse(course=c):
                s.order_course(c)
                self._ack("course", {"course": c}, s.course == s.ordered_course)
            case SetSpeed(speed=v):
                if v > s.max_speed:
                    self.say("nav.limit", {"what": "speed", "limit": s.max_speed})
                    return
                s.order_speed(v)
                self._ack("speed", {"speed": v}, s.speed == s.ordered_speed)
            case SetDepth(depth=d):
                if d > s.max_depth:
                    self.say("nav.limit", {"what": "depth", "limit": s.max_depth})
                    return
                s.order_depth(d)
                self._ack("depth", {"depth": d}, s.depth == s.ordered_depth)

    def _ack(self, what: str, data: dict, already: bool) -> None:
        self.say(f"nav.{what}.ack", {**data, "already": already}, kind="ack")
        if already:
            self._pending.discard(what)
        else:
            self._pending.add(what)

    def update(self) -> None:
        s = self.ship
        changing = s.changing()
        for what in list(self._pending):
            if what not in changing:
                self._pending.discard(what)
                value = {"course": s.course, "speed": s.speed, "depth": s.depth}[what]
                self.say(f"nav.{what}.done", {what: value}, kind="done")
