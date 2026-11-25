"""Vädret: sjögången som ändras under uppdraget (sanning).

`Environment.weather` (om scenariot har ett) sätter `Environment.sea_state` varje tick
(`World.tick`). Sjön ändras ett Beaufortsteg i taget, högst var 30–60:e minut, och drar mot
prognosens sjögång för tidpunkten (`trend`); prognosen står i ordern (kunskap), sanningen
kan avvika med ett steg åt vardera hållet inom `lo`–`hi`. Egen slumpström
(`Game.rng_for("weather")`), så att vädret inte flyttar andra dragningar; utan ström (ett
`World` utan `Game`) står sjön still.

Besättningen märker ändringen bara genom sina instrument: utkiken ser sjön
(bryggan, periskopet), sonaren hör havsbruset och trimmaren ser djupmätaren slå.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

STEP_EVERY_S = (30 * 60, 60 * 60)   # så länge mellan två möjliga ändringar
P_TOWARD = 0.6                       # steg mot prognosen när sjön inte är där
P_AWAY = 0.1                         # och bort från den
P_DRIFT = 0.2                        # vid prognosen: ett steg åt vardera hållet


@dataclass
class Weather:
    lo: int                                   # lugnast och …
    hi: int                                   # … grövst sjögången kan bli
    trend: tuple[tuple[int, int], ...] = ()   # (simtid, prognosens sjögång från den tiden)
    rng: random.Random | None = None
    next_t: int | None = field(default=None)

    def target(self, t: int, now_sea: int) -> int:
        """Prognosens sjögång vid tiden t (den senaste som börjat gälla)."""
        out = now_sea
        for at, sea in self.trend:
            if at <= t:
                out = sea
        return out

    def step(self, env, t: int) -> None:
        if self.rng is None:
            return
        if self.next_t is None:
            self.next_t = t + self.rng.randint(*STEP_EVERY_S)
            return
        if t < self.next_t:
            return
        self.next_t = t + self.rng.randint(*STEP_EVERY_S)
        cur = env.sea_state
        goal = self.target(t, cur)
        r = self.rng.random()
        if cur != goal:
            toward = 1 if goal > cur else -1
            d = toward if r < P_TOWARD else -toward if r < P_TOWARD + P_AWAY else 0
        else:
            d = -1 if r < P_DRIFT else 1 if r < 2 * P_DRIFT else 0
        env.sea_state = min(self.hi, max(self.lo, cur + d))


# --- regn och dimma ---------------------------------------------------------------------------
# Episoder som kommer och går (sanning): regn höjer havsbruset (smattret på ytan, sonar hör det) och
# ger klotter på radarn; dimma sänker sikten för periskopet, bryggan och utkiken (radarn ser genom
# den). Handelsfartygen i dimma blåser i mistluren (traffic.py). Egen slumpström
# (`Game.rng_for("showers")`); utan ström (ett `World` utan `Game`) kommer inget väder.
RAIN_RADAR_F = 0.7          # radarns räckvidd mot master i regn


@dataclass
class Showers:
    rain_per_h: float = 0.0                   # så många regnskurar per timme (i medel)
    fog_per_h: float = 0.0                    # och dimbankar
    rain_db: tuple[float, float] = (3.0, 8.0)     # havsbruset ökar så mycket (dB)
    fog_vis_nm: tuple[float, float] = (0.2, 0.8)  # sikten i dimman
    duration_s: tuple[int, int] = (15 * 60, 60 * 60)
    rng: random.Random | None = None
    kind: str | None = None                   # "rain", "fog" eller None just nu
    level: float = 0.0                        # dB (regn) eller sjömil (dimma)
    until: int = 0
    next_t: int | None = None

    def step(self, t: int) -> None:
        if self.rng is None or self.rain_per_h + self.fog_per_h <= 0:
            return
        if self.kind is not None and t >= self.until:
            self.kind = None
            self.next_t = None
        if self.kind is not None:
            return
        if self.next_t is None:
            rate = (self.rain_per_h + self.fog_per_h) / 3600.0
            self.next_t = t + int(self.rng.expovariate(rate))
            return
        if t < self.next_t:
            return
        fog = self.rng.random() < self.fog_per_h / (self.rain_per_h + self.fog_per_h)
        self.kind = "fog" if fog else "rain"
        self.level = self.rng.uniform(*(self.fog_vis_nm if fog else self.rain_db))
        self.until = t + self.rng.randint(*self.duration_s)

    def rain_db_now(self) -> float:
        return self.level if self.kind == "rain" else 0.0

    def fog_vis_now(self) -> float | None:
        return self.level if self.kind == "fog" else None
