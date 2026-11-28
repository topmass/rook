"""Checks the overlay process on an X display (gamescope's nested Xwayland in a test): opens a stand-in game window,
starts rook_overlay.py, and reports what an X client sees: the overlay window, its depth, its
GAMESCOPE_EXTERNAL_OVERLAY tag, its input shape (must be empty), where it sits, and whether it maps and unmaps with
Rook's state. Exits non-zero on a failed check. Run with the system python3, DISPLAY set:

    DISPLAY=:1 python3 overlay/dev/x11_check.py --events http://127.0.0.1:47331/overlay/events [--mode native]
"""

import argparse
import ctypes
import os
import subprocess
import sys
import time
from ctypes import POINTER, byref, c_int, c_ulong, c_void_p

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import xlib  # noqa: E402


class XRectangle(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short), ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]


get_rects = xlib._sig(xlib.xext, "XShapeGetRectangles", POINTER(XRectangle), c_void_p, c_ulong, c_int,
                      POINTER(c_int), POINTER(c_int))


def input_rects(d, win):
    n, order = c_int(), c_int()
    r = get_rects(d.dpy, win, xlib.SHAPE_INPUT, byref(n), byref(order))
    out = [(r[i].x, r[i].y, r[i].width, r[i].height) for i in range(n.value)]
    if r:
        xlib.XFree(r)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--events", required=True)
    p.add_argument("--url", default="http://127.0.0.1:1/overlay", help="the page (webengine mode)")
    p.add_argument("--mode", default="native")
    p.add_argument("--seconds", type=float, default=14)
    p.add_argument("--game", action="store_true", help="open a stand-in game window first")
    p.add_argument("--no-tag", action="store_true", help="pass --no-tag (a nested gamescope's screenshot shows it)")
    a = p.parse_args()
    d = xlib.Display()
    print(f"display {d.name} {d.width}x{d.height}", flush=True)
    game = None
    if a.game:  # A plain 24-bit window, as a game's, mapped and named.
        attrs = xlib.XSetWindowAttributes()
        attrs.background_pixel = 0x3a7bd5
        game = xlib.XCreateWindow(d.dpy, d.root, 0, 0, d.width, d.height, 0, 0, 1, None, xlib.CW_BACK_PIXEL,
                                  byref(attrs))
        xlib.XStoreName(d.dpy, game, b"World of Warcraft (stand-in)")
        d.map(game)
    proc = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "..", "rook_overlay.py"), "--mode", a.mode,
                             "--url", a.url, "--events", a.events,
                             "--parent-pid", str(os.getpid())] + (["--no-tag"] if a.no_tag else []))
    failures = []
    seen_mapped = seen_unmapped_after = False
    was_mapped = False
    win = None
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < a.seconds:
            time.sleep(0.25)
            wins = [w for w in d.walk(depth=3) if d.name_of(w) == "Rook Overlay"
                    and (a.mode != "native" or d.get_cardinal(w, "_NET_WM_PID") == proc.pid)]
            if not wins:
                continue
            if win is None:
                if a.mode != "native" and not d.get_cardinal(wins[0], "GAMESCOPE_EXTERNAL_OVERLAY"):
                    continue  # Not tagged yet: the launcher checks its depth first.
                win = wins[0]
                at = d.attributes(win)
                tag = d.get_cardinal(win, "GAMESCOPE_EXTERNAL_OVERLAY")
                rects = input_rects(d, win)
                print(f"window 0x{win:x}: depth {at.depth}, at {at.x},{at.y} {at.width}x{at.height}, "
                      f"override_redirect {at.override_redirect}, GAMESCOPE_EXTERNAL_OVERLAY={tag}, "
                      f"input shape rects {rects}", flush=True)
                if at.depth != 32:
                    failures.append("not a 32-bit window")
                if tag != 1 and not a.no_tag:
                    failures.append("not tagged")
                if rects:
                    failures.append("input shape not empty")
                if at.y < 6 and at.x < 1152 and at.x + at.width > 128:
                    failures.append("window covers the top-centre strip")
                cx, cy = d.width / 2, d.height / 2
                if at.x < cx < at.x + at.width and at.y < cy < at.y + at.height:
                    failures.append("window covers the screen's centre")
            mapped = d.attributes(win).map_state == xlib.IS_VIEWABLE
            if mapped != was_mapped:
                tag = d.get_cardinal(win, "GAMESCOPE_EXTERNAL_OVERLAY")
                print(f"{time.monotonic() - t0:5.1f}s {'mapped (Rook active)' if mapped else 'unmapped (at rest)'}"
                      f", tag={tag}, input rects={input_rects(d, win)}", flush=True)
                if mapped and tag != 1 and not a.no_tag:
                    failures.append("mapped without the tag")
                seen_unmapped_after |= seen_mapped and not mapped
            was_mapped = mapped
            seen_mapped |= mapped
            if mapped:
                overlays = d.external_overlays()
                if not a.no_tag and not any(w == win for w, _, _ in overlays):
                    failures.append("mapped but not listed as an external overlay")
        if win is None:
            failures.append("no overlay window appeared")
        if not seen_mapped:
            failures.append("never mapped")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f"overlay process exited {proc.returncode}", flush=True)
        time.sleep(0.3)
        left = [w for w in d.walk(depth=2) if d.name_of(w) == "Rook Overlay"]
        if left:
            failures.append(f"windows left after stop: {left}")
        if game:
            d.destroy(game)
        d.close()
    print("FAIL: " + "; ".join(failures) if failures else "OK", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
