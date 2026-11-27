#!/usr/bin/env bash
# Adversarial and safety tests for install/uninstall.sh and install/install.sh.
# Runs strictly inside a fresh mktemp -d root with fake systemctl, uv, pacman, curl, sudo, loginctl on PATH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNINSTALL_SH="$SCRIPT_DIR/uninstall.sh"
INSTALL_SH="$SCRIPT_DIR/install.sh"

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
  TEST_ROOT="$(mktemp -d "$ROOK_INSTALL_TEST_ROOT/rook-uninstall-test-XXXXXX")"
else
  TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/rook-uninstall-test-XXXXXX")"
fi
trap 'rm -rf -- "$TEST_ROOT"' EXIT

FAKE_BIN="$TEST_ROOT/fake-bin"
mkdir -p "$FAKE_BIN"

cat >"$FAKE_BIN/systemctl" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "${FAKE_SYSTEMCTL_LOG:-/dev/null}"
exit 0
SH
chmod +x "$FAKE_BIN/systemctl"

cat >"$FAKE_BIN/pacman" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "-Q" ]; then
  exit 0
fi
echo "ERROR: unexpected pacman invocation: $*" >&2
exit 99
SH
chmod +x "$FAKE_BIN/pacman"

cat >"$FAKE_BIN/uv" <<'SH'
#!/usr/bin/env bash
echo "ERROR: unexpected uv invocation in test_uninstall.sh: $*" >&2
exit 99
SH
chmod +x "$FAKE_BIN/uv"

# Claude Code, signed out: the installer asks its status and must never reach the real one.
cat >"$FAKE_BIN/claude" <<'SH'
#!/usr/bin/env bash
case "$*" in
  "auth status") echo '{"loggedIn": false}' ;;
  *) echo "2.1.332 (fake Claude Code)" ;;
esac
SH
chmod +x "$FAKE_BIN/claude"

for forbidden in curl sudo loginctl; do
  cat >"$FAKE_BIN/$forbidden" <<SH
#!/usr/bin/env bash
echo "ERROR: $forbidden must never be called (\$*)" >&2
exit 99
SH
  chmod +x "$FAKE_BIN/$forbidden"
done

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
    "$@"
}

echo "=== Case 1: Hostile manifest with every bad entry kind ==="
SB1="$(new_sandbox hostile)"
DATA1="$SB1/.local/share/rook"
CFG1="$SB1/.config/rook"
SYS1="$SB1/.config/systemd/user"
mkdir -p "$DATA1" "$CFG1" "$SYS1" "$SB1/Documents/precious" "$SB1/escape-target"
echo "keep-precious" >"$SB1/Documents/precious/file.txt"
echo "keep-relative" >"$SB1/.local/share/work-note.txt"
echo '{"agent":"claude"}' >"$CFG1/settings.json"
echo "keep-escape" >"$SB1/escape-target/secret.txt"
echo "keep-space" >"$SB1/space file.txt"
ln -s "$SB1/escape-target" "$DATA1/sym-out"
ln -s "$CFG1/settings.json" "$SYS1/rook.service"
echo "foreign unit" >"$SYS1/rook-daily.service"

