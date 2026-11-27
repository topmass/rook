"""Writing icons, round two: four Devs concepts for writing or editing a file (Edit, Write, NotebookEdit), writing2_a
to writing2_d, for the owner to pick from. Today's form is devs_pack's quill, and ACTIVITY_FORMS still maps the three
tools to it, so none of these shows live.

- A, Nib: a fountain pen writes three lines of words onto a blank page, the ink settling out of its nib. With the
  page full, the words lift off as dust and the pen goes back to the top.
- B, Strike: a written page. A text cursor strikes through a word, backspaces it away as crumbling dust, and types a
  new one in its place. Then it moves on to another word.
- C, Pencil: a pencil writes a line under a line of words, turns over, rubs a word out with its eraser, turns
  back and writes it again. Then the new line lifts away as dust and the pencil writes it once more.
- D, Flourish: a feather quill signs a flourish in the air: a tall loop and a run of waves. The gold ink stays, then
  lifts away as dust from its first stroke on, while the quill goes back to sign again.

They are icons_wow2 sketches: gold dust on lit 3D solids, the send morph in from the resting loop, and motion that
comes from the object itself. No sketch has a glowing bead, a roving point or anything under it. Grains on a face
that turns from the viewer dim. A pen points down and right toward the viewer, as a writer holds it, so it covers
only the lines still to be written. Import this module only through devs_pack, which registers it in one line.

The overlay's springs follow a moving target about LAG seconds late, so a tool shows where its target was LAG ago.
The ink keys on the tool's place LAG ago too, so each word appears under the tool the viewer sees, never ahead of it.
"""

from __future__ import annotations

import math
import random

import devs_pack as dp
import icons_wow2 as w2
from icons_wow2 import (I3, O3, PERSP, TAU, _al, _box, _cycle, _lathe, _lock, _mesh, _mm, _mv, _pose, _quad, _rx, _rz,
                        _seg, _Sketch, _tri, _unit, _view)

sin, cos = math.sin, math.cos
_smooth = dp._smooth
LAG = 0.12  # Seconds a spring-carried grain trails a moving target (1.1 / omega, omega about 9 rad/s).
INK = 1.15  # A text grain's weight, as the other Devs forms' text.
HAND = _unit((0.55, 0.6, 0.58))  # Up a pen from its point: down and right, toward the viewer, as a writer holds it.


# ---------------------------------------------------------------------------
# Shared parts: words, the page, a pen's aim, and what a tool in front of the page hides.
# ---------------------------------------------------------------------------

def _words(seed, x0, x1):
    """Fixed words, (start, end) from x0 to x1, so a sketch's timing and its grains agree on them."""
    r, words, x = random.Random(seed), [], x0
    while x < x1 - 3.0:
        length = min(r.uniform(6.0, 14.0), x1 - x)
        words.append((x, x + length))
        x += length + r.uniform(3.8, 5.0)
    return words


def _text(n, rows, rng, thick=1.8):
    """n grains spread evenly over the words of rows ((y, words), ...). A grain is (x, y, z, 0, 0, 1, INK, u, row,
    word): it faces the viewer, so it takes the light as the page does."""
    spans = [(r, k, a, b, y) for r, (y, words) in enumerate(rows) for k, (a, b) in enumerate(words)]
    total, out = sum(b - a for _, _, a, b, _ in spans), []
    for i in range(n):
        d = total * (i + 0.5) / n
        for r, k, a, b, y in spans:
            if d <= b - a or (r, k) == spans[-1][:2]:
                out.append((a + d + rng.uniform(-0.3, 0.3), y + rng.uniform(-thick, thick), 0.5, 0.0, 0.0, 1.0, INK,
                            rng.random(), r, k))
                break
            d -= b - a
    return out


def _page(n, w, h, ear, rng):
    """A sheet of paper facing the viewer with its top right corner folded down, as a file reads: a faint face, a
    bright outline, and the folded corner lit a little brighter, as it leans toward the key light."""
    x0, x1, y0, y1 = -w / 2, w / 2, -h / 2, h / 2
    up, fold = (0.0, 0.0, 1.0), _unit((-0.3, -0.3, 1.0))
    faces = [_quad((x0, y0, 0.0), (x1 - ear - x0, 0.0, 0.0), (0.0, h, 0.0), up, 0.28),
             _quad((x1 - ear, y0 + ear, 0.0), (ear, 0.0, 0.0), (0.0, h - ear, 0.0), up, 0.28),
             _tri((x1 - ear, y0, 0.4), (x1 - ear, y0 + ear, 0.4), (x1, y0 + ear, 0.4), fold, 0.6)]
    rim = [(x0, y0), (x1 - ear, y0), (x1, y0 + ear), (x1, y1), (x0, y1), (x0, y0)]
    edges = []
    for (ax, ay), (bx, by) in zip(rim, rim[1:]):
        nx, ny = _unit((by - ay, ax - bx, 0.0))[:2]  # Outward in the page's plane, as the rim runs clockwise.
        edges.append(_seg((ax, ay, 0.0), (bx, by, 0.0), _unit((nx, ny, 1.0)), 1.0, 0.2))
    for a, b in (((x1 - ear, y0), (x1 - ear, y0 + ear)), ((x1 - ear, y0 + ear), (x1, y0 + ear))):
        edges.append(_seg((*a, 0.4), (*b, 0.4), fold, 0.9, 0.2))
    return _mesh(n, faces, edges, rng, 0.55)


