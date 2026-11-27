"""Rook's daily update check. Once a day, at or after 10:00 local time, one git ls-remote asks Rook's public
repository for its newest commit. When that commit is new, the owner hears once that a newer Rook is on GitHub.

The version is the commit: the checkout's HEAD against the public main branch. It needs no API and no token.
The check runs only on a checkout whose origin is the public repository, so a private or hand-made checkout never
checks. update_check off stops it. A failure is silent, and the next day tries again. Standard library only.

python3 update_check.py --check runs the self-check against a local stand-in repository, never GitHub."""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import desk
import settings

# Rook's public repository. ROOK_PUBLIC_SOURCE names a stand-in for tests, as in install/get.sh.
PUBLIC = os.environ.get("ROOK_PUBLIC_SOURCE") or "https://github.com/topmass/rook.git"
CHECK_HOUR = 10  # Local time. A Rook that was off then checks at its first look after.
FIRST_SECONDS = 60  # The first look waits this long, so a start never waits on it.
LOOK_SECONDS = 10 * 60  # Then a look every this long. A look before 10:00 or after today's check does nothing.
NET_SECONDS = 20
AGENT = "OpenAI File Downloader, XaiImageApiFetch/1.0"
ROOT = Path(__file__).resolve().parent.parent
OWNER = settings.OWNER_TOKEN


def state_file():
    return desk.state_dir() / "rook/update-check.json"


def git(root, *args, seconds=5):
    """Run git in root with no prompt. Its stdout, stripped, or None when it fails or runs past seconds."""
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=seconds,
                              stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def same_repo(url, other):
    """Whether two remote addresses name one repository: https, ssh and scp forms, with or without .git."""
    def plain(u):
        u = re.sub(r"^(git@github\.com:|ssh://git@github\.com/|git://github\.com/)", "https://github.com/", u.strip())
        return re.sub(r"(\.git)?/*$", "", u).lower()
    return bool(url) and plain(url) == plain(other)


def is_public(root=ROOT):
    """Whether this checkout's origin is Rook's public repository."""
    return same_repo(git(root, "remote", "get-url", "origin") or "", PUBLIC)


def installed(root=ROOT):
    return git(root, "rev-parse", "HEAD")


def latest():
    """The public main branch's commit, from one git ls-remote, or None."""
    out = git(ROOT, "-c", f"http.userAgent={AGENT}", "ls-remote", PUBLIC, "refs/heads/main", seconds=NET_SECONDS)
    sha = (out or "").split("\t")[0]
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def mode(saved):
    """(update_check, source): the saved on or off, else on."""
    if saved.get("update_check") in ("on", "off"):
        return saved["update_check"], "settings file"
    return "on", "default"


def notice(old, new):
    return settings.render(f"A newer Rook is on GitHub ({new[:7]}; this one is {old[:7]}). Tell {OWNER} in one short "
                           f"sentence, and that {settings.token('he updates', 'they update')} with relay.py update in a "
                           "terminal. Never run the update yourself.")


def look(saved, now=None, root=ROOT, path=None):
    """One look: the notice text when a newer Rook than any told before is on GitHub, else None. It reaches the
    network at most once a day, at or after CHECK_HOUR, and never when the setting is off or origin is not public."""
    now = now or datetime.now()
    path = path or state_file()
    if mode(saved)[0] != "on" or now.hour < CHECK_HOUR:
        return None
    try:
        state = json.loads(path.read_text())
        state = state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        state = {}
    today = now.date().isoformat()
    if state.get("checked") == today:
        return None
    state["checked"] = today  # Marked before the network, so a failure waits for tomorrow.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
    if not is_public(root):
        return None
    old, new = installed(root), latest()
    if not old or not new or new == old or new == state.get("told"):
        return None
    state["told"] = new
    path.write_text(json.dumps(state))
    return notice(old, new)


def check():
    """Stand-in public repository and checkout in a scratch folder; GitHub is never reached."""
    global PUBLIC
    with tempfile.TemporaryDirectory() as base:
        base = Path(base)
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        run = lambda *a: subprocess.run(["git", *a], check=True, capture_output=True, env=env)  # noqa: E731
        work, bare, live = base / "work", base / "public.git", base / "live"
        run("init", "-q", "-b", "main", str(work))
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "one")
        run("clone", "-q", "--bare", str(work), str(bare))
        run("clone", "-q", str(bare), str(live))
        PUBLIC, calls, path = str(bare), [], base / "state.json"
        real_latest = latest

        def counted():
            calls.append(1)
            return real_latest()
        globals()["latest"] = counted
        at = lambda day, hour: datetime(2026, 11, day, hour, 5)  # noqa: E731
        on = {}
        assert same_repo("git@github.com:topmass/rook.git", "https://github.com/topmass/rook.git")
        assert same_repo("https://github.com/topmass/rook/", "https://github.com/topmass/rook.git")
        assert not same_repo("https://github.com/topmass/rook-private.git", "https://github.com/topmass/rook.git")
        # Up to date: before 10:00 nothing runs; at 10:00 one call, silent; a later look that day makes no call.
        assert look(on, at(1, 9), live, path) is None and calls == []
        assert look(on, at(1, 10), live, path) is None and len(calls) == 1
        assert look(on, at(1, 23), live, path) is None and len(calls) == 1, "checked twice in a day"
        # A newer version: told once, then never again for it, even on later days.
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "two")
        run("-C", str(work), "push", "-q", str(bare), "main")
        new = real_latest()
        told = look(on, at(2, 10), live, path)
        assert told and new[:7] in told and "relay.py update" in told, told
        assert look(on, at(2, 18), live, path) is None, "told twice in a day"
        assert look(on, at(3, 10), live, path) is None, "told twice for one version"
        # Rook off at 10:00 catches up at its first look after, once.
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "three")
        run("-C", str(work), "push", "-q", str(bare), "main")
        assert look(on, at(4, 9), live, path) is None
        assert look(on, at(4, 15), live, path), "missed 10:00 was not caught up"
        assert look(on, at(4, 16), live, path) is None
        # Off, or a private origin: no network call at all.
        before = len(calls)
        assert look({"update_check": "off"}, at(5, 12), live, path) is None and len(calls) == before
        run("-C", str(live), "remote", "set-url", "origin", "https://github.com/topmass/rook-private.git")
        assert look(on, at(6, 12), live, path) is None and len(calls) == before, "a private origin reached the network"
        run("-C", str(live), "remote", "set-url", "origin", str(bare))
        # A failure is silent, and tomorrow tries again.
        PUBLIC = str(base / "missing.git")
        run("-C", str(live), "remote", "set-url", "origin", PUBLIC)
        assert look(on, at(7, 10), live, path) is None
        assert json.loads(path.read_text())["checked"] == "2026-11-07"
        # An unreadable state file counts as no check yet.
        path.write_text("[")
        PUBLIC = str(bare)
        run("-C", str(live), "remote", "set-url", "origin", PUBLIC)
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "four")
        run("-C", str(work), "push", "-q", str(bare), "main")
        assert look(on, at(8, 10), live, path), "a broken state file stopped the check"
    print("update_check: all checks passed.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        check()
    else:
        sys.exit("Usage: update_check.py --check")
