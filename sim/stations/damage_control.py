"""Skadekontrollen (живучесть): maskins folk mot läckor, vatten och fastnade roder. docs/system/besattning.md,
Skadekontrollen.

Stationen läser bara egna instrument (`own`: läckorna, vattnet i avdelningarna, rodren, skrovet) och
föreslår det som hjälper: back när djuprodren fastnat i dykläge, grundare när läckan ger mer än
pumparna tar. Larmen (läcka tätad, avdelning utrymd, rodren fast …) sägs av maskin när de kommer
(`EngineeringStation` tömmer larmkön); fraserna står här.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import phrases
from .. import russian as R
from ..crew import Role
from ..damage import CAP_T, LEAK_KINDS, REPAIR_QUIET_F, bilge_capacity, inflow_factor, repairable
from ..events import OwnSoundMade
from ..fmt import nm
from ..orders import CommandSpec, Order
from ..ownship import COMPONENT_LABEL, COMPONENTS, PERISCOPE_DEPTH, REPAIR_S, TEST_DEPTH
from ..russian import ru
from .base import Station

ORDINAL = {1: "första", 2: "andra", 3: "tredje", 4: "fjärde", 5: "femte", 6: "sjätte",
           7: "sjunde", 8: "åttonde", 9: "nionde"}
ORDINAL_RU = {1: "первом", 2: "втором", 3: "третьем", 4: "четвёртом", 5: "пятом", 6: "шестом",
              7: "седьмом", 8: "восьмом", 9: "девятом"}
ORDINAL_RU_NOM = {1: "первый", 2: "второй", 3: "третий", 4: "четвёртый", 5: "пятый", 6: "шестой",
                  7: "седьмой", 8: "восьмой", 9: "девятый"}
KIND_SV = {"packbox": "packboxen", "rör": "rörgenomföringen", "svetsfog": "svetsfogen", "spricka": "sprickan"}
KIND_RU = {"packbox": "сальник", "rör": "забортный трубопровод", "svetsfog": "сварной шов",
           "spricka": "трещина"}

JAM_BACK_KN = 5             # rodren fast i dykläge: så mycket back
LEAK_UP_MIN_DEPTH = 60      # grundare än så föreslås inte "grundare för läckans skull"
LEAK_UP_FLOOR = 40          # och inte upp förbi detta
LEAK_UP_MARGIN = 0.2        # ton/min mer än pumparna tar innan det är värt att gå upp
LEAK_UP_EVERY_S = 600
BILGE_HUSH_DANGER_T = 8.0   # tystnad i båten: pumparna står tills det är så mycket vatten
BILGE_HOLD_DANGER_T = 15.0  # "läns stopp": pumparna står tills det är så mycket
BILGE_SUGGEST_T = 3.0       # tystnad och så mycket vatten som stiger: föreslå länsning
BILGE_SUGGEST_EVERY_S = 300
TEST_DEPTH_STEP = 10        # provdjupet sagt igen när det sjunkit så mycket …
TEST_DEPTH_EVERY_S = 90     # … men inte oftare än så …
TEST_DEPTH_BIG_STEP = 30    # … om det inte sjunkit så här mycket


@dataclass(frozen=True)
class Pump(Order):
    """länsa (on=True: pumparna går också i tystnad, tills båten är länsad) / läns stopp (on=False:
    pumparna står utom i fara)."""
    on: bool = True
    STANDING = True


@dataclass(frozen=True)
class Repair(Order):
    """reparera X: laga X först. Utan X: rapport om vad som lagas och i vilken ordning."""
    component: str | None = None


REPAIR_WORDS = {"planes": "roder|rodren|rodret|djuproder|djuprodren|djuprodret",
                "propulsion": "framdrivning|framdrivningen|maskin|maskinen|axel|axeln|propeller|propellern",
                "sonar": "sonar|sonaren|hydrofon|hydrofonerna",
                "tubes": "tuber|tuberna|torpedtuber|torpedtuberna",
                "periscope": "periskop|periskopet",
                "radio": "radio|radion|antenn|antennen"}
REPAIR_ORDER = ("planes", "propulsion", "sonar", "tubes", "periscope", "radio")   # maskins ordning
REPAIR_ORDER_HUNTED = ("propulsion", "planes", "sonar", "tubes", "periscope", "radio")
COMPONENT_RU = {"sonar": "гидроакустика", "planes": "горизонтальные рули", "propulsion": "главный двигатель",
                "tubes": "торпедные аппараты", "periscope": "перископ", "radio": "радиостанция"}
HEAVY_PLANES_T = 2.0        # så tung båt (som rodren inte bär): rodren först


def _repair_component(m) -> Repair:
    word = (m.group(1) or "").strip().lower()
    for c, pat in REPAIR_WORDS.items():
        if word and any(word == w for w in pat.split("|")):
            return Repair(c)
    return Repair(None)


def where(n: int) -> str:
    return f"{ORDINAL[n]} avdelningen"


PHRASES = {
    "dc.planes_jammed": lambda d: f"{ru('Avarijnaja trevoga')}! Djuprodren har fastnat i "
    + ("dykläge, vi går ned med farten!" if d["down"] else "stigläge, vi går upp med farten!")
    + " Kopplar om till handstyrning, en och en halv minut.",
    "dc.planes_manual": lambda d: "Djuprodren på handstyrning, kapten. De tar sämre tills de är lagade.",
    "dc.suggest.jam": lambda d: "Kapten, maskin! Rodren står i dykläge: föreslår "
    f"back {d['speed']}, då bromsar vi och slutar sjunka." if d["down"] else
    "Kapten, maskin! Rodren står i stigläge: föreslår stopp, utan fart drar de oss inte upp.",
    "dc.test_depth": lambda d: f"Kapten, maskin. Skrovet är skadat: räkna med provdjup {d['depth']} meter.",
    "dc.evacuated": lambda d: f"{ru('Tovarisjtj komandir')}! {where(d['compartment']).capitalize()} är halvfull. "
    "Folket har gått ut och stängt skottet efter sig, läckan där tätas inte längre.",
    "dc.remanned": lambda d: f"Vattnet i {where(d['compartment'])} är nere, kapten. Folket är inne igen.",
    "dc.leak_held": lambda d: f"{KIND_SV[d['kind']].capitalize()} i {where(d['compartment'])} är kilad och "
    "stöttad, kapten. Den läcker kvar, mindre ju grundare vi går.",
    "dc.bulkheads_open": lambda d: "Läckorna är tätade och båten länsad, kapten. Skotten öppnas.",
    "dc.bilge.on": lambda d: f"{ru('Jest')}, länsar. Pumparna hörs." if d["water"] > 0.05
    else f"{ru('Jest')}. Båten är torr, pumparna står klara.",
    "dc.bilge.off": lambda d: f"{ru('Jest')}, länspumparna stopp. Jag startar dem bara om vattnet blir farligt.",
    "dc.bilge.hushed": lambda d: f"Kapten, maskin. Länspumparna stoppade för tystnaden, {nm(d['water'])} ton "
    "i kölsvinet.",
    "dc.bilge.danger": lambda d: f"Kapten, maskin! {nm(d['water'])} ton vatten, länspumparna går ändå.",
    "dc.bilge.done": lambda d: "Båten är länsad, kapten. Pumparna står.",
    "dc.suggest.bilge": lambda d: f"Kapten, maskin. {nm(d['water'])} ton vatten i kölsvinet och det stiger. "
    "Ber att få länsa, pumparna hörs.",
    "dc.repair.start": lambda d: f"Kapten, maskin. Vi lagar {COMPONENT_LABEL[d['component']]}"
    + (" tyst, för tystnaden: det tar dubbelt så lång tid" if d.get("quiet") else ", det hörs")
    + f", cirka {d['minutes']} minuter." + (f" Sedan {d['next']}." if d.get("next") else ""),
    "dc.repair.ack": lambda d: f"{ru('Jest')}, {COMPONENT_LABEL[d['component']]} först." if d.get("component")
    else "Kapten, inget att laga." if not d.get("plan") else
    "Kapten, vi lagar " + ", sedan ".join(d["plan"]) + ".",
    "dc.repair.cannot": lambda d: f"Kapten, {COMPONENT_LABEL[d['component']]} "
    + ("står under vatten, ingen kommer åt dem." if d.get("flooded")
       else "är lagade så gott det går till sjöss." if d.get("as_good") else "är hela."),
    "dc.suggest.repair_planes": lambda d: "Kapten, maskin. Vi sjunker och rodren bär inte: föreslår att vi "
    "lagar rodren först.",
    "dc.suggest.leak_up": lambda d: f"Kapten, maskin. Läckan ger {nm(d['rate'])} ton i minuten på "
    f"{d['depth']} meter, mer än pumparna tar. Föreslår djup {d['target']}: "
    + ("där tar pumparna den." if d.get("enough") else "där läcker det mindre."),
}
phrases.register(PHRASES)

RU_PHRASES = {
    "dc.planes_jammed": lambda d: "Аварийная тревога! Заклинило горизонтальные рули "
    + ("на погружение!" if d["down"] else "на всплытие!") + " Переходим на ручное управление.",
    "dc.planes_manual": lambda d: "Горизонтальные рули на ручном управлении.",
    "dc.suggest.jam": lambda d: f"{R.CAPTAIN}, механик! Рули на погружение. Предлагаю "
    f"назад {R.count(d['speed'], R.KNOT)}." if d["down"] else
    f"{R.CAPTAIN}, механик! Рули на всплытие. Предлагаю стоп.",
    "dc.test_depth": lambda d: f"{R.CAPTAIN}, механик. Корпус повреждён, рабочая глубина "
    f"{R.count(d['depth'], R.METER)}.",
    "dc.evacuated": lambda d: f"{R.CAPTAIN}! {ORDINAL_RU_NOM[d['compartment']].capitalize()} отсек "
    "наполовину затоплен, личный состав вышел, переборка задраена.",
    "dc.remanned": lambda d: f"Вода в {ORDINAL_RU[d['compartment']]} отсеке откачана, личный состав вернулся.",
    "dc.leak_held": lambda d: f"{KIND_RU[d['kind']].capitalize()} в {ORDINAL_RU[d['compartment']]} отсеке "
    "заделан временно, течь остаётся.",
    "dc.bulkheads_open": lambda d: "Течи заделаны, вода откачана. Отдраиваем переборки.",
    "dc.bilge.on": lambda d: "Есть, откачиваем. Насосы слышно." if d["water"] > 0.05
    else "Есть. Трюм сухой.",
    "dc.bilge.off": lambda d: "Есть, осушительные насосы стоп.",
    "dc.bilge.hushed": lambda d: f"{R.CAPTAIN}, механик. Осушительные насосы остановлены для тишины, "
    f"в трюме {R.dec(d['water'], R.TON)}.",
    "dc.bilge.danger": lambda d: f"{R.CAPTAIN}, механик! {R.dec(d['water'], R.TON)} воды, запускаю насосы.",
    "dc.bilge.done": lambda d: "Трюм осушен, насосы остановлены.",
    "dc.suggest.bilge": lambda d: f"{R.CAPTAIN}, механик. В трюме {R.dec(d['water'], R.TON)} воды, "
    "прибывает. Прошу разрешения откачивать.",
    "dc.repair.start": lambda d: f"{R.CAPTAIN}, механик. Ремонтируем: {COMPONENT_RU[d['component']]}"
    + (", тихо." if d.get("quiet") else "."),
    "dc.repair.ack": lambda d: f"Есть, {COMPONENT_RU[d['component']]} в первую очередь." if d.get("component")
    else "Ремонтировать нечего." if not d.get("plan") else "Есть.",
    "dc.repair.cannot": lambda d: f"{R.CAPTAIN}, {COMPONENT_RU[d['component']]}: "
    + ("отсек затоплен." if d.get("flooded") else "сделали что могли." if d.get("as_good") else "исправно."),
    "dc.suggest.repair_planes": lambda d: f"{R.CAPTAIN}, механик. Проваливаемся, рули не держат. Предлагаю "
    "ремонтировать рули в первую очередь.",
    "dc.suggest.leak_up": lambda d: f"{R.CAPTAIN}, механик. Течь больше, чем откачивают насосы. "
    f"Предлагаю глубину {R.count(d['target'], R.METER)}.",
}
phrases.register_ru(RU_PHRASES)


class DamageControlStation(Station):
    """Skadekontrollen: förslag mot fastnade roder och läckor som pumparna inte rår på,
    provdjupet när skrovet tagit skada."""
    role = Role.ENGINEER
    COMMANDS = [
        CommandSpec(r"länsa|lansa|länsa båten|lansa baten|starta länspumparna|starta lanspumparna",
                    lambda m: Pump(True), "länsa"),
        CommandSpec(r"läns stopp|lans stopp|stoppa länspumparna|stoppa lanspumparna|länsa inte|lansa inte",
                    lambda m: Pump(False), "läns stopp"),
        CommandSpec(r"(?:reparera|laga)(?: (" + "|".join(REPAIR_WORDS.values()) + r"))?(?: först| forst)?",
                    _repair_component, "reparera roder"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.bilge_mode = "auto"         # auto (tystnad stänger av), on (kaptenen: länsa), hold (läns stopp)
        self._hushed_said = False
        self._danger_said = False
        self._last_water = 0.0
        self.repair_first: str | None = None    # kaptenens order: det här först
        self._repair_said: str | None = None
        self._test_said = TEST_DEPTH
        self._test_t = -10**9

    def on_order(self, order: Order) -> None:
        if isinstance(order, Repair):
            c = order.component
            if c is None:
                self.say("dc.repair.ack", {"plan": [COMPONENT_LABEL[x] for x in self._plan()]}, kind="ack")
            elif not repairable(self.own, c):
                s = self.own.sys
                self.say("dc.repair.cannot", {"component": c,
                                              "flooded": s.health[c] < s.dmg.cap.get(c, 1.0),
                                              "as_good": s.health[c] < 1.0}, kind="ack")
            else:
                self.repair_first = c
                self.say("dc.repair.ack", {"component": c}, kind="ack")
                self._repair_said = None if self.own.sys.dmg.repair != c else c
            return
        if isinstance(order, Pump):
            self.bilge_mode = "on" if order.on else "hold"
            self._danger_said = False
            self.say("dc.bilge.on" if order.on else "dc.bilge.off", {"water": self.own.sys.flooding}, kind="ack")
            self._bilge()

    def _plan(self) -> list[str]:
        """Det som går att laga, i den ordning vi lagar det: kaptenens först, sedan maskins (rodren först
        om båten är tung och de inte bär, framdrivningen först under jakt)."""
        hunted = self.game.knowledge.hunted(self.now)
        order = list(REPAIR_ORDER_HUNTED if hunted else REPAIR_ORDER)
        if self._planes_urgent():
            order.remove("planes")
            order.insert(0, "planes")
        if self.repair_first in order:
            order.remove(self.repair_first)
            order.insert(0, self.repair_first)
        return [c for c in order if repairable(self.own, c)]

    def _planes_urgent(self) -> bool:
        s = self.own.sys
        return s.dmg.planes_jam != 0 or (repairable(self.own, "planes") and abs(s.trim.free_t) >= HEAVY_PLANES_T)

    def _repair(self) -> None:
        own, dmg = self.own, self.own.sys.dmg
        plan = self._plan()
        target = plan[0] if plan else None
        if self.repair_first is not None and not repairable(own, self.repair_first):
            self.repair_first = None
        dmg.repair = target
        dmg.repair_quiet = self._hushed()
        if dmg._bang_t == self.now:
            self.game.bus.publish(OwnSoundMade(self.now, "repair"))
        if target is not None and target != self._repair_said:
            self._repair_said = target
            left = (own.sys.dmg.cap.get(target, 1.0) - own.sys.health[target]) * REPAIR_S
            if dmg.repair_quiet:
                left /= REPAIR_QUIET_F
            self.say("dc.repair.start", {"component": target, "quiet": dmg.repair_quiet,
                                         "minutes": max(1, round(left / 60)),
                                         "next": COMPONENT_LABEL[plan[1]] if len(plan) > 1 else None})
        elif target is None:
            self._repair_said = None
        if self.repair_first not in (None, "planes") and self._planes_urgent():
            self.suggest("repair_planes", "dc.suggest.repair_planes", {}, order="reparera roder",
                         cooldown=300, alarm=True)

    def order_in_force(self, order: Order) -> bool | None:
        if isinstance(order, Repair) and order.component is not None:
            return self.repair_first == order.component
        if isinstance(order, Pump):
            return self.bilge_mode == ("on" if order.on else "hold")
        return None

    def update(self) -> None:
        self._bilge()
        self._repair()
        self._jam_advice()
        self._test_depth_watch()
        self._leak_advice()

    def _hushed(self) -> bool:
        from .officer import OfficerStation
        try:
            return self.game.station(OfficerStation).hushed
        except KeyError:
            return False

    def _bilge(self) -> None:
        """Länspumparna: på som standard; tystnad i båten stänger av dem tills vattnet blir farligt
        (`länsa` kör dem ändå); `läns stopp` stänger av dem utom i fara."""
        dmg, water = self.own.sys.dmg, self.own.sys.flooding
        rising = water > self._last_water + 1e-6
        self._last_water = water
        if self.bilge_mode == "on":
            on = True
            if water <= 0.05:
                self.bilge_mode = "auto"
                self.say("dc.bilge.done", {})
        elif self.bilge_mode == "hold":
            on = water >= BILGE_HOLD_DANGER_T
        else:
            hushed = self._hushed()
            on = not hushed or water >= BILGE_HUSH_DANGER_T
            if hushed and not on and water > 0.5 and not self._hushed_said:
                self._hushed_said = True
                self.say("dc.bilge.hushed", {"water": water})
            if not hushed:
                self._hushed_said = False
            if hushed and not on and rising and water >= BILGE_SUGGEST_T:
                self.suggest("bilge", "dc.suggest.bilge", {"water": water}, order="länsa",
                             cooldown=BILGE_SUGGEST_EVERY_S)
        danger = self.bilge_mode != "on" and on and water >= min(BILGE_HUSH_DANGER_T, BILGE_HOLD_DANGER_T) and \
            (self.bilge_mode == "hold" or self._hushed())
        if danger and not self._danger_said:
            self._danger_said = True
            self.say("dc.bilge.danger", {"water": water}, alarm=True)
        elif not danger:
            self._danger_said = False
        dmg.bilge_on = on

    def _jam_advice(self) -> None:
        dmg, st = self.own.sys.dmg, self.own.state
        if not dmg.planes_jam or st.speed < 2 or st.astern and dmg.planes_jam < 0:
            return
        down = dmg.planes_jam > 0 and not st.astern
        if down:
            self.suggest("jam", "dc.suggest.jam", {"down": True, "speed": JAM_BACK_KN},
                         order=f"back {JAM_BACK_KN}", cooldown=60, alarm=True)
        else:
            self.suggest("jam", "dc.suggest.jam", {"down": False}, order="stopp", cooldown=60, alarm=True)

    def _test_depth_watch(self) -> None:
        """Provdjupet när skrovet tagit skada: när det sjunkit 10 m, inte oftare än var 90:e s (under
        bomberna sjönk det tre gånger på tio sekunder) om det inte sjunkit 30 m."""
        test = self.own.test_depth()
        drop = self._test_said - test
        if drop >= TEST_DEPTH_BIG_STEP or drop >= TEST_DEPTH_STEP and self.now - self._test_t >= TEST_DEPTH_EVERY_S:
            self._test_said, self._test_t = test, self.now
            self.say("dc.test_depth", {"depth": int(test // 10 * 10)}, alarm=True)

    def _leak_advice(self) -> None:
        """Läckan ger mer än pumparna tar: föreslå så grunt att de tar den (inflödet med roten ur
        trycket). Inte medan fienden har oss (vakthavande säger ändå nej till uppåt då)."""
        own, s, st = self.own, self.own.sys, self.own.state
        if st.depth < LEAK_UP_MIN_DEPTH or not s.dmg.leaks or own.surfaced:
            return
        pumps = bilge_capacity(st.depth) if s.dmg.bilge_on else 0.0
        # bara det som läcker kvar: en spricka som kilats, en läcka i en utrymd avdelning (de andra tätas snart)
        rate = sum(lk.rate(st.depth) for lk in s.dmg.leaks
                   if (lk.held or lk.compartment in s.dmg.evacuated) and not s.dmg.water[lk.compartment] >=
                   CAP_T[lk.compartment])
        if rate <= pumps + LEAK_UP_MARGIN or self.game.knowledge.hunted(self.now):
            return
        # rate(d) = rate · √(1 + d/10) / √(1 + D/10); sök d där rate(d) ≤ pumparna
        f = (pumps / rate) ** 2 * inflow_factor(st.depth) ** 2 if pumps > 0 else 0.0
        target = 10.0 * (f - 1.0)
        target = max(LEAK_UP_FLOOR, int(math.floor(target / 10.0) * 10))
        if target >= st.depth - 20 or target <= PERISCOPE_DEPTH:
            return
        enough = rate * inflow_factor(target) / inflow_factor(st.depth) <= pumps
        self.suggest("leak_up", "dc.suggest.leak_up",
                     {"rate": rate, "depth": round(st.depth), "target": target, "enough": enough},
                     order=f"djup {target}", cooldown=LEAK_UP_EVERY_S)


__all__ = ["DamageControlStation", "LEAK_KINDS"]
