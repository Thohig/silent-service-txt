"""Maskin: reaktor, framdrivning, batteri, skrov, läckor, luft och skadekontroll."""
from __future__ import annotations

from dataclasses import dataclass

from .. import acoustics, phrases
from ..crew import Role
from ..fmt import fmt_course, kn, nm
from ..orders import CommandSpec, Order
from ..ice import masts_clear
from ..ownship import COMPONENT_LABEL, PERISCOPE_DEPTH, TEST_DEPTH, TRIM_RESERVE_T
from .base import Proposal, Station


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


@dataclass(frozen=True)
class Ventilate(Order):
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
    if d.get("fire"):
        parts.append("brand i turbinrummet")
    if d.get("smoke", 0) > 0.05:
        parts.append(f"rök {_smoke_word(d['smoke'])}")
    if d["co2"] > 0.8:
        parts.append(f"koldioxid {nm(d['co2'])} %")
    damaged = [f"{COMPONENT_LABEL[c]} {h:.0%}" for c, h in d["health"].items() if h < 1.0]
    if damaged:
        parts.append("skadat: " + ", ".join(damaged))
    return "Maskinrapport: " + ", ".join(parts) + "."


def _smoke_word(v: float) -> str:
    return ("lätt" if v < 0.3 else "besvärande" if v < 0.5 else "tät" if v < 0.7
            else "mycket tät" if v < 0.85 else "livsfarlig")


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
    "ice.collision": lambda d: f"Kapten! Vi har gått in i isen! {d['severity'].capitalize()} skador"
    + (": " + ", ".join(COMPONENT_LABEL[c] for c in d["components"]) if d["components"] else "")
    + (". Vatteninträngning, länsning pågår." if d.get("leak") else ".")
    + " Maskinen stoppad.",
    "ice.touch": lambda d: "Vi tog i en isköl, kapten. Långsam fart, inga skador. Maskinen stoppad.",
    "ice.bump": lambda d: ("Vi stöter i isen ovanför, kapten. "
                           + ("Den är tunn, men vi har för hög fart för att bryta igenom. "
                              if d.get("thin") and d.get("too_fast")
                              else "Den är för tjock att bryta igenom. " if not d.get("thin")
                              else "")
                           + f"Går ned till {d['back_to']} meter."),
    "ice.pressing": lambda d: "Tornet ligger an mot tunn is. Vi trycker på, cirka fyrtio sekunder.",
    "ice.broke_through": lambda d: "Vi har brutit igenom isen!"
    + (" Periskopet fick en smäll." if d.get("damaged") else " Inga skador."),
    "repaired": lambda d: f"Reparationen av {COMPONENT_LABEL[d['component']]} är klar.",
    "shock": lambda d: ("Smällar nära, inga skador. Små laddningar." if d.get("practice")
                        else "Kraftig tryckvåg! Inga skador." if d["strength"] == "kraftig"
                        else "Detonation på avstånd. Inga skador."),
    "fire": lambda d: f"BRAND! Brand i {d['compartment']}! Avdelningen utrymd och stängd. "
    "Turbinen är stoppad, vi går på elmotor. Rökdykare på väg in.",
    "fire.out": lambda d: "Branden i turbinrummet är släckt, kapten. Men det glöder i isoleringen "
    "och röken sprider sig. Vi måste ventilera, och det kräver öppen luft.",
    "smoke": lambda d: f"Kapten, maskin. Röken är {_smoke_word(d['level'])} nu."
    + (" Folk har svårt att andas." if d["level"] >= 0.7 else "")
    + (" Vi har inte länge kvar!" if d["level"] >= 0.85 else ""),
    "vent.stopped": lambda d: "Ventilationen avbruten, masten är under vatten eller is.",
    "vent.done": lambda d: "Luften är ren igen, kapten. Ventilationen stängd.",
    "eng.vent.start": lambda d: "Ventilerar genom masten. Det tar en stund."
    if not d.get("surface") else "Luckorna öppna, ventilerar.",
    "eng.suggest.vent": lambda d: f"Kapten, maskin. Röken är {_smoke_word(d['smoke'])} och vi har "
    "öppen luft ovanför. Föreslår att vi ventilerar.",
    "eng.suggest.vent_vak": lambda d: f"Kapten, maskin. Röken är {_smoke_word(d['smoke'])} och vi måste "
    f"ventilera. Navigatören har öppning {d['no']} i bäring {fmt_course(d['bearing'])}, cirka "
    f"{d['range']} meter. Föreslår att vi går dit.",
    "eng.smoke_no_opening": lambda d: f"Kapten, maskin. Röken är {_smoke_word(d['smoke'])} och vi "
    "måste ventilera, men vi har ingen öppning i isen. Vi måste hitta öppet vatten.",
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
        CommandSpec(r"ventilera|vädra|vadra|ventilation", lambda m: Ventilate(), "ventilera"),
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
            case SetPropulsion(mode="turbine") if own.sys.fire:
                self.say("eng.refused", {"reason": "det brinner i turbinrummet"})
            case Ventilate():
                st = own.state
                if own.sys.smoke <= 0.0:
                    self.say("eng.refused", {"reason": "luften är ren, ingen ventilation behövs"})
                elif st.depth > PERISCOPE_DEPTH:
                    self.say("eng.refused", {"reason": "vi måste upp på periskopdjup för att ventilera"})
                elif not own.start_ventilation(masts_clear(self.game.world)):
                    self.say("eng.refused", {"reason": "det är is ovanför, masten kommer inte upp"})
                else:
                    self.say("eng.vent.start", {"surface": own.surfaced}, kind="ack")
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
                    "co2": s.co2, "health": dict(s.health), "fire": s.fire, "smoke": s.smoke})

    def idle_proposals(self) -> list[Proposal]:
        s, st = self.own.sys, self.own.state
        out = []
        if s.flooding > TRIM_RESERVE_T and st.depth > 20 and not s.blowing and s.hp_air > 0:
            out.append(Proposal(1, "idle_blow", "eng.suggest.blow", "nödblåsning",
                                {"flooding": s.flooding}, cooldown=120))
        if st.speed > acoustics.cavitation_speed(st.depth) + 0.2:
            safe = max(3.0, int(acoustics.cavitation_speed(st.depth)))
            out.append(Proposal(1, "idle_cavitation", "eng.suggest.cavitation", f"fart {safe}",
                                {"speed": safe}, cooldown=600))
        if s.reactor in ("scram", "off") and s.battery < 0.5:
            out.append(Proposal(1, "idle_restart", "eng.suggest.restart", "starta reaktorn"))
        if s.propulsion == "turbine" and self.game.knowledge.threat_held():
            out.append(Proposal(2, "idle_creep", "eng.suggest.creep", "smygmotor"))
        return out

    def _smoke_advice(self) -> None:
        own, s = self.own, self.own.sys
        if s.smoke < 0.15 or s.fire or s.ventilating:
            return
        alarm = s.smoke >= 0.7
        if own.state.depth <= PERISCOPE_DEPTH and masts_clear(self.game.world):
            self.suggest("vent", "eng.suggest.vent", {"smoke": s.smoke}, order="ventilera",
                         cooldown=120, alarm=alarm)
            return
        from .navigation import NavigationStation
        try:
            nav = self.game.station(NavigationStation)
        except KeyError:
            return
        if nav.vak is not None:
            return
        o = nav.best_opening() if nav.under_ice() else None
        if o is not None:
            self.suggest("vent_vak", "eng.suggest.vent_vak", {"smoke": s.smoke, **nav.opening_data(o)},
                         order="vak", cooldown=600, alarm=alarm, quality=o.quality(self.now))
        elif nav.under_ice():
            self.suggest("smoke_search", "eng.smoke_no_opening", {"smoke": s.smoke},
                         order="fart 5, djup 60", cooldown=900, alarm=alarm)

    def update(self) -> None:
        own, s = self.own, self.own.sys
        while s.alerts:
            type, data = s.alerts.pop(0)
            if type == "shock":
                if self.now - self._last_shock < 15:
                    continue
                self._last_shock = self.now
            alarm = type in ("reactor.scram", "damage", "surfaced", "ice.collision", "ice.bump",
                             "fire") or (type == "smoke" and data["level"] >= 0.7) or \
                (type == "battery" and data["level"] <= 0.1)
            self.say(type, data, kind="info", alarm=alarm)

        for m in self.game.crew.values():           # röken påverkar alla ombord
            m.traits["smoke"] = s.smoke
        self._smoke_advice()

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
                self.game.knowledge.threat_held():
            self.suggest("creep", "eng.suggest.creep", order="smygmotor", cooldown=3600)
