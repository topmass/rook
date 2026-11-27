"""Side-by-side clips of the round-two tool icon concepts in desktop/icons_tools2.py, in the overlay's real GL engine,
offscreen, at the owner's monitor scale of 1.0.

Four panels in a row: "Today" (the form the tool shows now), then the icon's candidates A, B and C. Each panel rests
on the loop, morphs in, holds about six seconds, and morphs back to rest. A surfaceless EGL context draws the dust
(see docs/banner/capture.py), so no window opens. The candidates show only in this process: it points a made-up
activity at each one, and leaves the live ACTIVITY_FORMS as it is.

From the repo root, under scripts/capped with scratch XDG folders and no display (see AGENTS.md):
  /usr/bin/python docs/icons/compare_tools2.py ICON OUT_DIR FRAMES_DIR          OUT_DIR/ICON.webp, ICON.mp4, ICON.png
  /usr/bin/python docs/icons/compare_tools2.py ICON OUT_DIR FRAMES_DIR 4 6.5    only those moments, as OUT_DIR/t4.00.png
  /usr/bin/python docs/icons/compare_tools2.py overview OUT_ROOT FRAMES_DIR     OUT_ROOT/overview-tools.png and .webp,
                                                                                 from OUT_ROOT/<icon>/<icon>.mp4
ICON is prompt, globe, message, overlook or book. FRAMES_DIR holds the PNG frames; delete it afterwards.
"""
import ctypes
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "banner"))
import capture  # noqa: E402  The banner's EGL context, and overlay with desktop on the path.
import cairo  # noqa: E402

ov = capture.ov
tools2 = ov.devs_pack.icons_tools2
TOOLS = {"prompt": "Bash", "globe": "WebSearch", "message": "t3_thread_read", "overlook": "t3_thread_list",
         "book": "recall"}
PANEL, CAPTION, SCALE = 200, 32, 1.0  # A panel's pixels, the caption strip under it, and the monitor's scale.
FPS, PREROLL, BLEND = 30, 2.5, 15
# Rest, think on the tool (its form morphs in), hold about six seconds, then morph back to rest.
SCRIPT = [(0.0, {"state": "ready"}), (1.2, "tool"), (8.2, {"state": "ready"})]
LENGTH = 10.6
STILL = 4.6  # The still: mid-hold, with every concept showing its content.


