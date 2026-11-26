#!/usr/bin/env bash
# Install Rook on Arch-based Linux with Hyprland, or on an Apple Silicon Mac.
# Safe to run more than once. Never runs sudo. Refuses to run as root.
set -euo pipefail

IS_MAC=0
if [ "$(uname -s)" = Darwin ]; then
  IS_MAC=1
fi
# macOS ships bash 3.2, where an empty "${array[@]}" fails under set -u.
# ponytail: nounset is off under bash 3 only; bash 4 or later keeps it on.
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  set +u
fi

if [ "$(id -u)" -eq 0 ]; then
  printf 'Error: Do not run install/install.sh as root.\nFix: Run it as your normal desktop user.\n' >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"

DATA_DIR="$XDG_DATA_HOME/rook"
CONFIG_DIR="$XDG_CONFIG_HOME/rook"
STATE_DIR="$XDG_STATE_HOME/rook"
DEFAULT_PREFIX="$DATA_DIR/live"

AGENT="claude"
AGENT_SET=0
VOICE="small"
VOICE_SET=0
VOICE_MODEL_CHOICE=""
RECOGNISER_CHOICE=""
RECOGNISER_MODEL="en"
RECOGNISER_MODEL_SET=0
SERVICE_CHOICE=""
PREFIX="$DEFAULT_PREFIX"
DRY_RUN=0
FROM_CACHE=""
ASSUME_YES=0
USE_EXISTING_ENV=0
REPLACE_UNITS=0
SOURCE=""
RECOGNISER_SOURCE=""

PYTHON_PIN="3.12.14"
# AirType is Rook's speech-to-text. Its public MIT repository is installed into Rook's own venv at this commit.
AIRTYPE_REPO="https://github.com/topmass/airtype-for-omarchy"
AIRTYPE_COMMIT="fe4815a480e40a68b220dadc8b23d61dbd4c3340"
PHONON_MODEL_REV="92741c5b07d085ff840e26fea8ce43110b87852f"
PHONON_VOICES_REV="da6c9ec0d47be8df5c87c730a3aa97187f3229c3"
PHONON_MODEL_SPEC="hf://gradium/phonon-31m-en@${PHONON_MODEL_REV}"
PHONON_VOICES_SPEC="hf://gradium/phonon-voices@${PHONON_VOICES_REV}"
MCP_PIN="2.3.0"
UNIT_MARKER="# Managed by Rook install/install.sh"
STAGE_MARKER=".rook-install-stage"
STAGE_MARKER_MAGIC="rook-installer-stage-v1"

PACMAN_PACKAGES=(
  base-devel
  linux-api-headers
  python
  gtk4
  gtk4-layer-shell
  python-gobject
  python-cairo
  grim
  pipewire-audio
  libpulse
  wl-clipboard
  ffmpeg
  libnotify
  git
  portaudio
  libsndfile
  uv
)

OPTIONAL_VIDEO_PACKAGES=(
  gstreamer
  gst-plugin-va
  gst-plugin-gtk4
)

# Cleanup tracking: ONLY fresh temporary stage directories created by this run are ever deleted on exit.
# Pre-existing user paths and already-completed install targets are never removed by the trap.
DL_TMP=""
STAGE_TMP=""
CURRENT_STEP="starting"
CREATED_SUMMARY=()
FINISHED_INCOMPLETE=0

cleanup_on_exit() {
  local rc=$?
  if [ -n "$DL_TMP" ] && [ -d "$DL_TMP" ] && [ ! -L "$DL_TMP" ]; then
    rm -rf -- "$DL_TMP"
  fi
  if [ -n "$STAGE_TMP" ] && [ -d "$STAGE_TMP" ] && [ ! -L "$STAGE_TMP" ]; then
    rm -rf -- "$STAGE_TMP"
  fi
  if [ "$rc" -ne 0 ] && [ "$DRY_RUN" -eq 0 ] && [ "$FINISHED_INCOMPLETE" -eq 0 ]; then
    printf 'Install stopped during "%s" (exit %d).\n' "$CURRENT_STEP" "$rc" >&2
    if [ "${#CREATED_SUMMARY[@]}" -gt 0 ]; then
      printf 'Completed steps recorded in manifest (%s): %s\n' "$MANIFEST_PATH" "${CREATED_SUMMARY[*]}" >&2
      printf 'Re-run install/install.sh to finish, or run install/uninstall.sh to remove them.\n' >&2
    else
      printf 'No Rook files were installed before the stop.\n' >&2
    fi
  fi
}
trap 'exit 130' INT
trap 'exit 143' TERM
trap cleanup_on_exit EXIT

usage() {
  cat <<EOF
Usage: install/install.sh [options]

Install Rook on Arch-based Linux with Hyprland, or on an Apple Silicon Mac.

Options:
  --agent NAME               Base agent: claude, codex, antigravity, or pi (default: claude).
  --voice TIER               Voice tier: small or medium (default: small). Medium needs an NVIDIA card
                             and installs its own user unit; other computers keep the small voice.
  --voice-model yes|no       Whether to download the small voice model (about 65 MB).
  --recogniser yes|no        Whether to download the speech recogniser model (about 490 MB).
  --recogniser-model en|multi  Speech recogniser: en, Parakeet English (default), or multi, Parakeet in
                             25 European languages.
  --service yes|no           Whether to install and enable systemd user units (on a Mac: Rook.app and its launchd agent).
  --no-service               Alias for --service no.
  --prefix DIR               Install Rook checkout into DIR (default: $DEFAULT_PREFIX).
  --source PATH|URL          Git repository to clone Rook from (default: this checkout).
  --recogniser-source PATH   AirType wheel, folder, or git URL (default: AirType's public repo at a pinned commit).
  --from-cache DIR           Use local cached packages and models from DIR.
  --use-existing-env         Use an existing unrecorded Python environment as it is (install nothing into it).
  --replace-units            Replace existing modified or unrecorded Rook systemd unit files.
  --dry-run                  Print every step and change nothing.
  -y, --yes                  Answer yes to prompts whose flags were not set.
  -h, --help                 Show this help message.
EOF
}

say() {
  printf '%s\n' "$*"
}

step() {
  CURRENT_STEP="$1"
  printf '\n==> %s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$1" >&2
  if [ "${2:-}" != "" ]; then
    printf 'Fix: %s\n' "$2" >&2
  fi
  exit 1
}

require_abs_path() {
  local label="$1"
  local val="$2"
  [ -n "$val" ] || die "$label is empty." "Set $label to an absolute directory path."
  case "$val" in
    /*) ;;
    *) die "$label must be an absolute path, got '$val'." "Set $label to a path starting with /." ;;
  esac
  case "/$val/" in
    */../*) die "$label must not contain '..': '$val'." "Set $label to a clean absolute path." ;;
  esac
  case "$val" in
    *$'\n'*|*$'\r'*|*$'\t'*)
      die "$label must not contain newlines or tabs." "Set $label to a single-line absolute path." ;;
    " "*|*" ")
      die "$label must not start or end with a space." "Remove leading or trailing spaces from $label." ;;
  esac
}

validate_yes_no() {
  local flag="$1"
  local val="$2"
  case "$val" in
    yes|no) ;;
    *) die "$flag takes yes or no, not '$val'." "Pass $flag yes or $flag no." ;;
  esac
}

decide_yes_no() {
  local flag_name="$1"
  local choice="$2"
  local prompt="$3"
  if [ "$choice" = "yes" ]; then
    say "$prompt -> yes ($flag_name yes)"
    return 0
  fi
  if [ "$choice" = "no" ]; then
    say "$prompt -> no ($flag_name no)"
    return 1
  fi
  if [ "$ASSUME_YES" -eq 1 ]; then
    say "$prompt -> yes (--yes)"
    return 0
  fi
  if [ ! -t 0 ]; then
    die "Cannot ask '$prompt' without a terminal." \
        "Ask the user first and pass $flag_name yes or $flag_name no."
  fi
  local reply=""
  printf '%s [y/N] ' "$prompt"
  if ! IFS= read -r reply; then
    die "No answer received for '$prompt'." "Pass $flag_name yes or $flag_name no."
  fi
  case "$reply" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

run_cmd() {
  printf '+ %s\n' "$(printf '%q ' "$@")"
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
  fi
}

make_stage_dir() {
  local parent="$1"
  local prefix="$2"
  local dir
  dir="$(mktemp -d "$parent/${prefix}-XXXXXX")"
  chmod 0700 "$dir"
  printf '%s\n' "$STAGE_MARKER_MAGIC" >"$dir/$STAGE_MARKER"
  printf '%s\n' "$dir"
}

cleanup_stale_stages() {
  local dir cand
  for dir in "$@"; do
    [ -n "$dir" ] && [ -d "$dir" ] && [ ! -L "$dir" ] || continue
    for cand in "$dir"/.rook-stage-* "$dir"/.tmp-download-*; do
      [ -e "$cand" ] || continue
      [ ! -L "$cand" ] && [ -d "$cand" ] || continue
      [ "$cand" != "$DL_TMP" ] && [ "$cand" != "$STAGE_TMP" ] || continue
      if [ -f "$cand/$STAGE_MARKER" ] && [ ! -L "$cand/$STAGE_MARKER" ]; then
        if [ "$(head -n 1 "$cand/$STAGE_MARKER" 2>/dev/null || true)" = "$STAGE_MARKER_MAGIC" ]; then
          rm -rf -- "$cand"
          say "  Cleaned stale installer staging folder: $cand"
        fi
      fi
    done
  done
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agent)
      [ "$#" -ge 2 ] || die "--agent needs a value." "Use --agent claude, --agent codex, --agent antigravity, or --agent pi."
      AGENT="$2"; AGENT_SET=1; shift 2 ;;
    --agent=*)
      AGENT="${1#*=}"; AGENT_SET=1; shift ;;
    --voice)
      [ "$#" -ge 2 ] || die "--voice needs a value." "Use --voice small or --voice medium."
      VOICE="$2"; VOICE_SET=1; shift 2 ;;
    --voice=*)
      VOICE="${1#*=}"; VOICE_SET=1; shift ;;
    --voice-model)
      [ "$#" -ge 2 ] || die "--voice-model needs yes or no." "Use --voice-model yes or --voice-model no."
      validate_yes_no "--voice-model" "$2"
      VOICE_MODEL_CHOICE="$2"; shift 2 ;;
    --voice-model=*)
      validate_yes_no "--voice-model" "${1#*=}"
      VOICE_MODEL_CHOICE="${1#*=}"; shift ;;
    --recogniser)
      [ "$#" -ge 2 ] || die "--recogniser needs yes or no." "Use --recogniser yes or --recogniser no."
      validate_yes_no "--recogniser" "$2"
      RECOGNISER_CHOICE="$2"; shift 2 ;;
    --recogniser=*)
      validate_yes_no "--recogniser" "${1#*=}"
      RECOGNISER_CHOICE="${1#*=}"; shift ;;
    --recogniser-model)
      [ "$#" -ge 2 ] || die "--recogniser-model needs en or multi." "Use --recogniser-model en or --recogniser-model multi."
      RECOGNISER_MODEL="$2"; RECOGNISER_MODEL_SET=1; shift 2 ;;
    --recogniser-model=*)
      RECOGNISER_MODEL="${1#*=}"; RECOGNISER_MODEL_SET=1; shift ;;
    --service)
      [ "$#" -ge 2 ] || die "--service needs yes or no." "Use --service yes or --service no."
      validate_yes_no "--service" "$2"
      SERVICE_CHOICE="$2"; shift 2 ;;
    --service=*)
      validate_yes_no "--service" "${1#*=}"
      SERVICE_CHOICE="${1#*=}"; shift ;;
    --no-service)
      SERVICE_CHOICE="no"; shift ;;
    --prefix)
      [ "$#" -ge 2 ] || die "--prefix needs a directory path." "Pass a folder path after --prefix."
      PREFIX="$2"; shift 2 ;;
    --prefix=*)
      PREFIX="${1#*=}"; shift ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    --use-existing-env)
      USE_EXISTING_ENV=1; shift ;;
    --replace-units)
      REPLACE_UNITS=1; shift ;;
    --from-cache)
      [ "$#" -ge 2 ] || die "--from-cache needs a directory path." "Pass a local cache folder after --from-cache."
      FROM_CACHE="$2"; shift 2 ;;
    --from-cache=*)
      FROM_CACHE="${1#*=}"; shift ;;
    --source)
      [ "$#" -ge 2 ] || die "--source needs a path or URL." "Pass a local checkout or git URL after --source."
      SOURCE="$2"; shift 2 ;;
    --source=*)
      SOURCE="${1#*=}"; shift ;;
    --recogniser-source)
      [ "$#" -ge 2 ] || die "--recogniser-source needs a path or URL." "Pass a local wheel, folder, or git URL."
      RECOGNISER_SOURCE="$2"; shift 2 ;;
    --recogniser-source=*)
      RECOGNISER_SOURCE="${1#*=}"; shift ;;
    -y|--yes)
      ASSUME_YES=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      die "Unknown option: $1" "Run install/install.sh --help to see valid options." ;;
  esac
done

# Validate every root path before touching anything.
require_abs_path "HOME" "${HOME:-}"
require_abs_path "XDG_CONFIG_HOME" "$XDG_CONFIG_HOME"
require_abs_path "XDG_DATA_HOME" "$XDG_DATA_HOME"
require_abs_path "XDG_CACHE_HOME" "$XDG_CACHE_HOME"
require_abs_path "XDG_STATE_HOME" "$XDG_STATE_HOME"
require_abs_path "--prefix" "$PREFIX"

case "$AGENT" in
  claude|codex|antigravity|pi) ;;
  *)
    die "Agent '$AGENT' is not supported yet. Today claude, codex, antigravity, and pi work." \
        "Re-run with --agent claude, --agent codex, --agent antigravity, or --agent pi." ;;
esac

case "$VOICE" in
  small|medium) ;;
  *)
    die "Unknown voice tier '$VOICE'." "Re-run with --voice small or --voice medium." ;;
esac

# The two speech recogniser models a public install offers, by AirType model name. A rerun without the flag keeps the
# saved choice.
if [ "$RECOGNISER_MODEL_SET" -eq 0 ] && [ -f "$CONFIG_DIR/settings.json" ]; then
  SAVED_ASR="$(grep -o -E '"recogniser_model"[[:space:]]*:[[:space:]]*"(en|multi)"' "$CONFIG_DIR/settings.json" | head -n 1)" || true
  case "$SAVED_ASR" in
    *'"multi"') RECOGNISER_MODEL="multi" ;;
    *'"en"') RECOGNISER_MODEL="en" ;;
  esac
fi
case "$RECOGNISER_MODEL" in
  en) ASR_NAME="parakeet-unified-en-0.6b-int8" ;;
  multi) ASR_NAME="parakeet-tdt-0.6b-v3-int8" ;;
  *)
    die "Unknown recogniser model '$RECOGNISER_MODEL'." "Re-run with --recogniser-model en or --recogniser-model multi." ;;
esac

# The medium voice runs on this computer only when its hardware can run it. Otherwise say why and keep the small voice.
if [ "$VOICE" = "medium" ] && ! MEDIUM_WHY="$(sh "$SCRIPT_DIR/medium-voice.sh" --check)"; then
  say "$MEDIUM_WHY"
  VOICE="small"
fi

if [ -n "$FROM_CACHE" ]; then
  require_abs_path "--from-cache" "$FROM_CACHE"
  [ -d "$FROM_CACHE" ] || die "Cache folder not found: $FROM_CACHE" "Pass an existing directory to --from-cache."
  FROM_CACHE="$(cd "$FROM_CACHE" && pwd)"
fi

if [ -z "$SOURCE" ]; then
  if [ -f "$REPO_ROOT/desktop/rook.py" ] && { [ -d "$REPO_ROOT/.git" ] || [ -f "$REPO_ROOT/.git" ]; }; then
    SOURCE="$REPO_ROOT"
  else
    die "No Rook git checkout found at $REPO_ROOT and no --source was given." \
        "Run install/install.sh from a Rook checkout or pass --source <path or URL>."
  fi
fi

# Resolve AirType recogniser package source: the flag, then --from-cache, then the pinned public repo.
AIRTYPE_SPEC=""
if [ -n "$RECOGNISER_SOURCE" ]; then
  case "$RECOGNISER_SOURCE" in
    git+*)
      AIRTYPE_SPEC="airtype @ $RECOGNISER_SOURCE" ;;
    http://*|https://*|ssh://*)
      URL_PATH="${RECOGNISER_SOURCE#*://*/}"
      if [[ "$URL_PATH" == *@* ]]; then
        AIRTYPE_SPEC="airtype @ git+$RECOGNISER_SOURCE"
      else
        AIRTYPE_SPEC="airtype @ git+${RECOGNISER_SOURCE}@${AIRTYPE_COMMIT}"
      fi ;;
    *)
      if [ "$DRY_RUN" -eq 0 ] && [ ! -e "$RECOGNISER_SOURCE" ]; then
        die "Recogniser source path not found: $RECOGNISER_SOURCE" \
            "Pass an existing local AirType wheel, checkout directory, or git URL to --recogniser-source."
      fi
      AIRTYPE_SPEC="$RECOGNISER_SOURCE" ;;
  esac
