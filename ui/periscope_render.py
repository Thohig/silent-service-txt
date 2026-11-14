"""Rastrering av periskopbilden till tecken (rich, testbart utan Textual).

Bilden är utkikens senaste svep (`Knowledge.periscope`), aldrig världen.

Överst en 360°-remsa med fören i mitten: beteckningar, horisonten med
föremålen och en bäringsskala. Okularets synfält (FOV_DEG) markeras med
klamrar. Under remsan okularet: ett runt synfält riktat mot det valda
föremålet, med sikte (┊), horisont och siluetter. Siluetterna väljs efter
fartygstyp och avstånd, vänds efter vinkeln på bogen (styrbordssidan mot oss:
fören åt höger), trycks ihop när fartyget går mot eller från oss och skärs
underifrån efter hur mycket som syns över horisonten. På natten syns bara
lanternorna. Sist en rad med det utkiken bedömde om det valda föremålet.
"""
from __future__ import annotations

import math

from rich.text import Text

from sim.fmt import fmt_course, kn, nm
from sim.geo import angle_diff, norm360
from sim.ice import ICE_LOOK_NM
from sim.periscope import SECTOR_HALF_DEG, IceBearing, PeriscopePicture, SightedObject, in_sector

FOV_DEG = 32.0              # okularets synfält i låg förstoring
STALE_S = 60                # äldre bild än så ritas nedtonad
STRIP_ROWS = 3
MIN_EYE_ROWS = 7

STYLE = {
    "sky_day": "#a8c0c8",
    "sky_night": "#3a4a58",
    "sea_day": "#4f7f9f",
    "sea_night": "#24384a",
    "tube": "#1a2420",
    "reticle": "#7f9a80",
    "ship": "bold #d8dccc",
    "ship_other": "#9aa49a",
    "ship_old": "#5f6a60",
    "light_white": "bold white",
    "light_red": "bold red",
    "light_green": "bold green",
    "aircraft": "bold #e0d090",
    "station": "bold #ffd75f",
    "net": "#d7af5f",
    "ice": "#c8d8e0",
    "ice_night": "#6a7a88",
    "ridge": "bold #e8f0f8",
    "label": "#c8d0b0",
    "selected": "bold reverse",
    "dim": "#4f6358",
}

# --- siluetter ------------------------------------------------------------------
# Rader uppifrån; första tecknet anger del: m mast, s överbyggnad, h skrov.
# Fören åt höger. Sista raden ligger på horisonten.
ART: dict[str, dict[str, list[str]]] = {
    "destroyer": {
        "L": ["m             |       |          ",
              "m            _|_    __|__        ",
              "s       ____|___|__|_____|___    ",
              "s   ___|_____________________|__ ",
              "h   \\__________________________/ "],
        "S": ["m    |   |    ",
              "s __|_|_|_|__ ",
              "h \\_________/ "],
    },
    "merchant": {
        "L": ["m   |                    |         ",
              "m   |      ||            |         ",
              "s   |   ___||___       __|_        ",
              "s __|__|________|_____|____|____   ",
              "h \\_____________________________/  "],
        "S": ["m  |   |  |   ",
              "s _|_|_|__|_  ",
              "h \\_________/ "],
    },
    "patrol": {
        "L": ["m        |         ",
              "s     __|_|__      ",
              "h \\___________/    "],
        "S": ["m   |    ",
              "h \\_|_/  "],
    },
}
ART["moored"] = ART["merchant"]
AIRCRAFT_ART = ["   _|_   ", "--=(o)=--"]
MIRROR = str.maketrans("/\\()[]<>", "\\/)(][><")


def mirror(lines: list[str]) -> list[str]:
    return [ln[0] + ln[1:][::-1].translate(MIRROR) for ln in lines]


