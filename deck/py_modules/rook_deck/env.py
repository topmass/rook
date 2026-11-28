"""The desktop session the plugin works in: whose PipeWire, which X display, and a clean environment for helpers.

Decky starts the backend from its system service, so the process inherits the service's environment: no
XDG_RUNTIME_DIR for the Deck user, no DISPLAY, and, because Decky is a PyInstaller binary, an LD_LIBRARY_PATH that
points at Decky's bundled libraries. A system program such as gst-launch-1.0 or pw-record that starts with that
LD_LIBRARY_PATH can load Decky's old libcrypto or libstdc++ and abort. Steamcord found and fixed the same thing
(github.com/Necrosiak/Steamcord, defaults/vesktop.py `_user_env`): restore PyInstaller's saved LD_LIBRARY_PATH_ORIG,
or drop the variable. Decktation does the PipeWire half (github.com/silverfoxy/decktation,
backend/src/audio_runtime.py): pick /run/user/<uid> of the logged-in user, never /run/user/0.

When the backend runs as root, helpers that touch the user's session (PipeWire, the X display) run as the Deck user,
so they connect as that user and every file they write belongs to that user.
"""

from __future__ import annotations

import os
import pwd
from dataclasses import dataclass, field

STEAM_COMMS = ("steam", "steamwebhelper", "gamescope-wl", "gamescope")  # Processes that carry the session's env.


@dataclass
class Session:
    """The Deck user's session, as helpers need it."""

    user: str
    uid: int
    gid: int
    home: str
    runtime_dir: str
    display: str = ":0"
    xauthority: str | None = None
    groups: list[int] = field(default_factory=list)

    def child_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """The environment for a helper program: the service's, cleaned, with the user's session added."""
        env = dict(os.environ)
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is not None:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        env.update({"XDG_RUNTIME_DIR": self.runtime_dir, "PIPEWIRE_RUNTIME_DIR": self.runtime_dir,
                    "PULSE_SERVER": f"unix:{self.runtime_dir}/pulse/native", "DISPLAY": self.display,
                    "HOME": self.home, "USER": self.user, "LOGNAME": self.user,
                    "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.runtime_dir}/bus"})
        if self.xauthority:
            env["XAUTHORITY"] = self.xauthority
        if extra:
            env.update(extra)
        return env

    def child_kwargs(self) -> dict:
        """Popen arguments that run a helper as the Deck user when the backend is root. Empty otherwise."""
        if os.geteuid() != 0 or self.uid == 0:
            return {}
        return {"user": self.uid, "group": self.gid, "extra_groups": self.groups or [self.gid]}


def _environ_of(pid: str) -> dict[str, str]:
    try:
        with open(f"/proc/{pid}/environ", "rb") as source:
            raw = source.read()
    except OSError:
        return {}
    pairs = (item.split(b"=", 1) for item in raw.split(b"\0") if b"=" in item)
    return {key.decode(errors="replace"): value.decode(errors="replace") for key, value in pairs}


def find_display_env(uid: int, proc: str = "/proc") -> dict[str, str]:
    """DISPLAY and XAUTHORITY from a running Steam or gamescope process of this user, or {} when none runs."""
    try:
        pids = [name for name in os.listdir(proc) if name.isdigit()]
    except OSError:
        return {}
    for pid in pids:
        try:
            if os.stat(f"{proc}/{pid}").st_uid != uid:
                continue
            with open(f"{proc}/{pid}/comm") as source:
                comm = source.read().strip()
        except OSError:
            continue
        if comm in STEAM_COMMS:
            env = _environ_of(pid)
            if env.get("DISPLAY"):
                return {key: env[key] for key in ("DISPLAY", "XAUTHORITY") if env.get(key)}
    return {}


def steam_running(proc: str = "/proc") -> bool:
    """Whether a Steam client process runs. Reading the Deck controller's raw HID while Steam is away would take it
    from hid-steam (see controller.py), so the plugin only does that while Steam holds it anyway."""
    try:
        for pid in os.listdir(proc):
            if pid.isdigit():
                try:
                    with open(f"{proc}/{pid}/comm") as source:
                        if source.read().strip() == "steam":
                            return True
                except OSError:
                    continue
    except OSError:
        pass
    return False


def detect(user: str | None = None) -> Session:
    """The Deck user's session. Decky names its user in DECKY_USER; a run outside Decky uses the current user."""
    name = user or os.environ.get("DECKY_USER") or pwd.getpwuid(os.getuid()).pw_name
    try:
        entry = pwd.getpwnam(name)
    except KeyError:
        entry = pwd.getpwuid(os.getuid())
    try:
        groups = os.getgrouplist(entry.pw_name, entry.pw_gid)
    except OSError:
        groups = [entry.pw_gid]
    session = Session(user=entry.pw_name, uid=entry.pw_uid, gid=entry.pw_gid,
                      home=os.environ.get("DECKY_USER_HOME") or entry.pw_dir,
                      runtime_dir=f"/run/user/{entry.pw_uid}", groups=groups)
    found = find_display_env(entry.pw_uid)
    session.display = found.get("DISPLAY") or os.environ.get("DISPLAY") or ":0"
    session.xauthority = found.get("XAUTHORITY") or os.environ.get("XAUTHORITY")
    return session


def which(name: str, env: dict[str, str] | None = None) -> str | None:
    """The full path of a program on the helper PATH, or None. SteamOS keeps its programs in /usr/bin."""
    path = (env or os.environ).get("PATH") or "/usr/bin:/bin"
    for folder in [*path.split(":"), "/usr/bin", "/usr/local/bin"]:
        candidate = os.path.join(folder, name)
        if folder and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None
