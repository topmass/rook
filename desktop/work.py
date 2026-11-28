"""Rook's work list: one entry per wish the owner handed to a T3 thread, kept across restarts and days.

relay.py work adds, changes and lists the entries. The thread watcher moves an entry when its thread runs, asks, stops
or finishes. The startup turn carries a few lines from it. The file holds the owner's words, so it stays private (mode 0600)
and never leaves this machine. Standard library only, so watch.py and relay.py can use it. Run this file to check its
logic: python desktop/work.py
"""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import time
import settings  # noqa: E402
OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.
OWNER_START = settings.OWNER_START_TOKEN  # The same, as the first word of a sentence.


def worklist():
    """The work list file, under the state folder as it is at the call, not at import."""
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "rook/work.json"


def _local_machine():
    """Name of the local machine from user machines.json (empty run prefix), else this host's short name."""
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "rook/machines.json"
    try:
        table = json.loads(cfg.read_text())
    except (OSError, ValueError):
        table = None
    if isinstance(table, dict):
        for name, entry in table.items():
            if isinstance(entry, dict) and entry.get("t3") and not (entry.get("run") or []):
                return name
    return socket.gethostname().split(".")[0] or "local"
STATES = ("drafted", "sent", "running", "waiting", "done", "live", "dropped")
OPEN = ("drafted", "sent", "running", "waiting")
FINISHED = ("done", "live")
# A finished entry leaves the default listing this long after it finished. It stays in the file.
WEEK = 7 * 86400
LINE = 300  # A one-line field is cut to this many characters.
BRIEF = 20000  # The longest brief the list keeps.
# The watcher's words for what a thread waits on: a question or approval in T3 Code, one that may have lapsed when
# the run ended after it, and a decision its report asks for.
NEEDS = f"{OWNER}'s answer or approval in T3 Code"
LAPSED = "a check of a question the thread asked before its run ended"
DECISION = f"{OWNER_START}'s decision: "
# The answer line as saved: with the owner token, or with a name, as entries saved before tokens hold it.
NEEDS_LINE = re.compile(r"(?:⟦owner⟧|[^\n]{1,40}?)'s answer or approval in T3 Code")


def asks(waits_on):
    """Whether an entry waits on the owner's answer to a thread's question, whatever name it was saved with."""
    return waits_on == LAPSED or bool(NEEDS_LINE.fullmatch(waits_on or ""))
# The startup turn names at most this many entries in each group.
CATCH_UP = 5


class Unreadable(Exception):
    """The file exists but is not a work list. Nothing writes over it, so no entry is lost."""


def empty():
    return {"next_id": 1, "entries": []}


def well_formed(entry):
    """Whether an entry has every field the list's code reads, each of a type it can use. A hand edit can break that."""
    def number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return (isinstance(entry, dict) and isinstance(entry.get("id"), int) and entry.get("state") in STATES
            and isinstance(entry.get("machine"), str) and isinstance(entry.get("thread"), (str, type(None)))
            and number(entry.get("changed")) and (entry["state"] not in FINISHED or number(entry.get("finished")))
            and all(entry.get(key) is None or number(entry[key]) for key in ("finished", "live_at", "quiet_since"))
            and all(isinstance(entry.get(key), (str, type(None))) for key in ("news", "try", "waits_on")))


def load(path=None):
    """The list, as {"next_id", "entries"}. A missing file is an empty list. A damaged one, or one with an odd entry,
    raises Unreadable, so every reader leaves it out and nothing writes over it."""
    path = worklist() if path is None else path
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return empty()
    except (OSError, ValueError) as error:
        raise Unreadable(f"Rook's work list at {path} cannot be read ({error}), so nothing changed.") from None
    if not (isinstance(data, dict) and isinstance(data.get("next_id"), int) and isinstance(data.get("entries"), list)
            and all(well_formed(e) for e in data["entries"])):
        raise Unreadable(f"Rook's work list at {path} is not in the list's shape, so nothing changed.")
    return data


def save(data, path=None):
    """Write the list atomically, private to the owner."""
    path = worklist() if path is None else path
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(data, out, indent=1)
    temp.replace(path)


