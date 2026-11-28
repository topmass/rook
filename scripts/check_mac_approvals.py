"""Exercise approval capture without microphone, desktop, or agent access."""

import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
import rook


async def check_capture(case):
    companion = rook.Companion.__new__(rook.Companion)
    approvals, errors = [], []
    opened = asyncio.Event()
    capture = object()
    companion.__dict__.update(
        permission={"card": "initial", "request": {"tool_name": "Bash"}},
        pipeline=SimpleNamespace(stop_recording=lambda _: SimpleNamespace(text="Yes.")),
        loop=asyncio.get_running_loop(), playing=asyncio.Event(), capture_finished=asyncio.Event(),
        recording_started=asyncio.Event(), voice=None, voice_id=None, voice_texts={}, asr_lock=None,
        game=None, recording_gen=0,
        hyprctl=lambda _: asyncio.sleep(0, result={}), no_shots=lambda _: asyncio.sleep(0),
        wait_tail_text=lambda: asyncio.sleep(0), stop_voice=lambda: None, show=lambda *args, **kwargs: None,
        log=lambda event, **fields: errors.append(fields) if event == "capture_error" else None,
        show_resting=lambda: None,
        restore_media_duck=lambda: None, maybe_restore_media_duck=lambda: None,
        end_listen_after=lambda **kwargs: False,
        answer_permission=lambda allow, card: approvals.append((allow, card)) or True,
    )
    companion.recording_seconds = lambda: 0.01 if case == "timeout" else 1
    releases = []

    async def open_capture():
        opened.set()
        return capture

    def start(released):
        releases.append(released)
        return True

    companion.open_capture = open_capture
    companion.start_talk = start
    companion.talking = lambda: bool(releases and not releases[-1].is_set())
    router = companion.make_mac_talk_router()

    def key(action, when, **fields):
        router.handle({"type": "talk_key", "action": action, "key": "RightOption", "ts": when, **fields})

    key("down", 1)
    task = asyncio.create_task(companion.record(releases[0]))
    with patch.object(rook, "discard_recording") as discard:
        await asyncio.wait_for(opened.wait(), 1)
        if case == "chord":
            key("chord_cancel", 1.2)
        elif case == "toggle":
            key("up", 1.1, held=0.1)
            assert not releases[0].is_set()
            key("down", 2)
        elif case != "timeout":
            if case == "stale":
                companion.permission["card"] = "replacement"
            key("up", 2, held=1)
        await asyncio.wait_for(task, 2)
        assert discard.called == (case == "chord"), case
    assert not errors, (case, errors)
    assert approvals == ([(True, "initial")] if case in ("hold", "toggle") else []), (case, approvals)


async def check():
    for case in ("hold", "toggle", "chord", "timeout", "stale"):
        await check_capture(case)
    print("Mac approval capture: hold, toggle, chord cancellation, timeout, and stale card checks passed.")


if __name__ == "__main__":
    asyncio.run(check())
