"""Rook's own self-contained memory for installs without the owner's shared memory system.

When ~/.agents/hooks/memory-context.sh exists, Rook stays in shared mode and changes nothing.
When that hook is missing, Rook uses $XDG_DATA_HOME/rook/memory/ (default ~/.local/share/rook/memory/):
- relay.py remember appends one JSON line {ts, text} to incoming.jsonl with no model call.
- rook.py injects MEMORY.md, untidied incoming.jsonl lines, and the remember instruction into the prompt.
- relay.py dream backs up the folder (keeping the last 7) and runs Claude Code, Antigravity, or Codex confined to that folder.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

# Isolated mode (-I) omits this script's folder from sys.path; put it first so sibling imports resolve.
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import desk  # noqa: E402
import settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WRITER_PROMPT = ROOT / "prompts/memory-writer.md"
SHARED_SOURCE = ROOT / "memory/shared"
SHARED_FILES = (
    ("bin/dream", 0o755),
    ("bin/remember", 0o755),
    ("bin/memory-dir", 0o755),
    ("hooks/memory-context.sh", 0o755),
    ("prompts/analyzer.md", 0o644),
    ("prompts/writer.md", 0o644),
    ("prompts/remember.md", 0o644),
)
SHARED_UNITS = ("agent-dream.service", "agent-dream.timer")
GIT_IGNORE_LINE = ".agent-memory/"
MANIFEST_NAME = "rook-shared-manifest.json"
MAX_BACKUPS = 7
INDEX_LIMIT = 8000
INCOMING_LIMIT = 10000
TURNS_TAIL_BYTES = 128 * 1024
MAX_TURNS = 120
DREAM_TIMEOUT = 900

_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

DREAM_READ_FILE_TOOLS = frozenset({"view_file", "read_file"})
DREAM_SEARCH_TOOLS = frozenset({"list_dir", "find_by_name", "grep_search"})
DREAM_WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "write_to_file",
    "replace_file_content", "multi_replace_file_content", "sed_file",
})
DREAM_ALLOWED_TOOLS = DREAM_READ_FILE_TOOLS | DREAM_SEARCH_TOOLS | DREAM_WRITE_TOOLS | frozenset({"finish"})
_DREAM_PATH_KEYS = frozenset({
    "path", "targetfile", "target_file", "filepath", "file_path",
    "absolutepath", "absolute_path", "file", "files", "paths",
    "directory", "directorypath", "directory_path",
    "searchdirectory", "search_directory", "searchpath", "search_path",
    "destination", "dest", "targetpath", "target_path",
    "filename", "cwd", "root",
})
_DREAM_PATH_SUBSTRINGS = ("path", "file", "dir", "dest", "uri", "url", "root", "cwd")
_DREAM_CWD_KEYS = frozenset({"cwd", "workdir", "working_dir", "working_directory", "workingdirectory"})


def is_shared():
    """Return True when the owner's shared memory hook is present."""
    return (Path.home() / ".agents/hooks/memory-context.sh").is_file()


def memory_dir():
    """Return Rook's own memory folder under XDG_DATA_HOME."""
    return desk.data_dir() / "rook/memory"


def agents_dir():
    """Return the shared agent memory root (~/.agents)."""
    return Path.home() / ".agents"


def manifest_path():
    """Return the manifest path recording Rook's shared-memory install."""
    return agents_dir() / MANIFEST_NAME


def rook_workspace():
    """Return Rook's default agent working directory (matches rook.py --workspace)."""
    return Path.home() / "Work"


