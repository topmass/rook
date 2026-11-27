"""Devs 3D concepts for the daily tool icons, round three, after the owner's review of round two on 2026-11-27.

prompt3_b is Glyph with a gentle sway. globe3_a, _b and _c are fresh concepts for web search and fetch. message3_a
is a new take on Writing. overlook3_a, _b and _c grow from Field: the cube above three thread rows on a floor. The
round-two forms in icons_tools2.py stay as they are. ACTIVITY_FORMS maps no tool to these forms yet.

Every concept moves by the object itself, in Devs dust. No form has a glowing bead, a roving point or a ground
element under the object. devs_pack registers BUILDERS and the evaluators in one line at its end. Import this module
only through devs_pack. Every form has 640 grains and stays in the Devs form box. Every loop closes with no seam.
"""

from __future__ import annotations

import math

import devs_pack as dp
import icons_tools2 as t2

TAU = t2.TAU
sin, cos, exp = math.sin, math.cos, math.exp
_smooth = dp._smooth
_age, _turn, _slab, _bubble, _words, _cube, _sphere, _fib = (t2._age, t2._turn, t2._slab, t2._bubble, t2._words,
                                                             t2._cube, t2._sphere, t2._fib)

# Each form's scale, so it stands about 105 px high or 120 px wide on screen, as the other Devs forms do.
FIT = {"prompt3_b": 1.15, "globe3_a": 1.1, "globe3_b": 1.05, "globe3_c": 1.1, "message3_a": 1.1,
       "overlook3_a": 1.0, "overlook3_b": 1.0, "overlook3_c": 0.95, "overlook3_d": 0.95}


class _Pose(t2._Pose):
    """icons_tools2's projection, with this module's FIT."""

    def __init__(self, name, scene, now, yaw, pitch, span=44.0, persp=320.0):
        super().__init__(name, scene, now, yaw, pitch, span, persp)
        self.k = FIT[name]
        self.span = span * self.k


def _bez(p, c, q, s):
    """The point a share s along the quadratic curve from p through the pull of c to q."""
    return tuple((1 - s) ** 2 * a + 2 * (1 - s) * s * b + s * s * e for a, b, e in zip(p, c, q))


# ---------------------------------------------------------------------------
# prompt: running a command (Bash)
# ---------------------------------------------------------------------------

# B: Glyph, calmer. Round two's solid ">_" and its dust flowing down the strokes, with a sway of at most 14 degrees,
# so the prompt always faces the viewer. The cursor blinks: its face and walls dim and come back, as a cursor does.
GLYPH_YAW, GLYPH_SWAY, GLYPH_BLINK = -0.12, 0.12, 1.1  # The sway's centre and reach in radians; the blink in seconds.


def build_prompt3_b(grains, rng):
    # Round two's glyph. The cursor's walls get their own kind, so they blink with its face.
    return [(*p[:3], "bar", p[4]) if p[3] == "wall" and p[0] > 0.0 and p[1] > 38.0 else p
            for p in t2.build_prompt2_b(grains, rng)]


def eval_prompt3_b(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, GLYPH_YAW + GLYPH_SWAY * sin(TAU * d / 9.0), -0.12 + 0.04 * sin(TAU * d / 11.0),
                 span=40.0)
    blink = 0.3 + 0.7 * _smooth((0.5 + 0.5 * cos(TAU * d / GLYPH_BLINK) - 0.3) / 0.4)
    tx_, ty_ = t2.GLYPH_TIP
    for rec in points:
        if rec[3] in ("wall", "bar"):
            pose.put(rec[0], rec[1], rec[2], rec[4] * (blink if rec[3] == "bar" else 1.0))
            continue
        side, u, w, length = rec[4:]
        span = t2.GLYPH_OVER if side else 1.0
        s = (u + t2.GLYPH_FLOW * d / length) % span
        b = 1.15 * _smooth((s - 0.06) / 0.08) * _smooth((span - s) / 0.05)  # Dark at first, while it flies back.
        if side:
            ex, ey = t2.GLYPH_ENDS[0 if side < 0 else 1]
            dx, dy = (tx_ - ex) / length, (ty_ - ey) / length
            x, y = ex + (tx_ - ex) * s - dy * w, ey + (ty_ - ey) * s + dx * w
        else:
            x0, x1, y0 = t2.GLYPH_BAR
            x, y, b = x0 + (x1 - x0) * s, y0 + w, b * blink
        pose.put(x, y, t2.GLYPH_DEEP / 2, b, gate=True)
    return pose.out()


