"""Filament: how a constellation looks. Each node is an original line icon and each thread a curve, drawn as a crisp
bright core with a soft gold glow and a soft ink edge under it, so it reads over a busy desktop. The presence's dust
only moves: it builds each line, runs along a thread as its node lights, gathers on the lit node, and carries the
drawing home (constellation.Constellation.targets).

The icons live on a 24-unit grid centred on 0, y down. A stroke is a list of ops: ("M", x, y), ("L", x, y),
("C", x1, y1, x2, y2, x, y) a cubic, ("A", cx, cy, r, a0, a1) an arc that starts a new stroke piece, ("a", ...) an arc
joined to the point before, ("E", cx, cy, rx, ry, a0, a1) an ellipse arc, ("R", x0, y0, x1, y1, radius) a closed
rounded box, and ("Z",) to close. Angles are radians, y down, so they run clockwise. Flattening is pure Python; only
art() and draw() need Cairo, which they import when called.

A diagram may also draw its own shapes: shape() reads SVG path data on the same grid (viewBox -12 -12 24 24) into
these ops and keeps them in SHAPES under a name that every function here takes as it takes an icon's.

The overlay draws one texture per diagram and scale (art): R the core's coverage, G the ink edge's, B how far along
its stroke each pixel lies (for the draw-on and the light run), A the element (node or thread) plus one. Per frame
only the elements' light state changes: Constellation.lines() gives 12 floats per element, which the GL path sends as
uniforms and draw() uses in the Cairo fallback.

Self-check: /usr/bin/python desktop/filament.py
"""

import math
import re

GRID = 0.075  # One icon grid unit as a share of the node's glyph radius.
CORE_W, THREAD_W, INK_W = 1.45, 1.2, 2.6  # px: an icon's core, a thread's, and how much wider the ink edge is.
HEAD = 6.5  # px: an arrowhead's arms.
GOLD, CHAMP, HOT = (0.91, 0.69, 0.29), (1.0, 0.91, 0.64), (1.0, 0.975, 0.90)
INK = (0.043, 0.043, 0.071)
LIGHT = {GOLD: (0.62, 0.40, 0.10), CHAMP: (0.70, 0.46, 0.12), HOT: (0.86, 0.45, 0.02)}  # The light theme's ambers.
GLOW_LIN = (0.81, 0.43, 0.07)  # GOLD in linear light, for the glow the bloom spreads.
GLOW_K = 1.8  # How strongly a line's glow feeds the overlay's bloom.
GLOW_KEEP = 0.1  # Of the glow's own band round the core, the share that stays once the bloom has spread it.
MAX_ELEMENTS = 20  # constellation.NODES_MAX + LINKS_MAX


def _gear():
    pts, n = [], 8
    for j in range(n):
        a = 2 * math.pi * j / n
        for da, r in ((-0.30, 7.0), (-0.17, 9.6), (0.17, 9.6), (0.30, 7.0)):
            pts.append((r * math.cos(a + da), r * math.sin(a + da)))
    return [("M", *pts[0])] + [("L", *p) for p in pts[1:]] + [("Z",)]


def _cloud():
    """Three lobes on a flat base, each arc ending where it meets the next circle."""
    lobes, base = [(-6.0, 1.5, 5.0), (0.5, -2.0, 6.0), (6.5, 2.0, 4.5)], 6.5

    def meet(c1, c2):  # The upper crossing of two circles, as an angle on each.
        (x1, y1, r1), (x2, y2, r2) = c1, c2
        d = math.hypot(x2 - x1, y2 - y1)
        a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
        hgt = math.sqrt(max(0.0, r1 * r1 - a * a))
        mx, my = x1 + a * (x2 - x1) / d, y1 + a * (y2 - y1) / d
        px, py = mx + hgt * (y2 - y1) / d, my - hgt * (x2 - x1) / d
        return math.atan2(py - y1, px - x1), math.atan2(py - y2, px - x2)
    (l_end, b_start), (b_end, r_start) = meet(lobes[0], lobes[1]), meet(lobes[1], lobes[2])
    (lx, ly, lr), (bx, by, br), (rx, ry, rr) = lobes
    l_start = math.pi - math.asin((base - ly) / lr)
    r_end = math.asin((base - ry) / rr)
    up = lambda a, ref: a + 2 * math.pi * math.ceil((ref - a) / (2 * math.pi))  # noqa: E731
    return [("M", lx + lr * math.cos(l_start), base), ("a", lx, ly, lr, l_start, up(l_end, l_start)),
            ("a", bx, by, br, up(b_start, 0), up(b_end, up(b_start, 0))),
            ("a", rx, ry, rr, r_start, up(r_end, r_start)), ("Z",)]


def _ring(r, x=0.0, y=0.0):
    return [("A", x, y, r, -math.pi / 2, 1.5 * math.pi)]


