"""Bounded, content-free request timings and local process measurements."""

import asyncio
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import stat
import sys
import time
from uuid import uuid4


STAGES = ("capture", "screenshot", "recognition", "smart_turn", "queue", "agent_first_token", "agent", "agent_ready", "journal", "dispatch", "tools", "approval", "phone_audio", "phone_render",
          "tts_queue", "tts_first_pcm", "audio_buffer", "playback")
LOG_BYTES = 2 * 1024 * 1024
SAMPLE_SECONDS = 0.1
MEMORY_SAMPLE_SECONDS = 0.25
MAC_PRESSURE = {1: "normal", 2: "warning", 4: "critical"}
MAX_REQUEST_SECONDS = 900
MAX_TRACES = 64
MAX_SPANS = 128
MAX_TOOLS = 128


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


def memory_reader():
    """Read the macOS pressure level, swap in use, and compressor usage without spawning a process."""
    if sys.platform != "darwin":
        return dict
    import ctypes
    import struct

    sysctl = ctypes.CDLL(None).sysctlbyname
    sysctl.argtypes = (ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                       ctypes.c_void_p, ctypes.c_size_t)
    # xsw_usage in <sys/sysctl.h>: total, available, used, page size, encryption flag.
    fields = (("pressure_level", b"kern.memorystatus_vm_pressure_level", struct.Struct("=I"), 0),
              ("swap_used_bytes", b"vm.swapusage", struct.Struct("=QQQII"), 2),
              ("compressor_used_bytes", b"vm.compressor_bytes_used", struct.Struct("=Q"), 0))

    def read():
        result = {}
        for key, name, layout, index in fields:
            size = ctypes.c_size_t(layout.size)
            data = ctypes.create_string_buffer(layout.size)
            if sysctl(name, data, ctypes.byref(size), None, 0) == 0 and size.value == layout.size:
                result[key] = layout.unpack(data.raw)[index]
        return result

    return read


def memory_labels(sample):
    level = sample.get("pressure_level")
    return {**sample, "pressure": MAC_PRESSURE.get(level, "unknown")} if level is not None else sample


class Span:
    def __init__(self, when, sample):
        self.when = when
        self.initial, self.memory_start = sample
        self.peak, self.memory_peak = {}, {}
        self.observe(sample)

    def observe(self, sample):
        workers, memory = sample
        for role, (_, _, rss) in workers.items():
            self.peak[role] = max(rss, self.peak.get(role, 0))
        for key, value in memory.items():
            self.memory_peak[key] = max(value, self.memory_peak.get(key, 0))


