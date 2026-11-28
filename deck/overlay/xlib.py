"""The few Xlib calls Rook's overlay needs, through ctypes (libX11 and libXext ship with SteamOS; nothing to build).

gamescope composites a window on top of the game when the window carries the X property GAMESCOPE_EXTERNAL_OVERLAY
(CARDINAL 1), as mangoapp (Steam's performance overlay) does. An empty input shape (XShape, ShapeInput) makes it
click- and touch-through. The same calls tag a window another process made (Qt's), since X11 lets any client set
properties and shapes on any window.

Written after decky-overlay's renderer (github.com/powange/decky-overlay, renderer/renderer.py, BSD-3-Clause),
which proved the approach on stock SteamOS; no code copied.
"""

import ctypes
import ctypes.util
import os
from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_long, c_uint, c_ulong, c_void_p


def _load(*names):
    for name in names:
        if not name:
            continue
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    return None


x11 = _load("libX11.so.6", ctypes.util.find_library("X11"))
xext = _load("libXext.so.6", ctypes.util.find_library("Xext"))


class XError(RuntimeError):
    pass


class XVisualInfo(Structure):
    _fields_ = [
        ("visual", c_void_p), ("visualid", c_ulong), ("screen", c_int), ("depth", c_int), ("c_class", c_int),
        ("red_mask", c_ulong), ("green_mask", c_ulong), ("blue_mask", c_ulong), ("colormap_size", c_int),
        ("bits_per_rgb", c_int),
    ]


class XSetWindowAttributes(Structure):
    _fields_ = [
        ("background_pixmap", c_ulong), ("background_pixel", c_ulong), ("border_pixmap", c_ulong),
        ("border_pixel", c_ulong), ("bit_gravity", c_int), ("win_gravity", c_int), ("backing_store", c_int),
        ("backing_planes", c_ulong), ("backing_pixel", c_ulong), ("save_under", c_int), ("event_mask", c_long),
        ("do_not_propagate_mask", c_long), ("override_redirect", c_int), ("colormap", c_ulong), ("cursor", c_ulong),
    ]


class XWindowAttributes(Structure):
    _fields_ = [
        ("x", c_int), ("y", c_int), ("width", c_int), ("height", c_int), ("border_width", c_int), ("depth", c_int),
        ("visual", c_void_p), ("root", c_ulong), ("c_class", c_int), ("bit_gravity", c_int), ("win_gravity", c_int),
        ("backing_store", c_int), ("backing_planes", c_ulong), ("backing_pixel", c_ulong), ("save_under", c_int),
        ("colormap", c_ulong), ("map_installed", c_int), ("map_state", c_int), ("all_event_masks", c_long),
        ("your_event_mask", c_long), ("do_not_propagate_mask", c_long), ("override_redirect", c_int),
        ("screen", c_void_p),
    ]


def _sig(lib, name, restype, *argtypes):
    fn = getattr(lib, name)
    fn.restype = restype
    fn.argtypes = list(argtypes)
    return fn


TRUE_COLOR = 4
INPUT_OUTPUT = 1
CW_BACK_PIXEL = 1 << 1
CW_BORDER_PIXEL = 1 << 3
CW_OVERRIDE_REDIRECT = 1 << 9
CW_EVENT_MASK = 1 << 11
CW_COLORMAP = 1 << 13
XA_CARDINAL = 6
XA_STRING = 31
XA_WINDOW = 33
PROP_MODE_REPLACE = 0
SHAPE_INPUT = 2
SHAPE_SET = 0
IS_VIEWABLE = 2
EXPOSURE_MASK = 1 << 15
STRUCTURE_NOTIFY_MASK = 1 << 17

