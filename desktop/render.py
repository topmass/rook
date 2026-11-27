"""Rook's render tool, layer one: a scene format that a model writes in one reply, a checker for it, and a sampler
that turns a scene into grain targets for the swarm. Nothing here draws on screen. Pure Python, and Cairo for measuring.

The format (a JSON object; every key not listed is an error):
    scene  {"name"?, "title"?, "size"?, "view"?: [w, h] = [100, 100], "parts": [part or group, ...],
            "steps"?: [step, ...]}
    layout {"name"?, "title"?, "layout", "nodes": [node, ...], "links"?: [[from, to] or [from, to, label], ...],
            "steps"?}, a scene with no view or parts
    node   {"id", "stencil"?, "label"?, "lead"?, "quiet"?}
    part   {"id", exactly one shape, "fill"?, "width"?, "weight"?, "lead"?, "quiet"?, "motion"?, "speed"?,
            "reverse"?, "label"?, "label_at"?, "repeat"?}
    shapes "circle": [cx, cy, r]   "ellipse": [cx, cy, rx, ry]   "rect": [x, y, w, h] (+ "radius")
           "line": [x1, y1, x2, y2]   "arrow": [x1, y1, x2, y2] (+ "bend")   "arc": [cx, cy, r, start, end]
           "poly": [x, y, x, y, ...] (+ "closed")   "path": "SVG path data: M L H V C S Q T A Z, absolute or relative"
           "link": [from id, to id] (+ "curve")
           "stencil": a drawn object by name, placed by "at": [x, y], with "size" (its width) and "rotate"
    group  {"id", "group": [part, ...], "translate"?: [dx, dy], "rotate"?: degrees, "scale"?: s, "repeat"?}
    repeat {"count", "about": [x, y], "rotate"?: degrees}  or  {"count", "step": [dx, dy]}
    step   {"light": [id, ...], "move"?: {id: move, ...}, "caption"?}
    move   {"to"?: [dx, dy], "rotate"?: degrees, "about"?: [x, y], "scale"?: s}
Coordinates are in the view's own units, x to the right and y down. Angles are degrees, clockwise on screen, and 0 points
right. A part is an outline unless "fill" is true. "width" is the outline's thickness in view units; it defaults to
DEFAULT_WIDTH of the view's shorter side in an icon, and to DIAGRAM_LINE px in a diagram. "bend" bows an arrow's
middle sideways by that many view units, to the right of its travel when positive. "arc" runs clockwise from start to
end. A link is an arrow from one part to another, at the top level: its ends sit just outside both parts, and it
bends round parts in its way. "curve" is one of CURVES. "over" and "under" bow a link or an arrow up or down on screen,
"left" and "right" bow it sideways, and "straight" keeps it straight; a link without it chooses. A repeat with "about"
turns each copy a further
"rotate" degrees (360 / count by default) about that point; one with "step" moves each copy a further [dx, dy].
A stencil is a well-drawn object: STENCILS. Its "at" is its pivot, the centre for most; a crank's journal, a
valve's stem top, and a piston's and a rod's pins. Its size defaults to a quarter of the view. "engine" is a compound
stencil, a group of parts that fit together: ENGINE. A step lights one of them as "engine.piston", and moves the
whole engine through a stroke with a named pose: "move": {"engine": "intake"}; its poses are POSES.
A layout places its nodes for you, LAYOUTS: "row" left to right, "column" top to bottom, "cycle" round a ring
from the top, clockwise, and "hub" with the first node in the middle and the rest round it. A node is a stencil, or a
box with its label inside when it has no stencil. Links join nodes in order (the ring closes, the hub joins its middle
to each), unless "links" lists them. A link's id is "from-to". A step lights nodes and links by id.
"lead" makes a part denser and brighter, to lead the eye; "quiet" makes it fainter, for context.
A group's children are drawn in the group's own frame: the group scales them, rotates them about its origin, then moves
them by translate. Groups hold parts only, one level deep. A child's full id is "group.child".
"motion" is one of MOTIONS (still by default), "speed" one of SPEEDS (normal by default), and "reverse" turns a flow or
a turn the other way. "weight" (1 by default) gives a part more or less of the dust. "label" is a short word drawn
near the part, at "label_at": one of LABEL_AT (below by default). A step lights a part, a whole group, or every
copy of a repeated part by naming its id. Copies of a repeated part share their part's id and its grains; a step cannot
single out one copy.
A step's "move" sets a part's or a whole group's pose for that step, from the pose it was drawn in: scale and rotate
about "about" (its centre by default), then move by "to". The dust flies to the new pose as the step starts, and the
pose holds through later steps until one moves the part again. A part turns the short way, and a half turn goes
clockwise. Links follow the parts they join. The whole scene shows every part as it was drawn.
A scene's "size" is one of SIZES. An icon is one bold object; a diagram gets more and larger grains in a much
larger box. Without it, a scene with a label or more than DIAGRAM_PARTS parts is a diagram.

Limits are in LIMITS; a scene stays up SCENE_SECONDS after its turn ends, unless it is cleared. SCHEMA is the scene's
JSON Schema, built from the same tables the checker uses, so the two cannot drift.

Density (see sample). Each part is drawn into a coverage mask at the form's size, and grains land on its pixels with a
random offset inside each pixel, as the overlay's own forms do. Pixels on the mask's edge count three times as much as
inner ones (at most 55% of a part's grains go to its edge), so a filled area is covered evenly and its silhouette still
reads. Pixels are drawn without replacement until each has a grain, which keeps clumps and holes down. Parts share the
budget by weight * ink ** 0.8: a large part gets more grains, but less than in proportion, so small parts still read.
A fill's inner pixels count 0.4 each in that ink, since a fill reads by its silhouette. Every part with ink gets at
least max(8, budget / 60) grains. A step multiplies its lit parts' weight by STEP_GATHER and the others' by STEP_THIN.

Grain ownership (the morph contract). The engine has a fixed number of grains, and a form gives each grain an owner
part. sample(..., previous=form) keeps owners stable: a part id that is in both scenes keeps its grains, up to its new
count; when it shrinks, it lets go of an even spread of them. Grains of parts that are gone, and grains let go, form a
pool; a part that grows or is new takes the pooled grains nearest its new centre. Inside a part, grains and places are
matched by their angle around the part's centre, so a part's dust turns into its new shape without crossing itself.
The first scene, with no previous form, sorts every grain by its angle around the form's centre, as _by_angle does in
the overlay, so the swarm keeps its sides when it arrives from any other form.

The motion contract. A form (see sample) has, per grain: x, y (its home, in form pixels around the form's centre), part
(an index into form["parts"]), move (None for a grain that rests, or the tuple below), and bright (1, or the step's
light). Each entry of form["parts"] carries what its motion needs, in form pixels. targets(form, d) is the reference:
it returns every grain's place and brightness d seconds after the form began.
    still  Rests; the engine's own drift and loose grains keep it alive.
    flow   part["paths"]: [{"points": even polyline, "length", "closed"}], part["speed"] in px per second.
           move = (path, phase, side, tail). A grain sits phase of the way along its path, advancing speed / length per
           second (backwards with reverse), side * part["spread"] across it, at brightness 1.35 - 0.85 * tail. Phases
           are bunched into comets, a dense bright head and a thinning tail, so the motion shows on an even outline.
           About 45% of the part's grains stay still to hold the outline. A closed path runs round for ever. An open
           one (a line, an arrow, an arc) runs like the needle's thread: each cycle opens with a hidden share
           HIDDEN_SHARE, in which the grain waits unseen at the start, then it fades in, runs, and fades out at the end.
           The overlay's FLOW_PATHS consume this as it stands: (points, length / speed, spread, spread, 1.35, 0.5), one
           FLOW_PATHS entry per path. What Scene._shape_motion lacks is more than one path per form, the closed case
           (no hidden share, no fade), and comet brightness per grain instead of per place on the path.
    fall   part["lanes"]: [(x0, y0, x1, y1)], top to bottom, part["accel"] in px/s^2. move = (lane, phase, side). As the
           hourglass's trickle: a hidden share, then the grain drops down its lane from rest, u = (t / T) ** 2, and fades
           in and out at the ends; T = sqrt(2 * length / accel). The trickle in Scene._shape_motion is this with one
           lane; the engine needs a lane per grain.
    turn   part["centre"], part["radii"] (least and most), part["spin"] in radians per second, clockwise unless
           reverse. Every grain of the part rotates its home about the centre. New in the engine: a rotation of one
           part's targets, as SPIN does for a whole form.
    fizz   part["lanes"]: [(x0, y0, x1, y1)], each from a point of the part straight up to just above its top,
           part["rise"] in px per second. About 35% of the part's grains fizz.
           move = (lane, phase, sway). A grain waits hidden at the lane's foot, then rises along it with a small
           sideways sway, bright at first and fading to nothing at the top. New in the engine: lanes per grain, as fall.
    glare  part["band"]: {"dir": (dx, dy), "low", "high", "width", "period", "pass"}. The band is a soft line across
           dir that sweeps from low to high along dir in pass seconds, then rests until the period ends. move = (lane,
           home, off) for band grains, half the part's grains: lane is the chord through the part along dir, and home
           is the grain's place on it (0 to 1). Near the band a grain is drawn toward the band (plus off) and brightens
           up to 3.2 times; the part's other grains brighten up to 2.2 times. New in the engine: a shared clock per
           part and the pull toward the band.

Run python desktop/render.py --check [folder of sample scenes] for the self-check, and python desktop/render.py
--author < scene.json to check a scene as the author would: it prints the summary and the path of a preview PNG.
"""

import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time

import stencils
try:
    import cairo
except ImportError:  # The tool server only needs the format's words, the checker and the schema.
    cairo = None

MOTIONS = ("still", "flow", "turn", "fizz", "glare", "fall")
SPEEDS = ("slow", "normal", "fast")
LABEL_AT = ("below", "above", "left", "right", "inside")
LIMITS = {"parts": 24, "copies": 160, "repeat": 36, "steps": 8, "path_chars": 1200, "path_commands": 200,
          "poly_points": 64, "id": 24, "name": 32, "title": 60, "label": 24, "caption": 120, "coordinate": 10000,
          "aspect": 4, "bytes": 16000, "budget": (64, 8000)}
SCENE_SECONDS = 30  # How long a scene stays up after the turn that showed it ends, unless it is cleared.
DEFAULT_WIDTH = 0.035  # An outline's default width, as a share of the view's shorter side: about 4 px at today's size.
BOX = 124  # The form's box in pixels at 640 grains: the size of the overlay's own forms (the hourglass is 116 tall).
CANVAS = 720  # The width a scene's labels must stay inside: the overlay's canvas, 740 px, less a margin.
HIDDEN_SHARE = 0.22  # The share of an open flow's cycle that a grain waits unseen at the start.
FLOW_SPEED = {"slow": 20, "normal": 38, "fast": 70}  # px per second along a flow.
TURN_SPEED = {"slow": 0.35, "normal": 0.8, "fast": 1.8}  # radians per second.
FALL_ACCEL = {"slow": 32, "normal": 65, "fast": 130}  # px/s^2: the hourglass's trickle falls 31 px in about 1 s.
FIZZ_RISE = {"slow": 10, "normal": 18, "fast": 32}  # px per second.
GLARE_PERIOD = {"slow": 7.0, "normal": 4.5, "fast": 2.8}  # seconds from one pass of the band to the next.
SIZES = ("icon", "diagram")
CURVES = ("straight", "over", "under", "left", "right")
SIDE = {"over": (0.0, -1.0), "under": (0.0, 1.0), "left": (-1.0, 0.0), "right": (1.0, 0.0)}  # On screen, y down.
LINK_GAP = 14  # px outside a shape's convex hull and label at the 560 px box (~12 px dark air past dust stroke width).
MIN_LINK_BODY = 48  # Minimum visible link body in px at the 560 px box, scaled with the box.
# An arrowhead: its length is HEAD_LENGTH outline widths, its width at the base equals its length, and HEAD_GRAINS
# grains per px of its length draw it (at most HEAD_CAP of its arrow's grains), packed along its two sides to a sharp
# tip and filling it. On a short arrow it shrinks to HEAD_SHARE of the arrow, down to HEAD_MIN outline widths (or 60%
# of the arrow); a note asks for room only when even that does not fit.
HEAD_LENGTH, HEAD_SHARE, HEAD_GRAINS, HEAD_MIN = 2.6, 0.45, 4.5, 1.8
# A link is drawn as a line first: its shaft's still grains sit evenly along it, and links get ARROW_WEIGHT times a
# shape's share of the grains for their ink, and keep it through steps. A flowing link marches: one bright grain every
# MARCH_SPACING px (at most MARCH_SHARE of its grains), evenly spaced, walks to its head at one steady pace and fades
# out at the head's base. The march crosses the shaft in MARCH_SECONDS whatever its length, at a pace kept inside
# MARCH_PACE px per second, so short and long links feel alike; MARCH_HIDDEN of each grain's cycle is the unseen walk
# back. Every link marches on the same clock, so six links move together, not as six blinking things.
ARROW_WEIGHT, MARCH_SHARE, MARCH_SPACING, HEAD_CAP = 1.5, 0.3, 5.0, 0.5
MARCH_SECONDS = {"slow": 2.6, "normal": 1.7, "fast": 1.0}
MARCH_PACE, MARCH_HIDDEN = (14, 70), 0.12
HEAD_BRIGHT = 1.25  # A head's grains are this much brighter than its line's, so the tip reads, lit or not.
DIAGRAM_PARTS = 6  # A scene with more parts than this, or with any label, is a diagram unless it says its size.
ICON_BOX, DIAGRAM_BOX = 180, 560  # The longest side of a scene's drawing, in pixels.
# Grains, the box in pixels, and how large each grain is drawn against the swarm's own. A diagram's box shrinks only to
# leave room for labels at its sides inside CANVAS.
SIZE_FORM = {"icon": (960, ICON_BOX), "diagram": (1200, DIAGRAM_BOX)}
GRAIN_SCALE = {"icon": 1.15, "diagram": 1.5}
DIAGRAM_LINE = 7  # A diagram's default outline in pixels: thick enough for its larger grains, thin enough to read.
STENCIL_LINE = 5  # A stencil's line in pixels, at any size: it holds more detail than a plain shape's.
STRESS = {"lead": (1.6, 1.2), "quiet": (0.6, 0.55)}  # (grain weight, brightness) of a lead and a quiet part.
LAYOUTS = ("row", "column", "cycle", "hub")
NODE_PX = 128  # A layout node's largest size in pixels; crowded layouts make nodes smaller.
# A crisp line under a diagram's dust, so its shapes read at a glance: (px, alpha, the dust's brightness). OUTLINE_LOOK
# picks one, or None for no line. The owner chose "clear" (2026-11-23). Links, arrows and turning parts get no line, since
# their dust moves along or off it, and an icon keeps its bold dust alone.
OUTLINES = {"hairline": (1.0, 0.3, 1.0), "clear": (1.4, 0.62, 0.72)}
OUTLINE_LOOK = "clear"
# The labels' font: (px, letter spacing in px, the width of one capital with its spacing), measured with Pango.
LABEL_TYPE = {"icon": (10, 2.4, 9.6), "diagram": (13, 2.4, 12.0)}
LIT, UNLIT = 1.25, 0.55  # Brightness of the lit and the other parts in a step.
# Material dust draws a diagram's fine layer from per-part baked textures instead of simulating thousands of grains.
# A diagram starts quiet with nothing lit. A step lights the parts it names over GLOW_SECONDS.
MATERIAL = True
FINE = 0  # Kept at 0 so callers checking render.FINE see no simulated fine grains.
MAT_GLOW, LIFE_GLOW, GLOW_SECONDS = {False: 0.82, True: 2.75}, {False: 0.30, True: 1.65}, 0.35
# Diagram living grains split into permanent ambient grains and one travelling highlight swarm.
SWARM_SHARE = 0.62
SWARM_CAP = 3.0  # Max multiple of a part's whole-scene swarm share when lit, so small parts stay crisp.
SWARM_SPREAD = 0.24  # Stagger window in seconds across which the highlight swarm lifts off.
SWARM_LIGHT_START, SWARM_LIGHT_END = 0.22, 0.62  # Material and ambient wake window as the swarm arrives.
SWARM_DIM_START, SWARM_DIM_END = 0.04, 0.36  # Material and ambient dim window as the swarm departs.
# Living dance presets for diagrams: material drift, twinkle, and GPU spring wander, wisps, and sparks.
# Material drift stays within the 2x2 cell search margin so micro-dots never clip on cell midlines.
DIAGRAM_DANCES = ("subtle", "medium", "lively")
DANCE_PRESETS = {
    "off": {"mat_drift": 0.06, "mat_twinkle": 0.24, "mat_glint": 0.42, "live_amp": 0.0,
            "live_shimmer": 0.0, "live_grow": 0.0, "spark_cut": 0.85, "wisp": 0.0},
    "subtle": {"mat_drift": 0.11, "mat_twinkle": 0.34, "mat_glint": 0.65, "live_amp": 0.65,
               "live_shimmer": 0.26, "live_grow": 0.14, "spark_cut": 0.76, "wisp": 0.25},
    "medium": {"mat_drift": 0.15, "mat_twinkle": 0.44, "mat_glint": 0.90, "live_amp": 1.00,
               "live_shimmer": 0.38, "live_grow": 0.24, "spark_cut": 0.66, "wisp": 0.55},
    "lively": {"mat_drift": 0.18, "mat_twinkle": 0.55, "mat_glint": 1.20, "live_amp": 1.45,
               "live_shimmer": 0.50, "live_grow": 0.34, "spark_cut": 0.54, "wisp": 0.90},
}
DANCE = "medium"


def dance_preset(name=None):
    """Return active diagram dance tuning parameters for name or the default preset."""
    return DANCE_PRESETS.get(name or DANCE, DANCE_PRESETS["medium"])
# Diagram entrance: "draw" traces each line behind living sparks; "fly" flies the living grains in first.
DIAGRAM_ENTRANCES = ("draw", "fly")
DIAGRAM_ENTRANCE = "draw"
DRAW_SECONDS, DRAW_START, LABELS_AFTER = 1.1, 0.35, 1.0
STEP_GATHER, STEP_THIN = 1.5, 0.8  # How a step shifts grains toward its lit parts, as weights.
PREVIEW_KEEP, PREVIEW_AGE = 20, 900  # Author previews kept, and their age in seconds before they are removed.

# The key tables. Both the checker and SCHEMA read them. A kind is one of: id, name, text, bool, number, integer,
# numbers (named), pair, points, path, enum, repeat, parts, steps, ids.
SHAPE_KEYS = {"circle": ("numbers", ("x", "y", "r")), "ellipse": ("numbers", ("x", "y", "rx", "ry")),
              "rect": ("numbers", ("x", "y", "w", "h")), "line": ("numbers", ("x1", "y1", "x2", "y2")),
              "arrow": ("numbers", ("x1", "y1", "x2", "y2")), "arc": ("numbers", ("x", "y", "r", "start", "end")),
              "poly": ("points", None), "path": ("path", None), "link": ("link", None),
              "stencil": ("enum", stencils.NAMES)}
PART_KEYS = {"id": ("id", None), **SHAPE_KEYS, "at": ("pair", None), "size": ("number", (0.5, 10000)),
             "rotate": ("number", (-360, 360)), "lead": ("bool", None), "quiet": ("bool", None),
             "fill": ("bool", None), "width": ("number", (0.01, 1000)),
             "radius": ("number", (0, 1000)), "closed": ("bool", None), "bend": ("number", (-1000, 1000)),
             "weight": ("number", (0.1, 10)), "motion": ("enum", MOTIONS), "speed": ("enum", SPEEDS),
             "reverse": ("bool", None), "curve": ("enum", CURVES), "label": ("text", LIMITS["label"]),
             "label_at": ("enum", LABEL_AT),
             "repeat": ("repeat", None)}
GROUP_KEYS = {"id": ("id", None), "group": ("parts", None), "translate": ("pair", None),
              "rotate": ("number", (-360, 360)), "scale": ("number", (0.05, 20)), "repeat": ("repeat", None)}
REPEAT_KEYS = {"count": ("integer", (2, LIMITS["repeat"])), "about": ("pair", None),
               "rotate": ("number", (-360, 360)), "step": ("pair", None)}
STEP_KEYS = {"light": ("ids", None), "move": ("moves", None), "caption": ("text", LIMITS["caption"])}
MOVE_KEYS = {"to": ("pair", None), "rotate": ("number", (-360, 360)), "about": ("pair", None),
             "scale": ("number", (0.05, 20))}
FLIGHT = 1.0  # Seconds a moved part takes to fly to its step's pose.
SCENE_KEYS = {"name": ("name", None), "title": ("text", LIMITS["title"]), "size": ("enum", SIZES),
              "view": ("pair", None), "parts": ("parts", None), "steps": ("steps", None),
              "layout": ("enum", LAYOUTS), "nodes": ("parts", None), "links": ("links", None)}
NODE_KEYS = {"id": ("id", None), "stencil": ("enum", stencils.NAMES), "label": ("text", LIMITS["label"]),
             "lead": ("bool", None), "quiet": ("bool", None)}
ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
PATH_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}
_TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)|[\s,]+|(.)")


# The checker.

def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _got(v):
    """A few words that say what the author sent."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return f"{len(v)} numbers" if all(_number(n) for n in v) else f"a list of {len(v)} items"
    if isinstance(v, str):
        return repr(v if len(v) <= 30 else v[:27] + "...")
    if isinstance(v, dict):
        return "an object"
    return repr(v)


def _value(kind, detail, v):
    """None when v suits the kind, or what it needs, as words that follow the key's name."""
    big = LIMITS["coordinate"]
    if kind in ("id", "name"):
        most = LIMITS[kind]
        if not isinstance(v, str) or not ID.match(v) or len(v) > most:
            return f"needs a name of letters, digits, _ or -, starting with a letter, at most {most} long; got {_got(v)}"
    elif kind == "text":
        if not isinstance(v, str) or not v.strip():
            return f"needs text; got {_got(v)}"
        if len(v) > detail or "\n" in v:
            return f"needs one line of at most {detail} characters; got {len(v)}"
    elif kind == "bool":
        if not isinstance(v, bool):
            return f"needs true or false; got {_got(v)}"
    elif kind in ("number", "integer"):
        lo, hi = detail
        if not _number(v) or (kind == "integer" and v != int(v)) or not lo <= v <= hi:
            return f"needs {'a whole number' if kind == 'integer' else 'a number'} from {lo} to {hi}; got {_got(v)}"
    elif kind == "numbers":
        if not isinstance(v, list) or len(v) != len(detail) or not all(_number(n) for n in v):
            return f"needs [{', '.join(detail)}]; got {_got(v)}"
        if any(abs(n) > big for n in v):
            return f"has a number past {big}; keep coordinates inside the view"
    elif kind == "pair":
        if not isinstance(v, list) or len(v) != 2 or not all(_number(n) and abs(n) <= big for n in v):
            return f"needs two numbers [x, y]; got {_got(v)}"
    elif kind == "points":
        most = LIMITS["poly_points"]
        if (not isinstance(v, list) or len(v) < 4 or len(v) % 2 or len(v) > 2 * most
                or not all(_number(n) and abs(n) <= big for n in v)):
            return f"needs an even list of numbers, x then y, for 2 to {most} points; got {_got(v)}"
    elif kind == "path":
        if not isinstance(v, str) or not v.strip():
            return f"needs SVG path data as text, such as \"M 10 10 L 90 10\"; got {_got(v)}"
        if len(v) > LIMITS["path_chars"]:
            return f"has {len(v)} characters; the most is {LIMITS['path_chars']}"
        return _parse_path(v)[1]
    elif kind == "enum":
        if v not in detail:
            return f"needs one of {', '.join(detail)}; got {_got(v)}"
    elif kind == "link":
        if not isinstance(v, list) or len(v) != 2 or not all(isinstance(n, str) for n in v) or v[0] == v[1]:
            return f"needs the ids of two different parts, from and to, such as [\"sam\", \"rook\"]; got {_got(v)}"
    elif kind == "ids":
        if not isinstance(v, list) or not v or not all(isinstance(n, str) for n in v):
            return f"needs a list of part or group ids; got {_got(v)}"
    elif kind == "links":
        if not isinstance(v, list) or not all(
                isinstance(k, list) and len(k) in (2, 3) and all(isinstance(n, str) for n in k) for k in v):
            return f"needs a list such as [[\"mic\", \"rook\"], [\"rook\", \"out\", \"answer\"]]; got {_got(v)}"
    elif kind == "moves":
        if not isinstance(v, dict) or not v:
            return f"needs an object of part or group ids, such as {{\"piston\": {{\"to\": [0, 20]}}}}; got {_got(v)}"
    elif kind in ("repeat",):
        if not isinstance(v, dict):
            return f"needs an object such as {{\"count\": 8, \"about\": [50, 50]}}; got {_got(v)}"
    elif kind in ("parts", "steps"):
        if not isinstance(v, list) or not v:
            return f"needs a list with at least one item; got {_got(v)}"
    return None


def _keys(obj, table, where, errors):
    """Check each key of obj against its table entry. Unknown keys are errors, so a typo is never ignored."""
    for key, v in obj.items():
        if key not in table:
            errors.append(f"{where}: '{key}' is not a key here. Use {', '.join(table)}.")
            continue
        problem = _value(*table[key], v)
        if problem:
            errors.append(f"{where}: {key} {problem}.")
            obj[key] = None
    return {key: obj[key] for key in obj if key in table and obj[key] is not None}


def _parse_path(d):
    """SVG path data as absolute ops: ("M", x, y), ("L", x, y), ("C", x1, y1, x2, y2, x, y),
    ("A", rx, ry, angle, large, sweep, x, y) and ("Z",). Returns (ops, None) or (None, what is wrong)."""
    tokens = []
    for m in _TOKEN.finditer(d):
        if m.group(3):
            return None, f"has {m.group(3)!r} at character {m.start() + 1}, which is not a command or a number"
        if m.group(1) or m.group(2):
            tokens.append(m.group(1) or m.group(2))
    ops, i, cmd, count = [], 0, None, 0
    x = y = sx = sy = 0.0
    last_c = last_q = None
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd, i, count = tokens[i], i + 1, count + 1
        elif cmd is None or cmd in "Zz":
            return None, f"has a number, {tokens[i]}, where a command letter belongs"
        if count > LIMITS["path_commands"]:
            return None, f"has more than {LIMITS['path_commands']} commands"
        if not ops and cmd not in "Mm":
            return None, "needs to start with M"
        up, rel = cmd.upper(), cmd.islower()
        if up == "Z":
            ops.append(("Z",))
            x, y, last_c, last_q = sx, sy, None, None
            continue
        nums = []
        while len(nums) < PATH_ARGS[up]:
            if i >= len(tokens) or tokens[i].isalpha():
                return None, f"has {cmd} with too few numbers: it needs {PATH_ARGS[up]}"
            tok = tokens[i]
            if up == "A" and len(nums) in (3, 4) and tok not in ("0", "1"):
                if tok[0] not in "01":
                    return None, f"has an arc flag {tok}; arc flags are 0 or 1"
                tokens[i] = tok[1:]  # Flags may be written together, as in "a 5 5 0 01 10 10".
                tok = tok[0]
            else:
                i += 1
            n = float(tok)
            if abs(n) > LIMITS["coordinate"]:
                return None, f"has {tok}, past the coordinate limit of {LIMITS['coordinate']}"
            nums.append(n)
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if up == "M":
            x, y = nums[0] + ox, nums[1] + oy
            sx, sy = x, y
            ops.append(("M", x, y))
            cmd = "l" if rel else "L"  # More pairs after M are lines.
            last_c = last_q = None
        elif up in ("L", "H", "V"):
            x = nums[0] + ox if up in "LH" else x
            y = (nums[1] + oy if up == "L" else nums[0] + oy) if up in "LV" else y
            ops.append(("L", x, y))
            last_c = last_q = None
        elif up in ("C", "S"):
            if up == "C":
                c1 = (nums[0] + ox, nums[1] + oy)
                nums = nums[2:]
            else:
                c1 = (2 * x - last_c[0], 2 * y - last_c[1]) if last_c else (x, y)
            c2, end = (nums[0] + ox, nums[1] + oy), (nums[2] + ox, nums[3] + oy)
            ops.append(("C", *c1, *c2, *end))
            (x, y), last_c, last_q = end, c2, None
        elif up in ("Q", "T"):
            if up == "Q":
                q = (nums[0] + ox, nums[1] + oy)
                nums = nums[2:]
            else:
                q = (2 * x - last_q[0], 2 * y - last_q[1]) if last_q else (x, y)
            end = (nums[0] + ox, nums[1] + oy)
            ops.append(("C", x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y),
                        end[0] + 2 / 3 * (q[0] - end[0]), end[1] + 2 / 3 * (q[1] - end[1]), *end))
            (x, y), last_q, last_c = end, q, None
        else:
            x, y = nums[5] + ox, nums[6] + oy
            ops.append(("A", *nums[:5], x, y))
            last_c = last_q = None
    if not ops:
        return None, "has no commands"
    return ops, None


def _matrix(scale=1.0, rotate=0.0, translate=(0.0, 0.0), about=(0.0, 0.0)):
    """A Cairo-ordered matrix (xx, yx, xy, yy, x0, y0): scale and rotate about a point, then translate."""
    c, s = math.cos(math.radians(rotate)) * scale, math.sin(math.radians(rotate)) * scale
    ax, ay = about
    return (c, s, -s, c, ax - c * ax + s * ay + translate[0], ay - s * ax - c * ay + translate[1])


def _then(a, b):
    """The matrix that applies a, then b."""
    axx, ayx, axy, ayy, ax0, ay0 = a
    bxx, byx, bxy, byy, bx0, by0 = b
    return (bxx * axx + bxy * ayx, byx * axx + byy * ayx, bxx * axy + bxy * ayy, byx * axy + byy * ayy,
            bxx * ax0 + bxy * ay0 + bx0, byx * ax0 + byy * ay0 + by0)


def _copies(repeat, where, errors):
    """The matrices of a repeat's copies, or one identity matrix."""
    if not isinstance(repeat, dict):  # None, or a bad repeat that the part's own key check reports.
        return [_matrix()]
    rep = _keys(dict(repeat), REPEAT_KEYS, f"{where}: repeat", errors)
    count = rep.get("count")
    if count is None:
        if "count" not in repeat:
            errors.append(f"{where}: repeat needs count, the number of copies, from 2 to {LIMITS['repeat']}.")
        return [_matrix()]
    if ("about" in rep) == ("step" in rep):
        errors.append(f"{where}: repeat needs about [x, y] to turn copies round a point, or step [dx, dy] to set them "
                      "in a row; give one of them.")
        return [_matrix()]
    if "step" in rep:
        if "rotate" in rep:
            errors.append(f"{where}: repeat with step cannot rotate; drop rotate, or use about instead of step.")
        dx, dy = rep["step"]
        return [_matrix(translate=(k * dx, k * dy)) for k in range(count)]
    turn = rep.get("rotate", 360 / count)
    return [_matrix(rotate=k * turn, about=tuple(rep["about"])) for k in range(count)]


def _part(raw, where, view, group_matrix, errors):
    """A checked part with its defaults, or None."""
    p = _keys(dict(raw), PART_KEYS, where, errors)
    shapes = [k for k in SHAPE_KEYS if k in raw]
    if not shapes:
        errors.append(f"{where}: needs one shape: {', '.join(SHAPE_KEYS)}.")
        return None
    if len(shapes) > 1:
        errors.append(f"{where}: has {len(shapes)} shapes, {' and '.join(shapes)}; give each its own part.")
        return None
    shape = shapes[0]
    if shape not in p:
        return None
    args = p[shape]
    stencil = shape == "stencil"
    for key in ("at", "size", "rotate"):
        if key in raw and not stencil:
            errors.append(f"{where}: {key} only places a stencil; drop it.")
    if stencil:
        for key in ("fill", "width"):
            if key in raw:
                errors.append(f"{where}: a stencil draws its own lines; drop {key}.")
        if "at" not in raw:
            errors.append(f"{where}: a stencil needs at, the [x, y] of its centre.")
        if p.get("motion") == "flow":
            errors.append(f"{where}: flow runs along a line, and a stencil has none. Use turn, fizz, glare or fall, "
                          "or draw the line as its own part.")
    if raw.get("lead") and raw.get("quiet"):
        errors.append(f"{where}: give lead or quiet, not both.")
    if shape == "path":
        args = _parse_path(args)[0]
    elif shape == "poly":
        args = [(args[k], args[k + 1]) for k in range(0, len(args), 2)]
    if shape == "circle" and args[2] <= 0 or shape == "ellipse" and min(args[2:]) <= 0 \
            or shape == "rect" and min(args[2:]) <= 0 or shape == "arc" and args[2] <= 0:
        errors.append(f"{where}: {shape} needs sizes above 0; got {args}.")
    if shape in ("line", "arrow") and args[:2] == args[2:]:
        errors.append(f"{where}: {shape} starts and ends at the same point; give it two different points.")
    for key, owner in (("radius", "rect"), ("closed", "poly"), ("bend", "arrow")):
        if key in raw and shape != owner:
            errors.append(f"{where}: {key} only applies to a {owner}; drop it.")
    if "curve" in raw and shape not in ("arrow", "link"):
        errors.append(f"{where}: curve only applies to a link or an arrow; drop it.")
    if "curve" in raw and "bend" in raw:
        errors.append(f"{where}: give curve or bend, not both; curve is easier.")
    if shape == "link" and "repeat" in raw:
        errors.append(f"{where}: a link joins two parts once, at the top level; take it out of its group or repeat.")
    bend = p.get("bend", 0.0)
    if shape == "arrow" and p.get("curve") in SIDE and args[:2] != args[2:]:
        # The side as a word: the apex sits a sixth of the arrow's length off its line, on that side of the screen.
        length = math.dist(args[:2], args[2:])
        nx, ny = -(args[3] - args[1]) / length, (args[2] - args[0]) / length
        lean = nx * SIDE[p["curve"]][0] + ny * SIDE[p["curve"]][1]
        if abs(lean) < 0.3:
            errors.append(f"{where}: curve {p['curve']} bows an arrow across its own line, and this arrow runs that "
                          "way; use " + ("left or right" if p["curve"] in ("over", "under") else "over or under") + ".")
        bend = math.copysign(length / 6, lean)
    fill = p.get("fill", False)
    if fill and shape in ("line", "arrow", "arc", "link"):
        errors.append(f"{where}: a {shape} has no inside to fill; drop fill, or draw a poly or path.")
    motion = p.get("motion", "still")
    if "reverse" in raw and motion not in ("flow", "turn"):
        errors.append(f"{where}: reverse only applies to flow and turn; drop it.")
    if "speed" in raw and motion == "still":
        errors.append(f"{where}: speed does nothing on a still part; drop it, or give the part a motion.")
    if motion == "glare" and not fill and not stencil:
        errors.append(f"{where}: glare slides across a filled area; set fill to true, or use flow on an outline.")
    if "label_at" in raw and "label" not in raw:
        errors.append(f"{where}: label_at needs a label; add one or drop label_at.")
    place = _matrix(p.get("size", max(view) / 4) / 128, p.get("rotate", 0.0), tuple(p.get("at", (0, 0))))
    copies = [_then(_then(place, m) if stencil else m, group_matrix)
              for m in _copies(raw.get("repeat"), where, errors)]
    return {"id": p.get("id"), "shape": shape, "args": args, "fill": fill,
            "stress": "lead" if p.get("lead") else "quiet" if p.get("quiet") else None,
            "width": p.get("width"), "radius": p.get("radius", 0.0),
            "closed": p.get("closed", False) or fill, "bend": bend, "curve": p.get("curve"),
            "weight": p.get("weight", 1.0),
            "motion": motion, "speed": p.get("speed", "normal"), "reverse": p.get("reverse", False),
            "label": p.get("label"), "label_at": p.get("label_at", "below"), "copies": copies}


def _apply(m, x, y):
    xx, yx, xy, yy, x0, y0 = m
    return xx * x + xy * y + x0, yx * x + yy * y + y0


