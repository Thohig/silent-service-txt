"""Torpedrum och eldledning: tuber, laddning, skjutlösningar, avfyring och skenmål.

Eldledningen räknar bara på kunskap: plottlagets lösning och navigatörens
bestick. Avfyring kräver alltid en uttrycklig order; torpedofficeren
meddelar när en skjutlösning finns men föreslår aldrig avfyring som en
order som kan godkännas med "ja".

Torpeder i vattnet följs via sonaren (OwnTorpedoHeard): normal gång,
sväng (målsökning), tappad, detonation och tystnad utan detonation. Hörs
ingenting innan räckvidden är slut rapporteras en trolig miss. Sonaren
numrerar egna torpeder i avfyrningsordning; torpedrummet gör detsamma
och knyter numret till tuben. Alla torpeder avfyras därför här.

Paketet: station.py (stationen, order, laddning, torpederna i vattnet, kortet), common.py
(konstanter, order, tuber), phrases.py, och firing.py (eldledningen, `FiringMixin`) och wire.py
(trådstyrningen av 53-62T, `WireMixin`) som TorpedoRoom ärver."""
from __future__ import annotations

from . import phrases  # noqa: F401  (registrerar fraserna)
from .common import (  # noqa: F401
    CONFIRM_S, END_GRACE_S, MAX_LAUNCH_DEPTH, MAX_LAUNCH_SPEED, N_TUBES, RELOAD_CLANK_S,
    RELOAD_QUIET_S, RELOAD_S, SALVO_MAX, TYPE_ALIASES,
    CutWire, FireAt, FireSalvo, FireTube, FiringSolution, LaunchDecoy, LoadTube, Running, TorpedoReport,
    TorpedoStatus, Tube, TubeStatus,
)
from .station import TorpedoRoom  # noqa: F401
