"""The overlay's link to the stage host (stage/host.py), which draws diagrams and the answer panel when the stage
setting is on. The host starts when one first shows and stays warm for a minute after the last one closes. Then it
asks to go: it says which message it saw last, and the link lets it quit only when nothing newer is on its way, so a
show sent at that moment is never lost. When the host cannot start, is not ready in time, or dies, the link starts a
fresh one once and sends it what was showing. When that fails too, the overlay draws that scene or panel itself, and the
stage rests for PAUSE_SECONDS before it tries again.

    python3 desktop/stage_link.py --check     start the host by its exact launch command, from another folder, on a
                                              private X display: shows, a show sent as the host idles, idle exits,
                                              a crash and its retry, a double failure, the pause and the next try
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk  # noqa: E402

READY_SECONDS = 8  # A cold start is ready in about a second; past this the host counts as failed.
PAUSE_SECONDS = 60  # After a retry failed too, the overlay draws for this long before the stage tries again.
SHOWING = ("scene", "panel", "history")


class StageLink:
    def __init__(self, on_event, command=None):
        """on_event(data) gets the host's events (shown, pick, history, copy, link, close) and {"event": "failed"}
        when a show could not be drawn on the stage, so the overlay draws it."""
        self.on_event = on_event
        self.command = command
        self.pause_seconds = PAUSE_SECONDS
        self.proc = None
        self.ready = False
        self.failed = None  # Why the stage last failed; it rests until resting_until.
        self.resting_until = 0.0
        self.context = {}
        self.showing = []  # What shows now: the scene, panel or card message and any step after it, to send again.
        self._queue = []
        self._buffer = b""
        self._seq = 0  # The number of the last message written to this host.
        self._retried = False

    def usable(self):
        """Whether the stage can draw now: the system has the host, and it is not resting after a failure."""
        if self.failed is not None and time.monotonic() >= self.resting_until:
            self.failed, self._retried = None, False
        return self.failed is None and (self.command or desk.stage_command()) is not None

    def running(self):
        return self.proc is not None

    def set(self, **context):
        """Theme, mode, monitor and top: kept, sent when they change, and sent first to a host that starts later."""
        changed = {key: value for key, value in context.items() if self.context.get(key) != value}
        if changed:
            self.context.update(changed)
            if self.proc is not None:
                self._send(changed)

    def send(self, message):
        """Send a message, starting the host when it is not running. False when the stage cannot draw."""
        if not self.usable():
            return False
        if any(key in message for key in SHOWING):
            self.showing = [message]
        elif "step" in message and self.showing:
            self.showing = [self.showing[0], message]
        if self.proc is None and not self._start():
            return False
        self._send(message)
        return True

    def hide(self):
        """Hide whatever the host shows; a host that is not running shows nothing."""
        self.showing = []
        if self.proc is not None:
            self._send({"hide": True})

    def close(self):
        if self.proc is not None:
            try:
                self.proc.stdin.close()  # The host quits when its input ends.
            except OSError:
                pass

    def _start(self):
        from gi.repository import GLib
        argv = self.command or desk.stage_command()
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    cwd="/", start_new_session=True)
        except OSError as error:
            return self._failure(f"the stage host could not start: {error}")
        self.proc, self.ready, self._buffer, self._seq = proc, False, b"", 0
        self._queue = [dict(self.context)] if self.context else []
        GLib.io_add_watch(proc.stdout.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
                          lambda fd, cond: self._readable(proc, fd, cond))
        GLib.child_watch_add(GLib.PRIORITY_DEFAULT, proc.pid, lambda _pid, status: self._exited(proc, status))
        GLib.timeout_add_seconds(READY_SECONDS, lambda: self._late(proc))
        return True

    def _send(self, message):
        if not self.ready:
            self._queue.append(message)
            return
        self._seq += 1
        try:
            self.proc.stdin.write((json.dumps({**message, "seq": self._seq}) + "\n").encode())
            self.proc.stdin.flush()
        except (OSError, ValueError) as error:
            self._lost(self.proc, f"the stage host stopped reading: {error}")

    def _readable(self, proc, fd, cond):
        if proc is not self.proc:
            return False
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            chunk = b""
        if not chunk:
            return False
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict) or proc is not self.proc:
                continue
            if data.get("event") == "ready":
                self.ready, self._retried = True, False
                queued, self._queue = self._queue, []
                for message in queued:
                    self._send(message)
            elif data.get("event") == "idle":
                if data.get("seq") == self._seq and not self.showing:
                    # Nothing newer is on its way: the host may go, and the next show starts a fresh one.
                    self._send({"quit": True})
                    self.proc, self.ready = None, False
                # Else a newer message is on its way, and the host stays for it.
            else:
                self.on_event(data)
        return True

    def _late(self, proc):
        if proc is self.proc and not self.ready:
            self._lost(proc, f"the stage host was not ready in {READY_SECONDS} s")
        return False

    def _exited(self, proc, status):
        if proc is self.proc:
            self._lost(proc, f"the stage host stopped (status {status})")

    def _lost(self, proc, why):
        """This host is gone or useless. Start a fresh one once and send it what showed; past that, fall back."""
        if proc is not self.proc:
            return
        self.proc, self.ready = None, False
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # The host and its web helpers, which share its session.
        except OSError:
            pass
        if not self.showing:  # Nothing to show: the next show starts a fresh host.
            print(f"stage: {why}", file=sys.stderr, flush=True)
            return
        if not self._retried:
            self._retried = True
            print(f"stage: {why}; starting it again", file=sys.stderr, flush=True)
            showing = list(self.showing)
            if self._start():
                for message in showing:
                    self._send(message)
            return
        self._failure(why)

    def _failure(self, why):
        """The stage cannot show this now: the overlay draws it, and the stage rests a while."""
        self.failed, self.resting_until = why, time.monotonic() + self.pause_seconds
        self.showing = []
        print(f"stage: {why}; the overlay draws instead, and the stage rests {self.pause_seconds:g} s", file=sys.stderr,
              flush=True)
        self.on_event({"event": "failed", "error": why})
        return False


def _check():
    """Start the host by its exact launch command from another folder, as the overlay does, on a private X display."""
    import select
    import shutil
    import tempfile
    from gi.repository import GLib
    command = desk.stage_command()
    host = Path(__file__).resolve().parent.parent / "stage" / "host.py"
    if command is None:  # This system has no layer-shell library: prove the same launch on the bare host command.
        command = [desk.python_exe(), str(host)]
    if os.environ.get("ROOK_STAGE_CHECK_DISPLAY") != "1":
        # The check itself runs again under xvfb-run, so nothing shows on the user's screens. Its scratch is removed only
        # after every host and web helper it started has ended (the inner run waits for them).
        xvfb = shutil.which("xvfb-run")
        assert xvfb, "The check needs xvfb-run for a private display."
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
        scratch = tempfile.mkdtemp(prefix="rook-stage-link-")
        try:
            # No shader cache: nothing of the check writes to scratch late, after its processes have gone.
            env.update(ROOK_STAGE_CHECK_DISPLAY="1", ROOK_STAGE_IDLE="2", GDK_BACKEND="x11", MESA_SHADER_CACHE_DISABLE="true",
                       XDG_CACHE_HOME=str(Path(scratch) / "cache"), XDG_DATA_HOME=str(Path(scratch) / "data"))
            done = subprocess.run([xvfb, "-a", sys.executable, str(Path(__file__).resolve()), "--check"], env=env,
                                  cwd=scratch, timeout=120)
        finally:
            for _ in range(40):  # A late write may land as it goes: try again for up to ten seconds.
                shutil.rmtree(scratch, ignore_errors=True)
                if not os.path.exists(scratch):
                    break
                time.sleep(0.25)
        sys.exit(done.returncode)
    events, kids = [], set()
    loop = GLib.MainLoop()
    GLib.timeout_add(100, lambda: True)  # A tick, so a wait below wakes to see its own deadline.
    link = StageLink(events.append, command)
    link.pause_seconds = 1
    scene = json.loads((host.parent / "scenes" / "hub.json").read_text())

    def wait(test, seconds=20):
        end = time.monotonic() + seconds
        while not test() and time.monotonic() < end:
            loop.get_context().iteration(True)
            if link.proc is not None:
                kids.update(pid for pid, _ in _descendants(link.proc.pid))
        assert test(), events

    def shown(sid):
        return lambda: any(e.get("event") == "shown" and e.get("id") == sid for e in events)

    try:
        link.set(theme="devs", mode="dark", monitor=[0, 0, 1600, 1000], top=300)
        started = time.monotonic()
        assert link.send({"scene": scene, "id": "c1"})
        wait(shown("c1"))
        ready_s = time.monotonic() - started
        assert {"event": "shown", "id": "c1", "ok": True} in events, events
        link.send({"step": 2})
        link.send({"scene": {"title": "broken", "layout": "row"}, "id": "c2"})
        wait(shown("c2"))
        bad = next(e for e in events if e.get("id") == "c2")
        assert bad["ok"] is False and bad["errors"], bad

        # The race: the host has said it is idle, and a scene goes out before the link has read that.
        link.hide()
        first = link.proc
        end = time.monotonic() + 10  # No main loop here, so the idle line stays unread until the scene is out.
        while not select.select([first.stdout], [], [], 0.1)[0] and time.monotonic() < end:
            pass
        assert link.send({"scene": scene, "id": "c3"})
        wait(shown("c3"))
        assert link.proc is first and link.failed is None, "a show sent as the host idled was lost or failed"

        # A plain idle: the host goes, which is no failure, and the next show starts a fresh one.
        link.hide()
        wait(lambda: not link.running())
        wait(lambda: first.poll() is not None)
        assert link.failed is None and link.usable() and "failed" not in [e.get("event") for e in events]
        assert link.send({"panel": {"text": "Started again."}, "index": 0, "count": 1})
        wait(lambda: link.ready)

        # The web process crashes while a scene shows: the host ends, one fresh host starts, and the scene shows again
        # there, with no fallback.
        link.send({"scene": scene, "id": "c4"})
        wait(shown("c4"))
        crashed = link.proc
        web = [pid for pid, name in _descendants(crashed.pid) if name.startswith("WebKitWebProces")]
        assert web, _descendants(crashed.pid)
        os.kill(web[0], signal.SIGKILL)
        wait(lambda: link.proc is not None and link.proc is not crashed and link.ready)
        wait(lambda: sum(e.get("id") == "c4" for e in events) == 2)
        assert "failed" not in [e.get("event") for e in events], events

        # A second failure in a row: the overlay draws (one failed event), the stage rests, then tries again.
        before = link.proc
        os.killpg(before.pid, signal.SIGKILL)
        wait(lambda: link.proc is not None and link.proc is not before)
        assert not link.ready
        os.killpg(link.proc.pid, signal.SIGKILL)  # The retry dies too, before it is ready.
        wait(lambda: link.failed is not None)
        assert [e.get("event") for e in events].count("failed") == 1 and not link.usable()
        assert not link.send({"scene": scene, "id": "c5"})
        time.sleep(1.1)
        assert link.usable() and link.send({"scene": scene, "id": "c6"})
        wait(shown("c6"))
    finally:
        # End every host and web helper this check started, and wait for them, before the scratch goes.
        if link.proc is not None:
            kids.update(pid for pid, _ in _descendants(link.proc.pid))
        for pid in kids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        end = time.monotonic() + 10
        while time.monotonic() < end and any(Path(f"/proc/{pid}").exists() and _state(pid) != "Z" for pid in kids):
            time.sleep(0.1)
    print(f"Stage link: all checks passed (ready and answered in {ready_s:.1f} s; the idle race, a retry, a "
          f"fallback and the next try).")


def _state(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return None


def _descendants(root):
    """(pid, name) of root and every process under it, from /proc."""
    parent, names = {}, {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                fields = dict(line.split(":", 1) for line in Path(f"/proc/{entry}/status").read_text().splitlines()
                              if ":" in line)
            except OSError:
                continue
            parent[int(entry)] = int(fields.get("PPid", "0").strip() or 0)
            names[int(entry)] = fields.get("Name", "").strip()
    found, todo = [], [root]
    while todo:
        pid = todo.pop()
        found.append((pid, names.get(pid, "")))
        todo += [child for child, up in parent.items() if up == pid]
    return found


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        _check()
    else:
        sys.exit(__doc__)