def _outline(part):
    """Points round a part, in its own frame, enough to bound it (main's exact path for link-free scenes)."""
    a, shape = part["args"], part["shape"]
    if shape in ("circle", "ellipse", "arc"):
        rx, ry = (a[2], a[3]) if shape == "ellipse" else (a[2], a[2])
        return [(a[0] + rx * math.cos(k * math.pi / 8), a[1] + ry * math.sin(k * math.pi / 8)) for k in range(16)]
    if shape == "rect":
        return [(a[0], a[1]), (a[0] + a[2], a[1]), (a[0], a[1] + a[3]), (a[0] + a[2], a[1] + a[3])]
    if shape in ("line", "arrow"):
        return [tuple(a[:2]), tuple(a[2:])]
    if shape == "poly":
        return list(a)
    if shape == "stencil":
        x0, y0, x1, y1 = _stencil(a)[1]
        return [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    return [op[k:k + 2] for op in a if op[0] in "MLC" for k in range(1, len(op), 2)] + [
        op[6:8] for op in a if op[0] == "A"]


def _main_ext(parts, bounds=None, verdict=False):
    """Main's _extent of some parts in the poses they have, each part's worked out once per validate() for 4 units a
    point. Once the budget is spent a part takes its box from bounds, an upper bound by part id, and the result is
    marked "bound". Without bounds (a part's first outline, which main also pays for) the points are always visited.
    Verdict work may draw on the whole budget, not just the current share."""
    w, boxes = _work(), []
    for part in parts:
        key = ("ext", part["id"], tuple(part["copies"]))
        ext = w.sups.get(key)
        if ext is None:
            a, shape = part["args"], part["shape"]
            npts = (16 if shape in ("circle", "ellipse", "arc") else 4 if shape in ("rect", "stencil") else
                    2 if shape in ("line", "arrow") else len(a) if shape == "poly" else
                    sum(3 if op[0] == "C" else 0 if op[0] == "Z" else 1 for op in a))  # As _outline counts them.
            cost = 4 * npts * len(part["copies"])
            if (w.draw(cost) if verdict else w.spend(cost)) or bounds is None:
                ext = w.sups[key] = _extent([part])
            else:
                ext = {"box": bounds[part["id"]], "circle": None, "bound": True}
        boxes.append(ext)
    if len(boxes) == 1:
        return boxes[0]
    return {"box": tuple(f(b["box"][k] for b in boxes) for k, f in enumerate((min, min, max, max))), "circle": None,
            "bound": any(b.get("bound") for b in boxes)}


def _extent(parts):
    """The box round some parts in view units, and the circle when there is exactly one plain circle."""
    pts = [_apply(m, *pt) for part in parts for m in part["copies"] for pt in _outline(part)]
    xs, ys = [pt[0] for pt in pts], [pt[1] for pt in pts]
    out = {"box": (min(xs), min(ys), max(xs), max(ys)), "circle": None}
    if len(parts) == 1 and parts[0]["shape"] == "circle" and len(parts[0]["copies"]) == 1:
        m, (cx, cy, r) = parts[0]["copies"][0], parts[0]["args"]
        out["circle"] = (*_apply(m, cx, cy), r * math.sqrt(abs(m[0] * m[3] - m[1] * m[2])))
    return out


def _centre(ext):
    x0, y0, x1, y1 = ext["box"]
    return ((x0 + x1) / 2, (y0 + y1) / 2) if ext["circle"] is None else ext["circle"][:2]


def _edge(ext, toward, gap):
    """Main's edge: where the line from the part's centre toward a point leaves its box or circle, plus gap."""
    cx, cy = _centre(ext)
    d = math.dist((cx, cy), toward) or 1.0
    ux, uy = (toward[0] - cx) / d, (toward[1] - cy) / d
    if ext["circle"]:
        reach = ext["circle"][2]
    else:
        x0, y0, x1, y1 = ext["box"]
        reach = min((x1 - x0) / 2 / abs(ux) if ux else math.inf, (y1 - y0) / 2 / abs(uy) if uy else math.inf)
    return cx + (reach + gap) * ux, cy + (reach + gap) * uy


# Thread-local Cairo/Pango state so concurrent validate() and bake threads never share a Cairo context.
_TLS = threading.local()
_LABEL_MEASURE_CACHE = {}
_LABEL_CACHE_MOST = 512  # Distinct label texts kept; the cache empties when it passes this.
_PANGO_READY = None

# One work budget per validate(), so a hostile scene cannot freeze the overlay's main loop. The unit is one
# half-plane test. Measured on this machine, legal scenes that spend it run 28,000 to 54,000 units per ms, so the
# whole budget is at most about 11 ms on top of the checks main already makes. The charges, each made before the work:
#   - an outline: 16 per point visited, 16 per copy of a circle, ellipse or rect, 256 per turned copy;
#   - a stencil's label box: 4 per copy and ink;
#   - a ray leaving a shape and its labels: 48 per outline crossed (16 half-planes, each with a division);
#   - a candidate curve: 4 per obstacle it sorts, then 16 per sample (15) and outline near it;
#   - the side search: 4 per obstacle and side; a link routed: 4 per obstacle unit;
#   - a min-link trial: 4 per node pair, and 16 per node pair for a push pass; its reroute pays the charges above;
#   - pass 2 (ends that crowd one node): 64 per pair of ends compared;
#   - main's box of a part in a new pose (a move near the view's edge, or a boxed part): 4 per point and copy;
#     a move's edge verdict may draw on the whole budget, past its step's share.
# When a share runs out nothing raises: each remaining link goes straight between its two shapes with the end gap,
# and each remaining outline of a path, poly, line, arc or stencil is the plain box of its points, the box main uses.
# Link ends get their outlines first, circles, ellipses and rects stay exact, and the edge check of a move is main's,
# so a spent budget never refuses a scene that main and an unlimited budget both accept. Near an edge with the budget
# spent, a move's outline bound refuses only a part wholly outside the view. Not charged, as main pays the same:
# parsing, a part's first box and pivot, group unions (at most 24 x 16), and the straight fallback (32 tests a link).
WORK_BUDGET = 300_000


class _Work:
    """The work counter of one validate(). `stop` is the current share: the base pose, then one share per step."""

    def __init__(self, limit=WORK_BUDGET):
        self.used, self.limit, self.stop, self.out, self.ran_out = 0, limit, limit, False, False
        self.sups, self.centres = {}, {}  # Outlines and pivots already worked out in this validate().
        self.boxed = set()  # Parts whose outline is main's box because the budget ran out.

    def share(self, parts_left):
        """Start a new share: an even split of what is left over the poses still to come."""
        self.stop, self.out = self.used + (self.limit - self.used) // max(1, parts_left), False

    def spend(self, n):
        """Charge n units. False, and nothing charged, once the share is spent."""
        if self.out or self.used + n > self.stop:
            self.out = self.ran_out = True
            return False
        self.used += n
        return True

    def draw(self, n):
        """Charge n units of verdict work against the whole budget, past this share's stop. False, and nothing
        charged, once the whole budget is spent. Going past the stop spends the share, so routing degrades."""
        if self.used + n > self.limit:
            self.ran_out = True
            return False
        self.used += n
        if self.used >= self.stop:
            self.out = self.ran_out = True
        return True


def _work():
    w = getattr(_TLS, "work", None)
    return w if w is not None else _Work(math.inf)  # Outside validate(), as in a check: no budget, no cache.


def _thread_cr():
    if not cairo:
        return None
    cr = getattr(_TLS, "cr", None)
    if cr is None:
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1))
        _TLS.cr = cr
    return cr


# Every obstacle the router sees (part, group, repeat, label box, link end) is ONE 16-direction support polygon:
# a 16-tuple of max dot products in _SUP_DIRS (angles k * 22.5 deg). Indices 0, 4, 8, 12 are +x, +y, -x, -y, so
# the AABB is (-h[8], -h[12], h[0], h[4]). Containment is exact for rects and honest (<= 1.96% conservative) for curves.
_SUP_N = 16
_SUP_DIRS = tuple((math.cos(k * math.pi / 8.0), math.sin(k * math.pi / 8.0)) for k in range(_SUP_N))
_SUP_DIAG = tuple((k, _SUP_DIRS[k][0], _SUP_DIRS[k][1]) for k in range(_SUP_N) if k & 3)
_SUP_SIN = math.sin(math.pi / 8.0)


def _sup_box(h):
    return (-h[8], -h[12], h[0], h[4])


def _sup_centre(h):
    return ((h[0] - h[8]) * 0.5, (h[4] - h[12]) * 0.5)


def _sup_rect(r):
    x0, y0, x1, y1 = r
    return tuple((nx * x1 if nx >= 0.0 else nx * x0) + (ny * y1 if ny >= 0.0 else ny * y0) for nx, ny in _SUP_DIRS)


def _sup_pts(pts):
    out = [0.0] * _SUP_N
    for k in range(_SUP_N // 2):  # Direction k + 8 is the opposite of k, so one pass gives both.
        nx, ny = _SUP_DIRS[k]
        dots = [nx * x + ny * y for x, y in pts]
        out[k], out[k + 8] = max(dots), -min(dots)
    return tuple(out)


def _sup_union(sups):
    return sups[0] if len(sups) == 1 else tuple(map(max, *sups))


def _sup_verts(h):
    """The 16 vertices of the circumscribed 16-gon defined by support tuple h."""
    out = []
    inv = 1.0 / _SUP_SIN
    for k in range(_SUP_N):
        j = (k + 1) & 15
        nx0, ny0 = _SUP_DIRS[k]
        nx1, ny1 = _SUP_DIRS[j]
        h0, h1 = h[k], h[j]
        out.append(((h0 * ny1 - h1 * ny0) * inv, (nx0 * h1 - nx1 * h0) * inv))
    return out


def _sup_transform(h, m):
    """Transform a 16-direction support polygon by affine matrix m. Exact for translations and uniform positive scales;
    transforms the 16 circumscribed vertices once for rotations/shears (honest containment, <= 1.96% conservative)."""
    m0, m1, m2, m3, m4, m5 = m
    if abs(m1) < 1e-9 and abs(m2) < 1e-9 and m0 > 0.0 and abs(m0 - m3) < 1e-9:
        return tuple(m0 * hk + nx * m4 + ny * m5 for (nx, ny), hk in zip(_SUP_DIRS, h))
    tverts = [(m0 * x + m2 * y + m4, m1 * x + m3 * y + m5) for x, y in _sup_verts(h)]
    return _sup_pts(tverts)


def _sup_within(x, y, h, req):
    """True if (x, y) lies strictly inside the support polygon inflated by req (4 AABB + <= 12 diagonal checks)."""
    if x <= -h[8] - req or x >= h[0] + req or y <= -h[12] - req or y >= h[4] + req:
        return False
    for k, nx, ny in _SUP_DIAG:
        if nx * x + ny * y >= h[k] + req:
            return False
    return True


def _sup_dist(x, y, h):
    """Signed outside distance to the 16-gon (0 when inside)."""
    return max(0.0, max(nx * x + ny * y - hk for (nx, ny), hk in zip(_SUP_DIRS, h)))


def _sup_ray_exit(ox, oy, ux, uy, h, gap):
    """Farthest t along ray (ox, oy) + t*(ux, uy) inside support polygon inflated by gap, or -inf if missed."""
    lo, hi = -math.inf, math.inf
    for (nx, ny), hk in zip(_SUP_DIRS, h):
        num = hk + gap - (nx * ox + ny * oy)
        den = nx * ux + ny * uy
        if den > 1e-12:
            t = num / den
            if t < hi:
                hi = t
        elif den < -1e-12:
            t = num / den
            if t > lo:
                lo = t
        elif num < -1e-9:
            return -math.inf
    return hi if lo <= hi + 1e-9 else -math.inf


def _arc_points(x0, y0, rx, ry, angle, large, sweep, x, y):
    """Bounded outer tangent polygon of an SVG endpoint arc (<= 17 pts, independent of radius/view, strictly containing)."""
    if (x0, y0) == (x, y) or not rx * rx or not ry * ry:  # A radius too small to square is a line.
        return [(x, y)]
    rx, ry, phi = abs(rx), abs(ry), math.radians(angle)
    c, s = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x) * 0.5, (y0 - y) * 0.5
    x1, y1 = c * dx + s * dy, -s * dx + c * dy
    grow = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if grow > 1.0:  # SVG scales radii that cannot reach up to fit; hypot keeps a tiny radius from overflowing.
        g = math.sqrt(grow) if grow < math.inf else math.hypot(x1 / rx, y1 / ry)
        rx, ry = rx * g, ry * g
    if not math.isfinite(rx * rx * ry * ry):  # Radii far apart in size scale past any float: a line, as drawn.
        return [(x, y)]
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    # The true centre even when the ends almost meet: the chord's length cancels, so nothing overflows.
    chord = math.hypot(x1, y1) or 1.0
    ux1, uy1 = x1 / chord, y1 / chord
    den = rx * rx * uy1 * uy1 + ry * ry * ux1 * ux1 or 1.0
    k = math.sqrt(max(0.0, num / den)) * (-1.0 if large == sweep else 1.0)
    cx1, cy1 = k * rx * uy1 / ry, -k * ry * ux1 / rx
    cx, cy = c * cx1 - s * cy1 + (x0 + x) * 0.5, s * cx1 + c * cy1 + (y0 + y) * 0.5
    t1 = math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
    t2 = math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx)
    dt = t2 - t1
    if sweep and dt < 0.0:
        dt += 2.0 * math.pi
    elif not sweep and dt > 0.0:
        dt -= 2.0 * math.pi
    n = max(1, min(16, int(math.ceil(abs(dt) / (math.pi / 8.0)))))
    step = dt / n
    sec = 1.0 / math.cos(abs(step) * 0.5)
    pts = [(x, y)]
    for i in range(n):
        ang = t1 + (i + 0.5) * step
        ex, ey = rx * sec * math.cos(ang), ry * sec * math.sin(ang)
        pts.append((cx + c * ex - s * ey, cy + s * ex + c * ey))
    return pts


def _mid(a, b):
    return (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5


def _path_points(ops):
    """Bounded enclosing points for parsed SVG path ops without Cairo flattening: a two-level De Casteljau split for
    cubics (12 pts, the control points of four quarter curves) and outer tangent polygons for arcs (<= 17 pts,
    <= 1.96% overshoot)."""
    pts = []
    cx = cy = sx = sy = 0.0

    def split(p0, p1, p2, p3):
        q0, q1, q2 = _mid(p0, p1), _mid(p1, p2), _mid(p2, p3)
        r0, r1 = _mid(q0, q1), _mid(q1, q2)
        m = _mid(r0, r1)
        return (p0, q0, r0, m), (m, r1, q2, p3)

    for op in ops:
        cmd = op[0]
        if cmd == "M":
            cx = sx = op[1]
            cy = sy = op[2]
            pts.append((cx, cy))
        elif cmd == "L":
            cx, cy = op[1], op[2]
            pts.append((cx, cy))
        elif cmd == "C":
            for half in split((cx, cy), op[1:3], op[3:5], op[5:7]):
                for quarter in split(*half):
                    pts.extend(quarter[1:])
            cx, cy = op[5], op[6]
        elif cmd == "A":
            pts.extend(_arc_points(cx, cy, *op[1:]))
            cx, cy = op[6], op[7]
        elif cmd == "Z":
            cx, cy = sx, sy
    return pts or [(0.0, 0.0)]


def _part_sup(part):
    """A part's 16-direction support polygon across all its repeat copies in view units. Each outline is worked out
    once per validate() and charged to its budget; once the budget is spent a new outline is the box main uses."""
    a, shape, copies = part["args"], part["shape"], part["copies"]
    w = _work()
    key = (part["id"], tuple(copies))
    hit = w.sups.get(key)
    if hit is not None:
        return hit
    h_local = w.sups.get(part["id"])  # The outline in the part's own frame, the same in every pose.
    if shape in ("circle", "ellipse", "rect"):
        cost = 16 * len(copies)
    else:
        cost = 0 if h_local is not None or shape == "stencil" else 16 * (
            2 if shape in ("line", "arrow") else len(a) if shape == "poly" else 18 if shape == "arc"
            else sum(18 if op[0] == "A" else 13 if op[0] == "C" else 1 for op in a))
        if len(copies) > 1 or copies[0] != (1.0, 0.0, 0.0, 1.0, 0.0, 0.0):
            cost += 256 * len(copies)
    if not w.spend(cost) and shape not in ("circle", "ellipse", "rect"):  # These stay exact: 16 per copy at most.
        w.boxed.add(part["id"])
        hit = w.sups[key] = _sup_rect(_main_ext([part])["box"])
        return hit
    if shape == "circle":
        cx, cy, r = a
        sups = []
        for m0, m1, m2, m3, m4, m5 in copies:
            tcx, tcy = m0 * cx + m2 * cy + m4, m1 * cx + m3 * cy + m5
            sups.append(tuple(nx * tcx + ny * tcy + r * math.hypot(m0 * nx + m1 * ny, m2 * nx + m3 * ny)
                              for nx, ny in _SUP_DIRS))
        hit = w.sups[key] = _sup_union(sups)
        return hit
    if shape == "ellipse":
        cx, cy, rx, ry = a
        sups = []
        for m0, m1, m2, m3, m4, m5 in copies:
            tcx, tcy = m0 * cx + m2 * cy + m4, m1 * cx + m3 * cy + m5
            sups.append(tuple(nx * tcx + ny * tcy + math.hypot((m0 * nx + m1 * ny) * rx, (m2 * nx + m3 * ny) * ry)
                              for nx, ny in _SUP_DIRS))
        hit = w.sups[key] = _sup_union(sups)
        return hit
    if shape == "rect":
        x, y, wd, ht = a
        rad = min(part.get("radius", 0.0), wd * 0.5, ht * 0.5)
        inner = ((x + rad, y + rad), (x + wd - rad, y + rad), (x + wd - rad, y + ht - rad), (x + rad, y + ht - rad))
        sups = []
        for m0, m1, m2, m3, m4, m5 in copies:
            tc = tuple((m0 * px + m2 * py + m4, m1 * px + m3 * py + m5) for px, py in inner)
            if rad <= 0.0:
                sups.append(tuple(max(nx * px + ny * py for px, py in tc) for nx, ny in _SUP_DIRS))
            else:
                sups.append(tuple(max(nx * px + ny * py for px, py in tc)
                                  + rad * math.hypot(m0 * nx + m1 * ny, m2 * nx + m3 * ny)
                                  for nx, ny in _SUP_DIRS))
        hit = w.sups[key] = _sup_union(sups)
        return hit
    if h_local is not None:
        pass
    elif shape == "stencil":
        h_local = _stencil(a)[2]
    elif shape in ("line", "arrow"):
        h_local = _sup_pts((tuple(a[:2]), tuple(a[2:])))
    elif shape == "poly":
        h_local = _sup_pts(a)
    elif shape == "arc":
        # As Cairo draws it: the end comes round past the start, and a sweep of a whole turn or more is the circle.
        sweep = (a[4] if a[4] > a[3] else a[4] + 360.0) - a[3]
        sweep = sweep % 360.0 if sweep < 0.0 else sweep
        if sweep >= 360.0:
            h_local = tuple(nx * a[0] + ny * a[1] + a[2] for nx, ny in _SUP_DIRS)
        else:
            start, dt = math.radians(a[3]), math.radians(sweep)
            end = start + dt
            n = max(1, min(16, int(math.ceil(dt / (math.pi / 8.0)))))
            step = dt / n
            rsec = a[2] / math.cos(step * 0.5)
            pts = [(a[0] + a[2] * math.cos(start), a[1] + a[2] * math.sin(start)),
                   (a[0] + a[2] * math.cos(end), a[1] + a[2] * math.sin(end))]
            for i in range(n):
                ang = start + (i + 0.5) * step
                pts.append((a[0] + rsec * math.cos(ang), a[1] + rsec * math.sin(ang)))
            h_local = _sup_pts(pts)
    else:
        h_local = _sup_pts(_path_points(a))
    w.sups[part["id"]] = h_local
    if len(copies) == 1 and copies[0] == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0):
        hit = h_local
    else:
        hit = _sup_union([_sup_transform(h_local, m) for m in copies])
    w.sups[key] = hit
    return hit


def _scene_box(parts, view, size):
    """The drawing box in pixels, matching sample() when side labels take room from CANVAS."""
    box, char = SIZE_FORM[size][1], LABEL_TYPE[size][2]
    side = {at: max([char * len(p["label"]) + 7 for p in parts if p.get("label") and p.get("label_at") == at],
                    default=0) for at in ("left", "right")}
    return min(box, int((CANVAS - side["left"] - side["right"]) * max(view) / view[0]))


def _measure_label_px(text, size):
    """Measure a rendered uppercase label's exact Pango logical (width, height) in pixels, thread-safely."""
    key = (text.upper(), size)
    hit = _LABEL_MEASURE_CACHE.get(key)
    if hit is not None:
        return hit
    global _PANGO_READY
    if _PANGO_READY is None:
        try:
            import gi
            gi.require_version("Pango", "1.0")
            gi.require_version("PangoCairo", "1.0")
            from gi.repository import Pango, PangoCairo
            _PANGO_READY = (Pango, PangoCairo)
        except Exception:
            _PANGO_READY = False
    px, spacing, char = LABEL_TYPE[size]
    cr = _thread_cr()
    if _PANGO_READY and cr is not None:
        Pango, PangoCairo = _PANGO_READY
        layouts = getattr(_TLS, "pango_layouts", None)
        if layouts is None:
            layouts = {}
            _TLS.pango_layouts = layouts
        layout = layouts.get(size)
        if layout is None:
            layout = PangoCairo.create_layout(cr)
            font = Pango.FontDescription()
            font.set_family("Noto Serif")
            font.set_weight(Pango.Weight.HEAVY)
            font.set_absolute_size(px * Pango.SCALE)
            layout.set_font_description(font)
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
            layout.set_attributes(attrs)
            layouts[size] = layout
        layout.set_text(key[0], -1)
        _, logical = layout.get_pixel_extents()
        res = (float(logical.width), float(logical.height))
    else:
        res = (float(char * len(key[0])), float(round(px * 1.38)))
    if len(_LABEL_MEASURE_CACHE) >= _LABEL_CACHE_MOST:
        _LABEL_MEASURE_CACHE.clear()
    _LABEL_MEASURE_CACHE[key] = res
    return res


def _label_rect(part, scale, size, sup=None):
    """A part's rendered label box as (x0, y0, x1, y1) in view units, matching _labels() and overlay._render_labels."""
    if not part.get("label") or part["shape"] in ("link", "arrow"):
        return None
    if part["shape"] == "stencil" and _work().spend(4 * len(part["copies"]) * len(_stencil(part["args"])[3])):
        px = part["width"] * scale
        ink_boxes = _stencil(part["args"])[3]
        xs, ys = [], []
        for ink, bx0, by0, bx1, by1 in ink_boxes:
            hw = 0.0 if ink == "fill" else (px * (stencils.THIN if ink == "thin" else 1.0)) * 0.5 / scale
            for m in part["copies"]:
                if abs(m[1]) < 1e-9 and abs(m[2]) < 1e-9:
                    ax, ay = _apply(m, bx0, by0)
                    cx_, cy_ = _apply(m, bx1, by1)
                    xs.extend(((ax if ax < cx_ else cx_) - hw, (ax if ax > cx_ else cx_) + hw))
                    ys.extend(((ay if ay < cy_ else cy_) - hw, (ay if ay > cy_ else cy_) + hw))
                else:
                    pts = (_apply(m, bx0, by0), _apply(m, bx1, by0), _apply(m, bx1, by1), _apply(m, bx0, by1))
                    xs.extend((min(p[0] for p in pts) - hw, max(p[0] for p in pts) + hw))
                    ys.extend((min(p[1] for p in pts) - hw, max(p[1] for p in pts) + hw))
        x0, y0, x1, y1 = (min(xs), min(ys), max(xs), max(ys)) if xs else _sup_box(sup or _part_sup(part))
    else:
        x0, y0, x1, y1 = _sup_box(sup or _part_sup(part))
        if not part.get("fill"):
            m = part["copies"][0]
            hw = (part["width"] or 0.0) * 0.5 * math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))
            x0, y0, x1, y1 = x0 - hw, y0 - hw, x1 + hw, y1 + hw
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    lw_px, lh_px = _measure_label_px(part["label"], size)
    lw, lh = lw_px / scale, lh_px / scale
    at = part.get("label_at", "below")
    if at == "below":
        x, y, align = cx, y1 + 10.0 / scale, 0
    elif at == "above":
        x, y, align = cx, y0 - 10.0 / scale, 0
    elif at == "left":
        x, y, align = x0 - 7.0 / scale, cy, -1
    elif at == "right":
        x, y, align = x1 + 7.0 / scale, cy, 1
    else:
        x, y, align = cx, cy, 0
    left = x - lw * 0.5 if align == 0 else x - lw if align < 0 else x
    top = y - lh * 0.5
    return (left, top, left + lw, top + lh)


def _leave(sup, label_sups, ox, oy, toward, gap):
    """Where the ray from (ox, oy) toward `toward` clears sup and all its label support polygons by gap."""
    dx, dy = toward[0] - ox, toward[1] - oy
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    t = _sup_ray_exit(ox, oy, ux, uy, sup, gap)
    if not _work().spend(48 * (1 + len(label_sups))):
        label_sups = ()  # Out of budget: the shape alone, the floor every link needs.
    for lsup in label_sups:
        tl = _sup_ray_exit(ox, oy, ux, uy, lsup, gap)
        if tl > t:
            t = tl
    if not math.isfinite(t) or t < 0.0:
        t = 0.0
    return ox + t * ux, oy + t * uy


def _arrow_head_pts(e1, e2, q, width):
    """Return (tip, wing_left, wing_right, head_size) for a quadratic arrow (e1, q, e2)."""
    dx, dy = e2[0] - q[0], e2[1] - q[1]
    d = math.hypot(dx, dy)
    if d <= 1e-9:
        dx, dy = e2[0] - e1[0], e2[1] - e1[1]
        d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    length = math.dist(e1, e2)
    size = min(HEAD_LENGTH * width, max(min(HEAD_MIN * width, 0.6 * length), HEAD_SHARE * length))
    bx, by = e2[0] - ux * size, e2[1] - uy * size
    nx, ny = -uy * size * 0.5, ux * size * 0.5
    return e2, (bx + nx, by + ny), (bx - nx, by - ny), size


def _segs_intersect(a, b, c, d):
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2 = ccw(a, b, c), ccw(a, b, d)
    d3, d4 = ccw(c, d, a), ccw(c, d, b)
    return (d1 * d2 < 0 and d3 * d4 < 0)


def _dist2_tri(px, py, tri):
    """Squared distance from (px, py) to triangle tri (0 when inside)."""
    pos = neg = False
    best2 = math.inf
    for i in range(3):
        ax, ay = tri[i]
        bx, by = tri[(i + 1) % 3]
        dx, dy = bx - ax, by - ay
        rx, ry = px - ax, py - ay
        c = dx * ry - dy * rx
        if c > 1e-9:
            pos = True
        elif c < -1e-9:
            neg = True
        d2 = dx * dx + dy * dy
        if d2 <= 1e-12:
            sd2 = rx * rx + ry * ry
        else:
            t = max(0.0, min(1.0, (rx * dx + ry * dy) / d2))
            ex, ey = rx - t * dx, ry - t * dy
            sd2 = ex * ex + ey * ey
        if sd2 < best2:
            best2 = sd2
    return 0.0 if not (pos and neg) else best2


def _tris_near(tri1, tri2, pad=0.0):
    """True if two triangles overlap or come within pad of each other."""
    pad2 = pad * pad
    for p in tri1:
        if _dist2_tri(p[0], p[1], tri2) <= pad2:
            return True
    for p in tri2:
        if _dist2_tri(p[0], p[1], tri1) <= pad2:
            return True
    for i in range(3):
        for j in range(3):
            if _segs_intersect(tri1[i], tri1[(i + 1) % 3], tri2[j], tri2[(j + 1) % 3]):
                return True
    return False


# Curve sample schedule: 7 coarse samples reject blocked curves fast; 6 fine samples confirm clear paths.
# Plus 2 arrowhead wings = 15 total samples per candidate.
_CURVE_T_COARSE = (0.5, 0.25, 0.75, 0.0, 1.0, 0.125, 0.875)
_CURVE_T_FINE = (0.06, 0.18, 0.375, 0.625, 0.82, 0.94)
_CURVE_W_COARSE = tuple(((1.0 - t) * (1.0 - t), 2.0 * (1.0 - t) * t, t * t) for t in _CURVE_T_COARSE)
_CURVE_W_FINE = tuple(((1.0 - t) * (1.0 - t), 2.0 * (1.0 - t) * t, t * t) for t in _CURVE_T_FINE)
_CURVE_W = _CURVE_W_COARSE + _CURVE_W_FINE


def _proj_q(e1, e2, q):
    """Project control point q onto the perpendicular bisector of (e1, e2), matching _arrow_curve."""
    edx, edy = e2[0] - e1[0], e2[1] - e1[1]
    elen = math.hypot(edx, edy) or 1.0
    nx, ny = -edy / elen, edx / elen
    mx, my = (e1[0] + e2[0]) * 0.5, (e1[1] + e2[1]) * 0.5
    bend2 = (q[0] - mx) * nx + (q[1] - my) * ny
    return (mx + bend2 * nx, my + bend2 * ny)


def _is_forward(ctx, e1, e2):
    edx, edy = e2[0] - e1[0], e2[1] - e1[1]
    return (edx * ctx["cdx"] + edy * ctx["cdy"] > 0.0) and (edx * edx + edy * edy >= ctx["min_len2"])


def _link_clear(ctx, e1, e2, q, check_labels=True, check_bounds=True):
    """Check whether quadratic link (e1, q, e2) clears endpoint/obstacle/label support polygons and view bounds."""
    if not _is_forward(ctx, e1, e2):
        return False
    q = _proj_q(e1, e2, q)
    _, wl, wr, _ = _arrow_head_pts(e1, e2, q, ctx["pwidth"])
    cx0 = min(e1[0], q[0], e2[0], wl[0], wr[0])
    cx1 = max(e1[0], q[0], e2[0], wl[0], wr[0])
    cy0 = min(e1[1], q[1], e2[1], wl[1], wr[1])
    cy1 = max(e1[1], q[1], e2[1], wl[1], wr[1])
    margin, vw, vh = ctx["margin"], ctx["vw"], ctx["vh"]
    if check_bounds and (e1[0] < margin or e1[0] > vw - margin or e1[1] < margin or e1[1] > vh - margin
                         or e2[0] < margin or e2[0] > vw - margin or e2[1] < margin or e2[1] > vh - margin
                         or wl[0] < margin or wl[0] > vw - margin or wl[1] < margin or wl[1] > vh - margin
                         or wr[0] < margin or wr[0] > vw - margin or wr[1] < margin or wr[1] > vh - margin):
        return False
    req = ctx["req"]
    a, b = ctx["a"], ctx["b"]
    obs = ctx["obs_shapes"] + (ctx["all_labels"] if check_labels else ())
    if not _work().spend(4 * len(obs)):
        return False
    near = [h for h in obs if -h[8] <= cx1 + req and h[0] >= cx0 - req and -h[12] <= cy1 + req and h[4] >= cy0 - req]
    if not _work().spend(16 * 15 * (2 + len(near))):
        return False
    for wx, wy in (wl, wr):
        if _sup_within(wx, wy, a, req) or _sup_within(wx, wy, b, req):
            return False
        for h in near:
            if _sup_within(wx, wy, h, req):
                return False
    e1x, e1y, qx, qy, e2x, e2y = e1[0], e1[1], q[0], q[1], e2[0], e2[1]
    need_bounds = check_bounds and (cx0 < margin or cx1 > vw - margin or cy0 < margin or cy1 > vh - margin)
    for w0, w1, w2 in _CURVE_W:
        x = w0 * e1x + w1 * qx + w2 * e2x
        y = w0 * e1y + w1 * qy + w2 * e2y
        if need_bounds and (x < margin or x > vw - margin or y < margin or y > vh - margin):
            return False
        if _sup_within(x, y, a, req) or _sup_within(x, y, b, req):
            return False
        for h in near:
            if _sup_within(x, y, h, req):
                return False
    return True


