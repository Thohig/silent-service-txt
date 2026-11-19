"""Krigsbedömningen inför kärnvapenrådet (KV3, kunskap: bara det besättningen vet).

`assess(knowledge, now)` svarar på det zampoliten och starpom väger:
- vad ordern säger om kärnladdningen (det senast lästa, `Knowledge.nuclear_order`)
- om Moskva sagt att det är krig
- om vi angrips med skarpa sjunkbomber: de bedömda bomberna (`Knowledge.charges`, sonaren och
  maskin) de senaste `ATTACK_WINDOW_S` nära oss; kvaliteten är den bästa bedömningens
- om vi kan nå staben: inte medan vi är jagade, angripna nyss eller har en hotkontakt nära

Officerarnas regler (`zampolit_vote`, `starpom_vote`) är fasta, ingen slump: zampoliten följer
partilinjen och ordern, starpom (Archipovs plats på B-59) kräver säkerhet; utan order från Moskva
dessutom att staben inte kan nås och att bomberna skadat skrovet (B-59-ubåtarnas regel: bara om
skrovet är skadat). Ett uttryckligt förbud häver ingen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .reports import Quality

if TYPE_CHECKING:
    from .knowledge import Knowledge

ATTACK_WINDOW_S = 30 * 60      # skarpa bomber så nyligen räknas som ett angrepp
REACH_BLOCK_S = 10 * 60        # så länge efter ett angrepp kan vi inte gå upp och fråga staben
THREAT_NEAR_NM = 3.0           # en hotkontakt med lösning så nära: vi kan inte gå upp


@dataclass(frozen=True)
class WarAssessment:
    order: str                  # forbidden, order_only, conditional, authorized
    order_source: str           # "ordern", "telegram 2"
    order_age_s: int
    war: bool                   # Moskva har sagt att det är krig
    attacked: bool              # vi angrips med skarpa sjunkbomber
    attacked_q: Quality         # hur säkert det är (åt endera hållet)
    signal_only: bool           # det vi angrips med är signalladdningar
    charges: int                # bedömda bomber nära oss i fönstret
    reach_staff: bool           # vi kan gå upp och fråga staben
    reach_why: str              # varför inte: hunted, attacked, threat (tomt om vi kan)
    damaged: bool = False       # sjunkbomberna har skadat skrovet (maskin) i fönstret


def assess(k: Knowledge, now: int) -> WarAssessment:
    order, order_t, source = k.nuclear_order()
    war, _wt, _ws = k.at_war()
    since = now - ATTACK_WINDOW_S
    if order == "conditional":
        since = max(since, order_t)          # villkoret räknas från telegrammet
    near = [c for c in k.charges if c.t >= since and c.near]
    real = [c for c in near if c.real]
    if real:
        attacked, q = True, max(c.quality for c in real)
    elif near:
        attacked, q = False, max(c.quality for c in near)
    else:
        attacked, q = False, Quality.SAKER if not k.charges else Quality.GOD
    recent = any(c.real and c.near and now - c.t <= REACH_BLOCK_S for c in k.charges)
    threat = any(t.threat and t.solution is not None and t.solution.quality >= Quality.OSAKER
                 and t.solution.range_nm < THREAT_NEAR_NM for t in k.tracks.values())
    why = "hunted" if k.hunted(now) else "attacked" if recent else "threat" if threat else ""
    damaged = any(c.damage for c in real)
    return WarAssessment(order, source, now - order_t, war, attacked, q,
                         bool(near) and not real, len(near), not why, why, damaged)


@dataclass(frozen=True)
class Vote:
    yes: bool
    why: str                    # nyckel för frasen: forbidden, authorized, condition_met, …
    suggest: str | None = None  # ja-order starpom föreslår i stället (aldrig att skjuta)


def zampolit_vote(a: WarAssessment) -> Vote:
    """Zampoliten: ordern och partilinjen. Ja med tillstånd, med uppfyllt villkor, eller utan
    order när vi angrips skarpt med minst god kvalitet."""
    if a.order == "forbidden":
        return Vote(False, "forbidden")
    if a.order == "authorized":
        return Vote(True, "authorized")
    sure = a.attacked and a.attacked_q >= Quality.GOD
    if a.order == "conditional":
        return Vote(True, "condition_met") if sure else Vote(False, "condition_unmet")
    return Vote(True, "attacked") if sure else Vote(False, "no_order")


def starpom_vote(a: WarAssessment) -> Vote:
    """Starpom: ja med tillstånd; med villkoret bara om angreppet är säkert; utan order bara om
    angreppet är säkert och staben inte kan nås. Annars nej, med ett annat förslag."""
    away = "djup 150"
    ask = "sänd kort rapport"
    if a.order == "forbidden":
        return Vote(False, "forbidden", away)
    if a.order == "authorized":
        return Vote(True, "authorized")
    sure = a.attacked and a.attacked_q == Quality.SAKER
    if a.order == "conditional":
        return Vote(True, "condition_met") if sure else Vote(False, "condition_unsure", away)
    if not sure:
        return Vote(False, "no_order" if not a.attacked else "attack_unsure", away)
    if a.reach_staff:
        return Vote(False, "ask_staff", ask)
    if not a.damaged:                    # B-59: utan order bara om skrovet är skadat
        return Vote(False, "not_damaged", away)
    return Vote(True, "attacked_cut_off")
