"""Maskin: reaktor, framdrivning, batteri, skrov, läckor, luft och skadekontroll."""
from __future__ import annotations

from dataclasses import dataclass

from .. import acoustics, phrases
from ..crew import Role
from ..events import OwnSoundMade
from ..fmt import fmt_course, kn, nm
from .. import russian as R
from ..russian import ru
from ..orders import CommandSpec, Order
from ..ice import masts_clear
from ..ownship import (COMPONENT_LABEL, COMPONENTS, FLOOD_LOSS_T, PERISCOPE_DEPTH, SMOKE_LEVELS,
                       TEST_DEPTH, TRIM_RESERVE_T)
from ..systems import (DANGER, INFO, OFF, OK, SEVERITY, WARN, Compartment, Flooding, Gauge,
                       health_state, health_word)
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


# Avdelningarna i Projekt 627A, från fören. Komponenterna bor i en avdelning var.
COMPARTMENTS = ((1, "torped"), (2, "batteri"), (3, "central"), (4, "diesel"), (5, "reaktor"),
                (6, "turbin"), (7, "el"), (8, "bostad"), (9, "akter"))
COMPONENT_COMPARTMENT = {"tubes": 1, "sonar": 1, "periscope": 3, "radio": 3,
                         "propulsion": 6, "planes": 9}
COMPONENT_NAME = {"sonar": "Sonar", "planes": "Roder", "propulsion": "Framdrivning",
                  "tubes": "Torpedtuber", "periscope": "Periskop", "radio": "Radio"}


def _pct(v: float) -> str:
    return f"{round(v * 100)} %"


def _smoke_word(v: float) -> str:
    return ("lätt" if v < 0.3 else "besvärande" if v < 0.5 else "tät" if v < 0.7
            else "mycket tät" if v < 0.85 else "livsfarlig")


ORDINAL = {1: "första", 2: "andra", 3: "tredje", 4: "fjärde", 5: "femte", 6: "sjätte",
           7: "sjunde", 8: "åttonde", 9: "nionde"}
INSPECT_NOTE = {"BRAND": "brand", "skada": "skador", "lågt": "batteriet lågt"}
INSPECT_AFTER_S = 60         # avdelningarna rapporterar så här länge efter haverilarmet
INSPECT_ALERTS = ("damage", "ice.collision", "bottom.collision", "fire")


def _ordinals(nos: list[int]) -> str:
    words = [ORDINAL[n] for n in nos]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " och " + words[-1]


def _inspected(d: dict) -> str:
    """Avdelningarna har inspekterats: anmärkningar per avdelning, som i flottan."""
    remarks: dict[str, list[int]] = {}
    for n, note in d["remarks"]:
        remarks.setdefault(note, []).append(n)
    if not remarks:
        txt = "Alla nio avdelningar inspekterade, inga anmärkningar."
    else:
        txt = "Avdelningarna inspekterade."
        clean = [n for n in ORDINAL if all(n not in v for v in remarks.values())]
        if clean:
            txt += f" Inga anmärkningar i {_ordinals(clean)}."
        for note, nos in remarks.items():
            where = "alla avdelningar" if len(nos) == len(ORDINAL) else \
                f"{_ordinals(nos)} avdelningen" if len(nos) == 1 else f"{_ordinals(nos)}"
            txt += f" {where[:1].upper()}{where[1:]}: {INSPECT_NOTE.get(note, note)}."
    if d.get("leak"):
        txt += " Vatteninträngning, länsning pågår."
    return txt


def _damage(d: dict) -> str:
    comps = ", ".join(COMPONENT_LABEL[c] for c in d["components"])
    txt = f"{ru('Avarijnaja trevoga')}! {d['severity'].capitalize()} skador"
    if comps:
        txt += f": {comps}"
    if d.get("leak"):
        txt += ". Vatteninträngning, länsning pågår"
    return txt + "."


