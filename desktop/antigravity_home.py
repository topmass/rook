"""Rook's private Antigravity folder: what the agy agent knows and obeys. Rook builds it fresh at each start.

Rook starts agy with --gemini-dir set to HOME. Antigravity then reads its personal customizations from
HOME/config, and the owner's own ~/.gemini stays untouched. Nothing private is copied here: the owner's files are linked
or named by path.

  config/plugins/rook/  skills/, rendered for Antigravity. They go by bare name, such as delegate, as agy lists them.
  config/AGENTS.md      a copy of the owner's global instructions, ~/.agents/AGENTS.md. A copy, so agy cannot change them.
  config/skills.json    Rook's own skills in ~/.config/rook/skills, and the active plugins' allowed host skills.
  config/hooks.json     `guard` below: Rook's denied tools and commands, then DCG on every run_command call.
  config/guard_policy.json  Plain data from the active plugins, which the guard reads with json alone.

The tables hold the only Claude-only strings. Each entry must still be in its source text, so an edit that breaks
one fails loudly at launch. Run `python3 antigravity_home.py check` to test them.
"""
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

# Isolated mode (-I) omits this script's folder from sys.path; put it first so sibling imports resolve.
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import desk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HOME = desk.runtime_dir() / "rook-antigravity"
AGENTS = Path.home() / ".agents"
ROOK_SKILLS = desk.config_dir() / "rook/skills"
GEMINI_SKILLS = Path.home() / ".gemini/config/skills"
DCG = Path.home() / ".local/bin/dcg"  # The same command as the DCG hook in ~/.claude/settings.json.

# skills/: file, Claude's text, Antigravity's text. Antigravity names a tool from Rook's servers
# mcp_<server>_<tool>, or reaches it through call_mcp_tool.
SKILLS = [
    ("delegate/SKILL.md", "They appear as `mcp__t3__t3_thread_list` and so on",
     "They appear as `mcp_t3_t3_thread_list` and so on"),
    ("delegate/SKILL.md", "Most load on first use: find one with ToolSearch, such as `select:mcp__t3__t3_thread_list`.",
     "When one is not in your tool list, call it through call_mcp_tool with ServerName t3."),
    ("delegate/SKILL.md", "when ToolSearch cannot find the tools", "when the T3 tools are missing"),
    ("delegate/references/t3-command.md", "when ToolSearch cannot find the T3 tools", "when the T3 tools are missing"),
    ("delegate/references/t3-tools.md", "Rook's Claude session", "Rook's Antigravity session"),
    ("delegate/references/t3-tools.md", "`mcp__t3__<name>`", "`mcp_t3_<name>`"),
    ("wow/SKILL.md", "Find one that is not loaded yet with ToolSearch.",
     "They appear as mcp_wow_<name>, such as mcp_wow_find_npc."),
]
OPTIONAL_SKILLS = frozenset({"wow/SKILL.md"})
# Rook's system prompt from rook.py. The memory lines follow it, from memory().
PROMPT = [
    ("a full Claude Code session", "a full Antigravity session"),
    ("that your session start message names", "that the session start lines at the end of this prompt name"),
    # Neon thinks for seconds before each tool. A sentence first lets the owner hear it start at once, but only when they
    # asked: Rook speaks text before a tool at once, so in any other turn it would break the silence of a PASS.
    ("first tool call, you may write one short sentence",
     "first tool call in a request ⟦owner⟧ spoke or typed, or in your startup turn, always write one short sentence"),
    ("it in a few words. Never ",
     "it in a few words. In any other turn, write nothing before your tools, not even for a handoff, so that PASS "
     "stays silent. Write that first sentence once in a turn, even when ⟦owner⟧ speaks again before you finish. Never "),
]
# When opt-in between-tool beats are enabled, lift the once-per-turn cap while keeping PASS silent on other turns.
PROMPT_BEATS_DROP = "Write that first sentence once in a turn, even when ⟦owner⟧ speaks again before you finish. "
# harness.Claude.setup. Antigravity has Rook's tools from the start, so there is nothing to search for.
SETUP = [(" When a tool you used before is missing, search for it again.", "")]
CLAUDE_ONLY = ("${CLAUDE_", "mcp__", "ToolSearch")
# The only built-in agy tools Rook may use: the ones Claude Code gives it under other names, and waits and reads.
# The hook sees every tool and denies any other, including tools a later agy adds, because some run with no
# permission request (agy ran invoke_subagent unasked). Denied so: subagents, send_message, send_command_input
# (it types into a running shell, which DCG never sees), manage_task, schedule, run_workflow, generate_image, the
# browser tools, notebook_execution, and the rest. Tools of Rook's own servers, mcp_<server>_<tool>, pass.
TOOLS = frozenset({"run_command", "command_status", "view_file", "read_file", "write_file", "edit_file", "list_dir",
                   "find_by_name",
                   "grep_search", "write_to_file", "replace_file_content", "multi_replace_file_content", "sed_file",
                   "notebook_edit", "search_web", "read_url_content", "call_mcp_tool", "list_resources",
                   "read_resource", "ask_question", "ask_permission", "ask_custom_permission", "list_permissions",
                   "finish", "wait", "wait_5_seconds"})


_OPTIONAL_SERVERS = {
    "wow": ("wow/gamedata.py", ("find_npc", "find_quest", "find_item", "find_object", "find_upgrades", "find_price",
                                "recall", "note", "forget")),
}
_ACTIVE_OPTIONAL_SERVERS = {name: info for name, info in _OPTIONAL_SERVERS.items() if (ROOT / info[0]).is_file()}
ROOK_SERVERS = ("render", *_ACTIVE_OPTIONAL_SERVERS, "t3")  # rook.py's tool servers; check() compares them.
GUARD_POLICY = HOME / "config/guard_policy.json"
# The active plugins' part of the policy: their tool servers with denied tools, relay commands that pass with no card,
# and programs that only read when run with no arguments. Empty is today's static policy. build() fills it in Rook's
# process, and guard() from GUARD_POLICY. Never import plugin_loader.py or plugin code here: the hook runs under -I.
NO_POLICY = {"servers": {}, "relay_commands": (), "read_only_commands": ()}
POLICY = dict(NO_POLICY)
_POLICY_NAME = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")
_POLICY_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}\Z")


def load_policy(path=GUARD_POLICY):
    """guard_policy.json's data, checked field by field. A missing, unreadable, malformed or unknown file gives
    NO_POLICY: the static policy, never a wider one."""
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as handle:  # A FIFO must not hang the hook.
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return dict(NO_POLICY)
            data = json.loads(handle.read(65537))
        servers, relay, reads = data["servers"], data["relay_commands"], data["read_only_commands"]
        if (data["schema_version"] != 1 or not isinstance(servers, dict) or not isinstance(relay, list)
                or not isinstance(reads, list)
                or not all(re.fullmatch(r"[a-z][a-z0-9]{0,39}", name) and name not in ROOK_SERVERS + ("wow",)
                           and isinstance(spec, dict) and isinstance(spec["denied_tools"], list)
                           and all(isinstance(tool, str) for tool in spec["denied_tools"])
                           for name, spec in servers.items())
                or not all(isinstance(name, str) and _POLICY_NAME.match(name) for name in relay)
                or not all(isinstance(name, str) and _POLICY_WORD.match(name) for name in reads)):
            return dict(NO_POLICY)
        return {"servers": {name: frozenset(tool.lower() for tool in spec["denied_tools"])
                            for name, spec in servers.items()},
                "relay_commands": tuple(relay), "read_only_commands": tuple(reads)}
    except Exception:
        return dict(NO_POLICY)


def servers():
    """Rook's own tool servers, then the active plugins'."""
    return ROOK_SERVERS + tuple(POLICY["servers"])


def plugin_denied(server, tool):
    """Whether an active plugin denies this tool of its own server."""
    return tool in POLICY["servers"].get(server, ())


def allowed_tool(name, args=None):
    """Whether Rook has this agy tool: a built-in one it uses, or a tool of one of its own servers or an active
    plugin's, by name or through call_mcp_tool. A plugin's denied tools are left out."""
    name = str(name).strip().lower()
    if name == "call_mcp_tool":
        server, tool, _ = mcp_call(args or {})
        return server in servers() and not plugin_denied(server, tool)
    return name in TOOLS or any(name.startswith(f"mcp_{server}_") and not plugin_denied(server, name[len(server) + 5:])
                                for server in servers())


# The T3 tools a misheard sentence must never run, as rook.py's T3_DENIED (check() compares them). The hook runs
# alone, so it cannot import rook.py.
T3_DENIED_TOOLS = ("t3_project_delete", "t3_environment_unlink", "t3_environment_link", "pull_request_merge")


def mcp_call(args):
    """call_mcp_tool's server, tool and arguments. Key case, spaces and name case are ignored, so "T3" is t3."""
    keys = {str(key).strip().lower(): value for key, value in args.items()} if isinstance(args, dict) else {}
    arguments = keys.get("arguments")
    return (str(keys.get("servername") or "").strip().lower(), str(keys.get("toolname") or "").strip().lower(),
            arguments if isinstance(arguments, dict) else {})


