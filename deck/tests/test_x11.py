"""The gamescope focus reader against a fake X server on a Unix socket: the connection setup with an Xauthority
cookie, InternAtom, GetProperty on the root window (gamescope's atoms) and on the game's window (its title)."""

import os
import socket
import socketserver
import struct
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402,F401

from rook_deck import x11  # noqa: E402

ROOT = 0x1E6
GAME = 0x400003
COOKIE = bytes(range(16))


def pad(data):
    return data + b"\0" * ((4 - len(data) % 4) % 4)


class FakeX(socketserver.BaseRequestHandler):
    """Enough of the X11 protocol for x11.py: one screen, and properties from a table."""

    atoms = {}
    properties = {}  # (window, atom name) -> (type atom, format, bytes)
    require_cookie = True
    screen = (1280, 800)

    def recv(self, n):
        out = b""
        while len(out) < n:
            chunk = self.request.recv(n - len(out))
            if not chunk:
                raise ConnectionError
            out += chunk
        return out

    def handle(self):
        order, major, minor, name_len, data_len = struct.unpack("<BxHHHHxx", self.recv(12))
        name = self.recv(len(pad(b"x" * name_len)))[:name_len]
        data = self.recv(len(pad(b"x" * data_len)))[:data_len]
        if self.require_cookie and (name != x11.COOKIE_NAME or data != COOKIE):
            reason = b"No protocol specified"
            body = pad(reason)
            self.request.sendall(struct.pack("<BBHHH", 0, len(reason), 11, 0, len(body) // 4) + body)
            return
        vendor = b"fake"
        width, height = self.screen
        screen = struct.pack("<IIIIIHHHHHHIBBBB", ROOT, 0x20, 0xFFFFFF, 0, 0, width, height, 300, 200, 1, 1, 0x21,
                             0, 0, 24, 0)
        body = struct.pack("<IIIIHHBBBBBBBBxxxx", 0, 0x200000, 0x1FFFFF, 0, len(vendor), 65535, 1, 0, 0, 0, 32, 32,
                           8, 255) + pad(vendor) + screen
        self.request.sendall(struct.pack("<BxHHH", 1, 11, 0, len(body) // 4) + body)
        seq = 0
        while True:
            try:
                head = self.recv(4)
            except ConnectionError:
                return
            opcode, detail, length = struct.unpack("<BBH", head)
            rest = self.recv(length * 4 - 4)
            seq += 1
            if opcode == 16:  # InternAtom
                (n,) = struct.unpack_from("<H", rest, 0)
                atom_name = rest[4:4 + n].decode()
                atom = self.atoms.get(atom_name, 0)
                self.request.sendall(struct.pack("<BxHII20x", 1, seq, 0, atom))
            elif opcode == 20:  # GetProperty
                window, prop, _type, _offset, _length = struct.unpack("<IIIII", rest)
                name = next((k for k, v in self.atoms.items() if v == prop), None)
                if name is None and prop == x11.XA_WM_NAME:
                    name = "WM_NAME"
                found = self.properties.get((window, name))
                if found is None:
                    self.request.sendall(struct.pack("<BBHIIII12x", 1, 0, seq, 0, 0, 0, 0))
                    continue
                kind, fmt, value = found
                count = len(value) // (fmt // 8)
                body = pad(value)
                self.request.sendall(struct.pack("<BBHIIII12x", 1, fmt, seq, len(body) // 4, kind, 0, count) + body)
            else:
                self.request.sendall(struct.pack("<BBH28x", 0, 1, seq))  # BadRequest


def cardinals(*values):
    return (x11.XA_CARDINAL, 32, struct.pack(f"<{len(values)}I", *values))


def display_name_items(name):
    """GAMESCOPE_FOCUS_DISPLAY as gamescope writes it on a 64-bit build: strlen+1 format-32 items, each the low 32
    bits of one 8-byte step through the C string (the first item is the string's first four bytes)."""
    raw = name.encode() + b"\0" * 8
    return (x11.XA_CARDINAL, 32, b"".join(raw[i * 8:i * 8 + 4] for i in range(len(name) + 1)))


class FocusReader(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.socket_dir = os.path.join(self.folder.name, ".X11-unix")
        os.mkdir(self.socket_dir)
        self.servers = []
        FakeX.atoms = {name: 100 + i for i, name in enumerate(
            ("GAMESCOPE_FOCUSED_APP", "GAMESCOPE_FOCUSED_WINDOW", "GAMESCOPE_FOCUS_DISPLAY",
             "GAMESCOPE_FOCUSABLE_WINDOWS", "_NET_WM_NAME", "UTF8_STRING"))}
        self.xauth = os.path.join(self.folder.name, "Xauthority")
        host = socket.gethostname().encode()
        with open(self.xauth, "wb") as f:
            for number in (b"0", b"1"):
                f.write(struct.pack(">H", 256) + struct.pack(">H", len(host)) + host + struct.pack(">H", 1) + number
                        + struct.pack(">H", len(x11.COOKIE_NAME)) + x11.COOKIE_NAME + struct.pack(">H", 16) + COOKIE)

    def serve(self, number, properties):
        handler = type(f"FakeX{number}", (FakeX,), {"properties": properties})
        server = socketserver.ThreadingUnixStreamServer(os.path.join(self.socket_dir, f"X{number}"), handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        self.folder.cleanup()

    def test_game_on_a_nested_display(self):
        self.serve(0, {(ROOT, "GAMESCOPE_FOCUSED_APP"): cardinals(769),
                       (ROOT, "GAMESCOPE_FOCUSED_WINDOW"): cardinals(GAME),
                       (ROOT, "GAMESCOPE_FOCUS_DISPLAY"): display_name_items(":1"),
                       (ROOT, "GAMESCOPE_FOCUSABLE_WINDOWS"): cardinals(0x200001, 769, 10, GAME, 769, 4242)})
        self.serve(1, {(GAME, "_NET_WM_NAME"): (FakeX.atoms["UTF8_STRING"], 8, "World of Warcraft".encode())})
        focus = x11.read_focus(":0", self.xauth, socket_dir=self.socket_dir)
        self.assertEqual((focus.app_id, focus.window, focus.display, focus.pid), (769, GAME, ":1", 4242))
        self.assertEqual(focus.title, "World of Warcraft")
        self.assertEqual(focus.root_size, (1280, 800))

    def test_title_from_wm_name_on_the_same_display(self):
        self.serve(0, {(ROOT, "GAMESCOPE_FOCUSED_WINDOW"): cardinals(GAME),
                       (GAME, "WM_NAME"): (x11.XA_STRING, 8, b"Celeste\0")})
        focus = x11.read_focus(":0", self.xauth, socket_dir=self.socket_dir)
        self.assertEqual((focus.app_id, focus.title, focus.display), (None, "Celeste", ":0"))

    def test_nothing_focused(self):
        self.serve(0, {})
        focus = x11.read_focus(":0", self.xauth, socket_dir=self.socket_dir)
        self.assertEqual((focus.window, focus.title), (None, None))

    def test_refused_without_the_cookie(self):
        self.serve(0, {})
        with self.assertRaises(x11.X11Error):
            x11.read_focus(":0", None, socket_dir=self.socket_dir)

    def test_display_name_decoding(self):
        self.assertEqual(x11.focus_display_name(display_name_items(":1")[2]), ":1")
        self.assertEqual(x11.focus_display_name(b":12\0"), ":12")
        self.assertIsNone(x11.focus_display_name(b"gamescope-0"[:4]))
        self.assertEqual(x11.display_number(":1.0"), 1)


if __name__ == "__main__":
    unittest.main()
