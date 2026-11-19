from sim.game import build_registry
from sim.orders import Help, SetTimeScale, Unknown
from sim.stations import (DEFAULT_STATIONS, QuerySolution, SetCourse, SetDepth,
                          SetSpeed, ShowPlot)

reg = build_registry(DEFAULT_STATIONS)
parse = reg.parse


def test_basic_orders():
    assert parse("kurs 090") == SetCourse(90)
    assert parse("Kurs 45") == SetCourse(45)
    assert parse("fart 5") == SetSpeed(5)
    assert parse("fart 7,5 knop") == SetSpeed(7.5)
    assert parse("djup 100") == SetDepth(100)
    assert parse("djup 150 m") == SetDepth(150)
    assert parse("tid 5") == SetTimeScale(5)
    assert parse("stopp") == SetSpeed(0)
    assert parse("hjälp") == Help()


def test_contact_designations():
    assert parse("läge S-1") == QuerySolution("S-1")
    assert parse("läge s1") == QuerySolution("S-1")
    assert parse("lage") == QuerySolution(None)
    assert parse("plot") == ShowPlot(None)
    assert parse("plot S-2") == ShowPlot("S-2")


def test_invalid_orders():
    assert isinstance(parse("kurs 400"), Unknown)
    assert parse("kurs 400").reason == "kursen måste vara 000–359"
    assert isinstance(parse("tid 3"), Unknown)
    assert isinstance(parse("dyk dyk dyk"), Unknown)


def test_help_lists_every_station_command():
    h = reg.help_text()
    for word in ("kurs 090", "fart 5", "djup 100", "tid 1|2|5|10", "S-1 (", "eld S-1", "fix (",
                 "torped (", "läget (", "radio moskva"):
        assert word in h
    for gone in ("läge S-1", "plot S-1", "skjutlösning S-1", "stjärnfix", "bottenfix", "periskop upp",
                 "förstoring", "sakta back", "full back", "· tuber ·", "eld tub 1 mot", "eld tub 1-3",
                 "sänd rapport S-3", "förslag sonar", "lyssna radio"):
        assert gone not in h, gone              # finns kvar som tysta synonymer
    assert "· hjälp." in h                       # hjälp registreras sist
    assert "Flera order på en rad" in h


# --- flera order på en rad -----------------------------------------------------------
from sim.orders import split_orders


def test_split_orders_separators_and_decimal_comma():
    assert split_orders("kurs 090, fart 5; djup 100") == ["kurs 090", "fart 5", "djup 100"]
    assert split_orders("kurs 090 och fart 5") == ["kurs 090", "fart 5"]
    assert split_orders("fart 5,5") == ["fart 5,5"]
    assert split_orders("fart 5,5, kurs 180") == ["fart 5,5", "kurs 180"]
    assert split_orders("kurs 090,fart 5") == ["kurs 090", "fart 5"]
    assert split_orders("  ;; kurs 090 ; ") == ["kurs 090"]


def _multi_game():
    import random
    from sim.events import ReportDelivered
    from sim.game import Game
    from sim.scenario import default_scenario
    g = Game(default_scenario(random.Random(3)), seed=3)
    g.world.ais.clear()
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def test_several_orders_on_one_line_are_all_executed():
    g, _ = _multi_game()
    g.command("kurs 090, fart 5; djup 100")
    s = g.world.own.state
    assert (s.ordered_course, s.ordered_speed, s.ordered_depth) == (90, 5, 100)


def test_unknown_part_is_named_and_the_rest_still_runs():
    g, reports = _multi_game()
    g.command("kurs 045 och flyg till månen, fart 4")
    for _ in range(20):
        g.tick()
    s = g.world.own.state
    assert (s.ordered_course, s.ordered_speed) == (45, 4)
    unknown = [r.text for r in reports if r.type == "order.unknown"]
    assert unknown and 'förstod inte "flyg till månen"' in unknown[0]


def test_ja_inside_a_line():
    g, _ = _multi_game()
    from sim.stations import EngineeringStation
    g.station(EngineeringStation).suggest("x", "eng.suggest.cavitation", {"speed": 6},
                                          order="fart 6")
    for _ in range(20):
        g.tick()
    g.command("ja, kurs 270")
    s = g.world.own.state
    assert (s.ordered_course, s.ordered_speed) == (270, 6)
