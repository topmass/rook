"""Third-round system activity forms for the Devs theme, after the owner's review of round two (2026-11-27): a lifelike
Gaze eye, three simpler git branches, the power Seal run the other way (a circle first), and a cleaner clapperboard.

They keep icons_system2's contract: a grain record is (x0, y0, kind, a, b, c), build(n, rng) gives the (kind, a, b, c)
tuples, and pose(T, now) gives (place, yaw, pitch), where place(rec) gives (x, y, z, glow, normal). Every loop is
periodic in T (PERIOD), so nothing jumps or comes back from nowhere when a cycle ends. register() adds the forms to
icons_system2's registry, whose projection and eval_targets hook then serve them, and their builders to devs_pack.
"""

from __future__ import annotations

import math
import random

import devs_pack as dp  # Before icons_system2, so running this file alone loads them in devs_pack's order.
import icons_system2 as s2
from icons_system2 import (FACE_Z, PI, POWER_GAP, POWER_R, POWER_TUBE, TAU, _Path, _bez, _clamp, _ease_back,
                           _ease_out, _even, _rect_edge, _smooth, _split, _tube, cos, exp, sin, sqrt)


# ---------------------------------------------------------------------------------------------------------------------
# Eye, Gaze made lifelike: almond lids with a thick margin and a crease, a round eyeball whose white dims toward its
# sides and under the upper lid, a domed cornea with a soft window glint, and an iris of radial fibres with a bright
# collarette and a darker limbal ring. The eye looks about in quick saccades that settle, the lids follow the gaze up
# and down, the pupil narrows when it looks straight at you, and it blinks once a cycle.
# ---------------------------------------------------------------------------------------------------------------------

E3_W, E3_UP, E3_LO = 52.0, 22.5, 17.5  # The lids' half width, and the upper and lower lids' height at the middle.
E3_BALL, E3_BALLZ, E3_IRIS = 40.0, -26.0, 17.5  # The eyeball's radius and centre depth, and the iris's radius.
E3_LIMB = sqrt(E3_BALL ** 2 - E3_IRIS ** 2)  # How far the limbus sits from the ball's centre, along the gaze.
E3_PERIOD, E3_BLINK = 7.0, 3.5  # The blink comes just before the long look right.
GAZE3 = ((0.0, 0.0, 0.0), (1.3, -0.40, 0.05), (2.45, -0.30, -0.14), (3.7, 0.36, 0.11), (5.1, 0.0, 0.0))  # s, yaw, up


def _e3_lids(q, U, L, c):
    """The upper and lower lid margins' y at q = x / E3_W (y grows downward), the eye shut by share c."""
    w = 1.0 - q * q
    tilt = -2.0 * q  # The outer corner sits a little higher than the inner one.
    lo = L * w * (1.0 + 0.2 * q) + tilt - 2.5 * w * c  # The lower lid lifts a little in a blink.
    up = -U * w * (1.0 - 0.25 * q) + tilt  # Highest a little toward the nose, at -x.
    return up + (lo - up) * c, lo


def _e3_lid_z(x, y):
    """The lids lie on an ellipsoid a little proud of the eyeball."""
    return E3_BALLZ + 42.5 * sqrt(max(0.0, 1.0 - (x / 56.0) ** 2 - (y / 46.0) ** 2))


def _e3_inside(x, y, up, lo):
    return _smooth((y - up - 0.6) / 1.8) * _smooth((lo - y - 0.6) / 1.8)


