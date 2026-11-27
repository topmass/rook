"""Bounded, content-free request timings and local process measurements."""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys
import time


STAGES = ("recognition", "smart_turn", "queue", "agent_first_token", "agent", "tools",
          "tts_queue", "tts_first_pcm", "audio_buffer", "playback")
LOG_BYTES = 2 * 1024 * 1024
SAMPLE_SECONDS = 0.1
MAX_REQUEST_SECONDS = 900
MAX_TRACES = 64


def process_reader():
    """Return a cheap (CPU milliseconds, RSS bytes) reader for the local OS."""
    if sys.platform == "darwin":
        import ctypes
        lib = ctypes.CDLL("/usr/lib/libproc.dylib")
        lib.proc_pid_rusage.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
        ratio = (ctypes.c_uint32 * 2)()
        ctypes.CDLL(None).mach_timebase_info(ctypes.byref(ratio))
        scale = ratio[0] / ratio[1] / 1e6
        # rusage_info_v0 starts with a 16-byte UUID, then uint64 fields.
        usage = (ctypes.c_uint64 * 13)()

        def read(pid):
            if lib.proc_pid_rusage(pid, 0, ctypes.byref(usage)) == 0:
                return (usage[2] + usage[3]) * scale, usage[8]
            return None

        return read
    if sys.platform.startswith("linux"):
        scale = 1000 / os.sysconf("SC_CLK_TCK")
        pages = os.sysconf("SC_PAGE_SIZE")

        def read(pid):
            try:
                fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                return (int(fields[11]) + int(fields[12])) * scale, int(fields[21]) * pages
            except (OSError, ValueError, IndexError):
                return None

        return read
    return lambda _pid: None


class Span:
    def __init__(self, when, sample):
        self.when = when
        self.initial = sample
        self.peak = {}
        self.observe(sample)

    def observe(self, sample):
        for role, (_, _, rss) in sample.items():
            self.peak[role] = max(rss, self.peak.get(role, 0))


class Trace:
    def __init__(self, logger, source, origin):
        self.logger, self.source, self.origin = logger, source, origin
        self.began = time.monotonic()
        self.at = datetime.now(timezone.utc).isoformat()
        self.session = logger.session
        self.turn = None
        self.active, self.stages = {}, {}
        self.first_audio = self.speech_end = None
        self.agent_status = None
        self.audio_status = None
        self.tools, self.audio = set(), set()

    def begin(self, stage, item=None, when=None, cpu=None):
        self.active[stage, item] = Span(time.monotonic() if when is None else when, self.logger.sample(cpu))

    def end(self, stage, item=None, when=None, cpu=None, complete=True):
        span = self.active.pop((stage, item), None)
        if span is None:
            return
        elapsed = max(0, ((time.monotonic() if when is None else when) - span.when) * 1000)
        final = self.logger.sample(cpu)
        span.observe(final)
        row = self.stages.setdefault(stage, {"wall_ms": 0.0, "count": 0, "complete": True, "workers": {}})
        row["wall_ms"] += elapsed
        row["count"] += 1
        row["complete"] &= complete
        for role, peak in span.peak.items():
            first, last = span.initial.get(role), final.get(role)
            stats = row["workers"].setdefault(role, {"cpu_ms": None, "peak_rss_bytes": 0})
            stats["peak_rss_bytes"] = max(stats["peak_rss_bytes"], peak)
            if first and last and first[0] == last[0]:
                stats["cpu_ms"] = (stats["cpu_ms"] or 0) + max(0, last[1] - first[1])

    def observe(self, sample):
        for span in self.active.values():
            span.observe(sample)

    def finish(self, status):
        if self not in self.logger.traces:
            return
        for stage, item in list(self.active):
            self.end(stage, item, complete=False)
        for row in self.stages.values():
            wall = row["wall_ms"]
            for worker in row["workers"].values():
                if worker["cpu_ms"] is not None:
                    worker["cpu_pct"] = round(100 * worker["cpu_ms"] / wall, 1) if wall else None
                    worker["cpu_ms"] = round(worker["cpu_ms"], 2)
            row["wall_ms"] = round(wall, 2)
        self.logger.complete(self, {
            "at": self.at, "level": "info", "event": "request_perf", "session": self.session,
            "turn": self.turn, "source": self.source, "origin": self.origin, "status": status,
            "audio_status": self.audio_status or ("played" if self.speech_end is not None else "none"),
            "input_to_first_audio_ms": self.offset(self.first_audio),
            "input_to_end_of_speech_ms": self.offset(self.speech_end),
            "stages": {stage: self.stages.get(stage) for stage in STAGES},
        })

    def offset(self, when):
        return round((when - self.began) * 1000, 2) if when is not None else None


