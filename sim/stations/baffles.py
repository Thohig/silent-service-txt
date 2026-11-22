"""Döda sektorn akterut: sonarrummet lyssnar i kölvattnet (del av SonarRoom, sonar_room.py).

Bara när båten har en död sektor (`OwnShip.baffle_deg` > 0, Svansen; modellen i sim/sonar.py
`baffle_loss`). Har vi gått rakt (inom `STRAIGHT_DEG`) i `CLEAR_AFTER_S` i minst `CLEAR_MIN_KN` vet
sonar att den inte hört något akterut: den föreslår en gir `CLEAR_TURN_DEG` åt sidan och `CLEAR_KN` en
stund (i vår marschfart dränker vårt eget brus en tyst ubåt även på sidan). Har vi legat på den nya kursen
`CLEAR_LISTEN_S` utan att sonar fått en ny kontakt säger sonar att det är tomt akterut och föreslår den
gamla kursen och farten igen. Ingen ny order: det är `kurs` och `fart`.
"""
from __future__ import annotations

from .. import phrases
from .. import russian as R
from ..fmt import fmt_course
from ..geo import angle_diff, norm360

CLEAR_AFTER_S = 10 * 60        # så länge rakt innan sonar vill lyssna akterut
CLEAR_MIN_KN = 6.0             # långsammare än så hörs kölvattnet ändå någorlunda
STRAIGHT_DEG = 20.0            # mindre kursändringar räknas inte som gir
CLEAR_TURN_DEG = 60.0          # så långt åt sidan: kölvattnet kommer ut ur döda sektorn
CLEAR_KN = 4                   # lyssningsfarten
CLEAR_LISTEN_S = 120           # så länge på den nya kursen innan sonar säger att det är tomt
CLEAR_COOLDOWN_S = 10 * 60


PHRASES = {
    "sonar.suggest.clear_baffles": lambda d: f"Kapten, sonar. Vi har gått rakt i {d['minutes']} "
    "minuter och hör ingenting akterut, där skymmer skrovet och skruven. Föreslår kurs "
    f"{fmt_course(d['course'])} och fart {d['speed']} en stund, så lyssnar vi i kölvattnet.",
    "sonar.baffles.clear": lambda d: "Kapten, sonar. Akterut är tomt, ingenting i kölvattnet. "
    f"Föreslår kurs {fmt_course(d['course'])} och fart {d['speed']} igen.",
}
phrases.register(PHRASES)

RU_PHRASES = {
    "sonar.suggest.clear_baffles": lambda d: f"{R.CAPTAIN}, акустик. Идём прямо "
    f"{R.count(d['minutes'], ('минуту', 'минуты', 'минут'))}, за кормой ничего не слышим. "
    f"Предлагаю курс {R.course(d['course'])} и ход {R.count(d['speed'], R.KNOT)} на время, "
    "прослушаем кильватер.",
    "sonar.baffles.clear": lambda d: f"{R.CAPTAIN}, акустик. За кормой чисто. Предлагаю курс "
    f"{R.course(d['course'])} и ход {R.count(d['speed'], R.KNOT)} снова.",
}
phrases.register_ru(RU_PHRASES)


class BafflesMixin:
    """Del av SonarRoom: lyssna i kölvattnet."""

    def _baffles_init(self) -> None:
        self._straight_course: float | None = None   # kursen vi gått rakt på (efter giren)
        self._straight_since = 0                     # sedan när
        self._straight_kn = 0                        # marschfarten (beordrad) före giren
        # sonars egen gir: (kursen vi föreslog, kurs och fart att gå tillbaka till)
        self._clear_plan: tuple[float, float, int] | None = None
        self._clear_t: int | None = None             # när vi låg på den föreslagna kursen
        self._clear_known: set[str] = set()          # kontakterna sonar hade innan
        self._clear_new = False                      # en ny kontakt under lyssningen

    def _baffles_watch(self) -> None:
        if self.own.baffle_deg <= 0 or self.now % 5:
            return
        st = self.own.state
        if abs(angle_diff(st.course, st.ordered_course)) > 5:
            return                                   # mitt i en gir
        if self._straight_course is None or abs(angle_diff(st.course, self._straight_course)) > STRAIGHT_DEG:
            self._straight_course, self._straight_since = st.course, self.now
        if self._clear_plan is not None:
            self._clear_listen(st)
            return
        self._straight_kn = round(st.ordered_speed)
        if st.speed < CLEAR_MIN_KN or self.now - self._straight_since < CLEAR_AFTER_S:
            return
        if self.game.knowledge.hunted(self.now):
            return                                   # då styr undanmanövern
        side = 1 if (self.now // CLEAR_COOLDOWN_S) % 2 == 0 else -1
        course = round(norm360(st.course + side * CLEAR_TURN_DEG))
        if self.suggest("clear_baffles", "sonar.suggest.clear_baffles",
                        {"minutes": (self.now - self._straight_since) // 60, "course": course,
                         "speed": CLEAR_KN},
                        order=f"kurs {course:03d}, fart {CLEAR_KN}", cooldown=CLEAR_COOLDOWN_S):
            self._clear_plan = (course, st.course, self._straight_kn)
            self._clear_t = None
            self._clear_known = set(self.held_designations())
            self._clear_new = False

    def _clear_listen(self, st) -> None:
        """Vår gir: ligger vi på den föreslagna kursen lyssnar vi `CLEAR_LISTEN_S` och säger sedan
        att det är tomt (och föreslår vägen tillbaka), om ingen ny kontakt hörts. Går kaptenen
        någon annanstans, eller sa nej, glömmer vi giren."""
        course, old, old_kn = self._clear_plan
        if set(self.held_designations()) - self._clear_known:
            self._clear_new = True
        on_course = abs(angle_diff(st.course, course)) <= STRAIGHT_DEG
        if not on_course:
            if self._clear_t is not None or self.now - self._straight_since > CLEAR_COOLDOWN_S:
                self._clear_plan = None                 # kaptenen valde en annan väg
            return
        if self._clear_t is None:
            self._clear_t = self.now
        if self.now - self._clear_t < CLEAR_LISTEN_S:
            return
        self._clear_plan = None
        if self._clear_new or self.game.knowledge.hunted(self.now):
            return                                      # sonar har redan sagt vad den hört
        back = round(old) % 360
        self.suggest("baffles_back", "sonar.baffles.clear", {"course": back, "speed": old_kn},
                     order=f"kurs {back:03d}, fart {old_kn}", cooldown=CLEAR_COOLDOWN_S)