def _ensure_private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _write_private_atomic(path, content):
    _ensure_private_dir(path.parent)
    temp = path.with_name(path.name + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    with os.fdopen(os.open(temp, flags, 0o600), "w") as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(content)
    temp.replace(path)


@contextmanager
def _incoming_lock():
    state = _ensure_private_dir(desk.state_dir() / "rook")
    fd = os.open(state / "memory-incoming.lock", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def remember(text):
    """Append one {ts, text} JSON line to incoming.jsonl and return the entry."""
    if is_shared():
        raise ValueError('Shared memory is active; use ~/.agents/bin/remember "<fact and why>" instead.')
    clean = str(text or "").strip()
    if not clean:
        raise ValueError("Give the fact to remember.")
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "text": clean}
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    path = memory_dir() / "incoming.jsonl"
    with _incoming_lock():
        _ensure_private_dir(path.parent)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
        with os.fdopen(os.open(path, flags, 0o600), "a") as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(line)
    return entry


def _parse_incoming_bytes(raw):
    items = []
    for raw_line in raw.decode(errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            items.append({"ts": "", "text": line})
            continue
        if isinstance(row, dict) and isinstance(row.get("text"), str) and row["text"].strip():
            items.append({"ts": str(row.get("ts") or ""), "text": row["text"].strip()})
        else:
            items.append({"ts": "", "text": line})
    return items


def _snapshot_incoming():
    """Read incoming.jsonl raw bytes and parsed entries under the incoming lock."""
    path = memory_dir() / "incoming.jsonl"
    with _incoming_lock():
        try:
            raw = path.read_bytes()
        except OSError:
            return b"", []
    return raw, _parse_incoming_bytes(raw)


def _drain_incoming(consumed_raw):
    """Remove only the exact bytes consumed by a successful dream run, keeping concurrent appends."""
    if not consumed_raw:
        return
    path = memory_dir() / "incoming.jsonl"
    with _incoming_lock():
        try:
            current = path.read_bytes()
        except OSError:
            return
        if not current.startswith(consumed_raw):
            return
        remainder = current[len(consumed_raw):]
        if remainder.strip():
            _write_private_atomic(path, remainder.decode(errors="replace"))
        else:
            path.unlink(missing_ok=True)


def startup_prompt(python_exe, relay_path):
    """Return Rook's own-memory prompt section, or empty string when shared memory is active."""
    if is_shared():
        return ""
    mem_dir = memory_dir()
    try:
        index_text = (mem_dir / "MEMORY.md").read_text(errors="replace").strip()
    except OSError:
        index_text = ""
    if len(index_text) > INDEX_LIMIT:
        index_text = index_text[:INDEX_LIMIT].rstrip() + "\n(truncated)"
    try:
        incoming = _parse_incoming_bytes((mem_dir / "incoming.jsonl").read_bytes())
    except OSError:
        incoming = []
    # Keep the exact phrase "that your session start message names" so Antigravity's prompt table still matches.
    parts = [
        f"Your memory folder is {mem_dir}, used instead of any folder that your session start message names. "
        "Before you answer from memory, read the relevant .md notes in that folder. "
        "When the user states a goal, fact, or standing preference, or asks you to remember something, "
        f'save it right away by running {python_exe} {relay_path} remember "<fact and why>". '
        "That command appends to incoming.jsonl and returns at once with no model call; a nightly tidy "
        "folds incoming entries into notes and keeps MEMORY.md current. Keep notes short and never store secrets."
    ]
    if index_text:
        parts.append("--- Memory index (MEMORY.md) ---\n" + index_text + "\n--- End of memory index ---")
    if incoming:
        # Keep the newest incoming notes first so a large backlog never drops recent facts.
        kept, used, trimmed = [], 0, False
        for item in reversed(incoming):
            ts = item.get("ts") or ""
            row = ((f"- [{ts}] " if ts else "- ") + item["text"])[:INCOMING_LIMIT]
            if kept and used + len(row) > INCOMING_LIMIT:
                trimmed = True
                break
            kept.append(row)
            used += len(row) + 1
        kept.reverse()
        if trimmed:
            kept.insert(0, "- (older untidied notes in incoming.jsonl)")
        parts.append("--- Recent notes not yet tidied (incoming.jsonl) ---\n"
                     + "\n".join(kept)
                     + "\n--- End of recent notes ---")
    if not index_text and not incoming:
        parts.append("Your memory folder has no notes yet.")
    return "\n\n".join(parts) + "\n\n"


def new_turns_since(since_ts):
    """Return (formatted turn lines, newest timestamp) for spoken/typed turns newer than since_ts."""
    path = desk.state_dir() / "rook/turns.jsonl"
    try:
        with open(path, "rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - TURNS_TAIL_BYTES))
            lines = handle.read().decode(errors="replace").splitlines()
    except OSError:
        return [], since_ts
    found, max_ts, user_turns = [], since_ts, set()
    for raw in lines:
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        event = row.get("event")
        if event not in ("request", "response"):
            continue
        session = row.get("session")
        if event == "request":
            if row.get("source") not in ("spoken", "typed"):
                continue
            turn_id = row.get("turn")
            if turn_id is not None:
                user_turns.add((session, turn_id))
        at = row.get("at")
        if not isinstance(at, str):
            continue
        try:
            parsed = datetime.fromisoformat(at)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        ts = parsed.timestamp()
        if ts <= since_ts:
            continue
        if event == "request":
            text = str(row.get("text") or "").strip()
            if text:
                found.append(f"[{at}] User ({row['source']}): {text[:1200]}")
                max_ts = max(max_ts, ts)
        else:
            turns = row.get("turns") or ([row["turn"]] if row.get("turn") is not None else [])
            if not any((session, turn_id) in user_turns for turn_id in turns):
                continue
            text = str(row.get("text") or row.get("spoken") or "").strip()
            if text:
                found.append(f"[{at}] Rook: {text[:1200]}")
                max_ts = max(max_ts, ts)
    return found[-MAX_TURNS:], max_ts


def backup_memory(keep=MAX_BACKUPS):
    """Copy the current memory folder to a timestamped backup and keep only the newest keep backups."""
    mem_dir = _ensure_private_dir(memory_dir())
    bdir = _ensure_private_dir(mem_dir.parent / "memory-backups")
    dest = _ensure_private_dir(bdir / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    for entry in sorted(mem_dir.iterdir()):
        if entry.is_file() and not entry.is_symlink():
            shutil.copy2(entry, dest / entry.name)
    existing = sorted(p for p in bdir.iterdir() if p.is_dir() and not p.is_symlink())
    for old in existing[:-keep] if len(existing) > keep else ():
        shutil.rmtree(old, ignore_errors=True)
    return dest


def _is_dream_path_key(key):
    lower = str(key).strip().lower()
    return lower in _DREAM_PATH_KEYS or any(sub in lower for sub in _DREAM_PATH_SUBSTRINGS)


def _is_dream_cwd_key(key):
    return str(key).strip().lower() in _DREAM_CWD_KEYS


def _extract_dream_paths(value, key_kind=None):
    """Yield (kind, raw_str) from path-bearing keys only; kind is 'cwd' or 'path'."""
    if isinstance(value, str):
        if key_kind:
            yield key_kind, value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _extract_dream_paths(item, key_kind=key_kind)
    elif isinstance(value, dict):
        for k, v in value.items():
            if _is_dream_cwd_key(k):
                child_kind = "cwd"
            elif _is_dream_path_key(k):
                child_kind = "path"
            else:
                child_kind = None
            yield from _extract_dream_paths(v, key_kind=child_kind)


def _resolve_dream_path(raw, base_dir):
    """Normalize a path string and resolve symlinks relative to base_dir. Return Path or None."""
    if not isinstance(raw, str) or not raw or "\n" in raw or "\r" in raw or "\x00" in raw:
        return None
    text = raw.strip()
    if not text or "$" in text:
        return None
    if text.lower().startswith("file://"):
        parsed = urllib.parse.urlparse(text)
        if parsed.netloc not in ("", "localhost"):
            return None
        text = urllib.parse.unquote(parsed.path)
        if not text or "\n" in text or "\r" in text or "\x00" in text or "$" in text:
            return None
    elif _URI_SCHEME.match(text):
        return None
    text = os.path.expanduser(text)
    if not text or "\n" in text or "\r" in text or "\x00" in text or "$" in text or text.startswith("~"):
        return None
    joined = text if os.path.isabs(text) else os.path.join(str(base_dir), text)
    return Path(os.path.realpath(joined))


def _inside_root(path, allowed_root):
    return path == allowed_root or allowed_root in path.parents


def _dream_guard_decision(tool_name, args, allowed_dir, cwd=None):
    """Shared confinement policy for Antigravity dream (PreToolUse hook and ACP permission requests).

    Returns (allowed: bool, reason: str).
    """
    tool = str(tool_name or "").strip().lower()
    if tool not in DREAM_ALLOWED_TOOLS:
        return False, (f"Memory dream denies {tool or 'unknown'}: only file read, search, write, and edit "
                       "tools inside the memory folder are allowed.")
    if tool == "finish":
        return True, ""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return False, f"Memory dream denies {tool}: tool arguments must be a JSON object."

    allowed_root = Path(os.path.realpath(str(allowed_dir)))
    incoming_path = allowed_root / "incoming.jsonl"

    cwd_raws, path_raws = [], []
    if cwd is not None and str(cwd).strip():
        cwd_raws.append(str(cwd))
    for kind, raw in _extract_dream_paths(args):
        if kind == "cwd":
            cwd_raws.append(raw)
        else:
            path_raws.append(raw)

    resolved_cwds = []
    for raw_cwd in cwd_raws:
        c_path = _resolve_dream_path(raw_cwd, allowed_root)
        if c_path is None or not _inside_root(c_path, allowed_root):
            return False, f"Memory dream denies {tool}: working directory must stay inside {allowed_root}."
        resolved_cwds.append(c_path)

    base_dir = resolved_cwds[0] if resolved_cwds else allowed_root

    for raw_path in path_raws:
        resolved = _resolve_dream_path(raw_path, base_dir)
        if resolved is None or not _inside_root(resolved, allowed_root):
            return False, f"Memory dream denies {tool}: path must stay inside {allowed_root}."
        if tool in DREAM_WRITE_TOOLS:
            if resolved == allowed_root:
                return False, f"Memory dream denies {tool}: cannot write to the memory folder itself."
            if resolved == incoming_path or resolved.name.lower() == "incoming.jsonl":
                return False, f"Memory dream denies {tool}: do not edit or delete incoming.jsonl."
            if resolved.parent != allowed_root or resolved.name.startswith(".") or resolved.suffix.lower() != ".md":
                return False, (f"Memory dream denies {tool}: writes must be flat .md notes directly inside "
                               f"{allowed_root} (no dotfiles, subdirectories, or non-.md files).")

    if tool in DREAM_WRITE_TOOLS and not path_raws:
        return False, f"Memory dream denies {tool}: missing target file path."
    if tool in DREAM_READ_FILE_TOOLS and not path_raws:
        return False, f"Memory dream denies {tool}: missing file path."
    return True, ""


def _make_dream_temp_dir(prefix="rook-dream-agy-"):
    """Create an ephemeral private temp folder under runtime_dir() if writable, else temp dir."""
    try:
        rt = desk.runtime_dir()
        rt.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.access(rt, os.W_OK | os.X_OK):
            return Path(tempfile.mkdtemp(prefix=prefix, dir=str(rt)))
    except OSError:
        pass
    return Path(tempfile.mkdtemp(prefix=prefix))


def _dream_guard_command(mem_dir_real):
    return (
        f"{shlex.quote(desk.python3_exe())} -I "
        f"{shlex.quote(str(Path(__file__).resolve()))} dream-guard "
        f"{shlex.quote(str(mem_dir_real))}"
    )


def _write_dream_agy_config(temp_dir, mem_dir_real):
    config = temp_dir / "config"
    (config / "projects").mkdir(mode=0o700, parents=True, exist_ok=True)
    (config / "projects/default-cli-project.json").write_text(
        json.dumps({"id": "default-cli-project", "name": "CLI Project", "projectResources": {}}, indent=2) + "\n"
    )
    (config / "mcp_config.json").write_text(json.dumps({"mcpServers": {}}) + "\n")
    (config / "skills.json").write_text(json.dumps({"entries": []}) + "\n")
    hooks = {
        "rook-dream": {
            "PreToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [{"type": "command", "command": _dream_guard_command(mem_dir_real), "timeout": 30}],
                }
            ]
        }
    }
    (config / "hooks.json").write_text(json.dumps(hooks) + "\n")


def _agy_error_message(stage, error, signed_out_fn):
    if isinstance(error, dict) and signed_out_fn(error):
        return "Memory dream failed: Antigravity is not signed in."
    msg = (error.get("message") if isinstance(error, dict) else str(error)) or f"{stage} error"
    return f"Memory dream failed: Antigravity {stage} failed: {' '.join(str(msg).split())[:200]}"


def _kill_process_group(proc, sig, *, force=False):
    """Signal the child's process group (started with start_new_session=True), falling back to proc itself."""
    if not force and proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, sig)
    except OSError:
        if proc.poll() is None:
            try:
                proc.terminate() if sig == signal.SIGTERM else proc.kill()
            except OSError:
                pass


def _run_antigravity_dream(agy_exe, saved, mem_dir, prompt_text, timeout=DREAM_TIMEOUT):
    """Run one confined, one-shot synchronous memory tidy over `agy acp`. Return (ok, summary_or_error)."""
    import agy_harness  # Lazy import so `python3 -I memory.py dream-guard` stays fast and self-contained.

    mem_dir_real = Path(os.path.realpath(str(mem_dir)))
    temp_dir = _make_dream_temp_dir()
    stderr_path = temp_dir / "agy.stderr"
    proc = None
    stderr_file = None
    watchdog = None
    watchdog_fired = threading.Event()
    session_id = None
    try:
        _write_dream_agy_config(temp_dir, mem_dir_real)
        env = dict(os.environ)
        env["AGY_CLI_DISABLE_AUTO_UPDATE"] = "1"
        env["BROWSER"] = desk.false_exe()
        cmd = [
            agy_exe,
            "acp",
            "--gemini-dir", str(temp_dir),
            "--app-data-dir", agy_harness.APP,
            "--include-default-customizations=false",
        ]
        stderr_file = open(stderr_path, "wb")
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                cwd=str(mem_dir_real),
                env=env,
                start_new_session=True,
            )
        except OSError as error:
            return False, f"Memory dream failed: {error}"

        def on_watchdog():
            watchdog_fired.set()
            _kill_process_group(proc, signal.SIGKILL)

        # Hard cap covering blocked stdin writes (>64 KiB prompt) as well as stalled reads.
        watchdog = threading.Timer(timeout + 5, on_watchdog)
        watchdog.daemon = True
        watchdog.start()

        deadline = time.monotonic() + timeout
        out_fd = proc.stdout.fileno()
        buf = bytearray()
        rpc_seq = 0
        all_text = []
        after_tool_text = []

        def send_rpc(message):
            payload = (json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode()
            proc.stdin.write(payload)
            proc.stdin.flush()

        def call_rpc(method, params):
            nonlocal rpc_seq
            rpc_seq += 1
            send_rpc({"id": rpc_seq, "method": method, "params": params})
            return rpc_seq

        def read_line():
            while True:
                nl = buf.find(b"\n")
                if nl != -1:
                    line = bytes(buf[:nl])
                    del buf[:nl + 1]
                    return line.decode(errors="replace")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"timed out after {timeout}s")
                ready, _, _ = select.select([out_fd], [], [], remaining)
                if not ready:
                    raise TimeoutError(f"timed out after {timeout}s")
                chunk = os.read(out_fd, 65536)
                if not chunk:
                    if buf:
                        line = bytes(buf)
                        buf.clear()
                        return line.decode(errors="replace")
                    return None
                buf.extend(chunk)

        def handle_permission(rpc_id, params):
            if not isinstance(params, dict):
                params = {}
            call = params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
            options = params.get("options") if isinstance(params.get("options"), list) else []
            call_id = str(call.get("toolCallId") or "")
            if call_id.startswith("interaction_"):
                allowed = False
            else:
                tool_name = call.get("name") or call.get("title") or ""
                raw_input = (call.get("rawInput") if isinstance(call.get("rawInput"), dict)
                             else call.get("args") if isinstance(call.get("args"), dict) else {})
                allowed, _ = _dream_guard_decision(tool_name, raw_input, mem_dir_real)
            wanted = "allow_once" if allowed else "reject_once"
            option = next((opt for opt in options if isinstance(opt, dict) and opt.get("kind") == wanted), None)
            outcome = ({"outcome": "selected", "optionId": option["optionId"]}
                       if (option and "optionId" in option) else {"outcome": "cancelled"})
            if rpc_id is not None:
                send_rpc({"id": rpc_id, "result": {"outcome": outcome}})

        def read_until(expected_id):
            while True:
                line = read_line()
                if line is None:
                    return None
                stripped = line.strip()
                if not stripped.startswith("{"):
                    continue
                try:
                    msg = json.loads(stripped)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                method = msg.get("method")
                rpc_id = msg.get("id")
                if method == "session/update":
                    params = msg.get("params")
                    update = params.get("update") if isinstance(params, dict) else None
                    if not isinstance(update, dict):
                        continue
                    kind = update.get("sessionUpdate")
                    if kind == "agent_message_chunk":
                        content = update.get("content")
                        text = content.get("text") if isinstance(content, dict) else None
                        if isinstance(text, str) and text:
                            all_text.append(text)
                            after_tool_text.append(text)
                    elif kind == "tool_call":
                        after_tool_text.clear()
                elif method == "session/request_permission":
                    handle_permission(rpc_id, msg.get("params"))
                elif method:
                    if rpc_id is not None:
                        send_rpc({"id": rpc_id, "error": {"code": -32601, "message": "Method not supported."}})
                elif rpc_id == expected_id:
                    return msg

        def eof_failure(stage):
            if watchdog_fired.is_set():
                return False, f"Memory dream failed: Antigravity timed out after {timeout}s."
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _kill_process_group(proc, signal.SIGKILL)
                proc.wait(timeout=2)
            if session_id and (problem := agy_harness.failure(temp_dir, session_id)):
                return False, f"Memory dream failed: {problem}"
            try:
                stderr_file.flush()
                err_tail = stderr_path.read_text(errors="replace").strip()
            except OSError:
                err_tail = ""
            detail = " ".join(err_tail.splitlines()[-3:])[:200] if err_tail else f"exit {proc.returncode}"
            return False, f"Memory dream failed: Antigravity closed during {stage} ({detail})."

        try:
            init_id = call_rpc("initialize", agy_harness.INITIALIZE)
            init_resp = read_until(init_id)
            if init_resp is None:
                return eof_failure("initialize")
            if init_resp.get("error"):
                return False, _agy_error_message("initialize", init_resp["error"], agy_harness.signed_out)

            new_id = call_rpc("session/new", {"cwd": str(mem_dir_real), "mcpServers": []})
            new_resp = read_until(new_id)
            if new_resp is None:
                return eof_failure("session/new")
            if new_resp.get("error"):
                return False, _agy_error_message("session/new", new_resp["error"], agy_harness.signed_out)
            new_result = new_resp.get("result")
            session_id = new_result.get("sessionId") if isinstance(new_result, dict) else None
            if not session_id:
                return False, "Memory dream failed: Antigravity session/new returned no sessionId."

            effort = saved.get("agent_effort")
            options_to_set = [
                ("mode", "default"),
                ("model", saved.get("agent_model") or agy_harness.Antigravity.model),
                ("thought_level", agy_harness.EFFORTS.get(effort, agy_harness.Antigravity.effort)),
            ]
            for config_id, value in options_to_set:
                opt_id = call_rpc("session/set_config_option", {
                    "sessionId": session_id,
                    "configId": config_id,
                    "value": value,
                })
                opt_resp = read_until(opt_id)
                if opt_resp is None:
                    return eof_failure(f"session/set_config_option({config_id})")
                if opt_resp.get("error"):
                    err = opt_resp["error"]
                    if (isinstance(err, dict) and agy_harness.signed_out(err)) or config_id == "mode":
                        return False, _agy_error_message(
                            f"session/set_config_option({config_id})", err, agy_harness.signed_out
                        )

            prompt_id = call_rpc("session/prompt", {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt_text}],
            })
            prompt_resp = read_until(prompt_id)
            if prompt_resp is None:
                return eof_failure("session/prompt")
            if prompt_resp.get("error"):
                return False, _agy_error_message("session/prompt", prompt_resp["error"], agy_harness.signed_out)
            prompt_result = prompt_resp.get("result")
            stop = prompt_result.get("stopReason") if isinstance(prompt_result, dict) else None
            if stop == "refusal":
                return False, "Memory dream failed: Antigravity refused the request (quota or policy refusal)."
            if stop not in (None, "end_turn"):
                return False, f"Memory dream failed: Antigravity stopped early ({stop})."
            if problem := agy_harness.failure(temp_dir, session_id):
                return False, f"Memory dream failed: {problem}"
            final_text = "".join(after_tool_text).strip() or "".join(all_text).strip()
            return True, " ".join(final_text.split())[:200]
        except TimeoutError as error:
            if session_id and proc.poll() is None:
                try:
                    send_rpc({"method": "session/cancel", "params": {"sessionId": session_id}})
                except OSError:
                    pass
            return False, f"Memory dream failed: Antigravity {error}."
        except (BrokenPipeError, OSError) as error:
            if watchdog_fired.is_set():
                return False, f"Memory dream failed: Antigravity timed out after {timeout}s."
            return False, f"Memory dream failed: Antigravity I/O error: {error}"
    finally:
        if watchdog is not None:
            watchdog.cancel()
        if proc is not None:
            for stream in (proc.stdin, proc.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if proc.poll() is None:
                _kill_process_group(proc, signal.SIGTERM)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _kill_process_group(proc, signal.SIGKILL)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
        if stderr_file is not None:
            try:
                stderr_file.close()
            except OSError:
                pass
        shutil.rmtree(temp_dir, ignore_errors=True)


_CODEX_DREAM_DISABLED_FEATURES = (
    "apps",
    "browser_use",
    "computer_use",
    "image_generation",
    "plugins",
    "multi_agent",
)


def _codex_signed_out(stderr_text, stdout_text, signed_out_fn):
    """Whether Codex CLI error lines indicate missing or rejected authentication.

    Inspects only ERROR-prefixed lines and the trailing stderr lines (never the echoed user prompt)
    so conversation text mentioning sign-in cannot mask an unrelated failure.
    """
    src = (stderr_text or "").strip() or (stdout_text or "").strip()
    if not src:
        return False
    lines = [ln.strip() for ln in src.splitlines() if ln.strip()]
    error_lines = [ln for ln in lines if ln.lower().startswith("error")]
    sample = "\n".join(dict.fromkeys(error_lines + lines[-5:]))
    if signed_out_fn({"message": sample}):
        return True
    low = sample.lower()
    return any(tok in low for tok in (
        "401 unauthorized",
        "missing bearer",
        "invalid_api_key",
        "authentication failed",
        "refresh token",
        "sign in again",
    ))


def _write_codex_dream_config(codex_home, codex_harness):
    """Write a minimal isolated config.toml disabling connectors, web search, project docs, and host skills."""
    agents = agents_dir()
    hidden = list(codex_harness.disabled_host_skills(agents, allow=()))
    cfg = {
        "approval_policy": "never",
        "web_search": "disabled",
        "project_doc_max_bytes": 0,
        "history": {"persistence": "none"},
        "agents": {"enabled": False},
        "features": {name: False for name in _CODEX_DREAM_DISABLED_FEATURES},
        "sandbox_workspace_write": {
            "network_access": False,
            "exclude_slash_tmp": True,
            "exclude_tmpdir_env_var": True,
        },
    }
    if hidden:
        cfg["skills"] = {"config": [{"path": path, "enabled": False} for path in hidden]}
    cfg_path = codex_home / "config.toml"
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    with os.fdopen(os.open(cfg_path, flags, 0o600), "w") as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(codex_harness.dump_toml(cfg))


def _sanitize_codex_memory_dir(mem_dir_real):
    """Reject symlinked incoming.jsonl and strip any top-level symlinks created inside the memory folder."""
    incoming = mem_dir_real / "incoming.jsonl"
    if incoming.is_symlink():
        incoming.unlink(missing_ok=True)
        return False, "Memory dream failed: Codex replaced incoming.jsonl with a symlink."
    for entry in list(mem_dir_real.iterdir()):
        if entry.is_symlink():
            entry.unlink(missing_ok=True)
    return True, ""


def _run_codex_dream(codex_exe, saved, mem_dir, prompt_text, timeout=DREAM_TIMEOUT):
    """Run one confined, one-shot synchronous memory tidy over `codex exec`. Return (ok, summary_or_error).

    Note: Codex's `workspace-write` sandbox confines writes to `mem_dir` (and disables network and /tmp),
    but unlike Antigravity's dream-guard hook it does not restrict read-only shell commands outside `mem_dir`.
    """
    import codex_harness  # Lazy import so `python3 -I memory.py dream-guard` stays fast and self-contained.

    mem_dir_real = Path(os.path.realpath(str(mem_dir)))
    temp_dir = _make_dream_temp_dir("rook-dream-codex-")
    proc = None
    try:
        codex_home = _ensure_private_dir(temp_dir / "codex-home")
        _write_codex_dream_config(codex_home, codex_harness)
        user_home = codex_harness.user_codex_home()
        for name in ("auth.json", ".credentials.json"):
            src = user_home / name
            if src.exists():
                (codex_home / name).symlink_to(src)

        last_msg_path = temp_dir / "last-message.txt"
        cmd = [
            codex_exe,
            "exec",
            "--sandbox", "workspace-write",
            "-C", str(mem_dir_real),
            "--ephemeral",
            "--skip-git-repo-check",
            "--ignore-rules",
            "--color", "never",
            "-c", 'approval_policy="never"',
            "-c", 'web_search="disabled"',
            "-c", "project_doc_max_bytes=0",
            "-c", 'history.persistence="none"',
            "-c", "sandbox_workspace_write.network_access=false",
            "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
        ]
        for feature in _CODEX_DREAM_DISABLED_FEATURES:
            cmd += ["--disable", feature]
        if model := saved.get("agent_model"):
            cmd += ["-m", model]
        effort = saved.get("agent_effort")
        if effort and (mapped := codex_harness.EFFORTS.get(effort)):
            cmd += ["-c", f'model_reasoning_effort="{mapped}"']
        cmd += ["-o", str(last_msg_path), "-"]

        env = dict(os.environ)
        env["CODEX_HOME"] = str(codex_home)
        env["BROWSER"] = desk.false_exe()

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(mem_dir_real),
                env=env,
                text=True,
                errors="replace",
                start_new_session=True,
            )
        except OSError as error:
            return False, f"Memory dream failed: {error}"

        try:
            stdout, stderr = proc.communicate(input=prompt_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc, signal.SIGTERM, force=True)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            _kill_process_group(proc, signal.SIGKILL, force=True)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            return False, f"Memory dream failed: Codex timed out after {timeout}s."
        except OSError as error:
            return False, f"Memory dream failed: Codex I/O error: {error}"

        if proc.returncode != 0:
            if _codex_signed_out(stderr, stdout, codex_harness.signed_out_error):
                return False, "Memory dream failed: Codex is not signed in."
            err_src = (stderr or "").strip() or (stdout or "").strip()
            if err_src:
                lines = [ln.strip() for ln in err_src.splitlines() if ln.strip()]
                detail = " ".join(lines[-3:])[:200]
            else:
                detail = f"exit {proc.returncode}"
            return False, f"Memory dream failed: {detail}"

        ok_dir, dir_err = _sanitize_codex_memory_dir(mem_dir_real)
        if not ok_dir:
            return False, dir_err

        summary_raw = ""
        try:
            if last_msg_path.is_file() and not last_msg_path.is_symlink():
                summary_raw = last_msg_path.read_text(errors="replace").strip()
        except OSError:
            summary_raw = ""
        if not summary_raw:
            non_empty = [ln.strip() for ln in (stdout or "").splitlines() if ln.strip()]
            summary_raw = non_empty[-1] if non_empty else ""
        return True, " ".join(summary_raw.split())[:200]
    finally:
        if proc is not None:
            if proc.poll() is None:
                _kill_process_group(proc, signal.SIGTERM, force=True)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            _kill_process_group(proc, signal.SIGKILL, force=True)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        shutil.rmtree(temp_dir, ignore_errors=True)