def compress(lines: list[str], factor: float) -> list[str]:
    """Tryck ihop vågrätt (fartyget går mot eller från oss); behåll master och kanter."""
    w = len(lines[0]) - 1
    n = max(3, round(w * factor))
    if n >= w:
        return lines
    out = []
    for ln in lines:
        body = ln[1:]
        cols = []
        for j in range(n):
            a, b = int(j * w / n), max(int(j * w / n) + 1, int((j + 1) * w / n))
            chunk = body[a:b]
            pick = next((c for c in "|_\\/" if c in chunk), None)
            cols.append(pick or next((c for c in chunk if c != " "), " "))
        out.append(ln[0] + "".join(cols))
    return out


def silhouette(obj: SightedObject, large: bool) -> list[str]:
    """Siluettens rader (utan deltecken), skurna efter synlig del, vända och ihoptryckta."""
    art = ART.get(obj.kind)
    if art is None:
        return []
    lines = list(art["L" if large and "L" in art else "S"])
    if obj.aob is not None:
        if obj.aob < 0:
            lines = mirror(lines)
        lines = compress(lines, max(0.3, abs(math.sin(math.radians(obj.aob)))))
    keep = {"helt": "mhs", "överbyggnad": "ms", "mastoppar": "m"}.get(obj.visible, "mhs")
    lines = [ln for ln in lines if ln[0] in keep]
    return [ln[1:].rstrip() for ln in lines]


def _is_large(obj: SightedObject) -> bool:
    return obj.range_nm < 2.5


def aob_text(aob: float) -> str:
    a = abs(aob)
    if a < 5:
        return "rakt förut"
    if a > 175:
        return "rakt akterut"
    return f"{'styrbord' if aob > 0 else 'babord'} {a:.0f}°"


# --- val av föremål ----------------------------------------------------------------
def ordered_objects(pic: PeriscopePicture) -> list[SightedObject]:
    """Föremålen från vänster till höger sett från fören."""
    return sorted(pic.objects, key=lambda o: angle_diff(o.bearing, pic.own_course))


def default_index(pic: PeriscopePicture) -> int:
    objs = ordered_objects(pic)
    if not objs:
        return 0
    fresh = [i for i, o in enumerate(objs) if not _old(o, pic)] or list(range(len(objs)))
    ships = [i for i in fresh if objs[i].designation is not None]
    cand = ships or fresh
    return min(cand, key=lambda i: objs[i].range_nm)


def object_key(o: SightedObject) -> str:
    return o.designation or f"{o.kind}@{o.bearing:.0f}"


# --- rutnät -------------------------------------------------------------------------
class _Grid:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.cells: list[list[tuple[str, str]]] = [[(" ", "")] * w for _ in range(h)]

    def put(self, x: int, y: int, ch: str, style: str = "") -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.cells[y][x] = (ch, style)

    def text(self, x: int, y: int, s: str, style: str = "") -> None:
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, style)

    def rows(self) -> list[Text]:
        out = []
        for row in self.cells:
            t = Text()
            for ch, st in row:
                t.append(ch, st)
            out.append(t)
        return out


# --- remsan ---------------------------------------------------------------------------
def _strip_col(bearing: float, own_course: float, w: int) -> int:
    return round((angle_diff(bearing, own_course) + 180.0) / 360.0 * (w - 1))


def _marker(o: SightedObject, day: bool) -> tuple[str, str]:
    if o.kind == "aircraft":
        return "v", STYLE["aircraft"]
    if o.kind == "station":
        return "*", STYLE["station"]
    if o.kind == "net":
        return "o", STYLE["net"]
    if not day:
        if "grön" in o.lights:
            return "•", STYLE["light_green"]
        if "röd" in o.lights:
            return "•", STYLE["light_red"]
        return "•", STYLE["light_white"]
    return {"helt": "▲", "överbyggnad": "▴"}.get(o.visible, "ˈ"), STYLE["ship"]


def _old(o: SightedObject, pic: PeriscopePicture) -> bool:
    """Föremålet är från ett tidigare svep (utanför en kort titt)."""
    return 0 <= o.seen_t < pic.t


