"""Den hemliga ordern som chiffertelegram och slutrapporten som донесение (rapport till staben).

Samma stil som huvudmenyn (`menutext`): rött fält, stämpel efter datumet, ryska med svensk
översättning. Avsändaren läses ur orderns FRÅN-rad, så att nya scenarier får rätt stab
utan att något behöver registreras här.
"""
from __future__ import annotations

import re

from rich.text import Text

from .menutext import (DIM, HIGHLIGHT_FG, INK, RED, RED_DARK, STAMP_SPECIAL, STAMP_TRAINING,
                       stamp_for, stamp_text)

# FRÅN-radens stab ⇒ (ryska, svenska)
STAFFS = (
    ("HUVUDSTAB", ("ГЛАВНЫЙ ШТАБ ВМФ · МОСКВА", "marinens huvudstab, Moskva")),
    ("NORRA FLOTTAN", ("ШТАБ СЕВЕРНОГО ФЛОТА · СЕВЕРОМОРСК", "staben, Norra flottan, Severomorsk")),
)
DEFAULT_STAFF = ("ГЛАВНЫЙ ШТАБ ВМФ · МОСКВА", "marinens huvudstab, Moskva")


def staff_of(order: str) -> tuple[str, str]:
    """Staben som sänt ordern, ur raden "FRÅN: …"."""
    m = re.search(r"^FRÅN:\s*(.+)$", order, re.MULTILINE)
    line = m.group(1).upper() if m else ""
    for key, staff in STAFFS:
        if key in line:
            return staff
    return DEFAULT_STAFF


def telegram_number(seed: int | None) -> str:
    """Mottagningsnumret, samma för samma frö: "Вх. № 417/с"."""
    return f"{(seed or 0) % 900 + 100}/с"


def _band(left: str, right: str, width: int, style: str) -> Text:
    t = Text()
    t.append(left + " " * max(2, width - len(left) - len(right)) + right, style=style)
    return t


def order_header(key: str, title: str, order: str, seed: int | None, width: int = 60) -> Text:
    """Telegrammets huvud: ШИФРОГРАММА, numret, stämpeln och avsändaren."""
    ru_staff, sv_staff = staff_of(order)
    number = telegram_number(seed)
    t = _band(" ШИФРОГРАММА", f"Вх. № {number} ", width, f"bold {INK} on {RED_DARK}")
    t.append("\n")
    t.append_text(_band(" chiffertelegram", f"inkommande nr {number} ", width,
                        f"{DIM} on {RED_DARK}"))
    t.append("\n\n")
    t.append_text(stamp_text(stamp_for(key, title)))
    t.append("\n\n")
    t.append("ОТ: ", style=DIM)
    t.append(ru_staff, style=f"bold {INK}")
    t.append(f"  ({sv_staff})", style=f"italic {DIM}")
    return t


def order_signature(order: str) -> Text:
    """Under ordern: dechiffrerat och kvitterat."""
    ru_staff, _ = staff_of(order)
    t = Text()
    t.append("РАСШИФРОВАЛ: ", style=DIM)
    t.append("старшина Белов", style=INK)
    t.append("  (dechiffrerat av radiomannen, starsjina Belov)\n", style=f"italic {DIM}")
    t.append("ПОДПИСЬ: ", style=DIM)
    t.append(ru_staff.split(" · ")[0], style=f"bold {INK}")
    t.append("  (underskrift)", style=f"italic {DIM}")
    return t


def report_header(key: str, title: str, order: str, width: int = 60) -> list[Text]:
    """Slutrapportens huvud: ДОНЕСЕНИЕ till staben som gav ordern, med uppdragets stämpel."""
    ru_staff, sv_staff = staff_of(order)
    head = _band(" ДОНЕСЕНИЕ", "К-114 ", width, f"bold {HIGHLIGHT_FG} on {RED}")
    to = Text("  КОМУ: ", style=DIM)
    to.append(ru_staff, style=f"bold {INK}")
    sv = Text(f"  Rapport till {sv_staff}", style=f"italic {DIM}")
    st = stamp_for(key, title)
    stamp = Text("  ")
    stamp.append(f" {st.ru} ", style=st.style)
    stamp.append(f"  {st.sv}", style=f"italic {DIM}")
    return [head, to, sv, stamp]


def crew_announcement(key: str, title: str) -> tuple[str, str]:
    """Vakthavandes utrop i högtalaren när kaptenen tar befälet: (ryska, svenska).
    Övning, operation eller krig efter uppdragets stämpel."""
    stamp = stamp_for(key, title)
    if stamp is STAMP_TRAINING:
        return ("Внимание экипажу. Выходим на учения. Командир на центральном посту. "
                "По местам стоять.",
                "Till besättningen: vi går ut på övning. Befälhavaren är i centralen. "
                "Intag stationerna.")
    if stamp is STAMP_SPECIAL:
        return ("Внимание экипажу. Получен боевой приказ. Командир на центральном посту. "
                "Боевая тревога. По местам стоять.",
                "Till besättningen: stridsorder har mottagits. Befälhavaren är i centralen. "
                "Stridslarm. Intag stationerna.")
    return ("Внимание экипажу. Получен приказ командования. Командир на центральном посту. "
            "По местам стоять.",
            "Till besättningen: order från staben har mottagits. Befälhavaren är i centralen. "
            "Intag stationerna.")