def t3_tool(name, args):
    """The T3 tool a call runs, by its direct name mcp_t3_<tool> or through call_mcp_tool, else None."""
    name = str(name).strip().lower()
    if name.startswith("mcp_t3_"):
        return name[len("mcp_t3_"):]
    server, tool, _ = mcp_call(args) if name == "call_mcp_tool" else (None, None, None)
    return tool if server == "t3" else None


def denied_t3_tool(name, args):
    return t3_tool(name, args) in T3_DENIED_TOOLS


# T3 tools that must go by the t3 command instead, which Rook's watcher follows. Empty since 2026-11-23: a real send
# through the tool server reached the watcher (run 42), and the t3 command cannot steer or reach another machine. Launch
# takes the same path, proven against a stand-in only. To send by the command again, make this
# ("t3_thread_send", "t3_thread_launch").
T3_SENDS_BY_COMMAND = ()
# The only T3 tools Rook uses through the tool server: those its delegate skill names, which the watcher follows or
# which start no thread work. agy is given only these (the model sees a limited number of tools), and the hook and
# decide() refuse every other T3 tool, such as t3_thread_send_attachments, create_threads or schedule_task, which
# would start work unwatched. Not here: the four denied tools, and t3_thread_wait, which the skill forbids.
T3_TOOLS = ("t3_environment_links", "t3_environment_read", "t3_project_list", "t3_project_read", "t3_project_create",
            "t3_project_clone", "t3_thread_list", "t3_thread_search", "t3_thread_read", "t3_thread_send",
            "t3_thread_launch", "t3_thread_interrupt", "t3_thread_organize", "t3_pending_request", "t3_queue",
            "orchestrator_capabilities", "pull_request_read", "pull_request_list", "list_thread_pull_requests", "ci_logs")
# The few that agy declares to the model up front. agy lists the others by name, and the model reaches them through
# call_mcp_tool after it reads their schema files.
T3_EAGER = ("t3_thread_send", "t3_thread_launch", "t3_thread_list", "t3_thread_read")
T3_QUEUE_ACTIONS = ("list", "read")
# Rook's own tools that agy always declares to the model up front: the owner uses diagrams daily, and the wow skill calls
# its tools by name. check() compares them with the @mcp.tool functions in each server's source.
EAGER_TOOLS = {"render": ("show_diagram", "clear_scene"),
               **{name: tools for name, (_, tools) in _ACTIVE_OPTIONAL_SERVERS.items()}}
SERVER_SOURCES = {"render": "desktop/render_tool.py",
                  **{name: src for name, (src, _) in _ACTIVE_OPTIONAL_SERVERS.items()}}
# T3 tools that start or feed thread work. A refused one is told the route Rook follows; any other refused T3 tool,
# such as a queue cancel, is the owner's to do.
T3_STARTS_WORK = ("t3_thread_send", "t3_thread_launch", "t3_thread_send_attachments", "create_threads",
                  "delegate_task", "t3_worktree_handoff", "schedule_task", "run_scheduled_task_now")  # t3_queue's other actions add or change a thread's queued work.


def t3_allowed(tool, arguments):
    """Whether Rook may call this T3 tool, with these arguments, through the tool server."""
    return (tool in T3_TOOLS and tool not in T3_SENDS_BY_COMMAND
            and (tool != "t3_queue" or isinstance(arguments, dict) and arguments.get("action") in T3_QUEUE_ACTIONS))
# The command forms of the T3 tools Rook denies (rook.py T3_DENIED), of T3 sign-in tokens, and of a merge.
DENIED_COMMANDS = re.compile(r"\bt3\s+(project\s+remove|environment\s+(un)?link|auth|pair)\b|\bgh\s+pr\s+merge\b"
                             # Rook never restarts or reloads itself.
                             r"|\brelay\.py\s+(restart|reload|daily-restart)\b"
                             # Nor works around relay.py's refusal, which reads ROOK_AGENT.
                             r"|\bROOK_AGENT\b|\benv\s+(-\S+\s+)*(-i|--ignore-environment)\b")
WRAPPERS = {"env", "sudo", "exec", "command", "nohup", "nice", "time", "xargs"}  # The word after runs as a program.
HEREDOC = re.compile(r"\s*<<-?\s*'(\w+)'\n(.*)\n\1\s*$", re.S)  # A quoted heredoc is data, never expanded.


def heredoc(command):
    """The quoted heredoc that ends a command, or None. A body with its own end line is not one: the shell would
    end the heredoc there and run the lines after it."""
    found = HEREDOC.search(command)
    return found if found and not any(line.strip() == found[1] for line in found[2].split("\n")) else None


# The same actions, word by word, after each t3, gh or relay.py: the subcommand that follows its global options.
T3_DENIED = (["project", "remove"], ["project", "rm"], ["project", "delete"], ["environment", "link"],
             ["environment", "unlink"], ["auth"], ["pair"])
VALUE_OPTIONS = {"--log-level", "--completions", "-R", "--repo", "--hostname"}  # Global options that take a value.


def words_of(text, depth=2, code=False):
    """The words of a command line, operators apart. Quoted text after a shell's or python's -c (bash -x -c,
    sh -c --, python3 -c) is code, so it is split again, quoted strings in it too; other quoted text, such as a
    note's sentence, stays one word."""
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = text.split()
    words, runner, dash_c = [], False, False
    for token in tokens:
        if token in (";", "&&", "||", "|", "&", "(", ")"):
            runner = dash_c = False  # A new simple command.
        if depth and re.search(r"\s", token) and (code or dash_c):
            words += words_of(token, depth - 1, code=True)
        else:
            words.append(token)
        name = os.path.basename(token)
        runner = runner or name in ("bash", "sh", "zsh") or name.startswith("python")
        dash_c = dash_c or runner and bool(re.fullmatch(r"-\w*c\w*", token))
    return words


def subcommand(words):
    """The words up to the next operator, with options and their values left out."""
    out, value = [], False
    for word in words:
        if word in (";", "&&", "||", "|", "&", "(", ")", "<<<", "<", ">"):
            break
        if value or word.startswith("-"):
            value = not value and word in VALUE_OPTIONS
            continue
        out.append(word)
    return out


def denied_words(words):
    for at, word in enumerate(words):
        program, sub = os.path.basename(word), subcommand(words[at + 1:])
        unknown = any("$" in part or "`" in part for part in sub[:2])  # A variable may name anything.
        if (program == "t3" and (unknown or any(sub[:len(form)] == form for form in T3_DENIED))
                or program == "gh" and (unknown or sub[:2] == ["pr", "merge"]
                                        or sub[:1] == ["api"] and any(re.search(r"/merge\b", part) for part in sub)
                                        or sub[:2] in (["alias", "set"], ["alias", "import"]))
                or program == "relay.py" and sub[:1] in (["restart"], ["reload"], ["daily-restart"])):
            return True
    return False


def command_line(command):
    """The command without its brief: a quoted heredoc fed to Rook's relay.py or to t3 thread is data."""
    head = command[:found.start()] if (found := heredoc(command)) else command
    return head if found and re.search(r"relay\.py|\bt3\s+thread\s", head) else command


def hidden_program(command):
    """Whether a program word holds $ or `, such as $T or ${T:-t3}: the guard cannot see what it runs."""
    words, program = words_of(command_line(command).replace("\n", " ; ")), True
    for word in words:
        if program and ("$" in word or "`" in word):
            return True
        program = (word in (";", "&&", "||", "|", "&", "(") or program and re.match(r"\w+=", word)
                   or os.path.basename(word) in WRAPPERS | {"bash", "sh", "zsh"} or program and word.startswith("-"))
    return False


# The forge may write only under ~/.config/rook/themes/: deny XDG_CONFIG_HOME overrides, path traversal, or
# out-of-folder --out/--pack-dir targets on any forge, bake, or preview command.
FORGE_SCRIPTS = {"forge.py", "bake.py", "preview.py"}
FORGE_INTERPRETERS = {"python", "python3", "uv"}


def _own_forge_dirs():
    dirs = {Path(os.path.realpath(ROOT / "themes/forge"))}
    for base in ROOK_CODE:
        dirs.add(Path(os.path.realpath(base / "themes/forge")))
    return dirs


def _is_own_forge_script(raw, cwd=None):
    word = re.sub(r"^\$(HOME\b|\{HOME\})", str(Path.home()), re.sub(r"^file://", "", str(raw)))
    if not word or "\n" in word or "$" in word or "`" in word:
        return False
    if os.path.basename(word) not in FORGE_SCRIPTS:
        return False
    base_dir = cwd or os.getcwd()
    path = Path(os.path.realpath(os.path.join(base_dir, os.path.expanduser(word))))
    return path.parent in _own_forge_dirs()


def _split_simple_commands(words):
    """Split shell token list into (prog_raw, args) simple commands, stripping leading env assignments and wrappers."""
    out, cur = [], []
    for word in words:
        if word in OPERATORS:
            if cur:
                out.append(cur)
                cur = []
        else:
            cur.append(word)
    if cur:
        out.append(cur)
    parsed = []
    for seg in out:
        i = 0
        while i < len(seg):
            w = seg[i]
            b = os.path.basename(w)
            if re.match(r"^\w+=", w):
                i += 1
            elif b in WRAPPERS:
                i += 1
                while i < len(seg) and seg[i].startswith("-"):
                    i += 1
            else:
                break
        if i < len(seg):
            parsed.append((seg[i], seg[i + 1:]))
    return parsed


