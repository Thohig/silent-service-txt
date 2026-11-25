"""Maskin: reaktor, framdrivning, batteri, skrov, läckor, luft och skadekontroll."""
from __future__ import annotations

from dataclasses import dataclass

from .. import acoustics, phrases
from ..crew import Role
from ..damage import CAP_T, COMPONENT_COMPARTMENT
from ..events import ChargeHeard, OwnSoundMade
from ..reports import Quality
from ..fmt import fmt_course, kn, nm
from .. import russian as R
from ..russian import ru
from ..orders import CommandSpec, Order, split_orders
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
COMPONENT_NAME = {"sonar": "Sonar", "planes": "Roder", "propulsion": "Framdrivning",
                  "tubes": "Torpedtuber", "periscope": "Periskop", "radio": "Radio"}


def _pct(v: float) -> str:
    return f"{round(v * 100)} %"


def _smoke_word(v: float) -> str:
    return ("lätt" if v < 0.3 else "besvärande" if v < 0.5 else "tät" if v < 0.7
            else "mycket tät" if v < 0.85 else "livsfarlig")


ORDINAL = {1: "första", 2: "andra", 3: "tredje", 4: "fjärde", 5: "femte", 6: "sjätte",
           7: "sjunde", 8: "åttonde", 9: "nionde"}
INSPECT_NOTE = {"BRAND": "brand", "skada": "skador", "lågt": "batteriet lågt", "läcka": "läcka, den tätas",
               "vatten": "vatten i kölsvinet", "utrymd": "halvfull, utrymd och stängd"}
INSPECT_AFTER_S = 60         # avdelningarna rapporterar så här länge efter haverilarmet
INSPECT_SAME_S = 900         # samma anmärkningar som förra inspektionen så nyss: "inget nytt" (jagad frö 3:
                             # samma långa rad sex gånger på 20 min under bomberna)
INSPECT_ALERTS = ("damage", "ice.collision", "bottom.collision", "fire")
GROAN_SAY_S = 180       # skrovknaket under jakt sägs högst så här ofta


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
    if d.get("compartment"):
        txt += f" vid {ORDINAL[d['compartment']]} avdelningen"
    if comps:
        txt += f": {comps}"
    if d.get("leak"):
        txt += ". Vatteninträngning" + (f" i {ORDINAL[d['compartment']]}" if d.get("compartment") else "") \
            + ", skotten stängda"
    return txt + "."


