"""Second-round design candidates for the system activities' icons in the Devs theme: three 3D gold-dust forms each for
the eye (screenshot), the branch (git), the cog (Skill), power (stopping or restarting), tiles (windows), film (media)
and the spinner (a background job). ACTIVITY_FORMS still names the flat fallbacks; these forms are candidates only.

Each form is one solid object whose own motion is the act: an iris closes down, a branch grows and merges, gears mesh,
a reel unspools. There is no shared gimmick and no bright travelling point. Brightness comes from the Devs depth shade
and from which way a surface faces: a surface turned away dims to about 35 percent, so the forms read as solid.

A grain record is (x0, y0, kind, a, b, c): its place at the reference pose (so grains sort by angle, as every Devs form
does, and keep their side of the swarm through the morph from the resting loop), the part it belongs to, and three
numbers that part reads. A form is (build, pose): build(n, rng) gives n (kind, a, b, c) tuples, and pose(T, now) gives
(place, yaw, pitch), where place(rec) gives (x, y, z, glow, normal) in the form's own space. normal is None, a unit
(nx, ny, nz) for a one-sided surface, or (nx, ny, nz, 1) for a two-sided one. BUILDERS and EVAL keep devs_pack's
contract; register() adds them to devs_pack.
"""

from __future__ import annotations

import math
import random

import devs_pack as dp

TAU, PI = 2.0 * math.pi, math.pi
sin, cos, exp, sqrt = math.sin, math.cos, math.exp, math.sqrt
REF_T = 3.0  # The pose the records sort by: every form is whole by then.
FACE_Z = (0.0, 0.0, 1.0)
_ease_back, _ease_out = dp._ease_back, dp._ease_out


def _smooth(x):
    x = 0.0 if x < 0.0 else 1.0 if x > 1.0 else x
    return x * x * (3.0 - 2.0 * x)


def _clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def _even(count, rng, jitter=0.18):
    """count values over [0, 1), evenly spaced with a little jitter."""
    return [(k + 0.5 + rng.uniform(-jitter, jitter)) / count for k in range(count)]


def _split(n, weights):
    """n grains shared by weight, summing to exactly n."""
    total = float(sum(weights))
    counts = [int(n * w / total) for w in weights]
    for k in range(n - sum(counts)):
        counts[k % len(counts)] += 1
    return counts


def _bez(p, t):
    a, b, c, d = p
    m = 1.0 - t
    return tuple(m * m * m * a[i] + 3 * m * m * t * b[i] + 3 * m * t * t * c[i] + t * t * t * d[i] for i in range(3))


class _Path:
    """A 3D curve fn(u), u in [0, 1], resampled evenly by length. at(s) gives the point and unit tangent at share s."""

    def __init__(self, fn, n=300):
        raw = [fn(k / (4 * n)) for k in range(4 * n + 1)]
        acc = [0.0]
        for a, b in zip(raw, raw[1:]):
            acc.append(acc[-1] + math.dist(a, b))
        self.length, self.n, pts, j = acc[-1], n, [], 0
        for k in range(n + 1):
            target = acc[-1] * k / n
            while j < len(acc) - 2 and acc[j + 1] < target:
                j += 1
            q = (target - acc[j]) / ((acc[j + 1] - acc[j]) or 1.0)
            pts.append(tuple(raw[j][i] + (raw[j + 1][i] - raw[j][i]) * q for i in range(3)))
        self.pts = pts

    def at(self, s):
        f = (0.0 if s < 0.0 else 1.0 if s > 1.0 else s) * self.n
        i = min(int(f), self.n - 1)
        q = f - i
        (ax, ay, az), (bx, by, bz) = self.pts[i], self.pts[i + 1]
        dx, dy, dz = bx - ax, by - ay, bz - az
        ln = sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        return ax + dx * q, ay + dy * q, az + dz * q, dx / ln, dy / ln, dz / ln


def _tube(path, s, r, phi):
    """A point on a tube of radius r round a path at share s, phi round it: (x, y, z, normal)."""
    x, y, z, tx, ty, tz = path.at(s)
    m = math.hypot(tx, ty) or 1.0
    n1x, n1y = -ty / m, tx / m
    n2x, n2y, n2z = -tz * n1y, tz * n1x, tx * n1y - ty * n1x
    c, s_ = cos(phi), sin(phi)
    nx, ny, nz = c * n1x + s_ * n2x, c * n1y + s_ * n2y, s_ * n2z
    return x + r * nx, y + r * ny, z + r * nz, (nx, ny, nz)


def _arc_inverse(fn, samples):
    """For a closed or open flat curve fn(u) -> (x, y), u in [0, 1]: a function from a share of its length to u."""
    pts = [fn(k / samples) for k in range(samples + 1)]
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    total = acc[-1] or 1.0

    def u_at(s):
        target, lo, hi = s * total, 0, samples
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if acc[mid] < target else (lo, mid)
        return (lo + (target - acc[lo]) / ((acc[hi] - acc[lo]) or 1.0)) / samples
    return u_at


def _tooth(f):
    """A gear tooth's height at f, a share of one tooth's pitch: 0 at the root, 1 on the tip land."""
    f %= 1.0
    if f < 0.05 or f >= 0.55:
        return 0.0
    if f < 0.17:
        return (f - 0.05) / 0.12
    if f < 0.43:
        return 1.0
    return (0.55 - f) / 0.12