def _aim(d):
    """The rotation that turns a tool's local -y (from its point up its body) to the direction d."""
    return _mm(_rz(math.atan2(d[0], -d[1])), _rx(-math.asin(d[2])))


def _rod_occ(V, a, b, r):
    """What a rod from a to b of radius r, in front of the page, hides: a grain behind it and within r of its axis
    on screen dims. At the tool's point the rod meets the page, so the fresh ink there stays lit."""
    av, bv = _mv(V, a), _mv(V, b)
    qa, qb = 1.0 / (1.0 - av[2] / PERSP), 1.0 / (1.0 - bv[2] / PERSP)
    ax, ay, dx, dy = av[0] * qa, av[1] * qa, bv[0] * qb - av[0] * qa, bv[1] * qb - av[1] * qa
    l2 = dx * dx + dy * dy or 1.0

    def occ(xv, yv, zv):
        q = 1.0 / (1.0 - zv / PERSP)
        x, y = xv * q - ax, yv * q - ay
        t = min(1.0, max(0.0, (x * dx + y * dy) / l2))
        if zv > av[2] + (bv[2] - av[2]) * t - 1.5:
            return 1.0
        return 1.0 - 0.92 * _smooth((r + 1.0 - math.hypot(x - t * dx, y - t * dy)) / 2.0)
    return occ


def _sway(T, reach=0.05, period=10.0):
    return reach * sin(TAU * T / period)


def _lift(g, rec, u, up=9.0):
    """A text grain lifting off as loose dust, a share u of the way: it rises, drifts toward the viewer and apart,
    and fades."""
    return (g[0] + 3.0 * (g[7] - 0.5) * u, g[1] - (up + 5.0 * rec[2]) * u, g[2] + 7.0 * u, 0.0, 0.0, 0.0,
            (1.0 - u) ** 2)


def _settle(g, k):
    """A text grain being written, a share k of the way: it settles onto its line out of the tool's point."""
    return g[0], g[1] - 0.8 * (1.0 - k), g[2] + 1.6 * (1.0 - k), g[3], g[4], g[5], k * (1.0 + 0.12 * (1.0 - k))


def _gap(words, x):
    """1 between words at x, 0 on a word: a pen lifts a little between words."""
    return 0.0 if any(a - 1.0 <= x <= b + 1.0 for a, b in words) else 1.0


# ---------------------------------------------------------------------------
# A: Nib. A fountain pen writes a page full.
# ---------------------------------------------------------------------------

NIB_W, NIB_H, NIB_EAR = 68.0, 74.0, 14.0  # The page.
NIB_X0, NIB_ROWS = -26.0, ((-19.0, 24.0), (-2.0, 24.0), (15.0, 4.0))  # The lines' left end; each line's y and end.
NIB_V, NIB_RET, NIB_REST, NIB_BACK = 40.0, 0.7, 0.3, 1.0  # Pen speed; carriage return; rest when done; back to top.
NIB_LIFT, NIB_LEN = 0.8, 48.0  # A word's lift off the page as dust; the pen's length.
NIB_HAND = _unit((0.5, 0.64, 0.4))  # The pen leans less toward the viewer than HAND, so its length shows.


def _fountain_pen(rng, n_barrel, n_nib):
    """A fountain pen with its nib's point at the origin and its barrel up along -y: a round barrel with a cap band,
    a tapered section, and a flat nib with a slit. The barrel carries grains on its front only; the pen never turns."""
    front = (-0.35, math.pi + 0.35)
    barrel = _lathe(n_barrel, ((1.8, -NIB_LEN), (3.2, -47.0), (3.6, -45.0), (3.6, -21.0), (3.3, -19.0), (2.5, -10.5)),
                    rng, rings=((3.8, -28.0, (1.0, 0.0)), (3.75, -21.0, (1.0, 0.0))), ring_share=0.16, arc=front)
    up = (0.0, 0.0, 1.0)
    tip, l, r = (0.0, -1.4, 1.2), (-3.3, -12.0, 1.2), (3.3, -12.0, 1.2)
    nib = _mesh(n_nib, [_tri(l, r, (0.0, 0.0, 1.2), up, 0.85)],
                [_seg(l, tip, _unit((-1.0, 0.25, 1.0)), 1.0, 0.15), _seg(r, tip, _unit((1.0, 0.25, 1.0)), 1.0, 0.15),
                 _seg((0.0, -7.5, 1.3), (0.0, -3.0, 1.3), up, 0.7, 0.1)], rng, 0.45)
    return barrel, nib


