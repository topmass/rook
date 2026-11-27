"""Rook's session for clients that attach over HTTP, such as the owner's phone: the real session behind desktop/server.py.

It reads the record (desktop/journal.py) for what is durable, and the companion's memory for what is only live: Rook's
state, a waiting card, dark, and a waiting restart. A command from a device is admitted in the record before it runs,
so a retry with the same id never runs it twice, and a dropped connection leaves the work running.

A paired device has the same access as the desk: Rook is one system. Nothing here assumes the session lives on this
desktop. A request's client is the device that sent it, and what needs the desk (a screenshot, speech, the overlay)
stays behind the companion's own calls.
"""

import asyncio
from collections import OrderedDict, deque
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from uuid import uuid4

import desk
import journal
import mailbox
import relay
import server
import work
OWNER = relay.settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.
OWNER_START = relay.settings.OWNER_START_TOKEN  # The same, as the first word of a sentence.


def pn(phrase, they=None):
    """The owner token for a phrase written with he, such as \"his\" or \"he asks\". A phrase with a verb
    gives its they form too."""
    return relay.settings.token(phrase, they)



PORT = 47326  # The phone server's port on loopback. tailscale serve forwards the tailnet HTTPS name to it.
SERVE_PORT = 8447  # The HTTPS port tailscale serve gives the phone, so the server accepts that Host too.
TAILSCALE_SECONDS = 3  # How long one read of the tailnet name may wait for tailscale status.
NAME_RETRY_SECONDS = 60  # A request with an unknown Host reads the tailnet name again, at most this often.
ADMIT_SECONDS = 5  # A command whose admission write takes longer is refused with a 5xx, and the app retries it.
LIST_POLL_SECONDS = 5  # While a client is attached, the work list and the mailbox are checked this often for changes.
PHONE_LABEL = f"Images: none. {OWNER_START} typed this on {pn('his')} phone."
PHONE_SPOKEN_LABEL = f"Images: none. {OWNER_START} said this to {pn('his')} phone."
TEXT_LIMIT = 20000
AUDIO_EXTENSIONS = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a"}
SPEECH_MAX_CLIPS = 32  # Cap on rendered audio pieces kept in memory across devices.
SPEECH_MAX_BYTES = 16 * 1024 * 1024  # Cap on total rendered audio bytes kept in memory.
SPEECH_TTL_SECONDS = 300  # Rendered pieces expire after five minutes.
DRAFT_SECONDS = 0.25  # A client gets the answer so far at most four times a second.
ACTIVITY_LINES = 8  # The running turn's latest activity lines that a snapshot carries.
DETAIL_CHARACTERS = 80  # A shell command's detail is its first 80 characters, on one line.

# What Rook starts doing in a turn, as clients show it: each key's kind, from the protocol's table, and one plain
# sentence in Rook's voice. The kind also names the app's icon. Correct the words here, in one place.
ACTIVITY = {
    "thinking": ("thinking", "Thinking it over."),
    "speaking": ("speaking", "Saying the answer at the desk."),
    "card": ("waiting", f"Waiting for {OWNER} to answer a card."),
    "held": ("waiting", "Waiting for a command that runs in the background."),
    "wait thread": ("waiting", "Waiting for a thread to finish."),
    "read file": ("reading", "Reading a file."),
    "read thread": ("reading", "Reading a thread."),
    "read web": ("reading", "Reading a web page."),
    "read mailbox": ("reading", "Checking the mailbox."),
    "read skill": ("reading", "Reading a skill."),
    "search files": ("searching", "Searching the files."),
    "search web": ("searching", "Searching the web."),
    "search threads": ("searching", "Looking through the threads."),
    "run": ("running", "Running a command."),
    "edit file": ("editing", "Editing a file."),
    "edit work": ("editing", "Updating the work list."),
    "brief": ("editing", "Writing a brief for a build thread."),
    "steps": ("tool", "Keeping track of the steps."),
    "send": ("sending", "Sending a message to a thread."),
    "send build": ("sending", "Sending this to the {who} build thread."),
    "answer": ("sending", f"Sending {OWNER}'s answer to a thread."),
    "launch": ("launching", "Starting a new thread."),
    "show": ("showing", "Showing it on the desk."),
    "draw": ("drawing", "Drawing a diagram on the desk."),
    "clear": ("drawing", "Clearing the diagram from the desk."),
    "timer": ("timing", "Setting a timer."),
    "game": ("game", "Checking the game."),
    "t3": ("tool", "Using T3 Code."),
    "tool": ("tool", "Using a tool."),
}
FILE_TOOLS = {"Read": "read file", "NotebookRead": "read file", "Edit": "edit file", "MultiEdit": "edit file",
              "Write": "edit file", "NotebookEdit": "edit file"}
