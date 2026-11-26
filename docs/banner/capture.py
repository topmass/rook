"""The README banner (docs/banner/banner.webp): Rook's real Devs animation, captured offscreen. It plays listening on
the helix, the thinking loop, a send to six threads, and rest again. The overlay's own GL engine draws the dust in a
surfaceless EGL context, so no window opens. Cairo draws the labels and thread names over it, as the live overlay does.

To re-run it, from the repo root, under scripts/capped with scratch XDG folders and no display (see AGENTS.md):
  /usr/bin/python docs/banner/capture.py OUT_DIR           every frame as OUT_DIR/f0000.png, then OUT_DIR/banner.webp and banner-dark.webp
  /usr/bin/python docs/banner/capture.py OUT_DIR 1.0 5.2   only the frames at those seconds, as OUT_DIR/t1.00.png
Then copy both WebP files to docs/banner/.
"""
import ctypes
import os
import subprocess
import sys
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "desktop"))
import cairo  # noqa: E402
import overlay as ov  # noqa: E402

W, H, SCALE = 1280, 400, 1.5  # The banner in pixels; the overlay draws at a HiDPI monitor's scale.
CX, CY = W / SCALE / 2, 113 / SCALE  # The presence's centre in logical pixels.
WORD_Y, LINE_Y = 278, 340  # The tops of the wordmark's and the tagline's sprites, in pixels.
FPS, PREROLL = 30, 3.0  # Output frames per second; seconds of rest before the first frame, so the loop is settled.
THREADS = ("T3 Code", "Herdr", "Claude Code", "Codex", "Antigravity", "Pi")
SEND = 3.0  # When the send starts, in banner seconds: listening ends straight into it.
# The send's own loop forms once from the helix and assembles into the send form, with no rest loop before it.
SCRIPT = [(0.0, {"state": "ready"}), (0.8, {"state": "listening"}),
          (SEND, {"state": "thinking", "activity": "t3_thread_send"}),
          (SEND + 0.05, {"send": [{"id": f"t{k}", "name": n} for k, n in enumerate(THREADS)]}),
          (SEND + 3.6, {"send": [{"id": f"t{k}", "outcome": "landed"} for k in range(len(THREADS))]}),
          (SEND + 5.4, {"state": "ready"})]
LENGTH = SEND + 7.0  # The teardown ends near SEND + 6.1, and the loop rests after it.
BLEND = 15  # The last frames fade into the first BLEND frames (all rest), so the WebP loops with no seam.
TAGLINE = "Drive your coding agents by voice, and hear them report back when they need you."


