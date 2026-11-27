#!/bin/sh
# Install or print Rook's macOS user LaunchAgent (~/Library/LaunchAgents/com.rook.companion.plist).
# launchd runs the signed Rook.app, which runs Python as its child, so macOS gives every
# permission to Rook.app and not to Python. Build the app first with macos/RookHelper/build.sh.
# Usage: launchd/install.sh [--print] [--daily] [--app PATH] [--python PATH] [--workspace PATH]
# With --print, prints the plist to stdout and changes nothing on disk.
# With --daily, the plist is <label>.daily instead: relay.py daily-restart at 04:30, as the Linux rook-daily.timer.
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
print_only=0
daily=0
app="${ROOK_APP:-$HOME/Applications/Rook.app}"
python_bin="${ROOK_PYTHON:-$here/.venv/bin/python}"
workspace="${ROOK_WORKSPACE:-$HOME/Work}"
label="${ROOK_LAUNCHD_LABEL:-com.rook.companion}"

while [ "$#" -gt 0 ]; do
	case "$1" in
		--print) print_only=1; shift ;;
		--daily) daily=1; shift ;;
		--app) app="$2"; shift 2 ;;
		--python) python_bin="$2"; shift 2 ;;
		--workspace) workspace="$2"; shift 2 ;;
		*) echo "Usage: $0 [--print] [--daily] [--app PATH] [--python PATH] [--workspace PATH]" >&2; exit 2 ;;
	esac
done

if [ "$daily" -eq 1 ]; then
	# launchd runs a missed time after the Mac wakes; daily-restart still waits until Rook is idle.
	plist=$(cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>${label}.daily</string>
	<key>ProgramArguments</key>
	<array>
		<string>${python_bin}</string>
		<string>${here}/desktop/relay.py</string>
		<string>daily-restart</string>
	</array>
	<key>WorkingDirectory</key>
	<string>${here}</string>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
		<key>ROOK_LAUNCHD_LABEL</key>
		<string>${label}</string>
	</dict>
	<key>StartCalendarInterval</key>
	<dict>
		<key>Hour</key>
		<integer>4</integer>
		<key>Minute</key>
		<integer>30</integer>
	</dict>
	<key>LimitLoadToSessionType</key>
	<string>Aqua</string>
	<key>StandardOutPath</key>
	<string>${HOME}/Library/Logs/rook-daily.log</string>
	<key>StandardErrorPath</key>
	<string>${HOME}/Library/Logs/rook-daily.log</string>
</dict>
</plist>
EOF
)
	label="${label}.daily"
else
	plist=$(cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>${label}</string>
	<key>ProgramArguments</key>
	<array>
		<string>${app}/Contents/MacOS/RookHelper</string>
		<string>--launch</string>
		<string>${python_bin}</string>
		<string>${here}/desktop/rook.py</string>
		<string>--workspace</string>
		<string>${workspace}</string>
		<string>--keys</string>
	</array>
	<key>WorkingDirectory</key>
	<string>${here}</string>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
		<key>PYTHONUNBUFFERED</key>
		<string>1</string>
		<key>ROOK_LAUNCHD_LABEL</key>
		<string>${label}</string>
	</dict>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<dict>
		<key>SuccessfulExit</key>
		<false/>
	</dict>
	<key>ThrottleInterval</key>
	<integer>5</integer>
	<key>LimitLoadToSessionType</key>
	<string>Aqua</string>
	<key>StandardOutPath</key>
	<string>${HOME}/Library/Logs/rook.out.log</string>
	<key>StandardErrorPath</key>
	<string>${HOME}/Library/Logs/rook.err.log</string>
</dict>
</plist>
EOF
)
fi

if [ "$daily" -eq 0 ] && [ -n "${HERDR_SOCKET_PATH:-}${HERDR_CONFIG_PATH:-}${ROOK_ALLOW_HERDR_SOCKET:-}" ]; then
	plist=$(printf '%s\n' "$plist" | python3 -c '
import plistlib
import sys

job = plistlib.loads(sys.stdin.buffer.read())
names = ("HERDR_SOCKET_PATH", "HERDR_CONFIG_PATH", "ROOK_ALLOW_HERDR_SOCKET")
job["EnvironmentVariables"].update({name: value for name, value in zip(names, sys.argv[1:]) if value})
plistlib.dump(job, sys.stdout.buffer)
' "${HERDR_SOCKET_PATH:-}" "${HERDR_CONFIG_PATH:-}" "${ROOK_ALLOW_HERDR_SOCKET:-}")
fi

if [ "$print_only" -eq 1 ]; then
	printf '%s\n' "$plist"
	exit 0
fi

dest="$HOME/Library/LaunchAgents/${label}.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
printf '%s\n' "$plist" > "$dest"
echo "Wrote $dest."
echo "Start it with: launchctl bootstrap gui/$(id -u) $dest"
echo "Stop it with:  launchctl bootout gui/$(id -u)/${label}"
