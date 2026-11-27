"""Rook's persistent mailbox: questions, decisions, reviews, reminders, and pull request overlays.

SQLite in WAL mode at <XDG_STATE_HOME>/rook/mailbox.db, private to the owner (mode 0600).
Standard library only, so Rook and relay.py can both use it. Run this file to check its logic:
python desktop/mailbox.py
"""

from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time

import agent_inbox
import watch
import settings  # noqa: E402
OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.
OWNER_START = settings.OWNER_START_TOKEN  # The same, as the first word of a sentence.

SCHEMA_VERSION = 2
BUSY_TIMEOUT_MS = 5000
ANSWER_LIMIT = 1000
SUMMARY_LIMIT = 300
# An item's detail is stored up to this size, so one item cannot flood Rook's context. A list shows this much of it.
DETAIL_LIMIT = 2000
DESCRIPTION_LIMIT = 240
# An item is first named once it is this old.
CHECKIN_AGE_SECONDS = 15 * 60
# After each mention, the item is due again after the next of these waits. The last one repeats while it is open.
CHECKIN_REPEAT_SECONDS = (60 * 60, 3 * 60 * 60, 24 * 60 * 60)
# Each item keeps its own schedule: (first wait, then the waits after each mention). An agent that waits on the owner
# comes back every 30 minutes for as long as it waits, and a decision every hour.
CHECKIN_CADENCE = {"needs": (10 * 60, (20 * 60, 30 * 60)), "question": (10 * 60, (20 * 60, 30 * 60)),
                   "decision": (15 * 60, (30 * 60, 60 * 60))}
# A focus lock set with no end ends once the owner has not touched it for this long.
DEFAULT_FOCUS_IDLE_SECONDS = 90 * 60

KINDS = ("question", "needs", "decision", "review", "pr", "reminder")
CHECKIN_KINDS = ("question", "needs", "decision", "review", "reminder")
ALL_STATES = ("open", "snoozed", "answered", "dismissed", "done")
CLOSED_STATES = ("answered", "dismissed", "done")
SYNC_CLOSED_RESOLUTION = "no longer pending"

BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"
SQLITE_MAGIC = b"SQLite format 3\x00"
PR_RE = re.compile(r"^([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)#(\d+)$")
REQUIRED_TABLES = frozenset({"items", "focus", "checkin_state"})

# Display order: questions and needs, decisions, things to look at, reminders, pull request overlays.
KIND_GROUP = {
    "question": 0,
    "needs": 0,
    "decision": 0,
    "review": 1,
    "reminder": 2,
    "pr": 3,
}
KIND_RANK = {
    "question": 0,
    "needs": 1,
    "decision": 2,
    "review": 3,
    "reminder": 4,
    "pr": 5,
}
GROUP_TITLES = (
    "Questions and decisions",
    "Things to look at",
    "Reminders",
    "Pull request overlays",
)

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE items (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        source_key TEXT NOT NULL UNIQUE,
        state TEXT NOT NULL,
        summary TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        machine TEXT,
        thread TEXT,
        parent_thread TEXT,
        project TEXT,
        run TEXT,
        request TEXT,
        pr TEXT,
        created REAL NOT NULL,
        updated REAL NOT NULL,
        seen REAL,
        offered INTEGER NOT NULL DEFAULT 0,
        asked_at REAL,
        snoozed_until REAL,
        answer TEXT,
        resolution TEXT,
        closed_at REAL,
        provisional INTEGER NOT NULL DEFAULT 0,
        observed_at REAL NOT NULL,
        checkin_count INTEGER NOT NULL DEFAULT 0,
        checkin_from REAL
    )
    """,
    "CREATE INDEX idx_items_state ON items (state)",
    "CREATE INDEX idx_items_kind_thread ON items (kind, machine, thread)",
    "CREATE INDEX idx_items_pr ON items (pr)",
    """
    CREATE TABLE focus (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        threads TEXT NOT NULL,
        projects TEXT NOT NULL,
        topic TEXT NOT NULL,
        set_at REAL NOT NULL,
        until REAL
    )
    """,
    """
    CREATE TABLE checkin_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        offered_ids TEXT NOT NULL,
        offered_at REAL NOT NULL
    )
    """,
)


class MailboxError(Exception):
    """Base error for mailbox operations."""


class Unavailable(MailboxError):
    """The mailbox database cannot be opened safely. Nothing overwrites or deletes it."""


class NotFound(MailboxError):
    """No mailbox item matches the given id."""


class Refused(MailboxError):
    """The mailbox refused the requested action."""


def __getattr__(name):
    """mailbox.MAILBOX: the file under the state folder as it is at the read, not at import. A check pins another
    file by assigning MAILBOX, and then this is not called."""
    if name == "MAILBOX":
        return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "rook/mailbox.db"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _db_path(path=None):
    return Path(path if path is not None else globals().get("MAILBOX") or __getattr__("MAILBOX"))


def _one_line(text, limit=SUMMARY_LIMIT):
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 3] + "..."


def _capped_detail(text):
    text = str(text).strip()
    return text if len(text) <= DETAIL_LIMIT else text[:DETAIL_LIMIT - 1].rstrip() + "…"


def thread_label(title, project, thread=None):
    """What Rook calls a thread in a summary: its title, else its project, else its id."""
    return (str(title or "").strip() or str(project or "").strip()
            or (f"Thread {thread}" if thread else "A thread"))


def needs_summary(label, kind=None):
    """The title of a thread that waits for the owner in T3 Code, when only its count is known."""
    what = {"question": "a question", "permission": "an approval"}.get(kind, "a question or an approval")
    return f"{label} has {what} waiting in T3 Code."


def needs_detail(count, machine, thread, kind=None, waited=None, report=None):
    """What a waiting thread entails, from what its thread row and last message give."""
    count = count if isinstance(count, int) and count > 0 else 1
    lines = [f"{count} {'request waits' if count == 1 else 'requests wait'} in T3 Code, in thread {thread} on "
             f"{machine}. " + {"question": "It is a question.",
                               "permission": settings.render(f"It is a permission request. {OWNER_START} approves it in T3 Code.")}.get(
                 kind, "The thread row does not say whether it is a question or an approval.")]
    if waited:
        lines.append(f"The thread was {waited}.")
    if report:
        lines.append(f"Its last message: {report}")
    return "\n".join(lines)


def _needs_parts(detail):
    """(how long ago the thread was updated, its last message) from a needs_detail text, each None when absent."""
    text = detail or ""
    waited = re.search(r"^The thread was (.+)\.$", text, re.M)
    at = text.find("Its last message: ")
    return (waited[1] if waited else None), (text[at + len("Its last message: "):] if at >= 0 else None)


def _merge_needs(existing, summary, detail, request_data, machine, thread):
    """A needs row observed again, by the watcher or by sync, keeps what either one knows. Knowing more means: a
    known kind, question or approval, beats an unknown one and stays for this wait. The count, the time the thread
    was updated, and its last message come from the newest observation that has them. Return (summary, detail,
    request)."""
    old = _decode_request(existing["request"]) or {}
    request = {**old, **(request_data or {})}
    if not (request_data or {}).get("kind") and old.get("kind"):
        request["kind"] = old["kind"]
    kind = request.get("kind") if request.get("kind") in ("question", "permission") else None
    generic = needs_summary("")
    if kind and summary.endswith(generic):
        summary = summary[: -len(generic)] + needs_summary("", kind)
    if detail is not None:
        old_waited, old_last = _needs_parts(existing["detail"])
        new_waited, new_last = _needs_parts(detail)
        detail = needs_detail(request.get("count"), machine, thread, kind, new_waited or old_waited,
                              new_last or old_last)
    return summary, detail, request or None


def _short_answer(text):
    clean = " ".join(str(text or "").split())
    if not clean:
        raise ValueError("Give an answer text.")
    return clean if len(clean) <= ANSWER_LIMIT else clean[: ANSWER_LIMIT - 3] + "..."


def _norm_hash(text):
    norm = " ".join(str(text or "").lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _base36_hash(text):
    value = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big")
    chars = []
    while value:
        value, rem = divmod(value, 36)
        chars.append(BASE36[rem])
    return "".join(reversed(chars)) or "0"


def id_for(source_key, length=4):
    """Build a short deterministic id from source_key."""
    return f"mb-{_base36_hash(source_key)[:length]}"


def normalize_pr(ref):
    """Normalize owner/repo#number to lowercase. Raise ValueError when invalid."""
    match = PR_RE.fullmatch(str(ref or "").strip())
    if not match:
        raise ValueError(f"{ref!r} is not a pull request reference. Use owner/repo#number.")
    number = int(match.group(2))
    if number < 1:
        raise ValueError(f"{ref!r} is not a valid pull request number.")
    return f"{match.group(1).lower()}#{number}"


def _resolve_machine(machine, environment):
    if machine:
        return str(machine).strip()
    if environment:
        found = watch.machine_for(environment)
        return found or str(environment).strip()
    return None


def _chmod_private(path):
    """Keep the database file and its WAL sidecars mode 0600."""
    for target in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass


def _create_database(path):
    """Create a fresh private mailbox database atomically without overwriting an existing file."""
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
    except OSError as exc:
        raise Unavailable(f"The mailbox is unavailable: cannot create {path.parent} ({exc}).") from None
    temp = path.with_name(f".{path.name}.init.{os.getpid()}.{threading.get_ident()}")
    try:
        fd = os.open(temp, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        conn = sqlite3.connect(str(temp), timeout=BUSY_TIMEOUT_MS / 1000.0, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            for stmt in SCHEMA_STATEMENTS:
                conn.execute(stmt)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.execute("COMMIT")
            # WAL from the start, so two first opens never race to switch the journal mode.
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        try:
            os.link(temp, path)
        except FileExistsError:
            pass
    except (OSError, sqlite3.Error) as exc:
        raise Unavailable(f"The mailbox is unavailable: cannot create the database ({exc}).") from None
    finally:
        try:
            os.unlink(temp)
        except OSError:
            pass


def _validate_existing_file(path):
    """Check readability and SQLite magic bytes before SQLite touches the file."""
    try:
        with open(path, "rb") as handle:
            header = handle.read(len(SQLITE_MAGIC))
    except OSError:
        raise Unavailable("The mailbox is unavailable: cannot read the database file.") from None
    if header != SQLITE_MAGIC:
        raise Unavailable("The mailbox is unavailable: the database file is corrupt.")


def _migrate(conn, current_version):
    """Run transactional schema migrations from current_version to SCHEMA_VERSION."""
    if current_version == SCHEMA_VERSION:
        return
    if current_version != 1:
        raise Unavailable(f"The mailbox is unavailable: schema version {current_version} cannot be migrated.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] == 1:  # Another process may have migrated meanwhile.
            # Version 2: each item's check-in schedule. An item the version 1 memory offered counts one mention.
            conn.execute("ALTER TABLE items ADD COLUMN checkin_count INTEGER NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE items ADD COLUMN checkin_from REAL")
            memory = conn.execute("SELECT offered_ids, offered_at FROM checkin_state WHERE id = 1").fetchone()
            for token in json.loads(memory["offered_ids"]) if memory else ():
                item_id, _, created = token.rpartition("@")
                conn.execute("UPDATE items SET checkin_count = 1, checkin_from = ? WHERE id = ? AND created = ?",
                             (memory["offered_at"], item_id, float(created)))
            conn.execute("UPDATE checkin_state SET offered_ids = '[]'")
            conn.execute("PRAGMA user_version = 2")
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


@contextmanager
def _connect(path=None, *, create=True):
    """Open one verified SQLite connection in WAL mode with a bounded busy timeout."""
    target = _db_path(path)
    try:
        os.stat(target)
        missing = False
    except FileNotFoundError:
        missing = True
    except OSError:
        raise Unavailable("The mailbox is unavailable: cannot read the database file.") from None
    if missing:
        if not create:
            yield None
            return
        _create_database(target)
    _validate_existing_file(target)
    conn = None
    try:
        conn = sqlite3.connect(str(target), timeout=BUSY_TIMEOUT_MS / 1000.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise Unavailable(
                f"The mailbox is unavailable: schema version {version} is newer than version {SCHEMA_VERSION}."
            )
        if version < 1:
            raise Unavailable("The mailbox is unavailable: the database is not a Rook mailbox.")
        check_row = conn.execute("PRAGMA quick_check(1)").fetchone()
        if not check_row or check_row[0] != "ok":
            raise Unavailable("The mailbox is unavailable: the database file is corrupt.")
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if not REQUIRED_TABLES <= tables:
            raise Unavailable("The mailbox is unavailable: the database schema is incomplete.")
        if version < SCHEMA_VERSION:
            _migrate(conn, version)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
        if mode != "wal":
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        _chmod_private(target)
    except Unavailable:
        if conn is not None:
            conn.close()
        raise
    except sqlite3.OperationalError as exc:
        if conn is not None:
            conn.close()
        lower = str(exc).lower()
        if "locked" in lower or "busy" in lower:
            raise Unavailable("The mailbox is unavailable: the database is busy.") from None
        raise Unavailable("The mailbox is unavailable: the database file is corrupt.") from None
    except sqlite3.DatabaseError:
        if conn is not None:
            conn.close()
        raise Unavailable("The mailbox is unavailable: the database file is corrupt.") from None
    try:
        yield conn
    finally:
        _chmod_private(target)
        conn.close()


@contextmanager
def _write_tx(conn, path):
    """Run a short write transaction with BEGIN IMMEDIATE."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
        conn.execute("COMMIT")
    except Exception as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        if isinstance(exc, sqlite3.OperationalError) and any(word in str(exc).lower() for word in ("locked", "busy")):
            raise Unavailable("The mailbox is unavailable: the database is busy.") from None
        raise
    finally:
        _chmod_private(path)


def _decode_request(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _encode_request(value):
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _row_to_item(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "source_key": row["source_key"],
        "state": row["state"],
        "summary": row["summary"],
        "detail": row["detail"],
        "machine": row["machine"],
        "thread": row["thread"],
        "parent_thread": row["parent_thread"],
        "project": row["project"],
        "run": row["run"],
        "request": _decode_request(row["request"]),
        "pr": row["pr"],
        "created": row["created"],
        "updated": row["updated"],
        "seen": row["seen"],
        "offered": row["offered"],
        "asked_at": row["asked_at"],
        "snoozed_until": row["snoozed_until"],
        "answer": row["answer"],
        "resolution": row["resolution"],
        "closed_at": row["closed_at"],
        "provisional": bool(row["provisional"]),
        "observed_at": row["observed_at"],
        "checkin_count": row["checkin_count"],
        "checkin_from": row["checkin_from"],
    }


def _wake_expired_snoozes(conn, target_path, now):
    """Move snoozed items whose wake time has passed back to open."""
    due = conn.execute(
        "SELECT 1 FROM items WHERE state = 'snoozed' AND snoozed_until IS NOT NULL AND snoozed_until <= ? LIMIT 1",
        (now,),
    ).fetchone()
    if not due:
        return
    try:
        with _write_tx(conn, target_path):
            conn.execute(
                "UPDATE items SET state = 'open', checkin_from = snoozed_until, snoozed_until = NULL, updated = ? "
                "WHERE state = 'snoozed' AND snoozed_until IS NOT NULL AND snoozed_until <= ?",
                (now, now),
            )
    except sqlite3.OperationalError:
        pass


def _allocate_id(conn, source_key):
    """Pick the shortest unused deterministic id for source_key."""
    digest = _base36_hash(source_key)
    for length in range(4, len(digest) + 1):
        candidate = f"mb-{digest[:length]}"
        exists = conn.execute("SELECT 1 FROM items WHERE id = ?", (candidate,)).fetchone()
        if not exists:
            return candidate
    raise Unavailable("The mailbox is unavailable: could not allocate a unique item id.")


def _build_request(kind, request, request_id, question_ids, request_kind, pending_count):
    data = dict(request) if isinstance(request, dict) else {}
    if request_id is not None:
        data["id"] = str(request_id).strip()
    if question_ids is not None:
        seen = []
        for qid in question_ids:
            text = str(qid).strip()
            if text and text not in seen:
                seen.append(text)
        data["questions"] = seen
    if request_kind is not None:
        data["kind"] = str(request_kind).strip()
    if pending_count is not None:
        data["count"] = int(pending_count)
    if kind == "question":
        if not data.get("id"):
            raise ValueError("A question item requires a request id.")
        data.setdefault("questions", [])
        return data
    return data or None


def _source_key_and_flags(kind, *, summary, machine, thread, run, request_data, pr_ref, observed_at):
    if kind == "question":
        if not machine or not thread:
            raise ValueError("A question item requires a machine and thread id.")
        req_id = request_data["id"]
        return f"question:{machine}:{thread}:{req_id}", run, False
    if kind == "needs":
        if not machine or not thread:
            raise ValueError("A needs item requires a machine and thread id.")
        return f"needs:{machine}:{thread}", run, True
    if kind == "decision":
        clean_run = (run or "").strip()
        if clean_run:
            return f"decision:{machine or ''}:{thread or ''}:{clean_run}", clean_run, False
        return f"decision:{machine or ''}:{thread or ''}::unknown:{_norm_hash(summary)}", "", True
    if kind == "review":
        clean_run = (run or "").strip()
        if clean_run:
            return f"review:{machine or ''}:{thread or ''}:{clean_run}:finish", clean_run, False
        return f"review:{machine or ''}:{thread or ''}::unknown:{_norm_hash(summary)}", "", True
    if kind == "pr":
        if not pr_ref:
            raise ValueError("A pull request item requires owner/repo#number.")
        return f"pr:{pr_ref}", run, False
    if kind == "reminder":
        day = datetime.fromtimestamp(observed_at).strftime("%Y-%m-%d")
        return f"reminder:{day}:{_norm_hash(summary)}", run, False
    raise ValueError(f"{kind!r} is not a valid mailbox kind.")


def _is_permission(kind, request_data):
    if kind == "needs":
        return True
    if isinstance(request_data, dict):
        req_kind = str(request_data.get("kind") or "").lower()
        if req_kind in ("permission", "approval"):
            return True
    return False


def _observe_in_tx(
    conn,
    kind,
    summary,
    *,
    detail=None,
    machine=None,
    environment=None,
    thread=None,
    parent_thread=None,
    project=None,
    run=None,
    request=None,
    request_id=None,
    question_ids=None,
    request_kind=None,
    pending_count=None,
    pr=None,
    seen=None,
    observed_at=None,
):
    if kind not in KINDS:
        raise ValueError(f"{kind!r} is not a valid mailbox kind. Use {', '.join(KINDS)}.")
    clean_summary = _one_line(summary)
    if not clean_summary:
        raise ValueError("Give a one-line summary for the mailbox item.")
    obs_at = float(time.time() if observed_at is None else observed_at)
    resolved_machine = _resolve_machine(machine, environment)
    clean_thread = str(thread).strip() if thread else None
    clean_parent = str(parent_thread).strip() if parent_thread else None
    clean_project = str(project).strip() if project else None
    norm_pr = normalize_pr(pr) if pr else None
    request_data = _build_request(kind, request, request_id, question_ids, request_kind, pending_count)
    source_key, stored_run, provisional = _source_key_and_flags(
        kind,
        summary=clean_summary,
        machine=resolved_machine,
        thread=clean_thread,
        run=run,
        request_data=request_data,
        pr_ref=norm_pr,
        observed_at=obs_at,
    )
    seen_ts = float(seen) if seen is not None else (obs_at if kind in ("question", "needs", "pr") else None)

    # Do not create a duplicate provisional needs entry when an identified question is already active.
    if kind == "needs" and (request_data or {}).get("kind") != "permission":
        active_q = conn.execute(
            "SELECT * FROM items WHERE kind = 'question' AND machine = ? AND thread = ? "
            "AND state IN ('open', 'snoozed') ORDER BY updated DESC LIMIT 1",
            (resolved_machine, clean_thread),
        ).fetchone()
        if active_q is not None:
            if seen_ts is not None and obs_at >= active_q["observed_at"]:
                new_seen = max(active_q["seen"] or 0.0, seen_ts)
                conn.execute("UPDATE items SET seen = ? WHERE id = ?", (new_seen, active_q["id"]))
                return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (active_q["id"],)).fetchone())
            return _row_to_item(active_q)

    existing = conn.execute("SELECT * FROM items WHERE source_key = ?", (source_key,)).fetchone()
    if existing is not None:
        if obs_at < existing["observed_at"]:
            return _row_to_item(existing)
        if kind == "needs":
            clean_summary, detail, request_data = _merge_needs(existing, clean_summary, detail, request_data,
                                                               resolved_machine, clean_thread)
            if existing["state"] in CLOSED_STATES and existing["state"] != "dismissed" and obs_at > existing["updated"]:
                # The live count wins over done/answered: a read after close still sees the agent wait, so reopen it.
                conn.execute("UPDATE items SET state = 'open', resolution = NULL, closed_at = NULL WHERE id = ?",
                             (existing["id"],))
        merged_detail = existing["detail"] if detail is None else _capped_detail(detail)
        merged_parent = clean_parent if clean_parent is not None else existing["parent_thread"]
        merged_project = clean_project if clean_project is not None else existing["project"]
        merged_run = stored_run if stored_run is not None else existing["run"]
        merged_request = _encode_request(request_data) if request_data is not None else existing["request"]
        merged_pr = norm_pr if norm_pr is not None else existing["pr"]
        merged_seen = (
            max(existing["seen"] or 0.0, seen_ts) if seen_ts is not None else existing["seen"]
        )
        # Never change state, snooze, answer, resolution, closed_at, asked_at, offered, or created.
        conn.execute(
            "UPDATE items SET summary = ?, detail = ?, parent_thread = ?, project = ?, run = ?, "
            "request = ?, pr = ?, seen = ?, updated = ?, observed_at = ? WHERE id = ?",
            (
                clean_summary,
                merged_detail,
                merged_parent,
                merged_project,
                merged_run,
                merged_request,
                merged_pr,
                merged_seen,
                max(existing["updated"], obs_at),
                obs_at,
                existing["id"],
            ),
        )
        return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (existing["id"],)).fetchone())

    # Fold a provisional needs entry for the same thread into this newly identified question.
    state = "open"
    snoozed_until = None
    offered_count = 0
    asked_at = None
    created = obs_at
    schedule = None
    if kind == "question":
        needs_row = conn.execute(
            "SELECT * FROM items WHERE kind = 'needs' AND machine = ? AND thread = ? "
            "AND state IN ('open', 'snoozed') AND provisional = 1",
            (resolved_machine, clean_thread),
        ).fetchone()
        if needs_row is not None:
            needs_req = _decode_request(needs_row["request"]) or {}
            if needs_req.get("kind") != "permission":
                offered_count = needs_row["offered"]  # Not asked_at: the owner never heard the question itself.
                schedule = (needs_row["checkin_count"], needs_row["checkin_from"])  # The same wait's check-ins.
                created = min(needs_row["created"], obs_at)
                if needs_row["state"] == "snoozed":
                    state = "snoozed"
                    snoozed_until = needs_row["snoozed_until"]
                if clean_parent is None:
                    clean_parent = needs_row["parent_thread"]
                if clean_project is None:
                    clean_project = needs_row["project"]
                conn.execute("DELETE FROM items WHERE id = ?", (needs_row["id"],))

    item_id = _allocate_id(conn, source_key)
    conn.execute(
        "INSERT INTO items (id, kind, source_key, state, summary, detail, machine, thread, parent_thread, "
        "project, run, request, pr, created, updated, seen, offered, asked_at, snoozed_until, answer, "
        "resolution, closed_at, provisional, observed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)",
        (
            item_id,
            kind,
            source_key,
            state,
            clean_summary,
            "" if detail is None else _capped_detail(detail),
            resolved_machine,
            clean_thread,
            clean_parent,
            clean_project,
            stored_run,
            _encode_request(request_data),
            norm_pr,
            created,
            obs_at,
            seen_ts,
            offered_count,
            asked_at,
            snoozed_until,
            1 if provisional else 0,
            obs_at,
        ),
    )
    if schedule:
        conn.execute("UPDATE items SET checkin_count = ?, checkin_from = ? WHERE id = ?", (*schedule, item_id))
    return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())


def observe(
    kind,
    summary,
    *,
    detail=None,
    machine=None,
    environment=None,
    thread=None,
    parent_thread=None,
    project=None,
    run=None,
    request=None,
    request_id=None,
    question_ids=None,
    request_kind=None,
    pending_count=None,
    pr=None,
    seen=None,
    observed_at=None,
    path=None,
):
    """Create or update a mailbox item from an observation without changing user decisions."""
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            return _observe_in_tx(
                conn,
                kind,
                summary,
                detail=detail,
                machine=machine,
                environment=environment,
                thread=thread,
                parent_thread=parent_thread,
                project=project,
                run=run,
                request=request,
                request_id=request_id,
                question_ids=question_ids,
                request_kind=request_kind,
                pending_count=pending_count,
                pr=pr,
                seen=seen,
                observed_at=observed_at,
            )


def revise(item_id, summary, detail=None, *, now=None, path=None):
    """Improve an item's summary, and its detail when given, from a later report. Nothing else changes."""
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            row = conn.execute("SELECT * FROM items WHERE id = ?", (str(item_id).strip(),)).fetchone()
            if row is None:
                raise NotFound(f"No mailbox item {item_id}.")
            conn.execute(
                "UPDATE items SET summary = ?, detail = COALESCE(?, detail), updated = ?, observed_at = ? WHERE id = ?",
                (_one_line(summary) or row["summary"], None if detail is None else _capped_detail(detail),
                 max(row["updated"], ts), max(row["observed_at"], ts), row["id"]),
            )
            return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (row["id"],)).fetchone())


def _normalize_states(states):
    if states is None:
        return ALL_STATES
    if isinstance(states, str):
        states = (states,)
    result = tuple(states)
    bad = [s for s in result if s not in ALL_STATES]
    if bad:
        raise ValueError(f"Unknown state: {', '.join(bad)}. Use {', '.join(ALL_STATES)}.")
    return result


def _item_sort_key(item):
    return (KIND_RANK.get(item["kind"], 9), item["created"], item["id"])


def items(states=("open",), focus=None, now=None, *, path=None):
    """Return mailbox items matching states and optional focus, waking expired snoozes first."""
    ts = float(time.time() if now is None else now)
    wanted = _normalize_states(states)
    if not wanted:
        return []
    target = _db_path(path)
    with _connect(target) as conn:
        _wake_expired_snoozes(conn, target, ts)
        active_focus = _focus_from_conn(conn, target, ts) if focus is True else focus
        placeholders = ", ".join("?" for _ in wanted)
        rows = conn.execute(
            f"SELECT * FROM items WHERE state IN ({placeholders})",
            wanted,
        ).fetchall()
    result = [_row_to_item(row) for row in rows]
    if active_focus is not None:
        result = [item for item in result if related(item, active_focus)]
    result.sort(key=_item_sort_key)
    return result


def get(item_id, *, now=None, path=None):
    """Return one mailbox item by id, or None when missing."""
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        _wake_expired_snoozes(conn, target, ts)
        row = conn.execute("SELECT * FROM items WHERE id = ?", (str(item_id).strip(),)).fetchone()
    return _row_to_item(row)


def get_by_pr(pr_ref, *, now=None, path=None):
    """Return the pull request overlay item for owner/repo#number, or None."""
    norm = normalize_pr(pr_ref)
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        _wake_expired_snoozes(conn, target, ts)
        row = conn.execute("SELECT * FROM items WHERE source_key = ?", (f"pr:{norm}",)).fetchone()
    return _row_to_item(row)


def pr_overlays(*, now=None, path=None):
    """Return active ignored or snoozed pull request overlays without creating a missing database."""
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target, create=False) as conn:
        if conn is None:
            return {}
        rows = conn.execute(
            "SELECT * FROM items WHERE kind = 'pr' AND state IN ('dismissed', 'snoozed')"
        ).fetchall()
    overlays = {}
    for row in rows:
        item = _row_to_item(row)
        if item["state"] == "snoozed" and item["snoozed_until"] is not None and ts >= item["snoozed_until"]:
            continue
        if item["pr"]:
            overlays[item["pr"]] = item
    return overlays


def offered(ids, *, path=None):
    """Increment the offered counter on each named item id."""
    clean_ids = [str(item_id).strip() for item_id in ids if str(item_id).strip()]
    if not clean_ids:
        return 0
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            placeholders = ", ".join("?" for _ in clean_ids)
            cur = conn.execute(
                f"UPDATE items SET offered = offered + 1 WHERE id IN ({placeholders})",
                clean_ids,
            )
            return cur.rowcount


def mark_asked(item_id, at=None, *, path=None):
    """Record when the owner was actually told about an item without closing it."""
    ts = float(time.time() if at is None else at)
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            row = conn.execute("SELECT * FROM items WHERE id = ?", (str(item_id).strip(),)).fetchone()
            if row is None:
                raise NotFound(f"No mailbox item {item_id}.")
            conn.execute(
                "UPDATE items SET asked_at = ?, updated = ? WHERE id = ?",
                (ts, max(row["updated"], ts), row["id"]),
            )
            return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (row["id"],)).fetchone())


