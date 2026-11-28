"""Platform seam for Rook's desk services: Linux (Omarchy/Hyprland/PipeWire/systemd) and macOS.

Chosen once at import. On Linux, every function matches Rook's existing behaviour. On macOS,
milestone 1 provides paths, a sleep-counting monotonic clock, audio output (afplay on a
temporary WAV file), theme reading, clipboard, Tailscale CLI lookup, and launchd control;
features not built on macOS yet (overlay, global keys, window capture, screen lock,
microphone-in-use) report cleanly as absent so Rook keeps running.
"""

import os
from pathlib import Path
import sys

IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
NOT_YET = "Not on this system yet."
LAUNCHD_LABEL = os.environ.get("ROOK_LAUNCHD_LABEL", "com.rook.companion")


def _mach_continuous_seconds():
    """Monotonic clock on macOS that counts sleep, matching Linux CLOCK_BOOTTIME."""
    import ctypes
    import time
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    libc.mach_continuous_time.restype = ctypes.c_uint64

    class Timebase(ctypes.Structure):
        _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]

    info = Timebase()
    if libc.mach_timebase_info(ctypes.byref(info)) != 0 or not info.denom:
        return time.monotonic()
    return libc.mach_continuous_time() * info.numer / info.denom / 1e9


def _unwrap_dbus(value):
    """Unwrap busctl --json=short typed values into plain Python objects."""
    if isinstance(value, dict) and set(value.keys()) == {"type", "data"}:
        kind, data = value["type"], value["data"]
        if kind == "a{sv}":
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
                return {k: _unwrap_dbus(v) for k, v in data[0].items()}
            if isinstance(data, dict):
                return {k: _unwrap_dbus(v) for k, v in data.items()}
        return _unwrap_dbus(data)
    if isinstance(value, list):
        return [_unwrap_dbus(item) for item in value]
    if isinstance(value, dict):
        return {k: _unwrap_dbus(v) for k, v in value.items()}
    return value


# Single call-classification rule for PipeWire source-outputs, shared by Rook and media.py.
#
# What counts as a call: an uncorked microphone capture stream owned by another process that is
# a known voice-chat or meeting program, a web browser capturing a microphone (not desktop/sink
# audio), or a stream carrying PipeWire media.role "communication" or "phone".
#
# What does not count as a call: corked streams, streams with no process id or no application
# name/binary (hardware remaps, loopbacks, and filter chains such as Komplete input), Rook's
# own process, speech recognisers, passive/loopback/sink-capture streams, media.role "production",
# screen/clip recorders (such as gpu-screen-recorder and OBS), DAWs, and audio meters.
#
# When unsure about an unknown program, lean "not a call". Real calls run in a browser, a known
# chat/meeting program, or declare media.role communication/phone; treating unknown Linux audio
# tools as calls silently holds timers, skips the listen window, and disables music ducking.
CALL_ROLES = frozenset({"communication", "phone"})
NON_CALL_ROLES = frozenset({"production", "music", "video", "game", "event", "notification"})
CALL_BROWSERS = frozenset({
    "chromium", "chrome", "google-chrome", "brave", "vivaldi", "edge", "microsoft-edge", "opera",
    "firefox", "zen", "librewolf", "floorp", "waterfox", "helium",
})
CALL_APPS = frozenset({
    "discord", "vesktop", "webcord", "armcord", "legcord", "dorion", "equibop",
    "zoom", "slack", "teams", "teams-for-linux",
    "telegram", "telegram-desktop", "signal", "signal-desktop",
    "element", "element-desktop", "mumble",
    "teamspeak", "ts3client_linux_amd64", "ts5client",
    "skype", "skypeforlinux", "webex", "whatsapp", "linphone",
    "jitsi", "jitsi-meet-electron", "chime", "gather", "tuple", "pop",
    "meet", "facetime", "wire", "viber", "cinny", "revolt", "guilded",
    "webrtc", "webrtc voiceengine",
})
NON_CALL_APPS = frozenset({
    # Screen, clip, and audio recorders.
    "gpu-screen-recorder", "gsr", "obs", "obs-studio", "wf-recorder", "wl-screenrec",
    "kooha", "simplescreenrecorder", "vokoscreenng", "kazam", "peek", "ffmpeg",
    "pw-record", "pw-cat", "parec", "parecord", "arecord", "sox", "rec",
    # Audio workstations and editors.
    "audacity", "tenacity", "ardour", "reaper", "bitwig", "bitwig-studio",
    "lmms", "carla", "qtractor", "zrythm",
    # Rook and speech recognisers.
    "rook", "airtype", "whisper", "vosk", "nerd-dictation", "speech-dispatcher",
    # Audio plumbing, patchbays, and level meters.
    "pavucontrol", "helvum", "qpwgraph", "coppwr", "easyeffects", "jamesdsp",
    "noisetorch", "cava", "waybar", "quickshell", "omarchy-shell", "pipewire", "wireplumber",
})
_NON_CALL_PREFIXES = ("gsr-", "gpu-screen-recorder", "pw-record", "pw-cat")
_LOOPBACK_PREFIXES = ("loopback-", "filter-chain-", "smart-")


def _stream_tokens(props):
    raw_app = str(props.get("application.name") or "").strip().lower()
    raw_bin = str(props.get("application.process.binary") or "").strip()
    bin_base = os.path.basename(raw_bin).lower() if raw_bin else ""
    tokens = set()
    for val in (raw_app, bin_base):
        if val:
            tokens.add(val)
            first = val.split()[0]
            if first:
                tokens.add(first)
    return tokens


def call_streams(streams, own_pid=None):
    """Filter raw PipeWire source-output rows to the ones that represent a live voice or video call."""
    own = str(os.getpid() if own_pid is None else own_pid)
    callers = []
    for stream in streams or ():
        if not isinstance(stream, dict) or stream.get("corked"):
            continue
        props = stream.get("properties") or {}
        owner = props.get("application.process.id")
        if owner is None or not str(owner).strip() or str(owner) == own:
            continue
        if str(props.get("node.passive") or "").lower() == "true":
            continue
        if str(props.get("stream.capture.sink") or "").lower() == "true":
            continue
        link_group = str(props.get("node.link-group") or "").strip().lower()
        if link_group.startswith(_LOOPBACK_PREFIXES):
            continue
        tokens = _stream_tokens(props)
        if not tokens:
            continue
        role = str(props.get("media.role") or "").strip().lower()
        if role in NON_CALL_ROLES:
            continue
        if (tokens & NON_CALL_APPS) or any(t.startswith(_NON_CALL_PREFIXES) for t in tokens):
            continue
        if role in CALL_ROLES or (tokens & CALL_APPS) or (tokens & CALL_BROWSERS):
            callers.append({
                "name": props.get("application.name"),
                "pid": str(owner),
                "binary": props.get("application.process.binary"),
            })
    return callers