# ---------------------------------------------------------------------------
# globe: searching and fetching the web
# ---------------------------------------------------------------------------

def _grid(pts, rng, r, rings, kind="grid"):
    """A globe's lines of latitude and longitude as solid lines of dust: rings is ((meridian, where, n), ...)."""
    for meridian, where, n in rings:
        for k in range(n):
            a = TAU * (k + rng.uniform(-0.2, 0.2)) / n
            if meridian:
                pts.append((*_turn(r * cos(a), r * sin(a), 0.0, where), kind, 1.0))
            else:
                pts.append((*_sphere(a, where, r), kind, 1.0))


# A: Lens. A turning globe of meridians and parallels, and a magnifying glass sweeping its face in a slow figure of
# eight. Under the lens the globe's lines swell, as a lens enlarges them: the web being searched.
LENS_GLOBE, LENS_R, LENS_TUBE, LENS_HANDLE = 40.0, 15.0, 1.6, 22.0
LENS_P, LENS_SPIN, LENS_TILT, LENS_ZOOM = 6.0, 0.22, -0.35, 1.6  # Sweep loop; turn; axis tilt; the zoom.
LENS_DIR = (math.sqrt(0.5), math.sqrt(0.5))  # The handle points down and right.


def _lens_at(d):
    a = TAU * d / LENS_P
    x, y = 17.0 * sin(a), -4.0 + 11.0 * sin(2.0 * a)
    return x, y, math.sqrt(max(0.0, LENS_GLOBE ** 2 - x * x - y * y)) + 7.0


def _lens_part(kind, a, c, lx, ly, lz):
    """A grain of the magnifier at lx, ly, lz: on the rim at angle a, or on the handle a share a of its length out;
    c is its angle round the rim's or the handle's section."""
    if kind == "rim":
        r = LENS_R + LENS_TUBE * cos(c)
        return lx + r * cos(a), ly + r * sin(a), lz + LENS_TUBE * sin(c)
    (hx, hy), r, along = LENS_DIR, 1.9 + 1.2 * a, LENS_R + 1.0 + LENS_HANDLE * a
    return lx + hx * along - hy * r * cos(c), ly + hy * along + hx * r * cos(c), lz + 0.3 * LENS_HANDLE * a + r * sin(c)


def build_globe3_a(grains, rng):
    pts = []
    _grid(pts, rng, LENS_GLOBE, ((0, 0.0, 74), (0, 0.62, 58), (0, -0.62, 58),
                                 (1, 0.0, 62), (1, math.pi / 3, 62), (1, 2 * math.pi / 3, 62)))
    for lon, lat in _fib(110):  # The globe's skin: faint, so it reads as a solid ball.
        pts.append((*_sphere(lon, lat, LENS_GLOBE), "skin", 0.38))
    pts = [(*_turn(*p[:3], 0.0, LENS_TILT), *p[3:], *p[:3]) for p in pts]  # Its place at the start, for the sort.
    lens = _lens_at(0.0)
    for k in range(130):  # The lens's rim: a ring with a round section.
        a, c = TAU * (k + rng.random()) / 130, rng.uniform(0.0, TAU)
        pts.append((*_lens_part("rim", a, c, *lens), "rim", a, c))
    n = grains - len(pts)
    for k in range(n):  # The handle: a rod that thickens toward its end.
        a, c = (k + rng.random()) / n, rng.uniform(0.0, TAU)
        pts.append((*_lens_part("handle", a, c, *lens), "handle", a, c))
    return dp._by_angle(pts)


