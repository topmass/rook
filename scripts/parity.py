#!/usr/bin/env python3
"""Parity checker for Rook: capture and compare the full agent-visible surface of two trees.

Usage:
  scripts/parity.py REF_TREE NEW_TREE [--only SECTION] [--expect-change SECTION[:PROFILE]] [--json OUT]
                    [--owner-settings FILE]
  scripts/parity.py --capture TREE --out DIR [--only SECTION]
  scripts/parity.py --check

Sections (1 to 7):
  1 / prompts  - System prompt and setup turn for Claude Code, Antigravity, and Codex
  2 / launch   - Launch argv, env delta, cwd, and generated files/policy per agent
  3 / skills   - Skill list and rendered skill files per agent
  4 / hook     - antigravity_home.py guard decisions across a fixed command suite
  5 / relay    - relay.py --help and safe offline command outputs
  6 / servers  - MCP tool servers: names, commands/URLs, env, denied/enabled, eager tools
  7 / timings  - Warmed ABBA median + IQR of relay.py --help (20x) and hook (40x), calibrated band
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import difflib
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import textwrap
import threading
import time


ALL_SECTIONS = ("prompts", "launch", "skills", "hook", "relay", "servers", "timings")
PARITY_SECTIONS = ("prompts", "launch", "skills", "hook", "relay", "servers")
SECTION_ALIASES = {
    "1": "prompts", "prompts": "prompts",
    "2": "launch", "launch": "launch",
    "3": "skills", "skills": "skills",
    "4": "hook", "hook": "hook",
    "5": "relay", "relay": "relay",
    "6": "servers", "servers": "servers",
    "7": "timings", "timings": "timings",
}
HYPR_SIGNATURE = "parity-hypr"
HYPR_STANDIN_REPLIES = {
    "activewindow": {
        "address": "0x1",
        "class": "foot",
        "title": "shell",
        "monitor": 0,
        "size": [1000, 800],
        "stableId": "win-narrow",
    },
    "monitors": [
        {"id": 0, "name": "DP-1", "scale": 1.5, "activeWorkspace": {"id": 1}, "solitaryBlockedBy": []},
    ],
    "clients": [],
    "workspaces": [{"id": 1, "name": "1", "monitor": "DP-1"}],
    "activeworkspace": {"id": 1, "name": "1", "monitor": "DP-1"},
    "version": {"branch": "main", "commit": "parity", "tag": "v0.0.0"},
}

OMARCHY_STUBS = ("omarchy-launch-browser", "omarchy-cmd-terminal-cwd")
OMARCHY_SKILL_STUB = (
    "---\n"
    "name: omarchy\n"
    "description: Stand-in host Omarchy desktop skill for parity testing.\n"
    "---\n\n"
    "# Omarchy (parity stand-in)\n"
)

# Exact system programs linked into scratch sys-bin so PATH never inherits the caller's PATH
# (and never leaks host omarchy-* commands from /usr/bin or ~/.local/bin).
SYSTEM_FIXED_BINARIES = ("python", "python3", "sh", "bash", "env", "git")
SYSTEM_OPTIONAL_BINARIES = ("uv", "dcg")

# Declarative profile table: each profile declares its desktop, skills, PATH stubs, and settings.
PROFILE_SPECS: dict[str, dict] = {
    "owner": {
        "desktop": "omarchy-hyprland",
        "hyprland": True,
        "omarchy": True,
        "wow": True,
        "exclude_wow_dir": False,
        "settings_kind": "owner",
    },
    "stranger": {
        "desktop": "none",
        "hyprland": False,
        "omarchy": False,
        "wow": False,
        "exclude_wow_dir": False,
        "settings_kind": "stranger",
    },
    "no-wow": {
        "desktop": "omarchy-hyprland",
        "hyprland": True,
        "omarchy": True,
        "wow": False,
        "exclude_wow_dir": True,
        "settings_kind": "owner",
    },
    "hyprland-plain": {
        "desktop": "hyprland",
        "hyprland": True,
        "omarchy": False,
        "wow": False,
        "exclude_wow_dir": False,
        "settings_kind": "stranger",
    },
}
PROFILES = tuple(PROFILE_SPECS.keys())
_TIMING_PROFILE_SPEC = {
    "desktop": "none",
    "hyprland": False,
    "omarchy": False,
    "wow": False,
    "exclude_wow_dir": False,
    "settings_kind": "stranger",
}

GUARD_BINARIES = (
    "systemctl", "t3", "gh", "tailscale", "pw-play", "pactl",
    "hyprctl", "grim", "claude", "agy", "codex", "herdr", "pi",
)

STRIPPED_ENV_VARS = (
    "T3CODE_THREAD_ID",
    "ROOK_AGENT",
    "WAYLAND_DISPLAY",
    "DISPLAY",
    "HYPRLAND_INSTANCE_SIGNATURE",
    "XDG_CURRENT_DESKTOP",
    "XDG_SESSION_DESKTOP",
    "PULSE_SERVER",
    "PIPEWIRE_REMOTE",
    "DBUS_SESSION_BUS_ADDRESS",
    "ROOK_MEDIUM_VOICE_URL",
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
)

FIXED_SESSION_ID = "00000000-0000-4000-8000-000000000000"
FAKE_T3_HOST = "127.0.0.1"
FAKE_T3_PORT = 39999
FAKE_T3_URL = f"http://{FAKE_T3_HOST}:{FAKE_T3_PORT}/mcp"

OWNER_MACHINES = {
    "desk-a": {
        "environmentId": "env-desk-a",
        "run": [],
        "t3": "t3",
        "code": "/tmp/example-code",
    },
    "desk-b": {
        "environmentId": "env-desk-b",
        "run": ["ssh", "desk-b.example.invalid"],
        "t3": "t3",
        "code": "/tmp/example-code",
    },
}

STRANGER_MACHINES = {
    "desk-a": {
        "environmentId": "",
        "run": [],
        "t3": "t3",
        "code": "/tmp/example-code",
    },
}

OWNER_CANDIDATE_SETTINGS = {
    "medium_voice_url": "https://voice.example.invalid:8090",
    "github_user": "example-user",
    "build_threads": {
        "alpha": "mcp:00000000-0000-4000-8000-000000000001",
        "beta": "mcp:00000000-0000-4000-8000-000000000002",
        "gamma": "mcp:00000000-0000-4000-8000-000000000003",
    },
    "owner_name": "Alex",
    "owner_pronouns": ["they/them", "they", "he/him", "he"],
    "pronouns": ["they/them", "they", "he/him", "he"],
    "permission_mode": "automatic",
}

# --owner-settings FILE: an owner's own settings for the owner profiles of the new tree, read at run time from a
# file outside the repository, so they never enter it. They are written into that profile's settings file as given.
OWNER_OVERRIDES: dict = {}

OWNER_PERSONALITY = "2026-01-01: Keep answers crisp and direct.\n"
OWNER_MODEL_PREFERENCES = "# Routing\nBuild thread: Alpha\n"

NORMALISED_ITEMS = [
    "tree root path -> <ROOT>",
    "scratch folder path -> <SCRATCH>",
    "resolved uv binary path -> <UV>",
    "fixed synthetic session id -> <SESSION_ID>",
    "random setup-turn UUID omitted (only setup text is compared)",
    "dictionary keys and directory listings sorted",
]

PYTHON3 = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
TIMING_WARMUP_RUNS = 3
TIMING_RELAY_BLOCKS = 10  # 10 ABBA blocks = 20 measured runs per tree
TIMING_HOOK_BLOCKS = 20   # 20 ABBA blocks = 40 measured runs per tree (cheaper hook gets more rounds)
TIMING_SELF_BAND = 0.03   # Calibrated self-comparison band (0.97..1.03); also drives warning threshold
DIFF_MAX_LINES = 40
DIFF_MAX_LINE_CHARS = 300


def _run_blocking_wait(
    cmd: list[str],
    *,
    input_bytes: bytes | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
    timeout: float = 30.0,
) -> tuple[int, bytes, bytes, float]:
    """Run cmd with blocking waitpid() + Timer safety timeout.

    Python's subprocess.run(..., timeout=...) uses a polling sleep loop (up to 50ms steps)
    inside Popen._wait, which quantizes short timings onto 50ms buckets. Waiting without a
    subprocess timeout uses blocking waitpid() while a Timer still enforces the deadline.
    """
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        cwd=cwd,
        env=env,
    )
    timed_out = False

    def _kill() -> None:
        nonlocal timed_out
        timed_out = True
        try:
            proc.kill()
        except OSError:
            pass

    timer = threading.Timer(timeout, _kill)
    timer.start()
    try:
        if capture:
            out_b, err_b = proc.communicate(input=input_bytes)
            rc = proc.returncode
        else:
            if input_bytes is not None:
                assert proc.stdin is not None
                try:
                    proc.stdin.write(input_bytes)
                except BrokenPipeError:
                    pass
                proc.stdin.close()
            rc = proc.wait()
            out_b, err_b = b"", b""
    finally:
        timer.cancel()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if timed_out:
        raise subprocess.TimeoutExpired(cmd, timeout)
    return rc, out_b, err_b, elapsed_ms


def parse_section_name(raw: str) -> str:
    key = raw.strip().lower()
    if key not in SECTION_ALIASES:
        raise ValueError(f"Unknown section {raw!r}. Valid: {', '.join(ALL_SECTIONS)} (or 1..7).")
    return SECTION_ALIASES[key]


def parse_expect_spec(raw: str) -> tuple[str, str | None]:
    if ":" in raw:
        sec_raw, prof_raw = raw.split(":", 1)
        sec = parse_section_name(sec_raw)
        prof = prof_raw.strip().lower()
        if prof not in PROFILES:
            raise ValueError(f"Unknown profile {prof_raw!r} in {raw!r}. Valid: {', '.join(PROFILES)}.")
        return sec, prof
    return parse_section_name(raw), None


def is_captured_dir(path: Path) -> bool:
    return path.is_dir() and (path / "surface.json").is_file() and not (path / "desktop/rook.py").is_file()


def normalise_text(text: str, replacements: list[tuple[str, str]]) -> str:
    for old, new in replacements:
        if old:
            text = text.replace(old, new)
    return text


def normalise_obj(obj, replacements: list[tuple[str, str]]):
    if isinstance(obj, str):
        return normalise_text(obj, replacements)
    if isinstance(obj, list):
        return [normalise_obj(item, replacements) for item in obj]
    if isinstance(obj, tuple):
        return [normalise_obj(item, replacements) for item in obj]
    if isinstance(obj, dict):
        return {
            normalise_text(str(k), replacements): normalise_obj(v, replacements)
            for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))
        }
    return obj


def build_replacements(tree: Path, scratch_root: Path, uv_path: str | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for p, token in (
        (str(tree.resolve()), "<ROOT>"),
        (os.path.realpath(str(tree)), "<ROOT>"),
        (str(tree), "<ROOT>"),
        (str(scratch_root.resolve()), "<SCRATCH>"),
        (os.path.realpath(str(scratch_root)), "<SCRATCH>"),
        (str(scratch_root), "<SCRATCH>"),
    ):
        if p and (p, token) not in pairs:
            pairs.append((p, token))
    if uv_path:
        for p in dict.fromkeys((os.path.realpath(uv_path), uv_path)):
            if p and not p.startswith(("/usr/bin/", "/bin/")):
                pairs.append((p, "<UV>"))
            elif p:
                pairs.append((p, "<UV>"))
    pairs.append((FIXED_SESSION_ID, "<SESSION_ID>"))
    # Longest patterns first so more specific paths match before shorter prefixes.
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


def copy_tree(src: Path, dst: Path, *, exclude_wow: bool = False) -> None:
    """Copy a repository tree to dst, excluding .git and __pycache__ (and top-level wow/ when requested)."""
    src_resolved = src.resolve()

    def _ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {n for n in names if n in (".git", "__pycache__") or n.endswith(".pyc")}
        if exclude_wow and Path(directory).resolve() == src_resolved and "wow" in names:
            ignored.add("wow")
        return ignored

    shutil.copytree(src_resolved, dst, symlinks=True, ignore=_ignore)


class _HyprStandIn:
    """Minimal stand-in Hyprland Unix socket answering j/<cmd> queries with fixed replies."""

    def __init__(self, sock_path: Path, replies: dict | None = None):
        self.path = Path(sock_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.replies = dict(HYPR_STANDIN_REPLIES if replies is None else replies)
        self.requests: list[str] = []
        self._stop = threading.Event()
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(str(self.path))
        self._srv.listen(8)
        self._srv.settimeout(0.05)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            try:
                req = conn.recv(4096).decode(errors="replace").strip()
            except OSError:
                return
            self.requests.append(req)
            cmd = req.removeprefix("j/")
            payload = json.dumps(self.replies.get(cmd, {})).encode("utf-8")
            try:
                conn.sendall(payload)
            except OSError:
                pass

    def close(self) -> None:
        self._stop.set()
        try:
            self._srv.close()
        except OSError:
            pass
        self._thread.join(timeout=1.0)
        self.path.unlink(missing_ok=True)


def _resolve_system_binary(name: str, *, fixed_only: bool) -> str | None:
    if fixed_only:
        for d in ("/usr/bin", "/bin"):
            cand = Path(d) / name
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
        return None
    found = shutil.which(name)
    if found:
        return found
    local_cand = Path.home() / ".local/bin" / name
    if local_cand.is_file() and os.access(local_cand, os.X_OK):
        return str(local_cand)
    return None


class ScratchProfileEnv:
    """Isolated scratch HOME + all 5 XDG dirs + fixed PATH + declared desktop stand-ins."""

    def __init__(self, profile: str, parent_dir: Path | None = None, spec: dict | None = None):
        self.profile = profile
        self.spec = dict(PROFILE_SPECS.get(profile, _TIMING_PROFILE_SPEC) if spec is None else spec)
        # Keep root path short so AF_UNIX socket path stays well under Linux's 108-byte sun_path limit.
        base_dir = parent_dir if parent_dir is not None else ("/tmp" if len(tempfile.gettempdir()) > 30 else None)
        self.root = Path(tempfile.mkdtemp(prefix="rp-", dir=base_dir))
        self.home = self.root / "home"
        self.runtime = self.root / "runtime"
        self.state = self.root / "state"
        self.config = self.root / "config"
        self.data = self.root / "data"
        self.cache = self.root / "cache"
        self.workspace = self.root / "workspace"
        self.guard_bin = self.root / "guard-bin"
        self.sys_bin = self.root / "sys-bin"
        self.guard_log = self.root / "guard.log"
        self.hypr_standin: _HyprStandIn | None = None
        for folder in (
            self.home, self.runtime, self.state, self.config,
            self.data, self.cache, self.workspace, self.guard_bin, self.sys_bin,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        self.runtime.chmod(0o700)
        self._install_guard_binaries()
        self._install_system_binaries()
        self._install_desktop_standins()
        self.env = self._build_env()

    def _install_guard_binaries(self) -> None:
        log_quoted = str(self.guard_log).replace("'", "'\"'\"'")
        stubs = list(GUARD_BINARIES)
        if self.spec.get("omarchy"):
            stubs.extend(OMARCHY_STUBS)
        for name in stubs:
            script = self.guard_bin / name
            script.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\037' '{name}' \"$@\" >> '{log_quoted}'\n"
                f"printf '\\036' >> '{log_quoted}'\n"
                "exit 0\n"
            )
            script.chmod(0o755)

    def _install_system_binaries(self) -> None:
        """Link only the explicit system binaries needed by captures into sys-bin (never raw caller PATH)."""
        for name in SYSTEM_FIXED_BINARIES:
            target = _resolve_system_binary(name, fixed_only=True)
            if target:
                (self.sys_bin / name).symlink_to(target)
        for name in SYSTEM_OPTIONAL_BINARIES:
            target = _resolve_system_binary(name, fixed_only=False)
            if target:
                (self.sys_bin / name).symlink_to(target)

    def _install_desktop_standins(self) -> None:
        if self.spec.get("hyprland"):
            sock_path = self.runtime / "hypr" / HYPR_SIGNATURE / ".socket.sock"
            self.hypr_standin = _HyprStandIn(sock_path)
        if self.spec.get("omarchy"):
            # Seed host omarchy skill where Claude Code, Antigravity, and Codex look for it.
            for rel in (".agents/skills/omarchy/SKILL.md", ".claude/skills/omarchy/SKILL.md"):
                path = self.home / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(OMARCHY_SKILL_STUB)

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        for var in STRIPPED_ENV_VARS:
            env.pop(var, None)
        env.update({
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "XDG_STATE_HOME": str(self.state),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_DATA_HOME": str(self.data),
            "XDG_CACHE_HOME": str(self.cache),
            "PATH": f"{self.guard_bin}:{self.sys_bin}",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
        })
        if self.spec.get("hyprland"):
            env["HYPRLAND_INSTANCE_SIGNATURE"] = HYPR_SIGNATURE
        return env

    def reset_guard_log(self) -> None:
        self.guard_log.unlink(missing_ok=True)

    def read_guard_log(self, replacements: list[tuple[str, str]]) -> list[list[str]]:
        if not self.guard_log.is_file():
            return []
        raw = self.guard_log.read_text(errors="replace")
        calls: list[list[str]] = []
        for record in raw.split("\x1e"):
            if not record:
                continue
            parts = record.split("\x1f")
            if parts and parts[-1] == "":
                parts = parts[:-1]
            if parts:
                calls.append([normalise_text(p, replacements) for p in parts])
        return calls

    def populate(self, settings_data: dict | None, machines_data: dict, *, with_t3: bool, with_notes: bool) -> None:
        rook_cfg = self.config / "rook"
        rook_cfg.mkdir(parents=True, exist_ok=True)
        if settings_data is not None:
            (rook_cfg / "settings.json").write_text(json.dumps(settings_data, indent=2, sort_keys=True) + "\n")
        (rook_cfg / "machines.json").write_text(json.dumps(machines_data, indent=2, sort_keys=True) + "\n")
        if with_notes:
            (rook_cfg / "personality.md").write_text(OWNER_PERSONALITY)
            (rook_cfg / "model-preferences.md").write_text(OWNER_MODEL_PREFERENCES)
        if with_t3:
            t3_dir = self.home / ".t3/userdata"
            t3_dir.mkdir(parents=True, exist_ok=True)
            (t3_dir / "server-runtime.json").write_text(
                json.dumps({"host": FAKE_T3_HOST, "port": FAKE_T3_PORT}) + "\n"
            )
            agy_dir = self.home / ".gemini/antigravity-cli"
            agy_dir.mkdir(parents=True, exist_ok=True)
            (agy_dir / "mcp_oauth_tokens.json").write_text(
                json.dumps({FAKE_T3_URL: {"token": {"refresh_token": "parity-fake-token"}}}) + "\n"
            )

    def cleanup(self) -> None:
        if self.hypr_standin is not None:
            self.hypr_standin.close()
            self.hypr_standin = None
        shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> "ScratchProfileEnv":
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()


_PROBE_SETTINGS_SCRIPT = textwrap.dedent(r"""
import json
import sys
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
candidates = json.loads(sys.argv[2])
sys.path.insert(0, str(tree / "desktop"))

