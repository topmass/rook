"""Rook's stencils: well-drawn parts a scene places by name, so a model writes one line, not a drawing.

Each stencil is a list of (ink, path). The path is SVG path data, in a frame 128 units wide with y down. The frame's
origin is the stencil's pivot: the point it turns about and the point "at" places. Most pivots are the centre; a crank
turns about its journal, a valve hangs from its stem's top, a piston and a rod pivot on their pins.
Ink is how the path is drawn: "line" is the main outline, "thin" is a detail line at THIN of its width, and "fill"
is a solid area.
Line widths are set in pixels when the stencil is drawn, so a small stencil keeps lines that dust can draw.

A compound stencil is a group of stencils that interlock, each with its own id, such as the parts of an engine. It is a
list of (id, stencil, at, size, rotate), in the compound's own 128-unit frame.
"""

import math

THIN = 0.6  # A thin line's width, as a share of a line's.


def _circle(cx, cy, r):
    return f"M {cx - r} {cy} a {r} {r} 0 1 0 {2 * r} 0 a {r} {r} 0 1 0 {-2 * r} 0 Z"


def _ellipse(cx, cy, rx, ry, turn=0.0):
    """An ellipse turned turn degrees, as two arcs."""
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    ax, ay = cx + rx * c, cy + rx * s
    bx, by = cx - rx * c, cy - rx * s
    return f"M {ax:.2f} {ay:.2f} A {rx} {ry} {turn} 1 0 {bx:.2f} {by:.2f} A {rx} {ry} {turn} 1 0 {ax:.2f} {ay:.2f} Z"


def _rect(x, y, w, h, r=0):
    if not r:
        return f"M {x} {y} h {w} v {h} h {-w} Z"
    return (f"M {x + r} {y} H {x + w - r} A {r} {r} 0 0 1 {x + w} {y + r} V {y + h - r} "
            f"A {r} {r} 0 0 1 {x + w - r} {y + h} H {x + r} A {r} {r} 0 0 1 {x} {y + h - r} V {y + r} "
            f"A {r} {r} 0 0 1 {x + r} {y} Z")


def _turned(points, turn):
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def _poly(points, closed=True):
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points) + (" Z" if closed else "")


def _lines(*segments):
    """Separate straight lines, each (x1, y1, x2, y2), as one path."""
    return " ".join(f"M {a:.2f} {b:.2f} L {c:.2f} {d:.2f}" for a, b, c, d in segments)


def _gear(teeth, outer, inner):
    points = []
    for k in range(teeth):
        a = 2 * math.pi * k / teeth
        w = math.pi / teeth
        for r, da in ((inner, -0.55 * w), (outer, -0.32 * w), (outer, 0.32 * w), (inner, 0.55 * w)):
            points.append((r * math.cos(a + da), r * math.sin(a + da)))
    return _poly(points)


def _rays(count, r0, r1, start=0.0):
    return _lines(*[(r0 * math.cos(a), r0 * math.sin(a), r1 * math.cos(a), r1 * math.sin(a))
                    for a in (math.radians(start) + 2 * math.pi * k / count for k in range(count))])


_CLOUD = ("M -44 34 H 42 A 20 20 0 0 0 40 -4 A 28 28 0 0 0 -10 -18 A 22 22 0 0 0 -46 2 A 16 16 0 0 0 -44 34 Z")
_BLADE = [(0, 0), (8, -18), (24, -38), (14, -50), (0, -52), (-8, -40), (-6, -20)]

