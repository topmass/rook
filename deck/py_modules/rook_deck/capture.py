"""Frames of the game, from gamescope's PipeWire video stream, cropped and scaled on the Deck for Rook's WoW mode.

gamescope publishes what it composites for the focused app as a PipeWire stream named "gamescope", class Video/Source,
in BGRx or NV12, at the output size (gamescope src/pipewire.cpp: pw_stream_new(core, "gamescope", {media.class:
Video/Source}), s_nOutputWidth = g_nOutputWidth). Steamcord captures Game Mode the same way, a pipewiresrc on that
node, "the only path that works in Game Mode" (github.com/Necrosiak/Steamcord, defaults/gst_camera.py).

Rook polls a strip about 1200x24 once a second and must have an answer within a second, and a one-shot gst-launch
spends most of that starting up and negotiating. So one pipeline stays warm while Rook polls:

    pipewiresrc target-object=gamescope ! videorate max-rate=2 ! videoconvert ! video/x-raw,format=RGB ! fdsink fd=N

It streams raw RGB frames into a pipe, at most two a second, and only the newest frame is kept. gst-launch -v prints
the negotiated caps, which give the frame size. The pipeline stops after IDLE_SECONDS with no request, because a
PipeWire consumer is not free for gamescope: Steamcord measured a second consumer of the gamescope node starving it of
buffers (main.py `_snapshot_once`), and every consumer makes gamescope paint an extra copy. It stops with SIGINT and a
short wait, never a bare kill mid-frame: Steamcord saw gamescope 3.16 crash when a client vanished while it painted.

JPEG comes from libturbojpeg through ctypes (Arch's libjpeg-turbo, which SteamOS ships, includes it), else from a
one-off gst-launch with jpegenc. PPM is written here.
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import os
import re
import shlex
import signal
import time
from dataclasses import dataclass

from . import env as envmod

IDLE_SECONDS = 20.0
FRESH_SECONDS = 1.5  # A frame older than this is stale: wait for the next one.
FIRST_FRAME_SECONDS = 0.9  # How long a request may wait for the first frame of a cold pipeline.
RESTART_SECONDS = 3.0  # A pipeline that died (no gamescope node yet) is not started again sooner than this.
# gst-launch -v prints each pad's caps; the fdsink's sink pad carries what reaches the pipe. Field order varies.
SINK_CAPS_RE = re.compile(r"GstFdSink:[^ ]*\.GstPad:sink: caps = (video/x-raw.*)$")
WIDTH_RE, HEIGHT_RE = re.compile(r"width=\(int\)(\d+)"), re.compile(r"height=\(int\)(\d+)")
SOURCE = "pipewiresrc target-object=gamescope do-timestamp=true"
SOURCE_OLD = "pipewiresrc path={node} do-timestamp=true"  # pipewiresrc before 1.22 has no target-object.


@dataclass
class Frame:
    width: int
    height: int
    rgb: bytes
    at: float


class CaptureError(Exception):
    pass


def crop_scale(frame: Frame, x: int, y: int, w: int, h: int, scale: float) -> tuple[int, int, bytes]:
    """A region of the frame, clipped to it, shrunk by scale (<= 1) with nearest-neighbour sampling, which keeps
    WoWFriend's strip colours exact. Returns (width, height, RGB bytes)."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.width, x + w), min(frame.height, y + h)
    if x1 <= x0 or y1 <= y0:
        raise CaptureError("the region is outside the game's picture")
    cw, ch = x1 - x0, y1 - y0
    stride = frame.width * 3
    rows = [frame.rgb[(y0 + r) * stride + x0 * 3:(y0 + r) * stride + x1 * 3] for r in range(ch)]
    if scale >= 1:
        return cw, ch, b"".join(rows)
    ow, oh = max(1, int(cw * scale)), max(1, int(ch * scale))
    cols = [min(cw - 1, int((i + 0.5) * cw / ow)) for i in range(ow)]
    out = bytearray()
    for j in range(oh):
        row = memoryview(rows[min(ch - 1, int((j + 0.5) * ch / oh))])
        out += b"".join(row[c * 3:c * 3 + 3] for c in cols)
    return ow, oh, bytes(out)


def ppm(width: int, height: int, rgb: bytes) -> bytes:
    return b"P6\n%d %d\n255\n" % (width, height) + rgb