PI = math.pi
ICONS = {
    "mic": [[("R", -3.5, -10.5, 3.5, 2.5, 3.5)], [("A", 0, -1.5, 7.0, -0.12, PI + 0.12)],
            [("M", 0, 5.5), ("L", 0, 10.0)], [("M", -4.5, 10.0), ("L", 4.5, 10.0)]],
    "chip": [[("R", -6.5, -6.5, 6.5, 6.5, 1.6)], [("R", -2.6, -2.6, 2.6, 2.6, 0.8)],
             *[[("M", p, -6.5), ("L", p, -10.0)] for p in (-3.5, 0.0, 3.5)],
             *[[("M", p, 6.5), ("L", p, 10.0)] for p in (-3.5, 0.0, 3.5)],
             *[[("M", -6.5, p), ("L", -10.0, p)] for p in (-3.5, 0.0, 3.5)],
             *[[("M", 6.5, p), ("L", 10.0, p)] for p in (-3.5, 0.0, 3.5)]],
    "rook": [[("M", -6.0, -10.5), ("L", -3.6, -10.5), ("L", -3.6, -8.0), ("L", -1.2, -8.0), ("L", -1.2, -10.5),
              ("L", 1.2, -10.5), ("L", 1.2, -8.0), ("L", 3.6, -8.0), ("L", 3.6, -10.5), ("L", 6.0, -10.5),
              ("L", 6.0, -5.0), ("L", 4.2, -3.2), ("L", 5.0, 6.2), ("L", 7.0, 7.8), ("L", 7.0, 10.5),
              ("L", -7.0, 10.5), ("L", -7.0, 7.8), ("L", -5.0, 6.2), ("L", -4.2, -3.2), ("L", -6.0, -5.0), ("Z",)],
             [("M", -4.2, -3.2), ("L", 4.2, -3.2)], [("M", -5.0, 6.2), ("L", 5.0, 6.2)]],
    "speaker": [[("M", -9.5, -3.5), ("L", -5.0, -3.5), ("L", 0.5, -8.5), ("L", 0.5, 8.5), ("L", -5.0, 3.5),
                 ("L", -9.5, 3.5), ("Z",)], [("A", 0.5, 0.0, 4.8, -0.85, 0.85)], [("A", 0.5, 0.0, 8.8, -0.85, 0.85)]],
    "terminal": [[("R", -10.5, -8.0, 10.5, 8.0, 2.0)], [("M", -6.0, -3.0), ("L", -2.5, 0.0), ("L", -6.0, 3.0)],
                 [("M", 0.0, 3.5), ("L", 5.5, 3.5)]],
    "clock": [_ring(9.5), [("M", 0.0, -5.5), ("L", 0.0, 0.0), ("L", 4.0, 2.5)]],
    "mail": [[("R", -10.5, -7.0, 10.5, 7.0, 1.6)], [("M", -10.0, -6.0), ("L", 0.0, 1.5), ("L", 10.0, -6.0)]],
    "phone": [[("R", -6.0, -10.5, 6.0, 10.5, 2.4)], [("M", -1.75, -7.6), ("L", 1.75, -7.6)],
              [("M", -1.5, 7.6), ("L", 1.5, 7.6)]],
    "file": [[("M", -7.5, -10.5), ("L", 3.0, -10.5), ("L", 8.0, -5.5), ("L", 8.0, 10.5), ("L", -7.5, 10.5), ("Z",)],
             [("M", 3.0, -10.5), ("L", 3.0, -5.5), ("L", 8.0, -5.5)], [("M", -4.0, -1.0), ("L", 4.5, -1.0)],
             [("M", -4.0, 3.0), ("L", 4.5, 3.0)], [("M", -4.0, 7.0), ("L", 1.5, 7.0)]],
    "browser": [[("R", -10.5, -8.5, 10.5, 8.5, 2.0)], [("M", -10.5, -4.0), ("L", 10.5, -4.0)],
                [("M", -7.9, -6.25), ("L", -7.1, -6.25)], [("M", -5.4, -6.25), ("L", -4.6, -6.25)]],
    "cloud": [_cloud()],
    "code": [[("M", -4.5, -6.0), ("L", -10.0, 0.0), ("L", -4.5, 6.0)], [("M", 4.5, -6.0), ("L", 10.0, 0.0), ("L", 4.5, 6.0)],
             [("M", 2.0, -9.0), ("L", -2.0, 9.0)]],
    "database": [[("E", 0, -7.0, 7.5, 2.8, 0, 2 * PI)], [("M", -7.5, -7.0), ("L", -7.5, 7.5)],
                 [("M", 7.5, -7.0), ("L", 7.5, 7.5)], [("E", 0, 0.25, 7.5, 2.8, 0, PI)],
                 [("E", 0, 7.5, 7.5, 2.8, 0, PI)]],
    "folder": [[("M", -10.5, -7.5), ("L", -3.5, -7.5), ("L", -1.5, -5.0), ("L", 10.5, -5.0), ("L", 10.5, 8.5),
                ("L", -10.5, 8.5), ("Z",)], [("M", -10.5, -2.0), ("L", 10.5, -2.0)]],
    "gear": [_gear(), _ring(3.0)],
    "globe": [_ring(9.5), [("E", 0, 0, 4.2, 9.5, 0, 2 * PI)], [("M", -9.5, 0.0), ("L", 9.5, 0.0)]],
    "key": [_ring(4.5, -5.5, 0.0), [("M", -1.0, 0.0), ("L", 10.0, 0.0), ("L", 10.0, 3.5)], [("M", 6.5, 0.0), ("L", 6.5, 2.8)]],
    "lock": [[("R", -8.0, -2.5, 8.0, 10.5, 2.0)], [("M", -5.0, -2.5), ("L", -5.0, -5.5), ("a", 0, -5.5, 5.0, PI, 2 * PI),
                                                  ("L", 5.0, -2.5)], _ring(1.3, 0.0, 3.0),
             [("M", 0.0, 4.3), ("L", 0.0, 6.8)]],
    "queue": [[("R", -9.0, -9.0, 9.0, -4.0, 1.5)], [("R", -9.0, -2.5, 9.0, 2.5, 1.5)], [("R", -9.0, 4.0, 9.0, 9.0, 1.5)]],
    "robot": [[("R", -8.5, -5.0, 8.5, 8.5, 3.0)], _ring(1.5, -3.5, 1.5), _ring(1.5, 3.5, 1.5),
              [("M", 0.0, -5.0), ("L", 0.0, -8.0)], _ring(1.3, 0.0, -9.3), [("M", -8.5, 1.5), ("L", -10.5, 1.5)],
              [("M", 8.5, 1.5), ("L", 10.5, 1.5)]],
    "server": [[("R", -10.0, -9.0, 10.0, -1.5, 1.5)], [("R", -10.0, 1.5, 10.0, 9.0, 1.5)],
               [("M", -6.5, -5.25), ("L", -3.0, -5.25)], [("M", -6.5, 5.25), ("L", -3.0, 5.25)],
               _ring(0.8, 6.5, -5.25), _ring(0.8, 6.5, 5.25)],
    "user": [_ring(4.2, 0.0, -5.0), [("M", -8.5, 10.5), ("a", 0.0, 10.5, 8.5, PI, 2 * PI)]],
    "bolt": [[("M", 2.0, -11.0), ("L", -6.5, 1.5), ("L", -0.5, 1.5), ("L", -2.0, 11.0), ("L", 6.5, -2.0),
              ("L", 0.5, -2.0), ("Z",)]],
    "bulb": [[("M", -3.0, 5.5), ("L", -3.0, 3.6), ("L", -4.6, 1.2), ("a", 0.0, -3.5, 6.5, 2.37, 2 * PI + 0.77),
              ("L", 3.0, 3.6), ("L", 3.0, 5.5), ("Z",)], [("M", -2.5, 8.0), ("L", 2.5, 8.0)],
             [("M", -1.5, 10.5), ("L", 1.5, 10.5)]],
    "coins": [[("E", 0, -5.5, 9.0, 2.6, 0, 2 * PI)], [("M", -9.0, -5.5), ("L", -9.0, 6.5)],
              [("M", 9.0, -5.5), ("L", 9.0, 6.5)], [("E", 0, -1.5, 9.0, 2.6, 0, PI)], [("E", 0, 2.5, 9.0, 2.6, 0, PI)],
              [("E", 0, 6.5, 9.0, 2.6, 0, PI)]],
    "drop": [[("M", 0.0, -10.5), ("L", 5.75, 0.49), ("a", 0.0, 3.5, 6.5, -0.482, PI + 0.482), ("Z",)]],
    "flame": [[("M", 0.0, 10.5), ("C", -6.5, 10.5, -8.5, 4.0, -5.0, -1.5), ("C", -3.0, -4.5, -1.5, -7.5, 0.5, -11.0),
               ("C", 2.5, -6.5, 8.5, -2.0, 7.0, 3.5), ("C", 6.0, 8.0, 3.5, 10.5, 0.0, 10.5)],
              [("M", 0.0, 10.5), ("C", -2.8, 10.5, -3.6, 6.8, -1.6, 4.0), ("C", -0.6, 2.6, 0.0, 1.5, 0.2, 0.0),
               ("C", 1.8, 2.0, 3.6, 5.0, 2.6, 8.0), ("C", 2.0, 9.6, 1.0, 10.5, 0.0, 10.5)]],
    "house": [[("M", -10.5, -0.5), ("L", 0.0, -9.5), ("L", 10.5, -0.5)],
              [("M", -7.5, -3.0), ("L", -7.5, 9.5), ("L", 7.5, 9.5), ("L", 7.5, -3.0)],
              [("M", -2.5, 9.5), ("L", -2.5, 3.5), ("L", 2.5, 3.5), ("L", 2.5, 9.5)]],
    "laptop": [[("R", -8.0, -8.5, 8.0, 3.5, 1.5)], [("M", -8.0, 3.5), ("L", -10.5, 7.5), ("L", 10.5, 7.5), ("L", 8.0, 3.5)]],
    "magnifier": [_ring(6.5, -2.0, -2.0), [("M", 2.7, 2.7), ("L", 9.5, 9.5)]],
    "message": [[("M", -8.0, -8.5), ("L", 8.0, -8.5), ("a", 8.0, -6.0, 2.5, -PI / 2, 0), ("L", 10.5, 2.5),
                 ("a", 8.0, 2.5, 2.5, 0, PI / 2), ("L", 0.0, 5.0), ("L", -6.0, 9.5), ("L", -5.0, 5.0), ("L", -8.0, 5.0),
                 ("a", -8.0, 2.5, 2.5, PI / 2, PI), ("L", -10.5, -6.0), ("a", -8.0, -6.0, 2.5, PI, 1.5 * PI), ("Z",)]],
    "wifi": [[("A", 0.0, 7.0, 4.5, -2.36, -0.785)], [("A", 0.0, 7.0, 9.0, -2.36, -0.785)],
             [("A", 0.0, 7.0, 13.5, -2.36, -0.785)], _ring(1.0, 0.0, 7.0)],
    "dot": [_ring(6.0)],  # Any other noun: a clean filament circle.
}


