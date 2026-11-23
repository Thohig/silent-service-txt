"""Kärnvapenrådet (KV4–KV5): tre nycklar till kärnladdningen.

Förebild: B-59 den 27 oktober 1962. Kaptenen beordrar `kärnvapenråd`; zampoliten (замполит)
och starpom kommer till centralen och säger ja eller nej efter krigsbedömningen
(`sim/war.py`, bara det besättningen vet). Säger båda ja vrids nycklarna: kärnladdningen är
skarp `ARM_S` sekunder och skjuts på kaptenens vanliga order, en gång. Säger någon nej förblir
den säkrad; starpom föreslår då något annat (aldrig att skjuta). Rådet hålls igen tidigast efter
`AGAIN_S`, eller så snart bedömningen ändrats (nytt telegram, nya bomber).

Stationen läser inte världen: den har kunskapen och torpedrummets tuber (egna instrument).
Torpedrummet frågar `armed()` före varje skott med T-5.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..fmt import minutes
from .. import phrases
from .. import russian as R
from ..crew import Role
from ..events import CouncilHeld
from ..orders import CommandSpec, Order
from ..reports import Quality
from ..systems import DANGER, INFO, OK, WARN, Gauge
from ..war import WarAssessment, assess, starpom_vote, zampolit_vote
from .base import Station

GATHER_S = 30                # zampoliten och starpom kommer till centralen
ARM_S = 600                  # nycklarna gäller så länge
AGAIN_S = 300                # rådet hålls inte oftare om inget ändrats
VERDICT_DELAY_S = 10         # torpedrummets besked kommer efter zampolitens och starpoms


@dataclass(frozen=True)
class CallCouncil(Order):
    pass


ORDER_TEXT = {"forbidden": "ordern förbjuder kärnladdningen", "order_only": "bara på order från Moskva",
              "conditional": "stabens villkor: om vi angrips med skarpa sjunkbomber",
              "authorized": "Moskva har gett tillstånd"}


def _q(d: dict) -> str:
    return Quality(d["q"]).label


def _charges(d: dict) -> str:
    if d["attacked"]:
        return f"vi angrips med skarpa sjunkbomber (bedömningen {_q(d)})"
    if d["signal_only"]:
        return f"det vi hört nära oss är signalladdningar (bedömningen {_q(d)})"
    return "inga sjunkbomber nära oss"


ZAMPOLIT_WHY = {
    "forbidden": lambda d: f"Ordern förbjuder kärnladdningen ({d['source']}).",
    "authorized": lambda d: f"Moskva har gett tillstånd ({d['source']}).",
    "condition_met": lambda d: f"Stabens villkor är uppfyllt: {_charges(d)}. Partiet kräver att vi "
    "försvarar oss.",
    "condition_unmet": lambda d: f"Stabens villkor är inte uppfyllt: {_charges(d)}.",
    "attacked": lambda d: f"Vi har ingen order, men {_charges(d)}. Det kan vara krig.",
    "no_order": lambda d: f"Vi har ingen order från Moskva, och {_charges(d)}.",
}
STARPOM_WHY = {
    "forbidden": lambda d: f"Ordern förbjuder kärnladdningen ({d['source']}).",
    "authorized": lambda d: f"Moskva har gett tillstånd ({d['source']}).",
    "condition_met": lambda d: f"Stabens villkor är uppfyllt, och det är säkert: {_charges(d)}.",
    "condition_unsure": lambda d: f"Villkoret kräver skarpa sjunkbomber, och det vet vi inte säkert: "
    f"{_charges(d)}.",
    "no_order": lambda d: f"Vi har ingen order från Moskva, och {_charges(d)}.",
    "attack_unsure": lambda d: f"Vi har ingen order, och vi vet inte säkert att det är skarpt: "
    f"{_charges(d)}.",
    "ask_staff": lambda d: f"Vi angrips skarpt, men vi kan nå staben. Moskva ska fråga, inte vi gissa.",
    "attacked_cut_off": lambda d: "Vi angrips skarpt, det är säkert, skrovet är skadat och vi kan "
    "inte nå staben.",
    "not_damaged": lambda d: "Vi angrips skarpt och kan inte nå staben, men skrovet håller. Utan order "
    "från Moskva skjuter vi inte. Vi kan fortfarande gå undan.",
}
REACH_TEXT = {"hunted": "de har kontakt med oss", "attacked": "vi angreps nyss",
              "threat": "en jagare är nära"}

PHRASES = {
    "council.called": lambda d: "Zampoliten här. Starpom är på väg till centralen.",
    "council.zampolit": lambda d: f"Kamrat befälhavare, zampolit. {ZAMPOLIT_WHY[d['why']](d)} "
    + ("Jag vrider min nyckel." if d["yes"] else "Jag vrider inte min nyckel."),
    "council.starpom": lambda d: f"Kamrat befälhavare, starpom. {STARPOM_WHY[d['why']](d)} "
    + ("Jag vrider min nyckel." if d["yes"] else "Jag vrider inte min nyckel."),
    "council.keys": lambda d: f"Torped. Alla tre nycklarna vridna. Kärnladdningen i tub {d['tube']} är "
    f"skarp i {minutes(d['minutes'])}. Skjuter på er order, kapten.",
    "council.refused": lambda d: f"Torped. Kärnladdningen förblir säkrad: {d['who']} har inte vridit "
    "sin nyckel.",
    "council.no_t5": lambda d: "Kapten, zampolit. Ingen tub är laddad med kärnladdning. "
    + ("Torpedrummet har T-5 i reserv." if d["reserve"] else "Vi har ingen ombord."),
    "council.again": lambda d: f"Kapten, zampolit. Rådet hölls för {minutes(d['minutes'])} sedan och "
    "inget har ändrats.",
    "council.pending": lambda d: "Rådet samlas redan, kapten.",
    "council.expired": lambda d: "Torped. Tiden för nycklarna har gått ut. Kärnladdningen är säkrad igen.",
    "council.suggest": lambda d: "Kapten, starpom. I stället: "
    + ("sänd en kort rapport och fråga staben." if d["why"] == "ask_staff"
       else f"gå djupt och bryt kontakten, {d['order']}."),
}
phrases.register(PHRASES)


def _ru_charges(d: dict) -> str:
    if d["attacked"]:
        return "нас атакуют боевыми глубинными бомбами"
    if d["signal_only"]:
        return "рядом рвутся сигнальные заряды"
    return "бомб рядом нет"


RU_WHY = {
    "forbidden": lambda d: "Приказ запрещает ядерное оружие.",
    "authorized": lambda d: "Москва дала разрешение.",
    "condition_met": lambda d: f"Условие штаба выполнено: {_ru_charges(d)}.",
    "condition_unmet": lambda d: f"Условие штаба не выполнено: {_ru_charges(d)}.",
    "condition_unsure": lambda d: "Мы не уверены, что бомбы боевые.",
    "attacked": lambda d: f"Приказа нет, но {_ru_charges(d)}. Возможно, это война.",
    "no_order": lambda d: f"Приказа из Москвы нет, {_ru_charges(d)}.",
    "attack_unsure": lambda d: "Приказа нет, и мы не уверены, что бомбы боевые.",
    "ask_staff": lambda d: "Нас атакуют, но со штабом можно связаться. Спросим Москву.",
    "attacked_cut_off": lambda d: "Нас атакуют боевыми, корпус повреждён, связи со штабом нет.",
    "not_damaged": lambda d: "Нас атакуют, но корпус цел. Без приказа Москвы не стреляем. "
    "Можем уйти.",
}
KEY_RU = {True: "Поворачиваю свой ключ.", False: "Свой ключ не поворачиваю."}
RU_PHRASES = {
    "council.called": lambda d: "Замполит в центральном. Старпом идёт.",
    "council.zampolit": lambda d: f"{R.CAPTAIN}, замполит. {RU_WHY[d['why']](d)} {KEY_RU[d['yes']]}",
    "council.starpom": lambda d: f"{R.CAPTAIN}, старпом. {RU_WHY[d['why']](d)} {KEY_RU[d['yes']]}",
    "council.keys": lambda d: f"Минёр. Все три ключа повёрнуты. Ядерная торпеда в аппарате номер "
    f"{R.DIGITS[d['tube']]} готова. Ждём приказа.",
    "council.refused": lambda d: "Минёр. Ядерная торпеда остаётся на предохранителе.",
    "council.no_t5": lambda d: f"{R.CAPTAIN}, замполит. Ядерной торпеды в аппаратах нет.",
    "council.again": lambda d: f"{R.CAPTAIN}, замполит. Совет уже был, ничего не изменилось.",
    "council.pending": lambda d: "Совет уже собирается.",
    "council.expired": lambda d: "Минёр. Время вышло, ядерная торпеда снова на предохранителе.",
    "council.suggest": lambda d: f"{R.CAPTAIN}, старпом. Предлагаю "
    + ("запросить штаб." if d["why"] == "ask_staff" else "уйти на глубину и оторваться."),
}
phrases.register_ru(RU_PHRASES)


def _situation(a: WarAssessment) -> tuple:
    """Det i bedömningen som gör att rådet kan hållas igen direkt om det ändrats."""
    return (a.order, a.war, a.attacked, a.attacked_q, a.signal_only, a.charges, a.reach_staff)


class NuclearCouncil(Station):
    """Zampoliten och kärnvapenrådet. Rollen är zampolitens; starpom svarar med sin egen röst."""
    role = Role.ZAMPOLIT
    COMMANDS = [
        CommandSpec(r"kärnvapenråd(?:et)?|karnvapenrad(?:et)?|förbered kärnladdningen|"
                    r"forbered karnladdningen|vrid nycklarna",
                    lambda m: CallCouncil(), "kärnvapenråd"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.due: int | None = None          # när rådet är samlat
        self.armed_until: int | None = None  # nycklarna vridna till dess
        self.armed_tube: int | None = None
        self.last: tuple[int, tuple] | None = None   # (tid, läget) vid senaste rådet
        self.held: list[dict] = []           # varje råd (för slutrapporten)

    # --- frågan torpedrummet ställer -------------------------------------------------
    def armed(self) -> bool:
        return self.armed_until is not None and self.now < self.armed_until

    def fired(self) -> None:
        """Torpedrummet har skjutit kärnladdningen: nycklarna tillbaka."""
        self.armed_until = self.armed_tube = None

    def _torpedo_room(self):
        from .torpedo_room import TorpedoRoom
        return self.game.station(TorpedoRoom)

    # --- order -----------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        if not isinstance(order, CallCouncil):
            return
        if self.due is not None:
            self.say("council.pending", kind="ack")
            return
        tr = self._torpedo_room()
        tube = next((t.n for t in tr.tubes if t.load == "T-5"), None) if tr else None
        if tube is None:
            self.say("council.no_t5", {"reserve": bool(tr and tr.inventory.get("T-5"))})
            return
        a = assess(self.game.knowledge, self.now)
        if self.last is not None and self.now - self.last[0] < AGAIN_S and \
                self.last[1] == _situation(a) and not self.armed():
            self.say("council.again", {"minutes": max(1, round((self.now - self.last[0]) / 60))})
            return
        self.armed_tube = tube
        self.due = self.now + GATHER_S
        self.say("council.called", kind="ack")

    # --- varje sekund ---------------------------------------------------------------
    def update(self) -> None:
        if self.armed_until is not None and self.now >= self.armed_until:
            self.armed_until = None
            tr = self._torpedo_room()
            (tr or self).say("council.expired", alarm=True)
        if self.due is None or self.now < self.due:
            return
        self.due = None
        self._hold()

    def _hold(self) -> None:
        k = self.game.knowledge
        a = assess(k, self.now)
        z, s = zampolit_vote(a), starpom_vote(a)
        base = {"attacked": a.attacked, "q": a.attacked_q.value, "signal_only": a.signal_only,
                "source": a.order_source, "order": a.order, "reach": a.reach_why}
        self.say("council.zampolit", {**base, "yes": z.yes, "why": z.why}, quality=a.attacked_q)
        self.game.say(Role.XO, "council.starpom", {**base, "yes": s.yes, "why": s.why},
                      quality=a.attacked_q)
        self.last = (self.now, _situation(a))
        record = {"t": self.now, "zampolit": z.yes, "starpom": s.yes, "z_why": z.why,
                  "s_why": s.why, "order": a.order, "attacked": a.attacked,
                  "q": a.attacked_q.value, "charges": a.charges}
        self.held.append(record)
        self.game.bus.publish(CouncilHeld(self.now, z.yes, s.yes, z.why, s.why, a.order,
                                          a.attacked, a.attacked_q))
        tr = self._torpedo_room()
        if z.yes and s.yes:
            self.armed_until = self.now + ARM_S
            (tr or self).say("council.keys", {"tube": self.armed_tube, "minutes": ARM_S // 60},
                             alarm=True, extra_delay=VERDICT_DELAY_S)
            return
        who = " och ".join(n for n, v in (("zampoliten", z), ("starpom", s)) if not v.yes)
        (tr or self).say("council.refused", {"who": who}, extra_delay=VERDICT_DELAY_S)
        if not s.yes and s.suggest:
            from .starpom import FirstOfficer
            fo = self.game.station(FirstOfficer)
            if fo is not None:
                fo.suggest("council_instead", "council.suggest", {"why": s.why},
                           order=s.suggest, cooldown=60)

    # --- systemtavlan ---------------------------------------------------------------
    def system_items(self) -> list:
        tr = self._torpedo_room()
        if tr is None or not (any(t.load == "T-5" for t in tr.tubes) or tr.inventory.get("T-5")):
            return []
        if self.armed():
            left = (self.armed_until - self.now + 59) // 60
            return [Gauge("VAPEN", "Kärnladdning", f"nycklar 3/3, skarp {left} min, tub {self.armed_tube}",
                          DANGER)]
        if self.due is not None:
            return [Gauge("VAPEN", "Kärnladdning", "rådet samlas, nycklar 1/3", WARN)]
        if self.held:
            h = self.held[-1]
            n = 1 + h["zampolit"] + h["starpom"]
            return [Gauge("VAPEN", "Kärnladdning", f"säkrad, nycklar {n}/3 vid senaste rådet", INFO)]
        return [Gauge("VAPEN", "Kärnladdning", "säkrad", OK)]
