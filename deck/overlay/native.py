"""Rook's overlay drawn natively: a 32-bit X11 window tagged GAMESCOPE_EXTERNAL_OVERLAY, painted with cairo through
ctypes. It needs only libX11, libXext and libcairo, which every SteamOS has, so it is the fallback when no Qt WebEngine
can host overlay/page. It reads the same /overlay/events stream as the page and draws the same picture, simpler:
gold dust in the top-right corner (after phone/presence.js's 2D fallback, a light spring model with one form per
mood) and the answer on a dark card beneath it. While nothing shows, the window is unmapped and the loop sleeps.
"""

import ctypes
import ctypes.util
import json
import math
import os
import queue
import random
import select
import threading
import time
import urllib.request
from ctypes import POINTER, Structure, byref, c_char_p, c_double, c_int, c_void_p

import xlib

cairo = None
for _name in ("libcairo.so.2", ctypes.util.find_library("cairo")):
    if _name:
        try:
            cairo = ctypes.CDLL(_name)
            break
        except OSError:
            pass


class TextExtents(Structure):
    _fields_ = [("x_bearing", c_double), ("y_bearing", c_double), ("width", c_double), ("height", c_double),
                ("x_advance", c_double), ("y_advance", c_double)]


class FontExtents(Structure):
    _fields_ = [("ascent", c_double), ("descent", c_double), ("height", c_double), ("max_x_advance", c_double),
                ("max_y_advance", c_double)]


def _c(name, restype, *args):
    fn = getattr(cairo, name)
    fn.restype = restype
    fn.argtypes = list(args)
    return fn


OP_SOURCE, OP_OVER = 1, 2
WEIGHT_NORMAL, WEIGHT_BOLD = 0, 1
if cairo is not None:
    xlib_surface = _c("cairo_xlib_surface_create", c_void_p, c_void_p, ctypes.c_ulong, c_void_p, c_int, c_int)
    surface_flush = _c("cairo_surface_flush", None, c_void_p)
    surface_destroy = _c("cairo_surface_destroy", None, c_void_p)
    create = _c("cairo_create", c_void_p, c_void_p)
    destroy = _c("cairo_destroy", None, c_void_p)
    save = _c("cairo_save", None, c_void_p)
    restore = _c("cairo_restore", None, c_void_p)
    push_group = _c("cairo_push_group", None, c_void_p)
    pop_group_to_source = _c("cairo_pop_group_to_source", None, c_void_p)
    set_operator = _c("cairo_set_operator", None, c_void_p, c_int)
    paint = _c("cairo_paint", None, c_void_p)
    paint_with_alpha = _c("cairo_paint_with_alpha", None, c_void_p, c_double)
    set_rgba = _c("cairo_set_source_rgba", None, c_void_p, c_double, c_double, c_double, c_double)
    set_source = _c("cairo_set_source", None, c_void_p, c_void_p)
    rectangle = _c("cairo_rectangle", None, c_void_p, c_double, c_double, c_double, c_double)
    arc = _c("cairo_arc", None, c_void_p, c_double, c_double, c_double, c_double, c_double)
    new_path = _c("cairo_new_path", None, c_void_p)
    new_sub_path = _c("cairo_new_sub_path", None, c_void_p)
    close_path = _c("cairo_close_path", None, c_void_p)
    fill = _c("cairo_fill", None, c_void_p)
    fill_preserve = _c("cairo_fill_preserve", None, c_void_p)
    stroke = _c("cairo_stroke", None, c_void_p)
    set_line_width = _c("cairo_set_line_width", None, c_void_p, c_double)
    set_dash = _c("cairo_set_dash", None, c_void_p, POINTER(c_double), c_int, c_double)
    move_to = _c("cairo_move_to", None, c_void_p, c_double, c_double)
    select_font = _c("cairo_select_font_face", None, c_void_p, c_char_p, c_int, c_int)
    set_font_size = _c("cairo_set_font_size", None, c_void_p, c_double)
    text_extents = _c("cairo_text_extents", None, c_void_p, c_char_p, POINTER(TextExtents))
    font_extents = _c("cairo_font_extents", None, c_void_p, POINTER(FontExtents))
    show_text = _c("cairo_show_text", None, c_void_p, c_char_p)
    radial = _c("cairo_pattern_create_radial", c_void_p, c_double, c_double, c_double, c_double, c_double, c_double)
    add_stop = _c("cairo_pattern_add_color_stop_rgba", None, c_void_p, c_double, c_double, c_double, c_double,
                  c_double)
    pattern_destroy = _c("cairo_pattern_destroy", None, c_void_p)


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


