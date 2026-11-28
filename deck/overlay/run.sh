#!/bin/sh
# Start, stop or check Rook's overlay by hand (the plugin backend uses launcher.py's start()/stop() directly).
#   overlay/run.sh start|stop|status|restart
# Env: ROOK_OVERLAY_MODE=auto|webengine|native, ROOK_OVERLAY_ANCHOR=middle-right|middle-left|top-right|top-left|
#      bottom-center, ROOK_OVERLAY_URL (default http://127.0.0.1:47331/overlay),
#      ROOK_OVERLAY_DISPLAY (default: from the running gamescope/Steam, else :0). Log: /tmp/rook-overlay/overlay.log
set -eu
here=$(cd "$(dirname "$0")" && pwd)
py=/usr/bin/python3
[ -x "$py" ] || py=python3
# Decky's bundled Python leaks these into child shells; the system python3 must not see them.
unset LD_LIBRARY_PATH LD_PRELOAD PYTHONHOME PYTHONPATH
case "${1:-status}" in
  start|stop|status) exec "$py" "$here/launcher.py" "$1" ;;
  restart) "$py" "$here/launcher.py" stop >/dev/null; exec "$py" "$here/launcher.py" start ;;
  *) echo "usage: $0 start|stop|status|restart" >&2; exit 2 ;;
esac
