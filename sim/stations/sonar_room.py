"""Sonarrummet: kör sonarsensorn, publicerar vad operatören hör och ropar ut det.

Sensorn (sim/sonar.py) är bryggan mellan sanning och kunskap. Stationen
publicerar sensorns utdata som händelser på bussen. Kunskapslagret och
plottlaget lyssnar på dem utan att känna till sonaren.
"""
from __future__ import annotations

import random

from ..crew import Role
from ..events import BearingObserved, ClassificationChanged, ContactDetected, ContactLost
from ..geo import angle_diff, circular_mean
from ..sonar import ClassificationUpdate, Detection, Lost, SonarStation
from ..tma import BearingObs
from .base import Station

BEARING_REPORT_DELTA = 5.0      # grader innan operatören ropar ny bäring
BEARING_REPORT_MAX_AGE = 300    # annars bäringsrapport var 5:e minut
SMOOTH_OBS = 6                  # bäringar som operatören medelvärdesbildar


class SonarRoom(Station):
    role = Role.SONAR

    def __init__(self, game):
        super().__init__(game)
        self.sensor = SonarStation(self.member, random.Random(game.rng.random()))
        self._last_called: dict[str, tuple[float, int]] = {}   # beteckning -> (bäring, tid)

    def held_designations(self) -> list[str]:
        return self.sensor.held_designations()

    def update(self) -> None:
        bus = self.game.bus
        own_xy = self.game.own_position_estimate()
        for ev in self.sensor.update(self.game.world, own_xy):
            match ev:
                case Detection():
                    bus.publish(ContactDetected(self.now, ev.designation, ev.bearing,
                                                ev.classification, ev.quality))
                    self._last_called[ev.designation] = (ev.bearing, self.now)
                    self.say("sonar.new_contact",
                             {"designation": ev.designation, "bearing": ev.bearing,
                              "classification": ev.classification},
                             kind="contact", quality=ev.quality, alarm=True)
                case ClassificationUpdate():
                    bus.publish(ClassificationChanged(self.now, ev.designation,
                                                      ev.classification, ev.quality))
                    self.say("sonar.classified",
                             {"designation": ev.designation, "classification": ev.classification},
                             kind="contact", quality=ev.quality)
                case Lost():
                    bus.publish(ContactLost(self.now, ev.designation))
                    tr = self.game.knowledge.tracks.get(ev.designation)
                    self.say("sonar.lost",
                             {"designation": ev.designation,
                              "last_bearing": tr.last_bearing if tr else None},
                             kind="contact")
                case BearingObs():
                    bus.publish(BearingObserved(self.now, ev))
                    self._maybe_call_bearing(ev.designation)

    def _maybe_call_bearing(self, designation: str) -> None:
        """Operatören medelvärdesbildar de senaste bäringarna innan han ropar."""
        tr = self.game.knowledge.tracks.get(designation)
        if tr is None or not tr.observations:
            return
        recent = tr.observations[-SMOOTH_OBS:]
        bearing = circular_mean([o.bearing for o in recent])
        prev, prev_t = self._last_called.get(designation, (None, -10**9))
        delta = angle_diff(bearing, prev) if prev is not None else 0.0
        if abs(delta) < BEARING_REPORT_DELTA and self.now - prev_t < BEARING_REPORT_MAX_AGE:
            return
        self._last_called[designation] = (bearing, self.now)
        se = sum(o.se for o in recent) / len(recent)
        self.say("sonar.bearing",
                 {"designation": designation, "bearing": bearing,
                  "strength": "svag" if se < 2 else "tydlig" if se < 6 else "stark",
                  "drift": 0 if abs(delta) < 2 else (1 if delta > 0 else -1)},
                 kind="contact")
