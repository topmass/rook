#!/bin/sh
# Install Rook with one command:
#   curl -fsSL <url of this file> | sh
#   curl -fsSL <url of this file> | sh -s -- SOURCE [install.sh options]
# SOURCE is a git URL, a local Rook checkout, or a .tar.gz URL. Without it, ROOK_PUBLIC_SOURCE is used.
# This script only gets uv and the code. install/install.sh does the real work, with these defaults:
# the agent found on PATH, both speech models, and the login service. The voice is the medium voice when
# install/medium-voice.sh --check passes (an NVIDIA card it can run on), and the small voice otherwise.
# Any install.sh option after SOURCE overrides a default, for example --agent codex or --dry-run.
set -eu

# Rook's public repository.
ROOK_PUBLIC_SOURCE="https://github.com/topmass/rook.git"

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
# bounded SECONDS OUT COMMAND...: run COMMAND with no input and its output in OUT, for at most SECONDS, so a tool that
# hangs or prompts cannot hang the install. Its exit code, or 124 at the limit. The Mac has no timeout command.
bounded() {
  limit=$(( $1 * 10 )) out=$2
  shift 2
  "$@" </dev/null >"$out" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$limit" -le 0 ]; then
      kill "$pid" 2>/dev/null
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    sleep 0.1
    limit=$((limit - 1))
  done
  wait "$pid"
}

# Whether the uv on PATH knows Python $1 (installed, or a download it can fetch).
uv_knows() {
  bounded 30 "$work/uv-python.txt" uv python list "$1" && grep -q "^cpython-$1-" "$work/uv-python.txt"
}

# The setting, if any, that stops uv from fetching a Python (then any uv looks too old): printed as written.
uv_download_blocker() {
  case "${UV_PYTHON_DOWNLOADS:-}" in never|manual) echo "UV_PYTHON_DOWNLOADS=$UV_PYTHON_DOWNLOADS"; return 0 ;; esac
  [ "${UV_PYTHON_PREFERENCE:-}" != only-system ] || { echo "UV_PYTHON_PREFERENCE=only-system"; return 0; }
  for f in "${XDG_CONFIG_HOME:-$HOME/.config}/uv/uv.toml" /etc/uv/uv.toml; do
    [ -f "$f" ] || continue
    line=$(grep -E '^[[:space:]]*python-(downloads|preference)[[:space:]]*=[[:space:]]*"(never|manual|only-system)"' "$f" | head -n 1)
    [ -z "$line" ] || { echo "$(echo "$line" | tr -d ' ') in $f"; return 0; }
  done
  return 1
}

