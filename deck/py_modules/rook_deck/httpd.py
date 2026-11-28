"""A small HTTP/1.1 server on asyncio streams, for the Deck agent API and the overlay feed.

One request per connection, answered with Connection: close, as Rook's own server does. Bodies need Content-Length and
are capped; chunked uploads are refused. A handler returns a Reply, or takes over the connection for an event stream.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import parse_qs, urlsplit

MAX_HEAD = 8192
MAX_BODY = 16384
READ_SECONDS = 5.0
PHRASES = {200: "OK", 204: "No Content", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
           405: "Method Not Allowed", 409: "Conflict", 411: "Length Required", 413: "Content Too Large",
           415: "Unsupported Media Type", 500: "Internal Server Error", 503: "Service Unavailable"}


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes
    peer: str = ""

    def arg(self, name: str, default: str | None = None) -> str | None:
        values = self.query.get(name)
        return values[0] if values else default

    def json(self) -> object:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None


@dataclass
class Reply:
    status: int
    body: bytes = b""
    content_type: str = "application/json"
    headers: list[tuple[str, str]] = field(default_factory=list)


def json_reply(status: int, payload: object) -> Reply:
    return Reply(status, json.dumps(payload, separators=(",", ":")).encode())


class Stream:
    """Hands an event stream's writer to a handler. send() writes one SSE message."""

    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer

    async def open(self, extra: list[tuple[str, str]] = ()) -> None:
        head = ["HTTP/1.1 200 OK", "Content-Type: text/event-stream", "Cache-Control: no-store",
                "Connection: close", "X-Accel-Buffering: no", *[f"{k}: {v}" for k, v in extra]]
        self.writer.write(("\r\n".join(head) + "\r\n\r\n").encode())
        await self.writer.drain()

    async def send(self, data: object, event: str | None = None) -> None:
        line = json.dumps(data, separators=(",", ":"))
        frame = (f"event: {event}\n" if event else "") + f"data: {line}\n\n"
        self.writer.write(frame.encode())
        await asyncio.wait_for(self.writer.drain(), 5)

    async def comment(self, text: str = "keepalive") -> None:
        self.writer.write(f": {text}\n\n".encode())
        await asyncio.wait_for(self.writer.drain(), 5)


Handler = Callable[[Request, Stream], Awaitable[Reply | None]]


class Server:
    def __init__(self, handler: Handler, host: str, port: int, log=None):
        self.handler = handler
        self.host, self.port = host, port
        self.log = log
        self.server: asyncio.Server | None = None

    async def start(self) -> "Server":
        self.server = await asyncio.start_server(self._serve, self.host, self.port, reuse_address=True,
                                                 limit=MAX_HEAD * 2)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def close(self) -> None:
        if self.server is not None:
            self.server.close()
            try:
                await asyncio.wait_for(self.server.wait_closed(), 2)
            except asyncio.TimeoutError:
                pass
            self.server = None

    async def _read(self, reader: asyncio.StreamReader) -> Request | Reply:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), READ_SECONDS)
        except asyncio.LimitOverrunError:
            return json_reply(400, {"ok": False, "error": "The request headers are too large."})
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            raise ConnectionError("no request")
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
            return json_reply(400, {"ok": False, "error": "The request line is malformed."})
        headers: dict[str, str] = {}
        for line in lines[1:]:
            key, sep, value = line.partition(":")
            if sep:
                headers[key.strip().lower()] = value.strip()
        if "transfer-encoding" in headers:
            return json_reply(411, {"ok": False, "error": "Send the body with Content-Length."})
        length = headers.get("content-length", "0")
        if not length.isdigit():
            return json_reply(400, {"ok": False, "error": "Content-Length must be a number."})
        if int(length) > MAX_BODY:
            return json_reply(413, {"ok": False, "error": "The request body is too large."})
        try:
            body = await asyncio.wait_for(reader.readexactly(int(length)), READ_SECONDS) if int(length) else b""
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            raise ConnectionError("short body")
        target = urlsplit(parts[1])
        return Request(parts[0].upper(), target.path, parse_qs(target.query, keep_blank_values=True), headers, body)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            got = await self._read(reader)
            if isinstance(got, Request):
                peer = writer.get_extra_info("peername")
                got.peer = peer[0] if isinstance(peer, tuple) else ""
                try:
                    reply = await self.handler(got, Stream(writer))
                except Exception as exc:
                    if self.log:
                        self.log.exception(f"handler failed for {got.method} {got.path}: {exc!r}")
                    reply = json_reply(500, {"ok": False, "error": "The Deck hit an unexpected error."})
            else:
                reply = got
            if reply is not None:
                head = [f"HTTP/1.1 {reply.status} {PHRASES.get(reply.status, 'Error')}",
                        f"Content-Type: {reply.content_type}", f"Content-Length: {len(reply.body)}",
                        "Cache-Control: no-store", "Connection: close", "X-Content-Type-Options: nosniff",
                        *[f"{k}: {v}" for k, v in reply.headers]]
                writer.write(("\r\n".join(head) + "\r\n\r\n").encode("latin-1") + reply.body)
                await asyncio.wait_for(writer.drain(), 10)
        except (ConnectionError, asyncio.TimeoutError, OSError):
            pass
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except Exception:
                pass
