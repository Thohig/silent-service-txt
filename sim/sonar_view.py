"""Sonarvyn: vattenfallet, bäring mot tid (kunskap, aldrig sanning).

Det sonarrummet hört, i den ordning det hörts: varje hållen kontakts bäringar, transienter
(ping, plask, detonationer …) och tappade kontakter. Plottet lägger sin lösnings förutsagda
bäringar ovanpå och markerar när det märkt att målet girat; navigatören ger vår egen kurs
över tid (för relativ bäring) och våra girar. Varje station bidrar med `sonar_items()`,
Game samlar dem i en `SonarView` och gränssnittet ritar (ui/sonar_render.py).

Vyn förklarar vad besättningen säger. Den är inget verktyg: bäringsdriften och lösningens
kvalitet är sonarrummets och plottets egna siffror.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Sequence

from .geo import angle_diff, norm360
from .reports import Quality

if TYPE_CHECKING:
    from .knowledge import ContactTrack

KEEP_S = 3600                     # vattenfallet minns en timme bakåt
SONAR_SOURCES = ("sonar", "ping", "aktiv")   # bäringar som sonarrummet tagit (inte periskop, radar)
DRIFT_SPAN_S = 180                # bäringsdriften räknas över de senaste tre minuterna
DRIFT_MIN_OBS = 6
STEADY_DEG_PER_MIN = 0.3          # långsammare än så: bäringen står stilla
OWN_TURN_MIN_DEG = 15.0           # mindre kursändringar räknas inte som gir
OWN_TURN_START_DEG = 3.0          # så här långt från förra kursen: en gir har börjat
OWN_TURN_STEADY_DEG = 1.0         # mindre ändring mellan två loggningar: giren är slut

# Kontaktens slag (för färgen): hot, okänd, handelsfartyg, ofarligt (is, drivstation), eget
KINDS = ("threat", "contact", "civil", "benign", "friendly")


@dataclass(frozen=True)
class BearingTrace:
    """En kontakts bäringar som sonarrummet tagit: (t, bäring, signalöverskott dB)."""
    designation: str
    points: tuple[tuple[int, float, float], ...]
    kind: str = "contact"
    held: bool = True


@dataclass(frozen=True)
class HeardMark:
    """En transient som sonar hörde: ping, plask, detonation, boj …"""
    t: int
    kind: str
    bearing: float
    symbol: str
    style: str
    designation: str | None = None


@dataclass(frozen=True)
class LostMark:
    """Sonar tappade kontakten här (senaste bäringen)."""
    t: int
    designation: str
    bearing: float


@dataclass(frozen=True)
class SolutionTrace:
    """Plottets lösning: de bäringar den förutsäger för det nuvarande benet, (t, bäring)."""
    designation: str
    points: tuple[tuple[int, float], ...]
    quality: Quality
    kind: str = "contact"           # kontaktens slag (track_kind): neutrala tonas ned


@dataclass(frozen=True)
class TargetTurn:
    """Plottet märkte att målet girade ungefär här."""
    t: int
    designation: str
    bearing: float


@dataclass(frozen=True)
class OwnHeading:
    """Vår kurs över tid enligt gyrot: (t, kurs). För relativ bäring."""
    points: tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class OwnTurn:
    """Vi girade: bäringskurvorna knäcker här."""
    t: int
    course_from: float
    course_to: float


@dataclass(frozen=True)
class OwnMark:
    """Något vi själva gjorde som hörs: aktiv ping, avfyring, skenmål, nödblåsning."""
    t: int
    kind: str
    symbol: str


@dataclass(frozen=True)
class ContactLine:
    """Raden under vattenfallet: sonarrummets och plottets ord om en kontakt."""
    designation: str
    classification: str
    class_quality: Quality
    bearing: float
    drift: float | None             # grader per minut, + = drar höger (medurs)
    solution_quality: Quality | None
    kind: str = "contact"
    held: bool = True


SonarItem = (BearingTrace | HeardMark | LostMark | SolutionTrace | TargetTurn | OwnHeading
             | OwnTurn | OwnMark | ContactLine)


@dataclass
class SonarView:
    clock: str
    now: int                        # simtid, sekunder
    start_clock: int                # klockan vid simtid 0, sekunder efter midnatt
    course: float                   # vår kurs nu (gyrot)
    items: list[SonarItem] = field(default_factory=list)

    def of(self, cls: type) -> list:
        return [i for i in self.items if isinstance(i, cls)]

    @property
    def traces(self) -> list[BearingTrace]:
        return self.of(BearingTrace)

    @property
    def lines(self) -> list[ContactLine]:
        order = {k: i for i, k in enumerate(KINDS)}
        return sorted(self.of(ContactLine),
                      key=lambda c: (not c.held, order.get(c.kind, 9), c.designation))

    @cached_property
    def heading(self) -> list[tuple[int, float]]:
        """Vår kurs över tid, en punkt per tidpunkt (räknas en gång per vy)."""
        pts = sorted((p for h in self.of(OwnHeading) for p in h.points), key=lambda p: p[0])
        return [p for i, p in enumerate(pts) if i + 1 == len(pts) or pts[i + 1][0] != p[0]]

    @cached_property
    def _heading_t(self) -> list[int]:
        return [t for t, _ in self.heading]

    def heading_at(self, t: float) -> float:
        """Vår kurs vid tiden t, mellan loggningarna den korta vägen; före loggen kursen nu."""
        h = self.heading
        i = bisect.bisect_right(self._heading_t, t)
        if i == 0:
            return self.course
        t0, c0 = h[i - 1]
        if i == len(h):
            return c0
        t1, c1 = h[i]
        return norm360(c0 + angle_diff(c1, c0) * (t - t0) / (t1 - t0))


# --- hjälp för stationerna --------------------------------------------------------
def track_kind(tr: ContactTrack) -> str:
    """Kontaktens slag för färgen, ur plottets och sonarrummets klassning."""
    if tr.friendly:
        return "friendly"
    if tr.civil:
        return "civil"
    if tr.benign:
        return "benign"
    if tr.warship:
        return "threat"
    return "contact"


def bearing_drift(points: Sequence[tuple[int, float]], now: int,
                  span_s: int = DRIFT_SPAN_S) -> float | None:
    """Bäringsdriften (grader per minut, + medurs) ur de senaste bäringarna, minsta kvadrat.
    None om det är för få bäringar eller de är för gamla."""
    pts = [(t, b) for t, b in points if t >= now - span_s]
    if len(pts) < DRIFT_MIN_OBS or pts[-1][0] - pts[0][0] < span_s / 3:
        return None
    t0, b0 = pts[0]
    xs = [(t - t0) / 60.0 for t, _ in pts]
    ys = []
    prev = 0.0
    for _, b in pts:                 # bäringen utan hopp vid 360
        prev = prev + angle_diff(b, b0 + prev)
        ys.append(prev)
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def drift_words(rate: float | None) -> str:
    if rate is None:
        return "drift okänd"
    if abs(rate) < STEADY_DEG_PER_MIN:
        return "bäringen står"
    side = "höger" if rate > 0 else "vänster"
    v = abs(rate)
    num = f"{v:.1f}".replace(".", ",") if v < 10 else f"{v:.0f}"
    return f"drar {side} {num}°/min"


def own_turns(points: Sequence[tuple[int, float]],
              min_deg: float = OWN_TURN_MIN_DEG) -> list[OwnTurn]:
    """Girar ur kursloggen: en gir börjar när kursen lämnat den förra med mer än några
    grader och slutar när den står still igen. Bara girar på minst `min_deg`."""
    out: list[OwnTurn] = []
    if len(points) < 2:
        return out
    steady = points[0][1]
    turning_from: float | None = None
    prev = points[0][1]
    prev_t = points[0][0]
    for t, c in points[1:]:
        if t <= prev_t:                 # samma tidpunkt två gånger: ingen ny loggning
            continue
        prev_t = t
        if turning_from is None:
            if abs(angle_diff(c, steady)) > OWN_TURN_START_DEG:
                turning_from = steady
        elif abs(angle_diff(c, prev)) < OWN_TURN_STEADY_DEG:
            if abs(angle_diff(c, turning_from)) >= min_deg:
                out.append(OwnTurn(t, turning_from, c))
            turning_from = None
            steady = c
        if turning_from is None and abs(angle_diff(c, steady)) <= OWN_TURN_START_DEG:
            steady = c
        prev = c
    return out


def designation_order(d: str) -> tuple[int, str]:
    """S-2 före S-10."""
    tail = d.rsplit("-", 1)[-1]
    return (int(tail), d) if tail.isdigit() else (10**6, d)


def held_by_kind(designations: list[str], track) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """De hållna kontakterna, hot först (ur kunskapens klassning), och slaget för var och en.
    `track(d)` ger kunskapens spår eller None."""
    order = {k: i for i, k in enumerate(KINDS)}
    pairs = []
    for d in designations:
        tr = track(d)
        pairs.append((d, track_kind(tr) if tr is not None else "contact"))
    pairs.sort(key=lambda p: (order[p[1]], designation_order(p[0])))
    return tuple(d for d, _ in pairs), tuple(k for _, k in pairs)
