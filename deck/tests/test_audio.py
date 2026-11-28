"""Recording and playback through the real GStreamer on this PC, with a test tone instead of the microphone and
fakesink instead of the speaker, so nothing is heard and no microphone opens. Also the X11 reader against this
PC's own display, read-only, when there is one."""

import asyncio
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402

from rook_deck import audio, env, x11  # noqa: E402

GST = shutil.which("gst-launch-1.0") is not None


@unittest.skipUnless(GST, "GStreamer is not installed")
class Recording(unittest.IsolatedAsyncioTestCase):
    async def test_ogg_opus_from_a_test_tone(self):
        recorder = audio.Recorder(env.detect(), support.log, gst_source="audiotestsrc is-live=true wave=sine",
                                  backends=("gst",))
        self.assertTrue((await recorder.available())["gst"])
        await recorder.start()
        self.assertTrue(recorder.recording)
        await asyncio.sleep(1.0)
        got = await recorder.stop()
        self.assertFalse(recorder.recording)
        self.assertEqual(got.content_type, "audio/ogg")
        self.assertGreater(got.seconds, 0.9)
        self.assertTrue(got.data.startswith(b"OggS"), got.data[:8])
        self.assertIn(b"OpusHead", got.data[:200])
        # SIGINT ended the stream: the last Ogg page carries the end-of-stream flag (header type 0x04).
        last = got.data.rfind(b"OggS")
        self.assertTrue(got.data[last + 5] & 0x04, "the file is whole")

    async def test_cancel_keeps_nothing(self):
        recorder = audio.Recorder(env.detect(), support.log, gst_source="audiotestsrc is-live=true",
                                  backends=("gst",))
        await recorder.start()
        await recorder.cancel()
        self.assertIsNone(await recorder.stop())

    async def test_no_recorder_says_so(self):
        recorder = audio.Recorder(env.detect(), support.log, backends=())
        with self.assertRaises(audio.AudioError):
            await recorder.start()


@unittest.skipUnless(GST, "GStreamer is not installed")
class Playback(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.player = audio.Player(env.detect(), support.log, gst_sink="fakesink sync=true", backends=("gst",))

    async def test_plays_a_clip_to_its_end(self):
        standin = support.load_standin()
        self.assertTrue(await self.player.play(standin.tone(0.2, 440), "audio/wav"))
        self.assertTrue(await self.player.play(support.make_ogg(0.3), "audio/ogg"))

    async def test_stop_cuts_it(self):
        standin = support.load_standin()
        task = asyncio.create_task(self.player.play(standin.tone(5.0, 440), "audio/wav"))
        await asyncio.sleep(0.4)
        await self.player.stop()
        self.assertFalse(await asyncio.wait_for(task, 3))


class ChildEnvironment(unittest.TestCase):
    def test_decky_library_path_is_dropped(self):
        session = env.Session(user="deck", uid=1000, gid=1000, home="/home/deck", runtime_dir="/run/user/1000")
        os.environ["LD_LIBRARY_PATH"] = "/tmp/_MEIxyz"
        try:
            child = session.child_env()
            self.assertNotIn("LD_LIBRARY_PATH", child)
            os.environ["LD_LIBRARY_PATH_ORIG"] = "/usr/lib/extra"
            self.assertEqual(session.child_env()["LD_LIBRARY_PATH"], "/usr/lib/extra")
        finally:
            os.environ.pop("LD_LIBRARY_PATH", None)
            os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
        self.assertEqual(child["XDG_RUNTIME_DIR"], "/run/user/1000")
        self.assertEqual(child["PULSE_SERVER"], "unix:/run/user/1000/pulse/native")


@unittest.skipUnless(os.environ.get("DISPLAY", "").startswith(":") and
                     os.path.exists(f"/tmp/.X11-unix/X{os.environ.get('DISPLAY', ':0')[1:].split('.')[0]}"),
                     "no local X display")
class RealDisplay(unittest.TestCase):
    def test_reads_this_pcs_display(self):
        focus = x11.read_focus(os.environ["DISPLAY"], os.environ.get("XAUTHORITY"))
        self.assertIsInstance(focus.root_size, tuple)  # No gamescope here: its atoms are simply unset.


if __name__ == "__main__":
    unittest.main()
