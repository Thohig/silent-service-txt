"""Bryggan: utkiken i tornet när vi ligger i ytläge.

Luckan och bryggan är sanning (`OwnSystems.bridge` i sim/ownship.py): bryggan
bemannas när vi kommit upp och måste utrymmas innan vi kan dyka. Stationen läser
luckan som ett eget instrument och säger när det händer.

Utkiken är en sensor. Medan bryggan är bemannad ser den sig runt varannan sekund
(World) och publicerar `BridgeSighted` med en `PeriscopePicture` (eye "brygga"):
samma regler för horisont, synlig del och natt som periskopet, men med ögat 8 m
upp, bäring med pejlskivan och avståndet bedömt med ögat (σ 15 % + 0,05 nm).
Bedömningsfelen dras om en gång i minuten per föremål, så att bilden inte
fladdrar; vid varje ny bedömning får plottet en observation. Nya föremål ropas ut,
och flyg i sikte eller en jagare nära ger förslag att dyka.
"""
from __future__ import annotations

from .. import phrases
from .. import russian as R
from ..arctic import STATION_LIGHT_NM
from ..crew import Role
from ..events import (BearingObserved, BridgeSighted, ClassificationChanged, ContactDetected,
                      EventSighted, PositionReported)
from ..fmt import fmt_course, kn, nm
from ..geo import bearing_to, distance, norm360, velocity
from ..ice import ice_view
from ..ownship import BRIDGE_CLEAR_S
from ..seabed import shore_ranges
from ..periscope import (EVENT_S, sea_sigma_f, wave_height_m, sky_of, AOB_SIGMA, TWILIGHT_AOB_F, EYE_BRIDGE_M, IceBearing, Judgement, Judges, LandBearing,
                         PeriscopePicture, SightedObject, angle_on_bow, aob_quality, lights,
                         detectable, range_quality, visible_part)
from ..reports import Quality
from ..systems import INFO, OK, WARN, Gauge
from ..tma import BearingObs
from .base import Station
from .lookout import visible_events
from .officer import SIGHTED, _view_object
from .sonar_room import SonarRoom

LOOK_EVERY_S = 2
BEARING_SIGMA = 1.0          # pejlskivan på bryggan, grader
RANGE_REL_SIGMA = 0.15       # avstånd med ögat: σ = 15 % + 0,05 nm (land, händelser)
RANGE_ABS_SIGMA = 0.05
# Utkiken tittar på fartyg i kikaren (7×50 med strecksskala): ser det som hög förstoring ser
# och bedömer avståndet bättre än med ögat
BINOC_POWER = 7.0
BINOC_RANGE_REL = 0.12
BINOC_RANGE_ABS = 0.03
SPEED_SIGMA = 3.0            # fart ur bogvåg och svall, knop
JUDGE_EVERY_S = 60           # ny bedömning (och observation till plottet) så här ofta
RESIGHT_S = 300              # ett föremål ur sikte så länge ropas ut igen när det syns
CLOSE_NM = 3.0               # en jagare så nära: föreslå att dyka
DIVE_DEPTH = 60
WAKE_NM = 1.5                # torpedspår syns i dagsljus så här långt

PART_TEXT = {"helt": "", "överbyggnad": ", skrovet under horisonten",
             "mastoppar": ", bara mastopparna syns"}
LIGHT_TEXT = {"topp": "topplanterna", "grön": "grön sidolanterna", "röd": "röd sidolanterna",
              "akter": "akterlanterna"}
LABEL_RU = {"jagare": "эсминец", "handelsfartyg": "транспорт", "patrullbåt": "сторожевой катер",
            "fartyg till ankars": "судно на якоре", "trupptransport": "войсковой транспорт",
            "tankfartyg": "танкер", "fartyg": "судно"}


def _lights_text(ls: tuple[str, ...]) -> str:
    words = [LIGHT_TEXT[x] for x in ls if x in LIGHT_TEXT]
    return " och ".join(words) if words else "ljus"


