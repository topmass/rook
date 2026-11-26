"""Theme pack discovery and flipbook atlas playback matching themes/forge/FORMAT.md (checkpoint 3).

Supports both ``kind: "points"`` (Devs gold dust) and ``kind: "flipbook"`` (Nova baked WebP/PNG atlases),
including ``cycle`` states, ``level`` ("in"/"out"), per-icon ``voice`` (opacity/scale/stretch), and ``label``.
"""

from __future__ import annotations

from collections import OrderedDict, deque
import io
import json
import math
import os
import re
import stat
import threading

import cairo
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

_HERE = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.normpath(os.path.join(_HERE, "..", "themes"))
DEFAULT_PACK = "devs"
REAL_SIZE = 140.0  # Presence icon size on screen in logical pixels (matches forge/presence.js).
PACK_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
MAX_ATLAS_SIDE = 4096          # Max atlas width/height in pixels (16x16 grid of 256 px cells; Nova max is 2816x2560).
MAX_ATLAS_PIXELS = 4096 * 4096 # Max decoded pixels per atlas (64 MiB uncompressed RGBA ceiling).
MAX_ATLAS_FILE_BYTES = 16 * 1024 * 1024  # Max compressed atlas file size on disk (16 MiB).
MAX_FONT_FILE_BYTES = 2 * 1024 * 1024  # Max font file a built-in pack's text block may name (2 MiB).

_PACK_CACHE: dict[tuple[str, str, str], dict] = {}


def user_themes_dir() -> str:
    """User's own theme packs folder ($XDG_CONFIG_HOME/rook/themes, default ~/.config/rook/themes)."""
    cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.normpath(os.path.join(cfg, "rook", "themes"))


def _contained_dir(root: str, name: str) -> str:
    """Return pack folder inside root; refuse invalid names, symlinked pack folders, or path escapes."""
    if not isinstance(name, str) or not PACK_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid theme pack name '{name}'")
    cand = os.path.join(root, name)
    if os.path.islink(cand):
        raise ValueError(f"pack '{name}' folder may not be a symlink")
    real_root = os.path.realpath(root)
    real_cand = os.path.realpath(cand)
    try:
        inside = os.path.commonpath([real_root, real_cand]) == real_root and real_cand != real_root
    except ValueError:
        inside = False
    if not inside:
        raise ValueError(f"pack '{name}' resolves outside themes directory")
    return real_cand