BUILT_INS = {"Grep": "search files", "Glob": "search files", "LS": "search files", "WebSearch": "search web",
             "WebFetch": "read web", "Skill": "read skill", "TodoWrite": "steps"}
def _build_names():
    return {thread: who.capitalize() for who, thread in relay.active_build_threads().items()}  # Said by name, never by id.
QUIET_TOOLS = ("ToolSearch", "AskUserQuestion")  # Loading tools says nothing, and a question shows as its card.
RELAY_KEYS = (("relay.py timer", "timer"), ("relay.py mailbox", "read mailbox"), ("relay.py work", "edit work"),
              ("relay.py handoff", "brief"), ("relay.py show", "show"), ("t3 thread send", "send"),
              ("t3 thread start", "launch"))


def tool_activity(name, args, title_of):
    """What a tool call starts, as (activity key, detail) or None to say nothing. detail is only a thread's title, a
    file's name, or a shell command's first 80 characters: nothing else of a tool's input. title_of(thread) gives a
    thread's title, or None; a build thread's key carries its name instead."""
    args = args if isinstance(args, dict) else {}
    if name in QUIET_TOOLS:
        return None
    if name in FILE_TOOLS:
        path = args.get("file_path") or args.get("notebook_path")
        return FILE_TOOLS[name], os.path.basename(path) if isinstance(path, str) and path else None
    if name in BUILT_INS:
        return BUILT_INS[name], None
    if name == "Bash":
        command = args.get("command")
        if not isinstance(command, str):  # Under Antigravity the input may come late: say only what is known.
            return "run", None
        key = next((key for marker, key in RELAY_KEYS if marker in command), "run")
        return key, " ".join(command.split())[:DETAIL_CHARACTERS] or None
    if name.startswith("mcp__"):
        server_name, tool = name.split("__")[1], name.split("__")[-1]
        thread = args.get("threadId") if isinstance(args.get("threadId"), str) else None
        if server_name == "render":
            return ("clear" if tool == "clear_scene" else "draw"), None
        if server_name == "wow":
            return "game", None
        if server_name != "t3":
            return "tool", None
        if tool == "t3_thread_launch":
            title = args.get("title")
            return "launch", title[:DETAIL_CHARACTERS] if isinstance(title, str) and title.strip() else None
        if tool == "t3_pending_request":
            return ("answer" if args.get("action") == "respond" else "read thread"), thread and title_of(thread)
        key = {"t3_thread_send": "send", "t3_thread_read": "read thread", "t3_thread_wait": "wait thread",
               "t3_thread_list": "search threads", "t3_thread_search": "search threads"}.get(tool, "t3")
        return key, thread and title_of(thread)
    return "tool", None


def devices_path():
    """The paired devices' file, beside the record's."""
    return journal.MAILBOX.with_name("devices.db")


def tailnet_name():
    """This machine's Tailscale HTTPS name, or None without Tailscale. Runs in a worker: it may wait."""
    try:
        done = subprocess.run([desk.tailscale_exe(), "status", "--json"], capture_output=True, text=True,
                              timeout=TAILSCALE_SECONDS, stdin=subprocess.DEVNULL)
        name = json.loads(done.stdout)["Self"]["DNSName"].rstrip(".") if done.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, AttributeError):
        return None
    return name or None


def card_question(request):
    """What a waiting card asks, in words a phone can show: its questions, or the tool's input as the desk shows it."""
    data = request.get("input") or {}
    if request.get("tool_name") == "AskUserQuestion" and isinstance(data, dict):
        return "\n".join(q["question"] for q in data.get("questions") or [] if isinstance(q, dict)
                         and isinstance(q.get("question"), str))
    return json.dumps(request.get("input"), indent=2)


def read_work():
    """The open work list for a client, led by project. A person reads no work number in it."""
    entries = [e for e in work.load()["entries"] if work.is_open(e)]
    entries.sort(key=lambda e: (e.get("project") or "", -(e.get("changed") or 0)))
    return [{"id": e["id"], "project": e.get("project"), "wish": e.get("wish"), "state": e.get("state"),
             "news": e.get("news"), "try": e.get("try")} for e in entries]


def read_mailbox():
    items = mailbox.items(("open",))
    return {"open": len(items), "items": [{"id": i["id"], "kind": i["kind"], "summary": i["summary"],
                                           "detail": i["detail"]} for i in items]}  # Data: Rook rendered its own words.