python3 - "$DATA1/install-manifest.json" "$SB1" "$DATA1" "$CFG1" "$SYS1" <<'PY'
import json, sys
from pathlib import Path
mpath, sb, data, cfg, sysd = sys.argv[1:6]
payload = {
    "version": 2,
    "entries": [
        {"path": f"{sb}/Documents/precious", "kind": "dir", "role": "prefix", "created": True},
        {"path": "../work-note.txt", "kind": "dir", "role": "prefix", "created": True},
        {"path": f"{data}/../work-note.txt", "kind": "dir", "role": "prefix", "created": True},
        {"path": sb, "kind": "dir", "role": "prefix", "created": True},
        {"path": "/", "kind": "dir", "role": "prefix", "created": True},
        {"path": data, "kind": "dir", "role": "prefix", "created": True},
        {"path": f"{data}/sym-out", "kind": "dir", "role": "prefix", "created": True},
        {"path": f"{cfg}/settings.json", "kind": "unit", "role": "systemd_unit", "created": True},
        {"path": f"{sysd}/rook.service", "kind": "unit", "role": "systemd_unit", "created": True},
        {"path": f"{sysd}/rook-daily.service", "kind": "unit", "role": "systemd_unit", "created": True},
        {"path": "", "kind": "dir", "role": "prefix", "created": True},
        {"path": f"{sb}/space file.txt\n{sb}/Documents/precious", "kind": "dir", "role": "prefix", "created": True},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY

set +e
OUT1_DRY="$(run_in_sb "$SB1" bash "$UNINSTALL_SH" --dry-run 2>&1)"
RC1_DRY=$?
OUT1_RUN="$(run_in_sb "$SB1" bash "$UNINSTALL_SH" --yes 2>&1)"
RC1_RUN=$?
set -e

[ "$RC1_DRY" -ne 0 ] || fail "Hostile manifest --dry-run should exit non-zero"
[ "$RC1_RUN" -ne 0 ] || fail "Hostile manifest --yes should exit non-zero"
[ -f "$SB1/Documents/precious/file.txt" ] || fail "User Documents/precious was deleted!"
[ -f "$SB1/.local/share/work-note.txt" ] || fail "Relative work-note.txt was deleted!"
[ -f "$CFG1/settings.json" ] || fail "settings.json listed as unit was deleted!"
[ -f "$SB1/escape-target/secret.txt" ] || fail "Symlink escape target was deleted!"
[ -L "$DATA1/sym-out" ] || fail "Symlink dir entry should have been skipped, not followed!"
[ -f "$SYS1/rook-daily.service" ] || fail "Unmarked foreign unit was deleted!"
[ -f "$SB1/space file.txt" ] || fail "Path with space/newline victim was deleted!"
[ -f "$DATA1/install-manifest.json" ] || fail "Manifest was deleted even though entries were skipped!"
pass "Hostile manifest: exited non-zero, kept manifest, and every victim file survived"

echo "=== Case 2: Missing manifest removes nothing and exits 0 (idempotent) ==="
SB2="$(new_sandbox nomanifest)"
DATA2="$SB2/.local/share/rook"
mkdir -p "$DATA2/live" "$SB2/.config/rook"
echo "live-checkout" >"$DATA2/live/README.md"
echo '{"agent":"claude"}' >"$SB2/.config/rook/settings.json"
OUT2="$(run_in_sb "$SB2" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -f "$DATA2/live/README.md" ] || fail "Live checkout deleted with no manifest!"
[ -f "$SB2/.config/rook/settings.json" ] || fail "settings.json deleted with no manifest!"
printf '%s\n' "$OUT2" | grep -q "No install manifest found" || fail "Missing manifest did not explain why nothing was removed"
pass "Missing manifest: removed nothing, explained clearly, and exited 0"

echo "=== Case 3: Existing install kept by installer is never deleted and manifest retains kept record ==="
SB3="$(new_sandbox kept)"
DATA3="$SB3/.local/share/rook"
mkdir -p "$DATA3/live" "$DATA3/venv"
echo "owner-live-checkout" >"$DATA3/live/keep.txt"
python3 - "$DATA3/install-manifest.json" "$DATA3" <<'PY'
import json, sys
from pathlib import Path
mpath, data = sys.argv[1:3]
payload = {
    "version": 2,
    "entries": [
        {"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True, "installed_files": []},
    ],
    "kept": [
        {"path": f"{data}/live", "role": "prefix", "reason": "existing install kept unchanged"},
    ],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT3="$(run_in_sb "$SB3" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -f "$DATA3/live/keep.txt" ] || fail "Kept existing install was deleted!"
[ ! -e "$DATA3/venv" ] || fail "Installer-created venv should have been removed"
[ -f "$DATA3/install-manifest.json" ] || fail "Manifest should be kept with remaining kept items!"
python3 - "$DATA3/install-manifest.json" "$DATA3/live" <<'PY'
import json, sys
data = json.loads(open(sys.argv[1]).read())
assert data["entries"] == [], f"expected empty entries, got {data['entries']}"
assert len(data["kept"]) == 1 and data["kept"][0]["path"] == sys.argv[2], f"unexpected kept: {data['kept']}"
PY
printf '%s\n' "$OUT3" | grep -q "existing install kept unchanged" || fail "Plan did not mention kept install"
pass "Kept existing install survived, venv removed, and manifest updated with kept record"

echo "=== Case 4: Installed checkout with user-added file is kept and manifest retains it ==="
SB4="$(new_sandbox userfiles)"
DATA4="$SB4/.local/share/rook"
mkdir -p "$DATA4/venv"
git clone -q "$REPO_ROOT" "$DATA4/live"
CLONE_SHA4="$(git -C "$DATA4/live" rev-parse HEAD)"
CLONE_BR4="$(git -C "$DATA4/live" rev-parse --abbrev-ref HEAD)"
echo "my notes" >"$DATA4/live/my-personal-note.txt"
python3 - "$DATA4/install-manifest.json" "$DATA4" "$CLONE_SHA4" "$CLONE_BR4" <<'PY'
import json, sys
from pathlib import Path
mpath, data, sha, br = sys.argv[1:5]
payload = {
    "version": 2,
    "entries": [
        {"path": f"{data}/live", "kind": "dir", "role": "prefix", "created": True, "commit": sha, "branch": br},
        {"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True, "installed_files": []},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT4_DRY="$(run_in_sb "$SB4" bash "$UNINSTALL_SH" --dry-run 2>&1)"
printf '%s\n' "$OUT4_DRY" | grep -q "my-personal-note.txt" || fail "Dry-run plan did not report user file in prefix"
OUT4="$(run_in_sb "$SB4" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -f "$DATA4/live/my-personal-note.txt" ] || fail "User file inside installed folder was deleted!"
[ ! -e "$DATA4/venv" ] || fail "Clean installer venv should still be removed"
[ -f "$DATA4/install-manifest.json" ] || fail "Manifest was deleted even though live was kept!"
# Once user removes their personal note, a second uninstall removes live AND the manifest cleanly.
rm -f "$DATA4/live/my-personal-note.txt"
run_in_sb "$SB4" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$DATA4/live" ] && [ ! -e "$DATA4/install-manifest.json" ] || fail "Second uninstall after cleanup failed to remove live and manifest"
pass "Dirty checkout kept with manifest preserved; second uninstall after cleanup removed both"

echo "=== Case 5: Dry-run writes nothing (no shader cache, no pulse cookie) and never says complete ==="
SB5="$(new_sandbox dryrun)"
OUT5="$(run_in_sb "$SB5" bash "$INSTALL_SH" --dry-run --service no --voice-model yes --recogniser yes --recogniser-source https://example.invalid/airtype.git 2>&1)"
if printf '%s\n' "$OUT5" | grep -q "Rook install complete"; then
  fail "--dry-run printed 'Rook install complete'"
fi
printf '%s\n' "$OUT5" | grep -q "Dry run finished. Nothing was changed." || fail "--dry-run missing clear finish line"
LEFTOVER="$(find "$SB5" -mindepth 1 ! -path "$SB5/.config" ! -path "$SB5/.local" ! -path "$SB5/.local/share" ! -path "$SB5/.cache" ! -path "$SB5/.local/state" ! -path "$SB5/run")"
[ -z "$LEFTOVER" ] || fail "--dry-run wrote unexpected files:\n$LEFTOVER"
pass "--dry-run wrote zero files and did not print complete"

echo "=== Case 6: Unparseable settings.json is never overwritten and non-TTY refuses to guess ==="
SB6="$(new_sandbox badsettings)"
mkdir -p "$SB6/.config/rook"
printf '{broken json\n' >"$SB6/.config/rook/settings.json"
chmod 0640 "$SB6/.config/rook/settings.json"
if run_in_sb "$SB6" bash "$INSTALL_SH" --agent claude --voice small --recogniser-source https://example.invalid/airtype.git </dev/null >/dev/null 2>&1; then
  fail "Non-TTY install without model/service flags should refuse to guess"
fi
[ "$(cat "$SB6/.config/rook/settings.json")" = "{broken json" ] || fail "Bad settings.json was modified"
pass "Non-TTY install refuses to guess and broken settings.json stays untouched"

echo "=== Case 7: Clean uninstall matches dry-run, second uninstall exits 0, --purge removes config/state ==="
SB7="$(new_sandbox clean)"
DATA7="$SB7/.local/share/rook"
CFG7="$SB7/.config/rook"
STATE7="$SB7/.local/state/rook"
SYS7="$SB7/.config/systemd/user"
mkdir -p "$DATA7/venv" "$DATA7/voice-phonon" "$CFG7" "$STATE7" "$SYS7"
git clone -q "$REPO_ROOT" "$DATA7/live"
mkdir -p "$DATA7/live/desktop/__pycache__"
printf 'bytecode' >"$DATA7/live/desktop/__pycache__/rook.cpython-312.pyc"
CLONE_SHA7="$(git -C "$DATA7/live" rev-parse HEAD)"
CLONE_BR7="$(git -C "$DATA7/live" rev-parse --abbrev-ref HEAD)"
echo '{"agent":"claude"}' >"$CFG7/settings.json"
echo "memory" >"$STATE7/turns.jsonl"
printf '# Managed by Rook install/install.sh\n[Unit]\nDescription=Rook\n' >"$SYS7/rook.service"
python3 - "$DATA7/install-manifest.json" "$DATA7" "$SYS7" "$CLONE_SHA7" "$CLONE_BR7" <<'PY'
import hashlib, json, sys
from pathlib import Path
mpath, data, sysd, sha, br = sys.argv[1:6]
unit_sha = hashlib.sha256((Path(sysd) / "rook.service").read_bytes()).hexdigest()
payload = {
    "version": 2,
    "created_config_dir": True,
    "created_state_dir": True,
    "entries": [
        {"path": f"{data}/live", "kind": "dir", "role": "prefix", "created": True, "commit": sha, "branch": br},
        {"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True, "installed_files": []},
        {"path": f"{data}/voice-phonon", "kind": "dir", "role": "voice_venv", "created": True, "installed_files": []},
        {"path": f"{sysd}/rook.service", "kind": "unit", "role": "systemd_unit", "created": True, "sha256": unit_sha},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
DRY7="$(run_in_sb "$SB7" bash "$UNINSTALL_SH" --dry-run 2>&1)"
[ -d "$DATA7/live" ] && [ -f "$SYS7/rook.service" ] || fail "Dry-run removed files"
REAL7="$(run_in_sb "$SB7" bash "$UNINSTALL_SH" --yes 2>&1)"
[ ! -e "$DATA7/live" ] && [ ! -e "$DATA7/venv" ] && [ ! -e "$DATA7/voice-phonon" ] && [ ! -e "$SYS7/rook.service" ] || fail "Clean uninstall missed an entry"
[ ! -e "$DATA7/install-manifest.json" ] || fail "Clean uninstall should remove manifest when nothing remains"
[ -f "$CFG7/settings.json" ] && [ -f "$STATE7/turns.jsonl" ] || fail "Default uninstall deleted config or state"
diff -u <(printf '%s\n' "$DRY7" | sed '/^Dry run finished/d') <(printf '%s\n' "$REAL7" | sed '/^Proceed with/,$d') >/dev/null || fail "Dry-run plan differed from real uninstall plan"
SECOND7="$(run_in_sb "$SB7" bash "$UNINSTALL_SH" --yes 2>&1)"
printf '%s\n' "$SECOND7" | grep -q "Nothing to remove" || fail "Second uninstall did not report nothing to remove"
mkdir -p "$DATA7"
printf '{"version":2,"created_config_dir":true,"created_state_dir":true,"entries":[],"kept":[]}\n' >"$DATA7/install-manifest.json"
run_in_sb "$SB7" bash "$UNINSTALL_SH" --purge --yes >/dev/null
[ ! -e "$CFG7" ] && [ ! -e "$STATE7" ] && [ ! -e "$DATA7" ] || fail "--purge left config/state/data behind"
pass "Clean uninstall matches dry-run, second uninstall exits 0, and --purge removes installer-created config/state"

echo "=== Case 8: Checkout with local commit, ignored file, extra branch, or stash is kept ==="
for mode in commit ignored branch stash; do
  SB8="$(new_sandbox "git-$mode")"
  DATA8="$SB8/.local/share/rook"
  mkdir -p "$DATA8"
  git clone -q "$REPO_ROOT" "$DATA8/live"
  SHA8="$(git -C "$DATA8/live" rev-parse HEAD)"
  BR8="$(git -C "$DATA8/live" rev-parse --abbrev-ref HEAD)"
  case "$mode" in
    commit)
      echo "my local work" >"$DATA8/live/local-work.txt"
      git -C "$DATA8/live" add local-work.txt
      git -C "$DATA8/live" -c user.name=Test -c user.email=test@example.com commit -q -m "Local commit"
      ;;
    ignored)
      printf 'secret.env\n' >>"$DATA8/live/.git/info/exclude"
      echo "API_KEY=keepme" >"$DATA8/live/secret.env"
      ;;
    branch)
      git -C "$DATA8/live" branch my-side-branch
      ;;
    stash)
      echo "# temp change" >>"$DATA8/live/README.md"
      git -C "$DATA8/live" -c user.name=Test -c user.email=test@example.com stash push -q -m "my stash"
      ;;
  esac
  python3 - "$DATA8/install-manifest.json" "$DATA8" "$SHA8" "$BR8" <<'PY'
import json, sys
from pathlib import Path
mpath, data, sha, br = sys.argv[1:5]
payload = {
    "version": 2,
    "entries": [{"path": f"{data}/live", "kind": "dir", "role": "prefix", "created": True, "commit": sha, "branch": br}],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
  OUT8="$(run_in_sb "$SB8" bash "$UNINSTALL_SH" --yes 2>&1)"
  [ -d "$DATA8/live" ] || fail "Checkout with $mode was deleted!"
  [ -f "$DATA8/install-manifest.json" ] || fail "Manifest was deleted when checkout ($mode) was kept!"
  if [ "$mode" = "ignored" ]; then
    [ -f "$DATA8/live/secret.env" ] || fail "Ignored secret.env was deleted!"
  fi
done
pass "Checkouts with local commit, ignored secret.env, extra branch, or stash were all kept"

echo "=== Case 9 (Review 65 #4d): User symlink roots (~/.config/rook and ~/.local/share/rook) are left untouched ==="
SB9="$(new_sandbox symlinks)"
DOTFILES9="$SB9/dotfiles/rook-config"
EXTDATA9="$SB9/external/rook-data"
mkdir -p "$DOTFILES9" "$EXTDATA9/venv" "$SB9/.local/state/rook"
echo '{"agent":"claude"}' >"$DOTFILES9/settings.json"
echo "precious-dotfile" >"$DOTFILES9/keep.txt"
ln -s "$DOTFILES9" "$SB9/.config/rook"
ln -s "$EXTDATA9" "$SB9/.local/share/rook"
python3 - "$EXTDATA9/install-manifest.json" "$SB9/.local/share/rook" <<'PY'
import json, sys
from pathlib import Path
mpath, data = sys.argv[1:3]
payload = {
    "version": 2,
    "created_config_dir": False,
    "created_state_dir": True,
    "entries": [{"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True, "installed_files": []}],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT9="$(run_in_sb "$SB9" bash "$UNINSTALL_SH" --purge --yes 2>&1)"
[ -L "$SB9/.config/rook" ] || fail "User config symlink was unlinked by --purge!"
[ -f "$DOTFILES9/keep.txt" ] && [ -f "$DOTFILES9/settings.json" ] || fail "--purge deleted through config symlink into dotfiles!"
[ -L "$SB9/.local/share/rook" ] || fail "User data symlink was unlinked!"
[ -d "$EXTDATA9" ] && [ ! -e "$EXTDATA9/venv" ] || fail "Venv should be removed while data symlink target stays!"
[ ! -e "$SB9/.local/state/rook" ] || fail "Installer-created state dir should be removed on --purge"
pass "User symlink roots were left untouched (never unlinked or target-deleted) even with --purge"

echo "=== Case 10: User-added file inside an installer-created venv is kept with warning ==="
SB10="$(new_sandbox venvuser)"
DATA10="$SB10/.local/share/rook"
mkdir -p "$DATA10/venv/bin"
echo "#!/bin/sh" >"$DATA10/venv/bin/python"
echo "personal tool" >"$DATA10/venv/bin/my-personal-tool"
python3 - "$DATA10/install-manifest.json" "$DATA10" <<'PY'
import json, sys
from pathlib import Path
mpath, data = sys.argv[1:3]
payload = {
    "version": 2,
    "entries": [
        {"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True, "installed_files": ["bin/python"]},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT10="$(run_in_sb "$SB10" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -f "$DATA10/venv/bin/my-personal-tool" ] || fail "User-added file inside venv was deleted!"
[ -f "$DATA10/install-manifest.json" ] || fail "Manifest was deleted even though venv was kept!"
printf '%s\n' "$OUT10" | grep -q "my-personal-tool" || fail "Uninstall did not name the user-added venv file"
pass "Venv with user-added file was kept with warning and manifest retained"

echo "=== Case 11: Relative XDG roots are refused by both install.sh and uninstall.sh ==="
SB11="$(new_sandbox relative)"
if env PATH="$FAKE_BIN:$PATH" HOME="$SB11" XDG_DATA_HOME="relative/data" bash "$UNINSTALL_SH" --dry-run >/dev/null 2>&1; then
  fail "uninstall.sh accepted relative XDG_DATA_HOME"
fi
if env PATH="$FAKE_BIN:$PATH" HOME="$SB11" XDG_DATA_HOME="relative/data" bash "$INSTALL_SH" --dry-run --service no --voice-model no --recogniser no --recogniser-source https://example.invalid/airtype.git >/dev/null 2>&1; then
  fail "install.sh accepted relative XDG_DATA_HOME"
fi
if run_in_sb "$SB11" bash "$INSTALL_SH" --dry-run --prefix "relative/prefix" --service no --voice-model no --recogniser no --recogniser-source https://example.invalid/airtype.git >/dev/null 2>&1; then
  fail "install.sh accepted relative --prefix"
fi
pass "Relative XDG roots and relative --prefix were refused"

echo "=== Case 12 (Review 58 #3 + Review 65 #2): Uninstall never stops or disables a modified or unowned unit ==="
SB12="$(new_sandbox unowned-unit)"
DATA12="$SB12/.local/share/rook"
SYS12="$SB12/.config/systemd/user"
mkdir -p "$DATA12" "$SYS12"
printf '[Unit]\nDescription=My custom rook service\n[Service]\nExecStart=/usr/bin/true\n' >"$SYS12/rook.service"
printf '# Managed by Rook install/install.sh\n[Unit]\nDescription=Daily timer\n[Timer]\nOnCalendar=04:30\n' >"$SYS12/rook-daily.timer"
python3 - "$DATA12/install-manifest.json" "$SYS12" <<'PY'
import hashlib, json, sys
from pathlib import Path
mpath, sysd = sys.argv[1:3]
timer_sha = hashlib.sha256((Path(sysd) / "rook-daily.timer").read_bytes()).hexdigest()
payload = {
    "version": 2,
    "entries": [
        {"path": f"{sysd}/rook.service", "kind": "unit", "role": "systemd_unit", "created": True, "sha256": "0" * 64},
        {"path": f"{sysd}/rook-daily.timer", "kind": "unit", "role": "systemd_unit", "created": True, "sha256": timer_sha},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
: >"$TEST_ROOT/systemctl.log"
OUT12="$(run_in_sb "$SB12" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -f "$SYS12/rook.service" ] || fail "User-owned/modified rook.service file was deleted!"
[ ! -e "$SYS12/rook-daily.timer" ] || fail "Installer-owned rook-daily.timer should have been removed"
grep -q "disable --now rook-daily.timer" "$TEST_ROOT/systemctl.log" || fail "Owned rook-daily.timer was not disabled"
if grep -q "rook.service" "$TEST_ROOT/systemctl.log"; then
  fail "Uninstall called systemctl on unowned/modified rook.service! Log: $(cat "$TEST_ROOT/systemctl.log")"
fi
[ -f "$DATA12/install-manifest.json" ] || fail "Manifest was deleted despite kept unit"
pass "Unowned/modified rook.service was neither deleted nor stopped/disabled by systemctl"

echo "=== Case 13 (Review 58 #4): Detached-HEAD commit left behind and linked worktree commit are both kept ==="
# 13a. Detached HEAD commit, then returned to original branch (commit lives only in reflog).
SB13A="$(new_sandbox git-detached)"
DATA13A="$SB13A/.local/share/rook"
mkdir -p "$DATA13A"
git clone -q "$REPO_ROOT" "$DATA13A/live"
SHA13A="$(git -C "$DATA13A/live" rev-parse HEAD)"
BR13A="$(git -C "$DATA13A/live" rev-parse --abbrev-ref HEAD)"
git -C "$DATA13A/live" checkout -q --detach
echo "detached work" >"$DATA13A/live/detached.txt"
git -C "$DATA13A/live" add detached.txt
git -C "$DATA13A/live" -c user.name=Test -c user.email=test@example.com commit -q -m "Detached commit"
DETACHED_SHA="$(git -C "$DATA13A/live" rev-parse HEAD)"
git -C "$DATA13A/live" checkout -q "$BR13A"
python3 - "$DATA13A/install-manifest.json" "$DATA13A" "$SHA13A" "$BR13A" <<'PY'
import json, sys
from pathlib import Path
mpath, data, sha, br = sys.argv[1:5]
payload = {
    "version": 2,
    "entries": [{"path": f"{data}/live", "kind": "dir", "role": "prefix", "created": True, "commit": sha, "branch": br}],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT13A="$(run_in_sb "$SB13A" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -d "$DATA13A/live" ] || fail "Checkout with detached-HEAD commit in reflog was deleted!"
git -C "$DATA13A/live" cat-file -e "$DETACHED_SHA^{commit}" || fail "Detached commit object was lost!"
printf '%s\n' "$OUT13A" | grep -qi "remote-tracking" || fail "Output did not explain unreachable-from-remote commit"

# 13b. Linked worktree created with --detach and a commit made inside it.
SB13B="$(new_sandbox git-worktree)"
DATA13B="$SB13B/.local/share/rook"
mkdir -p "$DATA13B"
git clone -q "$REPO_ROOT" "$DATA13B/live"
SHA13B="$(git -C "$DATA13B/live" rev-parse HEAD)"
BR13B="$(git -C "$DATA13B/live" rev-parse --abbrev-ref HEAD)"
git -C "$DATA13B/live" worktree add -q --detach "$SB13B/my-wt"
echo "worktree work" >"$SB13B/my-wt/wt.txt"
git -C "$SB13B/my-wt" add wt.txt
git -C "$SB13B/my-wt" -c user.name=Test -c user.email=test@example.com commit -q -m "Worktree detached commit"
python3 - "$DATA13B/install-manifest.json" "$DATA13B" "$SHA13B" "$BR13B" <<'PY'
import json, sys
from pathlib import Path
mpath, data, sha, br = sys.argv[1:5]
payload = {
    "version": 2,
    "entries": [{"path": f"{data}/live", "kind": "dir", "role": "prefix", "created": True, "commit": sha, "branch": br}],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT13B="$(run_in_sb "$SB13B" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -d "$DATA13B/live" ] || fail "Checkout with linked worktree was deleted!"
git -C "$SB13B/my-wt" status --porcelain >/dev/null || fail "Linked worktree broke after uninstall!"
printf '%s\n' "$OUT13B" | grep -qi "worktree" || fail "Output did not explain linked worktree reason"
pass "Checkouts with detached-HEAD reflog commit or linked worktree were both kept"

echo "=== Case 14 (Review 58 #5c): Manifest targeting lib/-only folder without valid record is rejected ==="
SB14="$(new_sandbox libonly)"
DATA14="$SB14/.local/share/rook"
mkdir -p "$DATA14/my-lib-proj/lib" "$DATA14/venv/lib"
echo "precious-a" >"$DATA14/my-lib-proj/lib/precious.py"
echo "precious-b" >"$DATA14/venv/lib/precious.py"
python3 - "$DATA14/install-manifest.json" "$DATA14" <<'PY'
import json, sys
from pathlib import Path
mpath, data = sys.argv[1:3]
payload = {
    "version": 2,
    "entries": [
        {"path": f"{data}/my-lib-proj", "kind": "dir", "role": "rook_venv", "created": True},
        {"path": f"{data}/my-lib-proj", "kind": "dir", "role": "rook_venv", "created": True, "installed_files": ["lib/precious.py"]},
        {"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True},
        {"path": f"{data}/my-lib-proj", "kind": "dir", "role": "prefix", "created": True, "commit": "a" * 40, "branch": "main"},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
set +e
OUT14="$(run_in_sb "$SB14" bash "$UNINSTALL_SH" --yes 2>&1)"
RC14=$?
set -e
[ "$RC14" -ne 0 ] || fail "Invalid lib/-only manifest entries should exit non-zero"
[ -f "$DATA14/my-lib-proj/lib/precious.py" ] || fail "User lib/-only folder my-lib-proj was deleted!"
[ -f "$DATA14/venv/lib/precious.py" ] || fail "venv without recorded installed_files was deleted!"
[ -f "$DATA14/install-manifest.json" ] || fail "Manifest was deleted despite skipped entries"
pass "Hostile manifest targeting lib/-only folders was rejected with all files intact"

echo "=== Case 15 (Review 65 #3): Checkout with custom .git/hooks file is kept (while .sample hooks allow removal) ==="
SB15="$(new_sandbox git-hook)"
DATA15="$SB15/.local/share/rook"
mkdir -p "$DATA15"
git clone -q "$REPO_ROOT" "$DATA15/live"
SHA15="$(git -C "$DATA15/live" rev-parse HEAD)"
BR15="$(git -C "$DATA15/live" rev-parse --abbrev-ref HEAD)"
printf '#!/bin/sh\necho custom hook\n' >"$DATA15/live/.git/hooks/pre-commit"
chmod +x "$DATA15/live/.git/hooks/pre-commit"
python3 - "$DATA15/install-manifest.json" "$DATA15" "$SHA15" "$BR15" <<'PY'
import json, sys
from pathlib import Path
mpath, data, sha, br = sys.argv[1:5]
payload = {
    "version": 2,
    "entries": [{"path": f"{data}/live", "kind": "dir", "role": "prefix", "created": True, "commit": sha, "branch": br}],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT15="$(run_in_sb "$SB15" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -f "$DATA15/live/.git/hooks/pre-commit" ] || fail "Checkout with custom git hook was deleted!"
printf '%s\n' "$OUT15" | grep -q "custom git hooks" || fail "Output did not explain custom git hooks"
rm -f "$DATA15/live/.git/hooks/pre-commit"
run_in_sb "$SB15" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$DATA15/live" ] || fail "Clean checkout with only .sample hooks should be removed"
pass "Checkout with custom .git/hooks/pre-commit was kept; clean checkout removed once hook removed"

echo "=== Case 16 (Review 65 #4c): XDG_CONFIG_HOME=\$HOME with pre-existing \$HOME/rook survives --purge ==="
SB16="$(new_sandbox xdg-home-purge)"
DATA16="$SB16/.local/share/rook"
mkdir -p "$SB16/rook" "$DATA16/venv"
echo "my-preexisting-home-rook-file" >"$SB16/rook/precious.txt"
python3 - "$DATA16/install-manifest.json" "$DATA16" <<'PY'
import json, sys
from pathlib import Path
mpath, data = sys.argv[1:3]
payload = {
    "version": 2,
    "created_config_dir": False,
    "created_state_dir": False,
    "entries": [{"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True, "installed_files": []}],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT16="$(env PATH="$FAKE_BIN:$PATH" HOME="$SB16" XDG_CONFIG_HOME="$SB16" XDG_DATA_HOME="$SB16/.local/share" XDG_CACHE_HOME="$SB16/.cache" XDG_STATE_HOME="$SB16/.local/state" XDG_RUNTIME_DIR="$SB16/run" bash "$UNINSTALL_SH" --purge --yes 2>&1)"
[ -f "$SB16/rook/precious.txt" ] || fail "--purge deleted pre-existing \$HOME/rook when XDG_CONFIG_HOME=\$HOME!"
[ ! -e "$DATA16/venv" ] || fail "Installer-created venv should still be removed"
printf '%s\n' "$OUT16" | grep -q "pre-existing config folder not created by installer" || fail "Plan did not explain why \$HOME/rook was kept"
pass "Pre-existing \$HOME/rook survived --purge when XDG_CONFIG_HOME=\$HOME"

echo "=== Case 17 (Review 65 #4e): Source checkout on detached HEAD keeps live and clearly explains why ==="
SB17="$(new_sandbox detached-source)"
SRC17="$TEST_ROOT/src-detached"
rm -rf -- "$SRC17"
git clone -q "$REPO_ROOT" "$SRC17"
git -C "$SRC17" checkout -q --detach HEAD
echo "detached-source-tip" >"$SRC17/detached-tip.txt"
git -C "$SRC17" add detached-tip.txt
git -C "$SRC17" -c user.name=Test -c user.email=test@example.com commit -q -m "Detached source commit"
DATA17="$SB17/.local/share/rook"
mkdir -p "$DATA17/venv"
git clone -q "$SRC17" "$DATA17/live" 2>/dev/null
SHA17="$(git -C "$DATA17/live" rev-parse HEAD)"
BR17="$(git -C "$DATA17/live" rev-parse --abbrev-ref HEAD)"
python3 - "$DATA17/install-manifest.json" "$DATA17" "$SHA17" "$BR17" <<'PY'
import json, sys
from pathlib import Path
mpath, data, sha, br = sys.argv[1:5]
payload = {
    "version": 2,
    "entries": [
        {"path": f"{data}/live", "kind": "dir", "role": "prefix", "created": True, "commit": sha, "branch": br},
        {"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True, "installed_files": []},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT17="$(run_in_sb "$SB17" bash "$UNINSTALL_SH" --yes 2>&1)"
[ -d "$DATA17/live" ] || fail "Detached-source checkout should be kept"
printf '%s\n' "$OUT17" | grep -q "installed from a detached HEAD" || fail "Output did not explain detached HEAD source reason: $OUT17"
printf '%s\n' "$OUT17" | grep -q "tracked item(s) were kept" || fail "Output did not clearly report kept items on exit: $OUT17"
pass "Detached-HEAD source checkout was kept with clear explanation of why"

echo "=== Case 18 (Review 68 #3a): Non-UTF-8 filename in venv prints escaped plan without traceback and stays kept ==="
SB18="$(new_sandbox non-utf8)"
DATA18="$SB18/.local/share/rook"
mkdir -p "$DATA18/venv/bin"
printf '#!/bin/sh\n' >"$DATA18/venv/bin/python"
python3 - "$DATA18/venv" "$DATA18/install-manifest.json" <<'PY'
import json, os, sys
from pathlib import Path
venv_dir, mpath = sys.argv[1:3]
bad_path = os.path.join(os.fsencode(venv_dir), b"bad-\xff-notes.txt")
with open(bad_path, "wb") as f:
    f.write(b"non-utf8-precious\n")
payload = {
    "version": 2,
    "entries": [
        {"path": venv_dir, "kind": "dir", "role": "rook_venv", "created": True,
         "installed_files": ["bin/python"], "installed_dirs": ["bin"]},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
OUT18_DRY="$(run_in_sb "$SB18" bash "$UNINSTALL_SH" --dry-run 2>&1)"
! printf '%s\n' "$OUT18_DRY" | grep -q "Traceback" || fail "18 --dry-run crashed with traceback: $OUT18_DRY"
printf '%s\n' "$OUT18_DRY" | grep -qF '\xff' || fail "18 --dry-run did not escape non-UTF-8 byte: $OUT18_DRY"
OUT18_YES="$(run_in_sb "$SB18" bash "$UNINSTALL_SH" --yes 2>&1)"
! printf '%s\n' "$OUT18_YES" | grep -q "Traceback" || fail "18 --yes crashed with traceback: $OUT18_YES"
python3 - "$DATA18/venv" <<'PY'
import os, sys
bad_path = os.path.join(os.fsencode(sys.argv[1]), b"bad-\xff-notes.txt")
assert os.path.isfile(bad_path) and open(bad_path, "rb").read() == b"non-utf8-precious\n", "non-UTF-8 file lost!"
PY
pass "Non-UTF-8 filename in venv printed safely with backslash escape, no traceback, and file survived"

echo "=== Case 19 (Review 68 #3b): Person's file inside __pycache__ survives in both venv and checkout ==="
SB19="$(new_sandbox pycache-user-file)"
DATA19="$SB19/.local/share/rook"
mkdir -p "$DATA19/venv/lib/__pycache__"
git clone -q "$REPO_ROOT" "$DATA19/live"
SHA19="$(git -C "$DATA19/live" rev-parse HEAD)"
BR19="$(git -C "$DATA19/live" rev-parse --abbrev-ref HEAD)"
mkdir -p "$DATA19/live/desktop/__pycache__"
printf 'pyc-bytes' >"$DATA19/venv/lib/__pycache__/mod.cpython-312.pyc"
printf 'keep-venv-pycache-note\n' >"$DATA19/venv/lib/__pycache__/notes.txt"
printf 'pyc-bytes' >"$DATA19/live/desktop/__pycache__/rook.cpython-312.pyc"
printf 'keep-live-pycache-note\n' >"$DATA19/live/desktop/__pycache__/notes.txt"
python3 - "$DATA19/install-manifest.json" "$DATA19" "$SHA19" "$BR19" <<'PY'
import json, sys
from pathlib import Path
mpath, data, sha, br = sys.argv[1:5]
payload = {
    "version": 2,
    "entries": [
        {"path": f"{data}/live", "kind": "dir", "role": "prefix", "created": True, "commit": sha, "branch": br},
        {"path": f"{data}/venv", "kind": "dir", "role": "rook_venv", "created": True,
         "installed_files": [], "installed_dirs": ["lib"]},
    ],
    "kept": [],
}
Path(mpath).write_text(json.dumps(payload, indent=2) + "\n")
PY
run_in_sb "$SB19" bash "$UNINSTALL_SH" --yes >/dev/null
[ -f "$DATA19/venv/lib/__pycache__/notes.txt" ] || fail "19 user file inside venv __pycache__ was DELETED!"
[ -f "$DATA19/live/desktop/__pycache__/notes.txt" ] || fail "19 user file inside checkout __pycache__ was DELETED!"
# Once user removes their own notes.txt (leaving only *.pyc inside __pycache__), uninstall removes both cleanly.
rm -f "$DATA19/venv/lib/__pycache__/notes.txt" "$DATA19/live/desktop/__pycache__/notes.txt"
run_in_sb "$SB19" bash "$UNINSTALL_SH" --yes >/dev/null
[ ! -e "$DATA19/venv" ] && [ ! -e "$DATA19/live" ] || fail "19 clean venv/checkout with only *.pyc in __pycache__ should be removed"
pass "User files inside __pycache__ survived in both venv and checkout; *.pyc-only __pycache__ removed cleanly"

echo "All uninstall and safety tests passed (19/19)."
