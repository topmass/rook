#!/usr/bin/env python3
"""Rook's in-game overlay process. Run with the system python3 (not Decky's bundled one), as the desktop user, with
DISPLAY set to gamescope's Xwayland (":0" in Game Mode). overlay/launcher.py starts and stops it.

    rook_overlay.py [--url http://127.0.0.1:47331/overlay] [--mode auto|webengine|native] [--display :0]
                    [--anchor middle-right|middle-left|top-right|top-left|bottom-center]
                    [--geometry WxH+X+Y] [--parent-pid PID] [--always]

Two ways to draw, the same picture:
- webengine: a Qt WebEngine host already on the system (qmlscene from qt5-declarative with qt5-webengine, or Qt 6's
  qml with qt6-webengine) loads overlay/page in a transparent frameless window, so phone/presence.js draws Rook's
  real WebGL dust. This process then finds the host's X window, checks it is 32-bit (ARGB, so it really is
  transparent), tags it GAMESCOPE_EXTERNAL_OVERLAY and gives it an empty input shape. A window that is not ARGB is
  never tagged (gamescope then never shows it), and the process falls back to native.
- native: native.py, ctypes libX11 + libXext + libcairo, which every SteamOS has. Simpler dust, the same text.
auto tries webengine first, then native. Exit codes: 0 stopped by a signal or the parent going, 2 nothing could draw.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import anchors  # noqa: E402
import xlib  # noqa: E402
from urllib.parse import urlencode, urlsplit, urlunsplit  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:47331/overlay"


def log(msg):
    sys.stderr.write(f"rook-overlay: {msg}\n")
    sys.stderr.flush()


def parse_geometry(text):
    if not text:
        return None
    size, _, rest = text.partition("+")
    w, h = (int(v) for v in size.lower().split("x"))
    x, _, y = rest.partition("+")
    return int(x or 0), int(y or 0), w, h


# ------------------------------------------------------------------------------------------------------- webengine

QT5_IMPORTS = "import QtQuick 2.12\nimport QtQuick.Window 2.12\nimport QtWebEngine 1.8"
QT6_IMPORTS = "import QtQuick\nimport QtQuick.Window\nimport QtWebEngine"


def find_webengine_host():
    """(argv prefix, qt major) of a QML runtime with the QtWebEngine QML module beside it, or None.
    ROOK_OVERLAY_QML_HOST (a command line) and ROOK_OVERLAY_QT (5 or 6) name another host, for tests."""
    custom = os.environ.get("ROOK_OVERLAY_QML_HOST")
    if custom:
        return custom.split(), int(os.environ.get("ROOK_OVERLAY_QT", "6"))
    qt5_modules = [p for p in ("/usr/lib/qt/qml/QtWebEngine", "/usr/lib64/qt5/qml/QtWebEngine",
                               "/usr/lib/x86_64-linux-gnu/qt5/qml/QtWebEngine") if os.path.isdir(p)]
    qt6_modules = [p for p in ("/usr/lib/qt6/qml/QtWebEngine", "/usr/lib64/qt6/qml/QtWebEngine",
                               "/usr/lib/x86_64-linux-gnu/qt6/qml/QtWebEngine") if os.path.isdir(p)]
    if qt5_modules:
        for exe in (shutil.which("qmlscene"), shutil.which("qmlscene-qt5"), "/usr/lib/qt/bin/qmlscene",
                    "/usr/lib64/qt5/bin/qmlscene"):
            if exe and os.access(exe, os.X_OK):
                return [exe, "--transparent"], 5
    if qt6_modules:
        for exe in (shutil.which("qml6"), shutil.which("qml-qt6"), "/usr/lib/qt6/bin/qml", "/usr/lib64/qt6/bin/qml"):
            if exe and os.access(exe, os.X_OK):
                return [exe], 6
    return None


def page_url(url, anchor):
    """The page, told its anchor and that it fills a window placed for that anchor (not the whole screen)."""
    parts = urlsplit(url)
    query = (parts.query + "&" if parts.query else "") + urlencode({"anchor": anchor, "frame": "window"})
    return urlunsplit(parts._replace(query=query))


def write_qml(url, geometry, qt, always):
    x, y, w, h = geometry
    with open(os.path.join(HERE, "overlay.qml")) as f:
        qml = f.read()
    for key, value in {"@IMPORTS@": QT5_IMPORTS if qt == 5 else QT6_IMPORTS, "@X@": x, "@Y@": y, "@W@": w,
                       "@H@": h, "@URL@": url, "@ALWAYS@": "true" if always else "false"}.items():
        qml = qml.replace(key, str(value))
    folder = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    path = os.path.join(folder, f"rook-overlay-{os.getuid()}.qml")
    with open(path, "w") as f:
        f.write(qml)
    return path


def family(pid):
    """pid and every process under it (a host started through a wrapper has its window in a child)."""
    parents = {}
    for stat in os.listdir("/proc"):
        if stat.isdigit():
            try:
                with open(f"/proc/{stat}/stat") as f:
                    parents[int(stat)] = int(f.read().rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                pass
    out = {pid}
    grew = True
    while grew:
        grew = False
        for child, parent in parents.items():
            if parent in out and child not in out:
                out.add(child)
                grew = True
    return out


def windows_of(d, pid):
    pids = family(pid)
    return [w for w in d.walk(depth=3)
            if d.name_of(w) == "Rook Overlay" and d.get_cardinal(w, "_NET_WM_PID") in pids]


class Stop(Exception):
    pass


def run_webengine(args, d, geometry, stopping):
    host = find_webengine_host()
    if host is None:
        log("no Qt WebEngine QML runtime here")
        return None
    argv, qt = host
    qml = write_qml(page_url(args.url, args.anchor), geometry, qt, args.always)
    env = dict(os.environ)
    env.update({
        "QT_QPA_PLATFORM": "xcb",
        "DISPLAY": d.name,
        "QTWEBENGINE_DISABLE_SANDBOX": "1",  # Only our own localhost page loads; the sandbox needs user namespaces.
        "QT_QUICK_BACKEND": env.get("QT_QUICK_BACKEND", ""),
    })
    env.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--autoplay-policy=no-user-gesture-required --disable-pinch")
    log(f"webengine: {' '.join(argv)} (Qt {qt}) loading {args.url}")
    proc = subprocess.Popen(argv + [qml], env=env, stdin=subprocess.DEVNULL)
    tagged = set()
    deadline = time.monotonic() + 20
    try:
        while True:
            if stopping():
                raise Stop()
            if proc.poll() is not None:
                log(f"webengine host exited with {proc.returncode}")
                return False if not tagged else True
            for w in windows_of(d, proc.pid):
                if w in tagged:
                    continue
                a = d.attributes(w)
                if a is None:
                    continue
                if a.depth != 32:
                    log(f"webengine window 0x{w:x} is {a.depth}-bit, not ARGB: it would hide the game, so it is "
                        "not used")
                    proc.terminate()
                    proc.wait(5)
                    return False
                d.make_overlay(w)
                tagged.add(w)
                log(f"webengine window 0x{w:x} tagged GAMESCOPE_EXTERNAL_OVERLAY, input-transparent")
            if not tagged and time.monotonic() > deadline:
                log("webengine host made no window in 20 s")
                proc.terminate()
                proc.wait(5)
                return False
            if args.parent_pid and not alive(args.parent_pid):
                raise Stop()
            time.sleep(0.05 if not tagged else 1.0)
    except Stop:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return True


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def main(argv=None):
    p = argparse.ArgumentParser(description="Rook's in-game overlay (gamescope external overlay).")
    p.add_argument("--url", default=DEFAULT_URL, help="the overlay page; its SSE is <url>/events")
    p.add_argument("--mode", default="auto", choices=("auto", "webengine", "native"))
    p.add_argument("--display", default=os.environ.get("DISPLAY") or ":0")
    p.add_argument("--anchor", default=anchors.DEFAULT, help="where on the screen: " + ", ".join(anchors.ANCHORS))
    p.add_argument("--geometry", default=None, help="WxH+X+Y, overriding the anchor's window rectangle")
    p.add_argument("--parent-pid", type=int, default=None, help="exit when this process is gone")
    p.add_argument("--events", default=None, help="the SSE stream (default: <url>/events)")
    p.add_argument("--no-tag", action="store_true", help=argparse.SUPPRESS)  # tests: a plain override window
    p.add_argument("--always", action="store_true", help="keep the window mapped (for tests)")
    args = p.parse_args(argv)

    flag = {"stop": False}

    def on_signal(*_):
        flag["stop"] = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    try:
        d = xlib.Display(args.display)
    except xlib.XError as e:
        log(str(e))
        return 2
    import native  # noqa: E402  (loads libcairo only when needed)
    args.anchor = anchors.normalise(args.anchor)
    geometry = parse_geometry(args.geometry) or anchors.geometry(args.anchor, d.width, d.height)
    others = [o for o in d.external_overlays()]
    if others:
        log("other external overlays are mapped (gamescope shows one at a time): "
            + ", ".join(f"0x{w:x} {name!r} pid {pid}" for w, name, pid in others))

    if args.mode in ("auto", "webengine"):
        done = run_webengine(args, d, geometry, lambda: flag["stop"])
        if done or flag["stop"]:
            return 0
        if args.mode == "webengine":
            return 2
    if flag["stop"]:
        return 0
    events = args.events or args.url.rstrip("/") + "/events"
    try:
        r = native.Renderer(d, geometry, events, args.parent_pid, tag=not args.no_tag, anchor=args.anchor)
    except xlib.XError as e:
        log(f"native renderer: {e}")
        return 2
    signal.signal(signal.SIGTERM, r.stop)
    signal.signal(signal.SIGINT, r.stop)
    log(f"native renderer on {d.name} {d.width}x{d.height}, anchor {args.anchor}, window {geometry}, events {events}")
    r.run()
    d.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
