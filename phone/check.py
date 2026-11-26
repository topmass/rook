"""The phone app's check: the app in phone/, against phone/standin.py, in a headless Chromium on a scratch profile.

    scripts/capped python phone/check.py                 the check, one pass line
    scripts/capped python phone/check.py --shots DIR     screenshots of each screen at 390 x 844 and 360 x 740

Standard library only. It drives the browser over the DevTools protocol with a small WebSocket client of its own.
The browser is headless, muted, and has its own profile in a temporary folder that the check deletes.
"""

import argparse
import base64
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import standin  # noqa: E402

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 26_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
ANDROID = "Mozilla/5.0 (Linux; Android 16; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0 Mobile Safari/537.36"
SIZES = [(390, 844, IPHONE, (47, 34)), (360, 740, ANDROID, (32, 16))]


class DevTools:
    """One DevTools session over a WebSocket: send a command, read until its answer, ignore events."""

    def __init__(self, url):
        parts = urlsplit(url)
        self.sock = socket.create_connection((parts.hostname, parts.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {parts.path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        self.buf = b""
        while b"\r\n\r\n" not in self.buf:
            self.buf += self.sock.recv(4096)
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        assert b" 101 " in head.split(b"\r\n")[0], head
        self.last = 0

    def _read(self, n):
        chunks, have = [self.buf], len(self.buf)
        while have < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise ConnectionError("The browser closed the DevTools connection.")
            chunks.append(chunk)
            have += len(chunk)
        data = b"".join(chunks)
        self.buf = data[n:]
        return data[:n]

    def _message(self):
        message = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if b0 & 0x0F == 8:
                raise ConnectionError("The browser closed the DevTools connection.")
            if b0 & 0x0F in (9, 10):
                continue
            message += payload
            if b0 & 0x80:
                return json.loads(message)

    def call(self, method, **params):
        self.last += 1
        data = json.dumps({"id": self.last, "method": method, "params": params}).encode()
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n)
                                if n < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", n))
        mask = os.urandom(4)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        while True:
            reply = self._message()
            if reply.get("id") == self.last:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error'].get('message')}")
                return reply.get("result", {})


class BrowserUnavailable(RuntimeError):
    """Raised when no supported Chromium binary is installed on PATH."""


def find_browser():
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        if found := shutil.which(name):
            return found
    return None


class Phone:
    """A headless Chromium with one page, sized as a phone."""

    def __init__(self, scratch, width, height, agent, insets, quiet=True):
        browser_bin = find_browser()
        if not browser_bin:
            raise BrowserUnavailable("No Chromium browser is installed on PATH.")
        self._short_dir = None
        profile = Path(scratch) / f"profile-{width}"
        # Chromium puts SingletonSocket under TMPDIR / profile; paths over ~95 bytes abort on Linux sun_path limits.
        if len(str(profile)) > 60:
            self._short_dir = Path(tempfile.mkdtemp(prefix="rkc-", dir="/tmp"))
            profile = self._short_dir / f"p{width}"
        profile.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
        if len(env.get("TMPDIR", "")) > 40:
            env["TMPDIR"] = "/tmp"
        # Never the caller's runtime folder or session bus, where the running Rook watches media players.
        env["XDG_RUNTIME_DIR"] = str(self._short_dir or profile)
        env.pop("DBUS_SESSION_BUS_ADDRESS", None)
        self.proc = None
        try:
            self.proc = subprocess.Popen(
                [browser_bin, "--headless=new", f"--user-data-dir={profile}", "--remote-debugging-port=0",
                 "--no-first-run", "--no-default-browser-check", "--mute-audio", "--disable-gpu", "--hide-scrollbars",
                 "--disable-extensions", "--disable-sync", "--disable-background-networking", "--disable-component-update",
                 "--password-store=basic", "--use-mock-keychain",
                 # A fake microphone that grants itself, and sound that plays without a gesture, into a muted browser.
                 "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                 "--autoplay-policy=no-user-gesture-required", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            port_file = profile / "DevToolsActivePort"
            deadline = time.time() + 20
            while not (port_file.exists() and len(port_file.read_text().split()) == 2):
                if time.time() > deadline or self.proc.poll() is not None:
                    raise RuntimeError("Headless Chromium did not start.")
                time.sleep(0.05)
            port, path = port_file.read_text().split()
            browser = DevTools(f"ws://127.0.0.1:{port}{path}")
            target = browser.call("Target.createTarget", url="about:blank")["targetId"]
            self.page = DevTools(f"ws://127.0.0.1:{port}/devtools/page/{target}")
            self.page.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=3,
                           mobile=True)
            self.page.call("Emulation.setUserAgentOverride", userAgent=agent)
            try:
                top, bottom = insets
                self.page.call("Emulation.setSafeAreaInsetsOverride", insets={"top": top, "bottom": bottom})
            except RuntimeError:
                pass  # An older Chromium has no safe-area emulation; the screens then show no notch room.
            # The presence's quiet switch (see phone/presence.js): checks test the page, not the dust's pixels, which
            # headless Chromium can only render in software, at several cores' cost. The screenshots keep the real look.
            self.quiet = None
            if quiet:
                self.page.call("Page.enable")  # Scripts for new documents need the Page domain on.
                self.quiet = self.page.call("Page.addScriptToEvaluateOnNewDocument",
                                            source="window.rookCheckPresence = 'quiet';")["identifier"]
        except Exception:
            self.close()
            raise

    def unquiet(self):
        """From the next page load on, the presence draws as on a phone: the real WebGL look."""
        if self.quiet is not None:
            self.page.call("Page.removeScriptToEvaluateOnNewDocument", identifier=self.quiet)
            self.quiet = None

    def go(self, url):
        self.page.call("Page.navigate", url=url)
        self.wait("document.readyState === 'complete' && typeof app === 'object'")

    def js(self, expression):
        result = self.page.call("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in result:
            raise AssertionError(f"{expression}: {result['exceptionDetails']}")
        return result["result"].get("value")

    def wait(self, expression, timeout=8.0, why=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.js(expression):
                    return
            except (AssertionError, RuntimeError):
                pass
            time.sleep(0.05)
        raise AssertionError(why or f"Timed out waiting for: {expression}")

    def type_and_send(self, text):
        self.js(f"""(() => {{ const t = document.getElementById('ask-text'); t.value = {json.dumps(text)};
                   t.dispatchEvent(new Event('input')); document.getElementById('ask-form').requestSubmit(); }})()""")

    def pair(self, code):
        self.js(f"""(() => {{ document.getElementById('pair-code').value = {json.dumps(code)};
                   document.getElementById('pair-form').requestSubmit(); }})()""")

    def shot(self, path):
        self.js("document.activeElement?.blur()")
        self.js("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")
        data = self.page.call("Page.captureScreenshot", format="png")["data"]
        Path(path).write_bytes(base64.b64decode(data))

    def close(self):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self._short_dir is not None:
            shutil.rmtree(self._short_dir, ignore_errors=True)
            self._short_dir = None


def text_of(selector):
    return f"(document.querySelector({json.dumps(selector)})?.textContent ?? '')"


def _serve_real(scratch):
    """Start desktop/server.py with a fake session that matches phone/standin.py."""
    import asyncio
    import threading
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))
    import server as server_mod  # noqa: E402

    class ConformanceSession:
        def __init__(self):
            now = time.time()
            self.lock = threading.Condition()
            self.events = []
            self.seq = 100
            self.subscribers = []
            self.requests = {r["turn"]: r for r in standin.fixture_requests("full", now)}
            self.card = None
            self.state = "resting"
            self.commands = {}
            self.turns = 102
            self.answer_delay = 1.2
            self.refuse_streams = False
            self.drop_next_reply = False
            self.retry_gates = {}
            self.stream_starts = []
            self.command_ids = []
            self.card_answers = []

        def emit(self, kind, data, seq=None, live=False):
            with self.lock:
                if live:
                    ev = server_mod.Event(kind=kind, data=data, seq=None)
                elif seq is None:
                    self.seq += 1
                    seq = self.seq
                    ev = server_mod.Event(kind=kind, data=data, seq=seq)
                    self.events.append(ev)
                else:
                    ev = server_mod.Event(kind=kind, data=data, seq=seq)
                subs = list(self.subscribers)
            for cb in subs:
                cb(ev)
            return seq

        def snapshot(self, device_id):
            with self.lock:
                reqs = sorted(self.requests.values(), key=lambda r: r["at"])[-20:]
                return {"cursor": self.seq, "state": self.state, "requests": reqs, "card": self.card, "notices": [],
                        "work": standin.WORK, "mailbox": {"open": 0, "items": []}, "dark": False, "focus": None,
                        "restart": None}

        def high_water(self):
            with self.lock:
                if self.refuse_streams:
                    raise RuntimeError("Streams are refused for check.")
                return self.seq

        def events_after(self, cursor, upto):
            with self.lock:
                if self.refuse_streams:
                    raise RuntimeError("Streams are refused for check.")
                self.stream_starts.append(cursor)
                return [e for e in self.events if e.seq is not None and cursor < e.seq <= upto]

        def subscribe(self, callback):
            with self.lock:
                self.subscribers.append(callback)

        def unsubscribe(self, callback):
            with self.lock:
                if callback in self.subscribers:
                    self.subscribers.remove(callback)

        def work(self):
            return standin.WORK

        def mailbox(self):
            return {"open": 0, "items": []}

        def set_state(self, state):
            self.state = state
            self.emit("state", {"state": state, "live": True}, live=True)

        def ask(self, device_id, text, gate=None):
            with self.lock:
                self.turns += 1
                turn = f"t-{self.turns}"
                self.requests[turn] = {"turn": turn, "source": "typed", "client": device_id, "text": text,
                                       "state": "accepted", "answer": None, "at": time.time()}
            self.emit("request", {"turn": turn, "state": "accepted", "text": text})
            threading.Thread(target=self.play, args=(turn, text, gate), daemon=True).start()
            return turn

        def play(self, turn, text, gate):
            time.sleep(0.3)
            self.requests[turn]["state"] = "working"
            self.emit("request", {"turn": turn, "state": "working"})
            self.set_state("thinking")
            if gate is not None:
                gate.wait(timeout=6.0)
            time.sleep(self.answer_delay)
            answer = f"Done. You asked: {text}"
            self.requests[turn].update(state="answered", answer=answer)
            self.emit("request", {"turn": turn, "state": "answered", "answer": answer})
            self.set_state("resting")

        def resolve_card(self, card_id):
            with self.lock:
                if not self.card or self.card["id"] != card_id:
                    return False
                self.card = None
                self.lock.notify_all()
            self.emit("card", {"id": card_id, "state": "resolved"})
            return True

        def command(self, device_id, data):
            if data.get("kind") == "card":
                self.card_answers.append(data)
                ok = self.resolve_card(data.get("card"))
                return {"ok": True} if ok else {"ok": False, "error": "stale"}
            if data.get("kind") != "ask" or not str(data.get("text", "")).strip():
                raise server_mod.CommandError(400, "That command is not one Rook knows.")
            self.command_ids.append(data["id"])
            key = (device_id, data["id"])
            fingerprint = json.dumps([data["text"], data.get("mode", "queue")])
            with self.lock:
                stored = self.commands.get(key)
            if stored:
                if stored[0] != fingerprint:
                    raise server_mod.CommandError(409, "That command id was already used for another request.")
                gate = self.retry_gates.pop(stored[1]["turn"], None)
                if gate is not None:
                    gate.set()
                return dict(stored[1], status="duplicate")
            drop = self.drop_next_reply
            self.drop_next_reply = False
            gate = threading.Event() if drop else None
            turn = self.ask(device_id, data["text"], gate=gate)
            result = {"ok": True, "turn": turn, "status": "accepted"}
            with self.lock:
                self.commands[key] = (fingerprint, result)
                if gate is not None:
                    self.retry_gates[turn] = gate
            if drop:
                raise RuntimeError("Dropped reply for retry check.")
            return result

    session = ConformanceSession()
    store = server_mod.DeviceStore(Path(scratch) / "devices.db").open()
    store.create_code(code=standin.CODE)
    srv = server_mod.Server(session, store, port=0, static_dir=Path(__file__).resolve().parent, secure_cookies=False,
                            pair_on_loopback=True)
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def runner():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(srv.start())
        ready.set()
        loop.run_forever()
        loop.run_until_complete(srv.close())
        loop.close()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    ready.wait(timeout=5.0)
    base = f"http://127.0.0.1:{srv.port}/"

    def hook(body):
        do = body.get("do")
        if do == "set":
            for key in ("answer_delay", "refuse_streams", "drop_next_reply"):
                if key in body:
                    setattr(session, key, body[key])
        elif do == "emit":
            return {"seq": session.emit(body["kind"], body["data"], body.get("seq"), body.get("live", False))}
        elif do == "open_card":
            session.card = dict(body["card"])
            return {"seq": session.emit("card", dict(session.card, state="opened"))}
        elif do == "forget_card":
            session.card = None
        elif do == "clear":
            session.requests.clear()
        elif do == "close_card":
            session.resolve_card(body["id"])
        elif do == "cut_streams":
            done = threading.Event()
            loop.call_soon_threadsafe(lambda: (srv.close_streams(), done.set()))
            done.wait(timeout=5.0)
        elif do == "record":
            return {"stream_starts": list(session.stream_starts), "command_ids": list(session.command_ids),
                    "card_answers": list(session.card_answers), "turns": sorted(session.requests)}
        return {}

    def shutdown():
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5.0)

    return base, hook, shutdown


def check(scratch, use_server=False):
    if use_server:
        base, hook, shutdown = _serve_real(scratch)
    else:
        server, fake = standin.serve("full")
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        hook = lambda body: post(base + "__test", body)
        shutdown = server.shutdown
    phone = Phone(scratch, *SIZES[0])
    try:
        # Pairing: an unpaired phone sees the pairing screen; a wrong code gets one sentence; the right code pairs.
        phone.go(base + "#code=418207")
        phone.wait("!document.getElementById('pair').hidden", why="An unpaired phone did not see the pairing screen.")
        assert phone.js("document.getElementById('pair-name').value") == "iPhone"
        assert phone.js("[document.getElementById('pair-code').value, location.hash, document.activeElement.id]") == [
            "418207", "", "pair-name"], "A pairing link did not fill in the code, focus the name, and drop the hash."
        phone.pair("000000")
        phone.wait("!document.getElementById('pair-error').hidden")
        assert "wrong or has expired" in phone.js(text_of("#pair-error"))
        phone.pair("418 207")
        phone.wait("!document.getElementById('shell').hidden", why="The right code did not pair the phone.")

        # The snapshot: both exchanges, newest first under the presence, the long answer with its list and code.
        phone.wait("document.querySelectorAll('.turn').length === 2")
        asks = phone.js("[...document.querySelectorAll('.ask')].map((e) => e.textContent)")
        assert asks == ["How did the phone build go?", "What time is my call with Dana?"], asks
        assert phone.js("document.querySelectorAll('.answer ul li').length") == 3
        assert phone.js("document.querySelectorAll('.answer code').length") >= 3
        phone.wait("app.connected")
        assert phone.js("document.getElementById('talk').scrollTop") == 0, "The newest exchange is not in view."

        # Sending: pending at once, then the answer replaces it.
        hook({"do": "set", "answer_delay": 0.8})
        phone.type_and_send("Is the build green?")
        assert phone.js("document.querySelector('article.turn:first-of-type .pending') !== null"), "A sent request is not pending."
        phone.wait(f"{text_of('article.turn:first-of-type .answer:not(.draft)')}.includes('You asked: Is the build green?')")
        assert phone.js("document.querySelector('article.turn:first-of-type .pending')") is None

        # A retry after a lost reply reuses the command id, and the request runs once.
        hook({"do": "set", "drop_next_reply": True})
        turns_before = len(hook({"do": "record"})["turns"])
        phone.type_and_send("Retry me once.")
        phone.wait(f"{text_of('article.turn:first-of-type .answer:not(.draft)')}.includes('Retry me once.')", timeout=10)
        record = hook({"do": "record"})
        assert record["command_ids"][-1] == record["command_ids"][-2], record["command_ids"][-3:]
        assert len(record["turns"]) == turns_before + 1, "The retried request ran twice."
        assert phone.js("document.querySelectorAll('.turn').length") == 4, "The retried request shows twice."

        # An event that arrives twice applies once.
        seq = hook({"do": "emit", "kind": "request", "data": {"turn": "t-101", "state": "closed", "answer": "FIRST"}})["seq"]
        phone.wait(f"{text_of(turn_of('t-101', '.answer'))} === 'FIRST'")
        hook({"do": "emit", "kind": "request", "seq": seq, "data": {"turn": "t-101", "state": "closed", "answer": "SECOND"}})
        time.sleep(0.5)
        assert phone.js(text_of(turn_of("t-101", ".answer"))) == "FIRST", "An event applied twice."

        # A live event right after a stored one applies: it has no id, and a browser repeats the last id on it.
        for state in ("thinking", "speaking"):
            hook({"do": "emit", "kind": "state", "live": True, "data": {"state": state, "live": True}})
            phone.wait(f"app.rook === '{state}'", why=f"The live state {state} did not apply.")
        assert phone.js("app.lastId") == seq, "A live event moved the cursor."

        # Answers are text: markup in an answer shows as its own characters and never runs.
        hostile = '<script>window.pwned = 1</script> and <img src=x onerror="window.pwned = 2">'
        hook({"do": "emit", "kind": "request", "data": {"turn": "t-900", "state": "answered", "text": "Show markup.",
                                                        "answer": hostile, "at": time.time()}})
        phone.wait(f"{text_of('article.turn:first-of-type .answer:not(.draft)')}.includes('<script>')")
        assert phone.js(text_of("article.turn:first-of-type .answer")) == hostile
        assert phone.js("document.querySelector('#talk img, #talk script') === null && window.pwned === undefined")

        # A waiting card: shown with its words, answered with its id; a stale answer removes it with one line.
        card = {"id": "card-a", "turn": "t-900", "tool": "Bash", "question": "rm -r build/", "options": []}
        hook({"do": "open_card", "card": card})
        phone.wait("!document.getElementById('card').hidden")
        assert "Bash" in phone.js(text_of("#card-title")) and "rm -r build/" in phone.js(text_of(".card-question"))
        phone.js("document.querySelector('#card .button-primary').click()")
        phone.wait("document.getElementById('card').hidden")
        answer = hook({"do": "record"})["card_answers"][-1]
        assert (answer["card"], answer["allow"], answer["kind"]) == ("card-a", True, "card"), answer
        hook({"do": "open_card", "card": dict(card, id="card-b")})
        phone.wait("!document.getElementById('card').hidden")
        # The same id with other words redraws: the card never keeps old words under a new ask.
        hook({"do": "open_card", "card": dict(card, id="card-b", question="rm -rf ~", count=2, live=True)})
        phone.wait(f"{text_of('.card-question')}.includes('rm -rf ~')")
        assert "1 of 2" in phone.js(text_of("#card"))
        hook({"do": "forget_card"})
        phone.js("[...document.querySelectorAll('#card .button')].find((b) => b.textContent === 'Decline').click()")
        phone.wait("document.getElementById('card').hidden && !document.getElementById('card-note').hidden")
        assert "already closed" in phone.js(text_of("#card-note"))
        assert hook({"do": "record"})["card_answers"][-1]["card"] == "card-b"

        # A question with options waits for the desk: the phone shows it with one line and no buttons.
        hook({"do": "open_card", "card": {"id": "card-q", "turn": "t-900", "tool": None, "question": "Ship tonight?",
                                           "options": ["Yes", "No"], "desk": True}})
        phone.wait("!document.getElementById('card').hidden")
        assert "at your desk" in phone.js(text_of("#card")) and phone.js("document.querySelector('#card button')") is None
        hook({"do": "close_card", "id": "card-q"})
        phone.wait("document.getElementById('card').hidden")

        # The work list: waiting first, then finished, then running, each line led by its project.
        phone.js("document.getElementById('work-open').click()")
        phone.wait("document.querySelectorAll('.work-item').length === 4")
        heads = phone.js("[...document.querySelectorAll('.work-heading')].map((e) => e.textContent)")
        assert heads == ["Waiting on you", "Finished", "Running"], heads
        assert phone.js(text_of(".work-item .work-project")) == "rook"
        phone.js("document.getElementById('work-close').click()")
        phone.wait("document.getElementById('work').hidden")

        # A reconnect resumes from the last id, and an event sent while the stream was down arrives.
        last = phone.js("app.lastId")
        starts = len(hook({"do": "record"})["stream_starts"])
        hook({"do": "cut_streams"})
        hook({"do": "emit", "kind": "request", "data": {"turn": "t-101", "state": "closed", "answer": "RESUMED"}})
        phone.wait(f"{text_of(turn_of('t-101', '.answer'))} === 'RESUMED'", timeout=10)
        resumed = hook({"do": "record"})["stream_starts"][starts:]
        assert resumed and resumed[0] == last, (resumed, last)

        # Down and refused: one honest line; typing still works, and the request sends once when Rook is back.
        hook({"do": "set", "refuse_streams": True})
        hook({"do": "cut_streams"})
        phone.wait("!document.getElementById('presence-note').hidden", timeout=10)
        assert phone.js("document.getElementById('shell').dataset.mood") == "away"
        assert "Rook is back" in phone.js(text_of("#presence-note"))
        phone.type_and_send("Send me when you can.")
        phone.wait(f"{text_of('article.turn:first-of-type .pending')} === 'Waits to send'")
        hook({"do": "set", "refuse_streams": False})
        phone.wait(f"{text_of('article.turn:first-of-type .answer:not(.draft)')}.includes('Send me when you can.')", timeout=20)
        ids = hook({"do": "record"})["command_ids"]
        assert phone.js("document.getElementById('presence-note').hidden")
        assert len(ids) == len(set(ids)) + 1, "A request queued while away was sent more than once."

        # A request in flight when the app is reopened shows as in flight, from the snapshot.
        hook({"do": "set", "answer_delay": 60})
        phone.type_and_send("Take your time.")
        phone.wait("app.exchanges.some((x) => x.text === 'Take your time.' && x.turn)")
        phone.go(base)
        phone.wait(f"{text_of('article.turn:first-of-type .ask')} === 'Take your time.' && "
                   "document.querySelector('article.turn:first-of-type .pending') !== null")

        # A request left in the outbox past its window is not sent again: it shows one line, and the owner decides.
        hook({"do": "set", "answer_delay": 0.2})
        outbox(phone, base, "[{id: 'too-old-1', text: 'From yesterday.', at: Date.now() / 1000 - 21 * 3600}]")
        phone.go(base)
        phone.wait("[...document.querySelectorAll('.turn-error')].some((e) => e.textContent === "
                   "'Not sent: too old. Send it again.')")
        time.sleep(0.5)
        assert "too-old-1" not in hook({"do": "record"})["command_ids"]
        assert phone.js("JSON.parse(localStorage.getItem('rook.outbox')).length") == 0

        if not use_server:  # Versions 2 and 3 live in the stand-in until desktop/server.py has them.
            check_live(phone, base, hook)
            check_voice(phone, base, hook)
        check_collapse(phone, base, hook, voice=not use_server)

        # The real look still starts: WebGL draws a few frames, then the check moves on.
        phone.unquiet()
        phone.go(base)
        phone.wait("app.connected && RookPresence.stats.gl && RookPresence.stats.frames > 3",
                   why="The WebGL presence did not start and draw.")
        phone.js("Object.defineProperty(document, 'hidden', { value: true, configurable: true }); "
                 "document.dispatchEvent(new Event('visibilitychange'))")
        frames = phone.js("RookPresence.stats.frames")
        time.sleep(0.5)
        assert phone.js("RookPresence.stats.frames") == frames and not phone.js("RookPresence.stats.running"), \
            "The WebGL presence drew on a hidden page."
        phone.js("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")

        # No sideways scroll at 360 px.
        phone.page.call("Emulation.setDeviceMetricsOverride", width=360, height=740, deviceScaleFactor=3, mobile=True)
        assert phone.js("document.documentElement.scrollWidth <= 360"), "The page scrolls sideways at 360 px."
    finally:
        phone.close()
        shutdown()
    print("Phone app against desktop/server.py: all checks passed." if use_server else "Phone app: all checks passed.")


def outbox(phone, base, items):
    """Leave requests in the outbox from a page with no app on it, so no running app can write over them first."""
    phone.page.call("Page.navigate", url=base + "no-app-here")
    phone.wait("document.readyState === 'complete' && typeof app === 'undefined'")
    phone.js(f"localStorage.setItem('rook.outbox', JSON.stringify({items}))")


def turn_of(turn, selector=""):
    return f"article[data-turn={json.dumps(turn)}] {selector}".strip()


def texts(selector):
    return f"[...document.querySelectorAll({json.dumps(selector)})].map((e) => e.textContent)"


def live(hook, event, **data):
    hook({"do": "emit", "kind": event, "live": True, "data": dict(data, live=True)})


def check_live(phone, base, hook):
    """Version 2: the trail of what Rook does, its fold, drafts, stop, and a mid-turn attach."""
    # Stop: the turn still running from the reopen case offers Stop in the send control's place, and stops it.
    turn = phone.js("app.exchanges.find((x) => x.text === 'Take your time.').turn")
    phone.wait("!document.getElementById('ask-stop').hidden && document.getElementById('ask-send').hidden",
               why="A running turn did not offer Stop.")
    phone.js("document.getElementById('ask-stop').click()")
    phone.wait(f"{text_of(turn_of(turn, '.turn-note'))} === 'Rook stopped before it answered.'", timeout=10)
    phone.wait("document.getElementById('ask-stop').hidden && !document.getElementById('ask-send').hidden")
    sent = hook({"do": "record"})["stop_commands"][-1]
    assert (sent["kind"], sent["turn"]) == ("stop", turn) and sent["id"], sent

    # A stale stop removes the control quietly: no line, no error.
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-ghost", "state": "working", "text": "A turn that ended.",
                                                    "at": time.time()}})
    phone.wait("document.getElementById('ask-stop').dataset.turn === 't-ghost'")
    phone.js("document.getElementById('ask-stop').click()")
    phone.wait("document.getElementById('ask-stop').hidden")
    assert phone.js("document.getElementById('card-note').hidden")
    assert phone.js(f"document.querySelector({json.dumps(turn_of('t-ghost', '.turn-error'))}) === null")
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-ghost", "state": "closed", "answer": "It had ended."}})

    # A scripted turn: four steps in order with their icons and details; the tool call clears the draft before it.
    hook({"do": "set", "answer_delay": 2.0, "hold": True})
    phone.type_and_send("Show me the steps.")
    phone.wait("app.exchanges.some((x) => x.text === 'Show me the steps.' && x.turn)")
    turn = phone.js("app.exchanges.find((x) => x.text === 'Show me the steps.').turn")
    phone.wait(f"document.querySelectorAll({json.dumps(turn_of(turn, '.step'))}).length === 4", timeout=10)
    labels = phone.js(texts(turn_of(turn, ".step-label")))
    assert labels == [s["label"] for s in standin.STEPS], labels
    icons = phone.js(f"[...document.querySelectorAll({json.dumps(turn_of(turn, '.step use'))})]"
                     ".map((u) => u.getAttribute('href'))")
    assert icons == ["#i-thinking", "#i-reading", "#i-running", "#i-sending"], icons
    assert phone.js(texts(turn_of(turn, ".step-detail"))) == ["phone/app.js", "scripts/capped python3 phone/check.py",
                                                             "Rook build (Opus)"]
    assert phone.js(f"document.querySelector({json.dumps(turn_of(turn, '.draft'))}) === null"), "A tool call left a draft."
    assert phone.js(f"document.querySelectorAll({json.dumps(turn_of(turn, '.step-now'))}).length") == 1
    assert phone.js(text_of("#presence-label")) == "Sending to a thread", phone.js(text_of("#presence-label"))

    # A phone that attaches mid-turn shows the snapshot's activity at once.
    phone.go(base)
    phone.wait(f"document.querySelectorAll({json.dumps(turn_of(turn, '.step'))}).length === 4",
               why="A mid-turn attach did not show the turn's activity.")

    # The answer folds the trail into one line, which opens again and stays open through a redraw.
    hook({"do": "set", "hold": False})
    phone.wait(f"{text_of(turn_of(turn, '.answer:not(.draft)'))}.includes('You asked: Show me the steps.')", timeout=10)
    said = phone.js(text_of(turn_of(turn, ".trail-said")))
    assert said == "Rook read, ran one command and sent one message.", said
    assert phone.js(f"document.querySelector({json.dumps(turn_of(turn, 'details.trail'))}).open") is False
    assert phone.js(f"document.querySelector({json.dumps(turn_of(turn, '.step'))}).checkVisibility()") is False
    phone.js(f"document.querySelector({json.dumps(turn_of(turn, '.trail summary'))}).click()")
    phone.wait(f"document.querySelector({json.dumps(turn_of(turn, 'details.trail'))}).open")
    live(hook, "state", state="thinking")
    live(hook, "state", state="resting")
    time.sleep(0.3)
    assert phone.js(f"document.querySelector({json.dumps(turn_of(turn, 'details.trail'))}).open"), "A redraw closed the fold."
    assert phone.js(f"document.querySelector({json.dumps(turn_of(turn, '.step'))}).checkVisibility()") is True

    # Drafts: shown in the answer's place, replaced whole, cleared by a tool call, replaced for good by the answer.
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-draft", "state": "working", "text": "Write it out.",
                                                    "at": time.time()}})
    draft = turn_of("t-draft", ".answer.draft")
    live(hook, "draft", turn="t-draft", text="The first words")
    phone.wait(f"{text_of(draft)} === 'The first words' && document.querySelector({json.dumps(draft + ' .draft-grain')}) !== null")
    live(hook, "draft", turn="t-draft", text="The first words and then more")
    phone.wait(f"{text_of(draft)} === 'The first words and then more'")
    assert phone.js(f"document.querySelectorAll({json.dumps(draft)}).length") == 1
    live(hook, "activity", turn="t-draft", kind="searching", label="Searching the web.", icon="zeppelin",
         detail='<img src=x onerror="window.pwned = 3"> and <b>bold</b>')
    phone.wait(f"document.querySelector({json.dumps(draft)}) === null", why="A tool call did not clear the draft.")
    assert phone.js(f"document.querySelector({json.dumps(turn_of('t-draft', '.step use'))}).getAttribute('href')") == "#i-dot"
    assert phone.js(text_of(turn_of("t-draft", ".step-detail"))) == '<img src=x onerror="window.pwned = 3"> and <b>bold</b>'
    assert phone.js("document.querySelector('#talk img, #talk b') === null && window.pwned === undefined")
    live(hook, "activity", turn="t-draft", kind="hovering", label="Doing something new.")
    phone.wait(f"document.querySelectorAll({json.dumps(turn_of('t-draft', '.step use'))})[1]?.getAttribute('href') === '#i-dot'")

    # No scroll jump: when the owner has scrolled down to older exchanges, the newest draft growing above them leaves
    # what they read where it is.
    older = json.dumps(turn_of("t-101", ".ask"))
    phone.js(f"document.querySelector({older}).scrollIntoView({{block: 'center'}})")
    time.sleep(0.2)
    before = phone.js(f"document.querySelector({older}).getBoundingClientRect().top")
    for words in ("Now the draft", "Now the draft grows\n\nby a paragraph", "Now the draft grows\n\nby a paragraph\n\nand one more"):
        live(hook, "draft", turn="t-draft", text=words)
        phone.wait(f"{text_of(draft)}.endsWith({json.dumps(words.split(chr(10))[-1])})")
    after = phone.js(f"document.querySelector({older}).getBoundingClientRect().top")
    assert abs(after - before) < 2, f"A draft moved what the owner was reading by {after - before} px."
    phone.js("document.getElementById('talk').scrollTop = 0")

    hook({"do": "emit", "kind": "request", "data": {"turn": "t-draft", "state": "answered", "answer": "The final words."}})
    phone.wait(f"{text_of(turn_of('t-draft', '.answer:not(.draft)'))} === 'The final words.'")
    live(hook, "draft", turn="t-draft", text="A late draft")
    time.sleep(0.3)
    assert phone.js(f"document.querySelector({json.dumps(draft)}) === null"), "A late draft covered the answer."
    assert phone.js(text_of(turn_of("t-draft", ".trail-said"))) == "Rook searched and used one tool."


