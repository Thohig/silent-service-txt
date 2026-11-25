"""Centralens stora instrument: brailleritning, skalorna, visarna och den stora bilden."""
import math
from dataclasses import replace

from sim.game import StatusSnapshot
from ui import instruments as ins
from ui.canvas import BRAILLE_BASE, Braille, Canvas
from ui.central_render import Geometry, Needles, render_central

P = {"ring": "ring", "needle": "needle", "hub": "hub", "label": "label"}
BASE = StatusSnapshot(clock=4 * 3600 + 37 * 60, sim_time=0, course=90, ordered_course=90,
                      speed=6, ordered_speed=6, depth=100, ordered_depth=100,
                      changing=frozenset(), time_scale=1, contacts_held=())


def braille_cells(lines) -> int:
    return sum(1 for line in lines for ch in line.plain if 0x2800 < ord(ch) <= 0x28FF)


def test_braille_dots_and_priority():
    b = Braille(2, 1)
    b.dot(0, 0, "a")
    b.dot(1, 3, "b", prio=2)
    b.dot(0, 1, "c", prio=1)                 # lägre prioritet tar inte över rutan
    c = Canvas(2, 1, "")
    b.blit(c, 0, 0)
    ch, style = c.cells[0][0]
    assert ord(ch) - BRAILLE_BASE == 0x01 | 0x80 | 0x02
    assert style == "b"
    assert c.cells[0][1][0] == " "           # tom ruta lämnas orörd


def test_ray_points_the_right_way():
    b = Braille(20, 10)                      # 40 × 40 prickar
    b.ray(20, 20, 90, 0, 15, "x")            # österut
    right = sum(bin(b.bits[r][c]).count("1") for r in range(10) for c in range(11, 20))
    left = sum(bin(b.bits[r][c]).count("1") for r in range(10) for c in range(0, 9))
    assert right > 10 and left == 0


def test_scales():
    assert ins.depth_angle(0) == -135 and ins.depth_angle(500) == 135
    assert ins.depth_angle(900) == 135
    assert ins.speed_angle(15) == 0
    assert ins.rudder_needle(35) == 80 and ins.rudder_needle(-50) == -80
    assert ins.planes_needle(0) == 90 and ins.planes_needle(25) > 90
    assert [ins.telegraph_step(v) for v in (0, 3, 8, 20)] == [0, 1, 2, 3]
    assert ins.cavitation_kn(100) == 10


def test_dials_show_orders_and_zones():
    g = ins.gyro(247, 270, P)
    assert any(m[0] == 270 for m in g.markers)
    assert "247" in "".join(t for t, _ in g.readout)
    assert not ins.gyro(247, None, P).markers
    d = ins.depth_gauge(320, None, P)
    assert any(z[2] == ins.YELLOW for z in d.zones)
    assert "ff5f5f" in d.needles[0][2]       # över provdjupet blir visaren röd
    f = ins.speed_gauge(12, 12, 100, True, P)
    assert f.zones[0][0] == ins.speed_angle(10)    # kavitationen börjar på 10 kn på 100 m
    t = ins.telegraph(8, 3, "turbine", "online", P)
    assert {n[0] for n in t.needles} == {ins.TELEGRAPH_ANGLES[2], ins.TELEGRAPH_ANGLES[1]}
    assert ins.libell(20) != ins.libell(-20) and ins.libell(0).index("○") == 4


def test_clock_hands():
    c = ins.clock_face(3 * 3600, P)          # 03:00
    hour, minute, _ = c.needles
    assert hour[0] == 90 and minute[0] == 0


def test_needles_swing_smoothly_and_the_short_way():
    n = Needles(tau=0.5)
    n.update(replace(BASE, course=350), 0.0)
    v = n.update(replace(BASE, course=10), 0.1)["course"]
    assert 350 < v < 360 or v < 10           # mot 010 över norr, inte bakåt
    for i in range(2, 40):
        v = n.update(replace(BASE, course=10), i * 0.1)["course"]
    assert abs(v - 10) < 0.5
    d = Needles(tau=0.5)
    d.update(BASE, 0.0)
    half = d.update(replace(BASE, depth=200), 0.35)["depth"]
    assert 100 < half < 200