elif [ -n "$FROM_CACHE" ]; then
  if [ -d "$FROM_CACHE/wheels" ] && compgen -G "$FROM_CACHE/wheels/airtype-*.whl" >/dev/null 2>&1; then
    AIRTYPE_SPEC="$(compgen -G "$FROM_CACHE/wheels/airtype-*.whl" | head -n 1)"
  elif [ -d "$FROM_CACHE/airtype-src" ]; then
    AIRTYPE_SPEC="$FROM_CACHE/airtype-src"
  fi
fi

if [ -z "$AIRTYPE_SPEC" ]; then
  AIRTYPE_SPEC="airtype @ git+${AIRTYPE_REPO}@${AIRTYPE_COMMIT}"
fi

ROOK_VENV="$DATA_DIR/venv"
VOICE_VENV="$DATA_DIR/voice-phonon"
MANIFEST_PATH="$DATA_DIR/install-manifest.json"
MEDIUM_DIR="$DATA_DIR/medium-voice"
MEDIUM_URL="http://127.0.0.1:8090"
SYSTEMD_USER_DIR="$XDG_CONFIG_HOME/systemd/user"
SYSTEMCTL_BIN="systemctl"

# ---------------------------------------------------------------------------
# Ownership & manifest helpers:
# The installer owns only what it wrote when creating it, recorded once from the
# stage folder before rename, passed via files (never argv), and never widened.
# ---------------------------------------------------------------------------
prior_manifest_created() {
  local target="$1"
  [ -f "$MANIFEST_PATH" ] || return 1
  python3 - "$MANIFEST_PATH" "$target" <<'PY' >/dev/null 2>&1
import json, os, sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text())
except Exception:
    sys.exit(1)
want = os.path.realpath(sys.argv[2])
for entry in data.get("entries") or []:
    if isinstance(entry, dict) and entry.get("created") is True:
        p = entry.get("path")
        if isinstance(p, str) and p and os.path.realpath(p) == want:
            sys.exit(0)
sys.exit(1)
PY
}

manifest_get_entry_to_file() {
  local target="$1"
  local out_file="$2"
  [ -f "$MANIFEST_PATH" ] || return 1
  python3 - "$MANIFEST_PATH" "$target" "$out_file" <<'PY' >/dev/null 2>&1
import json, os, sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text())
except Exception:
    sys.exit(1)
want = os.path.realpath(sys.argv[2])
for entry in data.get("entries") or []:
    if isinstance(entry, dict) and entry.get("created") is True:
        p = entry.get("path")
        if isinstance(p, str) and p and os.path.realpath(p) == want:
            Path(sys.argv[3]).write_text(json.dumps(entry))
            sys.exit(0)
sys.exit(1)
PY
}

manifest_has_units() {
  [ -f "$MANIFEST_PATH" ] || return 1
  python3 - "$MANIFEST_PATH" <<'PY' >/dev/null 2>&1
import json, os, sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text())
except Exception:
    sys.exit(1)
for entry in data.get("entries") or []:
    if isinstance(entry, dict) and entry.get("created") is True and entry.get("kind") == "unit":
        p = entry.get("path")
        if isinstance(p, str) and os.path.exists(p):
            sys.exit(0)
sys.exit(1)
PY
}

manifest_init() {
  [ "$DRY_RUN" -eq 0 ] || return 0
  mkdir -p "$DATA_DIR"
  python3 - "$MANIFEST_PATH" "$DATA_DIR" "$CONFIG_DIR" "$STATE_DIR" "$UNIT_MARKER" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

manifest_path = Path(sys.argv[1])
data_dir, config_dir, state_dir, marker = sys.argv[2:6]
if manifest_path.is_symlink():
    print(f"Error: Manifest path {manifest_path} is a symlink. Refusing to overwrite.", file=sys.stderr)
    sys.exit(1)
existing = {}
if manifest_path.exists():
    try:
        loaded = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        print(f"Error: Existing manifest {manifest_path} could not be parsed ({exc}).", file=sys.stderr)
        sys.exit(1)
    if not isinstance(loaded, dict):
        print(f"Error: Existing manifest {manifest_path} is not a JSON object.", file=sys.stderr)
        sys.exit(1)
    existing = loaded

payload = {
    "version": 2,
    "data_dir": data_dir,
    "config_dir": config_dir,
    "state_dir": state_dir,
    "unit_marker": marker,
    "created_config_dir": bool(existing.get("created_config_dir", False)),
    "created_state_dir": bool(existing.get("created_state_dir", False)),
    "entries": existing.get("entries") if isinstance(existing.get("entries"), list) else [],
    "kept": existing.get("kept") if isinstance(existing.get("kept"), list) else [],
}
fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=manifest_path.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(payload, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, manifest_path)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
PY
}

manifest_record_entry() {
  local path="$1" kind="$2" role="$3" extra_file="${4:-}"
  [ "$DRY_RUN" -eq 0 ] || return 0
  python3 - "$MANIFEST_PATH" "$path" "$kind" "$role" "$extra_file" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

manifest_path = Path(sys.argv[1])
path_str, kind, role, extra_file = sys.argv[2:6]
extra = json.loads(Path(extra_file).read_text()) if extra_file else {}
data = json.loads(manifest_path.read_text())
entries = data.setdefault("entries", [])
kept = data.setdefault("kept", [])

norm = os.path.normpath(path_str)
new_entry = {"path": norm, "kind": kind, "role": role, "created": True}
new_entry.update(extra)

# Replace any previous entry for this path with the freshly staged ownership record.
entries = [
    item for item in entries
    if not (isinstance(item, dict) and isinstance(item.get("path"), str) and os.path.normpath(item["path"]) == norm)
]
entries.append(new_entry)
data["entries"] = entries

data["kept"] = [
    k for k in kept
    if not (isinstance(k, dict) and isinstance(k.get("path"), str) and os.path.normpath(k["path"]) == norm)
]

fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=manifest_path.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(data, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, manifest_path)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
PY
  CREATED_SUMMARY+=("$path")
}

manifest_remove_entry() {
  local path="$1"
  [ "$DRY_RUN" -eq 0 ] || return 0
  python3 - "$MANIFEST_PATH" "$path" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

manifest_path = Path(sys.argv[1])
norm = os.path.normpath(sys.argv[2])
data = json.loads(manifest_path.read_text())
entries = data.get("entries") or []
new_entries = [
    item for item in entries
    if not (isinstance(item, dict) and isinstance(item.get("path"), str) and os.path.normpath(item["path"]) == norm)
]
if len(new_entries) == len(entries):
    sys.exit(0)
data["entries"] = new_entries
fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=manifest_path.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(data, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, manifest_path)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
PY
}

manifest_record_kept() {
  local path="$1" role="$2" reason="$3"
  [ "$DRY_RUN" -eq 0 ] || return 0
  python3 - "$MANIFEST_PATH" "$path" "$role" "$reason" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

manifest_path = Path(sys.argv[1])
path_str, role, reason = sys.argv[2], sys.argv[3], sys.argv[4]
data = json.loads(manifest_path.read_text())
entries = data.setdefault("entries", [])
kept = data.setdefault("kept", [])
norm = os.path.normpath(path_str)

# Never downgrade a previously created entry to kept.
for item in entries:
    if isinstance(item, dict) and item.get("created") is True and isinstance(item.get("path"), str):
        if os.path.normpath(item["path"]) == norm:
            sys.exit(0)

new_kept = {"path": norm, "role": role, "reason": reason}
updated = False
for idx, item in enumerate(kept):
    if isinstance(item, dict) and isinstance(item.get("path"), str) and os.path.normpath(item["path"]) == norm:
        kept[idx] = new_kept
        updated = True
        break
if not updated:
    kept.append(new_kept)

fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=manifest_path.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(data, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, manifest_path)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
PY
}

manifest_record_swap_pending() {
  local path="$1" role="$2" reason="$3" old_entry_file="$4"
  [ "$DRY_RUN" -eq 0 ] || return 0
  python3 - "$MANIFEST_PATH" "$path" "$role" "$reason" "$old_entry_file" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

manifest_path = Path(sys.argv[1])
path_str, role, reason, old_entry_path = sys.argv[2:6]
data = json.loads(manifest_path.read_text())
entries = data.setdefault("entries", [])
kept = data.setdefault("kept", [])
norm = os.path.normpath(path_str)

for item in entries:
    if isinstance(item, dict) and item.get("created") is True and isinstance(item.get("path"), str):
        if os.path.normpath(item["path"]) == norm:
            sys.exit(0)

old_entry = json.loads(Path(old_entry_path).read_text())
new_kept = {
    "path": norm,
    "role": role,
    "reason": reason,
    "swap_pending": True,
    "installed_files": old_entry.get("installed_files") or [],
    "installed_dirs": old_entry.get("installed_dirs") or [],
}
updated = False
for idx, item in enumerate(kept):
    if isinstance(item, dict) and isinstance(item.get("path"), str) and os.path.normpath(item["path"]) == norm:
        kept[idx] = new_kept
        updated = True
        break
if not updated:
    kept.append(new_kept)

fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=manifest_path.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(data, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, manifest_path)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
PY
}

cleanup_pending_swap_backups() {
  [ "$DRY_RUN" -eq 0 ] || return 0
  [ -f "$MANIFEST_PATH" ] && [ ! -L "$MANIFEST_PATH" ] || return 0
  python3 - "$MANIFEST_PATH" "$DATA_DIR" <<'PY'
import json, os, shutil, sys, tempfile
from pathlib import Path

sys.stdout.reconfigure(errors="backslashreplace")
sys.stderr.reconfigure(errors="backslashreplace")

def safe_display(name):
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        name = name.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="backslashreplace")
    return repr(name) if ("\n" in name or "\r" in name) else name

def is_clean_rel_list(val):
    if not isinstance(val, list):
        return False
    for item in val:
        if not isinstance(item, str) or not item or "\x00" in item:
            return False
        if os.path.isabs(item) or ".." in Path(item).parts:
            return False
    return True

def check_dir_clean(root_path, recorded_files, recorded_dirs):
    root = Path(root_path)
    allowed_files = set(recorded_files)
    allowed_dirs = set(recorded_dirs) if is_clean_rel_list(recorded_dirs) else None
    unexpected = []
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
    if unexpected:
        sample = ", ".join(safe_display(x) for x in unexpected[:3])
        extra = f" (+{len(unexpected) - 3} more)" if len(unexpected) > 3 else ""
        return f"{sample}{extra}"
    return None

manifest_path = Path(sys.argv[1])
data_real = os.path.realpath(sys.argv[2])
try:
    data = json.loads(manifest_path.read_text())
except (OSError, ValueError):
    sys.exit(0)

kept = data.get("kept")
if not isinstance(kept, list):
    sys.exit(0)

expected_prefixes = {
    "rook_venv_backup": "venv.kept-",
    "voice_venv_backup": "voice-phonon.kept-",
}

changed = False
new_kept = []
for item in kept:
    if not (isinstance(item, dict) and item.get("swap_pending") is True):
        new_kept.append(item)
        continue
    role = item.get("role")
    raw_path = item.get("path")
    rec_files = item.get("installed_files")
    rec_dirs = item.get("installed_dirs")
    prefix = expected_prefixes.get(role)
    if not prefix or not isinstance(raw_path, str) or not os.path.isabs(raw_path):
        new_kept.append(item)
        continue
    norm = os.path.normpath(raw_path)
    if not os.path.exists(norm) and not os.path.islink(norm):
        changed = True
        continue
    if os.path.islink(norm) or not os.path.isdir(norm):
        new_kept.append(item)
        continue
    parent_real = os.path.realpath(os.path.dirname(norm))
    base = os.path.basename(norm)
    if parent_real != data_real or not base.startswith(prefix) or not is_clean_rel_list(rec_files):
        new_kept.append(item)
        continue
    unexpected_msg = check_dir_clean(norm, rec_files, rec_dirs)
    if unexpected_msg is None:
        shutil.rmtree(norm)
        print(f"  Cleaned previous clean environment from interrupted swap: {safe_display(norm)}")
        changed = True
    else:
        kept_clean = {
            "path": norm,
            "role": role,
            "reason": f"previous environment kept because it contains user-added files ({unexpected_msg})",
        }
        new_kept.append(kept_clean)
        print(f"  Kept previous environment at {safe_display(norm)} (contains extra files: {unexpected_msg}).")
        changed = True

