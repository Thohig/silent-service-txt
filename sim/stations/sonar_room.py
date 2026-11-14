"""Sonarrummet: passiv lyssning, transienter, aktiv sonar och förslag.

Sensorn (sim/sonar.py) är bryggan mellan sanning och kunskap. Stationen
publicerar sensorns utdata som händelser på bussen. Kunskapslagret,
plottlaget och torpedrummet lyssnar utan att känna till sonaren.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .. import acoustics, phrases
from ..crew import Role
from ..entities import Transient
from ..events import (BearingObserved, ClassificationChanged, ContactDetected,
                      ContactLost, OwnTorpedoHeard, SoundHeard)
from ..fmt import fmt_course, nm
from ..geo import angle_diff, circular_mean, norm360
from ..orders import CommandSpec, Order
from ..reports import Quality
from ..sonar import (ClassificationUpdate, Detection, Lost, OwnTorpedo, SonarStation,
                     TransientHeard)
from ..tma import BearingObs
from .base import Proposal, Station

BEARING_REPORT_DELTA = 5.0
BEARING_REPORT_MAX_AGE = 300
SMOOTH_OBS = 6
FAST_PING_S = 13
ICE_REPORT_S = 1800          # knakande is rapporteras inte oftare


@dataclass(frozen=True)
class ActivePing(Order):
    pass


def _src(d: dict) -> str:
    return f" från {d['designation']}" if d.get("designation") else ""


PHRASES = {
    "sonar.new_contact": lambda d: f"Kapten, sonar! Ny kontakt i bäring {fmt_course(d['bearing'])}. "
    f"Betecknas {d['designation']}. {d['classification'][:1].upper()}{d['classification'][1:]}.",
    "sonar.classified": lambda d: f"{d['designation']} klassas som {d['classification']}.",
    "sonar.bearing": lambda d: f"{d['designation']}, bäring {fmt_course(d['bearing'])}, "
    f"{d['strength']} signal" + {1: ", bäringen drar höger", -1: ", bäringen drar vänster"}
    .get(d.get("drift", 0), "") + ".",
    "sonar.lost": lambda d: f"Kapten, sonar. Har tappat {d['designation']}"
    + (f", sista bäring {fmt_course(d['last_bearing'])}" if d.get("last_bearing") is not None else "")
    + ".",
    "sonar.regained": lambda d: f"{d['designation']} hörs igen, bäring {fmt_course(d['bearing'])}.",
    "sonar.ping.first": lambda d: f"Kapten, sonar! Aktiv sonar i bäring {fmt_course(d['bearing'])}"
    f"{_src(d)}. Någon söker.",
    "sonar.ping.fast": lambda d: f"Kapten, sonar! Pingtakten{_src(d)} har ökat kraftigt. "
    "De har troligen kontakt med oss!",
    "sonar.ping.slow": lambda d: f"Pingtakten{_src(d)} har minskat igen.",
    "sonar.ping.close": lambda d: f"Pingarna{_src(d)} är mycket starka nu, kapten. "
    "Jag hör dem genom skrovet.",
    "sonar.splash": lambda d: f"Kapten, sonar! Plask i vattnet, bäring {fmt_course(d['bearing'])}"
    + (", nära!" if d.get("near") else ".") + " Sjunkbomber!",
    "sonar.explosion": lambda d: (
        f"Små detonationer i bäring {fmt_course(d['bearing'])}. Troligen signalsjunkbomber."
        if d.get("practice") else
        f"Detonation i bäring {fmt_course(d['bearing'])}" + (", mycket nära!" if d.get("near") else "!")),
    "sonar.nuclear": lambda d: f"Kapten! Enorm detonation i bäring {fmt_course(d['bearing'])}. "
    "Hela hydrofonen är mättad.",
    "sonar.uwt": lambda d: f"Undervattenstelefon i bäring {fmt_course(d['bearing'])}. Morse, "
    "upprepat. Jag tror de uppmanar oss att gå till ytan.",
    "sonar.breakup": lambda d: f"Brytningsljud i bäring {fmt_course(d['bearing'])}{_src(d)}. "
    "Skott som ger vika. Ett fartyg sjunker, kapten.",
    "sonar.ice": lambda d: f"Knakande isljud i bäring {fmt_course(d['bearing'])}"
    + (", starkt. Isen skruvar sig nära." if d.get("near") else ". Isen skruvar sig."),
    "sonar.active.none": lambda d: "Aktiv sonar: inga ekon.",
    "sonar.active.echo": lambda d: f"Aktiv sonar: eko {d['designation']} i bäring "
    f"{fmt_course(d['bearing'])}, avstånd {nm(d['range'])} sjömil.",
    "sonar.active.refused": lambda d: f"Kapten, {d['reason']}.",
    "sonar.suggest.layer": lambda d: f"Kapten, sonar. Vi ligger ovanför språngskiktet på "
    f"{d['layer']:.0f} meter. Föreslår djup {d['depth']:.0f}, under skiktet hörs vi sämre.",
    "sonar.suggest.depth_change": lambda d: f"Föreslår djupändring till {d['depth']:.0f} meter, "
    "så att laddningarna är inställda på fel djup!",
    "sonar.suggest.slow": lambda d: f"Kapten, sonar. Vi hör dåligt i {d['speed']:.0f} knop. "
    "Föreslår fart 4.",
}
phrases.register(PHRASES)


class SonarRoom(Station):
    role = Role.SONAR
    COMMANDS = [
        CommandSpec(r"aktiv sonar|pinga|ping|aktiv", lambda m: ActivePing(), "aktiv sonar"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.sensor = SonarStation(self.member, random.Random(game.rng.random()))
        self._last_called: dict[str, tuple[float, int]] = {}
        self._pings: dict[str, dict] = {}
        self._last_sound: dict[str, int] = {}

    def held_designations(self) -> list[str]:
        return self.sensor.held_designations()

    @property
    def own(self):
        return self.game.world.own

    # --- order -------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        if isinstance(order, ActivePing):
            self._active_ping()

    def _active_ping(self) -> None:
        world, own = self.game.world, self.own
        if own.sys.health["sonar"] < 0.3:
            self.say("sonar.active.refused", {"reason": "sonaren är skadad"})
            return
        o = own.state
        world.emit(Transient("ping", o.x, o.y, o.depth, acoustics.PING_LEVEL_OWN, own.id, self.now))
        world.mission["own_pings"] = world.mission.get("own_pings", 0) + 1
        noise = acoustics.power_sum(world.background_at_own(), own.self_noise())
        own_xy = self.game.own_position_estimate()
        rng = self.sensor.rng
        echoes = []
        for v in world.contacts:
            if v.side == "own" or v.sunk or not v.is_ship:
                continue
            tl = world.tl_to_own(v.state.x, v.state.y, v.depth)
            se = acoustics.active_excess(acoustics.PING_LEVEL_OWN, tl, v.target_strength,
                                         noise, self.sensor.threshold(world)) + rng.gauss(0, 2)
            if se <= 0:
                continue
            r = world.true_range(v)
            desig = self.sensor.designate(v.id)
            if self.game.knowledge.tracks.get(desig) is None:
                self.game.bus.publish(ContactDetected(self.now, desig, world.true_bearing(v),
                                                      "eko, okänd typ", Quality.DALIG))
            r_meas = max(0.05, r + rng.gauss(0, 0.02 * r + 0.02))
            obs = BearingObs(self.now, norm360(world.true_bearing(v) + rng.gauss(0, 1.0)), 1.0,
                             own_xy[0], own_xy[1], o.course, se=se, designation=desig,
                             range_nm=r_meas, range_sigma=0.02 * r + 0.02, source="aktiv")
            self.game.bus.publish(BearingObserved(self.now, obs))
            echoes.append({"designation": desig, "bearing": obs.bearing, "range": r_meas})
        if not echoes:
            self.say("sonar.active.none")
        for e in echoes:
            self.say("sonar.active.echo", e, kind="contact", quality=Quality.SAKER)

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        bus = self.game.bus
        own_xy = self.game.own_position_estimate()
        for ev in self.sensor.update(self.game.world, own_xy):
            match ev:
                case Detection():
                    known = self.game.knowledge.tracks.get(ev.designation)
                    bus.publish(ContactDetected(self.now, ev.designation, ev.bearing,
                                                ev.classification, ev.quality))
                    self._last_called[ev.designation] = (ev.bearing, self.now)
                    if known is not None:
                        self.say("sonar.regained", {"designation": ev.designation,
                                                    "bearing": ev.bearing}, kind="contact")
                        continue
                    self.say("sonar.new_contact",
                             {"designation": ev.designation, "bearing": ev.bearing,
                              "classification": ev.classification},
                             kind="contact", quality=ev.quality, alarm=True)
                    self._suggest_layer()
                case ClassificationUpdate():
                    bus.publish(ClassificationChanged(self.now, ev.designation,
                                                      ev.classification, ev.quality))
                    self.say("sonar.classified",
                             {"designation": ev.designation, "classification": ev.classification},
                             kind="contact", quality=ev.quality)
                case Lost():
                    bus.publish(ContactLost(self.now, ev.designation))
                    tr = self.game.knowledge.tracks.get(ev.designation)
                    self.say("sonar.lost", {"designation": ev.designation,
                                            "last_bearing": tr.last_bearing if tr else None},
                             kind="contact")
                    if self.own.state.speed > 6:
                        self.suggest("slow", "sonar.suggest.slow",
                                     {"speed": self.own.state.speed}, order="fart 4", cooldown=600)
                case BearingObs():
                    bus.publish(BearingObserved(self.now, ev))
                    if ev.source == "sonar":
                        self._maybe_call_bearing(ev.designation)
                case TransientHeard():
                    self._on_sound(ev)
                case OwnTorpedo():
                    # Torpedrummet rapporterar egna torpeder med tubnummer.
                    q = Quality.GOD if ev.se >= 6 else Quality.OSAKER
                    bus.publish(OwnTorpedoHeard(self.now, ev.no, ev.kind, ev.bearing, q))

    def idle_proposals(self) -> list[Proposal]:
        st, env = self.own.state, self.game.world.env
        held = self.game.knowledge.threat_held()
        out = []
        if held and env.layer_depth is not None and st.ordered_depth < env.layer_depth:
            d = env.layer_depth + 60
            out.append(Proposal(2, "idle_layer", "sonar.suggest.layer",
                                f"djup {d:.0f}", {"layer": env.layer_depth, "depth": d}))
        if not held and st.ordered_speed > 6:
            out.append(Proposal(4, "idle_slow", "sonar.suggest.slow", "fart 4",
                                {"speed": st.ordered_speed}))
        return out

    def _suggest_layer(self) -> None:
        env, st = self.game.world.env, self.own.state
        if env.layer_depth is not None and st.ordered_depth < env.layer_depth:
            d = env.layer_depth + 60
            self.suggest("layer", "sonar.suggest.layer", {"layer": env.layer_depth, "depth": d},
                         order=f"djup {d:.0f}", cooldown=1800)

    def _dedupe(self, key: str, window: int) -> bool:
        if self.now - self._last_sound.get(key, -10**9) < window:
            return False
        self._last_sound[key] = self.now
        return True

    def _on_sound(self, ev: TransientHeard) -> None:
        bus = self.game.bus
        d = {"bearing": ev.bearing, "designation": ev.designation}
        detail = ""
        if ev.kind == "ping":
            key = ev.designation or "okänd"
            if key not in self._pings and "okänd" in self._pings and ev.designation:
                self._pings[key] = self._pings.pop("okänd")      # samma pingare, nu identifierad
            p = self._pings.setdefault(key, {"last": None, "fast": False, "close_t": -10**9})
            if p["last"] is None or self.now - p["last"] > 900:
                self.say("sonar.ping.first", d, kind="contact", alarm=True)
                self._suggest_layer()
            else:
                interval = self.now - p["last"]
                if interval <= FAST_PING_S and not p["fast"]:
                    p["fast"] = True
                    detail = "fast"
                    self.say("sonar.ping.fast", d, kind="contact", alarm=True)
                    self._evasive_depth()
                elif interval >= 20 and p["fast"]:
                    p["fast"] = False
                    self.say("sonar.ping.slow", d, kind="contact")
            if ev.se > 75 and self.now - p["close_t"] > 300:
                p["close_t"] = self.now
                self.say("sonar.ping.close", d, kind="contact")
            p["last"] = self.now
        elif ev.kind == "splash":
            if self._dedupe("splash", 20):
                self.say("sonar.splash", {**d, "near": ev.se > 45}, kind="contact", alarm=True)
                self._evasive_depth(cooldown=60)
        elif ev.kind == "explosion":
            if ev.se > 160:
                if self._dedupe("nuclear", 60):
                    self.say("sonar.nuclear", d, kind="contact", alarm=True)
            elif ev.own_weapon:
                pass                    # torpedrummet rapporterar sina egna träffar
            elif self._dedupe("explosion", 10):
                self.say("sonar.explosion", {**d, "practice": ev.practice, "near": ev.se > 110},
                         kind="contact", alarm=not ev.practice)
        elif ev.kind == "ice":
            if self._dedupe("ice", ICE_REPORT_S):
                self.say("sonar.ice", {**d, "near": ev.se > 25}, kind="contact",
                         quality=Quality.GOD if ev.se > 10 else Quality.OSAKER)
        elif ev.kind == "uwt":
            if self._dedupe("uwt", 120):
                self.say("sonar.uwt", d, kind="contact")
        elif ev.kind == "breakup":
            if self._dedupe(f"breakup{ev.designation}", 60):
                # brytningsljudet följer på detonationen; rapportera det efter den
                self.say("sonar.breakup", d, kind="contact", alarm=True, extra_delay=6)
        bus.publish(SoundHeard(self.now, ev.kind, ev.bearing, ev.designation, ev.practice, detail))

    def _evasive_depth(self, cooldown: int = 300) -> None:
        st = self.own.state
        env = self.game.world.env
        if env.layer_depth is not None and st.ordered_depth < env.layer_depth:
            d = env.layer_depth + 60
        elif st.ordered_depth < 200:
            d = min(st.ordered_depth + 80, 280)
        else:
            d = st.ordered_depth - 80
        self.suggest("evade_depth", "sonar.suggest.depth_change", {"depth": d},
                     order=f"djup {d:.0f}", cooldown=cooldown, alarm=True)

    def _maybe_call_bearing(self, designation: str) -> None:
        tr = self.game.knowledge.tracks.get(designation)
        if tr is None or not tr.observations:
            return
        recent = [o for o in tr.observations if o.source == "sonar"][-SMOOTH_OBS:]
        if not recent:
            return
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