def denied_forge(command, cwd=None):
    """Deny direct execution of Rook's own themes/forge/{bake,forge,preview}.py scripts, and HOME/XDG_CONFIG_HOME
    overrides on relay.py forge commands. Reading, searching, diffing, or running same-named scripts elsewhere pass."""
    checked = command_line(command)
    words = words_of(checked.replace("\n", " ; "))
    cur_cwd = cwd or os.getcwd()
    is_forge = False
    for prog_raw, args in _split_simple_commands(words):
        prog = os.path.basename(prog_raw)
        if prog == "cd" and args and not args[0].startswith("-"):
            target = re.sub(r"^\$(HOME\b|\{HOME\})", str(Path.home()), args[0])
            if "$" not in target and "`" not in target:
                cur_cwd = os.path.realpath(os.path.join(cur_cwd, os.path.expanduser(target)))
            continue
        if _is_own_forge_script(prog_raw, cur_cwd):
            return True
        if prog.startswith("python") or prog == "uv":
            # Find the script argument passed to python/uv run (stopping at -c / -m).
            idx = 1 if (prog == "uv" and args[:1] == ["run"]) else 0
            while idx < len(args):
                tok = args[idx]
                if tok in ("-c", "-m"):
                    break
                if tok.startswith("-"):
                    idx += 2 if tok in ("-W", "-X", "--python") else 1
                    continue
                if _is_own_forge_script(tok, cur_cwd):
                    return True
                if os.path.basename(tok) == "relay.py" and subcommand(args[idx + 1:])[:1] == ["forge"]:
                    is_forge = True
                break
        elif prog == "relay.py" and subcommand(args)[:1] == ["forge"]:
            is_forge = True
    if is_forge and re.search(r"(?:^|[\s;|&(])(?:export\s+)?(?:XDG_CONFIG_HOME|HOME)\s*=", checked):
        return True
    return False


def denied_command(command):
    """Whether a shell command runs one of the denied T3, GitHub, restart or out-of-scope forge actions, also behind
    global options, quotes or bash -c. A quoted heredoc fed to Rook's relay.py or to t3 thread is a brief, so only
    its command line counts."""
    checked = command_line(command)
    try:
        flat = " ".join(shlex.split(checked))
    except ValueError:
        flat = checked
    return bool(DENIED_COMMANDS.search(checked) or DENIED_COMMANDS.search(flat) or denied_words(words_of(checked))
                or stops_rook(checked) or denied_forge(command))


SYSTEMCTL_READS = {"status", "show", "cat", "is-active", "is-enabled", "is-failed", "list-units", "list-unit-files"}
LAUNCHCTL_READS = {"print", "print-cache", "print-disabled", "list", "blame"}
OPERATORS = (";", "&&", "||", "|", "&", "(", ")")


def commands(command):
    """Each simple command of a line, as (program name, its words after it), through sudo, xargs, bash -c and the
    like. Words inside quotes are arguments, so a quoted sentence such as 'kill the rook timer' runs nothing."""
    found, program = [], True
    for word in words_of(command.replace("\n", " ; ")):
        if word in OPERATORS:
            program = True
        elif program and (re.match(r"\w+=", word) or word.startswith("-")
                          or os.path.basename(word) in WRAPPERS | {"bash", "sh", "zsh"}):
            continue  # An assignment, a wrapper or its option: the program comes after it.
        elif program:
            found.append((os.path.basename(word), []))
            program = False
        else:
            found[-1][1].append(word)
    return found


def stops_rook(command):
    """Whether a command stops or restarts Rook through systemctl, launchctl, kill or relay's module, or merges a pull request
    through GitHub's API. Judged on program words, never on quoted text."""
    for name, args in commands(command):
        verb = next((arg for arg in args if not arg.startswith("-")), "")
        rook = any("rook" in arg.lower() for arg in args)
        hidden = any("$" in arg or "`" in arg for arg in args) or name == "kill" and not args  # A pid from elsewhere.
        if (name == "systemctl" and rook and verb not in SYSTEMCTL_READS
                # Rook's job, its <label>.daily restart, or a glob with rook in it that the shell may expand to them.
                or name == "launchctl" and verb not in LAUNCHCTL_READS
                and any(desk.LAUNCHD_LABEL.lower() in arg.lower()
                        or "rook" in arg.lower() and any(glob in arg for glob in "*?[") for arg in args)
                or name in ("kill", "pkill", "killall") and (rook or hidden and "rook" in command.lower())
                or name == "kill" and "-1" in args  # Every process the owner owns, Rook among them.
                or name in ("pkill", "killall") and any("python" in arg for arg in args)  # Rook runs as python.
                or name.startswith("python") and any(arg == "-mrelay" or arg == "relay" and args[at - 1:at] == ["-m"]
                                                     for at, arg in enumerate(args))
                and any(arg in ("restart", "reload", "daily-restart") for arg in args)
                or name in ("gh", "curl") and any("mergePullRequest" in arg for arg in args)):
            return True
    return False


# Rook never edits itself: agy's file tools may not write in this checkout, the live install, or its parent repo.
def _rook_code_roots():
    roots = [ROOT, desk.data_dir() / "rook/live"]
    dot_git = ROOT / ".git"
    if dot_git.is_file():
        try:
            line = dot_git.read_text(errors="replace").strip()
            if line.startswith("gitdir:"):
                gitdir = Path(line.split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = (ROOT / gitdir).resolve()
                if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
                    roots.append(gitdir.parent.parent.parent)
        except OSError:
            pass
    return tuple(dict.fromkeys(Path(os.path.realpath(path)) for path in roots))


ROOK_CODE = _rook_code_roots()
# Nor the guard, keys, agent settings or global instructions: Rook's private agy home (with this hook's own file), the
# command guard DCG, SSH and GPG keys, the agents' settings and global instructions and skills (a thread changes those
# through agents-sync), and user services and their environment. Those are the owner's to do, or a thread's.
PROTECTED_ROOTS = tuple(dict.fromkeys(Path(os.path.realpath(path)) for path in (
    HOME, DCG, shutil.which("dcg") or DCG, Path.home() / ".config/dcg", Path.home() / ".ssh", Path.home() / ".gnupg",
    Path.home() / ".claude", Path.home() / ".codex", Path.home() / ".gemini", Path.home() / ".agents",
    Path.home() / ".config/systemd", Path.home() / ".config/environment.d")))
# agy 1.5 names them write_file and edit_file; the others are older agy's names, kept for an older install.
WRITE_TOOLS = {"write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content", "sed_file",
               "notebook_edit"}


def rook_path(word, cwd=None):
    """Whether a word names a path inside Rook's code or a protected root, also through a link, a file:// URI, ~ or
    $HOME. A relative path counts from cwd; with no cwd, only an absolute one counts."""
    word = re.sub(r"^\$(HOME\b|\{HOME\})", str(Path.home()), re.sub(r"^file://", "", word))
    if not word or "\n" in word or not (word.startswith(("/", "~")) or cwd):
        return False
    path = Path(os.path.realpath(os.path.join(cwd or "/", os.path.expanduser(word))))
    return any(path == root or root in path.parents for root in ROOK_CODE + PROTECTED_ROOTS)


def strings_in(value):
    """Every string in a tool's arguments, also inside nested objects and lists."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, (dict, list)):
        for item in value.values() if isinstance(value, dict) else value:
            yield from strings_in(item)


def writes_rook(args, cwd=None):
    """Whether a file tool's arguments name a path inside Rook's code or a protected root. Every path counts, whatever
    its key or nesting."""
    return any(rook_path(value, cwd) for value in strings_in(args))


# Shell programs that write: any path they name, or for the second set only the last, their destination.
WRITERS = {"tee", "rm", "mv", "touch", "chmod", "truncate", "patch", "dd"}
DESTINATION_WRITERS = {"cp", "install", "ln", "rsync"}
GIT_READS = {"status", "log", "diff", "show", "grep", "blame", "rev-parse", "ls-files", "fetch", "rev-list", "describe",
             "shortlog", "cat-file", "for-each-ref", "merge-base"}
# Verbs that read only with these next words: git stash alone stashes, and reflog expire and delete write.
GIT_LISTS = {"remote": ("show", "get-url"), "stash": ("list", "show"), "worktree": ("list",), "reflog": ("show",)}
# Verbs that read with no next word and only these flags. Any other flag, such as --set-upstream-to, writes.
GIT_FLAG_READS = {"branch": {"-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "-l", "--list", "--show-current",
                             "--contains", "--no-contains", "--merged", "--no-merged", "--sort", "--format",
                             "--points-at", "--color", "--no-color", "--column", "--no-column"},
                  "remote": {"-v", "--verbose"}, "reflog": set()}
GIT_VALUE_FLAGS = {"--contains", "--no-contains", "--merged", "--no-merged", "--sort", "--format", "--points-at"}


def git_reads(verb, args):
    """Whether git with this verb and these words only reads."""
    if verb in GIT_READS:
        return True
    rest = args[args.index(verb) + 1:] if verb in args else []
    flags = [arg.split("=", 1)[0] for arg in rest if arg.startswith("-")]
    words = [arg for at, arg in enumerate(rest) if not arg.startswith("-") and not (at and rest[at - 1] in GIT_VALUE_FLAGS)]
    if verb in GIT_FLAG_READS and all(flag in GIT_FLAG_READS[verb] for flag in flags) and (
            not words or verb == "branch" and {"-l", "--list"} & set(flags)):  # branch --list takes patterns.
        return True
    return bool(words) and words[0] in GIT_LISTS.get(verb, ())


def shell_writes_rook(command, cwd=None):
    """Whether a shell command writes in Rook's code: a writing program, sed -i, a git command that changes the
    checkout, or a > redirect, on a path in it. A cd in the line moves where relative paths count from."""
    for name, args in commands(command_line(command)):
        paths = [arg for arg in args if not arg.startswith("-") and arg not in (">", ">>")]
        if name == "cd" and paths:
            cwd = os.path.join(cwd or "/", os.path.expanduser(paths[0]))
            continue
        verb = next((arg for at, arg in enumerate(args)  # git's verb: past its options and their values.
                     if not arg.startswith("-") and (at == 0 or args[at - 1] not in ("-C", "-c"))), "")
        if (any(args[at] in (">", ">>") and rook_path(args[at + 1], cwd) for at in range(len(args) - 1))
                or (name in WRITERS or name == "sed" and any(a.startswith("-i") or a == "--in-place" for a in args))
                and any(rook_path(arg, cwd) for arg in paths)
                or name in DESTINATION_WRITERS and paths and rook_path(paths[-1], cwd)
                or name == "git" and not git_reads(verb, args)
                and (any(rook_path(arg, cwd) for arg in args) or cwd and rook_path(".", cwd))):
            return True
    return False


def edit(text, table, where):
    for old, new in table:
        if old not in text:
            raise ValueError(f"{where} no longer holds {old!r}. Update the table in {__file__}.")
        text = text.replace(old, new)
    return text


def skills(target, wow=False):
    """Copy skills/ (plus wow/skills when wow is on and present) to target, rendered for Antigravity, naming Rook's owner."""
    import harness  # Here, so that the guard starts fast.
    sources = harness.skill_sources(wow=wow)
    include_wow = any((folder / "wow/SKILL.md").is_file() for folder in sources)
    edits = {}
    for path, old, new in SKILLS:
        if path in OPTIONAL_SKILLS and not include_wow:
            continue
        edits.setdefault(path, []).append((old, new))
    for source in sources:
        for file in sorted(source.rglob("*")):
            rel = file.relative_to(source)
            if not file.is_file() or "__pycache__" in rel.parts:
                continue
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if file.suffix != ".md":
                shutil.copyfile(file, out)
                continue
            text = (file.read_text().replace("${CLAUDE_SKILL_DIR}", str(source / rel.parts[0]))
                    .replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT / "plugin")))
            if rel.name == "SKILL.md":  # Claude Code's permission syntax. It means nothing to Antigravity.
                text = re.sub(r"(?m)^allowed-tools:.*\n", "", text, count=1)
            text = harness.bare_skill_names(owned(edit(text, edits.pop(str(rel), []), f"{source.relative_to(ROOT)}/{rel}")))
            if left := [name for name in CLAUDE_ONLY if name in text]:
                raise ValueError(f"{source.relative_to(ROOT)}/{rel} still names {left}. Add an entry to SKILLS in {__file__}.")
            out.write_text(text)
    if edits:
        raise ValueError(f"skills/ has no {sorted(edits)}. Update SKILLS in {__file__}.")


