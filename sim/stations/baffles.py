"""Döda sektorn akterut: sonarrummet lyssnar i kölvattnet (del av SonarRoom, sonar_room.py).

Båten har en död sektor i alla scenarier (`OwnShip.baffle_deg`, sedan 2026-11-23; förut bara Svansen; modellen
i sim/sonar.py `baffle_loss`). Har vi gått rakt (inom `STRAIGHT_DEG`) i `CLEAR_AFTER_S` i minst `CLEAR_MIN_KN` vet
sonar att den inte hört något akterut: den föreslår en gir `CLEAR_TURN_DEG` åt sidan och `CLEAR_KN` en
stund (i vår marschfart dränker vårt eget brus en tyst ubåt även på sidan). Har vi legat på den nya kursen
`CLEAR_LISTEN_S` utan att sonar fått en ny kontakt säger sonar att det är tomt akterut och föreslår den
gamla kursen och farten igen. Ingen ny order: det är `kurs` och `fart`. Inte medan de har oss, inte när
navigatören styr (`steer`, `vak`), och inte mot kortets land (`course_safe`, båda sidorna prövas).
"""
from __future__ import annotations

from .. import phrases
from .. import russian as R
from ..fmt import fmt_course
from ..geo import angle_diff, bearing_to, norm360
from ..reports import Quality

CLEAR_AFTER_S = 10 * 60        # så länge rakt innan sonar vill lyssna akterut
CLEAR_EMPTY_MAX = 2            # varje tom lyssning fördubblar väntan, högst så många gånger (10, 20, 40 min)
CLEAR_MIN_KN = 6.0             # långsammare än så hörs kölvattnet ändå någorlunda
STRAIGHT_DEG = 20.0            # mindre kursändringar räknas inte som gir
CLEAR_TURN_DEG = 60.0          # så långt åt sidan: kölvattnet kommer ut ur döda sektorn
CLEAR_KN = 4                   # lyssningsfarten
CLEAR_LISTEN_S = 120           # så länge på den nya kursen innan sonar säger att det är tomt
CLEAR_COOLDOWN_S = 10 * 60
ASTERN_LOST_S = 30 * 60        # en tappad kontakt så nyss hörd: sonar vill höra den igen
ASTERN_MARGIN_DEG = 10.0       # ... och den ligger inom sektorn och så här mycket till
ASTERN_COOLDOWN_S = 10 * 60
TORPEDO_QUIET_S = 5 * 60       # så länge efter en torped (eller medan den troligen går akterut) ingen gir


PHRASES = {
    "sonar.suggest.clear_baffles": lambda d: f"Kapten, sonar. Vi har gått rakt i {d['minutes']} "
    "minuter och hör ingenting akterut, där skymmer skrovet och skruven. Föreslår kurs "
    f"{fmt_course(d['course'])} och fart {d['speed']} en stund, så lyssnar vi i kölvattnet.",
    "sonar.baffles.clear": lambda d: "Kapten, sonar. Akterut är tomt, ingenting i kölvattnet. "
    + (f"Föreslår kurs {fmt_course(d['course'])} och fart {d['speed']} igen." if d.get("course") is not None
       else f"Föreslår fart {d['speed']} igen."),
    "sonar.baffles.speed": lambda d: f"Kapten, sonar. Vi lyssnar inte akterut längre. Föreslår "
    f"fart {d['speed']} igen.",
    "sonar.suggest.astern_lost": lambda d: f"Kapten, sonar. {d['designation']} ligger akterut nu, "
    f"{'enligt plottet' if d.get('solution') else 'sista bäringen'} {fmt_course(d['bearing'])}, där "
    f"skymmer skrovet och skruven. Föreslår kurs {fmt_course(d['course'])}, så hör vi den igen.",
}
phrases.register(PHRASES)

RU_PHRASES = {
    "sonar.suggest.clear_baffles": lambda d: f"{R.CAPTAIN}, акустик. Идём прямо "
    f"{R.count(d['minutes'], ('минуту', 'минуты', 'минут'))}, за кормой ничего не слышим. "
    f"Предлагаю курс {R.course(d['course'])} и ход {R.count(d['speed'], R.KNOT)} на время, "
    "прослушаем кильватер.",
    "sonar.baffles.clear": lambda d: f"{R.CAPTAIN}, акустик. За кормой чисто. Предлагаю "
    + (f"курс {R.course(d['course'])} и " if d.get("course") is not None else "")
    + f"ход {R.count(d['speed'], R.KNOT)} снова.",
    "sonar.baffles.speed": lambda d: f"{R.CAPTAIN}, акустик. Предлагаю ход "
    f"{R.count(d['speed'], R.KNOT)} снова.",
    "sonar.suggest.astern_lost": lambda d: f"{R.CAPTAIN}, акустик. "
    f"{R.contact(d['designation']).capitalize()} за кормой, в мёртвой зоне. Предлагаю курс "
    f"{R.course(d['course'])}, услышим снова.",
}
phrases.register_ru(RU_PHRASES)


