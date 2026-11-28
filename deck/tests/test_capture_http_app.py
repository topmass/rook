"""The warm capture pipeline with GStreamer's test source in place of gamescope's PipeWire node; the HTTP client's
address and framing rules; and the App and main.py wired together with fakes for the Deck's hardware."""

import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402

from rook_deck import capture, env, httpc  # noqa: E402
from rook_deck.app import App  # noqa: E402

GST = shutil.which("gst-launch-1.0") is not None
TEST_SOURCE = ("videotestsrc is-live=true pattern=solid-color foreground-color=0xff3366cc "
               "! video/x-raw,width=320,height=200,framerate=10/1")


@unittest.skipUnless(GST, "GStreamer is not installed")
class WarmPipeline(unittest.IsolatedAsyncioTestCase):
    async def test_frames_size_and_idle_stop(self):
        grabber = capture.Grabber(env.detect(), support.log, source=TEST_SOURCE)
        cap = capture.Capture(grabber, capture.Encoder(env.detect()))
        try:
            started = time.monotonic()
            found = await cap.region(10, 20, 30, 4, 1, "ppm")
            self.assertIsNotNone(found, grabber.error)
            self.assertLess(time.monotonic() - started, 1.0, "a cold start answers inside the second")
            kind, data = found
            self.assertEqual(data[:12], b"P6\n30 4\n255\n")
            self.assertEqual(data[12:15], bytes((0x33, 0x66, 0xCC)))
            self.assertEqual(cap.size(), (320, 200))
            started = time.monotonic()
            for _ in range(3):
                self.assertIsNotNone(await cap.region(0, 0, 320, 24, 1, "ppm"))
            self.assertLess(time.monotonic() - started, 0.5, "a warm pipeline answers at once")
            kind, jpeg = await cap.region(0, 0, 320, 200, 1, "jpeg")
            self.assertEqual(kind, "image/jpeg")
            self.assertTrue(jpeg.startswith(b"\xff\xd8"))
            capture.IDLE_SECONDS, old = 0.1, capture.IDLE_SECONDS
            try:
                grabber.last_request = 0
                await support.until(lambda: not grabber.running, timeout=5, what="the idle stop")
            finally:
                capture.IDLE_SECONDS = old
        finally:
            await grabber.stop()

    async def test_region_outside_the_picture(self):
        frame = capture.Frame(4, 4, bytes(48), 0)
        with self.assertRaises(capture.CaptureError):
            capture.crop_scale(frame, 10, 10, 2, 2, 1)
        width, height, rgb = capture.crop_scale(frame, 2, 2, 10, 10, 1)  # Clipped to the picture.
        self.assertEqual((width, height, len(rgb)), (2, 2, 12))


class Addresses(unittest.TestCase):
    def test_lan_http_is_the_default(self):
        base = httpc.parse_base("192.168.1.20:47326")
        self.assertEqual((base.scheme, base.host, base.port, base.netloc), ("http", "192.168.1.20", 47326,
                                                                            "192.168.1.20:47326"))
        self.assertEqual(base.origin, "http://192.168.1.20:47326")
        base = httpc.parse_base(" http://192.168.1.20:47326/ ")
        self.assertEqual(base.origin, "http://192.168.1.20:47326")

    def test_https_and_default_ports(self):
        base = httpc.parse_base("https://Oak.Tail.ts.net:8447")
        self.assertEqual((base.port, base.origin), (8447, "https://oak.tail.ts.net:8447"))
        self.assertEqual(httpc.parse_base("https://oak.tail.ts.net").netloc, "oak.tail.ts.net")
        self.assertEqual(httpc.parse_base("http://[fd00::5]:47326").netloc, "[fd00::5]:47326")

    def test_refusals(self):
        for bad in ("", "ftp://x", "http://", "http://host/path", "http://u:p@host", "http://host:port"):
            with self.assertRaises(ValueError):
                httpc.parse_base(bad)


