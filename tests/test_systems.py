"""Systemtavlan: stationernas element ur egna instrument, och rastreringen."""
import pytest
import asyncio
import random

from sim.crew import Role
from sim.game import Game
from sim.scenario import build_scenario
from sim.stations import DEFAULT_STATIONS, Station, TorpedoRoom
from sim.systems import DANGER, OK, WARN, Compartment, Flooding, Gauge, TubeRack
from ui.systems_render import render_systems


def _game(key="kuba", seed=3, **kw):
    return Game(build_scenario(key, random.Random(seed)), seed=seed, **kw)


def _run(g, n):
    for _ in range(n):
        g.tick()


def _text(lines):
    return "\n".join(line.plain for line in lines)


def test_calm_board_has_all_panels_and_compartments():
    g = _game()
    _run(g, 60)
    v = g.systems()
    assert v.panels() == ["MASKIN", "TRIM", "SKADOR", "NAVIGATION", "VAPEN", "SONAR", "SAMBAND"]
    assert [c.no for c in v.compartments()] == list(range(1, 10))
    assert v.worst() == OK
    rack = v.first(TubeRack)
    assert len(rack.tubes) == 8 and rack.tubes[0][1] == "53-61" and rack.tubes[7][1] is None
    txt = _text(render_systems(v, 110))
    assert "reaktor" in txt and "i drift" in txt and "100 %" in txt


def test_fire_leak_and_damage_show_where_they_are():
    g = _game()
    _run(g, 30)
    s = g.world.own.sys
    s.health["tubes"] = 0.15
    s.flooding, s.leak_rate = 30.0, 0.3
    _run(g, 1)                                  # skadekontrollen väljer vad som lagas
    s.fire, s.smoke = True, 0.4
    g.invalidate_views()
    v = g.systems()
    comps = {c.name: c for c in v.compartments()}
    assert comps["turbin"].state == DANGER and comps["turbin"].note == "BRAND"
    assert comps["torped"].state == DANGER and comps["torped"].note == "skada"
    assert comps["bostad"].state == WARN and comps["bostad"].note == "rök"
    assert v.worst() == DANGER
    damage = {gg.label: gg for gg in v.gauges("SKADOR")}
    assert damage["Torpedtuber"].text.startswith("svårt skadad")
    assert damage["Torpedtuber"].text.endswith("lagas")         # en komponent i taget
    txt = _text(render_systems(v, 110))
    assert "BRAND" in txt and "≈" in txt and "läcker" in txt


def test_reloading_tube_counts_down():
    g = _game()
    g.command("ladda tub 7 SET-53")
    _run(g, 20)
    rack = g.systems().first(TubeRack)
    n, load, loading, left = rack.tubes[6]
    assert load is None and loading == "SET-53" and 0 < left < 300
    assert "SET-53 4:" in _text(render_systems(g.systems(), 110))


def test_board_never_names_truth_ids():
    g = _game(seed=5)
    g.command("fart 8")
    _run(g, 1500)
    txt = _text(render_systems(g.systems(), 140))
    ids = [v.id for v in g.world.contacts if v is not g.world.own]
    assert ids
    for vid in ids:
        assert f" {vid}" not in txt and f"{vid}," not in txt


def test_lines_fit_the_width():
    g = _game()
    g.world.own.sys.flooding = 50.0
    _run(g, 10)
    for w in (50, 80, 110, 150):
        for line in render_systems(g.systems(), w):
            assert line.cell_len <= w, (w, line.plain)


class CoolantStation(Station):
    role = Role.ENGINEER

    def system_items(self):
        return [Gauge("KYLNING", "Primärkrets", "280 °C", WARN, 0.8)]


def test_new_station_draws_its_own_panel():
    g = _game(stations=[*DEFAULT_STATIONS, CoolantStation])
    v = g.systems()
    assert v.panels()[-1] == "KYLNING"
    assert "Primärkrets" in _text(render_systems(v, 110))


@pytest.mark.slow
def test_tab_cycles_through_the_boat_view(tmp_path):
    from ui.app import SubApp
    from ui.boat import BoatScreen
    from ui.chart import ChartScreen
    from ui.logview import LogScreen

    async def run():
        app = SubApp(seed=2, log_dir=tmp_path, scenario="kuba")
        async with app.run_test(size=(120, 45)) as pilot:   # stort: översikten är huvudvy
            await pilot.press("enter", "enter")
            for _ in range(60):
                app.game.tick()
            from ui.sonar import SonarScreen
            from ui.central import CentralScreen
            for cls in (CentralScreen, LogScreen, ChartScreen, SonarScreen, BoatScreen):
                await pilot.press("tab")
                assert isinstance(app.screen, cls)
            await pilot.pause(0.6)
            body = str(app.screen.query_one("#boat-body").render())
            assert "MASKIN" in body and "53-61" in body and "▬▶" in body
            app.save_screenshot(str(tmp_path / "ubaten.svg"))
            await pilot.press("tab", "tab")       # periskopbilden, sedan översikten
            assert not isinstance(app.screen, (LogScreen, ChartScreen, BoatScreen))
            for word in ("system", "profil", "ubåt"):
                await pilot.press(*word, "enter")
                assert isinstance(app.screen, BoatScreen)
                await pilot.press("escape")
                assert not isinstance(app.screen, BoatScreen)
            await pilot.press(*"kurs 090", "enter")
            assert app.game.world.own.state.ordered_course == 90

    asyncio.run(run())


