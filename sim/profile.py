"""Djupprofilen: ubåten sedd från sidan, över tid (kunskap, aldrig sanning).

Motsvarigheten till sjökortet i höjdled. Varje station bidrar med egna
element via `Station.profile_items()`; Game samlar dem i en `ProfileView`.
Den vågräta axeln är simtid (sekunder), den lodräta djup i meter. Allt
bygger på vad besättningen vet: djupmätaren, sonarens språngskikt,
isekolodets lodningar, ekolodets lodningar av botten och ljud sonar hört.
Gränssnittet rastrerar elementen (ui/profile_render.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .reports import Quality


@dataclass(frozen=True)
class Level:
    """Ett vågrätt djup: periskopdjup, språngskikt, provdjup, krossdjup."""
    depth: float
    label: str
    style: str
    char: str = "─"


@dataclass(frozen=True)
class DepthTrace:
    """Egen ubåts djup över tid, enligt djupmätaren: (t, djup)."""
    points: tuple[tuple[int, float], ...]
    style: str = "own"


@dataclass(frozen=True)
class BottomSounding:
    """Ekolodets lodning: botten på detta djup vid tiden t."""
    t: int
    depth: float


@dataclass(frozen=True)
class IceSounding:
    """Isekolodets lodning: tjocklek och isens undersida (meter) vid tiden t."""
    t: int
    thickness: float
    draft: float
    open: bool
    usable: bool


@dataclass(frozen=True)
class HeardEvent:
    """Något sonar hörde (eller vi själva gjorde) vid tiden t, med en symbol."""
    t: int
    kind: str
    symbol: str
    style: str
    near: bool = False


@dataclass(frozen=True)
class ProfileNote:
    text: str
    quality: Quality | None = None


ProfileItem = Level | DepthTrace | BottomSounding | IceSounding | HeardEvent | ProfileNote


@dataclass
class ProfileView:
    clock: str
    now: int                        # simtid, sekunder
    start_clock: int                # klockan vid simtid 0, sekunder efter midnatt
    depth: float                    # djupmätaren
    ordered_depth: float
    speed: float
    course: float
    items: list[ProfileItem] = field(default_factory=list)

    def of(self, cls: type) -> list:
        return [i for i in self.items if isinstance(i, cls)]

    @property
    def notes(self) -> list[ProfileNote]:
        return self.of(ProfileNote)

    @property
    def levels(self) -> list[Level]:
        return sorted(self.of(Level), key=lambda lv: lv.depth)

    @property
    def trace(self) -> list[tuple[int, float]]:
        return [p for tr in self.of(DepthTrace) for p in tr.points]

    @property
    def bottom(self) -> list[BottomSounding]:
        return sorted(self.of(BottomSounding), key=lambda b: b.t)

    @property
    def ice(self) -> list[IceSounding]:
        return sorted(self.of(IceSounding), key=lambda s: s.t)

    @property
    def events(self) -> list[HeardEvent]:
        return sorted(self.of(HeardEvent), key=lambda e: e.t)

    def latest_bottom(self) -> BottomSounding | None:
        b = self.bottom
        return b[-1] if b else None