def caption(cr, x, label, lead):
    cr.select_font_face("Noto Serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(14)
    ext = cr.text_extents(label)
    cr.move_to(x + (PANEL - ext.x_advance) / 2, PANEL + 20)
    cr.set_source_rgb(1.0, 0.91, 0.64) if lead else cr.set_source_rgb(0.62, 0.58, 0.52)
    cr.show_text(label)


def clip(icon, out, frames_dir, at, forms=None):
    """forms: (label, form) pairs to show in place of Today and the three candidates (compare_tools3.py)."""
    panels = [] if forms else [("Today", TOOLS[icon])]
    for label, form in forms or [(f"{v.upper()}: {tools2.NAMES[f'{icon}2_{v}']}", f"{icon}2_{v}") for v in "abc"]:
        ov.ACTIVITY_FORMS[f"concept:{form}"] = form  # This process only: the live mapping is unchanged.
        panels.append((label, f"concept:{form}"))
    ctx = capture.egl_context()
    ctx.make_current()
    read = ctypes.CDLL("libOpenGL.so.0").glReadPixels
    W, H = PANEL * len(panels), PANEL + CAPTION
    lanes = []
    for label, tool in panels:
        gl, pixels = ov._DustGL(None, ctx), bytearray(PANEL * PANEL * 4)

        def build(tex, sync, w, h, gl=gl, pixels=pixels):
            gl.gl.BindFramebuffer(0x8D40, gl.out_fbo)
            read(0, 0, w, h, 0x80E1, 0x1401, (ctypes.c_char * len(pixels)).from_buffer(pixels))  # BGRA, as Cairo keeps it
            gl.free.append((tex, sync, (w, h)))
        gl._build = build
        sc = ov.Scene(0.0)
        sc.lift, sc.rest_pad, sc.monitor_width = 0, ov.ORB / 2, PANEL / SCALE
        sc.spring_back = (lambda sc=sc, gl=gl: gl.read_springs(sc))
        script = [(t + PREROLL, {"state": "thinking", "activity": tool} if m == "tool" else m) for t, m in SCRIPT]
        lanes.append((label, sc, gl, pixels, script))
    cx = cy = PANEL / SCALE / 2
    tick, frames = 1 / (2 * FPS), round(LENGTH * FPS) + (0 if at else BLEND)
    wanted = {round(a * FPS) for a in at} if at else set(range(frames))
    heads, cpu0 = [], os.times()
    for step in range(round(PREROLL * 2 * FPS) + 2 * frames):
        t = step * tick
        frame = round((t - PREROLL) * FPS)
        draw = t >= PREROLL and not step % 2 and frame < frames
        image = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H) if draw and frame in wanted else None
        for k, (label, sc, gl, pixels, script) in enumerate(lanes):
            while script and script[0][0] <= t:
                sc.handle(script.pop(0)[1], t)
            sc.spring_gl = True
            if sc.springs_on_gpu:
                gl.follow(sc)
            sc.step(t)
            if not draw:
                continue
            gl.draw_main(sc, PANEL / SCALE, PANEL / SCALE, (cx, cy), SCALE, sc.main_scrim(SCALE, cx, cy))
            if image is None:
                continue
            dust = cairo.ImageSurface.create_for_data(pixels, cairo.FORMAT_ARGB32, PANEL, PANEL, PANEL * 4)
            cr = cairo.Context(image)
            cr.set_source_surface(dust, k * PANEL, 0)
            cr.paint()
            caption(cr, k * PANEL, label, k > 0)
        if image is None:
            continue
        if at:
            image.write_to_png(os.path.join(out, f"t{frame / FPS:.2f}.png"))
        elif frame < BLEND:
            heads.append(image)
        else:
            if frame >= frames - BLEND:  # The closing frames fade into the first ones, all at rest: a seamless loop.
                k = frame - (frames - BLEND)
                cr = cairo.Context(image)
                cr.set_source_surface(heads[k], 0, 0)
                cr.paint_with_alpha((k + 1) / BLEND)
            image.write_to_png(os.path.join(frames_dir, f"f{frame - BLEND:04d}.png"))
    cpu = os.times()
    ctx.clear_current()
    print(f"{icon}: {cpu.user - cpu0.user + cpu.system - cpu0.system:.1f} s CPU")
    if at:
        return
    src = ["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(frames_dir, "f%04d.png")]
    subprocess.run(src + ["-c:v", "libwebp_anim", "-lossless", "0", "-quality", "85", "-compression_level", "4",
                          "-loop", "0", os.path.join(out, f"{icon}.webp")], check=True)
    subprocess.run(src + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "14", "-preset", "medium",
                          "-movflags", "+faststart", os.path.join(out, f"{icon}.mp4")], check=True)
    still = round(STILL * FPS) - BLEND
    subprocess.run(["cp", os.path.join(frames_dir, f"f{still:04d}.png"), os.path.join(out, f"{icon}.png")], check=True)


def overview(root, frames_dir):
    """Every icon's three candidates in a grid, one icon a row with its name on the left, from the icons' clips."""
    icons, side, H = tuple(TOOLS), 96, PANEL + CAPTION
    labels = cairo.ImageSurface(cairo.FORMAT_RGB24, side, H * len(icons))
    cr = cairo.Context(labels)
    cr.select_font_face("Noto Serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(16)
    cr.set_source_rgb(0.86, 0.80, 0.68)
    for k, icon in enumerate(icons):
        cr.move_to(14, k * H + PANEL / 2 + 6)
        cr.show_text(icon)
    path = os.path.join(frames_dir, "labels.png")
    labels.write_to_png(path)
    args = ["ffmpeg", "-loglevel", "error", "-y"]
    for icon in icons:
        args += ["-i", os.path.join(root, icon, f"{icon}.mp4")]
    args += ["-loop", "1", "-i", path]
    crops = "".join(f"[{k}]crop={3 * PANEL}:{H}:{PANEL}:0[r{k}];" for k in range(len(icons)))
    graph = (crops + "".join(f"[r{k}]" for k in range(len(icons))) + f"vstack={len(icons)}[grid];"
             f"[{len(icons)}][grid]hstack=2:shortest=1[out]")
    webp = os.path.join(root, "overview-tools.webp")
    subprocess.run(args + ["-filter_complex", graph, "-map", "[out]", "-c:v", "libwebp_anim", "-lossless", "0",
                           "-quality", "85", "-compression_level", "4", "-loop", "0", webp], check=True)
    subprocess.run(args + ["-filter_complex", graph, "-map", "[out]", "-ss", str(STILL), "-frames:v", "1",
                           os.path.join(root, "overview-tools.png")], check=True)


def main():
    ov._use_theme("dark")
    ov._paint_reveal_rows = lambda *_: None
    icon, out, frames_dir = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    if icon == "overview":
        overview(out, frames_dir)
    else:
        clip(icon, out, frames_dir, [float(a) for a in sys.argv[4:]])


if __name__ == "__main__":
    main()