def test_big_room_has_braille_instruments_and_small_has_none():
    big = render_central(BASE, width=150, height=29)
    small = render_central(BASE)
    assert braille_cells(big) > 300
    assert braille_cells(small) == 0
    text = "\n".join(line.plain for line in big)
    for word in ("GYRO", "DJUP", "FART", "KLOCKA", "SIDROR", "DJUPROD", "TELEGRAF", "04:37"):
        assert word in text


def test_slots_fit_inside_the_walls():
    for w, h in ((100, 22), (130, 26), (150, 29), (220, 60)):
        g = Geometry(w, h)
        assert g.big
        slots = g.slots()
        for name, (top, left, rows, cols) in slots.items():
            assert top >= 1 and top + rows <= g.lamps, name
            assert cols >= 6 and rows >= 3, name
            inside_left = g.left[0] <= left and left + cols - 1 <= g.left[1]
            inside_right = g.right[0] <= left and left + cols - 1 <= g.right[1]
            assert inside_left or inside_right, name
    assert not Geometry(99, 30).big and not Geometry(150, 21).big


def test_readouts_show_the_exact_value_while_needles_lag():
    shown = {"course": 80.0, "depth": 90.0, "speed": 5.0, "rudder": 0.0, "planes": 0.0}
    text = "\n".join(line.plain for line in
                     render_central(BASE, width=150, height=29, shown=shown))
    assert "GYRO 090" in text and "DJUP 100 m" in text
    assert math.isclose(shown["course"], 80.0)


def test_no_crew_figures_in_any_size():
    for kw in ({}, {"width": 150, "height": 29}, {"width": 160, "height": 38}):
        text = "\n".join(line.plain for line in render_central(BASE, **kw))
        assert "▟█▙" not in text and "▐ ▌" not in text


def test_tall_wall_gets_the_smaller_instruments():
    tall, low = Geometry(160, 38), Geometry(150, 26)
    assert tall.strip_rows() > 0 and low.strip_rows() == 0
    slots = tall.slots()
    for name in ("lutning", "trim", "batteri", "lans"):
        top, left, rows, cols = slots[name]
        assert top + rows <= tall.lamps and rows >= 6
    assert not {"lutning", "batteri"} & set(low.slots())
    text = "\n".join(line.plain for line in render_central(BASE, width=160, height=38))
    for word in ("LUTNING", "TRIM", "BATTERI", "LÄNS", "GYRO", "DJUP"):
        assert word in text
    assert "LUTNING" not in "\n".join(line.plain for line in render_central(BASE, width=150, height=26))


def test_phone_panel_lights_the_speaker():
    from ui.central_render import ROLE_LIGHT
    rows = render_central(BASE, {"navigator": 0.5}, width=160, height=38)
    assert any(sp.style == ROLE_LIGHT["navigator"] for r in rows for sp in r.spans)
    assert "Navigatör" in "\n".join(r.plain for r in rows)


def test_dial_labels_never_overlap():
    """Små mätare: en etikett som skulle krocka med en annan ritas inte (SAKTA HALV blev SAKTHALV)."""
    for w, h in ((100, 22), (100, 26), (150, 29)):
        text = "\n".join(line.plain for line in render_central(BASE, width=w, height=h))
        assert "SAKTHALV" not in text and "SAKTAHALV" not in text


def test_tall_wall_gives_the_speed_gauge_its_own_slot_and_the_clock_goes_below():
    tall, low = Geometry(160, 38), Geometry(150, 26)
    t, l = tall.slots(), low.slots()
    assert t["klocka"][0] == t["batteri"][0]                     # klockan i raden under
    assert t["fart"][3] > l["fart"][3]                           # fartmätaren bredare
    assert l["klocka"][0] == l["fart"][0]                        # låg vägg: sida vid sida som förut
    for g in (tall, low):                                        # inga rutor överlappar
        boxes = list(g.slots().values())
        for i, (r0, c0, h0, w0) in enumerate(boxes):
            for r1, c1, h1, w1 in boxes[i + 1:]:
                assert r0 + h0 <= r1 or r1 + h1 <= r0 or c0 + w0 <= c1 or c1 + w1 <= c0
