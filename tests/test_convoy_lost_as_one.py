"""Konvojen som en enhet i sonars rader (2026-11-24): tappad helt och hörd igen sägs alltid, annars hur många
vi hör högst var tionde minut; fartyg utanför konvojen som förut."""
import random

from sim.game import Game
from sim.knowledge import ContactTrack
from sim.scenario import build_scenario
from sim.stations.sonar_room import CONVOY_SAY_S, SonarRoom


class _Convoy:
    members, escorts = ("S-1", "S-2"), ("S-3",)

    def contains(self, d):
        return d in self.members or d in self.escorts


def _room():
    g = Game(build_scenario("konvoj-kort", random.Random(3)), seed=3, warm_up=False)
    k = g.knowledge
    k.tracks.clear()
    for d in ("S-1", "S-2", "S-3", "S-9"):
        k.tracks[d] = ContactTrack(d, 0)
    k.convoy = _Convoy()
    room = g.station(SonarRoom)
    said = []
    room.say = lambda type, data, **kw: said.append(type)     # det stationen säger, före kön
    return g, room, said


def _lose(g, room, *ds):
    for d in ds:
        g.knowledge.tracks[d].held = False
    room._lost_batch = [(d, 100.0) for d in ds]
    room._say_lost()


def _regain(g, room, *ds):
    for d in ds:
        g.knowledge.tracks[d].held = True
    room._regained_batch = [(d, 100.0) for d in ds]
    room._say_regained()


def test_convoy_lines():
    g, room, said = _room()
    _lose(g, room, "S-1", "S-9")
    assert said[-2:] == ["sonar.convoy.count", "sonar.lost"]
    n = len(said)
    _lose(g, room, "S-2")
    assert len(said) == n                       # inom tio minuter: ingen ny räkning
    _lose(g, room, "S-3")
    assert said[-1] == "sonar.convoy.lost"      # hela konvojen tappad: alltid
    _regain(g, room, "S-2")
    assert said[-1] == "sonar.convoy.regained"
    room._convoy_said_t -= CONVOY_SAY_S
    _regain(g, room, "S-1")
    assert said[-1] == "sonar.convoy.count"
