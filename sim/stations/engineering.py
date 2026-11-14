"""Maskin: reaktor, framdrivning, batteri, skrov, läckor, luft och skadekontroll."""
from __future__ import annotations

from dataclasses import dataclass

from .. import acoustics, phrases
from ..crew import Role
from ..fmt import kn, nm
from ..orders import CommandSpec, Order
from ..ownship import COMPONENT_LABEL, TEST_DEPTH, TRIM_RESERVE_T
from .base import Station


@dataclass(frozen=True)
class SetPropulsion(Order):
    mode: str            # turbine, electric
    STANDING = True


@dataclass(frozen=True)
class ReactorOrder(Order):
    action: str          # start, stop
    STANDING = True


@dataclass(frozen=True)
class EmergencyBlow(Order):
    pass


@dataclass(frozen=True)
class EngineReport(Order):
    pass


REACTOR_LABEL = {"online": "i drift", "scram": "snabbstoppad", "off": "avställd",
                 "starting": "under uppstart"}


def _status(d: dict) -> str:
    parts = [f"Reaktorn {REACTOR_LABEL[d['reactor']]}",
             "turbindrift" if d["propulsion"] == "turbine" else "elmotor (smygmotor)",
             f"högsta fart {kn(d['max_speed'])} knop",
             f"batteri {d['battery']:.0%}"]
    if d["steam_leak"]:
        parts.append("läcka i ånggeneratorn")
    parts.append(f"skrov {d['hull']:.0%}")
    if d["flooding"] > 0.5:
        parts.append(f"{d['flooding']:.0f} ton vatten ombord")
    if d["co2"] > 0.8:
        parts.append(f"koldioxid {nm(d['co2'])} %")
    damaged = [f"{COMPONENT_LABEL[c]} {h:.0%}" for c, h in d["health"].items() if h < 1.0]
    if damaged:
        parts.append("skadat: " + ", ".join(damaged))
    return "Maskinrapport: " + ", ".join(parts) + "."


def _damage(d: dict) -> str:
    comps = ", ".join(COMPONENT_LABEL[c] for c in d["components"])
    txt = f"Kapten, maskin! {d['severity'].capitalize()} skador"
    if comps:
        txt += f": {comps}"
    if d.get("leak"):
        txt += ". Vatteninträngning, länsning pågår"
    return txt + "."


PHRASES = {
    "eng.status": _status,
    "eng.propulsion": lambda d: "Turbindrift, aye." if d["mode"] == "turbine"
    else "Smygmotor, aye. Högsta fart 5 knop.",
    "eng.refused": lambda d: f"Kapten, {d['reason']}.",
    "eng.reactor.stopping": lambda d: "Ställer av reaktorn. Vi går på batteri, högsta fart 5 knop.",
    "eng.reactor.starting": lambda d: "Startar reaktorn. Cirka tjugo minuter.",
    "eng.blow": lambda d: "Nödblåsning! Alla tankar blåses!",
    "reactor.scram": lambda d: f"Kapten, maskin! Reaktorn har snabbstoppat ({d['cause']}). "
    f"Vi går på batteri och elmotor, högsta fart 5 knop.",
    "reactor.online": lambda d: "Reaktorn är i drift igen.",
    "reactor.leak": lambda d: "Kapten, maskin. Läcka i ånggeneratorn, förhöjd strålning i "
    "reaktorrummet. Vi begränsar till 16 knop medan vi tätar.",
    "reactor.leak_fixed": lambda d: "Läckan i ånggeneratorn är tätad. Full effekt tillgänglig.",
    "battery": lambda d: "Batteriet är tomt, kapten!" if d["level"] == 0
    else f"Batteriet nere på {d['level']:.0%}, kapten.",
    "air": lambda d: f"Koldioxidhalten är {nm(d['co2'])} procent och stiger.",
    "surfaced": lambda d: "Vi är i ytläge!",
    "leak_stopped": lambda d: "Läckan är tätad.",
    "hull.creak": lambda d: f"Skrovet knakar, kapten. {d['depth']:.0f} meter, under provdjup.",
    "damage": _damage,
    "repaired": lambda d: f"{COMPONENT_LABEL[d['component']].capitalize()} är reparerad.",
    "shock": lambda d: ("Smällar nära, inga skador. Små laddningar." if d.get("practice")
                        else "Kraftig tryckvåg! Inga skador." if d["strength"] == "kraftig"
                        else "Detonation på avstånd. Inga skador."),
    "eng.suggest.cavitation": lambda d: f"Kapten, maskin. Vi kaviterar, vi hörs långt. "
    f"Föreslår fart {kn(d['speed'])} knop.",
    "eng.suggest.restart": lambda d: "Kapten, maskin. Föreslår omstart av reaktorn.",
    "eng.suggest.blow": lambda d: f"Kapten, maskin! Vi tar in vatten och sjunker, "
    f"{d['flooding']:.0f} ton ombord. Föreslår nödblåsning!",
    "eng.suggest.creep": lambda d: "Kapten, maskin. Med kontakt i närheten föreslår jag "
    "smygmotor, det sänker vårt ljud kraftigt.",
}
phrases.register(PHRASES)