class Trace:
    def __init__(self, logger, source, origin):
        self.logger, self.source, self.origin = logger, source, origin
        self.began = time.monotonic()
        self.input_at = self.began
        self.request_id = uuid4().hex
        self.at = datetime.now(timezone.utc).isoformat()
        self.session = logger.session
        self.turn = None
        self.attempts = []
        self.active, self.stages = {}, {}
        self.first_audio = self.speech_end = None
        self.agent_status = None
        self.audio_status = None
        self.tools, self.audio = {}, set()
        self.timeline, self.tool_calls, self.tool_seen = [], [], set()
        self.approvals = set()
        self.omitted_spans = self.omitted_tools = 0

    def begin(self, stage, item=None, when=None, cpu=None):
        if self in self.logger.traces:
            self.active[stage, item] = Span(time.monotonic() if when is None else when, self.logger.sample(cpu))

    def end(self, stage, item=None, when=None, cpu=None, complete=True):
        span = self.active.pop((stage, item), None)
        if span is None:
            return
        elapsed = max(0, ((time.monotonic() if when is None else when) - span.when) * 1000)
        if len(self.timeline) < MAX_SPANS:
            self.timeline.append({"stage": stage, "at_ms": self.offset(span.when),
                                  "wall_ms": round(elapsed, 2), "complete": complete})
        else:
            self.omitted_spans += 1
        final = self.logger.sample(cpu)
        span.observe(final)
        workers, memory = final
        row = self.stages.setdefault(stage, {"wall_ms": 0.0, "count": 0, "complete": True, "workers": {}})
        row["wall_ms"] += elapsed
        row["count"] += 1
        row["complete"] &= complete
        if span.memory_peak:
            values = row.setdefault("system_memory", {"start": span.memory_start, "peak": {}})
            values["end"] = memory
            for key, value in span.memory_peak.items():
                values["peak"][key] = max(value, values["peak"].get(key, 0))
        for role, peak in span.peak.items():
            first, last = span.initial.get(role), workers.get(role)
            stats = row["workers"].setdefault(role, {"cpu_ms": None, "peak_rss_bytes": 0})
            stats["peak_rss_bytes"] = max(stats["peak_rss_bytes"], peak)
            if first and last and first[0] == last[0]:
                stats["cpu_ms"] = (stats["cpu_ms"] or 0) + max(0, last[1] - first[1])

    def observe(self, sample):
        for span in self.active.values():
            span.observe(sample)

    def tool_start(self, block):
        token = block.get("id")
        if not isinstance(token, str) or not token or len(token) > 256 or token in self.tool_seen:
            return
        if len(self.tool_seen) >= MAX_TOOLS:
            self.omitted_tools += 1
            return
        name = block.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", name):
            name = "unknown"
        if not self.tools:
            self.begin("tools")
        self.tool_seen.add(token)
        self.tools[token] = (len(self.tool_seen), name, time.monotonic())

    def tool_end(self, token, status):
        if not isinstance(token, str) or not (tool := self.tools.pop(token, None)):
            return
        number, name, at = tool
        self.tool_calls.append({"id": number, "name": name, "at_ms": self.offset(at),
                                "wall_ms": round((time.monotonic() - at) * 1000, 2), "status": status})
        if not self.tools:
            self.end("tools", complete=status != "unfinished")

    def finish(self, status):
        if self not in self.logger.traces:
            return
        for token in tuple(self.tools):
            self.tool_end(token, "unfinished")
        for stage, item in list(self.active):
            self.end(stage, item, complete=False)
        for row in self.stages.values():
            wall = row["wall_ms"]
            if memory := row.get("system_memory"):
                row["system_memory"] = {key: memory_labels(reading) for key, reading in memory.items()}
            for worker in row["workers"].values():
                if worker["cpu_ms"] is not None:
                    worker["cpu_pct"] = round(100 * worker["cpu_ms"] / wall, 1) if wall else None
                    worker["cpu_ms"] = round(worker["cpu_ms"], 2)
            row["wall_ms"] = round(wall, 2)
        self.logger.complete(self, {
            "at": self.at, "level": "info", "event": "request_perf", "session": self.session,
            "request_id": self.request_id, "turn": self.turn, "attempts": self.attempts, "source": self.source, "origin": self.origin, "status": status,
            "audio_status": self.audio_status or ("played" if self.speech_end is not None else "none"),
            "input_to_first_audio_ms": self.offset(self.first_audio, self.input_at),
            "input_to_end_of_speech_ms": self.offset(self.speech_end, self.input_at),
            "wall_ms": self.offset(time.monotonic()),
            "timeline": sorted(self.timeline, key=lambda event: event["at_ms"]),
            "tool_calls": self.tool_calls,
            "omitted_spans": self.omitted_spans, "omitted_tools": self.omitted_tools,
            "stages": {stage: self.stages.get(stage) for stage in STAGES},
        })

    def offset(self, when, origin=None):
        return round((when - (self.began if origin is None else origin)) * 1000, 2) if when is not None else None


