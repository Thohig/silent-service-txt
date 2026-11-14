"""Vakthavande officer: periskop, radar och radarvarnare (ESM).

Allt här kräver periskopdjup och exponerar ubåten: periskop och radar kan
upptäckas av jagarens radar och utkik, och radarsändning pejlas på långt håll.

Vakthavande håller också vakten när kaptenen är tyst: efter QUIET_S sekunder
utan inmatning och utan att någon annan föreslagit något samlar han
stationernas idle_proposals() och låter den station som har det viktigaste
förslaget säga det. Högst ett sådant förslag per QUIET_S, inget medan ett
annat förslag väntar, och ingen order som redan föreslagits inom REPEAT_S.

Ber kaptenen om förslag ("förslag", "förslag sonar", "annat förslag") svarar
vakthavande direkt ur samma kandidater, utan att vänta eller spärra upprepning.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .. import phrases
from ..crew import ROLE_LABEL, Role
from ..entities import Emission
from ..arctic import STATION_LIGHT_NM
from ..events import (BearingObserved, ClassificationChanged, ContactDetected,
                      PeriscopeBlocked, PeriscopeSighted, PhotoTaken, PositionReported)
from ..fmt import fmt_course, kn, nm
from ..geo import angle_diff, norm360, velocity
from ..ice import ice_view, masts_clear
from ..orders import DESIG, AskSuggestion, CommandSpec, Order, desig
from ..ownship import PERISCOPE_DEPTH
from ..periscope import (AOB_SIGMA, EYE_BRIDGE_M, EYE_PERISCOPE_M, IceBearing,
                         PeriscopePicture, SightedObject, angle_on_bow, aob_quality, carried,
                         in_sector, lights, range_quality, visible_part)
from ..reports import Quality
from ..russian import ru
from ..tma import BearingObs
from .base import Proposal, Station
from .sonar_room import SonarRoom

LOOK_S = 15
SHORT_LOOK_S = 8           # kort titt mot en bäring: mindre tid med masten uppe
RADAR_S = 10
RADAR_RANGE_NM = 12.0
AIR_ESM_NM = 40.0          # flygradar hörs så här långt
QUIET_S = 600              # tystnad från kaptenen innan besättningen tar initiativ
IDLE_RETRY_S = 60          # om ingen station hade något att föreslå
REPEAT_S = 1200            # samma order föreslås inte igen inom denna tid
LOOK_INTERVAL_S = 900      # på periskopdjup utan kontakt: titta så här ofta


@dataclass(frozen=True)
class PeriscopeLook(Order):
    bearing: float | None = None     # kort titt mot en bäring
    target: str | None = None        # kort titt mot en kontakts senaste bäring


@dataclass(frozen=True)
class RadarSweep(Order):
    pass


@dataclass(frozen=True)
class Photograph(Order):
    pass


PHOTO_S = 40               # periskopet uppe medan kameran arbetar
# bildens kvalitet efter avstånd (nm) till närmaste fartyg vid ankarplatsen: dag, natt
PHOTO_RANGES = {True: ((1.2, Quality.SAKER), (2.2, Quality.GOD), (3.5, Quality.OSAKER)),
                False: ((0.6, Quality.GOD), (1.2, Quality.OSAKER))}
PHOTO_TARGET_KIND = "moored"


# vad utkiken ser i periskopet: (klassning till plottet, ord i rapporten)
SIGHTED = {"destroyer": ("jagare, amerikansk", "jagare"),
           "merchant": ("handelsfartyg", "handelsfartyg"),
           "patrol": ("patrullbåt, amerikansk", "patrullbåt"),
           "moored": ("fartyg till ankars", "fartyg till ankars"),
           "transport": ("trupptransport, amerikansk", "trupptransport"),
           "tanker": ("tankfartyg, amerikanskt", "tankfartyg")}


def _view_object(type_: str, d: dict) -> SightedObject | None:
    """Hamnskyddets nät (spawnarnas periscope_view) som föremål i bilden."""
    if type_ == "off.periscope.net":
        return SightedObject("net", "bojrad", d["bearing"], d["range"], Quality.OSAKER,
                             detail="grinden öppen" if d["gate_open"] else "grinden stängd")
    return None


def _contact(d: dict) -> str:
    return (f"{d['designation']}: {d['label']} i bäring {fmt_course(d['bearing'])}, avstånd cirka "
            f"{nm(d['range'])} sjömil. Vinkel på bogen ger kurs ungefär {fmt_course(d['course'])}, "
            f"fart cirka {kn(d['speed'])} knop.")


BATTLE_CALM_S = 1800        # så länge utan jakttecken innan nytt stridslarm
BATTLE_DELAY_S = 6          # vakthavande ropar efter sonars rapport

PHRASES = {
    "off.refused": lambda d: f"Kapten, {d['reason']}.",
    "off.battle_stations": lambda d: f"{ru('Boevaja trevoga')}! Stridslarm, alla man till "
    "stridsstationerna. Fienden har troligen kontakt med oss.",
    "off.periscope.up": lambda d: "Periskop upp." if d.get("bearing") is None
    else f"Periskop upp, kort titt i bäring {fmt_course(d['bearing'])}.",
    "off.periscope.contact": lambda d: "Periskop: " + _contact(d),
    "off.periscope.none": lambda d: (f"Periskop: inget i sikte i bäring {fmt_course(d['sector'])}. "
                                     if d.get("sector") is not None else "Periskop: inget i sikte. ")
    + f"{'Dagsljus' if d['day'] else 'Mörkt'}, sikt cirka {nm(d['visibility'])} sjömil. Periskop ner.",
    "off.periscope.station": lambda d: f"Periskop: ljus på isen i bäring {fmt_course(d['bearing'])}, "
    f"avstånd cirka {nm(d['range'])} sjömil. Baracker och radiomaster. Det måste vara Nord-7! "
    "Inga rörelser, inget ljus i fönstren.",
    "off.suggest.surface_station": lambda d: "Kapten, vakthavande. Vi har öppet vatten ovanför och "
    f"Nord-7 på {nm(d['range'])} sjömil, nära nog att gå över isen. Föreslår ytläge.",
    "off.periscope.net": lambda d: f"Periskop: rad av små bojar tvärs farleden, närmast i bäring "
    f"{fmt_course(d['bearing'])}, cirka {nm(d['range'])} sjömil. Ett nät! Grinden i bäring "
    f"{fmt_course(d['gate_bearing'])} är " + ("öppen." if d["gate_open"] else "stängd."),
    "off.photo.start": lambda d: "Periskop upp, kameran klar. Fotograferar.",
    "off.photo.aborted": lambda d: "Kapten, vi kom under periskopdjup. Inga bilder.",
    "off.photo.nothing": lambda d: "Kapten, bilderna visar inget. "
    + ("Ankarplatsen är för långt bort." if d.get("far") else "Inga fartyg i sikte.")
    + ("" if d["day"] else " Det är för mörkt."),
    "off.photo.done": lambda d: f"Bilder tagna, kapten. {d['count']} fartyg till ankars på cirka "
    f"{nm(d['range'])} sjömil. Bildkvaliteten är {d['quality']}"
    + ("." if d["day"] else ", i mörker.") + " Periskop ner.",
    "off.suggest.photo": lambda d: f"Kapten, vakthavande. Ankarplatsen är cirka {nm(d['range'])} "
    f"sjömil bort, nära nog för {d['quality']} bild. Föreslår fotografering.",
    "off.radar.start": lambda d: "Radar sänder. Ett svep.",
    "off.radar.contact": lambda d: f"Radar: {d['designation']} i bäring {fmt_course(d['bearing'])}, "
    f"avstånd {nm(d['range'])} sjömil.",
    "off.radar.none": lambda d: "Radar: inga ekon inom tolv sjömil.",
    "off.esm": lambda d: f"Radarvarnare: radar i bäring {fmt_course(d['bearing'])}, "
    f"signal {d['strength']}." + (" De kan se våra master!" if d['strength'] == "mycket stark" else ""),
    "off.esm.air": lambda d: f"Radarvarnare: flygradar i bäring {fmt_course(d['bearing'])}, "
    f"signal {d['strength']}. Bäringen drar snabbt, det är ett flygplan."
    + (" Det är nära, kapten!" if d['strength'] == "mycket stark" else ""),
    "off.periscope.aircraft": lambda d: f"Periskop: flygplan i bäring {fmt_course(d['bearing'])}, "
    f"cirka {nm(d['range'])} sjömil, " + ("lågt över vattnet" if d["low"] else "på höjd")
    + ". Tvåmotorigt patrullplan.",
    "off.suggest.down": lambda d: f"Kapten, vakthavande. {d['reason']} Föreslår djup "
    f"{d['depth']:.0f}.",
    "off.suggest.none": lambda d: (
        f"Kapten, vakthavande. {d['station']} har inget att föreslå just nu." if d.get("station")
        else "Kapten, vakthavande. Inget annat att föreslå just nu." if d.get("other")
        else "Kapten, vakthavande. Inga förslag just nu, läget är lugnt."),
    "off.suggest.look": lambda d: "Kapten, vakthavande. Vi är på periskopdjup och har inte "
    "tittat på en stund. Föreslår ett periskopsvep.",
}
phrases.register(PHRASES)


RU_PHRASES = {
    "off.battle_stations": lambda d: "Боевая тревога! Боевая тревога! Противник, видимо, "
    "обнаружил нас.",
    "off.periscope.up": lambda d: "Есть, поднять перископ.",
}
phrases.register_ru(RU_PHRASES)


class OfficerStation(Station):
    role = Role.OFFICER
    COMMANDS = [
        CommandSpec(r"periskop|periskop upp|titta", lambda m: PeriscopeLook(), "periskop"),
        CommandSpec(rf"(?:periskop|titta)\s+(?:mot\s+)?{DESIG}",
                    lambda m: PeriscopeLook(target=desig(m[1])), "periskop S-3"),
        CommandSpec(r"(?:periskop|titta)\s+(?:mot\s+|bäring\s+|baring\s+)?(\d{1,3})",
                    lambda m: PeriscopeLook(bearing=int(m[1]) % 360), "periskop 047"),
        CommandSpec(r"radar|radarsvep", lambda m: RadarSweep(), "radar"),
        CommandSpec(r"foto|fotografera|ta bilder|ta foto|kamera", lambda m: Photograph(), "foto"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.look_done_t: int | None = None
        self.look_sector: float | None = None
        self.radar_done_t: int | None = None
        self.photo_done_t: int | None = None
        self._esm_last: dict[str, tuple[str, int]] = {}
        self._next_esm = 0
        self._last_look_t = -10**9
        self._idle_t = -10**9       # senaste initiativ (eller försök) vid tystnad
        self._hunt_seen = -10**9    # senaste jakttecken vakthavande har tagit ställning till

    @property
    def own(self):
        return self.game.world.own

    def _sonar(self) -> SonarRoom:
        return self.game.station(SonarRoom)

    def _check_mast(self, what: str) -> str | None:
        st, sys = self.own.state, self.own.sys
        if st.depth > PERISCOPE_DEPTH:
            return f"vi måste upp på periskopdjup för {what}"
        if st.speed > 7:
            return "farten är för hög, periskopet vibrerar och ger svall"
        if sys.health["periscope"] < 0.3:
            return "periskopet och masterna är skadade"
        if not masts_clear(self.game.world):
            return "det är is ovanför, masterna kommer inte upp"
        return None

    def on_order(self, order: Order) -> None:
        sys = self.own.sys
        match order:
            case PeriscopeLook(bearing=bearing, target=target):
                if reason := self._check_mast("periskopet"):
                    self.say("off.refused", {"reason": reason})
                    if self.own.state.depth <= PERISCOPE_DEPTH and \
                            not masts_clear(self.game.world):
                        self.game.bus.publish(PeriscopeBlocked(self.now, "is"))
                    return
                if target is not None:
                    tr = self.game.knowledge.track(target)
                    if tr is None or tr.last_bearing is None:
                        self.say("off.refused", {"reason": f"vi har ingen bäring på {target}"})
                        return
                    bearing = tr.last_bearing
                look_s = LOOK_S if bearing is None else SHORT_LOOK_S
                self._last_look_t = self.now
                self.look_sector = bearing
                sys.periscope_until = max(sys.periscope_until, self.now + look_s)
                self.look_done_t = self.now + look_s
                self.say("off.periscope.up", {"bearing": bearing}, kind="ack")
            case AskSuggestion(role=role, other=other):
                self._answer_request(Role(role) if role else None, other)
            case Photograph():
                if reason := self._check_mast("periskopet"):
                    self.say("off.refused", {"reason": reason})
                    return
                sys.periscope_until = max(sys.periscope_until, self.now + PHOTO_S)
                self.photo_done_t = self.now + PHOTO_S
                self.say("off.photo.start", kind="ack")
            case RadarSweep():
                if reason := self._check_mast("radarn"):
                    self.say("off.refused", {"reason": reason})
                    return
                o = self.own.state
                sys.radar_until = self.now + RADAR_S
                self.game.world.emit_em(Emission("radar", o.x, o.y, self.own.id, self.now))
                self.radar_done_t = self.now + RADAR_S
                self.say("off.radar.start", kind="ack")

    def _battle_watch(self) -> None:
        """Stridslarm när sonar hör att fienden har oss, om det var lugnt en halvtimme."""
        ht = self.game.knowledge.hunt_t
        if ht <= self._hunt_seen:
            return
        if ht - self._hunt_seen > BATTLE_CALM_S:
            self.say("off.battle_stations", kind="info", alarm=True, extra_delay=BATTLE_DELAY_S)
        self._hunt_seen = ht

    # --- initiativ när kaptenen är tyst ------------------------------------------
    def _idle_watch(self) -> None:
        g = self.game
        since = max(g.last_command_t, g.last_suggestion_t, self._idle_t)
        if self.now - since < QUIET_S:
            return
        if g.active_suggestion() is not None or g.queue.has_kind("suggest"):
            return
        for st, p in self._candidates():
            if self.now - g.suggested_at.get(p.order, -10**9) < REPEAT_S:
                continue
            if st.propose(p):
                self._idle_t = self.now
                g.log(f"INITIATIV efter tystnad: {p.key} -> {p.order!r}")
                return
        self._idle_t = self.now - QUIET_S + IDLE_RETRY_S

    def _candidates(self, role: Role | None = None) -> list[tuple[Station, Proposal]]:
        """Alla stationers förslag, viktigast först (lika prioritet: stationsordning)."""
        out = [(p.priority, i, st, p) for i, st in enumerate(self.game.stations)
               if role is None or st.role == role for p in st.idle_proposals()]
        return [(st, p) for _, _, st, p in sorted(out, key=lambda c: (c[0], c[1]))]

    def _answer_request(self, role: Role | None, other: bool) -> None:
        g = self.game
        active = g.active_suggestion()
        skip = active[0] if (other and active) else None
        for st, p in self._candidates(role):
            if p.order == skip:
                continue
            # kaptenen frågade: ingen väntan och ingen spärr mot upprepning
            if st.suggest(p.key, p.type, p.data, order=p.order, cooldown=0, quality=p.quality):
                g.log(f"FÖRSLAG på begäran: {p.key} -> {p.order!r}")
                return
        self.say("off.suggest.none",
                 {"station": ROLE_LABEL[role] if role else None, "other": other})

    def idle_proposals(self) -> list[Proposal]:
        st = self.own.state
        held = self.game.knowledge.threat_held()
        if st.depth <= PERISCOPE_DEPTH and not held and st.speed <= 7 and \
                not self.game.knowledge.ice.under_ice(self.now) and \
                self.now - self._last_look_t >= LOOK_INTERVAL_S and self.look_done_t is None:
            return [Proposal(5, "idle_look", "off.suggest.look", "periskop", cooldown=900)]
        return []

    def _sight_station(self, v) -> SightedObject:
        """Stationens ljus i periskopet: bäring och avstånd, och läget till navigatören."""
        world, rng = self.game.world, self.game.rng
        r = world.true_range(v)
        bearing = norm360(world.true_bearing(v) + rng.gauss(0, 1.0))
        r_meas = max(0.05, r + rng.gauss(0, 0.1 * r + 0.03))
        ex, ey = self.game.own_position_estimate()
        dx, dy = velocity(bearing, r_meas * 3600)          # en timme i r_meas knop = r_meas nm
        self.game.bus.publish(PositionReported(self.now, "Nord-7", ex + dx, ey + dy,
                                               0.1 * r_meas + 0.05, self.now, "periskop"))
        self.say("off.periscope.station", {"bearing": bearing, "range": r_meas}, kind="contact",
                 quality=Quality.GOD, alarm=True)
        from .navigation import NavigationStation
        try:
            room = self.game.station(NavigationStation).surface_ok()
        except KeyError:
            room = True
        if r_meas < 1.4 and self.own.state.depth > 1.0 and room:
            self.suggest("surface_station", "off.suggest.surface_station", {"range": r_meas},
                         order="ytläge", cooldown=300)
        return SightedObject("station", "drivstation", bearing, r_meas,
                             range_quality(r_meas, 0.1 * r_meas + 0.03), lights=("ljus",))

    def _observe(self, v, bearing_sigma: float, range_sigma: float, source: str,
                 label: str) -> dict:
        world, rng = self.game.world, self.game.rng
        sonar = self._sonar().sensor
        desig = sonar.designate(v.id)
        bearing = norm360(world.true_bearing(v) + rng.gauss(0, bearing_sigma))
        r = world.true_range(v)
        r_meas = max(0.05, r + rng.gauss(0, range_sigma))
        tr = self.game.knowledge.tracks.get(desig)
        if tr is None:
            self.game.bus.publish(ContactDetected(self.now, desig, bearing, label, Quality.GOD))
        elif source == "periskop" and tr.class_quality < Quality.GOD:
            # det vi ser i periskopet slår sonarens gissning
            self.game.bus.publish(ClassificationChanged(self.now, desig, label, Quality.GOD))
        ex, ey = self.game.own_position_estimate()
        self.game.bus.publish(BearingObserved(self.now, BearingObs(
            self.now, bearing, bearing_sigma, ex, ey, self.own.state.course,
            designation=desig, range_nm=r_meas, range_sigma=range_sigma, source=source)))
        return {"designation": desig, "bearing": bearing, "range": r_meas}

    def _photo_targets(self):
        world = self.game.world
        return [v for v in world.contacts if v.kind == PHOTO_TARGET_KIND and not v.sunk]

    def _photo_quality(self, r: float) -> Quality | None:
        day = self.game.world.env.is_day(self.now)
        for limit, q in PHOTO_RANGES[day]:
            if r <= limit:
                return q
        return None

    def _photo_done(self) -> None:
        world = self.game.world
        if self.own.state.depth > PERISCOPE_DEPTH + 1:
            self.say("off.photo.aborted")
            return
        targets = self._photo_targets()
        if not targets:
            self.say("off.photo.nothing", {"day": world.env.is_day(self.now)})
            return
        r = min(world.true_range(v) for v in targets)
        q = self._photo_quality(r)
        if q is None:
            self.say("off.photo.nothing", {"day": world.env.is_day(self.now), "far": True})
            return
        n = sum(1 for v in targets if world.true_range(v) <= r + 1.0)
        world.mission["best_photo"] = max(world.mission.get("best_photo", -1), int(q))
        self.game.bus.publish(PhotoTaken(self.now, q, "ankarplatsen"))
        self.say("off.photo.done", {"range": r * self.game.rng.uniform(0.9, 1.1), "count": n,
                                    "quality": q.label, "day": world.env.is_day(self.now)},
                 quality=q)

    def _suggest_photo(self) -> None:
        """Efter ett periskopsvep: ankarplatsen nära nog för en bättre bild än vi har."""
        world = self.game.world
        targets = self._photo_targets()
        if not targets:
            return
        r = min(world.true_range(v) for v in targets)
        q = self._photo_quality(r)
        best = self.game.knowledge.best_photo
        if q is None or (best is not None and q <= best):
            return
        self.suggest("photo", "off.suggest.photo", {"range": r, "quality": q.label},
                     order="foto", cooldown=300, quality=q)

    def _esm_air(self) -> None:
        """Flygradar: stark på långt håll, och bäringen drar snabbt."""
        world, rng = self.game.world, self.game.rng
        for v in world.contacts:
            if v.kind != "aircraft" or v.gone:
                continue
            r = world.true_range(v)
            if r > AIR_ESM_NM:
                continue
            strength = ("mycket stark" if r < 4 else "stark" if r < 10
                        else "medel" if r < 20 else "svag")
            prev = self._esm_last.get(v.id)
            if prev is None or prev[0] != strength or self.now - prev[1] > 600:
                self._esm_last[v.id] = (strength, self.now)
                b = norm360(world.true_bearing(v) + rng.gauss(0, 3))
                close = strength in ("mycket stark", "stark")
                self.say("off.esm.air", {"bearing": b, "strength": strength}, kind="contact",
                         alarm=close)
                if close:
                    self.suggest("down_air", "off.suggest.down",
                                 {"reason": "Flygradar, nära. De kan se våra master.", "depth": 60},
                                 order="djup 60", cooldown=300, alarm=True)

    def _surface_ships(self):
        return [v for v in self.game.world.contacts
                if v.side != "own" and v.is_ship and not v.sunk and v.depth < 10]

    def update(self) -> None:
        world, st, rng = self.game.world, self.own.state, self.game.rng
        self._idle_watch()
        self._battle_watch()
        if self.look_done_t is not None and self.now >= self.look_done_t:
            self.look_done_t = None
            if st.depth > PERISCOPE_DEPTH + 1:
                return
            vis = world.env.visibility_nm(self.now)
            day = world.env.is_day(self.now)
            sector = self.look_sector

            def looked(v) -> bool:
                return in_sector(world.true_bearing(v), sector)

            eye = EYE_BRIDGE_M if self.own.surfaced else EYE_PERISCOPE_M
            objects: list[SightedObject] = []
            seen = [v for v in self._surface_ships() if world.true_range(v) <= vis and looked(v)]
            stations = [v for v in world.contacts if v.kind == "station"
                        and world.true_range(v) <= STATION_LIGHT_NM and looked(v)]
            for v in stations:
                objects.append(self._sight_station(v))
            planes = [v for v in world.contacts if v.kind == "aircraft" and day
                      and world.true_range(v) <= vis and looked(v)]
            for v in planes:
                d = {"bearing": norm360(world.true_bearing(v) + rng.gauss(0, 2)),
                     "range": max(0.2, world.true_range(v) * rng.uniform(0.8, 1.2)),
                     "low": v.altitude < 150}
                self.say("off.periscope.aircraft", d, kind="contact", alarm=True)
                objects.append(SightedObject("aircraft", "flygplan", d["bearing"], d["range"],
                                             Quality.OSAKER, detail="lågt" if d["low"] else ""))
                self.suggest("down_air", "off.suggest.down",
                             {"reason": "Flygplan i sikte.", "depth": 60}, order="djup 60",
                             cooldown=300, alarm=True)
            views = [v for sp in world.spawners if hasattr(sp, "periscope_view")
                     for v in sp.periscope_view(world, rng)
                     if in_sector(v[1].get("bearing", 0.0), sector)]
            for type_, d in views:
                self.say(type_, d, kind="contact", alarm=True)
                if obj := _view_object(type_, d):
                    objects.append(obj)
            if any(v.kind == PHOTO_TARGET_KIND for v in seen):
                self._suggest_photo()
            if not seen and not stations and not planes and not views:
                self.say("off.periscope.none", {"day": day, "visibility": vis, "sector": sector})
            for v in seen:
                r = world.true_range(v)
                full, short = SIGHTED.get(v.kind, ("ytfartyg", "fartyg"))
                r_sigma = 0.08 * r + 0.03
                d = self._observe(v, 0.5, r_sigma, "periskop", full)
                part = visible_part(v.kind, r, eye) if day else "ljus"
                c_sigma = AOB_SIGMA[part]
                d.update(label=short,
                         course=norm360(v.state.course + rng.gauss(0, c_sigma)),
                         speed=max(0, round(v.state.speed + rng.gauss(0, 2))))
                self.say("off.periscope.contact", d, kind="contact", quality=Quality.GOD)
                aob = angle_on_bow(d["bearing"], d["course"])
                objects.append(SightedObject(
                    v.kind, short, d["bearing"], d["range"], range_quality(d["range"], r_sigma),
                    designation=d["designation"], visible=part, aob=aob,
                    aob_quality=aob_quality(c_sigma), course=d["course"], speed=d["speed"],
                    lights=() if day else lights(aob), seen_t=self.now))
                if r < 3.0 and v.kind == "destroyer":
                    self.suggest("down_close", "off.suggest.down",
                                 {"reason": f"{d['designation']} är nära.", "depth": 100},
                                 order="djup 100", cooldown=300)
            objects = [o if o.seen_t >= 0 else replace(o, seen_t=self.now) for o in objects]
            if sector is not None:
                objects += carried(self.game.knowledge.periscope, self.now, sector, objects)
            ice = tuple(IceBearing(b, None if e is None else e * rng.uniform(0.85, 1.15), r)
                        for b, e, r in ice_view(world))
            self.game.bus.publish(PeriscopeSighted(self.now, PeriscopePicture(
                self.now, day, vis, self.own.state.course,
                "brygga" if self.own.surfaced else "periskop", tuple(objects), sector, ice)))

        if self.photo_done_t is not None and self.now >= self.photo_done_t:
            self.photo_done_t = None
            self._photo_done()

        if self.radar_done_t is not None and self.now >= self.radar_done_t:
            self.radar_done_t = None
            hits = [v for v in self._surface_ships() if world.true_range(v) <= RADAR_RANGE_NM]
            if not hits:
                self.say("off.radar.none")
            for v in hits:
                r = world.true_range(v)
                d = self._observe(v, 1.0, 0.01 * r + 0.01, "radar", "ytfartyg (radar)")
                self.say("off.radar.contact", d, kind="contact", quality=Quality.SAKER)

        # radarvarnare: automatiskt på periskopdjup
        if st.depth <= PERISCOPE_DEPTH + 1 and self.now >= self._next_esm:
            self._next_esm = self.now + 10
            self._esm_air()
            for v in self._surface_ships():
                if not v.has_radar:
                    continue
                r = world.true_range(v)
                if r > 30:
                    continue
                strength = ("mycket stark" if r < 4 else "stark" if r < 8
                            else "medel" if r < 15 else "svag")
                prev = self._esm_last.get(v.id)
                if prev is None or prev[0] != strength or self.now - prev[1] > 600:
                    self._esm_last[v.id] = (strength, self.now)
                    b = norm360(world.true_bearing(v) + rng.gauss(0, 3))
                    self.say("off.esm", {"bearing": b, "strength": strength}, kind="contact",
                             alarm=strength == "mycket stark")
                    if strength == "mycket stark":
                        self.suggest("down_esm", "off.suggest.down",
                                     {"reason": "Radarn är mycket stark.", "depth": 60},
                                     order="djup 60", cooldown=300, alarm=True)
