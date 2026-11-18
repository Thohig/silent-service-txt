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
    Word("Torpeda", "Торпеда", "torped (i vattnet)"),
    Word("Komandovanie prinjal", "Командование принял", "befälet övertaget (starpom tar vakten)"),
    Word("Komandovanie sdal", "Командование сдал", "befälet överlämnat (tillbaka till kaptenen)"),
    Word("Komandir, v tsentralnyj", "Командир, в центральный", "kaptenen till centralen"),
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


# --------------------------------------------------------------------------- ryskt tal
# Besättningens repliker kan läsas upp på ryska (ui/audio.py, "tal ryska"). Varje station
# registrerar ryska talfraser med phrases.register_ru(); de byggs ur samma data som den
# svenska texten. Det ryska syns aldrig i loggen.

ROLE_RU = {"sonar": "акустик", "navigator": "штурман", "plot": "планшет", "engineer": "пульт",
           "torpedo": "минёр", "officer": "вахтенный офицер", "radio": "радист",
           "starpom": "старпом", "trim": "трюмный"}
CAPTAIN = "Товарищ командир"
DIGITS = ("ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
TENTHS = ("", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
MILE = ("миля", "мили", "миль")
KNOT = ("узел", "узла", "узлов")
METER = ("метр", "метра", "метров")
TON = ("тонна", "тонны", "тонн")
DEGREE = ("градус", "градуса", "градусов")
MINUTE = ("минута", "минуты", "минут")
SECOND = ("секунда", "секунды", "секунд")
QUALITY_RU = {0: "плохое", 1: "неуверенное", 2: "хорошее", 3: "надёжное"}
CLASS_RU = {
    "okänd kontakt": "неизвестный контакт",
    "ytfartyg": "надводная цель",
    "ytfartyg, tvåskruv, trolig jagare": "надводная цель, двухвальная, вероятно эсминец",
    "jagare, ångturbiner, två axlar": "эсминец, паровые турбины, два вала",
    "ytfartyg, enskruv, troligt handelsfartyg": "надводная цель, одновальная, вероятно транспорт",
    "handelsfartyg, diesel, en axel": "транспорт, дизель, один вал",
    "ytfartyg, tvåskruv, snabbgående, trolig patrullbåt":
        "надводная цель, двухвальная, быстроходная, вероятно сторожевой катер",
    "patrullbåt, diesel, två axlar": "сторожевой катер, дизели, два вала",
    "ytfartyg, tvåskruv, troligt bevakningsfartyg":
        "надводная цель, двухвальная, вероятно сторожевой корабль",
    "bevakningsfartyg, ångturbiner, två axlar": "сторожевой корабль, паровые турбины, два вала",
    "bevakningsfartyg, sovjetiskt": "наш сторожевой корабль",
    "ytfartyg, stort, två axlar, långsamt varvtal":
        "надводная цель, крупная, двухвальная, малые обороты",
    "stort fartyg, ångturbiner, två axlar, trolig trupptransport":
        "крупное судно, паровые турбины, два вала, вероятно войсковой транспорт",
    "ytfartyg, stort, enskruv, tungt lastat": "надводная цель, крупная, одновальная, гружёная",
    "tankfartyg, ångturbin, en axel": "танкер, паровая турбина, один вал",
    "svagt maskinbuller, stillaliggande": "слабый шум механизмов, без хода",
    "hjälpmaskiner, troligen fartyg till ankars": "вспомогательные механизмы, вероятно судно на якоре",
    "fartyg till ankars, hjälpmaskiner": "судно на якоре, вспомогательные механизмы",
    "möjlig undervattenskontakt": "возможно, подводная цель",
    "trolig ubåt": "вероятно подводная лодка",
    "ubåt, atomdriven": "атомная подводная лодка",
    "maskinbuller, stillaliggande": "шум механизмов, без хода",
    "dieselgenerator, trolig drivstation": "дизель-генератор, вероятно дрейфующая станция",
    "dieselgenerator, drivstation på isen": "дизель-генератор, дрейфующая станция на льду",
    "bredbandigt brus, ingen tydlig maskin": "широкополосный шум, механизмов не слышно",
    "trolig isskruvning": "вероятно торошение льда",
    "isljud, ingen maskin": "шум льда, механизмов нет",
}


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """Rätt rysk form efter ett heltal: 1 миля, 2 мили, 5 миль."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def count(n: float, forms: tuple[str, str, str]) -> str:
    n = int(round(n))
    return f"{n} {plural(n, forms)}"


def dec(x: float, forms: tuple[str, str, str]) -> str:
    """Tal med en decimal i ord som rösten läser rätt: '3 и две десятых мили'."""
    tenths = int(round(abs(x) * 10))
    whole, t = divmod(tenths, 10)
    if t == 0:
        return count(whole, forms)
    frac = f"{TENTHS[t]} {'десятая' if t == 1 else 'десятых'}"
    return f"{frac} {forms[1]}" if whole == 0 else f"{whole} и {frac} {forms[1]}"


def course(c: float) -> str:
    """Kurs och bäring siffra för siffra, som till sjöss: 'ноль девять ноль'."""
    return " ".join(DIGITS[int(ch)] for ch in f"{int(round(c)) % 360:03d}")


def mmss(s: float) -> str:
    s = int(round(s))
    m, s = divmod(s, 60)
    return (f"{count(m, MINUTE)} {count(s, SECOND)}" if m and s else
            count(m, MINUTE) if m else count(s, SECOND))


def contact(designation: str, genitive: bool = False) -> str:
    """S-1 -> 'цель 1' (genitiv 'цели 1'). Beteckningen är kunskap, inte sanning."""
    m = re.fullmatch(r"S-(\d+)", designation or "")
    word = "цели" if genitive else "цель"
    return f"{word} {m[1]}" if m else word


def classification(s: str) -> str:
    return CLASS_RU.get(s, "классификация уточняется")


def weapon(name: str) -> str:
    """Torpedtyp för rösten: SET-53 -> 'СЭТ 53', 53-61 -> '53 61' (inte 'minus')."""
    if name == "övning":
        return "практическая"
    return name.replace("SET", "СЭТ").replace("-", " ")


def fallback(role: str, kind: str) -> str:
    """Tal för en rapport utan rysk fras: vem som rapporterar. Texten står i loggen."""
    if kind == "ack":
        return "Есть."
    who = ROLE_RU.get(role)
    if who is None:
        return ""
    if kind == "suggest":
        return f"{CAPTAIN}, {who}. Есть предложение."
    return f"{CAPTAIN}, {who}."