def eval_globe3_a(name, points, scene, now):
    d = _age(scene, now)
    spin = LENS_SPIN * d
    lx, ly, lz = _lens_at(d)
    pose = _Pose(name, scene, now, 0.0, 0.0, span=LENS_GLOBE)
    for rec in points:
        kind = rec[3]
        if kind in ("rim", "handle"):
            pose.put(*_lens_part(kind, *rec[4:], lx, ly, lz), 0.8 if kind == "rim" else 0.9)
            continue
        x, y, z = _turn(*rec[5:], spin, LENS_TILT)
        b, gate = rec[4], False
        if z > 0.0 and math.hypot(x - lx, y - ly) < LENS_R:  # Under the glass: the middle shows enlarged, and the
            x, y = lx + (x - lx) * LENS_ZOOM, ly + (y - ly) * LENS_ZOOM  # rest of the disc is out of its view.
            b, gate = (b * 1.3 if math.hypot(x - lx, y - ly) < LENS_R - 1.0 else 0.0), True
        pose.put(x, y, z, b, gate=gate, back=0.3)
    return pose.out()


# B: Unfold. A globe of meridians and parallels turns once and stops. Its meridians open out: the sphere unrolls
# toward the viewer into a flat page. The back meridian becomes the page's sides, the polar rings its top and foot,
# the parallels its lines of text, and the other meridians' dust flows into those lines. Then it folds back up.
UNF_R, UNF_W, UNF_H, UNF_EDGE = 40.0, 50.0 / math.pi, 26.0, 1.25  # Globe radius; page scale across and down; poles.
UNF_ROWS = (0.9, 0.45, 0.0, -0.45, -0.9)  # The parallels that become the page's lines.
UNF_MERIDIANS = tuple(k * math.pi / 3 for k in (-2, -1, 0, 1, 2))  # Inner meridians; the back one is at pi.
UNF_TURN, UNF_OPEN, UNF_HOLD, UNF_LEAD = 4.2, 1.1, 1.9, 2.4  # The turn, the open or close, the page's hold; start.
UNF_P = UNF_TURN + 2 * UNF_OPEN + UNF_HOLD


def build_globe3_b(grains, rng):
    """A record ends (lon, lat on the globe, lon, lat on the page, lag, look)."""
    pts = []

    def put(lon0, lat0, lon1, lat1, kind, look):
        pts.append((*_sphere(lon0, lat0, UNF_R), kind, lon0, lat0, lon1, lat1, rng.random(), look))

    for side in (-1, 1):  # The polar rings: the page's top and foot.
        for k in range(40):
            lon = -math.pi + TAU * (k + 0.5) / 40
            put(lon, side * UNF_EDGE, lon, side * UNF_EDGE, "edge", 0.95)
    for k in range(60):  # The back meridian, which splits into the page's two sides.
        lon, lat = (math.pi if k % 2 else -math.pi), -UNF_EDGE + 2 * UNF_EDGE * (k + 0.5) / 60
        put(lon, lat, lon, lat, "edge", 0.95)
    per = (grains - len(pts)) // len(UNF_ROWS)
    for row, lat in enumerate(UNF_ROWS):
        n = per if row < len(UNF_ROWS) - 1 else grains - len(pts)
        free = [-math.pi + TAU * m / 100.0 for m in _words(rng, 100.0, n)]  # Words as on a page 100 px wide.
        lo = UNF_EDGE if row == 0 else lat + 0.225  # The band of the meridian this row's dust comes from.
        hi = -UNF_EDGE if row == len(UNF_ROWS) - 1 else lat - 0.225
        for lon_m in UNF_MERIDIANS:  # The places nearest each meridian take its dust.
            free.sort(key=lambda m: abs(m - lon_m))
            for i in range(8):
                put(lon_m, lo + (hi - lo) * (i + 0.5) / 8, free[i], lat + rng.gauss(0, 0.035), "text", 1.0)
            del free[:8]
        for m in free:
            j = rng.gauss(0, 0.035)
            put(m, lat + j, m, lat + j, "text", 1.0)
    return dp._by_angle(pts)


