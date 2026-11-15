"""Loggboken: vad som hände under patrullen, sett från ubåten.

Loggboken byggs bara av det besättningen rapporterat (ReportDelivered) och
kaptenens order (OrderIssued), aldrig av sanningen. Den används för den korta
rapporten när spelet slutar.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .events import EventBus, OrderIssued, ReportDelivered
from .orders import (AcceptSuggestion, AskSuggestion, DeclineSuggestion, Help, Quit,
                     SetTimeScale, Unknown)

MAX_EVENTS = 8
SAME_EVENT_S = 900          # samma slags händelse räknas en gång per kvart
EVENT_TEXT_MAX = 100

# rapporter som alltid hör hemma bland viktiga händelser, även utan larm
_NOTABLE = {"sonar.new_contact", "torp.fired", "torp.run.hit", "torp.run.silent",
            "torp.run.timeout", "sonar.breakup", "radio.message", "radio.sent", "damage",
            "off.periscope.contact"}


@dataclass
class Logbook:
    clock: Callable[[int], str]
    start_t: int = 0
    counts: Counter = field(default_factory=Counter)
    orders: int = 0
    events: list[tuple[int, str, str]] = field(default_factory=list)   # (t, typ, text)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(ReportDelivered, self._on_report)
        bus.subscribe(OrderIssued, self._on_order)

    def _on_order(self, e: OrderIssued) -> None:
        if not isinstance(e.order, (Unknown, Help, SetTimeScale, AskSuggestion, Quit,
                                    AcceptSuggestion, DeclineSuggestion)) \
                and not e.order.INSTRUMENT:
            self.orders += 1

    def _on_report(self, e: ReportDelivered) -> None:
        r = e.report
        key = r.type
        if r.type == "sonar.explosion":
            key = "sonar.explosion.practice" if r.data.get("practice") else "sonar.explosion.real"
        self.counts[key] += 1
        if (r.alarm or r.type in _NOTABLE) and r.kind != "suggest":
            # samma slags händelse tätt inpå varandra räknas en gång
            if not any(typ == r.type and e.t - t0 < SAME_EVENT_S for t0, typ, _ in self.events):
                self.events.append((e.t, r.type, r.text))

    # --- rapporten ------------------------------------------------------------
    def report(self, now: int, knowledge) -> dict:
        c = self.counts
        dur = now - self.start_t
        rows: list[tuple[str, str]] = [
            ("Tid i befäl", f"{self.clock(self.start_t)[:5]}–{self.clock(now)[:5]} "
                            f"({dur // 3600} h {dur % 3600 // 60:02d} min)"),
            ("Order", f"{self.orders} givna, {_n(c['order.executing'], 'förslag', 'förslag')} "
                      "godkända"),
        ]
        tracks = sorted(knowledge.tracks.values(), key=lambda t: t.first_t)
        rows.append(("Kontakter", "; ".join(f"{t.designation} ({t.classification})"
                                            for t in tracks) or "inga"))
        fired = c["torp.fired"]
        if fired:
            misses = c["torp.run.silent"] + c["torp.run.timeout"]
            rows.append(("Torpeder", f"{fired} avfyrade, {_n(c['torp.run.hit'], 'träff', 'träffar')}, "
                                     f"{_n(misses, 'miss', 'missar')}"))
        if c["sonar.breakup"]:
            rows.append(("Fartyg som hörts sjunka", str(c["sonar.breakup"])))
        practice, real = c["sonar.explosion.practice"], c["sonar.explosion.real"]
        if practice or real:
            rows.append(("Sjunkbomber hörda", f"{_n(practice, 'signalladdning', 'signalladdningar')}, "
                                              f"{real} skarpa"))
        rows.append(("Skador", _n(c["damage"], "skaderapport", "skaderapporter")
                     if c["damage"] else "inga"))
        if c["radio.sent"] or c["radio.message"]:
            rows.append(("Radio", f"{_n(c['radio.sent'], 'rapport', 'rapporter')} sända, "
                                  f"{_n(c['radio.message'], 'meddelande', 'meddelanden')} mottagna"))
        events = self.events
        if len(events) > MAX_EVENTS:            # första och senaste händelserna
            half = MAX_EVENTS // 2
            events = events[:half] + events[-half:]
        return {
            "rows": rows,
            "events": [(self.clock(t)[:5], _short(text)) for t, _, text in events],
        }


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _short(text: str) -> str:
    text = text.split(" [ja:")[0]
    return text if len(text) <= EVENT_TEXT_MAX else text[: EVENT_TEXT_MAX - 1].rstrip() + "…"
