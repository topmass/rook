"""Round two of the gold-dust icons for WoW mode's six game lookups: figure (find_npc), exclaim (find_quest), chest
(find_item), sword (find_upgrades), coins (find_price) and pickaxe (find_object). Each icon has three sketches,
<icon>2_a, _b and _c in themes/devs/manifest.json, for the owner to pick from; overlay.ACTIVITY_FORMS names the
picks. Round three adds new swords (sword3_a to _c) and a logical dig (pickaxe3_c and _d), not yet mapped.

What makes all eighteen Devs, and nothing else is shared:
- Gold dust on true 3D solids. Grains sit on the object's surfaces, lit by one key light from the upper left. A
  surface that faces away goes dark, so a box reads as a solid box, not as a front and a back outline.
- The send forms' morph (devs_pack.eval_send_tech). The grains first ride the resting loop. Each part then leaves the
  loop from the stretch nearest where it lands, flies there and locks with a small overshoot. When the form ends, the
  overlay's springs carry each grain back to its own place on the loop.
- Motion that comes from the object itself: a lid opens, a coin turns, a pick swings. Loose dust flows, gathers,
  parts and settles. No sketch has a glowing bead, an orb or any roving point of light.
"""

from __future__ import annotations

import math

import devs_pack as dp

TAU = 2.0 * math.pi
sin, cos, sqrt, exp = math.sin, math.cos, math.sqrt, math.exp
MORPH, FLY, ALIGN = dp.SEND_MORPH, 0.55, 0.5  # The loop holds, a grain's flight, a part's lock (as the send forms).
PERSP = 320.0
_KEY = (-0.42, -0.62, 0.66)  # The key light, from the upper left and in front, in view space.
LIGHT = tuple(c / math.hypot(*_KEY) for c in _KEY)
FOOT = 4.0  # Each form's box is centred this far below the presence's centre, as the flat forms sit.
BOX_W, BOX_H = 126.0, 114.0  # The most a form covers over its hold, as FORM_FIT sizes the flat forms.
I3, O3 = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0)
_smooth, _ease_out, _ease_back = dp._smooth, dp._ease_out, dp._ease_back


# ---------------------------------------------------------------------------
# Matrices: 3x3, row by row. y points down, as on screen, and z toward the viewer.
# ---------------------------------------------------------------------------

def _rx(a):
    c, s = cos(a), sin(a)
    return (1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c)


def _ry(a):
    c, s = cos(a), sin(a)
    return (c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c)


def _rz(a):
    c, s = cos(a), sin(a)
    return (c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0)


def _sc(x, y=None, z=None):
    return (x, 0.0, 0.0, 0.0, x if y is None else y, 0.0, 0.0, 0.0, x if z is None else z)


def _mm(a, b, *more):
    m = tuple(a[3 * i] * b[j] + a[3 * i + 1] * b[3 + j] + a[3 * i + 2] * b[6 + j] for i in range(3) for j in range(3))
    return _mm(m, *more) if more else m


def _mv(m, v):
    return (m[0] * v[0] + m[1] * v[1] + m[2] * v[2], m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
            m[6] * v[0] + m[7] * v[1] + m[8] * v[2])


def _pose(m, pivot=O3, to=None, glow=1.0):
    """A rigid pose: turn by m about pivot, which lands at to."""
    to = pivot if to is None else to
    q = _mv(m, pivot)
    return m, (to[0] - q[0], to[1] - q[1], to[2] - q[2]), glow


def _view(yaw, pitch):
    return dp._send_matrix((yaw, pitch), 0.0)


# ---------------------------------------------------------------------------
# Surfaces. A grain's geometry is (x, y, z, nx, ny, nz, weight, u): its place, its outward normal (zero for loose
# dust, which is not lit) and its brightness weight, and u, its place along a stroke or a free number from 0 to 1.
# ---------------------------------------------------------------------------

def _unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def _even(n, rng):
    """n points evenly spread over the unit square (an R2 sequence from a random start)."""
    s, t, j = rng.random(), rng.random(), 0.45 / math.sqrt(max(1, n))  # A small jitter breaks up the lattice.
    return [((s + 0.7548776662 * k + rng.uniform(-j, j)) % 1.0, (t + 0.5698402910 * k + rng.uniform(-j, j)) % 1.0)
            for k in range(n)]


def _split(n, weights):
    total = sum(weights) or 1.0
    share = [n * w / total for w in weights]
    counts = [int(s) for s in share]
    for i in sorted(range(len(share)), key=lambda i: counts[i] - share[i])[:n - sum(counts)]:
        counts[i] += 1
    return counts


def _mesh(n, faces, edges, rng, edge=0.4):
    """n grains over a solid: the edge share on its edges by length, the rest on its faces by area. A face or an edge
    is (measure, sampler), and sampler(count, rng) gives that many grains."""
    ne = round(n * edge) if faces and edges else (n if edges else 0)
    out = []
    for group, count in ((faces, n - ne), (edges, ne)):
        if group:
            for (_, fn), c in zip(group, _split(count, [m for m, _ in group])):
                out += fn(c, rng)
    return out


def _quad(o, eu, ev, nrm, w=0.9):
    area = math.hypot(*(eu[1] * ev[2] - eu[2] * ev[1], eu[2] * ev[0] - eu[0] * ev[2], eu[0] * ev[1] - eu[1] * ev[0]))

    def fn(c, rng):
        return [(o[0] + s * eu[0] + t * ev[0], o[1] + s * eu[1] + t * ev[1], o[2] + s * eu[2] + t * ev[2], *nrm, w,
                 rng.random()) for s, t in _even(c, rng)]
    return area, fn


def _tri(a, b, c, nrm, w=0.9):
    e1, e2 = [q - p for p, q in zip(a, b)], [q - p for p, q in zip(a, c)]
    area = 0.5 * math.hypot(e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])

    def fn(count, rng):
        out = []
        for s, t in _even(count, rng):
            if s + t > 1.0:
                s, t = 1.0 - s, 1.0 - t
            out.append((*(p + s * u + t * v for p, u, v in zip(a, e1, e2)), *nrm, w, rng.random()))
        return out
    return area, fn


def _seg(a, b, nrm, w=1.15, jitter=0.25):
    def fn(c, rng):
        out = []
        for k in range(c):
            f = (k + 0.5 + rng.uniform(-0.2, 0.2)) / c
            out.append((*(p + (q - p) * f + rng.gauss(0, jitter) for p, q in zip(a, b)), *nrm, w, (k + 0.5) / c))
        return out
    return math.dist(a, b), fn


