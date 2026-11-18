"""Rapporten till huvudstaben (донесение): byggs ur kunskapen, aldrig ur sanningen.

Radiomannen sätter ihop rapporten när kaptenen beordrar en sändning. Innehållet avgör längden
(grupper), och längden avgör sändningstiden i morse och hur väl fienden hinner pejla den.
Huvudstaben (`headquarters.py`) och slutrapporten (`goals.py`) läser vad vi sänt
(`ReportTransmitted`).
"""
from __future__ import annotations

from dataclasses import dataclass

from .fmt import fmt_course, nm
from .knowledge import Knowledge
from .reports import Quality

# Morse 1962: radiomannen sänder en femsiffergrupp på ungefär fyra sekunder; anrop och
# kvittens tar några sekunder till.
BASE_S = 6
GROUP_S = 4
HEADER_GROUPS = 2           # anrop, datum-tid-grupp
POSITION_GROUPS = 2
CONTACT_GROUPS = 3          # klass, läge, kurs och fart
CONVOY_GROUPS = 2
EVENT_GROUPS = 1
MAX_CONTACTS = 5            # fler än så får inte plats i en rapport: de viktigaste först
REPORT_MIN_QUALITY = Quality.OSAKER


@dataclass(frozen=True)
class ReportedContact:
    designation: str
    classification: str
    x: float                # beräknat läge (bestickets koordinater) när rapporten skrevs
    y: float
    course: float
    speed: float
    quality: Quality
    t: int                  # tid lösningen avser


@dataclass(frozen=True)
class ReportedConvoy:
    x: float
    y: float
    course: float
    speed: float
    quality: Quality
    members: int
    escorts: int


@dataclass(frozen=True)
class SentReport:
    """Det vi sänt (eller börjat sända) till staben."""
    t: int
    kind: str                           # "full", "short", "contact"
    position: tuple[float, float, float]   # bestick x, y, σ nm
    contacts: tuple[ReportedContact, ...] = ()
    convoy: ReportedConvoy | None = None
    events: tuple[str, ...] = ()        # "photo", "hit", "hunted"
    number: int = 0                     # utgående nummer ombord

    @property
    def groups(self) -> int:
        return (HEADER_GROUPS + POSITION_GROUPS + CONTACT_GROUPS * len(self.contacts)
                + (CONVOY_GROUPS if self.convoy else 0) + EVENT_GROUPS * len(self.events))

    @property
    def duration_s(self) -> int:
        return BASE_S + GROUP_S * self.groups


def _contacts(k: Knowledge, target: str | None) -> list[ReportedContact]:
    out = []
    for tr in k.tracks.values():
        sol = tr.solution
        if sol is None or sol.quality < REPORT_MIN_QUALITY:
            continue
        if target is not None and tr.designation != target:
            continue
        if target is None and (tr.benign and "handelsfartyg" not in tr.classification):
            continue            # isljud och drivstationen hör inte hemma i rapporten
        out.append(ReportedContact(tr.designation, tr.classification, sol.x, sol.y, sol.course,
                                   sol.speed, sol.quality, sol.t))
    # hot först, sedan bästa lösningen
    out.sort(key=lambda c: (not any(w in c.classification for w in ("jagare", "ubåt", "patrull",
                                                                       "bevakning")),
                            -int(c.quality)))
    return out[:MAX_CONTACTS]


def _convoy(k: Knowledge, now: int) -> ReportedConvoy | None:
    c = k.convoy
    if c is None:
        return None
    x, y, course, speed = c.advance(now)
    q = c.base.quality if c.base is not None else Quality.OSAKER
    return ReportedConvoy(x, y, course, speed, q, len(c.members), len(c.escorts))


def compose(k: Knowledge, now: int, position: tuple[float, float, float], kind: str = "full",
            target: str | None = None, events: tuple[str, ...] = (), number: int = 0) -> SentReport:
    """Rapporten ur kunskapen. kind: full (allt), short (läge och det som hänt), contact (en
    kontakt, `target`)."""
    if kind == "short":
        return SentReport(now, kind, position, events=events, number=number)
    contacts = tuple(_contacts(k, target if kind == "contact" else None))
    convoy = _convoy(k, now) if kind == "full" else None
    return SentReport(now, kind, position, contacts, convoy, events if kind == "full" else (),
                      number)


EVENT_TEXT = {"photo": "SPANINGSFOTO TAGET", "hit": "TORPEDTRÄFF HÖRD",
              "hunted": "VI HAR VARIT JAGADE"}


def report_text(r: SentReport) -> str:
    """Rapportens klartext, som remsan i loggboken visar den (versaler, som telegrammen)."""
    x, y, sigma = r.position
    parts = [f"TILL HUVUDSTABEN. EGET LÄGE {nm(x)} Ö {nm(y)} N I KVADRATEN, ± {nm(sigma)} NM."]
    for c in r.contacts:
        parts.append(f"{c.designation} {c.classification.upper()} I {nm(c.x)} Ö {nm(c.y)} N, "
                     f"KURS {fmt_course(c.course)}, {c.speed:.0f} KNOP ({c.quality.label.upper()}).")
    if r.convoy is not None:
        cv = r.convoy
        parts.append(f"KONVOJ {cv.members} FARTYG, {cv.escorts} ESKORT, I {nm(cv.x)} Ö {nm(cv.y)} N, "
                     f"BASKURS {fmt_course(cv.course)}, {cv.speed:.0f} KNOP "
                     f"({cv.quality.label.upper()}).")
    for e in r.events:
        parts.append(EVENT_TEXT.get(e, e.upper()) + ".")
    if r.kind == "short" and not r.events:
        parts.append("INGET ATT RAPPORTERA.")
    return " ".join(parts)
