"""Watch the T3 threads that Rook handed work to, and say when each finishes, stops, or needs the owner.

Rook notices a delegation in Claude's stream: a T3 tool call that sends to or launches a thread, or a
`t3 thread send` or `t3 thread start` command. It then polls each watched thread with
`t3 thread show <id> --json` about once a minute, locally or over SSH, as
machines.json says, and announces each change once through Rook's inbox. It also watches the Herdr agents that
relay.py herdr sends to, with one herdr agent get each, and says when one is blocked or done. Standard library only, so
relay.py can use it too.
"""

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import socket
import sys
import time

import desk
import herdr
import work  # Rook's work list, which the watcher keeps in step with each thread.
import settings  # noqa: E402
OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.


def pn(phrase, they=None):
    """The owner token for a phrase written with he, such as \"his\" or \"he asks\". A phrase with a verb
    gives its they form too."""
    return settings.token(phrase, they)



MACHINES = Path(__file__).with_name("machines.json")
LIMIT = 40  # Threads in the list at most. The oldest go first.
POLL_SECONDS = 60
SHOW_SECONDS = 25  # One t3 thread show, local or over SSH, may take this long before it counts as failed.
KEEP_SECONDS = 30 * 60  # A thread that finished with nothing pending is watched this much longer.
QUIET_SECONDS = 40 * 60  # A busy thread with no new item this long gets a silent "quiet since" mark.
UNREACHABLE_SECONDS = 2 * 3600  # A thread that cannot be read this long is dropped quietly.
BUSY = {"preparing", "queued", "starting", "running"}
STOPPED = {"failed", "interrupted", "cancelled", "rolled_back"}
OUTCOMES = {"finished": "finished its turn", "needs": f"is waiting for {OWNER} to answer a question or approve "
            "something in T3 Code", "failed": "stopped with a failure", "interrupted": "was interrupted",
            "cancelled": "was cancelled", "rolled_back": "was rolled back"}
THREAD_ID = r"(?:mcp:[A-Za-z0-9:_-]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
ENV_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
# A thread that a tell reported is quiet when its run ended within this long after the tell.
TELL_COVERS_SECONDS = 120
# Words of a t3 error for a thread that no longer exists.
GONE = ("not found", "no thread", "unknown thread", "no longer available", "thread_not_found")
# A watched Herdr agent's thread id: herdr:AGENT here, or herdr:MACHINE/AGENT on a saved Herdr machine.
HERDR = "herdr:"


_MACHINES_WARNING = None  # Last (path_str, reason) emitted once to stderr.
_LAST_MACHINES_ERROR = None  # Human-readable warning from the last machines() call, or None.


def machines_file():
    """User's machines.json under XDG_CONFIG_HOME/rook/machines.json."""
    return desk.config_dir() / "rook/machines.json"


def machines_error():
    """Warning message if the user's machines.json exists and is unreadable or invalid, else None."""
    return _LAST_MACHINES_ERROR


def _note_machines_error(path, reason):
    global _MACHINES_WARNING, _LAST_MACHINES_ERROR
    _LAST_MACHINES_ERROR = f"Ignoring invalid {path}: {reason}. Using this machine only."
    key = (str(path), reason)
    if _MACHINES_WARNING != key:
        _MACHINES_WARNING = key
        print(f"rook: {_LAST_MACHINES_ERROR}", file=sys.stderr)


def machines():
    """The machine table: each machine's environment id, the prefix that runs a command there (none for
    this machine, ssh for another), its t3 program, and the folder that holds its code projects.
    Reads ~/.config/rook/machines.json first, then the repo default; falls back to this machine locally."""
    global _MACHINES_WARNING, _LAST_MACHINES_ERROR
    user_path = machines_file()
    if user_path.exists() or user_path.is_symlink():
        try:
            table = json.loads(user_path.read_text())
        except (OSError, ValueError) as exc:
            _note_machines_error(user_path, str(exc))
        else:
            if not isinstance(table, dict):
                _note_machines_error(user_path, "expected a JSON object")
            elif table:
                entries = {name: entry for name, entry in table.items() if isinstance(entry, dict) and entry.get("t3")}
                if entries:
                    _LAST_MACHINES_ERROR = None
                    _MACHINES_WARNING = None
                    return entries
                _note_machines_error(user_path, "no machine entry has a 't3' path")
            else:
                _LAST_MACHINES_ERROR = None
                _MACHINES_WARNING = None
    else:
        _LAST_MACHINES_ERROR = None
    try:
        table = json.loads(MACHINES.read_text())
    except (OSError, ValueError):
        table = None
    if isinstance(table, dict) and table:
        entries = {name: entry for name, entry in table.items() if isinstance(entry, dict) and entry.get("t3")}
        if entries:
            return entries
    host = socket.gethostname().split(".")[0] or "local"
    return {host: {"environmentId": "", "run": [], "t3": "t3", "code": str(Path.home() / "Code")}}


def local_machine():
    """Name of the local machine entry (empty run prefix), or this host's short name when none is configured."""
    for name, entry in machines().items():
        if not (entry.get("run") or []):
            return name
    return socket.gethostname().split(".")[0] or "local"


def on(machine, *args):
    """The argv that runs args on a machine: directly here, or as one quoted command through its prefix."""
    entry = machines().get(machine)
    if entry is None:
        return None
    prefix = entry.get("run") or []
    return [*prefix, shlex.join(args)] if prefix else list(args)


def t3_on(machine, *args):
    """The argv that runs the t3 command on a machine."""
    entry = machines().get(machine)
    return entry and on(machine, entry["t3"], *args)


def herdr_thread(machine, agent):
    return HERDR + (f"{machine}/" if machine else "") + agent


def herdr_target(thread):
    """(saved Herdr machine or None, agent) of a watched Herdr agent's thread id."""
    machine, _, agent = thread[len(HERDR):].rpartition("/")
    return machine or None, agent


def machine_for(environment_id):
    """The machine a T3 tool call acted on. No environment id means this machine."""
    if not environment_id:
        return local_machine()
    return next((name for name, entry in machines().items() if entry.get("environmentId") == environment_id), None)


