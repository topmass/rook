#!/usr/bin/env bash
# Failure, rerun-ownership, large-venv, symlink, space-prefix, stale-stage, and real SIGTERM/SIGKILL tests.
# Runs strictly inside a fresh mktemp -d root with fake systemctl, uv, pacman, curl, sudo, loginctl on PATH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_SH="$SCRIPT_DIR/install.sh"
UNINSTALL_SH="$SCRIPT_DIR/uninstall.sh"
REAL_GIT="$(command -v git)"
REAL_MV="$(command -v mv)"
REAL_PY3="$(command -v python3)"

# Always create and own our own fresh mktemp -d directory; never rm -rf a caller-supplied path.
if [ -n "${ROOK_INSTALL_TEST_ROOT:-}" ]; then
  case "$ROOK_INSTALL_TEST_ROOT" in
    /*) ;;
    *) printf 'Error: ROOK_INSTALL_TEST_ROOT must be an absolute path.\n' >&2; exit 1 ;;
  esac
  case "/$ROOK_INSTALL_TEST_ROOT/" in
    */../*) printf 'Error: ROOK_INSTALL_TEST_ROOT must not contain "..".\n' >&2; exit 1 ;;
  esac
  if [ "$ROOK_INSTALL_TEST_ROOT" = "/" ] || [ "$ROOK_INSTALL_TEST_ROOT" = "${HOME:-}" ] || [ ! -d "$ROOK_INSTALL_TEST_ROOT" ]; then
    printf 'Error: ROOK_INSTALL_TEST_ROOT must be an existing temp directory (not / or HOME).\n' >&2
    exit 1
  fi
  TEST_ROOT="$(mktemp -d "$ROOK_INSTALL_TEST_ROOT/rook-fail-test-XXXXXX")"
else
  TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/rook-fail-test-XXXXXX")"
fi
trap 'rm -rf -- "$TEST_ROOT"' EXIT

FAKE_BIN="$TEST_ROOT/fake-bin"
mkdir -p "$FAKE_BIN"

cat >"$FAKE_BIN/systemctl" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "${FAKE_SYSTEMCTL_LOG:-/dev/null}"
if [ "${KILL_SYNC_STEP:-}" = "systemctl" ] && [ "${2:-}" = "daemon-reload" ] && [ -n "${KILL_SYNC_FILE:-}" ]; then
  echo "$$" > "$KILL_SYNC_FILE"
  sleep 10
fi
if [ "${2:-}" = "is-enabled" ] && [[ " ${FAKE_SYSTEMCTL_DISABLED:-} " == *" ${3:-} "* ]]; then
  exit 1
fi
if [ "${2:-}" = "is-active" ] && [ -n "${FAKE_SYSTEMCTL_INACTIVE:-}" ]; then
  exit 3
fi
if [ "${2:-}" = "show-environment" ]; then
  [ -z "${FAKE_SYSTEMCTL_PATH:-}" ] || echo "PATH=$FAKE_SYSTEMCTL_PATH"
fi
exit 0
SH
chmod +x "$FAKE_BIN/systemctl"

# Never the real launchctl, even when this suite runs on a Mac: every case's launchd calls are logged only.
cat >"$FAKE_BIN/launchctl" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "${FAKE_LAUNCHCTL_LOG:-/dev/null}"
exit 0
SH
chmod +x "$FAKE_BIN/launchctl"

# Without FAKE_GPU it fails like a computer with no NVIDIA driver.
cat >"$FAKE_BIN/nvidia-smi" <<'SH'
#!/usr/bin/env bash
[ -n "${FAKE_GPU:-}" ] || { echo "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver."; exit 9; }
echo "$FAKE_GPU"
SH
chmod +x "$FAKE_BIN/nvidia-smi"

cat >"$FAKE_BIN/pacman" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "-Q" ]; then
  exit 0
fi
echo "ERROR: unexpected pacman invocation: $*" >&2
exit 99
SH
chmod +x "$FAKE_BIN/pacman"

for forbidden in curl sudo loginctl; do
  cat >"$FAKE_BIN/$forbidden" <<SH
#!/usr/bin/env bash
echo "ERROR: $forbidden must never be called (\$*)" >&2
exit 99
SH
  chmod +x "$FAKE_BIN/$forbidden"
done

cat >"$FAKE_BIN/git" <<SH
#!/usr/bin/env bash
if [ "\${KILL_SYNC_STEP:-}" = "git-clone" ] && [ "\${1:-}" = "clone" ] && [ -n "\${KILL_SYNC_FILE:-}" ]; then
  echo "\$\$" > "\$KILL_SYNC_FILE"
  sleep 10
fi
exec "$REAL_GIT" "\$@"
SH
chmod +x "$FAKE_BIN/git"

cat >"$FAKE_BIN/mv" <<SH
#!/usr/bin/env bash
if [ -n "\${KILL_SYNC_STEP:-}" ] && [ -n "\${KILL_SYNC_FILE:-}" ]; then
  if [ "\$KILL_SYNC_STEP" = "prefix-before-rename" ] && [[ "\${1:-}" == *".rook-stage-prefix-"*"/checkout" ]]; then
    echo "\$\$" > "\$KILL_SYNC_FILE"
    sleep 10
  elif [ "\$KILL_SYNC_STEP" = "venv-before-rename" ] && [[ "\${1:-}" == *".rook-stage-venv-"*"/venv" ]]; then
    echo "\$\$" > "\$KILL_SYNC_FILE"
    sleep 10
  elif [ "\$KILL_SYNC_STEP" = "venv-swap-after-move-old" ] && [[ "\${1:-}" == *".rook-stage-venv-"*"/venv" ]]; then
    echo "\$\$" > "\$KILL_SYNC_FILE"
    sleep 10
  fi
fi
exec "$REAL_MV" "\$@"
SH
chmod +x "$FAKE_BIN/mv"

cat >"$FAKE_BIN/python3" <<SH
#!/usr/bin/env bash
if [ "\${KILL_SYNC_STEP:-}" = "unit-before-write" ] && [ -n "\${KILL_SYNC_FILE:-}" ]; then
  last="\${!#}"
  if [[ "\$last" == *"/rook.service" ]] && [[ "\$*" == *"os.replace(tmp, target)"* ]]; then
    echo "\$\$" > "\$KILL_SYNC_FILE"
    sleep 10
  fi
fi
exec "$REAL_PY3" "\$@"
SH
chmod +x "$FAKE_BIN/python3"

# Lightweight uv stub with fault injection, large-file generation, and real-signal sync hooks.
cat >"$FAKE_BIN/uv" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
shift || true

if [ "$cmd" = "venv" ]; then
  target="${!#}"
  if [ "${KILL_SYNC_STEP:-}" = "uv-venv" ] && [[ "$target" == *"rook-stage-venv"* ]] && [ -n "${KILL_SYNC_FILE:-}" ]; then
    mkdir -p "$target"
    echo "partial-junk" >"$target/partial.tmp"
    echo "$$" > "$KILL_SYNC_FILE"
    sleep 10
  fi
  if [ "${KILL_SYNC_STEP:-}" = "uv-voice" ] && [[ "$target" == *"rook-stage-voice"* ]] && [ -n "${KILL_SYNC_FILE:-}" ]; then
    mkdir -p "$target"
    echo "partial-junk" >"$target/partial.tmp"
    echo "$$" > "$KILL_SYNC_FILE"
    sleep 10
  fi
  if [ "${FAIL_UV_VENV_ON:-}" != "" ] && [[ "$target" == *"$FAIL_UV_VENV_ON"* ]]; then
    mkdir -p "$target"
    echo "partial-junk" >"$target/partial.tmp"
    echo "Simulated uv venv failure on $target" >&2
    exit 1
  fi
  mkdir -p "$target/bin" "$target/lib/stub"
  cat >"$target/bin/python" <<'PY'
#!/usr/bin/env bash
VENV_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$VENV_DIR/lib/stub${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 "$@"
PY
  chmod +x "$target/bin/python"
  echo "home = /usr/bin" >"$target/pyvenv.cfg"
  exit 0
fi

if [ "$cmd" = "pip" ]; then
  echo "pip $*" >> "${FAKE_UV_LOG:-/dev/null}"
  sub="${1:-}"; shift || true
  py_bin=""
  req_file=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --python) py_bin="$2"; shift 2 ;;
      -r) req_file="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  venv_dir="$(dirname "$(dirname "$py_bin")")"
  if [ "${FAIL_UV_PIP_ON:-}" != "" ] && [[ "$venv_dir" == *"$FAIL_UV_PIP_ON"* ]]; then
    echo "Simulated uv pip install failure on $venv_dir" >&2
    exit 1
  fi
  if [ "${FAIL_UV_PIP_SILENT_ON:-}" != "" ] && [[ "$venv_dir" == *"$FAIL_UV_PIP_SILENT_ON"* ]]; then
    exit 1  # Killed or out of memory: nothing on stderr.
  fi
  stub_dir="$venv_dir/lib/stub"
  mkdir -p "$stub_dir/airtype"
  cat >"$stub_dir/airtype/__init__.py" <<'PY'
__version__ = "2.1.2-stub"
PY
  cat >"$stub_dir/airtype/pipeline.py" <<'PY'
class AirtypePipeline: pass
PY
  cat >"$stub_dir/airtype/config.py" <<'PY'
def default_config(): return {}
PY
  cat >"$stub_dir/airtype/asr.py" <<'PY'
from pathlib import Path
import os
class _Spec:
    name = "parakeet-unified-en-0.6b-int8"
    dir_name = "stub-asr"
    size_label = "480 MB"
    url = "https://example.invalid/asr"
    hf_repo = None
def active_model_spec(): return _Spec()
def default_model_dir(spec=None):
    return Path(os.environ.get("XDG_CACHE_HOME", "")) / "airtype/models/stub-asr"
def model_exists(spec=None):
    return (default_model_dir(spec) / "tokens.txt").is_file()
def ensure_model_download(spec=None, progress=False):
    raise RuntimeError("offline stub")
PY
  cat >"$stub_dir/airtype/registry.py" <<'PY'
from airtype.asr import _Spec
MODEL_REGISTRY = {"parakeet-unified-en-0.6b-int8": _Spec(), "parakeet-tdt-0.6b-v3-int8": _Spec()}
PY
  for mod in evdev sherpa_onnx sounddevice soundfile numpy ptts; do
    cat >"$stub_dir/${mod}.py" <<'PY'
__version__ = "0.7.1-stub"
def set_num_threads(n): pass
class TTS:
    def __init__(self, **kw): pass
    def synth(self, text, voice=None): return b""
PY
  done
  cat >"$stub_dir/huggingface_hub.py" <<'PY'
from pathlib import Path
def hf_hub_download(repo, name, revision=None, cache_dir=None, local_files_only=False):
    path = Path(cache_dir) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stub model")
    return str(path)
def snapshot_download(*args, **kwargs): raise RuntimeError("offline stub")
PY
  if [ -n "${FAKE_UV_BUILD_TAG:-}" ]; then
    printf '%s\n' "$FAKE_UV_BUILD_TAG" >"$stub_dir/build-tag.txt"
  fi
  if [ "${FAKE_UV_NEWLINE_FILE:-0}" -eq 1 ] && [[ "$venv_dir" == *"rook-stage-venv"* ]]; then
    python3 -c 'from pathlib import Path; import sys; (Path(sys.argv[1]) / "lib/stub/weird\nname.txt").write_text("ok\n")' "$venv_dir"
  fi
  if [ "${FAKE_UV_EXTRA_FILES:-0}" -gt 0 ] && [[ "$venv_dir" == *"rook-stage-venv"* || "$venv_dir" == */venv ]]; then
    python3 - "$venv_dir" "$FAKE_UV_EXTRA_FILES" <<'PY'
import sys
from pathlib import Path
base = Path(sys.argv[1]) / "lib/python3.12/site-packages/big_pkg_with_long_name"
base.mkdir(parents=True, exist_ok=True)
n = int(sys.argv[2])
for i in range(n):
    (base / f"module_entry_number_{i:05d}.py").write_text("")
PY
  fi
  exit 0
fi

if [ "$cmd" = "run" ]; then
  exit 0
fi
if [ "$cmd" = "python" ]; then  # python list PIN: an old uv (FAKE_UV_OLD=1) does not know the pinned Python.
  [ -n "${FAKE_UV_OLD:-}" ] || echo "cpython-${2:-3.12.14}-linux-x86_64-gnu    <download available>"
  exit 0
fi
if [ "$cmd" = "--version" ]; then
  [ -z "${FAKE_UV_VERSION_FAILS:-}" ] || exit 2
  [ -n "${FAKE_UV_OLD:-}" ] && echo "uv 0.5.8 (fake)" || echo "uv 0.13.10 (fake)"
  exit 0
fi
exit 0
SH
chmod +x "$FAKE_BIN/uv"

# Claude Code, signed out: the installer asks its status and must never reach the real one.
cat >"$FAKE_BIN/claude" <<'SH'
#!/usr/bin/env bash
case "$*" in
  "auth status")
    [ -z "${FAKE_CLAUDE_HANGS:-}" ] || exec sleep 60
    [ -n "${FAKE_CLAUDE_SIGNED_IN:-}" ] && echo '{"loggedIn": true}' || echo '{"loggedIn": false}' ;;
  *) echo "2.1.332 (fake Claude Code)" ;;
esac
SH
chmod +x "$FAKE_BIN/claude"

FAKE_WHEEL="$TEST_ROOT/airtype-2.1.2-py3-none-any.whl"
echo "stub-wheel-v1" >"$FAKE_WHEEL"

fail() {
  printf '  FAIL: %s\n' "$*" >&2
  exit 1
}

pass() {
  printf '  PASS: %s\n' "$*"
}

new_sandbox() {
  local name="$1"
  local sb="$TEST_ROOT/sb-$name/home"
  rm -rf -- "$TEST_ROOT/sb-$name"
  mkdir -p "$sb/.config" "$sb/.local/share" "$sb/.cache" "$sb/.local/state" "$sb/run"
  chmod 0700 "$sb/run"
  printf '%s\n' "$sb"
}

run_in_sb() {
  local sb="$1"; shift
  env \
    PATH="$FAKE_BIN:$PATH" \
    HOME="$sb" \
    XDG_CONFIG_HOME="$sb/.config" \
    XDG_DATA_HOME="$sb/.local/share" \
    XDG_CACHE_HOME="$sb/.cache" \
    XDG_STATE_HOME="$sb/.local/state" \
    XDG_RUNTIME_DIR="$sb/run" \
    FAKE_SYSTEMCTL_LOG="$TEST_ROOT/systemctl.log" \
    ROOK_SYSTEM_APPS="$sb/no-system-apps" \
    ROOK_SIGN_IDENTITY=- \
    "$@"
}
# On a real Mac the cases below run as a Mac: ROOK_SYSTEM_APPS keeps Rook.app out of the real /Applications,
# ROOK_SIGN_IDENTITY=- signs ad hoc instead of touching a keychain, and the fake launchctl loads no job.