if changed:
    data["kept"] = new_kept
    fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=manifest_path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as out:
            os.fchmod(out.fileno(), 0o600)
            json.dump(data, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, manifest_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
PY
}

manifest_remove_kept() {
  local path="$1"
  [ "$DRY_RUN" -eq 0 ] || return 0
  python3 - "$MANIFEST_PATH" "$path" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

manifest_path = Path(sys.argv[1])
norm = os.path.normpath(sys.argv[2])
data = json.loads(manifest_path.read_text())
kept = data.get("kept") or []
new_kept = [
    k for k in kept
    if not (isinstance(k, dict) and isinstance(k.get("path"), str) and os.path.normpath(k["path"]) == norm)
]
if len(new_kept) == len(kept):
    sys.exit(0)
data["kept"] = new_kept
fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=manifest_path.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(data, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, manifest_path)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
PY
}

manifest_mark_created_root() {
  local field="$1"
  [ "$DRY_RUN" -eq 0 ] || return 0
  python3 - "$MANIFEST_PATH" "$field" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

manifest_path = Path(sys.argv[1])
field = sys.argv[2]
data = json.loads(manifest_path.read_text())
if data.get(field) is True:
    sys.exit(0)
data[field] = True
fd, tmp_name = tempfile.mkstemp(prefix=".install-manifest-", suffix=".tmp", dir=manifest_path.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(data, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, manifest_path)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
PY
}

snapshot_venv_to_file() {
  local venv_path="$1"
  local out_file="$2"
  local spec_hash="$3"
  python3 - "$venv_path" "$out_file" "$spec_hash" "$STAGE_MARKER" <<'PY'
import json, os, sys
from pathlib import Path

root = Path(sys.argv[1])
out_file = Path(sys.argv[2])
spec_hash = sys.argv[3]
stage_marker = sys.argv[4]
files_list = []
dirs_list = []
for cur, dirs, files in os.walk(root):
    real_dirs = []
    for d in sorted(dirs):
        if d == "__pycache__":
            continue
        full = os.path.join(cur, d)
        rel = os.path.relpath(full, root)
        if os.path.islink(full):
            files_list.append(rel)
        else:
            dirs_list.append(rel)
            real_dirs.append(d)
    dirs[:] = real_dirs
    for fname in sorted(files):
        if fname == stage_marker or fname.endswith((".pyc", ".pyo")):
            continue
        rel = os.path.relpath(os.path.join(cur, fname), root)
        files_list.append(rel)
out_file.write_text(json.dumps({
    "installed_files": files_list,
    "installed_dirs": dirs_list,
    "spec_hash": spec_hash,
}))
PY
}

compute_venv_spec_hash() {
  local role="$1"
  local req_file="$2"
  local extra_spec="${3:-}"
  python3 - "$PYTHON_PIN" "$role" "$req_file" "$extra_spec" <<'PY'
import hashlib, subprocess, sys
from pathlib import Path

py_pin, role, req_path, extra_spec = sys.argv[1:5]
h = hashlib.sha256()
h.update(f"py={py_pin}\nrole={role}\n".encode())
p = Path(req_path)
if p.is_file():
    h.update(p.read_bytes())
h.update(f"\nextra={extra_spec}\n".encode())
if extra_spec:
    ep = Path(extra_spec)
    if ep.is_file():
        h.update(b"file:")
        h.update(ep.read_bytes())
    elif ep.is_dir():
        res = subprocess.run(["git", "-C", str(ep), "rev-parse", "HEAD"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            h.update(f"git:{res.stdout.strip()}\n".encode())
print(h.hexdigest())
PY
}

check_venv_against_record() {
  local venv_path="$1"
  local record_file="$2"
  python3 - "$venv_path" "$record_file" <<'PY'
import json, os, sys
from pathlib import Path

sys.stdout.reconfigure(errors="backslashreplace")
sys.stderr.reconfigure(errors="backslashreplace")

def safe_display(name):
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        name = name.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="backslashreplace")
    return repr(name) if ("\n" in name or "\r" in name) else name

root = Path(sys.argv[1])
rec = json.loads(Path(sys.argv[2]).read_text())
recorded_files = rec.get("installed_files")
recorded_dirs = rec.get("installed_dirs")
if not isinstance(recorded_files, list) or not all(isinstance(x, str) for x in recorded_files):
    print("no recorded file list")
    sys.exit(1)
allowed_files = set(recorded_files)
allowed_dirs = set(recorded_dirs) if isinstance(recorded_dirs, list) and all(isinstance(x, str) for x in recorded_dirs) else None
unexpected = []
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
if unexpected:
    sample = ", ".join(safe_display(x) for x in unexpected[:3])
    extra = f" (+{len(unexpected) - 3} more)" if len(unexpected) > 3 else ""
    print(f"{sample}{extra}")
    sys.exit(1)
sys.exit(0)
PY
}

dated_backup_path() {
  local base_path="$1"
  local stamp cand idx
  stamp="$(date +%Y%m%d-%H%M%S)"
  cand="${base_path}.kept-${stamp}"
  idx=1
  while [ -e "$cand" ] || [ -L "$cand" ]; do
    cand="${base_path}.kept-${stamp}-${idx}"
    idx=$((idx + 1))
  done
  printf '%s\n' "$cand"
}

dated_replaced_unit_path() {
  local base_path="$1"
  local stamp cand idx
  stamp="$(date +%Y%m%d-%H%M%S)"
  cand="${base_path}.replaced-${stamp}"
  idx=1
  while [ -e "$cand" ] || [ -L "$cand" ]; do
    cand="${base_path}.replaced-${stamp}-${idx}"
    idx=$((idx + 1))
  done
  printf '%s\n' "$cand"
}

if [ "$IS_MAC" -eq 1 ]; then
  say "Rook macOS installer"
else
  say "Rook Linux installer"
fi
say "  Agent:      $AGENT"
say "  Voice:      $VOICE"
say "  Prefix:     $PREFIX"
say "  Source:     $SOURCE"
say "  Recogniser: $AIRTYPE_SPEC ($ASR_NAME)"
say "  Data:       $DATA_DIR"
say "  Config:     $CONFIG_DIR"
say "  Service:    ${SERVICE_CHOICE:-ask}"
if [ -n "$FROM_CACHE" ]; then
  say "  Cache:      $FROM_CACHE"
fi
if [ "$DRY_RUN" -eq 1 ]; then
  say "  Mode:       dry-run (no files will be changed or written)"
fi

# Report offline coverage clearly when --from-cache is used.
CACHE_NEEDS_NET=()
if [ -n "$FROM_CACHE" ]; then
  [ -d "$FROM_CACHE/uv" ] || CACHE_NEEDS_NET+=("uv package cache (no $FROM_CACHE/uv)")
  [ -d "$FROM_CACHE/uv-python" ] || CACHE_NEEDS_NET+=("Python $PYTHON_PIN (no $FROM_CACHE/uv-python)")
  if [ -z "$RECOGNISER_SOURCE" ] && ! compgen -G "$FROM_CACHE/wheels/airtype-*.whl" >/dev/null 2>&1 && [ ! -d "$FROM_CACHE/airtype-src" ]; then
    CACHE_NEEDS_NET+=("AirType package (no $FROM_CACHE/wheels/airtype-*.whl or $FROM_CACHE/airtype-src)")
  fi
  [ -d "$FROM_CACHE/huggingface/hub" ] || CACHE_NEEDS_NET+=("Phonon voice model (no $FROM_CACHE/huggingface/hub)")
  [ -d "$FROM_CACHE/airtype/models" ] || CACHE_NEEDS_NET+=("AirType recogniser model (no $FROM_CACHE/airtype/models)")
  if [ "${#CACHE_NEEDS_NET[@]}" -eq 0 ]; then
    say "  Offline: --from-cache supplies packages, Python, AirType, and both models (no network needed)."
  else
    say "  Cache note: --from-cache is missing items that would fetch from network:"
    for item in "${CACHE_NEEDS_NET[@]}"; do
      say "    - $item"
    done
  fi
fi

# ---------------------------------------------------------------------------
# Step 1: Check the system (read-only; must write nothing on --dry-run)
# ---------------------------------------------------------------------------
step "[1/7] Checking system requirements"

SYS_MISSING=()

if [ "$IS_MAC" -eq 1 ]; then
  MAC_VERSION="$(sw_vers -productVersion)"
  if [ "$(uname -m)" = arm64 ] && [ "${MAC_VERSION%%.*}" -ge 14 ]; then
    say "  OK: macOS $MAC_VERSION on Apple Silicon."
  else
    SYS_MISSING+=("An Apple Silicon Mac with macOS 14 or later (found macOS $MAC_VERSION on $(uname -m)).")
  fi
  if xcode-select -p >/dev/null 2>&1; then
    say "  OK: Xcode Command Line Tools are installed (clang, codesign, git, python3)."
  else
    SYS_MISSING+=("Xcode Command Line Tools. Run: xcode-select --install")
  fi
else  # Linux checks, through the input group note.

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-}"
  OS_LIKE="${ID_LIKE:-}"
  if [ "$OS_ID" = "arch" ] || [[ " $OS_LIKE " == *" arch "* ]]; then
    say "  OK: Arch-based Linux (${PRETTY_NAME:-$OS_ID})."
  else
    SYS_MISSING+=("Arch-based Linux (found ${PRETTY_NAME:-unknown}). Rook only supports Arch with Hyprland today.")
  fi
else
  SYS_MISSING+=("/etc/os-release is missing. Rook only supports Arch-based Linux with Hyprland today.")
fi

if ! command -v pacman >/dev/null 2>&1; then
  SYS_MISSING+=("pacman is not on PATH. Rook requires an Arch-based Linux system.")
fi

HYPR_OK=0
RUNTIME_CHECK_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
SYS_RUNTIME_DIR="/run/user/$(id -u)"
if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
  HYPR_OK=1
elif [[ "${XDG_CURRENT_DESKTOP:-}" == *Hyprland* ]]; then
  HYPR_OK=1
elif compgen -G "$RUNTIME_CHECK_DIR/hypr/*/.socket.sock" >/dev/null 2>&1 || compgen -G "$SYS_RUNTIME_DIR/hypr/*/.socket.sock" >/dev/null 2>&1; then
  HYPR_OK=1
fi
if [ "$HYPR_OK" -eq 1 ]; then
  say "  OK: Hyprland session detected."
else
  SYS_MISSING+=("Hyprland session is not active. Log into a Hyprland session before installing Rook.")
fi

# Check PipeWire socket first so no pulse cookie is written to disk.
PIPEWIRE_OK=0
if [ -S "$RUNTIME_CHECK_DIR/pipewire-0" ] || [ -S "$SYS_RUNTIME_DIR/pipewire-0" ]; then
  PIPEWIRE_OK=1
elif command -v pactl >/dev/null 2>&1 && PULSE_COOKIE=/dev/null pactl info 2>/dev/null | grep -qi "PipeWire"; then
  PIPEWIRE_OK=1
fi
if [ "$PIPEWIRE_OK" -eq 1 ]; then
  say "  OK: PipeWire audio server is running."
else
  SYS_MISSING+=("PipeWire is not running. Start pipewire and pipewire-pulse user services, then try again.")
fi

# GPU OpenGL 4.4 Core probe with cache dirs pointed at /dev/null so nothing is written.
GL_CHECK_PY="$(command -v python3 || command -v python || true)"
if ! compgen -G "/dev/dri/renderD*" >/dev/null 2>&1; then
  SYS_MISSING+=("No GPU render node under /dev/dri/renderD*. Install your GPU drivers and check permissions.")
elif [ -n "$GL_CHECK_PY" ]; then
  GL_INFO="$(HOME=/dev/null XDG_CACHE_HOME=/dev/null MESA_SHADER_CACHE_DISABLE=1 MESA_GLSL_CACHE_DISABLE=1 __GL_SHADER_DISK_CACHE=0 "$GL_CHECK_PY" - <<'PY' 2>&1 || true
import ctypes
try:
    egl = ctypes.CDLL("libEGL.so.1")
    gl = ctypes.CDLL("libGL.so.1")
    egl.eglGetPlatformDisplay.restype = ctypes.c_void_p
    egl.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglGetDisplay.restype = ctypes.c_void_p
    egl.eglGetDisplay.argtypes = [ctypes.c_void_p]
    egl.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    egl.eglBindAPI.argtypes = [ctypes.c_uint]
    egl.eglCreateContext.restype = ctypes.c_void_p
    egl.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    egl.eglMakeCurrent.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglTerminate.argtypes = [ctypes.c_void_p]
    gl.glGetString.restype = ctypes.c_char_p
    gl.glGetString.argtypes = [ctypes.c_uint]
    dpy = egl.eglGetPlatformDisplay(0x31DD, None, None) or egl.eglGetDisplay(None)
    maj, minv = ctypes.c_int(), ctypes.c_int()
    if not dpy or not egl.eglInitialize(dpy, ctypes.byref(maj), ctypes.byref(minv)):
        raise RuntimeError("EGL did not initialize")
    if not egl.eglBindAPI(0x30A2):
        raise RuntimeError("EGL OpenGL API unavailable")
    ctx_attrs = (ctypes.c_int * 7)(0x3098, 4, 0x30FB, 4, 0x30FD, 1, 0x3038)
    ctx = egl.eglCreateContext(dpy, None, None, ctx_attrs)
    if not ctx:
        raise RuntimeError("GPU does not support OpenGL 4.4 Core")
    if not egl.eglMakeCurrent(dpy, None, None, ctx):
        raise RuntimeError("Could not make OpenGL 4.4 Core context current")
    ver = (gl.glGetString(0x1F02) or b"").decode(errors="replace")
    ren = (gl.glGetString(0x1F01) or b"").decode(errors="replace")
    egl.eglTerminate(dpy)
    print(f"OK:{ver} | {ren}")
except Exception as exc:
    print(f"FAIL:{exc}")
PY
)"
  if [[ "$GL_INFO" == OK:* ]]; then
    say "  OK: GPU supports OpenGL 4.4 Core (${GL_INFO#OK:})."
    case "${GL_INFO,,}" in
      *llvmpipe*|*softpipe*|*swrast*|*software*)
        say "  Warning: OpenGL runs in software, not on the GPU, so Rook's overlay will be slow. Install your GPU drivers." ;;
    esac
  else
    SYS_MISSING+=("GPU OpenGL 4.4 Core check failed (${GL_INFO#FAIL:}). Rook's overlay needs Mesa/GPU drivers with OpenGL 4.4 Core.")
  fi
