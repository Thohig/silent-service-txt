"""Formatering av tal och tider för besättningens tal."""
from __future__ import annotations

from .geo import fmt_course  # noqa: F401  (återexport)


def nm(v: float) -> str:
    """Svensk decimal med en decimal: 6,2"""
    return f"{v:.1f}".replace(".", ",")


def kn(v: float) -> str:
    """Fart: heltal om möjligt, annars en decimal."""
    return f"{v:.0f}" if abs(v - round(v)) < 0.05 else nm(v)


def clock(seconds: int) -> str:
    s = int(seconds) % 86400
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
