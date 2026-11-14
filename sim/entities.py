"""Grundtyper för sanningslagret: fartyg, transienter och emissioner."""
from __future__ import annotations

from dataclasses import dataclass

from . import acoustics
from .ship import ShipState


@dataclass
class Vessel:
    id: str          # sanningens id, t.ex. "DD1" – visas aldrig för spelaren
    kind: str        # "submarine", "destroyer", "torpedo", "decoy", ...
    state: ShipState
    side: str = "enemy"     # "own", "enemy", "neutral"
    sunk: bool = False
    has_radar: bool = False

    @property
    def depth(self) -> float:
        return self.state.depth

    @property
    def is_ship(self) -> bool:
        return self.kind not in ("torpedo", "decoy", "ice")

    def radiated_level(self, env) -> float:
        """Utstrålat bredbandsljud (dB). Sjunkna fartyg är tysta."""
        if self.sunk:
            return -999.0
        return acoustics.source_level(self.kind, self.state.speed)

    @property
    def target_strength(self) -> float:
        return acoustics.TARGET_STRENGTH.get(self.kind, 15.0)


@dataclass(frozen=True)
class Transient:
    """Momentant ljud: ping, plask, explosion, utskjutning, undervattenstelefon …"""
    kind: str
    x: float
    y: float
    depth: float
    level: float
    source_id: str
    t: int
    practice: bool = False


@dataclass(frozen=True)
class Emission:
    """Elektromagnetisk utsändning: radar eller kortvågsradio."""
    kind: str        # "radar", "hf"
    x: float
    y: float
    source_id: str
    t: int