def _writing2_a():
    """Nib: the pen writes each line left to right, lifting a little between words, and its ink settles out of the
    nib onto the page. It returns to the next line, as a hand does. With the page full it rests, the words lift off
    as dust from the top line down, and the pen goes back to the top to write the page again."""
    arrive = (0.0, 0.0, 0.25, 0.3)  # The page, its unwritten ink, the barrel, the nib.
    lock = _lock(arrive)
    start = lock + 0.15
    rows = [(y, _words(11 + r, NIB_X0, end)) for r, (y, end) in enumerate(NIB_ROWS)]
    times, t = [], 0.0  # Each line's start.
    for r, (_, end) in enumerate(NIB_ROWS):
        times.append(t)
        t += (end - NIB_X0) / NIB_V + (NIB_RET if r < len(NIB_ROWS) - 1 else 0.0)
    done = t
    gone = done + NIB_REST  # The words start to lift, and the pen starts back.
    period = gone + NIB_BACK + 0.3
    R = _aim(NIB_HAND)

    def nib_at(c):
        """The nib's point at c seconds into the cycle."""
        if c < 0.0:
            return NIB_X0, NIB_ROWS[0][0], 5.0
        for r, (y, end) in enumerate(NIB_ROWS):
            t1 = times[r] + (end - NIB_X0) / NIB_V
            if c < t1:
                x = NIB_X0 + NIB_V * (c - times[r])
                g = _gap(rows[r][1], x)
                return x, y - 0.8 * g, 2.0 * g
            if r < len(NIB_ROWS) - 1 and c < t1 + NIB_RET:
                f = _smooth((c - t1) / NIB_RET)
                ny = NIB_ROWS[r + 1][0]
                return end + (NIB_X0 - end) * f, y + (ny - y) * f - 3.0 * sin(math.pi * f), 6.0 * sin(math.pi * f)
        y, end = NIB_ROWS[-1]
        f = _smooth((c - gone) / NIB_BACK)
        lift = 2.0 * _smooth((c - done) / 0.3)
        return (end + (NIB_X0 - end) * f, y + (NIB_ROWS[0][0] - y) * f - 4.0 * sin(math.pi * f),
                lift + (5.0 - lift) * f + 6.0 * sin(math.pi * f))

    def parts(rng):
        barrel, nib = _fountain_pen(rng, 160, 44)
        return [_page(130, NIB_W, NIB_H, NIB_EAR, rng), _text(306, rows, rng), barrel, nib]

    def frame(T):
        c = _cycle(T, start, period)
        x, y, z = nib_at(c)
        tip = (x, y - 10.0 * (1.0 - _al(T, arrive[2])), z)
        pen = _pose(R, O3, tip)
        seen = c - LAG  # Where the pen shows now: the ink keys on it.

        def ink(rec):
            g = rec[3]
            if c < 0.0:
                return (*g[:6], 0.0)
            w = times[g[8]] + (g[0] - NIB_X0) / NIB_V  # When the nib reaches it.
            off = gone + 0.2 * g[8] + 0.3 * rec[2]
            if seen < w or c >= off + NIB_LIFT:
                return (*g[:6], 0.0)
            if c >= off:
                return _lift(g, rec, _smooth((c - off) / NIB_LIFT))
            return _settle(g, _smooth((seen - w) / 0.12))

        V = _view(-0.18 + _sway(T), -0.12)
        top = tuple(p + q for p, q in zip(tip, _mv(R, (0.0, -NIB_LEN, 0.0))))
        return V, ((I3, O3, 1.0), ink, pen, pen), _rod_occ(V, tip, top, 3.8)
    return _Sketch("Nib", arrive, parts, frame, hides=(0, 1))


# ---------------------------------------------------------------------------
# B: Strike. A cursor strikes a word out and types a new one.
# ---------------------------------------------------------------------------

STR_W, STR_H, STR_EAR = 76.0, 66.0, 13.0
STR_X0, STR_ROWS = -29.0, ((-15.0, 29.0), (0.0, 29.0), (15.0, 8.0))  # The lines' left end; each line's y and end.
STR_ORDER = ((1, 0), (0, 0), (2, 0), (1, 1))  # The words edited in turn: (line, its longest word or the next).
# The edit's beats, in seconds: glide to the word, strike it, wait, backspace it, wait, type the new word, rest.
STR_GLIDE, STR_STRIKE, STR_WAIT, STR_BACK, STR_EMPTY, STR_TYPE, STR_DONE = 0.5, 0.5, 0.35, 0.45, 0.6, 0.5, 0.7
STR_CRUMB, STR_PAD = 0.4, 1.8  # A backspaced grain's crumble; the cursor's gap from a word's ends.


