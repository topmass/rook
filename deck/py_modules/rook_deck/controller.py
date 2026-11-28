"""The talk chord on the Deck's controller: hold it to talk, release it to send, as Rook's desk key works.

Steam's frontend input APIs stop delivering buttons to plugins once a game has focus (Steamcord notes the same,
github.com/Necrosiak/Steamcord, main.py, the "Manette Valve lue en hidraw" comment), so the backend reads the
controller from the kernel itself, read-only, next to Steam. Nothing here ever grabs a device (no EVIOCGRAB) or writes
to one, so Steam and the game keep every button.

Where the Deck's buttons show up while Steam runs:

- The physical controller is HID 28de:1205, driven by hid-steam. Steam opens its hidraw node, and from then on
  hid-steam forwards every raw report to that hidraw client and stops reporting on its own evdev device ("Steam Deck"):
  in drivers/hid/hid-steam.c, steam_raw_event() hands the report to client_hdev and returns early while
  steam->client_opened is set. So the kernel's evdev device is silent in Game Mode.
- Steam's virtual gamepad (a uinput "Microsoft X-Box 360 pad", 28de:11ff) carries what the running game's Steam Input
  layout sends. It exists only while a game runs, and its buttons follow the layout: a layout that maps A to a key, or
  leaves the back paddles unbound (the default), shows nothing for them.
- The hidraw node itself: any number of readers get every report. Decktation reads the Deck this way for exactly this
  reason, "independent of the active Steam Input layout", including the rear grips L4/R4/L5/R5
  (github.com/silverfoxy/decktation, backend/src/deck_hid.py and controller_profiles.py). The byte and bit offsets
  below are theirs, which follow hid-steam.c's ID_CONTROLLER_DECK_STATE table.

So the reader takes both: the Deck's hidraw report (all buttons, paddles too) and every evdev gamepad (Steam's virtual
pad, hid-steam's own device when Steam is not running, an external pad). A chord counts when one source holds all of
its buttons. The back paddles come only from hidraw: if that node cannot be opened, a chord with L4..R5 cannot work,
and the plugin falls back to FALLBACK_CHORD. This is the main uncertainty to check on a real Deck.

Opening the Deck's hidraw node counts as a hid-steam client too. With Steam running that changes nothing (Steam is
already a client); without Steam it would turn off hid-steam's lizard mode and evdev pad, so hidraw is opened only while
a steam process runs. Decktation opens the node O_RDWR, noting that hid-steam can need write access for input
delivery; this does the same and never writes.
"""

from __future__ import annotations

import fcntl
import glob
import os
import struct
from dataclasses import dataclass, field
from typing import Callable, Iterable

# struct input_event on 64-bit Linux: struct timeval (two longs), __u16 type, __u16 code, __s32 value.
EVENT = struct.Struct("@llHHi")
EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03
SYN_REPORT, SYN_DROPPED = 0, 3

# Linux key codes for gamepad buttons (include/uapi/linux/input-event-codes.h).
EVDEV_BUTTONS = {
    0x130: "A", 0x131: "B", 0x133: "X", 0x134: "Y",  # BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST
    0x136: "L1", 0x137: "R1", 0x138: "L2", 0x139: "R2",  # BTN_TL, BTN_TR, BTN_TL2, BTN_TR2
    0x13a: "View", 0x13b: "Menu", 0x13d: "L3", 0x13e: "R3",  # BTN_SELECT, BTN_START, BTN_THUMBL, BTN_THUMBR
    0x220: "DUp", 0x221: "DDown", 0x222: "DLeft", 0x223: "DRight",
    # hid-steam's own evdev device names the Deck's grips BTN_GRIPL/R (upper, L4/R4) and BTN_GRIPL2/R2 (lower, L5/R5).
    0x224: "L4", 0x225: "R4", 0x226: "L5", 0x227: "R5",
}
# Xbox pads (and Steam's virtual Xbox 360 pad) use the historical BTN_X/BTN_Y meaning, not the positional one:
# 0x133 is X, 0x134 is Y. Decktation swaps them the same way. Keep the positional names for every other pad.
XBOX_LIKE = {(0x045E, None), (0x28DE, 0x11FF)}
TRIGGER_AXES = {0x02: "L2", 0x05: "R2", 0x0A: "L2", 0x09: "R2"}  # ABS_Z/ABS_RZ or ABS_BRAKE/ABS_GAS.
HAT_AXES = {0x10: ("DLeft", "DRight"), 0x11: ("DUp", "DDown")}