def _flatten(stroke):
    """One stroke's ops as polylines on the grid: a list of point lists (an "A" or "E" starts a new one)."""
    out, cur, start = [], None, None

    def arc_pts(cx, cy, rx, ry, a0, a1):
        n = max(3, math.ceil(abs(a1 - a0) * max(rx, ry) / 0.45))
        return [(cx + rx * math.cos(a0 + (a1 - a0) * j / n), cy + ry * math.sin(a0 + (a1 - a0) * j / n))
                for j in range(n + 1)]

    for op in stroke:
        kind = op[0]
        if kind == "M":
            cur = [(op[1], op[2])]
            start = cur[0]
            out.append(cur)
        elif kind == "L":
            cur.append((op[1], op[2]))
        elif kind == "C":
            (x0, y0), (x1, y1, x2, y2, x3, y3) = cur[-1], op[1:]
            for j in range(1, 17):
                u = j / 16
                v = 1 - u
                cur.append((v * v * v * x0 + 3 * v * v * u * x1 + 3 * v * u * u * x2 + u * u * u * x3,
                            v * v * v * y0 + 3 * v * v * u * y1 + 3 * v * u * u * y2 + u * u * u * y3))
        elif kind in ("A", "a", "E"):
            cx, cy, rx, ry, a0, a1 = (op[1], op[2], op[3], op[3], op[4], op[5]) if kind != "E" else op[1:]
            pts = arc_pts(cx, cy, rx, ry, a0, a1)
            if kind == "a" and cur is not None:
                cur.extend(pts)
            else:
                cur = pts
                start = cur[0]
                out.append(cur)
        elif kind == "R":
            x0, y0, x1, y1, r = op[1:]
            cur = (arc_pts(x1 - r, y0 + r, r, r, -PI / 2, 0) + arc_pts(x1 - r, y1 - r, r, r, 0, PI / 2)
                   + arc_pts(x0 + r, y1 - r, r, r, PI / 2, PI) + arc_pts(x0 + r, y0 + r, r, r, PI, 1.5 * PI))
            cur.append(cur[0])
            start = cur[0]
            out.append(cur)
        elif kind == "Z" and cur and cur[-1] != start:
            cur.append(start)
    return out


