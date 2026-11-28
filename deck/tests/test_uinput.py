"""The uinput keyboard: the ioctl numbers, the US layout map, the event encoding, and the typing plan (Enter, text,
Enter), decoded back to text through a fake keyboard. /dev/uinput itself is never opened."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402,F401

from rook_deck import uinput as u  # noqa: E402


class FakeKeyboard:
    def __init__(self):
        self.fd = None
        self.frames = []
        self.opened = 0

    def open(self):
        self.fd = 99
        self.opened += 1

    def write_frame(self, frame):
        self.frames.append(frame)

    def close(self):
        self.fd = None


def replay(frames):
    """Typed text from key frames, as a US-layout keyboard reader would see it."""
    reverse = {(code, shift): ch for ch, (code, shift) in u.KEYMAP.items()}
    shift, out = False, []
    for frame in frames:
        for etype, code, value in frame:
            if etype != u.EV_KEY:
                continue
            if code == u.KEY_LEFTSHIFT:
                shift = value == 1
            elif code == u.KEY_ENTER and value == 1:
                out.append("\n")
            elif value == 1:
                out.append(reverse[(code, shift)])
    return "".join(out)


class Encoding(unittest.TestCase):
    def test_ioctl_numbers(self):
        self.assertEqual(u.UI_SET_EVBIT, 0x40045564)
        self.assertEqual(u.UI_SET_KEYBIT, 0x40045565)
        self.assertEqual(u.SETUP.size, 92)
        self.assertEqual(u.UI_DEV_SETUP, 0x405C5503)

    def test_every_printable_ascii_character_has_a_key(self):
        for code in range(32, 127):
            self.assertIn(chr(code), u.KEYMAP)
        self.assertEqual(u.KEYMAP["a"], (30, False))
        self.assertEqual(u.KEYMAP["A"], (30, True))
        self.assertEqual(u.KEYMAP["!"], (2, True))
        self.assertEqual(u.KEYMAP["/"], (53, False))
        self.assertEqual(u.KEYMAP["?"], (53, True))

    def test_event_bytes(self):
        raw = u.encode_frames(u.key_strokes("a"))
        events = [struct.unpack("@llHHi", raw[i:i + 24]) for i in range(0, len(raw), 24)]
        self.assertEqual([e[2:] for e in events], [(1, 30, 1), (0, 0, 0), (1, 30, 0), (0, 0, 0)])

    def test_text_checks(self):
        self.assertEqual(u.check_text("/w Bob hi!"), "/w Bob hi!")
        for bad in ("", "x" * 256, "café", "tab\there", "line\nbreak", None):
            with self.assertRaises(ValueError):
                u.check_text(bad)
        self.assertEqual(len(u.check_text("x" * 255)), 255)


class Typing(unittest.IsolatedAsyncioTestCase):
    async def test_enter_text_enter(self):
        keyboard = FakeKeyboard()
        pauses = []

        async def sleep(seconds):
            pauses.append(seconds)

        typist = u.Typist(keyboard, sleep=sleep)
        text = '/r On my way! (2 min) "ok"?'
        await typist.type_chat(text)
        self.assertEqual(replay(keyboard.frames), "\n" + text + "\n")
        self.assertEqual(pauses[0], u.Typist.SETTLE_SECONDS, "a new keyboard settles before its first key")
        await typist.type_chat("again")
        self.assertEqual(keyboard.opened, 1, "the keyboard is made once and kept")
        self.assertFalse(typist.busy)

    async def test_refused_text_types_nothing(self):
        keyboard = FakeKeyboard()
        typist = u.Typist(keyboard)
        with self.assertRaises(ValueError):
            await typist.type_chat("naïve")
        self.assertEqual(keyboard.frames, [])
        self.assertIsNone(keyboard.fd)


if __name__ == "__main__":
    unittest.main()
