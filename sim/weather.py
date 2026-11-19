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