def _poly(n, verts, tris, rng, edge=0.4, wf=0.9, we=1.15):
    """A convex solid from its corners and triangles: faces lit by their own normals, edges by the mean of theirs."""
    mid = tuple(sum(v[i] for v in verts) / len(verts) for i in range(3))
    faces, normals = [], {}
    for t in tris:
        a, b, c = (verts[i] for i in t)
        nrm = _unit(((b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
                     (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
                     (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])))
        if sum(nrm[i] * ((a[i] + b[i] + c[i]) / 3 - mid[i]) for i in range(3)) < 0:
            nrm = tuple(-x for x in nrm)
        faces.append(_tri(a, b, c, nrm, wf))
        for e in ((t[0], t[1]), (t[1], t[2]), (t[0], t[2])):
            normals.setdefault(tuple(sorted(e)), []).append(nrm)
    edges = [_seg(verts[i], verts[j], _unit(tuple(sum(x) for x in zip(*ns))), we) for (i, j), ns in normals.items()]
    return _mesh(n, faces, edges, rng, edge)


def _box_pieces(c, h, skip=(), wf=0.9, we=1.15, seen=None):
    """A box's faces and edges; with seen, a view matrix, only those that face that view."""
    def faces_view(nrm, least):
        return seen is None or seen[6] * nrm[0] + seen[7] * nrm[1] + seen[8] * nrm[2] >= least
    faces, edges = [], []
    for i in range(3):
        j, k = (i + 1) % 3, (i + 2) % 3
        for s in (-1, 1):
            if (i, s) not in skip:
                o, eu, ev, nrm = list(c), [0.0] * 3, [0.0] * 3, [0.0] * 3
                o[i] += s * h[i]
                o[j] -= h[j]
                o[k] -= h[k]
                eu[j], ev[k], nrm[i] = 2 * h[j], 2 * h[k], float(s)
                if faces_view(nrm, -0.05):
                    faces.append(_quad(tuple(o), tuple(eu), tuple(ev), tuple(nrm), wf))
        for sj in (-1, 1):
            for sk in (-1, 1):
                a, nrm = list(c), [0.0] * 3
                a[i] -= h[i]
                a[j] += sj * h[j]
                a[k] += sk * h[k]
                b = list(a)
                b[i] += 2 * h[i]
                nrm[j], nrm[k] = float(sj), float(sk)
                if faces_view(_unit(nrm), -0.3):
                    edges.append(_seg(tuple(a), tuple(b), _unit(nrm), we))
    return faces, edges


def _box(n, c, h, rng, edge=0.42, skip=()):
    return _mesh(n, *_box_pieces(c, h, skip), rng, edge)


def _sweep(n, path, half_w, half_d, rng, edge=0.4, caps=(True, True), wf=0.9, we=1.15, steps=48):
    """A bar with a diamond cross-section along a path in the xy plane: path(s) for s from 0 to 1, its half width in
    the plane and its half depth in z. Four faces, four ridges, and a diamond cap at each end."""
    ss = [k / steps for k in range(steps + 1)]
    pts = [path(s) for s in ss]

    def frame(s):
        a, b = path(max(0.0, s - 1e-3)), path(min(1.0, s + 1e-3))
        tx, ty = _unit((b[0] - a[0], b[1] - a[1], 0.0))[:2]
        return path(s), (-ty, tx), (tx, ty)

    lens = [math.dist(p, q) for p, q in zip(pts, pts[1:])]

    def pick(weights, v):
        total, run = sum(weights), 0.0
        for k, wk in enumerate(weights):
            if run + wk >= v * total:
                return (k + (v * total - run) / (wk or 1.0)) / steps
            run += wk
        return 1.0

    face_w = [ln * math.hypot(half_w((k + 0.5) / steps), half_d((k + 0.5) / steps)) for k, ln in enumerate(lens)]
    faces, edges = [], []
    for sa in (-1, 1):
        for sb in (-1, 1):
            def face(c, rng, sa=sa, sb=sb):
                out = []
                for v, f in _even(c, rng):
                    s = pick(face_w, v)
                    (px, py), (nx, ny), _ = frame(s)
                    w, d = half_w(s), half_d(s)
                    out.append((px + (1 - f) * w * sa * nx, py + (1 - f) * w * sa * ny, f * d * sb,
                                *_unit((sa * d * nx, sa * d * ny, sb * w)), wf, s))
                return out
            faces.append((sum(face_w), face))
    for axis, sign in ((0, -1), (0, 1), (1, -1), (1, 1)):
        def ridge(c, rng, axis=axis, sign=sign):
            out = []
            for k in range(c):
                s = pick(lens, (k + 0.5 + rng.uniform(-0.2, 0.2)) / c)
                (px, py), (nx, ny), _ = frame(s)
                if axis == 0:
                    w = half_w(s) * sign
                    out.append((px + w * nx, py + w * ny, 0.0, sign * nx, sign * ny, 0.0, we, s))
                else:
                    out.append((px, py, sign * half_d(s), 0.0, 0.0, float(sign), we, s))
            return out
        edges.append((sum(lens), ridge))
    for s, on in zip((0.0, 1.0), caps):
        w, d = half_w(s), half_d(s)
        if on and w > 0.5:
            def cap(c, rng, s=s, w=w, d=d):
                (px, py), (nx, ny), (tx, ty) = frame(s)
                sign = 1.0 if s else -1.0
                out = []
                for a, b in _even(c, rng):
                    u, v = a - b, a + b - 1.0
                    out.append((px + u * w * nx, py + u * w * ny, v * d, sign * tx, sign * ty, 0.0, wf, s))
                return out
            faces.append((2.0 * w * d, cap))
    return _mesh(n, faces, edges, rng, edge)


def _lathe(n, prof, rng, rings=(), ring_share=0.0, w=0.95, we=1.15, arc=(0.0, TAU)):
    """A surface of revolution about the y axis from a profile of (radius, y), listed top to bottom so the normals
    point out. Rings are (radius, y, (normal out, normal down)) edges, drawn brighter. arc limits the turn round the
    axis, for a solid whose back is never seen."""
    segs = []
    for (r0, y0), (r1, y1) in zip(prof, prof[1:]):
        ln = math.hypot(r1 - r0, y1 - y0)
        segs.append((r0, y0, r1, y1, math.pi * (r0 + r1) * ln, (y1 - y0) / ln, -(r1 - r0) / ln))
    total = sum(s[4] for s in segs)
    nr = round(n * ring_share) if rings else 0
    out = []
    for v, t in _even(n - nr, rng):
        d = v * total
        for r0, y0, r1, y1, area, nrr, nry in segs:
            if d <= area or (r0, y0) == segs[-1][:2]:
                f = min(1.0, d / area)
                r, y, a = r0 + (r1 - r0) * f, y0 + (y1 - y0) * f, arc[0] + (arc[1] - arc[0]) * t
                out.append((r * cos(a), y, r * sin(a), nrr * cos(a), nry, nrr * sin(a), w, t))
                break
            d -= area
    for (r, y, (nrr, nry)), c in zip(rings, _split(nr, [r for r, _, _ in rings]) if rings else []):
        k0 = rng.random()
        for k in range(c):
            a = arc[0] + (arc[1] - arc[0]) * (k + k0) / c
            out.append((r * cos(a), y + rng.gauss(0, 0.25), r * sin(a), nrr * cos(a), nry, nrr * sin(a), we, k / c))
    return out


def _sphere(n, c, r, rng, w=0.95, front=-1.0):
    """A sphere's surface; with front, only the part whose normal's z is at least that, for a back never seen."""
    a0, out, total = rng.random() * TAU, [], int(n * 2.0 / (1.0 - front)) + 8 if front > -1.0 else n
    while len(out) < n:
        out = []
        for k in range(total):
            y = 1.0 - 2.0 * (k + 0.5) / total
            rr, a = math.sqrt(1.0 - y * y), a0 + 2.39996 * k
            nrm = (rr * cos(a), y, rr * sin(a))
            if nrm[2] >= front:
                out.append((c[0] + r * nrm[0], c[1] + r * nrm[1], c[2] + r * nrm[2], *nrm, w, rng.random()))
        total += n - len(out) + 4
    return [out[k * len(out) // n] for k in range(n)]  # An even subset of exactly n.


def _annulus(z, r0, r1, nz, w=0.9):
    """A flat ring (a disc when r0 is 0) round the z axis at depth z, facing nz."""
    def fn(c, rng):
        out = []
        for s, t in _even(c, rng):
            r, a = math.sqrt(r0 * r0 + s * (r1 * r1 - r0 * r0)), TAU * t
            out.append((r * cos(a), r * sin(a), z, 0.0, 0.0, nz, w, t))
        return out
    return math.pi * (r1 * r1 - r0 * r0), fn


def _circle(z, r, nz, w=1.15):
    """A circle round the z axis at depth z, its normal out and tilted by nz toward +z."""
    def fn(c, rng):
        k0 = rng.random()
        return [(r * cos(a), r * sin(a), z, *_unit((cos(a), sin(a), nz)), w, (k + k0) / c)
                for k in range(c) for a in (TAU * (k + k0) / c,)]
    return TAU * r, fn


def _band(r, z0, z1, w=0.9):
    def fn(c, rng):
        return [(r * cos(TAU * t), r * sin(TAU * t), z0 + (z1 - z0) * s, cos(TAU * t), sin(TAU * t), 0.0, w, t)
                for s, t in _even(c, rng)]
    return TAU * r * (z1 - z0), fn


def _xf(gs, m, t=O3):
    """Grains turned by m and moved by t, normals too."""
    out = []
    for g in gs:
        p, q = _mv(m, g[:3]), _mv(m, g[3:6])
        out.append((p[0] + t[0], p[1] + t[1], p[2] + t[2], *q, g[6], g[7]))
    return out


def _loose(n, rng, w=1.0, spread=0.45):
    """Loose dust: unlit grains whose place the sketch works out; small offsets keep a stroke from looking ruled."""
    return [(rng.gauss(0, spread), rng.gauss(0, spread), rng.gauss(0, spread), 0.0, 0.0, 0.0, w,
             (k + 0.5 + rng.uniform(-0.3, 0.3)) / n) for k in range(n)]


# ---------------------------------------------------------------------------
# The machinery every sketch shares: the build, which ties each grain to its place on the loop, and the evaluation.
# ---------------------------------------------------------------------------

class _Sketch:
    """label; arrive, each part's flight start in seconds after MORPH; parts(rng), the grain geometry per part;
    frame(T), which gives (view matrix, a pose per part, occluder or None) at T seconds into the form. A pose is
    (matrix, offset, glow) for a rigid part, or a function of the grain record giving (x, y, z, nx, ny, nz, glow).
    The occluder dims the grains of the parts in hides that pass behind the solid, from their view position."""

    def __init__(self, label, arrive, parts, frame, hides=()):
        self.label, self.arrive, self.parts, self.frame, self.hides = label, arrive, parts, frame, frozenset(hides)


def _lock(arrive):
    """When every part has landed and locked."""
    return MORPH + max(arrive) + FLY + ALIGN


def _al(T, a):
    """A part's lock, 0 to 1 with a small overshoot, after it lands."""
    return _ease_back((T - MORPH - a - FLY) / ALIGN)


def _place(pose, rec):
    if pose.__class__ is tuple:
        m, t, glow = pose
        g = rec[3]
        x, y, z = g[0], g[1], g[2]
        nx, ny, nz = g[3], g[4], g[5]
        return (m[0] * x + m[1] * y + m[2] * z + t[0], m[3] * x + m[4] * y + m[5] * z + t[1],
                m[6] * x + m[7] * y + m[8] * z + t[2], m[0] * nx + m[1] * ny + m[2] * nz,
                m[3] * nx + m[4] * ny + m[5] * nz, m[6] * nx + m[7] * ny + m[8] * nz, glow)
    return pose(rec)


SKETCHES, _FIT = {}, {}  # Per form: its sketch, and its fit (scale, centre x, centre y).


def _build(name, grains, rng):
    """Grain records (along, part, lag, geometry), as the send forms keep them (devs_pack._send_points): grain i keeps
    its own place on the resting loop, and part by part, in the order they leave, each landing place takes the free
    grain nearest it on the loop."""
    sk = SKETCHES[name]
    parts = sk.parts(rng)
    assert sum(map(len, parts)) == grains, (name, sum(map(len, parts)))
    if name not in _FIT:
        # The box every lit grain covers over the whole hold, fitted to the Devs form box and centred FOOT below the
        # presence's centre, so a form in motion keeps its size and place.
        xs, ys, lock = [], [], _lock(sk.arrive)
        for k in range(28):
            V, poses, _ = sk.frame(lock + 0.25 * k)
            for p, part in enumerate(parts):
                for g in part[::3]:
                    x, y, z, *_, glow = _place(poses[p], (0.0, p, 0.5, g))
                    if glow > 0.05:
                        xv, yv, zv = _mv(V, (x, y, z))
                        q = 1.0 / (1.0 - zv / PERSP)
                        xs.append(xv * q)
                        ys.append(yv * q)
        k = min(BOX_W / (max(xs) - min(xs)), BOX_H / (max(ys) - min(ys)))
        _FIT[name] = (k, (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0 - FOOT / k)
    fit, cx, cy = _FIT[name]
    along = []
    for n in range(grains):
        a = -math.pi + TAU * (n + 0.5) / grains
        along.append(math.pi / 2 - a if abs(a) <= math.pi / 2 else math.pi / 2 + a)
    pts, free = [None] * grains, set(range(grains))
    for p in sorted(range(len(parts)), key=lambda q: sk.arrive[q]):
        T = MORPH + sk.arrive[p]
        V, poses, _ = sk.frame(T + FLY)
        flow = T * dp.SEND_LOOP_FLOW
        loop = [(i, 60.0 * sin(along[i] + flow), 26.0 * sin(2.0 * (along[i] + flow))) for i in sorted(free)]
        pairs = []
        for k, g in enumerate(parts[p]):
            x, y, z, *_ = _place(poses[p], (0.0, p, 0.5, g))
            xv, yv, zv = _mv(V, (x, y, z))
            q = 1.0 / (1.0 - zv / PERSP)
            gx, gy = (xv * q - cx) * fit, (yv * q - cy) * fit
            pairs += [((gx - lx) ** 2 + (gy - ly) ** 2, k, i) for i, lx, ly in loop]
        pairs.sort()
        left = list(parts[p])
        for _, k, i in pairs:
            if pts[i] is None and left[k] is not None:
                pts[i], left[k] = (along[i], p, rng.random(), parts[p][k]), None
                free.discard(i)
    return pts


def _evaluate(name, points, now, form_at, persp=PERSP):
    """(tx, ty, tb, tz), as eval_send_tech: on the flowing loop until a grain's part leaves, then in flight with a
    small swirl, then on the lit solid."""
    sk = SKETCHES[name]
    T = now - form_at
    V, poses, occ = sk.frame(T)
    v0, v1, v2, v3, v4, v5, v6, v7, v8 = V
    fit, cx, cy = _FIT[name]
    arrive, hides = sk.arrive, sk.hides
    late = T - MORPH
    formed = late > max(arrive) + FLY + 0.2
    flow = T * dp.SEND_LOOP_FLOW
    lx_, ly_, lz_ = LIGHT
    inv = 1.0 / persp
    tx, ty, tb, tz = [], [], [], []
    for rec in points:
        p = rec[1]
        if formed:
            k = 1.0
        else:
            d = rec[2]
            k = (late - arrive[p] - d * 0.2) / FLY
            k = 0.0 if k <= 0.0 else 1.0 if k >= 1.0 else 1.0 - (1.0 - k) ** 3
        if k > 0.0:
            x, y, z, nx, ny, nz, glow = _place(poses[p], rec)
            xv, yv, zv = v0 * x + v1 * y + v2 * z, v3 * x + v4 * y + v5 * z, v6 * x + v7 * y + v8 * z
            q = 1.0 / (1.0 - zv * inv)
            gx, gy = (xv * q - cx) * fit, (yv * q - cy) * fit
            zn = zv / 46.0  # _depth_shade(zv, 46.0), inline.
            zn = -1.0 if zn < -1.0 else 1.0 if zn > 1.0 else zn
            b = glow * rec[3][6] * (0.62 + 0.5 * (0.30 + 1.08 * (0.5 + 0.5 * zn) ** 1.25))
            if nx or ny or nz:
                nxv, nyv, nzv = v0 * nx + v1 * ny + v2 * nz, v3 * nx + v4 * ny + v5 * nz, v6 * nx + v7 * ny + v8 * nz
                vis = (nzv + 0.18) / 0.36
                vis = 0.0 if vis <= 0.0 else 1.0 if vis >= 1.0 else vis * vis * (3.0 - 2.0 * vis)
                lit = nxv * lx_ + nyv * ly_ + nzv * lz_
                b *= (0.34 + 0.96 * (lit if lit > 0.0 else 0.0)) * (0.05 + 0.95 * vis)
            if occ is not None and p in hides:
                b *= occ(xv, yv, zv)
        if k < 1.0:
            a = rec[0] + flow
            sa, ca = sin(a), cos(a)
            lx, ly, lb = 60.0 * sa, 52.0 * sa * ca, 0.55 + 0.225 * (ca + 1.0)
            if k <= 0.0:
                gx, gy, b, zn = lx, ly, lb, 0.0
            else:
                swirl = sin(math.pi * k) * 7.0 * (rec[2] - 0.5)
                gx, gy, b, zn = lx + (gx - lx) * k, ly + (gy - ly) * k + swirl, lb + (b - lb) * k, zn * k
        tx.append(gx)
        ty.append(gy)
        tb.append(b)
        tz.append(zn)
    return tx, ty, tb, tz


def _even_line(V, t):
    """How much a stretch of a line with 3D tangent t shrinks on screen, 1 when it lies flat to the view. A ring's
    grains bunch where it turns edge on; dimming them by this keeps the ring an even line, with no bright tip."""
    sx, sy = V[0] * t[0] + V[1] * t[1] + V[2] * t[2], V[3] * t[0] + V[4] * t[1] + V[5] * t[2]
    return 0.3 + 0.7 * math.hypot(sx, sy) / (math.hypot(*t) or 1.0)


def _cycle(T, start, period):
    """Seconds into the current cycle, or -1 before the first."""
    return (T - start) % period if T >= start else -1.0


# ---------------------------------------------------------------------------
# figure (find_npc): a solid bust, and rings that loop round it. The owner liked the rings of the last round, not
# its dot. Explored: the loop as a ring (A), two lassos (B), a climbing coil (C), ripples at the feet, and a halo at
# the shoulders. The ripples dropped: they read as a sonar ping, not as rings round the person. The halo read as a
# saint.
# ---------------------------------------------------------------------------

FIG_PROFILE = tuple((36.0 * math.sqrt(max(0.0, 1.0 - ((y - 25.0) / 46.0) ** 2)), y)
                    for y in (-19.5, -17.0, -13.0, -8.0, -2.0, 5.0, 13.0, 25.0))  # A dome, as the flat figure's.
FIG_HEAD, FIG_HEAD_R = (0.0, -37.0, 0.0), 13.0


def _fig_parts(rng, n_body, n_head):
    """The bust and head. The view never turns far, so only their front two thirds carry grains."""
    front = (math.pi / 2 - 1.85, math.pi / 2 + 1.85)
    body = _lathe(n_body, FIG_PROFILE, rng, rings=((36.0, 25.0, (0.86, 0.5)),), ring_share=0.16, arc=front)
    return body, _sphere(n_head, FIG_HEAD, FIG_HEAD_R, rng, front=-0.35)


def _fig_width(y):
    """The bust's half width at height y."""
    c = FIG_HEAD[1]
    hw = math.sqrt(FIG_HEAD_R ** 2 - (y - c) ** 2) if abs(y - c) < FIG_HEAD_R else 0.0
    for (r0, y0), (r1, y1) in zip(FIG_PROFILE, FIG_PROFILE[1:]):
        if y0 <= y <= y1:
            hw = max(hw, r0 + (r1 - r0) * (y - y0) / (y1 - y0))
    return hw


def _fig_hide(V):
    """What the bust hides: a grain behind its axis and within its width at that height goes dark."""
    v1, v4, v7 = V[1], V[4], V[7]

    def occ(xv, yv, zv):
        s = yv / v4
        if zv - s * v7 >= 0.0:
            return 1.0
        hw = _fig_width(s)
        return 1.0 - 0.9 * _smooth((hw + 1.5 - abs(xv - s * v1)) / 3.0) if hw > 0.0 else 1.0
    return occ


def _figure_a():
    """The loop itself becomes the ring: it is already a ring seen edge on. Half its grains fly in to build the bust,
    and as the view tips down, the rest tighten into a ring that hugs the bust and wobbles round it like a hoop."""
    arrive = (0.0, 0.3, 0.55)  # The ring, the body, the head.
    lock = _lock(arrive)

    def parts(rng):
        body, head = _fig_parts(rng, 215, 105)
        return [_loose(320, rng, 0.85), body, head]

    def frame(T):
        blend = _smooth((T - MORPH - 0.2) / 1.7)
        V = _view(0.0, -0.34 * blend)
        flow = T * dp.SEND_LOOP_FLOW
        tip = 11.0 * blend * _smooth((T - lock + 0.4) / 1.2)
        phi = 1.3 * T
        R = 60.0 - 6.0 * blend

        def ring(rec):
            g = rec[3]
            a = TAU * g[7] + flow
            sa, ca = sin(a), cos(a)
            y = 26.0 * sin(2.0 * a) * (1.0 - blend) + blend * 4.0 + tip * sin(a - phi)
            dy = 52.0 * cos(2.0 * a) * (1.0 - blend) + tip * cos(a - phi)
            even = _even_line(V, (R * ca, dy, -R * sa * blend)) if blend > 0.0 else 1.0
            return R * sa + g[0], y + g[1], R * ca * blend + g[2], 0.0, 0.0, 0.0, even

        body = (I3, (0.0, 8.0 * (1.0 - _al(T, arrive[1])), 0.0), 1.0)
        head = (I3, (0.0, -10.0 * (1.0 - _al(T, arrive[2])), 0.0), 1.0)
        return V, (ring, body, head), _fig_hide(V)
    return _Sketch("Loop ring", arrive, parts, frame, hides=(0,))


def _figure_b():
    """Two lassos: open rings drawn round the bust, a near-level one and a steep one, each running its own way while
    its tilt turns, so they loop round the person without a gap that stands still."""
    arrive = (0.0, 0.25, 0.5, 0.62)  # The body, the head, the level ring, the steep ring.

    def parts(rng):
        body, head = _fig_parts(rng, 205, 100)
        return [body, head, _loose(165, rng, 0.95), _loose(170, rng, 0.95)]

    def frame(T):
        V = _view(0.0, -0.26)

        def lasso(M, R, spin, al, cy):
            r = R * (0.7 + 0.3 * al)

            def f(rec):
                g = rec[3]
                u = g[7]
                a = spin * T + TAU * 0.78 * u
                x, y, z = _mv(M, (r * cos(a), g[1], r * sin(a)))
                taper = _smooth(u / 0.18) * _smooth((1.0 - u) / 0.18)
                even = _even_line(V, _mv(M, (-sin(a), 0.0, cos(a))))
                return x + g[0], y + cy, z + g[2], 0.0, 0.0, 0.0, (0.25 + 0.8 * taper) * even
            return f

        level = _mm(_ry(0.5 * T), _rx(0.28))
        steep = _mm(_ry(-0.38 * T + 1.2), _rz(1.0))
        body = (I3, (0.0, 8.0 * (1.0 - _al(T, arrive[0])), 0.0), 1.0)
        head = (I3, (0.0, -10.0 * (1.0 - _al(T, arrive[1])), 0.0), 1.0)
        return V, (body, head, lasso(level, 50.0, 1.7, _al(T, arrive[2]), 3.0),
                   lasso(steep, 54.0, -1.4, _al(T, arrive[3]), -8.0)), _fig_hide(V)
    return _Sketch("Lassos", arrive, parts, frame, hides=(2, 3))


def _figure_c():
    """A coil of dust winds up round the bust from its feet to its head, turning so its loops climb, as a search that
    spirals in on the person."""
    arrive = (0.0, 0.25, 0.5)  # The body, the head, the coil.

    def parts(rng):
        body, head = _fig_parts(rng, 225, 105)
        return [body, head, _loose(310, rng, 1.0)]

    def frame(T):
        V = _view(0.0, -0.22)
        al = _al(T, arrive[2])

        def coil(rec):
            g = rec[3]
            u = g[7]
            a = TAU * 1.8 * u - 2.1 * T
            r = (47.0 - 15.0 * u) * (0.75 + 0.25 * al)
            taper = _smooth(u / 0.12) * _smooth((1.0 - u) / 0.14)
            even = _even_line(V, (-r * sin(a) * 11.3, -74.0, r * cos(a) * 11.3))
            return (r * cos(a) + g[0], 28.0 - 74.0 * u + g[1], r * sin(a) + g[2], 0.0, 0.0, 0.0,
                    (0.3 + 0.8 * taper) * even)

        body = (I3, (0.0, 8.0 * (1.0 - _al(T, arrive[0])), 0.0), 1.0)
        head = (I3, (0.0, -10.0 * (1.0 - _al(T, arrive[1])), 0.0), 1.0)
        return V, (body, head, coil), _fig_hide(V)
    return _Sketch("Coil", arrive, parts, frame, hides=(2,))


# ---------------------------------------------------------------------------
# exclaim (find_quest): a solid faceted "!", a tapered diamond bar over a diamond dot. Explored: the in-game marker's
# turn (A), a pop-up from flat (B), a hop (C), a drip from bar to dot, and a bell's rock. The drip dropped: a small
# falling drop is a moving dot. The rock dropped: its swinging dot was the same fault.
# ---------------------------------------------------------------------------

BANG_TOP, BANG_FOOT, BANG_DOT, BANG_BASE = -50.0, 8.0, 27.0, 37.0


def _bang(rng, n_bar, n_dot):
    bar = _sweep(n_bar, lambda s: (0.0, BANG_TOP + s * (BANG_FOOT - BANG_TOP)), lambda s: 12.5 - 6.0 * s,
                 lambda s: 0.62 * (12.5 - 6.0 * s), rng, edge=0.38)
    c = BANG_DOT
    verts = [(0.0, c - 9.5, 0.0), (0.0, c + 9.5, 0.0), (8.5, c, 0.0), (0.0, c, 5.5), (-8.5, c, 0.0), (0.0, c, -5.5)]
    tris = [(t, a, b) for t in (0, 1) for a, b in ((2, 3), (3, 4), (4, 5), (5, 2))]
    return bar, _poly(n_dot, verts, tris, rng, edge=0.42)


def _exclaim_a():
    """The quest marker: the "!" turns about its own axis and bobs, as the game's marker does over a quest giver.
    Its facets catch the light in turn."""
    arrive = (0.0, 0.35)  # The bar, then the dot drops in.
    lock = _lock(arrive)

    def parts(rng):
        return list(_bang(rng, 440, 200))

    def frame(T):
        hold = max(0.0, T - lock)
        turn = 0.5 + 1.35 * (hold - 0.8 * (1.0 - exp(-hold / 0.8)))
        bob = 2.8 * sin(2.4 * hold) * _smooth(hold / 1.0)
        R = _ry(turn)
        return _view(0.0, -0.16), (_pose(R, to=(0.0, bob + 12.0 * (1.0 - _al(T, arrive[0])), 0.0)),
                                   _pose(R, to=(0.0, bob - 30.0 * (1.0 - _al(T, arrive[1])), 0.0))), None
    return _Sketch("Marker", arrive, parts, frame)


def _bang_ground(rng, n, rx=24.0, rz=11.0):
    """A flat patch of dust on the ground under the mark."""
    return [(rx * math.sqrt(s) * cos(TAU * t), BANG_BASE + 1.0, rz * math.sqrt(s) * sin(TAU * t), 0.0, 0.0, 0.0,
             0.5, t) for s, t in _even(n, rng)]


def _exclaim_b():
    """A pop-up: the "!" lies flat on the ground and springs upright about its foot, like a page in a pop-up book.
    It overshoots, quivers, stands, then folds down to pop again."""
    arrive = (0.0, 0.25)  # The bar, the dot.
    lock = _lock(arrive)

    def parts(rng):
        return list(_bang(rng, 440, 200))

    def tilt(T):
        c = _cycle(T, lock, 3.1)
        if c < 0.0:
            return math.pi / 2
        if c < 0.42:
            return math.pi / 2 * (1.0 - _ease_back(c / 0.42, 2.2))
        if c < 2.25:
            return -0.07 * exp(-(c - 0.42) / 0.3) * sin(13.0 * (c - 0.42))
        if c < 2.6:
            return math.pi / 2 * ((c - 2.25) / 0.35) ** 2
        return math.pi / 2

    def frame(T):
        M = _mm(_ry(0.32), _rx(tilt(T)))
        base = (0.0, BANG_BASE, 0.0)
        return _view(0.0, -0.42), (_pose(M, base, (0.0, BANG_BASE + 10.0 * (1.0 - _al(T, arrive[0])), 0.0)),
                                   _pose(M, base, (0.0, BANG_BASE - 10.0 * (1.0 - _al(T, arrive[1])), 0.0))), None
    return _Sketch("Pop-up", arrive, parts, frame)


def _exclaim_c():
    """A hop: the "!" crouches, springs up with a quarter turn, lands and squashes. The bar lags the dot a beat, so
    the mark stretches in the air and settles on landing, and the dust at its foot puffs out and back."""
    arrive = (0.0, 0.15, 0.4)
    lock = _lock(arrive)
    P, AIR = 2.4, 0.46

    def parts(rng):
        bar, dot = _bang(rng, 370, 180)
        return [_bang_ground(rng, 90), bar, dot]

    def jump(c):
        """(height, squash, turn) c seconds into a hop."""
        if c < 0.0:
            return 0.0, 1.0, 0.0
        if c < 0.16:
            return 0.0, 1.0 - 0.2 * _smooth(c / 0.16), 0.0
        if c < 0.16 + AIR:
            f = (c - 0.16) / AIR
            return 88.0 * f * (1.0 - f), 1.0 + 0.12 * (1.0 - 2.0 * f) ** 2, _smooth(f)
        a = c - 0.16 - AIR
        return 0.0, 1.0 - 0.17 * exp(-a / 0.11) * cos(16.0 * a), 1.0

    def frame(T):
        c = _cycle(T, lock + 0.2, P)
        hops = int((T - lock - 0.2) // P) if c >= 0.0 else 0
        out = []
        for lag in (0.035, 0.0):  # The bar lags the dot.
            h, s, turn = jump(c - lag if c >= lag else (-1.0 if c < 0.0 else 0.0))
            M = _mm(_ry(0.4 + 1.2 * (hops + turn)), _sc(1.0 / math.sqrt(s), s))
            out.append(_pose(M, (0.0, BANG_BASE, 0.0), (0.0, BANG_BASE - h, 0.0)))
        out[0] = (out[0][0], (out[0][1][0], out[0][1][1] + 12.0 * (1.0 - _al(T, arrive[1])), out[0][1][2]), 1.0)
        out[1] = (out[1][0], (out[1][1][0], out[1][1][1] - 12.0 * (1.0 - _al(T, arrive[2])), out[1][1][2]), 1.0)
        land = c - 0.16 - AIR if c >= 0.16 + AIR else -1.0

        def ground(rec):
            g = rec[3]
            puff = exp(-land / 0.22) * _smooth(land / 0.05) if land >= 0.0 else 0.0
            k = 1.0 + 0.45 * puff
            return g[0] * k, g[1] - 7.0 * puff * (1.0 - g[0] ** 2 / 700.0), g[2] * k, 0.0, 0.0, 0.0, 1.0 + 0.6 * puff
        return _view(0.0, -0.3), (ground, *out), None
    return _Sketch("Hop", arrive, parts, frame)


# ---------------------------------------------------------------------------
# chest (find_item): a solid chest with a barrel lid on a hinge at the back. Explored: a lid that opens on a heap of
# dust (A), a sealed lid that lifts a crack and lets dust out (B), an open chest that overflows (C), a chest built
# plank by plank, and a lid that bursts open on a plume. The planks dropped: the build is the morph, not the hold.
# The plume dropped: a tall plume over the chest blurred its silhouette.
# ---------------------------------------------------------------------------

CW, CD, RIM, CFOOT = 30.0, 17.0, -4.0, 24.0  # Half width, half depth, the rim's height and the foot's.
HINGE = (0.0, RIM, -CD)
CHEST_VIEW = (0.52, -0.34)


def _chest_body(rng, n):
    faces, edges = _box_pieces((0.0, (RIM + CFOOT) / 2, 0.0), (CW, (CFOOT - RIM) / 2, CD), skip=((1, -1), (1, 1)),
                               seen=_view(*CHEST_VIEW))
    for x in (-16.0, 16.0):  # The two straps down the front.
        edges.append(_seg((x, RIM, CD + 0.6), (x, CFOOT, CD + 0.6), (0.0, 0.0, 1.0), 1.1))
    faces.append(_quad((-4.5, RIM, CD + 0.8), (9.0, 0.0, 0.0), (0.0, 9.0, 0.0), (0.0, 0.0, 1.0), 1.2))  # The lock.
    return _mesh(n, faces, edges, rng, 0.56)


def _chest_lid(rng, n):
    """The barrel lid, closed: its curve, its two ends, its flat underside, and its rims and straps."""
    def curve(c, rng):
        return [(-CW + 2 * CW * s, RIM - CD * sin(math.pi * t), CD * cos(math.pi * t), 0.0, -sin(math.pi * t),
                 cos(math.pi * t), 0.9, t) for s, t in _even(c, rng)]

    def end(sign):
        def fn(c, rng):
            return [(sign * CW, RIM - CD * math.sqrt(s) * sin(math.pi * t), CD * math.sqrt(s) * cos(math.pi * t),
                     sign, 0.0, 0.0, 0.85, t) for s, t in _even(c, rng)]
        return math.pi * CD * CD / 2, fn

    def arc(x, r, nx, w):
        def fn(c, rng):
            return [(x, RIM - r * sin(math.pi * f), r * cos(math.pi * f), *_unit((nx, -sin(math.pi * f),
                     cos(math.pi * f))), w, f) for k in range(c) for f in ((k + 0.5) / c,)]
        return math.pi * r, fn

    faces = [(math.pi * CD * 2 * CW, curve), end(-1.0), end(1.0),
             _quad((-CW, RIM, -CD), (2 * CW, 0.0, 0.0), (0.0, 0.0, 2 * CD), (0.0, 1.0, 0.0), 0.7)]
    edges = [arc(-CW, CD, -1.0, 1.15), arc(CW, CD, 1.0, 1.15), arc(-16.0, CD + 0.6, 0.0, 1.1),
             arc(16.0, CD + 0.6, 0.0, 1.1), _seg((-CW, RIM, CD), (CW, RIM, CD), (0.0, 0.3, 1.0), 1.15)]
    return _mesh(n, faces, edges, rng, 0.52)


def _lid_pose(angle, drop=0.0):
    return _pose(_rx(angle), HINGE, (HINGE[0], HINGE[1] + drop, HINGE[2]))


def _heap(H, glow, t, spin=0.13):
    """The heap of dust in the chest, H high over the rim. Its grains roll slowly from the crown out to the rim and
    rise again unseen at the crown, so the heap churns. Flow is in area, so the heap's density stays even."""
    def f(rec):
        g = rec[3]
        area = (g[7] + spin * t) % 1.0
        r, a = math.sqrt(area), TAU * rec[2]
        x, z = (CW - 3.0) * r * cos(a), (CD - 3.0) * r * sin(a)
        y = RIM - H * (1.0 - area)
        nrm = _unit((2.0 * H * x / (CW - 3.0) ** 2, -1.0, 2.0 * H * z / (CD - 3.0) ** 2))
        fade = _smooth(area / 0.12) * _smooth((1.0 - area) / 0.1)
        return x + g[0], y + g[1], z + g[2], *nrm, glow * fade * 1.15
    return f


def _chest_a():
    """The open hoard: the lid swings back on its hinge with a small overshoot, and a heap of dust swells up from the
    chest and churns. The lid shuts with a bounce and opens again."""
    arrive = (0.0, 0.2, 0.45)  # The body, the lid, the heap.
    lock = _lock(arrive)

    def parts(rng):
        return [_chest_body(rng, 215), _chest_lid(rng, 215), _loose(210, rng, 1.0, 0.3)]

    def opened(T):
        c = _cycle(T, lock + 0.15, 4.4)
        if c < 0.0:
            return 0.0
        if c < 0.75:
            return _ease_back(c / 0.75, 1.3)
        if c < 2.9:
            return 1.0
        if c < 3.22:
            return 1.0 - ((c - 2.9) / 0.32) ** 2
        return 0.07 * sin(math.pi * min(1.0, (c - 3.22) / 0.3))

    def frame(T):
        o = opened(T)
        lid = _lid_pose(1.95 * o, -14.0 * (1.0 - _al(T, arrive[1])))
        return _view(*CHEST_VIEW), ((I3, O3, 1.0), lid, _heap(13.0 * max(0.0, o) ** 0.8, _smooth(o * 2.5), T)), None
    return _Sketch("Open hoard", arrive, parts, frame)


def _chest_b():
    """The sealed chest: the lid lifts a crack, rattles and drops shut with a bounce. While it is up, dust sifts out of
    the seam along the front and falls away down the chest's face."""
    arrive = (0.0, 0.2, 0.45)  # The body, the lid, the dust inside.
    lock = _lock(arrive)
    P = 2.8

    def lift(c):
        if c < 0.0:
            return 0.0
        if c < 0.35:
            return _ease_out(c / 0.35)
        if c < 0.95:
            return 1.0 + 0.08 * sin(38.0 * (c - 0.35)) * exp(-(c - 0.35) / 0.25)
        if c < 1.15:
            return 1.0 - ((c - 0.95) / 0.2) ** 2
        return 0.18 * sin(math.pi * min(1.0, (c - 1.15) / 0.18))

    def parts(rng):
        return [_chest_body(rng, 250), _chest_lid(rng, 250), _loose(140, rng, 1.0, 0.2)]

    def frame(T):
        c = _cycle(T, lock + 0.2, P)

        def spill(rec):
            g = rec[3]
            x0 = -24.0 + 48.0 * rec[2]
            age = c - 0.12 - 0.75 * g[7]
            if c < 0.0 or age < 0.0 or age > 0.75:
                return x0 * 0.8, RIM + 4.0, 6.0, 0.0, 0.0, 0.0, 0.0  # Unseen, inside.
            y = RIM - 3.0 * age + 0.5 * 150.0 * age * age
            glow = _smooth(age / 0.08) * (1.0 - _smooth((age - 0.4) / 0.35)) * 1.1
            return x0 + g[0] * 3.0, y, CD + 2.0 + 13.0 * age + g[2], 0.0, 0.0, 0.0, glow

        lid = _lid_pose(0.24 * lift(c), -14.0 * (1.0 - _al(T, arrive[1])))
        return _view(*CHEST_VIEW), ((I3, O3, 1.0), lid, spill), None
    return _Sketch("Sealed", arrive, parts, frame)


def _chest_c():
    """The overflow: the lid stands open and the heap spills. Dust rolls over the front rim, pours down the chest's
    face and spreads into a pile at its foot, then fades as more comes."""
    arrive = (0.0, 0.2, 0.45, 0.5)  # The body, the lid, the heap, the stream.
    lock = _lock(arrive)

    def parts(rng):
        return [_chest_body(rng, 200), _chest_lid(rng, 150), _loose(130, rng, 1.0, 0.3), _loose(160, rng, 1.0, 0.5)]

    def frame(T):
        o = _ease_back((T - lock) / 0.8, 1.2) if T > lock else 0.0
        flow = _smooth((T - lock - 0.5) / 0.6)

        def stream(rec):
            g = rec[3]
            c = (g[7] + 0.3 * T) % 1.0
            xs = (rec[2] - 0.5) * 16.0
            if c < 0.35:  # Rolling to the front rim over the heap.
                f = c / 0.35
                x, y, z = xs * (0.5 + 0.5 * f), RIM - 15.0 * (1.0 - f * f), (CD - 3.0) * f
            elif c < 0.72:  # Falling down the face.
                f = (c - 0.35) / 0.37
                x, y, z = xs, RIM + (CFOOT - RIM) * f * f, CD + 1.5 + 5.0 * f
            else:  # Spreading into the pile.
                f = (c - 0.72) / 0.28
                x, y, z = xs * (1.0 + 0.5 * f), CFOOT - 2.0 * (1.0 - f), CD + 6.5 + 10.0 * f
            glow = flow * _smooth(c / 0.08) * (1.0 - _smooth((c - 0.8) / 0.2)) * 1.1
            return x + g[0], y + g[1], z + g[2], 0.0, 0.0, 0.0, glow

        lid = _lid_pose(2.0 * o, -14.0 * (1.0 - _al(T, arrive[1])))
        return _view(*CHEST_VIEW), ((I3, O3, 1.0), lid, _heap(15.0 * min(1.0, o) ** 0.8, _smooth(o * 2.0), T, 0.09),
                                    stream), None
    return _Sketch("Overflow", arrive, parts, frame)


# ---------------------------------------------------------------------------
# sword (find_upgrades): a solid sword with a diamond blade, a guard, a grip and a faceted pommel. Explored: drawn up
# out of a pool of dust (A), two swords that cross and clash (B), a twirl (C), a blade that sharpens from a blur,
# and a sword that climbs in steps. The blur dropped: a soft blade read as a smudge. The steps read as an arrow.
# ---------------------------------------------------------------------------

def _sword(rng, n_blade, n_guard, n_grip, n_pommel):
    blade = _sweep(n_blade, lambda s: (0.0, -62.0 * s), lambda s: 8.6 if s < 0.72 else 8.6 * (1.0 - s) / 0.28,
                   lambda s: 2.6 if s < 0.72 else 2.6 * (1.0 - s) / 0.28 + 0.2, rng, edge=0.5, caps=(False, False))
    guard = _box(n_guard, (0.0, 3.2, 0.0), (24.0, 3.2, 4.2), rng, 0.5)
    grip = _lathe(n_grip, ((3.3, 6.0), (3.7, 15.5), (3.3, 25.0)), rng)
    c = 31.0
    pommel = _poly(n_pommel, [(0.0, c - 5.8, 0.0), (0.0, c + 5.8, 0.0), (5.2, c, 0.0), (0.0, c, 5.2), (-5.2, c, 0.0),
                              (0.0, c, -5.2)],
                   [(t, a, b) for t in (0, 1) for a, b in ((2, 3), (3, 4), (4, 5), (5, 2))], rng, 0.45)
    return [blade, guard, grip, pommel]


POOL_Y = 33.0


def _sword_a():
    """Drawn from dust: a pool of dust lies on the ground, and the sword rises out of it point first. Each grain stays
    in the pool until the blade carries its place up through the surface, so the dust streams up into the steel.
    Then it turns slowly over the pool."""
    arrive = (0.0, 0.2, 0.25, 0.3, 0.35)  # The pool, then the sword's blade, guard, grip and pommel, into the pool.
    rise_at = MORPH + 0.35 + FLY + 0.2

    def parts(rng):
        return [_loose(100, rng, 1.0, 0.3), *_sword(rng, 300, 100, 60, 80)]

    def frame(T):
        r = _ease_back((T - rise_at) / 1.5, 0.7) if T > rise_at else 0.0
        off = 100.0 * (1.0 - r)
        hold = max(0.0, T - rise_at - 1.5)
        R = _ry(0.35 + 0.7 * sin(0.8 * hold) * _smooth(hold / 1.2))
        bob = 1.5 * sin(1.6 * hold)
        swirl = 0.55 * T

        def pool(rec, rad=None):
            g = rec[3]
            a = TAU * g[7] + swirl
            rad = 3.0 + 25.0 * math.sqrt(rec[2]) if rad is None else rad
            return rad * cos(a) + g[0], POOL_Y + g[1], rad * sin(a) + g[2], 0.0, 0.0, 0.0, 0.55

        def steel(rec):
            x, y, z, nx, ny, nz, _ = _place((R, (0.0, off + bob, 0.0), 1.0), rec)
            up = 1.0 - _smooth((y - POOL_Y + 2.0) / 6.0)
            if up >= 1.0:
                return x, y, z, nx, ny, nz, 1.0
            px, py, pz, *_ = pool(rec)
            if up < 0.5:
                return px + (x - px) * up, py + (y - py) * up, pz + (z - pz) * up, 0.0, 0.0, 0.0, 0.55
            return px + (x - px) * up, py + (y - py) * up, pz + (z - pz) * up, nx, ny, nz, up
        return _view(0.0, -0.3), (pool, steel, steel, steel, steel), None
    return _Sketch("Drawn", arrive, parts, frame)


def _sword_b():
    """Crossed swords, for gear held against gear: two blades swing in from either side and cross with a clash. The
    pair turns slowly, and now and then the blades part and clash again."""
    arrive = (0.0, 0.15)
    lock = _lock(arrive)
    X, MID, S = (0.0, -6.0, 0.0), (0.0, -24.0, 0.0), 0.86  # Where they cross, the blade's middle, their scale.

    def parts(rng):
        return [sum(_sword(rng, 175, 60, 35, 50), []), sum(_sword(rng, 175, 60, 35, 50), [])]

    def frame(T):
        hold = max(0.0, T - lock)
        c = _cycle(hold, 1.2, 2.8)
        apart = 0.0
        if 0.0 <= c < 0.4:
            apart = _smooth(c / 0.4)
        elif 0.4 <= c < 0.7:
            apart = 1.0
        elif 0.7 <= c < 1.05:
            apart = 1.0 - _ease_back((c - 0.7) / 0.35, 2.6)
        Y = _ry(0.45 * sin(0.55 * hold))
        poses = []
        for k, side in ((0, 1.0), (1, -1.0)):
            a = side * (0.62 + 0.22 * apart + 0.9 * (1.0 - _al(T, arrive[k])))
            M = _mm(Y, _rz(a), _sc(S))
            to = _mv(Y, (side * 9.0 * apart, X[1], side * 3.2))
            poses.append(_pose(M, MID, to))
        return _view(0.0, -0.18), tuple(poses), None
    return _Sketch("Crossed", arrive, parts, frame)


def _sword_c():
    """The flourish: the sword twirls a full turn about its balance point, sweeping through depth as it goes, and
    lands upright with a small settle. Then it holds and twirls again."""
    arrive = (0.0, 0.1, 0.15, 0.2)
    lock = _lock(arrive)

    def parts(rng):
        return _sword(rng, 300, 120, 90, 130)

    def frame(T):
        c = _cycle(T, lock + 0.5, 3.6)
        if c < 0.0:
            th = 0.0
        elif c < 2.1:
            f = c / 2.1
            th = TAU * f * f * f * (f * (6.0 * f - 15.0) + 10.0)
        else:
            th = TAU + 0.13 * exp(-(c - 2.1) / 0.25) * sin(11.0 * (c - 2.1))
        M = _mm(_ry(0.42 + 0.2 * sin(th)), _rz(th))
        poses = tuple(_pose(M, (0.0, -10.0, 0.0), (0.0, -10.0 + 10.0 * (1.0 - _al(T, a)), 0.0)) for a in arrive)
        return _view(0.0, -0.16), poses, None
    return _Sketch("Flourish", arrive, parts, frame)


# ---------------------------------------------------------------------------
# coins (find_price): a struck coin with a raised rim and Rook's own tower on its face. Explored: the turning coin the
# owner liked (A), a stack that grows as coins drop (B), a flip that lands and wobbles (C), a coin rolling on its
# edge, and a coin spun on a table. The roll left the form box. The table spin read as A again.
# ---------------------------------------------------------------------------

TOWER = [(-9.0, 12.0), (9.0, 12.0), (9.0, 9.0), (6.0, 7.5), (6.0, -3.0), (9.0, -5.5), (9.0, -12.0), (5.0, -12.0),
         (5.0, -8.5), (1.8, -8.5), (1.8, -12.0), (-1.8, -12.0), (-1.8, -8.5), (-5.0, -8.5), (-5.0, -12.0),
         (-9.0, -12.0), (-9.0, -5.5), (-6.0, -3.0), (-6.0, 7.5), (-9.0, 9.0), (-9.0, 12.0)]


def _coin(rng, n, r=25.0, hz=3.4, edge=0.36, tower=0, fill=0.8):
    """A coin about the z axis with its face toward +z only: _two_faced draws that face on whichever side the viewer
    sees, so no grain is spent on a face turned away. With tower, that many of the n grains draw the tower in
    relief."""
    rim = r - 4.5
    faces = [_annulus(hz, 0.0, rim, 1.0, fill), _annulus(hz + 0.7, rim, r, 1.0, 1.0), _band(r, -hz, hz + 0.7, fill)]
    edges = [_circle(hz + 0.7, r, 1.0, 1.2), _circle(hz + 0.7, rim, 1.6, 1.05), _circle(-hz, r, -1.0)]
    out = _mesh(n - tower, faces, edges, rng, edge)
    if tower:
        pts = [(x * r / 25.0, y * r / 25.0, hz + 0.9) for x, y in TOWER]
        out += _mesh(tower, [], [_seg(a, b, (0.0, 0.0, 1.0), 1.25, 0.2) for a, b in zip(pts, pts[1:])], rng)
    return out


def _two_faced(M, t, V, axis, hz, glow=1.0):
    """A coin's pose that keeps its face toward the viewer: when the face (along axis) looks away, each grain on the
    face's side is mirrored through the coin's plane, so the coin shows its other face, lit the same."""
    a = _mv(M, axis)
    if V[6] * a[0] + V[7] * a[1] + V[8] * a[2] >= 0.0:
        return M, t, glow

    def f(rec):
        g = rec[3]
        d = g[0] * axis[0] + g[1] * axis[1] + g[2] * axis[2]
        if d > 0.5 * hz:
            dn = 2.0 * (g[3] * axis[0] + g[4] * axis[1] + g[5] * axis[2])
            d *= 2.0
            g = (g[0] - d * axis[0], g[1] - d * axis[1], g[2] - d * axis[2], g[3] - dn * axis[0],
                 g[4] - dn * axis[1], g[5] - dn * axis[2], g[6], g[7])
        return _place((M, t, glow), (0.0, 0, 0.0, g))
    return f


def _coins_a():
    """The struck coin: the tower stamps into the coin's face as it locks, and the coin turns steadily about its
    upright axis, its faces catching the light and its rim showing edge on."""
    arrive = (0.0, 0.4)  # The coin, then the tower struck into it.
    lock = _lock(arrive)

    def parts(rng):
        coin = _coin(rng, 640, tower=170)
        return [coin[:470], coin[470:]]

    def frame(T):
        hold = max(0.0, T - lock)
        turn = 0.35 + 1.9 * (hold - 0.7 * (1.0 - exp(-hold / 0.7)))
        R = _mm(_rz(0.1), _ry(turn))
        V = _view(0.0, -0.12)
        lift = 16.0 * (1.0 - _al(T, arrive[1]))
        coin = _two_faced(R, O3, V, (0.0, 0.0, 1.0), 3.4)
        stamp = _two_faced(R, _mv(R, (0.0, 0.0, lift)), V, (0.0, 0.0, 1.0), 3.4)
        return V, (coin, stamp), None
    return _Sketch("Struck coin", arrive, parts, frame)


GROUND = 30.0
FLAT = _rx(math.pi / 2)  # A coin lying flat, its face up.


def _coins_b():
    """The stack: coins drop one at a time onto a short stack and settle, and as each lands the stack sinks one coin
    into a plate of dust, its bottom coin melting into the dust. So the count keeps going."""
    H, HZ, R, P, DROP = 10.0, 2.2, 25.0, 1.3, 34.0
    arrive = (0.0, 0.1, 0.17, 0.24, 0.31, 0.38)  # The dust plate, then the coins.
    lock = _lock(arrive)

    def parts(rng):
        plate = [(33.0 * math.sqrt(s) * cos(TAU * t), GROUND + 0.5, 14.0 * math.sqrt(s) * sin(TAU * t),
                  0.0, 0.0, 0.0, 0.42, t) for s, t in _even(140, rng)]
        return [plate] + [_xf(_coin(rng, 100, R, HZ, 0.8, fill=0.5), FLAT) for _ in range(5)]

    def rest(m):
        return GROUND - HZ - H * m

    def frame(T):
        c = _cycle(T, lock, P)
        n = int((T - lock) // P) if c >= 0.0 else 0
        f = c / P if c >= 0.0 else 0.0
        slide = H * _smooth((f - 0.55) / 0.32)
        poses = [(I3, O3, 1.0)]
        for j in range(5):
            m = (j - n) % 5
            if c < 0.0:  # Before the count starts: three stacked, the other two wait unseen above.
                y, M, glow = (rest(j), I3, 1.0) if j < 3 else (rest(3) - DROP, I3, 0.0)
                y += 10.0 * (1.0 - _al(T, arrive[j + 1]))
            elif m == 3:  # Falling: it spins down, tilted, and lands flat with a wobble.
                d = min(1.0, f / 0.36)
                y = rest(3) - DROP * (1.0 - d * d) + slide
                wob = 0.07 * exp(-(f - 0.36) * P / 0.12) * sin(30.0 * (f - 0.36) * P) if f > 0.36 else 0.0
                M, glow = _mm(_ry(2.2 * (1.0 - d)), _rx(wob)), _smooth(f / 0.1)
            elif m == 4:  # Unseen, waiting above to fall next.
                y, M, glow = rest(3) - DROP, I3, 0.0
            else:
                y, M, glow = rest(m) + slide, I3, 1.0
            # A coin with another resting on it shows only its side: the coin above hides its face.
            covered = (m < 2 or (m == 2 and c >= 0.0 and f > 0.36)) if c >= 0.0 else j < 2
            poses.append(_sink(M, y, glow, covered))
        return _view(0.0, -0.5), tuple(poses), None
    return _Sketch("Stack", arrive, parts, frame)


def _covered(g):
    """A flat coin's grain that the coin resting on it hides: its face, and the far half of its rims."""
    return g[4] < -0.9 or (g[4] < -0.3 and g[2] < 0.0)


def _sink(M, y, glow, covered=False):
    """A flat coin at height y whose grains below the dust plate spread into it and fade."""
    def f(rec):
        g = rec[3]
        if covered and _covered(g):
            return g[0], y + g[1], g[2], 0.0, 0.0, 0.0, 0.0
        x, gy, z, nx, ny, nz, _ = _place((M, (0.0, y, 0.0), 1.0), (0.0, 0, 0.0, g))
        under = gy - GROUND
        if under <= -0.5:
            return x, gy, z, nx, ny, nz, glow
        k = 1.0 + 0.12 * max(0.0, under)
        return x * k, GROUND + 0.5, z * k, 0.0, 0.0, 0.0, glow * 0.55 * (1.0 - _smooth(under / 5.0))
    return f


def _coins_c():
    """The flip: a coin leaps off a short stack, turns end over end and lands flat, then wobbles down like a spun
    coin, its tilt circling as it settles."""
    HZ, R, H = 2.2, 25.0, 10.0
    arrive = (0.0, 0.12, 0.3)  # The two stacked coins, then the coin that flips.
    lock = _lock(arrive)
    top = GROUND - HZ - H * 2

    def parts(rng):
        return [_xf(_coin(rng, 170, R, HZ, 0.8, fill=0.5), FLAT) for _ in range(2)] + [
            _xf(_coin(rng, 300, R, HZ, 0.45, tower=60), FLAT)]

    def frame(T):
        c = _cycle(T, lock + 0.3, 2.6)
        y, M = top, I3
        if 0.0 <= c < 0.95:
            f = c / 0.95
            y = top - 36.0 * 4.0 * f * (1.0 - f)
            M = _rx(TAU * _smooth(f))
        elif 0.95 <= c < 2.0:
            a = c - 0.95
            th = 0.36 * exp(-a / 0.3)
            psi = 10.0 * a
            M = _mm(_ry(psi), _rx(th), _ry(-psi))
            y = top - R * sin(th) * 0.9
        V = _view(0.0, -0.45)
        poses = []
        for k in range(2):  # The lower coin is always covered; the upper one while the flipped coin rests on it.
            at = (0.0, GROUND - HZ - H * k + 8.0 * (1.0 - _al(T, arrive[k])), 0.0)
            covered = k == 0 or not 0.0 <= c < 0.95
            poses.append(lambda rec, at=at, covered=covered: (
                (rec[3][0], at[1] + rec[3][1], rec[3][2], 0.0, 0.0, 0.0, 0.0) if covered and _covered(rec[3])
                else _place((I3, at, 1.0), rec)))
        poses.append(_two_faced(M, (0.0, y - 14.0 * (1.0 - _al(T, arrive[2])), 0.0), V, (0.0, -1.0, 0.0), HZ))
        return V, tuple(poses), None
    return _Sketch("Flip", arrive, parts, frame)


# ---------------------------------------------------------------------------
# pickaxe (find_object): a solid pick with a round haft, a collar and two curved horns. Explored: a swing that
# strikes the ground and throws up dust (A), taps that chip a rock (B), quick chops that dig a pile (C), a pick that
# spins on its haft to point the way, a pry that levers up a clod, and a pick thrown end over end. The spin dropped:
# edge on, its head shrank to a bright knot, an orb. The clod was a dense knot too. The throw read as the sword's
# flourish.
# ---------------------------------------------------------------------------

def _bez(a, b, c):
    return lambda s: tuple((1 - s) ** 2 * p + 2 * (1 - s) * s * q + s * s * r for p, q, r in zip(a, b, c))


def _pick(rng, n_haft, n_head):
    haft = _lathe(n_haft, ((2.6, -34.0), (2.8, 8.0), (3.0, 40.0)), rng, rings=((3.0, 40.0, (0.5, 0.86)),),
                  ring_share=0.1)
    right, left, collar = _split(n_head, (0.38, 0.38, 0.24))
    horn = _bez((4.5, -41.0), (21.0, -46.0), (35.0, -31.0))
    head = []
    for side, c in ((1.0, right), (-1.0, left)):  # The left horn is the right one mirrored.
        g = _sweep(c, horn, lambda s: 4.8 * (1 - s) + 0.6 * s, lambda s: 3.4 * (1 - s) + 0.6 * s, rng, 0.45,
                   (False, False))
        head += _xf(g, _sc(side, 1.0, 1.0))
    head += _box(collar, (0.0, -40.5, 0.0), (5.0, 6.5, 4.4), rng, 0.45)
    return haft, head


def _swing_pose(alpha, grip_at, scale=0.8, yaw=0.3):
    """The pick turned alpha about the grip (its haft end) in the swing's plane, the grip held at grip_at."""
    return _pose(_mm(_ry(yaw), _rz(alpha), _sc(scale)), (0.0, 36.0, 0.0), _mv(_ry(yaw), grip_at))


def _pickaxe_a():
    """The strike: the pick rises slowly over the grip, hangs, swings down hard and bites the ground. Dust leaps up
    from the strike in arcs, lands, and drifts back to lie still before the next blow."""
    arrive = (0.0, 0.15, 0.3)  # The dust on the ground, the haft, the head.
    lock = _lock(arrive)
    GRIP, RAISED, STRIKE, P = (30.0, 32.0, 0.0), 0.28, -1.13, 1.9
    HIT = (-26.0, 40.0)  # Where the horn bites.

    def parts(rng):
        dust = []
        for s, t in _even(130, rng):
            r, a = 26.0 * math.sqrt(s), TAU * t
            dust.append((HIT[0] + 1.2 * r * cos(a), 40.0, 0.5 * r * sin(a), 0.0, 0.0, 0.0, 0.6, t))
        return [dust, *_pick(rng, 150, 360)]

    def alpha(c):
        if c < 0.0:
            return RAISED
        if c < 0.25:
            return STRIKE + 0.1 * sin(math.pi * c / 0.25) * exp(-c / 0.15)
        if c < 0.55:
            return STRIKE
        if c < 1.35:
            return STRIKE + (RAISED - STRIKE) * _smooth((c - 0.55) / 0.8)
        if c < 1.5:
            return RAISED
        return RAISED + (STRIKE - RAISED) * ((c - 1.5) / 0.4) ** 2

    def frame(T):
        c = _cycle(T, lock - 1.35, P)
        hit = c if c >= 0.0 and T >= lock + 0.4 - 1e-9 else -1.0  # Seconds since the last blow.
        pick = _swing_pose(alpha(c), GRIP)
        pick = (pick[0], (pick[1][0], pick[1][1] - 12.0 * (1.0 - _al(T, arrive[1])), pick[1][2]), 1.0)

        def dust(rec):
            g = rec[3]
            dx, dz = g[0] - HIT[0], g[2]
            near = 1.0 - min(1.0, math.hypot(dx, 2.0 * dz) / 32.0)
            h = (8.0 + 30.0 * rec[2]) * (0.25 + 0.75 * near)
            tau = 0.3 + 0.25 * math.sqrt(h / 38.0)
            out = 4.0 + 16.0 * rec[2]
            ux, uz = _unit((dx, 0.0, dz))[0::2] if dx or dz else (1.0, 0.0)
            if hit < 0.0:
                return g[0], g[1], g[2], 0.0, 0.0, 0.0, 1.0
            if hit < tau:
                f = hit / tau
                return (g[0] + ux * out * f, 40.0 - 4.0 * h * f * (1.0 - f), g[2] + uz * out * f, 0.0, 0.0, 0.0,
                        1.0 + 0.6 * (1.0 - f))
            back = 1.0 - _smooth((hit - tau) / 0.9)
            return g[0] + ux * out * back, 40.0, g[2] + uz * out * back, 0.0, 0.0, 0.0, 1.0
        return _view(0.0, -0.22), (dust, pick, pick), None
    return _Sketch("Strike", arrive, parts, frame)


ROCK_C, ROCK_R = (-14.0, 20.0, 0.0), 21.0


def _rock(rng, n, c=ROCK_C, r=ROCK_R, floor=40.0):
    """A faceted rock: an icosahedron with its corners pushed in and out, centred at c, cut flat at floor."""
    t = (1.0 + math.sqrt(5.0)) / 2.0
    base = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
            (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    tris = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
            (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
            (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    verts = []
    for x, y, z in base:
        k = r * (0.85 + 0.3 * rng.random()) / math.hypot(x, y, z)
        verts.append((c[0] + k * x * 1.15, min(c[1] + k * y * 0.85, floor), c[2] + k * z))
    return _poly(n, verts, tris, rng, 0.42)


def _pickaxe_b():
    """The ore node: a faceted rock, and a pick that taps it in a steady rhythm. Each blow jolts the rock and knocks
    chips of dust off its struck face; they tumble down, then creep back up and close over the face."""
    arrive = (0.0, 0.2, 0.35)  # The rock with its chips, the haft, the head.
    lock = _lock(arrive)
    GRIP, UP, TAP, P = (40.0, 34.0, 0.0), 0.12, -0.62, 1.4
    HIT = (2.0, 4.0, 0.0)

    def parts(rng):
        rock = _rock(rng, 300)
        rock.sort(key=lambda g: math.dist(g[:3], HIT))
        return [rock, *_pick(rng, 110, 230)]

    def alpha(c):
        if c < 0.0:
            return UP
        if c < 0.2:
            return TAP + 0.08 * sin(math.pi * c / 0.2)
        if c < 1.0:
            return TAP + (UP - TAP) * _smooth((c - 0.2) / 0.8)
        if c < 1.1:
            return UP
        return UP + (TAP - UP) * ((c - 1.1) / 0.3) ** 2

    def frame(T):
        c = _cycle(T, lock - 1.0, P)
        hit = c if c >= 0.0 and T >= lock + 0.4 - 1e-9 else -1.0
        jolt = 1.8 * exp(-hit / 0.09) * sin(40.0 * hit) if hit >= 0.0 else 0.0
        pick = _swing_pose(alpha(c), GRIP, 0.68, 0.25)
        pick = (pick[0], (pick[1][0], pick[1][1] - 12.0 * (1.0 - _al(T, arrive[1])), pick[1][2]), 1.0)

        def rock(rec):
            g = rec[3]
            x, y, z = g[0] + jolt, g[1], g[2]
            chip = math.dist(g[:3], HIT) < 11.0 and hit >= 0.0
            if not chip:
                return x, y, z, g[3], g[4], g[5], 1.0
            r = rec[2]
            fall = 0.45 + 0.2 * r
            if hit < fall:
                f = hit / fall
                ox, oy = g[0] + (14.0 + 18.0 * r) * f, g[1] - (16.0 + 16.0 * r) * 4.0 * f * (1.0 - f) * 0.6
                oy += (40.0 - g[1]) * f * f
                return ox, oy, g[2] + 6.0 * (r - 0.5) * f, 0.0, 0.0, 0.0, 1.1
            back = _smooth((hit - fall) / 0.7)
            ox, oy = g[0] + (14.0 + 18.0 * r) * (1.0 - back), 40.0 + (g[1] - 40.0) * back
            return ox, oy, g[2] * back + 3.0 * (r - 0.5) * (1.0 - back), *(v * back for v in g[3:6]), 1.0
        return _view(0.0, -0.22), (rock, pick, pick), None
    return _Sketch("Ore node", arrive, parts, frame)


def _pickaxe_c():
    """The dig: the pick chops at the ground in a quick, steady rhythm, and each chop throws a spadeful of dust in an
    arc onto a pile beside the hole. After four chops the pile slumps and slides back into the hole."""
    arrive = (0.0, 0.15, 0.3)  # The dust, the haft, the head.
    lock = _lock(arrive)
    GRIP, UP, CHOP, BEAT, P = (30.0, 32.0, 0.0), -0.5, -1.13, 0.72, 3.6
    HOLE, PILE = (-26.0, 40.0), (-62.0, 40.0)

    def parts(rng):
        return [_loose(140, rng, 0.85, 0.4), *_pick(rng, 160, 340)]

    def alpha(c):
        if c < 0.0 or c >= 4 * BEAT:
            return UP + (CHOP - UP) * 0.15 if c >= 4 * BEAT else UP
        b = c % BEAT
        if b < 0.18:
            return UP + (CHOP - UP) * (b / 0.18) ** 2
        if b < 0.3:
            return CHOP
        return CHOP + (UP - CHOP) * _smooth((b - 0.3) / 0.42)

    def frame(T):
        c = _cycle(T, lock + 0.1, P)
        pick = _swing_pose(alpha(c), GRIP)
        pick = (pick[0], (pick[1][0], pick[1][1] - 12.0 * (1.0 - _al(T, arrive[1])), pick[1][2]), 1.0)
        slump = _smooth((c - 4 * BEAT + 0.1) / 0.7) if c >= 0.0 else 0.0

        def dust(rec):
            g = rec[3]
            u, r = g[7], rec[2]
            # In the hole: loose dust round where the horn bites.
            hx, hz = HOLE[0] + 34.0 * (r - 0.5), 16.0 * (u * 7.0 % 1.0 - 0.5)
            # On the pile: a round mound, filled in from its foot up as the chops come.
            a, rad = TAU * (u * 13.0 % 1.0), math.sqrt(1.0 - u * 0.9)
            px, pz = PILE[0] + 19.0 * rad * cos(a), 11.0 * rad * sin(a)
            py = 40.0 - 10.0 * (1.0 - rad * rad)
            k = int(u * 4.0)
            since = c - k * BEAT - 0.18  # Seconds since this grain's chop bit.
            if c < 0.0 or since < 0.0:
                return hx + g[0], 40.0, hz + g[2], 0.0, 0.0, 0.0, 0.4
            if since < 0.42:
                f = since / 0.42
                return (hx + (px - hx) * f, 40.0 + (py - 40.0) * f - 30.0 * 4.0 * f * (1.0 - f), hz + (pz - hz) * f,
                        0.0, 0.0, 0.0, 1.05)
            return (px + (hx - px) * slump + g[0], py + (40.0 - py) * slump, pz + (hz - pz) * slump + g[2],
                    0.0, 0.0, 0.0, 0.9 - 0.35 * slump)
        return _view(0.0, -0.22), (dust, pick, pick), None
    return _Sketch("Dig", arrive, parts, frame)


# ---------------------------------------------------------------------------
# Round three, after the owner's review on 2026-11-27. The rule: nothing lies under a 3D object, no pool, floor,
# shadow, puff or pile. It floats free, as the other Devs forms do.
#
# sword (find_upgrades), three new drawn swords. Live, find_upgrades turns to prices 2.2 s in, so each sword has
# landed by about 1.9 s and starts its own motion inside that turn.
# ---------------------------------------------------------------------------

def _bands(gs, k):
    """Grains in k bands along a stroke, from its start (u = 0, the guard on a blade) to its end."""
    gs = sorted(gs, key=lambda g: g[7])
    return [gs[len(gs) * j // k:len(gs) * (j + 1) // k] for j in range(k)]


def _cooling(pose, a, T):
    """A rigid part that lands hot and cools to the steel's own light in the 0.6 s after it lands."""
    m, t, glow = pose
    return m, t, glow * (1.0 + 0.2 * (1.0 - _smooth((T - MORPH - a - FLY) / 0.6)))


def _sword3_a():
    """Forged from the loop: the hilt lands first, then dust streams in off the loop's arc and sets the blade band by
    band from the guard to the tip, each band landing hot and cooling to steel. Then the sword stands and turns about
    its length, its facets taking the light in turn."""
    K = 7
    arrive = (0.0, 0.05, 0.1, *(0.2 + 0.075 * j for j in range(K)))  # The pommel, grip and guard, then the bands.
    lock = _lock(arrive)

    def parts(rng):
        blade, guard, grip, pommel = _sword(rng, 370, 120, 80, 70)
        return [pommel, grip, guard, *_bands(blade, K)]

    def frame(T):
        hold = max(0.0, T - lock)
        R = _mm(_rz(0.06), _ry(0.45 + 1.15 * (hold - 0.8 * (1.0 - exp(-hold / 0.8)))))
        bob = 1.6 * sin(1.5 * hold) * _smooth(hold / 1.0)
        return _view(0.0, -0.28), tuple(_cooling(_pose(R, to=(0.0, bob + 7.0 * (1.0 - _al(T, a)), 0.0)), a, T)
                                        for a in arrive), None
    return _Sketch("Forged", arrive, parts, frame)


MOUTH = 30.0  # sword3_b's sheath mouth, a level no one sees: steel below it is in the sheath.


def _sword3_b():
    """Unsheathed: the sword hangs point down in a sheath no one sees, only its hilt showing. It is drawn straight up,
    its steel appearing as it slides out of the sheath's mouth. Clear of it, the sword turns over to stand point up
    and sways, then turns back and slides home, to be drawn again."""
    arrive = (0.0, 0.12, 0.17, 0.22)  # The blade pours into the sheath, then the guard, grip and pommel set on it.
    lock = _lock(arrive)
    DRAW, P, LAG = 70.0, 5.3, 0.35  # LAG: a grain trails its place by about this long on its spring.

    def parts(rng):
        return _sword(rng, 370, 120, 80, 70)

    def motion(c):
        """(drawn, turned over), each 0 to 1, c seconds into a draw."""
        if 0.0 <= c < 0.7:
            return _smooth(c / 0.7), 0.0
        if 0.7 <= c < 4.2:
            return 1.0, _ease_back((c - 0.7) / 1.0, 1.0) if c < 3.4 else 1.0 - _smooth((c - 3.4) / 0.8)
        if 4.2 <= c < 4.9:
            return 1.0 - _smooth((c - 4.2) / 0.7), 0.0
        return 0.0, 0.0

    def sheathed(pose, trail):
        """Steel shows once the place its grain trails behind, trail below its own, is out of the sheath, so no grain
        lights below the mouth while it catches up."""
        def f(rec):
            x, y, z, nx, ny, nz, glow = _place(pose, rec)
            return x, y, z, nx, ny, nz, glow * (1.0 - _smooth((y + trail - MOUTH + 1.0) / 2.5))
        return f

    def frame(T):
        c = _cycle(T, lock - 0.3, P)
        draw, flip = motion(c)
        trail = DRAW * (draw - motion(c - LAG)[0]) if c >= LAG else 0.0
        top = MOUTH - 0.5 - DRAW * draw  # Where the blade meets the guard.
        M = _mm(_ry(0.38 + 0.3 * sin(1.1 * T)), _rz(math.pi * (1.0 + flip)))  # It turns over about its middle.
        return _view(0.0, -0.18), tuple(
            sheathed(_pose(M, (0.0, -12.0, 0.0), (0.0, top + 12.0 - 8.0 * (1.0 - _al(T, a)), 0.0)), trail)
            for a in arrive), None
    return _Sketch("Unsheathed", arrive, parts, frame)


def _sword3_c():
    """Tempered: the blade is forged edge by edge. Its four ridges set first, from the guard to the tip, then its faces
    fill in between them, each band landing hot and cooling. While the sword sways, a temper band of its own steel
    runs up the blade from the guard to the tip now and then."""
    K = 4
    arrive = (0.0, 0.05, 0.1, *(0.18 + 0.07 * j for j in range(K)), *(0.45 + 0.07 * j for j in range(K)))
    lock = _lock(arrive)

    def parts(rng):
        blade, guard, grip, pommel = _sword(rng, 370, 120, 80, 70)
        faces = 370 - round(370 * 0.5)  # _sweep lists its faces' grains first, then its ridges'.
        return [pommel, grip, guard, *_bands(blade[faces:], K), *_bands(blade[:faces], K)]

    def temper(pose, at, e):
        def f(rec):
            x, y, z, nx, ny, nz, glow = _place(pose, rec)
            return x, y, z, nx, ny, nz, glow * (1.0 + e * (0.5 * exp(-((rec[3][7] - at) / 0.13) ** 2) - 0.2))
        return f

    def frame(T):
        hold = max(0.0, T - lock)
        R = _mm(_rz(0.07 * sin(0.7 * hold)), _ry(0.4 + 0.5 * sin(0.85 * hold) * _smooth(hold / 1.2)))
        bob = 1.6 * sin(1.6 * hold) * _smooth(hold / 1.0)
        c = _cycle(T, lock - 0.2, 2.6)
        poses = []
        for p, a in enumerate(arrive):
            pose = _cooling(_pose(R, to=(0.0, bob + 7.0 * (1.0 - _al(T, a)), 0.0)), a, T)
            if p >= 3 and 0.0 <= c < 0.85:
                pose = temper(pose, -0.3 + 1.6 * c / 0.85, sin(math.pi * c / 0.85))
            poses.append(pose)
        return _view(0.0, -0.18), tuple(poses), None
    return _Sketch("Tempered", arrive, parts, frame)


# ---------------------------------------------------------------------------
# pickaxe (find_object), round three: sketch C's quick chops, made logical. The pick chops at an ore chunk that floats
# free. What a chop knocks off flies away and fades; nothing knocked off comes back.
# ---------------------------------------------------------------------------

PICK_GRIP, PICK_UP, PICK_CHOP, PICK_BEAT = (30.0, 32.0, 0.0), -0.5, -1.13, 0.72  # As the dig's (sketch C).


def _chop(c):
    """The pick's angle c seconds into a round of four quick chops. After them it rests raised."""
    if c < 0.0 or c >= 4 * PICK_BEAT:
        return PICK_UP
    b = c % PICK_BEAT
    if b < 0.18:
        return PICK_UP + (PICK_CHOP - PICK_UP) * (b / 0.18) ** 2
    if b < 0.3:
        return PICK_CHOP
    return PICK_CHOP + (PICK_UP - PICK_CHOP) * _smooth((b - 0.3) / 0.42)


_m, _t, _ = _swing_pose(PICK_CHOP, PICK_GRIP)
STRIKE_AT = tuple(a + b for a, b in zip(_mv(_m, (-35.0, -31.0, 0.0)), _t))  # Where the left horn's tip bites.
FACE = _unit((0.62, -0.62, 0.48))  # The struck face's outward normal: up, right and toward the viewer.
CHUNK_R = 19.0
CHUNK_C = tuple(h - 0.9 * CHUNK_R * f for h, f in zip(STRIKE_AT, FACE))


def _since(c, bites):
    """Seconds since the latest of bites (seconds into the round) at c, or -1 before the first."""
    past = [c - b for b in bites if b <= c]
    return min(past) if past else -1.0


def _chip(rec, since):
    """A chip knocked off the struck face since seconds ago: it flies out fast, slows, and fades into loose dust that
    drifts on and up. Unseen on the struck face before its chop and once it has faded. Chips leave from all over the
    face, never from one point, which would flash as a knot of light."""
    g = rec[3]
    a, b = TAU * rec[2], g[7] * 7.31 % 1.0
    d = _unit((FACE[0] + 0.9 * sqrt(b) * cos(a), FACE[1] + 0.9 * sqrt(b) * sin(a), FACE[2] + 0.9 * (b - 0.5)))
    o = tuple(s + 7.0 * (u - f) for s, u, f in zip(STRIKE_AT, d, FACE))
    if since < 0.0 or since > 1.1:
        return (*o, 0.0, 0.0, 0.0, 0.0)
    r = (12.0 + 12.0 * (g[7] * 3.7 % 1.0)) * (1.0 - exp(-since / 0.16)) + 7.0 * since
    glow = 1.2 * _smooth(since / 0.1) * (1.0 - _smooth((since - 0.2) / 0.85))
    return o[0] + d[0] * r + g[0], o[1] + d[1] * r - 4.0 * since + g[1], o[2] + d[2] * r + g[2], 0.0, 0.0, 0.0, glow


def _chips(c, bites):
    """The chips' pose: two sets of chips that take the chops in turn, so each set has faded before it flies again."""
    def f(rec):
        return _chip(rec, _since(c, bites[int(rec[3][7] * 2.0) % 2::2]))
    return f


def _pick_pose(T, c, arrive):
    pick = _swing_pose(_chop(c), PICK_GRIP)
    return pick[0], (pick[1][0], pick[1][1] - 12.0 * (1.0 - _al(T, arrive)), pick[1][2]), 1.0


def _pickaxe3_c():
    """Chips: four quick chops and a breath at an ore chunk floating free. Each bite jolts the chunk, knocks it round a
    little, and throws a spray of chips off its struck face; they fly out, slow, and fade into loose dust that drifts
    away. The chunk keeps turning, so every chop meets a fresh face."""
    arrive = (0.0, 0.0, 0.15, 0.3)  # The chunk, its chips (unseen at the struck face), the haft, the head.
    lock = _lock(arrive)
    P = 3.6
    bites = tuple(j * PICK_BEAT + 0.18 for j in range(4))

    def parts(rng):
        return [_rock(rng, 270, O3, CHUNK_R, math.inf), _loose(60, rng, 1.0, 0.4), *_pick(rng, 110, 200)]

    def frame(T):
        c = _cycle(T, lock + 0.1, P)
        hit = _since(c, bites)
        knocks = (int((T - lock - 0.1) // P) * 4 + sum(1 for b in bites if b <= c)) if c >= 0.0 else 0
        turn = 0.08 * T + 0.22 * (knocks - 1 + _ease_out(hit / 0.3) if hit >= 0.0 else knocks)
        jolt = 1.6 * exp(-hit / 0.09) * sin(40.0 * hit) if hit >= 0.0 else 0.0
        chunk = _pose(_mm(_ry(turn), _rx(0.3)), O3, tuple(k - jolt * f for k, f in zip(CHUNK_C, FACE)))
        pick = _pick_pose(T, c, arrive[2])
        return _view(0.0, -0.22), (chunk, _chips(c, bites), pick, pick), None
    return _Sketch("Chips", arrive, parts, frame)


def _pickaxe3_d():
    """Split: three chops each knock chips off the floating chunk, and it shrinks toward the struck face. The fourth
    splits what is left in two. The halves tumble apart and crumble into dust, and while the pick rests raised the
    drifting dust gathers into a fresh chunk for the next round."""
    arrive = (0.0, 0.0, 0.15, 0.3)
    lock = _lock(arrive)
    P = 4.2
    bites = tuple(j * PICK_BEAT + 0.18 for j in range(4))
    split = bites[3]
    side = _unit((FACE[1], -FACE[0], 0.0))  # Across the stroke: the halves part this way.

    def parts(rng):
        return [_rock(rng, 270, O3, CHUNK_R, math.inf), _loose(60, rng, 1.0, 0.4), *_pick(rng, 110, 200)]

    def frame(T):
        c = _cycle(T, lock + 0.1, P)
        knocks = sum(1 for b in bites[:3] if b <= c)
        size = 1.0 - 0.14 * (knocks - 1 + _ease_out((c - bites[knocks - 1]) / 0.15)) if knocks else 1.0
        hit = _since(c, bites[:3])
        jolt = 1.6 * exp(-hit / 0.09) * sin(40.0 * hit) if hit >= 0.0 and c < split else 0.0
        R = _mm(_ry(0.1 * T), _rx(0.3))
        mid = tuple(s + (k - s) * size - jolt * f for s, k, f in zip(STRIKE_AT, CHUNK_C, FACE))
        sp = c - split
        gather = _smooth((c - 3.0) / 0.95)

        def chunk(rec):
            g = rec[3]
            p, nrm = _mv(R, g[:3]), _mv(R, g[3:6])
            if sp < 0.0:
                return mid[0] + size * p[0], mid[1] + size * p[1], mid[2] + size * p[2], *nrm, 1.0
            # The halves part across the stroke and tumble apart, then crumble into drifting dust.
            s = 1.0 if p[0] * side[0] + p[1] * side[1] + p[2] * side[2] >= 0.0 else -1.0
            part = _ease_out(sp / 0.5)
            q = _mv(_rz(s * 0.9 * part), p)
            crumble = _smooth((sp - 0.2) / 0.55)
            a, b = TAU * rec[2], g[7] * 5.17 % 1.0
            scatter = 9.0 * crumble
            dust = [mid[i] + size * q[i] + side[i] * s * 13.0 * part - FACE[i] * 4.0 * part for i in range(3)]
            dust = (dust[0] + scatter * cos(a) * sqrt(b), dust[1] + scatter * sin(a) * sqrt(b) - 3.0 * sp,
                    dust[2] + scatter * (b - 0.5))
            fresh = tuple(CHUNK_C[i] + p[i] for i in range(3))
            x, y, z = (d + (h - d) * gather for d, h in zip(dust, fresh))
            loose = crumble * (1.0 - gather)
            return (x, y, z, *(nrm if loose < 0.5 else (0.0, 0.0, 0.0)), 1.0 - 0.25 * loose)

        pick = _pick_pose(T, c, arrive[2])
        return _view(0.0, -0.22), (chunk, _chips(c, bites[:3]), pick, pick), None
    return _Sketch("Split", arrive, parts, frame)


def _pickaxe3_e():
    """Whittle (the owner's pick of Split, without the split): four chops each knock chips off the floating chunk and it
    shrinks toward the struck face. Then the pick rests raised over the small chunk, which keeps turning, and that is
    the end: nothing splits, and nothing gathers back."""
    arrive = (0.0, 0.0, 0.15, 0.3)
    lock = _lock(arrive)
    bites = tuple(j * PICK_BEAT + 0.18 for j in range(4))

    def parts(rng):
        return [_rock(rng, 270, O3, CHUNK_R, math.inf), _loose(60, rng, 1.0, 0.4), *_pick(rng, 110, 200)]

    def frame(T):
        c = T - (lock + 0.1) if T >= lock + 0.1 else -1.0  # One round only: the chunk never grows back.
        knocks = sum(1 for b in bites if b <= c)
        size = 1.0 - 0.12 * (knocks - 1 + _ease_out((c - bites[knocks - 1]) / 0.15)) if knocks else 1.0
        hit = _since(c, bites)
        jolt = 1.6 * exp(-hit / 0.09) * sin(40.0 * hit) if hit >= 0.0 else 0.0
        R = _mm(_ry(0.1 * T), _rx(0.3))
        mid = tuple(s + (k - s) * size - jolt * f for s, k, f in zip(STRIKE_AT, CHUNK_C, FACE))

        def chunk(rec):
            g = rec[3]
            p, nrm = _mv(R, g[:3]), _mv(R, g[3:6])
            return mid[0] + size * p[0], mid[1] + size * p[1], mid[2] + size * p[2], *nrm, size * size  # Even light per area: a small chunk never knots into an orb.

        pick = _pick_pose(T, c, arrive[2])
        return _view(0.0, -0.22), (chunk, _chips(c, bites), pick, pick), None
    return _Sketch("Whittle", arrive, parts, frame)


# ---------------------------------------------------------------------------
# The registry, in devs_pack's contract: BUILDERS[name](grains, rng) gives the grain records and EVAL[name](points,
# scene, now) gives (tx, ty, tb, tz), as an eval_targets branch does. The recommended sketch for every icon is A.
# ---------------------------------------------------------------------------

ICONS = {
    "figure": ("find_npc", (_figure_a, _figure_b, _figure_c)),
    "exclaim": ("find_quest", (_exclaim_a, _exclaim_b, _exclaim_c)),
    "chest": ("find_item", (_chest_a, _chest_b, _chest_c)),
    "sword": ("find_upgrades", (_sword_a, _sword_b, _sword_c)),
    "coins": ("find_price", (_coins_a, _coins_b, _coins_c)),
    "pickaxe": ("find_object", (_pickaxe_a, _pickaxe_b, _pickaxe_c)),
}
ROUND3 = {"sword3_a": _sword3_a, "sword3_b": _sword3_b, "sword3_c": _sword3_c, "pickaxe3_c": _pickaxe3_c,
          "pickaxe3_d": _pickaxe3_d, "pickaxe3_e": _pickaxe3_e}
BUILDERS, EVAL = {}, {}
for _name, _make in [(f"{i}2_{l}", m) for i, (_, ms) in ICONS.items() for l, m in zip("abc", ms)] + [*ROUND3.items()]:
    SKETCHES[_name] = _make()
    BUILDERS[_name] = lambda grains, rng, n=_name: _build(n, grains, rng)
    EVAL[_name] = (lambda points, scene, now, n=_name:
                   _evaluate(n, points, now, scene.form_at, float(dp.FORMS_META.get(n, {}).get("persp", PERSP))))


def register():
    """devs_pack's one line: add the forms, and answer eval_targets for them."""
    dp.BUILDERS.update(BUILDERS)
    before = dp.eval_targets

    def eval_targets(name, points, scene, now):
        return EVAL[name](points, scene, now) if name in EVAL else before(name, points, scene, now)
    dp.eval_targets = eval_targets


if __name__ == "__main__":
    # Every sketch has the Devs grain count and a manifest entry, every target is finite over a whole form, and no
    # grain is lit past the bright cap, so no knot of light can bloom into an orb. Run: /usr/bin/python
    # desktop/icons_wow2.py
    import random
    import types
    CAP = 2.0
    for name, build in BUILDERS.items():
        pts = build(640, random.Random(sum(map(ord, name))))
        assert len(pts) == 640 and None not in pts, name
        assert name in dp.FORMS_META, f"{name} has no manifest entry"
        scene, top = types.SimpleNamespace(form_at=0.0), 0.0
        for frame in range(0, 360, 3):
            tx, ty, tb, tz = EVAL[name](pts, scene, frame / 30.0)
            assert all(map(math.isfinite, tx + ty + tb + tz)), (name, frame)
            top = max(top, max(tb))
        print(f"{name:11s} {SKETCHES[name].label:12s} brightest grain {top:4.2f}")
        assert top <= CAP, f"{name} lights a grain past {CAP}"
    print("ok")