def _route_links(parts, groups, view, size, errors, moving=(), base_cache=None, moved_names=None,
                 moved_part_sup=None):
    """Turn each link into an arrow using 16-direction support polygons for all shapes, groups, repeats, and labels."""
    w = _work()
    if base_cache is not None:
        box, scale, gap = base_cache["box"], base_cache["scale"], base_cache["gap"]
    else:
        box = _scene_box(parts, view, size)
        scale = box / max(view)
        gap = LINK_GAP / scale
    solid = [p for p in parts if p["shape"] != "link" and not p.get("link")]
    named = {p["id"]: [p] for p in solid}
    named.update({g: [p for p in solid if p["group"] == g] for g in groups})

    if base_cache is not None and moved_names is not None:
        part_sup = dict(base_cache["part_sup"])
        part_label = dict(base_cache["part_label"])
        node_sup = dict(base_cache["node_sup"])
        for p in solid:
            pid = p["id"]
            if pid in moved_names or pid not in part_sup:
                sup = moved_part_sup[pid] if (moved_part_sup is not None and pid in moved_part_sup) else _part_sup(p)
                part_sup[pid] = sup
                lr = _label_rect(p, scale, size, sup)
                part_label[pid] = _sup_rect(lr) if lr is not None else None
                node_sup[pid] = sup
        for g in groups:
            if named[g] and (g in moved_names or g not in node_sup):  # A group of links only has no outline.
                node_sup[g] = _sup_union([part_sup[p["id"]] for p in named[g]])
    else:
        ends = {n for p in parts if p["shape"] == "link" for n in p["args"]}
        first = sorted(solid, key=lambda p: p["id"] not in ends and p["group"] not in ends)  # Stable: ends first.
        part_sup = {p["id"]: _part_sup(p) for p in first}
        part_sup = {p["id"]: part_sup[p["id"]] for p in solid}
        part_label = {}
        for p in solid:
            lr = _label_rect(p, scale, size, part_sup[p["id"]])
            part_label[p["id"]] = _sup_rect(lr) if lr is not None else None
        node_sup = dict(part_sup)
        for g in groups:
            if named[g]:  # A group of links only has no outline.
                node_sup[g] = _sup_union([part_sup[p["id"]] for p in named[g]])

    node_labels = {name: tuple(part_label[p["id"]] for p in ps if part_label[p["id"]] is not None)
                   for name, ps in named.items()}

    obs_units = []
    seen_groups = set()
    for p in solid:
        if p["id"] in moving or p["group"] in moving:
            continue
        if p["group"]:
            g = p["group"]
            if g not in seen_groups:
                seen_groups.add(g)
                obs_units.append(({gp["id"] for gp in named[g]}, node_sup[g], node_labels[g]))
        else:
            obs_units.append(({p["id"]}, node_sup[p["id"]], node_labels[p["id"]]))

    base_routed = base_cache["routed"] if base_cache is not None else None
    dirty_links = set()
    if base_routed is not None and moved_names is not None:
        for part in parts:
            if part["shape"] != "link" and not part.get("link"):
                continue
            lid = part["id"]
            na, nb = part["link"] if part.get("link") else part["args"]
            if lid not in base_routed or na in moved_names or nb in moved_names:
                dirty_links.add(lid)
    else:
        dirty_links = None

    routed = []
    pair_cache = {}
    for part in parts:
        is_reused_link = (part["shape"] == "arrow" and bool(part.get("link")))
        if part["shape"] != "link" and not is_reused_link:
            continue
        lid = part["id"]
        if dirty_links is not None and lid not in dirty_links:
            args, bend, g_cached, raw_chosen, was_clear_c, ctx_c = base_routed[lid]
            na, nb = part["link"] if part.get("link") else part["args"]
            e1, e2 = (args[0], args[1]), (args[2], args[3])
            elen = math.dist(e1, e2) or 1.0
            nx, ny = -(e2[1] - e1[1]) / elen, (e2[0] - e1[0]) / elen
            q = ((e1[0] + e2[0]) * 0.5 + 2.0 * bend * nx, (e1[1] + e2[1]) * 0.5 + 2.0 * bend * ny)
            part.update(shape="arrow", args=list(args), link=(na, nb), bend=bend)
            routed.append({"part": part, "na": na, "nb": nb, "a": ctx_c["a"], "b": ctx_c["b"],
                           "la": ctx_c["la"], "lb": ctx_c["lb"], "ca": ctx_c["ca"], "cb": ctx_c["cb"],
                           "g": g_cached, "chosen": (e1, e2, q), "raw_chosen": raw_chosen,
                           "ctx": ctx_c, "reused": True, "was_clear": was_clear_c})
            continue

        link_ends = list(part["link"]) if is_reused_link else list(part["args"])
        where = f"part '{lid}'"
        if part["group"]:
            errors.append(f"{where}: a link joins two parts once, at the top level; take it out of its group.")
            continue
        missing = [n for n in link_ends if not named.get(n)]
        if missing:
            errors.append(f"{where}: link names '{missing[0]}', which is not a part or group drawn in this scene.")
            continue
        na, nb = link_ends
        a, b = node_sup[na], node_sup[nb]
        la, lb = node_labels[na], node_labels[nb]
        ca, cb = _sup_centre(a), _sup_centre(b)
        pwidth = part["width"]
        curve = part["curve"]
        pkey = (na, nb, curve, pwidth)
        cached_pair = pair_cache.get(pkey)
        if cached_pair is not None:
            chosen_p, was_clear_p, g_p, ctx_p = cached_pair
            routed.append({"part": part, "na": na, "nb": nb, "a": a, "b": b, "la": la, "lb": lb,
                           "ca": ca, "cb": cb, "g": g_p, "curve": curve, "chosen": chosen_p,
                           "raw_chosen": chosen_p, "ctx": ctx_p, "reused": False, "was_clear": was_clear_p})
            continue
        ends = {p["id"] for n in (na, nb) for p in named[n]}
        boxed_end = bool(ends & w.boxed)
        if boxed_end:  # A boxed end: main's verdicts, from main's boxes and centres.
            # The base pose pays for main's boxes as main does; a step's new pose is charged, and once the budget is
            # spent it takes the outline bound, which is too coarse to refuse on.
            outline = None if base_cache is None else {
                p["id"]: _sup_box(part_sup[p["id"]]) for n in (na, nb) for p in named[n]}
            ea, eb = _main_ext(named[na], outline), _main_ext(named[nb], outline)
            ma, mb = _centre(ea), _centre(eb)
            on = not (ea.get("bound") or eb.get("bound")) and (
                ea["box"][0] <= mb[0] <= ea["box"][2] and ea["box"][1] <= mb[1] <= ea["box"][3]
                or eb["box"][0] <= ma[0] <= eb["box"][2] and eb["box"][1] <= ma[1] <= eb["box"][3])
        else:
            on = _sup_dist(cb[0], cb[1], a) <= 1e-6 or _sup_dist(ca[0], ca[1], b) <= 1e-6
        if on:
            errors.append(f"{where}: '{na}' and '{nb}' sit one on the other, so a link has "
                          "no room between them. Move them apart, or drop the link.")
            continue

        obs_shapes, obs_labels = [], []
        for uids, h, lsups in obs_units:
            if uids & ends:
                continue
            encloses = (-h[8] - gap * 0.5 < ca[0] < h[0] + gap * 0.5 and -h[12] - gap * 0.5 < ca[1] < h[4] + gap * 0.5
                        and -h[8] - gap * 0.5 < cb[0] < h[0] + gap * 0.5 and -h[12] - gap * 0.5 < cb[1] < h[4] + gap * 0.5)
            if not encloses:
                obs_shapes.append(h)
                obs_labels.extend(lsups)

        cdx, cdy = cb[0] - ca[0], cb[1] - ca[1]
        length = math.hypot(cdx, cdy) or 1.0
        mid = ((ca[0] + cb[0]) * 0.5, (ca[1] + cb[1]) * 0.5)
        (x1, y1), (x2, y2) = _leave(a, (), ca[0], ca[1], cb, 0.0), _leave(b, (), cb[0], cb[1], ca, 0.0)
        room = math.dist((x1, y1), (x2, y2))
        if room < 0.5 or (x2 - x1) * cdx + (y2 - y1) * cdy <= 0:
            if boxed_end:  # Main's verdict; where main finds room, main's own straight link.
                (m1x, m1y), (m2x, m2y) = _edge(ea, mb, 0.0), _edge(eb, ma, 0.0)
                mroom = math.dist((m1x, m1y), (m2x, m2y))
                if mroom >= 0.5 and (m2x - m1x) * (mb[0] - ma[0]) + (m2y - m1y) * (mb[1] - ma[1]) > 0:
                    gm = min(gap, max(0.4 * gap, 0.2 * mroom), 0.3 * mroom)
                    part.update(shape="arrow", args=[*_edge(ea, mb, gm), *_edge(eb, ma, gm)], link=(na, nb), bend=0.0)
                    continue
                if (ea.get("bound") or eb.get("bound")) and math.dist(ma, mb) > 1e-6:
                    # A bound is too coarse to refuse on: the middle of the line between the centres.
                    part.update(shape="arrow", link=(na, nb), bend=0.0, args=[
                        ma[0] + 0.3 * (mb[0] - ma[0]), ma[1] + 0.3 * (mb[1] - ma[1]),
                        ma[0] + 0.7 * (mb[0] - ma[0]), ma[1] + 0.7 * (mb[1] - ma[1])])
                    continue
            errors.append(f"{where}: '{na}' and '{nb}' touch, so a link has no room between "
                          "them. Move them apart.")
            continue
        g = min(gap, max(0.4 * gap, 0.2 * room), 0.3 * room)
        req = g * 0.96
        margin = max(0.75, pwidth * 0.5)
        all_labels = la + lb + tuple(obs_labels)
        min_len = max(1.0, 0.4 * g)
        vw, vh = view[0], view[1]
        ctx = {"a": a, "b": b, "la": la, "lb": lb, "ca": ca, "cb": cb, "cdx": cdx, "cdy": cdy,
               "req": req, "pwidth": pwidth, "min_len2": min_len * min_len, "margin": margin,
               "vw": vw, "vh": vh, "obs_shapes": tuple(obs_shapes), "all_labels": all_labels}

        def _build_q(q, use_labels=True):
            e1 = _leave(a, la if use_labels else (), ca[0], ca[1], q, g)
            e2 = _leave(b, lb if use_labels else (), cb[0], cb[1], q, g)
            return e1, e2, _proj_q(e1, e2, q)

        def _build_straight(use_labels=True):
            sa, sb = ca, cb
            if abs(cdy) < abs(cdx) * 0.07:
                my = (ca[1] + cb[1]) * 0.5
                if _sup_dist(ca[0], my, a) <= 1e-6 and _sup_dist(cb[0], my, b) <= 1e-6:
                    sa, sb = (ca[0], my), (cb[0], my)
            elif abs(cdx) < abs(cdy) * 0.07:
                mx = (ca[0] + cb[0]) * 0.5
                if _sup_dist(mx, ca[1], a) <= 1e-6 and _sup_dist(mx, cb[1], b) <= 1e-6:
                    sa, sb = (mx, ca[1]), (mx, cb[1])
            e1 = _leave(a, la if use_labels else (), sa[0], sa[1], sb, g)
            e2 = _leave(b, lb if use_labels else (), sb[0], sb[1], sa, g)
            return e1, e2, ((e1[0] + e2[0]) * 0.5, (e1[1] + e2[1]) * 0.5)

        def _safe_forward_straight():
            c_nl = _build_straight(use_labels=False)
            if _is_forward(ctx, c_nl[0], c_nl[1]):
                return c_nl
            ux, uy = (x2 - x1) / room, (y2 - y1) / room
            g_small = min(g, 0.25 * room)
            se1 = (x1 + ux * g_small, y1 + uy * g_small)
            se2 = (x2 - ux * g_small, y2 - uy * g_small)
            return se1, se2, ((se1[0] + se2[0]) * 0.5, (se1[1] + se2[1]) * 0.5)

        def _build(side, k):
            if side is None:
                return _build_straight()
            return _build_q((mid[0] + side[0] * k * length, mid[1] + side[1] * k * length))

        def _score_cand(e1, e2, q, k_val):
            if not _is_forward(ctx, e1, e2):
                return False, (1, 1, 1, 1, 999, 999, 999, k_val)
            q = _proj_q(e1, e2, q)
            _, wl, wr, _ = _arrow_head_pts(e1, e2, q, pwidth)
            cx0 = min(e1[0], q[0], e2[0], wl[0], wr[0])
            cx1 = max(e1[0], q[0], e2[0], wl[0], wr[0])
            cy0 = min(e1[1], q[1], e2[1], wl[1], wr[1])
            cy1 = max(e1[1], q[1], e2[1], wl[1], wr[1])
            if not w.spend(4 * (len(obs_shapes) + len(all_labels))):
                return False, (1, 1, 1, 1, 999, 999, 999, k_val)
            near_s = [h for h in obs_shapes
                      if -h[8] <= cx1 + req and h[0] >= cx0 - req and -h[12] <= cy1 + req and h[4] >= cy0 - req]
            near_l = [h for h in all_labels
                      if -h[8] <= cx1 + req and h[0] >= cx0 - req and -h[12] <= cy1 + req and h[4] >= cy0 - req]
            if not w.spend(16 * 15 * (2 + len(near_s) + len(near_l))):
                return False, (1, 1, 1, 1, 999, 999, 999, k_val)
            oob = shape_hits = label_hits = 0
            e1x, e1y, qx, qy, e2x, e2y = e1[0], e1[1], q[0], q[1], e2[0], e2[1]
            need_bounds = (cx0 < margin or cx1 > vw - margin or cy0 < margin or cy1 > vh - margin)
            x_hi, y_hi = vw - margin, vh - margin

            def _hit_pt(x, y):
                nonlocal oob, shape_hits, label_hits
                if need_bounds and (x < margin or x > x_hi or y < margin or y > y_hi):
                    oob += 1
                if _sup_within(x, y, a, req) or _sup_within(x, y, b, req) or any(
                        _sup_within(x, y, h, req) for h in near_s):
                    shape_hits += 1
                if any(_sup_within(x, y, h, req) for h in near_l):
                    label_hits += 1

            _hit_pt(wl[0], wl[1])
            _hit_pt(wr[0], wr[1])
            for w0, w1, w2 in _CURVE_W_COARSE:
                _hit_pt(w0 * e1x + w1 * qx + w2 * e2x, w0 * e1y + w1 * qy + w2 * e2y)
            if oob == 0 and shape_hits == 0 and label_hits == 0:
                for w0, w1, w2 in _CURVE_W_FINE:
                    _hit_pt(w0 * e1x + w1 * qx + w2 * e2x, w0 * e1y + w1 * qy + w2 * e2y)
                    if oob or shape_hits or label_hits:
                        break
            clear = (oob == 0 and shape_hits == 0 and label_hits == 0)
            return clear, (0, 1 if shape_hits else 0, 1 if oob else 0, 1 if label_hits else 0,
                           shape_hits, oob, label_hits, k_val)

        def _analytical_ks(side, k_start):
            if not w.spend(4 * (2 + len(obs_shapes) + len(all_labels))):
                return [k_start]
            sx, sy = side
            tx, ty = cdx / length, cdy / length
            ax0, ay0, ax1, ay1 = _sup_box(_sup_union((a, *la)) if la else a)
            bx0, by0, bx1, by1 = _sup_box(_sup_union((b, *lb)) if lb else b)
            ea = max((px - ca[0]) * sx + (py - ca[1]) * sy for px in (ax0, ax1) for py in (ay0, ay1))
            eb = max((px - cb[0]) * sx + (py - cb[1]) * sy for px in (bx0, bx1) for py in (by0, by1))
            v_end_hi = max(0.0, (ea + eb) * 0.5 + g)
            v_end_lo = v_end_hi * 0.35
            avail = math.inf
            if sx > 1e-6:
                avail = min(avail, (vw - margin - mid[0]) / sx)
            elif sx < -1e-6:
                avail = min(avail, (mid[0] - margin) / (-sx))
            if sy > 1e-6:
                avail = min(avail, (vh - margin - mid[1]) / sy)
            elif sy < -1e-6:
                avail = min(avail, (mid[1] - margin) / (-sy))
            k_view = max(k_start, min(2.05, (2.0 * avail - v_end_hi) / length))

            k_need = 0.0
            cax, cay = ca[0], ca[1]
            for h in obs_shapes + list(all_labels):
                ox0, oy0, ox1, oy1 = -h[8], -h[12], h[0], h[4]
                u0, u1 = math.inf, -math.inf
                v0, v1 = math.inf, -math.inf
                for px, py in ((ox0, oy0), (ox1, oy0), (ox1, oy1), (ox0, oy1)):
                    rx, ry = px - cax, py - cay
                    u = (rx * tx + ry * ty) / length
                    v = rx * sx + ry * sy
                    if u < u0:
                        u0 = u
                    if u > u1:
                        u1 = u
                    if v < v0:
                        v0 = v
                    if v > v1:
                        v1 = v
                if u1 <= 0.02 or u0 >= 0.98 or v1 < -req:
                    continue
                if v0 < req + 0.25 * length:
                    u_mid = min(0.85, max(0.15, (max(0.0, u0) + min(1.0, u1)) * 0.5))
                    arch = 2.0 * u_mid * (1.0 - u_mid)
                    if arch > 1e-6:
                        k_obs = (v1 + req * 1.04 - (1.0 - arch) * v_end_lo) / (arch * length)
                        if k_obs > k_need:
                            k_need = k_obs

            if k_need > k_start + 0.02:
                k1 = min(k_view, max(k_start + 0.04, k_need))
                raw = [k1, min(k_view, k_need * 1.18), k_view]
            else:
                raw = [k_start, min(k_view, max(k_start + 0.14, 0.36)), k_view]
            ks = []
            for k in raw:
                if not ks or abs(k - ks[-1]) > 0.02:
                    ks.append(k)
            return ks[:3]

        def _try_side(side, k_start):
            ks = _analytical_ks(side, k_start)
            best_score = best_cand = prev_k = None
            for k in ks:
                cand = _build(side, k)
                clear, score = _score_cand(*cand, k)
                if clear:
                    lo_bound = prev_k if prev_k is not None else (k_start if k > k_start + 0.02 else None)
                    if lo_bound is not None:
                        lo, hi, best_c = lo_bound, k, cand
                        for _ in range(2):
                            m = (lo + hi) * 0.5
                            mc = _build(side, m)
                            if _link_clear(ctx, *mc, check_labels=True, check_bounds=True):
                                hi, best_c = m, mc
                            else:
                                lo = m
                        return True, hi, best_c, (0, 0, 0, 0, 0, 0, 0, hi)
                    return True, k, cand, score
                if best_score is None or score < best_score:
                    best_score, best_cand = score, cand
                prev_k = k
            return False, ks[0], best_cand, best_score

        vdx, vdy = (mb[0] - ma[0], mb[1] - ma[1]) if boxed_end else (cdx, cdy)  # A boxed end: main's verdict.
        if curve in SIDE and abs(vdy * SIDE[curve][0] - vdx * SIDE[curve][1]) < 0.3 * math.hypot(vdx, vdy):
            errors.append(f"{where}: curve {curve} bows a link across its own line, and this link runs that way; use "
                          + ("left or right." if curve in ("over", "under") else "over or under."))
            continue

        pnx, pny = -cdy / length, cdx / length
        perps = sorted(((pnx, pny), (-pnx, -pny)), key=lambda s: (s[1], s[0]))

        chosen = None
        was_clear = False
        if w.out or not w.spend(4 * len(obs_units)):
            chosen = _safe_forward_straight()
        elif curve in SIDE:
            ok, _, cand, _ = _try_side(SIDE[curve], 0.25)
            was_clear = ok
            if cand is not None and _is_forward(ctx, cand[0], cand[1]):
                chosen = cand
            else:
                fb = _build(SIDE[curve], 0.4)
                chosen = fb if _is_forward(ctx, fb[0], fb[1]) else _safe_forward_straight()
        elif curve == "straight":
            cand = _build(None, 0.0)
            if _is_forward(ctx, cand[0], cand[1]):
                chosen = cand
                was_clear = _link_clear(ctx, *cand, check_labels=True, check_bounds=True)
            else:
                chosen = _safe_forward_straight()
        else:
            cand = _build(None, 0.0)
            clear, straight_score = _score_cand(*cand, 0.0)
            if clear:
                chosen, was_clear = cand, True
            else:
                best_clear = []
                best_fallback = (straight_score, cand) if _is_forward(ctx, cand[0], cand[1]) else None
                for s_idx, s in enumerate(perps):
                    ok, k_hit, c_hit, sc_hit = _try_side(s, 0.14)
                    if ok:
                        best_clear.append((round(k_hit / 0.02), s_idx, c_hit))
                    elif c_hit is not None and _is_forward(ctx, c_hit[0], c_hit[1]):
                        if best_fallback is None or sc_hit < best_fallback[0]:
                            best_fallback = (sc_hit, c_hit)
                if best_clear:
                    best_clear.sort(key=lambda item: (item[0], item[1]))
                    chosen, was_clear = best_clear[0][2], True
                else:
                    chosen = best_fallback[1] if best_fallback is not None else _safe_forward_straight()
        if w.out:  # The budget ran out while this link was routed: it goes straight, as every later link does.
            chosen, was_clear = _safe_forward_straight(), False

        pair_cache[pkey] = (chosen, was_clear, g, ctx)
        routed.append({"part": part, "na": na, "nb": nb, "a": a, "b": b, "la": la, "lb": lb,
                       "ca": ca, "cb": cb, "g": g, "curve": curve, "chosen": chosen,
                       "raw_chosen": chosen, "ctx": ctx, "reused": False, "was_clear": was_clear})

    # Pass 2: separate link endpoints that crowd or overlap on the same node.
    def _pair_min_sep(rec_i, is_end_i, rec_j, is_end_j):
        hi = _arrow_head_pts(*rec_i["chosen"], rec_i["part"]["width"])[3] if is_end_i else 0.0
        hj = _arrow_head_pts(*rec_j["chosen"], rec_j["part"]["width"])[3] if is_end_j else 0.0
        g_pair = max(rec_i["g"], rec_j["g"])
        if is_end_i and is_end_j:
            return max(1.15 * max(hi, hj), 0.9 * g_pair)
        if is_end_i or is_end_j:
            return max(0.85 * max(hi, hj), 0.85 * g_pair)
        return 0.7 * g_pair

    by_node = {}
    for idx, rec in enumerate(routed):
        by_node.setdefault(rec["na"], []).append((idx, False))
        by_node.setdefault(rec["nb"], []).append((idx, True))

    if dirty_links is not None:
        active_nodes = {n for n, items in by_node.items() if any(not routed[idx]["reused"] for idx, _ in items)}
        changed_active = True
        while changed_active:
            changed_active = False
            for rec in routed:
                if rec["reused"] and (rec["na"] in active_nodes or rec["nb"] in active_nodes):
                    rec["chosen"] = rec["raw_chosen"]
                    rec["reused"] = False
                    if rec["na"] not in active_nodes:
                        active_nodes.add(rec["na"])
                        changed_active = True
                    if rec["nb"] not in active_nodes:
                        active_nodes.add(rec["nb"])
                        changed_active = True
    else:
        active_nodes = None

    for node_name, items in by_node.items():
        if len(items) < 2 or (active_nodes is not None and node_name not in active_nodes) or not w.spend(
                32 * len(items) * len(items)):
            continue
        cn = _sup_centre(node_sup[node_name])

        def _pt_of(idx, is_end):
            return routed[idx]["chosen"][1] if is_end else routed[idx]["chosen"][0]

        def _head_tri(idx):
            e1, e2, q = routed[idx]["chosen"]
            return _arrow_head_pts(e1, e2, q, routed[idx]["part"]["width"])[:3]

        crowded = False
        for i in range(len(items)):
            ii, ei = items[i]
            pi = _pt_of(ii, ei)
            for j in range(i + 1, len(items)):
                jj, ej = items[j]
                pj = _pt_of(jj, ej)
                if math.dist(pi, pj) < _pair_min_sep(routed[ii], ei, routed[jj], ej) or (
                        ei and ej and _tris_near(_head_tri(ii), _head_tri(jj),
                                                 pad=0.2 * max(routed[ii]["g"], routed[jj]["g"]))):
                    crowded = True
                    break
            if crowded:
                break
        if not crowded:
            continue

        annotated = sorted(((math.atan2(_pt_of(idx, ie)[1] - cn[1], _pt_of(idx, ie)[0] - cn[0]), idx, ie)
                            for idx, ie in items), key=lambda t: t[0])
        clusters = [[annotated[0]]]
        for entry in annotated[1:]:
            prev = clusters[-1][-1]
            req = _pair_min_sep(routed[prev[1]], prev[2], routed[entry[1]], entry[2])
            if math.dist(_pt_of(prev[1], prev[2]), _pt_of(entry[1], entry[2])) < req * 1.15:
                clusters[-1].append(entry)
            else:
                clusters.append([entry])
        if len(clusters) > 1:
            p0, p1 = _pt_of(clusters[-1][-1][1], clusters[-1][-1][2]), _pt_of(clusters[0][0][1], clusters[0][0][2])
            req = _pair_min_sep(routed[clusters[-1][-1][1]], clusters[-1][-1][2],
                                routed[clusters[0][0][1]], clusters[0][0][2])
            if math.dist(p0, p1) < req * 1.15:
                clusters[0] = clusters[-1] + clusters[0]
                clusters.pop()

        sup_n, labs_n = node_sup[node_name], node_labels[node_name]
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            base_ang = cluster[0][0]
            angs = sorted(((base_ang + (ang - base_ang + math.pi) % (2 * math.pi) - math.pi, idx, ie)
                           for ang, idx, ie in cluster), key=lambda t: t[0])
            mean_ang = sum(t[0] for t in angs) / len(angs)
            r_eff = max(sum(math.dist(cn, _pt_of(idx, ie)) for _, idx, ie in angs) / len(angs), 1.0)
            max_req = max(_pair_min_sep(routed[angs[k][1]], angs[k][2], routed[angs[k + 1][1]], angs[k + 1][2])
                          for k in range(len(angs) - 1))
            step_ang = min(0.55, max_req * 1.18 / r_eff)
            for k, (_, idx, is_end) in enumerate(angs):
                rec = routed[idx]
                if rec["reused"] or rec["ctx"] is None or not rec.get("was_clear", True):
                    continue
                target_ang = mean_ang + (k - (len(angs) - 1) * 0.5) * step_ang
                e1, e2, q = rec["chosen"]
                ux, uy = math.cos(target_ang), math.sin(target_ang)
                port = _leave(sup_n, labs_n, cn[0], cn[1], (cn[0] + ux * 1000.0, cn[1] + uy * 1000.0), rec["g"])
                is_straight = math.hypot(q[0] - (e1[0] + e2[0]) * 0.5, q[1] - (e1[1] + e2[1]) * 0.5) < 1e-4
                if is_end:
                    if is_straight:
                        ne1 = _leave(rec["a"], rec["la"], rec["ca"][0], rec["ca"][1], port, rec["g"])
                        cand = (ne1, port, ((ne1[0] + port[0]) * 0.5, (ne1[1] + port[1]) * 0.5))
                    else:
                        arm = max(math.dist(q, e2), 0.35 * math.dist(e1, port))
                        nq = (port[0] + ux * arm * 0.5 + (q[0] - e2[0]) * 0.5,
                              port[1] + uy * arm * 0.5 + (q[1] - e2[1]) * 0.5)
                        cand = (_leave(rec["a"], rec["la"], rec["ca"][0], rec["ca"][1], nq, rec["g"]), port, nq)
                else:
                    if is_straight:
                        ne2 = _leave(rec["b"], rec["lb"], rec["cb"][0], rec["cb"][1], port, rec["g"])
                        cand = (port, ne2, ((port[0] + ne2[0]) * 0.5, (port[1] + ne2[1]) * 0.5))
                    else:
                        arm = max(math.dist(q, e1), 0.35 * math.dist(port, e2))
                        nq = (port[0] + ux * arm * 0.5 + (q[0] - e1[0]) * 0.5,
                              port[1] + uy * arm * 0.5 + (q[1] - e1[1]) * 0.5)
                        cand = (port, _leave(rec["b"], rec["lb"], rec["cb"][0], rec["cb"][1], nq, rec["g"]), nq)
                if _link_clear(rec["ctx"], *cand, check_labels=True, check_bounds=True) or _link_clear(
                        rec["ctx"], *cand, check_labels=False, check_bounds=True):
                    rec["chosen"] = cand

    routed_cache = {}
    for rec in routed:
        part = rec["part"]
        if rec["reused"]:
            routed_cache[part["id"]] = (tuple(part["args"]), part["bend"], rec["g"],
                                        rec["raw_chosen"], rec["was_clear"], rec["ctx"])
            continue
        e1, e2, q = rec["chosen"]
        elen = math.dist(e1, e2) or 1.0
        nx, ny = -(e2[1] - e1[1]) / elen, (e2[0] - e1[0]) / elen
        bend = ((q[0] - (e1[0] + e2[0]) * 0.5) * nx + (q[1] - (e1[1] + e2[1]) * 0.5) * ny) * 0.5
        args = [e1[0], e1[1], e2[0], e2[1]]
        part.update(shape="arrow", args=args, link=(rec["na"], rec["nb"]), bend=bend)
        routed_cache[part["id"]] = (tuple(args), bend, rec["g"], rec["raw_chosen"], rec["was_clear"], rec["ctx"])

    return {"box": box, "scale": scale, "gap": gap, "part_sup": part_sup, "part_label": part_label,
            "node_sup": node_sup, "routed": routed_cache}


_STENCILS = {}


def _stencil(name):
    """A stencil's inks as parsed path ops, its box, its 16-direction support polygon, and per-ink boxes.
    Uses a fresh Cairo context per parse so concurrent threads never share Cairo state."""
    hit = _STENCILS.get(name)
    if hit is not None:
        return hit
    inks = [(ink, _parse_path(d)[0]) for ink, d in stencils.STENCILS[name]]
    box = (-64, -64, 64, 64)
    sup = _sup_rect(box)
    ink_boxes = [("stroke", -64, -64, 64, 64)]
    if cairo:
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1))
        for _, ops in inks:
            _trace_ops(cr, ops)
        box = cr.path_extents()
        cr.set_tolerance(1.0)
        ink_boxes, pts = [], []
        for ink, ops in inks:
            cr.new_path()
            _trace_ops(cr, ops)
            b = cr.path_extents()
            if b[2] > b[0] or b[3] > b[1]:
                ink_boxes.append((ink, b[0], b[1], b[2], b[3]))
            pts.extend(pt for kind, pt in cr.copy_path_flat() if kind in (cairo.PATH_MOVE_TO, cairo.PATH_LINE_TO))
        if pts:
            sup = _sup_pts(pts)
    val = (inks, box, sup, tuple(ink_boxes))
    _STENCILS[name] = val
    return val

def _compound(raw, where, view, errors):
    """A compound stencil as the group of stencils it stands for."""
    for key in raw:
        if key not in ("id", "stencil", "at", "size", "rotate", "repeat", "lead", "quiet"):
            errors.append(f"{where}: a compound stencil takes id, at, size, rotate, repeat, lead and quiet; drop "
                          f"{key}.")
    size = raw.get("size", max(view) / 4)
    problem = _value(*PART_KEYS["size"], size)
    if problem:
        errors.append(f"{where}: size {problem}.")
        size = max(view) / 4
    kids = []
    for cid, name, at, size_, turn, *label in stencils.COMPOUNDS[raw["stencil"]]:
        kids.append({"id": cid, "stencil": name, "at": list(at), "size": size_, "rotate": turn,
                     **{k: raw[k] for k in ("lead", "quiet") if k in raw}})
        if label:
            kids[-1].update(label=label[0], label_at=label[1])
    group = {"id": raw.get("id"), "group": kids, "translate": raw.get("at", [0, 0]), "rotate": raw.get("rotate", 0),
             "scale": size / 128}
    return {**group, **({"repeat": raw["repeat"]} if "repeat" in raw else {})}


def _layout(doc, errors):
    """A layout scene as a plain one: its nodes placed in a view of pixels, and the links between them."""
    out = {k: v for k, v in doc.items() if k not in ("layout", "nodes", "links")}
    for key in ("view", "parts"):
        if key in doc:
            errors.append(f"The scene: a layout places its own nodes; drop {key}, or drop layout and place parts "
                          "yourself.")
    kind, nodes = doc["layout"], doc.get("nodes")
    if kind not in LAYOUTS:
        errors.append(f"The scene: layout needs one of {', '.join(LAYOUTS)}; got {_got(kind)}.")
    if not isinstance(nodes, list) or not nodes:
        errors.append("The scene: a layout needs nodes, a list such as [{\"id\": \"mic\", \"stencil\": \"mic\"}].")
        return out
    checked = []
    for k, raw in enumerate(nodes, 1):
        if not isinstance(raw, dict):
            errors.append(f"Node {k} needs to be an object such as {{\"id\": \"mic\", \"stencil\": \"mic\"}}; "
                          f"got {_got(raw)}.")
            continue
        where = f"node '{raw['id']}'" if isinstance(raw.get("id"), str) else f"node {k}"
        if "id" not in raw:
            errors.append(f"{where} needs an id, such as \"mic\", so links and steps can name it.")
        node = _keys(dict(raw), NODE_KEYS, where, errors)
        if "stencil" not in node and "label" not in node:
            errors.append(f"{where} needs a stencil or a label, or both.")
        if node.get("stencil") in stencils.COMPOUNDS and "label" in node:
            errors.append(f"{where}: the {node['stencil']} labels its own parts; drop label.")
        checked.append(node)
    problem = "links" in doc and _value("links", None, doc["links"])
    if problem:
        errors.append(f"The scene: links {problem}.")
    if errors:
        return out
    n, side = len(checked), DIAGRAM_BOX
    if kind in ("row", "column"):
        cell = side / max(n, 3)
        size = min(NODE_PX, 0.58 * cell)
        across = max(size + 90, cell * n / LIMITS["aspect"])
        view = [cell * n, across]
        if kind == "row":
            # Keep boxes narrow enough for visible links and spread nodes cleanly across the row width.
            max_box = (0.72 if n <= 5 else 0.64) * cell
            widths = [size if "stencil" in node else min(max(0.8 * size, LABEL_TYPE["diagram"][2] * len(node["label"])
                                                             + 28), 1.6 * size, max_box) for node in checked]
            if n >= 2:
                pad = min(14.0, 0.12 * cell)
                left, right = widths[0] / 2 + pad, view[0] - widths[-1] / 2 - pad
                spots = [(left + (right - left) * k / (n - 1), across / 2, "below") for k in range(n)]
            else:
                spots = [(view[0] / 2, across / 2, "below")]
        else:
            spots, view = [(across / 2, cell * (k + 0.5), "right") for k in range(n)], view[::-1]
            widths = None
    else:
        ring = checked[1:] if kind == "hub" else checked
        count = max(len(ring), 1)
        size = min(NODE_PX, 0.55 * side * math.sin(math.pi / max(count, 3)))
        r = side / 2 - size / 2 - 30
        start = -90 + (180 / count if kind == "hub" and count % 2 == 0 else 0)
        spots = [(side / 2, side / 2, "below")] if kind == "hub" else []
        for k in range(len(ring)):
            a = math.radians(start + 360 * k / count)
            c, s = math.cos(a), math.sin(a)
            at = "above" if s < -0.6 else "below" if s > 0.6 else "right" if c > 0 else "left"
            spots.append((side / 2 + r * c, side / 2 + r * s, at))
        view = [side, side]
        widths = None
    parts = []
    for k, ((x, y, at), node) in enumerate(zip(spots, checked)):
        part = {key: node[key] for key in ("id", "label", "lead", "quiet") if key in node}
        if "stencil" in node:
            part.update(stencil=node["stencil"], at=[round(x, 1), round(y, 1)], size=round(size, 1))
            if "label" in node:
                part["label_at"] = at
        else:  # A box round its label: the label's capitals and some room each side.
            w = widths[k] if widths is not None else min(
                max(0.8 * size, LABEL_TYPE["diagram"][2] * len(node["label"]) + 28), 1.6 * size)
            part.update(rect=[round(x - w / 2, 1), round(y - 0.28 * size, 1), round(w, 1), round(0.56 * size, 1)],
                        radius=8, label_at="inside")
        parts.append(part)
    ids = [node.get("id") for node in checked]
    pairs = list(zip(ids, ids[1:])) + ([(ids[-1], ids[0])] if kind == "cycle" and n > 2 else [])
    if kind == "hub":
        pairs = [(ids[0], other) for other in ids[1:]]
    links = doc.get("links", pairs)
    ends = {tuple(link[:2]) for link in links}
    for link in links:
        part = {"id": f"{link[0]}-{link[1]}"[:LIMITS["id"]], "link": list(link[:2])}
        bow = None
        if (link[1], link[0]) in ends and kind in ("row", "column"):  # A pair joined both ways: one bows each side.
            ahead = ids.index(link[0]) < ids.index(link[1]) if link[0] in ids and link[1] in ids else True
            bow = ("over" if ahead else "under") if kind == "row" else ("right" if ahead else "left")
            part["curve"] = bow
        if len(link) > 2:
            part.update(label=link[2], label_at={"under": "below", "left": "left"}.get(bow, "above" if kind == "row"
                                                                                       else "right"))
        parts.append(part)
    out.update(view=[round(v, 1) for v in view], parts=parts)
    return out


def _link_body_len(part):
    """Visible link body length in view units between start and end (arc length when bowed)."""
    e1, e2 = tuple(part["args"][:2]), tuple(part["args"][2:])
    if abs(part.get("bend", 0.0)) <= 1e-6:
        return math.dist(e1, e2)
    elen = math.dist(e1, e2) or 1.0
    nx, ny = -(e2[1] - e1[1]) / elen, (e2[0] - e1[0]) / elen
    q = ((e1[0] + e2[0]) * 0.5 + 2.0 * part["bend"] * nx, (e1[1] + e2[1]) * 0.5 + 2.0 * part["bend"] * ny)
    total, prev = 0.0, e1
    for k in range(1, 17):
        t = k / 16.0
        mt = 1.0 - t
        cur = (mt * mt * e1[0] + 2.0 * mt * t * q[0] + t * t * e2[0],
               mt * mt * e1[1] + 2.0 * mt * t * q[1] + t * t * e2[1])
        total += math.dist(prev, cur)
        prev = cur
    return total


def _clone_parts(parts):
    """Shallow-copy each part dict and its copies/args lists for trial layout adjustments."""
    return [{**p, "copies": list(p["copies"]),
             "args": list(p["args"]) if isinstance(p["args"], list) else p["args"]} for p in parts]


def _node_boxes_cached(nm, node_ids, scale, cache):
    """Compute (centres, view_boxes, full_boxes) directly from cached support polygons and label boxes."""
    centres, vboxes, fboxes = {}, {}, {}
    node_sup, part_label = cache["node_sup"], cache["part_label"]
    for nid in node_ids:
        ps = nm.get(nid)
        if not ps or nid not in node_sup:
            continue
        sup = node_sup[nid]
        centres[nid] = _sup_centre(sup)
        vx0, vy0, vx1, vy1 = _sup_box(sup)
        for p in ps:
            if p["shape"] == "stencil":
                hw = STENCIL_LINE * 0.5 / scale
            elif p.get("fill"):
                hw = 0.0
            else:
                m = p["copies"][0]
                hw = (p["width"] or 0.0) * 0.5 * math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))
            vx0, vy0 = min(vx0, -sup[8] - hw), min(vy0, -sup[12] - hw)
            vx1, vy1 = max(vx1, sup[0] + hw), max(vy1, sup[4] + hw)
        fx0, fy0, fx1, fy1 = vx0, vy0, vx1, vy1
        for p in ps:
            lsup = part_label.get(p["id"])
            if lsup is not None:
                lx0, ly0, lx1, ly1 = _sup_box(lsup)
                fx0, fy0, fx1, fy1 = min(fx0, lx0), min(fy0, ly0), max(fx1, lx1), max(fy1, ly1)
                if p.get("label_at", "below") not in ("left", "right"):
                    vx0, vy0, vx1, vy1 = min(vx0, lx0), min(vy0, ly0), max(vx1, lx1), max(vy1, ly1)
        vboxes[nid] = (vx0, vy0, vx1, vy1)
        fboxes[nid] = (fx0, fy0, fx1, fy1)
    return centres, vboxes, fboxes


def _fit_min_links(parts, groups, view, size, moving, layout_kind, node_ids, route_cache, compounds):
    """For layout scenes where any link body is shorter than MIN_LINK_BODY (scaled with the box):
    1. Grow the whole ring (or layout about its centre) uniformly by the smallest factor that clears the minimum
       while keeping every node and label inside the box/canvas with a 16 px margin and clear of neighbours.
    2. If a uniform grow cannot fit, push short spokes individually (matching mirrored pairs where possible).
    3. As a last resort, shrink ring/node sizes slightly and retry (strictly budgeted to at most 4 route trials).
    When no room exists inside the box (for example a 12-node row with long labels or overlapping hubs), this does
    the best it can without clipping or overlapping neighbours and accepts the result. Updates `compounds` frames in
    place so compound named poses resolve from the final layout positions. Returns (parts, route_cache)."""
    if route_cache is None:
        return parts, route_cache
    box = route_cache["box"]
    scale = route_cache["scale"]
    min_body = (MIN_LINK_BODY * box / DIAGRAM_BOX) / scale
    target_body = min_body + 0.5 / scale

    def _measure(cand):
        lens = [(p, _link_body_len(p)) for p in cand if p["shape"] == "arrow" and p.get("link")]
        if not lens:
            return math.inf, []
        short = [(p, ln) for p, ln in lens if ln < min_body]
        return min(ln for _, ln in lens), short

    init_min, init_short = _measure(parts)
    if not init_short:
        return parts, route_cache

    def _named_of(cand):
        solid = [p for p in cand if p["shape"] != "link" and not p.get("link")]
        nm = {p["id"]: [p] for p in solid}
        nm.update({g: [p for p in solid if p["group"] == g] for g in groups})
        return nm

    trials_left = [4]
    w = _work()

    def _reroute(cand, base_cache=None, moved_names=None, moved_part_sup=None):
        if trials_left[0] <= 0 or not w.spend(4 * len(node_ids) * len(node_ids)):
            return False, -1.0, [], None
        trials_left[0] -= 1
        if base_cache is None:
            for p in cand:
                if p.get("link"):
                    p.update(shape="link", args=list(p["link"]), bend=0.0)
        errs = []
        cache = _route_links(cand, groups, view, size, errs, moving, base_cache=base_cache,
                             moved_names=moved_names, moved_part_sup=moved_part_sup)
        if errs or w.out:  # A trial the budget cut short is no trial.
            return False, -1.0, [], None
        mn, sh = _measure(cand)
        return True, mn, sh, cache

    def _shift_node(cand, comp_map, name, dx, dy):
        m = _matrix(translate=(dx, dy))
        for p in cand:
            if p["id"] == name or p["group"] == name:
                p["copies"] = [_then(c, m) for c in p["copies"]]
        if name in comp_map:
            kind, frame = comp_map[name]
            comp_map[name] = (kind, _then(frame, m))

    def _scale_node(cand, comp_map, name, factor, about):
        m = _matrix(scale=factor, about=about)
        for p in cand:
            if p["id"] == name or p["group"] == name:
                p["copies"] = [_then(c, m) for c in p["copies"]]
        if name in comp_map:
            kind, frame = comp_map[name]
            comp_map[name] = (kind, _then(frame, m))

    edge_pad = 16.0 / scale
    neighbour_pad = 16.0 / scale
    side_slack = max(0.0, (CANVAS / scale - view[0]) * 0.5 - edge_pad)
    hub_id = node_ids[0] if layout_kind == "hub" and node_ids else None
    ring_ids = node_ids[1:] if hub_id else list(node_ids)

    def _fits_all(vboxes, fboxes):
        if not w.spend(4 * len(fboxes) * len(fboxes)):
            return False
        for nid, (vx0, vy0, vx1, vy1) in vboxes.items():
            if vx0 < edge_pad - 1e-6 or vx1 > view[0] - edge_pad + 1e-6:
                return False
            if vy0 < edge_pad - 1e-6 or vy1 > view[1] - edge_pad + 1e-6:
                return False
            fx0, fy0, fx1, fy1 = fboxes[nid]
            if fx0 < -side_slack - 1e-6 or fx1 > view[0] + side_slack + 1e-6:
                return False
            if fy0 < edge_pad - 1e-6 or fy1 > view[1] - edge_pad + 1e-6:
                return False
        nids = list(fboxes)
        for i in range(len(nids)):
            a = fboxes[nids[i]]
            for j in range(i + 1, len(nids)):
                b = fboxes[nids[j]]
                if not (a[2] + neighbour_pad < b[0] or a[0] - neighbour_pad > b[2]
                        or a[3] + neighbour_pad < b[1] or a[1] - neighbour_pad > b[3]):
                    return False
        return True

    def _uniform_grow(base, base_cache, base_comp, short_list):
        nm = _named_of(base)
        centres, vboxes, fboxes = _node_boxes_cached(nm, node_ids, scale, base_cache)
        anchor = centres[hub_id] if (hub_id and hub_id in centres) else (view[0] * 0.5, view[1] * 0.5)
        max_f = 2.0
        for nid in ring_ids:
            if nid not in centres:
                continue
            dx, dy = centres[nid][0] - anchor[0], centres[nid][1] - anchor[1]
            vx0, vy0, vx1, vy1 = vboxes[nid]
            fx0, fy0, fx1, fy1 = fboxes[nid]
            if dx > 1e-6:
                max_f = min(max_f, 1.0 + max(0.0, view[0] - edge_pad - vx1) / dx,
                            1.0 + max(0.0, view[0] + side_slack - fx1) / dx)
            elif dx < -1e-6:
                max_f = min(max_f, 1.0 + max(0.0, vx0 - edge_pad) / (-dx),
                            1.0 + max(0.0, fx0 + side_slack) / (-dx))
            if dy > 1e-6:
                max_f = min(max_f, 1.0 + max(0.0, view[1] - edge_pad - vy1) / dy,
                            1.0 + max(0.0, view[1] - edge_pad - fy1) / dy)
            elif dy < -1e-6:
                max_f = min(max_f, 1.0 + max(0.0, vy0 - edge_pad) / (-dy),
                            1.0 + max(0.0, fy0 - edge_pad) / (-dy))
        if max_f <= 1.001:
            return None, -1.0, None, None

        def _at_factor(f):
            cand = _clone_parts(base)
            cc = dict(base_comp)
            nv, nf = dict(vboxes), dict(fboxes)
            for nid in ring_ids:
                if nid not in centres:
                    continue
                sx, sy = (centres[nid][0] - anchor[0]) * (f - 1.0), (centres[nid][1] - anchor[1]) * (f - 1.0)
                _shift_node(cand, cc, nid, sx, sy)
                vx0, vy0, vx1, vy1 = vboxes[nid]
                fx0, fy0, fx1, fy1 = fboxes[nid]
                nv[nid] = (vx0 + sx, vy0 + sy, vx1 + sx, vy1 + sy)
                nf[nid] = (fx0 + sx, fy0 + sy, fx1 + sx, fy1 + sy)
            if not _fits_all(nv, nf):
                return False, -1.0, [], cand, None, cc
            ok, mn, sh, cache = _reroute(cand)
            return ok, mn, sh, cand, cache, cc

        f_est = 1.0
        for p, ln in short_list:
            na, nb = p["link"]
            if na in centres and nb in centres:
                span = math.dist(centres[na], centres[nb])
                if span > 1e-6:
                    f_est = max(f_est, 1.0 + (target_body - ln) / span)
        f_try = min(max_f, max(1.01, f_est * 1.03))
        ok_t, mn_t, sh_t, cand_t, cache_t, cc_t = _at_factor(f_try)
        if ok_t and not sh_t:
            if mn_t <= target_body + 2.0 / scale or trials_left[0] <= 0:
                return cand_t, mn_t, cache_t, cc_t
            mid = (1.0 + f_try) * 0.5
            ok_m, mn_m, sh_m, cand_m, cache_m, cc_m = _at_factor(mid)
            if ok_m and not sh_m:
                return cand_m, mn_m, cache_m, cc_m
            return cand_t, mn_t, cache_t, cc_t
        if abs(max_f - f_try) <= 0.005:
            return (cand_t, mn_t, cache_t, cc_t) if ok_t else (None, -1.0, None, None)
        ok_hi, mn_hi, sh_hi, cand_hi, cache_hi, cc_hi = _at_factor(max_f)
        if not ok_hi:
            return (cand_t, mn_t, cache_t, cc_t) if ok_t else (None, -1.0, None, None)
        if sh_hi or trials_left[0] <= 0:
            return cand_hi, mn_hi, cache_hi, cc_hi
        mid = (f_try + max_f) * 0.5
        ok_m, mn_m, sh_m, cand_m, cache_m, cc_m = _at_factor(mid)
        if ok_m and not sh_m:
            return cand_m, mn_m, cache_m, cc_m
        return cand_hi, mn_hi, cache_hi, cc_hi

    def _push_passes(cand, cand_cache, cand_comp, max_passes=2):
        best_c, best_m, best_ca, best_cc = _clone_parts(cand), _measure(cand)[0], cand_cache, dict(cand_comp)
        cur_cache = cand_cache
        for _ in range(max_passes):
            if trials_left[0] <= 0 or not w.spend(16 * len(node_ids) * len(node_ids)):
                break
            mn, short = _measure(cand)
            if not short:
                return cand, mn, cur_cache, cand_comp
            nm = _named_of(cand)
            centres, vboxes, fboxes = _node_boxes_cached(nm, node_ids, scale, cur_cache)
            anchor_x = centres[hub_id][0] if (hub_id and hub_id in centres) else view[0] * 0.5
            pushes = {}
            for p, ln in short:
                na, nb = p["link"]
                if na not in centres or nb not in centres:
                    continue
                need = target_body - ln
                if hub_id and na == hub_id and nb != hub_id:
                    target, anchor = nb, na
                elif hub_id and nb == hub_id and na != hub_id:
                    target, anchor = na, nb
                else:
                    target, anchor = nb, na
                dx, dy = centres[target][0] - centres[anchor][0], centres[target][1] - centres[anchor][1]
                d = math.hypot(dx, dy)
                if d <= 1e-6:
                    continue
                ux, uy = dx / d, dy / d
                prev = pushes.get(target)
                if prev is None or need > prev[0]:
                    pushes[target] = (need, ux, uy)
            for target in list(pushes):
                need, ux, uy = pushes[target]
                tx, ty = centres[target]
                for other in ring_ids:
                    if other == target or other not in centres:
                        continue
                    ox, oy = centres[other]
                    if abs((tx - anchor_x) + (ox - anchor_x)) < 2.0 and abs(ty - oy) < 2.0:
                        if other in pushes:
                            same = max(need, pushes[other][0])
                            pushes[target] = (same, ux, uy)
                            pushes[other] = (same, pushes[other][1], pushes[other][2])
                        else:
                            odx = ox - anchor_x
                            ody = oy - (centres[hub_id][1] if (hub_id and hub_id in centres) else view[1] * 0.5)
                            od = math.hypot(odx, ody)
                            if od > 1e-6:
                                pushes[other] = (need, odx / od, ody / od)
            moved_any = False
            for target, (need, ux, uy) in pushes.items():
                vx0, vy0, vx1, vy1 = vboxes[target]
                fx0, fy0, fx1, fy1 = fboxes[target]
                max_d = need
                if ux > 1e-6:
                    max_d = min(max_d, max(0.0, (view[0] - edge_pad - vx1) / ux),
                                max(0.0, (view[0] + side_slack - fx1) / ux))
                elif ux < -1e-6:
                    max_d = min(max_d, max(0.0, (vx0 - edge_pad) / (-ux)),
                                max(0.0, (fx0 + side_slack) / (-ux)))
                if uy > 1e-6:
                    max_d = min(max_d, max(0.0, (view[1] - edge_pad - vy1) / uy),
                                max(0.0, (view[1] - edge_pad - fy1) / uy))
                elif uy < -1e-6:
                    max_d = min(max_d, max(0.0, (vy0 - edge_pad) / (-uy)),
                                max(0.0, (fy0 - edge_pad) / (-uy)))
                if max_d <= 0.25 / scale:
                    continue
                step = max_d
                for _ in range(4):
                    nx0, ny0, nx1, ny1 = fx0 + ux * step, fy0 + uy * step, fx1 + ux * step, fy1 + uy * step
                    crowd = any(
                        other != target and not (
                            nx1 + neighbour_pad < ob[0] or nx0 - neighbour_pad > ob[2]
                            or ny1 + neighbour_pad < ob[1] or ny0 - neighbour_pad > ob[3])
                        for other, ob in fboxes.items())
                    if not crowd:
                        break
                    step *= 0.5
                else:
                    step = 0.0
                if step > 0.25 / scale:
                    _shift_node(cand, cand_comp, target, ux * step, uy * step)
                    vboxes[target] = (vx0 + ux * step, vy0 + uy * step, vx1 + ux * step, vy1 + uy * step)
                    fboxes[target] = (fx0 + ux * step, fy0 + uy * step, fx1 + ux * step, fy1 + uy * step)
                    moved_any = True
            if not moved_any:
                break
            ok, mn2, sh2, ca2 = _reroute(cand)
            if ok:
                cur_cache = ca2
                if mn2 > best_m:
                    best_c, best_m, best_ca, best_cc = _clone_parts(cand), mn2, ca2, dict(cand_comp)
                if not sh2:
                    return cand, mn2, ca2, cand_comp
            else:
                break
        return best_c, best_m, best_ca, best_cc

    best_parts, best_min, best_cache, best_comp = _clone_parts(parts), init_min, route_cache, dict(compounds)

    uni_parts, uni_min, uni_cache, uni_comp = _uniform_grow(parts, route_cache, compounds, init_short)
    if uni_parts is not None and uni_min > best_min:
        best_parts, best_min, best_cache, best_comp = uni_parts, uni_min, uni_cache, uni_comp
    if best_min >= min_body:
        compounds.update(best_comp)
        return best_parts, best_cache

    push_parts, push_min, push_cache, push_comp = _push_passes(_clone_parts(parts), route_cache, dict(compounds), max_passes=2)
    if push_min > best_min:
        best_parts, best_min, best_cache, best_comp = push_parts, push_min, push_cache, push_comp
    if best_min >= min_body:
        compounds.update(best_comp)
        return best_parts, best_cache

    base_centres = {nid: _sup_centre(route_cache["node_sup"][nid])
                    for nid in node_ids if nid in route_cache["node_sup"]}
    for k, shrink in enumerate((0.88, 0.76), 1):
        if trials_left[0] <= 0:
            break
        cand = _clone_parts(parts)
        cc = dict(compounds)
        for nid in ring_ids:
            if nid in base_centres:
                _scale_node(cand, cc, nid, shrink, base_centres[nid])
        if hub_id and k >= 2 and hub_id in base_centres:
            _scale_node(cand, cc, hub_id, max(0.84, 0.5 + 0.5 * shrink), base_centres[hub_id])
        ok, mn, sh, ca = _reroute(cand)
        if ok:
            if mn > best_min:
                best_parts, best_min, best_cache, best_comp = _clone_parts(cand), mn, ca, dict(cc)
            if not sh:
                compounds.update(cc)
                return cand, ca
            up, um, uca, ucc = _uniform_grow(cand, ca, cc, sh)
            if up is not None and um > best_min:
                best_parts, best_min, best_cache, best_comp = up, um, uca, ucc
            if best_min >= min_body:
                compounds.update(best_comp)
                return best_parts, best_cache
            pp, pm, pca, pcc = _push_passes(cand, ca, cc, max_passes=1)
            if pm > best_min:
                best_parts, best_min, best_cache, best_comp = pp, pm, pca, pcc
            if best_min >= min_body:
                compounds.update(best_comp)
                return best_parts, best_cache
    compounds.update(best_comp)
    return best_parts, best_cache