def _unroll(lon, lat, u):
    """A point of the globe at lon, lat, a share u of the way unrolled into the page: the sphere opens through ever
    wider cylinders, and its parallels straighten into lines."""
    a = 1.0 - u
    cl = cos(lat) * a + u
    y = -UNF_R * sin(lat) * a - UNF_H * lat * u
    w = UNF_R * a + UNF_W * u
    if a < 1e-6:
        return w * lon, y, 0.0
    rho, th = w / a, lon * a
    return cl * rho * sin(th), y, -2.0 * cl * rho * sin(th / 2) ** 2 + w * (cos(lat) - 1.0) + UNF_R * a


def eval_globe3_b(name, points, scene, now):
    d = _age(scene, now)
    t = (d + UNF_LEAD) % UNF_P
    spin, u = 0.0, 0.0
    if t < UNF_TURN:
        spin = TAU * _smooth(t / UNF_TURN)
    elif t < UNF_TURN + UNF_OPEN:
        u = _smooth((t - UNF_TURN) / UNF_OPEN)
    elif t < UNF_TURN + UNF_OPEN + UNF_HOLD:
        u = 1.0
    else:
        u = 1.0 - _smooth((t - UNF_P + UNF_OPEN) / UNF_OPEN)
    pose = _Pose(name, scene, now, 0.0, -0.22, span=UNF_R)
    for rec in points:
        lon0, lat0, lon1, lat1, lag, look = rec[4:]
        k = _smooth(1.6 * u - 0.6 * lag)  # Each grain flows to its line a beat apart, so the dust streams.
        x, y, z = _unroll(lon0 + (lon1 - lon0) * k + spin, lat0 + (lat1 - lat0) * k, u)
        pose.put(x, y, z + 10.0 * u, look * (1.0 + 0.15 * u * (rec[3] == "text")), back=0.3)
    return pose.out()


# C: Results. A turning globe on the left, and a list of three results on the right. Every beat a new result is
# pulled out of the globe's face as a stream of dust that lays itself out as the newest line, the list moves up one
# place, and the top line lifts away as loose dust.
PULL_C, PULL_R, PULL_SPIN, PULL_TILT = (-34.0, 0.0), 26.0, 0.3, -0.35  # The globe's centre, radius, turn and tilt.
PULL_P, PULL_STEP, PULL_X = 1.7, 0.4, 2.0  # One beat; the share of it the list takes to move; the lines' left end.
PULL_YS = (22.0, 0.0, -22.0)  # The list's places, newest at the foot.
PULL_ENDS, PULL_LATS = (58.0, 44.0, 54.0, 38.0), (0.45, -0.1, 0.25, -0.4)  # Each line's length; where it is pulled.


def _pull_source(slot):
    """The place on the globe's face, toward the list, that a slot's line is pulled from."""
    lat, cx, cy = PULL_LATS[slot], *PULL_C
    return cx + PULL_R * cos(lat) * sin(0.8), cy - PULL_R * sin(lat), PULL_R * cos(lat) * cos(0.8)


def build_globe3_c(grains, rng):
    pts = []
    _grid(pts, rng, PULL_R, ((0, 0.0, 50), (0, 0.62, 38), (0, -0.62, 38),
                             (1, 0.0, 44), (1, math.pi / 3, 44), (1, 2 * math.pi / 3, 44)))
    for lon, lat in _fib(36):
        pts.append((*_sphere(lon, lat, PULL_R), "skin", 0.38))
    pts = [(x + PULL_C[0], y + PULL_C[1], z, kind, look) for x, y, z, kind, look in pts]
    per = (grains - len(pts)) // len(PULL_ENDS)
    for slot, end in enumerate(PULL_ENDS):
        n = per if slot < len(PULL_ENDS) - 1 else grains - len(pts)
        for m in _words(rng, end, n):
            pts.append((PULL_X + m, PULL_YS[0], 0.0, "line", slot, m, m / end, rng.uniform(-2.1, 2.1),
                        rng.gauss(0, 3.0), rng.random()))
    return dp._by_angle(pts)