# The Deck's 64-byte raw state report: report[0] == 1, report[1] == 0, report[2] == 9. name -> (byte, bit).
DECK_REPORT_SIZE = 64
DECK_REPORT_TYPE = 9
DECK_BITS = {
    "R2": (8, 0), "L2": (8, 1), "R1": (8, 2), "L1": (8, 3),
    "Y": (8, 4), "B": (8, 5), "X": (8, 6), "A": (8, 7),
    "DUp": (9, 0), "DRight": (9, 1), "DLeft": (9, 2), "DDown": (9, 3),
    "View": (9, 4), "Menu": (9, 6), "L5": (9, 7), "R5": (10, 0),
    "L3": (10, 6), "R3": (11, 2), "L4": (13, 1), "R4": (13, 2),
}
DECK_HID_ID = (0x0003, 0x28DE, 0x1205)  # bus USB, Valve, Steam Deck controller.

BUTTONS = ("A", "B", "X", "Y", "L1", "R1", "L2", "R2", "L3", "R3", "L4", "R4", "L5", "R5",
           "View", "Menu", "DUp", "DDown", "DLeft", "DRight")
ALIASES = {"LB": "L1", "RB": "R1", "LT": "L2", "RT": "R2", "SELECT": "View", "BACK": "View", "START": "Menu",
           "UP": "DUp", "DOWN": "DDown", "LEFT": "DLeft", "RIGHT": "DRight",
           "D-PAD UP": "DUp", "D-PAD DOWN": "DDown", "D-PAD LEFT": "DLeft", "D-PAD RIGHT": "DRight"}
PADDLES = frozenset({"L4", "R4", "L5", "R5"})
FALLBACK_CHORD = ("L1", "R1", "A")  # The plan's fallback when the back paddles cannot be read.


def parse_chord(chord: str | Iterable[str]) -> tuple[str, ...]:
    """A chord such as "L4" or "L1+R1+A" as a tuple of button names. Raises ValueError for an unknown button."""
    parts = chord.replace(",", "+").split("+") if isinstance(chord, str) else list(chord)
    by_upper = {name.upper(): name for name in BUTTONS}
    names = []
    for part in parts:
        key = str(part).strip().upper()
        if not key:
            continue
        name = by_upper.get(key) or ALIASES.get(key)
        if not name:
            raise ValueError(f"{part!r} is not a controller button. Use names such as A, L1, R1, L4 or R5.")
        if name not in names:
            names.append(name)
    if not names:
        raise ValueError("A talk chord needs at least one button.")
    if len(names) > 4:
        raise ValueError("A talk chord has at most four buttons.")
    return tuple(names)


def chord_text(chord: Iterable[str]) -> str:
    return "+".join(chord)


def decode_deck_report(report: bytes) -> dict[str, bool] | None:
    """Button states from one raw Deck report, or None for any other report on the same node."""
    if len(report) != DECK_REPORT_SIZE or report[0] != 1 or report[1] != 0 or report[2] != DECK_REPORT_TYPE:
        return None
    return {name: bool(report[byte] & (1 << bit)) for name, (byte, bit) in DECK_BITS.items()}


def encode_deck_report(held: Iterable[str]) -> bytes:
    """A synthetic Deck report with these buttons held. Used by the tests, and handy for a dry run."""
    report = bytearray(DECK_REPORT_SIZE)
    report[0], report[1], report[2], report[3] = 1, 0, DECK_REPORT_TYPE, 0x40
    for name in held:
        byte, bit = DECK_BITS[name]
        report[byte] |= 1 << bit
    return bytes(report)


