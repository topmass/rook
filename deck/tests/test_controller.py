"""The talk chord: raw evdev input_event parsing, the Deck's raw HID report, chords per source, and the watcher's
read loop over a FIFO that stands in for the Deck's hidraw node. No real input device is opened."""

import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402,F401

from rook_deck import controller as c  # noqa: E402

A, B, TL, TR = 0x130, 0x131, 0x136, 0x137
MAPPING = {code: name for code, name in c.EVDEV_BUTTONS.items()}


def frame(*events):
    return b"".join(c.pack_event(*e) for e in events) + c.pack_event(c.EV_SYN, c.SYN_REPORT, 0)


class EvdevParsing(unittest.TestCase):
    def test_struct_is_the_64_bit_input_event(self):
        self.assertEqual(c.EVENT.size, 24)
        raw = c.pack_event(c.EV_KEY, A, 1, sec=5, usec=7)
        self.assertEqual(c.EVENT.unpack(raw), (5, 7, c.EV_KEY, A, 1))

    def test_press_and_release(self):
        state = c.EvdevState(MAPPING)
        frames = state.feed_bytes(frame((c.EV_KEY, A, 1), (c.EV_KEY, TL, 1)))
        self.assertEqual(len(frames), 1)
        self.assertTrue(frames[0]["A"] and frames[0]["L1"])
        self.assertFalse(frames[0]["B"])
        frames = state.feed_bytes(frame((c.EV_KEY, A, 0)))
        self.assertFalse(frames[0]["A"])
        self.assertTrue(frames[0]["L1"])

    def test_autorepeat_and_partial_records_are_ignored(self):
        state = c.EvdevState(MAPPING)
        data = frame((c.EV_KEY, A, 1), (c.EV_KEY, A, 2))
        frames = state.feed_bytes(data + data[:10])  # A torn record at the end is left for the next read.
        self.assertTrue(frames[-1]["A"])

    def test_syn_dropped_resyncs_from_the_device(self):
        state = c.EvdevState(MAPPING, resync=lambda: ({B}, {}))
        state.feed_bytes(frame((c.EV_KEY, A, 1)))
        frames = state.feed_bytes(c.pack_event(c.EV_SYN, c.SYN_DROPPED, 0) + frame((c.EV_KEY, TL, 1)))
        # Events between SYN_DROPPED and the next SYN_REPORT are not trusted; the state is read anew.
        self.assertEqual(len(frames), 1)
        self.assertTrue(frames[0]["B"])
        self.assertFalse(frames[0]["A"] or frames[0]["L1"])

    def test_triggers_and_hat(self):
        state = c.EvdevState(MAPPING, {0x02: (0, 255), 0x05: (0, 255), 0x10: (-1, 1), 0x11: (-1, 1)})
        frames = state.feed_bytes(frame((c.EV_ABS, 0x02, 200), (c.EV_ABS, 0x05, 20), (c.EV_ABS, 0x11, -1)))
        self.assertTrue(frames[0]["L2"])
        self.assertFalse(frames[0].get("R2"))
        self.assertTrue(frames[0]["DUp"])


class DeckReport(unittest.TestCase):
    def test_every_button_round_trips(self):
        for name in c.DECK_BITS:
            states = c.decode_deck_report(c.encode_deck_report([name]))
            self.assertEqual([k for k, v in states.items() if v], [name])

    def test_paddles_at_hid_steam_offsets(self):
        report = bytearray(c.encode_deck_report([]))
        report[13] |= 0b10  # L4: byte 13 bit 1 (hid-steam.c ID_CONTROLLER_DECK_STATE, BTN_GRIPL)
        report[9] |= 0x80  # L5: byte 9 bit 7 (BTN_GRIPL2)
        states = c.decode_deck_report(bytes(report))
        self.assertTrue(states["L4"] and states["L5"])
        self.assertFalse(states["R4"] or states["R5"])

    def test_other_reports_are_ignored(self):
        self.assertIsNone(c.decode_deck_report(b"\x01\x00\x03" + bytes(61)))  # A status report.
        self.assertIsNone(c.decode_deck_report(c.encode_deck_report(["A"])[:32]))


