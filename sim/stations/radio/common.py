"""Radions konstanter, order och den stympade långvågen."""
from __future__ import annotations

from dataclasses import dataclass

from ...orders import Order


RECEIVE_S = 60
RISK_LONG_S = 45             # så lång sändning: pejlas med god noggrannhet
RISK_MID_S = 25
RISK_NEAR_NM = 8.0           # en hotkontakt så nära i plottet: hör sändningen
RISK_MID_NM = 15.0
PREWARN_S = 600
CLOSING_WARN_S = 300        # fönstret stänger om så här länge utan rapport: radion säger det (högst halva fönstret)
RADIO_SAFE_NM = 5.0          # en hotkontakt närmare än så enligt plottet: vänta med att gå upp
REPORT_SUGGEST_S = 180       # förslaget att sända upprepas högst så här ofta
AIR_QUIET_S = 120            # så länge efter flygradar nära innan radion föreslår att gå upp igen
AIR_LEFT_S = 150             # minst så mycket kvar av fönstret: upp från djupet och trettio sekunder sändning
INTERCEPT_S = 60             # radiospaning: så länge radiomannen avlyssnar trafiken
INTERCEPT_AIR_NM = 150       # flygradion hörs så långt (VHF/UHF från höjd)
INTERCEPT_SHIP_NM = 60       # fartygens radiotelefoni
INTERCEPT_AGAIN_S = 1800     # radiomannen föreslår en ny avlyssning högst så här ofta
INTERCEPT_HUNT_S = 600       # jagarna har haft kontakt så nyss: deras trafik är livlig
LISTEN_S = 20                # så länge radiomannen letar upp Moskva på kortvåg
RADIO_VAK_MAX_M = 2500        # öppningar längre bort hinner vi inte till
VLF_DEPTH = 50.0             # flytkabeln: djupare än så räcker den inte till ytan
VLF_SPEED = 5.0              # fortare än så dras kabeln under
VLF_UP_DEPTH = 40            # radiomannen föreslår det här djupet för långvågen
VLF_SLOW_KN = 3              # och den här farten
VLF_RECEIVE_S = 300          # långvågen är långsam: så länge tar mottagningen
GARBLE_P = 0.45              # stympad: så stor del av grupperna går förlorade


@dataclass(frozen=True)
class SendReport(Order):
    kind: str = "full"              # full, short (läge och det som hänt), contact (en kontakt)
    target: str | None = None


@dataclass(frozen=True)
class RadioStatus(Order):
    pass


@dataclass(frozen=True)
class ListenBroadcast(Order):
    pass


@dataclass(frozen=True)
class Intercept(Order):
    """Radiospaning: avlyssna amerikansk trafik på antenndjup."""

def garble(text: str, rng) -> str:
    """Stympad mottagning: en del av grupperna oläsbara (samma längd, ░)."""
    words = text.split(" ")
    idx = [i for i, w in enumerate(words) if sum(ch.isalnum() for ch in w) >= 2]
    if not idx:
        return text
    lost = {i for i in idx if rng.random() < GARBLE_P} or {rng.choice(idx)}
    return " ".join("░" * len(w) if i in lost else w for i, w in enumerate(words))
