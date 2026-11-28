"""The plugin's parts, put together: the Rook client, the talk chord, the Deck agent API, the overlay feed and the
overlay process. main.py makes one App and hands Decky's callables to it.

Every part that needs the Deck itself (the controller, the microphone, the speaker, gamescope's X display and video
stream, /dev/uinput) is made here from a seam that a test or a run on a PC can replace.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path

from . import VERSION, agent, audio, capture, controller, env as envmod, notes, uinput, x11
from .client import RookClient
from .store import Store

HOTKEY_CHOICES = ["L4+R4", "L5+R5", "L4", "R4", "L5", "R5", "L1+R1+A", "off"]
OVERLAY_ANCHORS = ("top-right", "top-left", "middle-left", "middle-right", "bottom-center")
DEFAULT_ANCHOR = "middle-right"  # WoW's minimap sits top-right, and its data strip top-centre.
EDGE = 10  # The overlay keeps this far from the screen's edges (and off WoWFriend's strip in the top 10 px).


def overlay_geometry(anchor: str, width: int, height: int) -> str:
    """The overlay window for an anchor, as WxH+X+Y on a screen of width x height. The side and corner boxes are
    overlay/native.py's default size; the bottom one is wide and short, like a caption."""
    if anchor == "bottom-center":
        w, h = min(720, int(width * 0.6)), min(260, int(height * 0.33))
        x, y = (width - w) // 2, height - h - EDGE
    else:
        w, h = min(430, max(300, int(width * 0.34))), min(560, int(height * 0.7))
        x = EDGE if anchor.endswith("left") else width - w
        y = EDGE if anchor.startswith("top") else (height - h) // 2
    return f"{w}x{h}+{x}+{y}"