def _posed(parts, groups, view, size, moves, where, errors, moving, base_cache=None, prev_cache=None, changed=None,
           has_links=True):
    """The parts in a step's pose: each moved part's copies moved, with its pose, and only affected links rerouted.
    Link-free scenes take main's exact _extent/_centre path so pivots and bounds are byte-for-byte unchanged."""
    poses = {}
    moved_part_sup = {}
    ref_cache = prev_cache if prev_cache is not None else base_cache
    part_base = base_cache["part_sup"] if base_cache is not None else None
    for name, move in moves.items():
        kids = [p for p in parts if p["id"] == name or p["group"] == name]
        if any(p.get("link") for p in kids):
            errors.append(f"{where}: '{name}' is a link, which follows the parts it joins. Move those parts instead.")
            continue
        if any(p["id"] in poses for p in kids):
            errors.append(f"{where}: '{name}' is moved twice, as a part and with its group. Move one of them.")
            continue
        past = None  # Set only when the budget is spent and an outline bound must answer.
        if not has_links:
            pose = (tuple(move.get("to", (0.0, 0.0))), move.get("rotate", 0.0),
                    tuple(move.get("about") or _centre(_extent(kids))), move.get("scale", 1.0))
            poses.update((p["id"], pose) for p in kids)
            m = _matrix(pose[3], pose[1], pose[0], pose[2])
            x0, y0, x1, y1 = _extent([dict(p, copies=[_then(c, m) for c in p["copies"]]) for p in kids])["box"]
        else:
            centres = _work().centres  # The pivot is main's box centre; the drawn pose is the same in every step.
            if not move.get("about") and name not in centres:
                centres[name] = _centre(_extent(kids))
            pose = (tuple(move.get("to", (0.0, 0.0))), move.get("rotate", 0.0),
                    tuple(move.get("about") or centres[name]), move.get("scale", 1.0))
            poses.update((p["id"], pose) for p in kids)
            m = _matrix(pose[3], pose[1], pose[0], pose[2])
            kid_sups, boxed, moved = [], _work().boxed, []
            for k in kids:  # A boxed part keeps main's box in each pose, so main's verdicts hold for it.
                mk = dict(k, copies=[_then(c, m) for c in k["copies"]])
                ksup = _sup_transform(part_base[k["id"]] if (part_base is not None and k["id"] in part_base)
                                      else _part_sup(k), m)
                if k["id"] in boxed:
                    ksup = _sup_rect(_main_ext([mk], {k["id"]: _sup_box(ksup)})["box"])
                moved_part_sup[k["id"]] = ksup
                kid_sups.append(ksup)
                moved.append(mk)
            x0, y0, x1, y1 = _sup_box(_sup_union(kid_sups))
            if x0 < -1 or y0 < -1 or x1 > view[0] + 1 or y1 > view[1] + 1:
                # The outline is an upper bound, so near an edge the verdict is main's, from main's own points, paid
                # from the whole budget; a held move keeps its pose, so each pose pays for its points once. Once the
                # whole budget is spent the bound refuses only a part wholly outside the view, which main refuses too.
                ext = _main_ext(moved, {k["id"]: _sup_box(moved_part_sup[k["id"]]) for k in kids}, verdict=True)
                x0, y0, x1, y1 = ext["box"]
                if ext.get("bound"):
                    past = x1 < -1 or y1 < -1 or x0 > view[0] + 1 or y0 > view[1] + 1
        if past is None:
            past = x0 < -1 or y0 < -1 or x1 > view[0] + 1 or y1 > view[1] + 1
        if past:
            errors.append(f"{where}: the move takes '{name}' past the view's edge. \"to\" is how far it moves, "
                          f"[dx, dy], not where it goes; keep it inside [0, 0, {view[0]:g}, {view[1]:g}].")
    out = []
    for p in parts:
        if p.get("link"):
            p = dict(p)
        elif p["id"] in poses:
            to, rotate, about, scale = poses[p["id"]]
            p = dict(p, copies=[_then(c, _matrix(scale, rotate, to, about)) for c in p["copies"]],
                     pose=poses[p["id"]])
        out.append(p)
    if not has_links:
        return out, None
    if prev_cache is not None and changed is not None:
        changed_ids = {p["id"] for p in parts if p["id"] in changed or p["group"] in changed}
        moved_names = changed_ids | {p["group"] for p in parts if p["id"] in changed_ids and p["group"]}
    else:
        moved_names = set(poses) | {p["group"] for p in parts if p["id"] in poses and p["group"]}
    routed = []
    step_cache = _route_links(out, groups, view, size, routed, moving, base_cache=ref_cache,
                              moved_names=moved_names, moved_part_sup=moved_part_sup)
    errors += [f"{where}, after its moves: {e}" for e in routed]
    return out, step_cache


def _resolve_compound_moves(steps, parts, compounds):
    """Expand validated compound named poses from each kid's final base position."""
    for step in steps:
        if not any(isinstance(v, tuple) and v[0] == "_pose" for v in step["move"].values()):
            continue
        expanded = {}
        for name, move in step["move"].items():
            if isinstance(move, tuple) and move[0] == "_pose":
                kind, frame = compounds[name]
                for cid, (dx, dy, turn) in stencils.POSES[kind][move[1]].items():
                    kid = next(p for p in parts if p["id"] == f"{name}.{cid}")
                    expanded[kid["id"]] = {"to": [frame[0] * dx + frame[2] * dy, frame[1] * dx + frame[3] * dy],
                                           "rotate": turn, "about": list(_apply(kid["copies"][0], 0.0, 0.0))}
            else:
                expanded[name] = move
        step["move"] = expanded


def validate(doc, budget=WORK_BUDGET):
    """Check a scene. Returns (scene, []) with every default filled in, or (None, errors): every problem at once, each a
    sentence that names the part and says how to fix it. All its outline and routing work shares one budget."""
    _TLS.work = _Work(budget)
    try:
        return _validate(doc)
    finally:
        _TLS.last_work, _TLS.work = _TLS.work, None


def _validate(doc):
    errors = []
    if not isinstance(doc, dict):
        return None, ["The scene needs to be a JSON object with a parts list."]
    try:
        size = len(json.dumps(doc))
    except (TypeError, ValueError):
        return None, ["The scene needs to be plain JSON: objects, lists, text, numbers, true and false."]
    if size > LIMITS["bytes"]:
        return None, [f"The scene is {size} bytes; the most is {LIMITS['bytes']}. Use repeat, or fewer parts."]
    layout_kind, layout_nodes = None, []
    if "layout" in doc:
        layout_kind = doc.get("layout")
        if isinstance(doc.get("nodes"), list):
            layout_nodes = [raw["id"] for raw in doc["nodes"] if isinstance(raw, dict) and isinstance(raw.get("id"), str)]
        doc = _layout(doc, errors)
        if errors:
            return None, errors
    for key in ("nodes", "links"):
        if key in doc:
            errors.append(f"The scene: {key} only goes with a layout. Add \"layout\", or draw them as parts.")
    top = _keys(dict(doc), SCENE_KEYS, "The scene", errors)
    view = top.get("view", [100, 100])
    if min(view) <= 0 or max(view) / min(view) > LIMITS["aspect"]:
        errors.append(f"The scene: view needs a width and height above 0, at most {LIMITS['aspect']} to 1; got {view}.")
        view = [100, 100]
    if "parts" not in doc:
        errors.append("The scene needs parts: a list of parts, such as {\"id\": \"sun\", \"circle\": [50, 50, 20]}.")
    parts, seen, groups, compounds = [], set(), {}, {}
    for n, raw in enumerate(top.get("parts", []), 1):
        if not isinstance(raw, dict):
            errors.append(f"Part {n} needs to be an object with an id and a shape; got {_got(raw)}.")
            continue
        name = raw.get("id") if isinstance(raw.get("id"), str) else None  # A bad id is reported below, by _keys.
        where = f"part '{name}'" if name else f"part {n}"
        if "id" not in raw:
            errors.append(f"{where} needs an id, such as \"lens\", so steps and later scenes can name it.")
        if isinstance(raw.get("stencil"), str) and raw["stencil"] in stencils.COMPOUNDS and "group" not in raw:
            compounds[name] = raw["stencil"]
            raw = _compound(raw, where, view, errors)
        if "group" in raw:
            where = where.replace("part", "group", 1)
            g = _keys(dict(raw), GROUP_KEYS, where, errors)
            frame = _matrix(g.get("scale", 1.0), g.get("rotate", 0.0), tuple(g.get("translate", (0, 0))))
            if name in compounds:
                compounds[name] = (compounds[name], frame)
            outer = _copies(raw.get("repeat"), where, errors)
            kids = []
            for k, child in enumerate(g.get("group", []), 1):
                cname = child.get("id") if isinstance(child, dict) else None
                cwhere = f"part '{name}.{cname}'" if isinstance(cname, str) else f"{where}, part {k}"
                if not isinstance(child, dict) or "group" in child or (
                        isinstance(child.get("stencil"), str) and child["stencil"] in stencils.COMPOUNDS):
                    errors.append(f"{cwhere}: a group holds parts only, one level deep; move it out of {where}.")
                    continue
                if "id" not in child:
                    errors.append(f"{cwhere} needs an id.")
                part = _part(child, cwhere, view, _matrix(), errors)
                if part:
                    part["id"], part["group"] = f"{name}.{part['id']}", name
                    part["copies"] = [_then(_then(m, frame), o) for m in part["copies"] for o in outer]
                    kids.append(part)
            groups[name] = [kid["id"] for kid in kids]
            if name in seen:
                errors.append(f"{where}: the id '{name}' is used twice; give each part and group its own id.")
            seen.add(name)
        else:
            part = _part(raw, where, view, _matrix(), errors)
            kids = [part] if part else []
            if part:
                part["group"] = None
        for part in kids:
            if part["id"] in seen and part["group"] is None:
                errors.append(f"{where}: the id '{part['id']}' is used twice; give each part its own id.")
            seen.add(part["id"])
            parts.append(part)
    if len(parts) > LIMITS["parts"]:
        errors.append(f"The scene has {len(parts)} parts; the most is {LIMITS['parts']}. Use repeat, or join parts.")
    copies = sum(len(p["copies"]) for p in parts)
    if copies > LIMITS["copies"]:
        errors.append(f"The scene draws {copies} shapes once repeats are counted; the most is {LIMITS['copies']}.")
    steps = []
    if len(top.get("steps", [])) > LIMITS["steps"]:
        errors.append(f"The scene has {len(top['steps'])} steps; the most is {LIMITS['steps']}.")
    for n, raw in enumerate(top.get("steps", [])[:LIMITS["steps"]], 1):
        if not isinstance(raw, dict):
            errors.append(f"Step {n} needs to be an object such as {{\"light\": [\"lens\"]}}; got {_got(raw)}.")
            continue
        s = _keys(dict(raw), STEP_KEYS, f"Step {n}", errors)
        if "light" not in raw:
            errors.append(f"Step {n} needs light: the ids of the parts it lights.")
        for name in s.get("light", []):
            if name not in seen:
                errors.append(f"Step {n}: light names '{name}', which is not a part or group in this scene.")
        moves = {}
        for name, move in s.get("move", {}).items():
            if name not in seen:
                errors.append(f"Step {n}: move names '{name}', which is not a part or group in this scene.")
            elif isinstance(move, str) and name in compounds:
                kind, _ = compounds[name]
                if move not in stencils.POSES.get(kind, {}):
                    errors.append(f"Step {n}: the {kind} '{name}' has no pose '{move}'. Give one of "
                                  f"{', '.join(stencils.POSES.get(kind, {})) or 'none'}.")
                    continue
                moves[name] = ("_pose", move)
            elif not isinstance(move, dict) or not move:
                errors.append(f"Step {n}: the move of '{name}' needs to, rotate, about or scale, such as "
                              f"{{\"to\": [0, 20]}}; got {_got(move)}.")
            else:
                moves[name] = _keys(dict(move), MOVE_KEYS, f"Step {n}: the move of '{name}'", errors)
        steps.append({"light": s.get("light", []), "move": moves, "caption": s.get("caption", "")})
    if errors:
        return None, errors[:20] + ([f"There are {len(errors) - 20} more problems; fix these first."]
                                    if len(errors) > 20 else [])
    size = top.get("size") or ("diagram" if len(parts) > DIAGRAM_PARTS or any(p["label"] for p in parts) else "icon")
    for part in parts:
        if part["shape"] == "stencil":  # In pixels at any size; the sampler draws it so.
            part["width"] = STENCIL_LINE * max(view) / SIZE_FORM[size][1]
        elif part["width"] is None:
            part["width"] = DEFAULT_WIDTH * min(view) if size == "icon" else DIAGRAM_LINE * max(view) / DIAGRAM_BOX
    moving = set()
    for step in steps:
        for name, move in step["move"].items():
            if isinstance(move, tuple) and move[0] == "_pose":
                kind, _ = compounds[name]
                moving.update(f"{name}.{cid}" for cid in stencils.POSES[kind][move[1]])
            else:
                moving.add(name)
    has_links = any(p["shape"] == "link" for p in parts)
    posing = len(steps) - next((n for n, step in enumerate(steps) if step["move"]), len(steps))  # Steps posed below.
    _TLS.work.share(2 if posing else 1)  # The base pose may take half; the steps share what is left.
    route_cache = _route_links(parts, groups, view, size, errors, moving) if has_links else None
    if layout_kind and has_links and not errors:
        parts, route_cache = _fit_min_links(parts, groups, view, size, moving, layout_kind, layout_nodes,
                                            route_cache, compounds)
    _resolve_compound_moves(steps, parts, compounds)
    prev_cache = route_cache
    held = {}  # A move holds until a later step moves the same part again.
    for n, step in enumerate(steps, 1):
        changed = set(step["move"])
        for name in step["move"]:
            for k in list(held):
                if k == name or k.startswith(name + ".") or name.startswith(k + "."):
                    changed.add(k)
                    del held[k]
        held.update(step["move"])
        if held and not errors:
            _TLS.work.share(max(1, posing))
            posing -= 1
            step["parts"], prev_cache = _posed(parts, groups, view, size, held, f"Step {n}", errors, moving,
                                               base_cache=route_cache, prev_cache=prev_cache, changed=changed,
                                               has_links=has_links)
    if errors:
        return None, errors
    return {"name": top.get("name", "scene"), "title": top.get("title", ""), "size": size, "view": view,
            "parts": parts, "groups": groups, "steps": steps, "seconds": SCENE_SECONDS}, []


def _schema_of(kind, detail):
    if kind in ("id", "name"):
        return {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]*$", "maxLength": LIMITS[kind]}
    if kind == "text":
        return {"type": "string", "minLength": 1, "maxLength": detail}
    if kind == "bool":
        return {"type": "boolean"}
    if kind in ("number", "integer"):
        return {"type": kind, "minimum": detail[0], "maximum": detail[1]}
    if kind == "numbers":
        return {"type": "array", "items": {"type": "number"}, "minItems": len(detail), "maxItems": len(detail),
                "description": "[" + ", ".join(detail) + "]"}
    if kind == "pair":
        return {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
    if kind == "points":
        return {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 2 * LIMITS["poly_points"]}
    if kind == "path":
        return {"type": "string", "minLength": 1, "maxLength": LIMITS["path_chars"]}
    if kind == "enum":
        return {"enum": list(detail)}
    if kind == "ids":
        return {"type": "array", "items": {"type": "string"}, "minItems": 1}
    if kind == "link":
        return {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2}
    if kind == "repeat":
        return {"$ref": "#/$defs/repeat"}
    if kind == "links":
        return {"type": "array", "items": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3}}
    if kind == "moves":
        return {"type": "object", "minProperties": 1,
                "additionalProperties": {"anyOf": [{"$ref": "#/$defs/move"}, {"type": "string"}]}}
    if kind == "steps":
        return {"type": "array", "items": {"$ref": "#/$defs/step"}, "minItems": 1, "maxItems": LIMITS["steps"]}
    raise KeyError(kind)


def _object(table, required, **extra):
    return {"type": "object", "additionalProperties": False, "required": required,
            "properties": {k: _schema_of(*v) for k, v in table.items() if v[0] != "parts"}, **extra}


def _build_schema():
    part = _object(PART_KEYS, ["id"], oneOf=[{"required": [k]} for k in SHAPE_KEYS])
    group = _object(GROUP_KEYS, ["id", "group"])
    group["properties"]["group"] = {"type": "array", "items": {"$ref": "#/$defs/part"}, "minItems": 1}
    scene = _object(SCENE_KEYS, [], anyOf=[{"required": ["parts"]}, {"required": ["layout", "nodes"]}])
    scene["properties"]["parts"] = {"type": "array", "minItems": 1, "maxItems": LIMITS["parts"],
                                    "items": {"anyOf": [{"$ref": "#/$defs/part"}, {"$ref": "#/$defs/group"}]}}
    scene["properties"]["nodes"] = {"type": "array", "minItems": 1, "items": _object(NODE_KEYS, ["id"])}
    scene.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Rook render scene",
                  "$defs": {"part": part, "group": group, "repeat": _object(REPEAT_KEYS, ["count"]),
                            "step": _object(STEP_KEYS, ["light"]), "move": _object(MOVE_KEYS, [])}})
    return scene


SCHEMA = _build_schema()


# The sampler.

def _svg_arc(cr, x0, y0, rx, ry, angle, large, sweep, x, y):
    """An SVG endpoint arc, as Cairo's centre arc (SVG 1.1, appendix F.6.5)."""
    if (x0, y0) == (x, y):
        return
    if not rx * rx or not ry * ry:  # A radius too small to square is a line, as in _arc_points.
        cr.line_to(x, y)
        return
    rx, ry, phi = abs(rx), abs(ry), math.radians(angle)
    c, s = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x) / 2, (y0 - y) / 2
    x1, y1 = c * dx + s * dy, -s * dx + c * dy
    grow = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if grow > 1:  # As in _arc_points: hypot keeps a tiny radius from overflowing.
        g = math.sqrt(grow) if grow < math.inf else math.hypot(x1 / rx, y1 / ry)
        rx, ry = rx * g, ry * g
    if not math.isfinite(rx * rx * ry * ry):  # As in _arc_points: radii far apart in size draw a line.
        cr.line_to(x, y)
        return
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    if den:
        k = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
        cx1, cy1 = k * rx * y1 / ry, -k * ry * x1 / rx
    else:  # The ends almost meet and den underflows: as in _arc_points, the chord's length cancels out.
        chord = math.hypot(x1, y1) or 1.0
        ux1, uy1 = x1 / chord, y1 / chord
        k = math.sqrt(max(0.0, num / (rx * rx * uy1 * uy1 + ry * ry * ux1 * ux1 or 1.0)))
        k *= -1 if large == sweep else 1
        cx1, cy1 = k * rx * uy1 / ry, -k * ry * ux1 / rx
    cx, cy = c * cx1 - s * cy1 + (x0 + x) / 2, s * cx1 + c * cy1 + (y0 + y) / 2
    t1 = math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
    t2 = math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx)
    cr.save()
    cr.translate(cx, cy)
    cr.rotate(phi)
    cr.scale(rx, ry)
    (cr.arc if sweep else cr.arc_negative)(0, 0, 1, t1, t2)
    cr.restore()


def _arrow_curve(part):
    """An arrow's shaft as a cubic (start, control 1, control 2, end), bowed by its bend."""
    x1, y1, x2, y2 = part["args"]
    length = math.hypot(x2 - x1, y2 - y1)
    nx, ny = -(y2 - y1) / length, (x2 - x1) / length  # To the right of the travel, on a y-down screen.
    qx, qy = (x1 + x2) / 2 + 2 * part["bend"] * nx, (y1 + y2) / 2 + 2 * part["bend"] * ny
    return ((x1, y1), (x1 + 2 / 3 * (qx - x1), y1 + 2 / 3 * (qy - y1)),
            (x2 + 2 / 3 * (qx - x2), y2 + 2 / 3 * (qy - y2)), (x2, y2))


def _trace(cr, part):
    """Add one copy of the part's outline to cr's path, in view units."""
    a, shape = part["args"], part["shape"]
    cr.new_sub_path()
    if shape == "circle":
        cr.arc(a[0], a[1], a[2], 0, 2 * math.pi)
        cr.close_path()
    elif shape == "ellipse":
        cr.save()
        cr.translate(a[0], a[1])
        cr.scale(a[2], a[3])
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.close_path()
    elif shape == "rect":
        x, y, w, h = a
        r = min(part["radius"], w / 2, h / 2)
        if r <= 0:
            cr.rectangle(x, y, w, h)
        else:
            cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
            cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
            cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
            cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
            cr.close_path()
    elif shape == "line":
        cr.move_to(a[0], a[1])
        cr.line_to(a[2], a[3])
    elif shape == "arc":
        end = a[4] if a[4] > a[3] else a[4] + 360
        cr.arc(a[0], a[1], a[2], math.radians(a[3]), math.radians(end))
    elif shape == "poly":
        cr.move_to(*a[0])
        for p in a[1:]:
            cr.line_to(*p)
        if part["closed"]:
            cr.close_path()
    elif shape == "path":
        _trace_ops(cr, a)
    elif shape == "stencil":
        for _, ops in _stencil(a)[0]:
            _trace_ops(cr, ops)
    else:
        # The shaft stops at the head's base, so its round end never blunts the tip. sample draws the head itself.
        p0, c1, c2, p3 = _shaft(part)
        cr.move_to(*p0)
        cr.curve_to(*c1, *c2, *p3)


def _trace_ops(cr, ops):
    for op in ops:
        if op[0] == "M":
            cr.move_to(*op[1:])
        elif op[0] == "L":
            cr.line_to(*op[1:])
        elif op[0] == "C":
            cr.curve_to(*op[1:])
        elif op[0] == "A":
            _svg_arc(cr, *cr.get_current_point(), *op[1:])
        else:
            cr.close_path()


def _ink_stencil(cr, part, px):
    """Draw one copy of a stencil with its own inks, lines px wide on the device whatever its size. Returns the device
    box of its ink."""
    boxes = []
    for ink, ops in _stencil(part["args"])[0]:
        cr.new_path()
        _trace_ops(cr, ops)
        cr.save()
        cr.identity_matrix()  # The path stays where it is; widths are now in device pixels.
        if ink == "fill":
            boxes.append(cr.fill_extents())
            cr.fill()
        else:
            cr.set_line_width(px * (stencils.THIN if ink == "thin" else 1.0))
            boxes.append(cr.stroke_extents())
            cr.stroke()
        cr.restore()
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _head(part):
    """An arrow's head in view units: its tip, its unit direction there, and its length."""
    p0, c1, c2, p3 = _arrow_curve(part)
    d = math.dist(c2, p3) or 1.0
    length, w = math.dist(p0, p3), part["width"]
    size = min(HEAD_LENGTH * w, max(min(HEAD_MIN * w, 0.6 * length), HEAD_SHARE * length))
    return p3, ((p3[0] - c2[0]) / d, (p3[1] - c2[1]) / d), size


def _shaft(part):
    """The arrow's curve cut where the head's base begins: (start, control 1, control 2, end)."""
    p0, c1, c2, p3 = _arrow_curve(part)
    size = _head(part)[2]
    point = lambda t: tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * e  # noqa
                            for a, b, c, e in zip(p0, c1, c2, p3))
    lo, hi = 0.0, 1.0
    for _ in range(30):  # The t whose point lies one head length from the tip.
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if math.dist(point(mid), p3) > size else (lo, mid)
    t = lo
    # de Casteljau: the first part of the curve, up to t.
    ab = [a + (b - a) * t for a, b in zip(p0, c1)]
    bc = [b + (c - b) * t for b, c in zip(c1, c2)]
    cd = [c + (e - c) * t for c, e in zip(c2, p3)]
    abc = [a + (b - a) * t for a, b in zip(ab, bc)]
    bcd = [b + (c - b) * t for b, c in zip(bc, cd)]
    return p0, tuple(ab), tuple(abc), tuple(a + (b - a) * t for a, b in zip(abc, bcd))


def _line_grains(paths, count, rng, sigma):
    """count points spread evenly along even polylines, each a little off its line (sigma px), so a line's dust has an
    even density and a steady width."""
    total = sum(p["length"] for p in paths) or 1.0
    out = []
    for k in range(count):
        at = (k + 0.5 + rng.uniform(-0.3, 0.3)) / count * total
        for path in paths:
            if at <= path["length"] or path is paths[-1]:
                x, y, nx, ny = _along(path["points"], at / path["length"])
                off = rng.gauss(0, sigma)
                out.append((x + off * nx, y + off * ny))
                break
            at -= path["length"]
    return out


