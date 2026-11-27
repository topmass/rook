"""Rook's daily update check. Once a day, at or after 10:00 local time, one git ls-remote asks Rook's public
repository for its newest commit. When that commit is new, the owner hears once that a newer Rook is on GitHub.

The version is the commit: the checkout's HEAD against the public main branch. It needs no API and no token.
The check runs only on a checkout that tracks production: its origin is the public repository and its HEAD is on main
or on a commit of origin/main. A private, dev-branch or hand-made checkout never checks. update_check off stops it. A
failure is silent, and the next day tries again. A newer version also leaves one mailbox reminder, which closes once
the owner has heard it or the checkout has moved. Standard library only.

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


def developer(root=ROOT):
    """Why this checkout is a developer one, or "" when it tracks production: origin is the public repository, and
    HEAD is the main branch or, detached, a commit that origin/main holds. A dev branch, or a commit only on dev, is not."""
    if not is_public(root):
        return "this checkout's origin is not Rook's public repository"
    branch = git(root, "symbolic-ref", "-q", "--short", "HEAD")
    if branch:
        return "" if branch == "main" else f"this checkout runs the {branch} branch, not main"
    if git(root, "merge-base", "--is-ancestor", "HEAD", "refs/remotes/origin/main") is None:
        return "this checkout's commit is not on Rook's main branch"
    return ""


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
                           f"sentence, and that you can install it when {settings.token('he asks', 'they ask')}. Run "
                           f"relay.py update --install only when {OWNER} asks, as the settings skill says.")


def file_item(old, new, path=None):
    """One mailbox reminder for this version, or None when the mailbox is unavailable. Its run names both versions."""
    import mailbox  # Here, so relay.py loads the mailbox only for this.
    try:
        return mailbox.observe("reminder", f"A newer Rook is ready: {new[:7]}, and this one is {old[:7]}.",
                               detail=settings.render(f"{settings.OWNER_START_TOKEN} can ask Rook to install it."),
                               run=f"update:{old}:{new}", path=path)
    except (mailbox.MailboxError, OSError):
        return None


def close_moved(root=ROOT, path=None):
    """Close each open update reminder whose old version is no longer the checkout's HEAD: the owner has updated."""
    import mailbox
    head = installed(root)
    try:
        for item in mailbox.items(("open", "snoozed"), path=path):
            if head and (item["run"] or "").startswith("update:") and item["run"].split(":")[1] != head:
                mailbox.done(item["id"], "updated", path=path)
    except (mailbox.MailboxError, OSError):
        pass


def look(saved, now=None, root=ROOT, path=None, mail=None):
    """One look: (notice text, mailbox item id or None) when a newer Rook than any told before is on GitHub, else None.
    It reaches the network at most once a day, at or after CHECK_HOUR, and never when the setting is off or the
    checkout does not track production. Each look first closes the reminders of a version the checkout has left."""
    now = now or datetime.now()
    path = path or state_file()
    close_moved(root, mail)
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
    if developer(root):
        return None
    old, new = installed(root), latest()
    if not old or not new or new == old or new == state.get("told"):
        return None
    state["told"] = new
    path.write_text(json.dumps(state))
    item = file_item(old, new, mail)
    return notice(old, new), item and item["id"]