_POLY = {}


def polylines(name):
    """Every piece of an icon as (points, shares) on the grid: shares run 0 to 1 along each stroke, so all of a
    stroke's pieces draw on together. Cached."""
    if name not in _POLY:
        out = []
        for stroke in ICONS.get(name) or SHAPES.get(name) or ICONS["dot"]:
            pieces = _flatten(stroke)
            total = sum(math.dist(a, b) for p in pieces for a, b in zip(p, p[1:])) or 1.0
            run = 0.0
            for pts in pieces:
                shares = [run / total]
                for a, b in zip(pts, pts[1:]):
                    run += math.dist(a, b)
                    shares.append(run / total)
                out.append((pts, shares))
        _POLY[name] = out
    return _POLY[name]


_WALK = {}


def _walk(name):
    """An icon's segments end to end, with their lengths and the total. Cached: the glints ask every frame."""
    if name not in _WALK:
        segs = [(a, b, math.dist(a, b)) for pts, _ in polylines(name) for a, b in zip(pts, pts[1:])]
        _WALK[name] = segs, sum(d for _, _, d in segs) or 1.0
    return _WALK[name]


def sample(name, count):
    """count points spaced evenly along all of an icon's strokes, on the grid."""
    segs, total = _walk(name)
    out, j, run = [], 0, 0.0
    for a, b, d in segs:
        while j < count and (j + 0.5) * total / count <= run + d:
            k = ((j + 0.5) * total / count - run) / d if d else 0.0
            out.append((a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k))
            j += 1
        run += d
    while len(out) < count:
        out.append(segs[-1][1])
    return out


def point_at(name, s):
    """The point at share s (wrapping) of all of an icon's stroke length, on the grid."""
    segs, total = _walk(name)
    want = (s % 1.0) * total
    for a, b, d in segs:
        if want <= d:
            k = want / d if d else 0.0
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        want -= d
    return segs[-1][1]