STENCILS = {
    # Computing.
    "server": [("line", _rect(-46, y, 92, 28, 5)) for y in (-46, -14, 18)]
              + [("fill", _circle(-32, y + 14, 4)) for y in (-46, -14, 18)]
              + [("thin", _lines(*[(-8, y + 14, 32, y + 14) for y in (-46, -14, 18)]))],
    "database": [("line", _ellipse(0, -36, 44, 13)),
                 ("line", "M -44 -36 V 36 A 44 13 0 0 0 44 36 V -36"),
                 ("thin", "M -44 -8 A 44 13 0 0 0 44 -8 M -44 14 A 44 13 0 0 0 44 14")],
    "laptop": [("line", _rect(-42, -40, 84, 58, 5)), ("thin", _rect(-33, -31, 66, 40)),
               ("line", "M -56 26 H 56 L 50 36 H -50 Z")],
    "phone": [("line", _rect(-27, -54, 54, 108, 9)), ("thin", _rect(-19, -38, 38, 70, 2)),
              ("thin", "M -8 -46 H 8"), ("fill", _circle(0, 44, 4))],
    "browser": [("line", _rect(-58, -42, 116, 84, 6)), ("line", "M -58 -22 H 58"),
                ("fill", " ".join(_circle(x, -32, 3.5) for x in (-46, -35, -24))),
                ("thin", _rect(-10, -37, 58, 10, 5)), ("thin", _lines((-44, -4, 30, -4), (-44, 10, 40, 10),
                                                                     (-44, 24, 12, 24)))],
    "cloud": [("line", _CLOUD)],
    "chip": [("line", _rect(-32, -32, 64, 64, 4)), ("thin", _rect(-17, -17, 34, 34)),
             ("thin", _lines(*[seg for p in (-21, -7, 7, 21) for seg in
                               ((p, -32, p, -46), (p, 32, p, 46), (-32, p, -46, p), (32, p, 46, p))]))],
    "lock": [("line", "M -22 -6 V -24 A 22 22 0 0 1 22 -24 V -6"), ("line", _rect(-34, -6, 68, 54, 6)),
             ("fill", _circle(0, 14, 6) + " M -3 16 L -5 32 H 5 L 3 16 Z")],
    "key": [("line", _circle(-34, 0, 18)), ("thin", _circle(-34, 0, 6)),
            ("line", "M -16 0 H 54 M 38 0 V 14 M 50 0 V 12")],
    "file": [("line", "M -36 -52 H 14 L 38 -28 V 52 H -36 Z"), ("thin", "M 14 -52 V -28 H 38"),
             ("thin", _lines((-24, -14, 24, -14), (-24, 2, 24, 2), (-24, 18, 24, 18), (-24, 34, 8, 34)))],
    "folder": [("line", "M -56 -34 V 40 H 56 V -22 H -2 L -12 -34 Z"), ("thin", "M -56 -12 H 56")],
    "terminal": [("line", _rect(-56, -42, 112, 84, 6)), ("line", "M -38 -16 L -20 0 L -38 16 M -10 18 H 18")],
    "robot": [("line", _rect(-38, -28, 76, 60, 14)), ("line", "M 0 -28 V -44"), ("fill", _circle(0, -48, 6)),
              ("fill", _circle(-16, -4, 7) + " " + _circle(16, -4, 7)), ("thin", "M -14 16 H 14"),
              ("thin", _rect(-48, -10, 10, 20, 3) + " " + _rect(38, -10, 10, 20, 3))],
    "user": [("line", _circle(0, -26, 20)), ("line", "M -44 50 C -44 8 44 8 44 50 Z")],
    "globe": [("line", _circle(0, 0, 48)), ("thin", _ellipse(0, 0, 20, 48, 90)),
              ("thin", _lines((-48, 0, 48, 0), (-41, -24, 41, -24), (-41, 24, 41, 24)))],
    "mail": [("line", _rect(-54, -36, 108, 72, 6)), ("line", "M -52 -32 L 0 6 L 52 -32")],
    "message": [("line", "M -50 -24 A 14 14 0 0 1 -36 -38 H 36 A 14 14 0 0 1 50 -24 V 12 A 14 14 0 0 1 36 26 "
                         "H -14 L -34 44 L -30 26 H -36 A 14 14 0 0 1 -50 12 Z"),
                ("thin", _lines((-32, -16, 32, -16), (-32, 2, 18, 2)))],
    "queue": [("line", " ".join(_rect(x, -18, 24, 36, 4) for x in (-56, -26, 4))),
              ("line", "M 36 0 H 56 M 48 -8 L 56 0 L 48 8")],
    "code": [("line", "M -22 -26 L -48 0 L -22 26 M 22 -26 L 48 0 L 22 26 M 9 -36 L -9 36")],
    "wifi": [("line", "M -50 -10 A 72 72 0 0 1 50 -10 M -33 8 A 48 48 0 0 1 33 8 M -16 26 A 24 24 0 0 1 16 26"),
             ("fill", _circle(0, 42, 7))],
    # Machines and power.
    "piston": [("line", _rect(-32, -40, 64, 54, 4)), ("thin", _lines((-32, -30, 32, -30), (-32, -22, 32, -22))),
               ("fill", _circle(0, 0, 7))],
    "rod": [("line", _circle(0, 0, 9) + " " + _circle(0, 64, 13)), ("line", "M -5 8 L -8 52 M 5 8 L 8 52")],
    "crank": [("line", "M -30 6 A 30 30 0 0 0 30 6 Z"),
              ("line", "M -12 -4 L -8 -36 A 9 9 0 0 1 8 -36 L 12 -4 A 13 13 0 0 1 -12 -4 Z"),
              ("fill", _circle(0, 0, 6)), ("thin", _circle(0, -36, 5))],
    "valve": [("line", "M 0 0 V 78"), ("fill", "M -20 90 L 20 90 L 6 78 L -6 78 Z")],
    "spark": [("fill", _rect(-5, -60, 10, 10, 2)), ("line", _rect(-10, -50, 20, 38, 6)),
              ("line", _rect(-17, -12, 34, 14, 2)), ("thin", _lines((-12, 6, 12, 6), (-12, 13, 12, 13))),
              ("line", "M 0 2 V 30 M 12 2 V 40 H 4")],
    "cylinder": [("line", "M -38 72 V -40 H -26 V -58 H -50 V 72 Z M 38 72 V -40 H 26 V -58 H 50 V 72 Z "
                          "M -8 -40 H 8 V -58 H -8 Z"),
                 ("thin", _lines((-50, 20, -38, 8), (-50, -8, -38, -20), (38, 20, 50, 8), (38, -8, 50, -20)))],
    "gear": [("line", _gear(10, 50, 38)), ("line", _circle(0, 0, 12))],
    "spring": [("line", "M 0 -56 V -46 L 24 -38 L -24 -26 L 24 -14 L -24 -2 L 24 10 L -24 22 L 24 34 L 0 42 V 56")],
    "wheel": [("line", _circle(0, 0, 52)), ("thin", _circle(0, 0, 42)), ("line", _circle(0, 0, 10)),
              ("thin", _rays(6, 10, 42, 90))],
    "fan": [("line", " ".join(_poly(_turned(_BLADE, t)) for t in (0, 120, 240))), ("fill", _circle(0, 0, 9)),
            ("thin", _circle(0, 0, 58))],
    "battery": [("line", _rect(-52, -26, 94, 52, 6)), ("fill", _rect(42, -11, 10, 22, 2)),
                ("line", "M 12 0 H 30 M 21 -9 V 9 M -38 0 H -22")],
    "bulb": [("line", "M -16 26 C -16 12 -40 0 -40 -20 A 40 40 0 0 1 40 -20 C 40 0 16 12 16 26 Z"),
             ("line", "M -16 36 H 16 M -13 46 H 13"), ("fill", "M -8 52 H 8 L 4 58 H -4 Z"),
             ("thin", "M -9 26 V 2 M 9 26 V 2 M -9 2 Q 0 -18 9 2")],
    "magnet": [("line", "M -44 -44 V 4 A 44 44 0 0 0 44 4 V -44 H 22 V 4 A 22 22 0 0 1 -22 4 V -44 Z"),
               ("line", "M -44 -28 H -22 M 22 -28 H 44")],
    "bolt": [("line", "M 10 -58 L -28 6 H 0 L -12 58 L 32 -10 H 4 Z")],
    "switch": [("fill", _circle(-40, 10, 6) + " " + _circle(40, 10, 6)), ("line", "M -40 10 L 32 -20"),
               ("thin", "M -58 10 H -46 M 46 10 H 58")],
    # Science and everyday.
    "sun": [("line", _circle(0, 0, 24)), ("line", _rays(8, 34, 52))],
    "rain": [("line", "M -44 14 H 42 A 20 20 0 0 0 40 -24 A 28 28 0 0 0 -10 -38 A 22 22 0 0 0 -46 -18 "
                      "A 16 16 0 0 0 -44 14 Z"),
             ("thin", _lines(*[(x, y, x - 6, y + 14)
                               for x, y in ((-26, 26), (-4, 30), (18, 26), (-14, 46), (8, 48))]))],
    "flask": [("line", "M -14 -52 H 14 M -9 -52 V -14 L -40 40 A 6 6 0 0 0 -35 50 H 35 A 6 6 0 0 0 40 40 L 9 -14 "
                       "V -52"),
              ("thin", "M -27 18 H 27"), ("fill", _circle(-6, 2, 3) + " " + _circle(5, -8, 2.5))],
    "atom": [("thin", " ".join(_ellipse(0, 0, 54, 18, t) for t in (0, 60, 120))), ("fill", _circle(0, 0, 8))],
    "eye": [("line", "M -60 0 C -30 -40 30 -40 60 0 C 30 40 -30 40 -60 0 Z"), ("line", _circle(0, 0, 20)),
            ("fill", _circle(0, 0, 9))],
    "heart": [("line", "M 0 46 C -40 20 -56 -4 -50 -24 C -44 -46 -12 -50 0 -26 C 12 -50 44 -46 50 -24 "
                       "C 56 -4 40 20 0 46 Z")],
    "leaf": [("line", "M -46 46 C -52 -10 -10 -50 50 -50 C 50 10 10 52 -46 46 Z"),
             ("thin", "M -46 46 L 30 -30 M -18 18 L -20 -8 M -18 18 L 8 20 M 4 -4 L 4 -26 M 4 -4 L 26 -4")],
    "house": [("line", "M -52 -2 L 0 -48 L 52 -2 M -38 -14 V 48 H 38 V -14"), ("thin", _rect(-10, 18, 20, 30)),
              ("thin", _rect(14, 0, 14, 14))],
    "coins": [("line", _ellipse(0, -18, 42, 13)), ("line", "M -42 -18 V 26 A 42 13 0 0 0 42 26 V -18"),
              ("thin", "M -42 -3 A 42 13 0 0 0 42 -3 M -42 11 A 42 13 0 0 0 42 11")],
    "clock": [("line", _circle(0, 0, 50)), ("thin", _rays(12, 40, 46)), ("line", "M 0 0 V -30 M 0 0 L 20 12"),
              ("fill", _circle(0, 0, 4))],
    "mic": [("line", _rect(-16, -54, 32, 58, 16)), ("thin", "M -16 -30 H 16 M -16 -18 H 16"),
            ("line", "M -30 -16 V -8 A 30 30 0 0 0 30 -8 V -16 M 0 22 V 46 M -20 46 H 20")],
    "speaker": [("line", "M -46 -16 H -26 L 4 -42 V 42 L -26 16 H -46 Z"),
                ("line", "M 20 -18 A 24 24 0 0 1 20 18 M 32 -34 A 44 44 0 0 1 32 34")],
    "magnifier": [("line", _circle(-12, -12, 32)), ("line", "M 12 12 L 46 46"),
                  ("thin", "M -28 -24 A 20 20 0 0 1 -14 -32")],
    "book": [("line", "M 0 -34 C -20 -44 -44 -44 -56 -36 V 40 C -44 32 -20 32 0 42 C 20 32 44 32 56 40 V -36 "
                      "C 44 -44 20 -44 0 -34 Z"), ("thin", "M 0 -34 V 42"),
             ("thin", _lines((-44, -22, -12, -18), (-44, -8, -12, -4), (-44, 6, -12, 10), (12, -18, 44, -22),
                             (12, -4, 44, -8), (12, 10, 44, 6)))],
    "drop": [("line", "M 0 -54 C 18 -28 38 -6 38 16 A 38 38 0 0 1 -38 16 C -38 -6 -18 -28 0 -54 Z"),
             ("thin", "M 22 14 A 22 22 0 0 1 8 34")],
    "flame": [("line", "M 0 -56 C 14 -30 40 -16 38 14 A 38 38 0 0 1 -38 14 C -40 -12 -18 -22 -14 -44 "
                       "C -6 -30 -2 -24 0 -56 Z"),
              ("thin", "M 0 50 C -16 46 -20 30 -10 16 C -6 24 -2 26 2 12 C 14 24 18 44 0 50 Z")],
    "rook": [("line", "M -38 54 H 38 V 44 H -38 Z M -28 44 L -22 -16 H 22 L 28 44 M -32 -16 H 32 V -26 H -32 Z "
                      "M -32 -26 V -52 H -20 V -42 H -6 V -52 H 6 V -42 H 20 V -52 H 32 V -26")],
}


