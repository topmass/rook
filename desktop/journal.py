"""Rook's request journal: one durable row per request, and the notices the owner is owed after a restart.

The rows and notices live in the mailbox's database file, in two tables of their own. The mailbox checks and
migrates the file when this module opens it, and its schema version stays the mailbox's. This module creates its
tables only when they are missing, so an older Rook ignores them, and a rollback and a redeploy both just work. A
later change to these tables adds columns when they are missing, the same way, or gives them a version of their own
then. This module keeps one long-lived connection, because a request's first write is on Rook's hot path. It knows nothing of the microphone,
the overlay or this machine: the client is a column, so a phone or a remote laptop can write rows too.
Run this file to check its logic: python desktop/journal.py
"""

from contextlib import contextmanager
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

ENDED = ("closed", "interrupted", "empty")  # A row in any of these states owes the owner nothing.
TABLES = (
    """
    CREATE TABLE IF NOT EXISTS requests (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        turn TEXT NOT NULL UNIQUE,
        conversation TEXT NOT NULL,
        client TEXT NOT NULL,
        source TEXT NOT NULL,
        text TEXT NOT NULL,
        at REAL NOT NULL,
        state TEXT NOT NULL,
        tools TEXT NOT NULL DEFAULT '',
        tools_known INTEGER NOT NULL DEFAULT 1,
        answer TEXT,
        draft INTEGER NOT NULL DEFAULT 0,
        speech TEXT,
        heard TEXT,
        unheard TEXT,
        reason TEXT,
        updated REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_requests_state ON requests (state)",
    """
    CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT NOT NULL,
        kind TEXT NOT NULL,
        text TEXT NOT NULL,
        at REAL NOT NULL,
        offered INTEGER NOT NULL DEFAULT 0,
        partly INTEGER NOT NULL DEFAULT 0,
        cleared REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS journal_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS timers (
        id TEXT PRIMARY KEY,
        label TEXT NOT NULL DEFAULT '',
        due REAL NOT NULL,
        seconds INTEGER,
        clock TEXT,
        kind TEXT NOT NULL,
        task TEXT,
        set_at REAL NOT NULL,
        called INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inbox_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT NOT NULL,
        event TEXT NOT NULL,
        text TEXT NOT NULL,
        arrived REAL NOT NULL,
        source TEXT,
        delivered REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_inbox_items_open ON inbox_items (client, delivered)",
    """
    CREATE TABLE IF NOT EXISTS waits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT NOT NULL,
        conversation TEXT NOT NULL,
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        turn TEXT,
        tool TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        at REAL NOT NULL,
        cleared REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_waits_open ON waits (client, cleared)",
)
# Rook's sends to T3 threads: a row before each send and its outcome after, so a restart between them never sends
# twice blindly and never loses one silently. key is the send's clientRequestId, which T3 keys its receipt by. Rows
# keep ids, destinations, outcomes and one-line descriptions. brief keeps Rook's own framed handoff only until the
# send settles. digest is a hash of the sent text, never the text: a restart looks for it among the thread's messages.
# told is the outcome a notice already gave, so a notice is given once.
SEND_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS sends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT NOT NULL,
        key TEXT NOT NULL,
        conversation TEXT NOT NULL DEFAULT '',
        turn TEXT,
        tool TEXT NOT NULL,
        machine TEXT,
        thread TEXT,
        project TEXT,
        work INTEGER,
        description TEXT NOT NULL DEFAULT '',
        digest TEXT,
        brief TEXT,
        at REAL NOT NULL,
        outcome TEXT,
        result TEXT,
        told TEXT,
        settled REAL,
        UNIQUE (client, key)
    )
    """,
)
# The session's events, for clients that attach, such as the owner's phone. A stored event is written in the same
# transaction as the change it describes, so it costs no extra commit, and goes to subscribers after that commit, in
# commit order. seq only grows: AUTOINCREMENT keeps the highest across pruning. A command from a device is admitted
# here, by its id and a fingerprint of its input, before it runs, so a retry never runs it twice.
EVENT_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        at REAL NOT NULL,
        conversation TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL,
        turn TEXT,
        client TEXT NOT NULL,
        body TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_at ON events (at)",
    """
    CREATE TABLE IF NOT EXISTS commands (
        device TEXT NOT NULL,
        id TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        kind TEXT NOT NULL,
        turn TEXT,
        status TEXT NOT NULL,
        result TEXT,
        at REAL NOT NULL,
        updated REAL NOT NULL,
        PRIMARY KEY (device, id)
    )
    """,
)
# The thread roster: one row per open, unsettled or recently active thread or agent, so a restart keeps it. watch.Roster
# owns its rules; the rows are only kept here.
ROSTER_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS roster (
        orchestrator TEXT NOT NULL,
        machine TEXT NOT NULL,
        id TEXT NOT NULL,
        project TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT '',
        settled INTEGER NOT NULL DEFAULT 0,
        snoozed INTEGER NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL DEFAULT 0,
        scope TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (orchestrator, machine, id)
    )
    """,
)
ROSTER_COLUMNS = ("orchestrator", "machine", "id", "project", "title", "status", "settled", "snoozed", "updated_at", "scope")
EVENT_KEEP_SECONDS = 7 * 24 * 3600  # Events older than this are pruned at each start, a batch at a time.
COMMAND_KEEP_SECONDS = 24 * 3600  # A device's command row, kept long past any retry of it.
EVENT_PRUNE_BATCH = 500
IN_FLIGHT = ("hearing", "queued", "accepted", "handed", "working")  # A request in one of these states has no final outcome yet.
SNAPSHOT_EXCHANGES = 20  # A snapshot carries the requests in flight and this many of the latest others.
SEND_KEEP_SECONDS = 7 * 24 * 3600  # A settled send's row is dropped after this long.
SEND_RETRY_SECONDS = 24 * 3600  # Each start looks up an unsettled send for this long, then settles it as unknown.
BUSY_SECONDS = 0.25  # A write that waits longer for the file's lock fails, and Rook goes on without it.
# A notice the owner never heard stops being owed after this long, so nothing comes back forever: a build thread's
# restart note after a week, and a notice of a cut request or answer after a day.
NOTE_KEEP_SECONDS = 7 * 24 * 3600
CUT_KEEP_SECONDS = 24 * 3600


CLIENT = "desktop"  # This machine's Rook. A phone or a remote laptop would write rows as another client.


class Journal:
    def __init__(self, path=None, client=CLIENT):
        self.path, self.client = path, client  # client names this brain: the Rook that owns the session.
        self.conn = None
        self.file = None  # The database file, once open, for readers on their own connections.
        self.high = 0  # The highest committed event seq.
        self.on_event = None  # Called as on_event(seq, kind, data) after each commit, in commit order.
        self.pending = []  # Events of the open transaction, published after its commit.
        self.lock = threading.Lock()  # The event loop and the one worker thread share the connection.

    def open(self):
        """Check and migrate the file the mailbox's way, then keep one connection. Raise mailbox.Unavailable when
        the file is damaged, newer or unreadable: nothing here writes over such a file."""
        import mailbox  # Here, not at the top: relay.py imports this module on a handoff's path, and needs no mailbox.
        with mailbox._connect(self.path):
            pass
        conn = sqlite3.connect(str(mailbox._db_path(self.path)), timeout=BUSY_SECONDS, isolation_level=None,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # A delivered inbox row keeps no words: the owner got them, and the row stays only to tell a repeat.
        conn.create_function("gone", 1, gone, deterministic=True)
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("BEGIN IMMEDIATE")
        try:
            # created says this open made the tables: the first start with a record, whose cuts are still in the log.
            self.created = not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'requests'"
                                            ).fetchone()
            for statement in TABLES + SEND_TABLES + EVENT_TABLES + ROSTER_TABLES:
                conn.execute(statement)
            # brain names the Rook that owns a request, which recovers it at a restart; client is who sent it.
            if "brain" not in {row[1] for row in conn.execute("PRAGMA table_info(requests)")}:
                conn.execute("ALTER TABLE requests ADD COLUMN brain TEXT")
            high = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'events'").fetchone()
            self.high = high[0] if high else 0
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        self.conn = conn
        self.file = mailbox._db_path(self.path)
        return self

    def event(self, kind, data, turn=None, client=None):
        """Store an event in the open transaction. The caller holds the lock; the commit publishes it."""
        cur = self.conn.execute(
            "INSERT INTO events (at, conversation, kind, turn, client, body) VALUES (?, coalesce((SELECT conversation "
            "FROM requests WHERE turn = ?), ''), ?, ?, ?, ?)",
            (time.time(), turn, kind, turn, client or self.client, json.dumps(data, separators=(",", ":"))))
        self.pending.append((cur.lastrowid, kind, data))

    def committed(self):
        """Commit the open transaction, then publish its events in order."""
        self.conn.execute("COMMIT")
        events, self.pending = self.pending, []
        for seq, kind, data in events:
            self.high = seq
            if self.on_event:
                try:
                    self.on_event(seq, kind, data)
                except Exception:  # A subscriber never breaks the record.
                    pass

    def rolled_back(self):
        self.pending = []
        self.conn.execute("ROLLBACK")

    @contextmanager
    def transaction(self):
        """One write transaction whose events publish after its commit. The caller holds the lock."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.rolled_back()
            raise
        self.committed()

    def write(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args)

    def read(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def accept(self, turn, conversation, source, text, at=None, tools_known=True, inbox_ids=(), client=None):
        """The row of a request Rook accepted, written before the request goes to the agent. It is the one write
        on the hot path, so it alone waits for the disk (synchronous FULL): a power loss cannot drop it.
        tools_known says the agent's harness marks a tool before the tool can run. When inbox_ids are given, those
        kept inbox rows are marked delivered in the same transaction so a crash cannot deliver them twice."""
        now = time.time() if at is None else at
        with self.lock:
            self.conn.execute("PRAGMA synchronous = FULL")
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                try:
                    sender = client or self.client
                    added = self.conn.execute(
                        "INSERT OR IGNORE INTO requests (turn, conversation, client, brain, source, text, at, state, "
                        "updated, tools_known) VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?)",
                        (turn, conversation, sender, self.client, source or "unknown", text, now, now,
                         int(tools_known))).rowcount
                    if added:
                        self.event("request", {"turn": turn, "state": "accepted", "text": text,
                                               "source": source or "unknown", "client": sender, "at": now}, turn, sender)
                    else:  # A device's command admitted it as queued: it reached the agent now.
                        self.conn.execute("UPDATE requests SET state = 'accepted', updated = ? WHERE turn = ? AND "
                                          "state = 'queued'", (now, turn))
                    for inbox_id in inbox_ids:
                        self.conn.execute(
                            "UPDATE inbox_items SET delivered = ?, text = gone(text) WHERE id = ? AND delivered IS NULL",
                            (now, inbox_id))
                    self.committed()
                except BaseException:
                    self.rolled_back()
                    raise
            finally:
                self.conn.execute("PRAGMA synchronous = NORMAL")

    def handed(self, turn):
        self.write("UPDATE requests SET state = 'handed', updated = ? WHERE turn = ? AND state = 'accepted'",
                   (time.time(), turn))

    def tools(self, turn, names):
        """A tool call started in this turn: its names, never its inputs."""
        self.write("UPDATE requests SET tools = trim(tools || ',' || ?, ','), updated = ?, state = CASE WHEN "
                   "state IN ('accepted', 'handed') THEN 'working' ELSE state END WHERE turn = ?",
                   (",".join(names), time.time(), turn))

    def draft(self, turn, text):
        """The answer as it streams, at most once a second from Rook. It may be commentary before a tool call."""
        self.write("UPDATE requests SET answer = ?, draft = 1, updated = ? WHERE turn = ? AND draft != 0 OR "
                   "turn = ? AND answer IS NULL", (text, time.time(), turn, turn))

    def answer(self, turns, text):
        """The final answer of these turns, each with its outcome event in the same transaction."""
        for turn in turns:
            with self.lock, self.transaction():
                if self.conn.execute("UPDATE requests SET answer = ?, draft = 0, updated = ?, state = CASE WHEN state "
                                     "IN ('closed', 'interrupted', 'empty') THEN state ELSE 'answered' END WHERE turn = ?",
                                     (text, time.time(), turn)).rowcount:
                    state = self.conn.execute("SELECT state FROM requests WHERE turn = ?", (turn,)).fetchone()[0]
                    self.event("request", {"turn": turn, "state": state, "answer": text}, turn)

    def speech(self, turn, state, heard=None, unheard=None):
        """Speech of the turn's answer: started, ended, or cut, with what the owner heard and did not hear."""
        self.write("UPDATE requests SET speech = ?, heard = coalesce(?, heard), unheard = coalesce(?, unheard), "
                   "updated = ? WHERE turn = ?", (state, heard, unheard, time.time(), turn))

    def close(self, turns, state="closed", reason=None):
        """These turns owe the owner nothing more: answered and heard, or interrupted by Stop or an agent error. A client
        already has an answered turn's outcome, so only a turn that ends without an answer gets an event."""
        for turn in turns:
            with self.lock, self.transaction():
                was = self.conn.execute("SELECT state FROM requests WHERE turn = ?", (turn,)).fetchone()
                if was and was[0] not in ENDED:
                    self.conn.execute("UPDATE requests SET state = ?, reason = ?, updated = ? WHERE turn = ?",
                                      (state, reason, time.time(), turn))
                    if was[0] != "answered":
                        self.event("request", {"turn": turn, "state": state}, turn)

    def settle_start(self, conversation, notes, describe, cuts=(), describe_wait=None):
        """At a start, in one transaction: each restart note becomes an owed notice, once, and each open row of an
        earlier conversation of this client becomes the notice describe(row) gives, if any, and ends as interrupted
        by the restart. Any leftover waiting card or held background command from an earlier conversation becomes
        the notice describe_wait(row) gives and is cleared. Another client's rows are its own. cuts, (time, text),
        become cut notices too: on the first start with a record, they are what the turn log says the last stop cut.
        Last, notices past their age bound and old settled rows are dropped."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                for at, text in notes:
                    if not self.conn.execute("SELECT 1 FROM notices WHERE client = ? AND kind = 'note' AND at = ? AND "
                                             "text = ?", (self.client, at, text)).fetchone():
                        self.owed_notice("note", text, at)
                # This brain recovers every request it owned, whoever sent it: a phone's request too.
                rows = self.conn.execute("SELECT * FROM requests WHERE state NOT IN ('closed', 'interrupted', 'empty') "
                                         "AND conversation != ? AND coalesce(brain, client) = ? ORDER BY seq",
                                         (conversation, self.client)).fetchall()
                for at, text in cuts:
                    self.owed_notice("cut", text, at)
                for row in rows:
                    if found := describe(row):
                        self.owed_notice("cut", found[1], found[0])
                    self.conn.execute("UPDATE requests SET state = 'interrupted', reason = 'restart', updated = ? "
                                      "WHERE seq = ?", (time.time(), row["seq"]))
                    self.event("request", {"turn": row["turn"], "state": "interrupted"}, row["turn"])
                now = time.time()
                open_waits = self.conn.execute(
                    "SELECT * FROM waits WHERE cleared IS NULL AND conversation != ? AND client = ? ORDER BY id",
                    (conversation, self.client)).fetchall()
                for row in open_waits:
                    if describe_wait and (found := describe_wait(row)):
                        self.owed_notice("cut", found[1], found[0])
                    self.conn.execute("UPDATE waits SET cleared = ? WHERE id = ?", (now, row["id"]))
                    if row["kind"] == "card":
                        self.event("card", {"id": row["key"], "state": "resolved"}, row["turn"])
                self.conn.execute("UPDATE notices SET cleared = ? WHERE cleared IS NULL AND client = ? AND (kind = "
                                  "'note' AND at < ? OR kind = 'cut' AND at < ?)",
                                  (now, self.client, now - NOTE_KEEP_SECONDS, now - CUT_KEEP_SECONDS))
                self.conn.execute("DELETE FROM inbox_items WHERE client = ? AND delivered IS NOT NULL AND delivered < ?",
                                  (self.client, now - NOTE_KEEP_SECONDS))
                self.conn.execute("DELETE FROM waits WHERE client = ? AND cleared IS NOT NULL AND cleared < ?",
                                  (self.client, now - NOTE_KEEP_SECONDS))
                self.committed()
            except BaseException:
                self.rolled_back()
                raise

    def owed_notice(self, kind, text, at):
        """Insert an owed notice and its event in the open transaction. A client learns of it, not its words."""
        notice = self.conn.execute("INSERT INTO notices (client, kind, text, at) VALUES (?, ?, ?, ?)",
                                   (self.client, kind, text, at)).lastrowid
        self.event("notice", {"id": notice, "kind": kind, "state": "owed"})

    def notice(self, kind, text, at=None):
        with self.lock, self.transaction():
            self.owed_notice(kind, text, time.time() if at is None else at)

    def notices(self, offered=False):
        """The notices the owner is still owed, oldest first. offered limits them to those a turn already carried."""
        return self.read("SELECT * FROM notices WHERE cleared IS NULL AND client = ?" + (" AND offered > 0" if offered
                                                                                        else "") + " ORDER BY at, id",
                         (self.client,))

    def offered(self, ids):
        for notice in ids:
            self.write("UPDATE notices SET offered = offered + 1 WHERE id = ?", (notice,))

    def partly(self, ids):
        """Speech of the turn that carried these notices started. The owner may have heard part of them."""
        for notice in ids:
            self.write("UPDATE notices SET partly = 1 WHERE id = ?", (notice,))

    def clear(self, ids):
        """The owner heard these notices to the end of the turn that carried them."""
        for notice in ids:
            with self.lock, self.transaction():
                if self.conn.execute("UPDATE notices SET cleared = ? WHERE id = ? AND cleared IS NULL",
                                     (time.time(), notice)).rowcount:
                    self.event("notice", {"id": notice, "state": "cleared"})

    def _timer_row(self, row):
        timer = {
            "id": row["id"], "label": row["label"], "due": row["due"],
            "seconds": row["seconds"], "clock": row["clock"],
            "kind": row["kind"], "task": row["task"], "set_at": row["set_at"],
        }
        if row["called"]:
            timer["call"] = True
        return timer

    def import_timers(self, timers, next_id):
        """Import the timers of a legacy timers.json, as a Rook without this store wrote it, in one transaction. It
        runs whenever the file exists, so timers set during a rollback come back after a redeploy. A timer already
        stored, by its label, due time and time set, is skipped, and one whose id is taken gets a new id. Return the
        number of entries that could not be read, which are skipped."""
        skipped = 0
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute("SELECT value FROM journal_meta WHERE key = 'timer_next'").fetchone()
                ids = {r["id"] for r in self.conn.execute("SELECT id FROM timers")}
                max_next = max([int(row["value"]) if row else 1, int(next_id or 1)]
                               + [int(i) + 1 for i in ids if i.isdigit()])
                for timer in timers:
                    try:
                        due = float(timer["due"])
                        label = str(timer.get("label") or "")
                        set_at = float(timer.get("set_at") or due)
                        values = (label, due, int(timer["seconds"]) if timer.get("seconds") is not None else None,
                                  timer.get("clock") or None,
                                  timer.get("kind") or ("task" if timer.get("task") else "announce"),
                                  timer.get("task") or None, set_at, 1 if timer.get("call") else 0)
                    except (KeyError, TypeError, ValueError):
                        skipped += 1
                        continue
                    if self.conn.execute("SELECT 1 FROM timers WHERE label = ? AND due = ? AND set_at = ?",
                                         (label, due, set_at)).fetchone():
                        continue
                    tid = str(timer.get("id"))
                    if tid in ids or not tid.isdigit():
                        tid = str(max_next)
                    max_next = max(max_next, int(tid) + 1)
                    ids.add(tid)
                    self.conn.execute("INSERT INTO timers (id, label, due, seconds, clock, kind, task, set_at, called) "
                                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (tid, *values))
                self.conn.execute("INSERT OR REPLACE INTO journal_meta (key, value) VALUES ('timer_next', ?)",
                                  (str(max_next),))
                self.conn.execute("COMMIT")
                return skipped
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def load_timers(self):
        """Return (timers, next_id) from the database, ordered by due time."""
        with self.lock:
            rows = self.conn.execute("SELECT * FROM timers ORDER BY due, id").fetchall()
            meta = self.conn.execute("SELECT value FROM journal_meta WHERE key = 'timer_next'").fetchone()
        timers = [self._timer_row(row) for row in rows]
        next_id = int(meta["value"]) if meta else 1
        next_id = max([next_id] + [int(t["id"]) + 1 for t in timers if str(t.get("id")).isdigit()])
        return timers, next_id

    def save_timer(self, timer, next_id=None):
        """Store or update one timer and advance timer_next in one transaction."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "INSERT OR REPLACE INTO timers (id, label, due, seconds, clock, kind, task, set_at, called) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(timer["id"]), str(timer.get("label") or ""), float(timer["due"]),
                     int(timer["seconds"]) if timer.get("seconds") is not None else None,
                     timer.get("clock") or None,
                     timer.get("kind") or ("task" if timer.get("task") else "announce"),
                     timer.get("task") or None,
                     float(timer.get("set_at", timer["due"])),
                     1 if timer.get("call") else 0))
                if next_id is not None:
                    self.conn.execute("INSERT OR REPLACE INTO journal_meta (key, value) VALUES ('timer_next', ?)",
                                      (str(int(next_id)),))
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def delete_timer(self, timer_id):
        self.write("DELETE FROM timers WHERE id = ?", (str(timer_id),))

    def clear_timers(self):
        self.write("DELETE FROM timers")

    def delete_timers(self, ids):
        with self.lock, self.transaction():
            for timer_id in ids:
                self.conn.execute("DELETE FROM timers WHERE id = ?", (str(timer_id),))

    def mark_timer_call(self, timer_id):
        self.write("UPDATE timers SET called = 1 WHERE id = ?", (str(timer_id),))

    def fire_task_timer(self, timer_id, event, text, arrived):
        """Remove a due task timer and insert its kept inbox entry in one transaction. Return the inbox row id. The
        row names its timer, so a second call after a write that landed late returns the same row: "given" when it
        was delivered already, and False only when neither the timer nor its row is in the store."""
        marker = json.dumps({"timer": str(timer_id)})
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                cur = self.conn.execute("DELETE FROM timers WHERE id = ?", (str(timer_id),))
                if cur.rowcount == 0:
                    row = self.conn.execute("SELECT id, delivered FROM inbox_items WHERE client = ? AND event = ? "
                                            "AND source = ? ORDER BY id DESC", (self.client, event, marker)).fetchone()
                    self.conn.execute("ROLLBACK")
                    return False if row is None else row["id"] if row["delivered"] is None else "given"
                inserted = self.conn.execute(
                    "INSERT INTO inbox_items (client, event, text, arrived, source) VALUES (?, ?, ?, ?, ?)",
                    (self.client, event, text, float(arrived), marker))
                inbox_id = inserted.lastrowid
                self.conn.execute("COMMIT")
                return inbox_id
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def import_inbox(self, entries):
        """Import the kept entries of a legacy inbox.json in one transaction, whenever the file exists. An entry
        already stored, by its event, text and arrival time, is skipped. Return the number that could not be read."""
        skipped = 0
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                for entry in entries:
                    try:
                        event, text, arrived = str(entry["event"]), str(entry["text"]), float(entry["arrived"])
                        source = json.dumps(entry["source"]) if "source" in entry else None
                    except (KeyError, TypeError, ValueError):
                        skipped += 1
                        continue
                    if not self.conn.execute("SELECT 1 FROM inbox_items WHERE client = ? AND event = ? AND arrived = ? "
                                             "AND text IN (?, ?)", (self.client, event, arrived, text,
                                                                    gone(text))).fetchone():
                        self.conn.execute("INSERT INTO inbox_items (client, event, text, arrived, source) VALUES "
                                          "(?, ?, ?, ?, ?)", (self.client, event, text, arrived, source))
                self.conn.execute("COMMIT")
                return skipped
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def load_inbox(self):
        """Return undelivered kept inbox entries for this client, oldest first."""
        rows = self.read("SELECT * FROM inbox_items WHERE client = ? AND delivered IS NULL ORDER BY id",
                         (self.client,))
        entries = []
        for row in rows:
            item = {"id": row["id"], "event": row["event"], "text": row["text"], "arrived": row["arrived"]}
            if row["source"] is not None and row["event"] == "inbox":  # A task timer's row names only its timer.
                try:
                    parsed = json.loads(row["source"])
                    if isinstance(parsed, dict):
                        item["source"] = parsed
                except ValueError:
                    pass
            entries.append(item)
        return entries

    def add_inbox(self, event, text, arrived, source=None):
        """Insert one kept inbox item and return its row id."""
        raw_source = json.dumps(source) if source is not None else None
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO inbox_items (client, event, text, arrived, source) VALUES (?, ?, ?, ?, ?)",
                (self.client, event, text, float(arrived), raw_source))
            return cur.lastrowid

    def deliver_inbox(self, ids):
        """Mark these kept inbox rows delivered."""
        now = time.time()
        with self.lock:
            for row_id in ids:
                self.conn.execute(
                    "UPDATE inbox_items SET delivered = ?, text = gone(text) WHERE id = ? AND delivered IS NULL",
                    (now, row_id))

    def take_startup_notes(self):
        """Mark and return (arrived, text) for undelivered startup notes of this client, oldest first."""
        now = time.time()
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self.conn.execute(
                    "SELECT id, arrived, text FROM inbox_items WHERE client = ? AND event = 'startup' "
                    "AND delivered IS NULL ORDER BY id", (self.client,)).fetchall()
                for row in rows:
                    self.conn.execute("UPDATE inbox_items SET delivered = ?, text = gone(text) WHERE id = ?",
                                      (now, row["id"]))
                self.conn.execute("COMMIT")
                return [(row["arrived"], row["text"]) for row in rows]
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def set_wait(self, conversation, kind, key, turn, tool, summary, at=None, announce=True):
        """Record a waiting permission card or held background command. Never store raw tool inputs. A card that waits
        behind the one shown is recorded with announce False: clients hear of it in card_shown, when it shows."""
        now = time.time() if at is None else at
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "UPDATE waits SET cleared = ? WHERE client = ? AND kind = ? AND key = ? AND cleared IS NULL",
                    (now, self.client, kind, key or ""))
                self.conn.execute(
                    "INSERT INTO waits (client, conversation, kind, key, turn, tool, summary, at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (self.client, conversation, kind, key or "", turn, tool or "", summary or "", now))
                if kind == "card" and announce:  # Its summary, never the tool's input: the phone gets the rest live.
                    self.event("card", card_event(key or "", turn, tool, summary), turn)
                self.committed()
            except BaseException:
                self.rolled_back()
                raise

    def card_shown(self, key):
        """A waiting card has come to the front: clients hear of it now, from its record."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute("SELECT turn, tool, summary FROM waits WHERE client = ? AND kind = 'card' "
                                        "AND key = ? AND cleared IS NULL", (self.client, key)).fetchone()
                if row:
                    self.event("card", card_event(key, row["turn"], row["tool"], row["summary"]), row["turn"])
                self.committed()
            except BaseException:
                self.rolled_back()
                raise

    def clear_wait(self, key=None, turn=None, kind=None, turns=None):
        """Clear matching open waiting cards or held commands for this client."""
        now = time.time()
        clauses = ["client = ?", "cleared IS NULL"]
        params = [now, self.client]
        if key is not None:
            clauses.append("key = ?")
            params.append(key)
        if turn is not None:
            clauses.append("turn = ?")
            params.append(turn)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if turns is not None:
            turn_list = [t for t in turns if t]
            if not turn_list:
                return
            clauses.append(f"turn IN ({','.join('?' for _ in turn_list)})")
            params.extend(turn_list)
        where = " AND ".join(clauses)
        with self.lock, self.transaction():
            cards = self.conn.execute(f"SELECT key, turn FROM waits WHERE kind = 'card' AND {where}",
                                      tuple(params[1:])).fetchall()
            self.conn.execute(f"UPDATE waits SET cleared = ? WHERE {where}", tuple(params))
            for card in cards:
                self.event("card", {"id": card["key"], "state": "resolved"}, card["turn"])

    def lists_changed(self, name):
        """The work list or the mailbox changed: a client reads it again."""
        with self.lock, self.transaction():
            self.event("lists", {"list": name})

    def admit(self, device, command_id, fingerprint, kind, turn=None, conversation="", text=None, source="typed"):
        """Admit a device's command durably before it runs, in one transaction. An ask inserts its request row as
        queued; a speak inserts its row as hearing with no text yet. Return (status, turn, row): "accepted" for a
        new command, "duplicate" for the same id and input, with the command row, or "conflict" for other input."""
        now = time.time()
        with self.lock, self.transaction():
            row = self.conn.execute("SELECT * FROM commands WHERE device = ? AND id = ?", (device, command_id)).fetchone()
            if row:
                return ("duplicate" if row["fingerprint"] == fingerprint else "conflict"), row["turn"], dict(row)
            if kind == "speak" and self.conn.execute(
                    "SELECT 1 FROM requests WHERE client = ? AND state = 'hearing' LIMIT 1", (device,)).fetchone():
                return "busy", None, None
            self.conn.execute("INSERT INTO commands (device, id, fingerprint, kind, turn, status, at, updated) VALUES "
                              "(?, ?, ?, ?, ?, 'admitted', ?, ?)", (device, command_id, fingerprint, kind, turn, now, now))
            if kind == "ask":
                self.conn.execute(
                    "INSERT INTO requests (turn, conversation, client, brain, source, text, at, state, updated, "
                    "tools_known) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, 1)",
                    (turn, conversation, device, self.client, source, text, now, now))
                self.event("request", {"turn": turn, "state": "queued", "text": text, "source": source,
                                       "client": device, "at": now}, turn, device)
            elif kind == "speak":
                self.conn.execute(
                    "INSERT INTO requests (turn, conversation, client, brain, source, text, at, state, updated, "
                    "tools_known) VALUES (?, ?, ?, ?, ?, '', ?, 'hearing', ?, 1)",
                    (turn, conversation, device, self.client, source or "spoken", now, now))
                self.event("request", {"turn": turn, "state": "hearing", "text": "", "source": source or "spoken",
                                       "client": device, "at": now}, turn, device)
        return "accepted", turn, None

    def heard(self, turn, text):
        """A phone recording produced words: store its text, move from hearing to queued, and emit its event."""
        now = time.time()
        with self.lock, self.transaction():
            changed = self.conn.execute(
                "UPDATE requests SET text = ?, state = 'queued', updated = ? WHERE turn = ? AND state = 'hearing'",
                (text, now, turn)).rowcount
            if not changed:
                return False
            row = self.conn.execute("SELECT source, client, at FROM requests WHERE turn = ?", (turn,)).fetchone()
            self.event("request", {"turn": turn, "state": "queued", "text": text, "source": row["source"],
                                   "client": row["client"], "at": row["at"]}, turn, row["client"])
            return True

    def empty_audio(self, turn, reason="empty"):
        """A phone recording held no words or could not be decoded: settle it as empty and emit its event."""
        now = time.time()
        with self.lock, self.transaction():
            changed = self.conn.execute(
                "UPDATE requests SET state = 'empty', reason = ?, updated = ? WHERE turn = ? AND state = 'hearing'",
                (reason, now, turn)).rowcount
            if not changed:
                return False
            self.event("request", {"turn": turn, "state": "empty", "reason": reason}, turn)
            return True

    def command_done(self, device, command_id, status, result=None):
        """A command ran, or could not run: its status, and for a card its answer, kept for a retry."""
        self.write("UPDATE commands SET status = ?, result = coalesce(?, result), updated = ? WHERE device = ? AND "
                   "id = ?", (status, None if result is None else json.dumps(result), time.time(), device, command_id))

    def prune_events(self, now=None):
        """Drop events and commands past their age, a batch per transaction. The highest seq stays."""
        now = time.time() if now is None else now
        cutoff = now - EVENT_KEEP_SECONDS
        while True:
            with self.lock, self.transaction():
                gone_events = self.conn.execute("DELETE FROM events WHERE seq IN (SELECT seq FROM events WHERE at < ? "
                                                "ORDER BY seq LIMIT ?)", (cutoff, EVENT_PRUNE_BATCH)).rowcount
                gone_commands = self.conn.execute("DELETE FROM commands WHERE rowid IN (SELECT rowid FROM commands "
                                                  "WHERE updated < ? LIMIT ?)",
                                                  (now - COMMAND_KEEP_SECONDS, EVENT_PRUNE_BATCH)).rowcount
            if gone_events < EVENT_PRUNE_BATCH and gone_commands < EVENT_PRUNE_BATCH:
                return

    def send_intent(self, key, tool, machine, thread, conversation, turn, description="", text=None, project=None):
        """A send to a T3 thread, seen as its tool call starts. A row relay.py wrote first keeps its brief."""
        with self.lock:
            intend(self.conn, self.client, key, tool, machine, thread, conversation=conversation, turn=turn,
                   description=description, text_digest=None if text is None else digest(text), project=project)

    def send_settle(self, key, outcome, result):
        """A send's outcome. A send that landed also settles an open handoff row of the same text to the same thread:
        the agent sent that brief under a key of its own."""
        with self.lock:
            settle(self.conn, self.client, key, outcome, result)
            sent = self.conn.execute("SELECT thread, digest FROM sends WHERE client = ? AND key = ?",
                                     (self.client, key)).fetchone()
            if outcome == "landed" and sent and sent["digest"]:
                self.conn.execute("UPDATE sends SET outcome = ?, result = ?, settled = ?, brief = NULL WHERE client = ? "
                                  "AND tool = 'handoff' AND outcome IS NULL AND thread = ? AND digest = ? AND key != ?",
                                  (outcome, result, time.time(), self.client, sent["thread"], sent["digest"], key))

    def sends_open(self, before):
        """The sends from before this start whose outcome is not known."""
        return self.read("SELECT * FROM sends WHERE client = ? AND outcome IS NULL AND at < ? ORDER BY id",
                         (self.client, before))

    def send_told(self, key, outcome):
        self.write("UPDATE sends SET told = ? WHERE client = ? AND key = ?", (outcome, self.client, key))

    def sends_prune(self, now=None):
        """Settle as unknown the sends looked up too long, and drop settled rows past their age. Return the rows
        settled now that no notice told."""
        now = time.time() if now is None else now
        with self.lock:
            untold = self.conn.execute("SELECT * FROM sends WHERE client = ? AND outcome IS NULL AND at < ? AND told "
                                       "IS NULL", (self.client, now - SEND_RETRY_SECONDS)).fetchall()
            self.conn.execute("UPDATE sends SET outcome = coalesce(told, 'unknown'), settled = ?, brief = NULL WHERE "
                              "client = ? AND outcome IS NULL AND at < ?", (now, self.client, now - SEND_RETRY_SECONDS))
            self.conn.execute("DELETE FROM sends WHERE client = ? AND settled < ?", (self.client, now - SEND_KEEP_SECONDS))
        return untold

    def roster(self):
        """The saved roster rows."""
        return [{**dict(row), "settled": bool(row["settled"]), "snoozed": bool(row["snoozed"])}
                for row in self.read("SELECT * FROM roster")]

    def roster_save(self, puts, drops):
        """Write changed roster rows and delete closed ones, in one transaction."""
        with self.lock, self.transaction():
            self.conn.executemany(f"INSERT OR REPLACE INTO roster ({', '.join(ROSTER_COLUMNS)}) VALUES "
                                  f"({', '.join('?' for _ in ROSTER_COLUMNS)})",
                                  [tuple(row[column] for column in ROSTER_COLUMNS) for row in puts])
            self.conn.executemany("DELETE FROM roster WHERE orchestrator = ? AND machine = ? AND id = ?", drops)

    def cut_notice(self, at, text):
        """Replace the text of the cut notice from this time that no turn carried yet. Return whether one was."""
        return self.write("UPDATE notices SET text = ? WHERE client = ? AND kind = 'cut' AND at = ? AND offered = 0 "
                          "AND cleared IS NULL", (text, self.client, at)).rowcount > 0


def card_event(key, turn, tool, summary):
    """A waiting card as a client sees it, from what the record keeps: never the tool's input. A question with
    options is answered at the desk."""
    ask = tool == "AskUserQuestion"
    return {"id": key, "turn": turn, "tool": None if ask else tool, "question": summary, "options": [],
            "desk": ask, "state": "opened"}


def reader(file):
    """A connection of its own for a reader on another thread, such as the phone server's."""
    conn = sqlite3.connect(str(file), timeout=BUSY_SECONDS, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def read_snapshot(file, brain):
    """The durable part of a snapshot and its cursor, read in one read transaction: the requests in flight and the
    latest others, and the owed notices. Live fields come from the companion's memory."""
    conn = reader(file)
    try:
        conn.execute("BEGIN")
        high = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'events'").fetchone()
        rows = conn.execute(
            f"SELECT * FROM requests WHERE coalesce(brain, client) = ? AND state != 'empty' AND (state IN {IN_FLIGHT} "
            f"OR seq IN (SELECT seq FROM requests WHERE coalesce(brain, client) = ? AND state NOT IN {IN_FLIGHT} "
            "AND state != 'empty' ORDER BY seq DESC LIMIT ?)) ORDER BY seq",
            (brain, brain, SNAPSHOT_EXCHANGES)).fetchall()
        notices = conn.execute("SELECT id, kind, at FROM notices WHERE cleared IS NULL AND client = ? ORDER BY at, id",
                               (brain,)).fetchall()
        conn.execute("COMMIT")
    finally:
        conn.close()
    return {"cursor": high[0] if high else 0,
            "requests": [{"turn": r["turn"], "source": r["source"], "client": r["client"], "text": r["text"],
                          "state": r["state"], "answer": None if r["draft"] else r["answer"], "at": r["at"]}
                         for r in rows],
            "notices": [dict(n) for n in notices]}


def read_events(file, cursor, upto):
    """Stored events with cursor < seq <= upto, as (seq, kind, data), or None when the cursor is older than what is
    kept, so the client must read a snapshot again."""
    if cursor > upto:
        return None
    conn = reader(file)
    try:
        conn.execute("BEGIN")
        oldest = conn.execute("SELECT min(seq) FROM events").fetchone()[0]
        rows = conn.execute("SELECT seq, kind, body FROM events WHERE seq > ? AND seq <= ? ORDER BY seq",
                            (cursor, upto)).fetchall()
        conn.execute("COMMIT")
    finally:
        conn.close()
    if cursor < upto and (oldest is None or cursor < oldest - 1):
        return None
    return [(row["seq"], row["kind"], json.loads(row["body"])) for row in rows]


def gone(text):
    """What a delivered inbox row keeps of its text: a hash, so an import can tell it again, and no words."""
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def digest(text):
    """The sent text's hash. T3 keeps the text without its outer white space."""
    return hashlib.sha256(text.strip().encode()).hexdigest()


def handoff_key():
    """A new clientRequestId for each handoff, so a brief sent twice on purpose is two messages. Its row keeps it, and
    relay.py handoff --again prints it for a send again."""
    return "rook-" + os.urandom(12).hex()


def intend(conn, client, key, tool, machine, thread, at=None, conversation="", turn=None, work=None, description="",
           text_digest=None, brief=None, project=None):
    conn.execute(
        "INSERT INTO sends (client, key, conversation, turn, tool, machine, thread, project, work, description, "
        "digest, brief, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (client, key) DO UPDATE SET "
        "conversation = CASE excluded.conversation WHEN '' THEN conversation ELSE excluded.conversation END, "
        "turn = coalesce(excluded.turn, turn), digest = coalesce(excluded.digest, digest)",
        (client, key, conversation, turn, tool, machine, thread, project, work, description[:200], text_digest, brief,
         time.time() if at is None else at))


def settle(conn, client, key, outcome, result):
    """The send's outcome: landed, failed, or missing. Its brief goes at once."""
    conn.execute("UPDATE sends SET outcome = ?, result = ?, settled = ?, brief = NULL WHERE client = ? AND key = ? AND "
                 "outcome IS NULL", (outcome, result, time.time(), client, key))


# The mailbox's file, as mailbox.MAILBOX names it, and the mailbox schema version this code knows, which check()
# keeps equal to mailbox.SCHEMA_VERSION.
KNOWN_SCHEMA = 2


def __getattr__(name):
    """journal.MAILBOX: read at each use, as mailbox.MAILBOX is. A check pins another file by assigning it."""
    if name == "MAILBOX":
        return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "rook/mailbox.db"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def with_sends(path, write, *args, **kwargs):
    """One write of relay.py, on a connection of its own. It is on a handoff's path, so it skips the mailbox's full
    check: it writes only to a file of the schema it knows, whose send table Rook's own open made after that check.
    Raise sqlite3.Error otherwise, and write nothing."""
    target = Path(path) if path is not None else globals().get("MAILBOX") or __getattr__("MAILBOX")
    if not target.exists():
        raise sqlite3.OperationalError("no mailbox file")
    conn = sqlite3.connect(str(target), timeout=BUSY_SECONDS, isolation_level=None)
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] != KNOWN_SCHEMA or not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sends'").fetchone():
            raise sqlite3.DatabaseError("not a record this code knows")
        conn.execute("PRAGMA synchronous = NORMAL")  # The file is in WAL mode: a crash of Rook loses no commit.
        return write(conn, *args, **kwargs)
    finally:
        conn.close()


def check():
    import ast
    import mailbox
    import re
    import subprocess
    import sys
    import tempfile
    assert KNOWN_SCHEMA == mailbox.SCHEMA_VERSION and __getattr__("MAILBOX") == mailbox.MAILBOX
    # relay.py imports this module on a handoff's path, so importing it loads no mailbox and nothing heavy.
    loaded = subprocess.run([sys.executable, "-c", "import sys, journal; print(' '.join(sys.modules))"],
                            cwd=Path(__file__).parent, capture_output=True, text=True, check=True).stdout.split()
    assert not {"mailbox", "agent_inbox", "asyncio", "tempfile"} & set(loaded), loaded
    # Two builders add to this file: no table, function or method is defined twice.
    tree = ast.parse(Path(__file__).read_text())
    journal_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Journal")
    for scope in (tree.body, journal_class.body):
        names = [node.name for node in scope if isinstance(node, ast.FunctionDef)]
        assert len(names) == len(set(names)), names
    tables = re.findall(r"CREATE (?:TABLE|INDEX) IF NOT EXISTS (\w+)", "".join(TABLES + SEND_TABLES))
    assert len(tables) == len(set(tables)), tables
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "rook/mailbox.db"
        visa = mailbox.observe("reminder", "Renew the visa.", path=path)  # A mailbox file without the record's tables.
        try:  # relay.py writes a send only to a file whose send table Rook's own open made.
            with_sends(path, intend, CLIENT, "k0", "handoff", "oak", "t")
            raise AssertionError("with_sends wrote to a file Rook never opened")
        except sqlite3.DatabaseError:
            pass
        mailbox.dismiss(visa["id"], "test", path=path)
        record = Journal(path).open()
        with_sends(path, intend, CLIENT, "k0", "handoff", "oak", "t", text_digest=digest("Hi.\n"), brief="Hi.")
        with_sends(path, settle, CLIENT, "k0", "landed", "m")
        assert tuple(record.read("SELECT outcome, brief, digest FROM sends")[0]) == ("landed", None, digest("Hi."))
        record.write("DELETE FROM sends")
        base = time.time()
        record.accept("t1", "s1", "spoken", "Fix the halo.", at=base)
        record.accept("t2", "s1", "spoken", "Send it to Fable.", at=base + 1)
        record.accept("t3", "s1", "typed", "What time is it?", at=base + 2)
        record.handed("t1")
        record.tools("t2", ["Bash"])
        record.tools("t2", ["mcp__t3__t3_thread_send"])
        record.draft("t3", "It is ten")
        record.answer(["t3"], "It is ten past two.")
        record.speech("t3", "started")
        rows = {row["turn"]: row for row in record.read("SELECT * FROM requests")}
        assert [rows[t]["seq"] for t in ("t1", "t2", "t3")] == [1, 2, 3] and rows["t1"]["client"] == "desktop"
        assert rows["t1"]["state"] == "handed" and rows["t2"]["state"] == "working"
        assert rows["t2"]["tools"] == "Bash,mcp__t3__t3_thread_send"
        assert (rows["t3"]["state"], rows["t3"]["answer"], rows["t3"]["draft"]) == ("answered", "It is ten past two.", 0)
        record.draft("t3", "late draft")  # A draft never replaces a final answer.
        assert record.read("SELECT answer FROM requests WHERE turn = 't3'")[0][0] == "It is ten past two."
        # A start turns the earlier conversation's open rows into notices, once, and notes once each.
        record.settle_start("s2", [(base - 10, "Fixed the dust.")], lambda row: (row["at"], f"cut {row['turn']}"))
        record.settle_start("s2", [(base - 10, "Fixed the dust.")], lambda row: (row["at"], f"cut {row['turn']}"))
        assert [(n["kind"], n["text"]) for n in record.notices()] == [
            ("note", "Fixed the dust."), ("cut", "cut t1"), ("cut", "cut t2"), ("cut", "cut t3")]
        assert {row["state"] for row in record.read("SELECT state FROM requests")} == {"interrupted"}
        ids = [n["id"] for n in record.notices()]
        record.offered(ids[:2])
        record.partly(ids[:1])
        assert [n["id"] for n in record.notices(offered=True)] == ids[:2]
        record.clear(ids[:1])
        assert [n["id"] for n in record.notices()] == ids[1:]
        record.accept("t4", "s2", "spoken", "Hello.")
        record.close(["t4"])
        record.answer(["t4"], "Hi.")  # An answer after the end keeps the row ended.
        assert record.read("SELECT state FROM requests WHERE turn = 't4'")[0][0] == "closed"
        # Timers and kept inbox: an import that never doubles, transactional task fire, atomic accept + deliver.
        legacy_timer = {"id": "3", "label": "Tea", "due": base + 60, "seconds": 60, "clock": None,
                        "kind": "task", "task": "Check the kettle.", "set_at": base}
        assert record.import_timers([legacy_timer], 4) == 0
        assert record.import_timers([legacy_timer], 4) == 0  # Imported again, as after a rollback: no second row.
        timers, next_id = record.load_timers()
        assert len(timers) == 1 and timers[0]["id"] == "3" and next_id == 4, (timers, next_id)
        # A rollback's timer whose id is taken gets a new one; a bad entry is skipped and counted; no set_at is fine.
        assert record.import_timers([{**legacy_timer, "label": "Rice", "set_at": None}, {"id": "9"}], 4) == 1
        assert [(t["id"], t["label"]) for t in record.load_timers()[0]] == [("3", "Tea"), ("4", "Rice")]
        record.delete_timer("4")
        fired_id = record.fire_task_timer("3", "timer", "Check the kettle.", base + 60)
        assert isinstance(fired_id, int) and fired_id > 0
        assert record.fire_task_timer("3", "timer", "Check the kettle.", base + 60) == fired_id  # A late retry.
        assert record.fire_task_timer("8", "timer", "Gone.", base + 60) is False
        assert record.load_timers()[0] == []
        inbox = record.load_inbox()
        assert len(inbox) == 1 and inbox[0]["id"] == fired_id and inbox[0]["event"] == "timer", inbox
        assert "source" not in inbox[0]  # Its row names its timer, which is not a thread's source.
        # A legacy inbox import keeps source dicts and never doubles.
        assert record.import_inbox([{"event": "inbox", "text": "Build done.", "arrived": base + 5,
                                     "source": {"machine": "oak", "thread": "t-1"}}]) == 0
        assert record.import_inbox([{"event": "inbox", "text": "Build done.", "arrived": base + 5}, {"x": 1}]) == 1
        inbox = record.load_inbox()
        assert len(inbox) == 2 and inbox[1]["source"]["thread"] == "t-1", inbox
        # Delivering via accept marks the inbox row delivered in the same transaction.
        record.accept("t5", "s2", "timer", "Check the kettle.", inbox_ids=[fired_id])
        remaining = record.load_inbox()
        assert [e["text"] for e in remaining] == ["Build done."], remaining
        assert record.read("SELECT text FROM inbox_items WHERE id = ?", (fired_id,))[0][0] == gone("Check the kettle.")
        record.deliver_inbox([remaining[0]["id"]])
        assert not record.read("SELECT 1 FROM inbox_items WHERE text LIKE '%Build done%'")
        assert record.import_inbox([{"event": "inbox", "text": "Build done.", "arrived": base + 5}]) == 0
        assert record.load_inbox() == []  # A delivered entry imported again is told by its hash: no repeat.
        record.add_inbox("startup", "Fixed the dust.", base + 6)
        assert record.take_startup_notes() == [(base + 6, "Fixed the dust.")]
        assert not record.read("SELECT 1 FROM inbox_items WHERE text LIKE '%dust%'")
        record.close(["t5"])
        # Waiting cards and held commands settle into owed notices across a restart, and never twice.
        record.set_wait("s2", "card", "req-1", "t6", "Bash", "Claude requests Bash.", at=base + 10)
        record.set_wait("s2", "held", "held-t6", "t6", "Bash", "Bash", at=base + 11)
        record.set_wait("s2", "card", "req-2", "t7", "Edit", "Claude requests Edit.", at=base + 12)
        record.clear_wait(key="req-2")
        record.settle_start("s3", [], lambda row: None,
                            describe_wait=lambda row: (row["at"], f"wait {row['kind']} {row['tool']}"))
        wait_notices = [n["text"] for n in record.notices() if n["text"].startswith("wait ")]
        assert wait_notices == ["wait card Bash", "wait held Bash"], wait_notices
        record.settle_start("s4", [], lambda row: None,
                            describe_wait=lambda row: (row["at"], f"wait {row['kind']} {row['tool']}"))
        assert [n["text"] for n in record.notices() if n["text"].startswith("wait ")] == wait_notices
        # The mailbox keeps its own schema version, so a Rook without the journal opens the file, and a redeploy
        # opens it again with every row.
        with mailbox._connect(path) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == mailbox.SCHEMA_VERSION == 2
            # A file from a Rook that had the retired action ledger opens as before, and its rows stay.
            conn.execute("CREATE TABLE actions (id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, state TEXT)")
            conn.execute("INSERT INTO actions (key, state) VALUES ('act-1', 'confirmed')")
            conn.execute("INSERT INTO journal_meta (key, value) VALUES ('action_seq', '1')")
        mailbox.observe("reminder", "Renew the passport.", path=path)
        again = Journal(path).open()
        assert len(again.read("SELECT * FROM requests")) == 5 and mailbox.items(path=path)[0]["kind"] == "reminder"
        assert [tuple(row) for row in again.read("SELECT key, state FROM actions")] == [("act-1", "confirmed")]
        # Events: each beside the change it describes, published after the commit in order, two for a turn.
        record = Journal(Path(folder) / "events/mailbox.db").open()
        heard = []
        record.on_event = lambda seq, kind, data: heard.append((seq, kind, data.get("state")))
        record.accept("e1", "s9", "spoken", "Dim the lights.")
        record.answer(["e1"], "Done.")
        record.close(["e1"])  # Answered already: no third event.
        assert [k for _, k, _ in heard] == ["request", "request"] and record.high == heard[-1][0]
        assert read_events(record.file, 0, record.high) == [(heard[0][0], "request", {
            "turn": "e1", "state": "accepted", "text": "Dim the lights.", "source": "spoken", "client": "desktop",
            "at": record.read("SELECT at FROM requests WHERE turn = 'e1'")[0][0]}), (heard[1][0], "request", {
            "turn": "e1", "state": "answered", "answer": "Done."})]
        # A device's command is admitted once: the same id again is a duplicate, other input a conflict.
        assert record.admit("dev-1", "c1", "f1", "ask", "e2", "s9", "Is it raining?") == ("accepted", "e2", None)
        assert record.admit("dev-1", "c1", "f1", "ask", "e3", "s9", "Is it raining?")[:2] == ("duplicate", "e2")
        assert record.admit("dev-1", "c1", "f2", "ask", "e4", "s9", "Other words.")[0] == "conflict"
        assert record.read("SELECT state, client, brain FROM requests WHERE turn = 'e2'")[0][:] == (
            "queued", "dev-1", "desktop")
        record.accept("e2", "s9", "typed", "Is it raining?", client="dev-1")  # It reached the agent.
        snap = read_snapshot(record.file, "desktop")
        assert snap["cursor"] == record.high and [(r["turn"], r["state"], r["client"]) for r in snap["requests"]] == [
            ("e1", "closed", "desktop"), ("e2", "accepted", "dev-1")]
        # A card's event keeps its summary, never the tool's input; clearing it resolves it.
        record.set_wait("s9", "card", "req-9", "e2", "Bash", "Claude requests Bash.")
        record.clear_wait("req-9")
        assert [d for _, k, d in heard if k == "card"] == ["opened", "resolved"]
        # Recovery belongs to the brain: a restart ends the phone's request too, with its event.
        record.settle_start("s10", [], lambda row: None)
        assert record.read("SELECT state FROM requests WHERE turn = 'e2'")[0][0] == "interrupted"
        assert heard[-1][1:] == ("request", "interrupted")
        # Voice upload admission (speak): hearing -> queued with text, hearing -> empty, restart while hearing.
        assert record.admit("dev-1", "s-ok", "h1", "speak", "v1", "s10", "", "spoken") == ("accepted", "v1", None)
        assert record.admit("dev-1", "s-ok", "h1", "speak", "v1b", "s10", "", "spoken")[:2] == ("duplicate", "v1")
        assert record.admit("dev-1", "s-ok", "h2", "speak", "v1c", "s10", "", "spoken")[0] == "conflict"
        assert record.read("SELECT state, text, source FROM requests WHERE turn = 'v1'")[0][:] == ("hearing", "", "spoken")
        assert record.heard("v1", "Check the gate.") is True
        assert record.read("SELECT state, text FROM requests WHERE turn = 'v1'")[0][:] == ("queued", "Check the gate.")
        assert record.admit("dev-1", "s-empty", "h3", "speak", "v2", "s10", "", "spoken") == ("accepted", "v2", None)
        assert record.empty_audio("v2") is True
        assert record.read("SELECT state FROM requests WHERE turn = 'v2'")[0][0] == "empty"
        assert record.admit("dev-1", "s-cut", "h4", "speak", "v3", "s10", "", "spoken") == ("accepted", "v3", None)
        snap = read_snapshot(record.file, "desktop")
        assert any(r["turn"] == "v3" and r["state"] == "hearing" for r in snap["requests"]), snap
        record.settle_start("s11", [], lambda row: (row["at"], f"cut {row['turn']} {row['state']}"))
        assert record.read("SELECT state FROM requests WHERE turn = 'v2'")[0][0] == "empty"
        assert record.read("SELECT state FROM requests WHERE turn = 'v3'")[0][0] == "interrupted"
        assert any("cut v3 hearing" in n["text"] for n in record.notices())
        # Pruning drops old events in batches and keeps the highest seq.
        high = record.high
        record.prune_events(now=time.time() + EVENT_KEEP_SECONDS + 60)
        assert not record.read("SELECT * FROM events") and Journal(record.file).open().high == high
        assert read_events(record.file, 1, high) is None and read_events(record.file, high, high) == []
    print("Request journal: all checks passed.")


if __name__ == "__main__":
    check()