else
  say "  Note: Python is not installed yet, so the OpenGL 4.4 Core check will run after system packages are installed."
fi

if id -Gn | tr ' ' '\n' | grep -qx "input"; then
  say "  OK: User is in the input group for global talk keys."
else
  say "  Note: User is not in the input group yet."
  say "  Rook reads /dev/input so your global push-to-talk key works across Wayland windows."
  say "  Security note: joining the input group lets any program you run read every key press, including passwords."
  say "  If you accept that tradeoff, run this yourself and log out and back in:"
  say "    sudo usermod -aG input \"\$USER\""
fi
fi  # End of the Linux checks.

if [ "${#SYS_MISSING[@]}" -gt 0 ]; then
  for msg in "${SYS_MISSING[@]}"; do
    printf '  Missing: %s\n' "$msg" >&2
  done
  if [ "$DRY_RUN" -eq 0 ]; then
    die "System requirements are not met." "Resolve the missing items above, then run install/install.sh again."
  fi
fi

# ---------------------------------------------------------------------------
# Step 2: System packages (print one pacman line, never run sudo)
# ---------------------------------------------------------------------------
step "[2/7] Checking system packages"

if [ "$IS_MAC" -eq 1 ]; then
  say "  OK: A Mac needs no system packages. uv brings Python, and the wheels bring PortAudio and libsndfile."
else  # Linux packages, through the GTK check.
say "  Required packages command (run yourself if any package is missing):"
say "    sudo pacman -S --needed ${PACMAN_PACKAGES[*]}"

MISSING_PKGS=()
for pkg in "${PACMAN_PACKAGES[@]}"; do
  if [ "$pkg" = "uv" ]; then
    if ! pacman -Q uv >/dev/null 2>&1 && ! command -v uv >/dev/null 2>&1; then
      MISSING_PKGS+=("uv")
    fi
  else
    if ! pacman -Q "$pkg" >/dev/null 2>&1; then
      MISSING_PKGS+=("$pkg")
    fi
  fi
done

if [ "${#MISSING_PKGS[@]}" -gt 0 ]; then
  say "  Missing packages: ${MISSING_PKGS[*]}"
  if [ "$DRY_RUN" -eq 0 ]; then
    die "Missing required Arch packages: ${MISSING_PKGS[*]}." \
        "Run: sudo pacman -S --needed ${MISSING_PKGS[*]}"
  fi
else
  say "  OK: All required system packages are installed (including base-devel and linux-api-headers for evdev)."
fi

MISSING_OPT_PKGS=()
for pkg in "${OPTIONAL_VIDEO_PACKAGES[@]}"; do
  if ! pacman -Q "$pkg" >/dev/null 2>&1; then
    MISSING_OPT_PKGS+=("$pkg")
  fi
done
if [ "${#MISSING_OPT_PKGS[@]}" -gt 0 ]; then
  say "  Note: Optional video viewer packages are not installed: ${MISSING_OPT_PKGS[*]}."
  say "  To enable video playback in Rook's viewer, run:"
  say "    sudo pacman -S --needed ${MISSING_OPT_PKGS[*]}"
fi

if [ -x /usr/bin/python ]; then
  if HOME=/dev/null XDG_CACHE_HOME=/dev/null MESA_SHADER_CACHE_DISABLE=1 MESA_GLSL_CACHE_DISABLE=1 __GL_SHADER_DISK_CACHE=0 GSK_RENDERER=cairo /usr/bin/python -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Gtk4LayerShell', '1.0'); import cairo; from gi.repository import Gtk, Gtk4LayerShell" >/dev/null 2>&1; then
    say "  OK: System /usr/bin/python can load GTK 4, gtk4-layer-shell, and cairo."
  elif [ "$DRY_RUN" -eq 0 ]; then
    die "System /usr/bin/python cannot import GTK 4 or gtk4-layer-shell." \
        "Run: sudo pacman -S --needed python gtk4 gtk4-layer-shell python-gobject python-cairo"
  fi
fi
fi  # End of the Linux packages.

# Clean stale marker-carrying stage folders from any prior SIGKILL, then initialize manifest & disk temp dir.
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$DATA_DIR"
  cleanup_stale_stages "$DATA_DIR" "$(dirname "$PREFIX")" "$XDG_CACHE_HOME/airtype/models"
  DL_TMP="$(make_stage_dir "$DATA_DIR" ".tmp-download")"
  manifest_init
  cleanup_pending_swap_backups
fi

# ---------------------------------------------------------------------------
# Step 3: Install Rook checkout at $PREFIX (stage, record before rename, rename)
# ---------------------------------------------------------------------------
step "[3/7] Installing Rook into $PREFIX"

PREFIX_EXISTED=0
if [ -e "$PREFIX" ] || [ -L "$PREFIX" ]; then
  PREFIX_EXISTED=1
fi

stage_and_install_prefix() {
  local replace_empty="$1"
  STAGE_TMP="$(make_stage_dir "$(dirname "$PREFIX")" ".rook-stage-prefix")"
  run_cmd git clone "$SOURCE" "$STAGE_TMP/checkout"
  [ -f "$STAGE_TMP/checkout/desktop/rook.py" ] || die "Install check failed: desktop/rook.py is missing." "Check that $SOURCE is a valid Rook repository."
  [ -f "$STAGE_TMP/checkout/desktop/relay.py" ] || die "Install check failed: desktop/relay.py is missing." "Check that $SOURCE is a valid Rook repository."
  local clone_commit clone_branch
  clone_commit="$(git -C "$STAGE_TMP/checkout" rev-parse HEAD)"
  clone_branch="$(git -C "$STAGE_TMP/checkout" rev-parse --abbrev-ref HEAD)"
  python3 - "$STAGE_TMP/meta.json" "$clone_commit" "$clone_branch" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"commit": sys.argv[2], "branch": sys.argv[3]}))
PY
  # Record ownership BEFORE the rename so a failure or kill after rename cannot orphan the checkout.
  manifest_record_entry "$PREFIX" "dir" "prefix" "$STAGE_TMP/meta.json"
  if [ "$replace_empty" -eq 1 ]; then
    rmdir "$PREFIX" || die "Could not replace empty folder $PREFIX." "Check permissions on $PREFIX."
  fi
  mv "$STAGE_TMP/checkout" "$PREFIX"
  rm -rf -- "$STAGE_TMP"
  STAGE_TMP=""
}

if [ -L "$PREFIX" ]; then
  die "$PREFIX is a symlink. Refusing to overwrite or follow it." \
      "Pick another path with --prefix DIR or move $PREFIX aside first."
elif [ "$PREFIX_EXISTED" -eq 1 ]; then
  if [ -f "$PREFIX/desktop/rook.py" ]; then
    if prior_manifest_created "$PREFIX"; then
      say "  Existing installer-managed Rook checkout found at $PREFIX. Keeping it and its manifest record unchanged."
    else
      say "  Existing Rook install found at $PREFIX (not created by this installer). Keeping it unchanged."
      manifest_record_kept "$PREFIX" "prefix" "existing install kept unchanged"
    fi
  elif [ -d "$PREFIX" ] && [ -z "$(ls -A "$PREFIX" 2>/dev/null)" ]; then
    say "  Empty folder at $PREFIX. Cloning Rook from $SOURCE into a fresh staging folder first."
    if [ "$DRY_RUN" -eq 1 ]; then
      run_cmd git clone "$SOURCE" "$PREFIX"
    else
      stage_and_install_prefix 1
    fi
  else
    die "$PREFIX already exists and does not look like a Rook install." \
        "Pick another path with --prefix DIR or move $PREFIX aside first."
  fi
else
  if [ "$DRY_RUN" -eq 1 ]; then
    run_cmd mkdir -p "$(dirname "$PREFIX")"
    run_cmd git clone "$SOURCE" "$PREFIX"
  else
    run_cmd mkdir -p "$(dirname "$PREFIX")"
    stage_and_install_prefix 0
  fi
fi

if [ "$DRY_RUN" -eq 0 ]; then
  [ -f "$PREFIX/desktop/rook.py" ] || die "Install check failed: $PREFIX/desktop/rook.py is missing." "Check that $SOURCE is a valid Rook repository."
  [ -f "$PREFIX/desktop/relay.py" ] || die "Install check failed: $PREFIX/desktop/relay.py is missing." "Check that $SOURCE is a valid Rook repository."
  say "  OK: Rook files verified at $PREFIX."
fi

REQ_SUFFIX=""
EVDEV_IMPORT="evdev, "
if [ "$IS_MAC" -eq 1 ]; then
  REQ_SUFFIX="-macos"  # macOS arm64 locks, without the Linux-only evdev.
  EVDEV_IMPORT=""
fi
REQ_ROOK="$PREFIX/install/requirements-rook$REQ_SUFFIX.txt"
REQ_VOICE="$PREFIX/install/requirements-voice$REQ_SUFFIX.txt"
[ -f "$REQ_ROOK" ] || REQ_ROOK="$SCRIPT_DIR/requirements-rook$REQ_SUFFIX.txt"
[ -f "$REQ_VOICE" ] || REQ_VOICE="$SCRIPT_DIR/requirements-voice$REQ_SUFFIX.txt"

# ---------------------------------------------------------------------------
# Step 4: Python environments with uv (staged atomically, recorded once from stage)
# ---------------------------------------------------------------------------
step "[4/7] Creating Python environments with uv"

UV_BIN="$(command -v uv || true)"
[ -n "$UV_BIN" ] || [ "$DRY_RUN" -eq 1 ] || die "uv is not on PATH." "Install uv with: sudo pacman -S --needed uv"

UV_COMMON_ARGS=()
UV_VENV_ARGS=()
UV_ENV_VARS=()

if [ -n "$FROM_CACHE" ]; then
  if [ -d "$FROM_CACHE/uv" ]; then
    UV_ENV_VARS+=("UV_CACHE_DIR=$FROM_CACHE/uv")
    UV_COMMON_ARGS+=(--offline)
  fi
  if [ -d "$FROM_CACHE/uv-python" ]; then
    UV_ENV_VARS+=("UV_PYTHON_INSTALL_DIR=$FROM_CACHE/uv-python")
    UV_VENV_ARGS+=(--no-python-downloads)
  fi
fi

run_uv() {
  if [ "${#UV_ENV_VARS[@]}" -gt 0 ]; then
    run_cmd env "${UV_ENV_VARS[@]}" "$UV_BIN" "$@"
  else
    run_cmd "$UV_BIN" "$@"
  fi
}