# Everything runs inside main, so sh has read the whole script before any step can read stdin.
main() {
  [ "$(id -u)" -ne 0 ] || die "Run this as your normal desktop user, not as root."
  case "$(uname -s) $(uname -m)" in
    Linux\ *) fix_git="sudo pacman -S --needed git" ;;
    "Darwin arm64") fix_git="xcode-select --install" ;;
    *) die "Rook installs on Arch Linux with Hyprland, or on an Apple Silicon Mac, today." ;;
  esac
  # On a Mac without the Command Line Tools, /usr/bin/git is a stub that only offers to install them.
  git --version >/dev/null 2>&1 || die "git is missing. Run: $fix_git"

  source="$ROOK_PUBLIC_SOURCE"
  case "${1:-}" in
    ''|-*) ;;
    *) source="$1"; shift ;;
  esac

  # The agent Rook runs on: the one named with --agent, else the first that runs on PATH.
  # Checked first, so a missing agent stops the install before any download.
  orig_path=$PATH  # The search path the person has, before this run adds ~/.local/bin.
  export PATH="$HOME/.local/bin:$PATH"
  dry=0
  case " $* " in *" --dry-run "*) dry=1 ;; esac
  named="" prev=""
  for arg in "$@"; do
    [ "$prev" != "--agent" ] || named="$arg"
    prev="$arg"
  done
  agent="" agent_cmd="" label=""
  for entry in "claude:claude:Claude Code" "codex:codex:Codex" "agy:antigravity:Antigravity" "pi:pi:Pi"; do
    cmd="${entry%%:*}" rest="${entry#*:}"
    name="${rest%%:*}"
    [ -z "$named" ] || [ "$named" = "$name" ] || continue
    if command -v "$cmd" >/dev/null 2>&1 && bounded 10 /dev/null "$cmd" --version; then
      agent="$name" agent_cmd="$cmd" label="${rest#*:}"
      break
    fi
  done
  guide="https://github.com/topmass/rook/blob/main/INSTALL.md"
  if [ -n "$agent" ]; then
    [ -n "$named" ] || set -- --agent "$agent" "$@"
    say "Rook will run on $label ($(command -v "$agent_cmd")). To use another agent, add --agent claude, codex, antigravity or pi to the install command."
  elif [ -n "$named" ] && [ "$dry" -eq 0 ]; then
    die "Rook is set to run on $named with --agent, but that agent is missing or does not run. Install it and sign in (see $guide), or pick another with --agent claude, codex, antigravity or pi."
  elif [ "$dry" -eq 0 ]; then
    die "No coding agent found. Rook runs on Claude Code, Codex, Antigravity or Pi. Install one and sign in, then run this again. Claude Code installs with: curl -fsSL https://claude.ai/install.sh | bash. More in $guide"
  fi

  # 1. uv, the tool that builds Rook's Python environments.
  if ! command -v uv >/dev/null 2>&1 && [ "$dry" -eq 1 ]; then
    say "uv is missing. A real install gets it from https://astral.sh/uv/install.sh. This dry run does not."
  elif ! command -v uv >/dev/null 2>&1; then
    say "Installing uv. Its installer puts uv in ~/.local/bin and adds that folder to your shell's PATH in your shell's start files."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    command -v uv >/dev/null 2>&1 || die "uv did not install. See https://docs.astral.sh/uv/getting-started/installation/"
  fi

  # 2. The code, in a folder on disk. /tmp is often RAM.
  cache="${XDG_CACHE_HOME:-$HOME/.cache}"
  mkdir -p "$cache"
  work="$(mktemp -d "$cache/rook-get.XXXXXX")"
  trap 'rm -rf "$work"' EXIT
  case "$source" in
    *.tar.gz|*.tgz)
      if [ -f "$source" ]; then
        cp "$source" "$work/rook.tar.gz"
      else
        say "Downloading Rook from $source..."
        curl -fsSL "$source" -o "$work/rook.tar.gz" || die "Could not download $source."
      fi
      mkdir "$work/rook"
      tar -xzf "$work/rook.tar.gz" -C "$work/rook" --strip-components=1
      # install.sh installs from a git repository, so the unpacked code becomes one.
      git -C "$work/rook" init -q
      git -C "$work/rook" add -A
      git -C "$work/rook" -c user.name=Rook -c user.email=rook@localhost commit -qm "Rook from $source"
      from_tarball=1
      code="$work/rook"
      source="$work/rook" ;;
    *)
      if [ -d "$source" ]; then
        code="$(cd "$source" && pwd)"
        source="$code"
      else
        say "Getting Rook from $source..."
        GIT_TERMINAL_PROMPT=0 git clone -q --depth 1 "$source" "$work/rook" </dev/null \
          || die "Could not get Rook from $source. Check the address, or pass a local checkout or a .tar.gz URL."
        code="$work/rook"
      fi ;;
  esac
  [ -f "$code/install/install.sh" ] || die "$source does not hold Rook (install/install.sh is missing)."

  # 3. An old uv cannot fetch the Python Rook pins, and its self-update may refuse, so uv's own installer puts a
  # current uv first on this run's PATH. A setting that forbids Python downloads is named instead.
  pin=$(sed -n 's/^PYTHON_PIN="\(.*\)"$/\1/p' "$code/install/install.sh")
  if [ "$dry" -eq 0 ] && [ -n "$pin" ] && command -v uv >/dev/null 2>&1 && ! uv_knows "$pin"; then
    where=$(command -v uv)
    old=$(uv --version 2>/dev/null | cut -d' ' -f1,2)
    old=${old:-"the uv at $where"}
    if blocker=$(uv_download_blocker); then
      die "$blocker stops uv from fetching Python $pin, which Rook needs. Change that setting for this install, then run it again."
    fi
    # The folder uv's installer writes to, in its own order.
    dest=${UV_INSTALL_DIR:-${XDG_BIN_HOME:-${XDG_DATA_HOME:+$XDG_DATA_HOME/../bin}}}
    dest=${dest:-$HOME/.local/bin}
    mkdir -p "$dest" 2>/dev/null || true  # uv's installer makes it too; made here, its real path can be named.
    dest_real=$( (cd "$dest" 2>/dev/null && pwd -P) || printf '%s' "$dest")
    if [ "$( (cd "$(dirname "$where")" && pwd -P) )" = "$dest_real" ]; then
      what="replaces it in place in $dest_real"
    else
      what="puts a newer uv in $dest_real, ahead of the one at $where, which stays as it is"
    fi
    case ":$orig_path:" in
      *":$dest:"*|*":$dest_real:"*) later="" ;;
      *) later=" To use that uv yourself later, add $dest_real to your shell's PATH." ;;
    esac
    say "$old cannot fetch Python $pin, which Rook needs, so uv's own installer $what.$later"
    curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh || true
    PATH="$dest_real:$PATH"
    export PATH
    hash -r 2>/dev/null || true  # The shell must look uv up again.
    uv_knows "$pin" || die "$old is too old for Rook: it cannot fetch Python $pin. Replace it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
  fi

  # 4. Install. The models download here: the small voice (about 65 MB) and AirType's recogniser (about 480 MB for English, 490 MB with --recogniser-model multi).
  # The medium voice (about 3.3 GB on disk, 2.5 GB on a Mac) too, when this computer can run it.
  voice=medium
  why=$(sh "$code/install/medium-voice.sh" --check) || { voice=small; say "$why"; }
  case "$voice $*" in
    "medium "*--voice*) ;;
    medium*)
      size="3.3 GB"; [ "$(uname -s)" != Darwin ] || size="2.5 GB"
      say "Rook also gets its medium voice, a $size voice model. The install option --voice small skips it." ;;
  esac
  rc=0
  ROOK_GET_STARTS_ROOK=1 bash "$code/install/install.sh" --source "$source" \
    --voice "$voice" --voice-model yes --recogniser yes --service yes "$@" </dev/null || rc=$?
  if [ "$rc" -ne 0 ]; then
    say ""
    say "Rook is not installed yet. Fix the problem above, then run the same install command again."
    exit "$rc"
  fi
  case " $* " in *" --dry-run "*) exit 0 ;; esac

  # 5. Start Rook. relay.py verify then checks every piece, and Rook's own voice onboarding asks the rest.
  rook="${XDG_DATA_HOME:-$HOME/.local/share}/rook"
  verify="$rook/venv/bin/python $rook/live/desktop/relay.py verify"
  if [ "$(uname -s)" != Darwin ] && ! id -Gn | tr ' ' '\n' | grep -qx input; then
    say ""
    say "The talk key works only after you join the input group and log in again (see the note above)."
  fi
  label="${ROOK_LAUNCHD_LABEL:-com.rook.companion}"
  plist="$HOME/Library/LaunchAgents/$label.plist"
  if [ "$(uname -s)" = Darwin ] && [ -f "$plist" ]; then
    # Through launchd only, so the permissions belong to Rook.app. A Rook that is already loaded keeps running.
    launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1 || launchctl bootstrap "gui/$(id -u)" "$plist"
    # The app the launchd agent runs, wherever the installer put it: /Applications or ~/Applications.
    app=$(/usr/libexec/PlistBuddy -c "Print :ProgramArguments:0" "$plist" 2>/dev/null)
    app=${app%/Contents/MacOS/RookHelper}
    app=${app:-$HOME/Applications/Rook.app}
    say ""
    say "Rook is starting. Give it the microphone and the talk key first:"
    say "  open -W -n \"$app\" --args --request-access microphone   (click Allow)"
    say "  open -W -n \"$app\" --args --request-access input        (switch Rook on, then click Later)"
    say "  If no dialog appears, add Rook by hand: System Settings > Privacy & Security > Input Monitoring, click +, pick $app."
    say "  launchctl kickstart -k gui/$(id -u)/$label"
    say "Then hold Right Option and say hello: Rook takes it from there."
    say "Next, check every piece: $verify   (each row marked FIX prints its fix)"
  elif [ "$(uname -s)" = Darwin ]; then
    say ""
    say "Start Rook with the command above, then hold Right Option and say hello."
  else
    # The talk key in force: the saved one, else Right Control.
    key=$(python3 -c 'import json, re, sys
try:
    keys = json.load(open(sys.argv[1])).get("talk_keys") or []
except (OSError, ValueError, AttributeError):
    keys = []
key = keys[0] if keys and isinstance(keys, list) and isinstance(keys[0], str) else "RightCtrl"
print(re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", key).replace("Ctrl", "Control"))' \
      "${XDG_CONFIG_HOME:-$HOME/.config}/rook/settings.json" 2>/dev/null) || key="Right Control"
    say ""
    if [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/rook.service" ]; then
      systemctl --user start rook.service
      say "Rook is starting. Once every piece checks out, hold $key and say hello: Rook takes it from there."
    else
      say "Start Rook with the command above. Once every piece checks out, hold $key and say hello."
    fi
    say "Next, check every piece: $verify   (each row marked FIX prints its fix)"
    [ -z "${from_tarball:-}" ] || say "This copy came from a .tar.gz file, so relay.py update cannot update it. To update later, uninstall and install again from a git URL."
  fi
  # Last, so it is the line a person reads: an agent that is not signed in answers nothing.
  # Only a status command that runs and says plainly that it is signed out: an old tool without one says nothing.
  status="$work/agent-status.txt"
  case "$agent_cmd" in
    claude) bounded 15 "$status" "$agent_cmd" auth status --text && : > "$status"; login="auth login" ;;
    codex) bounded 15 "$status" "$agent_cmd" login status && : > "$status"; login="login" ;;
    *) : > "$status" 2>/dev/null || true ;;
  esac
  if [ -s "$status" ] && grep -qi -E 'not (logged|signed) in|logged out|signed out' "$status"; then
    signin="$(command -v "$agent_cmd") $login"
  fi
  if [ -n "${signin:-}" ]; then
    say ""
    say "Sign in first: $signin"
  fi
}

main "$@"