echo "=== Case 1: Pre-existing folder with notes.txt at each target is never deleted ==="
for target in live venv voice-phonon; do
  SB1="$(new_sandbox "preexist-$target")"
  mkdir -p "$SB1/.local/share/rook/$target"
  echo "precious-user-notes" >"$SB1/.local/share/rook/$target/notes.txt"
  if run_in_sb "$SB1" bash "$INSTALL_SH" --agent claude --voice small --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1; then
    fail "Installer should have refused pre-existing non-Rook folder $target"
  fi
  [ -f "$SB1/.local/share/rook/$target/notes.txt" ] || fail "Pre-existing $target/notes.txt was DELETED!"
  [ -z "$(find "$SB1/.local/share/rook" -maxdepth 1 \( -name '.rook-stage-*' -o -name '.tmp-download-*' \))" ] || fail "Temp stage dir leaked after refusal on $target"
done
pass "Pre-existing folders with notes.txt at live, venv, and voice-phonon survived untouched"

echo "=== Case 2: Forced failures leave no stage folders and record completed items incrementally ==="
SB2A="$(new_sandbox fail-clone)"
if run_in_sb "$SB2A" bash "$INSTALL_SH" --source "$TEST_ROOT/no-such-repo" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1; then
  fail "Bad --source should fail"
fi
[ ! -e "$SB2A/.local/share/rook/live" ] || fail "Half-made live folder left after clone failure"
[ -z "$(find "$SB2A/.local/share/rook" -maxdepth 1 \( -name '.rook-stage-*' -o -name '.tmp-download-*' \))" ] || fail "Stage temp left after clone failure"

SB2B="$(new_sandbox fail-venv1)"
if run_in_sb "$SB2B" env FAIL_UV_VENV_ON="rook-stage-venv" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1; then
  fail "Forced rook_venv failure should fail"
fi
[ -d "$SB2B/.local/share/rook/live" ] || fail "Completed prefix should remain"
[ ! -e "$SB2B/.local/share/rook/venv" ] || fail "Failed rook_venv should not exist at final path"
[ -f "$SB2B/.local/share/rook/install-manifest.json" ] || fail "Manifest was not written before Step 4a failure!"
grep -q '/live"' "$SB2B/.local/share/rook/install-manifest.json" || fail "Manifest missing completed prefix after Step 4a failure"
[ -z "$(find "$SB2B/.local/share/rook" -maxdepth 1 \( -name '.rook-stage-*' -o -name '.tmp-download-*' \))" ] || fail "Stage temp left after Step 4a failure"

SB2C="$(new_sandbox fail-venv2)"
if run_in_sb "$SB2C" env FAIL_UV_PIP_ON="rook-stage-voice" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1; then
  fail "Forced voice_venv pip failure should fail"
fi
[ ! -e "$SB2C/.local/share/rook/voice-phonon" ] || fail "Failed voice_venv should not exist at final path"
grep -q '/live"' "$SB2C/.local/share/rook/install-manifest.json" || fail "Manifest missing prefix after Step 4b failure"
grep -q '/venv"' "$SB2C/.local/share/rook/install-manifest.json" || fail "Manifest missing rook_venv after Step 4b failure"
run_in_sb "$SB2C" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB2C/.local/share/rook/live" ] && [ ! -e "$SB2C/.local/share/rook/venv" ] && [ ! -e "$SB2C/.local/share/rook" ] || fail "Uninstall after failed install left files behind"
pass "Forced failures cleaned staging dirs, recorded completed items incrementally, and allowed clean uninstall"

echo "=== Case 3: Re-run after mid-install failure recognizes prior prefix as installer-managed ==="
SB3="$(new_sandbox rerun-after-fail)"
if run_in_sb "$SB3" env FAIL_UV_PIP_ON="rook-stage-voice" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1; then
  fail "First run should have failed in Step 4b"
fi
set +e
OUT3="$(run_in_sb "$SB3" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC3=$?
set -e
[ "$RC3" -eq 2 ] || fail "Re-run with --voice-model no should exit 2 (incomplete), got $RC3"
printf '%s\n' "$OUT3" | grep -q "Existing installer-managed Rook checkout found" || fail "Re-run failed to recognize prior prefix as installer-managed"
! printf '%s\n' "$OUT3" | grep -q "not created by this installer" || fail "Re-run wrongly called prior prefix foreign"
run_in_sb "$SB3" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB3/.local/share/rook/live" ] && [ ! -e "$SB3/.local/share/rook/venv" ] && [ ! -e "$SB3/.local/share/rook/voice-phonon" ] || fail "Uninstall after recovered re-run left items behind"
pass "Re-run after failure recognized prior prefix/venv as installer-managed and uninstalled cleanly"

echo "=== Case 4: Re-run with --service no keeps previously installed systemd units in cumulative manifest ==="
SB4="$(new_sandbox cumulative-service)"
set +e
run_in_sb "$SB4" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC4A=$?
OUT4B="$(run_in_sb "$SB4" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC4B=$?
set -e
[ "$RC4A" -eq 2 ] && [ "$RC4B" -eq 2 ] || fail "Expected exit 2 (skipped models) on both runs, got $RC4A/$RC4B"
[ -f "$SB4/.config/systemd/user/rook.service" ] || fail "rook.service missing after --service yes"
grep -q "rook.service" "$SB4/.local/share/rook/install-manifest.json" || fail "Manifest forgot rook.service after --service no re-run!"
printf '%s\n' "$OUT4B" | grep -q "Previously installed Rook units remain tracked" || fail "Re-run did not mention preserved units"
run_in_sb "$SB4" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB4/.config/systemd/user/rook.service" ] && [ ! -e "$SB4/.config/systemd/user/rook-daily.timer" ] || fail "Uninstall did not remove units after --service no re-run!"
pass "Cumulative manifest preserved systemd units across --service no re-run and removed them on uninstall"

echo "=== Case 5: Without --recogniser-source, AirType comes from its public repo at the pinned commit ==="
SB5="$(new_sandbox no-rec-src)"
OUT5="$(run_in_sb "$SB5" bash "$INSTALL_SH" --dry-run --voice-model no --recogniser no --service no 2>&1)"
printf '%s\n' "$OUT5" | grep -q "Recogniser: airtype @ git+https://github.com/topmass/airtype-for-omarchy@fe4815a480e40a68b220dadc8b23d61dbd4c3340" \
  || fail "Default AirType source is not the pinned public commit"
pass "Default AirType source is the public repo at the pinned commit"

echo "=== Case 6: Broken settings.json at Step 6 preserves file and keeps earlier steps uninstallable ==="
SB6="$(new_sandbox broken-step6)"
mkdir -p "$SB6/.config/rook"
printf '{broken\n' >"$SB6/.config/rook/settings.json"
chmod 0640 "$SB6/.config/rook/settings.json"
if run_in_sb "$SB6" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1; then
  fail "Broken settings.json should fail in Step 6"
fi
[ "$(cat "$SB6/.config/rook/settings.json")" = "{broken" ] || fail "Broken settings.json was overwritten"
[ "$(stat -c %a "$SB6/.config/rook/settings.json")" = "640" ] || fail "Broken settings.json mode changed"
run_in_sb "$SB6" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB6/.local/share/rook/live" ] && [ ! -e "$SB6/.local/share/rook/venv" ] && [ ! -e "$SB6/.local/share/rook/voice-phonon" ] || fail "Uninstall after Step 6 failure left items behind"
[ "$(cat "$SB6/.config/rook/settings.json")" = "{broken" ] || fail "Uninstall touched broken settings.json"
pass "Broken settings.json failed cleanly, preserved file/mode, and earlier steps uninstalled cleanly"

echo "=== Case 7 (Review 58 #1): Rerun never re-snapshots venv; user notes.txt survives rerun & swap ==="
# 7a. Unchanged rerun after user adds notes.txt to both venvs.
SB7A="$(new_sandbox rerun-no-resnapshot)"
set +e
run_in_sb "$SB7A" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC7A1=$?
set -e
[ "$RC7A1" -eq 2 ] || fail "Initial install failed with $RC7A1"
echo "my precious venv notes" >"$SB7A/.local/share/rook/venv/notes.txt"
echo "my precious voice notes" >"$SB7A/.local/share/rook/voice-phonon/notes.txt"
set +e
run_in_sb "$SB7A" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC7A2=$?
set -e
[ "$RC7A2" -eq 2 ] || fail "Rerun failed with $RC7A2"
run_in_sb "$SB7A" bash "$UNINSTALL_SH" --yes >/dev/null
[ -f "$SB7A/.local/share/rook/venv/notes.txt" ] || fail "venv/notes.txt was DELETED after rerun + uninstall!"
[ -f "$SB7A/.local/share/rook/voice-phonon/notes.txt" ] || fail "voice-phonon/notes.txt was DELETED after rerun + uninstall!"

# 7b. Rerun that MUST update venv (wheel changed) swaps in fresh stage and keeps dirty old venv under dated name.
SB7B="$(new_sandbox rerun-swap-dirty)"
WHEEL7B="$TEST_ROOT/airtype-swap-dirty.whl"
echo "wheel-v1" >"$WHEEL7B"
set +e
run_in_sb "$SB7B" env FAKE_UV_BUILD_TAG="v1" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$WHEEL7B" >/dev/null 2>&1
RC7B1=$?
set -e
[ "$RC7B1" -eq 2 ] || fail "7b initial install failed with $RC7B1"
echo "keep-me-across-swap" >"$SB7B/.local/share/rook/venv/notes.txt"
echo "wheel-v2" >"$WHEEL7B"
set +e
OUT7B="$(run_in_sb "$SB7B" env FAKE_UV_BUILD_TAG="v2" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$WHEEL7B" 2>&1)"
RC7B2=$?
set -e
[ "$RC7B2" -eq 2 ] || fail "7b update rerun failed with $RC7B2"
[ "$(cat "$SB7B/.local/share/rook/venv/lib/stub/build-tag.txt")" = "v2" ] || fail "New swapped venv was not installed"
[ ! -e "$SB7B/.local/share/rook/venv/notes.txt" ] || fail "New swapped venv should be fresh"
KEPT_DIR7B="$(find "$SB7B/.local/share/rook" -maxdepth 1 -type d -name 'venv.kept-*' | head -n 1)"
[ -n "$KEPT_DIR7B" ] && [ -f "$KEPT_DIR7B/notes.txt" ] || fail "Old venv with notes.txt was not kept under dated name!"
printf '%s\n' "$OUT7B" | grep -q "Kept previous environment at" || fail "Swap did not tell user where old venv was kept"
run_in_sb "$SB7B" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB7B/.local/share/rook/venv" ] || fail "Clean new venv should have been removed by uninstall"
[ -f "$KEPT_DIR7B/notes.txt" ] || fail "Dated old venv with notes.txt was deleted by uninstall!"

# 7c. Rerun that MUST update a CLEAN venv removes the old venv cleanly.
SB7C="$(new_sandbox rerun-swap-clean)"
WHEEL7C="$TEST_ROOT/airtype-swap-clean.whl"
echo "wheel-v1" >"$WHEEL7C"
set +e
run_in_sb "$SB7C" env FAKE_UV_BUILD_TAG="v1" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$WHEEL7C" >/dev/null 2>&1
RC7C1=$?
echo "wheel-v2" >"$WHEEL7C"
run_in_sb "$SB7C" env FAKE_UV_BUILD_TAG="v2" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$WHEEL7C" >/dev/null 2>&1
RC7C2=$?
set -e
[ "$RC7C1" -eq 2 ] && [ "$RC7C2" -eq 2 ] || fail "7c expected exit 2, got $RC7C1/$RC7C2"
[ -z "$(find "$SB7C/.local/share/rook" -maxdepth 1 -name 'venv.kept-*')" ] || fail "Clean old venv left a stale venv.kept-* behind"
run_in_sb "$SB7C" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB7C/.local/share/rook/venv" ] && [ ! -e "$SB7C/.local/share/rook" ] || fail "7c uninstall left files behind"
pass "Rerun never re-snapshots venv; user notes.txt survived both unchanged rerun and update swap"

echo "=== Case 8 (Review 58 #2): Large venv (>3,000 files, >180 KB JSON) never hits Argument list too long ==="
SB8="$(new_sandbox large-venv)"
set +e
OUT8="$(run_in_sb "$SB8" env FAKE_UV_EXTRA_FILES=3000 bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC8=$?
set -e
[ "$RC8" -eq 2 ] || fail "Large venv install failed (rc=$RC8): $OUT8"
python3 - "$SB8/.local/share/rook/install-manifest.json" <<'PY'
import json, sys
data = json.loads(open(sys.argv[1]).read())
venv_entries = [e for e in data["entries"] if e.get("role") == "rook_venv"]
assert len(venv_entries) == 1, f"missing rook_venv entry: {data['entries']}"
count = len(venv_entries[0]["installed_files"])
assert count >= 3000, f"expected >=3000 files recorded, got {count}"
PY
# Rerun must recognize venv as installer-managed (not foreign), and uninstall must remove it cleanly.
set +e
OUT8R="$(run_in_sb "$SB8" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC8R=$?
set -e
[ "$RC8R" -eq 2 ] || fail "Large venv rerun failed (rc=$RC8R)"
! printf '%s\n' "$OUT8R" | grep -q "not created by this installer" || fail "Large venv rerun wrongly called venv foreign"
run_in_sb "$SB8" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB8/.local/share/rook/venv" ] && [ ! -e "$SB8/.local/share/rook" ] || fail "Large venv was not cleanly uninstalled"
pass "Large venv (3,000+ files, >180 KB JSON) recorded via file, recognized on rerun, and uninstalled cleanly"

echo "=== Case 9 (Review 58 #5a): Symlinked settings.json is preserved (write-through + mode kept) ==="
SB9="$(new_sandbox symlink-settings)"
mkdir -p "$SB9/dotfiles" "$SB9/.config/rook"
printf '{"voice": "Miles", "custom_key": "keep"}\n' >"$SB9/dotfiles/settings.json"
chmod 0640 "$SB9/dotfiles/settings.json"
ln -s "$SB9/dotfiles/settings.json" "$SB9/.config/rook/settings.json"
set +e
run_in_sb "$SB9" bash "$INSTALL_SH" --agent antigravity --voice small --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC9=$?
set -e
[ "$RC9" -eq 2 ] || fail "Symlink settings install failed with $RC9"
[ -L "$SB9/.config/rook/settings.json" ] || fail "settings.json symlink was replaced with a regular file!"
[ "$(readlink "$SB9/.config/rook/settings.json")" = "$SB9/dotfiles/settings.json" ] || fail "settings.json symlink target changed!"
[ "$(stat -c %a "$SB9/dotfiles/settings.json")" = "640" ] || fail "settings.json target mode changed!"
python3 - "$SB9/dotfiles/settings.json" <<'PY'
import json, sys
d = json.loads(open(sys.argv[1]).read())
assert d["agent"] == "antigravity" and d["custom_key"] == "keep", f"unexpected settings: {d}"
PY
pass "Symlinked settings.json stayed a symlink, wrote through to target, and preserved mode 0640"