def _gear_recs(gid, n, N, rr, rt, h, rng, spokes=4, hub=6.0):
    """A solid spur gear's grains, in its own plane, axis +z. Kinds gid*10 + part: 0 the front face's toothed outline,
    1 the tooth tips' side walls, 2 the face's rim band, 3 the hub, 4 the spokes (none when spokes is 0). a is the
    angle, b the radius, c the depth (or across, for a spoke)."""
    cnt = _split(n, (40, 16, 20, 8, 16) if spokes else (46, 16, 26, 12, 0))
    prof = lambda th: rr + (rt - rr) * _tooth(th * N / TAU)  # noqa: E731
    u_at = _arc_inverse(lambda u: (prof(u * TAU) * cos(u * TAU), prof(u * TAU) * sin(u * TAU)), N * 90)
    recs = []
    for s in _even(cnt[0], rng, 0.3):
        th = u_at(s) * TAU
        recs.append((gid * 10, th, prof(th) + rng.gauss(0, 0.45), h / 2 + rng.gauss(0, 0.3)))
    edges = [(k + f) / N * TAU for k in range(N) for f in (0.17, 0.43)]
    rows = -(-cnt[1] // len(edges))
    for j in range(cnt[1]):
        recs.append((gid * 10 + 1, edges[j % len(edges)], rt, h / 2 - h * (j // len(edges) + 0.5) / rows))
    for _ in range(cnt[2]):
        recs.append((gid * 10 + 2, rng.uniform(0, TAU), rng.uniform(max(hub + 1.5, rr - 6.5), rr - 0.5), h / 2))
    for th in _even(cnt[3], rng):
        recs.append((gid * 10 + 3, th * TAU, hub + rng.gauss(0, 0.4), h / 2 + 2.0))
    for j in range(cnt[4]):
        sp = j % spokes
        recs.append((gid * 10 + 4, TAU * sp / spokes, hub + (rr - 6.5 - hub) * rng.random(), rng.gauss(0, 1.1)))
    return recs


def _gear_place(part, a, b, c, cx, cy, cz, rot):
    """A spur gear grain in the xy plane at (cx, cy, cz), turned by rot: (x, y, z, glow, normal)."""
    th = a + rot
    ct, st = cos(th), sin(th)
    if part == 4:
        return cx + b * ct - c * st, cy + b * st + c * ct, cz + 3.5, 0.8, FACE_Z
    if part == 1:
        return cx + b * ct, cy + b * st, cz + c, 1.0, (ct, st, 0.0)
    glow = (1.1, 0, 0.55, 1.05)[part]
    return cx + b * ct, cy + b * st, cz + c, glow, FACE_Z


# ---------------------------------------------------------------------------------------------------------------------
# Eye: screenshot, looking at the screen. All three share almond lids that bulge toward the viewer, and the lids hide
# whatever of the iris lies outside them.
# ---------------------------------------------------------------------------------------------------------------------

EYE_W, EYE_H, EYE_Z = 52.0, 25.0, 14.0
IRIS_R = 21.0


def _lid_recs(n, rng):
    recs = []
    for k, s in enumerate(_even(n, rng, 0.3)):
        side = 1 if k % 2 == 0 else -1
        u = 2.0 * s - 1.0
        recs.append((0, u, side, rng.gauss(0, 1.25 if side > 0 else 0.9)))
    return recs


def _lid(u, side, o, H):
    """A lid grain: u along the eye from corner to corner, side +1 upper or -1 lower, o across the lid's band."""
    edge = H * (1.0 - u * u)
    taper = 0.35 + 0.65 * (1.0 - u * u)
    return EYE_W * u, -side * edge + o * taper, EYE_Z * (1.0 - u * u), 1.12 if side > 0 else 0.95, None


def _inside(x, y, H):
    """How far inside the lids a point sits: 0 outside, 1 a little way in."""
    q = x / EYE_W
    if q * q >= 1.0:
        return 0.0
    return _smooth((H * (1.0 - q * q) - abs(y) - 1.0) / 2.5)


def _iris_z(r):
    return 8.0 + 6.0 * max(0.0, 1.0 - (r / IRIS_R) ** 2)


def build_eye_a(n, rng):
    """Focus: the iris is an aperture. Fibres, outer rim, pupil rim."""
    lids, fibres, rim, pupil = _split(n, (250, 270, 84, 36))
    recs = _lid_recs(lids, rng)
    for k in range(fibres):  # Spread by area, so the fibres do not crowd into a bright core at the pupil.
        recs.append((1, TAU * (k % 24) / 24 + rng.gauss(0, 0.03), sqrt(rng.random()), rng.gauss(0, 0.5)))
    recs += [(2, a * TAU, rng.gauss(0, 0.6), 0.0) for a in _even(rim, rng)]
    recs += [(3, a * TAU, rng.gauss(0, 0.45), 0.0) for a in _even(pupil, rng)]
    return recs


def pose_eye_a(T, now):
    """The eye opens, then focuses again and again: the pupil snaps small as the fibres twist like aperture blades and
    the lids narrow a little, holds, then relaxes."""
    opened = _ease_back((T - 0.3) / 0.55, 1.2)
    ph = (T - 1.0) % 4.4 if T >= 1.0 else -1.0
    focus = _ease_back((ph - 0.7) / 0.32, 1.4) * (1.0 - _smooth((ph - 2.9) / 1.1)) if ph >= 0.0 else 0.0
    rp = 13.0 - 5.0 * focus  # The pupil stays an open dark hole even when focused.
    H = EYE_H * opened - 3.5 * _clamp(focus)
    twist = 1.15 * focus

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            return _lid(a, b, c, H)
        if kind == 1:
            r = rp + (IRIS_R - rp) * b
            ang = a + twist * (1.0 - b) ** 1.5
            x, y = r * cos(ang) - c * sin(ang), r * sin(ang) + c * cos(ang)
            return x, y, _iris_z(r), 0.8 * _inside(x, y, H), None
        r = (IRIS_R + b) if kind == 2 else (rp + 0.9 + b)
        x, y = r * cos(a), r * sin(a)
        return x, y, _iris_z(r), (1.05 if kind == 2 else 0.85) * _inside(x, y, H), None
    return place, 0.28 * sin(TAU * now / 11.0), -0.12


def build_eye_b(n, rng):
    """Intake: the iris is a slow spiral of dust pouring into the pupil."""
    lids, stream, rim, pupil = _split(n, (240, 300, 70, 30))
    recs = _lid_recs(lids, rng)
    recs += [(1, rng.uniform(0, TAU), (k + rng.random()) / stream, rng.gauss(0, 0.5)) for k in range(stream)]
    recs += [(2, a * TAU, rng.gauss(0, 0.6), 0.0) for a in _even(rim, rng)]
    recs += [(3, a * TAU, rng.gauss(0, 0.5), 0.0) for a in _even(pupil, rng)]
    return recs


def pose_eye_b(T, now):
    """Dust drifts in from the iris's rim along gentle spirals, slows and gathers at the pupil's edge, and sinks into
    the pupil. The rim and the pupil hold still, so only the dust flows."""
    rp, H = 9.5, EYE_H
    flow = T / 2.8

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            return _lid(a, b, c, H)
        if kind == 1:
            u = (b + flow) % 1.0
            q = (1.0 - u) ** 1.3  # Fast at the rim, slowing as it nears the pupil, so it gathers there.
            r = rp + 1.0 + (IRIS_R - rp - 1.0) * q
            ang = a + 1.4 * (1.0 - q)
            x, y = r * cos(ang) - c * sin(ang), r * sin(ang) + c * cos(ang)
            sink = _smooth((u - 0.82) / 0.18)
            glow = _smooth(u / 0.12) * (1.0 - sink) * (0.62 + 0.3 * (1.0 - q))
            return x, y, _iris_z(r) - 7.0 * sink, glow * _inside(x, y, H), None
        r = (IRIS_R + b) if kind == 2 else (rp + b)
        x, y = r * cos(a), r * sin(a)
        return x, y, _iris_z(r), (1.05 if kind == 2 else 0.8) * _inside(x, y, H), None
    return place, 0.26 * sin(TAU * now / 12.0), -0.12


EYEBALL_R = 30.0
GAZES = ((0.0, 0.0), (-0.5, 0.06), (0.46, -0.2), (0.12, 0.24))


def build_eye_c(n, rng):
    """Gaze: an eyeball turns behind the lids. Iris fibres (polar angle, azimuth), iris rim, pupil rim, sclera."""
    lids, fibres, rim, pupil, sclera = _split(n, (240, 250, 70, 30, 50))
    recs = _lid_recs(lids, rng)
    for k in range(fibres):  # Even by area over the iris's band of the ball.
        recs.append((1, math.acos(rng.uniform(cos(0.62), cos(0.36))), TAU * (k % 25) / 25 + rng.gauss(0, 0.04), 0.0))
    recs += [(2, 0.64, a * TAU, 0.0) for a in _even(rim, rng)]
    recs += [(2, 0.33, a * TAU, 1.0) for a in _even(pupil, rng)]
    for _ in range(sclera):
        recs.append((3, math.acos(rng.uniform(0.35, 1.0)), rng.uniform(0, TAU), 0.0))
    return recs


def pose_eye_c(T, now):
    """The ball looks left, right, up and back at you in quick saccades, holding each look. The iris foreshortens to
    an ellipse as it turns, and the lids hide what turns past them."""
    opened = _ease_back((T - 0.3) / 0.55, 1.2)
    ph = (T - 1.0) % 5.6 if T >= 1.0 else 0.0
    k = int(ph / 1.4)
    g0, g1 = GAZES[k - 1], GAZES[k]
    m = _ease_back((ph - 1.4 * k) / 0.26, 1.3) if T >= 1.0 else 1.0
    gx, gy = g0[0] + (g1[0] - g0[0]) * m, g0[1] + (g1[1] - g0[1]) * m
    cgx, sgx, cgy, sgy = cos(gx), sin(gx), cos(gy), sin(gy)
    H, R, zc = EYE_H * opened, EYEBALL_R, EYE_Z - EYEBALL_R - 2.0

    def place(rec):
        kind, psi, chi = rec[2], rec[3], rec[4]
        if kind == 0:
            return _lid(psi, chi, rec[5], H)
        sp_, cp_ = sin(psi), cos(psi)
        lx, ly, lz = sp_ * cos(chi), sp_ * sin(chi), cp_
        if kind != 3:  # The iris turns with the gaze; the sclera's dust stays put as the ball's still surface.
            ly, lz = ly * cgy - lz * sgy, ly * sgy + lz * cgy
            lx, lz = lx * cgx + lz * sgx, lz * cgx - lx * sgx
        x, y, z = R * lx, R * ly, zc + R * lz
        glow = (0.0, 0.8, 1.05 if rec[5] == 0.0 else 0.85, 0.38)[kind] * _inside(x, y, H)
        return x, y, z, glow, (lx, ly, lz)
    return place, 0.18 * sin(TAU * now / 13.0), -0.1


# ---------------------------------------------------------------------------------------------------------------------
# Branch: git. Lines are tubes of dust; commits are rings of dust the line runs into and out of.
# ---------------------------------------------------------------------------------------------------------------------

TUBE_R = 2.6
KNOT_R = 7.5


def _knot_place(cx, cy, cz, a, j, scale, glow):
    r = (KNOT_R + j) * scale
    return cx + r * cos(a), cy + r * sin(a), cz, glow * min(1.0, scale), FACE_Z


def _near_knot(x, y, knots):
    for kx, ky in knots:
        if (x - kx) ** 2 + (y - ky) ** 2 < (KNOT_R + 1.5) ** 2:
            return True
    return False


BR_TRUNK = _Path(lambda u: (-20.0, 50.0 - 102.0 * u, 0.0))
BR_FORK = _Path(lambda u: (  # Fork out of the trunk, the branch's own lane, and the merge back.
    _bez(((-20.0, 32.0, 0.0), (-20.0, 14.0, 4.0), (20.0, 18.0, 10.0), (20.0, 0.0, 10.0)), 3 * u) if u < 1 / 3 else
    (20.0, -14.0 * (3 * u - 1), 10.0) if u < 2 / 3 else
    _bez(((20.0, -14.0, 10.0), (20.0, -32.0, 10.0), (-20.0, -28.0, 4.0), (-20.0, -46.0, 0.0)), 3 * u - 2)))
BR_KNOTS_TRUNK = ((-20.0, 40.0), (-20.0, -10.0))
BR_KNOT_BRANCH = (20.0, -7.0)


def build_branch_a(n, rng):
    """Grow: the trunk, the branch's path (fork, lane, merge), two trunk commits and one branch commit."""
    trunk, branch, knots = _split(n, (230, 230, 180))
    recs = [(0, (k + rng.random()) / trunk, rng.uniform(0, TAU), rng.gauss(0, 0.35)) for k in range(trunk)]
    recs += [(1, (k + rng.random()) / branch, rng.uniform(0, TAU), rng.gauss(0, 0.35)) for k in range(branch)]
    for k in range(knots):
        recs.append((2 + k % 3, rng.uniform(0, TAU), rng.gauss(0, 0.5), 0.0))
    return recs


def _branch_s(x, y):
    """The share along BR_FORK nearest a point (found once, for the branch commit)."""
    return min(range(BR_FORK.n + 1), key=lambda i: (BR_FORK.pts[i][0] - x) ** 2 + (BR_FORK.pts[i][1] - y) ** 2) / BR_FORK.n


BR_KNOT_S = _branch_s(*BR_KNOT_BRANCH)


def pose_branch_a(T, now):
    """Dust streams up the trunk. A branch grows out of it, a commit gathers on the branch, the branch runs back and
    merges, and then the branch drains into the trunk from its root, its dust following the merge. Then it grows
    again."""
    flow = 0.085 * T
    ph = (T - 0.9) % 5.6 if T >= 0.9 else -1.0
    head = _smooth(ph / 1.7) if ph >= 0.0 else 0.0
    tail = _smooth((ph - 3.5) / 1.5) if ph >= 0.0 else 0.0
    edge = 0.05
    knot_in = _ease_back((head - BR_KNOT_S) / 0.12 * 1.0, 1.6) if head > BR_KNOT_S else 0.0
    knot_out = 1.0 - _smooth((tail - BR_KNOT_S + 0.02) / 0.1)
    kx, ky = BR_KNOT_BRANCH
    trunk_knots = BR_KNOTS_TRUNK
    branch_knot_on = knot_in * knot_out > 0.3
    bz = 10.0

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            u = (a + flow) % 1.0
            x, y, z, nrm = _tube(BR_TRUNK, u, TUBE_R + c, b)
            glow = 0.0 if _near_knot(x, y, trunk_knots) else _smooth(u / 0.05) * _smooth((1.0 - u) / 0.05)
            return x, y, z, glow, nrm
        if kind == 1:
            u = (a + flow * BR_TRUNK.length / BR_FORK.length) % 1.0
            x, y, z, nrm = _tube(BR_FORK, u, TUBE_R + c, b)
            glow = _smooth((head - u) / edge) * _smooth((u - tail) / edge)
            if branch_knot_on and (x - kx) ** 2 + (y - ky) ** 2 < (KNOT_R + 1.5) ** 2:
                glow = 0.0
            return x, y, z, glow, nrm
        if kind < 4:
            cx, cy = trunk_knots[kind - 2]
            return _knot_place(cx, cy, 0.0, a, b, 1.0, 1.05)
        return _knot_place(kx, ky, bz, a, b, knot_in * knot_out, 1.1)
    return place, 0.34 * sin(TAU * now / 10.0), -0.15


def build_branch_b(n, rng):
    """Unbraid: two strands, each a stream of grains (strand, share, jitter)."""
    return [(k % 2, (k // 2 + rng.random()) / (n // 2), rng.gauss(0, 0.7), rng.gauss(0, 0.7)) for k in range(n)]


def pose_branch_b(T, now):
    """Two strands twist together as one braided line, and dust runs up them. Then the braid parts: one strand bows
    out and away as a branch and runs beside the other, and later they braid back together, a merge."""
    ph = (T - 0.6) % 5.2 if T >= 0.6 else -1.0
    opened = (_ease_back(ph / 1.0, 1.3) * (1.0 - _smooth((ph - 2.8) / 1.3))) if ph >= 0.0 else 0.0
    flow, spin = 0.11 * T, 1.7 * T
    y0, y1 = -32.0, 26.0

    def place(rec):
        s, a, jx, jz = rec[2], rec[3], rec[4], rec[5]
        u = (a + flow) % 1.0
        y = 50.0 - 102.0 * u
        q = (y - y0) / (y1 - y0)
        bump = _smooth(q / 0.3) * _smooth((1.0 - q) / 0.3)  # Out, along its own lane, and back: a branch's course.
        sep = 38.0 * bump * opened
        rh = 2.8 * max(0.0, 1.0 - 1.7 * bump * _clamp(opened))  # Closed, the two wind tight as one rope.
        cx = -16.0 if s == 0 else -16.0 + sep  # The main line holds its course; the branch bows out.
        th = 0.16 * y + spin + PI * s
        glow = _smooth(u / 0.07) * _smooth((1.0 - u) / 0.07) * (0.9 + 0.2 * bump * _clamp(opened))
        return cx + rh * cos(th) + jx, y, rh * sin(th) + jz + 6.0 * bump * opened * s, glow, None
    return place, 0.3 * sin(TAU * now / 9.0), -0.12


LOG_LANE, LOG_PERIOD, LOG_TILT = 20.0, 80.0, 0.38


def build_branch_c(n, rng):
    """Log: the main lane, the branch lane, and commits, on a sheet that scrolls (place along the sheet, jitter)."""
    main, branch, knots = _split(n, (190, 170, 280))
    recs = [(0, 2.0 * LOG_PERIOD * (k + rng.random()) / main, rng.gauss(0, 1.1), 0.0) for k in range(main)]
    u_at = _arc_inverse(lambda u: (_log_branch_x(8.0 + 64.0 * u), 8.0 + 64.0 * u), 400)
    per = -(-branch // 2)
    for k in range(branch):
        w = 8.0 + 64.0 * u_at((k // 2 + rng.random()) / per)
        recs.append((1, w + LOG_PERIOD * (k % 2), rng.gauss(0, 1.1), 0.0))
    for k in range(knots):  # Four commits: a main and a branch commit in each period.
        recs.append((2, rng.uniform(0, TAU), rng.gauss(0, 0.5), k % 4))
    return recs


def _log_branch_x(w):
    if w >= 56.0:
        return -LOG_LANE + 2 * LOG_LANE * _smooth((72.0 - w) / 16.0)
    if w >= 24.0:
        return LOG_LANE
    return -LOG_LANE + 2 * LOG_LANE * _smooth((w - 8.0) / 16.0)


def pose_branch_c(T, now):
    """The history scrolls slowly down a sheet tipped away from you. New commits rise in at the far top, and each
    period a branch forks from the main line, takes a commit, and merges back."""
    scroll = 10.0 * T
    ct, st = cos(LOG_TILT), sin(LOG_TILT)
    span = 2.0 * LOG_PERIOD

    def sheet(xs, v, glow, nrm=None):
        fade = _smooth((54.0 - abs(v)) / 12.0)
        return xs, v * ct + 4.0, v * st, glow * fade, nrm

    def scrolled(w):
        return (w + scroll) % span - LOG_PERIOD

    def in_knot(xs, v):
        for kx in (-LOG_LANE, LOG_LANE):
            for kv in (scrolled(40.0), scrolled(40.0 + LOG_PERIOD)):
                if (xs - kx) ** 2 + (v - kv) ** 2 < (KNOT_R + 1.5) ** 2:
                    return True
        return False

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            v = scrolled(a)
            xs = -LOG_LANE + b
            return sheet(xs, v, 0.0 if in_knot(xs, v) else 1.0)
        if kind == 1:
            v = scrolled(a)
            xs = _log_branch_x(a % LOG_PERIOD) + b
            return sheet(xs, v, 0.0 if in_knot(xs, v) else 1.05)
        kx = -LOG_LANE if c % 2 == 0 else LOG_LANE
        v = scrolled(40.0 + LOG_PERIOD * (c // 2))
        r = KNOT_R + b
        return sheet(kx + r * cos(a), v + r * sin(a), 1.08, (0.0, -st, ct))
    return place, 0.3 * sin(TAU * now / 11.0), -0.05


# ---------------------------------------------------------------------------------------------------------------------
# Cog: using a skill. Solid gears: a toothed face, the tooth tips' side walls, a rim band, a hub and spokes. Their
# backs are not drawn, so no gear reads as two outlines.
# ---------------------------------------------------------------------------------------------------------------------

MESH_A = (10, 20.5, 29.0)  # Teeth, root radius, tip radius.
MESH_B = (7, 13.0, 21.5)
MESH_C1 = (-13.0, 10.0)
MESH_ANGLE = -0.70  # The line from the big gear's centre to the small one's.
MESH_D = 42.5
MESH_C2 = (MESH_C1[0] + MESH_D * cos(MESH_ANGLE), MESH_C1[1] + MESH_D * sin(MESH_ANGLE))


def build_cog_a(n, rng):
    """Mesh: two gears, ten and seven teeth."""
    a, b = _split(n, (370, 270))
    return _gear_recs(0, a, *MESH_A, 8.0, rng) + _gear_recs(1, b, *MESH_B, 8.0, rng, spokes=3, hub=4.5)


def pose_cog_a(T, now):
    """The gears spin up from rest and turn together, each tooth meshing with the other gear's gap."""
    w = 0.85 * (T - 0.7 * (1.0 - exp(-T / 0.7)))
    o1 = MESH_ANGLE - 0.3 * TAU / MESH_A[0]  # A tooth of the big gear faces the small one...
    o2 = MESH_ANGLE + PI - 0.8 * TAU / MESH_B[0]  # ...and a gap of the small gear faces it back.
    r1, r2 = o1 + w, o2 - w * MESH_A[0] / MESH_B[0]
    (x1, y1), (x2, y2) = MESH_C1, MESH_C2

    def place(rec):
        kind = rec[2]
        if kind < 10:
            return _gear_place(kind, rec[3], rec[4], rec[5], x1, y1, 0.0, r1)
        return _gear_place(kind - 10, rec[3], rec[4], rec[5], x2, y2, 0.0, r2)
    return place, 0.24 + 0.1 * sin(TAU * now / 12.0), -0.2


ENGAGE_OUT = (9.0, 24.0)  # Where the small gear waits: out along the mesh line, and toward you.
build_cog_b = build_cog_a  # Engage: the same pair of gears as Mesh.


def _turned(x):
    """The integral of _smooth over [0, x], for x in [0, 1]: how far a smoothly started turn has gone."""
    x = _clamp(x)
    return x ** 3 - 0.5 * x ** 4


def pose_cog_b(T, now):
    """The small gear swings in from in front, tipped, settles into mesh with a click, and the two drive together for
    a few seconds. They ease to a stop, and the small gear swings back out to wait. Both hold still while apart, so the
    teeth meet tooth to gap every time."""
    ph = (T - 1.2) % 5.4 if T >= 1.2 else 0.0
    laps = int((T - 1.2) / 5.4) if T >= 1.2 else 0
    out = 1.0 - _ease_back(ph / 0.7, 1.4) + _smooth((ph - 4.2) / 0.8) if T >= 1.2 else 1.0
    # Speed eases up over 0.5 s from 0.8 s, holds, and eases down over 0.5 s from 3.8 s: angle is its integral.
    w, up, hold = 1.4, 0.5, 2.5
    down = up * (0.5 - _turned(1.0 - (ph - 3.8) / up)) if ph > 3.8 else 0.0
    turn = w * (up * _turned((ph - 0.8) / up) + _clamp(ph - 1.3, 0.0, hold) + down)
    turn += laps * w * (hold + up)
    o1 = MESH_ANGLE - 0.3 * TAU / MESH_A[0]
    o2 = MESH_ANGLE + PI - 0.8 * TAU / MESH_B[0]
    r1, r2 = o1 + turn, o2 - turn * MESH_A[0] / MESH_B[0]
    (x1, y1), (x2, y2) = MESH_C1, MESH_C2
    o = _clamp(out, -0.2, 1.0)
    dx, dz = ENGAGE_OUT[0] * o * cos(MESH_ANGLE), ENGAGE_OUT[1] * o
    dy = ENGAGE_OUT[0] * o * sin(MESH_ANGLE)
    tip = 0.6 * o
    ct, st = cos(tip), sin(tip)

    def place(rec):
        kind = rec[2]
        if kind < 10:
            return _gear_place(kind, rec[3], rec[4], rec[5], x1, y1, 0.0, r1)
        x, y, z, glow, nrm = _gear_place(kind - 10, rec[3], rec[4], rec[5], 0.0, 0.0, 0.0, r2)
        x, z = x * ct + z * st, z * ct - x * st  # Tipped about its upright while it swings in.
        if nrm is not None:
            nrm = (nrm[0] * ct + nrm[2] * st, nrm[1], nrm[2] * ct - nrm[0] * st)
        return x + x2 + dx, y + y2 + dy, z + dz, glow, nrm
    return place, 0.24 + 0.1 * sin(TAU * now / 12.0), -0.2


WORM_Y, WORM_R, WHEEL_C = 26.0, 8.5, (0.0, -12.0)
WHEEL = (16, 25.0, 30.5)
WORM_LEAD = TAU * 27.5 / 16  # One wheel tooth's pitch at its pitch radius.


def build_cog_c(n, rng):
    """Worm: a toothed wheel, the worm's thread, its core and its two bearing collars."""
    wheel, thread, core, collars = _split(n, (330, 200, 70, 40))
    recs = _gear_recs(0, wheel, *WHEEL, 7.0, rng, spokes=5, hub=5.0)
    recs += [(10, -40.0 + 80.0 * s, rng.gauss(0, 0.35), 0.0) for s in _even(thread, rng)]
    recs += [(11, -40.0 + 80.0 * rng.random(), TAU * (k % 6) / 6, 0.0) for k in range(core)]
    recs += [(12, a * TAU, 1.0 if k % 2 else -1.0, 0.0) for k, a in enumerate(_even(collars, rng))]
    return recs


def pose_cog_c(T, now):
    """The worm turns steadily, its thread seeming to travel along it, and each turn of the worm moves the wheel above
    on by one tooth: a slow, strong drive."""
    spin = 2.6 * (T - 0.6 * (1.0 - exp(-T / 0.6)))
    wheel = spin / WHEEL[0] - 0.3 * TAU / WHEEL[0] + PI / 2
    cx, cy = WHEEL_C

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind < 10:
            return _gear_place(kind, a, b, c, cx, cy, 0.0, wheel)
        if kind == 10:  # The thread: a helix whose phase turns with the worm.
            th = TAU * a / WORM_LEAD + spin
            r = WORM_R + b
            return a, WORM_Y - r * cos(th), r * sin(th), 1.12, (0.0, -cos(th), sin(th))
        if kind == 11:
            th = b + spin
            return a, WORM_Y - 4.5 * cos(th), 4.5 * sin(th), 0.6, (0.0, -cos(th), sin(th))
        r = 6.5
        return 42.0 * b, WORM_Y - r * cos(a), r * sin(a), 0.95, (b, 0.0, 0.0)
    return place, 0.3 + 0.1 * sin(TAU * now / 12.0), -0.24


# ---------------------------------------------------------------------------------------------------------------------
# Power: stopping or restarting. The ring is a torus of dust and the bar a solid rod.
# ---------------------------------------------------------------------------------------------------------------------

POWER_R, POWER_TUBE, POWER_GAP = 32.0, 4.4, 0.62


def _ring_pt(al, phi, r=POWER_TUBE, R=POWER_R):
    """The torus at angle al (0 at the top, clockwise) and phi round its tube."""
    ra, rb = sin(al), -cos(al)
    c, s = cos(phi), sin(phi)
    return R * ra + r * c * ra, R * rb + r * c * rb, r * s, (c * ra, c * rb, s)


def build_power_a(n, rng):
    """Close: the open ring and the bar."""
    ring, bar = _split(n, (420, 220))
    recs = [(0, POWER_GAP + (TAU - 2 * POWER_GAP) * s, rng.uniform(0, TAU), rng.gauss(0, 0.3))
            for s in _even(ring, rng)]
    recs += [(1, s, rng.uniform(0, TAU), 1.0 if k % 2 else -1.0) for k, s in enumerate(_even(bar, rng))]
    return recs


def pose_power_a(T, now):
    """Switching off: the bar's dust gathers to the ring's line and parts both ways into the gap, sealing the ring.
    Switching on: the sealed arc's dust gathers back and rises as the bar. Then it holds, on."""
    ph = (T - 0.9) % 4.4 if T >= 0.9 else -1.0
    closing = _smooth((ph - 1.3) / 0.9) if ph >= 0.0 else 0.0
    opening = _ease_back((ph - 2.9) / 0.9, 1.2) if ph >= 0.0 else 0.0
    shut = closing * (1.0 - opening)
    line = -POWER_R * cos(POWER_GAP)
    spin = 0.9 * T

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            x, y, z, nrm = _ring_pt(a, b + spin, POWER_TUBE + c)
            return x, y, z, 1.0, nrm
        by = -48.0 + 40.0 * a
        bx, bz, bn = POWER_TUBE * cos(b + spin), POWER_TUBE * sin(b + spin), (cos(b + spin), 0.0, sin(b + spin))
        if shut <= 0.0:
            return bx, by, bz, 1.05, bn
        reach = min(1.0, abs(by - line) / 21.0)  # Grains far from the ring's line fill the gap's ends.
        e = _smooth(shut * 1.6 - 0.6 * reach) if shut < 1.0 else 1.0
        x, y, z, nrm = _ring_pt(c * (POWER_GAP + 0.35) * reach, b + spin)  # Spread past the ends: no bright cap.
        return bx + (x - bx) * e, by + (y - by) * e, bz + (z - bz) * e, 1.05, nrm if e > 0.5 else bn
    return place, 0.3 * sin(TAU * now / 10.0), -0.14


def build_power_b(n, rng):
    """Lever: the open ring, the bar as a lever, and the pivot's collar."""
    ring, lever, pivot = _split(n, (400, 200, 40))
    recs = [(0, POWER_GAP + (TAU - 2 * POWER_GAP) * s, rng.uniform(0, TAU), rng.gauss(0, 0.3))
            for s in _even(ring, rng)]
    recs += [(1, s, rng.uniform(0, TAU), 0.0) for s in _even(lever, rng)]
    recs += [(2, rng.uniform(-1.0, 1.0), a * TAU, 0.0) for a in _even(pivot, rng)]
    return recs


def pose_power_b(T, now):
    """The bar is a lever pivoting at the ring's centre. It flicks down and out toward you, off, holds, and flicks
    back up through the gap, on, with a small overshoot: a restart."""
    ph = (T - 0.9) % 4.0 if T >= 0.9 else -1.0
    off = _ease_back((ph - 1.2) / 0.42, 1.0) if ph >= 0.0 else 0.0
    on = _ease_back((ph - 2.5) / 0.5, 1.4) if ph >= 0.0 else 0.0
    psi = 2.45 * (off - on)
    dx, dy, dz = 0.0, -cos(psi), sin(psi)
    e2 = (0.0, sin(psi), cos(psi))

    def place(rec):
        kind, a, b = rec[2], rec[3], rec[4]
        if kind == 0:
            x, y, z, nrm = _ring_pt(a, b, POWER_TUBE + rec[5])
            return x, y, z, 1.0, nrm
        if kind == 1:
            d = 7.0 + 39.0 * a
            c, s = cos(b), sin(b)
            nx, ny, nz = c, s * e2[1], s * e2[2]
            r = POWER_TUBE
            return dx * d + r * nx, dy * d + r * ny, dz * d + r * nz, 1.08, (nx, ny, nz)
        c, s = cos(b), sin(b)
        return 6.0 * a, 6.0 * c, 6.0 * s, 0.9, (0.0, c, s)
    return place, 0.42 + 0.1 * sin(TAU * now / 10.0), -0.12


BUTTON_R, BEZEL = 34.0, (37.0, 43.0)


def build_power_c(n, rng):
    """Press: the bezel, the button's side wall and face rim, the power mark on its face, and the face itself."""
    bezel, wall, rim, mark_ring, mark_bar, face = _split(n, (80, 120, 70, 210, 80, 80))
    recs = [(0, a * TAU, rng.uniform(*BEZEL), 0.0) for a in _even(bezel, rng)]
    recs += [(1, a * TAU, rng.random(), 0.0) for a in _even(wall, rng)]
    recs += [(2, a * TAU, rng.gauss(0, 0.4), 0.0) for a in _even(rim, rng)]
    recs += [(3, POWER_GAP + (TAU - 2 * POWER_GAP) * s, rng.gauss(0, 1.0), 0.0) for s in _even(mark_ring, rng)]
    recs += [(4, s, rng.gauss(0, 1.0), 0.0) for s in _even(mark_bar, rng)]
    while len(recs) < n:
        r, th = BUTTON_R * sqrt(rng.uniform(0.05, 0.93)), rng.uniform(0, TAU)
        x, y = r * cos(th), r * sin(th)
        if abs(math.hypot(x, y) - 23.0) > 5.0 and not (abs(x) < 5.0 and y < -6.0):
            recs.append((5, x, y, 0.0))
    return recs


def pose_power_c(T, now):
    """A round power button seen from above. It presses down into its bezel, the mark brightening as it gives, holds
    a moment, and springs back up with a small overshoot."""
    ph = (T - 0.9) % 3.0 if T >= 0.9 else -1.0
    down = _ease_out((ph - 0.9) / 0.18) if ph >= 0.0 else 0.0
    up = _ease_back((ph - 1.35) / 0.5, 1.6) if ph >= 0.0 else 0.0
    press = down * (1.0 - up)
    h = 12.0 - 8.5 * press
    mark = 1.15 + 0.3 * _clamp(press)
    top = (0.0, -1.0, 0.0)

    def place(rec):
        kind, a, b = rec[2], rec[3], rec[4]
        if kind == 0:
            return b * cos(a), 0.0, b * sin(a), 0.5, top
        if kind == 1:
            return BUTTON_R * cos(a), -h * b, BUTTON_R * sin(a), 0.6, (cos(a), 0.0, sin(a))
        if kind == 2:
            r = BUTTON_R + b
            return r * cos(a), -h, r * sin(a), 0.8, top
        if kind == 3:
            r = 23.0 + 1.3 * b
            return r * sin(a), -h, -r * cos(a), mark, top
        if kind == 4:
            return 1.3 * b, -h, -33.0 + 26.0 * a, mark, top
        return a, -h, b, 0.4, top
    return place, 0.25 * sin(TAU * now / 11.0), -0.66


# ---------------------------------------------------------------------------------------------------------------------
# Tiles: arranging windows. Each tile is a panel of dust, filled, with a brighter edge.
# ---------------------------------------------------------------------------------------------------------------------

TILE_W, TILE_H = 38.0, 28.0
SLOTS = ((-22.0, -16.5), (22.0, -16.5), (22.0, 16.5), (-22.0, 16.5))  # Clockwise from the top left.


def _rect_edge(n, rng, w, h, cx=0.0, cy=0.0):
    """n points evenly round a w x h rectangle's outline centred at (cx, cy)."""
    out, per = [], 2 * (w + h)
    for s in _even(n, rng, 0.3):
        d = s * per
        if d < w:
            x, y = -w / 2 + d, -h / 2
        elif d < w + h:
            x, y = w / 2, -h / 2 + d - w
        elif d < 2 * w + h:
            x, y = w / 2 - (d - w - h), h / 2
        else:
            x, y = -w / 2, h / 2 - (d - 2 * w - h)
        out.append((cx + x + rng.gauss(0, 0.35), cy + y + rng.gauss(0, 0.35)))
    return out


def _tile_recs(tile, n, rng, w=TILE_W, h=TILE_H):
    """A tile's grains: (tile, x, y, edge) in the tile's own plane."""
    edge = int(n * 0.56)
    recs = [(tile, x, y, 1.0) for x, y in _rect_edge(edge, rng, w, h)]
    for _ in range(n - edge):
        recs.append((tile, rng.uniform(-w / 2 + 2, w / 2 - 2), rng.uniform(-h / 2 + 2, h / 2 - 2), 0.0))
    return recs


def _tile_place(x, y, cx, cy, cz, rx, ry, glow):
    """A tile grain at (x, y) in a tile centred at (cx, cy, cz), tipped by rx about x and ry about y."""
    cy_, sy_, cx_, sx_ = cos(ry), sin(ry), cos(rx), sin(rx)
    px, pz = x * cy_, -x * sy_
    py, pz = y * cx_ - pz * sx_, y * sx_ + pz * cx_
    nrm = (sy_, -cy_ * sx_, cy_ * cx_)
    return cx + px, cy + py, cz + pz, glow, nrm


def build_tiles_a(n, rng):
    """Snap: four tiles."""
    recs = []
    for k, m in enumerate(_split(n, (1, 1, 1, 1))):
        recs += [(10 + r[0],) + r[1:] for r in _tile_recs(k, m, rng)]
    return recs


SCATTER = ((-15.0, -11.0, 12.0, 0.35, 0.5), (15.0, -12.0, -10.0, -0.3, -0.45),
           (14.0, 12.0, 10.0, 0.4, -0.5), (-16.0, 11.0, -12.0, -0.35, 0.45))  # dx, dy, dz, rx, ry per slot.


def pose_tiles_a(T, now):
    """The tiles fly in loose and tipped and snap into a two by two grid, one after another, with a click of
    overshoot. Later they drift a little apart, loosen and tip, and snap back together."""
    ph = (T - 1.6) % 4.4 if T >= 1.6 else -1.0
    apart = []
    for k in range(4):
        if ph < 0.0:
            f = 1.0 - _ease_back((T - 0.45 - 0.1 * k) / 0.45, 1.5)
        else:
            f = 0.5 * _smooth((ph - 1.5) / 1.1) * (1.0 - _ease_back((ph - 2.6 - 0.09 * k) / 0.42, 1.5))
        apart.append(f)

    def place(rec):
        k = rec[2] - 10
        f = apart[k]
        sx, sy = SLOTS[k]
        dx, dy, dz, rx, ry = SCATTER[k]
        return _tile_place(rec[3], rec[4], sx + dx * f, sy + dy * f, dz * f, rx * f, ry * f,
                           0.6 + 0.55 * rec[5])
    return place, 0.32 + 0.1 * sin(TAU * now / 12.0), -0.22


SPLIT_W, SPLIT_H, SPLIT_GAP = 88.0, 64.0, 6.0


def build_tiles_b(n, rng):
    """Split: one window's grains (x, y, role): role 1 its outer edge, 2 the upright seam, 3 the right half's level
    seam, 0 its fill."""
    outer, seam_v, seam_h = _split(int(n * 0.5), (200, 80, 44))
    recs = [(0, x, y, 1) for x, y in _rect_edge(outer, rng, SPLIT_W, SPLIT_H)]
    for k, s in enumerate(_even(seam_v, rng)):
        recs.append((0, -0.01 if k % 2 else 0.01, -SPLIT_H / 2 + SPLIT_H * s, 2))
    for k, s in enumerate(_even(seam_h, rng)):
        recs.append((0, SPLIT_W / 2 * s, -0.01 if k % 2 else 0.01, 3))
    while len(recs) < n:
        recs.append((0, rng.uniform(-SPLIT_W / 2 + 2, SPLIT_W / 2 - 2), rng.uniform(-SPLIT_H / 2 + 2, SPLIT_H / 2 - 2), 0))
    return recs


def pose_tiles_b(T, now):
    """One window splits down the middle: its dust parts along a seam that brightens into two edges, and the halves
    slide apart. Then the right half splits across, the new tile lifting toward you as it parts. Later the seams close
    and the dust settles back into one window."""
    ph = (T - 0.8) % 5.2 if T >= 0.8 else -1.0
    if ph < 0.0:
        g1 = g2 = 0.0
    else:
        close = _smooth((ph - 3.6) / 0.8)
        g1 = _ease_back((ph - 0.2) / 0.5, 1.4) * (1.0 - _smooth((ph - 3.9) / 0.8))
        g2 = _ease_back((ph - 1.3) / 0.5, 1.4) * (1.0 - close)
    hw, hh = SPLIT_W / 2, SPLIT_H / 2
    lift = 5.0 * _clamp(g2) * (1.0 if ph < 2.6 else 1.0 - _smooth((ph - 2.6) / 0.6))

    def place(rec):
        x, y, role = rec[3], rec[4], rec[5]
        gx, gy = SPLIT_GAP * g1 / 2, 0.0
        nx = (gx + abs(x) * (hw - gx) / hw) * (1.0 if x > 0 else -1.0)
        ny, z = y, 0.0
        if x > 0:
            gy = SPLIT_GAP * g2 / 2
            ny = (gy + abs(y) * (hh - gy) / hh) * (1.0 if y > 0 else -1.0)
            z = lift if y > 0 else 0.0
        if role == 1:
            glow = 1.15
        elif role == 2:
            glow = 1.15 * _clamp(g1 * 1.3)
        elif role == 3:
            glow = 1.15 * _clamp(g2 * 1.3)
        else:
            glow = 0.5
        return nx, ny, z, glow, FACE_Z
    return place, 0.32 + 0.1 * sin(TAU * now / 12.0), -0.2


def build_tiles_c(n, rng):
    """Slide: three tiles in a two by two grid with one slot free."""
    recs = []
    for k, m in enumerate(_split(n, (1, 1, 1))):
        recs += [(10 + r[0],) + r[1:] for r in _tile_recs(k, m, rng)]
    return recs


SLIDE_STEP = 1.4  # Seconds per move.


def pose_tiles_c(T, now):
    """A sliding puzzle: the free slot travels round the grid, and each move a tile lifts, slides into it and lands
    with a small overshoot."""
    t = max(0.0, T - 0.9)
    moves = int(t / SLIDE_STEP)
    q = _ease_back((t - moves * SLIDE_STEP) / 0.85, 0.8) if T >= 0.9 else 0.0
    slot = [1, 2, 3]  # Tile k's slot; the free slot starts at 0.
    gap = 0
    for m in range(moves % 12):
        k = slot.index((gap + 1) % 4)
        slot[k], gap = gap, (gap + 1) % 4
    mover = slot.index((gap + 1) % 4) if T >= 0.9 else -1
    poses = []
    for k in range(3):
        x, y = SLOTS[slot[k]]
        z, rx, ry = 0.0, 0.0, 0.0
        if k == mover:
            x1, y1 = SLOTS[gap]
            bump = sin(PI * _clamp(q))
            x, y = x + (x1 - x) * q, y + (y1 - y) * q
            z = 6.0 * bump
            rx, ry = -0.12 * bump * (y1 - SLOTS[slot[k]][1]) / 33.0, 0.12 * bump * (x1 - SLOTS[slot[k]][0]) / 44.0
        poses.append((x, y, z, rx, ry))

    def place(rec):
        x, y, z, rx, ry = poses[rec[2] - 10]
        return _tile_place(rec[3], rec[4], x, y, z, rx, ry, 0.6 + 0.55 * rec[5])
    return place, 0.32 + 0.1 * sin(TAU * now / 12.0), -0.22


# ---------------------------------------------------------------------------------------------------------------------
# Film: media. A reel is a solid disc: its rim and rim wall, round windows, a hub and a light fill.
# ---------------------------------------------------------------------------------------------------------------------

def _reel_recs(rid, n, rng, R, windows, rw, dw, hub):
    rim, wall, win, hb, fill = _split(n, (18, 15, 35, 7, 25))
    recs = [(rid * 10, a * TAU, rng.gauss(0, 0.4), 0.0) for a in _even(rim, rng)]
    recs += [(rid * 10 + 1, a * TAU, rng.random(), 0.0) for a in _even(wall, rng)]
    recs += [(rid * 10 + 2, k % windows, a * TAU, rng.gauss(0, 0.35)) for k, a in enumerate(_even(win, rng))]
    recs += [(rid * 10 + 3, a * TAU, rng.gauss(0, 0.3), 0.0) for a in _even(hb, rng)]
    while fill:
        r, th = rng.uniform(hub + 2.5, R - 2.5), rng.uniform(0, TAU)
        if all(math.hypot(r * cos(th) - dw * cos(TAU * w / windows), r * sin(th) - dw * sin(TAU * w / windows)) > rw + 2
               for w in range(windows)):
            recs.append((rid * 10 + 4, th, r, 0.0))
            fill -= 1
    return recs


def _reel_place(part, a, b, c, cx, cy, rot, R, depth, windows, rw, dw, hub):
    if part == 2:
        wa = TAU * a / windows + rot
        x, y = cx + dw * cos(wa) + (rw + c) * cos(b), cy + dw * sin(wa) + (rw + c) * sin(b)
        return x, y, depth / 2, 1.05, FACE_Z
    th = a + rot
    ct, st = cos(th), sin(th)
    if part == 1:
        return cx + R * ct, cy + R * st, depth / 2 - depth * b, 0.85, (ct, st, 0.0)
    r = (R + b) if part == 0 else (hub + b) if part == 3 else b
    return cx + r * ct, cy + r * st, depth / 2, (1.1, 0, 0, 1.0, 0.45)[part], FACE_Z


def _strip_recs(sid, n, rng, length, width):
    """A film strip's grains: (sid, place along it in px, across, role): role 0 an edge, 1 a sprocket hole, 2 a frame
    divider."""
    edges, holes, dividers = _split(n, (46, 30, 24))
    recs = [(sid, length * s, (width / 2) * (1 if k % 2 else -1) + rng.gauss(0, 0.3), 0)
            for k, s in enumerate(_even(edges, rng))]
    pitch = 6.0
    for k in range(holes):
        slot = (k // 2) % int(length / pitch)
        recs.append((sid, slot * pitch + rng.uniform(0, 2.2), (1 if k % 2 else -1) * (width / 2 - 2.6), 1))
    frame = 13.0
    frames = max(1, int(length / frame))
    for k in range(dividers):
        recs.append((sid, (k % frames) * frame + rng.gauss(0, 0.25), rng.uniform(-width / 2 + 4, width / 2 - 4), 2))
    return recs


def _strip_place(path, s0, across, role, shift, ends=(0.0, 0.15)):
    """A strip grain, carried shift px along the path. The strip thins away over the shares ends gives at each end."""
    s = ((s0 + shift) % path.length) / path.length
    x, y, z, tx, ty, _ = path.at(s)
    m = math.hypot(tx, ty) or 1.0
    nx, ny = -ty / m, tx / m
    fade = (_smooth(s / ends[0]) if ends[0] else 1.0) * _smooth((1.0 - s) / ends[1])
    return x + nx * across, y + ny * across, z, (0.95, 1.0, 0.8)[role] * fade, None


REEL_A = dict(R=33.0, windows=5, rw=8.0, dw=19.5, hub=5.0)
REEL_A_C = (-12.0, -13.0)
STRIP_A = _Path(lambda u: _bez(((-12.0, 20.5, 4.0), (8.0, 20.5, 4.0), (26.0, 21.0, 8.0), (44.0, 36.0, 12.0)), u))


def build_film_a(n, rng):
    """Reel: one reel, and the film leaving it."""
    reel, strip = _split(n, (400, 240))
    return _reel_recs(0, reel, rng, **REEL_A) + _strip_recs(99, strip, rng, STRIP_A.length, 14.0)


def pose_film_a(T, now):
    """The reel turns and unspools: the film runs off its foot at the rim's own speed, frames and sprocket holes
    travelling out along the strip, which curls toward you and thins away at its end."""
    w = 0.55 * (T - 0.6 * (1.0 - exp(-T / 0.6)))
    rot = -w
    shift = w * REEL_A["R"]
    cx, cy = REEL_A_C

    def place(rec):
        kind = rec[2]
        if kind != 99:
            return _reel_place(kind, rec[3], rec[4], rec[5], cx, cy, rot, depth=8.0, **REEL_A)
        return _strip_place(STRIP_A, rec[3], rec[4], rec[5], shift)
    return place, 0.4 + 0.12 * sin(TAU * now / 12.0), -0.2


STRIP_W, FRAME, HOLE = 32.0, 24.0, 6.0  # The film's width, a frame's length, and the sprocket holes' pitch.
STRIP_B = _Path(lambda u: (54.0 * sin(-1.15 + 2.3 * u), 12.0 - 24.0 * u + 6.0 * sin(PI * u),
                           54.0 * cos(-1.15 + 2.3 * u) - 40.0))


def build_film_b(n, rng):
    """Strip: a wide strip of film. Records are (role, place along it in px, across): role 0 an edge, 1 a sprocket
    hole, 2 a frame line, 3 a frame's faint picture."""
    edges, holes, lines, fill = _split(n, (220, 120, 150, 150))
    L = STRIP_B.length
    recs = [(0, L * s, (STRIP_W / 2) * (1 if k % 2 else -1) + rng.gauss(0, 0.3)) for k, s in enumerate(_even(edges, rng))]
    slots = int(L / HOLE)
    for k in range(holes):
        recs.append((1, (k // 2 % slots) * HOLE + rng.uniform(0, 2.4), (1 if k % 2 else -1) * (STRIP_W / 2 - 3.2)))
    frames = int(L / FRAME)
    for k in range(lines):
        recs.append((2, (k % frames) * FRAME + rng.gauss(0, 0.25), rng.uniform(-STRIP_W / 2 + 6.0, STRIP_W / 2 - 6.0)))
    for _ in range(fill):
        recs.append((3, rng.uniform(0, L), rng.uniform(-STRIP_W / 2 + 7.0, STRIP_W / 2 - 7.0)))
    return recs


def pose_film_b(T, now):
    """A strip of film curves round in front of you and slides steadily along its length, frame after frame, as if
    running through a projector's gate. It thins away at both ends."""
    shift = 15.0 * T
    L = STRIP_B.length

    def place(rec):
        role, s0, across = rec[2], rec[3], rec[4]
        s = ((s0 + shift) % L) / L
        x, y, z, tx, ty, tz = STRIP_B.at(s)
        # Across the film is upright, square to its run: (0, 1, 0) less its share along the tangent.
        ax, ay, az = -ty * tx, 1.0 - ty * ty, -ty * tz
        m = sqrt(ax * ax + ay * ay + az * az) or 1.0
        ax, ay, az = ax / m, ay / m, az / m
        nrm = (ty * az - tz * ay, tz * ax - tx * az, tx * ay - ty * ax, 1)
        glow = (1.05, 0.95, 0.9, 0.32)[role] * _smooth(s / 0.12) * _smooth((1.0 - s) / 0.12)
        return x + ax * across, y + ay * across, z + az * across, glow, nrm
    return place, 0.12 * sin(TAU * now / 12.0), -0.18


CLAP_HINGE = (-42.0, -7.0)


def build_film_c(n, rng):
    """Clapper: the board's outline, its lines and fill, the striped band, the hinged stick, and the stick's foot
    (which kicks up dust as it claps)."""
    board, text, band, stick, stripes, foot, hinge = _split(n - 110, (150, 50, 90, 130, 60, 40, 10))
    recs = []
    recs += [(0, x, y, 1.05) for x, y in _rect_edge(board, rng, 84.0, 46.0, 0.0, 17.0)]
    for k in range(text):
        row = k % 2
        recs.append((0, -32.0 + rng.random() * (44.0 if row == 0 else 30.0), 18.0 + 11.0 * row + rng.gauss(0, 0.4), 0.85))
    seam = band // 3
    for s in _even(seam, rng):
        recs.append((0, -42.0 + 84.0 * s, 4.0 + rng.gauss(0, 0.35), 1.0))
    for k in range(band - seam):  # Board stripes lean one way...
        x0, q = -34.0 + 16.0 * (k % 5), rng.random()
        recs.append((0, x0 + 7.0 * q, 4.0 - 10.0 * q, 1.0))
    recs += [(1, x, y, 1.08) for x, y in _rect_edge(stick, rng, 84.0, 11.0, 0.0, -12.5)]  # The stick, above the board.
    for k in range(stripes):  # ...and the stick's stripes lean the other.
        x0, q = -34.0 + 16.0 * (k % 5), rng.random()
        recs.append((1, x0 + 7.0 * q, -7.0 - 11.0 * q, 1.0))
    for k in range(foot):
        recs.append((2, -40.0 + 82.0 * rng.random(), rng.uniform(-PI, 0.0), rng.uniform(0.5, 1.0)))
    for a in _even(hinge, rng):
        recs.append((3, a * TAU, 0.0, 0.0))
    while len(recs) < n:
        recs.append((0, rng.uniform(-39.0, 39.0), rng.uniform(7.0, 37.0), 0.42))
    return recs


def pose_film_c(T, now):
    """A clapperboard. The stick lifts slowly on its hinge, holds, and claps shut with a small bounce. As it claps,
    dust kicks up off the seam and settles back."""
    ph = (T - 0.7) % 2.8 if T >= 0.7 else -1.0
    if ph < 0.0:
        ang = 0.0
    elif ph < 1.5:
        ang = 0.42 * _smooth(ph / 0.8)
    elif ph < 1.62:
        ang = 0.42 * (1.0 - ((ph - 1.5) / 0.12) ** 2)  # Falling faster and faster: the clap.
    else:
        ang = 0.05 * sin((ph - 1.62) * 18.0) * exp(-(ph - 1.62) / 0.09)  # A small bounce.
    since = (ph - 1.62) % 2.8 if T >= 0.7 + 1.62 else 9.0
    ca, sa = cos(ang), sin(ang)
    hx, hy = CLAP_HINGE
    kick = (since / 0.07) * exp(1.0 - since / 0.07) if since < 1.0 else 0.0

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            return a, b, 0.0, c, FACE_Z
        if kind == 1:
            dx, dy = a - hx, b - hy
            return hx + dx * ca + dy * sa, hy - dx * sa + dy * ca, 0.35 * dx * sa, c, FACE_Z
        if kind == 2:  # The stick's foot: on its lower edge, kicked out as it lands.
            dx = a - hx
            x, y = hx + dx * ca, hy - dx * sa
            d = 11.0 * c * kick
            return x + d * cos(b), y + d * sin(b) * 0.9, 3.0 * kick, 1.0 - 0.4 * _clamp(kick), None
        return hx + 2.6 * cos(a), hy + 2.6 * sin(a), 1.0, 1.0, None
    return place, 0.34 + 0.1 * sin(TAU * now / 11.0), -0.16


# ---------------------------------------------------------------------------------------------------------------------
# Spinner: a background job, always quietly working.
# ---------------------------------------------------------------------------------------------------------------------

def build_spinner_a(n, rng):
    """Orbit: a small dust world and a broad ring of dust round it, with three thicker arcs."""
    core, ring = _split(n, (170, 470))
    recs = []
    for k in range(core):  # A Fibonacci sphere: even dust over the world.
        y = 1.0 - 2.0 * (k + 0.5) / core
        recs.append((0, math.acos(y), 2.39996 * k, 0.0))
    for k in range(ring):
        if k % 5 < 3:  # Three arcs carry most of the dust...
            a = TAU * (k % 3) / 3 + rng.gauss(0, 0.32)
        else:  # ...and a thin even sheet carries the rest.
            a = rng.uniform(0, TAU)
        recs.append((1, a, 23.0 + 18.0 * rng.random() ** 1.3, rng.uniform(0, TAU)))
    return recs


def pose_spinner_a(T, now):
    """The ring of dust turns steadily round the world, its arcs coming toward you and away, each grain riding a
    little up and down; the world turns slowly the other way."""
    spin = 0.8 * T
    world = -0.35 * T
    roll = 0.3
    cr, sr = cos(roll), sin(roll)

    def place(rec):
        kind, a, b, c = rec[2], rec[3], rec[4], rec[5]
        if kind == 0:
            st, th = sin(a), b + world
            lx, ly, lz = st * cos(th), cos(a), st * sin(th)
            x, y = lx * cr - ly * sr, lx * sr + ly * cr
            return 12.0 * x, 12.0 * y, 12.0 * lz, 0.85, (x, y, lz)
        th = a + spin
        lift = 0.9 * sin(1.3 * T + c)
        x, y, z = b * cos(th), lift, b * sin(th)
        x, y = x * cr - y * sr, x * sr + y * cr
        return x, y, z, 0.95, None
    return place, 0.15 * sin(TAU * now / 13.0), -0.38


COIL_R, COIL_TUBE, COIL_TURNS = 30.0, 9.0, 10


def build_spinner_b(n, rng):
    """Coil: two helices wound round a ring, and a faint skin on the ring."""
    helix, skin = _split(n, (520, 120))
    recs = [(k % 2, TAU * s, rng.gauss(0, 0.35), 0.0) for k, s in enumerate(_even(helix, rng))]
    recs += [(2, rng.uniform(0, TAU), rng.uniform(0, TAU), 0.0) for _ in range(skin)]
    return recs


def pose_spinner_b(T, now):
    """A coil wound round a ring, like a spring bent into a circle. Its turns crawl steadily round the ring, so it
    always looks at work, while the ring itself turns slowly."""
    crawl, turn = -1.7 * T, 0.18 * T

    def place(rec):
        kind, th, b = rec[2], rec[3], rec[4]
        if kind < 2:
            phi = COIL_TURNS * th + crawl + PI * kind
            r, glow = COIL_TUBE + b, 1.05
        else:
            phi, r, glow = b, COIL_TUBE, 0.42
        th += turn
        cp, sp, ct, st = cos(phi), sin(phi), cos(th), sin(th)
        R = COIL_R + r * cp
        return R * ct, r * sp, R * st, glow, (cp * ct, sp, cp * st)
    return place, 0.12 * sin(TAU * now / 13.0), -0.62


MOBIUS_R, MOBIUS_W = 30.0, 11.0


def build_spinner_c(n, rng):
    """Mobius: the band's one edge, rungs across it, and a light fill (angle round, place across)."""
    edge, rungs, fill = _split(n, (240, 170, 230))
    recs = [(0, TAU * s, 1.0 if k % 2 else -1.0, 0.0) for k, s in enumerate(_even(edge, rng))]
    rows = -(-rungs // 17)
    recs += [(1, TAU * (k % 17) / 17, -1.0 + 2.0 * ((k // 17) + 0.5) / rows, 0.0) for k in range(rungs)]
    recs += [(2, rng.uniform(0, TAU), rng.uniform(-0.9, 0.9), 0.0) for _ in range(fill)]
    return recs


def pose_spinner_c(T, now):
    """A Mobius band, Rook's loop given a twist and a width. The band slides along itself without end, its rungs
    rolling through the twist, and it turns slowly as a whole."""
    flow, turn = 0.42 * T, 0.2 * T

    def place(rec):
        kind, th, s = rec[2], rec[3] + flow, rec[4] * MOBIUS_W
        h = th / 2.0
        ch, sh = cos(h), sin(h)
        a = th + turn
        ca, sa = cos(a), sin(a)
        R = MOBIUS_R + s * ch
        # The band's normal: across-vector (ch ca, sh, ch sa) crossed with the tangent (-sa, 0, ca).
        nrm = (sh * ca, -ch, sh * sa, 1)
        glow = (1.1, 1.0, 0.45)[kind]
        return R * ca, s * sh, R * sa, glow, nrm
    return place, 0.18 * sin(TAU * now / 13.0), -0.55


# ---------------------------------------------------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------------------------------------------------

FORMS = {
    "eye2_a": (build_eye_a, pose_eye_a), "eye2_b": (build_eye_b, pose_eye_b), "eye2_c": (build_eye_c, pose_eye_c),
    "branch2_a": (build_branch_a, pose_branch_a), "branch2_b": (build_branch_b, pose_branch_b),
    "branch2_c": (build_branch_c, pose_branch_c),
    "cog2_a": (build_cog_a, pose_cog_a), "cog2_b": (build_cog_b, pose_cog_b), "cog2_c": (build_cog_c, pose_cog_c),
    "power2_a": (build_power_a, pose_power_a), "power2_b": (build_power_b, pose_power_b),
    "power2_c": (build_power_c, pose_power_c),
    "tiles2_a": (build_tiles_a, pose_tiles_a), "tiles2_b": (build_tiles_b, pose_tiles_b),
    "tiles2_c": (build_tiles_c, pose_tiles_c),
    "film2_a": (build_film_a, pose_film_a), "film2_b": (build_film_b, pose_film_b),
    "film2_c": (build_film_c, pose_film_c),
    "spinner2_a": (build_spinner_a, pose_spinner_a), "spinner2_b": (build_spinner_b, pose_spinner_b),
    "spinner2_c": (build_spinner_c, pose_spinner_c),
}
# Each form's scale, so it stands about as large as the hourglass, the standard: tall forms about 110 px, round ones
# about 105 px across.
FIT = {"eye2_a": 1.15, "eye2_b": 1.15, "eye2_c": 1.15, "branch2_a": 1.08, "tiles2_a": 1.05,
       "film2_a": 1.05, "cog2_a": 1.3, "cog2_b": 1.2, "cog2_c": 1.3, "power2_a": 1.25, "power2_b": 1.2, "power2_c": 1.25,
       "tiles2_b": 1.2, "tiles2_c": 1.2, "film2_c": 1.1, "spinner2_a": 1.35, "spinner2_b": 1.35,
       "spinner2_c": 1.3}


def _project(name, recs, T, now):
    """Project records at form time T: (tx, ty, tb, tz)."""
    meta = dp.FORMS_META.get(name) or {}
    inv = 1.0 / float(meta.get("persp", 320.0))
    place, yaw, pitch = FORMS[name][1](T, now)
    cy, sy, cp, sp = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
    k = FIT.get(name, 1.0)
    tx, ty, tb, tz = [], [], [], []
    for rec in recs:
        x, y, z, glow, nrm = place(rec)
        x, y, z = x * k, y * k, z * k
        x1 = x * cy + z * sy
        z1 = z * cy - x * sy
        y2 = y * cp - z1 * sp
        z2 = y * sp + z1 * cp
        if nrm is not None and glow > 0.0:
            nz = nrm[1] * sp + (nrm[2] * cy - nrm[0] * sy) * cp
            if len(nrm) > 3:
                nz = abs(nz)
            glow *= 0.35 + 0.65 * _smooth(0.5 + nz)
        p = 1.0 / (1.0 - z2 * inv)
        zn = z2 / 46.0
        zn = -1.0 if zn < -1.0 else 1.0 if zn > 1.0 else zn
        tx.append(x1 * p)
        ty.append(y2 * p)
        tb.append((0.30 + 1.08 * (0.5 + 0.5 * zn) ** 1.25) * glow)
        tz.append(zn)
    return tx, ty, tb, tz


def _builder(name):
    def build(grains, rng):
        recs = [(0.0, 0.0) + tuple(r) for r in FORMS[name][0](grains, rng)]
        assert len(recs) == grains, (name, len(recs))
        tx, ty, _, _ = _project(name, recs, REF_T, REF_T)
        recs = [r[2:] for r in recs]
        return [r for _, r in sorted(((math.atan2(y, x), (x, y) + tuple(rec)) for x, y, rec in zip(tx, ty, recs)),
                                     key=lambda p: p[0])]
    return build


BUILDERS = {name: _builder(name) for name in FORMS}


def EVAL(name, points, scene, now):
    """devs_pack's eval_targets for these forms: (tx, ty, tb, tz)."""
    return _project(name, points, max(0.0, now - scene.form_at), now)


def register(pack):
    """Add these forms to devs_pack, given its globals: the builders, and EVAL ahead of its eval_targets."""
    pack["BUILDERS"].update(BUILDERS)
    rest = pack["eval_targets"]
    pack["eval_targets"] = lambda name, points, scene, now: (
        EVAL(name, points, scene, now) if name in FORMS else rest(name, points, scene, now))


if __name__ == "__main__":
    # Every form has the Devs grain count and a manifest entry, and stays inside the 124 px form box.
    import types
    trouble = []
    for name, build in BUILDERS.items():
        pts = build(640, random.Random(sum(map(ord, name))))
        assert len(pts) == 640, (name, len(pts))
        assert name in dp.FORMS_META, f"{name} has no manifest entry"
        box = [0.0, 0.0, 0.0, 0.0]
        for step in range(360):
            tx, ty, tb, _ = EVAL(name, pts, types.SimpleNamespace(form_at=0.0), step / 30.0)
            lit = [(x, y) for x, y, b in zip(tx, ty, tb) if b > 0.05]
            box = [min(box[0], *(x for x, _ in lit)), max(box[1], *(x for x, _ in lit)),
                   min(box[2], *(y for _, y in lit)), max(box[3], *(y for _, y in lit))]
        print(f"{name:11s} x {box[0]:6.1f} .. {box[1]:5.1f}   y {box[2]:6.1f} .. {box[3]:5.1f}")
        if not (-62 <= box[0] and box[1] <= 62 and -62 <= box[2] and box[3] <= 62):
            trouble.append(name)
    assert not trouble, f"outside the form box: {trouble}"
    print("ok")
