"""Basklass för besättningsstationer.

En station är ett system ombord med en ansvarig besättningsmedlem. Den
- registrerar sina order (COMMANDS),
- tar emot order via händelsebussen (on_order),
- uppdateras en gång per simsekund (update),
- rapporterar via say() med strukturerad data, aldrig färdig text,
- föreslår åtgärder via suggest(): en rapport med en färdig order som
  kaptenen kan godkänna med "ja".

Nya system (torpedrum, reaktor, radio, periskop …) läggs till som nya
stationer utan att Game behöver ändras.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from ..crew import CrewMember, Role
from ..events import EventBus, OrderIssued
from ..orders import CommandSpec, Order
from ..reports import Quality

if TYPE_CHECKING:
    from ..game import Game


class Station:
    role: ClassVar[Role]
    COMMANDS: ClassVar[list[CommandSpec]] = []

    def __init__(self, game: Game):
        self.game = game
        self._suggested: dict[str, int] = {}

    # --- koppling -----------------------------------------------------------
    def attach(self, bus: EventBus) -> None:
        bus.subscribe(OrderIssued, lambda e: self.on_order(e.order))

    # --- livscykel ----------------------------------------------------------
    def on_order(self, order: Order) -> None:
        """Hantera order som tillhör stationen. Ignorera andra."""

    def update(self) -> None:
        """Anropas en gång per simsekund, efter att världen tickat."""

    # --- hjälp --------------------------------------------------------------
    @property
    def member(self) -> CrewMember:
        return self.game.crew[self.role]

    @property
    def now(self) -> int:
        return self.game.now

    def suggest(self, key: str, type: str, data: dict[str, Any] | None = None, *,
                order: str | None = None, cooldown: int = 600,
                quality: Quality | None = None, alarm: bool = False) -> bool:
        """Föreslå en åtgärd. order är texten som utförs om kaptenen svarar ja.

        Samma förslag (key) upprepas inte inom cooldown sekunder. Ett förslag
        om något kaptenen redan har beordrat ges inte alls (se
        Game.suggestion_redundant) och förbrukar då ingen cooldown.
        """
        if order and self.game.suggestion_redundant(order, self.now):
            return False
        if self.now - self._suggested.get(key, -10**9) < cooldown:
            return False
        self._suggested[key] = self.now
        d = dict(data or {})
        if order:
            d["order"] = order
            d["made_t"] = self.now
        self.say(type, d, kind="suggest", quality=quality, alarm=alarm)
        return True

    def say(self, type: str, data: dict[str, Any] | None = None, *, kind: str = "info",
            quality: Quality | None = None, alarm: bool = False, extra_delay: int = 0) -> None:
        self.game.say(self.role, type, data or {}, kind=kind, quality=quality,
                      alarm=alarm, extra_delay=extra_delay)