def build_agent_command(saved=None):
    """Return (argv, skip_reason) for the configured non-interactive agent."""
    saved = settings.read_settings()[0] if saved is None else saved
    agent = saved.get("agent", "claude")
    if agent == "pi":  # One print-mode run with no session, none of the person's extensions, and the dream guard.
        exe = desk.find_tool("pi")
        if not exe:
            return None, "Skipped dream: pi is not installed."
        guard = [desk.python3_exe(), "-I", str(Path(__file__).resolve()), "dream-guard", os.path.realpath(memory_dir())]
        cmd = ["env", f"ROOK_DREAM_GUARD={json.dumps(guard)}", exe, "-p", "--no-session", "--no-extensions",
               "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-mcp",
               "--tools", "read,write,edit,find,ls", "-e", str(Path(__file__).with_name("pi_dream_guard.ts"))]
        for flag, key in (("--model", "agent_model"), ("--thinking", "agent_effort")):
            if value := saved.get(key):
                cmd += [flag, value]
        return cmd, None
    if agent != "claude":
        return None, f"Nightly memory tidy does not support agent {agent!r}; skipped."
    exe = desk.find_tool("claude")
    if not exe:
        return None, "Skipped dream: claude is not installed."
    cmd = [
        exe, "-p", "--restricted",
        "--tools", "Read,Write,Edit,Glob",
        "--permission-mode", "acceptEdits",
        "--no-session-persistence",
    ]
    for flag, key in (("--model", "agent_model"), ("--effort", "agent_effort")):
        if value := saved.get(key):
            cmd += [flag, value]
    return cmd, None


