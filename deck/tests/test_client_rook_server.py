"""The Rook client against Rook's real phone server (desktop/server.py) with its in-memory _FakeSession: the strict
HTTP/1.1 framing, the Host and Origin checks, and a cookie the server marks Secure, all over plain http on 127.0.0.1.
"""

import asyncio
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402

from rook_deck import httpc  # noqa: E402
from rook_deck.client import RookClient  # noqa: E402
from rook_deck.store import Store  # noqa: E402

SERVER_PY = support.ROOK / "desktop" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("rook_server", SERVER_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rook_server"] = module  # dataclasses look the module up by name.
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(SERVER_PY.is_file(), "Rook's desktop/server.py is not checked out")
class ClientAgainstRookServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.rs = load_server()
        self.scratch = tempfile.TemporaryDirectory()
        self.devices = self.rs.DeviceStore(Path(self.scratch.name) / "devices.db").open()
        self.code = self.devices.create_code(code="DECK42")
        self.session = self.rs._FakeSession()
        self.server = await self.rs.Server(self.session, self.devices, port=0, secure_cookies=True,
                                           pair_on_loopback=True, keepalive_seconds=0.2).start()
        self.url = f"http://127.0.0.1:{self.server.port}"
        self.store = Store(Path(self.scratch.name) / "deck")
        self.events = support.Events()
        self.player = support.FakePlayer()
        self.client = RookClient(self.store, self.events, recorder=support.FakeRecorder(support.make_ogg(0.8)),
                                 player=self.player, log=support.log)

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        self.scratch.cleanup()

    async def test_pair_attach_command_audio_speech(self):
        result = await self.client.pair(self.url, "deck 42")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["device"]["name"], "Steam Deck")
        self.assertTrue(self.client.cookie)
        await support.until(lambda: self.client.connected, what="the stream")

        sent = await self.client.send_text("hello from the Deck")
        await support.until(lambda: self.session.commands, what="the command")
        device_id, body = self.session.commands[0]
        self.assertEqual(device_id, result["device"]["id"])
        self.assertEqual((body["id"], body["kind"], body["text"], body["mode"]),
                         (sent["id"], "ask", "hello from the Deck", "queue"))

        await self.client.talk_start()
        await self.client.talk_stop()
        await support.until(lambda: self.session.audios, what="the recording")
        self.assertEqual(self.session.audios[0][2], "audio/ogg")

        # A stored event and a live speech piece for this device reach the client through the stream.
        self.session.emit("request", {"turn": "t-1", "state": "working", "text": "hello from the Deck"})
        await support.until(lambda: self.client.find("t-1"), what="the stored event")
        # session.live() marks live events {"live": true}; the fake's emit does not, so the test adds it.
        # Speech for an older turn than the newest is skipped, as on the phone; the newest turn's plays.
        self.session.emit("speech", {"turn": "t-1", "index": 0, "id": "clip-1", "text": "Old.",
                                     "device": result["device"]["id"], "live": True}, live=True)
        await asyncio.sleep(0.3)
        self.assertEqual(self.player.clips, [])
        self.session.emit("speech", {"turn": "t-audio", "index": 0, "id": "clip-1", "text": "Hi.",
                                     "device": result["device"]["id"], "live": True}, live=True)
        await support.until(lambda: self.player.clips, what="the speech clip")
        self.assertEqual(self.player.clips[0], ("audio/ogg", b"0123456789"))

    async def test_wrong_origin_is_what_the_server_refuses(self):
        """The check the client passes: Rook's server refuses a POST whose Origin is not scheme://Host."""
        base = httpc.parse_base(self.url)
        refused = await httpc.request(base, "POST", "/pair", body=b'{"code":"DECK42","name":"x"}', headers={
            "Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(refused.status, 403)
        ok = await self.client.pair(self.url, "DECK42")
        self.assertTrue(ok["ok"], ok)


if __name__ == "__main__":
    unittest.main()