def ordinal(run_id):
    """The run's number within its thread, from a run id like run:thread:<id>:ordinal:3."""
    match = re.search(r":ordinal:(\d+)$", run_id or "")
    return int(match.group(1)) if match else None


def text_of(content):
    """A tool result's text, whether the stream gave a string or a list of text blocks."""
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content or () if isinstance(block, dict))


# What the t3 command prints after a send: Sent. when the message started a run, Queued. when it waits
# behind the running one. With --json it prints the tool's answer instead. Either may share the output with
# other lines, such as an update notice.
COMMAND_DELIVERY = {"Sent.": "started", "Queued.": "queued"}


def delegation(name, tool_input, result, failed):
    """Return (thread id, machine, title, first run to report, delivery) when a finished tool call handed work
    to a thread, else None. The first run is None when only the thread's next poll can tell it. The delivery is
    T3's word for what the message did: started a run, queued behind one, or steered into the running one."""
    if failed or not isinstance(tool_input, dict):
        return None
    if name in ("mcp__t3__t3_thread_send", "mcp__t3__t3_thread_launch"):
        try:
            data = json.loads(text_of(result))
        except ValueError:
            return None
        machine = machine_for(tool_input.get("environmentId"))
        if not isinstance(data, dict) or not data.get("threadId") or not machine:
            return None
        return data["threadId"], machine, tool_input.get("title"), ordinal(data.get("runId")), data.get("delivery")
    if name == "Bash":
        words = t3_thread_command(tool_input.get("command") or "")
        if words and words[0] == "send" and len(words) > 1 and re.fullmatch(THREAD_ID, words[1]):
            lines = [line.strip() for line in text_of(result).splitlines()]
            for line in lines:
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if isinstance(data, dict) and data.get("runId"):
                    return words[1], local_machine(), None, ordinal(data["runId"]), data.get("delivery")
            return words[1], local_machine(), None, None, next((COMMAND_DELIVERY[line] for line in lines if line in COMMAND_DELIVERY), None)
        if words and words[0] == "start" and (found := re.search(r"^\s*(" + THREAD_ID + r")\s*$", text_of(result), re.M)):
            title = words[words.index("--title") + 1] if "--title" in words[:-1] else None
            return found.group(1), local_machine(), title, 1, "started"
    return None


def pending(tool_input, result, failed):
    """What a finished t3_pending_request call showed, for Rook's mailbox: ("list", machine, thread, request ids)
    for a complete list, ("read", machine, thread, (request id, questions)), or ("respond", machine, thread,
    (request id, answers)) for an answer T3 accepted. A failed or unclear call shows nothing, so it gives None."""
    if failed or not isinstance(tool_input, dict) or not tool_input.get("threadId"):
        return None
    try:
        data = json.loads(text_of(result))
    except ValueError:
        return None
    machine, thread, action = machine_for(tool_input.get("environmentId")), str(tool_input["threadId"]), tool_input.get("action")
    if not machine or not isinstance(data, dict):
        return None
    if action == "list" and isinstance(data.get("requestIds"), list):
        return "list", machine, thread, [str(request) for request in data["requestIds"]]
    if action == "read" and data.get("requestId") and isinstance(data.get("questions"), list):
        return "read", machine, thread, (str(data["requestId"]), [q for q in data["questions"] if isinstance(q, dict)])
    if (action == "respond" and tool_input.get("requestId") and isinstance(tool_input.get("answers"), dict)
            and isinstance(data.get("sequence"), int)):
        return "respond", machine, thread, (str(tool_input["requestId"]), tool_input["answers"])
    return None


def t3_thread_command(command):
    """The words after "t3 thread" when the command run is t3 thread send or start, else None. A leading
    environment assignment and the skill's heredoc are allowed. Text that only mentions a send is not one."""
    try:
        words = shlex.split(command.split("\n", 1)[0], comments=True)
    except ValueError:
        return None
    while words and ENV_ASSIGNMENT.fullmatch(words[0]):
        words = words[1:]
    if len(words) < 3 or Path(words[0]).name != "t3" or words[1] != "thread" or words[2] not in ("send", "start"):
        return None
    # A heredoc marker ends the arguments, and nothing may follow on the line but the marker.
    rest = words[2:]
    if any(word.startswith("<<") for word in rest):
        rest = rest[:next(i for i, word in enumerate(rest) if word.startswith("<<"))]
    if any(word in ("|", "&&", "||", ";", ">", ">>") for word in rest):
        return None
    return rest


# The proof lines a brief asks a thread to end its report with, in their order, and one such line.
PROOF = ("Tested", "Not tested", "Links", "Deployed to", "Show", "Decision needed")
PROOF_LINE = re.compile(r"^[\s>*_-]*(" + "|".join(PROOF) + r")[*_]*\s*:[*_]*[ \t]*(.*?)[\s*_]*$", re.I | re.M)
# The first words of news that needs the owner, which a batch puts first.
DECISION = "A decision is needed: "
ANSWER = f"An answer from {OWNER} is needed."
MAYBE = f"A question may still need {OWNER}."


def last_words(messages):
    """What the thread said last: its "For Rook:" paragraph when it wrote one, else the end of its message. The
    summary is cut short for speech. The proof lines follow it whole, each on its own line, wherever they stood."""
    text = next((m.get("text") or "" for m in reversed(messages or ()) if m.get("role") == "assistant"), "")
    at = text.lower().rfind("for rook:")
    report = text[at + len("for rook:"):] if at >= 0 else text
    proof = {match[1].lower(): match[2] for match in PROOF_LINE.finditer(report)}  # The last of each counts.
    words = " ".join(PROOF_LINE.sub("", report).split())
    summary = words[:800] if at >= 0 else words if len(words) <= 400 else "..." + words[-400:]
    lines = [f"{label}: {proof[label.lower()]}".rstrip() for label in PROOF if label.lower() in proof]
    return "\n".join(part for part in (summary, *lines) if part)


