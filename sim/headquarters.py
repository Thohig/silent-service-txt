"""Huvudstaben (R3): vet bara vad vi har sänt (`ReportTransmitted`) och vad ordern väntar sig.

Staben skriver telegram som radion tar emot vid nästa sambandstillfälle, efter scenariots egna:
kvittens på varje rapport, följduppdrag ur rapportens innehåll (konvoj, örlogsfartyg, att vi
varit jagade) och en upptrappning när en rapport väntas och vi tiger. Reglerna är desamma i
alla scenarier; scenariot säger bara om en rapport väntas (`Scenario.report_required` eller ett
telegram med flaggan `report_requested`).

Staben läser aldrig världen. Det vi rapporterat sparas (`received`) för en kampanj, där fel
uppgifter kan styra nästa uppdrag.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .dispatch import SentReport
from .events import EventBus, ReportTransmitted

MAX_PER_WINDOW = 3          # fler stabstelegram än så vid ett sambandstillfälle blir det inte

SILENCE = (
    "FRÅN HUVUDSTABEN. RAPPORT SAKNAS. RAPPORTERA LÄGE VID NÄSTA SAMBANDSTILLFÄLLE.",
    "FRÅN HUVUDSTABEN. INGEN RAPPORT MOTTAGEN. BEKRÄFTA ATT NI ÄR OSKADDA. RAPPORTERA OMEDELBART.",
)


@dataclass
class Headquarters:
    expects_report: bool = False
    received: list[SentReport] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)
    silent_windows: int = 0         # sambandstillfällen i rad utan väntad rapport
    _asked_convoy: bool = False
    _warned: set[str] = field(default_factory=set)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(ReportTransmitted, self._on_report)

    def request_report(self) -> None:
        """Ett telegram (scenariots) ber om rapport: från nu väntar staben en."""
        self.expects_report = True

    def _on_report(self, e: ReportTransmitted) -> None:
        if not e.complete:
            return                  # staben fick inget, även om fienden kan ha pejlat
        r: SentReport = e.report
        self.received.append(r)
        self.silent_windows = 0
        self.queue.append(f"FRÅN HUVUDSTABEN. ER RAPPORT NR {r.number} MOTTAGEN.")
        if r.convoy is not None and not self._asked_convoy:
            self._asked_convoy = True
            self.queue.append("FRÅN HUVUDSTABEN. FÖLJ KONVOJEN. RAPPORTERA KURS OCH FART VID "
                              "NÄSTA SAMBANDSTILLFÄLLE.")
            self.expects_report = True
        for c in r.contacts:
            if c.designation in self._warned:
                continue
            if any(w in c.classification for w in ("jagare", "bevakningsfartyg", "patrullbåt")):
                self._warned.add(c.designation)
                self.queue.append(f"FRÅN HUVUDSTABEN. {c.designation} UPPFATTAD. UNDVIK "
                                  "UPPTÄCKT. ANGRIP EJ UTAN ORDER.")
        if "hunted" in r.events:
            self.queue.append("FRÅN HUVUDSTABEN. BRYT KONTAKTEN MED FÖRFÖLJARNA. "
                              "RAPPORTERA NÄR NI ÄR FRIA.")

    def window_closed(self, reported: bool) -> None:
        """Ett sambandstillfälle har stängt: tystnad när en rapport väntades trappar upp."""
        if not self.expects_report or reported:
            return
        self.queue.append(SILENCE[min(self.silent_windows, len(SILENCE) - 1)])
        self.silent_windows += 1

    def outgoing(self) -> list[str]:
        """Stabens telegram till detta sambandstillfälle (tas ur kön)."""
        out, self.queue = self.queue[:MAX_PER_WINDOW], self.queue[MAX_PER_WINDOW:]
        return out