def check_voice(phone, base, hook):
    """Version 3: the presence from the desktop's forms, tap to talk and tap to send, Rook's voice on the phone."""
    phone.go(base)
    phone.wait("app.connected && RookPresence.forms().length > 0", why="The presence did not load its forms.")
    assert not phone.js("RookPresence.stats.gl"), "The check's presence is not the quiet one."
    forms = set(phone.js("RookPresence.forms()"))
    assert {"loop", "halo", "helix", "rows", "lattice", "rook", "sphere", "question", "send_turbine", "send_array",
            "prompt", "page"} <= forms, forms
    hook({"do": "set", "answer_delay": 0.6, "tone_seconds": 0.35, "hold": False})

    # Every form a mood or an activity can take draws in the quiet mode: the grains reach the canvas.
    phone.js("window.keptRender = renderPresence; renderPresence = () => {}")  # The check drives the presence.
    lit = ("(() => { const c = document.getElementById('dust'); const d = c.getContext('2d')"
           ".getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) "
           "n += d[i] > 0; return n; })()")
    moods = [("resting", None, "loop"), ("listening", None, "halo"), ("resting", None, "loop"),
             ("listening", None, "helix"), ("transcribing", None, "rows"), ("speaking", None, "sphere"),
             ("waiting", None, "question"), ("error", None, "sink"), ("thinking", "sending", "send_turbine"),
             ("thinking", "reading", "page"), ("thinking", "launching", "send_array")]
    moods += [("thinking", kind, None) for kind in ("reading", "searching", "running", "editing", "launching",
                                                     "waiting", "showing", "drawing", "timing", "game", "tool")]
    for mood, kind, form in moods:
        phone.js(f"RookPresence.set({json.dumps(mood)}, {json.dumps(kind)}, {json.dumps(kind and 'line')})")
        shape = f"=== {json.dumps(form)}" if form else "!== 'lattice' && RookPresence.form() !== 'rook'"
        phone.wait(f"RookPresence.form() {shape}", why=f"{mood} {kind} did not take its form.")
        time.sleep(0.6)  # The grains have flown: a form that cannot be drawn leaves the canvas empty.
        assert phone.js(lit) > 40, f"The {phone.js('RookPresence.form()')} form drew nothing."

    # The speaking globe moves as the desk's does: a wave for each syllable of Rook's voice. With no level on the
    # phone (the desk speaks) a stand-in rhythm drives it; a level played here drives it, and silence stills it.
    phone.js("RookPresence.set('speaking')")
    phone.wait("RookPresence.form() === 'sphere'")
    phone.wait("RookPresence.waves() > 0", timeout=4, why="The speaking globe made no waves without a level.")
    phone.js("window.saying = setInterval(() => RookPresence.setSpeech(0), 50)")
    phone.wait("RookPresence.waves() === 0", timeout=4, why="Silence on the phone did not still the globe.")
    phone.js("clearInterval(saying); window.saying = setInterval(() => "
             "RookPresence.setSpeech(Math.sin(performance.now() / 40) > 0 ? 0.8 : 0), 50)")
    phone.wait("RookPresence.waves() > 0", timeout=4, why="Rook's level on the phone made no waves.")
    phone.js("clearInterval(saying)")
    phone.js("RookPresence.set('resting'); renderPresence = keptRender; renderPresence()")

    # The right form for each state: resting is the loop, a desk turn's thinking the lattice, a card the question.
    phone.wait("RookPresence.form() === 'loop'", timeout=15, why="Resting is not the loop.")
    assert phone.js(text_of("#presence-label")) == ""
    live(hook, "state", state="thinking")
    phone.wait("RookPresence.form() === 'lattice' && document.getElementById('presence-label').textContent === 'Thinking'")
    hook({"do": "open_card", "card": {"id": "card-v", "turn": "t-101", "tool": "Bash", "question": "ls", "options": []}})
    phone.wait("RookPresence.form() === 'question'")
    hook({"do": "close_card", "id": "card-v"})
    live(hook, "state", state="resting")
    phone.wait("RookPresence.form() === 'loop'")

    # At rest the presence draws at a low rate, and nothing at all while the page is hidden.
    time.sleep(3.5)
    frames = phone.js("RookPresence.stats.frames")
    time.sleep(1.0)
    rate = phone.js("RookPresence.stats.frames") - frames
    assert rate <= 24, f"The resting presence drew {rate} frames in a second."
    phone.js("""(() => { window.rafAsked = 0; const ask = window.requestAnimationFrame.bind(window);
                window.requestAnimationFrame = (f) => { window.rafAsked += 1; return ask(f); };
                Object.defineProperty(document, 'hidden', { value: true, configurable: true });
                document.dispatchEvent(new Event('visibilitychange')); })()""")
    frames = phone.js("RookPresence.stats.frames")
    time.sleep(1.0)
    assert phone.js("window.rafAsked") == 0 and phone.js("RookPresence.stats.frames") == frames, "A hidden page drew."
    assert phone.js("RookPresence.stats.running") is False
    phone.js("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")
    phone.wait("RookPresence.stats.running")

    # A tap starts a recording: the ring, LISTENING. A second tap sends it with its type and its command id.
    uploads = len(hook({"do": "record"})["audio_uploads"])
    phone.js("document.getElementById('presence').click()")
    phone.wait("voice.phase === 'recording'", why="A tap did not start a recording.")
    phone.wait("RookPresence.form() === 'halo' && document.getElementById('presence-label').textContent === 'Listening'")
    time.sleep(1.2)
    phone.js("document.getElementById('presence').click()")
    phone.wait(f"{text_of('article.turn:first-of-type .ask')} === {json.dumps(standin.HEARD)}", timeout=10)
    command, kind, size = hook({"do": "record"})["audio_uploads"][uploads]
    assert kind.startswith("audio/webm") and size > 0, (kind, size)
    turn = phone.js(f"app.exchanges.find((x) => x.cmd === {json.dumps(command)}).turn")
    assert turn and phone.js(text_of(turn_of(turn, ".ask-meta"))).endswith("Spoken on this phone")

    # Its answer is spoken: the pieces play in order, one at a time, and the presence is the sphere while they do.
    phone.js("""(() => { window.mostPlaying = 0; window.overlapWatch = setInterval(() => {
                const now = voice.els.filter((e) => !e.paused).length; window.mostPlaying = Math.max(window.mostPlaying, now);
                }, 10); })()""")
    phone.wait(f"voice.played.length >= 3 && voice.played.at(-1) === {json.dumps(turn + '-2')}", timeout=15,
               why="The spoken answer did not play through.")
    assert phone.js("voice.played.slice(-3)") == [f"{turn}-0", f"{turn}-1", f"{turn}-2"]
    assert phone.js("window.mostPlaying") == 1, "Two pieces played at once."
    phone.js("clearInterval(window.overlapWatch)")

    # A recording in state hearing shows as in flight and keeps the presence on its transcribing form.
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-hear", "state": "hearing", "text": "",
                                                    "source": "spoken", "client": "dev-phone", "at": time.time()}})
    phone.wait(f"{text_of(turn_of('t-hear', '.pending'))} === 'Transcribing' && RookPresence.form() === 'rows' && "
               "document.getElementById('shell').dataset.mood === 'transcribing'",
               why="A hearing recording did not show as in flight on the transcribing form.")
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-hear", "state": "empty"}})
    phone.wait(f"document.querySelector({json.dumps(turn_of('t-hear'))}) === null && RookPresence.form() === 'loop'")

    # A speech piece plays only for this device's id, and never for a turn older than the newest turn.
    played_before = len(phone.js("voice.played"))
    valid_clip = f"{turn}-0"
    now = time.time()
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-sp-old", "state": "answered", "text": "Old.",
                                                    "answer": "Old answer.", "at": now - 0.05}})
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-sp-new", "state": "answered", "text": "New.",
                                                    "answer": "New answer.", "at": now}})
    phone.wait("app.exchanges.some((x) => x.turn === 't-sp-new')")
    live(hook, "speech", turn="t-sp-new", index=0, id=valid_clip, text="Other phone.", device="dev-other")
    live(hook, "speech", turn="t-sp-new", index=0, id=valid_clip, text="No device.")
    live(hook, "speech", turn="t-sp-old", index=0, id=valid_clip, text="Older turn.", device="dev-phone")
    time.sleep(0.4)
    assert len(phone.js("voice.played")) == played_before and not phone.js("voice.playing"), "Wrong device or old turn played."
    # Switching to a newer turn never switches back when a late piece for the superseded turn arrives.
    live(hook, "speech", turn="t-sp-new", index=0, id=valid_clip, text="New turn.", device="dev-phone")
    phone.wait(f"voice.played.length === {played_before + 1}")
    live(hook, "speech", turn="t-sp-newer", index=0, id=f"{turn}-1", text="Even newer.", device="dev-phone")
    phone.wait(f"voice.played.length === {played_before + 2} && voice.queue?.turn === 't-sp-newer'")
    live(hook, "speech", turn="t-sp-new", index=1, id=f"{turn}-2", text="Late from old.", device="dev-phone")
    time.sleep(0.4)
    assert phone.js("voice.played.length") == played_before + 2 and phone.js("voice.queue?.turn") == "t-sp-newer"
    phone.js("stopSpeech(false)")

    # A typed request with "answer aloud" carries voice; a tap while Rook speaks stops it at once and records.
    hook({"do": "set", "tone_seconds": 20})
    phone.js("document.getElementById('ask-voice').click()")
    assert phone.js("document.getElementById('ask-voice').getAttribute('aria-pressed')") == "true"
    phone.type_and_send("Read me the plan.")
    phone.wait("voice.playing", timeout=15)
    assert hook({"do": "record"})["ask_voice"][-1] is True
    phone.wait("RookPresence.form() === 'sphere'")
    phone.js("document.getElementById('presence').click()")
    phone.wait("voice.phase === 'recording' && voice.els.every((e) => e.paused) && !voice.playing",
               why="A tap while Rook spoke did not stop it and record.")
    phone.js("document.getElementById('ask-voice').click()")
    hook({"do": "set", "tone_seconds": 0.35, "empty_next_audio": True})

    # A recording with no words in it: no exchange, one quiet line.
    time.sleep(0.8)
    count = phone.js("app.exchanges.length")
    phone.js("document.getElementById('presence').click()")
    phone.wait("!document.getElementById('presence-note').hidden && "
               "document.getElementById('presence-note').textContent.includes('heard no words')", timeout=10)
    phone.wait(f"app.exchanges.length === {count}")

    # A recording whose transcription failed says so clearly instead of "heard no words".
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-fail-aud", "state": "hearing", "text": "",
                                                    "source": "spoken", "client": "dev-phone", "at": time.time()}})
    phone.wait(f"document.querySelector({json.dumps(turn_of('t-fail-aud'))}) !== null")
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-fail-aud", "state": "empty", "reason": "failed"}})
    phone.wait(f"document.querySelector({json.dumps(turn_of('t-fail-aud'))}) === null && "
               "document.getElementById('presence-note').textContent.includes('did not go through')",
               why="A failed recording did not show the retry message.")

    # A 429 while still hearing the last recording shows a calm line, then succeeds on retry.
    hook({"do": "set", "busy_next_audio": True})
    phone.js("document.getElementById('presence').click()")
    phone.wait("voice.phase === 'recording'")
    time.sleep(0.8)
    phone.js("document.getElementById('presence').click()")
    phone.wait("document.getElementById('presence-note').textContent.includes('still hearing')", timeout=8,
               why="A 429 upload did not show the still-hearing line.")
    phone.wait("voice.pending === null && voice.phase === 'idle'", timeout=15)

    # An upload whose answer is lost is sent again with the same command id, and runs once.
    hook({"do": "set", "drop_next_audio": True})
    before = hook({"do": "record"})
    phone.js("document.getElementById('presence').click()")
    phone.wait("voice.phase === 'recording'")
    time.sleep(0.8)
    phone.js("document.getElementById('presence').click()")
    phone.wait("voice.pending === null && voice.phase === 'idle'", timeout=15)
    after = hook({"do": "record"})
    retried = after["audio_uploads"][len(before["audio_uploads"]):]
    assert len(retried) == 2 and retried[0][0] == retried[1][0], retried
    assert len(after["turns"]) == len(before["turns"]) + 1, "The retried recording ran twice."

    # A recording that runs to its limit ends itself and is sent.
    phone.js("voice.maxSeconds = 1")
    phone.js("document.getElementById('presence').click()")
    phone.wait("voice.phase === 'uploading' || voice.phase === 'idle'", timeout=5, why="A long recording did not end.")
    phone.wait("document.getElementById('presence-note').textContent.includes('five minutes')")
    phone.js("voice.maxSeconds = RECORD_MAX_SECONDS")

    # A refused microphone: one plain sentence, and typing still works.
    phone.js("navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('No.', 'NotAllowedError'))")
    phone.js("document.getElementById('presence').click()")
    phone.wait("document.getElementById('presence-note').textContent.includes('cannot use the microphone')")
    assert phone.js("voice.phase") == "idle" and phone.js("document.getElementById('ask-text').disabled") is False