# A Decision needed line that asks nothing: it starts with none, nothing, n/a, not needed, a dash, or a bare "no",
# such as "No." or "No decision needed", and holds no question mark. The brief's unfilled <template> asks nothing too.
NO_DECISION = re.compile(r"(none|nothing|n/?a|not (needed|required)|-+"
                         r"|no(\s*[.,;:!]|\s+(decision|need|question|action)|$))(\W|$)", re.I)


def decision(report):
    """The question in a report's Decision needed line, or None when the line is missing or asks nothing."""
    found = [match[2] for match in PROOF_LINE.finditer(report or "") if match[1].lower() == "decision needed"]
    question = found[-1].strip() if found else ""
    if not question or question.startswith("<") and question.endswith(">"):
        return None
    return None if NO_DECISION.match(question) and "?" not in question else question


def needs_owner(text):
    """Whether a message from the watcher or a thread needs the owner: a question, a decision, or a question that may
    have lapsed."""
    return text.startswith(DECISION) or bool(NEEDS_LINE.match(text))


# The two lines as saved: with the owner token, or with a name, as messages saved before tokens hold them.
NEEDS_LINE = re.compile(r"An answer from (?:⟦owner⟧|[^\n]{1,40}?) is needed\.|A question may still need (?:⟦owner⟧|[^\n]{1,40}?)\.")


def last_user(messages):
    """[run id, text] of the newest user message among messages, or None. A newer one after a question is an answer."""
    return next(([m.get("runId"), m.get("text")] for m in reversed(messages or ()) if m.get("role") == "user"), None)


def parent_of(thread, machine):
    """(machine, thread id, title or None) of the thread that delegated this one, or None. A local delegated task is a
    subagent child with a parent id. A task from another machine names its source in delegatedFrom. A fork is not a
    child here: it is the owner's own copy of a thread."""
    if thread.get("relationshipToParent") == "subagent" and thread.get("parentThreadId"):
        return machine, thread["parentThreadId"], None
    source = thread.get("delegatedFrom")
    if isinstance(source, dict) and source.get("threadId") and (home := machine_for(source.get("environmentId"))):
        return home, source["threadId"], source.get("title")
    return None


def classify(thread):
    """The state that matters to the owner: busy, needs, finished, a stopped state, or idle."""
    status = thread.get("status")
    # A question for the owner comes first: a thread that waits for their answer can still show as running.
    if (thread.get("pendingRequestCount") or 0) > 0:
        return "needs"
    if status in BUSY or thread.get("activeRunId") or status == "waiting":
        # Waiting with nothing pending means the thread waits on its own subagents or background tasks.
        return "busy"
    if status == "completed":
        return "finished"
    return status if status in STOPPED else "idle"


def watchlist():
    """The watch list file, under the state folder as it is at the call, not at import."""
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "rook/watching.json"


def load(path=None):
    path = watchlist() if path is None else path
    try:
        entries = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {(e["machine"], e["thread"]): e for e in entries if isinstance(e, dict) and e.get("thread") and e.get("machine")}


