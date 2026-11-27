"""Side-by-side clips of the round-three tool icon concepts in desktop/icons_tools3.py, next to the round-two forms
they replace. It uses compare_tools2.py's offscreen GL engine at the monitor scale of 1.0, and opens no window.

From the repo root, under scripts/capped with scratch XDG folders and no display (see AGENTS.md):
  /usr/bin/python docs/icons/compare_tools3.py ICON OUT_DIR FRAMES_DIR          OUT_DIR/ICON.webp, ICON.mp4, ICON.png
  /usr/bin/python docs/icons/compare_tools3.py ICON OUT_DIR FRAMES_DIR 4 6.5    only those moments, as OUT_DIR/t4.00.png
  /usr/bin/python docs/icons/compare_tools3.py overview OUT_ROOT FRAMES_DIR     OUT_ROOT/overview-tools-v3.png and .webp
ICON is prompt, globe, message or overlook. FRAMES_DIR holds the PNG frames; delete it afterwards.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_tools2 as c2  # noqa: E402

N2, N3 = c2.tools2.NAMES, c2.ov.devs_pack.icons_tools3.NAMES
SETS = {"prompt": ["prompt2_b", "prompt3_b"], "globe": ["globe3_a", "globe3_b", "globe3_c"],
        "message": ["message2_a", "message3_a"], "overlook": ["overlook2_b", "overlook3_a", "overlook3_b", "overlook3_c"]}
WIDE = max(map(len, SETS.values()))


def label(form):
    rnd, v = form[-3], form[-1].upper()
    return f"{'v2' if rnd == '2' else 'v3'} {v}: {(N2 if rnd == '2' else N3)[form]}"


def overview(root, frames_dir):
    """Every icon's clip in a grid, one icon a row with its name on the left, each row padded to the widest."""
    icons, side, H = tuple(SETS), 96, c2.PANEL + c2.CAPTION
    labels = c2.cairo.ImageSurface(c2.cairo.FORMAT_RGB24, side, H * len(icons))
    cr = c2.cairo.Context(labels)
    cr.select_font_face("Noto Serif", c2.cairo.FONT_SLANT_NORMAL, c2.cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(16)
    cr.set_source_rgb(0.86, 0.80, 0.68)
    for k, icon in enumerate(icons):
        cr.move_to(14, k * H + c2.PANEL / 2 + 6)
        cr.show_text(icon)
    path = os.path.join(frames_dir, "labels.png")
    labels.write_to_png(path)
    args = ["ffmpeg", "-loglevel", "error", "-y"]
    for icon in icons:
        args += ["-i", os.path.join(root, icon, f"{icon}.mp4")]
    args += ["-loop", "1", "-i", path]
    pads = "".join(f"[{k}]pad={WIDE * c2.PANEL}:{H}:0:0[r{k}];" for k in range(len(icons)))
    graph = (pads + "".join(f"[r{k}]" for k in range(len(icons))) + f"vstack={len(icons)}[grid];"
             f"[{len(icons)}][grid]hstack=2:shortest=1[out]")
    subprocess.run(args + ["-filter_complex", graph, "-map", "[out]", "-c:v", "libwebp_anim", "-lossless", "0",
                           "-quality", "85", "-compression_level", "4", "-loop", "0",
                           os.path.join(root, "overview-tools-v3.webp")], check=True)
    subprocess.run(args + ["-filter_complex", graph, "-map", "[out]", "-ss", str(c2.STILL), "-frames:v", "1",
                           os.path.join(root, "overview-tools-v3.png")], check=True)


def main():
    c2.ov._use_theme("dark")
    c2.ov._paint_reveal_rows = lambda *_: None
    icon, out, frames_dir = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    if icon == "overview":
        overview(out, frames_dir)
    else:
        c2.clip(icon, out, frames_dir, [float(a) for a in sys.argv[4:]], [(label(f), f) for f in SETS[icon]])


if __name__ == "__main__":
    main()
