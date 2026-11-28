"""Start and stop Rook's overlay process (overlay/rook_overlay.py) from the plugin backend.

The backend runs in Decky's bundled Python as root; the overlay must run with the system python3 (/usr/bin/python3,
which can load the system's libX11, libcairo and Qt), as the desktop user, on gamescope's Xwayland. This module does
that and nothing else: pure standard library, no decky import, safe to import from Decky's Python 3.11.

    import importlib.util, os
    spec = importlib.util.spec_from_file_location("rook_overlay_launcher",
                                                  os.path.join(decky.DECKY_PLUGIN_DIR, "overlay", "launcher.py"))
    launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)

    launcher.start(url="http://127.0.0.1:47331/overlay", display=":0", xauthority=None, user=decky.DECKY_USER,
                   log_path=os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "overlay.log"),
                   anchor="middle-right")                                               -> status dict
    launcher.stop()                                                                     -> status dict
    launcher.status()  -> {"running": bool, "pid": int|None, "mode": "webengine"|"native"|None, "anchor": str,
                           "error": str|None, "log": str|None, "others": [str]}
    launcher.ANCHORS   -> ("middle-right", "middle-left", "top-right", "top-left", "bottom-center")

anchor picks where the overlay sits (overlay/anchors.py); start() with another anchor restarts the overlay there, so
set_overlay_position(anchor) is: store it, then start(..., anchor=anchor). geometry ("WxH+X+Y") overrides it.

start() is idempotent (a running overlay is left alone unless its settings changed) and kills a stale one left by a
previous backend (pid file /tmp/rook-overlay/overlay.pid). The child exits by itself when the backend's pid is gone.
gamescope shows one external overlay at a time: "others" names other mapped ones (mangoapp, the performance overlay,
is one while it shows).
"""

import importlib.util
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "rook_overlay.py")
RUN_DIR = "/tmp/rook-overlay"
PID_FILE = os.path.join(RUN_DIR, "overlay.pid")
DEFAULT_URL = "http://127.0.0.1:47331/overlay"
# Decky's bundled (PyInstaller) Python sets these; they would break the system python3 and Qt.
STRIP_ENV = ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "PYTHONSAFEPATH", "_MEIPASS2",
             "QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "SSL_CERT_FILE")

_spec = importlib.util.spec_from_file_location("rook_overlay_anchors", os.path.join(HERE, "anchors.py"))
anchors = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anchors)
ANCHORS = anchors.ANCHORS
DEFAULT_ANCHOR = anchors.DEFAULT

_proc = None
_args = None
_anchor = DEFAULT_ANCHOR
_log_path = None
_error = None


def _python():
    for p in ("/usr/bin/python3", "/usr/local/bin/python3"):
        if os.access(p, os.X_OK):
            return p
    return None


def _user(user):
    """(uid, gid, home, name) to run as, or None to stay as we are (not root, or no such user)."""
    if os.geteuid() != 0:
        return None
    import pwd
    candidates = [user] if user is not None else [os.environ.get("DECKY_USER"), "deck"]
    for u in candidates:
        if u is None:
            continue
        try:
            pw = pwd.getpwuid(u) if isinstance(u, int) else pwd.getpwnam(str(u))
            return pw.pw_uid, pw.pw_gid, pw.pw_dir, pw.pw_name
        except KeyError:
            continue
    return None


