"""A small HTTP/1.1 client on asyncio streams, for Rook's phone server.

Rook's server answers one request per connection and closes it (desktop/server.py sends Connection: close), so every
request here opens its own connection. Bodies come with Content-Length; a proxy in between may send chunked bodies,
and the event stream may run until the server closes it, so both are read too.

The Host and Origin headers come from the URL the user gave: scheme://host:port. Rook's server checks both. Cookies are
handled here by hand, so a cookie the server marks Secure still goes out over plain http on the home LAN.
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
from dataclasses import dataclass, field
from typing import AsyncIterator
from urllib.parse import urlsplit

MAX_HEAD = 16384
MAX_BODY = 8 * 1024 * 1024
CA_FILES = ("/etc/ssl/certs/ca-certificates.crt", "/etc/ca-certificates/extracted/tls-ca-bundle.pem")


class HttpError(OSError):
    """The server could not be reached, or its answer was not HTTP."""


@dataclass
class Base:
    """Where Rook's server is, as the plugin speaks to it."""

    scheme: str
    host: str  # The host name or address, lower case, without brackets.
    port: int
    netloc: str  # host:port as the Host header carries it.

    @property
    def origin(self) -> str:
        return f"{self.scheme}://{self.netloc}"

    @property
    def url(self) -> str:
        return self.origin


def parse_base(url: str) -> Base:
    """Read a server address such as http://192.168.1.20:47326 or https://pc.tail.ts.net:8447.
    A bare host:port means http, the LAN default. Raises ValueError with a sentence for the user."""
    text = (url or "").strip()
    if not text:
        raise ValueError("Enter Rook's address, such as http://192.168.1.20:47326.")
    if "://" not in text:
        text = "http://" + text
    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("Rook's address starts with http:// or https://.")
    if not parts.hostname:
        raise ValueError("Rook's address needs a host, such as 192.168.1.20.")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ValueError("Give only Rook's address and port, with no path.")
    try:
        explicit = parts.port
    except ValueError as exc:
        raise ValueError("The port in Rook's address is not a number.") from exc
    host = parts.hostname.lower()
    port = explicit or (443 if scheme == "https" else 80)
    shown = f"[{host}]" if ":" in host else host
    netloc = f"{shown}:{port}" if explicit else shown
    return Base(scheme, host, port, netloc)


def ssl_context() -> ssl.SSLContext:
    """Certificate checks on, with the system's CA bundle when the embedded Python's own default finds none."""
    context = ssl.create_default_context()
    if not context.get_ca_certs():
        for path in CA_FILES:
            if os.path.isfile(path):
                context.load_verify_locations(path)
                break
    return context