echo "=== Case 10 (Review 58 #5d): --prefix with a space writes valid systemd-quoted ExecStart ==="
SB10="$(new_sandbox space-prefix)"
SPACE_PREFIX="$SB10/.local/share/rook/my rook live"
set +e
OUT10="$(run_in_sb "$SB10" bash "$INSTALL_SH" --prefix "$SPACE_PREFIX" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC10=$?
set -e
[ "$RC10" -eq 2 ] || fail "Space-prefix install failed (rc=$RC10): $OUT10"
UNIT10="$SB10/.config/systemd/user/rook.service"
DAILY10="$SB10/.config/systemd/user/rook-daily.service"
grep -qF "WorkingDirectory=$SPACE_PREFIX" "$UNIT10" || fail "WorkingDirectory missing exact space prefix"
grep -qF "\"$SPACE_PREFIX/desktop/rook.py\"" "$UNIT10" || fail "ExecStart did not systemd-quote space prefix in rook.service"
grep -qF "\"$SPACE_PREFIX/desktop/relay.py\"" "$DAILY10" || fail "ExecStart did not systemd-quote space prefix in rook-daily.service"
run_in_sb "$SB10" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SPACE_PREFIX" ] && [ ! -e "$UNIT10" ] || fail "Space-prefix uninstall left files behind"
pass "--prefix with spaces produced systemd-quoted units and uninstalled cleanly"

echo "=== Case 11 (Review 58 #5f): Stale stage dirs with marker are cleaned; unmarked user dirs survive ==="
SB11="$(new_sandbox stale-stage)"
DATA11="$SB11/.local/share/rook"
mkdir -p "$DATA11/.rook-stage-venv-old123" "$DATA11/.tmp-download-old456" "$DATA11/.rook-stage-user"
printf 'rook-installer-stage-v1\n' >"$DATA11/.rook-stage-venv-old123/.rook-install-stage"
printf 'rook-installer-stage-v1\n' >"$DATA11/.tmp-download-old456/.rook-install-stage"
echo "user-owned-dotdir" >"$DATA11/.rook-stage-user/keep.txt"
set +e
run_in_sb "$SB11" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC11=$?
set -e
[ "$RC11" -eq 2 ] || fail "Stale-stage cleanup run failed (rc=$RC11)"
[ ! -e "$DATA11/.rook-stage-venv-old123" ] || fail "Marked stale .rook-stage-* dir was not cleaned"
[ ! -e "$DATA11/.tmp-download-old456" ] || fail "Marked stale .tmp-download-* dir was not cleaned"
[ -f "$DATA11/.rook-stage-user/keep.txt" ] || fail "Unmarked user folder .rook-stage-user/keep.txt was deleted!"
pass "Stale marked stage dirs cleaned on next run while unmarked user .rook-stage-user survived"

echo "=== Case 12 (Review 58 #6): Real SIGTERM and SIGKILL at each step, then rerun and uninstall ==="
plant_canaries() {
  local sb="$1"
  mkdir -p "$sb/Documents" "$sb/.config/rook" "$sb/.local/state/rook" "$sb/.local/share/rook/.rook-stage-user" "$sb/.config/systemd/user"
  echo "canary-doc" >"$sb/Documents/canary.txt"
  echo "canary-cfg" >"$sb/.config/rook/canary.txt"
  echo "canary-state" >"$sb/.local/state/rook/canary.txt"
  echo "canary-data" >"$sb/.local/share/rook/user-canary.txt"
  echo "canary-stage" >"$sb/.local/share/rook/.rook-stage-user/canary.txt"
  echo "canary-unit" >"$sb/.config/systemd/user/user-custom.service"
}

assert_canaries() {
  local sb="$1"
  local when="$2"
  [ "$(cat "$sb/Documents/canary.txt")" = "canary-doc" ] || fail "Documents canary lost ($when)"
  [ "$(cat "$sb/.config/rook/canary.txt")" = "canary-cfg" ] || fail "Config canary lost ($when)"
  [ "$(cat "$sb/.local/state/rook/canary.txt")" = "canary-state" ] || fail "State canary lost ($when)"
  [ "$(cat "$sb/.local/share/rook/user-canary.txt")" = "canary-data" ] || fail "Data canary lost ($when)"
  [ "$(cat "$sb/.local/share/rook/.rook-stage-user/canary.txt")" = "canary-stage" ] || fail "Unmarked stage canary lost ($when)"
  [ "$(cat "$sb/.config/systemd/user/user-custom.service")" = "canary-unit" ] || fail "Systemd canary lost ($when)"
}

for sig in TERM KILL; do
  for step_name in git-clone uv-venv uv-voice systemctl; do
    SB12="$(new_sandbox "kill-${sig}-${step_name}")"
    plant_canaries "$SB12"
    SYNC_FILE="$TEST_ROOT/sync-${sig}-${step_name}.pid"
    rm -f "$SYNC_FILE"

    run_in_sb "$SB12" env KILL_SYNC_STEP="$step_name" KILL_SYNC_FILE="$SYNC_FILE" \
      bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" \
      >"$TEST_ROOT/kill-${sig}-${step_name}.log" 2>&1 &
    INST_PID=$!

    waited=0
    while [ ! -s "$SYNC_FILE" ] && [ "$waited" -lt 200 ]; do
      sleep 0.05
      waited=$((waited + 1))
    done
    [ -s "$SYNC_FILE" ] || fail "Installer never reached sync point $step_name for SIG$sig (log: $(cat "$TEST_ROOT/kill-${sig}-${step_name}.log"))"
    CHILD_PID="$(cat "$SYNC_FILE")"

    # Send the real signal to the installer and its active child, then wait for termination.
    kill "-$sig" "$INST_PID" 2>/dev/null || true
    kill "-$sig" "$CHILD_PID" 2>/dev/null || true
    wait "$INST_PID" 2>/dev/null || true
    assert_canaries "$SB12" "after SIG$sig at $step_name"

    if [ "$sig" = "TERM" ]; then
      # On SIGTERM, trap must have removed our marked stage dirs.
      for cand in "$SB12/.local/share/rook"/.rook-stage-* "$SB12/.local/share/rook"/.tmp-download-*; do
        [ -e "$cand" ] || continue
        if [ -f "$cand/.rook-install-stage" ]; then
          fail "SIGTERM at $step_name left marked stage dir $cand behind"
        fi
      done
    fi

    # Rerun cleanly -> must clean any SIGKILL stage dirs, finish cleanly (rc=2), and keep all canaries.
    set +e
    run_in_sb "$SB12" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
    RC12_RERUN=$?
    set -e
    [ "$RC12_RERUN" -eq 2 ] || fail "Rerun after SIG$sig at $step_name failed (rc=$RC12_RERUN)"
    assert_canaries "$SB12" "after rerun following SIG$sig at $step_name"
    for cand in "$SB12/.local/share/rook"/.rook-stage-* "$SB12/.local/share/rook"/.tmp-download-*; do
      [ -e "$cand" ] || continue
      if [ -f "$cand/.rook-install-stage" ]; then
        fail "Rerun after SIG$sig at $step_name did not clean stale marked stage dir $cand"
      fi
    done

    # Uninstall cleanly -> must remove Rook items and keep every planted canary file!
    run_in_sb "$SB12" bash "$UNINSTALL_SH" --yes >/dev/null
    [ ! -e "$SB12/.local/share/rook/live" ] || fail "live remained after uninstall ($sig/$step_name)"
    [ ! -e "$SB12/.local/share/rook/venv" ] || fail "venv remained after uninstall ($sig/$step_name)"
    [ ! -e "$SB12/.local/share/rook/voice-phonon" ] || fail "voice-phonon remained after uninstall ($sig/$step_name)"
    [ ! -e "$SB12/.config/systemd/user/rook.service" ] || fail "rook.service remained after uninstall ($sig/$step_name)"
    assert_canaries "$SB12" "after uninstall following SIG$sig at $step_name"
  done
done
pass "Real SIGTERM and SIGKILL at all 4 steps (8 scenarios) recovered on rerun, uninstalled cleanly, and preserved every canary"

