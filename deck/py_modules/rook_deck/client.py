"""The Deck as a client of Rook's phone server: pairing, the event stream, requests, recordings and speech.

This follows the phone app, phone/app.js, step for step, so the Deck behaves as a phone does and the server needs
nothing new (desktop/server.py, desktop/session.py; phone/standin.py fakes the same protocol):

- Pairing: POST /pair {"code", "name": "Steam Deck"}; the answer sets the rook_device cookie and names the device.
  The cookie is the Deck's whole credential. It is kept in Decky's settings folder and sent by hand on every request,
  so a cookie the server marks Secure still works over plain http on the home LAN.
- Host and Origin: Rook's server takes a request only when its Host is one it serves and, for a POST, its Origin is
  that same scheme://host:port. Both come from the address the user typed, http://192.168.1.20:47326 by default.
- Attach: GET /snapshot, then GET /events?after=<cursor>. Each stored event carries its sequence number as its SSE id
  and applies once; a live event (data.live) has none and is never checked. A dropped stream reconnects after the
  server's retry (one second) from the last id applied. A refused stream, or an unreachable server, reads the
  snapshot again with a backoff that doubles from one second to fifteen. An "event: snapshot" means the cursor is too
  old: read the whole state again.
- The outbox: a typed request goes out with an id made here and stays in a file until the server answers it; a retry
  reuses the id, so the server never runs it twice. A request older than 20 hours is not sent (the server's record
  remembers ids for a day).
- A recording uploads to POST /audio with X-Rook-Command: <its own id>, and is kept and sent again every three
  seconds while the server cannot take it (5xx, 429, or no answer).
- Speech: "speech" events name pieces of a spoken answer for this device; they play in order, one fetched ahead
  while the one before plays. Stop (or a new recording) mutes the rest of that turn.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from . import httpc
from .audio import RECORD_MIN_SECONDS, AudioError

COOKIE = "rook_device"
DEVICE_NAME = "Steam Deck"
IN_FLIGHT = {"hearing", "queued", "accepted", "handed", "working"}
RUNNING = {"handed", "working"}
OUTBOX_MAX_SECONDS = 20 * 3600
TRAIL_MAX = 60
HISTORY_MAX = 50
OVERLAY_STATE = {"listening": "listening", "transcribing": "thinking", "thinking": "thinking", "speaking": "speaking",
                 "waiting": "waiting"}
ALLOW_WORDS = {"allow", "yes", "approve", "ok", "true", "accept"}
DECLINE_WORDS = {"decline", "no", "deny", "false", "reject"}


class Unpaired(Exception):
    """The server answered 401: it no longer knows this Deck."""


@dataclass
class SseEvent:
    kind: str
    data: str
    id: str | None


class SseParser:
    """Server-sent events, as a browser's EventSource reads them: lines of field: value, a blank line ends one."""

    def __init__(self):
        self.buffer = b""
        self.kind = ""
        self.data: list[str] = []
        self.id: str | None = None
        self.retry: int | None = None

    def feed(self, chunk: bytes) -> list[SseEvent]:
        self.buffer += chunk
        out = []
        while True:
            cut = min((i for i in (self.buffer.find(b"\n"), self.buffer.find(b"\r")) if i >= 0), default=-1)
            if cut < 0:
                return out
            line = self.buffer[:cut].decode("utf-8", errors="replace")
            skip = 2 if self.buffer[cut:cut + 2] == b"\r\n" else 1
            self.buffer = self.buffer[cut + skip:]
            if not line:
                if self.data:
                    out.append(SseEvent(self.kind or "message", "\n".join(self.data), self.id))
                self.kind, self.data = "", []
                continue
            if line.startswith(":"):
                continue
            name, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if name == "event":
                self.kind = value
            elif name == "data":
                self.data.append(value)
            elif name == "id":
                self.id = value or None
            elif name == "retry" and value.isdigit():
                self.retry = int(value)


def plain_words(text: str) -> str:
    """An answer as plain words, for the overlay: no code fences, list marks or markdown signs (phone/app.js)."""
    import re
    text = re.sub(r"```[\s\S]*?(?:```|$)", " ", str(text))
    text = re.sub(r"(?m)^\s*(?:[-*•]|\d+[.)]|#+)\s+", "", text)
    return text.replace("`", "").replace("**", "")


