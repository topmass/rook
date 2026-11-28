"""Rook's reach into Herdr, the terminal workspace that runs coding agents, and into Pi's saved sessions.

relay.py's herdr and pi commands and the thread watcher use it. Standard library only. Rook adds no permission
layer: each agent keeps its own settings, and Rook never answers a blocked agent's question or approval.
A send is guarded. It goes only to an agent that is idle or done, after an intent record is written. A send whose
outcome is unknown is recorded and shown, and nothing ever sends it again.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import settings

OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.
OWNER_START = settings.OWNER_START_TOKEN  # The same, as the first word of a sentence.

READY = ("idle", "done")  # Herdr's states in which an agent takes a prompt.
SECONDS = 20  # One herdr call, local or over SSH, may take this long.
START_SECONDS = 45  # herdr agent start waits up to 30 seconds for the agent itself.
SHELL_START_SECONDS = 5  # A new pane can return before its shell reaches the prompt.
KEEP = 50  # Intent records kept, newest last.
# Herdr's error codes that prove a prompt was never written, and exit status 2, a syntax error.
NOT_SENT = {"agent_blocked", "agent_not_found", "agent_not_ready", "server_not_running", "not_installed"}
# Where Pi keeps its sessions, by Pi's own variables.
PI_SESSIONS = Path(os.environ.get("PI_CODING_AGENT_SESSION_DIR")
                   or Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent") / "sessions")


class Failed(Exception):
    """A herdr call failed. code is Herdr's error code, such as agent_not_found, or None."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def argv(machine, *args):
    """The herdr command for a saved Herdr machine, or for this machine when machine is None."""
    return ["herdr", *(["--machine", machine] if machine else []), *args]


def parse(returncode, stdout, stderr):
    """A herdr answer's result, from its JSON. Raise Failed with Herdr's code on an error."""
    for text in (stdout, stderr):
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            raise Failed(data["error"].get("message") or "Herdr gave an error.", data["error"].get("code"))
        if returncode == 0:
            return data.get("result", data) if isinstance(data, dict) else data
    lines = (stderr or stdout).strip().splitlines()
    raise Failed(lines[-1] if lines else f"herdr exited with {returncode}.", "usage" if returncode == 2 else None)


