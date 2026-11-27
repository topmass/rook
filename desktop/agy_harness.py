"""Rook's main agent on Google's Antigravity CLI (agy), through its Agent Client Protocol server, agy acp.

ACP is JSON-RPC on stdio. This harness opens one session per agy process and turns ACP's messages into the Claude
Code stream-json shapes that harness.py lists, so Rook's reader, watcher, overlay tables and log keep their code.

Nothing of the conversation stays on disk, by the owner's rule: each request carries a screenshot of their screen. agy saves
every session, images included, under its data folder. Rook starts agy with --gemini-dir set to antigravity_home's
folder in the runtime folder, which is memory, and removes the data folder in it at each launch and when the session
ends, at a clean stop too.
The Google sign-in stays in the system keyring, which every agy data folder shares, so no credential is copied.

agy has no flag that denies a tool. antigravity_home's hook sees every tool call. It denies each tool Rook does not
have (subagents, browser, scheduling and any tool a later agy adds) and Rook's denied commands before they run,
with a reason the model reads. The session runs in agy's default mode, which asks before commands and
tool-server calls. decide() answers each ask: it rejects what Rook denies under Claude Code, allows reads, searches,
Rook's own relay.py commands, plain thread sends (SENDS) and the game-data and render tools, and shows the rest on
The owner's permission card.
agy ends its turn at a rejection, with no answer, so the result then says what was declined.

Self-check: ~/.local/share/rook/venv/bin/python desktop/agy_harness.py --check
The file is not named antigravity.py: Python's own antigravity module opens a web page when imported.
"""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import os
from pathlib import Path
import re
import shlex
import select
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

import antigravity_home  # Rook's private agy folder: its skills, instructions and command guard.
import desk
from harness import Harness
import machine
import plugin_loader
import settings  # noqa: E402
OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.

ROOT = Path(__file__).resolve().parents[1]
APP = "antigravity-acp"  # agy's data folder, conversations included, under --gemini-dir. Only agy writes it.
# The owner's own agy sign-in to T3's tool server: agy keeps each tool server's OAuth sign-in here, keyed by its URL. They
# sign in once in interactive agy (/mcp, Authenticate). A Rook session uses it through a link in its private data
# folder, so the token stays in this one file (mode 0600), and no copy can go stale.
T3_TOKENS = Path.home() / ".gemini/antigravity-cli/mcp_oauth_tokens.json"
# When T3 rejects that sign-in, agy drops it, and the T3 tools vanish with no error. Neon is told what that means.
T3_LOST = (f"\n\nYour T3 tools come from {OWNER}'s own Antigravity sign-in to T3. If they are gone, or a T3 tool says it "
           f"is not authorized, tell {OWNER} in one sentence that the T3 sign-in for Antigravity has ended, then use the "
           "t3 command as your delegate skill says.")
# Rook's effort names, as Claude Code takes them, and agy's thinking levels. Neon has no max, so max is xhigh.
EFFORTS = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}
# No update of the owner's agy install, and no browser: a missing sign-in shows as an error instead.
ENV = ["env", "AGY_CLI_DISABLE_AUTO_UPDATE=1", f"BROWSER={desk.false_exe()}"]
INITIALIZE = {"protocolVersion": 1, "clientInfo": {"name": "rook", "version": "1"},
              "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}}
# The watchdog: a turn ends when agy has sent nothing for this long with a prompt open and no card waiting on the owner.
# Ten minutes, as Claude Code's own limit for a command (the owner's call, 2026-11-23). agy sends nothing while a command
# runs (58.7 s during sleep 75, run 38) or while it compacts a large session (23 to 25 s in a scratch run, over 60 s
# live, where a 60 s limit cancelled it three turns in a row). On 2026-11-23 a turn hung for nine minutes on a card.
STALL_SECONDS = 600
STALLED = "Antigravity stopped answering, so I stopped that turn. Ask again."
# After Rook cancels a turn (the owner's stop or the watchdog), late text and asks belong to that turn, and Rook drops
# them, for this long. agy answers a cancel within about a second. When its answer never comes, a newer turn's text
# and asks are then its own, so one lost answer cannot mute every turn after it (review 2).
STALE_SECONDS = 5
# agy puts a long command in the background after 10 s, may end its turn while it runs, and then wakes with the
# command's result and more text, though no prompt is open (09:38 live test, run 38). Rook holds such a turn open,
# as Claude Code waits for a command, until agy's next model step ends with no tool open, or it is this quiet.
HELD_QUIET_SECONDS = 10
MODE = "default"  # agy asks before edits, commands and tool-server calls. Its "auto" would run them unseen.
# The owner's call, 2026-11-23, after repeated cards: "full" lets every tool and command that Rook does not deny pass with
# no card, as under Claude Code. The denials in decide() and the hook, and DCG, stay. An agent's question still shows
# its card. "strict" brings back the read-only list and the owner's card for everything else; no mode picks it now. "ask"
# shows the card for every ask that Rook does not deny, so agy's own mode alone decides what it asks.
PERMISSIONS = "full"
# agy's own session mode for each permission_mode. inherit sends none, so the person's own agentMode rules. full
# also starts agy with --dangerously-skip-permissions, agy's always-proceed.
AGY_MODES = {"rook": MODE, "careful": "default", "automatic": "auto", "full": "default"}
# The person's own agy settings that decide how it asks, copied into Rook's private agy folder for inherit.
OWN_SETTINGS = Path.home() / ".gemini/antigravity-cli/settings.json"
OWN_KEYS = ("agentMode", "toolPermission", "enableTerminalSandbox", "allowNonWorkspaceAccess", "permissions")

# agy's tool names, as Rook's reader knows them from Claude Code. Others keep agy's name.
NAMES = {"run_command": "Bash", "view_file": "Read", "read_file": "Read", "write_file": "Write", "edit_file": "Edit",
         "write_to_file": "Write",
         "replace_file_content": "Edit", "multi_replace_file_content": "Edit", "sed_file": "Edit",
         "grep_search": "Grep", "find_by_name": "Glob", "list_dir": "Glob", "search_web": "WebSearch",
         "read_url_content": "WebFetch", "ask_question": "AskUserQuestion", "invoke_subagent": "Agent",
         "define_subagent": "Agent", "manage_subagents": "Agent", "browser_subagent": "Agent"}
READS = {"Read", "Glob", "Grep", "WebSearch", "WebFetch"}
RAW_READS = {"command_status", "list_resources", "read_resource", "list_permissions", "finish", "wait", "wait_5_seconds"}
T3_READS = {"t3_pending_request", "t3_thread_read", "t3_thread_list", "t3_thread_search", "t3_project_list",
            "t3_project_read", "t3_environment_links", "t3_environment_read", "orchestrator_capabilities"}
# Shell commands that only read, in every form: none of these programs has an option that writes, runs a command
# or waits. A command with any other shell syntax goes to the card. read_only() below holds the programs that do
# have such options, each allowed only in its safe forms.
SAFE_PROGRAMS = {"ls", "cat", "head", "wc", "grep", "stat", "pwd", "echo", "which", "uname", "df", "free", "uptime",
                 "ps", "whoami", "realpath"}
# git log, diff and show: refs, paths and these display options only. No --output, --ext-diff, --textconv or -c.
GIT_SUBCOMMANDS = ("status", "log", "diff", "show")
GIT_FLAGS = {"--", "-s", "--short", "--porcelain", "-b", "--branch", "--oneline", "--stat", "-p", "--patch", "--cached",
             "--staged", "--name-only", "--name-status", "--graph", "--decorate", "--all", "--no-color", "-q",
             "--no-ext-diff", "--no-textconv"}
GIT_PREFIXES = ("--format=", "--pretty=", "--since=", "--until=", "--author=", "--grep=", "--max-count=", "-n")
HYPRCTL_READS = {"activewindow", "clients", "monitors", "workspaces", "activeworkspace", "version"}
T3_READS_CLI = (["thread", "list"], ["thread", "show"], ["environment", "list"])


def short_flag(word, letters):
    """Whether a word is a cluster of short options, such as -fn, that holds one of the letters."""
    return bool(re.fullmatch(r"-[A-Za-z0-9]+", word)) and bool(set(word[1:]) & set(letters))


def read_only(program, args):
    """Whether this program with these arguments only reads and ends by itself."""
    if program in SAFE_PROGRAMS:
        return True
    if program == "tail":  # -f and -F wait for more lines, which would hold the turn open.
        return not any(short_flag(a, "fF") or a.startswith(("--follow", "--retry", "--pid")) for a in args)
    if program == "file":  # -C compiles a magic file, which writes one.
        return not any(short_flag(a, "C") or a.startswith("--compile") for a in args)
    if program == "date":  # -s sets the clock.
        return all(a.startswith("+") or a in ("-u", "--utc", "-R", "-I") or a.startswith(("--iso-8601", "-I"))
                   for a in args)
    if program == "hostname":  # hostname NAME sets it.
        return not args
    if program == "git":
        return bool(args) and args[0] in GIT_SUBCOMMANDS and all(
            not a.startswith("-") or a in GIT_FLAGS or re.fullmatch(r"-\d+", a) or a.startswith(GIT_PREFIXES)
            for a in args[1:])
    if program == "hyprctl":  # One read and nothing else: no --batch, dispatch or keyword.
        return len(reads := [a for a in args if a != "-j"]) == 1 and reads[0] in HYPRCTL_READS
    if program == "t3":
        return args[:2] in T3_READS_CLI and all(not a.startswith("-") or a == "--json" for a in args[2:])
    # An active plugin's read-only program, with no arguments. Last, so it only adds: no built-in rule changes.
    return program in antigravity_home.POLICY["read_only_commands"] and not args
SCRIPTS = {ROOT / "desktop/relay.py", ROOT / "skills/delegate/scripts/t3_threads.py"}
# relay.py subcommands that pass with no card, as prefixes the way Claude Code matches its skills' allowed-tools
# lines. RELAY_SKILLS is exactly those lines' list; check() compares the two. RELAY_CARD holds skill entries that
# would show a card under agy anyway; it is empty, so dark and set pass as under Claude Code (the review agreed:
# going dark is reversible, and set only saves a checked setting for the next start). RELAY_PROMPT are the prompt's own
# commands. restart, reload and daily-restart are refused outright, by antigravity_home: Rook never restarts itself.
RELAY_SKILLS = ("get", "voices", "fonts", "dusts", "set ", "show ", "dark ", "media", "forge ", "wow-note ", "wow-data ", "project new ",
                "watch ", "work ", "inbox", "threads", "mailbox ", "handoff --print ", "clip ", "audition", "onboard ",
                "herdr agents", "herdr read ", "pi ")
RELAY_CARD = ()
RELAY_PROMPT = ("timer ", "remember ")
# Phone pairing passes with no card, though no shipped skill offers it: the owner's own workspace skill does.
RELAY_OWNER = ("device pair", "device list")
# relay.py's guarded sends to Herdr agents pass with no card here, like a thread send (SENDS below). They stay out
# of the skill's allowed-tools: under Claude Code they meet the person's own permission mode, as a T3 send does.
RELAY_SENDS = ("herdr send ", "herdr start ")
_OPTIONAL_SKILL_RELAY = {"wow": ("wow-note ", "wow-data ", "clip ")}


def _active_relay_skills():
    dropped = {cmd for skill, cmds in _OPTIONAL_SKILL_RELAY.items()
               if not any((folder / skill / "SKILL.md").is_file()
                          for folder in (ROOT / "skills", ROOT / "wow/skills"))
               for cmd in cmds}
    return tuple(cmd for cmd in RELAY_SKILLS if cmd not in dropped)


def handoff_prints(args):
    """Return whether relay.py handoff args include the --print flag."""
    if args[:1] != ["handoff"]:
        return False
    skip = False
    for arg in args[1:]:
        if skip:
            skip = False
        elif arg == "--print":
            return True
        elif arg.startswith("--"):
            skip = True
    return False


def relay_allowed(args):
    words = " ".join(args) + " "
    plugin = tuple(f"{name} " for name in antigravity_home.POLICY["relay_commands"])  # Active plugins' own commands.
    return not words.startswith(RELAY_CARD) and (words.startswith(_active_relay_skills() + RELAY_PROMPT + RELAY_SENDS
                                                                  + RELAY_OWNER + plugin) or handoff_prints(args))


# DECISION, Fable for the owner, 2026-11-22, for their review: a thread send or start passes without a card, as under Claude
# Code, where a send never shows one. Only a plain t3 thread send or start counts, alone on its command line, with
# its brief in a quoted heredoc. To put sends back on the card, make this ().
SENDS = ("thread send", "thread start")
# How agy's saved session names an API failure that it reported as a normal answer (from T3 Code's driver).
ERROR_STEP = 17
API_ERROR = re.compile(r"Error (\d{3}), Message: (.+?), Status: ([A-Z_]+|\d{3}[^,\n]*)", re.S)
STATUS_ERROR = re.compile(r"(?<![A-Z_])([A-Z_]+) \(code (\d{3})\): ([^\x00-\x1f]+)")


def send(process, message):
    process.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode())


