"""Trim och flytkraft (sanning): hur tung ubåten är och hur den ligger.

Ubåten är trimmad för djupet den började på. Sedan ändras vikten:

- djupet: skrovet trycks ihop och båten blir tyngre ju djupare den går (`COMPRESS_T_PER_100M`);
- språngskiktet: under skiktet är vattnet kallare och tätare och bär mer (`LAYER_LIFT_T`);
  under isen ligger lättare smältvatten överst (`MELT_T`, båten tyngre där);
- torpeder och skenmål: ersättningstanken tar `REPLACE_SHARE` av vikten, resten saknas förut;
- läckvatten i kölsvinet.

Trimmaren (`sim/stations/trim.py`) pumpar vatten in i eller ur utjämningstanken (`ballast_t`)
och mellan för- och akterkantens tankar (`fore_ballast_t`). Pumparna hörs (`PUMP_LEVEL`).

Verkan: i fart bär djuprodren en obalans upp till `plane_capacity(fart)`. Det som rodren inte
bär driver båten mot ytan eller djupet (`DRIFT_M_PER_S_PER_T`) och tar över djupstyrningen.
Framåt- eller bakåtlast ger en lutning (дифферент) på `PITCH_DEG_PER_T` grader per ton.

    excess(...)          överskottsvikt i ton (+ tung, - lätt)
    plane_capacity(v)    ton som djuprodren bär i farten v
    TrimState            pumparnas och tankarnas läge
"""
from __future__ import annotations

from dataclasses import dataclass

COMPRESS_T_PER_100M = 1.0      # skrovet trycks ihop: tyngre ju djupare
LAYER_LIFT_T = 3.0             # under språngskiktet bär det kallare vattnet mer
LAYER_BAND_M = 10.0            # övergången genom skiktet
MELT_T = 1.0                   # under isen: smältvatten överst, båten tyngre där
MELT_DEPTH_M = 25.0
TORPEDO_T = 2.0                # en torped; ersättningstanken tar det mesta
DECOY_T = 0.2
REPLACE_SHARE = 0.7            # så stor del av vikten som ersättningstanken tar
PLANE_T_PER_KN2 = 0.8          # djuprodren bär 0,8·v² ton …
PLANE_MAX_T = 10.0             # … men högst så mycket
DRIFT_M_PER_S_PER_T = 0.03     # det rodren inte bär: så fort driver båten (samma som läckan förut)
DRIFT_MAX_M_PER_S = 1.5
CONTROL_LOST_T = 2.0           # så mycket över rodrens förmåga och djupstyrningen är borta
PITCH_DEG_PER_T = 0.6          # lutning per ton framåt- eller bakåtlast
PITCH_MAX_DEG = 15.0
PUMP_T_PER_MIN = 1.0           # utjämningstanken
TRANSFER_T_PER_MIN = 0.5       # mellan för och akter
BALLAST_MIN_T = -25.0          # så mycket utjämningstanken kan tömma (TRIM_RESERVE_T förut)
BALLAST_MAX_T = 15.0           # så mycket den kan ta in
FORE_MAX_T = 8.0
PUMP_LEVEL = 121.0             # dB, trimpumparna: ~+1,7 dB i smygfart (reaktorns kylpumpar 120)
SURFACING_DEPTH_M = 40.0       # order ytläge: härifrån blåses huvudbarlasten, trimmen spelar ingen roll
SURFACING_SLOW_KN = 2.0        # i så låg fart görs varje beordrad djupändring med barlasten


def ballast_carries(depth: float, ordered_depth: float, speed: float, changing: bool) -> bool:
    """Barlasten bär och trimmen spelar ingen roll: på väg upp till ytan (huvudbarlasten blåses),
    eller en ny order om djup i låg fart tills djupet är nått (lodrätt, t.ex. upp genom en öppning
    i isen). Trimmen märks när båten ska hålla djupet."""
    if ordered_depth <= 1.0 and depth <= SURFACING_DEPTH_M:
        return True
    return changing and speed <= SURFACING_SLOW_KN


def environment_weight(depth: float, env) -> float:
    """Vikten vattnet och djupet ger (ton, + tyngre), utan det trimmaren pumpat."""
    w = COMPRESS_T_PER_100M * max(depth, 0.0) / 100.0
    layer = getattr(env, "layer_depth", None)
    if layer is not None:
        f = min(1.0, max(0.0, (depth - layer + LAYER_BAND_M / 2) / LAYER_BAND_M))
        w -= LAYER_LIFT_T * f
    if getattr(env, "ice", None) is not None:
        f = min(1.0, max(0.0, (MELT_DEPTH_M + 5 - depth) / 10.0))
        w += MELT_T * f
    return w


