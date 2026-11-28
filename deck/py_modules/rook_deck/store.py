"""The plugin's small files in Decky's settings folder: settings.json, the outbox, and the Deck agent token.

Each file is written whole under a temporary name and renamed into place, with mode 0600: the device cookie and the
agent token are secrets, and a crash mid-write must never leave half a file.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

TOKEN_FILE = "deck_token"
SETTINGS_FILE = "settings.json"
OUTBOX_FILE = "outbox.json"


def write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    os.chmod(temp, 0o600)
    os.replace(temp, path)


class Store:
    """JSON settings with defaults, saved on every change."""

    DEFAULTS: dict[str, Any] = {
        "server_url": None,  # Rook's phone server, as the user typed it, such as http://192.168.1.20:47326.
        "cookie": None,  # The rook_device cookie value from pairing. It is the device's whole credential.
        "device": None,  # {"id", "name"} from the pairing answer: speech events name the device they are for.
        "hotkey": "L4",  # The talk chord: hold to talk, release to send.
        "addons_dir": None,  # The WoW AddOns folder on the Deck, found on first use or set by the user.
        "overlay_position": None,  # Where the overlay sits: top-right, top-left, middle-left, middle-right, bottom-center.
        "typed_aloud": False,  # Whether typed requests are answered aloud on the Deck too, as the phone's toggle.
    }

    def __init__(self, folder: str | os.PathLike):
        self.folder = Path(folder)
        self.path = self.folder / SETTINGS_FILE
        self.data = dict(self.DEFAULTS)
        try:
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in self.DEFAULTS})
        except (OSError, ValueError):
            pass

    def get(self, key: str) -> Any:
        return self.data.get(key, self.DEFAULTS.get(key))

    def set(self, **values: Any) -> None:
        self.data.update(values)
        write_private(self.path, json.dumps(self.data, indent=2).encode())

    def load_outbox(self) -> list[dict]:
        try:
            items = json.loads((self.folder / OUTBOX_FILE).read_text())
        except (OSError, ValueError):
            return []
        return [m for m in items if isinstance(m, dict) and isinstance(m.get("id"), str)] if isinstance(items, list) else []

    def save_outbox(self, items: list[dict]) -> None:
        write_private(self.folder / OUTBOX_FILE, json.dumps(items).encode())

    def deck_token(self) -> str:
        """The Deck agent API's bearer token: made once at first start, then kept."""
        path = self.folder / TOKEN_FILE
        try:
            token = path.read_text().strip()
            if len(token) >= 32:
                return token
        except OSError:
            pass
        token = secrets.token_urlsafe(32)
        write_private(path, token.encode())
        return token