def stream(kind, **fields):
    return {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": kind, **fields}}


def claude_tool(call, servers):
    """Return (name, input) for an ACP tool call, named as Claude Code names it."""
    name = call.get("name") or call.get("title") or "tool"
    tool_input = call.get("rawInput") if isinstance(call.get("rawInput"), dict) else call.get("args") or {}
    if name == "call_mcp_tool":  # agy loads a tool on demand through this one.
        server, tool, arguments = antigravity_home.mcp_call(tool_input)
        return f"mcp__{server}__{tool}", arguments
    if server := next((server for server in servers if name.startswith(f"mcp_{server}_")), None):
        return f"mcp__{server}__{name[len(server) + 5:]}", tool_input
    if name == "run_command":
        tool_input = {**tool_input, "command": tool_input.get("CommandLine", ""),
                      "run_in_background": tool_input.get("IsDaemon") is True}
    return NAMES.get(name, name), tool_input


def program_of(word):
    """The program a command word starts: a bare name, or a path that is exactly the one PATH finds for its name.
    Any other path, such as ./ls or /tmp/x/cat, gives None, so it is never taken for the safe program."""
    name = os.path.basename(word)
    if "/" not in word or word == shutil.which(name) or word in ("/usr/bin/python", "/usr/bin/python3", sys.executable):
        return name
    return None


def safe_shell(command):
    """Whether a shell command only reads, is one of Rook's own scripts, or is a thread send (SENDS)."""
    head = command[:found.start()] if (found := antigravity_home.heredoc(command)) else command
    if re.search(r"[;&<>`$()\\\n]", head):
        return False
    parts = head.split("|")
    for part in parts:
        try:
            words = shlex.split(part)
        except ValueError:
            return False
        if not words or not (program := program_of(words[0])):
            return False
        rest = words[1:]
        if found and not program.startswith("python") and program != "t3":
            return False
        if program == "t3" and any(rest[:2] == send.split() for send in SENDS):
            # Only the skill's form, t3 thread send ID - or start PATH -, alone on its command line.
            if len(parts) > 1 or len(rest) < 4 or rest[2].startswith("-") or rest[3] != "-":
                return False
            continue
        if not found and read_only(program, rest):
            continue
        if not (program.startswith("python") and len(words) > 1 and os.path.isabs(words[1])
                and (script := Path(words[1]).resolve()) in SCRIPTS):
            return False
        if script.name == "relay.py" and not relay_allowed(words[2:]):
            return False
    return True


def decide(name, tool_input, denied):
    """Answer an ask by the fixed policy: "deny", "allow", or "ask" the owner on the card. The hook in antigravity_home
    denies the same tools and commands first, so that the model hears why; this is the second line."""
    tool = name.split("__")[-1].strip().lower()
    raw = name not in NAMES.values() and not name.startswith("mcp__")  # A built-in agy tool Rook has no name for.
    if (name == "Agent" or raw and not antigravity_home.allowed_tool(name)
            or name.startswith("mcp__") and (name.split("__")[1] not in antigravity_home.servers()
                                             or antigravity_home.plugin_denied(name.split("__")[1], tool))
            or name.startswith("mcp__t3__") and (tool in denied or not antigravity_home.t3_allowed(tool, tool_input))
            or name in ("Write", "Edit", "notebook_edit") and antigravity_home.writes_rook(tool_input, tool_input.get("Cwd"))
            or name == "Bash" and (antigravity_home.denied_command(command := tool_input.get("command") or "")
                                   or antigravity_home.hidden_program(command)
                                   or antigravity_home.shell_writes_rook(command, tool_input.get("Cwd")))):
        return "deny"
    if PERMISSIONS == "full":
        return "allow"
    if PERMISSIONS == "ask":
        return "ask"
    if name in RAW_READS:
        return "allow"
    if name == "Bash":
        command = tool_input.get("command") or ""
        return "deny" if antigravity_home.denied_command(command) else "allow" if safe_shell(command) else "ask"
    own_mcp = tuple(f"mcp__{server}__" for server in antigravity_home.servers() if server != "t3")
    if (name in READS or name.startswith(own_mcp)
            or name.startswith("mcp__t3__") and tool in T3_READS):
        return "allow"
    return "ask"


TOOL_STEP = 132  # A tool's step in agy's session record, which holds the tool's output.
# Rook reads tool_result content only for these MCP calls: the watcher for a send, the mailbox for pending requests.
RECORDED_TOOLS = ("mcp__t3__t3_thread_send", "mcp__t3__t3_thread_launch", "mcp__t3__t3_pending_request")
UNSET = object()


def tool_output(update):
    """Return text output from an ACP tool_call_update, or empty string."""
    raw = update.get("rawOutput")
    return (raw["output"] if isinstance(raw, dict) and isinstance(raw.get("output"), str) else
            "".join(str((item.get("content") or {}).get("text", "")) for item in update.get("content") or ()
                    if isinstance(item, dict)) or (json.dumps(raw) if raw else ""))


def recorded_output(folder, session, call_id):
    """A tool's output from agy's in-memory session record: ACP's update for an MCP tool carries none, and the
    watcher needs what t3_thread_send returned. The step that names this tool call wins; "" when none does."""
    if not re.fullmatch(r"[\w-]+", session or "") or not call_id:
        return ""
    for attempt in range(3):  # agy may send the update just before it writes the step. Each try waits 0.3 s at most.
        if attempt:
            time.sleep(0.1)
        try:  # A short timeout: a locked record must not hold Rook's reader, and with it the watchdog.
            database = sqlite3.connect(f"file:{folder / APP / 'conversations' / session}.db?mode=ro", uri=True,
                                       timeout=0.2)
            try:
                rows = database.execute("SELECT step_payload FROM steps WHERE step_type = ? ORDER BY idx DESC "
                                        "LIMIT 20", (TOOL_STEP,)).fetchall()
            finally:
                database.close()
        except sqlite3.Error:
            continue
        for (payload,) in rows:
            text = bytes(payload or b"").decode(errors="replace")
            if re.search(re.escape(call_id) + r"(?!\d)", text) and (found := re.search(r"Completed At: [^\n]*\n(.*?)(?:\x1a|$)", text, re.S)):
                output = found[1].lstrip()
                try:  # A JSON answer, such as a send's, ends where its value ends, not at the record's next field.
                    return output[:json.JSONDecoder().raw_decode(output)[1]]
                except ValueError:
                    return found[1]
    return ""


def brief(text, limit=200):
    """agy's error text, cut at a word near limit characters: Rook speaks it."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:.") + "..."


# agy's exact limit on the bytes of tools a session declares is unknown. Run 49, in the live shape (real T3's four
# eager tools, --wow, brief show_scene), passed with 8,568 bytes of eager render and wow tools; run 47, with
# show_scene's full description, failed at 15,158 and agy left show_scene out. check() fails above this number, so a
# tool that grows past the room found in a real run is caught before a session drops it.
EAGER_BYTES_LIMIT = 9_500


def declared_sizes(command, env):
    """The JSON size of each tool a Rook tool server declares, from its own tools/list over stdio, started by its
    generated mcp_config.json command from outside the repo. None when the server does not answer within 60 seconds."""
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "rook", "version": "1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    server = subprocess.Popen(command, cwd=tempfile.gettempdir(), env={**os.environ, **env}, text=True,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:  # stdin stays open until the answer: a server may stop at the end of its input before it answers.
        server.stdin.write("".join(json.dumps(message) + "\n" for message in messages))
        server.stdin.flush()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and select.select([server.stdout], [], [], deadline - time.monotonic())[0]:
            line = server.stdout.readline()
            if not line:
                return None
            answer = json.loads(line) if line.startswith("{") else {}
            if answer.get("id") == 2:
                return {tool["name"]: len(json.dumps(tool)) for tool in answer["result"]["tools"]}
        return None
    finally:
        server.kill()
        server.wait()


def render_guide():
    """How to use show_scene, for Neon's system prompt: under Antigravity the tool's own description is brief, since
    agy left the full one out of a session with T3's tools (2026-11-23)."""
    import render  # Here, so that the harness loads fast.
    return "\n\nRender scenes. How to use your show_scene tool:\n\n" + render.TOOL_GUIDE + render.describe()


def failure(folder, session):
    """The error text when agy ended the turn on an API failure, which it reports as a normal answer."""
    if not re.fullmatch(r"[\w-]+", session or ""):
        return None
    try:
        database = sqlite3.connect(f"file:{folder / APP / 'conversations' / session}.db?mode=ro", uri=True,
                                   timeout=0.2)  # The reader waits on it: a locked record must not hold it.
        try:
            row = database.execute("SELECT step_type, substr(step_payload, 1, 16384) FROM steps "
                                   "ORDER BY idx DESC LIMIT 1").fetchone()
        finally:
            database.close()
    except sqlite3.Error:
        return None
    if not row or row[0] != ERROR_STEP:
        return None
    text = bytes(row[1] or b"").decode(errors="replace") if not isinstance(row[1], str) else row[1]
    if found := API_ERROR.search(text):
        return f"Antigravity failed: {brief(found[2])} ({brief(found[3], 40)})."
    if found := STATUS_ERROR.search(text):
        return f"Antigravity failed: {brief(found[3])} ({brief(found[1], 40)})."
    return "Antigravity stopped this turn because of an error."


def clear():
    shutil.rmtree(antigravity_home.HOME / APP, ignore_errors=True)


def signed_in(url):
    """Whether the owner's own agy sign-in to the tool server at url is there and not expired. Only the entry's presence
    and expiry are used; the token is never printed, logged or copied."""
    try:
        entry = json.loads(T3_TOKENS.read_text()).get(url)
    except (OSError, ValueError, AttributeError):
        return False
    if not isinstance(entry, dict) or not entry.get("token"):
        return False
    token = entry["token"] if isinstance(entry["token"], dict) else {}
    if token.get("refresh_token"):
        return True  # agy renews an expired access token with it.
    expiry = entry.get("expiry") or token.get("expiry")
    if not expiry or str(expiry).startswith("0001-01-01"):
        return True  # A token with no expiry, or Go's zero time for none, does not end by time.
    try:  # Go writes nanoseconds and Z; Python reads six digits and an offset.
        when = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", str(expiry)).replace("Z", "+00:00"))
        if when.tzinfo is None:  # No time zone: Go's own times are UTC.
            when = when.replace(tzinfo=timezone.utc)
        return when > datetime.now(timezone.utc) + timedelta(minutes=5)
    except (ValueError, TypeError, OverflowError):
        return False


def signed_out(error):
    # -32603 with "No browser is available here": agy has no sign-in and, under Rook, no browser to open (T3 Code's
    # antigravityAuthSupport.ts reads it the same way).
    return (error.get("code") == -32000 or "authenticat" in str(error.get("message")).lower()
            or error.get("code") == -32603 and str(error.get("message")).startswith("No browser is available here"))


class Prompt(Enum):
    """Lifecycle states of one ACP prompt sent to agy."""

    OPEN = 1
    HELD = 2
    FOLDED = 3
    CANCELLED = 4
    ABANDONED = 5
    DONE = 6


PROMPT_MOVES = {
    Prompt.OPEN: {Prompt.HELD, Prompt.FOLDED, Prompt.CANCELLED, Prompt.ABANDONED, Prompt.DONE},
    Prompt.HELD: {Prompt.CANCELLED, Prompt.DONE},
    Prompt.FOLDED: {Prompt.DONE},
    Prompt.CANCELLED: {Prompt.CANCELLED, Prompt.ABANDONED, Prompt.DONE},
    Prompt.ABANDONED: {Prompt.DONE},
    Prompt.DONE: set(),
}


class Antigravity(Harness):
    name = "Antigravity"  # In "Antigravity closed" and other errors.
    short = "Antigravity"  # In the permission card: "Antigravity requests Bash."
    # agy reports a tool call after it has started the tool, so a request with no tool mark may have run one.
    marks_tools_first = False
    # The defaults, when the settings name none. Low thinking for a voice: on the same turn Neon took 14.7 seconds at
    # low and 22.1 at medium, mostly in its last step, with the same answer. agent_effort medium or high restores more.
    model, effort = "gemini-4-neon", "low"
    # Rook's setup deadline (rook.py setup_deadline): agy falls back when it has sent nothing for setup_quiet seconds,
    # or at setup_limit in all. A working agy streams something every few seconds: in every captured turn its first
    # message came within 6 seconds. The first start of a day took over 30 seconds, and the next one 12.
    setup_quiet, setup_limit = 45, 90
    setup_problem = None  # Why the launch failed, such as a missing sign-in, for Rook's fallback sentence.
    permission_mode = "rook"  # pick() sets the setting's value at a start. A bare harness, as in the checks, is as before.

    def __init__(self, model=None, effort=None):
        super().__init__(model, effort)
        self.process, self.heard = None, 0

    def ready(self):
        """None when agy is installed, else why not, in one sentence, which also goes to the journal. Rook starts no
        agy to check: each start unpacks about 1 GB. The real launch reports a missing sign-in itself, and Rook then
        falls back with setup_problem's sentence."""
        if shutil.which("agy"):
            return None
        print("antigravity: not ready: agy is not installed.", file=sys.stderr)
        return "agy is not installed. Install the Antigravity CLI, or ask Rook to use Claude Code."

    def command(self, prompt, servers, session, plugin, denied):
        """The argv. It also rebuilds Rook's private agy folder, with no data folder. ACP takes the prompt and the
        servers in the session, so they wait here. T3's tool server comes along only when the owner's agy sign-in to it
        is there and current; otherwise Rook reaches T3 through the t3 command, as before.
        A ValueError from antigravity_home means its tables no longer match Rook's text."""
        global PERMISSIONS
        if "permission_mode" in vars(self):  # A start, by the setting: Rook's own allow policy only for rook.
            # Each mode is agy's own: full and rook pass what agy asks, and every other mode shows agy's own asks as
            # cards. Rook adds no allow list of its own (the owner, 2026-11-25).
            PERMISSIONS = "full" if self.permission_mode in ("rook", "full") else "ask"
        self.prompt, self.denied = prompt, denied
        self.servers = {name: server for name, server in servers.items() if "command" in server}
        self.names, self.t3 = list(servers), "t3" in servers
        url = servers.get("t3", {}).get("url")
        self.t3_url = url if url and signed_in(url) else None
        home = antigravity_home.build(wow="wow" in self.servers)
        eager = {spec["name"]: spec["eager_tools"] for spec in plugin_loader.servers()}  # Active plugins' tool servers.
        clear()
        # Rook's servers go in the private mcp_config.json, the one place where agy takes which tools it declares
        # up front (eager) and which it allows: in session/new, agy decides that itself.
        entries = {name: {"command": server["command"], "args": server.get("args", []),
                          "tools": {tool: {"eager": True} for tool in antigravity_home.EAGER_TOOLS.get(name, eager.get(name, ()))}}
                   for name, server in self.servers.items()}
        if "render" in entries:  # show_scene's guide goes in the system prompt, so agy can declare the tool.
            entries["render"]["env"] = {"ROOK_RENDER_BRIEF": "1"}
        if self.t3_url:  # The sign-in, by a link: agy reads it there, and nothing else is copied out.
            (home / APP).mkdir(parents=True)
            (home / APP / "mcp_oauth_tokens.json").symlink_to(T3_TOKENS)
            entries["t3"] = {"url": self.t3_url, "enabledTools": list(antigravity_home.T3_TOOLS),
                             "tools": {name: {"eager": True} for name in antigravity_home.T3_EAGER}}
        config = home / "config/mcp_config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"mcpServers": entries}))
        if self.permission_mode == "inherit":  # The private folder hides the person's own settings: copy how agy asks.
            try:
                own = json.loads(OWN_SETTINGS.read_text())
            except (OSError, ValueError):
                own = {}
            own = {key: own[key] for key in OWN_KEYS if isinstance(own, dict) and key in own}
            if own:
                (home / APP).mkdir(parents=True, exist_ok=True)
                (home / APP / "settings.json").write_text(json.dumps(own))
        return [*ENV, "agy", "acp", "--gemini-dir", str(home), "--app-data-dir", APP,
                *(["--dangerously-skip-permissions"] if self.permission_mode == "full" else [])]

    def setup(self, start, later, wow):
        """The setup turn's text. agy has every tool of the session's servers from the start."""
        return antigravity_home.setup(wow)

    def begin(self, process, session, uuid, text):
        """Start the handshake, and queue the setup turn until the session exists."""
        self.process, self.session = process, None
        self.next_id, self.calls, self.outbox, self.open, self.folded = 0, {}, [], [], []
        self.texting, self.answer, self.tools, self.asks, self.declined = False, "", set(), {}, None
        self.tool_names = {}  # Each tool call's name, by its id.
        self.cancelled = set()  # Prompts cancelled whose answers have not come yet.
        self.withdrawn = []  # Cards that a new request took back, for control_cancel_request.
        self.held = None  # (rpc, uuid) of a turn agy ended while its tool still ran, held open for the result.
        self.held_reported = False  # Whether Rook was notified that a background command is held.
        self.woke = self.release_now = False  # The held tool finished; a new request ends the held turn.
        self.abandoned = set()  # Prompts the watchdog ended whose answers have not come yet.
        self.prompt_states = {}  # rpc -> Machine tracking each prompt's life in log-only mode.
        self.folded_rpcs = []  # rpcs folded into self.folded until the steered turn ends.
        self.context, self.turn_began, self.first_words = 0, time.monotonic(), None  # For one journal line a turn.
        self.stale_until = 0  # Until then, late text and asks belong to a turn Rook cancelled.
        # How far the setup got, for one journal line: stage names and seconds, tool names, never the owner's words.
        self.began = self.heard = time.monotonic()
        self.setup_uuid, self.setup_done, self.stages, self.setup_tools = uuid, False, {}, []
        self.cwd = desk.process_cwd(getattr(process, "pid", None))
        self.call("initialize", INITIALIZE)
        self.outbox.append((uuid, [{"type": "text", "text": text}]))

    def turn(self, process, session, uuid, text, shots, steer):
        """Send one turn: JPEG images, then the text. A prompt sent while one runs steers it."""
        blocks = [{"type": "image", "mimeType": "image/jpeg", "data": base64.b64encode(shot).decode()}
                  for shot in shots] + [{"type": "text", "text": text}]
        # A card still open means the owner moved on without answering it, perhaps without seeing it. agy waits for that
        # answer before it reads this turn, so the card is declined and taken back, and this turn goes ahead.
        for request_id, (rpc, options) in list(self.asks.items()):
            self.choose(rpc, options, "reject_once", process)
            self.withdrawn.append(request_id)
            self.heard = time.monotonic()  # And from the card's end, when this turn took it back.
        self.asks.clear()
        if self.held:  # A new request ends the held turn first, with what it has, and the watchdog counts anew.
            self.release_now, self.first_words = True, None  # The new turn's journal numbers start now.
            self.heard = self.turn_began = time.monotonic()
        if self.session:
            self.prompt_now(uuid, blocks)
        else:
            self.outbox.append((uuid, blocks))

    def quiet(self):
        """How long agy may send nothing before the watchdog ends the turn."""
        return HELD_QUIET_SECONDS if self.held and not self.tools else STALL_SECONDS

    def held_tools(self):
        """Names of tools still running in the background of a held turn, never their inputs."""
        return list(dict.fromkeys(self.tool_names.get(tid, "command") for tid in sorted(self.tools)))

    def log_move(self, event, **fields):
        """Log an untabled prompt state move to stderr without any user text."""
        why = f" ({fields['why']})" if fields.get("why") else ""
        print(f"antigravity: {event} {fields.get('machine')} {fields.get('old')} -> {fields.get('new')}{why}",
              file=sys.stderr)

    def prompt_move(self, rpc, state, why=""):
        """Record a prompt state move in log-only mode and drop finished entries."""
        slot = self.prompt_states.get(rpc)
        if slot is None:
            slot = self.prompt_states[rpc] = machine.Machine("prompt", Prompt.OPEN, PROMPT_MOVES, self.log_move)
        slot.to(state, why)
        if state is Prompt.DONE:
            self.prompt_states.pop(rpc, None)

    def finish_folded(self, why):
        """Mark all folded prompts done when the turn they joined finishes."""
        for rpc in self.folded_rpcs:
            self.prompt_move(rpc, Prompt.DONE, why)
        self.folded_rpcs.clear()

    def release(self):
        """End a held turn: its result is the text since its last tool call, as Claude Code's is."""
        rpc, uuid = self.held
        self.prompt_move(rpc, Prompt.DONE, "release")
        self.finish_folded("release")
        self.turn_line(*self.held_line)  # The held turn's own numbers, kept when it was held.
        self.held, self.woke, self.release_now, self.declined, self.held_reported = None, False, False, None, False
        if rpc in self.open:
            self.open.remove(rpc)
        self.tools.clear()  # A command still running when a new request came is not the next turn's.
        yield from self.close_text()
        uuids, self.folded, answer, self.answer = self.folded + [uuid], [], self.answer, ""
        yield {"type": "result", "user_message_uuids": uuids, "result": answer, "terminal_reason": "completed",
               "is_error": False, "errors": []}

    def turn_line(self, began, first, usage):
        """One journal line a turn: speed and size, never content. A slowdown shows here before the owner feels it."""
        print(f"antigravity: turn {round(time.monotonic() - began, 1)} s, first output "
              f"{'none' if first is None else round(first, 1)} s; context {self.context} tokens; input "
              f"{usage.get('inputTokens')}, cached {usage.get('cachedReadTokens')}, thinking {usage.get('thoughtTokens')}, "
              f"output {usage.get('outputTokens')}", file=sys.stderr)

    def flush(self):
        """What Rook's side asked for since the last message: cards taken back, and a held turn to end."""
        for request_id in self.withdrawn:
            yield {"type": "control_cancel_request", "request_id": request_id}
        self.withdrawn.clear()
        if self.release_now and self.held:
            yield from self.release()

    def stalled(self, problem=UNSET):
        """End the open turn when agy has sent nothing for STALL_SECONDS: tell the owner in words Rook speaks, cancel the
        prompt so the session stays usable, and drop any late answer to it. Steered turns end with it, not silently."""
        if self.held and not self.tools:  # agy ended this turn itself; its wake said nothing more. No stall.
            yield from self.release()
            return
        if self.held:  # Its command ran past STALL_SECONDS. Its prompt was answered: no late answer comes.
            self.prompt_move(self.held[0], Prompt.DONE, "held_stalled")
            self.open.remove(self.held[0])
            self.folded.append(self.held[1])  # handle() already dropped its calls entry.
            self.held, self.woke, self.held_reported = None, False, False
        uuids = self.folded + [self.calls[rpc][1] for rpc in self.open]
        if problem is UNSET:
            problem = failure(antigravity_home.HOME, self.session)  # A quota or API error should sound like one.
        wedged = bool(self.abandoned)  # An earlier stalled turn never got its answer: agy has stopped for good.
        print(f"antigravity: no word from agy for {self.quiet()} s with a turn open; the turn ends"
              + ("; agy is wedged, so it ends too" if wedged else ""), file=sys.stderr)
        send(self.process, {"method": "session/cancel", "params": {"sessionId": self.session}})
        for rpc in self.open:
            self.calls[rpc] = ("abandoned", self.calls[rpc][1])
            self.prompt_move(rpc, Prompt.ABANDONED, "stalled")
        self.cancelled.update(self.open)  # Its late asks are answered cancelled: no card, and they do not run.
        self.abandoned.update(self.open)  # Its late text is dropped: it would be spoken as the next turn's.
        self.stale_until = time.monotonic() + STALE_SECONDS
        self.open, self.folded, self.answer = [], [], ""
        self.finish_folded("stalled")
        self.tools.clear()
        yield from self.close_text()
        yield {"type": "result", "user_message_uuids": uuids, "result": problem or STALLED, "terminal_reason": "stalled",
               "is_error": False, "errors": []}
        if wedged:  # Rook's reader then sees it closed; the next request starts a new agy.
            try:
                self.process.kill()
            except ProcessLookupError:
                pass

    def stale(self):
        """Whether late text and asks still belong to a turn Rook cancelled. STALE_SECONDS says why it ends."""
        return time.monotonic() < self.stale_until

    def settle(self, rpc):
        """A prompt's answer came. agy answers prompts in order, so every older cancelled prompt is done too."""
        settled = {older for older in self.cancelled | self.abandoned if older <= rpc}
        self.cancelled = {older for older in self.cancelled if older > rpc}
        self.abandoned = {older for older in self.abandoned if older > rpc}
        for older in sorted(settled):
            if older in self.prompt_states:
                self.prompt_move(older, Prompt.DONE, "settled")

    def interrupt(self, process):
        """Cancel the running turn and any queued ones. A permission ask still open is answered cancelled, and so is
        any ask that comes before the cancelled prompts end."""
        self.outbox.clear()
        if self.held:  # Stop ends a held turn too, with what it has.
            self.release_now = True
        if self.session:
            send(process, {"method": "session/cancel", "params": {"sessionId": self.session}})
            for rpc in self.open:
                self.prompt_move(rpc, Prompt.CANCELLED, "interrupt")
            self.cancelled.update(self.open)
            self.stale_until = time.monotonic() + STALE_SECONDS
        for rpc, options in self.asks.values():
            send(process, {"id": rpc, "result": {"outcome": {"outcome": "cancelled"}}})
        self.asks.clear()

    def permit(self, process, ask, allowed, answers=None, reason=None):
        """Answer a permission ask that the owner's card decided. answers are the card's answers to a question. An ask
        that a cancel already answered gets no second answer. ACP's answer carries no reason, so reason goes unsaid."""
        if ask["request_id"] not in self.asks:
            return
        rpc, options = self.asks.pop(ask["request_id"])
        self.heard = time.monotonic()  # The watchdog counts from the owner's answer, not from before the card.
        if answers is not None:
            wanted = {str(answer).strip().lower() for answer in answers.values()}
            option = next((option for option in options
                           if (option.get("name") or option.get("optionId", "")).strip().lower() in wanted), None)
            outcome = ({"outcome": "selected", "optionId": option["optionId"]} if option else {"outcome": "cancelled"})
            send(process, {"id": rpc, "result": {"outcome": outcome}})
        else:
            self.declined = None if allowed else ask["request"]["tool_name"]
            self.choose(rpc, options, "allow_once" if allowed else "reject_once", process)

    async def read(self, messages):
        """Rook's messages, in Claude Code's shapes, from agy's JSON-RPC. It also answers agy's requests, through
        the process that begin() kept. When agy closes, or Rook stops and cancels this reader, the session's files
        go. Rook leaves with os._exit, which runs no exit handlers, so this is the clean stop's removal."""
        process, waiting = self.process, None
        stream = messages.__aiter__()
        try:
            while True:
                for converted in self.flush():
                    yield converted
                # The watchdog: a prompt open, no card waiting on the owner, and nothing from agy for STALL_SECONDS. It
                # looks again each second, since a prompt or a take-back from Rook's side does not wake this wait.
                watching = self.open and not self.asks
                limit = min(1, max(0.1, self.heard + self.quiet() - time.monotonic())) if watching else 1
                waiting = waiting or asyncio.ensure_future(stream.__anext__())
                if not (await asyncio.wait({waiting}, timeout=limit))[0]:
                    if watching and time.monotonic() - self.heard >= self.quiet():
                        problem = (None if self.held and not self.tools
                                   else await asyncio.to_thread(failure, antigravity_home.HOME, self.session))
                        if self.open and not self.asks and not self.release_now and time.monotonic() - self.heard >= self.quiet():
                            for converted in self.stalled(problem=problem):
                                yield converted
                    continue
                try:
                    message = waiting.result()
                except StopAsyncIteration:
                    break
                waiting = None
                self.heard = time.monotonic()  # Rook's setup deadline waits while agy keeps sending.
                if not self.setup_done:
                    self.trace(message)
                for converted in self.flush():  # Before agy's next words, which may belong to the new request.
                    yield converted
                prepared = await self.prepare(message)
                for converted in self.flush():  # Flush anything queued while the worker thread ran.
                    yield converted
                for converted in self.handle(message, prepared):
                    if (converted["type"] == "result" and not self.setup_done
                            and self.setup_uuid in converted["user_message_uuids"]):
                        self.setup_done = True
                        print(f"antigravity: setup answered {self.progress()}", file=sys.stderr)
                    yield converted
        finally:
            if waiting is not None:
                waiting.cancel()
            if self.process is process and not self.setup_done:
                print(f"antigravity: setup ended unanswered {self.progress()}", file=sys.stderr)
            if self.process is process:  # Not the files of a newer launch.
                clear()

    def trace(self, message):
        """Note the first time each setup stage happened."""
        at = round(time.monotonic() - self.began, 1)
        kind = message.get("method") or self.calls.get(message.get("id"), (None,))[0]
        update = ((message.get("params") or {}).get("update") or {})
        stage = ({"initialize": "initialized", "session/new": "session opened", "prompt": "answer"}.get(kind)
                 or {"agent_thought_chunk": "first thought", "agent_message_chunk": "first text"}.get(
                     update.get("sessionUpdate")))
        if stage and "error" in message:  # Such as a missing sign-in: say so, with the error's code only.
            stage = f"{kind} failed ({(message.get('error') or {}).get('code')})"
        if stage:
            self.stages.setdefault(stage, at)
        if update.get("sessionUpdate") == "tool_call":
            self.setup_tools.append(f"{update.get('name')} at {at}")

    def progress(self):
        stages = ", ".join(f"{stage} {at}" for stage, at in self.stages.items()) or "nothing from agy"
        return (f"after {round(time.monotonic() - self.began, 1)} s: {stages}"
                + (f"; tools: {', '.join(self.setup_tools)}" if self.setup_tools else ""))

    # ---- the converter ----

    def call(self, method, params, kind=None, uuid=None):
        self.next_id += 1
        self.calls[self.next_id] = (kind or method, uuid)
        send(self.process, {"id": self.next_id, "method": method, "params": params})
        return self.next_id

    def prompt_now(self, uuid, blocks):
        if not self.open:
            self.answer = ""  # Text agy wrote with no prompt open, such as a late wake, is not this answer.
            self.heard = self.turn_began = time.monotonic()  # The watchdog counts from the prompt, not an old message.
            self.first_words = None
        if uuid == self.setup_uuid:
            self.stages.setdefault("setup sent", round(time.monotonic() - self.began, 1))
        rpc = self.call("session/prompt", {"sessionId": self.session or "", "prompt": blocks},
                        "prompt", uuid)
        self.open.append(rpc)
        self.prompt_states[rpc] = machine.Machine("prompt", Prompt.OPEN, PROMPT_MOVES, self.log_move)

    def choose(self, rpc, options, kind, process=None):
        option = next((option for option in options if option.get("kind") == kind), None)
        send(process or self.process, {"id": rpc, "result": {"outcome": (
            {"outcome": "selected", "optionId": option["optionId"]} if option else {"outcome": "cancelled"})}})

    def close_text(self):
        if self.texting:
            self.texting = False
            yield stream("content_block_stop")

    def system_append(self):
        """Build the system prompt append, including project memory lines."""
        return (antigravity_home.prompt(self.prompt, self.cwd, beats=self.narrate_beats)
                + settings.render((T3_LOST if self.t3_url else "") + (render_guide() if "render" in self.servers else "")))

    def needs_recorded(self, update):
        """Return whether this tool update needs a session-record lookup."""
        call_id = update.get("toolCallId")
        return (update.get("sessionUpdate") == "tool_call_update" and update.get("status") == "completed"
                and call_id in self.tools and self.tool_names.get(call_id) in RECORDED_TOOLS
                and not tool_output(update))

    def needs_failure(self, kind, rpc, message):
        """Return whether this prompt response needs a session-record error lookup."""
        if kind != "prompt" or message.get("error"):
            return False
        if (message.get("result") or {}).get("stopReason") != "end_turn":
            return False
        held = bool(self.tools and self.open == [rpc] and rpc not in self.cancelled and not self.held)
        folded = len(self.open) > 1 and rpc not in self.cancelled
        return not held and not folded

    async def prepare(self, message):
        """Run blocking lookups for one ACP message in a worker thread."""
        method, rpc = message.get("method"), message.get("id")
        if method == "session/update":
            update = (message.get("params") or {}).get("update") or {}
            if self.needs_recorded(update):
                return {"recorded": await asyncio.to_thread(
                    recorded_output, antigravity_home.HOME, self.session, update["toolCallId"])}
        elif not method and rpc in self.calls:
            kind = self.calls[rpc][0]
            if kind == "initialize" and not message.get("error"):
                return {"append": await asyncio.to_thread(self.system_append)}
            if self.needs_failure(kind, rpc, message):
                return {"problem": await asyncio.to_thread(failure, antigravity_home.HOME, self.session)}
        return {}

    def handle(self, message, prepared=None):
        prepared = prepared or {}
        method, rpc = message.get("method"), message.get("id")
        if method == "session/update":
            yield from self.update((message.get("params") or {}).get("update") or {}, prepared)
        elif method == "session/request_permission":
            yield from self.ask(rpc, message.get("params") or {})
        elif method:
            if rpc is not None:
                send(self.process, {"id": rpc, "error": {"code": -32601, "message": "Rook does not offer this."}})
        elif rpc in self.calls:
            yield from self.answered(*self.calls.pop(rpc), rpc, message, prepared)

    def answered(self, kind, uuid, rpc, message, prepared=None):
        prepared = prepared or {}
        error = message.get("error")
        if kind == "initialize" and not error:
            append = prepared["append"] if "append" in prepared else self.system_append()
            self.call("session/new", {"cwd": self.cwd, "_meta": {"antigravity": {"systemPrompt": {"append": append}}},
                                      "mcpServers": []})  # Rook's servers come from mcp_config.json.
        elif kind == "session/new" and not error:
            self.session = message["result"]["sessionId"]
            mode = AGY_MODES.get(self.permission_mode)  # None for inherit: the person's own agentMode rules.
            for option, value in (("model", self.model), ("thought_level", EFFORTS.get(self.effort, "low")),
                                  *((("mode", mode),) if mode else ())):
                self.call("session/set_config_option", {"sessionId": self.session, "configId": option, "value": value})
            yield {"type": "system", "subtype": "init",
                   "mcp_servers": [{"name": name, "status": "connected"} for name in self.servers]
                   + ([{"name": "t3", "status": "connected" if self.t3_url else "needs-auth"}] if self.t3 else [])}
            for uuid, blocks in self.outbox:
                self.prompt_now(uuid, blocks)
            self.outbox.clear()
        elif kind in ("initialize", "session/new"):
            # With no session, agy is no use. Ending it ends the stream before the setup answer, so Rook falls back.
            print(f"antigravity: {kind} failed{', not signed in' if signed_out(error) else ''}: {error}",
                  file=sys.stderr)
            self.setup_problem = ("Antigravity is not signed in. Run agy in a terminal and finish the Google sign-in, "
                                  "then restart Rook." if signed_out(error)
                                  else f"Antigravity refused a session: {brief((error or {}).get('message'))}.")
            self.process.kill()
        elif kind == "session/set_config_option" and error:
            print(f"antigravity: an option was refused: {error}", file=sys.stderr)
        elif kind == "abandoned":  # The late answer to a turn the watchdog ended.
            self.settle(rpc)
        elif kind == "prompt":
            if ((message.get("result") or {}).get("stopReason") == "end_turn" and not error and self.tools
                    and self.open == [rpc] and rpc not in self.cancelled and not self.held):
                self.prompt_move(rpc, Prompt.HELD, "held")
                self.held = (rpc, uuid)  # agy ended the turn with its command in the background: hold it open.
                self.held_line = (self.turn_began, self.first_words, (message.get("result") or {}).get("usage") or {})
                self.held_reported = True
                yield from self.close_text()
                yield {"type": "rook_held", "active": True, "turn": uuid, "tools": self.held_tools()}
                return
            self.open.remove(rpc)
            if not self.open:  # A tool agy never finished must not hold the next turn open.
                self.tools.clear()
            interrupted = rpc in self.cancelled
            self.settle(rpc)
            yield from self.close_text()
            if self.open and not interrupted:  # A later prompt steered this one: its text belongs to that prompt.
                self.prompt_move(rpc, Prompt.FOLDED, "folded")
                self.folded_rpcs.append(rpc)
                self.folded.append(uuid)
                return
            if not interrupted:
                self.prompt_move(rpc, Prompt.DONE, "answered")
                self.finish_folded("answered")
            # A turn the owner stopped ends alone; it never folds into the next one.
            uuids, self.folded = ([uuid], self.folded) if interrupted else (self.folded + [uuid], [])
            stop = (message.get("result") or {}).get("stopReason")
            problem = (f"Antigravity refused the request: {error.get('message')}" if error else
                       "You have reached your Antigravity quota for now." if stop == "refusal" else
                       (prepared["problem"] if "problem" in prepared
                        else failure(antigravity_home.HOME, self.session))
                       if stop == "end_turn" else None)
            answer, self.answer, declined, self.declined = self.answer, "", self.declined, None
            self.turn_line(self.turn_began, self.first_words, (message.get("result") or {}).get("usage") or {})
            if declined and not answer.strip() and not problem and stop == "end_turn":
                answer = f"Antigravity ended the turn when {declined} was declined."  # agy says nothing then.
            yield {"type": "result", "user_message_uuids": uuids, "result": problem or answer,
                   "terminal_reason": "error" if problem else "completed" if stop == "end_turn" else stop,
                   "is_error": bool(problem), "errors": [problem] if problem else []}

    def update(self, update, prepared=None):
        prepared = prepared or {}
        kind = update.get("sessionUpdate")
        if self.first_words is None and self.open:  # agy's first sign of life, of any kind, such as a thought.
            self.first_words = time.monotonic() - self.turn_began
        if kind == "agent_message_chunk":
            text = (update.get("content") or {}).get("text")
            if not isinstance(text, str) or not text or self.abandoned and self.stale():  # An ended turn's.
                return
            if not self.texting:
                self.texting = True
                yield stream("content_block_start", content_block={"type": "text", "text": ""})
            self.answer += text
            yield stream("content_block_delta", delta={"type": "text_delta", "text": text})
        elif kind == "agent_thought_chunk":  # Dropped by default; opt-in emits non-answer thought events.
            if not self.narrate_thoughts:
                return
            text = (update.get("content") or {}).get("text")
            if isinstance(text, str) and text and not (self.abandoned and self.stale()):
                yield {"type": "thought", "text": text}
        elif kind == "tool_call":
            yield from self.close_text()
            name, tool_input = claude_tool(update, self.names)
            self.answer = ""  # Like Claude Code's result: the text after the last tool call.
            if update.get("status") not in ("completed", "failed"):  # agy sends a declined call's twin born failed.
                self.tools.add(update.get("toolCallId"))
            self.tool_names[update.get("toolCallId")] = name
            yield stream("content_block_start", content_block={"type": "tool_use", "id": update.get("toolCallId"),
                                                               "name": name, "input": {}})
            yield {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": update.get("toolCallId"), "name": name, "input": tool_input}]}}
        elif kind == "tool_call_update" and update.get("status") in ("completed", "failed") \
                and update.get("toolCallId") in self.tools:
            self.tools.discard(update["toolCallId"])
            self.woke = self.woke or bool(self.held and not self.tools)  # The held turn's command finished.
            output = tool_output(update)
            if (not output and update["status"] == "completed"
                    and self.tool_names.get(update["toolCallId"]) in RECORDED_TOOLS):
                output = (prepared["recorded"] if "recorded" in prepared
                          else recorded_output(antigravity_home.HOME, self.session, update["toolCallId"]))
            yield {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": update["toolCallId"], "content": output,
                 "is_error": update["status"] == "failed"}]}}
            if self.held and not self.tools and self.held_reported:
                self.held_reported = False
                yield {"type": "rook_held", "active": False, "turn": self.held[1]}
        elif kind == "usage_update":  # The end of one model step: text after it is a new block, as in Claude Code.
            self.context = update.get("used") or self.context  # Tokens in the session's context now.
            spoke = self.texting  # A step that only called a tool, such as command_status, has said nothing yet.
            yield from self.close_text()
            if self.held and self.woke and not self.tools and spoke:  # agy's wake after the held command has spoken.
                yield from self.release()

    def ask(self, rpc, params):
        call, options = params.get("toolCall") or {}, params.get("options") or []
        if self.cancelled and self.stale():  # It belongs to a turn Rook cancelled: no card, and it does not run.
            send(self.process, {"id": rpc, "result": {"outcome": {"outcome": "cancelled"}}})
            return
        if str(call.get("toolCallId", "")).startswith("interaction_"):  # A question for the owner, not an approval.
            name, verdict = "AskUserQuestion", "ask"
            tool_input = {"questions": [{"question": call.get("title") or "Choose an option.", "header": "Question",
                                         "multiSelect": False, "options": [
                                             {"label": option.get("name") or option.get("optionId"), "description": ""}
                                             for option in options]}]}
        else:
            name, tool_input = claude_tool(call, self.names)
            verdict = decide(name, tool_input, self.denied)
        if verdict != "ask":
            # The journal is on disk: the verdict and the tool's name only, never its input, which holds the owner's words.
            print(f"antigravity: {verdict} {name}", file=sys.stderr)
            self.declined = name if verdict == "deny" else self.declined
            self.choose(rpc, options, "allow_once" if verdict == "allow" else "reject_once")
            return
        request_id = f"acp-{rpc}"
        self.asks[request_id] = (rpc, options)
        yield {"type": "control_request", "request_id": request_id, "rpc": rpc, "options": options,
               "request": {"subtype": "can_use_tool", "tool_name": name, "input": tool_input}}