class Chords(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(c.parse_chord("l1 + r1 + a"), ("L1", "R1", "A"))
        self.assertEqual(c.parse_chord("LB+RB"), ("L1", "R1"))
        self.assertEqual(c.parse_chord(["L4"]), ("L4",))
        for bad in ("", "L1+Q", "A+B+X+Y+L1"):
            with self.assertRaises(ValueError):
                c.parse_chord(bad)

    def test_hold_to_talk_per_source(self):
        changes = []
        tracker = c.ChordTracker(("L1", "R1"), changes.append)
        tracker.update("pad", {"L1": True})
        tracker.update("hid", {"R1": True})
        self.assertEqual(changes, [], "two sources never make one chord")
        tracker.update("hid", {"L1": True, "R1": True})
        tracker.update("hid", {"L1": True, "R1": True, "A": True})
        self.assertEqual(changes, [True])
        tracker.remove("hid")
        self.assertEqual(changes, [True, False])

    def test_off_is_never_down(self):
        changes = []
        tracker = c.ChordTracker((), changes.append)
        tracker.update("hid", {"A": True})
        self.assertEqual(changes, [])


class WatcherReadsRawReports(unittest.IsolatedAsyncioTestCase):
    async def test_fifo_as_hidraw(self):
        folder = tempfile.TemporaryDirectory()
        path = os.path.join(folder.name, "hidraw9")
        os.mkfifo(path)
        changes = []
        tracker = c.ChordTracker(("L4",), changes.append)
        watcher = c.Watcher(asyncio.get_running_loop(), tracker, evdev_glob=os.path.join(folder.name, "none*"),
                            hidraw_finder=lambda: [path], steam_running=lambda: True)
        watcher.start()
        try:
            self.assertIn(path, watcher.devices)
            self.assertIn("L4", watcher.supported())
            fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, c.encode_deck_report(["L4"]))
            await support.until(lambda: changes == [True], what="the chord down")
            os.write(fd, c.encode_deck_report(["L4"]))  # An unchanged report changes nothing.
            os.write(fd, c.encode_deck_report([]))
            await support.until(lambda: changes == [True, False], what="the chord up")
            os.close(fd)
        finally:
            watcher.close()
            folder.cleanup()

    async def test_hidraw_only_while_steam_runs(self):
        changes = []
        watcher = c.Watcher(asyncio.get_running_loop(), c.ChordTracker(("A",), changes.append),
                            evdev_glob="/nonexistent/event*", hidraw_finder=lambda: ["/nonexistent/hidraw0"],
                            steam_running=lambda: False)
        watcher.start()
        watcher.close()
        self.assertEqual(watcher.refused, set(), "the hidraw node is not even tried without Steam")


class HidrawDiscovery(unittest.TestCase):
    def test_sysfs_match(self):
        with tempfile.TemporaryDirectory() as sysfs:
            for name, hid_id, phys in (("hidraw0", "0003:000028DE:00001205", "usb-0000:04:00.4-3/input0"),
                                       ("hidraw2", "0003:000028DE:00001205", "usb-0000:04:00.4-3/input2"),
                                       ("hidraw3", "0003:0000046D:0000C52B", "usb-x/input2")):
                os.makedirs(os.path.join(sysfs, name, "device"))
                with open(os.path.join(sysfs, name, "device", "uevent"), "w") as f:
                    f.write(f"DRIVER=steam\nHID_ID={hid_id}\nHID_NAME=Valve Software Steam Deck Controller\n"
                            f"HID_PHYS={phys}\n")
            self.assertEqual(c.find_deck_hidraw(sysfs), ["/dev/hidraw2"])


if __name__ == "__main__":
    unittest.main()
