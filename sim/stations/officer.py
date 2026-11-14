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

from dataclasses import dataclass

from .. import phrases
from ..crew import ROLE_LABEL, Role
from ..entities import Emission
from ..events import BearingObserved, ContactDetected
from ..fmt import fmt_course, kn, nm
from ..geo import angle_diff, norm360
from ..ice import masts_clear
from ..orders import AskSuggestion, CommandSpec, Order
from ..ownship import PERISCOPE_DEPTH
from ..reports import Quality
from ..tma import BearingObs
from .base import Proposal, Station
from .sonar_room import SonarRoom

LOOK_S = 15
RADAR_S = 10
RADAR_RANGE_NM = 12.0
QUIET_S = 600              # tystnad från kaptenen innan besättningen tar initiativ
IDLE_RETRY_S = 60          # om ingen station hade något att föreslå
REPEAT_S = 1200            # samma order föreslås inte igen inom denna tid
LOOK_INTERVAL_S = 900      # på periskopdjup utan kontakt: titta så här ofta


@dataclass(frozen=True)
class PeriscopeLook(Order):
    pass


@dataclass(frozen=True)
class RadarSweep(Order):
    pass


def _contact(d: dict) -> str:
    return (f"{d['designation']}: {d['label']} i bäring {fmt_course(d['bearing'])}, avstånd cirka "
            f"{nm(d['range'])} sjömil. Vinkel på bogen ger kurs ungefär {fmt_course(d['course'])}, "
            f"fart cirka {kn(d['speed'])} knop.")


PHRASES = {
    "off.refused": lambda d: f"Kapten, {d['reason']}.",
    "off.periscope.up": lambda d: "Periskop upp.",
    "off.periscope.contact": lambda d: "Periskop: " + _contact(d),
    "off.periscope.none": lambda d: f"Periskop: inget i sikte. "
    f"{'Dagsljus' if d['day'] else 'Mörkt'}, sikt cirka {nm(d['visibility'])} sjömil. Periskop ner.",
    "off.radar.start": lambda d: "Radar sänder. Ett svep.",
    "off.radar.contact": lambda d: f"Radar: {d['designation']} i bäring {fmt_course(d['bearing'])}, "
    f"avstånd {nm(d['range'])} sjömil.",
    "off.radar.none": lambda d: "Radar: inga ekon inom tolv sjömil.",
    "off.esm": lambda d: f"Radarvarnare: radar i bäring {fmt_course(d['bearing'])}, "
    f"signal {d['strength']}." + (" De kan se våra master!" if d['strength'] == "mycket stark" else ""),
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


class OfficerStation(Station):
    role = Role.OFFICER
    COMMANDS = [
        CommandSpec(r"periskop|periskop upp|titta", lambda m: PeriscopeLook(), "periskop"),
        CommandSpec(r"radar|radarsvep", lambda m: RadarSweep(), "radar"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.look_done_t: int | None = None
        self.radar_done_t: int | None = None
        self._esm_last: dict[str, tuple[str, int]] = {}
        self._next_esm = 0
        self._last_look_t = -10**9
        self._idle_t = -10**9       # senaste initiativ (eller försök) vid tystnad

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
            case PeriscopeLook():
                if reason := self._check_mast("periskopet"):
                    self.say("off.refused", {"reason": reason})
                    return
                self._last_look_t = self.now
                sys.periscope_until = max(sys.periscope_until, self.now + LOOK_S)
                self.look_done_t = self.now + LOOK_S
                self.say("off.periscope.up", kind="ack")
            case AskSuggestion(role=role, other=other):
                self._answer_request(Role(role) if role else None, other)
            case RadarSweep():
                if reason := self._check_mast("radarn"):
                    self.say("off.refused", {"reason": reason})
                    return
                o = self.own.state
                sys.radar_until = self.now + RADAR_S
                self.game.world.emit_em(Emission("radar", o.x, o.y, self.own.id, self.now))
                self.radar_done_t = self.now + RADAR_S
                self.say("off.radar.start", kind="ack")

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
        held = any(t.held for t in self.game.knowledge.tracks.values())
        if st.depth <= PERISCOPE_DEPTH + 1 and not held and st.speed <= 7 and \
                self.now - self._last_look_t >= LOOK_INTERVAL_S and self.look_done_t is None:
            return [Proposal(5, "idle_look", "off.suggest.look", "periskop", cooldown=900)]
        return []

    def _observe(self, v, bearing_sigma: float, range_sigma: float, source: str,
                 label: str) -> dict:
        world, rng = self.game.world, self.game.rng
        sonar = self._sonar().sensor
        desig = sonar.designate(v.id)
        bearing = norm360(world.true_bearing(v) + rng.gauss(0, bearing_sigma))
        r = world.true_range(v)
        r_meas = max(0.05, r + rng.gauss(0, range_sigma))
        if self.game.knowledge.tracks.get(desig) is None:
            self.game.bus.publish(ContactDetected(self.now, desig, bearing, label, Quality.GOD))
        ex, ey = self.game.own_position_estimate()
        self.game.bus.publish(BearingObserved(self.now, BearingObs(
            self.now, bearing, bearing_sigma, ex, ey, self.own.state.course,
            designation=desig, range_nm=r_meas, range_sigma=range_sigma, source=source)))
        return {"designation": desig, "bearing": bearing, "range": r_meas}

    def _surface_ships(self):
        return [v for v in self.game.world.contacts
                if v.side != "own" and v.is_ship and not v.sunk and v.depth < 10]

    def update(self) -> None:
        world, st, rng = self.game.world, self.own.state, self.game.rng
        self._idle_watch()
        if self.look_done_t is not None and self.now >= self.look_done_t:
            self.look_done_t = None
            if st.depth > PERISCOPE_DEPTH + 1:
                return
            vis = world.env.visibility_nm(self.now)
            seen = [v for v in self._surface_ships() if world.true_range(v) <= vis]
            if not seen:
                self.say("off.periscope.none", {"day": world.env.is_day(self.now), "visibility": vis})
            for v in seen:
                r = world.true_range(v)
                d = self._observe(v, 0.5, 0.08 * r + 0.03, "periskop",
                                  "jagare, amerikansk" if v.kind == "destroyer" else "ytfartyg")
                d.update(label="jagare" if v.kind == "destroyer" else "fartyg",
                         course=norm360(v.state.course + rng.gauss(0, 8)),
                         speed=max(0, round(v.state.speed + rng.gauss(0, 2))))
                self.say("off.periscope.contact", d, kind="contact", quality=Quality.GOD)
                if r < 3.0:
                    self.suggest("down_close", "off.suggest.down",
                                 {"reason": f"{d['designation']} är nära.", "depth": 100},
                                 order="djup 100", cooldown=300)

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
