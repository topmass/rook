#!/bin/sh
# Install Rook's medium voice on an Apple Silicon Mac: Qwen3-TTS 0.6B on MLX (desktop/medium_voice.py), served on
# 127.0.0.1:8090 by a user LaunchAgent, then point Rook at it. Any other Mac keeps the small voice.
# About 2.5 GB on disk (500 MB environment, 2 GB model). The model loads only while Rook uses the medium voice.
# Usage: launchd/install-voice.sh [--python PATH]   PATH is Rook's Python (default: .venv/bin/python in the repo).
#        launchd/install-voice.sh --check           exits 0 when this Mac can run it, else says why and exits 1.
# --no-start writes the launchd agent without loading it, and prints the command that starts it.
# --then-start is --no-start without that hint, and --start-only installs nothing: it loads the agent written
# earlier and waits for the voice. install.sh runs the two, and records the plist's hash between them.
# ROOK_MEDIUM_MIN_GB (default 16) is the least memory, in GB, that gets the medium voice.
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
python_bin="${ROOK_PYTHON:-$here/.venv/bin/python}"
[ "${1:-}" = "--python" ] && python_bin="$2"
start=1
start_only=0
hint=1
for arg in "$@"; do
	[ "$arg" != "--no-start" ] || start=0
	[ "$arg" != "--then-start" ] || { start=0; hint=0; }
	[ "$arg" != "--start-only" ] || start_only=1
done
data="${XDG_DATA_HOME:-$HOME/.local/share}/rook/medium-voice"
label="${ROOK_MEDIUM_LABEL:-com.rook.medium-voice}"  # Tests give a scratch label.
port="${ROOK_MEDIUM_PORT:-8090}"
url="http://127.0.0.1:$port"

mem_gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
if [ "$(uname -s) $(uname -m)" != "Darwin arm64" ] || [ "$mem_gb" -lt "${ROOK_MEDIUM_MIN_GB:-16}" ]; then
	echo "This Mac keeps the small voice. The medium voice needs Apple Silicon and ${ROOK_MEDIUM_MIN_GB:-16} GB of memory."
	[ "${1:-}" != "--check" ] || exit 1
	exit 0
fi
[ "${1:-}" != "--check" ] || exit 0
uv=$(command -v uv || echo "$HOME/.local/bin/uv")
[ -x "$uv" ] || { echo "The medium voice needs uv. Install it from https://docs.astral.sh/uv/ and run this again." >&2; exit 1; }

plist="$HOME/Library/LaunchAgents/$label.plist"
if [ "$start_only" -eq 0 ]; then
echo "Installing the medium voice in $data..."
mkdir -p "$data" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
[ -x "$data/venv/bin/python" ] || "$uv" venv -q --python 3.12 "$data/venv"
"$uv" pip install -q --require-hashes --no-build --python "$data/venv/bin/python" -r "$here/install/requirements-medium-voice-macos.txt"
echo "Downloading the medium voice's model, about 2 GB. It shows no progress, so the log stays quiet until it ends."
HF_HUB_DISABLE_PROGRESS_BARS=1 "$data/venv/bin/python" "$here/desktop/medium_voice.py" --download >/dev/null
echo "The medium voice's model is downloaded, and every file matches its pinned checksum."

cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$label</string>
	<key>ProgramArguments</key>
	<array>
		<string>$data/venv/bin/python</string>
		<string>$here/desktop/medium_voice.py</string>
	</array>
	<key>EnvironmentVariables</key>
	<dict>
		<key>ROOK_MEDIUM_PORT</key>
		<string>$port</string>
		<key>XDG_DATA_HOME</key>
		<string>${XDG_DATA_HOME:-$HOME/.local/share}</string>
		<key>HF_HUB_OFFLINE</key>
		<string>1</string>
		<key>PYTHONUNBUFFERED</key>
		<string>1</string>
	</dict>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<true/>
	<key>ThrottleInterval</key>
	<integer>5</integer>
	<key>StandardOutPath</key>
	<string>$HOME/Library/Logs/rook-medium-voice.log</string>
	<key>StandardErrorPath</key>
	<string>$HOME/Library/Logs/rook-medium-voice.log</string>
</dict>
</plist>
EOF
fi
if [ "$start" -eq 1 ]; then
	launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
	launchctl bootstrap "gui/$(id -u)" "$plist"
	tries=0
	until curl -fs "$url/health" >/dev/null; do
		tries=$((tries + 1))
		[ "$tries" -lt 50 ] || { echo "The medium voice server did not start. See ~/Library/Logs/rook-medium-voice.log." >&2; exit 1; }
		sleep 0.2
	done
elif [ "$hint" -eq 1 ]; then
	echo "Start the medium voice with: launchctl bootstrap gui/$(id -u) $plist"
fi

[ "$start_only" -eq 0 ] || exit 0
if [ -x "$python_bin" ]; then
	"$python_bin" "$here/desktop/relay.py" set medium_voice_url "$url"
	"$python_bin" "$here/desktop/relay.py" set voice_engine medium
else
	echo "Rook's Python is not at $python_bin. Point Rook at the voice with:"
	echo "  relay.py set medium_voice_url $url && relay.py set voice_engine medium"
fi
echo "The medium voice is installed. Remove it with: launchctl bootout gui/$(id -u)/$label; rm $plist"