if x11 is not None:
    XOpenDisplay = _sig(x11, "XOpenDisplay", c_void_p, c_char_p)
    XCloseDisplay = _sig(x11, "XCloseDisplay", c_int, c_void_p)
    XDefaultScreen = _sig(x11, "XDefaultScreen", c_int, c_void_p)
    XRootWindow = _sig(x11, "XRootWindow", c_ulong, c_void_p, c_int)
    XDisplayWidth = _sig(x11, "XDisplayWidth", c_int, c_void_p, c_int)
    XDisplayHeight = _sig(x11, "XDisplayHeight", c_int, c_void_p, c_int)
    XMatchVisualInfo = _sig(x11, "XMatchVisualInfo", c_int, c_void_p, c_int, c_int, c_int, POINTER(XVisualInfo))
    XCreateColormap = _sig(x11, "XCreateColormap", c_ulong, c_void_p, c_ulong, c_void_p, c_int)
    XCreateWindow = _sig(x11, "XCreateWindow", c_ulong, c_void_p, c_ulong, c_int, c_int, c_uint, c_uint, c_uint,
                         c_int, c_uint, c_void_p, c_ulong, POINTER(XSetWindowAttributes))
    XDestroyWindow = _sig(x11, "XDestroyWindow", c_int, c_void_p, c_ulong)
    XInternAtom = _sig(x11, "XInternAtom", c_ulong, c_void_p, c_char_p, c_int)
    XChangeProperty = _sig(x11, "XChangeProperty", c_int, c_void_p, c_ulong, c_ulong, c_ulong, c_int, c_int,
                           c_void_p, c_int)
    XGetWindowProperty = _sig(x11, "XGetWindowProperty", c_int, c_void_p, c_ulong, c_ulong, c_long, c_long, c_int,
                              c_ulong, POINTER(c_ulong), POINTER(c_int), POINTER(c_ulong), POINTER(c_ulong),
                              POINTER(c_void_p))
    XFree = _sig(x11, "XFree", c_int, c_void_p)
    XStoreName = _sig(x11, "XStoreName", c_int, c_void_p, c_ulong, c_char_p)
    XFetchName = _sig(x11, "XFetchName", c_int, c_void_p, c_ulong, POINTER(c_char_p))
    XMapWindow = _sig(x11, "XMapWindow", c_int, c_void_p, c_ulong)
    XMapRaised = _sig(x11, "XMapRaised", c_int, c_void_p, c_ulong)
    XUnmapWindow = _sig(x11, "XUnmapWindow", c_int, c_void_p, c_ulong)
    XMoveResizeWindow = _sig(x11, "XMoveResizeWindow", c_int, c_void_p, c_ulong, c_int, c_int, c_uint, c_uint)
    XFlush = _sig(x11, "XFlush", c_int, c_void_p)
    XSync = _sig(x11, "XSync", c_int, c_void_p, c_int)
    XPending = _sig(x11, "XPending", c_int, c_void_p)
    XNextEvent = _sig(x11, "XNextEvent", c_int, c_void_p, c_void_p)
    XConnectionNumber = _sig(x11, "XConnectionNumber", c_int, c_void_p)
    XQueryTree = _sig(x11, "XQueryTree", c_int, c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                      POINTER(POINTER(c_ulong)), POINTER(c_uint))
    XGetWindowAttributes = _sig(x11, "XGetWindowAttributes", c_int, c_void_p, c_ulong, POINTER(XWindowAttributes))
    _ERROR_HANDLER = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p)
    XSetErrorHandler = _sig(x11, "XSetErrorHandler", c_void_p, _ERROR_HANDLER)

    # A window can vanish between listing and asking (Qt makes and drops helper windows): an X error must not kill us.
    @_ERROR_HANDLER
    def _ignore_errors(_dpy, _event):
        return 0

    XSetErrorHandler(_ignore_errors)

if xext is not None:
    try:
        XShapeCombineRectangles = _sig(xext, "XShapeCombineRectangles", None, c_void_p, c_ulong, c_int, c_int, c_int,
                                       c_void_p, c_int, c_int, c_int)
    except AttributeError:
        XShapeCombineRectangles = None
else:
    XShapeCombineRectangles = None