def _contained_file(pdir: str, rel_path: str, label: str) -> str:
    """Resolve rel_path strictly to a regular file inside pdir (following symlinks); reject absolute paths and escapes."""
    if not isinstance(rel_path, str) or not rel_path or os.path.isabs(rel_path) or "\x00" in rel_path:
        raise ValueError(f"{label} must be a relative path inside the pack")
    real_root = os.path.realpath(pdir)
    real_file = os.path.realpath(os.path.join(real_root, rel_path))
    try:
        inside = os.path.commonpath([real_root, real_file]) == real_root and real_file != real_root
    except ValueError:
        inside = False
    if not inside:
        raise ValueError(f"{label} escapes pack directory")
    try:
        st = os.stat(real_file)
    except OSError as exc:
        raise ValueError(f"{label} missing or unreadable: {exc}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise ValueError(f"{label} must be a regular file")
    return real_file


def _resolve_pack_dir(name: str, themes_dir: str = THEMES_DIR, user_dir: str | None = None) -> tuple[str, bool]:
    """Locate a pack in repo themes_dir first, then user_dir; returns (pack_dir, is_user)."""
    if not isinstance(name, str) or not PACK_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid theme pack name '{name}'")
    repo_cand = os.path.join(themes_dir, name)
    if os.path.exists(repo_cand) or os.path.islink(repo_cand):
        repo = _contained_dir(themes_dir, name)
        if os.path.isfile(os.path.join(repo, "manifest.json")):
            return repo, False
    udir = user_themes_dir() if user_dir is None else user_dir
    if udir:
        upath = os.path.join(udir, name)
        if os.path.exists(upath) or os.path.islink(upath):
            u_real = _contained_dir(udir, name)
            if os.path.isfile(os.path.join(u_real, "manifest.json")):
                return u_real, True
    return repo_cand, False


def list_packs(themes_dir: str = THEMES_DIR, user_dir: str | None = None) -> tuple[str, ...]:
    """Return sorted theme pack names across repo themes/ and ~/.config/rook/themes/."""
    udir = user_themes_dir() if user_dir is None else user_dir
    found: set[str] = set()
    for root in (themes_dir, udir):
        if not root or not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            if not PACK_NAME_RE.fullmatch(entry):
                continue
            cand = os.path.join(root, entry)
            if os.path.islink(cand):
                continue
            try:
                pdir = _contained_dir(root, entry)
                _contained_file(pdir, "manifest.json", "manifest.json")
            except ValueError:
                continue
            found.add(entry)
    return tuple(sorted(found)) or (DEFAULT_PACK,)


def _probe_image_header(path: str) -> tuple[int, int]:
    """Read PNG or WebP dimensions from the first 32 bytes (< 0.05 ms/file) and enforce size/dimension caps before decode."""
    st = os.stat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("atlas must be a regular file")
    if st.st_size <= 0 or st.st_size > MAX_ATLAS_FILE_BYTES:
        raise ValueError(f"atlas file size {st.st_size} bytes exceeds limit ({MAX_ATLAS_FILE_BYTES})")
    with open(path, "rb") as f:
        head = f.read(32)
    w = h = 0
    if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        w = int.from_bytes(head[16:20], "big")
        h = int.from_bytes(head[20:24], "big")
        if w <= 0 or h <= 0:
            raise ValueError("invalid PNG dimensions")
    elif len(head) >= 30 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        chunk = head[12:16]
        if chunk == b"VP8X":
            w = 1 + int.from_bytes(head[24:27], "little")
            h = 1 + int.from_bytes(head[27:30], "little")
        elif chunk == b"VP8 " and head[23:26] == b"\x9d\x01\x2a":
            w = int.from_bytes(head[26:28], "little") & 0x3FFF
            h = int.from_bytes(head[28:30], "little") & 0x3FFF
        elif chunk == b"VP8L" and head[20] == 0x2F:
            bits = int.from_bytes(head[21:25], "little")
            w = 1 + (bits & 0x3FFF)
            h = 1 + ((bits >> 14) & 0x3FFF)
        if w <= 0 or h <= 0:
            raise ValueError("invalid WebP header")
    else:
        fmt, w, h = GdkPixbuf.Pixbuf.get_file_info(path)
        if fmt is None or w <= 0 or h <= 0:
            raise ValueError("unreadable image header")
    if w > MAX_ATLAS_SIDE or h > MAX_ATLAS_SIDE or (w * h) > MAX_ATLAS_PIXELS:
        raise ValueError(f"atlas dimensions {w}x{h} exceed cap ({MAX_ATLAS_SIDE}x{MAX_ATLAS_SIDE})")
    return w, h


def validate_pack(name: str, themes_dir: str = THEMES_DIR, user_dir: str | None = None) -> dict:
    """Validate manifest structure, optional base theme, icon fields, and atlas readability; return merged pack."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("theme pack name must be a non-empty string")
    udir = user_themes_dir() if user_dir is None else user_dir
    pdir, is_user = _resolve_pack_dir(name, themes_dir=themes_dir, user_dir=udir)
    mpath = _contained_file(pdir, "manifest.json", f"manifest.json for pack '{name}'")
    try:
        with open(mpath, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as exc:
        raise ValueError(f"unreadable manifest.json for pack '{name}': {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"manifest for pack '{name}' must be a JSON object")
    kind = raw.get("kind", "points")
    if kind not in ("points", "flipbook"):
        raise ValueError(f"unsupported pack kind '{kind}' in '{name}'")
    base_name = raw.get("base")
    if base_name is not None:
        if not isinstance(base_name, str) or not base_name.strip() or "/" in base_name or ".." in base_name:
            raise ValueError(f"pack '{name}' has invalid base '{base_name}'")
        base_manifest = os.path.join(themes_dir, base_name, "manifest.json")
        if not os.path.isfile(base_manifest):
            raise ValueError(f"pack '{name}' references unknown base theme '{base_name}'")
    icons = raw.get("icons")
    states = raw.get("states")
    if not isinstance(icons, dict) or not isinstance(states, dict):
        raise ValueError(f"pack '{name}' must define object 'icons' and 'states'")
    tr_raw = raw.get("transition")
    if tr_raw is not None:
        if not isinstance(tr_raw, dict):
            raise ValueError(f"pack '{name}' transition must be an object")
        if "seconds" in tr_raw and float(tr_raw["seconds"]) <= 0:
            raise ValueError(f"pack '{name}' transition.seconds must be positive")
    for st_name, st_val in states.items():
        if not isinstance(st_val, (str, dict)):
            raise ValueError(f"pack '{name}' state '{st_name}' has invalid type")
    for iname, spec in icons.items():
        if not isinstance(spec, dict):
            raise ValueError(f"pack '{name}' icon '{iname}' must be an object")
        if "fps" in spec and (isinstance(spec["fps"], bool) or float(spec["fps"]) <= 0):
            raise ValueError(f"pack '{name}' icon '{iname}' has invalid fps")
        if "frames" in spec and (isinstance(spec["frames"], bool) or int(spec["frames"]) < 1):
            raise ValueError(f"pack '{name}' icon '{iname}' has invalid frames")
        if "cell" in spec and (isinstance(spec["cell"], bool) or int(spec["cell"]) < 1):
            raise ValueError(f"pack '{name}' icon '{iname}' has invalid cell")
        if "grid" in spec:
            g = spec["grid"]
            if not (isinstance(g, list) and len(g) == 2 and int(g[0]) >= 1 and int(g[1]) >= 1):
                raise ValueError(f"pack '{name}' icon '{iname}' has invalid grid")
        if "voice" in spec and spec["voice"] is not None and not isinstance(spec["voice"], dict):
            raise ValueError(f"pack '{name}' icon '{iname}' has invalid voice config")

    pack = load_pack(name, themes_dir=themes_dir, reload=True, user_dir=udir)
    if pack.get("kind") == "flipbook":
        needed: set[str] = set()
        for st_val in (pack.get("states") or {}).values():
            if isinstance(st_val, str):
                needed.add(st_val)
            elif isinstance(st_val, dict):
                if isinstance(st_val.get("icon"), str):
                    needed.add(st_val["icon"])
                if isinstance(st_val.get("rook"), str):
                    needed.add(st_val["rook"])
                if isinstance(st_val.get("cycle"), list):
                    for c in st_val["cycle"]:
                        if isinstance(c, str):
                            needed.add(c)
        tr = pack.get("transition") or {}
        if isinstance(tr, dict) and isinstance(tr.get("flash"), str):
            needed.add(tr["flash"])
        for iname, spec in pack["icons"].items():
            if isinstance(spec, dict) and (spec.get("think") or spec.get("sprite")):
                needed.add(iname)
        # Also validate every user-defined icon in a user pack, even if not yet referenced by a state.
        if is_user:
            needed.update(icons.keys())
        # Include any one-shot intro referenced by a needed icon (e.g. dispatch -> dispatch_in).
        for iname in list(needed):
            spec = pack["icons"].get(iname)
            intro = spec.get("intro") if isinstance(spec, dict) else None
            if isinstance(intro, dict) and isinstance(intro.get("icon"), str):
                needed.add(intro["icon"])
        if not needed:
            raise ValueError(f"flipbook pack '{name}' references no icons")
        for iname in sorted(needed):
            spec = pack["icons"].get(iname)
            if not isinstance(spec, dict):
                raise ValueError(f"pack '{name}' missing icon spec '{iname}'")
            img = spec.get("_image_path")
            if not isinstance(img, str) or not os.path.isfile(img):
                raise ValueError(f"pack '{name}' missing atlas file for icon '{iname}'")
            try:
                w, h = _probe_image_header(img)
            except (OSError, ValueError) as exc:
                raise ValueError(f"pack '{name}' unreadable atlas image for icon '{iname}': {exc}") from exc
            if w <= 0 or h <= 0:
                raise ValueError(f"pack '{name}' invalid atlas dimensions for icon '{iname}'")
            frames = int(spec.get("frames", 0))
            fps = float(spec.get("fps", 0))
            grid = spec.get("grid")
            cell = int(spec.get("cell", 0))
            if frames < 1 or fps <= 0 or cell < 1 or not (isinstance(grid, list) and len(grid) == 2 and int(grid[0]) >= 1 and int(grid[1]) >= 1):
                raise ValueError(f"pack '{name}' invalid grid/frames/fps for icon '{iname}'")
    return pack


def _load_pack_icons(pdir: str, pack: dict) -> dict:
    defaults = pack.get("defaults") or {}
    default_cell = int(pack.get("cell", 256))
    merged_icons = {}
    icons_raw = pack.get("icons")
    if not isinstance(icons_raw, dict):
        raise ValueError(f"manifest in '{pdir}' missing icons dict")
    for iname, spec in icons_raw.items():
        if not isinstance(spec, dict):
            raise ValueError(f"icon '{iname}' in '{pdir}' must be an object")
        merged = dict(spec)
        baked_rel = os.path.join("baked", f"{iname}.json")
        baked_cand = os.path.join(pdir, baked_rel)
        if os.path.exists(baked_cand) or os.path.islink(baked_cand):
            baked_json = _contained_file(pdir, baked_rel, f"baked json for '{iname}'")
            with open(baked_json, "r", encoding="utf-8") as bf:
                bdata = json.load(bf)
                if not isinstance(bdata, dict):
                    raise ValueError(f"baked json for '{iname}' is not an object")
                merged.update(bdata)
        merged.setdefault("frames", int(defaults.get("frames", 24)))
        merged.setdefault("fps", float(defaults.get("fps", 12)))
        merged.setdefault("layers", ["main"])
        merged.setdefault("pivot", [0.5, 0.5])
        merged.setdefault("loop", True)
        merged.setdefault("cell", default_cell)
        if "image" in merged:
            merged["_image_path"] = _contained_file(pdir, merged["image"], f"atlas for icon '{iname}'")
        merged_icons[iname] = merged
    return merged_icons


def load_pack(name: str = DEFAULT_PACK, themes_dir: str = THEMES_DIR, reload: bool = False,
              user_dir: str | None = None) -> dict:
    """Load a theme pack manifest (repo or ~/.config/rook/themes/), resolving optional 'base' and baked/*.json."""
    udir = user_themes_dir() if user_dir is None else user_dir
    key = (themes_dir, udir, name)
    if not reload and key in _PACK_CACHE:
        return _PACK_CACHE[key]
    pdir, _is_user = _resolve_pack_dir(name, themes_dir=themes_dir, user_dir=udir)
    mpath = os.path.join(pdir, "manifest.json")
    with open(mpath, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"manifest for '{name}' is not a JSON object")
    raw = {k: v for k, v in raw.items() if not str(k).startswith("_")}  # Keys starting "_" are the loader's own.
    own_icons = _load_pack_icons(pdir, raw)
    base_name = raw.get("base")
    if isinstance(base_name, str) and base_name.strip():
        if base_name == name or "/" in base_name or ".." in base_name:
            raise ValueError(f"invalid base theme '{base_name}' in pack '{name}'")
        base_dir = os.path.join(themes_dir, base_name)
        base_mpath = os.path.join(base_dir, "manifest.json")
        if not os.path.isfile(base_mpath):
            raise ValueError(f"missing base theme '{base_name}' for pack '{name}'")
        with open(base_mpath, "r", encoding="utf-8") as bf:
            base_raw = json.load(bf)
        if not isinstance(base_raw, dict):
            raise ValueError(f"base manifest '{base_name}' is not a JSON object")
        base_raw = {k: v for k, v in base_raw.items() if not str(k).startswith("_")}
        base_icons = _load_pack_icons(base_dir, base_raw)
        pack = dict(base_raw)
        pack.update({k: v for k, v in raw.items() if k not in ("icons", "states", "palette", "transition")})
        # Keep base palette unless user overrides; merge dict palettes cleanly.
        merged_pal = dict(base_raw.get("palette") or {})
        if isinstance(raw.get("palette"), dict):
            merged_pal.update(raw["palette"])
        pack["palette"] = merged_pal
        if isinstance(raw.get("transition"), dict):
            merged_tr = dict(base_raw.get("transition") or {})
            merged_tr.update(raw["transition"])
            pack["transition"] = merged_tr
        merged_icons = dict(base_icons)
        merged_icons.update(own_icons)
        pack["icons"] = merged_icons
        merged_states = dict(base_raw.get("states") or {})
        if isinstance(raw.get("states"), dict):
            merged_states.update(raw["states"])
        pack["states"] = merged_states
        pack["_dir"] = pdir
        pack["_base_dir"] = base_dir
    else:
        pack = dict(raw)
        pack["_dir"] = pdir
        pack["icons"] = own_icons
    pack["_user"] = _is_user
    pack["_own"] = tuple(own_icons)  # The icons this pack's own manifest names, not its base's.
    _PACK_CACHE[key] = pack
    return pack


FORM_ROWS = 640  # A dust form's grains: the dust engine's GRAINS.
FORM_HALF = 62.0  # Half the 124 px form box, in logical px.
MAX_FORM_BYTES = 64 * 1024
MAX_PACK_FORMS = 4  # Dust forms a pack may add to the thinking rotation; Devs has four thinking forms of its own.
MAX_FORM_TRIES = 4 * MAX_PACK_FORMS  # Form files read per pack load, good or bad, so a huge pack cannot stall it.


def _plain(text) -> str:
    """A name from a pack, safe to put in a log line: printable characters only, and short."""
    return "".join(c if c.isprintable() else "?" for c in str(text))[:60]


def check_form_rows(rows) -> str | None:
    """One plain sentence on what is wrong with a dust form's [x, y, z] rows, or None when they are good. It only
    compares numbers, so no value can make it raise."""
    if not isinstance(rows, list) or len(rows) != FORM_ROWS:
        return f"The form has {len(rows) if isinstance(rows, list) else 0} rows, and a form needs exactly {FORM_ROWS}."
    for k, row in enumerate(rows, 1):
        if not (isinstance(row, list) and len(row) == 3 and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != math.inf for v in row)):
            return f"Row {k} of the form is not three plain numbers."
        if not all(abs(v) <= FORM_HALF for v in row):
            return f"Row {k} of the form lies outside the 124 px form box."
    return None


def pack_forms(pack: dict) -> tuple[dict, list]:
    """A user dust pack's own forms for the thinking rotation: ({key: (points, spin)}, problems). Each problem is one
    plain sentence, and its icon is left out, so thinking keeps the built-in forms. At most MAX_PACK_FORMS are read."""
    forms, problems, over, tries = {}, [], 0, 0
    if pack.get("kind") != "points" or not pack.get("_user"):
        return forms, problems
    for iname in pack.get("_own", ()):
        spec = pack["icons"].get(iname)
        rel = spec.get("form") if isinstance(spec, dict) and spec.get("think") else None
        if not (isinstance(rel, str) and rel.endswith(".json")):
            problems.append(f"Icon {_plain(iname)} keeps the built-in forms. A dust icon needs a .json form file and "
                            "think set to true.")
            continue
        if len(forms) >= MAX_PACK_FORMS or tries >= MAX_FORM_TRIES:
            over += 1
            continue
        tries += 1
        shown = _plain(rel)
        spin, rows = spec.get("spin", 0.45), None
        try:
            path = _contained_file(pack["_dir"], rel, rel)
            if os.path.getsize(path) > MAX_FORM_BYTES:
                problem = f"The form file {shown} is over {MAX_FORM_BYTES // 1024} KB."
            else:
                with open(path, encoding="utf-8") as f:
                    rows = json.load(f)
                problem = check_form_rows(rows)
        except Exception as exc:  # Every way a form file can fail ends in one sentence, never a dropped pack.
            text = str(exc)
            problem = (f"The form file {shown} is not JSON." if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError))
                       else f"The form file {shown} is missing." if "missing" in text
                       else f"The form file {shown} is not a file inside the pack folder." if isinstance(exc, ValueError)
                       else f"The form file {shown} cannot be read as a form.")
        if problem is None and not (isinstance(spin, (int, float)) and not isinstance(spin, bool) and abs(spin) <= 2):
            problem = "The icon's spin must be a number from -2 to 2."
        if problem:
            problems.append(f"Icon {_plain(iname)} keeps the built-in forms. {problem}")
            continue
        points = sorted((tuple(map(float, r)) for r in rows), key=lambda p: math.atan2(p[1], p[0]))
        forms[f"pack:{os.path.basename(pack['_dir'])}/{iname}"] = (points, float(spin))
    if over:
        problems.append(f"{over} more icons keep the built-in forms, because a pack holds at most {MAX_PACK_FORMS} "
                        "dust forms.")
    return forms, problems


def pack_font_file(pack: dict) -> str | None:
    """The font file a pack's text block names, checked, or None when it names none. Only a built-in pack may bring
    one, because FreeType parses it inside the overlay: a user pack's "font" is ignored. The file must be a regular
    .ttf or .otf file inside the pack folder, under the size cap, with no symlink on its path. Raises ValueError."""
    text = pack.get("text")
    rel = text.get("font") if isinstance(text, dict) else None
    if rel is None or pack.get("_user", True):
        return None
    pdir = pack.get("_dir")
    if not isinstance(pdir, str) or not isinstance(rel, str) or not rel.lower().endswith((".ttf", ".otf")):
        raise ValueError("text.font must be a .ttf or .otf file inside the pack")
    step = pdir
    for part in rel.split("/"):
        step = os.path.join(step, part)
        if os.path.islink(step):
            raise ValueError("text.font may not be or pass through a symlink")
    path = _contained_file(pdir, rel, "text.font")
    if os.path.getsize(path) > MAX_FONT_FILE_BYTES:
        raise ValueError(f"text.font is larger than {MAX_FONT_FILE_BYTES} bytes")
    return path


def load_premultiplied_surface(path: str) -> cairo.ImageSurface:
    """Load a straight-alpha PNG or WebP atlas into a premultiplied BGRA Cairo ImageSurface after header cap check."""
    _probe_image_header(path)
    if path.lower().endswith(".png"):
        return cairo.ImageSurface.create_from_png(path)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
    ok, data = pixbuf.save_to_bufferv("png", ["compression"], ["0"])
    if not ok:
        raise RuntimeError(f"Could not decode atlas {path}")
    return cairo.ImageSurface.create_from_png(io.BytesIO(data))


def load_rgba_pixels(path: str) -> tuple[bytes, int, int, int]:
    """Decode a PNG or WebP atlas directly to straight-alpha RGBA8 bytes after enforcing size/dimension header caps."""
    _probe_image_header(path)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
    if not pixbuf.get_has_alpha():
        pixbuf = pixbuf.add_alpha(False, 0, 0, 0)
    return pixbuf.get_pixels(), pixbuf.get_width(), pixbuf.get_height(), pixbuf.get_rowstride()


class AtlasLoader:
    """Single daemon-thread background WebP/PNG decoder with bounded LRU ready cache and instant exit."""

    MAX_READY_BYTES = 32 * 1024 * 1024  # Cap undrawn decoded buffers at 32 MiB (fits 27.5 MiB dispatch atlas).

    def __init__(self):
        self._cond = threading.Condition()
        self._worker: threading.Thread | None = None
        self._queue: deque[tuple[int, str]] = deque()
        self._queued: set[str] = set()
        self._inflight: str | None = None
        self._gen = 0
        self._wanted: set[str] | None = None  # None = accept any path in current gen; set = active filter.
        self._ready: OrderedDict[str, tuple[bytes, int, int, int]] = OrderedDict()
        self._ready_bytes = 0
        self._failed: dict[str, str] = {}

    def _ensure_worker(self):
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run, name="rook-atlas", daemon=True)
            self._worker.start()

    def _run(self):
        while True:
            with self._cond:
                while not self._queue:
                    self._cond.wait()
                gen, path = self._queue.popleft()
                self._queued.discard(path)
                if gen != self._gen or (self._wanted is not None and path not in self._wanted):
                    continue
                self._inflight = path
            data = None
            err = None
            try:
                data = load_rgba_pixels(path)
            except Exception as exc:
                err = str(exc)
            with self._cond:
                self._inflight = None
                stale = (gen != self._gen) or (self._wanted is not None and path not in self._wanted)
                if stale:
                    continue
                if data is not None:
                    nbytes = len(data[0])
                    if path in self._ready:
                        self._ready_bytes = max(0, self._ready_bytes - len(self._ready.pop(path)[0]))
                    self._ready[path] = data
                    self._ready_bytes += nbytes
                    self._evict_locked()
                else:
                    self._failed[path] = err or "decode failed"

    def _evict_locked(self):
        while self._ready_bytes > self.MAX_READY_BYTES and len(self._ready) > 1:
            _, old = self._ready.popitem(last=False)
            self._ready_bytes = max(0, self._ready_bytes - len(old[0]))

    def prefetch(self, path: str):
        if not path:
            return
        with self._cond:
            if path in self._ready:
                self._ready.move_to_end(path)
                return
            if path in self._queued or path == self._inflight or path in self._failed:
                return
            if self._wanted is not None:
                self._wanted.add(path)
            self._ensure_worker()
            self._queue.append((self._gen, path))
            self._queued.add(path)
            self._cond.notify()

    def pop_ready(self, path: str) -> tuple[bytes, int, int, int] | None:
        with self._cond:
            data = self._ready.pop(path, None)
            if data is not None:
                self._ready_bytes = max(0, self._ready_bytes - len(data[0]))
            return data

    def keep_only(self, keep_paths: set[str] | None):
        """Drop undrawn decoded buffers outside keep_paths (or all when keep_paths is None/empty)."""
        with self._cond:
            if not keep_paths:
                self._gen += 1
                self._wanted = None
                self._queue.clear()
                self._queued.clear()
                self._ready.clear()
                self._ready_bytes = 0
                return
            self._wanted = set(keep_paths)
            for p in list(self._ready.keys()):
                if p not in keep_paths:
                    old = self._ready.pop(p)
                    self._ready_bytes = max(0, self._ready_bytes - len(old[0]))
            if self._queue:
                kept = deque((g, p) for g, p in self._queue if g == self._gen and p in keep_paths)
                self._queue = kept
                self._queued = {p for _, p in kept}

    def reset_for_pack(self, pack: dict | None = None):
        """Clear stale failures and undrawn buffers when switching or re-selecting a theme pack."""
        allowed = None
        if isinstance(pack, dict) and pack.get("kind") == "flipbook":
            allowed = {spec["_image_path"] for spec in (pack.get("icons") or {}).values()
                       if isinstance(spec, dict) and isinstance(spec.get("_image_path"), str)}
        with self._cond:
            self._failed.clear()
            self._gen += 1
            self._wanted = allowed
            self._queue.clear()
            self._queued.clear()
            if not allowed:
                self._ready.clear()
                self._ready_bytes = 0
            else:
                for p in list(self._ready.keys()):
                    if p not in allowed:
                        old = self._ready.pop(p)
                        self._ready_bytes = max(0, self._ready_bytes - len(old[0]))

    def failure(self, path: str) -> str | None:
        with self._cond:
            return self._failed.get(path)

    def clear_failed(self, path: str | None = None):
        with self._cond:
            if path is None:
                self._failed.clear()
            else:
                self._failed.pop(path, None)

    @property
    def ready_bytes(self) -> int:
        with self._cond:
            return self._ready_bytes


ATLAS_LOADER = AtlasLoader()


def _hex_rgb(code: str, fallback: tuple[float, float, float]) -> tuple[float, float, float]:
    s = (code or "").strip().lstrip("#")
    if len(s) == 6:
        try:
            return int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0
        except ValueError:
            pass
    return fallback


def _ease_in_out_cubic(x: float) -> float:
    """Ease in and out (matching themes/forge/presence.js) so icon changes start and end gently."""
    x = max(0.0, min(1.0, x))
    return 4.0 * x * x * x if x < 0.5 else 1.0 - ((-2.0 * x + 2.0) ** 3) / 2.0


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def has_dispatch_bake(pack: dict | None) -> bool:
    """True once a flipbook pack (e.g. Nova) includes the baked 'dispatch' icon from the forge."""
    if not isinstance(pack, dict) or pack.get("kind") != "flipbook":
        return False
    spec = (pack.get("icons") or {}).get("dispatch")
    return isinstance(spec, dict) and isinstance(spec.get("_image_path"), str) and os.path.isfile(spec["_image_path"])


# The activities that show the "find" state: file search tools, search commands, and WoW waypoints.
FIND_ACTIVITIES = ("Grep", "Glob", "find", "waypoint")
# The activities that show the "write" state (Nova quill fountain pen; Devs quill).
WRITE_ACTIVITIES = ("Edit", "Write", "NotebookEdit")


def map_overlay_state(scene) -> str:
    """Resolve overlay Scene state + activity into FORMAT.md's canonical state names."""
    if getattr(scene, "state", None) == "thinking" and hasattr(scene, "dispatch_active") and scene.dispatch_active(scene.last):
        if not (hasattr(scene, "dispatch_leaving") and scene.dispatch_leaving(scene.last)):
            return "send"
    if scene.home:
        return "rest"
    if scene.reading is not None or scene.view is not None:
        return "open"
    s = scene.state
    if s == "permission":
        return "waiting"
    if s == "thinking":
        act = scene.activity
        if act in ("WebSearch", "WebFetch"):
            return "search"
        if act in ("t3_thread_send", "t3_thread_launch", "handoff"):
            return "send"
        if act == "timer":
            return "timer"
        if act in FIND_ACTIVITIES:
            return "find"
        if act in WRITE_ACTIVITIES:
            return "write"
        if act in ("show", "open_media", "aperture"):
            return "open"
        return "thinking"
    if s in ("listening", "transcribing", "speaking", "error"):
        return s
    return "rest"


def state_level_for_scene(pack: dict, state: str, scene) -> float:
    """Pick the voice level ("in" = the owner's mic level, "out" = Rook's outgoing speech level)."""
    st = (pack.get("states") or {}).get(state)
    kind = st.get("level") if isinstance(st, dict) else None
    if kind == "in":
        return max(0.0, min(1.0, float(getattr(scene, "level", 0.0))))
    if kind == "out":
        # Prefer the fast syllable envelope (min(1, said) ** 0.55 with 40 ms attack / 120 ms release) when live
        # outgoing speech levels are arriving; fall back to scene.voice when no levels were sent recently.
        if (float(getattr(scene, "last", 0.0)) - float(getattr(scene, "level_at", float("-inf")))) < 0.3:
            return max(0.0, min(1.0, float(getattr(scene, "env", 0.0))))
        return max(0.0, min(1.0, float(getattr(scene, "voice", 0.0))))
    return 0.0


class FlipbookPresence:
    """Deterministic state, cycle, alternation, intro/tips/sprite, voice-layer, label, and transition scheduler."""

    def __init__(self, pack: dict):
        self.pack = pack
        self.icons = pack.get("icons", {})
        self.states = pack.get("states", {})
        self.palette = pack.get("palette", {})
        self.transition = pack.get("transition") or {"seconds": 0.28, "from_scale": 0.85, "to_scale": 0.92}
        th = self.states.get("thinking") or {}
        self.rook = th.get("rook", "rook") if isinstance(th, dict) else "rook"
        self.think_turn = float(th.get("turn", 3.0)) if isinstance(th, dict) else 3.0
        self.thinkers = [n for n, spec in self.icons.items() if spec.get("think") and n != self.rook]
        # CP7 anchors: rest icon, any icon whose intro.from is rest, and that intro sit at rest_dy; others sit at 0.
        rest_icon = self.states.get("rest") if isinstance(self.states.get("rest"), str) else "rest"
        self.rest_set: set[str] = {rest_icon}
        for iname, spec in self.icons.items():
            intro = spec.get("intro") if isinstance(spec, dict) else None
            if isinstance(intro, dict) and intro.get("from") == rest_icon:
                self.rest_set.add(iname)
                if isinstance(intro.get("icon"), str):
                    self.rest_set.add(intro["icon"])
        self.state: str | None = None
        self.state_at = 0.0
        self.turns: dict[str, int] = {}
        self.label = ""
        self.cur: dict | None = None
        self.prev: dict | None = None
        self.set_state("rest", 0.0)

    def _duration(self, name: str) -> float:
        spec = self.icons.get(name) or {}
        return float(spec.get("frames", 24)) / max(1.0, float(spec.get("fps", 12)))

    def _clock(self, entry: dict, now: float) -> float:
        t = max(0.0, now - float(entry["at"]))
        if entry.get("reverse"):
            return max(0.0, self._duration(entry["name"]) - t - 1e-3)
        return t

    def _state_supported(self, state: str) -> bool:
        st = self.states.get(state)
        if isinstance(st, str):
            return (not self.icons) or st in self.icons
        if isinstance(st, dict):
            if isinstance(st.get("icon"), str):
                return (not self.icons) or st["icon"] in self.icons
            if isinstance(st.get("cycle"), list) and st["cycle"]:
                return (not self.icons) or any(c in self.icons for c in st["cycle"])
            if isinstance(st.get("rook"), str):
                return (not self.icons) or st["rook"] in self.icons
        return False

    def set_state(self, state: str, now: float):
        if not self._state_supported(state) and "thinking" in self.states:
            state = "thinking"  # One rule for every state a pack lacks (find, write, search, etc.): fall back to thinking.
        if state != self.state:
            self.state = state
            self.state_at = now
            self.turns[state] = self.turns.get(state, -1) + 1
        self.advance(now)

    def _change(self, want: str, now: float):
        """Transition toward icon `want`, using forward/reverse one-shot intro when declared (FORMAT.md)."""
        w_spec = self.icons.get(want) or {}
        wi = w_spec.get("intro") if isinstance(w_spec, dict) else None
        cur_target = self.cur["target"] if self.cur else None
        c_spec = self.icons.get(cur_target) if cur_target else None
        ci = c_spec.get("intro") if isinstance(c_spec, dict) else None
        self.prev = self.cur
        if (isinstance(wi, dict) and isinstance(wi.get("icon"), str)
                and wi["icon"] in self.icons and cur_target == wi.get("from")):
            self.cur = {"name": wi["icon"], "at": now, "target": want, "fade": 0.12, "quiet": True, "reverse": False}
        elif (isinstance(ci, dict) and isinstance(ci.get("icon"), str)
                and ci["icon"] in self.icons and want == ci.get("from")):
            self.cur = {"name": ci["icon"], "at": now, "target": want, "fade": 0.15, "quiet": True, "reverse": True}
        else:
            self.cur = {"name": want, "at": now, "target": want, "fade": None, "quiet": False, "reverse": False}

    def advance(self, now: float):
        """Update cur/prev icon transitions and complete any finished one-shot intro."""
        want = self.pick(now)
        if self.cur is None:
            self.cur = {"name": want, "at": now, "target": want, "fade": None, "quiet": False, "reverse": False}
        elif want != self.cur["target"]:
            self._change(want, now)
        if self.cur["name"] != self.cur["target"]:
            dur = self._duration(self.cur["name"])
            if now - float(self.cur["at"]) >= dur:
                back = bool(self.cur.get("reverse"))
                self.prev = self.cur
                self.cur = {
                    "name": self.cur["target"],
                    "at": now,
                    "target": self.cur["target"],
                    "fade": 0.15 if back else 0.0,
                    "quiet": True,
                    "reverse": False,
                }

    def pick(self, now: float) -> str:
        st = self.states.get(self.state, self.state)
        if self.state == "thinking":
            turn = max(0, int((now - self.state_at) / max(0.2, self.think_turn)))
            if turn % 2 == 0 or not self.thinkers:
                return self.rook
            return self.thinkers[(turn // 2) % len(self.thinkers)]
        if isinstance(st, dict):
            cycle = st.get("cycle")
            if cycle:
                return str(cycle[self.turns.get(self.state, 0) % len(cycle)])
            return str(st.get("icon", "rest"))
        return str(st)

    def changing(self, now: float) -> bool:
        """True while a crossfade, flash one-shot, or intro/reverse-intro is active (holds overlay at 60 fps)."""
        if self.cur is None:
            return False
        if self.cur["name"] != self.cur["target"]:
            return True
        if self.prev is None:
            return False
        tr = self.transition
        quiet = bool(self.cur.get("quiet"))
        span = float(tr.get("seconds", 0.45)) if self.cur.get("fade") is None else float(self.cur["fade"])
        flash_name = tr.get("flash")
        flash_end = 0.0
        if not quiet and flash_name and flash_name in self.icons:
            flash_end = float(tr.get("flash_at", 0.0)) + self._duration(flash_name)
        return max(0.0, now - float(self.cur["at"])) < max(span, flash_end)

    def _state_voiced(self) -> bool:
        st = self.states.get(self.state)
        return isinstance(st, dict) and bool(st.get("level") or st.get("voice"))

    @staticmethod
    def _frame_at(spec: dict, seconds: float) -> int:
        frames = max(1, int(spec.get("frames", 24)))
        fps = float(spec.get("fps", 12))
        f = int(math.floor(max(0.0, seconds) * fps))
        if spec.get("loop", True) is False:
            return min(f, frames - 1)
        return f % frames

    def _icon_quads(self, name: str, elapsed: float, alpha: float, scale: float, level: float,
                    use_voice: bool, additive: bool = False, tip_levels: dict | None = None, dy: float = 0.0):
        if alpha <= 0.002:
            return []
        spec = self.icons.get(name)
        if not spec or "_image_path" not in spec:
            return []
        layers = spec.get("layers") or ["main"]
        frames = max(1, int(spec.get("frames", 24)))
        frame = self._frame_at(spec, elapsed)
        cols, rows = spec.get("grid", [1, 1])
        cell = int(spec.get("cell", 256))
        pivot = tuple(spec.get("pivot", [0.5, 0.5]))
        # CP3/CP6 FORMAT.md: voice reactions under spec["voice"][layer], tip layers under spec["tips"][layer].
        voice_layers = (spec.get("voice") or {}) if (use_voice and self._state_voiced()) else {}
        tips_cfg = spec.get("tips") or {}
        out = []
        for l_idx, l_name in enumerate(layers):
            la, ls, stretch = alpha, scale, 1.0
            if isinstance(tips_cfg, dict) and l_name in tips_cfg:
                tip = tips_cfg[l_name]
                side = int(tip.get("side", 1)) if isinstance(tip, dict) else 1
                la *= float((tip_levels or {}).get(side, 0.0))
            else:
                cfg = voice_layers.get(l_name) if isinstance(voice_layers, dict) else None
                if isinstance(cfg, dict):
                    op = cfg.get("opacity")
                    sc = cfg.get("scale")
                    st = cfg.get("stretch")
                    if op:
                        la *= _lerp(float(op[0]), float(op[1]), level)
                    if sc:
                        ls *= _lerp(float(sc[0]), float(sc[1]), level)
                    if st:
                        stretch *= _lerp(float(st[0]), float(st[1]), level)
            if la <= 0.002:
                continue
            cell_idx = l_idx * frames + frame
            out.append({
                "icon": name,
                "path": spec["_image_path"],
                "cols": int(cols),
                "rows": int(rows),
                "cell": cell,
                "cell_idx": cell_idx,
                "pivot": pivot,
                "alpha": float(la),
                "scale": float(ls),
                "stretch": float(stretch),
                "additive": additive,
                "angle": 0.0,
                "offset": (0.0, 0.0),
                "dy": float(dy),
                "size_px": None,
                "label": spec.get("label") if l_idx == 0 else None,
            })
        return out

    def sprite_quad(self, name: str, elapsed: float, offset: tuple[float, float],
                    size_px: float, angle: float, alpha: float = 1.0) -> dict | None:
        """Build one rotated sprite quad (e.g. strand_head turned along a dispatch Bézier tangent)."""
        if alpha <= 0.002:
            return None
        spec = self.icons.get(name)
        if not spec or "_image_path" not in spec:
            return None
        cols, rows = spec.get("grid", [1, 1])
        cell = int(spec.get("cell", 64))
        pivot = tuple(spec.get("pivot", [0.5, 0.5]))
        frame = self._frame_at(spec, elapsed)
        return {
            "icon": name,
            "path": spec["_image_path"],
            "cols": int(cols),
            "rows": int(rows),
            "cell": cell,
            "cell_idx": frame,
            "pivot": pivot,
            "alpha": float(alpha),
            "scale": 1.0,
            "stretch": 1.0,
            "additive": False,
            "angle": float(angle),
            "offset": (float(offset[0]), float(offset[1])),
            "size_px": float(size_px),
            "label": None,
        }

    def dispatch_tip_at(self) -> dict[int, tuple[float, float]]:
        """Normalized [x, y] tip origins for side +1 (right) and -1 (left) from icons.dispatch.tips."""
        spec = self.icons.get("dispatch") or {}
        tips = spec.get("tips") if isinstance(spec, dict) else None
        out = {1: (0.83, 0.5), -1: (0.17, 0.5)}
        if isinstance(tips, dict):
            for cfg in tips.values():
                if isinstance(cfg, dict) and isinstance(cfg.get("at"), list) and len(cfg["at"]) == 2:
                    side = int(cfg.get("side", 1))
                    out[side] = (float(cfg["at"][0]), float(cfg["at"][1]))
        return out

    def draw_list(self, now: float, level: float = 0.0, tip_levels: dict | None = None,
                  rest_dy: float = 0.0) -> list[dict]:
        """Return ordered quad draw commands with per-icon anchors (dy), cubic crossfades, intros, and premultiplied flash."""
        self.advance(now)
        cur = self.cur
        tr = self.transition
        quiet = bool(cur.get("quiet"))
        span = float(tr.get("seconds", 0.45)) if cur.get("fade") is None else float(cur["fade"])
        from_sc = 1.0 if quiet else float(tr.get("from_scale", 0.88))
        to_sc = 1.0 if quiet else float(tr.get("to_scale", 0.90))
        elapsed_cur = max(0.0, now - float(cur["at"]))
        f = _ease_in_out_cubic(elapsed_cur / span) if (self.prev is not None and span > 0.0) else 1.0
        dy_c = float(rest_dy if cur["name"] in self.rest_set else 0.0)
        dy_p = float(rest_dy if (self.prev is not None and self.prev["name"] in self.rest_set) else 0.0)
        quads = []
        if quiet:
            # Intro handoff joins two matching shapes: draw new icon at full strength under old fading out (no dip).
            quads.extend(self._icon_quads(cur["name"], self._clock(cur, now), 1.0, 1.0, level,
                                          use_voice=True, tip_levels=tip_levels, dy=dy_c))
            if self.prev is not None and f < 1.0:
                quads.extend(self._icon_quads(self.prev["name"], self._clock(self.prev, now), 1.0 - f,
                                              1.0, level, use_voice=False, tip_levels=tip_levels, dy=dy_p))
        else:
            if self.prev is not None and f < 1.0:
                quads.extend(self._icon_quads(self.prev["name"], self._clock(self.prev, now), 1.0 - f,
                                              _lerp(1.0, from_sc, f), level, use_voice=False,
                                              tip_levels=tip_levels, dy=dy_p))
            quads.extend(self._icon_quads(cur["name"], self._clock(cur, now), f,
                                          _lerp(to_sc, 1.0, f), level, use_voice=True,
                                          tip_levels=tip_levels, dy=dy_c))
            flash_name = tr.get("flash")
            if flash_name and self.prev is not None:
                fspec = self.icons.get(flash_name)
                if fspec:
                    dur = self._duration(flash_name)
                    ft = elapsed_cur - float(tr.get("flash_at", 0.0))
                    f_scale = float(tr.get("flash_scale", 1.0))
                    if 0.0 <= ft < dur:
                        # CP7 FORMAT.md: draw flash premultiplied OVER (not additive) so ink edges darken on light.
                        quads.extend(self._icon_quads(flash_name, ft, 1.0, f_scale, 0.0,
                                                      use_voice=False, additive=False, dy=dy_c))
        return quads

    def live_icon_names(self) -> set[str]:
        """Protected icon names that must not be evicted mid-draw (current, previous, target, flash, and dispatch)."""
        keep = set()
        if self.cur:
            keep.add(self.cur["name"])
            keep.add(self.cur["target"])
        if self.prev:
            keep.add(self.prev["name"])
        fl = self.transition.get("flash")
        if fl:
            keep.add(fl)
        if self.state == "send" or (self.cur and self.cur["target"] == "dispatch"):
            for n in ("dispatch", "dispatch_in", "strand_head"):
                if n in self.icons:
                    keep.add(n)
        return keep

    def peek_next_path(self, now: float) -> str | None:
        """Look ahead so the next icon decodes off-thread before handoff (e.g. dispatch during dispatch_in, or thinkers)."""
        if self.cur and self.cur["name"] != self.cur["target"]:
            spec = self.icons.get(self.cur["target"])
            if isinstance(spec, dict) and spec.get("_image_path"):
                return spec["_image_path"]
        if self.state != "thinking" or not self.thinkers:
            return None
        nxt = self.pick(now + 0.8)
        if self.cur and nxt == self.cur["target"]:
            return None
        spec = self.icons.get(nxt)
        return spec.get("_image_path") if isinstance(spec, dict) else None

    def prefetch_warm(self):
        """Queue current icon, flash, rook, and tiny dispatch intro/head sprites for off-thread decode."""
        ordered = []
        if self.cur:
            ordered.append(self.cur["name"])
        fl = self.transition.get("flash")
        if fl:
            ordered.append(fl)
        if self.rook:
            ordered.append(self.rook)
        for n in ("dispatch_in", "strand_head"):
            if n in self.icons:
                ordered.append(n)
        for name in ordered:
            spec = self.icons.get(name)
            if spec and "_image_path" in spec:
                ATLAS_LOADER.prefetch(spec["_image_path"])


class CairoFlipbookPlayer:
    """Cairo renderer for flipbook packs (offscreen previews and fallback), matching the GL quad player."""

    def __init__(self):
        self._surfaces: dict[str, cairo.ImageSurface] = {}

    def _surface(self, path: str) -> cairo.ImageSurface:
        if path not in self._surfaces:
            self._surfaces[path] = load_premultiplied_surface(path)
        return self._surfaces[path]

    def trim(self, keep_paths: set[str]):
        for p in list(self._surfaces):
            if p not in keep_paths:
                del self._surfaces[p]

    @staticmethod
    def _draw_label(cr: cairo.Context, text: str, label_spec: dict, palette: dict,
                    cx: float, cy: float, size: float, scale: float, alpha: float):
        if not text or alpha <= 0.01:
            return
        shown = text if len(text) <= 22 else text[:21] + "…"
        ax, ay = label_spec.get("at", [0.5, 0.93])
        px = max(10.0, float(label_spec.get("size", 0.085)) * size)
        tx = cx + (float(ax) - 0.5) * size * scale
        ty = cy + (float(ay) - 0.5) * size * scale
        ink = _hex_rgb(palette.get("ink", "#150B33"), (0.08, 0.04, 0.2))
        core = _hex_rgb(palette.get("core", "#FFF4FF"), (1.0, 0.96, 1.0))
        cr.save()
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(px)
        ext = cr.text_extents(shown)
        x = tx - (ext.x_bearing + ext.width / 2.0)
        y = ty - (ext.y_bearing + ext.height / 2.0)
        cr.move_to(x, y)
        cr.text_path(shown)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_width(px * 0.28)
        cr.set_source_rgba(*ink, alpha)
        cr.stroke_preserve()
        cr.set_source_rgba(*core, alpha)
        cr.fill()
        cr.restore()

    def draw_quads(self, cr: cairo.Context, quads: list[dict], cx: float, cy: float, size: float) -> set[str]:
        """Draw a list of icon/sprite quads (supporting pivot, stretch, offset, and rotation) onto a Cairo context."""
        keep_paths = set()
        for q in quads:
            path = q["path"]
            keep_paths.add(path)
            surf = self._surface(path)
            cell = q["cell"]
            cols = q["cols"]
            sx = (q["cell_idx"] % cols) * cell
            sy = (q["cell_idx"] // cols) * cell
            base = float(q["size_px"]) if q.get("size_px") is not None else size
            draw_w = base * q["scale"]
            draw_h = draw_w * q["stretch"]
            px, py = q["pivot"]
            ox, oy = q.get("offset") or (0.0, 0.0)
            qdy = float(q.get("dy", 0.0))
            angle = float(q.get("angle", 0.0))
            cr.save()
            cr.set_operator(cairo.OPERATOR_ADD if q["additive"] else cairo.OPERATOR_OVER)
            cr.translate(cx + ox, cy + qdy + oy)
            if angle:
                cr.rotate(angle)
            cr.translate(-draw_w * px, -draw_h * py)
            cr.scale(draw_w / cell, draw_h / cell)
            cr.rectangle(0, 0, cell, cell)
            cr.clip()
            cr.set_source_surface(surf, -sx, -sy)
            cr.get_source().set_filter(cairo.FILTER_BILINEAR)
            if q["alpha"] < 0.999:
                cr.paint_with_alpha(q["alpha"])
            else:
                cr.paint()
            cr.restore()
        return keep_paths

    def draw(self, cr: cairo.Context, presence: FlipbookPresence, cx: float, cy: float,
             size: float, now: float, level: float = 0.0, tip_levels: dict | None = None,
             extra_quads: list[dict] | None = None, rest_dy: float = 0.0):
        quads = presence.draw_list(now, level, tip_levels=tip_levels, rest_dy=rest_dy)
        keep_paths = self.draw_quads(cr, quads, cx, cy, size)
        if extra_quads:
            keep_paths.update(self.draw_quads(cr, extra_quads, cx, cy, size))
        for q in quads:
            if q["label"] and presence.label:
                self._draw_label(cr, presence.label, q["label"], presence.palette, cx,
                                 cy + float(q.get("dy", 0.0)), size, q["scale"], q["alpha"])
        for name in presence.live_icon_names():
            spec = presence.icons.get(name)
            if spec and "_image_path" in spec:
                keep_paths.add(spec["_image_path"])
        self.trim(keep_paths)
