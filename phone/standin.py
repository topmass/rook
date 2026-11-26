"""A stand-in for Rook's phone server, protocol versions 1 to 3, for development and for phone/check.py only.

It serves the app in phone/ and fakes the protocol from fixtures, with the standard library only. It listens on
127.0.0.1 on a free port and prints the address. It holds nothing real: no socket to Rook, no state on disk.

    python phone/standin.py [--port N] [--scene empty|full]

The pairing code is 418207. A request whose text has the word "card" opens a permission card first. A recording
sent to POST /audio is heard as a fixed sentence. Every request then plays a scripted turn: four steps of activity,
the answer so far between them, and the final answer, spread over the answer delay. A stop command ends the turn
where it is. A spoken request, or a typed one with "voice", ends with three pieces of speech: short tones made in
code, served at GET /speech/<id>. The app's own rules (the cookie, Origin, JSON bodies) are checked as the real
server will check them. POST /__test drives the fake for the check: see Fake.test.
"""

import argparse
import hashlib
import http.server
import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
FILES = {"/": "index.html", "/app.css": "app.css", "/app.js": "app.js", "/presence.js": "presence.js",
         "/forms.json": "forms.json", "/icon.svg": "icon.svg", "/manifest.webmanifest": "manifest.webmanifest"}
# The stage's own files, served from the repo's stage folder as the real server serves them.
FILES.update({"/stage/stage.js": "../stage/stage.js", "/stage/stage.css": "../stage/stage.css",
              "/stage/art/rook-dust.js": "../stage/art/rook-dust.js", "/stage/art/nova-rook.png": "../stage/art/nova-rook.png"})
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
         ".js": "text/javascript; charset=utf-8", ".webmanifest": "application/manifest+json",
         ".json": "application/json", ".png": "image/png", ".webp": "image/webp"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
       "media-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/mp4")
AUDIO_MAX = 4 * 1024 * 1024
HEARD = "What is on my calendar this afternoon?"  # The words the stand-in "hears" in any recording.
SPOKEN = ["You have two things this afternoon.", "A call with Dana at three thirty.", "Then the shop closes at six."]


def tone(seconds, pitch, rate=16000):
    """A short sine tone as 16-bit mono WAV: the stand-in's speech, made in code."""
    import math
    import struct
    n = int(seconds * rate)
    frames = b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * pitch * k / rate)
                                                * min(1.0, k / 400, (n - k) / 400))) for k in range(n))
    return (b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate,
            rate * 2, 2, 16) + b"data" + struct.pack("<I", len(frames)) + frames)
CODE = "418207"
COOKIE = "rook_device"

LONG_ANSWER = """The phone build is on its branch and its check passes.

Here is what changed today:
- The pairing screen takes a one-use code and names the phone.
- Requests from the phone queue behind the running turn, so nothing at the desk is cut off.
- A permission card shows on the phone, and `Allow` sends the card's own id with the answer.

Run `python phone/check.py` to see it pass. The stand-in listens on `127.0.0.1` only.

**Not tested yet:** a real phone over Tailscale."""

# A scripted turn's steps, one of each kind a turn often has, as Rook's activity events carry them.
STEPS = [
    {"kind": "thinking", "label": "Thinking about what you asked."},
    {"kind": "reading", "label": "Reading the phone app's script.", "detail": "phone/app.js"},
    {"kind": "running", "label": "Running the phone app's check.", "detail": "scripts/capped python3 phone/check.py"},
    {"kind": "sending", "label": "Sending this to the Opus build thread.", "detail": "Rook build (Opus)"},
]
ANSWER_TAIL = ("The phone now shows each step as Rook takes it. When the answer arrives, the steps fold into one "
               "line that opens again.")

WORK = [
    {"id": 14, "project": "rook", "wish": "Build the phone's web app, first release.", "state": "waiting",
     "news": "It asks whether the work list should open from the state line.", "try": None},
    {"id": 12, "project": "dashboards", "wish": "Fix the estimate total that drops tax on a split invoice.",
     "state": "done", "news": "The fix is merged and the staging total matches.", "try": "Open estimate 4113 on staging."},
    {"id": 11, "project": "rook", "wish": "Make restarts wait for a quiet moment.", "state": "live",
     "news": "It is live since 9:40 AM.", "try": "relay.py restart"},
    {"id": 15, "project": "gw2-tp", "wish": "Find three crafting margins above 15 percent after fees.",
     "state": "running", "news": "It is reading the order books.", "try": None},
]


