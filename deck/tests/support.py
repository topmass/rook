"""Shared test helpers: the package on sys.path, Rook's phone stand-in, a small Ogg file, and waiting on a condition.

Nothing here plays a sound, opens a microphone or touches a real controller, and nothing reaches beyond 127.0.0.1.
"""

import asyncio
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
ROOK = Path(os.environ.get("ROOK_DIR") or Path.home() / "src" / "rook")
STANDIN = ROOK / "phone" / "standin.py"

log = logging.getLogger("rook-deck-tests")
log.addHandler(logging.NullHandler())
logging.getLogger("asyncio").setLevel(logging.ERROR)  # IsolatedAsyncioTestCase's debug mode reports slow steps.


def load_standin():
    """phone/standin.py from Rook's checkout, imported as a module so a test can drive its fake."""
    if not STANDIN.is_file():
        raise FileNotFoundError(f"Rook's phone stand-in is not at {STANDIN}; set ROOK_DIR")
    spec = importlib.util.spec_from_file_location("rook_standin", STANDIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def has(program: str) -> bool:
    return shutil.which(program) is not None


def make_ogg(seconds: float = 1.0) -> bytes:
    """A short Ogg/Opus tone made with ffmpeg (or GStreamer when ffmpeg is missing)."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "tone.ogg")
        if has("ffmpeg"):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                            "-ac", "1", "-c:a", "libopus", "-b:a", "32k", path], check=True)
        else:
            subprocess.run(["gst-launch-1.0", "-q", "audiotestsrc", f"num-buffers={int(seconds * 100)}",
                            "samplesperbuffer=480", "!", "audioconvert", "!", "opusenc", "!", "oggmux", "!",
                            "filesink", f"location={path}"], check=True)
        return Path(path).read_bytes()


async def until(condition, timeout: float = 8.0, step: float = 0.02, what: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        await asyncio.sleep(step)
    raise AssertionError(f"timed out waiting for {what}")


class Events:
    """Collects what the backend would send the frontend with decky.emit."""

    def __init__(self):
        self.items = []

    def __call__(self, *args):
        event = args[-1]
        self.items.append(event)

    def of(self, kind):
        return [e for e in self.items if e.get("type") == kind]


class FakeRecorder:
    """Stands in for the microphone: start/stop hand back a fixed recording."""

    def __init__(self, data: bytes, seconds: float = 1.2, content_type: str = "audio/ogg"):
        self.data, self.seconds, self.content_type = data, seconds, content_type
        self.recording = False
        self.starts = 0

    async def start(self):
        self.recording = True
        self.starts += 1

    async def stop(self):
        from rook_deck.audio import Recording
        if not self.recording:
            return None
        self.recording = False
        return Recording(self.data, self.content_type, self.seconds)

    async def cancel(self):
        self.recording = False


class FakePlayer:
    """Stands in for the speaker: keeps every clip it was given, and plays each for a short while."""

    def __init__(self, seconds: float = 0.05):
        self.seconds = seconds
        self.clips = []
        self.stopped = False
        self._stop = asyncio.Event()

    async def play(self, data, content_type):
        self.stopped = False
        self._stop = asyncio.Event()
        self.clips.append((content_type, data))
        try:
            await asyncio.wait_for(self._stop.wait(), self.seconds)
            return False
        except asyncio.TimeoutError:
            return True

    async def stop(self):
        self.stopped = True
        self._stop.set()
