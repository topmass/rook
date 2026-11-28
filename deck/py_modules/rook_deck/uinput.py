"""A virtual keyboard through /dev/uinput, for typing an approved chat reply into the game: Enter, text, Enter.

gamescope reads input with libinput from the kernel's devices, so a new uinput keyboard reaches the focused game the
way a USB keyboard would. Decktation types into WoW chat the same way, with a bundled ydotoold that makes a uinput
device (github.com/silverfoxy/decktation, backend/src/wow_voice_chat.py: `ydotool key 28:1 28:0` for Enter, then the
text, then Enter). This does it directly with the kernel's uinput ioctls, so nothing is bundled.

Only printable ASCII is typed, through a US layout: a game set to another keyboard layout would read other characters,
which is why non-ASCII text is refused rather than guessed. The keyboard is made once and kept, because libinput and
gamescope need a moment to notice a new device before its first key counts.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import struct
from typing import Iterable

EVENT = struct.Struct("@llHHi")  # struct input_event on 64-bit Linux.
EV_SYN, EV_KEY = 0x00, 0x01
SYN_REPORT = 0
BUS_VIRTUAL = 0x06
DEVICE_NAME = "Rook Deck keyboard"

# ioctls from include/uapi/linux/uinput.h: UINPUT_IOCTL_BASE is 'U'.
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_SET_EVBIT = 0x40045564  # _IOW('U', 100, int)
UI_SET_KEYBIT = 0x40045565  # _IOW('U', 101, int)
SETUP = struct.Struct("HHHH80sI")  # struct uinput_setup: input_id, name[UINPUT_MAX_NAME_SIZE], ff_effects_max.
UI_DEV_SETUP = (1 << 30) | (SETUP.size << 16) | (ord("U") << 8) | 3  # _IOW('U', 3, struct uinput_setup)

KEY_ENTER, KEY_LEFTSHIFT, KEY_SPACE = 28, 42, 57
MAX_TEXT = 255

# Printable ASCII on a US layout: character -> (key code, shift).
_ROWS = {
    "1234567890": (2, "!@#$%^&*()"),
    "qwertyuiop": (16, None),
    "asdfghjkl": (30, None),
    "zxcvbnm": (44, None),
}
KEYMAP: dict[str, tuple[int, bool]] = {" ": (KEY_SPACE, False)}
for _plain, (_first, _shifted) in _ROWS.items():
    for _i, _ch in enumerate(_plain):
        KEYMAP[_ch] = (_first + _i, False)
        if _shifted:
            KEYMAP[_shifted[_i]] = (_first + _i, True)
        elif _ch.isalpha():
            KEYMAP[_ch.upper()] = (_first + _i, True)
for _plain, _shifted, _code in (("-", "_", 12), ("=", "+", 13), ("[", "{", 26), ("]", "}", 27), (";", ":", 39),
                                ("'", '"', 40), ("`", "~", 41), ("\\", "|", 43), (",", "<", 51), (".", ">", 52),
                                ("/", "?", 53)):
    KEYMAP[_plain] = (_code, False)
    KEYMAP[_shifted] = (_code, True)
KEY_CODES = sorted({code for code, _ in KEYMAP.values()} | {KEY_ENTER, KEY_LEFTSHIFT})


def check_text(text: object) -> str:
    """The text to type, or ValueError with a reason: at most 255 characters, printable ASCII only."""
    if not isinstance(text, str) or not text:
        raise ValueError("Send the text to type.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"The text has {len(text)} characters. The most is {MAX_TEXT}.")
    bad = sorted({ch for ch in text if ch not in KEYMAP})
    if bad:
        raise ValueError("Only printable ASCII can be typed; this text has " + ", ".join(repr(ch) for ch in bad[:5]))
    return text


def pack(etype: int, code: int, value: int) -> bytes:
    return EVENT.pack(0, 0, etype, code, value)  # The kernel stamps the time itself.


def key_strokes(char: str) -> list[list[tuple[int, int, int]]]:
    """One character as frames of (type, code, value): each frame ends with SYN_REPORT, and frames are written with a
    short pause between them, as a person's key press and release are."""
    code, shift = KEYMAP[char]
    syn = (EV_SYN, SYN_REPORT, 0)
    frames = []
    if shift:
        frames.append([(EV_KEY, KEY_LEFTSHIFT, 1), syn])
    frames.append([(EV_KEY, code, 1), syn])
    frames.append([(EV_KEY, code, 0), syn])
    if shift:
        frames.append([(EV_KEY, KEY_LEFTSHIFT, 0), syn])
    return frames