def _contact(d: dict) -> str:
    where = f"i bäring {fmt_course(d['bearing'])}, cirka {nm(d['range'])} sjömil"
    if d["lights"]:
        return (f"Bryggan: {d['designation']}, lanternor {where}. Vi ser "
                f"{_lights_text(tuple(d['lights']))}.")
    out = f"Bryggan: {d['designation']}, {d['label']} {where}{PART_TEXT[d['visible']]}."
    if d["visible"] != "mastoppar":
        out += f" Går ungefär {fmt_course(round(d['course'] / 5) * 5)}, fart cirka {kn(d['speed'])} knop."
    return out



SEA_WORDS = ((0, "Spegelblankt"), (2, "Lugn sjö"), (4, "Måttlig sjö"), (6, "Grov sjö"),
             (99, "Hård sjö"))


def sea_words(beaufort: int) -> str:
    """Vakthavandes ord om sjögången, med vindstyrkan."""
    word = next(w for top, w in SEA_WORDS if beaufort <= top)
    return word if beaufort == 0 else f"{word}, vind {beaufort}"

PHRASES = {
    "bridge.manned": lambda d: "Luckan öppen, utkikarna på bryggan."
                               + (f" {sea_words(d['sea'])}." if "sea" in d else ""),
    "bridge.sea": lambda d: f"Bryggan: sjön {'ökar' if d['up'] else 'mojnar'}. {sea_words(d['sea'])}.",
    "bridge.clearing": lambda d: f"Utrym bryggan! Alla man ned, luckan stängs. "
    f"Cirka {d['seconds']} sekunder.",
    "bridge.shut": lambda d: "Bryggan utrymd, tornluckan stängd. Klart att dyka.",
    "bridge.contact": _contact,
    "bridge.aircraft": lambda d: f"Bryggan: flygplan i bäring {fmt_course(d['bearing'])}, cirka "
    f"{nm(d['range'])} sjömil, " + ("lågt över vattnet!" if d["low"] else "på höjd."),
    "bridge.station": lambda d: f"Bryggan: ljus på isen i bäring {fmt_course(d['bearing'])}, "
    f"cirka {nm(d['range'])} sjömil. Det är stationen!",
    "bridge.suggest.dive": lambda d: f"Kapten, bryggan. {d['reason']} Föreslår att vi dyker, "
    f"djup {d['depth']:.0f}.",
    "bridge.land": lambda d: f"Bryggan: land i sikte, närmast i bäring {fmt_course(d['bearing'])}, "
    f"cirka {nm(d['range'])} sjömil.",
    "bridge.column": lambda d: f"Bryggan: vattenpelare i bäring {fmt_course(d['bearing'])}, cirka "
    f"{nm(d['range'])} sjömil. Sjunkbomber" + (", övningsladdningar." if d["practice"] else "!"),
    "bridge.hit": lambda d: f"Bryggan: explosion i bäring {fmt_course(d['bearing'])}, cirka "
    f"{nm(d['range'])} sjömil! " + ("Ett eldklot, kapten!" if d["nuclear"] else "Eld och rök."),
}
phrases.register(PHRASES)


def _contact_ru(d: dict) -> str:
    what = "ходовые огни" if d["lights"] else LABEL_RU.get(d["label"], "судно")
    return (f"Мостик: {R.contact(d['designation'])}, {what}, пеленг {R.course(d['bearing'])}, "
            f"дистанция {R.dec(d['range'], R.MILE)}.")