install_or_update_venv() {
  local venv_path="$1"
  local role="$2"
  local stage_prefix="$3"
  local req_file="$4"
  local extra_spec="$5"
  local verify_py="$6"
  local label="$7"

  say "  $label: $venv_path (Python $PYTHON_PIN, hashes verified)"
  local existed=0
  if [ -e "$venv_path" ] || [ -L "$venv_path" ]; then
    existed=1
  fi

  if [ -L "$venv_path" ]; then
    die "$venv_path is a symlink. Refusing to overwrite or follow it." \
        "Move $venv_path aside before running install/install.sh."
  fi

  local spec_hash=""
  if [ "$DRY_RUN" -eq 0 ]; then
    spec_hash="$(compute_venv_spec_hash "$role" "$req_file" "$extra_spec")"
  fi

  if [ "$existed" -eq 1 ]; then
    if [ ! -x "$venv_path/bin/python" ]; then
      die "$venv_path already exists and is not an installer-managed Python environment." \
          "Move or remove $venv_path first; the installer never deletes pre-existing folders."
    fi
    if prior_manifest_created "$venv_path"; then
      if [ "$DRY_RUN" -eq 1 ]; then
        say "  Would check existing installer-managed environment at $venv_path; rebuild in stage and swap only if changed."
        return 0
      fi
      local old_entry_file="$DL_TMP/old-${role}-entry.json"
      manifest_get_entry_to_file "$venv_path" "$old_entry_file" \
        || die "Manifest record missing for $venv_path." "Inspect $MANIFEST_PATH."
      local old_hash=""
      old_hash="$(python3 -c 'import json,sys; d=json.loads(open(sys.argv[1]).read()); print(d.get("spec_hash") or "")' "$old_entry_file")"
      if [ -n "$old_hash" ] && [ "$old_hash" = "$spec_hash" ] && "$venv_path/bin/python" -c "$verify_py"; then
        say "  Existing installer-managed environment at $venv_path is up to date. Keeping it unchanged."
        return 0
      fi
      # Must change the venv: build replacement in a fresh stage folder, snapshot stage, swap,
      # and remove the old folder only if every file in it is in its original recorded list.
      say "  Existing installer-managed environment at $venv_path needs update. Building replacement in a fresh stage folder."
      STAGE_TMP="$(make_stage_dir "$DATA_DIR" "$stage_prefix")"
      local staged_venv="$STAGE_TMP/venv"
      run_uv venv --relocatable --python "$PYTHON_PIN" "${UV_VENV_ARGS[@]}" "$staged_venv"
      run_uv pip install "${UV_COMMON_ARGS[@]}" --require-hashes --python "$staged_venv/bin/python" -r "$req_file"
      if [ -n "$extra_spec" ]; then
        run_uv pip install "${UV_COMMON_ARGS[@]}" --python "$staged_venv/bin/python" --no-deps "$extra_spec"
      fi
      "$staged_venv/bin/python" -c "$verify_py" \
        || die "$label check failed." "Check uv output above and re-run install/install.sh."
      snapshot_venv_to_file "$staged_venv" "$STAGE_TMP/new-meta.json" "$spec_hash"
      local old_backup
      old_backup="$(dated_backup_path "$venv_path")"
      # Record dated backup (with its original file list) BEFORE moving old venv aside so a SIGKILL mid-swap
      # never leaves it unrecorded, and a rerun can clean it if every file still matches its recorded list.
      manifest_record_swap_pending "$old_backup" "${role}_backup" "previous environment moved aside during swap" "$old_entry_file"
      mv "$venv_path" "$old_backup"
      manifest_record_entry "$venv_path" "dir" "$role" "$STAGE_TMP/new-meta.json"
      mv "$staged_venv" "$venv_path"
      local unexpected_msg=""
      if unexpected_msg="$(check_venv_against_record "$old_backup" "$old_entry_file")"; then
        rm -rf -- "$old_backup"
        manifest_remove_kept "$old_backup"
        say "  Removed previous clean environment after swap."
      else
        manifest_record_kept "$old_backup" "${role}_backup" "previous environment kept because it contains user-added files ($unexpected_msg)"
        say "  Kept previous environment at $old_backup (contains extra files: $unexpected_msg)."
      fi
      rm -rf -- "$STAGE_TMP"
      STAGE_TMP=""
      return 0
    else
      if [ "$USE_EXISTING_ENV" -eq 0 ]; then
        die "Existing Python environment at $venv_path was not created by this installer. Refusing to modify it." \
            "Move $venv_path aside so the installer can create its own, or pass --use-existing-env to use it as it is without installing anything into it."
      fi
      say "  Using existing environment at $venv_path as it is (--use-existing-env; installed nothing into it)."
      if [ "$DRY_RUN" -eq 0 ]; then
        "$venv_path/bin/python" -c "$verify_py" \
          || die "$label check failed in existing environment $venv_path." "Install the needed packages yourself, or move $venv_path aside and re-run without --use-existing-env."
        manifest_record_kept "$venv_path" "$role" "pre-existing environment kept untouched (--use-existing-env)"
      fi
      return 0
    fi
  fi

  # Fresh creation: stage, verify, snapshot stage to file, record ownership BEFORE rename, then rename.
  if [ "$DRY_RUN" -eq 1 ]; then
    run_cmd mkdir -p "$DATA_DIR"
    run_uv venv --relocatable --python "$PYTHON_PIN" "${UV_VENV_ARGS[@]}" "$venv_path"
    run_uv pip install "${UV_COMMON_ARGS[@]}" --require-hashes --python "$venv_path/bin/python" -r "$req_file"
    if [ -n "$extra_spec" ]; then
      run_uv pip install "${UV_COMMON_ARGS[@]}" --python "$venv_path/bin/python" --no-deps "$extra_spec"
    fi
  else
    STAGE_TMP="$(make_stage_dir "$DATA_DIR" "$stage_prefix")"
    local staged_venv="$STAGE_TMP/venv"
    run_uv venv --relocatable --python "$PYTHON_PIN" "${UV_VENV_ARGS[@]}" "$staged_venv"
    run_uv pip install "${UV_COMMON_ARGS[@]}" --require-hashes --python "$staged_venv/bin/python" -r "$req_file"
    if [ -n "$extra_spec" ]; then
      run_uv pip install "${UV_COMMON_ARGS[@]}" --python "$staged_venv/bin/python" --no-deps "$extra_spec"
    fi
    "$staged_venv/bin/python" -c "$verify_py" \
      || die "$label check failed." "Check uv output above and re-run install/install.sh."
    snapshot_venv_to_file "$staged_venv" "$STAGE_TMP/meta.json" "$spec_hash"
    # Record ownership BEFORE the rename so any failure after rename cannot orphan the folder.
    manifest_record_entry "$venv_path" "dir" "$role" "$STAGE_TMP/meta.json"
    mv "$staged_venv" "$venv_path"
    rm -rf -- "$STAGE_TMP"
    STAGE_TMP=""
  fi
}

# 4a. Rook and recogniser environment ($ROOK_VENV)
install_or_update_venv \
  "$ROOK_VENV" \
  "rook_venv" \
  ".rook-stage-venv" \
  "$REQ_ROOK" \
  "$AIRTYPE_SPEC" \
  "import airtype.pipeline, ${EVDEV_IMPORT}sherpa_onnx, sounddevice, soundfile, numpy; print('  OK: Rook + recogniser imports verified (airtype', __import__('airtype').__version__ + ').')" \
  "Environment 1 (Rook + recogniser)"

# 4b. Small voice environment ($VOICE_VENV)
install_or_update_venv \
  "$VOICE_VENV" \
  "voice_venv" \
  ".rook-stage-voice" \
  "$REQ_VOICE" \
  "" \
  "import ptts, numpy; print('  OK: Small voice imports verified (ptts', ptts.__version__ + ').')" \
  "Environment 2 (small voice, Phonon)"

# 4c. Render MCP script environment
say "  Environment 3 (render MCP tool): uv script cache for desktop/render_tool.py (mcp==$MCP_PIN)"
if [ "$DRY_RUN" -eq 1 ]; then
  say "+ uv run --with mcp==$MCP_PIN --no-project python -c 'import mcp.server.mcpserver'"
else
  if ! (
    if [ "${#UV_ENV_VARS[@]}" -gt 0 ]; then
      env "${UV_ENV_VARS[@]}" "$UV_BIN" run "${UV_COMMON_ARGS[@]}" "${UV_VENV_ARGS[@]}" \
        --python "$ROOK_VENV/bin/python" --with "mcp==$MCP_PIN" --no-project \
        python -c "import mcp.server.mcpserver" >/dev/null 2>&1
    else
      "$UV_BIN" run "${UV_COMMON_ARGS[@]}" "${UV_VENV_ARGS[@]}" \
        --python "$ROOK_VENV/bin/python" --with "mcp==$MCP_PIN" --no-project \
        python -c "import mcp.server.mcpserver" >/dev/null 2>&1
    fi
  ); then
    say "  Note: Could not pre-warm render_tool.py MCP cache now. uv will fetch mcp>=2 on first launch."
  else
    say "  OK: Render MCP tool environment verified (mcp $MCP_PIN)."
  fi
fi

# ---------------------------------------------------------------------------
# Step 5: Speech models (explicit choices, pinned revisions, SHA256 + size checks, disk TMPDIR)
# ---------------------------------------------------------------------------
step "[5/7] Setting up speech models"

INCOMPLETE_REASONS=()
HF_HUB_DIR="$XDG_CACHE_HOME/huggingface/hub"
PHONON_SNAP_DIR="$HF_HUB_DIR/models--gradium--phonon-31m-en/snapshots/$PHONON_MODEL_REV"
PHONON_VOICES_SNAP_DIR="$HF_HUB_DIR/models--gradium--phonon-voices/snapshots/$PHONON_VOICES_REV"

verify_phonon_checksums() {
  "$ROOK_VENV/bin/python" - "$PHONON_SNAP_DIR" "$PHONON_VOICES_SNAP_DIR" <<'PY'
import hashlib, sys
from pathlib import Path

model_dir, voices_dir = Path(sys.argv[1]), Path(sys.argv[2])
expected = [
    (model_dir / "config.json", 4634, "b5d0f88353638370d94035b7d73d7d6577c0554d78f8d7ecfd40490aae39ae85"),
    (model_dir / "model.q8.gguf", 64512352, "a7d9aad2cd6dc66473f24a08bc6d2939030ef4d751ef82349361fbef3272dbae"),
    (model_dir / "tokenizer.json", 277967, "691a00068fa7b989f2f3e5ae5daa2d1a5bb319f2d5360deafcfb19a8bb6e7936"),
    (model_dir / "default-voice.safetensors", 256136, "dc537478eaadc1a5257fcda2e3501ab81e14c111a5d95a5838f350db2afd0f1a"),
    (voices_dir / "voices.jsonl", 33407, "874f34998ce581b94f2b8912aa015639f52b5fd62eba3ba11e1b64dcaed7d802"),
    (voices_dir / "voices/d9XCyhjo4JhkHF1d.safetensors", 256136, "eab20e4f159b48cfbc01b1885804e24f681f80e7a64f909182763a4e3361bee8"),
]
for path, want_size, want_sha in expected:
    if not path.is_file():
        print(f"Missing model file: {path}", file=sys.stderr)
        sys.exit(1)
    size = path.stat().st_size
    if size != want_size:
        print(f"Size mismatch for {path.name}: got {size}, expected {want_size}", file=sys.stderr)
        sys.exit(1)
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    got_sha = h.hexdigest()
    if got_sha != want_sha:
        print(f"SHA256 mismatch for {path.name}: got {got_sha}, expected {want_sha}", file=sys.stderr)
        sys.exit(1)
PY
}

verify_asr_checksums() {
  local asr_name="$1"
  local asr_dir="$2"
  "$ROOK_VENV/bin/python" - "$asr_name" "$asr_dir" <<'PY'
import hashlib, sys
from pathlib import Path

name, folder = sys.argv[1], Path(sys.argv[2])
known = {
    "parakeet-unified-en-0.6b-int8": [
        ("encoder.int8.onnx", 654040552, "6716910b7a0833997fec7a410494c995d70124001a0e9b66d6370d6aced577e0"),
        ("decoder.int8.onnx", 7257753, "a5e223392c90e75f8144cdb5eb95af7625db389e39edef2bd1a9c872b3298fe6"),
        ("joiner.int8.onnx", 1735860, "869f43f7d24595c55581ad3bf249a935fb8a71389fbdaa7504b9f46f93140f8a"),
        ("tokens.txt", 8952, "dc0b4584ab2e4ddbf888425c076c61b736e7356a015250db7d307e6f1a8188ff"),
    ],
    "parakeet-tdt-0.6b-v3-int8": [
        ("encoder.int8.onnx", 652282294, "1afbe69c1ffdabee94755f42e4daf1d93549131a3da11356bda84fcef0f2c479"),
        ("decoder.int8.onnx", 11845274, "0222a86147299d4dee90edf95b6d13827edb42ad8b7c9cf0b2582f030937c0b5"),
        ("joiner.int8.onnx", 6355277, "cbd02f3696e9944970111fb439d9c3fd365a80374565f13f2b9c7007d253fc98"),
        ("tokens.txt", 93939, "d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d"),
    ],
}
checks = known.get(name)
if not checks:
    print(f"No pinned checksums for recogniser model {name}; verifying files are non-empty.", file=sys.stderr)
    sys.exit(0)
for fname, want_size, want_sha in checks:
    path = folder / fname
    if not path.is_file():
        print(f"Missing recogniser file: {path}", file=sys.stderr)
        sys.exit(1)
    size = path.stat().st_size
    if size != want_size:
        print(f"Size mismatch for {fname}: got {size}, expected {want_size}", file=sys.stderr)
        sys.exit(1)
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    got_sha = h.hexdigest()
    if got_sha != want_sha:
        print(f"SHA256 mismatch for {fname}: got {got_sha}, expected {want_sha}", file=sys.stderr)
        sys.exit(1)
PY
}

copy_hf_from_cache() {
  local src_hub="$1"
  local dst_hub="$2"
  "$ROOK_VENV/bin/python" - "$src_hub" "$dst_hub" "$PHONON_MODEL_REV" "$PHONON_VOICES_REV" <<'PY'
import os, shutil, sys
from pathlib import Path

src_hub, dst_hub, model_rev, voices_rev = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]

def copy_repo(repo_dir_name, rev, skip_names=()):
    src_repo = src_hub / repo_dir_name
    src_snap = src_repo / "snapshots" / rev
    if not src_snap.is_dir():
        raise FileNotFoundError(f"Missing cached snapshot: {src_snap}")
    dst_repo = dst_hub / repo_dir_name
    dst_snap = dst_repo / "snapshots" / rev
    dst_blobs = dst_repo / "blobs"
    dst_refs = dst_repo / "refs"
    dst_snap.mkdir(parents=True, exist_ok=True)
    dst_blobs.mkdir(parents=True, exist_ok=True)
    dst_refs.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src_snap):
        rel_root = Path(root).relative_to(src_snap)
        (dst_snap / rel_root).mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in skip_names:
                continue
            src_file = Path(root) / name
            dst_file = dst_snap / rel_root / name
            if dst_file.exists() or dst_file.is_symlink():
                continue
            if src_file.is_symlink():
                real = src_file.resolve(strict=True)
                dst_blob = dst_blobs / real.name
                if not dst_blob.exists():
                    shutil.copy2(real, dst_blob)
                dst_file.symlink_to(os.path.relpath(dst_blob, dst_file.parent))
            else:
                shutil.copy2(src_file, dst_file)
    ref_main = src_repo / "refs" / "main"
    if ref_main.is_file():
        shutil.copy2(ref_main, dst_refs / "main")

copy_repo("models--gradium--phonon-31m-en", model_rev, skip_names=("model.safetensors",))
copy_repo("models--gradium--phonon-voices", voices_rev)
PY
}

# 5a. Small voice model (Phonon 31M English q8 + Miles voice, pinned revisions)
PHONON_READY=0
if [ "$DRY_RUN" -eq 0 ] && verify_phonon_checksums >/dev/null 2>&1; then
  PHONON_READY=1
fi

if [ "$PHONON_READY" -eq 1 ]; then
  say "  OK: Small voice model (Phonon 31M EN, q8) is already cached and checksum-verified."
else
  say "  Small voice model: Gradium Phonon 31M English (q8) plus default voice (Miles)."
  say "  Pinned source:     $PHONON_MODEL_SPEC and $PHONON_VOICES_SPEC"
  say "  Download size:     about 65 MB (62 MiB on disk)."
  if [ "$DRY_RUN" -eq 1 ]; then
    say "  Would check --voice-model (${VOICE_MODEL_CHOICE:-ask}) and fetch Phonon into $HF_HUB_DIR using disk TMPDIR."
  elif decide_yes_no "--voice-model" "$VOICE_MODEL_CHOICE" "  Download the small voice model (about 65 MB)?"; then
    if [ -n "$FROM_CACHE" ] && [ -d "$FROM_CACHE/huggingface/hub" ]; then
      say "  Copying small voice model from local cache ($FROM_CACHE/huggingface/hub)..."
      copy_hf_from_cache "$FROM_CACHE/huggingface/hub" "$HF_HUB_DIR"
      verify_phonon_checksums \
        || die "Small voice model checksum verification failed after copying from cache." \
               "Check $FROM_CACHE/huggingface/hub for partial or corrupted files."
      TMPDIR="$DL_TMP" XDG_CACHE_HOME="$XDG_CACHE_HOME" HF_HUB_OFFLINE=1 "$VOICE_VENV/bin/python" - "$PHONON_MODEL_SPEC" "$PHONON_VOICES_SPEC" <<'PY' \
        || die "Small voice model failed synthesis verification offline." "Check $HF_HUB_DIR and re-run install/install.sh."