def enter_strokes() -> list[list[tuple[int, int, int]]]:
    syn = (EV_SYN, SYN_REPORT, 0)
    return [[(EV_KEY, KEY_ENTER, 1), syn], [(EV_KEY, KEY_ENTER, 0), syn]]


def chat_plan(text: str) -> list[tuple[str, list[list[tuple[int, int, int]]]]]:
    """The whole reply as steps: ("open", Enter), ("char", ...) per character, ("send", Enter)."""
    steps = [("open", enter_strokes())]
    steps += [("char", key_strokes(ch)) for ch in check_text(text)]
    steps.append(("send", enter_strokes()))
    return steps


def encode_frames(frames: Iterable[list[tuple[int, int, int]]]) -> bytes:
    return b"".join(pack(*event) for frame in frames for event in frame)


class Keyboard:
    """The uinput device. write_frame() is the only seam the typing loop needs, so a test can stand in for it."""

    def __init__(self, path: str = "/dev/uinput"):
        self.path = path
        self.fd: int | None = None

    def open(self) -> None:
        if self.fd is not None:
            return
        fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
            for code in KEY_CODES:
                fcntl.ioctl(fd, UI_SET_KEYBIT, code)
            setup = SETUP.pack(BUS_VIRTUAL, 0x1209, 0x5250, 1, DEVICE_NAME.encode(), 0)
            fcntl.ioctl(fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            raise
        self.fd = fd

    def write_frame(self, frame: list[tuple[int, int, int]]) -> None:
        os.write(self.fd, encode_frames([frame]))

    def close(self) -> None:
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = None


class Typist:
    """Types one reply at a time. busy is true while a reply is being typed, so /type answers 409."""

    SETTLE_SECONDS = 1.0  # After the keyboard is made, before its first key: libinput and gamescope must see it.
    KEY_SECONDS = 0.012  # Between frames of one key.
    CHAR_SECONDS = 0.018  # Between characters. A game reads keys per frame, so keys must not arrive all at once.
    CHAT_OPEN_SECONDS = 0.25  # After the first Enter, while the game opens its chat box.
    CHAT_SEND_SECONDS = 0.15  # Before the last Enter.

    def __init__(self, keyboard: Keyboard | None = None, sleep=asyncio.sleep):
        self.keyboard = keyboard or Keyboard()
        self.sleep = sleep
        self.lock = asyncio.Lock()
        self.fresh = True

    @property
    def busy(self) -> bool:
        return self.lock.locked()

    async def type_chat(self, text: str) -> None:
        plan = chat_plan(text)  # Checked before anything is typed.
        async with self.lock:
            if self.keyboard.fd is None:
                self.keyboard.open()
                self.fresh = True
            if self.fresh:
                await self.sleep(self.SETTLE_SECONDS)
                self.fresh = False
            for kind, frames in plan:
                if kind == "send":
                    await self.sleep(self.CHAT_SEND_SECONDS)
                for frame in frames:
                    self.keyboard.write_frame(frame)
                    await self.sleep(self.KEY_SECONDS)
                await self.sleep(self.CHAT_OPEN_SECONDS if kind == "open" else self.CHAR_SECONDS)

    def close(self) -> None:
        self.keyboard.close()
