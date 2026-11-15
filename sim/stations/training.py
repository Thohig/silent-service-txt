"""Övningsledaren: vakthavande går igenom scenariots övningsprogram steg för steg.

Scenariot listar stegen (`Scenario.training`). Varje steg föreslås som en ja-order
med en kort förklaring av vad ordern gör, och bockas av ur egna instrument (djup,
framdrivning), navigatörens fix eller periskopets bild – aldrig ur sanningen om
världen. Stegen efter `framme` görs i övningsområdet, provdjupet bara där kortet
visar tillräckligt djup. När alla steg är klara anmäler vakthavande det, och
uppdraget (`mission["training"]`) räknas som genomfört en halv minut senare.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import phrases
from .. import russian as R
from ..crew import Role
from ..events import PeriscopeSighted
from ..fmt import nm
from ..geo import bearing_to, distance
from ..ownship import TEST_DEPTH
from .base import Station
from .navigation import NavigationStation

CHECK_S = 5                  # stegen kontrolleras så här ofta
PAUSE_S = 30                 # efter ett avklarat steg: så länge innan nästa föreslås
SUGGEST_S = 300              # obesvarat förslag upprepas (glesas ut av Station.suggest)
AREA_NM = 1.5                # inom så här långt från övningsområdets mitt är vi framme
PROOF_MARGIN_M = 40          # provdjup bara där kortet visar så här mycket vatten under
DIVED_M = 10                 # så djupt: vi har dykt
DEPTH_DONE_M = 5             # beordrat djup nått inom så här många meter
FJORD_MARGIN_NM = 0.5        # kortet och besticket kan fela: ute först så här långt utanför
LOOK_FRESH_S = 120           # före uppstigning: periskopbilden högst så här gammal
SURFACE_CLEAR_NM = 1.5       # och inget fartyg närmare än så
PD_SPEED = 6                 # på periskopdjup: inte fortare (kavitation, periskopet vibrerar)
DONE_DELAY_S = 30            # anmälan levereras innan övningen räknas som klar


@dataclass(frozen=True)
class Step:
    order: str
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
    "pd": Step("periskopdjup", "periskopdjup", area=True),
    "upp": Step("ytläge", "uppstigning", area=True),
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

    def attach(self, bus) -> None:
        super().attach(bus)
        bus.subscribe(PeriscopeSighted, lambda e: setattr(self, "_look_t", e.t))

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
            case "pd":
                return st.depth <= 18 and not self.own.surfaced
            case "upp":
                return self.own.surfaced
        return False

    # --- löpande -----------------------------------------------------------------
    def update(self) -> None:
        if not self.steps or self.i >= len(self.steps) or self.now % CHECK_S:
            return
        if not self._in_area and (a := self._area()) is not None:
            x, y = self.game.own_position_estimate()
            self._in_area = distance(x, y, a.x, a.y) <= AREA_NM
        key = self.steps[self.i]
        if self.now >= self.started_t and self._step_done(key):
            self._finish(key)
            return
        if self.now < self.step_t:
            return
        step = STEPS[key]
        if self._in_fjord():
            return                          # ordern: dykning först utanför mynningen
        if step.area and not self._in_area:
            return                          # navigatören föreslår vägen dit
        data: dict = {}
        order = step.order
        if key == "svep" and self.own.state.ordered_speed > PD_SPEED + 1:
            order = f"fart {PD_SPEED}, periskop"
            data["slow"] = PD_SPEED
        if key == "upp":
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
        self.suggest(f"train_{key}", f"train.suggest.{key}", data, order=order,
                     cooldown=SUGGEST_S)

    def _finish(self, key: str) -> None:
        self.done.append((key, self.now))
        self.i += 1
        self.step_t = self.now + PAUSE_S
        self.started_t = self.now
        sys = self.own.sys
        data = {"step": key, "name": STEPS[key].name, "last": self.i >= len(self.steps),
                "leak": sys.leak_rate > 0, "depth": round(self.own.state.depth)}
        self.say("train.step.done", data, kind="done")
        if self.i >= len(self.steps):
            first = self.done[0][1]
            self.say("train.done", {"steps": [STEPS[k].name for k, _ in self.done],
                                    "minutes": max(1, round((self.now - first) / 60))},
                     extra_delay=5)
            tr = self.game.world.mission.get("training")
            if tr is not None:
                tr["done_t"] = self.now + DONE_DELAY_S


def _step_done_text(d: dict) -> str:
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
    "train.suggest.upp": lambda d: "Kapten, vakthavande. Ytan är fri. Upp till ytläge: vi blåser "
    "barlast, och bryggan bemannas igen.",
    "train.step.done": _step_done_text,
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
}

phrases.register(PHRASES)
phrases.register_ru(RU_PHRASES)

