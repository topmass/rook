"""Measure Rook's local trace overhead in fresh processes with no model, microphone, or game."""

import argparse
import asyncio
from contextlib import redirect_stderr
import json
import os
from pathlib import Path
import resource
from statistics import median
import subprocess
import sys
import tempfile
import time


async def workload(root, mode, count, active_ms, sample):
    os.environ["XDG_STATE_HOME"] = str(root)
    os.environ["XDG_CONFIG_HOME"] = str(root / "config")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
    from rook import Companion

    companion = Companion.__new__(Companion)
    companion.session = "fixture"
    companion.perf_log = None
    if mode == "on":
        from perf import PerfLog
        # Re-read the same local PID for all four roles to model the cost of four available process counters.
        workers = dict.fromkeys(("recogniser", "tts", "agent", "wow"), os.getpid())
        companion.perf_log = PerfLog(root / "rook/perf.jsonl", companion.session, lambda: workers,
                                     lambda error: print(error, file=sys.stderr), companion.perf_event)
    logger = companion.perf_log

    async def request(number, trace=None):
        turn = f"turn-{number}"
        if trace:
            trace.begin("queue")
            trace.begin("recognition")
            trace.end("recognition")
            logger.dispatch(trace, turn)
            logger.agent_message(turn, {"type": "assistant", "message": {
                "content": [{"type": "tool_use", "id": "example", "name": "Read"}]}})
        companion.log("request", turn=turn, source="typed")
        if active_ms:
            await asyncio.sleep(active_ms / 1000)
        if trace:
            logger.agent_message(turn, {"type": "user", "message": {
                "content": [{"type": "tool_result", "tool_use_id": "example"}]}})
            logger.agent_message(turn, {"type": "assistant", "message": {"content": [{"type": "text", "text": "test"}]}})
            logger.queue_audio(turn, turn)
            for event in ("tts_begin", "tts_pcm", "start", None):
                logger.speech_event({"id": turn, "event": event})
        companion.log("response", turns=[turn])
        if trace:
            logger.finish_turns([turn], "completed")

    # Move lazy imports and file creation out of the timed window.
    await request(-1, logger.begin("typed", "fixture") if logger else None)
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
    for number in range(count):
        if mode == "baseline":
            await request(number)
        else:
            await request(number, logger.begin("typed", "fixture") if logger else None)
    cpu, wall = time.process_time_ns() - cpu, time.perf_counter_ns() - wall
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if sys.platform == "darwin" else 1024
    values = {"cpu_ms_per_request": cpu / 1e6 / count, "wall_ms_per_request": wall / 1e6 / count,
              "peak_rss_mib": rss_after * scale / 2**20, "rss_growth_mib": (rss_after - rss_before) * scale / 2**20}
    if logger is None:
        assert "perf" not in sys.modules and not (root / "rook/perf.jsonl").exists()
    if sample:
        assert logger is not None
        # Show one failed request and verify that all three records use the same opaque ID.
        with (root / "rook.err.log").open("w") as error_log, redirect_stderr(error_log):
            trace = logger.begin("typed", "fixture")
            logger.dispatch(trace, "failed-turn")
            logger.agent_message("failed-turn", {"type": "stream_event", "event": {
                "type": "content_block_start", "content_block": {"type": "tool_use", "id": "call", "name": "Bash"}}})
            logger.agent_message("failed-turn", {"type": "user", "message": {
                "content": [{"type": "tool_result", "tool_use_id": "call", "is_error": True}]}})
            companion.log("request", turn="failed-turn", source="typed")
            logger.finish_turns(["failed-turn"], "agent_error")
        perf = json.loads((root / "rook/perf.jsonl").read_text().splitlines()[-1])
        turns = json.loads((root / "rook/turns.jsonl").read_text().splitlines()[-1])
        error = (root / "rook.err.log").read_text().strip()
        assert perf["request_id"] == turns["request_id"] == trace.request_id
        assert f"request_id={trace.request_id}" in error
        values["trace"] = {name: perf[name] for name in ("request_id", "turn", "status", "timeline", "tool_calls")}
        values["trace"]["turns_event"] = turns
        values["trace"]["stderr"] = error
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--active-ms", type=float, default=0, help="Simulated agent latency to exercise timed sampling")
    parser.add_argument("--sample", action="store_true", help="Include one verified cross-log failure trace")
    parser.add_argument("--mode", choices=("baseline", "off", "on"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.requests < 1 or args.repeats < 1 or args.active_ms < 0:
        parser.error("requests and repeats must be positive, and active-ms must be nonnegative")
    if args.mode:
        with tempfile.TemporaryDirectory(prefix="rook-perf-") as scratch:
            print(json.dumps(asyncio.run(workload(Path(scratch), args.mode, args.requests, args.active_ms, args.sample))))
        return
    modes = ("baseline", "off", "on")
    rows = {mode: [] for mode in modes}
    sample = None
    for run in range(args.repeats):
        for mode in modes[run % 3:] + modes[:run % 3]:
            command = [sys.executable, __file__, "--mode", mode, "--requests", str(args.requests),
                       "--active-ms", str(args.active_ms)]
            if mode == "on" and args.sample and sample is None:
                command.append("--sample")
            row = json.loads(subprocess.check_output(command, text=True))
            if "trace" in row:
                sample = row.pop("trace")
            rows[mode].append(row)
    output = {"requests": args.requests, "repeats": args.repeats, "active_ms": args.active_ms,
              "medians": {mode: {key: round(median(row[key] for row in group), 4) for key in group[0]}
                          for mode, group in rows.items()}}
    if sample:
        output["sample_trace"] = sample
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
