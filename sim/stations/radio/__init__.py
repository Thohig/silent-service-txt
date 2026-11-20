"""Radio: sambandstillfällen med huvudstaben och rapportsändning.

Staben sänder vid sambandstillfällena enligt schemat; det vi missar sänds om vid nästa.
Mottagning: på antenndjup med masten (en minut), eller på djupet på långvåg med flytkabeln
(högst VLF_DEPTH meter och VLF_SPEED knop, fem minuter; kabeln flyter inte under is).
Långvågen kommer in hel eller stympad (`_vlf_quality`: mörker, låg fart och grunt hjälper);
stympat visas med oläsbara grupper och radion lyssnar vidare på omsändningen.
Sändning (kortvåg) kräver periskopdjup och kan pejlas av fienden.

Paketet: station.py (stationen, order, tavlan, förslagen, update, radiospaningen), common.py
(konstanter, order, `garble`), phrases.py, och delarna som RadioStation ärver: reception.py
(mottagningen) och sending.py (rapporten, pejlrisken, råden)."""
from __future__ import annotations

from . import phrases  # noqa: F401  (registrerar fraserna)
from .common import (  # noqa: F401
    AIR_LEFT_S, AIR_QUIET_S, GARBLE_P, INTERCEPT_S, LISTEN_S, RADIO_SAFE_NM, RECEIVE_S,
    VLF_DEPTH, VLF_RECEIVE_S, VLF_SLOW_KN, VLF_SPEED, VLF_UP_DEPTH,
    Intercept, ListenBroadcast, RadioStatus, SendReport, garble,
)
from .station import RadioStation  # noqa: F401
