"""Tester för utbyggnadspunkterna: stationer, orderregister, rapportfilter och händelsebuss."""
import random
from dataclasses import dataclass

from sim.crew import Role
from sim.events import BearingObserved, ContactDetected, ReportDelivered
from sim.game import Game
from sim.orders import CommandSpec, Order
from sim.scenario import default_scenario
from sim.stations import DEFAULT_STATIONS, Station
from sim.tma import BearingObs


def _game(**kw):
    g = Game(default_scenario(random.Random(3)), seed=3, **kw)
    reports = []
    g.bus.subscribe(ReportDelivered, lambda e: reports.append(e.report))
    return g, reports


def _run(g, seconds):
    for _ in range(seconds):
        g.tick()


# --- ny station utan att röra Game -----------------------------------------------
@dataclass(frozen=True)
class FireTube(Order):
    tube: int


class FakeTorpedoRoom(Station):
    role = Role.NAVIGATOR          # lånar en befintlig besättningsman i testet
    COMMANDS = [CommandSpec(r"tub (\d)", lambda m: FireTube(int(m[1])), "tub 1")]

    def __init__(self, game):
        super().__init__(game)
        self.fired: list[int] = []
        self.ticks = 0

    def on_order(self, order):
        if isinstance(order, FireTube):
            self.fired.append(order.tube)
            self.say("torpedo.fired", {"tube": order.tube}, kind="ack")

    def update(self):
        self.ticks += 1


def test_new_station_plugs_in_with_commands_updates_and_reports():
    g, reports = _game(stations=[*DEFAULT_STATIONS, FakeTorpedoRoom])
    room = g.station(FakeTorpedoRoom)
    g.command("tub 2")
    _run(g, 15)
    assert room.fired == [2]
    assert room.ticks == 15
    assert "tub 1" in g.registry.help_text()
    # okänd meddelandetyp får en reservformulering i stället för att krascha
    assert any(r.type == "torpedo.fired" and "2" in r.text for r in reports)


def test_other_stations_ignore_foreign_orders():
    g, reports = _game()
    g.command("kurs 045")
    _run(g, 10)
    assert [r.type for r in reports if r.kind == "ack"] == ["nav.course.ack"]


# --- rapportfilter arbetar på data -------------------------------------------------
def test_filter_can_falsify_data_and_text_follows():
    g, reports = _game()

    def saboteur(r):
        if r.type == "nav.course.ack":
            r.data["course"] = (r.data["course"] + 180) % 360
        return r

    g.queue.filters.append(saboteur)
    g.command("kurs 045")
    _run(g, 10)
    ack = next(r for r in reports if r.type == "nav.course.ack")
    assert ack.text == "Kurs 225, aye."
    assert g.world.own.state.ordered_course == 45     # sanningen påverkas inte


def test_filter_can_silence_reports():
    g, reports = _game()
    g.queue.filters.append(lambda r: None if r.role == Role.NAVIGATOR.value else r)
    g.command("kurs 045")
    _run(g, 120)
    assert not any(r.role == Role.NAVIGATOR.value for r in reports)


# --- kunskap byggs från bussen --------------------------------------------------
def test_knowledge_is_fed_only_by_bus_events():
    g, _ = _game()
    g.bus.publish(ContactDetected(5, "S-9", 120.0, "ytfartyg"))
    g.bus.publish(BearingObserved(10, BearingObs(10, 121.0, 1.0, 0, 0, 0, designation="S-9")))
    tr = g.knowledge.track("s9")
    assert tr is not None and tr.classification == "ytfartyg"
    assert tr.last_bearing == 121.0
    assert not hasattr(g.knowledge, "world")


def test_captain_hears_limits_from_crew():
    g, reports = _game()
    g.command("djup 900")
    _run(g, 10)
    assert any(r.text == "Kapten, största djup är 300 meter." for r in reports)
    assert g.world.own.state.ordered_depth == 100