echo "=== Case 13 (Review 65 #1): Pre-existing unrecorded venv is refused; --use-existing-env installs nothing into it ==="
SB13="$(new_sandbox foreign-venv)"
DATA13="$SB13/.local/share/rook"
# Build a pre-existing runnable voice-phonon venv manually (simulating old INSTALL.md instructions).
mkdir -p "$DATA13/voice-phonon/bin" "$DATA13/voice-phonon/lib/stub"
cat >"$DATA13/voice-phonon/bin/python" <<'PY'
#!/usr/bin/env bash
VENV_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$VENV_DIR/lib/stub${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 "$@"
PY
chmod +x "$DATA13/voice-phonon/bin/python"
printf '__version__ = "0.7.1-user"\n' >"$DATA13/voice-phonon/lib/stub/ptts.py"
printf '__version__ = "2.0-user"\n' >"$DATA13/voice-phonon/lib/stub/numpy.py"
printf 'user-custom-pkg\n' >"$DATA13/voice-phonon/lib/stub/my_custom_pkg.py"
UV_LOG13="$TEST_ROOT/uv-case13.log"
: >"$UV_LOG13"
set +e
OUT13_REFUSE="$(run_in_sb "$SB13" env FAKE_UV_LOG="$UV_LOG13" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC13_REFUSE=$?
set -e
[ "$RC13_REFUSE" -ne 0 ] || fail "Installer should refuse pre-existing unrecorded voice-phonon venv!"
printf '%s\n' "$OUT13_REFUSE" | grep -q "voice-phonon" || fail "Refusal did not name the folder"
printf '%s\n' "$OUT13_REFUSE" | grep -q -- "--use-existing-env" || fail "Refusal did not mention --use-existing-env"
if grep -q "voice-phonon" "$UV_LOG13"; then
  fail "uv pip install ran into unrecorded voice-phonon before refusal!"
fi
# Now run with --use-existing-env: must succeed, install NOTHING into voice-phonon, and keep it across uninstall!
: >"$UV_LOG13"
set +e
OUT13_OK="$(run_in_sb "$SB13" env FAKE_UV_LOG="$UV_LOG13" bash "$INSTALL_SH" --use-existing-env --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC13_OK=$?
set -e
[ "$RC13_OK" -eq 2 ] || fail "--use-existing-env install failed (rc=$RC13_OK): $OUT13_OK"
if grep -q "voice-phonon" "$UV_LOG13"; then
  fail "--use-existing-env ran uv pip install into voice-phonon! Log: $(cat "$UV_LOG13")"
fi
[ "$(cat "$DATA13/voice-phonon/lib/stub/my_custom_pkg.py")" = "user-custom-pkg" ] || fail "User package inside voice-phonon was altered!"
# Rerun WITHOUT --use-existing-env must still refuse the kept pre-existing environment!
: >"$UV_LOG13"
if run_in_sb "$SB13" env FAKE_UV_LOG="$UV_LOG13" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1; then
  fail "Rerun without --use-existing-env should still refuse kept unrecorded voice-phonon!"
fi
if grep -q "voice-phonon" "$UV_LOG13"; then
  fail "Rerun without --use-existing-env ran uv pip install into voice-phonon!"
fi
run_in_sb "$SB13" bash "$UNINSTALL_SH" --yes >/dev/null
[ -f "$DATA13/voice-phonon/lib/stub/my_custom_pkg.py" ] || fail "Uninstall deleted pre-existing voice-phonon!"
pass "Unrecorded venv refused by default (including on rerun); --use-existing-env installed nothing into it and uninstall kept it"

echo "=== Case 14 (Review 65 #2): Unit ownership by content hash (copied marker + edited unit + drop-in) ==="
# 14a. Person copied the marker line into their own rook.service BEFORE install.
SB14A="$(new_sandbox unit-copied-marker)"
SYS14A="$SB14A/.config/systemd/user"
mkdir -p "$SYS14A"
USER_UNIT14A="$(printf '# Managed by Rook install/install.sh\n[Unit]\nDescription=My personal rook service\n[Service]\nExecStart=/usr/bin/my-rook\n')"
printf '%s\n' "$USER_UNIT14A" >"$SYS14A/rook.service"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT14A="$(run_in_sb "$SB14A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC14A=$?
set -e
[ "$RC14A" -eq 2 ] || fail "14a install failed (rc=$RC14A): $OUT14A"
[ "$(cat "$SYS14A/rook.service")" = "$USER_UNIT14A" ] || fail "User unit with copied marker was OVERWRITTEN!"
printf '%s\n' "$OUT14A" | grep -q -- "--replace-units" || fail "14a did not tell user how to replace unit"
if grep -q "enable" "$TEST_ROOT/systemctl.log"; then
  fail "14a enabled units when rook.service was unowned! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
[ ! -e "$SYS14A/rook-failed.service" ] && [ ! -e "$SYS14A/rook-daily.service" ] && [ ! -e "$SYS14A/rook-daily.timer" ] \
  || fail "14a wrote helper/timer units despite unowned rook.service!"
: >"$TEST_ROOT/systemctl.log"
run_in_sb "$SB14A" bash "$UNINSTALL_SH" --yes >/dev/null
[ "$(cat "$SYS14A/rook.service")" = "$USER_UNIT14A" ] || fail "14a uninstall deleted user unit with copied marker!"
if grep -q "rook.service" "$TEST_ROOT/systemctl.log"; then
  fail "14a uninstall stopped/disabled unowned rook.service! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi

# 14b. Person adds Environment= line to installer's rook.service AND creates rook.service.d/override.conf.
SB14B="$(new_sandbox unit-edited)"
SYS14B="$SB14B/.config/systemd/user"
set +e
run_in_sb "$SB14B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC14B1=$?
set -e
[ "$RC14B1" -eq 2 ] || fail "14b initial install failed ($RC14B1)"
printf 'Environment=MY_CUSTOM=1\n' >>"$SYS14B/rook.service"
mkdir -p "$SYS14B/rook.service.d"
printf '[Service]\nEnvironment=DROPIN=1\n' >"$SYS14B/rook.service.d/override.conf"
# Rerun with --service yes must NOT wipe the user's Environment= line or drop-in!
set +e
OUT14B2="$(run_in_sb "$SB14B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC14B2=$?
set -e
[ "$RC14B2" -eq 2 ] || fail "14b rerun failed ($RC14B2)"
grep -q "Environment=MY_CUSTOM=1" "$SYS14B/rook.service" || fail "14b rerun wiped user's Environment= line!"
grep -q "Environment=DROPIN=1" "$SYS14B/rook.service.d/override.conf" || fail "14b rerun touched rook.service.d!"
printf '%s\n' "$OUT14B2" | grep -q -- "--replace-units" || fail "14b rerun did not mention --replace-units"
# Uninstall must leave edited rook.service + drop-in intact and NEVER stop/disable rook.service!
: >"$TEST_ROOT/systemctl.log"
run_in_sb "$SB14B" bash "$UNINSTALL_SH" --yes >/dev/null
grep -q "Environment=MY_CUSTOM=1" "$SYS14B/rook.service" || fail "14b uninstall deleted edited rook.service!"
grep -q "Environment=DROPIN=1" "$SYS14B/rook.service.d/override.conf" || fail "14b uninstall touched rook.service.d!"
[ ! -e "$SYS14B/rook-daily.timer" ] || fail "14b uninstall should remove untouched rook-daily.timer"
if grep -q "rook.service" "$TEST_ROOT/systemctl.log"; then
  fail "14b uninstall called systemctl on edited rook.service! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
# Explicit --replace-units replaces rook.service while keeping rook.service.d/ intact.
set +e
run_in_sb "$SB14B" bash "$INSTALL_SH" --replace-units --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC14B3=$?
set -e
[ "$RC14B3" -eq 2 ] || fail "14b --replace-units failed ($RC14B3)"
! grep -q "Environment=MY_CUSTOM=1" "$SYS14B/rook.service" || fail "--replace-units did not replace rook.service"
grep -q "Environment=DROPIN=1" "$SYS14B/rook.service.d/override.conf" || fail "--replace-units touched rook.service.d!"
pass "Unit ownership enforced by SHA256 hash: copied marker, edited unit, and rook.service.d all protected"

echo "=== Case 15 (Review 65 #4a): Newline in filename inside venv installs and uninstalls cleanly ==="
SB15="$(new_sandbox newline-venv)"
set +e
run_in_sb "$SB15" env FAKE_UV_NEWLINE_FILE=1 bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC15=$?
set -e
[ "$RC15" -eq 2 ] || fail "Newline-filename venv install failed ($RC15)"
run_in_sb "$SB15" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB15/.local/share/rook/venv" ] && [ ! -e "$SB15/.local/share/rook" ] || fail "Newline-filename venv was not cleanly uninstalled"
pass "Venv containing a filename with a newline installed and uninstalled cleanly with exit 0"

echo "=== Case 16 (Review 65 #5 + Review 68 #3d/#3e): Real SIGTERM/SIGKILL in record-to-rename and swap windows (no hook in install.sh) ==="
# Verify shipped install.sh contains no test kill hook.
if grep -q "ROOK_INSTALL_TEST_KILL\|_test_kill_point" "$INSTALL_SH"; then
  fail "Shipped install.sh still contains a test kill hook!"
fi
# 16a. Kills inside record-to-rename and unit-before-write windows (fresh install).
for sig in TERM KILL; do
  for kp in prefix-before-rename venv-before-rename unit-before-write; do
    SB16A="$(new_sandbox "kp-${sig}-${kp}")"
    plant_canaries "$SB16A"
    KF="$TEST_ROOT/kp-${sig}-${kp}.pid"
    rm -f "$KF"
    run_in_sb "$SB16A" env KILL_SYNC_STEP="$kp" KILL_SYNC_FILE="$KF" \
      bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" \
      >"$TEST_ROOT/kp-${sig}-${kp}.log" 2>&1 &
    PID16=$!
    waited=0
    while [ ! -s "$KF" ] && [ "$waited" -lt 200 ]; do
      sleep 0.05
      waited=$((waited + 1))
    done
    [ -s "$KF" ] || fail "Never reached kill point $kp for SIG$sig (log: $(cat "$TEST_ROOT/kp-${sig}-${kp}.log"))"
    CHILD16="$(cat "$KF")"
    kill "-$sig" "$PID16" 2>/dev/null || true
    kill "-$sig" "$CHILD16" 2>/dev/null || true
    wait "$PID16" 2>/dev/null || true
    assert_canaries "$SB16A" "after SIG$sig at $kp"
    set +e
    run_in_sb "$SB16A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
    RC16R=$?
    set -e
    [ "$RC16R" -eq 2 ] || fail "Rerun after SIG$sig at $kp failed ($RC16R)"
    run_in_sb "$SB16A" bash "$UNINSTALL_SH" --yes >/dev/null
    [ ! -e "$SB16A/.local/share/rook/live" ] && [ ! -e "$SB16A/.local/share/rook/venv" ] && [ ! -e "$SB16A/.local/share/rook/voice-phonon" ] || fail "Uninstall after $sig/$kp left Rook dirs behind"
    assert_canaries "$SB16A" "after uninstall following SIG$sig at $kp"
  done
done

# 16b. Kills inside environment swap (venv-swap-after-move-old) with files planted INSIDE live, venv, and voice-phonon!
for sig in TERM KILL; do
  SB16B="$(new_sandbox "swap-kill-${sig}")"
  plant_canaries "$SB16B"
  WHEEL16="$TEST_ROOT/airtype-swap-kill-${sig}.whl"
  echo "swap-v1" >"$WHEEL16"
  set +e
  run_in_sb "$SB16B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$WHEEL16" >/dev/null 2>&1
  RC16I=$?
  set -e
  [ "$RC16I" -eq 2 ] || fail "16b initial install failed ($RC16I)"
  # Plant personal files INSIDE live, venv, and voice-phonon!
  echo "inside-live-note" >"$SB16B/.local/share/rook/live/my-work.txt"
  echo "inside-venv-note" >"$SB16B/.local/share/rook/venv/my-notes.txt"
  echo "inside-voice-note" >"$SB16B/.local/share/rook/voice-phonon/my-notes.txt"
  echo "swap-v2" >"$WHEEL16"
  KF="$TEST_ROOT/swap-kill-${sig}.pid"
  rm -f "$KF"
  run_in_sb "$SB16B" env KILL_SYNC_STEP="venv-swap-after-move-old" KILL_SYNC_FILE="$KF" \
    bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$WHEEL16" \
    >"$TEST_ROOT/swap-kill-${sig}.log" 2>&1 &
  PID16B=$!
  waited=0
  while [ ! -s "$KF" ] && [ "$waited" -lt 200 ]; do
    sleep 0.05
    waited=$((waited + 1))
  done
  [ -s "$KF" ] || fail "Never reached venv-swap-after-move-old for SIG$sig"
  CHILD16B="$(cat "$KF")"
  kill "-$sig" "$PID16B" 2>/dev/null || true
  kill "-$sig" "$CHILD16B" 2>/dev/null || true
  wait "$PID16B" 2>/dev/null || true
  # Verify venv.kept-* is ALREADY recorded in manifest.kept and holds my-notes.txt!
  KEPT16="$(find "$SB16B/.local/share/rook" -maxdepth 1 -type d -name 'venv.kept-*' | head -n 1)"
  [ -n "$KEPT16" ] && [ "$(cat "$KEPT16/my-notes.txt")" = "inside-venv-note" ] || fail "venv.kept-*/my-notes.txt missing after swap SIG$sig!"
  grep -qF "$KEPT16" "$SB16B/.local/share/rook/install-manifest.json" || fail "venv.kept-* was NOT recorded in manifest before swap move (SIG$sig)!"
  [ "$(cat "$SB16B/.local/share/rook/live/my-work.txt")" = "inside-live-note" ] || fail "live/my-work.txt lost after swap SIG$sig"
  [ "$(cat "$SB16B/.local/share/rook/voice-phonon/my-notes.txt")" = "inside-voice-note" ] || fail "voice-phonon/my-notes.txt lost after swap SIG$sig"
  # Rerun cleanly -> rebuilds fresh venv while keeping all planted files inside live, venv.kept-*, voice-phonon!
  set +e
  run_in_sb "$SB16B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$WHEEL16" >/dev/null 2>&1
  RC16BR=$?
  set -e
  [ "$RC16BR" -eq 2 ] || fail "16b rerun after swap SIG$sig failed ($RC16BR)"
  # Uninstall -> removes fresh clean venv & clean units; keeps live, voice-phonon, venv.kept-*, and ALL planted files!
  run_in_sb "$SB16B" bash "$UNINSTALL_SH" --yes >/dev/null
  [ ! -e "$SB16B/.local/share/rook/venv" ] || fail "Fresh clean venv should be removed by uninstall ($sig)"
  [ "$(cat "$SB16B/.local/share/rook/live/my-work.txt")" = "inside-live-note" ] || fail "live/my-work.txt deleted by uninstall ($sig)!"
  [ "$(cat "$KEPT16/my-notes.txt")" = "inside-venv-note" ] || fail "venv.kept-*/my-notes.txt deleted by uninstall ($sig)!"
  [ "$(cat "$SB16B/.local/share/rook/voice-phonon/my-notes.txt")" = "inside-voice-note" ] || fail "voice-phonon/my-notes.txt deleted by uninstall ($sig)!"
  assert_canaries "$SB16B" "after swap SIG$sig + rerun + uninstall"
done

# 16c. SIGKILL during swap of a CLEAN installer venv -> next rerun cleans up the clean venv.kept-* aside folder!
SB16C="$(new_sandbox swap-kill-clean)"
WHEEL16C="$TEST_ROOT/airtype-swap-clean-kill.whl"
echo "clean-v1" >"$WHEEL16C"
set +e
run_in_sb "$SB16C" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$WHEEL16C" >/dev/null 2>&1
RC16C1=$?
set -e
[ "$RC16C1" -eq 2 ] || fail "16c initial install failed ($RC16C1)"
echo "clean-v2" >"$WHEEL16C"
KF16C="$TEST_ROOT/swap-kill-clean.pid"
rm -f "$KF16C"
run_in_sb "$SB16C" env KILL_SYNC_STEP="venv-swap-after-move-old" KILL_SYNC_FILE="$KF16C" \
  bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$WHEEL16C" \
  >"$TEST_ROOT/swap-kill-clean.log" 2>&1 &
PID16C=$!
waited=0
while [ ! -s "$KF16C" ] && [ "$waited" -lt 200 ]; do
  sleep 0.05
  waited=$((waited + 1))
done
[ -s "$KF16C" ] || fail "16c never reached venv-swap-after-move-old"
CHILD16C="$(cat "$KF16C")"
kill -KILL "$PID16C" 2>/dev/null || true
kill -KILL "$CHILD16C" 2>/dev/null || true
wait "$PID16C" 2>/dev/null || true
KEPT16C="$(find "$SB16C/.local/share/rook" -maxdepth 1 -type d -name 'venv.kept-*' | head -n 1)"
[ -n "$KEPT16C" ] || fail "16c expected clean venv.kept-* after swap SIGKILL"
set +e
OUT16CR="$(run_in_sb "$SB16C" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$WHEEL16C" 2>&1)"
RC16CR=$?
set -e
[ "$RC16CR" -eq 2 ] || fail "16c rerun failed ($RC16CR): $OUT16CR"
[ ! -e "$KEPT16C" ] || fail "16c rerun did not clean up clean swap backup $KEPT16C!"
run_in_sb "$SB16C" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB16C/.local/share/rook" ] || fail "16c uninstall left files behind"
pass "Kills in record-to-rename, unit-before-write, and dirty/clean swap windows all recovered cleanly with no hook in install.sh"

echo "=== Case 17 (Review 68 #1): Unowned rook.service writes none of the four units and never enables the timer ==="
for kind in file symlink; do
  SB17="$(new_sandbox "unowned-unit-${kind}")"
  SYS17="$SB17/.config/systemd/user"
  mkdir -p "$SYS17"
  if [ "$kind" = "file" ]; then
    printf '[Unit]\nDescription=My own rook unit\n[Service]\nExecStart=/usr/local/bin/my-rook\n' >"$SYS17/rook.service"
  else
    printf '[Unit]\nDescription=My symlinked rook unit\n[Service]\nExecStart=/usr/local/bin/my-rook\n' >"$SB17/my-rook.service"
    ln -s "$SB17/my-rook.service" "$SYS17/rook.service"
  fi
  : >"$TEST_ROOT/systemctl.log"
  set +e
  OUT17="$(run_in_sb "$SB17" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
  RC17=$?
  set -e
  [ "$RC17" -eq 2 ] || fail "17 ($kind) install failed ($RC17): $OUT17"
  [ ! -e "$SYS17/rook-failed.service" ] || fail "17 ($kind) wrote rook-failed.service despite unowned rook.service!"
  [ ! -e "$SYS17/rook-daily.service" ] || fail "17 ($kind) wrote rook-daily.service despite unowned rook.service!"
  [ ! -e "$SYS17/rook-daily.timer" ] || fail "17 ($kind) wrote rook-daily.timer despite unowned rook.service!"
  if grep -q "enable" "$TEST_ROOT/systemctl.log"; then
    fail "17 ($kind) called systemctl enable when rook.service was unowned! Log: $(cat "$TEST_ROOT/systemctl.log")"
  fi
  printf '%s\n' "$OUT17" | grep -q -- "--replace-units" || fail "17 ($kind) did not mention --replace-units: $OUT17"
done
pass "Unowned rook.service (file and symlink) skipped all four units and never enabled rook-daily.timer"

echo "=== Case 18 (Review 68 #2): --replace-units saves dated copy, records it in kept, and uninstall keeps & explains restore ==="
SB18="$(new_sandbox replace-units-backup)"
SYS18="$SB18/.config/systemd/user"
mkdir -p "$SYS18"
ORIG18="$(printf '[Unit]\nDescription=My handcrafted rook service\n[Service]\nExecStart=/usr/local/bin/custom-rook --mine\n')"
printf '%s\n' "$ORIG18" >"$SYS18/rook.service"
set +e
OUT18_INST="$(run_in_sb "$SB18" bash "$INSTALL_SH" --replace-units --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC18_INST=$?
set -e
[ "$RC18_INST" -eq 2 ] || fail "18 --replace-units install failed ($RC18_INST): $OUT18_INST"
BACKUP18="$(find "$SYS18" -maxdepth 1 -type f -name 'rook.service.replaced-*' | head -n 1)"
[ -n "$BACKUP18" ] || fail "18 --replace-units did not create rook.service.replaced-* backup!"
[ "$(cat "$BACKUP18")" = "$ORIG18" ] || fail "18 dated backup content does not match original rook.service!"
grep -qF "# Managed by Rook install/install.sh" "$SYS18/rook.service" || fail "18 rook.service was not replaced"
printf '%s\n' "$OUT18_INST" | grep -qF "$BACKUP18" || fail "18 install output did not print where original copy was saved"
grep -qF "$BACKUP18" "$SB18/.local/share/rook/install-manifest.json" || fail "18 dated backup not recorded in manifest"
# Dry-run, real uninstall (--purge --yes), and nothing-to-remove rerun must all print the restore note (with mv -n and enable).
OUT18_DRY="$(run_in_sb "$SB18" bash "$UNINSTALL_SH" --dry-run 2>&1)"
printf '%s\n' "$OUT18_DRY" | grep -qF "$BACKUP18" || fail "18 dry-run did not print original unit backup path"
printf '%s\n' "$OUT18_DRY" | grep -q "mv -n -- " || fail "18 dry-run did not suggest non-overwriting mv -n"
printf '%s\n' "$OUT18_DRY" | grep -q "enable rook.service" || fail "18 dry-run did not mention re-enabling rook.service"
OUT18_UNINST="$(run_in_sb "$SB18" bash "$UNINSTALL_SH" --purge --yes 2>&1)"
[ ! -e "$SYS18/rook.service" ] || fail "18 uninstall should remove installer replacement rook.service (and not auto-restore)"
[ ! -e "$SYS18/rook-daily.timer" ] || fail "18 uninstall should remove installer rook-daily.timer"
[ -f "$BACKUP18" ] && [ "$(cat "$BACKUP18")" = "$ORIG18" ] || fail "18 uninstall deleted or altered original dated backup!"
printf '%s\n' "$OUT18_UNINST" | grep -qF "$BACKUP18" || fail "18 uninstall did not tell user where original unit copy is"
printf '%s\n' "$OUT18_UNINST" | grep -q "mv -n -- " || fail "18 uninstall did not suggest non-overwriting mv -n"
printf '%s\n' "$OUT18_UNINST" | grep -q "enable rook.service" || fail "18 uninstall did not mention re-enabling rook.service"
OUT18_NOOP="$(run_in_sb "$SB18" bash "$UNINSTALL_SH" --yes 2>&1)"
printf '%s\n' "$OUT18_NOOP" | grep -qF "$BACKUP18" || fail "18 nothing-to-remove uninstall did not print restore note"
printf '%s\n' "$OUT18_NOOP" | grep -q "mv -n -- " || fail "18 nothing-to-remove uninstall did not print mv -n hint"
# --replace-units must be refused when ~/.config/systemd/user is itself a symlink (e.g. into a dotfiles repo).
SB18L="$(new_sandbox replace-units-symlink-dir)"
mkdir -p "$SB18L/dotfiles-systemd" "$SB18L/.config/systemd"
printf '%s\n' "$ORIG18" >"$SB18L/dotfiles-systemd/rook.service"
ln -s "$SB18L/dotfiles-systemd" "$SB18L/.config/systemd/user"
set +e
OUT18L="$(run_in_sb "$SB18L" bash "$INSTALL_SH" --replace-units --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC18L=$?
set -e
[ "$RC18L" -ne 0 ] || fail "18L should refuse --replace-units when systemd/user is a symlink!"
[ "$(cat "$SB18L/dotfiles-systemd/rook.service")" = "$ORIG18" ] || fail "18L modified unit inside symlinked systemd/user!"
printf '%s\n' "$OUT18L" | grep -qi "symlink" || fail "18L refusal did not mention symlink: $OUT18L"
pass "--replace-units preserved original unit across install/uninstall (dry-run, purge, noop) with mv -n + enable hint, and refused symlinked unit dir"