RU_PHRASES = {
    "bridge.manned": lambda d: "Рубочный люк открыт, сигнальщики на мостике."
                               + (f" Волнение {R.count(d['sea'], ('балл', 'балла', 'баллов'))}."
                                  if "sea" in d else ""),
    "bridge.sea": lambda d: f"Мостик: волнение {'усиливается' if d['up'] else 'стихает'}, "
    f"{R.count(d['sea'], ('балл', 'балла', 'баллов'))}.",
    "bridge.clearing": lambda d: "Все вниз! Задраить рубочный люк!",
    "bridge.shut": lambda d: "Рубочный люк задраен, мостик пуст. К погружению готовы.",
    "bridge.contact": _contact_ru,
    "bridge.aircraft": lambda d: f"Мостик: самолёт, пеленг {R.course(d['bearing'])}"
    + (", низко над водой!" if d["low"] else "."),
    "bridge.station": lambda d: f"Мостик: огни на льду, пеленг {R.course(d['bearing'])}. Это станция!",
    "bridge.suggest.dive": lambda d: f"{R.CAPTAIN}, мостик. Предлагаю срочное погружение.",
    "bridge.land": lambda d: f"Мостик: вижу берег, пеленг {R.course(d['bearing'])}.",
    "bridge.column": lambda d: f"Мостик: столб воды, пеленг {R.course(d['bearing'])}. "
    "Глубинные бомбы!",
    "bridge.hit": lambda d: f"Мостик: взрыв, пеленг {R.course(d['bearing'])}! Огонь и дым.",
}
phrases.register_ru(RU_PHRASES)


