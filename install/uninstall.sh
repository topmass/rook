#!/usr/bin/env bash
# Uninstall only what install/install.sh created and recorded in its manifest.
# Leaves user config and memory intact unless --purge is passed. Never runs sudo. Refuses root.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  printf 'Error: Do not run install/uninstall.sh as root.\nFix: Run it as your normal desktop user.\n' >&2
  exit 1
fi

XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"

DATA_DIR="$XDG_DATA_HOME/rook"
CONFIG_DIR="$XDG_CONFIG_HOME/rook"
STATE_DIR="$XDG_STATE_HOME/rook"
MANIFEST_PATH="$DATA_DIR/install-manifest.json"
SYSTEMD_USER_DIR="$XDG_CONFIG_HOME/systemd/user"
SYSTEMCTL_BIN="systemctl"
# On a Mac: the launchd agents and Rook.app that install/install.sh records.
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LAUNCHD_LABEL="${ROOK_LAUNCHD_LABEL:-com.rook.companion}"
MAC_APP="${ROOK_APP:-$HOME/Applications/Rook.app}"

PURGE=0
DRY_RUN=0
ASSUME_YES=0

usage() {
  cat <<EOF
Usage: install/uninstall.sh [options]

Remove only the files created by install/install.sh as recorded in its manifest.
Config and memory are kept unless --purge is given.

Options:
  --purge        Also remove user config ($CONFIG_DIR) and state/memory ($STATE_DIR)
                 when created by this installer, plus an empty Rook data folder ($DATA_DIR).
                 Pre-existing folders and user symlinks are left untouched.
  --dry-run      Print the exact removal plan and change nothing.
  -y, --yes      Skip the confirmation prompt.
  -h, --help     Show this help message.
EOF
}

die() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