class _Linux:
    supports_overlay = True
    supports_capture = True
    supports_hyprland = True

    def runtime_dir(self):
        return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")

    def config_dir(self):
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")

    def state_dir(self):
        return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")

    def data_dir(self):
        return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")

    def cache_dir(self):
        return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")

    def python_exe(self):
        return "/usr/bin/python" if os.path.exists("/usr/bin/python") else sys.executable

    def python3_exe(self):
        return "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable

    def false_exe(self):
        return "/bin/false"

    def ffmpeg_exe(self):
        return "/usr/bin/ffmpeg"

    def find_tool(self, name):
        import shutil
        return shutil.which(name)

    def tailscale_exe(self):
        return "tailscale"

    def uptime_seconds(self):
        import time
        return time.clock_gettime(time.CLOCK_BOOTTIME)

    def process_cwd(self, pid, fallback=None):
        if pid:
            try:
                return os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                pass
        return fallback or os.getcwd()

    def hyprland_session(self, timeout=0.2):
        """Whether a Hyprland session is reachable now on its command socket within one total deadline."""
        import socket
        import time
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "").strip()
        if not sig:
            return False
        sock_path = os.path.join(str(self.runtime_dir()), "hypr", sig, ".socket.sock")
        deadline = time.monotonic() + timeout
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                rem = deadline - time.monotonic()
                if rem <= 0:
                    return False
                sock.settimeout(rem)
                sock.connect(sock_path)
                rem = deadline - time.monotonic()
                if rem <= 0:
                    return False
                sock.settimeout(rem)
                sock.sendall(b"j/version")
                rem = deadline - time.monotonic()
                if rem <= 0:
                    return False
                sock.settimeout(rem)
                chunk = sock.recv(4096)
            return chunk[:1] in (b"{", b"[")
        except (OSError, TimeoutError):
            return False

    def wayland_globals(self, timeout=0.2):
        """Frozenset of Wayland registry interface names offered by the current display within one total deadline."""
        import socket
        import struct
        import time
        display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
        if not display or not display.strip():
            return None
        sock_path = os.path.join(str(self.runtime_dir()), display)
        deadline = time.monotonic() + timeout
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                rem = deadline - time.monotonic()
                if rem <= 0:
                    return None
                sock.settimeout(rem)
                sock.connect(sock_path)
                rem = deadline - time.monotonic()
                if rem <= 0:
                    return None
                sock.settimeout(rem)
                # wl_display.get_registry(new_id=2), then wl_display.sync(callback=3).
                sock.sendall(struct.pack("<IHHI", 1, 1, 12, 2) + struct.pack("<IHHI", 1, 0, 12, 3))
                buf = b""
                names = set()
                while True:
                    while len(buf) >= 8:
                        obj, op, size = struct.unpack_from("<IHH", buf)
                        if size < 8:
                            return None
                        if len(buf) < size:
                            break
                        body, buf = buf[8:size], buf[size:]
                        if obj == 3:
                            return frozenset(names)
                        if obj == 2 and op == 0 and len(body) >= 8:  # wl_registry.global
                            n, = struct.unpack_from("<I", body, 4)
                            if 8 + n <= len(body) and n > 0:
                                names.add(body[8:7 + n].decode(errors="replace"))
                    rem = deadline - time.monotonic()
                    if rem <= 0:
                        return None
                    sock.settimeout(rem)
                    chunk = sock.recv(65536)
                    if not chunk:
                        return None
                    buf += chunk
        except (OSError, TimeoutError, struct.error, ValueError):
            return None

    def desktop_capabilities(self, timeout=1.0):
        """Probe Hyprland, Wayland layer-shell overlay, and grim+toplevel capture within one total deadline."""
        import time
        deadline = time.monotonic() + timeout
        hypr_budget = min(timeout / 2, max(0.01, deadline - time.monotonic()))
        hypr = self.hyprland_session(timeout=hypr_budget)
        wl_budget = deadline - time.monotonic()
        wl = self.wayland_globals(timeout=wl_budget) if wl_budget > 0 else None
        grim = bool(self.find_tool("grim"))
        return {
            "hyprland": hypr,
            "overlay": bool(wl and "zwlr_layer_shell_v1" in wl),
            "capture": bool(grim and wl and "ext_foreign_toplevel_list_v1" in wl),
            "grim": grim,
        }

    def find_session(self):
        """Set HYPRLAND_INSTANCE_SIGNATURE and WAYLAND_DISPLAY when they are missing, from the live sockets in the
        runtime folder: the newest that takes a connection. A variable that is set is never changed. Return the
        names it set. For a service whose systemd manager never got the session's variables."""
        import glob
        set_now = []
        run = str(self.runtime_dir())
        for name, pattern, value in (("HYPRLAND_INSTANCE_SIGNATURE", "hypr/*/.socket.sock", lambda p: p.split("/")[-2]),
                                     ("WAYLAND_DISPLAY", "wayland-[0-9]*", os.path.basename)):
            if os.environ.get(name, "").strip():
                continue
            def mtime(path):
                try:
                    return os.stat(path).st_mtime
                except OSError:  # Gone since the listing: it sorts last, and the connect below finds it dead.
                    return 0
            for path in sorted((p for p in glob.glob(f"{run}/{pattern}") if not p.endswith(".lock")), key=mtime,
                               reverse=True):
                if self.socket_alive(path):
                    os.environ[name] = value(path)
                    set_now.append(name)
                    break
        return set_now

    def socket_alive(self, path):
        """Whether a Unix socket at path takes a connection now."""
        import socket
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                sock.connect(path)
            return True
        except OSError:
            return False

    def has_keys(self):
        return True

    def has_media(self):
        return True

    def stage_command(self):
        """The stage host's launch command (stage/host.py), or None when this system cannot show it as a layer: it
        needs WebKitGTK 4.1 and the GTK 3 layer-shell library (gtk-layer-shell), under the system Python."""
        typelibs = Path("/usr/lib/girepository-1.0")
        if not all((typelibs / name).exists() for name in ("WebKit2-4.1.typelib", "GtkLayerShell-0.1.typelib")):
            return None
        return [self.python_exe(), str(Path(__file__).resolve().parent.parent / "stage" / "host.py")]

    def _has_user_bus(self):
        if os.environ.get("ROOK_DISABLE_MEDIA") == "1":
            return False
        addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        if addr is not None:
            return bool(addr.strip())
        return (self.runtime_dir() / "bus").exists()

    def mpris_list(self, timeout=0.5):
        import json
        import subprocess
        if not self._has_user_bus():
            return []
        try:
            done = subprocess.run(
                ["busctl", "--user", "--json=short", "list"],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
            )
            if done.returncode != 0 or not done.stdout.strip():
                return []
            rows = json.loads(done.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return []
        if not isinstance(rows, list):
            return []
        players = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "")
            if not name.startswith("org.mpris.MediaPlayer2."):
                continue
            pid = row.get("pid")
            players.append({
                "bus": name,
                "pid": int(pid) if isinstance(pid, int) and not isinstance(pid, bool) else None,
                "process": str(row.get("process") or ""),
            })
        return players

    def mpris_properties(self, bus_name, interface, timeout=0.5):
        import json
        import subprocess
        if not self._has_user_bus():
            return {}
        try:
            done = subprocess.run(
                ["busctl", "--user", "--json=short", "call", bus_name, "/org/mpris/MediaPlayer2",
                 "org.freedesktop.DBus.Properties", "GetAll", "s", interface],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
            )
            if done.returncode != 0 or not done.stdout.strip():
                return {}
            parsed = _unwrap_dbus(json.loads(done.stdout))
            return parsed if isinstance(parsed, dict) else {}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {}

    def mpris_call(self, bus_name, method, timeout=1.0):
        import subprocess
        if method not in ("Pause", "Play", "PlayPause"):
            return False, f"Unsupported media method {method!r}."
        if not self._has_user_bus():
            return False, "No user D-Bus session is available."
        try:
            done = subprocess.run(
                ["busctl", "--user", "call", bus_name, "/org/mpris/MediaPlayer2",
                 "org.mpris.MediaPlayer2.Player", method],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"Could not run busctl: {error}"
        if done.returncode != 0:
            msg = (done.stderr or done.stdout or "").strip()
            return False, msg or f"busctl exited with code {done.returncode}."
        return True, None

    def hyprland_json(self, command, timeout=0.5):
        import json
        import socket
        import subprocess
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "").strip()
        if not sig:
            return None
        sock_path = os.path.join(str(self.runtime_dir()), "hypr", sig, ".socket.sock")
        output = b""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(sock_path)
                sock.sendall(f"j/{command}".encode())
                chunks = []
                while chunk := sock.recv(65536):
                    chunks.append(chunk)
                output = b"".join(chunks)
        except OSError:
            output = b""
        if output[:1] not in (b"{", b"["):
            try:
                done = subprocess.run(
                    ["hyprctl", command, "-j"],
                    stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout,
                )
                output = done.stdout if done.returncode == 0 else b""
            except (OSError, subprocess.TimeoutExpired):
                return None
        try:
            return json.loads(output) if output[:1] in (b"{", b"[") else None
        except ValueError:
            return None

    def sink_inputs(self, timeout=0.5):
        import json
        import subprocess
        try:
            done = subprocess.run(
                ["pactl", "-f", "json", "list", "sink-inputs"],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
            )
            if done.returncode != 0:
                return None
            if not done.stdout.strip():
                return []
            rows = json.loads(done.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        if not isinstance(rows, list):
            return None
        streams = []
        for row in rows:
            if not isinstance(row, dict) or "index" not in row:
                continue
            props = row.get("properties") or {}
            vol_map = row.get("volume") or {}
            volumes = [int(ch["value"]) for ch in vol_map.values()
                       if isinstance(ch, dict) and isinstance(ch.get("value"), (int, float))]
            raw_pid = props.get("application.process.id")
            streams.append({
                "index": int(row["index"]),
                "corked": bool(row.get("corked")),
                "mute": bool(row.get("mute")),
                "volumes": volumes,
                "app": str(props.get("application.name") or ""),
                "binary": str(props.get("application.process.binary") or ""),
                "pid": int(raw_pid) if str(raw_pid or "").isdigit() else None,
                "media": str(props.get("media.name") or ""),
                "title": str(props.get("media.title") or props.get("node.description") or ""),
                "node": str(props.get("node.name") or ""),
                "passive": str(props.get("node.passive") or "").lower() == "true",
                "virtual": str(props.get("node.virtual") or "").lower() == "true",
            })
        return streams

    sound_settings = "your sound settings"  # Where a person picks the microphone, in one plain phrase.

    # relay.py verify's checks of this system, one function each. A Mac returns None from any it does not check yet,
    # and verify then says so, rather than passing it.
    def service_health(self, timeout=5.0):
        """Rook's login service now: {"active": bool, "restarts": int or None}, or None when there is no unit."""
        import subprocess
        try:
            done = subprocess.run(["systemctl", "--user", "show", "rook.service", "-p", "LoadState", "-p",
                                   "ActiveState", "-p", "NRestarts"], stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            return None
        fields = dict(line.split("=", 1) for line in done.stdout.splitlines() if "=" in line)
        if done.returncode or fields.get("LoadState") != "loaded":
            return None
        restarts = fields.get("NRestarts", "")
        return {"active": fields.get("ActiveState") == "active", "restarts": int(restarts) if restarts.isdigit() else None}

    def talk_key_access(self):
        """Whether this process may read the keyboards for the talk key: the input group. Run inside Rook, it is
        Rook's own groups, which change only at a new login."""
        import grp
        names = set()
        for gid in os.getgroups():
            try:
                names.add(grp.getgrgid(gid).gr_name)
            except KeyError:
                pass
        return "input" in names

    def mic_access(self):
        """Whether this process may record. Linux has no microphone permission."""
        return True

    def audio_device(self, direction="input", timeout=2.0):
        """The default input (or output) device, as {"name": ..., "kind": ...}. kind is real, virtual (a monitor of an
        output, or the sound server's own dummy device: nothing a person speaks into or hears), none (no such device
        at all), or unknown (cannot tell, such as a noise filter or effects node in front of real hardware). Only a
        device positively known to be a loopback is virtual, so a real setup never reads as broken."""
        import json
        import subprocess
        kind = "source" if direction == "input" else "sink"
        try:
            default = subprocess.run(["pactl", f"get-default-{kind}"], stdin=subprocess.DEVNULL, capture_output=True,
                                     text=True, timeout=timeout).stdout.strip()
            listed = subprocess.run(["pactl", "-f", "json", "list", f"{kind}s"], stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=timeout)
            rows = json.loads(listed.stdout) if listed.returncode == 0 and listed.stdout.strip() else None
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {"name": None, "kind": "unknown"}
        if not isinstance(rows, list):
            return {"name": None, "kind": "unknown"}
        row = next((r for r in rows if isinstance(r, dict) and r.get("name") == default), None)
        if row is None:
            real = [r for r in rows if isinstance(r, dict)
                    and (r.get("properties") or {}).get("device.class") != "monitor"]
            return {"name": None, "kind": "none" if not real else "unknown"}
        props = row.get("properties") or {}
        name = row.get("description") or default
        if props.get("device.class") == "monitor" or default in ("auto_null", "auto_null.monitor"):
            return {"name": name, "kind": "virtual"}
        return {"name": name, "kind": "real" if props.get("device.api") else "unknown", "muted": row.get("mute") is True}

    def microphone_busy(self, timeout=0.4):
        import json
        import subprocess
        try:
            done = subprocess.run(
                ["pactl", "-f", "json", "list", "source-outputs"],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
            )
            if done.returncode != 0:
                return None
            if not done.stdout.strip():
                return []
            rows = json.loads(done.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        if not isinstance(rows, list):
            return None
        return call_streams(rows)

    def set_sink_input_volume(self, index, values, timeout=0.5):
        import subprocess
        if not values:
            return False, "No channel volumes given."
        clamped = [str(max(0, min(131072, int(v)))) for v in values]
        try:
            done = subprocess.run(
                ["pactl", "set-sink-input-volume", str(int(index)), *clamped],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"Could not run pactl: {error}"
        if done.returncode != 0:
            msg = (done.stderr or done.stdout or "").strip()
            return False, msg or f"pactl exited with code {done.returncode}."
        return True, None

    def desktop_theme(self):
        import subprocess
        try:
            scheme = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                                    capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None
        return "light" if "prefer-light" in scheme else "dark" if scheme.strip() else None

    def play_pcm(self, sample_rate, volume, generate, text, stop, voiced, on_start, on_length, played, levels=None):
        import queue
        import subprocess
        import threading
        error = None
        with subprocess.Popen(
            ["pw-play", "--raw", "--rate", str(sample_rate),
             "--channels", "1", "--format", "s16", "--latency", "40ms",
             "--volume", str(volume), "-"],
            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ) as player:
            def stop_player():
                while player.poll() is None:
                    if stop.wait(0.1):
                        player.terminate()
                        return

            threading.Thread(target=stop_player, daemon=True).start()
            # Generation runs ahead of playback: Phonon at about 14x real time, Qwen at about 5x. So the
            # item's real length is known long before it ends, and the caption re-times to it.
            chunks, made, finished, halt = queue.Queue(), [0, 0, 0], threading.Event(), threading.Event()

            def produce():
                try:
                    for audio in generate(text, stop):
                        if stop.is_set() or halt.is_set():
                            return
                        voiced(made, audio)
                        chunks.put(audio)
                    finished.set()
                except Exception as exc:
                    chunks.put(exc)
                finally:
                    chunks.put(None)

            producer = threading.Thread(target=produce, daemon=True)
            producer.start()
            told = False
            try:
                while (audio := chunks.get()) is not None:
                    if isinstance(audio, Exception):
                        raise audio
                    if stop.is_set():
                        break
                    if not played[0]:
                        on_start()
                    if levels is not None:
                        levels.push(audio)
                    player.stdin.write(audio)
                    player.stdin.flush()
                    voiced(played, audio)
                    if finished.is_set() and not told:
                        told = True
                        on_length(round(made[2] / sample_rate, 2))
                if levels is not None:
                    levels.finish()
                player.stdin.close()
                if player.wait() and not stop.is_set():
                    error = "PipeWire could not play the reply."
            except BrokenPipeError:
                if not stop.is_set():
                    error = "PipeWire closed the audio stream."
            finally:
                if levels is not None:
                    levels.close()
                halt.set()
                producer.join()  # One item generates at a time, and its problem is read after playback.
        return error

    def copy_clipboard(self, text):
        return NOT_YET

    def service_state(self, unit):
        return "inactive"

    def service_restart(self, try_only=False):
        return 1, NOT_YET

    def exit_process(self, code):
        # Skip exit handlers so PortAudio's JACK backend cannot abort on shutdown.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)


class _Mac(_Linux):
    supports_overlay = False
    supports_capture = False
    supports_hyprland = False

    def runtime_dir(self):
        if env_rt := os.environ.get("XDG_RUNTIME_DIR"):
            return Path(env_rt)
        # Keep the AF_UNIX socket path well under macOS's 104-byte sun_path limit.
        candidate = self.cache_dir() / "rook/run"
        if len(str(candidate / "rook.sock")) < 100:
            return candidate
        return Path(f"/tmp/rook-{os.getuid()}")

    def python_exe(self):
        return sys.executable

    def python3_exe(self):
        return sys.executable

    def false_exe(self):
        import shutil
        return "/usr/bin/false" if os.path.exists("/usr/bin/false") else (shutil.which("false") or "/usr/bin/false")

    def find_tool(self, name):
        import shutil
        found = shutil.which(name)
        if found:
            return found
        extras = [f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"]
        if name == "tailscale":
            extras.append("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
        for path in extras:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None

    def ffmpeg_exe(self):
        return self.find_tool("ffmpeg") or "ffmpeg"

    def tailscale_exe(self):
        return self.find_tool("tailscale") or "tailscale"

    def uptime_seconds(self):
        import time
        try:
            return _mach_continuous_seconds()
        except OSError:
            return time.monotonic()

    def process_cwd(self, pid, fallback=None):
        import subprocess
        if pid:
            try:
                done = subprocess.run(
                    ["/usr/sbin/lsof", "-a", "-p", str(int(pid)), "-d", "cwd", "-Fn"],
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1.0,
                )
                if done.returncode == 0:
                    for line in done.stdout.splitlines():
                        if line.startswith("n/"):
                            return line[1:]
            except (OSError, subprocess.TimeoutExpired, ValueError):
                pass
        return fallback or os.getcwd()

    def desktop_capabilities(self, timeout=1.0):
        return {"hyprland": False, "overlay": False, "capture": False, "grim": False}

    def find_session(self):
        return []

    def has_keys(self):
        return False

    def has_media(self):
        return False

    def stage_command(self):
        return None

    def mpris_list(self, timeout=0.5):
        return []

    def mpris_properties(self, bus_name, interface, timeout=0.5):
        return {}

    def mpris_call(self, bus_name, method, timeout=1.0):
        return False, NOT_YET

    def hyprland_json(self, command, timeout=0.5):
        return None

    def sink_inputs(self, timeout=0.5):
        return []

    def microphone_busy(self, timeout=0.4):
        return []

    sound_settings = "System Settings, Sound, Input"

    def service_health(self, timeout=5.0):
        """launchd's job state. launchd keeps no restart count that verify reads, so restarts is None."""
        return {"active": self.service_state("rook.service") == "active", "restarts": None}

    def helper_access(self, timeout=10.0):
        """Rook.app's own permissions, from RookHelper --check-access, as a dict, or None when it cannot tell. It is
        true only inside Rook, whose process belongs to Rook.app (the launcher sets ROOK_MAC_HELPER): from another
        terminal, macOS would answer for that terminal. The check never prompts. It does list Rook, switched off,
        under Accessibility (AXIsProcessTrusted), which is harmless and expected."""
        import json
        import subprocess
        helper = os.environ.get("ROOK_MAC_HELPER")
        if not helper:
            return None
        try:
            done = subprocess.run([helper, "--check-access"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=timeout)
            state = json.loads(done.stdout.strip().splitlines()[-1])
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
            return None
        return state if isinstance(state, dict) else None

    def talk_key_access(self):
        """Whether Input Monitoring is in force for this build of Rook.app. A switch left on for an older build that was
        signed differently reads false here, which is the truth: the key stays deaf."""
        state = self.helper_access()
        return None if state is None else state.get("input") is True

    def mic_access(self):
        """Whether Rook.app may record."""
        state = self.helper_access()
        return None if state is None else state.get("microphone") == "allowed"

    def audio_device(self, direction="input", timeout=10.0):
        """The default input (or output) device, from system_profiler: virtual for a CoreAudio virtual device such as
        a loopback driver, real for built-in, USB, Bluetooth and other hardware, unknown for an aggregate."""
        import json
        import subprocess
        try:
            done = subprocess.run(["system_profiler", "SPAudioDataType", "-json"], stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=timeout)
            groups = json.loads(done.stdout).get("SPAudioDataType") or []
        except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
            return {"name": None, "kind": "unknown"}
        flag, count = (("coreaudio_default_audio_input_device", "coreaudio_device_input") if direction == "input" else
                       ("coreaudio_default_audio_output_device", "coreaudio_device_output"))
        devices = [d for g in groups if isinstance(g, dict) for d in g.get("_items") or () if isinstance(d, dict)]
        device = next((d for d in devices if d.get(flag) == "spaudio_yes"), None)
        if device is None:
            return {"name": None, "kind": "none" if not any(d.get(count) for d in devices) else "unknown"}
        transport = str(device.get("coreaudio_device_transport") or "")
        kind = ("virtual" if transport.endswith("_virtual") else "unknown" if transport.endswith("_aggregate") or not transport
                else "real")
        return {"name": device.get("_name"), "kind": kind}

    def set_sink_input_volume(self, index, values, timeout=0.5):
        return False, NOT_YET

    def desktop_theme(self):
        import subprocess
        try:
            done = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                  capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if done.returncode == 0 and "dark" in done.stdout.lower():
            return "dark"
        if done.returncode == 1:
            return "light"
        return None

    def _mac_audio_devices(self):
        import ctypes
        ca = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

        class _Addr(ctypes.Structure):
            _fields_ = [("mSelector", ctypes.c_uint32), ("mScope", ctypes.c_uint32), ("mElement", ctypes.c_uint32)]

        ca.AudioObjectGetPropertyDataSize.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(_Addr), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
        ]
        ca.AudioObjectGetPropertyDataSize.restype = ctypes.c_int32
        ca.AudioObjectGetPropertyData.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(_Addr), ctypes.c_uint32, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p,
        ]
        ca.AudioObjectGetPropertyData.restype = ctypes.c_int32
        cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFRelease.argtypes = [ctypes.c_void_p]

        def fourcc(tag):
            return int.from_bytes(tag.encode("ascii"), "big")

        glob, outp = fourcc("glob"), fourcc("outp")

        def get_u32(obj, tag, scope=glob):
            addr = _Addr(fourcc(tag), scope, 0)
            val, size = ctypes.c_uint32(0), ctypes.c_uint32(4)
            st = ca.AudioObjectGetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(val))
            return val.value if st == 0 else None

        def get_str(obj, tag):
            addr = _Addr(fourcc(tag), glob, 0)
            ref = ctypes.c_void_p()
            size = ctypes.c_uint32(ctypes.sizeof(ref))
            st = ca.AudioObjectGetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(ref))
            if st != 0 or not ref.value:
                return None
            buf = ctypes.create_string_buffer(512)
            ok = cf.CFStringGetCString(ref, buf, 512, 0x08000100)
            cf.CFRelease(ref)
            return buf.value.decode("utf-8", "replace") if ok else None

        def has_output(dev):
            addr = _Addr(fourcc("stm#"), outp, 0)
            size = ctypes.c_uint32(0)
            return ca.AudioObjectGetPropertyDataSize(dev, ctypes.byref(addr), 0, None, ctypes.byref(size)) == 0 and size.value > 0

        default_id = get_u32(1, "dOut")
        addr = _Addr(fourcc("dev#"), glob, 0)
        size = ctypes.c_uint32(0)
        if ca.AudioObjectGetPropertyDataSize(1, ctypes.byref(addr), 0, None, ctypes.byref(size)) != 0 or size.value < 4:
            return [], default_id
        ids = (ctypes.c_uint32 * (size.value // 4))()
        if ca.AudioObjectGetPropertyData(1, ctypes.byref(addr), 0, None, ctypes.byref(size), ids) != 0:
            return [], default_id
        devices = []
        for dev in ids:
            if not has_output(dev):
                continue
            tt = get_u32(dev, "tran")
            devices.append({
                "id": int(dev),
                "name": get_str(dev, "lnam") or "",
                "uid": get_str(dev, "uid ") or "",
                "transport": tt.to_bytes(4, "big").decode("ascii", "replace") if tt is not None else "",
                "alive": get_u32(dev, "livn") != 0,
            })
        return devices, default_id

    @staticmethod
    def _choose_output_uid(devices, default_id, wanted=None):
        """Pick a CoreAudio output device UID, skipping virtual defaults (e.g. BlackHole) when hardware output exists."""
        want = (wanted or "").strip()
        if want:
            low = want.lower()
            for dev in devices:
                if dev.get("uid") == want or dev.get("name", "").lower() == low:
                    return dev.get("uid") or want
            return want
        default_dev = next((d for d in devices if d.get("id") == default_id), None)
        if default_dev and default_dev.get("alive", True) and default_dev.get("transport") != "virt":
            return None
        hardware = [d for d in devices if d.get("alive", True) and d.get("transport") != "virt" and d.get("uid")]
        for dev in hardware:
            if dev.get("transport") == "bltn":
                return dev["uid"]
        return hardware[0]["uid"] if hardware else None

    def play_pcm(self, sample_rate, volume, generate, text, stop, voiced, on_start, on_length, played, levels=None):
        import ctypes
        import queue
        import threading
        import time
        import wave
        # Stream 16-bit mono PCM through native CoreAudio AudioQueue (no PortAudio), or a null/file sink when ROOK_AUDIO_OUT is set.
        sink_spec = (os.environ.get("ROOK_AUDIO_OUT") or "").strip()

        def scale_pcm(data):
            if volume == 1.0 or not data:
                return data
            from array import array
            arr = array("h")
            arr.frombytes(data)
            for idx in range(len(arr)):
                val = int(round(arr[idx] * volume))
                arr[idx] = -32768 if val < -32768 else (32767 if val > 32767 else val)
            return arr.tobytes()

        class _FileSink:
            def __init__(self):
                self._wav = None
                self._raw = None
                self._closed = False
                if sink_spec == "null":
                    return
                path = Path(sink_spec)
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix.lower() == ".wav":
                    w = wave.open(str(path), "wb")
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(sample_rate)
                    self._wav = w
                else:
                    self._raw = open(path, "wb")

            def write(self, data, _stop):
                if self._closed or not data:
                    return
                scaled = scale_pcm(data)
                if self._wav is not None:
                    self._wav.writeframes(scaled)
                elif self._raw is not None:
                    self._raw.write(scaled)

            def drain(self, _stop):
                return

            def abort(self):
                self._closed = True

            def close(self):
                self._closed = True
                if self._wav is not None:
                    self._wav.close()
                    self._wav = None
                if self._raw is not None:
                    self._raw.close()
                    self._raw = None

        mac_self = self

        class _AudioQueueSink:
            _leaked_callbacks = []

            def __init__(self):
                self._at = ctypes.CDLL("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox")
                self._cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

                class _ASBD(ctypes.Structure):
                    _fields_ = [
                        ("mSampleRate", ctypes.c_double), ("mFormatID", ctypes.c_uint32),
                        ("mFormatFlags", ctypes.c_uint32), ("mBytesPerPacket", ctypes.c_uint32),
                        ("mFramesPerPacket", ctypes.c_uint32), ("mBytesPerFrame", ctypes.c_uint32),
                        ("mChannelsPerFrame", ctypes.c_uint32), ("mBitsPerChannel", ctypes.c_uint32),
                        ("mReserved", ctypes.c_uint32),
                    ]

                class _AQBuf(ctypes.Structure):
                    _fields_ = [
                        ("mAudioDataBytesCapacity", ctypes.c_uint32), ("mAudioData", ctypes.c_void_p),
                        ("mAudioDataByteSize", ctypes.c_uint32), ("mUserData", ctypes.c_void_p),
                        ("mPacketDescriptionCapacity", ctypes.c_uint32), ("mPacketDescriptions", ctypes.c_void_p),
                        ("mPacketDescriptionCount", ctypes.c_uint32),
                    ]

                aq_ref = ctypes.c_void_p
                buf_ptr = ctypes.POINTER(_AQBuf)
                cb_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, aq_ref, buf_ptr)
                at, cf = self._at, self._cf
                at.AudioQueueNewOutput.argtypes = [
                    ctypes.POINTER(_ASBD), cb_type, ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(aq_ref),
                ]
                at.AudioQueueNewOutput.restype = ctypes.c_int32
                at.AudioQueueSetProperty.argtypes = [aq_ref, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
                at.AudioQueueSetProperty.restype = ctypes.c_int32
                at.AudioQueueSetParameter.argtypes = [aq_ref, ctypes.c_uint32, ctypes.c_float]
                at.AudioQueueSetParameter.restype = ctypes.c_int32
                at.AudioQueueAllocateBuffer.argtypes = [aq_ref, ctypes.c_uint32, ctypes.POINTER(buf_ptr)]
                at.AudioQueueAllocateBuffer.restype = ctypes.c_int32
                at.AudioQueueEnqueueBuffer.argtypes = [aq_ref, buf_ptr, ctypes.c_uint32, ctypes.c_void_p]
                at.AudioQueueEnqueueBuffer.restype = ctypes.c_int32
                at.AudioQueueFreeBuffer.argtypes = [aq_ref, buf_ptr]
                at.AudioQueueFreeBuffer.restype = ctypes.c_int32
                at.AudioQueueStart.argtypes = [aq_ref, ctypes.c_void_p]
                at.AudioQueueStart.restype = ctypes.c_int32
                at.AudioQueueStop.argtypes = [aq_ref, ctypes.c_uint8]
                at.AudioQueueStop.restype = ctypes.c_int32
                at.AudioQueueDispose.argtypes = [aq_ref, ctypes.c_uint8]
                at.AudioQueueDispose.restype = ctypes.c_int32
                cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
                cf.CFStringCreateWithCString.restype = ctypes.c_void_p
                cf.CFRelease.argtypes = [ctypes.c_void_p]

                self._buf_ptr = buf_ptr
                self._op_lock = threading.Lock()
                self._cond = threading.Condition()
                self._pending = 0
                self._queued_bytes = 0
                self._returned = []
                self._started = False
                self._aborted = False
                self._closed = False
                self._start_hung = False
                self._q = aq_ref()

                @cb_type
                def _on_buf_done(_user_data, _aq, buf):
                    nbytes = int(buf.contents.mAudioDataByteSize) if buf else 0
                    with self._cond:
                        self._pending = max(0, self._pending - 1)
                        self._queued_bytes = max(0, self._queued_bytes - nbytes)
                        if buf:
                            self._returned.append(buf)
                        self._cond.notify_all()

                self._cb = _on_buf_done
                asbd = _ASBD(float(sample_rate), 0x6C70636D, 4 | 8, 2, 1, 2, 1, 16, 0)
                st = at.AudioQueueNewOutput(ctypes.byref(asbd), self._cb, None, None, None, 0, ctypes.byref(self._q))
                if st != 0 or not self._q.value:
                    raise OSError(f"AudioQueueNewOutput failed ({st})")

                wanted = (os.environ.get("ROOK_AUDIO_DEVICE") or "").strip() or None
                try:
                    devices, default_id = mac_self._mac_audio_devices()
                    device_uid = mac_self._choose_output_uid(devices, default_id, wanted=wanted)
                except OSError:
                    device_uid = wanted
                if device_uid:
                    cf_uid = cf.CFStringCreateWithCString(None, device_uid.encode("utf-8"), 0x08000100)
                    if cf_uid:
                        ptr = ctypes.c_void_p(cf_uid)
                        at.AudioQueueSetProperty(self._q, 0x61716364, ctypes.byref(ptr), ctypes.sizeof(ptr))
                        cf.CFRelease(cf_uid)
                at.AudioQueueSetParameter(self._q, 1, ctypes.c_float(max(0.0, min(1.0, float(volume)))))

            def _free_returned_locked(self):
                with self._cond:
                    stale, self._returned = self._returned, []
                for buf in stale:
                    self._at.AudioQueueFreeBuffer(self._q, buf)

            def _start_bounded(self, timeout=3.0):
                result = [None]

                def go():
                    result[0] = self._at.AudioQueueStart(self._q, None)

                starter = threading.Thread(target=go, daemon=True)
                starter.start()
                starter.join(timeout)
                if starter.is_alive():
                    self._start_hung = True
                    self._leaked_callbacks.append(self._cb)
                    raise TimeoutError("CoreAudio timed out starting playback.")
                if result[0] != 0:
                    raise OSError(f"AudioQueueStart failed ({result[0]})")

            def write(self, data, stop_ev):
                if not data or self._closed or self._aborted or stop_ev.is_set():
                    return
                max_queued = max(4096, int(sample_rate * 2))  # ~1s lookahead for gapless streaming and prompt barge-in.
                with self._cond:
                    deadline = time.monotonic() + 5.0
                    while (self._pending >= 2 and self._queued_bytes >= max_queued
                           and not self._aborted and not self._closed and not stop_ev.is_set()):
                        rem = deadline - time.monotonic()
                        if rem <= 0:
                            raise TimeoutError("CoreAudio stalled during playback.")
                        self._cond.wait(min(rem, 0.1))
                if self._closed or self._aborted or stop_ev.is_set():
                    return
                need_start = False
                with self._op_lock:
                    if self._closed or self._aborted or not self._q.value:
                        return
                    self._free_returned_locked()
                    buf = self._buf_ptr()
                    st = self._at.AudioQueueAllocateBuffer(self._q, len(data), ctypes.byref(buf))
                    if st != 0:
                        raise OSError(f"AudioQueueAllocateBuffer failed ({st})")
                    ctypes.memmove(buf.contents.mAudioData, data, len(data))
                    buf.contents.mAudioDataByteSize = len(data)
                    with self._cond:
                        self._pending += 1
                        self._queued_bytes += len(data)
                    st = self._at.AudioQueueEnqueueBuffer(self._q, buf, 0, None)
                    if st != 0:
                        with self._cond:
                            self._pending = max(0, self._pending - 1)
                            self._queued_bytes = max(0, self._queued_bytes - len(data))
                        self._at.AudioQueueFreeBuffer(self._q, buf)
                        raise OSError(f"AudioQueueEnqueueBuffer failed ({st})")
                    need_start = not self._started
                if need_start:
                    self._start_bounded()
                    with self._op_lock:
                        self._started = True
                        if (self._aborted or stop_ev.is_set()) and self._q.value:
                            self._at.AudioQueueStop(self._q, 1)

            def drain(self, stop_ev):
                with self._cond:
                    wait_budget = max(5.0, (self._queued_bytes / max(1, sample_rate * 2)) + 5.0)
                    deadline = time.monotonic() + wait_budget
                    while self._pending > 0 and not self._aborted and not self._closed and not stop_ev.is_set():
                        rem = deadline - time.monotonic()
                        if rem <= 0:
                            raise TimeoutError("CoreAudio timed out finishing playback.")
                        self._cond.wait(min(rem, 0.1))

            def abort(self):
                with self._cond:
                    self._aborted = True
                    self._cond.notify_all()
                with self._op_lock:
                    if self._q.value and self._started and not self._closed and not self._start_hung:
                        self._at.AudioQueueStop(self._q, 1)

            def close(self):
                with self._cond:
                    self._closed = True
                    self._cond.notify_all()
                with self._op_lock:
                    q, self._q = self._q, ctypes.c_void_p()
                    if q.value and not self._start_hung:
                        if self._started:
                            self._at.AudioQueueStop(q, 1 if (stop.is_set() or self._aborted) else 0)
                        self._at.AudioQueueDispose(q, 1)

        error = None
        try:
            sink = _FileSink() if sink_spec else _AudioQueueSink()
        except Exception as exc:
            return None if stop.is_set() else f"CoreAudio could not play the reply: {exc}"
        chunks, made, finished, halt = queue.Queue(), [0, 0, 0], threading.Event(), threading.Event()
        done_playing = threading.Event()

        def stop_player():
            while not done_playing.is_set():
                if stop.wait(0.05):
                    sink.abort()
                    return

        stopper = threading.Thread(target=stop_player, daemon=True)
        stopper.start()

        def produce():
            try:
                for audio in generate(text, stop):
                    if stop.is_set() or halt.is_set():
                        return
                    voiced(made, audio)
                    chunks.put(audio)
                finished.set()
            except Exception as exc:
                chunks.put(exc)
            finally:
                chunks.put(None)

        producer = threading.Thread(target=produce, daemon=True)
        producer.start()
        told = False
        try:
            while (audio := chunks.get()) is not None:
                if isinstance(audio, Exception):
                    raise audio
                if stop.is_set():
                    break
                if not played[0]:
                    on_start()
                if levels is not None:
                    levels.push(audio)
                sink.write(audio, stop)
                voiced(played, audio)
                if finished.is_set() and not told:
                    told = True
                    on_length(round(made[2] / sample_rate, 2))
            if finished.is_set() and not told and not stop.is_set():
                told = True
                on_length(round(made[2] / sample_rate, 2))
            if not stop.is_set():
                sink.drain(stop)
            if levels is not None:
                levels.finish()
        except Exception as exc:
            if not stop.is_set():
                error = f"CoreAudio could not play the reply: {exc}"
        finally:
            done_playing.set()
            sink.close()
            if levels is not None:
                levels.close()
            halt.set()
            producer.join()
        return error

    def copy_clipboard(self, text):
        import subprocess
        try:
            copied = subprocess.run(["/usr/bin/pbcopy"], input=text, text=True, capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            return f"Could not run pbcopy: {error}"
        if copied.returncode:
            return (copied.stderr or copied.stdout).strip() or f"pbcopy failed with exit code {copied.returncode}."
        try:
            pasted = subprocess.run(["/usr/bin/pbpaste"], stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired) as error:
            return f"Could not read the clipboard: {error}"
        if pasted.returncode != 0 or pasted.stdout != text:
            return "Clipboard did not hold the copied text."
        return None

    def service_state(self, unit):
        import subprocess
        if unit != "rook.service":
            return "inactive"
        target = f"gui/{os.getuid()}/{LAUNCHD_LABEL}"
        try:
            done = subprocess.run(["launchctl", "print", target], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return "inactive"
        return "active" if done.returncode == 0 and "state = running" in done.stdout else "inactive"

    def service_restart(self, try_only=False):
        import subprocess
        if try_only and self.service_state("rook.service") != "active":
            return 0, ""
        target = f"gui/{os.getuid()}/{LAUNCHD_LABEL}"
        try:
            done = subprocess.run(["launchctl", "kickstart", "-k", target], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, str(error)
        return done.returncode, (done.stderr or done.stdout or "").strip()

    def exit_process(self, code):
        sys.stdout.flush()
        sys.stderr.flush()
        sys.exit(code)


PLATFORM = _Mac() if IS_MAC else _Linux()


def ensure_dir(path):
    """Create a private directory (mode 0700) owned by this user, refusing symlinks."""
    import stat
    folder = Path(path)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = folder.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise OSError(f"Refusing unsafe runtime folder {folder}")
    folder.chmod(0o700)
    return folder


def runtime_dir():
    return PLATFORM.runtime_dir()


def config_dir():
    return PLATFORM.config_dir()


def state_dir():
    return PLATFORM.state_dir()


def data_dir():
    return PLATFORM.data_dir()


def cache_dir():
    return PLATFORM.cache_dir()


def python_exe():
    return PLATFORM.python_exe()


def python3_exe():
    return PLATFORM.python3_exe()


def false_exe():
    return PLATFORM.false_exe()


def ffmpeg_exe():
    return PLATFORM.ffmpeg_exe()


def find_tool(name):
    return PLATFORM.find_tool(name)


def tailscale_exe():
    return PLATFORM.tailscale_exe()


def uptime_seconds():
    return PLATFORM.uptime_seconds()


def process_cwd(pid, fallback=None):
    """The folder a process runs in, else fallback, else Rook's own folder."""
    return PLATFORM.process_cwd(pid, fallback)


def desktop_capabilities(timeout=1.0):
    return PLATFORM.desktop_capabilities(timeout=timeout)


def find_session():
    return PLATFORM.find_session()


def wayland_alive():
    """Whether the Wayland socket named by WAYLAND_DISPLAY still takes a connection."""
    display = os.environ.get("WAYLAND_DISPLAY", "").strip()
    return bool(display) and PLATFORM.socket_alive(os.path.join(str(PLATFORM.runtime_dir()), display))


def has_keys():
    return PLATFORM.has_keys()


def stage_command():
    return PLATFORM.stage_command()


def has_media():
    return PLATFORM.has_media()


def mpris_list(timeout=0.5):
    return PLATFORM.mpris_list(timeout=timeout)


def mpris_properties(bus_name, interface, timeout=0.5):
    return PLATFORM.mpris_properties(bus_name, interface, timeout=timeout)


def mpris_call(bus_name, method, timeout=1.0):
    return PLATFORM.mpris_call(bus_name, method, timeout=timeout)


def hyprland_json(command, timeout=0.5):
    return PLATFORM.hyprland_json(command, timeout=timeout)


def companion_screen_monitor(monitors, wanted):
    """The monitor in Hyprland's monitor list that the companion_screen setting names, or None. wanted is the connector
    name, such as DP-2, or text in the monitor's description, in any case, since a port can change on a replug."""
    wanted = (wanted or "").strip().casefold()
    if not wanted or wanted == "off" or not isinstance(monitors, list):
        return None
    mons = [m for m in monitors if isinstance(m, dict)]
    return (next((m for m in mons if str(m.get("name", "")).casefold() == wanted), None)
            or next((m for m in mons if wanted in str(m.get("description", "")).casefold()), None))


def sink_inputs(timeout=0.5):
    return PLATFORM.sink_inputs(timeout=timeout)


def microphone_busy(timeout=0.4):
    return PLATFORM.microphone_busy(timeout=timeout)


def audio_device(direction="input"):
    """The default input or output device: {"name": str or None, "kind": "real" | "virtual" | "none" | "unknown"}."""
    return PLATFORM.audio_device(direction)


def input_problem(device=None):
    """Why Rook cannot hear the person, as the one sentence Rook says, or None when the input is real or cannot be
    told. device is an audio_device("input") result, looked up when not given. The turn path and relay.py verify share
    these words."""
    device = device or audio_device("input")
    if device["kind"] == "none":
        return f"I can't hear you: this computer has no microphone. Plug one in, or pick it in {PLATFORM.sound_settings}."
    if device["kind"] == "virtual":
        return (f"I can't hear you: the only input here is {device['name']}, which is not a microphone. Plug one in, "
                f"or pick it in {PLATFORM.sound_settings}.")
    return None


def silence_sentence(device=None):
    """What Rook says after a recording of pure digital silence: a dead or virtual input. device as in input_problem."""
    device = device or audio_device("input")
    heard = f"from {device['name']}" if device.get("name") else "from the microphone"
    return (f"I heard only silence {heard}. If that is not your microphone, pick a real one in "
            f"{PLATFORM.sound_settings}, then try again.")


def set_sink_input_volume(index, values, timeout=0.5):
    return PLATFORM.set_sink_input_volume(index, values, timeout=timeout)


def desktop_theme():
    return PLATFORM.desktop_theme()


def play_pcm(sample_rate, volume, generate, text, stop, voiced, on_start, on_length, played, levels=None):
    return PLATFORM.play_pcm(sample_rate, volume, generate, text, stop, voiced, on_start, on_length, played, levels=levels)


def copy_clipboard(text):
    return PLATFORM.copy_clipboard(text)


def service_state(unit):
    return PLATFORM.service_state(unit)


def service_restart(try_only=False):
    return PLATFORM.service_restart(try_only=try_only)


def remote_size_command(path):
    """Portable command to print a file's byte size (following symlinks) on Linux or macOS."""
    return ["sh", "-c", 'stat -L -c %s -- "$1" 2>/dev/null || stat -L -f %z -- "$1"', "sh", path]


def mac_app():
    """Rook.app as Rook's launchd agent runs it: ProgramArguments[0] of its plist names the app's RookHelper, wherever
    the installer put the app (/Applications or ~/Applications). Without that plist, ~/Applications/Rook.app."""
    import plistlib
    label = os.environ.get("ROOK_LAUNCHD_LABEL") or "com.rook.companion"
    helper_tail = "/Contents/MacOS/RookHelper"
    try:
        with open(Path.home() / "Library/LaunchAgents" / f"{label}.plist", "rb") as plist:
            program = plistlib.load(plist)["ProgramArguments"][0]
        if isinstance(program, str) and program.endswith(helper_tail):
            return Path(program[:-len(helper_tail)])
    except (OSError, ValueError, KeyError, IndexError, TypeError, plistlib.InvalidFileException):
        pass
    return Path.home() / "Applications/Rook.app"


def exit_process(code):
    PLATFORM.exit_process(code)


class MacTalkRouter:
    """Translate RookHelper talk_key events (down, up, chord_cancel) into hold-to-talk, tap-to-toggle, and cancel."""

    def __init__(self, tap_seconds=0.35, on_start=None, on_stop=None, on_cancel=None, on_listen_end=None,
                 is_talking=None, clock=None):
        import time
        self.tap_seconds = tap_seconds
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_cancel = on_cancel
        self.on_listen_end = on_listen_end
        self.is_talking = is_talking or (lambda: False)
        self.clock = clock or time.monotonic
        self.mode = None  # "held" or "toggle"
        self.down_at = 0.0
        self.key = None

    def handle(self, event):
        if not isinstance(event, dict) or event.get("type") != "talk_key":
            return None
        action = event.get("action")
        key = event.get("key") or "RightOption"
        now = event["ts"] if isinstance(event.get("ts"), (int, float)) else self.clock()
        if action == "down":
            if self.on_listen_end and self.on_listen_end():
                return "listen_ended"
            if not self.is_talking():
                if self.on_start and self.on_start(key):
                    self.mode, self.down_at, self.key = "held", now, key
                    return "started"
                return "ignored"
            if self.mode == "toggle":
                self.mode = self.key = None
                if self.on_stop:
                    self.on_stop()
                return "stopped"
            return "ignored"
        if action == "chord_cancel":
            if self.mode == "held" and self.key == key:
                self.mode = self.key = None
                if self.on_cancel:
                    self.on_cancel()
                return "cancelled"
            return "ignored"
        if action == "up":
            if self.mode == "held" and self.key == key:
                held = event["held"] if isinstance(event.get("held"), (int, float)) else (now - self.down_at)
                if held >= self.tap_seconds:
                    self.mode = self.key = None
                    if self.on_stop:
                        self.on_stop()
                    return "stopped"
                self.mode = "toggle"
                return "toggled"
            return "ignored"
        return None


def _check():
    """Self-check platform paths, clock, size command, Linux seam, macOS streaming playback, and Mac talk key."""
    import json
    import socket
    import subprocess
    import tempfile
    import threading
    import wave
    assert runtime_dir() and config_dir() and state_dir() and data_dir() and cache_dir()
    assert uptime_seconds() > 0
    assert Path(python_exe()).exists()
    assert Path(python3_exe()).exists()
    assert Path(false_exe()).exists()
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="rkd-") as folder:
        base = Path(folder)
        sample = base / "sample.bin"
        sample.write_bytes(b"hello world")
        got = subprocess.run(remote_size_command(str(sample)), capture_output=True, text=True, check=True)
        assert got.stdout.strip() == "11", got.stdout
        wav_out = base / "streamed.wav"
        fake_bin = base / "bin"
        fake_bin.mkdir()
        rt_dir = base / "rt"
        rt_dir.mkdir(mode=0o700)
        saved_env = {k: os.environ.get(k) for k in (
            "PATH", "XDG_RUNTIME_DIR", "HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY", "DISPLAY", "ROOK_AUDIO_OUT")}
        os.environ["PATH"] = f"{fake_bin}:{saved_env['PATH'] or ''}"
        os.environ["XDG_RUNTIME_DIR"] = str(rt_dir)
        for k in ("HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY", "DISPLAY"):
            os.environ.pop(k, None)
        try:
            # Real desktop probes: without a live Hyprland socket or Wayland display they return False.
            import struct
            import time
            linux = _Linux()
            caps0 = linux.desktop_capabilities(timeout=0.2)
            assert not caps0["hyprland"] and not caps0["overlay"] and not caps0["capture"], caps0
            assert linux.has_keys() is True, "desk._Linux.has_keys: expected True"
            assert linux.has_media() is True, "desk._Linux.has_media: expected True"

            # Start-order pin for desk._Linux.hyprland_json: without HYPRLAND_INSTANCE_SIGNATURE it returns
            # None without invoking hyprctl; with a signature before the socket exists it falls back to hyprctl;
            # once the stand-in socket appears late it reads directly from the socket.
            hypr_log = base / "hyprctl.log"
            fake_hyprctl = fake_bin / "hyprctl"
            fake_hyprctl.write_text(
                f"#!{sys.executable}\nimport json, pathlib, sys\n"
                f"with pathlib.Path({str(hypr_log)!r}).open('a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "print(json.dumps({'source': 'cli', 'cmd': sys.argv[1]}))\n"
            )
            fake_hyprctl.chmod(0o755)
            assert linux.hyprland_json("activewindow") is None, "hyprland_json: missing signature must return None"
            assert not hypr_log.exists(), "hyprland_json: missing signature must not invoke hyprctl CLI"

            os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = "late"
            empty_bin = base / "empty_bin"
            empty_bin.mkdir()
            os.environ["PATH"] = str(empty_bin)
            assert linux.hyprland_json("activewindow") is None, "hyprland_json: absent socket and no CLI returns None"
            assert linux.desktop_capabilities(timeout=0.2)["hyprland"] is False, "absent socket must return False"

            os.environ["PATH"] = str(fake_bin)
            cli_reply = linux.hyprland_json("activewindow")
            assert cli_reply == {"source": "cli", "cmd": "activewindow"}, f"hyprland_json CLI fallback: {cli_reply}"
            assert linux.desktop_capabilities(timeout=0.2)["hyprland"] is False, "must probe live socket, not CLI"

            # Bring up the stand-in Hyprland socket late at the same signature.
            hypr_dir = rt_dir / "hypr" / "late"
            hypr_dir.mkdir(parents=True)
            sock_path = hypr_dir / ".socket.sock"
            stop_srv = threading.Event()
            hang_hypr = threading.Event()
            release_hypr = threading.Event()
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(sock_path))
            srv.listen(4)
            srv.settimeout(0.05)

            def _serve():
                while not stop_srv.is_set():
                    try:
                        conn, _ = srv.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    with conn:
                        req = conn.recv(4096).decode(errors="replace").strip()
                        if hang_hypr.is_set():
                            release_hypr.wait(timeout=2.0)
                            continue
                        conn.sendall(json.dumps({"source": "socket", "req": req}).encode())

            srv_thread = threading.Thread(target=_serve, daemon=True)
            srv_thread.start()
            try:
                calls_before = hypr_log.read_text() if hypr_log.exists() else ""
                sock_reply = linux.hyprland_json("activewindow")
                assert sock_reply == {"source": "socket", "req": "j/activewindow"}, f"hyprland_json late socket: {sock_reply}"
                assert (hypr_log.read_text() if hypr_log.exists() else "") == calls_before, (
                    "hyprland_json: late socket reply must not invoke hyprctl CLI"
                )
                assert linux.desktop_capabilities(timeout=0.2)["hyprland"] is True, "live socket must return True"
                hang_hypr.set()
                t0 = time.monotonic()
                assert linux.hyprland_session(timeout=0.12) is False, "hyprland_session: hung socket must return False"
                assert time.monotonic() - t0 < 0.4, "hyprland_session: hung socket exceeded total deadline"
                hang_hypr.clear()
                release_hypr.set()
            finally:
                stop_srv.set()
                release_hypr.set()
                srv.close()
                srv_thread.join(timeout=1.0)

            # Stand-in Wayland socket for desktop_capabilities() and total-deadline trickle bound.
            wl_globals = ["zwlr_layer_shell_v1", "ext_foreign_toplevel_list_v1"]
            wl_trickle = threading.Event()
            wl_stop = threading.Event()
            wl_path = rt_dir / "wl-desk"
            wl_srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            wl_srv.bind(str(wl_path))
            wl_srv.listen(4)
            wl_srv.settimeout(0.05)

            def _serve_wl():
                def _s(t):
                    b = t.encode() + b"\0"
                    return struct.pack("<I", len(b)) + b + b"\0" * (-len(b) % 4)
                def _m(o, op, p=b""):
                    return struct.pack("<IHH", o, op, 8 + len(p)) + p
                while not wl_stop.is_set():
                    try:
                        conn, _ = wl_srv.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    with conn:
                        conn.settimeout(0.5)
                        buf = b""
                        try:
                            while True:
                                chunk = conn.recv(4096)
                                if not chunk:
                                    break
                                buf += chunk
                                if wl_trickle.is_set():
                                    # Trickle partial bytes every 40 ms without sync done; total deadline must stop it.
                                    for _ in range(12):
                                        if wl_stop.is_set():
                                            break
                                        conn.sendall(b"\x02\x00")
                                        time.sleep(0.04)
                                    break
                                while len(buf) >= 8:
                                    obj, op, sz = struct.unpack_from("<IHH", buf)
                                    if len(buf) < sz:
                                        break
                                    body, buf = buf[8:sz], buf[sz:]
                                    if obj == 1 and op == 1:
                                        reg_id, = struct.unpack_from("<I", body)
                                        for idx, iface in enumerate(wl_globals, start=10):
                                            conn.sendall(_m(reg_id, 0, struct.pack("<I", idx) + _s(iface) + struct.pack("<I", 1)))
                                    elif obj == 1 and op == 0:
                                        cb_id, = struct.unpack_from("<I", body)
                                        conn.sendall(_m(cb_id, 0, struct.pack("<I", 1)))
                        except OSError:
                            pass

            wl_thread = threading.Thread(target=_serve_wl, daemon=True)
            wl_thread.start()
            os.environ["WAYLAND_DISPLAY"] = "wl-desk"
            fake_grim = fake_bin / "grim"
            fake_grim.write_text("#!/bin/sh\nexit 0\n")
            fake_grim.chmod(0o755)
            try:
                os.environ["PATH"] = str(empty_bin)
                c_nogrim = linux.desktop_capabilities(timeout=0.2)
                assert c_nogrim["overlay"] is True and c_nogrim["capture"] is False and c_nogrim["grim"] is False, c_nogrim
                os.environ["PATH"] = str(fake_bin)
                c_ok = linux.desktop_capabilities(timeout=0.2)
                assert c_ok["overlay"] is True and c_ok["capture"] is True and c_ok["grim"] is True, c_ok
                wl_globals[:] = ["wl_compositor"]
                c_none = linux.desktop_capabilities(timeout=0.2)
                assert c_none["overlay"] is False and c_none["capture"] is False, c_none
                # Total deadline bound on trickling Wayland socket.
                wl_trickle.set()
                t0 = time.monotonic()
                assert linux.wayland_globals(timeout=0.15) is None, "wayland_globals: trickle must time out"
                assert time.monotonic() - t0 < 0.35, "wayland_globals: trickle exceeded total deadline"
                t0 = time.monotonic()
                caps = linux.desktop_capabilities(timeout=0.2)
                assert not caps["overlay"] and not caps["capture"] and time.monotonic() - t0 < 0.4, caps
            finally:
                wl_stop.set()
                wl_srv.close()
                wl_thread.join(timeout=1.0)
                os.environ.pop("WAYLAND_DISPLAY", None)

            os.environ["PATH"] = f"{fake_bin}:{saved_env['PATH'] or ''}"
            mac = _Mac()
            assert not mac.supports_overlay and not mac.supports_capture and not mac.supports_hyprland
            assert not mac.has_keys() and mac.desktop_capabilities() == {
                "hyprland": False, "overlay": False, "capture": False, "grim": False,
            }
            assert mac.stage_command() is None
            assert not mac.has_media() and mac.mpris_list() == [] and mac.sink_inputs() == [] and mac.microphone_busy() == []
            assert mac.mpris_call("org.mpris.MediaPlayer2.test", "Pause") == (False, NOT_YET)
            assert mac.set_sink_input_volume(1, [65536]) == (False, NOT_YET)
            assert mac.hyprland_json("activewindow") is None
            assert _unwrap_dbus({"type": "a{sv}", "data": [{"PlaybackStatus": {"type": "s", "data": "Playing"}}]}) == {
                "PlaybackStatus": "Playing",
            }
            # Verify the single call-classification rule across non-calls and real calls.
            sample_streams = [
                {"corked": False, "properties": {"media.name": "Komplete input", "node.passive": "true",
                                                 "node.link-group": "loopback-1685576-12"}},
                {"corked": False, "properties": {"application.name": "gsr-default_output", "application.process.id": "101",
                                                 "application.process.binary": "gpu-screen-recorder",
                                                 "media.role": "production", "stream.capture.sink": "true"}},
                {"corked": False, "properties": {"application.name": "gsr-default_input", "application.process.id": "101",
                                                 "application.process.binary": "gpu-screen-recorder",
                                                 "media.role": "production"}},
                {"corked": False, "properties": {"application.name": "OBS", "application.process.id": "102",
                                                 "application.process.binary": "obs"}},
                {"corked": False, "properties": {"application.name": "Chromium", "application.process.id": "103",
                                                 "application.process.binary": "chromium", "stream.capture.sink": "true"}},
                {"corked": False, "properties": {"application.name": "MysteryTool", "application.process.id": "104",
                                                 "application.process.binary": "mystery-tool"}},
                {"corked": False, "properties": {"application.name": "WEBRTC VoiceEngine", "application.process.id": "105",
                                                 "application.process.binary": "Discord"}},
                {"corked": False, "properties": {"application.name": "Chromium", "application.process.id": "106",
                                                 "application.process.binary": "chromium"}},
                {"corked": False, "properties": {"application.name": "MeetApp", "application.process.id": "107",
                                                 "application.process.binary": "meetapp", "media.role": "communication"}},
                {"corked": True, "properties": {"application.name": "Zoom", "application.process.id": "108",
                                                "application.process.binary": "zoom"}},
            ]
            assert [c["pid"] for c in call_streams(sample_streams, own_pid=999)] == ["105", "106", "107"]
            assert call_streams(sample_streams, own_pid=105) == [
                {"name": "Chromium", "pid": "106", "binary": "chromium"},
                {"name": "MeetApp", "pid": "107", "binary": "meetapp"},
            ]
            # Verify macOS CoreAudio output selection skips virtual defaults (like BlackHole) when hardware output exists.
            mac_devs = [
                {"id": 79, "name": "BlackHole 2ch", "uid": "BlackHole2ch_UID", "transport": "virt", "alive": True},
                {"id": 73, "name": "Mac mini Speakers", "uid": "BuiltInSpeakerDevice", "transport": "bltn", "alive": True},
            ]
            assert mac._choose_output_uid(mac_devs, 79) == "BuiltInSpeakerDevice"
            assert mac._choose_output_uid(mac_devs, 73) is None
            assert mac._choose_output_uid(mac_devs, 79, wanted="BlackHole 2ch") == "BlackHole2ch_UID"
            assert mac._choose_output_uid(mac_devs, 79, wanted="BuiltInSpeakerDevice") == "BuiltInSpeakerDevice"
            assert mac._choose_output_uid(mac_devs[:1], 79) is None

            # Verify macOS streaming player against a file-backed WAV sink and null sink (zero speaker output).
            os.environ["ROOK_AUDIO_OUT"] = str(wav_out)
            started, lengths, span = [], [], [0, 0, 0]
            pcm = b"\x00\x10" * 1200  # 4096 amplitude, two streamed chunks = 2400 frames = 0.1s at 24kHz.

            def fake_voiced(s, data):
                s[0] += len(data) // 2
                s[1] = s[1] or 1
                s[2] = s[0]

            err = mac.play_pcm(
                24000, 0.5, lambda _t, _s: iter([pcm, pcm]), "Hi", threading.Event(),
                fake_voiced, lambda: started.append(1), lengths.append, span,
            )
            assert err is None and started == [1] and lengths == [0.1] and span[0] == 2400, (err, started, lengths, span)
            with wave.open(str(wav_out), "rb") as w:
                assert w.getframerate() == 24000 and w.getnframes() == 2400 and w.getnchannels() == 1
                raw = w.readframes(4)
                first_sample = int.from_bytes(raw[:2], "little", signed=True)
                assert first_sample == 2048, first_sample  # 4096 scaled by volume 0.5.

            # Verify null sink and barge-in stop mid-stream.
            os.environ["ROOK_AUDIO_OUT"] = "null"
            stop_ev, played_first = threading.Event(), threading.Event()
            stopped_span = [0, 0, 0]

            def halting_gen(_t, ev):
                yield pcm
                played_first.wait(1.0)
                ev.set()
                yield pcm

            err2 = mac.play_pcm(
                24000, 1.0, halting_gen, "Stop", stop_ev,
                fake_voiced, played_first.set, lambda _l: None, stopped_span,
            )
            assert err2 is None and stopped_span[0] == 1200, (err2, stopped_span)
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    # Verify MacTalkRouter hold, tap-toggle, and Right Option chord-cancel rules with a stand-in event source.
    log, talking = [], [False]

    def _start(_key):
        talking[0] = True
        log.append("start")
        return True

    def _stop():
        talking[0] = False
        log.append("stop")

    def _cancel():
        talking[0] = False
        log.append("cancel")

    router = MacTalkRouter(tap_seconds=0.35, on_start=_start, on_stop=_stop, on_cancel=_cancel,
                           is_talking=lambda: talking[0])
    # 1. Hold >= 0.35s then release stops recording.
    assert router.handle({"type": "talk_key", "action": "down", "key": "RightOption", "ts": 1.0}) == "started"
    assert router.handle({"type": "talk_key", "action": "up", "key": "RightOption", "held": 0.6, "ts": 1.6}) == "stopped"
    # 2. Quick tap switches to toggle; next press stops.
    assert router.handle({"type": "talk_key", "action": "down", "key": "RightOption", "ts": 2.0}) == "started"
    assert router.handle({"type": "talk_key", "action": "up", "key": "RightOption", "held": 0.1, "ts": 2.1}) == "toggled"
    assert talking[0] is True
    assert router.handle({"type": "talk_key", "action": "down", "key": "RightOption", "ts": 3.0}) == "stopped"
    # 3. Chord cancel (another key pressed while Right Option held) discards silently.
    assert router.handle({"type": "talk_key", "action": "down", "key": "RightOption", "ts": 4.0}) == "started"
    assert router.handle({"type": "talk_key", "action": "chord_cancel", "key": "RightOption", "ts": 4.05}) == "cancelled"
    assert router.handle({"type": "talk_key", "action": "up", "key": "RightOption", "held": 0.2, "ts": 4.2}) == "ignored"
    assert log == ["start", "stop", "start", "stop", "start", "cancel"], log

    # find_session: live sockets only, newest first, and a variable that is set never changes.
    import socket
    import tempfile
    saved = {k: os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY")}
    with tempfile.TemporaryDirectory(prefix="dk-", dir="/tmp") as run:
        servers = []
        for path in (f"{run}/hypr/old/.socket.sock", f"{run}/hypr/live/.socket.sock", f"{run}/wayland-1"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            server = socket.socket(socket.AF_UNIX)
            server.bind(path)
            server.listen()
            servers.append(server)
        servers.pop(0).close()  # hypr/old: a socket file nothing listens on, made newest below.
        os.utime(f"{run}/hypr/old/.socket.sock", (2e9, 2e9))
        try:
            os.environ["XDG_RUNTIME_DIR"] = run
            os.environ.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert PLATFORM.find_session() == ["HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY"]
            assert os.environ["HYPRLAND_INSTANCE_SIGNATURE"] == "live" and os.environ["WAYLAND_DISPLAY"] == "wayland-1"
            assert wayland_alive() and PLATFORM.find_session() == []
            os.environ["WAYLAND_DISPLAY"] = "wayland-9"  # Set by the session: kept, even though it is dead.
            assert PLATFORM.find_session() == [] and os.environ["WAYLAND_DISPLAY"] == "wayland-9" and not wayland_alive()
        finally:
            for server in servers:
                server.close()
            for key, value in saved.items():
                os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
    _check_setup_helpers()
    print("Desk platform seam: all checks passed.")


def _check_setup_helpers():
    """audio_device, input_problem, silence_sentence and the agents' signin_status, against stand-in pactl,
    system_profiler, claude and codex programs in a scratch folder: never the real ones, never a real credential."""
    import json
    import stat
    import tempfile
    import harness
    import codex_harness

    def stand_in(folder, name, out, code=0):
        script = Path(folder) / name
        data = Path(folder) / f"{name}.out"
        data.write_text(out)
        script.write_text(f"#!/bin/sh\ncat '{data}'\nexit {code}\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

    saved_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="dk-") as folder:
        os.environ["PATH"] = f"{folder}:/usr/bin:/bin"
        try:
            linux = _Linux()

            def pactl(default, rows):
                script = Path(folder) / "pactl"
                (Path(folder) / "default").write_text(default + "\n")
                (Path(folder) / "rows").write_text(json.dumps(rows))
                script.write_text(f"#!/bin/sh\ncase \"$1\" in get-default-*) cat '{folder}/default' ;; "
                                  f"*) cat '{folder}/rows' ;; esac\n")
                script.chmod(0o755)
                return linux.audio_device("input")
            mic = {"name": "alsa_input.mic", "description": "USB Mic", "properties": {"device.api": "alsa",
                                                                                        "device.class": "sound"}}
            monitor = {"name": "out.monitor", "description": "Monitor of Speakers",
                       "properties": {"device.api": "alsa", "device.class": "monitor"}}
            fil = {"name": "mono_mic", "description": "Mono Mic", "properties": {"device.class": "filter"}}
            assert pactl("alsa_input.mic", [mic, monitor]) == {"name": "USB Mic", "kind": "real", "muted": False}
            assert pactl("alsa_input.mic", [{**mic, "mute": True}])["muted"] is True
            assert pactl("out.monitor", [mic, monitor]) == {"name": "Monitor of Speakers", "kind": "virtual"}
            assert pactl("mono_mic", [fil, mic])["kind"] == "unknown"  # A filter in front of a real microphone.
            assert pactl("", [monitor]) == {"name": None, "kind": "none"}
            effects = {"name": "denoise", "description": "Noise Canceling Source",
                       "properties": {"factory.name": "support.null-audio-sink", "media.class": "Audio/Source/Virtual"}}
            assert pactl("denoise", [effects, mic])["kind"] == "unknown"  # In front of a real microphone: say nothing.
            dummy = {"name": "auto_null", "description": "Dummy Output", "properties": {"factory.name": "support.null-audio-sink"}}
            assert pactl("auto_null", [dummy]) == {"name": "Dummy Output", "kind": "virtual"}
            mac = _Mac()
            blackhole = {"_name": "BlackHole 2ch", "coreaudio_default_audio_input_device": "spaudio_yes",
                         "coreaudio_default_audio_output_device": "spaudio_yes", "coreaudio_device_input": 2,
                         "coreaudio_device_output": 2, "coreaudio_device_transport": "coreaudio_device_type_virtual"}
            speakers = {"_name": "Mac mini Speakers", "coreaudio_device_output": 2,
                        "coreaudio_device_transport": "coreaudio_device_type_builtin"}
            stand_in(folder, "system_profiler", json.dumps({"SPAudioDataType": [{"_items": [blackhole, speakers]}]}))
            assert mac.audio_device("input") == {"name": "BlackHole 2ch", "kind": "virtual"}
            assert mac.audio_device("output") == {"name": "BlackHole 2ch", "kind": "virtual"}
            builtin = {**blackhole, "_name": "MacBook Pro Microphone",
                       "coreaudio_device_transport": "coreaudio_device_type_builtin"}
            stand_in(folder, "system_profiler", json.dumps({"SPAudioDataType": [{"_items": [builtin]}]}))
            assert mac.audio_device("input") == {"name": "MacBook Pro Microphone", "kind": "real"}
            assert "BlackHole 2ch, which is not a microphone" in input_problem({"name": "BlackHole 2ch", "kind": "virtual"})
            assert "no microphone" in input_problem({"name": None, "kind": "none"})
            assert input_problem({"name": "USB Mic", "kind": "real"}) is None
            assert input_problem({"name": None, "kind": "unknown"}) is None
            assert silence_sentence({"name": "USB Mic", "kind": "real"}).startswith("I heard only silence from USB Mic.")
            claude, codex = harness.Claude(), codex_harness.Codex()
            assert claude.signin_status() == ("unknown", None) and codex.signin_status() == ("unknown", None)  # None here.
            stand_in(folder, "claude", json.dumps({"loggedIn": False}), 1)
            state, said = claude.signin_status()
            assert state == "out" and said == (f"Claude Code is not signed in. Run {folder}/claude auth login in a "
                                               "terminal on this computer, then ask again."), said
            stand_in(folder, "claude", json.dumps({"loggedIn": True, "loginExpiresAt": "2001-01-01T00:00:00.000Z"}))
            assert claude.signin_status()[0] == "out" and "sign-in has ended" in claude.signin_problem()
            stand_in(folder, "claude", json.dumps({"loggedIn": True, "loginExpiresAt": "2999-01-01T00:00:00.000Z"}))
            assert claude.signin_status() == ("in", None) and claude.signin_problem() is None
            stand_in(folder, "claude", "error: unknown command 'status'", 1)  # An older Claude Code: no answer.
            assert claude.signin_status() == ("unknown", None)
            stand_in(folder, "codex", "Logged in using ChatGPT")
            assert codex.signin_status() == ("in", None)
            stand_in(folder, "codex", "Not logged in", 1)
            assert codex.signin_status()[0] == "out" and f"{folder}/codex login" in codex.signin_problem()
            stand_in(folder, "codex", "config error", 1)
            assert codex.signin_status() == ("unknown", None)
        finally:
            os.environ["PATH"] = saved_path


if __name__ == "__main__":
    _check()