def check():
    """Stand-in public repository and checkout in a scratch folder; GitHub is never reached."""
    global PUBLIC
    import mailbox
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
        PUBLIC, calls, path, mail = str(bare), [], base / "state.json", base / "mailbox.db"
        real_latest = latest

        def counted():
            calls.append(1)
            return real_latest()
        globals()["latest"] = counted
        at = lambda day, hour: datetime(2026, 11, day, hour, 5)  # noqa: E731
        see = lambda saved, when: look(saved, when, live, path, mail)  # noqa: E731
        updates = lambda: [i for i in mailbox.items(("open",), path=mail) if (i["run"] or "").startswith("update:")]  # noqa: E731
        on = {}
        assert same_repo("git@github.com:topmass/rook.git", "https://github.com/topmass/rook.git")
        assert same_repo("https://github.com/topmass/rook/", "https://github.com/topmass/rook.git")
        assert not same_repo("https://github.com/topmass/rook-private.git", "https://github.com/topmass/rook.git")
        # Up to date: before 10:00 nothing runs; at 10:00 one call, silent; a later look that day makes no call.
        assert see(on, at(1, 9)) is None and calls == []
        assert see(on, at(1, 10)) is None and len(calls) == 1
        assert see(on, at(1, 23)) is None and len(calls) == 1, "checked twice in a day"
        # A newer version: told once, then never again for it, even on later days. It leaves one mailbox reminder.
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "two")
        run("-C", str(work), "push", "-q", str(bare), "main")
        new, old = real_latest(), installed(live)
        told, item = see(on, at(2, 10))
        assert new[:7] in told and "relay.py update --install" in told and "only when" in told, told
        assert see(on, at(2, 18)) is None, "told twice in a day"
        assert see(on, at(3, 10)) is None, "told twice for one version"
        assert [i["id"] for i in updates()] == [item], updates()
        only = updates()[0]
        assert only["kind"] == "reminder" and new[:7] in only["summary"] and old[:7] in only["summary"], only
        assert "ask Rook to install it" in only["detail"], only
        # Heard to its end, the status turn closes the reminder, as rook.py's carry(told=...) does.
        assert mailbox.close_delivered([item], path=mail) == 1 and updates() == []
        # Rook off at 10:00 catches up at its first look after, once.
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "three")
        run("-C", str(work), "push", "-q", str(bare), "main")
        assert see(on, at(4, 9)) is None
        assert see(on, at(4, 15)), "missed 10:00 was not caught up"
        assert see(on, at(4, 16)) is None
        # Not heard yet, but the owner updated: the next look, even before 10:00, closes the reminder.
        assert len(updates()) == 1
        run("-C", str(live), "fetch", "-q", "origin")
        run("-C", str(live), "checkout", "-q", "--detach", "origin/main")
        assert developer(live) == "", "a detached commit of origin/main counts as production"
        assert see(on, at(5, 8)) is None and updates() == [], updates()
        # Off, or a private origin: no network call at all.
        before = len(calls)
        assert see({"update_check": "off"}, at(5, 12)) is None and len(calls) == before
        run("-C", str(live), "remote", "set-url", "origin", "https://github.com/topmass/rook-private.git")
        assert developer(live).startswith("this checkout's origin is not")
        assert see(on, at(6, 12)) is None and len(calls) == before, "a private origin reached the network"
        run("-C", str(live), "remote", "set-url", "origin", str(bare))
        # A dev branch, or a detached commit only on dev, is a developer checkout: no network call, no reminder.
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "newer main")
        run("-C", str(work), "push", "-q", str(bare), "main")
        run("-C", str(live), "checkout", "-q", "-b", "dev")
        assert developer(live) == "this checkout runs the dev branch, not main", developer(live)
        path.write_text(json.dumps({"checked": "2026-11-05"}))
        assert see(on, at(6, 13)) is None and len(calls) == before, "a dev branch looked"
        run("-C", str(live), "commit", "-q", "--allow-empty", "-m", "dev only")
        run("-C", str(live), "checkout", "-q", "--detach", "dev")
        assert developer(live) == "this checkout's commit is not on Rook's main branch", developer(live)
        path.write_text(json.dumps({"checked": "2026-11-06"}))
        assert see(on, at(7, 10)) is None and len(calls) == before and updates() == [], "a dev checkout looked"
        run("-C", str(live), "checkout", "-q", "--detach", "origin/main")
        # A failure is silent, and tomorrow tries again.
        PUBLIC = str(base / "missing.git")
        run("-C", str(live), "remote", "set-url", "origin", PUBLIC)
        assert see(on, at(8, 10)) is None
        assert json.loads(path.read_text())["checked"] == "2026-11-08"
        # An unreadable state file counts as no check yet.
        path.write_text("[")
        PUBLIC = str(bare)
        run("-C", str(live), "remote", "set-url", "origin", PUBLIC)
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "four")
        run("-C", str(work), "push", "-q", str(bare), "main")
        assert see(on, at(9, 10)), "a broken state file stopped the check"
        check_install(base / "install", env)
    print("update_check: all checks passed.")


