"""Which game has focus under gamescope, read from gamescope's X root properties, in pure Python.

gamescope publishes its focus on the root window of its first Xwayland server, DISPLAY=:0 (steamcompmgr.cpp,
determine_and_apply_focus: XChangeProperty on root_ctx, which is wlserver_get_xwayland_server(0)):

- GAMESCOPE_FOCUSED_APP (CARDINAL): the focused app's Steam app id. Written only in Steam mode.
- GAMESCOPE_FOCUSED_WINDOW (CARDINAL): the focused window's XID, on the display named by GAMESCOPE_FOCUS_DISPLAY.
- GAMESCOPE_FOCUS_DISPLAY: that display's name, such as ":1". gamescope writes the C string as format-32 data with
  strlen+1 items, so on a 64-bit build each 32-bit item is the low half of one 8-byte step through the string: only
  the first item is the string's first four bytes. A display name like ":0" or ":1" fits in them; anything longer
  (the Wayland socket name of a native Wayland app) is not an X display and has no X title.
- GAMESCOPE_FOCUSABLE_WINDOWS (CARDINAL): triples of window, app id, pid, which give the focused window's process.

The title is the window's own _NET_WM_NAME (UTF-8), else WM_NAME, read on its display; Wine sets both to the game
window's caption, "World of Warcraft".

This speaks the X11 wire protocol on the display's Unix socket instead of loading libX11 with ctypes: libX11 calls
exit() from its default I/O error handler when a connection breaks, which here would end Decky's whole plugin process
whenever gamescope restarts mid-read. Four requests are all it needs: the connection setup, InternAtom, GetProperty,
and nothing else. xprop and xdotool are not on a stock SteamOS, so they are not relied on.
"""

from __future__ import annotations

import os
import socket
import struct
from dataclasses import dataclass

XA_STRING, XA_WM_NAME, XA_CARDINAL = 31, 39, 6
FAMILY_LOCAL, FAMILY_WILD = 256, 65535
COOKIE_NAME = b"MIT-MAGIC-COOKIE-1"


class X11Error(OSError):
    pass


def _pad(n: int) -> int:
    return (4 - n % 4) % 4


def display_number(display: str) -> int:
    """":1" or ":1.0" -> 1. Only local displays are spoken to."""
    text = display.strip()
    if not text.startswith(":"):
        raise X11Error(f"only local displays are read, not {display!r}")
    return int(text[1:].split(".", 1)[0])


def read_xauthority(path: str | None, number: int, hostname: str | None = None) -> tuple[bytes, bytes]:
    """(auth name, auth data) for this display from an Xauthority file, or empty for none."""
    if not path:
        return b"", b""
    try:
        with open(path, "rb") as source:
            raw = source.read()
    except OSError:
        return b"", b""
    host = (hostname or socket.gethostname()).encode()
    offset, best = 0, (b"", b"")

    def field_at(pos: int) -> tuple[bytes, int]:
        (size,) = struct.unpack_from(">H", raw, pos)
        return raw[pos + 2:pos + 2 + size], pos + 2 + size

    try:
        while offset + 2 <= len(raw):
            (family,) = struct.unpack_from(">H", raw, offset)
            address, offset = field_at(offset + 2)
            num, offset = field_at(offset)
            name, offset = field_at(offset)
            data, offset = field_at(offset)
            if name != COOKIE_NAME or (num and num != str(number).encode()):
                continue
            if family == FAMILY_WILD or (family == FAMILY_LOCAL and address == host):
                return name, data
            if family == FAMILY_LOCAL and not best[0]:
                best = (name, data)
    except struct.error:
        pass
    return best


@dataclass
class Screen:
    root: int
    width: int
    height: int