def _writing2_b():
    """Strike: the page is written. The cursor glides to a word and sweeps across it, drawing a strike line through
    it, and the word dims. It backspaces: the struck word crumbles into dust that lifts away as the cursor passes.
    It blinks in the gap, types the new word, rests, then moves on to the next word."""
    arrive = (0.0, 0.08, 0.3, 0.3)  # The page, its words, the strike line (unseen), the cursor.
    lock = _lock(arrive)
    start = lock + 0.1
    rows = [(y, _words(21 + r, STR_X0, end)) for r, (y, end) in enumerate(STR_ROWS)]
    edits = []
    for r, rank in STR_ORDER:
        by_length = sorted(range(len(rows[r][1])), key=lambda k: rows[r][1][k][0] - rows[r][1][k][1])
        edits.append((r, by_length[rank]))
    s0 = STR_GLIDE
    s1 = s0 + STR_STRIKE
    b0 = s1 + STR_WAIT
    b1 = b0 + STR_BACK
    t0 = b1 + STR_EMPTY
    t1 = t0 + STR_TYPE
    period = t1 + STR_DONE
    first = (rows[-1][1][-1][1] + STR_PAD, STR_ROWS[-1][0])  # The cursor starts after the last word on the page.

    def span(k):
        r, w = edits[k % len(edits)]
        a, b = rows[r][1][w]
        return r, w, a, b, rows[r][0]

    def across(c, c0, length):
        """A share of the way across the word, c0 to c0 + length seconds."""
        return min(1.0, max(0.0, (c - c0) / length))

    def state(T):
        """(edit number, seconds into it, the cursor's x and y), or edit -1 before the first."""
        if T < start:
            return -1, 0.0, first
        k, c = divmod(T - start, period)
        k = int(k)
        _, _, a, b, y = span(k)
        if k == 0:
            bx, by = first
        else:
            _, _, _, pb, by = span(k - 1)
            bx = pb + STR_PAD
        lo, hi = a - STR_PAD, b + STR_PAD
        if c < s0:
            f = _smooth(c / STR_GLIDE)
            return k, c, (bx + (lo - bx) * f, by + (y - by) * f)
        if c < b0:
            x = lo + (hi - lo) * across(c, s0, STR_STRIKE)
        elif c < t0:
            x = hi - (hi - lo) * across(c, b0, STR_BACK)
        else:
            x = lo + (hi - lo) * across(c, t0, STR_TYPE)
        return k, c, (x, y)

    def parts(rng):
        cursor = (_box(64, (0.0, 0.0, 0.0), (1.1, 10.5, 1.1), rng, 0.5)
                  + _box(10, (0.0, -10.5, 0.0), (3.0, 0.7, 1.1), rng, 0.5)
                  + _box(10, (0.0, 10.5, 0.0), (3.0, 0.7, 1.1), rng, 0.5))
        strike = [(0.0, 0.0, 0.9, 0.0, 0.0, 1.0, 1.25, (j // 2 + 0.5 + rng.uniform(-0.25, 0.25)) / 26, -1, j % 2)
                  for j in range(52)]
        return [_page(120, STR_W, STR_H, STR_EAR, rng), _text(384, rows, rng), strike, cursor]

    def frame(T):
        k, c, (cx, cy) = state(T)
        seen_k, seen_c, _ = state(T - LAG)  # Where the cursor shows now: the edit keys on it.
        blink = 1.0
        if k < 0 or s1 <= c < b0 or b1 <= c < t0 or c >= t1:
            blink = 0.3 + 0.7 * _smooth((0.5 + 0.5 * cos(TAU * T / 1.05) - 0.25) / 0.5)
        cursor = _pose(I3, O3, (cx, cy - 8.0 * (1.0 - _al(T, arrive[3])), 1.2), blink)
        r, w, a, b, y = span(seen_k) if seen_k >= 0 else (-1, -1, 0.0, 1.0, 0.0)
        lo, hi = a - STR_PAD, b + STR_PAD

        def when(c0, length, x, back=False):
            """When the cursor, crossing the word in length seconds from c0, reaches x."""
            f = (x - lo) / (hi - lo)
            return c0 + length * ((1.0 - f) if back else f)

        def crumble(g, rec, x, y0, at):
            """A grain the backspace reached at seen time at: it crumbles and lifts away, or None once gone."""
            u = _smooth((seen_c - at) / STR_CRUMB)
            if u >= 1.0:
                return None
            return (x + 2.5 * (g[7] - 0.5) * u, y0 - (4.0 + 4.0 * rec[2]) * u, g[2] + 4.0 * u, 0.0, 0.0, 0.0,
                    0.75 * (1.0 - u) ** 2)

        def word(rec):
            g = rec[3]
            if g[8] != r or g[9] != w:
                return (*g[:6], 1.0)
            x = g[0]
            at_back, at_type = when(b0, STR_BACK, x, True), when(t0, STR_TYPE, x)
            if seen_c < when(s0, STR_STRIKE, x):
                return (*g[:6], 1.0)
            if seen_c < at_back:
                return (*g[:6], 0.42)  # Struck: it dims under the bright strike line.
            if seen_c < at_type:
                return crumble(g, rec, x, g[1], at_back) or (*g[:6], 0.0)
            return _settle(g, _smooth((seen_c - at_type) / 0.1))

        def strike(rec):
            g = rec[3]
            if seen_k < 0:
                return (*first, 0.9, 0.0, 0.0, 1.0, 0.0)
            x = a - 0.8 + (b - a + 1.6) * g[7]
            here = (x, y + (0.55 if g[9] else -0.55), 0.9, 0.0, 0.0, 1.0)
            at_back = when(b0, STR_BACK, x, True)
            if seen_c < when(s0, STR_STRIKE, x):
                return (*here, 0.0)
            if seen_c < at_back:
                return (*here, 1.0)
            out = crumble(g, rec, x, here[1], at_back)
            if out:
                return out
            _, _, na, nb, ny = span(seen_k + 1)  # Unseen: it waits at the next word to strike.
            return na - 0.8 + (nb - na + 1.6) * g[7], ny, 0.9, 0.0, 0.0, 1.0, 0.0

        return _view(-0.16 + _sway(T), -0.1), ((I3, O3, 1.0), word, strike, cursor), None
    return _Sketch("Strike", arrive, parts, frame)


# ---------------------------------------------------------------------------
# C: Pencil. The pencil writes a line, turns over, rubs a word out, turns back and writes it again.
# ---------------------------------------------------------------------------

PEN_X0, PEN_ROWS = -36.0, ((-9.0, 30.0), (9.0, 20.0))  # The lines' left end; each line's y and end.
PEN_L, PEN_V = 54.0, 36.0  # The pencil from its point to its eraser's end; its writing speed.
# The beats: write the line, turn over, rub the last word out, turn back, write it again, rest, then the line lifts.
PEN_FLIP, PEN_RUB, PEN_STROKES, PEN_REST, PEN_BACK = 0.7, 0.95, 3, 0.3, 0.95
PEN_CRUMB, PEN_LIFT = 0.55, 0.8


def _pencil(rng, n):
    """A hexagonal pencil, point at the origin and eraser up along -y: graphite point, sharpened wood, six flat sides
    with bright ridges, a banded ferrule and a rounded eraser. It turns over, so it has grains all round."""
    hexa = [(3.8 * cos(TAU * (k + 0.5) / 6), 3.8 * sin(TAU * (k + 0.5) / 6)) for k in range(6)]
    faces, ridges = [], []
    for k in range(6):
        (ax, az), (bx, bz) = hexa[k], hexa[(k + 1) % 6]
        mid = TAU * (k + 1) / 6
        faces.append(_quad((ax, -11.0, az), (bx - ax, 0.0, bz - az), (0.0, -32.0, 0.0), (cos(mid), 0.0, sin(mid)),
                           0.85))
        ridges.append(_seg((ax, -11.0, az), (ax, -43.0, az), _unit((ax, 0.0, az)), 1.1, 0.12))
    body = _mesh(round(n * 0.5), faces, ridges, rng, 0.36)
    wood = _lathe(round(n * 0.1), ((3.5, -11.0), (1.2, -3.2)), rng, w=0.75)
    lead = _lathe(6, ((1.15, -3.0), (0.5, -1.0)), rng, w=0.8)
    ferrule = _lathe(round(n * 0.14), ((3.95, -48.0), (3.95, -43.0)), rng,
                     rings=((4.05, -47.8, (1.0, 0.0)), (4.05, -45.5, (1.0, 0.0)), (4.05, -43.2, (1.0, 0.0))),
                     ring_share=0.55, w=0.95)
    eraser = _lathe(n - len(body) - len(wood) - len(lead) - len(ferrule),
                    ((2.2, -PEN_L), (3.4, -53.2), (3.65, -51.8), (3.65, -48.0)), rng, w=0.6)
    return body + wood + lead + ferrule + eraser


def _writing2_c():
    """Pencil: a line of words floats above, and the pencil writes the line under it. It turns over end for end
    onto the line's longest word and its eraser rubs it out in three strokes; the first crumbles it into crumbs that
    scatter away from the pencil and fade. It turns back over, writes the word again and rests. Then the new line lifts away as dust while
    the pencil goes back to its start, to write the line once more."""
    arrive = (0.0, 0.3)  # The words, the pencil.
    lock = _lock(arrive)
    start = lock + 0.1
    rows = [(y, _words(33 + r, PEN_X0, end)) for r, (y, end) in enumerate(PEN_ROWS)]
    y1, end1 = PEN_ROWS[1]
    a, b = max(rows[1][1], key=lambda w: w[1] - w[0])  # The word it rubs out: the line's longest.
    write = (end1 - PEN_X0) / PEN_V
    f0 = write + PEN_FLIP
    r1 = f0 + PEN_RUB
    f1 = r1 + PEN_FLIP
    w1 = f1 + (b - a) / PEN_V
    gone = w1 + PEN_REST
    period = gone + PEN_BACK + 0.25
    stroke = PEN_RUB / PEN_STROKES
    R0 = _aim(HAND)

    def turn(theta):
        """The pencil turned by theta in the screen's plane, so it keeps its length on screen as it turns over and
        never points at the viewer, which would gather its grains into a knot."""
        return _mm(_rz(theta), R0)

    def flip(f, p, q, over):
        """Turning over, a share f of the way, from contact at p to contact at q; over: from the point to the
        eraser, and back again when not. It turns about its middle, which moves from p's side to q's."""
        theta = math.pi * (f if over else 1.0 - f)
        Rf = turn(theta)
        half = _mv(Rf, (0.0, -PEN_L / 2, 0.0))  # From its point to its middle.
        lo, hi = _mv(turn(0.0), (0.0, -PEN_L / 2, 0.0)), _mv(turn(math.pi), (0.0, PEN_L / 2, 0.0))
        a0, a1 = (lo, hi) if over else (hi, lo)  # From the contact to the middle, before and after.
        m = [pp + (qq - pp) * f + u + (v - u) * f for pp, qq, u, v in zip(p, q, a0, a1)]
        m[2] += 4.0 * sin(math.pi * f)
        return Rf, tuple(mm - h for mm, h in zip(m, half))

    def pose(c):
        """(rotation, place of its local origin, the point) at c seconds into the cycle."""
        if c < 0.0:
            return R0, (PEN_X0, y1, 4.0)
        if c < write:
            x = PEN_X0 + PEN_V * c
            g = _gap(rows[1][1], x)
            return R0, (x, y1 - 0.8 * g, 2.0 * g)
        if c < f0:
            return flip(_smooth((c - write) / PEN_FLIP), (end1, y1, 0.0), (a, y1, 0.0), True)
        if c < r1:
            s = (c - f0) / stroke
            f = _smooth(s % 1.0)
            ex = a + (b - a) * (f if int(s) % 2 == 0 else 1.0 - f)
            Rp = turn(math.pi)
            return Rp, tuple(p - q for p, q in zip((ex, y1, 0.0), _mv(Rp, (0.0, -PEN_L, 0.0))))
        if c < f1:
            return flip(_smooth((c - r1) / PEN_FLIP), (b, y1, 0.0), (a, y1, 0.0), False)
        if c < w1:
            return R0, (a + PEN_V * (c - f1), y1, 0.0)
        if c < gone:
            return R0, (b, y1, 2.0 * _smooth((c - w1) / 0.3))
        f = _smooth((c - gone) / PEN_BACK)
        return R0, (b + (PEN_X0 - b) * f, y1 - 5.0 * sin(math.pi * f), 2.0 + 2.0 * f + 7.0 * sin(math.pi * f))

    def parts(rng):
        return [_text(340, rows, rng), _pencil(rng, 300)]

    def frame(T):
        c = _cycle(T, start, period)
        Rp, at = pose(c)
        at = (at[0], at[1] - 10.0 * (1.0 - _al(T, arrive[1])), at[2])
        seen = c - LAG

        def word(rec):
            g = rec[3]
            if g[8] == 0:
                return (*g[:6], 1.0)
            x = g[0]
            if c < 0.0 or seen < (x - PEN_X0) / PEN_V:
                return (*g[:6], 0.0)
            off = gone + 0.4 * rec[2]
            if c >= off:
                return _lift(g, rec, _smooth((c - off) / PEN_LIFT)) if c < off + PEN_LIFT else (*g[:6], 0.0)
            if not a - 0.5 <= x <= b + 0.5:
                return _settle(g, _smooth((seen - (x - PEN_X0) / PEN_V) / 0.12))
            at_rub = f0 + stroke * (x - a) / (b - a)  # The first stroke reaches it (roughly, as it eases).
            at_write = f1 + (x - a) / PEN_V
            if seen < at_rub:
                return _settle(g, _smooth((seen - (x - PEN_X0) / PEN_V) / 0.12))
            if seen < at_write:
                u = _smooth((seen - at_rub) / PEN_CRUMB)
                if u >= 1.0:
                    return (*g[:6], 0.0)
                return (x - (2.0 + 3.0 * g[7]) * u, g[1] - (2.0 + 4.0 * rec[2]) * u, g[2] + 3.0 * u,
                        0.0, 0.0, 0.0, 0.9 * (1.0 - u) ** 2)
            return _settle(g, _smooth((seen - at_write) / 0.12))

        far = tuple(p + q for p, q in zip(at, _mv(Rp, (0.0, -PEN_L, 0.0))))
        lo, hi = (at, far) if at[2] <= far[2] else (far, at)
        V = _view(-0.16 + _sway(T), -0.12)
        return V, (word, _pose(Rp, O3, at)), _rod_occ(V, lo, hi, 3.8)
    return _Sketch("Pencil", arrive, parts, frame, hides=(0,))


# ---------------------------------------------------------------------------
# D: Flourish. A feather quill signs in the air.
# ---------------------------------------------------------------------------

FL_KNOTS = ((-50.0, 14.0), (-36.0, 4.0), (-24.0, -14.0), (-20.0, -28.0), (-27.0, -30.0), (-31.0, -20.0),
            (-27.0, -2.0), (-20.0, 12.0), (-12.0, 14.0), (-4.0, 4.0), (2.0, -4.0), (9.0, 4.0), (15.0, 12.0),
            (22.0, 4.0), (28.0, -4.0), (35.0, 4.0), (41.0, 12.0), (49.0, 6.0), (56.0, -8.0))  # A tall loop, waves, a flick.
FL_V, FL_REST, FL_BACK, FL_LIFT = 55.0, 0.4, 1.3, 0.8  # Pen speed; rest when signed; back to the start; ink lift.
FL_QUILL = 52.0  # The quill's length.


def _flourish_path(per=24):
    """The flourish through FL_KNOTS (a Catmull-Rom curve), and each point's distance along it."""
    k = (FL_KNOTS[0], *FL_KNOTS, FL_KNOTS[-1])
    raw = []
    for i in range(1, len(k) - 2):
        p0, p1, p2, p3 = k[i - 1], k[i], k[i + 1], k[i + 2]
        for j in range(per):
            t = j / per
            raw.append(tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t
                                    + (-a + 3 * b - 3 * c + d) * t ** 3) for a, b, c, d in zip(p0, p1, p2, p3)))
    raw.append(FL_KNOTS[-1])
    ss = [0.0]
    for p, q in zip(raw, raw[1:]):
        ss.append(ss[-1] + math.dist(p, q))
    return raw, ss


