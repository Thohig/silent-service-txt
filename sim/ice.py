"""Packisen: istjocklek och iskölar över operationsområdet (sanning).

Isen är ett rutnät (CELL_NM per ruta) som upprepas periodiskt, så att
området aldrig tar slut. Varje ruta har
  thickness – istjocklek i meter (0 = öppet vatten),
  draft     – hur djupt isens undersida når, i meter (iskölar når djupast).

Isen genereras ur ett seedat frö:
  flerårsis    2–4,5 m, med långsamma variationer,
  iskölar      vallar längs slingrande linjer, 8–25 m djupa, ibland 30–45 m,
  råkar        smala rännor, öppna eller med nyis 0,2–0,8 m,
  polynyor     öppna vakar, 150–450 m tvärs.

Isen driver med transpolardriften (drift_set, drift_kn), oberoende av
vattnets ström. Den flyttar alltså vakar och kölar i förhållande till
ubåten.

Kontakt med isen (ice_contact) anropas av World efter förflyttningen:
  - åt sidan in i en isköl: ubåten stannar och tar skada efter farten,
  - uppåt mot isen: ubåten hålls kvar under den. Tunn is (≤ BREAK_MAX_M)
    kan brytas igenom om ubåten står nästan still och fortsätter uppåt.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import numpy as np

from .geo import NM_IN_M, velocity

if TYPE_CHECKING:
    from .world import World

CELL_NM = 0.05              # 93 m per ruta
OPEN_M = 0.05               # tunnare än så räknas som öppet vatten
BREAK_MAX_M = 1.0           # tjockare is går inte att bryta igenom
BREAK_S = 40                # så länge ubåten måste trycka mot tunn is
BREAK_MAX_SPEED = 2.0       # knop
HULL_TOP_M = 8.0            # skrovets ovansida över kölen
SAIL_TOP_M = 13.0           # tornets ovansida över kölen
HULL_HALF_NM = 50.0 / NM_IN_M   # för- och akterskeppet, från tornet räknat
BUMP_BACKOFF_M = 5.0        # efter stöt mot isen går ubåten ned så här mycket


def _smooth_noise(gen: np.random.Generator, n: int, k: int) -> np.ndarray:
    """Periodiskt värdebrus i [0, 1]: k×k slumpvärden, bilinjärt uppsamplade till n×n."""
    coarse = gen.random((k, k))
    u = np.arange(n) * k / n
    i0 = np.floor(u).astype(int)
    f = u - i0
    i1 = (i0 + 1) % k
    f = f * f * (3 - 2 * f)                       # mjuk övergång
    rows = coarse[i0][:, i0] * (1 - f)[None, :] + coarse[i0][:, i1] * f[None, :]
    rows1 = coarse[i1][:, i0] * (1 - f)[None, :] + coarse[i1][:, i1] * f[None, :]
    return rows * (1 - f)[:, None] + rows1 * f[:, None]


class IceField:
    def __init__(self, rng: random.Random, size_nm: float = 20.0, *,
                 drift_set: float = 200.0, drift_kn: float = 0.25,
                 leads: int = 170, ridges: int = 160, polynyas: int = 28):
        self.n = int(round(size_nm / CELL_NM))
        self.size_nm = self.n * CELL_NM
        self.drift_set = drift_set
        self.drift_kn = drift_kn
        self.ox = 0.0                 # isens förflyttning sedan start, nm
        self.oy = 0.0
        gen = np.random.default_rng(rng.getrandbits(64))
        n = self.n

        thick = 2.0 + 2.0 * _smooth_noise(gen, n, 6) + 0.5 * _smooth_noise(gen, n, 30)
        draft = 0.89 * thick + gen.random((n, n)) * 0.6
        # iskölar
        for _ in range(ridges):
            keel = gen.uniform(8.0, 25.0) if gen.random() > 0.06 else gen.uniform(30.0, 45.0)
            for i, j in self._walk(gen, gen.uniform(0.4, 2.5)):
                d = keel * gen.uniform(0.6, 1.0)
                draft[i, j] = max(draft[i, j], d)
                thick[i, j] = max(thick[i, j], 0.2 * d)
        # råkar: smala rännor, öppna eller med nyis
        for _ in range(leads):
            t = 0.0 if gen.random() < 0.45 else gen.uniform(0.2, 0.8)
            width = int(gen.integers(1, 4))
            for i, j in self._walk(gen, gen.uniform(0.8, 4.0), width=width):
                thick[i, j] = t
                draft[i, j] = 0.89 * t
        # polynyor: öppna vakar
        for _ in range(polynyas):
            ci, cj = gen.integers(0, n, 2)
            r = gen.uniform(0.08, 0.25) / CELL_NM
            t = 0.0 if gen.random() < 0.7 else gen.uniform(0.2, 0.6)
            rr = int(math.ceil(r))
            for di in range(-rr, rr + 1):
                for dj in range(-rr, rr + 1):
                    if di * di + dj * dj <= r * r:
                        thick[(ci + di) % n, (cj + dj) % n] = t
                        draft[(ci + di) % n, (cj + dj) % n] = 0.89 * t
        self.thickness = thick
        self.draft = draft

    def _walk(self, gen: np.random.Generator, length_nm: float, width: int = 1):
        """Rutor längs en slingrande linje. index = (rad = y, kolumn = x)."""
        n = self.n
        x, y = gen.uniform(0, n), gen.uniform(0, n)
        heading = gen.uniform(0, 2 * math.pi)
        for _ in range(int(length_nm / CELL_NM)):
            heading += gen.normal(0, 0.15)
            x += math.sin(heading)
            y += math.cos(heading)
            for w in range(width):
                # bredden läggs vinkelrätt mot riktningen
                wx = x + w * math.cos(heading)
                wy = y - w * math.sin(heading)
                yield int(wy) % n, int(wx) % n

    # --- drift -----------------------------------------------------------------
    def advance(self, dt: float) -> None:
        vx, vy = velocity(self.drift_set, self.drift_kn)
        self.ox += vx * dt
        self.oy += vy * dt

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        n = self.n
        return int(math.floor((y - self.oy) / CELL_NM)) % n, \
            int(math.floor((x - self.ox) / CELL_NM)) % n

    # --- frågor ----------------------------------------------------------------
    def thickness_at(self, x: float, y: float) -> float:
        return float(self.thickness[self._cell(x, y)])

    def draft_at(self, x: float, y: float) -> float:
        return float(self.draft[self._cell(x, y)])

    def is_open(self, x: float, y: float) -> bool:
        return self.thickness_at(x, y) < OPEN_M

    def open_fraction(self) -> float:
        return float(np.mean(self.thickness < OPEN_M))

    def break_through(self, points: list[tuple[float, float]]) -> None:
        """Ubåten har brutit igenom: isen ovanför blir krossad, öppen ränna."""
        for x, y in points:
            c = self._cell(x, y)
            self.thickness[c] = 0.0
            self.draft[c] = 0.0


# --- ubåtens kontakt med isen ----------------------------------------------------
def hull_points(x: float, y: float, course: float) -> list[tuple[float, float, float]]:
    """(x, y, höjd över kölen) för torn, förskepp och akterskepp."""
    dx, dy = math.sin(math.radians(course)) * HULL_HALF_NM, \
        math.cos(math.radians(course)) * HULL_HALF_NM
    return [(x, y, SAIL_TOP_M), (x + dx, y + dy, HULL_TOP_M), (x - dx, y - dy, HULL_TOP_M)]


def _iced_points(ice: IceField, x: float, y: float, course: float):
    """Skrovpunkter med is ovanför: (höjd över kölen, isens djup). Öppet vatten hindrar inget."""
    return [(top, ice.draft_at(px, py)) for px, py, top in hull_points(x, y, course)
            if not ice.is_open(px, py)]


def clearance(ice: IceField, x: float, y: float, course: float, depth: float) -> float:
    """Minsta frigång (m) mellan ubåtens ovansida och isens undersida. < 0 = kontakt."""
    return min((depth - top - draft for top, draft in _iced_points(ice, x, y, course)),
               default=math.inf)


def ceiling(ice: IceField, x: float, y: float, course: float) -> float:
    """Grundaste djup ubåten kan ha här utan att röra isen (0 = ytläge möjligt)."""
    return max((top + draft for top, draft in _iced_points(ice, x, y, course)), default=0.0)


def ice_contact(world: World, prev: tuple[float, float, float], dt: int = 1) -> None:
    ice = world.env.ice
    own = world.own
    if ice is None or own.sunk:
        return
    st, sys = own.state, own.sys
    px, py, pdepth = prev
    if clearance(ice, st.x, st.y, st.course, st.depth) >= 0:
        sys.ice_press = 0
        sys.ice_contact = False
        return

    sideways = clearance(ice, st.x, st.y, st.course, pdepth) < 0 and \
        clearance(ice, px, py, st.course, pdepth) >= 0
    if sideways:
        # rakt in i en isköl
        speed = st.speed
        st.x, st.y, st.depth = px, py, pdepth
        st.speed = 0.0
        st.ordered_speed = 0.0
        if speed > 1.5:
            sys.hull -= 0.012 * speed
            hit = ["sonar"] if speed < 6 else ["sonar", world.rng.choice(["periscope", "planes"])]
            for c in hit:
                sys.health[c] = max(0.0, sys.health[c] - 0.06 * speed)
            leak = speed > 6
            if leak:
                sys.leak_rate += 0.05 * speed
            own.alert("ice.collision", severity="svår" if speed > 6 else "lätt",
                      components=hit, leak=leak)
        else:
            own.alert("ice.touch")
        return

    # uppåt mot isen: hålls kvar under den
    top = ceiling(ice, st.x, st.y, st.course)
    st.depth = top
    points = hull_points(st.x, st.y, st.course)
    thickest = max(ice.thickness_at(x, y) for x, y, _ in points)
    wants_up = st.ordered_depth < st.depth - 0.5 or sys.blowing
    if sys.blowing and not sys.ice_contact:
        sys.hull -= 0.05
        sys.health["periscope"] = max(0.0, sys.health["periscope"] - 0.5)
        own.alert("ice.collision", severity="svår", components=["periscope"], leak=False)
    if wants_up and thickest <= BREAK_MAX_M and st.speed <= BREAK_MAX_SPEED:
        if not sys.ice_contact:
            own.alert("ice.pressing", thin=True)
        sys.ice_contact = True
        sys.ice_press += dt
        if sys.ice_press >= BREAK_S:
            ice.break_through([(x, y) for x, y, _ in points])
            sys.ice_press = 0
            sys.ice_contact = False
            if thickest > 0.6 and world.rng.random() < 0.5:
                sys.health["periscope"] = max(0.0, sys.health["periscope"] - 0.3)
                own.alert("ice.broke_through", damaged=["periscope"])
            else:
                own.alert("ice.broke_through", damaged=[])
        return
    if not sys.ice_contact:
        own.alert("ice.bump", thin=thickest <= BREAK_MAX_M, too_fast=st.speed > BREAK_MAX_SPEED,
                  back_to=round(st.depth + BUMP_BACKOFF_M))
    sys.ice_contact = True
    sys.ice_press = 0
    if not sys.blowing:
        # trimmen tar oss några meter ned från isen igen
        st.ordered_depth = st.depth + BUMP_BACKOFF_M


def masts_clear(world: World) -> bool:
    """Kan periskop, antenn och radar komma upp i fria luften här?"""
    ice = world.env.ice
    if ice is None:
        return True
    s = world.own.state
    return ice.is_open(s.x, s.y)
