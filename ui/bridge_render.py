"""Rastrering av utsikten från bryggan (rich, testbart utan Textual).

Bilden är utkikens (`Knowledge.bridge`), aldrig världen, och den uppdateras
varannan sekund medan bryggan är bemannad. Kaptenen tittar åt ett håll relativt
fören (`view_rel`), FOV_DEG brett: himmel, horisont med föremålen, sjö med
vågor som rör sig, och i förgrunden tornets räcke. Ser vi förut syns fördäcket,
ser vi akterut kölvattnet. Under bilden en bäringsskala för synfältet, en
360°-remsa med synfältet markerat och en rad om det föremål som ligger
närmast mitten av blicken.

Siluetter, lanternor, flyg, stationsljus, nät och is ritas som i periskopet
(`periscope_render`), så att samma fartyg ser likadant ut i båda vyerna.
"""
from __future__ import annotations

import math

from rich.text import Text

from sim.fmt import fmt_course, nm
from sim.geo import angle_diff, norm360
from sim.periscope import EVENT_KINDS, PeriscopePicture, SightedObject

from .periscope_render import (STYLE, _draw_ice, _draw_object, _Grid, _land_at, _marker,
                               data_line, object_key, render_strip)
from .placards import view_title

FOV_DEG = 120.0             # synfältet från bryggan
TURN_STEP_DEG = 15.0        # ← → vrider blicken så här mycket
FOCUS_DEG = 12.0            # föremål så nära blickens mitt beskrivs på dataraden
FAR_NM = 8.0                # längre bort: bara ett tecken på horisonten
LARGE_NM = 2.5              # närmare: stor siluett
STRIP_ROWS = 3
FOOT_ROWS = 3               # räcket och fördäcket längst ned i bilden
MIN_SCENE_ROWS = 9

BRIDGE_STYLE = {
    "rail": "#8a948a",
    "deck": "#3a4440",
    "deck_edge": "#6f7a70",
    "wake": "#b8d0d8",
    "star": "#8090a0",
    "foam": "#c8dce4",
    "cloud": "#5a6a70",
}


def view_text(view_rel: float) -> str:
    """Blickens riktning i ord, relativt fören."""
    r = angle_diff(norm360(view_rel), 0.0)
    if abs(r) < 1:
        return "rakt förut"
    if abs(r) > 179:
        return "rakt akterut"
    return f"{'styrbord' if r > 0 else 'babord'} {abs(r):.0f}°"


def focus_object(pic: PeriscopePicture, view_rel: float) -> SightedObject | None:
    """Föremålet närmast blickens mitt, om något ligger inom FOCUS_DEG."""
    center = norm360(pic.own_course + view_rel)
    near = [o for o in pic.objects if abs(angle_diff(o.bearing, center)) <= FOCUS_DEG]
    return min(near, key=lambda o: (abs(angle_diff(o.bearing, center)), o.range_nm), default=None)


def _wave(b: int, d: int) -> int:
    """Ett fast slumptal per bäringskolumn och rad, så att vågorna sitter i världen."""
    return hash((b, d, 114)) & 0xFFFFFF       # heltalstupler hashas lika i varje körning


def _sea(g: _Grid, horizon: int, bottom: int, day: bool, t: int, center: float,
         cols_per_deg: float, cx: float) -> None:
    """Sjön: korta vågkammar i prickar, glesa och korta vid horisonten, fler och längre
    nära oss; fasta i världen och de driver med tiden."""
    st = STYLE["sea_day"] if day else STYLE["sea_night"]
    rows = max(1, bottom - horizon - 1)
    for y in range(horizon + 1, bottom):
        d = y - horizon
        near = d / rows                          # 0 vid horisonten, 1 närmast
        period = round(18 - 12 * near)
        drift = t // 2
        base = round(center * cols_per_deg)
        length = 2 + round(7 * near)             # kammens längd i prickar
        for x in range(g.w):
            b = base + x - round(cx) + (drift if d % 2 else -drift)
            n = _wave(b, d)
            if n % period == 0:
                y0 = 4 * y + 1 + (n >> 8) % 2
                x0 = 2 * x + (n >> 9) % 2
                for k in range(length):
                    lift = 1 if 0 < k < length - 1 and length > 3 else 0     # kammen i mitten
                    g.dots.dot(x0 + k, y0 - lift, st)


