#!/bin/sh
# Install Rook's login service for this user: link the units, reload systemd, and enable Rook, so it starts
# with every graphical login. rook-failed.service is only linked: rook.service starts it when it gives up.
# rook-daily.timer is enabled and started: it restarts a running Rook once a day after the nightly dream.
# Safe to run again. It does not start or stop Rook.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
units="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
systemctl=${SYSTEMCTL:-systemctl}  # Tests point this at a stand-in.
mkdir -p "$units"
ln -sfn "$here/rook.service" "$units/rook.service"
ln -sfn "$here/rook-failed.service" "$units/rook-failed.service"
ln -sfn "$here/rook-daily.service" "$units/rook-daily.service"
ln -sfn "$here/rook-daily.timer" "$units/rook-daily.timer"
"$systemctl" --user daemon-reload
"$systemctl" --user enable rook.service
"$systemctl" --user enable --now rook-daily.timer
echo "Installed $units/rook.service, rook-failed.service, and rook-daily.service and .timer, linked to $here."
echo "Rook starts with graphical logins, and the daily restart runs at 04:30."
echo "Start it now with: systemctl --user start rook.service"