class Connection:
    """One short-lived X connection. Requests are answered in order, so each read takes its own reply."""

    def __init__(self, display: str = ":0", xauthority: str | None = None, timeout: float = 1.0,
                 socket_dir: str = "/tmp/.X11-unix"):
        number = display_number(display)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        path = os.path.join(socket_dir, f"X{number}")
        try:
            try:
                self.sock.connect(path)
            except OSError:
                self.sock.connect("\0" + path)  # The abstract socket Xwayland also listens on.
            self._setup(*read_xauthority(xauthority, number))
        except BaseException:
            self.sock.close()
            raise
        self.atoms: dict[str, int] = {}

    def close(self) -> None:
        self.sock.close()

    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _recv(self, size: int) -> bytes:
        out = bytearray()
        while len(out) < size:
            chunk = self.sock.recv(size - len(out))
            if not chunk:
                raise X11Error("the X server closed the connection")
            out += chunk
        return bytes(out)

    def _setup(self, auth_name: bytes, auth_data: bytes) -> None:
        head = struct.pack("<BxHHHHxx", 0x6C, 11, 0, len(auth_name), len(auth_data))
        self.sock.sendall(head + auth_name + b"\0" * _pad(len(auth_name)) + auth_data + b"\0" * _pad(len(auth_data)))
        status, reason_len, _major, _minor, length = struct.unpack("<BBHHH", self._recv(8))
        body = self._recv(length * 4)
        if status != 1:
            reason = body[:reason_len] if status == 0 else body
            raise X11Error(f"the X server refused the connection: {reason.decode(errors='replace').strip()}")
        vendor_len, = struct.unpack_from("<H", body, 16)
        formats = body[21]
        offset = 32 + vendor_len + _pad(vendor_len) + 8 * formats
        root, = struct.unpack_from("<I", body, offset)
        width, height = struct.unpack_from("<HH", body, offset + 20)
        self.screen = Screen(root, width, height)

    def _reply(self) -> bytes:
        while True:
            head = self._recv(32)
            kind = head[0]
            if kind == 0:
                raise X11Error(f"X error {head[1]}")
            if kind == 1:
                (extra,) = struct.unpack_from("<I", head, 4)
                return head + self._recv(extra * 4)
            # Anything else is an event; none are selected, but skip any that arrive.

    def atom(self, name: str, only_if_exists: bool = True) -> int:
        """The atom for a name, or 0 when it does not exist (nothing ever set it)."""
        if name in self.atoms:
            return self.atoms[name]
        raw = name.encode()
        request = struct.pack("<BBHHxx", 16, 1 if only_if_exists else 0, 2 + (len(raw) + _pad(len(raw))) // 4,
                              len(raw)) + raw + b"\0" * _pad(len(raw))
        self.sock.sendall(request)
        (value,) = struct.unpack_from("<I", self._reply(), 8)
        self.atoms[name] = value
        return value

    def get_property(self, window: int, prop: int, prop_type: int = 0, max_bytes: int = 4096) -> tuple[int, int, bytes]:
        """(type, format, value bytes) of a window property; type 0 means it is not set."""
        if not prop:
            return 0, 0, b""
        request = struct.pack("<BBHIIIII", 20, 0, 6, window, prop, prop_type, 0, max_bytes // 4)
        self.sock.sendall(request)
        reply = self._reply()
        fmt = reply[1]
        got_type, _after, count = struct.unpack_from("<III", reply, 8)
        size = count * (fmt // 8) if fmt else 0
        return got_type, fmt, reply[32:32 + size]

    def cardinals(self, window: int, name: str) -> list[int]:
        got_type, fmt, value = self.get_property(window, self.atom(name))
        if not got_type or fmt != 32:
            return []
        return list(struct.unpack(f"<{len(value) // 4}I", value))

    def title(self, window: int) -> str | None:
        """A window's title: _NET_WM_NAME as UTF-8, else WM_NAME as Latin-1."""
        for prop, decode in ((self.atom("_NET_WM_NAME"), "utf-8"), (XA_WM_NAME, "latin-1")):
            got_type, fmt, value = self.get_property(window, prop)
            if got_type and fmt == 8 and value:
                return value.split(b"\0", 1)[0].decode(decode, errors="replace").strip() or None
        return None


@dataclass
class Focus:
    app_id: int | None
    window: int | None
    display: str | None
    title: str | None
    pid: int | None
    root_size: tuple[int, int]


def focus_display_name(value: bytes) -> str | None:
    """The display name in GAMESCOPE_FOCUS_DISPLAY: the first 32-bit item, up to its NUL (see the module notes)."""
    name = value[:4].split(b"\0", 1)[0].decode("ascii", errors="replace")
    return name if name.startswith(":") and name[1:].split(".")[0].isdigit() else None


def read_focus(display: str = ":0", xauthority: str | None = None, socket_dir: str = "/tmp/.X11-unix") -> Focus:
    """What gamescope says has focus. Raises X11Error or OSError when the display cannot be read."""
    with Connection(display, xauthority, socket_dir=socket_dir) as root_x:
        root = root_x.screen.root
        apps = root_x.cardinals(root, "GAMESCOPE_FOCUSED_APP")
        windows = root_x.cardinals(root, "GAMESCOPE_FOCUSED_WINDOW")
        _type, _fmt, raw_display = root_x.get_property(root, root_x.atom("GAMESCOPE_FOCUS_DISPLAY"))
        focusable = root_x.cardinals(root, "GAMESCOPE_FOCUSABLE_WINDOWS")
        window = windows[0] if windows else None
        on = focus_display_name(raw_display) or display
        pid = None
        for i in range(0, len(focusable) - 2, 3):
            if window and focusable[i] == window:
                pid = focusable[i + 2] or None
        title = None
        if window:
            try:
                if display_number(on) == display_number(display):
                    title = root_x.title(window)
                else:
                    with Connection(on, xauthority, socket_dir=socket_dir) as game_x:
                        title = game_x.title(window)
            except (OSError, ValueError):
                title = None
        return Focus(apps[0] if apps else None, window, on, title, pid,
                     (root_x.screen.width, root_x.screen.height))


def focus_json(focus: Focus) -> str:
    import json
    return json.dumps({"app_id": focus.app_id, "window": focus.window, "display": focus.display,
                       "title": focus.title, "pid": focus.pid, "root_size": list(focus.root_size)})


def focus_from_json(text: str) -> Focus:
    import json
    data = json.loads(text)
    return Focus(data.get("app_id"), data.get("window"), data.get("display"), data.get("title"), data.get("pid"),
                 tuple(data.get("root_size") or (0, 0)))


if __name__ == "__main__":
    # python3 -m rook_deck.x11 :0 — the backend runs this as the Deck user when gamescope's Xwayland refuses root
    # (an X server can admit clients by their local user instead of a cookie), and reads the JSON it prints.
    import sys
    print(focus_json(read_focus(sys.argv[1] if len(sys.argv) > 1 else ":0", os.environ.get("XAUTHORITY"))))
