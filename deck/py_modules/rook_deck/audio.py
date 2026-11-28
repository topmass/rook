"""The microphone and the speaker: record a request as Ogg/Opus, and play Rook's speech.

Recording. SteamOS ships GStreamer with the PipeWire plugin and the Opus encoder (Steamcord checks for exactly this,
"present on Bazzite/SteamOS": github.com/Necrosiak/Steamcord, main.py `_gst_python_hint`), and Decky Recorder builds its
clips with gst-launch-1.0 on the same system (github.com/marissa999/decky-recorder, main.py). So the first choice is
one gst-launch-1.0 process per recording:

    pipewiresrc ! audio/x-raw ! audioconvert ! audioresample ! audio/x-raw,channels=1,rate=48000
        ! opusenc bitrate=32000 ! oggmux ! fdsink fd=1

It writes Ogg/Opus to its stdout as it records, so nothing waits on a file, and the size cap is checked live. It runs
with -e: SIGINT then sends end-of-stream through the pipeline, so oggmux writes its last page and the file is whole.
32 kbit/s mono Opus is what the phone app records (phone/app.js `audioBitsPerSecond: 32000`).

The fallback is pw-record from PipeWire itself, which every SteamOS has. It writes through libsndfile, which picks the
container from the file name: a .ogg file is Ogg Vorbis. Rook takes audio/ogg either way (desktop/server.py
AUDIO_UPLOAD_TYPES), and its speech-to-text reads the file with its own decoder. SIGINT makes pw-record close the file.

Playback. pw-play plays WAV, Ogg and MP3 through libsndfile; GStreamer's decodebin covers anything else (audio/mp4).
"""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import tempfile
import time
from dataclasses import dataclass
from typing import Callable

from . import env as envmod

RECORD_MAX_SECONDS = 290  # Under five minutes, as the phone app: about 1.2 MB of Opus, well inside Rook's 4 MiB.
RECORD_MAX_BYTES = int(3.5 * 1024 * 1024)
RECORD_MIN_SECONDS = 0.5
STOP_SECONDS = 3.0  # How long a recorder may take to finish its file after SIGINT before it is killed.
GST_SOURCES = ("pipewiresrc ! audio/x-raw", "pulsesrc", "autoaudiosrc")
GST_ENCODE = ("audioconvert ! audioresample ! audio/x-raw,channels=1,rate=48000 ! opusenc bitrate=32000 "
              "! oggmux ! fdsink fd=1")
SPEECH_SUFFIX = {"audio/wav": ".wav", "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a"}


@dataclass
class Recording:
    data: bytes
    content_type: str
    seconds: float


class AudioError(RuntimeError):
    """A recording or playback could not start, with a sentence for the user."""


async def _gst_has(gst_inspect: str | None, elements: tuple[str, ...], session) -> bool:
    if not gst_inspect:
        return False
    for element in elements:
        proc = await asyncio.create_subprocess_exec(
            gst_inspect, "--exists", element, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            env=session.child_env(), **session.child_kwargs())
        if await proc.wait() != 0:
            return False
    return True