PHRASES = {
    "eng.status": _status,
    "eng.inspected": _inspected,
    "eng.inspected.same": lambda d: "Avdelningarna inspekterade, inget nytt sedan förra inspektionen.",
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
    "broach": lambda d: "Kapten, centralen! Sjön drog upp oss, tornet bröt ytan!",
    "leak_stopped": lambda d: f"Läckan i {ORDINAL[d['compartment']]} avdelningen är tätad."
    if d.get("compartment") else "Läckan är tätad.",
    "hull.creak": lambda d: f"Skrovet knakar, kapten. {d['depth']:.0f} meter, under provdjup.",
    "hull.clatter": lambda d: f"Lösa föremål far i durken, kapten, vi lutar {abs(d['pitch'])}° "
    + ("förut" if d["pitch"] > 0 else "akterut") + ". Det hörs i vattnet."
    + (" Det är den branta vinkeln: vi kommer undan fort, men de kan höra det." if d.get("steep") else "")
    + (f" Trimmen lutar oss {nm(abs(d['trim']))}° av det, trimmaren kan flytta vatten."
       if abs(d.get("trim") or 0) >= 2 else ""),
    "hull.groan": lambda d: "Skrovet knakar när vi går " + ("ned" if d.get("down") else "upp")
    + ", kapten. Det hörs i vattnet. Långsammare djupändring, i låg fart, knakar inte.",
    "damage": _damage,
    "ice.collision": lambda d: f"{ru('Avarijnaja trevoga')}! "
    + ("Vi har backat in i isen! " if d.get("astern") else "Vi har gått in i isen! ")
    + f"{d['severity'].capitalize()} skador"
    + (": " + ", ".join(COMPONENT_LABEL[c] for c in d["components"]) if d["components"] else "")
    + (". Vatteninträngning, länsning pågår." if d.get("leak") else ".")
    + " Maskinen stoppad.",
    "bottom.collision": lambda d: f"{ru('Avarijnaja trevoga')}! "
    + ("Vi har backat på grund! " if d.get("astern") else f"Vi har gått på grund med {d['where']}! ")
    + f"{d['severity'].capitalize()} skador: " + ", ".join(COMPONENT_LABEL[c] for c in d["components"])
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
    "bottom.pressed": lambda d: f"Kapten, vi står fast med {d['where']} mot botten och kommer "
    + ("inte akterut." if d.get("astern") else "inte framåt. Föreslår en annan kurs, bort från land."),
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
    "repaired": lambda d: f"Reparationen av {COMPONENT_LABEL[d['component']]} är klar"
    + (", så gott det går till sjöss." if d.get("partly") else "."),
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
    "eng.suggest.cavitation": lambda d: f"Kapten, maskin. Propellern kaviterar akterut, den tål "
    f"mindre bakåt, vi hörs långt. Föreslår back {kn(d['speed'])} knop." if d.get("astern") else
    f"Kapten, maskin. Vi kaviterar, vi hörs långt. Föreslår fart {kn(d['speed'])} knop.",
    "eng.suggest.restart": lambda d: "Kapten, maskin. Föreslår omstart av reaktorn.",
    "eng.suggest.blow": lambda d: f"Kapten, maskin! Vi tar in vatten och sjunker, "
    f"{d['flooding']:.0f} ton ombord. Föreslår nödblåsning!",
    "eng.suggest.lift": lambda d: f"Kapten, maskin! De bombar oss på botten, de har vårt läge. "
    + (f"Reaktorn står, men föreslår att vi lättar ändå: elmotorn, fart {d['speed']} på {d['depth']:.0f} meter, bort härifrån."
       if d.get("electric") else
       f"Föreslår att vi lättar: turbin och fart {d['speed']} på {d['depth']:.0f} meter, bort härifrån."),
    "eng.blow_confirm": lambda d: "Kapten, maskin. Ingen vatteninträngning och djupet är i ordning. "
    "Nödblåsningen tömmer högtrycksluften och tar oss rakt upp till ytan. Svara ja om vi ska blåsa.",
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
NOTE_RU = {"läcka": "течь, заделываем", "vatten": "вода в трюме", "utrymd": "затоплен наполовину, личный состав вышел",
           "snabbstopp": "аварийная защита реактора", "startar": "реактор вводится",
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


REACTOR_RU = {"online": "в работе", "scram": "сработала аварийная защита", "off": "выведен",
              "starting": "вводится"}


def _ru_pct(x: float) -> str:
    n = round(x * 100)
    return f"{n} {R.plural(n, ('процент', 'процента', 'процентов'))}"


def _ru_status(d: dict) -> str:
    parts = [f"реактор {REACTOR_RU[d['reactor']]}",
             "турбина" if d["propulsion"] == "turbine" else "электромотор",
             f"максимальный ход {R.count(d['max_speed'], R.KNOT)}",
             f"батарея {_ru_pct(d['battery'])}"]
    if d["steam_leak"]:
        parts.append("течь парогенератора")
    parts.append(f"корпус {_ru_pct(d['hull'])}")
    if d["flooding"] > 0.5:
        parts.append(f"внутри {R.count(d['flooding'], R.TON)} воды")
    if d.get("fire"):
        parts.append("пожар в турбинном отсеке")
    if d.get("smoke", 0) > 0.05:
        parts.append(f"задымление {SMOKE_RU[_smoke_word(d['smoke'])]}")
    if d["co2"] > 0.8:
        parts.append(f"углекислый газ {R.dec(d['co2'], ('процент', 'процента', 'процентов'))}")
    damaged = [f"{COMPONENT_RU[c]} {_ru_pct(h)}" for c, h in d["health"].items() if h < 1.0]
    if damaged:
        parts.append("повреждены: " + ", ".join(damaged))
    return "Доклад пульта: " + ", ".join(parts) + "."


def _ru_bump(d: dict) -> str:
    txt = f"{R.CAPTAIN}, упираемся в лёд над нами. "
    if d.get("thin") and d.get("too_fast"):
        txt += "Лёд тонкий, но ход слишком большой, чтобы проломить. "
    elif not d.get("thin"):
        txt += "Лёд слишком толстый, не проломить. "
    return txt + f"Погружаемся на {R.count(d['back_to'], R.METER)}."


RU_PHRASES = {
    "eng.refused": lambda d: f"{R.CAPTAIN}, пульт. Выполнить не могу.",
    "eng.status": _ru_status,
    "air": lambda d: f"Содержание углекислого газа "
    f"{R.dec(d['co2'], ('процент', 'процента', 'процентов'))} и растёт.",
    "eng.suggest.vent_vak": lambda d: f"{R.CAPTAIN}, пульт. Задымление "
    f"{SMOKE_RU[_smoke_word(d['smoke'])]}, нужно вентилироваться. У штурмана полынья {d['no']}, "
    f"пеленг {R.course(d['bearing'])}, около {R.count(d['range'], R.METER)}. Предлагаю идти туда.",
    "ice.bump": _ru_bump,
    "ice.pressing": lambda d: "Рубка упёрлась в тонкий лёд. Давим, около сорока секунд.",
    "ice.broke_through": lambda d: "Проломили лёд!"
    + (" Перископ получил удар." if d.get("damaged") else " Повреждений нет."),
    "net.caught": lambda d: f"{R.CAPTAIN}! Мы вошли в сеть! Сеть тянет корпус, винт намотал, "
    "машина остановлена. Буи на поверхности двигаются, они знают, где мы!",
    "eng.propulsion": lambda d: "Есть, турбина." if d["mode"] == "turbine"
    else "Есть, электромотор. Максимальный ход пять узлов.",
    "eng.reactor.stopping": lambda d: "Есть, глушим реактор. Идём на аккумуляторной батарее, "
    "максимальный ход пять узлов.",
    "eng.reactor.starting": lambda d: "Есть, вводим реактор. Около двадцати минут.",
    "eng.blow": lambda d: "Аварийное продувание! Продуть все цистерны!",
    "eng.inspected": _ru_inspected,
    "eng.inspected.same": lambda d: "Отсеки осмотрены, без изменений.",
    "reactor.scram": lambda d: f"{R.CAPTAIN}, пульт! Сработала аварийная защита реактора. "
    "Идём на батарее и электромоторе, максимальный ход пять узлов.",
    "reactor.online": lambda d: "Реактор снова в работе.",
    "reactor.leak": lambda d: f"{R.CAPTAIN}, пульт. Течь парогенератора, повышенная радиация в "
    "реакторном отсеке. Ограничиваем ход шестнадцатью узлами, пока устраняем.",
    "reactor.leak_fixed": lambda d: "Течь парогенератора устранена. Полная мощность.",
    "battery": lambda d: "Батарея разряжена, товарищ командир!" if d["level"] == 0
    else f"Заряд батареи {round(d['level'] * 100)} процентов, товарищ командир.",
    "surfaced": lambda d: "Мы в надводном положении!",
    "broach": lambda d: f"{R.CAPTAIN}, центральный! Волной подняло, рубка показалась!",
    "leak_stopped": lambda d: "Течь заделана.",
    "hull.groan": lambda d: f"{R.CAPTAIN}, корпус трещит. Нас слышно. Глубину менять медленнее.",
    "hull.clatter": lambda d: f"{R.CAPTAIN}, дифферент {R.dec(abs(d['pitch']), R.DEGREE)} "
    + ("на нос" if d["pitch"] > 0 else "на корму") + ". Незакреплённое падает, нас слышно."
    + (" Это большой дифферент при погружении." if d.get("steep") else "")
    + (" Часть дифферента от дифферентовки." if abs(d.get("trim") or 0) >= 2 else ""),
    "hull.creak": lambda d: f"Корпус трещит, товарищ командир. {R.count(d['depth'], R.METER)}, "
    "ниже рабочей глубины.",
    "damage": lambda d: f"Аварийная тревога! {_ru_damage_list(d)}{_ru_leak(d)}",
    "ice.collision": lambda d: "Аварийная тревога! "
    + ("Ударились кормой о лёд! " if d.get("astern") else "Мы ударились о лёд! ")
    + f"{_ru_damage_list(d)}"
    f"{_ru_leak(d)} Машина остановлена.",
    "bottom.collision": lambda d: "Аварийная тревога! "
    + ("Сели кормой на грунт! " if d.get("astern") else "Мы сели на грунт! ")
    + f"{_ru_damage_list(d)}"
    f"{_ru_leak(d)} Машина остановлена. Всплываем на {R.count(d['back_to'], R.METER)}.",
    "bottom.touch": lambda d: f"Коснулись грунта, товарищ командир. Малый ход, повреждений нет. "
    f"Всплываем на {R.count(d['back_to'], R.METER)}.",
    "bottom.pressed": lambda d: f"{R.CAPTAIN}, упёрлись в грунт, хода нет."
    + ("" if d.get("astern") else " Предлагаю другой курс, от берега."),
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
    + (f"Предлагаю задний ход {R.count(d['speed'], R.KNOT)}." if d.get("astern") else
       f"Предлагаю ход {R.count(d['speed'], R.KNOT)}."),
    "eng.suggest.restart": lambda d: f"{R.CAPTAIN}, пульт. Предлагаю ввести реактор.",
    "eng.suggest.blow": lambda d: f"{R.CAPTAIN}, пульт! Принимаем воду и тонем, "
    f"{round(d['flooding'])} тонн внутри. Предлагаю аварийное продувание!",
    "eng.suggest.lift": lambda d: f"{R.CAPTAIN}, пульт! Бомбят нас на грунте, место наше знают. "
    f"Предлагаю отрываться: {'электромотор' if d.get('electric') else 'турбина'}, "
    f"{R.count(d['speed'], R.KNOT)}, глубина {R.count(d['depth'], R.METER)}.",
    "eng.blow_confirm": lambda d: f"{R.CAPTAIN}, пульт. Поступления воды нет, глубина в норме. "
    "Аварийное продувание выбросит нас на поверхность. Повторите приказ, если продуваем.",
    "eng.suggest.sprint": lambda d: f"{R.CAPTAIN}, пульт. Нас уже держат гидролокатором, тишина "
    f"не поможет. Предлагаю турбину и ход {R.count(d['speed'], R.KNOT)} на глубине "
    f"{R.count(d['depth'], R.METER)}, там не кавитируем. Уходим глубоко и быстро.",
    "eng.suggest.creep": lambda d: f"{R.CAPTAIN}, пульт. Рядом контакт, предлагаю электромотор, "
    "это сильно снизит наш шум.",
}
phrases.register_ru(RU_PHRASES)

TORPEDO_SPEED_S = 300      # så länge efter senaste torpedbäringen gäller farten före tystnaden
SPRINT_DEPTH = 220          # upptäckta: så djupt vi vill springa (under skiktet, över provdjup)
SPRINT_MIN_DEPTH = 100
SPRINT_RUNNING_KN = 10      # så fort på turbinen: vi springer redan
SPRINT_DEEPEST = 290        # ett beordrat djup ned hit duger lika bra (sonars undanmanöver går ofta djupare)
CREEP_AFTER_HUNT_S = 600    # smygmotor föreslås inte förrän jakten varit tyst så här länge
SMOKE_SEARCH_AFTER_VAK_S = 300   # röken: "ingen öppning" sägs inte så nyss efter förslaget om en


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
        self._last_groan = -10**9
        self._inspect_t: int | None = None     # avdelningarna rapporterar då
        self._inspected_last: tuple | None = None   # förra inspektionens anmärkningar och tid


    def intercept(self, order: Order) -> bool:
        """Nödblåsning utan vatten i båten eller djupfara: fråga en gång (`confirm_once`)."""
        if not isinstance(order, EmergencyBlow):
            return False
        s, st = self.own.sys, self.own.state
        danger = s.flooding > 0.5 or s.leak_rate > 0 or s.hull < 0.7 or st.depth > TEST_DEPTH - 20
        if danger or st.depth <= 20:
            return False
        return self.confirm_once("blow", "eng.blow_confirm")

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
                elif not own.start_ventilation(self.masts_free):
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
            items.append(Compartment(n, name, state, note, s.dmg.water[n] / CAP_T[n]))
        items.append(Flooding(s.flooding, FLOOD_LOSS_T, s.leak_rate > 0, s.dmg.closed))
        return items

    def _compartments(self) -> list[tuple[int, str, str, str]]:
        """Avdelningarnas läge ur egna instrument: (nummer, namn, tillstånd, anmärkning)."""
        s = self.own.sys
        notes: dict[int, list[tuple[str, str]]] = {n: [] for n, _ in COMPARTMENTS}
        for c in COMPONENTS:
            if s.health[c] < 1.0:
                notes[COMPONENT_COMPARTMENT[c]].append((health_state(s.health[c]), "skada"))
        dmg = s.dmg
        for leak in dmg.leaks:
            notes[leak.compartment].append((WARN, "läcka"))
        for n, w in dmg.water.items():
            if n in dmg.evacuated:
                notes[n].append((DANGER, "utrymd"))
            elif w >= 0.5:
                notes[n].append((DANGER if w > 0.25 * CAP_T[n] else WARN, "vatten"))
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
        torpedo = self.game.knowledge.torpedo_alarm(self.now, window=TORPEDO_SPEED_S)
        if (cav := self._cavitation_advice()) is not None and not torpedo:
            order, data = cav
            out.append(Proposal(1, "idle_cavitation", "eng.suggest.cavitation", order, data,
                                cooldown=600))
        if s.reactor in ("scram", "off") and s.battery < 0.5:
            out.append(Proposal(1, "idle_restart", "eng.suggest.restart", "starta reaktorn"))
        hunted = self.game.knowledge.hunted(self.now)
        if hunted and (p := self._sprint()) is not None:
            order, data = p
            out.append(Proposal(2, "idle_sprint", "eng.suggest.sprint", order, data, cooldown=600))
        elif not hunted and s.propulsion == "turbine" and not s.on_bottom and \
                not self.own.surfaced and self.game.knowledge.threat_held() and self._hunt_quiet():
            out.append(Proposal(2, "idle_creep", "eng.suggest.creep", "smygmotor"))
        return out

    def _cavitation_advice(self) -> tuple[str, dict] | None:
        """Vi kaviterar under vattnet: order och data för en fart som inte gör det. Inte medan
        maskinen slår om (bromsningen river vattnet, det går över)."""
        st = self.own.state
        if self.own.surfaced or st.reversing:
            return None
        if st.speed <= acoustics.cavitation_speed(st.depth, st.astern) + 0.2:
            return None
        if st.astern:
            safe = max(1, int(acoustics.cavitation_speed(st.depth, True)))
            return f"back {safe}", {"speed": safe, "astern": True}
        # på väg upp: farten som inte kaviterar där vi ska vara (sundet: fart 12 på väg till 90 m,
        # där gränsen är 9,6)
        safe = max(3.0, int(acoustics.cavitation_speed(min(st.depth, st.ordered_depth))))
        return f"fart {safe}", {"speed": safe}

    def vetoes(self, order: str) -> bool:
        """Smygmotor föreslås inte när de har oss: maskin uppdateras före sonar, och förslaget som
        gjordes samma sekund som jakten började kom efter 'de har troligen kontakt med oss' (jagad
        frö 41: smygmotor, och 8 s senare turbin och sprint). Sonars tysta undanmanöver för en torped
        nära har fler delar och släpps igenom. Turbin föreslås inte när reaktorn inte är i drift."""
        if not self.own.power and any(p.strip().lower() == "turbin" for p in split_orders(order)):
            return True     # reaktorn är inte i drift (snabbstopp efter förslaget: jagad frö 61)
        return order.strip().lower() == "smygmotor" and self.game.knowledge.hunted(self.now)

    def _hunt_quiet(self) -> bool:
        """Har jakten varit tyst länge nog för att smyga igen? (Jakttecknen kommer och går; utan
        väntan föreslog maskin turbin och 36 s senare smygmotor.)"""
        if self.game.knowledge.hunted(self.now):
            self._hunted_t = self.now
        return self.now - getattr(self, "_hunted_t", -10**9) >= CREEP_AFTER_HUNT_S

    def _sprint(self, lift: bool = False) -> tuple[str, dict] | None:
        """Upptäckta: djupt och så fort det går utan kavitation. None om vi redan gör det.
        lift: vi ligger på botten och de bombar oss där: lätta och gå."""
        own, s, st = self.own, self.own.sys, self.own.state
        if (s.on_bottom or s.settle) and not lift or not own.power and not lift:
            return None
        from .navigation import NavigationStation
        depth = SPRINT_DEPTH
        try:
            lim = self.game.station(NavigationStation).depth_limit()
        except KeyError:
            lim = None
        lim = self.hull_depth() if lim is None else min(lim, self.hull_depth())    # skrovets skador
        depth = min(depth, lim)
        if depth < SPRINT_MIN_DEPTH:
            return None
        deepest = min(SPRINT_DEEPEST, lim) if lim is not None else SPRINT_DEEPEST
        depth_ok = depth - 40 <= st.ordered_depth <= max(deepest, depth)
        if depth_ok:
            depth = st.ordered_depth            # djupare duger: farten räknas där vi ska vara
        if not own.power:
            # reaktorn stoppad, på botten och bombade: lätta ändå och smyg bort på elmotorn (krig frö 4:
            # snabbstopp av tryckvågen, och vi låg kvar på botten i 20 min tills de sänkte oss)
            speed = min(int(acoustics.cavitation_speed(depth)) - 1, int(own.max_speed()))
            if speed < 2:
                return None
            parts = [] if depth_ok else [f"djup {depth:.0f}"]
            return ", ".join(parts + [f"fart {speed}"]), {"speed": speed, "depth": depth, "electric": True}
        # inte fortare än turbinen orkar med skadorna (krig-kort frö 20: fart 11, högsta 9,8)
        speed = min(int(acoustics.cavitation_speed(depth)) - 1, int(own.turbine_max_speed()))
        if speed <= 6:
            return None
        # redan djupt och fort på turbinen: ett par knop till på ett nytt djup är inget nytt förslag
        # (krig-kort: sprint åtta gånger på 90 min, varje gång sonars undanmanöver bytte djup)
        if s.propulsion == "turbine" and st.ordered_speed >= min(speed - 1, SPRINT_RUNNING_KN) and depth_ok:
            return None
        parts = [] if depth_ok else [f"djup {depth:.0f}"]
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
        if own.state.depth <= PERISCOPE_DEPTH and self.masts_free:
            self.suggest("vent", "eng.suggest.vent", {"smoke": s.smoke}, order="ventilera",
                         cooldown=120, alarm=alarm)
            return
        from .navigation import NavigationStation
        try:
            nav = self.game.station(NavigationStation)
        except KeyError:
            return
        if nav.vak is not None or own.state.ordered_depth <= PERISCOPE_DEPTH:
            return          # redan på väg till en öppning eller upp: ventilera där uppe
        sug = self.game.active_suggestion()
        if sug is not None and any(p in ("ytläge", "periskopdjup") for p in split_orders(sug[0])):
            return          # navigatören har just föreslagit upp genom öppningen vi står under (arktis-kort
                            # frö 3: maskins "gå till öppning 4" skrev över det, och vi letade vidare i röken)
        o = nav.best_opening() if nav.under_ice() else None
        if o is not None:
            self.suggest("vent_vak", "eng.suggest.vent_vak", {"smoke": s.smoke, **nav.opening_data(o)},
                         order="vak", cooldown=600, alarm=alarm, quality=o.quality(self.now))
        elif nav.under_ice() and self.now - self._suggested.get("vent_vak", -10**9) > SMOKE_SEARCH_AFTER_VAK_S:
            # (inte strax efter att vi föreslog en öppning: den har bara blivit lite osäkrare sedan dess)
            self.suggest("smoke_search", "eng.smoke_no_opening", {"smoke": s.smoke},
                         order="fart 5, djup 60", cooldown=900, alarm=alarm)

    def _charge_felt(self, type: str, data: dict) -> None:
        """Det maskin känner av sjunkbomberna (KV2): skador eller en kraftig tryckväg är en skarp
        laddning nära, säkert; små smällar nära är signalladdningar (gott omdöme: man hör skillnad på
        ett kilo och hundrafemtio); en avlägsen detonation är skarp men inte nära oss."""
        damage = False
        if type == "damage" and data.get("cause") == "charge":
            felt, damage = (True, Quality.SAKER, True), True
        elif type == "shock":
            if data.get("practice"):
                felt = (False, Quality.GOD, data.get("strength") == "kraftig")
            elif data.get("strength") == "kraftig":
                felt = (True, Quality.SAKER, True)
            else:
                felt = (True, Quality.GOD, False)
        else:
            return
        self.game.bus.publish(ChargeHeard(self.now, *felt, "maskin", damage=damage))

    def update(self) -> None:
        own, s = self.own, self.own.sys
        while s.alerts:
            type, data = s.alerts.pop(0)
            if type == "shock":
                if self.now - self._last_shock < 15:
                    continue
                self._last_shock = self.now
            if type == "hull.groan":
                # knaket hörs alltid ombord; maskin säger det bara när någon kan lyssna
                if not self.game.knowledge.hunted(self.now) or \
                        self.now - self._last_groan < GROAN_SAY_S:
                    continue
                self._last_groan = self.now
            alarm = type in ("reactor.scram", "damage", "surfaced", "broach", "ice.collision", "ice.bump",
                             "bottom.collision", "bottom.touch", "bottom.pressed", "net.caught",
                             "fire") or (type == "smoke" and data["level"] >= 0.7) or \
                (type == "battery" and data["level"] <= 0.1)
            self.say(type, data, kind="info", alarm=alarm)
            if type == "hull.clatter":              # plottets blyerts och sonarvyns marginal
                self.game.bus.publish(OwnSoundMade(self.now, "clatter"))
            self._charge_felt(type, data)
            hard = type == "shock" and data.get("strength") == "kraftig" and not data.get("practice")
            if (type in INSPECT_ALERTS or hard) and self._inspect_t is None:
                self._inspect_t = self.now + INSPECT_AFTER_S
        if self._inspect_t is not None and self.now >= self._inspect_t:
            self._inspect_t = None
            remarks = [(n, note) for n, _, state, note in self._compartments()
                       if state in (WARN, DANGER)]
            found = (remarks, s.leak_rate > 0)
            if remarks and self._inspected_last is not None and found == self._inspected_last[0] and \
                    self.now - self._inspected_last[1] <= INSPECT_SAME_S:
                self.say("eng.inspected.same", {})
            else:
                self.say("eng.inspected", {"remarks": remarks, "leak": s.leak_rate > 0})
            self._inspected_last = (found, self.now)

        for m in self.game.crew.values():           # röken påverkar alla ombord
            m.traits["smoke"] = s.smoke
        self._smoke_advice()

        st = own.state
        # i ytläge hörs vi ändå som ett ytfartyg: kavitationen spelar ingen roll; med en torped
        # i vattnet är farten viktigare än ljudet
        torpedo = self.game.knowledge.torpedo_alarm(self.now, window=TORPEDO_SPEED_S)
        if (cav := self._cavitation_advice()) is not None and not torpedo:
            order, data = cav
            self.suggest("cavitation", "eng.suggest.cavitation", data, order=order, cooldown=600)
        if s.reactor in ("scram", "off") and (s.battery < 0.5 or s.reactor == "scram"):
            self.suggest("restart", "eng.suggest.restart", order="starta reaktorn",
                         cooldown=900 if s.reactor == "scram" else 1800)
        if s.flooding > TRIM_RESERVE_T and st.depth > 20 and not s.blowing and s.hp_air > 0:
            self.suggest("blow", "eng.suggest.blow", {"flooding": s.flooding},
                         order="nödblåsning", cooldown=120, alarm=True)
        hunted = self.game.knowledge.hunted(self.now)
        if hunted:
            self._hunted_t = self.now
        if self.game.knowledge.torpedo_alarm(self.now) or self.game.knowledge.doors_t >= self.now - 60:
            pass                            # torped i vattnet: sonars undanmanöver gäller
        elif hunted and s.on_bottom and self.game.knowledge.charged_close(self.now, 120) and \
                (p := self._sprint(lift=True)) is not None:
            order, data = p
            self.suggest("lift", "eng.suggest.lift", data, order=order, cooldown=300, alarm=True)
        elif hunted and (p := self._sprint()) is not None:
            order, data = p
            self.suggest("sprint", "eng.suggest.sprint", data, order=order, cooldown=600)
        # i ytläge syns vi ändå: smygmotorn hjälper inte
        elif not hunted and s.propulsion == "turbine" and not s.on_bottom and \
                not own.surfaced and self.game.knowledge.tracks and \
                self.game.knowledge.threat_held() and self._hunt_quiet():
            self.suggest("creep", "eng.suggest.creep", order="smygmotor", cooldown=3600)