def _head_grains(part, fit, count, rng):
    """count grains that draw the head of each copy of an arrow, in mask pixels: two fifths packed along its two
    sides from the tip, the rest filling it, so the tip is a point and the head reads as solid."""
    tip, (ux, uy), size = _head(part)
    out, copies = [], part["copies"]
    for m in copies:
        each = count // len(copies)
        t = _apply(fit, *_apply(m, *tip))
        ahead = _apply(fit, *_apply(m, tip[0] + ux * size, tip[1] + uy * size))
        dx, dy = ahead[0] - t[0], ahead[1] - t[1]  # One head length forward, in pixels.
        corners = [(t[0] - dx - side * dy / 2, t[1] - dy + side * dx / 2) for side in (-1, 1)]
        sides = round(each * 2 / 5)
        for k in range(sides):
            cx, cy = corners[k % 2]
            f = (k // 2 + 0.5) / ((sides + 1) // 2)
            out.append((t[0] + (cx - t[0]) * f + rng.gauss(0, 0.35), t[1] + (cy - t[1]) * f + rng.gauss(0, 0.35)))
        for _ in range(each - sides):
            a, b = rng.random(), rng.random()
            a, b = (1 - a, 1 - b) if a + b > 1 else (a, b)
            out.append((t[0] + (corners[0][0] - t[0]) * a + (corners[1][0] - t[0]) * b,
                        t[1] + (corners[0][1] - t[1]) * a + (corners[1][1] - t[1]) * b))
    return out


def _fit(view, box):
    """The view's size in pixels in a box, keeping its aspect, and the matrix from view units to mask pixels."""
    scale = box / max(view)
    w, h = math.ceil(view[0] * scale) + 2, math.ceil(view[1] * scale) + 2
    return w, h, scale, (scale, 0.0, 0.0, scale, 1.0, 1.0)


def _mask(part, fit, w, h):
    """The part's pixels (index y * w + x) in a mask w by h, and how far its unclipped ink spills past the view."""
    surface = cairo.ImageSurface(cairo.FORMAT_A8, w, h)
    cr = cairo.Context(surface)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    spill = 0.0
    min_x, min_y, max_x, max_y = float(w), float(h), 0.0, 0.0
    for m in part["copies"]:
        cr.set_matrix(cairo.Matrix(*fit))
        cr.transform(cairo.Matrix(*m))
        if part["shape"] == "stencil":
            x0, y0, x1, y1 = _ink_stencil(cr, part, part["width"] * fit[0])
            spill = max(spill, 1 - x0, 1 - y0, x1 - (w - 1), y1 - (h - 1))
            if x1 > x0 or y1 > y0:
                min_x, min_y = min(min_x, x0), min(min_y, y0)
                max_x, max_y = max(max_x, x1), max(max_y, y1)
            continue
        cr.set_line_width(part["width"])
        _trace(cr, part)
        x0, y0, x1, y1 = cr.fill_extents() if part["fill"] else cr.stroke_extents()
        corners = [cr.user_to_device(x, y) for x in (x0, x1) for y in (y0, y1)]
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        lx0, ly0, lx1, ly1 = min(xs), min(ys), max(xs), max(ys)
        spill = max(spill, 1 - lx0, 1 - ly0, lx1 - (w - 1), ly1 - (h - 1))
        if lx1 > lx0 or ly1 > ly0:
            min_x, min_y = min(min_x, lx0), min(min_y, ly0)
            max_x, max_y = max(max_x, lx1), max(max_y, ly1)
        if part["fill"]:
            cr.fill()  # Each copy alone, so copies that touch add up and do not cut holes in each other.
        else:
            cr.stroke()
    surface.flush()
    rx0, ry0 = max(0, math.floor(min_x) - 2), max(0, math.floor(min_y) - 2)
    rx1, ry1 = min(w, math.ceil(max_x) + 2), min(h, math.ceil(max_y) + 2)
    rw = rx1 - rx0
    if rw <= 0 or ry1 <= ry0:
        return [], spill
    data, stride = surface.get_data(), surface.get_stride()
    pixels = []
    for y in range(ry0, ry1):
        row = bytes(data[y * stride + rx0:y * stride + rx1])
        if row.count(0) != rw:
            base = y * w + rx0
            pixels += [base + x for x, v in enumerate(row) if v > 127]
    return pixels, spill


def _freeze(value):
    """Turn nested lists into tuples so part arguments can act as a cache key."""
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _part_geom(part, fit, w, h, cache):
    """Cached mask, edge/core split, box, and centre for one part geometry."""
    key = (w, h, part["shape"], part["fill"], part["width"], tuple(part["copies"]), _freeze(part["args"]))
    entry = cache.get(key)
    if entry is not None:
        return entry
    pixels, spill = _mask(part, fit, w, h)
    if pixels:
        xs, ys = [p % w for p in pixels], [p // w for p in pixels]
        box = (min(xs) - w / 2, min(ys) - h / 2, max(xs) + 1 - w / 2, max(ys) + 1 - h / 2)
        centre = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        inside = set(pixels)
        edge = [p for p in pixels if not (p - 1 in inside and p + 1 in inside and p - w in inside and p + w in inside)]
        rim = set(edge)
        core = [p for p in pixels if p not in rim]
        ink = len(edge) + 0.4 * (len(pixels) - len(edge)) if part["fill"] else len(pixels)
    else:
        box = centre = None
        inside, edge, core, ink = set(), [], [], 0
    entry = {"pixels": pixels, "spill": spill, "ink": ink, "box": box, "centre": centre,
             "inside": inside, "edge": edge, "core": core}
    cache[key] = entry
    return entry


def _flow_paths(part, fit):
    """The part's strokes as even polylines in mask pixels, about 1.5 px apart, without arrowheads."""
    surface = cairo.ImageSurface(cairo.FORMAT_A8, 1, 1)
    cr = cairo.Context(surface)
    cr.set_tolerance(0.05)
    out = []
    for m in part["copies"]:
        cr.new_path()
        cr.set_matrix(cairo.Matrix(*fit))
        cr.transform(cairo.Matrix(*m))
        _trace(cr, part)
        runs = []
        for kind, pts in cr.copy_path_flat():
            if kind == cairo.PATH_MOVE_TO:
                runs.append([cr.user_to_device(*pts)])
            elif kind == cairo.PATH_LINE_TO:
                runs[-1].append(cr.user_to_device(*pts))
            elif kind == cairo.PATH_CLOSE_PATH and runs:
                runs[-1].append(runs[-1][0])
                runs[-1] = ("closed", runs[-1])
        for run in runs:
            closed, run = (True, run[1]) if run[0] == "closed" else (False, run)
            if len(run) >= 2:
                out.append(_even(run, closed))
    return [p for p in out if p["length"] > 4]


def _even(run, closed):
    """A polyline resampled to points about 1.5 px apart, with its length."""
    total = [0.0]
    for a, b in zip(run, run[1:]):
        total.append(total[-1] + math.dist(a, b))
    n = max(2, int(total[-1] / 1.5))
    points, k = [], 0
    for j in range(n + 1):
        d = total[-1] * j / n
        while k < len(run) - 2 and total[k + 1] < d:
            k += 1
        seg = total[k + 1] - total[k] or 1.0
        f = (d - total[k]) / seg
        points.append((run[k][0] + (run[k + 1][0] - run[k][0]) * f, run[k][1] + (run[k + 1][1] - run[k][1]) * f))
    return {"points": points, "length": total[-1], "closed": closed}


def _along(points, u):
    """A point u of the way along an even polyline, and the unit normal there."""
    f = min(1.0, max(0.0, u)) * (len(points) - 1)
    k = min(len(points) - 2, int(f))
    (x0, y0), (x1, y1) = points[k], points[k + 1]
    t = math.hypot(x1 - x0, y1 - y0) or 1.0
    return x0 + (x1 - x0) * (f - k), y0 + (y1 - y0) * (f - k), -(y1 - y0) / t, (x1 - x0) / t


def _spread(rng, pixels, count):
    """count pixels, each used once before any is used twice, so the dust has few clumps and few holes."""
    out = []
    while len(out) < count:
        out += rng.sample(pixels, min(len(pixels), count - len(out)))
    return out


def _shares(raw, budget, floor):
    """Whole grain counts that add up to budget, in proportion to raw, with at least floor for each part with ink."""
    live = [i for i, r in enumerate(raw) if r > 0]
    counts = [0] * len(raw)
    if not live:
        return counts
    floor = min(floor, budget // len(live))
    fixed, want = set(), {}
    while True:
        free = budget - floor * len(fixed)
        total = sum(raw[i] for i in live if i not in fixed)
        want = {i: free * raw[i] / total for i in live if i not in fixed} if total else {}
        low = [i for i, v in want.items() if v < floor]
        if not low:
            break
        fixed.update(low)
    for i in fixed:
        counts[i] = floor
    for i, v in want.items():
        counts[i] = int(v)
    left = budget - sum(counts)
    for i in sorted(want or live, key=lambda i: (want.get(i, 0) - counts[i], raw[i]), reverse=True)[:left]:
        counts[i] += 1
    return counts


def _chord(inside, w, h, x, y, dx, dy):
    """The ends of the run through (x, y) along (dx, dy) that stays inside the mask."""
    def walk(sign):
        t = 0.0
        while True:
            px, py = int(x + (t + sign) * dx), int(y + (t + sign) * dy)
            if not (0 <= px < w and 0 <= py < h) or py * w + px not in inside:
                return t
            t += sign
    a, b = walk(-1.0), walk(1.0)
    return (x + a * dx, y + a * dy, x + b * dx, y + b * dy)


def _lit(part, light):
    return any(part["id"] == n or part["group"] == n for n in light)


def sample(scene, budget=None, seed=0, box=None, step=None, previous=None, entrance=None, dance=None):
    """The form for a checked scene: every grain's home, owner part and motion, the parts' motion data, the labels, the
    grains per part, and notes for the author. budget and box are the grains and the form's size in pixels (the
    scene's SIZE_FORM by default). step is a step's index, which lights its parts. previous is the form shown before, so
    parts keep their grains (see the top). entrance picks "draw" or "fly" and dance picks a preset for a diagram."""
    started = time.perf_counter()
    whole = scene
    if entrance is None:
        entrance = (previous.get("entrance", DIAGRAM_ENTRANCE)
                    if previous and previous.get("scene") is whole else DIAGRAM_ENTRANCE)
    if entrance not in DIAGRAM_ENTRANCES:
        entrance = DIAGRAM_ENTRANCE
    if dance is None:
        dance = (previous.get("dance", DANCE) if previous and previous.get("scene") is whole else DANCE)
    if dance not in DANCE_PRESETS:
        dance = DANCE
    if step is not None and scene["steps"][step].get("parts"):
        scene = {**scene, "parts": scene["steps"][step]["parts"]}  # The step's pose.
    budget = budget or SIZE_FORM[scene["size"]][0]
    if not box:
        # The drawing and the labels at its sides share CANVAS.
        box, char = SIZE_FORM[scene["size"]][1], LABEL_TYPE[scene["size"]][2]
        side = {at: max([char * len(p["label"]) + 7 for p in scene["parts"] if p["label"] and p["label_at"] == at],
                        default=0) for at in ("left", "right")}
        box = min(box, int((CANVAS - side["left"] - side["right"]) * max(scene["view"]) / scene["view"][0]))
    rng = random.Random(f"{seed}:{scene['name']}")
    w, h, scale, fit = _fit(scene["view"], box)
    light = scene["steps"][step]["light"] if step is not None else None
    part_cache = previous["_part_cache"] if (previous and previous.get("scene") is whole
                                             and "_part_cache" in previous) else {}
    parts, geoms, masks, notes = scene["parts"], [], [], []
    if (_dense(scene) and previous and previous.get("scene") is whole and previous.get("material")
            and len(previous["x"]) == budget and len(previous.get("swarm") or ()) == budget):
        return _step_swarm(whole, scene, parts, step, light, previous, fit, w, h, scale, box, budget,
                           entrance, dance, part_cache, rng, started)
    for part in parts:
        geom = _part_geom(part, fit, w, h, part_cache)
        geoms.append(geom)
        masks.append(geom["pixels"])
        if geom["spill"] > 1.5:
            notes.append(f"Part '{part['id']}' reaches past the view's edge and is cut off there. Keep it inside "
                         f"[0, 0, {scene['view'][0]:g}, {scene['view'][1]:g}], or make the view larger.")
    raw = []
    for part, geom in zip(parts, geoms):
        # Diagrams split living grains into ambient homes and one travelling highlight swarm.
        boost = (1.0 if light is None or part["shape"] == "arrow" or _dense(scene) else
                 STEP_GATHER if _lit(part, light) else STEP_THIN)
        ink = geom["ink"]
        if part["shape"] == "arrow":  # The head is drawn apart from the mask (see _head_grains); its area counts too.
            size = _head(part)[2] * scale * math.sqrt(abs(part["copies"][0][0] * part["copies"][0][3]
                                                          - part["copies"][0][1] * part["copies"][0][2]))
            ink += size * size / 2 * len(part["copies"])
            ink *= ARROW_WEIGHT
        raw.append(part["weight"] * boost * STRESS.get(part["stress"], (1.0,))[0] * ink ** 0.8)
    dense = _dense(scene)
    if dense:
        swarm_budget = round(budget * SWARM_SHARE)
        amb_budget = budget - swarm_budget
        amb_floor = max(12, amb_budget // max(1, len(parts) * 2))
        amb_counts = _shares(raw, amb_budget, amb_floor)
        lit_ids = [pi for pi, p in enumerate(parts) if light is not None and _lit(p, light)]
        swarm_counts = _swarm_shares(raw, swarm_budget, lit_ids)
        counts = [a + s for a, s in zip(amb_counts, swarm_counts)]
    else:
        amb_counts = _shares(raw, budget, max(8, budget // 60))
        swarm_counts = [0] * len(parts)
        counts = list(amb_counts)
    # A moved part's pose in form pixels, (dx, dy, degrees, about x, about y, scale), and the pose it flies from. A
    # part that flies keeps the grains it had, so it arrives whole; the largest still parts give or take the rest.
    poses = [None if not part.get("pose") else (
        part["pose"][0][0] * scale, part["pose"][0][1] * scale, part["pose"][1], part["pose"][2][0] * scale + 1 - w / 2,
        part["pose"][2][1] * scale + 1 - h / 2, part["pose"][3]) for part in parts]
    was = {p["id"]: p.get("pose") for p in previous["parts"]} if previous and previous.get("scene") is whole else {}
    flying = {k for k, part in enumerate(parts) if was and was.get(part["id"]) != poses[k]}
    if flying and len(previous["x"]) == budget and not dense:
        for k in flying:
            counts[k] = previous["grains"].get(parts[k]["id"], counts[k])
        still = sorted((k for k in range(len(parts)) if k not in flying and counts[k] > 8), key=lambda k: -counts[k])
        extra, turn = sum(counts) - budget, 0
        while extra and still:
            k = still[turn % len(still)]
            counts[k] -= 1 if extra > 0 else -1
            extra += -1 if extra > 0 else 1
            turn += 1
    homes, info = [], []
    for pi, (part, geom, n) in enumerate(zip(parts, geoms, counts)):
        pixels = geom["pixels"]
        data = {"id": part["id"], "motion": part["motion"], "speed": part["speed"], "reverse": part["reverse"]}
        if poses[pi]:
            data["pose"] = poses[pi]
        if pi in flying:
            data["flight"] = (was.get(part["id"]), poses[pi])
        if dense:
            data["lit"] = light is not None and _lit(part, light)
            data["was_lit"] = (previous["parts"][pi].get("lit", data["lit"]) if was and pi < len(previous["parts"])
                               else data["lit"])
        info.append(data)
        if not pixels:
            notes.append(f"Part '{part['id']}' draws nothing inside the view. Check its numbers against the view, "
                         f"[{scene['view'][0]:g}, {scene['view'][1]:g}].")
            continue
        data["box"], data["centre"] = geom["box"], geom["centre"]
        width_px = part["width"] * scale * (1.0 if part["shape"] == "stencil" else math.sqrt(abs(
            part["copies"][0][0] * part["copies"][0][3] - part["copies"][0][1] * part["copies"][0][2])))
        mine = _sample_part_grains(part, geom, data, n, fit, w, h, scale, rng)
        lit = 1.0 if light is None else (LIT if _lit(part, light) else UNLIT)
        if dense:  # Quiet until a step lights the part.
            lit = LIFE_GLOW[light is not None and _lit(part, light)]
        stress_mul = STRESS.get(part["stress"], (1.0, 1.0))[1] * (OUTLINES[OUTLINE_LOOK][2] if _outlined(scene, part)
                                                                  else 1.0)
        lit *= stress_mul
        n_sw = swarm_counts[pi]
        sw_set = ({int(k * len(mine) / n_sw) for k in range(n_sw)} if 0 < n_sw < len(mine)
                  else (set(range(len(mine))) if n_sw >= len(mine) and n_sw > 0 else set()))
        homes += [(x, y, pi, move, lit * hmul, stress_mul * hmul, idx_m in sw_set)
                  for idx_m, (x, y, move, hmul) in enumerate(mine)]
        # Notes for the author: thin, sparse or tiny parts.
        bw, bh = data["box"][2] - data["box"][0], data["box"][3] - data["box"][1]
        if not part["fill"] and width_px < 2.4 and part["motion"] != "fall":
            need = 3 / (width_px / part["width"])
            notes.append(f"Part '{part['id']}' is {width_px:.1f} px thick at this size; dust needs about 3 px. "
                         f"Set width to at least {need:.2g}.")
        if max(bw, bh) < 6:
            notes.append(f"Part '{part['id']}' is only {max(bw, bh):.0f} px across; it will read as a speck. "
                         "Draw it larger.")
        elif n < 14:
            notes.append(f"Part '{part['id']}' gets {n} grains; it will read as a smudge. Give it more weight, draw "
                         "it larger, or use a larger budget.")
        elif not part["fill"] and part["shape"] != "stencil" and n / max(1.0, len(pixels) / max(1.0, width_px)) < 0.45:
            gap = len(pixels) / max(1.0, width_px) / n
            notes.append(f"Part '{part['id']}' gets one grain every {gap:.1f} px along its line, so it breaks up. "
                         "Give it more weight, or use a larger budget.")
    # Author-only overlap and crowding notes run on scene load, not on live step switches.
    need_notes = step is None or previous is None
    sets = [g["inside"] for g in geoms] if need_notes else None
    if need_notes:
        for i in range(len(parts)):
            for j in range(len(parts)):
                if (i != j and masks[i] and masks[j] and len(masks[i]) <= len(masks[j])
                        and (i < j or len(masks[i]) < len(masks[j]))):
                    shared = len(sets[i] & sets[j])
                    if shared > 0.7 * len(masks[i]) and not (parts[j]["fill"] and not parts[i]["fill"]):
                        notes.append(f"Part '{parts[i]['id']}' lies mostly on part '{parts[j]['id']}', so their dust merges "
                                     "and it does not read. Move it, or make one of them an outline.")
        if scene["size"] == "diagram":  # An icon's parts touch on purpose: a handle on its lens, a trunk under its crown.
            _mess_notes(parts, masks, sets, info, fit, w, scale, notes)
        ink = set().union(*sets) if sets else set()
        if ink:
            xs, ys = [p % w for p in ink], [p // w for p in ink]
            used = max((max(xs) - min(xs)) / w, (max(ys) - min(ys)) / h)
            if used < 0.6:
                notes.append(f"The drawing fills {used:.0%} of the view at most; make the view smaller around it to "
                             "draw it larger.")
    # A crank, a rod and a piston in one group move as an engine does while they fly (see flights): their pins, in
    # form pixels, and the line the piston slides on, from the crank's journal toward the piston as drawn.
    def px(ps, k, at):
        x, y = _apply(fit, *_apply(ps[k]["copies"][0], *at))
        return x - w / 2, y - h / 2

    for g in {p["group"] for p in parts if p["group"]}:
        roles = {p["args"]: k for k, p in enumerate(parts) if p["group"] == g and p["shape"] == "stencil"
                 and p["args"] in ("crank", "rod", "piston") and len(p["copies"]) == 1}
        if len(roles) == 3:
            crank, rod, piston = roles["crank"], roles["rod"], roles["piston"]
            journal, pin = px(parts, crank, (0, 0)), px(parts, crank, stencils.PINS["crank"])
            top, end = px(parts, rod, (0, 0)), px(parts, rod, stencils.PINS["rod"])
            a0, a1 = px(whole["parts"], crank, (0, 0)), px(whole["parts"], piston, (0, 0))
            span = math.dist(a0, a1) or 1.0
            info[crank]["engine"] = (piston, rod, journal, pin, top, end, ((a1[0] - a0[0]) / span,
                                                                         (a1[1] - a0[1]) / span), math.dist(top, end))
    labels = _labels(scene, info, notes, box)
    if need_notes:
        for label in labels:  # A label on a line or a shape reads as part of it.
            l, t, r, b = (int(v) for v in (label["span"][0] + w / 2, label["span"][1] + h / 2 + 2,
                                             label["span"][2] + w / 2, label["span"][3] + h / 2 - 2))
            spot = {y * w + x for y in range(max(0, t), min(h, b)) for x in range(max(0, l), min(w, r))}
            group = next(p["group"] for p in parts if p["id"] == label["id"])
            for part, cover in zip(parts, sets):
                # A group's parts fit on purpose, so a label may sit on its own group's parts.
                if part["id"] != label["id"] and not (group and part["group"] == group) and len(spot & cover) > 8:
                    notes.append(f"The label of '{label['id']}' sits on '{part['id']}'. Move it with label_at, or move "
                                 f"'{part['id']}'.")
                    break
    lost = {info[home[2]]["id"] for home in homes if not (math.isfinite(home[0]) and math.isfinite(home[1]))}
    if lost:  # No grain may reach the engine without a place: the chip has no second chance.
        homes = [home for home in homes if math.isfinite(home[0]) and math.isfinite(home[1])]
        notes += [f"Part '{pid}' could not be placed, so some of its dust is left out. Check its numbers."
                  for pid in lost]
    if homes and len(homes) < budget:  # Every grain needs a home: grains a part could not place double up on others.
        homes += [homes[k % len(homes)] for k in range(budget - len(homes))]
    order = _assign(homes, info, previous, budget)
    form = {"name": scene["name"], "title": scene["title"], "kind": scene["size"], "budget": budget, "box": box,
            "size": (w, h), "scene": whole, "drawn": parts, "_part_cache": part_cache, "entrance": entrance,
            "dance": dance, "step": step, "caption": scene["steps"][step]["caption"] if step is not None else "",
            "x": [homes[k][0] for k in order], "y": [homes[k][1] for k in order],
            "part": [homes[k][2] for k in order], "move": [homes[k][3] for k in order],
            "bright": [homes[k][4] for k in order], "bright_base": [homes[k][5] for k in order],
            "owner": [info[homes[k][2]]["id"] for k in order],
            "parts": info, "labels": labels, "grains": {p["id"]: n for p, n in zip(parts, counts)}, "notes": notes}
    if dense:
        same = previous and previous.get("scene") is whole and previous.get("material")
        mat = previous["material"] if same else bake_material(whole, fit, w, h)
        form["material"] = mat
        form["fit"] = fit
        form["swarm"] = [homes[k][6] for k in order]
        form["raw"] = raw
        # Record each grain's arrival u once on scene start for the draw-on entrance.
        form["grain_u"] = _grain_arrivals(form, mat)
        # Bake overrides only for links whose routed path changed in this step.
        overrides = {}
        for k, (base_p, cur_p) in enumerate(zip(whole["parts"], parts)):
            if cur_p["shape"] == "arrow" and cur_p["args"] != base_p["args"]:
                overrides[k] = _bake_part(cur_p, fit, w, h, mat["bake_scale"])
        if overrides:
            form["material_overrides"] = overrides
    form["ms"] = round((time.perf_counter() - started) * 1000, 1)
    return form


def _swarm_shares(raw, swarm_budget, lit_ids):
    """Divide swarm_budget across lit_ids by ink weight up to SWARM_CAP times each part's base share.
    Overflow stays spread across the remaining parts, as when nothing is lit."""
    if swarm_budget <= 0 or not raw:
        return [0] * len(raw)
    all_active = [pi for pi, r in enumerate(raw) if r > 0] or list(range(len(raw)))
    base_floor = min(4, swarm_budget // max(1, len(all_active) * 2))
    base_sub = _shares([raw[pi] for pi in all_active], swarm_budget, base_floor)
    base = [0] * len(raw)
    for pi, c in zip(all_active, base_sub):
        base[pi] = c
    if not lit_ids:
        return base
    active = [pi for pi in lit_ids if raw[pi] > 0] or list(lit_ids)
    # Cap each lit part relative to its whole-scene share so tiny parts never blow out into blobs.
    caps = {pi: min(swarm_budget, max(24, round(base[pi] * SWARM_CAP))) for pi in active}
    out = [0] * len(raw)
    rem_budget = min(swarm_budget, sum(caps.values()))
    open_ids = list(active)
    while rem_budget > 0 and open_ids:
        floor = min(16, rem_budget // max(1, len(open_ids) * 3))
        sub = _shares([raw[pi] for pi in open_ids], rem_budget, floor)
        clipped = False
        next_open = []
        for pi, c in zip(open_ids, sub):
            room = caps[pi] - out[pi]
            if c > room:
                out[pi] += room
                rem_budget -= room
                clipped = True
            else:
                next_open.append((pi, c))
        if not clipped:
            for pi, c in next_open:
                out[pi] += c
            rem_budget = 0
            break
        open_ids = [pi for pi, _ in next_open if out[pi] < caps[pi]]
    overflow = swarm_budget - sum(out)
    if overflow > 0:
        lit_set = set(active)
        quiet = [pi for pi in all_active if pi not in lit_set] or all_active
        q_floor = min(4, overflow // max(1, len(quiet) * 2))
        q_sub = _shares([raw[pi] for pi in quiet], overflow, q_floor)
        for pi, c in zip(quiet, q_sub):
            out[pi] += c
    return out


def _sample_part_grains(part, geom, data, n, fit, w, h, scale, rng, append_lanes=False):
    """Sample n living grain homes on one part, populating its motion metadata."""
    pixels = geom["pixels"]
    if n <= 0 or not pixels:
        return []
    inside, edge, core = geom["inside"], geom["edge"], geom["core"]
    motion, moving = part["motion"], 0
    if motion == "flow":
        if "paths" not in geom:
            geom["paths"] = _flow_paths(part, fit)
        data["paths"] = geom["paths"]
        moving = round(n * 0.55) if data["paths"] else 0
    elif motion == "fall":
        moving = n if not part["closed"] else round(n * 0.4)
    elif motion == "fizz":
        moving = round(n * 0.35)
    elif motion == "glare":
        moving = round(n * 0.5)
    still = n - moving
    on_edge = round(still * min(0.55, 3 * len(edge) / (3 * len(edge) + len(core)))) if core else still
    chosen = _spread(rng, edge, on_edge) + (_spread(rng, core, still - on_edge) if core else [])
    mine = [(p % w + rng.random() - w / 2, p // w + rng.random() - h / 2, None, 1.0) for p in chosen]
    width_px = part["width"] * scale * (1.0 if part["shape"] == "stencil" else math.sqrt(abs(
        part["copies"][0][0] * part["copies"][0][3] - part["copies"][0][1] * part["copies"][0][2])))
    march = part["shape"] == "arrow"
    if march:
        if "paths" not in geom:
            geom["paths"] = _flow_paths(part, fit)
        data["paths"] = shafts = geom["paths"]
        size_px = _head(part)[2] * width_px / part["width"]
        moving = (min(round(n * MARCH_SHARE), round(sum(p["length"] for p in shafts) / MARCH_SPACING))
                  if shafts else 0) if motion == "flow" else moving
        heads = min(round(HEAD_CAP * n), round(HEAD_GRAINS * size_px) * len(part["copies"]))
        mine = [(x - w / 2, y - h / 2, None, 1.0) for x, y in
                _line_grains(shafts, n - moving - heads, rng, min(2.0, max(0.6, 0.22 * width_px)))] + [
            (x - w / 2, y - h / 2, None, HEAD_BRIGHT) for x, y in _head_grains(part, fit, heads, rng)]
    half = max(0.6, width_px / 2) if not part["fill"] else 1.5
    if motion == "flow" and moving and data.get("paths"):
        total = sum(p["length"] for p in data["paths"])
        data["speed"] = FLOW_SPEED[part["speed"]]
        data["spread"] = half * 0.6
        if march:
            data["spread"], data["hidden"] = half * 0.3, MARCH_HIDDEN
            data["speed"] = min(MARCH_PACE[1], max(MARCH_PACE[0], data["paths"][0]["length"]
                                                    / MARCH_SECONDS[part["speed"]]))
        given = 0
        for k, path in enumerate(data["paths"]):
            m = moving - given if k == len(data["paths"]) - 1 else round(moving * path["length"] / total)
            given += m
            comets = max(1, round(path["length"] / 70))
            for j in range(m):
                comet, rank = j % comets, (j // comets + rng.random()) / max(1, m // comets)
                tail = min(1.0, rank) ** 1.5
                phase = ((comet + 1 - 0.7 * tail) / comets) % 1
                side = max(-1.6, min(1.6, rng.gauss(0, 0.7)))
                if march:  # Evenly spaced and all alike: a steady march, not a comet that blinks.
                    phase, tail, side = (j + 0.5 + rng.uniform(-0.15, 0.15)) / max(1, m), -0.3, rng.gauss(0, 0.3)
                x, y, nx, ny = _along(path["points"], phase)
                mine.append((x - w / 2 + side * data["spread"] * nx, y - h / 2 + side * data["spread"] * ny,
                             (k, phase, side, tail), 1.0))
    elif motion in ("fall", "fizz", "glare") and moving:
        lanes = list(data.get("lanes") or ()) if append_lanes else []
        direction = {"fall": (0.0, 1.0), "fizz": (0.0, -1.0), "glare": (0.7071, 0.7071)}[motion]
        if motion == "glare" and "band" not in data:
            proj = [(p % w - w / 2) * direction[0] + (p // w - h / 2) * direction[1] for p in pixels]
            data["band"] = {"dir": direction, "low": min(proj), "high": max(proj),
                            "width": max(3.5, 0.11 * (max(proj) - min(proj))),
                            "period": GLARE_PERIOD[part["speed"]], "pass": 0.45}
        if motion == "fizz":
            data["rise"] = FIZZ_RISE[part["speed"]]
        if motion == "fall":
            data["accel"] = FALL_ACCEL[part["speed"]]
        for p in _spread(rng, pixels, moving):
            x, y = p % w + rng.random(), p // w + rng.random()
            if motion == "fizz":
                top = data["box"][1] - rng.uniform(2.0, max(8.0, 0.3 * (data["box"][3] - data["box"][1])))
                lane = (x - w / 2, y - h / 2, x - w / 2, top)
            else:
                x0, y0, x1, y1 = _chord(inside, w, h, x, y, *direction)
                lane = (x0 - w / 2, y0 - h / 2, x1 - w / 2, y1 - h / 2)
                if math.hypot(lane[2] - lane[0], lane[3] - lane[1]) < 3:
                    mine.append((x - w / 2, y - h / 2, None, 1.0))
                    continue
            lanes.append(lane)
            if motion == "glare":
                home = math.hypot(x - w / 2 - lane[0], y - h / 2 - lane[1]) / (
                    math.hypot(lane[2] - lane[0], lane[3] - lane[1]) or 1.0)
                mine.append((x - w / 2, y - h / 2, (len(lanes) - 1, home, rng.gauss(0, 0.35)), 1.0))
            else:
                mine.append((lane[0], lane[1], (len(lanes) - 1, rng.random(),
                                                rng.gauss(0, 1) if motion == "fall" else rng.uniform(0, 6.3)), 1.0))
        data["lanes"] = lanes
    if motion == "turn":
        if part["shape"] == "stencil" and len(part["copies"]) == 1:
            px, py = _apply(fit, *_apply(part["copies"][0], 0.0, 0.0))
            data["centre"] = (px - w / 2, py - h / 2)
        cx, cy = data["centre"]
        dist = [math.hypot(x - cx, y - cy) for x, y, *_ in mine]
        if dist:
            prev_r = data.get("radii")
            data["radii"] = ((min(prev_r[0], min(dist)), max(prev_r[1], max(dist)))
                             if append_lanes and prev_r else (min(dist), max(dist)))
        data["spin"] = TURN_SPEED[part["speed"]] * (-1 if part["reverse"] else 1)
    if mine and len(mine) < n:
        mine += [mine[k % len(mine)] for k in range(n - len(mine))]
    return mine[:n]


def _step_swarm(whole, scene, parts, step, light, previous, fit, w, h, scale, box, budget,
                entrance, dance, part_cache, rng, started):
    """Switch a diagram step: keep ambient grains home and fly the highlight swarm to the newly lit parts."""
    poses = [None if not part.get("pose") else (
        part["pose"][0][0] * scale, part["pose"][0][1] * scale, part["pose"][1], part["pose"][2][0] * scale + 1 - w / 2,
        part["pose"][2][1] * scale + 1 - h / 2, part["pose"][3]) for part in parts]
    was_pose = {p["id"]: p.get("pose") for p in previous["parts"]}
    flying = {k for k, part in enumerate(parts) if was_pose.get(part["id"]) != poses[k]}
    prev_x, prev_y = previous["x"], previous["y"]
    prev_part = previous["part"]
    tx, ty = list(prev_x), list(prev_y)
    moves, part_of, owner = list(previous["move"]), list(prev_part), list(previous["owner"])
    bright_base = list(previous.get("bright_base") or [1.0] * budget)
    grain_u = list(previous.get("grain_u") or [0.5] * budget)
    swarm = list(previous["swarm"])
    raw = list(previous.get("raw") or [1.0] * len(parts))
    mat = previous["material"]
    prev_overrides = previous.get("material_overrides") or {}
    overrides = {}
    info = []
    dms = {}
    rerouted_arrows = set()

    for pi, part in enumerate(parts):
        old_data = previous["parts"][pi]
        data = {k: v for k, v in old_data.items() if k not in ("pose", "flight", "engine")}
        if "lanes" in old_data:
            data["lanes"] = list(old_data["lanes"])
        if poses[pi]:
            data["pose"] = poses[pi]
        if pi in flying:
            data["flight"] = (was_pose.get(part["id"]), poses[pi])
        data["lit"] = light is not None and _lit(part, light)
        data["was_lit"] = 1.0 if old_data.get("lit", False) else 0.0
        info.append(data)

        if pi in flying:
            # Rigidly move ambient grains with their part; kept swarm grains move with it below.
            dm = dms[pi] = _then(_invert(_pose_matrix(was_pose.get(part["id"]))), _pose_matrix(poses[pi]))
            for i in range(budget):
                if not swarm[i] and prev_part[i] == pi:
                    tx[i], ty[i] = _apply(dm, tx[i], ty[i])
            geom = _part_geom(part, fit, w, h, part_cache)
            if geom["box"] is not None:
                data["box"], data["centre"] = geom["box"], geom["centre"]
            if part["motion"] == "flow":
                if "paths" not in geom:
                    geom["paths"] = _flow_paths(part, fit)
                data["paths"] = geom["paths"]
            elif part["motion"] == "turn" and part["shape"] == "stencil" and len(part["copies"]) == 1:
                px, py = _apply(fit, *_apply(part["copies"][0], 0.0, 0.0))
                data["centre"] = (px - w / 2, py - h / 2)

        if part["shape"] == "arrow":
            base_p = whole["parts"][pi]
            prev_p = previous["drawn"][pi]
            if part["args"] != base_p["args"]:
                if part["args"] == prev_p["args"] and pi in prev_overrides:
                    overrides[pi] = prev_overrides[pi]
                else:
                    overrides[pi] = _bake_part(part, fit, w, h, mat["bake_scale"])
            if part["args"] != prev_p["args"]:
                rerouted_arrows.add(pi)
                geom = _part_geom(part, fit, w, h, part_cache)
                if geom["box"] is not None:
                    data["box"], data["centre"] = geom["box"], geom["centre"]
                amb_idxs = [i for i in range(budget) if not swarm[i] and prev_part[i] == pi]
                if amb_idxs:
                    mine = _sample_part_grains(part, geom, data, len(amb_idxs), fit, w, h, scale, rng)
                    stress_mul = STRESS.get(part["stress"], (1.0, 1.0))[1]
                    for idx_i, (gx, gy, mv, hmul) in zip(amb_idxs, mine):
                        tx[idx_i], ty[idx_i], moves[idx_i] = gx, gy, mv
                        bright_base[idx_i] = stress_mul * hmul

    # Partition highlight swarm grains: parts that stay lit keep theirs, departing parts release theirs.
    swarm_indices = [i for i in range(budget) if swarm[i]]
    lit_ids = [pi for pi in range(len(parts)) if info[pi]["lit"]]
    want_swarm = _swarm_shares(raw, len(swarm_indices), lit_ids)
    have_by_part = [[] for _ in parts]
    for i in swarm_indices:
        have_by_part[prev_part[i]].append(i)

    lit_deficit_centers = [info[pi].get("centre", (0.0, 0.0)) for pi in range(len(parts))
                           if info[pi]["lit"] and want_swarm[pi] > len(have_by_part[pi])]
    all_deficit_centers = [info[pi].get("centre", (0.0, 0.0)) for pi in range(len(parts))
                           if want_swarm[pi] > len(have_by_part[pi])]
    pick_centers = lit_deficit_centers or all_deficit_centers
    free_lit, free_quiet = [], []
    deficit = [0] * len(parts)
    for pi in range(len(parts)):
        have = have_by_part[pi]
        want = want_swarm[pi]
        k_keep = min(len(have), want)
        donor = free_lit if previous["parts"][pi].get("lit") else free_quiet
        if k_keep == 0:
            donor.extend(have)
            kept = []
        elif k_keep < len(have):
            if pick_centers:
                # Release grains closest to the newly lit parts so flights stay short.
                ranked = sorted(have, key=lambda i: min(
                    (prev_x[i] - cx) ** 2 + (prev_y[i] - cy) ** 2 for cx, cy in pick_centers))
                donor.extend(ranked[:len(have) - k_keep])
                kept = ranked[len(have) - k_keep:]
            else:
                donor.extend(have[k_keep:])
                kept = have[:k_keep]
        else:
            kept = have
        if kept:
            if pi in dms:
                dm = dms[pi]
                for i in kept:
                    tx[i], ty[i] = _apply(dm, tx[i], ty[i])
            if pi in rerouted_arrows:
                geom = _part_geom(parts[pi], fit, w, h, part_cache)
                mine = _sample_part_grains(parts[pi], geom, info[pi], len(kept), fit, w, h, scale, rng, append_lanes=True)
                stress_mul = STRESS.get(parts[pi]["stress"], (1.0, 1.0))[1]
                for idx_i, (gx, gy, mv, hmul) in zip(kept, mine):
                    tx[idx_i], ty[idx_i], moves[idx_i] = gx, gy, mv
                    bright_base[idx_i] = stress_mul * hmul
        deficit[pi] = want - k_keep

    # Sample destination slots on deficit parts, split into newly lit parts and quiet overflow.
    transit = set()
    dest_lit, dest_quiet = [], []
    for pi, need in enumerate(deficit):
        if need <= 0:
            continue
        geom = _part_geom(parts[pi], fit, w, h, part_cache)
        slots = _sample_part_grains(parts[pi], geom, info[pi], need, fit, w, h, scale, rng, append_lanes=True)
        if not slots:
            cx, cy = info[pi].get("centre", (0.0, 0.0))
            slots = [(cx, cy, None, 1.0)] * need
        cx, cy = info[pi].get("centre", (sum(s[0] for s in slots) / len(slots), sum(s[1] for s in slots) / len(slots)))
        stress_mul = STRESS.get(parts[pi]["stress"], (1.0, 1.0))[1]
        (dest_lit if info[pi]["lit"] else dest_quiet).append((pi, slots, stress_mul, cx, cy))

    def _assign_group(pool, targets):
        if not pool or not targets:
            return
        assigned = [[] for _ in targets]
        if len(targets) == 1:
            assigned[0] = list(pool)
        else:
            cap = [len(dp[1]) for dp in targets]
            ranked = []
            for i in pool:
                gx, gy = prev_x[i], prev_y[i]
                dists = sorted((((gx - cx) ** 2 + (gy - cy) ** 2), p_idx)
                               for p_idx, (_, _, _, cx, cy) in enumerate(targets))
                ranked.append((dists[1][0] - dists[0][0], i, dists))
            ranked.sort(key=lambda item: -item[0])
            for _, i, dists in ranked:
                for _, p_idx in dists:
                    if cap[p_idx] > 0:
                        assigned[p_idx].append(i)
                        cap[p_idx] -= 1
                        break
        for p_idx, (pi, slots, stress_mul, cx, cy) in enumerate(targets):
            g_list = assigned[p_idx]
            if not g_list:
                continue
            sx = sum(prev_x[i] for i in g_list) / len(g_list)
            sy = sum(prev_y[i] for i in g_list) / len(g_list)
            vx, vy = cx - sx, cy - sy
            px_a, py_a = (-vy, vx) if vx * vx + vy * vy > 1e-6 else (1.0, 0.0)
            g_list.sort(key=lambda i: prev_x[i] * px_a + prev_y[i] * py_a)
            slots.sort(key=lambda s: s[0] * px_a + s[1] * py_a)
            pid = parts[pi]["id"]
            for i, (gx, gy, mv, hmul) in zip(g_list, slots):
                tx[i], ty[i], moves[i] = gx, gy, mv
                part_of[i], owner[i] = pi, pid
                bright_base[i] = stress_mul * hmul
                transit.add(i)

    # Feed newly lit parts from previously lit donors first, then nearest quiet overflow if still needed.
    need_lit = sum(len(dp[1]) for dp in dest_lit)
    lit_centers = [(cx, cy) for _, _, _, cx, cy in dest_lit]
    if need_lit <= len(free_lit):
        if need_lit and len(free_lit) > need_lit:
            free_lit.sort(key=lambda i: min((prev_x[i] - cx) ** 2 + (prev_y[i] - cy) ** 2 for cx, cy in lit_centers))
        for_lit = free_lit[:need_lit]
        for_quiet = free_lit[need_lit:] + free_quiet
    else:
        extra = need_lit - len(free_lit)
        if extra and len(free_quiet) > extra:
            free_quiet.sort(key=lambda i: min((prev_x[i] - cx) ** 2 + (prev_y[i] - cy) ** 2 for cx, cy in lit_centers))
        for_lit = free_lit + free_quiet[:extra]
        for_quiet = free_quiet[extra:]
    _assign_group(for_lit, dest_lit)
    _assign_group(for_quiet, dest_quiet)

    # Recompute engine crank-rod-piston kinematics when an engine compound is present.
    def px(ps, k, at):
        x, y = _apply(fit, *_apply(ps[k]["copies"][0], *at))
        return x - w / 2, y - h / 2

    for g in {p["group"] for p in parts if p["group"]}:
        roles = {p["args"]: k for k, p in enumerate(parts) if p["group"] == g and p["shape"] == "stencil"
                 and p["args"] in ("crank", "rod", "piston") and len(p["copies"]) == 1}
        if len(roles) == 3:
            crank, rod, piston = roles["crank"], roles["rod"], roles["piston"]
            journal, pin = px(parts, crank, (0, 0)), px(parts, crank, stencils.PINS["crank"])
            top, end = px(parts, rod, (0, 0)), px(parts, rod, stencils.PINS["rod"])
            a0, a1 = px(whole["parts"], crank, (0, 0)), px(whole["parts"], piston, (0, 0))
            span = math.dist(a0, a1) or 1.0
            info[crank]["engine"] = (piston, rod, journal, pin, top, end, ((a1[0] - a0[0]) / span,
                                                                         (a1[1] - a0[1]) / span), math.dist(top, end))

    part_glow = [LIFE_GLOW[d["lit"]] for d in info]
    bright = [part_glow[part_of[i]] * bright_base[i] for i in range(budget)]
    grains = {p["id"]: 0 for p in parts}
    for pi in part_of:
        grains[parts[pi]["id"]] += 1
    labels = _labels(scene, info, [], box)
    form = {"name": scene["name"], "title": scene["title"], "kind": scene["size"], "budget": budget, "box": box,
            "size": (w, h), "scene": whole, "drawn": parts, "_part_cache": part_cache, "entrance": entrance,
            "dance": dance, "step": step, "caption": scene["steps"][step]["caption"] if step is not None else "",
            "x": tx, "y": ty, "part": part_of, "move": moves, "bright": bright, "bright_base": bright_base,
            "owner": owner, "swarm": swarm, "raw": raw, "transit": transit, "step_switch": True,
            "parts": info, "labels": labels, "grains": grains, "notes": [],
            "material": mat, "fit": fit, "grain_u": grain_u}
    if overrides:
        form["material_overrides"] = overrides
    form["ms"] = round((time.perf_counter() - started) * 1000, 1)
    return form


def _dense(scene):
    return MATERIAL and scene["size"] == "diagram"


def _part_extents(part, fit, w, h):
    """Return the padded bounding box (x0, y0, bw, bh) and raw span in form pixels centered at (0, 0)."""
    surf = cairo.ImageSurface(cairo.FORMAT_A8, 1, 1)
    cr = cairo.Context(surf)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    xs, ys = [], []
    for m in part["copies"]:
        cr.new_path()
        cr.set_matrix(cairo.Matrix(*fit))
        cr.transform(cairo.Matrix(*m))
        if part["shape"] == "stencil":
            for ink, ops in _stencil(part["args"])[0]:
                cr.new_path()
                _trace_ops(cr, ops)
                cr.save()
                cr.identity_matrix()
                b = cr.fill_extents() if ink == "fill" else cr.stroke_extents()
                cr.restore()
                if b[2] > b[0] or b[3] > b[1]:
                    xs += [b[0], b[2]]
                    ys += [b[1], b[3]]
        else:
            _trace(cr, part)
            cr.save()
            cr.identity_matrix()
            cr.set_line_width(max(4.0, part["width"] * fit[0]))
            b = cr.fill_extents() if part["fill"] else cr.stroke_extents()
            cr.restore()
            if b[2] > b[0] or b[3] > b[1]:
                xs += [b[0], b[2]]
                ys += [b[1], b[3]]
            if part["shape"] == "arrow":
                tip, (dx, dy), size = _head(part)
                bx, by, nx, ny = tip[0] - dx * size, tip[1] - dy * size, -dy * size / 2, dx * size / 2
                for pt in (tip, (bx + nx, by + ny), (bx - nx, by - ny)):
                    px, py = _apply(fit, *_apply(m, *pt))
                    xs.append(px)
                    ys.append(py)
    if not xs:
        return (-10.0, -10.0, 20.0, 20.0), (0.0, 0.0)
    raw_w, raw_h = max(xs) - min(xs), max(ys) - min(ys)
    pad = 8.0
    x0, y0 = math.floor(min(xs) - w / 2 - pad), math.floor(min(ys) - h / 2 - pad)
    x1, y1 = math.ceil(max(xs) - w / 2 + pad), math.ceil(max(ys) - h / 2 + pad)
    return (float(x0), float(y0), float(max(8, x1 - x0)), float(max(8, y1 - y0))), (raw_w, raw_h)


def _bake_part(part, fit, w, h, bake_scale=2):
    """Bake one part into a Cairo RGB24 texture: R stroke coverage, G arrival u, B fill coverage."""
    (x0, y0, bw, bh), (raw_w, raw_h) = _part_extents(part, fit, w, h)
    tw, th = int(bw) * bake_scale, int(bh) * bake_scale
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, tw, th)
    cr = cairo.Context(surf)
    cr.set_source_rgb(0.0, 0.0, 0.0)
    cr.paint()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    off_x, off_y = -(x0 + w / 2), -(y0 + h / 2)

    # Taper stroke width and cell size on small stencils so 30 px icons keep crisp gaps.
    cell_scale = 1.0
    if part["shape"] == "stencil":
        max_dim = max(raw_w, raw_h)
        if max_dim < 48.0:
            taper = max(0.58, max_dim / 48.0)
            core_w = 2.15 * taper
            cell_scale = max(0.70, 0.55 + 0.45 * taper)
        else:
            core_w = 2.15
    else:
        raw_px = part["width"] * fit[0] * math.sqrt(abs(
            part["copies"][0][0] * part["copies"][0][3] - part["copies"][0][1] * part["copies"][0][2]))
        # Floor plain strokes at 1.65 px so thin lines never bead into gaps.
        core_w = max(1.65, min(3.2, raw_px * 0.48))

    has_fill = part["fill"] or (part["shape"] == "stencil" and any(
        ink == "fill" for ink, _ in _stencil(part["args"])[0]))

    # Pass 1: paint arrival u in Green with ANTIALIAS_NONE so coverage pixels never bleed to zero.
    cr.save()
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    if has_fill:
        grad = cairo.LinearGradient(0, 0, tw * 0.25, th)
        grad.add_color_stop_rgb(0.0, 0.0, 0.10, 0.0)
        grad.add_color_stop_rgb(1.0, 0.0, 0.90, 0.0)
        for m in part["copies"]:
            cr.save()
            cr.scale(bake_scale, bake_scale)
            cr.translate(off_x, off_y)
            cr.transform(cairo.Matrix(*fit))
            cr.transform(cairo.Matrix(*m))
            if part["shape"] == "stencil":
                for ink, ops in _stencil(part["args"])[0]:
                    if ink == "fill":
                        cr.new_path()
                        _trace_ops(cr, ops)
                        cr.save()
                        cr.identity_matrix()
                        cr.set_source(grad)
                        cr.fill()
                        cr.restore()
            elif part["fill"]:
                cr.new_path()
                _trace(cr, part)
                cr.save()
                cr.identity_matrix()
                cr.set_source(grad)
                cr.fill()
                cr.restore()
            cr.restore()

    paths = _flow_paths(part, fit)
    if part["shape"] == "arrow":
        tip, (dx, dy), size = _head(part)
        bx, by, nx, ny = tip[0] - dx * size, tip[1] - dy * size, -dy * size / 2, dx * size / 2
        for m in part["copies"]:
            tp, lp, rp = (_apply(fit, *_apply(m, x, y)) for x, y in (
                tip, (bx + nx, by + ny), (bx - nx, by - ny)))
            paths.append(_even([lp, tp, rp, lp], True))

    total_len = sum(p["length"] for p in paths) or 1.0
    # Build segments in forward order, then paint in reverse so earlier arrival wins at crossings.
    chunks = []
    acc_len = 0.0
    for path in paths:
        pts, plen = path["points"], path["length"]
        n = len(pts) - 1
        if n < 1:
            continue
        step = max(1, n // 28)
        for idx in range(0, n, step):
            end_idx = min(n, idx + step)
            u_mid = 0.02 + 0.96 * ((acc_len + plen * (idx + end_idx) * 0.5 / n) / total_len)
            chunks.append((u_mid, pts[idx:end_idx + 1]))
        acc_len += plen
    chunks.reverse()
    for ribbon_w in (max(5.0, core_w * 3.8) * bake_scale, max(2.8, core_w * 1.9) * bake_scale):
        cr.set_line_width(ribbon_w)
        for u_mid, seg in chunks:
            cr.set_source_rgb(0.0, u_mid, 0.0)
            cr.new_path()
            cr.move_to((seg[0][0] + off_x) * bake_scale, (seg[0][1] + off_y) * bake_scale)
            for px, py in seg[1:]:
                cr.line_to((px + off_x) * bake_scale, (py + off_y) * bake_scale)
            cr.stroke()
    cr.restore()

    # Pass 2: paint bell-profile stroke coverage into Red using OPERATOR_LIGHTEN.
    cr.save()
    cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
    cr.set_operator(cairo.OPERATOR_LIGHTEN)

    def stroke_bell(base_w, thin=False):
        scale_w = 0.88 if thin else 1.0
        peak = 0.96 if thin else 1.0
        for lw, val in ((base_w * 1.95 * scale_w, 0.28 * peak),
                        (base_w * 1.35 * scale_w, 0.66 * peak),
                        (base_w * 0.92 * scale_w, 1.00 * peak)):
            cr.set_line_width(max(1.0, lw) * bake_scale)
            cr.set_source_rgb(val, 0.0, 0.0)
            cr.stroke_preserve()
        cr.new_path()

    for m in part["copies"]:
        cr.save()
        cr.scale(bake_scale, bake_scale)
        cr.translate(off_x, off_y)
        cr.transform(cairo.Matrix(*fit))
        cr.transform(cairo.Matrix(*m))
        if part["shape"] == "stencil":
            for ink, ops in _stencil(part["args"])[0]:
                cr.new_path()
                _trace_ops(cr, ops)
                cr.save()
                cr.identity_matrix()
                stroke_bell(core_w * (0.88 if ink == "fill" else 1.0), thin=(ink == "thin"))
                cr.restore()
        else:
            cr.new_path()
            _trace(cr, part)
            cr.save()
            cr.identity_matrix()
            stroke_bell(core_w, thin=False)
            cr.restore()
            if part["shape"] == "arrow":
                tip, (dx, dy), size = _head(part)
                bx, by, nx, ny = tip[0] - dx * size, tip[1] - dy * size, -dy * size / 2, dx * size / 2
                cr.new_path()
                cr.move_to(*tip)
                cr.line_to(bx + nx, by + ny)
                cr.line_to(bx - nx, by - ny)
                cr.close_path()
                cr.save()
                cr.identity_matrix()
                stroke_bell(core_w, thin=False)
                cr.restore()
        cr.restore()
    cr.restore()

    # Pass 3: paint fill coverage into Blue using OPERATOR_LIGHTEN.
    if has_fill or part["shape"] == "arrow":
        cr.save()
        cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
        cr.set_operator(cairo.OPERATOR_LIGHTEN)
        for m in part["copies"]:
            cr.save()
            cr.scale(bake_scale, bake_scale)
            cr.translate(off_x, off_y)
            cr.transform(cairo.Matrix(*fit))
            cr.transform(cairo.Matrix(*m))
            if part["shape"] == "stencil":
                for ink, ops in _stencil(part["args"])[0]:
                    if ink == "fill":
                        cr.new_path()
                        _trace_ops(cr, ops)
                        cr.save()
                        cr.identity_matrix()
                        cr.set_source_rgb(0.0, 0.0, 1.0)
                        cr.fill()
                        cr.restore()
            elif part["fill"]:
                cr.new_path()
                _trace(cr, part)
                cr.save()
                cr.identity_matrix()
                cr.set_source_rgb(0.0, 0.0, 1.0)
                cr.fill()
                cr.restore()
            elif part["shape"] == "arrow":
                tip, (dx, dy), size = _head(part)
                bx, by, nx, ny = tip[0] - dx * size, tip[1] - dy * size, -dy * size / 2, dx * size / 2
                cr.new_path()
                cr.move_to(*tip)
                cr.line_to(bx + nx, by + ny)
                cr.line_to(bx - nx, by - ny)
                cr.close_path()
                cr.save()
                cr.identity_matrix()
                cr.set_source_rgb(0.0, 0.0, 1.0)
                cr.fill()
                cr.restore()
            cr.restore()
        cr.restore()

    surf.flush()
    # Keep polylines in form-centered coordinates for living grains riding the draw-on front.
    centered = [{"points": [(px - w / 2, py - h / 2) for px, py in p["points"]], "length": p["length"]}
                for p in paths]
    return {"id": part["id"], "box": (x0, y0, bw, bh), "tex_w": tw, "tex_h": th,
            "bake_scale": bake_scale, "cell_scale": cell_scale, "surface": surf,
            "paths": centered, "total_len": total_len}


def bake_material(scene, fit, w, h, bake_scale=2):
    """Bake every part of a validated scene once for the material shader and Cairo fallback."""
    return {"parts": [_bake_part(p, fit, w, h, bake_scale) for p in scene["parts"]],
            "bake_scale": bake_scale, "size": (w, h)}


def _grain_arrivals(form, mat):
    """Sample each living grain's arrival u from its part's baked green channel or nearest stroke point."""
    parts = mat["parts"]
    scale = mat["bake_scale"]
    # Hoist per-part inverse pose and surface buffer outside the grain loop.
    part_info = []
    for pi, b in enumerate(parts):
        pose = form["parts"][pi].get("pose")
        inv = _invert(_pose_matrix(pose)) if pose else None
        surf = b["surface"]
        part_info.append((inv, b["box"][0], b["box"][1], b["tex_w"] - 1, b["tex_h"] - 1,
                          surf.get_data(), surf.get_stride(), b["paths"], b["total_len"] or 1.0))
    out = []
    for x, y, pi in zip(form["x"], form["y"], form["part"]):
        inv, x0, y0, max_tx, max_ty, data, stride, paths, total = part_info[pi]
        if inv is not None:
            lx = inv[0] * x + inv[2] * y + inv[4]
            ly = inv[1] * x + inv[3] * y + inv[5]
        else:
            lx, ly = x, y
        tx = min(max_tx, max(0, int((lx - x0) * scale)))
        ty = min(max_ty, max(0, int((ly - y0) * scale)))
        u = data[ty * stride + tx * 4 + 1] / 255.0
        if u <= 0.01 and paths:
            # Find nearest polyline sample when a jittered living grain sits outside the arrival ribbon.
            best_d, best_u, acc = math.inf, 0.5, 0.0
            for path in paths:
                pts, plen = path["points"], path["length"]
                n = max(1, len(pts) - 1)
                for idx, (px, py) in enumerate(pts):
                    d = (px - lx) ** 2 + (py - ly) ** 2
                    if d < best_d:
                        best_d = d
                        best_u = 0.02 + 0.96 * ((acc + plen * idx / n) / total)
                acc += plen
            u = best_u
        out.append(u if u > 0.01 else 0.5)
    return out


def _part_point_at(baked_part, u):
    """Return a point (x, y) at fraction u along a baked part's polylines."""
    paths = baked_part["paths"]
    if not paths:
        x0, y0, bw, bh = baked_part["box"]
        return x0 + bw * 0.5, y0 + bh * 0.5
    at = min(1.0, max(0.0, u)) * baked_part["total_len"]
    for path in paths:
        if at <= path["length"] or path is paths[-1]:
            x, y, _, _ = _along(path["points"], at / (path["length"] or 1.0))
            return x, y
        at -= path["length"]
    return paths[-1]["points"][-1]


def material_state(form, d):
    """Per-part transforms, lighting, reveal progress and entrance fade at d seconds."""
    parts = form["parts"]
    fly = flights(form, d)
    mats = []
    for k, part in enumerate(parts):
        m = _pose_matrix(part.get("pose"))
        if k in fly:
            m = _then(m, fly[k])
        if part["motion"] == "turn" and "centre" in part:
            m = _then(m, _matrix(1.0, math.degrees(part["spin"] * d), (0.0, 0.0), part["centre"]))
        mats.append(m)
    elapsed = d - form.get("start", 0.0)
    lits, glows = [], []
    for part in parts:
        lit_now = 1.0 if part.get("lit", False) else 0.0
        was_lit = float(part.get("was_lit", 0.0))
        if lit_now > was_lit:
            # Ease from the saved lit level as the highlight swarm arrives.
            lit_v = was_lit + (lit_now - was_lit) * _ease(elapsed, SWARM_LIGHT_START, SWARM_LIGHT_END)
        elif lit_now < was_lit:
            # Ease down from the saved lit level as the highlight swarm departs.
            lit_v = was_lit + (lit_now - was_lit) * _ease(elapsed, SWARM_DIM_START, SWARM_DIM_END)
        else:
            lit_v = lit_now
        lits.append(lit_v)
        glows.append(MAT_GLOW[False] + (MAT_GLOW[True] - MAT_GLOW[False]) * lit_v)
    if form.get("entrance", DIAGRAM_ENTRANCE) == "draw":
        reach = max(0.0, (d - DRAW_START) / DRAW_SECONDS)
        fade = 1.0 if d >= DRAW_START else 0.0
    else:
        reach = 2.0
        # Delay material fade-in during fly-in so nothing shows before living grains arrive.
        fade = _ease(d, 0.35, 0.95)
    return mats, glows, lits, reach, fade


def _mess_notes(parts, masks, sets, info, fit, w, scale, notes):
    """Notes for what makes a drawing messy: a line or an arrow that crosses a part or another line, an arrow that runs
    into the part it starts or ends on, and shapes that overlap without one sitting inside the other."""
    lines = [i for i, p in enumerate(parts) if p["shape"] in ("line", "arrow") and masks[i]]
    ends = {}
    for i in lines:
        a, px = parts[i]["args"], parts[i]["width"] * scale
        pts = [_apply(fit, *_apply(m, *xy)) for m in parts[i]["copies"] for xy in (a[:2], a[2:])]
        ends[i] = (pts, 3 * px + 6)
    for i in lines:  # An arrow too short for a full head shows a stub of a head.
        part = parts[i]
        length, full = math.dist(part["args"][:2], part["args"][2:]), HEAD_MIN * part["width"] / 0.6
        if part["shape"] == "arrow" and length < full:
            ends_of = f"'{part['link'][0]}' and '{part['link'][1]}'" if part.get("link") else "its ends"
            notes.append(f"'{part['id']}' is too short for a clear arrowhead. Move {ends_of} about "
                         f"{max(1, math.ceil(full - length))} units further apart.")
    near = lambda i, k: any((k % w - x) ** 2 + (k // w - y) ** 2 < ends[i][1] ** 2 for x, y in ends[i][0])  # noqa: E731
    said = set()
    for i in lines:
        name, link = parts[i]["id"], parts[i].get("link")
        fix = (f"Give it \"curve\": \"over\" or \"under\", or move the part out of its way." if link else
               "Draw it as \"link\": [\"from\", \"to\"], which routes round parts, or give it \"curve\".")
        for j, cover in enumerate(sets):
            if j == i or not masks[j] or (i, j) in said:
                continue
            shared = sets[i] & cover
            if len(shared) < 6:
                continue
            other = parts[j]["id"]
            if j in lines:
                said.add((j, i))
                if sum(1 for k in shared if not near(i, k) and not near(j, k)) > 6:
                    notes.append(f"'{name}' and '{other}' cross. Bow one of them with \"curve\", or move a part.")
            elif sum(1 for k in shared if not near(i, k)) > 6:
                notes.append(f"'{name}' crosses '{other}'. {fix}")
            elif not (link and other in link):
                notes.append(f"'{name}' runs into '{other}' at its end, so the two merge. Start and end it a few "
                             "units outside the shape, or draw it as a link, which leaves the gap itself.")
    shapes = [i for i, p in enumerate(parts) if p["shape"] not in ("line", "arrow", "arc") and masks[i]]
    for n, i in enumerate(shapes):
        for j in shapes[n + 1:]:
            a, b = info[i]["box"], info[j]["box"]
            nested = (a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]) or (
                b[0] >= a[0] and b[1] >= a[1] and b[2] <= a[2] and b[3] <= a[3])
            together = parts[i]["group"] and parts[i]["group"] == parts[j]["group"]  # A group's parts fit on purpose.
            if not nested and not together and len(sets[i] & sets[j]) > 8:
                notes.append(f"'{parts[i]['id']}' and '{parts[j]['id']}' overlap. Move them apart, or put one wholly "
                             "inside the other.")


def _labels(scene, info, notes, box):
    """Each label's text and anchor in form pixels: (text, x, y, align), align -1 right, 0 centre, 1 left."""
    out = []
    for part, data in zip(scene["parts"], info):
        if not part["label"] or "box" not in data:
            continue
        x0, y0, x1, y1 = data["box"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        x, y, align = {"below": (cx, y1 + 10, 0), "above": (cx, y0 - 10, 0), "left": (x0 - 7, cy, -1),
                       "right": (x1 + 7, cy, 1), "inside": (cx, cy, 0)}[part["label_at"]]
        width = LABEL_TYPE[scene["size"]][2] * len(part["label"])  # The overlay's label font, in heavy capitals.
        left = x - width / 2 if align == 0 else x - width if align < 0 else x
        out.append({"id": part["id"], "text": part["label"], "x": x, "y": y, "align": align,
                    "span": (left, y - 7, left + width, y + 7)})
    for k, a in enumerate(out):
        l, t, r, b = a["span"]
        if l < -CANVAS / 2 or r > CANVAS / 2:
            notes.append(f"The label of '{a['id']}' runs {max(-CANVAS / 2 - l, r - CANVAS / 2):.0f} px past the "
                         "overlay's edge. Shorten it, or move it with label_at.")
        for c in out[k + 1:]:
            l2, t2, r2, b2 = c["span"]
            if l < r2 and l2 < r and t < b2 and t2 < b:
                notes.append(f"The labels of '{a['id']}' and '{c['id']}' overlap. Shorten one, or move it with "
                             "label_at; a diagram with labels needs a larger box (see the budget notes).")
    return out


def _assign(homes, info, previous, budget):
    """The order of homes by grain: homes[order[i]] is grain i's. See the morph contract at the top."""
    atan2 = math.atan2
    if previous is None or previous["budget"] != budget or len(homes) != budget or len(previous["x"]) != budget:
        return sorted(range(len(homes)), key=lambda k: atan2(homes[k][1], homes[k][0]))
    px, py = previous["x"], previous["y"]
    by_part = {}
    for k, home in enumerate(homes):
        by_part.setdefault(info[home[2]]["id"], []).append(k)
    held = {}
    for g, pid in enumerate(previous["owner"]):
        held.setdefault(pid, []).append(g)
    order, pool, need = [None] * budget, [], {}
    for pid, grains in held.items():
        want = len(by_part.get(pid, []))
        if want >= len(grains):
            need[pid] = grains
            continue
        # Shrinking: keep an even spread of the old grains, in their order round the old part.
        cx, cy = previous["parts"][previous["part"][grains[0]]].get("centre", (0.0, 0.0))
        grains = sorted(grains, key=lambda g: atan2(py[g] - cy, px[g] - cx))
        keep = {round(i * len(grains) / want) for i in range(want)} if want else set()
        need[pid] = [g for i, g in enumerate(grains) if i in keep]
        pool += [g for i, g in enumerate(grains) if i not in keep]
    for pid in sorted(by_part, key=lambda p: len(by_part[p]) - len(need.get(p, [])), reverse=True):
        mine = need.setdefault(pid, [])
        short = len(by_part[pid]) - len(mine)
        if short > 0:
            cx, cy = info[homes[by_part[pid][0]][2]]["centre"]
            pool.sort(key=lambda g: (px[g] - cx) ** 2 + (py[g] - cy) ** 2)
            mine += pool[:short]
            del pool[:short]
    for pid, ks in by_part.items():
        data = info[homes[ks[0]][2]]
        cx, cy = data["centre"]
        if "flight" in data:
            # A moved part's grains keep their places within it: both poses are undone before they are matched.
            old, new = (_invert(_pose_matrix(pose)) for pose in data["flight"])
            nx0, ny0, nx1, ny1, ntx, nty = new
            ox0, oy0, ox1, oy1, otx, oty = old
            ccx, ccy = nx0 * cx + nx1 * cy + ntx, ny0 * cx + ny1 * cy + nty
            places = sorted(ks, key=lambda k: atan2(
                ny0 * homes[k][0] + ny1 * homes[k][1] + nty - ccy,
                nx0 * homes[k][0] + nx1 * homes[k][1] + ntx - ccx))
            grains = sorted(need[pid], key=lambda g: atan2(
                oy0 * px[g] + oy1 * py[g] + oty - ccy,
                ox0 * px[g] + ox1 * py[g] + otx - ccx))
        else:
            places = sorted(ks, key=lambda k: atan2(homes[k][1] - cy, homes[k][0] - cx))
            grains = sorted(need[pid], key=lambda g: atan2(py[g] - cy, px[g] - cx))
        for g, k in zip(grains, places):
            order[g] = k
    return order


def _outlined(scene, part):
    """True when OUTLINE_LOOK draws a line under this part (see OUTLINES)."""
    return (bool(OUTLINE_LOOK) and not _dense(scene) and scene["size"] == "diagram"
            and part["shape"] != "arrow" and part["motion"] != "turn")


def draw_outline(cr, form, cx, cy, colour, alpha=1.0, d=None):
    """The OUTLINE_LOOK line under each outlined part's dust, from the same geometry as its grains, round the form's
    centre (cx, cy). It dims with its part in a step, as the dust does. d, the time since the scene began, flies the
    line of a moved part with its dust (see flights)."""
    scene, w, h = form["scene"], *form["size"]
    if not OUTLINE_LOOK or scene["size"] != "diagram":
        return
    width, strength, _ = OUTLINES[OUTLINE_LOOK]
    fit = cairo.Matrix(*_fit(scene["view"], form["box"])[3])
    fly = flights(form, d) if d is not None else {}
    light = scene["steps"][form["step"]]["light"] if form["step"] is not None else None
    cr.save()
    cr.set_line_width(width)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for k, part in enumerate(form["drawn"]):
        if not _outlined(scene, part):
            continue
        cr.new_path()
        for m in part["copies"]:
            cr.save()
            cr.translate(cx, cy)
            if k in fly:
                cr.transform(cairo.Matrix(*fly[k]))
            cr.translate(-w / 2, -h / 2)
            cr.transform(fit)
            cr.transform(cairo.Matrix(*m))
            _trace(cr, part)
            cr.restore()  # The path keeps its place; the line's width is in pixels.
        dim = (1.0 if light is None or _lit(part, light) else 0.4) * STRESS.get(part["stress"], (1, 1))[1]
        cr.set_source_rgba(*colour, alpha * strength * min(1.0, dim))
        cr.stroke()
    cr.restore()


def _pose_matrix(pose):
    """A part's pose in form pixels as a matrix; None is the pose it was drawn in."""
    if pose is None:
        return _matrix()
    dx, dy, rotate, ax, ay, k = pose
    return _matrix(k, rotate, (dx, dy), (ax, ay))


def _invert(m):
    xx, yx, xy, yy, x0, y0 = m
    det = xx * yy - xy * yx
    return (yy / det, -yx / det, -xy / det, xx / det, (xy * y0 - yy * x0) / det, (yx * x0 - xx * y0) / det)


def flights(form, d):
    """Each moved part's matrix d seconds after the form began, while it flies from its last pose to the form's:
    {part index: matrix from its place in the form to its place now}. Empty once every part has landed."""
    u = (d - form.get("start", 0.0)) / FLIGHT
    if u >= 1 or not any("flight" in part for part in form["parts"]):
        return {}
    e = _ease(u, 0.0, 1.0)
    out = {}
    for pi, part in enumerate(form["parts"]):
        if "flight" in part:
            a, b = part["flight"]
            a = a or (0.0, 0.0, 0.0, *b[3:5], 1.0)
            b = b or (0.0, 0.0, 0.0, *a[3:5], 1.0)
            turn = 180 - (a[2] - b[2] + 180) % 360  # The short way; a half turn goes clockwise.
            now = tuple(p + (q - p) * e for p, q in zip(a, b))
            now = (*now[:2], a[2] + turn * e, *now[3:])
            out[pi] = _then(_invert(_pose_matrix(part["pose"] if "pose" in part else None)), _pose_matrix(now))
    for pi, part in enumerate(form["parts"]):
        if "engine" in part and pi in out:
            # The crank turns; the rod holds its pin, and the piston slides on its line, as in a real engine.
            piston, rod, journal, pin, top, end, (ax, ay), length = part["engine"]
            c, q1 = _apply(out[pi], *journal), _apply(out[pi], *pin)
            rx, ry = q1[0] - c[0], q1[1] - c[1]
            along = rx * ax + ry * ay + math.sqrt(max(0.0, length ** 2 - (rx * ay - ry * ax) ** 2))
            q0 = (c[0] + ax * along, c[1] + ay * along)
            if piston in out:
                out[piston] = _matrix(translate=(q0[0] - top[0], q0[1] - top[1]))
            if rod in out:
                turn = math.atan2(q1[1] - q0[1], q1[0] - q0[0]) - math.atan2(end[1] - top[1], end[0] - top[0])
                out[rod] = _matrix(1.0, math.degrees(turn), (q0[0] - top[0], q0[1] - top[1]), top)
    return out


# Motion, as the engine would run it. This is the reference for the contract at the top, and what the previews use.

def _ease(u, a, b):
    p = min(1.0, max(0.0, (u - a) / (b - a)))
    return p * p * (3 - 2 * p)


_MOVING = {}  # id(form): (form, the grains targets() moves), for the last few forms.


def _moving(form):
    """The grains whose place or brightness a part's motion changes, and the grains of parts that fly to a new pose:
    targets() leaves every other grain where the form put it, so it need not visit them each frame."""
    hit = _MOVING.get(id(form))
    if hit is None or hit[0] is not form:
        parts = form["parts"]
        moving = [i for i, (pi, move) in enumerate(zip(form["part"], form["move"]))
                  if parts[pi]["motion"] in ("turn", "glare")
                  or (move is not None and parts[pi]["motion"] in ("flow", "fall", "fizz"))]
        flying = [i for i, pi in enumerate(form["part"]) if "flight" in parts[pi]]
        if len(_MOVING) > 7:
            _MOVING.clear()
        hit = _MOVING[id(form)] = (form, moving, flying)
    return hit[1:]


def targets(form, d, lead=None):
    """Every grain's place and brightness d seconds after the form began: lists tx, ty, tb. lead, a time per grain,
    turns each turning grain that much further on, so a spring that trails its target lands on the place itself. A
    moved part flies on its mean lead, so its grains keep their places within it."""
    tx, ty, tb = list(form["x"]), list(form["y"]), list(form["bright"])
    parts = form["parts"]
    cos, sin = math.cos, math.sin
    part_of, moves = form["part"], form["move"]
    moving, flying = _moving(form)
    for i in moving:
        pi, move = part_of[i], moves[i]
        part = parts[pi]
        motion = part["motion"]
        if motion == "turn":
            cx, cy = part["centre"]
            a = part["spin"] * (d + lead[i] if lead else d)
            x, y = tx[i] - cx, ty[i] - cy
            tx[i], ty[i] = cx + x * cos(a) - y * sin(a), cy + x * sin(a) + y * cos(a)
        elif motion == "glare":
            band = part["band"]
            dx, dy = band["dir"]
            c = (d % band["period"]) / band["period"] / band["pass"]
            at = band["low"] - band["width"] * 2 + (band["high"] - band["low"] + band["width"] * 4) * c
            pull = math.exp(-(((tx[i] * dx + ty[i] * dy) - at) / band["width"]) ** 2) if c <= 1 else 0.0
            if move is not None and pull > 0.01:
                lane, home, off = move
                x0, y0, x1, y1 = part["lanes"][lane]
                length = math.hypot(x1 - x0, y1 - y0)
                start = x0 * dx + y0 * dy
                u = home + ((at + off * band["width"] - start) / length - home) * 0.85 * pull
                u = min(1.0, max(0.0, u))
                tx[i], ty[i] = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
            tb[i] *= 1 + (2.2 if move is not None else 1.2) * pull
        elif move is None:
            continue
        elif motion == "flow":
            k, phase, side, tail = move
            path = part["paths"][k]
            step = d * part["speed"] / path["length"] * (-1 if part["reverse"] else 1)
            look = 1.35 - 0.85 * tail
            if path["closed"]:
                u = (phase + step) % 1
            else:
                c, hidden = (phase + step) % 1, part.get("hidden", HIDDEN_SHARE)
                if c < hidden:
                    x, y, _, _ = _along(path["points"], 1.0 if part["reverse"] else 0.0)
                    tx[i], ty[i], tb[i] = x - form["size"][0] / 2, y - form["size"][1] / 2, 0.0
                    continue
                u = (c - hidden) / (1 - hidden)
                look *= _ease(u, 0.0, 0.1) * (1 - _ease(u, 0.86, 1.0))
                u = 1 - u if part["reverse"] else u
            x, y, nx, ny = _along(path["points"], u)
            s = side * part["spread"]
            tx[i], ty[i] = x - form["size"][0] / 2 + s * nx, y - form["size"][1] / 2 + s * ny
            tb[i] *= look
        elif motion == "fall":
            k, phase, side = move
            x0, y0, x1, y1 = part["lanes"][k]
            period = math.sqrt(2 * max(1.0, y1 - y0) / part["accel"]) / (1 - 0.25)
            c = (phase + d / period) % 1
            if c < 0.25:
                tx[i], ty[i], tb[i] = x0 + 1.5 * side, y0, 0.0
                continue
            u = (c - 0.25) / 0.75
            tx[i], ty[i] = x0 + side * (0.4 + 0.8 * u), y0 + (y1 - y0) * u * u
            tb[i] *= _ease(u, 0.0, 0.15) * (1 - _ease(u, 0.8, 1.0)) * 1.2
        elif motion == "fizz":
            k, phase, sway = move
            x0, y0, x1, y1 = part["lanes"][k]
            length = math.hypot(x1 - x0, y1 - y0) or 1.0
            period = length / part["rise"] / (1 - HIDDEN_SHARE)
            c = (phase + d / period) % 1
            if c < HIDDEN_SHARE:
                tx[i], ty[i], tb[i] = x0, y0, 0.0
                continue
            u = (c - HIDDEN_SHARE) / (1 - HIDDEN_SHARE)
            tx[i] = x0 + (x1 - x0) * u + 1.6 * sin(sway + 9 * u)
            ty[i] = y0 + (y1 - y0) * u
            tb[i] *= 1.5 * _ease(u, 0.0, 0.08) * (1 - _ease(u, 0.75, 1.0))
    ahead = sum(lead) / len(lead) if lead and flying else 0.0
    fly = flights(form, d + ahead) if flying else None
    if fly:
        # Each grain leads by its own time: the pose a moment later gives the velocity for the difference.
        later = flights(form, d + ahead + 0.02) if lead else {}
        for i in flying:
            xx, yx, xy, yy, x0, y0 = fly[part_of[i]]
            x, y = tx[i], ty[i]
            tx[i], ty[i] = xx * x + xy * y + x0, yx * x + yy * y + y0
            if part_of[i] in later:
                xx, yx, xy, yy, x0, y0 = later[part_of[i]]
                k = (lead[i] - ahead) / 0.02
                tx[i] += (xx * x + xy * y + x0 - tx[i]) * k
                ty[i] += (yx * x + yy * y + y0 - ty[i]) * k
    # Synchronize living grains with the draw-on entrance so sparks ride the front and nothing appears ahead.
    mat = form.get("material")
    if mat and form.get("entrance", DIAGRAM_ENTRANCE) == "draw" and d < DRAW_START + DRAW_SECONDS + 0.35:
        reach = (d - DRAW_START) / DRAW_SECONDS
        grain_u = form["grain_u"]
        bparts = mat["parts"]
        settle = _ease(d, DRAW_START + DRAW_SECONDS, DRAW_START + DRAW_SECONDS + 0.25)
        # Aim front-riders ahead by one spring trail so sparks sit directly on the glowing curve tip.
        lead_u = 0.11 / DRAW_SECONDS
        tip_u = max(0.0, min(1.0, reach + lead_u)) if reach > 0.0 else 0.0
        tips = [_part_point_at(b, tip_u) for b in bparts]
        for i in range(len(tx)):
            pi = part_of[i]
            if i % 6 == 0 and reach < 1.0 + 0.25 / DRAW_SECONDS:
                px, py = tips[pi]
                if reach <= 0.0:
                    tx[i], ty[i] = px, py
                    tb[i] *= _ease(d, 0.05, DRAW_START) * 0.85
                elif reach < 1.0:
                    tx[i], ty[i] = px, py
                    tb[i] *= 1.65
                else:
                    tx[i] = px + (tx[i] - px) * settle
                    ty[i] = py + (ty[i] - py) * settle
                    tb[i] *= 1.65 - 0.65 * settle
            else:
                ahead_u = reach - grain_u[i]
                if ahead_u <= 0.0:
                    tb[i] = 0.0
                else:
                    seen = _ease(ahead_u, 0.0, 0.06)
                    tip = math.exp(-((ahead_u / 0.035) ** 2))
                    tb[i] *= seen * (1.0 + 1.2 * tip)
    elif mat and form.get("step_switch"):
        # Wake or dim stationary grains from each part's saved lit level; keep transiting swarm bright.
        elapsed = d - form.get("start", 0.0)
        if 0.0 <= elapsed < SWARM_LIGHT_END:
            transit = form.get("transit") or ()
            e_on = _ease(elapsed, SWARM_LIGHT_START, SWARM_LIGHT_END)
            e_off = _ease(elapsed, SWARM_DIM_START, SWARM_DIM_END)
            scale_by_part = {}
            for pi, p in enumerate(parts):
                lit_now = 1.0 if p.get("lit", False) else 0.0
                was_lit = float(p.get("was_lit", 0.0))
                if abs(lit_now - was_lit) > 1e-6:
                    cur_v = was_lit + (lit_now - was_lit) * (e_on if lit_now > was_lit else e_off)
                    cur_g = LIFE_GLOW[False] + (LIFE_GLOW[True] - LIFE_GLOW[False]) * cur_v
                    scale_by_part[pi] = cur_g / LIFE_GLOW[bool(p.get("lit", False))]
            if scale_by_part:
                for i in range(len(tb)):
                    if i not in transit:
                        mul = scale_by_part.get(part_of[i])
                        if mul is not None:
                            tb[i] *= mul
    return tx, ty, tb


# The author's preview: a quick picture of the form as dust, in the dark theme's grain model, written to memory.

def _preview_dir():
    root = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/rook-render-{os.getuid()}"
    folder = os.path.join(root, "rook-render")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    # Old previews go: anything older than PREVIEW_AGE seconds, and all but the newest PREVIEW_KEEP.
    files = sorted((os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".png")),
                   key=os.path.getmtime, reverse=True)
    now = time.time()
    for k, path in enumerate(files):
        if k >= PREVIEW_KEEP or now - os.path.getmtime(path) > PREVIEW_AGE:
            os.remove(path)
    return folder


def preview_png(form, d=1.5, zoom=2.0, path=None):
    """Write the form as dust, d seconds into its motion, at zoom, and return the file's path."""
    tx, ty, tb = targets(form, d)
    w, h = form["size"]
    pad = 56
    width, height = int((w + 2 * pad) * zoom), int((h + 2 * pad) * zoom)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    cr.set_source_rgb(0.075, 0.075, 0.09)
    cr.paint()
    cr.translate(width / 2, height / 2)
    cr.scale(zoom, zoom)
    rng = random.Random(3)
    tones = [(0.95, 0.70, 0.28), (0.975, 0.81, 0.49), (1.0, 0.92, 0.70), (0.40, 0.76, 1.0)]
    buckets = {}
    for i in range(len(tx)):
        base = (rng.uniform(0.85, 1.0) if rng.random() < 0.04 else rng.uniform(0.5, 0.8) if rng.random() < 0.1
                else rng.uniform(0.18, 0.5))
        colour = 3 if rng.random() < 0.09 else rng.randrange(3)
        level = min(7, int(base * tb[i] * 0.9 * 7))
        if level > 0:
            buckets.setdefault((colour, level), []).append((tx[i], ty[i], 1.0 + 0.8 * base))
    cr.set_operator(cairo.OPERATOR_ADD)
    for (colour, level), grains in buckets.items():
        for x, y, s in grains:
            cr.rectangle(x - s / 2, y - s / 2, s, s)
        cr.set_source_rgba(*tones[colour], level / 7)
        cr.fill()
    cr.set_operator(cairo.OPERATOR_OVER)
    try:
        import gi
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo
    except (ImportError, ValueError):
        PangoCairo = None
    for label in form["labels"] if PangoCairo else ():
        layout = PangoCairo.create_layout(cr)
        px, spacing, _ = LABEL_TYPE[form["kind"]]
        layout.set_font_description(Pango.FontDescription.from_string(f"Noto Serif Heavy {px * 0.75}"))
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
        layout.set_attributes(attrs)
        layout.set_text(label["text"].upper(), -1)
        lw, lh = layout.get_pixel_size()
        x = label["x"] - (lw / 2 if label["align"] == 0 else lw if label["align"] < 0 else 0)
        cr.move_to(x, label["y"] - lh / 2)
        PangoCairo.layout_path(cr, layout)
        cr.set_source_rgba(0.035, 0.047, 0.10, 0.92)
        cr.set_line_width(2.8 / zoom * 2)
        cr.stroke_preserve()
        cr.set_source_rgba(0.975, 0.81, 0.49, 0.9)
        cr.fill()
    if path is None:
        key = hashlib.sha1(repr((form["name"], form["x"][:50], form["step"], form["budget"])).encode()).hexdigest()
        path = os.path.join(_preview_dir(), f"{form['name']}-{key[:10]}.png")
    surface.write_to_png(path)
    return path


def check(doc, budget=None, step=None, preview=True):
    """What the author calls: validate, sample, and look. Returns {"ok": False, "errors": [...]} or {"ok": True,
    "grains": {...}, "notes": [...], "preview": path, "ms": {...}}. budget None takes the scene's size."""
    started = time.perf_counter()
    scene, errors = validate(doc)
    lo, hi = LIMITS["budget"]
    if budget is not None and (not isinstance(budget, int) or not lo <= budget <= hi):
        errors.append(f"The budget needs a whole number of grains from {lo} to {hi}; got {_got(budget)}.")
    if step is not None and (scene is None or not isinstance(step, int) or not 0 <= step < len(scene["steps"])):
        errors.append(f"The step needs to be the number of one of the scene's steps, from 0; got {_got(step)}.")
    if errors:
        return {"ok": False, "errors": errors}
    checked = time.perf_counter()
    form = sample(scene, budget, step=step)
    out = {"ok": True, "grains": form["grains"], "notes": form["notes"],
           "ms": {"validate": round((checked - started) * 1000, 1), "sample": form["ms"]}}
    if preview:
        drawn = time.perf_counter()
        out["preview"] = preview_png(form)
        out["ms"]["preview"] = round((time.perf_counter() - drawn) * 1000, 1)
    return out


# The self-check.

EXAMPLE = {"name": "magnifier", "title": "A magnifying glass",
           "parts": [{"id": "lens", "circle": [40, 40, 22], "fill": True, "weight": 0.5, "motion": "glare"},
                     {"id": "rim", "circle": [40, 40, 22], "width": 4},
                     {"id": "handle", "line": [57, 57, 84, 84], "width": 8}],
           "steps": [{"light": ["lens"], "caption": "The lens bends the light."}]}

BAD = [  # (scene, words its first error must contain)
    ([], "JSON object"),
    ({"view": [100, 100], "parts": [{"id": "a", "circle": [20, 50, 5]}, {"id": "b", "circle": [80, 50, 5]},
                                    {"id": "g", "group": [{"id": "l", "link": ["a", "b"]}]}]},
     "a link joins two parts once"),
    ({"parts": []}, "at least one item"),
    ({"parts": [{"id": "rim", "circle": [1, 2]}]}, "part 'rim': circle needs [x, y, r]; got 2 numbers"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "motion": "spin"}]}, "motion needs one of still"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "colour": "red"}]}, "'colour' is not a key"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "rect": [1, 1, 2, 2]}]}, "give each its own part"),
    ({"parts": [{"id": "a"}]}, "needs one shape"),
    ({"parts": [{"circle": [5, 5, 2]}]}, "needs an id"),
    ({"parts": [{"id": "a", "path": "M 0 0 X 5 5"}]}, "not a command or a number"),
    ({"parts": [{"id": "a", "path": "L 5 5"}]}, "needs to start with M"),
    ({"parts": [{"id": "a", "path": "M 0 0 C 1 2 3"}]}, "too few numbers"),
    ({"parts": [{"id": "a", "path": "M 0 0 L 1 1" * 200}]}, "the most is 1200"),
    ({"parts": [{"id": "a", "line": [0, 0, 9, 9], "fill": True}]}, "no inside to fill"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "motion": "glare"}]}, "set fill to true"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "reverse": True}]}, "reverse only applies"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "speed": "fast"}]}, "speed does nothing"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "repeat": {"count": 4}}]}, "repeat needs about"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "repeat": {"count": 99, "step": [1, 0]}}]}, "from 2 to 36"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}, {"id": "a", "circle": [9, 9, 2]}]}, "used twice"),
    ({"parts": [{"id": "g", "group": [{"id": "h", "group": []}]}]}, "one level deep"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}], "steps": [{"light": ["b"]}]}, "not a part or group"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}], "view": [100, 1]}, "at most 4 to 1"),
    ({"parts": [{"id": "a", "circle": [5, 5, 1e9]}]}, "past 10000"),
    ({"parts": [{"id": "a", "circle": [5, 5, True]}]}, "got a list of 3 items"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "label": "x" * 40}]}, "at most 24"),
    ({"parts": [{"id": f"p{k}", "circle": [5, 5, 2]} for k in range(30)]}, "the most is 24"),
    ({"parts": [{"id": "../etc", "circle": [5, 5, 2]}]}, "needs a name of letters"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}], "parts2": 1}, "'parts2' is not a key"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}], "size": "huge"}, "size needs one of icon, diagram"),
    ({"parts": [{"id": "a", "link": ["a"]}]}, "needs the ids of two different parts"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "curve": "over"}]}, "curve only applies to a link or an arrow"),
    ({"parts": [{"id": "a", "stencil": "gear"}]}, "a stencil needs at"),
    ({"parts": [{"id": "a", "stencil": "gear", "at": [5, 5], "fill": True}]}, "draws its own lines; drop fill"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "at": [5, 5]}]}, "at only places a stencil"),
    ({"parts": [{"id": "a", "stencil": "gear", "at": [5, 5], "motion": "flow"}]}, "flow runs along a line"),
    ({"parts": [{"id": "a", "stencil": "teapot", "at": [5, 5]}]}, "stencil needs one of server"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2], "lead": True, "quiet": True}]}, "lead or quiet, not both"),
    ({"parts": [{"id": "e", "stencil": "engine", "label": "x"}]}, "compound stencil takes id, at"),
    ({"parts": [{"id": "g", "group": [{"id": "e", "stencil": "engine"}]}]}, "one level deep"),
    ({"layout": "spiral", "nodes": [{"id": "a", "label": "a"}]}, "layout needs one of row"),
    ({"layout": "row", "nodes": [{"id": "a", "label": "a"}], "view": [9, 9]}, "places its own nodes"),
    ({"layout": "row", "nodes": [{"id": "a"}]}, "needs a stencil or a label"),
    ({"layout": "row", "nodes": [{"id": "a", "label": "a"}], "links": [["a"]]}, "links needs a list such as"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}], "nodes": []}, "nodes only goes with a layout"),
    ({"parts": [{"id": "e", "stencil": "engine", "at": [50, 50]}], "steps": [{"light": ["e"], "move": {"e": "idle"}}]},
     "the engine 'e' has no pose 'idle'. Give one of intake"),
    ({"view": [160, 100], "parts": [{"id": "a", "rect": [10, 40, 30, 20]}, {"id": "b", "rect": [120, 40, 30, 20]},
                                    {"id": "p", "circle": [25, 50, 4], "fill": True}, {"id": "l", "link": ["a", "p"]}],
      "steps": [{"light": ["p"], "move": {"p": {"to": [110, 0]}}}]}, "'a' and 'p' sit one on the other"),
    ({"view": [160, 100], "parts": [{"id": "a", "rect": [10, 40, 30, 20]}, {"id": "b", "rect": [120, 40, 30, 20]},
                                    {"id": "l", "link": ["a", "b"]}], "steps": [{"light": ["b"], "move": {"b": {
        "to": [-110, 0]}}}]}, "Step 1, after its moves: part 'l': 'a' and 'b' sit one on the other"),
    ({"parts": [{"id": "a", "stencil": [0]}]}, "stencil needs one of"),
    ({"parts": [{"id": "e", "stencil": "engine", "at": [50, 50], "size": {}}]}, "size needs a number"),
    ({"parts": [{"id": "e", "stencil": "engine", "at": [50, 50], "size": "hub"}]}, "size needs a number"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}], "steps": [{"light": ["a"], "move": {"b": {"to": [1, 0]}}}]},
     "move names 'b', which is not a part"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}], "steps": [{"light": ["a"], "move": {"a": [1, 0]}}]},
     "the move of 'a' needs to, rotate, about or scale"),
    ({"parts": [{"id": "a", "circle": [5, 5, 2]}], "steps": [{"light": ["a"], "move": {"a": {"spin": 9}}}]},
     "'spin' is not a key here. Use to, rotate, about, scale"),
    ({"parts": [{"id": "a", "circle": [50, 50, 9]}], "steps": [{"light": ["a"], "move": {"a": {"to": [60, 0]}}}]},
     "the move takes 'a' past the view's edge. \"to\" is how far it moves"),
    ({"view": [160, 100], "parts": [{"id": "a", "circle": [20, 50, 9]}, {"id": "b", "circle": [140, 50, 9]},
                                    {"id": "l", "link": ["a", "b"]}], "steps": [{"light": ["l"], "move": {"l": {
        "to": [0, 9]}}}]}, "'l' is a link, which follows the parts it joins"),
]