def _sky(g: _Grid, horizon: int, day: bool, center: float, cols_per_deg: float,
         cx: float) -> None:
    if day:
        # några låga moln i prickar, fasta i världen: en rundad ovansida och platt botten
        for y in range(1, max(2, horizon // 2)):
            for x in range(g.w):
                b = int(round(center * cols_per_deg)) + x - round(cx)
                if b % 9 == 0 and _wave(b // 9, y) % 7 == 0:
                    n = _wave(b, y + 7)
                    length = 12 + n % 8                  # prickar
                    tall = 3 + (n >> 4) % 3
                    x0, base_y = 2 * x, 4 * y + 3
                    for k in range(length):
                        top = tall * math.sin(math.pi * (k + 0.5) / length) ** 0.7
                        g.dots.dot(x0 + k, base_y, BRIDGE_STYLE["cloud"])
                        g.dots.dot(x0 + k, base_y - top, BRIDGE_STYLE["cloud"])
                        if (k + y) % 3 == 0:
                            g.dots.dot(x0 + k, base_y - top / 2, BRIDGE_STYLE["cloud"])
        return
    for y in range(0, horizon - 1):
        for x in range(g.w):
            b = int(round((center + (x - cx) / cols_per_deg) * 2)) % 720
            if (b * 31 + y * 17) % 97 == 0:
                g.put(x, y, "·", BRIDGE_STYLE["star"])


PARTIAL = " ▁▂▃▄▅▆▇█"


def _land(g: _Grid, pic: PeriscopePicture, horizon: int, center: float, cols_per_deg: float,
          cx: float) -> None:
    """Landets silhuett ovanför horisonten i prickar: en jämn kam, högre ju närmare, kullar
    fasta i världen, och skrafferad mark under kammen ned till vattenlinjen."""
    if not pic.land:
        return
    st = STYLE["land_day"] if pic.day else STYLE["land_night"]
    base = 4 * horizon + 2                       # vattenlinjen, mitt i horisontens rad
    ridge_prev = None
    for xd in range(2 * g.w):
        b = norm360(center + (xd / 2 - cx) / cols_per_deg)
        land = _land_at(pic, b)
        if land is None:
            ridge_prev = None
            continue
        hill = 0.5 + 0.3 * math.sin(math.radians(b) * 7) + 0.2 * math.sin(math.radians(b) * 19 + 1)
        height = 0.7 + 3.0 * min(1.0, 1.5 / max(land.range_nm, 0.3)) * (0.5 + hill)
        ridge = base - 4 * height
        if xd % 2 == 0:
            g.put(xd // 2, horizon, " ", st)     # horisontlinjen går bakom landet
        lo = ridge if ridge_prev is None else min(ridge, ridge_prev)
        hi = ridge if ridge_prev is None else max(ridge, ridge_prev)
        for yd in range(int(lo), int(hi) + 1):   # kammen, sammanhängande där den lutar
            g.dots.dot(xd, yd, st, prio=1)
        for yd in range(int(ridge) + 2, base + 1):
            if (xd + yd) % 3 == 0 or yd >= base - 1:
                g.dots.dot(xd, yd, st, prio=1)
        ridge_prev = ridge


def _draw_event(g: _Grid, inside, o: SightedObject, x: float, horizon: int, t: int,
                day: bool = True) -> None:
    """Plask, vattenpelare, träff och torpedspår. På natten bara blixten och elden."""
    def put(px: int, py: int, ch: str, st: str) -> None:
        if 0 <= py < g.h and 0 <= px < g.w and inside[py][px] and ch != " ":
            g.put(px, py, ch, st)

    xi = round(x)
    age = max(0, t - o.seen_t)
    if o.kind == "splash":
        for dx, ch in ((-1, "'"), (0, ","), (1, "'")):
            put(xi + dx, horizon - 1, ch, STYLE["foam"])
    elif o.kind == "column" and not day:
        if age <= 2:
            put(xi, horizon - 1, "*", STYLE["light_white"])
    elif o.kind == "column":
        small = o.detail == "övning"
        rows = ([" . ", r"\|/", "|||"] if not small else [r"\|/", " | "])
        fall = min(len(rows) - 1, age // 4)            # pelaren sjunker ihop
        rows = rows[fall:]
        for i, ln in enumerate(rows):
            for j, ch in enumerate(ln):
                put(xi - 1 + j, horizon - len(rows) + i, ch, STYLE["foam"])
    elif o.kind == "hit":
        big = o.detail == "kärnladdning"
        flame = "▲▲▲▲▲" if big else "▲▲▲"
        for j, ch in enumerate(flame):
            put(xi - len(flame) // 2 + j, horizon - 1, ch, STYLE["fire"])
        height = min(8 if big else 5, 2 + age // 6) if day else 0   # röken stiger
        for k in range(2, height + 2):
            drift = k // 2                              # och driver undan
            w = 1 + k // 2 + (2 if big else 0)
            for dx in range(-w, w + 1):
                if (dx + k + t // 2) % 3:
                    put(xi + drift + dx, horizon - k, "░" if k > 3 else "▒", STYLE["smoke"])
    elif o.kind == "wake":
        rows_below = g.h - horizon - 4
        dy = min(max(1, round(0.6 / max(o.range_nm, 0.05))), max(1, rows_below))
        length = 1 + round(6 * abs(math.sin(math.radians(o.aob or 90.0))))
        step = -1 if (o.aob or 0) < 0 else 1
        for k in range(length):
            put(xi - step * k, horizon + dy, "=" if k else "◦", STYLE["foam"])


def _foreground(g: _Grid, horizon: int, view_rel: float, cx: float, cols_per_deg: float,
                own_speed: float, t: int) -> None:
    """Fördäcket eller kölvattnet, och tornets räcke närmast oss."""
    rail_y = g.h - 1
    bow = angle_diff(0.0, view_rel)          # fören i bilden, grader från mitten
    stern = angle_diff(180.0, view_rel)
    deck_top = horizon + max(2, round((rail_y - horizon) * 0.45))
    if abs(bow) <= FOV_DEG / 2 + 10:
        apex = cx + bow * cols_per_deg
        rows = rail_y - deck_top
        spread = (g.w / 9) / max(rows, 1)              # kolumner per rad åt varje sida
        for i, y in enumerate(range(deck_top, rail_y)):
            half = 0.5 + (i + 1) * spread
            left, right = round(apex - half), round(apex + half)
            for x in range(max(0, left + 1), min(g.w, right)):
                g.put(x, y, "▒", BRIDGE_STYLE["deck"])
        # relingen i prickar från stäven och ut mot räcket
        ax, ay = 2 * apex + 1, 4 * deck_top - 2
        span = 2 * (0.5 + rows * spread)
        g.dots.line(ax, ay, ax - span, 4 * rail_y, BRIDGE_STYLE["deck_edge"])
        g.dots.line(ax, ay, ax + span, 4 * rail_y, BRIDGE_STYLE["deck_edge"])
    elif abs(stern) <= FOV_DEG / 2 + 10 and own_speed > 0.5:
        apex = cx + stern * cols_per_deg
        rows = rail_y - (horizon + 1)
        for i, y in enumerate(range(horizon + 1, rail_y)):
            half = 1 + (i + 1) * (g.w / 8) / max(rows, 1)
            for xd in range(round(2 * (apex - half)), round(2 * (apex + half)) + 1):
                for yd in range(4 * y, 4 * y + 4):
                    if (xd * 5 + yd * 3 + t) % 7 == 0:   # skum som virvlar i kölvattnet
                        g.dots.dot(xd, yd, BRIDGE_STYLE["wake"])
    for x in range(g.w):
        g.put(x, rail_y, "╤" if x % 12 == 0 else "═", BRIDGE_STYLE["rail"])


def _labels(g: _Grid, objs, col_of, horizon: int, focus: SightedObject | None) -> None:
    taken: list[tuple[int, int, int]] = []
    for o in sorted(objs, key=lambda o: (focus is None or o is not focus, o.range_nm)):
        if o.designation is None:
            continue
        lab = f"{o.designation} {nm(o.range_nm)}"
        x0 = min(max(0, round(col_of(o)) - len(lab) // 2), g.w - len(lab))
        top = horizon - _height(o) - 1
        for y in range(top, max(0, top - 4), -1):
            if all(not (ty == y and x0 <= tx1 and tx0 <= x0 + len(lab)) for tx0, tx1, ty in taken):
                taken.append((x0, x0 + len(lab), y))
                g.text(x0, y, lab, STYLE["selected"] if o is focus else STYLE["label"])
                break


def _height(o: SightedObject) -> int:
    """Hur många rader föremålet når över horisonten (för etiketten)."""
    if o.kind == "aircraft":
        return 5
    if o.visible == "ljus" or o.range_nm >= FAR_NM:
        return 2
    if o.visible == "mastoppar":
        return 2
    return 6 if o.range_nm < LARGE_NM else 3


def render_scene(pic: PeriscopePicture, w: int, h: int, view_rel: float, t: int,
                 own_speed: float = 0.0) -> list[Text]:
    h = max(MIN_SCENE_ROWS, h)
    g = _Grid(w, h)
    cx = (w - 1) / 2
    cols_per_deg = w / FOV_DEG
    center = norm360(pic.own_course + view_rel)
    horizon = max(6, round(h * 0.45))
    sea_bottom = h - 1
    _sky(g, horizon, pic.day, center, cols_per_deg, cx)
    for x in range(w):
        g.put(x, horizon, "─", STYLE["sea_day"] if pic.day else STYLE["sea_night"])
    _sea(g, horizon, sea_bottom, pic.day, t, center, cols_per_deg, cx)
    _land(g, pic, horizon, center, cols_per_deg, cx)
    inside = [[y < h - FOOT_ROWS + 1 for _ in range(w)] for y in range(h)]
    if pic.ice:
        _draw_ice(g, inside, pic, center, cx, cols_per_deg, horizon, False)

    def col_of(o: SightedObject) -> float:
        return cx + angle_diff(o.bearing, center) * cols_per_deg

    seen = [o for o in pic.objects if abs(angle_diff(o.bearing, center)) <= FOV_DEG / 2 + 3]
    focus = focus_object(pic, view_rel)
    for o in sorted(seen, key=lambda o: -o.range_nm):
        x = col_of(o)
        if o.kind in EVENT_KINDS:
            _draw_event(g, inside, o, x, horizon, t, pic.day)
        elif o.designation is not None and o.range_nm >= FAR_NM and o.visible != "ljus":
            ch, st = _marker(o, pic.day)
            g.put(round(x), horizon, ch, st)
        else:
            _draw_object(g, inside, o, x, horizon, pic.day, True, False)
    _labels(g, seen, col_of, horizon, focus)
    _foreground(g, horizon, view_rel, cx, cols_per_deg, own_speed, t)
    return g.rows()


def render_scale(pic: PeriscopePicture, w: int, view_rel: float) -> Text:
    """Sanna bäringar var 10:e grad under bilden; blickens mitt med sin bäring."""
    g = _Grid(w, 1)
    cx = round((w - 1) / 2)
    cols_per_deg = w / FOV_DEG
    center = norm360(pic.own_course + view_rel)
    first = math.ceil((center - FOV_DEG / 2) / 10) * 10
    for b in range(first, int(center + FOV_DEG / 2) + 1, 10):
        x = round(cx + angle_diff(norm360(b), center) * cols_per_deg)
        if 1 <= x < w - 2 and abs(x - cx) > 5:
            g.text(x - 1, 0, fmt_course(norm360(b)), STYLE["dim"])
    g.text(cx - 2, 0, f"‹{fmt_course(center)}›", STYLE["reticle"])
    return g.rows()[0]


def render_bridge_strip(pic: PeriscopePicture, w: int, view_rel: float,
                        focus: SightedObject | None) -> list[Text]:
    """360°-remsan som i periskopet, med blickens synfält inom klamrar."""
    return render_strip(pic, w, focus, False, window=(norm360(pic.own_course + view_rel), FOV_DEG))


def no_picture(status_bridge: str, depth: float) -> list[Text]:
    if depth > 1.0:
        msg = "Under ytan, ingen sikt. Bryggan bemannas när vi går upp i ytläge (ytläge)."
    elif status_bridge == "manning":
        msg = "Tornluckan öppnas, utkikarna är på väg upp."
    elif status_bridge == "clearing":
        msg = "Bryggan utryms, luckan stängs. Vi dyker."
    else:
        msg = "Tornluckan är stängd."
    return [Text(""), Text(f" {msg}", style=STYLE["dim"])]


def header(pic: PeriscopePicture | None, clock: str, view_rel: float) -> Text:
    t = view_title("BRYGGAN")
    if pic is None:
        t.append("   ingen på bryggan", style="dim")
        return t
    center = norm360(pic.own_course + view_rel)
    t.append(f"   {clock[:5]} · {'dag' if pic.day else 'natt'} · sikt {nm(pic.visibility_nm)} nm"
             f" · vår kurs {fmt_course(pic.own_course)}"
             f" · blicken {view_text(view_rel)} (bäring {fmt_course(center)})")
    return t


def render_bridge(pic: PeriscopePicture | None, w: int, h: int, view_rel: float, t: int,
                  own_speed: float = 0.0, status_bridge: str = "shut",
                  depth: float = 0.0) -> list[Text]:
    """Hela vyn: bilden, bäringsskalan, remsan och dataraden."""
    if pic is None:
        return no_picture(status_bridge, depth)
    focus = focus_object(pic, view_rel)
    scene_h = max(MIN_SCENE_ROWS, h - STRIP_ROWS - 2)
    rows = render_scene(pic, w, scene_h, view_rel, t, own_speed)
    rows.append(render_scale(pic, w, view_rel))
    rows += render_bridge_strip(pic, w, view_rel, focus)
    line = data_line(focus) if focus is not None else Text(
        " Inget i sikte mitt i blicken. ← → vrider blicken.", style=STYLE["dim"])
    rows.append(line)
    return rows


__all__ = ["FOV_DEG", "TURN_STEP_DEG", "focus_object", "header", "object_key", "render_bridge",
           "view_text"]