def _display_env(uid):
    """DISPLAY and XAUTHORITY from the user's running gamescope or Steam, as the backend's env.py does."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if uid is not None and os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
            if not (comm.startswith("gamescope") or comm in ("steam", "steamwebhelper")):
                continue
            with open(f"/proc/{pid}/environ", "rb") as f:
                pairs = [item.split(b"=", 1) for item in f.read().split(b"\0") if b"=" in item]
        except OSError:
            continue
        env = {k.decode(errors="replace"): v.decode(errors="replace") for k, v in pairs}
        if env.get("DISPLAY"):
            return {k: env[k] for k in ("DISPLAY", "XAUTHORITY") if env.get(k)}
    return {}


def _read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _is_overlay(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"rook_overlay.py" in f.read()
    except OSError:
        return False


def _kill(pid, timeout):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not _is_overlay(pid):
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _reap():
    global _proc
    if _proc is not None and _proc.poll() is not None:
        _proc = None


def start(url=DEFAULT_URL, display=None, xauthority=None, user=None, mode="auto", log_path=None, geometry=None,
          parent_pid=None, anchor=DEFAULT_ANCHOR):
    """Starts the overlay (or leaves a running one with the same settings). Returns status()."""
    global _proc, _args, _log_path, _error, _anchor
    _reap()
    anchor = anchors.normalise(anchor)
    who = _user(user)
    uid = who[0] if who else os.getuid()
    found = {} if display else _display_env(uid)
    display = display or found.get("DISPLAY") or ":0"
    xauthority = xauthority or found.get("XAUTHORITY")
    args = (url, display, xauthority, mode, geometry, anchor)
    if _proc is not None and _args == args:
        return status()
    if _proc is not None:
        stop()
    stale = _read_pid()
    if stale and _is_overlay(stale):
        _kill(stale, 2.0)
    python = _python()
    if python is None:
        _error = "no system python3"
        return status()
    env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
    env["DISPLAY"] = display
    if xauthority:
        env["XAUTHORITY"] = xauthority
    kwargs = {}
    if who:
        uid, gid, home, name = who
        env.update({"HOME": home, "USER": name, "LOGNAME": name, "XDG_RUNTIME_DIR": f"/run/user/{uid}"})
        kwargs = {"user": uid, "group": gid, "extra_groups": []}
    argv = [python, "-u", SCRIPT, "--url", url, "--mode", mode, "--display", display,
            "--parent-pid", str(parent_pid or os.getpid()), "--anchor", anchor]
    if geometry:
        argv += ["--geometry", geometry]
    os.makedirs(RUN_DIR, exist_ok=True)
    _log_path = log_path or os.path.join(RUN_DIR, "overlay.log")
    try:
        if os.path.exists(_log_path) and os.path.getsize(_log_path) > 256 * 1024:
            os.replace(_log_path, _log_path + ".1")
        log = open(_log_path, "a")
        log.write(f"--- start {time.strftime('%Y-%m-%d %H:%M:%S')} DISPLAY={display} mode={mode}\n")
        log.flush()
        if who:
            try:
                os.chown(_log_path, who[0], who[1])
            except OSError:
                pass
        _proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env, cwd=HERE,
                                 start_new_session=True, **kwargs)
        log.close()
        with open(PID_FILE, "w") as f:
            f.write(f"{_proc.pid}\n")
        _args = args
        _anchor = anchor
        _error = None
    except Exception as e:  # noqa: BLE001 - every failure becomes the status's error
        _proc = None
        _error = f"cannot start the overlay: {e}"
    return status()


def stop(timeout=3.0):
    """Stops the overlay (ours, or a stale one from the pid file). Returns status()."""
    global _proc, _args
    if _proc is not None:
        if _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(timeout)
            except subprocess.TimeoutExpired:
                _proc.kill()
                _proc.wait(1)
        _proc = None
    stale = _read_pid()
    if stale and _is_overlay(stale):
        _kill(stale, timeout)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    _args = None
    return status()


def _tail():
    if not _log_path:
        return []
    try:
        with open(_log_path, "rb") as f:
            f.seek(max(0, os.path.getsize(_log_path) - 8192))
            lines = f.read().decode(errors="replace").splitlines()
    except OSError:
        return []
    for i in range(len(lines) - 1, -1, -1):  # This run's lines only.
        if lines[i].startswith("--- start"):
            return lines[i + 1:]
    return lines


def status():
    _reap()
    lines = _tail()
    mode = None
    others = []
    error = _error
    for line in lines:
        if "tagged GAMESCOPE_EXTERNAL_OVERLAY" in line:
            mode = "webengine"
        elif "native renderer on" in line:
            mode = "native"
        elif "other external overlays are mapped" in line:
            others = [line.split(": ", 2)[-1]]
    running = _proc is not None and _proc.poll() is None
    if not running and error is None and lines and _args is not None:
        error = lines[-1].replace("rook-overlay: ", "")
    return {"running": running, "pid": _proc.pid if running else None, "mode": mode if running else None,
            "anchor": _anchor, "error": error, "log": _log_path, "others": others}


if __name__ == "__main__":  # python3 launcher.py start|stop|status  (overlay/run.sh calls this)
    import json
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        s = start(mode=os.environ.get("ROOK_OVERLAY_MODE", "auto"),
                  url=os.environ.get("ROOK_OVERLAY_URL", DEFAULT_URL),
                  display=os.environ.get("ROOK_OVERLAY_DISPLAY"), parent_pid=1,
                  anchor=os.environ.get("ROOK_OVERLAY_ANCHOR", DEFAULT_ANCHOR))
        time.sleep(1.5)
        _args = None  # The CLI exits; the child keeps running, found again by its pid file.
        print(json.dumps(status()))
        _proc = None
    elif cmd == "stop":
        print(json.dumps(stop()))
    else:
        pid = _read_pid()
        print(json.dumps({"running": bool(pid and _is_overlay(pid)), "pid": pid if pid and _is_overlay(pid) else None}))
