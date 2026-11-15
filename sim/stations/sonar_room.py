"""Sonarrummet: passiv lyssning, transienter, aktiv sonar och förslag.

Sensorn (sim/sonar.py) är bryggan mellan sanning och kunskap. Stationen
publicerar sensorns utdata som händelser på bussen. Kunskapslagret,
plottlaget och torpedrummet lyssnar utan att känna till sonaren.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .. import acoustics, phrases
from ..crew import Role
from ..entities import Transient
from ..events import (BearingObserved, ClassificationChanged, ContactDetected, HuntSigns,
                      ContactLost, OwnSoundMade, OwnTorpedoHeard, SoundHeard)
from ..fmt import fmt_course, nm
from .. import russian as R
from ..russian import ru
from ..geo import angle_diff, circular_mean, norm360
from ..orders import CommandSpec, Order
from ..profile import HeardEvent, Level
from ..reports import Quality
from ..systems import INFO, OK, WARN, Gauge
from ..sonar import (ClassificationUpdate, Detection, Lost, OwnTorpedo, SonarStation,
                     TransientHeard)
from ..tma import BearingObs
from .base import Proposal, Station

BEARING_REPORT_DELTA = 5.0
BEARING_REPORT_MAX_AGE = 300
BEARING_MIN_GAP_S = 60       # samma kontakts bäring ropas inte oftare (jakt nära: annars var 5:e s)
SMOOTH_OBS = 6
FAST_PING_S = 13
SLOW_PING_S = 20            # så här långt mellan pingarna två gånger i rad: takten har minskat
PING_SAME_DEG = 8.0         # okända pingar inom så här många grader räknas som samma pingare
PING_DRIFT_DEG_PER_S = 0.15 # ... plus så här mycket per sekund sedan förra pingen (pingaren rör sig)
PING_SAME_MAX_DEG = 20.0
PING_SMOOTH = 0.5           # ny ping väger så här mycket i pingarens bäring
ICE_REPORT_S = 1800          # knakande is rapporteras inte oftare
PROFILE_KEEP_S = 3 * 3600    # djupprofilen minns hörda ljud så här länge
# Djupprofilens symboler för hörda ljud (och våra egna): (symbol, stil)
HEARD_SYMBOL = {
    "ping": ("◦", "heard_ping"), "splash": ("↓", "heard_splash"),
    "explosion": ("✱", "heard_explosion"), "practice": ("*", "heard_practice"),
    "buoy": ("⊥", "heard_buoy"), "buoy_ping": ("◎", "heard_buoy"),
    "uwt": ("~", "heard_other"), "breakup": ("×", "heard_explosion"),
}
OWN_SYMBOL = {"ping": ("!", "own_sound"), "launch": ("»", "own_sound"),
              "decoy": ("o", "own_sound"), "blow": ("↑", "own_sound")}


@dataclass(frozen=True)
class ActivePing(Order):
    pass


def _src(d: dict) -> str:
    return f" från {d['designation']}" if d.get("designation") else ""


PHRASES = {
    "sonar.new_contact": lambda d: f"{ru('Tovarisjtj komandir')}, sonar! Ny kontakt i bäring {fmt_course(d['bearing'])}. "
    f"Betecknas {d['designation']}. {d['classification'][:1].upper()}{d['classification'][1:]}.",
    "sonar.classified": lambda d: f"{d['designation']} klassas som {d['classification']}.",
    "sonar.bearing": lambda d: f"{d['designation']}, bäring {fmt_course(d['bearing'])}, "
    f"{d['strength']} signal" + {1: ", bäringen drar höger", -1: ", bäringen drar vänster"}
    .get(d.get("drift", 0), "") + ".",
    "sonar.lost": lambda d: f"Kapten, sonar. Har tappat {d['designation']}"
    + (f", sista bäring {fmt_course(d['last_bearing'])}" if d.get("last_bearing") is not None else "")
    + ".",
    "sonar.regained": lambda d: f"{d['designation']} hörs igen, bäring {fmt_course(d['bearing'])}.",
    "sonar.ping.first": lambda d: f"Kapten, sonar! Aktiv sonar i bäring {fmt_course(d['bearing'])}"
    f"{_src(d)}. Någon söker.",
    "sonar.ping.fast": lambda d: f"{ru('Tovarisjtj komandir')}, sonar! Pingtakten{_src(d)} har ökat kraftigt. "
    "De har troligen kontakt med oss!",
    "sonar.ping.slow": lambda d: f"Pingtakten{_src(d)} har minskat igen.",
    "sonar.ping.close": lambda d: f"Pingarna{_src(d)} är mycket starka nu, kapten. "
    "Jag hör dem genom skrovet.",
    "sonar.splash": lambda d: f"Kapten, sonar! Plask i vattnet, bäring {fmt_course(d['bearing'])}"
    + (", nära!" if d.get("near") else ".") + " Sjunkbomber!",
    "sonar.explosion": lambda d: (
        f"Små detonationer i bäring {fmt_course(d['bearing'])}. Troligen signalsjunkbomber."
        if d.get("practice") else
        f"Detonation i bäring {fmt_course(d['bearing'])}" + (", mycket nära!" if d.get("near") else "!")),
    "sonar.nuclear": lambda d: f"Kapten! Enorm detonation i bäring {fmt_course(d['bearing'])}. "
    "Hela hydrofonen är mättad.",
    "sonar.uwt": lambda d: f"Undervattenstelefon i bäring {fmt_course(d['bearing'])}. Morse, "
    "upprepat. Jag tror de uppmanar oss att gå till ytan.",
    "sonar.breakup": lambda d: f"Brytningsljud i bäring {fmt_course(d['bearing'])}{_src(d)}. "
    "Skott som ger vika. Ett fartyg sjunker, kapten.",
    "sonar.buoy": lambda d: f"Kapten, sonar. Små plask i bäring {fmt_course(d['bearing'])}, "
    "inget motorljud. Troligen sonobojar från ett flygplan. De lyssnar efter oss.",
    "sonar.buoy_ping": lambda d: f"Kapten, sonar! Korta ljusa pingar i bäring "
    f"{fmt_course(d['bearing'])}, från en fast punkt. Aktiv sonoboj.",
    "sonar.suggest.quiet": lambda d: "Kapten, sonar. Föreslår smygmotor, så hör bojarna oss sämre.",
    "sonar.ice": lambda d: f"Knakande isljud i bäring {fmt_course(d['bearing'])}"
    + (", starkt. Isen skruvar sig nära." if d.get("near") else ". Isen skruvar sig."),
    "sonar.active.none": lambda d: "Aktiv sonar: inga ekon.",
    "sonar.active.echo": lambda d: f"Aktiv sonar: eko {d['designation']} i bäring "
    f"{fmt_course(d['bearing'])}, avstånd {nm(d['range'])} sjömil.",
    "sonar.active.refused": lambda d: f"Kapten, {d['reason']}.",
    "sonar.suggest.layer": lambda d: f"Kapten, sonar. Vi ligger ovanför språngskiktet på "
    f"{d['layer']:.0f} meter. Föreslår djup {d['depth']:.0f}, under skiktet hörs vi sämre.",
    "sonar.suggest.depth_change": lambda d: f"Föreslår djupändring till {d['depth']:.0f} meter, "
    "så att laddningarna är inställda på fel djup!",
    "sonar.suggest.slow": lambda d: f"Kapten, sonar. Vi hör dåligt i {d['speed']:.0f} knop. "
    "Föreslår fart 4.",
}
phrases.register(PHRASES)


STRENGTH_RU = {"svag": "слабый", "tydlig": "чёткий", "stark": "сильный"}


def _ru_src(d: dict) -> str:
    return f" от {R.contact(d['designation'], True)}" if d.get("designation") else ""


def _ru_cap(s: str) -> str:
    return s[:1].upper() + s[1:]


RU_PHRASES = {
    "sonar.new_contact": lambda d: f"{R.CAPTAIN}, акустик! Новый контакт, пеленг "
    f"{R.course(d['bearing'])}, {R.contact(d['designation'])}. "
    f"{_ru_cap(R.classification(d['classification']))}.",
    "sonar.classified": lambda d: f"{_ru_cap(R.contact(d['designation']))}: "
    f"{R.classification(d['classification'])}.",
    "sonar.bearing": lambda d: f"{_ru_cap(R.contact(d['designation']))}, пеленг "
    f"{R.course(d['bearing'])}, сигнал {STRENGTH_RU.get(d['strength'], '')}"
    + {1: ", пеленг смещается вправо", -1: ", пеленг смещается влево"}.get(d.get("drift", 0), "")
    + ".",
    "sonar.lost": lambda d: f"{R.CAPTAIN}, акустик. {_ru_cap(R.contact(d['designation']))} потеряна"
    + (f", последний пеленг {R.course(d['last_bearing'])}" if d.get("last_bearing") is not None
       else "") + ".",
    "sonar.regained": lambda d: f"{_ru_cap(R.contact(d['designation']))} снова слышна, пеленг "
    f"{R.course(d['bearing'])}.",
    "sonar.ping.first": lambda d: f"{R.CAPTAIN}, акустик! Работа гидролокатора, пеленг "
    f"{R.course(d['bearing'])}{_ru_src(d)}. Нас ищут.",
    "sonar.ping.fast": lambda d: f"{R.CAPTAIN}, акустик! Темп посылок{_ru_src(d)} резко возрос. "
    "Видимо, они нас обнаружили!",
    "sonar.ping.slow": lambda d: f"Темп посылок{_ru_src(d)} снова снизился.",
    "sonar.ping.close": lambda d: f"Посылки{_ru_src(d)} очень сильные, товарищ командир. "
    "Слышно через корпус.",
    "sonar.splash": lambda d: f"{R.CAPTAIN}, акустик! Всплески, пеленг {R.course(d['bearing'])}"
    + (", близко!" if d.get("near") else ".") + " Глубинные бомбы!",
    "sonar.explosion": lambda d: (
        f"Слабые взрывы, пеленг {R.course(d['bearing'])}. Видимо, сигнальные заряды."
        if d.get("practice") else
        f"Взрыв, пеленг {R.course(d['bearing'])}" + (", очень близко!" if d.get("near") else "!")),
    "sonar.nuclear": lambda d: f"{R.CAPTAIN}! Мощнейший взрыв, пеленг {R.course(d['bearing'])}. "
    "Гидрофоны забиты.",
    "sonar.uwt": lambda d: f"Звукоподводная связь, пеленг {R.course(d['bearing'])}. Морзе, "
    "повторяют. Думаю, требуют всплыть.",
    "sonar.breakup": lambda d: f"Шумы разрушения корпуса, пеленг {R.course(d['bearing'])}"
    f"{_ru_src(d)}. Переборки не выдерживают. Судно тонет, товарищ командир.",
    "sonar.buoy": lambda d: f"{R.CAPTAIN}, акустик. Слабые всплески, пеленг "
    f"{R.course(d['bearing'])}, шума винтов нет. Видимо, самолёт ставит буи. Нас слушают.",
    "sonar.buoy_ping": lambda d: f"{R.CAPTAIN}, акустик! Короткие высокие посылки, пеленг "
    f"{R.course(d['bearing'])}, из неподвижной точки. Активный буй.",
    "sonar.suggest.quiet": lambda d: f"{R.CAPTAIN}, акустик. Предлагаю перейти на электромотор, "
    "тогда буи нас хуже услышат.",
    "sonar.ice": lambda d: f"Треск льда, пеленг {R.course(d['bearing'])}"
    + (", сильный. Лёд торосится рядом." if d.get("near") else ". Лёд торосится."),
    "sonar.active.none": lambda d: "Активный поиск: эха нет.",
    "sonar.active.echo": lambda d: f"Активный поиск: эхо от {R.contact(d['designation'], True)}, "
    f"пеленг {R.course(d['bearing'])}, дистанция {R.dec(d['range'], R.MILE)}.",
    "sonar.suggest.layer": lambda d: f"{R.CAPTAIN}, акустик. Мы над слоем скачка, он на глубине "
    f"{R.count(d['layer'], R.METER)}. Предлагаю глубину {R.count(d['depth'], R.METER)}, "
    "под слоем нас хуже слышно.",
    "sonar.suggest.depth_change": lambda d: f"Предлагаю сменить глубину на "
    f"{R.count(d['depth'], R.METER)}, чтобы бомбы были установлены на неверную глубину!",
    "sonar.suggest.slow": lambda d: f"{R.CAPTAIN}, акустик. На ходу {R.count(d['speed'], R.KNOT)} "
    "слышим плохо. Предлагаю ход четыре узла.",
}
phrases.register_ru(RU_PHRASES)


class SonarRoom(Station):
    role = Role.SONAR
    COMMANDS = [
        CommandSpec(r"aktiv sonar|pinga|ping|aktiv", lambda m: ActivePing(), "aktiv sonar"),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.sensor = SonarStation(self.member, random.Random(game.rng.random()))
        self._last_called: dict[str, tuple[float, int]] = {}
        self._pings: dict[str, dict] = {}
        self._unknown_pingers = 0
        self._last_sound: dict[str, int] = {}
        self.heard: list[HeardEvent] = []          # för djupprofilen

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(SoundHeard, self._note_heard)
        bus.subscribe(OwnSoundMade, self._note_own)

    # --- djupprofilen ------------------------------------------------------------
    def _note(self, e: HeardEvent) -> None:
        self.heard.append(e)
        cutoff = self.now - PROFILE_KEEP_S
        if self.heard[0].t < cutoff:
            self.heard = [h for h in self.heard if h.t >= cutoff]

    def _note_heard(self, e: SoundHeard) -> None:
        kind = "practice" if e.kind == "explosion" and e.practice else e.kind
        if kind not in HEARD_SYMBOL:
            return
        sym, style = HEARD_SYMBOL[kind]
        near = e.se > (110 if kind == "explosion" else 45 if kind == "splash" else 75)
        self._note(HeardEvent(e.t, kind, sym, style, near))

    def _note_own(self, e: OwnSoundMade) -> None:
        if e.kind in OWN_SYMBOL:
            sym, style = OWN_SYMBOL[e.kind]
            self._note(HeardEvent(e.t, "own_" + e.kind, sym, style))

    def profile_items(self) -> list:
        items: list = list(self.heard)
        layer = self.game.world.env.layer_depth
        if layer is not None:
            items.append(Level(layer, "språngskikt", "layer", "─"))
        return items

    # --- systemtavlan ------------------------------------------------------------
    def system_items(self) -> list:
        held = self.held_designations()
        k = self.game.knowledge
        threats = [d for d in held if (tr := k.track(d)) is not None and tr.threat]
        noise, ice = self.background()
        items = [Gauge("SONAR", "Kontakter", ", ".join(held) if held else "inga",
                       WARN if threats else INFO if held else OK),
                 Gauge("SONAR", "Bakgrund", f"{noise:.0f} dB" + (", isbrus" if ice else ""), INFO)]
        if self.game.world.own.sys.health["sonar"] < 0.5:
            items.append(Gauge("SONAR", "Aktiv sonar", "ur bruk, skadad", WARN))
        return items

    def held_designations(self) -> list[str]:
        return self.sensor.held_designations()

    def background(self) -> tuple[float, bool]:
        """Bakgrundsbruset i lurarna: (dB, kommer från isen)."""
        return self.sensor.background, self.sensor.under_ice

    @property
    def own(self):
        return self.game.world.own

    # --- order -------------------------------------------------------------------
    def on_order(self, order: Order) -> None:
        if isinstance(order, ActivePing):
            self._active_ping()

    def _active_ping(self) -> None:
        world, own = self.game.world, self.own
        if own.sys.health["sonar"] < 0.3:
            self.say("sonar.active.refused", {"reason": "sonaren är skadad"})
            return
        o = own.state
        world.emit(Transient("ping", o.x, o.y, o.depth, acoustics.PING_LEVEL_OWN, own.id, self.now))
        self.game.bus.publish(OwnSoundMade(self.now, "ping"))
        world.mission["own_pings"] = world.mission.get("own_pings", 0) + 1
        noise = acoustics.power_sum(world.background_at_own(), own.self_noise())
        own_xy = self.game.own_position_estimate()
        rng = self.sensor.rng
        echoes = []
        for v in world.contacts:
            if v.side == "own" or v.sunk or not v.is_ship:
                continue
            tl = world.tl_to_own(v.state.x, v.state.y, v.depth)
            se = acoustics.active_excess(acoustics.PING_LEVEL_OWN, tl, v.target_strength,
                                         noise, self.sensor.threshold(world)) + rng.gauss(0, 2)
            if se <= 0:
                continue
            r = world.true_range(v)
            desig = self.sensor.designate(v.id)
            if self.game.knowledge.tracks.get(desig) is None:
                self.game.bus.publish(ContactDetected(self.now, desig, world.true_bearing(v),
                                                      "eko, okänd typ", Quality.DALIG))
            r_meas = max(0.05, r + rng.gauss(0, 0.02 * r + 0.02))
            obs = BearingObs(self.now, norm360(world.true_bearing(v) + rng.gauss(0, 1.0)), 1.0,
                             own_xy[0], own_xy[1], o.course, se=se, designation=desig,
                             range_nm=r_meas, range_sigma=0.02 * r + 0.02, source="aktiv")
            self.game.bus.publish(BearingObserved(self.now, obs))
            echoes.append({"designation": desig, "bearing": obs.bearing, "range": r_meas})
        if not echoes:
            self.say("sonar.active.none")
        for e in echoes:
            self.say("sonar.active.echo", e, kind="contact", quality=Quality.SAKER)

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        bus = self.game.bus
        own_xy = self.game.own_position_estimate()
        for ev in self.sensor.update(self.game.world, own_xy):
            match ev:
                case Detection():
                    known = self.game.knowledge.tracks.get(ev.designation)
                    bus.publish(ContactDetected(self.now, ev.designation, ev.bearing,
                                                ev.classification, ev.quality))
                    self._last_called[ev.designation] = (ev.bearing, self.now)
                    if known is not None:
                        self.say("sonar.regained", {"designation": ev.designation,
                                                    "bearing": ev.bearing}, kind="contact")
                        continue
                    self.say("sonar.new_contact",
                             {"designation": ev.designation, "bearing": ev.bearing,
                              "classification": ev.classification},
                             kind="contact", quality=ev.quality, alarm=True)
                    self._suggest_layer()
                case ClassificationUpdate():
                    tr = self.game.knowledge.tracks.get(ev.designation)
                    if tr is not None and tr.class_quality > ev.quality:
                        continue        # utkiken (periskop, brygga) har redan sett bättre
                    bus.publish(ClassificationChanged(self.now, ev.designation,
                                                      ev.classification, ev.quality))
                    self.say("sonar.classified",
                             {"designation": ev.designation, "classification": ev.classification},
                             kind="contact", quality=ev.quality)
                case Lost():
                    bus.publish(ContactLost(self.now, ev.designation))
                    tr = self.game.knowledge.tracks.get(ev.designation)
                    self.say("sonar.lost", {"designation": ev.designation,
                                            "last_bearing": tr.last_bearing if tr else None},
                             kind="contact")
                    if self.own.state.speed > 6 and not self.game.knowledge.hunted(self.now) \
                            and not self.own.bridge_open:   # i ytläge ser bryggan
                        self.suggest("slow", "sonar.suggest.slow",
                                     {"speed": self.own.state.speed}, order="fart 4", cooldown=600)
                case BearingObs():
                    bus.publish(BearingObserved(self.now, ev))
                    if ev.source == "sonar":
                        self._maybe_call_bearing(ev.designation)
                case TransientHeard():
                    self._on_sound(ev)
                case OwnTorpedo():
                    # Torpedrummet rapporterar egna torpeder med tubnummer.
                    q = Quality.GOD if ev.se >= 6 else Quality.OSAKER
                    bus.publish(OwnTorpedoHeard(self.now, ev.no, ev.kind, ev.bearing, q))

    def idle_proposals(self) -> list[Proposal]:
        st, env = self.own.state, self.game.world.env
        held = self.game.knowledge.threat_held()
        out = []
        d = self._below_layer(env.layer_depth) if env.layer_depth is not None else None
        if held and d is not None and st.ordered_depth < env.layer_depth \
                and not self._up_for_radio():
            out.append(Proposal(2, "idle_layer", "sonar.suggest.layer",
                                f"djup {d:.0f}", {"layer": env.layer_depth, "depth": d}))
        if not held and st.ordered_speed > 6 and not self.own.bridge_open:
            out.append(Proposal(4, "idle_slow", "sonar.suggest.slow", "fart 4",
                                {"speed": st.ordered_speed}))
        return out

    def _depth_limit(self) -> float | None:
        """Navigatörens gräns mot botten (sjökortet och ekolodet), om den finns."""
        from .navigation import NavigationStation
        try:
            return self.game.station(NavigationStation).depth_limit()
        except KeyError:
            return None

    def _below_layer(self, layer: float) -> float | None:
        """Djup under skiktet som botten tillåter, eller None om det inte finns plats."""
        if self.own.sys.settle or self.own.sys.on_bottom:
            return None                     # vi ligger på (eller går ned mot) botten
        d = layer + 60
        lim = self._depth_limit()
        if lim is not None:
            d = min(d, lim)
        return d if d >= layer + 20 else None

    def _up_for_radio(self) -> bool:
        """Ligger vi uppe för ett sambandstillfälle som inte är avklarat? Då föreslår sonar
        inte skiktet, så länge fienden inte har oss."""
        from .radio import RadioStation
        try:
            radio = self.game.station(RadioStation)
        except KeyError:
            return False
        return radio.needs_mast() and not self.game.knowledge.hunted(self.now)

    def _suggest_layer(self) -> None:
        env, st = self.game.world.env, self.own.state
        if env.layer_depth is not None and st.ordered_depth < env.layer_depth \
                and not self._up_for_radio():
            d = self._below_layer(env.layer_depth)
            if d is None:
                return
            self.suggest("layer", "sonar.suggest.layer", {"layer": env.layer_depth, "depth": d},
                         order=f"djup {d:.0f}", cooldown=1800)

    def _dedupe(self, key: str, window: int) -> bool:
        if self.now - self._last_sound.get(key, -10**9) < window:
            return False
        self._last_sound[key] = self.now
        return True

    def _on_sound(self, ev: TransientHeard) -> None:
        bus = self.game.bus
        d = {"bearing": ev.bearing, "designation": ev.designation}
        detail = ""
        if ev.kind == "ping":
            # okända pingare hålls isär på bäringen: två jagare i skärm är inte en snabb pingare
            # bäringen brusar ett par grader per ping och pingaren rör sig: närmaste inom grinden
            unknown, best = None, None
            for k, q in self._pings.items():
                if not k.startswith("okänd"):
                    continue
                off = abs(angle_diff(q.get("bearing", ev.bearing), ev.bearing))
                since = self.now - q["last"] if q["last"] is not None else 0
                gate = min(PING_SAME_MAX_DEG, PING_SAME_DEG + PING_DRIFT_DEG_PER_S * since)
                if off <= gate and (best is None or off < best):
                    unknown, best = k, off
            if unknown is None and not ev.designation:
                self._unknown_pingers += 1
            key = ev.designation or unknown or f"okänd{self._unknown_pingers}"
            if key not in self._pings and unknown and ev.designation:
                self._pings[key] = self._pings.pop(unknown)      # samma pingare, nu identifierad
            p = self._pings.setdefault(key, {"last": None, "fast": False, "close_t": -10**9,
                                             "slow_n": 0})
            # utjämnad bäring: en enstaka brusig ping drar inte iväg grinden
            p["bearing"] = ev.bearing if "bearing" not in p else \
                norm360(p["bearing"] + PING_SMOOTH * angle_diff(ev.bearing, p["bearing"]))
            if p["last"] is None or self.now - p["last"] > 900:
                self.say("sonar.ping.first", d, kind="contact", alarm=True)
                self._suggest_layer()
            else:
                interval = self.now - p["last"]
                # en missad ping ger ett långt mellanrum: minskad takt först efter två i rad
                p["slow_n"] = p["slow_n"] + 1 if interval >= SLOW_PING_S else 0
                if interval <= FAST_PING_S and not p["fast"]:
                    p["fast"] = True
                    detail = "fast"
                    self.say("sonar.ping.fast", d, kind="contact", alarm=True)
                    self._evasive_depth()
                elif p["slow_n"] >= 2 and p["fast"]:
                    p["fast"] = False
                    self.say("sonar.ping.slow", d, kind="contact")
            if p["fast"]:
                bus.publish(HuntSigns(self.now, "ping"))
            if ev.se > 75 and self.now - p["close_t"] > 300:
                p["close_t"] = self.now
                self.say("sonar.ping.close", d, kind="contact")
            p["last"] = self.now
        elif ev.kind == "splash":
            if self._dedupe("splash", 20):
                self.say("sonar.splash", {**d, "near": ev.se > 45}, kind="contact", alarm=True)
                bus.publish(HuntSigns(self.now, "splash"))
                self._evasive_depth(cooldown=60)
        elif ev.kind == "explosion":
            if ev.se > 160:
                if self._dedupe("nuclear", 60):
                    self.say("sonar.nuclear", d, kind="contact", alarm=True)
            elif ev.own_weapon:
                pass                    # torpedrummet rapporterar sina egna träffar
            elif self._dedupe("explosion", 10):
                self.say("sonar.explosion", {**d, "practice": ev.practice, "near": ev.se > 110},
                         kind="contact", alarm=not ev.practice)
        elif ev.kind == "buoy":
            if self._dedupe("buoy", 300):
                self.say("sonar.buoy", d, kind="contact", alarm=True)
                if self.own.sys.propulsion == "turbine":
                    self.suggest("quiet", "sonar.suggest.quiet", order="smygmotor", cooldown=900)
        elif ev.kind == "buoy_ping":
            if self._dedupe("buoy_ping", 600):
                self.say("sonar.buoy_ping", d, kind="contact", alarm=True)
                self._evasive_depth()
        elif ev.kind == "ice":
            if self._dedupe("ice", ICE_REPORT_S):
                self.say("sonar.ice", {**d, "near": ev.se > 25}, kind="contact",
                         quality=Quality.GOD if ev.se > 10 else Quality.OSAKER)
        elif ev.kind == "uwt":
            if self._dedupe("uwt", 120):
                self.say("sonar.uwt", d, kind="contact")
        elif ev.kind == "breakup":
            if self._dedupe(f"breakup{ev.designation}", 60):
                # brytningsljudet följer på detonationen; rapportera det efter den
                self.say("sonar.breakup", d, kind="contact", alarm=True, extra_delay=6)
        bus.publish(SoundHeard(self.now, ev.kind, ev.bearing, ev.designation, ev.practice, detail,
                               se=ev.se))

    def _evasive_depth(self, cooldown: int = 300) -> None:
        st = self.own.state
        if self.own.sys.settle or self.own.sys.on_bottom:
            return
        env = self.game.world.env
        if env.layer_depth is not None and st.ordered_depth < env.layer_depth:
            d = env.layer_depth + 60
        elif st.ordered_depth < 200:
            d = min(st.ordered_depth + 80, 280)
        elif st.ordered_speed > acoustics.cavitation_speed(st.ordered_depth - 80):
            d = min(st.ordered_depth + 60, 280)     # grundare skulle vi kavitera i den här farten
        else:
            d = st.ordered_depth - 80
        lim = self._depth_limit()
        if lim is not None and d > lim:
            d = lim
            if abs(d - st.ordered_depth) < 20:
                return                      # botten ger inget utrymme att byta djup
        self.suggest("evade_depth", "sonar.suggest.depth_change", {"depth": d},
                     order=f"djup {d:.0f}", cooldown=cooldown, alarm=True)

    def _maybe_call_bearing(self, designation: str) -> None:
        tr = self.game.knowledge.tracks.get(designation)
        if tr is None or not tr.observations:
            return
        recent = [o for o in tr.observations if o.source == "sonar"][-SMOOTH_OBS:]
        if not recent:
            return
        bearing = circular_mean([o.bearing for o in recent])
        prev, prev_t = self._last_called.get(designation, (None, -10**9))
        delta = angle_diff(bearing, prev) if prev is not None else 0.0
        if abs(delta) < BEARING_REPORT_DELTA and self.now - prev_t < BEARING_REPORT_MAX_AGE:
            return
        if self.now - prev_t < BEARING_MIN_GAP_S:
            return
        self._last_called[designation] = (bearing, self.now)
        se = sum(o.se for o in recent) / len(recent)
        self.say("sonar.bearing",
                 {"designation": designation, "bearing": bearing,
                  "strength": "svag" if se < 2 else "tydlig" if se < 6 else "stark",
                  "drift": 0 if abs(delta) < 2 else (1 if delta > 0 else -1)},
                 kind="contact")