def pack_event(etype: int, code: int, value: int, sec: int = 0, usec: int = 0) -> bytes:
    return EVENT.pack(sec, usec, etype, code, value)


class EvdevState:
    """Button states of one evdev device, fed raw input_event records. A SYN_REPORT ends each frame; after
    SYN_DROPPED the frame is unreliable, so events are ignored until the next SYN_REPORT and the state is read anew."""

    def __init__(self, mapping: dict[int, str], axes: dict[int, tuple[int, int]] | None = None,
                 resync: Callable[[], tuple[set[int], dict[int, int]]] | None = None):
        self.mapping = mapping
        self.axes = axes or {}  # code -> (min, max) for the analog triggers and the d-pad hats.
        self.keys: set[int] = set()
        self.values: dict[int, int] = {}
        self.dropped = False
        self.resync = resync

    def states(self) -> dict[str, bool]:
        held = dict.fromkeys(self.mapping.values(), False)
        for code in self.keys:
            if code in self.mapping:
                held[self.mapping[code]] = True
        for code, (low, high) in self.axes.items():
            value = self.values.get(code, low)
            if code in TRIGGER_AXES and high > low and 2 * (value - low) >= high - low:
                held[TRIGGER_AXES[code]] = True
            if code in HAT_AXES:
                if value < 0:
                    held[HAT_AXES[code][0]] = True
                elif value > 0:
                    held[HAT_AXES[code][1]] = True
        return held

    def feed(self, etype: int, code: int, value: int) -> dict[str, bool] | None:
        """Take one event. Returns the frame's states at each SYN_REPORT, else None."""
        if etype == EV_SYN and code == SYN_DROPPED:
            self.dropped = True
        elif etype == EV_SYN and code == SYN_REPORT:
            if self.dropped:
                self.dropped = False
                if self.resync:
                    self.keys, self.values = self.resync()
            return self.states()
        elif not self.dropped:
            if etype == EV_KEY and value in (0, 1):
                (self.keys.add if value else self.keys.discard)(code)
            elif etype == EV_ABS and code in self.axes:
                self.values[code] = value
        return None

    def feed_bytes(self, data: bytes) -> list[dict[str, bool]]:
        frames = []
        usable = len(data) - len(data) % EVENT.size
        for _, _, etype, code, value in EVENT.iter_unpack(data[:usable]):
            found = self.feed(etype, code, value)
            if found is not None:
                frames.append(found)
        return frames


class ChordTracker:
    """Turns per-source button states into talk start and stop. The chord is down when one source holds all of its
    buttons, and up again as soon as none does. Each source keeps its own states, so a button held on Steam's
    virtual pad and another on the raw report never combine into a chord by accident."""

    def __init__(self, chord: tuple[str, ...], on_change: Callable[[bool], None]):
        self.chord = chord
        self.on_change = on_change
        self.sources: dict[str, dict[str, bool]] = {}
        self.down = False

    def set_chord(self, chord: tuple[str, ...]) -> None:
        self.chord = chord
        self._update()

    def update(self, source: str, states: dict[str, bool]) -> None:
        self.sources[source] = states
        self._update()

    def remove(self, source: str) -> None:
        self.sources.pop(source, None)
        self._update()

    def _update(self) -> None:
        # An empty chord (the hotkey is off) is never down.
        down = bool(self.chord) and any(all(states.get(name) for name in self.chord)
                                        for states in self.sources.values())
        if down != self.down:
            self.down = down
            self.on_change(down)


