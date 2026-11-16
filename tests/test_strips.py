"""Telegramremsor i loggboken: under radiomannens rad, ombrutna efter bredden."""
from rich.console import Console

from sim.reports import Report
from ui.strips import TelegramStrip, strip_lines
from ui.widgets import ReportLog


def _plain(renderable, width):
    c = Console(width=width, record=True, color_system=None)
    c.print(renderable)
    return c.export_text()


def test_strip_has_header_and_wraps_to_width():
    text = "SIGNALSJUNKBOMBER ANVÄNDS MOT OKÄNDA UBÅTAR. " * 4
    rows = strip_lines(3, "telegram", "04:30", text, 60)
    assert "РАДИОГРАММА № 3 · 04:30" in rows[0].plain and "från staben" in rows[0].plain
    assert len(rows) > 2 and all(len(r.plain) <= 60 for r in rows)
    narrow = strip_lines(3, "telegram", "04:30", text, 34)
    assert "från staben" not in narrow[0].plain and len(narrow[0].plain) <= 34
    wide = _plain(TelegramStrip(3, "telegram", "04:30", text), 100)
    assert max(len(line) for line in wide.splitlines()) <= 100
    assert "РАДИО МОСКВА" in strip_lines(1, "broadcast", "05:00", "Moskva talar.", 60)[0].plain


def test_log_writes_the_strip_under_the_radio_line():
    log = ReportLog()
    r = Report(0, "Radio (Belov)", "radio.message", {"telegram": 2, "text": "Gå till Nord-7.",
                                                     "telegram_kind": "telegram"},
               role="radio", text="Kapten, radio. Radiogram nummer 2 från huvudstaben.")
    log.add_report("04:30:12", r)
    assert isinstance(log.entries[-1], TelegramStrip)
    assert "Gå till Nord-7." in _plain(log.entries[-1], 80)
    assert "Radiogram nummer 2" in log.entries[-2].plain


def test_order_strip_keeps_the_order_lines():
    order = "STRÄNGT HEMLIGT\nFRÅN: MARINENS HUVUDSTAB\n\n1. INTA STÄLLNING.\n\nSLUT\n"
    rows = strip_lines("417/с", "order", "04:00", order, 70, "strängt hemligt")
    head = rows[0].plain
    assert "ШИФРОГРАММА · Вх. № 417/с · 04:00" in head and "ordern, strängt hemligt" in head
    body = [r.plain.strip() for r in rows[1:]]
    assert body[0] == "STRÄNGT HEMLIGT" and "1. INTA STÄLLNING." in body and body[-1] == "SLUT"