@dataclass
class Voice:
    phase: str = "idle"  # idle, recording, uploading
    pending: dict | None = None  # {"id", "data", "type", "at"}: a recording the server has not taken yet.
    playing: bool = False
    queue: dict | None = None  # {"turn", "next", "pieces": {index: event}}
    muted: set = field(default_factory=set)
    old: set = field(default_factory=set)
    failed_turn: str | None = None


class RookClient:
    RETRY_SECONDS = 3.0  # A request or recording the server could not take goes again after this.
    BACKOFF_START, BACKOFF_MAX = 1.0, 15.0
    STREAM_RETRY_SECONDS = 1.0  # The server's own "retry: 1000".
    REQUEST_SECONDS = 15.0
    AUDIO_SECONDS = 60.0

    def __init__(self, store, emit: Callable[[dict], Awaitable[None] | None], *, recorder=None, player=None, log=None,
                 on_overlay: Callable[[str, str, str | None], None] | None = None, device_name: str = DEVICE_NAME):
        self.store = store
        self.emit_cb = emit
        self.recorder = recorder
        self.player = player
        self.log = log
        self.on_overlay = on_overlay
        self.device_name = device_name
        self.base: httpc.Base | None = None
        url = store.get("server_url")
        if url:
            try:
                self.base = httpc.parse_base(url)
            except ValueError:
                self.base = None
        self.cookie: str | None = store.get("cookie")
        self.device: dict | None = store.get("device")
        self.exchanges: list[dict] = []
        self.outbox: list[dict] = store.load_outbox()
        for msg in self.outbox:
            self.exchanges.append({"key": f"c:{msg['id']}", "cmd": msg["id"], "text": msg.get("text", ""),
                                   "at": msg.get("at", time.time()), "phase": "offline", "voice": msg.get("voice")})
        self.card: dict | None = None
        self.rook = "resting"
        self.dark = False
        self.held = None
        self.activity: dict[str, list[dict]] = {}
        self.drafts: dict[str, str] = {}
        self.last_id = 0
        self.connected = False
        self.backoff = self.BACKOFF_START
        self.voice = Voice()
        self.stops: dict[str, str] = {}
        self.sending: set[str] = set()
        self.error: str | None = None
        self.stream_starts = 0  # How many times the event stream opened, for the status and the tests.
        self._task: asyncio.Task | None = None
        self._retry: asyncio.TimerHandle | None = None
        self._audio_retry: asyncio.TimerHandle | None = None
        self._speech_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._mood = None
        self._overlay = None
        self._uploading = False

    # Lifecycle.
    @property
    def paired(self) -> bool:
        return bool(self.cookie and self.base)

    def start(self) -> None:
        if self.paired and (self._task is None or self._task.done()):
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def close(self) -> None:
        for handle in (self._retry, self._audio_retry):
            if handle:
                handle.cancel()
        tasks = [t for t in (self._task, self._speech_task, *self._tasks) if t and not t.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.player:
            await self.player.stop()
        if self.recorder and self.recorder.recording:
            await self.recorder.cancel()

    def _spawn(self, coro) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def emit(self, event: dict) -> None:
        try:
            result = self.emit_cb(event)
            if asyncio.iscoroutine(result):
                self._spawn(result)
        except Exception as exc:
            if self.log:
                self.log.warning(f"emit failed: {exc!r}")

    def fail(self, message: str) -> None:
        self.error = message
        self.emit({"type": "error", "message": message})

    # Requests to the server.
    def _headers(self, post: bool = False) -> dict[str, str]:
        headers = {"Cookie": f"{COOKIE}={self.cookie}"} if self.cookie else {}
        if post:
            headers["Origin"] = self.base.origin
        return headers

    async def _call(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None,
                    timeout: float | None = None) -> httpc.Response:
        if not self.base:
            raise Unpaired()
        all_headers = {**self._headers(post=method == "POST"), **(headers or {})}
        response = await httpc.request(self.base, method, path, headers=all_headers, body=body,
                                       timeout=timeout or self.REQUEST_SECONDS)
        if response.status == 401 and path != "/pair":
            self._unpaired()
            raise Unpaired()
        return response

    async def _post_json(self, path: str, payload: dict) -> httpc.Response:
        return await self._call("POST", path, json.dumps(payload).encode(), {"Content-Type": "application/json"})

    def _unpaired(self) -> None:
        if self.cookie:
            self.cookie = None
            self.store.set(cookie=None)
            self.connected = False
            self.fail("Rook no longer knows this Deck. Pair it again with a new code.")
            self.emit({"type": "state", "paired": False, "connected": False, "state": self.mood()})

    # Pairing.
    async def pair(self, server_url: str, code: str) -> dict:
        try:
            base = httpc.parse_base(server_url)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        clean = "".join(str(code or "").split())
        if not clean:
            return {"ok": False, "error": "Enter the pairing code from Rook."}
        await self.close()
        self.base, self.cookie = base, None
        try:
            response = await httpc.request(base, "POST", "/pair", body=json.dumps(
                {"code": clean, "name": self.device_name}).encode(), headers={
                "Content-Type": "application/json", "Origin": base.origin}, timeout=self.REQUEST_SECONDS)
        except httpc.HttpError:
            return {"ok": False, "error": f"Rook did not answer at {base.url}. Check the address and that the Deck "
                                          "is on the same network."}
        data = response.json()
        token = httpc.cookie_from(response, COOKIE)
        if response.status != 200 or not data.get("ok") or not token:
            if response.status == 403:
                return {"ok": False, "error": "Rook refused this address. Use the address Rook's settings show for "
                                              "LAN devices."}
            return {"ok": False, "error": data.get("error") or "That code is wrong or has expired. Ask Rook for a "
                                                                 "new one."}
        device = data.get("device") if isinstance(data.get("device"), dict) else {"name": self.device_name}
        self.cookie, self.device = token, device
        self.store.set(server_url=base.url, cookie=token, device=device)
        self.exchanges = [x for x in self.exchanges if x.get("cmd") and not x.get("turn")]
        self.last_id, self.card, self.error = 0, None, None
        self.backoff = self.BACKOFF_START
        self.emit({"type": "state", "paired": True, "connected": False, "state": self.mood()})
        self.start()
        return {"ok": True, "device": device}

    async def unpair(self) -> dict:
        await self.close()
        self.cookie, self.device, self.connected = None, None, False
        self.outbox, self.exchanges, self.card = [], [], None
        self.voice.pending = None
        self.store.set(cookie=None, device=None)
        self.store.save_outbox([])
        self.emit({"type": "state", "paired": False, "connected": False, "state": self.mood()})
        return {"ok": True}

    # The stream.
    async def _run(self) -> None:
        while self.paired:
            try:
                response = await self._call("GET", "/snapshot")
                if response.status != 200:
                    raise httpc.HttpError(f"snapshot answered {response.status}")
                self.apply_snapshot(response.json())
                self.changed()
                while self.paired:
                    reread = await self._stream_once()
                    if reread:
                        break  # The cursor was too old, or the stream was refused: read the snapshot again.
                    await asyncio.sleep(self.STREAM_RETRY_SECONDS)
                if not self.paired:
                    return
            except Unpaired:
                return
            except asyncio.CancelledError:
                raise
            except (httpc.HttpError, OSError, ValueError) as exc:
                if self.log:
                    self.log.info(f"Rook is out of reach: {exc}")
            self.set_connected(False)
            await asyncio.sleep(self.backoff)
            self.backoff = min(self.backoff * 2, self.BACKOFF_MAX)

    async def _stream_once(self) -> bool:
        """One stream, from open to end. Returns True when the snapshot must be read again."""
        headers = {**self._headers(), "Accept": "text/event-stream"}
        try:
            async with httpc.Stream(self.base, f"/events?after={self.last_id}", headers) as stream:
                if stream.status == 401:
                    self._unpaired()
                    raise Unpaired()
                if stream.status != 200:
                    await stream.read_all()
                    raise httpc.HttpError(f"the event stream was refused ({stream.status})")
                self.backoff = self.BACKOFF_START
                self.stream_starts += 1
                self.set_connected(True)
                self.flush()
                self._spawn(self.upload_pending())
                parser = SseParser()
                async for chunk in stream.chunks():
                    for event in parser.feed(chunk):
                        if event.kind == "snapshot":
                            return True
                        self.on_event(event)
        except (httpc.HttpError, OSError, asyncio.IncompleteReadError) as exc:
            if self.connected:
                self.set_connected(False)
                return False  # A drop: reconnect from the last id, as a browser does.
            raise httpc.HttpError(str(exc)) from exc
        self.set_connected(False)
        return False

    def set_connected(self, up: bool) -> None:
        if up == self.connected:
            return
        self.connected = up
        for x in self.exchanges:
            if x.get("cmd") and not x.get("turn") and x.get("phase") != "failed":
                x["phase"] = "sending" if up else "offline"
        self.changed(force=True)

    def apply_snapshot(self, s: dict) -> None:
        try:
            self.last_id = int(s.get("cursor") or 0)
        except (TypeError, ValueError):
            self.last_id = 0
        state = s.get("state")
        self.rook = (state.get("state") if isinstance(state, dict) else state) or "resting"
        self.dark = bool(s.get("dark"))
        self.held = s.get("held")
        self.card = s.get("card") or None
        local = [x for x in self.exchanges if x.get("cmd") and not x.get("turn")]
        self.exchanges = [self.from_request(r) for r in s.get("requests") or [] if isinstance(r, dict)] + local
        running = next((x["turn"] for x in reversed(self.exchanges) if x.get("turn") and x.get("state") in IN_FLIGHT),
                       None)
        fresh: dict[str, list] = {}
        for step in s.get("activity") or []:
            if isinstance(step, dict) and (step.get("turn") or running):
                fresh.setdefault(step.get("turn") or running, []).append(self.step(step))
        self.activity.update({turn: steps[-TRAIL_MAX:] for turn, steps in fresh.items()})
        self.emit({"type": "card", "card": self.card})

    @staticmethod
    def from_request(r: dict) -> dict:
        return {"key": f"t:{r.get('turn')}", "turn": r.get("turn"), "text": r.get("text") or "",
                "state": r.get("state"), "answer": r.get("answer"), "at": r.get("at") or time.time(),
                "client": r.get("client"), "source": r.get("source")}

    @staticmethod
    def step(d: dict) -> dict:
        return {k: d.get(k) for k in ("kind", "label", "detail", "icon")}

    def find(self, turn) -> dict | None:
        return next((x for x in self.exchanges if turn and x.get("turn") == turn), None)

    def on_event(self, event: SseEvent) -> None:
        try:
            data = json.loads(event.data)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        if not data.get("live") and event.id:
            try:
                seq = int(event.id)
            except ValueError:
                seq = None
            if seq is not None:
                if seq <= self.last_id:
                    return  # Applied already.
                self.last_id = seq
        handler = getattr(self, f"on_{event.kind}", None)
        if handler is not None:
            handler(data)
        self.changed()

    # Events, as phone/app.js's APPLY.
    def on_request(self, d: dict) -> None:
        turn = d.get("turn")
        if d.get("state") == "empty":
            self.exchanges = [x for x in self.exchanges if x.get("turn") != turn]
            self.fail("That did not go through. Say it again." if d.get("reason") == "failed"
                      else "Rook heard no words in that recording.")
            return
        x = self.find(turn)
        if x is None:
            # The event can beat the post's own answer: adopt the request the Deck is still sending.
            x = next((e for e in self.exchanges if e.get("cmd") and not e.get("turn") and e.get("text") == d.get("text")),
                     None)
            if x is not None:
                x["turn"] = turn
        if x is None:
            x = self.from_request(d)
            self.exchanges.append(x)
        x["phase"] = None
        x["state"] = d.get("state") or x.get("state")
        if "text" in d:
            x["text"] = d["text"]
        if "answer" in d:
            x["answer"] = d["answer"]
        if x.get("answer") or x.get("state") not in IN_FLIGHT:
            self.drafts.pop(turn, None)
        if d.get("answer"):
            self.emit({"type": "answer", "turn": turn, "text": d["answer"], "request": x.get("text")})
        elif x.get("state") not in IN_FLIGHT:
            self.emit({"type": "state", "state": self.mood(), "turn": turn, "request_state": x.get("state")})

    def on_activity(self, d: dict) -> None:
        turn = d.get("turn")
        if not turn:
            return
        steps = self.activity.setdefault(turn, [])
        steps.append(self.step(d))
        del steps[:-TRAIL_MAX]
        self.drafts.pop(turn, None)  # A tool call clears the answer so far.
        self.emit({"type": "activity", "turn": turn, **self.step(d)})

    def on_draft(self, d: dict) -> None:
        turn = d.get("turn")
        if not turn:
            return
        x = self.find(turn)
        if x and x.get("answer"):
            return  # The final answer has arrived; a late draft never covers it.
        if d.get("text"):
            self.drafts[turn] = d["text"]
        else:
            self.drafts.pop(turn, None)
        self.emit({"type": "draft", "turn": turn, "text": d.get("text") or None, "request": x and x.get("text")})

    def on_card(self, d: dict) -> None:
        if d.get("state") == "resolved":
            if self.card and self.card.get("id") == d.get("id"):
                self.card = None
            self.emit({"type": "card", "card": None, "id": d.get("id"), "state": "resolved"})
            return
        if not self.card or self.card.get("id") != d.get("id") or d.get("live"):
            # A live card carries its full words. A stored one, replayed, keeps only a summary: read the snapshot.
            self.card = d
            if not d.get("live") and not d.get("desk"):
                self._spawn(self.whole_card(d.get("id")))
            self.emit({"type": "card", "card": self.card})

    def on_state(self, d: dict) -> None:
        if "state" in d:
            self.rook = d["state"]
        if "dark" in d:
            self.dark = bool(d["dark"])
        if "held" in d:
            self.held = d["held"]

    def on_speech(self, d: dict) -> None:
        self.hear_speech(d)

    def on_chat(self, d: dict) -> None:
        self.emit({"type": "chat", **{k: d.get(k) for k in ("sender", "text", "channel")}})

    async def whole_card(self, card_id) -> None:
        try:
            response = await self._call("GET", "/snapshot")
        except (Unpaired, httpc.HttpError):
            return
        card = response.json().get("card") if response.status == 200 else None
        if isinstance(card, dict) and card.get("id") == card_id and self.card and self.card.get("id") == card_id:
            self.card = card
            self.emit({"type": "card", "card": card})

    # Presence.
    def running_turn(self) -> str | None:
        live = [x for x in self.exchanges if x.get("turn") and not x.get("answer") and (
            x.get("state") in RUNNING or (x.get("state") in IN_FLIGHT and x["turn"] in self.activity))]
        return live[-1]["turn"] if live else None

    def mood(self) -> str:
        """Rook's presence on the Deck, as phone/app.js presenceMood() works it out."""
        if self.voice.phase == "recording":
            return "listening"
        heard = any(x.get("state") == "hearing" or (x.get("voice") and x.get("cmd") and not x.get("text")
                                                     and x.get("phase") != "failed"
                                                     and (x.get("phase") or x.get("state") in IN_FLIGHT))
                    for x in self.exchanges)
        if self.voice.phase == "uploading" or heard:
            return "transcribing"
        if self.voice.playing:
            return "speaking"
        if self.card:
            return "waiting"
        if self.paired and not self.connected:
            return "away"
        turn = self.running_turn()
        if turn and self.activity.get(turn) and self.rook != "speaking":
            return "thinking"
        if self.rook in ("listening", "transcribing", "speaking", "thinking", "error"):
            return self.rook
        return "dark" if self.dark else "resting"

    def newest(self) -> dict | None:
        return max(self.exchanges, key=lambda x: x.get("at") or 0, default=None)

    def changed(self, force: bool = False) -> None:
        """After any change: tell the frontend a new mood, and give the overlay its whole new picture."""
        mood = self.mood()
        if mood != self._mood or force:
            self._mood = mood
            self.emit({"type": "state", "state": mood, "connected": self.connected, "paired": self.paired,
                       "talking": self.voice.phase == "recording"})
        x = self.newest()
        draft = self.drafts.get(x.get("turn")) if x and x.get("turn") and not x.get("answer") else None
        text = plain_words(x.get("answer") or draft or "") if x else ""
        picture = (OVERLAY_STATE.get(mood, "resting"), text.strip(), None)
        if picture != self._overlay and self.on_overlay:
            self._overlay = picture
            self.on_overlay(*picture)

    # Typed requests.
    def save_outbox(self) -> None:
        self.store.save_outbox(self.outbox)

    async def send_text(self, text: str) -> dict:
        words = str(text or "").strip()
        if not words:
            return {"ok": False, "error": "Type a request first."}
        if not self.paired:
            return {"ok": False, "error": "Pair the Deck with Rook first."}
        msg = {"id": str(uuid.uuid4()), "text": words, "at": time.time()}
        if self.store.get("typed_aloud"):
            msg["voice"] = True
        self.outbox.append(msg)
        self.save_outbox()
        self.exchanges.append({"key": f"c:{msg['id']}", "cmd": msg["id"], "text": words, "at": msg["at"],
                               "phase": "sending" if self.connected else "offline", "voice": msg.get("voice")})
        self.changed()
        self.flush()
        return {"ok": True, "id": msg["id"], "queued": not self.connected}

    def flush(self) -> None:
        if self.connected:
            self._spawn(self._flush())

    async def _flush(self) -> None:
        for msg in list(self.outbox):
            if msg["id"] in self.sending or not self.connected:
                continue
            x = next((e for e in self.exchanges if e.get("cmd") == msg["id"]), None)
            if time.time() - msg.get("at", 0) > OUTBOX_MAX_SECONDS:  # Too old to send safely: the owner decides.
                self.outbox = [m for m in self.outbox if m["id"] != msg["id"]]
                self.save_outbox()
                if x:
                    x.update(phase="failed", old=True, error="Not sent: too old. Send it again.")
                continue
            self.sending.add(msg["id"])
            try:
                command = {"id": msg["id"], "kind": "ask", "text": msg["text"], "mode": "queue", "at": msg["at"]}
                if msg.get("voice"):
                    command["voice"] = True
                response = await self._post_json("/command", command)
                if response.status >= 500:
                    raise httpc.HttpError("server")
                data = response.json()
                self.outbox = [m for m in self.outbox if m["id"] != msg["id"]]
                self.save_outbox()
                if x and data.get("ok"):
                    twin = next((e for e in self.exchanges if e.get("turn") == data.get("turn") and e is not x), None)
                    if twin:
                        self.exchanges = [e for e in self.exchanges if e is not x]
                    else:
                        x.update(turn=data.get("turn"), phase=None, state=x.get("state") or "accepted")
                elif x:
                    x.update(phase="failed", error=data.get("error"))
                    self.fail(f"Rook did not take that request. {data.get('error') or ''}".strip())
            except Unpaired:
                return
            except (httpc.HttpError, OSError):
                self._schedule_flush()
            finally:
                self.sending.discard(msg["id"])
            self.changed()

    def _schedule_flush(self) -> None:
        if self._retry:
            self._retry.cancel()
        self._retry = asyncio.get_running_loop().call_later(self.RETRY_SECONDS, self.flush)

    # Voice in.
    async def talk_start(self) -> dict:
        if not self.paired:
            return {"ok": False, "error": "Pair the Deck with Rook first."}
        if self.recorder is None:
            return {"ok": False, "error": "This Deck cannot record."}
        if self.voice.phase == "recording":
            return {"ok": True}
        if self.voice.playing or self.voice.queue:
            await self.stop_speech()  # Talking over Rook stops it at once, as the desk's talk key does.
        try:
            await self.recorder.start()
        except AudioError as exc:
            self.fail(str(exc))
            return {"ok": False, "error": str(exc)}
        self.voice.phase = "recording"
        self.changed()
        return {"ok": True}

    async def talk_stop(self) -> dict:
        if self.voice.phase != "recording" or self.recorder is None:
            return {"ok": True, "sent": False}
        self.voice.phase = "uploading"
        self.changed()
        recording = await self.recorder.stop()
        if recording is None or recording.seconds < RECORD_MIN_SECONDS or not recording.data:
            self.voice.phase = "idle"
            self.changed()
            self.fail("That was too short to hear. Hold the talk button while you speak.")
            return {"ok": False, "error": "too short"}
        command_id = str(uuid.uuid4())
        self.voice.pending = {"id": command_id, "data": recording.data, "type": recording.content_type,
                              "at": time.time()}
        self.exchanges.append({"key": f"c:{command_id}", "cmd": command_id, "voice": True, "text": "",
                               "at": self.voice.pending["at"], "phase": "sending"})
        self.changed()
        await self.upload_pending()
        return {"ok": True, "sent": True, "id": command_id}

    async def upload_pending(self) -> None:
        job = self.voice.pending
        if not job or self.voice.phase == "recording" or self._uploading:
            return
        self._uploading = True
        self.voice.phase = "uploading"
        x = next((e for e in self.exchanges if e.get("cmd") == job["id"]), None)
        try:
            response = await self._call("POST", "/audio", job["data"], {
                "Content-Type": job["type"], "X-Rook-Command": job["id"]}, timeout=self.AUDIO_SECONDS)
            data = response.json()
            if response.status == 429:
                self.fail(data.get("error") or "Rook is still hearing your last recording.")
                raise httpc.HttpError("busy")
            if response.status >= 500:
                raise httpc.HttpError("server")
            self.voice.pending = None
            if x and data.get("ok"):
                twin = next((e for e in self.exchanges if e.get("turn") == data.get("turn") and e is not x), None)
                if twin:
                    twin["voice"] = True
                    self.exchanges = [e for e in self.exchanges if e is not x]
                else:
                    x.update(turn=data.get("turn"), phase=None, state=x.get("state") or "accepted")
            elif x:
                x.update(phase="failed", error=data.get("error") or "Rook did not take the recording.")
                self.fail(x["error"])
        except Unpaired:
            pass
        except (httpc.HttpError, OSError):
            # Kept, with its id, and sent again once Rook answers: the server runs one command id once.
            if self._audio_retry:
                self._audio_retry.cancel()
            self._audio_retry = asyncio.get_running_loop().call_later(
                self.RETRY_SECONDS, lambda: self._spawn(self.upload_pending()))
        finally:
            self._uploading = False
            if not self.voice.pending and self.voice.phase == "uploading":
                self.voice.phase = "idle"
            self.changed()

    # Voice out.
    def is_older_turn(self, turn) -> bool:
        if turn in self.voice.old:
            return True
        mine = self.find(turn)
        return bool(mine and any(e.get("turn") and e["turn"] != turn and (e.get("at") or 0) > (mine.get("at") or 0)
                                 for e in self.exchanges))

    def hear_speech(self, d: dict) -> None:
        me = (self.device or {}).get("id")
        turn = d.get("turn")
        if (not turn or not d.get("id") or not me or d.get("device") != me or turn in self.voice.muted
                or self.voice.failed_turn == turn or self.is_older_turn(turn) or self.player is None):
            return
        queue = self.voice.queue
        if not queue or queue["turn"] != turn:
            if queue:
                self.voice.old.add(queue["turn"])
            self._cut_speech()
            queue = self.voice.queue = {"turn": turn, "next": 0, "pieces": {}}
        index = d.get("index")
        if isinstance(index, int) and not isinstance(index, bool) and index >= queue["next"]:
            queue["pieces"][index] = d
        if self._speech_task is None or self._speech_task.done():
            self._speech_task = asyncio.get_running_loop().create_task(self._play_queue(queue))

    async def fetch_speech(self, piece: dict) -> tuple[str, bytes] | None:
        response = await self._call("GET", f"/speech/{piece['id']}")
        if response.status not in (200, 206):
            return None
        return (response.header("content-type") or "audio/wav").split(";")[0].strip(), response.body

    async def _play_queue(self, queue: dict) -> None:
        ahead: dict[int, asyncio.Task] = {}
        try:
            while self.voice.queue is queue:
                piece = queue["pieces"].get(queue["next"])
                if piece is None:
                    # Speech may still be on its way; the presence settles after a short pause with nothing to play.
                    for _ in range(7):
                        await asyncio.sleep(0.1)
                        if queue["pieces"].get(queue["next"]):
                            break
                    else:
                        return
                    continue
                task = ahead.pop(queue["next"], None) or asyncio.get_running_loop().create_task(self.fetch_speech(piece))
                clip = await task
                after = queue["pieces"].get(queue["next"] + 1)
                if after and queue["next"] + 1 not in ahead:  # The next piece loads while this one plays.
                    ahead[queue["next"] + 1] = asyncio.get_running_loop().create_task(self.fetch_speech(after))
                if clip is None:
                    raise httpc.HttpError("that piece of speech is gone")
                self.voice.playing = True
                self.changed()
                played = await self.player.play(clip[1], clip[0])
                if self.voice.queue is not queue:
                    return
                if not played and not self.player.stopped:
                    raise httpc.HttpError("the speech did not play")
                queue["pieces"].pop(queue["next"], None)
                queue["next"] += 1
        except (httpc.HttpError, Unpaired, OSError):
            self.voice.failed_turn = queue["turn"]
            self.fail("Rook's voice did not play on the Deck. The answer is in the Rook panel as text.")
        finally:
            for task in ahead.values():
                task.cancel()
            if self.voice.queue is queue:
                self.voice.queue = None
            self.voice.playing = False
            self.changed()

    def _cut_speech(self) -> None:
        self.voice.queue = None
        if self._speech_task and not self._speech_task.done():
            self._speech_task.cancel()
        if self.player:
            self._spawn(self.player.stop())
        self.voice.playing = False

    async def stop_speech(self, mute: bool = True) -> None:
        if mute and self.voice.queue:
            self.voice.muted.add(self.voice.queue["turn"])
        self._cut_speech()
        if self.player:
            await self.player.stop()
        self.changed()

    # Stop and cards.
    async def stop(self) -> dict:
        """The Deck's stop: silence Rook's speech here, and stop the running turn, as the phone's Stop does."""
        speaking = bool(self.voice.playing or self.voice.queue)
        await self.stop_speech()
        if self.voice.phase == "recording" and self.recorder:
            await self.recorder.cancel()
            self.voice.phase = "idle"
            self.changed()
        turn = self.running_turn()
        if not turn or self.stops.get(turn) == "stale":
            return {"ok": True, "stopped_speech": speaking, "stopped_turn": False}
        try:
            response = await self._post_json("/command", {"id": str(uuid.uuid4()), "kind": "stop", "turn": turn})
        except Unpaired:
            return {"ok": False, "error": "Pair the Deck with Rook first."}
        except httpc.HttpError:
            return {"ok": False, "error": "The stop did not reach Rook. Try again."}
        data = response.json()
        if data.get("ok"):
            self.stops[turn] = "sent"
            return {"ok": True, "stopped_speech": speaking, "stopped_turn": True}
        if data.get("error") == "stale":
            self.stops[turn] = "stale"
            return {"ok": True, "stopped_speech": speaking, "stopped_turn": False}
        return {"ok": False, "error": data.get("error") or "Rook did not take the stop."}

    async def answer_card(self, card_id: str, option) -> dict:
        """Answer the waiting card. option is "allow" or "decline" (or yes/no, true/false), as the phone's two
        buttons; a question with options is answered at the desk in this release, as on the phone."""
        word = str(option).strip().lower() if not isinstance(option, bool) else ("allow" if option else "decline")
        if word in ALLOW_WORDS:
            allow = True
        elif word in DECLINE_WORDS:
            allow = False
        else:
            return {"ok": False, "error": "Answer this one at your desk: the Deck answers Allow or Decline."}
        if self.card and self.card.get("id") == card_id and self.card.get("desk"):
            return {"ok": False, "error": "Answer this one at your desk."}
        try:
            response = await self._post_json("/command", {"id": str(uuid.uuid4()), "kind": "card", "card": card_id,
                                                          "allow": allow, "answers": {}})
        except Unpaired:
            return {"ok": False, "error": "Pair the Deck with Rook first."}
        except httpc.HttpError:
            return {"ok": False, "error": "The answer did not reach Rook. Try again."}
        data = response.json()
        if data.get("ok") or data.get("error") == "stale":
            if self.card and self.card.get("id") == card_id:
                self.card = None
                self.emit({"type": "card", "card": None, "id": card_id, "state": "resolved"})
                self.changed()
            if data.get("error") == "stale":
                return {"ok": True, "stale": True, "note": "That card had already closed, so nothing changed."}
            return {"ok": True}
        return {"ok": False, "error": data.get("error") or "Rook did not take the answer. Try again."}

    # Reads for the frontend.
    def history(self) -> list[dict]:
        items = sorted(self.exchanges, key=lambda x: x.get("at") or 0)[-HISTORY_MAX:]
        out = []
        for x in items:
            turn = x.get("turn")
            out.append({"id": turn or x.get("cmd"), "turn": turn, "request": x.get("text") or "",
                        "text": x.get("text") or "", "answer": x.get("answer"),
                        "draft": self.drafts.get(turn) if turn else None,
                        "state": x.get("phase") or x.get("state"), "at": x.get("at"),
                        "source": "spoken" if x.get("voice") else x.get("source"), "client": x.get("client"),
                        "error": x.get("error"), "activity": list(self.activity.get(turn, [])) if turn else []})
        return out

    def current_draft(self) -> str | None:
        turn = self.running_turn()
        return self.drafts.get(turn) if turn else None