@dataclass
class Response:
    status: int
    headers: dict[str, list[str]] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        values = self.headers.get(name.lower())
        return values[0] if values else None

    def json(self) -> dict:
        try:
            data = json.loads(self.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {"value": data}


def cookie_from(response: Response, name: str) -> str | None:
    """The value of one cookie a response sets. Its attributes (Secure, HttpOnly, Path) do not matter here."""
    for raw in response.headers.get("set-cookie", []):
        pair = raw.split(";", 1)[0]
        key, sep, value = pair.partition("=")
        if sep and key.strip() == name and value.strip():
            return value.strip()
    return None


async def _open(base: Base, timeout: float):
    context = ssl_context() if base.scheme == "https" else None
    try:
        return await asyncio.wait_for(asyncio.open_connection(
            base.host, base.port, ssl=context, server_hostname=base.host if context else None,
            limit=MAX_HEAD * 4), timeout)
    except (OSError, asyncio.TimeoutError, ssl.SSLError) as exc:
        raise HttpError(f"could not connect to {base.netloc}: {exc!r}") from exc


def _request_bytes(base: Base, method: str, path: str, headers: dict[str, str], body: bytes | None) -> bytes:
    lines = [f"{method} {path} HTTP/1.1", f"Host: {base.netloc}", "Connection: close", "User-Agent: rook-deck"]
    for key, value in headers.items():
        if "\r" in value or "\n" in value or "\r" in key or "\n" in key:
            raise ValueError("A header may not hold a line break.")
        lines.append(f"{key}: {value}")
    if body is not None:
        lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + (body or b"")


async def _read_head(reader: asyncio.StreamReader) -> tuple[int, dict[str, list[str]]]:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except asyncio.IncompleteReadError as exc:
        raise HttpError("the server closed the connection before answering") from exc
    except asyncio.LimitOverrunError as exc:
        raise HttpError("the server's answer headers are too large") from exc
    lines = head.decode("latin-1").split("\r\n")
    status_line = lines[0].split(" ", 2)
    if len(status_line) < 2 or not status_line[0].startswith("HTTP/") or not status_line[1].isdigit():
        raise HttpError("the answer was not HTTP")
    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        if not line:
            continue
        key, sep, value = line.partition(":")
        if sep:
            headers.setdefault(key.strip().lower(), []).append(value.strip())
    return int(status_line[1]), headers


async def _body_chunks(reader: asyncio.StreamReader, headers: dict[str, list[str]]) -> AsyncIterator[bytes]:
    """The body as it arrives: by Content-Length, by chunks, or until the server closes the connection."""
    encoding = ",".join(headers.get("transfer-encoding", [])).lower()
    if "chunked" in encoding:
        while True:
            size_line = await reader.readline()
            if not size_line:
                return
            size = int(size_line.split(b";", 1)[0].strip() or b"0", 16)
            if size == 0:
                await reader.readline()
                return
            data = await reader.readexactly(size)
            await reader.readexactly(2)
            yield data
        return
    lengths = headers.get("content-length")
    if lengths:
        remaining = int(lengths[0])
        while remaining > 0:
            data = await reader.read(min(65536, remaining))
            if not data:
                raise HttpError("the answer ended early")
            remaining -= len(data)
            yield data
        return
    while True:
        data = await reader.read(65536)
        if not data:
            return
        yield data


async def request(base: Base, method: str, path: str, *, headers: dict[str, str] | None = None,
                  body: bytes | None = None, timeout: float = 15.0, max_body: int = MAX_BODY) -> Response:
    """One whole request and answer. Raises HttpError when the server cannot be reached or the answer breaks."""
    reader, writer = await _open(base, timeout)
    try:
        async with asyncio.timeout(timeout):
            writer.write(_request_bytes(base, method, path, headers or {}, body))
            await writer.drain()
            status, answer_headers = await _read_head(reader)
            chunks = bytearray()
            async for data in _body_chunks(reader, answer_headers):
                chunks += data
                if len(chunks) > max_body:
                    raise HttpError("the answer is too large")
            return Response(status, answer_headers, bytes(chunks))
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise HttpError("the server took too long to answer") from exc
    except (OSError, asyncio.IncompleteReadError, ValueError, ssl.SSLError) as exc:
        if isinstance(exc, HttpError):
            raise
        raise HttpError(f"the connection broke: {exc!r}") from exc
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 1.0)
        except Exception:
            pass


class Stream:
    """An open streaming answer, such as Rook's event stream. Use as an async context manager."""

    def __init__(self, base: Base, path: str, headers: dict[str, str], connect_timeout: float = 10.0):
        self.base, self.path, self.headers, self.connect_timeout = base, path, headers, connect_timeout
        self.status = 0
        self.response_headers: dict[str, list[str]] = {}
        self._writer = None
        self._reader = None

    async def __aenter__(self) -> "Stream":
        self._reader, self._writer = await _open(self.base, self.connect_timeout)
        try:
            async with asyncio.timeout(self.connect_timeout):
                self._writer.write(_request_bytes(self.base, "GET", self.path, self.headers, None))
                await self._writer.drain()
                self.status, self.response_headers = await _read_head(self._reader)
        except BaseException:
            await self.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *exc) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await asyncio.wait_for(self._writer.wait_closed(), 1.0)
            except Exception:
                pass
            self._writer = None

    async def read_all(self, limit: int = 65536) -> bytes:
        out = bytearray()
        async for data in _body_chunks(self._reader, self.response_headers):
            out += data
            if len(out) > limit:
                break
        return bytes(out)

    def chunks(self) -> AsyncIterator[bytes]:
        return _body_chunks(self._reader, self.response_headers)