def list_marks(file):
    """What tells that the work list or the mailbox changed, cheap enough to check every few seconds."""
    try:
        work_mark = os.stat(work.worklist()).st_mtime_ns
    except OSError:
        work_mark = None
    conn = journal.reader(file)
    try:
        mail_mark = tuple(conn.execute("SELECT count(*), max(updated) FROM items").fetchone())
    except Exception:
        mail_mark = None
    finally:
        conn.close()
    return {"work": work_mark, "mailbox": mail_mark}


def write_audio_file(directory, turn, suffix, body):
    """Write an uploaded phone recording to a private 0600 temp file in directory and return its path."""
    folder = Path(directory)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    path = folder / f"{turn}-{secrets.token_hex(6)}{suffix}"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


class SpeechStore:
    """Bounded in-memory store for rendered phone speech clips, scoped by device and turn, with TTL."""

    def __init__(self, max_clips=SPEECH_MAX_CLIPS, max_bytes=SPEECH_MAX_BYTES, ttl_seconds=SPEECH_TTL_SECONDS):
        self.max_clips = max_clips
        self.max_bytes = max_bytes
        self.ttl_seconds = ttl_seconds
        self._items = OrderedDict()  # speech_id -> (device_id, turn, content_type, data, created_mono)
        self._bytes = 0
        self._lock = threading.Lock()

    def _prune(self, now):
        cutoff = now - self.ttl_seconds
        expired = [sid for sid, entry in self._items.items() if entry[4] < cutoff]
        for sid in expired:
            entry = self._items.pop(sid)
            self._bytes -= len(entry[3])
        while self._items and (len(self._items) > self.max_clips or self._bytes > self.max_bytes):
            _, entry = self._items.popitem(last=False)
            self._bytes -= len(entry[3])

    def put(self, device_id, turn, content_type, data, now=None):
        """Store one rendered clip and return its opaque id, or None if it exceeds max_bytes."""
        if not isinstance(data, bytes) or len(data) > self.max_bytes:
            return None
        stamp = time.monotonic() if now is None else now
        speech_id = secrets.token_urlsafe(18)
        with self._lock:
            self._prune(stamp)
            self._items[speech_id] = (device_id, turn, content_type, data, stamp)
            self._bytes += len(data)
            self._prune(stamp)
        return speech_id

    def get(self, device_id, speech_id, now=None):
        """Return (content_type, bytes) for this device and id, or None when absent, expired, or another device's."""
        stamp = time.monotonic() if now is None else now
        with self._lock:
            self._prune(stamp)
            entry = self._items.get(speech_id)
            if entry is None or entry[0] != device_id:
                return None
            return (entry[2], entry[3])

    def drop_turn(self, turn):
        """Drop every stored clip belonging to turn."""
        with self._lock:
            gone = [sid for sid, entry in self._items.items() if entry[1] == turn]
            for sid in gone:
                entry = self._items.pop(sid)
                self._bytes -= len(entry[3])
            return len(gone)

    def has_turn(self, turn, now=None):
        stamp = time.monotonic() if now is None else now
        with self._lock:
            self._prune(stamp)
            return any(entry[1] == turn for entry in self._items.values())

    def clear(self):
        with self._lock:
            self._items.clear()
            self._bytes = 0

    def stats(self, now=None):
        stamp = time.monotonic() if now is None else now
        with self._lock:
            self._prune(stamp)
            return len(self._items), self._bytes


