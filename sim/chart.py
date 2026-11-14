"""Sjökortet: vad besättningen vet, som ritelement (kunskap, aldrig sanning).

Varje station bidrar med egna element via `Station.chart_items()`; Game
samlar dem i en `ChartView`. Allt är i sjömil i kvadratens koordinater (x
österut, y norrut) och bygger på navigatörens beräknade positioner, så
kortet blir lika fel som besticket. Gränssnittet rastrerar elementen.

Stilarna är nycklar ("own", "contact", "ice_open" …) som gränssnittet
översätter till färg; `quality` styr färgen där den finns.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .reports import Quality

# Ritordning: lägre lager ritas först och skrivs över av högre.
LAYER_CONTOUR = -0.5        # djupkurvorna: under allt utom rutnätet
LAYER_TRACK = 0
LAYER_ICE = 1               # lodningarna ligger längs spåret och säger mer än det
LAYER_RING = 2
LAYER_RAY = 3
LAYER_MARK = 4
LAYER_OWN = 5


@dataclass(frozen=True)
class Mark:
    """En punkt med en symbol och en etikett bredvid."""
    x: float
    y: float
    symbol: str
    style: str
    label: str = ""
    quality: Quality | None = None
    faded: bool = False
    layer: int = LAYER_MARK


@dataclass(frozen=True)
class Ray:
    """En linje från (x, y) längs en bäring, t.ex. en bäring utan lösning."""
    x: float
    y: float
    bearing: float
    length: float
    style: str
    label: str = ""
    quality: Quality | None = None
    faded: bool = False
    layer: int = LAYER_RAY


@dataclass(frozen=True)
class Ring:
    """En osäkerhetscirkel."""
    x: float
    y: float
    radius: float
    style: str
    quality: Quality | None = None
    layer: int = LAYER_RING


@dataclass(frozen=True)
class Track:
    """Ett spår av punkter (besticket, djupkurvor). char None: tecknet följer linjens riktning."""
    points: tuple[tuple[float, float], ...]
    style: str
    layer: float = LAYER_TRACK
    char: str | None = "·"


@dataclass(frozen=True)
class Note:
    """En rad i kortets rubrik, t.ex. bestickets osäkerhet."""
    text: str
    quality: Quality | None = None


ChartItem = Mark | Ray | Ring | Track | Note


@dataclass
class ChartView:
    clock: str
    area_name: str
    size_nm: float
    own: tuple[float, float]               # beräknad position, för centrering
    items: list[ChartItem] = field(default_factory=list)

    @property
    def notes(self) -> list[Note]:
        return [i for i in self.items if isinstance(i, Note)]

    @property
    def drawables(self) -> list[ChartItem]:
        return sorted((i for i in self.items if not isinstance(i, Note)),
                      key=lambda i: i.layer)
