"""Centralens stora instrument, ritade med brailleprickar (`ui/canvas.py`).

Varje instrument är en `Dial`: skalans form (hel cirkel, övre halva eller högra halva),
skalstreck, siffror, färgade zoner, markeringar (beordrat värde, kavitationsgräns) och
visare. `draw_dial` skalar den till den ruta den får och skriver namn och avläsning på
nedersta raden. Egna instrument; gyrot kan bära en bäringsrepeater (plottets kontakter, översikten).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sim.fmt import kn
from sim.geo import fmt_course

from .canvas import Braille, Canvas, polar

MAX_DEPTH_M = 500.0
MAX_SPEED_KN = 30.0
TEST_DEPTH_M, CRUSH_DEPTH_M = 300.0, 450.0
YELLOW, REDZONE = "#c0a040", "#c04848"
MARKER = "bold #f0c674"
ANSWER = "bold #ffaf5f"
CAVITATION = "bold #ff5f5f"


@dataclass
class Dial:
    kind: str                                   # "full", "top" (övre halva), "right" (högra halva)
    a0: float = 0.0                             # skalans början och slut (kompassvinklar)
    a1: float = 360.0
    ticks: list[tuple[float, bool]] = field(default_factory=list)       # (vinkel, stort)
    labels: list[tuple[float, str]] = field(default_factory=list)
    zones: list[tuple[float, float, str]] = field(default_factory=list)
    markers: list[tuple[float, str, str]] = field(default_factory=list)  # (vinkel, tecken, stil)
    tags: list[tuple[float, str, str]] = field(default_factory=list)     # (vinkel, text, stil) på ringen
    needles: list[tuple[float, float, str, float]] = field(default_factory=list)  # (vinkel, längd, stil, svans)
    title: str = ""
    readout: list[tuple[str, str]] = field(default_factory=list)       # (text, stil)


def _frame(kind: str, w: int, h: int) -> tuple[float, float, float]:
    """Mitt och radie i prickar för en skala i en yta på w × h prickar."""
    if kind == "top":
        r = min(w / 2.0, float(h)) - 1.5
        return w / 2.0 - 0.5, h - 1.5, r
    if kind == "right":
        r = min(w - 2.0, h / 2.0 - 1.5)
        return (w - r) / 2.0, h / 2.0 - 0.5, r
    r = min(w, h) / 2.0 - 1.0
    return w / 2.0 - 0.5, h / 2.0 - 0.5, r


def draw_dial(c: Canvas, top: int, left: int, rows: int, cols: int, d: Dial, p: dict,
              ring_style: str | None = None) -> None:
    """Rita instrumentet i rutan (top, left, rows, cols); nedersta raden är namn och avläsning."""
    if rows < 3 or cols < 6:
        return
    ring = ring_style or p["ring"]
    b = Braille(cols, rows - 1)
    cx, cy, r = _frame(d.kind, b.w, b.h)
    if r < 3:
        return
    b.arc(cx, cy, r, d.a0, d.a1, ring)
    for a0, a1, style in d.zones:
        b.arc(cx, cy, r, a0, a1, style, prio=1)
        b.arc(cx, cy, r - 1, a0, a1, style, prio=1)
    major = max(2.0, r * 0.16)
    for angle, big in d.ticks:
        b.ray(cx, cy, angle, r - (major if big else 1.0), r, ring, prio=1)
    for angle, length, style, tail in d.needles:
        b.ray(cx, cy, angle, -tail * r, length * r, style, prio=3)
    b.blit(c, top, left)

    def cell(rad: float, angle: float) -> tuple[int, int]:
        x, y = polar(cx, cy, rad, angle)
        return top + int(y // 4), left + int(x // 2)

    if r >= 10:
        taken: set[tuple[int, int]] = set()     # en etikett som krockar med en tidigare ritas inte
        for angle, text in d.labels:
            row, col = cell(r - major - 3.5, angle)
            start = col - len(text) // 2
            cells = {(row, x) for x in range(start - 1, start + len(text) + 1)}
            if cells & taken:
                continue
            taken |= cells
            c.centered(row, col, text, p["label"])
    for angle, ch, style in d.markers:
        row, col = cell(r - 1.5, angle)
        c.put(row, col, ch, style)
    for angle, text, style in d.tags:
        row, col = cell(r, angle)
        c.centered(row, col, text, style)
    hub_row, hub_col = top + int(cy // 4), left + int(cx // 2)
    c.put(hub_row, hub_col, "●", p["hub"])

    # namn och avläsning
    line = [(d.title, p["label"])] + ([(" ", "")] if d.readout else []) + d.readout
    total = sum(len(t) for t, _ in line)
    col = left + max(0, (cols - total) // 2)
    for text, style in line:
        c.text(top + rows - 1, col, text, style or p["needle"])
        col += len(text)


# --- skalorna ------------------------------------------------------------------
def depth_angle(d: float) -> float:
    return -135.0 + 270.0 * min(max(d, 0.0), MAX_DEPTH_M) / MAX_DEPTH_M


def speed_angle(v: float) -> float:
    return -120.0 + 240.0 * min(max(v, 0.0), MAX_SPEED_KN) / MAX_SPEED_KN


def rudder_needle(r: float) -> float:
    """Sidrodret ±35° på en övre halvcirkel (±80°)."""
    return max(-35.0, min(35.0, r)) * 80.0 / 35.0


def planes_needle(p: float) -> float:
    """Djuprodren ±25° på en högra halvcirkel: 90 = rodret rakt, ned = större vinkel."""
    return 90.0 + max(-25.0, min(25.0, p)) * 80.0 / 25.0


TELEGRAPH = [("STOPP", 0.0), ("SAKTA", 0.5), ("HALV", 6.0), ("FULL", 12.0)]
TELEGRAPH_ANGLES = [-60.0, -20.0, 20.0, 60.0]
TELEGRAPH_ASTERN_ANGLE = -80.0     # back i maskin
ASTERN_LAMP = "bold #ff8787"       # back: telegrafens lampor och loggens visare


def telegraph_step(speed: float) -> int:
    return max(i for i, (_, v) in enumerate(TELEGRAPH) if speed >= v)


def cavitation_kn(depth: float) -> float:
    return 6.0 + max(depth, 0.0) / 25.0


# --- instrumenten ----------------------------------------------------------------
def gyro(course: float, ordered: float | None, p: dict,
         contacts: list[tuple[str, float, str]] = ()) -> Dial:
    """Gyrot med bäringsrepeatern: contacts är plottets kontakter (märke, bäring, stil), hot
    först; de ritas sist så att hoten hamnar överst."""
    d = Dial("full", title="GYRO")
    d.tags = [(b, tag, style) for tag, b, style in reversed(list(contacts))]
    d.ticks = [(a, a % 30 == 0) for a in range(0, 360, 10)]
    d.labels = [(a, f"{a:03d}") for a in (0, 90, 180, 270)] + \
        [(a, f"{a // 10}") for a in (30, 60, 120, 150, 210, 240, 300, 330)]
    if ordered is not None:
        d.markers.append((ordered, "◆", MARKER))
    d.needles.append((course, 0.82, p["needle"], 0.2))
    d.readout = [(fmt_course(course), "bold")]
    if ordered is not None:
        d.readout.append((f" ▸ {fmt_course(ordered)}", MARKER))
    return d


def depth_gauge(depth: float, ordered: float | None, p: dict) -> Dial:
    d = Dial("full", a0=depth_angle(0), a1=depth_angle(MAX_DEPTH_M), title="DJUP")
    d.ticks = [(depth_angle(m), m % 100 == 0) for m in range(0, int(MAX_DEPTH_M) + 1, 25)]
    d.labels = [(depth_angle(m), f"{m}") for m in range(0, int(MAX_DEPTH_M) + 1, 100)]
    d.zones = [(depth_angle(TEST_DEPTH_M), depth_angle(CRUSH_DEPTH_M), YELLOW),
               (depth_angle(CRUSH_DEPTH_M), depth_angle(MAX_DEPTH_M), REDZONE)]
    if ordered is not None:
        d.markers.append((depth_angle(ordered), "◆", MARKER))
    style = "bold #ff5f5f" if depth >= TEST_DEPTH_M else p["needle"]
    d.needles.append((depth_angle(depth), 0.82, style, 0.12))
    d.readout = [(f"{depth:.0f} m", "bold #ff5f5f" if depth >= TEST_DEPTH_M else "bold")]
    if ordered is not None:
        d.readout.append((f" ▸ {ordered:.0f}", MARKER))
    return d


def speed_gauge(speed: float, ordered: float, depth: float, cavitating: bool, p: dict,
                astern: bool = False, ordered_astern: bool = False) -> Dial:
    """Loggen visar farten genom vattnet; akterut står B (back) i avläsningen och den röda
    zonen börjar vid propellerns kavitationsfart bakåt (halva)."""
    d = Dial("full", a0=speed_angle(0), a1=speed_angle(MAX_SPEED_KN), title="FART")
    d.ticks = [(speed_angle(v), v % 10 == 0) for v in range(0, int(MAX_SPEED_KN) + 1, 2)]
    d.labels = [(speed_angle(v), f"{v}") for v in range(0, int(MAX_SPEED_KN) + 1, 10)]
    cav = cavitation_kn(depth) * (0.5 if ordered_astern else 1.0)
    d.zones = [(speed_angle(cav), speed_angle(MAX_SPEED_KN), REDZONE)]
    other = abs(ordered - speed) >= 0.3 or (astern != ordered_astern and ordered > 0)
    if other:
        d.markers.append((speed_angle(ordered), "◆", MARKER))
    d.needles.append((speed_angle(speed), 0.8, ASTERN_LAMP if astern else p["needle"], 0.12))
    back = "B " if astern and speed > 0 else ""      # B som på telegrafen: back
    d.readout = [(back + f"{speed:.1f}".replace(".", ","), "bold #ff5f5f" if cavitating else "bold")]
    if other:
        d.readout.append((f" ▸ {'B ' if ordered_astern else ''}{kn(ordered)}", MARKER))
    return d


def rudder_gauge(rudder: float, p: dict) -> Dial:
    d = Dial("top", a0=-80, a1=80, title="SIDROR")
    d.ticks = [(rudder_needle(r), r % 35 == 0 or r == 0) for r in (-35, -30, -20, -10, 0,
                                                                     10, 20, 30, 35)]
    d.labels = [(-62, "BB"), (62, "SB"), (0, "0")]
    d.needles.append((rudder_needle(rudder), 0.85, p["needle"], 0.0))
    side = "sb" if rudder > 0.5 else "bb" if rudder < -0.5 else ""
    d.readout = [(f"{abs(rudder):.0f}° {side}".strip(), "bold")]
    return d


def planes_gauge(planes: float, p: dict, pitch: float | None = None) -> Dial:
    """Djuprodret, och under det libellen: lutningen (дифферент) om den är känd, annars rodret."""
    d = Dial("right", a0=10, a1=170, title="DJUPROD")
    d.ticks = [(planes_needle(v), v % 25 == 0 or v == 0) for v in (-25, -20, -10, 0, 10, 20, 25)]
    d.labels = [(30, "upp"), (150, "ned")]
    d.needles.append((planes_needle(planes), 0.85, p["needle"], 0.0))
    word = "ned" if planes > 0.5 else "upp" if planes < -0.5 else ""
    bubble = libell(planes) if pitch is None else libell(pitch, span=PITCH_SPAN_DEG)
    d.readout = [(f"{abs(planes):.0f}° {word}".strip(), "bold"), ("  " + bubble, p["needle"])]
    return d


PITCH_SPAN_DEG = 5.0       # libellens fulla utslag för lutningen


def libell(planes: float, width: int = 7, span: float = 20.0) -> str:
    """Lutningens libell: bubblan går åt fören när vi går ned."""
    pos = width // 2 - round(max(-1.0, min(1.0, planes / span)) * (width // 2))
    return "╞" + "".join("○" if i == pos else "═" for i in range(width)) + "╡"


def telegraph(ordered: float, speed: float, propulsion: str, reactor: str, p: dict,
              astern: bool = False, ordered_astern: bool = False) -> Dial:
    """Maskintelegrafen: framåt i fyra steg, back längst till vänster (handtaget mot B)."""
    d = Dial("top", a0=-80, a1=80, title="TELEGRAF")
    d.ticks = [(a, False) for a in (-80, -40, 0, 40, 80)]
    d.labels = [(a, name) for a, (name, _) in zip(TELEGRAPH_ANGLES, TELEGRAPH)] + \
        [(TELEGRAPH_ASTERN_ANGLE, "B")]
    handle = TELEGRAPH_ASTERN_ANGLE if ordered_astern and ordered > 0 else \
        TELEGRAPH_ANGLES[telegraph_step(ordered)]
    answer = TELEGRAPH_ASTERN_ANGLE if astern and speed > 0 else \
        TELEGRAPH_ANGLES[telegraph_step(speed)]
    d.needles.append((answer, 0.55, ANSWER, 0.0))
    d.needles.append((handle, 0.92, p["needle"], 0.0))
    motor = {"turbine": "turbin", "electric": "smygmotor"}.get(propulsion, propulsion)
    if reactor != "online":
        motor = "batteri"
    d.readout = [(motor, "bold #ffaf00" if reactor != "online" else "bold")]
    if ordered_astern and ordered > 0:
        d.readout.append((" · back", ASTERN_LAMP))
    return d


def clock_face(seconds: int, p: dict) -> Dial:
    d = Dial("full", title="KLOCKA")
    d.ticks = [(a, a % 90 == 0) for a in range(0, 360, 30)]
    d.labels = [(0, "12"), (90, "3"), (180, "6"), (270, "9")]
    h, m, s = (seconds // 3600) % 24, (seconds // 60) % 60, seconds % 60
    d.needles.append(((h % 12) * 30.0 + m * 0.5, 0.5, p["needle"], 0.0))
    d.needles.append((m * 6.0 + s * 0.1, 0.8, p["needle"], 0.0))
    d.needles.append((s * 6.0, 0.85, p["label"], 0.15))
    d.readout = [(f"{h:02d}:{m:02d}", "bold")]
    return d


# --- de mindre instrumenten (helskärmscentralen, när väggen är hög nog) ------------------------
PITCH_MAX_DEG = 10.0       # lutningsmätarens fulla utslag
BILGE_MAX_T = 60.0         # vatten i båten: skalans slut


def pitch_gauge(pitch: float, p: dict) -> Dial:
    """Lutningsmätaren (дифферентометр): ± 10°, förut till höger (+ förlig, nosen ned)."""
    a = lambda deg: max(-1.0, min(1.0, deg / PITCH_MAX_DEG)) * 80.0
    d = Dial("top", a0=-80, a1=80, title="LUTNING")
    d.ticks = [(a(v), v % 5 == 0) for v in range(-10, 11, 2)]
    d.labels = [(-62, "akt"), (62, "för"), (0, "0")]
    d.zones = [(a(-10), a(-6), YELLOW), (a(6), a(10), YELLOW)]
    d.needles.append((a(pitch), 0.85, p["needle"], 0.0))
    word = "förlig" if pitch > 0.3 else "akterlig" if pitch < -0.3 else "rak"
    d.readout = [(f"{abs(pitch):.1f}° {word}".replace(".", ",") if word != "rak" else "rak", "bold")]
    return d


def trim_gauge(load: float, p: dict) -> Dial:
    """Trimmen: hur mycket av djuprodrens förmåga som bär vikten (− lätt, + tung)."""
    a = lambda v: max(-1.0, min(1.0, v)) * 80.0
    d = Dial("top", a0=-80, a1=80, title="TRIM")
    d.ticks = [(a(v / 4), v % 2 == 0) for v in range(-4, 5)]
    d.labels = [(-62, "lätt"), (62, "tung"), (0, "0")]
    d.zones = [(a(-1.0), a(-0.75), REDZONE), (a(0.75), a(1.0), REDZONE)]
    d.needles.append((a(load), 0.85, p["needle"], 0.0))
    word = "tung" if load > 0.05 else "lätt" if load < -0.05 else "i trim"
    d.readout = [(f"{word} {abs(load) * 100:.0f} %" if word != "i trim" else word, "bold")]
    return d


def battery_gauge(level: float, reactor: str, p: dict) -> Dial:
    """Batteriet 0–100 %, rött under 20 %; laddar när reaktorn går."""
    a = lambda v: -80.0 + 160.0 * max(0.0, min(1.0, v))
    d = Dial("top", a0=-80, a1=80, title="BATTERI")
    d.ticks = [(a(v / 10), v % 5 == 0) for v in range(11)]
    d.labels = [(-62, "0"), (62, "100")]
    d.zones = [(a(0.0), a(0.2), REDZONE)]
    low = level < 0.2
    d.needles.append((a(level), 0.85, "bold #ff5f5f" if low else p["needle"], 0.0))
    d.readout = [(f"{level * 100:.0f} %", "bold #ff5f5f" if low else "bold")]
    if reactor != "online":
        d.readout.append((" urladdning", "bold #ffaf00"))
    return d


def bilge_gauge(tons: float, p: dict) -> Dial:
    """Vatten i båten (läns): 0–60 t, gult från 10, rött från 40."""
    a = lambda t: -80.0 + 160.0 * max(0.0, min(1.0, t / BILGE_MAX_T))
    d = Dial("top", a0=-80, a1=80, title="LÄNS")
    d.ticks = [(a(t), t % 20 == 0) for t in range(0, int(BILGE_MAX_T) + 1, 10)]
    d.labels = [(-62, "0"), (62, f"{BILGE_MAX_T:.0f} t")]
    d.zones = [(a(10), a(40), YELLOW), (a(40), a(BILGE_MAX_T), REDZONE)]
    wet = tons >= 0.5
    d.needles.append((a(tons), 0.85, "bold #5fafff" if wet else p["needle"], 0.0))
    d.readout = [(f"{tons:.0f} t" if wet else "torrt", "bold #5fafff" if wet else "bold")]
    return d