def build_eye3_c(n, rng):
    """Records: 0 the upper margin (b 0 its front edge, 1 its back edge, which gives the lid its thickness), 2 the
    crease, 3 the lower margin (as 0), 5 iris fibres, 6 the limbus, 7 the pupil's rim, 8 the white of the eye, 9 the
    corneal glint."""
    up_f, up_b, crease, lo_f, lo_b, fibres, limbus, pupil, sclera, glint = _split(
        n, (96, 40, 34, 70, 30, 236, 48, 16, 56, 14))
    recs = []
    for kind, count, row in ((0, up_f, 0), (0, up_b, 1), (3, lo_f, 0), (3, lo_b, 1)):
        recs += [(kind, 2.0 * s - 1.0, row, rng.gauss(0, 0.22)) for s in _even(count, rng, 0.3)]
    recs += [(2, -0.78 + 1.62 * s, 0, rng.gauss(0, 0.3)) for s in _even(crease, rng, 0.3)]
    lines = 38
    per = -(-fibres // lines)
    for k in range(fibres):  # Radial fibres, each line evenly from the pupil out to the limbus.
        line = k % lines
        recs.append((5, TAU * line / lines + rng.gauss(0, 0.035), (k // lines + rng.random()) / per, line * 1.7))
    recs += [(6, a * TAU, rng.gauss(0, 0.3), 0.0) for a in _even(limbus, rng)]
    recs += [(7, a * TAU, rng.gauss(0, 0.25), 0.0) for a in _even(pupil, rng)]  # Sparse: a dense ring blooms.
    while sclera:  # The white: even over the ball where the open lids show it.
        lz = rng.uniform(0.25, 1.0)
        ph = rng.uniform(0, TAU)
        lx, ly = sqrt(1 - lz * lz) * cos(ph), sqrt(1 - lz * lz) * sin(ph)
        up, lo = _e3_lids(_clamp(E3_BALL * lx / E3_W, -0.999, 0.999), E3_UP + 3.0, E3_LO + 2.0, 0.0)
        if up < E3_BALL * ly < lo:
            recs.append((8, lx, ly, lz))
            sclera -= 1
    recs += [(9, 3.55 + 0.75 * s, rng.gauss(0, 0.35), 0.0) for s in _even(glint, rng)]
    return recs


def _e3_gaze(T):
    """(yaw, up) of the eye at form time T: quick saccades with a slight settle, and a faint drift while it holds."""
    if T < 1.0:
        return 0.0, 0.0
    t = (T - 1.0) % E3_PERIOD
    k = max(i for i, g in enumerate(GAZE3) if g[0] <= t)
    t0, gx1, gy1 = GAZE3[k]
    _, gx0, gy0 = GAZE3[k - 1]
    m = _ease_back((t - t0) / 0.17, 0.6)
    w = TAU / E3_PERIOD  # The drift repeats each period too.
    drift = _smooth((T - 1.0) / 0.5)
    return (gx0 + (gx1 - gx0) * m + drift * (0.010 * sin(w * 2.0 * T) + 0.007 * sin(w * 3.0 * T + 1.0)),
            gy0 + (gy1 - gy0) * m + drift * 0.008 * sin(w * 4.0 * T + 2.0))


def pose_eye3_c(T, now):
    opened = _smooth((T - 0.25) / 0.5)
    t = (T - 1.0) % E3_PERIOD if T >= 1.0 else -1.0
    blink = _smooth((t - E3_BLINK) / 0.09) * (1.0 - _smooth((t - E3_BLINK - 0.13) / 0.22)) if t >= 0.0 else 0.0
    shut = max(blink, 1.0 - opened)
    gx, gy = _e3_gaze(T)
    U, L = E3_UP + 9.0 * gy, E3_LO - 4.0 * gy  # The upper lid rides up with an upward look; the lower one dips.
    look = math.hypot(gx, gy)
    rp = 6.4 + 2.6 * _smooth(look / 0.38) + 0.3 * sin(TAU * 2.0 * T / E3_PERIOD)  # Narrow when it looks at you, wide when away.
    cgx, sgx, cgy, sgy = cos(gx), sin(gx), cos(gy), sin(gy)
    iris_cos = E3_LIMB / E3_BALL
    dx, dy, dz = sgx * cgy, -sgy, cgx * cgy  # The gaze's direction from the ball's centre.

    def turn(lx, ly, lz):
        ly, lz = ly * cgy - lz * sgy, ly * sgy + lz * cgy
        return lx * cgx + lz * sgx, ly, lz * cgx - lx * sgx

    def eye_pt(lx, ly, lz, glow, nrm):
        x, y, z = turn(lx, ly, lz)
        up, lo = _e3_lids(_clamp(x / E3_W, -0.999, 0.999), U, L, shut)
        return x, y, E3_BALLZ + z, glow * _e3_inside(x, y, up, lo), nrm

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind in (0, 3):
            up, lo = _e3_lids(a, U, L, shut)
            w = 1.0 - a * a
            corner = 0.55 + 0.45 * w
            if kind == 0:
                y = up + (1.9 * w if b else 0.0) + c
                glow = (0.55 if b else 1.15) * corner
            else:
                y = lo - (1.7 * w if b else 0.0) + c
                glow = (0.5 if b else 1.0) * corner
            x = E3_W * a
            return x, y, _e3_lid_z(x, y) + (-2.2 if b else 1.0), glow, None
        if kind == 2:
            up, _ = _e3_lids(a, U, L, shut)
            y = min(-(U + 7.0) * (1.0 - a * a) * (1.0 - 0.25 * a) - 2.0 * a, up - 1.0) + c
            x = E3_W * a
            return x, y, _e3_lid_z(x, y) + 1.5, 0.5 * (0.5 + 0.5 * (1.0 - a * a)), None
        if kind == 8:  # The white stays put; the iris hides it where it turns over it.
            x, y, z = E3_BALL * a, E3_BALL * b, E3_BALLZ + E3_BALL * c
            over = a * dx + b * dy + c * dz
            up, lo = _e3_lids(_clamp(x / E3_W, -0.999, 0.999), U, L, shut)
            shade = 0.55 + 0.45 * _smooth((y - up) / 9.0)  # The upper lid shades the white just under it.
            glow = 0.38 * shade * _smooth((iris_cos - 0.035 - over) / 0.05) * _e3_inside(x, y, up, lo)
            return x, y, z, glow, (a, b, c)
        gaze = (dx, dy, dz)
        if kind == 5:  # A fibre: wavy, a bright collarette near the pupil, darker toward the limbus.
            r = rp + 0.7 + (E3_IRIS - 1.2 - rp - 0.7) * b
            ang = a + 0.05 * sin(5.0 * b + c)
            glow = (0.6 + 0.42 * exp(-((b - 0.3) / 0.11) ** 2)) * (1.0 - 0.55 * _smooth((b - 0.72) / 0.26))
            return eye_pt(r * cos(ang), r * sin(ang), E3_LIMB - 0.6 + 1.8 * (1.0 - r / E3_IRIS), glow, gaze)
        if kind == 6:
            r = E3_IRIS + b
            return eye_pt(r * cos(a), r * sin(a), E3_LIMB + 0.2, 0.6, gaze)
        if kind == 7:
            r = rp + b
            return eye_pt(r * cos(a), r * sin(a), E3_LIMB + 1.2, 0.62, gaze)
        r = 10.5 + b  # The glint: a short soft arc on the cornea's dome, toward the light at the upper left.
        return eye_pt(r * cos(a), r * sin(a), E3_LIMB + 3.4, 0.62, gaze)
    return place, 0.1 * sin(TAU * now / 13.0), -0.08


# ---------------------------------------------------------------------------------------------------------------------
# Branch, simpler: the git glyph itself, a trunk with a commit at each end and a branch to a commit of its own. Lines
# are thin solid tubes; commits are rings. One idea each: A grows the branch out and draws it back, B parts a branch
# off the trunk and lays it back (a merge), C swings the branch out from behind the trunk on a hinge and back.
# ---------------------------------------------------------------------------------------------------------------------

B3_X0, B3_X1, B3_Y = -18.0, 18.0, 38.0  # The trunk's x, the branch commit's x, and the end commits' distance from 0.
B3_TUBE, B3_RING, B3_RT = 2.0, 7.0, 1.6  # The lines' radius, and the commits' ring radius and its tube's radius.
B3_EDGE = B3_RING + B3_RT  # A line meets a commit at the ring's outer edge.
B3_KNOT = (B3_X1, -22.0)  # The branch commit, for A and C.
B3_PERIOD = 6.2
B3_TRUNK = _Path(lambda u: (B3_X0, B3_Y - B3_EDGE - 2.0 * (B3_Y - B3_EDGE) * u, 0.0))
B3_FORK = _Path(lambda u: _bez(((B3_X0, 20.0, 0.0), (B3_X0, 2.0, 0.0), (B3_X1, 8.0, 0.0),
                                (B3_X1, B3_KNOT[1] + B3_EDGE, 0.0)), u))


def _b3_ring(cx, cy, cz, a, phi):
    """A commit ring's grain at angle a round it and phi round its tube: (x, y, z, normal)."""
    ca, sa, cp, sp = cos(a), sin(a), cos(phi), sin(phi)
    r = B3_RING + B3_RT * cp
    return cx + r * ca, cy + r * sa, cz + B3_RT * sp, (cp * ca, cp * sa, sp)


def _b3_drawn(a, attach, share):
    """How much of a ring drawn from attach both ways shows a grain at angle a, the ring drawn to share."""
    d = abs((a - attach + PI) % TAU - PI) / PI
    return _smooth((share - d) * 12.0) if share > 0.0 else 0.0


def build_branch3_a(n, rng, weights=(170, 140, 110, 110, 110)):
    """Fork: the trunk, the branch's line, and the bottom, top and branch commits (kinds 2, 3 and 4)."""
    trunk, branch, r1, r2, r3 = _split(n, weights)
    recs = [(0, s, rng.uniform(0, TAU), 0.0) for s in _even(trunk, rng, 0.4)]
    recs += [(1, s, rng.uniform(0, TAU), 0.0) for s in _even(branch, rng, 0.4)]
    for kind, count in ((2, r1), (3, r2), (4, r3)):
        recs += [(kind, a * TAU, rng.uniform(0, TAU), 0.0) for a in _even(count, rng, 0.3)]
    return recs


def _b3_stem(rec):
    """The trunk and its two end commits, which hold still in A, B and C."""
    kind, a, b = rec[2], rec[3], rec[4]
    if kind == 0:
        x, y, z, nrm = _tube(B3_TRUNK, a, B3_TUBE, b)
        return x, y, z, 1.0, nrm
    x, y, z, nrm = _b3_ring(B3_X0, B3_Y if kind == 2 else -B3_Y, 0.0, a, b)
    return x, y, z, 1.05, nrm


def pose_branch3_a(T, now):
    """The branch grows out of the trunk, its commit draws round from where the line arrives, and it holds. Then the
    commit undraws and the line draws back into the trunk, the way it came, and a moment later grows again."""
    ph = (T - 0.8) % B3_PERIOD if T >= 0.8 else -1.0
    if ph < 0.0:
        head = ring = 0.0
    else:
        head = _ease_out(ph / 1.0) * (1.0 - _smooth((ph - 4.45) / 0.95))
        ring = _smooth((ph - 0.85) / 0.5) * (1.0 - _smooth((ph - 4.0) / 0.45))
    soft = 2.0 / B3_FORK.length

    def place(rec):
        kind, a, b = rec[2], rec[3], rec[4]
        if kind < 1 or kind in (2, 3):
            return _b3_stem(rec)
        if kind == 1:
            x, y, z, nrm = _tube(B3_FORK, min(a, head), B3_TUBE, b)  # Unshown grains wait inside the tip.
            return x, y, z, _smooth((head - a) / soft), nrm
        x, y, z, nrm = _b3_ring(*B3_KNOT, 0.0, a, b)
        return x, y, z, 1.08 * _b3_drawn(a, PI / 2, 1.1 * ring), nrm
    return place, 0.3 * sin(TAU * now / 10.0), -0.12


def build_branch3_b(n, rng):
    """Merge: the same parts, with more dust on the branch, whose bowed course is longer than the trunk."""
    return build_branch3_a(n, rng, (130, 200, 103, 103, 104))
B3_BOW = 36.0


def pose_branch3_b(T, now):
    """A branch lies along the trunk. It parts and bows out to the side with a small click, and a commit draws round
    on it. It holds, the commit undraws, and the branch eases back in and lies along the trunk again: a merge."""
    ph = (T - 0.8) % B3_PERIOD if T >= 0.8 else -1.0
    if ph < 0.0:
        bow = ring = 0.0
    else:
        bow = _ease_back((ph - 0.1) / 0.9, 0.8) * (1.0 - _smooth((ph - 4.35) / 1.1))
        ring = _smooth((ph - 0.85) / 0.5) * (1.0 - _smooth((ph - 3.9) / 0.45))
    top, bottom = -B3_Y + B3_EDGE, B3_Y - B3_EDGE
    kx = B3_X0 + B3_BOW * bow

    def place(rec):
        kind, a, b = rec[2], rec[3], rec[4]
        if kind < 1 or kind in (2, 3):
            return _b3_stem(rec)
        if kind == 1:
            y = bottom + (top - bottom) * a
            out = _smooth(a / 0.36) * _smooth((1.0 - a) / 0.36)  # Out, along its own lane, and back.
            c, s = cos(b), sin(b)
            x = B3_X0 + B3_BOW * bow * out + B3_TUBE * c
            z = 6.0 * bow * out + B3_TUBE * s
            glow = 0.5 + 0.5 * _clamp(bow * 1.5)  # Lying on the trunk, the two read as one line.
            if ring > 0.0 and (x - kx) ** 2 + y * y < B3_EDGE ** 2:
                glow *= 1.0 - _smooth(ring * 2.0)  # The commit takes the line's place inside it.
            return x, y, z, glow, (c, 0.0, s)  # Square to an upright line: the bends are gentle.
        if kind == 4:
            x, y, z, nrm = _b3_ring(kx, 0.0, 6.0 * bow, a, b)
            return x, y, z, 1.08 * max(_b3_drawn(a, PI / 2, 0.55 * ring), _b3_drawn(a, -PI / 2, 0.55 * ring)), nrm
        return _b3_stem(rec)
    return place, 0.3 * sin(TAU * now / 10.0), -0.12


build_branch3_c = build_branch3_a  # Swing: the same parts; the branch and its commit turn on the trunk as one piece.
B3_FOLD = -1.5  # The branch's angle round the trunk when folded away behind it.


def pose_branch3_c(T, now):
    """The branch is a rigid arm hinged on the trunk. It swings round from behind the trunk to the side, settling with
    a small overshoot, holds, and swings back behind the trunk, where it waits, dim and edge on, before it swings out
    again."""
    ph = (T - 0.8) % B3_PERIOD if T >= 0.8 else -1.0
    out = _ease_back((ph - 0.2) / 1.0, 0.9) * (1.0 - _smooth((ph - 4.2) / 1.1)) if ph >= 0.0 else 0.0
    th = B3_FOLD * (1.0 - out)
    ct, st = cos(th), sin(th)

    def swing(x, y, z, glow, nrm):
        dx = x - B3_X0
        return (B3_X0 + dx * ct - z * st, y, dx * st + z * ct, glow,
                (nrm[0] * ct - nrm[2] * st, nrm[1], nrm[0] * st + nrm[2] * ct))

    def place(rec):
        kind, a, b = rec[2], rec[3], rec[4]
        if kind < 1 or kind in (2, 3):
            return _b3_stem(rec)
        if kind == 1:
            x, y, z, nrm = _tube(B3_FORK, a, B3_TUBE, b)
            return swing(x, y, z, 1.0, nrm)
        x, y, z, nrm = _b3_ring(*B3_KNOT, 0.0, a, b)
        return swing(x, y, z, 1.08, nrm)
    return place, 0.12 * sin(TAU * now / 11.0), -0.12


# ---------------------------------------------------------------------------------------------------------------------
# Power, Seal run the other way: a closed ring first. The top of the ring gathers and rises out of it as the bar,
# opening the gap, and the power mark holds. Then, slowly, the bar sinks back and its dust parts both ways into the
# gap, and the ring is whole again. The bar is exactly as long as the gap, so its dust fills the gap evenly.
# ---------------------------------------------------------------------------------------------------------------------

P3_LINE = -POWER_R * cos(POWER_GAP)  # Where the gap's ends sit: the bar's middle.
P3_HALF = POWER_R * POWER_GAP  # Half the bar: half the gap's arc.
P3_PERIOD = 5.6


def build_power3_a(n, rng):
    """Ring: the open ring's arc, and the gap's arc, which becomes the bar (angle and phi)."""
    ring, bar = _split(n, (TAU - 2.0 * POWER_GAP, 2.0 * POWER_GAP))  # Equal dust per pixel on both.
    recs = [(0, POWER_GAP + (TAU - 2.0 * POWER_GAP) * s, rng.uniform(0, TAU), rng.gauss(0, 0.3))
            for s in _even(ring, rng)]
    recs += [(1, POWER_GAP * (2.0 * s - 1.0), rng.uniform(0, TAU), 0.0) for s in _even(bar, rng)]
    return recs


def pose_power3_a(T, now):
    ph = (T - 0.8) % P3_PERIOD if T >= 0.8 else -1.0
    rise = _smooth((ph - 0.3) / 1.0) * (1.0 - _smooth((ph - 3.3) / 1.5)) if ph >= 0.0 else 0.0
    spin = TAU * T / P3_PERIOD  # The tube rolls once a period.

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            x, y, z, nrm = s2._ring_pt(a, b + spin, POWER_TUBE + c)
            return x, y, z, 1.0, nrm
        d = abs(a) / POWER_GAP  # In order, so no two grains cross: the gap's left half turns up into the bar's top
        e = _smooth(rise * 1.5 - 0.5 * d)
        x0, y0, z0, n0 = s2._ring_pt(a, b + spin)
        cp, sp = cos(b + spin), sin(b + spin)
        x1, y1, z1 = POWER_TUBE * cp, P3_LINE + P3_HALF * a / POWER_GAP, POWER_TUBE * sp  # and its right half down.
        nrm = n0 if e < 0.5 else (cp, 0.0, sp)
        return x0 + (x1 - x0) * e, y0 + (y1 - y0) * e, z0 + (z1 - z0) * e, 1.0 + 0.05 * e, nrm
    return place, 0.3 * sin(TAU * now / 10.0), -0.14


# ---------------------------------------------------------------------------------------------------------------------
# Film, the clapperboard made cleaner: a slate with a field rule, a fixed striped bar on top, and a striped stick on a
# hinge at the left, with a knuckle round its pivot. The stick lifts, holds, draws back a hair, and snaps shut: the
# seam flashes and the whole board jolts with the blow, then the stick settles with a tiny rebound.
# ---------------------------------------------------------------------------------------------------------------------

F3_X, F3_TOP, F3_BOT, F3_BAR = 40.0, -5.0, 33.0, 10.0  # Half width; the slate's top and bottom; a bar's height.
F3_HINGE = (-F3_X, F3_TOP - F3_BAR)  # The stick pivots on its lower left corner.
F3_OPEN, F3_PERIOD = 0.36, 3.4


def _f3_stripes(count, rng, y_bottom, lean):
    """count grains filling five slanted stripes across a bar, solid blocks with the dark gaps between: (x, y)."""
    out = []
    for k in range(count):
        v = rng.random()
        x = -F3_X + 4.0 + 16.0 * (k % 5) + 8.0 * rng.random() + lean * 6.0 * (v - 0.5)
        out.append((_clamp(x, -F3_X + 1.5, F3_X - 1.5), y_bottom - 1.0 - (F3_BAR - 2.0) * v))
    return out


def build_film3_c(n, rng):
    """Records: 0 the slate (x, y, glow), 1 the slate's left wall (y, depth), 2 the fixed bar (x, y, glow), 3 the stick
    in its closed place (x, y, glow), 4 the hinge's knuckle (angle). Seam grains carry glow 1.11, so the clap lights
    them."""
    slate, rules, fill, wall, bar_edge, bar_stripes, stick_edge, stick_stripes, knuckle = _split(
        n, (124, 56, 40, 18, 80, 106, 92, 118, 6))
    h = F3_BOT - F3_TOP
    recs = [(0, x, y, 1.05) for x, y in _rect_edge(slate, rng, 2 * F3_X, h, 0.0, (F3_TOP + F3_BOT) / 2)]
    rule_y = F3_TOP + 15.0
    for k in range(rules):  # One rule across, and two dividers below it: the slate's fields.
        q = rng.random()
        if k % 5 < 3:
            recs.append((0, -F3_X + 2.0 + (2 * F3_X - 4.0) * q, rule_y + rng.gauss(0, 0.3), 0.62))
        else:
            recs.append((0, (-8.0 if k % 5 == 3 else 16.0) + rng.gauss(0, 0.3), rule_y + (F3_BOT - rule_y) * q, 0.62))
    recs += [(0, rng.uniform(-F3_X + 2, F3_X - 2), rng.uniform(F3_TOP + 2, F3_BOT - 2), 0.3) for _ in range(fill)]
    recs += [(1, F3_TOP + h * s, rng.uniform(-1.0, 1.0), 0.0) for s in _even(wall, rng)]
    bar_bottom = F3_TOP
    for x, y in _rect_edge(bar_edge * 9 // 5, rng, 2 * F3_X, F3_BAR, 0.0, bar_bottom - F3_BAR / 2):
        if y < bar_bottom - 0.8:  # Its bottom edge is the slate's top edge, drawn once.
            recs.append((2, x, y, 1.11 if y < bar_bottom - F3_BAR + 0.8 else 1.0))
    recs += [(2, x, y, 0.8) for x, y in _f3_stripes(bar_stripes, rng, bar_bottom, 1.0)]
    stick_bottom = bar_bottom - F3_BAR - 0.8
    for x, y in _rect_edge(stick_edge, rng, 2 * F3_X, F3_BAR, 0.0, stick_bottom - F3_BAR / 2):
        recs.append((3, x, y, 1.11 if y > stick_bottom - 0.8 else 1.0))
    recs += [(3, x, y, 0.8) for x, y in _f3_stripes(stick_stripes, rng, stick_bottom, -1.0)]
    recs += [(4, PI / 2 + PI * s, 0.0, 0.0) for s in _even(knuckle, rng)]
    while len(recs) < n:
        recs.append((0, rng.uniform(-F3_X + 2, F3_X - 2), rng.uniform(F3_TOP + 2, F3_BOT - 2), 0.3))
    return recs[:n]


def _f3_angle(ph):
    """The stick's angle at ph seconds into a clap, and the seconds since the clap landed (negative before)."""
    since = ph - 1.86
    if ph < 0.25:
        return 0.0, since
    if ph < 1.55:
        return F3_OPEN * _ease_out((ph - 0.25) / 0.9), since
    if ph < 1.75:
        return F3_OPEN + 0.03 * _smooth((ph - 1.55) / 0.2), since  # A hair further: the wind up.
    if ph < 1.86:
        x = (ph - 1.75) / 0.11
        return (F3_OPEN + 0.03) * (1.0 - x * x), since  # Falling faster and faster: the clap.
    return 0.05 * abs(sin(since * 26.0)) * exp(-since / 0.06), since  # A tiny rebound, dying fast.


def pose_film3_c(T, now):
    ph = (T - 0.7) % F3_PERIOD if T >= 0.7 else 0.0
    ang, since = _f3_angle(ph)
    flash = exp(-since / 0.16) if since >= 0.0 else 0.0
    kick = (since / 0.04) * exp(1.0 - since / 0.04) if 0.0 <= since < 0.6 else 0.0
    jolt = 1.3 * kick  # The board gives a little under the blow.
    ca, sa = cos(ang), sin(ang)
    hx, hy = F3_HINGE

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            return a, b + jolt, 2.0, c, FACE_Z
        if kind == 1:
            return -F3_X, a + jolt, 2.0 * b, 0.5, (-1.0, 0.0, 0.0)
        if kind == 2:
            return a, b + jolt, 2.0, c * (1.0 + 0.35 * flash if c > 1.1 else 1.0), FACE_Z
        if kind == 3:
            dx, dy = a - hx, b - hy
            return (hx + dx * ca + dy * sa, hy - dx * sa + dy * ca + jolt, 2.6, c * (1.0 + 0.35 * flash if c > 1.1 else 1.0),
                    FACE_Z)
        return hx + 5.0 * cos(a), hy + 5.0 * sin(a) + jolt, 2.4, 0.55, None  # Wide and sparse: no hot spot.
    return place, 0.32 + 0.1 * sin(TAU * now / 11.0), -0.14 - 0.03 * kick


# ---------------------------------------------------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------------------------------------------------

FORMS = {
    "eye3_c": (build_eye3_c, pose_eye3_c),
    "branch3_a": (build_branch3_a, pose_branch3_a), "branch3_b": (build_branch3_b, pose_branch3_b),
    "branch3_c": (build_branch3_c, pose_branch3_c),
    "power3_a": (build_power3_a, pose_power3_a),
    "film3_c": (build_film3_c, pose_film3_c),
}
FIT = {"eye3_c": 1.15, "branch3_a": 1.15, "branch3_b": 1.15, "branch3_c": 1.15, "power3_a": 1.25, "film3_c": 1.08}
PERIOD = {"eye3_c": E3_PERIOD, "branch3_a": B3_PERIOD, "branch3_b": B3_PERIOD, "branch3_c": B3_PERIOD,
          "power3_a": P3_PERIOD, "film3_c": F3_PERIOD}


def register(pack):
    """Add these forms to icons_system2's registry (its eval_targets hook serves every name in it), and their builders
    to devs_pack, given its globals."""
    s2.FORMS.update(FORMS)
    s2.FIT.update(FIT)
    pack["BUILDERS"].update({name: s2._builder(name) for name in FORMS})


if __name__ == "__main__":
    # Every form is registered with the Devs grain count and a manifest entry, stays inside the 124 px form box, and
    # loops: one period on, every grain is where it was, and no lit grain jumps between frames across two periods.
    import types
    trouble = []
    for name in FORMS:
        pts = dp.BUILDERS[name](640, random.Random(sum(map(ord, name))))
        assert len(pts) == 640, (name, len(pts))
        assert name in dp.FORMS_META, f"{name} has no manifest entry"
        box, jump, prev = [0.0, 0.0, 0.0, 0.0], 0.0, None
        for step in range(round((1.0 + 2 * PERIOD[name]) * 60)):
            now = step / 60.0
            tx, ty, tb, _ = dp.eval_targets(name, pts, types.SimpleNamespace(form_at=0.0), now)
            lit = [(x, y) for x, y, b in zip(tx, ty, tb) if b > 0.05]
            box = [min(box[0], *(x for x, _ in lit)), max(box[1], *(x for x, _ in lit)),
                   min(box[2], *(y for _, y in lit)), max(box[3], *(y for _, y in lit))]
            if prev and now > 1.2:
                jump = max(jump, max(math.hypot(x - px, y - py) for x, y, b, px, py, pb in zip(tx, ty, tb, *prev)
                                     if b > 0.05 and pb > 0.05))
            prev = (tx, ty, tb)
        place, _, _ = FORMS[name][1](1.7, 0.0)
        again, _, _ = FORMS[name][1](1.7 + PERIOD[name], 0.0)
        recs = [(0.0, 0.0) + tuple(p[2:]) for p in pts]
        drift = max(math.dist(place(r)[:3], again(r)[:3]) for r in recs)
        print(f"{name:10s} x {box[0]:6.1f} .. {box[1]:5.1f}   y {box[2]:6.1f} .. {box[3]:5.1f}   "
              f"largest step {jump:4.1f} px   drift after a period {drift:.3f}")
        if not (-62 <= box[0] and box[1] <= 62 and -62 <= box[2] and box[3] <= 62) or jump > 14.0 or drift > 0.05:
            trouble.append(name)
    assert not trouble, f"out of the box, jumping or not looping: {trouble}"
    print("ok")