def _fitted(parts, top, bottom):
    """Parts drawn in units of their own, from top to bottom, moved and scaled into the 128-unit frame."""
    k, mid = 128 / (bottom - top), (top + bottom) / 2
    return [(cid, name, (x * k, (y - mid) * k), size * k, turn, *label) for cid, name, (x, y), size, turn, *label
            in parts]


# Where a part's pins sit in its own frame: the crank's crank pin, and the rod's big end. A group that holds a crank, a
# rod and a piston moves as a real engine does: the rod hangs from the piston's pin and holds the crank pin.
PINS = {"crank": (0.0, -36.0), "rod": (0.0, 64.0)}
# The engine's rod and crank sizes, and its height in its own units, top to bottom: a long rod and a short throw keep
# the piston in its bore and clear of the crank's counterweight at the bottom of its stroke.
_ROD, _CRANK, _SPAN = 150, 80, (-114, 144)
# The engine's parts, placed so they interlock: the piston in the bore, its rod down to the crank, the valves seated
# in the head's two ports and the spark plug between them. Each part keeps its own pivot, so it can move alone.
COMPOUNDS = {
    "engine": _fitted([("block", "cylinder", (0, -6), 128, 0),
                       ("intake", "valve", (-17, -113), 96, 0, "intake", "left"),
                       ("exhaust", "valve", (17, -113), 96, 0, "exhaust", "right"),
                       ("spark", "spark", (0, -65), 64, 0, "spark", "above"), ("piston", "piston", (0, 6), 136, 0),
                       ("rod", "rod", (0, 6), _ROD, 0),
                       ("crank", "crank", (0, 6 + (PINS["rod"][1] * _ROD - PINS["crank"][1] * _CRANK) / 128), _CRANK,
                        0, "crank", "right")],
                      *_SPAN),
}
# Named poses a step can give a compound stencil, as "move": {"e": "intake"}. Each moves its parts from where they were
# drawn, (dx, dy, degrees) in the parts' own units about each part's pivot: the piston drops by the stroke, twice the
# crank's throw. The intake opens by 9 as the piston drops away; the exhaust opens by 5, since the piston rises to
# meet it, and keeps about 5 px clear of it.
_STROKE = 2 * PINS["crank"][1] * -_CRANK / 128
_FIT = 128 / (_SPAN[1] - _SPAN[0])  # The engine's own units, fitted into the 128-unit frame as _fitted fits them.
_DOWN = {"piston": (0, _STROKE, 0), "rod": (0, _STROKE, 0), "crank": (0, 0, 180)}
_UP = {"piston": (0, 0, 0), "rod": (0, 0, 0), "crank": (0, 0, 0)}
_SHUT = {"intake": (0, 0, 0), "exhaust": (0, 0, 0)}
_ENGINE = {"intake": {**_DOWN, **_SHUT, "intake": (0, 9, 0)}, "compression": {**_UP, **_SHUT},
           "power": {**_DOWN, **_SHUT}, "exhaust": {**_UP, **_SHUT, "exhaust": (0, 5, 0)}}
POSES = {"engine": {name: {cid: (x * _FIT, y * _FIT, turn) for cid, (x, y, turn) in pose.items()}
                    for name, pose in _ENGINE.items()}}
NAMES = tuple(STENCILS) + tuple(COMPOUNDS)
