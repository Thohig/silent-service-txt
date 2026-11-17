"""Händelsebuss mellan simulering, besättning och gränssnitt.

Allt som händer ombord publiceras här. Stationer, kunskapslagret,
gränssnittet och framtida lager (talsyntes, berättelse, politisk officer)
prenumererar på det de bryr sig om utan att känna till varandra.

Prenumeranter anropas synkront i den ordning de registrerades. Game
registrerar kunskapslagret före stationerna, så att en stations
hanterare alltid ser uppdaterad kunskap.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from .reports import Quality, Report

if TYPE_CHECKING:
    from .icemap import IceSoundingObs
    from .periscope import PeriscopePicture
    from .zigzag import ConvoyEstimate
    from .tma import BearingObs


@dataclass(frozen=True)
class Event:
    t: int


@dataclass(frozen=True)
class Tick(Event):
    pass


# --- order och rapporter ------------------------------------------------------
@dataclass(frozen=True)
class OrderIssued(Event):
    text: str
    order: Any
    by: str = "captain"           # vem som gav ordern: captain eller starpom


@dataclass(frozen=True)
class ReportDelivered(Event):
    report: Report


@dataclass(frozen=True)
class Handover(Event):
    """Uppvärmningen är slut: kaptenen tar befälet efter warm_s sekunders vakt."""
    warm_s: int


@dataclass(frozen=True)
class TimeScaleChanged(Event):
    scale: int
    reason: str = ""


# --- sensorer (det sonaroperatören uppfattar) --------------------------------
@dataclass(frozen=True)
class ContactDetected(Event):
    designation: str
    bearing: float = 0.0
    classification: str = ""
    quality: Quality = Quality.DALIG


@dataclass(frozen=True)
class PhotoTaken(Event):
    """Periskopfoto av ett spaningsmål, med bildens kvalitet."""
    quality: Quality
    target: str


@dataclass(frozen=True)
class PeriscopeSighted(Event):
    """Utkikens bild i periskopet (se sim/periscope.py). Medan masten är uppe kommer en
    bild varannan sekund (live); live=False när svepet eller titten är klar."""
    picture: PeriscopePicture
    live: bool = False


@dataclass(frozen=True)
class BridgeSighted(Event):
    """Utkikens bild från bryggan (eye "brygga"), varannan sekund medan bryggan är
    bemannad; None när bryggan utryms."""
    picture: PeriscopePicture | None


@dataclass(frozen=True)
class ConvoyAssessed(Event):
    """Plottlagets bild av en konvoj: medlemmar, ben och baskurs (se sim/zigzag.py).
    None: konvojen är inte längre en grupp i plottet."""
    estimate: ConvoyEstimate | None


@dataclass(frozen=True)
class PeriscopeBlocked(Event):
    """Periskopet kom inte upp, t.ex. för att det är is ovanför."""
    reason: str


@dataclass(frozen=True)
class HuntSigns(Event):
    """Sonar tolkar ljuden som att fienden har kontakt med oss (snabb pingtakt, sjunkbomber)."""
    reason: str


@dataclass(frozen=True)
class BearingObserved(Event):
    obs: BearingObs


@dataclass(frozen=True)
class ClassificationChanged(Event):
    designation: str
    classification: str
    quality: Quality


@dataclass(frozen=True)
class ContactLost(Event):
    designation: str


@dataclass(frozen=True)
class SoundHeard(Event):
    """Sonaren hörde en transient: ping, plask, detonation, undervattenstelefon …"""
    kind: str
    bearing: float
    designation: str | None = None
    practice: bool = False
    detail: str = ""        # t.ex. "fast" för tät pingtakt
    se: float = 0.0         # signalöverskott i dB: hur starkt det hördes


@dataclass(frozen=True)
class OwnSoundMade(Event):
    """Egen båt gav ifrån sig ett ljud som hela besättningen hör: ping, launch, blow."""
    kind: str


@dataclass(frozen=True)
class OwnActionLogged(Event):
    """En egen handling som kan ha röjt oss och som plottet skriver upp: report, periscope."""
    kind: str


@dataclass(frozen=True)
class OwnTorpedoHeard(Event):
    """Sonaren hör en egen torped. no = ordningsnummer i avfyrningsordning.

    kind: running, turned, lost, detonated, silent (se sim/sonar.py OwnTorpedo).
    """
    no: int
    kind: str
    bearing: float | None = None
    quality: Quality = Quality.OSAKER


@dataclass(frozen=True)
class IceSounded(Event):
    """Isekolodet (uppåtriktat) har lodat isen ovanför."""
    obs: IceSoundingObs


@dataclass(frozen=True)
class OpeningNotFound(Event):
    """Navigatören sökte en loggad öppning men fann tjock is: den har drivit iväg."""
    no: int


@dataclass(frozen=True)
class ListeningExercise(Event):
    """Lyssningsövningen mot det egna bevakningsfartyget pågår (eller är slut)."""
    active: bool


@dataclass(frozen=True)
class TorpedoExercise(Event):
    """Torpedövningen mot det egna bevakningsfartyget pågår (eller är slut)."""
    active: bool


@dataclass(frozen=True)
class TelegramReceived(Event):
    """Radion har tagit emot något: ett telegram från staben eller en rundradiosändning."""
    text: str               # svensk text, som loggen och telegramvyn visar den
    kind: str = "telegram"  # telegram (staben), broadcast (Radio Moskva)
    number: int = 0         # mottagningsnummer ombord


@dataclass(frozen=True)
class PositionReported(Event):
    """En position på något vi söker (t.ex. drivstationen), i beräknade koordinater."""
    name: str
    x: float
    y: float
    sigma: float            # nm vid tidpunkten t_pos
    t_pos: int
    source: str = "radio"   # radio, periskop


@dataclass(frozen=True)
class GameEnded(Event):
    outcome: str
    summary: dict


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
