"""The small HTTP/1.1 server for Rook's phone app, built on asyncio streams and the standard library.

The server binds to 127.0.0.1 only, unless it is given a home LAN address too (lan). It enforces strict HTTP/1.1
framing, Host and Origin checks, and device cookies.
It knows nothing about Rook beyond the small session interface below.

Session interface (methods may be sync or async unless noted):
- snapshot(device_id) -> dict: return the protocol v1 snapshot dictionary, including the cursor.
- high_water() -> int: return the highest committed stored event sequence number.
- events_after(cursor, upto) -> list[Event] | None: return stored events with cursor < seq <= upto, or None if too old.
- subscribe(callback) -> None: sync, returns at once. Register callback(event) for new stored and live events.
- unsubscribe(callback) -> None: sync, returns at once. Remove a registered callback.
- command(device_id, body) -> dict: run one command durably and idempotently, and return its JSON result dict.
- audio(device_id, command_id, content_type, body) -> dict: admit and transcribe one recording, and return a JSON dict.
- speech(device_id, speech_id) -> tuple[str, bytes] | None: return (content_type, bytes) for one clip, or None if refused.
- work() -> list[dict]: return the current work list.
- mailbox() -> dict: return the current mailbox dictionary.

Stored events carry an integer seq on Event(kind, data, seq). Live events leave seq as None.
A command handler may raise CommandError(status, message) to choose a 4xx status code.

Run the hermetic check: scripts/capped python desktop/server.py --check
"""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import tempfile
import threading
import time
from typing import Any, Protocol
from urllib.parse import parse_qs

# Transport limits.
MAX_REQUEST_LINE = 1024
MAX_HEADER_BYTES = 8192
MAX_HEADER_COUNT = 32
MAX_BODY_BYTES = 16384
MAX_AUDIO_BYTES = 4 * 1024 * 1024
MAX_AUDIO_IN_FLIGHT = 8 * 1024 * 1024
MAX_SPEECH_BYTES = 2 * 1024 * 1024
HEADER_TIMEOUT = 5.0
BODY_TIMEOUT = 5.0
TOTAL_READ_TIMEOUT = 10.0
AUDIO_READ_TIMEOUT = 30.0
WRITE_TIMEOUT = 5.0
KEEPALIVE_SECONDS = 15.0
STREAM_QUEUE_SIZE = 128
MAX_CONNECTIONS = 64
MAX_STREAMS = 32
MAX_DEVICE_STREAMS = 4
MAX_DEVICE_AUDIO_UPLOADS = 1

# Pairing and store limits.
PAIR_CODE_TTL = 600.0
PAIR_RATE_MAX = 5
PAIR_RATE_WINDOW = 60.0
PAIR_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
PAIR_CODE_LENGTH = 6
COOKIE_NAME = "rook_device"
COOKIE_MAX_AGE = 31536000
LAST_SEEN_STEP = 10.0
STORE_BUSY_SECONDS = 0.25

DEFAULT_STATIC_DIR = Path(__file__).resolve().parent.parent / "phone"
DEFAULT_THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"
STATIC_FILES: dict[str, tuple[str, str]] = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/presence.js": ("presence.js", "text/javascript; charset=utf-8"),
    "/forms.json": ("forms.json", "application/json; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
}
# The Mac presence panel's page. Served, like /themes/, only when a local presence token is set (macOS only),
# so Linux routes stay as they were: unpaired 401, paired 404.
PRESENCE_FILES: dict[str, tuple[str, str]] = {
    "/presence": ("presence.html", "text/html; charset=utf-8"),
    "/presence.css": ("presence.css", "text/css; charset=utf-8"),
    "/presence-host.js": ("presence-host.js", "text/javascript; charset=utf-8"),
}
THEME_FILE_RE = re.compile(r"^/themes/([a-z0-9_-]+)/(?:(baked)/)?([a-z0-9_.-]+)$")
THEME_MIME: dict[str, str] = {
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".webp": "image/webp",
}
# The stage's own files, the same module the desktop's stage host loads, from the repo's stage folder. A fixed list.
STAGE_DIR = Path(__file__).resolve().parent.parent / "stage"
STAGE_FILES: dict[str, tuple[str, str]] = {
    "/stage/stage.js": ("stage.js", "text/javascript; charset=utf-8"),
    "/stage/stage.css": ("stage.css", "text/css; charset=utf-8"),
    "/stage/art/rook-dust.js": ("art/rook-dust.js", "text/javascript; charset=utf-8"),
    "/stage/art/nova-rook.png": ("art/nova-rook.png", "image/png"),
}
if STAGE_DIR.is_dir():  # The public snapshot leaves the shelved stage out.
    STATIC_FILES.update(STAGE_FILES)
