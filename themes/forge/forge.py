#!/usr/bin/env python3
"""The forge for Rook's own hands: make an icon or a theme in ~/.config/rook/themes, in two commands.

    forge.py new <theme> <icon> [--base nova] [--think] [--frames 24] [--fps 12] [--layers main,voice] < icon.glsl
        Creates the pack if it is new (built on a repo theme, Nova by default), writes the shader, and adds the
        manifest entry. The shader comes on standard input, so writing it costs no extra step.
    forge.py bake <theme> [icon ...] [--show]
        Bakes, checks that every loop closes (seam) and that nothing touches the cell's edge (edge), and renders a
        still and a short loop. Prints the checks and the preview paths. With --show, and only when every check
        passes, it puts the loop in Rook's viewer for the owner.
    forge.py list
        The user's packs and their icons.

Everything it writes stays in ~/.config/rook/themes/<theme>/: Rook never edits its own code. Bakes run headless,
muted and offline, through scripts/capped under the shared heavy-job lock.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

FORGE = Path(__file__).resolve().parent
ROOT = FORGE.parent.parent
sys.path.insert(0, str(FORGE))
from bake import MAX_ATLAS_SIDE, THEMES, USER_THEMES, is_builtin_or_reserved, safe_user_write_path, user_themes_dir  # noqa: E402

NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")
LOCK = "/tmp/rook-heavy.lock"
MAX_SHADER = 64 * 1024
MAX_FRAMES = 120


def name(kind, value):
    """Theme and icon names become folder and file names, so they must be plain."""
    if not NAME.fullmatch(value):
        raise SystemExit(f"A {kind} name is lower case letters, digits, - or _, starting with a letter: {value!r}")
    return value


def _user_pack_folder(theme):
    if is_builtin_or_reserved(theme):
        raise SystemExit(f"{theme} is a built-in or reserved theme. Make your own pack, such as {theme}-mine, with --base {theme}.")
    return safe_user_write_path(user_themes_dir() / theme, is_dir=True)


def new(a):
    theme, icon = name("theme", a.theme), name("icon", a.icon)
    folder = _user_pack_folder(theme)
    base = name("base", a.base)
    if not (THEMES / base / "manifest.json").exists():
        raise SystemExit(f"There is no built-in theme called {base}.")
    layers = [name("layer", x) for x in a.layers.split(",")] if a.layers else ["main"]
    if not (1 <= a.frames <= MAX_FRAMES):
        raise SystemExit(f"--frames must be between 1 and {MAX_FRAMES} (got {a.frames}).")
    if not (1 <= a.fps <= 60):
        raise SystemExit(f"--fps must be between 1 and 60 (got {a.fps}).")
    base_m = json.loads((THEMES / base / "manifest.json").read_text())
    cell = int(base_m.get("cell", 256))
    side = math.ceil(math.sqrt(a.frames * len(layers))) * cell
    if side > MAX_ATLAS_SIDE:
        raise SystemExit(f"{a.frames} frames x {len(layers)} layers at {cell}px exceeds the {MAX_ATLAS_SIDE}px atlas cap.")
    src = sys.stdin.read(MAX_SHADER + 1)
    if not src.strip() or "vec4 icon(" not in src:
        raise SystemExit("Pipe the shader in on standard input. It must define vec4 icon(vec2 p, float t, int layer).")
    if len(src) > MAX_SHADER:
        raise SystemExit("The shader is over 64 KB. Keep an icon to one small file.")
    icons_dir = folder / "icons"
    shader_path = icons_dir / f"{icon}.glsl"
    path = folder / "manifest.json"
    safe_user_write_path(icons_dir, is_dir=True)
    safe_user_write_path(shader_path)
    safe_user_write_path(path)
    icons_dir.mkdir(parents=True, exist_ok=True)
    m = json.loads(path.read_text()) if path.exists() else {
        "name": theme, "title": theme.replace("-", " ").title(), "format": 1, "kind": "flipbook", "base": base,
        "cell": cell, "defaults": base_m.get("defaults", {}), "icons": {}, "states": {}}
    shader_path.write_text(src)
    entry = {"src": f"icons/{icon}.glsl", "frames": a.frames, "fps": a.fps}
    if a.layers:
        entry["layers"] = layers
    if a.think:
        entry["think"] = True
    m["icons"][icon] = entry
    path.write_text(json.dumps(m, indent=1) + "\n")
    print(f"Wrote {shader_path} and its entry in {path}.")
    print(f"Next: forge.py bake {theme} {icon} --show")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def bake(a):
    theme = name("theme", a.theme)
    folder = _user_pack_folder(theme)
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"There is no pack called {theme} in {user_themes_dir()}. Start one with forge.py new.")
    safe_user_write_path(folder / "baked", is_dir=True)
    safe_user_write_path(folder / "pack.js")
    previews = folder / "previews"
    safe_user_write_path(previews, is_dir=True)
    m = json.loads(manifest_path.read_text())
    icons = [name("icon", i) for i in a.icons] or list(m["icons"])
    for icon in icons:
        safe_user_write_path(previews / f"{icon}.png")
        safe_user_write_path(previews / f"{icon}.webm")
    if os.environ.get("FORGE_LOCKED") != "1":
        # Take the shared lock and the resource cap, then run this same command inside them. Other renders may hold
        # the lock for minutes, so say so first: a silent wait looks like a hang.
        import fcntl
        with open(LOCK, "a") as probe:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(probe, fcntl.LOCK_UN)
            except BlockingIOError:
                print("Another render is running. Waiting for it to finish, up to 15 minutes, then baking.", flush=True)
        cmd = ["flock", "-w", "900", LOCK, str(ROOT / "scripts/capped"), sys.executable, __file__, *sys.argv[1:]]
        os.execve("/usr/bin/flock", cmd, {**os.environ, "FORGE_LOCKED": "1"})
    py, ok = sys.executable, True
    code, out = run([py, str(FORGE / "bake.py"), "--user-only", theme, *icons])
    print(out)
    if code != 0:
        ok = False
    code, out = run([py, str(FORGE / "bake.py"), "--user-only", theme, *icons, "--seam"])
    print(out)
    if "SEAM" in out or code != 0:
        ok = False
    previews.mkdir(exist_ok=True)
    shown = []
    for icon in icons:
        still, loop = previews / f"{icon}.png", previews / f"{icon}.webm"
        safe_user_write_path(still)
        safe_user_write_path(loop)
        common = [py, str(FORGE / "preview.py"), theme, "--pack-dir", str(folder)]
        # A still at three voice levels for an icon that answers the voice, else one frame on dark and on light.
        levels = "0,0.5,1" if m["icons"].get(icon, {}).get("voice") else "0"
        run(common + ["levels", "--icon", icon, "--levels", levels, "--scale", "2", "--out", str(still)])
        run(common + ["film", "--icon", icon, "--seconds", "4", "--fps", "24", "--size", "280", "--webm-only",
                      "--chunk", "4", "--out", str(loop)])
        print(f"{icon}: still {still}")
        print(f"{icon}: loop {loop}")
        shown.append((icon, loop))
    if not ok:
        print("A check failed: fix the shader and bake again. Nothing was shown.")
        return 1
    print("All checks passed.")
    if a.show and shown:
        icon, loop = shown[-1]
        code, out = run(["/usr/bin/python", str(ROOT / "desktop/relay.py"), "show", str(loop), "--title", f"{icon}, new icon"])
        print(out)
    return 0


def listing(_a):
    if not USER_THEMES.exists():
        print("No packs yet.")
        return
    for folder in sorted(p for p in USER_THEMES.iterdir() if (p / "manifest.json").exists()):
        m = json.loads((folder / "manifest.json").read_text())
        print(f"{folder.name} (on {m.get('base', 'its own')}): {', '.join(m.get('icons', {})) or 'no icons'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("theme")
    n.add_argument("icon")
    n.add_argument("--base", default="nova")
    n.add_argument("--think", action="store_true", help="join the thinking rotation")
    n.add_argument("--frames", type=int, default=24)
    n.add_argument("--fps", type=int, default=12)
    n.add_argument("--layers", help="comma-separated, such as main,voice")
    b = sub.add_parser("bake")
    b.add_argument("theme")
    b.add_argument("icons", nargs="*")
    b.add_argument("--show", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args()
    return {"new": new, "bake": bake, "list": listing}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
