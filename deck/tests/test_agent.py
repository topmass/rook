"""The Deck agent API (token auth, /health, /window, /capture, /type, /note) and the overlay feed (/overlay and its
event stream), each served on a free loopback port with fakes behind it."""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402

from rook_deck import agent, capture, channel, env, httpc, notes  # noqa: E402
from rook_deck.uinput import Typist  # noqa: E402

TOKEN = "t0k3n-" + "x" * 40


class FakeGrabber:
    """A grabber whose frame is a known gradient: pixel (x, y) is (x % 256, y % 256, 7)."""

    def __init__(self, width=64, height=40, available=True):
        rgb = bytearray()
        for y in range(height):
            for x in range(width):
                rgb += bytes((x % 256, y % 256, 7))
        self.frame = capture.Frame(width, height, bytes(rgb), 0.0) if available else None
        self.running = False
        self.error = None

    async def latest(self, wait=0.9):
        return self.frame

    def touch(self):
        pass

    async def stop(self):
        pass


class SlowTypist:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.typed = []

    @property
    def busy(self):
        return self.lock.locked()

    async def type_chat(self, text):
        async with self.lock:
            await asyncio.sleep(0.3)
            self.typed.append(text)


class AgentApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.window = {"app": "World of Warcraft", "width": 1280, "height": 800}
        self.grabber = FakeGrabber()
        session = env.detect()
        self.capture = capture.Capture(self.grabber, capture.Encoder(session))
        self.typist = SlowTypist()
        self.addons = tempfile.TemporaryDirectory()
        self.addons_dir = Path(self.addons.name)

        async def window():
            return dict(self.window)

        async def note(text):
            return await asyncio.to_thread(notes.send, text, self.addons_dir)

        deck = agent.DeckAgent(lambda: TOKEN, window=window, capture=self.capture.region, typist=self.typist,
                               note=note, log=support.log)
        self.server = await agent.serve_agent(deck, "127.0.0.1", 0)
        self.base = httpc.parse_base(f"http://127.0.0.1:{self.server.port}")

    async def asyncTearDown(self):
        await self.server.close()
        self.addons.cleanup()

    async def call(self, method, path, body=None, token=TOKEN, scheme="Bearer"):
        headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        return await httpc.request(self.base, method, path, headers=headers, body=data, timeout=5)

    async def test_health_needs_no_token(self):
        answer = await self.call("GET", "/health", token=None)
        self.assertEqual(answer.status, 200)
        self.assertEqual(answer.json()["ok"], True)
        self.assertTrue(answer.json()["version"])

    async def test_token(self):
        for token, scheme in ((None, "Bearer"), ("wrong", "Bearer"), (TOKEN, "Basic"), (TOKEN[:-1], "Bearer"),
                              ("", "Bearer")):
            answer = await self.call("GET", "/window", token=token, scheme=scheme)
            self.assertEqual(answer.status, 401, (token, scheme))
            self.assertEqual(answer.json(), {"ok": False, "error": "Unauthorized."})
        self.assertEqual((await self.call("GET", "/window")).status, 200)
        self.assertEqual((await self.call("GET", "/nope")).status, 404)
        self.assertEqual((await self.call("POST", "/window", {})).status, 405)

    async def test_window(self):
        answer = (await self.call("GET", "/window")).json()
        self.assertEqual(answer, {"wow_focused": True, "app": "World of Warcraft", "width": 1280, "height": 800})
        self.window["app"] = "Steam Big Picture Mode"
        self.assertFalse((await self.call("GET", "/window")).json()["wow_focused"])
        self.window["app"] = None
        self.assertEqual((await self.call("GET", "/window")).json()["app"], None)

    async def test_capture_ppm_is_the_exact_region(self):
        answer = await self.call("GET", "/capture?x=3&y=5&w=4&h=2&scale=1&kind=ppm")
        self.assertEqual(answer.status, 200)
        self.assertEqual(answer.header("content-type"), "image/x-portable-pixmap")
        head, pixels = answer.body[:11], answer.body[11:]
        self.assertEqual(head, b"P6\n4 2\n255\n")
        expected = b"".join(bytes((x, y, 7)) for y in (5, 6) for x in (3, 4, 5, 6))
        self.assertEqual(pixels, expected)

    async def test_capture_scale_and_jpeg(self):
        answer = await self.call("GET", "/capture?x=0&y=0&w=64&h=40&scale=0.5&kind=ppm")
        self.assertTrue(answer.body.startswith(b"P6\n32 20\n255\n"))
        answer = await self.call("GET", "/capture?x=0&y=0&w=64&h=40&scale=0.5")
        self.assertEqual(answer.status, 200)
        self.assertEqual(answer.header("content-type"), "image/jpeg")
        self.assertTrue(answer.body.startswith(b"\xff\xd8") and answer.body.endswith(b"\xff\xd9"))

    async def test_capture_refusals(self):
        for query in ("x=0&y=0&w=0&h=4", "x=a&y=0&w=1&h=1", "x=0&y=0&w=1&h=1&scale=2", "x=0&y=0&w=1&h=1&kind=png"):
            self.assertEqual((await self.call("GET", f"/capture?{query}")).status, 400, query)
        self.grabber.frame = None
        self.assertEqual((await self.call("GET", "/capture?x=0&y=0&w=4&h=4")).status, 503)

    async def test_type(self):
        self.assertEqual((await self.call("POST", "/type", {"text": "hi"})).status, 400)
        self.assertEqual((await self.call("POST", "/type", {"text": "hi", "approved": "yes"})).status, 400)
        self.assertEqual((await self.call("POST", "/type", {"text": "x" * 256, "approved": True})).status, 400)
        self.assertEqual((await self.call("POST", "/type", {"text": "naïve", "approved": True})).status, 400)
        first = asyncio.create_task(self.call("POST", "/type", {"text": "/r on my way", "approved": True}))
        await support.until(lambda: self.typist.busy, what="typing to start")
        busy = await self.call("POST", "/type", {"text": "second", "approved": True})
        self.assertEqual(busy.status, 409)
        self.assertEqual((await first).status, 200)
        self.assertEqual(self.typist.typed, ["/r on my way"])

    async def test_note(self):
        missing = await self.call("POST", "/note", {"text": "hello"})
        self.assertEqual(missing.status, 404)
        (self.addons_dir / "WoWFriend").mkdir()
        (self.addons_dir / "WoWFriend/WoWFriend.toc").write_text("## Interface: 16001\n")
        (self.addons_dir / "WoWFriend/Bells").mkdir()
        self.assertEqual((await self.call("POST", "/note", {"text": "hello"})).status, 503)
        channel.install(self.addons_dir)
        sent = await self.call("POST", "/note", {"text": "Turn in the quest at the inn."})
        self.assertEqual(sent.status, 200, sent.body)
        self.assertEqual(sent.json(), {"ok": True, "n": 1})
        inbox = (self.addons_dir / "WoWFriend_R01/Inbox.lua").read_text()
        self.assertTrue(inbox.startswith("WoWFriendChannel_Inbox = {n=1,"))
        self.assertIn('text="Turn in the quest at the inn."', inbox)
        self.assertEqual(channel.bell(self.addons_dir, 1).stat().st_size, 441044)
        self.assertEqual((await self.call("POST", "/note", {"text": "x" * 301})).status, 400)
        self.assertEqual((await self.call("POST", "/note", {"text": "   "})).status, 400)
        self.assertEqual((await self.call("POST", "/note", {"nope": 1})).status, 400)
        self.assertEqual((await self.call("POST", "/note", {"text": "second"})).json()["n"], 2)


