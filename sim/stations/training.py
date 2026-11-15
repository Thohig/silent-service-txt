"""Övningsledaren: vakthavande går igenom scenariots övningsprogram steg för steg.

Scenariot listar stegen (`Scenario.training`). Varje steg föreslås som en ja-order
med en kort förklaring av vad ordern gör, och bockas av ur egna instrument (djup,
framdrivning), navigatörens fix eller periskopets bild – aldrig ur sanningen om
världen. Stegen efter `framme` görs i övningsområdet, provdjupet bara där kortet
visar tillräckligt djup. När alla steg är klara anmäler vakthavande det, och
uppdraget (`mission["training"]`) räknas som genomfört en halv minut senare.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .. import phrases
from .. import russian as R
from ..crew import Role
from ..events import ListeningExercise, OwnSoundMade, PeriscopeSighted
from ..exercise import partner_report, torpedo_report
from ..fmt import fmt_course, kn, nm
from ..geo import bearing_to, distance
from ..ownship import TEST_DEPTH
from ..reports import Quality
from .base import Station
from .navigation import NavigationStation

CHECK_S = 5                  # stegen kontrolleras så här ofta
PAUSE_S = 30                 # efter ett avklarat steg: så länge innan nästa föreslås
SUGGEST_S = 300              # obesvarat förslag upprepas (glesas ut av Station.suggest)
AREA_NM = 1.5                # inom så här långt från övningsområdets mitt är vi framme
AREA_LEAVE_NM = 3.0          # ... och kvar i området tills vi är så här långt bort
PROOF_MARGIN_M = 40          # provdjup bara där kortet visar så här mycket vatten under
DIVED_M = 10                 # så djupt: vi har dykt
DEPTH_DONE_M = 5             # beordrat djup nått inom så här många meter
FJORD_MARGIN_NM = 0.5        # kortet och besticket kan fela: ute först så här långt utanför
LOOK_FRESH_S = 120           # före uppstigning: periskopbilden högst så här gammal
SURFACE_CLEAR_NM = 1.0       # och inget fartyg närmare än så
PD_SPEED = 6                 # på periskopdjup: inte fortare (kavitation, periskopet vibrerar)
LISTEN_DEPTH = 40            # lyssningsövningen: över språngskiktet, där ytfartyget hörs
LISTEN_MIN_S = 8 * 60        # lyssna minst så här länge efter förslaget
LISTEN_MAX_S = 25 * 60       # så länge får plottet hålla på innan övningen avbryts
LISTEN_TARGET = "bevakningsfartyg"
TORP_MAX_S = 15 * 60         # utan avfyring så här länge efter genomgången: steget hoppas över
TORP_AFTER_S = 60            # partnern rapporterar så här länge efter beräknad passage
TORP_BRIEF_S = 300           # genomgången upprepas så här ofta (glesas ut)
DONE_DELAY_S = 30            # anmälan levereras innan övningen räknas som klar


@dataclass(frozen=True)
class Step:
    order: str | None        # None: vakthavande förklarar, kaptenen ger ordern själv (vapen)
    name: str                # som vakthavande säger det: "övningen <name>"
    area: bool = False       # görs i övningsområdet


STEPS: dict[str, Step] = {
    "dyk": Step(f"fart {PD_SPEED}, periskopdjup", "dykning"),
    "svep": Step("periskop", "periskopsvep"),
    "fix": Step("fix", "fix i periskopet"),
    "framme": Step("fart 4", "framme i övningsområdet", area=True),
    "djup100": Step("djup 100", "djup 100", area=True),
    "provdjup": Step(f"djup {TEST_DEPTH:.0f}", "provdjup", area=True),
    "smyg": Step("smygmotor", "smygmotorn", area=True),
    "lyssna": Step(f"djup {LISTEN_DEPTH}", "lyssning", area=True),
    "torped": Step(None, "övningstorped", area=True),
    "pd": Step("periskopdjup", "periskopdjup"),
    "upp": Step("ytläge", "uppstigning"),
}


class TrainingOfficer(Station):
    """Vakthavande som övningsledare. Gör ingenting utan övningsprogram i scenariot."""
    role = Role.OFFICER

    def __init__(self, game):
        super().__init__(game)
        sc = game.scenario
        self.steps: list[str] = list(getattr(sc, "training", ()) or ())
        self.area_name: str | None = getattr(sc, "training_area", None)
        self.i = 0
        self.step_t = 0               # när stegets förslag får ges
        self.started_t = 0            # när steget började (bilder och fixar räknas efter)
        self.done: list[tuple[str, int]] = []
        self._in_area = False
        self._look_t = -10**9
        self._listen_t: int | None = None     # när lyssningsövningen föreslogs första gången
        self._torp_t: int | None = None       # när torpedövningen gicks igenom första gången
        self._fired_t: int | None = None      # senaste avfyring (vårt eget ljud)
        self.rng = random.Random(1962)          # undervattenstelefonens fel: egen slump

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(PeriscopeSighted, lambda e: setattr(self, "_look_t", e.t))
        bus.subscribe(OwnSoundMade, self._on_own_sound)

    def _on_own_sound(self, e: OwnSoundMade) -> None:
        if e.kind == "launch":
            self._fired_t = e.t

    @property
    def own(self):
        return self.game.world.own

    # --- kunskap ---------------------------------------------------------------
    def _area(self):
        return self.game.knowledge.waypoints.get(self.area_name) if self.area_name else None

    def _in_fjord(self) -> bool:
        """Enligt kortet och besticket: är vi inne i fjorden?"""
        chart = self.game.knowledge.bathymetry
        if chart is None:
            return False
        x, y = self.game.own_position_estimate()
        return any(hasattr(f, "in_fjord") and bool(f.in_fjord(x, y, FJORD_MARGIN_NM))
                   for f in chart.features)

    def _chart_depth(self) -> float | None:
        chart = self.game.knowledge.bathymetry
        if chart is None:
            return None
        return chart.depth_at(*self.game.own_position_estimate())

    def _listen_track(self):
        """Bevakningsfartyget i plottet, med en lösning minst god."""
        for tr in self.game.knowledge.tracks.values():
            sol = tr.solution
            if tr.held and LISTEN_TARGET in tr.classification and sol is not None \
                    and sol.quality >= Quality.GOD:
                return tr
        return None

    def _exercise_running(self) -> bool:
        """En övningstorped är på väg mot målet (partnern kan rapportera en minut efter
        beräknad passage; resten av gången väntar vi inte på)."""
        from .torpedo_room import TorpedoRoom
        return any(r.type == "övning" and self.now < (r.t_hit + TORP_AFTER_S if r.t_hit
                                                       else r.t_end)
                   for r in self.game.station(TorpedoRoom).in_water)

    def _torp_brief(self) -> dict:
        from .torpedo_room import TorpedoRoom
        tubes = [t.n for t in self.game.station(TorpedoRoom).tubes if t.load == "övning"]
        tr = self._listen_track() or next(
            (t for t in self.game.knowledge.tracks.values() if t.held and t.friendly), None)
        return {"tubes": tubes, "designation": tr.designation if tr else None,
                "good": tr is not None and tr.solution is not None
                and tr.solution.quality >= Quality.GOD}

    def _step_done(self, key: str) -> bool:
        st, sys = self.own.state, self.own.sys
        match key:
            case "dyk":
                return st.depth >= DIVED_M
            case "svep":
                return self._look_t >= self.started_t
            case "fix":
                nav = self.game.station(NavigationStation)
                return nav.last_fix_t >= self.started_t and st.depth >= DIVED_M
            case "framme":
                return st.ordered_speed <= 5
            case "djup100":
                return st.depth >= 100 - DEPTH_DONE_M
            case "provdjup":
                return st.depth >= TEST_DEPTH - DEPTH_DONE_M
            case "smyg":
                return sys.propulsion == "electric"
            case "lyssna":
                if self._listen_t is None:
                    return False
                spent = self.now - self._listen_t
                return spent >= LISTEN_MAX_S or \
                    spent >= LISTEN_MIN_S and self._listen_track() is not None
            case "torped":
                if self._torp_t is None:
                    return False
                if self._fired_t is not None and self._fired_t >= self._torp_t:
                    return not self._exercise_running()
                return self.now - self._torp_t >= TORP_MAX_S
            case "pd":
                return st.depth <= 18 and not self.own.surfaced
            case "upp":
                return self.own.surfaced
        return False

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        if not self.steps or self.i >= len(self.steps) or self.now % CHECK_S:
            return
        a = self._area()
        if a is not None:
            x, y = self.game.own_position_estimate()
            d = distance(x, y, a.x, a.y)
            self._in_area = d <= (AREA_LEAVE_NM if self._in_area else AREA_NM)
        key = self.steps[self.i]
        step = STEPS[key]
        if self.now >= self.started_t and (self._in_area or not step.area) \
                and self._step_done(key):
            self._finish(key)
            return
        if self.now < self.step_t:
            return
        if self._in_fjord():
            return                          # ordern: dykning först utanför mynningen
        if step.area and not self._in_area:
            if a is not None and self.done:     # vi har dykt men är inte i området
                self.suggest("train_area", "train.suggest.area",
                             {"name": a.name, "course": bearing_to(x, y, a.x, a.y), "range": d},
                             order=f"kurs mot {a.name.lower()}", cooldown=SUGGEST_S)
            return
        data: dict = {}
        order = step.order
        if key == "svep" and self.own.state.ordered_speed > PD_SPEED + 1:
            order = f"fart {PD_SPEED}, periskop"
            data["slow"] = PD_SPEED
        if key == "upp":
            if self.own.state.depth > 18:
                self.suggest("train_pd", "train.suggest.pd", {}, order="periskopdjup",
                             cooldown=SUGGEST_S)
                return
            pic = self.game.knowledge.periscope
            if pic is None or self.now - pic.t > LOOK_FRESH_S or pic.t < self.started_t:
                self.suggest("train_look", "train.suggest.look", {}, order="periskop",
                             cooldown=LOOK_FRESH_S)
                return
            near = [o for o in pic.ships() if o.range_nm < SURFACE_CLEAR_NM]
            if near:
                self.suggest("train_wait", "train.wait_ship",
                             {"designation": near[0].designation, "range": near[0].range_nm},
                             cooldown=LOOK_FRESH_S)
                return
        if key == "djup100":
            data["layer"] = self.game.world.env.layer_depth
        if key == "provdjup":
            cd = self._chart_depth()
            if cd is not None and cd < TEST_DEPTH + PROOF_MARGIN_M:
                a = self._area()
                if a is not None:
                    x, y = self.game.own_position_estimate()
                    self.suggest("train_deeper", "train.suggest.deeper",
                                 {"depth": round(cd, -1), "name": a.name,
                                  "course": bearing_to(x, y, a.x, a.y),
                                  "range": distance(x, y, a.x, a.y)},
                                 order=f"kurs mot {a.name.lower()}", cooldown=SUGGEST_S)
                return
            data["depth"] = round(TEST_DEPTH)
        if key == "torped":
            # vapen föreslås aldrig som ja-order: vakthavande går igenom, kaptenen beordrar
            if self._torp_t is None:
                self._torp_t = self.now
            if self._fired_t is None or self._fired_t < self._torp_t:
                self.suggest("train_torped", "train.torpedo.brief", self._torp_brief(),
                             cooldown=TORP_BRIEF_S)
            return
        if key == "lyssna" and self._listen_t is None:
            self._listen_t = self.now
            self.game.bus.publish(ListeningExercise(self.now, True))
        self.suggest(f"train_{key}", f"train.suggest.{key}", data, order=order,
                     cooldown=SUGGEST_S)

    def _partner_check(self, data: dict, tr) -> None:
        """Bevakningsfartyget meddelar kurs, fart och läge på undervattenstelefonen; vi
        jämför med plottet. Telefonen är en sensor (exercise.partner_report)."""
        rep = partner_report(self.game.world, self.rng)
        if rep is None or self.own.state.depth > 100:
            self.say("train.partner.none", {}, extra_delay=8)
            return
        ex, ey = self.game.own_position_estimate()
        rep = {**rep, "range": distance(ex, ey, rep["x"], rep["y"])}
        out = {"course": rep["course"], "speed": rep["speed"], "range": rep["range"]}
        if tr is not None and tr.solution is not None:
            sol = tr.solution
            dt = (self.now - sol.t) / 3600.0
            sx, sy = sol.x + sol.state[2] * dt, sol.y + sol.state[3] * dt
            out.update(designation=tr.designation,
                       d_course=abs((sol.course - rep["course"] + 180) % 360 - 180),
                       d_speed=abs(sol.speed - rep["speed"]),
                       d_pos=distance(sx, sy, rep["x"], rep["y"]))
        self.say("train.partner", out, extra_delay=8)

    def _finish(self, key: str) -> None:
        self.done.append((key, self.now))
        self.i += 1
        self.step_t = self.now + PAUSE_S
        self.started_t = self.now
        sys = self.own.sys
        data = {"step": key, "name": STEPS[key].name, "last": self.i >= len(self.steps),
                "leak": sys.leak_rate > 0, "depth": round(self.own.state.depth)}
        if key == "lyssna":
            self.game.bus.publish(ListeningExercise(self.now, False))
            tr = self._listen_track()
            if tr is not None:
                sol = tr.solution
                data.update(designation=tr.designation, range=sol.range_nm, course=sol.course,
                            speed=sol.speed, quality=sol.quality.label)
            self._partner_check(data, tr)
        if key == "torped":
            fired = self._fired_t is not None and self._torp_t is not None \
                and self._fired_t >= self._torp_t
            data["fired"] = fired
            if fired:
                rep = torpedo_report(self.game.world)
                self.say("train.torpedo.result", rep or {}, extra_delay=8)
        self.say("train.step.done", data, kind="done")
        if self.i >= len(self.steps):
            first = self.done[0][1]
            self.say("train.done", {"steps": [STEPS[k].name for k, _ in self.done],
                                    "minutes": max(1, round((self.now - first) / 60))},
                     extra_delay=5)
            tr = self.game.world.mission.get("training")
            if tr is not None:
                tr["done_t"] = self.now + DONE_DELAY_S


def _partner_text(d: dict) -> str:
    head = (f"Sonar: bevakningsfartyget på undervattenstelefonen. De går kurs "
            f"{fmt_course(d['course'])}, {d['speed']} knop, {nm(d['range'])} sjömil från oss.")
    if d.get("designation") is None:
        return head
    ok = d["d_course"] < 20 and d["d_speed"] < 4 and d["d_pos"] < max(0.5, 0.3 * d["range"])
    return head + (f" Plottets lösning på {d['designation']} stämmer: kursen {d['d_course']:.0f}°, "
                   f"farten {kn(d['d_speed'])} knop och läget {nm(d['d_pos'])} sjömil fel." if ok else
                   f" Plottets lösning på {d['designation']} låg fel: kursen {d['d_course']:.0f}°, "
                   f"farten {kn(d['d_speed'])} knop och läget {nm(d['d_pos'])} sjömil. "
                   "Fler och större girar ger bättre avstånd.")


def _torpedo_brief_text(d: dict) -> str:
    tubes = " och ".join(str(n) for n in d["tubes"]) or "–"
    target = d["designation"] or "bevakningsfartyget"
    return ("Kapten, vakthavande. Nästa övning: övningstorped mot bevakningsfartyget. "
            f"Tub {tubes} har övningstorpeder utan stridsspets; de går på 12 meter, under kölen. "
            + (f"Plottets lösning på {target} är god. " if d["good"] else
               f"Vänta tills plottets lösning på {target} är god. ")
            + f"Ordern ger ni själv: eld tub {d['tubes'][0] if d['tubes'] else 1} mot {target}"
            + (f", eller båda: salva mot {target}." if len(d["tubes"]) > 1 else "."))


def _torpedo_result_text(d: dict) -> str:
    if not d:
        return "Sonar: bevakningsfartyget svarar inte på undervattenstelefonen om torpeden."
    if d["hit"]:
        return "Sonar: bevakningsfartyget på undervattenstelefonen. Torpeden gick under kölen. Träff!"
    if d["seen"]:
        return (f"Sonar: bevakningsfartyget på undervattenstelefonen. Torpeden passerade "
                f"{d['miss_m']} meter från skrovet. Bom.")
    return "Sonar: bevakningsfartyget på undervattenstelefonen. De såg aldrig torpeden. Bom."


def _step_done_text(d: dict) -> str:
    if d["step"] == "torped" and not d.get("fired"):
        return "Ingen övningstorped avfyrad; vi hoppar över torpedövningen."
    if d["step"] == "torped":
        return "Torpedövningen genomförd."
    if d["step"] == "lyssna":
        if d.get("designation") is None:
            return "Lyssningsövningen avbruten: plottet fick ingen god lösning på bevakningsfartyget."
        return (f"Lyssningsövningen genomförd. Plottet har {d['designation']}, bevakningsfartyget, "
                f"på {nm(d['range'])} sjömil, kurs {fmt_course(d['course'])}, fart "
                f"{kn(d['speed'])} knop, {d['quality']}.")
    if d["step"] == "provdjup":
        return (f"Provdjup, {d['depth']} meter. "
                + ("Läckage, länsning pågår!" if d["leak"] else "Avdelningarna: inga läckor."))
    return f"Övningen {d['name']} genomförd." + ("" if d["last"] else " Nästa om en halv minut.")


PHRASES = {
    "train.suggest.dyk": lambda d: "Kapten, vakthavande. Vi är ute ur fjorden. Första övningen: "
    "dykning. Bryggan utryms och luckan stängs, sedan går vi till periskopdjup och trimmar båten. "
    f"Vi saktar till {PD_SPEED} knop, annars kaviterar propellern och periskopet vibrerar.",
    "train.suggest.svep": lambda d: "Kapten, vakthavande. Nästa övning: periskopsvep. "
    + (f"Fart {d['slow']} först, sedan " if d.get("slow") else "")
    + "periskopet upp och ett varv runt horisonten. Bilden syns i periskopvyn.",
    "train.suggest.fix": lambda d: "Kapten, vakthavande. Nästa övning: fix i periskopet. "
    "Navigatören pejlar landmärken på kusten och rättar besticket.",
    "train.suggest.framme": lambda d: "Kapten, vakthavande. Vi är i övningsområdet. Föreslår "
    "fart 4, så håller vi oss inom området under övningarna.",
    "train.suggest.djup100": lambda d: "Kapten, vakthavande. Nästa övning: djup 100 meter."
    + (f" Vi passerar språngskiktet vid ungefär {d['layer']:.0f} meter; under det hör ytfartygen "
       "oss sämre, och vi dem." if d.get("layer") else ""),
    "train.suggest.provdjup": lambda d: f"Kapten, vakthavande. Nästa övning: provdjup, "
    f"{d['depth']} meter. Skrovet kommer att knaka. Avdelningarna rapporterar läckor.",
    "train.suggest.area": lambda d: f"Kapten, vakthavande. Vi är utanför övningsområdet, "
    f"{nm(d['range'])} sjömil bort. Föreslår kurs mot {d['name'].lower()} innan nästa övning.",
    "train.suggest.deeper": lambda d: f"Kapten, vakthavande. Bara {d['depth']:.0f} meter här enligt "
    f"kortet, för grunt för provdjup. {d['name']} ligger {nm(d['range'])} sjömil bort. "
    f"Föreslår kurs mot {d['name'].lower()}.",
    "train.suggest.smyg": lambda d: "Kapten, vakthavande. Nästa övning: smygmotorn. Turbinen "
    "kopplas ur och vi går på elmotor, högst 5 knop, men mycket tystare.",
    "train.suggest.pd": lambda d: "Kapten, vakthavande. Sista övningen: uppstigning. Först upp "
    "till periskopdjup och en titt runt, så att vi inte kommer upp under ett fartyg.",
    "train.suggest.look": lambda d: "Kapten, vakthavande. Före ytläge: ett periskopsvep, "
    "så att ytan är fri.",
    "train.wait_ship": lambda d: f"Kapten, vakthavande. {d['designation']} är bara "
    f"{nm(d['range'])} sjömil bort. Vi väntar med ytläget tills det har passerat.",
    "train.suggest.lyssna": lambda d: "Kapten, vakthavande. Nästa övning: lyssning. "
    "Bevakningsfartyget rör sig i området. Vi går upp till "
    f"{LISTEN_DEPTH} meter, över språngskiktet, och lyssnar. Plottet räknar fram avstånd, kurs "
    "och fart ur bäringarna; för det måste vi gira, och plottet föreslår när.",
    "train.suggest.upp": lambda d: "Kapten, vakthavande. Ytan är fri. Upp till ytläge: vi blåser "
    "barlast, och bryggan bemannas igen.",
    "train.step.done": _step_done_text,
    "train.partner": _partner_text,
    "train.torpedo.brief": _torpedo_brief_text,
    "train.torpedo.result": _torpedo_result_text,
    "train.partner.none": lambda d: "Sonar: vi når inte bevakningsfartyget på "
    "undervattenstelefonen.",
    "train.done": lambda d: f"Kapten, övningsprogrammet är genomfört på {d['minutes']} minuter: "
    f"{', '.join(d['steps'])}. Jag anmäler till staben.",
}

RU_PHRASES = {
    "train.suggest.dyk": lambda d: f"{R.CAPTAIN}, вахтенный офицер. Вышли из залива. "
    "Предлагаю погружение на перископную глубину.",
    "train.suggest.svep": lambda d: f"{R.CAPTAIN}, предлагаю осмотр горизонта в перископ.",
    "train.suggest.fix": lambda d: f"{R.CAPTAIN}, предлагаю определиться по перископу.",
    "train.suggest.framme": lambda d: f"{R.CAPTAIN}, мы в районе учений. Предлагаю ход "
    f"{R.count(4, R.KNOT)}.",
    "train.suggest.djup100": lambda d: f"{R.CAPTAIN}, предлагаю глубину "
    f"{R.count(100, R.METER)}.",
    "train.suggest.provdjup": lambda d: f"{R.CAPTAIN}, предлагаю рабочую глубину "
    f"{R.count(d['depth'], R.METER)}.",
    "train.suggest.deeper": lambda d: f"{R.CAPTAIN}, здесь мелко. Предлагаю курс "
    f"{R.course(d['course'])} в район учений.",
    "train.suggest.smyg": lambda d: f"{R.CAPTAIN}, предлагаю перейти на электромотор.",
    "train.suggest.area": lambda d: f"{R.CAPTAIN}, мы вне района учений. Предлагаю курс "
    f"{R.course(d['course'])}.",
    "train.suggest.lyssna": lambda d: f"{R.CAPTAIN}, предлагаю глубину "
    f"{R.count(LISTEN_DEPTH, R.METER)}. Слушаем сторожевой корабль.",
    "train.suggest.pd": lambda d: f"{R.CAPTAIN}, предлагаю всплыть на перископную глубину.",
    "train.suggest.look": lambda d: f"{R.CAPTAIN}, перед всплытием предлагаю осмотреться "
    "в перископ.",
    "train.wait_ship": lambda d: f"{R.CAPTAIN}, {R.contact(d['designation'])} близко. "
    "С всплытием ждём.",
    "train.suggest.upp": lambda d: f"{R.CAPTAIN}, горизонт чист. Предлагаю всплытие.",
    "train.step.done": lambda d: (f"Рабочая глубина {R.count(d['depth'], R.METER)}. "
                                  + ("Поступление воды!" if d["leak"] else "Замечаний нет."))
    if d["step"] == "provdjup" else "Упражнение выполнено.",
    "train.done": lambda d: f"{R.CAPTAIN}, программа учений выполнена. Докладываю в штаб.",
    "train.partner": lambda d: f"{R.CAPTAIN}, акустик. Сторожевой корабль по звукоподводной "
    f"связи: курс {R.course(d['course'])}, ход {R.count(d['speed'], R.KNOT)}.",
    "train.partner.none": lambda d: f"{R.CAPTAIN}, акустик. Связи со сторожевым кораблём нет.",
    "train.torpedo.brief": lambda d: f"{R.CAPTAIN}, вахтенный офицер. Следующее упражнение: "
    "практическая торпедная стрельба по сторожевому кораблю. Приказ за вами.",
    "train.torpedo.result": lambda d: f"{R.CAPTAIN}, акустик. "
    + ("Нет связи." if not d else "Торпеда прошла под килем. Попадание!" if d["hit"]
       else "Промах."),
}

phrases.register(PHRASES)
phrases.register_ru(RU_PHRASES)