@contextmanager
def changing(path=None):
    """Load the list under a lock, let the caller change it, and save it when it changed. relay.py and the watcher
    both write it, so each change holds the lock from its read to its write."""
    path = worklist() if path is None else path
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with os.fdopen(os.open(path.with_suffix(".lock"), os.O_WRONLY | os.O_CREAT, 0o600), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load(path)
        before = json.dumps(data)
        yield data
        if json.dumps(data) != before:
            save(data, path)


def one_line(text):
    text = " ".join(str(text).split())
    return text if len(text) <= LINE else text[:LINE - 3] + "..."


def find(data, number):
    return next((e for e in data["entries"] if e["id"] == number), None)


def is_open(entry):
    """Open means not closed by Rook and not dropped. A finished entry stays open until Rook tells the owner."""
    return not entry.get("closed") and entry.get("state") != "dropped"


def change(entry, fields, by, now):
    """Apply fields to an entry. link adds one link. Leaving waiting clears what it waited on, and reaching done or
    live records when."""
    for key, value in fields.items():
        if key == "link":
            entry["links"] = [link for link in entry.get("links") or () if link != value] + [value]
        elif key == "brief":
            entry["brief"] = value
        else:
            entry[key] = one_line(value) if isinstance(value, str) else value
    if entry["state"] != "waiting" and "waits_on" not in fields:
        entry["waits_on"] = None
    if entry["state"] != "running":
        entry.pop("quiet_since", None)
    if entry["state"] in FINISHED:
        entry["finished"] = entry.get("finished") or now
    elif entry["state"] in OPEN:
        entry["finished"] = None
    if entry["state"] == "live":
        entry["live_at"] = entry.get("live_at") or now
    entry["changed"], entry["changed_by"] = now, by
    return entry


def add(data, fields, by, now):
    """Add an entry. A wish Rook adds is a draft until its send works. A thread's own entry is running."""
    entry = {"id": data["next_id"], "wish": None, "project": None, "machine": _local_machine(), "thread": None, "title": None,
             "thread_link": None, "done_means": None, "state": "running" if by.startswith("thread ") else "drafted",
             "waits_on": None, "links": [], "news": None, "brief": None, "commit": None, "try": None,
             "made": now, "changed": now, "finished": None, "live_at": None, "closed": None, "by": by, "changed_by": by}
    data["next_id"] += 1
    data["entries"].append(entry)
    return change(entry, fields, by, now)


def named(message):
    """The work number a brief names in its "Work N on Rook's list." line, or None."""
    found = re.search(r"^Work (\d+) on Rook's list\.", str(message or ""), re.M)
    return int(found[1]) if found else None


def thread_sent(data, machine, thread, title, delivery, now, number=None):
    """The watcher saw a send to a thread work. A draft for that thread, or for a new thread with that title, is
    sent: running when the send started or steered a run, else sent. So is an entry that waits on a question the
    thread asked, since Rook carried the owner's answer. number, from the brief, limits that to the one entry it names."""
    for entry in data["entries"]:
        if number is not None and entry["id"] != number:
            continue
        asked = entry["state"] == "waiting" and asks(entry.get("waits_on")) and entry["thread"] == thread
        if (is_open(entry) and entry["machine"] == machine and (asked or entry["state"] == "drafted" and (
                entry["thread"] == thread or not entry["thread"] and title and entry["title"] == title))):
            change(entry, {"thread": thread, "state": "running" if delivery in ("started", "steered") else "sent"},
                   "watcher", now)


def thread_news(data, machine, thread, state, news, outcome, now):
    """The watcher read a thread. state is the watcher's: busy, needs, decision, finished, a stopped state, or news.
    outcome is its words for that state, and for a decision the question. A busy thread moves sent entries, and the
    waits the watcher set, to running. news, from a delegated child, changes only the news. Any other state moves
    sent, running and waiting entries: finished to done, the rest to waiting on the owner. An entry that waits on the
    thread's question keeps waiting when the run ends instead, since the request may have lapsed. The watcher sends
    busy first when a user message shows the owner answered. A draft and a finished entry stay as they are."""
    for entry in data["entries"]:
        if not is_open(entry) or entry["machine"] != machine or entry["thread"] != thread:
            continue
        if state == "busy":
            if entry["state"] == "sent" or entry["state"] == "waiting" and entry.get("changed_by") == "watcher":
                change(entry, {"state": "running"}, "watcher", now)
        elif state == "news":
            if news and entry["state"] in OPEN:
                entry["news"] = one_line(news)
        elif entry["state"] in ("sent", "running", "waiting"):
            asked = entry["state"] == "waiting" and asks(entry.get("waits_on")) and state != "needs"
            # Rook's own words render as they are saved; the thread's outcome stays as it came.
            fields = {"state": "waiting", "waits_on": settings.render(DECISION) + outcome} if state == "decision" else {
                "state": "waiting", "waits_on": LAPSED} if asked else {"state": "done"} if state == "finished" else {
                "state": "waiting", "waits_on": settings.render(NEEDS) if state == "needs" else settings.render(f"{OWNER}, since the thread ") + outcome}
            if news:
                fields["news"] = news
            change(entry, fields, "watcher", now)


def thread_quiet(data, machine, thread, since, now):
    """The watcher's silent mark on a running entry: since when its thread has shown nothing new, or None. Nothing
    else changes, so the entry keeps its state and its place in the list."""
    for entry in data["entries"]:
        if is_open(entry) and entry["state"] == "running" and entry["machine"] == machine and entry["thread"] == thread:
            if since:
                entry["quiet_since"] = since
            else:
                entry.pop("quiet_since", None)


def when(at, now):
    """A time to read aloud: the clock today, the day and clock this week, else the date."""
    if time.strftime("%Y%m%d", time.localtime(at)) == time.strftime("%Y%m%d", time.localtime(now)):
        return time.strftime("%H:%M", time.localtime(at))
    return time.strftime("%A %H:%M" if now - at < WEEK - 86400 else "%-d %B", time.localtime(at))


def sentence(text):
    text = text.strip()
    return text if text.endswith((".", "!", "?", "...")) else text + "."


def where(entry):
    """The entry's project, with its machine when it is not this machine."""
    project = entry.get("project") or "No project"
    return project if entry["machine"] == _local_machine() else f"{project} on {entry['machine']}"


def line(entry, now):
    """One short line for an entry, made to be read aloud or pasted."""
    state = {"drafted": "Drafted and not sent", "waiting": f"Waiting on {entry.get('waits_on') or settings.render(OWNER)}",
             "live": f"Live since {when(entry.get('live_at') or entry['changed'], now)}"}.get(
                 entry["state"], entry["state"].capitalize())
    source = ", from its thread" if str(entry.get("by")).startswith("thread ") else ""
    place = where(entry)
    wish = sentence(entry["wish"]) if entry.get("wish") else ""
    text = f"{place}: {wish}" if wish else f"{place}."
    text += f" {sentence(state + source)}"
    if entry.get("commit"):
        text += f" Commit {entry['commit']}."
    if entry.get("try"):
        text += f" Try: {sentence(entry['try'])}"
    elif entry.get("news"):
        text += f" News: {sentence(entry['news'])}"
    if entry["state"] == "running" and entry.get("quiet_since"):
        text += f" Quiet since {when(entry['quiet_since'], now)}."
    if entry["state"] != "live":
        text += f" Changed {when(entry['changed'], now)}."
    return f"{text} [id {entry['id']}]"


# The default listing's order: what waits on the owner, then drafts, then what finished, then what runs.
RANK = {"waiting": 0, "drafted": 1, "done": 2, "live": 2, "running": 3, "sent": 3}


def listing(data, now, everything=False, since=None):
    """The entries a listing shows. By default: open entries, without finished ones older than a week. since: what
    finished or went live since then, closed or not. everything: every entry."""
    entries = data["entries"]
    if everything:
        return sorted(entries, key=lambda e: e["id"])
    if since is not None:
        return sorted((e for e in entries if e["state"] in FINISHED and (e.get("finished") or 0) >= since),
                      key=lambda e: e["finished"])
    return sorted((e for e in entries if is_open(e) and not (e["state"] in FINISHED and now - (e.get("finished") or now) > WEEK)),
                  key=lambda e: (RANK.get(e["state"], 9), e["changed"]))


def catch_up(data, since, now):
    """The startup turn's lines from the list, or "" when nothing is open: what waits on the owner, what finished since they
    were last here, and what still runs, at most CATCH_UP entries each."""
    shown = listing(data, now)
    groups = ((settings.render(f"Waits on {OWNER}"), [e for e in shown if e["state"] in ("waiting", "drafted")]),
              (settings.render(f"Finished since {OWNER} was last here"), [e for e in shown if e["state"] in FINISHED and e["finished"] >= since]),
              ("Still running", [e for e in shown if e["state"] in ("sent", "running")]))
    lines = []
    for name, entries in groups:
        if entries:
            lines.append(f"{name}:")
            lines += [f"- {line(e, now)}" for e in entries[:CATCH_UP]]
            if len(entries) > CATCH_UP:
                lines.append(f"- And {len(entries) - CATCH_UP} more, in relay.py work list.")
    return "\n".join(lines)


def check():
    """The self-check of the list's logic, on a scratch folder."""
    import tempfile
    # An entry saved with a name before owner tokens, and one saved with the token, both wait on the owner's answer.
    name = settings.owner_name({"owner_name": "Test Owner"})
    assert asks(f"{name}'s answer or approval in T3 Code") and asks(NEEDS) and asks(LAPSED) and not asks("other")
    now = time.time()
    data = empty()
    a = add(data, {"wish": "fix the export rounding", "project": "acme-demo", "machine": "nimbus-pc",
                   "thread": "t-1", "brief": "Brief A"}, "rook", now)
    b = add(data, {"wish": "add a dark theme", "project": "acme-demo", "machine": "nimbus-pc",
                   "title": "Dark theme"}, "rook", now)
    c = add(data, {"wish": "rename the settings page", "project": "zz-shop"}, "rook", now)
    assert [e["id"] for e in data["entries"]] == [1, 2, 3] and a["state"] == "drafted" and a["brief"] == "Brief A"
    thread_sent(data, "nimbus-pc", "t-1", None, "steered", now)  # A send to a thread its draft names.
    thread_sent(data, "nimbus-pc", "t-2", "Dark theme", "queued", now)  # A launch, matched by its title.
    thread_sent(data, "oak", "t-9", "Other", "started", now)  # No draft fits: nothing changes.
    assert (a["state"], b["state"], b["thread"], c["state"]) == ("running", "sent", "t-2", "drafted")
    thread_news(data, "nimbus-pc", "t-2", "busy", None, None, now)
    thread_news(data, "nimbus-pc", "t-1", "needs", "Which file?", "is waiting", now + 1)
    assert b["state"] == "running" and a["state"] == "waiting" and a["waits_on"] == settings.render(NEEDS) and a["news"] == "Which file?"
    thread_news(data, "nimbus-pc", "t-1", "busy", None, None, now + 2)  # The owner answered: running again.
    assert a["state"] == "running" and a["waits_on"] is None
    thread_news(data, "nimbus-pc", "t-1", "failed", "", "stopped with a failure", now + 3)
    assert a["state"] == "waiting" and "failure" in a["waits_on"] and a["news"] == "Which file?"
    change(a, {"state": "waiting", "waits_on": "a reviewer's approval"}, "rook", now + 4)
    thread_news(data, "nimbus-pc", "t-1", "busy", None, None, now + 5)  # A wait Rook set stays.
    assert a["state"] == "waiting" and a["waits_on"] == "a reviewer's approval"
    thread_news(data, "nimbus-pc", "t-2", "finished", "PR 12 is open.", "finished its turn", now + 6)
    assert b["state"] == "done" and b["finished"] == now + 6 and b["news"] == "PR 12 is open."
    thread_news(data, "nimbus-pc", "t-2", "needs", "Again?", "is waiting", now + 7)  # A finished entry stays done.
    assert b["state"] == "done"
    change(c, {"state": "live", "commit": "abc1234", "try": "open Settings"}, "thread t-3", now + 8)
    assert c["live_at"] == c["finished"] == now + 8 and c["changed_by"] == "thread t-3"
    assert line(c, now + 8) == (f"zz-shop: rename the settings page. Live since {when(now + 8, now + 8)}. "
                                "Commit abc1234. Try: open Settings. [id 3]"), line(c, now + 8)
    assert [e["id"] for e in listing(data, now + 9)] == [1, 2, 3]  # Waiting first, then finished by when.
    assert [e["id"] for e in listing(data, now + 9, since=now + 7)] == [3]
    text = catch_up(data, now + 7, now + 9)
    assert text.index(settings.render(f"Waits on {OWNER}")) < text.index("Finished since") < text.index("- zz-shop: ")
    assert "acme-demo on nimbus-pc: add a dark theme." not in text
    for entry in listing(data, now + 9):
        formatted = line(entry, now + 9)
        assert not re.match(r"^\d", formatted) and not re.search(r"\bWork \d+\b", formatted), formatted
        assert formatted.startswith(entry["project"]) and formatted.endswith(f" [id {entry['id']}]"), formatted
    for row in text.splitlines():
        if row.startswith("- "):
            body = row[2:]
            assert not re.match(r"^\d", body) and not re.search(r"\bWork \d+\b", body), row
            assert re.search(r" \[id \d+\]$", body), row
    assert named("Work 29 on Rook's list.\n\nFix it.") == 29
    change(a, {"state": "done"}, "rook", now + 10)
    a["closed"] = now + 10
    assert [e["id"] for e in listing(data, now + 9 + WEEK)] == [] and len(listing(data, now, everything=True)) == 3
    assert catch_up(data, 0, now + 9 + WEEK) == ""
    # The watcher's rules for code days, on one entry.
    data = empty()
    d = add(data, {"wish": "pick a chart style", "project": "acme-demo", "thread": "t-4"}, "rook", now)
    local = d["machine"]
    thread_sent(data, local, "t-4", None, "started", now)
    thread_news(data, local, "t-4", "decision", "Tested: x", "Line or bar chart?", now + 1)
    assert d["state"] == "waiting" and d["waits_on"] == settings.render(DECISION) + "Line or bar chart?" and d["news"] == "Tested: x"
    thread_news(data, local, "t-4", "busy", None, None, now + 2)  # The owner chose, through Rook: running again.
    assert d["state"] == "running"
    thread_quiet(data, local, "t-4", now + 2, now + 2402)
    assert d["quiet_since"] == now + 2 and f"Quiet since {when(now + 2, now + 2402)}." in line(d, now + 2402)
    thread_quiet(data, local, "t-4", None, now + 2403)
    assert "quiet_since" not in d and "Quiet" not in line(d, now + 2403)
    thread_quiet(data, local, "t-4", now + 2, now + 2404)
    thread_news(data, local, "t-4", "needs", None, "is waiting", now + 2405)  # Any other state ends the mark.
    assert d["state"] == "waiting" and d["waits_on"] == settings.render(NEEDS) and "quiet_since" not in d
    thread_news(data, local, "t-4", "news", "A child thread finished its turn: ok.", "finished its turn", now + 2406)
    assert d["state"] == "waiting" and d["waits_on"] == settings.render(NEEDS) and d["news"].startswith("A child")
    thread_news(data, local, "t-4", "finished", "Stopped: no password.", "finished its turn", now + 2407)
    assert d["state"] == "waiting" and d["waits_on"] == LAPSED and d["news"] == "Stopped: no password."
    assert settings.render(f"Waits on {OWNER}") in catch_up(data, now, now + 2408)
    thread_sent(data, local, "t-4", None, "queued", now + 2409)  # Rook carried the owner's answer.
    assert d["state"] == "sent" and d["waits_on"] is None
    thread_news(data, local, "t-4", "needs", None, "is waiting", now + 2410)
    thread_news(data, local, "t-4", "busy", None, None, now + 2411)  # The watcher saw the owner's answer as a user message.
    thread_news(data, local, "t-4", "finished", "Done.", "finished its turn", now + 2411)
    assert d["state"] == "done" and "did not" not in LAPSED and "unanswered" not in LAPSED
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "rook/work.json"
        assert load(path) == empty()  # Missing: an empty list.
        with changing(path) as saved:
            add(saved, {"wish": "x", "project": "acme-demo"}, "terminal", now)
        assert path.stat().st_mode & 0o777 == 0o600 and load(path)["next_id"] == 2
        path.write_text("{not json")
        try:
            with changing(path) as saved:
                raise AssertionError("A damaged list must not load.")
        except Unreadable:
            pass
        assert path.read_text() == "{not json"  # Nothing wrote over it.
        for odd in ({"id": 1}, {**data["entries"][0], "changed": "noon"}, {**data["entries"][0], "news": 5},
                    {**data["entries"][0], "state": "done", "finished": None}):
            path.write_text(json.dumps({"next_id": 2, "entries": [odd]}))
            try:  # An odd entry reads as damaged, so no reader raises anything else.
                load(path)
                raise AssertionError(f"An odd entry must not load: {odd}")
            except Unreadable:
                pass
        assert load(Path(folder) / "rook/missing.json") == empty() and all(well_formed(e) for e in data["entries"])
    print("Work list: all checks passed.")


if __name__ == "__main__":
    check()