def eval_globe3_c(name, points, scene, now):
    d = _age(scene, now)
    spin = PULL_SPIN * d
    pose = _Pose(name, scene, now, -0.12 + 0.08 * sin(TAU * d / 9.0), -0.1, span=36.0)
    cx, cy = PULL_C
    slots = len(PULL_ENDS)
    for rec in points:
        if rec[3] != "line":
            x, y, z = _turn(rec[0] - cx, rec[1] - cy, rec[2], spin, PULL_TILT)
            pose.put(cx + x, cy + y, z, rec[4], back=0.3)
            continue
        slot, m, f, jy, loose, lag = rec[4:]
        A = (d / PULL_P + slot + 0.6) % slots  # Its beat: 0 pulled out, 1 and 2 moving up the list, 3 lifting away.
        band, a = int(A), A % 1.0
        step = _smooth(a / PULL_STEP)
        source = _pull_source(slot)
        home = (PULL_X + m, jy, 0.0)
        if band == 0:  # Pulled out: the line's far end leaves first, so it unreels from the globe.
            s = _smooth((a - 0.25 - 0.35 * (1.0 - f)) / 0.4)
            if s <= 0.0:
                pose.put(*source, 0.0, gate=True)
                continue
            end = (home[0], home[1] + PULL_YS[0], 0.0)
            mid = ((source[0] + end[0]) / 2, min(source[1], end[1]) - 12.0, 16.0)
            pose.put(*_bez(source, mid, end, s), 0.35 + 0.8 * s)
        elif band < 3:
            pose.put(home[0], home[1] + PULL_YS[band - 1] + (PULL_YS[band] - PULL_YS[band - 1]) * step, 0.0, 1.15)
        elif a < PULL_STEP + 0.1:  # The top line lifts away as loose dust.
            pose.put(home[0] + loose * step, home[1] + PULL_YS[2] - (12.0 + 6.0 * lag) * step, 10.0 * step,
                     1.15 * (1.0 - step) ** 2)
        else:  # Gone: back to the globe unseen, for its next pull.
            pose.put(*source, 0.0, gate=True)
    return pose.out()


# ---------------------------------------------------------------------------
# message: reading a coding thread's messages
# ---------------------------------------------------------------------------

# A: Ink. A solid speech bubble with a clear tail, and its message writes itself line by line at the foot, as a pen
# does: each grain settles out of the face as the writing passes. Every line done, the lines move up one place, and
# the top line lifts off the face as loose dust. The bubble always holds two or three lines.
INK_W, INK_H, INK_R, INK_CY, INK_T = 104.0, 66.0, 20.0, -8.0, 10.0
INK_TAIL = (-14.0, -34.0, (-46.0, 44.0))
INK_P, INK_STEP, INK_PEN, INK_X = 1.5, 0.3, 82.0, -38.0  # One line's beat; the move's share; pen px/s; left margin.
INK_YS, INK_ENDS = (8.0, -8.0, -24.0), (72.0, 56.0, 76.0, 44.0)  # The lines' places, foot first; each line's length.


def build_message3_a(grains, rng):
    pts = []
    _slab(pts, _bubble(0.0, INK_CY, INK_W, INK_H, INK_R, INK_TAIL), INK_T, 300, rng, "bubble", face=0.3)
    per = (grains - len(pts)) // len(INK_ENDS)
    for slot, end in enumerate(INK_ENDS):
        n = per if slot < len(INK_ENDS) - 1 else grains - len(pts)
        for m in _words(rng, end, n):
            pts.append((INK_X + m, INK_YS[0], INK_T / 2 + 0.6, "text", slot, m, rng.uniform(-1.7, 1.7),
                        rng.gauss(0, 2.5), rng.random()))
    return dp._by_angle(pts)


