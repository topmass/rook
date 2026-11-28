"""The Deck's two HTTP servers.

The Deck agent API (0.0.0.0:47330) is how Rook on the PC reaches the game on the Deck: which game has focus, a picture
of a region of it, an approved chat reply typed into it, and a note into WoWFriend. Every route but /health needs the
token, as "Authorization: Bearer <token>". A wrong or missing token gets a plain 401 that never says which part
failed, and the token is compared in constant time. Anything that can call /type can speak in the player's name.

The overlay feed (127.0.0.1:47331) serves the overlay page from overlay/page and a stream of what the overlay shows.
It listens on loopback only and needs no token: it only ever shows Rook's state and words, which the overlay draws
over the game anyway.
"""

from __future__ import annotations

import asyncio
import mimetypes
import secrets
from pathlib import Path
from typing import Awaitable, Callable

from . import VERSION
from .httpd import Reply, Request, Server, Stream, json_reply
from .notes import NoteError
from .uinput import check_text

AGENT_PORT = 47330
OVERLAY_PORT = 47331
WINDOW_SECONDS = 0.8  # /window answers inside Rook's grab budget even when the X display hangs.
CAPTURE_SECONDS = 0.95  # The contract's one second, less the network.
WOW_TITLE = "World of Warcraft"


def _int(value: str | None, name: str, low: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number") from None
    if number < low:
        raise ValueError(f"{name} must be at least {low}")
    return number


class DeckAgent:
    """The routes. Each part of the Deck is a callable given in, so tests run them with fakes."""

    def __init__(self, token: Callable[[], str], *, window: Callable[[], Awaitable[dict]],
                 capture: Callable[..., Awaitable[tuple[str, bytes] | None]],
                 typist=None, note: Callable[[str], Awaitable[int]] | None = None, log=None):
        self.token = token
        self.window = window
        self.capture = capture
        self.typist = typist
        self.note = note
        self.log = log

    def authorised(self, request: Request) -> bool:
        given = request.headers.get("authorization", "")
        scheme, _, value = given.partition(" ")
        expected = self.token()
        # Both sides are compared whole, in constant time, even when the scheme is wrong, so timing tells nothing.
        ok = secrets.compare_digest(value.strip().encode(), expected.encode())
        return ok and scheme.lower() == "bearer" and bool(expected)

    async def handle(self, request: Request, stream: Stream) -> Reply:
        if request.path == "/health":
            return json_reply(200, {"ok": True, "version": VERSION})
        if not self.authorised(request):
            return json_reply(401, {"ok": False, "error": "Unauthorized."})
        routes = {"/window": ("GET", self.get_window), "/capture": ("GET", self.get_capture),
                  "/type": ("POST", self.post_type), "/note": ("POST", self.post_note)}
        found = routes.get(request.path)
        if found is None:
            return json_reply(404, {"ok": False, "error": "There is nothing at that address."})
        method, route = found
        if request.method != method:
            return Reply(405, b'{"ok":false,"error":"That method is not allowed here."}', headers=[("Allow", method)])
        return await route(request)

    async def get_window(self, request: Request) -> Reply:
        try:
            found = await asyncio.wait_for(self.window(), WINDOW_SECONDS)
        except Exception as exc:
            if self.log:
                self.log.warning(f"/window failed: {exc!r}")
            found = {"app": None, "width": 0, "height": 0}
        title = found.get("app")
        return json_reply(200, {"wow_focused": isinstance(title, str) and title.startswith(WOW_TITLE),
                                "app": title if isinstance(title, str) else None,
                                "width": int(found.get("width") or 0), "height": int(found.get("height") or 0)})

    async def get_capture(self, request: Request) -> Reply:
        try:
            x, y = _int(request.arg("x", "0"), "x"), _int(request.arg("y", "0"), "y")
            w, h = _int(request.arg("w"), "w", 1), _int(request.arg("h"), "h", 1)
            scale = float(request.arg("scale", "1") or "1")
            if not 0 < scale <= 1:
                raise ValueError("scale must be above 0 and at most 1")
            kind = (request.arg("kind", "jpeg") or "jpeg").lower()
            if kind not in ("ppm", "jpeg"):
                raise ValueError("kind is ppm or jpeg")
        except ValueError as exc:
            return json_reply(400, {"ok": False, "error": str(exc)})
        try:
            found = await asyncio.wait_for(self.capture(x, y, w, h, scale, kind), CAPTURE_SECONDS)
        except Exception as exc:
            if self.log and not isinstance(exc, asyncio.TimeoutError):
                self.log.warning(f"/capture failed: {exc!r}")
            found = None
        if found is None:
            return json_reply(503, {"ok": False, "error": "No picture of the game is available."})
        content_type, data = found
        return Reply(200, data, content_type)

    async def post_type(self, request: Request) -> Reply:
        data = request.json()
        if not isinstance(data, dict) or data.get("approved") is not True:
            return json_reply(400, {"ok": False, "error": "Typing needs the player's approval: approved true."})
        try:
            text = check_text(data.get("text"))
        except ValueError as exc:
            return json_reply(400, {"ok": False, "error": str(exc)})
        if self.typist is None:
            return json_reply(503, {"ok": False, "error": "The Deck cannot type."})
        if self.typist.busy:
            return json_reply(409, {"ok": False, "error": "The Deck is still typing the last reply."})
        try:
            await self.typist.type_chat(text)
        except OSError as exc:
            return json_reply(503, {"ok": False, "error": f"The Deck's keyboard is not available: {exc.strerror or exc}"})
        return json_reply(200, {"ok": True, "typed": len(text)})

    async def post_note(self, request: Request) -> Reply:
        data = request.json()
        if not isinstance(data, dict) or not isinstance(data.get("text"), str):
            return json_reply(400, {"ok": False, "error": "Send the note as {\"text\": ...}."})
        if self.note is None:
            return json_reply(503, {"ok": False, "error": "Notes are not available on this Deck."})
        try:
            n = await self.note(data["text"])
        except NoteError as exc:
            return json_reply(exc.status, {"ok": False, "error": exc.message})
        return json_reply(200, {"ok": True, "n": n})


class OverlayFeed:
    """What the overlay shows, {"state", "text", "draft"}, and the streams that follow it."""

    STATES = ("resting", "listening", "thinking", "speaking", "waiting")

    def __init__(self):
        self.now = {"state": "resting", "text": "", "draft": None}
        self.queues: set[asyncio.Queue] = set()

    def set(self, state: str, text: str, draft: str | None) -> None:
        picture = {"state": state if state in self.STATES else "resting", "text": text or "", "draft": draft}
        if picture == self.now:
            return
        self.now = picture
        for queue in list(self.queues):
            if queue.full():
                try:
                    queue.get_nowait()  # A slow reader skips to the newest picture: each one is whole.
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(dict(picture))


class OverlayServer:
    KEEPALIVE_SECONDS = 15.0

    def __init__(self, feed: OverlayFeed, page_dir: Path, log=None):
        self.feed = feed
        self.page_dir = Path(page_dir)
        self.log = log

    async def handle(self, request: Request, stream: Stream) -> Reply | None:
        if request.method != "GET":
            return json_reply(405, {"ok": False, "error": "Only GET is served here."})
        if request.path == "/overlay/events":
            await self.events(stream)
            return None
        if request.path in ("/overlay", "/overlay/"):
            return self.file("index.html")
        if request.path.startswith("/overlay/"):
            return self.file(request.path[len("/overlay/"):])
        return json_reply(404, {"ok": False, "error": "There is nothing at that address."})

    def file(self, name: str) -> Reply:
        """A file of the page folder, whatever the overlay's author put there. Nothing outside it is served."""
        root = self.page_dir.resolve()
        try:
            path = (root / name).resolve()
            path.relative_to(root)
            data = path.read_bytes() if path.is_file() else None
        except (OSError, ValueError):
            data = None
        if data is None:
            return json_reply(404, {"ok": False, "error": "The overlay page is not there."})
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind in ("application/javascript", "application/json"):
            kind += "; charset=utf-8"
        return Reply(200, data, kind)

    async def events(self, stream: Stream) -> None:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.feed.queues.add(queue)
        try:
            await stream.open()
            stream.writer.write(b"retry: 1000\n\n")
            await stream.send(self.feed.now)
            while True:
                try:
                    picture = await asyncio.wait_for(queue.get(), self.KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    await stream.comment()
                    continue
                await stream.send(picture)
        except (ConnectionError, OSError, asyncio.TimeoutError):
            return
        finally:
            self.feed.queues.discard(queue)


async def serve_agent(agent: DeckAgent, host: str = "0.0.0.0", port: int = AGENT_PORT, log=None) -> Server:
    return await Server(agent.handle, host, port, log).start()


async def serve_overlay(server: OverlayServer, host: str = "127.0.0.1", port: int = OVERLAY_PORT, log=None) -> Server:
    return await Server(server.handle, host, port, log).start()
