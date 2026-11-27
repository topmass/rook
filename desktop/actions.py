"""Rook's silent outbox, called Hands: action orders Rook dispatches with a {do: ...} mark in its answer, run one at a
time in an agent session of their own, with every change of state in the actions ledger of Rook's database.

Hands never speaks to the owner: Rook is the only voice. News comes back in two lanes.
- A routine confirmation stays silent. Rook's next spoken or typed turn ends with a short delta of the ledger rows that
  changed since the last delta it saw. The delta is appended to that turn, so the conversation before it never changes.
- A failure, a stuck or blocked action, or the answer to a {do wake: ...} order calls on_wake once, and Rook queues an
  action turn in its inbox. Rook decides there whether to speak or to answer PASS.
This module knows nothing of the overlay or the speech, and talks to Rook only through callbacks. The rows live in
journal.py; this module only moves them.
Run this file to check its logic: python desktop/actions.py --check
"""
import asyncio
import os
import re
import sys
import time
from uuid import uuid4

ACTOR = "rook-agent"  # The actor name on every row Hands writes.
STUCK_SECONDS = 75  # A running action that shows no progress this long is marked stuck. It is not stopped.
SETUP_SECONDS = 90  # The longest an order waits for Hands' setup turn.
BEAT_SECONDS = 5  # A running action's progress time is written at most this often.
WAKE_STATES = ("failed", "stuck", "blocked")  # States Rook always hears of at once.
RESULT_LIMIT = 240  # Characters in a result, and in one line of the ledger delta.
DELTA_LIMIT = 1600  # Characters in one ledger delta, so a backlog never bloats a turn.
DELTA_ROWS = 12
CANCELLED_EARLY = "Cancelled before it began."
# Hands shows no card: Rook's cards belong to the main session. A tool that needs the owner's yes is declined.
NEEDS_OWNER = "Run this from the main Rook session so the owner can approve it."
# A mark in Rook's answer: "{do: turn off the desk lamp}" or "{do wake: look up the build status}". Braces never occur in
# spoken prose, so a mark cannot be mistaken for words. A mark ends at "}", before a newline, or at the text's end. One
# longer than DO_HOLD characters is not a mark: only its opener goes, and its words are spoken.
DO_HOLD = 600
DO_MARK = re.compile(r"[ \t]*\{\s*do(\s+wake)?\s*:\s*([^{}\n]{0,%d}?)[ \t]*(\}|(?=\n)|\Z)" % DO_HOLD, re.IGNORECASE)
DO_OPENER = re.compile(r"\{\s*do(?:\s+wake)?\s*:\s*", re.IGNORECASE)
HANDS_PROMPT = (
    "You are Hands, the silent outbox of Rook, a voice assistant. Rook alone talks to the owner. Rook hands you short "
    "orders, one at a time. Carry out each order now, with your tools. You never speak, write or ask anything to the "
    "owner: no question card, no message, no notification and no spoken line. Never start subagents. Never delete "
    "data, do anything that cannot be undone, or reach outside this computer unless the order says so in so many "
    "words. When you cannot carry out an order, or it is unclear, stop and say why. End every turn with one short "
    "factual line of at most 200 characters: what you did or what you found, such as \"The desk lamp is off.\" "
    "Claim only what you checked.")


def mark_orders(match):
    """The order a mark carries, as a list of none or one: {"wake", "kind", "order"}. A wake order is a lookup whose
    answer the owner wants to hear."""
    order = " ".join(match[2].split())
    return [{"wake": bool(match[1]), "kind": "lookup" if match[1] else "task", "order": order}] if order else []


def parse_do_marks(text):
    """Return (text without its marks, the orders they carry)."""
    orders = []
    cleaned = DO_MARK.sub(lambda match: orders.extend(mark_orders(match)) or "", text)
    return DO_OPENER.sub("", cleaned), orders


def take_closed_marks(text):
    """Return (streamed text with every closed mark taken out, their orders). A mark still open at the text's end
    stays, so the speech waits for the rest of it, and it is never spoken."""
    orders = []

    def take(match):
        if not match[3] and match.end() == len(text):
            return match[0]
        orders.extend(mark_orders(match))
        return ""
    return DO_MARK.sub(take, text), orders