def eval_message3_a(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.3 + 0.1 * sin(TAU * d / 8.5), -0.1, span=36.0)
    z = INK_T / 2 + 0.6
    slots = len(INK_ENDS)
    for rec in points:
        if rec[3] == "bubble":
            pose.put(rec[0], rec[1], rec[2], rec[4] * (0.95 if rec[4] < 0.9 else 0.3))
            continue
        slot, m, jy, loose, lag = rec[4:]
        A = (d / INK_P + slot + 0.7) % slots  # Its beat: 0 written at the foot, 1 and 2 moving up, 3 lifting off.
        band, a = int(A), A % 1.0
        step = _smooth(a / INK_STEP)
        x, y = INK_X + m, jy
        if band == 0:
            pen = (a - INK_STEP - 0.02) * INK_P * INK_PEN - m  # How far the pen is past this grain, in px.
            k = _smooth(pen / 6.0)
            if k <= 0.0:  # Not written yet: dark, in its place.
                pose.put(x, y + INK_YS[0], z, 0.0, gate=True)
                continue
            pose.put(x, y + INK_YS[0] + 2.5 * (1.0 - k), z - 2.0 * (1.0 - k), k * (1.15 + 0.1 * exp(-pen / 8.0)))
        elif band < 3:
            pose.put(x, y + INK_YS[band - 1] + (INK_YS[band] - INK_YS[band - 1]) * step, z, 1.15)
        elif a < INK_STEP + 0.15:  # The top line lifts off the face as loose dust.
            u = _smooth(a / (INK_STEP + 0.1))
            pose.put(x + loose * u, y + INK_YS[2] - (10.0 + 6.0 * lag) * u, z + 10.0 * u, 1.15 * (1.0 - u) ** 2)
        else:  # Gone: back to the foot unseen, to be written again.
            pose.put(x, y + INK_YS[0], z, 0.0, gate=True)
    return pose.out()


# ---------------------------------------------------------------------------
# overlook: looking over the coding threads (a cube above three rows, as the owner chose on 2026-11-22)
# ---------------------------------------------------------------------------

# The three rows are thread cards lying on a floor, seen from above, as in Field: each a faint plate, a square mark
# and a line of words. A card grain's record ends (row, look, x, height, across): its place on its own card.
CARD_HALF, CARD_DEEP, CARD_FLOOR, CARD_PLACES = 48.0, 8.0, 24.0, (-34.0, 0.0, 34.0)  # Far to near.
CARD_ENDS, CUBE_Y, CUBE_HALF = (40.0, 26.0, 34.0), -40.0, 13.0


def _on_floor(card, place_z, lift=0.0, tilt=0.0):
    """A card grain's world place: on the card at depth place_z, raised by lift and tilted up toward the viewer by
    tilt radians about its long axis."""
    x, h, w = card
    ct, st = cos(tilt), sin(tilt)
    return x, CARD_FLOOR - lift + w * st - h * ct, place_z + w * ct + h * st


def _cards(grains, rng, cube_y=CUBE_Y):
    pts = []
    _cube(pts, CUBE_HALF, 190, rng, "cube")
    pts = [(x, y + cube_y, z, kind, -1, look) for x, y, z, kind, look in pts]
    per = (grains - len(pts)) // 3
    for row in range(3):
        n, card = per if row < 2 else grains - len(pts), []
        for x, w in t2._fill(lambda x, y: True, (-CARD_HALF, -CARD_DEEP, CARD_HALF, CARD_DEEP), 48, rng):
            card.append(("edge", 0.32, x, 0.0, w))
        for x, w in t2._fill(lambda x, y: True, (-3.6, -3.6, 3.6, 3.6), 18, rng):
            card.append(("mark", 0.95, -39.0 + x, 0.8, w))
        for m in _words(rng, CARD_ENDS[row] + 30.0, n - 66):
            card.append(("text", 1.15, -30.0 + m, rng.uniform(0.3, 1.2), rng.uniform(-2.6, 2.6)))
        pts += [(*_on_floor(g[2:], CARD_PLACES[row]), g[0], row, *g[1:]) for g in card]
    return pts


def _put_cube(pose, rec, d, lean=0.0, cube_y=CUBE_Y, bob=1.5):
    x, y, z = _turn(rec[0], rec[1] - cube_y, rec[2], 0.35 * d, lean)
    pose.put(x, y + cube_y + bob * sin(TAU * d / 4.0), z, rec[5])


# A: Review. The cards lie still, and the cube looks over them one at a time, far to near: it tips toward a card,
# and that card rises a little and tilts up toward the viewer, its words brightening, then settles back.
REVIEW_P = 1.9  # Seconds on each card.


def build_overlook3_a(grains, rng):
    return dp._by_angle(_cards(grains, rng))