class PhoneSession:
    """The session interface of server.py, over the companion. Stored events come from the record after their
    commit; live events come from the companion's loop. Subscribers are the server's stream pushes: they return at
    once and are safe from any thread."""

    def __init__(self, companion):
        self.c = companion
        self.subscribers = []
        self.lock = threading.Lock()
        self.running = set()  # (device, command id) of asks dispatched in this run.
        self.tasks = set()
        self.server = None
        self.lists_task = None
        self.marks = None  # The lists' marks as a client last read them, the watcher's baseline.
        self.lines = deque(maxlen=ACTIVITY_LINES)  # The running turn's activity, while a client is attached.
        self.draft_at = 0.0  # When the last draft went out, on the monotonic clock.
        self.draft_timer = None  # A draft that waits for the end of its window.
        self.drafted = (None, None)  # The turn and text of the last draft sent.
        self.speech_store = SpeechStore()  # Rendered phone audio clips, bounded in count, bytes, and age.
        self.voice_turns = {}  # turn: device_id for phone turns whose answers should be rendered as speech.
        self.speech_workers = {}  # turn: (device_id, asyncio.Queue, asyncio.Task) for ordered rendering.
        self.named_at = None  # When the tailnet name was last read, on the monotonic clock.
        self.local_presence_token = secrets.token_urlsafe(24) if desk.IS_MAC else None

    # Events.
    def publish(self, event):
        with self.lock:
            subscribers = list(self.subscribers)
        for push in subscribers:
            push(event)

    def stored(self, seq, kind, data):
        """The record's hook: an event committed, on the record's worker, in commit order."""
        if self.subscribers:
            self.publish(server.Event(kind, data, seq))

    def live(self, kind, data):
        """A live event, with no id: Rook's state, or a waiting card's full words. It is never stored."""
        if self.subscribers:
            self.publish(server.Event(kind, {**data, "live": True}))

    # Live activity and drafts. Each is called only when a client is attached: the caller checks subscribers first.
    def title_of(self, thread):
        """A thread's title for a person: from the watch list, then the work list. Never its id."""
        for (_, watched), entry in self.c.watcher.entries.items():
            if watched == thread and entry.get("title"):
                return entry["title"][:DETAIL_CHARACTERS]
        try:
            entries = work.load()["entries"]
        except Exception:
            return None
        return next((e["title"][:DETAIL_CHARACTERS] for e in reversed(entries)
                     if e.get("thread") == thread and e.get("title")), None)

    def activity(self, turn, key, detail=None, thread=None):
        """Push one activity line for this turn, and keep it for a snapshot. Never stored, never logged."""
        kind, label = ACTIVITY[key]
        build_names = _build_names()
        if key == "send" and thread in build_names:
            kind, label = ACTIVITY["send build"][0], ACTIVITY["send build"][1].format(who=build_names[thread])
            detail = None
        line = {"turn": turn, "kind": kind, "label": relay.settings.render(label), "icon": kind,
                **({"detail": detail} if detail else {})}
        if self.lines and self.lines[-1] == line:  # The same thing again, such as thinking after a card.
            return
        self.lines.append(line)
        self.live("activity", line)

    def tool(self, turn, name, args):
        """A tool call started in this turn."""
        found = tool_activity(name, args, self.title_of)
        if found:
            thread = args.get("threadId") if isinstance(args, dict) else None
            self.activity(turn, found[0], found[1], thread)

    def draft(self, turn, text, force=False):
        """The answer so far, whole, at most four times a second: a draft inside the window waits for its end, so a
        pause never leaves the phone behind. force sends it at once, as an empty draft when a tool call clears the
        commentary before it."""
        now = time.monotonic()
        if self.draft_timer:
            self.draft_timer.cancel()
            self.draft_timer = None
        if (turn, text) == self.drafted:  # Nothing new, such as a second tool call in a row.
            return
        if force or turn != self.drafted[0] or now - self.draft_at >= DRAFT_SECONDS:
            self.draft_at, self.drafted = now, (turn, text)
            self.live("draft", {"turn": turn, "text": text})
        else:
            self.draft_timer = self.c.loop.call_later(self.draft_at + DRAFT_SECONDS - now, self.draft, turn, text, True)

    def turn_ended(self):
        """No turn runs any more: its activity lines go, and a draft still waiting is dropped."""
        self.lines.clear()
        if self.draft_timer:
            self.draft_timer.cancel()
            self.draft_timer = None

    # Phone voice rendering and clip serving.
    def wants_voice(self, turn):
        return turn in self.voice_turns

    def has_speech(self, turn):
        return turn in self.speech_workers or self.speech_store.has_turn(turn)

    def queue_speech(self, turn, parts):
        """Queue spoken text pieces for ordered rendering and live speech announcements for turn's device."""
        device_id = self.voice_turns.get(turn)
        if not device_id or not parts:
            return
        cleaned = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
        if not cleaned:
            return
        worker = self.speech_workers.get(turn)
        if worker is None:
            q = asyncio.Queue()
            task = self.c.loop.create_task(self._render_speech_worker(turn, device_id, q))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            worker = (device_id, q, task)
            self.speech_workers[turn] = worker
        for part in cleaned:
            worker[1].put_nowait(part)

    def finish_speech_queue(self, turn):
        """Signal that no more spoken pieces will arrive for turn; let queued renders drain in order."""
        self.voice_turns.pop(turn, None)
        worker = self.speech_workers.get(turn)
        if worker is not None:
            worker[1].put_nowait(None)

    async def _render_speech_worker(self, turn, device_id, q):
        index = 0
        try:
            while True:
                text = await q.get()
                if text is None:
                    return
                has_voice = bool(self.c.voice and self.c.voice.returncode is None)
                rendered = await self.c.render_speech(text)
                if rendered is None:
                    if not has_voice:
                        print("rook: speech render skipped: voice unavailable", file=sys.stderr)
                    continue
                content_type, data = rendered
                speech_id = self.speech_store.put(device_id, turn, content_type, data)
                if speech_id is None:
                    print("rook: speech render skipped: clip exceeds store cap", file=sys.stderr)
                    continue
                self.live("speech", {"turn": turn, "index": index, "id": speech_id, "text": text, "device": device_id})
                index += 1
        except asyncio.CancelledError:
            raise
        finally:
            current = self.speech_workers.get(turn)
            if current is not None and current[1] is q:
                del self.speech_workers[turn]

    def stop_speech(self, turn):
        """Cancel queued or active speech renders for turn and drop its stored clips."""
        self.voice_turns.pop(turn, None)
        worker = self.speech_workers.pop(turn, None)
        if worker is not None:
            worker[2].cancel()
        self.speech_store.drop_turn(turn)

    def stop_device_speech(self, device_id):
        """Stop the speech of every turn that plays on this device, and nothing at the desk."""
        for turn in {turn for turn, worker in self.speech_workers.items() if worker[0] == device_id} | {
                turn for turn, device in self.voice_turns.items() if device == device_id}:
            self.stop_speech(turn)

    def speech(self, device_id, speech_id):
        """Return (content_type, bytes) for one rendered piece only to the device that asked, while kept."""
        return self.speech_store.get(device_id, speech_id)

    def subscribe(self, callback):
        with self.lock:
            self.subscribers.append(callback)
        if self.lists_task is None or self.lists_task.done():
            self.lists_task = self.c.loop.create_task(self.watch_lists())

    def unsubscribe(self, callback):
        with self.lock:
            if callback in self.subscribers:
                self.subscribers.remove(callback)

    def high_water(self):
        return self.c.journal.high

    async def events_after(self, cursor, upto):
        rows = await asyncio.to_thread(journal.read_events, self.c.journal.file, cursor, upto)
        return None if rows is None else [server.Event(kind, data, seq) for seq, kind, data in rows]

    async def watch_lists(self):
        """While a client is attached, note when the work list or the mailbox changed, as a stored event, so a
        client that reconnects reads it again. Its baseline is the marks taken before the last snapshot read the
        lists, so a change made in between is noted too. A client reads the work list again when its stream opens."""
        if self.marks is None:
            self.marks = await asyncio.to_thread(list_marks, self.c.journal.file)
        while self.subscribers and self.server:
            await asyncio.sleep(LIST_POLL_SECONDS)
            now = await asyncio.to_thread(list_marks, self.c.journal.file)
            for name in ("work", "mailbox"):
                if now[name] != self.marks[name]:
                    try:
                        self.c.journal_write("lists_changed", name)
                    except RuntimeError:  # Rook stopped, and the record's worker with it.
                        return
            self.marks = now

    # Reads.
    def card(self):
        """The waiting card from the companion's memory, with its id, or None."""
        message = self.c.permission
        if not message:
            return None
        request = message.get("request") or {}
        ask = request.get("tool_name") == "AskUserQuestion"
        options = [option.get("label", "") for question in ((request.get("input") or {}).get("questions") or [])
                   if isinstance(question, dict) for option in question.get("options") or [] if isinstance(option, dict)]
        return {"id": message.get("card"), "turn": self.c.latest_turn,
                "tool": None if ask else request.get("tool_name"), "question": card_question(request),
                "options": options, "desk": ask, "count": self.c.card_count()}

    def running_activity(self):
        """The running turn's latest activity lines. A client that attaches mid-turn, with none kept while nobody was
        attached, gets one line from what the desk shows now, as it is known."""
        turn = self.c.latest_turn if self.c.latest_turn in self.c.pending_turns else None
        if turn is None:
            return []
        if self.lines:
            return [line for line in self.lines if line["turn"] == turn]
        state = self.c.overlay_last.get("state")
        key = {"thinking": "thinking", "permission": "card", "speaking": "speaking"}.get(state)
        if state == "thinking" and self.c.overlay_last.get("activity"):
            found = tool_activity(self.c.overlay_last["activity"], {}, lambda thread: None)
            key = found[0] if found else key
        if not key:
            return []
        kind, label = ACTIVITY[key]
        return [{"turn": turn, "kind": kind, "label": relay.settings.render(label.format(who="build")), "icon": kind}]

    def restart(self):
        grant, wait = self.c.restart_grant if self.c.stopping() else None, self.c.active_restart_wait()
        if grant:
            return {"kind": grant.get("kind"), "reason": grant.get("reason"), "waiting": False}
        if wait:
            return {"kind": wait.get("kind"), "reason": wait.get("reason"), "waiting": True}
        return None

    async def snapshot(self, device_id):
        if not (self.lists_task and not self.lists_task.done()):  # A running watcher's baseline is older still.
            self.marks = await asyncio.to_thread(list_marks, self.c.journal.file)  # Before the lists are read.
        durable = await asyncio.to_thread(journal.read_snapshot, self.c.journal.file, self.c.journal.client)
        live = {"state": "dark" if self.c.dark and self.c.overlay_last.get("state") in (None, "ready", "hidden", "result")
                else self.c.overlay_last.get("state") or "ready",
                "card": self.card(), "dark": bool(self.c.dark), "restart": self.restart(),
                "held": getattr(self.c, "held_waiting", None)}
        listed, mail, focus = await asyncio.gather(asyncio.to_thread(read_work), asyncio.to_thread(read_mailbox),
                                                   asyncio.to_thread(mailbox.focus_get))
        live["activity"] = self.running_activity()
        return {**durable, **live, "work": listed, "mailbox": mail,
                "focus": focus and {"topic": focus.get("topic"), "until": focus.get("until")}}

    async def work(self):
        return await asyncio.to_thread(read_work)

    async def mailbox(self):
        return await asyncio.to_thread(read_mailbox)

    # Commands.
    async def admit(self, *args):
        """Admit a command in the record, before it runs. A write that fails or is slow refuses the command: the app
        sends it again with the same id."""
        future = self.c.journal_writes.submit(self.c.journal.admit, *args)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(future), ADMIT_SECONDS)
        except Exception as error:
            raise RuntimeError("The command could not be admitted.") from error

    async def command(self, device_id, body):
        if not self.c.journal:
            raise server.CommandError(503, "Rook's record is unavailable, so it takes no commands now.")
        if body.get("kind") == "ask":
            return await self.ask(device_id, body)
        if body.get("kind") == "card":
            return await self.answer_card(device_id, body)
        if body.get("kind") == "stop":
            return await self.stop_command(device_id, body)
        raise server.CommandError(400, "Rook does not know that command.")

    async def ask(self, device_id, body):
        text, mode = body.get("text"), body.get("mode", "queue")
        if not isinstance(text, str) or not text.strip() or len(text) > TEXT_LIMIT:
            raise server.CommandError(400, "Type a request of up to twenty thousand characters.")
        made = body.get("at")  # When the app first made it: a resend older than the record's memory of ids is refused.
        if isinstance(made, (int, float)) and not isinstance(made, bool) and \
                time.time() - made > journal.COMMAND_KEEP_SECONDS:
            raise server.CommandError(400, "Not sent: too old. Send it again.")
        if mode == "steer":  # A device's turn would silence the desk's answer until answers go to each client.
            raise server.CommandError(400, "The phone cannot join Rook's running turn yet. Send it as a new request.")
        if mode != "queue":
            raise server.CommandError(400, "The mode is queue.")
        text = text.strip()
        voice = body.get("voice") is True
        key = (device_id, body["id"])
        fingerprint = hashlib.sha256(json.dumps(["ask", text, mode, voice]).encode()).hexdigest()
        turn = str(uuid4())
        status, turn, row = await self.admit(device_id, body["id"], fingerprint, "ask", turn, self.c.session, text)
        if status == "conflict":
            raise server.CommandError(409, "That command id was already used for another request.")
        answer = {"ok": True, "turn": turn, "status": status}
        if status == "duplicate":
            state = await asyncio.to_thread(self.request_state, turn)
            answer["state"] = state
            # An admission that timed out on the way may have landed: a retry runs it, once, if it never ran.
            if state != "queued" or key in self.running or row["status"] != "admitted":
                return answer
        if voice:
            self.voice_turns[turn] = device_id
        self.running.add(key)
        task = self.c.loop.create_task(self.run_ask(device_id, body["id"], turn, text))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return answer

    async def audio(self, device_id, command_id, content_type, body):
        """Admit a phone voice recording durably in state hearing, then transcribe and dispatch off the loop."""
        if not self.c.journal:
            raise server.CommandError(503, "Rook's record is unavailable, so it takes no recordings now.")
        if not isinstance(body, (bytes, bytearray)) or not body:
            raise server.CommandError(400, "The audio recording is empty.")
        raw = bytes(body)
        fingerprint = hashlib.sha256(raw).hexdigest()
        key = (device_id, command_id)
        turn = str(uuid4())
        status, turn, row = await self.admit(device_id, command_id, fingerprint, "speak", turn, self.c.session, "", "spoken")
        if status == "conflict":
            raise server.CommandError(409, "That command id was already used for another recording.")
        if status == "busy":
            raise server.CommandError(429, "Rook is still hearing your last recording.")
        answer = {"ok": True, "turn": turn, "status": status}
        if status == "duplicate":
            state = await asyncio.to_thread(self.request_state, turn)
            answer["state"] = state
            if state != "hearing" or key in self.running or row["status"] != "admitted":
                return answer
        self.running.add(key)
        task = self.c.loop.create_task(self.run_audio(device_id, command_id, turn, content_type, raw))
        body = raw = None
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return answer

    async def run_audio(self, device_id, command_id, turn, content_type, body):
        """Write an uploaded recording to a private temp file, transcribe it, delete the file, and dispatch if spoken."""
        path = None
        text = None
        logger = getattr(self.c, "perf_log", None)
        trace = logger.begin("spoken", "phone_upload") if logger else None
        if trace:
            trace.turn = turn
            trace.begin("recognition")
        try:
            mime = (content_type or "").split(";", 1)[0].strip().lower()
            suffix = AUDIO_EXTENSIONS.get(mime, ".bin")
            path = await asyncio.to_thread(write_audio_file, self.c.audio_dir(), turn, suffix, body)
            body = None
            text = await self.c.transcribe_file(path, content_type=content_type)
        except Exception as error:
            print(f"rook: phone audio failed: {type(error).__name__}", file=sys.stderr)
            text = None
        finally:
            if trace:
                trace.end("recognition", complete=text is not None)
            body = None
            if path is not None:
                path.unlink(missing_ok=True)
        if text is None:
            if trace:
                trace.finish("recognition_failed")
            self.c.journal_write("empty_audio", turn, "failed")
            self.c.journal_write("command_done", device_id, command_id, "failed")
            return
        cleaned = text.strip()[:TEXT_LIMIT]
        if not cleaned:
            if trace:
                trace.finish("empty_transcript")
            self.c.journal_write("empty_audio", turn, "empty")
            self.c.journal_write("command_done", device_id, command_id, "empty")
            return
        self.voice_turns[turn] = device_id
        future = self.c.journal_write("heard", turn, cleaned)
        moved = False
        if future is not None:
            try:
                moved = await asyncio.wrap_future(future) is True
            except Exception:
                moved = False
        if not moved:
            if trace:
                trace.finish("not_dispatched")
            self.voice_turns.pop(turn, None)
            self.c.journal_write("command_done", device_id, command_id, "failed")
            return
        await self.run_ask(device_id, command_id, turn, cleaned, label=PHONE_SPOKEN_LABEL, source="spoken", trace=trace)

    def request_state(self, turn):
        conn = journal.reader(self.c.journal.file)
        try:
            row = conn.execute("SELECT state FROM requests WHERE turn = ?", (turn,)).fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    async def run_ask(self, device_id, command_id, turn, text, label=PHONE_LABEL, source="typed", trace=None):
        """Give a phone's request to the agent. It waits its turn as a typed ask does: the turn lock, then an idle
        Rook. No screenshot: the desk is not the phone. A stop word cuts the running turn first, as at the desk."""
        timings = {}
        if trace:
            trace.begin("queue")
            timings["timing"] = {"perf": trace}
        try:
            heeded = await self.c.heed_stop(text, client=device_id) if source == "spoken" else None
            if heeded is True:  # A bare stop: nothing goes to the agent.
                if trace:
                    trace.finish("stopped")
                self.voice_turns.pop(turn, None)
                self.c.journal_write("close", [turn], "closed", "stop")
                self.c.journal_write("command_done", device_id, command_id, "done")
                return
            async with self.c.turn_lock:
                await self.c.ensure_agent()
                while True:  # A turn that started inside submit sends this one back here, to wait again.
                    while not self.c.idle():
                        await asyncio.sleep(0.25)
                    if self.c.exit.is_set():  # Rook is stopping: its row stays queued, and the next start gives it.
                        if trace:
                            trace.finish("deferred")
                        self.voice_turns.pop(turn, None)
                        return
                    if await self.c.submit(text, relay.settings.render(label), (), source=source, note=heeded or None, turn=turn,
                                           client=device_id, **timings) is not False:
                        break
        except Exception as error:  # Its row stays queued, and the next start gives it again.
            if trace:
                trace.finish("not_dispatched")
            self.voice_turns.pop(turn, None)
            self.c.log("phone_ask_failed", turn=turn, error=repr(error))
            self.c.journal_write("command_done", device_id, command_id, "failed")
            return
        self.c.journal_write("command_done", device_id, command_id, "dispatched")

    async def stop_command(self, device_id, body):
        """Stop the turn the device names, as the desk's Stop does, if it is the one running. Every device has the
        desk's access, so a phone stops a desk turn too. A turn that ended answers stale."""
        turn = body.get("turn")
        if not isinstance(turn, str) or not turn:
            raise server.CommandError(400, "A stop names its turn.")
        fingerprint = hashlib.sha256(json.dumps(["stop", turn]).encode()).hexdigest()
        status, _, row = await self.admit(device_id, body["id"], fingerprint, "stop")
        if status == "conflict":
            raise server.CommandError(409, "That command id was already used for another command.")
        if status == "duplicate":
            return json.loads(row["result"]) if row["result"] else {
                "ok": False, "error": "Rook stopped before it took that stop. Stop the turn again if it still runs."}
        result = {"ok": True} if self.c.stop_turn(turn) else {"ok": False, "error": "stale"}
        self.c.journal_write("command_done", device_id, body["id"], "done", result)
        return result

    async def answer_card(self, device_id, body):
        card_id, allow = body.get("card"), body.get("allow")
        if not isinstance(card_id, str) or not card_id or not isinstance(allow, bool):
            raise server.CommandError(400, "A card answer names its card and says allow or decline.")
        fingerprint = hashlib.sha256(json.dumps(["card", card_id, allow]).encode()).hexdigest()
        status, _, row = await self.admit(device_id, body["id"], fingerprint, "card")
        if status == "conflict":
            raise server.CommandError(409, "That command id was already used for another answer.")
        if status == "duplicate":
            return json.loads(row["result"]) if row["result"] else {
                "ok": False, "error": "Rook stopped before it took that answer. Answer again if the card still waits."}
        # The card is compared and consumed in one step on the loop, with no await between.
        message = self.c.permission
        request = (message or {}).get("request") or {}
        if not message or message.get("card") != card_id:
            result = {"ok": False, "error": "stale"}
        elif request.get("tool_name") == "AskUserQuestion":
            result = {"ok": False, "error": "Answer this question at your desk."}
        else:
            self.c.answer_permission(allow, None, card=card_id)
            result = {"ok": True}
        self.c.journal_write("command_done", device_id, body["id"], "done", result)
        return result

    # The server's life.
    async def start(self, port=PORT, secure_cookies=True, pair_on_loopback=False):
        """Start the server on loopback, then learn the tailnet name. Rook starts it as a task of its own, after the
        agent, so it never holds Rook up. A server that cannot start leaves Rook working, with one journal line."""
        try:
            store = await asyncio.to_thread(lambda: server.DeviceStore(devices_path()).open())
            extra = {"local_token": self.local_presence_token} if desk.IS_MAC else {}
            self.server = await server.Server(self, store, port=port, on_unknown_host=self.unknown_host,
                                              on_paired=lambda: self.c.phone_paired(),
                                              static_dir=Path(__file__).resolve().parent.parent / "phone",
                                              secure_cookies=secure_cookies, pair_on_loopback=pair_on_loopback,
                                              **extra).start()
        except Exception as error:
            print(f"rook: the phone server did not start: {type(error).__name__}", file=sys.stderr)
            self.server = None
            return None
        self.c.journal.on_event = self.stored
        await self.read_name()
        return self.server

    async def read_name(self):
        """Read the tailnet name off the loop, and let the server accept it. No Tailscale: loopback only."""
        self.named_at = time.monotonic()
        name = await asyncio.to_thread(tailnet_name)
        if name and self.server:
            self.server.allow_hosts([name, f"{name}:{SERVE_PORT}"])

    def unknown_host(self, host):
        """A request came with a Host the server refused: read the tailnet name again, at most once a minute, so a
        Tailscale that came up after Rook heals without a restart."""
        if self.named_at is None or time.monotonic() - self.named_at >= NAME_RETRY_SECONDS:
            self.named_at = time.monotonic()
            self.c.loop.create_task(self.read_name())

    async def stop(self):
        if self.lists_task:
            self.lists_task.cancel()
        for turn in list(self.speech_workers):
            self.stop_speech(turn)
        self.speech_store.clear()
        if self.server:
            server, self.server = self.server, None
            await server.close()