def clip(text, limit=RESULT_LIMIT):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def one_line(text):
    """The last line of an agent's answer, which the prompt asks to be its result."""
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    return clip(lines[-1] if lines else "")


def should_wake(row):
    """Whether Rook hears of this row now: a failure, a stuck or blocked action, or the answer to a wake order. Each
    state wakes Rook once."""
    return row["notified_state"] != row["state"] and (
        row["state"] in WAKE_STATES or bool(row["wake"]) and row["state"] == "confirmed")


def wake_text(row):
    """The words of an action turn in Rook's inbox."""
    return (f"Action {row['key']} of {row['actor']} is {row['state']}: {row['description']}"
            + (f" Result: {row['result']}" if row.get("result") else ""))


def format_ledger_delta(rows):
    """The ledger rows that changed since Rook's last delta, one short line each, for the end of a turn."""
    if not rows:
        return ""
    lines, used = [], 0
    for n, row in enumerate(rows):
        line = clip(f"- {time.strftime('%H:%M', time.localtime(row['updated']))} {row['actor']} {row['key']} "
                    f"{row['state']}: {row['description']}" + (f" Result: {row['result']}" if row.get("result") else ""))
        if used + len(line) > DELTA_LIMIT:
            lines.append(f"- {len(rows) - n} more changed. relay.py actions lists them.")
            break
        lines.append(line)
        used += len(line) + 1
    return ("Your silent outbox's ledger changed since your last turn. These lines are not the owner's words, and a "
            "confirmed line needs no answer:\n" + "\n".join(lines))


class HarnessSession:
    """Hands' own agent session on one of Rook's harnesses: one process, one order at a time. It reads the messages
    harness.py documents, so it runs on every agent Rook runs on. messages turns the process's stdout into dicts."""

    def __init__(self, harness, process, session, messages, setup):
        self.harness, self.process, self.session = harness, process, session
        loop = asyncio.get_running_loop()
        self.ready = loop.create_future()  # True once the setup turn is answered, False when the agent closed first.
        self.turn = None  # The running order's future: (ok, text).
        self.on_progress = self.on_permission = None
        self.asks = {}  # request_id: the task that waits for an ask's answer.
        harness.begin(process, session, str(uuid4()), setup)
        self.reader = loop.create_task(self.read(messages))

    @property
    def alive(self):
        return self.process.returncode is None and not self.reader.done()

    async def run(self, text, on_progress, on_permission, cancelled=lambda: False):
        """Send one order and return (ok, the agent's final text). An order cancelled during the setup turn is never
        sent."""
        try:
            ready = await asyncio.wait_for(asyncio.shield(self.ready), SETUP_SECONDS)
        except TimeoutError:
            self.close()
            raise RuntimeError(f"{self.harness.name} gave no answer to its setup turn in {SETUP_SECONDS} seconds.")
        if cancelled():
            return False, CANCELLED_EARLY
        if not ready or not self.alive:
            return False, f"{self.harness.name} closed before the order."
        self.on_progress, self.on_permission = on_progress, on_permission
        self.turn = asyncio.get_running_loop().create_future()
        try:
            self.harness.turn(self.process, self.session, str(uuid4()), text, (), False)
            return await self.turn
        finally:
            self.turn = self.on_progress = self.on_permission = None

    def steer(self, text):
        if self.turn and self.alive:
            self.harness.turn(self.process, self.session, str(uuid4()), text, (), True)

    def interrupt(self):
        """Cut the running order. During the setup turn there is none, and the setup goes on."""
        if self.turn and self.alive:
            self.harness.interrupt(self.process)

    def close(self):
        self.reader.cancel()
        if self.process.returncode is None:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass

    async def read(self, messages):
        try:
            async for message in self.harness.read(messages(self.process.stdout)):
                kind = message.get("type")
                if kind == "result":
                    if not self.ready.done():  # The first result after a launch ends the setup turn.
                        self.ready.set_result(True)
                    elif self.turn and not self.turn.done():
                        self.turn.set_result((not message.get("is_error"),
                                              message.get("result") or "\n".join(message.get("errors") or [])))
                elif kind == "control_request" and (message.get("request") or {}).get("subtype") == "can_use_tool":
                    ask_id = message.get("request_id")
                    self.asks[ask_id] = asyncio.get_running_loop().create_task(self.ask(message))
                elif kind == "control_cancel_request":
                    if task := self.asks.pop(message.get("request_id"), None):
                        task.cancel()
                elif self.on_progress:
                    self.on_progress()
        finally:
            if not self.ready.done():
                self.ready.set_result(False)
            if self.turn and not self.turn.done():
                self.turn.set_result((False, f"{self.harness.name} closed during the order."))
            for task in self.asks.values():
                task.cancel()

    async def ask(self, message):
        """Answer one permission ask through on_permission: (allowed, answers, reason)."""
        try:
            if self.on_permission is None:
                allowed, answers, reason = False, None, "No order is running."
            else:
                allowed, answers, reason = await self.on_permission(message)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            allowed, answers, reason = False, None, f"Rook could not ask: {type(exc).__name__}."
        finally:
            self.asks.pop(message.get("request_id"), None)
        if self.alive:
            self.harness.permit(self.process, message, allowed, answers, reason)