def _board(*gauges):
    from sim.systems import SystemsView
    return SystemsView("12:00:00", list(gauges))


def test_compact_panels_put_danger_first_and_fold_calm_panels_when_short():
    from ui.systems_render import CALM_TEXT, render_compact_panels
    v = _board(Gauge("MASKIN", "Reaktor", "i drift", OK), Gauge("MASKIN", "Turbin", "12 kn", OK),
               Gauge("SONAR", "Kontakter", "S-1", OK), Gauge("SONAR", "Bakgrund", "60 dB", OK),
               Gauge("SKADOR", "Läcka", "avd VII", DANGER), Gauge("SKADOR", "Pumpar", "80 %", WARN))
    tall = _text(render_compact_panels(v, 50, 40))
    assert tall.index("SKADOR") < tall.index("MASKIN") < tall.index("SONAR")
    assert "Turbin" in tall and CALM_TEXT not in tall           # plats: allt fullt
    short = render_compact_panels(v, 50, 6)
    txt = _text(short)
    assert len(short) <= 6
    assert "Läcka" in txt and "Pumpar" in txt                    # faran syns alltid fullt
    assert "SONAR" in txt and CALM_TEXT in txt and "Bakgrund" not in txt
    assert txt.splitlines()[-1].strip().startswith("· " + CALM_TEXT)   # lugna sist, på en rad
    assert all(len(line.plain) == 50 for line in short)


def test_compact_panels_cut_when_even_danger_does_not_fit():
    from ui.systems_render import render_compact_panels
    v = _board(*(Gauge("SKADOR", f"Rad {i}", "fara", DANGER) for i in range(10)))
    rows = render_compact_panels(v, 40, 5)
    assert len(rows) == 5 and rows[-1].plain.strip() == "…"


def test_compact_panels_of_a_real_board_fit():
    from ui.systems_render import render_compact_panels
    g = _game()
    _run(g, 60)
    rows = render_compact_panels(g.systems(), 56, 30)
    assert 0 < len(rows) <= 30 and "53-61" in _text(rows)


def test_compact_panels_keep_only_alarms_when_even_folding_is_not_enough():
    from ui.systems_render import render_compact_panels
    v = _board(*(Gauge("MASKIN", f"Ok {i}", "bra", OK) for i in range(6)),
               Gauge("MASKIN", "Vatten", "30 ton", DANGER), Gauge("SONAR", "Kontakter", "S-1", OK))
    txt = _text(render_compact_panels(v, 50, 4))
    assert "Vatten" in txt and "Ok 0" not in txt and "SONAR" in txt


def test_hull_is_drawn_in_braille_with_compartments_as_text():
    from ui.systems_render import HULL_ROWS, render_hull
    g = _game()
    _run(g, 5)
    v = g.systems()
    rows = render_hull(v.compartments(), None, 120)
    assert len(rows) == HULL_ROWS
    text = "\n".join(r.plain for r in rows)
    assert sum(0x2800 < ord(ch) <= 0x28FF for ch in text) > 150     # skrov, torn och skott
    for name in ("torped", "central", "reaktor", "akter", "IX"):
        assert name in text
    assert "╪" in text                                              # propellern
    for n in (3, 5, 6):                                             # vattnet i tre avdelningar
        g.world.own.sys.dmg.water[n] = 13.4
    _run(g, 2)
    v = g.systems()
    wet = "\n".join(r.plain for r in render_hull(v.compartments(), v.first(Flooding), 120))
    assert "40 ton vatten" in wet
    assert sum(0x2800 < ord(ch) <= 0x28FF for ch in wet) > \
        sum(0x2800 < ord(ch) <= 0x28FF for ch in text) + 25        # vattnet i tre avdelningar
    assert render_hull(v.compartments(), None, 40) == []           # för smalt


def test_sonar_panel_counts_contacts_instead_of_clipping():
    from sim.stations.sonar_room import contacts_text
    assert contacts_text([], 0) == "inga"
    assert contacts_text(["S-1"], 0) == "S-1"
    assert contacts_text(["S-1", "S-4"], 1) == "S-1, S-4 (1 hot)"
    assert contacts_text(["S-1", "S-2", "S-3", "S-12"], 2) == "4 (2 hot)"
