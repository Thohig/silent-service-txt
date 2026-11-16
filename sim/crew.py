"""Besättningsmedlemmar.

Skickligheten påverkar brus och reaktionstid. All påverkan går via
effective_skill(), så att framtida trötthet, moral m.m. bara behöver
ändras där.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    SONAR = "sonar"
    NAVIGATOR = "navigator"
    PLOT = "plot"
    ENGINEER = "engineer"
    TORPEDO = "torpedo"
    OFFICER = "officer"
    RADIO = "radio"
    XO = "starpom"           # förste officer (старпом), tvåa i befälsordningen


ROLE_LABEL = {
    Role.SONAR: "Sonar",
    Role.NAVIGATOR: "Navigatör",
    Role.PLOT: "Plottet",
    Role.ENGINEER: "Maskin",
    Role.TORPEDO: "Torped",
    Role.OFFICER: "Vakthavande",
    Role.RADIO: "Radio",
    Role.XO: "Starpom",
}


@dataclass
class CrewMember:
    name: str
    role: Role
    skill: float                 # 0..1
    rank: str = ""
    # Utbyggnad: trötthet, moral, lojalitet, hemligheter.
    traits: dict[str, float] = field(default_factory=dict)

    @property
    def callsign(self) -> str:
        return f"{ROLE_LABEL[self.role]} ({self.name})"

    def effective_skill(self) -> float:
        # rök ombord: huvudvärk, rinnande ögon, sämre omdöme
        smoke = self.traits.get("smoke", 0.0)
        return min(max(self.skill * (1.0 - 0.5 * smoke), 0.0), 1.0)

    # --- härledda egenskaper ---------------------------------------------
    def bearing_sigma(self) -> float:
        """Grundbrus i bäring (grader, 1σ) vid god signal."""
        return 0.4 + 2.0 * (1.0 - self.effective_skill())

    def detection_threshold(self) -> float:
        """DT i dB: hur tydlig signalen måste vara för att uppfattas."""
        return 2.0 + 6.0 * (1.0 - self.effective_skill())

    def detection_time(self) -> int:
        """Sekunder med hörbar signal innan operatören är säker nog att ropa."""
        return int(5 + 25 * (1.0 - self.effective_skill()))

    def report_delay(self, rng: random.Random) -> int:
        """Sekunder från händelse till muntlig rapport."""
        return 1 + round(6 * (1.0 - self.effective_skill())) + rng.randint(0, 2)