def _ice_at(pic: PeriscopePicture, bearing: float) -> IceBearing | None:
    if not pic.ice:
        return None
    return min(pic.ice, key=lambda i: abs(angle_diff(i.bearing, bearing)))


def render_strip(pic: PeriscopePicture, w: int, selected: SightedObject | None,
                 stale: bool) -> list[Text]:
    g = _Grid(w, STRIP_ROWS)
    sea = STYLE["dim"] if stale else (STYLE["sea_day"] if pic.day else STYLE["sea_night"])
    ice_st = STYLE["ice"] if pic.day else STYLE["ice_night"]
    for x in range(w):
        b = norm360(pic.own_course + x / (w - 1) * 360.0 - 180.0)
        looked = in_sector(b, pic.sector)
        ice = _ice_at(pic, b)
        if ice is not None and ice.edge_nm is not None:
            g.put(x, 1, "^", STYLE["dim"] if stale or not looked
                  else (STYLE["ridge"] if ice.ridged else ice_st))
        else:
            g.put(x, 1, "─", sea if looked else STYLE["dim"])
    if pic.sector is not None:
        for side in (-1, 1):
            x = _strip_col(norm360(pic.sector + side * SECTOR_HALF_DEG), pic.own_course, w)
            g.put(x, 0, "{" if side < 0 else "}", STYLE["reticle"])
    # bäringsskala: var 30:e grad sann bäring
    mid = _strip_col(pic.own_course, pic.own_course, w)
    for b in range(0, 360, 30):
        x = _strip_col(b, pic.own_course, w)
        g.put(x, 1, "┼", STYLE["reticle"])
        if abs(x - mid) > 5:
            g.text(x - 1, 2, fmt_course(b), STYLE["dim"])
    g.text(mid - 2, 2, "förut", STYLE["reticle"])
    if selected is not None:
        for side in (-1, 1):
            x = _strip_col(norm360(selected.bearing + side * FOV_DEG / 2), pic.own_course, w)
            g.put(x, 1, "[" if side < 0 else "]", STYLE["label"])
    taken: set[int] = set()
    # det valda först, sedan närmast först: en beteckning som skulle krocka utelämnas
    for o in sorted(pic.objects, key=lambda o: (selected is None
                                                 or object_key(o) != object_key(selected),
                                                 o.range_nm)):
        x = _strip_col(o.bearing, pic.own_course, w)
        ch, st = _marker(o, pic.day)
        g.put(x, 1, ch, STYLE["ship_old"] if stale or _old(o, pic) else st)
        lab = o.designation or {"aircraft": "flyg", "station": "ljus", "net": "nät"}.get(o.kind, "")
        span = set(range(x - len(lab) // 2 - 1, x - len(lab) // 2 + len(lab) + 1))
        if lab and not span & taken:
            taken |= span
            sel = selected is not None and object_key(o) == object_key(selected)
            g.text(x - len(lab) // 2, 0, lab, STYLE["selected"] if sel
                   else STYLE["dim"] if _old(o, pic) else STYLE["label"])
    return g.rows()


# --- okularet -------------------------------------------------------------------------
def render_eyepiece(pic: PeriscopePicture, w: int, h: int, selected: SightedObject | None,
                    stale: bool) -> list[Text]:
    h = max(MIN_EYE_ROWS, h)
    g = _Grid(w, h)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    ry = (h - 1) / 2
    rx = min((w - 2) / 2, ry * 2.2)
    horizon = round(cy + 0.15 * ry)
    sky = STYLE["sky_day"] if pic.day else STYLE["sky_night"]
    sea = STYLE["sea_day"] if pic.day else STYLE["sea_night"]
    if stale:
        sky = sea = STYLE["dim"]
    inside = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            dx, dy = (x - cx) / rx, (y - cy) / max(ry, 1)
            if dx * dx + dy * dy <= 1.0:
                inside[y][x] = True
                if y == horizon:
                    g.put(x, y, "─", sea)
                elif y > horizon and (x * 7 + y * 3) % 11 == 0:
                    g.put(x, y, "~", sea)
            else:
                g.put(x, y, "░", STYLE["tube"])
    # sikte och gradering (var 4:e grad)
    cols_per_deg = 2 * rx / FOV_DEG
    for y in range(h):
        if inside[y][round(cx)] and y != horizon:
            g.put(round(cx), y, "┊", STYLE["reticle"])
    for k in range(-int(FOV_DEG // 8), int(FOV_DEG // 8) + 1):
        x = round(cx + k * 4 * cols_per_deg)
        if 0 <= x < w and inside[horizon][x]:
            g.put(x, horizon, "┼" if k == 0 else "┴", STYLE["reticle"])
    center = selected.bearing if selected is not None else (
        pic.sector if pic.sector is not None else pic.own_course)
    if pic.ice:
        _draw_ice(g, inside, pic, center, cx, cols_per_deg, horizon, stale)
    if selected is None:
        return g.rows()

    def col_of(b: float) -> float:
        return cx + angle_diff(b, selected.bearing) * cols_per_deg

    others = [o for o in pic.objects if o is not selected
              and abs(angle_diff(o.bearing, selected.bearing)) <= FOV_DEG / 2]
    for o in sorted(others, key=lambda o: -o.range_nm) + [selected]:
        sel = o is selected
        _draw_object(g, inside, o, col_of(o.bearing), horizon, pic.day, sel, stale, pic.t)
    return g.rows()


def _draw_ice(g: _Grid, inside, pic: PeriscopePicture, center: float, cx: float,
              cols_per_deg: float, horizon: int, stale: bool) -> None:
    """Isen runt öppningen: iskant på horisonten, vallar ovanför, nära is i förgrunden."""
    st = STYLE["dim"] if stale else (STYLE["ice"] if pic.day else STYLE["ice_night"])
    ridge = STYLE["dim"] if stale else STYLE["ridge"]
    for x in range(g.w):
        if not inside[horizon][x]:
            continue
        ice = _ice_at(pic, norm360(center + (x - cx) / cols_per_deg))
        if ice is None or ice.edge_nm is None:
            continue
        g.put(x, horizon, "▂", st)
        if ice.ridged and (x * 5) % 7 < 3 and inside[horizon - 1][x]:
            g.put(x, horizon - 1, "▲" if (x * 5) % 7 == 1 else "▴", ridge)
        near = round(3 * max(0.0, 1.0 - ice.edge_nm / ICE_LOOK_NM))
        for dy in range(1, near + 1):
            if horizon + dy < g.h and inside[horizon + dy][x]:
                g.put(x, horizon + dy, "▒", st)


def _draw_object(g: _Grid, inside, o: SightedObject, x: float, horizon: int, day: bool,
                 sel: bool, stale: bool, pic_t: int = 0) -> None:
    def put(px: int, py: int, ch: str, st: str) -> None:
        if 0 <= py < g.h and 0 <= px < g.w and inside[py][px] and ch != " ":
            g.put(px, py, ch, STYLE["ship_old"] if stale or old else st)

    old = 0 <= o.seen_t < pic_t

    xi = round(x)
    if o.kind == "aircraft":
        for i, ln in enumerate(AIRCRAFT_ART):
            for j, ch in enumerate(ln):
                put(xi - len(ln) // 2 + j, horizon - 5 + i, ch, STYLE["aircraft"])
        return
    if o.kind == "station":
        for dx, ch in ((-3, "*"), (0, "·"), (2, "*")):
            put(xi + dx, horizon - 1, ch, STYLE["station"])
        for dx in range(-6, 7):
            put(xi + dx, horizon, "^", STYLE["reticle"])
        return
    if o.kind == "net":
        for k in range(-4, 5):
            put(xi + 4 * k, horizon, "o", STYLE["net"])
        return
    if not day:
        if "topp" in o.lights:
            put(xi, horizon - 2, "*", STYLE["light_white"])
        side = next((c for c in ("grön", "röd") if c in o.lights), None)
        if side:
            put(xi + (2 if (o.aob or 0) > 0 else -2), horizon - 1, "●",
                STYLE["light_green" if side == "grön" else "light_red"])
        if "akter" in o.lights:
            put(xi, horizon - 1, "*", STYLE["light_white"])
        return
    lines = silhouette(o, large=_is_large(o) and sel)
    st = STYLE["ship"] if sel else STYLE["ship_other"]
    top = horizon - len(lines) + 1
    x0 = xi - max(map(len, lines), default=0) // 2
    for i, ln in enumerate(lines):
        for j, ch in enumerate(ln):
            put(x0 + j, top + i, ch, st)


# --- datarad och rubrik -------------------------------------------------------------
def data_line(o: SightedObject | None) -> Text:
    t = Text(" ")
    if o is None:
        t.append("Inget i sikte vid senaste svepet.", style=STYLE["dim"])
        return t
    name = f"{o.designation} {o.label}" if o.designation else o.label
    t.append(name, style="bold")
    t.append(f" · bäring {fmt_course(o.bearing)} · avstånd {nm(o.range_nm)} nm "
             f"({o.range_quality.label})")
    if o.aob is not None:
        t.append(f" · vinkel på bogen {aob_text(o.aob)} ({o.aob_quality.label})")
    if o.course is not None:
        t.append(f" · kurs {fmt_course(o.course)}")
    if o.speed is not None:
        t.append(f" · fart {kn(o.speed)} kn")
    if o.designation:
        t.append(" · " + ("lanternor: " + ", ".join(o.lights) if o.visible == "ljus"
                          else f"syns {o.visible}" if o.visible == "helt"
                          else f"syns: {o.visible}"))
    if o.detail:
        t.append(f" · {o.detail}")
    return t


def seen_earlier(o: SightedObject | None, pic: PeriscopePicture, clock: str) -> Text:
    return Text(f"  (sett {clock[:5]}, utanför senaste titten)", style="yellow") \
        if o is not None and _old(o, pic) else Text("")


def header(pic: PeriscopePicture | None, clock: str, age_s: int,
           note: str | None = None) -> Text:
    t = Text(" PERISKOP", style="bold")
    if note:
        t.append(f"   {note}", style="bold yellow")
    if pic is None:
        t.append("   inget svep än", style="dim")
        return t
    t.append(f"   bild {clock[:5]}")
    if age_s >= STALE_S:
        t.append(f" ({age_s // 60} min sedan)", style="yellow")
    t.append(f" · {'dag' if pic.day else 'natt'} · sikt {nm(pic.visibility_nm)} nm"
             f" · {pic.eye} · vår kurs {fmt_course(pic.own_course)}")
    if pic.sector is not None:
        t.append(f" · kort titt {fmt_course(pic.sector)}")
    return t


def render_periscope(pic: PeriscopePicture | None, w: int, h: int, index: int | None,
                     age_s: int, seen_clock=None) -> list[Text]:
    """Hela vyn: remsa, okular och datarad. index väljer bland ordered_objects()."""
    if pic is None:
        msg = Text(" Inget periskopsvep än. Gå upp på periskopdjup och skriv periskop.",
                   style=STYLE["dim"])
        return [msg]
    objs = ordered_objects(pic)
    sel = objs[index % len(objs)] if objs and index is not None else None
    stale = age_s >= STALE_S
    rows = render_strip(pic, w, sel, stale)
    rows.append(Text(""))
    eye_h = max(MIN_EYE_ROWS, h - STRIP_ROWS - 3)
    rows += render_eyepiece(pic, w, eye_h, sel, stale)
    line = data_line(sel)
    if sel is not None and seen_clock is not None:
        line.append_text(seen_earlier(sel, pic, seen_clock(sel.seen_t)))
    rows.append(line)
    return rows
