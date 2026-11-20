"""Krigsskådeplatsen (sanning): krigspatrullens uppgifter och fiendens svar på det vi gör.

Krigspatrullen (`scenario/krig.py`) har ingen fast plan. Krigsskådeplatsen är en spawner
(`World.spawners`) som lägger ut det staben skickar oss mot och skriver stabens telegram om det:

- **Uppgifterna** (`TASK_KINDS`): `anfall` (en konvoj med eskort: sänk minst ett fartyg),
  `spaning` (en landstigningsstyrka: rapportera kurs och fart) och `foto` (fartyg till ankars med en
  vaktjagare: fotografera ankarplatsen). En uppgift i taget. När den är avgjord läggs nästa ut strax
  före nästa sambandstillfälle, där staben sänder den. Telegrammet skrivs när radion tar emot det:
  läget med stabens fel (`SIGMA_NM`), kurs och fart avrundade. Missar vi tillfället sänds det igen
  med nytt läge vid nästa.
- **Avgörandet** läser sanningen: sänkta fartyg, rapporterna (`mission["report_truth"]`) och fotona
  (`mission["photos"]`). Det som hände skrivs i `mission["war_tasks"]` för slutrapporten
  (`task_summary`). Staben (`headquarters.py`) vet fortfarande bara det vi sänt.
- **Hemkallelsen**: efter `max_tasks` uppgifter, när torpederna nästan är slut, skrovet skadat eller
  tiden `recall_after_s` gått sänder staben ÅTERVÄND (`tasks` = ut, flaggan `recalled`): då gäller
  utvägen (`EscapeGoal(requires_flag="recalled")`, `Scenario.escape_task`).
- **Följderna** (`TheatreDef.hunt`): pejlar nätet vår sändning (samma regel som jagarnas,
  `enemy.df_probability`) skickas en jaktgrupp med två jagare och flyget dit; sänker vi ett fartyg
  kommer flyget till platsen. Inget av det är slumpade kriser: det är fiendens svar på det vi gjort.

Uppgiftsfartygen som passerat och ligger långt bort tas bort ur världen, så att spelet inte växer.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .convoy import ConvoyDef, ConvoyShip, make_convoy, make_escorts
from .enemy import Datum, DestroyerAI, df_probability, df_sigma
from .entities import Vessel
from .geo import bearing_to, distance
from .radiogram import RadioMessage
from .reports import Quality
from .ship import ShipState

if TYPE_CHECKING:
    from .air import AirPatrol
    from .world import World

TASK_KINDS = ("anfall", "spaning", "foto")
TASK_ORDER = {"anfall": ("anfall",), "spaning": ("rapport",), "foto": ("foto",)}
TASK_NAME = {"anfall": "konvoj", "spaning": "styrkan", "foto": "ankarplatsen"}
SIGMA_NM = {"anfall": 2.0, "spaning": 2.5, "foto": 0.8}   # stabens fel i läget (1σ)
STEP_S = 10                 # avgörandet och följderna prövas så här ofta
PREP_S = 5 * 60             # nästa uppgift läggs ut så långt före sambandstillfället
CLEAR_S = 10 * 60           # anfallet avgjort så länge efter sista sänkningen, om ingen har oss
TASK_MAX_S = 5 * 3600       # en uppgift som inte avgjorts på så här lång tid är missad
FOTO_MAX_S = 6 * 3600
REMOVE_NM = 15.0            # avgjorda uppgiftsfartyg så här långt bort tas bort
TORPEDO_RESERVE = 4         # så få konventionella torpeder kvar: staben kallar hem oss
HULL_RECALL = 0.5           # skrovet så skadat: staben kallar hem oss
HUNT_GAP_S = 60 * 60        # högst en ny jaktgrupp per timme
HUNT_LIFE_S = 3 * 3600      # så länge jaktgruppen söker innan den går hem
HUNT_FAR_NM = (18.0, 22.0)  # där jaktgruppen kommer ifrån (från pejlfixet)
HUNT_BOX_NM = 5.0           # jaktgruppens sökruta kring fixet (halva sidan)
HUNT_LEASH_NM = 4.0         # jaktgruppen släpper ett datum så långt utanför sin ruta
AIR_DELAY_S = (15 * 60, 30 * 60)    # flyget kommer så här långt efter en pejling eller sänkning
AIR_SINK_SIGMA_NM = 2.0
TONNAGE = {"transport": 12000, "tanker": 16000, "merchant": 7000, "destroyer": 2400,
           "moored": 9000}


def _compass(b: float) -> str:
    return ["NORR", "NORDOST", "ÖSTER", "SYDOST", "SÖDER", "SYDVÄST", "VÄSTER", "NORDVÄST"][
        int(((b % 360) + 22.5) // 45) % 8]


@dataclass(frozen=True)
class TheatreDef:
    """Krigspatrullens regler (kalibreringen står i `docs/system/scenarier.md`)."""
    kinds: tuple[str, ...] = ("foto", "spaning", "anfall")   # i tur och ordning efter den första
    max_tasks: int = 3
    recall_after_s: int = 10 * 3600     # senast då kallar staben hem oss
    far_nm: tuple[float, float] = (12.0, 16.0)      # konvojen och styrkan: så långt bort från oss
    side_nm: tuple[float, float] = (1.5, 5.0)       # och så långt vid sidan av vår position
    foto_nm: tuple[float, float] = (6.0, 9.0)       # ankarplatsen: så långt bort
    course: tuple[float, float] = (170.0, 280.0)    # konvojens och styrkans baskurs (mot Kuba)
    passed_nm: float = 10.0             # en konvoj som passerat och ligger så långt bort är missad
    torpedoes: int = 16                 # konventionella torpeder ombord från start
    hunt: bool = True                   # följderna: jaktgrupp efter pejling, flyg efter sänkning


@dataclass
class Task:
    n: int
    kind: str
    name: str                   # positionens namn (kunskapen, `kurs mot …`)
    t_spawn: int
    targets: list[Vessel]       # det uppgiften gäller (konvojens fartyg, styrkan, ankarplatsen)
    vessels: list[Vessel]       # allt uppgiften lagt ut (med eskort och vakt)
    ais: list[Any]
    spawners: list[Any]
    told_t: int | None = None   # när radion tog emot uppgiften
    result: str | None = None   # sänkt, rapporterad, fotograferad, missad, inställd
    t_done: int | None = None
    removed: bool = False

    def moving(self) -> tuple[float, float] | None:
        """Kurs och fart för målens mitt (None: till ankars)."""
        alive = [v for v in self.targets if not v.sunk]
        if not alive or self.kind == "foto":
            return None
        return alive[0].state.course, alive[0].state.speed


@dataclass
class HunterGroup:
    vessels: list[Vessel]
    ais: list[DestroyerAI]
    until: int
    leaving: bool = False


@dataclass
class Theatre:
    tdef: TheatreDef
    rng: random.Random
    area: float
    area_name: str
    start_clock: int
    windows: list[int]
    air: AirPatrol | None = None
    tasks: list[Task] = field(default_factory=list)
    queue: list[Any] = field(default_factory=list)     # Task eller "recall": sänds vid nästa tillfälle
    recall_queued: bool = False
    next_kind: int = 0
    next_at: int | None = None          # då läggs nästa uppgift ut
    hunters: list[HunterGroup] = field(default_factory=list)
    last_hunt_t: int = -10**9
    air_cue: tuple[int, float, float, float] | None = None   # (från tid, x, y, sigma) till flyget
    _seen_hf: set = field(default_factory=set)
    _sunk_seen: set = field(default_factory=set)
    _hunter_n: int = 0

    # ------------------------------------------------------------------ uppgifterna
    @property
    def current(self) -> Task | None:
        return next((t for t in self.tasks if t.result is None), None)

    def start(self, world: World, kind: str) -> Task:
        """Lägg ut en uppgift nu (sanning) och ställ dess telegram i kö."""
        n = len(self.tasks) + 1
        name = f"{TASK_NAME[kind]} {n}"
        o = world.own.state
        rng = random.Random(self.rng.random())
        if kind == "foto":
            task = self._anchorage(world, n, name, rng, o.x, o.y)
        else:
            task = self._convoy(world, n, name, kind, rng, o.x, o.y)
        self.tasks.append(task)
        self.queue.append(task)
        return task

    def _convoy(self, world: World, n: int, name: str, kind: str, rng: random.Random,
                ox: float, oy: float) -> Task:
        # på väg mot Kuba (sydväst) men inte alltid: från ett håll som passerar oss vid sidan
        base = rng.uniform(*self.tdef.course)
        ux, uy = math.sin(math.radians(base)), math.cos(math.radians(base))
        nx, ny = uy, -ux
        side = rng.choice((-1.0, 1.0)) * rng.uniform(*self.tdef.side_nm)
        run_in = rng.uniform(*self.tdef.far_nm)
        cx, cy = ox + side * nx - run_in * ux, oy + side * ny - run_in * uy
        if kind == "anfall":
            ships = (ConvoyShip("transport", -1, 0), ConvoyShip("tanker", 1, 0),
                     ConvoyShip("transport", 0, 1), ConvoyShip("transport", 0, 2))
            speed = rng.uniform(10.0, 12.0)
        else:           # landstigningsstyrkan: färre, snabbare fartyg
            ships = (ConvoyShip("transport", -1, 0), ConvoyShip("transport", 1, 0))
            speed = rng.uniform(13.0, 15.0)
        before = (len(world.contacts), len(world.ais), len(world.spawners))
        convoy = make_convoy(world, ConvoyDef(start=(cx, cy), base_course=base, speed=speed,
                                              ships=ships), rng, prefix=f"U{n}K")
        make_escorts(world, convoy, rng, prefix=f"U{n}E")
        return Task(n, kind, name, world.time, list(convoy.vessels),
                    world.contacts[before[0]:], world.ais[before[1]:],
                    world.spawners[before[2]:])

    def _anchorage(self, world: World, n: int, name: str, rng: random.Random,
                   ox: float, oy: float) -> Task:
        r = rng.uniform(*self.tdef.foto_nm)
        m = 3.0
        for _ in range(20):                 # helst i kvadraten
            b = rng.uniform(0.0, 360.0)
            ax, ay = ox + r * math.sin(math.radians(b)), oy + r * math.cos(math.radians(b))
            if m <= ax <= self.area - m and m <= ay <= self.area - m:
                break
        targets = []
        for i in range(3):
            v = Vessel(f"U{n}A{i + 1}", "moored",
                       ShipState(x=ax + rng.uniform(-0.3, 0.3), y=ay + rng.uniform(-0.3, 0.3),
                                 course=rng.uniform(0, 360), speed=0.0), side="enemy")
            targets.append(v)
            world.contacts.append(v)
        g = Vessel(f"U{n}G1", "destroyer",
                   ShipState(x=ax + 1.5, y=ay, course=0.0, speed=10.0, turn_rate=2.0, accel=0.3,
                             max_speed=32), side="enemy", has_radar=True)
        h = 2.5
        guard = DestroyerAI(g, random.Random(rng.random()), area=self.area, patrol_speed=10.0,
                            leash_nm=4.0, box=(ax - h, ay - h, ax + h, ay + h))
        guard.roe = "lethal"
        guard.quiet_patrol = True           # vid ankarplatsen lyssnar den; pingar först när den söker
        world.contacts.append(g)
        world.ais.append(guard)
        return Task(n, "foto", name, world.time, targets, targets + [g], [guard], [])

    # ------------------------------------------------------------------ telegrammen
    def _clock(self, t: int) -> str:
        c = (self.start_clock + t) % 86400
        return f"{c // 3600:02d}.{c % 3600 // 60:02d}"

    def _message(self, world: World, item: Any) -> RadioMessage | None:
        if item == "recall":
            return RadioMessage(
                f"FRÅN HUVUDSTABEN. PATRULLEN ÄR SLUT. LÄMNA {self.area_name.upper()} I "
                "UNDERVATTENSLÄGE OCH ÅTERVÄND TILL BASEN. RAPPORTERA INTE FÖRRÄN NI ÄR UTE.",
                {"tasks": ("ut",), "recalled": True})
        task: Task = item
        alive = [v for v in task.targets if not v.sunk]
        if task.result is not None or not alive:
            return None
        rng = random.Random(f"{task.n}:{world.time}")    # samma telegram vid samma tid
        sig = SIGMA_NM[task.kind]
        mx = sum(v.state.x for v in alive) / len(alive) + rng.gauss(0, sig)
        my = sum(v.state.y for v in alive) / len(alive) + rng.gauss(0, sig)
        o = world.own.state
        dist, where = distance(o.x, o.y, mx, my), _compass(bearing_to(o.x, o.y, mx, my))
        head = f"FRÅN HUVUDSTABEN. UPPGIFT {task.n}. "
        at = f"KL {self._clock(world.time)} CIRKA {round(dist)} SJÖMIL {where} OM ER"
        wp = (task.name, mx, my, sig, world.time)
        if task.kind == "foto":
            return RadioMessage(
                head + f"FIENTLIGA FARTYG TILL ANKARS {at}, BEVAKADE AV EN JAGARE. "
                "FOTOGRAFERA ANKARPLATSEN GENOM PERISKOPET, HELST I DAGSLJUS. "
                "FARTYGEN FÅR ANGRIPAS.", {"tasks": TASK_ORDER["foto"]}, wp)
        course, speed = task.moving() or (0.0, 0.0)
        c10 = int(round(course / 10.0) * 10) % 360
        v1 = int(round(speed))
        motion = (float(c10), float(v1))
        if task.kind == "anfall":
            return RadioMessage(
                head + f"KONVOJ MED TRUPPTRANSPORTER OCH TANKER UNDER ESKORT {at}, KURS CIRKA "
                f"{c10:03d}, FART {v1} KNOP. DEN SICKSACKAR. ANFALL KONVOJEN. SÄNK MINST ETT "
                "FARTYG OCH BRYT SEDAN KONTAKTEN.", {"tasks": TASK_ORDER["anfall"]}, wp, motion)
        return RadioMessage(
            head + f"LANDSTIGNINGSSTYRKA UNDER ESKORT {at}, KURS CIRKA {c10:03d}, FART {v1} KNOP. "
            "SÖK UPP DEN OCH RAPPORTERA DESS KURS OCH FART. ANFALL FÅR SKE FÖRST NÄR "
            "RAPPORTEN ÄR SÄND.", {"tasks": TASK_ORDER["spaning"], "report_requested": True},
            wp, motion)

    def pending(self, world: World) -> list[RadioMessage]:
        """Det staben skulle sända nu (radion frågar om det finns något, t.ex. när det stympas)."""
        out = [m for item in self.queue if (m := self._message(world, item)) is not None]
        return out

    def deliver(self, world: World) -> list[RadioMessage]:
        """Radion har tagit emot: stabens telegram nu, och kön töms."""
        out = []
        for item in self.queue:
            m = self._message(world, item)
            if m is None:
                continue
            out.append(m)
            if isinstance(item, Task):
                item.told_t = world.time
            elif item == "recall":
                for t in self.tasks:            # det som pågick ställs in
                    if t.result is None:
                        self._resolve(world, t, "inställd")
        self.queue = []
        return out

    # ------------------------------------------------------------------ steget
    def step(self, world: World) -> None:
        now = world.time
        if self.tdef.hunt:
            self._hunt_consequences(world)
        if now % STEP_S:
            return
        task = self.current
        if task is not None:
            self._judge(world, task)
        self._sinkings(world)
        self._cleanup(world)
        if self.recall_queued:
            return
        if self._recall_due(world):
            self.recall_queued = True
            self.queue = [i for i in self.queue if not isinstance(i, Task) or i.told_t is not None]
            self.queue.append("recall")
            return
        if self.current is None:
            if self.next_at is None:
                self.next_at = self._next_slot(now)
            if self.next_at is not None and now >= self.next_at:
                self.next_at = None
                kinds = self.tdef.kinds
                self.start(world, kinds[self.next_kind % len(kinds)])
                self.next_kind += 1

    def _next_slot(self, now: int) -> int | None:
        """Strax före nästa sambandstillfälle som inte börjat (då sänder staben uppgiften)."""
        nxt = next((w for w in self.windows if w > now + 60), None)
        return None if nxt is None else max(now, nxt - PREP_S)

    def _recall_due(self, world: World) -> bool:
        done = sum(1 for t in self.tasks if t.result is not None)
        fired = world.mission.get("torpedoes_fired", 0)
        return (done >= self.tdef.max_tasks
                or self.tdef.torpedoes - fired <= TORPEDO_RESERVE
                or world.own.sys.hull < HULL_RECALL
                or world.time >= self.tdef.recall_after_s)

    def _judge(self, world: World, task: Task) -> None:
        now = world.time
        o = world.own.state
        sunk = [v for v in task.targets if v.sunk]
        alive = [v for v in task.targets if not v.sunk]
        hunted = any(world._hunting_us(ai) for ai in task.ais if isinstance(ai, DestroyerAI))
        if task.kind == "spaning" and task.told_t is not None:
            ids = {v.id for v in task.vessels}      # styrkan med sin eskort
            if any(c.get("id") in ids for r in world.mission.get("report_truth", [])
                   if r["t"] >= task.told_t for c in r["contacts"]):
                self._resolve(world, task, "rapporterad")
                return
        if task.kind == "foto" and task.told_t is not None:
            if any(t >= task.told_t and q >= int(Quality.OSAKER)
                   for t, q in world.mission.get("photos", [])):
                self._resolve(world, task, "fotograferad")
                return
        if sunk and (not alive or now - world.mission.get("last_sink_t", 0) >= CLEAR_S
                     and not hunted):
            if task.kind != "spaning" or not alive:
                self._resolve(world, task, "sänkt")
                return
        if task.kind != "foto" and alive and all(
                distance(o.x, o.y, v.state.x, v.state.y) > self.tdef.passed_nm
                and (o.x - v.state.x) * math.sin(math.radians(v.state.course))
                + (o.y - v.state.y) * math.cos(math.radians(v.state.course)) < 0
                for v in alive):
            self._resolve(world, task, "sänkt" if sunk else "missad")
            return
        limit = FOTO_MAX_S if task.kind == "foto" else TASK_MAX_S
        if now - task.t_spawn >= limit:
            self._resolve(world, task, "sänkt" if sunk else "missad")

    def _resolve(self, world: World, task: Task, result: str) -> None:
        task.result, task.t_done = result, world.time
        sunk = [v for v in task.targets if v.sunk]
        world.mission.setdefault("war_tasks", []).append({
            "n": task.n, "kind": task.kind, "name": task.name,
            "given": self._clock(task.told_t) if task.told_t is not None else None,
            "done": self._clock(world.time), "result": result,
            "sunk": len(sunk), "tons": sum(TONNAGE.get(v.kind, 5000) for v in sunk)})
        if task in self.queue:
            self.queue.remove(task)

    def _sinkings(self, world: World) -> None:
        """Sänkta fiendefartyg (alla, även jagare): tonnaget och flyget till platsen."""
        for v in world.contacts:
            if v.sunk and v.side == "enemy" and v.is_ship and v.id not in self._sunk_seen:
                self._sunk_seen.add(v.id)
                world.mission.setdefault("war_sunk", []).append(
                    {"kind": v.kind, "tons": TONNAGE.get(v.kind, 5000), "t": world.time})
                if self.tdef.hunt:
                    self._cue_air(world, v.state.x, v.state.y, AIR_SINK_SIGMA_NM)

    def _cleanup(self, world: World) -> None:
        """Avgjorda uppgifter långt bort och jaktgrupper som gått hem tas bort ur världen."""
        o = world.own.state
        for t in self.tasks:
            if t.result is None or t.removed:
                continue
            if any(not v.sunk and distance(o.x, o.y, v.state.x, v.state.y) < REMOVE_NM
                   for v in t.vessels) or any(world._hunting_us(ai) for ai in t.ais
                                              if isinstance(ai, DestroyerAI)):
                continue
            t.removed = True
            self._remove(world, t.vessels, t.ais, t.spawners)
        for g in list(self.hunters):
            if not g.leaving and world.time >= g.until and \
                    not any(world._hunting_us(ai) for ai in g.ais):
                g.leaving = True
                far = self.area + 30.0
                for ai in g.ais:
                    ai.box = (far, far, far + 1, far + 1)
                    ai.datum, ai.state = None, "patrol"
            if g.leaving and all(v.sunk or distance(o.x, o.y, v.state.x, v.state.y) > REMOVE_NM
                                 for v in g.vessels):
                self.hunters.remove(g)
                self._remove(world, g.vessels, g.ais, [])

    @staticmethod
    def _remove(world: World, vessels: list, ais: list, spawners: list) -> None:
        for v in vessels:
            if v in world.contacts:
                world.contacts.remove(v)
        for ai in ais:
            if ai in world.ais:
                world.ais.remove(ai)
        for sp in spawners:
            if sp in world.spawners:
                world.spawners.remove(sp)

    # ------------------------------------------------------------------ följderna
    def _hunt_consequences(self, world: World) -> None:
        now = world.time
        for em in world.emissions:
            if em.kind != "hf" or em.source_id != world.own.id or (em.t, em.x) in self._seen_hf:
                continue
            self._seen_hf.add((em.t, em.x))
            if self.rng.random() >= df_probability(em.duration):
                continue
            sigma = df_sigma(em.duration)
            fx, fy = em.x + self.rng.gauss(0, sigma), em.y + self.rng.gauss(0, sigma)
            world.mission["war_df"] = world.mission.get("war_df", 0) + 1
            self._cue_air(world, fx, fy, sigma + 0.5)
            if now - self.last_hunt_t >= HUNT_GAP_S and not any(not g.leaving for g in self.hunters):
                self.last_hunt_t = now
                self._send_hunters(world, fx, fy, sigma)
        if self.air_cue is not None and self.air is not None:
            t0, x, y, sigma = self.air_cue
            cur = self.air.current
            if cur is None and self.air.next_t > t0:
                self.air.next_t = t0             # flyget startar tidigare
            elif cur is not None and now >= t0 and not cur.vessel.gone and cur.state != "leave":
                if cur.datum is None or cur.datum.sigma > sigma or now - cur.datum.t > 600:
                    cur.datum = Datum(x, y, 50.0, sigma, now)
                self.air_cue = None

    def _cue_air(self, world: World, x: float, y: float, sigma: float) -> None:
        if self.air is None:
            return
        t0 = world.time + self.rng.randint(*AIR_DELAY_S)
        if self.air_cue is None or t0 < self.air_cue[0]:
            self.air_cue = (t0, x, y, sigma)

    def _send_hunters(self, world: World, fx: float, fy: float, sigma: float) -> None:
        """En jaktgrupp med två jagare går mot pejlfixet och söker i en ruta kring det."""
        self._hunter_n += 1
        k = self._hunter_n
        b = self.rng.uniform(0.0, 360.0)
        r = self.rng.uniform(*HUNT_FAR_NM)
        sx, sy = fx + r * math.sin(math.radians(b)), fy + r * math.cos(math.radians(b))
        c = bearing_to(sx, sy, fx, fy)
        h = HUNT_BOX_NM
        vessels, ais = [], []
        for i in range(2):
            off = (i - 0.5) * 1.5
            v = Vessel(f"J{k}{i + 1}", "destroyer",
                       ShipState(x=sx + off * math.cos(math.radians(c)),
                                 y=sy - off * math.sin(math.radians(c)), course=c, speed=20.0,
                                 turn_rate=2.0, accel=0.3, max_speed=32),
                       side="enemy", has_radar=True)
            ai = DestroyerAI(v, random.Random(self.rng.random()), area=self.area,
                             patrol_speed=15.0, box=(fx - h, fy - h, fx + h, fy + h),
                             leash_nm=HUNT_LEASH_NM)
            ai.roe = "lethal"
            ai.start_hunt(fx, fy, 50.0, sigma + 1.0, t=world.time)
            vessels.append(v)
            ais.append(ai)
            world.contacts.append(v)
            world.ais.append(ai)
        for ai in ais:
            ai.partners = [p for p in ais if p is not ai]
        self.hunters.append(HunterGroup(vessels, ais, world.time + HUNT_LIFE_S))


def task_summary(world: World) -> dict | None:
    """Krigspatrullen i slutrapporten (sanning): uppgifterna och det sänkta tonnaget."""
    tasks = world.mission.get("war_tasks")
    if tasks is None and "war_sunk" not in world.mission:
        return None
    sunk = world.mission.get("war_sunk", [])
    return {"tasks": list(tasks or []), "sunk": len(sunk), "tons": sum(s["tons"] for s in sunk),
            "df": world.mission.get("war_df", 0)}