def _quill(rng, n):
    """A feather quill, its cut point at the origin and its shaft up along -y with a slight curve: a bare calamus, a
    rachis, and barbs that sweep up off both sides, the left vane wider. The vane curls a little toward the viewer."""
    pts = []

    def shaft(s):
        return 2.0 * s * s, -FL_QUILL * s

    n_shaft = round(n * 0.22)
    for k in range(n_shaft):
        s = 0.04 + 0.96 * (k + rng.random()) / n_shaft
        x, y = shaft(s)
        side = 0.7 if s < 0.3 else 0.4
        pts.append((x + side * (1 if k % 2 else -1), y, 0.0, 0.0, 0.0, 1.0, 1.0, s))
    per = []
    for side, width, count in ((-1, 8.5, 14), (1, 5.0, 14)):
        for j in range(count):
            s = 0.3 + 0.68 * (j + 0.5) / count
            per.append((side, s, width * sin(math.pi * min(1.0, (s - 0.28) / 0.72)) ** 0.55))
    left = n - n_shaft
    total = sum(w for _, _, w in per)
    for i, (side, s, w) in enumerate(per):
        c = min(left, round((n - n_shaft) * w / total) if i < len(per) - 1 else left)
        left -= c
        x0, y0 = shaft(s)
        for k in range(c):
            f = (k + 0.6 + rng.uniform(-0.2, 0.2)) / (c + 0.4)
            pts.append((x0 + side * w * f, y0 - 0.1 * FL_QUILL * f, 1.6 * f * f, *_unit((side * -0.3 * f, 0.15, 1.0)),
                        0.55 + 0.2 * (1.0 - f), s))
    return pts