PHRASES = {
    "eng.status": _status,
    "eng.inspected": _inspected,
    "eng.propulsion": lambda d: f"{ru('Jest')}, turbindrift." if d["mode"] == "turbine"
    else f"{ru('Jest')}, smygmotor. Högsta fart 5 knop.",
    "eng.refused": lambda d: f"Kapten, {d['reason']}.",
    "eng.reactor.stopping": lambda d: "Ställer av reaktorn. Vi går på batteri, högsta fart 5 knop.",
    "eng.reactor.starting": lambda d: "Startar reaktorn. Cirka tjugo minuter.",
    "eng.blow": lambda d: "Nödblåsning! Alla tankar blåses!",
    "reactor.scram": lambda d: f"{ru('Tovarisjtj komandir')}, maskin! Reaktorn har snabbstoppat ({d['cause']}). "
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
    "ice.collision": lambda d: f"{ru('Avarijnaja trevoga')}! Vi har gått in i isen! {d['severity'].capitalize()} skador"
    + (": " + ", ".join(COMPONENT_LABEL[c] for c in d["components"]) if d["components"] else "")
    + (". Vatteninträngning, länsning pågår." if d.get("leak") else ".")
    + " Maskinen stoppad.",
    "bottom.collision": lambda d: f"{ru('Avarijnaja trevoga')}! Vi har gått på grund med {d['where']}! "
    f"{d['severity'].capitalize()} skador: " + ", ".join(COMPONENT_LABEL[c] for c in d["components"])
    + (". Vatteninträngning, länsning pågår." if d.get("leak") else ".")
    + f" Maskinen stoppad. Går upp till {d['back_to']} meter.",
    "bottom.settled": lambda d: f"Vi ligger stilla på botten på {d['depth']} meter, kapten. "
    + ("Klippbotten, det skrapade i skrovet. " if d["kind"] == "klippa"
       else "Mjuk botten, inga skador. ")
    + "Maskinen stoppad, kylpumparna på lågvarv.",
    "net.caught": lambda d: "Kapten! Vi har gått in i ett nät! Det drar i skrovet och propellern "
    "har trasslat in sig, maskinen stoppad. Bojarna på ytan rör sig, de vet var vi är!",
    "bottom.touch": lambda d: f"Vi tog i botten med {d['where']}, kapten. Låg fart, inga skador. "
    f"Går upp till {d['back_to']} meter.",
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
    "fire": lambda d: f"{ru('Avarijnaja trevoga')}! Brand i {d['compartment']}! Avdelningen utrymd och stängd. "
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
    "eng.suggest.sprint": lambda d: "Kapten, maskin. De har oss redan på aktiv sonar, smygandet "
    f"hjälper inte nu. Föreslår turbin och fart {kn(d['speed'])} på {d['depth']:.0f} meter, "
    "där kaviterar vi inte. Djupt och fort bort.",
    "eng.suggest.creep": lambda d: "Kapten, maskin. Med kontakt i närheten föreslår jag "
    "smygmotor, det sänker vårt ljud kraftigt.",
}
phrases.register(PHRASES)


COMPONENT_RU = {"sonar": "гидроакустика", "planes": "рули", "propulsion": "движение",
                "tubes": "торпедные аппараты", "periscope": "перископ", "radio": "радиосвязь"}
SEVERITY_RU = {"lätta": "Лёгкие", "svåra": "Тяжёлые"}
SMOKE_RU = {"lätt": "лёгкое", "besvärande": "заметное", "tät": "сильное",
            "mycket tät": "очень сильное", "livsfarlig": "смертельно опасное"}
ORDINAL_RU = {1: "первый", 2: "второй", 3: "третий", 4: "четвёртый", 5: "пятый", 6: "шестой",
              7: "седьмой", 8: "восьмой", 9: "девятый"}
NOTE_RU = {"snabbstopp": "аварийная защита реактора", "startar": "реактор вводится",
           "ångläcka": "течь парогенератора", "BRAND": "пожар", "skada": "повреждения",
           "lågt": "батарея разряжена", "rök": "задымление"}


def _ru_damage_list(d: dict) -> str:
    comps = ", ".join(COMPONENT_RU[c] for c in d["components"])
    return f"{SEVERITY_RU.get(d['severity'], 'Есть')} повреждения" + (f": {comps}" if comps else "")


def _ru_leak(d: dict) -> str:
    return ". Поступление воды, откачиваем." if d.get("leak") else "."


def _ru_inspected(d: dict) -> str:
    remarks: dict[str, list[int]] = {}
    for n, note in d["remarks"]:
        remarks.setdefault(note, []).append(n)
    if not remarks:
        txt = "Отсеки осмотрены, замечаний нет."
    else:
        txt = "Отсеки осмотрены."
        for note, nos in remarks.items():
            where = "во всех отсеках" if len(nos) == len(ORDINAL_RU) else \
                ", ".join(ORDINAL_RU[n] for n in nos) + (" отсек" if len(nos) == 1 else " отсеки")
            txt += f" {where[:1].upper()}{where[1:]}: {NOTE_RU.get(note, 'замечания')}."
    if d.get("leak"):
        txt += " Поступление воды, откачиваем."
    return txt