echo "=== Case 19 (Review 70 #1): Rerun after person replaces rook.service disables/removes installer timer without touching user units ==="
# 19a. Install --service yes, person replaces rook.service, rerun --service yes.
SB19A="$(new_sandbox rerun-replaced-rook-service)"
SYS19A="$SB19A/.config/systemd/user"
set +e
run_in_sb "$SB19A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC19A1=$?
set -e
[ "$RC19A1" -eq 2 ] || fail "19a initial install failed ($RC19A1)"
[ -f "$SYS19A/rook-daily.timer" ] && [ -f "$SYS19A/rook-daily.service" ] || fail "19a initial install missing daily units"
USER_ROOK19A="$(printf '[Unit]\nDescription=My replacement rook unit\n[Service]\nExecStart=/usr/local/bin/my-rook\n')"
printf '%s\n' "$USER_ROOK19A" >"$SYS19A/rook.service"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT19A2="$(run_in_sb "$SB19A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC19A2=$?
set -e
[ "$RC19A2" -eq 2 ] || fail "19a rerun failed ($RC19A2): $OUT19A2"
[ "$(cat "$SYS19A/rook.service")" = "$USER_ROOK19A" ] || fail "19a rerun altered person's rook.service!"
[ ! -e "$SYS19A/rook-daily.timer" ] || fail "19a rerun did not remove installer-owned rook-daily.timer!"
[ ! -e "$SYS19A/rook-daily.service" ] || fail "19a rerun did not remove installer-owned rook-daily.service!"
grep -qF -- "--user disable --now rook-daily.timer" "$TEST_ROOT/systemctl.log" \
  || fail "19a systemctl log missing disable --now rook-daily.timer! Log: $(cat "$TEST_ROOT/systemctl.log")"
if grep -q "enable" "$TEST_ROOT/systemctl.log"; then
  fail "19a systemctl log unexpectedly ran enable! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
if printf '%s\n' "$OUT19A2" | grep -qi "skipped all four"; then
  fail "19a output falsely said 'Skipped all four'! Output: $OUT19A2"
fi
printf '%s\n' "$OUT19A2" | grep -q -- "--replace-units" || fail "19a output did not mention --replace-units"

# 19b. Same, except person also edited rook-daily.timer: edited timer is left alone, NOT disabled,
# and installer-owned rook-daily.service stays in place so the person's timer does not break.
SB19B="$(new_sandbox rerun-replaced-rook-and-timer)"
SYS19B="$SB19B/.config/systemd/user"
set +e
run_in_sb "$SB19B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC19B1=$?
set -e
[ "$RC19B1" -eq 2 ] || fail "19b initial install failed ($RC19B1)"
printf '%s\n' "$USER_ROOK19A" >"$SYS19B/rook.service"
printf '# person edited timer\n' >>"$SYS19B/rook-daily.timer"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT19B2="$(run_in_sb "$SB19B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC19B2=$?
set -e
[ "$RC19B2" -eq 2 ] || fail "19b rerun failed ($RC19B2): $OUT19B2"
grep -qF "# person edited timer" "$SYS19B/rook-daily.timer" || fail "19b rerun deleted or modified person-edited rook-daily.timer!"
[ -f "$SYS19B/rook-daily.service" ] || fail "19b rerun deleted rook-daily.service while person's timer still starts it!"
if grep -q "rook-daily.timer" "$TEST_ROOT/systemctl.log"; then
  fail "19b rerun touched person-edited rook-daily.timer via systemctl! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
printf '%s\n' "$OUT19B2" | grep -qF "systemctl --user disable --now rook-daily.timer" || fail "19b did not tell person how to switch off their timer: $OUT19B2"
pass "Rerun after person replaced rook.service disabled/removed installer timer+daily service, kept daily service when timer was edited, and reported truthfully"

echo "=== Case 20 (Review 70 #2): Person's rook-daily.service blocks timer enable on both fresh install and rerun ==="
# 20a. Fresh install with person's rook-daily.service already present.
SB20A="$(new_sandbox fresh-user-daily-service)"
SYS20A="$SB20A/.config/systemd/user"
mkdir -p "$SYS20A"
USER_DAILY20="$(printf '[Unit]\nDescription=My own daily service\n[Service]\nType=oneshot\nExecStart=/usr/local/bin/my-daily\n')"
printf '%s\n' "$USER_DAILY20" >"$SYS20A/rook-daily.service"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT20A="$(run_in_sb "$SB20A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC20A=$?
set -e
[ "$RC20A" -eq 2 ] || fail "20a install failed ($RC20A): $OUT20A"
[ "$(cat "$SYS20A/rook-daily.service")" = "$USER_DAILY20" ] || fail "20a overwrote person's rook-daily.service!"
[ -f "$SYS20A/rook.service" ] || fail "20a should still install rook.service"
[ ! -e "$SYS20A/rook-daily.timer" ] || fail "20a wrote rook-daily.timer despite unowned rook-daily.service!"
if grep -q "rook-daily.timer" "$TEST_ROOT/systemctl.log"; then
  fail "20a enabled rook-daily.timer when rook-daily.service was unowned! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
grep -qF -- "--user enable rook.service" "$TEST_ROOT/systemctl.log" \
  || fail "20a did not enable owned rook.service! Log: $(cat "$TEST_ROOT/systemctl.log")"

# 20b. Install --service yes, later person replaces rook-daily.service, rerun disables/removes installer timer.
SB20B="$(new_sandbox rerun-replaced-daily-service)"
SYS20B="$SB20B/.config/systemd/user"
set +e
run_in_sb "$SB20B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC20B1=$?
set -e
[ "$RC20B1" -eq 2 ] || fail "20b initial install failed ($RC20B1)"
printf '%s\n' "$USER_DAILY20" >"$SYS20B/rook-daily.service"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT20B2="$(run_in_sb "$SB20B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC20B2=$?
set -e
[ "$RC20B2" -eq 2 ] || fail "20b rerun failed ($RC20B2): $OUT20B2"
[ "$(cat "$SYS20B/rook-daily.service")" = "$USER_DAILY20" ] || fail "20b rerun altered person's rook-daily.service!"
[ ! -e "$SYS20B/rook-daily.timer" ] || fail "20b rerun did not remove installer-owned rook-daily.timer!"
grep -qF -- "--user disable --now rook-daily.timer" "$TEST_ROOT/systemctl.log" \
  || fail "20b rerun did not disable rook-daily.timer! Log: $(cat "$TEST_ROOT/systemctl.log")"
if grep -q "enable.*rook-daily.timer" "$TEST_ROOT/systemctl.log"; then
  fail "20b rerun enabled rook-daily.timer! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
pass "Person's rook-daily.service blocked timer enable on fresh install and disabled/removed installer timer on rerun"

echo "=== Case 21 (Review 73 #1): Person edits OnCalendar in rook-daily.timer (or wrong hash) -> rook-daily.service stays intact ==="
# 21a. Person edits only OnCalendar in rook-daily.timer, then reruns --service yes.
SB21A="$(new_sandbox edited-timer-oncalendar)"
SYS21A="$SB21A/.config/systemd/user"
set +e
run_in_sb "$SB21A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC21A1=$?
set -e
[ "$RC21A1" -eq 2 ] || fail "21a initial install failed ($RC21A1)"
sed -i 's/04:30:00/06:15:00/' "$SYS21A/rook-daily.timer"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT21A2="$(run_in_sb "$SB21A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC21A2=$?
set -e
[ "$RC21A2" -eq 2 ] || fail "21a rerun failed ($RC21A2): $OUT21A2"
grep -qF "06:15:00" "$SYS21A/rook-daily.timer" || fail "21a modified person's edited rook-daily.timer!"
[ -f "$SYS21A/rook-daily.service" ] || fail "21a deleted rook-daily.service, breaking person's edited timer!"
grep -qF "rook-daily.service" "$SB21A/.local/share/rook/install-manifest.json" || fail "21a dropped rook-daily.service from manifest!"
if grep -q "disable.*rook-daily.timer" "$TEST_ROOT/systemctl.log"; then
  fail "21a disabled person's edited rook-daily.timer! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
if grep -q "daemon-reload" "$TEST_ROOT/systemctl.log"; then
  fail "21a ran daemon-reload when no unit file changed! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
if printf '%s\n' "$OUT21A2" | grep -q "Switched off and removed"; then
  fail "21a output falsely claimed units were switched off and removed: $OUT21A2"
fi
printf '%s\n' "$OUT21A2" | grep -qF "systemctl --user disable --now rook-daily.timer" || fail "21a output did not show how to switch off the timer: $OUT21A2"

# 21b. Manifest with a wrong sha256 for rook-daily.timer yields the same safe result.
SB21B="$(new_sandbox wrong-timer-hash)"
SYS21B="$SB21B/.config/systemd/user"
set +e
run_in_sb "$SB21B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC21B1=$?
set -e
[ "$RC21B1" -eq 2 ] || fail "21b initial install failed ($RC21B1)"
python3 - "$SB21B/.local/share/rook/install-manifest.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
for e in d["entries"]:
    if str(e.get("path", "")).endswith("/rook-daily.timer"):
        e["sha256"] = "0" * 64
p.write_text(json.dumps(d, indent=2) + "\n")
PY
: >"$TEST_ROOT/systemctl.log"
set +e
OUT21B2="$(run_in_sb "$SB21B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC21B2=$?
set -e
[ "$RC21B2" -eq 2 ] || fail "21b rerun failed ($RC21B2): $OUT21B2"
[ -f "$SYS21B/rook-daily.service" ] || fail "21b deleted rook-daily.service despite mismatched timer hash!"
if grep -q "disable.*rook-daily.timer" "$TEST_ROOT/systemctl.log"; then
  fail "21b disabled rook-daily.timer despite hash mismatch! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
pass "Edited OnCalendar timer and wrong-hash timer both left rook-daily.service intact and reported truthfully"

echo "=== Case 22 (Review 73 #2 + #5): daemon-reload only when units change; no --wow or rook.service.d drop-in ==="
SB22="$(new_sandbox no-reload-unchanged)"
SYS22="$SB22/.config/systemd/user"
: >"$TEST_ROOT/systemctl.log"
set +e
run_in_sb "$SB22" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC22_1=$?
set -e
[ "$RC22_1" -eq 2 ] || fail "22 initial install failed ($RC22_1)"
grep -qF -- "--user daemon-reload" "$TEST_ROOT/systemctl.log" || fail "22 initial install should run daemon-reload"
! grep -q -- "--wow" "$SYS22/rook.service" || fail "22 rook.service should not carry --wow!"
[ ! -e "$SYS22/rook.service.d" ] || fail "22 installer should never create rook.service.d drop-ins!"
: >"$TEST_ROOT/systemctl.log"
set +e
run_in_sb "$SB22" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC22_2=$?
set -e
[ "$RC22_2" -eq 2 ] || fail "22 unchanged rerun failed ($RC22_2)"
if grep -q "daemon-reload" "$TEST_ROOT/systemctl.log"; then
  fail "22 unchanged rerun called daemon-reload even though no unit changed! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
pass "Unchanged --service yes rerun skipped daemon-reload, and rook.service omitted --wow with no drop-in created"

echo "=== Case 23 (Review 73 #3): --service no enforces timer rule on rerun; uninstall note is truthful per unit ==="
# 23a. Install --service yes, person edits rook.service, rerun with --service no -> disables/removes installer timer.
SB23A="$(new_sandbox service-no-timer-rule)"
SYS23A="$SB23A/.config/systemd/user"
set +e
run_in_sb "$SB23A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC23A1=$?
set -e
[ "$RC23A1" -eq 2 ] || fail "23a initial install failed ($RC23A1)"
printf '# person took over rook.service\n' >>"$SYS23A/rook.service"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT23A2="$(run_in_sb "$SB23A" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC23A2=$?
set -e
[ "$RC23A2" -eq 2 ] || fail "23a --service no rerun failed ($RC23A2): $OUT23A2"
grep -qF "# person took over rook.service" "$SYS23A/rook.service" || fail "23a altered person's rook.service!"
[ ! -e "$SYS23A/rook-daily.timer" ] && [ ! -e "$SYS23A/rook-daily.service" ] || fail "23a --service no rerun left installer daily units behind!"
grep -qF -- "--user disable --now rook-daily.timer" "$TEST_ROOT/systemctl.log" \
  || fail "23a --service no rerun did not disable rook-daily.timer! Log: $(cat "$TEST_ROOT/systemctl.log")"
if grep -q "enable" "$TEST_ROOT/systemctl.log"; then
  fail "23a --service no rerun unexpectedly called enable! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi

# 23b. Backed-up rook-daily.service uninstall note must NOT say 're-enable' or 'uninstall disabled'.
SB23B="$(new_sandbox daily-backup-note)"
SYS23B="$SB23B/.config/systemd/user"
mkdir -p "$SYS23B"
printf '[Unit]\nDescription=My daily\n[Service]\nType=oneshot\nExecStart=/bin/true\n' >"$SYS23B/rook-daily.service"
set +e
run_in_sb "$SB23B" bash "$INSTALL_SH" --replace-units --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC23B=$?
set -e
[ "$RC23B" -eq 2 ] || fail "23b --replace-units install failed ($RC23B)"
OUT23B_DRY="$(run_in_sb "$SB23B" bash "$UNINSTALL_SH" --dry-run 2>&1)"
printf '%s\n' "$OUT23B_DRY" | grep -qF "rook-daily.service.replaced-" || fail "23b dry-run missing rook-daily.service backup note"
printf '%s\n' "$OUT23B_DRY" | grep -q "mv -n -- " || fail "23b dry-run missing mv -n hint"
if printf '%s\n' "$OUT23B_DRY" | grep -q "re-enable\|uninstall disabled"; then
  fail "23b rook-daily.service restore note wrongly said re-enable/disabled: $OUT23B_DRY"
fi
pass "--service no rerun disabled installer timer after rook.service edit, and rook-daily.service restore note omitted false re-enable claim"

echo "=== Case 24 (Review 73 #4): --agent codex writes settings, checks PATH, never runs codex mcp login ==="
SB24="$(new_sandbox agent-codex)"
CODEX_LOG24="$TEST_ROOT/codex.log"
: >"$CODEX_LOG24"
FAKE_CODEX_DIR="$TEST_ROOT/fake-codex-bin"
mkdir -p "$FAKE_CODEX_DIR"
cat >"$FAKE_CODEX_DIR/codex" <<'SH'
#!/usr/bin/env bash
echo "codex $*" >> "${FAKE_CODEX_LOG:-/dev/null}"
exit 99
SH
chmod +x "$FAKE_CODEX_DIR/codex"
# Run with fake codex on PATH (installer must detect it, NEVER invoke it, and tell user to run codex mcp login t3).
set +e
OUT24="$(run_in_sb "$SB24" env PATH="$FAKE_BIN:$FAKE_CODEX_DIR:$PATH" FAKE_CODEX_LOG="$CODEX_LOG24" \
  bash "$INSTALL_SH" --agent codex --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC24=$?
set -e
[ "$RC24" -eq 2 ] || fail "24 --agent codex install failed ($RC24): $OUT24"
python3 - "$SB24/.config/rook/settings.json" <<'PY'
import json, sys
d = json.loads(open(sys.argv[1]).read())
assert d.get("agent") == "codex", f"expected agent=codex, got {d}"
PY
printf '%s\n' "$OUT24" | grep -qF "codex mcp login t3" || fail "24 output did not tell user to run codex mcp login t3: $OUT24"
[ ! -s "$CODEX_LOG24" ] || fail "24 installer ran codex itself! Log: $(cat "$CODEX_LOG24")"
pass "--agent codex saved setting, found codex on PATH, printed manual codex mcp login t3 step, and never ran codex"

echo "=== Case 25 (Review 74 #1 + #2): Uninstall warns on dangling edited/wrong-hash timer and only claims disabled when disabled ==="
# 25a. Person edits rook-daily.timer, then uninstalls: timer kept, not disabled, output warns and gives disable command.
SB25A="$(new_sandbox uninstall-edited-timer)"
SYS25A="$SB25A/.config/systemd/user"
set +e
run_in_sb "$SB25A" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC25A=$?
set -e
[ "$RC25A" -eq 2 ] || fail "25a initial install failed ($RC25A)"
sed -i 's/04:30:00/06:15:00/' "$SYS25A/rook-daily.timer"
: >"$TEST_ROOT/systemctl.log"
OUT25A="$(run_in_sb "$SB25A" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -f "$SYS25A/rook-daily.timer" ] || fail "25a uninstall deleted person's edited rook-daily.timer!"
[ ! -e "$SYS25A/rook-daily.service" ] && [ ! -e "$SYS25A/rook.service" ] || fail "25a uninstall should remove installer services"
if grep -q "rook-daily.timer" "$TEST_ROOT/systemctl.log"; then
  fail "25a uninstall called systemctl on person's edited rook-daily.timer! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
printf '%s\n' "$OUT25A" | grep -qF "rook-daily.timer" || fail "25a uninstall output did not name rook-daily.timer"
printf '%s\n' "$OUT25A" | grep -qF "if it is enabled, it will now fail" || fail "25a uninstall output did not warn timer will fail if enabled: $OUT25A"
printf '%s\n' "$OUT25A" | grep -qF "systemctl --user disable --now rook-daily.timer" || fail "25a uninstall output missing disable command: $OUT25A"

# 25b. Manifest with wrong sha256 hash for rook-daily.timer gives the same warning without touching the timer.
SB25B="$(new_sandbox uninstall-wrong-timer-hash)"
SYS25B="$SB25B/.config/systemd/user"
set +e
run_in_sb "$SB25B" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC25B=$?
set -e
[ "$RC25B" -eq 2 ] || fail "25b initial install failed ($RC25B)"
python3 - "$SB25B/.local/share/rook/install-manifest.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
for e in d["entries"]:
    if str(e.get("path", "")).endswith("/rook-daily.timer"):
        e["sha256"] = "0" * 64
p.write_text(json.dumps(d, indent=2) + "\n")
PY
: >"$TEST_ROOT/systemctl.log"
OUT25B="$(run_in_sb "$SB25B" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -f "$SYS25B/rook-daily.timer" ] || fail "25b uninstall deleted wrong-hash rook-daily.timer!"
[ ! -e "$SYS25B/rook-daily.service" ] || fail "25b uninstall should remove owned rook-daily.service"
if grep -q "rook-daily.timer" "$TEST_ROOT/systemctl.log"; then
  fail "25b uninstall called systemctl on wrong-hash rook-daily.timer! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
printf '%s\n' "$OUT25B" | grep -qF "systemctl --user disable --now rook-daily.timer" || fail "25b uninstall output missing disable command: $OUT25B"

# 25c (Item 2). After --replace-units, person edits the new rook.service and uninstalls: restore note must NOT say disabled.
SB25C="$(new_sandbox replace-then-edit-uninstall)"
SYS25C="$SB25C/.config/systemd/user"
mkdir -p "$SYS25C"
printf '[Unit]\nDescription=Original\n[Service]\nExecStart=/bin/true\n' >"$SYS25C/rook.service"
set +e
run_in_sb "$SB25C" bash "$INSTALL_SH" --replace-units --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC25C=$?
set -e
[ "$RC25C" -eq 2 ] || fail "25c --replace-units install failed ($RC25C)"
printf '# person edited replaced rook.service\n' >>"$SYS25C/rook.service"
: >"$TEST_ROOT/systemctl.log"
OUT25C="$(run_in_sb "$SB25C" bash "$UNINSTALL_SH" --yes 2>&1)"
if grep -q "rook.service" "$TEST_ROOT/systemctl.log"; then
  fail "25c uninstall disabled edited rook.service! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
if printf '%s\n' "$OUT25C" | grep -q "uninstall disabled this unit"; then
  fail "25c restore note falsely claimed uninstall disabled rook.service: $OUT25C"
fi
pass "Uninstall warned clearly on dangling edited/wrong-hash timer and omitted false disabled claim for kept rook.service"

echo "=== Case 26 (Review 74 #3 + #4): Unchanged rerun does not re-enable disabled units; user timer wording makes no unverified claims ==="
SB26="$(new_sandbox rerun-respects-disabled)"
set +e
run_in_sb "$SB26" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC26_1=$?
set -e
[ "$RC26_1" -eq 2 ] || fail "26 initial install failed ($RC26_1)"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT26_2="$(run_in_sb "$SB26" env FAKE_SYSTEMCTL_DISABLED="rook.service rook-daily.timer" \
  bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC26_2=$?
set -e
[ "$RC26_2" -eq 2 ] || fail "26 rerun failed ($RC26_2): $OUT26_2"
if grep -q "enable " "$TEST_ROOT/systemctl.log"; then
  fail "26 unchanged rerun re-enabled units the person switched off! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
if grep -q "daemon-reload" "$TEST_ROOT/systemctl.log"; then
  fail "26 unchanged rerun called daemon-reload! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
printf '%s\n' "$OUT26_2" | grep -qF "rook.service is installed but switched off (left disabled). To turn it on, run: systemctl --user enable --now rook.service" || fail "26 missing disabled note + command for rook.service: $OUT26_2"
printf '%s\n' "$OUT26_2" | grep -qF "rook-daily.timer is installed but switched off (left disabled). To turn it on, run: systemctl --user enable --now rook-daily.timer" || fail "26 missing disabled note + command for rook-daily.timer: $OUT26_2"
# Verify edited-timer wording makes no unverified claim about schedule or running each night.
sed -i 's/04:30:00/07:00:00/' "$SB26/.config/systemd/user/rook-daily.timer"
set +e
OUT26_3="$(run_in_sb "$SB26" bash "$INSTALL_SH" --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC26_3=$?
set -e
[ "$RC26_3" -eq 2 ] || fail "26 edited-timer rerun failed ($RC26_3)"
if printf '%s\n' "$OUT26_3" | grep -q "each night\|still runs at your scheduled time"; then
  fail "26 edited-timer message made unverified schedule/enabled claim: $OUT26_3"
fi
printf '%s\n' "$OUT26_3" | grep -qF "rook-daily.timer is yours and was left as it is" || fail "26 missing truthful timer note: $OUT26_3"
pass "Unchanged rerun left disabled units off with a note, and user-timer message made no unverified claims"

echo "=== Case 27: Medium voice: --service no writes no unit; --service yes owns it; uninstall removes unit and files ==="
SB27="$(new_sandbox medium-voice)"
SYS27="$SB27/.config/systemd/user"
MED27="$SB27/.local/share/rook/medium-voice"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT27_1="$(run_in_sb "$SB27" env FAKE_GPU="8.6, 12288, 580.95.05" bash "$INSTALL_SH" --voice medium --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC27_1=$?
set -e
[ "$RC27_1" -eq 2 ] || fail "27 --service no install failed ($RC27_1): $OUT27_1"
[ -f "$MED27/models/qwen-talker-0.6b-base-BF16.gguf" ] || fail "27 medium voice model was not fetched"
[ ! -e "$SYS27/rook-medium-voice.service" ] || fail "27 --service no wrote rook-medium-voice.service"
printf '%s\n' "$OUT27_1" | grep -qF "Start it by hand with: $MED27/venv/bin/python" || fail "27 missing the hand start command: $OUT27_1"
grep -qF '"medium_voice_url": "http://127.0.0.1:8090"' "$SB27/.config/rook/settings.json" || fail "27 settings lack the local medium_voice_url"
set +e
run_in_sb "$SB27" env FAKE_GPU="8.6, 12288, 580.95.05" bash "$INSTALL_SH" --voice medium --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC27_2=$?
set -e
[ "$RC27_2" -eq 2 ] || fail "27 --service yes rerun failed ($RC27_2)"
grep -qF "medium_voice.py" "$SYS27/rook-medium-voice.service" || fail "27 --service yes did not write rook-medium-voice.service"
grep -qF -- "--user enable --now rook-medium-voice.service" "$TEST_ROOT/systemctl.log" || fail "27 did not enable the medium unit. Log: $(cat "$TEST_ROOT/systemctl.log")"
run_in_sb "$SB27" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SYS27/rook-medium-voice.service" ] || fail "27 uninstall left rook-medium-voice.service"
[ ! -e "$MED27" ] || fail "27 uninstall left $MED27"
grep -qF -- "--user disable --now rook-medium-voice.service" "$TEST_ROOT/systemctl.log" || fail "27 uninstall did not stop the medium unit. Log: $(cat "$TEST_ROOT/systemctl.log")"
pass "Medium voice wrote no unit under --service no and printed the hand command; uninstall removed its unit, environment and model"

echo "=== Case 28: Mac: a failed medium voice keeps the small voice, the install finishes, and uninstall leaves no voice job ==="
SB28="$(new_sandbox mac-medium-fail)"
MAC_BIN="$TEST_ROOT/fake-mac-bin"
mkdir -p "$MAC_BIN"
cat >"$MAC_BIN/uname" <<'SH'
#!/usr/bin/env bash
case "${1:-}" in -m) echo arm64 ;; *) echo Darwin ;; esac
SH
cat >"$MAC_BIN/sw_vers" <<'SH'
#!/usr/bin/env bash
echo 15.6
SH
cat >"$MAC_BIN/xcode-select" <<'SH'
#!/usr/bin/env bash
echo /Library/Developer/CommandLineTools
SH
cat >"$MAC_BIN/sysctl" <<'SH'
#!/usr/bin/env bash
echo 25769803776
SH
cat >"$MAC_BIN/launchctl" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "${FAKE_LAUNCHCTL_LOG:-/dev/null}"
# Ctrl+C while the medium voice waits for its server: install.sh, the voice script's parent, gets TERM.
if [ -n "${FAKE_LAUNCHCTL_STOP_INSTALL:-}" ] && [ "${1:-}" = "bootstrap" ] && [[ "${3:-}" == *com.rook.medium-voice.plist ]]; then
  kill -TERM "$(ps -o ppid= -p "$PPID" | tr -d ' ')"
fi
exit 0
SH
cat >"$MAC_BIN/curl" <<'SH'
#!/usr/bin/env bash
# The medium voice server answers its health check only when FAKE_CURL_OK is set.
[ -z "${FAKE_CURL_OK:-}" ] || exit 0
echo "ERROR: curl must never be called ($*)" >&2
exit 99
SH
cat >"$MAC_BIN/clang" <<'SH'
#!/usr/bin/env bash
while [ "$#" -gt 0 ]; do [ "$1" = "-o" ] && { mkdir -p "$(dirname "$2")"; echo stub >"$2"; chmod +x "$2"; }; shift; done
SH
cat >"$MAC_BIN/codesign" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$MAC_BIN"/*
: >"$TEST_ROOT/launchctl.log"
# The fake curl refuses every call, so the medium voice server's health check never answers: the failed first run.
set +e
OUT28_1="$(run_in_sb "$SB28" env PATH="$MAC_BIN:$FAKE_BIN:$PATH" FAKE_LAUNCHCTL_LOG="$TEST_ROOT/launchctl.log" ROOK_SIGN_IDENTITY=- \
  ROOK_SYSTEM_APPS="$SB28/no-system-apps" \
  bash "$INSTALL_SH" --voice medium --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC28_1=$?
set -e
PLIST28="$SB28/Library/LaunchAgents/com.rook.medium-voice.plist"
[ "$RC28_1" -eq 2 ] || fail "28 install did not finish after the medium voice failed ($RC28_1): $OUT28_1"
printf '%s\n' "$OUT28_1" | grep -qF "Warning: The medium voice did not install (The medium voice server did not start." \
  || fail "28 missing the medium voice warning with its reason: $OUT28_1"