def _writing2_d():
    """Flourish: the quill signs a tall loop and a run of waves in the air, ending in a flick, and the gold ink
    stays where its point passed. Signed, it rests a beat. The ink lifts away as dust from its first stroke on, while
    the quill glides back to the start to sign again."""
    arrive = (0.0, 0.3)  # The ink (unseen), the quill.
    lock = _lock(arrive)
    start = lock + 0.1
    path, ss = _flourish_path()
    length = ss[-1]
    sign = length / FL_V
    back = sign + FL_REST
    period = back + FL_BACK + 0.3
    R = _aim(_unit((0.5, -0.78, 0.38)))  # The feather leans up and right, as a quill is held.

    def at(s):
        """The flourish's point s units along it."""
        s = min(length, max(0.0, s))
        lo, hi = 0, len(ss) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if ss[mid] <= s else (lo, mid)
        f = (s - ss[lo]) / ((ss[hi] - ss[lo]) or 1.0)
        return path[lo][0] + (path[hi][0] - path[lo][0]) * f, path[lo][1] + (path[hi][1] - path[lo][1]) * f

    def tip_at(c):
        if c < 0.0:
            return (*path[0], 4.0)
        if c < sign:
            return (*at(FL_V * c), 0.0)
        (x1, y1), (x0, y0) = path[-1], path[0]
        lift = 3.0 * _smooth((c - sign) / 0.3)
        f = _smooth((c - back) / FL_BACK)
        return (x1 + (x0 - x1) * f, y1 + (y0 - y1) * f - 8.0 * sin(math.pi * f),
                lift + (4.0 - lift) * f + 8.0 * sin(math.pi * f))

    def parts(rng):
        ink, n = [], 410
        for k in range(n):
            s = length * (k + 0.5 + rng.uniform(-0.3, 0.3)) / n
            x, y = at(s)
            ink.append((x + rng.gauss(0, 0.45), y + rng.gauss(0, 0.45), rng.gauss(0, 0.4), 0.0, 0.0, 0.0, 1.05,
                        s / length))
        return [ink, _quill(rng, 640 - n)]

    def frame(T):
        c = _cycle(T, start, period)
        x, y, z = tip_at(c)
        rock = 0.04 * sin(TAU * c / 1.7) if 0.0 <= c < sign else 0.0
        quill = _pose(_mm(_rz(rock), R), O3, (x, y - 10.0 * (1.0 - _al(T, arrive[1])), z))
        seen = c - LAG

        def ink(rec):
            g = rec[3]
            if c < 0.0:
                return (*g[:6], 0.0)
            w = g[7] * sign
            off = back + 0.9 * g[7] + 0.2 * rec[2]
            if seen < w or c >= off + FL_LIFT:
                return (*g[:6], 0.0)
            if c >= off:
                u = _smooth((c - off) / FL_LIFT)
                return (g[0] + 3.0 * (rec[2] - 0.5) * u, g[1] - (8.0 + 5.0 * rec[2]) * u, g[2] + 6.0 * u,
                        0.0, 0.0, 0.0, (1.0 - u) ** 2)
            k = _smooth((seen - w) / 0.1)
            return g[0], g[1], g[2] + 1.5 * (1.0 - k), 0.0, 0.0, 0.0, k

        return _view(-0.12 + _sway(T, 0.04), -0.08), (ink, quill), None
    return _Sketch("Flourish", arrive, parts, frame)


