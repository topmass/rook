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

  # The base agent: the first one found on PATH. --agent after SOURCE overrides it.
  # Checked first, so a missing agent stops the install before any download.
  export PATH="$HOME/.local/bin:$PATH"
  for pair in claude:claude codex:codex agy:antigravity pi:pi; do
    if command -v "${pair%%:*}" >/dev/null 2>&1; then
      set -- --agent "${pair#*:}" "$@"
      break
    fi
  done
  case " $* " in
    *" --agent"*|*" --dry-run "*) ;;
    *) die "No agent found on PATH. Install Claude Code, Codex, Antigravity, or Pi and sign in (see INSTALL.md step 1), then run this again." ;;
  esac

  # 1. uv, the tool that builds Rook's Python environments.
  if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv..."
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

  # 4. Install. The models download here: the small voice (about 65 MB) and AirType's recogniser (about 490 MB, English unless --recogniser-model multi).
  # The medium voice (about 3.3 GB on disk, 2.5 GB on a Mac) too, when this computer can run it.
  voice=medium
  why=$(sh "$code/install/medium-voice.sh" --check) || { voice=small; say "$why"; }
  case "$voice $*" in
    "medium "*--voice*) ;;
    medium*)
      size="3.3 GB"; [ "$(uname -s)" != Darwin ] || size="2.5 GB"
      say "Rook also gets its medium voice, a $size voice model. To skip it, press Ctrl+C and add --voice small to the install command." ;;
  esac
  rc=0
  bash "$code/install/install.sh" --source "$source" \
    --voice "$voice" --voice-model yes --recogniser yes --service yes "$@" </dev/null || rc=$?
  if [ "$rc" -ne 0 ]; then
    say ""
    say "Rook is not installed yet. Fix the problem above, then run the same install command again."
    exit "$rc"
  fi
  case " $* " in *" --dry-run "*) exit 0 ;; esac

  # 5. Rook hands real work to T3 Code or Herdr. With neither here, offer Herdr through its official installer.
  # Without a terminal to answer on, nothing installs, and onboarding offers Herdr again.
  if ! command -v t3 >/dev/null 2>&1 && ! command -v herdr >/dev/null 2>&1; then
    say ""
    say "Rook hands real work to background threads, and needs T3 Code or Herdr to run them. Neither is here."
    say "We recommend T3 Code: download it from https://t3.codes and open it, and Rook finds it."
    printf '%s' "Or install Herdr now, a lighter option that runs in your terminal? [y/N] "
    answer=$( (read -r reply </dev/tty && printf '%s' "$reply") 2>/dev/null ) || answer=""
    say ""
    case "$answer" in
      [Yy]*)
        if curl -fsSL https://herdr.dev/install.sh | sh && command -v herdr >/dev/null 2>&1; then
          say "Herdr is installed. Rook walks you through starting it during setup."
        else
          say "Herdr did not install. Rook can try again during setup."
        fi ;;
      *) say "No Herdr for now. Rook offers it again during setup." ;;
    esac
  fi

  # 6. Start Rook. Its own voice onboarding asks the rest.
  if [ "$(uname -s)" != Darwin ] && ! id -Gn | tr ' ' '\n' | grep -qx input; then
    say ""
    say "The talk key works only after you join the input group and log in again (see the note above)."
  fi
  label="${ROOK_LAUNCHD_LABEL:-com.rook.companion}"
  plist="$HOME/Library/LaunchAgents/$label.plist"
  if [ "$(uname -s)" = Darwin ] && [ -f "$plist" ]; then
    # Through launchd only, so the permissions belong to Rook.app. A Rook that is already loaded keeps running.
    launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1 || launchctl bootstrap "gui/$(id -u)" "$plist"
    app="${ROOK_APP:-$HOME/Applications/Rook.app}"
    say ""
    say "Rook is starting. Give it the microphone and the talk key first:"
    say "  open -W -n \"$app\" --args --request-access microphone   (click Allow)"
    say "  open -W -n \"$app\" --args --request-access input        (switch Rook on, then click Later)"
    say "  launchctl kickstart -k gui/$(id -u)/$label"
    say "Then hold Right Option and say \"run onboarding\"."
  elif [ "$(uname -s)" = Darwin ]; then
    say ""
    say "Start Rook with the command above, then hold Right Option and say \"run onboarding\"."
  elif [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/rook.service" ]; then
    systemctl --user start rook.service
    say ""
    say "Rook is starting. When it says it is ready, hold Right Control and say \"run onboarding\"."
  else
    say ""
    say "Start Rook with the command above, then hold Right Control and say \"run onboarding\"."
  fi
}

main "$@"
