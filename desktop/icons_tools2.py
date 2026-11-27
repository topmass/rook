"""Devs 3D concepts for the daily tool icons, round two: prompt (Bash), globe (web), message (a thread's messages),
overlook (the threads and projects) and book (memory). Each icon has three candidates, named <icon>2_a, _b and _c.
They are design candidates only: ACTIVITY_FORMS still maps every tool to its old form, so none of them shows live.

Each concept moves by its own idea, in Devs dust: grains that flow, gather, part, stream and settle. No form has a
glowing bead or a roving point. The overlay's own spring morph carries the grains in from the resting loop and back.

devs_pack registers BUILDERS and EVAL in one line at its end, so overlay treats a candidate like any other Devs form.
Import this module only through devs_pack. A record starts (x, y, z, kind): the grain's place at arrival, which the
sort by angle uses, and its part. The numbers after those are the part's own. Every form has 640 grains and stays in
the Devs form box, about 120 px wide and 100 px high. Every loop closes with no seam.
"""

from __future__ import annotations

import math

import devs_pack as dp

TAU = 2.0 * math.pi
sin, cos, exp = math.sin, math.cos, math.exp
_smooth, _ease_back = dp._smooth, dp._ease_back


# Each form's scale, so it stands about 105 px high or 120 px wide on screen, as the rook and Today's icons do.
FIT = {"prompt2_a": 1.15, "prompt2_b": 1.15, "prompt2_c": 1.1, "globe2_a": 1.12, "globe2_b": 1.05, "globe2_c": 1.12,
       "message2_a": 1.15, "message2_b": 1.15, "message2_c": 1.05, "overlook2_a": 1.1, "overlook2_b": 0.95,
       "overlook2_c": 1.1, "book2_a": 1.0, "book2_b": 1.05, "book2_c": 0.95}


def _age(scene, now):
    return max(0.0, now - scene.form_at)


class _Pose:
    """Projects a form's grains for one frame: the view's yaw and pitch, perspective, and depth shade. A gated grain
    lights only near its place, so a grain that flies back dark to the start of its stream never shows on the way.
    The gate waits until the morph from the loop has landed. FIT scales each form to the rook's size."""

    def __init__(self, name, scene, now, yaw, pitch, span=44.0, persp=320.0):
        self.v = (cos(yaw), sin(yaw), cos(pitch), sin(pitch))
        self.persp, self.k = persp, FIT.get(name, 1.0)
        self.span = span * self.k
        formed = now - getattr(scene, "form_at", 0.0) > 1.4
        self.xs, self.ys = (getattr(scene, "x", None), getattr(scene, "y", None)) if formed else (None, None)
        self.tx, self.ty, self.tb, self.tz = [], [], [], []

    def put(self, x, y, z, b, gate=False, back=1.0):
        """back: the share of brightness a grain keeps on the far side of the form."""
        k = self.k
        x1, y2, z2 = dp._rot_yx(x * k, y * k, z * k, *self.v)
        p = 1.0 / (1.0 - z2 / self.persp)
        bd, zn = dp._depth_shade(z2, self.span)
        gx, gy = x1 * p, y2 * p
        if back < 1.0:
            b *= back + (1.0 - back) * _smooth(0.5 + z2 / (12.0 * k))
        if gate and self.xs is not None and self.ys is not None:
            i = len(self.tx)
            if i < len(self.xs):
                b *= max(0.0, 1.0 - max(0.0, abs(self.xs[i] - gx) + abs(self.ys[i] - gy) - 6.0) / 6.0)
        self.tx.append(gx)
        self.ty.append(gy)
        self.tb.append(bd * max(0.0, b))
        self.tz.append(zn)

    def out(self):
        return self.tx, self.ty, self.tb, self.tz


def _turn(x, y, z, yaw=0.0, pitch=0.0):
    """A point turned by its own yaw, then pitch: a part that turns apart from the view."""
    cy, sy = cos(yaw), sin(yaw)
    x, z = x * cy + z * sy, z * cy - x * sy
    cp, sp = cos(pitch), sin(pitch)
    return x, y * cp - z * sp, y * sp + z * cp


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

def _lengths(path):
    return [math.dist(p, q) for p, q in zip(path, path[1:])]


def _along(path, s, seg=None):
    """The point a share s of the way along a polyline, and the unit direction there."""
    seg = seg or _lengths(path)
    left = min(1.0, max(0.0, s)) * sum(seg)
    for i, length in enumerate(seg):
        if left <= length or i == len(seg) - 1:
            f = left / length if length else 0.0
            p, q = path[i], path[i + 1]
            return tuple(a + (b - a) * f for a, b in zip(p, q)), tuple((b - a) / (length or 1.0) for a, b in zip(p, q))
        left -= length


def _inside(poly, x, y):
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def _fill(test, box, n, rng):
    """n points spread evenly over a 2D region: a jittered grid inside test(x, y), thinned at random to n."""
    x0, y0, x1, y1 = box
    step = math.sqrt((x1 - x0) * (y1 - y0) / (n * 1.6))
    while True:
        out = []
        y = y0 + step / 2
        while y < y1:
            x = x0 + step / 2
            while x < x1:
                px, py = x + rng.uniform(-0.35, 0.35) * step, y + rng.uniform(-0.35, 0.35) * step
                if test(px, py):
                    out.append((px, py))
                x += step
            y += step
        if len(out) >= n:
            rng.shuffle(out)
            return out[:n]
        step *= 0.85


def _rrect(cx, cy, w, h, r, steps=6):
    """A rounded rectangle's outline, clockwise from the top edge's right end (no repeated first point)."""
    out = []
    for qx, qy, a0 in ((w / 2 - r, -h / 2 + r, -math.pi / 2), (w / 2 - r, h / 2 - r, 0.0),
                       (-w / 2 + r, h / 2 - r, math.pi / 2), (-w / 2 + r, -h / 2 + r, math.pi)):
        for k in range(steps + 1):
            a = a0 + (math.pi / 2) * k / steps
            out.append((cx + qx + r * cos(a), cy + qy + r * sin(a)))
    return out


def _bubble(cx, cy, w, h, r, tail):
    """A speech bubble's outline: a rounded rectangle with a tail on its bottom edge. tail is the tail base's right
    and left x, and its tip."""
    rect = _rrect(cx, cy, w, h, r)
    cut = 2 * 7  # After the bottom-right corner: the bottom edge runs right to left from here.
    xr, xl, tip = tail
    return rect[:cut] + [(cx + xr, cy + h / 2), tip, (cx + xl, cy + h / 2)] + rect[cut:]


def _slab(pts, outline, depth, n, rng, kind, face=0.55, extra=()):
    """A solid flat shape with thickness: grains over its front face, round its side wall, and a few on its back.
    outline is a closed 2D polygon; the face is at z = depth / 2."""
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    n_face = round(n * face)
    n_wall = round(n * (1.0 - face) * 0.8)
    for x, y in _fill(lambda x, y: _inside(outline, x, y), (min(xs), min(ys), max(xs), max(ys)), n_face, rng) \
            if n_face else ():
        pts.append((x, y, depth / 2, kind, 1.0, *extra))
    loop = outline + outline[:1]
    seg = _lengths(loop)
    for k in range(n_wall):
        (x, y), _ = _along(loop, (k + rng.random()) / n_wall, seg)
        pts.append((x, y, rng.uniform(-depth / 2, depth / 2), kind, 0.8, *extra))
    for k in range(n - n_face - n_wall):
        (x, y), _ = _along(loop, (k + rng.random()) / (n - n_face - n_wall), seg)
        pts.append((x, y, -depth / 2, kind, 0.6, *extra))


