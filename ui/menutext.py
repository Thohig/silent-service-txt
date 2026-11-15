"""Huvudmenyns texter: sidhuvudet som en hemlig handling och stämplarna på uppdragen.

Ryskan står alltid med den svenska betydelsen bredvid. Inget här läser spelet; det är
bara stämning kring kalendern i oktober 1962.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rich.text import Text

# --- färger: en stämplad mapp, ockra papper och flaggrött ---------------------------
BG = "#120b09"
INK = "#d8c8a0"            # ockra text
DIM = "#8a7a5c"
RED = "#b8281c"
RED_DARK = "#5a1410"
HIGHLIGHT_BG = "#4a1a12"
HIGHLIGHT_FG = "#f4e6c4"
RULE = "#6a2a20"

STAR = "★"


def header(width: int = 100, level: int = 0, lit: bool = True) -> Text:
    """Två rader: sekretessen och flottan på ett rött fält, sedan båten och beredskapen."""
    left = " СОВЕРШЕННО СЕКРЕТНО · ЭКЗ. № 2"
    right = f"{STAR} ВМФ СССР · СЕВЕРНЫЙ ФЛОТ "
    gap = max(2, width - len(left) - len(right))
    t = Text()
    t.append(left + " " * gap + right, style=f"bold {INK} on {RED_DARK}")
    t.append("\n")
    sv_left = " Strängt hemligt, exemplar nr 2"
    note = "Sovjetunionens örlogsflotta, Norra flottan "
    t.append(sv_left + " " * max(2, width - len(sv_left) - len(note)) + note,
             style=f"{DIM} on {RED_DARK}")
    t.append("\n\n")
    boat = Text()
    boat.append(" К-114", style=f"bold {HIGHLIGHT_FG}")
    boat.append("   Projekt 627A · 4:e eskadern · Poljarnyj", style=DIM)
    ready = readiness_text(level, lit)
    t.append_text(boat)
    t.append(" " * max(2, width - len(boat.plain) - len(ready.plain)))
    t.append_text(ready)
    return t


# --- stämplar ---------------------------------------------------------------------
@dataclass(frozen=True)
class Stamp:
    ru: str
    sv: str
    style: str


STAMP_TRAINING = Stamp("ДЛЯ СЛУЖЕБНОГО ПОЛЬЗОВАНИЯ", "för tjänstebruk", f"{DIM}")
STAMP_SECRET = Stamp("СЕКРЕТНО", "hemligt", f"bold {RED}")
STAMP_TOP_SECRET = Stamp("СОВЕРШЕННО СЕКРЕТНО", "strängt hemligt", f"bold #e03a26")
STAMP_SPECIAL = Stamp("СОВ. СЕКРЕТНО · ОСОБОЙ ВАЖНОСТИ", "strängt hemligt, av särskild vikt",
                      f"bold {HIGHLIGHT_FG} on {RED}")


def mission_day(title: str) -> int | None:
    """Dagen i oktober ur titeln ("Jagade, natten till 27 oktober 1962" ⇒ 27)."""
    m = re.search(r"(\d+) oktober", title)
    return int(m.group(1)) if m else None


def stamp_for(key: str, title: str) -> Stamp:
    """Ju närmare den 28 oktober, desto hemligare. Övningen är bara för tjänstebruk."""
    if key.split("-")[0] == "ovning":
        return STAMP_TRAINING
    day = mission_day(title)
    if day is None or day < 22:
        return STAMP_SECRET
    if day < 27:
        return STAMP_TOP_SECRET
    return STAMP_SPECIAL


def stamp_text(stamp: Stamp) -> Text:
    t = Text()
    t.append(f" {stamp.ru} ", style=stamp.style)
    t.append(f"\n{stamp.sv}", style=f"italic {DIM}")
    return t


# --- beredskapen ------------------------------------------------------------------
@dataclass(frozen=True)
class Readiness:
    ru: str
    sv: str
    blink: bool = False


READINESS = [
    Readiness("ПОСТОЯННАЯ", "ständig"),
    Readiness("ПОВЫШЕННАЯ", "höjd"),
    Readiness("ВОЕННАЯ ОПАСНОСТЬ", "krigsfara", blink=True),
    Readiness("ПОЛНАЯ", "full", blink=True),
]


def readiness_text(level: int, lit: bool = True) -> Text:
    """"БОЕВАЯ ГОТОВНОСТЬ · ПОВЫШЕННАЯ" och översättningen. lit: blinkningens läge."""
    r = READINESS[level]
    t = Text()
    t.append("БОЕВАЯ ГОТОВНОСТЬ · ", style=DIM)
    hot = (f"bold {HIGHLIGHT_FG} on {RED}" if level >= 2 else f"bold {RED}" if level == 1
           else f"bold {INK}")
    t.append(f" {r.ru} ", style=hot if (lit or not r.blink) else f"bold {RED_DARK}")
    t.append(f"  stridsberedskap: {r.sv} ", style=f"italic {DIM}")
    return t


# --- fjärrskrivaren -----------------------------------------------------------------
@dataclass(frozen=True)
class Dispatch:
    stamp: str          # "23.10 06:40"
    level: int          # beredskapen när meddelandet kommer (index i READINESS)
    text: str


# Från flottans fjärrskrivare, hösten 1962. Kalendern följer krisen; den 28 oktober följer
# spelets historia: kriget har börjat.
DISPATCHES = [
    Dispatch("01.10 04:00", 0, "69:E UBÅTSBRIGADEN HAR LÄMNAT SAJDA-GUBAN. KURS VÄST. "
             "TYSTNADSPLIKT GÄLLER ALL PERSONAL."),
    Dispatch("08.10 09:30", 0, "K-114 KLAR EFTER VARVSTIDEN. ÖVNINGAR I KOLAFJORDEN ENLIGT PLAN."),
    Dispatch("14.10 18:15", 0, "AMERIKANSKT SPANINGSPLAN U-2 ÖVER VÄSTRA KUBA. HÖG HÖJD, "
             "EJ BEKÄMPAT."),
    Dispatch("20.10 22:40", 0, "ÖKAD AMERIKANSK FLYG- OCH FARTYGSRÖRELSE I KARIBISKA HAVET. "
             "LANDSTIGNINGSFÖRBAND I FLORIDA."),
    Dispatch("22.10 23:00", 0, "WASHINGTON: PRESIDENTEN HAR TALAT I RADIO. KARANTÄN KRING KUBA. "
             "FARTYG SKA STOPPAS OCH VISITERAS."),
    Dispatch("23.10 06:40", 1, "FÖRSVARSMINISTERN: VÄPNADE STYRKOR I HÖJD STRIDSBEREDSKAP. "
             "PERMISSIONER INDRAGNA. AVLÖSNINGAR INSTÄLLDA."),
    Dispatch("24.10 17:00", 1, "KARANTÄNEN I KRAFT. AMERIKANSKA JAGARE PÅ LINJEN 500 NM FRÅN KUBA. "
             "VÅRA TRANSPORTER HAR STOPPAT ELLER VÄNT."),
    Dispatch("25.10 21:10", 1, "FN:S SÄKERHETSRÅD SAMMANTRÄDER. AMERIKANERNA VISAR BILDER AV "
             "RAKETBASERNA."),
    Dispatch("26.10 03:20", 2, "JAGARE OCH FLYG JAGAR UBÅTAR I SARGASSOHAVET. SJUNKBOMBER "
             "FÄLLS SOM SIGNAL ATT GÅ TILL YTAN."),
    Dispatch("27.10 12:05", 2, "LUFTVÄRNET PÅ KUBA HAR SKJUTIT NED ETT AMERIKANSKT SPANINGSPLAN. "
             "FLYGAREN OMKOMMEN."),
    Dispatch("27.10 21:50", 2, "UBÅT I SARGASSOHAVET TVINGAD TILL YTAN. INGEN FÖRBINDELSE MED "
             "FLOTTANS STAB."),
    Dispatch("28.10 02:30", 2, "STRATEGISKT FLYG I LUFTEN DYGNET RUNT. ALLA FARTYG: VAR BEREDDA "
             "PÅ ORDER OM VAPENBRUK."),
    Dispatch("28.10 05:12", 3, "KRIG. FULL STRIDSBEREDSKAP. OPERATIONSPLAN 2 TRÄDER I KRAFT. "
             "BEKRÄFTA MOTTAGANDET."),
]

TICKER_CPS = 24.0           # tecken i sekunden, som en fjärrskrivare
TICKER_HOLD_S = 6.0         # meddelandet står kvar så länge
TICKER_GAP_S = 1.2          # tom remsa mellan meddelandena
TICKER_REST_S = 8.0         # efter sista meddelandet, innan kalendern börjar om


def dispatch_duration(i: int) -> float:
    d = len(DISPATCHES[i].text) / TICKER_CPS + TICKER_HOLD_S + TICKER_GAP_S
    return d + (TICKER_REST_S if i == len(DISPATCHES) - 1 else 0.0)


TICKER_CYCLE_S = sum(dispatch_duration(i) for i in range(len(DISPATCHES)))


@dataclass(frozen=True)
class TickerState:
    index: int
    chars: int              # så många tecken av texten är utskrivna
    typing: bool            # skrivaren går just nu (ljudet)
    blank: bool             # mellanrummet mellan meddelandena

    @property
    def dispatch(self) -> Dispatch:
        return DISPATCHES[self.index]

    @property
    def level(self) -> int:
        return self.dispatch.level


def ticker_at(t: float) -> TickerState:
    """Fjärrskrivaren t sekunder efter att menyn visades. Upprepas."""
    t = t % TICKER_CYCLE_S
    for i in range(len(DISPATCHES)):
        d = dispatch_duration(i)
        if t < d:
            n = len(DISPATCHES[i].text)
            chars = min(n, int(t * TICKER_CPS))
            shown = n / TICKER_CPS + TICKER_HOLD_S
            return TickerState(i, chars, chars < n, t >= shown)
        t -= d
    return TickerState(len(DISPATCHES) - 1, 0, False, True)   # pragma: no cover


def ticker_text(state: TickerState, width: int, cursor: bool = True) -> Text:
    """En rad remsa: avsändaren, datum och tid, sedan texten. Långa meddelanden rullar."""
    t = Text(no_wrap=True, overflow="crop")
    t.append(" ТЕЛЕТАЙП ", style=f"bold {HIGHLIGHT_FG} on {RED_DARK}")
    if state.blank:
        return t
    d = state.dispatch
    t.append(f" СЕВФЛОТ {d.stamp} ", style=f"bold {RED}" if d.level >= 2 else DIM)
    room = max(10, width - len(t.plain) - 2)
    body = d.text[: state.chars]
    if len(body) > room:                              # rulla: det senaste syns
        body = "…" + body[-(room - 1):]
    t.append(body, style=f"bold {INK}" if d.level >= 3 else INK)
    if state.typing and cursor:
        t.append("█", style=INK)
    return t