import ptts, sys
ptts.set_num_threads(2)
t = ptts.TTS(model=sys.argv[1], voice_catalog=sys.argv[2], quant="q8", lang="en")
t.synth("Ready.", voice="Miles")
print("  OK: Small voice model verified offline (checksums + synthesis).")
PY
    else
      say "  Downloading small voice model at pinned revisions (using disk temp dir $DL_TMP)..."
      TMPDIR="$DL_TMP" XDG_CACHE_HOME="$XDG_CACHE_HOME" "$VOICE_VENV/bin/python" - "$PHONON_MODEL_SPEC" "$PHONON_VOICES_SPEC" <<'PY' \
        || die "Could not download or verify the small voice model." "Check your internet connection and re-run install/install.sh."
import ptts, sys
ptts.set_num_threads(2)
t = ptts.TTS(model=sys.argv[1], voice_catalog=sys.argv[2], quant="q8", lang="en")
t.synth("Ready.", voice="Miles")
PY
      verify_phonon_checksums \
        || die "Small voice model checksum verification failed after download." \
               "Remove $HF_HUB_DIR/models--gradium--phonon-* and re-run install/install.sh."
      say "  OK: Small voice model downloaded and verified (checksums + synthesis)."
    fi
  else
    say "  Skipped small voice model download."
    INCOMPLETE_REASONS+=("small voice model (--voice-model yes)")
  fi
fi

# 5b. Recogniser model (AirType STT)
AIRTYPE_CONFIG_DIR="$XDG_CONFIG_HOME/airtype"
AIRTYPE_CONFIG_FILE="$AIRTYPE_CONFIG_DIR/config.json"
AIRTYPE_MODELS_DIR="$XDG_CACHE_HOME/airtype/models"

if [ "$DRY_RUN" -eq 1 ]; then
  say "  Recogniser model: $ASR_NAME (--recogniser-model $RECOGNISER_MODEL)."
  say "  Official source:  github.com/k2-fsa/sherpa-onnx or Hugging Face (per AirType registry)."
  say "  Download size:    about 490 MB download (about 670 MB on disk)."
  say "  Would check --recogniser (${RECOGNISER_CHOICE:-ask}) and fetch into $AIRTYPE_MODELS_DIR using disk TMPDIR."
else
  ASR_META=()  # A read loop, not mapfile, which bash 3.2 on macOS lacks.
  while IFS= read -r ASR_LINE; do
    ASR_META+=("$ASR_LINE")
  done < <(XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_CACHE_HOME="$XDG_CACHE_HOME" \
    "$ROOK_VENV/bin/python" - "$ASR_NAME" <<'PY'
import sys
from airtype.asr import default_model_dir, model_exists
from airtype.registry import MODEL_REGISTRY
spec = MODEL_REGISTRY[sys.argv[1]]
print(spec.name)
print(spec.dir_name)
print(spec.size_label)
print(spec.url or f"https://huggingface.co/{spec.hf_repo}")
print(str(default_model_dir(spec)))
print("1" if model_exists(spec) else "0")
PY
  )
  ASR_NAME="${ASR_META[0]}"
  ASR_DIR_NAME="${ASR_META[1]}"
  ASR_SIZE="${ASR_META[2]}"
  ASR_SOURCE="${ASR_META[3]}"
  ASR_MODEL_DIR="${ASR_META[4]}"
  ASR_EXISTS="${ASR_META[5]}"

  if [ "$ASR_EXISTS" = "1" ] && verify_asr_checksums "$ASR_NAME" "$ASR_MODEL_DIR" >/dev/null 2>&1; then
    say "  OK: Recogniser model ($ASR_NAME) is already cached and checksum-verified at $ASR_MODEL_DIR."
  else
    say "  Recogniser model: $ASR_NAME"
    say "  Official source:  $ASR_SOURCE"
    say "  Download size:    $ASR_SIZE"
    if decide_yes_no "--recogniser" "$RECOGNISER_CHOICE" "  Download the speech recogniser model ($ASR_SIZE)?"; then
      mkdir -p "$AIRTYPE_CONFIG_DIR" "$AIRTYPE_MODELS_DIR"
      if [ ! -f "$AIRTYPE_CONFIG_FILE" ]; then
        "$ROOK_VENV/bin/python" - "$AIRTYPE_CONFIG_FILE" "$ASR_NAME" <<'PY'
import json, sys
from pathlib import Path
from airtype.config import default_config
cfg = default_config()
cfg["model"] = sys.argv[2]
cfg["model_download_approved"] = True
Path(sys.argv[1]).write_text(json.dumps(cfg, indent=2) + "\n")
PY
      fi
      if [ -n "$FROM_CACHE" ] && [ -d "$FROM_CACHE/airtype/models/$ASR_DIR_NAME" ]; then
        say "  Copying recogniser model from local cache ($FROM_CACHE/airtype/models/$ASR_DIR_NAME)..."
        if [ -e "$ASR_MODEL_DIR" ] || [ -L "$ASR_MODEL_DIR" ]; then
          die "Existing recogniser model folder at $ASR_MODEL_DIR failed verification." \
              "Move or remove $ASR_MODEL_DIR and re-run install/install.sh."
        fi
        mkdir -p "$(dirname "$ASR_MODEL_DIR")"
        STAGE_TMP="$(make_stage_dir "$(dirname "$ASR_MODEL_DIR")" ".rook-stage-asr")"
        if [ "$IS_MAC" -eq 1 ]; then
          cp -a "$FROM_CACHE/airtype/models/$ASR_DIR_NAME" "$STAGE_TMP/model"
        else
          cp -a --reflink=auto "$FROM_CACHE/airtype/models/$ASR_DIR_NAME" "$STAGE_TMP/model"
        fi
        verify_asr_checksums "$ASR_NAME" "$STAGE_TMP/model" \
          || die "Recogniser model checksum verification failed in cache." "Check $FROM_CACHE/airtype/models/$ASR_DIR_NAME."
        mv "$STAGE_TMP/model" "$ASR_MODEL_DIR"
        rm -rf -- "$STAGE_TMP"
        STAGE_TMP=""
      else
        say "  Downloading recogniser model (using disk temp dir $DL_TMP, never /tmp)..."
        TMPDIR="$DL_TMP" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_CACHE_HOME="$XDG_CACHE_HOME" \
          "$ROOK_VENV/bin/python" -c "import sys; from airtype.asr import ensure_model_download; from airtype.registry import MODEL_REGISTRY; ensure_model_download(MODEL_REGISTRY[sys.argv[1]], progress=True)" "$ASR_NAME" \
          || die "Could not download the speech recogniser model ($ASR_NAME)." "Check your internet connection and re-run install/install.sh."
      fi
      XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_CACHE_HOME="$XDG_CACHE_HOME" \
        "$ROOK_VENV/bin/python" -c "import sys; from airtype.asr import model_exists; from airtype.registry import MODEL_REGISTRY; assert model_exists(MODEL_REGISTRY[sys.argv[1]])" "$ASR_NAME" \
        || die "Recogniser model files are incomplete at $ASR_MODEL_DIR." "Remove $ASR_MODEL_DIR and re-run install/install.sh."
      verify_asr_checksums "$ASR_NAME" "$ASR_MODEL_DIR" \
        || die "Recogniser model checksum verification failed at $ASR_MODEL_DIR." "Remove $ASR_MODEL_DIR and re-run install/install.sh."
      say "  OK: Recogniser model verified (checksums + sizes) at $ASR_MODEL_DIR."
    else
      say "  Skipped recogniser model download."
      INCOMPLETE_REASONS+=("speech recogniser model (--recogniser yes)")
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Step 6: Config folder with default settings (preserve symlinks, never overwrite bad JSON)
# ---------------------------------------------------------------------------
step "[6/7] Setting up config folder at $CONFIG_DIR"

SETTINGS_FILE="$CONFIG_DIR/settings.json"
SKILLS_DIR="$CONFIG_DIR/skills"

if [ "$DRY_RUN" -eq 1 ]; then
  say "  Would create $CONFIG_DIR (mode 0700) and $SKILLS_DIR (mode 0700)."
  if [ -f "$SETTINGS_FILE" ] || [ -L "$SETTINGS_FILE" ]; then
    say "  Existing $SETTINGS_FILE would be parsed and preserved (writing through symlinks, never overwriting invalid JSON)."
  else
    say "  Would write default settings to $SETTINGS_FILE (agent=$AGENT, voice_engine=$VOICE)."
  fi
  say "  Would copy the starter personality to $CONFIG_DIR/personality.md when that file does not exist."
else
  if [ ! -e "$CONFIG_DIR" ] && [ ! -L "$CONFIG_DIR" ]; then
    manifest_mark_created_root "created_config_dir"
  fi
  if [ ! -e "$STATE_DIR" ] && [ ! -L "$STATE_DIR" ]; then
    manifest_mark_created_root "created_state_dir"
    mkdir -p -m 0700 "$STATE_DIR"
  fi
  mkdir -p -m 0700 "$CONFIG_DIR" "$SKILLS_DIR"
  if [ -f "$SETTINGS_FILE" ] || [ -L "$SETTINGS_FILE" ]; then
    say "  Existing settings found at $SETTINGS_FILE. Checking JSON and keeping your values."
  fi
  "$ROOK_VENV/bin/python" - "$SETTINGS_FILE" "$PREFIX/desktop" "$AGENT" "$AGENT_SET" "$VOICE" "$VOICE_SET" "$MEDIUM_URL" \
    "$RECOGNISER_MODEL" "$RECOGNISER_MODEL_SET" <<'PY'
import json, os, stat, sys, tempfile
from pathlib import Path

path = Path(sys.argv[1])
desktop_dir = sys.argv[2]
agent, agent_set = sys.argv[3], sys.argv[4] == "1"
voice, voice_set = sys.argv[5], sys.argv[6] == "1"
medium_url = sys.argv[7] if voice == "medium" else ""  # The local medium voice server this installer sets up.
recogniser, recogniser_set = sys.argv[8], sys.argv[9] == "1"

# Share desktop/settings.py's atomic_write_text helper when available (e.g. after portability merge).
write_fn = None
if desktop_dir and os.path.isdir(desktop_dir):
    sys.path.insert(0, desktop_dir)
    try:
        import settings as rook_settings
        write_fn = getattr(rook_settings, "atomic_write_text", None)
    except Exception:
        write_fn = None

target = path.resolve() if path.is_symlink() else path
existing = None
existing_mode = None
if target.exists():
    existing_mode = stat.S_IMODE(target.stat().st_mode)
    try:
        loaded = json.loads(target.read_text())
    except (OSError, ValueError) as exc:
        print(f"Error: Existing settings file {path} could not be parsed ({exc}). Refusing to overwrite it.", file=sys.stderr)
        print(f"Fix: Repair or move {path}, then re-run install/install.sh.", file=sys.stderr)
        sys.exit(1)
    if not isinstance(loaded, dict):
        print(f"Error: Existing settings file {path} must be a JSON object. Refusing to overwrite it.", file=sys.stderr)
        print(f"Fix: Repair or move {path}, then re-run install/install.sh.", file=sys.stderr)
        sys.exit(1)
    existing = loaded
    if existing_mode & 0o077:
        print(f"  Note: Keeping existing mode {oct(existing_mode)} on {path}. Consider: chmod 600 {path}")

defaults = {
    "agent": agent,
    "voice_engine": voice,
    "voice": "Miles",
    "voice_pace": -0.25,
    "voice_volume": 0.5,
    "voice_temperature": 0.6,
    "recogniser_model": recogniser,
    "previous": {},
}
if medium_url:
    defaults["medium_voice_url"] = medium_url

if existing is None:
    merged = defaults
    target_mode = 0o600
else:
    merged = {**defaults, **existing}
    if agent_set:
        merged["agent"] = agent
    if recogniser_set:
        merged["recogniser_model"] = recogniser
    if voice_set:
        merged["voice_engine"] = voice
        if medium_url:
            merged["medium_voice_url"] = medium_url
    if "previous" not in merged or not isinstance(merged["previous"], dict):
        merged["previous"] = {}
    if merged == existing:
        sys.exit(0)
    target_mode = existing_mode

text = json.dumps(merged, indent=2) + "\n"
if write_fn is not None:
    write_fn(path, text, mode=target_mode)
else:
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as out:
            os.fchmod(out.fileno(), target_mode)
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
PY
  say "  OK: Settings ready at $SETTINGS_FILE (agent=$AGENT, voice_engine=$VOICE, recogniser_model=$RECOGNISER_MODEL)."
  # The starter personality is the user's own file from now on: copied once, never overwritten, and not in the
  # manifest, so uninstall keeps it.
  PERSONALITY_FILE="$CONFIG_DIR/personality.md"
  if [ ! -e "$PERSONALITY_FILE" ] && [ ! -L "$PERSONALITY_FILE" ] && [ -f "$PREFIX/prompts/personality.md" ]; then
    (umask 077 && cp -n "$PREFIX/prompts/personality.md" "$PERSONALITY_FILE")
    say "  OK: Starter personality copied to $PERSONALITY_FILE. Edit it as you like."
  fi
fi

