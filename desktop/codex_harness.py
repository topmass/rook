"""Rook's main agent on OpenAI's Codex CLI (`codex`), through its JSON-RPC app server (`codex app-server`).

The app server speaks JSON-RPC 2.0 (omitting `"jsonrpc": "2.0"` on the wire) as JSONL over stdio. This harness opens
one ephemeral thread per `codex app-server` child and translates Codex's items and server requests into the Claude Code
stream-json shapes listed in `desktop/harness.py`, so Rook's reader, watcher, overlay tables, and journal stay
unchanged.

Nothing of the conversation stays on persistent disk, by the owner's rule: each request carries a screenshot of their screen.
Codex is launched with `CODEX_HOME` pointed at a private folder under `desk.runtime_dir()` (memory-backed tmpfs on
Linux) or a private `0700` temp folder when no runtime directory is available (such as macOS), with
`history.persistence = "none"`. Threads start with `ephemeral: true` (no rollout files or thread history database),
images travel inline as `data:image/jpeg;base64,...` URLs (no image file is ever written), and the private `CODEX_HOME`
is removed at each launch and when the session ends. Credentials (`auth.json` and `.credentials.json`) are symlinked
from the user's real Codex folder and never copied, read, or printed. Verified on `codex-cli 0.169.0`: Codex resolves
the `auth.json` symlink and atomically replaces the target file in the real `~/.codex/` directory while leaving the
symlink intact. Any provider secret stored inside the person's own `config.toml` is deliberately copied into the
private `config.toml` (mode `0600`, in memory on Linux, wiped at session end and at the next launch).

Rook adds no permission layer of its own. The default mode is `inherit`, which starts from the person's own
`config.toml` and passes no sandbox or approval overrides so their Codex settings rule. Plain modes (`careful`,
`automatic`, `full`, and legacy `rook`) map to Codex's native `sandbox` and `approvalPolicy`. Every server-initiated
approval or user-input prompt becomes a Rook card with a globally unique id, shown one at a time in arrival order.
Rook never sends "allow always" (`acceptForSession`, policy amendments, or session-scoped permission grants).

Self-check: `~/.local/share/rook/venv/bin/python desktop/codex_harness.py --check`
"""
import asyncio
import base64
import copy
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

import desk
from harness import Harness, bare_skill_names, plugin_user_skills, rook_skills_dir, skill_sources
import plugin_loader
import settings as rook_settings

OWNER = rook_settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.

ROOT = Path(__file__).resolve().parent.parent
# Optional override for tests; when None, resolve_home() picks $XDG_RUNTIME_DIR/rook-codex (or /run/user/<uid>)
# on Linux, or a private 0700 temp folder when no runtime directory is available (e.g. macOS).
HOME = None
AGENTS = plugin_loader.host_skill_dirs()["agents"].parent
GEMINI_SKILLS = plugin_loader.host_skill_dirs()["gemini"]

# Rook's effort names (settings.EFFORTS) map 1:1 to Codex reasoningEffort levels.
EFFORTS = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max"}

# Rook permission_mode values (matching public/personal-settings) -> Codex native (sandbox, approvalPolicy) pairs.
# "inherit" passes no overrides and keeps the person's own ~/.codex/config.toml permission and profile settings.
PERMISSION_MODES = {
    "inherit": None,
    "careful": {"sandbox": "read-only", "approvalPolicy": "on-request"},
    "automatic": {"sandbox": "workspace-write", "approvalPolicy": "on-request"},
    "full": {"sandbox": "danger-full-access", "approvalPolicy": "never"},
    "rook": {"sandbox": "danger-full-access", "approvalPolicy": "never"},
}
DEFAULT_PERMISSIONS = rook_settings.PERMISSION_MODE  # full, as settings.py says.

# Watchdog: a turn ends when Codex sends nothing for 10 minutes with a turn open and no card waiting on the owner.
STALL_SECONDS = 600
STALLED = "Codex stopped answering, so I stopped that turn. Ask again."
STALE_SECONDS = 5

# skills/ edits: Codex loads configured MCP tools up front (no ToolSearch) and exposes them by server + tool.
SKILLS = [
    ("delegate/SKILL.md", "They appear as `mcp__t3__t3_thread_list` and so on",
     "They appear as `t3_thread_list` and so on on the `t3` MCP server"),
    ("delegate/SKILL.md", "Most load on first use: find one with ToolSearch, such as `select:mcp__t3__t3_thread_list`.",
     "They are already loaded from the `t3` MCP server when T3 is signed in."),
    ("delegate/SKILL.md", "when ToolSearch cannot find the tools", "when the T3 tools are missing"),
    ("delegate/references/t3-command.md", "when ToolSearch cannot find the T3 tools", "when the T3 tools are missing"),
    ("delegate/references/t3-tools.md", "Rook's Claude session", "Rook's Codex session"),
    ("delegate/references/t3-tools.md", "`mcp__t3__<name>`", "`<name>` on the `t3` MCP server"),
    ("wow/SKILL.md", "Find one that is not loaded yet with ToolSearch.",
     "They are already loaded from the `wow` MCP server."),
]
OPTIONAL_SKILLS = frozenset({"wow/SKILL.md"})
PROMPT = [
    ("a full Claude Code session", "a full Codex session"),
    ("that your session start message names", "that the session start lines at the end of this prompt name"),
]
SETUP = [(" When a tool you used before is missing, search for it again.", "")]
CLAUDE_ONLY = ("${CLAUDE_", "mcp__", "ToolSearch")

_TOML_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}


def user_codex_home():
    """Return the user's real Codex home folder, honoring CODEX_HOME."""
    return plugin_loader.host_skill_dirs()["codex"].parent


def resolve_home(home=None):
    """Return the private CODEX_HOME path: explicit override, runtime dir on tmpfs, or a private 0700 temp folder."""
    if home is not None:
        return Path(home)
    if HOME is not None:
        return Path(HOME)
    if os.environ.get("XDG_RUNTIME_DIR") or (desk.IS_LINUX and Path(f"/run/user/{os.getuid()}").is_dir()):
        return desk.runtime_dir() / "rook-codex"
    return Path(tempfile.mkdtemp(prefix="rook-codex-"))


def permission_mode(saved=None):
    """Return Rook's permission_mode: inherit, careful, automatic, full, or rook.

    Uses settings.permission_mode_in_force when present (public/personal-settings), otherwise reads
    `permission_mode` directly from saved/settings.json with DEFAULT_PERMISSIONS, full, as the fallback.
    """
    if saved is None:
        parsed = rook_settings.read_settings()[0]
        if hasattr(rook_settings, "permission_mode_in_force"):
            mode = rook_settings.permission_mode_in_force(parsed)[0]
        else:
            raw = {}
            try:
                loaded = json.loads(rook_settings.CONFIG.read_text())
                if isinstance(loaded, dict):
                    raw = loaded
            except (OSError, ValueError):
                pass
            mode = raw.get("permission_mode")
    else:
        data = saved if isinstance(saved, dict) else {}
        if hasattr(rook_settings, "permission_mode_in_force"):
            mode = rook_settings.permission_mode_in_force(data)[0]
        else:
            mode = data.get("permission_mode")
    value = str(mode or "").strip().lower()
    return value if value in PERMISSION_MODES else DEFAULT_PERMISSIONS


def send(process, message):
    process.stdin.write((json.dumps(message) + "\n").encode())


def stream(kind, **fields):
    return {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": kind, **fields}}


def brief(text, limit=200):
    """Shorten Codex error text cleanly at a word boundary for speech."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:.") + "..."


def toml_string(text):
    """Encode a Python str as a valid TOML basic string (UTF-8 literal for non-ASCII, never UTF-16 surrogates)."""
    out = ['"']
    for ch in text:
        if ch in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[ch])
        else:
            code = ord(ch)
            if code < 0x20 or code == 0x7F:
                out.append(f"\\u{code:04x}")
            else:
                out.append(ch)
    out.append('"')
    return "".join(out)


def toml_key(key):
    """Format a TOML key, quoting as a valid TOML basic string when needed."""
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else toml_string(key)


def toml_value(value):
    """Serialize a Python scalar, date/time, list, or inline dict to valid TOML inline syntax."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return "nan"
        if value == float("inf"):
            return "inf"
        if value == float("-inf"):
            return "-inf"
        return repr(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, str):
        return toml_string(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        items = [f"{toml_key(str(k))} = {toml_value(v)}" for k, v in value.items() if v is not None]
        return "{ " + ", ".join(items) + " }" if items else "{}"
    raise TypeError(f"Unsupported TOML value: {type(value).__name__}")


def _is_table_array(value):
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def dump_toml(data):
    """Serialize a nested dict (as produced by tomllib.loads) into a clean, valid TOML document."""
    lines = []

    def emit_table(mapping, path):
        scalars, subtables, arrays = [], [], []
        for k, v in mapping.items():
            if v is None:
                continue
            if isinstance(v, dict):
                subtables.append((str(k), v))
            elif _is_table_array(v):
                arrays.append((str(k), v))
            else:
                scalars.append((str(k), v))
        if path and (scalars or (not subtables and not arrays)):
            if lines:
                lines.append("")
            lines.append("[" + ".".join(toml_key(part) for part in path) + "]")
        for k, v in scalars:
            lines.append(f"{toml_key(k)} = {toml_value(v)}")
        for k, sub in subtables:
            emit_table(sub, (*path, k))
        for k, items in arrays:
            header = "[[" + ".".join(toml_key(part) for part in (*path, k)) + "]]"
            for item in items:
                if lines:
                    lines.append("")
                lines.append(header)
                nested_tables, nested_arrays = [], []
                for ik, iv in item.items():
                    if iv is None:
                        continue
                    if isinstance(iv, dict):
                        nested_tables.append((str(ik), iv))
                    elif _is_table_array(iv):
                        nested_arrays.append((str(ik), iv))
                    else:
                        lines.append(f"{toml_key(str(ik))} = {toml_value(iv)}")
                for nk, nv in nested_tables:
                    emit_table(nv, (*path, k, nk))
                for nk, nitems in nested_arrays:
                    sub_header = "[[" + ".".join(toml_key(part) for part in (*path, k, nk)) + "]]"
                    for nitem in nitems:
                        lines.append("")
                        lines.append(sub_header)
                        for sk, sv in nitem.items():
                            if sv is not None:
                                lines.append(f"{toml_key(str(sk))} = {toml_value(sv)}")

    emit_table(data, ())
    return "\n".join(lines).lstrip("\n") + "\n"


def edit(text, table, where):
    for old, new in table:
        if old not in text:
            raise ValueError(f"{where} no longer holds {old!r}. Update the table in {__file__}.")
        text = text.replace(old, new)
    return text


def render_skills(target, source=None, wow=False, table=None, banned=CLAUDE_ONLY):
    """Copy skills/ (plus wow/skills when wow is on and present) into target, rendered for Codex, or for
    another agent with its own edit table and banned words."""
    sources = skill_sources(wow=wow, plugin_skills=source)
    include_wow = any((folder / "wow/SKILL.md").is_file() for folder in sources)
    edits = {}
    for path, old, new in SKILLS if table is None else table:
        if path in OPTIONAL_SKILLS and not include_wow:
            continue
        edits.setdefault(path, []).append((old, new))
    for folder in sources:
        for file in sorted(folder.rglob("*")):
            rel = file.relative_to(folder)
            if not file.is_file() or "__pycache__" in rel.parts:
                continue
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if file.suffix != ".md":
                shutil.copyfile(file, out)
                continue
            text = (file.read_text().replace("${CLAUDE_SKILL_DIR}", str(folder / rel.parts[0]))
                    .replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT / "plugin")))
            if rel.name == "SKILL.md":  # Claude Code frontmatter; Codex ignores/doesn't enforce allowed-tools.
                text = re.sub(r"(?m)^allowed-tools:.*\n", "", text, count=1)
            text = bare_skill_names(edit(text, edits.pop(str(rel), []), f"{folder.name}/{rel}"))  # As Codex and Pi list them.
            if left := [name for name in banned if name in text]:
                raise ValueError(f"{folder.name}/{rel} still names {left}. Add an entry to SKILLS in {__file__}.")
            out.write_text(rook_settings.render(text))
    if edits:
        raise ValueError(f"skills/ has no {sorted(edits)}. Update SKILLS in {__file__}.")