def plane_capacity(speed: float, planes_health: float = 1.0) -> float:
    """Ton obalans som djuprodren bär i farten (knop)."""
    return min(PLANE_MAX_T, PLANE_T_PER_KN2 * max(speed, 0.0) ** 2) * max(planes_health, 0.0)


def pitch_deg(fore_t: float) -> float:
    """Lutningen: + fören ned (förlig), - fören upp."""
    return max(-PITCH_MAX_DEG, min(PITCH_MAX_DEG, PITCH_DEG_PER_T * fore_t))


@dataclass
class TrimState:
    ballast_t: float = 0.0           # utjämningstanken mot trimmen vid start (+ intaget vatten)
    fore_ballast_t: float = 0.0      # vatten flyttat förut (+) eller akterut (-)
    payload_t: float = 0.0           # torpeder och skenmål som saknas (negativt)
    payload_fore_t: float = 0.0      # det som saknas förut (negativt: fören lätt)
    pump_to_t: float | None = None   # utjämningstankens mål medan den pumpar
    fore_to_t: float | None = None   # för/akter-målet medan vatten flyttas
    hover: bool = False              # order: ligg still (djupet hålls bara med trimmen)
    weight_t: float = 0.0            # senaste överskottsvikt (uträknad i update)
    fore_t: float = 0.0              # senaste framåtlast
    free_t: float = 0.0              # det som rodren inte bär (+ tung, - lätt)
    plane_load: float = 0.0          # andel av rodrens förmåga som används (-1 … 1)
    started: bool = False            # trimmad för startdjupet
    order_depth: float | None = None # senaste beordrade djup
    changing: bool = False           # på väg mot ett nybeordrat djup

    def follow_order(self, depth: float, ordered_depth: float) -> None:
        """En ny order om djup utförs tills djupet är nått; att driva bort från det är inte det."""
        if ordered_depth != self.order_depth:
            self.order_depth = ordered_depth
            self.changing = abs(ordered_depth - depth) > 0.5
        elif self.changing and abs(ordered_depth - depth) <= 0.5:
            self.changing = False

    @property
    def pumping(self) -> bool:
        return self.pump_to_t is not None or self.fore_to_t is not None

    @property
    def pitch(self) -> float:
        return pitch_deg(self.fore_t)

    def start(self, depth: float, env) -> None:
        """Trimmad vid start: utjämningstanken tar ut vikten djupet och vattnet ger."""
        self.ballast_t = -environment_weight(depth, env)
        self.started = True

    def torpedo_fired(self) -> None:
        self._payload(TORPEDO_T)

    def decoy_launched(self) -> None:
        self._payload(DECOY_T)

    def _payload(self, tons: float) -> None:
        net = tons * (1 - REPLACE_SHARE)
        self.payload_t -= net
        self.payload_fore_t -= net

    def pump(self, ballast_to: float | None = None, fore_to: float | None = None) -> None:
        """Börja pumpa mot målen (inom tankarnas gränser)."""
        if ballast_to is not None:
            self.pump_to_t = max(BALLAST_MIN_T, min(BALLAST_MAX_T, ballast_to))
        if fore_to is not None:
            self.fore_to_t = max(-FORE_MAX_T, min(FORE_MAX_T, fore_to))

    def stop_pumps(self) -> None:
        self.pump_to_t = None
        self.fore_to_t = None

    def step_pumps(self, dt: float, power: bool) -> None:
        if not power:
            return
        if self.pump_to_t is not None:
            self.ballast_t = _approach(self.ballast_t, self.pump_to_t, PUMP_T_PER_MIN / 60 * dt)
            if self.ballast_t == self.pump_to_t:
                self.pump_to_t = None
        if self.fore_to_t is not None:
            self.fore_ballast_t = _approach(self.fore_ballast_t, self.fore_to_t,
                                            TRANSFER_T_PER_MIN / 60 * dt)
            if self.fore_ballast_t == self.fore_to_t:
                self.fore_to_t = None

    def weigh(self, depth: float, env, flooding_t: float) -> None:
        """Räkna överskottsvikt och framåtlast just nu."""
        self.weight_t = environment_weight(depth, env) + self.ballast_t + self.payload_t + flooding_t
        self.fore_t = self.fore_ballast_t + self.payload_fore_t


def _approach(value: float, target: float, step: float) -> float:
    if abs(target - value) <= step:
        return target
    return value + step if target > value else value - step