class Display:
    """An X connection, by default to $DISPLAY (gamescope's Xwayland is :0 on SteamOS's Game Mode)."""

    def __init__(self, name=None):
        if x11 is None:
            raise XError("libX11 not found")
        name = name or os.environ.get("DISPLAY") or ":0"
        self.name = name
        self.dpy = XOpenDisplay(name.encode())
        if not self.dpy:
            raise XError(f"cannot open display {name}")
        self.screen = XDefaultScreen(self.dpy)
        self.root = XRootWindow(self.dpy, self.screen)
        self.width = XDisplayWidth(self.dpy, self.screen)
        self.height = XDisplayHeight(self.dpy, self.screen)
        self._atoms = {}

    def close(self):
        if self.dpy:
            XCloseDisplay(self.dpy)
            self.dpy = None

    def atom(self, name):
        if name not in self._atoms:
            self._atoms[name] = XInternAtom(self.dpy, name.encode(), 0)
        return self._atoms[name]

    def flush(self):
        XFlush(self.dpy)

    def sync(self):
        XSync(self.dpy, 0)

    # -- properties

    def set_cardinal(self, win, name, value):
        v = c_long(value)
        XChangeProperty(self.dpy, win, self.atom(name), XA_CARDINAL, 32, PROP_MODE_REPLACE, byref(v), 1)

    def get_cardinal(self, win, name):
        actual_type, fmt, n, after, data = c_ulong(), c_int(), c_ulong(), c_ulong(), c_void_p()
        ok = XGetWindowProperty(self.dpy, win, self.atom(name), 0, 1, 0, 0, byref(actual_type), byref(fmt), byref(n),
                                byref(after), byref(data))
        try:
            if ok != 0 or not data.value or n.value < 1 or fmt.value != 32:
                return None
            return ctypes.cast(data, POINTER(c_long))[0] & 0xFFFFFFFF
        finally:
            if data.value:
                XFree(data)

    def name_of(self, win):
        out = c_char_p()
        if XFetchName(self.dpy, win, byref(out)) and out.value is not None:
            name = out.value.decode(errors="replace")
            XFree(out)
            return name
        return None

    def attributes(self, win):
        a = XWindowAttributes()
        if not XGetWindowAttributes(self.dpy, win, byref(a)):
            return None
        return a

    def children(self, win=None):
        root, parent, kids, n = c_ulong(), c_ulong(), POINTER(c_ulong)(), c_uint()
        if not XQueryTree(self.dpy, win or self.root, byref(root), byref(parent), byref(kids), byref(n)):
            return []
        try:
            return [kids[i] for i in range(n.value)]
        finally:
            if kids:
                XFree(kids)

    def walk(self, win=None, depth=3):
        """Every window under win (the root), down to depth levels."""
        out = []
        for w in self.children(win):
            out.append(w)
            if depth > 1:
                out.extend(self.walk(w, depth - 1))
        return out

    # -- the overlay tag

    def make_overlay(self, win):
        """Tags win as gamescope's external overlay and makes it take no input."""
        self.set_cardinal(win, "GAMESCOPE_EXTERNAL_OVERLAY", 1)
        self.input_passthrough(win)
        self.flush()

    def input_passthrough(self, win):
        if XShapeCombineRectangles is None:
            return False
        XShapeCombineRectangles(self.dpy, win, SHAPE_INPUT, 0, 0, None, 0, SHAPE_SET, 0)
        return True

    def create_argb_window(self, x, y, w, h, title="Rook Overlay", tag=True):
        """A 32-bit (ARGB) override-redirect window, tagged and input-transparent, not yet mapped. tag=False leaves
        out GAMESCOPE_EXTERNAL_OVERLAY (tests only: a nested gamescope screenshot then shows the window)."""
        vinfo = XVisualInfo()
        if not XMatchVisualInfo(self.dpy, self.screen, 32, TRUE_COLOR, byref(vinfo)):
            raise XError("no 32-bit ARGB visual")
        attrs = XSetWindowAttributes()
        attrs.colormap = XCreateColormap(self.dpy, self.root, vinfo.visual, 0)
        attrs.background_pixel = 0
        attrs.border_pixel = 0
        attrs.override_redirect = 1
        attrs.event_mask = EXPOSURE_MASK | STRUCTURE_NOTIFY_MASK
        mask = CW_COLORMAP | CW_BACK_PIXEL | CW_BORDER_PIXEL | CW_OVERRIDE_REDIRECT | CW_EVENT_MASK
        win = XCreateWindow(self.dpy, self.root, x, y, w, h, 0, 32, INPUT_OUTPUT, vinfo.visual, mask, byref(attrs))
        if not win:
            raise XError("XCreateWindow failed")
        XStoreName(self.dpy, win, title.encode())
        self.set_cardinal(win, "_NET_WM_PID", os.getpid())
        if tag:
            self.make_overlay(win)
        else:
            self.input_passthrough(win)
            self.flush()
        return win, vinfo.visual

    def map(self, win):
        XMapRaised(self.dpy, win)
        self.flush()

    def unmap(self, win):
        XUnmapWindow(self.dpy, win)
        self.flush()

    def destroy(self, win):
        XDestroyWindow(self.dpy, win)
        self.flush()

    def drain(self):
        ev = ctypes.create_string_buffer(256)  # sizeof(XEvent) is 192
        while XPending(self.dpy):
            XNextEvent(self.dpy, ev)

    def fileno(self):
        return XConnectionNumber(self.dpy)

    def external_overlays(self):
        """Every mapped window that carries GAMESCOPE_EXTERNAL_OVERLAY: (window, name, pid)."""
        out = []
        for w in self.walk(depth=2):
            if self.get_cardinal(w, "GAMESCOPE_EXTERNAL_OVERLAY"):
                a = self.attributes(w)
                if a is not None and a.map_state == IS_VIEWABLE:
                    out.append((w, self.name_of(w), self.get_cardinal(w, "_NET_WM_PID")))
        return out
