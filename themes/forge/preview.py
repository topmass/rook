#!/usr/bin/env python3
"""Previews from the player, rendered headless and muted.

    flock /tmp/rook-heavy.lock scripts/capped python3 themes/forge/preview.py nova sheet --scale 4 --out x.png
    ... preview.py nova film --state thinking --seconds 9 --out thinking.webm   (also writes .webp beside it)
    ... preview.py nova film --icon cascade --seconds 4 --out cascade.webm
"""
import argparse
import base64
import html
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

FORGE = Path(__file__).resolve().parent
OFFLINE_CHROMIUM_FLAGS = [
    "--host-resolver-rules=MAP * ~NOTFOUND",
    "--no-proxy-server",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--disable-extensions",
    "--disable-default-apps",
    "--metrics-recording-only",
]


def run_player(params, budget_ms=60000):
    url = (FORGE / "player.html").as_uri() + "?" + urllib.parse.urlencode(params)
    with tempfile.TemporaryDirectory(prefix="forge-", dir="/tmp") as tmp:
        cmd = [shutil.which("chromium") or "chromium", "--headless=new", "--mute-audio", "--no-first-run",
               f"--user-data-dir={tmp}/profile", "--allow-file-access-from-files",
               *OFFLINE_CHROMIUM_FLAGS, f"--virtual-time-budget={budget_ms}", "--dump-dom", url]
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
        env["XDG_CONFIG_HOME"] = tmp
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=115, env=env).stdout
    start = out.find('<pre id="forge">')
    if start < 0:
        raise SystemExit("the player printed nothing")
    result = json.loads(html.unescape(out[start + 16:out.index("</pre>", start)]))
    if isinstance(result, dict):
        raise SystemExit(result["error"])
    return [base64.b64decode(u.split(",", 1)[1]) for u in result]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack")
    ap.add_argument("--pack-dir", help="a pack outside the repo, such as ~/.config/rook/themes/<name>")
    ap.add_argument("mode", choices=["sheet", "film", "dsheet", "dfilm", "levels", "compare", "vfilm"])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", default="1")
    ap.add_argument("--t", default="0.3")
    ap.add_argument("--state")
    ap.add_argument("--icon")
    ap.add_argument("--seconds", default="4")
    ap.add_argument("--fps", default="24")
    ap.add_argument("--size", default="280")
    ap.add_argument("--layout", choices=["stage", "phone"], default="stage")
    ap.add_argument("--chunk", default="8", help="seconds per Chromium run for films")
    ap.add_argument("--levels", default="0,0.5,1", help="levels mode: comma-separated voice levels")
    ap.add_argument("--env", help="vfilm: a file of comma-separated levels, one per 1/60 s")
    ap.add_argument("--start", default="0", help="film from this second of the script (to split long films)")
    ap.add_argument("--n", default="1", help="dispatch: how many sends (or long)")
    ap.add_argument("--panel", default="1000", help="dispatch sheet: panel width at 1x")
    ap.add_argument("--stack", action="store_true", help="dispatch sheet: light panels under dark ones")
    ap.add_argument("--webm-only", action="store_true", help="skip the lossless WebP, which is slow on long films")
    a = ap.parse_args()
    extra = {"base": Path(a.pack_dir).resolve().as_uri() + "/"} if a.pack_dir else {}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.mode == "sheet":
        a.out.write_bytes(run_player({**extra, "pack": a.pack, "mode": "sheet", "scale": a.scale, "t": a.t})[0])
        return
    if a.mode == "levels":
        a.out.write_bytes(run_player({**extra, "pack": a.pack, "mode": "levels", "icon": a.icon or "speak", "scale": a.scale, "t": a.t,
                                      "levels": a.levels})[0])
        return
    if a.mode == "dsheet":
        a.out.write_bytes(run_player({**extra, "pack": a.pack, "mode": "dsheet", "scale": a.scale, "panel": a.panel,
                                      "stack": "1" if a.stack else "0"})[0])
        return
    params = {**extra, "pack": a.pack, "mode": "film", "fps": a.fps, "size": a.size}
    if a.mode == "vfilm":
        params = {**extra, "pack": a.pack, "mode": "vfilm", "fps": a.fps, "scale": a.scale, "icon": a.icon or "speak",
                  "env": Path(a.env).read_text().strip() if a.env else ""}
    if a.mode == "compare":
        params = {**extra, "pack": a.pack, "mode": "compare", "fps": a.fps, "scale": a.scale}
    if a.mode == "dfilm":
        params = {**extra, "pack": a.pack, "mode": "dfilm", "fps": a.fps, "n": a.n, "scale": a.scale}
    params.update({k: v for k, v in (("state", a.state), ("icon", a.icon)) if v})
    if a.layout == "phone":
        params["layout"] = "phone"
    # Long films render in chunks (each one Chromium run), so no page holds more frames than it can print.
    start, secs, chunk = float(a.start), float(a.seconds), float(a.chunk)
    frames = []
    k = 0.0
    while k < secs - 1e-6:
        frames += run_player({**params, "start": f"{start + k:g}", "seconds": f"{min(chunk, secs - k):g}"})
        k += chunk
    with tempfile.TemporaryDirectory(prefix="forge-film-") as tmp:
        for i, png in enumerate(frames):
            (Path(tmp) / f"f{i:04d}.png").write_bytes(png)
        src = ["-framerate", a.fps, "-i", f"{tmp}/f%04d.png"]
        # Lossless both ways, so the encoding hides nothing: VP9 lossless in full 4:4:4 colour, and lossless WebP.
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *src, "-c:v", "libvpx-vp9", "-lossless", "1",
                        "-pix_fmt", "yuv444p", "-an", str(a.out)], check=True)
        if not a.webm_only:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *src, "-c:v", "libwebp_anim", "-lossless", "1",
                            "-loop", "0", "-an", str(a.out.with_suffix(".webp"))], check=True)
    print(f"{len(frames)} frames -> {a.out}")


if __name__ == "__main__":
    main()