def copy(path, source):
    """Copy source to path. The old file goes first: a link left by an older Rook would take the copy to its target."""
    path.unlink(missing_ok=True)
    shutil.copyfile(source, path)


_WARNED = set()


def warn_once(key, text):
    """Print one notice to stderr per missing optional file or tool."""
    if key not in _WARNED:
        _WARNED.add(key)
        print(text, file=sys.stderr)


def dcg_configured():
    """Whether this person set DCG up, so its absence is worth a line. Most people never install it."""
    return (Path.home() / ".config/dcg").exists()


def dcg_path():
    """Return the DCG binary path when installed, else None."""
    if DCG.is_file() and os.access(DCG, os.X_OK):
        return str(DCG)
    return shutil.which("dcg")


def skills_entries(rook_dir=None, shared_dirs=None, plugin_dirs=None, host_skills=None):
    """Return skills.json entries for Rook's skills folder, the active user plugins' skills folders, and each
    allowed host skill alone, from the first shared folder that has it."""
    if plugin_dirs is None:
        import harness  # Here, so that the guard starts fast.
        plugin_dirs = harness.plugin_user_skills()
    if host_skills is None:
        import plugin_loader  # Here, never at the top: the guard must not import it.
        host_skills = plugin_loader.host_skills_allow()
    rook_dir = ROOK_SKILLS if rook_dir is None else Path(rook_dir)
    shared_dirs = (AGENTS / "skills", GEMINI_SKILLS) if shared_dirs is None else tuple(Path(d) for d in shared_dirs)
    entries = [{"path": str(rook_dir)}, *({"path": str(folder)} for folder in plugin_dirs)]
    found = {}
    for name in dict.fromkeys(host_skills):
        if folder := next((folder for folder in shared_dirs if (folder / name / "SKILL.md").is_file()), None):
            found.setdefault(folder, []).append(name)
    entries.extend({"path": str(folder), "include_only": names} for folder, names in found.items())
    return entries


def build(wow=False):
    """Build HOME/config and return HOME, the folder for agy's --gemini-dir."""
    config = HOME / "config"
    plugin = config / "plugins/rook"
    if plugin.exists():
        shutil.rmtree(plugin)  # The render from Rook's last start.
    skills(plugin / "skills", wow=wow)
    shutil.copyfile(ROOT / "plugin/.claude-plugin/plugin.json", plugin / "plugin.json")
    agents_md = AGENTS / "AGENTS.md"
    if agents_md.is_file():
        copy(config / "AGENTS.md", agents_md)
    else:
        (config / "AGENTS.md").unlink(missing_ok=True)
        if AGENTS.is_dir():  # Said only to a person who keeps a shared setup there.
            warn_once("agents_md", f"antigravity: {agents_md} is missing, skipping global instructions.")
    (config / "skills.json").write_text(json.dumps({"entries": skills_entries()}))
    # agy reads its default project on every request and logs an error when it is missing. The same file agy
    # writes for the owner's own CLI, which holds no setting.
    (config / "projects").mkdir(exist_ok=True)
    (config / "projects/default-cli-project.json").write_text(json.dumps(
        {"id": "default-cli-project", "name": "CLI Project", "projectResources": {}}, indent=2) + "\n")
    guard_command = f"{desk.python3_exe()} -I {shlex.quote(str(Path(__file__).resolve()))} guard"
    (config / "hooks.json").write_text(json.dumps({"dcg": {"PreToolUse": [
        {"matcher": ".*",  # Every tool. agy's matcher is a regular expression.
         "hooks": [{"type": "command", "command": guard_command, "timeout": 30}]}]}}))
    import plugin_loader  # Here, never at the top: the guard must not import it.
    policy, data = config / "guard_policy.json", plugin_loader.guard_policy()
    if data["servers"] or data["relay_commands"] or data["read_only_commands"]:
        policy.write_text(json.dumps(data))
    else:  # No plugin adds policy: no file, which is the static policy, so the folder matches a Rook without plugins.
        policy.unlink(missing_ok=True)
    POLICY.update(load_policy(policy))  # Rook's own policy, decide(), reads the same checked data as the hook.
    if dcg_path() is None and dcg_configured():
        warn_once("dcg", f"antigravity: {DCG} is not installed, skipping DCG command guard.")
        try:
            (HOME / ".dcg-warned").touch()
        except OSError:
            pass
    return HOME