printf '%s\n' "$OUT28_1" | grep -qF "==> [8/8] Installing Rook.app and its launchd agent" || fail "28 install stopped before its last step: $OUT28_1"
grep -qF '"voice_engine": "small"' "$SB28/.config/rook/settings.json" || fail "28 settings did not keep the small voice"
[ "$(grep 'com.rook.medium-voice' "$TEST_ROOT/launchctl.log" | tail -n 1)" = "bootout gui/$(id -u)/com.rook.medium-voice" ] \
  || fail "28 the failed medium voice job was left loaded. Log: $(cat "$TEST_ROOT/launchctl.log")"
[ -f "$PLIST28" ] || fail "28 medium voice plist was not written"
python3 - "$SB28/.local/share/rook/install-manifest.json" "$PLIST28" <<'PY' || fail "28 manifest does not own the medium voice plist with its hash"
import hashlib, json, os, sys
entries = json.load(open(sys.argv[1]))["entries"]
want = os.path.normpath(sys.argv[2])
sha = hashlib.sha256(open(want, "rb").read()).hexdigest()
sys.exit(0 if any(e.get("path") == want and e.get("created") and e.get("sha256") == sha for e in entries) else 1)
PY
: >"$TEST_ROOT/launchctl.log"
run_in_sb "$SB28" env PATH="$MAC_BIN:$FAKE_BIN:$PATH" FAKE_LAUNCHCTL_LOG="$TEST_ROOT/launchctl.log" \
  ROOK_SYSTEM_APPS="$SB28/no-system-apps" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$PLIST28" ] || fail "28 uninstall left the medium voice plist"
[ ! -e "$SB28/.local/share/rook/medium-voice" ] || fail "28 uninstall left the medium voice folder"
grep -qF "bootout gui/$(id -u)/com.rook.medium-voice" "$TEST_ROOT/launchctl.log" || fail "28 uninstall did not boot out the medium voice job"
pass "Mac medium voice failure: warned with the reason, kept the small voice, finished, and uninstall removed the plist, job and folder"

mac_sb() {  # mac_sb SANDBOX [ENV=VALUE...] -- SCRIPT [OPTIONS...]: run install.sh or uninstall.sh on the faked Mac.
  local sb="$1"; shift
  local envs=()
  while [ "$1" != "--" ]; do envs+=("$1"); shift; done
  shift
  # ROOK_SYSTEM_APPS: a scratch stand-in for /Applications, so on a real Mac no case builds into the real one. A
  # case's own ROOK_SYSTEM_APPS, given later, wins.
  run_in_sb "$sb" env PATH="$MAC_BIN:$FAKE_BIN:$PATH" FAKE_LAUNCHCTL_LOG="$TEST_ROOT/launchctl.log" ROOK_SIGN_IDENTITY=- \
    ROOK_SYSTEM_APPS="$sb/no-system-apps" \
    "${envs[@]}" bash "$@"
}
medium_lines() { grep 'com.rook.medium-voice' "$TEST_ROOT/launchctl.log" || true; }

echo "=== Case 29: Linux: a medium voice that fails with nothing on stderr keeps the small voice, and the install finishes ==="
SB29="$(new_sandbox linux-medium-silent)"
SYS29="$SB29/.config/systemd/user"
: >"$TEST_ROOT/systemctl.log"
set +e
OUT29="$(run_in_sb "$SB29" env FAKE_GPU="8.6, 12288, 580.95.05" FAIL_UV_PIP_SILENT_ON="medium-voice" bash "$INSTALL_SH" \
  --voice medium --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC29=$?
set -e
[ "$RC29" -eq 2 ] || fail "29 install did not finish after a silent medium voice failure ($RC29): $OUT29"
printf '%s\n' "$OUT29" | grep -qF "Warning: The medium voice did not install (medium-voice.sh stopped without saying why). Rook keeps its small voice. Details: $SB29/.local/state/rook/medium-voice-install.log." \
  || fail "29 missing the warning with the log path: $OUT29"
printf '%s\n' "$OUT29" | grep -qF "==> [7/8] Installing the medium voice (optional)" || fail "29 medium voice step label is wrong: $OUT29"
printf '%s\n' "$OUT29" | grep -qF "==> [8/8] Installing systemd user service units" || fail "29 last step label is wrong: $OUT29"
grep -qF '"voice_engine": "small"' "$SB29/.config/rook/settings.json" || fail "29 settings did not keep the small voice"
[ ! -e "$SYS29/rook-medium-voice.service" ] || fail "29 wrote rook-medium-voice.service for a voice that failed"
run_in_sb "$SB29" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SB29/.local/share/rook/medium-voice" ] || fail "29 uninstall left the failed medium voice folder"
pass "Linux silent medium voice failure: warned with the log path, kept the small voice, right step numbers, clean uninstall"

echo "=== Case 30: Mac: an interrupt during the medium voice's health wait leaves an owned job that uninstall stops and removes ==="
SB30="$(new_sandbox mac-medium-interrupt)"
PLIST30="$SB30/Library/LaunchAgents/com.rook.medium-voice.plist"
: >"$TEST_ROOT/launchctl.log"
set +e
mac_sb "$SB30" FAKE_LAUNCHCTL_STOP_INSTALL=1 -- "$INSTALL_SH" --voice medium --voice-model no --recogniser no --service yes \
  --recogniser-source "$FAKE_WHEEL" >"$TEST_ROOT/out30.txt" 2>&1
RC30=$?
set -e
[ "$RC30" -ne 0 ] && [ "$RC30" -ne 2 ] || fail "30 install was not stopped by the interrupt ($RC30): $(cat "$TEST_ROOT/out30.txt")"
[ "$(medium_lines | tail -n 1)" = "bootstrap gui/$(id -u) $PLIST30" ] || fail "30 the job was not left loaded: $(medium_lines)"
: >"$TEST_ROOT/launchctl.log"
mac_sb "$SB30" -- "$UNINSTALL_SH" --yes >/dev/null
grep -qF "bootout gui/$(id -u)/com.rook.medium-voice" "$TEST_ROOT/launchctl.log" || fail "30 uninstall did not stop the medium voice job"
[ ! -e "$PLIST30" ] || fail "30 uninstall left the medium voice plist"
[ ! -e "$SB30/.local/share/rook" ] || fail "30 uninstall left files this run created: $(find "$SB30/.local/share/rook" | head -5)"
pass "Mac interrupt during the health wait: the plist was owned by its hash, and uninstall stopped the job and removed it all"

echo "=== Case 31: Mac: a medium voice plist that was there before and is not ours stays untouched ==="
SB31="$(new_sandbox mac-medium-foreign)"
PLIST31="$SB31/Library/LaunchAgents/com.rook.medium-voice.plist"
mkdir -p "$(dirname "$PLIST31")"
printf '%s\n' '<plist><!-- written by hand with launchd/install-voice.sh --></plist>' >"$PLIST31"
FOREIGN31="$(sha256sum "$PLIST31")"
for run in 1 2; do
  : >"$TEST_ROOT/launchctl.log"
  set +e
  OUT31="$(mac_sb "$SB31" FAKE_CURL_OK=1 -- "$INSTALL_SH" --voice medium --voice-model no --recogniser no --service yes \
    --recogniser-source "$FAKE_WHEEL" 2>&1)"
  RC31=$?
  set -e
  [ "$RC31" -eq 2 ] || fail "31 run $run failed ($RC31): $OUT31"
  printf '%s\n' "$OUT31" | grep -qF "Kept $PLIST31 as it is, because this installer did not write it" || fail "31 run $run said nothing: $OUT31"
  [ "$(sha256sum "$PLIST31")" = "$FOREIGN31" ] || fail "31 run $run changed the plist"
  [ -z "$(medium_lines)" ] || fail "31 run $run touched the medium voice job: $(medium_lines)"
  ! grep -qF "$PLIST31" "$SB31/.local/share/rook/install-manifest.json" || fail "31 run $run recorded the plist as its own"
done
: >"$TEST_ROOT/launchctl.log"
mac_sb "$SB31" -- "$UNINSTALL_SH" --yes >/dev/null
[ "$(sha256sum "$PLIST31")" = "$FOREIGN31" ] || fail "31 uninstall changed or removed the plist"
[ -z "$(medium_lines)" ] || fail "31 uninstall touched the medium voice job: $(medium_lines)"
pass "Mac foreign medium voice plist: untouched by install, rerun and uninstall, with one sentence saying so"

echo "=== Case 32: Mac: a rerun that fails after a good install leaves the working medium voice running and selected ==="
SB32="$(new_sandbox mac-medium-rerun)"
PLIST32="$SB32/Library/LaunchAgents/com.rook.medium-voice.plist"
: >"$TEST_ROOT/launchctl.log"
set +e
mac_sb "$SB32" FAKE_CURL_OK=1 -- "$INSTALL_SH" --voice medium --voice-model no --recogniser no --service yes \
  --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC32_1=$?
set -e
[ "$RC32_1" -eq 2 ] || fail "32 the first, good install failed ($RC32_1)"
grep -qF '"voice_engine": "medium"' "$SB32/.config/rook/settings.json" || fail "32 the good install did not select the medium voice"
: >"$TEST_ROOT/launchctl.log"
set +e
OUT32="$(mac_sb "$SB32" FAKE_CURL_OK=1 FAIL_UV_PIP_SILENT_ON=medium-voice -- "$INSTALL_SH" --voice medium --voice-model no \
  --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC32_2=$?
set -e
[ "$RC32_2" -eq 2 ] || fail "32 the failing rerun did not finish ($RC32_2): $OUT32"
printf '%s\n' "$OUT32" | grep -qF "The medium voice from before keeps running." || fail "32 missing the keeps-running warning: $OUT32"
grep -qF '"voice_engine": "medium"' "$SB32/.config/rook/settings.json" || fail "32 the failing rerun unselected the working voice"
! medium_lines | grep -q bootout || fail "32 the failing rerun stopped the working voice: $(medium_lines)"
[ -f "$PLIST32" ] || fail "32 the working voice's plist is gone"
mac_sb "$SB32" -- "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$PLIST32" ] || fail "32 uninstall left the medium voice plist"
pass "Mac failing rerun after a good install: the working medium voice kept running and stayed selected"

# Cases 33 and 34 search a PATH that holds no uwsm, whatever this machine has: every system program but uwsm, by link.
NO_UWSM="$TEST_ROOT/no-uwsm-bin"
mkdir -p "$NO_UWSM"
for prog in /usr/bin/*; do
  case "${prog##*/}" in uwsm*) ;; *) ln -s "$prog" "$NO_UWSM/${prog##*/}" ;; esac
done
agent_sb() {  # A sandbox with Claude Code in ~/.local/bin, as its own installer puts it.
  local sb
  sb="$(new_sandbox "$1")"
  mkdir -p "$sb/.local/bin"
  printf '#!/bin/sh\nexit 0\n' >"$sb/.local/bin/claude"
  chmod +x "$sb/.local/bin/claude"
  printf '%s\n' "$sb"
}
install_in() {  # install_in SANDBOX [VAR=VALUE...]: --service yes with the sandbox's agent and no uwsm on PATH.
  local sb="$1"; shift
  run_in_sb "$sb" env PATH="$sb/.local/bin:$FAKE_BIN:$NO_UWSM" "$@" bash "$INSTALL_SH" --agent claude --voice small \
    --voice-model no --recogniser no --service yes --recogniser-source "$FAKE_WHEEL" 2>&1
}

echo "=== Case 33: The unit gets a PATH line only when the agent's folder is missing from the manager's PATH ==="
SB33="$(agent_sb path-missing)"
set +e
OUT33="$(install_in "$SB33" FAKE_SYSTEMCTL_PATH=/usr/local/bin:/usr/bin)"
RC33=$?
set -e
[ "$RC33" -eq 2 ] || fail "33 install failed ($RC33): $OUT33"
grep -qxF "Environment=\"PATH=$SB33/.local/bin:/usr/local/bin:/usr/bin\"" "$SB33/.config/systemd/user/rook.service" \
  || fail "33 no PATH line for a missing agent folder: $(cat "$SB33/.config/systemd/user/rook.service")"
SB33B="$(agent_sb path-present)"
set +e
OUT33B="$(install_in "$SB33B" FAKE_SYSTEMCTL_PATH="$SB33B/.local/bin:/usr/bin")"
RC33B=$?
set -e
[ "$RC33B" -eq 2 ] || fail "33 second install failed ($RC33B): $OUT33B"
! grep -q '^Environment="PATH=' "$SB33B/.config/systemd/user/rook.service" || fail "33 wrote a PATH line the manager did not need"
SB33C="$(agent_sb path-unknown)"
set +e
OUT33C="$(install_in "$SB33C")"
RC33C=$?
set -e
[ "$RC33C" -eq 2 ] || fail "33 third install failed ($RC33C): $OUT33C"
! grep -q '^Environment="PATH=' "$SB33C/.config/systemd/user/rook.service" || fail "33 wrote a PATH line with no manager PATH known"
pass "The PATH line appears only when the manager's PATH lacks the agent's folder"

echo "=== Case 34: The start target follows the session: graphical-session.target or uwsm keeps today's unit, else default.target ==="
SB34A="$(agent_sb target-default)"
set +e
OUT34A="$(install_in "$SB34A" FAKE_SYSTEMCTL_INACTIVE=1)"
RC34A=$?
set -e
[ "$RC34A" -eq 2 ] || fail "34 install failed ($RC34A): $OUT34A"
UNIT34A="$SB34A/.config/systemd/user/rook.service"
grep -qx "WantedBy=default.target" "$UNIT34A" || fail "34 no default.target without a session target: $(cat "$UNIT34A")"
! grep -q "graphical-session" "$UNIT34A" || fail "34 kept graphical-session.target lines: $(cat "$UNIT34A")"
for mode in active uwsm; do
  SB34="$(agent_sb "target-$mode")"
  if [ "$mode" = uwsm ]; then
    printf '#!/bin/sh\nexit 0\n' >"$SB34/.local/bin/uwsm"
    chmod +x "$SB34/.local/bin/uwsm"
    set +e; OUT34="$(install_in "$SB34" FAKE_SYSTEMCTL_INACTIVE=1)"; RC34=$?; set -e
  else
    set +e; OUT34="$(install_in "$SB34")"; RC34=$?; set -e
  fi
  [ "$RC34" -eq 2 ] || fail "34 $mode install failed ($RC34): $OUT34"
  UNIT34="$SB34/.config/systemd/user/rook.service"
  for line in "PartOf=graphical-session.target" "After=graphical-session.target" "WantedBy=graphical-session.target"; do
    grep -qxF "$line" "$UNIT34" || fail "34 $mode lost today's line $line: $(cat "$UNIT34")"
  done
done
for mode in active inactive; do
  SB34="$(agent_sb "target-link-$mode")"
  mkdir -p "$SB34/.config/systemd/user"
  printf '[Service]\nExecStart=/bin/true\n' >"$SB34/my-rook.service"
  ln -s "$SB34/my-rook.service" "$SB34/.config/systemd/user/rook.service"
  BEFORE34="$(sha256sum "$SB34/my-rook.service")"
  set +e
  if [ "$mode" = inactive ]; then OUT34="$(install_in "$SB34" FAKE_SYSTEMCTL_INACTIVE=1)"; else OUT34="$(install_in "$SB34")"; fi
  set -e
  [ -L "$SB34/.config/systemd/user/rook.service" ] || fail "34 $mode replaced the person's symlinked unit"
  [ "$(sha256sum "$SB34/my-rook.service")" = "$BEFORE34" ] || fail "34 $mode wrote through the person's symlinked unit"
done
pass "The start target follows the session, and a symlinked unit stays untouched either way"

echo "=== Case 35: An old uv that cannot fetch the pinned Python stops the install with one plain sentence ==="
SB35="$(new_sandbox uv-old)"
set +e
OUT35="$(run_in_sb "$SB35" env FAKE_UV_OLD=1 bash "$INSTALL_SH" --voice-model no --recogniser no --service no \
  --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC35=$?
set -e
[ "$RC35" -eq 1 ] || fail "35 an old uv did not stop the install ($RC35): $OUT35"
printf '%s\n' "$OUT35" | grep -qF "Error: uv 0.5.8 is too old for Rook: it cannot fetch Python 3.12.14." || fail "35 missing the plain sentence: $OUT35"
printf '%s\n' "$OUT35" | grep -qF "Fix: Replace it with: curl -LsSf https://astral.sh/uv/install.sh | sh" || fail "35 missing the fix: $OUT35"
[ ! -e "$SB35/.local/share/rook/venv" ] || fail "35 built an environment with the old uv"
OUT35B="$(run_in_sb "$SB35" env FAKE_UV_OLD=1 FAKE_UV_VERSION_FAILS=1 bash "$INSTALL_SH" --voice-model no --recogniser no \
  --service no --recogniser-source "$FAKE_WHEEL" 2>&1 || true)"
printf '%s\n' "$OUT35B" | grep -qF "Error: The uv at $FAKE_BIN/uv is too old for Rook" || fail "35 a uv with no version was not named: $OUT35B"
OUT35C="$(run_in_sb "$SB35" env FAKE_UV_OLD=1 UV_PYTHON_DOWNLOADS=never bash "$INSTALL_SH" --voice-model no --recogniser no \
  --service no --recogniser-source "$FAKE_WHEEL" 2>&1 || true)"
printf '%s\n' "$OUT35C" | grep -qF "Error: UV_PYTHON_DOWNLOADS=never stops uv from fetching Python 3.12.14, which Rook needs." \
  || fail "35 the download setting was not named: $OUT35C"
pass "Old uv: the install stops before the environments with 'uv 0.5.8 is too old', names a uv with no version, and names a setting that forbids downloads"

echo "=== Case 36: get.sh replaces an old uv with uv's own installer, and says so plainly when that fails ==="
GET_SH="$SCRIPT_DIR/get.sh"
UVI_BIN="$TEST_ROOT/fake-uv-installer-bin"
mkdir -p "$UVI_BIN"
NEW_UV="$TEST_ROOT/new-uv"  # The uv that uv's installer puts in place: a current one.
printf '%s\n' '#!/usr/bin/env bash' "FAKE_UV_OLD= exec \"$FAKE_BIN/uv\" \"\$@\"" >"$NEW_UV"
chmod +x "$NEW_UV"
cat >"$UVI_BIN/curl" <<SH
#!/usr/bin/env bash
# uv's installer, in its own folder order. It records whether it was told to leave the shell files alone.
# FAKE_UV_INSTALL_FAILS makes the download fail.
case "\$*" in *astral.sh/uv/install.sh*) ;; *) echo "ERROR: curl must never be called (\$*)" >&2; exit 99 ;; esac
[ -z "\${FAKE_UV_INSTALL_FAILS:-}" ] || { echo "curl: (6) Could not resolve host: astral.sh" >&2; exit 6; }
echo 'd="\${UV_INSTALL_DIR:-\${XDG_BIN_HOME:-\${XDG_DATA_HOME:+\$XDG_DATA_HOME/../bin}}}"; d="\${d:-\$HOME/.local/bin}"; mkdir -p "\$d" && cp "$NEW_UV" "\$d/uv"'
echo 'echo "UV_NO_MODIFY_PATH=\${UV_NO_MODIFY_PATH:-unset}" >> "\$HOME/uv-installer.log"; echo "everything is installed!"'
SH
chmod +x "$UVI_BIN/curl"
SB36="$(new_sandbox get-uv-old)"
set +e
OUT36="$(run_in_sb "$SB36" env PATH="$UVI_BIN:$FAKE_BIN:$PATH" FAKE_UV_OLD=1 sh "$GET_SH" "$REPO_ROOT" --agent claude --voice small \
  --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC36=$?