class PerfLog:
    def __init__(self, path, session, workers, warn):
        self.path, self.session, self.workers, self.warn = path, session, workers, warn
        self.read_process = process_reader()
        self.traces, self.turns, self.audio = set(), {}, {}
        self.timer = None
        self.warned = False

    def sample(self, tts_cpu=None):
        sample = {}
        for role, pid in self.workers().items():
            if pid and (reading := self.read_process(pid)) is not None:
                cpu, rss = reading
                sample[role] = pid, tts_cpu if role == "tts" and tts_cpu is not None else cpu, rss
        return sample

    def tick(self):
        self.timer = None
        now, sample = time.monotonic(), self.sample()
        for trace in tuple(self.traces):
            trace.observe(sample)
            if now - trace.began >= MAX_REQUEST_SECONDS:
                trace.finish("timed_out")
        self.schedule()

    def schedule(self):
        if self.traces and self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(SAMPLE_SECONDS, self.tick)

    def begin(self, source, origin):
        if len(self.traces) >= MAX_TRACES:
            min(self.traces, key=lambda trace: trace.began).finish("capacity")
        trace = Trace(self, source, origin)
        self.traces.add(trace)
        self.schedule()
        return trace

    def dispatch(self, trace, turn):
        if trace not in self.traces:
            return
        trace.end("queue")
        trace.turn = turn
        self.turns[turn] = trace
        trace.begin("agent")
        trace.begin("agent_first_token")

    def agent_message(self, turn, message):
        trace = self.turns.get(turn)
        kind = message.get("type")
        if kind == "user":
            for block in (message.get("message") or {}).get("content", ()):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    token = block.get("tool_use_id")
                    for active in self.turns.values():
                        if token in active.tools:
                            active.tools.discard(token)
                            if not active.tools:
                                active.end("tools")
            return
        if trace is None or message.get("parent_tool_use_id") is not None:
            return
        if kind == "stream_event":
            delta = (message.get("event") or {}).get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                trace.end("agent_first_token")
        elif kind == "assistant":
            for block in (message.get("message") or {}).get("content", ()):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    trace.end("agent_first_token")
                elif block.get("type") == "tool_use" and block.get("id"):
                    if not trace.tools:
                        trace.begin("tools")
                    trace.tools.add(block["id"])

    def queue_audio(self, turn, item):
        if (trace := self.turns.get(turn)) is None:
            return False
        trace.begin("tts_queue", item)
        trace.audio.add(item)
        self.audio[item] = trace
        return True

    def speech_event(self, message):
        item = message.get("id")
        if (trace := self.audio.get(item)) is None:
            return
        when = message.get("perf_at") or time.monotonic()
        cpu = message.get("perf_cpu_ms")
        event = message.get("event")
        if event == "tts_begin":
            trace.end("tts_queue", item, when, cpu)
            trace.begin("tts_first_pcm", item, when, cpu)
        elif event == "tts_pcm":
            trace.end("tts_first_pcm", item, when, cpu)
            trace.begin("audio_buffer", item, when, cpu)
        elif event == "start":
            trace.first_audio = trace.first_audio or when
            trace.end("audio_buffer", item, when, cpu)
            trace.begin("playback", item, when, cpu)
        elif event is None:
            if ("playback", item) in trace.active:
                trace.speech_end = when
                trace.end("playback", item, when, cpu, complete=not message.get("error"))
            self.drop_audio(item, "error" if message.get("error") else None)

    def drop_audio(self, item, status):
        trace = self.audio.pop(item)
        if status:
            trace.audio_status = status
        if ("playback", item) in trace.active:
            trace.speech_end = time.monotonic()
        for stage in ("tts_queue", "tts_first_pcm", "audio_buffer", "playback"):
            trace.end(stage, item, complete=False)
        trace.audio.discard(item)
        if trace.agent_status and not trace.audio:
            trace.finish(trace.agent_status)

    def finish_turns(self, turns, status):
        for turn in turns:
            if (trace := self.turns.get(turn)) is not None:
                trace.end("agent", complete=status == "completed")
                trace.end("agent_first_token", complete=False)
                trace.end("tools", complete=False)
                trace.agent_status = status
                if not trace.audio:
                    trace.finish(status)

    def cancel_audio(self, status):
        for item in tuple(self.audio):
            self.drop_audio(item, status)

    def close(self, status):
        for trace in tuple(self.traces):
            trace.finish(status)

    def complete(self, trace, row):
        self.traces.discard(trace)
        if self.turns.get(trace.turn) is trace:
            self.turns.pop(trace.turn, None)
        for item in trace.audio:
            self.audio.pop(item, None)
        if not self.traces and self.timer is not None:
            self.timer.cancel()
            self.timer = None
        try:
            self.append(row)
        except OSError as error:
            if not self.warned:
                self.warned = True
                self.warn(str(error))

    def append(self, row):
        line = (json.dumps(row, separators=(",", ":")) + "\n").encode()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            existing = self.path.lstat()
        except FileNotFoundError:
            existing = None
        if existing and (not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1 or existing.st_uid != os.getuid()):
            raise OSError(f"The performance log path is not a regular file: {self.path}")
        if existing and existing.st_size + len(line) > LOG_BYTES:
            self.path.replace(self.path.with_suffix(self.path.suffix + ".1"))
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(self.path, flags, 0o600), "ab") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                raise OSError("The performance log must be a regular file with one link owned by the current user.")
            if stat.S_IMODE(info.st_mode) != 0o600:
                os.fchmod(handle.fileno(), 0o600)
            handle.write(line)