def _has_surrogate(text):
    """Return True if text contains a lone UTF-16 surrogate (e.g. non-UTF-8 filename via surrogateescape)."""
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def read_user_config(user_home):
    """Read settings from the user's ~/.codex/config.toml.

    A missing file returns {}. An existing file that cannot be read, is invalid UTF-8, or fails TOML parsing
    logs one line naming the file and position (never its contents) and raises ValueError so Rook falls back
    instead of silently starting Codex on looser built-in defaults.
    """
    path = Path(user_home) / "config.toml"
    if not path.exists() and not path.is_symlink():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Could not read {path} (invalid UTF-8 at byte {exc.start})."
        print(f"codex: {msg}", file=sys.stderr)
        raise ValueError(msg) from exc
    except OSError as exc:
        msg = f"Could not read {path} ({exc.strerror or type(exc).__name__})."
        print(f"codex: {msg}", file=sys.stderr)
        raise ValueError(msg) from exc
    try:
        return tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        lineno, colno = getattr(exc, "lineno", None), getattr(exc, "colno", None)
        if lineno is not None and colno is not None:
            pos = f"line {lineno}, column {colno}"
        elif found := re.search(r"at (line \d+, column \d+|end of document)", str(exc)):
            pos = found.group(1)
        else:
            pos = "parse error"
        msg = f"Could not parse {path} ({pos})."
        print(f"codex: {msg}", file=sys.stderr)
        raise ValueError(msg) from exc


def disabled_host_skills(agents_dir=None, allow=None):
    """Return paths of host ~/.agents/skills/**/SKILL.md files to hide from Codex, keeping the allowed host skills
    (by default the active plugins')."""
    allowed = frozenset(plugin_loader.host_skills_allow() if allow is None else allow)
    root = (AGENTS / "skills") if agents_dir is None else Path(agents_dir) / "skills"
    if not root.is_dir():
        return []
    paths = []
    try:
        for md in sorted(root.rglob("SKILL.md")):
            if md.parent.name in allowed:
                continue
            text = str(md)
            if _has_surrogate(text):
                print(f"codex: skipping host skill with non-UTF-8 path: {os.fsencode(md)!r}", file=sys.stderr)
                continue
            paths.append(text)
    except OSError:
        return []
    return paths


def clear(home=None):
    """Remove Rook's private CODEX_HOME. shutil.rmtree unlinks symlinks without touching targets."""
    target = home if home is not None else HOME
    if target is not None:
        shutil.rmtree(Path(target), ignore_errors=True)