def eval_overlook3_a(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.15 + 0.06 * sin(TAU * d / 10.0), -0.55, span=44.0)
    c = (d / REVIEW_P + 2.6) % 3.0
    looks = []
    for row in range(3):
        g = (c - row - 0.5 + 1.5) % 3.0 - 1.5  # How far the look is from this card, in cards.
        looks.append(max(0.0, cos(math.pi * g / 1.6)) ** 2)
    lean = 0.22 * sum(g * (row - 1) for row, g in enumerate(looks))
    for rec in points:
        if rec[4] < 0:
            _put_cube(pose, rec, d, lean)
            continue
        g = looks[rec[4]]
        pose.put(*_on_floor(rec[6:], CARD_PLACES[rec[4]], 5.0 * g, 0.38 * g),
                 rec[5] * (1.0 + 0.22 * g * (rec[3] != "edge")))
    return pose.out()


# B: Cycle. The cards come on toward the viewer one place at a time, as threads take turns. The near card rises and
# tumbles back over the others to the far place, turning over once, so all three always show and its words dim
# while they face away. The cube turns above.
CYCLE_P, CYCLE_MOVE, CYCLE_ARC = 2.6, 1.3, 30.0  # One step; the move's length; the arc's height.


def build_overlook3_b(grains, rng):
    return dp._by_angle(_cards(grains, rng))


def eval_overlook3_b(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.15 + 0.06 * sin(TAU * d / 10.0), -0.55, span=44.0)
    n, ph = divmod(d + 0.6, CYCLE_P)
    e = _smooth((ph - CYCLE_P + CYCLE_MOVE) / CYCLE_MOVE)
    places = []
    for row in range(3):
        p = (row + int(n)) % 3  # Its place now: 0 far, 2 near.
        if p < 2:
            places.append((CARD_PLACES[p] + (CARD_PLACES[p + 1] - CARD_PLACES[p]) * e, 0.0, 0.0))
        else:  # Back over the top, turning over once about its long axis.
            places.append((CARD_PLACES[2] + (CARD_PLACES[0] - CARD_PLACES[2]) * e, CYCLE_ARC * sin(math.pi * e),
                           -TAU * e))
    for rec in points:
        if rec[4] < 0:
            _put_cube(pose, rec, d)
            continue
        z0, lift, tilt = places[rec[4]]
        pose.put(*_on_floor(rec[6:], z0, lift, tilt), rec[5] * (0.2 + 0.8 * (0.5 + 0.5 * cos(tilt))) ** 2)
    return pose.out()


# C: Tiers. The cards stand on three rising steps, tipped up toward the viewer, so every line reads. Each thread's
# line of words runs slowly along its card at its own pace, as threads run on, and the cube turns above the top step.
TIER_TILT, TIER_RISE, TIER_SPEEDS, TIER_CUBE_Y = 0.5, 11.0, (3.2, 4.6, 3.8), -46.0


def build_overlook3_c(grains, rng):
    return dp._by_angle(_cards(grains, rng, TIER_CUBE_Y))


def eval_overlook3_c(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.15 + 0.06 * sin(TAU * d / 10.0), -0.45, span=44.0)
    for rec in points:
        row = rec[4]
        if row < 0:
            _put_cube(pose, rec, d, cube_y=TIER_CUBE_Y)
            continue
        lift, b, card, gate = TIER_RISE * (2 - row) - 8.0, rec[5], rec[6:], False
        if rec[3] == "text":  # The line runs left along its card, and its words come round from the right end.
            length = CARD_ENDS[row] + 30.0
            s = (card[0] + 30.0 - TIER_SPEEDS[row] * d) % length
            b *= _smooth(s / 5.0) * _smooth((length - s) / 5.0)
            card, gate = (s - 30.0, *card[1:]), True
        pose.put(*_on_floor(card, CARD_PLACES[row] * 0.8, lift, TIER_TILT), b, gate=gate)
    return pose.out()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# D: Field, straight (the owner, 2026-11-27). v2's Field with the view held still, facing the rows: no side-to-side sway.
