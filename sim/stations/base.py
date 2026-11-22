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

Vägen till sanningen (designprincip 3): en station når `World` bara genom
- `own`: egen ubåt, dvs. egna instrument och reglage (gyro, logg, djupmätare, system),
  och `masts_free` (masterna kommer upp eller tar i isen),
- `area_nm` och `patrol_end`: kvadratens storlek och tidsgränsen, som står i ordern,
- `world`: bara i stationer med `REACHES_WORLD = True`, dvs. sensorer (sonar, periskop,
  brygga, radar, ekolod, isekolod, undervattenstelefon) och det som verkar i världen
  (torpeder, skenmål, sändningar). De skriver varför vid flaggan.
`tests/test_import_boundaries.py` underkänner `game.world` utanför denna fil och
`self.world` i stationer utan flaggan.
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
    from ..ownship import OwnShip
    from ..world import World

# Obesvarade förslag glesas ut: får kaptenen samma förslag (nyckel) igen utan
# att ha sagt något sedan förra gången, fördubblas väntetiden för varje gång.
BACKOFF_BASE_S = 420
BACKOFF_MAX_S = 3600
CONFIRM_S = 60              # confirm_once: en upprepad order inom så här lång tid verkställs


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
    REACHES_WORLD: ClassVar[bool] = False     # sensor eller vapen: får använda self.world
    # order som kräver masterna uppe: föreslås inte när kaptenen beordrat djupare än periskopdjup
    # (t.ex. ett "sänd rapport" som väntat bakom ett larm om att dyka, Game.held)
    MAST_ORDERS: ClassVar[tuple[type[Order], ...]] = ()

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

    def intercept(self, order: Order) -> bool:
        """Kaptenens order innan den verkställs: sant om stationen tar hand om den (och
        säger varför), så att den inte går vidare. T.ex. medan kaptenen är på väg."""
        return False

    def confirm_once(self, key: str, type: str, data: dict | None = None) -> bool:
        """För intercept: en order som bryter mot uppdraget eller saknar skäl. Första gången säger
        stationen varför och ordern stoppas (sant); upprepad inom CONFIRM_S verkställs. Ett förslag
        kaptenen sagt ja till, och vakten före överlämnandet, frågas aldrig."""
        if self.game.accepting or self.game.warmup_running:
            return False
        asked = getattr(self, "_confirm_asked", None)
        if asked is None:
            asked = self._confirm_asked = {}
        t = asked.pop(key, None)
        if t is not None and self.now - t <= CONFIRM_S:
            return False
        asked[key] = self.now
        self.say(type, data or {}, alarm=True)
        return True

    def on_suggestion(self, report) -> bool:
        """Ett förslag har levererats. Sant om stationen beslutat i frågan (starpom
        med befälet); förslaget väntar då inte längre på kaptenen."""
        return False

    def keeps_time_scale(self, report) -> bool:
        """Ett larm har levererats under tidskomprimering: sant om stationen tar hand om det
        och tiden inte ska sänkas av sig själv (starpom med befälet, för det som bara tänder
        lampan)."""
        return False

    def status_fields(self) -> dict:
        """Fält till StatusSnapshot ur stationens eget läge och kunskap (aldrig ur World).
        Game känner inga enskilda stationer: det stationen visar i statusraden lämnas här."""
        return {}

    def order_in_force(self, order: Order) -> bool | None:
        """Gäller en bestående order (STANDING) fortfarande, så som stationen ser det? None: inte
        stationens order. Game frågar innan ett förslag om samma order släpps som redundant: en
        uppgift (vaken, botten, styrningen) kan ha ändrat läget utan att kaptenen sagt något."""
        return None

    def vetoes(self, order: str) -> bool:
        """Får inte ett förslag med denna order ges (t.ex. dykning där ordern förbjuder det)?
        Grunden: en mastorder (MAST_ORDERS) när det beordrade djupet är under periskopdjup."""
        from ..ownship import PERISCOPE_DEPTH
        return bool(self.MAST_ORDERS) and self.own.state.ordered_depth > PERISCOPE_DEPTH and \
            isinstance(self.game.registry.parse(order), self.MAST_ORDERS)

    def dive_depth(self, want: int) -> int | None:
        """Djupet att föreslå när vi ska ned: want, men aldrig djupare än navigatören går med på här
        (kortet framåt, en färsk lodning). None om det inte går att komma under periskopdjup."""
        from ..ownship import PERISCOPE_DEPTH
        from .navigation import NavigationStation
        try:
            limit = self.game.station(NavigationStation).depth_limit()
        except KeyError:
            limit = None
        depth = int(want if limit is None else min(want, limit))
        return depth if depth > PERISCOPE_DEPTH else None

    def chart_items(self) -> list:
        """Sjökortselement (sim.chart) ur stationens kunskap. Aldrig ur World."""
        return []

    def profile_items(self) -> list:
        """Djupprofilens element (sim.profile) ur stationens kunskap. Aldrig ur World."""
        return []

    def sonar_items(self) -> list:
        """Sonarvyns element (sim.sonar_view) ur stationens kunskap. Aldrig ur World."""
        return []

    def system_items(self) -> list:
        """Systemtavlans element (sim.systems) ur stationens egna instrument."""
        return []

    def propose(self, p: Proposal) -> bool:
        return self.suggest(p.key, p.type, p.data, order=p.order, cooldown=p.cooldown,
                            quality=p.quality)

    # --- vägen till sanningen ---------------------------------------------------
    @property
    def own(self) -> OwnShip:
        """Egen ubåt: egna instrument och reglage."""
        return self.game.world.own

    @property
    def masts_free(self) -> bool:
        """Kan masterna komma upp (ingen is ovanför)? Hydrauliken känner det själv."""
        from ..ice import masts_clear
        return masts_clear(self.game.world)

    @property
    def area_nm(self) -> float:
        """Operationsområdets storlek (står i ordern)."""
        return self.game.world.size_nm

    @property
    def patrol_end(self) -> int | None:
        """Tidsgränsen i simtid (står i ordern)."""
        return self.game.world.patrol_end

    @property
    def world(self) -> World:
        """Världen, för stationens sensorer och vapen. Bara med REACHES_WORLD."""
        if not self.REACHES_WORLD:
            raise RuntimeError(f"{type(self).__name__} är ingen sensor och når inte världen")
        return self.game.world

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
        if order and any(st.vetoes(order) for st in self.game.stations):
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
