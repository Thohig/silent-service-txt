"""Ett svep med många kontakter blir en rad och en tabell (2026-11-23).

Periskopet, bryggan och den aktiva sonarn ropade förut varje kontakt för sig: ett svep över en konvoj
gav sju rader på tio sekunder (och sju upplästa meningar). `SweepCalls` samlar utropen i ett svep: är
de färre än `BATCH_MIN` sägs de var för sig som förut; annars en rapport med det viktiga i texten
(hur många, närmast, jagarna) och alla i tabellen under. Bara texten läses upp (`data["spoken"]`).

Svepet är slut när inget nytt ropats på `QUIET_S` sekunder (periskopet sveper runt på några sekunder),
eller när stationen säger att det är klart (`flush(force=True)`, aktiv sonar och bryggans titt).
"""
from __future__ import annotations

from .. import phrases
from .. import russian as R
from ..fmt import count, fmt_course, kn, nm
from ..reports import Quality

BATCH_MIN = 4          # så många eller fler i samma svep: en rad och en tabell
QUIET_S = 2            # svepet är slut när inget nytt ropats så här länge

WHO = {"periscope": "Periskop", "bridge": "Bryggan", "active": "Aktiv sonar"}
WHO_RU = {"periscope": "Перископ", "bridge": "Мостик", "active": "Активный поиск"}
WHAT = {"periscope": ("fartyg", "fartyg"), "bridge": ("fartyg", "fartyg"), "active": ("eko", "ekon")}


def _count(n: int, forms: tuple[str, str]) -> str:
    return count(n, *forms)


def _summary(d: dict) -> str:
    who = WHO[d["who"]]
    near = d["nearest"]
    out = f"{who}: {_count(d['n'], WHAT[d['who']])}"
    out += " i sikte." if d["who"] != "active" else "."
    label = f", {near['label']}" if near.get("label") else ""
    out += f" Närmast {near['designation']}{label}, bäring {fmt_course(near['bearing'])}, " \
           f"cirka {nm(near['range'])} sjömil."
    if d.get("warships"):
        out += " Örlogsfartyg: " + ", ".join(d["warships"]) + "."
    return out


def _summary_ru(d: dict) -> str:
    near = d["nearest"]
    return (f"{WHO_RU[d['who']]}: {R.count(d['n'], ('цель', 'цели', 'целей'))}. Ближайшая — "
            f"{R.contact(near['designation'])}, пеленг {R.course(near['bearing'])}, "
            f"дистанция {R.dec(near['range'], R.MILE)}.")


SUMMARY_TYPES = {"periscope": "off.periscope.sweep", "bridge": "bridge.sweep", "active": "sonar.active.sweep"}
phrases.register({t: _summary for t in SUMMARY_TYPES.values()})
phrases.register_ru({t: _summary_ru for t in SUMMARY_TYPES.values()})

HEADER = ["Kontakt", "Vad", "Bäring", "Avstånd", "Kurs och fart"]


def _row(d: dict) -> list[str]:
    if d.get("again"):
        motion = "som förut"
    elif d.get("course") is not None:
        motion = f"{fmt_course(round(d['course'] / 5) * 5)}, {kn(d.get('speed', 0))} kn"
    elif "course" in d:
        motion = "ligger still"
    else:
        motion = ""
    return [d["designation"], d.get("label") or "", fmt_course(d["bearing"]), f"{nm(d['range'])} nm", motion]


def _warship(label: str | None) -> bool:
    return bool(label) and any(w in label for w in ("jagare", "eskort", "patrullbåt", "bevakningsfartyg",
                                                    "ubåt", "örlogs"))


class SweepCalls:
    """Utropen i ett svep för en station (`who`: periscope, bridge, active)."""

    def __init__(self, station, who: str):
        self.station = station
        self.who = who
        self._calls: list[tuple[str, dict, Quality | None, dict]] = []   # (typ, data, kvalitet, say-argument)
        self._last_t: int | None = None

    def add(self, type: str, data: dict, quality: Quality | None = None, **kw) -> None:
        """Ett utrop. data ska ha designation, bearing, range (och gärna label, course, speed)."""
        self._calls.append((type, data, quality, kw))
        self._last_t = self.station.now

    def flush(self, force: bool = False) -> None:
        """Säg det som samlats om svepet är slut (eller force)."""
        if not self._calls or (not force and self.station.now - self._last_t < QUIET_S):
            return
        calls, self._calls = self._calls, []
        if len(calls) < BATCH_MIN:
            for type, data, quality, kw in calls:
                self.station.say(type, data, quality=quality, **kw)
            return
        items = [{**d, "again": t.endswith(".again")} for t, d, _, _ in calls]
        nearest = min(items, key=lambda d: d["range"])
        warships = [d["designation"] for d in sorted(items, key=lambda d: d["range"]) if _warship(d.get("label"))]
        qualities = [q for _, _, q, _ in calls if q is not None]
        self.station.say(SUMMARY_TYPES[self.who],
                         {"who": self.who, "n": len(items), "nearest": nearest, "warships": warships,
                          "table": [_row(d) for d in sorted(items, key=lambda d: d["range"])],
                          "table_header": HEADER, "spoken": True},
                         kind="contact", quality=min(qualities) if qualities else None)
