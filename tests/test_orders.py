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
    for word in ("kurs 090", "fart 5", "djup 100", "tid 1|2|5|10", "läge S-1", "plot S-1"):
        assert word in h
    assert h.rstrip().endswith("hjälp")
