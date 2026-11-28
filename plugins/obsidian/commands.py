"""Append dictated Markdown to today's note in the configured vault."""

from contextlib import ExitStack
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import stat
import sys


MAX_BYTES = 16 * 1024
DEFAULT_FOLDER = "rook"
HELP = """relay.py obsidian-note [TEXT|-]
                            Append Markdown to today's note in Rook's configured Obsidian vault."""


def append_daily_note(vault, text, folder=DEFAULT_FOLDER):
    if len(text.encode()) > MAX_BYTES:
        raise ValueError("An Obsidian note can be at most 16 KiB.")
    if not text.strip() or "\0" in text:
        raise ValueError("Give nonempty Markdown text without NUL characters.")
    entry = (text.rstrip("\r\n") + "\n").encode()
    if not vault:
        raise ValueError("Set the vault in obsidian.json or export ROOK_OBSIDIAN_VAULT first.")
    vault = Path(vault)
    if not vault.is_absolute():
        raise ValueError("ROOK_OBSIDIAN_VAULT must be an absolute path to a vault.")
    if (not folder or folder.startswith(".") or folder.casefold() == "daily"
            or folder != folder.strip() or any(char in "/\\" or ord(char) < 32 for char in folder)):
        raise ValueError("ROOK_OBSIDIAN_FOLDER must name a single visible vault folder other than daily.")

    filename = f"{date.today().isoformat()}.md"
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    # Open below directory descriptors so a symlink at the folder or note cannot redirect the write.
    with ExitStack() as opened:
        root = os.open(vault, directory_flags)
        opened.callback(os.close, root)
        try:
            os.mkdir(folder, 0o700, dir_fd=root)
        except FileExistsError:
            pass
        destination = os.open(folder, directory_flags, dir_fd=root)
        opened.callback(os.close, destination)
        try:
            daily = os.stat("daily", dir_fd=root, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if os.path.samestat(os.fstat(destination), daily):
                raise ValueError("Rook's Obsidian folder cannot be the vault's daily folder.")
        note = os.open(filename, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                       0o600, dir_fd=destination)
        opened.callback(os.close, note)
        info = os.fstat(note)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Today's daily note must be a regular file with no other links.")
        fcntl.flock(note, fcntl.LOCK_EX)
        if os.fstat(note).st_size:
            entry = b"\n\n" + entry
        remaining = memoryview(entry)
        while remaining:
            written = os.write(note, remaining)
            if not written:
                raise OSError("The daily note write made no progress.")
            remaining = remaining[written:]
    return f"{folder}/{filename}"


def note_command(args):
    import desk
    import plugin_loader

    if os.environ.get("ROOK_AGENT") and not any(
            plugin["id"] == "obsidian" for plugin in plugin_loader.activation()["active_plugins"]):
        sys.exit("Enable the Obsidian plugin to save dictated notes.")
    if len(args) > 1:
        sys.exit("Usage: relay.py obsidian-note [TEXT|-]")
    text = args[0] if args and args[0] != "-" else sys.stdin.read(MAX_BYTES + 1)
    config = desk.config_dir() / "rook/obsidian.json"
    try:
        try:
            saved = json.loads(config.read_text())
        except FileNotFoundError:
            saved = {}
        if not isinstance(saved, dict) or any(key in saved and not isinstance(saved[key], str)
                                             for key in ("vault", "folder")):
            raise ValueError(f"{config} must contain a JSON object with string vault and folder values.")
        vault = os.environ.get("ROOK_OBSIDIAN_VAULT") or saved.get("vault")
        folder = os.environ.get("ROOK_OBSIDIAN_FOLDER") or saved.get("folder", DEFAULT_FOLDER)
        path = append_daily_note(vault, text, folder)
    except (OSError, ValueError) as error:
        sys.exit(f"Could not save the Obsidian note: {error}")
    print(f"Saved to {path}.")


COMMANDS = {"obsidian-note": note_command}