def check():
    """Self-check of the converter and the policy: captured agy lines in, Rook's shapes out."""
    from types import SimpleNamespace
    import tempfile
    global PERMISSIONS, recorded_output, failure
    assert machine.Machine.strict is False
    saved_strict, machine.Machine.strict = machine.Machine.strict, True
    mode, PERMISSIONS = PERMISSIONS, "strict"  # The card tests below need the strict policy; full is checked last.
    home = antigravity_home.HOME = Path(tempfile.mkdtemp(prefix="rook-antigravity-check-"))  # Never a live Rook's.
    antigravity_home.build, antigravity_home.prompt = lambda wow=False: home, lambda text, workspace, beats=False: text
    sent = []
    process = SimpleNamespace(pid=None, stdin=SimpleNamespace(write=lambda line: sent.append(json.loads(line))))
    # A failed handshake, such as a missing sign-in, ends agy, so the stream ends and Rook falls back.
    killed = []
    agy = Antigravity()
    assert (agy.model, agy.effort, Antigravity("gemini-4-carbon", "max").effort) == ("gemini-4-neon", "low", "max")
    agy.command("PROMPT", {}, "s", None, ())
    agy.begin(SimpleNamespace(pid=None, kill=lambda: killed.append(1), stdin=SimpleNamespace(write=lambda line: None)),
              "s", "setup", "Setup.")
    assert not list(agy.handle({"id": 1, "error": {"code": -32000, "message": "Authentication required"}})) and killed
    assert agy.setup_problem == "Antigravity is not signed in. Run agy in a terminal and finish the Google sign-in, then restart Rook."  # The sentence Rook falls back with.
    assert signed_out({"code": -32603, "message": "No browser is available here to sign in."})
    # Review 3, fix 8: what Rook speaks of agy's error stays short.
    long = brief("word " * 100)
    assert len(long) <= 203 and long.endswith("word...") and brief("Quota exceeded") == "Quota exceeded"
    assert not signed_out({"code": -32603, "message": "Internal error."})
    agy = Antigravity(None, "max")
    agy.command("PROMPT", {"render": {"command": "uv", "args": []}, "t3": {"type": "http", "url": "x"}}, "s", None,
                ("t3_project_delete",))
    agy.begin(process, "s", "setup", "Setup.")
    out = lambda message: list(agy.handle(message))  # noqa: E731
    update = lambda fields: {"method": "session/update", "params": {"update": fields}}  # noqa: E731
    asked = lambda rpc, call, options: {"id": rpc, "method": "session/request_permission",  # noqa: E731
                                        "params": {"toolCall": call, "options": options}}
    chunk = lambda text: update({"sessionUpdate": "agent_message_chunk",  # noqa: E731
                                 "content": {"type": "text", "text": text}})
    assert sent[-1]["method"] == "initialize" and not out({"id": 1, "result": {}})
    assert sent[-1]["method"] == "session/new"
    assert sent[-1]["params"]["_meta"]["antigravity"]["systemPrompt"]["append"] == settings.render("PROMPT" + render_guide())
    assert sent[-1]["params"]["mcpServers"] == []  # Every server comes from mcp_config.json, render's tools eager.
    render = json.loads((home / "config/mcp_config.json").read_text())["mcpServers"]["render"]
    assert render["command"] == "uv" and render["tools"]["show_scene"] == {"eager": True}
    # The eager render and wow tools stay within the room a real session had (see EAGER_BYTES_LIMIT).
    # Read the generated mcp_config.json entries back and run their exact launch commands from outside the repo.
    if uv := shutil.which("uv"):
        mcp_servers = {name: {"command": uv, "args": ["run", "--script", str(ROOT / source)]}
                       for name, source in antigravity_home.SERVER_SOURCES.items()}
        Antigravity(None, "max").command("PROMPT", mcp_servers, "s", None, ("t3_project_delete",))
        written = json.loads((home / "config/mcp_config.json").read_text())["mcpServers"]
        eager = 0
        for server in antigravity_home.SERVER_SOURCES:
            entry = written[server]
            sizes = declared_sizes([entry["command"], *entry["args"]], entry.get("env", {}))
            assert sizes is not None, f"the {server} server did not list its tools"
            eager += sum(sizes[tool] for tool in antigravity_home.EAGER_TOOLS[server])
        assert eager <= EAGER_BYTES_LIMIT, (f"eager render and wow tools declare {eager} bytes; a real session had "
                                            f"room for about {EAGER_BYTES_LIMIT}")
    else:
        print("agy_harness check: uv is missing, so the declared size of the eager tools was not measured.")
    # 2026-11-23: with T3's tools, agy left out show_scene's 6,400-character description. The brief form goes to agy,
    # and the guide to Neon's prompt; Claude Code keeps the full description.
    assert render["env"] == {"ROOK_RENDER_BRIEF": "1"}
    import render as render_module
    guide = render_guide()
    assert render_module.TOOL_GUIDE in guide and render_module.describe() in guide
    source = (ROOT / "desktop/render_tool.py").read_text()
    brief_when = re.search(r'BRIEF_WHEN = \((.*?)\)\n', source, re.S)[1]
    assert len(brief_when) < 400 and "Render scenes" in brief_when and "Render scenes." in guide
    init = out({"id": 2, "result": {"sessionId": "sid"}})
    assert init[0]["mcp_servers"] == [{"name": "render", "status": "connected"}, {"name": "t3", "status": "needs-auth"}]
    assert [(m["params"]["configId"], m["params"]["value"]) for m in sent[-4:-1]] == [
        ("model", "gemini-4-neon"), ("thought_level", "xhigh"), ("mode", "default")]
    assert sent[-1]["method"] == "session/prompt" and sent[-1]["params"]["sessionId"] == "sid"
    # From captures/08: thinking is dropped, a tool call ends the text block, and Bash carries its command.
    shapes = out(chunk("Checking.")) + out(update({"sessionUpdate": "agent_thought_chunk",
                                                   "content": {"type": "text", "text": "hmm"}}))
    call = {"sessionUpdate": "tool_call", "toolCallId": "c1", "name": "run_command", "status": "in_progress",
            "kind": "execute", "rawInput": {"CommandLine": "touch x.txt", "WaitMsBeforeAsync": 5000}}
    shapes += out(update(call))
    assert [s["event"]["type"] for s in shapes[:3]] == ["content_block_start", "content_block_delta",
                                                        "content_block_stop"]
    assert shapes[3]["event"]["content_block"]["name"] == "Bash"
    bash_input = shapes[4]["message"]["content"][0]["input"]
    assert bash_input["command"] == "touch x.txt" and bash_input["run_in_background"] is False
    options = [{"optionId": "allow", "kind": "allow_once"}, {"optionId": "deny", "kind": "reject_once"}]
    card = out(asked("1", call, options))
    assert card[0]["request"] == {"subtype": "can_use_tool", "tool_name": "Bash", "input": bash_input}
    agy.permit(process, card[0], True)
    assert sent[-1] == {"jsonrpc": "2.0", "id": "1",
                        "result": {"outcome": {"outcome": "selected", "optionId": "allow"}}}
    done = out(update({**call, "sessionUpdate": "tool_call_update", "status": "completed",
                       "rawOutput": {"output": "ok", "exit_code": 0}}))
    assert done[0]["message"]["content"][0] == {"type": "tool_result", "tool_use_id": "c1", "content": "ok",
                                                "is_error": False}
    # From captures/21: an MCP tool keeps its server, and a render call passes without a card.
    mcp = {"sessionUpdate": "tool_call", "toolCallId": "c2", "name": "mcp_render_show_scene",
           "rawInput": {"title": "t"}}
    assert out(update(mcp))[1]["message"]["content"][0]["name"] == "mcp__render__show_scene"
    assert claude_tool({"name": "call_mcp_tool", "rawInput": {"ServerName": "t3", "ToolName": "t3_thread_send",
                                                              "Arguments": {"threadId": "x"}}}, ["t3"]) \
        == ("mcp__t3__t3_thread_send", {"threadId": "x"})
    assert not out(asked("2", mcp, options)) and sent[-1]["result"]["outcome"]["optionId"] == "allow"
    out(update({**mcp, "sessionUpdate": "tool_call_update", "status": "completed"}))  # Before its turn ends.
    # From captures/23: a second prompt steers the first. The first's early end_turn folds into the second.
    out(chunk("Done. "))
    agy.turn(process, "s", "steer", "Stop.", [b"\xff\xd8"], True)
    assert sent[-1]["params"]["prompt"][0] == {"type": "image", "mimeType": "image/jpeg", "data": "/9g="}
    assert out({"id": 6, "result": {"stopReason": "end_turn"}}) == [stream("content_block_stop")]
    out(chunk("Stopped."))
    result = out({"id": 7, "result": {"stopReason": "end_turn"}})[-1]
    assert (result["user_message_uuids"], result["result"], result["terminal_reason"]) \
        == (["setup", "steer"], "Done. Stopped.", "completed")
    # A question becomes AskUserQuestion, and the card's answer picks its option.
    ask = out(asked("3", {"toolCallId": "interaction_1", "title": "Red or blue?"},
                    [{"optionId": "r", "name": "Red"}, {"optionId": "b", "name": "Blue"}]))[0]
    assert ask["request"]["tool_name"] == "AskUserQuestion"
    assert ask["request"]["input"]["questions"][0]["options"][1]["label"] == "Blue"
    agy.permit(process, ask, True, {"Red or blue?": "blue"})
    assert sent[-1]["result"]["outcome"] == {"outcome": "selected", "optionId": "b"}
    # The policy.
    bash = lambda command: decide("Bash", {"command": command}, ("t3_project_delete",))  # noqa: E731
    relay = f"/usr/bin/python {ROOT}/desktop/relay.py"
    assert [bash(c) for c in ("ls -la", "git status", "hyprctl activewindow -j", "t3 thread list rook",
                              f"{relay} timer set 10m", f"{relay} handoff --print - <<'EOF'\nt3 project remove x\nEOF"
                              )] == ["allow"] * 6
    assert [bash(c) for c in ("t3 project remove demo", "t3 'project' remove demo", "bash -c 't3 environment unlink x'",
                              "gh pr merge 5", "cat <<'EOF' | sh\nt3 auth session\nEOF",
                              # A body with its own end line runs what follows it, so it is not a brief.
                              "t3 thread send a - --json <<'B'\nhi\nB\nt3 project remove p\nB")] == ["deny"] * 6
    # Behind global options, other verbs, a variable, or gh api: refused like the plain forms.
    assert [bash(c) for c in ("t3 --log-level none project remove x", "gh -R o/r pr merge 1", "t3 project rm x",
                              "t3 project delete x", "p=project; t3 $p remove x", "gh api -X PUT repos/o/r/pulls/1/merge",
                              "echo 't3 project remove x' | sh", "xargs t3 project remove <<< x",
                              "/home/user/.t3/bin/t3 environment unlink remote")] == ["deny"] * 9
    # In every mode: a program from a variable, Rook stopping itself, and writes in Rook's own code (review, 2026-11-23).
    assert [bash(c) for c in ("T=t3; $T project remove demo", "systemctl --user stop rook", "pkill -f rook.py",
                              "python3 -m relay reload overlay", "gh alias set m 'pr merge'")] == ["deny"] * 5
    assert decide("Write", {"TargetFile": str(ROOT / "desktop/rook.py")}, ()) == "deny"
    assert decide("Edit", {"TargetFile": "/tmp/rook-note.txt"}, ()) != "deny"
    # agy 1.5's file tools are Rook's Write and Edit: its notes pass, its own code never, under any path form.
    assert claude_tool({"name": "edit_file", "rawInput": {"TargetFile": "/x"}}, [])[0] == "Edit"
    assert claude_tool({"name": "write_file", "rawInput": {"TargetFile": "/x"}}, [])[0] == "Write"
    assert decide("Edit", {"TargetFile": str(desk.config_dir() / "rook/model-preferences.md")}, ()) != "deny"
    assert decide("Write", {"FilePath": f"{ROOT.name}/desktop/rook.py", "Cwd": str(ROOT.parent)}, ()) == "deny"
    assert decide("Write", {"TargetFile": "~/.ssh/authorized_keys"}, ()) == "deny"  # A protected root, too.
    assert decide("Read", {"Path": f"{Path.home()}/.agents/skills/some-skill/SKILL.md"}, ()) == "allow"
    assert bash("t3 thread start /home/x/rook - --json --title \"Pair the link remover\" --provider claudeAgent "
                "--model claude-opus-5-5 <<'B'\nRemove the project link.\nB") == "allow"
    assert [bash(c) for c in ("touch x", "rm -rf /tmp/x", "ls; rm x", "ls $(rm x)", "git push", "rg --pre sh x",
                              "python3 /tmp/relay.py set")] == ["ask"] * 7
    # A program is safe only by its bare name or the exact path PATH finds: never ./ls or /tmp/x/cat.
    assert [bash(c) for c in ("/tmp/x/cat /etc/hostname", "./ls", "../bin/ls", "python3 desktop/relay.py timer list"
                              )] == ["ask"] * 4
    assert bash(f"{shutil.which('ls')} -la") == "allow"
    # relay.py: the skills' allowed-tools list, which RELAY_SKILLS must equal, so the two cannot drift.
    skills = {found.group(1) for base in (ROOT / "skills", ROOT / "wow/skills", *ROOT.glob("plugins/*/skills"))
              if base.is_dir() for path in base.glob("*/SKILL.md")
              for line in path.read_text().splitlines() if line.startswith("allowed-tools:")
              for found in re.finditer(r"relay\.py ([^)*]*)\*?\)", line)}
    active_relay = _active_relay_skills()
    assert skills == set(active_relay), (skills ^ set(active_relay))
    # Rook pairs the owner's phone and lists their devices when they ask; unpairing one stays a card.
    assert [bash(f"{relay} {c}") for c in ("device pair", "device list", "device revoke Pixel")] == [
        "allow", "allow", "ask"]
    assert [bash(f"{relay} {c}") for c in ("restart", "daily-restart", "reload overlay")] == ["deny"] * 3
    # Herdr and Pi: reads, and the guarded sends, pass with no card. A Herdr command Rook lacks goes to the card.
    assert [bash(f"{relay} {c}") for c in ("herdr agents", "herdr read fixer --lines 20", "pi sessions --limit 5",
                                           "pi read 01a1", "herdr send fixer 'Carry on.'",
                                           "herdr send fixer - <<'EOF'\nCarry on.\nEOF",
                                           "herdr start ~/Code/x --kind pi 'Begin.'")] == ["allow"] * 7
    assert bash(f"{relay} herdr keys fixer y") == "ask"
    assert [bash(f"{relay} {c}") for c in ("note gone", "ask x", "handoff -", "tell x", "darkness", "settle x", "dream",
                                           "memory install-shared", "memory remove-shared",
                                           "handoff --work 'fix x' - <<'EOF'\nbrief\nEOF",
                                           "handoff --work --print - <<'EOF'\nbrief\nEOF")
            ] == ["ask"] * 11
    assert [bash(f"{relay} {c}") for c in ("timer list", "timer set 10m", "remember 'prefers dark mode'",
                                           "get", "set voice Hugh", "show /tmp/a.png",
                                           "media", "media status", "media pause", "media play", "media toggle",
                                           "media pause chromium",
                                           "forge list", "forge bake nova-mine orbit --show",
                                           "forge new nova-mine orbit --base nova --think <<'GLSL'\nvec4 icon(vec2 p, float t, int l){return vec4(0);}\nGLSL",
                                           "work list", "watch abc", "dark on", "dark off",
                                           "set agent claude", "set agent_model gemini-4-neon",
                                           "handoff --print --work 'fix x' --done 'y' - <<'EOF'\nbrief\nEOF",
                                           "handoff --to opus --work 'fix x' --print - <<'EOF'\nbrief\nEOF",
                                           "handoff --to neon --print --work 'fix x' - <<'EOF'\nbrief\nEOF")] == ["allow"] * 24
    assert bash(f"{relay} wow-data gear") == ("allow" if "wow-data " in active_relay else "ask")
    assert [bash(f"XDG_CONFIG_HOME=/tmp {relay} forge new nova-mine orbit"),
            bash(f"HOME=/tmp {relay} forge new nova-mine orbit"),
            bash(f"python3 {antigravity_home.ROOT / 'themes/forge/bake.py'} nova --all"),
            bash(f"python3 {antigravity_home.ROOT / 'themes/forge/forge.py'} bake nova-mine"),
            bash(f"python3 {antigravity_home.ROOT / 'themes/forge/preview.py'} nova sheet --out /tmp/s.png")] == ["deny"] * 5
    assert [bash(f"{relay} forge --help"),
            bash(f"cat {antigravity_home.ROOT / 'themes/forge/bake.py'}"),
            bash("git diff -- themes/forge/preview.py"),
            bash("echo forge.py is a file")] == ["allow"] * 4
    # Read-only in every form: an option that writes, runs a command or waits goes to the card.
    assert [bash(c) for c in ("git show --output=/home/x/.config/hypr/hyprland.conf HEAD", "git diff --output=/tmp/x",
                              "git log --ext-diff", "git diff --textconv", "git -c core.pager=sh log", "git -C /x log",
                              "git push", "file -C -m /tmp/m", "tail -f /var/log/x", "tail -Fn 5 x",
                              "hyprctl --batch 'dispatch exec foo'", "hyprctl monitors --batch 'dispatch exec x'",
                              "hyprctl dispatch exec foo", "date -s '2020-01-01'", "hostname evil",
                              "jq -n 'input' --rawfile x /etc/shadow", "t3 thread list --port 1",
                              "t3 thread start --project p --model x - <<'EOF'\nbrief\nEOF")] == ["ask"] * 18
    assert [bash(c) for c in ("git log --oneline -5", "git diff --stat HEAD~1 -- desktop", "git show HEAD:README.md",
                              "git status --short", "tail -n 20 /tmp/x.log", "date +%H:%M", "hostname",
                              "hyprctl -j monitors", "file /tmp/x.png")] == ["allow"] * 9
    # A plugin's read-only program passes bare only while that plugin is active, as Omarchy's terminal lookup does.
    saved_policy = dict(antigravity_home.POLICY)
    try:
        for listed, bare in (((), "ask"), (("omarchy-cmd-terminal-cwd",), "allow")):
            antigravity_home.POLICY["read_only_commands"] = listed
            assert [bash("omarchy-cmd-terminal-cwd"), bash("omarchy-cmd-terminal-cwd /tmp")] == [bare, "ask"], listed
    finally:
        antigravity_home.POLICY.clear()
        antigravity_home.POLICY.update(saved_policy)
    # SENDS: a plain send or start passes, with any brief; anything chained to one goes to the card.
    assert [bash(c) for c in ("t3 thread send abc - --json",
                              "t3 thread send abc - --json <<'BRIEF'\nGo; rm -rf /\nBRIEF",
                              "t3 thread start /home/x/rook - --json --title \"Fix the bar\" --provider claudeAgent "
                              "--model claude-opus-5-5 --option effort=high <<'BRIEF'\nThe brief.\nBRIEF"
                              )] == ["allow"] * 3
    assert [bash(c) for c in ("t3 thread send abc - --json; rm x", "t3 thread send abc && rm x",
                              "t3 thread send a | tee o",
                              "t3 thread send abc > out.txt", "(t3 thread send abc)", "t3 thread send $(cat x)",
                              "ls | t3 thread send abc -", "t3 thread send a - <<'B'\nx\nB\nrm -rf /tmp/y\nB",
                              "T=1 t3 thread send abc")] == ["ask"] * 9
    # An unquoted heredoc runs a line that starts with $(...), so the guard cannot see it.
    assert bash("t3 thread send abc - <<EOF\n$(rm x)\nEOF") == "deny"
    assert {decide(name, {}, ("t3_project_delete",)) for name in (
        "Agent", "send_command_input", "invoke_subagent", "mcp__t3__t3_project_delete", "browser_click_element",
        "schedule", "run_workflow", "generate_image", "send_message", "manage_task", "a_tool_agy_adds_later")} == {"deny"}
    assert {decide(name, {}, ()) for name in ("command_status", "finish", "read_resource")} == {"allow"}
    assert {decide(name, {}, ()) for name in ("Read", "mcp__t3__t3_pending_request")} == {"allow"}
    assert decide("mcp__wow__find_npc", {}, ()) == ("allow" if "wow" in antigravity_home.ROOK_SERVERS else "deny")
    assert {decide(name, {}, ()) for name in ("Edit", "mcp__t3__t3_thread_organize", "ask_permission")} == {"ask"}
    for tool in ("t3_thread_send", "t3_thread_launch"):  # Refused while sends go by the t3 command, else as any tool.
        assert decide(f"mcp__t3__{tool}", {}, ()) == ("deny" if tool in antigravity_home.T3_SENDS_BY_COMMAND else "ask")
    # From captures/22: agy ends the turn with no text at a rejection, so the result says what was declined.
    agy.turn(process, "s", "deny", "Remove it.", [], False)
    assert not out(asked("5", {**call, "rawInput": {"CommandLine": "t3 project remove demo"}}, options))
    assert sent[-1]["result"]["outcome"]["optionId"] == "deny"
    result = out({"id": 8, "result": {"stopReason": "end_turn"}})[-1]
    assert result["result"] == "Antigravity ended the turn when Bash was declined."
    # A cancel answers the open card, and the turn ends cancelled, not completed.
    card = out(asked("4", call, options))[0]
    agy.open.append(9)  # As if the "late" prompt below were running; its own send is checked after.
    agy.interrupt(process)
    assert sent[-2]["method"] == "session/cancel" and sent[-1]["result"]["outcome"] == {"outcome": "cancelled"}
    agy.open.remove(9)
    agy.calls[9] = ("prompt", "late")
    agy.open.append(9)
    count = len(sent)
    agy.permit(process, card, True)  # The card was already answered by the cancel: no second answer.
    assert len(sent) == count
    # An ask that comes after the cancel, before its prompt ends, gets no card.
    assert not out(asked("6", call, options)) and sent[-1] == {"jsonrpc": "2.0", "id": "6",
                                                               "result": {"outcome": {"outcome": "cancelled"}}}
    assert out({"id": 9, "result": {"stopReason": "cancelled"}})[-1]["terminal_reason"] == "cancelled"
    assert out(asked("7", call, options))[0]["type"] == "control_request"  # After it, asks show again.
    # The hang of 2026-11-23: a card the owner never answered held agy, and their next request waited behind it. Now a new
    # turn declines the open card and takes it back from Rook, and the watchdog ends a turn agy has gone silent on.
    global STALL_SECONDS
    agy.asks.clear()  # Card 7 above is done with.
    card = out(asked("11", call, options))[0]
    agy.turn(process, "s", "next", "Next request.", [], True)
    assert sent[-2] == {"jsonrpc": "2.0", "id": "11",
                        "result": {"outcome": {"outcome": "selected", "optionId": "deny"}}}
    assert sent[-1]["method"] == "session/prompt" and not agy.asks and agy.withdrawn == [card["request_id"]]
    stall, STALL_SECONDS = STALL_SECONDS, 0.2
    feed = asyncio.Queue()

    async def lines():
        while (line := await feed.get()) is not None:
            yield line

    async def watch():
        reader, seen = agy.read(lines()), []
        seen.append(await asyncio.wait_for(reader.__anext__(), 2))  # The taken-back card, before agy says a word.
        await feed.put(chunk("Working on it. "))
        seen += [await reader.__anext__() for _ in range(2)]  # The text block starts.
        seen.append(await asyncio.wait_for(reader.__anext__(), 2))  # Silence: the block ends,
        seen.append(await asyncio.wait_for(reader.__anext__(), 2))  # and the turn ends, with words Rook says.
        late = sent[-1]
        await feed.put(None)
        rest = [message async for message in reader]
        return seen, late, rest
    seen, late, rest = asyncio.run(watch())
    STALL_SECONDS = stall
    assert seen[0] == {"type": "control_cancel_request", "request_id": card["request_id"]}
    assert seen[3] == stream("content_block_stop") and late["method"] == "session/cancel"
    result = seen[4]
    assert (result["result"], result["terminal_reason"], result["is_error"]) == (STALLED, "stalled", False)
    assert "next" in result["user_message_uuids"] and not agy.open and not rest
    # A wedged agy: a second stall while the first stalled turn still has no answer ends agy, so a new one starts.
    ended = []
    wedge = Antigravity()
    wedge.command("PROMPT", {}, "s", None, ())
    wedge.begin(SimpleNamespace(pid=None, kill=lambda: ended.append(1), stdin=SimpleNamespace(write=lambda line: None)),
                "s", "setup", "Setup.")
    wedge.session, wedge.outbox = "sid", []
    wedge.turn(wedge.process, "s", "A", "A.", [], False)
    assert list(wedge.stalled())[-1]["result"] == STALLED and not ended  # The first stall: agy may still answer.
    wedge.turn(wedge.process, "s", "B", "B.", [], False)
    assert list(wedge.stalled())[-1]["user_message_uuids"] == ["B"] and ended == [1]
    # Rook's first-output watchdog reads heard. A prompt that gets nothing leaves it before the prompt was handed. A
    # thought moves it past the prompt, though it yields nothing, so a long think is never taken for a stall.
    thinker = Antigravity()
    thinker.command("PROMPT", {}, "s", None, ())
    thinker.begin(SimpleNamespace(pid=None, kill=lambda: None, stdin=SimpleNamespace(write=lambda line: None)),
                  "s", "setup", "Setup.")
    thinker.session, thinker.outbox = "sid", []
    thinker.turn(thinker.process, "s", "T", "T.", [], False)
    handed = time.monotonic()
    assert thinker.heard <= handed

    async def think():
        queue = asyncio.Queue()
        for line in ({"method": "session/update", "params": {"update": {
                "sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "Hm."}}}}, None):
            await queue.put(line)

        async def thoughts():
            while (line := await queue.get()) is not None:
                yield line
        return [message async for message in thinker.read(thoughts())]
    assert asyncio.run(think()) == [] and thinker.heard > handed
    # After a stall, a late ask of the ended turn gets no card and does not run, until that turn's answer comes.
    assert agy.cancelled and not out(asked("16", call, options))
    assert sent[-1] == {"jsonrpc": "2.0", "id": "16", "result": {"outcome": {"outcome": "cancelled"}}}
    stalled_rpc = next(iter(agy.cancelled))
    assert agy.abandoned == {stalled_rpc} and not out(chunk("LATE TEXT."))  # Never spoken as the next turn's.
    out({"id": stalled_rpc, "result": {"stopReason": "cancelled"}})
    assert not agy.cancelled and not agy.abandoned and out(chunk("New text."))
    out(stream("content_block_stop") and {"method": "session/update", "params": {"update": {
        "sessionUpdate": "usage_update"}}})
    # Review 2, fix 3: a stalled turn whose answer never comes. Once STALE_SECONDS pass, the next turn's ask shows its
    # card and its text is spoken; its answer settles the older turn too.
    agy.turn(process, "s", "lost", "Go.", [], False)
    lost = agy.open[-1]
    list(agy.stalled())
    assert not out(chunk("LATE.")) and lost in agy.abandoned
    agy.stale_until = 0  # STALE_SECONDS later.
    agy.turn(process, "s", "healthy", "Next.", [], False)
    assert out(asked("17", call, options))[0]["type"] == "control_request"
    agy.asks.clear()
    assert out(chunk("Healthy words."))
    result = out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})[-1]
    assert result["result"] == "Healthy words." and not agy.abandoned and not agy.cancelled, result
    # A turn the owner stopped ends alone: its late answer never folds into the turn after it.
    agy.turn(process, "s", "stopped", "Go.", [], False)
    stopped = agy.open[-1]
    agy.interrupt(process)
    agy.turn(process, "s", "after-stop", "Next.", [], False)
    assert out({"id": stopped, "result": {"stopReason": "cancelled"}})[-1]["user_message_uuids"] == ["stopped"]
    assert out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})[-1]["user_message_uuids"] == ["after-stop"]
    # The watchdog counts from a card's end: the owner's answer, or a new request that takes the card back.
    agy.heard = 0
    agy.permit(process, out(asked("14", call, options))[0], True)
    assert time.monotonic() - agy.heard < 1
    agy.heard = 0
    out(asked("15", call, options))
    agy.turn(process, "s", "after-card", "Next.", [], True)
    assert time.monotonic() - agy.heard < 1
    # One limit, ten minutes, with a tool open or not. When agy ends the turn while its command still runs in the
    # background (live, 09:38), the turn is held open: the command's end and agy's next words are its answer.
    usage = {"method": "session/update", "params": {"update": {"sessionUpdate": "usage_update"}}}
    out({"method": "session/update", "params": {"update": {"sessionUpdate": "usage_update", "used": 41921}}})
    assert agy.context == 41921  # The journal's turn line reports the session's context size.
    assert agy.quiet() == STALL_SECONDS == 600 and out(update(call))[-1]["type"] == "assistant"
    assert agy.quiet() == STALL_SECONDS
    out(chunk("Waiting for the command to finish."))
    out(usage)
    held_msgs = out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})
    assert not [m for m in held_msgs if m["type"] == "result"]
    assert [m for m in held_msgs if m["type"] == "rook_held"] == [
        {"type": "rook_held", "active": True, "turn": "after-card", "tools": ["Bash"]}], held_msgs
    assert agy.held and agy.quiet() == STALL_SECONDS
    done_msgs = out(update({**call, "sessionUpdate": "tool_call_update", "status": "completed",
                            "rawOutput": {"output": "finished"}}))
    assert done_msgs[0]["message"]["content"][0]["content"] == "finished"
    assert [m for m in done_msgs if m["type"] == "rook_held"] == [
        {"type": "rook_held", "active": False, "turn": "after-card"}], done_msgs
    assert agy.quiet() == HELD_QUIET_SECONDS
    assert out(chunk(" It printed finished."))[-1] == stream("content_block_delta", delta={
        "type": "text_delta", "text": " It printed finished."})  # Streamed as the held turn's words, once.
    result = [m for m in out(usage) if m["type"] == "result"][-1]
    assert "after-card" in result["user_message_uuids"], result
    assert result["result"] == "Waiting for the command to finish. It printed finished.", result
    assert not agy.held and not agy.open and agy.quiet() == STALL_SECONDS
    # The journal's first output counts any message from agy, such as a thought: only true silence shows as a pause.
    agy.turn(process, "s", "think", "Hm?", [], False)
    out({"method": "session/update", "params": {"update": {"sessionUpdate": "agent_thought_chunk",
                                                           "content": {"type": "text", "text": "Thinking."}}}})
    assert agy.first_words is not None and agy.first_words < 1
    out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})
    # A new request ends a held turn first, and a wake that says nothing ends it after HELD_QUIET_SECONDS, unspoken.
    agy.turn(process, "s", "long", "Run it.", [], False)
    out(update({**call, "toolCallId": "c9"}))
    out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})
    agy.turn(process, "s", "next", "Next.", [], False)
    assert [m["user_message_uuids"] for m in agy.flush() if m["type"] == "result"] == [["long"]] and not agy.tools
    out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})
    agy.turn(process, "s", "quiet", "Run it.", [], False)
    out(update({**call, "toolCallId": "c10"}))
    out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})
    out(update({**call, "toolCallId": "c10", "sessionUpdate": "tool_call_update", "status": "completed"}))
    assert [(m["result"], m["user_message_uuids"]) for m in agy.stalled() if m["type"] == "result"] == [("", ["quiet"])]
    assert not agy.open and not agy.held

    def hold(uuid, tool):  # A turn agy ends while its tool still runs.
        agy.turn(process, "s", uuid, "Run it.", [], False)
        out(update({**call, "toolCallId": tool}))
        out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})
        assert agy.held and agy.held[1] == uuid
    # Review 5, fix 1: a held command past STALL_SECONDS ends its turn, not the reader.
    hold("stuck", "c11")
    stalled_msgs = list(agy.stalled())
    assert [m["user_message_uuids"] for m in stalled_msgs if m["type"] == "result"] == [["stuck"]]
    assert not agy.held and not agy.open and not agy.held_reported
    agy.stale_until = 0
    # Fix 2: a tool call agy sends already failed (capture 36) is not a running tool, so its turn is not held.
    agy.turn(process, "s", "declined", "Run it.", [], False)
    out(update({**call, "toolCallId": "c12", "status": "failed"}))
    assert "c12" not in agy.tools
    out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})
    assert not agy.held and not agy.open
    # Fix 3: a new request after long held silence starts the watchdog anew.
    hold("silent", "c13")
    agy.heard, agy.turn_began, agy.first_words = 0, time.monotonic() - 30, 2.0
    agy.turn(process, "s", "after-silence", "Next.", [], False)
    assert time.monotonic() - agy.heard < 1
    assert agy.first_words is None and time.monotonic() - agy.turn_began < 1  # Review 9: the new turn's own numbers.
    import contextlib
    import io
    journal = io.StringIO()
    with contextlib.redirect_stderr(journal):
        assert [m["user_message_uuids"] for m in agy.flush() if m["type"] == "result"] == [["silent"]]
    assert journal.getvalue().count("antigravity: turn") == 1  # The held turn gets its line too.
    out({"id": agy.open[-1], "result": {"stopReason": "end_turn"}})
    # Fix 4: a wake whose first step only calls a tool keeps the turn held until agy says something.
    hold("wake", "c14")
    out(update({**call, "toolCallId": "c14", "sessionUpdate": "tool_call_update", "status": "completed"}))
    assert not [m for m in out(usage) if m["type"] == "result"] and agy.held
    out(chunk("It printed finished."))
    assert [m["result"] for m in out(usage) if m["type"] == "result"] == ["It printed finished."]
    # Fix 5: Stop ends a held turn.
    hold("stopped-held", "c15")
    agy.interrupt(process)
    assert [m["user_message_uuids"] for m in agy.flush() if m["type"] == "result"] == [["stopped-held"]]
    assert not agy.held and not agy.open and agy.declined is None
    agy.stale_until = 0
    # T3's tool server: only with the owner's current agy sign-in, by a link, never a copy; otherwise the t3 command.
    global T3_TOKENS
    tokens, url = T3_TOKENS, "http://127.0.0.1:3773/mcp"
    T3_TOKENS = home / "tokens.json"
    later = (datetime.now(timezone.utc) + timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")
    for entry, signed in (({"token": {"access_token": "x", "expiry": later}, "expiry": later}, True),
                          ({"token": {"access_token": "x"}, "expiry": "2020-01-01T00:00:00Z"}, False),
                          ({"token": "x"}, True), ({}, False),
                          # Review 2, fix 9: no time zone, Go's zero time, and a refresh token.
                          ({"token": {"access_token": "x"}, "expiry": later[:19]}, True),
                          ({"token": {"access_token": "x"}, "expiry": "0001-01-01T00:00:00Z"}, True),
                          ({"token": {"access_token": "x", "refresh_token": "r"}, "expiry": "2020-01-01T00:00:00Z"},
                           True)):
        T3_TOKENS.write_text(json.dumps({url: entry}))
        assert signed_in(url) is signed and not signed_in("http://127.0.0.1:1/mcp"), entry
    T3_TOKENS.write_text(json.dumps({url: {"token": {"access_token": "x"}, "expiry": later}}))
    for signed in (True, False):
        if not signed:
            T3_TOKENS.unlink()
        t3 = Antigravity()
        t3.command("PROMPT", {"t3": {"type": "http", "url": url}}, "s", None, ("t3_project_delete",))
        link = home / APP / "mcp_oauth_tokens.json"
        assert link.is_symlink() is signed and (not signed or os.readlink(link) == str(T3_TOKENS))
        t3_sent = []
        t3.begin(SimpleNamespace(pid=None, stdin=SimpleNamespace(write=lambda line: t3_sent.append(json.loads(line)))),
                 "s", "setup", "Setup.")
        list(t3.handle({"id": 1, "result": {}}))
        assert t3_sent[-1]["params"]["mcpServers"] == []  # T3 comes from mcp_config.json, with Rook's tools only.
        config = json.loads((home / "config/mcp_config.json").read_text())["mcpServers"]
        assert ("t3" in config) is signed
        if signed:
            entry = config["t3"]
            assert entry["url"] == url and "t3_thread_send" in entry["enabledTools"] and entry["tools"][
                "t3_thread_send"] == {"eager": True}
            assert not set(entry["enabledTools"]) & {"t3_project_delete", "t3_environment_unlink",
                                                     "t3_environment_link", "pull_request_merge"}
        assert (settings.render(T3_LOST) in t3_sent[-1]["params"]["_meta"]["antigravity"]["systemPrompt"]["append"]) is signed
        status = list(t3.handle({"id": 2, "result": {"sessionId": "sid"}}))[0]["mcp_servers"]
        assert status == [{"name": "t3", "status": "connected" if signed else "needs-auth"}], status
        # Both of agy's forms reach the policy as mcp__t3__<tool>, so the denied four hold either way.
        assert decide(*claude_tool({"name": "mcp_t3_t3_project_delete", "rawInput": {}}, t3.names),
                      ("t3_project_delete",)) == "deny"
        assert decide(*claude_tool({"name": "call_mcp_tool", "rawInput": {"ServerName": "t3", "ToolName":
                                                                          "t3_project_delete"}}, t3.names),
                      ("t3_project_delete",)) == "deny"
    T3_TOKENS = tokens
    # A T3 tool's result, which ACP leaves out, from the session record's step that names the call.
    record = home / APP / "conversations"
    record.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(record / "sid.db")
    database.execute("CREATE TABLE steps (idx integer, step_type integer, step_payload blob)")
    database.executemany("INSERT INTO steps VALUES (?, ?, ?)", [
        (1, 132, b"\x12call_1 Created At: x\nCompleted At: y\n{\"threadId\": \"T1\"}\x1a\x02zz"),
        (2, 132, b"\x12call_2 Created At: x\nCompleted At: y\n{\"threadId\": \"T2\"}\x1a\x02zz"),
        (3, 132, b"\x12call_10 Created At: x\nCompleted At: y\n{\"threadId\": \"T10\"}\x1a\x02zz")])
    database.commit()
    database.close()
    assert recorded_output(home, "sid", "call_1") == '{"threadId": "T1"}'  # Never call_10's (review 2, fix 10).
    assert recorded_output(home, "sid", "call_9") == "" == recorded_output(home, "../x", "call_1")
    # A locked record gives "" in under a second, not five, so the reader and its watchdog go on (review 2, fix 2).
    lock = sqlite3.connect(record / "sid.db")
    lock.execute("BEGIN EXCLUSIVE")
    began = time.monotonic()
    assert recorded_output(home, "sid", "call_1") == "" and time.monotonic() - began < 1.5
    lock.rollback()
    lock.close()
    # A stall on a turn that agy's record ends with an API error says that error, not the stalled sentence.
    errored = Antigravity()
    errored.command("PROMPT", {}, "s", None, ())
    errored.begin(SimpleNamespace(pid=None, kill=lambda: None, stdin=SimpleNamespace(write=lambda line: None)),
                  "s", "setup", "Setup.")
    errored.session, errored.outbox = "quota", []
    record.mkdir(parents=True, exist_ok=True)  # command() cleared the data folder.
    errored.turn(errored.process, "s", "Q", "Q.", [], False)
    database = sqlite3.connect(record / "quota.db")
    database.execute("CREATE TABLE steps (idx integer, step_type integer, step_payload blob)")
    database.execute("INSERT INTO steps VALUES (1, 17, ?)", (b"Error 429, Message: Quota exceeded, Status: "
                                                             b"RESOURCE_EXHAUSTED",))
    database.commit()
    database.close()
    assert list(errored.stalled())[-1]["result"] == "Antigravity failed: Quota exceeded (RESOURCE_EXHAUSTED)."
    # Full permission: what the strict policy carded passes, every denial stays, and a question still asks the owner.
    PERMISSIONS = "full"
    assert [bash(c) for c in ("touch x", "rm -rf /tmp/x", "git push", "t3 thread send abc - --json; rm x",
                              f"{relay} note gone", "agy --help", "grep -r foo ~/.config")] == ["allow"] * 7
    assert {decide(name, {}, ()) for name in ("Edit", "Write", "mcp__t3__t3_thread_organize", "ask_permission")
            } == {"allow"}
    # Review 2, fix 1: only Rook's T3 tools pass. The others would start thread work that Rook does not follow.
    assert {decide(f"mcp__t3__{tool}", {}, ()) for tool in (
        "t3_thread_send_attachments", "create_threads", "delegate_task", "t3_worktree_handoff", "schedule_task",
        "run_scheduled_task_now", "t3_thread_wait", "a_tool_t3_adds_later")} == {"deny"}
    assert [decide("mcp__t3__t3_queue", {"action": action}, ()) for action in ("list", "read", "add", "cancel")
            ] == ["allow", "allow", "deny", "deny"]
    assert decide(*claude_tool({"name": "call_mcp_tool", "rawInput": {"ServerName": "t3", "ToolName": "create_threads",
                                                                      "Arguments": {}}}, ["t3"]), ()) == "deny"
    # Review 3, fix 6: a server that is not Rook's is refused, as it reaches through call_mcp_tool.
    assert decide(*claude_tool({"name": "call_mcp_tool", "rawInput": {"ServerName": "t3-code", "ToolName":
                                                                      "create_threads"}}, ["t3"]), ()) == "deny"
    # Fix 8: any case or spacing of the server's or tool's name is the same tool.
    assert decide(*claude_tool({"name": "call_mcp_tool", "rawInput": {"serverName": " T3", "toolName":
                                                                      "Pull_Request_Merge "}}, ["t3"]),
                  ("pull_request_merge",)) == "deny"
    assert [bash(c) for c in ("t3 project remove demo", "gh -R o/r pr merge 1", f"{relay} restart",
                              "p=project; t3 $p remove x", "bash -c 't3 environment unlink x'")] == ["deny"] * 5
    assert {decide(name, {}, ("t3_project_delete",)) for name in (
        "Agent", "send_command_input", "browser_click_element", "schedule", "a_tool_agy_adds_later",
        "mcp__t3__t3_project_delete")} == {"deny"}
    assert not out(asked("9", call, options)) and sent[-1]["result"]["outcome"]["optionId"] == "allow"
    question = out(asked("10", {"toolCallId": "interaction_2", "title": "Which?"}, [{"optionId": "a", "name": "A"}]))
    assert question[0]["request"]["tool_name"] == "AskUserQuestion"
    # Several asks at once: agy keeps each by its own id, and each answer goes to its own ask, in any order.
    agy.asks.clear()
    opened = [out(asked(rpc, {"toolCallId": f"interaction_{rpc}", "title": "Which?"}, [{"optionId": "a", "name": "A"}]))[0]
              for rpc in ("31", "32", "33")]
    assert sorted(agy.asks) == ["acp-31", "acp-32", "acp-33"] and [m["request_id"] for m in opened] == sorted(agy.asks)
    for card, answers in ((opened[2], {"Which?": "A"}), (opened[0], {"Which?": "B"}), (opened[1], None)):
        agy.permit(process, card, True, answers)
        assert sent[-1]["id"] == card["rpc"] and card["request_id"] not in agy.asks, sent[-1]
    assert [m["result"]["outcome"] for m in sent[-3:]] == [{"outcome": "selected", "optionId": "a"},
                                                         {"outcome": "cancelled"}, {"outcome": "cancelled"}], sent[-3:]
    assert not agy.asks
    # The journal is on disk: a decision prints the verdict and the tool's name, never its input.
    import contextlib
    import io
    printed = io.StringIO()
    with contextlib.redirect_stderr(printed):
        out(asked("12", {**call, "rawInput": {"CommandLine": "echo SAMS-WORDS"}}, options))
        out(asked("13", {**call, "rawInput": {"CommandLine": "t3 project remove SAMS-WORDS"}}, options))
    assert "antigravity: allow Bash" in printed.getvalue() and "SAMS-WORDS" not in printed.getvalue()
    # Gate recorded_output to T3 sends/launches and keep failure() off the loop on end_turn.
    real_recorded, real_failure, real_prompt = recorded_output, failure, antigravity_home.prompt
    rec_calls, fail_calls, threads = [], [], {}

    def spy_recorded(folder, session, call_id):
        import threading
        rec_calls.append(call_id)
        threads["recorded"] = threading.current_thread() is threading.main_thread()
        return real_recorded(folder, session, call_id)

    def spy_failure(folder, session):
        import threading
        fail_calls.append(session)
        threads["failure"] = threading.current_thread() is threading.main_thread()
        return real_failure(folder, session)

    def spy_prompt(text, workspace, beats=False):
        import threading
        threads["prompt"] = threading.current_thread() is threading.main_thread()
        threads["beats"] = beats
        return text

    try:
        recorded_output, failure = spy_recorded, spy_failure
        gated = Antigravity()
        gated.command("PROMPT", {"render": {"command": "uv", "args": []}, "t3": {"type": "http", "url": "x"}},
                      "s", None, ())
        gated.begin(process, "s", "setup", "Setup.")
        gated.session, gated.outbox = "sid", []
        record.mkdir(parents=True, exist_ok=True)
        database = sqlite3.connect(record / "sid.db")
        database.execute("CREATE TABLE steps (idx integer, step_type integer, step_payload blob)")
        database.execute("INSERT INTO steps VALUES (1, 132, ?)",
                         (b"\x12call_send Created At: x\nCompleted At: y\n{\"threadId\": \"T1\"}\x1a",))
        database.commit()
        database.close()
        # Non-delegating MCP tools skip recorded_output; T3 sends read it when output is empty.
        for call_id, name in (("call_read", "mcp_t3_t3_thread_read"), ("call_scene", "mcp_render_show_scene")):
            list(gated.handle(update({"sessionUpdate": "tool_call", "toolCallId": call_id, "name": name})))
            done = list(gated.handle(update({"sessionUpdate": "tool_call_update", "toolCallId": call_id,
                                             "status": "completed"})))
            assert done[0]["message"]["content"][0]["content"] == ""
        assert not rec_calls
        list(gated.handle(update({"sessionUpdate": "tool_call", "toolCallId": "call_send",
                                  "name": "mcp_t3_t3_thread_send"})))
        done = list(gated.handle(update({"sessionUpdate": "tool_call_update", "toolCallId": "call_send",
                                         "status": "completed"})))
        assert done[0]["message"]["content"][0]["content"] == '{"threadId": "T1"}' and rec_calls == ["call_send"]
        # A T3 launch with inline output skips recorded_output too.
        list(gated.handle(update({"sessionUpdate": "tool_call", "toolCallId": "call_launch",
                                  "name": "mcp_t3_t3_thread_launch"})))
        done = list(gated.handle(update({"sessionUpdate": "tool_call_update", "toolCallId": "call_launch",
                                         "status": "completed", "rawOutput": {"output": '{"threadId": "T2"}'}})))
        assert done[0]["message"]["content"][0]["content"] == '{"threadId": "T2"}' and rec_calls == ["call_send"]
        # Partial text followed by a 503 error step still reports the API error.
        gated.turn(process, "s", "partial-ok", "Hi.", [], False)
        list(gated.handle(chunk("Answered.")))
        res = list(gated.handle({"id": gated.open[-1], "result": {"stopReason": "end_turn"}}))[-1]
        assert res["result"] == "Answered." and not res["is_error"] and res["terminal_reason"] == "completed"
        database = sqlite3.connect(record / "sid.db")
        database.execute("INSERT INTO steps VALUES (2, 17, ?)",
                         (b"Error 503, Message: Backend unavailable, Status: UNAVAILABLE",))
        database.commit()
        database.close()
        gated.turn(process, "s", "partial-err", "Hi.", [], False)
        list(gated.handle(chunk("Let me check the")))
        res = list(gated.handle({"id": gated.open[-1], "result": {"stopReason": "end_turn"}}))[-1]
        assert res["result"] == "Antigravity failed: Backend unavailable (UNAVAILABLE).", res
        assert res["is_error"] is True and res["terminal_reason"] == "error", res
        # read() runs prompt/memory, recorded_output, and failure in worker threads without reordering messages.
        rec_calls.clear(); fail_calls.clear(); threads.clear()
        antigravity_home.prompt = spy_prompt
        threaded = Antigravity()
        threaded.command("PROMPT", {"t3": {"type": "http", "url": "x"}}, "s", None, ())
        t_sent = []
        t_proc = SimpleNamespace(pid=None, stdin=SimpleNamespace(write=lambda line: t_sent.append(json.loads(line))))
        threaded.begin(t_proc, "s", "setup", "Setup.")
        record.mkdir(parents=True, exist_ok=True)
        database = sqlite3.connect(record / "sid.db")
        database.execute("CREATE TABLE steps (idx integer, step_type integer, step_payload blob)")
        database.executemany("INSERT INTO steps VALUES (?, ?, ?)", [
            (1, 132, b"\x12call_send Created At: x\nCompleted At: y\n{\"threadId\": \"T1\"}\x1a"),
            (2, 17, b"Error 503, Message: Backend unavailable, Status: UNAVAILABLE")])
        database.commit()
        database.close()

        async def run_threaded():
            async def feed():
                yield {"id": 1, "result": {}}
                yield {"id": 2, "result": {"sessionId": "sid"}}
                yield update({"sessionUpdate": "tool_call", "toolCallId": "call_send",
                              "name": "mcp_t3_t3_thread_send"})
                yield update({"sessionUpdate": "tool_call_update", "toolCallId": "call_send",
                              "status": "completed"})
                yield chunk("Let me check the")
                yield {"id": threaded.open[-1], "result": {"stopReason": "end_turn"}}
            return [m async for m in threaded.read(feed())]

        ordered = asyncio.run(run_threaded())
        assert [m["type"] for m in ordered] == [
            "system", "stream_event", "assistant", "user", "stream_event", "stream_event", "stream_event", "result"
        ], ordered
        assert ordered[3]["message"]["content"][0]["content"] == '{"threadId": "T1"}'
        assert ordered[-1]["result"] == "Antigravity failed: Backend unavailable (UNAVAILABLE)."
        assert ordered[-1]["is_error"] is True and ordered[-1]["terminal_reason"] == "error"
        assert threads == {"prompt": False, "beats": False, "recorded": False, "failure": False}, threads
        # A new turn arriving while the stall lookup runs in a thread cancels the stall and keeps the new prompt.
        import threading
        entered, resume = threading.Event(), threading.Event()
        stall_saved = STALL_SECONDS
        STALL_SECONDS = 0.05

        def blocking_failure(folder, session):
            entered.set()
            resume.wait(2)
            return None

        failure = blocking_failure
        raced = Antigravity()
        raced.command("PROMPT", {}, "s", None, ())
        r_sent = []
        r_proc = SimpleNamespace(pid=None, stdin=SimpleNamespace(write=lambda line: r_sent.append(json.loads(line))))
        raced.begin(r_proc, "s", "setup", "Setup.")
        raced.session, raced.outbox = "sid", []
        raced.turn(r_proc, "s", "held-req", "Run.", [], False)
        list(raced.handle(update({**call, "toolCallId": "c_race"})))
        list(raced.handle({"id": raced.open[-1], "result": {"stopReason": "end_turn"}}))
        assert raced.held and raced.tools == {"c_race"}
        raced.heard = time.monotonic() - 1

        async def run_stall_race():
            queue = asyncio.Queue()

            async def feed():
                while (item := await queue.get()) is not None:
                    yield item

            reader = raced.read(feed())

            async def arrive_during_lookup():
                await asyncio.to_thread(entered.wait, 2)
                raced.turn(r_proc, "s", "new-req", "Next.", [], False)
                resume.set()

            task = asyncio.create_task(arrive_during_lookup())
            first_msg = await asyncio.wait_for(reader.__anext__(), 2)
            await task
            assert first_msg["type"] == "result" and first_msg["user_message_uuids"] == ["held-req"], first_msg
            assert first_msg["terminal_reason"] == "completed" and len(raced.open) == 1 and not raced.abandoned
            await queue.put(chunk("Fresh answer."))
            await queue.put({"id": raced.open[-1], "result": {"stopReason": "end_turn"}})
            await queue.put(None)
            return [m async for m in reader]

        try:
            rest = asyncio.run(run_stall_race())
        finally:
            STALL_SECONDS = stall_saved
        assert rest[-1]["type"] == "result" and rest[-1]["user_message_uuids"] == ["new-req"], rest
        assert rest[-1]["result"] == "Fresh answer." and rest[-1]["terminal_reason"] == "completed"
        # Opt-in live thought emission: off by default; when on, emits {"type": "thought"} without touching
        # self.texting, self.answer, or held-turn release, and drops stale thoughts from abandoned turns.
        narr = Antigravity()
        narr.narrate_thoughts = True
        narr.narrate_beats = True
        narr.command("PROMPT", {}, "s", None, ())
        n_proc = SimpleNamespace(pid=None, stdin=SimpleNamespace(write=lambda line: None))
        narr.begin(n_proc, "s", "setup", "Setup.")
        narr.session, narr.outbox = "sid", []
        assert narr.system_append() == "PROMPT" and threads["beats"] is True
        narr.turn(n_proc, "s", "t-narr", "Check.", [], False)
        th_out = list(narr.handle(update({"sessionUpdate": "agent_thought_chunk",
                                          "content": {"type": "text", "text": "Checking the layout.\n\n"}})))
        assert th_out == [{"type": "thought", "text": "Checking the layout.\n\n"}], th_out
        assert not narr.texting and narr.answer == ""
        # Thought during a held turn's wake does not count as spoken answer or release the held turn.
        list(narr.handle(update({**call, "toolCallId": "c_narr"})))
        list(narr.handle({"id": narr.open[-1], "result": {"stopReason": "end_turn"}}))
        assert narr.held
        list(narr.handle(update({**call, "toolCallId": "c_narr", "sessionUpdate": "tool_call_update",
                                 "status": "completed", "rawOutput": {"output": "ok"}})))
        assert list(narr.handle(update({"sessionUpdate": "agent_thought_chunk",
                                        "content": {"type": "text", "text": "Reviewing output.\n\n"}}))) == [
            {"type": "thought", "text": "Reviewing output.\n\n"}]
        assert list(narr.handle(usage)) == [] and narr.held  # Usage after thought alone does not release held turn.
        list(narr.handle(chunk("All done.")))
        rel = [m for m in narr.handle(usage) if m["type"] == "result"]
        assert len(rel) == 1 and rel[0]["result"] == "All done." and not narr.held, rel
        # Stale thoughts after a stalled turn are dropped.
        narr.turn(n_proc, "s", "t-stale", "Go.", [], False)
        list(narr.stalled(problem=None))
        assert list(narr.handle(update({"sessionUpdate": "agent_thought_chunk",
                                        "content": {"type": "text", "text": "Late thought.\n\n"}}))) == []
    finally:
        recorded_output, failure, antigravity_home.prompt = real_recorded, real_failure, real_prompt
        machine.Machine.strict = saved_strict
    PERMISSIONS = mode
    shutil.rmtree(home, ignore_errors=True)
    print("Antigravity converter and policy: all checks passed.")


if __name__ == "__main__" and sys.argv[1:2] == ["--check"]:
    check()