class ActionOutbox:
    """The worker that runs dispatched actions in arrival order, in Hands' session, and writes each change to the
    ledger. record is Rook's journal.Journal. start_session() is awaited for a new session when there is none or it
    closed. on_wake(row) tells Rook of a row it must judge now. Hands' permission asks are declined, and the action
    is blocked."""

    def __init__(self, record, start_session, on_wake, log=None, stuck_seconds=STUCK_SECONDS):
        self.record, self.start_session, self.on_wake = record, start_session, on_wake
        self.log = log or (lambda event, **fields: None)
        self.stuck_seconds = stuck_seconds
        self.queue = asyncio.Queue()
        self.session = None
        self.running = None  # The row of the action Hands runs now.
        self.cancels = set()  # Keys of running actions a cancel interrupted, or caught before Hands' setup ended.
        self.heard = self.beat = 0.0  # When the running action last showed progress, and when that was written.
        self.beat_write = None

    async def db(self, name, *args, **kwargs):
        return await asyncio.to_thread(getattr(self.record, name), *args, **kwargs)

    async def dispatch(self, order, *, wake=False, conversation="", turn=None):
        """Write the order's dispatched row, then queue it. Return the row."""
        row = await self.db("dispatch_action", "act-" + os.urandom(6).hex(), actor=ACTOR, conversation=conversation,
                            turn=turn, kind="lookup" if wake else "task", effect=0 if wake else 1, wake=int(wake),
                            description=clip(order, 120), order_text=order)
        self.enqueue(row)
        return row

    def enqueue(self, row):
        self.queue.put_nowait(row["key"])
        self.log("action", key=row["key"], state=row["state"], wake=bool(row["wake"]))

    async def unread(self, since_seq):
        return await self.db("unread_actions", since_seq, limit=DELTA_ROWS)

    async def cancel(self, key):
        """Cancel an action: at once when it has not begun, and by interrupting Hands when it runs. Return its row, or
        None when there is no such action."""
        row = await self.db("get_action", key)
        if row and row["state"] == "dispatched":
            self.cancels.add(key)  # Also guards the millisecond window while work() transitions it to running.
            return await self.settle(key, "cancelled", CANCELLED_EARLY) or await self.db("get_action", key)
        if row and self.running and self.running["key"] == key:
            self.cancels.add(key)  # Also while Hands starts: the order is then never sent.
            if self.session:
                self.session.interrupt()
        return row

    def steer(self, key, text):
        """Add to the running action's order. Return whether it was running."""
        if self.running and self.running["key"] == key and self.session:
            self.session.steer(text)
            return True
        return False

    async def settle(self, key, state, result):
        """Move an action to state and wake Rook once when the new state calls for it. Return the row, or None."""
        before = await self.db("get_action", key)
        wake = bool(before) and should_wake({**before, "state": state})
        row = await self.db("action_transition", key, state, result=result, notified_state=state if wake else None)
        if row:
            self.log("action", key=key, state=state, wake=wake)
            if wake:
                try:
                    self.on_wake(row)
                except Exception as exc:  # A failed wake never stops the worker; the ledger still holds the row.
                    self.log("action_wake_error", key=key, error=repr(exc))
        return row

    async def work(self):
        """Run each dispatched action in arrival order. One that a cancel ended first is skipped."""
        while True:
            key = await self.queue.get()
            row = await self.db("action_transition", key, "running")
            if row is None or row["state"] != "running":
                self.cancels.discard(key)
                continue
            self.running, self.heard = row, time.monotonic()
            try:
                if self.session is None or not self.session.alive:
                    if self.session:  # A dead session's process never outlives it.
                        self.session.close()
                    self.session = await self.start_session()
                ok, text = await self.session.run(f"Order {key}: {row['order_text']}", lambda: self.progress(key),
                                                  lambda ask: self.permission(key, ask), lambda: key in self.cancels)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                ok, text = False, f"Hands could not run it: {exc}"
            state = "cancelled" if key in self.cancels else "confirmed" if ok else "failed"
            blocked = self.running["state"] == "blocked"
            self.cancels.discard(key)
            self.running = None
            result = one_line(text) or ("Done." if ok else "It ended with no result.")
            if blocked and state == "failed":  # Rook heard of the block already: the row ends with no second wake.
                await self.db("action_transition", key, state, result=result, notified_state=state)
            else:
                await self.settle(key, state, result)

    def progress(self, key):
        self.heard = now = time.monotonic()
        if now - self.beat >= BEAT_SECONDS and (self.beat_write is None or self.beat_write.done()):
            self.beat = now
            self.beat_write = asyncio.get_running_loop().create_task(
                self.db("action_transition", key, "running", progress_only=True))

    async def permission(self, key, ask):
        """A permission ask from Hands is declined: Hands never asks the owner. A tool ask blocks the action, which
        wakes Rook once."""
        request = ask.get("request") or {}
        if request.get("tool_name") == "AskUserQuestion":
            return False, None, "Hands never asks the owner. Say what you need in your last line instead."
        self.running = await self.settle(key, "blocked", clip(f"Hands may not use {request.get('tool_name')} without "
                                                              f"the owner's yes. {NEEDS_OWNER}")) or self.running
        return False, None, NEEDS_OWNER

    async def watch(self):
        """Mark the running action stuck when it shows no progress for stuck_seconds. It goes on running."""
        while True:
            await asyncio.sleep(min(5.0, self.stuck_seconds / 3))
            row = self.running
            if row and row["state"] == "running" and time.monotonic() - self.heard > self.stuck_seconds:
                if (settled := await self.settle(row["key"], "stuck", None)) and self.running is row:
                    self.running = settled