class App:
    def __init__(self, settings_dir: str, plugin_dir: str, *, emit, log, session: envmod.Session | None = None,
                 agent_host: str = "0.0.0.0", agent_port: int = agent.AGENT_PORT,
                 overlay_port: int = agent.OVERLAY_PORT, log_dir: str | None = None,
                 hardware: bool = True, recorder=None, player=None, grabber=None, typist=None):
        self.log = log
        self.emit_cb = emit
        self.plugin_dir = Path(plugin_dir)
        self.log_dir = log_dir
        self.hardware = hardware  # False in tests and on a PC: no controller, no overlay process.
        self.session = session or envmod.detect()
        self.store = Store(settings_dir)
        self.token = self.store.deck_token()
        self.agent_host, self.agent_port, self.overlay_port = agent_host, agent_port, overlay_port
        self.feed = agent.OverlayFeed()
        self.recorder = recorder or audio.Recorder(self.session, log, on_limit=self._recording_full)
        self.player = player or audio.Player(self.session, log)
        self.grabber = grabber or capture.Grabber(self.session, log)
        self.capture = capture.Capture(self.grabber, capture.Encoder(self.session))
        self.typist = typist or uinput.Typist()
        self.client = RookClient(self.store, self._emit, recorder=self.recorder, player=self.player, log=log,
                                 on_overlay=self.feed.set)
        self.tracker = controller.ChordTracker(self._chord(), self._chord_changed)
        self.watcher: controller.Watcher | None = None
        self.servers = []
        self.launcher = None
        self.overlay_error: str | None = None
        self._addons: Path | None = None

    # Lifecycle.
    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        overlay_server = agent.OverlayServer(self.feed, self.plugin_dir / "overlay" / "page", self.log)
        deck = agent.DeckAgent(lambda: self.token, window=self.window, capture=self.capture.region,
                               typist=self.typist, note=self.note, log=self.log)
        for name, start in (("overlay feed", lambda: agent.serve_overlay(overlay_server, port=self.overlay_port,
                                                                          log=self.log)),
                            ("Deck agent API", lambda: agent.serve_agent(deck, self.agent_host, self.agent_port,
                                                                         self.log))):
            try:
                self.servers.append(await start())
            except OSError as exc:
                self.log.error(f"the {name} did not start: {exc!r}")
        if self.hardware:
            self.watcher = controller.Watcher(loop, self.tracker, self.log, own_names=[uinput.DEVICE_NAME],
                                              steam_running=envmod.steam_running, on_devices=self.refresh_chord)
            self.watcher.start()
            await self.start_overlay()
        self.client.start()
        self.client.changed(force=True)

    async def stop(self) -> None:
        if self.watcher:
            self.watcher.close()
        await self.client.close()
        await self.grabber.stop()
        self.typist.close()
        for server in self.servers:
            await server.close()
        self.servers = []
        if self.launcher is not None:
            try:
                await asyncio.to_thread(self.launcher.stop)
            except Exception as exc:
                self.log.warning(f"overlay stop failed: {exc!r}")

    def _emit(self, event: dict):
        return self.emit_cb("rook_event", event)

    # The overlay process, through the overlay's own launcher (overlay/launcher.py).
    def _load_launcher(self):
        path = self.plugin_dir / "overlay" / "launcher.py"
        if not path.is_file():
            self.overlay_error = "overlay/launcher.py is missing"
            return None
        spec = importlib.util.spec_from_file_location("rook_overlay_launcher", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def overlay_anchor(self) -> str:
        anchor = self.store.get("overlay_position")
        return anchor if anchor in OVERLAY_ANCHORS else DEFAULT_ANCHOR

    async def screen_size(self) -> tuple[int, int]:
        """gamescope's output size: the newest frame's, else :0's root window, else the Deck's 1280x800."""
        size = self.capture.size()
        if size:
            return size
        try:
            width, height = (await asyncio.wait_for(self.read_focus(), 2)).root_size
            if width > 0 and height > 0:
                return width, height
        except Exception:
            pass
        return 1280, 800

    async def start_overlay(self) -> None:
        try:
            self.launcher = self.launcher or self._load_launcher()
            if self.launcher is None:
                return
            import inspect
            log_path = os.path.join(self.log_dir, "overlay.log") if self.log_dir else None
            options = {"url": f"http://127.0.0.1:{self.overlay_port}/overlay", "display": self.session.display,
                       "xauthority": self.session.xauthority, "user": self.session.user, "log_path": log_path}
            anchor = self.overlay_anchor()
            if "anchor" in inspect.signature(self.launcher.start).parameters:
                options["anchor"] = anchor  # The overlay places itself, when its launcher knows anchors.
            else:
                options["geometry"] = overlay_geometry(anchor, *await self.screen_size())
            found = await asyncio.to_thread(self.launcher.start, **options)
            self.overlay_error = (found or {}).get("error")
        except Exception as exc:
            self.overlay_error = f"the overlay did not start: {exc!r}"
            self.log.warning(self.overlay_error)

    def overlay_status(self) -> dict:
        if self.launcher is None:
            return {"running": False, "mode": None, "error": self.overlay_error}
        try:
            found = self.launcher.status()
        except Exception as exc:
            return {"running": False, "mode": None, "error": repr(exc)}
        return {"running": bool(found.get("running")), "mode": found.get("mode"),
                "error": found.get("error") or self.overlay_error, "others": found.get("others") or [],
                "anchor": found.get("anchor")}

    # The talk chord.
    def _chord(self) -> tuple[str, ...]:
        hotkey = self.store.get("hotkey") or "off"
        if hotkey == "off":
            return ()
        try:
            return controller.parse_chord(hotkey)
        except ValueError:
            return controller.FALLBACK_CHORD

    def active_chord(self) -> tuple[str, ...]:
        """The chord in use: the chosen one, or L1+R1+A when no source carries one of its buttons (the back
        paddles come only from the raw HID report; see controller.py)."""
        chord = self._chord()
        if not chord or self.watcher is None or not self.watcher.devices:
            return chord
        supported = self.watcher.supported()
        return chord if set(chord) <= supported else controller.FALLBACK_CHORD

    def _chord_changed(self, down: bool) -> None:
        asyncio.get_running_loop().create_task(self.client.talk_start() if down else self.client.talk_stop())

    def _recording_full(self) -> None:
        asyncio.get_running_loop().create_task(self.client.talk_stop())

    def refresh_chord(self) -> None:
        chord = self.active_chord()
        self.tracker.set_chord(chord)

    # The Deck agent API's two Deck-side reads.
    async def read_focus(self) -> x11.Focus:
        """gamescope's focus from its X display. As root, a refusal is tried once more from a child that runs as
        the Deck user with the system python3, since gamescope's Xwayland may admit only that user."""
        try:
            return await asyncio.to_thread(x11.read_focus, self.session.display, self.session.xauthority)
        except x11.X11Error:
            kwargs = self.session.child_kwargs()
            python = envmod.which("python3", {"PATH": "/usr/bin:/bin"})
            if not kwargs or not python:
                raise
        env = self.session.child_env({"PYTHONPATH": str(Path(__file__).resolve().parent.parent)})
        proc = await asyncio.create_subprocess_exec(python, "-m", "rook_deck.x11", self.session.display,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                                                    env=env, **kwargs)
        out, _ = await asyncio.wait_for(proc.communicate(), 2)
        if proc.returncode != 0:
            raise x11.X11Error("the X display refused the Deck user too")
        return x11.focus_from_json(out.decode())

    async def window(self) -> dict:
        focus = await self.read_focus()
        size = self.capture.size() or focus.root_size
        if focus.title and focus.title.startswith(agent.WOW_TITLE):
            # Rook polls the strip next: warm the pipeline now, so the first capture answers inside its second.
            self.grabber.touch()
            if not self.grabber.running:
                asyncio.get_running_loop().create_task(self._warm())
        return {"app": focus.title, "width": size[0], "height": size[1], "app_id": focus.app_id}

    async def _warm(self) -> None:
        try:
            await self.grabber.start()
        except Exception as exc:
            self.log.warning(f"capture did not start: {exc!r}")

    def addons_dir(self, detect: bool = True) -> Path | None:
        configured = self.store.get("addons_dir")
        if configured:
            return Path(configured)
        if self._addons is None and detect:
            self._addons = notes.detect(self.session.home)
            if self._addons is not None:
                self.store.set(addons_dir=str(self._addons))
        return self._addons

    async def note(self, text: str) -> int:
        addons = await asyncio.to_thread(self.addons_dir)
        return await asyncio.to_thread(notes.send, text, addons)

    # Callables.
    async def get_status(self) -> dict:
        client = self.client
        addons = await asyncio.to_thread(notes.describe, self.addons_dir(detect=False))
        return {
            "paired": client.paired, "connected": client.connected,
            "server_url": client.base.url if client.base else self.store.get("server_url"),
            "device": (client.device or {}).get("name"), "state": client.mood(),
            "talking": client.voice.phase == "recording", "hotkey": self.store.get("hotkey"),
            "hotkey_active": controller.chord_text(self.active_chord()) or "off", "hotkeys": HOTKEY_CHOICES,
            "controllers": self.watcher.describe() if self.watcher else [],
            "card": client.card, "draft": client.current_draft(), "error": client.error,
            "overlay": self.overlay_status(), "overlay_position": self.overlay_anchor(), "version": VERSION,
            "deck_agent": {"port": self.agent_port, "running": any(s.port == self.agent_port for s in self.servers)},
            "wow": addons, "capture": {"running": self.grabber.running, "error": self.grabber.error},
        }

    async def set_hotkey(self, chord: str) -> dict:
        text = str(chord or "").strip()
        if text.lower() != "off":
            try:
                text = controller.chord_text(controller.parse_chord(text))
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
        else:
            text = "off"
        self.store.set(hotkey=text)
        self.refresh_chord()
        active = controller.chord_text(self.active_chord()) or "off"
        result = {"ok": True, "hotkey": text, "hotkey_active": active}
        if active != text:
            result["note"] = (f"No controller source on this Deck reports {text}, so the talk chord is {active} "
                              "until one does.")
        return result

    async def set_overlay_position(self, anchor: str) -> dict:
        """Where the overlay sits. The launcher restarts the overlay when its geometry changes."""
        text = str(anchor or "").strip().lower()
        if text not in OVERLAY_ANCHORS:
            return {"ok": False, "error": "The overlay sits at " + ", ".join(OVERLAY_ANCHORS) + "."}
        self.store.set(overlay_position=text)
        if self.hardware:
            await self.start_overlay()
        return {"ok": True, "overlay_position": text, "overlay": self.overlay_status()}

    async def set_addons_dir(self, path: str) -> dict:
        text = str(path or "").strip()
        if not text:
            self.store.set(addons_dir=None)
            self._addons = None
            return {"ok": True, **notes.describe(await asyncio.to_thread(self.addons_dir))}
        folder = Path(os.path.expanduser(text))
        if not folder.is_dir():
            return {"ok": False, "error": f"There is no folder at {folder}."}
        self.store.set(addons_dir=str(folder))
        return {"ok": True, **notes.describe(folder)}

    def local_address(self) -> str | None:
        """The Deck's own address on the route to Rook's PC, for ROOK_DECK_URL. No packet is sent."""
        import socket
        target = self.client.base.host if self.client.base else "192.168.0.1"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect((target, 9))
                return probe.getsockname()[0]
        except OSError:
            return None

    def deck_token(self) -> dict:
        address = self.local_address() or "steamdeck.local"
        return {"token": self.token, "url": f"http://{address}:{self.agent_port}"}