def check_install(base, env):
    """relay.py update --install in a scratch copy of this code, with a stand-in public repository, a stand-in Rook
    that answers the restart grant, and stand-in systemctl and launchctl that only log. Nothing real is reached."""
    import shutil
    import socket
    import threading
    import time
    run = lambda *a: subprocess.run(["git", *a], check=True, capture_output=True, env=env)  # noqa: E731
    work, bare, live, xdg, guard = base / "work", base / "public.git", base / "live", base / "xdg", base / "guard"
    for name in ("desktop", "prompts", "skills", "install", "plugins"):
        if (ROOT / name).is_dir():
            shutil.copytree(ROOT / name, work / name, ignore=shutil.ignore_patterns("__pycache__"))
    run("init", "-q", "-b", "main", str(work))
    run("-C", str(work), "add", "-A")
    run("-C", str(work), "commit", "-q", "-m", "one")
    run("clone", "-q", "--bare", str(work), str(bare))
    run("clone", "-q", str(bare), str(live))
    (work / "NEWS").write_text("two\n")
    run("-C", str(work), "add", "NEWS")
    run("-C", str(work), "commit", "-q", "-m", "two")
    run("-C", str(work), "push", "-q", str(bare), "main")
    old, new = installed(live), git(work, "rev-parse", "HEAD")
    for folder in ("state", "data/rook", "config", "cache", "run", "home"):
        (xdg / folder).mkdir(parents=True)
    (xdg / "run").chmod(0o700)
    (xdg / "data/rook/install-manifest.json").write_text(json.dumps(
        {"entries": [{"created": True, "path": os.path.realpath(live)}]}))
    guard.mkdir()
    managed = base / "service.log"
    for tool in ("systemctl", "launchctl"):
        (guard / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> "{managed}"\n')
        (guard / tool).chmod(0o755)
    relay_env = {k: v for k, v in env.items() if k not in ("T3CODE_THREAD_ID", "ROOK_AGENT")}
    relay_env.update(XDG_STATE_HOME=str(xdg / "state"), XDG_DATA_HOME=str(xdg / "data"), HOME=str(xdg / "home"),
                     XDG_CONFIG_HOME=str(xdg / "config"), XDG_CACHE_HOME=str(xdg / "cache"),
                     XDG_RUNTIME_DIR=str(xdg / "run"), PATH=f"{guard}:{env['PATH']}", SYSTEMCTL=str(guard / "systemctl"),
                     ROOK_PUBLIC_SOURCE=str(bare), GIT_TERMINAL_PROMPT="0")
    agent = {**relay_env, "ROOK_AGENT": "1"}
    relay = lambda *a, e=agent: subprocess.run([sys.executable, str(live / "desktop/relay.py"), *a],  # noqa: E731
                                               capture_output=True, text=True, env=e, stdin=subprocess.DEVNULL, timeout=60)
    # get says why the daily check is off on a dev branch. It runs before the stand-in Rook, which answers no get.
    run("-C", str(live), "checkout", "-q", "-b", "dev")
    shown = relay("get", "update_check", e=relay_env)
    assert "off here, since this checkout runs the dev branch, not main" in shown.stdout, shown.stdout + shown.stderr
    run("-C", str(live), "checkout", "-q", "main")
    run("-C", str(live), "branch", "-q", "-d", "dev")
    # The stand-in Rook: the first restart ask is busy with a turn, the next is granted.
    asks, sock = [], socket.socket(socket.AF_UNIX)
    sock.bind(str(xdg / "run/rook.sock"))
    sock.listen()

    def serve():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            with conn:
                data = b""
                while chunk := conn.recv(65536):
                    data += chunk
                head, _, body = data.decode().partition("\n")
                asks.append((head, json.loads(body or "{}")))
                answer = ({"ok": True, "granted": False, "busy": ["turn"], "waiting": True} if len(asks) == 1 else
                          {"ok": True, "granted": True, "id": asks[-1][1].get("id"), "expires_in": 5}
                          if head.endswith("restart ask") else {"ok": True, "cancelled": False})
                conn.sendall(json.dumps(answer).encode())
    threading.Thread(target=serve, daemon=True).start()
    untouched = lambda: installed(live) == old and not managed.exists() and asks == []  # noqa: E731
    try:
        # Rook's agent may not restart Rook, nor run the plain update.
        for args in (["restart"], ["update"], ["update", "main"], ["update", "--install", "main"]):
            done = relay(*args)
            assert done.returncode and untouched(), (args, done.stdout, done.stderr)
        # A developer checkout: the dev branch, then a private origin. Both refuse and say to use git.
        run("-C", str(live), "checkout", "-q", "-b", "dev")
        done = relay("update", "--install")
        assert done.returncode and "developer checkout" in done.stderr and "git" in done.stderr, done.stderr
        assert untouched()
        run("-C", str(live), "checkout", "-q", "main")
        done = relay("update", "--install", e={**agent, "ROOK_PUBLIC_SOURCE": "https://github.com/topmass/rook.git"})
        assert done.returncode and "origin is not Rook's public repository" in done.stderr and untouched(), done.stderr
        # A failed update never restarts, and says why in one sentence.
        bare.rename(base / "away.git")
        done = relay("update", "--install")
        (base / "away.git").rename(bare)
        assert done.returncode and done.stderr.strip().startswith("Rook could not fetch its source.") and untouched(), \
            done.stderr
        # The update: the checkout moves, then one restart waits for the grant, and the restart note names the version.
        done = relay("update", "--install")
        assert done.returncode == 0 and f"to {new[:7]}" in done.stdout and "quiet moment" in done.stdout, \
            done.stdout + done.stderr
        assert installed(live) == new
        end = time.monotonic() + 20
        while not managed.exists() and time.monotonic() < end:
            time.sleep(0.1)
        time.sleep(0.5)
        assert [a[0] for a in asks] == ["rook-settings:restart ask"] * 2, asks
        assert asks[0][1]["who"] == "rook" and new[:7] in asks[0][1]["reason"], asks
        if desk.IS_MAC:
            assert managed.read_text().split("\n")[:1] == [f"launchctl kickstart -k gui/{os.getuid()}/{desk.LAUNCHD_LABEL}"]
        else:
            assert managed.read_text() == "systemctl --user restart rook.service\n", managed.read_text()
        note = (xdg / "run/rook-restart-note").read_text()
        assert f"to {new[:7]}" in note and "name" in note, note
        # Once the public repository has a dev branch, a plain update from a detached install still lands on main.
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "three")
        run("-C", str(work), "checkout", "-q", "-b", "dev")
        run("-C", str(work), "commit", "-q", "--allow-empty", "-m", "dev only")
        run("-C", str(work), "push", "-q", str(bare), "main", "dev")
        main = git(work, "rev-parse", "main")
        done = relay("update", e=relay_env)
        assert done.returncode == 0 and installed(live) == main, (done.stdout, done.stderr, git(live, "log", "-1", "--format=%s"))
    finally:
        sock.close()

if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        check()
    else:
        sys.exit("Usage: update_check.py --check")
