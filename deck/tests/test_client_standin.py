"""The Rook client against Rook's own phone stand-in (phone/standin.py), over plain http on 127.0.0.1: pairing, a
typed request, a recording upload, speech, the stream's reconnect and replay, stop, cards, and losing the pairing.

The stand-in checks the phone app's rules as Rook's server does: the cookie, Origin equal to http://<Host>, JSON
bodies, X-Rook-Command and the audio types.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402

from rook_deck import httpc  # noqa: E402
from rook_deck.client import RookClient  # noqa: E402
from rook_deck.store import Store  # noqa: E402

standin = support.load_standin()


class ClientAgainstStandin(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server, self.fake = standin.serve("empty", 0)
        self.fake.answer_delay = 0.4
        self.fake.tone_seconds = 0.05
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(self.folder.name)
        self.events = support.Events()
        self.overlay = []
        self.player = support.FakePlayer()
        self.recorder = support.FakeRecorder(support.make_ogg(1.0))
        self.client = self.make_client()
        RookClient.RETRY_SECONDS = 0.3
        RookClient.STREAM_RETRY_SECONDS = 0.2

    def make_client(self):
        return RookClient(self.store, self.events, recorder=self.recorder, player=self.player, log=support.log,
                          on_overlay=lambda *picture: self.overlay.append(picture))

    async def asyncTearDown(self):
        await self.client.close()
        self.server.shutdown()
        self.server.server_close()
        self.folder.cleanup()

    async def pair(self):
        result = await self.client.pair(self.url, "418 207")
        self.assertTrue(result["ok"], result)
        await support.until(lambda: self.client.connected, what="the event stream")
        return result

    async def test_pairing(self):
        wrong = await self.client.pair(self.url, "000000")
        self.assertFalse(wrong["ok"])
        self.assertIn("code", wrong["error"])
        result = await self.pair()
        self.assertEqual(result["device"]["name"], "Steam Deck")
        saved = json.loads((self.store.path).read_text())
        self.assertEqual(saved["server_url"], self.url)
        self.assertTrue(saved["cookie"])
        self.assertEqual(saved["device"]["id"], "dev-phone")
        self.assertEqual(oct(self.store.path.stat().st_mode & 0o777), "0o600")
        # A restart reads the cookie back and attaches without pairing again.
        await self.client.close()
        again = self.make_client()
        self.assertTrue(again.paired)
        again.start()
        try:
            await support.until(lambda: again.connected, what="a restarted client's stream")
        finally:
            await again.close()

    async def test_bad_address(self):
        result = await self.client.pair("ftp://example", "418207")
        self.assertFalse(result["ok"])
        result = await self.client.pair("http://127.0.0.1:1", "418207")
        self.assertFalse(result["ok"])
        self.assertIn("did not answer", result["error"])

    async def test_typed_request(self):
        await self.pair()
        sent = await self.client.send_text("How is the build?")
        self.assertTrue(sent["ok"])
        exchange = await support.until(lambda: next((x for x in self.client.exchanges if x.get("answer")), None),
                                       what="the answer")
        self.assertIn("How is the build?", exchange["answer"])
        self.assertIn(sent["id"], self.fake.command_ids)
        self.assertEqual(self.fake.command_ids.count(sent["id"]), 1)
        kinds = {e["type"] for e in self.events.items}
        self.assertTrue({"activity", "draft", "answer", "state"} <= kinds, kinds)
        self.assertEqual(self.store.load_outbox(), [])
        history = self.client.history()
        self.assertEqual(history[-1]["request"], "How is the build?")
        self.assertTrue(history[-1]["answer"])
        # The overlay saw Rook think and then rest with the answer's words.
        states = [picture[0] for picture in self.overlay]
        self.assertIn("thinking", states)
        self.assertEqual(self.overlay[-1][0], "resting")
        self.assertIn("You asked", self.overlay[-1][1])

    async def test_outbox_waits_for_rook(self):
        self.store.set(server_url="http://127.0.0.1:1", cookie="x" * 40, device={"id": "dev-phone"})
        offline = self.make_client()
        sent = await offline.send_text("Queued while away")
        self.assertTrue(sent["queued"])
        self.assertEqual([m["text"] for m in self.store.load_outbox()], ["Queued while away"])
        await offline.close()
        # Pairing for real later sends what waited, once.
        self.client = self.make_client()
        await self.pair()
        await support.until(lambda: sent["id"] in self.fake.command_ids, what="the queued request")
        await support.until(lambda: not self.store.load_outbox(), what="an empty outbox")

    async def test_spoken_request_and_speech(self):
        await self.pair()
        started = await self.client.talk_start()
        self.assertTrue(started["ok"])
        self.assertEqual(self.client.mood(), "listening")
        result = await self.client.talk_stop()
        self.assertTrue(result["sent"], result)
        await support.until(lambda: self.fake.audio_uploads, what="the upload")
        command, content_type, size = self.fake.audio_uploads[0]
        self.assertEqual((command, content_type, size), (result["id"], "audio/ogg", len(self.recorder.data)))
        await support.until(lambda: len(self.player.clips) == 3, timeout=10, what="three pieces of speech")
        self.assertTrue(all(kind == "audio/wav" and data.startswith(b"RIFF") for kind, data in self.player.clips))
        exchange = next(x for x in self.client.exchanges if x.get("turn"))
        self.assertEqual(exchange["text"], standin.HEARD)
        await support.until(lambda: not self.client.voice.playing, what="speech to end")

    async def test_upload_retries_after_a_lost_answer(self):
        await self.pair()
        self.fake.test({"do": "set", "drop_next_audio": True})
        await self.client.talk_start()
        await self.client.talk_stop()
        await support.until(lambda: len(self.fake.audio_uploads) >= 2, what="the retry")
        ids = {upload[0] for upload in self.fake.audio_uploads}
        self.assertEqual(len(ids), 1, "a retry reuses the recording's command id")
        await support.until(lambda: self.client.voice.pending is None, what="the upload to be taken")

    async def test_too_short_is_not_sent(self):
        await self.pair()
        self.recorder.seconds = 0.2
        await self.client.talk_start()
        result = await self.client.talk_stop()
        self.assertFalse(result["ok"])
        self.assertEqual(self.fake.audio_uploads, [])
        self.assertTrue(self.events.of("error"))

    async def test_stream_reconnects_and_replays_once(self):
        await self.pair()
        starts = self.client.stream_starts
        cursor = self.client.last_id
        self.assertGreater(cursor, 0, "the snapshot's cursor")
        self.fake.test({"do": "cut_streams"})
        seq = self.fake.emit("request", {"turn": "t-900", "state": "accepted", "text": "while away"})
        await support.until(lambda: self.client.stream_starts > starts, what="the reconnect")
        await support.until(lambda: self.client.find("t-900"), what="the replayed event")
        self.assertEqual(self.fake.stream_starts[-1], cursor, "the reconnect resumes from the last id applied")
        self.assertGreaterEqual(self.client.last_id, seq)
        # The stand-in sends a stored event again under its old id: it applies once.
        before = len([x for x in self.client.exchanges if x.get("turn") == "t-900"])
        self.fake.test({"do": "emit", "kind": "request", "seq": seq,
                        "data": {"turn": "t-900", "state": "closed", "answer": "late"}})
        await asyncio.sleep(0.3)
        x = self.client.find("t-900")
        self.assertEqual(x["state"], "accepted", "an event under an id already applied is skipped")
        self.assertEqual(before, 1)

    async def test_refused_stream_backs_off_and_recovers(self):
        RookClient.BACKOFF_START = 0.1
        try:
            await self.pair()
            self.fake.test({"do": "set", "refuse_streams": True})
            self.fake.test({"do": "cut_streams"})
            await support.until(lambda: not self.client.connected, what="the drop")
            await asyncio.sleep(0.4)
            self.fake.test({"do": "set", "refuse_streams": False})
            await support.until(lambda: self.client.connected, what="the recovery")
        finally:
            RookClient.BACKOFF_START = 1.0

    async def test_snapshot_event_reads_everything_again(self):
        await self.pair()
        self.fake.test({"do": "emit", "kind": "request", "live": False,
                        "data": {"turn": "t-950", "state": "accepted", "text": "x"}})
        starts = self.client.stream_starts
        self.fake.test({"do": "emit", "kind": "snapshot", "data": {}})
        await support.until(lambda: self.client.stream_starts > starts, what="the re-attach")

    async def test_stop_ends_the_running_turn(self):
        await self.pair()
        self.fake.test({"do": "set", "hold": True})
        await self.client.send_text("Hold this one")
        await support.until(lambda: self.client.running_turn(), what="a running turn")
        await support.until(lambda: len(self.client.activity.get(self.client.running_turn(), [])) >= 4,
                            what="the held turn's steps")
        result = await self.client.stop()
        self.assertTrue(result["ok"] and result["stopped_turn"], result)
        self.assertEqual(self.fake.stop_commands[0]["kind"], "stop")
        await support.until(lambda: any(x.get("state") == "interrupted" for x in self.client.exchanges),
                            what="the interrupted turn")

    async def test_card_answer(self):
        await self.pair()
        await self.client.send_text("open a card please")
        card = await support.until(lambda: self.client.card, what="the card")
        self.assertEqual(self.client.mood(), "waiting")
        result = await self.client.answer_card(card["id"], "allow")
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.fake.card_answers[0]["allow"], True)
        self.assertEqual(self.fake.card_answers[0]["card"], card["id"])
        stale = await self.client.answer_card(card["id"], "decline")
        self.assertTrue(stale.get("stale"))
        refused = await self.client.answer_card(card["id"], "Option B")
        self.assertFalse(refused["ok"])

    async def test_lost_pairing(self):
        await self.pair()
        self.fake.tokens.clear()
        await self.client.send_text("anyone there?")
        await support.until(lambda: not self.client.paired, what="the unpairing")
        self.assertIsNone(json.loads(self.store.path.read_text())["cookie"])
        self.assertTrue(any(e.get("paired") is False for e in self.events.of("state")))

    async def test_unpair(self):
        await self.pair()
        result = await self.client.unpair()
        self.assertTrue(result["ok"])
        self.assertFalse(self.client.paired)


class SecureCookieOverHttp(unittest.TestCase):
    def test_cookie_kept_whatever_its_attributes(self):
        response = httpc.Response(200, {"set-cookie": [
            "other=1; Path=/", "rook_device=abc_DEF-123; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict; Secure"]})
        self.assertEqual(httpc.cookie_from(response, "rook_device"), "abc_DEF-123")


if __name__ == "__main__":
    unittest.main()