class PerfLog:
    def __init__(self, path, session, workers, warn, event=None):
        self.path, self.session, self.workers, self.warn = path, session, workers, warn
        self.event = event
        self.read_process = process_reader()
        self.read_memory = memory_reader()
        self.memory_at, self.memory = float("-inf"), {}
        self.traces, self.turns, self.audio = set(), {}, {}
        self.timer = None
        self.warned = False

    def sample(self, tts_cpu=None):
        sample = {}
        for role, pid in self.workers().items():
            if pid and (reading := self.read_process(pid)) is not None:
                cpu, rss = reading
                sample[role] = pid, tts_cpu if role == "tts" and tts_cpu is not None else cpu, rss
        now = time.monotonic()
        if now - self.memory_at >= MEMORY_SAMPLE_SECONDS:
            self.memory_at, self.memory = now, self.read_memory()
        return sample, self.memory

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
        if self.event:
            self.event(trace, "trace_started")
        return trace

    def bind(self, trace, turn):
        if trace in self.traces:
            if trace.turn != turn and self.turns.get(trace.turn) is trace:
                self.turns.pop(trace.turn)
            trace.turn = turn
            if not trace.attempts or trace.attempts[-1] != turn:
                trace.attempts.append(turn)
            self.turns[turn] = trace

    def dispatch(self, trace, turn):
        if trace not in self.traces:
            return
        self.bind(trace, turn)
        trace.end("queue")
        trace.begin("agent")
        trace.begin("agent_first_token")

    def retry(self, turn):
        if trace := self.turns.get(turn):
            for phase, item in tuple(trace.active):
                trace.end(phase, item, complete=False)
            return trace
        return None

    def approval_done(self, token):
        if not isinstance(token, str):
            return
        for trace in self.turns.values():
            if token in trace.approvals:
                trace.approvals.discard(token)
                trace.end("approval", token)
                return

    def agent_message(self, turn, message):
        trace = self.turns.get(turn)
        kind = message.get("type")
        if kind == "control_cancel_request":
            self.approval_done(message.get("request_id"))
            return
        parent = message.get("parent_tool_use_id")
        if isinstance(parent, str):
            trace = next((item for item in self.turns.values() if parent in item.tools), trace)
        if kind == "user":
            for block in (message.get("message") or {}).get("content", ()):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    token = block.get("tool_use_id")
                    if isinstance(token, str):
                        for active in self.turns.values():
                            if token in active.tools:
                                active.tool_end(token, "error" if block.get("is_error") else "completed")
                                break
            return
        if trace is None:
            return
        if kind == "control_request" and (message.get("request") or {}).get("subtype") == "can_use_tool":
            token = message.get("request_id")
            if isinstance(token, str) and len(token) <= 256 and token not in trace.approvals and len(trace.approvals) < MAX_TOOLS:
                trace.approvals.add(token)
                trace.begin("approval", token)
        elif kind == "stream_event":
            event = message.get("event") or {}
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text") and parent is None:
                trace.end("agent_first_token")
            block = event.get("content_block") or {}
            if event.get("type") == "content_block_start" and block.get("type") == "tool_use":
                trace.tool_start(block)
        elif kind == "assistant":
            for block in (message.get("message") or {}).get("content", ()):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text") and parent is None:
                    trace.end("agent_first_token")
                elif block.get("type") == "tool_use":
                    trace.tool_start(block)

    def queue_audio(self, turn, item, stage="tts_queue"):
        if (trace := self.turns.get(turn)) is None or len(trace.audio) >= MAX_SPANS:
            return False
        trace.begin(stage, item)
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
        for stage in ("tts_queue", "tts_first_pcm", "audio_buffer", "playback", "phone_audio"):
            trace.end(stage, item, complete=False)
        trace.audio.discard(item)
        if trace.agent_status and not trace.audio:
            trace.finish(trace.agent_status)

    def finish_turns(self, turns, status):
        for turn in turns:
            if (trace := self.turns.get(turn)) is not None:
                trace.end("agent", complete=status == "completed")
                trace.end("agent_first_token", complete=False)
                for token in tuple(trace.tools):
                    trace.tool_end(token, "unfinished")
                trace.agent_status = status
                if not trace.audio:
                    trace.finish(status)

    def phone_audio_done(self, task):
        if (trace := self.audio.get(task)) is not None:
            status = "stopped" if task.cancelled() else "error" if task.exception() else None
            trace.end("phone_audio", task, complete=status is None)
            trace.end("phone_render", complete=False)
            if status is None and trace.audio_status is None:
                trace.audio_status = "rendered"
            self.drop_audio(task, status)

    def cancel_audio(self, status):
        for item, trace in tuple(self.audio.items()):
            if ("phone_audio", item) not in trace.active:
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
        if self.event:
            self.event(trace, "trace_finished", row["status"], row["audio_status"])
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
        events = []
        logger = PerfLog(path, "fixture", lambda: {"recogniser": 1, "tts": 2, "wow": 3},
                         lambda error: print(error, file=sys.stderr),
                         lambda trace, event, *rest: events.append((trace.request_id, event, rest)))
        total = 10
        logger.read_process = lambda pid: (total * pid, 4096 * pid)
        logger.read_memory = lambda: {"pressure_level": 1 if total < 12 else 4 if total == 12 else 2,
                                      "swap_used_bytes": 4096 * total}
        trace = logger.begin("spoken", "talk_key")
        trace.begin("recognition")
        total += 2
        logger.memory_at = float("-inf")
        trace.observe(logger.sample())
        total += 2
        logger.memory_at = float("-inf")
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
        memory = row["stages"]["recognition"]["system_memory"]
        assert [memory[key]["pressure"] for key in ("start", "end", "peak")] == ["normal", "warning", "critical"]
        assert row["stages"]["tools"]["workers"]["wow"]["cpu_ms"] == 15
        assert row["input_to_first_audio_ms"] <= row["input_to_end_of_speech_ms"]
        required = ("recognition", "smart_turn", "agent", "agent_first_token", "tools",
                    "tts_queue", "tts_first_pcm", "audio_buffer", "playback")
        assert all(row["stages"][stage] for stage in required)
        assert row["request_id"] == trace.request_id and row["attempts"] == ["request"]
        assert [(tool["id"], tool["status"]) for tool in row["tool_calls"]] == [(1, "completed")]
        assert events == [(trace.request_id, "trace_started", ()),
                          (trace.request_id, "trace_finished", ("completed", "played"))]
        assert sorted(row["timeline"], key=lambda span: span["at_ms"]) == row["timeline"]
        assert not logger.traces and not logger.audio and logger.timer is None

        with patch(__name__ + ".LOG_BYTES", len(text) + 5):
            silent = logger.begin("typed", "request")
            logger.dispatch(silent, "muted")
            logger.finish_turns(["muted"], "completed")
        assert json.loads(path.read_text())["audio_status"] == "none"
        assert json.loads(path.with_suffix(".jsonl.1").read_text())["turn"] == "request"
        assert path.stat().st_mode & 0o777 == 0o600

        retry = logger.begin("typed", "relay")
        logger.dispatch(retry, "first")
        assert logger.retry("first") is retry
        logger.dispatch(retry, "second")
        logger.agent_message("second", {"type": "control_request", "request_id": "approval",
                                         "request": {"subtype": "can_use_tool"}})
        logger.approval_done("approval")
        for number in range(MAX_TOOLS + 1):
            block = {"type": "tool_use", "id": str(number), "name": "Bash", "input": {"secret": "not logged"}}
            logger.agent_message("second", {"type": "stream_event", "event": {
                "type": "content_block_start", "content_block": block}})
            if number < MAX_TOOLS:
                logger.agent_message("second", {"type": "assistant", "message": {"content": [block]}})
        logger.agent_message("first", {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "0", "is_error": True}]}})
        logger.finish_turns(["second"], "agent_error")
        row = json.loads(path.read_text().splitlines()[-1])
        assert row["request_id"] == retry.request_id and row["attempts"] == ["first", "second"]
        assert row["stages"]["approval"]["count"] == 1 and row["omitted_tools"] == 1
        assert len(row["tool_calls"]) == MAX_TOOLS and row["tool_calls"][0]["status"] == "error"
        assert "not logged" not in json.dumps(row)
        assert row["tool_calls"][-1]["status"] == "unfinished"
    print("Request performance log: all checks passed.")


if __name__ == "__main__":
    asyncio.run(check())