def memory(workspace):
    """What the session start hook tells Claude Code: the machine (if present), and the memory folder with its index."""
    hook = AGENTS / "hooks/machine-context.sh"
    if not hook.is_file():
        hook = AGENTS / "hooks/memory-context.sh"
    if not hook.is_file():
        return ""
    try:
        done = subprocess.run(["bash", str(hook)], cwd=workspace, timeout=10,
                              input=json.dumps({"cwd": str(workspace)}), capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip()


def prompt(text, workspace, beats=False):
    """Antigravity's system prompt append, from Rook's prompt for Claude Code."""
    # The prompt came rendered from rook.py, where its data passes as it is. Only the table's own words fill in here.
    table = [(old, owned(new.replace(PROMPT_BEATS_DROP, "") if beats else new)) for old, new in PROMPT]
    return (edit(text, table, "Rook's system prompt")
            + owned("\n\nSession start lines, from ⟦owner⟧'s session start hook:\n") + memory(workspace))


def setup(wow):
    """Antigravity's setup turn text, from Claude Code's. wow is whether to load the rook:wow skill."""
    import harness  # Here, so that the guard starts fast.
    return edit(harness.Claude().setup({}, [], wow), SETUP, "Claude's setup turn")


def owned(text):
    """text naming Rook's owner. The settings module loads only here: the tool hook runs on every tool call."""
    import settings
    return settings.render(text)


def guard():
    """agy's PreToolUse hook. Every call gets a decision. The guard fails open: a tool call it cannot read, such as
    a path with a NUL byte or input that is not JSON, is allowed, never left with a traceback."""
    try:
        _guard()
    except Exception:  # Fails open on any call it cannot read, such as args that are not an object.
        print(json.dumps({"decision": "allow", "reason": ""}))


def _guard():
    """deny a tool Rook does not have, and Rook's denied commands, then ask DCG about a command, in Claude Code's
    hook shape, and answer in agy's. A denial's reason reaches the model, which goes on with the turn. A tool that
    passes still meets its permission request, where Rook's policy decides."""
    POLICY.update(load_policy())
    call = json.load(sys.stdin)
    args = call.get("toolCall", {}).get("args", {})
    if not allowed_tool(tool := str(call.get("toolCall", {}).get("name")).strip().lower(), args):
        print(json.dumps({"decision": "deny", "reason": f"Rook's rules deny {tool}: Rook never starts subagents, "
                                                        "messages other agents, schedules work, drives a browser or "
                                                        "types into a running shell. Do the work yourself."}))
        return
    if denied_t3_tool(tool, args):
        print(json.dumps({"decision": "deny", "reason": owned("Rook's rules deny this T3 tool: deleting a project, "
                                                              "linking or unlinking a machine, and merging a pull "
                                                              "request are ⟦owner⟧'s to do. Tell ⟦him⟧ so.")}))
        return
    if (t3 := t3_tool(tool, args)) is not None and not t3_allowed(t3, mcp_call(args)[2] if tool == "call_mcp_tool"
                                                                  else args):
        if t3 in T3_STARTS_WORK:
            reason = ("Rook does not use this T3 tool. Send to or start a thread with t3_thread_send or "
                      "t3_thread_launch, or with the t3 command, as your delegate skill shows: Rook watches the "
                      "threads it sends to that way.")
        else:
            reason = owned("Rook does not do this through T3 here. Tell ⟦owner⟧ in one sentence that it is ⟦hers⟧ to do.")
        print(json.dumps({"decision": "deny", "reason": reason}))
        return
    cwd = args.get("Cwd") or (call.get("workspacePaths") or [None])[0]
    if (tool in WRITE_TOOLS and writes_rook(args, cwd)
            or tool == "run_command" and shell_writes_rook(args.get("CommandLine", ""), cwd)):
        print(json.dumps({"decision": "deny", "reason": owned("Rook's rules deny writing in Rook's own code, its "
                                                              "command guard, keys, agent settings, global instructions "
                                                              "or user services. That is ⟦owner⟧'s to do, or a thread's: "
                                                              "changes to Rook go to the build thread. Tell ⟦owner⟧ so.")}))
        return
    if tool != "run_command":
        print(json.dumps({"decision": "allow", "reason": ""}))
        return
    if hidden_program(args.get("CommandLine", "")):
        print(json.dumps({"decision": "deny", "reason": "Rook's rules deny a command whose program comes from a "
                                                        "variable, such as $T: the guard cannot see what it runs. "
                                                        "Write the command plainly."}))
        return
    if denied_forge(args.get("CommandLine", ""), cwd):
        print(json.dumps({"decision": "deny", "reason": "Rook's forge must run through relay.py forge (never bake.py, "
                                                        "forge.py, or preview.py directly), may write only under "
                                                        "~/.config/rook/themes/ with plain non-built-in theme and icon "
                                                        "names, and may not override HOME or XDG_CONFIG_HOME."}))
        return
    if denied_command(args.get("CommandLine", "")):
        print(json.dumps({"decision": "deny", "reason": owned("Rook's rules deny this command: deleting a T3 "
                                                              "project, linking or unlinking a machine, T3 sign-in "
                                                              "tokens, merging a pull request, and restarting or "
                                                              "stopping Rook are ⟦owner⟧'s or the build thread's to do. "
                                                              "Tell ⟦him⟧ so.")}))
        return
    dcg = dcg_path()
    if dcg is None:
        marker = HOME / ".dcg-warned"
        if not marker.exists() and dcg_configured():
            warn_once("dcg", f"antigravity: {DCG} is not installed, skipping DCG command guard.")
            if HOME.is_dir():
                try:
                    marker.touch()
                except OSError:
                    pass
        print(json.dumps({"decision": "allow", "reason": ""}))
        return
    ask = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
           "tool_input": {"command": args.get("CommandLine", "")},
           "cwd": args.get("Cwd") or (call.get("workspacePaths") or [os.getcwd()])[0]}
    try:
        done = subprocess.run([dcg], input=json.dumps(ask), capture_output=True, text=True, timeout=20)
        if done.returncode:
            raise RuntimeError(f"dcg exited with {done.returncode}")
        verdict = json.loads(done.stdout).get("hookSpecificOutput", {}) if done.stdout.strip() else {}
        decision = {"deny": "deny", "ask": "ask"}.get(verdict.get("permissionDecision"), "allow")
        answer = {"decision": decision, "reason": verdict.get("permissionDecisionReason", "")}
    except Exception as error:  # DCG stays on: a command it cannot check does not run.
        answer = {"decision": "deny", "reason": f"Rook's command guard, DCG, could not check this command: {error}"}
    print(json.dumps(answer))


