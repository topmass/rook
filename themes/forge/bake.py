#!/usr/bin/env python3
"""The forge: bake a theme's shader icons into flipbook atlases.

    flock /tmp/rook-heavy.lock scripts/capped python3 themes/forge/bake.py nova rook cascade
    ... bake.py nova --all
    ... bake.py nova rook --cell 768 --still 0.25 --out <dir>   (one large frame, for close inspection)
    ... bake.py nova --all --seam   (checks that every loop closes; bakes nothing)

Each icon in themes/<theme>/manifest.json with a "src" is a GLSL file (see prelude.glsl for the contract). The bake
renders it in headless Chromium on the CPU (SwiftShader), muted, on a throwaway profile, and writes baked/<icon>.png
(the atlas, straight alpha) and baked/<icon>.json. Then it rewrites the theme's pack.js, which the player loads.
"""
import argparse
import base64
import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FORGE = Path(__file__).resolve().parent
THEMES = FORGE.parent
REPO_ROOT = THEMES.parent
ROOK_REPOS = (REPO_ROOT, Path.home() / ".local/share/rook/live", Path.home() / "Code/rook")
MAX_ATLAS_SIDE = 4096
# A user's own packs live outside the repo, because Rook never edits its own code (see skills/forge).
USER_THEMES = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "rook" / "themes"
RESERVED_NAMES = {"forge", "devs", "nova", "default", "builtin", "system", "tmp", "temp", "con", "nul"}


def user_themes_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "rook" / "themes"


def _path_within(path: Path, root: Path, *, allow_equal: bool = False) -> bool:
    r = os.path.realpath(str(root))
    p = os.path.realpath(str(path))
    try:
        same = os.path.commonpath([r, p]) == r
    except ValueError:
        return False
    return same if allow_equal else (same and p != r)


def _is_under(path: Path, root: Path) -> bool:
    return _path_within(path, root, allow_equal=False)


def safe_user_write_path(target: Path, *, is_dir: bool = False) -> Path:
    """Resolve target and its parent after following all symlinks; refuse unless strictly inside the real user themes
    folder and never inside Rook's own repo or live checkout."""
    real_udir = Path(os.path.realpath(str(user_themes_dir())))
    for repo in ROOK_REPOS:
        if _path_within(real_udir, repo, allow_equal=True):
            raise SystemExit(f"User themes folder {real_udir} lies inside Rook's own checkout ({repo}); refusing write.")
    cand = Path(target)
    if cand.is_symlink():
        raise SystemExit(f"Refusing to write through symlink {cand}.")
    real_parent = Path(os.path.realpath(str(cand.parent)))
    real_target = Path(os.path.realpath(str(cand)))
    if not _path_within(real_parent, real_udir, allow_equal=True):
        raise SystemExit(f"Write parent {cand.parent} resolves outside {real_udir}.")
    if not _path_within(real_target, real_udir, allow_equal=is_dir):
        raise SystemExit(f"Write target {cand} resolves outside {real_udir}.")
    for repo in ROOK_REPOS:
        if _path_within(real_target, repo, allow_equal=True) or _path_within(real_parent, repo, allow_equal=True):
            raise SystemExit(f"Refusing write inside Rook's own checkout: {real_target}.")
    return real_target


def is_builtin_or_reserved(name: str) -> bool:
    return name in RESERVED_NAMES or (THEMES / name).exists()


def theme_path(name, user_only=False):
    """A repo theme if one has this name (unless user_only), else the user's pack in ~/.config/rook/themes/<name>."""
    if user_only:
        if is_builtin_or_reserved(name):
            raise SystemExit(f"{name!r} is a built-in or reserved theme name and cannot be baked as a user pack.")
        udir = user_themes_dir()
        return safe_user_write_path(udir / name, is_dir=True)
    repo = THEMES / name
    return repo if (repo / "manifest.json").exists() else user_themes_dir() / name