RU_PHRASES = {
    "eng.propulsion": lambda d: "Есть, турбина." if d["mode"] == "turbine"
    else "Есть, электромотор. Максимальный ход пять узлов.",
    "eng.reactor.stopping": lambda d: "Есть, глушим реактор. Идём на аккумуляторной батарее, "
    "максимальный ход пять узлов.",
    "eng.reactor.starting": lambda d: "Есть, вводим реактор. Около двадцати минут.",
    "eng.blow": lambda d: "Аварийное продувание! Продуть все цистерны!",
    "eng.inspected": _ru_inspected,
    "reactor.scram": lambda d: f"{R.CAPTAIN}, пульт! Сработала аварийная защита реактора. "
    "Идём на батарее и электромоторе, максимальный ход пять узлов.",
    "reactor.online": lambda d: "Реактор снова в работе.",
    "reactor.leak": lambda d: f"{R.CAPTAIN}, пульт. Течь парогенератора, повышенная радиация в "
    "реакторном отсеке. Ограничиваем ход шестнадцатью узлами, пока устраняем.",
    "reactor.leak_fixed": lambda d: "Течь парогенератора устранена. Полная мощность.",
    "battery": lambda d: "Батарея разряжена, товарищ командир!" if d["level"] == 0
    else f"Заряд батареи {round(d['level'] * 100)} процентов, товарищ командир.",
    "surfaced": lambda d: "Мы в надводном положении!",
    "leak_stopped": lambda d: "Течь заделана.",
    "hull.creak": lambda d: f"Корпус трещит, товарищ командир. {R.count(d['depth'], R.METER)}, "
    "ниже рабочей глубины.",
    "damage": lambda d: f"Аварийная тревога! {_ru_damage_list(d)}{_ru_leak(d)}",
    "ice.collision": lambda d: f"Аварийная тревога! Мы ударились о лёд! {_ru_damage_list(d)}"
    f"{_ru_leak(d)} Машина остановлена.",
    "bottom.collision": lambda d: f"Аварийная тревога! Мы сели на грунт! {_ru_damage_list(d)}"
    f"{_ru_leak(d)} Машина остановлена. Всплываем на {R.count(d['back_to'], R.METER)}.",
    "bottom.touch": lambda d: f"Коснулись грунта, товарищ командир. Малый ход, повреждений нет. "
    f"Всплываем на {R.count(d['back_to'], R.METER)}.",
    "ice.touch": lambda d: "Коснулись ледового киля, товарищ командир. Малый ход, повреждений нет.",
    "shock": lambda d: ("Взрывы рядом, повреждений нет. Малые заряды." if d.get("practice")
                        else "Сильный гидроудар! Повреждений нет." if d["strength"] == "kraftig"
                        else "Взрыв на удалении. Повреждений нет."),
    "fire": lambda d: "Аварийная тревога! Пожар в турбинном отсеке! Отсек покинут и "
    "загерметизирован. Турбина остановлена, идём на электромоторе.",
    "fire.out": lambda d: f"{R.CAPTAIN}, пожар в турбинном отсеке потушен. Но изоляция тлеет, "
    "дым расходится. Нужно вентилироваться, а для этого нужен воздух.",
    "smoke": lambda d: f"{R.CAPTAIN}, пульт. Задымление теперь {SMOKE_RU[_smoke_word(d['level'])]}."
    + (" Людям трудно дышать." if d["level"] >= 0.7 else "")
    + (" Времени у нас мало!" if d["level"] >= 0.85 else ""),
    "vent.stopped": lambda d: "Вентиляция прервана, шахта под водой или подо льдом.",
    "eng.vent.start": lambda d: "Есть, вентилируемся через шахту. Это займёт время."
    if not d.get("surface") else "Есть, люки открыты, вентилируемся.",
    "eng.suggest.vent": lambda d: f"{R.CAPTAIN}, пульт. Задымление {SMOKE_RU[_smoke_word(d['smoke'])]}, "
    "а над нами открытый воздух. Предлагаю провентилироваться.",
    "eng.smoke_no_opening": lambda d: f"{R.CAPTAIN}, пульт. Задымление "
    f"{SMOKE_RU[_smoke_word(d['smoke'])]}, нужно вентилироваться, но полыньи у нас нет. "
    "Надо искать чистую воду.",
    "repaired": lambda d: f"Ремонт закончен: {COMPONENT_RU[d['component']]}.",
    "bottom.settled": lambda d: f"Лежим на грунте, {R.count(d['depth'], R.METER)}, товарищ командир. "
    + ("Скальный грунт, корпус поцарапали. " if d["kind"] == "klippa" else
       "Мягкий грунт, повреждений нет. ")
    + "Машина остановлена, насосы на малых оборотах.",
    "vent.done": lambda d: f"{R.CAPTAIN}, воздух снова чистый. Вентиляция закрыта.",
    "eng.suggest.cavitation": lambda d: f"{R.CAPTAIN}, пульт. Кавитируем, нас слышно далеко. "
    f"Предлагаю ход {R.count(d['speed'], R.KNOT)}.",
    "eng.suggest.restart": lambda d: f"{R.CAPTAIN}, пульт. Предлагаю ввести реактор.",
    "eng.suggest.blow": lambda d: f"{R.CAPTAIN}, пульт! Принимаем воду и тонем, "
    f"{round(d['flooding'])} тонн внутри. Предлагаю аварийное продувание!",
    "eng.suggest.sprint": lambda d: f"{R.CAPTAIN}, пульт. Нас уже держат гидролокатором, тишина "
    f"не поможет. Предлагаю турбину и ход {R.count(d['speed'], R.KNOT)} на глубине "
    f"{R.count(d['depth'], R.METER)}, там не кавитируем. Уходим глубоко и быстро.",
    "eng.suggest.creep": lambda d: f"{R.CAPTAIN}, пульт. Рядом контакт, предлагаю электромотор, "
    "это сильно снизит наш шум.",
}
phrases.register_ru(RU_PHRASES)