def call(machine, *args, timeout=SECONDS, raw=False):
    """Run one herdr command. Return its result, or its plain text with raw, as agent read prints."""
    try:
        done = subprocess.run(argv(machine, *args), capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Failed("Herdr is not installed.", "not_installed")
    except subprocess.TimeoutExpired:
        raise Failed(f"Herdr did not answer within {timeout} seconds.", "timeout")
    if raw and done.returncode == 0:
        return done.stdout
    return parse(done.returncode, done.stdout, done.stderr)


def target(info):
    """The name Rook uses for an agent: its Herdr name, else the pane that hosts it."""
    return info.get("name") or info["pane_id"]


def short_path(path):
    home = str(Path.home())
    return "~" + path[len(home):] if path and (path == home or path.startswith(home + "/")) else path or "?"


def agent_line(info, where):
    return " | ".join((target(info), info.get("agent") or "?", info.get("agent_status") or "unknown",
                       short_path(info.get("foreground_cwd") or info.get("cwd")), where))


SCREEN_LINES = 200  # Claude Code and Codex pad blank lines above their bottom box, so a read takes this many.
RULE = re.compile(r"[─━]{8,}")
# The bottom hint of a dialog that waits for a choice. Herdr may read such a dialog as idle.
DIALOG = re.compile(r"esc(?:ape)? to (?:cancel|dismiss)|enter to (?:confirm|continue|approve)|to choose\b|to select\b",
                    re.I)
TRUST = re.compile(r"one you trust|trust (this|the) (folder|files|contents|directory)", re.I)
APPROVAL = re.compile(r"would you like to run|do you want to (?:run|allow|proceed)|"
                      r"approval (?:required|requested|needed)|requires (?:your )?approval|permission (?:request|required)|"
                      r"approve (?:this|the) (?:command|tool|action)", re.I)


def dialog(tail):
    """"trust" when a screen's end waits at the agent's folder trust question, "dialog" at another dialog, else None."""
    lines = [line for line in (tail or "").splitlines() if line.strip()]
    if not DIALOG.search("\n".join(lines[-3:])):
        return None
    return "trust" if TRUST.search("\n".join(lines[-15:])) else "dialog"


def screen_tail(text, lines, blocked=False):
    """Clean the pane text, preserving the heading and command of a blocked approval."""
    kept = []
    for line in (text or "").splitlines():
        line = line.rstrip()
        if line or kept and kept[-1]:
            kept.append(line)
    while kept and not kept[-1]:
        kept.pop()
    if blocked:
        prompt = next((i for i in range(len(kept) - 1, max(-1, len(kept) - 61), -1)
                       if APPROVAL.search(kept[i])), None)
        if prompt is not None:
            head = "\n".join(kept[prompt:prompt + lines]).strip()
            return head[:settings.READBACK_LIMIT]
    elif not dialog("\n".join(kept[-15:])):
        # Claude Code's input box starts with ❯ under a rule, and Codex's with ›. The footer follows it.
        for at in range(len(kept) - 1, max(len(kept) - 8, 0) - 1, -1):
            mark = kept[at].lstrip()[:1]
            if mark == "›" or mark == "❯" and at and RULE.fullmatch(kept[at - 1].strip()):
                kept = kept[:at - (mark == "❯")]
                break
    tail = "\n".join(kept[-lines:]).strip()
    return tail if len(tail) <= settings.READBACK_LIMIT else "..." + tail[-settings.READBACK_LIMIT:]


def read_screen(machine, agent, lines, timeout=SECONDS, *, source=None, blocked=False):
    """Prefer the visible pane for a blocked agent and share one deadline across fallbacks."""
    preferred = source or ("visible" if blocked else "recent-unwrapped")
    deadline = time.monotonic() + timeout

    def read(view, preserve_prompt):
        count = max(lines, SCREEN_LINES) if preserve_prompt or view == "recent-unwrapped" else lines
        screen = call(machine, "agent", "read", agent, "--source", view, "--lines", str(count),
                      raw=True, timeout=max(0.1, deadline - time.monotonic()))
        return screen_tail(screen, lines, blocked=preserve_prompt)

    try:
        text = read(preferred, blocked)
    except Failed as error:
        if preferred != "recent-unwrapped" or error.code != "agent_not_idle" or time.monotonic() >= deadline:
            raise
        text = read("visible", True)
        blocked = True
    if not text and blocked and source is None and time.monotonic() < deadline:
        return read("detection", True)
    return text


def sends_path():
    """The intent record file, under the state folder as it is at the call, not at import."""
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "rook/herdr-sends.json"


# The intent record: one small JSON list. ponytail: no file lock; Rook sends one message at a time.
def records(path=None):
    try:
        data = json.loads(Path(sends_path() if path is None else path).read_text())
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def write_records(rows, path=None):
    path = Path(sends_path() if path is None else path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(rows[-KEEP:], out, indent=1)
    temp.replace(path)


def last_send(machine, agent, path=None):
    """The newest intent record for an agent, or None."""
    return next((r for r in reversed(records(path)) if r.get("machine") == machine and r.get("agent") == agent), None)


def send(machine, agent, text, path=None):
    """Prompt an agent once. Return (outcome, words): sent, refused, failed or unknown, and a sentence to say."""
    who = f"{agent}" + (f" on {machine}" if machine else "")
    try:
        info = call(machine, "agent", "get", agent)["agent"]
    except Failed as error:
        return "failed", f"Rook could not read {who}: {error}. Nothing was sent."
    state = info.get("agent_status") or "unknown"
    if state == "working":
        return "refused", f"{who} is working, so Rook did not send it. Try again when it is done."
    if state == "blocked":
        return "refused", (f"{who} is blocked at a question or approval, so Rook did not send it. "
                           + settings.render(f"{OWNER_START} answers it in Herdr."))
    if state not in READY:
        return "refused", f"Herdr cannot tell what {who} is doing, so Rook did not send it."
    try:
        held = dialog(read_screen(machine, agent, 15))
    except Failed:
        held = None  # Herdr itself refuses an agent it knows is blocked.
    if held:  # Herdr may read a dialog as idle, and a prompt typed into it would answer it.
        return "refused", (f"{who} " + ("asks whether its folder is trusted" if held == "trust" else
                                        "waits at a dialog in its window") + ", so Rook did not send it. "
                           + settings.render(f"{OWNER_START} answers it in Herdr. Then Rook can send it again."))
    key = os.urandom(8).hex()
    rows = records(path)
    # Of the text, only a hash, as Rook's record of T3 sends keeps. seq lets the watcher tell later news from old.
    rows.append({"key": key, "at": time.time(), "machine": machine, "agent": agent, "seq": info.get("state_change_seq"),
                 "digest": hashlib.sha256(text.strip().encode()).hexdigest(), "outcome": "sending"})
    write_records(rows, path)  # An intent that cannot be written stops the send here.
    # ponytail: the state can change between the get above and this prompt. Herdr itself refuses a blocked agent;
    # a prompt to an agent that just began working lands as its next input. That race is accepted.
    try:
        call(machine, "agent", "prompt", agent, text)
        outcome, result, words = "sent", None, f"Sent to {who}."
    except Failed as error:
        result = str(error)
        if error.code in NOT_SENT or error.code == "usage":
            outcome, words = "failed", f"Herdr refused the send to {who}: {error}. Nothing was sent."
        else:
            outcome, words = "unknown", (f"The send to {who} started, but its outcome is unknown: {error}. Check the "
                                         "agent in Herdr before anything is sent again. Rook will not resend it.")
    rows = records(path)
    for row in rows:
        if row.get("key") == key:
            row.update(outcome=outcome, result=result, settled=time.time())
    try:
        write_records(rows, path)
    except OSError:  # The row stays "sending". Rook's next start reports it as unknown and never resends it.
        words += " Rook could not record the outcome."
    return outcome, words


# Herdr's official installer, from its README (github.com/herdrdev/herdr). It checks the binary's SHA-256 against
# Herdr's release manifest and puts it in $HERDR_INSTALL_DIR, by default ~/.local/bin, for this user only.
INSTALLER = "https://herdr.dev/install.sh"
INSTALL_SECONDS = 90  # The whole install, under the 120 s shell limit.


def install(dry=False, fetch=None):
    """Install Herdr with its official installer, then check that the binary runs and is on Rook's PATH. Return one
    line, or raise Failed. fetch returns the installer's text; checks pass a stand-in, so no check runs the real one."""
    import shutil
    import urllib.request
    found = shutil.which("herdr")
    if found:
        return f"Herdr is already installed at {found}."
    binary = Path(os.environ.get("HERDR_INSTALL_DIR") or Path.home() / ".local/bin") / "herdr"
    if dry:
        return (f"Dry run: nothing changed. A real install runs Herdr's official installer from {INSTALLER}, which "
                f"checks the download's checksum and puts herdr at {binary}.")
    try:
        script = (fetch or (lambda: urllib.request.urlopen(INSTALLER, timeout=20).read()))()
        done = subprocess.run(["sh", "-s"], input=script, capture_output=True, timeout=INSTALL_SECONDS)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise Failed(f"Herdr's installer could not run: {error}")
    if done.returncode != 0:
        lines = re.sub(r"\x1b\[[0-9;]*m|✗", "", (done.stderr or done.stdout).decode(errors="replace")).split("\n")
        raise Failed("Herdr's installer stopped: " + (next((line.strip() for line in reversed(lines) if line.strip()), "")
                                                      or f"it exited with {done.returncode}"))
    try:
        version = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        version = None
    if not version or version.returncode != 0:
        raise Failed(f"Herdr's installer finished, but {binary} does not run")
    if shutil.which("herdr") != str(binary):
        raise Failed(f"Herdr is installed at {binary}, but {binary.parent} is not on Rook's PATH, so Rook cannot use it")
    return f"Installed {version.stdout.strip() or 'Herdr'} at {binary}."


def slug(text):
    return re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-_") or "agent"


def free_name(base, taken):
    """A Herdr agent name from base: [a-z][a-z0-9_-]{0,31}, not in taken."""
    base = slug(base)
    base = base if base[0].isalpha() else "a-" + base
    for n in range(1, 100):
        name = (base[:32] if n == 1 else f"{base[:28]}-{n}")
        if name not in taken:
            return name
    raise Failed("No free agent name.")


# Each agent's own effort flag, and the levels its CLI takes: claude --help, and Codex's model_reasoning_effort.
EFFORTS = {"claude": (["--effort", "{}"], ("low", "medium", "high", "xhigh", "max")),
           "codex": (["-c", "model_reasoning_effort={}"], ("low", "medium", "high", "xhigh", "max", "ultra"))}

CODEX_MODEL = r"[A-Za-z0-9][A-Za-z0-9._:/-]*"
CODEX_MODEL_CONFIRMATION = re.compile(
    rf"(?m)^\s*• Model changed to ({CODEX_MODEL})(?: ([a-z]+))? for this session only\.?[ \t]*$")


def configure_codex(machine, agent, model=None, effort=None):
    """Change one idle Codex session through its inline /model command and verify the transcript."""
    if model is None and effort is None:
        raise Failed("Give a model, a reasoning effort, or both.", "usage")
    if model is not None and not re.fullmatch(CODEX_MODEL, model):
        raise Failed("Give a Codex model ID without spaces or flags.", "usage")
    if effort is not None and effort not in ("none", "minimal", *EFFORTS["codex"][1]):
        raise Failed("Codex effort must be none, minimal, low, medium, high, xhigh, max, or ultra.", "usage")
    info = call(machine, "agent", "get", agent)["agent"]
    if info.get("agent") != "codex" or info.get("agent_status") not in READY:
        raise Failed("Choose an idle or done Codex pane.")
    pane = info["pane_id"]
    read = ("agent", "read", pane)
    transcript = (*read, "--source", "recent-unwrapped", "--lines", str(SCREEN_LINES))
    before = call(machine, *transcript, raw=True)
    visible = call(machine, *read, "--source", "visible", "--lines", "30", raw=True)
    composer = next((line.strip() for line in reversed(visible.splitlines()) if line.lstrip().startswith("›")), "")
    if composer != "› Ask Codex to do anything" or dialog(visible):
        raise Failed("Rook could not verify an empty Codex composer. Clear any draft or dialog in that pane first.")
    current = call(machine, "agent", "get", pane)["agent"]
    if (current.get("agent") != "codex" or current.get("agent_status") not in READY
            or current.get("state_change_seq") != info.get("state_change_seq")):
        raise Failed("The pane changed while Rook was checking it. Try again when it is idle.")
    command = " ".join(("/model", *([model] if model else []), *([f"--reasoning={effort}"] if effort else [])))
    try:
        call(machine, "agent", "prompt", pane, command)
    except Failed as error:
        if error.code in NOT_SENT or error.code == "usage":
            raise
        raise Failed(f"The outcome of the Codex settings command is unknown. Check /status in {pane}.") from error
    old = CODEX_MODEL_CONFIRMATION.findall(before)
    deadline = time.monotonic() + 4  # The local slash command needs no model turn.
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            after = call(machine, *transcript, raw=True, timeout=remaining)
        except Failed:
            break
        confirmations = CODEX_MODEL_CONFIRMATION.findall(after)
        for changed in reversed(confirmations):
            actual_model, actual_effort = changed
            if ((not model or model == actual_model) and (not effort or effort == actual_effort)
                    and confirmations.count(changed) > old.count(changed)):
                return f"Codex in {pane} is using {actual_model}" + (f" at {actual_effort} effort." if actual_effort else ".")
        time.sleep(min(0.15, remaining))
    raise Failed(f"Codex did not confirm the requested change. Check /status in {pane} before retrying.")


def start(machine, folder, kind, name=None, model=None, effort=None):
    """Start an agent of kind for folder without focus, so no pane the owner looks at is split: in a new tab of the
    workspace that already holds a pane in folder, else in a new workspace. model and effort go through the agent's
    own flags. Return the agent's info. On this machine a folder may be relative or start with ~. On a saved Herdr
    machine it is passed as given, and Herdr takes it only when it is absolute or starts with ~/."""
    if effort and effort not in EFFORTS.get(kind, ((), ()))[1]:
        levels = EFFORTS.get(kind, ((), ()))[1]
        raise Failed(f"{kind} takes the effort levels {', '.join(levels)}" if levels else
                     f"Rook cannot pass an effort to {kind}", "usage")
    if not machine:
        folder = os.path.abspath(os.path.expanduser(folder))
    home = next((p["workspace_id"] for p in call(machine, "pane", "list").get("panes") or ()
                 if folder in (p.get("cwd"), p.get("foreground_cwd")) and p.get("workspace_id")), None)
    made = (call(machine, "tab", "create", "--workspace", home, "--cwd", folder, "--label", kind, "--no-focus") if home
            else call(machine, "workspace", "create", "--cwd", folder, "--label", Path(folder).name or folder,
                      "--no-focus"))
    pane = made["root_pane"]
    taken = {a.get("name") for a in call(machine, "agent", "list").get("agents") or ()}
    name = name or free_name(f"{kind}-{Path(pane.get('cwd') or kind).name}", taken)
    extra = [*(["--model", model] if model else []),
             *([word.format(effort) for word in EFFORTS[kind][0]] if effort else [])]
    args = ("agent", "start", name, "--kind", kind, "--pane", pane["pane_id"],
            *(["--", *extra] if extra else []))
    shell_deadline = time.monotonic() + SHELL_START_SECONDS
    try:
        while True:
            try:
                return call(machine, *args, timeout=START_SECONDS)["agent"]
            except Failed as error:
                # Herdr rejected the launch before writing to the pane. Retry only that refusal on this new pane.
                remaining = shell_deadline - time.monotonic()
                if error.code != "agent_pane_busy" or remaining <= 0:
                    raise
                time.sleep(min(0.25, remaining))
    except Failed as error:
        if error.code != "agent_not_ready":  # A blocked start keeps its pane, so the owner can answer it in Herdr.
            try:
                call(machine, "pane", "close", pane["pane_id"])
            except Failed:
                pass
        error.name = name
        raise


def machines():
    """The labels of the enabled saved Herdr machines, or none when Herdr cannot list them."""
    try:
        saved = call(None, "machine", "list", "--json", timeout=5)
    except Failed:
        return []
    saved = saved.get("machines", []) if isinstance(saved, dict) else saved
    return [m.get("label") or m.get("id") for m in saved or () if isinstance(m, dict) and m.get("enabled", True)
            and (m.get("label") or m.get("id"))]


# Pi's sessions: append-only JSONL files, one folder per working folder. Read only.
def pi_text(content):
    """The plain text of a Pi message's content: its text parts, without thinking or tool calls."""
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text") or "" for part in content or () if isinstance(part, dict)
                     and part.get("type") == "text").strip()


def pi_session(path):
    """(id, name, cwd, messages) of one Pi session file. messages are (role, text) of user and assistant turns."""
    sid, name, cwd, messages = None, None, None, []
    with open(path, encoding="utf-8", errors="replace") as lines:
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            kind = entry.get("type") if isinstance(entry, dict) else None
            if kind == "session":
                sid, cwd = entry.get("id"), entry.get("cwd")
            elif kind == "session_info" and entry.get("name"):
                name = entry["name"]
            elif kind == "message" and isinstance(entry.get("message"), dict):
                message = entry["message"]
                if message.get("role") in ("user", "assistant") and (text := pi_text(message.get("content"))):
                    messages.append((message["role"], text))
    return sid or Path(path).stem.rpartition("_")[2], name, cwd, messages


def pi_files(root=PI_SESSIONS):
    """Pi's session files, newest first. A file deleted during the scan is left out."""
    found = []
    try:
        for path in [*Path(root).glob("*.jsonl"), *Path(root).glob("*/*.jsonl")]:
            try:
                found.append((path.stat().st_mtime, path))
            except OSError:
                pass
    except OSError:
        return []
    return [path for _, path in sorted(found, reverse=True)]