def icon_name(icon):
    return icon if icon in ICONS or icon in SHAPES else "dot"


# ---- shapes a diagram draws itself, as SVG path data ----

# Caps, so a huge or hostile path cannot stall a frame: the text read, the commands, and the points they flatten to.
SHAPE_TEXT, SHAPE_COMMANDS, SHAPE_POINTS = 1000, 64, 400
SHAPE_FIT = 10.5  # A shape that leaves the grid is centred and shrunk to this half size.
SHAPES = {}  # A drawn shape's name ("~" and its path) to its strokes, as in ICONS. Only the newest SHAPES_KEPT.
SHAPES_KEPT = 16
_TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)|[\s,]+|(.)")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}
_COST = {"M": 1, "L": 1, "C": 16, "Z": 1}  # The points each op flattens to (_flatten).


def _arc(p0, rx, ry, turn, large, sweep, p1):
    """An SVG endpoint arc as cubics of at most a quarter turn each (the centre conversion of the SVG spec, F.6.5)."""
    (x1, y1), (x2, y2) = p0, p1
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if not rx or not ry:
        return [("L", x2, y2)]
    phi = math.radians(turn % 360)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = cp * dx + sp * dy, -sp * dx + cp * dy
    grow = (xp / rx) ** 2 + (yp / ry) ** 2
    if grow > 1:  # Radii too small to reach the end: scale them up just enough.
        rx, ry = rx * math.sqrt(grow), ry * math.sqrt(grow)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    co = math.sqrt(max(0.0, num / (rx * rx * yp * yp + ry * ry * xp * xp))) * (-1 if large == sweep else 1)
    cxp, cyp = co * rx * yp / ry, -co * ry * xp / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2
    ux, uy, vx, vy = (xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry
    t0 = math.atan2(uy, ux)
    dt = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    if sweep and dt < 0:
        dt += 2 * PI
    elif not sweep and dt > 0:
        dt -= 2 * PI
    n = max(1, math.ceil(abs(dt) / (PI / 2) - 1e-9))
    d = dt / n
    k = 4 / 3 * math.tan(d / 4)

    def at(t):  # The point at angle t, and the tangent there.
        ex, ey, tx, ty = rx * math.cos(t), ry * math.sin(t), -rx * math.sin(t), ry * math.cos(t)
        return cx + cp * ex - sp * ey, cy + sp * ex + cp * ey, cp * tx - sp * ty, sp * tx + cp * ty

    out = []
    for j in range(n):
        (ax, ay, tax, tay), (bx, by, tbx, tby) = at(t0 + j * d), at(t0 + (j + 1) * d)
        out.append(("C", ax + k * tax, ay + k * tay, bx - k * tbx, by - k * tby, bx, by))
    out[-1] = out[-1][:5] + (x2, y2)
    return out


def path_strokes(d):
    """SVG path data on the grid as (strokes, repairs): one stroke per subpath, of M, L, C and Z ops; Q, T and arcs
    become cubics. It keeps at most SHAPE_COMMANDS commands and SHAPE_POINTS flattened points, and a shape that
    leaves the grid is centred and shrunk to fit. strokes is None when nothing in it draws. Repairs are for the
    builders' log."""
    text, repairs = str(d or ""), []
    if len(text) > SHAPE_TEXT:
        text = text[:SHAPE_TEXT]
        repairs.append(f"path cut at {SHAPE_TEXT} characters")
    items, odd = [], False
    for m in _TOKEN.finditer(text):
        if m[1] or m[2]:
            items.append(m[1] or m[2])
        odd = odd or m[3] is not None
    if odd:
        repairs.append("odd characters skipped")
    strokes, ops = [], None
    x = y = sx = sy = 0.0
    cmd, prev, ctrl = None, "", (0.0, 0.0)  # The command, the last segment's kind, and its last control point.
    commands = points = i = 0

    def put(op):
        nonlocal points
        if points + _COST[op[0]] > SHAPE_POINTS:
            return False
        points += _COST[op[0]]
        ops.append(op)
        return True

    while i < len(items):
        tok = items[i]
        if tok.isalpha():
            cmd, i = tok, i + 1
            if cmd in "Zz":
                if ops is not None:
                    if not put(("Z",)):
                        repairs.append(f"shape cut at {SHAPE_POINTS} points")
                        break
                    x, y, ops, prev = sx, sy, None, "Z"
                cmd = None
            continue
        if cmd is None:
            repairs.append("numbers with no command skipped")
            i += 1
            continue
        kind, rel = cmd.upper(), cmd.islower()
        args, j = [], i
        while len(args) < _ARGS[kind] and j < len(items) and not items[j].isalpha():
            tok = items[j]
            if kind == "A" and len(args) in (3, 4) and len(tok) > 1 and tok[0] in "01":  # Packed flags, as "011".
                items[j], tok = tok[1:], tok[0]
            else:
                j += 1
            args.append(float(tok))
        i = j
        if len(args) < _ARGS[kind]:
            repairs.append(f"short {cmd} dropped")
            continue
        if not all(abs(v) <= 1e4 for v in args):  # Also inf and nan.
            repairs.append("a number too large: path cut")
            break
        if commands >= SHAPE_COMMANDS:
            repairs.append(f"shape cut at {SHAPE_COMMANDS} commands")
            break
        commands += 1
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if kind == "M":
            x, y = sx, sy = ox + args[0], oy + args[1]
            ops = [("M", x, y)]
            strokes.append(ops)
            points += 1
            cmd, prev = "l" if rel else "L", "M"  # More pairs after a move are lines.
            continue
        if ops is None:  # A line on after Z starts again where the closed piece began.
            ops = [("M", x, y)]
            strokes.append(ops)
            points += 1
        if kind in "LHV":
            x, y = (ox + args[0] if kind != "V" else x), (oy + args[-1] if kind != "H" else y)
            new = [("L", x, y)]
        elif kind in "CS":
            c1 = (ox + args[0], oy + args[1]) if kind == "C" else \
                (2 * x - ctrl[0], 2 * y - ctrl[1]) if prev in "CS" else (x, y)
            c2, end = (ox + args[-4], oy + args[-3]), (ox + args[-2], oy + args[-1])
            new, ctrl = [("C", *c1, *c2, *end)], c2
        elif kind in "QT":
            q = (ox + args[0], oy + args[1]) if kind == "Q" else \
                (2 * x - ctrl[0], 2 * y - ctrl[1]) if prev in "QT" else (x, y)
            end = (ox + args[-2], oy + args[-1])
            new, ctrl = [("C", x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y), end[0] + 2 / 3 * (q[0] - end[0]),
                          end[1] + 2 / 3 * (q[1] - end[1]), *end)], q
        else:
            new = _arc((x, y), args[0], args[1], args[2], args[3] != 0, args[4] != 0, (ox + args[5], oy + args[6]))
        if not all(put(op) for op in new):
            repairs.append(f"shape cut at {SHAPE_POINTS} points")
            break
        x, y = new[-1][-2:] if new else (x, y)
        prev = kind
    strokes = [s for s in strokes if any(op[0] in "LC" for op in s)]
    if not strokes:
        return None, repairs + ["path drew nothing"]
    xs = [v for s in strokes for op in s for v in op[1::2]]
    ys = [v for s in strokes for op in s for v in op[2::2]]
    if max(map(abs, xs + ys)) > 12:
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        k = min(1.0, SHAPE_FIT / (max(max(xs) - min(xs), max(ys) - min(ys)) / 2 or 1.0))
        strokes = [[(op[0], *((v - (cy if j % 2 else cx)) * k for j, v in enumerate(op[1:]))) for op in s]
                   for s in strokes]
        repairs.append("shape fitted to the grid")
    return strokes, repairs