def build_home(servers, denied=(), mode=None, home=None, user_home=None, plugin_skills=None,
               user_rook_skills=None, agents_dir=None, wow=None, host_skills=None):
    """Build Rook's private CODEX_HOME and return its Path.

    Starts from the person's full ~/.codex/config.toml and overrides only the keys Rook must own:
    `agents.enabled`, `features.apps`, `features.browser_use`, `history.persistence`, `mcp_servers`,
    `skills.config` (hiding unrelated host skills), plus `sandbox_mode`/`approval_policy` (and clearing
    `profile`) only in non-`inherit` modes. Never writes to the user's real `~/.codex`.
    """
    real_home = user_codex_home() if user_home is None else Path(user_home)
    # Parse user config before creating or wiping the private home so a broken config fails cleanly.
    cfg = copy.deepcopy(read_user_config(real_home))
    target = resolve_home(home)
    agents = AGENTS if agents_dir is None else Path(agents_dir)
    mode = permission_mode() if mode is None else mode

    clear(target)
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.chmod(0o700)

    # Link credentials and user execpolicy rules without copying or inspecting secrets.
    for name in ("auth.json", ".credentials.json"):
        src = real_home / name
        if src.exists():
            (target / name).symlink_to(src)
    rules_src = real_home / "rules"
    if rules_src.is_dir():
        (target / "rules").symlink_to(rules_src)

    # Global instructions: copy (never symlink) so Codex cannot edit the owner's file.
    for candidate in (agents / "AGENTS.md", real_home / "AGENTS.md"):
        if candidate.is_file():
            shutil.copyfile(candidate, target / "AGENTS.md")
            break

    # Skills: render Rook's skills/ (plus wow/skills only with --wow), link ~/.config/rook/skills, and the
    # active plugins' allowed host skills.
    skills_dir = target / "skills"
    skills_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    render_skills(skills_dir, source=plugin_skills, wow=("wow" in (servers or {}) if wow is None else wow))
    custom_dir = rook_skills_dir() if user_rook_skills is None else Path(user_rook_skills)
    if custom_dir.is_dir():
        try:
            entries = sorted(custom_dir.iterdir())
        except OSError:
            entries = []
        for entry in entries:
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            if _has_surrogate(entry.name):
                print(f"codex: skipping custom skill with non-UTF-8 name: {os.fsencode(entry.name)!r}", file=sys.stderr)
                continue
            dest = skills_dir / entry.name
            if not dest.exists() and not dest.is_symlink():
                dest.symlink_to(entry)
    for folder in plugin_user_skills():  # Active user plugins' skills, linked as the user's own are.
        try:
            entries = sorted(folder.iterdir())
        except OSError as exc:  # The folder went away after discovery: skip it, as the Claude path does.
            print(f"codex: skipping plugin skills in {folder}: {exc.strerror or exc!r}", file=sys.stderr)
            continue
        for entry in entries:
            dest = skills_dir / entry.name
            if (entry / "SKILL.md").is_file() and not dest.exists() and not dest.is_symlink():
                dest.symlink_to(entry)
    allowed_host = tuple(dict.fromkeys(plugin_loader.host_skills_allow() if host_skills is None else host_skills))
    for name in allowed_host:
        if (agents / "skills" / name / "SKILL.md").is_file():
            continue
        for extra in (GEMINI_SKILLS / name, real_home / "skills" / name):
            dest = skills_dir / name
            if (extra / "SKILL.md").is_file() and not dest.exists() and not dest.is_symlink():
                dest.symlink_to(extra)
                break

    if mapping := PERMISSION_MODES.get(mode):
        cfg["sandbox_mode"] = mapping["sandbox"]
        cfg["approval_policy"] = mapping["approvalPolicy"]
        cfg.pop("profile", None)  # Do not let a user profile override Rook's explicit plain mode.

    agents_cfg = cfg.get("agents") if isinstance(cfg.get("agents"), dict) else {}
    agents_cfg["enabled"] = False
    cfg["agents"] = agents_cfg

    features_cfg = cfg.get("features") if isinstance(cfg.get("features"), dict) else {}
    features_cfg["apps"] = False
    features_cfg["browser_use"] = False
    cfg["features"] = features_cfg

    history_cfg = cfg.get("history") if isinstance(cfg.get("history"), dict) else {}
    history_cfg["persistence"] = "none"
    cfg["history"] = history_cfg

    # Replace mcp_servers with Rook's own servers only so unrelated user servers never start inside Rook.
    plugin_denied = {spec["name"]: spec["denied_tools"] for spec in plugin_loader.servers()}
    mcp_cfg = {}
    for name, server in (servers or {}).items():
        if not isinstance(server, dict):
            continue
        entry = {}
        if "command" in server:
            entry["command"] = server["command"]
            if server.get("args"):
                entry["args"] = list(server["args"])
            if server.get("env"):
                entry["env"] = dict(server["env"])
        elif "url" in server:
            entry["url"] = server["url"]
        if name == "t3" and denied:
            entry["disabled_tools"] = list(denied)
        elif plugin_denied.get(name):
            entry["disabled_tools"] = list(plugin_denied[name])
        mcp_cfg[name] = entry
    if mcp_cfg:
        cfg["mcp_servers"] = mcp_cfg
    else:
        cfg.pop("mcp_servers", None)

    hidden = disabled_host_skills(agents, allow=allowed_host)
    if hidden:
        skills_cfg = cfg.get("skills") if isinstance(cfg.get("skills"), dict) else {}
        existing = [e for e in (skills_cfg.get("config") or []) if isinstance(e, dict)]
        seen_paths = {e.get("path") for e in existing if isinstance(e.get("path"), str)}
        for path in hidden:
            if path not in seen_paths:
                existing.append({"path": path, "enabled": False})
        skills_cfg["config"] = existing
        cfg["skills"] = skills_cfg

    cfg_path = target / "config.toml"
    with os.fdopen(os.open(cfg_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(dump_toml(cfg))
    return target


def memory(workspace, agents_dir=None):
    """Run the owner's session start hook (shared memory) if present, returning its stdout or ''."""
    agents = AGENTS if agents_dir is None else Path(agents_dir)
    hook = agents / "hooks/machine-context.sh"
    if not hook.is_file():
        hook = agents / "hooks/memory-context.sh"
    if not hook.is_file():
        return ""
    try:
        done = subprocess.run(["bash", str(hook)], cwd=workspace, timeout=10,
                              input=json.dumps({"cwd": str(workspace)}), capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip()


def adapt_prompt(text, workspace, agents_dir=None):
    """Adapt Rook's system prompt for Codex and append shared session-start lines when present."""
    adapted = edit(text, PROMPT, "Rook's system prompt")  # Rendered already in rook.py, where its data passes as it is.
    if lines := memory(workspace, agents_dir=agents_dir):  # The hook's lines are data, passed as they are.
        adapted += rook_settings.render(f"\n\nSession start lines, from {OWNER}'s session start hook:\n") + lines
    return adapted


def adapt_setup(wow):
    """Adapt Claude's setup turn text for Codex (MCP tools are already loaded at thread start)."""
    import harness as harness_mod
    return edit(harness_mod.Claude().setup({}, [], wow), SETUP, "Claude's setup turn")


def mcp_output_text(item):
    """Extract plain text from a Codex mcpToolCall item's result or error."""
    error = item.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    result = item.get("result")
    if not isinstance(result, dict):
        return ""
    parts = []
    for entry in result.get("content") or ():
        if isinstance(entry, dict) and isinstance(entry.get("text"), str):
            parts.append(entry["text"])
        elif isinstance(entry, str):
            parts.append(entry)
    if parts:
        return "\n".join(parts)
    if result.get("structuredContent") is not None:
        return json.dumps(result["structuredContent"])
    return ""


def mcp_status_value(entry):
    """Map one Codex McpServerStatus entry to Rook's system/init status string."""
    runtime = entry.get("runtimeStatus")
    auth = entry.get("authStatus")
    tools_err = str(entry.get("toolsError") or "").lower()
    if runtime == "authenticationRequired" or auth == "notLoggedIn" or "auth required" in tools_err:
        return "needs-auth"
    if runtime == "connected":
        return "connected"
    if runtime in ("failed", "cancelled", "disabled"):
        return "failed"
    if entry.get("tools") or auth in ("oAuth", "bearerToken"):
        return "connected"
    return "failed" if tools_err else "connected"


def signed_out_error(error):
    """Whether a JSON-RPC error from Codex means it is not signed in."""
    if not isinstance(error, dict):
        return False
    msg = str(error.get("message") or "").lower()
    return any(tok in msg for tok in ("not signed in", "not logged in", "authentication required",
                                      "unauthenticated", "login required", "codex login"))


def user_input_answer(params, allowed, answers):
    """Build Codex ToolRequestUserInputResponse from Rook's AskUserQuestion answers dict."""
    if not allowed or not isinstance(answers, dict):
        return {"answers": {}}
    out = {}
    for q in params.get("questions") or ():
        if not isinstance(q, dict) or not q.get("id"):
            continue
        qid = q["id"]
        qtext = q.get("question") or ""
        raw = answers.get(qid)
        if raw is None:
            raw = answers.get(qtext)
        if raw is None and len(answers) == 1 and len(params.get("questions") or ()) == 1:
            raw = next(iter(answers.values()))
        if raw is None:
            continue
        vals = [str(v) for v in raw] if isinstance(raw, list) else [str(raw)]
        opts = [o.get("label") for o in (q.get("options") or ()) if isinstance(o, dict) and isinstance(o.get("label"), str)]
        if opts:
            by_low = {o.lower(): o for o in opts}
            vals = [by_low.get(v.strip().lower(), v) for v in vals]
        out[qid] = {"answers": vals}
    return {"answers": out}


class Codex(Harness):
    name = "Codex"  # In "Codex closed" and error messages.
    short = "Codex"  # In permission cards: "Codex requests Bash."
    # Verified on codex-cli 0.169.0: item/started fires before approval and before tool execution.
    marks_tools_first = True
    model, effort = "gpt-6.2-sol", "low"  # Fast voice default; overridden by agent_model / agent_effort.
    setup_quiet, setup_limit = 45, 90
    setup_problem = None

    def __init__(self, model=None, effort=None):
        super().__init__(model, effort)
        self.process, self.heard = None, 0
        self.home = None

    def signin_status(self, env=None):
        """codex login status: exit 0 is signed in; a failure that says "not logged in" is signed out; anything
        else cannot be told. The output is dropped."""
        from harness import signin_sentence, status_run
        program = shutil.which("codex", path=(env if env is not None else os.environ).get("PATH"))
        ran = program and status_run([program, "login", "status"], env=env)
        if not ran:
            return "unknown", None
        if ran[0] == 0:
            return "in", None
        if re.search(r"not (logged|signed) in", ran[1], re.I):
            return "out", signin_sentence(self.name, f"{program} login")
        return "unknown", None

    def ready(self):
        """Return None when `codex` is installed, else one short sentence on why it cannot start."""
        if shutil.which("codex"):
            return None
        print("codex: not ready: codex is not installed.", file=sys.stderr)
        return "codex is not installed. Install the Codex CLI, or ask Rook to use Claude Code."

    def command(self, prompt, servers, session, plugin, denied):
        """Build Rook's private CODEX_HOME and return the argv to launch `codex app-server`."""
        self.prompt = prompt
        self.servers = dict(servers or {})
        self.denied = tuple(denied or ())
        self.mode = permission_mode()
        if self.home is not None:
            clear(self.home)
        self.home = build_home(self.servers, denied=self.denied, mode=self.mode)
        return ["env", f"CODEX_HOME={self.home}", f"BROWSER={desk.false_exe()}",
                "codex", "app-server", "--listen", "stdio://"]

    def setup(self, start, later, wow):
        """Return the setup turn text. Codex loads MCP tool catalogs at thread start."""
        return adapt_setup(wow)

    def begin(self, process, session, uuid, text):
        """Start the app-server handshake and queue the setup turn until the ephemeral thread exists."""
        self.process = process
        self.run_id = secrets.token_hex(6)
        self.next_id = 0
        self.calls = {}  # rpc_id -> (kind, payload)
        self.thread_id = None
        self.outbox = [(uuid, [{"type": "text", "text": text}], False)]
        self.queue = []  # Queued turns while a turn is active: [(uuid, input_items, steer)]
        self.active_turn = None  # uuid of the currently running turn
        self.active_turn_id = None  # Codex turnId once turn/start or turn/started arrives
        self.steered_uuids = []  # Rook uuids folded into active_turn via turn/steer
        self.cancel_on_start = False  # interrupt() arrived before turn/start returned turnId
        self.interrupting_turns = set()  # Codex turnIds we sent turn/interrupt for
        self.abandoned_turns = set()  # Codex turnIds ended by the stall watchdog
        self.abandoned_pending = False  # True while an abandoned turn has not yet returned turn/completed
        self.stale_until = 0.0
        self.texting = False
        self.answer = ""
        self.streamed_items = set()  # itemIds that already streamed deltas
        self.active_tools = {}  # itemId -> (claude_tool_name, item_dict)
        # Every open ask, by the card id Rook knows. Each goes to Rook's own card queue as it comes, which shows one
        # at a time; an answer goes to exactly its request.
        self.asks = {}  # request_id -> (rpc_id, method, params)
        self.withdrawn = []  # Card request_ids cancelled from Rook's side
        self._wake = None  # Lazy asyncio.Event to wake read() immediately when a card promotes or withdraws
        self.mcp_statuses = {}  # server_name -> status from startupStatus notifications
        self.init_emitted = False
        self.last_error = None
        self.usage = {}
        self.context = 0
        self.began = self.heard = self.turn_began = time.monotonic()
        self.first_words = None
        self.setup_uuid, self.setup_done, self.stages = uuid, False, {}
        self.setup_problem = None
        self.cwd = desk.process_cwd(getattr(process, "pid", None), getattr(self, "workspace", None))
        self.call("initialize", {
            "clientInfo": {"name": "rook", "title": "Rook", "version": "1"},
            "capabilities": {"experimentalApi": True},
        })

    def turn(self, process, session, uuid, text, shots, steer):
        """Send one user turn with inline JPEG data URLs (no image files on disk). steer uses turn/steer."""
        items = [{"type": "image", "url": "data:image/jpeg;base64," + base64.b64encode(shot).decode()}
                 for shot in shots] + [{"type": "text", "text": text}]
        # If an approval card (or held queue) is open when a new request arrives, decline every one so Codex proceeds.
        self._decline_all_asks(process, cancel=False, withdraw=True)
        if not self.thread_id or not self.init_emitted:
            self.outbox.append((uuid, items, steer))
            return
        if self.active_turn is not None:
            if steer and self.active_turn_id and self.active_turn_id not in self.interrupting_turns:
                self._send_steer(uuid, items)
            else:
                self.queue.append((uuid, items, steer))
        else:
            self._start_turn(uuid, items)

    def interrupt(self, process):
        """Cancel the running turn and any queued turns, and cancel every open or held approval card."""
        self.outbox.clear()
        self.queue.clear()
        if self.thread_id and self.active_turn_id:
            self.interrupting_turns.add(self.active_turn_id)
            self.stale_until = time.monotonic() + STALE_SECONDS
            self.call("turn/interrupt", {"threadId": self.thread_id, "turnId": self.active_turn_id})
        elif self.active_turn is not None:
            self.cancel_on_start = True
            self.stale_until = time.monotonic() + STALE_SECONDS
        self._decline_all_asks(process, cancel=True, withdraw=False)

    def permit(self, process, ask, allowed, answers=None, reason=None):
        """Answer the request this card names, once. Codex's decline carries no reason, so reason goes unsaid."""
        entry = self.asks.pop(ask.get("request_id"), None)
        if entry is None:
            return
        rpc, method, params = entry
        self.heard = time.monotonic()
        self._reply_ask(process, rpc, method, params, allowed=allowed, answers=answers, cancel=False)

    async def read(self, messages):
        """Translate Codex app-server JSON-RPC messages into Rook's stream-json dicts."""
        process, waiting = self.process, None
        self._wake = asyncio.Event()
        stream_it = messages.__aiter__()
        try:
            while True:
                for converted in self.flush():
                    yield converted
                watching = self.active_turn is not None and not self._has_open_ask()
                limit = min(1, max(0.1, self.heard + STALL_SECONDS - time.monotonic())) if watching else 1
                waiting = waiting or asyncio.ensure_future(stream_it.__anext__())
                wake_task = asyncio.ensure_future(self._wake.wait())
                done, _ = await asyncio.wait({waiting, wake_task}, timeout=limit, return_when=asyncio.FIRST_COMPLETED)
                if not wake_task.done():
                    wake_task.cancel()
                else:
                    self._wake.clear()
                if waiting not in done:
                    if watching and not self._has_open_ask() and time.monotonic() - self.heard >= STALL_SECONDS:
                        for converted in self.stalled():
                            yield converted
                    continue
                try:
                    message = waiting.result()
                except StopAsyncIteration:
                    break
                waiting = None
                self.heard = time.monotonic()
                if not self.setup_done:
                    self.trace(message)
                for converted in self.flush():
                    yield converted
                prepared = await self.prepare(message)
                for converted in self.flush():
                    yield converted
                for converted in self.handle(message, prepared):
                    if (converted["type"] == "result" and not self.setup_done
                            and self.setup_uuid in (converted.get("user_message_uuids") or ())):
                        self.setup_done = True
                        print(f"codex: setup answered {self.progress()}", file=sys.stderr)
                    yield converted
        finally:
            if waiting is not None:
                waiting.cancel()
            self._wake = None
            if self.process is process:
                self._decline_all_asks(process, cancel=True, withdraw=False, ignore_io=True)
            if self.process is process and not self.setup_done:
                print(f"codex: setup ended unanswered {self.progress()}", file=sys.stderr)
            if self.process is process and self.home is not None:
                clear(self.home)

    # ---- internal helpers ----

    def _has_open_ask(self):
        return bool(self.asks)

    def _signal_wake(self):
        if self._wake is not None:
            self._wake.set()

    def _decline_all_asks(self, process, cancel, withdraw, ignore_io=False):
        """Decline or cancel every open ask in arrival order. withdraw also takes each card back from Rook."""
        entries = list(self.asks.items())
        self.asks.clear()
        if withdraw:
            self.withdrawn.extend(request_id for request_id, _ in entries)
        for _, (rpc, method, params) in entries:
            try:
                self._reply_ask(process, rpc, method, params, allowed=False, cancel=cancel)
            except OSError:
                if not ignore_io:
                    raise
        if entries:
            self.heard = time.monotonic()
            self._signal_wake()

    def call(self, method, params, kind=None, payload=None):
        self.next_id += 1
        self.calls[self.next_id] = (kind or method, payload)
        send(self.process, {"id": self.next_id, "method": method, "params": params})
        return self.next_id

    def _start_turn(self, uuid, items):
        self.active_turn = uuid
        self.active_turn_id = None
        self.steered_uuids = []
        self.cancel_on_start = False
        self.answer = ""
        self.last_error = None
        self.streamed_items.clear()
        self.active_tools.clear()
        self.heard = self.turn_began = time.monotonic()
        self.first_words = None
        if uuid == self.setup_uuid:
            self.stages.setdefault("setup sent", round(time.monotonic() - self.began, 1))
        params = {"threadId": self.thread_id, "input": items}
        if self.effort and self.effort in EFFORTS:
            params["effort"] = EFFORTS[self.effort]
        self.call("turn/start", params, "turn/start", uuid)

    def _send_steer(self, uuid, items):
        self.steered_uuids.append(uuid)
        self.call("turn/steer", {
            "threadId": self.thread_id,
            "expectedTurnId": self.active_turn_id,
            "input": items,
        }, "turn/steer", (uuid, items))

    def _reply_ask(self, process, rpc, method, params, allowed, answers=None, cancel=False):
        """Send a single-use approval or user-input reply. Never sends allow-always or session scope."""
        if method == "item/commandExecution/requestApproval":
            decision = "cancel" if cancel else ("accept" if allowed else "decline")
            result = {"decision": decision}
        elif method == "item/fileChange/requestApproval":
            decision = "cancel" if cancel else ("accept" if allowed else "decline")
            result = {"decision": decision}
        elif method in ("execCommandApproval", "applyPatchApproval"):
            decision = ("abort" if cancel else
                        "approved" if allowed else {"denied": {"rejection": "The user declined this request."}})
            result = {"decision": decision}
        elif method == "item/permissions/requestApproval":
            granted = (params.get("permissions") or {}) if (allowed and not cancel) else {}
            result = {"permissions": granted, "scope": "turn"}
        elif method == "item/tool/requestUserInput":
            result = {"answers": {}} if cancel else user_input_answer(params, allowed, answers)
        elif method == "mcpServer/elicitation/request":
            action = "cancel" if cancel else ("accept" if allowed else "decline")
            result = {"action": action, "content": None}
        else:
            send(process, {"id": rpc, "error": {"code": -32601, "message": "Rook does not support this request."}})
            return
        send(process, {"id": rpc, "result": result})

    def close_text(self):
        if self.texting:
            self.texting = False
            yield stream("content_block_stop")

    def flush(self):
        for request_id in self.withdrawn:
            yield {"type": "control_cancel_request", "request_id": request_id}
        self.withdrawn.clear()

    def stale(self):
        return time.monotonic() < self.stale_until

    def turn_line(self):
        """One journal line per turn: speed and token counts, never user content."""
        last = (self.usage or {}).get("last") or {}
        print(f"codex: turn {round(time.monotonic() - self.turn_began, 1)} s, first output "
              f"{'none' if self.first_words is None else round(self.first_words, 1)} s; context {self.context} tokens; "
              f"input {last.get('inputTokens')}, cached {last.get('cachedInputTokens')}, "
              f"reasoning {last.get('reasoningOutputTokens')}, output {last.get('outputTokens')}",
              file=sys.stderr)

    def trace(self, message):
        at = round(time.monotonic() - self.began, 1)
        kind = message.get("method") or self.calls.get(message.get("id"), (None,))[0]
        stage = {"initialize": "initialized", "account/read": "account checked", "thread/start": "thread started",
                 "mcpServerStatus/list": "mcp checked", "turn/started": "turn started",
                 "item/agentMessage/delta": "first text", "turn/completed": "answer"}.get(kind)
        if stage and "error" in message:
            stage = f"{kind} failed ({(message.get('error') or {}).get('code')})"
        if stage:
            self.stages.setdefault(stage, at)

    def progress(self):
        stages = ", ".join(f"{stage} {at}" for stage, at in self.stages.items()) or "nothing from codex"
        return f"after {round(time.monotonic() - self.began, 1)} s: {stages}"

    def stalled(self):
        """End the active turn after STALL_SECONDS of silence; kill a wedged process on a second stall."""
        uuids = ([self.active_turn] if self.active_turn else []) + list(self.steered_uuids)
        wedged = self.abandoned_pending
        print(f"codex: no word from codex for {STALL_SECONDS} s with a turn open; the turn ends"
              + ("; codex is wedged, so it ends too" if wedged else ""), file=sys.stderr)
        if self.thread_id and self.active_turn_id:
            self.abandoned_turns.add(self.active_turn_id)
            self.interrupting_turns.add(self.active_turn_id)
            self.call("turn/interrupt", {"threadId": self.thread_id, "turnId": self.active_turn_id})
        self.abandoned_pending = True
        self.stale_until = time.monotonic() + STALE_SECONDS
        self.active_turn = None
        self.active_turn_id = None
        self.steered_uuids = []
        self.answer = ""
        self.active_tools.clear()
        yield from self.close_text()
        yield {"type": "result", "user_message_uuids": uuids, "result": STALLED,
               "terminal_reason": "stalled", "is_error": False, "errors": []}
        if wedged:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass
        elif self.queue:
            next_uuid, next_items, _ = self.queue.pop(0)
            self._start_turn(next_uuid, next_items)

    def developer_instructions(self):
        return adapt_prompt(self.prompt, self.cwd)

    async def prepare(self, message):
        """Run blocking hook lookup off the event loop before starting the Codex thread."""
        if not message.get("method") and message.get("id") in self.calls:
            kind = self.calls[message["id"]][0]
            if kind == "account/read" and not message.get("error"):
                return {"instructions": await asyncio.to_thread(self.developer_instructions)}
        return {}

    def handle(self, message, prepared=None):
        prepared = prepared or {}
        method, rpc = message.get("method"), message.get("id")
        if method and rpc is not None:
            yield from self.server_request(rpc, method, message.get("params") or {})
        elif method:
            yield from self.notification(method, message.get("params") or {})
        elif rpc in self.calls:
            yield from self.answered(*self.calls.pop(rpc), rpc, message, prepared)

    def _emit_init(self, entries=None):
        """Emit system/init with MCP server statuses, then flush queued startup turns."""
        if self.init_emitted:
            return
        self.init_emitted = True
        statuses = dict(self.mcp_statuses)
        for entry in entries or ():
            if isinstance(entry, dict) and entry.get("name"):
                statuses[entry["name"]] = mcp_status_value(entry)
        mcp_list = []
        for name in self.servers:
            mcp_list.append({"name": name, "status": statuses.get(name, "connected")})
        for name, st in statuses.items():
            if name not in self.servers:
                mcp_list.append({"name": name, "status": st})
        yield {"type": "system", "subtype": "init", "mcp_servers": mcp_list}
        if self.outbox:
            first_uuid, first_items, _ = self.outbox.pop(0)
            self._start_turn(first_uuid, first_items)
            for queued in self.outbox:
                self.queue.append(queued)
            self.outbox.clear()

    def answered(self, kind, payload, rpc, message, prepared=None):
        prepared = prepared or {}
        error = message.get("error")
        result = message.get("result") or {}
        if kind == "initialize":
            if error:
                self._fail_startup(kind, error)
                return
            send(self.process, {"method": "initialized", "params": {}})
            self.call("account/read", {"refreshToken": False})
        elif kind == "account/read":
            if error:
                self._fail_startup(kind, error)
                return
            if result.get("requiresOpenaiAuth") and not result.get("account"):
                print("codex: account/read reports signed out", file=sys.stderr)
                self.setup_problem = "Codex is not signed in. Run codex login in a terminal, then restart Rook."
                self.process.kill()
                return
            instructions = prepared["instructions"] if "instructions" in prepared else self.developer_instructions()
            params = {
                "cwd": self.cwd,
                "ephemeral": True,
                "developerInstructions": instructions,
            }
            if self.model:
                params["model"] = self.model
            if mapping := PERMISSION_MODES.get(self.mode):
                params["sandbox"] = mapping["sandbox"]
                params["approvalPolicy"] = mapping["approvalPolicy"]
            self.call("thread/start", params)
        elif kind == "thread/start":
            if error:
                self._fail_startup(kind, error)
                return
            thread = result.get("thread") or {}
            self.thread_id = thread.get("id")
            if not self.thread_id:
                self._fail_startup(kind, {"message": "thread/start returned no thread id"})
                return
            self.call("mcpServerStatus/list", {"threadId": self.thread_id})
        elif kind == "mcpServerStatus/list":
            entries = (result.get("data") or []) if not error else []
            yield from self._emit_init(entries)
        elif kind == "turn/start":
            # Ignore a late reply for a turn Rook already gave up on (e.g. stalled or replaced).
            if payload != self.active_turn:
                turn_id = (result.get("turn") or {}).get("id") if not error else None
                if turn_id and self.thread_id:
                    self.abandoned_turns.add(turn_id)
                    self.interrupting_turns.add(turn_id)
                    self.call("turn/interrupt", {"threadId": self.thread_id, "turnId": turn_id})
                return
            if error:
                problem = f"Codex refused the request: {brief(error.get('message'))}"
                uuid = payload
                uuids = [uuid] + list(self.steered_uuids)
                self.active_turn = self.active_turn_id = None
                self.steered_uuids = []
                yield from self.close_text()
                yield {"type": "result", "user_message_uuids": uuids, "result": problem,
                       "terminal_reason": "error", "is_error": True, "errors": [problem]}
                if self.queue:
                    next_uuid, next_items, _ = self.queue.pop(0)
                    self._start_turn(next_uuid, next_items)
                return
            turn_id = (result.get("turn") or {}).get("id")
            if turn_id:
                self.active_turn_id = turn_id
                if self.cancel_on_start:
                    self.cancel_on_start = False
                    self.interrupting_turns.add(turn_id)
                    self.call("turn/interrupt", {"threadId": self.thread_id, "turnId": turn_id})
                else:
                    self._drain_steers()
        elif kind == "turn/steer" and error:
            # Turn finished right as steer was sent: run the steered message as a fresh turn.
            uuid, items = payload
            if uuid in self.steered_uuids:
                self.steered_uuids.remove(uuid)
            if self.active_turn is None:
                self._start_turn(uuid, items)
            else:
                self.queue.insert(0, (uuid, items, False))
        elif kind == "turn/interrupt" and error:
            print(f"codex: turn/interrupt error: {brief(error.get('message'))}", file=sys.stderr)

    def _fail_startup(self, kind, error):
        is_auth = signed_out_error(error)
        print(f"codex: {kind} failed{', not signed in' if is_auth else ''}: {error}", file=sys.stderr)
        self.setup_problem = ("Codex is not signed in. Run codex login in a terminal, then restart Rook." if is_auth
                              else f"Codex refused a session: {brief((error or {}).get('message'))}.")
        self.process.kill()

    def _drain_steers(self):
        """Send any queued steer requests now that active_turn_id is known."""
        if not self.active_turn_id or self.active_turn_id in self.interrupting_turns:
            return
        remaining = []
        for uuid, items, steer in self.queue:
            if steer:
                self._send_steer(uuid, items)
            else:
                remaining.append((uuid, items, steer))
        self.queue = remaining

    def _is_stale_turn(self, turn_id):
        if turn_id and turn_id in self.abandoned_turns:
            return True
        if self.active_turn is None and self.abandoned_pending and self.stale():
            return True
        return False

    def notification(self, method, params):
        turn_id = params.get("turnId") or (params.get("turn") or {}).get("id")
        if self.first_words is None and self.active_turn is not None and method.startswith("item/"):
            self.first_words = time.monotonic() - self.turn_began
        if method == "mcpServer/startupStatus/updated":
            name = params.get("name")
            if name:
                status = params.get("status")
                err = str(params.get("error") or "").lower()
                if status == "ready":
                    self.mcp_statuses[name] = "connected"
                elif (params.get("failureReason") == "reauthenticationRequired"
                      or "not logged in" in err or "auth required" in err):
                    self.mcp_statuses[name] = "needs-auth"
                elif status in ("failed", "cancelled"):
                    self.mcp_statuses[name] = "failed"
            return
        if method == "thread/tokenUsage/updated":
            usage = params.get("tokenUsage") or {}
            self.usage = usage
            last = usage.get("last") or {}
            if isinstance(last.get("totalTokens"), int):
                self.context = last["totalTokens"]
            return
        if method == "serverRequest/resolved":
            req_id = params.get("requestId")
            for request_id, (rpc, _, _) in list(self.asks.items()):
                if rpc == req_id:  # Settled elsewhere: its card ends in Rook's queue, shown or waiting.
                    del self.asks[request_id]
                    yield {"type": "control_cancel_request", "request_id": request_id}
            return
        if method == "error":
            if not params.get("willRetry"):
                err = params.get("error") or {}
                self.last_error = brief(err.get("message") or "Codex reported an error.")
            return
        if method == "turn/started":
            tid = (params.get("turn") or {}).get("id")
            # Only bind active_turn_id from turn/started when no older turn/start is unresolved; after a stall
            # with no turn/start reply, wait for the new turn's own JSON-RPC turn/start response instead.
            ambiguous = self.abandoned_pending or any(
                k == "turn/start" and p != self.active_turn for k, p in self.calls.values()
            )
            if (tid and not ambiguous and tid not in self.abandoned_turns and tid not in self.interrupting_turns
                    and self.active_turn is not None and self.active_turn_id is None):
                self.active_turn_id = tid
                if self.cancel_on_start:
                    self.cancel_on_start = False
                    self.interrupting_turns.add(tid)
                    self.call("turn/interrupt", {"threadId": self.thread_id, "turnId": tid})
                else:
                    self._drain_steers()
            return
        if method == "item/agentMessage/delta":
            if self._is_stale_turn(turn_id):
                return
            delta = params.get("delta")
            if not isinstance(delta, str) or not delta:
                return
            if item_id := params.get("itemId"):
                self.streamed_items.add(item_id)
            if not self.texting:
                self.texting = True
                yield stream("content_block_start", content_block={"type": "text", "text": ""})
            self.answer += delta
            yield stream("content_block_delta", delta={"type": "text_delta", "text": delta})
            return
        if method == "item/started":
            if self._is_stale_turn(turn_id):
                return
            yield from self._item_started(params.get("item") or {})
            return
        if method == "item/completed":
            if self._is_stale_turn(turn_id):
                return
            yield from self._item_completed(params.get("item") or {})
            return
        if method == "turn/completed":
            yield from self._turn_completed(params.get("turn") or {})

    def _item_started(self, item):
        kind, item_id = item.get("type"), item.get("id") or ""
        if kind == "commandExecution":
            yield from self.close_text()
            self.answer = ""
            tool_input = {"command": item.get("command") or "", "run_in_background": False}
            self.active_tools[item_id] = ("Bash", item)
            yield stream("content_block_start", content_block={"type": "tool_use", "id": item_id, "name": "Bash", "input": {}})
            yield {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": item_id, "name": "Bash", "input": tool_input}]}}
        elif kind == "fileChange":
            yield from self.close_text()
            self.answer = ""
            changes = item.get("changes") or []
            first = next((c.get("path") for c in changes if isinstance(c, dict) and c.get("path")), "")
            tool_input = {"file_path": first, "changes": changes}
            self.active_tools[item_id] = ("Edit", item)
            yield stream("content_block_start", content_block={"type": "tool_use", "id": item_id, "name": "Edit", "input": {}})
            yield {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": item_id, "name": "Edit", "input": tool_input}]}}
        elif kind == "mcpToolCall":
            yield from self.close_text()
            self.answer = ""
            name = f"mcp__{item.get('server', 'mcp')}__{item.get('tool', 'tool')}"
            tool_input = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
            self.active_tools[item_id] = (name, item)
            yield stream("content_block_start", content_block={"type": "tool_use", "id": item_id, "name": name, "input": {}})
            yield {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": item_id, "name": name, "input": tool_input}]}}
        elif kind == "webSearch":
            yield from self.close_text()
            self.answer = ""
            tool_input = {"query": item.get("query") or ""}
            self.active_tools[item_id] = ("WebSearch", item)
            yield stream("content_block_start", content_block={"type": "tool_use", "id": item_id, "name": "WebSearch", "input": {}})
            yield {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": item_id, "name": "WebSearch", "input": tool_input}]}}
        elif kind == "imageView":
            yield from self.close_text()
            self.answer = ""
            tool_input = {"file_path": item.get("path") or ""}
            self.active_tools[item_id] = ("Read", item)
            yield stream("content_block_start", content_block={"type": "tool_use", "id": item_id, "name": "Read", "input": {}})
            yield {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": item_id, "name": "Read", "input": tool_input}]}}

    def _item_completed(self, item):
        kind, item_id = item.get("type"), item.get("id") or ""
        if kind == "agentMessage":
            text = item.get("text")
            if isinstance(text, str) and text and item_id not in self.streamed_items:
                if not self.texting:
                    self.texting = True
                    yield stream("content_block_start", content_block={"type": "text", "text": ""})
                self.answer += text
                yield stream("content_block_delta", delta={"type": "text_delta", "text": text})
            self.streamed_items.discard(item_id)
            yield from self.close_text()
        elif kind == "commandExecution":
            self.active_tools.pop(item_id, None)
            output = item.get("aggregatedOutput") or ""
            is_error = item.get("status") in ("failed", "declined") or item.get("exitCode") not in (None, 0)
            yield {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": item_id, "content": output, "is_error": is_error}]}}
        elif kind == "fileChange":
            self.active_tools.pop(item_id, None)
            paths = [c.get("path", "") for c in (item.get("changes") or ()) if isinstance(c, dict) and c.get("path")]
            is_error = item.get("status") in ("failed", "declined")
            yield {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": item_id, "content": ", ".join(paths), "is_error": is_error}]}}
        elif kind == "mcpToolCall":
            self.active_tools.pop(item_id, None)
            is_error = item.get("status") == "failed" or bool(item.get("error"))
            yield {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": item_id, "content": mcp_output_text(item), "is_error": is_error}]}}
        elif kind in ("webSearch", "imageView"):
            self.active_tools.pop(item_id, None)
            output = item.get("query") or item.get("path") or ""
            yield {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": item_id, "content": output, "is_error": False}]}}

    def _turn_completed(self, turn):
        turn_id = turn.get("id")
        if turn_id and turn_id in self.abandoned_turns:
            self.abandoned_turns.discard(turn_id)
            self.interrupting_turns.discard(turn_id)
            if not self.abandoned_turns:
                self.abandoned_pending = False
            return
        if self.active_turn is None and self.abandoned_pending:
            self.abandoned_pending = False
            return
        if self.active_turn is not None:
            if self.active_turn_id is not None and turn_id and turn_id != self.active_turn_id:
                return
            if self.active_turn_id is None and (
                self.abandoned_pending or any(k == "turn/start" and p != self.active_turn for k, p in self.calls.values())
            ):
                return
        self.interrupting_turns.discard(turn_id)
        for request_id in list(self.asks):  # The turn ended: its cards end in Rook's queue too.
            yield {"type": "control_cancel_request", "request_id": request_id}
        self.asks.clear()
        yield from self.close_text()
        self.turn_line()
        uuids = ([self.active_turn] if self.active_turn else []) + list(self.steered_uuids)
        status = turn.get("status") or "completed"
        err = turn.get("error") or {}
        problem = None
        if status == "failed":
            problem = brief(err.get("message") or self.last_error or "Codex failed this turn.")
        answer = self.answer
        self.active_turn = None
        self.active_turn_id = None
        self.steered_uuids = []
        self.cancel_on_start = False
        self.answer = ""
        self.last_error = None
        self.active_tools.clear()
        self.streamed_items.clear()
        reason = "error" if problem else ("cancelled" if status == "interrupted" else "completed")
        yield {"type": "result", "user_message_uuids": uuids, "result": problem or answer,
               "terminal_reason": reason, "is_error": bool(problem), "errors": [problem] if problem else []}
        if self.queue:
            next_uuid, next_items, _ = self.queue.pop(0)
            self._start_turn(next_uuid, next_items)

    def server_request(self, rpc, method, params):
        turn_id = params.get("turnId")
        if turn_id:
            if turn_id in self.interrupting_turns or turn_id in self.abandoned_turns:
                self._reply_ask(self.process, rpc, method, params, allowed=False, cancel=True)
                return
        elif self.active_turn is None and (self.interrupting_turns or self.abandoned_pending) and self.stale():
            self._reply_ask(self.process, rpc, method, params, allowed=False, cancel=True)
            return
        if method in ("item/commandExecution/requestApproval", "execCommandApproval"):
            cmd = params.get("command")
            if isinstance(cmd, list):
                cmd = " ".join(str(part) for part in cmd)
            tool_name = "Bash"
            tool_input = {
                "command": cmd or "",
                "cwd": params.get("cwd") or "",
                "description": params.get("reason") or "",
                "run_in_background": False,
            }
        elif method in ("item/fileChange/requestApproval", "applyPatchApproval"):
            item_id = params.get("itemId") or params.get("callId") or ""
            cached = (self.active_tools.get(item_id) or (None, {}))[1]
            tool_name = "Edit"
            tool_input = {
                "reason": params.get("reason") or "",
                "grantRoot": params.get("grantRoot") or "",
                "changes": cached.get("changes") or params.get("fileChanges") or [],
            }
        elif method == "item/permissions/requestApproval":
            tool_name = "Permissions"
            tool_input = {
                "reason": params.get("reason") or "",
                "cwd": params.get("cwd") or "",
                "permissions": params.get("permissions") or {},
            }
        elif method == "item/tool/requestUserInput":
            tool_name = "AskUserQuestion"
            questions = []
            for q in params.get("questions") or ():
                if not isinstance(q, dict):
                    continue
                questions.append({
                    "question": q.get("question") or "Choose an option.",
                    "header": q.get("header") or "Question",
                    "multiSelect": False,
                    "options": [{"label": o.get("label") or "", "description": o.get("description") or ""}
                                for o in (q.get("options") or ()) if isinstance(o, dict)],
                })
            tool_input = {"questions": questions}
        elif method == "mcpServer/elicitation/request":
            server = params.get("serverName") or "mcp"
            tool_name = f"mcp__{server}__elicitation"
            tool_input = {
                "message": params.get("message") or "",
                "mode": params.get("mode") or "",
                "url": params.get("url") or "",
            }
        else:
            send(self.process, {"id": rpc, "error": {"code": -32601, "message": "Rook does not offer this."}})
            return
        # Globally unique card id: session run_id + JSON-RPC request id + random suffix.
        request_id = f"codex-{self.run_id}-{rpc}-{secrets.token_hex(4)}"
        card = {"type": "control_request", "request_id": request_id,
                "request": {"subtype": "can_use_tool", "tool_name": tool_name, "input": tool_input}}
        self.asks[request_id] = (rpc, method, params)
        yield card


def _standin_script():
    """Return Python source for a stand-in `codex` binary speaking the real `app-server` protocol."""
    return r'''#!''' + sys.executable + r'''
import json, os, sys

mode = os.environ.get("FAKE_CODEX_MODE", "normal")
log_path = os.environ.get("FAKE_CODEX_LOG")

def log(entry):
    if log_path:
        with open(log_path, "a") as out:
            out.write(json.dumps(entry) + "\n")

def emit(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def read_msg():
    line = sys.stdin.readline()
    if not line:
        return None
    m = json.loads(line)
    log({"in": m})
    return m

if sys.argv[1:3] != ["app-server", "--listen"] and sys.argv[1:2] != ["app-server"]:
    sys.exit(2)

turn_seq = 0
active_turn = None
thread_id = "thr-fake-1"
pair_decisions = {}

while True:
    msg = read_msg()
    if msg is None:
        break
    method, rpc = msg.get("method"), msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        emit({"id": rpc, "result": {"userAgent": "fake-codex/0.169.0", "codexHome": os.environ.get("CODEX_HOME", "")}})
    elif method == "initialized":
        continue
    elif method == "account/read":
        if mode == "signed_out":
            emit({"id": rpc, "result": {"account": None, "userId": None, "requiresOpenaiAuth": True}})
        else:
            emit({"id": rpc, "result": {"account": {"type": "chatgpt", "email": "test@example.com", "planType": "pro"},
                                        "userId": "u1", "requiresOpenaiAuth": True}})
    elif method == "thread/start":
        emit({"id": rpc, "result": {"thread": {"id": thread_id, "ephemeral": params.get("ephemeral", False)},
                                    "model": params.get("model"), "approvalPolicy": params.get("approvalPolicy"),
                                    "sandbox": params.get("sandbox"), "instructionSources": []}})
    elif method == "mcpServerStatus/list":
        t3_auth = "notLoggedIn" if mode == "t3_needs_auth" else "oAuth"
        t3_rt = "authenticationRequired" if mode == "t3_needs_auth" else "connected"
        emit({"id": rpc, "result": {"data": [
            {"name": "render", "authStatus": "unsupported", "runtimeStatus": "connected", "tools": {"show_diagram": {}}, "resources": [], "resourceTemplates": []},
            {"name": "t3", "authStatus": t3_auth, "runtimeStatus": t3_rt, "tools": {"t3_thread_send": {}} if t3_rt == "connected" else {}, "resources": [], "resourceTemplates": []},
        ]}})
    elif method == "turn/start":
        turn_seq += 1
        active_turn = f"turn-{turn_seq}"
        text = next((i.get("text", "") for i in params.get("input", []) if i.get("type") == "text"), "")
        emit({"id": rpc, "result": {"turn": {"id": active_turn, "status": "inProgress", "items": []}}})
        emit({"method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": active_turn, "status": "inProgress", "items": []}}})
        if "CRASH" in text:
            sys.exit(1)
        if "STALL" in text:
            continue
        if "THINK_ONLY" in text:
            emit({"method": "item/reasoning/textDelta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": "r1", "delta": "thinking..."}})
            continue
        if "TOOL_RUN" in text:
            emit({"method": "item/started", "params": {"threadId": thread_id, "turnId": active_turn, "startedAtMs": 1,
                  "item": {"type": "agentMessage", "id": "m-pre", "text": ""}}})
            emit({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": "m-pre", "delta": "Checking now."}})
            emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 2,
                  "item": {"type": "agentMessage", "id": "m-pre", "text": "Checking now."}}})
            emit({"method": "item/started", "params": {"threadId": thread_id, "turnId": active_turn, "startedAtMs": 3,
                  "item": {"type": "commandExecution", "id": "cmd-1", "command": "echo hi", "cwd": "/tmp", "status": "inProgress", "commandActions": []}}})
            emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 4,
                  "item": {"type": "commandExecution", "id": "cmd-1", "command": "echo hi", "cwd": "/tmp", "status": "completed", "commandActions": [], "aggregatedOutput": "hi\n", "exitCode": 0}}})
            emit({"method": "item/started", "params": {"threadId": thread_id, "turnId": active_turn, "startedAtMs": 5,
                  "item": {"type": "mcpToolCall", "id": "mcp-1", "server": "t3", "tool": "t3_thread_send", "status": "inProgress", "arguments": {"threadId": "T1", "message": "go"}}}})
            emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 6,
                  "item": {"type": "mcpToolCall", "id": "mcp-1", "server": "t3", "tool": "t3_thread_send", "status": "completed", "arguments": {"threadId": "T1", "message": "go"},
                           "result": {"content": [{"type": "text", "text": "{\"threadId\":\"T1\",\"runId\":\"r1\",\"delivery\":\"started\"}"}]}}}})
            emit({"method": "item/started", "params": {"threadId": thread_id, "turnId": active_turn, "startedAtMs": 7,
                  "item": {"type": "agentMessage", "id": "m-post", "text": ""}}})
            emit({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": "m-post", "delta": "All done."}})
            emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 8,
                  "item": {"type": "agentMessage", "id": "m-post", "text": "All done."}}})
            emit({"method": "thread/tokenUsage/updated", "params": {"threadId": thread_id, "turnId": active_turn,
                  "tokenUsage": {"total": {"totalTokens": 500, "inputTokens": 400, "cachedInputTokens": 100, "outputTokens": 100, "reasoningOutputTokens": 10},
                                 "last": {"totalTokens": 500, "inputTokens": 400, "cachedInputTokens": 100, "outputTokens": 100, "reasoningOutputTokens": 10}}}})
            emit({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": active_turn, "status": "completed", "items": []}}})
            active_turn = None
        elif "WAIT_STEER" in text:
            emit({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": "m-st", "delta": "Starting. "}})
            continue
        elif "WAIT_INTERRUPT" in text:
            emit({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": "m-int", "delta": "Counting..."}})
            continue
        elif "ASK_TWO" in text:
            pair_decisions.clear()
            emit({"id": 910, "method": "item/commandExecution/requestApproval", "params": {
                "threadId": thread_id, "turnId": active_turn, "itemId": "cmd-a", "startedAtMs": 2, "command": "touch a", "cwd": "/tmp"}})
            emit({"id": 911, "method": "item/commandExecution/requestApproval", "params": {
                "threadId": thread_id, "turnId": active_turn, "itemId": "cmd-b", "startedAtMs": 3, "command": "touch b", "cwd": "/tmp"}})
            continue
        elif "ASK_CMD" in text:
            emit({"method": "item/started", "params": {"threadId": thread_id, "turnId": active_turn, "startedAtMs": 1,
                  "item": {"type": "commandExecution", "id": "cmd-ask", "command": "touch x", "cwd": "/tmp", "status": "inProgress", "commandActions": []}}})
            emit({"id": 901, "method": "item/commandExecution/requestApproval", "params": {
                "threadId": thread_id, "turnId": active_turn, "itemId": "cmd-ask", "startedAtMs": 2, "command": "touch x", "cwd": "/tmp", "reason": "Create x"}})
            continue
        elif "ASK_CUT" in text:
            emit({"id": 902, "method": "item/commandExecution/requestApproval", "params": {
                "threadId": thread_id, "turnId": active_turn, "itemId": "cmd-cut", "startedAtMs": 2, "command": "rm x", "cwd": "/tmp"}})
            continue
        else:
            emit({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": f"m-{turn_seq}", "delta": "ready"}})
            emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 2,
                  "item": {"type": "agentMessage", "id": f"m-{turn_seq}", "text": "ready"}}})
            emit({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": active_turn, "status": "completed", "items": []}}})
            active_turn = None
    elif method == "turn/steer":
        emit({"id": rpc, "result": {"turnId": active_turn}})
        emit({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": "m-st", "delta": "Steered."}})
        emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 5,
              "item": {"type": "agentMessage", "id": "m-st", "text": "Starting. Steered."}}})
        emit({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": active_turn, "status": "completed", "items": []}}})
        active_turn = None
    elif method == "turn/interrupt":
        emit({"id": rpc, "result": {}})
        tid = params.get("turnId") or active_turn
        if tid:
            emit({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": tid, "status": "interrupted", "items": []}}})
        if tid == active_turn:
            active_turn = None
    elif rpc in (901, 902):
        decision = (msg.get("result") or {}).get("decision")
        emit({"method": "serverRequest/resolved", "params": {"threadId": thread_id, "requestId": rpc}})
        if rpc == 901:
            emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 4,
                  "item": {"type": "commandExecution", "id": "cmd-ask", "command": "touch x", "cwd": "/tmp",
                           "status": "completed" if decision == "accept" else "declined", "commandActions": [], "aggregatedOutput": "", "exitCode": 0 if decision == "accept" else 1}}})
            emit({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": "m-ask", "delta": f"Decision was {decision}."}})
            emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 5,
                  "item": {"type": "agentMessage", "id": "m-ask", "text": f"Decision was {decision}."}}})
            emit({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": active_turn, "status": "completed", "items": []}}})
            active_turn = None
    elif rpc in (910, 911):
        pair_decisions[rpc] = (msg.get("result") or {}).get("decision")
        emit({"method": "serverRequest/resolved", "params": {"threadId": thread_id, "requestId": rpc}})
        if 910 in pair_decisions and 911 in pair_decisions:
            summary = f"Both: {pair_decisions[910]},{pair_decisions[911]}."
            emit({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": active_turn, "itemId": "m-two", "delta": summary}})
            emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": active_turn, "completedAtMs": 6,
                  "item": {"type": "agentMessage", "id": "m-two", "text": summary}}})
            emit({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": active_turn, "status": "completed", "items": []}}})
            active_turn = None
'''


def check():
    """Self-check of Codex home builder, permission mapping, converter, and a real stand-in app server."""
    global HOME, STALL_SECONDS, GEMINI_SKILLS
    from types import SimpleNamespace

    # 1. Text tables against live skills/, desktop/rook.py, and harness.Claude.setup.
    has_wow_skill = (ROOT / "wow/skills/wow/SKILL.md").is_file()
    core_skills = ("about", "dark", "delegate", "extend", "forge", "media", "onboarding", "settings", "show")
    with tempfile.TemporaryDirectory(prefix="rook-codex-check-") as tmp:
        base = Path(tmp)
        render_skills(base / "skills", wow=False)
        for name in core_skills:
            body = (base / "skills" / name / "SKILL.md").read_text()
            assert body.startswith(f"---\nname: {name}\n"), name
            assert "allowed-tools:" not in body, name
        # Codex and Pi list Rook's skills by bare name, so the rendered skills name each other that way too.
        left = [str(f) for f in (base / "skills").rglob("*.md") if re.search(r"\brook:[a-z]", f.read_text())]
        assert not left, left
        assert not (base / "skills/wow").exists()
        render_skills(base / "skills-wow", wow=True)
        for name in core_skills + (("wow",) if has_wow_skill else ()):
            body = (base / "skills-wow" / name / "SKILL.md").read_text()
            assert body.startswith(f"---\nname: {name}\n"), name
            assert "allowed-tools:" not in body, name
        if not has_wow_skill:
            assert not (base / "skills-wow/wow").exists()
        edit((ROOT / "desktop/rook.py").read_text(), PROMPT, "desktop/rook.py")
        if has_wow_skill:
            assert "rook:wow" in adapt_setup(True) and "rook:wow" not in adapt_setup(False)
        else:
            assert "rook:wow" not in adapt_setup(True) and "rook:wow" not in adapt_setup(False)
        assert not any(tok in adapt_setup(True) for tok in CLAUDE_ONLY)

        # 2. TOML basic string serialization handles astral Unicode (never UTF-16 surrogates) and control chars.
        astral = "/tmp/skill-\U0001f98a-\"quoted\"-\x07/SKILL.md"
        encoded = toml_string(astral)
        assert "\\ud83e" not in encoded.lower() and "\U0001f98a" in encoded
        assert tomllib.loads(f"p = {encoded}\n")["p"] == astral

        # 3. Private CODEX_HOME builder: full user config inheritance ([projects], [profiles], profile, keyring),
        #    history.persistence="none", astral skill path, plain-mode overrides, and clear() preserves targets.
        fake_user = base / "real-codex"
        fake_user.mkdir()
        (fake_user / "auth.json").write_text('{"tokens":"sentinel"}\n')
        (fake_user / ".credentials.json").write_text('{"mcp":"sentinel"}\n')
        (fake_user / "rules").mkdir()
        (fake_user / "rules/default.rules").write_text("# user rule\n")
        (fake_user / "config.toml").write_text(
            'profile = "work"\n'
            'cli_auth_credentials_store = "keyring"\n'
            'mcp_oauth_credentials_store = "file"\n'
            'approval_policy = "on-request"\n'
            'sandbox_mode = "workspace-write"\n'
            '\n'
            '[profiles.work]\n'
            'approval_policy = "on-request"\n'
            'sandbox_mode = "workspace-write"\n'
            '\n'
            '[projects."/home/test/repo"]\n'
            'trust_level = "trusted"\n'
            '\n'
            '[features]\n'
            'goals = true\n'
            'apps = true\n'
            '\n'
            '[mcp_servers.unrelated_user_mcp]\n'
            'url = "http://127.0.0.1:9999/mcp"\n'
        )
        fake_agents = base / "agents"
        (fake_agents / "skills/omarchy").mkdir(parents=True)
        (fake_agents / "skills/omarchy/SKILL.md").write_text("---\nname: omarchy\n---\n")
        (fake_agents / "skills/unrelated-\U0001f98a").mkdir(parents=True)
        (fake_agents / "skills/unrelated-\U0001f98a/SKILL.md").write_text("---\nname: unrelated\n---\n")
        (fake_agents / "AGENTS.md").write_text("Global rule.\n")
        fake_rook_skills = base / "rook-skills"
        (fake_rook_skills / "custom-one").mkdir(parents=True)
        (fake_rook_skills / "custom-one/SKILL.md").write_text("---\nname: custom-one\n---\n")

        priv = base / "runtime-codex"
        servers = {
            "render": {"command": "uv", "args": ["run", "--script", "/tmp/render_tool.py"]},
            "t3": {"type": "http", "url": "http://127.0.0.1:3773/mcp"},
        }
        build_home(servers, denied=("t3_project_delete", "pull_request_merge"), mode="inherit",
                   home=priv, user_home=fake_user, user_rook_skills=fake_rook_skills, agents_dir=fake_agents,
                   host_skills=("omarchy",))
        assert (priv / "auth.json").is_symlink() and (priv / ".credentials.json").is_symlink()
        assert (priv / "rules").is_symlink()
        assert (priv / "AGENTS.md").is_file() and not (priv / "AGENTS.md").is_symlink()
        assert (priv / "skills/custom-one").is_symlink()
        assert (priv / "skills/delegate/SKILL.md").is_file()
        parsed = tomllib.loads((priv / "config.toml").read_text())
        # User's whole config survives in inherit mode: projects trust, profile/profiles, keyring store, other features.
        assert parsed["profile"] == "work"
        assert parsed["profiles"]["work"]["sandbox_mode"] == "workspace-write"
        assert parsed["projects"]["/home/test/repo"]["trust_level"] == "trusted"
        assert parsed["cli_auth_credentials_store"] == "keyring"
        assert parsed["mcp_oauth_credentials_store"] == "file"
        assert parsed["approval_policy"] == "on-request" and parsed["sandbox_mode"] == "workspace-write"
        assert parsed["agents"] == {"enabled": False}
        assert parsed["history"] == {"persistence": "none"}
        assert parsed["features"]["apps"] is False and parsed["features"]["browser_use"] is False
        assert parsed["features"]["goals"] is True  # Unrelated user feature kept.
        assert "unrelated_user_mcp" not in parsed["mcp_servers"]
        assert parsed["mcp_servers"]["t3"]["disabled_tools"] == ["t3_project_delete", "pull_request_merge"]
        hidden_paths = [entry["path"] for entry in parsed["skills"]["config"] if entry["enabled"] is False]
        assert any("unrelated-\U0001f98a/SKILL.md" in p for p in hidden_paths)
        assert not any("omarchy/SKILL.md" in p for p in hidden_paths)

        # Plain mode (e.g. careful) overrides sandbox_mode/approval_policy and clears profile while keeping [projects].
        build_home(servers, denied=(), mode="careful", home=priv, user_home=fake_user,
                   user_rook_skills=fake_rook_skills, agents_dir=fake_agents)
        parsed_careful = tomllib.loads((priv / "config.toml").read_text())
        assert parsed_careful["sandbox_mode"] == "read-only" and parsed_careful["approval_policy"] == "on-request"
        assert "profile" not in parsed_careful
        assert parsed_careful["projects"]["/home/test/repo"]["trust_level"] == "trusted"

        # Host skills follow the active plugins: an allowed one is kept or linked, any other is hidden and never linked.
        assert not any("omarchy/" in p for p in disabled_host_skills(fake_agents, allow=("omarchy",)))
        assert any(p.endswith("/omarchy/SKILL.md") for p in disabled_host_skills(fake_agents, allow=()))
        (fake_user / "skills/omarchy").mkdir(parents=True)
        (fake_user / "skills/omarchy/SKILL.md").write_text("---\nname: omarchy\n---\n")
        saved_gemini, GEMINI_SKILLS = GEMINI_SKILLS, base / "no-gemini-skills"  # Never the host's own folder.
        try:
            for agents_dir, allowed in ((fake_agents, ()), (base / "no-agents", ("omarchy", "omarchy")),
                                        (base / "no-agents", ())):
                build_home(servers, mode="inherit", home=priv, user_home=fake_user, user_rook_skills=fake_rook_skills,
                           agents_dir=agents_dir, host_skills=allowed)
                parsed_now = tomllib.loads((priv / "config.toml").read_text())
                hidden_now = [e["path"] for e in parsed_now.get("skills", {}).get("config", []) if e["enabled"] is False]
                assert any(p.endswith("/omarchy/SKILL.md") for p in hidden_now) == (agents_dir == fake_agents), hidden_now
                linked = agents_dir != fake_agents and bool(allowed)
                assert (priv / "skills/omarchy").is_symlink() == linked
                if linked:
                    assert os.readlink(priv / "skills/omarchy") == str(fake_user / "skills/omarchy")
            # The Gemini skills folder comes first when it has the skill.
            GEMINI_SKILLS = base / "gemini-skills"
            (GEMINI_SKILLS / "omarchy").mkdir(parents=True)
            (GEMINI_SKILLS / "omarchy/SKILL.md").write_text("---\nname: omarchy\n---\n")
            build_home(servers, mode="inherit", home=priv, user_home=fake_user, user_rook_skills=fake_rook_skills,
                       agents_dir=base / "no-agents", host_skills=("omarchy",))
            assert os.readlink(priv / "skills/omarchy") == str(GEMINI_SKILLS / "omarchy")
        finally:
            GEMINI_SKILLS = saved_gemini
        shutil.rmtree(fake_user / "skills")

        # Fix 1: unparseable or non-UTF-8 ~/.codex/config.toml fails start loudly (naming file & position, never contents).
        bad_user = base / "bad-codex"
        bad_user.mkdir()
        secret_tok = "SUPER_SECRET_SHOULD_NEVER_APPEAR"
        (bad_user / "config.toml").write_text(f'api_key = "{secret_tok}"\nbroken = ===\n')
        try:
            build_home(servers, home=base / "priv-bad", user_home=bad_user, agents_dir=fake_agents)
            assert False, "unparseable config.toml must raise"
        except ValueError as exc:
            err_text = str(exc)
            assert str(bad_user / "config.toml") in err_text and "line 2" in err_text and secret_tok not in err_text, err_text
        (bad_user / "config.toml").write_bytes(b"\xff\xfeinvalid-utf8")
        try:
            build_home(servers, home=base / "priv-bad", user_home=bad_user, agents_dir=fake_agents)
            assert False, "non-UTF-8 config.toml must raise"
        except ValueError as exc:
            err_text = str(exc)
            assert str(bad_user / "config.toml") in err_text and "UTF-8" in err_text and "byte 0" in err_text, err_text

        # Fix 2: a lone surrogate in a broken skill directory name is skipped with a log line, not fatal.
        surr_agents = base / "surr-agents"
        (surr_agents / "skills/good-skill").mkdir(parents=True)
        (surr_agents / "skills/good-skill/SKILL.md").write_text("---\nname: good-skill\n---\n")
        bad_skill_dir = os.fsencode(surr_agents / "skills") + b"/bad-\xff-skill"
        os.makedirs(bad_skill_dir, exist_ok=True)
        with open(bad_skill_dir + b"/SKILL.md", "wb") as out:
            out.write(b"---\nname: bad\n---\n")
        build_home(servers, home=priv, user_home=fake_user, user_rook_skills=fake_rook_skills, agents_dir=surr_agents)
        parsed_surr = tomllib.loads((priv / "config.toml").read_text())
        surr_hidden = [e["path"] for e in parsed_surr["skills"]["config"] if e["enabled"] is False]
        assert any("good-skill/SKILL.md" in p for p in surr_hidden) and len(surr_hidden) == 1, surr_hidden

        # clear() removes private home without harming symlinked real credentials.
        clear(priv)
        assert not priv.exists()
        assert (fake_user / "auth.json").read_text() == '{"tokens":"sentinel"}\n'
        assert (fake_user / ".credentials.json").read_text() == '{"mcp":"sentinel"}\n'

        # Without XDG_RUNTIME_DIR and non-Linux, resolve_home() creates a private 0700 temp folder.
        saved_home_mod, saved_xdg, saved_linux = HOME, os.environ.get("XDG_RUNTIME_DIR"), desk.IS_LINUX
        HOME = None
        os.environ.pop("XDG_RUNTIME_DIR", None)
        desk.IS_LINUX = False
        try:
            temp_home = resolve_home()
            assert temp_home.is_dir() and (temp_home.stat().st_mode & 0o777) == 0o700
            clear(temp_home)
            assert not temp_home.exists()
        finally:
            HOME = saved_home_mod
            desk.IS_LINUX = saved_linux
            if saved_xdg is not None:
                os.environ["XDG_RUNTIME_DIR"] = saved_xdg

        # 4. Permission mode default is "full" (the owner, 2026-11-25); each mode maps to Codex's own.
        assert permission_mode({}) == "full"
        assert permission_mode({"permissions": "inherit"}) == "full"  # Old unused key ignored.
        for mode_name, want in (
            ("inherit", None),
            ("careful", {"sandbox": "read-only", "approvalPolicy": "on-request"}),
            ("automatic", {"sandbox": "workspace-write", "approvalPolicy": "on-request"}),
            ("full", {"sandbox": "danger-full-access", "approvalPolicy": "never"}),
            ("rook", {"sandbox": "danger-full-access", "approvalPolicy": "never"}),
        ):
            assert permission_mode({"permission_mode": mode_name}) == mode_name
            assert PERMISSION_MODES[mode_name] == want

        # 5. Every ask reaches Rook as it comes, for Rook's own queue, which shows one at a time. Unique IDs, all
        #    approval types, each answer to exactly its request in any order, never allow-always, and stale
        #    turn/start replies ignored.
        sent = []
        fake_proc = SimpleNamespace(pid=None, kill=lambda: None,
                                    stdin=SimpleNamespace(write=lambda b: sent.append(json.loads(b.decode()))))
        cx = Codex()
        cx.prompt = "You run as a full Claude Code session. that your session start message names."
        cx.servers, cx.denied, cx.mode = {}, (), "careful"
        cx.begin(fake_proc, "s", "setup", "Setup.")
        seen_cards = []
        for rpc, method, params in (
                (50, "item/commandExecution/requestApproval", {"threadId": "t", "turnId": "u", "itemId": "i1",
                                                               "command": "ls"}),
                (51, "item/fileChange/requestApproval", {"threadId": "t", "turnId": "u", "itemId": "i2",
                                                         "reason": "Edit a.py"}),
                (52, "item/permissions/requestApproval", {"threadId": "t", "turnId": "u", "itemId": "i3", "cwd": "/tmp",
                                                          "permissions": {"network": {"enabled": True}}}),
                (53, "item/tool/requestUserInput", {"threadId": "t", "turnId": "u", "itemId": "i4", "isBlocking": True,
                                                    "questions": [{"id": "q1", "header": "Color",
                                                                   "question": "Red or blue?",
                                                                   "options": [{"label": "Red", "description": ""},
                                                                               {"label": "Blue", "description": ""}]}]}),
                (54, "mcpServer/elicitation/request", {"threadId": "t", "serverName": "t3", "mode": "url",
                                                       "elicitationId": "e1", "message": "Open link",
                                                       "url": "http://x"})):
            seen_cards.extend(cx.handle({"id": rpc, "method": method, "params": params}))
        assert [card["request"]["tool_name"] for card in seen_cards] == [
            "Bash", "Edit", "Permissions", "AskUserQuestion", "mcp__t3__elicitation"], seen_cards
        cx.permit(fake_proc, seen_cards[0], True)
        assert sent[-1] == {"id": 50, "result": {"decision": "accept"}}
        cx.permit(fake_proc, seen_cards[0], False)  # Already answered: no second reply.
        assert len(sent) == 2
        cx.permit(fake_proc, seen_cards[2], True)  # Out of order: the answer goes to its own request.
        assert sent[-1] == {"id": 52, "result": {"permissions": {"network": {"enabled": True}}, "scope": "turn"}}
        cx.permit(fake_proc, seen_cards[1], False)
        assert sent[-1] == {"id": 51, "result": {"decision": "decline"}}
        cx.permit(fake_proc, seen_cards[3], True, {"Red or blue?": "blue"})
        assert sent[-1] == {"id": 53, "result": {"answers": {"q1": {"answers": ["Blue"]}}}}
        cx.permit(fake_proc, seen_cards[4], False)
        assert sent[-1] == {"id": 54, "result": {"action": "decline", "content": None}}
        assert list(cx.flush()) == [] and not cx.asks
        ids = {c["request_id"] for c in seen_cards}
        assert len(ids) == 5 and all(cid.startswith(f"codex-{cx.run_id}-") for cid in ids)

        # Late turn/start reply for an abandoned turn must NOT overwrite active_turn_id of a newer turn.
        cx.thread_id = "thr-x"
        cx.active_turn = "new-uuid"
        cx.active_turn_id = "turn-new"
        cx.calls[77] = ("turn/start", "old-uuid")
        list(cx.handle({"id": 77, "result": {"turn": {"id": "turn-old", "status": "inProgress", "items": []}}}))
        assert cx.active_turn_id == "turn-new" and "turn-old" in cx.abandoned_turns
        assert sent[-1] == {"id": cx.next_id, "method": "turn/interrupt",
                            "params": {"threadId": "thr-x", "turnId": "turn-old"}}

        # Fix 3: after stopping turn-stop, an approval from the NEXT turn (turn-next) within 5s must still show a card,
        # while an approval from turn-stop itself is cancelled.
        cx.interrupting_turns = {"turn-stop"}
        cx.stale_until = time.monotonic() + STALE_SECONDS
        cx.active_turn = "next-uuid"
        cx.active_turn_id = "turn-next"
        assert list(cx.handle({"id": 80, "method": "item/commandExecution/requestApproval",
                               "params": {"threadId": "thr-x", "turnId": "turn-stop", "itemId": "i-s", "command": "rm a"}})) == []
        assert sent[-1] == {"id": 80, "result": {"decision": "cancel"}}
        next_cards = list(cx.handle({"id": 81, "method": "item/commandExecution/requestApproval",
                                     "params": {"threadId": "thr-x", "turnId": "turn-next", "itemId": "i-n", "command": "touch b"}}))
        assert len(next_cards) == 1 and next_cards[0]["request"]["input"]["command"] == "touch b"
        cx.permit(fake_proc, next_cards[0], True)
        assert sent[-1] == {"id": 81, "result": {"decision": "accept"}}

        # Fix 4: after a stall with no turn/start reply and a queued turn started, a late turn/started from the old
        # stalled turn is dropped and NOT taken as the new turn's id; the new turn's own turn/start response binds it.
        cx.interrupting_turns.clear()
        cx.abandoned_turns.clear()
        cx.calls.clear()
        cx.abandoned_pending = False
        cx.active_turn = "old-stall-uuid"
        cx.active_turn_id = None
        cx.calls[90] = ("turn/start", "old-stall-uuid")
        cx.queue = [("queued-uuid", [{"type": "text", "text": "Next."}], False)]
        list(cx.stalled())
        assert cx.active_turn == "queued-uuid" and cx.active_turn_id is None and cx.abandoned_pending
        new_rpc = cx.next_id
        # Late turn/started + turn/completed for old stalled turn must be ignored.
        assert list(cx.handle({"method": "turn/started",
                               "params": {"threadId": "thr-x", "turn": {"id": "turn-old-late", "status": "inProgress", "items": []}}})) == []
        assert cx.active_turn_id is None
        assert list(cx.handle({"method": "turn/completed",
                               "params": {"threadId": "thr-x", "turn": {"id": "turn-old-late", "status": "completed", "items": []}}})) == []
        assert cx.active_turn == "queued-uuid"
        # Now the new turn's own turn/start RPC response binds active_turn_id cleanly.
        list(cx.handle({"id": new_rpc, "result": {"turn": {"id": "turn-queued-real", "status": "inProgress", "items": []}}}))
        assert cx.active_turn_id == "turn-queued-real"

        # 6. End-to-end stand-in `codex` app-server launched via the EXACT generated command() from /tmp!
        fake_bin = base / "bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(_standin_script())
        fake_codex.chmod(0o755)

        saved_home, saved_path = HOME, os.environ.get("PATH", "")
        saved_codex_home = os.environ.get("CODEX_HOME")
        saved_cfg = rook_settings.CONFIG
        saved_stall = STALL_SECONDS
        os.environ["PATH"] = f"{fake_bin}:{saved_path}"
        os.environ["CODEX_HOME"] = str(fake_user)
        # A settings file that chooses inherit: the stand-in tests then check that NO overrides are sent.
        rook_settings.CONFIG = base / "inherit-settings.json"
        rook_settings.CONFIG.write_text('{"permission_mode": "inherit"}')

        async def read_lines(proc):
            while line := await proc.stdout.readline():
                yield json.loads(line.decode())

        async def run_standin_tests():
            global HOME, STALL_SECONDS
            prompt_text = "You run as a full Claude Code session. Your memory is that your session start message names."
            sample_servers = {"render": {"command": "uv", "args": []}, "t3": {"type": "http", "url": "http://127.0.0.1:3773/mcp"}}

            # 6a. No setting -> inherit mode with NO sandbox/approvalPolicy overrides sent on thread/start,
            #     streamed turn + inline JPEG data URL + tool call + MCP result, steer, interrupt,
            #     single approval, TWO concurrent approvals shown & answered in order, cut by stop,
            #     reasoning heartbeat, stall watchdog, and crash cleanup.
            HOME = base / "rt-main"
            log_file = base / "standin-main.jsonl"
            cx = Codex("gpt-6.2-sol", "low")
            assert cx.ready() is None and cx.marks_tools_first is True
            argv = cx.command(prompt_text, sample_servers, "sess-1", ROOT / "plugin", ("t3_project_delete",))
            assert cx.mode == "inherit"
            assert argv[:2] == ["env", f"CODEX_HOME={HOME}"] and "codex" in argv
            env = {**os.environ, "FAKE_CODEX_MODE": "normal", "FAKE_CODEX_LOG": str(log_file)}
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd="/tmp", env=env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            cx.begin(proc, "sess-1", "u-setup", cx.setup({}, [], False))
            reader = cx.read(read_lines(proc))

            async def next_until(pred, limit=5.0):
                collected = []
                async def pump():
                    async for m in reader:
                        collected.append(m)
                        if pred(m):
                            return m
                    return None
                hit = await asyncio.wait_for(pump(), limit)
                return hit, collected

            res, got = await next_until(lambda m: m["type"] == "result")
            assert any(m.get("type") == "system" and any(s == {"name": "t3", "status": "connected"} for s in m["mcp_servers"]) for m in got), got
            assert res["user_message_uuids"] == ["u-setup"] and res["result"] == "ready" and res["terminal_reason"] == "completed"
            # Verify inherit sent NO sandbox or approvalPolicy overrides on thread/start!
            logged = [json.loads(line)["in"] for line in log_file.read_text().splitlines()]
            thr_start = next(m for m in logged if m.get("method") == "thread/start")
            assert "sandbox" not in thr_start["params"] and "approvalPolicy" not in thr_start["params"], thr_start

            # Streamed turn with JPEG screenshot (inline data URL) + Bash + mcp__t3__t3_thread_send.
            cx.turn(proc, "sess-1", "u-tool", "TOOL_RUN", [b"\xff\xd8\xff\xd9"], False)
            res, got = await next_until(lambda m: m["type"] == "result")
            assert res["user_message_uuids"] == ["u-tool"] and res["result"] == "All done."
            tool_uses = [b for m in got if m["type"] == "assistant" for b in m["message"]["content"] if b["type"] == "tool_use"]
            tool_results = [b for m in got if m["type"] == "user" for b in m["message"]["content"] if b["type"] == "tool_result"]
            assert [t["name"] for t in tool_uses] == ["Bash", "mcp__t3__t3_thread_send"]
            assert tool_uses[0]["input"] == {"command": "echo hi", "run_in_background": False}
            assert len(tool_results) == 2 and tool_results[0]["content"] == "hi\n" and "T1" in tool_results[1]["content"]
            assert cx.context == 500
            logged = [json.loads(line)["in"] for line in log_file.read_text().splitlines()]
            tool_start = next(m for m in logged if m.get("method") == "turn/start"
                              and any("TOOL_RUN" in i.get("text", "") for i in m["params"]["input"]))
            assert tool_start["params"]["input"][0] == {"type": "image", "url": "data:image/jpeg;base64,/9j/2Q=="}

            # Steer mid-turn -> both uuids returned in final result.
            cx.turn(proc, "sess-1", "u-st1", "WAIT_STEER", [], False)
            await next_until(lambda m: m["type"] == "stream_event" and m["event"].get("type") == "content_block_delta")
            cx.turn(proc, "sess-1", "u-st2", "Actually steer.", [], True)
            res, _ = await next_until(lambda m: m["type"] == "result")
            assert res["user_message_uuids"] == ["u-st1", "u-st2"] and res["result"] == "Starting. Steered."

            # Interrupt mid-turn -> confirmed cancelled result.
            cx.turn(proc, "sess-1", "u-int", "WAIT_INTERRUPT", [], False)
            await next_until(lambda m: m["type"] == "stream_event" and m["event"].get("type") == "content_block_delta")
            cx.interrupt(proc)
            res, _ = await next_until(lambda m: m["type"] == "result")
            assert res["user_message_uuids"] == ["u-int"] and res["terminal_reason"] == "cancelled"

            # Single approval answered -> accept sent for exact request, turn completes.
            cx.turn(proc, "sess-1", "u-ask", "ASK_CMD", [], False)
            card, _ = await next_until(lambda m: m["type"] == "control_request")
            assert card["request"]["tool_name"] == "Bash" and card["request"]["input"]["command"] == "touch x"
            cx.permit(proc, card, True)
            res, _ = await next_until(lambda m: m["type"] == "result")
            assert res["result"] == "Decision was accept." and res["terminal_reason"] == "completed"

            # TWO approval requests in a row: both reach Rook at once, for its own queue, and both finish.
            cx.turn(proc, "sess-1", "u-two", "ASK_TWO", [], False)
            card_a, _ = await next_until(lambda m: m["type"] == "control_request")
            assert card_a["request"]["input"]["command"] == "touch a"
            card_b, _ = await next_until(lambda m: m["type"] == "control_request")
            cx.permit(proc, card_a, True)
            assert card_b["type"] == "control_request" and card_b["request"]["input"]["command"] == "touch b"
            assert card_b["request_id"] != card_a["request_id"]
            cx.permit(proc, card_b, False)
            res, _ = await next_until(lambda m: m["type"] == "result")
            assert res["result"] == "Both: accept,decline." and res["terminal_reason"] == "completed", res

            # Approval cut by stop -> cancel sent + turn interrupted, late permit() sends nothing.
            cx.turn(proc, "sess-1", "u-cut", "ASK_CUT", [], False)
            card, _ = await next_until(lambda m: m["type"] == "control_request")
            cx.interrupt(proc)
            res, _ = await next_until(lambda m: m["type"] == "result")
            assert res["terminal_reason"] == "cancelled"
            before_count = len(log_file.read_text().splitlines())
            cx.permit(proc, card, True)
            await asyncio.sleep(0.05)
            assert len(log_file.read_text().splitlines()) == before_count

            # Reasoning-only notification updates heard without yielding any spoken text.
            cx.turn(proc, "sess-1", "u-think", "THINK_ONLY", [], False)
            handed = time.monotonic()
            pump_task = asyncio.create_task(reader.__anext__())
            try:
                await asyncio.wait_for(asyncio.shield(pump_task), 0.2)
                assert False, "reasoning notification must not yield a message"
            except asyncio.TimeoutError:
                pass
            assert cx.heard > handed
            cx.interrupt(proc)
            first_after = await asyncio.wait_for(pump_task, 3.0)
            res = first_after if first_after["type"] == "result" else (await next_until(lambda m: m["type"] == "result"))[0]
            assert res["terminal_reason"] == "cancelled"

            # Stall with no output -> harness sends turn/interrupt and yields STALLED result.
            STALL_SECONDS = 0.25
            cx.turn(proc, "sess-1", "u-stall", "STALL", [], False)
            res, _ = await next_until(lambda m: m["type"] == "result", limit=3.0)
            assert res["user_message_uuids"] == ["u-stall"] and res["terminal_reason"] == "stalled" and res["result"] == STALLED
            STALL_SECONDS = saved_stall

            # Crash mid-turn -> reader exits cleanly and wipes private CODEX_HOME.
            cx.turn(proc, "sess-1", "u-crash", "CRASH", [], False)
            rest = [m async for m in reader]
            await proc.wait()
            assert not HOME.exists() and not any(m["type"] == "result" for m in rest)

            # 6b. Sign-out -> setup_problem says Codex is not signed in, process killed, stream ends.
            HOME = base / "rt-signout"
            cx2 = Codex()
            argv2 = cx2.command(prompt_text, sample_servers, "sess-2", ROOT / "plugin", ())
            proc2 = await asyncio.create_subprocess_exec(
                *argv2, cwd="/tmp", env={**os.environ, "FAKE_CODEX_MODE": "signed_out"},
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            cx2.begin(proc2, "sess-2", "u-so", cx2.setup({}, [], False))
            seen2 = [m async for m in cx2.read(read_lines(proc2))]
            await proc2.wait()
            assert cx2.setup_problem == "Codex is not signed in. Run codex login in a terminal, then restart Rook." and not seen2 and not HOME.exists()

            # 6c. T3 needs-auth -> system/init reports t3 status "needs-auth".
            HOME = base / "rt-t3auth"
            cx3 = Codex()
            argv3 = cx3.command(prompt_text, sample_servers, "sess-3", ROOT / "plugin", ())
            proc3 = await asyncio.create_subprocess_exec(
                *argv3, cwd="/tmp", env={**os.environ, "FAKE_CODEX_MODE": "t3_needs_auth"},
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            cx3.begin(proc3, "sess-3", "u-t3", cx3.setup({}, [], False))
            r3 = cx3.read(read_lines(proc3))
            seen3 = []
            async for m in r3:
                seen3.append(m)
                if m["type"] == "result":
                    break
            proc3.terminate()
            await proc3.wait()
            await r3.aclose()
            assert any(m.get("type") == "system" and any(s == {"name": "t3", "status": "needs-auth"} for s in m["mcp_servers"]) for m in seen3), seen3
            assert not HOME.exists()

        try:
            asyncio.run(run_standin_tests())
        finally:
            HOME = saved_home
            STALL_SECONDS = saved_stall
            rook_settings.CONFIG = saved_cfg
            os.environ["PATH"] = saved_path
            if saved_codex_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = saved_codex_home

    print("Codex harness: all checks passed.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        check()
    else:
        sys.exit("Run with --check for the self-check.")