SPRINT_DEPTH = 220          # upptäckta: så djupt vi vill springa (under skiktet, över provdjup)
SPRINT_MIN_DEPTH = 100


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
        self._inspect_t: int | None = None     # avdelningarna rapporterar då

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
                    self.game.bus.publish(OwnSoundMade(self.now, "blow"))
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

    # --- systemtavlan ---------------------------------------------------------------
    def system_items(self) -> list:
        own, s = self.own, self.own.sys
        items: list = []
        g = lambda label, text, state=OK, level=None, panel="MASKIN": \
            items.append(Gauge(panel, label, text, state, level))

        reactor_state = {"online": OK, "starting": WARN, "off": OFF, "scram": DANGER}[s.reactor]
        txt = REACTOR_LABEL[s.reactor]
        if s.reactor == "starting":
            txt += f", klar om {max(0, s.reactor_ready_t - self.now) // 60 + 1} min"
        if s.steam_leak:
            txt += ", ångläcka"
            reactor_state = max(reactor_state, WARN, key=SEVERITY.get)
        g("Reaktor", txt, reactor_state)
        prop = "turbin" if s.propulsion == "turbine" else "elmotor (smyg)"
        g("Framdrivning", f"{prop}, högst {kn(own.max_speed())} kn",
          WARN if own.max_speed() <= 0 else INFO)
        g("Batteri", _pct(s.battery), DANGER if s.battery <= 0.1 else
          WARN if s.battery < 0.3 else OK, s.battery)
        g("Tryckluft", "full" if s.hp_air >= 1 else "förbrukad" if s.hp_air <= 0
          else _pct(s.hp_air), WARN if s.hp_air <= 0 else OK, s.hp_air)
        g("Skrov", _pct(s.hull), DANGER if s.hull < 0.5 else WARN if s.hull < 0.9 else OK,
          s.hull)
        if s.flooding > 0.5 or s.leak_rate > 0:
            txt = f"{s.flooding:.0f} ton ombord"
            if s.leak_rate > 0:
                txt += ", läcker"
            g("Vatten", txt, DANGER if s.flooding > TRIM_RESERVE_T else WARN,
              min(1.0, s.flooding / FLOOD_LOSS_T))
        else:
            g("Vatten", "torrt")
        g("Koldioxid", f"{nm(s.co2)} %", DANGER if s.co2 > 3 else WARN if s.co2 > 0.8 else OK)
        if s.fire:
            g("Brand", "i turbinrummet", DANGER)
        if s.smoke > 0.0:
            txt = _smoke_word(s.smoke) + (", ventilerar" if s.ventilating else "")
            g("Rök", txt, DANGER if s.smoke >= 0.7 else WARN if s.smoke >= 0.15 else INFO,
              s.smoke)
        if s.blowing:
            g("Nödblåsning", "pågår", WARN)

        repairing = next((c for c in COMPONENTS if s.health[c] < 1.0), None)
        for c in COMPONENTS:
            h = s.health[c]
            txt = health_word(h) + (", lagas" if c == repairing else "")
            g(COMPONENT_NAME[c], txt, health_state(h), h if h < 1.0 else None, panel="SKADOR")

        for n, name, state, note in self._compartments():
            items.append(Compartment(n, name, state, note))
        items.append(Flooding(s.flooding, FLOOD_LOSS_T, s.leak_rate > 0))
        return items

    def _compartments(self) -> list[tuple[int, str, str, str]]:
        """Avdelningarnas läge ur egna instrument: (nummer, namn, tillstånd, anmärkning)."""
        s = self.own.sys
        notes: dict[int, list[tuple[str, str]]] = {n: [] for n, _ in COMPARTMENTS}
        for c in COMPONENTS:
            if s.health[c] < 1.0:
                notes[COMPONENT_COMPARTMENT[c]].append((health_state(s.health[c]), "skada"))
        if s.reactor == "scram":
            notes[5].append((DANGER, "snabbstopp"))
        elif s.reactor == "off":
            notes[5].append((OFF, "avställd"))
        elif s.reactor == "starting":
            notes[5].append((WARN, "startar"))
        if s.steam_leak:
            notes[5].append((WARN, "ångläcka"))
        if s.fire:
            notes[6].append((DANGER, "BRAND"))
        elif s.propulsion == "electric" or s.reactor != "online":
            notes[6].append((OFF, "stoppad"))
        if s.battery < 0.3:
            notes[2].append((WARN, "lågt"))
        if s.smoke >= SMOKE_LEVELS[0]:              # röken sprider sig i hela båten
            for n in notes:
                notes[n].append((DANGER if s.smoke >= 0.7 else WARN, "rök"))
        out = []
        for n, name in COMPARTMENTS:
            state, note = max(notes[n], key=lambda x: SEVERITY[x[0]], default=(OK, ""))
            out.append((n, name, state, note))
        return out

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
        hunted = self.game.knowledge.hunted(self.now)
        if hunted and (p := self._sprint()) is not None:
            order, data = p
            out.append(Proposal(2, "idle_sprint", "eng.suggest.sprint", order, data, cooldown=600))
        elif not hunted and s.propulsion == "turbine" and not s.on_bottom and \
                self.game.knowledge.threat_held():
            out.append(Proposal(2, "idle_creep", "eng.suggest.creep", "smygmotor"))
        return out

    def _sprint(self) -> tuple[str, dict] | None:
        """Upptäckta: djupt och så fort det går utan kavitation. None om vi redan gör det."""
        own, s, st = self.own, self.own.sys, self.own.state
        if s.on_bottom or s.settle or not own.power:
            return None
        from .navigation import NavigationStation
        depth = SPRINT_DEPTH
        try:
            lim = self.game.station(NavigationStation).depth_limit()
        except KeyError:
            lim = None
        if lim is not None:
            depth = min(depth, lim)
        if depth < SPRINT_MIN_DEPTH:
            return None
        speed = int(acoustics.cavitation_speed(depth)) - 1
        if speed <= 6:
            return None
        if s.propulsion == "turbine" and st.ordered_speed >= speed - 1 and \
                abs(st.ordered_depth - depth) <= 40:
            return None
        parts = [] if abs(st.ordered_depth - depth) <= 40 else [f"djup {depth:.0f}"]
        # alltid med: förslaget levereras med fördröjning, och smygmotor kan ha
        # beordrats under tiden
        parts.append("turbin")
        parts.append(f"fart {speed}")
        return ", ".join(parts), {"speed": speed, "depth": depth}

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
                             "bottom.collision", "bottom.touch", "net.caught",
                             "fire") or (type == "smoke" and data["level"] >= 0.7) or \
                (type == "battery" and data["level"] <= 0.1)
            self.say(type, data, kind="info", alarm=alarm)
            hard = type == "shock" and data.get("strength") == "kraftig" and not data.get("practice")
            if (type in INSPECT_ALERTS or hard) and self._inspect_t is None:
                self._inspect_t = self.now + INSPECT_AFTER_S
        if self._inspect_t is not None and self.now >= self._inspect_t:
            self._inspect_t = None
            remarks = [(n, note) for n, _, state, note in self._compartments()
                       if state in (WARN, DANGER)]
            self.say("eng.inspected", {"remarks": remarks, "leak": s.leak_rate > 0})

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
        hunted = self.game.knowledge.hunted(self.now)
        if hunted and (p := self._sprint()) is not None:
            order, data = p
            self.suggest("sprint", "eng.suggest.sprint", data, order=order, cooldown=600)
        elif not hunted and s.propulsion == "turbine" and not s.on_bottom and \
                self.game.knowledge.tracks and self.game.knowledge.threat_held():
            self.suggest("creep", "eng.suggest.creep", order="smygmotor", cooldown=3600)