class EngineeringStation(Station):
    role = Role.ENGINEER
    COMMANDS = [
        CommandSpec(r"smygmotor|elmotor|smyg", lambda m: SetPropulsion("electric"), "smygmotor"),
        CommandSpec(r"turbin|huvudmaskin|turbindrift", lambda m: SetPropulsion("turbine"), "turbin"),
        CommandSpec(r"starta reaktorn|reaktor start|starta reaktor",
                    lambda m: ReactorOrder("start"), "starta reaktorn"),
        CommandSpec(r"stäng reaktorn|stang reaktorn|ställ av reaktorn|reaktor av",
                    lambda m: ReactorOrder("stop"), "stäng reaktorn"),
        CommandSpec(r"nödblåsning|nodblasning|blås alla tankar|blas alla tankar",
                    lambda m: EmergencyBlow(), "nödblåsning"),
        CommandSpec(r"maskin|maskinrapport|skador|skaderapport|status",
                    lambda m: EngineReport(), "maskin"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self._last_shock = -10**9

    @property
    def own(self):
        return self.game.world.own

    def on_order(self, order: Order) -> None:
        own = self.own
        match order:
            case SetPropulsion(mode=mode):
                if not own.set_propulsion(mode):
                    self.say("eng.refused", {"reason": "reaktorn är inte i drift, turbinen kan inte köras"})
                else:
                    self.say("eng.propulsion", {"mode": mode}, kind="ack")
            case ReactorOrder(action="stop"):
                if own.sys.reactor != "online":
                    self.say("eng.refused", {"reason": "reaktorn är redan avställd"})
                else:
                    own.shutdown_reactor()
                    self.say("eng.reactor.stopping", kind="ack")
            case ReactorOrder(action="start"):
                if own.start_reactor(self.now):
                    self.say("eng.reactor.starting", kind="ack")
                else:
                    self.say("eng.refused", {"reason": "reaktorn är redan i drift eller startar"})
            case EmergencyBlow():
                if own.emergency_blow():
                    self.say("eng.blow", kind="ack", alarm=True)
                else:
                    self.say("eng.refused", {"reason": "högtrycksluften är förbrukad"})
            case EngineReport():
                s = own.sys
                self.say("eng.status", {
                    "reactor": s.reactor, "propulsion": s.propulsion,
                    "max_speed": own.max_speed(), "battery": s.battery,
                    "steam_leak": s.steam_leak, "hull": s.hull, "flooding": s.flooding,
                    "co2": s.co2, "health": dict(s.health)})

    def update(self) -> None:
        own, s = self.own, self.own.sys
        while s.alerts:
            type, data = s.alerts.pop(0)
            if type == "shock":
                if self.now - self._last_shock < 15:
                    continue
                self._last_shock = self.now
            alarm = type in ("reactor.scram", "damage", "surfaced") or \
                (type == "battery" and data["level"] <= 0.1)
            self.say(type, data, kind="info", alarm=alarm)

        st = own.state
        if st.speed > acoustics.cavitation_speed(st.depth) + 0.2:
            safe = max(3.0, int(acoustics.cavitation_speed(st.depth)))
            self.suggest("cavitation", "eng.suggest.cavitation", {"speed": safe},
                         order=f"fart {safe}", cooldown=600)
        if s.reactor in ("scram", "off") and (s.battery < 0.5 or s.reactor == "scram"):
            self.suggest("restart", "eng.suggest.restart", order="starta reaktorn",
                         cooldown=900 if s.reactor == "scram" else 1800)
        if s.flooding > TRIM_RESERVE_T and st.depth > 20 and not s.blowing and s.hp_air > 0:
            self.suggest("blow", "eng.suggest.blow", {"flooding": s.flooding},
                         order="nödblåsning", cooldown=120, alarm=True)
        if s.propulsion == "turbine" and self.game.knowledge.tracks and \
                any(t.held for t in self.game.knowledge.tracks.values()):
            self.suggest("creep", "eng.suggest.creep", order="smygmotor", cooldown=3600)