def check():
    """Test the three tables against today's skills/, rook.py and harness.py, and the guard against DCG."""
    import tempfile
    has_wow_skill = (ROOT / "wow/skills/wow/SKILL.md").is_file()
    has_wow_server = "wow" in ROOK_SERVERS
    with tempfile.TemporaryDirectory() as scratch:
        plain = Path(scratch) / "plain"
        skills(plain, wow=False)
        for name in ("about", "dark", "delegate", "extend", "forge", "media", "onboarding", "settings", "show"):
            assert (plain / name / "SKILL.md").read_text().startswith(f"---\nname: {name}\n")
        # agy lists Rook's skills by bare name, so the rendered skills name each other that way too.
        left = [str(f) for f in plain.rglob("*.md") if re.search(r"\brook:[a-z]", f.read_text())]
        assert not left and "the delegate skill" in (plain / "settings/SKILL.md").read_text(), left
        assert not (plain / "wow").exists()
        with_wow = Path(scratch) / "wow"
        skills(with_wow, wow=True)
        expected = ("about", "dark", "delegate", "extend", "forge", "media", "onboarding", "settings", "show") + (("wow",) if has_wow_skill else ())
        for name in expected:
            assert (with_wow / name / "SKILL.md").read_text().startswith(f"---\nname: {name}\n")
        if not has_wow_skill:
            assert not (with_wow / "wow").exists()
    edit((ROOT / "desktop/rook.py").read_text(), PROMPT, "desktop/rook.py")
    # Opt-in beats=True lifts the once-per-turn cap while preserving PASS silence on non-owner turns.
    sample_prompt = (
        "a full Claude Code session; that your session start message names; "
        "Before your first tool call, you may write one short sentence. Confirm it in a few words. Never write filler."
    )
    default_p = prompt(sample_prompt, str(ROOT), beats=False)
    beats_p = prompt(sample_prompt, str(ROOT), beats=True)
    assert "first sentence once in a turn" in default_p and "PASS stays silent" in default_p, default_p
    assert "first sentence once in a turn" not in beats_p and "PASS stays silent" in beats_p, beats_p
    if has_wow_skill:
        assert "rook:wow" in setup(True) and "rook:wow" not in setup(False)
    else:
        assert "rook:wow" not in setup(True) and "rook:wow" not in setup(False)
    assert not any(name in setup(True) for name in CLAUDE_ONLY)
    live_root = desk.data_dir() / "rook/live"
    code_root = ROOT
    has_dcg = dcg_path() is not None
    for tool, command, decision, reason in (
                                            ("run_command", "git reset --hard",
                                             "deny" if has_dcg else "allow", "BLOCKED by dcg" if has_dcg else ""),
                                            ("run_command", "echo hello", "allow", ""),
                                            ("run_command", f"/usr/bin/python {ROOT}/desktop/relay.py media status", "allow", ""),
                                            ("run_command", f"/usr/bin/python {ROOT}/desktop/relay.py media pause", "allow", ""),
                                            ("run_command", "t3 'project' remove x", "deny", "Rook's rules"),
                                            ("invoke_subagent", "", "deny", "Rook's rules"),
                                            ("browser_click_element", "", "deny", "Rook's rules"),
                                            ("schedule", "", "deny", "Rook's rules"),
                                            ("a_tool_agy_adds_later", "", "deny", "Rook's rules"),
                                            ("view_file", "", "allow", ""),
                                            ("mcp_wow_find_npc", "", "allow" if has_wow_server else "deny",
                                             "" if has_wow_server else "Rook's rules"),
                                            ("mcp_t3_t3_project_delete", "", "deny", "Rook's rules"),
                                            ("mcp_t3_t3_thread_list", "", "allow", ""),
                                            ("mcp_t3_t3_thread_send", "", "deny" if T3_SENDS_BY_COMMAND else "allow",
                                             "t3 command" if T3_SENDS_BY_COMMAND else ""),
                                            # The reviewer's routes around full permission, 2026-11-23.
                                            ("run_command", "T=t3; $T project remove demo", "deny", "plainly"),
                                            ("run_command", "${T:-t3} project remove demo", "deny", "plainly"),
                                            ("run_command", "systemctl --user restart rook.service", "deny", "Rook's"),
                                            ("run_command", "systemctl --user status rook", "allow", ""),
                                            ("run_command", "kill $(pgrep -f rook.py)", "deny", "Rook's rules"),
                                            ("run_command", "cd desktop && python3 -m relay restart", "deny", "Rook's"),
                                            ("run_command", "env -u ROOK_AGENT python3 /tmp/r.py restart", "deny",
                                             "Rook's rules"),
                                            ("run_command", "gh api graphql -f query='mutation{mergePullRequest}'",
                                             "deny", "Rook's rules"),
                                            ("run_command", "gh alias set m 'pr merge'", "deny", "Rook's rules"),
                                            ("write_to_file", str(code_root / "desktop/rook.py"), "deny", "own code"),
                                            ("sed_file", str(live_root / "desktop/relay.py"), "deny", "own code"),
                                            ("write_to_file", "/tmp/rook-note.txt", "allow", ""),
                                            # agy 1.5's own file tools: Rook edits its own notes, never its code.
                                            ("edit_file", str(desk.config_dir() / "rook/model-preferences.md"),
                                             "allow", ""),
                                            ("write_file", str(Path.home() / "Work/note.md"), "allow", ""),
                                            ("edit_file", str(code_root / "desktop/rook.py"), "deny", "own code"),
                                            ("write_file", str(live_root / "desktop/relay.py"), "deny",
                                             "own code")):
        if command == "git reset --hard" and dcg_path() is None:
            continue  # Without DCG installed, this check's no-DCG block below verifies the fallback.
        done = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, input=json.dumps(
            {"toolCall": {"name": tool, "args": {"CommandLine": command}}, "workspacePaths": ["/tmp"]}))
        answer = json.loads(done.stdout)
        assert answer["decision"] == decision and reason in answer["reason"], (command, answer)
    # Also test DCG denial with a stand-in dcg executable when DCG is not installed on this machine.
    with tempfile.TemporaryDirectory() as fake_dcg_dir:
        fake_dcg = Path(fake_dcg_dir) / "dcg"
        fake_dcg.write_text(
            f"#!{sys.executable}\nimport json, sys\n"
            "cmd = (json.loads(sys.stdin.read()).get('tool_input') or {}).get('command', '')\n"
            "if 'git reset --hard' in cmd:\n"
            "    print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'deny', 'permissionDecisionReason': 'BLOCKED by dcg'}}))\n"
        )
        fake_dcg.chmod(0o755)
        fake_env = {**os.environ, "PATH": f"{fake_dcg_dir}:/usr/bin:/bin", "HOME": fake_dcg_dir}
        done = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, env=fake_env,
                              input=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "git reset --hard"}},
                                                "workspacePaths": ["/tmp"]}))
        answer = json.loads(done.stdout)
        assert answer["decision"] == "deny" and "BLOCKED by dcg" in answer["reason"], answer
    for server, name, decision in (("t3", "pull_request_merge", "deny"), ("t3", "t3_thread_read", "allow"),
                                   ("wow", "pull_request_merge", "allow" if has_wow_server else "deny")):  # agy's lazy form, through call_mcp_tool.
        done = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, input=json.dumps(
            {"toolCall": {"name": "call_mcp_tool", "args": {"ServerName": server, "ToolName": name}}}))
        assert json.loads(done.stdout)["decision"] == decision, (server, name, done.stdout)
    # A variable as an argument, or in a send's brief, is no hidden program.
    for command in ("ls -la $HOME", "FOO=1 ls", "echo \"$PATH\"", "t3 thread send T1 - <<'EOF'\nIt costs\n$5; $T\nEOF"):
        assert not hidden_program(command), command
    for command in ("echo x | $T", "FOO=1 $T x", "env $T x", "bash -c \"$(printf 't3 proj''ect remove demo')\"", "ls\n$T project remove demo", "`which t3` auth"):
        assert hidden_program(command), command
    with tempfile.TemporaryDirectory() as scratch:  # A link into Rook's code is Rook's code.
        (Path(scratch) / "r").symlink_to(code_root)
        assert writes_rook({"TargetFile": f"{scratch}/r/desktop/rook.py"}) and not writes_rook({"TargetFile": scratch})
    # Review 2, fix 6: $HOME and relative paths count, and shell programs that write there are refused too.
    work = str(code_root.parent)
    rel_rook = code_root.name
    qroot = shlex.quote(str(code_root))
    qlive = shlex.quote(str(live_root))
    assert writes_rook({"TargetFile": str(code_root / "desktop/rook.py")})
    assert writes_rook({"TargetFile": f"{rel_rook}/desktop/rook.py"}, work)
    for command in (f"sed -i s/a/b/ {qroot}/desktop/rook.py", f"tee {qroot}/x < y",
                    f"cp /tmp/x {qlive}/desktop/relay.py", f"mv {qroot}/a /tmp/b",
                    f"git -C {qroot} commit -am x", f"cd {qroot} && git commit -am x",
                    f"echo x > {rel_rook}/desktop/rook.py", f"rm {qlive}/desktop/relay.py"):
        assert shell_writes_rook(command, work), command
    for command in (f"sed -n 1,5p {qroot}/desktop/rook.py", f"cp {qroot}/desktop/rook.py /tmp/r.py",
                    f"git -C {qroot} log -3", f"cd {qroot} && git status", f"grep -rn tee {qroot}",
                    "echo x > /tmp/out", "rm /tmp/x",
                    # Review 3, fix 2: git reads in Rook's repo.
                    f"git -C {qroot} branch -a", f"git -C {qroot} remote -v", f"git -C {qroot} worktree list",
                    f"git -C {qroot} stash list", f"git -C {qroot} rev-list --count main",
                    f"git -C {qroot} describe --tags", f"cd {qroot} && git branch --show-current"):
        assert not shell_writes_rook(command, work), command
    assert not shell_writes_rook(f"/usr/bin/python relay.py set voice 'Miles' --say 'Hi; rm {qroot} ok'", work)
    assert shell_writes_rook(f"bash -c 'rm {qroot}/desktop/rook.py'", work)  # A shell's -c command still counts.
    # Review 4: reflog writes, other flags of branch and remote, and every shell's or python's -c count as writes.
    for command in (f"git -C {qroot} reflog expire --expire=now --all", f"git -C {qroot} reflog delete HEAD@{{1}}",
                    f"git -C {qroot} branch --set-upstream-to=origin/x", f"git -C {qroot} branch --unset-upstream",
                    f"git -C {qroot} branch --edit-description", f"bash -x -c 'rm {qroot}/desktop/rook.py'",
                    f"bash -c -- 'git -C {qroot} commit -am x'",
                    f"python3 -c 'import os; os.system(\"rm {code_root}/desktop/rook.py\")'"):
        assert shell_writes_rook(command, work), command
    for command in (f"git -C {qroot} reflog", f"git -C {qroot} reflog show -5", f"git -C {qroot} branch -vv",
                    f"git -C {qroot} branch --contains main", f"git -C {qroot} branch --list 'feat*'"):
        assert not shell_writes_rook(command, work), command
    for command in ("bash -x -c 'python3 -m relay restart'", "sh -c -- 'systemctl --user restart rook'",
                    "python3 -c 'import os; os.system(\"systemctl --user restart rook\")'"):
        assert denied_command(command), command
    for command in (f"git -C {qroot} stash", f"git -C {qroot} branch -D old", f"git -C {qroot} remote add x y",
                    f"git -C {qroot} worktree add /tmp/w"):
        assert shell_writes_rook(command, work), command
    global HOME, AGENTS  # build() copies ~/.agents/AGENTS.md when present, and replaces any stale symlink.
    real_home, HOME = HOME, Path(tempfile.mkdtemp())
    try:
        (HOME / "config").mkdir()
        (HOME / "config/AGENTS.md").symlink_to(HOME / "owners.md")
        (HOME / "owners.md").write_text("The owner's own.")
        build()
        made = HOME / "config/AGENTS.md"
        if (AGENTS / "AGENTS.md").is_file():
            assert not made.is_symlink() and made.read_text() == (AGENTS / "AGENTS.md").read_text()
        else:
            assert not made.exists()
        assert (HOME / "owners.md").read_text() == "The owner's own."
        # Always verify copying when AGENTS.md exists, even on a machine without ~/.agents.
        real_agents_for_copy = AGENTS
        try:
            with tempfile.TemporaryDirectory() as sample_agents:
                AGENTS = Path(sample_agents)
                (AGENTS / "AGENTS.md").write_text("Sample global instructions.\n")
                made.unlink(missing_ok=True)
                made.symlink_to(HOME / "owners.md")
                build()
                assert not made.is_symlink() and made.read_text() == "Sample global instructions.\n"
                assert (HOME / "owners.md").read_text() == "The owner's own."
        finally:
            AGENTS = real_agents_for_copy
            build()
        hooks = json.loads((HOME / "config/hooks.json").read_text())
        hook_cmd = shlex.split(hooks["dcg"]["PreToolUse"][0]["hooks"][0]["command"])
        assert "-I" in hook_cmd, hook_cmd
        # Run the exact generated hook command from outside the repo so isolated mode (-I) is exercised live.
        with tempfile.TemporaryDirectory() as scratch:
            scratch_rt = Path(scratch) / "runtime"
            (scratch_rt / "rook-antigravity").mkdir(parents=True)
            hook_env = {**os.environ, "XDG_RUNTIME_DIR": str(scratch_rt)}
            for payload, expected in (
                ({"toolCall": {"name": "view_file", "args": {"Path": "/tmp/x"}}}, "allow"),
                ({"toolCall": {"name": "run_command", "args": {"CommandLine": "echo hi"}},
                  "workspacePaths": [scratch]}, "allow"),
                ({"toolCall": {"name": "run_command", "args": {"CommandLine": "t3 project remove demo"}},
                  "workspacePaths": [scratch]}, "deny"),
            ):
                done = subprocess.run(hook_cmd, cwd=scratch, env=hook_env, capture_output=True, text=True,
                                      input=json.dumps(payload))
                assert done.returncode == 0, (hook_cmd, done.returncode, done.stderr)
                answer = json.loads(done.stdout)
                assert answer.get("decision") == expected and isinstance(answer.get("reason"), str), (payload, answer)
        written = json.loads((HOME / "config/skills.json").read_text())["entries"]
        import harness
        import plugin_loader
        expected = [{"path": str(ROOK_SKILLS)}, *({"path": str(folder)} for folder in harness.plugin_user_skills())]
        grouped = {}  # Each active plugin's host skill, from the first folder with it, grouped by folder.
        for name in dict.fromkeys(plugin_loader.host_skills_allow()):
            if folder := next((f for f in (AGENTS / "skills", GEMINI_SKILLS) if (f / name / "SKILL.md").is_file()), None):
                grouped.setdefault(str(folder), []).append(name)
        expected += [{"path": folder, "include_only": names} for folder, names in grouped.items()]
        assert written == expected, written
        # Skills entries: prefer the first shared folder with the skill, fall back to the next, survive missing dirs,
        # group skills by folder, and offer no host skill that no active plugin allows.
        with tempfile.TemporaryDirectory() as fake:
            base = Path(fake)
            a, b, missing = base / "a", base / "b", base / "missing-rook"
            (b / "omarchy").mkdir(parents=True)
            (b / "omarchy/SKILL.md").write_text("---\nname: omarchy\n---\n")
            assert skills_entries(missing, (a, b), (), ("omarchy",)) == [
                {"path": str(missing)}, {"path": str(b), "include_only": ["omarchy"]}]
            (a / "omarchy").mkdir(parents=True)
            (a / "omarchy/SKILL.md").write_text("---\nname: omarchy\n---\n")
            assert skills_entries(missing, (a, b), (), ("omarchy",)) == [
                {"path": str(missing)}, {"path": str(a), "include_only": ["omarchy"]}]
            assert skills_entries(missing, (a, b), (), ()) == [{"path": str(missing)}]
            (b / "extra").mkdir()
            (b / "extra/SKILL.md").write_text("---\nname: extra\n---\n")
            assert skills_entries(missing, (a, b), (), ("extra", "omarchy", "extra")) == [
                {"path": str(missing)}, {"path": str(b), "include_only": ["extra"]},
                {"path": str(a), "include_only": ["omarchy"]}]
            (a / "extra").mkdir()
            (a / "extra/SKILL.md").write_text("---\nname: extra\n---\n")
            assert skills_entries(missing, (a, b), (), ("omarchy", "extra")) == [
                {"path": str(missing)}, {"path": str(a), "include_only": ["omarchy", "extra"]}]
            assert skills_entries(missing, (base / "none1", base / "none2"), (), ("omarchy",)) == [{"path": str(missing)}]
        # build() succeeds without ~/.agents/AGENTS.md, removes any stale copy, and logs once.
        import contextlib
        import io
        real_agents = AGENTS
        saved_warned = set(_WARNED)
        _WARNED.discard("agents_md")
        try:
            with tempfile.TemporaryDirectory() as empty_agents:
                AGENTS = Path(empty_agents)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    build()
                    build()
                assert not (HOME / "config/AGENTS.md").exists()
                lines = [line for line in err.getvalue().splitlines() if "AGENTS.md" in line]
                assert len(lines) == 1, err.getvalue()
                # memory() runs memory-context.sh when machine-context.sh is absent, prefers machine-context.sh when both exist.
                hooks_dir = AGENTS / "hooks"
                hooks_dir.mkdir()
                assert memory(empty_agents) == ""
                (hooks_dir / "memory-context.sh").write_text("#!/bin/sh\necho from-memory-context\n")
                assert memory(empty_agents) == "from-memory-context"
                (hooks_dir / "machine-context.sh").write_text("#!/bin/sh\necho from-machine-context\n")
                assert memory(empty_agents) == "from-machine-context"
        finally:
            AGENTS = real_agents
            _WARNED.clear()
            _WARNED.update(saved_warned)
        # guard() allows shell commands when DCG is not installed, logs once, and keeps Rook's own denials.
        with tempfile.TemporaryDirectory() as no_dcg:
            fake_home = Path(no_dcg) / "home"
            fake_rt = Path(no_dcg) / "runtime"
            (fake_rt / "rook-antigravity").mkdir(parents=True)
            fake_home.mkdir()
            env = {**os.environ, "HOME": str(fake_home), "XDG_RUNTIME_DIR": str(fake_rt), "PATH": "/usr/bin:/bin"}
            quiet = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, env=env,
                                   input=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "echo hi"}},
                                                     "workspacePaths": ["/tmp"]}))
            assert "not installed" not in quiet.stderr, quiet.stderr  # A person who never set DCG up hears nothing.
            (fake_home / ".config/dcg").mkdir(parents=True)
            first = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, env=env,
                                   input=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "echo hi"}},
                                                     "workspacePaths": ["/tmp"]}))
            assert json.loads(first.stdout) == {"decision": "allow", "reason": ""}, first.stdout
            assert "not installed" in first.stderr, first.stderr
            second = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, env=env,
                                    input=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "git reset --hard"}},
                                                      "workspacePaths": ["/tmp"]}))
            assert json.loads(second.stdout) == {"decision": "allow", "reason": ""}, second.stdout
            assert second.stderr == "", second.stderr
            denied = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, env=env,
                                    input=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "t3 project remove demo"}},
                                                      "workspacePaths": ["/tmp"]}))
            assert json.loads(denied.stdout)["decision"] == "deny", denied.stdout
    finally:
        shutil.rmtree(HOME)
        HOME = real_home
    # Review 2, fixes 4 and 5: the stop and merge checks read program words and the systemctl verb, not quoted text.
    for command in ("systemctl --user restart rook", "/usr/bin/python relay.py restart", "relay.py restart",
                    "systemctl --user restart rook --show-transaction", "systemctl --user stop rook --no-pager -l status",
                    "kill $(pgrep -f rook.py)", "pgrep -f rook.py | xargs kill", "sudo systemctl restart rook",
                    "cd desktop && python3 -m relay reload overlay", "bash -c 'pkill -f rook'",
                    "python3 -B -m relay daily-restart", "python3 -mrelay restart", "python3 -u -m relay restart",
                    "gh api graphql -f query='mutation{mergePullRequest}'", "kill -9 -1", "pkill -f python3",
                    "killall python", f"launchctl bootout gui/501/{desk.LAUNCHD_LABEL}",
                    f"launchctl kickstart -k gui/501/{desk.LAUNCHD_LABEL}", f"launchctl kill TERM gui/501/{desk.LAUNCHD_LABEL}",
                    f"launchctl unload ~/Library/LaunchAgents/{desk.LAUNCHD_LABEL}.plist", f"launchctl stop {desk.LAUNCHD_LABEL}",
                    f"launchctl bootstrap gui/501 ~/Library/LaunchAgents/{desk.LAUNCHD_LABEL}.daily.plist",
                    f"launchctl remove {desk.LAUNCHD_LABEL}", f"launchctl disable gui/501/{desk.LAUNCHD_LABEL}",
                    f"launchctl kickstart -k gui/501/{desk.LAUNCHD_LABEL}.daily",
                    "launchctl unload ~/Library/LaunchAgents/com.rook.*.plist", "launchctl bootout gui/501/com.rook.compan?on",
                    "launchctl unload ~/Library/LaunchAgents/[c]om.rook.companion.plist"):
        assert denied_command(command), command
    for command in ("/usr/bin/python relay.py note 'Done; kill the rook overlay test later'",  # Review 3, fix 3.
                    "/usr/bin/python relay.py tell 'Build passed; systemctl rook restart is next'",
                    "/usr/bin/python relay.py set voice 'Miles' --say 'Hi; rm ~/Code/rook ok'",
                    "/usr/bin/python relay.py note 'the relay restart on nimbus failed'",
                    "/usr/bin/python relay.py tell 'Rook will kill the rook timer'", "rg -n 'kill' ~/Code/rook/desktop",
                    "git log --grep 'kill rook'", "grep -rn mergePullRequest ~/Code", "systemctl --user status rook",
                    "launchctl print gui/501/com.rook.companion", "launchctl list com.rook.companion",
                    "launchctl blame gui/501/com.rook.companion", "launchctl print-disabled gui/501",
                    "launchctl kickstart -k gui/501/com.example.other", "launchctl kickstart gui/501/com.rook.agent-dream",
                    "launchctl bootout gui/501/com.rook.medium-voice",
                    "t3 thread start /x - --json --title 'Kill switch for rook' <<'EOF'\nx\nEOF",
                    "/usr/bin/python relay.py update --install"):  # The one update Rook runs when its owner asks.
        assert not denied_command(command), command
    # Review 2, fix 1: T3 tools outside Rook's list are refused in both of agy's forms, as are t3_queue's writes.
    for name, args, decision in (("mcp_t3_create_threads", {}, "deny"), ("mcp_t3_t3_thread_send_attachments", {}, "deny"),
                                 ("call_mcp_tool", {"ServerName": "t3", "ToolName": "schedule_task"}, "deny"),
                                 ("mcp_t3_t3_queue", {"action": "add"}, "deny"),
                                 ("call_mcp_tool", {"ServerName": "t3", "ToolName": "t3_queue",
                                                    "Arguments": {"action": "list"}}, "allow"),
                                 ("mcp_t3_t3_thread_read", {}, "allow")):
        done = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, input=json.dumps(
            {"toolCall": {"name": name, "args": args}}))
        assert json.loads(done.stdout)["decision"] == decision, (name, args, done.stdout)
    assert not set(T3_TOOLS) & set(T3_DENIED_TOOLS) and set(T3_EAGER) <= set(T3_TOOLS)
    # Review 2, fix 8: the server's and tool's names count whatever their case or spaces.
    for args in ({"ServerName": "T3", "ToolName": "pull_request_merge"}, {"ServerName": " t3", "ToolName": "X"},
                 {"serverName": "t3", "toolName": " Pull_Request_Merge "}):
        done = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, input=json.dumps(
            {"toolCall": {"name": "call_mcp_tool", "args": args}}))
        assert json.loads(done.stdout)["decision"] == "deny", (args, done.stdout)
    # Review 3, fix 9: each refused T3 tool hears the right route.
    for name, args, words in (("mcp_t3_create_threads", {}, "t3_thread_launch"),
                              ("mcp_t3_t3_queue", {"action": "cancel"}, owned("⟦hers⟧ to do"))):
        done = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, input=json.dumps(
            {"toolCall": {"name": name, "args": args}}))
        assert words in json.loads(done.stdout)["reason"], (name, done.stdout)
    # Review of t3/neon-file-tools, B1: each protected root is refused through both file tools and the shell guard;
    # Rook's own places pass.
    for root in PROTECTED_ROOTS:
        target = str(root if root.name == "dcg" else root / "x.txt")
        for tool in ("write_file", "edit_file"):
            assert allowed_tool(tool) and tool in WRITE_TOOLS and writes_rook({"TargetFile": target}), (tool, target)
        assert shell_writes_rook(f"tee {target}", str(Path.home() / "Work")), target
    for place in (Path.home() / ".config/rook/model-preferences.md", Path.home() / "Work/note.md",
                  Path.home() / ".local/share/rook/renders/a.png", Path.home() / ".local/state/rook/x.json",
                  Path.home() / "Code/someproject/README.md"):
        assert not writes_rook({"TargetFile": str(place)}) and not shell_writes_rook(f"tee {place}"), place
    # B3: a path nested in the arguments, in a list, or as a file:// URI counts. B2: the tool's name in any case.
    assert writes_rook({"Edits": [{"Path": f"{Path.home()}/.ssh/authorized_keys"}]})
    assert writes_rook({"TargetFile": f"file://{Path.home()}/.agents/AGENTS.md"})
    for name, args in (("WRITE_FILE", {"TargetFile": str(code_root / "desktop/rook.py")}),
                       ("write_file", {"TargetFile": str(HOME / "config/hooks.json")}),
                       ("edit_file", {"Files": [f"{Path.home()}/.config/dcg/config.toml"]})):
        done = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, input=json.dumps(
            {"toolCall": {"name": name, "args": args}, "workspacePaths": [str(Path.home() / "Work")]}))
        answer = json.loads(done.stdout)
        assert answer["decision"] == "deny" and owned("That is ⟦owner⟧'s to do") in answer["reason"], (name, answer)
    # One-time global skill reads: reading ~/.agents/skills/<name>/SKILL.md passes the guard while writes stay denied.
    skill_path = f"{Path.home()}/.agents/skills/some-skill/SKILL.md"
    for tool in ("read_file", "view_file"):
        done = subprocess.run([sys.executable, __file__, "guard"], capture_output=True, text=True, input=json.dumps(
            {"toolCall": {"name": tool, "args": {"Path": skill_path}}, "workspacePaths": [str(Path.home() / "Work")]}))
        assert json.loads(done.stdout)["decision"] == "allow", (tool, done.stdout)
    # Review 3, fix 6: a server other than Rook's own, by call_mcp_tool or by name, is refused.
    rook_servers = set(re.findall(r'servers\["(\w+)"\]', (ROOT / "desktop/rook.py").read_text()))
    assert set(ROOK_SERVERS) <= rook_servers and rook_servers - set(ROOK_SERVERS) <= set(_OPTIONAL_SERVERS)
    for name, args in (("call_mcp_tool", {"ServerName": "mcp_t3", "ToolName": "create_threads"}),
                       ("call_mcp_tool", {"ServerName": "t3-code", "ToolName": "create_threads"}),
                       ("mcp_other_tool", {})):
        assert not allowed_tool(name, args), (name, args)
    if has_wow_server:
        assert allowed_tool("call_mcp_tool", {"ServerName": "wow", "ToolName": "find_npc"}) and allowed_tool("mcp_wow_x")
    else:
        assert not allowed_tool("call_mcp_tool", {"ServerName": "wow", "ToolName": "find_npc"}) and not allowed_tool("mcp_wow_x")
    for server, source in SERVER_SOURCES.items():  # Each server's tools, all of them eager.
        defined = re.findall(r"@mcp\.tool\b.*?\n\s*(?:async\s+)?def (\w+)", (ROOT / source).read_text(), re.S)
        assert sorted(defined) == sorted(EAGER_TOOLS[server]), (server, defined)
    # The hook's list of denied T3 tools must be rook.py's.
    import ast
    source = re.search(r"^T3_DENIED = (\(.*\))$", (ROOT / "desktop/rook.py").read_text(), re.M)[1]
    assert ast.literal_eval(source) == T3_DENIED_TOOLS, source
    # Forge policy: relay.py forge (including --help), reading/searching/diffing forge files, and same-named scripts
    # in other folders pass; running Rook's own themes/forge/{bake,forge,preview}.py directly or overriding
    # HOME/XDG_CONFIG_HOME on relay.py forge is denied.
    for good in (f"/usr/bin/python {ROOT}/desktop/relay.py forge list",
                 f"/usr/bin/python {ROOT}/desktop/relay.py forge --help",
                 f"/usr/bin/python {ROOT}/desktop/relay.py forge bake mine rook",
                 f"/usr/bin/python {ROOT}/desktop/relay.py forge bake nova-mine orbit --show",
                 f"/usr/bin/python {ROOT}/desktop/relay.py forge new nova-mine orbit --think <<'GLSL'\nvec4 icon(vec2 p, float t, int l){{return vec4(0);}}\nGLSL",
                 f"cat {ROOT}/themes/forge/bake.py",
                 "git diff -- themes/forge/preview.py",
                 "grep -n icon forge.py",
                 "echo forge.py is a file",
                 "cd ~/Code/other && python preview.py"):
        assert not denied_forge(good) and not denied_command(good), good
    for bad in (f"XDG_CONFIG_HOME=/tmp /usr/bin/python {ROOT}/desktop/relay.py forge new nova-mine orbit",
                f"HOME=/tmp /usr/bin/python {ROOT}/desktop/relay.py forge new nova-mine orbit",
                f"env HOME=/x /usr/bin/python {ROOT}/desktop/relay.py forge bake nova-mine",
                f"/usr/bin/python {ROOT}/themes/forge/bake.py nova --all",
                f"/usr/bin/python {ROOT}/themes/forge/forge.py bake nova-mine",
                f"/usr/bin/python {ROOT}/themes/forge/preview.py nova sheet --out /tmp/s.png",
                f"{ROOT}/themes/forge/bake.py nova --all"):
        assert denied_forge(bad) and denied_command(bad), bad
    print("ok")


if __name__ == "__main__":
    {"guard": guard, "check": check}[sys.argv[1]]()