if [ "$VOICE" = "medium" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    say "  Would install the medium voice in $MEDIUM_DIR with $PREFIX/install/medium-voice.sh (about 3.3 GB)."
  else
    # Own the folder only when this installer creates it. It is recorded before the download, so an
    # interrupted install stays owned, and uninstall keeps it until a finished install records its files.
    if [ ! -e "$MEDIUM_DIR" ] && [ ! -L "$MEDIUM_DIR" ]; then
      printf '{"installed_files": [], "installed_dirs": []}' >"$DL_TMP/medium-voice-meta.json"
      manifest_record_entry "$MEDIUM_DIR" "dir" "medium_voice" "$DL_TMP/medium-voice-meta.json"
    fi
    # On a Mac the voice runs as its own launchd agent. Uninstall removes it when this installer made it.
    MEDIUM_PLIST="$HOME/Library/LaunchAgents/com.rook.medium-voice.plist"
    MEDIUM_PLIST_OURS=0
    if [ "$IS_MAC" -eq 1 ] && { [ ! -e "$MEDIUM_PLIST" ] || prior_manifest_created "$MEDIUM_PLIST"; }; then
      MEDIUM_PLIST_OURS=1
    fi
    # On a Mac, the voice's launchd agent starts now only when the login service is chosen.
    MEDIUM_FLAG=""
    if [ "$SERVICE_CHOICE" = "no" ] || { [ "$SERVICE_CHOICE" != "yes" ] && [ "$ASSUME_YES" -ne 1 ]; }; then
      MEDIUM_FLAG="--no-start"
    fi
    ROOK_PYTHON="$ROOK_VENV/bin/python" sh "$PREFIX/install/medium-voice.sh" $MEDIUM_FLAG \
      || die "The medium voice did not install." "Re-run install/install.sh, or use --voice small."
    if [ "$MEDIUM_PLIST_OURS" -eq 1 ] && [ -f "$MEDIUM_PLIST" ] && [ ! -L "$MEDIUM_PLIST" ]; then
      python3 -c 'import hashlib,json,sys; print(json.dumps({"sha256": hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest()}))' \
        "$MEDIUM_PLIST" >"$DL_TMP/medium-plist-meta.json"
      manifest_record_entry "$MEDIUM_PLIST" "unit" "launchd_plist" "$DL_TMP/medium-plist-meta.json"
    fi
    if prior_manifest_created "$MEDIUM_DIR"; then
      snapshot_venv_to_file "$MEDIUM_DIR" "$DL_TMP/medium-voice-meta.json" "medium-voice"
      manifest_record_entry "$MEDIUM_DIR" "dir" "medium_voice" "$DL_TMP/medium-voice-meta.json"
    else
      manifest_record_kept "$MEDIUM_DIR" "medium_voice" "pre-existing folder kept untouched by uninstall"
    fi
    say "  OK: Medium voice installed in $MEDIUM_DIR."
  fi
fi

if [ "$AGENT" = "claude" ]; then
  if command -v claude >/dev/null 2>&1; then
    say "  OK: claude CLI found at $(command -v claude). Sign in by hand with: claude auth login"
  else
    say "  Note: claude CLI is not on PATH yet. Install Claude Code and sign in with: claude auth login"
  fi
elif [ "$AGENT" = "codex" ]; then
  if command -v codex >/dev/null 2>&1; then
    say "  OK: codex CLI found at $(command -v codex). Sign in to Codex by hand, then run once by hand: codex mcp login t3"
  else
    say "  Note: codex CLI is not on PATH yet. Install Codex CLI, sign in by hand, and run once by hand: codex mcp login t3"
  fi
elif [ "$AGENT" = "antigravity" ]; then
  if command -v agy >/dev/null 2>&1; then
    say "  OK: agy CLI found at $(command -v agy). Sign in to your Google account in agy by hand."
  else
    say "  Note: agy CLI is not on PATH yet. Install Antigravity CLI and sign in to your Google account."
  fi
elif [ "$AGENT" = "pi" ]; then
  if command -v pi >/dev/null 2>&1; then
    say "  OK: pi CLI found at $(command -v pi). Set up a model in Pi by hand. For T3, see INSTALL.md step 1."
  else
    say "  Note: pi CLI is not on PATH yet. Install Pi and set up a model in it by hand."
  fi
fi

# ---------------------------------------------------------------------------
# Step 7: Systemd user service units (ask first, never overwrite foreign units, systemd quoting)
# ---------------------------------------------------------------------------
if [ "$IS_MAC" -eq 1 ]; then
  step "[7/7] Installing Rook.app and its launchd agent"
else
  step "[7/7] Installing systemd user service units"
fi

systemd_quote_arg() {
  python3 -c 'import sys; s = sys.argv[1].replace("\\", "\\\\").replace("\"", "\\\"").replace("%", "%%").replace("$", "$$"); print("\"" + s + "\"")' "$1"
}

systemd_escape_wd() {
  python3 -c 'import sys; print(sys.argv[1].replace("%", "%%"))' "$1"
}

write_unit_atomic() {
  local target="$1"
  python3 -c '
import os, sys, tempfile
from pathlib import Path
target = Path(sys.argv[1])
content = sys.stdin.read()
fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "w") as out:
        os.fchmod(out.fileno(), 0o644)
        out.write(content)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, target)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
' "$target"
}

copy_file_atomic() {
  local src="$1"
  local dst="$2"
  python3 -c '
import os, stat, sys, tempfile
from pathlib import Path
src = Path(sys.argv[1])
dst = Path(sys.argv[2])
st = os.lstat(src)
if not stat.S_ISREG(st.st_mode):
    sys.exit(1)
data = src.read_bytes()
mode = stat.S_IMODE(st.st_mode)
fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=dst.parent)
tmp = Path(tmp_name)
try:
    with os.fdopen(fd, "wb") as out:
        os.fchmod(out.fileno(), mode)
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, dst)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
' "$src" "$dst"
}

unit_is_owned() {
  local target="$1"
  local tmp_old="$DL_TMP/unit-check-old.json"
  [ ! -L "$target" ] && [ -f "$target" ] || return 1
  manifest_get_entry_to_file "$target" "$tmp_old" || return 1
  python3 - "$target" "$tmp_old" <<'PY' >/dev/null 2>&1
import hashlib, json, sys
from pathlib import Path
target, old_path = Path(sys.argv[1]), Path(sys.argv[2])
entry = json.loads(old_path.read_text())
rec_sha = entry.get("sha256")
if not isinstance(rec_sha, str) or len(rec_sha) != 64:
    sys.exit(1)
actual_sha = hashlib.sha256(target.read_bytes()).hexdigest()
sys.exit(0 if actual_sha == rec_sha else 1)
PY
}

unit_can_install() {
  local target="$1"
  if [ -L "$target" ]; then
    return 1
  fi
  if [ ! -e "$target" ]; then
    return 0
  fi
  if unit_is_owned "$target"; then
    return 0
  fi
  if [ "$REPLACE_UNITS" -eq 1 ] && [ -f "$target" ]; then
    return 0
  fi
  return 1
}

install_unit_file() {
  local target="$1"
  local base="$2"
  local role="${3:-systemd_unit}"  # launchd_plist on a Mac.
  local tmp_new="$DL_TMP/unit-${base}.new"
  local meta_file="$DL_TMP/unit-${base}.meta.json"
  local old_file="$DL_TMP/unit-${base}.old.json"
  UNIT_WRITTEN=0
  cat >"$tmp_new"
  local new_sha
  new_sha="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$tmp_new")"
  python3 - "$meta_file" "$new_sha" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"sha256": sys.argv[2]}))
PY
  if [ -L "$target" ]; then
    manifest_record_kept "$target" "$role" "pre-existing unit symlink kept untouched"
    say "  Left symlink $target untouched (not created by this installer). Remove it first to install Rook's unit."
    return 1
  fi
  if [ -e "$target" ]; then
    local is_owned=0
    local actual_sha=""
    if [ -f "$target" ] && manifest_get_entry_to_file "$target" "$old_file"; then
      actual_sha="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$target")"
      local rec_sha=""
      rec_sha="$(python3 -c 'import json,sys; d=json.loads(open(sys.argv[1]).read()); s=d.get("sha256"); print(s if isinstance(s,str) and len(s)==64 else "")' "$old_file")"
      if [ -n "$rec_sha" ] && [ "$actual_sha" = "$rec_sha" ]; then
        is_owned=1
      fi
    fi
    if [ "$is_owned" -eq 1 ]; then
      if [ "$actual_sha" = "$new_sha" ]; then
        return 0
      fi
      manifest_record_entry "$target" "unit" "$role" "$meta_file"
      write_unit_atomic "$target" <"$tmp_new"
      UNITS_CHANGED=1
      UNIT_WRITTEN=1
      return 0
    fi
    if [ "$REPLACE_UNITS" -eq 1 ]; then
      if [ ! -f "$target" ]; then
        die "$target exists and is not a regular file. Refusing to replace it." \
            "Move $target aside before running install/install.sh."
      fi
      local backup_unit
      backup_unit="$(dated_replaced_unit_path "$target")"
      copy_file_atomic "$target" "$backup_unit" \
        || die "Could not back up $target to $backup_unit before replacing." "Check permissions on $SYSTEMD_USER_DIR."
      manifest_record_kept "$backup_unit" "replaced_unit_backup" "original $base saved before --replace-units (never deleted; move back by hand to restore)"
      manifest_record_entry "$target" "unit" "$role" "$meta_file"
      write_unit_atomic "$target" <"$tmp_new"
      UNITS_CHANGED=1
      UNIT_WRITTEN=1
      say "  Replaced $target (--replace-units); original copy saved at $backup_unit."
      return 0
    fi
    if ! prior_manifest_created "$target"; then
      manifest_record_kept "$target" "$role" "pre-existing unit file kept untouched"
    fi
    say "  Left $target untouched (not recorded by this installer or modified since install). Re-run with --replace-units to replace it."
    return 1
  fi
  # Fresh creation: record ownership + content hash BEFORE writing the unit file.
  manifest_record_entry "$target" "unit" "$role" "$meta_file"
  write_unit_atomic "$target" <"$tmp_new"
  UNITS_CHANGED=1
  UNIT_WRITTEN=1
  return 0
}

# Reconcile installer-owned daily timer/service when the three-unit ownership rule does not hold.
# Rule: remove installer-owned rook-daily.service ONLY when no timer that starts it remains enabled
# (i.e. only together with our own timer, or when no timer file exists). If rook-daily.timer is
# now the person's (edited, unrecorded, symlink, or manifest hash mismatch), leave rook-daily.service
# in place so their timer keeps working, and report what is true.
reconcile_unowned_daily_units() {
  local timer_is_users=0
  local kept_daily_for_user_timer=0
  if [ -e "$UNIT_TIMER" ] || [ -L "$UNIT_TIMER" ]; then
    if unit_is_owned "$UNIT_TIMER"; then
      run_cmd "$SYSTEMCTL_BIN" --user disable --now rook-daily.timer || true
      rm -f -- "$UNIT_TIMER"
      manifest_remove_entry "$UNIT_TIMER"
      DISABLED_OWNED_UNITS+=("rook-daily.timer")
      UNITS_CHANGED=1
    else
      timer_is_users=1
      if [ -L "$UNIT_TIMER" ]; then
        manifest_record_kept "$UNIT_TIMER" "systemd_unit" "pre-existing unit symlink kept untouched"
      elif ! prior_manifest_created "$UNIT_TIMER"; then
        manifest_record_kept "$UNIT_TIMER" "systemd_unit" "pre-existing unit file kept untouched"
      fi
      LEFT_USER_UNITS+=("rook-daily.timer")
    fi
  fi

  if [ -e "$UNIT_DAILY" ] || [ -L "$UNIT_DAILY" ]; then
    if unit_is_owned "$UNIT_DAILY"; then
      if [ "$timer_is_users" -eq 1 ]; then
        kept_daily_for_user_timer=1
      else
        rm -f -- "$UNIT_DAILY"
        manifest_remove_entry "$UNIT_DAILY"
        DISABLED_OWNED_UNITS+=("rook-daily.service")
        UNITS_CHANGED=1
      fi
    else
      if [ -L "$UNIT_DAILY" ]; then
        manifest_record_kept "$UNIT_DAILY" "systemd_unit" "pre-existing unit symlink kept untouched"
      elif ! prior_manifest_created "$UNIT_DAILY"; then
        manifest_record_kept "$UNIT_DAILY" "systemd_unit" "pre-existing unit file kept untouched"
      fi
      LEFT_USER_UNITS+=("rook-daily.service")
    fi
  fi

  TIMER_IS_USERS="$timer_is_users"
  KEPT_DAILY_FOR_USER_TIMER="$kept_daily_for_user_timer"
}

UNIT_ROOK="$SYSTEMD_USER_DIR/rook.service"
UNIT_FAILED="$SYSTEMD_USER_DIR/rook-failed.service"
UNIT_DAILY="$SYSTEMD_USER_DIR/rook-daily.service"
UNIT_TIMER="$SYSTEMD_USER_DIR/rook-daily.timer"
UNIT_MEDIUM="$SYSTEMD_USER_DIR/rook-medium-voice.service"
MEDIUM_BY_HAND="$(printf '%q' "$MEDIUM_DIR/venv/bin/python") $(printf '%q' "$PREFIX/desktop/medium_voice.py")"

INSTALL_SERVICE=0
UNITS_CHANGED=0
OWNED_UNITS=()
LEFT_USER_UNITS=()
DISABLED_OWNED_UNITS=()
TIMER_IS_USERS=0
KEPT_DAILY_FOR_USER_TIMER=0

# On a Mac, launchd runs the signed Rook.app, which runs Rook's Python, so every macOS permission belongs to the app.
MAC_APP="${ROOK_APP:-$HOME/Applications/Rook.app}"
LAUNCHD_LABEL="${ROOK_LAUNCHD_LABEL:-com.rook.companion}"
MAC_PLIST="$HOME/Library/LaunchAgents/$LAUNCHD_LABEL.plist"
MAC_DAILY_PLIST="$HOME/Library/LaunchAgents/$LAUNCHD_LABEL.daily.plist"