def answer(item_id, text, *, now=None, path=None):
    """Record the owner's short answer and close the item. Refuse needs and permission entries."""
    short = _short_answer(text)
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            row = conn.execute("SELECT * FROM items WHERE id = ?", (str(item_id).strip(),)).fetchone()
            if row is None:
                raise NotFound(f"No mailbox item {item_id}.")
            req = _decode_request(row["request"])
            if _is_permission(row["kind"], req):
                raise Refused(f"{OWNER_START} answers that in T3 Code, not through the mailbox.")
            if row["kind"] == "pr":
                raise Refused("A pull request is not answered. Use relay.py mailbox pr ignore, snooze, or wake.")
            if row["state"] in CLOSED_STATES:
                raise Refused(f"{row['id']} is already {row['state']}, so it takes no answer.")
            conn.execute(
                "UPDATE items SET state = 'answered', answer = ?, snoozed_until = NULL, "
                "closed_at = ?, updated = ?, observed_at = ? WHERE id = ?",
                (short, ts, ts, max(row["observed_at"], ts), row["id"]),
            )
            return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (row["id"],)).fetchone())


def _set_closed(item_id, state, reason, now, path):
    ts = float(time.time() if now is None else now)
    clean_reason = _one_line(reason) if reason else None
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            row = conn.execute("SELECT * FROM items WHERE id = ?", (str(item_id).strip(),)).fetchone()
            if row is None:
                raise NotFound(f"No mailbox item {item_id}.")
            conn.execute(
                "UPDATE items SET state = ?, resolution = ?, snoozed_until = NULL, "
                "closed_at = ?, updated = ?, observed_at = ? WHERE id = ?",
                (state, clean_reason, ts, ts, max(row["observed_at"], ts), row["id"]),
            )
            return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (row["id"],)).fetchone())


def dismiss(item_id, reason=None, *, now=None, path=None):
    """Dismiss an item with an optional short reason."""
    return _set_closed(item_id, "dismissed", reason, now, path)


def done(item_id, reason=None, *, now=None, path=None):
    """Mark an item done with an optional short reason."""
    return _set_closed(item_id, "done", reason, now, path)


def close_delivered(ids, reason=None, *, now=None, path=None):
    """Close any open reminders or video-held updates among ids once the owner has heard them."""
    reason = reason or settings.render(f"told {OWNER}")
    clean_ids = sorted({str(item_id).strip() for item_id in ids if str(item_id).strip()})
    if not clean_ids:
        return 0
    ts = float(time.time() if now is None else now)
    clean_reason = _one_line(reason) if reason else None
    target = _db_path(path)
    placeholders = ", ".join("?" for _ in clean_ids)
    eligible = "(kind = 'reminder' OR (kind = 'review' AND (run LIKE 'video:%' OR run LIKE 'startup:%')))"
    with _connect(target) as conn:
        due = conn.execute(
            f"SELECT 1 FROM items WHERE id IN ({placeholders}) AND state = 'open' AND {eligible} LIMIT 1",
            clean_ids,
        ).fetchone()
        if not due:
            return 0
        with _write_tx(conn, target):
            cur = conn.execute(
                f"UPDATE items SET state = 'done', resolution = ?, snoozed_until = NULL, "
                f"closed_at = ?, updated = ?, observed_at = MAX(observed_at, ?) "
                f"WHERE id IN ({placeholders}) AND state = 'open' AND {eligible}",
                (clean_reason, ts, ts, ts, *clean_ids),
            )
            return cur.rowcount


def snooze(item_id, until=None, *, now=None, path=None):
    """Snooze an item until a Unix timestamp, or indefinitely when until is None."""
    ts = float(time.time() if now is None else now)
    wake_at = None if until is None else float(until)
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            row = conn.execute("SELECT * FROM items WHERE id = ?", (str(item_id).strip(),)).fetchone()
            if row is None:
                raise NotFound(f"No mailbox item {item_id}.")
            conn.execute(
                "UPDATE items SET state = 'snoozed', snoozed_until = ?, resolution = NULL, closed_at = NULL, "
                "updated = ?, observed_at = ? WHERE id = ?",
                (wake_at, ts, max(row["observed_at"], ts), row["id"]),
            )
            return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (row["id"],)).fetchone())


def wake(item_id, *, now=None, path=None):
    """Wake a snoozed or dismissed item back to open."""
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            row = conn.execute("SELECT * FROM items WHERE id = ?", (str(item_id).strip(),)).fetchone()
            if row is None:
                raise NotFound(f"No mailbox item {item_id}.")
            conn.execute(
                "UPDATE items SET state = 'open', snoozed_until = NULL, resolution = NULL, closed_at = NULL, "
                "checkin_from = ?, updated = ?, observed_at = ? WHERE id = ?",
                (ts, ts, max(row["observed_at"], ts), row["id"]),
            )
            return _row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (row["id"],)).fetchone())


def reopen(item_id, *, now=None, path=None):
    """Reopen a closed or snoozed item."""
    return wake(item_id, now=now, path=path)


def _normalize_focus_threads(threads):
    result = []
    seen = set()
    for entry in threads or ():
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            machine = str(entry[0]).strip() if entry[0] else None
            tid = str(entry[1]).strip() if entry[1] else ""
        else:
            machine = None
            tid = str(entry).strip() if entry else ""
        if not tid:
            continue
        pair = (machine, tid)
        if pair not in seen:
            seen.add(pair)
            result.append([machine, tid])
    return result