def build_dream_prompt(incoming_items, turn_lines):
    """Build the nightly writer prompt from the vendored instructions, incoming notes, and recent turns."""
    base = WRITER_PROMPT.read_text(errors="replace").strip()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    incoming_text = ("\n".join(f"- [{item['ts']}] {item['text']}" if item.get("ts") else f"- {item['text']}"
                               for item in incoming_items) if incoming_items else "(none)")
    turns_text = "\n".join(turn_lines) if turn_lines else "(none)"
    return (
        f"{base}\n\n"
        f"Today (UTC): {today}\nMemory folder: {memory_dir()}\n\n"
        f"## Incoming notes (incoming.jsonl)\n{incoming_text}\n\n"
        f"## Recent Rook turns (turns.jsonl)\n{turns_text}\n"
    )


def run_dream(timeout=DREAM_TIMEOUT):
    """Run one nightly memory tidy in own mode. Return (ok, message)."""
    if is_shared():
        return True, "Shared memory is active; skipping Rook dream."
    state = _ensure_private_dir(desk.state_dir() / "rook")
    lock_fd = os.open(state / "memory-dream.lock", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False, "Another memory dream is already running."
        started = time.time()
        stamp_path = state / "memory-dream.stamp"
        try:
            last_tidy = stamp_path.stat().st_mtime
        except OSError:
            last_tidy = 0.0
        raw_incoming, incoming_items = _snapshot_incoming()
        turn_lines, max_turn_ts = new_turns_since(last_tidy)
        if not incoming_items and not turn_lines:
            return True, "Skipped dream: nothing new since last tidy."
        saved = settings.read_settings()[0]
        use_agy = False
        agy_exe = None
        use_codex = False
        codex_exe = None
        cmd = None
        if env_cmd := os.environ.get("ROOK_DREAM_COMMAND", "").strip():
            cmd = shlex.split(env_cmd)
        elif saved.get("agent", "claude") == "antigravity":
            agy_exe = desk.find_tool("agy")
            if not agy_exe:
                return True, "Skipped dream: agy is not installed."
            use_agy = True
        elif saved.get("agent", "claude") == "codex":
            codex_exe = desk.find_tool("codex")
            if not codex_exe:
                return True, "Skipped dream: codex is not installed."
            use_codex = True
        else:
            cmd, skip_reason = build_agent_command(saved)
            if not cmd:
                return True, skip_reason
        mem_dir = _ensure_private_dir(memory_dir())
        backup_memory()
        prompt_text = build_dream_prompt(incoming_items, turn_lines)
        if use_agy:
            ok, detail = _run_antigravity_dream(agy_exe, saved, mem_dir, prompt_text, timeout=timeout)
            if not ok:
                return False, detail
            summary = detail
        elif use_codex:
            ok, detail = _run_codex_dream(codex_exe, saved, mem_dir, prompt_text, timeout=timeout)
            if not ok:
                return False, detail
            summary = detail
        else:
            try:
                done = subprocess.run(
                    cmd,
                    input=prompt_text,
                    cwd=str(mem_dir),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                return False, f"Memory dream failed: {error}"
            if done.returncode != 0:
                detail = (done.stderr or done.stdout or f"exit {done.returncode}").strip()
                return False, f"Memory dream failed: {detail}"
            summary = " ".join((done.stdout or "").split())[:200]
        _drain_incoming(raw_incoming)
        stamp_path.touch(mode=0o600, exist_ok=True)
        os.chmod(stamp_path, 0o600)
        stamp_ts = max(started, max_turn_ts)
        os.utime(stamp_path, (stamp_ts, stamp_ts))
        return True, (f"Tidied memory ({len(incoming_items)} incoming, {len(turn_lines)} turns)."
                      + (f" {summary}" if summary else ""))
    finally:
        os.close(lock_fd)


def _claude_settings_path():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"


def _git_ignore_path():
    return desk.config_dir() / "git/ignore"


def _systemd_user_dir():
    return desk.config_dir() / "systemd/user"


def _sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_manifest(path=None):
    target = manifest_path() if path is None else Path(path)
    if not target.is_file() or target.is_symlink():
        return None
    try:
        data = json.loads(target.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("installed_by") == "rook" else None


def _read_json_dict(path):
    if not path.exists() and not path.is_symlink():
        return {}, False
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"Could not read {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a JSON object.")
    return data, True


def _write_json_atomic(path, data, default_mode=0o600):
    target = path.resolve() if path.is_symlink() else path
    mode = (target.stat().st_mode & 0o777) if target.exists() else default_mode
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    with os.fdopen(os.open(temp, flags, mode), "w") as out:
        os.fchmod(out.fileno(), mode)
        json.dump(data, out, indent=2)
        out.write("\n")
    temp.replace(target)


def _hook_present(entries, command):
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for hook in entry.get("hooks") or ():
            if not isinstance(hook, dict):
                continue
            cmd = str(hook.get("command") or "")
            if cmd == command or "memory-context.sh" in cmd:
                return True
    return False


def _merge_hook_json(path, command, set_auto_memory=True):
    data, existed = _read_json_dict(path)
    hooks = data.get("hooks")
    if hooks is None:
        hooks = {}
    elif not isinstance(hooks, dict):
        raise ValueError(f"{path} has a non-object 'hooks' field.")
    session_start = hooks.get("SessionStart")
    if session_start is None:
        session_start = []
    elif not isinstance(session_start, list):
        raise ValueError(f"{path} has a non-list 'hooks.SessionStart' field.")
    added = False
    if not _hook_present(session_start, command):
        hook_item = {"type": "command", "command": command, "timeout": 5}
        session_start.append({"matcher": "*", "hooks": [hook_item]})
        hooks["SessionStart"] = session_start
        data["hooks"] = hooks
        added = True
    auto_info = None
    changed = added
    if set_auto_memory:
        had_key = "autoMemoryEnabled" in data
        previous = data.get("autoMemoryEnabled")
        if not had_key or previous is not False:
            data["autoMemoryEnabled"] = False
            changed = True
        auto_info = {"had_key": had_key, "previous": previous}
    if changed:
        _write_json_atomic(path, data)
    return added, not existed, auto_info


def _remove_hook_json(path, command, created_file, auto_memory=None):
    if not path.is_file():
        return
    data, _ = _read_json_dict(path)
    hooks = data.get("hooks")
    if command and isinstance(hooks, dict):
        session_start = hooks.get("SessionStart")
        if isinstance(session_start, list):
            kept_entries = []
            for entry in session_start:
                if not isinstance(entry, dict):
                    kept_entries.append(entry)
                    continue
                items = entry.get("hooks")
                if not isinstance(items, list):
                    kept_entries.append(entry)
                    continue
                kept_hooks = [h for h in items if not (isinstance(h, dict) and h.get("command") == command)]
                if kept_hooks:
                    kept_entries.append({**entry, "hooks": kept_hooks})
            if kept_entries:
                hooks["SessionStart"] = kept_entries
            else:
                hooks.pop("SessionStart", None)
            if not hooks:
                data.pop("hooks", None)
    if isinstance(auto_memory, dict):
        if auto_memory.get("had_key"):
            data["autoMemoryEnabled"] = auto_memory.get("previous")
        else:
            data.pop("autoMemoryEnabled", None)
    if created_file and not data and not path.is_symlink():
        path.unlink(missing_ok=True)
    else:
        _write_json_atomic(path, data)


def _add_git_ignore(path, line):
    existed = path.is_file()
    if existed:
        text = path.read_text(errors="replace")
        if line in text.splitlines():
            return False, False
        sep = "" if (not text or text.endswith("\n")) else "\n"
        path.write_text(text + sep + line + "\n")
        return True, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(line + "\n")
    return True, True


def _remove_git_ignore(path, line, created_file):
    if not path.is_file():
        return
    kept = [row for row in path.read_text(errors="replace").splitlines() if row != line]
    if created_file and not kept:
        path.unlink(missing_ok=True)
    else:
        path.write_text(("\n".join(kept) + "\n") if kept else "")


def _copy_file(src, dst, mode):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        dst.unlink()
    shutil.copyfile(src, dst)
    dst.chmod(mode)


def _run_systemctl(*args):
    try:
        done = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or f"exit {done.returncode}").strip()
        return False, detail
    return True, ""


def _resolve_shared_dir(memory_dir_bin, workspace):
    done = subprocess.run([str(memory_dir_bin), "--start", str(workspace)], capture_output=True, text=True, timeout=15)
    if done.returncode == 3:
        return None
    if done.returncode != 0 or not done.stdout.strip():
        detail = (done.stderr or f"exit {done.returncode}").strip()
        raise RuntimeError(f"Could not resolve shared memory folder for {workspace}: {detail}")
    return Path(done.stdout.strip())


def _rewrite_index_lines(lines, renames):
    out = []
    for line in lines:
        updated = line
        for old_stem, new_stem in renames.items():
            updated = updated.replace(f"[[{old_stem}]]", f"[[{new_stem}]]")
            updated = updated.replace(f"({old_stem}.md)", f"({new_stem}.md)")
        out.append(updated)
    return out


def _merge_index_file(src, dst, renames):
    src_lines = _rewrite_index_lines(
        [line for line in src.read_text(errors="replace").splitlines() if line.strip()],
        renames,
    )
    dst_text = dst.read_text(errors="replace") if dst.exists() else ""
    dst_lines = [line for line in dst_text.splitlines() if line.strip()]
    if not dst_lines or dst_lines == ["# Memory index"]:
        dst.write_text("\n".join(src_lines) + "\n" if src_lines else "# Memory index\n")
        src.unlink()
        return
    seen = set(dst_lines)
    extra = [line for line in src_lines if line != "# Memory index" and line not in seen]
    if extra:
        sep = "" if (not dst_text or dst_text.endswith("\n")) else "\n"
        dst.write_text(dst_text + sep + "\n".join(extra) + "\n")
    src.unlink()


def _move_own_notes_to_shared(target_dir):
    own = memory_dir()
    if not own.is_dir():
        return []
    md_files = sorted(f for f in own.glob("*.md") if f.is_file() and not f.is_symlink())
    raw_incoming, incoming_items = _snapshot_incoming()
    if not md_files and not incoming_items:
        return []
    target_dir.mkdir(parents=True, exist_ok=True)
    moved_names, renames = [], {}
    index_src = None
    for src in md_files:
        if src.name == "MEMORY.md":
            index_src = src
            continue
        dst = target_dir / src.name
        if not dst.exists():
            shutil.move(str(src), str(dst))
            moved_names.append(dst.name)
        elif dst.read_bytes() == src.read_bytes():
            src.unlink()
            moved_names.append(dst.name)
        else:
            idx = 1
            while True:
                suffix = "-rook" if idx == 1 else f"-rook-{idx}"
                alt = target_dir / f"{src.stem}{suffix}.md"
                if not alt.exists():
                    shutil.move(str(src), str(alt))
                    renames[src.stem] = alt.stem
                    moved_names.append(alt.name)
                    break
                idx += 1
    if index_src is not None:
        _merge_index_file(index_src, target_dir / "MEMORY.md", renames)
        moved_names.append("MEMORY.md")
    if incoming_items:
        note = target_dir / "rook-incoming.md"
        lines = [f"- [{item['ts']}] {item['text']}" if item.get("ts") else f"- {item['text']}" for item in incoming_items]
        if note.exists():
            old = note.read_text(errors="replace")
            sep = "" if (not old or old.endswith("\n")) else "\n"
            note.write_text(old + sep + "\n".join(lines) + "\n")
        else:
            note.write_text(
                "---\nname: rook-incoming\n"
                "description: Notes saved with relay.py remember before switching to shared memory.\n---\n\n"
                + "\n".join(lines) + "\n"
            )
        index = target_dir / "MEMORY.md"
        index_line = "[[rook-incoming]] - Notes saved with relay.py remember before switching to shared memory."
        idx_text = index.read_text(errors="replace") if index.exists() else "# Memory index\n"
        if "[[rook-incoming]]" not in idx_text:
            sep = "" if (not idx_text or idx_text.endswith("\n")) else "\n"
            index.write_text(idx_text + sep + index_line + "\n")
        _drain_incoming(raw_incoming)
        moved_names.append("rook-incoming.md")
        if "MEMORY.md" not in moved_names:
            moved_names.append("MEMORY.md")
    return sorted(set(moved_names))


def _copy_shared_notes_to_own(source_dir, moved_notes):
    if not source_dir or not source_dir.is_dir() or not moved_notes:
        return 0
    to_copy = []
    for name in moved_notes:
        src = source_dir / name
        if src.is_file() and not src.is_symlink():
            to_copy.append(src)
    if not to_copy:
        return 0
    own = _ensure_private_dir(memory_dir())
    for src in to_copy:
        shutil.copy2(src, own / src.name)
    return len(to_copy)


def _render_memory_conf():
    claude_bin = desk.find_tool("claude") or shutil.which("claude") or ""
    lines = []
    for line in (SHARED_SOURCE / "memory.conf").read_text().splitlines():
        if line.startswith("CLAUDE_BIN=") and claude_bin:
            lines.append(f"CLAUDE_BIN={claude_bin}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def install_shared():
    """Install the vendored shared memory system into ~/.agents/. Return (ok, message)."""
    if not shutil.which("systemctl"):  # Its nightly tidy is agent-dream.timer: refuse before anything is written.
        return False, ("Refused: the shared memory tidies its notes each night with a systemd timer, and this computer "
                       "has no systemd, so Rook keeps its own memory.")
    agents = agents_dir()
    mpath = manifest_path()
    dream_bin = agents / "bin/dream"
    prior = _read_manifest(mpath)
    if dream_bin.exists() or dream_bin.is_symlink():
        prior_files = prior.get("files") if prior else None
        owned = (
            prior is not None
            and not dream_bin.is_symlink()
            and (isinstance(prior_files, dict) and str(dream_bin) in prior_files
                 or isinstance(prior_files, list) and str(dream_bin) in prior_files)
        )
        if not owned:
            return False, "Refused: ~/.agents/bin/dream already exists and was not installed by Rook."

    claude_path = _claude_settings_path()
    try:
        _read_json_dict(claude_path)
    except ValueError as error:
        return False, str(error)

    prior_files = dict(prior["files"]) if prior and isinstance(prior.get("files"), dict) else {}
    prior_timer = prior.get("timer") if prior and isinstance(prior.get("timer"), dict) else None
    manifest = {
        "version": 1,
        "installed_by": "rook",
        "files": prior_files,
        "git_ignore": prior.get("git_ignore") if prior else None,
        "claude_hook": prior.get("claude_hook") if prior else None,
        "timer": dict(prior_timer) if prior_timer else {"unit": "agent-dream.timer", "enabled": False},
        "rook_memory_dir": prior.get("rook_memory_dir") if prior else None,
        "moved_notes": list(prior.get("moved_notes") or []) if prior else [],
    }

    def save_manifest():
        _write_json_atomic(mpath, manifest, default_mode=0o600)

    # Write the manifest before making any change so a partial failure can always be undone or resumed.
    save_manifest()

    for rel, mode in SHARED_FILES:
        dest = agents / rel
        key = str(dest)
        if (dest.exists() or dest.is_symlink()) and key not in manifest["files"]:
            continue
        _copy_file(SHARED_SOURCE / rel, dest, mode)
        manifest["files"][key] = _sha256_file(dest)
        save_manifest()

    conf_dest = agents / "memory.conf"
    if not (conf_dest.exists() or conf_dest.is_symlink()):
        conf_dest.parent.mkdir(parents=True, exist_ok=True)
        conf_dest.write_text(_render_memory_conf())
        conf_dest.chmod(0o644)
        manifest["files"][str(conf_dest)] = _sha256_file(conf_dest)
        save_manifest()

    systemd_dir = _systemd_user_dir()
    for unit in SHARED_UNITS:
        dest = systemd_dir / unit
        key = str(dest)
        if (dest.exists() or dest.is_symlink()) and key not in manifest["files"]:
            continue
        _copy_file(SHARED_SOURCE / "systemd" / unit, dest, 0o644)
        manifest["files"][key] = _sha256_file(dest)
        save_manifest()

    git_path = _git_ignore_path()
    git_added, git_created = _add_git_ignore(git_path, GIT_IGNORE_LINE)
    prev_git = manifest.get("git_ignore")
    if isinstance(prev_git, dict) and prev_git.get("path") == str(git_path):
        git_added = git_added or bool(prev_git.get("added"))
        git_created = bool(prev_git.get("created_file"))
    manifest["git_ignore"] = {
        "path": str(git_path),
        "line": GIT_IGNORE_LINE,
        "added": git_added,
        "created_file": git_created,
    }
    save_manifest()

    hook_path = agents / "hooks/memory-context.sh"
    hook_cmd = f"bash {shlex.quote(str(hook_path))}"
    try:
        claude_added, claude_created, auto_info = _merge_hook_json(claude_path, hook_cmd, set_auto_memory=True)
    except ValueError as error:
        return False, str(error)
    prev_claude = manifest.get("claude_hook")
    if isinstance(prev_claude, dict) and prev_claude.get("path") == str(claude_path):
        claude_added = claude_added or bool(prev_claude.get("added"))
        claude_created = bool(prev_claude.get("created_file"))
        if isinstance(prev_claude.get("auto_memory"), dict):
            auto_info = prev_claude["auto_memory"]
    manifest["claude_hook"] = {
        "path": str(claude_path),
        "command": hook_cmd,
        "added": claude_added,
        "created_file": claude_created,
        "auto_memory": auto_info,
    }
    save_manifest()

    ok, detail = _run_systemctl("daemon-reload")
    if not ok:
        return False, f"Could not reload user systemd units: {detail}"
    ok, detail = _run_systemctl("enable", "--now", "agent-dream.timer")
    if not ok:
        return False, f"Could not enable agent-dream.timer: {detail}"
    manifest["timer"] = {"unit": "agent-dream.timer", "enabled": True}
    save_manifest()

    try:
        rook_shared = _resolve_shared_dir(agents / "bin/memory-dir", rook_workspace())
    except RuntimeError as error:
        return False, str(error)
    moved_names = _move_own_notes_to_shared(rook_shared) if rook_shared else []
    if rook_shared:
        manifest["rook_memory_dir"] = str(rook_shared)
    if moved_names:
        manifest["moved_notes"] = sorted(set(manifest["moved_notes"]) | set(moved_names))
    save_manifest()
    note_msg = f" Moved {len(moved_names)} Rook note file(s) to {rook_shared}." if moved_names else ""
    return True, f"Installed shared memory in {agents}.{note_msg}"


def remove_shared():
    """Undo Rook's shared-memory install from its manifest, keeping all notes and copying Rook's notes back."""
    mpath = manifest_path()
    manifest = _read_manifest(mpath)
    if manifest is None:
        return False, "Shared memory was not installed by Rook."

    rook_shared = Path(manifest["rook_memory_dir"]) if manifest.get("rook_memory_dir") else None
    copied = _copy_shared_notes_to_own(rook_shared, manifest.get("moved_notes") or [])

    timer = manifest.get("timer") or {}
    timer_enabled = bool(timer.get("enabled") and timer.get("unit"))
    if timer_enabled:
        ok, detail = _run_systemctl("disable", "--now", str(timer["unit"]))
        if not ok:
            return False, f"Could not disable {timer['unit']}: {detail}"

    claude_hook = manifest.get("claude_hook") or {}
    if claude_hook.get("path") and (claude_hook.get("added") or isinstance(claude_hook.get("auto_memory"), dict)):
        _remove_hook_json(
            Path(claude_hook["path"]),
            claude_hook["command"] if claude_hook.get("added") else None,
            bool(claude_hook.get("created_file")),
            auto_memory=claude_hook.get("auto_memory"),
        )

    git_ignore = manifest.get("git_ignore") or {}
    if git_ignore.get("added") and git_ignore.get("path") and git_ignore.get("line"):
        _remove_git_ignore(Path(git_ignore["path"]), git_ignore["line"], bool(git_ignore.get("created_file")))

    removed_unit = False
    raw_files = manifest.get("files") or {}
    items = raw_files.items() if isinstance(raw_files, dict) else ((f, None) for f in raw_files)
    for raw_file, expected_hash in items:
        target = Path(raw_file)
        if not target.is_file() or target.is_symlink():
            continue
        if expected_hash is not None and _sha256_file(target) != expected_hash:
            continue
        if target.name in SHARED_UNITS:
            removed_unit = True
        target.unlink()

    if removed_unit:
        ok, detail = _run_systemctl("daemon-reload")
        if not ok and timer_enabled:
            return False, f"Could not reload user systemd units: {detail}"

    agents = agents_dir()
    for sub in ("bin", "hooks", "prompts"):
        folder = agents / sub
        if folder.is_dir():
            try:
                folder.rmdir()
            except OSError:
                pass

    mpath.unlink(missing_ok=True)
    copy_msg = f" Copied {copied} Rook note file(s) back to {memory_dir()}." if copied else ""
    return True, f"Removed shared memory install. All memory notes remain in place.{copy_msg}"


def _dream_guard_main(argv):
    """PreToolUse hook entrypoint for Antigravity nightly memory tidy."""
    if len(argv) != 1 or not argv[0]:
        print(json.dumps({"decision": "deny", "reason": "Memory dream guard: missing allowed directory."}))
        return 0
    allowed_dir = argv[0]
    try:
        call = json.load(sys.stdin)
    except Exception as error:
        print(json.dumps({"decision": "deny", "reason": f"Memory dream guard: unreadable hook input: {error}"}))
        return 0
    if not isinstance(call, dict):
        print(json.dumps({"decision": "deny", "reason": "Memory dream guard: invalid hook payload."}))
        return 0
    tool_call = call.get("toolCall") if isinstance(call.get("toolCall"), dict) else {}
    tool = str(tool_call.get("name") or "").strip()
    args = tool_call.get("args")
    if args is None:
        args = {}
    allowed, reason = _dream_guard_decision(tool, args, allowed_dir)
    print(json.dumps({"decision": "allow" if allowed else "deny", "reason": "" if allowed else reason}))
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "dream-guard":
        sys.exit(_dream_guard_main(sys.argv[2:]))
    sys.exit("Usage: memory.py dream-guard <allowed_dir>")