class TurboJpeg:
    """libturbojpeg's tjCompress2 through ctypes. tj handles and buffers are plain pointers, so no struct layout
    matters here (unlike libjpeg's own API, whose struct sizes change between versions)."""

    TJPF_RGB, TJSAMP_420, TJFLAG_FASTDCT = 0, 2, 2048

    def __init__(self):
        lib = None
        for name in ("libturbojpeg.so.0", ctypes.util.find_library("turbojpeg")):
            if name:
                try:
                    lib = ctypes.CDLL(name)
                    break
                except OSError:
                    continue
        if lib is None:
            raise OSError("libturbojpeg is not on this system")
        self.lib = lib
        lib.tjInitCompress.restype = ctypes.c_void_p
        lib.tjCompress2.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_ulong),
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.tjFree.argtypes = [ctypes.c_void_p]
        lib.tjDestroy.argtypes = [ctypes.c_void_p]

    def encode(self, width: int, height: int, rgb: bytes, quality: int = 85) -> bytes:
        handle = self.lib.tjInitCompress()
        if not handle:
            raise CaptureError("tjInitCompress failed")
        out, size = ctypes.c_void_p(), ctypes.c_ulong(0)
        try:
            if self.lib.tjCompress2(handle, rgb, width, 0, height, self.TJPF_RGB, ctypes.byref(out), ctypes.byref(size),
                                    self.TJSAMP_420, quality, self.TJFLAG_FASTDCT) != 0:
                raise CaptureError("tjCompress2 failed")
            return ctypes.string_at(out, size.value)
        finally:
            if out:
                self.lib.tjFree(out)
            self.lib.tjDestroy(handle)


async def gst_jpeg(session: envmod.Session, width: int, height: int, rgb: bytes) -> bytes:
    """The fallback JPEG encoder: one gst-launch with rawvideoparse and jpegenc."""
    gst = envmod.which("gst-launch-1.0", session.child_env())
    if not gst:
        raise CaptureError("no JPEG encoder: neither libturbojpeg nor gst-launch-1.0")
    argv = [gst, "-q", "fdsrc", "fd=0", "!", "rawvideoparse", f"width={width}", f"height={height}", "format=rgb",
            "framerate=1/1", "!", "videoconvert", "!", "jpegenc", "quality=85", "!", "fdsink", "fd=1"]
    proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL, env=session.child_env(),
                                                **session.child_kwargs())
    out, _ = await asyncio.wait_for(proc.communicate(rgb), 5)
    if proc.returncode != 0 or not out:
        raise CaptureError("jpegenc failed")
    return out


class Encoder:
    def __init__(self, session: envmod.Session):
        self.session = session
        try:
            self.turbo: TurboJpeg | None = TurboJpeg()
        except OSError:
            self.turbo = None

    async def jpeg(self, width: int, height: int, rgb: bytes) -> bytes:
        if self.turbo is not None:
            return await asyncio.to_thread(self.turbo.encode, width, height, rgb)
        return await gst_jpeg(self.session, width, height, rgb)