try:
    import settings
except Exception as exc:
    print(json.dumps({"error": f"could not import desktop/settings.py: {exc!r}"}))
    sys.exit(0)

known = set()
for attr in ("KNOWN_SETTINGS_KEYS", "SETTINGS", "CONFIG_SETTINGS", "AGENT_SETTINGS"):
    val = getattr(settings, attr, None)
    if isinstance(val, (set, frozenset, list, tuple)):
        known.update(str(k) for k in val)

valid_fn = getattr(settings, "valid", None)
chosen = {}
for key, val in candidates.items():
    if key not in known:
        continue
    options = val if isinstance(val, list) else [val]
    for opt in options:
        if callable(valid_fn):
            try:
                parsed = valid_fn({key: opt})
            except Exception:
                continue
            if key in parsed:
                chosen[key] = opt
                break
        else:
            chosen[key] = opt
            break

print(json.dumps({"known": sorted(known), "chosen": chosen}))
""")


def probe_owner_settings(tree: Path, scratch_env: ScratchProfileEnv) -> dict:
    """Learn which owner settings keys the tree's desktop/settings.py knows, in a child process."""
    res = subprocess.run(
        [PYTHON3, "-c", _PROBE_SETTINGS_SCRIPT, str(tree), json.dumps(OWNER_CANDIDATE_SETTINGS)],
        env=scratch_env.env,
        cwd=str(scratch_env.workspace),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return {}
    try:
        data = json.loads(res.stdout)
    except ValueError:
        return {}
    return data.get("chosen") if isinstance(data.get("chosen"), dict) else {}


_CAPTURE_AGENTS_SCRIPT = textwrap.dedent(r"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
from types import SimpleNamespace

tree = Path(sys.argv[1]).resolve()
workspace = Path(sys.argv[2]).resolve()
wow_enabled = sys.argv[3] == "1"
fixed_session = sys.argv[4]

# Stub Linux-only audio/input packages so desktop/rook.py imports cleanly on /usr/bin/python3
# without loading ASR/ML libraries or touching hardware.
def _install_stubs():
    if "airtype.pipeline" not in sys.modules:
        airtype_pkg = types.ModuleType("airtype")
        airtype_pipe = types.ModuleType("airtype.pipeline")
        airtype_pipe.AirtypePipeline = None
        airtype_pkg.pipeline = airtype_pipe
        sys.modules["airtype"] = airtype_pkg
        sys.modules["airtype.pipeline"] = airtype_pipe
    if "evdev" not in sys.modules:
        evdev_mod = types.ModuleType("evdev")
        evdev_mod.InputDevice = None
        evdev_mod.ecodes = None
        evdev_mod.list_devices = lambda: []
        sys.modules["evdev"] = evdev_mod

_install_stubs()
sys.path.insert(0, str(tree / "desktop"))
os.chdir(workspace)

out = {
    "prompts": {},
    "launch": {},
    "skills": {},
    "servers": {},
    "errors": {},
}

try:
    import rook
    import harness
except Exception as exc:
    out["errors"]["import"] = f"failed importing rook/harness: {type(exc).__name__}: {exc}"
    print(json.dumps(out))
    sys.exit(0)

def _load_optional_module(name):
    path = tree / "desktop" / f"{name}.py"
    if not path.is_file():
        return None, f"{name}.py missing"
    try:
        if name in sys.modules:
            return sys.modules[name], None
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

agy_harness, agy_err = _load_optional_module("agy_harness")
antigravity_home, agy_home_err = _load_optional_module("antigravity_home")
codex_harness, codex_err = _load_optional_module("codex_harness")

def _list_tree(root_dir):
    root = Path(root_dir)
    if not root.exists():
        return None
    entries = []
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if "__pycache__" in p.parts:
            continue
        if p.is_symlink():
            entries.append({"path": rel, "type": "symlink", "target": os.readlink(p)})
        elif p.is_dir():
            entries.append({"path": rel, "type": "dir"})
        else:
            entries.append({"path": rel, "type": "file"})
    return entries

def _read_skills_dir(skills_root):
    root = Path(skills_root)
    if not root.is_dir():
        return {"names": [], "files": {}}
    names = []
    files = {}
    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        if (entry / "SKILL.md").is_file():
            names.append(entry.name)
        skill_files = {}
        for f in sorted(entry.rglob("*")):
            if not f.is_file() or "__pycache__" in f.parts:
                continue
            rel = str(f.relative_to(entry))
            try:
                skill_files[rel] = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                skill_files[rel] = f"<binary:{f.stat().st_size}>"
        files[entry.name] = skill_files
    return {"names": sorted(names), "files": files}

def _read_json_if_file(path):
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": repr(exc)}

def _read_text_if_file(path):
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception as exc:
        return f"<read_error:{exc!r}>"

def _env_delta(baseline, actual):
    if actual is None:
        return {"added_or_changed": {}, "removed": []}
    added = {k: actual[k] for k in sorted(actual) if baseline.get(k) != actual[k]}
    removed = sorted(k for k in baseline if k not in actual)
    return {"added_or_changed": added, "removed": removed}

def _policy_snapshot(mod, names):
    if mod is None:
        return None
    snap = {}
    for attr in names:
        if not hasattr(mod, attr):
            continue
        val = getattr(mod, attr)
        if isinstance(val, (set, frozenset)):
            snap[attr] = sorted(str(x) for x in val)
        elif isinstance(val, tuple):
            snap[attr] = list(val)
        elif isinstance(val, dict):
            snap[attr] = {
                str(k): (list(v) if isinstance(v, (tuple, set, frozenset)) else v)
                for k, v in sorted(val.items(), key=lambda kv: str(kv[0]))
            }
        else:
            snap[attr] = val
    return snap

# Shared skill_sources metadata (if present in this tree)
if hasattr(harness, "skill_sources"):
    try:
        out["skills"]["shared_sources"] = [str(p) for p in harness.skill_sources(wow=wow_enabled)]
    except Exception as exc:
        out["skills"]["shared_sources"] = {"unavailable": repr(exc)}
else:
    out["skills"]["shared_sources"] = None

async def capture_all():
    baseline_env = dict(os.environ)
    real_exec = asyncio.create_subprocess_exec

    for kind in ("claude", "antigravity", "codex"):
        if kind == "claude":
            h = harness.Claude()
        elif kind == "antigravity":
            if agy_harness is None:
                msg = f"unavailable: {agy_err}"
                for sec in ("prompts", "launch", "skills", "servers"):
                    out[sec][kind] = {"unavailable": msg}
                continue
            h = agy_harness.Antigravity()
        else:
            if codex_harness is None:
                msg = f"unavailable: {codex_err}"
                for sec in ("prompts", "launch", "skills", "servers"):
                    out[sec][kind] = {"unavailable": msg}
                continue
            h = codex_harness.Codex()

        launched = []
        written = []
        captured_cmd_args = {}
        captured_setup_args = {}

        orig_command = h.command
        def _wrap_command(prompt, servers, session, plugin, denied, _orig=orig_command):
            captured_cmd_args["prompt"] = prompt
            captured_cmd_args["servers"] = servers
            captured_cmd_args["session"] = session
            captured_cmd_args["plugin"] = str(plugin)
            captured_cmd_args["denied"] = list(denied) if denied is not None else []
            return _orig(prompt, servers, session, plugin, denied)
        h.command = _wrap_command
        # Rook's start gives the harness the saved permission mode (harness.pick), on a tree that has the setting.
        _rook_settings = getattr(harness, "settings", None)
        if hasattr(_rook_settings, "permission_mode_in_force"):
            h.permission_mode = _rook_settings.permission_mode_in_force(_rook_settings.read_settings()[0])[0]

        orig_setup = h.setup
        def _wrap_setup(start, later, wow, _orig=orig_setup):
            captured_setup_args["start"] = {
                k: list(v) for k, v in sorted((start or {}).items())
            }
            captured_setup_args["later"] = list(later or [])
            captured_setup_args["wow"] = bool(wow)
            return _orig(start, later, wow)
        h.setup = _wrap_setup

        class FakeProc:
            pid = None
            returncode = None
            def __init__(self):
                self.stdout = asyncio.StreamReader()
                self.stdout.feed_eof()
                self.stdin = SimpleNamespace(write=self._write)
            def _write(self, data):
                for line in data.decode("utf-8", errors="replace").splitlines():
                    if line.strip():
                        written.append(json.loads(line))
            def kill(self):
                self.returncode = -9

        async def fake_exec(*argv, **kwargs):
            proc = FakeProc()
            launched.append({
                "argv": list(argv),
                "cwd": str(kwargs.get("cwd")) if kwargs.get("cwd") is not None else None,
                "env_delta": _env_delta(baseline_env, kwargs.get("env")),
            })
            return proc

        asyncio.create_subprocess_exec = fake_exec
        try:
            c = rook.Companion.__new__(rook.Companion)
            game_obj = None
            if wow_enabled:
                game_path = tree / "wow/game.py"
                if game_path.is_file():
                    if str(tree) not in sys.path:
                        sys.path.insert(0, str(tree))
                    import wow.game as wow_game
                    game_obj = wow_game.Game(c, rook.toplevels)
            async def _noop_async(*a, **k):
                return None

            c.__dict__.update(
                args=SimpleNamespace(workspace=workspace, wow=wow_enabled),
                loop=asyncio.get_running_loop(),
                game=game_obj,
                session=fixed_session,
                agent=None,
                agent_name=kind,
                agent_deaths=[],
                fallback=None,
                agent_told=False,
                agent_note=None,
                warming=False,
                warm_waits=0,
                pending_turns=set(),
                latest_turn=None,
                turn_spoken=[],
                turn_tools=[],
                turn_timing=None,
                pending_timing=None,
                scene_steps=0,
                held_note=None,
                spoke_at=None,
                playing=set(),
                silenced_at=None,
                silenced_turn=None,
                missed_events=0,
                fired=[],
                dark=None,
                dark_turn=None,
                dark_call=None,
                waiters={},
                permission=None,
                last_reply={},
                delegating={},
                tasks={},
                staged=None,
                staged_item=None,
                exit=asyncio.Event(),
                save_presence=lambda: None,
                log=lambda *a, **k: None,
                show=lambda *a, **k: None,
                read_agent=_noop_async,
                setup_deadline=_noop_async,
                harness=h,
            )
            c.exit.set()
            await c.launch_agent()
            if c.agent_reader is not None:
                c.agent_reader.cancel()

            if not launched:
                raise RuntimeError("launch_agent did not invoke create_subprocess_exec")
            launch_info = launched[0]
            argv = list(launch_info["argv"])

            # Section 1: prompts + setup turn
            system_prompt = None
            setup_turn = None
            thread_start_params = None

            if kind == "claude":
                idx = argv.index("--append-system-prompt")
                system_prompt = argv[idx + 1]
                argv[idx + 1] = "<SYSTEM_PROMPT>"
                if written:
                    msg = written[0].get("message", {})
                    setup_turn = msg.get("content")
            elif kind == "antigravity":
                list(c.harness.handle({"id": 1, "result": {}}))
                new_req = next(m for m in written if m.get("method") == "session/new")
                system_prompt = new_req["params"]["_meta"]["antigravity"]["systemPrompt"]["append"]
                list(c.harness.handle({"id": 2, "result": {"sessionId": "sid"}}))
                prompt_req = next((m for m in written if m.get("method") == "session/prompt"), None)
                if prompt_req:
                    blocks = prompt_req.get("params", {}).get("prompt", [])
                    setup_turn = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
            else:
                list(c.harness.handle({"id": 1, "result": {}}))
                list(c.harness.handle({"id": 2, "result": {"account": {"type": "chatgpt"}, "requiresOpenaiAuth": True}}))
                start_req = next(m for m in written if m.get("method") == "thread/start")
                params = dict(start_req.get("params") or {})
                system_prompt = params.pop("developerInstructions", None)
                thread_start_params = params
                list(c.harness.handle({"id": 3, "result": {"thread": {"id": "thr-1"}}}))
                list(c.harness.handle({"id": 4, "result": {"data": []}}))
                turn_req = next((m for m in written if m.get("method") == "turn/start"), None)
                if turn_req:
                    items = turn_req.get("params", {}).get("input", [])
                    setup_turn = "\n".join(i.get("text", "") for i in items if isinstance(i, dict) and i.get("type") == "text")

            out["prompts"][kind] = {
                "system_prompt": system_prompt,
                "setup_turn": setup_turn,
            }

            # Section 2: launch argv, env delta, cwd, and generated files/policy
            # Normalize --mcp-config JSON in argv for deterministic key order
            display_argv = list(argv)
            claude_mcp_config = None
            if "--mcp-config" in display_argv:
                m_idx = display_argv.index("--mcp-config")
                try:
                    claude_mcp_config = json.loads(display_argv[m_idx + 1])
                    display_argv[m_idx + 1] = json.dumps(claude_mcp_config, sort_keys=True)
                except ValueError:
                    pass

            launch_entry = {
                "argv": display_argv,
                "cwd": launch_info["cwd"],
                "env_delta": launch_info["env_delta"],
                "files": {},
            }

            # Section 3: skills
            skills_entry = {}

            # Section 6: servers
            servers_entry = {
                "rook_servers": captured_cmd_args.get("servers", {}),
                "denied_t3_tools": captured_cmd_args.get("denied", []),
                "setup_start": captured_setup_args.get("start", {}),
                "setup_later": captured_setup_args.get("later", []),
            }

            if kind == "claude":
                if "--settings" in argv:
                    s_path = Path(argv[argv.index("--settings") + 1])
                    launch_entry["files"]["settings.json"] = _read_json_if_file(s_path)
                plugin_dirs = [argv[i + 1] for i, tok in enumerate(argv) if tok == "--plugin-dir" and i + 1 < len(argv)]
                plugin_listings = {}
                all_skill_names = []
                all_skill_files = {}
                for pdir in plugin_dirs:
                    p = Path(pdir)
                    plugin_listings[str(p)] = {
                        "listing": _list_tree(p),
                        "plugin.json": _read_json_if_file(p / ".claude-plugin/plugin.json"),
                    }
                    sk = _read_skills_dir(p / "skills")
                    all_skill_names.extend(sk["names"])
                    all_skill_files.update(sk["files"])
                launch_entry["files"]["plugin_dirs"] = plugin_listings
                skills_entry = {"names": sorted(set(all_skill_names)), "files": all_skill_files}
                servers_entry["mcp_config"] = claude_mcp_config

            elif kind == "antigravity":
                agy_dir = Path(argv[argv.index("--gemini-dir") + 1]) if "--gemini-dir" in argv else antigravity_home.HOME
                cfg_dir = agy_dir / "config"
                mcp_cfg = _read_json_if_file(cfg_dir / "mcp_config.json")
                launch_entry["files"] = {
                    "hooks.json": _read_json_if_file(cfg_dir / "hooks.json"),
                    "mcp_config.json": mcp_cfg,
                    "skills.json": _read_json_if_file(cfg_dir / "skills.json"),
                    "default-cli-project.json": _read_json_if_file(cfg_dir / "projects/default-cli-project.json"),
                    "plugin.json": _read_json_if_file(cfg_dir / "plugins/rook/plugin.json"),
                    "listing": _list_tree(agy_dir),
                    "policy": {
                        "harness": _policy_snapshot(agy_harness, (
                            "MODE", "PERMISSIONS", "READS", "RAW_READS", "T3_READS",
                            "SAFE_PROGRAMS", "GIT_SUBCOMMANDS", "GIT_FLAGS", "HYPRCTL_READS",
                            "T3_READS_CLI", "RELAY_SKILLS", "RELAY_CARD", "RELAY_PROMPT",
                            "RELAY_SENDS", "SENDS",
                        )),
                        "home": _policy_snapshot(antigravity_home, (
                            "TOOLS", "ROOK_SERVERS", "T3_DENIED_TOOLS", "T3_SENDS_BY_COMMAND",
                            "T3_TOOLS", "T3_EAGER", "T3_QUEUE_ACTIONS", "EAGER_TOOLS", "WRITE_TOOLS",
                        )),
                    },
                }
                if hasattr(agy_harness, "_active_relay_skills"):
                    launch_entry["files"]["policy"]["harness"]["active_relay_skills"] = list(agy_harness._active_relay_skills())
                skills_entry = _read_skills_dir(cfg_dir / "plugins/rook/skills")
                servers_entry["mcp_config"] = mcp_cfg
                servers_entry["eager_tools"] = _policy_snapshot(antigravity_home, ("EAGER_TOOLS", "T3_EAGER", "T3_TOOLS", "ROOK_SERVERS"))

            else:
                codex_dir = getattr(c.harness, "home", None)
                cfg_text = _read_text_if_file(codex_dir / "config.toml") if codex_dir else None
                launch_entry["thread_start_params"] = thread_start_params
                launch_entry["files"] = {
                    "config.toml": cfg_text,
                    "listing": _list_tree(codex_dir) if codex_dir else None,
                }
                skills_entry = _read_skills_dir(codex_dir / "skills") if codex_dir else {"names": [], "files": {}}
                codex_mcp = None
                if cfg_text:
                    try:
                        import tomllib
                        codex_mcp = tomllib.loads(cfg_text).get("mcp_servers")
                    except Exception as exc:
                        codex_mcp = {"_parse_error": repr(exc)}
                servers_entry["config_mcp_servers"] = codex_mcp

            out["launch"][kind] = launch_entry
            out["skills"][kind] = skills_entry
            out["servers"][kind] = servers_entry

        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            for sec in ("prompts", "launch", "skills", "servers"):
                if kind not in out[sec]:
                    out[sec][kind] = {"unavailable": err}
            out["errors"][kind] = err
        finally:
            asyncio.create_subprocess_exec = real_exec

asyncio.run(capture_all())
print(json.dumps(out))
""")


def build_hook_cases(tree: Path, scratch_env: ScratchProfileEnv) -> list[tuple[str, str]]:
    """Return >= 60 fixed (case_id, stdin_text) cases for desktop/antigravity_home.py guard."""
    root = str(tree)
    relay = f"/usr/bin/python {root}/desktop/relay.py"
    skills = "skills" if (tree / "skills").is_dir() else "plugin/skills"  # Before and after the Stage 5 move.
    live = str(scratch_env.data / "rook/live")
    cfg = str(scratch_env.config / "rook")

    def cmd_case(cid: str, command: str) -> tuple[str, str]:
        payload = {
            "toolCall": {"name": "run_command", "args": {"CommandLine": command}},
            "workspacePaths": ["/tmp"],
        }
        return cid, json.dumps(payload)

    def tool_case(cid: str, name: str, args: dict) -> tuple[str, str]:
        payload = {
            "toolCall": {"name": name, "args": args},
            "workspacePaths": ["/tmp"],
        }
        return cid, json.dumps(payload)

    cases: list[tuple[str, str]] = [
        # 1. Ordinary shell commands & security boundaries
        cmd_case("shell/echo-hi", "echo hi"),
        cmd_case("shell/ls-tmp", "ls -la /tmp"),
        cmd_case("shell/cat-file", "cat /tmp/parity-sample.txt"),
        cmd_case("shell/pwd", "pwd"),
        cmd_case("shell/git-status-rook", f"git -C {root} status"),
        cmd_case("shell/git-log-rook", f"git -C {root} log -3"),
        cmd_case("shell/git-branch-read", f"git -C {root} branch -a"),
        cmd_case("shell/git-worktree-list", f"git -C {root} worktree list"),
        cmd_case("shell/git-commit-rook", f"git -C {root} commit -am parity"),
        cmd_case("shell/git-reset-hard", "git reset --hard"),
        cmd_case("shell/hidden-var-prog", "T=t3; $T project remove demo"),
        cmd_case("shell/hidden-default-var", "${T:-t3} project remove demo"),
        cmd_case("shell/systemctl-status-rook", "systemctl --user status rook"),
        cmd_case("shell/systemctl-restart-rook", "systemctl --user restart rook.service"),
        cmd_case("shell/kill-rook", "kill $(pgrep -f rook.py)"),
        cmd_case("shell/t3-project-remove", "t3 project remove demo"),
        cmd_case("shell/t3-env-unlink", "t3 environment unlink env-desk-b"),
        cmd_case("shell/t3-env-link", "t3 environment link env-desk-b"),
        cmd_case("shell/t3-auth", "t3 auth"),
        cmd_case("shell/t3-pair", "t3 pair"),
        cmd_case("shell/t3-thread-list", "t3 thread list --json"),
        cmd_case("shell/t3-thread-show", "t3 thread show mcp:00000000-0000-4000-8000-000000000001 --json"),
        cmd_case("shell/t3-env-list", "t3 environment list"),
        cmd_case("shell/gh-pr-merge", "gh pr merge 42"),
        cmd_case("shell/gh-graphql-merge", "gh api graphql -f query='mutation{mergePullRequest}'"),
        cmd_case("shell/gh-alias-merge", "gh alias set m 'pr merge'"),
        cmd_case("shell/env-unset-rook-agent", f"env -u ROOK_AGENT {relay} restart"),
        cmd_case("shell/python-m-relay-restart", "python3 -m relay restart"),
        # 2. Every relay.py subcommand used by skills (+ prompt & denied relay commands)
        cmd_case("relay/dark-on", f"{relay} dark on --for 30m"),
        cmd_case("relay/dark-status", f"{relay} dark status"),
        cmd_case("relay/project-new", f"{relay} project new demo --machine desk-a --git"),
        cmd_case("relay/watch", f"{relay} watch mcp:00000000-0000-4000-8000-000000000001"),
        cmd_case("relay/inbox", f"{relay} inbox"),
        cmd_case("relay/mailbox-list", f"{relay} mailbox list"),
        cmd_case("relay/work-list", f"{relay} work list"),
        cmd_case("relay/handoff-print", f"{relay} handoff --print -"),
        cmd_case("relay/herdr-agents", f"{relay} herdr agents"),
        cmd_case("relay/herdr-read", f"{relay} herdr read demo"),
        cmd_case("relay/pi-sessions", f"{relay} pi sessions"),
        cmd_case("relay/t3-threads-script", f"python3 {root}/{skills}/delegate/scripts/t3_threads.py --help"),
        cmd_case("relay/media-status", f"{relay} media status"),
        cmd_case("relay/media-pause", f"{relay} media pause"),
        cmd_case("relay/audition", f"{relay} audition"),
        cmd_case("relay/onboard-dry-run", f"{relay} onboard --dry-run"),
        cmd_case("relay/get", f"{relay} get"),
        cmd_case("relay/voices", f"{relay} voices"),
        cmd_case("relay/fonts", f"{relay} fonts"),
        cmd_case("relay/dusts", f"{relay} dusts"),
        cmd_case("relay/set-engine", f"{relay} set voice_engine small"),
        cmd_case("relay/device-pair", f"{relay} device pair"),
        cmd_case("relay/device-list", f"{relay} device list"),
        cmd_case("relay/show", f"{relay} show /tmp/parity-sample.png"),
        cmd_case("relay/timer-list", f"{relay} timer list"),
        cmd_case("relay/remember", f'{relay} remember "parity test note"'),
        cmd_case("relay/restart-denied", f"{relay} restart"),
        cmd_case("relay/reload-denied", f"{relay} reload overlay"),
        cmd_case("relay/daily-restart-denied", f"{relay} daily-restart"),
        # 3. Forge cases
        cmd_case("forge/relay-forge-help", f"{relay} forge --help"),
        cmd_case("forge/relay-forge-list", f"{relay} forge list"),
        cmd_case("forge/direct-bake", f"/usr/bin/python {root}/themes/forge/bake.py --help"),
        cmd_case("forge/direct-forge", f"/usr/bin/python {root}/themes/forge/forge.py --help"),
        cmd_case("forge/direct-preview", f"/usr/bin/python {root}/themes/forge/preview.py --help"),
        cmd_case("forge/xdg-override", f"XDG_CONFIG_HOME=/tmp {relay} forge list"),
        # 4. Game commands (active vs absent wow/)
        cmd_case("wow/relay-wow-note", f'{relay} wow-note "parity test"'),
        cmd_case("wow/relay-wow-data", f"{relay} wow-data gear"),
        cmd_case("wow/relay-clip", f"{relay} clip"),
        tool_case("wow/mcp-find-npc", "mcp_wow_find_npc", {"query": "innkeeper"}),
        tool_case("wow/call-mcp-find-item", "call_mcp_tool", {"ServerName": "wow", "ToolName": "find_item"}),
        # 5. Writes into Rook's own code & protected roots vs allowed writes/reads
        tool_case("write/rook-code-write-file", "write_file", {"Path": f"{root}/desktop/rook.py"}),
        tool_case("write/rook-code-edit-file", "edit_file", {"Path": f"{root}/desktop/relay.py"}),
        tool_case("write/rook-live-write", "write_to_file", {"TargetFile": f"{live}/desktop/relay.py"}),
        cmd_case("write/shell-sed-rook", f"sed -i s/a/b/ {root}/desktop/rook.py"),
        cmd_case("write/shell-redirect-rook", f"echo x > {root}/desktop/rook.py"),
        tool_case("write/config-prefs-allowed", "edit_file", {"Path": f"{cfg}/model-preferences.md"}),
        tool_case("write/tmp-file-allowed", "write_file", {"Path": "/tmp/rook-parity-note.txt"}),
        tool_case("write/view-rook-allowed", "view_file", {"Path": f"{root}/desktop/rook.py"}),
        # 6. hyprctl reads
        cmd_case("hyprctl/activewindow", "hyprctl activewindow -j"),
        cmd_case("hyprctl/monitors", "hyprctl monitors -j"),
        # 7. Omarchy commands
        cmd_case("omarchy/terminal-cwd", "omarchy-cmd-terminal-cwd"),
        cmd_case("omarchy/launch-browser", 'omarchy-launch-browser "https://example.invalid"'),
        # 8. MCP tool calls for each server & disallowed tools
        tool_case("mcp/render-show-diagram", "mcp_render_show_diagram", {"graph": "a > b"}),
        tool_case("mcp/render-call-clear", "call_mcp_tool", {"ServerName": "render", "ToolName": "clear_scene"}),
        tool_case("mcp/t3-thread-list", "mcp_t3_t3_thread_list", {}),
        tool_case("mcp/t3-thread-send", "mcp_t3_t3_thread_send", {"threadId": "t1", "message": "hi"}),
        tool_case("mcp/t3-project-delete", "mcp_t3_t3_project_delete", {"projectId": "p1"}),
        tool_case("mcp/t3-pr-merge", "mcp_t3_pull_request_merge", {"number": 1}),
        tool_case("mcp/t3-delegate-task", "mcp_t3_delegate_task", {"task": "x"}),
        tool_case("mcp/t3-queue-list", "mcp_t3_t3_queue", {"action": "list"}),
        tool_case("mcp/t3-queue-cancel", "mcp_t3_t3_queue", {"action": "cancel"}),
        tool_case("mcp/t3-call-read", "call_mcp_tool", {"ServerName": "t3", "ToolName": "t3_thread_read"}),
        tool_case("mcp/t3-call-merge", "call_mcp_tool", {"ServerName": "t3", "ToolName": "pull_request_merge"}),
        tool_case("mcp/unknown-server", "mcp_unknown_action", {}),
        tool_case("mcp/call-unknown-server", "call_mcp_tool", {"ServerName": "unknown", "ToolName": "foo"}),
        tool_case("tool/disallowed-subagent", "invoke_subagent", {}),
        tool_case("tool/disallowed-browser", "browser_click_element", {}),
        tool_case("tool/disallowed-schedule", "schedule", {}),
        # 9. Malformed and empty inputs
        ("edge/empty-stdin", ""),
        ("edge/malformed-json", "{not valid json"),
        ("edge/empty-json-object", "{}"),
    ]
    return cases


def capture_hook_section(tree: Path, scratch_env: ScratchProfileEnv, replacements: list[tuple[str, str]]) -> dict:
    hook_script = tree / "desktop/antigravity_home.py"
    if not hook_script.is_file():
        return {"unavailable": "desktop/antigravity_home.py missing"}
    scratch_env.reset_guard_log()
    cases = build_hook_cases(tree, scratch_env)

    def _run_one(item: tuple[str, str]) -> tuple[str, dict]:
        cid, stdin_text = item
        rc, out_b, err_b, _ = _run_blocking_wait(
            [PYTHON3, "-I", str(hook_script), "guard"],
            input_bytes=stdin_text.encode("utf-8"),
            cwd="/tmp",
            env=scratch_env.env,
            capture=True,
            timeout=30.0,
        )
        entry: dict = {"returncode": rc}
        stdout = out_b.decode("utf-8", errors="replace").strip()
        if stdout:
            try:
                parsed = json.loads(stdout)
                entry["decision"] = parsed.get("decision")
                # The command guard's one-time approval code changes on every run.
                entry["reason"] = re.sub(r"allow-once \d+", "allow-once <code>",
                                         normalise_text(str(parsed.get("reason", "")), replacements))
            except ValueError:
                entry["decision"] = None
                entry["stdout"] = normalise_text(stdout, replacements)
        else:
            entry["decision"] = None
            entry["reason"] = ""
        if rc != 0:
            stderr = err_b.decode("utf-8", errors="replace")
            lines = [ln for ln in stderr.strip().splitlines() if ln.strip()]
            entry["error"] = normalise_text(lines[-1] if lines else "", replacements)
        return cid, entry

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for cid, entry in pool.map(_run_one, cases):
            results[cid] = entry
    guard_calls = scratch_env.read_guard_log(replacements)
    return {
        "case_count": len(cases),
        "cases": results,
        "guard_calls": guard_calls,
    }


def capture_relay_section(tree: Path, scratch_env: ScratchProfileEnv, replacements: list[tuple[str, str]]) -> dict:
    relay_script = tree / "desktop/relay.py"
    if not relay_script.is_file():
        return {"unavailable": "desktop/relay.py missing"}
    scratch_env.reset_guard_log()

    def _run_relay(args: list[str]) -> dict:
        rc, out_b, err_b, _ = _run_blocking_wait(
            [PYTHON3, str(relay_script), *args],
            cwd=str(scratch_env.workspace),
            env=scratch_env.env,
            capture=True,
            timeout=30.0,
        )
        return {
            "returncode": rc,
            "stdout": normalise_text(out_b.decode("utf-8", errors="replace"), replacements),
            "stderr": normalise_text(err_b.decode("utf-8", errors="replace"), replacements),
        }

    help_res = _run_relay(["--help"])
    help_blob = help_res["stdout"] + "\n" + help_res["stderr"]
    has_plugin_cmd = bool(re.search(r"\brelay\.py\s+plugin\b", help_blob))

    commands: dict[str, dict] = {
        "--help": help_res,
    }
    fixed_cmds: list[tuple[str, list[str]]] = [
        ("get", ["get"]),
        ("get voice_engine", ["get", "voice_engine"]),
        ("watching", ["watching"]),
        ("work list", ["work", "list"]),
        ("unknown-command", ["no-such-parity-command"]),
        ("wow-data gear", ["wow-data", "gear"]),
    ]
    if has_plugin_cmd:
        fixed_cmds.append(("plugin list", ["plugin", "list"]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for label, res in pool.map(lambda item: (item[0], _run_relay(item[1])), fixed_cmds):
            commands[label] = res
    if not has_plugin_cmd:
        commands["plugin list"] = {"skipped": "plugin command not present in --help"}

    guard_calls = scratch_env.read_guard_log(replacements)
    return {
        "commands": commands,
        "guard_calls": guard_calls,
    }


def capture_profile(tree: Path, profile: str, sections: set[str], scratch_parent: Path | None = None,
                    overrides: dict | None = None) -> dict:
    """Capture all requested parity sections (1..6) for one profile on one tree."""
    spec = PROFILE_SPECS[profile]
    need_copy = bool(spec.get("exclude_wow_dir"))
    copy_root = Path(tempfile.mkdtemp(prefix="rook-parity-nowow-", dir=scratch_parent)) if need_copy else None
    try:
        effective_tree = tree.resolve()
        if need_copy:
            assert copy_root is not None
            effective_tree = copy_root / "tree"
            copy_tree(tree, effective_tree, exclude_wow=True)

        with ScratchProfileEnv(profile, parent_dir=scratch_parent, spec=spec) as env:
            uv_path = shutil.which("uv", path=env.env.get("PATH"))
            replacements = build_replacements(effective_tree, env.root, uv_path)

            if spec.get("settings_kind") == "owner":
                # An owner's own values go into the file as written, whether or not this tree knows the key.
                owner_settings = {**probe_owner_settings(effective_tree, env), **(overrides or {})}
                env.populate(owner_settings, OWNER_MACHINES, with_t3=True, with_notes=True)
            else:
                env.populate(None, STRANGER_MACHINES, with_t3=False, with_notes=False)

            result: dict[str, dict] = {}
            agent_sections = sections & {"prompts", "launch", "skills", "servers"}
            if agent_sections:
                env.reset_guard_log()
                wow_flag = "1" if spec.get("wow") else "0"
                done = subprocess.run(
                    [
                        PYTHON3, "-c", _CAPTURE_AGENTS_SCRIPT,
                        str(effective_tree), str(env.workspace), wow_flag, FIXED_SESSION_ID,
                    ],
                    env=env.env,
                    cwd=str(env.workspace),
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                guard_calls = env.read_guard_log(replacements)
                if done.returncode != 0 or not done.stdout.strip():
                    err = f"agent capture child failed (rc={done.returncode}): {done.stderr.strip()[:400]}"
                    for sec in sorted(agent_sections):
                        result[sec] = {"unavailable": normalise_text(err, replacements), "guard_calls": guard_calls}
                else:
                    raw = json.loads(done.stdout)
                    top_err = (raw.get("errors") or {}).get("import")
                    for sec in sorted(agent_sections):
                        if top_err:
                            result[sec] = {"unavailable": normalise_text(top_err, replacements), "guard_calls": guard_calls}
                        else:
                            sec_data = normalise_obj(raw.get(sec, {}), replacements)
                            if isinstance(sec_data, dict):
                                sec_data["guard_calls"] = guard_calls
                            result[sec] = sec_data

            if "hook" in sections:
                result["hook"] = capture_hook_section(effective_tree, env, replacements)

            if "relay" in sections:
                result["relay"] = capture_relay_section(effective_tree, env, replacements)

            return result
    finally:
        if copy_root is not None:
            shutil.rmtree(copy_root, ignore_errors=True)


def _median_iqr(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    med = statistics.median(values)
    if len(values) >= 4:
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
        iqr = q3 - q1
    else:
        iqr = max(values) - min(values)
    return round(med, 2), round(iqr, 2)


def _timing_comparison(
    ref_vals: list[float],
    new_vals: list[float],
    *,
    band: float = TIMING_SELF_BAND,
) -> dict:
    ref_med, ref_iqr = _median_iqr(ref_vals)
    new_med, new_iqr = _median_iqr(new_vals)
    if ref_med is None or new_med is None or ref_med <= 0:
        return {
            "runs": min(len(ref_vals), len(new_vals)),
            "ref_ms": ref_med,
            "ref_iqr_ms": ref_iqr,
            "new_ms": new_med,
            "new_iqr_ms": new_iqr,
            "ratio": None,
            "delta_pct": None,
            "noise_pct": None,
            "verdict": "unavailable",
            "warn": False,
        }
    ratio = new_med / ref_med
    delta_pct = (ratio - 1.0) * 100.0
    n_ref, n_new = max(1, len(ref_vals)), max(1, len(new_vals))
    se_ref = 1.253 * ((ref_iqr or 0.0) / 1.349) / math.sqrt(n_ref)
    se_new = 1.253 * ((new_iqr or 0.0) / 1.349) / math.sqrt(n_new)
    noise_pct = 1.96 * math.hypot(se_new, ratio * se_ref) / ref_med * 100.0
    threshold_pct = max(band * 100.0, noise_pct)
    if abs(delta_pct) <= threshold_pct:
        verdict = f"within noise (±{noise_pct:.1f}%)"
        warn = False
    elif delta_pct > 0:
        verdict = f"slower by {delta_pct:.1f} percent (±{noise_pct:.1f})"
        warn = True
    else:
        verdict = f"faster by {abs(delta_pct):.1f} percent (±{noise_pct:.1f})"
        warn = False
    return {
        "runs": min(len(ref_vals), len(new_vals)),
        "ref_ms": ref_med,
        "ref_iqr_ms": ref_iqr,
        "new_ms": new_med,
        "new_iqr_ms": new_iqr,
        "ratio": round(ratio, 4),
        "delta_pct": round(delta_pct, 2),
        "noise_pct": round(noise_pct, 2),
        "threshold_pct": round(threshold_pct, 2),
        "verdict": verdict,
        "warn": warn,
    }


def _timing_comparison_from_summary(
    ref_med: float | None,
    ref_iqr: float | None,
    ref_n: int,
    new_med: float | None,
    new_iqr: float | None,
    new_n: int,
    *,
    band: float = TIMING_SELF_BAND,
) -> dict:
    if ref_med is None or new_med is None or ref_med <= 0:
        return {
            "runs": min(ref_n, new_n),
            "ref_ms": ref_med,
            "ref_iqr_ms": ref_iqr,
            "new_ms": new_med,
            "new_iqr_ms": new_iqr,
            "ratio": None,
            "delta_pct": None,
            "noise_pct": None,
            "verdict": "unavailable",
            "warn": False,
        }
    ratio = new_med / ref_med
    delta_pct = (ratio - 1.0) * 100.0
    se_ref = 1.253 * ((ref_iqr or 0.0) / 1.349) / math.sqrt(max(1, ref_n))
    se_new = 1.253 * ((new_iqr or 0.0) / 1.349) / math.sqrt(max(1, new_n))
    noise_pct = 1.96 * math.hypot(se_new, ratio * se_ref) / ref_med * 100.0
    threshold_pct = max(band * 100.0, noise_pct)
    if abs(delta_pct) <= threshold_pct:
        verdict = f"within noise (±{noise_pct:.1f}%)"
        warn = False
    elif delta_pct > 0:
        verdict = f"slower by {delta_pct:.1f} percent (±{noise_pct:.1f})"
        warn = True
    else:
        verdict = f"faster by {abs(delta_pct):.1f} percent (±{noise_pct:.1f})"
        warn = False
    return {
        "runs": min(ref_n, new_n),
        "ref_ms": ref_med,
        "ref_iqr_ms": ref_iqr,
        "new_ms": new_med,
        "new_iqr_ms": new_iqr,
        "ratio": round(ratio, 4),
        "delta_pct": round(delta_pct, 2),
        "noise_pct": round(noise_pct, 2),
        "threshold_pct": round(threshold_pct, 2),
        "verdict": verdict,
        "warn": warn,
    }


def measure_single_tree_timings(
    tree: Path,
    warmup: int = TIMING_WARMUP_RUNS,
    relay_runs: int = TIMING_RELAY_BLOCKS * 2,
    hook_runs: int = TIMING_HOOK_BLOCKS * 2,
) -> dict:
    """Measure warmed median and IQR (ms) of relay.py --help and hook on a single tree."""
    tree = tree.resolve()
    relay_script = tree / "desktop/relay.py"
    hook_script = tree / "desktop/antigravity_home.py"
    hook_input = json.dumps({
        "toolCall": {"name": "run_command", "args": {"CommandLine": "echo hi"}},
        "workspacePaths": ["/tmp"],
    }).encode("utf-8")
    with ScratchProfileEnv("timings") as env:
        env.populate(None, STRANGER_MACHINES, with_t3=False, with_notes=False)
        relay_ms: list[float] = []
        hook_ms: list[float] = []
        if relay_script.is_file():
            for _ in range(warmup):
                _run_blocking_wait([PYTHON3, str(relay_script), "--help"], cwd=str(env.workspace), env=env.env)
            for _ in range(relay_runs):
                rc, _, _, ms = _run_blocking_wait([PYTHON3, str(relay_script), "--help"], cwd=str(env.workspace), env=env.env)
                if rc in (0, 1):
                    relay_ms.append(ms)
        if hook_script.is_file():
            for _ in range(warmup):
                _run_blocking_wait([PYTHON3, "-I", str(hook_script), "guard"], input_bytes=hook_input, cwd="/tmp", env=env.env)
            for _ in range(hook_runs):
                rc, _, _, ms = _run_blocking_wait([PYTHON3, "-I", str(hook_script), "guard"], input_bytes=hook_input, cwd="/tmp", env=env.env)
                if rc == 0:
                    hook_ms.append(ms)
        r_med, r_iqr = _median_iqr(relay_ms)
        h_med, h_iqr = _median_iqr(hook_ms)
        return {
            "warmup": warmup,
            "relay_runs": len(relay_ms),
            "hook_runs": len(hook_ms),
            "relay_help_ms": r_med,
            "relay_help_iqr_ms": r_iqr,
            "hook_ms": h_med,
            "hook_iqr_ms": h_iqr,
        }


def measure_interleaved_timings(
    ref_tree: Path,
    new_tree: Path,
    warmup: int = TIMING_WARMUP_RUNS,
    relay_blocks: int = TIMING_RELAY_BLOCKS,
    hook_blocks: int = TIMING_HOOK_BLOCKS,
) -> dict:
    """Warm both trees, then run ABBA interleaved timing blocks (ref, new, new, ref)."""
    ref_tree, new_tree = ref_tree.resolve(), new_tree.resolve()
    ref_relay, new_relay = ref_tree / "desktop/relay.py", new_tree / "desktop/relay.py"
    ref_hook, new_hook = ref_tree / "desktop/antigravity_home.py", new_tree / "desktop/antigravity_home.py"
    hook_input = json.dumps({
        "toolCall": {"name": "run_command", "args": {"CommandLine": "echo hi"}},
        "workspacePaths": ["/tmp"],
    }).encode("utf-8")
    with ScratchProfileEnv("timings-ref") as ref_env, ScratchProfileEnv("timings-new") as new_env:
        ref_env.populate(None, STRANGER_MACHINES, with_t3=False, with_notes=False)
        new_env.populate(None, STRANGER_MACHINES, with_t3=False, with_notes=False)
        samples: dict[str, list[float]] = {"ref_relay": [], "new_relay": [], "ref_hook": [], "new_hook": []}

        def _time_relay(script: Path, env: ScratchProfileEnv) -> float | None:
            if not script.is_file():
                return None
            rc, _, _, ms = _run_blocking_wait([PYTHON3, str(script), "--help"], cwd=str(env.workspace), env=env.env)
            return ms if rc in (0, 1) else None

        def _time_hook(script: Path, env: ScratchProfileEnv) -> float | None:
            if not script.is_file():
                return None
            rc, _, _, ms = _run_blocking_wait(
                [PYTHON3, "-I", str(script), "guard"], input_bytes=hook_input, cwd="/tmp", env=env.env
            )
            return ms if rc == 0 else None

        # Warm both trees alternately before measuring (page cache + bytecode cache).
        for _ in range(warmup):
            _time_relay(ref_relay, ref_env)
            _time_relay(new_relay, new_env)
        for _ in range(relay_blocks):
            for tag, script, env in (
                ("ref", ref_relay, ref_env),
                ("new", new_relay, new_env),
                ("new", new_relay, new_env),
                ("ref", ref_relay, ref_env),
            ):
                ms = _time_relay(script, env)
                if ms is not None:
                    samples[f"{tag}_relay"].append(ms)

        for _ in range(warmup):
            _time_hook(ref_hook, ref_env)
            _time_hook(new_hook, new_env)
        for _ in range(hook_blocks):
            for tag, script, env in (
                ("ref", ref_hook, ref_env),
                ("new", new_hook, new_env),
                ("new", new_hook, new_env),
                ("ref", ref_hook, ref_env),
            ):
                ms = _time_hook(script, env)
                if ms is not None:
                    samples[f"{tag}_hook"].append(ms)

        return {
            "warmup": warmup,
            "order": "ABBA",
            "interleaved": True,
            "band_pct": round(TIMING_SELF_BAND * 100.0, 1),
            "relay_help": _timing_comparison(samples["ref_relay"], samples["new_relay"]),
            "hook": _timing_comparison(samples["ref_hook"], samples["new_hook"]),
        }


def capture_tree_surface(tree: Path, sections: set[str], *, include_timings: bool = True,
                         overrides: dict | None = None) -> dict:
    profiles_data = {}
    for prof in PROFILES:
        profiles_data[prof] = capture_profile(tree, prof, sections, overrides=overrides)
    timings = measure_single_tree_timings(tree) if (include_timings and "timings" in sections) else None
    return {
        "format_version": 1,
        "tree": str(tree.resolve()),
        "sections": [s for s in ALL_SECTIONS if s in sections],
        "normalised": list(NORMALISED_ITEMS),
        "profiles": profiles_data,
        "timings": timings,
    }


def write_capture_dir(surface: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "surface.json").write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n")
    for prof, sections in (surface.get("profiles") or {}).items():
        pdir = out_dir / prof
        pdir.mkdir(parents=True, exist_ok=True)
        for sec, data in sections.items():
            (pdir / f"{sec}.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
            if sec == "prompts" and isinstance(data, dict):
                pr_dir = pdir / "prompts"
                pr_dir.mkdir(exist_ok=True)
                for agent in ("claude", "antigravity", "codex"):
                    item = data.get(agent)
                    if isinstance(item, dict) and isinstance(item.get("system_prompt"), str):
                        (pr_dir / f"{agent}.system.txt").write_text(item["system_prompt"])
                    if isinstance(item, dict) and isinstance(item.get("setup_turn"), str):
                        (pr_dir / f"{agent}.setup.txt").write_text(item["setup_turn"])
    if surface.get("timings") is not None:
        (out_dir / "timings.json").write_text(json.dumps(surface["timings"], indent=2, sort_keys=True) + "\n")


def _section_has_unavailable(data) -> list[str]:
    found: list[str] = []
    if isinstance(data, dict):
        if "unavailable" in data:
            found.append(str(data["unavailable"]))
        for k, v in data.items():
            if k != "unavailable" and isinstance(v, dict) and "unavailable" in v:
                found.append(f"{k}: {v['unavailable']}")
    return found


def _render_for_diff(section: str, data) -> str:
    """Render a section into readable, deterministic lines for unified diffing."""
    if section == "prompts" and isinstance(data, dict):
        parts = []
        for agent in ("claude", "antigravity", "codex"):
            item = data.get(agent)
            parts.append(f"=== {agent} ===")
            if isinstance(item, dict) and "unavailable" not in item:
                parts.append("-- system_prompt --")
                parts.append(str(item.get("system_prompt") or ""))
                parts.append("-- setup_turn --")
                parts.append(str(item.get("setup_turn") or ""))
            else:
                parts.append(json.dumps(item, indent=2, sort_keys=True))
        if data.get("guard_calls"):
            parts.append("=== guard_calls ===")
            parts.append(json.dumps(data["guard_calls"], indent=2, sort_keys=True))
        return "\n".join(parts) + "\n"
    if section == "skills" and isinstance(data, dict):
        parts = [f"shared_sources: {json.dumps(data.get('shared_sources'), sort_keys=True)}"]
        for agent in ("claude", "antigravity", "codex"):
            item = data.get(agent)
            parts.append(f"=== {agent} ===")
            if isinstance(item, dict) and "unavailable" not in item:
                parts.append(f"names: {json.dumps(item.get('names') or [])}")
                for sk_name, sk_files in sorted((item.get("files") or {}).items()):
                    for rel, content in sorted((sk_files or {}).items()):
                        parts.append(f"--- {agent}/{sk_name}/{rel} ---")
                        parts.append(str(content))
            else:
                parts.append(json.dumps(item, indent=2, sort_keys=True))
        if data.get("guard_calls"):
            parts.append("=== guard_calls ===")
            parts.append(json.dumps(data["guard_calls"], indent=2, sort_keys=True))
        return "\n".join(parts) + "\n"
    if section == "relay" and isinstance(data, dict) and "commands" in data:
        parts = []
        for label, item in sorted((data.get("commands") or {}).items()):
            parts.append(f"=== relay {label} ===")
            if isinstance(item, dict) and "returncode" in item:
                parts.append(f"returncode: {item['returncode']}")
                if item.get("stdout"):
                    parts.append("-- stdout --")
                    parts.append(str(item["stdout"]).rstrip("\n"))
                if item.get("stderr"):
                    parts.append("-- stderr --")
                    parts.append(str(item["stderr"]).rstrip("\n"))
            else:
                parts.append(json.dumps(item, indent=2, sort_keys=True))
        if data.get("guard_calls"):
            parts.append("=== guard_calls ===")
            parts.append(json.dumps(data["guard_calls"], indent=2, sort_keys=True))
        return "\n".join(parts) + "\n"
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _trim_line(line: str) -> str:
    nl = "\n" if line.endswith("\n") else ""
    body = line[:-1] if nl else line
    if len(body) <= DIFF_MAX_LINE_CHARS:
        return line
    extra = len(body) - DIFF_MAX_LINE_CHARS
    return f"{body[:DIFF_MAX_LINE_CHARS]}... (+{extra} chars){nl}"


def first_difference(section: str, ref_val, new_val) -> str:
    """Name the first differing item in a section (agent prompt, skill file, hook case, relay command, etc.)."""
    if not isinstance(ref_val, dict) or not isinstance(new_val, dict):
        return section
    if section == "prompts":
        for agent in ("claude", "antigravity", "codex"):
            ra, na = ref_val.get(agent), new_val.get(agent)
            if ra != na:
                if isinstance(ra, dict) and isinstance(na, dict):
                    for field in ("system_prompt", "setup_turn"):
                        if ra.get(field) != na.get(field):
                            return f"{agent} {field}"
                return agent
        if ref_val.get("guard_calls") != new_val.get("guard_calls"):
            return "guard_calls"
    elif section == "launch":
        for agent in ("claude", "antigravity", "codex"):
            ra, na = ref_val.get(agent), new_val.get(agent)
            if ra != na:
                if isinstance(ra, dict) and isinstance(na, dict):
                    for field in ("argv", "env_delta", "cwd", "thread_start_params"):
                        if ra.get(field) != na.get(field):
                            return f"{agent} {field}"
                    rf, nf = ra.get("files") or {}, na.get("files") or {}
                    if isinstance(rf, dict) and isinstance(nf, dict):
                        for fname in sorted(set(rf) | set(nf)):
                            if rf.get(fname) != nf.get(fname):
                                return f"{agent} files/{fname}"
                return agent
        if ref_val.get("guard_calls") != new_val.get("guard_calls"):
            return "guard_calls"
    elif section == "skills":
        for agent in ("claude", "antigravity", "codex"):
            ra, na = ref_val.get(agent), new_val.get(agent)
            if ra != na:
                if isinstance(ra, dict) and isinstance(na, dict):
                    if ra.get("names") != na.get("names"):
                        return f"{agent} skill list"
                    rf, nf = ra.get("files") or {}, na.get("files") or {}
                    if isinstance(rf, dict) and isinstance(nf, dict):
                        for sk in sorted(set(rf) | set(nf)):
                            rsk, nsk = rf.get(sk), nf.get(sk)
                            if rsk != nsk:
                                if isinstance(rsk, dict) and isinstance(nsk, dict):
                                    for rel in sorted(set(rsk) | set(nsk)):
                                        if rsk.get(rel) != nsk.get(rel):
                                            return f"{agent} {sk}/{rel}"
                                return f"{agent} {sk}"
                return agent
        if ref_val.get("shared_sources") != new_val.get("shared_sources"):
            return "shared_sources"
        if ref_val.get("guard_calls") != new_val.get("guard_calls"):
            return "guard_calls"
    elif section == "hook":
        rc, nc = ref_val.get("cases") or {}, new_val.get("cases") or {}
        if isinstance(rc, dict) and isinstance(nc, dict):
            for cid in sorted(set(rc) | set(nc)):
                if rc.get(cid) != nc.get(cid):
                    return f"case {cid}"
        if ref_val.get("guard_calls") != new_val.get("guard_calls"):
            return "guard_calls"
    elif section == "relay":
        rc, nc = ref_val.get("commands") or {}, new_val.get("commands") or {}
        if isinstance(rc, dict) and isinstance(nc, dict):
            for cmd in sorted(set(rc) | set(nc)):
                if rc.get(cmd) != nc.get(cmd):
                    return f"command {cmd}"
        if ref_val.get("guard_calls") != new_val.get("guard_calls"):
            return "guard_calls"
    elif section == "servers":
        for agent in ("claude", "antigravity", "codex"):
            ra, na = ref_val.get(agent), new_val.get(agent)
            if ra != na:
                if isinstance(ra, dict) and isinstance(na, dict):
                    for field in ("rook_servers", "mcp_config", "config_mcp_servers", "eager_tools", "setup_start", "setup_later", "denied_t3_tools"):
                        if ra.get(field) != na.get(field):
                            rf, nf = ra.get(field), na.get(field)
                            if field == "rook_servers" and isinstance(rf, dict) and isinstance(nf, dict):
                                for srv in sorted(set(rf) | set(nf)):
                                    if rf.get(srv) != nf.get(srv):
                                        return f"{agent} server {srv}"
                            return f"{agent} {field}"
                return agent
        if ref_val.get("guard_calls") != new_val.get("guard_calls"):
            return "guard_calls"
    for key in sorted(set(ref_val) | set(new_val)):
        if ref_val.get(key) != new_val.get(key):
            return str(key)
    return section


def make_trimmed_diff(section: str, ref_data, new_data, ref_label: str, new_label: str, max_lines: int = DIFF_MAX_LINES) -> str:
    ref_lines = _render_for_diff(section, ref_data).splitlines(keepends=True)
    new_lines = _render_for_diff(section, new_data).splitlines(keepends=True)
    diff = [
        _trim_line(ln)
        for ln in difflib.unified_diff(ref_lines, new_lines, fromfile=f"ref/{ref_label}", tofile=f"new/{new_label}", n=2)
    ]
    if len(diff) <= max_lines:
        return "".join(diff)
    hidden = len(diff) - max_lines
    return "".join(diff[:max_lines]) + f"... ({hidden} more diff lines trimmed)\n"


def compare_surfaces(
    ref_target: Path,
    new_target: Path,
    sections: set[str],
    expect_changes: set[tuple[str, str | None]],
) -> dict:
    """Capture (or load) both targets, compare sections 1..6 and report timings (7)."""
    t0 = time.perf_counter()
    ref_target, new_target = ref_target.resolve(), new_target.resolve()
    ref_is_cap = is_captured_dir(ref_target)
    new_is_cap = is_captured_dir(new_target)

    ref_surface = json.loads((ref_target / "surface.json").read_text()) if ref_is_cap else capture_tree_surface(
        ref_target, sections, include_timings=False
    )
    new_surface = json.loads((new_target / "surface.json").read_text()) if new_is_cap else capture_tree_surface(
        new_target, sections, include_timings=False, overrides=OWNER_OVERRIDES  # The new tree only: the reference
    )  # tree is main as the owner runs it today.

    parity_secs = [s for s in PARITY_SECTIONS if s in sections]
    rows: list[dict] = []
    failed = False

    for prof in PROFILES:
        ref_prof = (ref_surface.get("profiles") or {}).get(prof, {})
        new_prof = (new_surface.get("profiles") or {}).get(prof, {})
        for sec in parity_secs:
            ref_missing = sec not in ref_prof
            new_missing = sec not in new_prof
            ref_val = ref_prof.get(sec)
            new_val = new_prof.get(sec)
            ref_unavail = (["section not captured"] if ref_missing else _section_has_unavailable(ref_val))
            new_unavail = (["section not captured"] if new_missing else _section_has_unavailable(new_val))
            expected = (sec, None) in expect_changes or (sec, prof) in expect_changes

            if ref_unavail or new_unavail:
                status = "UNAVAILABLE"
                diff_text = ""
                if ref_val != new_val:
                    diff_text = make_trimmed_diff(sec, ref_val, new_val, f"{prof}/{sec}", f"{prof}/{sec}")
                detail = "; ".join(
                    ([f"ref: {', '.join(ref_unavail)}"] if ref_unavail else [])
                    + ([f"new: {', '.join(new_unavail)}"] if new_unavail else [])
                )
                if not expected:
                    failed = True
                rows.append({
                    "profile": prof,
                    "section": sec,
                    "status": status,
                    "expected": expected,
                    "detail": detail,
                    "diff": diff_text,
                })
            elif ref_val == new_val:
                rows.append({
                    "profile": prof,
                    "section": sec,
                    "status": "SAME",
                    "expected": expected,
                    "detail": "",
                    "diff": "",
                })
            else:
                status = "EXPECTED" if expected else "DIFFERENT"
                if not expected:
                    failed = True
                first_diff = first_difference(sec, ref_val, new_val)
                diff_text = make_trimmed_diff(sec, ref_val, new_val, f"{prof}/{sec}", f"{prof}/{sec}")
                rows.append({
                    "profile": prof,
                    "section": sec,
                    "status": status,
                    "expected": expected,
                    "detail": first_diff,
                    "first_diff": first_diff,
                    "diff": diff_text,
                })

    timings = None
    if "timings" in sections:
        if not ref_is_cap and not new_is_cap:
            timings = measure_interleaved_timings(ref_target, new_target)
        else:
            rt = ref_surface.get("timings") or (measure_single_tree_timings(ref_target) if not ref_is_cap else None)
            nt = new_surface.get("timings") or (measure_single_tree_timings(new_target) if not new_is_cap else None)
            timings = {
                "warmup": (rt or nt or {}).get("warmup", TIMING_WARMUP_RUNS),
                "order": "single-tree",
                "interleaved": False,
                "band_pct": round(TIMING_SELF_BAND * 100.0, 1),
                "relay_help": _timing_comparison_from_summary(
                    (rt or {}).get("relay_help_ms"), (rt or {}).get("relay_help_iqr_ms"),
                    (rt or {}).get("relay_runs", TIMING_RELAY_BLOCKS * 2),
                    (nt or {}).get("relay_help_ms"), (nt or {}).get("relay_help_iqr_ms"),
                    (nt or {}).get("relay_runs", TIMING_RELAY_BLOCKS * 2),
                ),
                "hook": _timing_comparison_from_summary(
                    (rt or {}).get("hook_ms"), (rt or {}).get("hook_iqr_ms"),
                    (rt or {}).get("hook_runs", TIMING_HOOK_BLOCKS * 2),
                    (nt or {}).get("hook_ms"), (nt or {}).get("hook_iqr_ms"),
                    (nt or {}).get("hook_runs", TIMING_HOOK_BLOCKS * 2),
                ),
            }

    return {
        "ref": str(ref_target.resolve()),
        "new": str(new_target.resolve()),
        "ok": not failed,
        "sections": [s for s in ALL_SECTIONS if s in sections],
        "expected_changes": sorted(f"{s}:{p}" if p else s for s, p in expect_changes),
        "normalised": list(NORMALISED_ITEMS),
        "rows": rows,
        "timings": timings,
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }


def format_timing_line(name: str, item: dict) -> str:
    r_ms, n_ms = item.get("ref_ms"), item.get("new_ms")
    r_iqr, n_iqr = item.get("ref_iqr_ms"), item.get("new_iqr_ms")
    runs = item.get("runs")
    verdict = item.get("verdict") or "unavailable"
    if r_ms is None or n_ms is None:
        return f"{name}: unavailable"
    r_spread = f" (IQR {r_iqr:.1f}ms)" if r_iqr is not None else ""
    n_spread = f" (IQR {n_iqr:.1f}ms)" if n_iqr is not None else ""
    warn = " WARNING" if item.get("warn") else ""
    n_tag = f" ({runs}x)" if runs else ""
    return f"{name}{n_tag}: ref={r_ms:.1f}ms{r_spread} new={n_ms:.1f}ms{n_spread} -> {verdict}{warn}"


def print_report(report: dict) -> None:
    print(f"Parity: {report['ref']}  vs  {report['new']}")
    for row in report["rows"]:
        label = f"{row['profile']}/{row['section']}"
        extra = f" ({row['detail']})" if row.get("detail") else ""
        print(f"  {label:<24} {row['status']}{extra}")
        if row.get("diff"):
            for line in row["diff"].splitlines():
                print(f"    {line}")
    if report.get("timings"):
        t = report["timings"]
        mode = f"warmup {t.get('warmup', TIMING_WARMUP_RUNS)}x, {t.get('order', 'ABBA')}"
        print(f"  timings ({mode}, band ±{t.get('band_pct', TIMING_SELF_BAND * 100):.1f}%):")
        for name, key in (("relay --help", "relay_help"), ("hook", "hook")):
            print(f"    {format_timing_line(name, t.get(key) or {})}")
    verdict = "PASS" if report["ok"] else "FAIL"
    print(f"Result: {verdict} ({report['elapsed_seconds']}s)")


def _check_profile_isolation() -> None:
    """Verify every profile's scratch desktop, PATH isolation, Hyprland socket, and host omarchy skill."""
    for name in PROFILES:
        spec = PROFILE_SPECS[name]
        with ScratchProfileEnv(name, spec=spec) as env:
            path_dirs = env.env["PATH"].split(":")
            assert path_dirs == [str(env.guard_bin), str(env.sys_bin)], (name, path_dirs)
            omarchy_bins = sorted(
                p.name for d in path_dirs for p in Path(d).iterdir() if p.name.startswith("omarchy-")
            )
            has_agent_skill = (env.home / ".agents/skills/omarchy/SKILL.md").is_file()
            has_claude_skill = (env.home / ".claude/skills/omarchy/SKILL.md").is_file()
            if spec["omarchy"]:
                assert omarchy_bins == sorted(OMARCHY_STUBS), (name, omarchy_bins)
                assert has_agent_skill and has_claude_skill, (name, has_agent_skill, has_claude_skill)
            else:
                assert omarchy_bins == [], (name, omarchy_bins)
                assert not has_agent_skill and not has_claude_skill, (name, has_agent_skill, has_claude_skill)

            sig = env.env.get("HYPRLAND_INSTANCE_SIGNATURE")
            sock_path = env.runtime / "hypr" / HYPR_SIGNATURE / ".socket.sock"
            if spec["hyprland"]:
                assert sig == HYPR_SIGNATURE and sock_path.exists(), (name, sig, sock_path)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(1.0)
                    s.connect(str(sock_path))
                    s.sendall(b"j/activewindow")
                    reply = json.loads(s.recv(4096).decode("utf-8"))
                assert reply == HYPR_STANDIN_REPLIES["activewindow"], (name, reply)
            else:
                assert sig is None and not sock_path.exists(), (name, sig, sock_path)


def _patch_file(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"Self-check mutation target not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def run_self_check() -> int:
    """Self-check profile isolation, (a) same-tree determinism + calibration, and (c) 6 planted mutations."""
    t0 = time.perf_counter()
    tree = Path(__file__).resolve().parent.parent
    print(f"Running scripts/parity.py --check on {tree}")

    _check_profile_isolation()
    print(f"  [p] profile isolation verified across {len(PROFILES)} profiles ({', '.join(PROFILES)})")

    # (a) Same tree vs same tree, twice in a row (all 4 profiles x 6 sections + timing calibration).
    all_secs = set(ALL_SECTIONS)
    lo, hi = 1.0 - TIMING_SELF_BAND, 1.0 + TIMING_SELF_BAND
    for run_idx in (1, 2):
        rep = compare_surfaces(tree, tree, all_secs, set())
        bad = [r for r in rep["rows"] if r["status"] != "SAME"]
        if not rep["ok"] or bad or len(rep["rows"]) != len(PROFILES) * len(PARITY_SECTIONS):
            print_report(rep)
            print(f"FAIL: self-check (a) run {run_idx} was not all SAME.", file=sys.stderr)
            return 1
        t = rep.get("timings") or {}
        for name, key in (("relay --help", "relay_help"), ("hook", "hook")):
            item = t.get(key) or {}
            ratio = item.get("ratio")
            if ratio is None or not (lo <= ratio <= hi):
                print_report(rep)
                print(
                    f"FAIL: self-check (a.{run_idx}) timing calibration for {name} outside {lo:.2f}..{hi:.2f}: "
                    f"{format_timing_line(name, item)}",
                    file=sys.stderr,
                )
                return 1
        r_line = format_timing_line("relay --help", t.get("relay_help") or {})
        h_line = format_timing_line("hook", t.get("hook") or {})
        print(f"  [a.{run_idx}] same-tree: {len(rep['rows'])}/{len(rep['rows'])} SAME ({rep['elapsed_seconds']}s)")
        print(f"        {r_line}")
        print(f"        {h_line}")

    # Capture baseline once to speed up mutation checks while exercising --capture too.
    scratch = Path(tempfile.mkdtemp(prefix="rook-parity-selfcheck-"))
    try:
        base_dir = scratch / "baseline"
        baseline = capture_tree_surface(tree, set(PARITY_SECTIONS), include_timings=False)
        write_capture_dir(baseline, base_dir)

        mutations = [
            (
                "prompts",
                "one word in the prompt",
                "desktop/rook.py",
                "You are not a pet or a toy.",
                "You are not a pet or a gadget.",
            ),
            (
                "launch",
                "a launch flag",
                "desktop/harness.py",
                '"--permission-mode", "auto",',
                '"--permission-mode", "plan",',
            ),
            (
                "skills",
                "one skill line",
                "skills/dark/SKILL.md",
                "# Going dark\n",
                "# Going dark\n\nParity check marker line.\n",
            ),
            (
                "hook",
                "one hook rule",
                "desktop/antigravity_home.py",
                r'DENIED_COMMANDS = re.compile(r"\bt3\s+',
                r'DENIED_COMMANDS = re.compile(r"\becho\s+hi\b|\bt3\s+',
            ),
            (
                "relay",
                "one help line",
                "desktop/relay.py",
                "Print Rook's settings and where each value comes from.",
                "Show Rook's settings and where each value comes from.",
            ),
            (
                "servers",
                "a server argument",
                "desktop/rook.py",
                '["run", "--script", str(ROOT / "desktop/render_tool.py")]',
                '["run", "--no-sync", "--script", str(ROOT / "desktop/render_tool.py")]',
            ),
        ]

        for idx, (target_sec, desc, rel_path, old, new) in enumerate(mutations, 1):
            mut_tree = scratch / f"mut-{idx}-{target_sec}"
            copy_tree(tree, mut_tree, exclude_wow=False)
            try:
                _patch_file(mut_tree / rel_path, old, new)
                rep = compare_surfaces(base_dir, mut_tree, {target_sec}, set())
                caught = [r for r in rep["rows"] if r["section"] == target_sec and r["status"] == "DIFFERENT"]
                if rep["ok"] or not caught:
                    print_report(rep)
                    print(f"FAIL: self-check (c.{idx}) mutation ({desc}) not caught in {target_sec}.", file=sys.stderr)
                    return 1
                print(
                    f"  [c.{idx}] planted {target_sec} ({desc}): caught "
                    f"({len(caught)}/{len(PROFILES)} profiles, {rep['elapsed_seconds']}s)"
                )
            finally:
                shutil.rmtree(mut_tree, ignore_errors=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    total = round(time.perf_counter() - t0, 2)
    print(f"Self-check: all checks passed in {total}s.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture and compare Rook's agent-visible surface across two trees.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Sections: 1/prompts (3-agent system+setup prompts), 2/launch (argv, env delta, files, policy), 3/skills (lists+rendered files),\n"
            "  4/hook (97 guard decisions from /tmp), 5/relay (relay.py --help+safe commands), 6/servers (MCP servers+eager tools), 7/timings (ABBA medians+IQR).\n"
            "Normalised: tree root-><ROOT>, scratch-><SCRATCH>, uv-><UV>, fixed <SESSION_ID>, setup UUID omitted, keys/listings sorted."
        ),
    )
    parser.add_argument("trees", nargs="*", metavar="TREE", help="REF_TREE NEW_TREE (checkouts or captured dirs)")
    parser.add_argument("--capture", metavar="TREE", help="Capture one tree's surface to --out DIR")
    parser.add_argument("--out", metavar="DIR", help="Output directory for --capture")
    parser.add_argument(
        "--only", action="append", default=[], metavar="SECTION",
        help="Limit to one or more sections (prompts, launch, skills, hook, relay, servers, timings; or 1..7)",
    )
    parser.add_argument(
        "--expect-change", action="append", default=[], metavar="SECTION[:PROFILE]",
        help="Mark a section (or section:profile) as expected to differ (still prints diff, does not fail)",
    )
    parser.add_argument("--json", metavar="OUT", dest="json_out", help="Write JSON comparison report to OUT")
    parser.add_argument("--check", action="store_true", help="Run built-in determinism and mutation self-checks")
    parser.add_argument("--owner-settings", metavar="FILE",
                        help="JSON settings for the owner and no-wow profiles of the new tree only")
    args = parser.parse_args(argv)
    if args.owner_settings:
        OWNER_OVERRIDES.update(json.loads(Path(args.owner_settings).read_text()))

    if args.check:
        return run_self_check()

    try:
        sections: set[str] = set()
        for raw in args.only:
            for piece in raw.split(","):
                if piece.strip():
                    sections.add(parse_section_name(piece))
        if not sections:
            sections = set(ALL_SECTIONS)
        expect_changes = {parse_expect_spec(raw) for raw in args.expect_change}
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.capture:
        if not args.out:
            print("error: --capture requires --out DIR.", file=sys.stderr)
            return 2
        tree = Path(args.capture)
        if not tree.is_dir():
            print(f"error: tree does not exist: {tree}", file=sys.stderr)
            return 2
        out_dir = Path(args.out)
        surface = capture_tree_surface(tree, sections, include_timings=("timings" in sections), overrides=OWNER_OVERRIDES)
        write_capture_dir(surface, out_dir)
        print(f"Captured surface of {tree.resolve()} to {out_dir.resolve()}")
        return 0

    if len(args.trees) != 2:
        parser.print_usage(sys.stderr)
        return 2

    ref_path, new_path = Path(args.trees[0]), Path(args.trees[1])
    for p in (ref_path, new_path):
        if not p.exists():
            print(f"error: path does not exist: {p}", file=sys.stderr)
            return 2

    report = compare_surfaces(ref_path, new_path, sections, expect_changes)
    print_report(report)
    if args.json_out:
        out_p = Path(args.json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