require_abs_path() {
  local label="$1"
  local val="$2"
  [ -n "$val" ] || die "$label is empty."
  case "$val" in
    /*) ;;
    *) die "$label must be an absolute path, got '$val'." ;;
  esac
  case "/$val/" in
    */../*) die "$label must not contain '..': '$val'." ;;
  esac
  case "$val" in
    *$'\n'*|*$'\r'*|*$'\t'*) die "$label must not contain newlines or tabs." ;;
  esac
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --purge) PURGE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

require_abs_path "HOME" "${HOME:-}"
require_abs_path "XDG_CONFIG_HOME" "$XDG_CONFIG_HOME"
require_abs_path "XDG_DATA_HOME" "$XDG_DATA_HOME"
require_abs_path "XDG_CACHE_HOME" "$XDG_CACHE_HOME"
require_abs_path "XDG_STATE_HOME" "$XDG_STATE_HOME"

if [ -L "$MANIFEST_PATH" ]; then
  die "Install manifest $MANIFEST_PATH is a symlink. Refusing to trust it. Nothing was removed."
fi

if [ ! -e "$MANIFEST_PATH" ]; then
  printf 'No install manifest found at %s. Nothing to remove.\n' "$MANIFEST_PATH"
  exit 0
fi

if [ ! -f "$MANIFEST_PATH" ]; then
  die "Install manifest $MANIFEST_PATH is not a regular file. Nothing was removed."
fi

exec python3 - "$MANIFEST_PATH" "$HOME" "$DATA_DIR" "$CONFIG_DIR" "$STATE_DIR" "$SYSTEMD_USER_DIR" "$XDG_CACHE_HOME" "$SYSTEMCTL_BIN" "$PURGE" "$DRY_RUN" "$ASSUME_YES" "$LAUNCH_AGENTS_DIR" "$LAUNCHD_LABEL" "$MAC_APP" <<'PY'
import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(errors="backslashreplace")
sys.stderr.reconfigure(errors="backslashreplace")

(
    manifest_arg,
    home_arg,
    data_arg,
    config_arg,
    state_arg,
    systemd_arg,
    cache_arg,
    systemctl_bin,
    purge_arg,
    dry_arg,
    yes_arg,
) = sys.argv[1:12]
launch_agents_arg, launchd_label, mac_app_arg = sys.argv[12:15]

PURGE = purge_arg == "1"
DRY_RUN = dry_arg == "1"
ASSUME_YES = yes_arg == "1"

ALLOWED_UNITS = frozenset({
    "rook.service",
    "rook-failed.service",
    "rook-daily.service",
    "rook-daily.timer",
    "rook-medium-voice.service",
})
# Units that run on their own and are stopped and disabled before their file goes.
STOPPED_UNITS = ("rook.service", "rook-daily.timer", "rook-medium-voice.service")
ALLOWED_DIR_ROLES = frozenset({"prefix", "rook_venv", "voice_venv", "medium_voice"})
# On a Mac, the installer's launchd agents are Rook's own and its daily restart, and Rook.app has one exact path.
ALLOWED_PLISTS = frozenset({f"{launchd_label}.plist", f"{launchd_label}.daily.plist", "com.rook.medium-voice.plist"})
LAUNCH_AGENTS_REAL = os.path.realpath(os.path.normpath(launch_agents_arg))
MAC_APP_REAL = os.path.realpath(os.path.normpath(mac_app_arg))
UNIT_MARKER = "# Managed by Rook install/install.sh"
# Ignored files that Python/Rook itself may generate inside a checkout.
ALLOWED_IGNORED_NAMES = ("__pycache__/", "*.pyc", "*.pyo")

for label, val in (
    ("HOME", home_arg),
    ("DATA_DIR", data_arg),
    ("CONFIG_DIR", config_arg),
    ("STATE_DIR", state_arg),
    ("SYSTEMD_USER_DIR", systemd_arg),
    ("MANIFEST_PATH", manifest_arg),
):
    if not val or not val.strip():
        print(f"Error: {label} is empty.", file=sys.stderr)
        sys.exit(1)
    if not os.path.isabs(val) or ".." in Path(val).parts:
        print(f"Error: {label} must be a clean absolute path, got {val!r}.", file=sys.stderr)
        sys.exit(1)

HOME_NORM = os.path.normpath(home_arg)
DATA_NORM = os.path.normpath(data_arg)
CONFIG_NORM = os.path.normpath(config_arg)
STATE_NORM = os.path.normpath(state_arg)
SYSTEMD_NORM = os.path.normpath(systemd_arg)

HOME_REAL = os.path.realpath(HOME_NORM)
DATA_REAL = os.path.realpath(DATA_NORM)
CONFIG_REAL = os.path.realpath(CONFIG_NORM)
STATE_REAL = os.path.realpath(STATE_NORM)
SYSTEMD_REAL = os.path.realpath(SYSTEMD_NORM)
MANIFEST_PATH = Path(manifest_arg)

EXPECTED_VENV_REALS = {
    "rook_venv": os.path.realpath(os.path.join(DATA_REAL, "venv")),
    "voice_venv": os.path.realpath(os.path.join(DATA_REAL, "voice-phonon")),
    "medium_voice": os.path.realpath(os.path.join(DATA_REAL, "medium-voice")),
}

FORBIDDEN_EXACT = frozenset({
    "/",
    HOME_NORM,
    HOME_REAL,
    DATA_NORM,
    DATA_REAL,
    CONFIG_NORM,
    CONFIG_REAL,
    STATE_NORM,
    STATE_REAL,
    SYSTEMD_NORM,
    SYSTEMD_REAL,
})


def is_strictly_inside(path_str, root_str):
    if not path_str or not root_str:
        return False
    try:
        rel = os.path.relpath(path_str, root_str)
    except ValueError:
        return False
    return rel not in (".", "..") and not rel.startswith(".." + os.sep)


def is_clean_rel_list(val):
    if not isinstance(val, list):
        return False
    for item in val:
        if not isinstance(item, str) or not item:
            return False
        if "\x00" in item:
            return False
        if os.path.isabs(item) or ".." in Path(item).parts:
            return False
    return True


def is_hex_sha40(val):
    return isinstance(val, str) and len(val) == 40 and all(c in "0123456789abcdef" for c in val)


def is_hex_sha64(val):
    return isinstance(val, str) and len(val) == 64 and all(c in "0123456789abcdef" for c in val)


def safe_display(name):
    if not isinstance(name, str):
        name = str(name)
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        name = name.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="backslashreplace")
    return repr(name) if ("\n" in name or "\r" in name) else name


def is_allowed_ignored(root, rel_path):
    p = rel_path.rstrip("/")
    if not p:
        return False
    full = os.path.join(str(root), p)
    if os.path.islink(full):
        return False
    if os.path.isdir(full):
        if os.path.basename(full) != "__pycache__":
            return False
        try:
            for cur, dirs, files in os.walk(full):
                if dirs:
                    return False
                for fname in files:
                    fpath = os.path.join(cur, fname)
                    if os.path.islink(fpath) or not fname.endswith((".pyc", ".pyo")):
                        return False
        except OSError:
            return False
        return True
    return p.endswith((".pyc", ".pyo"))


def check_prefix_clean(prefix_path, entry):
    """Return a reason string if the checkout differs in any way from what was installed, else None."""
    root = Path(prefix_path)
    git_dir = root / ".git"
    if not git_dir.is_dir():
        return f"not a standalone git checkout; inspect or remove {prefix_path} by hand"
    if not (root / "desktop" / "rook.py").is_file() or not (root / "desktop" / "relay.py").is_file():
        return f"folder does not contain Rook checkout files; inspect or remove {prefix_path} by hand"

    def run_git(*args):
        return subprocess.run(
            ["git", "-C", str(prefix_path), *args],
            capture_output=True,
            text=True,
            timeout=15,
        )

    # Keep the checkout if it has any custom git hook (any file in .git/hooks that is not a .sample).
    hooks_dir = git_dir / "hooks"
    if hooks_dir.is_dir():
        try:
            custom_hooks = [h.name for h in sorted(hooks_dir.iterdir()) if not h.name.endswith(".sample")]
        except OSError:
            return f"could not inspect git hooks; leaving {prefix_path} untouched"
        if custom_hooks:
            sample = ", ".join(safe_display(h) for h in custom_hooks[:3])
            extra = f" (+{len(custom_hooks) - 3} more)" if len(custom_hooks) > 3 else ""
            return f"checkout has custom git hooks ({sample}{extra}); inspect or remove {prefix_path} by hand"

    # Keep the checkout if it has any linked worktree (deleting the main repo breaks every linked worktree).
    wt_dir = git_dir / "worktrees"
    if wt_dir.is_dir():
        try:
            if any(wt_dir.iterdir()):
                return f"checkout has linked git worktrees; remove them first or remove {prefix_path} by hand"
        except OSError:
            return f"could not inspect linked git worktrees; leaving {prefix_path} untouched"
    try:
        wt_res = run_git("worktree", "list", "--porcelain")
    except (OSError, subprocess.TimeoutExpired):
        return f"could not inspect git worktrees; leaving {prefix_path} untouched"
    if wt_res.returncode != 0:
        return f"git worktree check failed; leaving {prefix_path} untouched"
    wt_count = sum(1 for line in wt_res.stdout.splitlines() if line.startswith("worktree "))
    if wt_count != 1:
        return f"checkout has {wt_count - 1} linked git worktree(s); remove them first or remove {prefix_path} by hand"

    try:
        st = subprocess.run(
            ["git", "-C", str(prefix_path), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching"],
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return f"could not check git status; leaving {prefix_path} untouched"
    if st.returncode != 0:
        return f"git status failed; leaving {prefix_path} untouched"

    dirty_items = []
    ignored_items = []
    records = st.stdout.split(b"\x00")
    idx = 0
    while idx < len(records):
        raw_rec = records[idx]
        idx += 1
        if not raw_rec or len(raw_rec) < 4:
            continue
        code = raw_rec[:2].decode("ascii", errors="replace")
        rel = raw_rec[3:].decode("utf-8", errors="surrogateescape")
        if code[0] in ("R", "C") or code[1] in ("R", "C"):
            idx += 1  # Skip original path entry for renames/copies in -z format.
        if code == "!!":
            if not is_allowed_ignored(root, rel):
                ignored_items.append(safe_display(rel))
        elif code == "??" and is_allowed_ignored(root, rel):
            continue
        else:
            dirty_items.append(f"{code.strip()} {safe_display(rel)}".strip())

    if dirty_items:
        sample = ", ".join(dirty_items[:3])
        extra = f" (+{len(dirty_items) - 3} more)" if len(dirty_items) > 3 else ""
        return f"checkout has local edits or untracked files ({sample}{extra}); back up or remove {prefix_path} by hand"

    if ignored_items:
        sample = ", ".join(ignored_items[:3])
        extra = f" (+{len(ignored_items) - 3} more)" if len(ignored_items) > 3 else ""
        allowed_desc = ", ".join(ALLOWED_IGNORED_NAMES)
        return (
            f"checkout has ignored files outside Rook/Python bytecode ({allowed_desc}): "
            f"{sample}{extra}; back up or remove {prefix_path} by hand"
        )

    try:
        stash = run_git("stash", "list")
    except (OSError, subprocess.TimeoutExpired):
        return f"could not check git stashes; leaving {prefix_path} untouched"
    if stash.returncode != 0 or stash.stdout.strip():
        return f"checkout contains git stashes; inspect with git -C {prefix_path} stash list or remove by hand"

    try:
        branches_res = run_git("for-each-ref", "--format=%(refname:short)", "refs/heads")
        remotes_res = run_git("for-each-ref", "--format=%(refname)", "refs/remotes")
        head_res = run_git("rev-parse", "HEAD")
    except (OSError, subprocess.TimeoutExpired):
        return f"could not inspect git refs/HEAD; leaving {prefix_path} untouched"
    if branches_res.returncode != 0 or remotes_res.returncode != 0 or head_res.returncode != 0:
        return f"git ref check failed; leaving {prefix_path} untouched"

    branches = [b.strip() for b in branches_res.stdout.splitlines() if b.strip()]
    installed_branch = entry.get("branch")
    if len(branches) > 1:
        return f"checkout has extra local branches ({', '.join(branches)}); inspect or remove {prefix_path} by hand"
    if isinstance(installed_branch, str) and installed_branch and installed_branch != "HEAD":
        if branches and branches != [installed_branch]:
            return f"checkout branch changed from {installed_branch} to {branches[0]}; inspect or remove {prefix_path} by hand"

    head_sha = head_res.stdout.strip()
    installed_commit = entry.get("commit")
    if head_sha != installed_commit:
        return (
            f"checkout HEAD ({head_sha[:7]}) differs from installed commit ({installed_commit[:7]}); "
            f"inspect with git -C {prefix_path} log or remove by hand"
        )

    # Unreachable-from-remote check over HEAD, all refs, and the reflog (catches detached/orphan/local commits).
    if not remotes_res.stdout.strip():
        return f"checkout has no remote-tracking refs to verify commits against; inspect or remove {prefix_path} by hand"
    try:
        unreached_res = run_git("rev-list", "--max-count=5", "HEAD", "--all", "--reflog", "--not", "--remotes")
    except (OSError, subprocess.TimeoutExpired):
        return f"could not verify commits against remote-tracking refs; leaving {prefix_path} untouched"
    if unreached_res.returncode != 0 or unreached_res.stdout.strip():
        unreached_shas = [line.strip() for line in unreached_res.stdout.splitlines() if line.strip()]
        if installed_branch == "HEAD" and unreached_shas == [installed_commit]:
            return (
                f"checkout was installed from a detached HEAD ({installed_commit[:7]}) not on any remote-tracking "
                f"branch; inspect or remove {prefix_path} by hand"
            )
        return (
            f"checkout has commits not reachable from any remote-tracking ref (local, detached HEAD, or reflog); "
            f"inspect with git -C {prefix_path} log --all --reflog or remove by hand"
        )

    return None


def check_venv_clean(venv_path, entry):
    """Return a reason string if unexpected user-added files or dirs exist inside an installer venv, else None."""
    root = Path(venv_path)
    recorded_files = entry.get("installed_files")
    recorded_dirs = entry.get("installed_dirs")
    if not is_clean_rel_list(recorded_files):
        return f"manifest entry has no valid recorded file list; leaving {venv_path} untouched"
    allowed_files = set(recorded_files)
    allowed_dirs = set(recorded_dirs) if is_clean_rel_list(recorded_dirs) else None
    unexpected = []
    try:
        for cur, dirs, files in os.walk(root):
            cur_rel = os.path.relpath(cur, root)
            in_pycache = cur_rel != "." and "__pycache__" in Path(cur_rel).parts
            real_dirs = []
            for d in sorted(dirs):
                full = os.path.join(cur, d)
                rel = os.path.relpath(full, root)
                if os.path.islink(full):
                    if in_pycache or rel not in allowed_files:
                        unexpected.append(rel)
                elif d == "__pycache__" and not in_pycache:
                    real_dirs.append(d)
                else:
                    if in_pycache or (allowed_dirs is not None and rel not in allowed_dirs):
                        unexpected.append(rel + "/")
                    real_dirs.append(d)
            dirs[:] = real_dirs
            for fname in sorted(files):
                full = os.path.join(cur, fname)
                rel = os.path.relpath(full, root)
                if not os.path.islink(full) and fname.endswith((".pyc", ".pyo")):
                    continue
                if rel not in allowed_files:
                    unexpected.append(rel)
    except OSError as exc:
        return f"could not scan venv ({exc}); leaving {venv_path} untouched"

    if unexpected:
        sample = ", ".join(safe_display(x) for x in unexpected[:3])
        extra = f" (+{len(unexpected) - 3} more)" if len(unexpected) > 3 else ""
        return f"venv contains user-added files ({sample}{extra}); back up your files or remove {venv_path} by hand"
    return None


def write_manifest_atomic(path, payload):
    fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as out:
            os.fchmod(out.fileno(), 0o600)
            json.dump(payload, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


try:
    manifest = json.loads(MANIFEST_PATH.read_text())
except (OSError, ValueError) as exc:
    print(f"Error: Install manifest {MANIFEST_PATH} could not be parsed ({exc}). Nothing was removed.", file=sys.stderr)
    sys.exit(1)

if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
    print(f"Error: Install manifest {MANIFEST_PATH} has an invalid format. Nothing was removed.", file=sys.stderr)
    sys.exit(1)

to_remove = []            # list of (path_str, kind, note)
owned_units_to_remove = set()
owned_plists_to_remove = set()  # launchd labels whose recorded plist still matches its hash
kept_items = []           # list of (path_str, reason)
skipped_bad = []          # list of (display_str, reason)
remaining_entries = []    # entries kept in manifest after this uninstall run
seen_targets = set()

for raw_entry in manifest.get("entries") or []:
    if not isinstance(raw_entry, dict):
        skipped_bad.append((repr(raw_entry), "manifest entry is not an object"))
        remaining_entries.append(raw_entry)
        continue
    raw_path = raw_entry.get("path")
    kind = raw_entry.get("kind")
    role = raw_entry.get("role")
    created = raw_entry.get("created")

    if not isinstance(raw_path, str) or not raw_path.strip():
        skipped_bad.append((repr(raw_path), "empty path"))
        remaining_entries.append(raw_entry)
        continue
    if "\n" in raw_path or "\r" in raw_path or "\x00" in raw_path:
        skipped_bad.append((repr(raw_path), "path contains newline or control character"))
        remaining_entries.append(raw_entry)
        continue
    if created is not True:
        kept_items.append((raw_path, "not created by installer"))
        remaining_entries.append(raw_entry)
        continue
    if not os.path.isabs(raw_path):
        skipped_bad.append((raw_path, "path is not absolute"))
        remaining_entries.append(raw_entry)
        continue
    if ".." in Path(raw_path).parts:
        skipped_bad.append((raw_path, "path contains '..'"))
        remaining_entries.append(raw_entry)
        continue

    norm = os.path.normpath(raw_path)
    if norm in ("/", HOME_NORM, HOME_REAL):
        skipped_bad.append((raw_path, "refusing to touch root or HOME"))
        remaining_entries.append(raw_entry)
        continue

    parent_real = os.path.realpath(os.path.dirname(norm))
    real_target = os.path.realpath(norm)

    if real_target in FORBIDDEN_EXACT:
        skipped_bad.append((raw_path, "resolves to a protected root folder"))
        remaining_entries.append(raw_entry)
        continue

    try:
        st = os.lstat(norm)
    except FileNotFoundError:
        continue
    except OSError as exc:
        skipped_bad.append((raw_path, f"cannot stat path: {exc}"))
        remaining_entries.append(raw_entry)
        continue

    is_link = stat.S_ISLNK(st.st_mode)
    is_dir = stat.S_ISDIR(st.st_mode)
    is_file = stat.S_ISREG(st.st_mode)

    if kind == "unit":
        base = os.path.basename(norm)
        if role not in ("systemd_unit", "launchd_plist"):
            skipped_bad.append((raw_path, f"unit role '{role}' is not 'systemd_unit' or 'launchd_plist'"))
            remaining_entries.append(raw_entry)
            continue
        is_plist = role == "launchd_plist"
        allowed_names, unit_dir = (ALLOWED_PLISTS, LAUNCH_AGENTS_REAL) if is_plist else (ALLOWED_UNITS, SYSTEMD_REAL)
        if base not in allowed_names:
            skipped_bad.append((raw_path, f"unit name '{base}' is not a Rook {'launchd agent' if is_plist else 'systemd unit'}"))
            remaining_entries.append(raw_entry)
            continue
        if parent_real != unit_dir:
            skipped_bad.append((raw_path, f"unit is outside {unit_dir}"))
            remaining_entries.append(raw_entry)
            continue
        if is_link:
            skipped_bad.append((raw_path, "unit entry is a symlink; installer only writes regular unit files"))
            remaining_entries.append(raw_entry)
            continue
        if not is_file:
            skipped_bad.append((raw_path, "unit entry is not a regular file"))
            remaining_entries.append(raw_entry)
            continue
        rec_sha = raw_entry.get("sha256")
        if not is_hex_sha64(rec_sha):
            skipped_bad.append((raw_path, "unit entry is missing a valid recorded content hash"))
            remaining_entries.append(raw_entry)
            continue
        try:
            actual_sha = hashlib.sha256(Path(norm).read_bytes()).hexdigest()
        except OSError as exc:
            skipped_bad.append((raw_path, f"cannot read unit file: {exc}"))
            remaining_entries.append(raw_entry)
            continue
        if actual_sha != rec_sha:
            kept_items.append((norm, "unit file was modified since install or not written by Rook's installer; left untouched and not stopped/disabled"))
            remaining_entries.append(raw_entry)
            continue
        if norm not in seen_targets:
            seen_targets.add(norm)
            if is_plist:
                owned_plists_to_remove.add(base[:-len(".plist")])
                to_remove.append((norm, "unit", "launchd agent"))
            else:
                owned_units_to_remove.add(base)
                to_remove.append((norm, "unit", "systemd user unit"))
    elif kind == "dir" and role == "mac_app":
        if is_link or not is_dir or real_target != MAC_APP_REAL or not os.path.isfile(
                os.path.join(norm, "Contents", "MacOS", "RookHelper")):
            skipped_bad.append((raw_path, f"Rook.app entry is not the app the installer builds at {MAC_APP_REAL}"))
            remaining_entries.append(raw_entry)
            continue
        if norm not in seen_targets:
            seen_targets.add(norm)
            to_remove.append((norm, "dir", "Rook.app"))
    elif kind == "dir":
        if role not in ALLOWED_DIR_ROLES:
            skipped_bad.append((raw_path, f"directory role '{role}' is not installer-managed"))
            remaining_entries.append(raw_entry)
            continue
        if not is_strictly_inside(parent_real, DATA_REAL) and parent_real != DATA_REAL:
            skipped_bad.append((raw_path, f"parent resolves outside {DATA_REAL}"))
            remaining_entries.append(raw_entry)
            continue
        if not is_strictly_inside(real_target, DATA_REAL):
            skipped_bad.append((raw_path, f"resolves outside {DATA_REAL}"))
            remaining_entries.append(raw_entry)
            continue
        if is_link:
            skipped_bad.append((raw_path, "directory entry is a symlink, refusing to follow"))
            remaining_entries.append(raw_entry)
            continue
        if not is_dir:
            skipped_bad.append((raw_path, "directory entry is not a directory"))
            remaining_entries.append(raw_entry)
            continue
        if role == "prefix":
            if not is_hex_sha40(raw_entry.get("commit")) or not isinstance(raw_entry.get("branch"), str) or not raw_entry["branch"].strip():
                skipped_bad.append((raw_path, "prefix entry is missing valid recorded commit/branch"))
                remaining_entries.append(raw_entry)
                continue
            if not (Path(norm) / ".git").exists():
                skipped_bad.append((raw_path, "prefix entry is not a git checkout"))
                remaining_entries.append(raw_entry)
                continue
            user_reason = check_prefix_clean(norm, raw_entry)
            if user_reason:
                kept_items.append((norm, user_reason))
                remaining_entries.append(raw_entry)
                continue
        elif role in ("rook_venv", "voice_venv", "medium_voice"):
            if real_target != EXPECTED_VENV_REALS[role]:
                skipped_bad.append((raw_path, f"{role} path does not match installer target {EXPECTED_VENV_REALS[role]}"))
                remaining_entries.append(raw_entry)
                continue
            if not is_clean_rel_list(raw_entry.get("installed_files")):
                skipped_bad.append((raw_path, f"{role} entry is missing a valid recorded file list"))
                remaining_entries.append(raw_entry)
                continue
            if "installed_dirs" in raw_entry and not is_clean_rel_list(raw_entry.get("installed_dirs")):
                skipped_bad.append((raw_path, f"{role} entry has an invalid recorded directory list"))
                remaining_entries.append(raw_entry)
                continue
            venv_reason = check_venv_clean(norm, raw_entry)
            if venv_reason:
                kept_items.append((norm, venv_reason))
                remaining_entries.append(raw_entry)
                continue
        if norm not in seen_targets:
            seen_targets.add(norm)
            to_remove.append((norm, "dir", role))
    else:
        skipped_bad.append((raw_path, f"unknown entry kind '{kind}'"))
        remaining_entries.append(raw_entry)

# Record kept items from manifest that still exist so plan shows them clearly and manifest retains them.
remaining_kept = []
for k in manifest.get("kept") or []:
    if isinstance(k, dict) and isinstance(k.get("path"), str) and (os.path.exists(k["path"]) or os.path.islink(k["path"])):
        kept_items.append((k["path"], str(k.get("reason") or "kept by installer")))
        remaining_kept.append(k)

# Keep the manifest whenever any kept or skipped items remain; remove it only when nothing remains.
keep_manifest = bool(remaining_entries or remaining_kept or skipped_bad)
manifest_norm = os.path.normpath(str(MANIFEST_PATH))
if keep_manifest:
    kept_items.append((manifest_norm, "install manifest kept to track remaining kept/skipped items"))
elif os.path.isfile(manifest_norm) and not os.path.islink(manifest_norm) and is_strictly_inside(os.path.realpath(manifest_norm), DATA_REAL):
    to_remove.append((manifest_norm, "file", "install manifest"))

# If DATA_DIR itself is a symlink, the installer did not create it: leave the symlink and its target untouched.
if os.path.islink(DATA_NORM):
    kept_items.append((DATA_NORM, f"data symlink not created by installer (left untouched; target {DATA_REAL})"))

# Purge targets: remove ONLY folders the manifest recorded as created by this installer, never pre-existing folders or user symlinks.
created_config_dir = manifest.get("created_config_dir") is True
created_state_dir = manifest.get("created_state_dir") is True
if PURGE:
    for label, p_norm, created_flag in (
        ("config", CONFIG_NORM, created_config_dir),
        ("state", STATE_NORM, created_state_dir),
    ):
        if p_norm in ("/", HOME_NORM, HOME_REAL):
            skipped_bad.append((p_norm, f"refusing to purge {label} root"))
            continue
        if os.path.islink(p_norm):
            kept_items.append((p_norm, f"user {label} symlink not created by installer (left untouched even with --purge)"))
        elif os.path.exists(p_norm):
            if not created_flag:
                kept_items.append((p_norm, f"pre-existing {label} folder not created by installer (left untouched even with --purge)"))
                continue
            p_real = os.path.realpath(p_norm)
            if p_real in ("/", HOME_REAL):
                skipped_bad.append((p_norm, f"refusing to purge {label} resolving to root or HOME"))
                continue
            to_remove.append((p_norm, "dir", f"user {label} (--purge)"))
else:
    if os.path.exists(CONFIG_NORM) or os.path.islink(CONFIG_NORM):
        kept_items.append((CONFIG_NORM, "user settings, personality and custom skills (use --purge to remove)"))
    if os.path.exists(STATE_NORM) or os.path.islink(STATE_NORM):
        kept_items.append((STATE_NORM, "logs, journal, and memory (use --purge to remove)"))

# Print exact plan BEFORE any action.
print("Rook uninstall plan")
if to_remove:
    print("  Will remove:")
    for path_str, kind, note in to_remove:
        print(f"    - {safe_display(path_str)} ({safe_display(note)})")
else:
    print("  Will remove: (nothing)")

if kept_items:
    print("  Will keep:")
    for path_str, reason in kept_items:
        print(f"    - {safe_display(path_str)} ({safe_display(reason)})")

if skipped_bad:
    print("  Skipped unsafe or invalid manifest entries:")
    for disp, reason in skipped_bad:
        print(f"    - {safe_display(disp)}: {safe_display(reason)}")

print(f"  Shared model caches under {safe_display(cache_arg)} (huggingface, airtype) are left untouched.")


def print_replaced_unit_notes(disabled_units=(), dry_run=False):
    for k in remaining_kept:
        if k.get("role") == "replaced_unit_backup" and isinstance(k.get("path"), str):
            bpath = k["path"]
            base_orig = os.path.basename(bpath).split(".replaced-")[0]
            orig_path = os.path.join(SYSTEMD_NORM, base_orig)
            if base_orig in disabled_units:
                verb = "uninstall will disable this unit" if dry_run else "uninstall disabled this unit"
                print(
                    f"  Note: your original unit copy is still at {safe_display(bpath)} (never restored automatically). "
                    f"Compare first if {safe_display(orig_path)} still exists, then restore without overwriting and re-enable "
                    f"({verb}): "
                    f"mv -n -- {shlex.quote(bpath)} {shlex.quote(orig_path)} && systemctl --user daemon-reload && systemctl --user enable {shlex.quote(base_orig)}"
                )
            else:
                print(
                    f"  Note: your original unit copy is still at {safe_display(bpath)} (never restored automatically). "
                    f"Compare first if {safe_display(orig_path)} still exists, then restore without overwriting: "
                    f"mv -n -- {shlex.quote(bpath)} {shlex.quote(orig_path)} && systemctl --user daemon-reload"
                )


if DRY_RUN:
    planned_disabled = {u for u in STOPPED_UNITS if u in owned_units_to_remove}
    print_replaced_unit_notes(planned_disabled, dry_run=True)
    print("Dry run finished. Nothing was removed.")
    sys.exit(1 if skipped_bad else 0)

if not to_remove:
    print_replaced_unit_notes()
    print("Nothing removed.")
    sys.exit(1 if skipped_bad else 0)

if not ASSUME_YES:
    if not sys.stdin.isatty():
        print("Error: Cannot ask for confirmation without a terminal. Pass --yes to confirm.", file=sys.stderr)
        sys.exit(1)
    try:
        reply = input("Proceed with removing the items listed above? [y/N] ").strip().lower()
    except EOFError:
        reply = ""
    if reply not in ("y", "yes"):
        print_replaced_unit_notes()
        print("Cancelled. Nothing was removed.")
        sys.exit(1 if skipped_bad else 0)
else:
    print("Proceed with removing the items listed above? [y/N] y (--yes)")

# Stop and disable ONLY units whose file is recorded AND still matches its recorded hash.
actually_disabled = set()
if owned_units_to_remove and shutil.which(systemctl_bin):
    for unit_name in STOPPED_UNITS:
        if unit_name in owned_units_to_remove:
            subprocess.run([systemctl_bin, "--user", "disable", "--now", unit_name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            actually_disabled.add(unit_name)
# On a Mac: unload each owned launchd job before its plist goes. Unloading Rook's own job stops Rook.
if owned_plists_to_remove and shutil.which("launchctl"):
    for job in sorted(owned_plists_to_remove):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{job}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Execute EXACTLY what was printed in to_remove.
for path_str, kind, _note in to_remove:
    assert path_str and path_str not in ("/", HOME_NORM, HOME_REAL), f"Refusing unsafe delete: {path_str}"
    if kind in ("unit", "file", "symlink") or os.path.islink(path_str):
        try:
            os.unlink(path_str)
        except FileNotFoundError:
            pass
    elif kind == "dir":
        shutil.rmtree(path_str)

if owned_units_to_remove and shutil.which(systemctl_bin):
    subprocess.run([systemctl_bin, "--user", "daemon-reload"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Update manifest in place when kept or skipped items remain.
if keep_manifest and os.path.isfile(manifest_norm) and not os.path.islink(manifest_norm):
    updated_manifest = dict(manifest)
    updated_manifest["entries"] = remaining_entries
    updated_manifest["kept"] = remaining_kept
    write_manifest_atomic(MANIFEST_PATH, updated_manifest)

# Remove DATA_DIR only if it is a real empty directory (never a symlink, never / or HOME).
if DATA_NORM not in ("/", HOME_NORM, HOME_REAL) and not os.path.islink(DATA_NORM) and os.path.isdir(DATA_NORM):
    try:
        os.rmdir(DATA_NORM)
    except OSError:
        pass

print_replaced_unit_notes(actually_disabled)

timer_path = os.path.join(SYSTEMD_NORM, "rook-daily.timer")
if (
    "rook-daily.service" in owned_units_to_remove
    and "rook-daily.timer" not in owned_units_to_remove
    and (os.path.exists(timer_path) or os.path.islink(timer_path))
):
    print(
        f"Note: {safe_display(timer_path)} was left untouched; if it is enabled, it will now fail, because "
        f"the service it starts (rook-daily.service) was removed. Switch it off with: systemctl --user disable --now rook-daily.timer"
    )

if skipped_bad:
    print("Rook uninstall finished with skipped invalid manifest entries.", file=sys.stderr)
    sys.exit(1)

if remaining_entries or remaining_kept:
    n_kept = len(remaining_entries) + len(remaining_kept)
    print(f"Rook uninstall finished: {n_kept} tracked item(s) were kept (see 'Will keep' above; manifest retained).")
else:
    print("Rook uninstall complete.")
PY