TONES = [rgb("#f2b347"), rgb("#f8cf7d"), rgb("#fde9b2")]
EMBER = rgb("#c0563a")
IVORY = rgb("#fbf3dd")
AMBER = rgb("#f2b347")
GOLD = rgb("#f6cd7c")
PALE = rgb("#fde9b2")
BG = rgb("#0b0c0f")
FONT = b"Noto Serif"
LABELS = {"listening": "LISTENING", "transcribing": "TRANSCRIBING", "thinking": "THINKING",
          "waiting": "WAITING", "error": "TROUBLE"}
STATES = {"resting", "listening", "transcribing", "thinking", "speaking", "waiting", "error"}


# ---------------------------------------------------------------------------------------------------------- the dust

class Dust:
    """Gold grains on springs, one form per mood: the loop at rest, the halo listening, the lattice thinking, the
    globe speaking, an open ring waiting. Coordinates are in units, the form about -1..1 across."""

    N = 170

    def __init__(self):
        rnd = random.Random(7919)
        self.g = [dict(omega=3.2 + rnd.random() * 2.6, delay=rnd.random() * 0.35, phase=rnd.random() * 6.283,
                       freq=0.6 + rnd.random() * 1.4, size=1.4 + rnd.random() * 1.8, tone=i % 3,
                       base=0.45 + rnd.random() * 0.55) for i in range(self.N)]
        self.mood = "resting"
        self.clock = 0.0
        self.form_at = -10.0
        self.p = [list(self.target(i, 0.0)[:2]) + [0.0, 0.0, 1.0] for i in range(self.N)]  # x, y, vx, vy, b

    def set(self, mood):
        if mood != self.mood:
            self.mood = mood
            self.form_at = self.clock

    def target(self, i, t):
        sin, cos, pi = math.sin, math.cos, math.pi
        g = self.g[i]
        u = i / self.N
        a = u * 2 * pi
        m = self.mood
        if m == "listening":
            r = 0.42 + 0.02 * sin(t * 1.1) + 0.05 * sin(a * 9 + t * 3.0) * sin(t * 2.3 + g["phase"])
            th = a + t * 0.2
            return r * cos(th), r * sin(th), 1.0
        if m == "transcribing":
            row = i % 3
            k = (i // 3) / (self.N / 3)
            ln = (0.9, 0.75, 0.5)[row]
            return -0.9 + ((k * 2 + t * 0.25) % 2) * ln, -0.28 + row * 0.28, 0.6 + 0.4 * sin(t * 4 + k * 9)
        if m == "thinking":
            spoke = i % 4 == 0
            side = int(u * 6)
            f = (u * 6) % 1
            p0 = side * pi / 3 + pi / 6
            p1 = (side + 1) * pi / 3 + pi / 6
            x = f * cos(p0) if spoke else cos(p0) + (cos(p1) - cos(p0)) * f
            y = f * sin(p0) if spoke else sin(p0) + (sin(p1) - sin(p0)) * f
            x, y = x * 0.46, y * 0.46
            yaw = t * 0.9
            z = x * sin(yaw)
            return x * cos(yaw), y, 0.65 + 0.45 * (z / 0.46 + 1) / 2
        if m == "speaking":
            yy = 1 - 2 * ((i + 0.5) / self.N)
            rr = math.sqrt(max(0.0, 1 - yy * yy))
            ph = i * 2.399963 + t * 0.8
            swell = 1 + 0.06 * sin(t * 6 - yy * 4)
            return rr * cos(ph) * 0.42 * swell, yy * 0.42 * swell, 0.45 + 0.55 * (rr * sin(ph) + 1) / 2
        if m == "waiting":
            th = -pi / 2 + u * pi * 1.6 + t * 0.6
            return 0.4 * cos(th), 0.4 * sin(th), 1.2 if u < 0.2 else 0.8
        if m == "error":
            x = (u * 2 - 1) * 0.8
            return x, 0.35 + 0.06 * sin(x * 7 + t), 0.5
        f = a + t * 2 * pi / 10.5
        sa, ca = sin(f), cos(f)
        return 0.78 * sa, 0.62 * sa * ca, 0.55 + 0.22 * (ca + 1)

    def step(self, dt):
        self.clock += dt
        t = self.clock
        since = t - self.form_at
        jitter = 1.2 if since < 0.6 else 0.06
        steps = max(1, int(math.ceil(dt / 0.034)))
        h = dt / steps
        for i, g in enumerate(self.g):
            if since < g["delay"]:
                continue
            tx, ty, tb = self.target(i, t)
            p = self.p[i]
            w = g["omega"]
            k = w * w
            jx = jitter * math.sin(t * g["freq"] * 6 + g["phase"])
            jy = jitter * math.cos(t * g["freq"] * 7 + g["phase"])
            for _ in range(steps):
                p[2] += (k * (tx - p[0]) - 1.4 * w * p[2] + jx) * h
                p[3] += (k * (ty - p[1]) - 1.4 * w * p[3] + jy) * h
                p[0] += p[2] * h
                p[1] += p[3] * h
            p[4] = tb


# ------------------------------------------------------------------------------------------------------- the events

class Events(threading.Thread):
    """Reads the backend's SSE stream; each message's JSON goes on the queue and wakes the draw loop."""

    def __init__(self, url, wake_fd):
        super().__init__(daemon=True)
        self.url = url
        self.wake_fd = wake_fd
        self.q = queue.Queue()
        self.connected = False
        self.down_since = time.monotonic()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _put(self, item):
        self.q.put(item)
        try:
            os.write(self.wake_fd, b"x")
        except OSError:
            pass

    def run(self):
        while True:
            try:
                req = urllib.request.Request(self.url, headers={"Accept": "text/event-stream"})
                with self.opener.open(req, timeout=60) as res:
                    self.connected = True
                    self.down_since = None
                    data = []
                    for raw in res:
                        line = raw.decode("utf-8", "replace").rstrip("\r\n")
                        if not line:
                            if data:
                                try:
                                    self._put(json.loads("\n".join(data)))
                                except ValueError:
                                    pass
                            data = []
                        elif line.startswith("data:"):
                            data.append(line[5:].lstrip(" ") if line[5:6] == " " else line[5:])
            except Exception:
                pass
            if self.connected or self.down_since is None:
                self.down_since = time.monotonic()
            self.connected = False
            time.sleep(2)


# ---------------------------------------------------------------------------------------------------------- drawing

class Renderer:
    MARGIN = 14
    PRESENCE = 108

    def __init__(self, display, geometry, events_url, parent_pid=None, tag=True, anchor="top-right"):
        if cairo is None:
            raise xlib.XError("libcairo not found")
        self.d = display
        self.x, self.y, self.w, self.h = geometry
        self.anchor = anchor
        m, P = self.MARGIN, self.PRESENCE
        # The presence keeps to the screen edge it is anchored to; the card goes under it (beside it, at the bottom).
        if anchor == "bottom-center":
            self.cx, self.cy = m + P / 2, self.h / 2 - 8
            self.card = (m + P + 10, m, self.w - (m + P + 10) - m, self.h - 2 * m)
        else:
            self.cx = m + P / 2 if anchor.endswith("left") else self.w - m - P / 2
            self.cy = m + P / 2
            self.card = (m, m + P + 20, self.w - 2 * m, self.h - (m + P + 20) - m)
        self.win, visual = self.d.create_argb_window(self.x, self.y, self.w, self.h, tag=tag)
        self.surface = xlib_surface(self.d.dpy, self.win, visual, self.w, self.h)
        self.cr = create(self.surface)
        self.mapped = False
        self.dust = Dust()
        self.state = {"state": "resting", "text": "", "draft": None}
        self.rested_at = time.monotonic() - 60
        self.alpha = 0.0
        self.parent_pid = parent_pid
        self.running = True
        self.wake_r, self.wake_w = os.pipe()
        os.set_blocking(self.wake_r, False)
        self.events = Events(events_url, self.wake_w)

    # -- state, as overlay/page/overlay.js has it

    def apply(self, data):
        if not isinstance(data, dict):
            return
        s = data.get("state")
        state = s if s in STATES else "resting" if s == "ready" else self.state["state"]
        text = data["text"] if isinstance(data.get("text"), str) else self.state["text"]
        if state == "resting" and (self.state["state"] != "resting" or text != self.state["text"]):
            self.rested_at = time.monotonic()
        self.state["state"] = state
        self.state["text"] = text
        if "draft" in data:
            self.state["draft"] = data["draft"] if isinstance(data["draft"], str) and data["draft"].strip() else None
        self.dust.set(state)

    def wanted(self):
        st = self.state
        if st["state"] != "resting" or st["draft"]:
            return True
        hold = max(6.0, min(20.0, 3.0 + len(st["text"]) * 0.065)) if st["text"] else 1.5
        return time.monotonic() - self.rested_at < hold

    # -- text

    def font(self, size, bold=False):
        select_font(self.cr, FONT, 0, WEIGHT_BOLD if bold else WEIGHT_NORMAL)
        set_font_size(self.cr, size)

    def width_of(self, s):
        e = TextExtents()
        text_extents(self.cr, s.encode(), byref(e))
        return e.x_advance

    def wrap(self, text, width):
        lines = []
        for para in [p.strip() for p in text.replace("\r", "").split("\n\n")]:
            if not para:
                continue
            if lines:
                lines.append("")
            line = ""
            for word in para.replace("\n", " ").split():
                trial = f"{line} {word}" if line else word
                if self.width_of(trial) <= width or not line:
                    line = trial
                else:
                    lines.append(line)
                    line = word
            if line:
                lines.append(line)
        return lines

    def rounded(self, x, y, w, h, r):
        cr = self.cr
        new_path(cr)
        new_sub_path(cr)
        arc(cr, x + w - r, y + r, r, -math.pi / 2, 0)
        arc(cr, x + w - r, y + h - r, r, 0, math.pi / 2)
        arc(cr, x + r, y + h - r, r, math.pi / 2, math.pi)
        arc(cr, x + r, y + r, r, math.pi, 3 * math.pi / 2)
        close_path(cr)

    def text(self, s, x, y, colour, alpha=1.0, shadow=True):
        cr = self.cr
        b = s.encode()
        if shadow:
            set_rgba(cr, 0, 0, 0, 0.85 * alpha)
            move_to(cr, x, y + 1.2)
            show_text(cr, b)
        set_rgba(cr, *colour, alpha)
        move_to(cr, x, y)
        show_text(cr, b)

    # -- one frame

    def draw(self):
        cr = self.cr
        st = self.state
        push_group(cr)
        set_operator(cr, OP_SOURCE)
        set_rgba(cr, 0, 0, 0, 0)
        paint(cr)
        set_operator(cr, OP_OVER)
        m, P = self.MARGIN, self.PRESENCE
        cx, cy = self.cx, self.cy

        # The dark well under the dust, then the grains, added in light.
        pat = radial(cx, cy, 0, cx, cy, P / 2)
        add_stop(pat, 0, *BG, 0.55)
        add_stop(pat, 0.62, *BG, 0.28)
        add_stop(pat, 1, *BG, 0)
        set_source(cr, pat)
        arc(cr, cx, cy, P / 2, 0, 2 * math.pi)
        fill(cr)
        pattern_destroy(pat)
        unit = P * 0.5  # OVER, not ADD: added grains saturate to white, and Rook's dust is gold.
        err = st["state"] == "error"
        for g, p in zip(self.dust.g, self.dust.p):
            a = max(0.0, min(1.0, g["base"] * p[4] * 1.25))
            if a <= 0.02:
                continue
            s = g["size"] * (0.8 + 0.3 * p[4])
            set_rgba(cr, *(EMBER if err else TONES[g["tone"]]), a)
            rectangle(cr, cx + p[0] * unit - s / 2, cy + p[1] * unit - s / 2, s, s)
            fill(cr)
        set_operator(cr, OP_OVER)

        label = LABELS.get(st["state"], "")
        if label:
            self.font(11, True)
            spaced = " ".join(label)
            self.text(spaced, cx - self.width_of(spaced) / 2, cy + P / 2 + 8, GOLD)

        # The answer and the draft on a dark card under the presence.
        text, draft = st["text"], st["draft"]
        if text or draft:
            pad = 14
            x0, y0, cw, avail = self.card
            inner = cw - 2 * pad
            self.font(17)
            fe = FontExtents()
            font_extents(cr, byref(fe))
            lh = 17 * 1.42
            dlines = []
            if draft:
                self.font(16)
                dlines = self.wrap(draft, inner - 20)[:4]  # The draft comes whole first: it waits on a yes.
            dh = (16 + 6 + len(dlines) * 16 * 1.4 + 16) if draft else 0
            self.font(17)
            lines = self.wrap(text, inner) if text else []
            max_lines = max(0, int((avail - 2 * pad + 4 - dh - (8 if draft else 0)) // lh))
            clipped = len(lines) > max_lines
            lines = lines[-max_lines:]
            th = len(lines) * lh
            ch = pad + th + (8 if lines and draft else 0) + dh + pad - 4
            self.rounded(x0, y0, cw, ch, 12)
            set_rgba(cr, *BG, 0.8)
            fill_preserve(cr)
            set_rgba(cr, *AMBER, 0.34)
            set_line_width(cr, 1)
            stroke(cr)
            y = y0 + pad + fe.ascent * 0.95
            self.font(17)
            for k, line in enumerate(lines):
                fade = 0.35 + 0.65 * min(1, k / 1.5) if clipped else 1.0
                if line:
                    self.text(line, x0 + pad, y, IVORY, fade)
                y += lh
            if draft:
                bx, by = x0 + pad - 4, y - fe.ascent + (8 if lines else 0)
                bw, bh = inner + 8, dh
                self.rounded(bx, by, bw, bh, 8)
                set_rgba(cr, *AMBER, 0.08)
                fill_preserve(cr)
                dash = (c_double * 2)(4, 3)
                set_dash(cr, dash, 2, 0)
                set_rgba(cr, *AMBER, 0.7)
                stroke(cr)
                set_dash(cr, None, 0, 0)
                self.font(11, True)
                self.text("D R A F T", bx + 10, by + 16, AMBER)
                w = self.width_of("D R A F T ")
                self.font(11)
                self.text(" · say yes to send", bx + 10 + w, by + 16, GOLD)
                self.font(16)
                yy = by + 16 + 6 + 16
                for line in dlines:
                    self.text(line, bx + 10, yy, PALE)
                    yy += 16 * 1.4

        pop_group_to_source(cr)
        set_operator(cr, OP_SOURCE)
        paint_with_alpha(cr, self.alpha)
        surface_flush(self.surface)
        self.d.flush()

    # -- the loop

    def parent_alive(self):
        if not self.parent_pid:
            return True
        try:
            os.kill(self.parent_pid, 0)
            return True
        except PermissionError:
            return True
        except ProcessLookupError:
            return False

    def stop(self, *_):
        self.running = False
        try:
            os.write(self.wake_w, b"q")
        except OSError:
            pass

    def run(self):
        self.events.start()
        last = time.monotonic()
        checked = 0.0
        while self.running:
            want = self.wanted()
            animating = self.mapped or want
            timeout = 1 / 30 if animating else 1.0
            try:
                select.select([self.wake_r, self.d.fileno()], [], [], timeout)
            except InterruptedError:
                pass
            try:
                os.read(self.wake_r, 4096)
            except (BlockingIOError, OSError):
                pass
            while True:
                try:
                    self.apply(self.events.q.get_nowait())
                except queue.Empty:
                    break
            self.d.drain()
            now = time.monotonic()
            dt = min(0.1, now - last)
            last = now
            if now - checked > 2:
                checked = now
                if not self.parent_alive():
                    break
                # A dropped stream never leaves Rook "thinking" over the game.
                down = self.events.down_since
                if down is not None and now - down > 15 and self.state["state"] != "resting":
                    self.apply({"state": "resting", "text": "", "draft": None})
            want = self.wanted()
            goal = 1.0 if want else 0.0
            rate = dt / (0.22 if want else 0.7)
            self.alpha = min(goal, self.alpha + rate) if goal > self.alpha else max(goal, self.alpha - rate)
            if self.alpha > 0.001:
                if not self.mapped:
                    self.d.map(self.win)
                    self.mapped = True
                self.dust.step(dt)
                self.draw()
            elif self.mapped:
                self.draw()
                self.d.unmap(self.win)
                self.mapped = False
        self.close()

    def close(self):
        try:
            destroy(self.cr)
            surface_destroy(self.surface)
            self.d.destroy(self.win)
        except Exception:
            pass