def fixture_requests(scene, now):
    if scene == "empty":
        return []
    return [
        {"turn": "t-101", "source": "spoken", "client": "desktop", "text": "What time is my call with Dana?",
         "state": "closed", "answer": "Your call with Dana is at 3:30 PM. It is in the calendar as a video call.",
         "at": now - 3600},
        {"turn": "t-102", "source": "typed", "client": "dev-phone", "text": "How did the phone build go?",
         "state": "closed", "answer": LONG_ANSWER, "at": now - 600},
    ]


class Fake:
    """The fake session: an event log with ids, requests, a card, the work list and the command record."""

    def __init__(self, scene):
        now = time.time()
        self.lock = threading.Condition()
        self.events = []  # (seq, kind, data)
        self.seq = 100
        self.requests = {r["turn"]: r for r in fixture_requests(scene, now)}
        self.card = None
        self.state = "resting"
        self.tokens = set()
        self.commands = {}  # (token hash, id) -> (fingerprint, result)
        self.turns = 102
        self.answer_delay = 1.2
        self.refuse_streams = False
        self.drop_next_reply = False
        self.stream_starts = []  # The cursor each stream started from, for the check.
        self.command_ids = []  # Every ask command id received, retries included.
        self.card_answers = []
        self.generation = 0  # Raised to cut every open stream.
        self.activity = {}  # turn -> the running turn's activity lines, for the snapshot
        self.stopped = set()
        self.hold = False  # True holds a scripted turn after its fourth step, until the check lets it go.
        self.stop_commands = []
        self.ask_voice = []  # Whether each ask carried voice: true.
        self.audio_uploads = []  # (command id, content type, bytes) for every upload, retries included.
        self.speech = {}  # id -> WAV bytes
        self.tone_seconds = 0.35
        self.drop_next_audio = False
        self.empty_next_audio = False
        self.busy_next_audio = False

    def emit(self, kind, data, seq=None, live=False):
        """Log an event. A live one has no id, as Rook's state has none: it is never stored or replayed."""
        with self.lock:
            if live:
                seq = None
            elif seq is None:
                self.seq += 1
                seq = self.seq
            self.events.append((seq, kind, data))
            self.lock.notify_all()
        return seq

    def snapshot(self):
        with self.lock:
            requests = sorted(self.requests.values(), key=lambda r: r["at"])[-20:]
            activity = [step for steps in self.activity.values() for step in steps[-8:]]
            return {"cursor": self.seq, "state": self.state, "requests": requests, "card": self.card, "notices": [],
                    "activity": activity,
                    "work": WORK, "mailbox": {"open": 0, "items": []}, "dark": False, "focus": None, "restart": None}

    def set_state(self, state):
        self.state = state
        self.emit("state", {"state": state, "live": True}, live=True)

    def ask(self, text, voice=False, recording=None):
        """A typed request, or with recording a spoken one: the words arrive once the fake recogniser has heard them,
        and a recording marked empty ends with no words. A spoken request, or one with voice, is answered aloud."""
        spoken = recording is not None
        with self.lock:
            self.turns += 1
            turn = f"t-{self.turns}"
            self.requests[turn] = {"turn": turn, "source": "spoken" if spoken else "typed", "client": "dev-phone",
                                   "text": "" if spoken else text, "state": "hearing" if spoken else "accepted",
                                   "answer": None, "at": time.time()}
        self.emit("request", {"turn": turn, "state": "hearing" if spoken else "accepted",
                              "text": "" if spoken else text})
        args = (turn, text, self.answer_delay, voice or spoken, recording == "empty")
        threading.Thread(target=self.play, args=args, daemon=True).start()
        return turn

    def play(self, turn, text, delay, aloud=False, empty=False):
        """The scripted turn: thinking, a card when asked for, then the final answer, and its speech when aloud."""
        time.sleep(0.3)
        if self.requests[turn]["source"] == "spoken":
            if empty:
                self.requests.pop(turn, None)
                return self.emit("request", {"turn": turn, "state": "empty"})
            self.requests[turn]["text"] = text
            self.emit("request", {"turn": turn, "state": "accepted", "text": text})
        self.requests[turn]["state"] = "working"
        self.emit("request", {"turn": turn, "state": "working"})
        self.set_state("thinking")
        if "card" in text.lower():
            card_id = f"card-{secrets.token_hex(3)}"
            self.card = {"id": card_id, "turn": turn, "tool": "Bash",
                         "question": "git -C ~/Code/rook status --short\nShow what changed in Rook's repo.",
                         "options": []}
            self.emit("card", dict(self.card, state="opened"))
            with self.lock:
                self.lock.wait_for(lambda: self.card is None or self.card["id"] != card_id, timeout=120)
        answer = f"Done. You asked: {text}\n\n{ANSWER_TAIL}"
        words = answer.split(" ")
        script = [("activity", STEPS[0]), ("activity", STEPS[1]), ("draft", " ".join(words[:5])),
                  ("activity", STEPS[2]), ("activity", STEPS[3]), ("hold", None),
                  ("draft", " ".join(words[:len(words) // 2])), ("draft", " ".join(words[:len(words) * 4 // 5]))]
        gap = delay / (len(script) + 1)  # Taken when the turn was asked, so a later change waits for the next.
        for what, data in script:
            with self.lock:
                if what == "hold":  # The check holds a turn here, mid-flight, to look at it.
                    self.lock.wait_for(lambda: not self.hold or turn in self.stopped, timeout=300)
                else:
                    self.lock.wait_for(lambda: turn in self.stopped, timeout=gap)
            if turn in self.stopped:
                return self.end(turn, "interrupted", None)
            if what == "activity":
                self.activity.setdefault(turn, []).append(dict(data, turn=turn))
                self.emit("activity", dict(data, live=True, turn=turn, icon=data["kind"]), live=True)
            elif what == "draft":
                self.emit("draft", {"live": True, "turn": turn, "text": data}, live=True)
        with self.lock:
            self.lock.wait_for(lambda: turn in self.stopped, timeout=gap)
        if turn in self.stopped:
            return self.end(turn, "interrupted", None)
        self.end(turn, "answered", answer)
        if aloud:
            for index, words in enumerate(SPOKEN):
                piece = f"{turn}-{index}"
                self.speech[piece] = tone(self.tone_seconds, 440 + 110 * index)
                self.emit("speech", {"live": True, "turn": turn, "index": index, "id": piece, "text": words,
                                     "device": "dev-phone"}, live=True)

    def end(self, turn, state, answer):
        self.requests[turn].update(state=state, answer=answer)
        self.activity.pop(turn, None)
        self.emit("request", {"turn": turn, "state": state, "answer": answer} if answer else {"turn": turn, "state": state})
        self.set_state("resting")

    def stop(self, turn):
        """Stop a turn that still runs. Returns False for one that already ended: its stop is stale."""
        with self.lock:
            request = self.requests.get(turn)
            if not request or request["state"] not in ("hearing", "accepted", "working") or turn in self.stopped:
                return False
            self.stopped.add(turn)
            self.lock.notify_all()
        return True

    def resolve_card(self, card_id):
        with self.lock:
            if not self.card or self.card["id"] != card_id:
                return False
            self.card = None
            self.lock.notify_all()
        self.emit("card", {"id": card_id, "state": "resolved"})
        return True

    def test(self, body):
        """Hooks for phone/check.py: change the fake's behaviour or inject events."""
        do = body.get("do")
        if do == "set":
            with self.lock:
                for key in ("answer_delay", "refuse_streams", "drop_next_reply", "hold", "tone_seconds",
                            "drop_next_audio", "empty_next_audio", "busy_next_audio"):
                    if key in body:
                        setattr(self, key, body[key])
                self.lock.notify_all()
        elif do == "emit":
            return {"seq": self.emit(body["kind"], body["data"], body.get("seq"), body.get("live", False))}
        elif do == "open_card":
            self.card = dict(body["card"])
            return {"seq": self.emit("card", dict(self.card, state="opened"))}
        elif do == "forget_card":  # The card goes away without an event, so the next answer to it is stale.
            self.card = None
        elif do == "clear":
            self.requests.clear()
        elif do == "close_card":
            self.resolve_card(body["id"])
        elif do == "cut_streams":
            with self.lock:
                self.generation += 1
                self.lock.notify_all()
        elif do == "record":
            return {"stream_starts": self.stream_starts, "command_ids": self.command_ids,
                    "card_answers": self.card_answers, "turns": sorted(self.requests),
                    "stop_commands": self.stop_commands, "audio_uploads": self.audio_uploads,
                    "ask_voice": self.ask_voice}
        return {}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    fake: Fake = None

    def log_message(self, *args):
        pass

    def reply(self, status, body, headers=()):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "microphone=(self)")
        if not isinstance(body, bytes):
            self.send_header("Content-Type", "application/json")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, sentence):
        self.reply(status, {"ok": False, "error": sentence})

    def token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and hashlib.sha256(value.encode()).hexdigest() in self.fake.tokens:
                return value
        return None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in FILES:
            name = FILES[path]
            body = (HERE / name).read_bytes()
            return self.reply(200, body, [("Content-Type", TYPES[Path(name).suffix])])
        token = self.token()
        if path in ("/snapshot", "/events", "/work") and not token:
            return self.error(401, "This device is not paired.")
        if path == "/snapshot":
            return self.reply(200, self.fake.snapshot())
        if path == "/work":
            return self.reply(200, WORK)
        if path == "/events":
            return self.events()
        if path.startswith("/speech/") and token:
            return self.speech(path.removeprefix("/speech/"))
        if path.startswith("/speech/"):
            return self.error(401, "This device is not paired.")
        self.error(404, "There is nothing at that address.")

    def speech(self, piece):
        """One piece of spoken answer, with a single byte range when the audio element asks for one."""
        audio = self.fake.speech.get(piece)
        if audio is None:
            return self.error(404, "That speech is gone.")
        wanted = self.headers.get("Range", "")
        if wanted.startswith("bytes=") and "," not in wanted:
            first, _, last = wanted[6:].partition("-")
            start = int(first) if first.isdigit() else 0
            end = min(len(audio) - 1, int(last)) if last.isdigit() else len(audio) - 1
            if start <= end:
                return self.reply(206, audio[start:end + 1], [("Content-Type", "audio/wav"), ("Accept-Ranges", "bytes"),
                                                              ("Content-Range", f"bytes {start}-{end}/{len(audio)}")])
        self.reply(200, audio, [("Content-Type", "audio/wav"), ("Accept-Ranges", "bytes")])

    def events(self):
        fake = self.fake
        if fake.refuse_streams:
            return self.error(503, "Rook is not answering.")
        after = self.headers.get("Last-Event-ID") or parse_qs(urlsplit(self.path).query).get("after", ["0"])[0]
        cursor = int(after) if after.isdigit() else 0
        fake.stream_starts.append(cursor)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        generation = fake.generation
        with fake.lock:  # sent indexes the log, so an event the check sends again under its old id goes out again.
            sent = next((i for i, e in enumerate(fake.events) if e[0] is not None and e[0] > cursor), len(fake.events))
        try:
            self.wfile.write(b"retry: 1000\n: hello\n\n")
            self.wfile.flush()
            while True:
                with fake.lock:
                    fake.lock.wait_for(lambda: len(fake.events) > sent or fake.generation != generation, timeout=15)
                    if fake.generation != generation:
                        return
                    batch = fake.events[sent:]
                    sent = len(fake.events)
                if not batch:
                    self.wfile.write(b": quiet\n\n")
                for seq, kind, data in batch:
                    head = f"id: {seq}\n" if seq is not None else ""
                    self.wfile.write(f"{head}event: {kind}\ndata: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def body(self):
        if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            self.error(403, "This request came from another site.")
            return None
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self.error(415, "Send JSON.")
            return None
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length)) if 0 < length <= 16384 else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            self.error(400, "The request body is not a JSON object.")
        return data

    def do_POST(self):
        fake, path = self.fake, urlsplit(self.path).path
        if path == "/__test":
            length = int(self.headers.get("Content-Length") or 0)
            return self.reply(200, fake.test(json.loads(self.rfile.read(length))))
        if path == "/audio":
            return self.audio()
        data = self.body()
        if data is None:
            return
        if path == "/pair":
            if str(data.get("code", "")).replace(" ", "") != CODE:
                return self.error(400, "That code is wrong or has expired. Ask Rook for a new one.")
            token = secrets.token_urlsafe(32)
            fake.tokens.add(hashlib.sha256(token.encode()).hexdigest())
            cookie = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000"
            return self.reply(200, {"ok": True, "device": {"id": "dev-phone", "name": data.get("name", "")}},
                              [("Set-Cookie", cookie)])
        token = self.token()
        if not token:
            return self.error(401, "This device is not paired.")
        if path != "/command":
            return self.error(404, "There is nothing at that address.")
        if data.get("kind") == "card":
            fake.card_answers.append(data)
            ok = fake.resolve_card(data.get("card"))
            return self.reply(200, {"ok": True}) if ok else self.reply(409, {"ok": False, "error": "stale"})
        if data.get("kind") == "stop":
            fake.stop_commands.append(data)
            ok = fake.stop(data.get("turn"))
            return self.reply(200, {"ok": True}) if ok else self.reply(409, {"ok": False, "error": "stale"})
        if data.get("kind") != "ask" or not str(data.get("text", "")).strip() or not data.get("id"):
            return self.error(400, "That command is not one Rook knows.")
        fake.command_ids.append(data["id"])
        fake.ask_voice.append(data.get("voice") is True)
        key = (hashlib.sha256(token.encode()).hexdigest(), data["id"])
        fingerprint = json.dumps([data["text"], data.get("mode", "queue")])
        with fake.lock:
            stored = fake.commands.get(key)
        if stored:
            if stored[0] != fingerprint:
                return self.error(409, "That command id was already used for another request.")
            result = dict(stored[1], status="duplicate")
        else:
            result = {"ok": True, "turn": fake.ask(data["text"], voice=data.get("voice") is True), "status": "accepted"}
            with fake.lock:
                fake.commands[key] = (fingerprint, result)
        if fake.drop_next_reply:
            fake.drop_next_reply = False
            self.close_connection = True
            return  # The command ran, and its answer is lost on the way back.
        self.reply(200, result)

    def audio(self):
        """A recording: the body is the audio as the browser made it, with the command id in X-Rook-Command."""
        fake = self.fake
        if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            return self.error(403, "This request came from another site.")
        token = self.token()
        if not token:
            return self.error(401, "This device is not paired.")
        kind = self.headers.get("Content-Type", "").split(";")[0].strip()
        command = self.headers.get("X-Rook-Command", "")
        length = int(self.headers.get("Content-Length") or 0)
        if kind not in AUDIO_TYPES:
            return self.error(415, "Send the recording as audio/webm, audio/ogg or audio/mp4.")
        if not (0 < len(command) <= 128 and all(c.isalnum() or c in "-_" for c in command)):
            return self.error(400, "The recording needs its command id.")
        if not 0 < length <= AUDIO_MAX:
            return self.error(413, "That recording is too long.")
        body = self.rfile.read(length)
        if fake.busy_next_audio:
            fake.busy_next_audio = False
            return self.error(429, "Rook is still hearing your last recording.")
        fake.audio_uploads.append((command, self.headers.get("Content-Type"), len(body)))
        key = (hashlib.sha256(token.encode()).hexdigest(), command)
        fingerprint = hashlib.sha256(body).hexdigest()
        with fake.lock:
            stored = fake.commands.get(key)
        if stored:
            if stored[0] != fingerprint:
                return self.error(409, "That command id was already used for another request.")
            result = dict(stored[1], status="duplicate")
        else:
            recording = "empty" if fake.empty_next_audio else "words"
            fake.empty_next_audio = False
            result = {"ok": True, "turn": fake.ask(HEARD, recording=recording), "status": "accepted"}
            with fake.lock:
                fake.commands[key] = (fingerprint, result)
        if fake.drop_next_audio:
            fake.drop_next_audio = False
            self.close_connection = True
            return  # The recording was taken, and the answer is lost on the way back.
        self.reply(200, result)


def serve(scene="full", port=0, paired_token=None):
    """Start the stand-in in a thread. Returns (server, fake)."""
    fake = Fake(scene)
    if paired_token:
        fake.tokens.add(hashlib.sha256(paired_token.encode()).hexdigest())
    handler = type("BoundHandler", (Handler,), {"fake": fake})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, fake


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--scene", choices=("empty", "full"), default="full")
    args = parser.parse_args()
    server, _ = serve(args.scene, args.port)
    print(f"Rook's phone stand-in: http://127.0.0.1:{server.server_address[1]}/  (pairing code {CODE})", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