async def check():
    """Exercise a complete speech path, a muted request, and bounded log rotation without audio."""
    import tempfile
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "perf.jsonl"
        logger = PerfLog(path, "fixture", lambda: {"recogniser": 1, "tts": 2, "wow": 3},
                         lambda error: print(error, file=sys.stderr))
        total = 10
        logger.read_process = lambda pid: (total * pid, 4096 * pid)
        trace = logger.begin("spoken", "talk_key")
        trace.begin("recognition")
        total += 4
        trace.end("recognition")
        trace.begin("smart_turn")
        trace.end("smart_turn")
        logger.dispatch(trace, "request")
        logger.agent_message("request", {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "call"}]}})
        total += 5
        logger.agent_message("request", {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call"}]}})
        logger.agent_message("request", {"type": "stream_event", "event": {
            "delta": {"type": "text_delta", "text": "this text stays out of the log"}}})
        assert logger.queue_audio("request", "speech")
        for event in ("tts_begin", "tts_pcm", "start"):
            logger.speech_event({"id": "speech", "event": event})
        logger.finish_turns(["request"], "completed")
        assert not path.exists()
        logger.speech_event({"id": "speech", "error": None})
        text = path.read_text()
        row = json.loads(text)
        assert "this text stays out" not in text
        assert row["stages"]["recognition"]["workers"]["recogniser"]["cpu_ms"] == 4
        assert row["stages"]["tools"]["workers"]["wow"]["cpu_ms"] == 15
        assert row["input_to_first_audio_ms"] <= row["input_to_end_of_speech_ms"]
        assert all(row["stages"][stage] for stage in STAGES if stage != "queue")
        assert not logger.traces and not logger.audio and logger.timer is None

        with patch(__name__ + ".LOG_BYTES", len(text) + 5):
            silent = logger.begin("typed", "request")
            logger.dispatch(silent, "muted")
            logger.finish_turns(["muted"], "completed")
        assert json.loads(path.read_text())["audio_status"] == "none"
        assert json.loads(path.with_suffix(".jsonl.1").read_text())["turn"] == "request"
        assert path.stat().st_mode & 0o777 == 0o600
    print("Request performance log: all checks passed.")


if __name__ == "__main__":
    asyncio.run(check())