LINK_FIXTURES = {
    "crowd": {
        "title": "A crowded hub", "layout": "hub", "nodes": [
            {"id": "core", "stencil": "chip", "label": "core", "lead": True},
            {"id": "a", "stencil": "key", "label": "keys"},
            {"id": "b", "stencil": "lock", "label": "locks"},
            {"id": "c", "stencil": "globe", "label": "web"},
            {"id": "d", "stencil": "battery", "label": "power"},
            {"id": "e", "stencil": "wifi", "label": "radio"},
            {"id": "f", "stencil": "gear", "label": "jobs"},
            {"id": "g", "stencil": "eye", "label": "camera"},
        ],
    },
    "curves": {
        "title": "Every curve", "size": "diagram", "view": [160, 100], "parts": [
            {"id": "a", "stencil": "user", "at": [20, 30], "size": 18, "label": "you"},
            {"id": "b", "stencil": "message", "at": [80, 30], "size": 18, "label": "note"},
            {"id": "c", "stencil": "mail", "at": [140, 30], "size": 18, "label": "mail"},
            {"id": "d", "stencil": "folder", "at": [20, 80], "size": 18, "label": "files"},
            {"id": "e", "stencil": "database", "at": [140, 80], "size": 18, "label": "store"},
            {"id": "ab", "link": ["a", "b"], "curve": "over"},
            {"id": "bc", "link": ["b", "c"], "curve": "under"},
            {"id": "ad", "link": ["a", "d"], "curve": "left"},
            {"id": "ce", "link": ["c", "e"], "curve": "right"},
            {"id": "de", "link": ["d", "e"], "curve": "straight"},
            {"id": "eb", "link": ["e", "b"]},
        ],
    },
    "fan-in": {
        "title": "Four ways into one server", "size": "diagram", "view": [160, 100], "parts": [
            {"id": "srv", "stencil": "server", "at": [80, 52], "size": 22, "label": "server", "lead": True},
            {"id": "web", "stencil": "browser", "at": [22, 22], "size": 20, "label": "browser"},
            {"id": "app", "stencil": "phone", "at": [22, 80], "size": 14, "label": "app"},
            {"id": "cron", "stencil": "clock", "at": [138, 22], "size": 18, "label": "timer"},
            {"id": "queue", "stencil": "queue", "at": [138, 80], "size": 20, "label": "queue"},
            {"id": "w", "link": ["web", "srv"]},
            {"id": "a", "link": ["app", "srv"]},
            {"id": "c", "link": ["cron", "srv"]},
            {"id": "q", "link": ["queue", "srv"]},
        ],
        "steps": [
            {"light": ["web", "w", "srv"], "caption": "A page asks"},
            {"light": ["app", "a", "srv"], "caption": "The app asks"},
        ],
    },
    "fan-in-tight": {
        "title": "Three sources on one side", "size": "diagram", "view": [160, 100], "parts": [
            {"id": "s1", "stencil": "browser", "at": [24, 24], "size": 16, "label": "web"},
            {"id": "s2", "stencil": "phone", "at": [24, 52], "size": 14, "label": "app"},
            {"id": "s3", "stencil": "terminal", "at": [24, 80], "size": 16, "label": "cli"},
            {"id": "srv", "stencil": "server", "at": [132, 52], "size": 24, "label": "server", "lead": True},
            {"id": "l1", "link": ["s1", "srv"]},
            {"id": "l2", "link": ["s2", "srv"]},
            {"id": "l3", "link": ["s3", "srv"]},
        ],
    },
    "group": {
        "title": "Into a group", "size": "diagram", "view": [160, 100], "parts": [
            {"id": "in", "stencil": "file", "at": [20, 50], "size": 18, "label": "upload"},
            {"id": "farm", "group": [
                {"id": "one", "stencil": "server", "at": [0, -22], "size": 16},
                {"id": "two", "stencil": "server", "at": [0, 0], "size": 16},
                {"id": "three", "stencil": "server", "at": [0, 22], "size": 16},
            ], "translate": [80, 50]},
            {"id": "farm-label", "rect": [62, 80, 36, 10], "label": "three servers", "label_at": "inside", "quiet": True},
            {"id": "out", "stencil": "cloud", "at": [140, 50], "size": 20, "label": "backup"},
            {"id": "i", "link": ["in", "farm"]},
            {"id": "o", "link": ["farm", "out"], "curve": "over"},
            {"id": "t", "link": ["in", "out"], "curve": "under"},
        ],
    },
    "flow": {
        "title": "Three steps in a row", "layout": "row", "nodes": [
            {"id": "mic", "stencil": "mic", "label": "you"},
            {"id": "core", "stencil": "rook", "label": "agent", "lead": True},
            {"id": "out", "stencil": "speaker", "label": "voice"},
        ],
    },
    "hub": {
        "title": "One hub and five spokes", "layout": "hub", "nodes": [
            {"id": "core", "stencil": "rook", "label": "agent", "lead": True},
            {"id": "threads", "stencil": "terminal", "label": "threads"},
            {"id": "mail", "stencil": "mail", "label": "mailbox"},
            {"id": "work", "stencil": "file", "label": "work list"},
            {"id": "phone", "stencil": "phone", "label": "phone"},
            {"id": "clock", "stencil": "clock", "label": "timers"},
        ],
    },
    "cycle": {
        "title": "The water cycle", "layout": "cycle", "nodes": [
            {"id": "sun", "stencil": "sun", "label": "heat"},
            {"id": "cloud", "stencil": "cloud", "label": "cloud"},
            {"id": "rain", "stencil": "rain", "label": "rain"},
            {"id": "sea", "stencil": "drop", "label": "sea", "lead": True},
        ],
    },
    "request": {
        "name": "request", "title": "A web request", "size": "diagram", "view": [200, 80], "parts": [
            {"id": "browser", "rect": [8, 28, 40, 28], "radius": 4, "label": "browser", "label_at": "below"},
            {"id": "server", "rect": [80, 28, 40, 28], "radius": 4, "label": "server", "label_at": "below"},
            {"id": "db", "group": [
                {"id": "body", "path": "M 158 32 L 158 54 A 14 5 0 0 0 186 54 L 186 32",
                 "label": "database", "label_at": "below"},
                {"id": "top", "ellipse": [172, 32, 14, 5]},
            ]},
            {"id": "web", "link": ["browser", "server"], "curve": "straight"},
            {"id": "query", "link": ["server", "db"], "curve": "straight"},
            {"id": "packet", "circle": [28, 42, 4], "fill": True, "weight": 2},
        ],
        "steps": [
            {"light": ["web", "server", "packet"], "caption": "Request", "move": {"packet": {"to": [72, 0]}}},
            {"light": ["query", "db", "packet"], "caption": "Query", "move": {"packet": {"to": [144, 5]}}},
        ],
    },
}