# ---------------------------------------------------------------------------
# The registry, in devs_pack's contract, through icons_wow2's machinery (its build, evaluation and fit).
# ---------------------------------------------------------------------------

SKETCHES = {"writing2_a": _writing2_a, "writing2_b": _writing2_b, "writing2_c": _writing2_c,
            "writing2_d": _writing2_d}
SPANS = {"writing2_a": 8.0, "writing2_b": 17.0, "writing2_c": 8.0, "writing2_d": 8.0}  # A full turn of each.


def _fit(name):
    """icons_wow2's fit (the box every lit grain covers, fitted to the Devs form box), over the sketch's whole turn
    and not only its first 7 s, so a later edit never takes the form past the box."""
    sk = w2.SKETCHES[name]
    parts, lock, xs, ys = sk.parts(random.Random(0)), _lock(sk.arrive), [], []
    for k in range(int(SPANS[name] / 0.2)):
        V, poses, _ = sk.frame(lock + 0.2 * k)
        for p, part in enumerate(parts):
            for g in part[::3]:
                x, y, z, *_, glow = w2._place(poses[p], (0.0, p, 0.5, g))
                if glow > 0.05:
                    xv, yv, zv = _mv(V, (x, y, z))
                    q = 1.0 / (1.0 - zv / PERSP)
                    xs.append(xv * q)
                    ys.append(yv * q)
    k = min(w2.BOX_W / (max(xs) - min(xs)), w2.BOX_H / (max(ys) - min(ys)))
    w2._FIT[name] = (k, (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0 - w2.FOOT / k)


def _build(name, grains, rng):
    if name not in w2._FIT:
        _fit(name)
    return w2._build(name, grains, rng)


BUILDERS, EVAL = {}, {}
for _name, _make in SKETCHES.items():
    w2.SKETCHES[_name] = _make()
    BUILDERS[_name] = lambda grains, rng, n=_name: _build(n, grains, rng)
    EVAL[_name] = (lambda points, scene, now, n=_name:
                   w2._evaluate(n, points, now, scene.form_at, float(dp.FORMS_META.get(n, {}).get("persp", PERSP))))


def register():
    """devs_pack's one line: add the forms, and answer eval_targets for them."""
    dp.BUILDERS.update(BUILDERS)
    before = dp.eval_targets

    def eval_targets(name, points, scene, now):
        return EVAL[name](points, scene, now) if name in EVAL else before(name, points, scene, now)
    dp.eval_targets = eval_targets


if __name__ == "__main__":
    # Every sketch has the Devs grain count and a manifest entry, finite targets, no grain past the bright cap (so no
    # knot of light can bloom into an orb), and stays in the Devs form box over 12 s. Run it capped:
    #   scripts/capped /usr/bin/python desktop/icons_writing.py
    import types

    CAP = 2.0
    trouble = []
    for name, build in BUILDERS.items():
        pts = build(640, random.Random(sum(map(ord, name))))
        assert len(pts) == 640 and None not in pts, name
        assert name in dp.FORMS_META, f"{name} has no manifest entry"
        scene, top, box = types.SimpleNamespace(form_at=0.0), 0.0, [0.0, 0.0, 0.0, 0.0]
        for frame in range(0, 360, 2):
            tx, ty, tb, tz = dp.eval_targets(name, pts, scene, frame / 30.0)
            assert len(tx) == 640 and all(map(math.isfinite, tx + ty + tb + tz)), (name, frame)
            top = max(top, max(tb))
            if frame / 30.0 > 2.2:
                lit = [(x, y) for x, y, b in zip(tx, ty, tb) if b > 0.05]
                box = [min(box[0], *(x for x, _ in lit)), max(box[1], *(x for x, _ in lit)),
                       min(box[2], *(y for _, y in lit)), max(box[3], *(y for _, y in lit))]
        print(f"{name:11s} {w2.SKETCHES[name].label:9s} x {box[0]:6.1f} .. {box[1]:5.1f}   "
              f"y {box[2]:6.1f} .. {box[3]:5.1f}   brightest grain {top:4.2f}")
        if not (-72 < box[0] and box[1] < 72 and -66 < box[2] and box[3] < 64) or top > CAP:
            trouble.append(name)
    assert not trouble, f"outside the form box or past the bright cap: {trouble}"
    print("ok")