def check():
    """Mark parsing, the state machine, actor tags, the ledger delta, wake routing and restart recovery, on a scratch
    database with a stand-in session. It opens no agent, window, sound or microphone."""
    import json
    import tempfile
    from pathlib import Path
    import journal

    # Marks: taken out of the text, closed or at its end, and never spoken.
    text, orders = parse_do_marks("Turning it off. {do: turn off the  desk lamp} Anything else?")
    assert text == "Turning it off. Anything else?", text
    assert orders == [{"wake": False, "kind": "task", "order": "turn off the desk lamp"}], orders
    text, orders = parse_do_marks("I'll look. {DO WAKE: look up the build status}")
    assert text == "I'll look." and orders == [{"wake": True, "kind": "lookup", "order": "look up the build status"}]
    text, orders = parse_do_marks("On it. {do: dim the lights\n\nThe full answer.")  # A newline closes it and stays.
    assert text == "On it.\n\nThe full answer." and orders[0]["order"] == "dim the lights", (text, orders)
    text, orders = parse_do_marks("Two. {do: a} {do wake: b} {do: }")
    assert text == "Two." and [o["order"] for o in orders] == ["a", "b"], (text, orders)
    long = "{do: " + "word " * 130 + "end. More."  # Past DO_HOLD it is no mark: its opener goes, its words stay.
    text, orders = parse_do_marks(long)
    assert not orders and text == long[len("{do: "):], text[:30]
    assert parse_do_marks("Plain {braces} and {diagram a > b} stay.") == ("Plain {braces} and {diagram a > b} stay.", [])
    # Streaming: an open mark waits, a closed one goes, and the spoken text never holds a mark.
    assert take_closed_marks("On it. {do: send the") == ("On it. {do: send the", [])
    assert take_closed_marks("On it. {do: send the note} Done") == ("On it. Done", [
        {"wake": False, "kind": "task", "order": "send the note"}])
    assert take_closed_marks("On it. {do: send\nMore")[0] == "On it.\nMore"
    acc, taken = "", []
    for piece in ("Sure", ". {d", "o wake: check the", " gate} It's", " on its way."):
        acc, orders = take_closed_marks(acc + piece)
        taken += orders
    assert acc == "Sure. It's on its way." and [o["order"] for o in taken] == ["check the gate"], (acc, taken)
    assert format_ledger_delta([]) == ""
    assert one_line("Thinking.\n\nThe lamp is off.\n") == "The lamp is off." and len(one_line("x" * 900)) == RESULT_LIMIT

    async def until(test, label, timeout=5.0):
        end = time.monotonic() + timeout
        while not test():
            assert time.monotonic() < end, label
            await asyncio.sleep(0.01)

    class Session:
        """Stands in for Hands' agent: an order's words choose what it does."""
        alive, closed = True, False

        def __init__(self):
            self.orders, self.release, self.interrupted = [], asyncio.Event(), asyncio.Event()

        async def run(self, text, on_progress, on_permission, cancelled):
            if cancelled():
                return False, CANCELLED_EARLY
            self.orders.append(text)
            on_progress()
            if "fail" in text:
                return False, "The lamp did not answer."
            if "hang" in text:
                done = asyncio.ensure_future(self.release.wait())
                cut = asyncio.ensure_future(self.interrupted.wait())
                await asyncio.wait({done, cut}, return_when=asyncio.FIRST_COMPLETED)
                done.cancel(), cut.cancel()
                self.release.clear()
                if self.interrupted.is_set():
                    self.interrupted.clear()
                    return False, "Interrupted."
                return True, "Waited, then done."
            if "ask" in text:
                allowed, _, reason = await on_permission({"request_id": "r1", "request": {
                    "subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "ls"}}})
                question = await on_permission({"request_id": "r2", "request": {
                    "subtype": "can_use_tool", "tool_name": "AskUserQuestion", "input": {}}})
                assert question[0] is False and "never asks" in question[2], question
                return allowed, "Listed the folder." if allowed else "Not allowed."
            return True, f"Thinking.\nDone: {text.split(': ', 1)[1]}."

        def interrupt(self):
            self.interrupted.set()

        def steer(self, text):
            self.orders.append(f"steer {text}")

        def close(self):
            self.closed = True

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "rook/mailbox.db"
        record = journal.Journal(path).open()
        woke, sessions, starting = [], [], asyncio.Event()
        starting.set()

        async def start_session():
            await starting.wait()
            sessions.append(Session())
            return sessions[-1]

        async def run():
            outbox = ActionOutbox(record, start_session, woke.append, stuck_seconds=0.3)
            tasks = [asyncio.create_task(outbox.work()), asyncio.create_task(outbox.watch())]

            def state(key):
                return record.get_action(key)["state"]
            # A routine order: confirmed in silence, tagged with Hands' actor name.
            lamp = await outbox.dispatch("turn off the desk lamp", conversation="s1", turn="t1")
            assert (lamp["state"], lamp["actor"], lamp["wake"], lamp["kind"]) == ("dispatched", ACTOR, 0, "task"), lamp
            await until(lambda: state(lamp["key"]) == "confirmed", "routine confirm")
            row = record.get_action(lamp["key"])
            assert row["result"] == "Done: turn off the desk lamp." and row["started"] and row["ended"], row
            assert sessions[0].orders == [f"Order {lamp['key']}: turn off the desk lamp"] and woke == []
            # A lookup the owner waits on wakes Rook once it is confirmed.
            build = await outbox.dispatch("look up the build status", wake=True, conversation="s1")
            await until(lambda: woke, "wake on a lookup")
            assert [(r["key"], r["state"]) for r in woke] == [(build["key"], "confirmed")], woke
            assert record.get_action(build["key"])["notified_state"] == "confirmed"
            # A failure wakes Rook, once.
            fail = await outbox.dispatch("fail at the porch light")
            await until(lambda: len(woke) == 2, "wake on a failure")
            assert (woke[1]["key"], woke[1]["state"], woke[1]["result"]) == (fail["key"], "failed", "The lamp did not answer.")
            # No progress past stuck_seconds: stuck, one wake, and it goes on to a silent confirm.
            slow = await outbox.dispatch("hang on the kettle")
            await until(lambda: state(slow["key"]) == "stuck", "stuck")
            await asyncio.sleep(0.5)
            assert [r["state"] for r in woke] == ["confirmed", "failed", "stuck"], woke
            # An order queued behind it and cancelled before it began never runs.
            queued = await outbox.dispatch("open the blinds")
            cancelled = await outbox.cancel(queued["key"])
            assert cancelled["state"] == "cancelled" and cancelled["result"] == "Cancelled before it began.", cancelled
            assert outbox.steer(slow["key"], "and the tea") and not outbox.steer(queued["key"], "no")
            sessions[0].release.set()
            await until(lambda: state(slow["key"]) == "confirmed", "stuck then confirmed")
            await asyncio.sleep(0.05)
            assert len(woke) == 3 and not any("open the blinds" in o for o in sessions[0].orders), sessions[0].orders
            # A running action that is cancelled is interrupted and ends cancelled, with no wake.
            held = await outbox.dispatch("hang on the oven")
            await until(lambda: state(held["key"]) == "running", "running")
            await outbox.cancel(held["key"])
            await until(lambda: state(held["key"]) == "cancelled", "cancel while running")
            # A permission ask is declined with no card: blocked and woken once, then failed with no second wake.
            ask = await outbox.dispatch("ask to list the folder")
            await until(lambda: state(ask["key"]) == "failed", "permission")
            assert len(woke) == 4 and woke[-1]["state"] == "blocked" and NEEDS_OWNER in woke[-1]["result"], woke
            assert record.get_action(ask["key"])["result"] == "Not allowed."
            # A session that closed is closed for good and replaced for the next order.
            sessions[0].alive = False
            again = await outbox.dispatch("lock the door")
            await until(lambda: state(again["key"]) == "confirmed", "new session")
            assert len(sessions) == 2 and sessions[0].closed and not sessions[1].closed
            # A cancel while Hands' session starts: the order is never sent, and it ends cancelled.
            sessions[1].alive = False
            starting.clear()
            cold = await outbox.dispatch("hang on the heater")
            await until(lambda: state(cold["key"]) == "running", "cold start")
            await outbox.cancel(cold["key"])
            starting.set()
            await until(lambda: state(cold["key"]) == "cancelled", "cancel during the start")
            assert record.get_action(cold["key"])["result"] == CANCELLED_EARLY and sessions[2].orders == []
            assert len(woke) == 4 and not outbox.cancels
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return [lamp, build, fail, slow, queued, held, ask, again, cold]
        rows = asyncio.run(run())
        # The ledger: every change has its own seq, growing, and the delta reads them in order, append-only.
        changed, high = record.unread_actions(0, limit=100)
        seqs = [row["ledger_seq"] for row in changed]
        assert seqs == sorted(set(seqs)) and high == seqs[-1], seqs
        assert {row["actor"] for row in changed} == {ACTOR} and len(changed) == len(rows)
        first, mid = record.unread_actions(0, limit=3)
        rest, end = record.unread_actions(mid, limit=100)
        assert [r["key"] for r in first + rest] == [r["key"] for r in changed] and end == high
        assert record.unread_actions(high) == ([], high)
        delta = format_ledger_delta(changed)
        assert delta.count(f"\n- ") == len(changed) and ACTOR in delta and rows[0]["key"] in delta, delta
        assert all(len(line) <= RESULT_LIMIT for line in delta.splitlines()[1:]), delta
        big = format_ledger_delta([{**changed[0], "description": "x" * 500, "key": f"act-{n}"} for n in range(40)])
        assert len(big) < DELTA_LIMIT + 400 and big.endswith("more changed. relay.py actions lists them."), big[-80:]
        listed = record.list_actions(limit=3)
        assert [r["key"] for r in listed] == [r["key"] for r in rows[::-1][:3]] and record.list_actions(open_only=True) == []
        assert record.action_transition(rows[0]["key"], "running") is None  # An ended action never moves again.
        # A restart: a running action ends as unknown, one never begun as cancelled, and the first delta tells both.
        ran = record.dispatch_action("act-ran", client=None, conversation="s1", description="Water the plants",
                                     order_text="water the plants")
        record.action_transition("act-ran", "running")
        record.dispatch_action("act-new", conversation="s1", description="Feed the cat", order_text="feed the cat")
        before = record.unread_actions(0, limit=100)[1]
        since = journal.Journal(path).open().recover_actions()
        assert since == before and ran["ledger_seq"] < since, (since, before)
        told, _ = record.unread_actions(since)
        assert [(r["key"], r["state"]) for r in told] == [("act-ran", "unknown"), ("act-new", "cancelled")], told
        assert json.loads(json.dumps(told))  # Rows are plain data, for relay.py actions over the socket.
        # A delta a turn carried but never finished cleanly is told again after a restart: only a seen seq is kept.
        record.seen_actions(since)
        assert journal.Journal(path).open().recover_actions() == since

    # Hands' session reads the harness stream: the setup turn first, then an order's progress, ask and result.
    class Harness:
        name = "Stand-in"

        def __init__(self):
            self.sent = []

        def begin(self, process, session, uuid, text):
            self.sent.append(("begin", text))

        def turn(self, process, session, uuid, text, shots, steer):
            self.sent.append(("turn", text, steer))

        def interrupt(self, process):
            self.sent.append(("interrupt",))

        def permit(self, process, ask, allowed, answers=None, reason=None):
            self.sent.append(("permit", ask["request_id"], allowed))

        def read(self, messages):
            return messages

    async def lines(stream):
        while line := await stream.readline():
            yield json.loads(line)

    async def session_check():
        class Process:
            returncode = None
            stdout = asyncio.StreamReader()

            def kill(self):
                self.returncode = -9
        process, stand_in = Process(), Harness()
        feed = process.stdout.feed_data
        session = HarnessSession(stand_in, process, "s", lines, "Setup, then reply ready.")
        beats, asks = [], []

        async def answer(ask):
            asks.append(ask["request_id"])
            return True, None, None
        running = asyncio.ensure_future(session.run("Order act-1: water the plants", lambda: beats.append(1), answer))
        await asyncio.sleep(0.02)
        assert stand_in.sent == [("begin", "Setup, then reply ready.")]  # No order before the setup turn ends.
        feed(json.dumps({"type": "result", "result": "ready"}).encode() + b"\n")
        await until(lambda: len(stand_in.sent) == 2, "order sent")
        session.steer("and the ferns")
        for message in ({"type": "stream_event", "event": {}},
                        {"type": "control_request", "request_id": "q1", "request": {"subtype": "can_use_tool",
                                                                                    "tool_name": "Bash", "input": {}}},
                        {"type": "result", "result": "Watering.\nThe plants are watered."}):
            feed(json.dumps(message).encode() + b"\n")
        ok, text = await running
        assert ok and one_line(text) == "The plants are watered." and beats and asks == ["q1"], (ok, text, beats, asks)
        assert stand_in.sent[1:] == [("turn", "Order act-1: water the plants", False), ("turn", "and the ferns", True),
                                     ("permit", "q1", True)], stand_in.sent
        process.stdout.feed_eof()  # The agent closed: the session is no longer alive, and its next order fails.
        await until(lambda: not session.alive, "closed")
        assert await session.run("Order act-2: x", lambda: None, answer) == (False, "Stand-in closed before the order.")
        # A cancel during the setup turn: no interrupt cuts the setup, and the order is never sent.
        process, stand_in = Process(), Harness()
        process.stdout = asyncio.StreamReader()  # The class's own stream ended above.
        session, cut = HarnessSession(stand_in, process, "s", lines, "Setup."), []
        running = asyncio.ensure_future(session.run("Order act-3: y", lambda: None, answer, lambda: bool(cut)))
        await asyncio.sleep(0.02)
        session.interrupt()
        cut.append(1)
        process.stdout.feed_data(json.dumps({"type": "result", "result": "ready"}).encode() + b"\n")
        assert await running == (False, CANCELLED_EARLY) and stand_in.sent == [("begin", "Setup.")], stand_in.sent
        session.close()
    asyncio.run(session_check())
    isolation_check()
    print("Silent outbox: all checks passed.")


def isolation_check():
    """Hands beside the main session on each agent, in scratch folders: runtime folders of its own, its plain prompt
    with no rewrite, and its cleanup leaves the main session's files alone. It starts no agent."""
    import tempfile
    from pathlib import Path
    names = ("XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR")
    saved = {name: os.environ.get(name) for name in names}
    with tempfile.TemporaryDirectory(prefix="rook-actions-check-") as folder:
        scratch = Path(folder)
        os.environ.update({name: str(scratch / name.lower()) for name in names})
        try:
            import antigravity_home
            import agy_harness
            import codex_harness
            import harness
            import pi_harness
            runtime = scratch / "xdg_runtime_dir"
            antigravity_home.HOME, antigravity_home.AGENTS = antigravity_home.home(), scratch / "agents"
            assert antigravity_home.HOME == runtime / "rook-antigravity", antigravity_home.HOME  # Never a live one.
            plugin = Path(__file__).resolve().parent.parent / "plugin"
            main_prompt = "You run in a full Claude Code session."
            # Each agent, the folder it builds, and the part of it that Hands' cleanup would remove if it shared it.
            agents = ((harness.Claude, "rook-claude", "rook-plugin", "rook-plugin"),
                      (agy_harness.Antigravity, "rook-antigravity", "config", agy_harness.APP),
                      (codex_harness.Codex, "rook-codex", "config.toml", "."),
                      (pi_harness.Pi, "rook-pi", "agent", "agent"))
            for kind, folder_name, inside, cleared in agents:
                main, hands = kind(), kind()
                hands.plain_prompt, hands.runtime_tag = True, "-hands"
                main.command(main_prompt, {}, "s1", plugin, ())
                argv = hands.command(HANDS_PROMPT, {}, "s2", plugin, ())
                own, theirs = runtime / folder_name, runtime / (folder_name + "-hands")
                assert (own / inside).exists() and (theirs / inside).exists(), (kind.name, sorted(runtime.iterdir()))
                paths = [arg for arg in argv if str(runtime) in arg]
                assert paths and all(str(theirs) in arg for arg in paths), (kind.name, paths)
                marker = own / cleared / "main-marker"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("main")
                hands.command(HANDS_PROMPT, {}, "s3", plugin, ())  # A new Hands launch rebuilds only its own files.
                if kind is agy_harness.Antigravity:
                    hands.cwd = main.cwd = folder
                    assert hands.system_append().startswith(HANDS_PROMPT) and str(theirs) in argv[argv.index(
                        "--gemini-dir") + 1] and f"{antigravity_home.TAG_VARIABLE}=-hands" in argv, argv
                    agy_harness.clear(hands.home)  # What the reader does when Hands' agy closes.
                    main.prompt = HANDS_PROMPT
                    try:
                        main.system_append()
                        raise AssertionError("Rook's main rewrite took Hands' prompt.")
                    except ValueError:
                        pass
                if kind is codex_harness.Codex:
                    hands.cwd = folder
                    assert hands.developer_instructions() == HANDS_PROMPT
                    codex_harness.clear(hands.home)  # What the reader does when Hands' Codex closes.
                if kind is pi_harness.Pi:
                    assert argv[argv.index("--append-system-prompt") + 1].startswith(HANDS_PROMPT), argv[-1][:80]
                assert marker.read_text() == "main", kind.name
            # The guard hook finds the folder of the session that started it, by the tag agy passes on.
            assert antigravity_home.home("-hands") == runtime / "rook-antigravity-hands"
            assert antigravity_home.home("/../x") == antigravity_home.home() == runtime / "rook-antigravity"
            assert {Path(os.path.realpath(runtime / name)) for name in ("rook-antigravity", "rook-antigravity-hands")
                    } <= set(antigravity_home.PROTECTED_ROOTS), antigravity_home.PROTECTED_ROOTS
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        check()
    else:
        sys.exit("Usage: python desktop/actions.py --check")
