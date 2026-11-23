"""Periskopet: vakthavandes öga ovanför ytan, i realtid.

Masten är uppe (`OwnSystems.periscope_until`) under ett svep, en kort titt eller så
länge kaptenen håller den uppe. Okularet ser FOV_HALF_DEG åt var sida om sin bäring
(`train`, sann bäring):
- svep (`periskop`): vakthavande vrider runt från rätt förut på LOOK_S sekunder, sedan ner
- kort titt (`periskop 047`, `periskop S-3`): mot bäringen i SHORT_LOOK_S sekunder
- hålla (`periskop upp` … `periskop ned`): okularet står där kaptenen vrider det
  (`vrid periskop 047`); masten är uppe tills den fälls eller inte kan vara uppe
  (under periskopdjup, för hög fart, is, skadat periskop)

I ytläge med bryggan bemannad tar vakthavande kikaren på bryggan i stället (`optic`
"kikare"): samma order, men ingen mast och ingen fartgräns, och okularet visar bryggans
bild (`Knowledge.bridge`) inom synfältet. Kikaren mäter inget eget: utkiken har redan
ropat ut och gett plottet sina observationer, så bilden och siffrorna är bryggans.
Utryms bryggan fälls kikaren.

Periskopet är en sensor: varje sekund läser det World för det som ligger i okularet, och
varannan sekund publiceras en `PeriscopeSighted` (live). När svepet eller titten är klar
kommer en sista bild (live=False). Bedömningsfelen (`Judges`) dras en gång per hissning
och föremål (i hålläge om var JUDGE_EVERY_S), och då får plottet en observation. Samma
fel ritas i bilden, så bilden och rapporterna stämmer. Nytt i okularet ropas ut en gång
per hissning. Egen slump, så att periskopet inte flyttar resten av spelets dragningar.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .. import phrases
from .. import russian as R
from ..arctic import STATION_LIGHT_NM
from ..crew import Role
from ..events import (OwnActionLogged, BearingObserved, ClassificationChanged, ContactDetected, EventSighted,
                      PeriscopeBlocked,
                      PeriscopeSighted, PositionReported)
from ..fmt import fmt_course, kn, nm
from ..geo import angle_diff, norm360, velocity
from ..ice import ice_view
from ..orders import DESIG, CommandSpec, Order, Unknown, desig
from ..ownship import PERISCOPE_DEPTH
from .sweep import SweepCalls
from ..periscope import (EVENT_S, crest_m, sea_sigma_f, wave_height_m, sky_of, AOB_SIGMA, TWILIGHT_AOB_F, EYE_BRIDGE_M, EYE_PERISCOPE_M, SECTOR_HALF_DEG, IceBearing,
                         LandBearing,
                         HIGH, LOW, OPTICS, Optic, detectable,
                         Judges, PeriscopePicture, SightedObject, angle_on_bow, aob_quality,
                         carried, lights, range_quality, visible_part)
from ..reports import Quality
from ..seabed import shore_ranges
from ..tma import BearingObs
from .base import Station
from .lookout import visible_events
from .bridge import sea_words
from .officer import PHOTO_TARGET_KIND, SIGHTED, OfficerStation, _view_object, mast_refusal
from .sonar_room import SonarRoom

LOOK_S = 15                  # ett svep runt
SHORT_LOOK_S = 8             # kort titt mot en bäring: mindre tid med masten uppe
FOV_HALF_DEG = SECTOR_HALF_DEG
SWEEP_DEG_S = 360.0 / LOOK_S
FRAME_S = 2                  # en bild så här ofta medan masten är uppe
JUDGE_EVERY_S = 60           # i hålläge: ny bedömning (och observation) så här ofta
ICE_EVERY_S = 60
LAND_EVERY_S = 30           # stranden mäts om så här ofta medan masten är uppe
LAND_RESIGHT_S = 600        # land ur sikte så länge ropas ut igen
# bäring och avstånd efter förstoringen (`periscope.OPTICS`): låg 1° och 15 % + 0,05 nm (ögonmått),
# hög 0,5° och 8 % + 0,03 nm (stadimetern)
SPEED_SIGMA = 2.0            # fart ur bogvåg och varvtal, knop
CLOSE_NM = 3.0               # en jagare så nära: föreslå djupt
HOLD_MAX_KN = 7              # fortare vibrerar masten och ger svall
RECALL_S = 300               # samma fartyg, oförändrat, så nyss utropat: bara en kort rapport
RECALL_COURSE_DEG = 15
RECALL_SPEED_KN = 3
MAST_WARN_S = 60             # masten uppe så länge med ett hot i plottet: föreslå periskop ned
MAST_WARN_EVERY_S = 180
COLUMN_RESIGHT_S = 300       # vattenpelare ropas ut högst så här ofta (en serie sjunkbomber)
EVENT_LABEL = {"splash": "plask", "column": "vattenpelare", "hit": "explosion"}


@dataclass(frozen=True)
class PeriscopeLook(Order):
    bearing: float | None = None     # kort titt mot en bäring
    target: str | None = None        # kort titt mot en kontakts senaste bäring


@dataclass(frozen=True)
class PeriscopeHold(Order):
    pass


@dataclass(frozen=True)
class PeriscopeDown(Order):
    pass


@dataclass(frozen=True)
class PeriscopePower(Order):
    """Förstoringen i hålläge. Kaptenens hand på periskopet, inte en order till besättningen."""
    INSTRUMENT = True
    power: str = "låg"


def _power(word: str) -> str:
    return "hög" if word.lower().startswith("h") else "låg"


def _bearing(m, build) -> Order:
    """Bäringen 000–360 (360 är norr); `periskop 400` ska inte tyst bli 040."""
    b = int(m[1])
    return build(b % 360) if b <= 360 else Unknown("", "bäringen måste vara 000–359")


@dataclass(frozen=True)
class PeriscopeTrain(Order):
    """Vrid okularet. Kaptenens hand på periskopet, inte en order till besättningen."""
    INSTRUMENT = True
    bearing: float | None = None
    target: str | None = None


def _contact(d: dict) -> str:
    how = "enligt stadimetern" if d.get("power") == "hög" else "cirka"
    out = (f"{d['designation']}: {d['label']} i bäring {fmt_course(d['bearing'])}, avstånd {how} "
           f"{nm(d['range'])} sjömil.")
    if d.get("course") is None:             # till ankars
        return out + " Ligger still."
    return out + (f" Vinkel på bogen ger kurs ungefär {fmt_course(d['course'])}, "
                  f"fart cirka {kn(d['speed'])} knop.")


def _lights_contact(d: dict) -> str:
    if d.get("course") is None:             # ankarljus: ligger still
        return (f"{d['designation']}: ankarljus i bäring {fmt_course(d['bearing'])}, avstånd cirka "
                f"{nm(d['range'])} sjömil. Ligger still.")
    return (f"{d['designation']}: lanternor i bäring {fmt_course(d['bearing'])}, avstånd cirka "
            f"{nm(d['range'])} sjömil. Kurs ungefär {fmt_course(d['course'])}.")


PHRASES = {
    "off.periscope.up": lambda d: "Periskop upp." if d.get("bearing") is None
    else f"Periskop upp, kort titt i bäring {fmt_course(d['bearing'])}.",
    "off.periscope.hold": lambda d: "Periskop upp. Det står uppe tills ni fäller det, kapten.",
    "off.periscope.down": lambda d: "Periskop ner.",
    "off.periscope.is_down": lambda d: "Kapten, periskopet är nere.",
    "off.periscope.lowered": lambda d: f"Periskop ner, {d['reason']}.",
    "off.periscope.contact": lambda d: ("Periskop, hög förstoring: " if d.get("power") == "hög"
                                        else "Periskop: ")
    + (_lights_contact(d) if d.get("lights") else _contact(d)),
    "off.periscope.power": lambda d: "Hög förstoring." if d["power"] == "hög" else "Låg förstoring.",
    "off.binoculars.power": lambda d: "Kikaren har bara en förstoring, kapten.",
    "off.periscope.again": lambda d: f"Periskop: {d['designation']} som förut, i bäring "
    f"{fmt_course(d['bearing'])}, cirka {nm(d['range'])} sjömil.",
    "off.suggest.mast_down": lambda d: f"Kapten, vakthavande. Periskopet har varit uppe i "
    f"{d['seconds'] // 60} minut{'er' if d['seconds'] >= 120 else ''} och plottet har "
    f"{d['designation']}. Masten kan synas på deras radar. Föreslår periskop ned.",
    "off.periscope.none": lambda d: (f"Periskop: inget i sikte i bäring {fmt_course(d['sector'])}. "
                                     if d.get("sector") is not None else "Periskop: inget i sikte. ")
    + f"{'Dagsljus' if d['day'] else 'Mörkt'}, sikt cirka {kn(d['visibility'])} sjömil. Periskop ner.",
    "off.periscope.station": lambda d: f"Periskop: ljus på isen i bäring {fmt_course(d['bearing'])}, "
    f"avstånd cirka {nm(d['range'])} sjömil. Baracker och radiomaster. Det måste vara Nord-7! "
    "Inga rörelser, inget ljus i fönstren.",
    "off.suggest.surface_station": lambda d: "Kapten, vakthavande. Vi har öppet vatten ovanför och "
    f"Nord-7 på {nm(d['range'])} sjömil, nära nog att gå över isen. Föreslår ytläge.",
    "off.binoculars.up": lambda d: "Kikaren, svep runt horisonten." if d.get("bearing") is None
    else f"Kikaren mot bäring {fmt_course(d['bearing'])}.",
    "off.binoculars.hold": lambda d: "Jag håller kikaren, kapten.",
    "off.binoculars.down": lambda d: "Kikaren ner.",
    "off.binoculars.none": lambda d: (f"Kikaren: inget i sikte i bäring {fmt_course(d['sector'])}. "
                                      if d.get("sector") is not None else "Kikaren: inget i sikte. ")
    + f"{'Dagsljus' if d['day'] else 'Mörkt'}, sikt cirka {kn(d['visibility'])} sjömil.",
    "off.periscope.land": lambda d: f"Periskop: land i sikte, närmast i bäring "
    f"{fmt_course(d['bearing'])}, cirka {nm(d['range'])} sjömil.",
    "off.periscope.column": lambda d: f"Periskop: vattenpelare i bäring {fmt_course(d['bearing'])}, "
    f"cirka {nm(d['range'])} sjömil. Sjunkbomber" + (", övningsladdningar." if d["practice"] else "!"),
    "off.periscope.hit": lambda d: f"Periskop: explosion i bäring {fmt_course(d['bearing'])}, cirka "
    f"{nm(d['range'])} sjömil! " + ("Ett eldklot, kapten!" if d["nuclear"] else "Eld och rök."),
    "off.periscope.sea": lambda d: f"Periskop: sjön har {'ökat' if d['up'] else 'mojnat'} sedan förra "
    f"titten. {sea_words(d['sea'])}.",
    "off.periscope.washed": lambda d: "Sjön sköljer över periskopet, kapten. Bilden kommer och går.",
    "off.periscope.aircraft": lambda d: f"Periskop: flygplan i bäring {fmt_course(d['bearing'])}, "
    f"cirka {nm(d['range'])} sjömil, " + ("lågt över vattnet" if d["low"] else "på höjd")
    + ". Tvåmotorigt patrullplan.",
}
phrases.register(PHRASES)

RU_PHRASES = {
    "off.periscope.up": lambda d: "Есть, поднять перископ.",
    "off.periscope.power": lambda d: "Есть, большое увеличение." if d["power"] == "hög"
    else "Есть, малое увеличение.",
    "off.binoculars.power": lambda d: "У бинокля одно увеличение.",
    "off.periscope.hold": lambda d: "Есть, перископ поднят.",
    "off.periscope.down": lambda d: "Есть, опустить перископ.",
    "off.periscope.is_down": lambda d: f"{R.CAPTAIN}, перископ опущен.",
    "off.periscope.lowered": lambda d: "Перископ опущен.",
    "off.periscope.contact": lambda d: f"Перископ: {R.contact(d['designation'])}, пеленг "
    f"{R.course(d['bearing'])}, дистанция {R.dec(d['range'], R.MILE)}.",
    "off.periscope.none": lambda d: "Перископ: горизонт чист. Перископ опущен.",
    "off.periscope.land": lambda d: f"Перископ: вижу берег, пеленг {R.course(d['bearing'])}.",
    "off.periscope.again": lambda d: f"Перископ: {R.contact(d['designation'])} без изменений, "
    f"пеленг {R.course(d['bearing'])}.",
    "off.suggest.mast_down": lambda d: f"{R.CAPTAIN}, вахтенный офицер. Перископ поднят давно. "
    "Предлагаю опустить перископ.",
    "off.periscope.station": lambda d: f"Перископ: огни на льду, пеленг {R.course(d['bearing'])}. "
    "Это станция!",
    "off.suggest.surface_station": lambda d: f"{R.CAPTAIN}, вахтенный офицер. Станция рядом. "
    "Предлагаю всплыть.",
    "off.binoculars.up": lambda d: "Есть, бинокль.",
    "off.binoculars.hold": lambda d: "Есть, держу бинокль.",
    "off.binoculars.down": lambda d: "Бинокль убран.",
    "off.binoculars.none": lambda d: "Горизонт чист.",
    "off.periscope.column": lambda d: f"Перископ: столб воды, пеленг {R.course(d['bearing'])}. "
    + ("Учебные бомбы." if d["practice"] else "Глубинные бомбы!"),
    "off.periscope.hit": lambda d: f"Перископ: взрыв, пеленг {R.course(d['bearing'])}! "
    + ("Огненный шар!" if d["nuclear"] else "Огонь и дым."),
    "off.periscope.sea": lambda d: f"Перископ: волнение {'усилилось' if d['up'] else 'стихло'}, "
    f"{R.count(d['sea'], ('балл', 'балла', 'баллов'))}.",
    "off.periscope.washed": lambda d: f"{R.CAPTAIN}, перископ захлёстывает волной.",
    "off.periscope.aircraft": lambda d: f"Перископ: самолёт, пеленг {R.course(d['bearing'])}"
    + (", низко над водой!" if d["low"] else "."),
}
phrases.register_ru(RU_PHRASES)


class PeriscopeWatch(Station):
    """Periskopet. Vakthavande sköter det, därför samma roll."""
    REACHES_WORLD = True        # periskopet (sensor)
    role = Role.OFFICER
    MAST_ORDERS = (PeriscopeLook,)
    COMMANDS = [
        # resten (upp, ned, vrid, förstoring) sköts med tangenterna i periskopbilden
        CommandSpec(r"periskop|titta", lambda m: PeriscopeLook(), "periskop (svep)"),
        CommandSpec(rf"(?:periskop|titta)\s+(?:mot\s+)?{DESIG}",
                    lambda m: PeriscopeLook(target=desig(m[1])), "periskop S-3 (eller 047: kort titt)"),
        CommandSpec(r"(?:periskop|titta)\s+(?:mot\s+|bäring\s+|baring\s+)?(\d{1,3})",
                    lambda m: _bearing(m, lambda b: PeriscopeLook(bearing=b))),
        CommandSpec(r"periskop upp|håll periskopet uppe|hall periskopet uppe",
                    lambda m: PeriscopeHold()),
        CommandSpec(r"periskop (?:ned|ner|in)|periskopet (?:ned|ner)|fäll periskopet|fall periskopet",
                    lambda m: PeriscopeDown()),
        CommandSpec(r"(?:förstoring|forstoring)\s+(hög|hog|låg|lag)",
                    lambda m: PeriscopePower(_power(m[1]))),
        CommandSpec(r"(hög|hog|låg|lag)\s+(?:förstoring|forstoring)",
                    lambda m: PeriscopePower(_power(m[1]))),
        CommandSpec(rf"vrid periskop(?:et)?\s+(?:mot\s+)?{DESIG}",
                    lambda m: PeriscopeTrain(target=desig(m[1]))),
        CommandSpec(r"vrid periskop(?:et)?\s+(?:mot\s+|bäring\s+|baring\s+)?(\d{1,3})",
                    lambda m: _bearing(m, lambda b: PeriscopeTrain(bearing=b))),
    ]

    def __init__(self, game):
        super().__init__(game)
        # egen slump (fröet ur spelets oanvända tillstånd, skilt från bryggans)
        self.rng = game.rng_for("periscope")
        self.mode: str | None = None        # sweep, look, hold; None = nere
        self.optic = "periskop"             # periskop, eller kikare från bryggan
        self.train = 0.0                    # okularets bäring (sann)
        self.power = "låg"                  # förstoringen i hålläge (svep alltid låg, titt hög)
        self.t_end: int | None = None
        self.last_look_t = -10**9
        self._start_t = 0                   # när svepet, titten eller hållet började
        self._up_t = 0                      # när masten hissades (en hissning = en bedömning)
        self._sweep_from = 0.0
        self._judges = Judges(JUDGE_EVERY_S)
        self._last_call: dict[str, tuple[int, float, float]] = {}   # (t, kurs, fart) senast utropat
        self._land_seen_t = -10**9          # senast land syntes i okularet
        self._sea_seen = self.world.env.sea_state   # sjögången man såg senast (vid start: känd)
        self._column_t = -10**9             # senast en vattenpelare ropades ut
        self._sweep_calls = SweepCalls(self, "periscope")
        self._new_raising()


    @property
    def up_s(self) -> int:
        """Så länge masten varit uppe i denna hissning (0 när den är nere)."""
        return 0 if self.mode is None else self.now - self._up_t

    @property
    def search(self) -> Optic:
        """Förstoringen man letar med: svepet och titten söker i låg, hålläget i den valda."""
        return OPTICS[self.power] if self.mode == "hold" else LOW

    @property
    def measure(self) -> Optic:
        """Förstoringen man mäter med: titten mäter i hög (stadimetern), svepet i låg."""
        return HIGH if self.mode == "look" else OPTICS[self.power] if self.mode == "hold" else LOW

    @property
    def shown_power(self) -> str:
        """Förstoringen i okularet just nu (för vyn)."""
        return self.measure.key if self.mode is not None else self.power

    def status_fields(self) -> dict:
        return {"periscope": self.mode, "periscope_train": self.train, "periscope_up_s": self.up_s,
                "periscope_optic": self.optic, "periscope_power": self.shown_power}

    @property
    def busy(self) -> bool:
        """Ett svep eller en titt pågår (inte hålläge)."""
        return self.mode in ("sweep", "look")

    @property
    def binoculars(self) -> bool:
        """Bryggan är bemannad: vakthavande tittar med kikaren, masten behövs inte."""
        return self.own.surfaced and self.own.sys.bridge == "manned"

    def _say(self, key: str, data: dict | None = None, **kw) -> None:
        """off.periscope.x eller, med kikaren, off.binoculars.x."""
        if self.optic == "kikare":
            key = key.replace("off.periscope.", "off.binoculars.")
        self.say(key, data, **kw)

    def _new_raising(self) -> None:
        self._before: PeriscopePicture | None = None
        self._covered: set[int] = set()
        self._seen: dict[str, SightedObject] = {}
        self._called: set[str] = set()
        self._views: list | None = None
        self._ice: tuple[IceBearing, ...] = ()
        self._ice_t = -10**9
        self._land: tuple = ()
        self._land_by: dict[float, LandBearing] = {}    # stranden i de riktningar okularet sett
        self._shore: dict[float, float] = {}            # sann bäring -> avstånd (senaste mätning)
        self._shore_t = -10**9
        self._land_f: float | None = None               # avståndsbedömningens fel, en per hissning
        self._events: list[tuple[int, SightedObject]] = []    # (syns till, händelsen)
        self._washed_said = False                       # "sjön sköljer över" en gång per hissning

    # --- order ------------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        match order:
            case PeriscopeLook(bearing=bearing, target=target):
                if not self._may_raise():
                    return
                if target is not None:
                    bearing = self._target_bearing(target)
                    if bearing is None:
                        return
                look_s = LOOK_S if bearing is None else SHORT_LOOK_S
                self._raise("sweep" if bearing is None else "look",
                            self.own.state.course if bearing is None else bearing, look_s)
                self._say("off.periscope.up", {"bearing": bearing}, kind="ack")
            case PeriscopeHold():
                if self.mode != "hold" and not self._may_raise():
                    return
                self._raise("hold", self.train if self.mode else self.own.state.course, None)
                self._say("off.periscope.hold", kind="ack")
            case PeriscopeDown():
                if self.mode is None:
                    self.say("off.periscope.is_down", kind="ack")
                    return
                self._lower(final=True)
                self._say("off.periscope.down", kind="ack")
            case PeriscopePower(power=power):
                self.power = power
                self._say("off.periscope.power", {"power": power}, kind="ack")
            case PeriscopeTrain(bearing=bearing, target=target):
                if self.mode is None:
                    self.say("off.periscope.is_down", kind="ack")
                    return
                if target is not None:
                    bearing = self._target_bearing(target)
                    if bearing is None:
                        return
                if self.mode != "hold":         # kaptenen tar periskopet: det står kvar uppe
                    self._raise("hold", self.train, None)
                self.train = float(bearing)

    def _may_raise(self) -> bool:
        if self.binoculars:
            return True
        if reason := mast_refusal(self, "periskopet"):
            self.say("off.refused", {"reason": reason})
            if self.own.state.depth <= PERISCOPE_DEPTH and not self.masts_free:
                self.game.bus.publish(PeriscopeBlocked(self.now, "is"))
            return False
        return True

    def _target_bearing(self, target: str) -> float | None:
        tr = self.game.knowledge.track(target)
        if tr is None or tr.last_bearing is None:
            self.say("off.refused", {"reason": f"vi har ingen bäring på {target}"})
            return None
        return tr.last_bearing

    def _raise(self, mode: str, train: float, seconds: int | None) -> None:
        sys = self.own.sys
        if self.mode is None or mode != "hold":     # en ny titt: nya bedömningar
            self._new_raising()
            self.optic = "kikare" if self.binoculars else "periskop"
            self._before = self.game.knowledge.periscope
            self._up_t = self.now
            if self.optic == "periskop":
                self.game.bus.publish(OwnActionLogged(self.now, "periscope"))
        self.mode = mode
        self.train = float(train)
        self._sweep_from = float(train)
        self._start_t = self.now
        self.last_look_t = self.now
        self.t_end = None if seconds is None else self.now + seconds
        if self.optic == "periskop":
            sys.periscope_until = max(sys.periscope_until, self.now + (seconds or 1))

    def _lower(self, final: bool) -> None:
        if final and self._covered:
            self._publish(live=False)
        self.mode = None
        self.t_end = None
        sys = self.own.sys
        if self.optic == "periskop" and self.game.station(OfficerStation).photo_done_t is None:
            sys.periscope_until = min(sys.periscope_until, self.now)

    # --- varje sekund -------------------------------------------------------------------
    def update(self) -> None:
        self._sweep_calls.flush()
        if self.mode is None:
            return
        st, sys = self.own.state, self.own.sys
        if self.optic == "kikare":
            if not self.binoculars:
                self.say("off.binoculars.down", kind="ack")
                self.mode = self.t_end = None
                return
            if self.mode == "sweep":
                done = min(self.now - self._start_t, LOOK_S)
                self.train = norm360(self._sweep_from + SWEEP_DEG_S * done)
            self._observe_bridge()
            self._step()
            return
        if st.depth > PERISCOPE_DEPTH + 1:
            if self.mode == "hold":
                self.say("off.periscope.lowered", {"reason": "vi är under periskopdjup"})
            self.mode = self.t_end = None           # svep och titt: ingen bild
            return
        if self.mode == "hold":
            reason = mast_refusal(self, "periskopet")
            if reason is not None:
                self.say("off.periscope.lowered", {"reason": reason})
                self._lower(final=True)
                return
            sys.periscope_until = max(sys.periscope_until, self.now + 1)
            self._mast_watch()
        elif self.mode == "sweep":
            done = min(self.now - self._start_t, LOOK_S)
            self.train = norm360(self._sweep_from + SWEEP_DEG_S * done)
        if self._washed():
            if not self._washed_said:
                self._washed_said = True
                self.say("off.periscope.washed", kind="info")
        else:
            self._observe()
            sea = self.world.env.sea_state  # sjön ändrats sedan förra titten (vädret)
            if sea != self._sea_seen:
                self.say("off.periscope.sea", {"sea": sea, "up": sea > self._sea_seen})
                self._sea_seen = sea
        self._step()

    def _washed(self) -> bool:
        """Vågtoppen över okularet denna sekund: inget syns (grov sjö). Ögat står högre när
        sjön drar upp båten (`OwnShip.heave_m`)."""
        own = self.own
        if own.surfaced:
            return False
        return crest_m(self.world.env.sea_state, self.now) > EYE_PERISCOPE_M + own.heave_m

    def _mast_watch(self) -> None:
        """Masten länge uppe och ett hot i plottet: föreslå att fälla den."""
        if self.up_s < MAST_WARN_S:
            return
        threats = [t for t in self.game.knowledge.tracks.values() if t.threat]
        if threats:
            self.suggest("mast_down", "off.suggest.mast_down",
                         {"seconds": self.up_s, "designation": threats[0].designation},
                         order="periskop ned", cooldown=MAST_WARN_EVERY_S)

    def _step(self) -> None:
        if self.t_end is not None and self.now >= self.t_end:
            self._finish()
        elif (self.now - self._start_t) % FRAME_S == 1:
            self._publish(live=True)

    def _finish(self) -> None:
        world = self.world
        if not self._seen:
            self._say("off.periscope.none", {"day": world.env.daylight(self.now),
                                            "visibility": world.env.visibility_nm(self.now),
                                            "sector": self.train if self.mode == "look" else None})
        self._publish(live=False)
        self.mode = self.t_end = None

    def _cover(self) -> None:
        c = round(self.train)
        half = self.search.half_fov if self.optic != "kikare" else FOV_HALF_DEG
        self._covered.update(int(norm360(c + d)) for d in range(-int(half), int(half) + 1))

    def _observe_bridge(self) -> None:
        """Kikaren: det i bryggans bild (kunskap) som ligger inom synfältet."""
        self._cover()
        pic = self.game.knowledge.bridge
        if pic is None:
            return
        for o in pic.objects:
            if self._looked(o.bearing):     # flyg, ljus, händelser: en per slag och riktning
                self._seen[o.designation or f"{o.kind}{round(o.bearing / 10)}"] = o
        self._ice, self._land = pic.ice, pic.land

    def _looked(self, bearing: float) -> bool:
        half = self.search.half_fov if self.optic != "kikare" else FOV_HALF_DEG
        return abs(angle_diff(bearing, self.train)) <= half

    def _observe(self) -> None:
        """Det som ligger i okularet just nu (World: periskopet är en sensor)."""
        world, now = self.world, self.now
        light = world.env.light(now)
        day, vis = light.daylight, light.visibility_nm
        eye = EYE_BRIDGE_M if self.own.surfaced else EYE_PERISCOPE_M
        self._cover()
        for v in world.contacts:
            if v.side == "own" or v.sunk or getattr(v, "gone", False):
                continue
            if not self._looked(world.true_bearing(v)):
                continue
            r = world.true_range(v)
            if v.is_ship and v.depth < 10 and r <= vis and world.in_sight(v.state.x, v.state.y):
                if not self._spots(v.kind, r, eye, world.true_bearing(v)):
                    continue
                self._seen[v.id] = self._ship(v, r, light, eye)
            elif v.kind == "aircraft" and day and r <= vis:
                self._seen[v.id] = self._aircraft(v, r)
            elif v.kind == "station" and r <= STATION_LIGHT_NM:
                self._seen[v.id] = self._station(v, r)
        if self._views is None:
            self._views = [v for sp in world.spawners if hasattr(sp, "periscope_view")
                           for v in sp.periscope_view(world, self.rng)]
        for i, (type_, d) in enumerate(self._views):
            key = f"view{i}"
            if key in self._called or not self._looked(d.get("bearing", 0.0)):
                continue
            self._called.add(key)
            self.say(type_, d, kind="contact", alarm=True)
            if obj := _view_object(type_, d):
                self._seen[key] = replace(obj, seen_t=now)
        if now - self._ice_t >= ICE_EVERY_S:
            self._ice_t = now
            self._ice = tuple(IceBearing(b, None if e is None else e * self.rng.uniform(0.85, 1.15), rd)
                              for b, e, rd in ice_view(world))
        self._observe_land(vis)
        self._observe_events(eye)

    def _observe_events(self, eye: float) -> None:
        """Plask, vattenpelare och träffar i okularet (`lookout.visible_events`): ögat 1,5 m
        upp ser ett plask bara på några sjömil, en vattenpelare längre. Bäring och avstånd
        bedöms med förstoringen man mäter med."""
        now, m, g = self.now, self.measure, self.rng.gauss
        for ev in visible_events(self.world, eye, self._looked):
            b = norm360(ev.bearing + g(0, m.bearing_sigma))
            r_sig = m.range_rel * ev.range_nm + m.range_abs
            r_meas = max(0.02, ev.range_nm + g(0, r_sig))
            detail = "kärnladdning" if ev.nuclear else ("övning" if ev.practice else "")
            o = SightedObject(ev.kind, EVENT_LABEL[ev.kind], b, r_meas, range_quality(r_meas, r_sig),
                              detail=detail, seen_t=now)
            self._events.append((now + EVENT_S[ev.kind], o))
            self.game.bus.publish(EventSighted(now, ev.kind, b, r_meas, ev.practice, "periskop"))
            if ev.kind == "column" and now - self._column_t > COLUMN_RESIGHT_S:
                self._column_t = now
                self.say("off.periscope.column", {"bearing": b, "range": r_meas,
                                                  "practice": ev.practice},
                         kind="contact", alarm=not ev.practice)
            elif ev.kind == "hit":
                self.say("off.periscope.hit", {"bearing": b, "range": r_meas, "nuclear": ev.nuclear},
                         kind="contact", alarm=True)

    def _observe_land(self, vis: float) -> None:
        """Stranden i de riktningar okularet sett under hissningen (som bryggans, men bara där
        periskopet tittat). Avståndet bedöms med ögat: en bedömning per hissning."""
        now = self.now
        if now - self._shore_t >= LAND_EVERY_S:
            self._shore_t = now
            o = self.own.state
            self._shore = dict(shore_ranges(self.world.env.seabed, o.x, o.y, vis))
            self._land_by = {b: lb for b, lb in self._land_by.items() if b in self._shore}
        if not self._shore:
            self._land = tuple(self._land_by.values())
            return
        if self._land_f is None:
            self._land_f = 1 + self.rng.gauss(0, self.measure.range_rel)
        seen = False
        for b, r in self._shore.items():
            if self._looked(b):
                seen = True
                self._land_by[b] = LandBearing(b, max(0.05, r * self._land_f))
        self._land = tuple(self._land_by[b] for b in sorted(self._land_by))
        if not seen:
            return
        if now - self._land_seen_t > LAND_RESIGHT_S:
            near = min(self._land, key=lambda lb: lb.range_nm)
            self.say("off.periscope.land", {"bearing": near.bearing, "range": near.range_nm},
                     kind="contact", quality=Quality.GOD)
        self._land_seen_t = now

    def _spots(self, kind: str, r: float, eye: float, bearing: float) -> bool:
        """Ser okularet fartyget? Titten letar i hög rakt mot bäringen och i låg runt omkring;
        svepet i låg; hålläget i den valda förstoringen (`periscope.detectable`)."""
        wave = wave_height_m(self.world.env.sea_state)
        if self.mode == "look" and abs(angle_diff(bearing, self.train)) <= HIGH.half_fov and \
                detectable(kind, r, eye, HIGH.power, wave):
            return True
        return detectable(kind, r, eye, self.search.power, wave)

    def _judgement(self, key: str):
        return self._judges.get(key, self.now, self.rng, since=self._up_t)

    def _ship(self, v, r: float, light, eye: float) -> SightedObject:
        world = self.world
        desig_ = self.game.station(SonarRoom).sensor.designate(v.id)
        j, fresh = self._judgement(v.id)
        full, short = SIGHTED.get(v.kind, ("ytfartyg", "fartyg"))
        day = light.phase == "dag"
        sil = light.silhouette(world.true_bearing(v))     # siluett, eller bara lanternor
        sea = world.env.sea_state
        part = visible_part(v.kind, r, eye, wave_height_m(sea)) if sil else "ljus"
        opt = self.measure
        c_sig = AOB_SIGMA[part] if day or not sil else min(AOB_SIGMA["mastoppar"],
                                                           AOB_SIGMA[part] * TWILIGHT_AOB_F)
        f = sea_sigma_f(sea)                              # grov sjö: sämre bedömning
        c_sig = min(c_sig * opt.aob_f * f, 60.0)
        known = sil and light.daylight                    # klassning god ur siluetten
        bearing = norm360(world.true_bearing(v) + j.bearing * opt.bearing_sigma)
        rel, ab = opt.range_rel * f, opt.range_abs * f
        r_meas = max(0.05, r + j.range_rel * (rel * r + ab))
        r_sig = rel * r_meas + ab                         # vakthavande vet bara sitt mätta avstånd
        course = norm360(v.state.course + j.course * c_sig)
        speed = max(0, round(v.state.speed + j.speed * SPEED_SIGMA))
        moored = v.kind == "moored"     # ankarkulan, ankarljusen: det ligger still, ingen kurs att säga
        if moored:
            speed = 0
        aob = angle_on_bow(bearing, course)
        ls = () if day else lights(aob)
        if fresh:
            self._plot(desig_, full if sil else "ytfartyg", known, bearing, r_meas, r_sig,
                       None if moored else course, c_sig, speed, opt.bearing_sigma)
        if v.id not in self._called:
            self._called.add(v.id)
            prev = self._last_call.get(v.id)
            if prev is not None and self.now - prev[0] <= RECALL_S \
                    and (moored or abs(angle_diff(course, prev[1])) < RECALL_COURSE_DEG) \
                    and abs(speed - prev[2]) <= RECALL_SPEED_KN:
                self._sweep_calls.add("off.periscope.again",
                                      {"designation": desig_, "bearing": bearing, "range": r_meas},
                                      kind="contact", quality=Quality.GOD)
            else:
                self._last_call[v.id] = (self.now, course, speed)
                self._sweep_calls.add("off.periscope.contact",
                                      {"designation": desig_, "label": short, "bearing": bearing,
                                       "range": r_meas, "course": None if moored else course, "speed": speed,
                                       "lights": list(ls),
                                       "power": opt.key},
                                      kind="contact", quality=Quality.GOD)
            if v.kind == PHOTO_TARGET_KIND:
                self.game.station(OfficerStation)._suggest_photo()
        if v.kind == "destroyer" and r_meas < CLOSE_NM and (d := self.dive_depth(100)) is not None:
            self.suggest("down_close", "off.suggest.down",
                         {"reason": f"{desig_} är nära.", "why": "close",
                          "designation": desig_, "depth": d}, order=f"djup {d}",
                         cooldown=300)
        return SightedObject(v.kind, short, bearing, r_meas, range_quality(r_meas, r_sig),
                             designation=desig_, visible=part, aob=aob,
                             aob_quality=aob_quality(c_sig), course=course, speed=speed,
                             lights=ls, seen_t=self.now)

    def _plot(self, desig_: str, label: str, day: bool, bearing: float, r_meas: float,
              r_sig: float, course: float | None, c_sig: float, speed: float,
              b_sig: float = HIGH.bearing_sigma) -> None:
        """En observation till plottet: bäring, avstånd, kurs och fart med periskopets σ."""
        bus, now = self.game.bus, self.now
        tr = self.game.knowledge.tracks.get(desig_)
        if tr is None:
            bus.publish(ContactDetected(now, desig_, bearing, label,
                                        Quality.GOD if day else Quality.OSAKER))
        elif day and tr.class_quality < Quality.GOD:
            bus.publish(ClassificationChanged(now, desig_, label, Quality.GOD))
        ex, ey = self.game.own_position_estimate()
        bus.publish(BearingObserved(now, BearingObs(
            now, bearing, b_sig, ex, ey, self.own.state.course, designation=desig_,
            range_nm=r_meas, range_sigma=r_sig, source="periskop", course_obs=course,
            course_sigma=c_sig, speed_obs=speed, speed_sigma=SPEED_SIGMA + 0.3)))

    def _aircraft(self, v, r: float) -> SightedObject:
        world = self.world
        j, _ = self._judgement(v.id)
        bearing = norm360(world.true_bearing(v) + j.bearing * 2.0)
        r_meas = max(0.2, r * (1 + 0.2 * j.range_rel))
        low = v.altitude < 150
        if v.id not in self._called:
            self._called.add(v.id)
            self.say("off.periscope.aircraft", {"bearing": bearing, "range": r_meas, "low": low},
                     kind="contact", alarm=True)
        if (d := self.dive_depth(60)) is not None:
            self.suggest("down_air", "off.suggest.down", {"reason": "Flygplan i sikte.", "why": "aircraft",
                                                           "depth": d},
                         order=f"djup {d}", cooldown=300, alarm=True)
        return SightedObject("aircraft", "flygplan", bearing, r_meas, Quality.OSAKER,
                             detail="lågt" if low else "", seen_t=self.now)

    def _station(self, v, r: float) -> SightedObject:
        """Stationens ljus: bäring och avstånd, och läget till navigatören."""
        world = self.world
        j, fresh = self._judgement(v.id)
        bearing = norm360(world.true_bearing(v) + j.bearing * 1.0)
        r_sig = 0.1 * r + 0.03
        r_meas = max(0.05, r + j.range_rel * r_sig)
        if fresh:
            ex, ey = self.game.own_position_estimate()
            dx, dy = velocity(bearing, r_meas * 3600)      # en timme i r_meas knop = r_meas nm
            self.game.bus.publish(PositionReported(self.now, "Nord-7", ex + dx, ey + dy,
                                                   0.1 * r_meas + 0.05, self.now, "periskop"))
        if v.id not in self._called:
            self._called.add(v.id)
            self.say("off.periscope.station", {"bearing": bearing, "range": r_meas},
                     kind="contact", quality=Quality.GOD, alarm=True)
        from .navigation import NavigationStation
        try:
            room = self.game.station(NavigationStation).surface_ok()
        except KeyError:
            room = True
        if r_meas < 1.4 and self.own.state.depth > 1.0 and room:
            self.suggest("surface_station", "off.suggest.surface_station", {"range": r_meas},
                         order="ytläge", cooldown=300)
        return SightedObject("station", "drivstation", bearing, r_meas,
                             range_quality(r_meas, r_sig), lights=("ljus",), seen_t=self.now)

    # --- bilden ---------------------------------------------------------------------
    def _publish(self, live: bool) -> None:
        world, now = self.world, self.now
        one_look = self.mode in ("sweep", "look")   # ett svep eller en titt är en bild
        objects = [replace(o, seen_t=now) if one_look else o for o in self._seen.values()]
        self._events = [(until, o) for until, o in self._events if until >= now]
        objects += [o for _, o in self._events]
        covered = self._covered
        objects += carried(self._before, now,
                           lambda b: int(norm360(round(b))) in covered, objects)
        sector = None if (self.mode == "sweep" and not live) else self.train
        self.game.bus.publish(PeriscopeSighted(now, PeriscopePicture(
            now, world.env.daylight(now), world.env.visibility_nm(now), self.own.state.course,
            "brygga" if self.own.surfaced else "periskop", tuple(objects), sector, self._ice,
            self._land, **sky_of(world.env.light(now)), sea_state=world.env.sea_state,
            power=self.measure.key if self.optic != "kikare" else "låg"), live=live))