def check_collapse(phone, base, hook, voice):
    """Presence only: the handle tucks the text away, the arrow brings it back as it was, and the phone keeps the choice."""
    shell = "document.getElementById('shell').classList.contains('collapsed')"
    flag = "!document.getElementById('expand-flag').hidden"
    label = "document.getElementById('expand').getAttribute('aria-label')"
    expanded = "[...document.querySelectorAll('#collapse, #expand')].map((b) => b.getAttribute('aria-expanded'))"
    work = [dict(w) for w in standin.WORK]
    for w in standin.WORK:  # Nothing waits on the owner until the case for it below.
        w["state"] = "done" if w["state"] == "waiting" else w["state"]
    phone.go(base)
    phone.wait("app.connected && document.querySelectorAll('.turn').length > 1")
    # A turn still answering would rightly mark the arrow. Against desktop/server.py the reopen case's turn runs its
    # full minute, since nothing stops it there.
    phone.wait("!app.exchanges.some((x) => IN_FLIGHT.has(x.state) || x.phase)", timeout=75,
               why="Earlier turns did not settle.")
    phone.js("""(() => { const t = document.getElementById('ask-text'); t.value = 'Half a thought';
               t.dispatchEvent(new Event('input')); document.getElementById('talk').scrollTop = 90; })()""")
    top = phone.js("document.getElementById('talk').scrollTop")
    assert top > 0, "The conversation is too short to scroll."

    # A tap on the handle tucks the text away; the arrow brings it back with its scroll and its unsent words.
    phone.js("document.getElementById('collapse').click()")
    phone.wait(f"{shell} && document.getElementById('talk').inert && !document.getElementById('expand').inert")
    assert phone.js("localStorage.getItem('rook.collapsed')") == "true"
    assert phone.js(expanded) == ["false", "false"], phone.js(expanded)
    phone.js("document.getElementById('expand').click()")
    phone.wait(f"!{shell} && !document.getElementById('talk').inert")
    assert phone.js(expanded) == ["true", "true"], phone.js(expanded)
    assert phone.js("document.getElementById('ask-text').value") == "Half a thought", "The unsent words were lost."
    assert phone.js("document.getElementById('talk').scrollTop") == top, "The scroll moved."

    # A pull down on the handle tucks it away too, once the handle has slid back in.
    time.sleep(0.6)
    x, y = phone.js("""(() => { const r = document.getElementById('collapse').getBoundingClientRect();
                       return [r.x + r.width / 2, r.y + r.height / 2]; })()""")
    for kind, dy in (("touchStart", 0), ("touchMove", 20), ("touchMove", 60), ("touchEnd", 60)):
        phone.page.call("Input.dispatchTouchEvent", type=kind,
                        touchPoints=[] if kind == "touchEnd" else [{"x": x, "y": y + dy}])
    phone.wait(shell, why="A pull down on the handle did not tuck the text away.")

    # Rook only: a push up anywhere brings the text back, and a pull down on Rook tucks it away again. Neither starts
    # a recording, and only Rook and its captions stay in view.
    def drag(selector, dy):
        time.sleep(0.6)  # The last change has settled.
        x, y = phone.js(f"""(() => {{ const r = document.querySelector({json.dumps(selector)}).getBoundingClientRect();
                           return [r.x + r.width / 2, r.y + r.height / 2]; }})()""")
        for kind, k in (("touchStart", 0), ("touchMove", 0.3), ("touchMove", 0.7), ("touchMove", 1), ("touchEnd", 1)):
            phone.page.call("Input.dispatchTouchEvent", type=kind,
                            touchPoints=[] if kind == "touchEnd" else [{"x": x, "y": y + dy * k}])

    drag("#presence", -90)
    phone.wait(f"!{shell}", why="A push up did not bring the text back.")
    drag("#presence", 30)  # Short of the threshold: nothing changes.
    time.sleep(0.3)
    assert not phone.js(shell), "A short pull tucked the text away."
    drag("#presence", 90)
    phone.wait(shell, why="A pull down on Rook did not leave Rook alone.")
    hidden = ("[...document.querySelectorAll('#collapse, #talk, .dock')].every((e) => "
              "getComputedStyle(e).visibility === 'hidden')")
    phone.wait(hidden, why="Rook-only view left other parts in view.")
    assert phone.js("getComputedStyle(document.getElementById('presence')).visibility") == "visible"
    assert phone.js("voice.phase") == "idle", "A pull started a recording."

    # The choice survives a reload, and what the phone opens on is not marked new.
    phone.go(base)
    phone.wait(f"app.connected && {shell}", why="A reload forgot the presence-only view.")
    time.sleep(0.4)
    assert not phone.js(flag), "Old replies were marked new."

    # Voice works as before while the text is away: a tap on Rook starts a recording, a second sends it.
    if voice:
        x, y = phone.js("""(() => { const r = document.getElementById('presence').getBoundingClientRect();
                           return [r.x + r.width / 2, r.y + r.height / 2]; })()""")
        for kind in ("touchStart", "touchEnd"):
            phone.page.call("Input.dispatchTouchEvent", type=kind,
                            touchPoints=[] if kind == "touchEnd" else [{"x": x, "y": y}])
        phone.wait("voice.phase === 'recording' && document.getElementById('presence-label').textContent === 'Listening'")
        time.sleep(0.8)
        phone.js("document.getElementById('presence').click()")
        phone.wait("voice.phase !== 'recording'")
        phone.wait("voice.pending === null && voice.phase === 'idle'", timeout=15)
        phone.wait(shell)
    else:
        # A reply that arrives while the text is away marks the arrow.
        hook({"do": "emit", "kind": "request", "data": {"turn": "t-tuck", "state": "answered", "text": "Tucked?",
                                                        "answer": "Yes.", "at": time.time()}})
    phone.wait(flag, timeout=20, why="A reply that arrived while collapsed set no sign.")
    assert "new repl" in phone.js(label)

    # Live captions: Rook's newest words show under it while the text is away, as text.
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-caption", "state": "answered", "text": "Caption?",
                                                    "answer": "The build is **green**.", "at": time.time() + 5}})
    phone.wait(f"{text_of('#caption')} === 'The build is green.' && !document.getElementById('caption').hidden",
               why="A new answer showed no caption in Rook-only view.")

    # A request that ends with no answer marks the arrow too.
    phone.js("document.getElementById('expand').click()")
    phone.js("document.getElementById('collapse').click()")
    phone.wait(f"{shell} && !({flag})")
    hook({"do": "emit", "kind": "request", "data": {"turn": "t-tuck-2", "state": "closed", "text": "Never mind.",
                                                    "at": time.time()}})
    phone.wait(flag, why="A request closed without an answer set no sign.")

    # So does a typed request that was not sent: here, one left in the outbox past its window.
    outbox(phone, base, "[{id: 'too-old-2', text: 'From last week.', at: Date.now() / 1000 - 30 * 3600}]")
    phone.go(base)
    phone.wait(f"app.connected && {shell}")
    phone.wait(f"{flag} && app.exchanges.some((x) => x.cmd === 'too-old-2' && x.phase === 'failed')",
               why="A request Rook did not take set no sign.")

    # A card cannot wait unseen: it opens the text, and once it is answered the text tucks away again.
    phone.js("document.getElementById('expand').click()")
    phone.js("document.getElementById('collapse').click()")
    hook({"do": "open_card", "card": {"id": "card-t", "turn": "t-101", "tool": "Bash", "question": "ls", "options": []}})
    phone.wait(f"!document.getElementById('card').hidden && !{shell}", why="A card waited behind the collapsed text.")
    assert phone.js(expanded) == ["true", "true"], phone.js(expanded)
    hook({"do": "close_card", "id": "card-t"})
    phone.wait(shell)

    # A stale answer's note keeps the text open until it has been read, then the text tucks away again.
    hook({"do": "open_card", "card": {"id": "card-u", "turn": "t-101", "tool": "Bash", "question": "ls", "options": []}})
    phone.wait("!document.getElementById('card').hidden")
    hook({"do": "forget_card"})
    phone.js("[...document.querySelectorAll('#card .button')].find((b) => b.textContent === 'Decline').click()")
    phone.wait(f"document.getElementById('card').hidden && !document.getElementById('card-note').hidden && !{shell}")
    time.sleep(3)
    assert not phone.js(shell), "The stale-card note hid before it could be read."
    phone.wait(shell, timeout=10, why="The text did not tuck away again after the note.")

    # Work that waits on the owner marks the arrow.
    standin.WORK[:] = work
    hook({"do": "emit", "kind": "lists", "data": {"list": "work"}})
    phone.wait(f"{flag} && {label}.includes('waits on you')", why="Waiting work set no sign while collapsed.")

    # The arrow brings the text back and clears the sign.
    phone.js("document.getElementById('expand').click()")
    phone.wait(f"!{shell}")
    phone.wait(f"!{label}.includes('new repl')")
    assert phone.js("localStorage.getItem('rook.collapsed')") == "false"