if [ "$IS_MAC" -eq 1 ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    say "  Would check --service (${SERVICE_CHOICE:-ask}), build and sign $MAC_APP, and write $MAC_PLIST."
  elif decide_yes_no "--service" "$SERVICE_CHOICE" "  Install Rook.app and its launchd agent, so Rook starts at login?"; then
    require_abs_path "ROOK_APP" "$MAC_APP"
    if [ -L "$MAC_APP" ] || { [ -e "$MAC_APP" ] && ! prior_manifest_created "$MAC_APP"; }; then
      manifest_record_kept "$MAC_APP" "mac_app" "pre-existing Rook.app kept untouched"
      say "  Kept $MAC_APP as it is (not created by this installer). The launchd agent runs it."
    else
      # Rebuilt on every run from the installed checkout. The signing certificate stays the same, so grants survive.
      mkdir -p "$(dirname "$MAC_APP")"
      STAGE_TMP="$(make_stage_dir "$(dirname "$MAC_APP")" ".rook-stage-app")"
      sh "$PREFIX/macos/RookHelper/build.sh" "$STAGE_TMP/Rook.app" \
        || die "Could not build and sign Rook.app." "Check the clang and codesign output above."
      printf '{}\n' >"$STAGE_TMP/meta.json"
      manifest_record_entry "$MAC_APP" "dir" "mac_app" "$STAGE_TMP/meta.json"
      if [ -e "$MAC_APP" ]; then
        rm -rf -- "$MAC_APP"
      fi
      mv "$STAGE_TMP/Rook.app" "$MAC_APP"
      rm -rf -- "$STAGE_TMP"
      STAGE_TMP=""
      say "  OK: Built and signed $MAC_APP."
    fi
    mkdir -p "$(dirname "$MAC_PLIST")" "$HOME/Library/Logs"
    ROOK_LAUNCHD_LABEL="$LAUNCHD_LABEL" sh "$PREFIX/launchd/install.sh" --print --app "$MAC_APP" \
      --python "$ROOK_VENV/bin/python" --workspace "$HOME" >"$DL_TMP/launchd.plist"
    if install_unit_file "$MAC_PLIST" "$LAUNCHD_LABEL.plist" "launchd_plist" <"$DL_TMP/launchd.plist"; then
      INSTALL_SERVICE=1
      say "  OK: launchd agent ready at $MAC_PLIST. It starts Rook at each login."
      # The daily restart, as rook-daily.timer on Linux, only while this installer owns Rook's own agent.
      ROOK_LAUNCHD_LABEL="$LAUNCHD_LABEL" sh "$PREFIX/launchd/install.sh" --print --daily \
        --python "$ROOK_VENV/bin/python" >"$DL_TMP/launchd-daily.plist"
      if install_unit_file "$MAC_DAILY_PLIST" "$LAUNCHD_LABEL.daily.plist" "launchd_plist" <"$DL_TMP/launchd-daily.plist"; then
        if [ "$UNIT_WRITTEN" -eq 1 ]; then
          launchctl bootout "gui/$(id -u)/$LAUNCHD_LABEL.daily" >/dev/null 2>&1 || true
          run_cmd launchctl bootstrap "gui/$(id -u)" "$MAC_DAILY_PLIST" \
            || say "  Note: launchd could not load the daily restart now. It loads at your next login."
        fi
        say "  OK: Daily restart at 04:30 ready at $MAC_DAILY_PLIST."
      fi
    else
      LEFT_USER_UNITS+=("$LAUNCHD_LABEL.plist")
    fi
  else
    say "  Skipped Rook.app and the launchd agent."
  fi
elif [ "$DRY_RUN" -eq 1 ]; then
  if [ "$SERVICE_CHOICE" = "no" ]; then
    say "  Would skip systemd user units (--service no)."
    if [ "$VOICE" = "medium" ]; then
      say "  Would print the command that starts the medium voice by hand."
    fi
  else
    say "  Would check --service (${SERVICE_CHOICE:-ask}) and write Rook user units into $SYSTEMD_USER_DIR."
    if [ "$VOICE" = "medium" ]; then
      say "  Would also write and enable rook-medium-voice.service."
    fi
  fi
elif decide_yes_no "--service" "$SERVICE_CHOICE" "  Install and enable Rook's systemd user service and daily restart timer?"; then
  if [ "$REPLACE_UNITS" -eq 1 ] && [ -L "$SYSTEMD_USER_DIR" ]; then
    die "Refusing --replace-units because $SYSTEMD_USER_DIR is a symlink." \
        "Manage units inside the linked folder by hand, or replace the symlink with a real directory first."
  fi

  mkdir -p "$SYSTEMD_USER_DIR"

  WD_PREFIX="$(systemd_escape_wd "$PREFIX")"
  Q_ROOK_PY_BIN="$(systemd_quote_arg "$ROOK_VENV/bin/python")"
  Q_ROOK_SCRIPT="$(systemd_quote_arg "$PREFIX/desktop/rook.py")"
  Q_RELAY_SCRIPT="$(systemd_quote_arg "$PREFIX/desktop/relay.py")"

  ROOK_OWNED=0
  ROOK_WRITTEN=0
  TIMER_WRITTEN=0

  if install_unit_file "$UNIT_ROOK" "rook.service" <<EOF
$UNIT_MARKER
[Unit]
Description=Rook desktop voice assistant
PartOf=graphical-session.target
After=graphical-session.target
StartLimitIntervalSec=300
StartLimitBurst=5
OnFailure=rook-failed.service

[Service]
Type=simple
WorkingDirectory=$WD_PREFIX
ExecStart=$Q_ROOK_PY_BIN $Q_ROOK_SCRIPT --workspace %h
Restart=on-failure
RestartSec=5
RestartMode=direct
TimeoutStopSec=20
Environment=XDG_RUNTIME_DIR=%t
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
EOF
  then
    ROOK_OWNED=1
    ROOK_WRITTEN="$UNIT_WRITTEN"
    INSTALL_SERVICE=1
    OWNED_UNITS+=("rook.service")

    if install_unit_file "$UNIT_FAILED" "rook-failed.service" <<EOF
$UNIT_MARKER
[Unit]
Description=Notify the user when Rook stops after repeated failures

[Service]
Type=oneshot
ExecStart=/usr/bin/notify-send --urgency=critical --app-name=Rook "Rook stopped" "Rook kept failing, so systemd stopped restarting it. Check logs with: journalctl --user -u rook.service"
EOF
    then
      OWNED_UNITS+=("rook-failed.service")
    else
      LEFT_USER_UNITS+=("rook-failed.service")
    fi
  else
    LEFT_USER_UNITS+=("rook.service")
  fi

  # Standing rule: the installer's daily timer may be enabled ONLY while the installer owns
  # all three of rook.service, rook-daily.service, and rook-daily.timer (checked on every run).
  if [ "$ROOK_OWNED" -eq 1 ] && unit_can_install "$UNIT_DAILY" && unit_can_install "$UNIT_TIMER"; then
    if install_unit_file "$UNIT_DAILY" "rook-daily.service" <<EOF
$UNIT_MARKER
[Unit]
Description=Restart Rook once a day when idle

[Service]
Type=oneshot
ExecStart=/usr/bin/python $Q_RELAY_SCRIPT daily-restart
TimeoutStartSec=130min
Environment=XDG_RUNTIME_DIR=%t
EOF
    then
      OWNED_UNITS+=("rook-daily.service")
    else
      LEFT_USER_UNITS+=("rook-daily.service")
    fi

    if install_unit_file "$UNIT_TIMER" "rook-daily.timer" <<EOF
$UNIT_MARKER
[Unit]
Description=Restart Rook once a day at 04:30

[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=false

[Install]
WantedBy=timers.target
EOF
    then
      TIMER_WRITTEN="$UNIT_WRITTEN"
      OWNED_UNITS+=("rook-daily.timer")
    else
      LEFT_USER_UNITS+=("rook-daily.timer")
    fi
  else
    reconcile_unowned_daily_units
  fi

  # The medium voice server: its own unit, owned and recorded like Rook's.
  MEDIUM_OWNED=0
  MEDIUM_WRITTEN=0
  if [ "$VOICE" = "medium" ]; then
    Q_MEDIUM_PY_BIN="$(systemd_quote_arg "$MEDIUM_DIR/venv/bin/python")"
    Q_MEDIUM_SCRIPT="$(systemd_quote_arg "$PREFIX/desktop/medium_voice.py")"
    if install_unit_file "$UNIT_MEDIUM" "rook-medium-voice.service" <<EOF
$UNIT_MARKER
[Unit]
Description=Rook's medium voice (Qwen3-TTS 0.6B). It holds no graphics memory until Rook loads it.

[Service]
Type=simple
ExecStart=$Q_MEDIUM_PY_BIN $Q_MEDIUM_SCRIPT
Restart=always
RestartSec=5
Environment=HF_HUB_OFFLINE=1
Environment=PYTHONUNBUFFERED=1
Environment="XDG_DATA_HOME=$(systemd_escape_wd "$XDG_DATA_HOME")"

[Install]
WantedBy=default.target
EOF
    then
      MEDIUM_OWNED=1
      MEDIUM_WRITTEN="$UNIT_WRITTEN"
      OWNED_UNITS+=("rook-medium-voice.service")
    else
      LEFT_USER_UNITS+=("rook-medium-voice.service")
    fi
  fi

  TIMER_RULE_HOLDS=0
  if unit_is_owned "$UNIT_ROOK" && unit_is_owned "$UNIT_DAILY" && unit_is_owned "$UNIT_TIMER"; then
    TIMER_RULE_HOLDS=1
  fi

  if [ "$UNITS_CHANGED" -eq 1 ]; then
    run_cmd "$SYSTEMCTL_BIN" --user daemon-reload
  fi

  if [ "$MEDIUM_WRITTEN" -eq 1 ]; then
    run_cmd "$SYSTEMCTL_BIN" --user enable --now rook-medium-voice.service
  elif [ "$MEDIUM_OWNED" -eq 1 ] && ! "$SYSTEMCTL_BIN" --user is-enabled rook-medium-voice.service >/dev/null 2>&1; then
    say "  Note: rook-medium-voice.service is installed but switched off (left disabled). To turn it on, run: systemctl --user enable --now rook-medium-voice.service"
  fi

  if [ "$ROOK_OWNED" -eq 1 ]; then
    if [ "$ROOK_WRITTEN" -eq 1 ]; then
      run_cmd "$SYSTEMCTL_BIN" --user enable rook.service
      "$SYSTEMCTL_BIN" --user is-enabled rook.service >/dev/null 2>&1 \
        || die "rook.service failed to enable in systemd." "Check systemctl --user status rook.service."
    elif ! "$SYSTEMCTL_BIN" --user is-enabled rook.service >/dev/null 2>&1; then
      say "  Note: rook.service is installed but switched off (left disabled). To turn it on, run: systemctl --user enable --now rook.service"
    fi
    if [ "$TIMER_RULE_HOLDS" -eq 1 ]; then
      if [ "$TIMER_WRITTEN" -eq 1 ]; then
        run_cmd "$SYSTEMCTL_BIN" --user enable --now rook-daily.timer
      elif ! "$SYSTEMCTL_BIN" --user is-enabled rook-daily.timer >/dev/null 2>&1; then
        say "  Note: rook-daily.timer is installed but switched off (left disabled). To turn it on, run: systemctl --user enable --now rook-daily.timer"
      fi
      say "  OK: Installer-owned user units ready in $SYSTEMD_USER_DIR (${OWNED_UNITS[*]})."
    fi
  fi

  if [ "$TIMER_RULE_HOLDS" -eq 0 ]; then
    if [ "${#LEFT_USER_UNITS[@]}" -gt 0 ]; then
      say "  Left your systemd unit(s) untouched: ${LEFT_USER_UNITS[*]}."
    fi
    if [ "$TIMER_IS_USERS" -eq 1 ]; then
      if [ "$KEPT_DAILY_FOR_USER_TIMER" -eq 1 ]; then
        say "  Left installer-owned rook-daily.service in place so your timer keeps working."
      fi
      say "  rook-daily.timer is yours and was left as it is. If it is enabled, switch it off with: systemctl --user disable --now rook-daily.timer"
    elif [ "${#DISABLED_OWNED_UNITS[@]}" -gt 0 ]; then
      say "  Switched off and removed installer-owned ${DISABLED_OWNED_UNITS[*]} because the daily timer only runs while this installer owns all three of rook.service, rook-daily.service, and rook-daily.timer."
    else
      say "  Did not install or enable rook-daily.timer because this installer does not own all three of rook.service, rook-daily.service, and rook-daily.timer."
    fi
    say "  Re-run with --replace-units to back up and replace unowned or edited regular unit files."
  fi
else
  if manifest_has_units; then
    # Check the standing timer rule on --service no reruns too (safe direction: only ever switches
    # the installer's own timer off if the person took over rook.service or rook-daily.service).
    if { [ -e "$UNIT_TIMER" ] || [ -L "$UNIT_TIMER" ]; } && ! { unit_is_owned "$UNIT_ROOK" && unit_is_owned "$UNIT_DAILY" && unit_is_owned "$UNIT_TIMER"; }; then
      if { [ -e "$UNIT_ROOK" ] || [ -L "$UNIT_ROOK" ]; } && ! unit_is_owned "$UNIT_ROOK"; then
        LEFT_USER_UNITS+=("rook.service")
      fi
      reconcile_unowned_daily_units
      if [ "$UNITS_CHANGED" -eq 1 ]; then
        run_cmd "$SYSTEMCTL_BIN" --user daemon-reload
      fi
      if [ "${#LEFT_USER_UNITS[@]}" -gt 0 ]; then
        say "  Left your systemd unit(s) untouched: ${LEFT_USER_UNITS[*]}."
      fi
      if [ "$TIMER_IS_USERS" -eq 1 ]; then
        if [ "$KEPT_DAILY_FOR_USER_TIMER" -eq 1 ]; then
          say "  Left installer-owned rook-daily.service in place so your timer keeps working."
        fi
        say "  rook-daily.timer is yours and was left as it is. If it is enabled, switch it off with: systemctl --user disable --now rook-daily.timer"
      elif [ "${#DISABLED_OWNED_UNITS[@]}" -gt 0 ]; then
        say "  Switched off and removed installer-owned ${DISABLED_OWNED_UNITS[*]} because the daily timer only runs while this installer owns all three of rook.service, rook-daily.service, and rook-daily.timer."
      fi
    fi
    say "  Skipped systemd unit updates (--service no). Previously installed Rook units remain tracked in $MANIFEST_PATH."
  else
    say "  Skipped systemd user units."
  fi
  if [ "$VOICE" = "medium" ]; then
    say "  The medium voice has no login service (--service no). Start it by hand with: $MEDIUM_BY_HAND"
  fi
fi

say ""
if [ "$DRY_RUN" -eq 1 ]; then
  say "Dry run finished. Nothing was changed."
  exit 0
fi

if [ "${#INCOMPLETE_REASONS[@]}" -gt 0 ]; then
  FINISHED_INCOMPLETE=1
  say "Rook install is incomplete. Missing: ${INCOMPLETE_REASONS[*]}."
  say "Re-run install/install.sh with the needed flags to finish setup."
  exit 2
fi

say "Rook install complete."
if [ "$INSTALL_SERVICE" -eq 1 ] && [ "$IS_MAC" -eq 1 ]; then
  say "Start Rook with: launchctl bootstrap gui/$(id -u) $(printf '%q' "$MAC_PLIST")"
  say "Watch logs with: tail -f ~/Library/Logs/rook.err.log"
elif [ "$INSTALL_SERVICE" -eq 1 ]; then
  say "Start Rook with: systemctl --user start rook.service"
  say "Watch logs with: journalctl --user -u rook.service -o cat --since -60s"
else
  say "Start Rook manually with: $(printf '%q' "$ROOK_VENV/bin/python") $(printf '%q' "$PREFIX/desktop/rook.py") --workspace \"$HOME\""
fi