class Recorder:
    """One recording at a time. start() opens the microphone; stop() returns the whole recording."""

    def __init__(self, session: envmod.Session, log=None, *, gst_source: str | None = None,
                 backends: tuple[str, ...] = ("gst", "pw-record"), on_limit: Callable[[], None] | None = None):
        self.session = session
        self.log = log
        self.gst_source = gst_source  # A test gives audiotestsrc here, so no microphone is needed.
        self.backends = backends
        self.on_limit = on_limit  # Told when the recording hits its size or time cap and stops by itself.
        self.proc: asyncio.subprocess.Process | None = None
        self.backend: str | None = None
        self.started_at = 0.0
        self.buffer = bytearray()
        self.file: str | None = None
        self._pump: asyncio.Task | None = None
        self._cap: asyncio.TimerHandle | None = None
        self._capable: dict[str, bool] = {}

    @property
    def recording(self) -> bool:
        return self.proc is not None

    async def available(self) -> dict[str, bool]:
        """Which recorders this system has. Checked once, then remembered."""
        if not self._capable:
            child = self.session.child_env()
            gst = envmod.which("gst-launch-1.0", child)
            inspect = envmod.which("gst-inspect-1.0", child)
            sources = ("audiotestsrc",) if self.gst_source else ()
            self._capable["gst"] = bool(gst) and await _gst_has(
                inspect, ("opusenc", "oggmux", "audioconvert", "audioresample", "fdsink", *sources), self.session)
            self._capable["pw-record"] = bool(envmod.which("pw-record", child))
        return dict(self._capable)

    async def _start_gst(self) -> None:
        gst = envmod.which("gst-launch-1.0", self.session.child_env())
        sources = (self.gst_source,) if self.gst_source else GST_SOURCES
        last_error = "no source"
        for source in sources:
            argv = [gst, "-q", "-e", *shlex.split(f"{source} ! {GST_ENCODE}")]
            proc = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=self.session.child_env(), start_new_session=True,
                **self.session.child_kwargs())
            # A source that cannot open (no such element, no PipeWire) makes gst-launch exit at once.
            try:
                await asyncio.wait_for(proc.wait(), 0.25)
            except asyncio.TimeoutError:
                self.proc, self.backend = proc, "gst"
                return
            err = (await proc.stderr.read()).decode(errors="replace").strip()
            last_error = err.splitlines()[-1] if err else f"exit {proc.returncode}"
            if self.log:
                self.log.warning(f"recorder source {source!r} failed: {last_error}")
        raise AudioError(f"The microphone did not start ({last_error}).")

    async def _start_pw_record(self) -> None:
        pw = envmod.which("pw-record", self.session.child_env())
        fd, self.file = tempfile.mkstemp(prefix="rook-rec-", suffix=".ogg")
        os.close(fd)
        kwargs = self.session.child_kwargs()
        if kwargs:  # The helper runs as the Deck user and writes this file.
            os.chown(self.file, self.session.uid, self.session.gid)
        proc = await asyncio.create_subprocess_exec(
            pw, "--rate", "48000", "--channels", "1", self.file, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=self.session.child_env(),
            start_new_session=True, **kwargs)
        try:
            await asyncio.wait_for(proc.wait(), 0.25)
        except asyncio.TimeoutError:
            self.proc, self.backend = proc, "pw-record"
            return
        err = (await proc.stderr.read()).decode(errors="replace").strip()
        os.unlink(self.file)
        self.file = None
        raise AudioError(f"The microphone did not start ({err.splitlines()[-1] if err else proc.returncode}).")

    async def start(self) -> None:
        if self.proc is not None:
            return
        capable = await self.available()
        errors = []
        for backend in self.backends:
            if not capable.get(backend):
                continue
            try:
                await (self._start_gst() if backend == "gst" else self._start_pw_record())
                break
            except (AudioError, OSError) as exc:
                errors.append(str(exc))
        if self.proc is None:
            raise AudioError(errors[-1] if errors else
                             "This Deck has neither GStreamer's Opus encoder nor pw-record, so it cannot record.")
        self.buffer = bytearray()
        self.started_at = time.monotonic()
        if self.backend == "gst":
            self._pump = asyncio.get_running_loop().create_task(self._read_stdout(self.proc))
        self._cap = asyncio.get_running_loop().call_later(RECORD_MAX_SECONDS, self._limit)

    def _limit(self) -> None:
        if self.on_limit:
            self.on_limit()

    async def _read_stdout(self, proc) -> None:
        while True:
            data = await proc.stdout.read(65536)
            if not data:
                return
            self.buffer += data
            if len(self.buffer) > RECORD_MAX_BYTES:
                self._limit()
                return

    async def _end(self, proc) -> None:
        """SIGINT, then wait for the file to finish; a recorder that hangs is killed."""
        try:
            proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), STOP_SECONDS)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()

    async def stop(self) -> Recording | None:
        """Finish the recording and return it, or None when there was none."""
        proc, backend = self.proc, self.backend
        if proc is None:
            return None
        self.proc = None
        if self._cap:
            self._cap.cancel()
        seconds = time.monotonic() - self.started_at
        await self._end(proc)
        if backend == "gst":
            if self._pump:
                try:
                    await asyncio.wait_for(self._pump, 1.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
            data = bytes(self.buffer[:RECORD_MAX_BYTES])
        else:
            try:
                with open(self.file, "rb") as source:
                    data = source.read(RECORD_MAX_BYTES)
            except OSError:
                data = b""
            finally:
                os.unlink(self.file)
                self.file = None
        self.buffer = bytearray()
        return Recording(data, "audio/ogg", seconds)

    async def cancel(self) -> None:
        """Drop the recording: nothing is kept."""
        proc = self.proc
        self.proc = None
        if self._cap:
            self._cap.cancel()
        if proc is not None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
        if self._pump:
            self._pump.cancel()
        if self.file:
            try:
                os.unlink(self.file)
            except OSError:
                pass
            self.file = None
        self.buffer = bytearray()


class Player:
    """Plays one clip at a time. play() returns when the clip ends or stop() cuts it."""

    def __init__(self, session: envmod.Session, log=None, *, gst_sink: str = "pipewiresink",
                 backends: tuple[str, ...] = ("pw-play", "gst")):
        self.session = session
        self.log = log
        self.gst_sink = gst_sink  # A test gives fakesink here, so nothing reaches a speaker.
        self.backends = backends
        self.proc: asyncio.subprocess.Process | None = None
        self.stopped = False

    def _argv(self, backend: str, path: str) -> list[str] | None:
        child = self.session.child_env()
        if backend == "pw-play":
            exe = envmod.which("pw-play", child)
            return [exe, "--media-role", "Communication", path] if exe else None
        exe = envmod.which("gst-launch-1.0", child)
        if not exe:
            return None
        return [exe, "-q", "filesrc", f"location={path}", "!", "decodebin", "!", "audioconvert", "!",
                "audioresample", "!", *shlex.split(self.gst_sink)]

    async def play(self, data: bytes, content_type: str) -> bool:
        """Play a clip. Returns True when it played to its end."""
        self.stopped = False
        suffix = SPEECH_SUFFIX.get(content_type.split(";")[0].strip().lower(), ".bin")
        fd, path = tempfile.mkstemp(prefix="rook-speech-", suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            kwargs = self.session.child_kwargs()
            if kwargs:
                os.chown(path, self.session.uid, self.session.gid)
            backends = self.backends if suffix != ".m4a" else tuple(b for b in self.backends if b == "gst")
            for backend in backends:
                argv = self._argv(backend, path)
                if not argv:
                    continue
                self.proc = await asyncio.create_subprocess_exec(
                    *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE, env=self.session.child_env(), start_new_session=True, **kwargs)
                _, err = await self.proc.communicate()
                code, self.proc = self.proc.returncode, None
                if self.stopped:
                    return False
                if code == 0:
                    return True
                if self.log:
                    self.log.warning(f"{backend} could not play {content_type}: {err.decode(errors='replace')[-200:]}")
            return False
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    async def stop(self) -> None:
        self.stopped = True
        proc = self.proc
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
