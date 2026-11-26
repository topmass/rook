#!/bin/sh
# Run one harmless live Antigravity (agy) turn through Rook on macOS and print the answer.
# Uses scratch XDG folders and no speakers. Run after signing agy in once on the Mac.
# Usage: macos/live-turn.sh [PROMPT]
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
prompt="${1:-Reply with exactly three words: Rook Mac ready.}"
py="${ROOK_PYTHON:-$HOME/rook-mac1/.venv/bin/python}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

scratch=$(mktemp -d /tmp/rook-mac-live-XXXXXX)
trap 'kill "${rook_pid:-}" 2>/dev/null || true; wait "${rook_pid:-}" 2>/dev/null || true; rm -rf "$scratch"' EXIT
mkdir -p "$scratch/config/rook" "$scratch/data/rook" "$scratch/cache" "$scratch/state" "$scratch/run"
printf '{"agent": "antigravity"}\n' > "$scratch/config/rook/settings.json"

export XDG_CONFIG_HOME="$scratch/config"
export XDG_DATA_HOME="$scratch/data"
export XDG_CACHE_HOME="$scratch/cache"
export XDG_STATE_HOME="$scratch/state"
export XDG_RUNTIME_DIR="$scratch/run"
export ROOK_AUDIO_OUT=null

"$py" "$here/desktop/rook.py" --workspace "$scratch" > "$scratch/rook.out" 2> "$scratch/rook.err" &
rook_pid=$!

i=0
while [ "$i" -lt 80 ]; do
  [ -S "$scratch/run/rook.sock" ] && break
  sleep 0.25
  i=$((i + 1))
done
if [ ! -S "$scratch/run/rook.sock" ]; then
  echo "Rook did not open its socket." >&2
  cat "$scratch/rook.err" >&2
  exit 1
fi

"$py" "$here/desktop/relay.py" ask "$prompt"
