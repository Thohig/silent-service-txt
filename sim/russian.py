"""Ryska inslag: fasta fraser som ger besättningen sovjetisk prägel.

Regel: ryskan är krydda, aldrig information. Varje rysk fras är en fast
formel vars betydelse framgår av den svenska texten bredvid (eller av
`hjälp`). Siffror, bäringar och bedömningar står alltid på svenska.

Fraserna skrivs med svensk translitterering i texten. Talet (ui/audio.py)
hittar dem med `segments()` och läser den kyrilliska formen med en rysk röst.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    latin: str          # svensk translitterering, som spelaren ser
    cyrillic: str       # för den ryska rösten
    meaning: str        # svensk betydelse, för ordlistan i hjälpen


WORDS: dict[str, Word] = {w.latin: w for w in (
    Word("Jest", "Есть", "ska ske, uppfattat (kvittens på order)"),
    Word("Tovarisjtj komandir", "Товарищ командир", "kamrat befälhavare (tilltal till kaptenen)"),
    Word("Boevaja trevoga", "Боевая тревога", "stridslarm"),
    Word("Avarijnaja trevoga", "Аварийная тревога", "haverilarm"),
    Word("Torpeda vysjla", "Торпеда вышла", "torpeden har lämnat tuben"),
)}

_PATTERN = re.compile(r"\b(" + "|".join(re.escape(k) for k in
                                       sorted(WORDS, key=len, reverse=True)) + r")\b([!?.]?)")


def ru(latin: str) -> str:
    """Rysk fras i text. Bara ord ur ordlistan, så att talet hittar dem."""
    return WORDS[latin].latin


def segments(text: str) -> list[tuple[str, str]]:
    """Dela texten i ("sv", text) och ("ru", kyrilliska) i tur och ordning."""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in _PATTERN.finditer(text):
        before = text[pos:m.start()].strip(" ,")
        if before.strip(" .!?"):
            out.append(("sv", before))
        out.append(("ru", WORDS[m[1]].cyrillic + m[2]))   # utropet hör till tonfallet
        pos = m.end()
    rest = text[pos:].strip(" ,")
    if rest.strip(" .!?"):
        out.append(("sv", rest))
    return out


def glossary() -> str:
    return "Ryska: " + " · ".join(f"{w.latin} = {w.meaning}" for w in WORDS.values()) + "."
