"""Radion: Radio Moskva ombord efter orderns datum, och allt radion tar emot hamnar i kunskapen."""
import asyncio
import random

import pytest

from sim.broadcasts import BROADCASTS, broadcasts_for, order_day
from sim.events import ReportDelivered
from sim.game import Game
from sim.scenario import SCENARIOS, build_scenario
from sim.stations.radio import LISTEN_S, RadioStation


def test_broadcasts_follow_the_calendar_and_moscow_falls_silent_on_the_28th():
    assert order_day("FRÅN: X\nDATUM: 24 OKTOBER 1962\n") == 24
    assert order_day("ingen datumrad") is None
    assert all(b.from_day == 1 for b in broadcasts_for(None))
    assert "blockad" in broadcasts_for(22)[0].sv
    assert all(b.from_day == 24 for b in broadcasts_for(26))
    war = broadcasts_for(28)
    assert len(war) == 1 and war[0].ru == ""
    for b in BROADCASTS:
        assert not any("a" <= c.lower() <= "z" for c in b.ru)     # rösten läser bara kyrilliska
    for key in SCENARIOS:                                          # alla ordrar har ett datum
        assert order_day(build_scenario(key, random.Random(1)).secret_order) is not None


def _game(key="kuba"):
    g = Game(build_scenario(key, random.Random(2)), seed=2)
    said = []
    g.bus.subscribe(ReportDelivered, lambda e: said.append(e.report))
    return g, said


def _run(g, seconds):
    for _ in range(seconds):
        g.tick()


def test_listening_needs_antenna_depth_and_gives_a_broadcast():
    g, said = _game()
    g.command("lyssna radio")
    _run(g, 15)
    assert any(r.type == "radio.refused" and "antenndjup" in r.text for r in said)
    g.world.own.state.depth = 20.0
    g.world.own.state.ordered_depth = 20.0
    g.command("lyssna på moskva")
    _run(g, LISTEN_S + 15)
    heard = [r for r in said if r.type == "radio.moscow"]
    assert heard and "Radio Moskva" in heard[0].text and heard[0].data["telegram"] == 1
    tg = g.knowledge.telegrams
    assert len(tg) == 1 and tg[0].kind == "broadcast" and tg[0].number == 1
    assert heard[0].speech and not any("a" <= c.lower() <= "z" for c in heard[0].speech)


def test_staff_telegrams_reach_knowledge_with_numbers():
    g, _ = _game()
    radio = g.station(RadioStation)
    g.world.own.state.depth = 20.0
    g.world.own.state.ordered_depth = 20.0
    radio._deliver(upto=1)
    tg = g.knowledge.telegrams
    assert [t.kind for t in tg] == ["telegram", "telegram"] and [t.number for t in tg] == [1, 2]
    assert tg[0].text == radio.delivered[0]


@pytest.mark.slow
def test_telegram_opens_the_log_with_only_the_strips(tmp_path):
    from ui.app import SubApp
    from ui.logview import LogScreen
    from ui.strips import TelegramStrip

    def shown(app):
        log = app.screen.query_one("#logview-log")
        return "\n".join("".join(seg.text for seg in line) for line in log.lines)

    async def run():
        app = SubApp(seed=2, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(110, 34)) as pilot:   # loggen är huvudvy
            await pilot.pause()
            await pilot.press("enter", "enter")
            await pilot.pause()
            main = app.gs().query_one("#log")
            assert isinstance(main.entries[0], TelegramStrip)          # ordern först
            app.game.station(RadioStation)._deliver(upto=0)
            for _ in range(30):
                app.game.tick()
            assert sum(isinstance(e, TelegramStrip) for e in main.entries) == 2
            await pilot.press(*"telegram", "enter")
            await pilot.pause(0.3)
            assert isinstance(app.screen, LogScreen) and app.screen.only_telegrams
            txt = shown(app)
            assert "ШИФРОГРАММА" in txt and "РАДИОГРАММА № 1" in txt and "HUVUDSTABEN" in txt
            assert "Du har befälet" not in txt
            await pilot.press("space")                                  # hela loggen
            await pilot.pause(0.3)
            assert not app.screen.only_telegrams and "Du har befälet" in shown(app)
            await pilot.press(*"telegram", "enter")
            assert app.screen.only_telegrams
            await pilot.press(*"telegram", "enter")                     # igen stänger
            assert not isinstance(app.screen, LogScreen)

    asyncio.run(run())
