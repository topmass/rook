#!/usr/bin/env python3
"""Types one approved chat line into World of Warcraft on the Steam Deck, through the Deck agent's POST /type.

    send.py reply TEXT          /r TEXT, to the last person who whispered the player
    send.py whisper NAME TEXT   /w NAME TEXT
    send.py party TEXT          /p TEXT
    send.py --check ...         prints the line it would type, and sends nothing

It reads ROOK_DECK_URL and ROOK_DECK_TOKEN from the environment. It sends only when the game has focus on the Deck,
retries once after a 409 (the Deck is still typing an earlier line), and never retries anything else, because a
line that timed out may already be typed. It refuses the same line again within REPEAT_SECONDS. It prints one line:
"sent: ...", "not sent: ...", or "would send: ...". Exit status 0 means sent (or checked), 1 not sent, 2 bad input.
Standard library only."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.error
import urllib.request

# The Deck types at most this many characters, each printable ASCII: a uinput keyboard has no keys for other
# letters, and the game's chat box holds 255.
MAX_CHARS = 255
CHANNELS = {"reply": "/r", "whisper": "/w", "party": "/p"}
REPEAT_SECONDS, RETRY_WAIT, TIMEOUT = 60, 2, 5
SENT = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()) / "rook-steamdeck-sent.json"


def printable(text):
    return all(" " <= c <= "~" for c in text)


def line_of(args):
    """(the line to type, None), or (None, why) when the arguments are wrong."""
    if not args or args[0] not in CHANNELS:
        return None, "the first word must be reply, whisper, or party"
    channel, rest = args[0], args[1:]
    if channel == "whisper":
        if len(rest) != 2:
            return None, "whisper takes a name and the text"
        name, text = rest
        if not name or not printable(name) or " " in name or name.startswith("/"):
            return None, (f"the name {name!r} cannot be typed on the Deck's keyboard; "
                          "use reply if this is the last person who whispered")
        prefix = f"/w {name} "
    else:
        if len(rest) != 1:
            return None, f"{channel} takes only the text"
        text, prefix = rest[0], CHANNELS[channel] + " "
    text = " ".join(text.split())
    if not text:
        return None, "the text is empty"
    if text.startswith("/"):
        return None, "the text must not start with /"
    if not printable(text):
        bad = "".join(sorted({c for c in text if not " " <= c <= "~"}))
        return None, f"the Deck's keyboard cannot type {bad!r}; use plain ASCII"
    line = prefix + text
    if len(line) > MAX_CHARS:
        return None, f"the line is {len(line)} characters, over {MAX_CHARS}"
    return line, None


def request(method, url, token, body=None):
    """(HTTP status, parsed JSON or None). Raises OSError on a network failure or a timeout."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        return status, json.loads(raw or b"null")
    except ValueError:
        return status, None


def recent(line):
    """Seconds since this same line was sent, or None."""
    try:
        sent = json.loads(SENT.read_text())
        key = hashlib.sha256(line.encode()).hexdigest()
        return time.time() - sent["at"] if sent.get("line") == key else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remember(line):
    try:
        SENT.write_text(json.dumps({"line": hashlib.sha256(line.encode()).hexdigest(), "at": time.time()}))
        SENT.chmod(0o600)
    except OSError:
        pass  # Only the repeat guard is lost.


def main(argv):
    check = argv[:1] == ["--check"]
    line, why = line_of(argv[1:] if check else argv)
    if not line:
        print(f"not sent: {why}.")
        return 2
    if check:
        print(f"would send: {line}")
        return 0
    base, token = os.environ.get("ROOK_DECK_URL", "").rstrip("/"), os.environ.get("ROOK_DECK_TOKEN", "")
    if not base or not token:
        print("not sent: ROOK_DECK_URL or ROOK_DECK_TOKEN is not set.")
        return 1
    ago = recent(line)
    if ago is not None and ago < REPEAT_SECONDS:
        print(f"not sent: the same line went {ago:.0f} s ago.")
        return 1
    try:
        status, window = request("GET", base + "/window", token)
        if status == 401:
            print("not sent: the Deck token is wrong.")
            return 1
        if status != 200 or not isinstance(window, dict):
            print(f"not sent: the Deck answered {status} to the focus check.")
            return 1
        if window.get("wow_focused") is not True:
            print("not sent: World of Warcraft does not have focus on the Deck.")
            return 1
        status, _ = request("POST", base + "/type", token, {"text": line, "approved": True})
        if status == 409:
            time.sleep(RETRY_WAIT)
            status, _ = request("POST", base + "/type", token, {"text": line, "approved": True})
    except OSError as error:
        reason = getattr(error, "reason", error)
        print(f"not sent: the Deck did not answer ({reason}). It may have typed part of it, so check before trying again.")
        return 1
    if 200 <= status < 300:
        remember(line)
        print(f"sent: {line}")
        return 0
    words = {400: "the Deck refused the line", 401: "the Deck token is wrong",
             409: "the Deck was still typing an earlier line, twice"}
    print(f"not sent: {words.get(status, f'the Deck answered {status}')}.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