set -e
# Exit 2, not 0: --voice-model no and --recogniser no leave the setup incomplete on purpose, which install.sh reports
# with 2. It proves the install ran to its end with the new uv.
[ "$RC36" -eq 2 ] || fail "36 get.sh did not finish the install after replacing uv ($RC36): $OUT36"
printf '%s\n' "$OUT36" | grep -qF "uv 0.5.8 cannot fetch Python 3.12.14, which Rook needs, so uv's own installer puts a newer uv in $SB36/.local/bin, ahead of the one at $FAKE_BIN/uv, which stays as it is." \
  || fail "36 missing the replacement line: $OUT36"
grep -qx "UV_NO_MODIFY_PATH=1" "$SB36/uv-installer.log" || fail "36 uv's installer was allowed to edit the shell files"
! printf '%s\n' "$OUT36" | grep -qF "too old for Rook" || fail "36 still called uv too old after replacing it: $OUT36"
[ -x "$SB36/.local/bin/uv" ] && [ -d "$SB36/.local/share/rook/venv" ] || fail "36 the new uv did not build the environments"
SB36B="$(new_sandbox get-uv-old-fails)"
set +e
OUT36B="$(run_in_sb "$SB36B" env PATH="$UVI_BIN:$FAKE_BIN:$PATH" FAKE_UV_OLD=1 FAKE_UV_INSTALL_FAILS=1 sh "$GET_SH" "$REPO_ROOT" \
  --agent claude --voice small --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC36B=$?
set -e
[ "$RC36B" -eq 1 ] || fail "36 a failed uv install did not stop get.sh ($RC36B): $OUT36B"
printf '%s\n' "$OUT36B" | grep -qF "Error: uv 0.5.8 is too old for Rook: it cannot fetch Python 3.12.14. Replace it with: curl -LsSf https://astral.sh/uv/install.sh | sh" \
  || fail "36 missing the plain sentence after a failed uv install: $OUT36B"
[ ! -e "$SB36B/.local/share/rook" ] || fail "36 installed something with the old uv"
SB36C="$(new_sandbox get-uv-xdg-bin)"
set +e
OUT36C="$(run_in_sb "$SB36C" env PATH="$UVI_BIN:$FAKE_BIN:$PATH" FAKE_UV_OLD=1 XDG_BIN_HOME="$SB36C/xbin" sh "$GET_SH" "$REPO_ROOT" \
  --agent claude --voice small --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1)"
RC36C=$?
set -e
[ "$RC36C" -eq 2 ] || fail "36 with XDG_BIN_HOME the install did not finish ($RC36C): $OUT36C"
printf '%s\n' "$OUT36C" | grep -qF "puts a newer uv in $SB36C/xbin, ahead of" || fail "36 named the wrong folder: $OUT36C"
printf '%s\n' "$OUT36C" | grep -qF "To use that uv yourself later, add $SB36C/xbin to your shell's PATH." || fail "36 no PATH note: $OUT36C"
pass "get.sh: an old uv was shadowed by uv's installer in its real folder, with no shell file changed, and the install went on; a failed replacement stopped with one plain sentence"

echo "=== Case 37: 'Sign in by hand' only for an agent that reports it is signed out ==="
SB37="$(new_sandbox sign-in-line)"
OUT37_OUT="$(run_in_sb "$SB37" bash "$INSTALL_SH" --dry-run --agent claude --voice-model no --recogniser no --service no 2>&1 || true)"
OUT37_IN="$(run_in_sb "$SB37" env FAKE_CLAUDE_SIGNED_IN=1 bash "$INSTALL_SH" --dry-run --agent claude --voice-model no --recogniser no --service no 2>&1 || true)"
printf '%s\n' "$OUT37_OUT" | grep -qF "Sign in by hand with: claude auth login" || fail "37 signed out, but no sign-in line: $OUT37_OUT"
printf '%s\n' "$OUT37_IN" | grep -qF ", and it is signed in." || fail "37 signed in, but not said: $OUT37_IN"
! printf '%s\n' "$OUT37_IN" | grep -qF "Sign in by hand" || fail "37 told a signed-in person to sign in by hand: $OUT37_IN"
OUT37_HANG="$(run_in_sb "$SB37" env FAKE_CLAUDE_HANGS=1 bash "$INSTALL_SH" --dry-run --agent claude --voice-model no --recogniser no --service no 2>&1 || true)"
printf '%s\n' "$OUT37_HANG" | grep -qF "I could not check the sign-in. If it is not signed in, run: claude auth login" \
  || fail "37 a status that hangs was not 'could not check': $OUT37_HANG"
! printf '%s\n' "$OUT37_HANG" | grep -qF "Sign in by hand" || fail "37 a hung status was told as signed out: $OUT37_HANG"
pass "Sign-in line: printed for a signed-out Claude Code only; a status that hangs is 'could not check'"

echo "=== Case 38: Mac: Rook.app goes to /Applications when writable, stays where it was recorded, and never replaces another ==="
SB38="$(new_sandbox mac-app-place)"
SYS38="$SB38/sysapps"  # Stands in for /Applications.
mkdir -p "$SYS38"
mac38() { mac_sb "$SB38" FAKE_CURL_OK=1 "$@" -- "$INSTALL_SH" --voice small --voice-model no --recogniser no --service yes \
  --recogniser-source "$FAKE_WHEEL"; }
set +e
mac38 ROOK_SYSTEM_APPS="$SYS38" >"$TEST_ROOT/out38.txt" 2>&1
RC38=$?
set -e
[ "$RC38" -eq 2 ] || fail "38 install failed ($RC38): $(cat "$TEST_ROOT/out38.txt")"
[ -x "$SYS38/Rook.app/Contents/MacOS/RookHelper" ] || fail "38 Rook.app did not go to the writable system folder"
[ ! -e "$SB38/Applications/Rook.app" ] || fail "38 Rook.app also went to ~/Applications"
grep -qF "$SYS38/Rook.app/Contents/MacOS/RookHelper" "$SB38/Library/LaunchAgents/com.rook.companion.plist" \
  || fail "38 the launchd agent does not run the app where it was put"
# The rerun names only mac_sb's empty scratch system folder, so only the recorded place can keep it there.
set +e
mac38 >"$TEST_ROOT/out38b.txt" 2>&1
RC38B=$?
set -e
[ "$RC38B" -eq 2 ] && grep -qF "OK: Built and signed $SYS38/Rook.app." "$TEST_ROOT/out38b.txt" \
  || fail "38 the rerun did not rebuild Rook.app where it was recorded ($RC38B): $(cat "$TEST_ROOT/out38b.txt")"
[ ! -e "$SB38/Applications/Rook.app" ] || fail "38 the rerun moved Rook.app to ~/Applications"
mac_sb "$SB38" ROOK_SYSTEM_APPS="$SYS38" -- "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$SYS38/Rook.app" ] || fail "38 uninstall left Rook.app in the system folder"
SB38C="$(new_sandbox mac-app-foreign)"
SYS38C="$SB38C/sysapps"
mkdir -p "$SYS38C/Rook.app"
echo "someone else's app" >"$SYS38C/Rook.app/notes.txt"
set +e
mac_sb "$SB38C" FAKE_CURL_OK=1 ROOK_SYSTEM_APPS="$SYS38C" -- "$INSTALL_SH" --voice small --voice-model no --recogniser no \
  --service yes --recogniser-source "$FAKE_WHEEL" >/dev/null 2>&1
RC38C=$?
set -e
[ "$RC38C" -eq 2 ] || fail "38 install beside a foreign Rook.app failed ($RC38C)"
[ "$(cat "$SYS38C/Rook.app/notes.txt")" = "someone else's app" ] && [ ! -e "$SYS38C/Rook.app/Contents" ] \
  || fail "38 a Rook.app that is not ours was changed"
[ -x "$SB38C/Applications/Rook.app/Contents/MacOS/RookHelper" ] || fail "38 Rook.app did not fall back to ~/Applications"
SB38D="$(new_sandbox mac-app-home-first)"
SYS38D="$SB38D/sysapps"
mkdir -p "$SYS38D" "$SB38D/Applications/Rook.app/Contents/MacOS"
echo "an earlier Rook.app, made before the manifest" >"$SB38D/Applications/Rook.app/notes.txt"
set +e
mac_sb "$SB38D" FAKE_CURL_OK=1 ROOK_SYSTEM_APPS="$SYS38D" -- "$INSTALL_SH" --voice small --voice-model no --recogniser no \
  --service yes --recogniser-source "$FAKE_WHEEL" >"$TEST_ROOT/out38d.txt" 2>&1
RC38D=$?
set -e
[ "$RC38D" -eq 2 ] || fail "38 install beside an earlier ~/Applications/Rook.app failed ($RC38D): $(cat "$TEST_ROOT/out38d.txt")"
[ ! -e "$SYS38D/Rook.app" ] || fail "38 a second Rook.app went to the system folder beside the one in ~/Applications"
grep -qF "Kept $SB38D/Applications/Rook.app as it is" "$TEST_ROOT/out38d.txt" || fail "38 the earlier app was not kept: $(cat "$TEST_ROOT/out38d.txt")"
pass "Mac Rook.app: the system folder when writable, the recorded place on reruns and at uninstall, an earlier ~/Applications app keeps the place, and another Rook.app left alone"

echo "=== Case 39: A run with no --voice (relay.py update) shows the saved voice, not the default small one ==="
SB39="$(new_sandbox voice-banner)"
mkdir -p "$SB39/.config/rook"
printf '%s\n' '{"voice_engine": "medium", "medium_voice_url": "http://127.0.0.1:8090"}' >"$SB39/.config/rook/settings.json"
OUT39="$(run_in_sb "$SB39" bash "$INSTALL_SH" --voice-model no --recogniser no --service no --recogniser-source "$FAKE_WHEEL" 2>&1 || true)"
printf '%s\n' "$OUT39" | grep -qF "  Voice:      medium (kept from your settings)" || fail "39 the banner did not show the saved voice: $OUT39"
printf '%s\n' "$OUT39" | grep -qF "voice_engine=medium," || fail "39 the settings line did not show the saved voice: $OUT39"
grep -qF '"voice_engine": "medium"' "$SB39/.config/rook/settings.json" || fail "39 the saved voice changed"
pass "Voice banner: a run with no --voice shows the saved medium voice, and keeps it"

echo "All install failure and recovery tests passed (39/39)."