class Notes(unittest.TestCase):
    def test_detect_prefers_wowfriend_and_forever(self):
        with tempfile.TemporaryDirectory() as home:
            drive = Path(home, ".local/share/Steam/steamapps/compatdata/3000000001/pfx/drive_c")
            retail = drive / "Program Files (x86)/World of Warcraft/_retail_/Interface/AddOns"
            forever = drive / "Program Files (x86)/World of Warcraft/_forever_/Interface/AddOns"
            lutris = Path(home, "Games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_classic_era_/"
                                "Interface/AddOns")
            for folder in (retail, forever, lutris):
                folder.mkdir(parents=True)
            self.assertEqual(notes.detect(home, media_globs=()), forever)
            (lutris / "WoWFriend").mkdir()
            (lutris / "WoWFriend/WoWFriend.toc").write_text("")
            self.assertEqual(notes.detect(home, media_globs=()), lutris, "an install with WoWFriend wins")
            self.assertEqual(notes.describe(lutris), {"addons_dir": str(lutris), "wowfriend": True, "slots": False})
        with tempfile.TemporaryDirectory() as empty:
            self.assertIsNone(notes.detect(empty, media_globs=()))


class OverlayFeedServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.page = tempfile.TemporaryDirectory()
        Path(self.page.name, "index.html").write_text("<!doctype html><title>Rook Overlay</title>")
        Path(self.page.name, "overlay.js").write_text("// js")
        self.feed = agent.OverlayFeed()
        self.server = await agent.serve_overlay(agent.OverlayServer(self.feed, Path(self.page.name)), port=0)
        self.base = httpc.parse_base(f"http://127.0.0.1:{self.server.port}")

    async def asyncTearDown(self):
        await self.server.close()
        self.page.cleanup()

    async def test_page_files(self):
        page = await httpc.request(self.base, "GET", "/overlay")
        self.assertEqual(page.status, 200)
        self.assertIn(b"Rook Overlay", page.body)
        self.assertTrue(page.header("content-type").startswith("text/html"))
        script = await httpc.request(self.base, "GET", "/overlay/overlay.js")
        self.assertEqual(script.status, 200)
        self.assertEqual((await httpc.request(self.base, "GET", "/overlay/missing.css")).status, 404)
        self.assertEqual((await httpc.request(self.base, "GET", "/overlay/../../etc/passwd")).status, 404)
        self.assertEqual((await httpc.request(self.base, "GET", "/overlay/%2e%2e/secret")).status, 404)

    async def test_missing_page_is_404(self):
        Path(self.page.name, "index.html").unlink()
        self.assertEqual((await httpc.request(self.base, "GET", "/overlay")).status, 404)

    async def test_event_stream(self):
        from rook_deck.client import SseParser
        async with httpc.Stream(self.base, "/overlay/events", {}) as stream:
            self.assertEqual(stream.status, 200)
            self.assertEqual(stream.response_headers["content-type"], ["text/event-stream"])
            parser, seen = SseParser(), []
            chunks = stream.chunks()

            async def next_picture():
                while not seen:
                    seen.extend(parser.feed(await chunks.__anext__()))
                return json.loads(seen.pop(0).data)

            self.assertEqual(await next_picture(), {"state": "resting", "text": "", "draft": None})
            self.feed.set("thinking", "Half an answer", None)
            self.assertEqual(await next_picture(), {"state": "thinking", "text": "Half an answer", "draft": None})
            self.feed.set("transcribing", "x", None)  # Not one of the contract's five: shown as resting.
            self.assertEqual((await next_picture())["state"], "resting")


if __name__ == "__main__":
    unittest.main()