class BridgeWatch(Station):
    """Utkiken på bryggan i ytläge. Vakthavande har bryggan, därför samma roll."""
    REACHES_WORLD = True        # utkiken på bryggan (sensor)
    role = Role.OFFICER

    def __init__(self, game):
        super().__init__(game)
        # egen slump, så att utkiken inte flyttar resten av spelets dragningar;
        # fröet ur spelets (oanvända) tillstånd, alltså samma för samma frö
        self.rng = game.rng_for("bridge")
        self._hatch = self.own.sys.bridge
        self._judges = Judges(JUDGE_EVERY_S)
        self._seen: dict[str, int] = {}
        self._ice_f: tuple[int, list[float]] = (-10**9, [])
        self._land_f: tuple[int, float] = (-10**9, 1.0)
        self._events: list[tuple[int, SightedObject]] = []    # (syns till, händelsen)
        self._sea_said: int | None = None   # sjögången utkiken senast sagt


    def update(self) -> None:
        self._watch_hatch()
        if self.own.sys.bridge != "manned":
            self._events.clear()
            return
        new = self._watch_events()
        if new or self.now % LOOK_EVERY_S == 0:
            self._look()
        sea = self.world.env.sea_state       # utkiken ser sjön ändras (vädret)
        if self._sea_said is not None and sea != self._sea_said:
            self.say("bridge.sea", {"sea": sea, "up": sea > self._sea_said})
        self._sea_said = sea

    # --- luckan ---------------------------------------------------------------------
    def _watch_hatch(self) -> None:
        b = self.own.sys.bridge
        if b == self._hatch:
            return
        prev, self._hatch = self._hatch, b
        if b == "manned":
            self._sea_said = self.world.env.sea_state
            self.say("bridge.manned", {"sea": self._sea_said})
        elif b == "clearing":
            self.game.bus.publish(BridgeSighted(self.now, None))
            self.say("bridge.clearing", {"seconds": BRIDGE_CLEAR_S}, kind="ack")
        elif b == "shut" and prev == "clearing":
            self.say("bridge.shut", kind="done")

    def system_items(self) -> list:
        s = self.own.sys
        left = max(0, s.bridge_t - self.now)
        text, state = {"manned": ("bemannad, luckan öppen", INFO),
                       "manning": (f"luckan öppnas, {left} s", INFO),
                       "clearing": (f"utryms, {left} s", WARN)}.get(s.bridge, ("luckan stängd", OK))
        return [Gauge("NAVIGATION", "Bryggan", text, state)]

    # --- utkiken --------------------------------------------------------------------
    def _judgement(self, key: str) -> tuple[Judgement, bool]:
        """Bedömningen för ett föremål; sant om den är ny (dragen nu)."""
        return self._judges.get(key, self.now, self.rng)

    def _call_out(self, key: str) -> bool:
        """Sant om föremålet ska ropas ut: nytt, eller ur sikte länge."""
        last = self._seen.get(key)
        self._seen[key] = self.now
        return last is None or self.now - last > RESIGHT_S

    def _look(self) -> None:
        world, now = self.world, self.now
        light = world.env.light(now)
        day, vis = light.daylight, light.visibility_nm
        objects: list[SightedObject] = []
        for v in world.contacts:
            if v.kind == "torpedo" and not v.sunk and day:
                if (w := self._wake(v)) is not None:
                    objects.append(w)
                continue
            if v.side == "own" or v.sunk or getattr(v, "gone", False):
                continue
            r = world.true_range(v)
            if r <= vis and not world.in_sight(v.state.x, v.state.y):
                continue                        # bakom land
            if v.is_ship and v.depth < 10 and r <= vis:
                if not detectable(v.kind, r, EYE_BRIDGE_M, BINOC_POWER,
                                  wave_height_m(world.env.sea_state)):
                    continue                    # under horisonten eller för litet i kikaren
                objects.append(self._ship(v, r, light))
            elif v.kind == "aircraft" and day and r <= vis:
                objects.append(self._aircraft(v, r))
            elif v.kind == "station" and r <= STATION_LIGHT_NM:
                objects.append(self._station(v, r))
        for sp in world.spawners:
            if hasattr(sp, "periscope_view"):
                for type_, d in sp.periscope_view(world, self.rng):
                    if obj := _view_object(type_, d):
                        objects.append(obj)
        self._events = [(until, o) for until, o in self._events if until >= now]
        objects += [o for _, o in self._events]
        self.game.bus.publish(BridgeSighted(now, PeriscopePicture(
            now, day, vis, self.own.state.course, "brygga", tuple(objects), None, self._ice(),
            self._land(vis), **sky_of(light),
            sea_state=world.env.sea_state)))

    # --- land, händelser och torpedspår ------------------------------------------------
    def _seen_at(self, x: float, y: float, key: str | None) -> tuple[float, float]:
        """Bäring och avstånd med ögat till en punkt. Med nyckel hålls bedömningen en
        minut (något som rör sig); utan dras den en gång (en händelse)."""
        o = self.own.state
        if key is None:
            g = self.rng.gauss
            j = Judgement(self.now, g(0, 1), g(0, 1), g(0, 1), 0.0, 0.0)
        else:
            j, _ = self._judgement(key)
        r = distance(o.x, o.y, x, y)
        b = norm360(bearing_to(o.x, o.y, x, y) + j.bearing * BEARING_SIGMA)
        return b, max(0.02, r * (1 + j.range_rel * RANGE_REL_SIGMA) + j.range_abs * RANGE_ABS_SIGMA)

    def _land(self, reach: float) -> tuple[LandBearing, ...]:
        """Stranden i varje riktning ut till sikten (landet är högre än horisonten)."""
        o = self.own.state
        shore = shore_ranges(self.world.env.seabed, o.x, o.y, reach)
        if not shore:
            return ()
        t, f = self._land_f
        if self.now - t >= JUDGE_EVERY_S:
            f = 1 + self.rng.gauss(0, RANGE_REL_SIGMA)
            self._land_f = (self.now, f)
        out = [LandBearing(b, max(0.05, r * f)) for b, r in shore]
        if out:
            near = min(out, key=lambda lb: lb.range_nm)
            if self._call_out("land"):
                self.say("bridge.land", {"bearing": near.bearing, "range": near.range_nm},
                         kind="contact", quality=Quality.GOD)
        return tuple(out)

    def _watch_events(self) -> bool:
        """Plask, vattenpelare och träffar (`lookout.visible_events`). Sant om något nytt syntes."""
        now = self.now
        new = False
        for ev in visible_events(self.world, EYE_BRIDGE_M):
            b, r_meas = self._seen_at(ev.x, ev.y, None)
            label = {"splash": "plask", "column": "vattenpelare", "hit": "explosion"}[ev.kind]
            detail = "kärnladdning" if ev.nuclear else ("övning" if ev.practice else "")
            o = SightedObject(ev.kind, label, b, r_meas, range_quality(r_meas, RANGE_REL_SIGMA * r_meas),
                              detail=detail, seen_t=now)
            self._events.append((now + EVENT_S[ev.kind], o))
            self.game.bus.publish(EventSighted(now, ev.kind, b, r_meas, ev.practice, "brygga"))
            new = True
            if ev.kind == "column" and self._call_out("column"):
                self.say("bridge.column", {"bearing": b, "range": r_meas, "practice": ev.practice},
                         kind="contact", alarm=not ev.practice)
            elif ev.kind == "hit":
                self.say("bridge.hit", {"bearing": b, "range": r_meas, "nuclear": ev.nuclear},
                         kind="contact", alarm=True)
        return new

    def _wake(self, t) -> SightedObject | None:
        """Spåret efter en ångtorped (inte den eldrivna) på nära håll i dagsljus."""
        if t.spec.key == "SET-53" or getattr(t, "done", False):
            return None
        r = self.world.true_range(t)
        if r > WAKE_NM:
            return None
        b, r_meas = self._seen_at(t.state.x, t.state.y, t.id)
        course = t.state.course
        return SightedObject("wake", "torpedspår", b, r_meas, range_quality(r_meas, 0.15 * r_meas),
                             aob=angle_on_bow(b, course), course=course, seen_t=self.now)

    def _ice(self) -> tuple[IceBearing, ...]:
        view = ice_view(self.world)
        t, f = self._ice_f
        if self.now - t >= JUDGE_EVERY_S or len(f) != len(view):
            f = [self.rng.uniform(0.85, 1.15) for _ in view]
            self._ice_f = (self.now, f)
        return tuple(IceBearing(b, None if e is None else e * k, ridged)
                     for (b, e, ridged), k in zip(view, f))

    def _ship(self, v, r: float, light) -> SightedObject:
        world = self.world
        desig = self.game.station(SonarRoom).sensor.designate(v.id)
        j, fresh = self._judgement(v.id)
        full, short = SIGHTED.get(v.kind, ("ytfartyg", "fartyg"))
        day = light.phase == "dag"
        sil = light.silhouette(world.true_bearing(v))     # siluett, eller bara lanternor
        sea = world.env.sea_state
        part = visible_part(v.kind, r, EYE_BRIDGE_M, wave_height_m(sea)) if sil else "ljus"
        c_sig = AOB_SIGMA[part] if day or not sil else min(AOB_SIGMA["mastoppar"],
                                                           AOB_SIGMA[part] * TWILIGHT_AOB_F)
        f = sea_sigma_f(sea)                              # grov sjö: sämre bedömning
        c_sig = min(c_sig * f, 60.0)
        known = sil and light.daylight                    # klassning god ur siluetten
        bearing = norm360(world.true_bearing(v) + j.bearing * BEARING_SIGMA)
        rel, ab = BINOC_RANGE_REL * f, BINOC_RANGE_ABS * f
        r_meas = max(0.05, r * (1 + j.range_rel * rel) + j.range_abs * ab)
        r_sig = rel * r_meas + ab                         # utkiken vet bara sitt mätta avstånd
        course = norm360(v.state.course + j.course * c_sig)
        speed = max(0, round(v.state.speed + j.speed * SPEED_SIGMA))
        aob = angle_on_bow(bearing, course)
        ls = () if day else lights(aob)
        if fresh:
            self._plot(desig, full if sil else "ytfartyg", known, bearing, r_meas, r_sig,
                       course, c_sig, speed)
        if self._call_out(v.id):
            self.say("bridge.contact", {"designation": desig, "label": short, "bearing": bearing,
                                        "range": r_meas, "visible": part, "course": course,
                                        "speed": speed, "lights": list(ls)},
                     kind="contact", quality=range_quality(r_meas, r_sig))
        if v.kind == "destroyer" and r_meas < CLOSE_NM:
            self.suggest("bridge_dive", "bridge.suggest.dive",
                         {"reason": f"{desig} är nära, cirka {nm(r_meas)} sjömil.",
                          "depth": DIVE_DEPTH},
                         order=f"djup {DIVE_DEPTH}", cooldown=300, alarm=True)
        return SightedObject(v.kind, short, bearing, r_meas, range_quality(r_meas, r_sig),
                             designation=desig, visible=part, aob=aob,
                             aob_quality=aob_quality(c_sig), course=course, speed=speed,
                             lights=ls, seen_t=self.now)

    def _plot(self, desig: str, label: str, day: bool, bearing: float, r_meas: float,
              r_sig: float, course: float, c_sig: float, speed: float) -> None:
        """En observation till plottet: bäring, avstånd, kurs och fart med utkikens σ."""
        bus, now = self.game.bus, self.now
        tr = self.game.knowledge.tracks.get(desig)
        if tr is None:
            bus.publish(ContactDetected(now, desig, bearing, label,
                                        Quality.GOD if day else Quality.OSAKER))
        elif day and tr.class_quality < Quality.GOD:
            bus.publish(ClassificationChanged(now, desig, label, Quality.GOD))
        ex, ey = self.game.own_position_estimate()
        bus.publish(BearingObserved(now, BearingObs(
            now, bearing, BEARING_SIGMA, ex, ey, self.own.state.course, designation=desig,
            range_nm=r_meas, range_sigma=r_sig, source="brygga", course_obs=course,
            course_sigma=c_sig, speed_obs=speed, speed_sigma=SPEED_SIGMA)))

    def _aircraft(self, v, r: float) -> SightedObject:
        world = self.world
        j, _ = self._judgement(v.id)
        bearing = norm360(world.true_bearing(v) + j.bearing * 2.0)
        r_meas = max(0.2, r * (1 + 0.2 * j.range_rel))
        low = v.altitude < 150
        if self._call_out(v.id):
            self.say("bridge.aircraft", {"bearing": bearing, "range": r_meas, "low": low},
                     kind="contact", alarm=True)
        self.suggest("bridge_dive_air", "bridge.suggest.dive",
                     {"reason": "Flygplan i sikte.", "depth": DIVE_DEPTH},
                     order=f"djup {DIVE_DEPTH}", cooldown=300, alarm=True)
        return SightedObject("aircraft", "flygplan", bearing, r_meas, Quality.OSAKER,
                             detail="lågt" if low else "")

    def _station(self, v, r: float) -> SightedObject:
        world = self.world
        j, fresh = self._judgement(v.id)
        bearing = norm360(world.true_bearing(v) + j.bearing * BEARING_SIGMA)
        r_sig = 0.1 * r + 0.03
        r_meas = max(0.05, r + j.range_rel * r_sig)
        if fresh:
            ex, ey = self.game.own_position_estimate()
            dx, dy = velocity(bearing, r_meas * 3600)      # en timme i r_meas knop = r_meas nm
            self.game.bus.publish(PositionReported(self.now, "Nord-7", ex + dx, ey + dy,
                                                   0.1 * r_meas + 0.05, self.now, "brygga"))
        if self._call_out(v.id):
            self.say("bridge.station", {"bearing": bearing, "range": r_meas}, kind="contact",
                     quality=Quality.GOD, alarm=True)
        return SightedObject("station", "drivstation", bearing, r_meas,
                             range_quality(r_meas, r_sig), lights=("ljus",))
