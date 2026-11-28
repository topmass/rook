"""Rook's notes into WoW on the Deck: find the game's AddOns folder, and write one note through the vendored channel.

WoW runs on the Deck under Proton or Wine, so its folder sits inside a Windows prefix. Battle.net added to Steam as a
non-Steam game puts that prefix under Steam's compatdata/<id>/pfx; Lutris and Heroic keep theirs under ~/Games; Bottles
under ~/.local/share/bottles; an SD card has its own steamapps. The search walks those places for
"World of Warcraft/<flavour>/Interface/AddOns", where the flavour is _forever_ (the client WoWFriend targets) or, when
there is none, _classic_era_, _retail_ or _classic_. A folder that holds WoWFriend wins over one that does not.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path

from . import channel

FLAVOURS = ("_forever_", "_classic_era_", "_retail_", "_classic_")
WOW_DIRS = ("Program Files (x86)/World of Warcraft", "Program Files/World of Warcraft")
PREFIX_GLOBS = (
    ".local/share/Steam/steamapps/compatdata/*/pfx/drive_c",
    ".steam/steam/steamapps/compatdata/*/pfx/drive_c",
    ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata/*/pfx/drive_c",
    "Games/*/drive_c",  # Lutris: ~/Games/battlenet, ~/Games/world-of-warcraft
    "Games/Heroic/Prefixes/*/drive_c",
    "Games/Heroic/Prefixes/default/*/drive_c",
    ".local/share/bottles/bottles/*/drive_c",
    ".local/share/lutris/runners/wine/*/drive_c",
)
MEDIA_GLOBS = ("/run/media/*/steamapps/compatdata/*/pfx/drive_c", "/run/media/*/*/steamapps/compatdata/*/pfx/drive_c")


class NoteError(Exception):
    """A note that could not be written, with the HTTP status the Deck agent answers and a sentence for Rook."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def candidates(home: str, media_globs=MEDIA_GLOBS) -> list[Path]:
    found: list[Path] = []
    drives = [p for pattern in PREFIX_GLOBS for p in glob.glob(os.path.join(home, pattern))]
    drives += [p for pattern in media_globs for p in glob.glob(pattern)]
    for drive in sorted(set(drives)):
        for wow in WOW_DIRS:
            for flavour in FLAVOURS:
                addons = Path(drive) / wow / flavour / "Interface" / "AddOns"
                if addons.is_dir():
                    found.append(addons)
    return found


def rank(addons: Path) -> tuple:
    flavour = addons.parent.parent.name
    return (not has_wowfriend(addons), FLAVOURS.index(flavour) if flavour in FLAVOURS else len(FLAVOURS))


def detect(home: str, media_globs=MEDIA_GLOBS) -> Path | None:
    """The best AddOns folder on this Deck, or None."""
    found = candidates(home, media_globs)
    return min(found, key=rank) if found else None


def has_wowfriend(addons: Path) -> bool:
    return (addons / "WoWFriend" / "WoWFriend.toc").is_file()


def has_slots(addons: Path) -> bool:
    return all(channel.bell(addons, k).is_file() and (channel.slot_dir(addons, k) / "Inbox.lua").is_file()
               for k in range(1, channel.SLOTS + 1))


def describe(addons: Path | None) -> dict:
    if addons is None:
        return {"addons_dir": None, "wowfriend": False, "slots": False}
    return {"addons_dir": str(addons), "wowfriend": has_wowfriend(addons), "slots": has_slots(addons)}


def _give_back(addons: Path, n: int) -> None:
    """The backend may run as root: hand the files it just wrote to the folder's owner, so the game's user owns
    them as it owns the rest of its AddOns folder."""
    if os.geteuid() != 0:
        return
    owner = os.stat(addons)
    k, after = (n - 1) % channel.SLOTS + 1, n % channel.SLOTS + 1
    for path in (channel.bell(addons, after), channel.slot_dir(addons, k) / "Inbox.lua", channel.bell(addons, k)):
        try:
            os.chown(path, owner.st_uid, owner.st_gid)
        except OSError:
            pass


def send(text: object, addons: Path | None) -> int:
    """Write one note. Returns its number. Raises NoteError: 400 for the text, 404 with no WoWFriend, 503 with no
    note slots (they appear once the add-on zip is installed and WoW has restarted fully)."""
    if not isinstance(text, str):
        raise NoteError(400, "Send the note as text.")
    if addons is None or not has_wowfriend(addons):
        raise NoteError(404, "WoWFriend is not installed on this Deck, or its AddOns folder is not set.")
    if not has_slots(addons):
        raise NoteError(503, "WoWFriend's 50 note slots are missing on the Deck. Install the add-on zip with its "
                             "slot folders, then restart WoW fully.")
    try:
        n = channel.send(text, addons)
    except ValueError as error:
        raise NoteError(400, str(error)) from None
    _give_back(addons, n)
    return n
