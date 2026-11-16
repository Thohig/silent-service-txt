"""Orderregister: varje station registrerar sina egna order.

En order tolkas i två steg:
1. Registret hittar den CommandSpec vars mönster matchar texten och bygger
   ett Order-objekt (ren syntax, ingen kunskap om ubåtens tillstånd).
2. Ordern publiceras på händelsebussen och den station som äger den
   hanterar den, inklusive att säga ifrån om ordern inte går att utföra.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, ClassVar, Iterable

TIME_SCALES = (1, 2, 5, 10, 30, 60)
REST_SCALE = 10             # snabbare än så bara när starpom har befälet

NUM = r"(\d+(?:[.,]\d+)?)"
DESIG = r"(s\s*-?\s*\d+)"


@dataclass(frozen=True)
class Order:
    """Basklass för alla order.

    STANDING: ordern sätter ett bestående läge (kurs, fart, djup, framdrivning,
    reaktor). Ett förslag om exakt samma order som redan gäller är då meningslöst.
    Engångsåtgärder (fix, skenmål, sänd …) kan däremot behöva upprepas.

    INSTRUMENT: kaptenens hand på ett instrument (vrida periskopet), inte en order
    till besättningen; räknas inte i loggbokens order.
    """
    STANDING: ClassVar[bool] = False
    INSTRUMENT: ClassVar[bool] = False


@dataclass(frozen=True)
class Unknown(Order):
    text: str
    reason: str = ""


@dataclass(frozen=True)
class Help(Order):
    pass


@dataclass(frozen=True)
class SetTimeScale(Order):
    scale: int


@dataclass(frozen=True)
class Quit(Order):
    """Kaptenen avslutar spelet. Utan bekräftelse frågar vakthavande först."""
    confirmed: bool = False


@dataclass(frozen=True)
class AcceptSuggestion(Order):
    pass


@dataclass(frozen=True)
class DeclineSuggestion(Order):
    pass


@dataclass(frozen=True)
class AskSuggestion(Order):
    """Kaptenen ber om förslag.

    role: besättningsroll (Role-värde) om kaptenen frågar en viss station.
    other: "annat förslag", dvs. något annat än det som väntar på svar.
    Utan role och other upprepas ett väntande förslag; annars svarar
    vakthavande med stationernas bästa förslag just nu.
    """
    role: str | None = None
    other: bool = False


# station i "förslag sonar" -> Role-värde (sim.crew.Role)
STATION_WORDS = {
    "sonar": "sonar", "sonaren": "sonar",
    "maskin": "engineer", "maskinen": "engineer",
    "plott": "plot", "plot": "plot", "plottet": "plot", "plotten": "plot",
    "navigatör": "navigator", "navigatören": "navigator", "navigator": "navigator",
    "navigatoren": "navigator", "nav": "navigator",
    "torped": "torpedo", "torpedrum": "torpedo", "torpedrummet": "torpedo",
    "radio": "radio", "radion": "radio",
    "vakthavande": "officer", "officer": "officer", "officeren": "officer",
    "starpom": "starpom", "starpomen": "starpom",
}


def _ask_station(m: re.Match) -> Order:
    role = STATION_WORDS.get(m[1])
    if role is None:
        return Unknown("", f"vilken station? Sonar, maskin, plott, navigatör, torped, "
                           f"radio, vakthavande eller starpom")
    return AskSuggestion(role)


def num(s: str) -> float:
    return float(s.replace(",", "."))


def desig(s: str | None) -> str | None:
    if not s:
        return None
    return f"S-{int(re.sub(r'[^0-9]', '', s))}"


# Flera order på en rad: "kurs 090, fart 5; djup 100" eller "kurs 090 och fart 5".
# Komma följt av en siffra är decimalkomma ("fart 5,5") och delar inte.
_ORDER_SEP = re.compile(r"\s*;\s*|\s*,(?!\d)\s*|\s+och\s+", re.IGNORECASE)


def split_orders(text: str) -> list[str]:
    return [p for p in (part.strip() for part in _ORDER_SEP.split(text)) if p]


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


@dataclass(frozen=True)
class CommandSpec:
    pattern: str
    build: Callable[[re.Match], Order]
    help: str = ""
    regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "regex", re.compile(self.pattern))


class CommandRegistry:
    def __init__(self, specs: Iterable[CommandSpec] = ()):
        self._specs: list[CommandSpec] = []
        self.register(*specs)

    def register(self, *specs: CommandSpec) -> None:
        self._specs.extend(specs)

    def parse(self, text: str) -> Order:
        t = normalize(text)
        if not t:
            return Unknown(text, "tom order")
        for spec in self._specs:
            if m := spec.regex.fullmatch(t):
                order = spec.build(m)
                if isinstance(order, Unknown) and not order.text:
                    order = Unknown(text, order.reason)
                return order
        return Unknown(text)

    def help_text(self) -> str:
        return ("Order: " + " · ".join(s.help for s in self._specs if s.help)
                + ". Flera order på en rad: kurs 090, fart 5; djup 100 (eller \"och\").")


def _time_scale(m: re.Match) -> Order:
    n = int(m[1])
    if n not in TIME_SCALES:
        return Unknown("", "tid kan vara 1, 2, 5 eller 10 (30 och 60 när starpom har befälet)")
    return SetTimeScale(n)


TIME_COMMAND = CommandSpec(r"(?:tid|tidskomprimering)\s+(\d+)\s*x?", _time_scale, "tid 1|2|5|10|30|60")
QUIT_COMMAND = CommandSpec(
    r"(?:avsluta(?: spelet| patrullen| uppdraget| övningen| ovningen)?|"
    r"avbryt (?:patrullen|uppdraget|uppdrag|övningen|ovningen)|sluta spela)"
    r"(?P<confirmed> bekräftat| bekraftat)?",
    lambda m: Quit(confirmed=bool(m.group("confirmed"))), "avbryt uppdraget")
HELP_COMMAND = CommandSpec(r"hjälp|hjalp|\?|order", lambda m: Help(), "hjälp")

SUGGESTION_COMMANDS = [
    CommandSpec(r"ja|verkställ|verkstall|gör så|gor sa|utför|utfor|aye|jest|есть",
                lambda m: AcceptSuggestion(), "ja"),
    CommandSpec(r"nej|avslå|avsla|avvakta", lambda m: DeclineSuggestion(), "nej"),
    CommandSpec(r"(?:förslag|forslag|några förslag|nagra forslag|vad föreslår ni|"
                r"vad foreslar ni)\s*\??", lambda m: AskSuggestion(), "förslag"),
    CommandSpec(r"(?:annat|nytt|nästa|nasta|fler)\s+(?:förslag|forslag)\s*\??",
                lambda m: AskSuggestion(other=True), "annat förslag"),
    CommandSpec(r"(?:förslag|forslag)\s+(?:från\s+|fran\s+)?(\S+?)\s*\??",
                _ask_station, "förslag sonar"),
]