def shape(d):
    """Keep a drawn shape: (its name for the functions here, repairs). The name is None when the path draws nothing,
    so the node keeps its icon or ring."""
    strokes, repairs = path_strokes(d)
    if strokes is None:
        return None, repairs
    name = "~" + " ".join(str(d).split())[:SHAPE_TEXT]
    if name not in SHAPES:
        while len(SHAPES) >= SHAPES_KEPT:  # The oldest goes; a constellation keeps the strokes it already made.
            old = next(iter(SHAPES))
            del SHAPES[old]
            _POLY.pop(old, None)
            _WALK.pop(old, None)
        SHAPES[name] = strokes
    return name, repairs


def _qpt(c, u):
    (x0, y0), (x1, y1), (x2, y2) = c
    v = 1.0 - u
    return v * v * x0 + 2 * v * u * x1 + u * u * x2, v * v * y0 + 2 * v * u * y1 + u * u * y2


def elements(plan, nodes):
    """The drawing's elements, nodes first, then threads: each a list of (points, shares, width) in px about the
    drawing's centre. A thread is its curve, its shares the length along it, and an arrow's head (share 1) last."""
    out = []
    for k, nd in enumerate(nodes):
        (px, py), u = plan["pos"][k], plan["r"][k] * GRID
        out.append([([(px + x * u, py + y * u) for x, y in pts], shares, CORE_W)
                    for pts, shares in polylines(icon_name(nd["icon"]))])
    for c, (_, _, arrow) in zip(plan["curves"], plan["links"]):
        pts = [_qpt(c, j / 40) for j in range(41)]
        run, shares = 0.0, [0.0]
        for a, b in zip(pts, pts[1:]):
            run += math.dist(a, b)
            shares.append(run)
        strokes = [(pts, [s / (run or 1.0) for s in shares], THREAD_W)]
        if arrow:
            (x0, y0), (x1, y1) = pts[-3], pts[-1]
            ang = math.atan2(y1 - y0, x1 - x0)
            for side in (-1, 1):
                tip = (x1 - HEAD * math.cos(ang + side * 0.5), y1 - HEAD * math.sin(ang + side * 0.5))
                strokes.append(([tip, (x1, y1)], [1.0, 1.0], THREAD_W))
        out.append(strokes)
    return out