def _chevron(p0, p1, p2, h):
    """The outline of a chevron stroke of half-width h, mitred at p1."""
    def unit(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        return dx / length, dy / length
    u1, u2 = unit(p0, p1), unit(p1, p2)
    n1, n2 = (-u1[1], u1[0]), (-u2[1], u2[0])
    k = h / (1.0 + n1[0] * n2[0] + n1[1] * n2[1])
    m = (n1[0] + n2[0], n1[1] + n2[1])
    return [(p0[0] + h * n1[0], p0[1] + h * n1[1]), (p1[0] + k * m[0], p1[1] + k * m[1]),
            (p2[0] + h * n2[0], p2[1] + h * n2[1]), (p2[0] - h * n2[0], p2[1] - h * n2[1]),
            (p1[0] - k * m[0], p1[1] - k * m[1]), (p0[0] - h * n1[0], p0[1] - h * n1[1])]


def _cube(pts, half, n, rng, kind):
    """A solid cube of side 2 * half at the origin: its twelve edges dense, its six faces lightly dusted."""
    corners = [(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    edges = [(a, b) for a in range(8) for b in range(a + 1, 8) if sum(u != v for u, v in zip(corners[a], corners[b])) == 1]
    n_edge = round(n * 0.66)
    for k in range(n_edge):
        e, f = divmod((k + rng.random()) / n_edge * 12.0, 1.0)
        a, b = corners[edges[int(e)][0]], corners[edges[int(e)][1]]
        pts.append((*(half * (p + (q - p) * f) + rng.gauss(0, 0.3) for p, q in zip(a, b)), kind, 1.05))
    for k in range(n - n_edge):
        axis, side = k % 3, (1 if k % 6 < 3 else -1)
        u, v = rng.uniform(-0.85, 0.85), rng.uniform(-0.85, 0.85)
        p = [u, v]
        p.insert(axis, side)
        pts.append((*(half * c for c in p), kind, 0.42))


def _words(rng, length, n):
    """n material places over [0, length): words of dust with gaps, as Rook's lines of text read."""
    return dp._read_words(rng, 0.0, length, n)


# ---------------------------------------------------------------------------
# prompt: running a command (Bash)
# ---------------------------------------------------------------------------

# A: Typed. A solid chevron, and the command line typed into existence: each word of dust gathers out of a faint
# drifting cloud. The line runs (the chevron kicks), and every line rises one row and slides to the margin, receding
# into depth as output. The top row lifts away as loose dust, and its grains come back dark as the next cloud.
TYPE_P, TYPE_START, TYPE_SPAN, TYPE_RUN, TYPE_RISE = 3.0, 0.15, 1.3, 2.0, 0.8
TYPE_ROW, TYPE_DEEP, TYPE_Y, TYPE_X, TYPE_MARGIN = 20.0, 12.0, 24.0, -24.0, -52.0
TYPE_LINES, TYPE_ENDS = 4, (44.0, 26.0, 50.0, 36.0)
TYPE_TOP = TYPE_LINES - 2  # The highest output row; above it a row lifts away, then flies back dark.
TYPE_CHEVRON = _chevron((-54.0, 10.0), (-35.0, 24.0), (-54.0, 38.0), 4.4)
TYPE_LEAD = 0.55  # The first cycle starts this long after the form, so the morph lands before the typing.


def build_prompt2_a(grains, rng):
    pts = []
    _slab(pts, TYPE_CHEVRON, 9.0, 170, rng, "chev")
    left = grains - len(pts)
    for j in range(TYPE_LINES):
        n = left // TYPE_LINES + (1 if j < left % TYPE_LINES else 0)
        length = TYPE_ENDS[j] - TYPE_X
        age = min(TYPE_TOP, (-1 - j) % TYPE_LINES)  # Its row as the form arrives.
        for x in _words(rng, length, n):
            pts.append((TYPE_X + x + (TYPE_MARGIN - TYPE_X) * min(age, 1), TYPE_Y - TYPE_ROW * age, 0.0, "line",
                        j, x, x / length, rng.gauss(0, 3.0), rng.gauss(-1.5, 2.4), rng.random(), rng.gauss(0, 0.9)))
    return dp._by_angle(pts)


def eval_prompt2_a(name, points, scene, now):
    d = _age(scene, now)
    n, ph = divmod(d - TYPE_LEAD, TYPE_P)
    n, run = int(n), ph - TYPE_RUN
    pose = _Pose(name, scene, now, -0.30 + 0.14 * sin(TAU * d / 8.0), -0.12, span=40.0)
    flash = exp(-run / 0.25) if run >= 0.0 else 0.0
    drift = 0.9 * d
    for rec in points:
        if rec[3] == "chev":
            pose.put(rec[0] + 2.5 * flash, rec[1], rec[2], rec[4] * (1.05 + 0.5 * flash))
            continue
        j, x, f, ox, oy, lag, h = rec[4:]
        age = (n - j) % TYPE_LINES
        A = age + (_smooth((run - 0.2 * lag) / TYPE_RISE) if run > 0.0 else 0.0)
        a = drift + 7.0 * f
        cx, cy = TYPE_X + x + ox * cos(a) - oy * sin(a), TYPE_Y + 0.6 * ox * sin(a) + oy * cos(a)  # Its cloud place.
        if A >= TYPE_TOP + 1:  # Dark on its way back, then the faint cloud as the old line rises.
            pose.put(cx, cy, 0.0, 0.1 * (A - TYPE_TOP - 1), gate=True)
            continue
        top = min(A, TYPE_TOP)
        gx = TYPE_X + x + (TYPE_MARGIN - TYPE_X) * min(A, 1.0)
        gy, gz, b = TYPE_Y - TYPE_ROW * top + h, -TYPE_DEEP * top, 1.25 - 0.15 * top
        if age == 0:
            k = _smooth((ph - TYPE_START - TYPE_SPAN * f) / 0.25)  # Gathers out of the cloud as it is typed.
            gx, gy = cx + (gx - cx) * k, cy + (gy - cy) * k
            b = 0.1 + (b + 0.45 * flash - 0.1) * k
        elif A > TYPE_TOP:  # The top row lifts away as loose dust.
            u = A - TYPE_TOP
            gx += 1.4 * ox * u
            gy += -18.0 * u + oy * u - 10.0 * u * u * lag
            gz -= 10.0 * u
            b *= (1.0 - u) ** 2
        pose.put(gx, gy, gz, b)
    return pose.out()


# B: Glyph. The prompt itself, ">_", as bold solid letters with depth. They turn slowly to show it, and the dust in
# their faces flows along each stroke: down both arms into the chevron's point, and on along the cursor.
GLYPH_ENDS, GLYPH_TIP, GLYPH_HALF = ((-48.0, -30.0), (-48.0, 30.0)), (-12.0, 0.0), 7.5
GLYPH_BAR, GLYPH_BAR_HALF = (2.0, 46.0, 28.0), 6.0
GLYPH_DEEP, GLYPH_FLOW, GLYPH_OVER = 14.0, 9.0, 1.14  # Depth; flow in px/s; how far an arm runs past the point.


def build_prompt2_b(grains, rng):
    pts = []
    arm = math.dist(GLYPH_ENDS[0], GLYPH_TIP)
    for side, end in zip((-1, 1), GLYPH_ENDS):  # Each arm's face: (side, share along, offset across, length).
        for k in range(110):
            u, w = GLYPH_OVER * (k + rng.random()) / 110, rng.uniform(-GLYPH_HALF, GLYPH_HALF)
            pts.append((end[0] + (GLYPH_TIP[0] - end[0]) * u, end[1] * (1.0 - u), GLYPH_DEEP / 2, "face", side, u, w,
                        arm))
    x0, x1, y = GLYPH_BAR
    for k in range(150):
        pts.append((x0 + (x1 - x0) * (k + 0.5) / 150, y, GLYPH_DEEP / 2, "face", 0, (k + rng.random()) / 150,
                    rng.uniform(-GLYPH_BAR_HALF, GLYPH_BAR_HALF), x1 - x0))
    bar = [(x0, y - GLYPH_BAR_HALF), (x1, y - GLYPH_BAR_HALF), (x1, y + GLYPH_BAR_HALF), (x0, y + GLYPH_BAR_HALF)]
    walls = []
    _slab(walls, _chevron(GLYPH_ENDS[0], GLYPH_TIP, GLYPH_ENDS[1], GLYPH_HALF), GLYPH_DEEP, 160, rng, "wall", face=0.0)
    _slab(walls, bar, GLYPH_DEEP, grains - len(pts) - len(walls), rng, "wall", face=0.0)
    return dp._by_angle(pts + walls)


def eval_prompt2_b(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.15 + 0.5 * sin(TAU * d / 7.0), -0.12, span=40.0)
    tx_, ty_ = GLYPH_TIP
    for rec in points:
        if rec[3] == "wall":
            pose.put(rec[0], rec[1], rec[2], rec[4])
            continue
        side, u, w, length = rec[4:]
        span = GLYPH_OVER if side else 1.0
        s = (u + GLYPH_FLOW * d / length) % span
        b = 1.15 * _smooth((s - 0.06) / 0.08) * _smooth((span - s) / 0.05)  # Dark at first, while it flies back.
        if side:
            ex, ey = GLYPH_ENDS[0 if side < 0 else 1]
            dx, dy = (tx_ - ex) / length, (ty_ - ey) / length
            x, y = ex + (tx_ - ex) * s - dy * w, ey + (ty_ - ey) * s + dx * w
        else:
            x0, x1, y0 = GLYPH_BAR
            x, y = x0 + (x1 - x0) * s, y0 + w
        pose.put(x, y, GLYPH_DEEP / 2, b, gate=True)
    return pose.out()


# C: Console. A solid screen, leaning back, with the prompt on its bottom line. Its output streams steadily up the
# face, and each line that reaches the top lifts off the screen as loose dust.
CONSOLE_W, CONSOLE_H, CONSOLE_R, CONSOLE_DEEP, CONSOLE_LEAN = 104.0, 82.0, 9.0, 10.0, 0.3
CONSOLE_ROWS, CONSOLE_GAP, CONSOLE_SPEED = 5, 12.5, 5.0
CONSOLE_FROM, CONSOLE_TOP = 14.0, -28.0  # Where output fades in above the prompt line, and where it lifts off.
CONSOLE_PROMPT = ((-44.0, 22.0), (-36.0, 28.0), (-44.0, 34.0))


def build_prompt2_c(grains, rng):
    pts = []
    _slab(pts, _rrect(0.0, 0.0, CONSOLE_W, CONSOLE_H, CONSOLE_R), CONSOLE_DEEP, 200, rng, "screen", face=0.18)
    seg = _lengths(CONSOLE_PROMPT)
    for k in range(34):
        (x, y), _ = _along(CONSOLE_PROMPT, (k + rng.random()) / 34, seg)
        pts.append((x, y + rng.gauss(0, 0.6), CONSOLE_DEEP / 2 + 0.5, "prompt", 1.3))
    for x in _words(rng, 34.0, 46):
        pts.append((-30.0 + x, 28.0 + rng.gauss(0, 0.6), CONSOLE_DEEP / 2 + 0.5, "prompt", 1.2))
    left = grains - len(pts)
    for j in range(CONSOLE_ROWS):
        n = left // CONSOLE_ROWS + (1 if j < left % CONSOLE_ROWS else 0)
        length = (82.0, 60.0, 74.0, 50.0, 86.0)[j]
        for x in _words(rng, length, n):
            pts.append((-44.0 + x, CONSOLE_FROM - CONSOLE_GAP * j, CONSOLE_DEEP / 2 + 0.5, "row", j, x,
                        rng.gauss(0, 3.0), rng.gauss(0, 0.6), rng.random()))
    return dp._by_angle(pts)


def eval_prompt2_c(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.36 + 0.14 * sin(TAU * d / 8.0), -0.16, span=40.0)
    run = CONSOLE_GAP * CONSOLE_ROWS
    for rec in points:
        kind = rec[3]
        if kind != "row":
            look = rec[4] * (0.35 if kind == "screen" and rec[4] > 0.9 else 1.0)
            pose.put(*_turn(rec[0], rec[1], rec[2], 0.0, CONSOLE_LEAN), look)
            continue
        j, x, spread, h, lag = rec[4:]
        y = CONSOLE_FROM - (CONSOLE_GAP * j + CONSOLE_SPEED * d) % run
        lift = _smooth((CONSOLE_TOP - y) / 16.0)
        b = 1.15 * _smooth((CONSOLE_FROM - y - 4.0) / 6.0) * (1.0 - lift) ** 2
        gx, gy = -44.0 + x + spread * lift, y + h - 4.0 * lift * (1.0 + lag)
        pose.put(*_turn(gx, gy, CONSOLE_DEEP / 2 + 0.5 + 14.0 * lift, 0.0, CONSOLE_LEAN), b, gate=True)
    return pose.out()


# ---------------------------------------------------------------------------
# globe: searching and fetching the web
# ---------------------------------------------------------------------------

GLOBE_R = 46.0


def _sphere(lon, lat, r=GLOBE_R):
    return r * cos(lat) * cos(lon), -r * sin(lat), r * cos(lat) * sin(lon)


def _fib(n):
    """n even places on a sphere, as (lon, lat)."""
    out = []
    for k in range(n):
        y = 1.0 - 2.0 * (k + 0.5) / n
        out.append(((2.39996 * k) % TAU, math.asin(y)))
    return out


# A: Currents. A turning Earth: continents of dense dust on a faint sea, and two jet streams of word-dust that
# meander round it a little above the land, flowing east faster than the globe turns.
EARTH_LAND = ((-1.65, 0.75, 0.42), (-1.45, 0.3, 0.3), (-1.05, -0.2, 0.32), (-1.0, -0.6, 0.26), (0.25, 0.85, 0.28),
              (0.35, 0.12, 0.42), (0.5, -0.42, 0.3), (1.5, 0.85, 0.5), (1.95, 0.4, 0.36), (1.75, 1.15, 0.3),
              (2.4, -0.45, 0.26))
EARTH_SPIN, EARTH_WIND = 0.22, 0.12
EARTH_STREAMS = ((0.62, 0.0), (-0.5, 2.0))  # Each jet stream's latitude and meander phase.


def _land(lon, lat):
    for blon, blat, size in EARTH_LAND:
        c = sin(lat) * sin(blat) + cos(lat) * cos(blat) * cos(lon - blon)
        edge = size * (1.0 + 0.22 * sin(5.0 * lon + 3.0 * lat) + 0.12 * sin(11.0 * lat - 2.0 * lon))
        if math.acos(max(-1.0, min(1.0, c))) < edge:
            return True
    return False


def build_globe2_a(grains, rng):
    pts = []
    land = [p for p in _fib(1400) if _land(*p)]
    sea = [p for p in _fib(400) if not _land(*p)]
    for kind, places, n in (("land", land, 290), ("sea", sea, 130)):
        for k in range(n):  # Evenly through the list, which runs pole to pole.
            lon, lat = places[k * len(places) // n]
            pts.append((*_sphere(lon, lat), kind, lon, lat))
    left = grains - len(pts)
    for i, (lat0, ph0) in enumerate(EARTH_STREAMS):
        n = left // 2 + (left % 2 if i == 0 else 0)
        for m in _words(rng, TAU, n):
            pts.append((*_sphere(m, lat0), "wind", m, lat0, ph0, rng.gauss(0, 0.012)))
    return dp._by_angle(pts)


def eval_globe2_a(name, points, scene, now):
    d = _age(scene, now)
    spin = EARTH_SPIN * d
    pose = _Pose(name, scene, now, 0.0, -0.38, span=GLOBE_R)
    for rec in points:
        kind = rec[3]
        if kind == "wind":
            m, lat0, ph0, j = rec[4:]
            lon = m + EARTH_WIND * d * (1.0 if lat0 > 0 else 1.3)
            lat = lat0 + 0.16 * sin(3.0 * lon + ph0) + j
            x, y, z = _sphere(lon, lat, GLOBE_R + 3.5)
            x, y, z = _turn(x, y, z, spin)
            pose.put(x, y, z, 1.05, back=0.3)
            continue
        x, y, z = _turn(*rec[:3], spin)
        pose.put(x, y, z, 1.15 if kind == "land" else 0.45, back=0.35)
    return pose.out()


# B: Fetch. A turning globe of meridians and parallels. A patch of its face peels away as a page of text, floats out
# toward the viewer, holds, and sinks back into the globe: a page fetched from the web.
FETCH_P, FETCH_SPIN, FETCH_OUT = 5.2, 0.25, 26.0  # The loop; the globe's turn; how far out in front the page floats.
FETCH_W, FETCH_ROWS = 20.0, (-20.0, -10.0, 0.0, 10.0, 20.0)  # The page's half width, and its lines.
FETCH_LON, FETCH_LAT = 0.5, 0.45  # The patch's half width in longitude, and half height in latitude, on the globe.


def build_globe2_b(grains, rng):
    pts = []
    for lat, n in ((0.0, 88), (0.7, 60), (-0.7, 60)):
        for k in range(n):
            lon = TAU * (k + rng.uniform(-0.2, 0.2)) / n
            pts.append((*_sphere(lon, lat), "grid", 1.0))
    for lon0 in (0.0, math.pi / 3, 2 * math.pi / 3):
        for k in range(68):
            a = TAU * (k + rng.uniform(-0.2, 0.2)) / 68
            pts.append((*_turn(GLOBE_R * cos(a), GLOBE_R * sin(a), 0.0, lon0), "grid", 0.9))
    left = grains - len(pts)
    for row, y in enumerate(FETCH_ROWS):
        end = FETCH_W if row < len(FETCH_ROWS) - 1 else 0.0
        n = round(left * 2 * FETCH_W / (9 * FETCH_W)) if row < len(FETCH_ROWS) - 1 else grains - len(pts)
        for x in _words(rng, end + FETCH_W, n):
            pts.append((-FETCH_W + x, y, GLOBE_R, "page", -FETCH_W + x, y + rng.gauss(0, 0.5), rng.random()))
    return dp._by_angle(pts)


def eval_globe2_b(name, points, scene, now):
    d = _age(scene, now)
    ph = (d - 0.6) % FETCH_P
    spin = FETCH_SPIN * d
    pose = _Pose(name, scene, now, 0.0, -0.3, span=GLOBE_R)
    for rec in points:
        if rec[3] == "grid":
            pose.put(*_turn(*rec[:3], spin), 0.85 * rec[4], back=0.3)
            continue
        px, py, lag = rec[4:]
        # Out with a small overshoot, a hold, then back; each grain a touch apart, so the page peels and settles.
        k = _ease_back((ph - 0.5 - 0.3 * lag) / 0.9, 1.1) * (1.0 - _smooth((ph - 3.4 - 0.3 * lag) / 1.0))
        lon, lat = px / FETCH_W * FETCH_LON, -py / FETCH_ROWS[-1] * FETCH_LAT
        sx, sy, sz = GLOBE_R * cos(lat) * sin(lon), -GLOBE_R * sin(lat), GLOBE_R * cos(lat) * cos(lon)  # On the face.
        lift = sin(math.pi * min(1.0, max(0.0, k))) * 6.0  # It bows out a little on the way.
        pose.put(sx + (px - sx) * k, sy + (py - sy) * k, sz + (GLOBE_R + FETCH_OUT - sz) * k + lift,
                 0.7 + 0.55 * min(1.0, max(0.0, k)))
    return pose.out()


# C: Weave. The globe's own lines are the motion: dashes of dust run east along the parallels, each against its
# neighbour, and pole to pole along the meridians, as the globe turns, so the web's grid weaves itself.
WEAVE_SPIN = 0.2
WEAVE_LINES = ((0, 0.0, 112, 0.26), (0, 0.66, 84, -0.3), (0, -0.66, 84, -0.3),
               (1, 0.0, 120, 0.22), (1, math.pi / 3, 120, -0.22), (1, 2 * math.pi / 3, 120, 0.22))


def build_globe2_c(grains, rng):
    pts = []
    for line, (meridian, where, n, _) in enumerate(WEAVE_LINES):
        if line == len(WEAVE_LINES) - 1:
            n = grains - len(pts)
        for m in _words(rng, TAU, n):
            if meridian:
                x, y, z = _turn(GLOBE_R * cos(m), GLOBE_R * sin(m), 0.0, where)
            else:
                x, y, z = _sphere(m, where)
            pts.append((x, y, z, "line", line, m))
    return dp._by_angle(pts)


def eval_globe2_c(name, points, scene, now):
    d = _age(scene, now)
    spin = WEAVE_SPIN * d
    pose = _Pose(name, scene, now, 0.0, -0.36, span=GLOBE_R)
    for rec in points:
        line, m = rec[4:]
        meridian, where, _, speed = WEAVE_LINES[line]
        a = m + speed * d
        if meridian:
            x, y, z = _turn(GLOBE_R * cos(a), GLOBE_R * sin(a), 0.0, where)
        else:
            x, y, z = _sphere(a, where)
        pose.put(*_turn(x, y, z, spin), 1.05, back=0.32)
    return pose.out()


# ---------------------------------------------------------------------------
# message: reading or sending a coding thread's messages
# ---------------------------------------------------------------------------

BUBBLE_W, BUBBLE_H, BUBBLE_R, BUBBLE_CY, BUBBLE_T = 96.0, 58.0, 16.0, -8.0, 10.0
BUBBLE_TAIL = (-8.0, -28.0, (-42.0, 40.0))
BUBBLE_ROWS, BUBBLE_ENDS = (-22.0, -8.0, 6.0), (36.0, 30.0, 6.0)
BUBBLE_OUTLINE = _bubble(0.0, BUBBLE_CY, BUBBLE_W, BUBBLE_H, BUBBLE_R, BUBBLE_TAIL)

# A: Writing. A solid bubble. Its text comes in as a stream of dust through the tail, runs along each line, and
# settles into words. Once read, the lines lift off the face as loose dust, and the next message streams in.
WRITE_P, WRITE_START, WRITE_SPAN, WRITE_TRAVEL, WRITE_LIFT = 5.4, 0.25, 1.4, 1.6, 3.8


def build_message2_a(grains, rng):
    pts = []
    _slab(pts, BUBBLE_OUTLINE, BUBBLE_T, 330, rng, "bubble", face=0.3)
    left, x0 = grains - len(pts), -40.0
    total = sum(e - x0 for e in BUBBLE_ENDS)
    for row, (y, end) in enumerate(zip(BUBBLE_ROWS, BUBBLE_ENDS)):
        n = round(left * (end - x0) / total) if row < 2 else grains - len(pts)
        for x in _words(rng, end - x0, n):
            order = (row + x / (end - x0)) / len(BUBBLE_ROWS)
            pts.append((x0 + x, y, BUBBLE_T / 2 + 0.6, "text", row, x0 + x, order, rng.gauss(0, 2.4),
                        rng.gauss(0, 4.0), rng.random()))
    return dp._by_angle(pts)


def eval_message2_a(name, points, scene, now):
    d = _age(scene, now)
    ph = d % WRITE_P
    pose = _Pose(name, scene, now, -0.34 + 0.16 * sin(TAU * d / 7.5), -0.1, span=36.0)
    tip = BUBBLE_TAIL[2]
    z = BUBBLE_T / 2 + 0.6
    for rec in points:
        if rec[3] == "bubble":
            pose.put(rec[0], rec[1], rec[2], rec[4] * (0.95 if rec[4] < 0.9 else 0.32))
            continue
        row, x, order, w, spread, lag = rec[4:]
        y = BUBBLE_ROWS[row]
        s = (ph - WRITE_START - WRITE_SPAN * order) / WRITE_TRAVEL
        if s < 0.0:  # Waits dark at the tail's tip.
            pose.put(tip[0], tip[1], z, 0.0, gate=True)
            continue
        if s < 1.0:  # In through the tail, up into the bubble, and along the line.
            # Each grain bends at its own place, so the stream stays a broad band of dust and never bunches.
            path = (tip, (-22.0 + 2.0 * w, 14.0 + w), (-42.0 + w, y), (x, y))
            (gx, gy), (ux, uy) = _along(path, s)
            pose.put(gx - uy * w, gy + ux * w, z, 0.55 * _smooth((s - 0.03) / 0.15))
            continue
        u = _smooth((ph - WRITE_LIFT - 0.25 * row - 0.2 * lag) / 0.75)  # Read: the line lifts off as loose dust.
        pose.put(x + 0.4 * spread * u, y - 14.0 * u - abs(spread) * u, z + 8.0 * u,
                 (1.2 + 0.25 * exp(-(s - 1.0) * WRITE_TRAVEL / 0.3)) * (1.0 - u) ** 2)
    return pose.out()


# B: Pillow. A soft, round bubble with real volume, which breathes as a voice does. Its surface dust churns slowly
# round its middle. With each breath in, its lines of text gather out of the surface, and with each breath out they
# sink back into it.
PILLOW_A, PILLOW_B, PILLOW_C, PILLOW_CY = 48.0, 30.0, 13.0, -6.0
PILLOW_P, PILLOW_ROWS = 4.6, (-14.0, -1.0, 12.0)
PILLOW_TAIL = ((-24.0, 20.0), (-46.0, 42.0), (-8.0, 22.0))


def _pillow_z(x, y):
    rho = (abs(x) / PILLOW_A) ** 4 + (abs(y) / PILLOW_B) ** 4
    return PILLOW_C * math.sqrt(max(0.0, 1.0 - rho)) if rho < 1.0 else 0.0


def build_message2_b(grains, rng):
    pts = []
    test = lambda x, y: (abs(x) / PILLOW_A) ** 4 + (abs(y) / PILLOW_B) ** 4 < 1.0  # noqa: E731
    for x, y in _fill(test, (-PILLOW_A, -PILLOW_B, PILLOW_A, PILLOW_B), 160, rng):
        pts.append((x, y + PILLOW_CY, _pillow_z(x, y), "skin", 1.0, math.atan2(y / PILLOW_B, x / PILLOW_A),
                    math.hypot(x / PILLOW_A, y / PILLOW_B)))
    for x, y in _fill(test, (-PILLOW_A, -PILLOW_B, PILLOW_A, PILLOW_B), 60, rng):
        pts.append((x, y + PILLOW_CY, -_pillow_z(x, y), "skin", 0.6, math.atan2(y / PILLOW_B, x / PILLOW_A),
                    math.hypot(x / PILLOW_A, y / PILLOW_B)))
    for k in range(110):  # The rim, where the two faces meet: round its edge in depth too.
        a = TAU * (k + rng.random()) / 110
        c, s = cos(a), sin(a)
        rr = (c ** 4 + s ** 4) ** -0.25
        pts.append((PILLOW_A * c * rr, PILLOW_CY + PILLOW_B * s * rr, rng.uniform(-0.4, 0.4) * PILLOW_C * 0.5, "rim",
                    0.95, a, rr))
    (ax, ay), tip, (bx, by) = PILLOW_TAIL
    for k in range(50):  # The tail: a solid wedge.
        u, v = rng.random(), rng.random()
        if u + v > 1.0:
            u, v = 1.0 - u, 1.0 - v
        x, y = ax + (tip[0] - ax) * u + (bx - ax) * v, ay + (tip[1] - ay) * u + (by - ay) * v
        pts.append((x, y + PILLOW_CY, rng.uniform(-4.0, 4.0) * (1.0 - u), "tail", 0.95, 0.0, 0.0))
    left = grains - len(pts)
    for row, y in enumerate(PILLOW_ROWS):
        end = 30.0 if row < 2 else 6.0
        n = round(left * 64.0 / 168.0) if row < 2 else grains - len(pts)
        for x in _words(rng, end + 34.0, n):
            gx = -34.0 + x
            pts.append((gx, y + PILLOW_CY, _pillow_z(gx, y) + 0.8, "text", row, x / (end + 34.0), rng.random()))
    return dp._by_angle(pts)


def _breath(ph):
    """The breath: 0 out, 1 in, eased in fast with a small overshoot, out slowly."""
    return _ease_back(ph / 0.9, 1.2) * (1.0 - _smooth((ph - 3.0) / 1.3))


def eval_message2_b(name, points, scene, now):
    d = _age(scene, now)
    ph = d % PILLOW_P
    breath = _breath(ph)
    puff, wide = 0.55 + 0.45 * breath, 0.94 + 0.06 * breath
    churn = 0.16 * d
    pose = _Pose(name, scene, now, -0.42 + 0.18 * sin(TAU * d / 9.0), -0.16, span=30.0)
    for rec in points:
        kind = rec[3]
        if kind == "skin":
            a, rho = rec[5] + churn * (1.0 - 0.5 * rec[6]), rec[6]
            c, s = cos(a), sin(a)
            x, y = PILLOW_A * rho * c, PILLOW_B * rho * s
            z = _pillow_z(x, y) * (1.0 if rec[2] >= 0 else -1.0)
            pose.put(x * wide, PILLOW_CY + y * wide, z * puff, 0.36 * rec[4])
        elif kind in ("rim", "tail"):
            pose.put(rec[0] * wide, PILLOW_CY + (rec[1] - PILLOW_CY) * wide, rec[2] * puff, rec[4])
        else:
            row, f, lag = rec[4:]
            show = _smooth((ph - 0.35 - 0.3 * row - 0.6 * f) / 0.35) * (1.0 - _smooth((ph - 2.7 - 0.25 * row) / 0.7))
            x, y = rec[0], rec[1] - PILLOW_CY
            z = _pillow_z(x, y) * puff + 0.8 * show + 2.0 * (1.0 - show) * (lag - 0.5)
            pose.put(x * wide, PILLOW_CY + y * wide, z, 0.45 + 0.85 * show)
    return pose.out()



# C: Thread. A conversation: small solid bubbles one above another, from either side in turn. The thread drifts
# slowly up: the newest gathers out of dust at the foot, and the oldest lifts away as loose dust at the top.
THREAD_SLOTS, THREAD_P, THREAD_GAP = 4, 2.6, 28.0  # Bubbles; seconds for one to rise one place; the place's height.
THREAD_FOOT, THREAD_FORM = 42.0, 0.6  # The foot's height, and the share of a place spent gathering or lifting away.


def build_message2_c(grains, rng):
    pts = []
    per = grains // THREAD_SLOTS
    for slot in range(THREAD_SLOTS):
        side = 1 if slot % 2 else -1  # Right or left: the tail on the outer side.
        outline = [(-side * x, y) for x, y in _bubble(0.0, 0.0, 60.0, 22.0, 10.0, (-8.0, -18.0, (-27.0, 19.0)))]
        part = []
        n_text = 48 if slot < THREAD_SLOTS - 1 else grains - len(pts) - (per - 48)
        _slab(part, outline, 6.0, per - 48, rng, "bubble", face=0.15)
        for x in _words(rng, 38.0, n_text):
            part.append((-20.0 + x, rng.gauss(0, 0.6), 3.6, "text", 1.2))
        cx, cy = 12.0 * side, THREAD_FOOT - THREAD_GAP * min(3.0, slot + 0.5)
        pts += [(x + cx, y + cy, z, kind, look, slot, x, y, z, rng.gauss(0, 3.5), rng.gauss(0, 3.0), rng.random())
                for x, y, z, kind, look in part]
    return dp._by_angle(pts)


def eval_message2_c(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.3 + 0.14 * sin(TAU * d / 8.0), -0.1, span=36.0)
    top = THREAD_SLOTS - 1
    for rec in points:
        look, slot, x, y, z, sx, sy, lag = rec[4:]
        cx = 12.0 * (1 if slot % 2 else -1)
        look *= 0.3 if rec[3] == "bubble" and look > 0.9 else 1.0  # The face: faint, so the text reads on it.
        A = (d / THREAD_P + slot + 0.5) % THREAD_SLOTS  # Its place: 0 at the foot, 3 at the top, then dark.
        if A >= top:  # Gone: back to the foot unseen.
            pose.put(cx + x + sx, THREAD_FOOT + y + sy, z, 0.0, gate=True)
            continue
        loose = 1.0 - _smooth((A - 0.15 * lag) / THREAD_FORM) + _smooth((A - top + THREAD_FORM + 0.15 * lag) / THREAD_FORM)
        b = (1.15 - 0.4 * A / top) * (1.0 - min(1.0, loose))
        pose.put(cx + x + sx * loose, THREAD_FOOT - THREAD_GAP * A + y + sy * loose - 4.0 * max(0.0, A - 2.0) * loose,
                 z - 6.0 * A, look * b)
    return pose.out()


# ---------------------------------------------------------------------------
# overlook: looking over the coding threads (a cube above three rows, as the owner chose on 2026-11-22)
# ---------------------------------------------------------------------------

def _row_text(pts, rng, y, x0, x1, n, kind, row, z=0.0):
    for m in _words(rng, x1 - x0, n):
        pts.append((x0 + m, y, z, kind, row, m, x1 - x0, rng.gauss(0, 0.8)))


def _square(pts, cx, cy, half, n, rng, kind, row, z=0.0):
    for x, y in _fill(lambda x, y: True, (-half, -half, half, half), n, rng):
        pts.append((cx + x, cy + y, z, kind, row, x, y, 0.0))


# A: Lookout. A solid cube turns above three rows. Each row is a thread: a square mark and a line of word-dust that
# streams steadily to the right, each at its own pace, as threads run on.
LOOK_CUBE_Y, LOOK_HALF, LOOK_ROWS = -28.0, 14.0, (12.0, 28.0, 44.0)
LOOK_ENDS, LOOK_SPEEDS = (46.0, 32.0, 40.0), (6.0, 4.2, 7.5)


def build_overlook2_a(grains, rng):
    pts = []
    _cube(pts, LOOK_HALF, 230, rng, "cube")
    pts = [(x, y + LOOK_CUBE_Y, z, k, b) for x, y, z, k, b in pts]
    left = grains - len(pts)
    for row, (y, end) in enumerate(zip(LOOK_ROWS, LOOK_ENDS)):
        _square(pts, -44.0, y, 3.6, 22, rng, "mark", row)
        n = (left - 66) // 3 if row < 2 else grains - len(pts)
        _row_text(pts, rng, y, -34.0, end, n, "text", row)
    return dp._by_angle(pts)


def eval_overlook2_a(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.2 + 0.12 * sin(TAU * d / 9.0), -0.12, span=40.0)
    spin = 0.5 * d
    for rec in points:
        kind = rec[3]
        if kind == "cube":
            x, y, z = _turn(rec[0], rec[1] - LOOK_CUBE_Y, rec[2], spin, -0.55)
            pose.put(x, y + LOOK_CUBE_Y + 2.0 * sin(TAU * d / 3.2), z, rec[4])
        elif kind == "mark":
            pose.put(rec[0], rec[1], rec[2], 1.05)
        else:
            row, m, length, j = rec[4:]
            s = (m + LOOK_SPEEDS[row] * d) % length
            pose.put(-34.0 + s, LOOK_ROWS[row] + j, 0.0, 1.1 * _smooth((s - 3.0) / 5.0) * _smooth((length - s) / 5.0),
                     gate=True)
    return pose.out()


# B: Field. The three rows lie on a floor seen from above, and come on toward the viewer, one after another, the far
# one gathering out of the distance and the near one fading as it passes. The cube hovers over them and turns.
FIELD_FLOOR, FIELD_DEEP, FIELD_SPEED, FIELD_CUBE_Y = 30.0, 90.0, 9.0, -36.0


def build_overlook2_b(grains, rng):
    pts = []
    _cube(pts, 15.0, 250, rng, "cube")
    pts = [(x, y + FIELD_CUBE_Y, z, k, b) for x, y, z, k, b in pts]
    left = grains - len(pts)
    for row in range(3):
        z0 = -FIELD_DEEP / 2 + FIELD_DEEP * (row + 0.5) / 3
        _square(pts, -44.0, FIELD_FLOOR, 4.0, 22, rng, "mark", row, z0)
        n = (left - 66) // 3 if row < 2 else grains - len(pts)
        for m in _words(rng, 82.0, n):
            pts.append((-34.0 + m, FIELD_FLOOR, z0, "text", row, m, 0.0, rng.gauss(0, 0.5)))
    return dp._by_angle(pts)


def eval_overlook2_b(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.18 + 0.1 * sin(TAU * d / 9.0), -0.62, span=46.0)
    spin = 0.45 * d
    for rec in points:
        kind = rec[3]
        if kind == "cube":
            x, y, z = _turn(rec[0], rec[1] - FIELD_CUBE_Y, rec[2], spin)
            pose.put(x, y + FIELD_CUBE_Y - 2.0 * sin(TAU * d / 3.6), z, rec[4])
            continue
        row = rec[4]
        z0 = -FIELD_DEEP / 2 + FIELD_DEEP * (row + 0.5) / 3
        z = (z0 + FIELD_SPEED * d + FIELD_DEEP / 2) % FIELD_DEEP - FIELD_DEEP / 2
        fade = _smooth((z + FIELD_DEEP / 2) / 18.0) * _smooth((FIELD_DEEP / 2 - z) / 18.0)
        if kind == "mark":
            pose.put(-44.0 + rec[5], FIELD_FLOOR, z + rec[6], 1.05 * fade, gate=True)
        else:
            pose.put(rec[0], FIELD_FLOOR, z + rec[7], 1.15 * fade, gate=True)
    return pose.out()


# C: Shuffle. A solid cube turns above three rows, and the rows sort themselves: every two seconds two of them swap
# places, one sweeping forward and one back through depth, and settle with a small overshoot.
SHUFFLE_CUBE_Y, SHUFFLE_HALF, SHUFFLE_ROWS = -28.0, 14.0, (12.0, 28.0, 44.0)
SHUFFLE_ENDS, SHUFFLE_P, SHUFFLE_MOVE = (46.0, 22.0, 36.0), 2.0, 0.9
SHUFFLE_SWAPS = (0, 1, 0, 1, 0, 1)  # The upper place of each swap in turn: six swaps bring every row home.


def _shuffle_orders():
    """The rows' places before each swap: orders[k][row] is the row's place."""
    order, out = [0, 1, 2], []
    for top in SHUFFLE_SWAPS:
        out.append(tuple(order))
        a, b = order.index(top), order.index(top + 1)
        order[a], order[b] = top + 1, top
    return out


SHUFFLE_ORDERS = _shuffle_orders()


def build_overlook2_c(grains, rng):
    pts = []
    _cube(pts, SHUFFLE_HALF, 230, rng, "cube")
    pts = [(x, y + SHUFFLE_CUBE_Y, z, kind, b, 0, 0.0) for x, y, z, kind, b in pts]
    left = grains - len(pts)
    for row, (y, end) in enumerate(zip(SHUFFLE_ROWS, SHUFFLE_ENDS)):
        for x, yy in _fill(lambda x, y: True, (-3.8, -3.8, 3.8, 3.8), 22, rng):
            pts.append((-44.0 + x, y + yy, 0.0, "row", 1.05, row, rng.random()))
        n = (left - 66) // 3 if row < 2 else grains - len(pts)
        for m in _words(rng, end + 34.0, n):
            pts.append((-34.0 + m, y + rng.gauss(0, 0.8), 0.0, "row", 1.1, row, rng.random()))
    return dp._by_angle(pts)


def eval_overlook2_c(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.2 + 0.12 * sin(TAU * d / 9.0), -0.12, span=40.0)
    spin = 0.5 * d
    step, ph = divmod(max(0.0, d - 0.8), SHUFFLE_P)
    before = SHUFFLE_ORDERS[int(step) % len(SHUFFLE_ORDERS)]
    after = SHUFFLE_ORDERS[(int(step) + 1) % len(SHUFFLE_ORDERS)]
    for rec in points:
        if rec[3] == "cube":
            x, y, z = _turn(rec[0], rec[1] - SHUFFLE_CUBE_Y, rec[2], spin, -0.55)
            pose.put(x, y + SHUFFLE_CUBE_Y, z, rec[4])
            continue
        row, lag = rec[5], rec[6]
        p0, p1 = before[row], after[row]
        y0 = SHUFFLE_ROWS[row]
        if p0 == p1:
            pose.put(rec[0], rec[1] - y0 + SHUFFLE_ROWS[p0], 0.0, rec[4])
            continue
        k = (ph - SHUFFLE_P + SHUFFLE_MOVE + 0.12 * lag) / SHUFFLE_MOVE  # Each grain a touch apart: a flowing swap.
        e = _ease_back(k, 1.2)
        arc = sin(math.pi * min(1.0, max(0.0, k))) * (14.0 if p1 > p0 else -14.0)  # One forward, one back.
        y = SHUFFLE_ROWS[p0] + (SHUFFLE_ROWS[p1] - SHUFFLE_ROWS[p0]) * e
        pose.put(rec[0], rec[1] - y0 + y, arc, rec[4])
    return pose.out()


# ---------------------------------------------------------------------------
# book: memory (recall, note, forget)
# ---------------------------------------------------------------------------

BOOK_W, BOOK_H, BOOK_LIFT = 48.0, 31.0, 7.0  # A page's width out from the spine, half its height, its curl.


def _page_z(x):
    return BOOK_LIFT * sin(min(1.0, abs(x) / 18.0) * math.pi / 2)


def _open_book(pts, rng, rows, per_row, n_edge, n_cover):
    """An open book lying on its back: the two pages' lines of words, the page block's edges, and the cover."""
    for side in (-1, 1):
        for row, y in enumerate(rows):
            end = BOOK_W - 4.0 if (row + (side > 0)) % 4 else BOOK_W - 20.0
            for x in _words(rng, end - 7.0, per_row):
                gx = side * (7.0 + x)
                pts.append((gx, y + rng.gauss(0, 0.45), _page_z(gx) + 0.3, "text", 1.15, side, row, x / (end - 7.0)))
    for k in range(n_edge):  # The page block's fore-edges and foot: walls down to the cover.
        if k % 3 < 2:
            side = 1 if k % 3 else -1
            pts.append((side * BOOK_W, rng.uniform(-BOOK_H, BOOK_H), rng.uniform(-4.0, BOOK_LIFT), "edge", 0.8,
                        side, 0, 0.0))
        else:
            x = rng.uniform(-BOOK_W, BOOK_W)
            pts.append((x, BOOK_H, rng.uniform(-4.0, _page_z(x)), "edge", 0.8, 0, 0, 0.0))
    rim = _rrect(0.0, 0.0, 2 * BOOK_W + 9.0, 2 * BOOK_H + 8.0, 3.0)
    rim += rim[:1]
    seg = _lengths(rim)
    for k in range(n_cover):
        (x, y), _ = _along(rim, (k + rng.random()) / n_cover, seg)
        pts.append((x, y, -5.0, "cover", 0.85, 0, 0, 0.0))


# A: Riffle. An open book; its pages riffle over from right to left, three sheets of written dust one after another,
# each curling as it turns and settling flat on the left page. Then the book rests a beat and riffles again.
RIFFLE_P, RIFFLE_SHEETS, RIFFLE_GAP, RIFFLE_TURN = 3.6, 3, 0.42, 1.1
RIFFLE_ROWS = (-24.0, -14.5, -5.0, 4.5, 14.0, 23.5)


def build_book2_a(grains, rng):
    pts = []
    _open_book(pts, rng, RIFFLE_ROWS, 22, 96, 78)
    left = grains - len(pts)
    per = left // RIFFLE_SHEETS
    for k in range(RIFFLE_SHEETS):
        n = per if k < RIFFLE_SHEETS - 1 else grains - len(pts)
        for i in range(n):
            if i < 14:  # The sheet's fore-edge, so it reads as a sheet as it turns.
                r, y = BOOK_W - 1.0, -BOOK_H + 2 * BOOK_H * (i + 0.5) / 14
            else:
                row = (i - 14) % 4
                r = 8.0 + 36.0 * ((i - 14) // 4 + rng.random()) / ((n - 14) / 4)
                y = (-21.0, -7.0, 7.0, 21.0)[row] + rng.gauss(0, 0.45)
            pts.append((r, y, _page_z(r) + 0.6, "sheet", k, r, y, 0.0))
    return dp._by_angle(pts)


def eval_book2_a(name, points, scene, now):
    d = _age(scene, now)
    ph = (d - 0.7) % RIFFLE_P
    pose = _Pose(name, scene, now, -0.3 + 0.12 * sin(TAU * d / 8.0), 0.85, span=40.0)
    turns = [_smooth((ph - k * RIFFLE_GAP) / RIFFLE_TURN) for k in range(RIFFLE_SHEETS)]
    for rec in points:
        kind = rec[3]
        if kind != "sheet":
            pose.put(rec[0], rec[1], rec[2], rec[4])
            continue
        k, r, y = rec[4], rec[5], rec[6]
        th = math.pi * turns[k]
        if th <= 0.0 or th >= math.pi:  # Resting on a page, dark: the page's own lines show there.
            pose.put(r * (1 if th <= 0.0 else -1), y, _page_z(r) + 0.6, 0.0, gate=True)
            continue
        a = th - 0.55 * sin(th) * (r / BOOK_W) ** 1.5  # The outer part lags: the sheet curls as it turns.
        lift = _page_z(r) * abs(cos(a))
        b = 1.15 * _smooth(th / 0.35) * _smooth((math.pi - th) / 0.35)
        pose.put(r * cos(a), y, lift + 0.6 + r * sin(a), b)
    return pose.out()


# B: Lifting. An open book whose lines of words lift off the page as dust, one after another, each peeling up from
# the spine outward and loosening, then settling back into its place: memory being read.
LIFT_P, LIFT_ROWS = 4.2, (-25.0, -16.5, -8.0, 0.5, 9.0, 17.5, 26.0)


def build_book2_b(grains, rng):
    pts = []
    _open_book(pts, rng, LIFT_ROWS, 33, 86, 92)
    pts = [p + (rng.gauss(0, 1.0), rng.gauss(0, 1.0), rng.random()) for p in pts]
    return dp._by_angle(pts[:grains])


def eval_book2_b(name, points, scene, now):
    d = _age(scene, now)
    pose = _Pose(name, scene, now, -0.3 + 0.14 * sin(TAU * d / 9.0), 0.85, span=40.0)
    rows = len(LIFT_ROWS)
    for rec in points:
        x, y, z, kind, look, side, row, f, jx, jy, jr = rec
        if kind != "text":
            pose.put(x, y, z, look)
            continue
        order = (row if side > 0 else rows + row) / (2 * rows)  # Right page top to bottom, then the left.
        t = (d - 0.6 - order * LIFT_P - 0.5 * f) % LIFT_P
        lift = _smooth(t / 0.55) * (1.0 - _smooth((t - 0.75) / 0.9))
        loose = 2.6 * lift
        a = 2.2 * d + jr * TAU
        pose.put(x + jx * loose + 1.2 * lift * cos(a), y + jy * loose - 1.5 * lift + 1.2 * lift * sin(a),
                 z + 16.0 * lift * (0.7 + 0.3 * jr), look * (1.0 + 0.12 * lift))
    return pose.out()


# C: Clasp. The open book closes: its right half swings over onto the left, the pages fanning a beat behind the
# cover, and it rests shut as a solid book. Then it opens again with a small overshoot.
CLASP_P, CLASP_PIVOT = 5.6, BOOK_LIFT  # The loop, and the hinge's height: the page surface, so the halves meet.


def _shut(ph):
    """0 open, 1 shut: it closes, rests shut, opens with a small overshoot, and rests open."""
    if ph < 2.8:
        return _smooth(ph / 1.3)
    return 1.0 - _ease_back((ph - 2.8) / 1.3, 1.0)


def build_book2_c(grains, rng):
    pts = []
    _open_book(pts, rng, RIFFLE_ROWS, 20, 90, 80)
    # The right cover's outer face: a solid panel under the right page, which faces up once the book is shut.
    for x, y in _fill(lambda x, y: True, (2.0, -BOOK_H - 3.0, BOOK_W + 4.0, BOOK_H + 3.0), grains - len(pts), rng):
        pts.append((x, y, -5.0, "panel", 0.9, 1, 0, 0.0))
    return dp._by_angle(pts)


def eval_book2_c(name, points, scene, now):
    d = _age(scene, now)
    ph = (d - 0.8) % CLASP_P
    shut = _shut(ph)
    drop = 12.0 * sin(math.pi * min(1.0, shut))  # The book sinks a little as its half stands up, to stay in the box.
    pose = _Pose(name, scene, now, -0.3 + 0.12 * sin(TAU * d / 8.0), 0.85, span=40.0)
    for rec in points:
        x, y, z, kind, look = rec[:5]
        if x <= 0.0:
            pose.put(x + 0.5 * BOOK_W * shut, y + drop, z, look * (1.0 - 0.6 * shut if kind == "text" else 1.0))
            continue
        lag = 0.0 if kind in ("cover", "panel") else 0.1 + 0.12 * min(1.0, x / BOOK_W)  # Pages trail the cover.
        a = math.pi * _shut(ph - lag) if ph - lag >= 0.0 else math.pi * _shut(ph - lag + CLASP_P)
        a -= 0.35 * sin(a) * min(1.0, x / BOOK_W) ** 1.5  # The outer edge lags a little: the pages curl.
        h = z - CLASP_PIVOT
        gx, gz = x * cos(a) - h * sin(a), CLASP_PIVOT + x * sin(a) + h * cos(a)
        if kind == "panel":
            look *= 0.12 + 0.88 * _smooth((a - 1.6) / 1.2)  # It faces up only as the book shuts.
        elif kind == "text":
            look *= 1.0 - 0.75 * _smooth((a - 1.6) / 1.2)  # Face down on the other page.
        pose.put(gx + 0.5 * BOOK_W * shut, y + drop, gz, look)
    return pose.out()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ICONS = ("prompt", "globe", "message", "overlook", "book")
BUILDERS = {f"{icon}2_{v}": globals()[f"build_{icon}2_{v}"] for icon in ICONS for v in "abc"}
EVAL = {f"{icon}2_{v}": globals()[f"eval_{icon}2_{v}"] for icon in ICONS for v in "abc"}
NAMES = {"prompt2_a": "Typed", "prompt2_b": "Glyph", "prompt2_c": "Console",
         "globe2_a": "Currents", "globe2_b": "Fetch", "globe2_c": "Weave",
         "message2_a": "Writing", "message2_b": "Pillow", "message2_c": "Thread",
         "overlook2_a": "Lookout", "overlook2_b": "Field", "overlook2_c": "Shuffle",
         "book2_a": "Riffle", "book2_b": "Lifting", "book2_c": "Clasp"}


def extend(eval_targets):
    """devs_pack.eval_targets with these forms' own evaluators in front of it."""
    def with_tools(name, points, scene, now):
        own = EVAL.get(name)
        return own(name, points, scene, now) if own else eval_targets(name, points, scene, now)
    return with_tools


if __name__ == "__main__":
    # Each concept has the Devs grain count and a manifest entry, and stays inside the Devs form box over 12 s.
    # Run it as scripts/capped /usr/bin/python desktop/icons_tools2.py
    import random
    import types

    import icons_tools2 as tools  # The registered module, as devs_pack loaded it.

    trouble = []
    for name in tools.BUILDERS:
        pts = tools.BUILDERS[name](640, random.Random(sum(map(ord, name))))
        assert len(pts) == 640, (name, len(pts))
        assert name in dp.FORMS_META, f"{name} has no manifest entry"
        box = [0.0, 0.0, 0.0, 0.0]
        for k in range(360):
            tx, ty, tb, _ = dp.eval_targets(name, pts, types.SimpleNamespace(form_at=0.0), k / 30.0)
            assert len(tx) == 640, (name, len(tx))
            lit = [(x, y) for x, y, b in zip(tx, ty, tb) if b > 0.05]
            box = [min(box[0], *(x for x, _ in lit)), max(box[1], *(x for x, _ in lit)),
                   min(box[2], *(y for _, y in lit)), max(box[3], *(y for _, y in lit))]
        print(f"{name:12s} x {box[0]:6.1f} .. {box[1]:5.1f}   y {box[2]:6.1f} .. {box[3]:5.1f}")
        if not (-72 < box[0] and box[1] < 72 and -66 < box[2] and box[3] < 64):
            trouble.append(name)
    assert not trouble, f"outside the form box: {trouble}"
    print("ok")