class Grabber:
    """The warm pipeline and its newest frame. source is the gst source description; tests give videotestsrc."""

    def __init__(self, session: envmod.Session, log=None, source: str | None = None):
        self.session = session
        self.log = log
        self.source = source
        self.proc: asyncio.subprocess.Process | None = None
        self.frame: Frame | None = None
        self.size: tuple[int, int] | None = None
        self.last_request = 0.0
        self.new_frame = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._idle: asyncio.Task | None = None
        self._read_fd: int | None = None
        self.error: str | None = None
        self.started_at = -RESTART_SECONDS

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def _source(self) -> str:
        if self.source:
            return self.source
        inspect = envmod.which("gst-inspect-1.0", self.session.child_env())
        if inspect:
            proc = await asyncio.create_subprocess_exec(
                inspect, "pipewiresrc", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                env=self.session.child_env(), **self.session.child_kwargs())
            out, _ = await proc.communicate()
            if b"target-object" not in out:
                node = await self._node_id()
                if node is not None:
                    return SOURCE_OLD.format(node=node)
        return SOURCE

    async def _node_id(self) -> int | None:
        """The gamescope node's id from pw-dump, for an old pipewiresrc that only takes path=."""
        import json
        dump = envmod.which("pw-dump", self.session.child_env())
        if not dump:
            return None
        proc = await asyncio.create_subprocess_exec(dump, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL, env=self.session.child_env(),
                                                    **self.session.child_kwargs())
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), 5)  # A wedged PipeWire can hang pw-dump (Steamcord).
            nodes = json.loads(out or b"[]")
        except (asyncio.TimeoutError, ValueError):
            proc.kill()
            return None
        for node in nodes:
            props = (node.get("info") or {}).get("props") or {}
            if props.get("node.name") == "gamescope" and str(props.get("media.class", "")).startswith("Video/"):
                return node.get("id")
        return None

    async def start(self) -> None:
        if self.running:
            return
        gst = envmod.which("gst-launch-1.0", self.session.child_env())
        if not gst:
            raise CaptureError("gst-launch-1.0 is not on this system")
        source = await self._source()
        read_fd, write_fd = os.pipe()
        os.set_inheritable(write_fd, True)
        # The frames go to the pipe's own descriptor number, passed to the child as is, so stdout stays free for
        # -v's caps lines.
        description = (f"{source} ! videorate max-rate=2 ! videoconvert ! video/x-raw,format=RGB "
                       f"! fdsink fd={write_fd} sync=false")
        argv = [gst, "-v", "-e", *shlex.split(description)]
        child_env = self.session.child_env()
        kwargs = self.session.child_kwargs()

        try:
            self.proc = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=child_env, pass_fds=(write_fd,),
                start_new_session=True, **kwargs)
        finally:
            os.close(write_fd)
        self._read_fd = read_fd
        self.size, self.frame, self.error = None, None, None
        loop = asyncio.get_running_loop()
        self._tasks = [loop.create_task(self._read_caps(self.proc)), loop.create_task(self._read_frames(read_fd)),
                       loop.create_task(self._read_errors(self.proc))]
        if self._idle is None or self._idle.done():
            self._idle = loop.create_task(self._idle_watch())
        if self.log:
            self.log.info(f"capture pipeline started: {description}")

    async def _read_caps(self, proc) -> None:
        while True:
            line = await proc.stdout.readline()
            if not line:
                return
            found = SINK_CAPS_RE.search(line.decode(errors="replace").rstrip())
            width = WIDTH_RE.search(found[1]) if found else None
            height = HEIGHT_RE.search(found[1]) if found else None
            if width and height:
                size = (int(width[1]), int(height[1]))
                if self.size is not None and size != self.size:
                    # A new size mid-stream (the game changed resolution): start again so frames and size agree.
                    asyncio.get_running_loop().create_task(self.restart())
                    return
                self.size = size

    async def _read_errors(self, proc) -> None:
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            text = line.decode(errors="replace").strip()
            if text and ("ERROR" in text or "error" in text):
                self.error = text[-300:]

    async def _read_frames(self, fd: int) -> None:
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(limit=1 << 24)
        transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(fd, "rb", 0))
        try:
            while True:
                while self.size is None:
                    await asyncio.sleep(0.01)
                    if not self.running and reader.at_eof():
                        return
                width, height = self.size
                try:
                    data = await reader.readexactly(width * height * 3)
                except asyncio.IncompleteReadError:
                    return
                self.frame = Frame(width, height, data, time.monotonic())
                self.new_frame.set()
                self.new_frame = asyncio.Event()
        finally:
            transport.close()

    async def _idle_watch(self) -> None:
        while True:
            await asyncio.sleep(2)
            if not self.running:
                return
            if time.monotonic() - self.last_request > IDLE_SECONDS:
                await self.stop()
                return

    async def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None and proc.returncode is None:
            try:
                proc.send_signal(signal.SIGINT)  # -e: end-of-stream first, so gamescope sees a clean goodbye.
                await asyncio.wait_for(proc.wait(), 2)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
        for task in self._tasks:
            task.cancel()
        self._tasks = []
        self.frame = None
        self.size = None
        if self.log:
            self.log.info("capture pipeline stopped")

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    def touch(self) -> None:
        """Note a request, so the pipeline stays warm (and starts, from the caller, when it is not running)."""
        self.last_request = time.monotonic()

    async def latest(self, wait: float = FIRST_FRAME_SECONDS) -> Frame | None:
        """The newest fresh frame, starting the pipeline when needed. None when no frame comes in time."""
        self.touch()
        if not self.running:
            if time.monotonic() - self.started_at < RESTART_SECONDS:
                return None  # It just died: answer 503 at once rather than start gst on every poll.
            self.started_at = time.monotonic()
            await self.start()
        frame = self.frame
        if frame is not None and time.monotonic() - frame.at <= FRESH_SECONDS:
            return frame
        try:
            await asyncio.wait_for(self.new_frame.wait(), wait)
        except asyncio.TimeoutError:
            return None
        return self.frame


class Capture:
    """/capture's logic: a region of the newest frame as PPM or JPEG."""

    def __init__(self, grabber: Grabber, encoder: Encoder):
        self.grabber = grabber
        self.encoder = encoder

    async def region(self, x: int, y: int, w: int, h: int, scale: float, kind: str) -> tuple[str, bytes] | None:
        frame = await self.grabber.latest()
        if frame is None:
            return None
        width, height, rgb = await asyncio.to_thread(crop_scale, frame, x, y, w, h, scale)
        if kind == "ppm":
            return "image/x-portable-pixmap", ppm(width, height, rgb)
        return "image/jpeg", await self.encoder.jpeg(width, height, rgb)

    def size(self) -> tuple[int, int] | None:
        frame = self.grabber.frame
        return (frame.width, frame.height) if frame else None