# ioctl numbers from include/uapi/linux/input.h and hidraw.h.
def _ioc(direction: int, kind: int, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (kind << 8) | number


def EVIOCGBIT(ev: int, size: int) -> int:
    return _ioc(2, ord("E"), 0x20 + ev, size)


EVIOCGID = _ioc(2, ord("E"), 0x02, 8)
EVIOCGKEY = _ioc(2, ord("E"), 0x18, 96)


def EVIOCGNAME(size: int) -> int:
    return _ioc(2, ord("E"), 0x06, size)


def EVIOCGABS(axis: int) -> int:
    return _ioc(2, ord("E"), 0x40 + axis, 24)


def _bits(data: bytes) -> set[int]:
    return {i for i in range(len(data) * 8) if data[i // 8] & (1 << (i % 8))}


def _ioctl(fd: int, request: int, size: int) -> bytes:
    buf = bytearray(size)
    fcntl.ioctl(fd, request, buf)
    return bytes(buf)


@dataclass
class Device:
    path: str
    kind: str  # "hidraw" or "evdev"
    fd: int
    name: str = ""
    state: EvdevState | None = None
    supported: set[str] = field(default_factory=set)
    last: bytes = b""  # The button bytes of the last raw report, so an unchanged report costs nothing.


def open_evdev(path: str, own_names: Iterable[str] = ()) -> Device | None:
    """Open an evdev node if it is a gamepad: gamepad buttons and two stick axes, as Linux's joystick test asks, so a
    keyboard helper that claims every key is not taken for a pad. Opened read-only and non-blocking, never grabbed."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        keys = _bits(_ioctl(fd, EVIOCGBIT(EV_KEY, 96), 96))
        axes = _bits(_ioctl(fd, EVIOCGBIT(EV_ABS, 8), 8))
        name = _ioctl(fd, EVIOCGNAME(256), 256).split(b"\0", 1)[0].decode(errors="replace")
        if name in own_names or not ({0x130, 0x131} <= keys and {0, 1} <= axes):
            os.close(fd)
            return None
        _bus, vendor, product, _version = struct.unpack("4H", _ioctl(fd, EVIOCGID, 8))
        mapping = {code: label for code, label in EVDEV_BUTTONS.items() if code in keys}
        if (vendor, product) in XBOX_LIKE or (vendor, None) in XBOX_LIKE:
            mapping = {code: {0x133: "X", 0x134: "Y"}.get(code, label) for code, label in mapping.items()}
        ranges = {}
        for code in set(TRIGGER_AXES) | set(HAT_AXES):
            if code in axes:
                _value, low, high, *_ = struct.unpack("6i", _ioctl(fd, EVIOCGABS(code), 24))
                ranges[code] = (low, high)

        def resync() -> tuple[set[int], dict[int, int]]:
            held = _bits(_ioctl(fd, EVIOCGKEY, 96))
            values = {code: struct.unpack("6i", _ioctl(fd, EVIOCGABS(code), 24))[0] for code in ranges}
            return held, values

        state = EvdevState(mapping, ranges, resync)
        state.keys, state.values = resync()
        supported = set(mapping.values()) | {TRIGGER_AXES[c] for c in ranges if c in TRIGGER_AXES}
        if any(c in HAT_AXES for c in ranges):
            supported |= {"DUp", "DDown", "DLeft", "DRight"}
        return Device(path, "evdev", fd, name, state, supported)
    except OSError:
        os.close(fd)
        return None


def find_deck_hidraw(sysfs: str = "/sys/class/hidraw") -> list[str]:
    """The Deck controller's hidraw nodes: HID_ID 0003:28DE:1205 on the interface whose HID_PHYS ends in /input2,
    the controller interface (the same match as Decktation's controller_profiles.py)."""
    found = []
    for node in sorted(glob.glob(os.path.join(sysfs, "hidraw*"))):
        try:
            with open(os.path.join(node, "device", "uevent")) as source:
                props = dict(line.rstrip("\n").split("=", 1) for line in source if "=" in line)
            bus, vendor, product = (int(part, 16) for part in props.get("HID_ID", "").split(":"))
        except (OSError, ValueError):
            continue
        if (bus, vendor, product) == DECK_HID_ID and props.get("HID_PHYS", "").endswith("/input2"):
            found.append("/dev/" + os.path.basename(node))
    return found


def open_hidraw(path: str) -> Device | None:
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return None
    return Device(path, "hidraw", fd, "Steam Deck (raw HID)", None, set(DECK_BITS))


class Watcher:
    """Reads every controller source on the asyncio loop, with add_reader, and rescans now and then: a device node can
    come back under a new number after sleep (Steamcord measured this), and Steam's virtual pad comes and goes with
    each game."""

    RESCAN_SECONDS = 10.0

    def __init__(self, loop, tracker: ChordTracker, log=None, *, own_names: Iterable[str] = (),
                 steam_running: Callable[[], bool] | None = None,
                 evdev_glob: str = "/dev/input/event*", hidraw_finder: Callable[[], list[str]] = find_deck_hidraw,
                 on_devices: Callable[[], None] | None = None):
        self.loop = loop
        self.tracker = tracker
        self.log = log
        self.own_names = set(own_names)  # Our own uinput keyboard is never a source.
        self.steam_running = steam_running or (lambda: True)
        self.evdev_glob = evdev_glob
        self.hidraw_finder = hidraw_finder
        self.devices: dict[str, Device] = {}
        self.refused: set[str] = set()
        self._timer = None
        self.closed = False
        self.on_devices = on_devices  # Told when the set of sources changes, so the chord in use can follow.

    def start(self) -> None:
        self.closed = False
        self.rescan()

    def close(self) -> None:
        self.closed = True
        if self._timer:
            self._timer.cancel()
        for path in list(self.devices):
            self._drop(path)

    def supported(self) -> set[str]:
        out: set[str] = set()
        for device in self.devices.values():
            out |= device.supported
        return out

    def describe(self) -> list[dict]:
        return [{"path": d.path, "kind": d.kind, "name": d.name} for d in self.devices.values()]

    def rescan(self) -> None:
        if self.closed:
            return
        before = set(self.devices)
        wanted: list[tuple[str, str]] = []
        if self.steam_running():
            wanted += [(path, "hidraw") for path in self.hidraw_finder()]
        wanted += [(path, "evdev") for path in sorted(glob.glob(self.evdev_glob))]
        present = {path for path, _ in wanted}
        for path in list(self.devices):
            if path not in present or (self.devices[path].kind == "hidraw" and not self.steam_running()):
                self._drop(path)
        self.refused &= present
        for path, kind in wanted:
            if path in self.devices or path in self.refused:
                continue
            device = open_hidraw(path) if kind == "hidraw" else open_evdev(path, self.own_names)
            if device is None:
                self.refused.add(path)  # Not a gamepad, or no access: tried again only once it disappears.
                continue
            self.devices[path] = device
            self.loop.add_reader(device.fd, self._readable, path)
            if self.log:
                self.log.info(f"controller source {device.name or path} ({kind}, {path})")
        if set(self.devices) != before and self.on_devices:
            self.on_devices()
        self._timer = self.loop.call_later(self.RESCAN_SECONDS, self.rescan)

    def _drop(self, path: str) -> None:
        device = self.devices.pop(path, None)
        if device is None:
            return
        try:
            self.loop.remove_reader(device.fd)
        except Exception:
            pass
        try:
            os.close(device.fd)
        except OSError:
            pass
        self.tracker.remove(path)

    def _readable(self, path: str) -> None:
        device = self.devices.get(path)
        if device is None:
            return
        try:
            if device.kind == "hidraw":
                while True:
                    report = os.read(device.fd, DECK_REPORT_SIZE)
                    if not report:
                        raise OSError("hidraw closed")
                    # The Deck sends about 250 reports a second, mostly stick and gyro motion: decode only when a
                    # button byte changed.
                    if report[8:14] == device.last:
                        continue
                    states = decode_deck_report(report)
                    if states is not None:
                        device.last = report[8:14]
                        self.tracker.update(path, states)
            else:
                data = os.read(device.fd, EVENT.size * 64)
                if not data:
                    raise OSError("evdev closed")
                for states in device.state.feed_bytes(data):
                    self.tracker.update(path, states)
        except BlockingIOError:
            return
        except OSError:
            self._drop(path)  # Unplugged, or asleep: the next rescan opens it again.