def _dangerous(classification: str) -> bool:
    """En jagare, eskort eller ubåt i undervattensläge: tappar vi den akterut söker vi inte upp den
    (i Svansen gav giren tillbaka lösningen, ubåten märkte det och sköt)."""
    c = classification
    return any(w in c for w in ("jagare", "eskort", "patrullbåt", "undervattens")) or \
        ("ubåt" in c and "ytläge" not in c)


class BafflesMixin:
    """Del av SonarRoom: lyssna i kölvattnet."""

    def _baffles_init(self) -> None:
        self._straight_course: float | None = None   # kursen vi gått rakt på (efter giren)
        self._straight_since = 0                     # sedan när
        self._straight_kn = 0                        # marschfarten (beordrad) före giren
        # sonars egen gir: (kursen vi föreslog, kurs och fart att gå tillbaka till)
        self._clear_plan: tuple[float, float, int] | None = None
        self._clear_t: int | None = None             # när vi låg på den föreslagna kursen
        self._clear_asked_t = 0                      # när sonar föreslog giren
        self._clear_known: set[str] = set()          # kontakterna sonar hade innan
        self._clear_new = False                      # en ny kontakt under lyssningen
        self._clear_empty = 0                        # tomma lyssningar i rad (Clyde: var 15:e min hela natten)
        self._clear_tracks = 0                       # kontakterna i plottet när vi senast lyssnade
        self._astern_asked: set[tuple[str, int]] = set()   # (kontakt, sista bäringens tid) vi föreslagit gir för

    def _baffles_watch(self) -> None:
        if self.own.baffle_deg <= 0 or self.now % 5:
            return
        if self.now % 30 == 0:
            self._astern_lost_watch()
        st = self.own.state
        # också mitt i en gir: en undanmanöver ut och tillbaka till nästan samma kurs är ingen rak gång
        if self._straight_course is None or abs(angle_diff(st.course, self._straight_course)) > STRAIGHT_DEG:
            self._straight_course, self._straight_since = st.course, self.now
        if abs(angle_diff(st.course, st.ordered_course)) > 5:
            return                                   # mitt i en gir
        if self._clear_plan is not None:
            self._clear_listen(st)
            return
        self._straight_kn = round(st.ordered_speed)
        if len(self.game.knowledge.tracks) > self._clear_tracks:
            self._clear_empty = 0                    # en ny kontakt sedan sist: lyssna som vanligt igen
        wait = CLEAR_AFTER_S * 2 ** min(self._clear_empty, CLEAR_EMPTY_MAX)
        if st.speed < CLEAR_MIN_KN or self.now - self._straight_since < wait:
            return
        if self.game.knowledge.hunted(self.now) or \
                self.game.knowledge.torpedo_alarm(self.now, window=TORPEDO_QUIET_S):
            return                                   # då styr undanmanövern
        if self.game.knowledge.threat_held():
            return      # ett hot i plottet (Kuba: jagaren pingade på 2 nm): inte nu, i 4 knop
        nav = self._navigator()
        if nav is not None and (nav.steer is not None or nav.vak is not None):
            return                                   # navigatören styr (anfall, följa, farleden …)
        first = 1 if (self.now // CLEAR_COOLDOWN_S) % 2 == 0 else -1
        course = None
        for side in (first, -first):                 # inte mot kortets land eller grund
            c = round(norm360(st.course + side * CLEAR_TURN_DEG))
            if nav is None or nav.course_safe(c):
                course = c
                break
        if course is None:
            return
        if self.suggest("clear_baffles", "sonar.suggest.clear_baffles",
                        {"minutes": (self.now - self._straight_since) // 60, "course": course,
                         "speed": CLEAR_KN},
                        order=f"kurs {course:03d}, fart {CLEAR_KN}", cooldown=CLEAR_COOLDOWN_S):
            self._clear_plan = (course, st.course, self._straight_kn)
            self._clear_asked_t = self.now
            self._clear_t = None
            self._clear_known = set(self.game.knowledge.tracks)   # allt sonar redan känner
            self._clear_new = False

    def _astern_lost_watch(self) -> None:
        """En kontakt vi tappat nyss ligger (enligt plottet, annars sista bäringen) i döda sektorn:
        föreslå en gir som lägger den tvärs. Bara fartyg vi vill höra (övningsfartyget, stora fartyg,
        Polarisbåten i ytläge), inte handel, is eller jägare (`_dangerous`). Inte medan de har oss eller navigatören styr, inte mot
        kortets land; en gång per gång vi tappat kontakten (tills den hörts igen)."""
        st = self.own.state
        k = self.game.knowledge
        if k.hunted(self.now) or k.torpedo_alarm(self.now, window=TORPEDO_QUIET_S) or st.speed < 0.5 \
                or self.own.surfaced:
            return
        nav = self._navigator()
        if nav is not None and (nav.steer is not None or nav.vak is not None):
            return
        if abs(angle_diff(st.course, st.ordered_course)) > 5:
            return                                   # mitt i en gir
        ex, ey = self.game.own_position_estimate()
        stern = norm360(st.course + 180.0)
        for tr in k.tracks.values():
            if tr.held or tr.sunk or not tr.observations or tr.benign or _dangerous(tr.classification):
                continue                             # inget att söka upp: handel, is, eller en jägare vi blivit av med
            last_t = tr.observations[-1].t
            if self.now - last_t > ASTERN_LOST_S or (tr.designation, last_t) in self._astern_asked:
                continue                             # en gång per gång vi tappat den
            sol = tr.solution
            if sol is not None and sol.quality >= Quality.OSAKER:
                dt = (self.now - sol.t) / 3600.0
                b = bearing_to(ex, ey, sol.x + sol.state[2] * dt, sol.y + sol.state[3] * dt)
            else:
                b, sol = tr.last_bearing, None
            if abs(angle_diff(b, stern)) > self.own.baffle_deg + ASTERN_MARGIN_DEG:
                continue
            # tvärs om kontakten, åt det håll som är närmast vår kurs
            options = sorted((norm360(b + 90), norm360(b - 90)), key=lambda c: abs(angle_diff(c, st.course)))
            course = next((round(c) % 360 for c in options if nav is None or nav.course_safe(c)), None)
            if course is None:
                continue
            if self.suggest(f"astern_lost{tr.designation}", "sonar.suggest.astern_lost",
                            {"designation": tr.designation, "bearing": b, "course": course,
                             "solution": sol is not None},
                            order=f"kurs {course:03d}", cooldown=ASTERN_COOLDOWN_S):
                self._astern_asked.add((tr.designation, last_t))
                return

    def _took_other_course(self, planned: float) -> bool:
        """Kaptenen har beordrat en annan kurs än lyssningskursen (eller navigatören styr)."""
        st = self.own.state
        nav = self._navigator()
        return self.now - self._clear_asked_t > 60 and (
            abs(angle_diff(st.ordered_course, planned)) > STRAIGHT_DEG
            or (nav is not None and (nav.steer is not None or nav.vak is not None)))

    def _navigator(self):
        from .navigation import NavigationStation
        try:
            return self.game.station(NavigationStation)
        except KeyError:
            return None

    def _clear_listen(self, st) -> None:
        """Vår gir: ligger vi på den föreslagna kursen lyssnar vi `CLEAR_LISTEN_S` och säger sedan
        att det är tomt (och föreslår vägen tillbaka), om inget nytt som kan vara ett hot hörts
        (handel och övningsfartyget räknas inte). Går kaptenen någon annanstans, eller sa nej, glömmer
        vi giren, och står lyssningsfarten kvar föreslår sonar den gamla farten."""
        course, old, old_kn = self._clear_plan
        on_course = abs(angle_diff(st.course, course)) <= STRAIGHT_DEG
        if not on_course:
            # kaptenen valde en annan väg: lämnade kursen, eller girade inte dit inom spärrtiden.
            # (Förut räknades tiden från när vi började gå rakt, minst CLEAR_AFTER_S sedan, så planen
            # glömdes fem sekunder efter förslaget och "tomt akterut" kom aldrig: farten blev kvar.)
            if self._clear_t is not None or self.now - self._clear_asked_t > CLEAR_COOLDOWN_S \
                    or self._took_other_course(course):
                self._clear_plan = None
                if round(st.ordered_speed) == CLEAR_KN and old_kn > CLEAR_KN:
                    # lyssningsfarten står kvar fast giren är övergiven: den gamla farten igen
                    self.suggest("baffles_speed", "sonar.baffles.speed", {"speed": old_kn},
                                 order=f"fart {old_kn}", cooldown=CLEAR_COOLDOWN_S)
            return
        if self._clear_t is None:
            self._clear_t = self.now
        if self.now - self._clear_t < CLEAR_LISTEN_S:
            return
        self._clear_plan = None
        k = self.game.knowledge
        new = [t for d, t in k.tracks.items() if d not in self._clear_known]
        self._clear_new = any(not (t.benign or t.friendly) for t in new)
        if self._clear_new or k.hunted(self.now):
            # något nytt som kan vara ett hot (inte handel eller övningsfartyget): kaptenen beslutar
            return                                      # sonar har redan sagt vad den hört
        self._clear_empty += 1
        self._clear_tracks = len(k.tracks)
        nav = self._navigator()
        back = None
        for off in (0, 15, -15, 30, -30, 45, -45, 60, -60, 90, -90):
            c = round(norm360(old + off)) % 360       # den gamla kursen, annars närmaste säkra
            if nav is None or nav.course_safe(c):
                back = c
                break
        if back is None:
            # ingen kurs nära den gamla går: tillbaka till farten, navigatören tar kursen
            self.suggest("baffles_back", "sonar.baffles.clear", {"speed": old_kn},
                         order=f"fart {old_kn}", cooldown=CLEAR_COOLDOWN_S)
            return
        self.suggest("baffles_back", "sonar.baffles.clear", {"course": back, "speed": old_kn},
                     order=f"kurs {back:03d}, fart {old_kn}", cooldown=CLEAR_COOLDOWN_S)