def _check_link_geometry_pose(scene, gap_px=None, min_body_px=None, step=None):
    """Independently verify one pose's routed links against real Cairo-flattened shape boundaries and real sampled/Pango
    label boxes (matching overlay._render_labels), plus MIN_LINK_BODY visible length, without reusing the router's
    own hull or label helpers."""
    parts = scene["steps"][step]["parts"] if step is not None else scene["parts"]
    groups, view, size = scene["groups"], scene["view"], scene["size"]
    moving = {name for st in scene.get("steps", ()) for name in st.get("move", ())}
    form = sample(scene, budget=640, step=step)
    scale = form["box"] / max(view)
    fw, fh = form["size"]
    fit = form.get("fit") or (scale, 0.0, 0.0, scale, 1.0, 1.0)
    gap_target = LINK_GAP if gap_px is None else gap_px
    gap = gap_target / scale
    min_req_px = (MIN_LINK_BODY if min_body_px is None else min_body_px) * form["box"] / DIAGRAM_BOX

    # 1. Independently flatten each solid part via Cairo path flattening into view coordinates.
    cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1)) if cairo else None
    if cr is not None:
        cr.set_tolerance(0.15)

    def _real_points(part):
        pts = []
        if cr is not None:
            for m in part["copies"]:
                cr.new_path()
                cr.set_matrix(cairo.Matrix(*m))
                _trace(cr, part)
                cr.identity_matrix()
                pts.extend(pt for kind, pt in cr.copy_path_flat() if kind in (cairo.PATH_MOVE_TO, cairo.PATH_LINE_TO))
        if not pts:
            pts = [_apply(m, *pt) for m in part["copies"] for pt in _outline(part)]
        return pts

    def _independent_hull(pts):
        uniq = sorted({(round(x, 6), round(y, 6)) for x, y in pts})
        if len(uniq) <= 2:
            return uniq
        cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])  # noqa: E731
        lo, hi = [], []
        for p in uniq:
            while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
                lo.pop()
            lo.append(p)
        for p in reversed(uniq):
            while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
                hi.pop()
            hi.append(p)
        return lo[:-1] + hi[:-1]

    def _poly_dist(x, y, poly):
        n = len(poly)
        if n == 0:
            return math.inf
        if n == 1:
            return math.hypot(x - poly[0][0], y - poly[0][1])
        inside = n >= 3
        best = math.inf
        for i in range(n):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % n]
            dx, dy = bx - ax, by - ay
            if inside and dx * (y - ay) - dy * (x - ax) < -1e-9:
                inside = False
            d2 = dx * dx + dy * dy
            t = 0.0 if d2 <= 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / d2))
            d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
            if d < best:
                best = d
        return 0.0 if inside else best

    # 2. Independently measure each rendered label's exact box in form pixels from form["labels"] + Pango logical size.
    label_boxes_px = {}  # part_id -> (x0, y0, x1, y1) in form pixels
    try:
        import gi
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo
        lcr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 16, 16))
        px_sz, spacing, _ = LABEL_TYPE[form["kind"]]
        lay = PangoCairo.create_layout(lcr)
        font = Pango.FontDescription()
        font.set_family("Noto Serif")
        font.set_weight(Pango.Weight.HEAVY)
        font.set_absolute_size(px_sz * Pango.SCALE)
        lay.set_font_description(font)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
        lay.set_attributes(attrs)
        for lbl in form["labels"]:
            lay.set_text(lbl["text"].upper(), -1)
            _, log = lay.get_pixel_extents()
            tw, th = float(log.width), float(log.height)
            left = lbl["x"] - (tw * 0.5 if lbl["align"] == 0 else tw if lbl["align"] < 0 else 0.0)
            label_boxes_px[lbl["id"]] = (left, lbl["y"] - th * 0.5, left + tw, lbl["y"] + th * 0.5)
    except Exception:
        for lbl in form["labels"]:
            label_boxes_px[lbl["id"]] = lbl["span"]

    solid = [p for p in parts if not p.get("link") and p["shape"] != "link"]
    named = {p["id"]: [p] for p in solid}
    named.update({g: [p for p in solid if p["group"] == g] for g in groups})
    part_pts = {p["id"]: _real_points(p) for p in solid}
    node_hull = {}
    node_box = {}
    node_centre = {}
    node_labels_px = {}
    for name, ps in named.items():
        pts = [pt for p in ps for pt in part_pts[p["id"]]]
        hull = _independent_hull(pts)
        xs, ys = [pt[0] for pt in pts], [pt[1] for pt in pts]
        bx = (min(xs), min(ys), max(xs), max(ys))
        node_hull[name] = hull
        node_box[name] = bx
        node_centre[name] = ((bx[0] + bx[2]) * 0.5, (bx[1] + bx[3]) * 0.5)
        node_labels_px[name] = [label_boxes_px[p["id"]] for p in ps if p["id"] in label_boxes_px]

    obs_units = []
    seen_groups = set()
    for p in solid:
        if p["id"] in moving or p["group"] in moving:
            continue
        if p["group"]:
            g = p["group"]
            if g not in seen_groups:
                seen_groups.add(g)
                obs_units.append((g, {gp["id"] for gp in named[g]}, node_hull[g], node_box[g], node_labels_px[g]))
        else:
            obs_units.append((p["id"], {p["id"]}, node_hull[p["id"]], node_box[p["id"]], node_labels_px[p["id"]]))

    def _to_form_px(vx, vy):
        fx, fy = _apply(fit, vx, vy)
        return fx - fw * 0.5, fy - fh * 0.5

    def _rect_dist_px(px, py, rect):
        dx = max(rect[0] - px, 0.0, px - rect[2])
        dy = max(rect[1] - py, 0.0, py - rect[3])
        return math.hypot(dx, dy)

    issues = []
    link_info = []
    for p in parts:
        if p["shape"] != "arrow" or not p.get("link"):
            continue
        na, nb = p["link"]
        ha, hb = node_hull[na], node_hull[nb]
        la, lb = node_labels_px[na], node_labels_px[nb]
        ca, cb = node_centre[na], node_centre[nb]
        ends = {sp["id"] for n in (na, nb) for sp in named[n]}
        # Independent room along centre-to-centre chord by stepping from centre until outside hull.
        chord = math.dist(ca, cb) or 1.0
        ux, uy = (cb[0] - ca[0]) / chord, (cb[1] - ca[1]) / chord
        # Estimate surface distance along chord using binary search on _poly_dist.
        def _chord_exit(origin, dx, dy, hull):
            lo, hi = 0.0, chord
            for _ in range(18):
                m = (lo + hi) * 0.5
                if _poly_dist(origin[0] + dx * m, origin[1] + dy * m, hull) <= 1e-4:
                    lo = m
                else:
                    hi = m
            return hi
        room = max(0.0, chord - _chord_exit(ca, ux, uy, ha) - _chord_exit(cb, -ux, -uy, hb))
        g = min(gap, max(0.4 * gap, 0.2 * room), 0.3 * room)
        req = g * 0.88  # 12% tolerance for pixel rasterization rounding and curve discretization.
        req_px = req * scale - 1.25  # Allow <= 1.25 px for rasterized _part_geom label anchor rounding.

        e1, e2 = tuple(p["args"][:2]), tuple(p["args"][2:])
        if (e2[0] - e1[0]) * (cb[0] - ca[0]) + (e2[1] - e1[1]) * (cb[1] - ca[1]) <= 0:
            issues.append(f"link '{p['id']}' points backwards relative to '{na}' -> '{nb}'")
        elen = math.dist(e1, e2) or 1.0
        nx, ny = -(e2[1] - e1[1]) / elen, (e2[0] - e1[0]) / elen
        q = ((e1[0] + e2[0]) * 0.5 + 2.0 * p["bend"] * nx, (e1[1] + e2[1]) * 0.5 + 2.0 * p["bend"] * ny)
        tip, wl, wr, hsz = _arrow_head_pts(e1, e2, q, p["width"])

        # 1. Endpoints and arrowhead wings vs real joined hulls & real rendered label boxes.
        for label_pt, pt in (("start", e1), ("end", e2), ("head-wing-l", wl), ("head-wing-r", wr)):
            fpx, fpy = _to_form_px(pt[0], pt[1])
            for nm, hull, labs in ((na, ha, la), (nb, hb, lb)):
                d_hull = _poly_dist(pt[0], pt[1], hull)
                if d_hull < req:
                    issues.append(f"link '{p['id']}' {label_pt} is {d_hull * scale:.1f} px from '{nm}' hull (< {req * scale:.1f} px)")
                for lbox in labs:
                    d_lab = _rect_dist_px(fpx, fpy, lbox)
                    if d_lab < req_px:
                        issues.append(f"link '{p['id']}' {label_pt} is {d_lab:.1f} px from '{nm}' rendered label (< {req_px:.1f} px)")

        # 2. Curve body vs non-endpoint real hulls, real rendered labels, and view bounds.
        for idx in range(41):
            t = idx / 40.0
            mt = 1.0 - t
            x = mt * mt * e1[0] + 2.0 * mt * t * q[0] + t * t * e2[0]
            y = mt * mt * e1[1] + 2.0 * mt * t * q[1] + t * t * e2[1]
            if x < -0.5 or x > view[0] + 0.5 or y < -0.5 or y > view[1] + 0.5:
                issues.append(f"link '{p['id']}' leaves view at ({x:.1f}, {y:.1f})")
                break
            fpx, fpy = _to_form_px(x, y)
            for oname, uids, ohull, obx, olabs in obs_units:
                if uids & ends:
                    continue
                if (obx[0] - gap * 0.5 < ca[0] < obx[2] + gap * 0.5 and obx[1] - gap * 0.5 < ca[1] < obx[3] + gap * 0.5
                        and obx[0] - gap * 0.5 < cb[0] < obx[2] + gap * 0.5 and obx[1] - gap * 0.5 < cb[1] < obx[3] + gap * 0.5):
                    continue
                d_obs = _poly_dist(x, y, ohull)
                if d_obs < req:
                    issues.append(f"link '{p['id']}' body comes {d_obs * scale:.1f} px from non-endpoint '{oname}' (< {req * scale:.1f} px)")
                    break
                for lbox in olabs:
                    d_ol = _rect_dist_px(fpx, fpy, lbox)
                    if d_ol < req_px:
                        issues.append(f"link '{p['id']}' body comes {d_ol:.1f} px from '{oname}' rendered label (< {req_px:.1f} px)")
                        break

        body_px = _link_body_len(p) * scale
        if min_req_px > 0.0 and body_px < min_req_px - 0.5:
            issues.append(f"link '{p['id']}' body is {body_px:.1f} px (< {min_req_px:.1f} px minimum)")

        link_info.append((p["id"], na, nb, e1, e2, (tip, wl, wr), hsz, g))

    # 3. Multiple links meeting on one node must not collide at their ends/arrowheads.
    for i in range(len(link_info)):
        id1, a1, b1, s1, e1, tri1, h1, g1 = link_info[i]
        for j in range(i + 1, len(link_info)):
            id2, a2, b2, s2, e2, tri2, h2, g2 = link_info[j]
            g_pair = max(g1, g2)
            if b1 == b2:
                if _tris_near(tri1, tri2, pad=0.0):
                    issues.append(f"links '{id1}' and '{id2}' arrowheads collide at '{b1}'")
                elif math.dist(e1, e2) < min(max(h1, h2), 0.85 * g_pair):
                    issues.append(f"links '{id1}' and '{id2}' end too close ({math.dist(e1, e2) * scale:.1f} px) at '{b1}'")
            if b1 == a2 and math.dist(e1, s2) < 0.7 * g_pair:
                issues.append(f"link '{id1}' head crowds link '{id2}' start ({math.dist(e1, s2) * scale:.1f} px) at '{b1}'")
            if a1 == b2 and math.dist(s1, e2) < 0.7 * g_pair:
                issues.append(f"link '{id2}' head crowds link '{id1}' start ({math.dist(s1, e2) * scale:.1f} px) at '{a1}'")
    return issues


def check_link_geometry(scene, gap_px=None, min_body_px=None):
    """Independently verify every routed link across the base pose and every step pose against real Cairo-flattened
    shape boundaries, real sampled/Pango label boxes, and MIN_LINK_BODY visible length. Pass min_body_px=0 for
    intentionally cramped scenes where no room exists inside the box. Returns violation strings."""
    issues = _check_link_geometry_pose(scene, gap_px=gap_px, min_body_px=min_body_px, step=None)
    for s_idx, step in enumerate(scene.get("steps", ())):
        if step.get("parts"):
            issues.extend(f"step {s_idx + 1}: {msg}"
                          for msg in _check_link_geometry_pose(scene, gap_px=gap_px, min_body_px=min_body_px, step=s_idx))
    return issues


def _review_scenes():
    """Reviews four and five's worst scenes, rebuilt from their recipe: (name, scene, True when it must run out of
    budget)."""
    ends = [{"id": "zz1", "circle": [5, 5, 2]}, {"id": "zz2", "circle": [195, 5, 2]},
            {"id": "zzl", "link": ["zz1", "zz2"]}]
    turn = [{"light": ["p"], "move": {"p": {"rotate": 33, "scale": 0.8}}}]
    tip = [{"light": ["p"], "move": {"p": {"rotate": 47, "scale": 0.7}}}]
    arcs = [{"id": f"p{k}", "path": f"M{150 + 60 * (k % 6)} {300 + 300 * (k // 6)}a-9-9 0 111-1"} for k in range(12)]
    pair = [{"id": "a", "circle": [60, 900, 20], "label": "A"}, {"id": "b", "circle": [940, 900, 20], "label": "B"},
            {"id": "l", "link": ["a", "b"]}]
    group = [dict(p, path=p["path"] + "-9-9 0 111-1" * 89) for p in arcs]
    heavy = [dict(p, path=p["path"] + "-9-9 0 111-1" * 97) for p in arcs]
    kinds = ["server", "database", "laptop", "phone", "browser", "cloud", "chip", "lock"]
    hub = [{"id": "h", "stencil": "chip", "label": "THE HUB NODE LABEL"}] + [
        {"id": f"x{k}", "stencil": kinds[k], "label": f"OTHER NODE LABEL {k}"} for k in range(7)]
    kids = [{"id": f"k{k}", "stencil": kinds[k], "at": [100, 60 + 20 * k], "size": 8, "label": f"KID {k}",
             "repeat": {"count": 30, "about": [100, 100]}} for k in range(5)]
    outs = [{"id": f"o{k}", "circle": [20 + 40 * k, 190, 5], "label": f"OUT {k}"} for k in range(4)]
    return [
        ("arc_3200", {"view": [200, 200], "size": "diagram", "parts": [{"id": "p", "arc": [100, 100, 50, 0, 3200]}]
                      + ends, "steps": turn}, False),
        ("arc_5760", {"view": [200, 200], "size": "diagram", "parts": [{"id": "p", "arc": [100, 100, 50, 0, 5760]}]
                      + ends, "steps": turn}, False),
        ("cycle_custom", {"title": "cyc", "layout": "cycle", "nodes": [
            {"id": f"c{k}", "stencil": kinds[k], "label": f"CYCLE NODE {k}"} for k in range(8)],
            "links": [[f"c{k}", f"c{j}", "LBL"] for k in range(8) for j in sorted(((k + 1) % 8, (k + 3) % 8))],
            "steps": [{"light": ["c0"], "move": {"c0": {"to": [k % 2, 0]}}} for k in range(8)]}, False),
        ("hub_custom16_steps", {"layout": "hub", "nodes": hub,
                                "links": [["h", f"x{k}", "LABEL TEXT"] for k in range(7)]
                                + [[f"x{k}", "h"] for k in range(7)] + [["x0", "x1"], ["x2", "x3"]],
                                "steps": [{"light": ["h"], "move": {"h": {"to": [k % 3 - 1, 0], "rotate": 4 * k}}}
                                          for k in range(8)]}, True),
        ("path_arc_tiny_chord", {"view": [200, 200], "size": "diagram", "parts": [
            {"id": "p", "path": "M100 60 A 40 40 0 1 1 100.000000000001 60"}] + ends, "steps": tip}, False),
        ("path_group_alt", {"view": [1000, 1000], "size": "diagram", "parts": [{"id": "g", "group": group}] + pair,
                            "steps": [{"light": ["a"], "move": {"g": {"to": [k + 1, 0]}} if k % 2 == 0 else
                                       {"g.p0": {"to": [0, k + 1]}}} for k in range(8)]}, True),
        ("path_heavy", {"view": [1000, 1000], "size": "diagram", "parts": heavy + pair}, True),
        ("repeat_group", {"view": [210, 210], "size": "diagram", "parts": [
            {"id": "rg", "rotate": 17, "translate": [10, 5], "group": kids}] + outs
            + [{"id": f"lk{k}", "link": [f"o{k}", "rg"]} for k in range(4)] + [{"id": "lo", "link": ["o0", "o3"]}],
            "steps": [{"light": ["rg"], "move": {"rg": {"rotate": 10 * k, "scale": 0.9}}} for k in range(8)]}, False),
        ("rotate_no_about_flip", {"view": [200, 200], "size": "diagram", "parts": [
            {"id": "p", "path": "M100 60 A 40 40 0 1 1 100.5 60"}] + ends, "steps": tip}, False),
        ("row12_steps", {"layout": "row", "nodes": [{"id": f"r{k}", "label": "W" * 24} for k in range(12)],
                         "steps": [{"light": ["r0"], "move": {f"r{j}": {"to": [0, k % 2]} for j in range(12)}}
                                   for k in range(8)]}, True),
    ] + _review5_scenes()


def _review5_scenes():
    """Review five: a tiny arc radius, legal scenes a spent budget once refused, and round parts turned at the edge."""
    pair = [{"id": "a", "circle": [20, 50, 5]}, {"id": "b", "circle": [80, 50, 5]}, {"id": "l", "link": ["a", "b"]}]
    loops = [{"id": f"h{k}", "path": f"M {10 + 3 * k} 90 " + " ".join(["a5 5 0 11.1 0"] * 84)} for k in range(7)]
    ring = [{"id": "a", "circle": [20, 20, 3]}, {"id": "b", "circle": [80, 20, 3]}, {"id": "l", "link": ["a", "b"]}]
    label = "abcdefghijklmnopqrstuvwx"
    dots = [{"id": f"h{k}", "path": f"M {52 + 6 * k} {95 - 10 * (k % 2)} " + " ".join(["a1 1 0 11.1 0"] * 84)}
            for k in range(7)]
    return [
        ("nan_arc_radius_inview", {"view": [100, 100], "parts": [
            {"id": "p", "path": "M 10 10 A 1e-160 1e-160 0 0 1 90 90"}] + pair}, False),
        ("cross_turn_heavy", {"view": [100, 100], "parts": loops + [
            {"id": "x", "poly": [50, 2, 50, 98, 50, 50, 2, 50, 98, 50]}] + ring,
            "steps": [{"light": ["x"], "move": {"x": {"rotate": 45}}}]}, True),
        ("tri_heavy_step", {"view": [100, 100], "parts": loops + [
            {"id": "t1", "poly": [10, 10, 40, 10, 10, 40], "closed": True},
            {"id": "t2", "poly": [47, 47, 47, 17, 17, 47], "closed": True}, {"id": "l", "link": ["t1", "t2"]}],
            "steps": [{"light": ["t1"], "move": {"t1": {"to": [0, 1]}}}]}, True),
        ("circle_turn_edge", {"view": [560, 560], "parts": [
            {"id": "ring", "circle": [280, 280, 279]}, {"id": "a", "circle": [200, 280, 10]},
            {"id": "b", "circle": [360, 280, 10]}, {"id": "l", "link": ["a", "b"]}],
            "steps": [{"light": ["ring"], "move": {"ring": {"rotate": 10}}}]}, False),
        ("ellipse_turn_edge", {"view": [400, 400], "parts": [
            {"id": "ring", "ellipse": [200, 200, 199, 199]}, {"id": "a", "circle": [150, 200, 10]},
            {"id": "b", "circle": [250, 200, 10]}, {"id": "l", "link": ["a", "b"]}],
            "steps": [{"light": ["ring"], "move": {"ring": {"rotate": 5, "about": [200, 200]}}}]}, False),
        ("row5_19links", {"layout": "row", "nodes": [{"id": f"n{k}", "label": label} for k in range(5)],
                          "links": [[f"n{a}", f"n{b}", "lbl"] for a in range(5) for b in range(5) if a != b][:19],
                          "steps": [{"light": ["n0"], "move": {f"n{j}": {"to": [0, k - 4]} for j in range(5)}}
                                    for k in range(8)]}, True),
        ("rrect_160", {"view": [100, 100], "parts": [
            {"id": f"r{k}", "rect": [48, 5 + k, 4, 3], "radius": 1, "repeat": {"count": 36, "about": [50, 50]}}
            for k in range(4)] + [{"id": "a", "circle": [50, 50, 2]}, {"id": "b", "circle": [50, 62, 2]},
                                  {"id": "l", "link": ["a", "b"]}]}, False),
        ("mixed_exact_boxed_ends", {"view": [100, 100], "parts": [
            {"id": "ring", "path": "M 30 40 A 10 10 0 1 0 30.1 40"}] + dots + [
            {"id": "tri", "poly": [60, 45, 60, 80, 25, 80], "closed": True}] + [
            {"id": f"k{k}", "link": [f"h{a}", f"h{b}"]} for k, (a, b) in enumerate(((0, 1), (2, 3), (4, 5), (6, 0)))]
            + [{"id": "l", "link": ["ring", "tri"]}], "steps": [{"light": ["h0"], "move": {"h0": {"to": [0, 1]}}}]},
         True),
        ("cpath_144_steps_all", {"view": [100, 100], "parts": [
            {"id": f"c{j}", "path": "M 45 45 " + "c1 1 2 1 0 0" * 95, "repeat": {"count": 36, "about": [50, 50]}}
            for j in range(4)] + [{"id": "a", "circle": [50, 50, 1]}, {"id": "b", "circle": [50, 60, 1]},
                                  {"id": "l", "link": ["a", "b"]}],
            "steps": [{"light": ["a"], "move": {f"c{j}": {"rotate": 3 * (k + 1) + j} for j in range(4)}}
                      for k in range(8)]}, False),
        ("cpath_edge_steps", {"view": [100, 100], "parts": [
            {"id": f"c{j}", "path": "M 45 45 " + "c1 1 2 1 0 0" * 95, "repeat": {"count": 36, "about": [50, 50]}}
            for j in range(4)] + [{"id": "a", "circle": [50, 50, 1]}, {"id": "b", "circle": [50, 60, 1]},
                                  {"id": "l", "link": ["a", "b"]}],
            "steps": [{"light": ["a"], "move": {f"c{j}": {"rotate": 3 * (k + 1) + j, "scale": 7.15, "about": [50, 50]}
                                                for j in range(4)}} for k in range(8)]}, True),
        ("arc_bulge_steps", {"view": [100, 100], "parts": [
            {"id": "p", "path": "M 50 5 A 40 40 0 1 1 50.1 5 " + "l0 0 " * 190,
             "repeat": {"count": 36, "step": [0, 0]}}]
            + pair, "steps": [{"light": ["p"], "move": {"p": {"to": [0.1 * (k + 1), 0]}}} for k in range(8)]}, False),
    ]


