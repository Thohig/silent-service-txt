"""Formatering av tal och tider för besättningens tal."""
from __future__ import annotations

from .geo import fmt_course  # noqa: F401  (återexport)


def nm(v: float) -> str:
    """Svensk decimal med en decimal: 6,2"""
    return f"{v:.1f}".replace(".", ",")


def kn(v: float) -> str:
    """Fart: heltal om möjligt, annars en decimal."""
    return f"{v:.0f}" if abs(v - round(v)) < 0.05 else nm(v)


def kn_dir(v: float, astern: bool) -> str:
    """Fart med riktning: "back 3" när båten går (eller ska gå) akterut, annars "3"."""
    return f"back {kn(v)}" if astern and v > 0 else kn(v)


_NUMBERS = ["noll", "", "två", "tre", "fyra", "fem", "sex", "sju", "åtta", "nio", "tio", "elva", "tolv"]


def count(n: int, one: str, many: str, neuter: bool = True) -> str:
    """Antal med ord (till tolv) och rätt form: "ett civilt fartyg", "en jagare", "tre jagare"."""
    if n == 1:
        return f"{'ett' if neuter else 'en'} {one}"
    word = _NUMBERS[n] if 0 <= n < len(_NUMBERS) else str(n)
    return f"{word} {many}"


def minutes(n: int) -> str:
    """"en minut", "5 minuter" (talet med siffror, som i besättningens övriga tal)."""
    return "en minut" if n == 1 else f"{n} minuter"


def duration(minutes: int) -> str:
    """Översiktens kvarvarande tid: "29 min", "3 h 05 min" (inga noll timmar)."""
    h, m = divmod(max(0, int(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def clock(seconds: int) -> str:
    s = int(seconds) % 86400
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