def _normalize_focus_projects(projects):
    result = []
    seen = set()
    for name in projects or ():
        clean = str(name or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _focus_from_conn(conn, target_path, now):
    row = conn.execute("SELECT * FROM focus WHERE id = 1").fetchone()
    if row is None:
        return None
    ends = row["until"] if row["until"] is not None else row["set_at"] + DEFAULT_FOCUS_IDLE_SECONDS
    if now >= ends:
        try:
            with _write_tx(conn, target_path):
                conn.execute("DELETE FROM focus WHERE id = 1 AND set_at = ?", (row["set_at"],))
        except sqlite3.OperationalError:
            pass
        return None
    return {
        "threads": json.loads(row["threads"]),
        "projects": json.loads(row["projects"]),
        "topic": row["topic"],
        "set_at": row["set_at"],
        "until": row["until"],
    }


def focus_set(threads=(), projects=(), topic="", until=None, *, now=None, path=None):
    """Persist the active focus lock in the database."""
    ts = float(time.time() if now is None else now)
    norm_threads = _normalize_focus_threads(threads)
    norm_projects = _normalize_focus_projects(projects)
    clean_topic = _one_line(topic) if topic else ""
    end_at = None if until is None else float(until)
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            conn.execute(
                "INSERT INTO focus (id, threads, projects, topic, set_at, until) "
                "VALUES (1, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET threads = excluded.threads, projects = excluded.projects, "
                "topic = excluded.topic, set_at = excluded.set_at, until = excluded.until",
                (json.dumps(norm_threads), json.dumps(norm_projects), clean_topic, ts, end_at),
            )
    return {
        "threads": norm_threads,
        "projects": norm_projects,
        "topic": clean_topic,
        "set_at": ts,
        "until": end_at,
    }


def focus_get(*, now=None, path=None):
    """Return the active focus lock, or None when none is set or its duration ended."""
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        return _focus_from_conn(conn, target, ts)


def focus_touch(*, now=None, path=None):
    """The owner is active: a focus set with no end starts its idle wait again. Return the active focus or None."""
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        focus = _focus_from_conn(conn, target, ts)
        if focus and focus["until"] is None:
            with _write_tx(conn, target):
                conn.execute("UPDATE focus SET set_at = ? WHERE id = 1 AND until IS NULL", (ts,))
            focus["set_at"] = ts
        return focus


def focus_clear(*, path=None):
    """Clear the focus lock. Return True when a lock was active."""
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            cur = conn.execute("DELETE FROM focus WHERE id = 1")
            return cur.rowcount > 0


def related(item, focus):
    """Return True when item belongs to the active focus lock."""
    if not focus:
        return True
    item_machine = item.get("machine")
    item_thread = item.get("thread")
    item_parent = item.get("parent_thread")
    item_project = item.get("project")
    if not item_thread and not item_parent and not item_project:
        return False
    for entry in focus.get("threads") or ():
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            machine, tid = entry
        else:
            machine, tid = None, entry
        if not tid:
            continue
        if item_thread and item_thread == tid and (machine is None or item_machine == machine):
            return True
        if item_parent and item_parent == tid:
            return True
    if item_project:
        wanted = item_project.strip().lower()
        for project in focus.get("projects") or ():
            if str(project).strip().lower() == wanted:
                return True
    return False


def checkin_due_at(item):
    """When an item is next due in a check-in, by its kind's CHECKIN_CADENCE, else CHECKIN_AGE_SECONDS then
    CHECKIN_REPEAT_SECONDS. The first mention waits from its creation, or from its last wake. Each later one waits
    the next step from the last mention, and the last step repeats."""
    count, start = item["checkin_count"], item["checkin_from"]
    first, repeats = CHECKIN_CADENCE.get(item["kind"], (CHECKIN_AGE_SECONDS, CHECKIN_REPEAT_SECONDS))
    if not count:
        return max(item["created"], start or 0) + first
    return start + repeats[min(count, len(repeats)) - 1]


def checkin(now=None, *, kinds=CHECKIN_KINDS, path=None):
    """Return (due items, how many other open items wait) for a check-in, or ([], 0) when none is due. Each item keeps
    its own schedule, so one item's mention never holds another back. Only items of kinds count, and under a focus,
    only related ones."""
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        _wake_expired_snoozes(conn, target, ts)
        active_focus = _focus_from_conn(conn, target, ts)
        rows = conn.execute("SELECT * FROM items WHERE state = 'open'").fetchall()
    waiting = [item for item in map(_row_to_item, rows) if item["kind"] in kinds
               and (active_focus is None or related(item, active_focus))]
    due = sorted((item for item in waiting if checkin_due_at(item) <= ts), key=_item_sort_key)
    return (due, len(waiting) - len(due)) if due else ([], 0)


def checkin_done(ids, *, now=None, path=None):
    """Count one check-in mention for each named item, which starts its own next wait."""
    ts = float(time.time() if now is None else now)
    clean_ids = sorted({str(item_id).strip() for item_id in ids if str(item_id).strip()})
    target = _db_path(path)
    with _connect(target) as conn:
        with _write_tx(conn, target):
            conn.executemany("UPDATE items SET checkin_count = checkin_count + 1, checkin_from = ? WHERE id = ?",
                             [(ts, item_id) for item_id in clean_ids])
    return clean_ids


def counts(*, focus=None, now=None, path=None):
    """Return counts of open, unasked, asked, snoozed, and closed items."""
    ts = float(time.time() if now is None else now)
    target = _db_path(path)
    with _connect(target) as conn:
        _wake_expired_snoozes(conn, target, ts)
        active_focus = _focus_from_conn(conn, target, ts) if focus is True else focus
        rows = conn.execute("SELECT * FROM items").fetchall()
    by_kind = {kind: 0 for kind in KINDS}
    open_count = unasked = asked = snoozed = closed = 0
    oldest_open = None
    for row in rows:
        item = _row_to_item(row)
        if active_focus is not None and not related(item, active_focus):
            continue
        state = item["state"]
        if state == "open":
            open_count += 1
            by_kind[item["kind"]] += 1
            if item["asked_at"] is None:
                unasked += 1
            else:
                asked += 1
            oldest_open = item["created"] if oldest_open is None else min(oldest_open, item["created"])
        elif state == "snoozed":
            snoozed += 1
        elif state in CLOSED_STATES:
            closed += 1
    return {
        "open": open_count,
        "unasked": unasked,
        "asked": asked,
        "snoozed": snoozed,
        "closed": closed,
        "by_kind": by_kind,
        "oldest_open": oldest_open,
    }


def _failed_sources_from_errors(errors):
    failed = {}
    for err in errors or ():
        if ":" in err:
            source = err.split(":", 1)[0].strip()
            if source:
                failed[source] = err
    return failed


def _pr_detail(pr):
    parts = [pr.get("state") or "open", f"CI {pr.get('ci') or 'none'}"]
    if pr.get("review_decision"):
        parts.append(pr["review_decision"])
    if pr.get("url"):
        parts.append(pr["url"])
    return " | ".join(parts)


def sync(
    gathered=None,
    *,
    question_lists=None,
    pr_states=None,
    check_pr=None,
    check_thread=None,
    now=None,
    path=None,
):
    """Sync mailbox items with live sources on demand, closing only on direct evidence."""
    sync_at = float(time.time() if now is None else now)
    target = _db_path(path)

    # Read current live-backed rows in a short read before touching remote sources.
    with _connect(target) as conn:
        existing_needs = [
            _row_to_item(row)
            for row in conn.execute(
                "SELECT * FROM items WHERE kind = 'needs' AND state IN ('open', 'snoozed')"
            ).fetchall()
        ]
        existing_questions = [
            _row_to_item(row)
            for row in conn.execute(
                "SELECT * FROM items WHERE kind = 'question' AND state IN ('open', 'snoozed')"
            ).fetchall()
        ]
        existing_prs = [
            _row_to_item(row)
            for row in conn.execute(
                "SELECT * FROM items WHERE kind = 'pr' AND state IN ('open', 'snoozed', 'dismissed')"
            ).fetchall()
        ]

    # Phase 1: gather remote state outside any SQLite transaction.
    live_gather = gathered is None
    if live_gather:
        public_data, meta = agent_inbox.gather_for_sync(now=sync_at)
        all_threads = list(meta["all_threads"])
        failed_sources = dict(meta["failed_sources"])
        unreachable_machines = set(meta["unreachable_machines"])
    else:
        public_data = {
            "threads": list(gathered.get("threads") or []),
            "work": list(gathered.get("work") or []),
            "pull_requests": list(gathered.get("pull_requests") or []),
            "errors": list(gathered.get("errors") or []),
        }
        all_threads = list(gathered.get("all_threads") or [])
        failed_sources = dict(gathered.get("failed_sources") or _failed_sources_from_errors(public_data["errors"]))
        unreachable_machines = {
            m for m, err in failed_sources.items() if "could not reach" in str(err).lower()
        }

    errors = list(public_data["errors"])

    # Map explicit integer pending counts from fresh thread reads.
    explicit_counts = {}
    for t in all_threads:
        machine, tid = t.get("machine"), t.get("thread_id") or t.get("threadId")
        if not machine or not tid or machine in unreachable_machines:
            continue
        raw = t.get("pending_count") if "pending_count" in t else t.get("pendingRequestCount")
        if isinstance(raw, int) and not isinstance(raw, bool):
            explicit_counts[(machine, tid)] = raw

    # Directly verify any open needs thread that lacked an explicit count.
    needs_to_upsert = list(public_data["threads"])
    seen_needs_keys = {(t["machine"], t["thread_id"]) for t in needs_to_upsert if t.get("machine") and t.get("thread_id")}
    thread_checker = check_thread if check_thread is not None else (agent_inbox.check_thread_state if live_gather else None)
    if thread_checker is not None:
        checked = set()
        for item in existing_needs + existing_questions:
            key = (item["machine"], item["thread"])
            if key in checked:
                continue
            checked.add(key)
            if not key[0] or not key[1] or key in seen_needs_keys or key in explicit_counts:
                continue
            if key[0] in unreachable_machines:
                continue
            detail = thread_checker(key[0], key[1])
            if not isinstance(detail, dict):
                continue
            raw = detail.get("pendingRequestCount")
            if isinstance(raw, int) and not isinstance(raw, bool):
                explicit_counts[key] = raw
                if raw > 0:
                    needs_to_upsert.append({
                        "machine": key[0],
                        "project": item["project"],
                        "thread_id": key[1],
                        "title": (detail.get("title") or item["summary"]).strip(),
                        "kind": agent_inbox.request_kind(detail),
                        "pending_count": raw,
                        "parent_thread": (watch.parent_of(detail, key[0]) or (None, None, None))[1],
                        "run_id": detail.get("activeRunId") or detail.get("latestRunId") or None,
                    })
                    seen_needs_keys.add(key)

    # Map open PRs seen in the gather, and directly check any missing PR overlay.
    gathered_prs = {}
    for pr in public_data["pull_requests"]:
        ref = agent_inbox.pr_ref_of(pr)
        if ref:
            gathered_prs[ref] = pr

    direct_open_prs = {}
    prs_to_close = set()
    pr_checker = check_pr if check_pr is not None else (agent_inbox.check_pr_state if live_gather else None)
    github_failed = "github" in failed_sources
    provided_pr_states = {normalize_pr(k): v for k, v in (pr_states or {}).items()}
    for item in existing_prs:
        ref = item["pr"]
        if not ref or ref in gathered_prs or github_failed:
            continue
        state_val = None
        pr_info = None
        if ref in provided_pr_states:
            raw_state = provided_pr_states[ref]
            if isinstance(raw_state, dict):
                pr_info = raw_state
                state_val = raw_state.get("state")
            else:
                state_val = raw_state
        elif pr_checker is not None:
            checked = pr_checker(ref)
            if isinstance(checked, dict):
                pr_info = checked
                state_val = checked.get("state")
            elif isinstance(checked, str):
                state_val = checked
        if isinstance(state_val, str):
            upper = state_val.strip().upper()
            if upper in ("CLOSED", "MERGED"):
                prs_to_close.add(ref)
            elif upper == "OPEN":
                direct_open_prs[ref] = pr_info or {"state": "open", "title": item["summary"]}

    # Phase 2: apply all upserts and authoritative closures in one short transaction.
    upserted_ids = []
    closed_ids = []
    q_lists = question_lists or {}
    thread_meta = {(t.get("machine"), t.get("thread_id") or t.get("threadId")): t for t in all_threads}

    with _connect(target) as conn:
        with _write_tx(conn, target):
            conn.execute(
                "UPDATE items SET state = 'open', checkin_from = snoozed_until, snoozed_until = NULL, updated = ? "
                "WHERE state = 'snoozed' AND snoozed_until IS NOT NULL AND snoozed_until <= ?",
                (sync_at, sync_at),
            )

            # Upsert needs entries for threads waiting on the owner.
            for t in needs_to_upsert:
                machine = t.get("machine")
                tid = t.get("thread_id")
                if not machine or not tid:
                    continue
                extra = thread_meta.get((machine, tid)) or {}
                req_kind = t.get("kind")
                if req_kind not in ("question", "permission"):
                    req_kind = None
                project = t.get("project") or extra.get("project")
                summary = needs_summary(thread_label(t.get("title"), project, tid), req_kind)
                item = _observe_in_tx(  # The store keeps the watcher's last message: see _merge_needs.
                    conn,
                    "needs",
                    summary,
                    detail=needs_detail(t.get("pending_count"), machine, tid, req_kind, t.get("age")),
                    machine=machine,
                    thread=tid,
                    parent_thread=t.get("parent_thread") or extra.get("parent_thread"),
                    project=project,
                    run=t.get("run_id") or extra.get("run_id"),
                    request_kind=req_kind,
                    pending_count=t.get("pending_count") or 1,
                    seen=sync_at,
                    observed_at=sync_at,
                )
                upserted_ids.append(item["id"])

            # Refresh existing PR overlays that are still open. Never create overlays for plain PRs.
            for item in existing_prs:
                ref = item["pr"]
                if not ref:
                    continue
                if ref in gathered_prs:
                    pr = gathered_prs[ref]
                    updated = _observe_in_tx(
                        conn,
                        "pr",
                        pr.get("title") or ref,
                        detail=_pr_detail(pr),
                        pr=ref,
                        project=item["project"],
                        seen=sync_at,
                        observed_at=sync_at,
                    )
                    upserted_ids.append(updated["id"])
                elif ref in direct_open_prs:
                    info = direct_open_prs[ref]
                    updated = _observe_in_tx(
                        conn,
                        "pr",
                        info.get("title") or item["summary"],
                        detail=info.get("url") or item["detail"],
                        pr=ref,
                        project=item["project"],
                        seen=sync_at,
                        observed_at=sync_at,
                    )
                    upserted_ids.append(updated["id"])

            # Authoritative closure for needs: explicit pendingRequestCount == 0. A needs row is provisional and holds
            # nothing the owner decided, so it goes, whatever its state. A later wait on the thread is a new row.
            for key, count in explicit_counts.items():
                if count != 0:
                    continue
                gone = [row["id"] for row in conn.execute(
                    "SELECT id FROM items WHERE kind = 'needs' AND machine = ? AND thread = ? AND observed_at <= ?",
                    (*key, sync_at)).fetchall()]
                conn.execute(
                    "DELETE FROM items WHERE kind = 'needs' AND machine = ? AND thread = ? AND observed_at <= ?",
                    (*key, sync_at))
                closed_ids.extend(gone)

            # Authoritative closure for question: complete fresh question list omits its request id, or the
            # thread's explicit pending count is zero.
            for item in existing_questions:
                key = (item["machine"], item["thread"])
                if explicit_counts.get(key) == 0:
                    cur = conn.execute(
                        "UPDATE items SET state = 'done', resolution = ?, snoozed_until = NULL, "
                        "closed_at = ?, updated = ?, observed_at = ? "
                        "WHERE id = ? AND state IN ('open', 'snoozed') AND observed_at <= ?",
                        (SYNC_CLOSED_RESOLUTION, sync_at, sync_at, sync_at, item["id"], sync_at),
                    )
                    if cur.rowcount:
                        closed_ids.append(item["id"])
                    continue
                if key not in q_lists or q_lists[key] is None:
                    continue
                req_id = (item["request"] or {}).get("id")
                live_ids = {str(x) for x in q_lists[key]}
                if req_id and req_id not in live_ids:
                    cur = conn.execute(
                        "UPDATE items SET state = 'done', resolution = ?, snoozed_until = NULL, "
                        "closed_at = ?, updated = ?, observed_at = ? "
                        "WHERE id = ? AND state IN ('open', 'snoozed') AND observed_at <= ?",
                        (SYNC_CLOSED_RESOLUTION, sync_at, sync_at, sync_at, item["id"], sync_at),
                    )
                    if cur.rowcount:
                        closed_ids.append(item["id"])

            # Authoritative closure for PR overlay: direct check proved CLOSED or MERGED.
            for item in existing_prs:
                if item["pr"] not in prs_to_close:
                    continue
                cur = conn.execute(
                    "UPDATE items SET state = 'done', resolution = ?, snoozed_until = NULL, "
                    "closed_at = ?, updated = ?, observed_at = ? "
                    "WHERE id = ? AND state IN ('open', 'snoozed', 'dismissed') AND observed_at <= ?",
                    (SYNC_CLOSED_RESOLUTION, sync_at, sync_at, sync_at, item["id"], sync_at),
                )
                if cur.rowcount:
                    closed_ids.append(item["id"])

    return {
        "synced_at": sync_at,
        "upserted": upserted_ids,
        "closed": closed_ids,
        "errors": errors,
        "failed_sources": failed_sources,
        "gathered": public_data,
    }


def short_age(ts, now):
    """Format a timestamp age compactly, such as 5m ago or 2d ago."""
    if ts is None:
        return "unknown"
    seconds = max(0.0, now - ts)
    if seconds < 60:
        return "just now"
    for suffix, unit in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= unit:
            return f"{int(seconds // unit)}{suffix} ago"
    return "just now"


def _clock_label(ts):
    return time.strftime("%-I:%M %p", time.localtime(ts)).lower()


def item_source_failed(item, failed_sources):
    """Return True when sync failed to read the live source behind item."""
    if not failed_sources:
        return False
    if item["kind"] in ("needs", "question") and item.get("machine") in failed_sources:
        return True
    if item["kind"] == "pr" and "github" in failed_sources:
        return True
    return False


def format_focus(focus):
    """Format an active focus lock as one short line."""
    parts = []
    if focus.get("topic"):
        parts.append(focus["topic"])
    if focus.get("projects"):
        parts.append("projects: " + ", ".join(focus["projects"]))
    if focus.get("threads"):
        labels = [f"{m}:{t}" if m else t for m, t in focus["threads"]]
        parts.append("threads: " + ", ".join(labels))
    if focus.get("until") is not None:
        parts.append(f"until {_clock_label(focus['until'])}")
    line = "Focus: " + (" | ".join(parts) if parts else "active")
    if not focus.get("threads") and not focus.get("projects"):
        line += settings.render(f". It names no thread or project, so it holds every thread message until {OWNER} ends it")
    return line


def format_line(item, now, *, failed_sources=None, show_state=False):
    """Format one mailbox item as a single readable line."""
    origin = item.get("pr") or item.get("project") or item.get("thread") or "general"
    if item.get("machine") and item.get("kind") != "pr" and origin != "general":
        origin = f"{item['machine']}/{origin}"
    tags = []
    if show_state:
        if item["state"] == "snoozed" and item.get("snoozed_until") is not None:
            tags.append(f"snoozed until {_clock_label(item['snoozed_until'])}")
        else:
            tags.append(item["state"])
    elif item["state"] == "open" and item.get("asked_at") is not None:
        tags.append("asked")
    if item["kind"] == "needs":
        tags.append("check in T3")
    if item_source_failed(item, failed_sources):
        tags.append("last known waiting")
    tag_text = f" [{', '.join(tags)}]" if tags else ""
    return f"- {origin} | {short_age(item['created'], now)} | {item['summary']}{tag_text} [id {item['id']}]"


def format_description(item):
    """An item's detail as one indented line of at most DESCRIPTION_LIMIT characters, or "" when it has none."""
    text = " ".join(str(item.get("detail") or "").split())
    if len(text) > DESCRIPTION_LIMIT:
        text = text[:DESCRIPTION_LIMIT].rsplit(" ", 1)[0].rstrip(",;:.") + f"… (show {item['id']} has the rest)"
    return f"\n  {text}" if text else ""


def format_list(
    item_list,
    *,
    focus=None,
    now=None,
    errors=(),
    failed_sources=None,
    held_count=0,
    show_all=False,
    details=False,
):
    """Format mailbox items grouped by priority, plus focus and source error lines. details adds each item's
    short description under its line, for relay.py mailbox list."""
    ts = float(time.time() if now is None else now)
    sections = []
    if focus:
        sections.append(format_focus(focus))
    grouped = {index: [] for index in range(len(GROUP_TITLES))}
    for item in item_list:
        grouped[KIND_GROUP.get(item["kind"], 2)].append(item)
    for index, title in enumerate(GROUP_TITLES):
        rows = grouped[index]
        if rows:
            lines = [format_line(item, ts, failed_sources=failed_sources, show_state=show_all)
                     + (format_description(item) if details else "") for item in rows]
            sections.append(f"{title} ({len(rows)}):\n" + "\n".join(lines))
    if not item_list:
        if focus and not show_all:
            sections.append("No open items match this focus.")
        elif show_all:
            sections.append("The mailbox is empty.")
        else:
            sections.append("No open items in the mailbox.")
    if held_count and not show_all:
        noun = "item" if held_count == 1 else "items"
        sections.append(f"{held_count} other open {noun} outside this focus.")
    if errors:
        sections.append("\n".join(errors))
    return "\n\n".join(sections)


def format_item(item):
    """Format every field of one mailbox item for relay.py mailbox show."""
    time_fields = {"created", "updated", "seen", "asked_at", "snoozed_until", "closed_at", "observed_at"}
    lines = []
    for key, value in item.items():
        if key == "detail":
            continue
        if key in time_fields and value is not None:
            shown = datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        elif key == "request" and value is not None:
            shown = json.dumps(value)
        else:
            shown = value
        lines.append(f"{key}: {shown}")
    lines.append(f"detail:\n{item.get('detail') or '(none)'}")
    return "\n".join(lines)


def check():
    """Run hermetic self-checks on temporary folders with fake live sources."""
    now = 1_795_400_000.0
    relay_script = Path(__file__).resolve().with_name("relay.py")

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        old_xdg_cfg = os.environ.get("XDG_CONFIG_HOME")
        cfg_root = root / "config"
        (cfg_root / "rook").mkdir(parents=True)
        (cfg_root / "rook/machines.json").write_text(json.dumps({
            "oak": {"environmentId": "env-oak", "run": [], "t3": "t3", "code": "/tmp/code"},
            "nimbus-pc": {"environmentId": "env-nimbus", "run": ["ssh", "host"], "t3": "t3", "code": "/tmp/code"},
        }) + "\n")
        os.environ["XDG_CONFIG_HOME"] = str(cfg_root)
        try:
            _run_check_body(root, now, relay_script)
        finally:
            if old_xdg_cfg is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old_xdg_cfg
    print("Mailbox: all checks passed.")


def _run_check_body(root, now, relay_script):
        db = root / "state/rook/mailbox.db"

        # 1. Missing database creates empty with 0600 permissions and 0700 parent folder.
        assert items(path=db, now=now) == []
        assert (db.parent.stat().st_mode & 0o777) == 0o700
        assert (db.stat().st_mode & 0o777) == 0o600
        # Verify WAL sidecars are mode 0600 while a connection holds them open.
        with _connect(db) as live_conn:
            with _write_tx(live_conn, db):
                live_conn.execute(
                    "INSERT INTO checkin_state (id, offered_ids, offered_at) VALUES (1, '[]', ?)",
                    (now,),
                )
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{db}{suffix}")
                if sidecar.exists():
                    assert (sidecar.stat().st_mode & 0o777) == 0o600, f"{sidecar} mode not 0600"

        # 2. Same question observed five times by two sources across simulated restart -> one item.
        # Second question in same thread and run with new request id -> second item; answer stays isolated.
        q1_ids = set()
        for idx in range(5):
            q = observe(
                "question",
                f"Pick port? v{idx}",
                detail="Options: 8080 or 9090",
                machine="oak" if idx % 2 == 0 else None,
                environment="env-oak" if idx % 2 == 1 else None,
                thread="t-1",
                project="rook",
                run="run:thread:t-1:ordinal:2",
                request_id="req-1",
                question_ids=["q-port", "q-host"],
                observed_at=now + idx,
                path=db,
            )
            q1_ids.add(q["id"])
        assert len(q1_ids) == 1
        q1_id = next(iter(q1_ids))
        q1 = get(q1_id, path=db, now=now + 10)
        assert q1["summary"] == "Pick port? v4"
        assert q1["request"] == {"id": "req-1", "questions": ["q-port", "q-host"]}
        assert q1["asked_at"] is None
        q2 = observe(
            "question",
            "Enable TLS?",
            machine="oak",
            thread="t-1",
            project="rook",
            run="run:thread:t-1:ordinal:2",
            request={"id": "req-2", "questions": ["q-tls"]},
            observed_at=now + 6,
            path=db,
        )
        assert q2["id"] != q1_id
        assert offered([q1_id], path=db) == 1
        assert get(q1_id, path=db)["offered"] == 1 and get(q1_id, path=db)["asked_at"] is None
        mark_asked(q1_id, at=now + 7, path=db)
        assert get(q1_id, path=db)["state"] == "open" and get(q1_id, path=db)["asked_at"] == now + 7
        answer(q1_id, "Use 8080", now=now + 8, path=db)
        assert get(q1_id, path=db)["state"] == "answered" and get(q1_id, path=db)["answer"] == "Use 8080"
        assert get(q2["id"], path=db)["state"] == "open" and get(q2["id"], path=db)["answer"] is None

        # 2b. Answer receipt preserves up to ANSWER_LIMIT (1000) chars and truncates longer answers cleanly.
        assert ANSWER_LIMIT == 1000
        db_ans = root / "answer-limit/mailbox.db"
        q_ok = observe("decision", "Keep 500-char answer?", machine="oak", thread="t-ans", run="r-ok", observed_at=now, path=db_ans)
        ans_500 = "a" * 500
        answer(q_ok["id"], ans_500, now=now + 1, path=db_ans)
        assert get(q_ok["id"], path=db_ans)["answer"] == ans_500
        q_long = observe("decision", "Cap 1200-char answer?", machine="oak", thread="t-ans", run="r-long", observed_at=now + 2, path=db_ans)
        answer(q_long["id"], "b" * 1200, now=now + 3, path=db_ans)
        got_long = get(q_long["id"], path=db_ans)["answer"]
        assert len(got_long) == 1000 and got_long == ("b" * 997) + "...", (len(got_long), got_long[-10:])

        # 3. Deterministic ID collision extends hash length.
        coll_key = "reminder:2026-11-23:" + _norm_hash("collide test")
        base_id = id_for(coll_key, 4)
        with _connect(db) as c:
            with _write_tx(c, db):
                c.execute(
                    "INSERT INTO items (id, kind, source_key, state, summary, detail, created, updated, observed_at) "
                    "VALUES (?, 'reminder', 'synthetic:collision', 'done', 'holder', '', ?, ?, ?)",
                    (base_id, now, now, now),
                )
        rem_coll = observe("reminder", "collide test", observed_at=datetime(2026, 11, 23, 12, 0).timestamp(), path=db)
        assert rem_coll["id"] == id_for(coll_key, 5) and len(rem_coll["id"]) == len(base_id) + 1
        done(rem_coll["id"], path=db, now=now + 9)

        # 4. Needs folds into identified question; count stays one; needs refuses answer.
        db_fold = root / "fold/mailbox.db"
        n1 = observe("needs", "Thread waits", machine="oak", thread="t-fold", project="rook", pending_count=1, observed_at=now, path=db_fold)
        assert n1["provisional"] is True and counts(path=db_fold, now=now)["open"] == 1
        try:
            answer(n1["id"], "Yes", now=now + 1, path=db_fold)
            raise AssertionError("Needs item must refuse answer.")
        except Refused as exc:
            assert "T3 Code" in str(exc)
        mark_asked(n1["id"], at=now + 1, path=db_fold)
        qf = observe(
            "question",
            "Which font?",
            machine="oak",
            thread="t-fold",
            project="rook",
            request_id="req-fold",
            question_ids=["q-font"],
            observed_at=now + 2,
            path=db_fold,
        )
        assert counts(path=db_fold, now=now + 2)["open"] == 1
        assert len(items(states=None, path=db_fold, now=now + 2)) == 1
        # The question keeps the needs row's offers, not its asked time: the owner never heard the question itself.
        assert qf["kind"] == "question" and qf["provisional"] is False and qf["asked_at"] is None
        # A subsequent provisional needs observation does not duplicate the active question.
        n_dup = observe("needs", "Thread waits again", machine="oak", thread="t-fold", pending_count=1, observed_at=now + 3, path=db_fold)
        assert n_dup["id"] == qf["id"] and counts(path=db_fold, now=now + 3)["open"] == 1

        # 5. Decision with known run updates same row; unknown run does not merge with a known run.
        d_known = observe("decision", "Use SQLite?", machine="oak", thread="t-dec", run="run:1", observed_at=now, path=db_fold)
        d_reword = observe("decision", "Use SQLite or JSON?", machine="oak", thread="t-dec", run="run:1", observed_at=now + 1, path=db_fold)
        assert d_known["id"] == d_reword["id"] and d_reword["summary"] == "Use SQLite or JSON?" and d_reword["provisional"] is False
        d_unk = observe("decision", "Ship tonight?", machine="oak", thread="t-dec", observed_at=now + 2, path=db_fold)
        d_known2 = observe("decision", "Ship tonight?", machine="oak", thread="t-dec", run="run:2", observed_at=now + 3, path=db_fold)
        assert d_unk["run"] == "" and d_unk["provisional"] is True and d_unk["id"] != d_known2["id"]

        # 6. Upsert never reopens, un-snoozes, or applies an older observation; dismissed PR stays dismissed after 35 days.
        db_up = root / "upsert/mailbox.db"
        u1 = observe("decision", "Deploy now?", machine="oak", thread="t-u", run="r1", observed_at=now, path=db_up)
        snooze(u1["id"], until=now + 3600, now=now + 5, path=db_up)
        observe("decision", "Deploy now revised?", machine="oak", thread="t-u", run="r1", observed_at=now + 10, path=db_up)
        u1_after = get(u1["id"], now=now + 11, path=db_up)
        assert u1_after["state"] == "snoozed" and u1_after["snoozed_until"] == now + 3600 and u1_after["summary"] == "Deploy now revised?"
        # Older observation rejected completely.
        observe("decision", "Stale title", machine="oak", thread="t-u", run="r1", observed_at=now + 2, path=db_up)
        assert get(u1["id"], now=now + 12, path=db_up)["summary"] == "Deploy now revised?"
        # Dismissed PR stays dismissed after 35 days and fresh updatedAt, reopens only via wake/reopen.
        pr_item = observe("pr", "Old PR", pr="mariusflorescu/pstack-t3#1", observed_at=now, path=db_up)
        dismiss(pr_item["id"], "ignore", now=now + 1, path=db_up)
        observe("pr", "Old PR with new commit", pr="MariusFlorescu/pstack-t3#1", observed_at=now + 35 * 86400, path=db_up)
        pr_still = get(pr_item["id"], now=now + 35 * 86400 + 10, path=db_up)
        assert pr_still["state"] == "dismissed" and pr_still["summary"] == "Old PR with new commit"
        reopen(pr_item["id"], now=now + 35 * 86400 + 20, path=db_up)
        assert get(pr_item["id"], now=now + 35 * 86400 + 21, path=db_up)["state"] == "open"

        # 7. Concurrent writers: race stale watcher upsert against dismissal; hold write lock while reader reads.
        db_conc = root / "conc/mailbox.db"
        c_item = observe("needs", "Needs review", machine="oak", thread="t-race", observed_at=now, path=db_conc)
        lock_ready = threading.Event()
        release_lock = threading.Event()
        errors_conc = []

        def hold_write_lock():
            try:
                with _connect(db_conc) as c:
                    c.execute("BEGIN IMMEDIATE")
                    lock_ready.set()
                    release_lock.wait(2.0)
                    c.execute("COMMIT")
                dismiss(c_item["id"], "sam dismissed", now=now + 5, path=db_conc)  # Races the stale upsert.
            except Exception as exc:
                errors_conc.append(exc)
                lock_ready.set()

        reader_saw = []
        upsert_done = []

        def read_during_lock():
            try:
                lock_ready.wait(2.0)
                reader_saw.append(items(path=db_conc, now=now + 1))
            except Exception as exc:
                errors_conc.append(exc)

        def stale_upsert_during_lock():
            try:
                lock_ready.wait(2.0)
                res = observe("needs", "Stale watcher write", machine="oak", thread="t-race", observed_at=now + 2, path=db_conc)
                upsert_done.append(res)
            except Exception as exc:
                errors_conc.append(exc)

        t_lock = threading.Thread(target=hold_write_lock)
        t_read = threading.Thread(target=read_during_lock)
        t_up = threading.Thread(target=stale_upsert_during_lock)
        t_lock.start()
        t_read.start()
        t_up.start()
        lock_ready.wait(2.0)
        time.sleep(0.15)
        release_lock.set()
        t_lock.join(5.0)
        t_read.join(5.0)
        t_up.join(5.0)
        assert not errors_conc, errors_conc
        assert len(reader_saw) == 1 and len(reader_saw[0]) == 1
        final_c = get(c_item["id"], path=db_conc, now=now + 10)
        assert final_c["state"] == "dismissed" and final_c["resolution"] == "sam dismissed", final_c
        # 6. A write lock held past the busy timeout is Unavailable, never a raw SQLite error.
        global BUSY_TIMEOUT_MS
        kept_timeout, BUSY_TIMEOUT_MS = BUSY_TIMEOUT_MS, 100
        try:
            with _connect(db_conc) as c:
                c.execute("BEGIN IMMEDIATE")
                try:
                    dismiss(c_item["id"], path=db_conc)
                    raise AssertionError("A busy database must raise Unavailable.")
                except Unavailable as exc:
                    assert str(exc) == "The mailbox is unavailable: the database is busy.", exc
                c.execute("ROLLBACK")
        finally:
            BUSY_TIMEOUT_MS = kept_timeout
        # 7. A state folder that cannot be read is unavailable, never missing: nothing creates or changes it.
        locked_dir = root / "locked"
        observe("reminder", "x", path=locked_dir / "mailbox.db")
        locked_dir.chmod(0)
        try:
            for fn in (lambda: pr_overlays(path=locked_dir / "mailbox.db"), lambda: items(path=locked_dir / "mailbox.db")):
                try:
                    fn()
                    raise AssertionError("An unreadable folder must raise Unavailable.")
                except Unavailable:
                    pass
            assert stat.S_IMODE(locked_dir.stat().st_mode) == 0
        finally:
            locked_dir.chmod(0o700)

        # 8. Partial discovery: timed-out machine, thread row with no count, PR outside first 50 close nothing;
        # then authoritative closures retire each row.
        db_sync = root / "sync/mailbox.db"
        s_nimbus = observe("needs", "Nimbus thread waits", machine="nimbus-pc", thread="t-nb", observed_at=now, path=db_sync)
        s_nocount = observe("needs", "Oak thread waits", machine="oak", thread="t-nc", observed_at=now, path=db_sync)
        s_q = observe("question", "Pick option?", machine="oak", thread="t-q", request_id="req-9", question_ids=["q1"], observed_at=now, path=db_sync)
        s_pr = observe("pr", "PR 51", pr="example/rook#51", observed_at=now, path=db_sync)
        dismiss(s_pr["id"], "ignore", now=now + 1, path=db_sync)

        partial_gathered = {
            "threads": [],
            "work": [],
            "pull_requests": [],  # PR #51 absent (e.g. outside first 50).
            "errors": ["nimbus-pc: could not reach"],
            "all_threads": [
                {"machine": "oak", "thread_id": "t-nc", "title": "Oak thread", "pending_count": None},
            ],
        }
        res_partial = sync(partial_gathered, now=now + 60, path=db_sync)
        assert res_partial["closed"] == []
        assert get(s_nimbus["id"], path=db_sync)["state"] == "open"
        assert get(s_nocount["id"], path=db_sync)["state"] == "open"
        assert get(s_q["id"], path=db_sync)["state"] == "open"
        assert get(s_pr["id"], path=db_sync)["state"] == "dismissed"
        listed_partial = format_list(
            items(path=db_sync, now=now + 60),
            now=now + 60,
            errors=res_partial["errors"],
            failed_sources=res_partial["failed_sources"],
        )
        assert "nimbus-pc: could not reach" in listed_partial
        assert "last known waiting" in listed_partial

        # Direct check says PR #51 is still OPEN -> must not close.
        res_open_pr = sync(partial_gathered, pr_states={"example/rook#51": "OPEN"}, now=now + 90, path=db_sync)
        assert get(s_pr["id"], path=db_sync)["state"] == "dismissed" and res_open_pr["closed"] == []

        # Now authoritative evidence closes each item.
        auth_gathered = {
            "threads": [],
            "work": [],
            "pull_requests": [],
            "errors": [],
            "all_threads": [
                {"machine": "nimbus-pc", "thread_id": "t-nb", "title": "Nimbus", "pending_count": 0},
                {"machine": "oak", "thread_id": "t-nc", "title": "Oak", "pending_count": 0},
            ],
        }
        res_auth = sync(
            auth_gathered,
            question_lists={("oak", "t-q"): []},
            pr_states={"example/rook#51": "MERGED"},
            now=now + 120,
            path=db_sync,
        )
        assert set(res_auth["closed"]) == {s_nimbus["id"], s_nocount["id"], s_q["id"], s_pr["id"]}
        assert get(s_nimbus["id"], path=db_sync) is None and get(s_nocount["id"], path=db_sync) is None
        for cid in (s_q["id"], s_pr["id"]):
            row = get(cid, path=db_sync)
            assert row["state"] == "done" and row["resolution"] == SYNC_CLOSED_RESOLUTION
        # 1. A needs row the zero count removed comes back when the thread waits again, even after a dismissal.
        again = sync({"all_threads": [], "threads": [{"machine": "oak", "thread_id": "t-nc", "title": "Oak",
                                                      "pending_count": 1}]}, now=now + 3600, path=db_sync)
        assert len(again["upserted"]) == 1 and get(again["upserted"][0], path=db_sync)["state"] == "open"
        dismiss(again["upserted"][0], path=db_sync, now=now + 3601)
        sync({"all_threads": [{"machine": "oak", "thread_id": "t-nc", "pending_count": 0}]}, now=now + 3602,
             path=db_sync)
        third = observe("needs", "Oak thread waits", machine="oak", thread="t-nc", observed_at=now + 3603, path=db_sync)
        assert third["state"] == "open", third
        # 2. A fresh explicit count of zero closes the thread's questions with no question list.
        s_q2 = observe("question", "Ship it?", machine="oak", thread="t-q2", request_id="req-2", observed_at=now,
                       path=db_sync)
        zero = sync({"all_threads": [{"machine": "oak", "thread_id": "t-q2", "pending_count": 0}]}, now=now + 3700,
                    path=db_sync)
        assert s_q2["id"] in zero["closed"] and get(s_q2["id"], path=db_sync)["state"] == "done"
        # 3. answer() refuses a closed item and a pull request overlay.
        for refused_id in (s_q2["id"], s_pr["id"]):
            try:
                answer(refused_id, "yes", path=db_sync)
                raise AssertionError("A closed item or a pull request must refuse an answer.")
            except Refused:
                pass

        # Plain open PR with no overlay is never stored in mailbox.db by sync.
        plain_pr_gathered = {
            "threads": [],
            "work": [],
            "pull_requests": [
                {"repo": "example/rook", "number": 77, "title": "Plain PR", "state": "ready", "ci": "passing"}
            ],
            "errors": [],
            "all_threads": [],
        }
        sync(plain_pr_gathered, now=now + 130, path=db_sync)
        assert get_by_pr("example/rook#77", path=db_sync) is None

        # 9. Focus: related, unrelated, parent thread, unknown-origin item, project scope, duration expiry.
        db_focus = root / "focus/mailbox.db"
        f_direct = observe("decision", "Direct thread", machine="oak", thread="t-main", run="r1", project="rook", observed_at=now, path=db_focus)
        f_child = observe("decision", "Child thread", machine="oak", thread="t-child", parent_thread="t-main", run="r1", observed_at=now, path=db_focus)
        f_proj = observe("review", "Same project", machine="nimbus-pc", thread="t-other", project="dashboards", run="r1", observed_at=now, path=db_focus)
        f_unrel = observe("decision", "Other work", machine="oak", thread="t-else", project="other", run="r1", observed_at=now, path=db_focus)
        f_unknown = observe("reminder", "Buy milk", observed_at=now, path=db_focus)

        focus_set([("oak", "t-main")], ["dashboards"], "Rook + Dashboards", until=now + 1800, now=now, path=db_focus)
        active = focus_get(now=now + 60, path=db_focus)
        assert active is not None and active["topic"] == "Rook + Dashboards"
        assert related(f_direct, active) is True
        assert related(f_child, active) is True
        assert related(f_proj, active) is True
        assert related(f_unrel, active) is False
        assert related(f_unknown, active) is False
        focused_ids = {item["id"] for item in items(focus=active, now=now + 60, path=db_focus)}
        assert focused_ids == {f_direct["id"], f_child["id"], f_proj["id"]}
        # Duration ends -> focus clears automatically.
        assert focus_get(now=now + 1800, path=db_focus) is None
        assert len(items(focus=True, now=now + 1800, path=db_focus)) == 5

        # 10. Check-in ladder: first at 15m, then 1h, 3h, and every 24h after each mention. Not a second early.
        db_chk = root / "checkin/mailbox.db"
        minute, hour = 60, 3600
        k1 = observe("reminder", "Call dentist", observed_at=now, path=db_chk)
        observe("pr", "Some PR", pr="example/rook#9", observed_at=now, path=db_chk)  # Never in a check-in.
        assert checkin(now + 14 * minute, path=db_chk) == ([], 0)
        at = now + 15 * minute
        for wait in (0, hour, 3 * hour, 24 * hour, 24 * hour):
            at += wait
            if wait:
                assert checkin(at - 1, path=db_chk) == ([], 0)
            due, more = checkin(at, path=db_chk)
            assert [item["id"] for item in due] == [k1["id"]] and more == 0, (wait, due, more)
            checkin_done([k1["id"]], now=at, path=db_chk)
        assert get(k1["id"], path=db_chk)["checkin_count"] == 5 and get(k1["id"], path=db_chk)["checkin_from"] == at
        # Staggered items: each keeps its own schedule, so one mention never holds another due item back.
        db_gap = root / "gap/mailbox.db"
        a = observe("reminder", "A", observed_at=now, path=db_gap)
        b = observe("reminder", "B", observed_at=now + 10 * minute, path=db_gap)
        due, more = checkin(now + 15 * minute, path=db_gap)
        assert [item["id"] for item in due] == [a["id"]] and more == 1  # B waits, unnamed.
        checkin_done([a["id"]], now=now + 15 * minute, path=db_gap)
        due, more = checkin(now + 25 * minute, path=db_gap)
        assert [item["id"] for item in due] == [b["id"]] and more == 1  # No global gap: B is due at its own time.
        checkin_done([b["id"]], now=now + 45 * minute, path=db_gap)
        assert [get(x["id"], path=db_gap)["checkin_count"] for x in (a, b)] == [1, 1]
        assert [item["id"] for item in checkin(now + 75 * minute, path=db_gap)[0]] == [a["id"]]
        # A snooze ends the schedule. A wake makes the item due at its next step from the wake, not at once.
        snooze(a["id"], until=now + 2 * hour, now=now + 76 * minute, path=db_gap)
        due, more = checkin(now + 2 * hour + 1, path=db_gap)  # The snooze has ended: A woke at 2h.
        assert [item["id"] for item in due] == [b["id"]] and more == 1
        checkin_done([b["id"]], now=now + 2 * hour + 1, path=db_gap)
        assert checkin(now + 3 * hour - 1, path=db_gap) == ([], 0)
        assert [item["id"] for item in checkin(now + 3 * hour, path=db_gap)[0]] == [a["id"]]
        snooze(b["id"], now=now + 3 * hour, path=db_gap)
        assert checkin(now + 30 * hour, path=db_gap)[1] == 0  # A snoozed item is never counted.
        wake(b["id"], now=now + 30 * hour, path=db_gap)
        due = checkin(now + 30 * hour + 1, path=db_gap)[0]
        assert b["id"] not in [item["id"] for item in due]  # B woke: due 3h after the wake, its next step.
        assert b["id"] in [item["id"] for item in checkin(now + 33 * hour, path=db_gap)[0]]
        # A focus: only related items are named or counted.
        db_fc = root / "checkin-focus/mailbox.db"
        f_in = observe("decision", "Ship it?", machine="oak", thread="t-in", run="r1", observed_at=now, path=db_fc)
        observe("decision", "Rename it?", machine="oak", thread="t-out", run="r1", observed_at=now, path=db_fc)
        focus_set([("oak", "t-in")], topic="shipping", now=now, path=db_fc)
        assert checkin(now + hour, path=db_fc) == ([get(f_in["id"], path=db_fc)], 0)
        # A new wait on the same thread is a new row, so it starts a new schedule.
        n_old = observe("needs", "Waits", machine="oak", thread="t-new", observed_at=now, path=db_fc)
        checkin_done([n_old["id"]], now=now + hour, path=db_fc)
        sync({"all_threads": [{"machine": "oak", "thread_id": "t-new", "pending_count": 0}]}, now=now + 2 * hour,
             path=db_fc)
        n_new = observe("needs", "Waits again", machine="oak", thread="t-new", observed_at=now + 3 * hour, path=db_fc)
        assert n_new["checkin_count"] == 0 and n_new["created"] == now + 3 * hour

        # An agent that waits on the owner: first at 10m, then 20m, then every 30m for as long as it waits. A decision:
        # 15m, 30m, then every hour. A mention of one never holds the other back.
        db_cad = root / "cadence/mailbox.db"
        blocked = observe("needs", "Waits", machine="oak", thread="t-blk", observed_at=now, path=db_cad)
        asks = observe("decision", "Ship it?", machine="oak", thread="t-dec", run="r1", observed_at=now, path=db_cad)
        assert checkin(now + 10 * minute - 1, path=db_cad) == ([], 0)
        assert [item["id"] for item in checkin(now + 10 * minute, path=db_cad)[0]] == [blocked["id"]]
        at = now + 10 * minute
        for wait in (0, 20 * minute, 30 * minute, 30 * minute, 30 * minute):
            at += wait
            if wait:
                assert blocked["id"] not in [item["id"] for item in checkin(at - 1, path=db_cad)[0]], wait
            assert blocked["id"] in [item["id"] for item in checkin(at, path=db_cad)[0]], wait
            checkin_done([blocked["id"]], now=at, path=db_cad)
        assert [checkin_due_at(dict(asks, checkin_count=n, checkin_from=now)) - now for n in (0, 1, 2, 3)] == [
            15 * minute, 30 * minute, 60 * minute, 60 * minute]
        assert asks["id"] in [item["id"] for item in checkin(now + 15 * minute, path=db_cad)[0]]

        # A live count wins over a closed needs row: a read after a premature done opens it again. An older read does not.
        db_live = root / "live/mailbox.db"
        live = observe("needs", "Waits", machine="oak", thread="t-live", observed_at=now, path=db_live)
        done(live["id"], now=now + 60, path=db_live)
        assert observe("needs", "Waits", machine="oak", thread="t-live", observed_at=now + 30,
                       path=db_live)["state"] == "done"
        again = observe("needs", "Waits", machine="oak", thread="t-live", observed_at=now + 120, path=db_live)
        assert again["id"] == live["id"] and again["state"] == "open" and again["closed_at"] is None, again
        snooze(live["id"], until=now + hour, now=now + 130, path=db_live)
        assert observe("needs", "Waits", machine="oak", thread="t-live", observed_at=now + 140,
                       path=db_live)["state"] == "snoozed"  # The owner's snooze stands.

        # A focus set with no end ends after 90 idle minutes. Each touch starts the wait again. A set end stands.
        db_idle = root / "idle/mailbox.db"
        focus_set(topic="long work", now=now, path=db_idle)
        assert focus_get(now=now + DEFAULT_FOCUS_IDLE_SECONDS - 1, path=db_idle) is not None
        assert focus_touch(now=now + 80 * minute, path=db_idle)["set_at"] == now + 80 * minute
        assert focus_get(now=now + 80 * minute + DEFAULT_FOCUS_IDLE_SECONDS - 1, path=db_idle) is not None
        assert focus_get(now=now + 80 * minute + DEFAULT_FOCUS_IDLE_SECONDS, path=db_idle) is None
        focus_set(topic="all day", until=now + 10 * hour, now=now, path=db_idle)
        assert focus_touch(now=now + 5 * hour, path=db_idle)["set_at"] == now
        assert focus_get(now=now + 9 * hour, path=db_idle) is not None

        # Migration: a version 1 database keeps its items, focus and check-in memory.
        db_v1 = root / "v1/mailbox.db"
        db_v1.parent.mkdir(mode=0o700)
        v1 = sqlite3.connect(db_v1)
        v1.execute(SCHEMA_STATEMENTS[0].replace(
            "observed_at REAL NOT NULL,\n        checkin_count INTEGER NOT NULL DEFAULT 0,\n        checkin_from REAL",
            "observed_at REAL NOT NULL"))
        for stmt in SCHEMA_STATEMENTS[1:]:
            v1.execute(stmt)
        for item_id, summary in (("mb-aaaa", "Offered once"), ("mb-bbbb", "Never offered")):
            v1.execute("INSERT INTO items (id, kind, source_key, state, summary, created, updated, observed_at) "
                       "VALUES (?, 'reminder', ?, 'open', ?, ?, ?, ?)", (item_id, f"k:{item_id}", summary, now, now, now))
        v1.execute("INSERT INTO focus VALUES (1, '[]', '[\"rook\"]', 'the build', ?, NULL)", (now,))
        v1.execute("INSERT INTO checkin_state VALUES (1, ?, ?)", (json.dumps([f"mb-aaaa@{now}"]), now + hour))
        v1.execute("PRAGMA user_version = 1")
        v1.commit()
        v1.close()
        migrated = {item["id"]: item for item in items(path=db_v1, now=now + hour)}
        assert set(migrated) == {"mb-aaaa", "mb-bbbb"} and focus_get(now=now, path=db_v1)["topic"] == "the build"
        assert (migrated["mb-aaaa"]["checkin_count"], migrated["mb-aaaa"]["checkin_from"]) == (1, now + hour)
        assert (migrated["mb-bbbb"]["checkin_count"], migrated["mb-bbbb"]["checkin_from"]) == (0, None)
        with _connect(db_v1) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        focus_clear(path=db_v1)
        due, more = checkin(now + 15 * minute, path=db_v1)
        assert [item["id"] for item in due] == ["mb-bbbb"] and more == 1  # The offered one is on its next step.
        assert [item["id"] for item in checkin(now + 2 * hour, path=db_v1)[0]] == ["mb-aaaa", "mb-bbbb"]

        # Self-contained items: the detail is capped when stored, and an older longer one stays as it is.
        db_text = root / "text/mailbox.db"
        long_item = observe("reminder", "Read the report", detail="word " * 1000, observed_at=now, path=db_text)
        assert len(long_item["detail"]) == DETAIL_LIMIT and long_item["detail"].endswith("…")
        with _connect(db_text) as conn:
            with _write_tx(conn, db_text):
                conn.execute("UPDATE items SET detail = ? WHERE id = ?", ("x" * 5000, long_item["id"]))
        assert len(get(long_item["id"], path=db_text)["detail"]) == 5000  # Nothing rewrites stored text.
        # The list prints a short description under each title, cut with a pointer to show ID.
        listed = format_list([get(long_item["id"], path=db_text)], now=now, details=True)
        title_line, description = listed.splitlines()[1:3]
        assert "Read the report" in title_line and title_line.endswith(f" [id {long_item['id']}]"), title_line
        assert not title_line.startswith(f"- {long_item['id']}") and description.startswith("  x"), title_line
        assert description.endswith(f"… (show {long_item['id']} has the rest)") and len(description) < 300
        assert "\n  " not in format_list([long_item], now=now)  # The context lines stay one line per item.
        # A later observation of the same source improves the text and changes nothing else.
        d1 = observe("decision", "t-q: Ship?", detail="Old.", machine="oak", thread="t-q", run="r1", observed_at=now,
                     path=db_text)
        snooze(d1["id"], until=now + 3600, now=now + 1, path=db_text)
        mark_asked(d1["id"], at=now + 2, path=db_text)
        before = get(d1["id"], path=db_text)
        d2 = observe("decision", "Importer: Ship?", detail="Tested: all.\nLinks: https://x", machine="oak",
                     thread="t-q", run="r1", observed_at=now + 3, path=db_text)
        assert (d2["summary"], d2["detail"]) == ("Importer: Ship?", "Tested: all.\nLinks: https://x")
        assert all(d2[key] == before[key] for key in ("id", "state", "snoozed_until", "asked_at", "answer",
                                                      "checkin_count", "checkin_from", "created", "offered"))
        # Sync names a waiting thread and its kind, and never replaces a richer detail the watcher stored.
        db_needs = root / "needs-text/mailbox.db"
        rows = [{"machine": "oak", "thread_id": "t-ap", "title": "Deploy", "project": "acme", "kind": "permission",
                 "pending_count": 2, "age": "updated 5 minutes ago"}]
        sync({"threads": rows, "all_threads": []}, now=now, path=db_needs)
        approval = items(path=db_needs, now=now)[0]
        assert approval["summary"] == "Deploy has an approval waiting in T3 Code.", approval
        assert approval["detail"].startswith("2 requests wait in T3 Code, in thread t-ap on oak. It is a permission")
        assert "updated 5 minutes ago" in approval["detail"]
        # The watcher knows less (no kind) but has the last message: neither writer's knowledge is lost.
        observe("needs", "Deploy has a question or an approval waiting in T3 Code.",
                detail=needs_detail(2, "oak", "t-ap", report="Ship?\nTested: yes."), pending_count=2,
                machine="oak", thread="t-ap", observed_at=now + 1, path=db_needs)
        merged = items(path=db_needs, now=now + 1)[0]
        assert merged["summary"] == "Deploy has an approval waiting in T3 Code.", merged
        assert "It is a permission request." in merged["detail"] and "updated 5 minutes ago" in merged["detail"]
        assert merged["detail"].endswith("Its last message: Ship?\nTested: yes."), merged["detail"]
        # Sync after the watcher: a newer count of 3, its kind and age, and the watcher's last message kept.
        rows[0].update(pending_count=3, age="updated 1 minute ago")
        sync({"threads": rows, "all_threads": []}, now=now + 2, path=db_needs)
        merged = items(path=db_needs, now=now + 2)[0]
        assert merged["detail"].startswith("3 requests wait in T3 Code") and "It is a permission" in merged["detail"]
        assert "updated 1 minute ago" in merged["detail"] and merged["detail"].endswith("Tested: yes.")
        # The other order: the watcher files first with no kind; sync's kind then fixes both title and detail.
        db_order = root / "needs-order/mailbox.db"
        observe("needs", "Builder has a question or an approval waiting in T3 Code.",
                detail=needs_detail(1, "oak", "t-b", report="Hold on."), pending_count=1, machine="oak",
                thread="t-b", observed_at=now, path=db_order)
        sync({"threads": [{"machine": "oak", "thread_id": "t-b", "title": "Builder", "kind": "permission",
                           "pending_count": 3}], "all_threads": []}, now=now + 1, path=db_order)
        fixed = items(path=db_order, now=now + 1)[0]
        assert fixed["summary"] == "Builder has an approval waiting in T3 Code.", fixed
        assert fixed["detail"].startswith("3 requests wait") and "permission request" in fixed["detail"]
        assert "does not say" not in fixed["detail"] and fixed["detail"].endswith("Its last message: Hold on.")

        # 11. Corrupt file and newer schema: left byte-for-byte intact, error is one sentence.
        corrupt = root / "corrupt/mailbox.db"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt_bytes = b"not a sqlite database at all"
        corrupt.write_bytes(corrupt_bytes)
        for fn in (lambda: items(path=corrupt), lambda: observe("reminder", "x", path=corrupt)):
            try:
                fn()
                raise AssertionError("Corrupt DB must raise Unavailable.")
            except Unavailable as exc:
                msg = str(exc)
                assert msg.startswith("The mailbox is unavailable: ") and msg.count(".") == 1, msg
        assert corrupt.read_bytes() == corrupt_bytes
        assert not Path(f"{corrupt}-wal").exists()

        newer = root / "newer/mailbox.db"
        newer.parent.mkdir(parents=True, exist_ok=True)
        nc = sqlite3.connect(str(newer))
        nc.execute("CREATE TABLE items (id TEXT)")
        nc.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
        nc.commit()
        nc.close()
        newer_bytes = newer.read_bytes()
        try:
            items(path=newer)
            raise AssertionError("Newer schema must raise Unavailable.")
        except Unavailable as exc:
            msg = str(exc)
            assert msg.startswith("The mailbox is unavailable: ") and str(SCHEMA_VERSION + 5) in msg, msg
        assert newer.read_bytes() == newer_bytes

        # Unreadable file raises Unavailable without changing the file.
        if os.geteuid() != 0:
            unreadable = root / "unreadable/mailbox.db"
            unreadable.parent.mkdir(parents=True, exist_ok=True)
            unreadable.write_bytes(b"secret")
            os.chmod(unreadable, 0o000)
            try:
                try:
                    items(path=unreadable)
                    raise AssertionError("Unreadable file must raise Unavailable.")
                except Unavailable as exc:
                    assert str(exc).startswith("The mailbox is unavailable: ")
            finally:
                os.chmod(unreadable, 0o600)
            assert unreadable.read_bytes() == b"secret"

        # 12. CLI checks through a scratch XDG_STATE_HOME: every subcommand, every refusal, inbox overlays.
        cli_state = root / "cli_state"
        cli_state.mkdir()
        cli_cfg = root / "cli-config"
        (cli_cfg / "rook").mkdir(parents=True)
        (cli_cfg / "rook/machines.json").write_text(json.dumps({
            "oak": {"environmentId": "env-oak", "run": [], "t3": "t3", "code": "/tmp/code"},
            "nimbus-pc": {"environmentId": "env-nb", "run": ["ssh", "host"], "t3": "t3", "code": "/tmp/code"},
        }) + "\n")

        def run_cli(*args, extra_env=None):
            env = {k: v for k, v in os.environ.items() if k not in ("ROOK_AGENT", "T3CODE_THREAD_ID")}
            env["XDG_STATE_HOME"] = str(cli_state)
            env["XDG_CONFIG_HOME"] = str(cli_cfg)
            # Never the caller's running Rook or its files.
            (root / "run").mkdir(mode=0o700, exist_ok=True)
            env.update(XDG_RUNTIME_DIR=str(root / "run"), XDG_DATA_HOME=str(root / "data"),
                       XDG_CACHE_HOME=str(root / "cache"))
            if extra_env:
                env.update(extra_env)
            return subprocess.run(
                [sys.executable, str(relay_script), *args],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )

        # Add from shell, list, show, snooze, wake, answer, dismiss, done, asked.
        r = run_cli("mailbox", "add", "--kind", "reminder", "--summary", "Check deploy", "--detail", "Verify logs")
        assert r.returncode == 0, r.stderr
        rid = r.stdout.strip()
        assert rid.startswith("mb-")

        r = run_cli("mailbox", "list")
        assert r.returncode == 0 and rid in r.stdout and "Check deploy" in r.stdout, r.stdout
        r = run_cli("mailbox", "list", "--json")
        assert r.returncode == 0 and any(i["id"] == rid for i in json.loads(r.stdout)["items"])
        r = run_cli("mailbox", "show", rid)
        assert r.returncode == 0 and "Verify logs" in r.stdout

        # asked refuses shell and thread, succeeds for ROOK_AGENT.
        r_no_rook = run_cli("mailbox", "asked", rid)
        assert r_no_rook.returncode != 0 and "Only Rook" in r_no_rook.stderr
        r_rook = run_cli("mailbox", "asked", rid, extra_env={"ROOK_AGENT": "1"})
        assert r_rook.returncode == 0, r_rook.stderr

        r = run_cli("mailbox", "snooze", rid, "--until", "30m")
        assert r.returncode == 0, r.stderr
        r = run_cli("mailbox", "list")
        assert rid not in r.stdout
        r = run_cli("mailbox", "list", "--all")
        assert rid in r.stdout and "snoozed" in r.stdout
        r = run_cli("mailbox", "wake", rid)
        assert r.returncode == 0, r.stderr
        r = run_cli("mailbox", "done", rid)
        assert r.returncode == 0, r.stderr

        # T3 thread guard: may add for itself on oak and list; refused on other thread, other machine, mutations.
        r_self = run_cli(
            "mailbox", "add", "--kind", "decision", "--summary", "Ship A or B?", "--project", "rook",
            extra_env={"T3CODE_THREAD_ID": "mcp:thread-self"},
        )
        assert r_self.returncode == 0, r_self.stderr
        tid_item = r_self.stdout.strip()
        assert get(tid_item, path=cli_state / "rook/mailbox.db")["thread"] == "mcp:thread-self"
        assert run_cli("mailbox", "list", extra_env={"T3CODE_THREAD_ID": "mcp:thread-self"}).returncode == 0
        assert run_cli(
            "mailbox", "add", "--kind", "decision", "--summary", "Spoof", "--thread", "mcp:other",
            extra_env={"T3CODE_THREAD_ID": "mcp:thread-self"},
        ).returncode != 0
        assert run_cli(
            "mailbox", "add", "--kind", "decision", "--summary", "Spoof", "--machine", "nimbus-pc",
            extra_env={"T3CODE_THREAD_ID": "mcp:thread-self"},
        ).returncode != 0
        for forbidden in (
            ("mailbox", "answer", tid_item, "A"),
            ("mailbox", "dismiss", tid_item),
            ("mailbox", "done", tid_item),
            ("mailbox", "snooze", tid_item),
            ("mailbox", "wake", tid_item),
            ("mailbox", "asked", tid_item),
            ("mailbox", "pr", "ignore", "example/rook#1"),
            ("mailbox", "focus", "set", "--project", "rook"),
            ("mailbox", "focus", "clear"),
            ("mailbox", "sync"),
        ):
            rf = run_cli(*forbidden, extra_env={"T3CODE_THREAD_ID": "mcp:thread-self"})
            assert rf.returncode != 0, f"Thread must be refused on {forbidden}"

        # Answer and dismiss from shell; needs refuses answer on CLI.
        r = run_cli("mailbox", "answer", tid_item, "Go with A")
        assert r.returncode == 0, r.stderr
        r_needs = run_cli(
            "mailbox", "add", "--kind", "needs", "--summary", "Approve command",
            "--thread", "t-perm", "--machine", "oak",
        )
        assert r_needs.returncode == 0, r_needs.stderr
        r_ref = run_cli("mailbox", "answer", r_needs.stdout.strip(), "Approved")
        assert r_ref.returncode != 0 and "T3 Code" in r_ref.stderr
        assert run_cli("mailbox", "dismiss", r_needs.stdout.strip(), "handled").returncode == 0

        # Focus CLI commands.
        r = run_cli("mailbox", "focus", "set", "--project", "rook", "--topic", "Mailbox work", "--for", "1h")
        assert r.returncode == 0, r.stderr
        r = run_cli("mailbox", "focus", "status")
        assert r.returncode == 0 and "Mailbox work" in r.stdout
        r = run_cli("mailbox", "focus", "clear")
        assert r.returncode == 0, r.stderr
        r = run_cli("mailbox", "focus", "status")
        assert r.returncode == 0 and "No focus" in r.stdout

        # PR overlay CLI commands + inbox overlay filtering and unchanged JSON without overlays.
        sample_inbox = {
            "threads": [],
            "work": [],
            "pull_requests": [
                {
                    "repo": "mariusflorescu/pstack-t3",
                    "number": 1,
                    "title": "Demo PR",
                    "url": "https://github.com/mariusflorescu/pstack-t3/pull/1",
                    "draft": False,
                    "state": "ready",
                    "ci": "passing",
                    "review_decision": None,
                    "head_ref": "main",
                    "updated_at": "2026-11-23T12:00:00Z",
                    "age": "updated 1 hour ago",
                    "thread": None,
                }
            ],
            "errors": [],
        }
        # No overlay: JSON unchanged.
        no_ov = pr_overlays(path=root / "empty_state/rook/mailbox.db", now=now)
        assert no_ov == {} and not (root / "empty_state/rook/mailbox.db").exists()
        filtered_plain, hidden_plain = agent_inbox.apply_overlays(sample_inbox, no_ov)
        assert json.dumps(filtered_plain, indent=2) == json.dumps(sample_inbox, indent=2)
        assert hidden_plain == {"ignored": 0, "snoozed": 0}

        # Ignore PR via CLI, verify overlay hides it by default and --all shows it.
        r = run_cli("mailbox", "pr", "ignore", "mariusflorescu/pstack-t3#1")
        assert r.returncode == 0, r.stderr
        ov_cli = pr_overlays(path=cli_state / "rook/mailbox.db")
        filtered_ov, hidden_ov = agent_inbox.apply_overlays(sample_inbox, ov_cli, show_all=False)
        assert filtered_ov["pull_requests"] == [] and hidden_ov == {"ignored": 1, "snoozed": 0}
        txt_ov = agent_inbox.format_inbox(filtered_ov, now=now, hidden_prs=hidden_ov)
        assert "1 pull request ignored" in txt_ov and "Demo PR" not in txt_ov
        filtered_all, hidden_all = agent_inbox.apply_overlays(sample_inbox, ov_cli, show_all=True)
        txt_all = agent_inbox.format_inbox(filtered_all, now=now, hidden_prs=hidden_all, pr_overlays=ov_cli)
        assert "Demo PR" in txt_all and "ignored" in txt_all

        # Snooze and wake PR via CLI.
        assert run_cli("mailbox", "pr", "snooze", "mariusflorescu/pstack-t3#1", "--until", "2h").returncode == 0
        assert pr_overlays(path=cli_state / "rook/mailbox.db")["mariusflorescu/pstack-t3#1"]["state"] == "snoozed"
        assert run_cli("mailbox", "pr", "wake", "mariusflorescu/pstack-t3#1").returncode == 0
        assert "mariusflorescu/pstack-t3#1" not in pr_overlays(path=cli_state / "rook/mailbox.db")

        # End-to-end relay.inbox_command and relay.mailbox_command sync checks with fake gather data.
        import io
        from contextlib import redirect_stdout
        import relay as relay_mod

        orig_gather = agent_inbox.gather
        orig_gather_sync = agent_inbox.gather_for_sync
        orig_thread_state, orig_pr_state = agent_inbox.check_thread_state, agent_inbox.check_pr_state
        orig_mailbox = globals().get("MAILBOX")
        orig_mod = sys.modules.get("mailbox")
        orig_thread_env = os.environ.pop("T3CODE_THREAD_ID", None)
        orig_rook_env = os.environ.pop("ROOK_AGENT", None)
        try:
            sys.modules["mailbox"] = sys.modules[__name__]
            globals()["MAILBOX"] = root / "empty_inbox_state/rook/mailbox.db"
            agent_inbox.gather = lambda **kw: sample_inbox
            buf = io.StringIO()
            with redirect_stdout(buf):
                relay_mod.inbox_command(["--json"])
            assert buf.getvalue().strip() == json.dumps(sample_inbox, indent=2)
            assert not (root / "empty_inbox_state/rook/mailbox.db").exists()

            # Apply an overlay and verify relay.inbox_command hides by default and shows with --all.
            globals()["MAILBOX"] = cli_state / "rook/mailbox.db"
            assert run_cli("mailbox", "pr", "ignore", "mariusflorescu/pstack-t3#1").returncode == 0
            buf_text = io.StringIO()
            with redirect_stdout(buf_text):
                relay_mod.inbox_command([])
            assert "1 pull request ignored" in buf_text.getvalue() and "Demo PR" not in buf_text.getvalue()
            buf_all = io.StringIO()
            with redirect_stdout(buf_all):
                relay_mod.inbox_command(["--all"])
            assert "Demo PR" in buf_all.getvalue() and "ignored" in buf_all.getvalue()

            # Verify relay.mailbox_command sync and list --sync with fake gather_for_sync.
            # Sync must never run the real t3 or gh.
            agent_inbox.check_thread_state = agent_inbox.check_pr_state = lambda *a, **kw: None
            agent_inbox.gather_for_sync = lambda **kw: (
                {"threads": [], "work": [], "pull_requests": sample_inbox["pull_requests"], "errors": ["nimbus-pc: could not reach"]},
                {"all_threads": [], "failed_sources": {"nimbus-pc": "nimbus-pc: could not reach"}, "unreachable_machines": {"nimbus-pc"}},
            )
            buf_sync = io.StringIO()
            with redirect_stdout(buf_sync):
                relay_mod.mailbox_command(["sync"])
            assert "Synced mailbox:" in buf_sync.getvalue() and "nimbus-pc: could not reach" in buf_sync.getvalue()
            buf_lsync = io.StringIO()
            with redirect_stdout(buf_lsync):
                relay_mod.mailbox_command(["list", "--sync"])
            assert "nimbus-pc: could not reach" in buf_lsync.getvalue()
        finally:
            if orig_thread_env is not None:
                os.environ["T3CODE_THREAD_ID"] = orig_thread_env
            if orig_rook_env is not None:
                os.environ["ROOK_AGENT"] = orig_rook_env
            agent_inbox.gather = orig_gather
            agent_inbox.gather_for_sync = orig_gather_sync
            agent_inbox.check_thread_state, agent_inbox.check_pr_state = orig_thread_state, orig_pr_state
            if orig_mailbox is None:
                globals().pop("MAILBOX", None)
            else:
                globals()["MAILBOX"] = orig_mailbox
            if orig_mod is None:
                sys.modules.pop("mailbox", None)
            else:
                sys.modules["mailbox"] = orig_mod

        # Corrupt DB through CLI prints the unavailable sentence and exits non-zero.
        corrupt_state = root / "cli_corrupt"
        (corrupt_state / "rook").mkdir(parents=True)
        (corrupt_state / "rook/mailbox.db").write_bytes(b"broken")
        env_bad = {k: v for k, v in os.environ.items() if k not in ("ROOK_AGENT", "T3CODE_THREAD_ID")}
        env_bad["XDG_STATE_HOME"] = str(corrupt_state)
        (root / "run").mkdir(mode=0o700, exist_ok=True)
        env_bad.update(XDG_CONFIG_HOME=str(cli_cfg), XDG_RUNTIME_DIR=str(root / "run"),
                       XDG_DATA_HOME=str(root / "data"), XDG_CACHE_HOME=str(root / "cache"))
        r_bad = subprocess.run(
            [sys.executable, str(relay_script), "mailbox", "list"],
            capture_output=True,
            text=True,
            env=env_bad,
            timeout=15,
        )
        assert r_bad.returncode != 0 and r_bad.stderr.strip().startswith("The mailbox is unavailable:"), r_bad.stderr
        assert (corrupt_state / "rook/mailbox.db").read_bytes() == b"broken"

        # 13. close_delivered closes open reminders and video/startup-held review items, leaving other items open.
        db_rem = root / "delivered-reminders/mailbox.db"
        r_open = observe("reminder", "Send the invite", observed_at=now, path=db_rem)
        r_snoozed = observe("reminder", "Call tomorrow", observed_at=now, path=db_rem)
        snooze(r_snoozed["id"], until=now + 3600, now=now + 1, path=db_rem)
        v_open = observe("review", "Update waited during video: build green.", run="video:status:123",
                         observed_at=now, path=db_rem)
        s_open = observe("review", "Rook restarted while a video was playing.", run="startup:456",
                         observed_at=now, path=db_rem)
        rev_keep = observe("review", "Look at the chart.", run="r1", observed_at=now, path=db_rem)
        n_open = observe("needs", "Thread waits", machine="oak", thread="t-rem", observed_at=now, path=db_rem)
        d_open = observe("decision", "Ship it?", machine="oak", thread="t-rem2", run="r1", observed_at=now, path=db_rem)
        assert close_delivered(
            [r_open["id"], r_snoozed["id"], v_open["id"], s_open["id"], rev_keep["id"], n_open["id"], d_open["id"]],
            now=now + 60, path=db_rem) == 3
        for cid in (r_open["id"], v_open["id"], s_open["id"]):
            closed_r = get(cid, now=now + 60, path=db_rem)
            assert closed_r["state"] == "done" and closed_r["resolution"] == settings.render(f"told {OWNER}") and closed_r["closed_at"] == now + 60
        assert get(r_snoozed["id"], now=now + 60, path=db_rem)["state"] == "snoozed"
        assert get(rev_keep["id"], now=now + 60, path=db_rem)["state"] == "open"
        assert get(n_open["id"], now=now + 60, path=db_rem)["state"] == "open"
        assert get(d_open["id"], now=now + 60, path=db_rem)["state"] == "open"
        # Re-snoozing a delivered reminder clears resolution and brings it back at its time.
        snooze(r_open["id"], until=now + 7200, now=now + 65, path=db_rem)
        resnoozed = get(r_open["id"], now=now + 66, path=db_rem)
        assert resnoozed["state"] == "snoozed" and resnoozed["resolution"] is None and resnoozed["closed_at"] is None
        woken = get(r_open["id"], now=now + 7200, path=db_rem)
        assert woken["state"] == "open"
        assert close_delivered([r_open["id"]], now=now + 8100, path=db_rem) == 1
        assert get(r_open["id"], now=now + 8100, path=db_rem)["resolution"] == settings.render(f"told {OWNER}")

if __name__ == "__main__":
    check()
