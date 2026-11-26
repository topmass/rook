"""Data-driven Devs theme pack loader and 3D particle form registry.

Loads palette, grain look, role assignments, and per-form motion parameters from
``themes/devs/manifest.json``, and registers clean edge-weighted 3D point sets
and motion evaluators for all upgraded and new Round-2 forms.
"""

from __future__ import annotations

import json
import math
import os
import random

_HERE = os.path.dirname(os.path.abspath(__file__))
_MANIFEST_PATH = os.path.normpath(os.path.join(_HERE, "..", "themes", "devs", "manifest.json"))


def load_pack(path: str = _MANIFEST_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


PACK = load_pack()
LOOK = PACK["look"]
ICONS = PACK.get("icons", {})
STATES = PACK.get("states", {})
FORMS_META = PACK["forms"]
THINK_ANCHOR = STATES.get("thinking", {}).get("rook", "rook")
THINK_OTHERS = tuple(
    (spec.get("form") or name)
    for name, spec in ICONS.items()
    if spec.get("think") and name != THINK_ANCHOR
)


def _by_angle(points):
    return sorted(points, key=lambda p: math.atan2(p[1], p[0]))


def _depth_shade(z2: float, z_span: float = 46.0):
    """Map rotated view-space Z to (brightness, z_norm in [-1, 1]) with crisp 4.6x 3D depth contrast."""
    zn = max(-1.0, min(1.0, z2 / z_span))
    d = 0.5 + 0.5 * zn
    # Far grains sit cleanly at 0.30x while near grains climb to 1.38x (4.6x near-to-far contrast).
    return 0.30 + 1.08 * (d ** 1.25), zn


def _rot_yx(x: float, y: float, z: float, cy: float, sy: float, cp: float, sp: float):
    x1 = x * cy + z * sy
    z1 = z * cy - x * sy
    y2 = y * cp - z1 * sp
    z2 = y * sp + z1 * cp
    return x1, y2, z2


def _edge_line(pts, a, b, count, rng, jitter=0.35):
    ax, ay, az = a
    bx, by, bz = b
    for k in range(count):
        u = (k + 0.5 + rng.uniform(-0.22, 0.22)) / count
        pts.append((
            ax + (bx - ax) * u + rng.gauss(0, jitter),
            ay + (by - ay) * u + rng.gauss(0, jitter),
            az + (bz - az) * u + rng.gauss(0, jitter),
        ))


# ---------------------------------------------------------------------------
# 3D point-set builders (all edge/silhouette-weighted, exact GRAINS count)
# ---------------------------------------------------------------------------

def build_helix_3d(grains: int, rng: random.Random):
    """True 3D double helix: two glowing golden strands (1.05 turns) with grains riding them + 10 crisp rungs."""
    pts = []
    strand_n = 468
    rung_count = 10
    # Two bold, tightly packed helical strands (234 grains each) riding directly on the glowing gold strands.
    for n in range(strand_n):
        u = -1.0 + 2.0 * (n // 2 + rng.random()) / (strand_n // 2)
        turn = (n % 2) * math.pi
        oy, oz = rng.gauss(0, 0.32), rng.gauss(0, 0.32)
        lag = int(abs(u) * 8)
        pts.append((68.0 * u, 24.0 * math.sin(3.3 * u + turn), u, turn, None, oy, oz, lag))
    # 10 evenly spaced crisp vertical base-pair rungs bridging strand A to strand B.
    rem = grains - len(pts)
    for k in range(rem):
        rung = k % rung_count
        slot = k // rung_count
        per = max(1, (rem + rung_count - 1) // rung_count)
        u = 0.84 * (-1.0 + 2.0 * (rung + 0.5) / rung_count)
        v = -0.92 + 1.84 * (slot + 0.5) / per
        lag = int(abs(u) * 8)
        pts.append((68.0 * u, v * 24.0 * math.sin(3.3 * u), u, 0.0, v, 0.0, 0.0, lag))
    return _by_angle(pts[:grains])


def build_rook_even(grains: int, rng: random.Random):
    """Same iconic chess rook silhouette the owner loves, with an evenly luminous waist between base and crown."""
    sin, cos, tau = math.sin, math.cos, 2 * math.pi
    pts = []

    def ring(r, y, count, a0=0.0, a1=tau):
        for k in range(count):
            a = a0 + (a1 - a0) * (k + 0.5 + rng.uniform(-0.18, 0.18)) / count
            pts.append((r * cos(a), y + rng.gauss(0, 0.35), r * sin(a)))

    # Keep exact base, collar, head, and crown radii while adding three intermediate waist rings.
    rook_rings = (
        (36, 52, 42), (34, 43, 30), (26, 35, 24),
        (24, 24, 24), (22, 12, 24), (20, -1, 24), (19, -12, 24),
        (27, -20, 26), (31, -30, 32), (31, -40, 30),
    )
    for r, y, n in rook_rings:
        ring(r, y, n)

    profile = ((35, 26), (12, 22), (-16, 19), (-20, 27), (-25, 27), (-30, 31), (-40, 31))
    seg_len = [math.dist(a, b) for a, b in zip(profile, profile[1:])]
    total_len = sum(seg_len)
    meridians = 10
    per_mer = 16
    for m in range(meridians):
        a = tau * (m + 0.5) / meridians
        for k in range(per_mer):
            d = total_len * (k + 0.5 + rng.uniform(-0.2, 0.2)) / per_mer
            for (y0, r0), (y1, r1), step in zip(profile, profile[1:], seg_len):
                if d <= step:
                    f = d / step
                    r, y = r0 + (r1 - r0) * f, y0 + (y1 - y0) * f
                    pts.append((r * cos(a), y, r * sin(a)))
                    break
                d -= step

    # Crown merlons (exact 5 crenellations between radii 21 and 31, y -40..-54).
    merlons = 5
    span = tau / merlons
    for m in range(merlons):
        a0, a1 = span * m, span * m + span * 0.58
        ring(31, -54, 10, a0, a1)
        ring(21, -54, 6, a0, a1)
        for a in (a0, a1):
            for k in range(7):
                y = -40 + (-14) * (k + 0.5) / 7.0
                pts.append((31 * cos(a), y, 31 * sin(a)))
            for k in range(3):
                r = 21 + 10 * (k + 0.5) / 3.0
                pts.append((r * cos(a), -54, r * sin(a)))

    # Remaining grains dust the waist barrel evenly so the middle glows continuously.
    while len(pts) < grains:
        y = rng.uniform(-16, 34)
        r = 19.0 + (26.0 - 19.0) * (y + 16.0) / 50.0
        a = rng.uniform(0, tau)
        pts.append((r * cos(a), y, r * sin(a)))
    return _by_angle(pts[:grains])


def build_hourglass_3d(grains: int, rng: random.Random):
    """Crisp lathed 3D hourglass: clean glass ribs, double caps, sculpted 3D sand cones, falling trickle."""
    sin, cos, tau = math.sin, math.cos, 2 * math.pi
    pts = []

    def h_rad(y):
        p = min(1.0, abs(y) / 44.0)
        return 4.5 + 28.5 * p * p * (3.0 - 2.0 * p)

    def h_ring(r, y, count):
        for k in range(count):
            a = tau * (k + 0.5 + rng.uniform(-0.15, 0.15)) / count
            pts.append((r * cos(a), y + rng.gauss(0, 0.25), r * sin(a), None, 0.0))

    # Crisp top and bottom caps + mid-bulb latitude hoops + pinched waist ring.
    for sy in (-1.0, 1.0):
        h_ring(35.0, sy * 50.0, 46)
        h_ring(28.0, sy * 50.0, 22)
        h_ring(33.0, sy * 46.0, 28)
    h_ring(h_rad(25.0), -25.0, 36)
    h_ring(h_rad(25.0), 25.0, 36)
    h_ring(5.0, 0.0, 26)
    # Eight crisp curved meridian glass ribs (tight, no noise scatter).
    for m in range(8):
        a = tau * m / 8.0
        for k in range(24):
            y = -46.0 + 92.0 * (k + 0.5) / 24.0
            r = h_rad(y)
            pts.append((r * cos(a), y, r * sin(a), None, 0.0))
    # Sculpted 3D sand cones (balanced top/bottom weight; centered in cell).
    for r, y, c in ((18.0, -24.0, 26), (11.5, -16.0, 18), (5.5, -9.0, 12)):
        h_ring(r, y, c)
    for r, y, c in ((26.0, 44.0, 30), (18.0, 37.0, 22), (10.0, 31.0, 14), (4.0, 26.0, 10)):
        h_ring(r, y, c)
    trickle_n = max(36, grains - len(pts))
    for k in range(trickle_n):
        pts.append((0.0, 12.0, 0.0, (k + rng.random()) / trickle_n, rng.gauss(0, 0.65)))
    return _by_angle(pts[:grains])


# ---------------------------------------------------------------------------
# The two send forms, which sends take in turn: the turbine, a ducted rotor seen three-quarter on, and the array, a
# small box body whose two solar wings deploy. The grains first fly into the loop. Each part then leaves the loop from
# the stretch nearest where it lands, arrives, aligns and locks with a small overshoot. The strands fire from the
# ports, the form holds in motion while the fan shows, and as the fan leaves the form gathers into its centre, the
# strands drawing back into the ports with it. Times are seconds after the form began.
# ---------------------------------------------------------------------------

SEND_FORMS = ("send_turbine", "send_array")
SEND_MORPH = 0.6               # The loop starts to come apart.
SEND_LOCK = SEND_MORPH + 1.75  # Every part has arrived and locked.
SEND_FIRE = SEND_LOCK + 0.08   # The first strand leaves its port.
SEND_LOOP_FLOW = 2.0 * math.pi / 10.5  # The resting loop's flow, 2 pi / overlay.LOOP_PERIOD.
TURBINE_R = 38.0
TURBINE_VIEW = (0.62, -0.22)   # Yaw and pitch.
# Front and back casing rings, hub, spinner, ten vanes, then the nozzles at 3 and 9 o'clock.
TURBINE_ARRIVE = (0.0, 0.10, 0.20, 0.25, *(0.35 + 0.045 * k for k in range(10)), 0.70, 0.70)
ARRAY_SEG_W, ARRAY_SEG_H = 19.0, 28.0
ARRAY_VIEW = (0.34, -0.26)
# The body, then for the right wing and the left: its boom, inner panel, outer panel and tip emitter.
ARRAY_ARRIVE = (0.0, 0.15, 0.25, 0.35, 0.65, 0.15, 0.25, 0.35, 0.65)
_TAU = 2.0 * math.pi


def _ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1.0 - (1.0 - x) ** 3


def _ease_back(x, over=1.6):
    """Ease out with a small overshoot: the click of a part locking home."""
    x = min(1.0, max(0.0, x)) - 1.0
    return 1.0 + x * x * ((over + 1.0) * x + over)


def _send_points(name, grains, rng, parts):
    """Grain records (along, part, lag, kind, *geometry) from a list of parts, each a list of geometry tuples. Each
    grain keeps its own place on the resting loop (along), so it flies into the loop on its own side. Part by part, in
    the order they arrive, each landing place takes the free grain nearest it on the loop as that part leaves, so no
    part sweeps across the form."""
    along = []
    for n in range(grains):  # Each grain's place on the overlay's resting loop form.
        a = -math.pi + _TAU * (n + 0.5) / grains
        along.append(math.pi / 2 - a if abs(a) <= math.pi / 2 else math.pi / 2 + a)
    assert sum(map(len, parts)) == grains, sum(map(len, parts))
    arrive = TURBINE_ARRIVE if name == "send_turbine" else ARRAY_ARRIVE
    pts, free = [None] * grains, set(range(grains))
    for p in sorted(range(len(parts)), key=lambda q: arrive[q]):
        T = SEND_MORPH + arrive[p]
        place, _, m = _send_device(name, T + 0.55, 0.0, math.inf)  # Where the part lands, before it aligns.
        ox, oy = _send_centre(name, T + 0.55)
        flow = T * SEND_LOOP_FLOW
        loop = {i: (60.0 * math.sin(along[i] + flow), 26.0 * math.sin(2.0 * (along[i] + flow))) for i in free}
        recs = [(0.0, p, 0.0, *g) for g in parts[p]]
        pairs = []
        for k, rec in enumerate(recs):
            x, y, z, _ = place(rec)
            q = 1.0 / (1.0 - (m[6] * x + m[7] * y + m[8] * z) / 320.0)
            gx, gy = (m[0] * x + m[1] * y + m[2] * z) * q - ox, (m[3] * x + m[4] * y + m[5] * z) * q - oy
            pairs += [((gx - lx) ** 2 + (gy - ly) ** 2, k, i) for i, (lx, ly) in loop.items()]
        pairs.sort()
        for _, k, i in pairs:
            if pts[i] is None and recs[k] is not None:
                pts[i], recs[k] = (along[i], p, rng.random(), *parts[p][k]), None
                free.discard(i)
    return pts


def _turbine_parts():
    """Ducted rotor. Rotor parts are (0, r0, r1, a0, a1, spins, z0, z1, glow): radius r0 + r1 * align, angle
    a0 + a1 * align (+ the spin), depth z0 + z1 * align. Nozzle parts are (1, x0, x1, y, z): x is x0 + x1 * align."""
    R = TURBINE_R

    def ring(z0, r, n):
        return [(0, 0.4 * r, 0.6 * r, _TAU * (k + 0.5) / n, 0.0, 0.0, z0, 0.0, 0.85) for k in range(n)]

    spinner = []
    for k in range(32):
        line, f = divmod((k + 0.5) / 32 * 4.0, 1.0)
        spinner.append((0, 8.0 * (1.0 - f), 0.0, _TAU * line / 4.0, 0.0, 1.0, 9.0, 7.0 * f, 1.0))
    parts = [ring(7.0, R, 116), ring(-7.0, R, 84), ring(9.0, 8.0, 40), spinner]
    for v in range(10):
        parts.append([(0, 9.0, (R - 11.0) * u, _TAU * v / 10.0, 0.7 * u, 1.0, 5.0 - 6.0 * u, 0.0, 0.9 + 0.2 * u)
                      for u in ((k + 0.5) / 26 for k in range(26))])
    for side in (1, -1):
        nozzle = []
        for k in range(54):  # The root ring, the mouth ring, and four rails between them.
            ring_i, f = divmod((k + 0.5) / 54 * 3.0, 1.0)
            if ring_i < 2:
                a, q = _TAU * f, ring_i
            else:
                rail, q = divmod(f * 4.0, 1.0)
                a = _TAU * (rail / 4.0 + 0.125)
            nozzle.append((1, side * R, side * 14.0 * q, 4.2 * math.cos(a), 4.2 * math.sin(a)))
        parts.append(nozzle)
    return parts


def build_send_turbine_3d(grains: int, rng: random.Random):
    return _send_points("send_turbine", grains, rng, _turbine_parts())


def _array_parts():
    """Deploying solar array. Fixed parts are (0, x, y, z, glow); wing panels (1, side, panel, u, v) in panel space;
    tip emitters (2, side, cos, sin) round the wing tip."""
    W, H = ARRAY_SEG_W, ARRAY_SEG_H
    corners = [(sx * 8.0, sy * 10.0, sz * 6.0) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    edges = [(a, b) for a in range(8) for b in range(a + 1, 8)
             if sum(1 for i in range(3) if corners[a][i] != corners[b][i]) == 1]
    body = []
    for k in range(128):
        e, f = divmod((k + 0.5) / 128 * 12.0, 1.0)
        a, b = corners[edges[int(e)][0]], corners[edges[int(e)][1]]
        body.append((0, *(p + (q - p) * f for p, q in zip(a, b)), 0.95))
    parts = [body]
    total = 4 * W + 2 * H  # Each panel: its outline and two dividers, walked at even spacing.
    for side in (1, -1):
        parts.append([(0, side * (8.0 + 6.0 * (k + 0.5) / 12), 0.0, 0.0, 0.9) for k in range(12)])
        for panel in (1, 2):
            seg = []
            for k in range(112):
                s = (k + 0.5) / 112 * total
                if s < W:
                    lu, lv = s, -H / 2
                elif s < W + H:
                    lu, lv = W, -H / 2 + (s - W)
                elif s < 2 * W + H:
                    lu, lv = W - (s - W - H), H / 2
                elif s < 2 * W + 2 * H:
                    lu, lv = 0.0, H / 2 - (s - 2 * W - H)
                elif s < 3 * W + 2 * H:
                    lu, lv = s - 2 * W - 2 * H, -H / 6
                else:
                    lu, lv = s - 3 * W - 2 * H, H / 6
                seg.append((1, side, panel, lu, lv))
            parts.append(seg)
        parts.append([(2, side, math.cos(_TAU * (k + 0.5) / 20), math.sin(_TAU * (k + 0.5) / 20)) for k in range(20)])
    return parts


def build_send_array_3d(grains: int, rng: random.Random):
    return _send_points("send_array", grains, rng, _array_parts())


_SEND_PARTS = {"send_turbine": _turbine_parts, "send_array": _array_parts}
_SEND_CENTRE = {}  # Per form: its geometry records, and the last (T, persp) with the device's centre then.


def _send_centre(name, T, persp=320.0):
    """The device's own centre at time T: the mean of every part's place, projected, as if all had arrived. Taking it
    off keeps the device on the presence's centre as it unfurls (folded wings and perspective pull it aside)."""
    recs, last = _SEND_CENTRE.get(name, (None, None))
    if recs is None:
        recs = [(0.0, p, 0.0, *g) for p, part in enumerate(_SEND_PARTS[name]()) for g in part]
    if last is None or last[0] != (T, persp):
        place, _, m = _send_device(name, T, 0.0, math.inf)
        sx = sy = 0.0
        for rec in recs:
            x, y, z, _ = place(rec)
            q = 1.0 / (1.0 - (m[6] * x + m[7] * y + m[8] * z) / persp)
            sx += (m[0] * x + m[1] * y + m[2] * z) * q
            sy += (m[3] * x + m[4] * y + m[5] * z) * q
        last = ((T, persp), (sx / len(recs), sy / len(recs)))
        _SEND_CENTRE[name] = (recs, last)
    return last[1]


def _send_device(name, T, now, fire_at):
    """The form at time T: (place, arrive, m). place(record) gives a grain's (x, y, z, glow) in device space, and m is
    the frame's 3x3 matrix, row by row, from device space to view space: the array's rigid roll, then the view."""
    hold = max(0.0, T - SEND_LOCK)
    fire = math.exp(-3.0 * (now - fire_at)) if now >= fire_at else 0.0
    sin, cos = math.sin, math.cos
    if name == "send_turbine":
        align = [_ease_back((T - SEND_MORPH - a - 0.55) / 0.5) for a in TURBINE_ARRIVE]
        spin = 0.3 * T + 2.4 * hold - 2.0 * (1.0 - math.exp(-1.2 * hold))  # Spins up, then holds turning.
        nozzle_glow = 1.0 + 0.9 * fire

        def place(rec):
            al = align[rec[1]]
            if rec[3]:
                return rec[4] + rec[5] * al, rec[6], rec[7], nozzle_glow
            r, a = rec[4] + rec[5] * al, rec[6] + rec[7] * al + rec[8] * spin
            return r * cos(a), r * sin(a), rec[9] + rec[10] * al, rec[11]
        return place, TURBINE_ARRIVE, _send_matrix(TURBINE_VIEW, 0.0)

    align = [_ease_back((T - SEND_MORPH - a - 0.55) / 0.5) for a in ARRAY_ARRIVE]
    roll = 0.42 * sin(0.9 * hold) * min(1.0, hold * 1.5)  # A slow roll about the wing axis.
    a1 = (math.pi / 2) * (1.0 - _ease_back((T - SEND_MORPH - 0.85) / 0.4))  # The two hinges open in turn.
    a2 = -math.pi * (1.0 - _ease_back((T - SEND_MORPH - 1.2) / 0.5))  # The outer panel swings furthest: slower.
    ca1, sa1, ca12, sa12 = cos(a1), sin(a1), cos(a1 + a2), sin(a1 + a2)
    W = ARRAY_SEG_W
    panel_glow = 0.85 + 0.7 * math.exp(-((roll - 0.18) / 0.10) ** 2) * min(1.0, hold * 2.0)  # The glint.
    emit_glow = 1.1 + 0.9 * fire
    tip_x, tip_z = 14.0 + W * ca1 + W * ca12, -W * sa1 - W * sa12

    def place(rec):
        kind = rec[3]
        if kind == 0:
            return rec[4], rec[5], rec[6], rec[7]
        if kind == 1:
            side, lu = rec[4], rec[6]
            if rec[5] == 1:
                return side * (14.0 + lu * ca1), rec[7], -lu * sa1, panel_glow
            return side * (14.0 + W * ca1 + lu * ca12), rec[7], -W * sa1 - lu * sa12, panel_glow
        r = 3.4 * align[rec[1]]
        return rec[4] * (tip_x + 4.0), r * rec[5], tip_z + r * rec[6], emit_glow
    return place, ARRAY_ARRIVE, _send_matrix(ARRAY_VIEW, roll)


def _send_matrix(view, roll):
    """The view rotation (as _rot_yx) after a roll about the x axis, as nine numbers row by row."""
    cy, sy, cp, sp = math.cos(view[0]), math.sin(view[0]), math.cos(view[1]), math.sin(view[1])
    cr, sr = math.cos(roll), math.sin(roll)
    rows = ((cy, 0.0, sy), (sy * sp, cp, -cy * sp), (-sy * cp, sp, cy * cp))
    return tuple(v for a, b, c in rows for v in (a, b * cr + c * sr, c * cr - b * sr))


# A port record per side: the turbine's nozzle mouth centre, the array's emitter centre at the wing tip.
_SEND_PORTS = {"send_turbine": {1: (0.0, 14, 0.0, 1, TURBINE_R, 14.0, 0.0, 0.0),
                                -1: (0.0, 15, 0.0, 1, -TURBINE_R, -14.0, 0.0, 0.0)},
               "send_array": {1: (0.0, 4, 0.0, 2, 1, 0.0, 0.0), -1: (0.0, 8, 0.0, 2, -1, 0.0, 0.0)}}


def send_ports(name, T, gather: float = 0.0, persp: float = 320.0):
    """Where the strands leave a send form at time T, in form units before the fan's y offset: {1: right, -1: left}.
    As the form gathers into its centre (gather 0 to 1), the ports ease in to the centre."""
    place, _, m = _send_device(name, T, 0.0, math.inf)
    keep = 1.0 - _ease_out(gather)
    ox, oy = _send_centre(name, T, persp)
    out = {}
    for side, rec in _SEND_PORTS[name].items():
        x, y, z, _ = place(rec)
        p = 1.0 / (1.0 - (m[6] * x + m[7] * y + m[8] * z) / persp)
        out[side] = (((m[0] * x + m[1] * y + m[2] * z) * p - ox) * keep,
                     ((m[3] * x + m[4] * y + m[5] * z) * p - oy) * keep)
    return out


def eval_send_tech(name, points, now: float, form_at: float, fire_at: float, gather: float = 0.0,
                   persp: float = 320.0, y_off: float = 0.0):
    """Evaluate (tx, ty, tb, tz) for a send form. fire_at is when the first strand leaves; gather is how far the form
    has gathered into its centre as the fan leaves, 0 to 1."""
    T = now - form_at
    place, arrive, (m0, m1, m2, m3, m4, m5, m6, m7, m8) = _send_device(name, T, now, fire_at)
    sin, cos = math.sin, math.cos
    inv = 1.0 / persp
    late = T - SEND_MORPH
    formed = late > max(arrive) + 0.75  # Every grain has arrived: no loop to blend with.
    ox, oy = _send_centre(name, T, persp)
    flow = T * SEND_LOOP_FLOW  # The loop's phase counts from the form's start, as _send_points matched it.
    tx, ty, tb, tz = [], [], [], []
    for rec in points:
        if formed:
            k = 1.0
        else:
            d = rec[2]
            k = (late - arrive[rec[1]] - d * 0.2) / 0.55  # _ease_out, inline.
            k = 0.0 if k <= 0.0 else 1.0 if k >= 1.0 else 1.0 - (1.0 - k) ** 3
        if k > 0.0:
            x, y, z, glow = place(rec)
            z2 = m6 * x + m7 * y + m8 * z
            p = 1.0 / (1.0 - z2 * inv)
            gx, gy = (m0 * x + m1 * y + m2 * z) * p - ox, (m3 * x + m4 * y + m5 * z) * p - oy
            zn = z2 / 46.0  # _depth_shade(z2, 46.0), inline.
            zn = -1.0 if zn < -1.0 else 1.0 if zn > 1.0 else zn
            b = (0.30 + 1.08 * (0.5 + 0.5 * zn) ** 1.25) * glow
        if k < 1.0:
            a = rec[0] + flow
            sa, ca = sin(a), cos(a)
            lx, ly, lb = 60.0 * sa, 52.0 * sa * ca, 0.55 + 0.225 * (ca + 1.0)
            if k <= 0.0:
                gx, gy, b, zn = lx, ly, lb, 0.0
            else:
                swirl = sin(math.pi * k) * 7.0 * (d - 0.5)
                gx, gy, b, zn = lx + (gx - lx) * k, ly + (gy - ly) * k + swirl, lb + (b - lb) * k, zn * k
        if gather > 0.0:  # Into a small turning knot at the centre, the outer grains a beat behind.
            g = _ease_out(gather * 2.2 - (1.0 - rec[2]) * 0.6)
            a = rec[0] + 2.0 * T
            gx += (5.0 * sin(3.0 * a) - gx) * g
            gy += (4.0 * cos(5.0 * a) - gy) * g
            zn *= 1.0 - g
        tx.append(gx)
        ty.append(y_off + gy)
        tb.append(b)
        tz.append(zn)
    return tx, ty, tb, tz


def build_rows_3d(grains: int, rng: random.Random):
    """Tilted 3D holographic manuscript tablet: glowing corner brackets + 4 crisp lines of luminous script."""
    pts = []
    # Crisp 3D tablet corner brackets (4 corners * 2 arms * 14 grains = 112) + subtle top/bottom edge rail.
    w, h = 62.0, 40.0
    arm = 16.0
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            cx, cy = sx * w, sy * h
            for k in range(14):
                u = (k + 0.5) / 14.0
                pts.append((cx - sx * arm * u, cy, 0.0, -1.0, -1))
                pts.append((cx, cy - sy * arm * u, 0.0, -1.0, -1))
    # Back ghost tablet frame offset slightly in Z (-8 px) for instant 3D parallax (48 grains).
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            cx, cy = sx * w, sy * h
            for k in range(6):
                u = (k + 0.5) / 6.0
                pts.append((cx - sx * 12.0 * u, cy, -8.0, -1.0, -1))
                pts.append((cx, cy - sy * 12.0 * u, -8.0, -1.0, -1))
    # Four crisp horizontal script lines (tight y spread, clean word gaps, left-to-right arrival, full golden body).
    line_pts = []
    for row, y in enumerate((-24.0, -8.0, 8.0, 24.0)):
        x = -50.0 + rng.uniform(0, 2.5)
        while x < 45.0:
            length = min(rng.uniform(12.0, 26.0), 50.0 - x)
            cnt = max(10, int(length * 2.9))
            for k in range(cnt):
                px = x + length * (k + 0.5 + rng.uniform(-0.18, 0.18)) / cnt
                written = row * 0.65 + (px + 52.0) / 104.0 * 0.65
                line_pts.append((px, y + rng.gauss(0, 0.65), 3.0, written, row))
            x += length + rng.uniform(5.5, 8.0)
    rng.shuffle(line_pts)
    need = grains - len(pts)
    if len(line_pts) < need:
        line_pts = (line_pts * (need // len(line_pts) + 1))
    pts.extend(line_pts[:need])
    return _by_angle(pts[:grains])


# ---------------------------------------------------------------------------
# Four new 3D thinking forms (each built to match rook & lattice)
# ---------------------------------------------------------------------------

def build_prism_3d(grains: int, rng: random.Random):
    """Faceted 3D bipyramid crystal octahedron with nested inner crystal core and equatorial jewel ring."""
    pts = []
    top = (0.0, -52.0, 0.0)
    bot = (0.0, 52.0, 0.0)
    eq = ((42.0, 0.0, 0.0), (0.0, 0.0, 42.0), (-42.0, 0.0, 0.0), (0.0, 0.0, -42.0))
    # 8 outer sloping pyramid edges (34 grains each = 272) + 4 equatorial outer edges (26 each = 104).
    for v in eq:
        _edge_line(pts, top, v, 34, rng, 0.32)
        _edge_line(pts, bot, v, 34, rng, 0.32)
    for a, b in zip(eq, eq[1:] + eq[:1]):
        _edge_line(pts, a, b, 26, rng, 0.32)
    # Inner nested crystal octahedron (rotated 45 deg, 0.50x scale) for rich crystalline refraction (160 grains).
    itop = (0.0, -26.0, 0.0)
    ibot = (0.0, 26.0, 0.0)
    s = 20.5 / math.sqrt(2.0)
    ieq = ((s, 0.0, s), (-s, 0.0, s), (-s, 0.0, -s), (s, 0.0, -s))
    for v in ieq:
        _edge_line(pts, itop, v, 14, rng, 0.28)
        _edge_line(pts, ibot, v, 14, rng, 0.28)
    for a, b in zip(ieq, ieq[1:] + ieq[:1]):
        _edge_line(pts, a, b, 12, rng, 0.28)
    # Bright central vertical axis spine + glowing apex jewels (remaining grains).
    _edge_line(pts, itop, ibot, 24, rng, 0.28)
    while len(pts) < grains:
        v = rng.choice((top, bot, *eq))
        pts.append((v[0] + rng.gauss(0, 1.0), v[1] + rng.gauss(0, 1.0), v[2] + rng.gauss(0, 1.0)))
    return _by_angle(pts[:grains])


def build_astrolabe_3d(grains: int, rng: random.Random):
    """Three nested counter-turning 3D brass armillary rings around a luminous central quantum core."""
    tau = 2 * math.pi
    pts = []
    # Ring 0: outer gimbal (r=48, 200 grains); Ring 1: middle tilted ecliptic (r=38, 175 grains);
    # Ring 2: inner meridian (r=28, 145 grains); Core: glowing Fibonacci heart (r=9, 120 grains).
    for ring_id, r, count in ((0, 48.0, 200), (1, 38.0, 175), (2, 28.0, 145)):
        for k in range(count):
            a = tau * (k + 0.5 + rng.uniform(-0.14, 0.14)) / count
            w = (1.15 if k % 2 == 0 else -1.15) + rng.gauss(0, 0.22)
            pts.append((r * math.cos(a), r * math.sin(a), ring_id, a, r, w))
    golden = math.pi * (3.0 - math.sqrt(5.0))
    rem = grains - len(pts)
    for k in range(rem):
        y = 1.0 - 2.0 * (k + 0.5) / rem
        rr = math.sqrt(max(0.0, 1.0 - y * y))
        rad = 8.8 if k < rem * 0.7 else 4.4
        pts.append((rad * rr * math.cos(golden * k), rad * y, 3, golden * k, rad, rad * rr * math.sin(golden * k)))
    return _by_angle(pts[:grains])


def build_tesseract_3d(grains: int, rng: random.Random):
    """Sculptural 3D hypercube: crisp outer cube + nested inner cube linked by 8 diagonal corner struts."""
    pts = []
    corners_out = [(sx * 35.0, sy * 35.0, sz * 35.0) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    corners_in = [(sx * 17.5, sy * 17.5, sz * 17.5) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    edges = []
    for i in range(8):
        for j in range(i + 1, 8):
            if bin(i ^ j).count("1") == 1:
                edges.append((i, j))
    # 12 outer edges (26 grains each = 312).
    for i, j in edges:
        _edge_line(pts, corners_out[i], corners_out[j], 26, rng, 0.32)
    # 12 inner edges (14 grains each = 168).
    for i, j in edges:
        _edge_line(pts, corners_in[i], corners_in[j], 14, rng, 0.28)
    # 8 diagonal hypercube struts linking inner and outer corners (15 grains each = 120).
    for i in range(8):
        _edge_line(pts, corners_in[i], corners_out[i], 15, rng, 0.28)
    # Bright corner vertices (remaining 40 grains).
    while len(pts) < grains:
        v = rng.choice(corners_out if rng.random() < 0.6 else corners_in)
        pts.append((v[0] + rng.gauss(0, 0.85), v[1] + rng.gauss(0, 0.85), v[2] + rng.gauss(0, 0.85)))
    return _by_angle(pts[:grains])


def build_knot_3d(grains: int, rng: random.Random):
    """Sculpted 3D trefoil knot: crisp golden mathematical tube slowly turning in space."""
    sin, cos, tau = math.sin, math.cos, 2 * math.pi
    pts = []
    # Classic trefoil knot curve scaled to ~46 px radius, with tight slender tube cross-section (r=1.85).
    for k in range(grains):
        t = tau * (k + 0.5 + rng.uniform(-0.16, 0.16)) / grains
        x = 15.2 * (sin(t) + 2.0 * sin(2.0 * t))
        y = 15.2 * (cos(t) - 2.0 * cos(2.0 * t))
        z = -19.0 * sin(3.0 * t)
        dx = 15.2 * (cos(t) + 4.0 * cos(2.0 * t))
        dy = 15.2 * (-sin(t) + 4.0 * sin(2.0 * t))
        dz = -57.0 * cos(3.0 * t)
        tl = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        tx0, ty0, tz0 = dx / tl, dy / tl, dz / tl
        nx, ny = -ty0, tx0
        nl = math.hypot(nx, ny) or 1.0
        nx, ny = nx / nl, ny / nl
        bx, by, bz = -tz0 * ny, tz0 * nx, tx0 * ny - ty0 * nx
        phi = (0.0 if k % 2 == 0 else math.pi) + rng.gauss(0, 0.22) if rng.random() < 0.75 else rng.uniform(0, tau)
        rad = 1.85
        pts.append((
            x + rad * (nx * cos(phi) + bx * sin(phi)),
            y + rad * (ny * cos(phi) + by * sin(phi)),
            z + rad * (bz * sin(phi)),
        ))
    return _by_angle(pts[:grains])


# ---------------------------------------------------------------------------
# Meaningful motif: aperture (black-hole vortex)
# ---------------------------------------------------------------------------

def build_aperture_3d(grains: int, rng: random.Random):
    """Black-hole / accretion aperture motif (opening media or a panel): bright photon ring + 6 spiral arms."""
    tau = 2 * math.pi
    pts = []
    # 1) Razor-bright inner photon ring framing the dark event horizon (r=18 px, 170 grains).
    for k in range(170):
        a = tau * (k + rng.random()) / 170.0
        pts.append((18.0 * math.cos(a), 18.0 * math.sin(a), "ring", a, rng.gauss(0, 0.42), rng.gauss(0, 0.55)))
    # 2) Six logarithmic spiral accretion arms sweeping out from the photon ring (400 grains).
    arms = 6
    arm_n = 400
    for k in range(arm_n):
        arm = k % arms
        slot = k // arms
        per = max(1, (arm_n + arms - 1) // arms)
        u = (slot + rng.random()) / per
        a0 = tau * arm / arms
        pts.append((30.0 * math.cos(a0), 30.0 * math.sin(a0), "arm", a0, u, rng.gauss(0, 0.85)))
    # 3) Outer floating accretion embers (remaining 70 grains, tightened to r=35..51).
    rem = grains - len(pts)
    for k in range(rem):
        a = tau * (k + rng.random()) / rem
        r = rng.uniform(35.0, 51.0)
        pts.append((r * math.cos(a), r * math.sin(a), "ember", a, r, rng.uniform(-6.0, 6.0)))
    return _by_angle(pts[:grains])


def build_ear_3d(grains: int, rng: random.Random):
    """3D Sound-Wave Ripple Orb: 7 concentric acoustic rings radiating from the front listening pole back over a sphere."""
    sin, cos, tau = math.sin, math.cos, 2 * math.pi
    pts = []
    # Front focal pulse dot at the listening pole (0, 0, +44) — 44 grains.
    for k in range(44):
        a = tau * k / 44.0
        r = 5.5 * math.sqrt(rng.random())
        pts.append((r * cos(a), r * sin(a), 43.0 - 0.1 * r * r, "core", 0, a))
    # Seven concentric acoustic wave rings stepping back across a 44 px sphere (no spiderweb spokes!).
    ring_specs = (
        (16.0,  40.5, 56, 1),
        (28.0,  33.8, 76, 2),
        (37.5,  22.5, 92, 3),
        (43.2,   8.0, 104, 4),
        (43.0,  -9.0, 98, 5),
        (36.0, -24.5, 88, 6),
        (24.0, -36.5, 82, 7),
    )
    for r, z0, count, lag_idx in ring_specs:
        for k in range(count):
            a = tau * (k + 0.5 + rng.uniform(-0.18, 0.18)) / count
            pts.append((r * cos(a), r * sin(a), z0 + rng.gauss(0, 0.35), "wave", lag_idx, a))
    return _by_angle(pts[:grains])


# The writing pen: where its nib touches the paper, its lean from upright, and how the written line moves.
QUILL_TIP = (-6.0, 47.0)
QUILL_LEAN = math.radians(34.0)
QUILL_NIB, QUILL_GRIP, QUILL_GRIP_R = 60.0, 104.0, 10.5
QUILL_OMEGA, QUILL_PAPER, QUILL_SWING = 5.2, 26.0, 8.0  # Loop rate (rad/s), paper speed (px/s), loop width (px).
QUILL_HEIGHTS = (17.0, 9.0, 21.0, 11.0, 15.0, 8.0, 19.0, 12.0)  # Letter heights, so the line reads as script.
QUILL_LIFE, QUILL_SHOWN = 3.2, 0.86  # Seconds a grain of ink lives, and the share of it spent on the line.


def build_quill_3d(grains: int, rng: random.Random):
    """A fountain pen leaning on the paper: curved nib with slit and breather hole, a round grip, and ink grains."""
    sin, cos, tau = math.sin, math.cos, 2 * math.pi
    tip_x, tip_y = QUILL_TIP
    ax, ay = sin(QUILL_LEAN), -cos(QUILL_LEAN)
    px_, py_ = cos(QUILL_LEAN), sin(QUILL_LEAN)
    pts = []

    def pen(u, v, w, kind="pen"):
        pts.append((tip_x + u * px_ + v * ax, tip_y + u * py_ + v * ay, u, v, w, kind))

    def nib_w(v):
        return 11.0 * sin(0.5 * math.pi * v / 44.0) ** 0.85 if v < 44.0 else 11.0 - 1.5 * (v - 44.0) / 16.0

    def nib_z(u):
        return 4.2 - 0.035 * u * u  # The nib bows toward the viewer.

    # The nib's two edges, its slit, breather hole, shoulder line, and a bright point at the tip.
    for side in (-1.0, 1.0):
        for k in range(66):
            v = QUILL_NIB * (k + 0.5 + rng.uniform(-0.2, 0.2)) / 66
            u = side * nib_w(v)
            pen(u, v, nib_z(u) + rng.gauss(0, 0.2))
    for k in range(22):
        pen(rng.gauss(0, 0.2), 24.0 * (k + 0.5) / 22, nib_z(0.0))
    for k in range(18):
        a = tau * k / 18
        pen(2.6 * cos(a), 27.0 + 2.6 * sin(a), nib_z(0.0))
    for k in range(20):
        u = -9.0 + 18.0 * (k + 0.5) / 20
        pen(u, 44.0 - 5.0 * (1.0 - (u / 9.0) ** 2), nib_z(u))
    for k in range(10):
        pen(rng.gauss(0, 0.7), abs(rng.gauss(0, 0.9)), nib_z(0.0), "tip")
    # The round grip: three rings and six lines along it.
    for v, count in ((QUILL_NIB, 30), (QUILL_NIB + 6.0, 30), (QUILL_GRIP, 30)):
        for k in range(count):
            a = tau * (k + 0.5 + rng.uniform(-0.15, 0.15)) / count
            pen(QUILL_GRIP_R * cos(a), v, QUILL_GRIP_R * sin(a), "grip")
    for m in range(6):
        a = tau * (m + 0.5) / 6
        for k in range(14):
            v = QUILL_NIB + (QUILL_GRIP - QUILL_NIB) * (k + 0.5) / 14
            pen(QUILL_GRIP_R * cos(a), v, QUILL_GRIP_R * sin(a), "grip")
    # The rest are ink: each grain leaves the nib in turn and rides the written line away.
    ink = grains - len(pts)
    for k in range(ink):
        phase = (k + rng.random()) / ink
        pts.append((tip_x - 66.0 * phase, tip_y, phase, rng.gauss(0, 0.55), 0.0, "ink"))
    return _by_angle(pts[:grains])


# The listening ripples: a slowly turning gold ring of radius 40 px, as the old halo. While the voice is up, gold
# ripples are born just inside the rim and contract to a bright core at the centre, each turning against the last.
# Each of the RIPPLE_SLOTS slots has its own grains and carries one ripple at a time. A louder voice keeps more busy.
HALO_RING = 40.0
RIPPLE_SLOTS, RIPPLE_GRAINS, CORE_GRAINS = 6, 52, 36
RIPPLE_BIRTH, RIPPLE_END, CORE_R = 0.9 * HALO_RING, 5.0, 6.4


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def build_listen_ripples(grains: int, rng: random.Random):
    """The ring's grains are (x, y, None, angle, offset). A ripple grain is (x, y, slot, cos, sin, offset, lum): the
    cosine and sine of its angle on the ripple, its offset across it, and its brightness. The brightness makes two
    bright arcs on each ripple, so its turn shows. A core grain is (x, y, -1, cos, sin, reach): reach is its share
    of the core's radius. The first two values are where a ripple grain waits dark when not in use: on the ring, so
    forms change by angle. The core's grains always sit at the core."""
    sin, cos, tau = math.sin, math.cos, 2 * math.pi
    pts = []
    for s in range(RIPPLE_SLOTS):
        for k in range(RIPPLE_GRAINS):
            a = tau * (k + rng.uniform(-0.3, 0.3)) / RIPPLE_GRAINS + 2.4 * s
            ca, sa = cos(a), sin(a)
            pts.append((HALO_RING * ca, HALO_RING * sa, s, ca, sa, rng.gauss(0, 0.4), 0.8 + 0.3 * cos(2 * a)))
    for k in range(CORE_GRAINS):
        a = 2.39996 * k  # The golden angle spreads the core's grains evenly over its disc.
        pts.append((HALO_RING * cos(a), HALO_RING * sin(a), -1, cos(a), sin(a), math.sqrt((k + 0.5) / CORE_GRAINS)))
    ring = grains - len(pts)
    for k in range(ring):
        a = tau * (k + rng.random()) / ring
        pts.append((HALO_RING * cos(a), HALO_RING * sin(a), None, a, max(-1.5, min(1.5, rng.gauss(0, 0.7)))))
    return _by_angle(pts[:grains])


# ---------------------------------------------------------------------------
# Registry of Round-3 3D point builders and live motion evaluators
# (rook, lattice, and sphere keep their exact origin/main 3D point sets!)
# ---------------------------------------------------------------------------

BUILDERS = {
    "helix": build_helix_3d,
    "ear": build_ear_3d,
    "halo": build_listen_ripples,
    "hourglass": build_hourglass_3d,
    "send_turbine": build_send_turbine_3d,
    "send_array": build_send_array_3d,
    "rows": build_rows_3d,
    "prism": build_prism_3d,
    "astrolabe": build_astrolabe_3d,
    "tesseract": build_tesseract_3d,
    "aperture": build_aperture_3d,
    "quill": build_quill_3d,
}


def eval_helix_strands(scene, now: float, samples: int = 64):
    """Evaluate the two continuous 3D glowing gold backbone strands for helix (shared by Cairo and _DustGL).

    Returns a list of 2 strands, each a list of ``(x, y, z_norm, depth_bright, voice_lv, fade)`` tuples.
    Fades with the grains' arrival (``scene.helix_fade``), so the strands never show ahead of the grains.
    """
    form_fade = float(getattr(scene, "helix_fade", 0.0))
    if form_fade <= 0.01:
        return []
    meta = FORMS_META.get("helix") or {}
    sin, cos = math.sin, math.cos
    persp_d = float(meta.get("persp", 320.0))
    heard = scene.heard
    held = sum(heard) / len(heard)
    spin = now * float(meta.get("spin", 0.85))
    yaw = float(meta.get("yaw_base", 0.0)) + 0.10 * sin(now * 0.28)
    pitch = float(meta.get("pitch", 0.14))
    cy_r, sy_r, cp_r, sp_r = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
    twist = 0.048 * (1.0 + 0.12 * held)
    strands = []
    for turn in (0.0, math.pi):
        pts = []
        for k in range(samples):
            u = -1.0 + 2.0 * k / (samples - 1)
            x = 68.0 * u
            lag = int(abs(u) * 8)
            lv = heard[min(len(heard) - 1, lag)]
            end_taper = 1.0 - 0.28 * (u * u * u * u)
            r = (22.5 * end_taper) * (1.0 + 0.36 * lv * (0.45 + 0.55 * (1.0 - u * u)))
            ph = twist * x + spin + turn
            px, py, pz = x, r * sin(ph), r * cos(ph)
            x1, y2, z2 = _rot_yx(px, py, pz, cy_r, sy_r, cp_r, sp_r)
            p = 1.0 / (1.0 - z2 / persp_d)
            b_d, zn = _depth_shade(z2, 28.0)
            tip_fade = min(1.0, (1.0 - abs(u)) / 0.10)
            pts.append((x1 * p, y2 * p, zn, b_d, lv, form_fade * tip_fade))
        strands.append(pts)
    return strands


def eval_targets(name: str, points, scene, now: float):
    """Evaluate (tx, ty, tb, tz) for a data-driven 3D form, or return None to fall back."""
    meta = FORMS_META.get(name)
    if meta is None:
        return None
    sin, cos, pi = math.sin, math.cos, math.pi
    grains = len(points)
    persp_d = float(meta.get("persp", 320.0))

    if name == "helix":
        heard = scene.heard
        held = sum(heard) / len(heard)
        spin = now * float(meta.get("spin", 0.85))
        yaw = float(meta.get("yaw_base", 0.0)) + 0.10 * sin(now * 0.28)
        pitch = float(meta.get("pitch", 0.14))
        cy_r, sy_r, cp_r, sp_r = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
        twist = 0.048 * (1.0 + 0.12 * held)
        tx, ty, tb, tz = [0.0] * grains, [0.0] * grains, [1.0] * grains, [0.0] * grains
        for i, (x, _, u, turn, v, oy, oz, lag) in enumerate(points):
            lv = heard[lag]
            # Smooth wide cylinder (1.05 gentle turns, zero steep zigzag V-peaks), swelling gracefully to voice.
            end_taper = 1.0 - 0.28 * (u * u * u * u)
            r = (22.5 * end_taper) * (1.0 + 0.36 * lv * (0.45 + 0.55 * (1.0 - u * u)))
            ph = twist * x + spin + turn
            s, c = sin(ph), cos(ph)
            if v is None:
                px, py, pz = x, r * s + oy, r * c + oz
                boost = 1.04 + 0.28 * lv
            else:
                px, py, pz = x, v * r * s, v * r * c
                boost = 0.68 + 0.34 * lv
            x1, y2, z2 = _rot_yx(px, py, pz, cy_r, sy_r, cp_r, sp_r)
            p = 1.0 / (1.0 - z2 / persp_d)
            tx[i], ty[i] = x1 * p, y2 * p
            b_d, zn = _depth_shade(z2, 28.0)
            tb[i], tz[i] = b_d * boost, zn
        return tx, ty, tb, tz

    if name == "halo":
        # The voice envelope, on the frame's real dt: it rises within about 30 ms and falls at a steady 1.6 per
        # second, so the ripples clear about 0.5 s after the voice stops at any frame rate. The slow fall also
        # bridges the gaps between syllables and between the mic's 50 ms levels.
        dt = max(0.0, now - scene.ripple_at)
        level, env = scene.heard[0], scene.ripple_env
        env = env + (level - env) * (1.0 - math.exp(-dt / 0.03)) if level > env else max(level, env - 1.6 * dt)
        scene.ripple_env, scene.ripple_at = env, now
        # A ripple is born at once when the voice starts, then about 1 a second at a murmur and 4 at full voice.
        # It takes a slot whose last ripple ended at least 0.4 s ago, so that slot's grains are back on the rim.
        if env < 0.05:
            scene.ripple_due = 1.0
        elif dt > 0.0:
            scene.ripple_due += dt * (0.6 + 3.4 * env * env)
            free = [r for r in scene.ripples if now - r[0] > r[2] + 0.4]
            if scene.ripple_due >= 1.0 and free:
                scene.ripple_due, scene.ripple_spin = 0.0, -scene.ripple_spin
                min(free, key=lambda r: r[0])[:] = [now, env, 1.2 - 0.4 * env, scene.ripple_spin]
        # Each live ripple contracts from just inside the rim to the core, easing in, and fades as it nears the core.
        # All of them dim with the envelope. tol is how far a grain may trail its moving place and still light.
        live = _smooth((env - 0.03) / 0.3)
        spin = float(meta.get("spin", 0.8))
        waves = []
        for start, loud, life, turn in scene.ripples:
            age = now - start
            if age >= life:
                waves.append(None)
                continue
            s = age / life
            r = RIPPLE_BIRTH - (RIPPLE_BIRTH - RIPPLE_END) * s * s
            glow = (0.8 + 0.6 * loud) * live * _smooth(age / 0.18) * _smooth((r - RIPPLE_END) / 12.0)
            a, speed = turn * spin * age, 2.0 * (RIPPLE_BIRTH - RIPPLE_END) * s / life + spin * r
            waves.append((r, cos(a), sin(a), glow, 3.0 + 0.16 * speed))
        # The core never goes out: in silence it rests as a dim dot, 0.8 times its base size at 28 percent of its
        # full-voice glow, and it eases back there on the envelope's release.
        core_r, core_glow = CORE_R * (0.8 + 0.2 * live + 0.35 * env), 0.45 + (0.55 + 0.6 * env) * live
        # The rim turns once in about 25 s, and up to a third faster with the voice. It turns on the real dt, capped
        # so a long gap does not jump it. Three soft glints orbit at 2.5 times the rim's speed, so the turn shows.
        scene.ring_turn += min(dt, 0.1) * float(meta.get("rim_spin", 0.25)) * (1.0 + 0.35 * env)
        turn, glint = scene.ring_turn, 7.5 * scene.ring_turn
        gc, gs = cos(glint), sin(glint)
        ring_tb = 1.0 + 0.12 * env
        xs, ys = scene.x, scene.y
        tx, ty, tb, tz = [0.0] * grains, [0.0] * grains, [0.0] * grains, [0.0] * grains
        for i, p in enumerate(points):
            c = p[2]
            if c is None:
                r, ca, sa = HALO_RING + p[4], cos(p[3] + turn), sin(p[3] + turn)
                # w is cos(3 a - glint), from the grain's own cosine and sine; the sixth power narrows it to a glint.
                w = 0.5 + 0.5 * ((4 * ca * ca - 3) * ca * gc + (3 - 4 * sa * sa) * sa * gs)
                w *= w * w
                tx[i], ty[i], tb[i] = r * ca, r * sa, ring_tb * (0.8 + 0.8 * w * w)
                continue
            wave = waves[c] if c >= 0 else (core_r * p[5], 1.0, 0.0, core_glow, 3.0)
            if wave is None:
                tx[i], ty[i] = p[0], p[1]  # A grain not in use waits dark on the rim.
                continue
            r, ca, sa, glow, tol = wave
            if c >= 0:
                r += p[5]
            gx, gy = r * (p[3] * ca - p[4] * sa), r * (p[4] * ca + p[3] * sa)
            tx[i], ty[i] = gx, gy
            # A grain lights only near its place, so none streaks across the ring on its way there.
            near = 1.0 - max(0.0, abs(xs[i] - gx) + abs(ys[i] - gy) - tol) / 6.0
            if glow > 0.0 and near > 0.0:
                tb[i] = glow * near * (p[6] if c >= 0 else 1.0)
        return tx, ty, tb, tz

    if name == "ear":
        heard = scene.heard
        a = now * float(meta.get("spin", 0.36))
        tilt = float(meta.get("tilt", 0.24))
        # Gentle oblique gaze (+/- 26 deg) so concentric 3D sound-wave rings pulse cleanly from front to back.
        yaw = 0.45 * sin(a) + 0.22
        pitch = tilt + 0.10 * cos(a)
        cy_r, sy_r, cp_r, sp_r = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
        tx, ty, tb, tz = [], [], [], []
        for x, y, z, kind, lag, ang in points:
            lv = heard[min(len(heard) - 1, lag * 3)]
            if kind == "core":
                swell = 1.0 + 0.35 * heard[0]
                px, py, pz = x * swell, y * swell, z + 3.0 * heard[0]
                boost = 1.32 + 0.25 * heard[0]
            else:
                swell = 1.0 + 0.18 * lv
                px, py, pz = x * swell, y * swell, z + 4.5 * lv
                boost = 0.96 + 0.32 * lv
            x1, y2, z2 = _rot_yx(px, py, pz, cy_r, sy_r, cp_r, sp_r)
            p = 1.0 / (1.0 - z2 / persp_d)
            tx.append(x1 * p)
            ty.append(y2 * p)
            b_d, zn = _depth_shade(z2, 46.0)
            tb.append(b_d * boost)
            tz.append(zn)
        return tx, ty, tb, tz

    if name in ("prism", "tesseract"):
        a = now * float(meta.get("spin", 0.42))
        tilt = float(meta.get("tilt", 0.32))
        ca, sa, ct, st = cos(a), sin(a), cos(tilt), sin(tilt)
        tx, ty, tb, tz = [], [], [], []
        for x, y, z in points:
            x1, y2, z2 = _rot_yx(x, y, z, ca, sa, ct, st)
            p = 1.0 / (1.0 - z2 / persp_d)
            tx.append(x1 * p)
            ty.append(y2 * p)
            b_d, zn = _depth_shade(z2, 46.0)
            tb.append(b_d * 1.02)
            tz.append(zn)
        return tx, ty, tb, tz

    if name == "astrolabe":
        s0 = now * float(meta.get("spin", 0.50))
        tilt = float(meta.get("tilt", 0.34))
        c_t, s_t = cos(tilt), sin(tilt)
        tx, ty, tb, tz = [], [], [], []
        for _, _, ring_id, a, r, w in points:
            if ring_id == 0:
                # Outer ring turns slowly around Y.
                px, py, pz = r * cos(a), r * sin(a), w
                x1, y2, z2 = _rot_yx(px, py, pz, cos(s0 * 0.7), sin(s0 * 0.7), c_t, s_t)
                boost = 1.0
            elif ring_id == 1:
                # Middle ring tilts and precesses oppositely.
                px, py, pz = r * cos(a), w, r * sin(a)
                x1, y2, z2 = _rot_yx(px, py, pz, cos(-s0 * 1.05), sin(-s0 * 1.05), cos(0.75 + 0.25 * sin(s0)), sin(0.75 + 0.25 * sin(s0)))
                boost = 0.96
            elif ring_id == 2:
                # Inner gimbal spins faster around a skewed diagonal axis.
                px, py, pz = w, r * cos(a), r * sin(a)
                x1, y2, z2 = _rot_yx(px, py, pz, cos(s0 * 1.45), sin(s0 * 1.45), cos(0.45), sin(0.45))
                boost = 0.98
            else:
                # Bright pulsing central quantum core.
                pulse = 1.0 + 0.10 * sin(now * 2.4)
                px = r * cos(a) * pulse
                py = points[len(tx)][1] * pulse
                pz = w * pulse
                x1, y2, z2 = _rot_yx(px, py, pz, cos(-s0), sin(-s0), c_t, s_t)
                boost = 1.30
            p = 1.0 / (1.0 - z2 / persp_d)
            tx.append(x1 * p)
            ty.append(y2 * p)
            b_d, zn = _depth_shade(z2, 48.0)
            tb.append(b_d * boost)
            tz.append(zn)
        return tx, ty, tb, tz

    if name in SEND_FORMS:
        fire_at, gather = scene.send_clock(now) if hasattr(scene, "send_clock") else (scene.form_at + SEND_FIRE, 0.0)
        y_off = scene.dispatch_y_offset() if hasattr(scene, "dispatch_y_offset") else 0.0
        return eval_send_tech(name, points, now, scene.form_at, fire_at, gather, persp_d, y_off)

    if name == "rows":
        elapsed = now - scene.state_at if scene.state == "transcribing" else 99.0
        row = min(3, int(elapsed / 0.65))
        pen = -50.0 + 100.0 * min(1.0, max(0.0, elapsed / 0.65 - row))
        rows_y = (-24.0, -8.0, 8.0, 24.0)
        yaw = float(meta.get("yaw_base", -0.18)) + 0.08 * sin(now * 0.40)
        pitch = float(meta.get("pitch", 0.20))
        ca, sa, ct, st = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
        tx, ty, tb, tz = [], [], [], []
        for x, y, z, written, r in points:
            if written < 0.0:
                px, py, pz, boost = x, y, z, (1.02 if z >= 0 else 0.56)
            elif written <= elapsed:
                px, py, pz, boost = x, y, z, 1.18
            else:
                u = written * 37.0 % 1.0
                px = min(52.0, pen + 2.0 + 20.0 * u)
                py = rows_y[row] + (y - rows_y[r]) * (0.5 + 1.1 * u)
                pz = 4.0
                boost = 1.20 - 0.55 * u
            x1, y2, z2 = _rot_yx(px, py, pz, ca, sa, ct, st)
            p = 1.0 / (1.0 - z2 / persp_d)
            tx.append(x1 * p - 2.0)
            ty.append(y2 * p + 1.5)
            b_d, zn = _depth_shade(z2, 42.0)
            tb.append(b_d * boost)
            tz.append(zn)
        return tx, ty, tb, tz

    if name == "hourglass":
        d = max(0.0, now - scene.form_at)
        arrive = max(0.0, 1.0 - d)

        def ease(u, a0, b0):
            q = min(1.0, max(0.0, (u - a0) / (b0 - a0)))
            return q * q * (3.0 - 2.0 * q)

        tx, ty, tb, tz = [0.0] * grains, [0.0] * grains, [1.0] * grains, [0.0] * grains
        spin = float(meta.get("spin", 0.36))
        tilt = float(meta.get("tilt", 0.32))
        a = d * spin + 0.45
        ca, sa, ct, st = cos(a), sin(a), cos(tilt), sin(tilt)

        hidden = 0.25
        for i, (px, py, pz, phase, side) in enumerate(points):
            if phase is None:
                x1, y2, z2 = _rot_yx(px, py, pz, ca, sa, ct, st)
                p = 1.0 / (1.0 - z2 / persp_d)
                tx[i], ty[i] = x1 * p, y2 * p - 3.0
                tb[i], tz[i] = _depth_shade(z2, 44.0)
            else:
                c = (phase + d / 1.3) % 1.0
                if c < hidden:
                    x1, y2, z2 = _rot_yx(side, -3.0 - 3.0 * (phase * 37 % 1), 0.0, ca, sa, ct, st)
                    tx[i], ty[i], tb[i] = x1, y2 - 3.0, arrive
                    _, tz[i] = _depth_shade(z2, 44.0)
                else:
                    u = (c - hidden) / (1.0 - hidden)
                    fx, fy, fz = side * (0.35 + 0.75 * u), -3.0 + 30.0 * u * u, 0.7 * sin(phase * 19.0 + u * 4.0)
                    x1, y2, z2 = _rot_yx(fx, fy, fz, 1.0, 0.0, ct, st)
                    p = 1.0 / (1.0 - z2 / persp_d)
                    tx[i], ty[i] = x1 * p, y2 * p - 3.0
                    look = ease(u, 0.0, 0.15) * (1.0 - ease(u, 0.80, 1.0))
                    tb[i] = arrive + (1.0 - arrive) * look * 1.35
                    _, tz[i] = _depth_shade(z2, 44.0)
        return tx, ty, tb, tz

    if name == "aperture":
        # Seamless 3.0-second loop: dark event horizon breathing open + glowing photon ring + 6 spiral accretion arms.
        loop_t = (now % 3.0) / 3.0
        spin_ang = loop_t * 2.0 * pi
        pitch = float(meta.get("pitch", 0.38)) + 0.06 * sin(spin_ang)
        yaw = 0.22 * cos(spin_ang)
        cy_r, sy_r, cp_r, sp_r = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
        open_breath = 1.0 + 0.09 * sin(spin_ang)
        tx, ty, tb, tz = [0.0] * grains, [0.0] * grains, [1.0] * grains, [0.0] * grains
        for i, (_, _, kind, a0, p_a, p_b) in enumerate(points):
            if kind == "ring":
                # Crisp bright inner photon ring framing the dark hole.
                a = a0 + spin_ang
                r = 18.5 * open_breath + p_a
                px, py, pz = r * cos(a), r * sin(a), p_b
                boost = 1.35
            elif kind == "arm":
                # Sweeping logarithmic spiral arms flowing smoothly around the aperture.
                u = (p_a + loop_t) % 1.0
                r = (19.5 * open_breath) + 36.0 * (u ** 1.15)
                a = a0 + spin_ang - 2.35 * u
                px = r * cos(a) + p_b * (-sin(a)) * (0.6 + 1.4 * u)
                py = r * sin(a) + p_b * cos(a) * (0.6 + 1.4 * u)
                pz = 9.0 * sin(a * 2.0 - spin_ang) * u * (1.0 - u)
                fade = min(1.0, u / 0.12) * min(1.0, (1.0 - u) / 0.22)
                boost = 0.45 + 0.85 * fade * (1.0 - 0.35 * u)
            else:
                a = a0 + spin_ang * 0.5
                r = p_a * open_breath
                px, py, pz = r * cos(a), r * sin(a), p_b
                boost = 0.58
            x1, y2, z2 = _rot_yx(px, py, pz, cy_r, sy_r, cp_r, sp_r)
            p = 1.0 / (1.0 - z2 / persp_d)
            tx[i], ty[i] = x1 * p, y2 * p
            b_d, zn = _depth_shade(z2, 44.0)
            tb[i], tz[i] = b_d * boost, zn
        return tx, ty, tb, tz

    if name == "quill":
        # The pen writes looped script: its tip circles while the paper carries the ink line to the left.
        d = max(0.0, now - scene.form_at)
        arrive = max(0.0, 1.0 - d)
        spin = float(meta.get("spin", 0.5))
        yaw = 0.22 * sin(now * spin)
        pitch = float(meta.get("pitch", 0.10))
        cy_r, sy_r, cp_r, sp_r = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
        roll = 0.25 * sin(now * spin * 0.8 + 1.0)
        cr_, sr_ = cos(roll), sin(roll)
        tip_x, tip_y = QUILL_TIP
        ax, ay = sin(QUILL_LEAN), -cos(QUILL_LEAN)
        px_, py_ = cos(QUILL_LEAN), sin(QUILL_LEAN)
        heights, swing, paper = QUILL_HEIGHTS, QUILL_SWING, QUILL_PAPER
        # The pen speeds over the loop tops, where it barely moves on the paper, so the ink lies evenly.
        u_now = QUILL_OMEGA * d - 0.55 * sin(QUILL_OMEGA * d)
        oy = -heights[int(u_now / (2 * pi)) % len(heights)] * (1.0 - cos(u_now)) * 0.5
        ox = swing * sin(u_now) - 0.35 * oy  # The script slants forward.
        shown = QUILL_LIFE * QUILL_SHOWN
        tx, ty, tb, tz = [0.0] * grains, [0.0] * grains, [0.0] * grains, [0.0] * grains
        for i, (_, _, a, b, c, kind) in enumerate(points):
            if kind == "ink":
                age = ((a + d / QUILL_LIFE) % 1.0) * QUILL_LIFE
                t0 = d - age
                if age >= shown or t0 < 0.0:
                    # Not written yet, or done: wait unseen at the nib.
                    px, py, pz, boost = tip_x + ox + 2.0 * b, tip_y + oy + b, 0.0, 0.25 * arrive
                else:
                    u0 = QUILL_OMEGA * t0 - 0.55 * sin(QUILL_OMEGA * t0)
                    h = heights[int(u0 / (2 * pi)) % len(heights)]
                    lift = -h * (1.0 - cos(u0)) * 0.5
                    px = tip_x + swing * sin(u0) - 0.35 * lift - paper * age + 0.3 * b
                    py = tip_y + lift + b
                    pz = 0.0
                    fresh = math.exp(-age / 0.25)
                    boost = (1.0 + 0.55 * fresh) * min(1.0, (shown - age) / 0.7)
            else:
                u, w = a * cr_ - c * sr_, a * sr_ + c * cr_
                px = tip_x + ox + u * px_ + b * ax
                py = tip_y + oy + u * py_ + b * ay
                pz = w
                boost = 1.5 if kind == "tip" else 0.95 if kind == "grip" else 1.1
            x1, y2, z2 = _rot_yx(px, py, pz, cy_r, sy_r, cp_r, sp_r)
            p = 1.0 / (1.0 - z2 / persp_d)
            tx[i], ty[i] = x1 * p, y2 * p
            b_d, zn = _depth_shade(z2, 30.0)
            tb[i], tz[i] = b_d * boost, zn
        return tx, ty, tb, tz

    return None
