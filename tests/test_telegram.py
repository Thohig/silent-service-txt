"""Den hemliga ordern som chiffertelegram och slutrapporten som донесение."""
import asyncio
import random

import pytest

from sim.scenario import SCENARIOS, build_scenario
from ui.telegram import (DEFAULT_STAFF, order_header, order_signature, report_header, staff_of,
                         telegram_number)


def test_every_scenario_order_names_a_known_staff():
    for key in SCENARIOS:
        order = build_scenario(key, random.Random(1)).secret_order
        ru, sv = staff_of(order)
        assert ru and sv
    training = build_scenario("ovning", random.Random(1)).secret_order
    assert staff_of(training)[0].startswith("ШТАБ СЕВЕРНОГО ФЛОТА")
    assert staff_of("ingen avsändare") == DEFAULT_STAFF


def test_header_has_cipher_title_number_stamp_and_translations():
    order = SCENARIOS["jagad"].build(random.Random(1)).secret_order
    plain = order_header("jagad", SCENARIOS["jagad"].title, order, seed=1234, width=60).plain
    assert "ШИФРОГРАММА" in plain and "chiffertelegram" in plain
    assert f"Вх. № {telegram_number(1234)}" in plain and "inkommande nr" in plain
    assert "ОСОБОЙ ВАЖНОСТИ" in plain and "strängt hemligt" in plain
    assert "ГЛАВНЫЙ ШТАБ ВМФ" in plain and "marinens huvudstab" in plain
    assert all(len(line) <= 60 for line in plain.split("\n")[:2])
    assert telegram_number(1234) == telegram_number(1234) != telegram_number(1235)
    sig = order_signature(order).plain
    assert "РАСШИФРОВАЛ" in sig and "underskrift" in sig


def test_report_header_goes_to_the_staff_that_gave_the_order():
    order = SCENARIOS["ovning"].build(random.Random(1)).secret_order
    lines = [t.plain for t in report_header("ovning", SCENARIOS["ovning"].title, order)]
    assert lines[0].startswith(" ДОНЕСЕНИЕ")
    assert "ШТАБ СЕВЕРНОГО ФЛОТА" in lines[1] and "Norra flottan" in lines[2]
    assert "ДЛЯ СЛУЖЕБНОГО ПОЛЬЗОВАНИЯ" in lines[3] and "\n" not in lines[3]


@pytest.mark.slow
def test_order_is_shown_as_telegram_and_ending_as_report(tmp_path):
    from ui.app import SubApp
    from ui.teletype import Teletype
    from ui.widgets import ReportLog

    async def run():
        app = SubApp(seed=5, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tt = app.gs().query_one(Teletype)
            await pilot.press("enter")                       # hela ordern
            for _ in range(20):                              # under full last (hela sviten) tar ritningen tid
                await pilot.pause(0.1)
                shown = str(tt.render())
                if "SLUT" in shown:
                    break
            assert "ШИФРОГРАММА" in shown and "РАСШИФРОВАЛ" in shown and "SLUT" in shown
            await pilot.press("enter")                       # ta befälet
            await pilot.pause()
            app.game.world.outcome = {"outcome": "patrol_end"}
            app.game.tick()
            for _ in range(20):
                await pilot.pause(0.1)
                text = "\n".join(t.plain if hasattr(t, "plain") else str(t)
                                 for t in app.gs().query_one(ReportLog).entries)
                if "ДОНЕСЕНИЕ" in text:
                    break
            assert "ДОНЕСЕНИЕ" in text and "ГЛАВНЫЙ ШТАБ ВМФ" in text

    asyncio.run(run())