def post(url, body):
    import urllib.request
    request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as res:
        return json.loads(res.read() or b"{}")


def shots(scratch, out):
    """The screens at both sizes, and at 390 px each presence form alone, for the side-by-side with the desktop."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for width, height, agent, insets in SIZES:
        server, fake = standin.serve("full")
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        hook = lambda body: post(base + "__test", body)
        phone = Phone(scratch, width, height, agent, insets, quiet=False)
        name = lambda n: out / f"v3-{width}x{height}-{n}.png"
        try:
            phone.go(base)
            phone.wait("!document.getElementById('pair').hidden")
            phone.shot(name("8-pairing"))
            phone.pair("418207")
            phone.wait("!document.getElementById('shell').hidden && app.connected && RookPresence.forms().length > 0")
            time.sleep(3.2)
            phone.shot(name("1-resting"))
            hook({"do": "set", "answer_delay": 60, "hold": True, "tone_seconds": 30})
            phone.js("document.getElementById('presence').click()")
            phone.wait("voice.phase === 'recording'")
            time.sleep(1.6)
            phone.shot(name("2-listening"))
            phone.js("document.getElementById('presence').click()")
            phone.wait("app.exchanges.some((x) => x.voice && x.text)", timeout=10)
            phone.wait("RookPresence.form() === 'lattice'", timeout=10)
            time.sleep(1.2)
            phone.shot(name("3-thinking"))
            phone.wait("document.querySelectorAll('article.turn:first-of-type .step').length === 4", timeout=90)
            time.sleep(1.4)
            phone.shot(name("5-activity"))
            hook({"do": "set", "hold": False})
            phone.wait("voice.playing", timeout=90)
            time.sleep(1.4)
            phone.shot(name("4-speaking"))
            phone.js("stopSpeech()")
            phone.js("(() => { const t = document.getElementById('ask-text'); t.value = 'Start the phone build on the "
                     "Opus thread and tell me when it is green.'; t.dispatchEvent(new Event('input')); t.focus(); })()")
            time.sleep(1.0)
            data = phone.page.call("Page.captureScreenshot", format="png")["data"]  # The field keeps its focus.
            name("6-typing").write_bytes(base64.b64decode(data))
            phone.js("(() => { const t = document.getElementById('ask-text'); t.value = ''; t.dispatchEvent(new Event('input')); })()")
            hook({"do": "open_card", "card": {"id": "card-s", "turn": "t-102", "tool": "Bash", "options": [],
                                              "question": "git -C ~/Code/rook push origin t3/phone-web-app\n"
                                                          "Push the phone app's branch to GitHub."}})
            phone.wait("!document.getElementById('card').hidden")
            time.sleep(1.4)
            phone.shot(name("7-card"))
            hook({"do": "close_card", "id": "card-s"})
            if width == 390:
                clip = phone.js("(() => { const r = document.getElementById('dust').getBoundingClientRect(); "
                                "return [r.x, r.y, r.width, r.height]; })()")
                for state, mood, kind, wait in (("resting", "resting", None, 3.2), ("listening", "listening", None, 1.6),
                                                ("transcribing", "transcribing", None, 1.6),
                                                ("thinking", "thinking", None, 1.6), ("thinking-rook", "thinking", None, 5.6),
                                                ("speaking", "speaking", None, 1.6), ("sending", "thinking", "sending", 1.6),
                                                ("running", "thinking", "running", 1.6)):
                    phone.js("renderPresence = () => {}; RookPresence.set('resting')")  # The check drives the presence.
                    time.sleep(0.2)
                    phone.js(f"RookPresence.set({json.dumps(mood)}, {json.dumps(kind)}, {json.dumps(state)})")
                    deadline = time.time() + wait
                    while time.time() < deadline:
                        if mood == "listening":
                            phone.js(f"RookPresence.setLevel({0.25 + 0.5 * abs(math.sin(time.time() * 7))})")
                        time.sleep(0.03)
                    x, y, w, h = clip
                    data = phone.page.call("Page.captureScreenshot", format="png",
                                           clip={"x": x, "y": y, "width": w, "height": h, "scale": 1})["data"]
                    (out / f"v3-presence-{state}.png").write_bytes(base64.b64decode(data))
        finally:
            phone.close()
            server.shutdown()
    print(f"Phone app: screenshots in {out}")


def main():
    parser = argparse.ArgumentParser(description="Check the phone app, or take its screenshots.")
    parser.add_argument("--shots", metavar="DIR")
    parser.add_argument("--server", action="store_true", help="Test against desktop/server.py.")
    args = parser.parse_args()
    scratch = tempfile.mkdtemp(prefix="rook-phone-check-")
    try:
        shots(scratch, args.shots) if args.shots else check(scratch, use_server=args.server)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