def art(els, size, scale):
    """The drawing's texture (see the module note) as (RGBA bytes, width, height) in device pixels, its centre at
    (width / 2, height / 2). A few ms, once per diagram and scale."""
    import cairo
    W = (math.ceil(size[0] * scale) + 7) // 8 * 8  # Even halves, and rows whole words, so stride == width.
    H = (math.ceil(size[1] * scale) + 1) // 2 * 2
    planes = []
    for plane in range(4):
        surf = cairo.ImageSurface(cairo.FORMAT_A8, W, H)
        cr = cairo.Context(surf)
        cr.translate(W / 2, H / 2)
        cr.scale(scale, scale)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        if plane >= 2:  # The share and the element are exact values, never blended.
            cr.set_antialias(cairo.ANTIALIAS_NONE)
            cr.set_operator(cairo.OPERATOR_SOURCE)
        for e, strokes in enumerate(els):
            for pts, shares, width in strokes:
                cr.set_line_width(width + (INK_W if plane else 0.0))
                if plane == 2:  # One segment at a time, each carrying its share; later ones win at the joins.
                    for (a, b), s in zip(zip(pts, pts[1:]), shares[1:]):
                        cr.move_to(*a)
                        cr.line_to(*b)
                        cr.set_source_rgba(0, 0, 0, max(0.0, min(1.0, s)))
                        cr.stroke()
                    continue
                cr.move_to(*pts[0])
                for p in pts[1:]:
                    cr.line_to(*p)
                cr.set_source_rgba(0, 0, 0, (e + 1) / 255 if plane == 3 else 1.0)
                cr.stroke()
        surf.flush()
        assert surf.get_stride() == W
        planes.append(bytes(surf.get_data()))
    data = bytearray(W * H * 4)
    for plane, values in enumerate(planes):
        data[plane::4] = values
    return bytes(data), W, H


def _part(pts, shares, lo, hi):
    """The piece of a polyline between shares lo and hi."""
    out = []
    for (a, sa), (b, sb) in zip(zip(pts, shares), zip(pts[1:], shares[1:])):
        if sb < lo or sa > hi:
            continue
        span = sb - sa
        k0, k1 = (max(0.0, (lo - sa) / span), min(1.0, (hi - sa) / span)) if span else (0.0, 1.0)  # A head: all.
        p0 = (a[0] + (b[0] - a[0]) * k0, a[1] + (b[1] - a[1]) * k0)
        p1 = (a[0] + (b[0] - a[0]) * k1, a[1] + (b[1] - a[1]) * k1)
        if not out:
            out.append(p0)
        out.append(p1)
    return out


def draw(cr, els, state, ox, oy, light=False):
    """The Cairo fallback of the GL passes: ink edge, a soft glow, then the cores, with state from
    Constellation.lines() (12 floats per element) and the drawing's centre at (ox, oy) in logical px."""
    import cairo
    cr.save()
    cr.translate(ox, oy)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    hot_rgb = LIGHT[HOT] if light else HOT
    for e, strokes in enumerate(els):
        r, g, b, a, p, run, rev, glow, _out, _pen, hot_a, hot_glow = state[12 * e:12 * e + 12]
        if p <= 0.001:
            continue
        pieces = []  # (points, colour, alpha, glow, width)
        for pts, shares, width in strokes:
            shown = _part(pts, shares, -1.0, p + 0.002)
            if len(shown) > 1:
                pieces.append((shown, (r, g, b), a, glow, width))
            if run > 0:  # The lit run, from the start, or from the end for a plain line lit at its start.
                hot = _part(pts, shares, -1.0, min(run, p)) if rev < 0.5 else _part(pts, shares, 1.0 - run, p)
                if len(hot) > 1:
                    pieces.append((hot, hot_rgb, hot_a, hot_glow, width))
        for layer in ("ink", "glow", "core"):
            if light and layer != "core":
                continue
            for pts, rgb, alpha, glw, width in pieces:
                cr.move_to(*pts[0])
                for q in pts[1:]:
                    cr.line_to(*q)
                if layer == "ink":
                    cr.set_source_rgba(*INK, min(0.55, 0.6 * alpha))
                    cr.set_line_width(width + INK_W)
                elif layer == "glow":
                    cr.set_source_rgba(*GOLD, 0.30 * glw)
                    cr.set_line_width(width * 3.2)
                else:
                    cr.set_source_rgba(*rgb, min(1.0, alpha))
                    cr.set_line_width(width)
                cr.stroke()
    cr.restore()


