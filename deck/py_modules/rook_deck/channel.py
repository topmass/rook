"""Rook's channel into the running game, vendored from Rook's wow/channel.py so the Deck writes its notes itself.

This is Rook's writer with only its command line, its self-check and its ROOK_WOW_ADDONS default taken out: the
plugin always passes the AddOns folder. The slots, the 300-character LIMIT, the numbering, the lock on the bell folder
and the whole-file writes are Rook's, unchanged; keep them in step with wow/channel.py and Channel.lua. The text that
follows is Rook's own module note.

Rook's channel into the running game: short notes that WoW Friend shows on screen, with no reload.

An add-on cannot read files, but the game reads a load-on-demand add-on's files when it loads it, and each
loads once per UI session. So the channel has SLOTS slot add-ons, WoWFriend_R01 to WoWFriend_R50, each with
one Inbox.lua. Note n goes into slot ((n - 1) % SLOTS) + 1. Each slot has a bell, a silent WAV file in
WoWFriend/Bells. A blank bell plays nothing, and a full one plays. The add-on plays the bell of the next
note every second, and a bell that plays makes it load that slot. The game finds only files that
existed when it started, so `install` makes every file blank first, and the game then needs a full restart.

The slot and bell layout follows t3wow (github.com/MatiasCiccone/t3wow, addon/T3WoW/Link.lua) and t3code-wow
(github.com/ryanrhughes/t3code-wow, Core/Transport.lua). The bell format, a 441,044-byte silent 22,050 Hz mono WAV, is
t3code-wow's. Both are under this MIT license:

Copyright (c) 2026 Matias Ciccone
Copyright (c) 2026 Ryan Hughes

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of
the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import fcntl
import io
import os
from pathlib import Path
import re
import time
import wave

SLOTS = 50  # Keep in step with SLOTS in Channel.lua.
LIMIT = 300  # The most characters one note may hold. Keep in step with LIMIT in Channel.lua.
INTERFACE = "16001"  # The same as WoWFriend.toc.
TOC = (f"## Interface: {INTERFACE}\n## Title: WoWFriend note slot\n"
       "## Notes: Carries Rook's notes into WoWFriend. Leave it enabled.\n"
       "## LoadOnDemand: 1\n## Group: WoWFriend\n\nInbox.lua\n")
BLANK = "-- Rook writes its notes into this file. WoWFriend reads it as data.\n"
NUMBER = re.compile(rb"^WoWFriendChannel_Inbox = \{n=(\d+),")


def slot_dir(addons, k):
    return addons / f"WoWFriend_R{k:02d}"


def bell(addons, k):
    return addons / "WoWFriend/Bells" / f"{k:02d}.wav"


def silence():
    """A full bell: 10 s of silence, over the size the game caches, so it reads the file anew each play."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(bytes(441000))
    return out.getvalue()


def lua_string(text):
    """A Lua string literal that can only ever be data: every byte but letters, digits, space, and plain
    punctuation is a decimal escape, so the text cannot end the string or start code."""
    safe = set(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,:;!?'()+-*/=%&#@$_<>~^")
    return '"' + "".join(chr(b) if b in safe else f"\\{b:03d}" for b in text.encode()) + '"'


def write_whole(path, data):
    """Write a file whole under a fixed temporary name in the same folder, then rename it into place."""
    temp = path.with_name(path.stem + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


def install(addons):
    """Make the files that do not exist yet. It never changes a file that exists. Returns how many it made."""
    if not (addons / "WoWFriend/WoWFriend.toc").is_file():
        raise SystemExit(f"WoWFriend is not installed in {addons}. Install the add-on first.")
    made = 0
    files = [(bell(addons, k), b"") for k in range(1, SLOTS + 1)]
    files += [(addons / "WoWFriend/Bells/empty.wav", b""), (addons / "WoWFriend/Bells/full.wav", silence())]
    for k in range(1, SLOTS + 1):
        # The Inbox before the toc, so a failed install never leaves a toc that names a missing file.
        files += [(slot_dir(addons, k) / "Inbox.lua", BLANK.encode()),
                  (slot_dir(addons, k) / f"WoWFriend_R{k:02d}.toc", TOC.encode())]
    for path, data in files:
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            write_whole(path, data)
            made += 1
    return made


def send(text, addons, now=None):
    """Write note n into its slot and ring its bell. Returns n. Raises ValueError with a reason to give Rook."""
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("The note is empty.")
    if len(text) > LIMIT:
        raise ValueError(f"The note has {len(text)} characters. The most is {LIMIT}.")
    bells = addons / "WoWFriend/Bells"
    if not all(bell(addons, k).is_file() and (slot_dir(addons, k) / "Inbox.lua").is_file()
               for k in range(1, SLOTS + 1)):
        raise ValueError("The game's note slots are not installed. Run wow/channel.py install, "
                         "then restart WoW fully.")
    # One send at a time: a lock on the bell folder, so two sends never take the same number.
    folder = os.open(bells, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(folder, fcntl.LOCK_EX)
        last = 0
        for k in range(1, SLOTS + 1):
            with open(slot_dir(addons, k) / "Inbox.lua", "rb") as inbox:
                found = NUMBER.match(inbox.read(64))
            last = max(last, int(found[1]) if found else 0)
        n = last + 1
        k, after = (n - 1) % SLOTS + 1, n % SLOTS + 1
        stamp = int(time.time() if now is None else now)
        # Blank the next bell first: the add-on waits on it next, and it may still be full from 50 notes ago.
        write_whole(bell(addons, after), b"")
        write_whole(slot_dir(addons, k) / "Inbox.lua",
                    f"WoWFriendChannel_Inbox = {{n={n},t={stamp},text={lua_string(text)}}}\n".encode())
        write_whole(bell(addons, k), silence())
        return n
    finally:
        os.close(folder)