def egl_context():
    """A GL 4.4 core context with no surface, wrapped as _DustGL expects (see overlay._check_send_window_gl)."""
    egl = ctypes.CDLL("libEGL.so.1")
    egl.eglGetPlatformDisplay.restype = egl.eglCreateContext.restype = ctypes.c_void_p
    egl.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglChooseConfig.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    egl.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglMakeCurrent.argtypes = [ctypes.c_void_p] * 4
    dpy = egl.eglGetPlatformDisplay(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
    cfg, n = ctypes.c_void_p(), ctypes.c_int()
    assert dpy and egl.eglInitialize(dpy, None, None) and egl.eglBindAPI(0x30A2) and egl.eglChooseConfig(
        dpy, (ctypes.c_int * 5)(0x3040, 8, 0x3033, 0, 0x3038), ctypes.byref(cfg), 1, ctypes.byref(n)) and n.value
    context = egl.eglCreateContext(dpy, cfg, None, (ctypes.c_int * 7)(0x3098, 4, 0x30FB, 4, 0x30FD, 1, 0x3038))
    assert context, "no GL 4.4 core context"
    return types.SimpleNamespace(make_current=lambda: egl.eglMakeCurrent(dpy, None, None, context),
                                 clear_current=lambda: egl.eglMakeCurrent(dpy, None, None, None))


def lettering():
    """The wordmark and tagline in the Filament look of the previous banner, as one still layer in pixels."""
    layer = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(layer)
    word, _, _ = ov._word_sprite(cr, "ROOK", 1, ov._font("Noto Serif", 44, ov.Pango.Weight.BOLD), (1.0, 0.965, 0.878),
                                 0.42 * 44, (), ov.INK, (2.2, 0.9), rim=(1.0, 1.0, (0.91, 0.69, 0.29)))
    line, _, _ = ov._word_sprite(cr, TAGLINE, 1, ov._font("Noto Serif", 21), (0.75, 0.68, 0.565), 0.0, ())
    # Pango spaces after the last capital too, so the wordmark shifts right by half a space to sit centred.
    cr.set_source_surface(word, (W - word.get_width() + 0.42 * 44) / 2, WORD_Y)
    cr.paint()
    cr.set_source_surface(line, (W - line.get_width()) / 2, LINE_Y)
    cr.paint()
    return layer


def main():
    out, at = sys.argv[1], [float(a) for a in sys.argv[2:]]
    os.makedirs(out, exist_ok=True)
    ov._use_theme("dark")
    ov.FORM_FOR_STATE["listening"] = "helix"  # Devs listening shows only the helix.
    ov._paint_reveal_rows = lambda *_: None  # The GL frame draws the reveal grains (Scene.dispatch_gl_rows).
    ctx = egl_context()
    ctx.make_current()
    gl, read = ov._DustGL(None, ctx), ctypes.CDLL("libOpenGL.so.0").glReadPixels
    pixels = bytearray(W * H * 4)

    def build(tex, sync, w, h):  # In place of a GDK texture: the frame's pixels, and the texture back for reuse.
        assert (w, h) == (W, H), (w, h)
        gl.gl.BindFramebuffer(0x8D40, gl.out_fbo)
        read(0, 0, w, h, 0x80E1, 0x1401, (ctypes.c_char * len(pixels)).from_buffer(pixels))  # BGRA, as Cairo keeps it
        gl.free.append((tex, sync, (w, h)))
    gl._build = build
    still = lettering()

    sc = ov.Scene(0.0)
    # Every form, the resting loop too, sits at one centre, as in a stage: lift 0, and the rest pad half the form box.
    sc.lift, sc.rest_pad, sc.monitor_width = 0, ov.ORB / 2, W / SCALE
    sc.spring_back = lambda: gl.read_springs(sc)
    script = sorted(((t + PREROLL, m) for t, m in SCRIPT), key=lambda s: s[0])
    # Two scene steps per frame, near the overlay's tick. A full run draws BLEND frames more than it writes.
    tick, frames, t = 1 / (2 * FPS), round(LENGTH * FPS) + (0 if at else BLEND), 0.0
    wanted, heads = {round(a * FPS) for a in at} if at else set(range(frames)), []
    drawn, saved, cpu0, wall0 = [], [], os.times(), time.perf_counter()
    for step in range(round(PREROLL * 2 * FPS) + 2 * frames):
        t = step * tick
        while script and script[0][0] <= t:
            sc.handle(script.pop(0)[1], t)
        if sc.state == "listening":
            sc.handle({"level": 0.6 * ov._speech(t)}, t)  # A gentle voice.
        sc.spring_gl = True
        if sc.springs_on_gpu:
            gl.follow(sc)
        sc.step(t)
        frame = round((t - PREROLL) * FPS)
        if t < PREROLL or step % 2 or frame >= frames:
            continue
        began = time.perf_counter()
        gl.draw_main(sc, W / SCALE, H / SCALE, (CX, CY), SCALE, sc.main_scrim(SCALE, CX, CY))
        drawn.append(time.perf_counter() - began)
        if frame not in wanted:
            continue
        dust = cairo.ImageSurface.create_for_data(pixels, cairo.FORMAT_ARGB32, W, H, W * 4)
        dust.set_device_scale(SCALE, SCALE)
        image = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
        image.set_device_scale(SCALE, SCALE)
        cr = cairo.Context(image)
        cr.set_source_surface(dust, 0, 0)
        cr.paint()  # Over black: the frame is premultiplied.
        sc._label(cr, CX, CY)  # The labels over the grains, as Overlay._append_labels draws them.
        sc.draw_dispatch_overlay(cr, CX, CY, t)
        cr.scale(1 / SCALE, 1 / SCALE)
        cr.set_source_surface(still, 0, 0)
        cr.paint()
        if at:
            image.write_to_png(os.path.join(out, f"t{frame / FPS:.2f}.png"))
        elif frame < BLEND:
            heads.append(image)  # Written last, faded over the closing frames.
        else:
            if frame >= frames - BLEND:
                k = frame - (frames - BLEND)
                cr.identity_matrix()  # Back to logical pixels, as heads[k] keeps them.
                cr.set_source_surface(heads[k], 0, 0)
                cr.paint_with_alpha((k + 1) / BLEND)
            image.write_to_png(os.path.join(out, f"f{frame - BLEND:04d}.png"))
        saved.append(time.perf_counter() - began - drawn[-1])
    cpu = os.times()
    ctx.clear_current()
    wall = time.perf_counter() - wall0
    print(f"{len(drawn)} frames drawn, {len(saved)} saved, in {wall:.1f} s wall and "
          f"{cpu.user - cpu0.user + cpu.system - cpu0.system:.1f} s CPU. A draw took {1000 * sum(drawn) / len(drawn):.1f} ms, "
          f"a save {1000 * sum(saved) / max(1, len(saved)):.1f} ms more, on average.")
    if not at:
        # GitHub pads the README, so the banner cannot reach the card's edges. In dark mode its ground is transparent:
        # a pixel's alpha is its brightest channel, with the faintest noise dropped, so the dust and lettering glow on
        # GitHub's own dark page with no box. In light mode it is a black card with rounded corners.
        r, peak = 16, "max(max(r(X,Y),g(X,Y)),b(X,Y))"  # The light card's corner radius in pixels.
        corner = f"max(max({r}-{{0}},{{0}}-({{1}}-{r}-1)),0)"
        card = f"clip(({r}.5-hypot({corner.format('X', 'W')},{corner.format('Y', 'H')}))*255,0,255)"
        glow = ":".join(f"{c}='255*{c}(X,Y)/max(1,{peak})'" for c in "rgb") + f":a='if(lt({peak},8),0,{peak})'"
        for name, graph, quality in (
                ("banner-dark.webp", f"[0]format=rgba,geq={glow},format=yuva420p", "70"),
                ("banner.webp", f"[0]format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{card}',format=yuva420p", "75")):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(out, "f%04d.png"),
                            "-filter_complex", graph, "-c:v", "libwebp_anim", "-lossless", "0", "-quality", quality,
                            "-compression_level", "6", "-loop", "0", os.path.join(out, name)], check=True)

if __name__ == "__main__":
    main()