# The rows still come on toward the viewer and the cube still turns above them.
def build_overlook3_d(grains, rng):
    return t2.build_overlook2_b(grains, rng)


def eval_overlook3_d(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, 0.0, -0.62, span=46.0)
    spin = 0.45 * d
    for rec in points:
        kind = rec[3]
        if kind == "cube":
            x, y, z = _turn(rec[0], rec[1] - t2.FIELD_CUBE_Y, rec[2], spin)
            pose.put(x, y + t2.FIELD_CUBE_Y - 2.0 * sin(TAU * d / 3.6), z, rec[4])
            continue
        row = rec[4]
        z0 = -t2.FIELD_DEEP / 2 + t2.FIELD_DEEP * (row + 0.5) / 3
        z = (z0 + t2.FIELD_SPEED * d + t2.FIELD_DEEP / 2) % t2.FIELD_DEEP - t2.FIELD_DEEP / 2
        fade = _smooth((z + t2.FIELD_DEEP / 2) / 18.0) * _smooth((t2.FIELD_DEEP / 2 - z) / 18.0)
        if kind == "mark":
            pose.put(-44.0 + rec[5], t2.FIELD_FLOOR, z + rec[6], 1.05 * fade, gate=True)
        else:
            pose.put(rec[0], t2.FIELD_FLOOR, z + rec[7], 1.15 * fade, gate=True)
    return pose.out()


FORMS = ("prompt3_b", "globe3_a", "globe3_b", "globe3_c", "message3_a", "overlook3_a", "overlook3_b", "overlook3_c", "overlook3_d")
BUILDERS = {name: globals()[f"build_{name}"] for name in FORMS}
EVAL = {name: globals()[f"eval_{name}"] for name in FORMS}
NAMES = {"prompt3_b": "Glyph", "globe3_a": "Lens", "globe3_b": "Unfold", "globe3_c": "Results", "message3_a": "Ink",
         "overlook3_a": "Review", "overlook3_b": "Cycle", "overlook3_c": "Tiers", "overlook3_d": "Field straight"}


def extend(eval_targets):
    """devs_pack.eval_targets with these forms' own evaluators in front of it."""
    def with_tools(name, points, scene, now):
        own = EVAL.get(name)
        return own(name, points, scene, now) if own else eval_targets(name, points, scene, now)
    return with_tools


if __name__ == "__main__":
    # Each concept has the Devs grain count and a manifest entry, finite targets, no grain past the bright cap, and
    # stays inside the Devs form box over 12 s. Glyph's sway stays within 15 degrees.
    # Run it as scripts/capped /usr/bin/python desktop/icons_tools3.py
    import random
    import types

    import icons_tools3 as tools  # The registered module, as devs_pack loaded it.

    assert abs(GLYPH_YAW) + GLYPH_SWAY <= math.radians(15.0)
    trouble = []
    for name in tools.BUILDERS:
        pts = tools.BUILDERS[name](640, random.Random(sum(map(ord, name))))
        assert len(pts) == 640, (name, len(pts))
        assert name in dp.FORMS_META, f"{name} has no manifest entry"
        box, top = [0.0, 0.0, 0.0, 0.0], 0.0
        for k in range(360):
            tx, ty, tb, tz = dp.eval_targets(name, pts, types.SimpleNamespace(form_at=0.0), k / 30.0)
            assert len(tx) == 640 and all(map(math.isfinite, tx + ty + tb + tz)), (name, k)
            top = max(top, *tb)
            lit = [(x, y) for x, y, b in zip(tx, ty, tb) if b > 0.05]
            box = [min(box[0], *(x for x, _ in lit)), max(box[1], *(x for x, _ in lit)),
                   min(box[2], *(y for _, y in lit)), max(box[3], *(y for _, y in lit))]
        print(f"{name:12s} x {box[0]:6.1f} .. {box[1]:5.1f}   y {box[2]:6.1f} .. {box[3]:5.1f}   bright {top:.2f}")
        if not (-72 < box[0] and box[1] < 72 and -66 < box[2] and box[3] < 64) or top > 2.0:
            trouble.append(name)
    assert not trouble, f"outside the form box or too bright: {trouble}"
    print("ok")