def theme_common(theme_dir, manifest):
    """The theme's own common.glsl, or its base theme's (a user pack built on Nova uses Nova's palette and plasma)."""
    own = theme_dir / "common.glsl"
    if own.exists():
        return own.read_text()
    base = manifest.get("base")
    shared = THEMES / base / "common.glsl" if base else None
    return shared.read_text() if shared and shared.exists() else ""
DEFAULTS = {"frames": 24, "fps": 12, "layers": ["main"], "pivot": [0.5, 0.5], "loop": True, "ss": 2,
            "format": "png", "quality": 0.9}


def icon_spec(manifest, name):
    spec = {**DEFAULTS, "cell": manifest.get("cell", 192), **manifest.get("defaults", {}), **manifest["icons"][name]}
    if "src" not in spec:
        raise SystemExit(f"{name} has no src: only shader icons bake")
    return spec


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


def render(src, job, timeout=110):
    payload_b64 = base64.b64encode(json.dumps({"src": src, **job}).encode("utf-8")).decode("ascii")
    page = (FORGE / "bake.html").read_text().replace("__FORGE_JOB_B64__", payload_b64, 1)
    with tempfile.TemporaryDirectory(prefix="forge-", dir="/tmp") as tmp:
        (Path(tmp) / "bake.html").write_text(page)
        cmd = [shutil.which("chromium") or "chromium", "--headless=new", "--mute-audio", "--no-first-run",
               f"--user-data-dir={tmp}/profile", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
               *OFFLINE_CHROMIUM_FLAGS, "--dump-dom", f"file://{tmp}/bake.html"]
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
        env["XDG_CONFIG_HOME"] = tmp
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env).stdout
    start = out.find('<pre id="forge">')
    if start < 0:
        raise SystemExit("the bake page printed nothing; is Chromium working?")
    result = json.loads(html.unescape(out[start + 16:out.index("</pre>", start)]))
    if "error" in result:
        raise SystemExit(result["error"])
    return result