class Framing(unittest.IsolatedAsyncioTestCase):
    async def test_headers_sent_and_chunked_answer(self):
        seen = {}

        async def serve(reader, writer):
            head = await reader.readuntil(b"\r\n\r\n")
            seen["head"] = head.decode()
            writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nSet-Cookie: a=b; Secure\r\n\r\n"
                         b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n")
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            base = httpc.parse_base(f"http://127.0.0.1:{port}")
            answer = await httpc.request(base, "POST", "/command", body=b"{}", headers={"Origin": base.origin})
        finally:
            server.close()
        self.assertEqual(answer.body, b"hello world")
        self.assertEqual(httpc.cookie_from(answer, "a"), "b")
        lines = seen["head"].split("\r\n")
        self.assertEqual(lines[0], "POST /command HTTP/1.1")
        self.assertEqual([line for line in lines if line.startswith("Host:")], [f"Host: 127.0.0.1:{port}"])
        self.assertIn(f"Origin: http://127.0.0.1:{port}", lines)
        self.assertIn("Content-Length: 2", lines)
        self.assertFalse(any(line.lower().startswith("transfer-encoding") for line in lines))

    async def test_unreachable(self):
        with self.assertRaises(httpc.HttpError):
            await httpc.request(httpc.parse_base("http://127.0.0.1:1"), "GET", "/snapshot", timeout=2)


class Wiring(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.events = []
        self.app = App(os.path.join(self.folder.name, "settings"), str(support.ROOT),
                       emit=lambda name, event: self.events.append((name, event)), log=support.log,
                       agent_host="127.0.0.1", agent_port=0, overlay_port=0, hardware=False,
                       recorder=support.FakeRecorder(b"OggS"), player=support.FakePlayer())
        await self.app.start()

    async def asyncTearDown(self):
        await self.app.stop()
        self.folder.cleanup()

    async def test_status_hotkey_token(self):
        status = await self.app.get_status()
        self.assertFalse(status["paired"])
        self.assertEqual(status["hotkey"], "L4")
        self.assertIn("L1+R1+A", status["hotkeys"])
        self.assertEqual(status["wow"]["addons_dir"], None)
        json.dumps(status)  # Decky sends it as JSON.
        self.assertEqual((await self.app.set_hotkey("r1 + l1"))["hotkey"], "R1+L1")
        self.assertEqual((await self.app.set_hotkey("off"))["hotkey"], "off")
        self.assertFalse((await self.app.set_hotkey("Z9"))["ok"])
        token = self.app.deck_token()
        self.assertGreaterEqual(len(token["token"]), 32)
        self.assertEqual(token["token"], self.app.store.deck_token(), "the token is made once and kept")
        self.assertTrue(token["url"].startswith("http://"))
        self.assertEqual(self.events[-1][0], "rook_event")

    async def test_agent_and_overlay_servers_run(self):
        ports = [s.port for s in self.app.servers]
        self.assertEqual(len(ports), 2)
        overlay, deck = (httpc.parse_base(f"http://127.0.0.1:{p}") for p in ports)
        page = await httpc.request(overlay, "GET", "/overlay")
        self.assertEqual(page.status, 200 if (support.ROOT / "overlay/page/index.html").is_file() else 404)
        health = await httpc.request(deck, "GET", "/health")
        self.assertEqual(health.json()["ok"], True)
        denied = await httpc.request(deck, "GET", "/window")
        self.assertEqual(denied.status, 401)

    async def test_overlay_position(self):
        self.assertEqual((await self.app.get_status())["overlay_position"], "middle-right")
        result = await self.app.set_overlay_position("Bottom-Center")
        self.assertTrue(result["ok"], result)
        self.assertEqual((await self.app.get_status())["overlay_position"], "bottom-center")
        self.assertFalse((await self.app.set_overlay_position("centre"))["ok"])
        from rook_deck.app import overlay_geometry
        self.assertEqual(overlay_geometry("top-right", 1280, 800), "430x560+850+10")
        self.assertEqual(overlay_geometry("middle-left", 1280, 800), "430x560+10+120")
        self.assertEqual(overlay_geometry("bottom-center", 1280, 800), "720x260+280+530")

    async def test_addons_setting(self):
        result = await self.app.set_addons_dir(self.folder.name)
        self.assertTrue(result["ok"])
        self.assertEqual(result["addons_dir"], self.folder.name)
        self.assertFalse(result["wowfriend"])
        self.assertFalse((await self.app.set_addons_dir("/no/such/folder"))["ok"])


class MainPy(unittest.TestCase):
    def test_plugin_exposes_the_contracts_callables(self):
        fake = types.ModuleType("decky")
        fake.logger = support.log
        sys.modules["decky"] = fake
        spec = importlib.util.spec_from_file_location("rook_main", support.ROOT / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ("get_status", "pair", "unpair", "talk_start", "talk_stop", "send_text", "stop", "get_history",
                     "get_deck_token", "set_hotkey", "answer_card", "set_addons_dir", "set_overlay_position", "_main", "_unload"):
            self.assertTrue(asyncio.iscoroutinefunction(getattr(module.Plugin, name)), name)


if __name__ == "__main__":
    unittest.main()
