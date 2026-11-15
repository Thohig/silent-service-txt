"""Radio Moskva ombord: vad radiomannen hör på kortvåg, efter datumet i ordern.

Bara stämning, aldrig information om läget: sändningarna följer kalendern i oktober 1962.
Den 28 oktober följer spelets historia (kriget har börjat) och Moskva sänder inget.
Ryskan är det rösten läser; svenskan står i loggen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Broadcast:
    from_day: int           # gäller från denna dag i oktober (till nästa)
    ru: str                 # tom: bara bärvåg, ingen sändning
    sv: str


BROADCASTS = [
    Broadcast(1, "Говорит Москва. Труженики села завершают уборку урожая.",
              "Här är Moskva. Lantbrukarna avslutar skörden."),
    Broadcast(1, "Говорит Москва. Передаём концерт по заявкам моряков Северного флота.",
              "Här är Moskva. Önskekonsert för sjömännen i Norra flottan."),
    Broadcast(22, "Говорит Москва. Правительство Соединённых Штатов объявило морскую блокаду Кубы.",
              "Här är Moskva. USA:s regering har utlyst sjöblockad mot Kuba."),
    Broadcast(22, "Говорит Москва. Заявление ТАСС: блокада — это акт пиратства.",
              "Här är Moskva. TASS förklarar: blockaden är sjöröveri."),
    Broadcast(24, "Говорит Москва. Американские корабли останавливают суда в открытом море.",
              "Här är Moskva. Amerikanska örlogsfartyg stoppar fartyg på öppet hav."),
    Broadcast(24, "Говорит Москва. Советский народ требует: руки прочь от Кубы!",
              "Här är Moskva. Sovjetfolket kräver: händerna bort från Kuba!"),
    Broadcast(27, "Говорит Москва. Над Кубой сбит американский самолёт-разведчик.",
              "Här är Moskva. Ett amerikanskt spaningsplan har skjutits ned över Kuba."),
    Broadcast(27, "Внимание. Говорит Москва. Слушайте важное правительственное сообщение.",
              "Uppmärksamhet. Här är Moskva. Lyssna på ett viktigt meddelande från regeringen …"),
    Broadcast(28, "", "Bara bärvåg. Moskva sänder ingenting."),
]


def order_day(order: str) -> int | None:
    """Dagen i oktober ur orderns DATUM-rad ("DATUM: 24 OKTOBER 1962" ⇒ 24)."""
    m = re.search(r"DATUM:\s*(\d+)\s+OKTOBER", order.upper())
    return int(m.group(1)) if m else None


def broadcasts_for(day: int | None) -> list[Broadcast]:
    """Sändningarna den dagen: de senaste som börjat gälla."""
    day = day or 1
    start = max(b.from_day for b in BROADCASTS if b.from_day <= day)
    return [b for b in BROADCASTS if b.from_day == start]