def save(entries, path=None):
    """Write the list atomically, private to the owner, keeping the newest LIMIT threads."""
    path = watchlist() if path is None else path
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    keep = sorted(entries.values(), key=lambda e: e.get("watched_at", 0))[-LIMIT:]
    temp = path.with_suffix(".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(keep, out, indent=1)
    temp.replace(path)


def add(entries, thread, machine=None, title=None, since=None, delivery=None):
    """Watch a thread for one more run that Rook started. since is the first run number to report. A second
    send keeps the first run's place, and each send is one run to report: the entry goes when all are. A
    message steered into a run counts as a send for that run, even the owner's own run, so its end is reported. A
    second message steered into a run already in runs adds no send, so that run is reported once. Every run
    of Rook's whose number is known is kept in runs."""
    machine = machine or local_machine()
    entry = entries.get((machine, thread)) or {"thread": thread, "machine": machine, "announced": [], "sends": 0}
    steered = delivery == "steered" and since in entry.get("runs", [])
    if steered:
        since = None
    elif since is not None:
        entry["runs"] = sorted(set(entry.get("runs", [])) | {since})[-10:]
    entry.pop("asked", None)  # A send is the owner's answer to a question the thread asked, carried by Rook.
    known = [run for run in (entry.get("since"), since) if run is not None]
    entry.update(watched_at=time.time(), since=min(known) if known else None, finished_at=None, failed_since=None,
                 sends=entry.get("sends", 0) + (0 if steered else 1))
    if entry["since"] is None and delivery in ("started", "queued"):
        # T3 confirmed the run, and names it as the thread's latest at once, even while it waits in the queue.
        entry["latest_is_ours"] = True
    entry["title"] = title or entry.get("title")
    entries[(machine, thread)] = entry
    return entry


def updated(thread):
    """When T3 last changed the thread, as a Unix time, or None."""
    try:
        return datetime.fromisoformat(thread["updatedAt"].replace("Z", "+00:00")).timestamp()
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


class Watcher:
    def __init__(self, path, announce, log):
        """announce(text, delivered, source) queues a message. Rook calls delivered() once the owner has it, or once it
        is dropped as old news, and only then is the outcome marked as reported. source names the thread, its
        parent, its run, and the mailbox item that holds what it needs from the owner, if any."""
        self.path, self.announce, self.log = path, announce, log
        self.entries = load(path)
        self.queued = set()  # (machine, thread, mark) announced but not yet delivered. Kept in memory only.
        self.held = []  # (text, delivered, source) for the news of the poll that runs, announced together at its end.
        # Rook sets this: capture(kind, summary, source) records what needs the owner in the mailbox, and returns the
        # item's id or None. It runs at every poll, before any mark decides whether to announce. A kind of None
        # says the thread's pending count is zero, which closes its waits.
        self.capture = None
        self.wake = asyncio.Event()
        self.work_error = None  # The last error from the work list, logged once.
        self.machines_error_logged = None  # The last machines.json warning logged once.

    def _check_machines_error(self):
        err = machines_error()
        if err and err != self.machines_error_logged:
            self.machines_error_logged = err
            self.log("machines_error", error=err)
        elif not err:
            self.machines_error_logged = None

    def keep_work(self, step, *args):
        """Keep Rook's work list in step with a thread. The list is data only: a failure is logged once and never
        stops the watcher, and no change here makes Rook speak."""
        try:
            with work.changing(self.path.with_name("work.json")) as data:
                step(data, *args, time.time())
            self.work_error = None
        except Exception as exc:
            if str(exc) != self.work_error:
                self.work_error = str(exc)
                self.log("work_error", error=str(exc))

    def add(self, thread, machine=None, title=None, since=None, delivery=None):
        machine = machine or local_machine()
        entry = add(self.entries, thread, machine, title, since, delivery)
        self.save()
        if not thread.startswith(HERDR):  # The work list names T3 threads only.
            self.keep_work(work.thread_sent, machine, thread, title, delivery)
        self.log("watch_added", thread=thread, machine=machine, since=entry["since"], sends=entry["sends"],
                 delivery=delivery)
        self.wake.set()

    def save(self):
        try:
            save(self.entries, self.path)
        except OSError as exc:
            self.log("watch_error", error=f"Could not save the watch list: {exc}")

    def listing(self):
        return [{key: entry.get(key) for key in ("thread", "machine", "title", "watched_at", "since", "finished_at",
                                                 "sends", "quiet_since")}
                for entry in sorted(self.entries.values(), key=lambda e: e.get("watched_at", 0))]

    async def show(self, entry):
        """Return (the thread's JSON, None) or (None, an error). A dead link never hangs, thanks to the timeout."""
        command = t3_on(entry["machine"], "thread", "show", entry["thread"], "--messages", "6", "--json")
        self._check_machines_error()
        if not command:
            err = machines_error()
            return None, f"No machine named {entry['machine']}." + (f" ({err})" if err else "")
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except OSError as exc:
            return None, str(exc)
        try:
            output, error = await asyncio.wait_for(process.communicate(), SHOW_SECONDS)
        except TimeoutError:
            process.kill()
            await process.wait()
            return None, "timed out"
        if process.returncode:
            return None, (error.decode(errors="replace").strip().splitlines() or [f"exit {process.returncode}"])[-1]
        try:
            return json.loads(output), None
        except ValueError:
            return None, "unreadable answer"

    async def note_tell(self, thread, asks=None):
        """A thread reported through relay.py tell. The next outcome of the run it reported from is quiet,
        when that run ends soon after the tell, since the tell already said it. asks is the decision the tell
        needs from the owner, which the run's work entry then waits on."""
        entry = next((e for (machine, t), e in self.entries.items() if t == thread), None)
        if entry:
            detail, _ = await self.show(entry)
            thread_state = (detail or {}).get("thread") or {}
            entry["reported"] = {"run": thread_state.get("activeRunId") or thread_state.get("latestRunId"),
                                 "at": time.time(), "decision": asks}
            self.save()

    def delivered(self, key, mark, state, run):
        """Mark an outcome as reported, once the owner has it. A finish or a stop uses up the sends it covers."""
        self.queued.discard((*key, mark))
        entry = self.entries.get(key)
        if not entry:
            return
        entry["announced"] = (entry["announced"] + [mark])[-10:]
        if state != "needs":
            self.finished(key, entry, run)
        self.save()

    def finished(self, key, entry, run):
        # One finish reports every run since the last report, and each of Rook's sends starts one run.
        done = (ordinal(run) or 0) + 1
        entry["sends"] = entry.get("sends", 1) - max(1, done - (entry.get("since") or done - 1))
        entry["since"] = done
        if entry["sends"] <= 0:
            del self.entries[key]  # Every run Rook started has been reported. The owner's own runs are not news.

    async def herdr(self, machine, *args, raw=False):
        """Return (one herdr call's result, None) or (None, an error), like show."""
        try:
            return await asyncio.to_thread(herdr.call, machine, *args, timeout=SHOW_SECONDS, raw=raw), None
        except herdr.Failed as failed:
            return None, f"{failed.code or 'error'}: {failed}"

    def stale_sends(self):
        """At a start: a Herdr send still marked sending was cut off when Rook stopped, so it may or may not have
        arrived. Mark each one unknown first, so it is told once and never sent again. Then tell the owner, and watch the
        agent, so its finish is told if the send did arrive."""
        path, now = self.path.with_name("herdr-sends.json"), time.time()
        rows = herdr.records(path)
        stale = [r for r in rows if r.get("outcome") == "sending" and now - (r.get("at") or 0) > 2 * herdr.SECONDS]
        if not stale:
            return
        for row in stale:
            row.update(outcome="unknown", result="Rook stopped mid-send", settled=now)
        try:
            herdr.write_records(rows, path)
        except OSError as exc:  # Unmarked rows are told at a later start instead.
            self.log("watch_error", error=f"Could not mark the Herdr sends: {exc}")
            return
        local = local_machine()
        for row in stale:
            machine, agent = row.get("machine"), str(row.get("agent"))
            thread = herdr_thread(machine, agent)
            self.announce(f"Rook stopped while it sent a message to the Herdr agent \"{agent}\" on "
                          f"{machine or local}. The message may or may not have arrived. " + settings.render(
                              f"Tell {OWNER} to check the agent in Herdr. Never send it again unless "
                              f"{pn('he asks', 'they ask')} after {pn('he')} checked."), lambda: None,
                          {"machine": local, "thread": thread, "title": agent, "outcome": "send outcome unknown"})
            self.add(thread, local, agent)

    def herdr_delivered(self, key, mark, finished, watched_at):
        """A Herdr agent's news reached the owner. A finish ends the watch, unless Rook sent to the agent again since."""
        self.queued.discard((*key, mark))
        if entry := self.entries.get(key):
            entry["announced"] = (entry["announced"] + [mark])[-10:]
            if finished and entry.get("watched_at") == watched_at:
                del self.entries[key]
            self.save()

    async def poll_herdr(self, key, entry, now):
        """Announce once when a watched Herdr agent is blocked, since it needs the owner, and once when it is done. A
        blocked agent is news only: the owner answers it in Herdr, and Rook never sends it keys."""
        machine, agent = herdr_target(entry["thread"])
        result, error = await self.herdr(machine, "agent", "get", agent)
        if error:
            if not entry.get("failed_since"):
                self.log("watch_unreachable", thread=entry["thread"], machine=entry["machine"], error=error)
            entry["failed_since"] = entry.get("failed_since") or now
            if error.startswith("agent_not_found") or now - entry["failed_since"] > UNREACHABLE_SECONDS:
                self.log("watch_dropped", thread=entry["thread"], machine=entry["machine"], error=error)
                self.entries.pop(key, None)
            return
        entry["failed_since"] = None
        info = result.get("agent") or {}
        state, seq = info.get("agent_status"), info.get("state_change_seq") or 0
        if entry.get("since") is None:
            # The state count just before Rook's send, from its intent record, else now: only later changes are news.
            sent = herdr.last_send(machine, agent, self.path.with_name("herdr-sends.json"))
            entry["since"] = sent["seq"] if sent and isinstance(sent.get("seq"), int) else seq
        finished = state in herdr.READY
        # A smaller count means the Herdr server restarted. A ready agent unchanged since the send never took it.
        if seq < entry["since"] or finished and seq == entry["since"] and now - entry.get("watched_at", now) > KEEP_SECONDS:
            self.log("watch_dropped", thread=entry["thread"], machine=entry["machine"], error=f"{state} at {seq}")
            self.entries.pop(key, None)
            return
        mark = f"herdr:{'finished' if finished else state}:{seq}"
        if (state != "blocked" and not finished or seq <= entry["since"] or mark in entry["announced"]
                or (*key, mark) in self.queued
                # done turning idle once the owner saw it in Herdr is the same finish.
                or finished and entry.get("told") == ["finished", seq - 1]):
            return
        entry["told"] = ["finished" if finished else state, seq]
        screen, _ = await self.herdr(machine, "agent", "read", agent, "--source", "recent-unwrapped", "--lines", "15",
                                     raw=True)
        said = herdr.screen_tail(screen, 15)[-800:]
        name = f"The Herdr agent \"{agent}\" ({info.get('agent') or 'agent'}) on {machine or entry['machine']}"
        # Rook's own words fill in. The agent's name and screen pass as they are.
        if finished:
            text = (f"{name} finished its turn. Its screen ends:\n{said or 'nothing readable'}\n" + settings.render(
                f"Tell {OWNER} what was done and what {pn('he has', 'they have')} to decide, if anything. Do not act on "
                "it as new work."))
        else:
            text = (settings.render(ANSWER) + f"\n{name} is blocked at a question or an approval. Its screen ends:\n"
                    f"{said or 'nothing readable'}\n" + settings.render(
                        f"Tell {OWNER} which agent needs {pn('him')}, and that {pn('he answers', 'they answer')} it in "
                        f"Herdr. Never send it keys or answer it for {pn('him')}."))
        source = {"machine": entry["machine"], "thread": entry["thread"], "title": entry.get("title") or agent,
                  "outcome": "finished its turn" if finished else "is blocked", "report": said}
        self.queued.add((*key, mark))
        watched_at = entry.get("watched_at")
        self.held.append((text, lambda: self.herdr_delivered(key, mark, finished, watched_at), source))
        self.log("watch_announced", thread=entry["thread"], machine=entry["machine"], state=state, run=mark)

    async def poll_one(self, key, entry, now):
        if entry["thread"].startswith(HERDR):
            return await self.poll_herdr(key, entry, now)
        detail, error = await self.show(entry)
        if error:
            gone = any(word in error.lower() for word in GONE)
            if not entry.get("failed_since"):
                self.log("watch_unreachable", thread=entry["thread"], machine=entry["machine"], error=error)
            entry["failed_since"] = entry.get("failed_since") or now
            if gone or now - entry["failed_since"] > UNREACHABLE_SECONDS:
                self.log("watch_dropped", thread=entry["thread"], machine=entry["machine"], error=error)
                self.entries.pop(key, None)
            return
        entry["failed_since"] = None
        thread = detail.get("thread") or {}
        entry["title"] = thread.get("title") or entry.get("title")
        # A delegated child's news goes to its parent's work entry, and its report names the parent.
        parent = parent_of(thread, entry["machine"])
        state, run = classify(thread), thread.get("latestRunId")
        if self.capture and thread.get("pendingRequestCount") == 0:
            await self.capture(None, None, {"machine": entry["machine"], "thread": entry["thread"]})
        if state == "needs":
            # Until the thread runs again, Rook sends to it, or a user message follows, the question is open.
            entry["asked"] = {"user": last_user(detail.get("messages"))}
        if entry.get("since") is None:
            # A send T3 confirmed is the latest run, even when it already ended. For any other send, the run
            # that is busy now carries it, else the next run will.
            entry["since"] = (ordinal(run) or 0) + (0 if state == "busy" or entry.pop("latest_is_ours", False) else 1)
        if state == "busy":
            entry["finished_at"] = None
            asked = entry.pop("asked", False)
            if thread.get("itemCount") != entry.get("items"):
                entry["items"], entry["active_at"] = thread.get("itemCount"), now
            entry["quiet_since"] = entry["active_at"] if now - entry.get("active_at", now) >= QUIET_SECONDS else None
            if not parent:
                self.keep_work(work.thread_news, *key, "busy", None, None)
                self.keep_work(work.thread_quiet, *key, entry["quiet_since"])
            elif asked:  # The child runs again after its question, so the parent's wait on it ends.
                self.keep_work(work.thread_news, *parent[:2], "busy", None, None)
            return
        entry["quiet_since"] = None
        messages, missing = detail.get("messages"), "none"
        ours = [n for n in entry.get("runs", []) if n >= entry["since"]]
        if ours and state != "needs" and (ordinal(run) or 0) > max(ours):
            # A later run, such as one the owner started, is the thread's latest, so Rook's own run already ended. Its
            # outcome is told with its own words: every message names the run it belongs to.
            run, state = re.sub(r":ordinal:\d+$", f":ordinal:{max(ours)}", run), "finished"
            messages = [m for m in messages or () if ordinal(m.get("runId")) in ours]
            missing = "not among the thread's latest messages, so read the thread for it"
        mark = f"{run}:{state}"
        # What the mailbox needs to make a self-contained item: the thread's title, what happened, and its report.
        source = {"machine": entry["machine"], "thread": entry["thread"], "parent_thread": parent and parent[1],
                  "run": run, "title": entry["title"], "outcome": OUTCOMES.get(state, state),
                  "report": last_words(messages)}
        if self.capture and state == "needs":
            source["item"] = await self.capture("needs", None,
                                                {**source, "pending_count": thread.get("pendingRequestCount")})
        elif self.capture and state == "finished" and (ordinal(run) or 0) >= entry["since"] and (
                asks := decision(source["report"])):
            reported = entry.get("reported")
            # A tell that named this run with the same question already put it in the mailbox.
            if not (isinstance(reported, dict) and reported.get("run") == run and reported.get("decision") == asks):
                source["item"] = await self.capture("decision", asks, source)
        if (state in OUTCOMES and (ordinal(run) or 0) >= entry["since"] and mark not in entry["announced"]
                and (*key, mark) not in self.queued):
            said = last_words(messages)
            reported = entry.pop("reported", None)
            told = isinstance(reported, dict) and reported.get("run") == run
            # A finish whose report asks the owner to decide waits on them. So may a run that ended after a question with
            # no user message after it: its request may have lapsed. An approval leaves no message, so this is a maybe.
            asks = (decision(said) or told and reported.get("decision")) if state == "finished" else None
            asked = entry.pop("asked", None) if state != "needs" else None
            before = asked.get("user") if isinstance(asked, dict) else None
            answered = asked and last_user(detail.get("messages")) != before
            lapsed = asked and not answered
            if answered:  # The owner answered in T3 Code, so the wait the question set ends, and this is a plain outcome.
                self.keep_work(work.thread_news, *(parent[:2] if parent else key), "busy", None, None)
            name = f"The thread \"{entry['title'] or entry['thread']}\" on {entry['machine']}"
            if parent:
                above = self.entries.get(parent[:2], {}).get("title") or parent[2]
                above = f"\"{above}\" ({parent[1]})" if above else parent[1]
                name = (f"A child thread, \"{entry['title'] or entry['thread']}\", that the thread {above} on "
                        f"{parent[0]} delegated,")
                self.keep_work(work.thread_news, *parent[:2], "needs" if state == "needs" else "decision" if asks
                               else "news", f"A child thread {OUTCOMES[state]}: {said}", asks or OUTCOMES[state])
            else:
                self.keep_work(work.thread_news, *key, "decision" if asks else state, said, asks or OUTCOMES[state])
            if told and (updated(thread) or now) - reported["at"] <= TELL_COVERS_SECONDS:
                # The thread's own tell already said this. Hide this one outcome, and only this one.
                entry["announced"] = (entry["announced"] + [mark])[-10:]
                if state != "needs":
                    self.finished(key, entry, run)
                return
            self.queued.add((*key, mark))
            # Rook's own words fill in. The thread's title, words and question pass as they are.
            render = settings.render
            if state == "needs":
                # A question or an approval is not a message, so the thread's words may say nothing about it.
                news = ((f"Its last message: {said}\n" if said else "") + render(
                    f"It waits for {OWNER}'s answer or approval. Read its pending request, or the thread, to tell "
                    f"{pn('him')} what it asks."))
            else:
                news = f"Its last message: {said or missing}"
            lead = (f"{DECISION}{asks}\n" if asks else render(f"{ANSWER}\n") if state == "needs" else
                    render(f"{MAYBE} The run ended after the thread asked {pn('him')} something. Read the thread to see "
                           f"whether {pn('he')} answered.\n") if lapsed else "")
            self.held.append((f"{lead}{name} {render(OUTCOMES[state])}. {news}\n"
                              + ("This child's work is part of that thread's work, not a new wish.\n" if parent else "")
                              + render(f"Tell {OWNER} what was done and what {pn('he has', 'they have')} to decide, if "
                                       "anything. Do not act on it as new work."),
                              lambda: self.delivered(key, mark, state, run), source))
            self.log("watch_announced", thread=entry["thread"], machine=entry["machine"], state=state, run=run)
        if state != "needs" and key in self.entries:
            entry["finished_at"] = entry.get("finished_at") or now
            if now - entry["finished_at"] > KEEP_SECONDS and not any(q[:2] == key for q in self.queued):
                del self.entries[key]

    async def poll(self):
        """Read every watched thread once, and announce each change once. Machines are read side by side, so a
        machine that does not answer never delays another; threads on one machine are read in turn."""
        now = time.time()
        by_machine = {}
        for key, entry in list(self.entries.items()):
            by_machine.setdefault(entry["machine"], []).append((key, entry))

        async def one_machine(pairs):
            for key, entry in pairs:
                if key in self.entries:
                    await self.poll_one(key, entry, now)

        try:
            await asyncio.gather(*(one_machine(pairs) for pairs in by_machine.values()))
        finally:
            # One poll's news reaches the inbox at one moment, so news of threads that ended together is one turn.
            held, self.held = self.held, []
            for text, delivered, source in held:
                self.announce(text, delivered, source)
        self.save()

    async def run(self):
        """Poll about once a minute while anything is watched. A new watch wakes it at once, even one added
        while a poll runs."""
        try:
            self.stale_sends()
        except Exception as exc:  # The watcher must never take Rook down.
            self.log("watch_error", error=str(exc))
        while True:
            self.wake.clear()
            if self.entries:
                try:
                    await self.poll()
                except Exception as exc:  # The watcher must never take Rook down.
                    self.log("watch_error", error=str(exc))
            try:
                await asyncio.wait_for(self.wake.wait(), POLL_SECONDS if self.entries else None)
            except TimeoutError:
                pass


def _check():
    """Self-check of Watcher and machines table using isolated scratch XDG folders and a fake t3 on PATH."""
    import tempfile
    # Messages saved with a name before owner tokens still need the owner, and so do token ones.
    name = settings.owner_name({"owner_name": "Test Owner"})
    assert needs_owner(f"An answer from {name} is needed.\nWhich file?") and needs_owner(f"A question may still need {name}. x")
    assert needs_owner(f"{ANSWER}\nWhich file?") and needs_owner(f"{MAYBE} x") and not needs_owner("Finished.")

    global MACHINES, _MACHINES_WARNING, _LAST_MACHINES_ERROR
    saved_machines = MACHINES
    saved_env = {k: os.environ.get(k) for k in (
        "HOME", "PATH", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")}
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="rkw-") as folder:
        base = Path(folder)
        home = base / "home"
        rt = base / "run"
        cfg = base / "config"
        state = base / "state"
        data = base / "data"
        cache = base / "cache"
        bin_dir = base / "bin"
        for d in (home, cfg, state, data, cache, bin_dir):
            d.mkdir(parents=True)
        rt.mkdir(mode=0o700)
        os.environ.update(
            HOME=str(home),
            PATH=str(bin_dir),
            XDG_RUNTIME_DIR=str(rt),
            XDG_CONFIG_HOME=str(cfg),
            XDG_STATE_HOME=str(state),
            XDG_DATA_HOME=str(data),
            XDG_CACHE_HOME=str(cache),
        )
        # Repo default machines.json stand-in: empty object so "no machines file" uses local fallback.
        empty_machines = base / "repo-machines.json"
        empty_machines.write_text("{}\n")
        MACHINES = empty_machines
        _MACHINES_WARNING = _LAST_MACHINES_ERROR = None

        t3_replies = base / "t3-replies.json"
        t3_calls = base / "t3-calls.jsonl"
        fake_t3 = bin_dir / "t3"
        fake_t3.write_text(
            f"#!{sys.executable}\n"
            "import json, pathlib, sys\n"
            f"calls = pathlib.Path({str(t3_calls)!r})\n"
            "with calls.open('a') as f: f.write(json.dumps(['local', sys.argv[1:]]) + '\\n')\n"
            f"table = json.loads(pathlib.Path({str(t3_replies)!r}).read_text())\n"
            "tid = sys.argv[3] if len(sys.argv) > 3 else ''\n"
            "reply = table.get(tid, {'rc': 1, 'stderr': 'thread not found'})\n"
            "if reply.get('rc', 0):\n"
            "    sys.stderr.write(reply.get('stderr', 'error') + '\\n')\n"
            "    raise SystemExit(reply['rc'])\n"
            "print(json.dumps(reply['data']))\n"
        )
        fake_t3.chmod(0o755)

        fake_remote = bin_dir / "fake-remote"
        fake_remote.write_text(
            f"#!{sys.executable}\n"
            "import json, pathlib, shlex, sys\n"
            "words = shlex.split(sys.argv[-1])\n"
            f"calls = pathlib.Path({str(t3_calls)!r})\n"
            "with calls.open('a') as f: f.write(json.dumps(['remote', words]) + '\\n')\n"
            f"table = json.loads(pathlib.Path({str(t3_replies)!r}).read_text())\n"
            "tid = words[3] if len(words) > 3 else ''\n"
            "reply = table.get('remote:' + tid, {'rc': 1, 'stderr': 'connection refused'})\n"
            "if reply.get('rc', 0):\n"
            "    sys.stderr.write(reply.get('stderr', 'error') + '\\n')\n"
            "    raise SystemExit(reply['rc'])\n"
            "print(json.dumps(reply['data']))\n"
        )
        fake_remote.chmod(0o755)

        def set_replies(data_map):
            t3_replies.write_text(json.dumps(data_map))

        async def run():
            # 1. One local machine with no machines.json file.
            m = machines()
            local = local_machine()
            assert list(m.keys()) == [local], f"watch.machines no-file fallback: {m}"
            assert m[local]["run"] == [] and m[local]["t3"] == "t3", m[local]
            assert t3_on(local, "thread", "show", "mcp:t-1") == ["t3", "thread", "show", "mcp:t-1"]

            # 2. Adding and listing a watch (plus private 0600 persistence).
            announced, logged = [], []
            wpath = state / "rook/watching.json"
            watcher = Watcher(wpath, lambda text, delivered, source=None: announced.append((text, delivered, source)),
                              lambda event, **fields: logged.append((event, fields)))
            tid1 = "mcp:11111111-1111-1111-1111-111111111111"
            watcher.add(tid1, title="Alpha task", since=1, delivery="started")
            listed = watcher.listing()
            assert len(listed) == 1 and listed[0]["thread"] == tid1 and listed[0]["machine"] == local, listed
            assert listed[0]["title"] == "Alpha task" and listed[0]["since"] == 1 and listed[0]["sends"] == 1, listed
            assert wpath.stat().st_mode & 0o777 == 0o600
            assert (local, tid1) in load(wpath), "watch.load did not reload saved watch"

            # 3. One poll that finds a thread finished.
            set_replies({
                tid1: {"rc": 0, "data": {
                    "thread": {"id": tid1, "title": "Alpha task", "status": "completed",
                               "latestRunId": f"run:thread:{tid1}:ordinal:1", "pendingRequestCount": 0},
                    "messages": [{"role": "assistant", "runId": f"run:thread:{tid1}:ordinal:1",
                                  "text": "For Rook: Built the widget.\nTested: unit checks"}],
                }}
            })
            await watcher.poll()
            assert len(announced) == 1, f"watch finish poll: expected 1 announcement, got {announced}"
            text, done_cb, source = announced[0]
            assert "finished its turn" in text and "Built the widget." in text and "Tested: unit checks" in text, text
            assert source["thread"] == tid1 and source["machine"] == local, source
            # Polling again before delivered() does not double-announce.
            await watcher.poll()
            assert len(announced) == 1, "watch finish poll: double-announced while queued"
            # Marking delivered consumes the send and removes the entry from the watch list.
            done_cb()
            assert (local, tid1) not in watcher.entries and watcher.listing() == [], watcher.entries

            # 4. A poll that fails (transient error stays watched; repeated fail does not spam watch_unreachable).
            tid2 = "mcp:22222222-2222-2222-2222-222222222222"
            watcher.add(tid2, title="Flaky thread", since=1, delivery="started")
            set_replies({tid2: {"rc": 1, "stderr": "connection refused"}})
            logged.clear()
            announced.clear()
            await watcher.poll()
            assert not announced, f"watch failing poll should not announce: {announced}"
            assert (local, tid2) in watcher.entries, "watch failing poll should keep entry"
            assert watcher.entries[(local, tid2)]["failed_since"] is not None
            assert [e for e, _ in logged].count("watch_unreachable") == 1, logged
            await watcher.poll()
            assert [e for e, _ in logged].count("watch_unreachable") == 1, "watch_unreachable should log once"

            # 5. The "dropped after two hours" rule (UNREACHABLE_SECONDS = 7200).
            assert UNREACHABLE_SECONDS == 2 * 3600
            watcher.entries[(local, tid2)]["failed_since"] = time.time() - UNREACHABLE_SECONDS + 120
            await watcher.poll()
            assert (local, tid2) in watcher.entries, "watch must not drop before 2 hours unreachable"
            watcher.entries[(local, tid2)]["failed_since"] = time.time() - UNREACHABLE_SECONDS - 5
            logged.clear()
            await watcher.poll()
            assert (local, tid2) not in watcher.entries, "watch must drop after 2 hours unreachable"
            assert any(e == "watch_dropped" and f.get("thread") == tid2 for e, f in logged), logged

            # Gone error ("thread not found") drops immediately.
            tid_gone = "mcp:33333333-3333-3333-3333-333333333333"
            watcher.add(tid_gone, title="Deleted thread", since=1, delivery="started")
            set_replies({tid_gone: {"rc": 1, "stderr": "Error: thread not found"}})
            await watcher.poll()
            assert (local, tid_gone) not in watcher.entries, "watch must drop gone thread immediately"

            # 6. Two machines (one local, one remote via run prefix).
            user_machines = cfg / "rook/machines.json"
            user_machines.parent.mkdir(parents=True, exist_ok=True)
            user_machines.write_text(json.dumps({
                "host-a": {"environmentId": "env-a", "run": [], "t3": "t3", "code": str(home / "Code")},
                "host-b": {"environmentId": "env-b", "run": [str(fake_remote)], "t3": "t3-remote", "code": "/srv/code"},
            }))
            m2 = machines()
            assert set(m2.keys()) == {"host-a", "host-b"}, m2
            assert local_machine() == "host-a"
            assert machine_for("env-a") == "host-a" and machine_for("env-b") == "host-b"
            assert t3_on("host-b", "thread", "show", "mcp:x") == [str(fake_remote), "t3-remote thread show mcp:x"]

            announced.clear()
            logged.clear()
            tid_a = "mcp:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            tid_b = "mcp:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            watcher.add(tid_a, machine="host-a", title="Local job", since=1, delivery="started")
            watcher.add(tid_b, machine="host-b", title="Remote job", since=2, delivery="started")
            set_replies({
                tid_a: {"rc": 0, "data": {
                    "thread": {"id": tid_a, "title": "Local job", "status": "completed",
                               "latestRunId": f"run:thread:{tid_a}:ordinal:1", "pendingRequestCount": 0},
                    "messages": [{"role": "assistant", "runId": f"run:thread:{tid_a}:ordinal:1", "text": "Local done."}],
                }},
                f"remote:{tid_b}": {"rc": 0, "data": {
                    "thread": {"id": tid_b, "title": "Remote job", "status": "completed",
                               "latestRunId": f"run:thread:{tid_b}:ordinal:2", "pendingRequestCount": 0},
                    "messages": [{"role": "assistant", "runId": f"run:thread:{tid_b}:ordinal:2", "text": "Remote done."}],
                }},
            })
            await watcher.poll()
            assert len(announced) == 2, f"two-machine poll: expected 2 announcements, got {announced}"
            by_machine = {src["machine"]: (txt, cb) for txt, cb, src in announced}
            assert set(by_machine.keys()) == {"host-a", "host-b"}, by_machine
            assert "on host-a" in by_machine["host-a"][0] and "Local done." in by_machine["host-a"][0]
            assert "on host-b" in by_machine["host-b"][0] and "Remote done." in by_machine["host-b"][0]
            for _, cb in by_machine.values():
                cb()
            assert watcher.listing() == []

            # One machine failing does not block the other machine's announcement.
            announced.clear()
            watcher.add(tid_a, machine="host-a", title="Local ok", since=3, delivery="started")
            watcher.add(tid_b, machine="host-b", title="Remote down", since=3, delivery="started")
            set_replies({
                tid_a: {"rc": 0, "data": {
                    "thread": {"id": tid_a, "title": "Local ok", "status": "completed",
                               "latestRunId": f"run:thread:{tid_a}:ordinal:3", "pendingRequestCount": 0},
                    "messages": [{"role": "assistant", "runId": f"run:thread:{tid_a}:ordinal:3", "text": "Still fine."}],
                }},
                f"remote:{tid_b}": {"rc": 255, "stderr": "ssh: connect to host timed out"},
            })
            await watcher.poll()
            assert len(announced) == 1 and announced[0][2]["machine"] == "host-a", announced
            assert ("host-b", tid_b) in watcher.entries and watcher.entries[("host-b", tid_b)]["failed_since"] is not None

        try:
            asyncio.run(run())
        finally:
            MACHINES = saved_machines
            _MACHINES_WARNING = _LAST_MACHINES_ERROR = None
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    print("Thread watcher: all checks passed.")


if __name__ == "__main__":
    _check()
