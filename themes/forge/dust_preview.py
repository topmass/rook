#!/usr/bin/env python3
"""A forged dust form at its real size, offscreen: the rest loop, the form assembling and swaying, back to rest.

    dust_preview.py <pack> <icon> <out_dir>    writes <out_dir>/<icon>.png (a still) and <out_dir>/<icon>.webm (a loop)

The overlay's own engine draws the dust in a surfaceless EGL context, as docs/banner/capture.py does, so no window
opens. It uses the graphics chip for a few seconds, and refuses to start while another preview runs. Run it as forge.py
bake does, under the shared lock and scripts/capped.
"""
import ctypes
import fcntl
import math
import os
import subprocess
import sys
import time
import types

for var in ("WAYLAND_DISPLAY", "DISPLAY"):  # GTK needs no display here: the dust is drawn with EGL alone.
    os.environ.pop(var, None)
os.environ["GDK_BACKEND"] = "x11"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "desktop"))
import cairo  # noqa: E402
import overlay as ov  # noqa: E402

SIZE, FPS = 200, 30  # The square clip in logical pixels at scale 1, so the form shows at its real size.
HOLD = 4.0  # Seconds the settled form sways in the clip. The clip is always one 10.5 s rest-loop period.
LOCK = "/tmp/rook-dust-preview.lock"


def egl_context():
    """A GL 4.4 core context with no surface (see overlay._check_send_window_gl)."""
    egl = ctypes.CDLL("libEGL.so.1")
    egl.eglGetPlatformDisplay.restype = egl.eglCreateContext.restype = ctypes.c_void_p
    egl.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglChooseConfig.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    egl.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglMakeCurrent.argtypes = [ctypes.c_void_p] * 4
    dpy = egl.eglGetPlatformDisplay(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
    cfg, n = ctypes.c_void_p(), ctypes.c_int()
    if not (dpy and egl.eglInitialize(dpy, None, None) and egl.eglBindAPI(0x30A2) and egl.eglChooseConfig(
            dpy, (ctypes.c_int * 5)(0x3040, 8, 0x3033, 0, 0x3038), ctypes.byref(cfg), 1, ctypes.byref(n)) and n.value):
        raise SystemExit("This machine has no surfaceless EGL, so the dust preview cannot run.")
    context = egl.eglCreateContext(dpy, cfg, None, (ctypes.c_int * 7)(0x3098, 4, 0x30FB, 4, 0x30FD, 1, 0x3038))
    if not context:
        raise SystemExit("This machine has no GL 4.4 context, so the dust preview cannot run.")
    return types.SimpleNamespace(make_current=lambda: egl.eglMakeCurrent(dpy, None, None, context),
                                 clear_current=lambda: egl.eglMakeCurrent(dpy, None, None, None))


def main():
    pack, icon, out = sys.argv[1:4]
    began = time.perf_counter()
    lock = open(LOCK, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another dust preview is running. Try again when it ends.")
    ov._use_theme("dark")
    ctx = egl_context()
    ctx.make_current()
    gl = ov._DustGL(None, ctx)
    gl.readback = frame = bytearray(SIZE * SIZE * 4)
    sc = ov.Scene(0.0)
    sc.lift, sc.rest_pad = 0, ov.ORB / 2  # The rest loop sits at the centre too, as in the banner.
    sc.spring_back = lambda: gl.read_springs(sc)
    sc.reveal_gl_rows = lambda now: []  # The preview draws no lettering, so none of the label's reveal grains either.
    key = f"pack:{pack}/{icon}"
    if not sc.set_pack(pack, 0.0) or key not in sc.think_forms:
        raise SystemExit(f"{icon} is not a dust form Rook can show from {pack}.")
    # In the overlay the form takes its turn in the thinking rotation. Here it holds for HOLD seconds, whatever its spin.
    ov.ACTIVITY_FORMS["forge_preview"] = key
    pre, think = 3.0, 1.0  # Seconds of rest to settle before the first frame, and of rest in the clip.
    ready = think + 1.5 + HOLD
    length = math.ceil((ready + 2.5) / ov.LOOP_PERIOD) * ov.LOOP_PERIOD  # Whole rest-loop periods, so it closes.
    script = [(pre + think, {"state": "thinking", "activity": "forge_preview"}), (pre + ready, {"state": "ready"})]
    still_at = round((think + 1.5 + 0.25 * (ready - think - 1.5)) * FPS)
    frames, first, tick = round(length * FPS), None, 1 / (2 * FPS)
    webm = os.path.join(out, f"{icon}.webm")
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s",
                            f"{SIZE}x{SIZE}", "-r", str(FPS), "-i", "-", "-c:v", "libvpx-vp9", "-lossless", "1",
                            "-pix_fmt", "yuv444p", "-threads", "2", "-an", webm], stdin=subprocess.PIPE)
    for step in range(round((pre + length) * 2 * FPS) + 1):
        t = step * tick
        while script and script[0][0] <= t:
            sc.handle(script.pop(0)[1], t)
        sc.spring_gl = True
        if sc.springs_on_gpu:
            gl.follow(sc)
        sc.step(t)
        k = round((t - pre) * FPS)
        if t < pre - 1e-9 or step % 2:
            continue
        gl.draw_main(sc, SIZE, SIZE, (SIZE / 2, SIZE / 2), 1.0, sc.main_scrim(1.0, SIZE / 2, SIZE / 2))
        if k == frames:  # One frame past the end: the same moment of the rest loop as the first frame.
            seam = [abs(a - b) for a, b in zip(frame, first)]
            print(f"{icon}: seam {sum(seam) / len(seam):.2f} of 255 on average, worst {max(seam)}")
            break
        first = first or bytes(frame)
        enc.stdin.write(frame)
        if k == still_at:
            image = cairo.ImageSurface(cairo.FORMAT_RGB24, SIZE, SIZE)  # Over black: the frame is premultiplied.
            image.get_data()[:] = frame
            image.mark_dirty()
            image.write_to_png(os.path.join(out, f"{icon}.png"))
    ctx.clear_current()
    enc.stdin.close()
    if enc.wait():
        raise SystemExit("ffmpeg could not write the loop.")
    print(f"{icon}: still {os.path.join(out, icon + '.png')}")
    print(f"{icon}: loop {webm} ({frames} frames, {length:g} s), made in {time.perf_counter() - began:.1f} s")


if __name__ == "__main__":
    main()
