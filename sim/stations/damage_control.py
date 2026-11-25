"""Skadekontrollen (живучесть): maskins folk mot läckor, vatten och fastnade roder. docs/system/besattning.md,
Skadekontrollen.

Stationen läser bara egna instrument (`own`: läckorna, vattnet i avdelningarna, rodren, skrovet) och
föreslår det som hjälper: back när djuprodren fastnat i dykläge, grundare när läckan ger mer än
pumparna tar. Larmen (läcka tätad, avdelning utrymd, rodren fast …) sägs av maskin när de kommer
(`EngineeringStation` tömmer larmkön); fraserna står här.
"""
from __future__ import annotations

import math

from .. import phrases
from .. import russian as R
from ..crew import Role
from ..damage import CAP_T, LEAK_KINDS, inflow_factor
from ..fmt import nm
from ..ownship import BILGE_T_PER_MIN, PERISCOPE_DEPTH, TEST_DEPTH
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
TEST_DEPTH_STEP = 10        # provdjupet sagt igen när det sjunkit så mycket …
TEST_DEPTH_EVERY_S = 90     # … men inte oftare än så …
TEST_DEPTH_BIG_STEP = 30    # … om det inte sjunkit så här mycket


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
    "dc.suggest.leak_up": lambda d: f"{R.CAPTAIN}, механик. Течь больше, чем откачивают насосы. "
    f"Предлагаю глубину {R.count(d['target'], R.METER)}.",
}
phrases.register_ru(RU_PHRASES)


class DamageControlStation(Station):
    """Skadekontrollen: förslag mot fastnade roder och läckor som pumparna inte rår på,
    provdjupet när skrovet tagit skada."""
    role = Role.ENGINEER

    def __init__(self, game):
        super().__init__(game)
        self._test_said = TEST_DEPTH
        self._test_t = -10**9

    def update(self) -> None:
        self._jam_advice()
        self._test_depth_watch()
        self._leak_advice()

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
        pumps = BILGE_T_PER_MIN if s.dmg.bilge_on else 0.0
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
