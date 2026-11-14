"""Basklass för besättningsstationer.

En station är ett system ombord med en ansvarig besättningsmedlem. Den
- registrerar sina order (COMMANDS),
- tar emot order via händelsebussen (on_order),
- uppdateras en gång per simsekund (update),
- rapporterar via say() med strukturerad data, aldrig färdig text,
- föreslår åtgärder via suggest(): en rapport med en färdig order som
  kaptenen kan godkänna med "ja",
- kan lämna förslag när kaptenen varit tyst länge (idle_proposals);
  vakthavande officer väljer det viktigaste.

Nya system (torpedrum, reaktor, radio, periskop …) läggs till som nya
stationer utan att Game behöver ändras.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from ..crew import CrewMember, Role
from ..events import EventBus, OrderIssued
from ..orders import CommandSpec, Order
from ..reports import Quality

if TYPE_CHECKING:
    from ..game import Game

# Obesvarade förslag glesas ut: får kaptenen samma förslag (nyckel) igen utan
# att ha sagt något sedan förra gången, fördubblas väntetiden för varje gång.
BACKOFF_BASE_S = 420
BACKOFF_MAX_S = 3600


@dataclass(frozen=True)
class Proposal:
    """Ett förslag en station kan ge när kaptenen varit tyst en längre stund.

    priority: 1 är viktigast (säkerhet), högre tal är rutin. Avfyring får
    aldrig vara ett Proposal.
    """
    priority: int
    key: str
    type: str                      # frastyp
    order: str
    data: dict[str, Any] = field(default_factory=dict)
    quality: Quality | None = None
    cooldown: int = 1800


class Station:
    role: ClassVar[Role]
    COMMANDS: ClassVar[list[CommandSpec]] = []

    def __init__(self, game: Game):
        self.game = game
        self._suggested: dict[str, int] = {}
        self._unanswered: dict[str, int] = {}

    # --- koppling -----------------------------------------------------------
    def attach(self, bus: EventBus) -> None:
        bus.subscribe(OrderIssued, lambda e: self.on_order(e.order))

    # --- livscykel ----------------------------------------------------------
    def on_order(self, order: Order) -> None:
        """Hantera order som tillhör stationen. Ignorera andra."""

    def update(self) -> None:
        """Anropas en gång per simsekund, efter att världen tickat."""

    def idle_proposals(self) -> list[Proposal]:
        """Förslag att ge om kaptenen varit tyst länge. Bara ur kunskap och eget läge."""
        return []

    def chart_items(self) -> list:
        """Sjökortselement (sim.chart) ur stationens kunskap. Aldrig ur World."""
        return []

    def profile_items(self) -> list:
        """Djupprofilens element (sim.profile) ur stationens kunskap. Aldrig ur World."""
        return []

    def propose(self, p: Proposal) -> bool:
        return self.suggest(p.key, p.type, p.data, order=p.order, cooldown=p.cooldown,
                            quality=p.quality)

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

        Har kaptenen inte sagt något sedan förslaget senast gavs glesas det ut:
        väntetiden fördubblas för varje obesvarad upprepning (larm undantagna).
        """
        if order and self.game.suggestion_redundant(order, self.now):
            return False
        last = self._suggested.get(key)
        n = 0
        if last is not None and not alarm and self.game.last_command_t <= last:
            n = self._unanswered.get(key, 0) + 1
        wait = cooldown if n == 0 else \
            min(max(cooldown, BACKOFF_BASE_S) * 2 ** n, BACKOFF_MAX_S)
        if last is not None and self.now - last < wait:
            return False
        self._suggested[key] = self.now
        self._unanswered[key] = n
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
