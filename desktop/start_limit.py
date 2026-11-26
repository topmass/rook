"""The Mac start limit: a start that keeps failing stops after five tries in 300 s, as systemd's start limit does
on Linux. launchd restarts Rook after every exit but a clean one (KeepAlive SuccessfulExit=false), so on the fifth
failure Rook posts one notification and exits 0, and launchd lets it rest. A good start clears the count.

rook.py imports this before any of Rook's own modules, so an import error counts too. Standard library only, so
it cannot fail the way it counts. Linux never reads or writes the file.

python3 start_limit.py --check runs the self-check: scratch folders and a stand-in osascript, never the real one."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

LIMIT = 5  # Failed starts...
WINDOW = 300  # ...in this many seconds: Linux rook.service has StartLimitBurst=5, StartLimitIntervalSec=300.


def path():
    """Rook's state folder, as desk.state_dir() finds it, without importing desk."""
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "rook/start-failures.json"


def failed(now=None):
    """Count one failed start. On the fifth in WINDOW seconds, post one notification and exit 0."""
    now = time.time() if now is None else now
    target = path()
    try:
        times = [t for t in json.loads(target.read_text()) if isinstance(t, (int, float)) and 0 <= now - t < WINDOW]
    except (OSError, ValueError, TypeError):
        times = []
    times.append(now)
    if len(times) < LIMIT:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(times))
        except OSError:
            pass
        return
    target.unlink(missing_ok=True)  # A later start by hand gets five tries again.
    label = os.environ.get("ROOK_LAUNCHD_LABEL") or "com.rook.companion"
    text = (f"Rook failed to start {LIMIT} times, so it stopped: the reason is in ~/Library/Logs/rook.err.log, and "
            f"launchctl kickstart gui/{os.getuid()}/{label} starts it again.")
    try:
        subprocess.run(["osascript", "-e", f'display notification "{text}" with title "Rook stopped"'],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass
    print(f"Rook stopped after {LIMIT} failed starts in {WINDOW // 60} minutes. {text}", file=sys.stderr, flush=True)
    os._exit(0)


def cleared():
    """A good start: forget the failures."""
    path().unlink(missing_ok=True)


def install(platform=None):
    """On a Mac, count every uncaught error as a failed start. Return whether it is on."""
    if (platform or sys.platform) != "darwin":
        return False
    default = sys.excepthook

    def hook(kind, error, trace):
        default(kind, error, trace)
        if not issubclass(kind, KeyboardInterrupt):
            sys.stderr.flush()
            failed()

    sys.excepthook = hook
    return True


def check():
    import shlex
    import tempfile
    here = Path(__file__).resolve()
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        stand_in = base / "bin/osascript"
        stand_in.parent.mkdir()
        calls = base / "osascript.log"
        stand_in.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {shlex.quote(str(calls))}\n")
        stand_in.chmod(0o755)
        state = base / "state"
        env = {**os.environ, "XDG_STATE_HOME": str(state), "PATH": f"{stand_in.parent}:{os.environ.get('PATH', '')}",
               "ROOK_LAUNCHD_LABEL": "com.rook.checktest"}
        record = state / "rook/start-failures.json"

        def start(platform, fail=True):
            """A start that dies before any of Rook's code runs, as an import error does."""
            code = (f"import sys; sys.path.insert(0, {str(here.parent)!r}); import start_limit; "
                    f"start_limit.install({platform!r}); " + ("import no_such_rook_module" if fail else
                                                             "start_limit.cleared()"))
            return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)

        # 1. Five fast failures on a Mac: four exit 1, the fifth notifies once and exits 0, and the count is gone.
        codes = [start("darwin").returncode for _ in range(LIMIT)]
        assert codes == [1] * (LIMIT - 1) + [0], codes
        lines = calls.read_text().splitlines()
        assert len(lines) == 1 and 'with title "Rook stopped"' in lines[0] and "rook.err.log" in lines[0] \
            and "launchctl kickstart gui/" in lines[0] and "com.rook.checktest" in lines[0], lines
        assert not record.exists()
        # 2. Four failures, then a good start, clears it: four more failures stop nothing.
        calls.unlink()
        for _ in range(LIMIT - 1):
            assert start("darwin").returncode == 1
        assert len(json.loads(record.read_text())) == LIMIT - 1
        assert start("darwin", fail=False).returncode == 0 and not record.exists()
        for _ in range(LIMIT - 1):
            assert start("darwin").returncode == 1
        assert not calls.exists()
        # 3. A failure older than WINDOW seconds does not count.
        now = time.time()
        record.write_text(json.dumps([now - WINDOW - 1] * 3 + [now - 10]))
        assert start("darwin").returncode == 1 and not calls.exists()
        assert len(json.loads(record.read_text())) == 2
        # 4. Linux: install does nothing, so a failed start neither counts nor notifies.
        record.unlink()
        assert start("linux").returncode == 1 and not record.exists() and not calls.exists()
        assert install("linux") is False and sys.excepthook is sys.__excepthook__
    print("Start limit: all checks passed.")


if __name__ == "__main__":
    if sys.argv[1:] != ["--check"]:
        sys.exit("Usage: python3 start_limit.py --check")
    check()