def _check():
    for name in ICONS:
        pts = sample(name, 240)
        assert len(pts) == 240 and all(abs(x) <= 12.01 and abs(y) <= 12.01 for x, y in pts), name
        for line, shares in polylines(name):
            assert len(line) == len(shares) >= 2 and shares == sorted(shares) and shares[-1] <= 1.0 + 1e-9, name
    # Drawn shapes: each SVG command family, relative ones, packed numbers, arcs, the fit, the caps, broken paths.
    flat = lambda d: [p for s in path_strokes(d)[0] for piece in _flatten(s) for p in piece]  # noqa: E731
    assert path_strokes("M-6-2L6-2")[0] == [[("M", -6.0, -2.0), ("L", 6.0, -2.0)]]
    assert path_strokes("M0 0h5v5H0z")[0] == [[("M", 0, 0), ("L", 5, 0), ("L", 5, 5), ("L", 0, 5), ("Z",)]]
    assert path_strokes("m1 1 2 0 0 2")[0] == [[("M", 1, 1), ("L", 3, 1), ("L", 3, 3)]]  # More pairs are lines.
    assert path_strokes("M0 0C0-4 4-4 4 0S8 4 8 0")[0][0][2][1:3] == (4.0, 4.0)  # S mirrors the last control.
    assert path_strokes("M0 0c0-4 4-4 4 0s4 4 4 0")[0] == path_strokes("M0 0C0-4 4-4 4 0S8 4 8 0")[0]
    q = flat("M-8 0Q-4-8 0 0T8 0")
    assert math.dist(q[8], (-4, -4)) < 1e-9 and math.dist(q[24], (4, 4)) < 1e-9, q  # Q's middle, and T mirrored.
    assert path_strokes("M-8 0q4-8 8 0t8 0")[0] == path_strokes("M-8 0Q-4-8 0 0T8 0")[0]
    arc = flat("M-5 0A5 5 0 0 1 5 0")  # Sweep 1 runs clockwise: over the top, y down.
    assert all(abs(math.hypot(*p) - 5) < 0.01 for p in arc) and abs(min(y for _, y in arc) + 5) < 0.01
    assert abs(max(y for _, y in flat("M-5 0a5 5 0 1010 0")) - 5) < 0.01  # Packed flags, under the bottom.
    assert abs(max(x for x, _ in flat("M0-8A8 4 90 0 1 0 8")) - 4) < 0.01  # A turned ellipse.
    assert len(path_strokes("M-9 0A1 1 0 0 1 9 0")[0][0]) == 3  # Radii too small grow to reach: a half turn.
    strokes, rep = path_strokes("M0 0L24 24")  # Off the grid: centred and shrunk to fit.
    assert strokes == [[("M", -SHAPE_FIT, -SHAPE_FIT), ("L", SHAPE_FIT, SHAPE_FIT)]] and "fitted" in rep[0]
    strokes, rep = path_strokes("M0 0" + " L1 1" * 99)
    assert len(strokes[0]) == SHAPE_COMMANDS and any("commands" in r for r in rep)
    strokes, rep = path_strokes("M0 0" + " C1 1 2 2 3 3" * 40)
    assert len(strokes[0]) == 1 + (SHAPE_POINTS - 1) // 16 and any("points" in r for r in rep)
    assert path_strokes("M0 0 L1 1 M5 5 Z M2 2 L3 3")[0] == [[("M", 0, 0), ("L", 1, 1)], [("M", 2, 2), ("L", 3, 3)]]
    for broken in ("", "hello", "M5 5", "12 4 L", "M0 0L1e9 0", "L", "Z Z", "M 1e999 0 L 1 1"):
        assert path_strokes(broken)[0] is None and shape(broken) == (None, path_strokes(broken)[1]), broken
    import time
    started = time.perf_counter()
    assert len(path_strokes("M0 0" + " L1 1" * 500_000)[1]) == 2 and time.perf_counter() - started < 0.1
    heart, rep = shape("M0 9C-6 4-10 0-10-4A5 5 0 0 1 0-6A5 5 0 0 1 10-4C10 0 6 4 0 9Z")
    assert heart in SHAPES and icon_name(heart) == heart and not rep
    assert all(abs(x) <= 12 and abs(y) <= 12 for x, y in sample(heart, 240)) and point_at(heart, 0.0) == (0, 9)
    for k in range(SHAPES_KEPT + 4):  # Only the newest shapes stay.
        shape(f"M0 0L{k} 5")
    assert len(SHAPES) == SHAPES_KEPT and heart not in SHAPES and icon_name(heart) == "dot"
    heart = shape("M0 9C-6 4-10 0-10-4A5 5 0 0 1 0-6A5 5 0 0 1 10-4C10 0 6 4 0 9Z")[0]
    plan = {"pos": [(-60.0, 0.0), (60.0, 0.0)], "r": [44.0, 44.0], "curves": [((-43.0, 0.0), (0.0, 4.0), (43.0, 0.0))],
            "links": [(0, 1, True)]}
    assert len(elements(plan, [{"icon": heart}, {"icon": "dot"}])[0][0][0]) > 40
    els = elements(plan, [{"icon": "mic"}, {"icon": "nosuch"}])
    assert len(els) == 3 and len(els[2]) == 3 and els[2][1][1] == [1.0, 1.0]
    data, w, h = art(els, (200, 120), 1.0)
    assert len(data) == w * h * 4 and w % 8 == 0
    ids = set(data[3::4])
    assert ids == {0, 1, 2, 3}, ids  # Every element drew, and nothing else.
    print("filament: ok")


if __name__ == "__main__":
    _check()