ROUTE_METHODS: dict[str, str] = {
    **{path: "GET" for path in STATIC_FILES},
    "/pair": "POST",
    "/snapshot": "GET",
    "/events": "GET",
    "/command": "POST",
    "/audio": "POST",
    "/work": "GET",
    "/mailbox": "GET",
}
AUDIO_UPLOAD_TYPES = frozenset({"audio/webm", "audio/ogg", "audio/mp4"})
SPEECH_CONTENT_TYPES = frozenset({"audio/ogg", "audio/wav", "audio/mpeg", "audio/mp4"})
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "media-src 'self'; connect-src 'self'; manifest-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
PERMISSIONS_POLICY = "microphone=(self), camera=(), geolocation=(), display-capture=(), payment=(), usb=()"
STATUS_PHRASES: dict[int, str] = {
    200: "OK",
    206: "Partial Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    409: "Conflict",
    411: "Length Required",
    413: "Content Too Large",
    414: "URI Too Long",
    415: "Unsupported Media Type",
    416: "Range Not Satisfiable",
    417: "Expectation Failed",
    429: "Too Many Requests",
    431: "Request Header Fields Too Large",
    500: "Internal Server Error",
    503: "Service Unavailable",
    505: "HTTP Version Not Supported",
}
HEADER_NAME_RE = re.compile(rb"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
HTTP_VERSION_RE = re.compile(rb"^HTTP/\d\.\d$")
TOKEN_VALUE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SPEECH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CODECS_VALUE_RE = re.compile(r"^[A-Za-z0-9._, -]{1,64}$")

STORE_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        created_at REAL NOT NULL,
        last_seen REAL NOT NULL,
        revoked_at REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pairing_codes (
        code_hash TEXT PRIMARY KEY,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        used_at REAL
    )
    """,
)


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    created_at: float
    last_seen: float


@dataclass(frozen=True)
class Event:
    kind: str
    data: dict[str, Any]
    seq: int | None = None


class Session(Protocol):
    """The seam between the HTTP server and Rook's session."""

    def snapshot(self, device_id: str) -> Any: ...
    def high_water(self) -> Any: ...
    def events_after(self, cursor: int, upto: int) -> Any: ...
    def subscribe(self, callback: Callable[[Event], None]) -> None: ...
    def unsubscribe(self, callback: Callable[[Event], None]) -> None: ...
    def command(self, device_id: str, body: dict[str, Any]) -> Any: ...
    def audio(self, device_id: str, command_id: str, content_type: str, body: bytes) -> Any: ...
    def speech(self, device_id: str, speech_id: str) -> Any: ...
    def work(self) -> Any: ...
    def mailbox(self) -> Any: ...


class StoreUnavailable(RuntimeError):
    """Raised when the device SQLite file is locked, missing, or damaged."""


class RateLimited(RuntimeError):
    """Raised when the global pairing failure limit is active."""


class CommandError(RuntimeError):
    """Raised by a session command handler to return a specific 4xx JSON error."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class _HttpError(Exception):
    def __init__(self, status: int, message: str, headers: tuple[tuple[str, str], ...] = ()) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = headers


@dataclass(frozen=True)
class _Request:
    method: str
    path: str
    query: str
    host: str
    headers: dict[str, list[str]]
    content_length: int | None
    extra: bytearray
    start: float
    lan: bool = False  # It came over the home LAN, in plain HTTP, to the address it names in Host.


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_code(code: str) -> str:
    return "".join(code.split()).upper()


class DeviceStore:
    """Stores paired device hashes and one-use pairing codes in one SQLite file.

    Every method is synchronous and runs in a worker thread when called by the server.
    A locked, missing, or unreadable database raises StoreUnavailable.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        busy_seconds: float = STORE_BUSY_SECONDS,
        pair_rate_max: int = PAIR_RATE_MAX,
        pair_rate_window: float = PAIR_RATE_WINDOW,
    ) -> None:
        self.path = Path(path)
        self.busy_seconds = busy_seconds
        self.pair_rate_max = pair_rate_max
        self.pair_rate_window = pair_rate_window
        self._lock = threading.Lock()
        self._failures: deque[float] = deque()

    def _connect(self, *, create: bool = False) -> sqlite3.Connection:
        if not create and not self.path.exists():
            raise StoreUnavailable("The device store file is missing.")
        try:
            if create:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.path),
                timeout=self.busy_seconds,
                isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute(f"PRAGMA busy_timeout = {int(self.busy_seconds * 1000)}")
            return conn
        except (sqlite3.Error, OSError) as exc:
            raise StoreUnavailable("The device store is unavailable.") from exc

    def open(self) -> DeviceStore:
        """Create the database tables when missing and enable WAL mode."""
        with self._lock:
            conn = self._connect(create=True)
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("BEGIN IMMEDIATE")
                for statement in STORE_TABLES:
                    conn.execute(statement)
                conn.execute("COMMIT")
            except (sqlite3.Error, OSError) as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise StoreUnavailable("The device store could not open.") from exc
            finally:
                conn.close()
        return self

    def create_code(self, *, ttl: float = PAIR_CODE_TTL, code: str | None = None) -> str:
        """Create one short pairing code and store only its hash."""
        raw = code if code is not None else "".join(secrets.choice(PAIR_ALPHABET) for _ in range(PAIR_CODE_LENGTH))
        normalized = _normalize_code(raw)
        if not normalized:
            raise ValueError("The pairing code must not be empty.")
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM pairing_codes WHERE expires_at <= ? OR used_at IS NOT NULL", (now,))
                conn.execute(
                    "INSERT OR REPLACE INTO pairing_codes (code_hash, created_at, expires_at, used_at) "
                    "VALUES (?, ?, ?, NULL)",
                    (_sha256(normalized), now, now + ttl),
                )
                conn.execute("COMMIT")
            except (sqlite3.Error, OSError) as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise StoreUnavailable("The device store could not save a pairing code.") from exc
            finally:
                conn.close()
        return raw

    def _check_rate_locked(self, now_mono: float) -> None:
        cutoff = now_mono - self.pair_rate_window
        while self._failures and self._failures[0] <= cutoff:
            self._failures.popleft()
        if len(self._failures) >= self.pair_rate_max:
            raise RateLimited("Too many wrong pairing codes. Wait a minute and try again.")

    def redeem_code(self, code: str, name: str) -> tuple[Device, str] | None:
        """Consume a pairing code atomically and return the new device and raw token."""
        normalized = _normalize_code(code)
        code_hash = _sha256(normalized)
        now = time.time()
        now_mono = time.monotonic()
        with self._lock:
            self._check_rate_locked(now_mono)
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "UPDATE pairing_codes SET used_at = ? "
                    "WHERE code_hash = ? AND used_at IS NULL AND expires_at > ?",
                    (now, code_hash, now),
                )
                if cur.rowcount != 1:
                    conn.execute("ROLLBACK")
                    self._failures.append(now_mono)
                    return None
                device_id = f"dev-{secrets.token_hex(6)}"
                token = secrets.token_urlsafe(32)
                conn.execute(
                    "INSERT INTO devices (id, name, token_hash, created_at, last_seen, revoked_at) "
                    "VALUES (?, ?, ?, ?, ?, NULL)",
                    (device_id, name, _sha256(token), now, now),
                )
                conn.execute("COMMIT")
                return Device(id=device_id, name=name, created_at=now, last_seen=now), token
            except (sqlite3.Error, OSError) as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise StoreUnavailable("The device store is busy. Try again.") from exc
            finally:
                conn.close()

    def authenticate(self, token: str) -> Device | None:
        """Look up an active device by token hash and update its last_seen time."""
        if not TOKEN_VALUE_RE.fullmatch(token):
            return None
        token_hash = _sha256(token)
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT id, name, created_at, last_seen FROM devices "
                    "WHERE token_hash = ? AND revoked_at IS NULL",
                    (token_hash,),
                ).fetchone()
                if row is None:
                    return None
                last_seen = row["last_seen"]
                if now - last_seen >= LAST_SEEN_STEP:
                    conn.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (now, row["id"]))
                    last_seen = now
                return Device(id=row["id"], name=row["name"], created_at=row["created_at"], last_seen=last_seen)
            except (sqlite3.Error, OSError) as exc:
                raise StoreUnavailable("The device store is busy. Try again.") from exc
            finally:
                conn.close()

    def list_devices(self) -> list[Device]:
        """Return every active device, oldest first."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT id, name, created_at, last_seen FROM devices "
                    "WHERE revoked_at IS NULL ORDER BY created_at"
                ).fetchall()
                return [
                    Device(id=r["id"], name=r["name"], created_at=r["created_at"], last_seen=r["last_seen"])
                    for r in rows
                ]
            except (sqlite3.Error, OSError) as exc:
                raise StoreUnavailable("The device store is unavailable.") from exc
            finally:
                conn.close()

    def revoke(self, device_id: str) -> bool:
        """Mark a device revoked so future requests fail with 401."""
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "UPDATE devices SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                    (now, device_id),
                )
                conn.execute("COMMIT")
                return cur.rowcount == 1
            except (sqlite3.Error, OSError) as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise StoreUnavailable("The device store is unavailable.") from exc
            finally:
                conn.close()


_REPLAY_DONE = object()


class _Stream:
    """One open event stream with a bounded queue and fast non-blocking push."""

    __slots__ = (
        "device_id",
        "queue",
        "maxsize",
        "wakeup",
        "overflowed",
        "closed",
        "writer",
        "loop",
        "loop_thread_id",
        "task",
    )

    def __init__(
        self,
        device_id: str,
        maxsize: int,
        writer: asyncio.StreamWriter,
        loop: asyncio.AbstractEventLoop,
        loop_thread_id: int,
    ) -> None:
        self.device_id = device_id
        self.queue: deque[Any] = deque()
        self.maxsize = maxsize
        self.wakeup = asyncio.Event()
        self.overflowed = False
        self.closed = False
        self.writer = writer
        self.loop = loop
        self.loop_thread_id = loop_thread_id
        self.task: asyncio.Task[None] | None = None

    def push(self, event: Event) -> None:
        """Accept an event from the session and return at once."""
        if self.closed or self.overflowed:
            return
        if threading.get_ident() == self.loop_thread_id:
            self._enqueue(event)
        else:
            try:
                self.loop.call_soon_threadsafe(self._enqueue, event)
            except RuntimeError:
                pass

    def _enqueue(self, event: Event) -> None:
        if self.closed or self.overflowed:
            return
        if len(self.queue) >= self.maxsize:
            self.overflowed = True
            self.queue.clear()
            self.wakeup.set()
            self._abort()
            return
        self.queue.append(event)
        self.wakeup.set()

    def mark_replay_done(self) -> None:
        """Place a boundary between events buffered during replay and live events."""
        if not self.closed and not self.overflowed:
            self.queue.append(_REPLAY_DONE)
            self.wakeup.set()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.queue.clear()
        self.wakeup.set()
        self._abort()

    def _abort(self) -> None:
        transport = self.writer.transport
        if transport is not None and not transport.is_closing():
            transport.close()
        if self.task is not None and not self.task.done():
            self.task.cancel()


def _format_sse(event: Event) -> bytes:
    if "\r" in event.kind or "\n" in event.kind or not event.kind:
        raise ValueError("Invalid event kind.")
    payload = json.dumps(event.data, separators=(",", ":"))
    if event.seq is not None:
        return f"id: {event.seq}\nevent: {event.kind}\ndata: {payload}\n\n".encode("utf-8")
    return f"event: {event.kind}\ndata: {payload}\n\n".encode("utf-8")


async def _call_session(func: Callable[..., Any], *args: Any) -> Any:
    result = func(*args)
    if inspect.isawaitable(result):
        return await result
    return result


class Server:
    """Asyncio HTTP/1.1 server for Rook's phone app, bound to 127.0.0.1, and to a LAN address only when given one."""

    def __init__(
        self,
        session: Session,
        store: DeviceStore,
        *,
        port: int = 0,
        allowed_hosts: Iterable[str] = (),
        static_dir: str | Path = DEFAULT_STATIC_DIR,
        secure_cookies: bool = True,
        max_request_line: int = MAX_REQUEST_LINE,
        max_header_bytes: int = MAX_HEADER_BYTES,
        max_header_count: int = MAX_HEADER_COUNT,
        max_body_bytes: int = MAX_BODY_BYTES,
        max_audio_bytes: int = MAX_AUDIO_BYTES,
        max_audio_in_flight: int = MAX_AUDIO_IN_FLIGHT,
        max_speech_bytes: int = MAX_SPEECH_BYTES,
        header_timeout: float = HEADER_TIMEOUT,
        body_timeout: float = BODY_TIMEOUT,
        total_read_timeout: float = TOTAL_READ_TIMEOUT,
        audio_read_timeout: float = AUDIO_READ_TIMEOUT,
        write_timeout: float = WRITE_TIMEOUT,
        keepalive_seconds: float = KEEPALIVE_SECONDS,
        stream_queue_size: int = STREAM_QUEUE_SIZE,
        max_connections: int = MAX_CONNECTIONS,
        max_streams: int = MAX_STREAMS,
        max_device_streams: int = MAX_DEVICE_STREAMS,
        on_unknown_host: Callable[[str], None] | None = None,
        on_paired: Callable[[], None] | None = None,
        pair_on_loopback: bool = False,
        local_token: str | None = None,
        themes_dir: str | Path = DEFAULT_THEMES_DIR,
        lan: str | None = None,
        lan_port: int | None = None,
    ) -> None:
        self.session = session
        self.store = store
        self.on_unknown_host = on_unknown_host  # Told of a refused Host, such as a tailnet name that came up late.
        self.on_paired = on_paired  # Told when a device pairs, so the overlay can drop the pairing code.
        # A desktop browser on 127.0.0.1 is never paired by accident: only a check pairs on a loopback name.
        self.pair_on_loopback = pair_on_loopback
        # Optional per-process loopback token for read-only desktop presence helpers (/snapshot and /events only).
        self.local_token = local_token
        self.themes_dir = Path(themes_dir)
        # A device with no tailnet, such as a Steam Deck at home, reaches Rook over the LAN in plain HTTP: the server
        # then listens on this IPv4 address too, or on every address with 0.0.0.0, on lan_port or else the loopback
        # port. A LAN connection is accepted only with the Host of the address and port it came to, and its http Origin.
        self.lan, self.lan_port = lan, lan_port
        self._lan_server: asyncio.Server | None = None
        self.requested_port = port
        self.port = port
        self.static_dir = Path(static_dir)
        self.secure_cookies = secure_cookies
        self.max_request_line = max_request_line
        self.max_header_bytes = max_header_bytes
        self.max_header_count = max_header_count
        self.max_body_bytes = max_body_bytes
        self.max_audio_bytes = max_audio_bytes
        self.max_audio_in_flight = max_audio_in_flight
        self.max_speech_bytes = max_speech_bytes
        self.header_timeout = header_timeout
        self.body_timeout = body_timeout
        self.total_read_timeout = total_read_timeout
        self.audio_read_timeout = audio_read_timeout
        self.write_timeout = write_timeout
        self.keepalive_seconds = keepalive_seconds
        self.stream_queue_size = stream_queue_size
        self.max_connections = max_connections
        self.max_streams = max_streams
        self.max_device_streams = max_device_streams

        self._extra_hosts = {h.strip().lower() for h in allowed_hosts if h.strip()}
        self._allowed_hosts: set[str] = set(self._extra_hosts)
        self._loopback_host = ""
        self._server: asyncio.Server | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread_id: int = 0
        self._connections: set[asyncio.Task[None]] = set()
        self._streams_by_device: dict[str, set[_Stream]] = {}
        self._stream_count = 0
        self._audio_devices: set[str] = set()
        self._audio_in_flight = 0

    async def start(self) -> Server:
        """Bind to 127.0.0.1, and the LAN address when given, and start accepting HTTP/1.1 connections."""
        self._loop = asyncio.get_running_loop()
        self._loop_thread_id = threading.get_ident()
        hosts = ["127.0.0.1"]
        if self.lan and not self.lan_port:  # On the same port, 0.0.0.0 holds loopback too: two binds would clash.
            hosts = [self.lan] if self.lan == "0.0.0.0" else [*hosts, self.lan]
        self._server = await asyncio.start_server(
            self._handle_connection,
            host=hosts,
            port=self.requested_port,
            reuse_address=True,
        )
        if self.lan and self.lan_port:
            self._lan_server = await asyncio.start_server(
                self._handle_connection, host=self.lan, port=self.lan_port, reuse_address=True)
        sockets = self._server.sockets
        if not sockets:
            raise RuntimeError("The server socket did not bind.")
        self.port = next((sock.getsockname()[1] for sock in sockets if sock.getsockname()[0] == "127.0.0.1"),
                         sockets[0].getsockname()[1])  # With the LAN on port 0, as in a check, each bind has its own.
        self._loopback_host = f"127.0.0.1:{self.port}"
        self._allowed_hosts = {self._loopback_host, *self._extra_hosts}
        return self

    def allow_hosts(self, hosts: Iterable[str]) -> None:
        """Accept these Host names too, such as the tailnet name once it is known."""
        self._extra_hosts |= {h.strip().lower() for h in hosts if h.strip()}
        self._allowed_hosts = {self._loopback_host, *self._extra_hosts}

    async def close(self) -> None:
        """Stop accepting connections and close every active stream and socket."""
        self.close_streams()
        for listening in (self._server, self._lan_server):
            if listening is not None:
                listening.close()
                await listening.wait_closed()
        self._server = self._lan_server = None
        tasks = list(self._connections)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def close_streams(self, device_id: str | None = None) -> int:
        """Close open streams for one device, or for every device when device_id is None."""
        targets: list[_Stream] = []
        if device_id is None:
            for streams in self._streams_by_device.values():
                targets.extend(streams)
        else:
            targets.extend(self._streams_by_device.get(device_id, ()))
        for stream in targets:
            stream.close()
        return len(targets)

    async def revoke_device(self, device_id: str) -> bool:
        """Revoke a device in the store and close its open streams at once."""
        revoked = await asyncio.to_thread(self.store.revoke, device_id)
        self.close_streams(device_id)
        return revoked

    def _expected_origin(self, host: str, lan: bool = False) -> str:
        if lan or host == self._loopback_host or host.startswith("127.0.0.1:"):
            return f"http://{host}"
        return f"https://{host}"

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        if len(self._connections) >= self.max_connections:
            try:
                await self._send_json(writer, 503, {"ok": False, "error": "The server has too many connections."})
            except OSError:
                pass
            finally:
                await self._close_writer(writer)
            return
        self._connections.add(task)
        try:
            # A connection that came to an address other than loopback came over the LAN, which only lan allows.
            local = writer.get_extra_info("sockname") or ()
            lan_host = f"{local[0]}:{local[1]}" if self.lan and len(local) >= 2 and local[0] != "127.0.0.1" else None
            request = await self._read_request(reader, lan_host)
            if request is None:
                return
            await self._dispatch(request, reader, writer)
        except _HttpError as err:
            await self._send_json(writer, err.status, {"ok": False, "error": err.message}, headers=err.headers)
        except StoreUnavailable:
            await self._send_json(writer, 503, {"ok": False, "error": "The device store is unavailable."})
        except (ConnectionError, BrokenPipeError, TimeoutError, asyncio.TimeoutError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._send_json(writer, 500, {"ok": False, "error": "Rook hit an unexpected error."})
        finally:
            self._connections.discard(task)
            await self._close_writer(writer)

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        if not writer.is_closing():
            writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
        except Exception:
            pass

    async def _read_request(self, reader: asyncio.StreamReader, lan_host: str | None = None) -> _Request | None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        header_deadline = start + self.header_timeout
        total_deadline = start + self.total_read_timeout
        buf = bytearray()
        head_end = -1

        while True:
            remaining = min(header_deadline, total_deadline) - loop.time()
            if remaining <= 0:
                raise _HttpError(408, "The request took too long.")
            want = min(4096, self.max_header_bytes + 1 - len(buf))
            try:
                chunk = await asyncio.wait_for(reader.read(want), timeout=remaining)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise _HttpError(408, "The request took too long.") from exc
            if not chunk:
                if not buf:
                    return None
                raise _HttpError(400, "The request ended before the headers finished.")
            buf.extend(chunk)

            crlf = buf.find(b"\r\n")
            lf = buf.find(b"\n")
            if lf != -1 and (crlf == -1 or lf < crlf):
                raise _HttpError(400, "Header lines must end with CRLF.")
            if crlf == -1:
                if len(buf) > self.max_request_line:
                    raise _HttpError(414, "The request line is too long.")
            elif crlf + 2 > self.max_request_line:
                raise _HttpError(414, "The request line is too long.")

            head_end = buf.find(b"\r\n\r\n")
            if head_end != -1:
                if head_end + 4 > self.max_header_bytes:
                    raise _HttpError(431, "The request headers are too large.")
                break
            if len(buf) > self.max_header_bytes:
                raise _HttpError(431, "The request headers are too large.")

        head = bytes(buf[:head_end])
        extra = bytearray(buf[head_end + 4 :])
        lines = head.split(b"\r\n")
        for line in lines:
            if b"\r" in line or b"\n" in line:
                raise _HttpError(400, "Header lines must end with CRLF.")

        method, path, query = self._parse_request_line(lines[0])
        headers = self._parse_headers(lines[1:])

        if "transfer-encoding" in headers:
            raise _HttpError(400, "Transfer encodings are not supported.")
        if "expect" in headers:
            raise _HttpError(417, "The Expect header is not supported.")
        if "content-encoding" in headers:
            raise _HttpError(415, "Content encodings are not supported.")

        hosts = headers.get("host", [])
        if len(hosts) != 1 or not hosts[0]:
            raise _HttpError(400, "Send exactly one Host header.")
        host = hosts[0].lower()
        if host not in ({lan_host} if lan_host else self._allowed_hosts):
            if self.on_unknown_host is not None:
                try:
                    self.on_unknown_host(host)
                except Exception:
                    pass
            raise _HttpError(403, "That Host header is not allowed.")

        cls = headers.get("content-length", [])
        if len(cls) > 1:
            raise _HttpError(400, "Send at most one Content-Length header.")
        content_length: int | None = None
        if len(cls) == 1:
            cl_str = cls[0]
            if not (cl_str and cl_str.isascii() and cl_str.isdigit()):
                raise _HttpError(400, "Content-Length must be a decimal number.")
            content_length = int(cl_str)

        if method == "POST":
            if content_length is None:
                raise _HttpError(411, "A POST request needs a Content-Length header.")
            if len(extra) > content_length:
                raise _HttpError(400, "The request sent more bytes than Content-Length.")
        else:
            if (content_length is not None and content_length > 0) or extra:
                raise _HttpError(400, "This request may not carry a body.")

        return _Request(
            method=method,
            path=path,
            query=query,
            host=host,
            headers=headers,
            content_length=content_length,
            extra=extra,
            start=start,
            lan=bool(lan_host),
        )

    def _parse_request_line(self, raw: bytes) -> tuple[str, str, str]:
        parts = raw.split(b" ")
        if len(parts) != 3 or not all(parts):
            raise _HttpError(400, "The request line is malformed.")
        method_b, target_b, version_b = parts
        if not all(65 <= b <= 90 for b in method_b):
            raise _HttpError(400, "The request method is invalid.")
        if version_b != b"HTTP/1.1":
            if HTTP_VERSION_RE.fullmatch(version_b):
                raise _HttpError(505, "Only HTTP/1.1 is supported.")
            raise _HttpError(400, "The HTTP version is invalid.")
        if not target_b.startswith(b"/") or not all(0x21 <= b <= 0x7E for b in target_b):
            raise _HttpError(400, "The request target is invalid.")
        target = target_b.decode("ascii")
        if "#" in target or "\\" in target:
            raise _HttpError(400, "The request path is invalid.")
        path, _, query = target.partition("?")
        if ".." in path or "//" in path or "%" in path:
            raise _HttpError(400, "The request path is invalid.")
        return method_b.decode("ascii"), path, query

    def _parse_headers(self, lines: list[bytes]) -> dict[str, list[str]]:
        if len(lines) > self.max_header_count:
            raise _HttpError(431, "The request has too many headers.")
        headers: dict[str, list[str]] = {}
        for line in lines:
            if not line or line[0] in (0x20, 0x09) or b":" not in line:
                raise _HttpError(400, "A header line is malformed.")
            name_b, value_b = line.split(b":", 1)
            if not HEADER_NAME_RE.fullmatch(name_b):
                raise _HttpError(400, "A header name is invalid.")
            if not all(b == 0x09 or 0x20 <= b <= 0x7E for b in value_b):
                raise _HttpError(400, "A header value is invalid.")
            name = name_b.decode("ascii").lower()
            value = value_b.decode("ascii").strip(" \t")
            headers.setdefault(name, []).append(value)
        return headers

    async def _read_body(
        self,
        reader: asyncio.StreamReader,
        buf: bytearray,
        length: int,
        deadline: float,
    ) -> bytes:
        loop = asyncio.get_running_loop()
        while len(buf) < length:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise _HttpError(408, "The request body took too long.")
            want = min(65536, length - len(buf))
            try:
                chunk = await asyncio.wait_for(reader.read(want), timeout=remaining)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise _HttpError(408, "The request body took too long.") from exc
            if not chunk:
                raise _HttpError(400, "The request body ended early.")
            buf.extend(chunk)
        return bytes(buf)

    def _extract_cookie(self, request: _Request) -> str | None:
        raw_headers = request.headers.get("cookie")
        if not raw_headers:
            return None
        joined = "; ".join(raw_headers)
        for part in joined.split(";"):
            name, sep, value = part.strip().partition("=")
            if sep and name == COOKIE_NAME:
                return value.strip()
        return None

    def _check_origin(self, request: _Request) -> None:
        origins = request.headers.get("origin", [])
        expected = self._expected_origin(request.host, request.lan)
        if len(origins) != 1 or origins[0] != expected:
            raise _HttpError(403, "This request came from another site.")

    async def _parse_json_post(self, request: _Request, reader: asyncio.StreamReader) -> dict[str, Any]:
        self._check_origin(request)

        ctypes = request.headers.get("content-type", [])
        if len(ctypes) != 1:
            raise _HttpError(415, "Send a JSON request body.")
        media, _, params = ctypes[0].partition(";")
        if media.strip().lower() != "application/json":
            raise _HttpError(415, "Send a JSON request body.")
        if params.strip():
            for param in params.split(";"):
                key, sep, val = param.strip().partition("=")
                if not sep or key.strip().lower() != "charset" or val.strip().strip('"').lower() != "utf-8":
                    raise _HttpError(415, "Send UTF-8 JSON.")

        assert request.content_length is not None
        if request.content_length > self.max_body_bytes:
            raise _HttpError(413, "The request body is too large.")
        loop = asyncio.get_running_loop()
        deadline = min(request.start + self.total_read_timeout, loop.time() + self.body_timeout)
        body = await self._read_body(reader, request.extra, request.content_length, deadline)

        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise _HttpError(400, "The request body is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise _HttpError(400, "The request body must be a JSON object.")
        return data

    def _parse_audio_content_type(self, request: _Request) -> str:
        ctypes = request.headers.get("content-type", [])
        if len(ctypes) != 1:
            raise _HttpError(415, "Send an allowed audio type.")
        media, _, params = ctypes[0].partition(";")
        media = media.strip().lower()
        if media not in AUDIO_UPLOAD_TYPES:
            raise _HttpError(415, "That audio type is not supported.")
        if not params.strip():
            return media
        parts = [part.strip() for part in params.split(";") if part.strip()]
        if len(parts) != 1:
            raise _HttpError(415, "That audio Content-Type has unsupported parameters.")
        key, sep, val = parts[0].partition("=")
        codecs = val.strip().strip('"')
        if not sep or key.strip().lower() != "codecs" or not CODECS_VALUE_RE.fullmatch(codecs):
            raise _HttpError(415, "That audio Content-Type has an invalid codecs parameter.")
        return f"{media};codecs={codecs}"

    def _parse_range(self, request: _Request, total: int) -> tuple[int, int] | None:
        ranges = request.headers.get("range", [])
        if not ranges:
            return None
        hdr = (("Content-Range", f"bytes */{total}"),)
        if len(ranges) != 1:
            raise _HttpError(416, "That byte range is not valid.", headers=hdr)
        raw = ranges[0].strip()
        if not raw.lower().startswith("bytes="):
            raise _HttpError(416, "That byte range is not valid.", headers=hdr)
        spec = raw[6:].strip()
        if "," in spec or "-" not in spec or total <= 0:
            raise _HttpError(416, "That byte range is not valid.", headers=hdr)
        start_s, end_s = spec.split("-", 1)
        start_s, end_s = start_s.strip(), end_s.strip()
        if not start_s and not end_s:
            raise _HttpError(416, "That byte range is not valid.", headers=hdr)
        if not start_s:
            if not (end_s.isascii() and end_s.isdigit()):
                raise _HttpError(416, "That byte range is not valid.", headers=hdr)
            suffix = int(end_s)
            if suffix <= 0:
                raise _HttpError(416, "That byte range is not valid.", headers=hdr)
            return max(0, total - suffix), total - 1
        if not (start_s.isascii() and start_s.isdigit()):
            raise _HttpError(416, "That byte range is not valid.", headers=hdr)
        start = int(start_s)
        if start >= total:
            raise _HttpError(416, "That byte range is not valid.", headers=hdr)
        if not end_s:
            return start, total - 1
        if not (end_s.isascii() and end_s.isdigit()):
            raise _HttpError(416, "That byte range is not valid.", headers=hdr)
        end = int(end_s)
        if end < start:
            raise _HttpError(416, "That byte range is not valid.", headers=hdr)
        return start, min(end, total - 1)

    async def _dispatch(
        self,
        request: _Request,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if request.method == "GET" and (
                request.path in STATIC_FILES or (self.local_token and request.path in PRESENCE_FILES)):
            extra_headers: tuple[tuple[str, str], ...] = ()
            if request.path == "/presence" and self.local_token and request.host == self._loopback_host:
                hdr_vals = request.headers.get("x-rook-presence-token", [])
                if len(hdr_vals) == 1 and secrets.compare_digest(hdr_vals[0].strip(), self.local_token):
                    cookie = f"{COOKIE_NAME}={self.local_token}; Path=/; HttpOnly; SameSite=Strict"
                    extra_headers = (("Set-Cookie", cookie),)
            await self._handle_static(request.path, writer, extra_headers=extra_headers)
            return
        if self.local_token and request.method == "GET" and request.path.startswith("/themes/"):
            await self._handle_theme_static(request.path, writer)
            return
        if request.method == "POST" and request.path == "/pair":
            await self._handle_pair(request, reader, writer)
            return

        token = self._extract_cookie(request)
        local_presence = bool(
            token and self.local_token and request.host == self._loopback_host
            and secrets.compare_digest(token, self.local_token)
        )
        if local_presence:
            if request.path not in ("/snapshot", "/events"):
                raise _HttpError(403, "Local presence may only read state and events.")
            device = Device(id="local-presence", name="Local Presence", created_at=0.0, last_seen=0.0)
        else:
            device = await asyncio.to_thread(self.store.authenticate, token) if token else None
            if device is None:
                raise _HttpError(401, "This device is not paired.")

        if request.path.startswith("/speech/"):
            if request.method != "GET":
                raise _HttpError(405, "That method is not allowed here.", headers=(("Allow", "GET"),))
            speech_id = request.path[len("/speech/") :]
            await self._handle_speech(request, device, speech_id, writer)
            return

        expected_method = ROUTE_METHODS.get(request.path)
        if expected_method is None:
            raise _HttpError(404, "There is nothing at that address.")
        if request.method != expected_method:
            raise _HttpError(405, "That method is not allowed here.", headers=(("Allow", expected_method),))

        if request.path == "/snapshot":
            await self._handle_snapshot(device, writer)
        elif request.path == "/work":
            await self._handle_work(writer)
        elif request.path == "/mailbox":
            await self._handle_mailbox(writer)
        elif request.path == "/command":
            await self._handle_command(request, device, reader, writer)
        elif request.path == "/audio":
            await self._handle_audio(request, device, reader, writer)
        elif request.path == "/events":
            await self._handle_events(request, device, reader, writer)

    async def _handle_static(
        self,
        route: str,
        writer: asyncio.StreamWriter,
        *,
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        filename, content_type = STATIC_FILES.get(route) or PRESENCE_FILES[route]
        file_path = (STAGE_DIR if route in STAGE_FILES else self.static_dir) / filename
        try:
            body = await asyncio.to_thread(file_path.read_bytes)
        except OSError as exc:
            raise _HttpError(503, "That app file is missing.") from exc
        await self._send_bytes(writer, 200, body, content_type, headers=extra_headers)

    async def _handle_theme_static(self, route: str, writer: asyncio.StreamWriter) -> None:
        match = THEME_FILE_RE.fullmatch(route)
        if not match:
            raise _HttpError(404, "There is nothing at that address.")
        pack, sub, name = match.groups()
        if ".." in name or name.startswith("."):
            raise _HttpError(404, "There is nothing at that address.")
        ext = Path(name).suffix.lower()
        content_type = THEME_MIME.get(ext)
        if not content_type:
            raise _HttpError(404, "There is nothing at that address.")
        root = self.themes_dir.resolve()
        candidate = (root / pack / sub / name if sub else root / pack / name).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise _HttpError(404, "There is nothing at that address.") from exc
        if not candidate.is_file():
            raise _HttpError(404, "There is nothing at that address.")
        try:
            body = await asyncio.to_thread(candidate.read_bytes)
        except OSError as exc:
            raise _HttpError(503, "That theme file is missing.") from exc
        await self._send_bytes(writer, 200, body, content_type)

    async def _handle_pair(
        self,
        request: _Request,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        data = await self._parse_json_post(request, reader)
        if not self.pair_on_loopback and request.host == self._loopback_host:
            raise _HttpError(403, "Pair from the phone, at Rook's tailnet address.")
        code = data.get("code")
        name = data.get("name")
        if not isinstance(code, str) or not code.strip() or len(code) > 64:
            raise _HttpError(400, "Enter the pairing code from Rook.")
        if not isinstance(name, str):
            raise _HttpError(400, "Give this device a name.")
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 40 or any(ord(ch) < 32 for ch in clean_name):
            raise _HttpError(400, "Give this device a valid name.")

        try:
            paired = await asyncio.to_thread(self.store.redeem_code, code, clean_name)
        except RateLimited as err:
            raise _HttpError(429, str(err)) from err

        if paired is None:
            raise _HttpError(400, "That code is wrong or has expired. Ask Rook for a new one.")

        device, token = paired
        if self.on_paired is not None:
            try:
                self.on_paired()
            except Exception:
                pass
        cookie = f"{COOKIE_NAME}={token}; Path=/; Max-Age={COOKIE_MAX_AGE}; HttpOnly; SameSite=Strict"
        if self.secure_cookies and not request.lan:  # A browser drops a Secure cookie that plain HTTP sets.
            cookie += "; Secure"
        await self._send_json(
            writer,
            200,
            {"ok": True, "device": {"id": device.id, "name": device.name}},
            headers=(("Set-Cookie", cookie),),
        )

    async def _handle_snapshot(self, device: Device, writer: asyncio.StreamWriter) -> None:
        try:
            data = await _call_session(self.session.snapshot, device.id)
        except Exception:
            await self._send_json(writer, 503, {"ok": False, "error": "Rook could not build the snapshot."})
            return
        await self._send_json(writer, 200, data)

    async def _handle_work(self, writer: asyncio.StreamWriter) -> None:
        try:
            data = await _call_session(self.session.work)
        except Exception:
            await self._send_json(writer, 503, {"ok": False, "error": "Rook could not read the work list."})
            return
        await self._send_json(writer, 200, data)

    async def _handle_mailbox(self, writer: asyncio.StreamWriter) -> None:
        try:
            data = await _call_session(self.session.mailbox)
        except Exception:
            await self._send_json(writer, 503, {"ok": False, "error": "Rook could not read the mailbox."})
            return
        await self._send_json(writer, 200, data)

    async def _handle_command(
        self,
        request: _Request,
        device: Device,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        data = await self._parse_json_post(request, reader)
        cmd_id = data.get("id")
        kind = data.get("kind")
        if not isinstance(cmd_id, str) or not COMMAND_ID_RE.fullmatch(cmd_id):
            raise _HttpError(400, "A command needs a valid id.")
        if not isinstance(kind, str) or not kind.strip() or len(kind) > 32:
            raise _HttpError(400, "A command needs a kind.")

        try:
            result = await _call_session(self.session.command, device.id, data)
        except CommandError as err:
            await self._send_json(writer, err.status, {"ok": False, "error": err.message})
            return
        except Exception:
            await self._send_json(writer, 500, {"ok": False, "error": "Rook could not handle that command."})
            return

        if not isinstance(result, dict):
            await self._send_json(writer, 500, {"ok": False, "error": "Rook returned an invalid command answer."})
            return
        status = 200
        if result.get("ok") is False:
            status = 409 if result.get("error") == "stale" else 400
        await self._send_json(writer, status, result)

    async def _handle_audio(
        self,
        request: _Request,
        device: Device,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._check_origin(request)
        content_type = self._parse_audio_content_type(request)
        cmd_headers = request.headers.get("x-rook-command", [])
        if len(cmd_headers) != 1 or not COMMAND_ID_RE.fullmatch(cmd_headers[0]):
            raise _HttpError(400, "An audio upload needs a valid X-Rook-Command header.")
        command_id = cmd_headers[0]

        assert request.content_length is not None
        if request.content_length <= 0:
            raise _HttpError(400, "The audio recording is empty.")
        if request.content_length > self.max_audio_bytes:
            raise _HttpError(413, "The audio recording is too large.")
        if device.id in self._audio_devices:
            raise _HttpError(429, "This device already has an audio upload running.")
        if self._audio_in_flight + request.content_length > self.max_audio_in_flight:
            raise _HttpError(503, "Too many audio uploads are in flight.")

        audio_fn = getattr(self.session, "audio", None)
        if audio_fn is None:
            raise _HttpError(503, "Voice input is not enabled.")

        self._audio_devices.add(device.id)
        self._audio_in_flight += request.content_length
        try:
            deadline = request.start + self.audio_read_timeout
            body = await self._read_body(reader, request.extra, request.content_length, deadline)
            try:
                result = await _call_session(audio_fn, device.id, command_id, content_type, body)
            except CommandError as err:
                await self._send_json(writer, err.status, {"ok": False, "error": err.message})
                return
            except Exception:
                await self._send_json(writer, 500, {"ok": False, "error": "Rook could not handle that recording."})
                return
        finally:
            self._audio_devices.discard(device.id)
            self._audio_in_flight -= request.content_length

        if not isinstance(result, dict):
            await self._send_json(writer, 500, {"ok": False, "error": "Rook returned an invalid audio answer."})
            return
        status = 200
        if result.get("ok") is False:
            status = 409 if result.get("error") == "stale" else 400
        await self._send_json(writer, status, result)

    async def _handle_speech(
        self,
        request: _Request,
        device: Device,
        speech_id: str,
        writer: asyncio.StreamWriter,
    ) -> None:
        if not SPEECH_ID_RE.fullmatch(speech_id):
            raise _HttpError(400, "The speech id is invalid.")
        speech_fn = getattr(self.session, "speech", None)
        if speech_fn is None:
            raise _HttpError(404, "That audio clip is gone.")

        try:
            found = await _call_session(speech_fn, device.id, speech_id)
        except Exception:
            await self._send_json(writer, 503, {"ok": False, "error": "Rook could not read that audio clip."})
            return

        if found is None:
            raise _HttpError(404, "That audio clip is gone.")
        if not isinstance(found, tuple) or len(found) != 2:
            await self._send_json(writer, 500, {"ok": False, "error": "Rook returned an invalid audio clip."})
            return
        raw_type, data = found
        if not isinstance(raw_type, str) or not isinstance(data, bytes):
            await self._send_json(writer, 500, {"ok": False, "error": "Rook returned an invalid audio clip."})
            return
        content_type = raw_type.strip().lower()
        if content_type not in SPEECH_CONTENT_TYPES:
            await self._send_json(writer, 500, {"ok": False, "error": "Rook returned an unsupported audio type."})
            return
        if len(data) > self.max_speech_bytes:
            await self._send_json(writer, 500, {"ok": False, "error": "That audio clip is too large."})
            return

        byte_range = self._parse_range(request, len(data))
        if byte_range is not None:
            start, end = byte_range
            chunk = data[start : end + 1]
            headers = (("Accept-Ranges", "bytes"), ("Content-Range", f"bytes {start}-{end}/{len(data)}"))
            await self._send_bytes(writer, 206, chunk, content_type, headers=headers)
            return
        await self._send_bytes(writer, 200, data, content_type, headers=(("Accept-Ranges", "bytes"),))

    def _parse_cursor(self, request: _Request) -> int:
        header_ids = request.headers.get("last-event-id", [])
        if len(header_ids) > 1:
            raise _HttpError(400, "Send at most one Last-Event-ID header.")
        raw = header_ids[0].strip() if header_ids and header_ids[0].strip() else ""
        if not raw and request.query:
            params = parse_qs(request.query, keep_blank_values=True)
            after_vals = params.get("after")
            if after_vals:
                if len(after_vals) > 1:
                    raise _HttpError(400, "Send at most one after parameter.")
                raw = after_vals[0].strip()
        if not raw:
            return 0
        if not (raw.isascii() and raw.isdigit()):
            raise _HttpError(400, "The event cursor must be a number.")
        return int(raw)

    async def _handle_events(
        self,
        request: _Request,
        device: Device,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        cursor = self._parse_cursor(request)
        if self._stream_count >= self.max_streams:
            raise _HttpError(503, "The server has too many open streams.")
        device_streams = self._streams_by_device.get(device.id)
        if device_streams is not None and len(device_streams) >= self.max_device_streams:
            raise _HttpError(429, "This device has too many open streams.")

        assert self._loop is not None
        stream = _Stream(device.id, self.stream_queue_size, writer, self._loop, self._loop_thread_id)
        stream.task = asyncio.current_task()
        self._streams_by_device.setdefault(device.id, set()).add(stream)
        self._stream_count += 1
        subscribed = False
        eof_task: asyncio.Task[None] | None = None

        try:
            # Reconnect step 1: register the subscription before reading high water.
            try:
                self.session.subscribe(stream.push)
                subscribed = True
            except Exception:
                await self._send_json(writer, 503, {"ok": False, "error": "Rook is not answering."})
                return

            # Reconnect step 2: read the highest committed sequence number H.
            try:
                high_water = int(await _call_session(self.session.high_water))
            except Exception:
                await self._send_json(writer, 503, {"ok": False, "error": "Rook is not answering."})
                return

            # Reconnect step 3: replay stored events after cursor up to H.
            try:
                replay = await _call_session(self.session.events_after, cursor, high_water)
            except Exception:
                await self._send_json(writer, 503, {"ok": False, "error": "Rook is not answering."})
                return

            stream.mark_replay_done()
            if stream.closed or stream.overflowed:
                return

            transport = writer.transport
            if transport is not None:
                transport.set_write_buffer_limits(high=16384, low=4096)
                sock = transport.get_extra_info("socket")
                if sock is not None:
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32768)
                    except OSError:
                        pass

            await self._write_sse_headers(writer)
            if replay is None:
                await self._write_chunk(writer, b"retry: 1000\nevent: snapshot\ndata: {}\n\n")
                return

            eof_task = asyncio.create_task(self._watch_eof(reader, stream))
            await self._write_chunk(writer, b"retry: 1000\n: hello\n\n")

            for event in replay:
                if stream.closed or stream.overflowed:
                    return
                await self._write_chunk(writer, _format_sse(event))

            # Reconnect step 4: pass on buffered events above H, then live events.
            filtering = True
            while not stream.closed and not stream.overflowed:
                if stream.queue:
                    item = stream.queue.popleft()
                    if item is _REPLAY_DONE:
                        filtering = False
                        continue
                    if filtering and item.seq is not None and item.seq <= high_water:
                        continue
                    if item.kind == "speech":
                        target_device = item.data.get("device")
                        if target_device and target_device != stream.device_id:
                            continue
                    await self._write_chunk(writer, _format_sse(item))
                    continue

                stream.wakeup.clear()
                if stream.queue or stream.closed or stream.overflowed:
                    continue
                try:
                    await asyncio.wait_for(stream.wakeup.wait(), timeout=self.keepalive_seconds)
                except (TimeoutError, asyncio.TimeoutError):
                    if stream.closed or stream.overflowed:
                        return
                    await self._write_chunk(writer, b": keepalive\n\n")
        except asyncio.CancelledError:
            if not (stream.closed or stream.overflowed):
                raise
        except (ConnectionError, BrokenPipeError, TimeoutError, asyncio.TimeoutError, OSError):
            return
        finally:
            stream.closed = True
            if eof_task is not None:
                eof_task.cancel()
                try:
                    await eof_task
                except (asyncio.CancelledError, Exception):
                    pass
            if subscribed:
                try:
                    self.session.unsubscribe(stream.push)
                except Exception:
                    pass
            bucket = self._streams_by_device.get(device.id)
            if bucket is not None:
                bucket.discard(stream)
                if not bucket:
                    del self._streams_by_device[device.id]
            self._stream_count -= 1

    async def _watch_eof(self, reader: asyncio.StreamReader, stream: _Stream) -> None:
        try:
            while not stream.closed:
                data = await reader.read(1)
                if not data:
                    stream.close()
                    return
        except (OSError, asyncio.CancelledError):
            return

    def _base_headers(self, content_type: str, extra: Iterable[tuple[str, str]] = ()) -> list[tuple[str, str]]:
        headers = [
            ("Content-Type", content_type),
            ("Cache-Control", "no-store"),
            ("Content-Security-Policy", CSP),
            ("Permissions-Policy", PERMISSIONS_POLICY),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("Connection", "close"),
        ]
        headers.extend(extra)
        return headers

    async def _write_chunk(self, writer: asyncio.StreamWriter, data: bytes) -> None:
        writer.write(data)
        await asyncio.wait_for(writer.drain(), timeout=self.write_timeout)

    async def _write_sse_headers(self, writer: asyncio.StreamWriter) -> None:
        headers = self._base_headers("text/event-stream", (("X-Accel-Buffering", "no"),))
        head = "HTTP/1.1 200 OK\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers) + "\r\n"
        await self._write_chunk(writer, head.encode("ascii"))

    async def _send_bytes(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: bytes,
        content_type: str,
        headers: Iterable[tuple[str, str]] = (),
    ) -> None:
        phrase = STATUS_PHRASES.get(status, "Error")
        all_headers = self._base_headers(content_type, (("Content-Length", str(len(body))), *headers))
        head = (f"HTTP/1.1 {status} {phrase}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in all_headers) + "\r\n").encode(
            "ascii"
        )
        if len(body) <= 65536:
            await self._write_chunk(writer, head + body)
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.write_timeout
        writer.write(head)
        for offset in range(0, len(body), 65536):
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("Response write timed out.")
            writer.write(body[offset : offset + 65536])
            await asyncio.wait_for(writer.drain(), timeout=remaining)

    async def _send_json(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        payload: Any,
        headers: Iterable[tuple[str, str]] = (),
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        await self._send_bytes(writer, status, body, "application/json", headers=headers)


# Hermetic self-check and timing check.


class _FakeSession:
    """In-memory session for desktop/server.py --check."""

    def __init__(self) -> None:
        self.seq = 10
        self.oldest_retained = 1
        self.events: list[Event] = []
        self.subscribers: list[Callable[[Event], None]] = []
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self.audios: list[tuple[str, str, str, bytes]] = []
        self.speech_calls: list[tuple[str, str]] = []
        self.clips: dict[str, tuple[str, bytes]] = {"clip-1": ("audio/ogg", b"0123456789")}
        self.on_high_water: Callable[[], None] | None = None
        self.on_events_after: Callable[[], None] | None = None
        self.fail_command = False
        self.fail_audio = False
        self.fail_snapshot = False
        self.stale_card = False

    def emit(self, kind: str, data: dict[str, Any], *, live: bool = False) -> Event:
        if live:
            event = Event(kind=kind, data=data, seq=None)
        else:
            self.seq += 1
            event = Event(kind=kind, data=data, seq=self.seq)
            self.events.append(event)
        for cb in list(self.subscribers):
            cb(event)
        return event

    async def snapshot(self, device_id: str) -> dict[str, Any]:
        if self.fail_snapshot:
            raise RuntimeError("Snapshot secret traceback detail")
        return {
            "cursor": self.seq,
            "state": "resting",
            "requests": [],
            "card": None,
            "notices": [],
            "work": [],
            "mailbox": {"open": 0, "items": []},
            "dark": False,
            "focus": None,
            "restart": None,
            "seen_device": device_id,
        }

    async def high_water(self) -> int:
        if self.on_high_water is not None:
            hook = self.on_high_water
            self.on_high_water = None
            hook()
        return self.seq

    async def events_after(self, cursor: int, upto: int) -> list[Event] | None:
        if self.on_events_after is not None:
            hook = self.on_events_after
            self.on_events_after = None
            hook()
        if cursor > upto or (cursor > 0 and cursor < self.oldest_retained - 1):
            return None
        return [e for e in self.events if e.seq is not None and cursor < e.seq <= upto]

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Event], None]) -> None:
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    async def command(self, device_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.fail_command:
            raise RuntimeError("Command internal traceback detail")
        self.commands.append((device_id, body))
        if body.get("kind") == "card" and self.stale_card:
            return {"ok": False, "error": "stale"}
        return {"ok": True, "turn": "t-1", "status": "accepted"}

    async def audio(self, device_id: str, command_id: str, content_type: str, body: bytes) -> dict[str, Any]:
        if self.fail_audio:
            raise RuntimeError("Audio internal traceback detail")
        self.audios.append((device_id, command_id, content_type, body))
        return {"ok": True, "turn": "t-audio", "status": "accepted"}

    async def speech(self, device_id: str, speech_id: str) -> tuple[str, bytes] | None:
        self.speech_calls.append((device_id, speech_id))
        return self.clips.get(speech_id)

    async def work(self) -> list[dict[str, Any]]:
        return [{"id": 1, "project": "rook", "wish": "Ship server.", "state": "running", "news": None, "try": None}]

    async def mailbox(self) -> dict[str, Any]:
        return {"open": 1, "items": [{"id": "m1", "kind": "note", "summary": "Hi", "detail": "Test"}]}


async def _raw_request(port: int, payload: bytes, *, timeout: float = 3.0,
                       address: str = "127.0.0.1") -> tuple[int, dict[str, list[str]], bytes]:
    reader, writer = await asyncio.open_connection(address, port)
    try:
        writer.write(payload)
        await writer.drain()
        data = await asyncio.wait_for(reader.read(), timeout=timeout)
    finally:
        writer.close()
        await writer.wait_closed()
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode("ascii").split("\r\n")
    status = int(lines[0].split(" ", 2)[1])
    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        headers.setdefault(k.strip().lower(), []).append(v.strip())
    return status, headers, body


def _parse_cookie_value(set_cookie: str) -> str:
    return set_cookie.split(";", 1)[0].split("=", 1)[1]


async def _open_sse(
    port: int,
    cookie: str,
    path: str = "/events?after=0",
    extra_headers: str = "",
) -> tuple[int, asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Cookie: {COOKIE_NAME}={cookie}\r\n"
        f"{extra_headers}"
        "\r\n"
    ).encode("ascii")
    writer.write(req)
    await writer.drain()
    head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=3.0)
    status = int(head.split(b"\r\n", 1)[0].split(b" ", 2)[1])
    return status, reader, writer


async def _read_sse_frame(reader: asyncio.StreamReader, timeout: float = 3.0) -> str:
    raw = await asyncio.wait_for(reader.readuntil(b"\n\n"), timeout=timeout)
    return raw.decode("utf-8")


async def _run_check() -> str:
    with tempfile.TemporaryDirectory(prefix="rook-server-check-") as scratch:
        db_path = Path(scratch) / "devices.db"
        store = DeviceStore(db_path, pair_rate_max=3, pair_rate_window=60.0).open()
        session = _FakeSession()
        server = Server(
            session,
            store,
            port=0,
            allowed_hosts=("oak.tail.ts.net",),
            static_dir=DEFAULT_STATIC_DIR,
            secure_cookies=True,
            max_audio_bytes=65536,
            max_audio_in_flight=90000,
            max_speech_bytes=4096,
            header_timeout=0.3,
            body_timeout=0.3,
            total_read_timeout=0.6,
            audio_read_timeout=0.5,
            write_timeout=0.3,
            keepalive_seconds=0.15,
            stream_queue_size=16,
            max_streams=24,
            max_device_streams=2,
            pair_on_loopback=True,
        )
        await server.start()
        port = server.port
        host = f"127.0.0.1:{port}"
        origin = f"http://{host}"

        try:
            # 1. Fixed static files work before pairing and carry strict security headers.
            for route in STATIC_FILES:
                status, hdrs, body = await _raw_request(port, f"GET {route} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
                assert status == 200 and body, (route, status)
                assert hdrs["content-security-policy"] == [CSP]
                assert "media-src 'self'" in hdrs["content-security-policy"][0]
                assert hdrs["permissions-policy"] == [PERMISSIONS_POLICY]
                assert "microphone=(self)" in hdrs["permissions-policy"][0]
                assert "camera=()" in hdrs["permissions-policy"][0]
                assert hdrs["x-content-type-options"] == ["nosniff"]
                assert hdrs["referrer-policy"] == ["no-referrer"]
                assert hdrs["cache-control"] == ["no-store"]
                assert hdrs["connection"] == ["close"]
                assert not any(k.startswith("access-control-") for k in hdrs)

            # 2. Everything except fixed files and /pair is 401 before pairing.
            for raw in (
                f"GET /snapshot HTTP/1.1\r\nHost: {host}\r\n\r\n",
                f"GET /events HTTP/1.1\r\nHost: {host}\r\n\r\n",
                f"GET /work HTTP/1.1\r\nHost: {host}\r\n\r\n",
                f"GET /mailbox HTTP/1.1\r\nHost: {host}\r\n\r\n",
                f"GET /speech/clip-1 HTTP/1.1\r\nHost: {host}\r\n\r\n",
                f"GET /nope HTTP/1.1\r\nHost: {host}\r\n\r\n",
                f"DELETE /work HTTP/1.1\r\nHost: {host}\r\n\r\n",
                f"POST /command HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                'Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}',
                f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                "Content-Type: audio/webm\r\nX-Rook-Command: a1\r\nContent-Length: 4\r\n\r\nabcd",
            ):
                status, _, body = await _raw_request(port, raw.encode())
                assert status == 401 and json.loads(body)["ok"] is False, (raw, status, body)

            # 3. Raw transport rules.
            # Oversized request line -> 414.
            long_path = "/" + "a" * (MAX_REQUEST_LINE + 10)
            status, _, _ = await _raw_request(port, f"GET {long_path} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
            assert status == 414, status

            # Too many headers -> 431.
            many = "".join(f"X-H{i}: v\r\n" for i in range(MAX_HEADER_COUNT + 2))
            status, _, _ = await _raw_request(port, f"GET / HTTP/1.1\r\nHost: {host}\r\n{many}\r\n".encode())
            assert status == 431, status

            # Oversized header bytes -> 431.
            big_val = "x" * (MAX_HEADER_BYTES + 10)
            status, _, _ = await _raw_request(
                port, f"GET / HTTP/1.1\r\nHost: {host}\r\nX-Big: {big_val}\r\n\r\n".encode()
            )
            assert status == 431, status

            # Missing Host -> 400.
            status, _, _ = await _raw_request(port, b"GET / HTTP/1.1\r\n\r\n")
            assert status == 400, status

            # Doubled Host -> 400.
            status, _, _ = await _raw_request(
                port, f"GET / HTTP/1.1\r\nHost: {host}\r\nHost: {host}\r\n\r\n".encode()
            )
            assert status == 400, status

            # Wrong Host -> 403.
            status, _, _ = await _raw_request(port, b"GET / HTTP/1.1\r\nHost: evil.example\r\n\r\n")
            assert status == 403, status

            # Transfer-Encoding refused -> 400.
            status, _, _ = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n".encode(),
            )
            assert status == 400, status

            # POST without Content-Length -> 411.
            status, _, _ = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\nContent-Type: application/json\r\n\r\n".encode(),
            )
            assert status == 411, status

            # Duplicate Content-Length -> 400.
            status, _, _ = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{{}}".encode(),
            )
            assert status == 400, status

            # Body over limit -> 413.
            status, _, _ = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {MAX_BODY_BYTES + 1}\r\n\r\n".encode(),
            )
            assert status == 413, status

            # Unexpected body on GET -> 400.
            status, _, _ = await _raw_request(
                port, f"GET / HTTP/1.1\r\nHost: {host}\r\nContent-Length: 4\r\n\r\ntest".encode()
            )
            assert status == 400, status

            # Slow client that never finishes headers -> 408.
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(f"GET / HTTP/1.1\r\nHost: {host}\r\n".encode())
                await writer.drain()
                slow_resp = await asyncio.wait_for(reader.read(), timeout=2.0)
                assert slow_resp.startswith(b"HTTP/1.1 408 "), slow_resp
            finally:
                writer.close()
                await writer.wait_closed()

            # Path with .. or encoded slash -> 400.
            for bad_path in ("/../desktop/server.py", "/%2fapp.js", "/app%2Fjs"):
                status, _, _ = await _raw_request(
                    port, f"GET {bad_path} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()
                )
                assert status == 400, (bad_path, status)

            # Wrong or missing Origin on POST /pair -> 403.
            pair_body = b'{"code":"123456","name":"Phone"}'
            for bad_origin in ("", "Origin: https://evil.example\r\n", "Origin: null\r\n"):
                status, _, _ = await _raw_request(
                    port,
                    f"POST /pair HTTP/1.1\r\nHost: {host}\r\n{bad_origin}"
                    f"Content-Type: application/json\r\nContent-Length: {len(pair_body)}\r\n\r\n".encode()
                    + pair_body,
                )
                assert status == 403, (bad_origin, status)

            # Tailscale Host requires https Origin, and forwarded identity headers are ignored.
            ts_code = store.create_code()
            ts_body = json.dumps({"code": ts_code, "name": "TailPhone"}).encode()
            status, _, _ = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: oak.tail.ts.net\r\nOrigin: http://oak.tail.ts.net\r\n"
                f"X-Forwarded-Proto: https\r\nTailscale-User-Login: fake\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(ts_body)}\r\n\r\n".encode()
                + ts_body,
            )
            assert status == 403, status
            status, hdrs, body = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: oak.tail.ts.net\r\nOrigin: https://oak.tail.ts.net\r\n"
                f"X-Forwarded-Host: evil.example\r\nTailscale-User-Login: ignored\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(ts_body)}\r\n\r\n".encode()
                + ts_body,
            )
            assert status == 200 and json.loads(body)["ok"] is True, (status, body)
            cookie_hdr = hdrs["set-cookie"][0]
            assert "HttpOnly" in cookie_hdr and "SameSite=Strict" in cookie_hdr and "Secure" in cookie_hdr
            assert "Domain=" not in cookie_hdr
            ts_token = _parse_cookie_value(cookie_hdr)
            # Raw token never appears in the SQLite database file.
            assert ts_token.encode() not in db_path.read_bytes()

            # 4. Pairing: expired code, race condition (one wins), wrong code, global rate limit.
            expired = store.create_code(ttl=-1.0)
            exp_body = json.dumps({"code": expired, "name": "Old"}).encode()
            status, _, _ = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(exp_body)}\r\n\r\n".encode()
                + exp_body,
            )
            assert status == 400, status

            # Clear the one failure from expired test so rate-limit test is exact.
            store._failures.clear()

            # Same code used twice at the same moment: exactly one wins.
            race_code = store.create_code()
            race_body = json.dumps({"code": race_code, "name": "RacePhone"}).encode()
            race_req = (
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(race_body)}\r\n\r\n".encode()
                + race_body
            )
            (s1, h1, b1), (s2, h2, b2) = await asyncio.gather(
                _raw_request(port, race_req),
                _raw_request(port, race_req),
            )
            assert sorted([s1, s2]) == [200, 400], (s1, s2)
            win_hdrs, win_body = (h1, b1) if s1 == 200 else (h2, b2)
            phone_token = _parse_cookie_value(win_hdrs["set-cookie"][0])
            phone_id = json.loads(win_body)["device"]["id"]

            # Wrong codes trip the global rate limit (already 1 failure from race loser; 2 more trips max=3).
            store._failures.clear()
            wrong_body = b'{"code":"ZZZZZZ","name":"Guess"}'
            wrong_req = (
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(wrong_body)}\r\n\r\n".encode()
                + wrong_body
            )
            for _ in range(3):
                status, _, _ = await _raw_request(port, wrong_req)
                assert status == 400, status
            valid_while_locked = store.create_code()
            locked_body = json.dumps({"code": valid_while_locked, "name": "Blocked"}).encode()
            status, _, _ = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(locked_body)}\r\n\r\n".encode()
                + locked_body,
            )
            assert status == 429, status
            store._failures.clear()

            # 5. Unknown route (404), wrong method (405), bad Origin on /command (403).
            status, _, _ = await _raw_request(
                port, f"GET /unknown HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode()
            )
            assert status == 404, status
            status, _, _ = await _raw_request(
                port, f"DELETE /work HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode()
            )
            assert status == 405, status
            cmd_body = b'{"id":"c1","kind":"ask","text":"hi"}'
            status, _, _ = await _raw_request(
                port,
                f"POST /command HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(cmd_body)}\r\n\r\n".encode()
                + cmd_body,
            )
            assert status == 403, status

            # 6. Commands pass through with device id; stale card returns JSON; raising session gives 5xx without traceback.
            status, _, body = await _raw_request(
                port,
                f"POST /command HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(cmd_body)}\r\n\r\n".encode()
                + cmd_body,
            )
            assert status == 200 and json.loads(body)["ok"] is True
            assert session.commands[-1] == (phone_id, {"id": "c1", "kind": "ask", "text": "hi"})

            session.stale_card = True
            card_body = b'{"id":"c2","kind":"card","card":"x","allow":true,"answers":{}}'
            status, _, body = await _raw_request(
                port,
                f"POST /command HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(card_body)}\r\n\r\n".encode()
                + card_body,
            )
            assert status == 409 and json.loads(body) == {"ok": False, "error": "stale"}

            session.fail_command = True
            status, _, body = await _raw_request(
                port,
                f"POST /command HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(cmd_body)}\r\n\r\n".encode()
                + cmd_body,
            )
            err_json = json.loads(body)
            assert 500 <= status < 600 and err_json["ok"] is False and "traceback" not in err_json["error"].lower()
            session.fail_command = False

            # /work returns a list and /mailbox returns a dict.
            status, _, body = await _raw_request(
                port, f"GET /work HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode()
            )
            assert status == 200 and isinstance(json.loads(body), list)
            status, _, body = await _raw_request(
                port, f"GET /mailbox HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode()
            )
            assert status == 200 and json.loads(body)["open"] == 1

            # 7. Streams: reconnect rule with event committed between subscribe/high_water and high_water/events_after.
            e1 = session.emit("state", {"state": "thinking"})  # seq 11
            # Commit seq 12 right before high_water reads H, and seq 13 right between high_water and events_after.
            session.on_high_water = lambda: session.emit("request", {"turn": "t-1", "state": "accepted"})
            session.on_events_after = lambda: session.emit("request", {"turn": "t-1", "state": "answered", "answer": "ok"})
            status, s_reader, s_writer = await _open_sse(port, phone_token, "/events?after=10")
            assert status == 200
            try:
                hello = await _read_sse_frame(s_reader)
                assert ": hello" in hello
                f1 = await _read_sse_frame(s_reader)
                f2 = await _read_sse_frame(s_reader)
                f3 = await _read_sse_frame(s_reader)
                assert f"id: {e1.seq}\n" in f1
                assert f"id: {e1.seq + 1}\n" in f2
                assert f"id: {e1.seq + 2}\n" in f3
                # Live event carries no id.
                session.emit("draft", {"turn": "t-1", "text": "part"}, live=True)
                f_live = await _read_sse_frame(s_reader)
                assert "id:" not in f_live and "event: draft\n" in f_live
                # Live speech events go only to the asking device.
                other_st, other_r, other_w = await _open_sse(port, ts_token, f"/events?after={session.seq}")
                assert other_st == 200
                try:
                    await _read_sse_frame(other_r)  # hello
                    session.emit("speech", {"live": True, "turn": "t-1", "index": 0, "id": "clip-1",
                                            "text": "Hi.", "device": phone_id}, live=True)
                    session.emit("state", {"live": True, "state": "resting"}, live=True)
                    f_sp = await _read_sse_frame(s_reader)
                    assert "event: speech\n" in f_sp and '"clip-1"' in f_sp, f_sp
                    f_st1 = await _read_sse_frame(s_reader)
                    assert "event: state\n" in f_st1, f_st1
                    f_other = await _read_sse_frame(other_r)
                    assert "event: state\n" in f_other and "speech" not in f_other, f_other
                finally:
                    other_w.close()
                    await other_w.wait_closed()
                # Quiet stream receives a keep-alive comment.
                ka = await _read_sse_frame(s_reader)
                assert ka.startswith(": keepalive")
            finally:
                s_writer.close()
                await s_writer.wait_closed()

            # Last-Event-ID is preferred over ?after=.
            status, s_reader, s_writer = await _open_sse(
                port, phone_token, "/events?after=10", extra_headers=f"Last-Event-ID: {e1.seq + 1}\r\n"
            )
            assert status == 200
            try:
                await _read_sse_frame(s_reader)  # hello
                only = await _read_sse_frame(s_reader)
                assert f"id: {e1.seq + 2}\n" in only
            finally:
                s_writer.close()
                await s_writer.wait_closed()

            # Cursor too old sends event: snapshot with data: {}.
            session.oldest_retained = e1.seq + 2
            status, s_reader, s_writer = await _open_sse(port, phone_token, "/events?after=5")
            assert status == 200
            try:
                snap_ev = await _read_sse_frame(s_reader)
                assert "event: snapshot\ndata: {}" in snap_ev
            finally:
                s_writer.close()
                await s_writer.wait_closed()
            session.oldest_retained = 1

            # Per-device stream limit (max_device_streams=2).
            s1_st, _, s1_w = await _open_sse(port, phone_token, f"/events?after={session.seq}")
            s2_st, _, s2_w = await _open_sse(port, phone_token, f"/events?after={session.seq}")
            assert s1_st == 200 and s2_st == 200
            s3_st, _, _ = await _raw_request(
                port, f"GET /events?after={session.seq} HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode()
            )
            assert s3_st == 429, s3_st
            s1_w.close()
            s2_w.close()
            await asyncio.gather(s1_w.wait_closed(), s2_w.wait_closed())
            await asyncio.sleep(0.05)

            # 8. Audio upload (POST /audio) and speech playback (GET /speech/<id>).
            audio_sample = b"\x1a\x45\xdf\xa3fake-opus-recording"
            for ct, want_ct in (
                ("audio/webm;codecs=opus", "audio/webm;codecs=opus"),
                ("audio/ogg", "audio/ogg"),
                ('audio/mp4; codecs="mp4a.40.2"', "audio/mp4;codecs=mp4a.40.2"),
            ):
                status, _, body = await _raw_request(
                    port,
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: {ct}\r\n"
                    f"X-Rook-Command: rec-1\r\nContent-Length: {len(audio_sample)}\r\n\r\n".encode()
                    + audio_sample,
                )
                assert status == 200 and json.loads(body)["turn"] == "t-audio", (ct, status, body)
                assert session.audios[-1] == (phone_id, "rec-1", want_ct, audio_sample)

            # Wrong Origin -> 403.
            status, _, _ = await _raw_request(
                port,
                f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: https://evil.example\r\n"
                f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                f"X-Rook-Command: rec-2\r\nContent-Length: 4\r\n\r\nabcd".encode(),
            )
            assert status == 403, status

            # Content-Type outside the allow list -> 415.
            for bad_ct in ("audio/wav", "application/json", "audio/webm; codecs=opus; foo=bar"):
                status, _, _ = await _raw_request(
                    port,
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: {bad_ct}\r\n"
                    f"X-Rook-Command: rec-3\r\nContent-Length: 4\r\n\r\nabcd".encode(),
                )
                assert status == 415, (bad_ct, status)

            # Missing Content-Length -> 411; bad or zero Content-Length -> 400; over cap -> 413.
            status, _, _ = await _raw_request(
                port,
                f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                f"X-Rook-Command: rec-4\r\n\r\n".encode(),
            )
            assert status == 411, status
            for bad_cl in ("abc", "-5", "0"):
                status, _, _ = await _raw_request(
                    port,
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                    f"X-Rook-Command: rec-4\r\nContent-Length: {bad_cl}\r\n\r\n".encode(),
                )
                assert status == 400, (bad_cl, status)
            status, _, _ = await _raw_request(
                port,
                f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                f"X-Rook-Command: rec-4\r\nContent-Length: {server.max_audio_bytes + 1}\r\n\r\n".encode(),
            )
            assert status == 413, status

            # Missing or malformed X-Rook-Command -> 400.
            for bad_hdr in ("", "X-Rook-Command: a/b\r\n", "X-Rook-Command: a b\r\n", f"X-Rook-Command: {'x' * 129}\r\n"):
                status, _, _ = await _raw_request(
                    port,
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                    f"{bad_hdr}Content-Length: 4\r\n\r\nabcd".encode(),
                )
                assert status == 400, (bad_hdr, status)

            # Body cut short -> 400 and nothing reaches session.audio.
            audios_before = len(session.audios)
            short_r, short_w = await asyncio.open_connection("127.0.0.1", port)
            try:
                short_w.write(
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                    f"X-Rook-Command: rec-short\r\nContent-Length: 20\r\n\r\nabcd".encode()
                )
                await short_w.drain()
                short_w.write_eof()
                resp = await asyncio.wait_for(short_r.read(), timeout=2.0)
                assert resp.startswith(b"HTTP/1.1 400 "), resp
            finally:
                short_w.close()
                await short_w.wait_closed()
            assert len(session.audios) == audios_before

            # Body trickled one byte at a time past audio_read_timeout -> 408 and nothing reaches session.audio.
            trickle_r, trickle_w = await asyncio.open_connection("127.0.0.1", port)
            try:
                trickle_w.write(
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                    f"X-Rook-Command: rec-slow\r\nContent-Length: 10\r\n\r\n".encode()
                )
                await trickle_w.drain()
                for _ in range(4):
                    trickle_w.write(b"a")
                    try:
                        await trickle_w.drain()
                    except ConnectionError:
                        break
                    await asyncio.sleep(0.18)
                resp = await asyncio.wait_for(trickle_r.read(), timeout=2.0)
                assert resp.startswith(b"HTTP/1.1 408 "), resp
            finally:
                trickle_w.close()
                await trickle_w.wait_closed()
            assert len(session.audios) == audios_before

            # Two uploads at once from one device -> second gets 429; total bytes cap -> second device gets 503.
            u1_r, u1_w = await asyncio.open_connection("127.0.0.1", port)
            try:
                u1_w.write(
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                    f"X-Rook-Command: rec-u1\r\nContent-Length: 60000\r\n\r\n".encode()
                    + b"x" * 10
                )
                await u1_w.drain()
                deadline = time.monotonic() + 1.0
                while phone_id not in server._audio_devices and time.monotonic() < deadline:
                    await asyncio.sleep(0.01)
                assert phone_id in server._audio_devices

                # Second upload from the same device is rejected with 429.
                status, _, _ = await _raw_request(
                    port,
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                    f"X-Rook-Command: rec-u2\r\nContent-Length: 10\r\n\r\n0123456789".encode(),
                )
                assert status == 429, status

                # Upload from another device that exceeds max_audio_in_flight (90000) gets 503.
                status, _, _ = await _raw_request(
                    port,
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={ts_token}\r\nContent-Type: audio/webm\r\n"
                    f"X-Rook-Command: rec-u3\r\nContent-Length: 40000\r\n\r\n".encode(),
                )
                assert status == 503, status

                u1_w.write(b"x" * (60000 - 10))
                await u1_w.drain()
                resp = await asyncio.wait_for(u1_r.read(), timeout=2.0)
                assert resp.startswith(b"HTTP/1.1 200 "), resp
            finally:
                u1_w.close()
                await u1_w.wait_closed()
            assert server._audio_in_flight == 0 and not server._audio_devices

            # Raising session.audio returns 500 with one plain sentence and no traceback.
            session.fail_audio = True
            status, _, body = await _raw_request(
                port,
                f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                f"X-Rook-Command: rec-err\r\nContent-Length: 4\r\n\r\nabcd".encode(),
            )
            err_json = json.loads(body)
            assert status == 500 and err_json["ok"] is False and "traceback" not in err_json["error"].lower()
            session.fail_audio = False

            # GET /speech/<id>: good piece, headers, invalid ids, refused piece, ranges, bad ranges, oversized piece.
            status, hdrs, body = await _raw_request(
                port,
                f"GET /speech/clip-1 HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode(),
            )
            assert status == 200 and body == b"0123456789"
            assert hdrs["content-type"] == ["audio/ogg"]
            assert hdrs["content-length"] == ["10"]
            assert hdrs["accept-ranges"] == ["bytes"]
            assert hdrs["cache-control"] == ["no-store"]
            assert hdrs["x-content-type-options"] == ["nosniff"]
            assert hdrs["content-security-policy"] == [CSP]
            assert hdrs["permissions-policy"] == [PERMISSIONS_POLICY]

            # Wrong method on /speech/<id> -> 405.
            status, _, _ = await _raw_request(
                port,
                f"POST /speech/clip-1 HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Length: 0\r\n\r\n".encode(),
            )
            assert status == 405, status

            # Bad speech ids are refused with 400 before reaching the session.
            calls_before = len(session.speech_calls)
            for bad_speech in ("/speech/", "/speech/a/b", "/speech/..", "/speech/a%2fb", f"/speech/{'a' * 65}"):
                status, _, _ = await _raw_request(
                    port,
                    f"GET {bad_speech} HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode(),
                )
                assert status == 400, (bad_speech, status)
            assert len(session.speech_calls) == calls_before

            # Session returns None -> 404.
            status, _, _ = await _raw_request(
                port,
                f"GET /speech/missing HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode(),
            )
            assert status == 404, status

            # Single well-formed Range requests -> 206 with Content-Range.
            for range_hdr, want_cr, want_body in (
                ("bytes=2-5", "bytes 2-5/10", b"2345"),
                ("bytes=7-", "bytes 7-9/10", b"789"),
                ("bytes=-3", "bytes 7-9/10", b"789"),
            ):
                status, hdrs, body = await _raw_request(
                    port,
                    f"GET /speech/clip-1 HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n"
                    f"Range: {range_hdr}\r\n\r\n".encode(),
                )
                assert status == 206 and hdrs["content-range"] == [want_cr] and body == want_body, (
                    range_hdr,
                    status,
                    hdrs,
                    body,
                )

            # Bad or multi-range Range headers -> 416 with Content-Range: bytes */10.
            for bad_range in ("bytes=20-30", "bytes=6-2", "bytes=0-1, 2-3", "items=0-2", "bytes=-0"):
                status, hdrs, _ = await _raw_request(
                    port,
                    f"GET /speech/clip-1 HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n"
                    f"Range: {bad_range}\r\n\r\n".encode(),
                )
                assert status == 416 and hdrs["content-range"] == ["bytes */10"], (bad_range, status, hdrs)

            # Oversized speech clip -> 500.
            session.clips["clip-big"] = ("audio/ogg", b"z" * (server.max_speech_bytes + 1))
            status, _, body = await _raw_request(
                port,
                f"GET /speech/clip-big HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n".encode(),
            )
            assert status == 500 and json.loads(body)["ok"] is False, (status, body)

            # 9. Revoking a device closes its open stream at once and blocks snapshot, audio, and speech.
            rev_st, rev_r, rev_w = await _open_sse(port, phone_token, f"/events?after={session.seq}")
            assert rev_st == 200
            await _read_sse_frame(rev_r)  # hello
            assert await server.revoke_device(phone_id) is True
            eof = await asyncio.wait_for(rev_r.read(), timeout=1.0)
            assert eof == b"", eof
            rev_w.close()
            await rev_w.wait_closed()
            for revoked_req in (
                f"GET /snapshot HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n",
                f"GET /speech/clip-1 HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={phone_token}\r\n\r\n",
                f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Cookie: {COOKIE_NAME}={phone_token}\r\nContent-Type: audio/webm\r\n"
                f"X-Rook-Command: rec-rev\r\nContent-Length: 4\r\n\r\nabcd",
            ):
                status, _, _ = await _raw_request(port, revoked_req.encode())
                assert status == 401, (revoked_req, status)

            # 9. Locked database returns 503 without harming the server.
            blocker = sqlite3.connect(str(db_path), isolation_level=None)
            blocker.execute("BEGIN EXCLUSIVE")
            try:
                lock_body = b'{"code":"123456","name":"Locked"}'
                status, _, body = await _raw_request(
                    port,
                    f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Content-Type: application/json\r\nContent-Length: {len(lock_body)}\r\n\r\n".encode()
                    + lock_body,
                )
                assert status == 503 and json.loads(body)["ok"] is False, (status, body)
            finally:
                blocker.execute("ROLLBACK")
                blocker.close()

            # 10. Timing check: 20 idle streams and 1 stalled client.
            tokens: list[str] = []
            for i in range(12):
                c = store.create_code()
                b = json.dumps({"code": c, "name": f"Dev{i}"}).encode()
                st, hdrs, _ = await _raw_request(
                    port,
                    f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Content-Type: application/json\r\nContent-Length: {len(b)}\r\n\r\n".encode()
                    + b,
                )
                assert st == 200
                tokens.append(_parse_cookie_value(hdrs["set-cookie"][0]))

            idle_writers: list[asyncio.StreamWriter] = []
            idle_readers: list[asyncio.StreamReader] = []
            for i in range(20):
                st, r, w = await _open_sse(port, tokens[i // 2], f"/events?after={session.seq}")
                assert st == 200
                await _read_sse_frame(r)  # hello
                idle_readers.append(r)
                idle_writers.append(w)

            # One stalled client: small receive buffer set before connect, never reads after opening.
            stalled_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            stalled_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            stalled_sock.connect(("127.0.0.1", port))
            stalled_sock.sendall(
                f"GET /events?after={session.seq} HTTP/1.1\r\nHost: {host}\r\n"
                f"Cookie: {COOKIE_NAME}={tokens[10]}\r\n\r\n".encode()
            )
            deadline = time.monotonic() + 2.0
            while len(session.subscribers) < 21 and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert len(session.subscribers) == 21, len(session.subscribers)

            # Measure push and snapshot with an audio upload in progress, 20 idle streams, and 1 stalled client.
            up_r, up_w = await asyncio.open_connection("127.0.0.1", port)
            try:
                up_size = 32768
                up_w.write(
                    f"POST /audio HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                    f"Cookie: {COOKIE_NAME}={tokens[11]}\r\nContent-Type: audio/webm;codecs=opus\r\n"
                    f"X-Rook-Command: rec-load\r\nContent-Length: {up_size}\r\n\r\n".encode()
                    + b"a" * 4096
                )
                await up_w.drain()
                deadline = time.monotonic() + 1.0
                while server._audio_in_flight == 0 and time.monotonic() < deadline:
                    await asyncio.sleep(0.005)
                assert server._audio_in_flight == up_size

                t0 = time.perf_counter()
                session.emit("state", {"state": "thinking"})
                push_ms = (time.perf_counter() - t0) * 1000.0
                assert push_ms < 1.0, f"Push took {push_ms:.3f} ms"

                t1 = time.perf_counter()
                status, _, body = await _raw_request(
                    port, f"GET /snapshot HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={ts_token}\r\n\r\n".encode()
                )
                snap_ms = (time.perf_counter() - t1) * 1000.0
                assert status == 200 and json.loads(body)["state"] == "resting"
                assert snap_ms < 250.0, f"Snapshot took {snap_ms:.3f} ms"

                up_w.write(b"a" * (up_size - 4096))
                await up_w.drain()
                up_resp = await asyncio.wait_for(up_r.read(), timeout=2.0)
                assert up_resp.startswith(b"HTTP/1.1 200 "), up_resp
            finally:
                up_w.close()
                await up_w.wait_closed()

            # Keep idle readers draining while pushing enough data to stall and disconnect the unread socket.
            async def _drain_reader(r: asyncio.StreamReader) -> None:
                try:
                    while await r.read(65536):
                        pass
                except (OSError, asyncio.CancelledError):
                    pass

            drainers = [asyncio.create_task(_drain_reader(r)) for r in idle_readers]
            try:
                blob = "x" * 16000
                for _ in range(200):
                    if len(session.subscribers) <= 20:
                        break
                    t_push = time.perf_counter()
                    session.emit("draft", {"blob": blob}, live=True)
                    assert (time.perf_counter() - t_push) * 1000.0 < 1.0
                    await asyncio.sleep(0.005)
                deadline = time.monotonic() + 2.0
                while len(session.subscribers) >= 21 and time.monotonic() < deadline:
                    await asyncio.sleep(0.02)
                assert len(session.subscribers) == 20, len(session.subscribers)
            finally:
                stalled_sock.close()
                for d in drainers:
                    d.cancel()
                await asyncio.gather(*drainers, return_exceptions=True)

            # Total stream limit (max_streams=24): open 4 more, then the 25th gets 503.
            extra_writers: list[asyncio.StreamWriter] = []
            for i in range(4):
                st, r, w = await _open_sse(port, tokens[10 + i // 2], f"/events?after={session.seq}")
                assert st == 200
                await _read_sse_frame(r)
                extra_writers.append(w)
            st_over, _, _ = await _raw_request(
                port,
                f"GET /events?after={session.seq} HTTP/1.1\r\nHost: {host}\r\n"
                f"Cookie: {COOKIE_NAME}={ts_token}\r\n\r\n".encode(),
            )
            assert st_over == 503, st_over

            for w in (*idle_writers, *extra_writers):
                w.close()
            await asyncio.gather(*(w.wait_closed() for w in (*idle_writers, *extra_writers)))
            deadline = time.monotonic() + 2.0
            while session.subscribers and time.monotonic() < deadline:
                await asyncio.sleep(0.02)
            assert len(session.subscribers) == 0, f"Leaked subscribers: {len(session.subscribers)}"

            # 11. Explicit secure_cookies=False omits the Secure flag for plain HTTP checks.
            server.secure_cookies = False
            plain_code = store.create_code()
            plain_body = json.dumps({"code": plain_code, "name": "PlainHTTP"}).encode()
            st, hdrs, _ = await _raw_request(
                port,
                f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(plain_body)}\r\n\r\n".encode()
                + plain_body,
            )
            assert st == 200 and "Secure" not in hdrs["set-cookie"][0] and "HttpOnly" in hdrs["set-cookie"][0]

            # 12. Shared presence page, theme player assets, and read-only loopback presence token.
            # Without a local presence token (Linux), the presence page and themes are not served, as before.
            for route in ("/presence", "/presence.css", "/presence-host.js", "/themes/forge/presence.js"):
                st, _, _ = await _raw_request(port, f"GET {route} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
                assert st == 401, (route, st)
            server.local_token = "local-presence-check-token"
            st, _, body = await _raw_request(port, f"GET /presence HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
            assert st == 200 and b"/presence.js" in body and b"/themes/forge/presence.js" in body, st
            st, _, body = await _raw_request(
                port, f"GET /themes/forge/presence.js HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()
            )
            assert st == 200 and b"ThemePresence" in body, st
            st, _, _ = await _raw_request(
                port, f"GET /themes/forge/..%2Fforge/presence.js HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()
            )
            assert st in (400, 404), st
            st, _, _ = await _raw_request(
                port, f"GET /themes/forge/FORMAT.md HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()
            )
            assert st == 404, st
            st, _, body = await _raw_request(
                port,
                f"GET /snapshot HTTP/1.1\r\nHost: {host}\r\n"
                f"Cookie: {COOKIE_NAME}=local-presence-check-token\r\n\r\n".encode(),
            )
            assert st == 200 and "cursor" in json.loads(body), (st, body)
            cmd_bytes = json.dumps({"id": "lp-1", "kind": "ask", "text": "no"}).encode()
            st, _, _ = await _raw_request(
                port,
                f"POST /command HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
                f"Cookie: {COOKIE_NAME}=local-presence-check-token\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(cmd_bytes)}\r\n\r\n".encode() + cmd_bytes,
            )
            assert st == 403, st
            st, _, _ = await _raw_request(
                port,
                f"GET /snapshot HTTP/1.1\r\nHost: oak.tail.ts.net\r\n"
                f"Cookie: {COOKIE_NAME}=local-presence-check-token\r\n\r\n".encode(),
            )
            assert st == 401, st
            server.local_token = None

            # 13. Missing database file returns 503 cleanly.
            db_path.unlink()
            status, _, body = await _raw_request(
                port, f"GET /snapshot HTTP/1.1\r\nHost: {host}\r\nCookie: {COOKIE_NAME}={ts_token}\r\n\r\n".encode()
            )
            assert status == 503 and json.loads(body)["ok"] is False, (status, body)
        finally:
            await server.close()

    return f"HTTP server: all checks passed. Push took {push_ms:.3f} ms and snapshot took {snap_ms:.2f} ms."


async def _run_lan_check() -> str:
    """The opt-in LAN listener. 127.0.0.2 stands in for the LAN address: Linux routes all of 127/8 to loopback."""
    with tempfile.TemporaryDirectory(prefix="rook-server-lan-") as scratch:
        store = DeviceStore(Path(scratch) / "devices.db").open()
        pair_body = lambda code: json.dumps({"code": code, "name": "Steam Deck"}).encode()  # noqa: E731

        def pair(host: str, origin: str, code: str) -> bytes:
            return (f"POST /pair HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(pair_body(code))}\r\n\r\n").encode() + pair_body(code)

        # Off, as by default: the LAN address is not listened on, and its Host is refused over loopback.
        plain = await Server(_FakeSession(), store, port=0, allowed_hosts=("oak.tail.ts.net",)).start()
        try:
            try:
                await _raw_request(plain.port, f"GET / HTTP/1.1\r\nHost: 127.0.0.2:{plain.port}\r\n\r\n".encode(),
                                   address="127.0.0.2")
                raise AssertionError("a server with no LAN address answered on another address")
            except ConnectionRefusedError:
                pass
            status, _, _ = await _raw_request(plain.port,
                                              f"GET / HTTP/1.1\r\nHost: 127.0.0.2:{plain.port}\r\n\r\n".encode())
            assert status == 403, status
        finally:
            await plain.close()

        # On, with a port of its own and with the loopback port: each LAN connection takes only its own address's Host,
        # with the http Origin, and pairs with a cookie a browser keeps over plain HTTP.
        free = socket.socket()
        free.bind(("127.0.0.2", 0))
        lan_port = free.getsockname()[1]
        free.close()
        for own_port in (lan_port, None):
            server = await Server(_FakeSession(), store, port=0, allowed_hosts=("oak.tail.ts.net",), lan="127.0.0.2",
                                  lan_port=own_port).start()
            try:
                port = own_port or next(sock.getsockname()[1] for sock in server._server.sockets
                                        if sock.getsockname()[0] == "127.0.0.2")
                lan = f"127.0.0.2:{port}"
                status, _, _ = await _raw_request(port, f"GET / HTTP/1.1\r\nHost: {lan}\r\n\r\n".encode(),
                                                  address="127.0.0.2")
                assert status == 200, status
                for wrong in (f"127.0.0.1:{server.port}", "oak.tail.ts.net", f"127.0.0.3:{port}"):
                    status, _, _ = await _raw_request(port, f"GET / HTTP/1.1\r\nHost: {wrong}\r\n\r\n".encode(),
                                                      address="127.0.0.2")
                    assert status == 403, (wrong, status)
                status, _, _ = await _raw_request(server.port, f"GET / HTTP/1.1\r\nHost: {lan}\r\n\r\n".encode())
                assert status == 403, "the LAN Host over loopback"
                status, _, _ = await _raw_request(port, pair(lan, f"https://{lan}", store.create_code()),
                                                  address="127.0.0.2")
                assert status == 403, "an https Origin on the LAN"
                status, hdrs, body = await _raw_request(port, pair(lan, f"http://{lan}", store.create_code()),
                                                        address="127.0.0.2")
                assert status == 200 and json.loads(body)["device"]["name"] == "Steam Deck", (status, body)
                cookie = hdrs["set-cookie"][0]
                assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Secure" not in cookie, cookie
                token = _parse_cookie_value(cookie)
                status, _, _ = await _raw_request(
                    port, f"GET /snapshot HTTP/1.1\r\nHost: {lan}\r\nCookie: {COOKIE_NAME}={token}\r\n\r\n".encode(),
                    address="127.0.0.2")
                assert status == 200, status
            finally:
                await server.close()
    return "LAN listener: off by default, and when on, its own Host and http Origin only. All checks passed."


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hermetic check for Rook's HTTP server.")
    parser.add_argument("--check", action="store_true", help="Run the hermetic server check.")
    parser.parse_args()
    print(asyncio.run(_run_check()))
    print(asyncio.run(_run_lan_check()))


if __name__ == "__main__":
    main()
