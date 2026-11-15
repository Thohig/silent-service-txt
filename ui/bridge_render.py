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
from sim.periscope import PeriscopePicture, SightedObject

from .periscope_render import (STYLE, _draw_ice, _draw_object, _Grid, _marker, data_line,
                               object_key, render_strip)

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
    """Sjön: glesa korta vågor vid horisonten, fler och längre nära oss; de rör sig med tiden."""
    st = STYLE["sea_day"] if day else STYLE["sea_night"]
    rows = max(1, bottom - horizon - 1)
    for y in range(horizon + 1, bottom):
        d = y - horizon
        near = d / rows                          # 0 vid horisonten, 1 närmast
        period = round(18 - 12 * near)
        drift = t // 2
        base = round(center * cols_per_deg)
        for x in range(g.w):
            b = base + x - round(cx) + (drift if d % 2 else -drift)
            if (_wave(b, d) % period) == 0:
                g.put(x, y, "~" if near > 0.3 else "-", st)
                if near > 0.6 and x + 1 < g.w:
                    g.put(x + 1, y, "~", st)


def _sky(g: _Grid, horizon: int, day: bool, center: float, cols_per_deg: float,
         cx: float) -> None:
    if day:
        # några låga moln, fasta i världen
        for y in range(1, max(2, horizon // 2)):
            for x in range(g.w):
                b = int(round(center * cols_per_deg)) + x - round(cx)
                if b % 9 == 0 and _wave(b // 9, y) % 7 == 0:
                    for k, ch in enumerate("._-‾‾-_."):
                        g.put(x + k, y, ch, BRIDGE_STYLE["cloud"])
        return
    for y in range(0, horizon - 1):
        for x in range(g.w):
            b = int(round((center + (x - cx) / cols_per_deg) * 2)) % 720
            if (b * 31 + y * 17) % 97 == 0:
                g.put(x, y, "·", BRIDGE_STYLE["star"])


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
        for i, y in enumerate(range(deck_top, rail_y)):
            half = 0.5 + (i + 1) * (g.w / 9) / max(rows, 1)
            left, right = round(apex - half), round(apex + half)
            for x in range(max(0, left + 1), min(g.w, right)):
                g.put(x, y, "▒", BRIDGE_STYLE["deck"])
            g.put(left, y, "/", BRIDGE_STYLE["deck_edge"])
            g.put(right, y, "\\", BRIDGE_STYLE["deck_edge"])
        g.put(round(apex), deck_top - 1, "^", BRIDGE_STYLE["deck_edge"])
    elif abs(stern) <= FOV_DEG / 2 + 10 and own_speed > 0.5:
        apex = cx + stern * cols_per_deg
        rows = rail_y - (horizon + 1)
        for i, y in enumerate(range(horizon + 1, rail_y)):
            half = 1 + (i + 1) * (g.w / 8) / max(rows, 1)
            for x in range(round(apex - half), round(apex + half) + 1):
                if (x * 5 + y * 3 + t) % 4 == 0:
                    g.put(x, y, "≈", BRIDGE_STYLE["wake"])
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
    inside = [[y < h - FOOT_ROWS + 1 for _ in range(w)] for y in range(h)]
    if pic.ice:
        _draw_ice(g, inside, pic, center, cx, cols_per_deg, horizon, False)

    def col_of(o: SightedObject) -> float:
        return cx + angle_diff(o.bearing, center) * cols_per_deg

    seen = [o for o in pic.objects if abs(angle_diff(o.bearing, center)) <= FOV_DEG / 2 + 3]
    focus = focus_object(pic, view_rel)
    for o in sorted(seen, key=lambda o: -o.range_nm):
        x = col_of(o)
        if o.designation is not None and o.range_nm >= FAR_NM and o.visible != "ljus":
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
    t = Text(" BRYGGAN", style="bold")
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