def _self_check(folder=None):
    for doc, words in BAD:
        scene, errors = validate(json.loads(json.dumps(doc)))
        assert scene is None and words in errors[0], (doc, errors)
    many = validate({"parts": [{"id": "a", "circle": [1]}, {"id": "b", "motion": "spin", "rect": [0, 0, 1, 1]}]})[1]
    assert len(many) == 2 and "'a'" in many[0] and "'b'" in many[1], many
    # The schema and the checker read the same tables.
    assert set(SCHEMA["$defs"]["part"]["properties"]) == set(PART_KEYS)
    assert set(SCHEMA["$defs"]["group"]["properties"]) == set(GROUP_KEYS)
    assert set(SCHEMA["properties"]) == set(SCENE_KEYS)
    json.dumps(SCHEMA)
    # The size: given, or a diagram when the scene has a label or many parts.
    assert validate(EXAMPLE)[0]["size"] == "icon"
    assert validate({**EXAMPLE, "size": "diagram"})[0]["size"] == "diagram"
    labelled = {"parts": [{"id": "a", "circle": [50, 50, 20], "label": "sun"}]}
    assert validate(labelled)[0]["size"] == "diagram"
    assert sample(validate(labelled)[0])["budget"] == SIZE_FORM["diagram"][0]
    assert sample(validate(labelled)[0])["box"] == DIAGRAM_BOX  # A label below takes no room from the box.
    wide = {"parts": [{"id": "a", "circle": [50, 50, 20], "label": "x" * 20, "label_at": "left"}]}
    assert sample(validate(wide)[0])["box"] < DIAGRAM_BOX  # One at the side does.
    many = {"parts": [{"id": f"p{k}", "circle": [10 + 10 * k, 50, 4]} for k in range(DIAGRAM_PARTS + 1)]}
    assert validate(many)[0]["size"] == "diagram"
    # A link finds its ends outside both parts and bows round a part in its way; a crossing arrow gets a note.
    row = [{"id": "a", "circle": [20, 50, 12]}, {"id": "b", "rect": [66, 38, 28, 24]},
           {"id": "c", "circle": [140, 50, 12]}]
    linked, _ = validate({"view": [160, 100], "parts": row + [{"id": "l", "link": ["c", "a"], "label": "back"}]})
    l = linked["parts"][-1]
    gap = LINK_GAP * 160 / DIAGRAM_BOX
    assert l["shape"] == "arrow" and l["bend"] > 0, l  # Round 'b', over the top.
    d_a = math.dist(l["args"][2:], (20, 50))
    assert (12 + gap) - 0.01 <= d_a <= (12 + gap) / math.cos(math.pi / 16.0) + 0.01, l  # Honest gap outside 'a'.
    assert not [n for n in sample(linked)["notes"] if "cross" in n], sample(linked)["notes"]
    straight, _ = validate({"view": [160, 100], "parts": row + [{"id": "l", "link": ["a", "b"]}]})
    assert straight["parts"][-1]["bend"] == 0
    crossing, _ = validate({"view": [160, 100], "parts": row + [
        {"id": "l", "arrow": [138, 34, 22, 34], "bend": -22, "label": "x"}]})
    assert any("'l' crosses 'b'" in n for n in sample(crossing)["notes"]), sample(crossing)["notes"]
    # A head: the shaft stops one head length short of the tip, and the head's own grains reach the tip.
    shot, _ = validate({"size": "diagram", "parts": [{"id": "s", "arrow": [10, 50, 90, 50]}]})
    tip, _, size = _head(shot["parts"][0])
    assert abs(_shaft(shot["parts"][0])[3][0] - (90 - size)) < 0.05 and size == HEAD_LENGTH * shot["parts"][0]["width"]
    form = sample(shot)
    px = (90 * form["box"] / 100 + 1 - form["size"][0] / 2, 50 * form["box"] / 100 + 1 - form["size"][1] / 2)
    assert min(math.dist(px, xy) for xy in zip(form["x"], form["y"])) < 1.5  # A grain at the very tip.
    # A short flowing link: no note, a pace set by its length, and its march evenly spaced in phase.
    pair, _ = validate({"view": [200, 95], "size": "diagram", "parts": [{"id": "a", "rect": [40, 30, 36, 22]},
                                                     {"id": "b", "rect": [92, 30, 36, 22]},
                                                     {"id": "l", "link": ["a", "b"], "motion": "flow"}]})
    form = sample(pair)
    flow = form["parts"][2]
    assert not [n for n in form["notes"] if "short" in n], form["notes"]
    assert flow["speed"] == max(MARCH_PACE[0], flow["paths"][0]["length"] / MARCH_SECONDS["normal"]), flow["speed"]
    phases = sorted(m[1] for m, p in zip(form["move"], form["part"]) if p == 2 and m)
    assert phases and max(b - a for a, b in zip(phases, phases[1:])) < 1.6 / len(phases), phases
    close = [{"id": "a", "rect": [40, 30, 36, 22]}, {"id": "b", "rect": [80, 30, 36, 22]}]
    near, _ = validate({"view": [200, 95], "parts": close + [{"id": "l", "link": ["a", "b"]}]})
    assert math.dist(near["parts"][2]["args"][:2], near["parts"][2]["args"][2:]) > 1  # Room is kept for an arrow.
    touching = [{"id": "a", "rect": [40, 30, 36, 22]}, {"id": "b", "rect": [70, 30, 36, 22]}]
    assert "touch" in validate({"parts": touching + [{"id": "l", "link": ["a", "b"]}]})[1][0]
    up, _ = validate({"parts": [{"id": "l", "arrow": [90, 50, 10, 50], "curve": "over"}]})
    assert up["parts"][0]["bend"] > 0  # Over is up on screen, whichever way the arrow runs.
    assert "use left or right" in validate({"parts": [{"id": "l", "arrow": [50, 10, 50, 90], "curve": "over"}]})[1][0]
    assert "not a part or group" in validate({"parts": row + [{"id": "l", "link": ["a", "zz"]}]})[1][0]
    assert not re.search(r"\b(DEFAULT_WIDTH|MOTIONS|SPEEDS|CURVES|LABEL_AT|SIZES|DIAGRAM_LINE|DIAGRAM_PARTS|LIMITS)\b",
                         words), words
    assert set(SCHEMA["properties"]["nodes"]["items"]["properties"]) == set(NODE_KEYS)
    # Every stencil parses, draws ink, and reads its pivot; a turning stencil turns about it.
    for name in stencils.NAMES:
        doc = {"size": "diagram", "parts": [{"id": "s", "stencil": name, "at": [50, 50], "size": 60}]}
        scene, errors = validate(doc)
        assert not errors and all(_stencil(p["args"])[0] for p in scene["parts"]), (name, errors)
        form = sample(scene)
        assert all(form["grains"].values()) and not [n for n in form["notes"] if "nothing" in n], (name, form["notes"])
    crank = sample(validate({"parts": [{"id": "c", "stencil": "crank", "at": [50, 50], "motion": "turn"}]})[0])
    assert max(map(abs, crank["parts"][0]["centre"])) < 1.0, crank["parts"][0]["centre"]  # The journal, not the box.
    engine, _ = validate({"parts": [{"id": "e", "stencil": "engine", "at": [50, 50], "size": 90}],
                          "steps": [{"light": ["e.piston"]}]})
    assert [p["id"] for p in engine["parts"]][:2] == ["e.block", "e.intake"] and engine["groups"]["e"]
    # A layout places its nodes and joins them: a row in order, a ring closed, a hub from its middle, a pair joined
    # both ways bowed apart.
    nodes = [{"id": n, "stencil": "server", "label": n} for n in ("a", "b", "c")]
    row, _ = validate({"layout": "row", "nodes": nodes})
    assert [p["id"] for p in row["parts"]] == ["a", "b", "c", "a-b", "b-c"] and row["size"] == "diagram"
    assert [p["id"] for p in validate({"layout": "cycle", "nodes": nodes})[0]["parts"]][-1] == "c-a"
    assert [p["id"] for p in validate({"layout": "hub", "nodes": nodes})[0]["parts"]][3:] == ["a-b", "a-c"]
    both, _ = validate({"layout": "row", "nodes": nodes, "links": [["a", "b", "ask"], ["b", "a"]]})
    rise = [_arrow_curve(p)[1][1] - p["args"][1] for p in both["parts"][3:]]
    assert rise[0] < 0 < rise[1], rise  # One over the top, one under.
    boxed, _ = validate({"layout": "column", "nodes": [{"id": "x", "label": "idea"}, {"id": "y", "label": "plan"}]})
    assert boxed["parts"][0]["shape"] == "rect" and boxed["parts"][0]["label_at"] == "inside"
    # Lead and quiet shift the dust and its light; the outline draws only when a look is chosen.
    plain = sample(row)
    led = sample(validate({"layout": "row", "nodes": [{**nodes[0], "lead": True}] + nodes[1:]})[0])
    light = lambda form: max(b for b, o in zip(form["bright"], form["owner"]) if o == "a")  # noqa: E731
    assert led["grains"]["a"] > plain["grains"]["a"] and light(led) > light(plain)
    global OUTLINE_LOOK, MATERIAL
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 400)
    dense, MATERIAL = MATERIAL, False  # The drawn outline belongs to the look without material dust.
    for look in (None, *OUTLINES):
        OUTLINE_LOOK = look
        draw_outline(cairo.Context(surface), sample(row), 400, 200, (1.0, 0.8, 0.5))
        assert any(surface.get_data()) == bool(look), look
    OUTLINE_LOOK = "clear"
    # The turn's lead turns a grain further on, and nothing else.
    gear = sample(validate({"parts": [{"id": "g", "rect": [30, 30, 40, 10], "motion": "turn"}]})[0])
    plain, ahead = targets(gear, 1.0), targets(gear, 0.5, [0.5] * gear["budget"])
    assert max(abs(a - b) for a, b in zip(plain[0], ahead[0])) < 1e-9
    # A step moves a part: it flies there whole, its link follows, and the whole scene shows it as drawn again.
    assert set(SCHEMA["$defs"]["step"]["properties"]) == set(STEP_KEYS) and SCHEMA["$defs"]["move"]
    three = [{"id": "a", "circle": [20, 50, 12]}, {"id": "b", "rect": [66, 38, 28, 24]},
             {"id": "c", "circle": [140, 50, 12]}]
    moving, _ = validate({"view": [160, 100], "parts": three + [{"id": "l", "link": ["a", "b"]}],
                          "steps": [{"light": ["a"], "move": {"a": {"to": [0, 30]}}}, {"light": ["b"]},
                                    {"light": ["a"], "move": {"a": {"to": [0, 0], "rotate": 180}}}]})
    whole = sample(moving)
    down = sample(moving, step=0, previous=whole)
    index = [p["id"] for p in down["parts"]].index("a")
    assert down["parts"][index]["flight"] == (None, down["parts"][index]["pose"])
    assert down["grains"]["a"] == whole["grains"]["a"]  # It keeps its grains, so it arrives whole.
    assert sum(down["grains"].values()) == down["budget"]
    mine = [i for i, o in enumerate(down["owner"]) if o == "a"]
    assert {whole["owner"][i] for i in mine} == {"a"}
    k = moving["parts"].index(next(p for p in moving["parts"] if p["id"] == "a"))
    assert moving["steps"][1]["parts"][k]["pose"] == moving["steps"][0]["parts"][k]["pose"]  # The move holds.
    assert moving["steps"][0]["parts"][-1]["args"] != moving["parts"][-1]["args"]  # The link is routed again.
    start = targets(down, 0.0)
    # It starts where it was: each grain within its line's width of its old place, and none drifts on average.
    assert max(abs(start[1][i] - whole["y"][i]) for i in mine) < 6
    assert abs(sum(start[1][i] - whole["y"][i] for i in mine) / len(mine)) < 0.5
    assert not flights(down, FLIGHT) and targets(down, FLIGHT)[1] == down["y"]  # It lands, and then costs nothing.
    turned = sample(moving, step=2, previous=sample(moving, step=1, previous=down))
    now = _then(_pose_matrix(turned["parts"][index]["pose"]), flights(turned, FLIGHT / 2)[index])
    assert abs(now[1] - 1.0) < 1e-9  # Half way through a half turn it has turned a quarter, clockwise.
    back = sample(moving, previous=down)
    assert back["parts"][index]["flight"] == (down["parts"][index]["pose"], None) and "pose" not in back["parts"][index]
    # An engine moves by named strokes, and its rod holds the crank pin all the way through each flight.
    strokes = [{"light": ["e.piston"], "move": {"e": pose}} for pose in stencils.POSES["engine"]]
    engine, errors = validate({"parts": [{"id": "e", "stencil": "engine", "at": [50, 50], "size": 90, "lead": True}],
                               "steps": strokes})
    assert not errors, errors
    form = sample(engine)
    for k, pose in enumerate(stencils.POSES["engine"]):
        form = sample(engine, step=k, previous=form)
        ids = [p["id"] for p in form["parts"]]
        crank, rod = ids.index("e.crank"), ids.index("e.rod")
        _, _, _, pin, _, end, _, _ = form["parts"][crank]["engine"]
        for u in (0.25, 0.5, 0.75):
            fly = flights(form, u * FLIGHT)
            assert math.dist(_apply(fly[crank], *pin), _apply(fly[rod], *end)) < 0.5, (pose, u)
        assert not form["notes"], form["notes"]  # A compound's own labels sit on its own parts on purpose.
    down = [p for p in engine["steps"][0]["parts"] if p["id"] == "e.piston"][0]["pose"]
    assert down[0][1] > 0 and [p for p in engine["steps"][1]["parts"] if p["id"] == "e.piston"][0]["pose"][0][1] == 0
    # A step still draws when the form before it had fewer grains than its budget.
    whole = sample(moving)
    short = {**whole, **{key: whole[key][:-9] for key in ("x", "y", "part", "move", "bright", "owner")}}
    assert len(sample(moving, step=0, previous=short)["x"]) == whole["budget"]
    # No grain reaches the engine without a finite place: one is left out, with a note.
    global _line_grains
    real = _line_grains
    _line_grains = lambda *a: [(math.nan, 0.0)] + real(*a)[1:]  # noqa: E731
    try:
        lost = sample(linked)
    finally:
        _line_grains = real
    assert all(math.isfinite(v) for v in lost["x"] + lost["y"])
    assert any("could not be placed" in n for n in lost["notes"])
    # The line goes under a diagram's parts, not under links, arrows, turning parts, or an icon.
    linked, _ = validate({"view": [160, 100], "size": "diagram", "parts": three + [
        {"id": "l", "link": ["a", "b"]}, {"id": "g", "circle": [140, 20, 8], "motion": "turn"}]})
    assert [_outlined(linked, p) for p in linked["parts"]] == [True, True, True, False, False]
    assert not any(_outlined(validate(EXAMPLE)[0], p) for p in validate(EXAMPLE)[0]["parts"])
    MATERIAL = dense
    assert not dense or not any(_outlined(linked, p) for p in linked["parts"])  # Material dust draws the lines instead.
    # Material dust: baked once per diagram, reused across steps, quiet until a step lights a part.
    if MATERIAL:
        quiet = sample(linked)
        mat = quiet["material"]
        assert len(mat["parts"]) == len(linked["parts"])
        assert sample(linked, step=None, previous=quiet)["material"] is mat
        _, glow, lits, _, _ = material_state(quiet, 5.0)
        assert glow == [MAT_GLOW[False]] * len(linked["parts"]) and lits == [0.0] * len(linked["parts"])
        stepped, _ = validate({"view": [160, 100], "size": "diagram", "parts": three,
                               "steps": [{"light": ["a"]}, {"light": ["b", "c"], "move": {"b": {"to": [0, 20]}}}]})
        base_step = sample(stepped)
        lit1 = sample(stepped, step=0, previous=base_step)
        lit2 = sample(stepped, step=1, previous=lit1)
        whole_again = sample(stepped, step=None, previous=lit2)
        sw = base_step["swarm"]
        assert any(sw) and not all(sw)
        # Ambient grains never change owner part across step switches.
        for nxt in (lit1, lit2, whole_again):
            assert all(base_step["owner"][i] == nxt["owner"][i] for i, is_sw in enumerate(sw) if not is_sw)
        # Step 1 gathers swarm grains onto "a" up to its SWARM_CAP ceiling; overflow stays spread.
        base_sw_a = sum(1 for i, is_sw in enumerate(sw) if is_sw and base_step["owner"][i] == "a")
        lit1_sw_a = sum(1 for i, is_sw in enumerate(sw) if is_sw and lit1["owner"][i] == "a")
        assert base_sw_a < lit1_sw_a <= min(sum(sw), max(24, round(base_sw_a * SWARM_CAP)))
        # Step 2 moves every grain released from the previously lit part ("a") onto newly lit parts ("b", "c") first.
        released_a = [i for i, is_sw in enumerate(sw) if is_sw and lit1["owner"][i] == "a" and lit2["owner"][i] != "a"]
        assert released_a and all(lit2["owner"][i] in ("b", "c") for i in released_a)
        assert {"b", "c"} == {lit2["owner"][i] for i, is_sw in enumerate(sw) if is_sw}
        # Returning to the whole scene spreads the swarm across all parts again.
        assert {"a", "b", "c"} == {whole_again["owner"][i] for i, is_sw in enumerate(sw) if is_sw}
        _, g0, l0, _, _ = material_state(lit2, 0.0)
        _, g1, l1, _, _ = material_state(lit2, 5.0)
        assert l0 == [1.0, 0.0, 0.0] and g0[1] == MAT_GLOW[False]
        assert l1 == [0.0, 1.0, 1.0] and g1[1] == MAT_GLOW[True]
        # Small lit part stays capped instead of swallowing the whole highlight swarm.
        tiny_doc, _ = validate({"view": [160, 100], "size": "diagram", "parts": [
            {"id": "tiny", "rect": [10, 10, 14, 14]},
            {"id": "big1", "rect": [40, 10, 50, 80]},
            {"id": "big2", "rect": [100, 10, 50, 80]}], "steps": [{"light": ["tiny"]}]})
        t_base = sample(tiny_doc)
        t_lit = sample(tiny_doc, step=0, previous=t_base)
        base_sw_tiny = sum(1 for i, is_sw in enumerate(t_base["swarm"]) if is_sw and t_base["owner"][i] == "tiny")
        lit_sw_tiny = sum(1 for i, is_sw in enumerate(t_lit["swarm"]) if is_sw and t_lit["owner"][i] == "tiny")
        assert lit_sw_tiny <= max(24, round(base_sw_tiny * SWARM_CAP)) and lit_sw_tiny < sum(t_base["swarm"]) // 2
        # Mid-ramp was_lit preserves current lit level without flashing to 1.0 or 0.0.
        lit2["parts"][0]["was_lit"] = 0.4
        _, _, l_mid, _, _ = material_state(lit2, 0.0)
        assert abs(l_mid[0] - 0.4) < 1e-6
        # Figure eight self-crossing: earlier arrival wins at the crossing point.
        fig8, errs = validate({"size": "diagram", "parts": [{
            "id": "eight", "path": "M 50 50 C 20 10 80 10 50 50 C 20 90 80 90 50 50 Z"}]})
        assert not errs, errs
        f8 = sample(fig8)
        b8 = f8["material"]["parts"][0]
        cx8 = min(b8["tex_w"] - 1, max(0, int((0.0 - b8["box"][0]) * b8["bake_scale"])))
        cy8 = min(b8["tex_h"] - 1, max(0, int((0.0 - b8["box"][1]) * b8["bake_scale"])))
        u_cross = b8["surface"].get_data()[cy8 * b8["surface"].get_stride() + cx8 * 4 + 1] / 255.0
        assert 0.0 < u_cross < 0.25, u_cross
    # Plain rows of four and nine label boxes keep room for links and fill the whole budget.
    for count in (4, 9):
        doc = {"name": f"row{count}", "layout": "row",
               "nodes": [{"id": f"n{k}", "label": "voice in"} for k in range(count)]}
        rscene, rerrs = validate(doc)
        assert not rerrs, (count, rerrs)
        rform = sample(rscene)
        assert len(rform["x"]) == rform["budget"], (count, len(rform["x"]), rform["budget"])
        for k in range(count - 1):
            assert rform["grains"].get(f"n{k}-n{k + 1}", 0) > 0, (count, k)
    scenes = [("example", EXAMPLE)]
    if folder:
        for name in sorted(os.listdir(folder)):
            if name.endswith(".json"):
                with open(os.path.join(folder, name)) as f:
                    scenes.append((name, json.load(f)))
    for name, doc in scenes:
        scene, errors = validate(doc)
        assert not errors, (name, errors)
        times = []
        for budget in (640, 2000, 5000):
            form = sample(scene, budget, box=BOX)
            assert len(form["x"]) == budget and sum(form["grains"].values()) == budget, name
            times.append(form["ms"])
            tx, _, tb = targets(form, 2.3)
            assert len(tx) == budget and all(math.isfinite(v) for v in tx + tb)
        assert sample(scene, 640)["x"] == sample(scene, 640)["x"], name  # The same scene gives the same dust.
        if scene["steps"]:
            first = sample(scene, 640)
            lit = sample(scene, 640, step=0, previous=first)
            kept = sum(a == b for a, b in zip(first["owner"], lit["owner"]))
            assert kept > 0.5 * 640, (name, kept)
        print(f"{name:24} ok  sample ms at 640/2000/5000: {times}  notes: {len(form['notes'])}")
    # Hard and ordinary diagram link geometry fixtures: base pose and all step poses checked by check_link_geometry.
    for fname, fdoc in LINK_FIXTURES.items():
        fscene, ferrs = validate(json.loads(json.dumps(fdoc)))
        assert not ferrs, (fname, ferrs)
        fissues = check_link_geometry(fscene)
        assert not fissues, (fname, fissues)
    # Regression (Pass 2 closure bug): two crowded left-to-right links followed by a right-to-left link on the same
    # target node must each evaluate their own forward/obstacle context rather than the last link's closure.
    closure_scene, closure_errs = validate({"size": "diagram", "view": [560, 560], "parts": [
        {"id": "n0", "rect": [40, 206, 50, 40]},
        {"id": "n1", "rect": [40, 266, 50, 40]},
        {"id": "n2", "rect": [470, 236, 50, 40]},
        {"id": "c", "rect": [255, 236, 50, 40]},
        {"id": "l0", "link": ["n0", "c"]},
        {"id": "l1", "link": ["n1", "c"]},
        {"id": "l2", "link": ["n2", "c"]},
    ]})
    assert not closure_errs, closure_errs
    closure_issues = check_link_geometry(closure_scene)
    assert not closure_issues, closure_issues
    # Regression (incremental step spread): moving a crowded neighbour away must clear stale Pass 2 spread on the
    # reused sibling link so the step pose matches a fresh route.
    spread_doc = {"size": "diagram", "view": [560, 560], "parts": [
        {"id": "n0", "rect": [40, 206, 50, 40]},
        {"id": "n1", "rect": [40, 266, 50, 40]},
        {"id": "c", "rect": [255, 236, 50, 40]},
        {"id": "l0", "link": ["n0", "c"]},
        {"id": "l1", "link": ["n1", "c"]},
    ], "steps": [{"light": ["n0"], "move": {"n0": {"to": [420, 0]}}}]}
    spread_scene, spread_errs = validate(json.loads(json.dumps(spread_doc)))
    assert not spread_errs, spread_errs
    assert not check_link_geometry(spread_scene), check_link_geometry(spread_scene)
    fresh_step, fresh_errs = validate({"size": "diagram", "view": [560, 560], "parts": [
        {"id": "n0", "rect": [460, 206, 50, 40]},
        {"id": "n1", "rect": [40, 266, 50, 40]},
        {"id": "c", "rect": [255, 236, 50, 40]},
        {"id": "l0", "link": ["n0", "c"]},
        {"id": "l1", "link": ["n1", "c"]},
    ]})
    assert not fresh_errs, fresh_errs
    step_l1 = next(p for p in spread_scene["steps"][0]["parts"] if p["id"] == "l1")
    fresh_l1 = next(p for p in fresh_step["parts"] if p["id"] == "l1")
    assert all(abs(a - b) < 1e-6 for a, b in zip(step_l1["args"], fresh_l1["args"])), (step_l1["args"], fresh_l1["args"])
    # Regression: close nodes with label between them and curve="straight" must never flip ends backwards.
    for curve_opt in ("straight", None):
        link_spec = {"id": "l", "link": ["a", "b"]}
        if curve_opt is not None:
            link_spec["curve"] = curve_opt
        close_lbl, cl_errs = validate({"size": "diagram", "view": [560, 560], "parts": [
            {"id": "a", "rect": [230, 100, 100, 50], "label": "first", "label_at": "below"},
            {"id": "b", "rect": [230, 165, 100, 50], "label": "second", "label_at": "below"},
            link_spec,
        ]})
        assert not cl_errs, (curve_opt, cl_errs)
        lp = close_lbl["parts"][2]
        assert lp["args"][3] > lp["args"][1] + 0.5, (curve_opt, lp["args"])
    # Regression: link leaving below a node's "below" label clears the real rendered label box by ~LINK_GAP px.
    below_doc, below_errs = validate({"size": "diagram", "view": [160, 100], "parts": [
        {"id": "a", "rect": [60, 10, 40, 20], "label": "top", "label_at": "below"},
        {"id": "b", "rect": [60, 75, 40, 20], "label": "bot", "label_at": "below"},
        {"id": "l", "link": ["a", "b"], "curve": "straight"},
    ]})
    assert not below_errs, below_errs
    below_issues = check_link_geometry(below_doc)
    assert not below_issues, below_issues
    # Worst legal scenes across all 3 cost drivers (links, shapes, layout): validate() must stay fast.
    wall_parts = [
        {"id": "a", "rect": [20, 220, 60, 120], "label": "left"},
        {"id": "b", "rect": [480, 220, 60, 120], "label": "right"},
    ] + [{"id": f"w{i}", "rect": [250, i * 56, 60, 52]} for i in range(10)] + [
        {"id": f"l{i}", "link": ["a", "b"]} for i in range(12)
    ]
    wall_worst = {"size": "diagram", "view": [560, 560], "parts": wall_parts,
                  "steps": [{"light": ["a"], "move": {"b": {"to": [0, (i - 4) * 4]}}} for i in range(8)]}
    mesh_nodes = [{"id": f"n{i}", "rect": [60 + (i % 4) * 130, 80 + (i // 4) * 260, 70, 50], "label": f"node {i}"}
                  for i in range(8)]
    mesh_links = [{"id": f"e{k}", "link": [f"n{k % 8}", f"n{(k % 8 + 1 + (k // 8) * 2) % 8}"]} for k in range(16)]
    mesh_worst = {"size": "diagram", "view": [560, 560], "parts": mesh_nodes + mesh_links,
                  "steps": [{"light": [f"n{i}"], "move": {f"n{i}": {"to": [5, 5]}}} for i in range(8)]}
    dw_parts = ([{"id": f"l{i}", "rect": [20, 60 + i * 120, 60, 60], "label": f"left {i}"} for i in range(4)]
                + [{"id": f"r{i}", "rect": [480, 60 + i * 120, 60, 60], "label": f"right {i}"} for i in range(4)]
                + [{"id": f"w{i}", "rect": [250, i * 94, 60, 90]} for i in range(6)]
                + [{"id": f"k{i}", "link": [f"l{i % 4}", f"r{(i + i // 4) % 4}"]} for i in range(10)])
    dw_worst = {"size": "diagram", "view": [560, 560], "parts": dw_parts,
                "steps": [{"light": ["l0"], "move": {f"r{i % 4}": {"to": [0, 8]}}} for i in range(8)]}
    # Heavy shapes: 12 large-arc paths in a [10000, 10000] view, 4 with repeat=36, with 0 and 8 rotate steps,
    # plus a heaviest path+link variant.
    big_arc_d = "M 100 5000 " + " ".join(
        f"A 4900 4900 0 1 1 {9900 if k % 2 == 0 else 100} {5000 + (k % 2)}" for k in range(42))
    heavy_parts = [{"id": f"p{i}", "path": big_arc_d,
                    **({"repeat": {"count": 36, "about": [5000, 5000], "rotate": 10}} if i < 4 else {})}
                   for i in range(12)]
    heavy_0 = {"view": [10000, 10000], "parts": heavy_parts}
    heavy_8 = {"view": [10000, 10000], "parts": heavy_parts,
               "steps": [{"light": ["p0"], "move": {f"p{i % 4}": {"rotate": 5 * (i + 1)}}} for i in range(8)]}
    def _arc_path(cx, cy, r):
        return f"M {cx - r} {cy} " + " ".join(
            f"A {r} {r} 0 1 1 {cx + r if k % 2 == 0 else cx - r} {cy + (k % 2)}" for k in range(42))
    heavy_links_8 = {
        "view": [10000, 10000], "size": "diagram",
        "parts": ([{"id": f"p{i}",
                    "path": _arc_path(1500 + (i % 4) * 2200, 2200 + (i // 4) * 2600, 250),
                    **({"repeat": {"count": 35, "about": [1500 + (i % 4) * 2200, 2200 + (i // 4) * 2600],
                                   "rotate": 10}} if i < 4 else {})}
                   for i in range(12)]
                  + [{"id": f"l{i}", "link": [f"p{i}", f"p{(i + 1) % 12}"]} for i in range(12)]),
        "steps": [{"light": ["p0"], "move": {f"p{i % 4}": {"rotate": 5 * (i + 1)}}} for i in range(8)],
    }
    hub_12 = {"layout": "hub", "nodes": [{"id": f"n{i}", "label": f"node {i}"} for i in range(12)]}
    row_12 = {"layout": "row", "nodes": [{"id": f"n{i}", "label": f"node {i}"} for i in range(12)]}
    col_12 = {"layout": "column", "nodes": [{"id": f"n{i}", "label": f"node {i}"} for i in range(12)]}
    cycle_12 = {"layout": "cycle", "nodes": [{"id": f"n{i}", "stencil": "server", "label": f"n{i}"} for i in range(12)]}
    def _poly_ring(cx, cy, r, n=64):
        pts = []
        for k in range(n):
            ang = 2 * math.pi * k / n
            pts.extend((round(cx + r * math.cos(ang), 2), round(cy + r * math.sin(ang), 2)))
        return pts
    grp14_8s = {
        "size": "diagram", "view": [560, 560],
        "parts": ([{"id": "g", "group": [{"id": f"k{i}", "poly": _poly_ring(
                       280 + 140 * math.cos(2 * math.pi * i / 14),
                       280 + 140 * math.sin(2 * math.pi * i / 14), 22, 64)} for i in range(14)]},
                   {"id": "a", "rect": [15, 250, 40, 40]}, {"id": "b", "rect": [505, 250, 40, 40]}]
                  + [{"id": f"l{i}", "link": ["a" if i % 2 == 0 else "b", "g"]} for i in range(8)]),
        "steps": [{"light": ["g"], "move": {"a": {"to": [0, (i - 4) * 8]}}} for i in range(8)],
    }
    rep36_8s = {
        "size": "diagram", "view": [560, 560],
        "parts": ([{"id": f"r{i}", "poly": _poly_ring(100 + i * 120, 280, 12, 64),
                    "repeat": {"count": 36, "about": [100 + i * 120, 280], "rotate": 10}} for i in range(4)]
                  + [{"id": f"l{i}", "link": [f"r{i % 4}", f"r{(i + 1) % 4}"]} for i in range(12)]),
        "steps": [{"light": ["r0"], "move": {"r0": {"rotate": 5 * (i + 1)}}} for i in range(8)],
    }
    grp_rep_8s = {
        "size": "diagram", "view": [560, 560],
        "parts": ([{"id": "g", "group": [{"id": f"k{i}", "poly": _poly_ring(
                       280 + 60 * math.cos(2 * math.pi * i / 4),
                       280 + 60 * math.sin(2 * math.pi * i / 4), 10, 64),
                       "repeat": {"count": 36, "about": [280, 280], "rotate": 10}} for i in range(4)]},
                   {"id": "a", "rect": [20, 260, 40, 40]}, {"id": "b", "rect": [500, 260, 40, 40]}]
                  + [{"id": f"l{i}", "link": ["a" if i % 2 == 0 else "b", "g"]} for i in range(8)]),
        "steps": [{"light": ["g"], "move": {"a": {"to": [0, (i - 4) * 8]}}} for i in range(8)],
    }
    tiny_big_r = "M 10 30 " + " ".join(
        f"A 10000 10000 0 0 1 {50 if k % 2 == 0 else 10} {30 + (k % 2)}" for k in range(36))
    r10k_view60 = {
        "size": "diagram", "view": [60, 60],
        "parts": ([{"id": f"p{i}", "path": tiny_big_r} for i in range(11)]
                  + [{"id": "a", "circle": [10, 10, 3]}, {"id": "b", "circle": [50, 50, 3]},
                     {"id": "l0", "link": ["a", "b"]}]),
    }
    hub_bi_ids = ["c"] + [f"n{i}" for i in range(7)]
    hub_bi_8s = {
        "layout": "hub", "nodes": [{"id": nid, "label": nid} for nid in hub_bi_ids],
        "links": [[a, b] for n in hub_bi_ids[1:] for a, b in (("c", n), (n, "c"))],
        "steps": [{"light": [hub_bi_ids[i % len(hub_bi_ids)]],
                   "move": {hub_bi_ids[1 + (i % 7)]: {"to": [0, 6]}}} for i in range(8)],
    }
    col_cross_ids = [f"n{i}" for i in range(12)]
    col12_cross = {
        "layout": "column", "nodes": [{"id": nid, "label": f"node {i}"} for i, nid in enumerate(col_cross_ids)],
        "links": [[col_cross_ids[i], col_cross_ids[(i + 5) % 12]] for i in range(12)],
    }
    bound_max_8s = {
        "size": "diagram", "view": [560, 560],
        "parts": ([{"id": f"n{i}", "rect": [40 + (i % 4) * 140, 40 + (i // 4) * 180, 50, 40], "label": f"node {i}"}
                   for i in range(12)]
                  + [{"id": f"l{i}", "link": [f"n{i}", f"n{(i + 5) % 12}"]} for i in range(12)]),
        "steps": [{"light": ["n0"], "move": {f"n{k}": {"to": [(i % 2) * 4 - 2, (k % 2) * 4 - 2]} for k in range(12)}}
                  for i in range(8)],
    }
    for wname, wdoc in (
        ("wall_24p_8s", wall_worst), ("mesh_24p_8s", mesh_worst), ("dwall_24p_8s", dw_worst),
        ("heavy_0", heavy_0), ("heavy_8", heavy_8), ("heavy_links_8", heavy_links_8),
        ("hub_12_boxes", hub_12), ("row_12_boxes", row_12), ("col_12_boxes", col_12), ("cycle_12_st", cycle_12),
        ("grp14_8s", grp14_8s), ("rep36_8s", rep36_8s), ("grp_rep_8s", grp_rep_8s),
        ("r10k_view60", r10k_view60), ("hub_bi_8s", hub_bi_8s), ("col12_cross", col12_cross),
        ("bound_max_8s", bound_max_8s),
    ):
        wscene, werrs = validate(json.loads(json.dumps(wdoc)))
        work = _TLS.last_work
        assert not werrs, (wname, werrs)
        assert work.used <= work.limit, (wname, work.used)
        print(f"worst-case {wname:14} ok  units: {work.used}{' (ran out)' if work.ran_out else ''}")
    # Review four's worst scenes: each is accepted within the budget, the heavy ones run out, and every step samples.
    for rname, rdoc, runs_out in _review_scenes():
        rscene, rerrs = validate(json.loads(json.dumps(rdoc)))
        work = _TLS.last_work
        assert not rerrs and work.used <= WORK_BUDGET and work.ran_out == runs_out, (rname, rerrs, work.used)
        for k in range(len(rscene["steps"])):
            sample(rscene, step=k)
        print(f"review scene {rname:22} ok  units: {work.used}{' (ran out)' if work.ran_out else ''}")
    rev = {name: doc for name, doc, _ in _review_scenes()}
    # A spent budget never refuses a scene that main and an unlimited budget both accept. Link ends get their outlines
    # first; an end the budget cannot afford is main's box, so the verdict is then main's. Main refuses tri_heavy_step.
    for name in ("cross_turn_heavy", "tri_heavy_step", "circle_turn_edge", "ellipse_turn_edge", "path_group_alt",
                 "mixed_exact_boxed_ends", "arc_bulge_steps"):
        for budget in (0, 2_000, 20_000, math.inf):
            ok = validate(json.loads(json.dumps(rev[name])), budget=budget)[0] is not None
            assert ok or (name, budget) == ("tri_heavy_step", 0), (name, budget)
    for name in ("arc_5760", "path_arc_tiny_chord"):  # A whole turn, or ends 1e-12 apart: the outline is the circle.
        rscene, _ = validate(json.loads(json.dumps(rev[name])))
        _TLS.work = _Work()
        x0, y0, x1, y1 = _sup_box(_part_sup(rscene["parts"][0]))
        _TLS.work = None
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1))
        _trace(cr, rscene["parts"][0])
        d0, e0, d1, e1 = cr.path_extents()  # What Cairo draws: the whole circle in both scenes.
        assert d1 - d0 > 79 and x0 <= d0 + 1e-6 and y0 <= e0 + 1e-6, (name, x0, d0)
        assert x1 >= d1 - 1e-6 and y1 >= e1 - 1e-6, (name, x1, d1)
        assert x1 - x0 < 1.05 * (d1 - d0) and y1 - y0 < 1.05 * (e1 - e0), (name, x0, x1, d0, d1)
    for d in ("M 10 10 A 1 1e-150 0 0 0 10.000000000001 10", "M 10 10 A 1e-160 5 30 1 0 10.000000000001 10",
              "M 10 10 A 1e-160 1e-3 0 0 1 90 20"):  # Tiny or far-apart radii: a scene that draws, never a raise.
        tiny_arc, _ = validate({"view": [100, 100], "parts": [{"id": "p", "path": d}]})
        sample(tiny_arc)
    pivot, _ = validate(json.loads(json.dumps(rev["rotate_no_about_flip"])))  # A rotate without about turns as main.
    assert pivot["steps"][0]["parts"][0]["pose"][2] == _centre(_extent([pivot["parts"][0]])), pivot["steps"][0]
    # Run the budget out on purpose: every share ends at its stop, the links left go straight, the scene still draws.
    for budget in (2_000, 20_000):
        out_scene, out_errs = validate(json.loads(json.dumps(rev["hub_custom16_steps"])), budget=budget)
        work = _TLS.last_work
        assert not out_errs and work.ran_out and work.used <= budget, (budget, out_errs, work.used)
        for k in range(len(out_scene["steps"])):
            sample(out_scene, step=k)
    tiny, _ = validate(json.loads(json.dumps(rev["hub_custom16_steps"])), budget=2_000)
    assert all(p["bend"] == 0 for st in [{"parts": tiny["parts"]}] + tiny["steps"] for p in st["parts"]
               if p.get("link")), "an out-of-budget link must go straight"
    # Regression (link-free parity): arc and curved path without links keep main's exact _extent pivots and edge check.
    arc_sc, arc_err = validate({"view": [120, 120], "parts": [{"id": "a", "arc": [60, 60, 40, 0, 90]}],
                                "steps": [{"light": ["a"], "move": {"a": {"rotate": 45}}}]})
    assert not arc_err and arc_sc["steps"][0]["parts"][0]["pose"][2] == (60.0, 60.0), arc_sc
    arc_oob, arc_oob_err = validate({"view": [100, 100], "parts": [{"id": "a", "arc": [50, 50, 45, 0, 90]}],
                                     "steps": [{"light": ["a"], "move": {"a": {"to": [10, 0]}}}]})
    assert arc_oob is None and any("past the view's edge" in e for e in arc_oob_err), arc_oob_err
    # Two-thread Cairo/Pango safety check in a child process so a C abort fails the check cleanly.
    import subprocess
    stress_src = (
        "import json, sys, threading; sys.path.insert(0, sys.argv[1]); import render, stencils\n"
        "names = list(stencils.STENCILS); errs = []\n"
        "def t_stencil():\n"
        "  try:\n"
        "    for i in range(2000):\n"
        "      render._STENCILS.pop(names[i % len(names)], None)\n"
        "      render._stencil(names[i % len(names)])\n"
        "  except Exception as e: errs.append(e)\n"
        "def t_validate():\n"
        "  docs = [render.LINK_FIXTURES['hub'], render.LINK_FIXTURES['curves'], render.LINK_FIXTURES['group']]\n"
        "  try:\n"
        "    for i in range(2000):\n"
        "      sc, err = render.validate(json.loads(json.dumps(docs[i % len(docs)])))\n"
        "      assert sc is not None and not err, err\n"
        "  except Exception as e: errs.append(e)\n"
        "t1, t2 = threading.Thread(target=t_stencil), threading.Thread(target=t_validate)\n"
        "t1.start(); t2.start(); t1.join(); t2.join()\n"
        "assert not errs, errs\n"
    )
    proc = subprocess.run([sys.executable, "-c", stress_src, os.path.dirname(os.path.abspath(__file__))],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"2-thread stress failed (rc={proc.returncode}): {proc.stderr}"
    print("2-thread stencil+validate stress (2000 rounds): ok")
    # Min-link layout checks: symmetric hub stays level, dense hub clears 48 px, cramped row stays fast, and
    # compound named pose pivots resolve from post-fit positions (not pre-fit).
    hub_sc, _ = validate(json.loads(json.dumps(LINK_FIXTURES["hub"])))
    hub_pos = {p["id"]: _apply(p["copies"][0], 0.0, 0.0) for p in hub_sc["parts"] if not p.get("link")}
    assert abs(hub_pos["phone"][1] - hub_pos["work"][1]) < 0.1, (hub_pos["phone"], hub_pos["work"])
    assert abs(hub_pos["clock"][1] - hub_pos["mail"][1]) < 0.1, (hub_pos["clock"], hub_pos["mail"])
    dense_hub = {"title": "Dense hub", "layout": "hub", "nodes": [
        {"id": "c", "stencil": "chip", "label": "core"},
        *[{"id": f"n{k}", "stencil": "server", "label": f"node {k}"} for k in range(9)],
    ]}
    dh_scene, dh_errs = validate(dense_hub)
    dh_units = _TLS.last_work.used
    assert not dh_errs and not check_link_geometry(dh_scene), (dh_errs, check_link_geometry(dh_scene))
    assert not _TLS.last_work.ran_out, dh_units
    cramped = {"title": "Cramped row", "layout": "row", "nodes": [
        {"id": f"r{k}", "label": "long label text here 123"} for k in range(12)],
    }
    cr_scene, cr_errs = validate(cramped)
    cr_units = _TLS.last_work.used
    assert not cr_errs and not check_link_geometry(cr_scene, min_body_px=0), (cr_errs, check_link_geometry(cr_scene, min_body_px=0))
    assert cr_units <= WORK_BUDGET, cr_units
    cyc_eng, cyc_err = validate({
        "layout": "cycle",
        "nodes": [{"id": "e", "stencil": "engine"},
                  *[{"id": f"n{k}", "stencil": "server", "label": f"node {k}"} for k in range(5)]],
        "steps": [{"light": ["e.piston"], "move": {"e": "intake"}}],
    })
    assert not cyc_err, cyc_err
    crank_base = next(p for p in cyc_eng["parts"] if p["id"] == "e.crank")
    crank_origin = list(_apply(crank_base["copies"][0], 0.0, 0.0))
    crank_about = cyc_eng["steps"][0]["move"]["e.crank"]["about"]
    assert math.dist(crank_origin, crank_about) < 1e-6, (crank_origin, crank_about)
    for hdoc in (
        {"view": [100, 100], "parts": [{"id": "a", "circle": [50, 50, 10]}, {"id": "b", "circle": [50, 50, 10]},
                                       {"id": "l", "link": ["a", "b"]}]},
        {"view": [100, 100], "parts": [{"id": "a", "circle": [50, 50, 10]}, {"id": "l", "link": ["a", "a"]}]},
        {"layout": "hub", "nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}], "links": [["a", "a"]]},
        {"layout": "hub", "nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}], "links": [["a", "missing"]]},
        {"layout": "hub", "nodes": [{"id": f"n{k}", "label": f"n{k}"} for k in range(30)],
         "links": [[f"n{k % 30}", f"n{(k + 1) % 30}"] for k in range(100)]},
    ):
        hsc, herr = validate(hdoc)
        assert hsc is None and herr, (hdoc, hsc, herr)
        assert _TLS.last_work.used <= WORK_BUDGET
    print(f"min-link layout checks ok  units: dense_hub={dh_units}  cramped={cr_units}")
    print(f"{len(LINK_FIXTURES)} link geometry fixtures clean.")
    print(f"{len(BAD)} bad scenes refused with the right sentence.")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--check"]:
        _self_check(sys.argv[2] if len(sys.argv) > 2 else None)
    elif sys.argv[1:2] == ["--author"]:
        try:
            doc = json.load(sys.stdin)
        except ValueError as e:
            print(json.dumps({"ok": False, "errors": [f"The scene is not valid JSON: {e}."]}))
            sys.exit(1)
        print(json.dumps(check(doc, int(sys.argv[2]) if len(sys.argv) > 2 else None), indent=1))
    elif sys.argv[1:2] == ["--schema"]:
        print(json.dumps(SCHEMA, indent=1))
    else:
        print(__doc__)