def write_pack(theme_dir, manifest, user_only=False):
    base = manifest.get("base")
    if base and "palette" not in manifest and (THEMES / base / "manifest.json").exists():
        manifest = {**manifest, "palette": json.loads((THEMES / base / "manifest.json").read_text()).get("palette", {})}
    icons = {}
    for name, entry in manifest["icons"].items():
        baked = theme_dir / "baked" / f"{name}.json"
        icons[name] = {**entry, **(json.loads(baked.read_text()) if baked.exists() else {})}
    pack = {**manifest, "icons": icons}
    target = theme_dir / "pack.js"
    if user_only:
        safe_user_write_path(target)
    target.write_text(
        f"(window.FORGE_PACKS ||= {{}})[{json.dumps(manifest['name'])}] = {json.dumps(pack, indent=1)};\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("theme")
    ap.add_argument("icons", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--cell", type=int, help="cell size in pixels, overriding the manifest")
    ap.add_argument("--format", choices=["png", "webp"], help="atlas format, overriding the manifest")
    ap.add_argument("--quality", type=float, help="WebP quality 0..1, overriding the manifest")
    ap.add_argument("--still", type=float, help="bake only this loop phase (0..1), for inspection")
    ap.add_argument("--out", type=Path, help="write here instead of the theme's baked/ (and skip pack.js)")
    ap.add_argument("--seam", action="store_true", help="check each loop: t = 0 and t = 1 must match; bakes nothing")
    ap.add_argument("--user-only", action="store_true", help="resolve strictly inside ~/.config/rook/themes/ (never repo)")
    a = ap.parse_args()
    theme_dir = theme_path(a.theme, user_only=a.user_only)
    out_dir = a.out or theme_dir / "baked"
    if a.user_only:
        safe_user_write_path(out_dir, is_dir=True)
        if not a.out and not a.seam:
            safe_user_write_path(theme_dir / "pack.js")
    manifest = json.loads((theme_dir / "manifest.json").read_text())
    names = [n for n, e in manifest["icons"].items() if "src" in e] if a.all else a.icons
    if not names:
        ap.error("name some icons, or pass --all")
    prelude = (FORGE / "prelude.glsl").read_text()
    common = theme_common(theme_dir, manifest)
    if a.user_only:
        # Validate every write target and atlas cap before creating directories or launching Chromium.
        for name in names:
            spec = icon_spec(manifest, name)
            cell = a.cell or spec["cell"]
            spec_fmt = a.format if a.format is not None else spec["format"]
            ext = "webp" if spec_fmt == "webp" else "png"
            n_cells = (1 if a.still is not None else int(spec["frames"])) * len(spec["layers"])
            side = math.ceil(math.sqrt(max(1, n_cells))) * int(cell)
            if side > MAX_ATLAS_SIDE:
                raise SystemExit(f"{name}: atlas side {side}px exceeds {MAX_ATLAS_SIDE}px cap (frames={spec['frames']}, layers={len(spec['layers'])}, cell={cell}).")
            if not a.seam:
                safe_user_write_path(out_dir / f"{name}.{ext}")
                safe_user_write_path(out_dir / f"{name}.json")
    out_dir.mkdir(parents=True, exist_ok=True)
    edge_fail = []
    for name in names:
        spec = icon_spec(manifest, name)
        cell = a.cell or spec["cell"]
        spec.update({k: v for k, v in (("format", a.format), ("quality", a.quality)) if v is not None})
        src = "\n".join([prelude, common, (theme_dir / spec["src"]).read_text()])
        job = {"cell": cell, "ss": spec["ss"], "frames": spec["frames"], "layers": spec["layers"], "loop": spec["loop"],
               "format": spec["format"], "quality": spec["quality"]}
        if a.seam:
            if not spec["loop"]:
                continue
            r = render(src, {**job, "cell": 96, "layers": spec["layers"][:1], "times": [0.0, 1.0], "seam": True})
            # A few edge pixels may round differently; a real seam moves many.
            print(f"{name}: {'ok' if r['off'] <= 3 else 'SEAM'} ({r['off']} pixels differ, worst by {r['seam']})")
            continue
        if a.still is not None:
            job["times"] = [a.still]
        r = render(src, job)
        png = base64.b64decode(r["png"].split(",", 1)[1])
        ext = "webp" if spec["format"] == "webp" else "png"
        for old in out_dir.glob(f"{name}.*"):
            if old.suffix in (".png", ".webp") and old.suffix != f".{ext}":
                if a.user_only:
                    safe_user_write_path(old)
                old.unlink()
        img_target = out_dir / f"{name}.{ext}"
        json_target = out_dir / f"{name}.json"
        if a.user_only:
            safe_user_write_path(img_target)
            safe_user_write_path(json_target)
        img_target.write_bytes(png)
        meta = {"image": f"baked/{name}.{ext}", "frames": len(job.get("times", [])) or spec["frames"],
                "fps": spec["fps"], "layers": spec["layers"], "cell": cell, "grid": r["grid"],
                "pivot": spec["pivot"], "bbox": r["bbox"], "loop": spec["loop"], "alpha": "straight"}
        json_target.write_text(json.dumps(meta, indent=1) + "\n")
        print(f"{name}: {len(png) / 1024:.0f} KiB, grid {r['grid']}, bbox {r['bbox']}")
        if r["edge"] > 1:
            edge_fail.append(f"{name} (alpha {r['edge']} at {r['edgeAt']} in the cell, 0..1 from top left)")
    if not a.out and not a.seam:
        write_pack(theme_dir, manifest, user_only=a.user_only)
    if edge_fail:
        # Glow that reaches the cell's outer band shows the cell as a faint square; pull it in.
        raise SystemExit("EDGE: glow reaches the cell's edge in " + ", ".join(edge_fail))


if __name__ == "__main__":
    sys.exit(main())
